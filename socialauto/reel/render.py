"""Step 3-4 render: real B-roll + infographics in Remotion, the owner's voice, ducked music, -14 LUFS, `_vN` export.

    B-roll normalised (h264, <= 1080 px short side, trimmed) -> Remotion props (scenes cut at the words, subtitle lines,
    the safe-zone layout) -> silent Remotion render -> voice + music mix (sidechain ducking, loudnorm -14 LUFS)
    -> exports/<date>-<topic>_vN.mp4 -> frames at the 8 section boundaries -> gate + checklist (after).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from ..video import audio, ffmpeg, quality
from ..voice import Word
from . import checklist, layout as layout_mod
from .broll import Clip
from .naming import Places
from .script import PART_UZ

log = logging.getLogger(__name__)

TAIL = 0.8
MAX_CLIP_SECONDS = 15
STYLE = {"accent": "#38bdf8", "titleSize": 64, "subtitleSize": 66, "infoSize": 150, "font": "Montserrat"}


class ReelRenderError(RuntimeError):
    pass


@dataclass
class ReelRender:
    version: int
    export: Path
    duration: float
    frames: list[tuple[str, float, Path]]
    gate: list[dict]
    after: checklist.Report
    props: dict


def normalize_clip(src: Path, dst: Path, kind: str, seconds: float) -> tuple[Path, float | None]:
    """Videos -> h264 mp4 (short side <= 1080, trimmed to what the scene needs); photos -> jpg <= 1600 px."""
    if dst.exists():
        return dst, _probe_seconds(dst) if kind == "video" else None
    if kind == "video":
        need = min(MAX_CLIP_SECONDS, seconds + 1.0)
        ffmpeg.run([ffmpeg.binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-threads", "2", "-i", str(src), "-t",
                    f"{need:.2f}", "-an", "-vf", "scale='if(gt(iw,ih),-2,min(1080,iw))':'if(gt(iw,ih),min(1080,ih),-2)',fps=30",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-threads", "2", str(dst)],
                   timeout=900)
        return dst, _probe_seconds(dst)
    with Image.open(src) as im:
        im = im.convert("RGB")
        im = ImageOps.contain(im, (1600, 1600))
        im.save(dst, "JPEG", quality=90)
    return dst, None


def _probe_seconds(path: Path) -> float:
    try:
        return float(ffmpeg.probe(path)["format"]["duration"])
    except Exception:          # noqa: BLE001
        return 1.0


def build_props(script: dict, clips: list[Clip], part_starts: list[float], lines: list[dict], total: float,
                lay: dict, media: dict[str, tuple[str, float | None]]) -> dict:
    scenes = []
    for k, (part, clip) in enumerate(zip(script["parts"], clips)):
        start = part_starts[k]
        end = part_starts[k + 1] if k + 1 < len(part_starts) else total
        src, secs = media[clip.part]
        scenes.append({"part": part["part"], "start": round(start, 3), "end": round(end, 3),
                       "media": {"type": clip.kind, "src": src, **({"seconds": round(secs, 2)} if secs else {})},
                       "info": part.get("info")})
    return {"width": layout_mod.W, "height": layout_mod.H, "fps": 30, "duration": round(total, 3),
            "title": script["title"], "scenes": scenes, "lines": lines, "layout": layout_mod.as_props(lay), "style": STYLE}


class ReelRenderer:
    def __init__(self, root: Path, places: Places, music_dir: Path, music_db: float = -20, concurrency: int = 2):
        self.root = root
        self.places = places
        self.music_dir = music_dir
        self.music_db = music_db
        self.concurrency = concurrency

    def remotion_bin(self) -> Path:
        name = "remotion.cmd" if sys.platform.startswith("win") else "remotion"   # npm makes a .cmd shim on Windows
        b = self.root / "remotion" / "node_modules" / ".bin" / name
        if not b.exists():
            raise ReelRenderError("Remotion is not installed: run `npm install` in remotion/")
        return b

    def render(self, *, base: str, script: dict, clips: list[Clip], voice_wav: Path, words: list[Word],
               part_starts: list[float], lines: list[dict], voice_seconds: float) -> ReelRender:
        work = self.places.work(base)
        total = round(voice_seconds + TAIL, 3)
        lay = layout_mod.default_layout()
        # 1. B-roll for Remotion (inside the work folder = Remotion's public dir).
        media: dict[str, tuple[str, float | None]] = {}
        for k, clip in enumerate(clips):
            start = part_starts[k]
            end = part_starts[k + 1] if k + 1 < len(part_starts) else total
            src = work / clip.file
            dst = src.with_name(src.stem + (".norm.mp4" if clip.kind == "video" else ".norm.jpg"))
            path, secs = normalize_clip(src, dst, clip.kind, end - start)
            media[clip.part] = (str(path.relative_to(work)), secs)
        fonts = work / "_fonts"
        fonts.mkdir(exist_ok=True)
        for f in ("Montserrat-ExtraBold.ttf", "Montserrat-Bold.ttf"):
            if not (fonts / f).exists():
                shutil.copy(self.root / "assets" / "fonts" / f, fonts / f)
        props = build_props(script, clips, part_starts, lines, total, lay, media)
        version, export = self.places.next_export(base)
        props_file = work / f"props_v{version}.json"
        props_file.write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
        # 2. Silent Remotion render.
        silent = work / f"render_v{version}.silent.mp4"
        cmd = [str(self.remotion_bin()), "render", "src/index.ts", "Reel", str(silent), f"--props={props_file}",
               f"--public-dir={work}", f"--concurrency={self.concurrency}", "--muted", "--log=error",
               "--disallow-parallel-encoding", "--offthreadvideo-cache-size-in-bytes=268435456"]   # law 9: low memory
        res = subprocess.run(cmd, cwd=self.root / "remotion", capture_output=True, text=True, timeout=3600)
        if res.returncode != 0 or not silent.exists():
            raise ReelRenderError(f"Remotion render failed: {(res.stderr or res.stdout)[-600:]}")
        # 3. Voice + music (ducked) -> -14 LUFS, muxed.
        voice_track = work / f"voice_track_v{version}.wav"
        ffmpeg.run([ffmpeg.binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", str(voice_wav), "-af",
                    "apad", "-t", f"{total:.3f}", "-ar", "48000", "-ac", "1", str(voice_track)])
        music = work / "music.wav"
        track = audio.pick_music_track(self.music_dir, version)
        if track:
            ffmpeg.decode_audio(track, music, total, 48000)
        else:
            audio.write_wav(music, audio.synth_music(total, 1000 + version))
        mixed = ffmpeg.mix_audio(voice_track, music, None, work / f"mix_v{version}.wav", self.music_db)
        tmp = export.with_suffix(".partial.mp4")
        ffmpeg.run([ffmpeg.binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", str(silent), "-i",
                    str(mixed), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar",
                    "48000", "-shortest", "-movflags", "+faststart", str(tmp)])
        tmp.replace(export)
        # 4. Frames at the 8 section boundaries.
        fdir = work / f"frames_v{version}"
        fdir.mkdir(exist_ok=True)
        frames = []
        for k, part in enumerate(script["parts"]):
            t = min(total - 0.2, part_starts[k] + 0.6)
            out = fdir / f"{k + 1:02d}-{part['part']}.jpg"
            ffmpeg.frame_at(export, t, out)
            frames.append((PART_UZ.get(part["part"], part["part"]), t, out))
        # 5. Gate + the after-render checklist.
        gate = self.gate(export, voice_track, total)
        after = checklist.after_render(export, frames, gate, total)
        report = {"version": version, "export": export.name, "duration": total, "gate": gate,
                  "frames": [{"part": p, "t": round(t, 2), "file": str(f.relative_to(work))} for p, t, f in frames]}
        (work / f"report_v{version}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        return ReelRender(version, export, total, frames, gate, after, props)

    @staticmethod
    def gate(video: Path, voice_track: Path, voice_seconds: float) -> list[dict]:
        g = quality.Gate()
        info = ffmpeg.probe(video)
        v = next((s for s in info["streams"] if s.get("codec_type") == "video"), {})
        a = next((s for s in info["streams"] if s.get("codec_type") == "audio"), {})
        g.add("Format (H.264/AAC, 1080×1920)", v.get("codec_name") == "h264" and a.get("codec_name") == "aac"
              and (v.get("width"), v.get("height")) == (1080, 1920),
              f"{v.get('codec_name')}/{a.get('codec_name')} {v.get('width')}×{v.get('height')}")
        loud = ffmpeg.loudness(video)
        g.add("Ovoz balandligi −14 LUFS", abs(loud["lufs"] + 14) <= 2.5, f"{loud['lufs']:.1f} LUFS")
        g.add("Cho'qqi (true peak)", loud["true_peak"] <= -0.8, f"{loud['true_peak']:.1f} dBTP")
        lag = quality.sync_lag(quality.decode_mono(voice_track), quality.decode_mono(video))
        g.add("Subtitr va ovoz sinxroni", abs(lag) <= quality.MAX_SYNC_LAG, f"{lag * 1000:+.0f} ms")
        black = ffmpeg.black_segments(video)
        g.add("Qora kadrlar yo'q", not black, "yo'q" if not black else ", ".join(f"{s:.1f}–{e:.1f}s" for s, e in black[:3]))
        return g.checks

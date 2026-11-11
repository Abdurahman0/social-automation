"""FFmpeg/ffprobe helpers: scene motion, final composition, measurements (copied from ytauto, extended)."""

import hashlib
import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

XFADE = 0.4   # seconds of crossfade between scenes


class FFmpegError(RuntimeError):
    pass


def binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise FFmpegError(f"{name} not found on PATH")
    return path


def run(args: list[str], timeout: int = 1800) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"{Path(args[0]).name} timed out after {timeout}s") from exc
    if result.returncode != 0:
        raise FFmpegError(f"{Path(args[0]).name} exited {result.returncode}: {result.stderr.strip()[-800:]}")
    return result


def _filter_path(path: Path) -> str:
    """Escape a path for use inside an ffmpeg filter argument."""
    return re.sub(r"([\\:'\[\],;])", r"\\\1", str(path))


@dataclass(frozen=True)
class Clip:
    image: Path
    seconds: float     # time on screen before the next scene starts


_MOTIONS = [  # (zoom expression, x expression, y expression) — slow Ken Burns moves
    ("1+0.10*on/{n}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),                 # push in
    ("1.10-0.10*on/{n}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),              # pull out
    ("1.08", "(iw-iw/zoom)*on/{n}", "ih/2-(ih/zoom/2)"),                       # pan right
    ("1.08", "(iw-iw/zoom)*(1-on/{n})", "ih/2-(ih/zoom/2)"),                   # pan left
    ("1+0.08*on/{n}", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*(1-on/{n})"),          # rise
]


def compose(clips: list[Clip], audio: Path, subtitles: Path, out: Path, *, width: int, height: int,
            fps: int, preset: str, fonts_dir: Path | None = None) -> Path:
    """Render scene images with motion + crossfades, burn subtitles and mux the mixed audio."""
    if not clips:
        raise FFmpegError("no clips")
    args = [binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error"]
    parts, durations = [], []
    for i, clip in enumerate(clips):
        d = clip.seconds + (XFADE if i < len(clips) - 1 else 0)
        frames = max(2, round(d * fps))
        durations.append(frames / fps)
        z, x, y = (e.format(n=frames) for e in _MOTIONS[i % len(_MOTIONS)])
        args += ["-i", str(clip.image)]
        # Upscale a little above the output size so zoom/pan stays sharp, then move.
        parts.append(
            f"[{i}:v]scale={int(width * 1.25)}:{int(height * 1.25)}:force_original_aspect_ratio=increase,"
            f"crop={int(width * 1.25)}:{int(height * 1.25)},setsar=1,"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps},"
            f"trim=duration={durations[-1]:.3f},setpts=PTS-STARTPTS,fps={fps},settb=1/{fps},format=yuv420p[v{i}]")
    last, length = "v0", durations[0]
    for i in range(1, len(clips)):
        offset = length - XFADE
        parts.append(f"[{last}][v{i}]xfade=transition=fade:duration={XFADE}:offset={offset:.3f}[x{i}]")
        last, length = f"x{i}", offset + durations[i]
    sub = f"subtitles={_filter_path(subtitles)}"
    if fonts_dir:
        sub += f":fontsdir={_filter_path(fonts_dir)}"
    parts.append(f"[{last}]{sub}[vout]")
    args += ["-i", str(audio), "-filter_complex", ";".join(parts),
             "-map", "[vout]", "-map", f"{len(clips)}:a",
             "-c:v", "libx264", "-preset", preset, "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(fps),
             "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
             "-t", f"{length:.3f}", "-movflags", "+faststart", str(out)]
    out.parent.mkdir(parents=True, exist_ok=True)
    run(args)
    return out


def filter_audio(src: Path, out: Path, chain: str, seconds: float, rate: int = 22050) -> Path:
    """An audio filter chain (the channel's voice EQ/reverb) on a wav, trimmed/padded to `seconds`."""
    run([binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
         "-af", f"{chain},apad", "-t", f"{seconds:.3f}", "-ar", str(rate), "-ac", "1", str(out)])
    return out


def mix_audio(narration: Path, music: Path, sfx: Path | None, out: Path, music_db: float) -> Path:
    """Narration on top; music ducks under the voice; loudness normalised for YouTube (-14 LUFS)."""
    args = [binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", str(narration), "-i", str(music)]
    graph = [
        "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,asplit=2[voice][key]",
        f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={music_db}dB[bed]",
        "[bed][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[ducked]",
    ]
    inputs = "[voice][ducked]"
    if sfx:
        args += ["-i", str(sfx)]
        graph.append("[2:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=-8dB[fx]")
        inputs += "[fx]"
    n = 3 if sfx else 2
    graph.append(f"{inputs}amix=inputs={n}:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[out]")
    args += ["-filter_complex", ";".join(graph), "-map", "[out]", "-ar", "44100", "-c:a", "pcm_s16le", str(out)]
    run(args)
    return out


def decode_audio(src: Path, out: Path, seconds: float, rate: int) -> Path:
    """Any music file -> mono wav of exactly `seconds` (looped if shorter), with fades."""
    fade = min(1.5, seconds / 4)
    run([binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-stream_loop", "-1", "-i", str(src),
         "-t", f"{seconds:.3f}", "-af", f"afade=t=in:d={fade},afade=t=out:st={seconds - fade:.3f}:d={fade}",
         "-ac", "1", "-ar", str(rate), str(out)])
    return out


def probe(path: Path) -> dict:
    result = run([binary("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                  str(path)], timeout=120)
    return json.loads(result.stdout)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def validate(path: Path, *, width: int, height: int, min_seconds: float, max_seconds: float) -> dict:
    """Check the rendered file. Returns a report; raises FFmpegError listing every problem found."""
    if not path.exists() or path.stat().st_size == 0:
        raise FFmpegError(f"output missing or empty: {path}")
    info = probe(path)
    video = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    audio = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    duration = float(info.get("format", {}).get("duration", 0))
    problems = []
    if not video:
        problems.append("no video stream")
    elif (video[0].get("width"), video[0].get("height")) != (width, height):
        problems.append(f"resolution {video[0].get('width')}x{video[0].get('height')}, expected {width}x{height}")
    if not audio:
        problems.append("no audio stream")
    if not min_seconds <= duration <= max_seconds:
        problems.append(f"duration {duration:.1f}s outside {min_seconds:g}-{max_seconds:g}s")
    # Full decode catches truncated or corrupt files; volumedetect catches silent audio.
    decode = subprocess.run([binary("ffmpeg"), "-v", "error", "-i", str(path), "-af", "volumedetect",
                             "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    errors = [l for l in decode.stderr.splitlines() if "volumedetect" not in l and "Parsed_" not in l and l.strip()]
    if decode.returncode != 0 or errors:
        problems.append(f"decode errors: {' | '.join(errors)[:300]}")
    stats = subprocess.run([binary("ffmpeg"), "-hide_banner", "-i", str(path), "-af", "volumedetect", "-vn",
                            "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600).stderr
    m = re.search(r"mean_volume: (-?[\d.]+) dB", stats)
    mean_db = float(m.group(1)) if m else -99.0
    if mean_db < -45:
        problems.append(f"audio is near silent ({mean_db:.0f} dB)")
    report = {"duration": round(duration, 2), "width": video[0].get("width") if video else None,
              "height": video[0].get("height") if video else None,
              "video_codec": video[0].get("codec_name") if video else None,
              "audio_codec": audio[0].get("codec_name") if audio else None,
              "mean_volume_db": mean_db, "size_bytes": path.stat().st_size}
    if problems:
        raise FFmpegError("validation failed: " + "; ".join(problems))
    return report


def make_preview(src: Path, out: Path, max_bytes: int, width: int = 720, height: int = 1280) -> Path:
    """Smaller copy for Telegram (Bot API uploads are limited to 50 MB). The full file is what gets
    uploaded to YouTube; the preview is the same edit at 720p (720x1280 for Shorts, 1280x720 for films)."""
    for crf in (28, 32, 36):
        run([binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
             "-vf", f"scale={width}:{height}", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
             "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out)])
        if out.stat().st_size <= max_bytes:
            return out
    raise FFmpegError(f"preview is still larger than {max_bytes // 1_000_000} MB")


def loudness(path: Path) -> dict:
    """Integrated loudness (LUFS) and true peak (dBTP) of a file's audio (EBU R128)."""
    out = subprocess.run([binary("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af",
                          "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600).stderr
    summary = out[out.rfind("Summary:"):] if "Summary:" in out else out
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", summary)
    tp = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    return {"lufs": float(i.group(1)) if i else -99.0,
            "true_peak": float(tp.group(1)) if tp and tp.group(1) != "-inf" else -99.0}


def black_segments(path: Path, min_seconds: float = 0.3) -> list[tuple[float, float]]:
    """Intervals of (almost) black frames."""
    out = subprocess.run([binary("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path), "-an", "-vf",
                          f"blackdetect=d={min_seconds}:pic_th=0.97:pix_th=0.08", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900).stderr
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:(-?[\d.]+) black_end:(-?[\d.]+)", out)]


def frame_at(path: Path, seconds: float, out: Path) -> Path:
    run([binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{seconds:.2f}", "-i", str(path),
         "-frames:v", "1", "-q:v", "3", str(out)], timeout=120)
    return out

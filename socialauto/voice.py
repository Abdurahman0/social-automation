"""The owner's voice (law 14): intake checks, cleanup, analysis, local transcription and script comparison.

Everything here is free and local:
- FFmpeg decodes any voice/audio/video file to wav, trims leading/trailing silence, removes rumble and light
  background noise (highpass + afftdn) and normalizes loudness to about -14 LUFS (both platforms' target). No
  pitch or "robot" effects: the voice stays natural.
- The raw recording is analysed first (too quiet, clipping, noisy) so the owner can get a short tip next time.
- faster-whisper (CPU, int8) transcribes the CLEANED file with word timestamps, so captions are built from what the
  owner actually said and are synced to exactly the audio that goes into the video.
- The transcript is compared with the approved script (word alignment): small differences are fine, a big
  missing part or an over-long recording makes the bot ask the owner once.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import subprocess
import wave
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from .config import VoiceConfig
from .video import ffmpeg

log = logging.getLogger(__name__)

SAMPLE_RATE = 48000
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".oga", ".opus", ".aac", ".flac", ".webm", ".mp4", ".mov", ".mkv"}
AUDIO_MIME_PREFIXES = ("audio/",)
VIDEO_MIME_PREFIXES = ("video/",)
MISSING_RUN = 6                    # this many consecutive script words unheard = "a big part is missing"


class VoiceError(RuntimeError):
    """The file cannot be used (not audio, unreadable, empty)."""


# --- intake -------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Intake:
    ok: bool
    reason: str = ""          # "type" | "size" when not ok
    suffix: str = ".ogg"


def check_upload(kind: str, size: int | None, max_mb: int, mime: str = "", filename: str = "") -> Intake:
    """kind: voice | audio | document | video_note | video. Documents must be audio (by mime or extension)."""
    suffix = Path(filename).suffix.lower() if filename else ""
    if kind == "document":
        is_audio = mime.startswith(AUDIO_MIME_PREFIXES) or mime.startswith(VIDEO_MIME_PREFIXES) or suffix in AUDIO_EXTENSIONS
        if not is_audio:
            return Intake(False, "type")
    elif kind not in ("voice", "audio", "video_note", "video"):
        return Intake(False, "type")
    if size is not None and size > max_mb * 1_000_000:
        return Intake(False, "size")
    default = {"voice": ".ogg", "audio": ".mp3", "video_note": ".mp4", "video": ".mp4"}.get(kind, ".bin")
    return Intake(True, "", suffix if suffix in AUDIO_EXTENSIONS else default)


# --- analysis + cleanup -------------------------------------------------------------------------------------------

def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
        if w.getnchannels() > 1:
            data = data.reshape(-1, w.getnchannels()).mean(axis=1)
    return data, rate


def decode(src: Path, out: Path, rate: int = SAMPLE_RATE) -> Path:
    """Any audio or video file -> mono 16-bit wav (the audio track only)."""
    try:
        ffmpeg.run([ffmpeg.binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-vn",
                    "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le", str(out)], timeout=300)
    except ffmpeg.FFmpegError as exc:
        raise VoiceError(f"cannot decode the recording: {exc}") from exc
    if not out.exists() or out.stat().st_size < 2000:
        raise VoiceError("the recording has no audio")
    return out


def analyse(samples: np.ndarray, rate: int) -> dict[str, float]:
    """Levels of the raw recording: speech level, noise floor, clipping share (all in dBFS / fractions)."""
    if not len(samples):
        return {"speech_db": -120.0, "noise_db": -120.0, "snr_db": 0.0, "clipped": 0.0, "seconds": 0.0}
    win = max(1, int(rate * 0.05))
    n = len(samples) // win
    frames = samples[: n * win].reshape(n, win) if n else samples.reshape(1, -1)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    speech, noise = float(np.percentile(db, 90)), float(np.percentile(db, 10))
    clipped = float(np.mean(np.abs(samples) >= 0.995))
    return {"speech_db": round(speech, 1), "noise_db": round(noise, 1), "snr_db": round(speech - noise, 1),
            "clipped": round(clipped, 5), "seconds": round(len(samples) / rate, 2)}


def level_problems(levels: dict[str, float]) -> list[str]:
    """Voice problems coded for the lessons store ("<code>: details")."""
    out = []
    if levels["speech_db"] < -38:
        out.append(f"quiet: speech level {levels['speech_db']:.0f} dBFS (too far from the microphone)")
    if levels["clipped"] > 0.001:
        out.append(f"clipping: {levels['clipped'] * 100:.2f}% of samples clipped (too loud / too close)")
    if levels["snr_db"] < 15:
        out.append(f"noise: only {levels['snr_db']:.0f} dB between speech and background noise")
    return out


def clean(raw_wav: Path, out: Path, target_lufs: float = -14.0, compressor: bool = False) -> Path:
    """Trim silence at both ends, light noise reduction, (optionally) a gentle compressor, loudness normalize
    (two-pass loudnorm). The owner's reel flow uses the compressor (highpass 80 Hz + compressor)."""
    trim = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15,areverse,"
            "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.25,areverse")
    denoise = "highpass=f=80,lowpass=f=12000,afftdn=nf=-30:nr=10"
    if compressor:
        denoise += ",acompressor=threshold=-20dB:ratio=3:attack=5:release=120:makeup=2"
    base = f"{trim},{denoise}"
    measure = subprocess.run([ffmpeg.binary("ffmpeg"), "-hide_banner", "-i", str(raw_wav), "-af",
                              f"{base},loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", measure.stderr, re.S)
    if m:
        s = json.loads(m.group(0))
        norm = (f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:measured_I={s['input_i']}:measured_TP={s['input_tp']}:"
                f"measured_LRA={s['input_lra']}:measured_thresh={s['input_thresh']}:offset={s['target_offset']}:"
                "linear=true")
    else:
        norm = f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
    ffmpeg.run([ffmpeg.binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw_wav), "-af",
                f"{base},{norm}", "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(out)], timeout=300)
    return out


# --- transcription ------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float

    def as_dict(self) -> dict[str, Any]:
        return {"w": self.text, "s": round(self.start, 3), "e": round(self.end, 3)}


def words_from_json(items: list[dict[str, Any]]) -> list[Word]:
    return [Word(i["w"], float(i["s"]), float(i["e"])) for i in items]


class Transcriber(Protocol):
    def transcribe(self, wav: Path, language: str) -> list[Word]: ...


@lru_cache(maxsize=1)
def _whisper(model: str, compute: str, root: str):
    from faster_whisper import WhisperModel
    return WhisperModel(model, device="cpu", compute_type=compute, cpu_threads=4, download_root=root)


class WhisperTranscriber:
    """faster-whisper on the CPU. The model (base: ~150 MB) is downloaded once into models/whisper (free)."""

    def __init__(self, cfg: VoiceConfig, models_dir: Path):
        self.cfg = cfg
        self.models_dir = models_dir

    def transcribe(self, wav: Path, language: str = "en") -> list[Word]:
        model = _whisper(self.cfg.whisper_model, self.cfg.whisper_compute, str(self.models_dir))
        # Decoded by our own ffmpeg to 16 kHz float32 (faster-whisper's PyAV path is version-fragile).
        pcm = subprocess.run([ffmpeg.binary("ffmpeg"), "-v", "error", "-i", str(wav), "-ac", "1", "-ar", "16000",
                              "-f", "s16le", "-"], capture_output=True, timeout=300, check=True).stdout
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        segments, _ = model.transcribe(samples, language=language, word_timestamps=True, beam_size=5,
                                       vad_filter=False, condition_on_previous_text=False)
        words = []
        for seg in segments:
            for w in seg.words or []:
                text = w.word.strip()
                if text:
                    words.append(Word(text, float(w.start), float(w.end)))
        return words


LANG_CODES = {"english": "en", "uzbek": "uz", "russian": "ru", "spanish": "es", "german": "de", "french": "fr",
              "turkish": "tr", "arabic": "ar"}


def language_code(name: str) -> str:
    return LANG_CODES.get(name.strip().lower(), name.strip().lower()[:2] or "en")


# --- comparison with the script -----------------------------------------------------------------------------------

def norm_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower().replace("’", "'"))


@dataclass
class Comparison:
    coverage: float                     # share of script words heard
    missing: list[str] = field(default_factory=list)   # missing passages (script text)
    extra_words: int = 0

    @property
    def big_gap(self) -> bool:
        return bool(self.missing)


def compare(script_text: str, spoken: list[Word]) -> Comparison:
    want = norm_words(script_text)
    got = [w for word in spoken for w in norm_words(word.text)]
    if not want:
        return Comparison(1.0)
    sm = difflib.SequenceMatcher(a=want, b=got, autojunk=False)
    matched = sum(b.size for b in sm.get_matching_blocks())
    missing, extra = [], 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace") and i2 - i1 >= MISSING_RUN and (tag == "delete" or (j2 - j1) < (i2 - i1) / 2):
            missing.append(" ".join(want[i1:i2]))
        if tag in ("insert", "replace"):
            extra += j2 - j1
    return Comparison(round(matched / len(want), 3), missing, extra)


def voice_problems(comparison: Comparison, duration: float, hard_max: float, min_coverage: float,
                   min_seconds: float = 3.0) -> list[str]:
    """Reasons to ask the owner before rendering (coded for the lessons store)."""
    out = []
    if comparison.coverage < min_coverage or comparison.big_gap:
        gap = f" (e.g. “{comparison.missing[0][:80]}”)" if comparison.missing else ""
        out.append(f"missing: only {comparison.coverage:.0%} of the script was heard{gap}")
    if duration > hard_max:
        out.append(f"too_long: the recording is {duration:.0f}s; the limit is {hard_max:.0f}s")
    if duration < min_seconds:
        out.append(f"too_short: the recording is only {duration:.1f}s")
    return out


# --- timing: scenes follow the real words -------------------------------------------------------------------------

def scene_starts(scene_texts: list[str], spoken: list[Word]) -> list[float]:
    """When each scene's first word is actually said. Scenes whose words were not heard get interpolated times."""
    if not spoken:
        return [0.0] * len(scene_texts)
    want: list[str] = []
    first_index: list[int] = []
    for text in scene_texts:
        first_index.append(len(want))
        want += norm_words(text)
    got, owner = [], []
    for k, word in enumerate(spoken):
        for w in norm_words(word.text):
            got.append(w)
            owner.append(k)
    mapping: dict[int, int] = {}
    for block in difflib.SequenceMatcher(a=want, b=got, autojunk=False).get_matching_blocks():
        for d in range(block.size):
            mapping[block.a + d] = block.b + d
    total = spoken[-1].end
    starts = []
    for idx in first_index:
        hit = next((mapping[i] for i in range(idx, min(len(want), idx + 8)) if i in mapping), None)
        if hit is not None:
            starts.append(spoken[owner[hit]].start)
        else:
            starts.append(total * idx / max(1, len(want)))
    starts[0] = 0.0
    for i in range(1, len(starts)):            # keep order and a minimum on-screen time
        starts[i] = max(starts[i], starts[i - 1] + 1.0)
    return starts


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


@dataclass
class ProcessedVoice:
    clean_path: Path
    duration: float
    words: list[Word]
    transcript: str
    levels: dict[str, float]
    level_problems: list[str]


def process(raw: Path, workdir: Path, cfg: VoiceConfig, transcriber: Transcriber, language: str,
            compressor: bool = False) -> ProcessedVoice:
    """Raw upload -> analysed, cleaned, transcribed voice."""
    workdir.mkdir(parents=True, exist_ok=True)
    raw_wav = decode(raw, workdir / "raw.wav")
    samples, rate = read_wav(raw_wav)
    levels = analyse(samples, rate)
    if levels["speech_db"] < -70:
        raise VoiceError("the recording is silent")
    clean_wav = clean(raw_wav, workdir / "voice_clean.wav", cfg.target_lufs, compressor)
    duration = wav_duration(clean_wav)
    words = transcriber.transcribe(clean_wav, language)
    if not words:
        raise VoiceError("no speech was recognised in the recording")
    return ProcessedVoice(clean_wav, round(duration, 2), words, " ".join(w.text for w in words), levels,
                          level_problems(levels))

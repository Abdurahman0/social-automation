"""Music bed (copied from ytauto, retuned for a curious/warm mood).

A royalty-free track from assets/music/ is used when the owner provides one; otherwise a soft ambient bed is
synthesized locally (free, nothing downloaded). A soft whoosh marks scene changes.
"""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np

SAMPLE_RATE = 48000
MUSIC_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}
# Warm major-seventh-ish pads (Cmaj7, Fmaj7, Am7, G6) cycling slowly: curious, light, not dark.
_PROGRESSION = [(130.81, 164.81, 196.0, 246.94), (174.61, 220.0, 261.63, 329.63),
                (110.0, 130.81, 164.81, 196.0), (98.0, 123.47, 146.83, 164.81)]


def pick_music_track(music_dir: Path, seed: int) -> Path | None:
    if music_dir.is_dir():
        tracks = sorted(p for p in music_dir.iterdir() if p.suffix.lower() in MUSIC_EXTENSIONS)
        if tracks:
            return random.Random(seed).choice(tracks)
    return None


def synth_music(seconds: float, seed: int, chord_seconds: float = 4.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(seconds * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    out = np.zeros(n, dtype=np.float64)
    start = rng.integers(0, len(_PROGRESSION))
    xf = 0.8                                  # chord crossfade seconds
    for k in range(int(seconds / chord_seconds) + 2):
        chord = _PROGRESSION[(start + k) % len(_PROGRESSION)]
        a, b = k * chord_seconds - xf, (k + 1) * chord_seconds + xf
        mask = (t >= a) & (t < b)
        if not mask.any():
            continue
        tt = t[mask]
        env = np.clip(np.minimum(tt - a, b - tt) / xf, 0, 1)
        for i, f in enumerate(chord):
            lfo = 0.7 + 0.3 * np.sin(2 * np.pi * (0.11 + 0.05 * i) * tt + i)
            out[mask] += env * lfo * (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(2 * np.pi * f * 2.001 * tt)) / (i + 1.5)
    pulse = 0.5 + 0.5 * np.sin(2 * np.pi * t / 0.5) ** 8      # a gentle 120 bpm shimmer
    out += 0.08 * pulse * np.sin(2 * np.pi * 523.25 * t)
    fade = min(n // 4, int(1.5 * SAMPLE_RATE))
    if fade:
        out[:fade] *= np.linspace(0, 1, fade)
        out[-fade:] *= np.linspace(1, 0, fade)
    return (0.5 * out / (np.abs(out).max() or 1)).astype(np.float32)


def whoosh(seconds: float = 0.5, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(seconds * SAMPLE_RATE)
    noise = rng.normal(0, 1, n)
    spec = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(n, 1 / SAMPLE_RATE)
    spec *= np.exp(-freqs / 2500)                       # soft, airy
    out = np.fft.irfft(spec, n) * np.sin(np.pi * np.arange(n) / n) ** 2
    return (0.35 * out / (np.abs(out).max() or 1)).astype(np.float32)


def sfx_track(seconds: float, cuts: list[float], seed: int) -> np.ndarray:
    out = np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)
    for k, at in enumerate(cuts):
        clip = whoosh(seed=seed + k)
        i = max(0, int((at - 0.25) * SAMPLE_RATE))
        j = min(len(out), i + len(clip))
        out[i:j] += clip[: j - i]
    return out


def write_wav(path: Path, samples: np.ndarray, rate: int = SAMPLE_RATE) -> Path:
    import wave
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return path

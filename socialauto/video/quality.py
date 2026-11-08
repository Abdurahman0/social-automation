"""Measurements used by the reel quality gate: a check list, decoded audio, and the voice-to-video sync lag."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from . import ffmpeg

MAX_SYNC_LAG = 0.08          # seconds
ENV_STEP = 0.01


@dataclass
class Gate:
    checks: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append({"name": name, "ok": bool(ok), "detail": detail})

    @property
    def passed(self) -> bool:
        return all(c["ok"] for c in self.checks)

    @property
    def problems(self) -> list[str]:
        return [f"{c['name']}: {c['detail']}" for c in self.checks if not c["ok"]]


def decode_mono(path: Path, rate: int = 16000) -> np.ndarray:
    out = subprocess.run([ffmpeg.binary("ffmpeg"), "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(rate),
                          "-f", "s16le", "-"], capture_output=True, timeout=600, check=False).stdout
    return np.frombuffer(out, dtype="<i2").astype(np.float32) / 32768.0


def envelope(samples: np.ndarray, rate: int = 16000, step: float = ENV_STEP) -> np.ndarray:
    win = int(rate * step)
    n = len(samples) // win
    if n == 0:
        return np.zeros(1)
    return np.sqrt(np.mean(samples[: n * win].reshape(n, win) ** 2, axis=1) + 1e-12)


def sync_lag(voice: np.ndarray, mix: np.ndarray, max_lag: float = 1.0) -> float:
    """Seconds by which the voice in the mix is late (+) or early (-) relative to the clean voice."""
    a = np.log(envelope(voice) + 1e-4)
    b = np.log(envelope(mix) + 1e-4)
    n = min(len(a), len(b))
    a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
    k = int(max_lag / ENV_STEP)
    best, best_lag = -np.inf, 0
    for lag in range(-k, k + 1):
        if lag >= 0:
            x, y = a[: n - lag], b[lag:]
        else:
            x, y = a[-lag:], b[: n + lag]
        if len(x) < 10:
            continue
        c = float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-9))
        if c > best:
            best, best_lag = c, lag
    return best_lag * ENV_STEP

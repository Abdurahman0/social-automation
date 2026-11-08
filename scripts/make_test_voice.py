"""Make a TEST voice clip with Kokoro (law 14: real videos always use the owner's own recording).

The clip is only a stand-in for the owner's voice in tests and in the dry-run demo, and is always written as
tests/fixtures/sample_voice_<name>.wav so it can never be mistaken for a real narration.

    .venv/bin/python scripts/make_test_voice.py short "Text to speak."
"""

import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def main(name: str, text: str, voice: str = "am_michael") -> Path:
    from kokoro_onnx import Kokoro
    kokoro = Kokoro(str(ROOT / "models/kokoro/kokoro-v1.0.onnx"), str(ROOT / "models/kokoro/voices-v1.0.bin"))
    samples, rate = kokoro.create(text, voice=voice, speed=1.0, lang="en-us")
    pad = np.zeros(int(rate * 0.6), dtype=np.float32)          # a phone recording starts and ends with silence
    rng = np.random.default_rng(1)
    audio = np.concatenate([pad, np.asarray(samples, dtype=np.float32) * 0.6, pad])
    audio += rng.normal(0, 0.002, len(audio)).astype(np.float32)   # faint room noise
    out = ROOT / "tests" / "fixtures" / f"sample_voice_{name}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    print(out)
    return out


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *(sys.argv[3:4]))

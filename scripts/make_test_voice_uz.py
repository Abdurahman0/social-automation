"""Make an UZBEK test voice clip with espeak-ng (law 14: real videos always use the owner's own recording).

Kokoro has no Uzbek voice, so the demo's stand-in for the owner's narration is synthesised with the espeak-ng library
(Uzbek voice data `trk/uz`, already on this machine as a dependency of the phonemizer). It sounds robotic on purpose:
it is only a test fixture, always written as tests/fixtures/sample_voice_<name>.wav.

    .venv/bin/python scripts/make_test_voice_uz.py demo_uz "Matn..."
"""

import ctypes
import ctypes.util
import re
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
AUDIO_OUTPUT_SYNCHRONOUS = 2
POS_CHARACTER = 1
ESPEAK_CHARS_UTF8 = 1
ESPEAK_RATE, ESPEAK_PITCH = 1, 3


def synth(text: str, rate: int = 150) -> tuple[np.ndarray, int]:
    lib = ctypes.CDLL(ctypes.util.find_library("espeak-ng") or "libespeak-ng.so.1")
    sr = lib.espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0, None, 0)
    if sr <= 0:
        raise RuntimeError("espeak-ng could not start")
    chunks: list[np.ndarray] = []
    cb_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p)

    def cb(wav, n, events):
        if n > 0:
            chunks.append(np.ctypeslib.as_array(wav, shape=(n,)).copy())
        return 0
    keep = cb_type(cb)
    lib.espeak_SetSynthCallback(keep)
    if lib.espeak_SetVoiceByName(b"uz") != 0:
        raise RuntimeError("espeak-ng has no Uzbek voice")
    lib.espeak_SetParameter(ESPEAK_RATE, rate, 0)
    lib.espeak_SetParameter(ESPEAK_PITCH, 45, 0)
    data = text.encode("utf-8")
    lib.espeak_Synth(data, len(data) + 1, 0, POS_CHARACTER, 0, ESPEAK_CHARS_UTF8, None, None)
    lib.espeak_Synchronize()
    return (np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.int16)), sr


def main(name: str, text: str, rate: int = 185) -> Path:
    text = re.sub(r"[ʻʼ‘’`]", "'", text)
    samples, sr = synth(text, rate)
    pad = np.zeros(int(sr * 0.6), dtype=np.int16)
    rng = np.random.default_rng(3)
    audio = np.concatenate([pad, samples, pad]).astype(np.float32) / 32768.0
    audio = audio * 0.7 + rng.normal(0, 0.002, len(audio)).astype(np.float32)   # faint room noise, like a phone
    out = ROOT / "tests" / "fixtures" / f"sample_voice_{name}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    print(out, f"{len(audio) / sr:.1f}s")
    return out


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *(int(x) for x in sys.argv[3:4]))

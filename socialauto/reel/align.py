"""Uzbek voice -> word timings for subtitles and scene cuts (the role of the owner's `align_voice.py`).

1. The cleaned voice is split into chunks at pauses (ffmpeg silencedetect), each under ~25 s.
2. Each chunk is transcribed locally with rubaiSTT (the renamed NavaiSTT: Whisper-medium fine-tuned for Uzbek,
   Apache-2.0; CTranslate2 int8 build run by faster-whisper on the CPU) with word timestamps.
3. The recognised words are aligned to the APPROVED script (the text is known, so alignment beats free
   transcription): Cyrillic output is transliterated to Latin, apostrophes unified, then a word-level sequence
   alignment maps script words to spoken times; words in between get times interpolated by their length. Where the
   owner clearly said something else (an inserted phrase), the spoken words are used; a skipped passage is dropped.
4. Scene cuts = the time the first word of each of the 8 parts is said.
"""

from __future__ import annotations

import difflib
import logging
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..video import ffmpeg
from ..voice import Word

log = logging.getLogger(__name__)

_CYR = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i", "й": "y",
        "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
        "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'", "ы": "i", "ь": "", "э": "e", "ю": "yu",
        "я": "ya", "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h"}
_APOS = re.compile(r"[ʻʼ‘’`´]")
MAX_CHUNK = 25.0


def uz_latin(text: str) -> str:
    out = []
    for i, ch in enumerate(text):
        low = ch.lower()
        if low == "е" and (i == 0 or not text[i - 1].isalpha()):
            rep = "ye"
        else:
            rep = _CYR.get(low)
        if rep is None:
            out.append(ch)
        else:
            out.append(rep.capitalize() if ch.isupper() and rep else rep)
    return _APOS.sub("'", "".join(out))


def norm(token: str) -> str:
    t = uz_latin(token).lower().replace("'", "")
    return re.sub(r"[^a-z0-9]", "", t)


def split_words(text: str) -> list[str]:
    return re.findall(r"[\w'ʻʼ‘’`%.,-]+", _APOS.sub("'", text))


# --- chunks at pauses ------------------------------------------------------------------------------------------

def pauses(wav: Path, noise_db: int = -35, min_silence: float = 0.35) -> list[tuple[float, float]]:
    out = subprocess.run([ffmpeg.binary("ffmpeg"), "-hide_banner", "-nostats", "-i", str(wav), "-af",
                          f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: (-?[\d.]+)", out)]
    return list(zip(starts, ends))


def chunk_bounds(duration: float, silences: list[tuple[float, float]], max_len: float = MAX_CHUNK) -> list[tuple[float, float]]:
    """Cut points in the middle of pauses, so no chunk is longer than max_len (hard cut if a pause is missing)."""
    mids = sorted((a + b) / 2 for a, b in silences if 0 < (a + b) / 2 < duration)
    bounds, start = [], 0.0
    while duration - start > max_len:
        options = [m for m in mids if start + 3 < m <= start + max_len]
        cut = options[-1] if options else start + max_len
        bounds.append((start, cut))
        start = cut
    bounds.append((start, duration))
    return bounds


# --- transcription (rubaiSTT) -----------------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _model(path: str):
    from faster_whisper import WhisperModel
    return WhisperModel(path, device="cpu", compute_type="int8", cpu_threads=4)


class RubaiSTT:
    """rubaiSTT / NavaiSTT (CTranslate2 int8) through faster-whisper."""
    name = "rubaiSTT (NavaiSTT v2, Whisper-medium uz)"

    def __init__(self, model_dir: Path):
        self.model_dir = model_dir

    def available(self) -> bool:
        return (self.model_dir / "model.bin").exists()

    def transcribe(self, wav: Path, language: str = "uz") -> list[Word]:
        from ..voice import read_wav, wav_duration
        model = _model(str(self.model_dir))
        duration = wav_duration(wav)
        samples, rate = read_wav(wav)
        if rate != 16000:
            pcm = subprocess.run([ffmpeg.binary("ffmpeg"), "-v", "error", "-i", str(wav), "-ac", "1", "-ar", "16000",
                                  "-f", "s16le", "-"], capture_output=True, check=True, timeout=300).stdout
            samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        out: list[Word] = []
        for a, b in chunk_bounds(duration, pauses(wav)):
            piece = samples[int(a * 16000): int(b * 16000)]
            segments, _ = model.transcribe(piece, language=language, word_timestamps=True, beam_size=5,
                                           vad_filter=False, condition_on_previous_text=False)
            for seg in segments:
                for w in seg.words or []:
                    text = w.word.strip()
                    if not text:
                        continue
                    if out and (text[0] in "'ʻʼ‘’`" or out[-1].text.endswith(("'", "ʻ", "ʼ", "‘", "’"))):
                        prev = out.pop()                       # "yo" + "'qoladi" -> "yo'qoladi"
                        out.append(Word(prev.text + text, prev.start, a + float(w.end)))
                        continue
                    out.append(Word(text, a + float(w.start), a + float(w.end)))
        _model.cache_clear()                 # ~1.8 GB: free it before B-roll processing and the Remotion render
        import gc
        gc.collect()
        return out


# --- alignment to the approved script --------------------------------------------------------------------------

@dataclass
class Alignment:
    words: list[Word]                # the subtitle words with times
    part_starts: list[float]         # scene cuts (one per part)
    coverage: float                  # share of script words matched to speech
    skipped: list[str]               # script passages not heard


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(a=a, b=b, autojunk=False).ratio()


MATCH_MIN = 0.62          # two words are "the same" from this character similarity on (mishearings, endings)
GAP = -0.45


def dp_align(a: list[str], b: list[str]) -> list[tuple[int | None, int | None]]:
    """Global word alignment (Needleman-Wunsch) with character-similarity scores: pairs (i, j), gaps as None."""
    n, m = len(a), len(b)
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        score[i][0], back[i][0] = i * GAP, 1
    for j in range(1, m + 1):
        score[0][j], back[0][j] = j * GAP, 2
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            s = similarity(a[i - 1], b[j - 1])
            diag = score[i - 1][j - 1] + (s if s >= MATCH_MIN else s - 1.0)
            up, left = score[i - 1][j] + GAP, score[i][j - 1] + GAP
            best = max(diag, up, left)
            score[i][j] = best
            back[i][j] = 0 if best == diag else (1 if best == up else 2)
    out, i, j = [], n, m
    while i > 0 or j > 0:
        mv = back[i][j] if i > 0 and j > 0 else (1 if i > 0 else 2)
        if mv == 0:
            out.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif mv == 1:
            out.append((i - 1, None))
            i -= 1
        else:
            out.append((None, j - 1))
            j -= 1
    return out[::-1]


def align(part_texts: list[str], spoken: list[Word], duration: float) -> Alignment:
    script: list[tuple[int, str]] = []          # (part index, word)
    for k, text in enumerate(part_texts):
        script += [(k, w) for w in split_words(text)]
    a = [norm(w) for _, w in script]
    b = [norm(w.text) for w in spoken]
    times: list[tuple[float, float] | None] = [None] * len(script)
    extra: list[tuple[int, Word]] = []          # spoken words the owner added (inserted before script index)
    skip = [False] * len(script)
    skipped: list[str] = []
    matched = 0
    pairs = dp_align(a, b)
    run_del: list[int] = []
    run_ins: list[int] = []
    next_script = 0

    def flush() -> None:
        nonlocal run_del, run_ins
        if len(run_del) >= 3 and not run_ins:          # a passage the owner skipped
            for i in run_del:
                skip[i] = True
            skipped.append(" ".join(script[i][1] for i in run_del))
        if len(run_ins) >= 2 and not run_del:          # a phrase the owner added
            extra.extend((next_script, spoken[j]) for j in run_ins)
        if run_del and run_ins:                        # same place, different words: spread the spoken span
            t0, t1 = spoken[run_ins[0]].start, spoken[run_ins[-1]].end
            total = sum(len(script[i][1]) for i in run_del) or 1
            t = t0
            for i in run_del:
                d = (t1 - t0) * len(script[i][1]) / total
                times[i] = (t, t + d)
                t += d
        run_del, run_ins = [], []

    for i, j in pairs:
        if i is not None and j is not None and similarity(a[i], b[j]) >= MATCH_MIN:
            flush()
            times[i] = (spoken[j].start, spoken[j].end)
            matched += 1
            next_script = i + 1
        else:
            if i is not None:
                run_del.append(i)
                next_script = i + 1 if not run_del[:-1] else next_script
            if j is not None:
                run_ins.append(j)
    flush()
    _interpolate(times, script, duration)
    words: list[Word] = []
    part_starts: list[float | None] = [None] * len(part_texts)
    extra_at: dict[int, list[Word]] = {}
    for i, w in extra:
        extra_at.setdefault(i, []).append(w)
    for i, (k, w) in enumerate(script):
        for e in extra_at.get(i, []):
            words.append(Word(uz_latin(e.text), e.start, e.end))
        if skip[i]:
            continue
        s, e = times[i]
        if part_starts[k] is None:
            part_starts[k] = s
        words.append(Word(w, s, e))
    for e in extra_at.get(len(script), []):
        words.append(Word(uz_latin(e.text), e.start, e.end))
    words.sort(key=lambda w: w.start)
    starts = _fill_starts(part_starts, duration)
    return Alignment(words, starts, round(matched / max(1, len(a)), 3), skipped)


def _interpolate(times: list, script: list, duration: float) -> None:
    known = [i for i, t in enumerate(times) if t]
    if not known:                                 # nothing recognised: spread evenly by length
        total = sum(len(w) for _, w in script) or 1
        t = 0.0
        for i, (_, w) in enumerate(script):
            d = duration * len(w) / total
            times[i] = (t, t + d)
            t += d
        return
    i = 0
    while i < len(times):
        if times[i]:
            i += 1
            continue
        j = i
        while j < len(times) and not times[j]:
            j += 1
        t0 = times[i - 1][1] if i > 0 else 0.0
        t1 = times[j][0] if j < len(times) else duration
        total = sum(len(script[k][1]) for k in range(i, j)) or 1
        t = t0
        for k in range(i, j):
            d = max(0.05, (t1 - t0) * len(script[k][1]) / total)
            times[k] = (t, min(t + d, t1 if t1 > t else t + d))
            t += d
        i = j


def _fill_starts(starts: list, duration: float) -> list[float]:
    out = []
    for k, s in enumerate(starts):
        if s is None:
            s = out[-1] + 1.0 if out else 0.0
        out.append(max(s, out[-1] + 0.8) if out else 0.0)
    return [min(s, max(0.0, duration - 0.8 * (len(out) - k))) for k, s in enumerate(out)]


def subtitle_lines(words: list[Word], max_words: int = 4, max_chars: int = 22, hold: float = 0.25) -> list[dict]:
    """Short lines (break at punctuation), each shown until the next starts."""
    lines, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or sum(len(x.text) + 1 for x in cur) >= max_chars or re.search(r"[.!?,;:]$", w.text):
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    out = []
    for i, ln in enumerate(lines):
        nxt = lines[i + 1][0].start if i + 1 < len(lines) else ln[-1].end + hold
        out.append({"start": round(ln[0].start, 3), "end": round(max(ln[-1].end, min(nxt, ln[-1].end + hold)), 3),
                    "words": [{"w": re.sub(r"[,;:]$", "", x.text), "s": round(x.start, 3), "e": round(x.end, 3)} for x in ln]})
    return out

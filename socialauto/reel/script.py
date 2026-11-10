"""The owner's 8-part reel script and its validator.

Parts, in order: hook · lead · body1 · loop1 · body2 · loop2 · body3 · cta. 45–60 s spoken. The answer or the
strongest fact must be heard in the first 5 seconds. After every technical term a plain "ya'ni ..." explanation
follows (the "double tap"). The language is configurable (default Uzbek, `uz`).

A script dict:
    title, topic, key_fact (the number/answer that must come in the first 5 s), terms[] (technical terms used),
    parts[{part, text, broll (English search words for real footage), info {value, label} | null}],
    hashtags[], sources[{name, url}]
"""

from __future__ import annotations

import re
from typing import Any

PARTS = ("hook", "lead", "body1", "loop1", "body2", "loop2", "body3", "cta")
PART_UZ = {"hook": "Hook", "lead": "Kirish", "body1": "Asosiy 1", "loop1": "Ochiq savol 1", "body2": "Asosiy 2",
           "loop2": "Ochiq savol 2", "body3": "Asosiy 3", "cta": "Chaqiriq (CTA)"}
WORDS_PER_SECOND = 2.2          # natural Uzbek narration (words are long and agglutinative)
MIN_SECONDS, MAX_SECONDS = 45, 60
FIRST_SECONDS = 5
YANI = re.compile(r"\by(?:a|o)[ʼ'‘’`]?ni\b", re.I)        # ya'ni (also yaʼni / ya’ni / yani)

SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "required": ["title", "topic", "key_fact", "terms", "parts", "hashtags", "sources"],
    "properties": {
        "title": {"type": "string", "description": "short on-screen title (max 45 characters), in the video language"},
        "topic": {"type": "string"},
        "key_fact": {"type": "string", "description": "the strongest number or the answer, exactly as it appears in the hook"},
        "terms": {"type": "array", "items": {"type": "string"},
                  "description": "technical terms used in the text; each must be followed by a plain ya'ni explanation"},
        "parts": {"type": "array", "minItems": 8, "maxItems": 8, "items": {
            "type": "object", "additionalProperties": False, "required": ["part", "text", "broll", "info"],
            "properties": {
                "part": {"type": "string", "enum": list(PARTS)},
                "text": {"type": "string", "description": "what is said in this part"},
                "broll": {"type": "string", "description": "2-5 English words to search REAL stock footage/photos"},
                "info": {"type": ["object", "null"], "additionalProperties": False, "required": ["value", "label"],
                         "properties": {"value": {"type": "string"}, "label": {"type": "string"}}},
            }}},
        "hashtags": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8},
        "sources": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                               "required": ["name", "url"],
                                               "properties": {"name": {"type": "string"}, "url": {"type": "string"}}}},
    },
}


_window_provider = None          # Task 09: the connected content repo's own length rule (e.g. "maksimum 45 s")
_window_cache: tuple[float, tuple[int, int]] | None = None


def set_window_provider(fn) -> None:
    """fn() -> (min_s, max_s) | None. Used by every length check (script, voice, video, Telegram texts)."""
    global _window_provider, _window_cache
    _window_provider, _window_cache = fn, None


def window() -> tuple[int, int]:
    """The spoken-length window in seconds: the user's own brand rule when his content repo has one, else 45–60."""
    global _window_cache
    import time
    if _window_provider is None:
        return MIN_SECONDS, MAX_SECONDS
    if _window_cache and time.monotonic() - _window_cache[0] < 60:
        return _window_cache[1]
    try:
        got = _window_provider()
    except Exception:            # noqa: BLE001 - the default window is always safe
        got = None
    value = (int(got[0]), int(got[1])) if got else (MIN_SECONDS, MAX_SECONDS)
    _window_cache = (time.monotonic(), value)
    return value


def words(text: str) -> list[str]:
    return re.findall(r"[\wʼ'‘’`]+", text)


def full_text(script: dict) -> str:
    return " ".join(" ".join(p["text"].split()) for p in script.get("parts", []))


def estimated_seconds(script: dict, wps: float = WORDS_PER_SECOND) -> float:
    return round(len(words(full_text(script))) / wps, 1)


def _norm(t: str) -> str:
    return re.sub(r"[ʼ'‘’`]", "'", t.lower())


def problems(script: dict, wps: float = WORDS_PER_SECOND, min_s: float | None = None,
             max_s: float | None = None) -> list[str]:
    """Every rule the owner's flow sets for a script (empty list = OK)."""
    w = window()
    min_s = w[0] if min_s is None else min_s
    max_s = w[1] if max_s is None else max_s
    out = []
    parts = script.get("parts") or []
    names = [p.get("part") for p in parts]
    if tuple(names) != PARTS:
        out.append(f"the script must have exactly 8 parts in this order: {', '.join(PARTS)} (got {', '.join(map(str, names))})")
    if any(not str(p.get("text", "")).strip() for p in parts):
        out.append("a part has no text")
    secs = estimated_seconds(script, wps)
    if not (min_s <= secs <= max_s):
        out.append(f"spoken length about {secs:.0f}s; it must be {min_s}-{max_s}s "
                   f"({int(min_s * wps)}-{int(max_s * wps)} words)")
    key = str(script.get("key_fact", "")).strip()
    first = _norm(" ".join(words(full_text(script))[: int(FIRST_SECONDS * wps)]))
    if not key:
        out.append("key_fact (the answer / strongest number) is missing")
    else:
        numbers = [n.replace(",", ".") for n in re.findall(r"\d+(?:[.,]\d+)?", key)]
        first_numbers = {n.replace(",", ".") for n in re.findall(r"\d+(?:[.,]\d+)?", first)}
        heard = any(n in first_numbers for n in numbers) if numbers else _norm(" ".join(words(key)[:3])) in first
        if not heard:
            out.append(f"the strongest fact ({key}) must be heard in the first {FIRST_SECONDS} seconds "
                       f"(the first {int(FIRST_SECONDS * wps)} words)")
    text = full_text(script)
    for term in script.get("terms") or []:
        m = re.search(re.escape(_norm(term)), _norm(text))
        if not m:
            out.append(f"the term \"{term}\" is listed but not used")
            continue
        after = text[m.end(): m.end() + 140]
        if not YANI.search(after):
            out.append(f"after the term \"{term}\" a plain \"ya'ni ...\" explanation must follow")
    if len(str(script.get("title", ""))) > 45:
        out.append("the on-screen title is longer than 45 characters")
    if any(not str(p.get("broll", "")).strip() for p in parts):
        out.append("a part has no B-roll search words")
    return out


_LABELS = {
    "hook": r"hook", "lead": r"lead|kirish", "body1": r"body\s*1|asosiy\s*1", "loop1": r"(open\s*)?loop\s*1|ochiq\s*savol\s*1",
    "body2": r"body\s*2|asosiy\s*2", "loop2": r"(open\s*)?loop\s*2|ochiq\s*savol\s*2", "body3": r"body\s*3|asosiy\s*3",
    "cta": r"cta|chaqiriq",
}


def parse_pasted(text: str) -> list[str] | None:
    """The owner pasted a full edited script: 8 labelled or blank-line separated paragraphs -> 8 texts (or None)."""
    text = text.strip()
    found: dict[str, str] = {}
    pattern = "|".join(f"(?P<{k}>{v})" for k, v in _LABELS.items())
    marks = list(re.finditer(rf"^\s*(?:\d+[.)]\s*)?(?:{pattern})\s*(?:\([^)]*\))?\s*[:\-–—]\s*", text, re.I | re.M))
    if len(marks) == 8:
        for i, m in enumerate(marks):
            key = next(k for k in _LABELS if m.group(k))
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            found[key] = " ".join(text[m.end():end].split())
        if list(found) == list(PARTS):
            return [found[k] for k in PARTS]
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()]
    paras = [re.sub(r"^\d+[.)]\s*", "", p) for p in paras]
    return paras if len(paras) == 8 else None


def apply_pasted(script: dict, texts: list[str]) -> dict:
    out = dict(script)
    out["parts"] = [dict(p, text=t) for p, t in zip(script["parts"], texts)]
    return out


def as_markdown(script: dict) -> str:
    lines = [f"# {script['title']}", "", f"**Mavzu:** {script.get('topic', '')}  ", f"**Asosiy fakt:** {script.get('key_fact', '')}", ""]
    for p in script["parts"]:
        lines.append(f"## {PART_UZ.get(p['part'], p['part'])}")
        lines.append(p["text"])
        if p.get("info"):
            lines.append(f"> Infografika: **{p['info']['value']}** — {p['info']['label']}")
        lines.append("")
    if script.get("sources"):
        lines.append("## Manbalar")
        lines += [f"- [{s['name']}]({s['url']})" for s in script["sources"]]
    return "\n".join(lines) + "\n"


def as_repo_markdown(script: dict, timings: list[float] | None, caption: str, made: str) -> str:
    """script.md in the format of a connected content repo that keeps its own reels (Task 09, Javohir's repo):
    the spoken text with seconds per line, the sources (links/DOI) and the caption. `made` is the plan line."""
    lines = [f"# {script['title']}", "", made, "", "## Ovoz matni (subtitr bilan bir xil)"]
    for i, p in enumerate(script.get("parts") or []):
        secs = timings[i] if timings and i < len(timings) else len(words(p["text"])) / WORDS_PER_SECOND
        lines.append(f"{i + 1}. ({secs:.1f} s) {' '.join(p['text'].split())}")
    infos = [p["info"] for p in script.get("parts") or [] if p.get("info")]
    if infos or script.get("sources"):
        lines += ["", "## Raqamlar va manbalar"]
        lines += [f"- {x['value']} — {x['label']}" for x in infos]
        lines += [f"- {s['name']}: {s['url']}" for s in script.get("sources") or []]
    if caption:
        lines += ["", "## Caption (Buffer navbatiga yuborilgan)", caption.strip()]
    return "\n".join(lines) + "\n"

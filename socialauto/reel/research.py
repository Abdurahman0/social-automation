"""Step 1 of the owner's flow: research and topic.

- Instagram statistics from Buffer (views, shares, comments, average watch time) -> which format works;
- Claude (web search on) looks for the latest Uzbekistan water / wastewater news and world trends; every number
  carries its source;
- candidates are de-duplicated against the last 30 posts and earlier research files; anything outside water /
  wastewater is dropped;
- `research/<date>-<topic>.md` keeps 3-5 topics, strongest first, each with sources. The owner picks one in Telegram.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from .naming import slugify

SCOPE_WORDS = ("suv", "oqova", "kanaliz", "tozal", "ichimlik", "daryo", "ko'l", "kol", "nasos", "quvur", "irrigats",
               "sug'or", "sugor", "water", "wastewater", "sewage", "drought", "aral", "orol", "yer osti", "gidro",
               "hydro", "desalin", "chiqindi suv", "vodokanal", "suvoqova")
STOP = {"va", "bilan", "uchun", "bu", "u", "da", "ni", "ning", "the", "a", "of", "in", "and", "to", "on", "for", "is",
        "qanday", "nima", "nega", "yangi", "2025", "2026"}
DUP_THRESHOLD = 0.5
IDEA_DUP_THRESHOLD = 0.85        # the owner asked for this idea himself: only near-identical repeats are dropped

SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["format_insight", "topics"],
    "properties": {
        "format_insight": {"type": "string", "description": "what format works on this account, from the statistics"},
        "idea_note": {"type": "string", "description": "only when the owner gave an idea: one sentence in the video "
                      "language on how the topics relate to it (say so plainly if the idea itself is outside water and "
                      "these are the closest water angles); empty otherwise"},
        "topics": {"type": "array", "minItems": 3, "maxItems": 6, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["title", "angle", "why_now", "facts", "hook_idea"],
            "properties": {
                "title": {"type": "string", "description": "the topic in the video language, max 70 characters"},
                "angle": {"type": "string"},
                "why_now": {"type": "string"},
                "hook_idea": {"type": "string", "description": "the strongest fact/answer for the first 5 seconds"},
                "facts": {"type": "array", "minItems": 1, "items": {
                    "type": "object", "additionalProperties": False, "required": ["claim", "source", "url", "date"],
                    "properties": {"claim": {"type": "string"}, "source": {"type": "string"},
                                   "url": {"type": "string"}, "date": {"type": "string"}}}},
            }}},
    },
}


def tokens(text: str) -> set[str]:
    from .align import norm
    return {norm(w) for w in re.findall(r"[\w'ʻʼ‘’`]+", text.lower()) if norm(w) and norm(w) not in STOP and len(norm(w)) > 2}


def similarity(a: str, b: str, ignore: set[str] | None = None) -> float:
    """Word overlap. `ignore`: words of the owner's idea — every topic about the idea shares them, so they do not make
    two angles "the same topic"."""
    ta, tb = tokens(a), tokens(b)
    if ignore:
        ta, tb = (ta - ignore) or ta, (tb - ignore) or tb
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _norm_text(text: str) -> str:
    return text.lower().replace("ʻ", "'").replace("‘", "'").replace("’", "'").replace("`", "'")


def in_scope(topic: dict, wide: bool = False) -> bool:
    """Water / wastewater? `wide` (an idea from the owner) also reads the hook, «nega hozir» and the facts."""
    fields = ["title", "angle"] + (["why_now", "hook_idea"] if wide else [])
    text = " ".join(str(topic.get(f, "")) for f in fields)
    if wide:
        text += " " + " ".join(str(f.get("claim", "")) for f in topic.get("facts") or [])
    text = _norm_text(text)
    return any(w in text for w in SCOPE_WORDS)


def filter_topics(candidates: list[dict], recent_titles: list[str], recent_limit: int = 30,
                  idea: str | None = None) -> tuple[list[dict], dict[str, int]]:
    """Keep in-scope, new, sourced topics. Returns (kept, how many were dropped for each reason:
    off_niche / duplicate / no_source) so an empty result can be explained to the owner."""
    recent = recent_titles[:recent_limit] if recent_limit else recent_titles
    threshold = IDEA_DUP_THRESHOLD if idea else DUP_THRESHOLD
    ignore = tokens(idea) if idea else None
    out: list[dict] = []
    dropped = {"off_niche": 0, "duplicate": 0, "no_source": 0}
    for t in candidates:
        title = t.get("title", "")
        if not in_scope(t, wide=bool(idea)):
            dropped["off_niche"] += 1
            continue
        if any(similarity(title, r, ignore) >= threshold for r in recent) or \
                any(similarity(title, o["title"], ignore) >= DUP_THRESHOLD for o in out):
            dropped["duplicate"] += 1
            continue
        if not t.get("facts") or not all(str(f.get("url", "")).startswith("http") for f in t["facts"]):
            dropped["no_source"] += 1        # every number needs a checkable source
            continue
        out.append(t)
    return out, dropped


def dedupe(candidates: list[dict], recent_titles: list[str], recent_limit: int = 30, idea: str | None = None) -> list[dict]:
    """Drop topics similar to the last `recent_limit` posts / research topics, or to each other, or off-scope."""
    return filter_topics(candidates, recent_titles, recent_limit, idea)[0]


def why_empty(found: int, dropped: dict[str, int], idea: str | None = None) -> str:
    """Plain Uzbek: why research ended with no usable topic."""
    if not found:
        return ("Claude birorta ham mavzu qaytarmadi" + (f" («{idea}» bo'yicha)" if idea else "") +
                " — internetdan yangilik topilmagan bo'lishi mumkin")
    parts = []
    if dropped.get("off_niche"):
        parts.append(f"{dropped['off_niche']} tasi suv / oqova suv yo'nalishiga mos kelmadi")
    if dropped.get("duplicate"):
        parts.append(f"{dropped['duplicate']} tasi avvalgi videolar yoki tadqiqotlarga juda o'xshash")
    if dropped.get("no_source"):
        parts.append(f"{dropped['no_source']} tasining manbasi (tekshiriladigan havola) yo'q")
    return f"topilgan {found} ta mavzudan " + ", ".join(parts or ["hech biri ishlatib bo'lmadi"])


def earlier_research_titles(research_dir: Path, limit: int = 60) -> list[str]:
    titles = []
    if research_dir.is_dir():
        for f in sorted(research_dir.glob("*.md"), reverse=True)[:limit]:
            for line in f.read_text(encoding="utf-8").splitlines():
                m = re.match(r"^##\s+\d+\.\s+(.+)$", line)
                if m:
                    titles.append(m.group(1).strip())
    return titles


def prompt(niche: str, language: str, insight_hint: str, avoid: list[str], today: date, idea: str | None = None) -> str:
    listed = "\n".join(f"- {a}" for a in avoid[:40]) or "- (none)"
    if idea:
        head = (f"Today is {today.isoformat()}. The channel owner wants a short vertical video about THIS IDEA:\n"
                f"«{idea}»\n\nThe idea is the MAIN CONSTRAINT. Research 3-5 different topic angles ABOUT THIS IDEA for "
                f"a channel about {niche}. Search the web specifically for this idea (in Uzbek, Russian and English): "
                "the latest news, official data, plans, problems and world comparisons about it. Every topic must be "
                "clearly about the idea — not a general water topic.\n"
                "If the idea itself is outside water / wastewater, give the closest water-related angles that connect "
                "to it, and say so in idea_note. Always fill idea_note (one sentence in the video language).\n")
        rules_scope = ("- Stay within water / wastewater (drinking water, sewage, treatment, leaks, irrigation, the "
                       "Aral Sea, droughts, tariffs, plants, technology) AND within the owner's idea. Name the water "
                       "subject in each title or angle.\n")
        covered = ("Topics already covered (do not repeat them word for word; a fresh angle on the same idea is "
                   f"fine):\n{listed}\n")
    else:
        head = (f"Today is {today.isoformat()}. Research topics for a short vertical video channel about {niche}.\n"
                "Search the web for the LATEST Uzbekistan water and wastewater news (official sources, news agencies, "
                "government and utility announcements, international organisations) and relevant world trends.\n")
        rules_scope = ("- Only water / wastewater topics (drinking water, sewage, treatment, leaks, irrigation, the "
                       "Aral Sea, droughts, tariffs, new plants, technology).\n")
        covered = f"Topics already covered (do NOT repeat or closely resemble):\n{listed}\n"
    return (head + f"Account statistics (from Buffer): {insight_hint}\n"
            "Rules:\n" + rules_scope + "- Every number must be verified against a source you "
            "actually opened; give the source name, URL and date. No invented figures.\n- 3-5 topics, strongest first. "
            f"Titles and angles in the video language ({language}).\n- why_now: why this matters now (a date, a "
            "decision, a season, a new number).\n- hook_idea: the answer or the strongest number "
            "that can be said in the first 5 seconds.\n" + covered)


def write_markdown(path: Path, topics: list[dict], insight: str, stats: dict, today: date,
                   idea: str | None = None, idea_note: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Tadqiqot — {today.isoformat()}", ""]
    if idea:
        lines += [f"**G'oya:** {idea}" + (f" — {idea_note}" if idea_note else ""), ""]
    lines += [f"**Format bo'yicha xulosa:** {insight}", ""]
    if stats:
        lines.append("**Instagram statistikasi (Buffer, o'rtacha):** " +
                     ", ".join(f"{k}: {v}" for k, v in stats.items()))
        lines.append("")
    for i, t in enumerate(topics, start=1):
        lines += [f"## {i}. {t['title']}", "", f"**Burchak:** {t['angle']}  ", f"**Nega hozir:** {t['why_now']}  ",
                  f"**Hook g'oyasi:** {t['hook_idea']}", "", "**Faktlar va manbalar:**"]
        lines += [f"- {f['claim']} — [{f['source']}]({f['url']}), {f['date']}" for f in t["facts"]]
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def research_filename(publish: date, topics: list[dict]) -> str:
    return f"{publish.isoformat()}-{slugify(topics[0]['title']) if topics else 'tadqiqot'}"


def parse_markdown(text: str) -> dict:
    """A research file -> {"insight", "topics": [{"title", "angle", "why_now", "hook", "facts": [{claim, source, url}]}]}
    (the website renders it with sources as names)."""
    out: dict = {"insight": "", "stats": "", "idea": "", "topics": []}
    cur = None
    for line in text.splitlines():
        if line.startswith("**G'oya:**"):
            out["idea"] = line.split("**", 2)[2].strip()
        if line.startswith("**Format bo'yicha xulosa:**"):
            out["insight"] = line.split("**", 2)[2].strip()
        elif line.startswith("**Instagram statistikasi"):
            out["stats"] = line.split("**", 2)[2].strip()
        m = re.match(r"^##\s+\d+\.\s+(.+)$", line)
        if m:
            cur = {"title": m.group(1).strip(), "angle": "", "why_now": "", "hook": "", "facts": []}
            out["topics"].append(cur)
            continue
        if cur is None:
            continue
        for key, label in (("angle", "Burchak"), ("why_now", "Nega hozir"), ("hook", "Hook g'oyasi")):
            if line.startswith(f"**{label}:**"):
                cur[key] = line.split("**", 2)[2].strip()
        fm = re.match(r"^- (.+?) — \[(.+?)\]\((.+?)\)(?:, (.*))?$", line)
        if fm:
            cur["facts"].append({"claim": fm.group(1), "source": fm.group(2), "url": fm.group(3), "date": fm.group(4) or ""})
    return out

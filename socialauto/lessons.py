"""The bot's lessons (law 11): every mistake and what fixed it, so it is never repeated (copied from ytauto).

When a step fails (an idea or script check, the voice check, the render's quality gate, an upload error, a video the
owner rejected or edited) the problem is recorded here: the stage, the concrete text and, once a retry passes, what
fixed it. The same mistake again only raises its counter (numbers are ignored when comparing). Before generating,
the Claude prompts get a short "Mistakes you made before - do NOT repeat" list for their stage. Voice problems
(too quiet, noise, cut words) become short tips in the next recording request. The owner reads them with /lessons;
a readable copy is kept in data/lessons.md. Lessons are never pushed to Telegram.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .db import Database

log = logging.getLogger(__name__)

STAGES = ("idea", "script", "voice", "render", "quality", "upload", "owner")
PROMPT_LIMIT = 6                 # lessons per prompt (short prompts save Claude budget)
PROMPT_CHARS = 1000              # and at most this much text
KEEP_PER_STAGE = 200             # rows kept per stage (the rare one-off ones go first)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


STAGE_UZ = {"idea": "G'oya", "script": "Ssenariy", "voice": "Ovoz", "render": "Video", "quality": "Sifat tekshiruvi",
            "upload": "Joylash", "owner": "Egasining izohlari"}

# Voice problems are recorded as "<code>: <details>"; each code has one short tip for the next recording request.
VOICE_TIPS = {
    "quiet": "Oldingi yozuv juda past edi — telefonni og'izdan 15–20 sm masofada tuting.",
    "clipping": "Oldingi yozuvda ovoz \"yorilib\" ketgan edi — biroz pastroq ovozda yoki uzoqroqdan gapiring.",
    "noise": "Oldingi yozuvda shovqin ko'p edi — eshik-derazasi yopiq, jim xonada yozing.",
    "missing": "Oldingi yozuvda matnning bir qismi tushib qolgan edi — matnni oxirigacha o'qing.",
    "too_long": "Oldingi yozuv juda uzun edi — biroz tezroq va pauzalarsiz o'qing.",
    "too_short": "Oldingi yozuv juda qisqa edi — shoshilmasdan, tabiiy tezlikda o'qing.",
}


def signature(text: str) -> str:
    """What makes two problems "the same mistake": lower case, numbers and quoted bits ignored."""
    t = (text or "").lower()
    t = re.sub(r"\d+(?:[.,:]\d+)*", "#", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:160]


class Lessons:
    def __init__(self, db: Database, mirror: Path | None = None):
        self.db = db
        self.mirror = mirror

    # --- writing ---------------------------------------------------------------------------------------------

    def record(self, stage: str, problems: Iterable[str], fix: str = "") -> list[int]:
        """Note each problem (deduplicated); returns their ids. `fix` is set at once for problems the bot
        repairs by itself."""
        ids = []
        now = now_iso()
        with self.db.tx() as conn:
            for text in problems:
                text = " ".join(str(text).split())[:400]
                if not text:
                    continue
                key = signature(text)
                row = conn.execute("SELECT id FROM lessons WHERE stage=? AND key=?", (stage, key)).fetchone()
                if row:
                    conn.execute("""UPDATE lessons SET count=count+1, last_seen=?, text=?,
                                    fix=CASE WHEN ?<>'' THEN ? ELSE fix END WHERE id=?""",
                                 (now, text, fix, fix, row["id"]))
                    ids.append(row["id"])
                else:
                    cur = conn.execute("""INSERT INTO lessons(stage, key, text, fix, count, first_seen, last_seen,
                                          fixed_at) VALUES (?, ?, ?, ?, 1, ?, ?, ?)""",
                                       (stage, key, text, fix, now, now, now if fix else None))
                    ids.append(cur.lastrowid)
            conn.execute(f"""DELETE FROM lessons WHERE stage=? AND id NOT IN (
                             SELECT id FROM lessons WHERE stage=? ORDER BY count DESC, last_seen DESC
                             LIMIT {KEEP_PER_STAGE})""", (stage, stage))
        self._write_mirror()
        return ids

    def fixed(self, ids: Iterable[int], how: str) -> None:
        """A retry passed: say what fixed these problems."""
        ids = list(ids)
        if not ids:
            return
        with self.db.tx() as conn:
            conn.executemany("UPDATE lessons SET fix=?, fixed_at=? WHERE id=?",
                             [(how[:300], now_iso(), i) for i in ids])
        self._write_mirror()

    def fix_open(self, stage: str, how: str) -> None:
        """A retry passed: every open lesson of this stage gets what fixed it."""
        with self.db.tx() as conn:
            conn.execute("UPDATE lessons SET fix=?, fixed_at=? WHERE stage=? AND fixed_at IS NULL",
                         (how[:300], now_iso(), stage))
        self._write_mirror()

    # --- reading ---------------------------------------------------------------------------------------------

    def top(self, stages: Iterable[str], limit: int = PROMPT_LIMIT) -> list[dict[str, Any]]:
        stages = tuple(stages)
        if not stages:
            return []
        rows = self.db.query(
            f"SELECT * FROM lessons WHERE stage IN ({','.join('?' * len(stages))}) "
            "ORDER BY stage='owner' DESC, count DESC, last_seen DESC LIMIT ?", (*stages, limit))   # owner's first
        return [dict(r) for r in rows]

    def all(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.query("SELECT * FROM lessons ORDER BY stage, count DESC, last_seen DESC")]

    def prompt_block(self, stages: Iterable[str], limit: int = PROMPT_LIMIT, chars: int = PROMPT_CHARS) -> str:
        items = self.top(stages, limit)
        if not items:
            return ""
        lines, used = [], 0
        for it in items:
            line = f"- {it['text']}" + (f" (seen {it['count']}x)" if it["count"] > 1 else "") + \
                   (f" -> what worked: {it['fix']}" if it["fix"] else "")
            if used + len(line) > chars:
                break
            lines.append(line)
            used += len(line)
        return ("\n\nMistakes made before on this channel - do NOT repeat them (they cost a redraft or a "
                "re-render):\n" + "\n".join(lines) + "\n")

    def voice_tips(self, limit: int = 3) -> list[str]:
        """Short Uzbek recording tips from past voice problems (newest/most frequent first)."""
        tips = []
        for row in self.top(("voice",), limit=10):
            tip = VOICE_TIPS.get(row["key"].split(":", 1)[0])
            if tip and tip not in tips:
                tips.append(tip)
        return tips[:limit]

    def text(self, limit: int = 30) -> str:
        """Plain text for /lessons and the lessons.md copy."""
        rows = self.all()
        if not rows:
            return "No lessons yet."
        out = []
        for stage in STAGES:
            items = [r for r in rows if r["stage"] == stage][:limit]
            if not items:
                continue
            out.append(f"[{STAGE_UZ.get(stage, stage)}]")
            for r in items:
                out.append(f"• {r['text']} — {r['count']} marta, oxirgisi {r['last_seen'][:10]}"
                           + (f"\n  yechim: {r['fix']}" if r["fix"] else ""))
        return "\n".join(out)

    def _write_mirror(self) -> None:
        if not self.mirror:
            return
        try:
            self.mirror.parent.mkdir(parents=True, exist_ok=True)
            self.mirror.write_text("# Lessons (mistakes the bot made, and what fixed them)\n\n" + self.text(200) + "\n",
                                   encoding="utf-8")
        except OSError as exc:
            log.debug("lessons.md not written: %s", exc)


def safe_record(lessons: "Lessons | None", stage: str, problems: Iterable[str], fix: str = "") -> list[int]:
    """Record problems; never lets a lessons error break the real work."""
    if lessons is None:
        return []
    try:
        return lessons.record(stage, problems, fix)
    except Exception as exc:       # noqa: BLE001 - lessons are a side record
        log.warning("Could not record lessons: %s", exc)
        return []


def safe_fixed(lessons: "Lessons | None", ids: Iterable[int], how: str) -> None:
    if lessons is None:
        return
    try:
        lessons.fixed(ids, how)
    except Exception as exc:       # noqa: BLE001
        log.warning("Could not record a lesson's fix: %s", exc)


# --- prompts get the relevant lessons ---------------------------------------------------------------------------

def stages_for_task(task: str) -> tuple[str, ...]:
    """Which lessons a Claude call should see, from its task name."""
    t = task.lower()
    if any(w in t for w in ("idea", "propos", "regenerat")):
        return ("idea", "script", "owner")
    return ("script", "quality", "owner")


class LessonsClaude:
    """Wraps the Claude client: each prompt gets its stage's lessons appended (never the JSON schema)."""

    def __init__(self, inner, lessons: Lessons):
        self.inner = inner
        self.lessons = lessons

    _OWN = ("inner", "lessons")

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def __setattr__(self, name, value):        # anything else belongs to the wrapped client
        if name in self._OWN:
            object.__setattr__(self, name, value)
        else:
            setattr(self.inner, name, value)

    def _prompt(self, task: str, prompt: str) -> str:
        try:
            block = self.lessons.prompt_block(stages_for_task(task))
        except Exception as exc:   # noqa: BLE001
            log.warning("Lessons not added to %s: %s", task, exc)
            block = ""
        return prompt + block

    def generate_json(self, task, prompt, schema, system_prompt, *args, **kwargs):
        return self.inner.generate_json(task, self._prompt(task, prompt), schema, system_prompt, *args, **kwargs)

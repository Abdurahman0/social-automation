"""Pipeline records: videos, script versions, voices, renders and approvals (versioned buttons)."""

from __future__ import annotations

import json
import secrets
from datetime import datetime
from typing import Any, Iterable

from .db import Database, iso, now_iso, parse_iso

# --- video statuses -----------------------------------------------------------------------------------------------
DRAFTING = "drafting"                 # Claude is writing the idea + script
SCRIPT_PENDING = "script_pending"     # Approval 1 sent
REVISING = "revising"                 # Claude rewrites after Edit / Regenerate
VOICE_WAITING = "voice_waiting"       # "Ovoz kutilmoqda": the owner records the narration
VOICE_PROCESSING = "voice_processing"
VOICE_CHECK = "voice_check"           # the recording differs a lot from the script: the owner decides
RENDERING = "rendering"
VIDEO_PENDING = "video_pending"       # the owner watches the reel
DONE = "done"                         # the owner scheduled it in Buffer and published the story
REJECTED = "rejected"
FAILED = "failed"
# Task 04 (the owner's reel flow)
RESEARCHING = "researching"           # Bot: Buffer stats + news research
TOPIC_PENDING = "topic_pending"       # Siz: pick a topic
COVER_WAITING = "cover_waiting"       # Siz: send the cover
PUBLISHING = "publishing"             # Bot: git reels/ + Buffer drafts
BUFFER_PENDING = "buffer_pending"     # Bot: in Buffer's queue, Buffer posts it at its own time (bot watches for "live")
STORY_PENDING = "story_pending"       # Siz: publish the story

ACTIVE = (RESEARCHING, TOPIC_PENDING, DRAFTING, SCRIPT_PENDING, REVISING, VOICE_WAITING, VOICE_PROCESSING, VOICE_CHECK,
          RENDERING, VIDEO_PENDING, COVER_WAITING, PUBLISHING, BUFFER_PENDING, STORY_PENDING)
WAITS_FOR_VOICE = (VOICE_WAITING, VOICE_CHECK)
ACCEPTS_NEW_VOICE = (VOICE_WAITING, VOICE_CHECK, VOICE_PROCESSING, RENDERING, VIDEO_PENDING)   # newest voice wins
TERMINAL = (DONE, REJECTED, FAILED)

STATUS_UZ = {
    DRAFTING: "Ssenariy yozilmoqda", SCRIPT_PENDING: "Ssenariy tasdig'i kutilmoqda", REVISING: "Qayta yozilmoqda",
    VOICE_WAITING: "Ovoz kutilmoqda", VOICE_PROCESSING: "Ovoz ishlanmoqda", VOICE_CHECK: "Ovoz bo'yicha qaror kutilmoqda",
    RENDERING: "Video tayyorlanmoqda", VIDEO_PENDING: "Videoni ko'rib chiqish kutilmoqda",
    DONE: "Tugadi", REJECTED: "Rad etildi", FAILED: "To'xtab qoldi",
    RESEARCHING: "Tadqiqot qilinmoqda", TOPIC_PENDING: "Mavzu tanlash kutilmoqda", COVER_WAITING: "Muqova kutilmoqda",
    PUBLISHING: "Buffer'ga yuborilmoqda", BUFFER_PENDING: "Buffer navbatida — o'z vaqtida chiqadi",
    STORY_PENDING: "Story qoralamasi tayyor — joylash sizda",
}


class ApprovalError(Exception):
    """A button that is outdated or already used."""


def _loads(row: dict[str, Any] | None, *fields: str) -> dict[str, Any] | None:
    if row is None:
        return None
    for f in fields:
        key = f[:-5] if f.endswith("_json") else f
        row[key] = json.loads(row.pop(f) or "null")
    return row


class Store:
    def __init__(self, db: Database):
        self.db = db

    # --- videos ---------------------------------------------------------------------------------------------
    def create_video(self, status: str, topic: str = "", origin: str = "claude", slot_at: datetime | None = None) -> int:
        now = now_iso()
        return self.db.execute("""INSERT INTO videos(topic, origin, status, slot_at, created_at, updated_at)
                                  VALUES (?, ?, ?, ?, ?, ?)""",
                               (topic, origin, status, iso(slot_at) if slot_at else None, now, now))

    def video(self, video_id: int) -> dict[str, Any] | None:
        return self.db.one("SELECT * FROM videos WHERE id=?", (video_id,))

    def videos(self, statuses: Iterable[str] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if statuses:
            st = tuple(statuses)
            return [dict(r) for r in self.db.query(
                f"SELECT * FROM videos WHERE status IN ({','.join('?' * len(st))}) ORDER BY id DESC LIMIT ?",
                (*st, limit))]
        return [dict(r) for r in self.db.query("SELECT * FROM videos ORDER BY id DESC LIMIT ?", (limit,))]

    def update_video(self, video_id: int, **fields: Any) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        vals = [iso(v) if isinstance(v, datetime) else v for v in fields.values()]
        self.db.execute(f"UPDATE videos SET {cols}, updated_at=? WHERE id=?", (*vals, now_iso(), video_id))

    def set_status(self, video_id: int, status: str, expected: Iterable[str] | None = None, **fields: Any) -> bool:
        """Atomic status change; with `expected`, only from one of those statuses."""
        fields["status"] = status
        cols = ", ".join(f"{k}=?" for k in fields)
        vals = [iso(v) if isinstance(v, datetime) else v for v in fields.values()]
        sql = f"UPDATE videos SET {cols}, updated_at=? WHERE id=?"
        args: tuple = (*vals, now_iso(), video_id)
        if expected:
            exp = tuple(expected)
            sql += f" AND status IN ({','.join('?' * len(exp))})"
            args += exp
        return self.db.execute(sql, args) > 0

    def taken_slots(self) -> set[datetime]:
        rows = self.db.query("SELECT slot_at FROM videos WHERE slot_at IS NOT NULL AND status NOT IN (?, ?)",
                             (REJECTED, FAILED))
        return {parse_iso(r["slot_at"]) for r in rows}

    def recent_topics(self, limit: int = 40) -> list[str]:
        return [r["topic"] for r in self.db.query(
            "SELECT topic FROM videos WHERE topic<>'' ORDER BY id DESC LIMIT ?", (limit,))]

    # --- scripts --------------------------------------------------------------------------------------------
    def add_script(self, video_id: int, script: dict[str, Any], feedback: str | None = None) -> int:
        with self.db.tx() as conn:
            row = conn.execute("SELECT COALESCE(MAX(version), 0) v FROM scripts WHERE video_id=?", (video_id,)).fetchone()
            version = row["v"] + 1
            conn.execute("INSERT INTO scripts(video_id, version, script_json, feedback, created_at) VALUES (?,?,?,?,?)",
                         (video_id, version, json.dumps(script, ensure_ascii=False), feedback, now_iso()))
            conn.execute("UPDATE videos SET script_version=?, title=?, topic=?, updated_at=? WHERE id=?",
                         (version, script.get("title", ""), script.get("topic", ""), now_iso(), video_id))
        return version

    def script(self, video_id: int, version: int | None = None) -> dict[str, Any] | None:
        if version is None:
            v = self.video(video_id)
            version = v["script_version"] if v else 0
        row = self.db.one("SELECT script_json FROM scripts WHERE video_id=? AND version=?", (video_id, version))
        return json.loads(row["script_json"]) if row else None

    # --- voices ---------------------------------------------------------------------------------------------
    def add_voice(self, video_id: int | None, source_kind: str, raw_path: str, status: str = "received") -> int:
        now = now_iso()
        return self.db.execute("""INSERT INTO voices(video_id, status, source_kind, raw_path, created_at, updated_at)
                                  VALUES (?, ?, ?, ?, ?, ?)""", (video_id, status, source_kind, raw_path, now, now))

    def voice(self, voice_id: int) -> dict[str, Any] | None:
        return _loads(self.db.one("SELECT * FROM voices WHERE id=?", (voice_id,)), "words_json", "problems_json", "levels_json")

    def update_voice(self, voice_id: int, **fields: Any) -> None:
        for k in ("words", "problems", "levels"):
            if k in fields:
                fields[f"{k}_json"] = json.dumps(fields.pop(k), ensure_ascii=False)
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE voices SET {cols}, updated_at=? WHERE id=?", (*fields.values(), now_iso(), voice_id))

    def latest_voice_id(self, video_id: int) -> int | None:
        row = self.db.one("SELECT MAX(id) id FROM voices WHERE video_id=? AND status<>'unassigned'", (video_id,))
        return row["id"] if row else None

    def supersede_voices(self, video_id: int, keep: int) -> None:
        self.db.execute("""UPDATE voices SET status='superseded', updated_at=? WHERE video_id=? AND id<>?
                           AND status NOT IN ('superseded', 'failed')""", (now_iso(), video_id, keep))

    # --- renders --------------------------------------------------------------------------------------------
    def add_render(self, video_id: int, script_version: int, voice_id: int | None) -> tuple[int, int]:
        with self.db.tx() as conn:
            row = conn.execute("SELECT COALESCE(MAX(version), 0) v FROM renders WHERE video_id=?", (video_id,)).fetchone()
            version = row["v"] + 1
            now = now_iso()
            cur = conn.execute("""INSERT INTO renders(video_id, version, script_version, voice_id, status, created_at,
                                  updated_at) VALUES (?, ?, ?, ?, 'rendering', ?, ?)""",
                               (video_id, version, script_version, voice_id, now, now))
        return cur.lastrowid, version

    def render(self, render_id: int) -> dict[str, Any] | None:
        return _loads(self.db.one("SELECT * FROM renders WHERE id=?", (render_id,)), "hashtags_json", "report_json")

    def update_render(self, render_id: int, **fields: Any) -> None:
        for k in ("hashtags", "report"):
            if k in fields:
                fields[f"{k}_json"] = json.dumps(fields.pop(k), ensure_ascii=False)
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE renders SET {cols}, updated_at=? WHERE id=?", (*fields.values(), now_iso(), render_id))

    # --- approvals (versioned buttons) ----------------------------------------------------------------------
    def open_approval(self, video_id: int, stage: str, ref_version: int, dry_run: bool) -> str:
        """A new approval for this video and stage; any older pending one of the same stage stops working."""
        token = secrets.token_hex(5)
        with self.db.tx() as conn:
            conn.execute("""UPDATE approvals SET status='superseded', decided_at=? WHERE video_id=? AND stage=?
                            AND status='pending'""", (now_iso(), video_id, stage))
            conn.execute("""INSERT INTO approvals(id, video_id, stage, ref_version, status, dry_run, created_at)
                            VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
                         (token, video_id, stage, ref_version, int(dry_run), now_iso()))
        return token

    def approval(self, token: str) -> dict[str, Any] | None:
        return self.db.one("SELECT * FROM approvals WHERE id=?", (token,))

    def pending_approval(self, video_id: int, stage: str) -> dict[str, Any] | None:
        return self.db.one("SELECT * FROM approvals WHERE video_id=? AND stage=? AND status='pending'", (video_id, stage))

    def pending_approvals(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.query("SELECT * FROM approvals WHERE status='pending' ORDER BY created_at")]

    def decide(self, token: str, decision: str) -> dict[str, Any]:
        """Use a button once. Raises ApprovalError for an unknown, outdated or already-used button."""
        with self.db.tx() as conn:
            row = conn.execute("SELECT * FROM approvals WHERE id=?", (token,)).fetchone()
            if not row:
                raise ApprovalError("Bu tugma endi ishlamaydi.")
            if row["status"] == "superseded":
                raise ApprovalError("Bu eski versiya tugmasi — eng so'nggi xabardagi tugmalardan foydalaning.")
            if row["status"] != "pending":
                raise ApprovalError("Bu tugma allaqachon bosilgan.")
            conn.execute("UPDATE approvals SET status=?, decided_at=? WHERE id=? AND status='pending'",
                         (decision, now_iso(), token))
        out = dict(row)
        out["status"] = decision
        return out

    def supersede_approvals(self, video_id: int, stages: Iterable[str] | None = None) -> None:
        sql = "UPDATE approvals SET status='superseded', decided_at=? WHERE video_id=? AND status='pending'"
        args: tuple = (now_iso(), video_id)
        if stages:
            st = tuple(stages)
            sql += f" AND stage IN ({','.join('?' * len(st))})"
            args += st
        self.db.execute(sql, args)

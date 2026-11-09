"""The six stages of the owner's reel flow and the per-reel record (the reels table)."""

from __future__ import annotations

import json
from typing import Any

from ..db import now_iso
from ..store import (BUFFER_PENDING, COVER_WAITING, DONE, DRAFTING, PUBLISHING, RENDERING, RESEARCHING, REVISING,
                     SCRIPT_PENDING, STORY_PENDING, TOPIC_PENDING, VIDEO_PENDING, VOICE_CHECK, VOICE_PROCESSING,
                     VOICE_WAITING)

STAGES = [
    ("research", "Tadqiqot va mavzu"), ("script", "Ssenariy va ovoz"), ("broll", "B-roll va dizayn"),
    ("edit", "Ovoz va montaj"), ("publish", "Tasdiq va Buffer"), ("live", "Efirdan keyin"),
]
# status -> (stage key, who acts now: "Siz" = the owner, "Bot" = the bot)
STATUS_STAGE = {
    RESEARCHING: ("research", "Bot"), TOPIC_PENDING: ("research", "Siz"),
    DRAFTING: ("script", "Bot"), REVISING: ("script", "Bot"), SCRIPT_PENDING: ("script", "Siz"),
    VOICE_WAITING: ("script", "Siz"), VOICE_CHECK: ("script", "Siz"), VOICE_PROCESSING: ("edit", "Bot"),
    RENDERING: ("edit", "Bot"), VIDEO_PENDING: ("edit", "Siz"),
    COVER_WAITING: ("publish", "Siz"), PUBLISHING: ("publish", "Bot"), BUFFER_PENDING: ("publish", "Bot"),
    STORY_PENDING: ("live", "Siz"), DONE: ("live", "Bot"),
}


class Reels:
    """The reels table (one row per video of this flow)."""

    def __init__(self, db):
        self.db = db

    def get(self, video_id: int) -> dict[str, Any] | None:
        row = self.db.one("SELECT * FROM reels WHERE video_id=?", (video_id,))
        if row:
            for k in ("topics_json", "captions_json", "drafts_json", "fix_notes_json", "checklist_json", "live_links_json",
                      "buffer_json"):
                row[k[:-5]] = json.loads(row.pop(k) or "null")
        return row

    def upsert(self, video_id: int, **fields: Any) -> None:
        for k in ("topics", "captions", "drafts", "fix_notes", "checklist", "live_links", "buffer"):
            if k in fields:
                fields[f"{k}_json"] = json.dumps(fields.pop(k), ensure_ascii=False)
        if not self.db.one("SELECT 1 FROM reels WHERE video_id=?", (video_id,)):
            self.db.execute("INSERT INTO reels(video_id, base, updated_at) VALUES (?, ?, ?)",
                            (video_id, fields.pop("base", "reel"), now_iso()))
        if fields:
            cols = ", ".join(f"{k}=?" for k in fields)
            self.db.execute(f"UPDATE reels SET {cols}, updated_at=? WHERE video_id=?", (*fields.values(), now_iso(), video_id))

    def all(self) -> list[dict]:
        return [self.get(r["video_id"]) for r in self.db.query("SELECT video_id FROM reels ORDER BY video_id DESC")]



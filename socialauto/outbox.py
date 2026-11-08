"""Durable outgoing notifications. The workflow writes here; the Telegram layer delivers.

Messages are kept until delivered, so nothing is lost while Telegram or the network is down.
"""

import json
from dataclasses import dataclass
from typing import Any

from .db import Database, now_iso

MAX_DELIVERY_ATTEMPTS = 50


@dataclass(frozen=True)
class OutboxItem:
    id: int
    kind: str
    payload: dict[str, Any]


class Outbox:
    def __init__(self, db: Database):
        self.db = db

    def add(self, kind: str, **payload: Any) -> None:
        with self.db.tx() as conn:
            conn.execute(
                "INSERT INTO outbox(kind, payload_json, created_at) VALUES (?, ?, ?)",
                (kind, json.dumps(payload), now_iso()),
            )

    def pending(self, limit: int = 20) -> list[OutboxItem]:
        rows = self.db.query(
            "SELECT id, kind, payload_json FROM outbox WHERE status='pending' ORDER BY id LIMIT ?", (limit,))
        return [OutboxItem(r["id"], r["kind"], json.loads(r["payload_json"])) for r in rows]

    def mark_sent(self, item_id: int) -> None:
        with self.db.tx() as conn:
            conn.execute("UPDATE outbox SET status='sent', sent_at=? WHERE id=?", (now_iso(), item_id))

    def mark_silenced(self, item_id: int) -> None:
        """Not for the owner (quiet Telegram): kept in the table for the record, never sent."""
        with self.db.tx() as conn:
            conn.execute("UPDATE outbox SET status='silenced', sent_at=? WHERE id=?", (now_iso(), item_id))

    def mark_attempt(self, item_id: int) -> None:
        with self.db.tx() as conn:
            conn.execute(
                """UPDATE outbox SET attempts=attempts+1,
                   status=CASE WHEN attempts+1>=? THEN 'dead' ELSE status END WHERE id=?""",
                (MAX_DELIVERY_ATTEMPTS, item_id),
            )

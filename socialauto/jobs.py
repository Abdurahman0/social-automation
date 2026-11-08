"""Persistent job queue. Jobs survive restarts; interrupted jobs are re-queued on startup."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .db import Database, iso, now_iso, utcnow

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    id: int
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


class JobQueue:
    def __init__(self, db: Database, clock=utcnow):
        self.db = db
        self.clock = clock

    def _now(self) -> str:
        return iso(self.clock())

    def enqueue(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        dedupe_key: str | None = None,
        run_after: datetime | None = None,
        max_attempts: int = 5,
    ) -> int | None:
        """Queue a job. Returns None if an identical job (same dedupe_key) is already pending or running."""
        now = self._now()
        with self.db.tx() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO jobs
                   (kind, payload_json, dedupe_key, max_attempts, run_after, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (kind, json.dumps(payload or {}), dedupe_key, max_attempts,
                 iso(run_after) if run_after else now, now, now),
            )
            return cur.lastrowid if cur.rowcount else None

    def cancel_for_video(self, video_id: int, reason: str, kinds: tuple[str, ...] = ()) -> list[int]:
        """Cancel pending jobs about this video (optionally only these kinds). A running one finishes; its
        handler checks the video's status."""
        with self.db.tx() as conn:
            rows = conn.execute("SELECT id, kind, payload_json FROM jobs WHERE status='pending'").fetchall()
            ids = [r["id"] for r in rows if json.loads(r["payload_json"] or "{}").get("video_id") == video_id
                   and (not kinds or r["kind"] in kinds)]
            conn.executemany("UPDATE jobs SET status='cancelled', last_error=?, updated_at=? WHERE id=?",
                             [(reason[:300], now_iso(), i) for i in ids])
        return ids

    def claim_next(self, exclude: tuple[str, ...] = (), now: str | None = None) -> Job | None:
        """Oldest due job, skipping `exclude` kinds (e.g. Claude jobs while the usage limit is hit)."""
        now = now or self._now()
        skip = f" AND kind NOT IN ({','.join('?' * len(exclude))})" if exclude else ""
        with self.db.tx() as conn:
            row = conn.execute(
                f"""SELECT * FROM jobs WHERE status='pending' AND run_after<=?{skip}
                   ORDER BY run_after, id LIMIT 1""",
                (now, *exclude),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE jobs SET status='running', attempts=attempts+1, updated_at=? WHERE id=?",
                (now, row["id"]),
            )
        return Job(row["id"], row["kind"], json.loads(row["payload_json"]),
                   row["attempts"] + 1, row["max_attempts"])

    def reschedule(self, dedupe_key: str, run_after: datetime) -> bool:
        """Move a pending job (found by its dedupe key) to another time."""
        with self.db.tx() as conn:
            cur = conn.execute("UPDATE jobs SET run_after=?, updated_at=? WHERE dedupe_key=? AND status='pending'",
                               (iso(run_after), now_iso(), dedupe_key))
            return cur.rowcount > 0

    def complete(self, job_id: int) -> None:
        self._set(job_id, "done", None)

    def retry_later(self, job: Job, error: str, delay_seconds: int) -> bool:
        """Re-queue after a failure. Returns False (and marks the job failed) once attempts are used up."""
        if job.attempts >= job.max_attempts:
            self._set(job.id, "failed", error)
            return False
        with self.db.tx() as conn:
            conn.execute(
                "UPDATE jobs SET status='pending', run_after=?, last_error=?, updated_at=? WHERE id=?",
                (iso(self.clock() + timedelta(seconds=delay_seconds)), error[:2000], self._now(), job.id),
            )
        return True

    def postpone(self, job: Job, until: datetime, reason: str) -> None:
        """Re-queue without consuming an attempt (usage limit, auth missing, ...)."""
        with self.db.tx() as conn:
            conn.execute(
                """UPDATE jobs SET status='pending', attempts=MAX(attempts-1, 0), run_after=?,
                   last_error=?, updated_at=? WHERE id=?""",
                (iso(until), reason[:2000], now_iso(), job.id),
            )

    def recover_running(self) -> int:
        """Jobs left 'running' by a crash or restart go back to the queue."""
        with self.db.tx() as conn:
            cur = conn.execute(
                """UPDATE jobs SET status='pending', attempts=MAX(attempts-1, 0), updated_at=?
                   WHERE status='running'""",
                (now_iso(),),
            )
            return cur.rowcount

    def active(self, kinds: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM jobs WHERE status IN ('pending','running')"
        params: tuple = ()
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            params = kinds
        return [dict(r) for r in self.db.query(sql + " ORDER BY run_after, id", params)]

    def recent_errors(self, limit: int = 5) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.query(
            """SELECT id, kind, status, last_error, updated_at FROM jobs WHERE last_error IS NOT NULL
               ORDER BY updated_at DESC, id DESC LIMIT ?""", (limit,))]

    def has_active(self, kind: str) -> bool:
        return bool(self.db.query(
            "SELECT 1 FROM jobs WHERE kind=? AND status IN ('pending','running') LIMIT 1", (kind,)))

    def counts(self) -> dict[str, int]:
        return {r["status"]: r["n"] for r in self.db.query(
            "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")}

    def _set(self, job_id: int, status: str, error: str | None) -> None:
        with self.db.tx() as conn:
            conn.execute(
                "UPDATE jobs SET status=?, last_error=COALESCE(?, last_error), updated_at=? WHERE id=?",
                (status, error[:2000] if error else None, now_iso(), job_id),
            )

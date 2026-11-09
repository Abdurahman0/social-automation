"""SQLite storage: connection handling, schema migrations and a small key-value store."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

MIGRATIONS: list[list[str]] = [
    [
        # --- pipeline ------------------------------------------------------------------------------------
        """CREATE TABLE videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            topic TEXT NOT NULL DEFAULT '',
            origin TEXT NOT NULL DEFAULT 'claude',          -- claude | voice (made from an unsolicited voice)
            status TEXT NOT NULL,
            script_version INTEGER NOT NULL DEFAULT 0,
            voice_id INTEGER,
            render_id INTEGER,
            slot_at TEXT,
            reminded_at TEXT,
            final_approved_at TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE scripts (
            video_id INTEGER NOT NULL REFERENCES videos(id),
            version INTEGER NOT NULL,
            script_json TEXT NOT NULL,
            feedback TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (video_id, version)
        )""",
        """CREATE TABLE voices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER REFERENCES videos(id),
            status TEXT NOT NULL,                           -- received | processing | accepted | mismatch |
                                                            -- superseded | unassigned | failed
            source_kind TEXT NOT NULL,                      -- voice | audio | document | video_note | video
            raw_path TEXT NOT NULL,
            clean_path TEXT,
            duration REAL,
            transcript TEXT,
            words_json TEXT NOT NULL DEFAULT '[]',
            coverage REAL,
            problems_json TEXT NOT NULL DEFAULT '[]',
            levels_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE renders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL REFERENCES videos(id),
            version INTEGER NOT NULL,
            script_version INTEGER NOT NULL,
            voice_id INTEGER REFERENCES voices(id),
            status TEXT NOT NULL,                           -- rendering | ready | failed | superseded
            video_path TEXT,
            preview_path TEXT,
            duration REAL,
            title TEXT,
            caption TEXT,
            hashtags_json TEXT NOT NULL DEFAULT '[]',
            report_json TEXT NOT NULL DEFAULT '{}',
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (video_id, version)
        )""",
        """CREATE TABLE approvals (
            id TEXT PRIMARY KEY,                            -- random token carried by the Telegram buttons
            video_id INTEGER NOT NULL REFERENCES videos(id),
            stage TEXT NOT NULL,                            -- script | video | voice_check
            ref_version INTEGER NOT NULL,                   -- script version, render id or voice id
            status TEXT NOT NULL,                           -- pending | approved | rejected | regenerate | edit |
                                                            -- superseded
            dry_run INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            decided_at TEXT
        )""",
        """CREATE UNIQUE INDEX approvals_one_open ON approvals(video_id, stage) WHERE status='pending'""",
        # --- infrastructure (copied from ytauto) --------------------------------------------------------------
        """CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            dedupe_key TEXT,
            run_after TEXT NOT NULL,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE UNIQUE INDEX jobs_active_dedupe ON jobs(dedupe_key)
           WHERE dedupe_key IS NOT NULL AND status IN ('pending', 'running')""",
        "CREATE INDEX jobs_due ON jobs(status, run_after)",
        """CREATE TABLE outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            sent_at TEXT
        )""",
        """CREATE TABLE kv (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stage TEXT NOT NULL,
            key TEXT NOT NULL,
            text TEXT NOT NULL,
            fix TEXT NOT NULL DEFAULT '',
            count INTEGER NOT NULL DEFAULT 1,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            fixed_at TEXT,
            UNIQUE (stage, key)
        )""",
        """CREATE TABLE claude_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TEXT NOT NULL,
            task TEXT NOT NULL,
            seconds REAL NOT NULL,
            turns INTEGER NOT NULL DEFAULT 0,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cache_read_tokens INTEGER NOT NULL DEFAULT 0,
            cache_write_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL DEFAULT 0,
            exit_code INTEGER NOT NULL DEFAULT 0,
            limit_hit INTEGER NOT NULL DEFAULT 0
        )""",
        "CREATE INDEX claude_calls_at ON claude_calls(at)",
        # --- analytics ------------------------------------------------------------------------------------
        # Current totals, one row per platform per (Tashkent) day: the last fetch of the day wins. History
        # charts work from these even where the API only gives current totals.
        """CREATE TABLE account_snapshots (
            platform TEXT NOT NULL,
            day TEXT NOT NULL,
            followers INTEGER,
            total_views INTEGER,
            media_count INTEGER,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (platform, day)
        )""",
        # Day values reported by the APIs themselves (YouTube Analytics day report, Instagram day insights).
        """CREATE TABLE account_daily (
            platform TEXT NOT NULL,
            day TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (platform, day, metric)
        )""",
        """CREATE TABLE media (
            platform TEXT NOT NULL,
            remote_id TEXT NOT NULL,
            video_id INTEGER REFERENCES videos(id),
            title TEXT NOT NULL DEFAULT '',
            permalink TEXT,
            thumb_path TEXT,
            posted_at TEXT,
            duration REAL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (platform, remote_id)
        )""",
        """CREATE TABLE media_snapshots (
            platform TEXT NOT NULL,
            remote_id TEXT NOT NULL,
            day TEXT NOT NULL,
            views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER, saves INTEGER, reach INTEGER,
            watch_minutes REAL, avg_view_seconds REAL, avg_view_pct REAL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (platform, remote_id, day)
        )""",
        """CREATE TABLE media_retention (
            platform TEXT NOT NULL,
            remote_id TEXT NOT NULL,
            points_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (platform, remote_id)
        )""",
    ],
]


MIGRATIONS.append([
    # Task 04: the owner's reel flow. One row per video: its date-based name, research, versions, drafts, story.
    """CREATE TABLE reels (
        video_id INTEGER PRIMARY KEY REFERENCES videos(id),
        base TEXT NOT NULL,                      -- YYYY-MM-DD-topic (the publish date)
        step TEXT NOT NULL DEFAULT 'research',   -- research | script | voice | broll | render | review | cover |
                                                 -- publish | buffer | story | done
        research_file TEXT,
        topics_json TEXT NOT NULL DEFAULT '[]',
        insight TEXT NOT NULL DEFAULT '',
        topic_index INTEGER,
        version INTEGER NOT NULL DEFAULT 0,
        cover_path TEXT,
        captions_json TEXT NOT NULL DEFAULT '{}',
        drafts_json TEXT NOT NULL DEFAULT '{}',
        git_note TEXT,
        git_folder TEXT,
        live_link TEXT,
        story_draft TEXT,
        fix_notes_json TEXT NOT NULL DEFAULT '[]',
        checklist_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL
    )""",
])


def _remove_direct_posting(conn) -> None:
    """Owner law 15/16 (Task 05): an older database loses the direct-posting tables and the bot-cover / post-now
    columns. Idempotent: a database created after this change never had them. (The only place these legacy names
    may appear in the code: to delete them.)"""
    legacy = {"videos": ("post_now", "announced_at"), "approvals": ("post_now",),
              "renders": ("thumb_youtube", "cover_instagram")}
    conn.execute("DROP TABLE IF EXISTS post_events")
    conn.execute("DROP TABLE IF EXISTS posts")
    for table, cols in legacy.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col in cols:
            if col in have:
                conn.execute(f"ALTER TABLE {table} DROP COLUMN {col}")
    conn.execute("UPDATE videos SET status='done' WHERE status IN ('posted', 'partial', 'scheduled')")
    have = {r[1] for r in conn.execute("PRAGMA table_info(reels)")}
    if "live_links_json" not in have:
        conn.execute("ALTER TABLE reels ADD COLUMN live_links_json TEXT NOT NULL DEFAULT '{}'")


MIGRATIONS.append([_remove_direct_posting])


def _add_buffer_state(conn) -> None:
    """Approved reels go into Buffer's queue (owner, 2026-11-09): the last known state of each queued post
    ({service: {status, due_at, sent_at, link}}) is kept for the website."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(reels)")}
    if "buffer_json" not in have:
        conn.execute("ALTER TABLE reels ADD COLUMN buffer_json TEXT NOT NULL DEFAULT '{}'")


MIGRATIONS.append([_add_buffer_state])


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def now_iso() -> str:
    return iso(utcnow())


def parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        conn = self.connect()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return dict(rows[0]) if rows else None

    def execute(self, sql: str, params: tuple = ()) -> int:
        with self.tx() as conn:
            cur = conn.execute(sql, params)
            return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount

    def migrate(self) -> None:
        with self.tx() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            for number, statements in enumerate(MIGRATIONS[version:], start=version + 1):
                for statement in statements:
                    if callable(statement):
                        statement(conn)
                    else:
                        conn.execute(statement)
                conn.execute(f"PRAGMA user_version={number}")


class KV:
    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str, default: Any = None) -> Any:
        rows = self.db.query("SELECT value FROM kv WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def set(self, key: str, value: Any) -> None:
        with self.db.tx() as conn:
            conn.execute(
                """INSERT INTO kv(key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (key, json.dumps(value), now_iso()),
            )

    def updated_at(self, key: str) -> datetime | None:
        rows = self.db.query("SELECT updated_at FROM kv WHERE key=?", (key,))
        return parse_iso(rows[0]["updated_at"]) if rows else None

    def delete(self, key: str) -> None:
        with self.db.tx() as conn:
            conn.execute("DELETE FROM kv WHERE key=?", (key,))

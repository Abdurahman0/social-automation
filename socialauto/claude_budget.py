"""Claude usage ledger, the one limit pause, and the owner's limit notices (copied from ytauto, one account).

- Every Claude call is recorded (table claude_calls): task, seconds, turns, tokens, exit code, limit hit.
- When the CLI reports a usage limit, all Claude work pauses until the reset time printed in the message
  (+2 min); no probing calls meanwhile. The owner gets ONE Telegram message per limit window with the reopen time
  in Tashkent time (law 5), and one "reopened" message when the first call succeeds again.
- /usage shows today / last 5 hours / this week.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .db import KV, Database

log = logging.getLogger(__name__)

PAUSE_KEY = "claude_paused_until"
PAUSE_REASON_KEY = "claude_paused_reason"
WEEKLY_KEY = "claude_weekly_reset"
LIMIT_NOTICE_KEY = "claude_limit_notice"
WINDOW = timedelta(hours=5)
TASHKENT = ZoneInfo("Asia/Tashkent")


class ClaudeBudgetWait(Exception):
    """Claude work may not start now; try again at `until` (does not count as a failed attempt)."""

    def __init__(self, until: datetime, reason: str):
        super().__init__(reason)
        self.until = until
        self.reason = reason


# --- the limit message ------------------------------------------------------------------------------------------

# "resets 11:10pm (Asia/Samarkand)", "resets Nov 3, 9am (UTC)", "resets Nov 3 at 9am", "resets Tue 9am", "resets 23:10".
# The CLI prints its reset in the machine's own time zone; without "(zone)" that zone is assumed.
_RESET = re.compile(r"resets\s+(?:at\s+)?(?:(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
                    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s+(?:at\s+)?|(?P<wd>mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s+"
                    r"(?:at\s+)?)?(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>am|pm)?(?:\s*\((?P<tz>[A-Za-z_/+-]+)\))?",
                    re.I)
_RESET_IN = re.compile(r"resets\s+in\s+(?:(?P<h>\d+)\s*h(?:ours?|rs?)?)?\s*(?:(?P<m>\d+)\s*m(?:in(?:utes?|s)?)?)?",
                       re.I)
_EPOCH = re.compile(r"limit reached\|(\d{9,11})", re.I)
_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
_DAYS = "mon tue wed thu fri sat sun".split()
JUST_PASSED = timedelta(minutes=30)          # a reset this recently passed is today's, not tomorrow's


def local_zone() -> ZoneInfo:
    """The machine's time zone (the CLI prints reset times in it); Asia/Tashkent if it cannot be read."""
    try:
        name = str(Path("/etc/localtime").resolve()).split("zoneinfo/", 1)[1]
        return ZoneInfo(name)
    except Exception:          # noqa: BLE001
        return ZoneInfo("Asia/Tashkent")


def parse_reset(text: str, now: datetime) -> datetime | None:
    """The reset moment in a limit message ("... · resets 6:10pm (Asia/Samarkand)", "resets Nov 4, 9am (UTC)")."""
    for m in _RESET.finditer(text or ""):
        if not (m.group("ap") or m.group("m") or m.group("tz") or m.group("mon") or m.group("wd")):
            continue           # a bare number ("resets 5") is not a time
        hour, minute = int(m.group("h")), int(m.group("m") or 0)
        if m.group("ap"):
            hour = hour % 12 + (12 if m.group("ap").lower() == "pm" else 0)
        if hour > 23 or minute > 59:
            continue
        try:
            zone = ZoneInfo(m.group("tz")) if m.group("tz") else local_zone()
        except Exception:      # noqa: BLE001 - an unknown zone name
            return None
        local = now.astimezone(zone)
        at = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if m.group("mon"):
            try:
                at = at.replace(month=_MONTHS.index(m.group("mon").lower()[:3]) + 1, day=int(m.group("day")))
            except ValueError:
                return None
            if at < local - timedelta(days=1):
                at = at.replace(year=at.year + 1)
            return at.astimezone(timezone.utc)
        if m.group("wd"):
            at += timedelta(days=(_DAYS.index(m.group("wd").lower()[:3]) - local.weekday()) % 7)
            if at <= local - JUST_PASSED:
                at += timedelta(days=7)
        elif at <= local - JUST_PASSED:
            at += timedelta(days=1)          # "resets 1am" said at 22:00: tomorrow
        return at.astimezone(timezone.utc)
    m = _RESET_IN.search(text or "")
    if m and (m.group("h") or m.group("m")):
        return now + timedelta(hours=int(m.group("h") or 0), minutes=int(m.group("m") or 0))
    return None


def reset_time(text: str, now: datetime) -> datetime | None:
    """The reset moment of any limit message the CLI prints: "Claude AI usage limit reached|<epoch>" or
    "You've hit your 5-hour / weekly limit · resets ...". None when the message names no time."""
    m = _EPOCH.search(text or "")
    if m:
        return datetime.fromtimestamp(int(m.group(1)), tz=timezone.utc)
    return parse_reset(text, now)


def is_weekly(text: str) -> bool:
    return bool(re.search(r"week", text or "", re.I))


def limit_kind(text: str) -> str:
    """Which limit a message is about: "weekly", "5-hour" or "" (not said)."""
    if is_weekly(text):
        return "weekly"
    if re.search(r"(5|five)[- ]hour|session limit", text or "", re.I):
        return "5-hour"
    return ""


# --- what the owner is told (Uzbek, Tashkent time) --------------------------------------------------------------

_KIND_UZ = {"5-hour": "5 soatlik limit", "weekly": "haftalik limit"}
MONTHS_UZ = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr",
             "dekabr"]


def tashkent_time(at: datetime, now: datetime) -> str:
    """"23:10", or "3-noyabr 09:00" when it is not today in Tashkent."""
    local, today = at.astimezone(TASHKENT), now.astimezone(TASHKENT).date()
    if local.date() == today:
        return f"{local:%H:%M}"
    return f"{local.day}-{MONTHS_UZ[local.month - 1]} {local:%H:%M}"


def limit_notice_text(kind: str, reset: datetime | None, until: datetime, now: datetime) -> str:
    what = f" ({_KIND_UZ[kind]})" if kind in _KIND_UZ else ""
    if reset:
        return (f"⏸ Claude limiti tugadi{what}. Soat {tashkent_time(reset, now)} da (Toshkent vaqti) qayta ochiladi — "
                "ish o'sha paytda o'zi davom etadi. Rejalangan joylashlar o'z vaqtida chiqadi.")
    return (f"⏸ Claude limiti tugadi{what}. Ochilish vaqti xabarda yo'q edi; bot soat {tashkent_time(until, now)} da "
            "(Toshkent vaqti) yana urinib ko'radi. Rejalangan joylashlar o'z vaqtida chiqadi.")


RESUME_TEXT = "▶️ Claude limiti ochildi, ish davom etmoqda."


def envelope_usage(envelope: dict[str, Any]) -> dict[str, Any]:
    usage = envelope.get("usage") or {}
    return {"turns": int(envelope.get("num_turns") or 0),
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "cache_read_tokens": int(usage.get("cache_read_input_tokens") or 0),
            "cache_write_tokens": int(usage.get("cache_creation_input_tokens") or 0),
            "cost_usd": float(envelope.get("total_cost_usd") or 0.0)}


class Budget:
    def __init__(self, db: Database, clock=lambda: datetime.now(timezone.utc)):
        self.db = db
        self.kv = KV(db)
        self.clock = clock

    def record(self, task: str, seconds: float, usage: dict[str, Any] | None = None, exit_code: int = 0,
               limit_hit: bool = False) -> None:
        u = usage or {}
        with self.db.tx() as conn:
            conn.execute("""INSERT INTO claude_calls(at, task, seconds, turns, input_tokens, output_tokens,
                            cache_read_tokens, cache_write_tokens, cost_usd, exit_code, limit_hit)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         (self.clock().replace(microsecond=0).isoformat(), task[:80], round(seconds, 1),
                          u.get("turns", 0), u.get("input_tokens", 0), u.get("output_tokens", 0),
                          u.get("cache_read_tokens", 0), u.get("cache_write_tokens", 0), u.get("cost_usd", 0.0),
                          exit_code, int(limit_hit)))

    def usage(self, since: datetime) -> dict[str, Any]:
        row = self.db.query("""SELECT COUNT(*) calls, COALESCE(SUM(seconds),0) seconds, COALESCE(SUM(input_tokens+
                               output_tokens+cache_read_tokens+cache_write_tokens),0) tokens,
                               COALESCE(SUM(limit_hit),0) limits FROM claude_calls WHERE at>=?""",
                            (since.isoformat(),))[0]
        return dict(row)

    def paused_until(self) -> datetime | None:
        value = self.kv.get(PAUSE_KEY)
        if value and datetime.fromisoformat(value) > self.clock():
            return datetime.fromisoformat(value)
        return None

    def check(self) -> None:
        paused = self.paused_until()
        if paused:
            raise ClaudeBudgetWait(paused, "Claude usage limit: waiting for the reset")

    def pause(self, until: datetime, reason: str) -> None:
        current = self.paused_until()
        if current and current >= until:
            return
        self.kv.set(PAUSE_KEY, until.isoformat())
        self.kv.set(PAUSE_REASON_KEY, reason[:300])
        log.warning("Claude paused until %s: %s", until.isoformat(), reason[:120])

    def limit_hit(self, text: str, fallback_minutes: int = 60) -> datetime:
        now = self.clock()
        reset = reset_time(text, now)
        if reset and reset < now - timedelta(days=1):
            reset = None
        until = (reset + timedelta(minutes=2)) if reset else now + timedelta(minutes=fallback_minutes)
        until = max(until, now + timedelta(minutes=3))
        if reset and is_weekly(text):
            self.kv.set(WEEKLY_KEY, reset.isoformat())
        self.pause(until, text)
        return until

    def claim_limit_notice(self, text: str, until: datetime) -> str | None:
        """The owner's limit message, or None if this limit window was announced already (atomic)."""
        now = self.clock()
        reset = reset_time(text, now)
        if reset and reset < now - timedelta(days=1):
            reset = None
        with self.db.tx() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key=?", (LIMIT_NOTICE_KEY,)).fetchone()
            prev = json.loads(row["value"]) if row else None
            if prev and not prev.get("resumed"):
                if datetime.fromisoformat(prev["until"]) > now:
                    return None
                if reset and prev.get("reset") == reset.isoformat():
                    return None
            notice = {"reset": reset.isoformat() if reset else None, "until": until.isoformat(),
                      "kind": limit_kind(text), "at": now.isoformat(), "resumed": False, "resume_sent": False}
            conn.execute("""INSERT INTO kv(key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE
                            SET value=excluded.value, updated_at=excluded.updated_at""",
                         (LIMIT_NOTICE_KEY, json.dumps(notice), now.isoformat()))
        return limit_notice_text(limit_kind(text), reset, until, now)

    def note_success(self) -> None:
        now = self.clock()
        with self.db.tx() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key=?", (LIMIT_NOTICE_KEY,)).fetchone()
            notice = json.loads(row["value"]) if row else None
            if not notice or notice.get("resumed"):
                return
            notice["resumed"] = True
            conn.execute("UPDATE kv SET value=?, updated_at=? WHERE key=?",
                         (json.dumps(notice), now.isoformat(), LIMIT_NOTICE_KEY))

    def take_resume_notice(self) -> str | None:
        with self.db.tx() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key=?", (LIMIT_NOTICE_KEY,)).fetchone()
            notice = json.loads(row["value"]) if row else None
            if not notice or not notice.get("resumed") or notice.get("resume_sent"):
                return None
            notice["resume_sent"] = True
            conn.execute("UPDATE kv SET value=?, updated_at=? WHERE key=?",
                         (json.dumps(notice), self.clock().isoformat(), LIMIT_NOTICE_KEY))
        return RESUME_TEXT

    def report(self) -> str:
        """Plain Uzbek text for /usage."""
        now = self.clock()
        day = now.astimezone(TASHKENT).replace(hour=0, minute=0, second=0, microsecond=0)
        week = day - timedelta(days=day.weekday())
        lines = ["🤖 Claude sarfi (1-akkaunt, obuna orqali, API kalitsiz)"]
        paused = self.paused_until()
        lines.append(f"⏸ Limit: {tashkent_time(paused, now)} gacha kutilmoqda (Toshkent vaqti)" if paused
                     else "✅ Limit: hozir ochiq")
        weekly = self.kv.get(WEEKLY_KEY)
        if weekly and datetime.fromisoformat(weekly) > now:
            lines.append(f"Haftalik limit yangilanishi: {tashkent_time(datetime.fromisoformat(weekly), now)}")
        for label, since in (("Bugun", day), ("Oxirgi 5 soat", now - WINDOW), ("Shu hafta", week)):
            u = self.usage(since)
            lines.append(f"{label}: {u['calls']} ta chaqiruv, {u['seconds'] / 60:.0f} daqiqa, "
                         f"{u['tokens'] / 1000:.0f} ming token" + (f", limit {u['limits']} marta" if u["limits"] else ""))
        return "\n".join(lines)

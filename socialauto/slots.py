"""Slot calendar (copied from ytauto, trimmed). Slots are wall-clock times in one IANA zone (Asia/Tashkent by
default), so DST is handled by zoneinfo: 19:00 stays 19:00 local time all year. A time that does not exist on a
spring-forward day is moved forward by the gap; an ambiguous fall-back time uses its first occurrence."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import ScheduleConfig


class SlotConfigError(ValueError):
    pass


def zone(cfg: ScheduleConfig) -> ZoneInfo:
    try:
        return ZoneInfo(cfg.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise SlotConfigError(f"Unknown IANA time zone: {cfg.timezone!r}") from exc


def times(cfg: ScheduleConfig) -> list[time]:
    try:
        parsed = sorted({time.fromisoformat(t) for t in cfg.slot_times})
    except ValueError as exc:
        raise SlotConfigError(f"Bad slot time in {cfg.slot_times!r}; use HH:MM.") from exc
    if not parsed:
        raise SlotConfigError("schedule.slot_times is empty.")
    return parsed


def localize(day: date, at: time, tz: ZoneInfo) -> datetime:
    """Wall-clock time on a day -> aware UTC datetime, resolving DST gaps and overlaps (PEP 495 fold=0)."""
    return datetime.combine(day, at, tzinfo=tz).astimezone(timezone.utc)


def slots_between(cfg: ScheduleConfig, start: datetime, end: datetime) -> list[datetime]:
    """All slot instants (UTC) with start < slot <= end."""
    tz, ts = zone(cfg), times(cfg)
    day = start.astimezone(tz).date() - timedelta(days=1)
    last = end.astimezone(tz).date() + timedelta(days=1)
    out: list[datetime] = []
    while day <= last:
        out.extend(s for t in ts if start < (s := localize(day, t, tz)) <= end)
        day += timedelta(days=1)
    return sorted(set(out))


def next_free_slot(cfg: ScheduleConfig, now: datetime, taken: set[datetime], after: datetime | None = None,
                   horizon_days: int = 60) -> datetime:
    """The first slot at least min_lead_minutes away (and after `after`) that no other video holds."""
    start = max(now + timedelta(minutes=cfg.min_lead_minutes), after or now)
    for slot in slots_between(cfg, start, start + timedelta(days=horizon_days)):
        if slot not in taken:
            return slot
    raise SlotConfigError("no free slot within the horizon")


def describe(cfg: ScheduleConfig, slot: datetime) -> str:
    """Uzbek, owner's zone: "9-noyabr, 19:00"."""
    from .claude_budget import MONTHS_UZ
    local = slot.astimezone(zone(cfg))
    return f"{local.day}-{MONTHS_UZ[local.month - 1]}, {local:%H:%M}"

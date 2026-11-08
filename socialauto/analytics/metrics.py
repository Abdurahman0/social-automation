"""Dashboard numbers computed from the stored snapshots (no API calls here).

Definitions (shown in the dashboard's help texts):
- followers: subscribers (YouTube) / followers (Instagram), the latest snapshot;
- total views: YouTube lifetime channel views; Instagram: the sum of views of the fetched media;
- views in a period: the APIs' own day values (YouTube Analytics `views`, Instagram day `views`); when a day is
  missing, the growth of the stored totals between snapshots is used instead ("snapshot math");
- reach (Instagram): sum of the day `reach` values in the period;
- engagement rate: (likes + comments + shares + saves) / views over the period's day values; when the platform has
  no day interactions, over the videos posted in the period (their latest totals);
- growth: value now minus the value at the latest snapshot on/before N days ago (day / week / month); None until
  that much history exists.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from ..db import Database, parse_iso
from .collector import TASHKENT, media_key

PLATFORMS = ("youtube", "instagram")
INTERACTIONS = ("likes", "comments", "shares", "saves")


def _d(day: str) -> date:
    return date.fromisoformat(day)


def daily_from_totals(snapshots: list[tuple[str, float | None]], clip: bool = True) -> dict[str, float]:
    """Day-by-day growth of a cumulative total from snapshots [(day, total)], spreading a multi-day gap evenly.
    Views never shrink (clip); follower counts can (clip=False)."""
    rows = sorted((d, v) for d, v in snapshots if v is not None)
    out: dict[str, float] = {}
    for (d0, v0), (d1, v1) in zip(rows, rows[1:]):
        days = (_d(d1) - _d(d0)).days
        if days <= 0:
            continue
        step = (v1 - v0) / days
        if clip:
            step = max(0.0, step)
        for k in range(1, days + 1):
            out[(_d(d0) + timedelta(days=k)).isoformat()] = step
    return out


def value_on(snapshots: list[tuple[str, float | None]], day: str) -> float | None:
    """The latest snapshot value on or before `day`."""
    best = None
    for d, v in sorted(snapshots):
        if d <= day and v is not None:
            best = v
    return best


def growth(snapshots: list[tuple[str, float | None]], today: str) -> dict[str, float | None]:
    now = value_on(snapshots, today)
    out = {}
    first = min((d for d, v in snapshots if v is not None), default=None)
    for name, days in (("day", 1), ("week", 7), ("month", 30)):
        ref_day = (_d(today) - timedelta(days=days)).isoformat()
        ref = value_on(snapshots, ref_day) if first and first <= ref_day else None
        out[name] = (now - ref) if (now is not None and ref is not None) else None
    return out


class Metrics:
    def __init__(self, db: Database, today: date | None = None):
        self.db = db
        self.today = today or datetime.now(TASHKENT).date()

    # --- raw reads ----------------------------------------------------------------------------------------
    def snapshots(self, platform: str, field: str) -> list[tuple[str, float | None]]:
        return [(r["day"], r[field]) for r in self.db.query(
            f"SELECT day, {field} FROM account_snapshots WHERE platform=? ORDER BY day", (platform,))]

    def daily(self, platform: str, metric: str, start: date, end: date) -> dict[str, float]:
        return {r["day"]: r["value"] for r in self.db.query(
            "SELECT day, value FROM account_daily WHERE platform=? AND metric=? AND day>=? AND day<=?",
            (platform, metric, start.isoformat(), end.isoformat()))}

    def has_daily(self, platform: str, metric: str) -> bool:
        return bool(self.db.query("SELECT 1 FROM account_daily WHERE platform=? AND metric=? LIMIT 1", (platform, metric)))

    def has_data(self, platform: str) -> bool:
        return bool(self.db.query("SELECT 1 FROM account_snapshots WHERE platform=? LIMIT 1", (platform,)))

    # --- series -------------------------------------------------------------------------------------------
    def views_by_day(self, platform: str, start: date, end: date) -> dict[str, float]:
        api = self.daily(platform, "views", start, end)
        # The platform's own day values win. Where it reports days at all, the newest days it has not reported yet
        # (data delay) stay empty instead of being guessed from partial-day snapshots.
        snap = {} if self.has_daily(platform, "views") else daily_from_totals(self.snapshots(platform, "total_views"))
        out = {}
        d = start
        while d <= end:
            k = d.isoformat()
            if k in api:
                out[k] = api[k]
            elif k in snap:
                out[k] = snap[k]
            d += timedelta(days=1)
        return out

    def interactions_by_day(self, platform: str, start: date, end: date) -> dict[str, float]:
        out: dict[str, float] = defaultdict(float)
        found = False
        for metric in INTERACTIONS:
            for k, v in self.daily(platform, metric, start, end).items():
                out[k] += v
                found = True
        return dict(out) if found else {}

    def followers_by_day(self, platform: str, start: date, end: date) -> dict[str, float]:
        snaps = self.snapshots(platform, "followers")
        out, d = {}, start
        while d <= end:
            v = value_on(snaps, d.isoformat())
            if v is not None and any(s <= d.isoformat() for s, _ in snaps):
                out[d.isoformat()] = v
            d += timedelta(days=1)
        return out

    def series(self, metric: str, start: date, end: date) -> dict[str, Any]:
        """{"days": [...], "youtube": [...|None], "instagram": [...], "combined": [...]} for the charts."""
        days = []
        d = start
        while d <= end:
            days.append(d.isoformat())
            d += timedelta(days=1)
        per = {}
        for p in PLATFORMS:
            if metric == "views":
                values = self.views_by_day(p, start, end)
            elif metric == "followers":
                values = self.followers_by_day(p, start, end)
            elif metric == "engagement":
                views, inter = self.views_by_day(p, start, end), self.interactions_by_day(p, start, end)
                values = {k: round(100 * inter[k] / views[k], 2) for k in inter if views.get(k)}
            elif metric == "reach":
                values = self.daily(p, "reach", start, end)
            else:
                raise ValueError(metric)
            per[p] = [values.get(k) for k in days]
        combined = []
        for i in range(len(days)):
            vals = [per[p][i] for p in PLATFORMS if per[p][i] is not None]
            if metric == "engagement":
                v = self.series_engagement_combined(days[i])
            else:
                v = sum(vals) if vals else None
            combined.append(v)
        return {"metric": metric, "days": days, **per, "combined": combined}

    def series_engagement_combined(self, day: str) -> float | None:
        d = _d(day)
        views = sum(self.views_by_day(p, d, d).get(day, 0) for p in PLATFORMS)
        inter = sum(self.interactions_by_day(p, d, d).get(day, 0) for p in PLATFORMS)
        return round(100 * inter / views, 2) if views and inter else None

    # --- overview -----------------------------------------------------------------------------------------
    def platform_overview(self, platform: str, days: int = 30) -> dict[str, Any] | None:
        if not self.has_data(platform):
            return None
        today = self.today.isoformat()
        start = self.today - timedelta(days=days - 1)
        followers = self.snapshots(platform, "followers")
        views_period = self.views_by_day(platform, start, self.today)
        inter = self.interactions_by_day(platform, start, self.today)
        reach = self.daily(platform, "reach", start, self.today)
        v_sum = sum(views_period.values()) if views_period else None
        if inter and v_sum:
            engagement = 100 * sum(inter.values()) / v_sum
        else:
            engagement = self._media_engagement(platform, start)
        def views_growth(n: int) -> float | None:
            s = self.views_by_day(platform, self.today - timedelta(days=n - 1), self.today)
            return sum(s.values()) if len(s) >= max(1, n // 2) else None
        return {
            "followers": value_on(followers, today),
            "followers_growth": growth(followers, today),
            "total_views": value_on(self.snapshots(platform, "total_views"), today),
            "views_period": v_sum,
            "views_growth": {"day": views_growth(1), "week": views_growth(7), "month": views_growth(30)},
            "reach_period": sum(reach.values()) if reach else None,
            "engagement_rate": round(engagement, 2) if engagement is not None else None,
            "media_count": value_on(self.snapshots(platform, "media_count"), today),
            "history_days": len({d for d, v in followers if v is not None}),
        }

    def _media_engagement(self, platform: str, since: date) -> float | None:
        rows = self.latest_media(platform)
        views = inter = 0.0
        for r in rows:
            if r["posted_at"] and parse_iso(r["posted_at"]).astimezone(TASHKENT).date() >= since and r["views"]:
                views += r["views"]
                inter += sum(r[k] or 0 for k in INTERACTIONS)
        return 100 * inter / views if views else None

    def overview(self, days: int = 30) -> dict[str, Any]:
        per = {p: self.platform_overview(p, days) for p in PLATFORMS}
        live = [v for v in per.values() if v]
        def total(key: str) -> float | None:
            vals = [v[key] for v in live if v.get(key) is not None]
            return sum(vals) if vals else None
        def total_growth(key: str, span: str) -> float | None:
            vals = [v[key][span] for v in live if v[key][span] is not None]
            return sum(vals) if vals else None
        views = total("views_period")
        inter_total = 0.0
        start = self.today - timedelta(days=days - 1)
        for p in PLATFORMS:
            if per[p]:
                inter_total += sum(self.interactions_by_day(p, start, self.today).values())
        combined = None
        if live:
            combined = {"followers": total("followers"), "total_views": total("total_views"), "views_period": views,
                        "reach_period": total("reach_period"),
                        "followers_growth": {s: total_growth("followers_growth", s) for s in ("day", "week", "month")},
                        "views_growth": {s: total_growth("views_growth", s) for s in ("day", "week", "month")},
                        "engagement_rate": round(100 * inter_total / views, 2) if views and inter_total else
                        (round(sum(v["engagement_rate"] for v in live if v["engagement_rate"] is not None) /
                               max(1, len([v for v in live if v["engagement_rate"] is not None])), 2)
                         if any(v["engagement_rate"] is not None for v in live) else None)}
        return {"days": days, "platforms": per, "combined": combined}

    # --- videos -------------------------------------------------------------------------------------------
    def latest_media(self, platform: str | None = None) -> list[dict[str, Any]]:
        sql = """SELECT m.*, s.views, s.likes, s.comments, s.shares, s.saves, s.reach, s.watch_minutes,
                 s.avg_view_seconds, s.avg_view_pct, s.day AS stats_day FROM media m
                 LEFT JOIN media_snapshots s ON s.platform=m.platform AND s.remote_id=m.remote_id
                 AND s.day=(SELECT MAX(day) FROM media_snapshots x WHERE x.platform=m.platform AND x.remote_id=m.remote_id)"""
        args: tuple = ()
        if platform:
            sql += " WHERE m.platform=?"
            args = (platform,)
        return [dict(r) for r in self.db.query(sql, args)]

    @staticmethod
    def _stats(r: dict[str, Any]) -> dict[str, Any]:
        return {k: r.get(k) for k in ("views", "likes", "comments", "shares", "saves", "reach", "watch_minutes",
                                      "avg_view_seconds", "avg_view_pct", "permalink")}

    def videos(self) -> list[dict[str, Any]]:
        """One row per video: our videos merge their YouTube and Instagram posts side by side."""
        rows: dict[str, dict[str, Any]] = {}
        for r in self.latest_media():
            key = f"v{r['video_id']}" if r["video_id"] else media_key(r["platform"], r["remote_id"])
            row = rows.setdefault(key, {"key": key if not r["video_id"] else media_key("video", str(r["video_id"])),
                                        "title": r["title"], "thumb": None, "posted_at": r["posted_at"],
                                        "duration": r["duration"], "youtube": None, "instagram": None,
                                        "video_id": r["video_id"]})
            row[r["platform"]] = self._stats(r)
            if r["platform"] == "youtube" or not row["title"]:
                row["title"] = r["title"] or row["title"]
            if r["thumb_path"] and (row["thumb"] is None or r["platform"] == "youtube"):
                row["thumb"] = media_key(r["platform"], r["remote_id"])
            if r["posted_at"] and (not row["posted_at"] or r["posted_at"] < row["posted_at"]):
                row["posted_at"] = r["posted_at"]
            row["duration"] = row["duration"] or r["duration"]
        out = []
        for row in rows.values():
            for k in ("views", "likes", "comments", "shares", "saves"):
                row[f"total_{k}"] = sum((row[p] or {}).get(k) or 0 for p in PLATFORMS)
            out.append(row)
        return sorted(out, key=lambda r: r["posted_at"] or "", reverse=True)

    def video(self, key: str) -> dict[str, Any] | None:
        row = next((r for r in self.videos() if r["key"] == key), None)
        if not row:
            return None
        history = {}
        retention = None
        for p in PLATFORMS:
            remote = self._remote_for(row, p)
            if not remote:
                continue
            hist = self.db.query("SELECT day, views, likes, comments FROM media_snapshots WHERE platform=? AND "
                                 "remote_id=? ORDER BY day", (p, remote))
            history[p] = [dict(h) for h in hist]
            ret = self.db.one("SELECT points_json FROM media_retention WHERE platform=? AND remote_id=?", (p, remote))
            if ret and p == "youtube":
                retention = json.loads(ret["points_json"])
        return {**row, "history": history, "retention": retention}

    def _remote_for(self, row: dict, platform: str) -> str | None:
        for r in self.db.query("SELECT remote_id, video_id FROM media WHERE platform=?", (platform,)):
            if row["video_id"] and r["video_id"] == row["video_id"]:
                return r["remote_id"]
            if not row["video_id"] and media_key(platform, r["remote_id"]) == row["key"]:
                return r["remote_id"]
        return None

    def thumb_path(self, key: str) -> str | None:
        for r in self.db.query("SELECT platform, remote_id, thumb_path FROM media WHERE thumb_path IS NOT NULL"):
            if media_key(r["platform"], r["remote_id"]) == key:
                return r["thumb_path"]
        return None

    # --- insights -----------------------------------------------------------------------------------------
    def best_times(self) -> dict[str, Any]:
        """Average views per video by posting hour and weekday (Tashkent time)."""
        by_hour: dict[int, list[float]] = defaultdict(list)
        by_day: dict[int, list[float]] = defaultdict(list)
        for r in self.videos():
            if not r["posted_at"]:
                continue
            local = parse_iso(r["posted_at"]).astimezone(TASHKENT)
            by_hour[local.hour].append(r["total_views"])
            by_day[local.weekday()].append(r["total_views"])
        hours = [{"hour": h, "videos": len(v), "avg_views": round(sum(v) / len(v))} for h, v in sorted(by_hour.items())]
        days = [{"weekday": d, "videos": len(v), "avg_views": round(sum(v) / len(v))} for d, v in sorted(by_day.items())]
        best = max(hours, key=lambda x: x["avg_views"]) if hours else None
        return {"hours": hours, "weekdays": days, "best_hour": best["hour"] if best else None}

    def top_videos(self, n: int = 5) -> list[dict[str, Any]]:
        return sorted(self.videos(), key=lambda r: r["total_views"], reverse=True)[:n]

    def comparison(self, days: int = 30) -> dict[str, Any]:
        start = self.today - timedelta(days=days - 1)
        out = {}
        for p in PLATFORMS:
            if not self.has_data(p):
                out[p] = None
                continue
            views = self.views_by_day(p, start, self.today)
            inter = self.interactions_by_day(p, start, self.today)
            vids = [r for r in self.latest_media(p) if r["posted_at"]
                    and parse_iso(r["posted_at"]).astimezone(TASHKENT).date() >= start]
            fol = self.snapshots(p, "followers")
            gained = None
            if p == "youtube":
                g = self.daily(p, "subscribersGained", start, self.today)
                lost = self.daily(p, "subscribersLost", start, self.today)
                gained = sum(g.values()) - sum(lost.values()) if g else None
            if gained is None:
                now, ref = value_on(fol, self.today.isoformat()), value_on(fol, start.isoformat())
                gained = now - ref if now is not None and ref is not None else None
            avg_views = sum(r["views"] or 0 for r in vids) / len(vids) if vids else None
            out[p] = {"views": sum(views.values()) if views else None,
                      "interactions": sum(inter.values()) if inter else None,
                      "followers_gained": gained, "videos": len(vids),
                      "avg_views_per_video": round(avg_views) if avg_views is not None else None,
                      "avg_view_seconds": _avg([r["avg_view_seconds"] for r in vids])}
        return out


def _avg(values: list) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None

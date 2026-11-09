"""Fetches live statistics from the official APIs and stores them (cache + daily snapshots).

YouTube (Data API v3 + YouTube Analytics API v2):
    every refresh: channels.list statistics (subscribers, lifetime views, video count) and videos.list statistics of
    the 50 newest uploads (views, likes, comments) - ~3 quota units;
    every reports_refresh_hours: the Analytics day report for the last 90 days (views, estimatedMinutesWatched,
    averageViewDuration, likes, comments, shares, subscribersGained, subscribersLost), the per-video report
    (watch time, average view duration / percentage, shares) and audience retention (elapsedVideoTimeRatio ->
    audienceWatchRatio) of the videos this bot posted.
Instagram (Graph API with Facebook Login, metric names per the 2026 docs; `impressions`/`plays` are gone):
    every refresh: followers_count / media_count, the 50 newest media and their insights (views, reach, likes,
    comments, shares, saved, total_interactions, ig_reels_avg_watch_time, ig_reels_video_view_total_time);
    every reports_refresh_hours: account day insights (reach, views, accounts_engaged, total_interactions, likes,
    comments, shares, saves) for the last days.

Everything is written to SQLite. account_snapshots / media_snapshots keep one row per (Tashkent) day with the
latest totals of that day, so history charts work even where an API only reports current totals. Thumbnails are
cached locally (Instagram's CDN links expire). Before an account is connected nothing is invented: if the Buffer
key is set, the posts that went out through Buffer give per-post numbers (views, likes, comments, shares, saves,
reach, average watch time; Buffer refreshes them about once a day), stored as `buffer:<post id>` media with the
account's follower count left empty. When the platform is connected directly, that Buffer data is removed and the
official API takes over. Without Buffer and without a connection the dashboard shows the "connect" state.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import requests

from ..db import KV, Database, iso, parse_iso

log = logging.getLogger(__name__)

TASHKENT = ZoneInfo("Asia/Tashkent")
YT_DAY_METRICS = ("views,estimatedMinutesWatched,averageViewDuration,likes,comments,shares,subscribersGained,"
                  "subscribersLost")
YT_VIDEO_METRICS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,shares"
IG_DAYS_BACK = 30
UPDATED_KEY = "analytics:{}:updated"
REPORTS_KEY = "analytics:{}:reports"
ERROR_KEY = "analytics:{}:error"
SOURCE_KEY = "analytics:{}:source"            # "direct" (the platform's own API) or "buffer" (fallback)
BUFFER_DAYS_KEY = "analytics:{}:buffer_days"  # account snapshot days written by the Buffer fallback
BUFFER_PREFIX = "buffer:"                     # media.remote_id of a post seen only through Buffer
BUFFER_POSTS = 100                            # newest sent posts per platform read from Buffer


def local_day(dt: datetime) -> str:
    return dt.astimezone(TASHKENT).date().isoformat()


def iso_duration(value: str | None) -> float | None:
    """ISO 8601 duration (PT1M5S) -> seconds."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", value or "")
    if not m:
        return None
    d, h, mi, s = (float(x) if x else 0.0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def media_key(platform: str, remote_id: str) -> str:
    """An opaque key for URLs (the UI never shows platform ids)."""
    return hashlib.sha1(f"{platform}:{remote_id}".encode()).hexdigest()[:10]


class Collector:
    def __init__(self, settings, db: Database, kv: KV, youtube_factory: Callable[[], Any] | None,
                 instagram_factory: Callable[[], Any] | None, clock: Callable[[], datetime],
                 session: requests.Session | None = None, buffer_factory: Callable[[], Any] | None = None):
        self.settings = settings
        self.db = db
        self.kv = kv
        self.youtube_factory = youtube_factory
        self.instagram_factory = instagram_factory
        self.clock = clock
        self.session = session or requests.Session()
        self.buffer_factory = buffer_factory       # Buffer statistics while a platform is not connected directly
        self.thumbs = settings.data_dir / "thumbs"

    # --- connection state ---------------------------------------------------------------------------------
    def connected(self) -> dict[str, bool]:
        s = self.settings
        return {"youtube": s.resolve(s.youtube.token_file).exists(),
                "instagram": s.resolve(s.instagram.token_file).exists()}

    def source(self, platform: str) -> str | None:
        """Where the stored numbers of this platform come from: "direct", "buffer" or None (nothing yet)."""
        return self.kv.get(SOURCE_KEY.format(platform))

    def updated_at(self, platform: str) -> datetime | None:
        value = self.kv.get(UPDATED_KEY.format(platform))
        return parse_iso(value) if value else None

    # --- refresh ------------------------------------------------------------------------------------------
    def refresh(self, force_reports: bool = False) -> list[tuple[str, str]]:
        """Refresh every connected platform. Returns owner alerts [(key, Uzbek text)] (expired auth only)."""
        from ..platforms.instagram import InstagramAuthError
        from ..platforms.youtube import YouTubeAuthError
        alerts = []
        conn = self.connected()
        for platform, factory, fn in (("youtube", self.youtube_factory, self.refresh_youtube),
                                      ("instagram", self.instagram_factory, self.refresh_instagram)):
            if not conn[platform] or factory is None:
                continue
            try:
                client = factory()
                if self.source(platform) == "buffer":
                    self._drop_buffer_data(platform)       # the real API takes over; Buffer numbers would double
                due = force_reports or self._reports_due(platform)
                fn(client, reports=due)
                if due:
                    self.kv.set(REPORTS_KEY.format(platform), iso(self.clock()))
                self.kv.set(UPDATED_KEY.format(platform), iso(self.clock()))
                self.kv.set(SOURCE_KEY.format(platform), "direct")
                self.kv.delete(ERROR_KEY.format(platform))
            except (YouTubeAuthError, InstagramAuthError) as exc:
                log.warning("Analytics: %s auth problem: %s", platform, exc)
                self.kv.set(ERROR_KEY.format(platform), "auth")
                cmd = "youtube-auth" if platform == "youtube" else "instagram-connect"
                alerts.append((platform, f"🔑 {platform.capitalize()} ruxsati tugagan — statistika va joylash "
                                         f"to'xtadi. Terminalda: `.venv/bin/python -m socialauto {cmd}`."))
            except Exception as exc:      # noqa: BLE001 - logged; the dashboard shows the last good data
                log.exception("Analytics: %s refresh failed", platform)
                self.kv.set(ERROR_KEY.format(platform), type(exc).__name__)
        fallback = [p for p in ("youtube", "instagram") if not conn[p]]
        if fallback and self.buffer_factory is not None:
            self._refresh_buffer_safely(fallback)
        return alerts

    def _refresh_buffer_safely(self, platforms: list[str]) -> None:
        try:
            buffer = self.buffer_factory()
            if buffer is None or getattr(buffer, "dry_run", False):
                return
            self.refresh_from_buffer(buffer, platforms)
        except Exception as exc:          # noqa: BLE001 - logged; the dashboard keeps the last good Buffer numbers
            log.warning("Analytics: Buffer statistics failed: %s", type(exc).__name__)
            for p in platforms:
                if self.source(p) == "buffer":
                    self.kv.set(ERROR_KEY.format(p), type(exc).__name__)

    def _reports_due(self, platform: str) -> bool:
        last = self.kv.get(REPORTS_KEY.format(platform))
        return not last or self.clock() - parse_iso(last) >= timedelta(hours=self.settings.analytics.reports_refresh_hours)

    # --- storage helpers ----------------------------------------------------------------------------------
    def save_account(self, platform: str, followers: int | None, total_views: int | None, media_count: int | None):
        day = local_day(self.clock())
        self.db.execute("""INSERT INTO account_snapshots(platform, day, followers, total_views, media_count, fetched_at)
                           VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(platform, day) DO UPDATE SET
                           followers=excluded.followers, total_views=excluded.total_views,
                           media_count=excluded.media_count, fetched_at=excluded.fetched_at""",
                        (platform, day, followers, total_views, media_count, iso(self.clock())))

    def save_daily(self, platform: str, day: str, values: dict[str, float]) -> None:
        with self.db.tx() as conn:
            for metric, value in values.items():
                if value is None:
                    continue
                conn.execute("""INSERT INTO account_daily(platform, day, metric, value, fetched_at) VALUES (?,?,?,?,?)
                                ON CONFLICT(platform, day, metric) DO UPDATE SET value=excluded.value,
                                fetched_at=excluded.fetched_at""", (platform, day, metric, float(value), iso(self.clock())))

    def save_media(self, platform: str, remote_id: str, title: str, permalink: str | None, thumb_url: str | None,
                   posted_at: str | None, duration: float | None) -> None:
        video_id = self._our_video(platform, remote_id, permalink)
        thumb = self._cache_thumb(platform, remote_id, thumb_url)
        self.db.execute("""INSERT INTO media(platform, remote_id, video_id, title, permalink, thumb_path, posted_at,
                           duration, fetched_at) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(platform, remote_id) DO UPDATE SET
                           video_id=COALESCE(excluded.video_id, media.video_id), title=excluded.title,
                           permalink=excluded.permalink, thumb_path=COALESCE(excluded.thumb_path, media.thumb_path),
                           posted_at=excluded.posted_at, duration=COALESCE(excluded.duration, media.duration),
                           fetched_at=excluded.fetched_at""",
                        (platform, remote_id, video_id, title[:200], permalink, thumb, posted_at, duration,
                         iso(self.clock())))

    def _our_video(self, platform: str, remote_id: str, permalink: str | None) -> int | None:
        """Is this media one of our reels? Matched through the live links Buffer reported for its drafts, or (for a
        post seen through Buffer) through the Buffer post id of the reel's draft."""
        import json as _json
        if remote_id.startswith(BUFFER_PREFIX):
            post_id = remote_id[len(BUFFER_PREFIX):]
            for row in self.db.query("SELECT video_id, drafts_json FROM reels WHERE drafts_json<>'{}'"):
                if (_json.loads(row["drafts_json"]) or {}).get(platform) == post_id:
                    return row["video_id"]
        for row in self.db.query("SELECT video_id, live_links_json FROM reels WHERE live_links_json<>'{}'"):
            link = (_json.loads(row["live_links_json"]) or {}).get(platform, "")
            if link and (remote_id in link or (permalink and permalink.rstrip("/") == link.rstrip("/"))):
                return row["video_id"]
        return None

    def save_media_stats(self, platform: str, remote_id: str, **values: Any) -> None:
        day = local_day(self.clock())
        cols = ["views", "likes", "comments", "shares", "saves", "reach", "watch_minutes", "avg_view_seconds",
                "avg_view_pct"]
        known = {k: v for k, v in values.items() if k in cols and v is not None}
        if not known:
            return
        exists = self.db.one("SELECT 1 FROM media_snapshots WHERE platform=? AND remote_id=? AND day=?",
                             (platform, remote_id, day))
        if exists:
            sets = ", ".join(f"{k}=?" for k in known)
            self.db.execute(f"UPDATE media_snapshots SET {sets}, fetched_at=? WHERE platform=? AND remote_id=? AND day=?",
                            (*known.values(), iso(self.clock()), platform, remote_id, day))
        else:
            names = ", ".join(known)
            self.db.execute(f"INSERT INTO media_snapshots(platform, remote_id, day, {names}, fetched_at) "
                            f"VALUES (?, ?, ?, {', '.join('?' * len(known))}, ?)",
                            (platform, remote_id, day, *known.values(), iso(self.clock())))

    def _cache_thumb(self, platform: str, remote_id: str, url: str | None) -> str | None:
        if not url:
            return None
        path = self.thumbs / f"{media_key(platform, remote_id)}.jpg"
        if path.exists() and path.stat().st_size > 0:
            return str(path)
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/"):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(resp.content)
                return str(path)
        except requests.RequestException as exc:
            log.debug("thumbnail not cached: %s", exc)
        return None

    # --- YouTube ------------------------------------------------------------------------------------------
    def refresh_youtube(self, yt, reports: bool = True) -> None:
        from ..platforms.youtube import watch_url
        ch = yt.channel()
        st = ch.get("statistics", {})
        self.save_account("youtube", int(st.get("subscriberCount") or 0) if not st.get("hiddenSubscriberCount") else None,
                          int(st.get("viewCount") or 0), int(st.get("videoCount") or 0))
        ids = yt.recent_upload_ids(50)
        for item in yt.videos(ids) if ids else []:
            sn, stats = item.get("snippet", {}), item.get("statistics", {})
            thumbs = sn.get("thumbnails", {})
            url = (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
            self.save_media("youtube", item["id"], sn.get("title", ""), watch_url(item["id"]), url,
                            sn.get("publishedAt"), iso_duration(item.get("contentDetails", {}).get("duration")))
            self.save_media_stats("youtube", item["id"], views=int(stats.get("viewCount") or 0),
                                  likes=int(stats.get("likeCount") or 0), comments=int(stats.get("commentCount") or 0))
        if not reports:
            return
        today = self.clock().astimezone(timezone.utc).date()
        rep = yt.report(startDate=(today - timedelta(days=90)).isoformat(), endDate=today.isoformat(),
                        metrics=YT_DAY_METRICS, dimensions="day", sort="day")
        names = [h["name"] for h in rep.get("columnHeaders", [])]
        for row in rep.get("rows", []) or []:
            data = dict(zip(names, row))
            day = data.pop("day")
            self.save_daily("youtube", day, {k: float(v) for k, v in data.items()})
        rep = yt.report(startDate="2005-01-01", endDate=today.isoformat(), metrics=YT_VIDEO_METRICS,
                        dimensions="video", sort="-views", maxResults=200)
        names = [h["name"] for h in rep.get("columnHeaders", [])]
        for row in rep.get("rows", []) or []:
            data = dict(zip(names, row))
            if self.db.one("SELECT 1 FROM media WHERE platform='youtube' AND remote_id=?", (data["video"],)):
                self.save_media_stats("youtube", data["video"], watch_minutes=float(data["estimatedMinutesWatched"]),
                                      avg_view_seconds=float(data["averageViewDuration"]),
                                      avg_view_pct=float(data["averageViewPercentage"]), shares=int(data["shares"]))
        for post in self.db.query("""SELECT remote_id FROM media WHERE platform='youtube' AND video_id IS NOT NULL
                                     ORDER BY posted_at DESC LIMIT 20"""):
            try:
                rep = yt.report(startDate="2005-01-01", endDate=today.isoformat(), metrics="audienceWatchRatio",
                                dimensions="elapsedVideoTimeRatio", filters=f"video=={post['remote_id']}")
            except Exception as exc:   # noqa: BLE001 - retention is only available after enough views
                log.debug("retention not available: %s", exc)
                continue
            points = [[float(a), float(b)] for a, b in rep.get("rows", []) or []]
            if points:
                self._save_retention("youtube", post["remote_id"], points)

    def _save_retention(self, platform: str, remote_id: str, points: list) -> None:
        import json
        self.db.execute("""INSERT INTO media_retention(platform, remote_id, points_json, fetched_at) VALUES (?,?,?,?)
                           ON CONFLICT(platform, remote_id) DO UPDATE SET points_json=excluded.points_json,
                           fetched_at=excluded.fetched_at""", (platform, remote_id, json.dumps(points), iso(self.clock())))

    # --- Instagram ----------------------------------------------------------------------------------------
    def refresh_instagram(self, ig, reports: bool = True) -> None:
        try:
            ig.refresh_if_needed()
        except Exception as exc:     # noqa: BLE001 - a failed refresh is retried next time; auth errors surface below
            log.warning("Instagram token refresh failed: %s", exc)
        acc = ig.account()
        media = ig.recent_media(50)
        total_views = 0
        for m in media:
            caption = (m.get("caption") or "").strip()
            title = caption.split("\n", 1)[0][:120] or "Instagram post"
            thumb = m.get("thumbnail_url") or (m.get("media_url") if m.get("media_type") == "IMAGE" else None)
            self.save_media("instagram", m["id"], title, m.get("permalink"), thumb, m.get("timestamp"), None)
            ins = ig.media_insights(m["id"])
            views = ins.get("views")
            total_views += int(views or 0)
            self.save_media_stats(
                "instagram", m["id"], views=int(views) if views is not None else None,
                likes=int(ins.get("likes", m.get("like_count") or 0)),
                comments=int(ins.get("comments", m.get("comments_count") or 0)),
                shares=int(ins["shares"]) if "shares" in ins else None,
                saves=int(ins["saved"]) if "saved" in ins else None,
                reach=int(ins["reach"]) if "reach" in ins else None,
                watch_minutes=ins["ig_reels_video_view_total_time"] / 60000 if "ig_reels_video_view_total_time" in ins else None,
                avg_view_seconds=ins["ig_reels_avg_watch_time"] / 1000 if "ig_reels_avg_watch_time" in ins else None)
        self.save_account("instagram", acc.get("followers_count"), total_views, acc.get("media_count"))
        if not reports:
            return
        today = self.clock().astimezone(TASHKENT).replace(hour=0, minute=0, second=0, microsecond=0)
        have = {r["day"] for r in self.db.query("SELECT DISTINCT day FROM account_daily WHERE platform='instagram'")}
        for back in range(1, IG_DAYS_BACK + 1):
            start = today - timedelta(days=back)
            day = start.date().isoformat()
            if day in have and back > 3:          # data can arrive up to 48 h late: refetch the last days only
                continue
            values = ig.account_insights(start, start + timedelta(days=1))
            if values:
                self.save_daily("instagram", day, values)


    # --- Buffer fallback ----------------------------------------------------------------------------------
    def refresh_from_buffer(self, buffer, platforms: list[str]) -> None:
        """Per-post statistics of the posts that went out through Buffer, for platforms that are not connected
        directly. Buffer has no follower counts, account reach, day values or retention, and refreshes its post
        metrics about once a day; those parts of the dashboard stay empty ("—") until the platform is connected."""
        channels = buffer.channels()
        for platform in platforms:
            ids = [c["id"] for c in channels if c.get("service") == platform]
            if not ids:
                continue
            posts = buffer.sent_posts(BUFFER_POSTS, channel_ids=ids)
            total_views = 0
            for post in posts:
                rid = BUFFER_PREFIX + post["id"]
                m = buffer_metrics(post)
                text = (post.get("text") or "").strip()
                title = text.split("\n", 1)[0][:120] or ("YouTube video" if platform == "youtube" else "Instagram post")
                thumb = next((a.get("thumbnail") for a in post.get("assets") or [] if a.get("thumbnail")), None)
                self.save_media(platform, rid, title, post.get("externalLink"), thumb, post.get("sentAt"), None)
                self.save_media_stats(platform, rid, **m)
                total_views += int(m.get("views") or 0)
            if self.source(platform) == "direct":
                continue                                   # never mix: a direct account keeps its own totals
            self.save_account(platform, None, total_views, len(posts))
            days = set(json.loads(self.kv.get(BUFFER_DAYS_KEY.format(platform)) or "[]"))
            days.add(local_day(self.clock()))
            self.kv.set(BUFFER_DAYS_KEY.format(platform), json.dumps(sorted(days)))
            self.kv.set(UPDATED_KEY.format(platform), iso(self.clock()))
            self.kv.set(SOURCE_KEY.format(platform), "buffer")
            self.kv.delete(ERROR_KEY.format(platform))

    def _drop_buffer_data(self, platform: str) -> None:
        """Remove everything the Buffer fallback stored for this platform (the direct API replaces it)."""
        days = json.loads(self.kv.get(BUFFER_DAYS_KEY.format(platform)) or "[]")
        like = BUFFER_PREFIX + "%"
        with self.db.tx() as conn:
            conn.execute("DELETE FROM media_snapshots WHERE platform=? AND remote_id LIKE ?", (platform, like))
            conn.execute("DELETE FROM media_retention WHERE platform=? AND remote_id LIKE ?", (platform, like))
            conn.execute("DELETE FROM media WHERE platform=? AND remote_id LIKE ?", (platform, like))
            for day in days:
                conn.execute("DELETE FROM account_snapshots WHERE platform=? AND day=?", (platform, day))
        self.kv.delete(BUFFER_DAYS_KEY.format(platform))
        self.kv.delete(SOURCE_KEY.format(platform))


def buffer_metrics(post: dict) -> dict[str, float]:
    """Buffer post metrics -> media_snapshots columns. averageTimeWatched / totalTimeWatched come as plain counts;
    a value too large to be seconds for a short video is taken as milliseconds (Instagram reports them that way)."""
    raw: dict[str, float] = {}
    for m in post.get("metrics") or []:
        try:
            raw[m["type"]] = float(m["value"])
        except (TypeError, ValueError, KeyError):
            continue
    out: dict[str, float] = {}
    for col, key in (("views", "views"), ("likes", "likes"), ("comments", "comments"), ("shares", "shares"),
                     ("saves", "saves"), ("reach", "reach")):
        if key in raw:
            out[col] = int(raw[key])
    if "likes" not in out and "reactions" in raw:
        out["likes"] = int(raw["reactions"])
    if "views" not in out and "impressions" in raw:
        out["views"] = int(raw["impressions"])
    if "averageTimeWatched" in raw:
        avg = raw["averageTimeWatched"]
        out["avg_view_seconds"] = round(avg / 1000 if avg > 600 else avg, 1)
    if "totalTimeWatched" in raw:
        total = raw["totalTimeWatched"]
        views = out.get("views") or 0
        as_ms = total > 600 * max(1, views)             # more than 10 min a view: it must be milliseconds
        out["watch_minutes"] = round((total / 1000 if as_ms else total) / 60, 1)
    return out


def make_collector(settings, db: Database, kv: KV, clock) -> Collector:
    from ..app import instagram_stats, youtube_stats

    def buffer():
        if not settings.buffer_api_key:
            return None
        from ..reel.buffer import GraphBuffer
        return GraphBuffer(settings.buffer_api_key)    # read-only: channels and sent posts with their metrics

    return Collector(settings, db, kv, lambda: youtube_stats(settings), lambda: instagram_stats(settings), clock,
                     buffer_factory=buffer)


__all__ = ["Collector", "make_collector", "media_key", "local_day", "Path"]

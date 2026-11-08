"""Analytics fetch (fake YouTube + Instagram API clients), snapshot storage and the snapshot math."""

from datetime import date, datetime, timedelta, timezone

import pytest

from socialauto.analytics.collector import Collector, iso_duration
from socialauto.analytics.metrics import Metrics, daily_from_totals, growth, value_on
from socialauto.db import KV
from socialauto.platforms.instagram import InstagramAuthError
from socialauto.platforms.youtube import YouTubeAuthError

UTC = timezone.utc


class FakeYT:
    def __init__(self, subs=1000, views=50000):
        self.subs, self.views = subs, views
        self.reports = []
        self.error = None

    def channel(self):
        if self.error:
            raise self.error
        return {"id": "UC1", "statistics": {"subscriberCount": str(self.subs), "viewCount": str(self.views),
                                            "videoCount": "2"}, "snippet": {"title": "Facts"}}

    def recent_upload_ids(self, n=50):
        return ["yt1", "yt2"]

    def videos(self, ids, parts=""):
        return [{"id": "yt1", "snippet": {"title": "Octopus hearts", "publishedAt": "2026-11-01T14:00:00Z",
                                          "thumbnails": {}}, "statistics": {"viewCount": "900", "likeCount": "80",
                                                                            "commentCount": "9"},
                 "contentDetails": {"duration": "PT41S"}},
                {"id": "yt2", "snippet": {"title": "Honey never spoils", "publishedAt": "2026-11-03T09:00:00Z",
                                          "thumbnails": {}}, "statistics": {"viewCount": "300", "likeCount": "20",
                                                                            "commentCount": "1"},
                 "contentDetails": {"duration": "PT38S"}}]

    def report(self, **p):
        self.reports.append(p)
        if p.get("dimensions") == "day":
            return {"columnHeaders": [{"name": n} for n in ("day", "views", "estimatedMinutesWatched",
                                                             "averageViewDuration", "likes", "comments", "shares",
                                                             "subscribersGained", "subscribersLost")],
                    "rows": [["2026-11-07", 100, 50, 30, 8, 1, 2, 5, 1], ["2026-11-08", 200, 90, 31, 12, 2, 3, 7, 2]]}
        if p.get("dimensions") == "video":
            return {"columnHeaders": [{"name": n} for n in ("video", "views", "estimatedMinutesWatched",
                                                             "averageViewDuration", "averageViewPercentage", "shares")],
                    "rows": [["yt1", 900, 400, 26.6, 64.9, 12]]}
        return {"rows": [[0.0, 1.0], [0.5, 0.7], [1.0, 0.4]]}


class FakeIG:
    def __init__(self, followers=500):
        self.followers = followers
        self.error = None
        self.refreshed = 0

    def refresh_if_needed(self):
        self.refreshed += 1

    def account(self):
        if self.error:
            raise self.error
        return {"followers_count": self.followers, "media_count": 1}

    def recent_media(self, n=50):
        return [{"id": "ig1", "caption": "Octopus hearts\n#Octopus", "permalink": "https://instagram.com/reel/x",
                 "timestamp": "2026-11-01T14:00:05+0000", "media_type": "VIDEO"}]

    def media_insights(self, mid):
        return {"views": 1500, "reach": 1200, "likes": 140, "comments": 6, "shares": 20, "saved": 30,
                "ig_reels_avg_watch_time": 12500, "ig_reels_video_view_total_time": 1_800_000}

    def account_insights(self, since, until):
        return {"reach": 300, "views": 400, "likes": 30, "comments": 2, "shares": 4, "saves": 5}


@pytest.fixture
def collector(app, settings, clock):
    yt, ig = FakeYT(), FakeIG()
    for f in (settings.youtube.token_file, settings.instagram.token_file):     # "connected"
        p = settings.resolve(f)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")
    c = Collector(settings, app.db, KV(app.db), lambda: yt, lambda: ig, clock)
    return c, yt, ig


def test_nothing_is_fetched_or_shown_before_connecting(app, settings, clock):
    c = Collector(settings, app.db, KV(app.db), lambda: FakeYT(), lambda: FakeIG(), clock)
    assert c.connected() == {"youtube": False, "instagram": False}
    assert c.refresh() == []
    ov = Metrics(app.db, date(2026, 11, 9)).overview()
    assert ov["combined"] is None and ov["platforms"] == {"youtube": None, "instagram": None}


def test_refresh_stores_snapshots_and_media(app, collector):
    c, yt, ig = collector
    assert c.refresh() == []
    m = Metrics(app.db, date(2026, 11, 9))
    yt_ov, ig_ov = m.platform_overview("youtube"), m.platform_overview("instagram")
    assert yt_ov["followers"] == 1000 and yt_ov["total_views"] == 50000
    assert ig_ov["followers"] == 500 and ig_ov["total_views"] == 1500
    assert yt_ov["views_period"] == 300                         # from the Analytics day report
    assert ig.refreshed == 1                                    # token auto-refresh is attempted every time
    rows = {r["title"]: r for r in m.videos()}
    assert rows["Octopus hearts"]["youtube"]["views"] == 900
    assert rows["Octopus hearts"]["youtube"]["avg_view_pct"] == pytest.approx(64.9)
    ig_row = next(r for r in m.videos() if r["instagram"])
    assert ig_row["instagram"]["saves"] == 30 and ig_row["instagram"]["avg_view_seconds"] == 12.5
    assert ig_row["instagram"]["watch_minutes"] == 30
    assert c.updated_at("youtube") is not None


def test_our_reel_merges_both_platforms(app, collector):
    """A reel the owner scheduled in Buffer: Buffer reported its live links, so its YouTube and Instagram stats merge."""
    c, yt, ig = collector
    vid = app.store.create_video("done")
    app.store.add_script(vid, {"title": "Octopus hearts", "topic": "x"})
    app.workflow.reels.upsert(vid, base="2026-11-01-x", live_links={"youtube": "https://youtube.com/shorts/yt1",
                                                                     "instagram": "https://instagram.com/reel/x"})
    c.refresh()
    row = next(r for r in Metrics(app.db, date(2026, 11, 9)).videos() if r["youtube"] and r["instagram"])
    assert row["total_views"] == 900 + 1500
    detail = Metrics(app.db, date(2026, 11, 9)).video(row["key"])
    assert detail["retention"] == [[0.0, 1.0], [0.5, 0.7], [1.0, 0.4]]     # YouTube retention of our own reel
    assert set(detail["history"]) == {"youtube", "instagram"}


def test_daily_snapshots_build_history(app, collector, clock):
    c, yt, ig = collector
    for day, subs, followers in ((0, 1000, 500), (1, 1010, 520), (2, 1030, 525)):
        clock.now = datetime(2026, 11, 9, 8, tzinfo=UTC) + timedelta(days=day)
        yt.subs, ig.followers = subs, followers
        c.refresh()
    m = Metrics(app.db, date(2026, 11, 11))
    f = m.series("followers", date(2026, 11, 9), date(2026, 11, 11))
    assert f["youtube"] == [1000, 1010, 1030] and f["instagram"] == [500, 520, 525]
    assert f["combined"] == [1500, 1530, 1555]
    ov = m.platform_overview("youtube")
    assert ov["followers_growth"]["day"] == 20 and ov["followers_growth"]["week"] is None   # not enough history yet


def test_snapshot_math():
    snaps = [("2026-11-01", 100), ("2026-11-02", 150), ("2026-11-05", 300), ("2026-11-06", 290)]
    d = daily_from_totals(snaps)
    assert d["2026-11-02"] == 50
    assert d["2026-11-03"] == d["2026-11-04"] == d["2026-11-05"] == 50          # a gap is spread evenly
    assert d["2026-11-06"] == 0                                                 # views never go negative
    assert daily_from_totals(snaps, clip=False)["2026-11-06"] == -10            # followers may shrink
    assert value_on(snaps, "2026-11-04") == 150
    g = growth(snaps, "2026-11-06")
    assert g == {"day": -10, "week": None, "month": None}
    assert iso_duration("PT1M5S") == 65 and iso_duration("PT41S") == 41


def test_views_fall_back_to_snapshot_math_when_no_day_report(app):
    db = app.db
    for day, total in (("2026-11-01", 1000), ("2026-11-03", 1400)):
        db.execute("INSERT INTO account_snapshots(platform, day, followers, total_views, media_count, fetched_at) "
                   "VALUES ('youtube', ?, 10, ?, 1, 'x')", (day, total))
    v = Metrics(db, date(2026, 11, 3)).views_by_day("youtube", date(2026, 11, 2), date(2026, 11, 3))
    assert v == {"2026-11-02": 200, "2026-11-03": 200}


def test_engagement_rate_and_comparison(app, collector):
    c, yt, ig = collector
    c.refresh()
    m = Metrics(app.db, date(2026, 11, 9))
    ov = m.overview(30)
    # YouTube day values: (8+1+2 + 12+2+3) / 300 views
    assert ov["platforms"]["youtube"]["engagement_rate"] == pytest.approx(100 * 28 / 300, abs=0.01)
    cmp = m.comparison(30)
    assert cmp["youtube"]["followers_gained"] == 9 and cmp["instagram"]["videos"] == 1
    best = m.best_times()
    assert best["best_hour"] == 19                              # 14:00 UTC posts = 19:00 Tashkent
    assert m.top_videos(1)[0]["total_views"] == 1500


def test_reports_only_every_few_hours(app, collector, clock):
    c, yt, ig = collector
    c.refresh()
    n = len(yt.reports)
    clock.advance(minutes=30)
    c.refresh()
    assert len(yt.reports) == n                                 # quota respected: totals only
    clock.advance(hours=6)
    c.refresh()
    assert len(yt.reports) > n


def test_expired_auth_becomes_an_owner_alert(app, collector):
    c, yt, ig = collector
    yt.error = YouTubeAuthError("expired")
    ig.error = InstagramAuthError("code 190")
    alerts = c.refresh()
    assert {a[0] for a in alerts} == {"youtube", "instagram"}
    assert all("Terminalda" in a[1] for a in alerts)
    assert KV(app.db).get("analytics:youtube:error") == "auth"

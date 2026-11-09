"""Buffer fallback for the dashboard: per-post statistics of the posts that went out through Buffer while YouTube /
Instagram are not connected directly, and the hand-over to the official API once they are."""

from datetime import date

from socialauto.analytics.collector import Collector, buffer_metrics
from socialauto.analytics.metrics import Metrics
from socialauto.db import KV

from tests.test_analytics import FakeIG, FakeYT


def metric(t, v):
    return {"type": t, "name": t, "value": v, "unit": "count"}


class FakeBuffer:
    dry_run = False

    def __init__(self):
        self.calls = []

    def channels(self):
        return [{"id": "c-ig", "service": "instagram"}, {"id": "c-yt", "service": "youtube"},
                {"id": "c-li", "service": "linkedin"}]

    def sent_posts(self, limit=30, channel_ids=None):
        self.calls.append(channel_ids)
        if channel_ids == ["c-ig"]:
            return [{"id": "p1", "text": "Octopus hearts\n#octopus", "sentAt": "2026-11-01T14:00:00Z",
                     "externalLink": "https://www.instagram.com/reel/abc/", "assets": [],
                     "metrics": [metric("views", 1500), metric("likes", 140), metric("comments", 6),
                                 metric("shares", 20), metric("saves", 30), metric("reach", 1200),
                                 metric("averageTimeWatched", 12500)]}]
        if channel_ids == ["c-yt"]:
            return [{"id": "p2", "text": "Honey never spoils", "sentAt": "2026-11-03T09:00:00Z",
                     "externalLink": "https://youtube.com/shorts/xyz", "assets": [],
                     "metrics": [metric("views", 300), metric("likes", 20), metric("comments", 1),
                                 metric("averageTimeWatched", 26.5)]}]
        return []


def test_buffer_metrics_mapping():
    m = buffer_metrics({"metrics": [metric("views", 10), metric("reactions", 3), metric("averageTimeWatched", 9000),
                                    metric("totalTimeWatched", 90000), {"type": "views"}]})
    assert m == {"views": 10, "likes": 3, "avg_view_seconds": 9.0, "watch_minutes": 1.5}
    assert buffer_metrics({"metrics": [metric("averageTimeWatched", 26.5)]}) == {"avg_view_seconds": 26.5}


def test_dashboard_uses_buffer_when_not_connected(app, settings, clock):
    kv = KV(app.db)
    buf = FakeBuffer()
    c = Collector(settings, app.db, kv, lambda: FakeYT(), lambda: FakeIG(), clock, buffer_factory=lambda: buf)
    assert c.refresh() == []
    assert buf.calls == [["c-yt"], ["c-ig"]]                            # LinkedIn is never read for the dashboard
    assert c.source("instagram") == "buffer" and c.source("youtube") == "buffer"
    m = Metrics(app.db, date(2026, 11, 9))
    ov = m.overview()
    assert ov["platforms"]["instagram"]["followers"] is None            # Buffer has no follower counts: never faked
    assert ov["platforms"]["instagram"]["total_views"] == 1500
    vids = {v["title"]: v for v in m.videos()}
    assert vids["Octopus hearts"]["instagram"]["avg_view_seconds"] == 12.5
    assert vids["Octopus hearts"]["total_saves"] == 30
    assert m.top_videos(1)[0]["title"] == "Octopus hearts"
    assert m.best_times()["hours"]


def test_dry_run_buffer_or_no_key_reads_nothing(app, settings, clock):
    class Dry(FakeBuffer):
        dry_run = True
    for factory in (lambda: Dry(), lambda: None):
        c = Collector(settings, app.db, KV(app.db), None, None, clock, buffer_factory=factory)
        c.refresh()
        assert c.source("instagram") is None
    assert Metrics(app.db, date(2026, 11, 9)).overview()["combined"] is None


def test_direct_connection_replaces_buffer_data(app, settings, clock):
    kv = KV(app.db)
    c = Collector(settings, app.db, kv, lambda: FakeYT(), lambda: FakeIG(), clock, buffer_factory=FakeBuffer)
    c.refresh()
    p = settings.resolve(settings.instagram.token_file)                  # Instagram gets connected
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}")
    c.refresh()
    assert c.source("instagram") == "direct" and c.source("youtube") == "buffer"
    assert not app.db.query("SELECT 1 FROM media WHERE platform='instagram' AND remote_id LIKE 'buffer:%'")
    ov = Metrics(app.db, date(2026, 11, 9)).overview()
    assert ov["platforms"]["instagram"]["followers"] == 500             # the real API's numbers, no Buffer mix


def test_buffer_post_is_matched_to_our_reel(app, settings, clock):
    vid = app.store.create_video("done", "Octopus hearts")
    app.db.execute("INSERT INTO reels(video_id, base, drafts_json, updated_at) VALUES (?,?,?,?)",
                   (vid, "2026-11-01-octopus", '{"instagram": "p1"}', "2026-11-01T00:00:00Z"))
    c = Collector(settings, app.db, KV(app.db), None, None, clock, buffer_factory=FakeBuffer)
    c.refresh()
    row = app.db.one("SELECT video_id FROM media WHERE remote_id='buffer:p1'")
    assert row["video_id"] == vid

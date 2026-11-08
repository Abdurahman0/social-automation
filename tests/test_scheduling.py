"""Publish-date calendar (DST-safe), free dates, automatic research, restart recovery, Claude limit handling."""

from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from conftest import outbox_kinds, run_all_jobs

from socialauto import slots
from socialauto.claude_client import ClaudeUsageLimit
from socialauto.config import ScheduleConfig
from socialauto.store import DRAFTING, RESEARCHING, TOPIC_PENDING

UTC = timezone.utc


def test_tashkent_date_is_19_local():
    cfg = ScheduleConfig()
    s = slots.slots_between(cfg, datetime(2026, 11, 9, 0, 0, tzinfo=UTC), datetime(2026, 11, 11, 0, 0, tzinfo=UTC))
    assert [x.astimezone(ZoneInfo("Asia/Tashkent")).hour for x in s] == [19, 19]
    assert slots.describe(cfg, s[0]) == "9-noyabr, 19:00"


def test_dst_zone_keeps_wall_clock_time():
    cfg = ScheduleConfig(timezone="America/New_York", slot_times=("19:00",))
    s = slots.slots_between(cfg, datetime(2026, 10, 30, tzinfo=UTC), datetime(2026, 11, 4, tzinfo=UTC))
    local = [x.astimezone(ZoneInfo("America/New_York")) for x in s]
    assert all(t.hour == 19 for t in local) and len({x.utcoffset() for x in local}) == 2


def test_next_free_date_skips_taken_and_too_close():
    cfg = ScheduleConfig(min_lead_minutes=30)
    now = datetime(2026, 11, 9, 13, 45, tzinfo=UTC)
    first = slots.next_free_slot(cfg, now, set())
    assert first == datetime(2026, 11, 10, 14, 0, tzinfo=UTC)
    assert slots.next_free_slot(cfg, now, {first}) == datetime(2026, 11, 11, 14, 0, tzinfo=UTC)


def test_automatic_research_only_when_needed(app):
    app.workflow.tick()
    assert [v["status"] for v in app.store.videos()] == [RESEARCHING]
    app.workflow.tick()
    assert len(app.store.videos()) == 1
    run_all_jobs(app)
    assert app.store.videos()[0]["status"] == TOPIC_PENDING
    app.workflow.tick()
    assert len(app.store.videos()) == 1


def test_no_research_when_the_date_is_far(settings, fake_claude, transcriber, clock):
    from socialauto.app import build_app
    s = replace(settings, schedule=replace(settings.schedule, propose_lead_hours=1))
    app = build_app(s, claude=fake_claude, transcriber=transcriber, clock=clock)
    app.workflow.tick()
    assert app.store.videos() == []


def test_restart_recovery_resumes_lost_steps(app):
    vid = app.store.create_video(DRAFTING, slot_at=app.workflow.next_slot())
    app.workflow.reels.upsert(vid, base="2026-11-09-test", topics=[{"title": "Suv", "facts": []}], topic_index=0)
    app.jobs.enqueue("research", {"video_id": 999}, dedupe_key="x")
    assert app.jobs.claim_next()                                    # left "running" by a crash
    done = app.workflow.recover()
    assert any("re-queued" in d for d in done) and any("drafting resumed" in d for d in done)
    run_all_jobs(app)
    assert app.store.video(vid)["status"] == "script_pending"


def test_claude_limit_pauses_and_tells_owner_once(app, fake_claude, clock):
    vid = app.workflow.request_new()
    reset = "You've hit your 5-hour limit · resets 11:10pm (Asia/Tashkent)"
    fake_claude.error = ClaudeUsageLimit(reset, datetime(2026, 11, 9, 18, 10, tzinfo=UTC))
    app.budget.limit_hit(reset)
    run_all_jobs(app)
    limits = [i for i in app.outbox.pending(50) if i.kind == "limit"]
    assert len(limits) == 1 and "23:10" in limits[0].payload["text"]
    assert app.jobs.active(("research",))[0]["attempts"] == 0
    clock.now = datetime(2026, 11, 9, 18, 20, tzinfo=UTC)
    run_all_jobs(app)
    assert app.store.video(vid)["status"] == TOPIC_PENDING
    app.budget.note_success()
    assert app.budget.take_resume_notice() and app.budget.take_resume_notice() is None
    assert outbox_kinds(app).count("limit") == 1


def test_usage_report_in_uzbek(app):
    app.budget.record("propose-reel-script", 42.0, {"input_tokens": 1000, "output_tokens": 500})
    assert "Bugun: 1 ta chaqiruv" in app.budget.report()

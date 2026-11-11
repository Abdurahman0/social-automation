"""Task 10: every error reaches the owner's Telegram (plain Uzbek, no spam), the give-up message has «Qayta urinish»,
research with zero usable topics is explained, /new while paused, stuck reels do not block /new, the Telegram error
handler, the watchdog, /status, the automatic update and the startup checks."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest
from conftest import run_all_jobs, topic

from socialauto import errors, runner
from socialauto.claude_client import ClaudeError
from socialauto.errors import NoTopicsError, explain, redact, short
from socialauto.scheduler import PAUSED_KEY, Scheduler
from socialauto.store import DRAFTING, FAILED, RESEARCHING, TOPIC_PENDING
from socialauto.telegram_bot import TelegramBot, status_text


def press(bot, data, user=111):
    return asyncio.run(bot.handle_button(user, data))


def error_items(app):
    return [i for i in app.outbox.pending(300) if i.kind == "error"]


def all_texts(app):
    return [i.payload.get("text", "") for i in error_items(app)]


# --- plain-Uzbek reasons and secrets --------------------------------------------------------------------------------

def test_explain_maps_common_causes():
    import requests
    assert explain(requests.ConnectionError("Failed to establish a new connection: Name resolution"))[0] == "offline"
    assert explain(ClaudeError("research-topics: timed out after 900s"))[0] == "timeout"
    assert explain(ClaudeError("research-topics: could not start Claude Code: [Errno 2] No such file"))[0] == "claude_missing"
    assert explain(ClaudeError("WebSearch tool failed: 503"))[0] == "claude_websearch"
    assert explain(RuntimeError("ffmpeg not found on PATH"))[0] == "ffmpeg_missing"
    assert explain(OSError(28, "No space left on device"))[0] == "disk_full"
    assert explain(RuntimeError("no licensed real footage found for part hook (water)"))[0] == "broll_none"
    assert explain(RuntimeError("! [rejected] main -> main (non-fast-forward)"))[0] == "push_rejected"
    assert explain(NoTopicsError("topilgan 6 ta mavzudan 6 tasi suv yo'nalishiga mos kelmadi"))[0] == "no_topics"
    code, reason = explain(ValueError("something odd happened in /home/x/project/socialauto/thing.py line 3"))
    assert code.startswith("other:") and "/home" not in reason and "thing.py" in reason


def test_secrets_never_reach_the_message():
    token = "123456789:" + "A" * 35
    text = redact(f"bot{token}/sendMessage failed; Authorization: Bearer abcdefghijklmnopqrstuv ghp_" + "x" * 30
                  + " https://user:pw@github.com/a/b?access_token=zzz")
    assert token not in text and "abcdefghijklmnopqrstuv" not in text and "ghp_" not in text
    assert "pw@" not in text and "zzz" not in text
    assert len(short("x " * 400)) <= 160


# --- jobs: first failure, no spam, give-up with «Qayta urinish» -----------------------------------------------------

def test_first_failure_is_told_once_with_the_retry_time(app, fake_claude, clock):
    vid = app.workflow.request_new("Toshkentda ichimlik suvi")
    fake_claude.error = ClaudeError("research-topics: timed out after 900s")
    run_all_jobs(app)
    texts = all_texts(app)
    assert len(texts) == 1
    t = texts[0]
    assert "«Mavzu qidirish»" in t and "«Toshkentda ichimlik suvi»" in t and "vaqt tugadi" in t
    assert "daqiqadan keyin o'zim qayta urinaman" in t
    assert app.store.video(vid)["status"] == RESEARCHING
    # the same error on the next retry: no second message
    clock.advance(minutes=5)
    fake_claude.error = ClaudeError("research-topics: timed out after 900s")
    run_all_jobs(app)
    assert len(all_texts(app)) == 1
    # a different error on a later retry: one more message
    clock.advance(minutes=10)
    fake_claude.error = ClaudeError("could not start Claude Code: No such file or directory: 'claude'")
    run_all_jobs(app)
    assert len(all_texts(app)) == 2 and "Claude Code" in all_texts(app)[1]
    for t in all_texts(app):                                    # never raw errors, ids or class names
        assert "ClaudeError" not in t and "Traceback" not in t and "{" not in t


def test_give_up_message_and_retry_button_re_enqueues(app, clock, monkeypatch):
    wf = app.workflow
    vid = wf.request_new()
    calls = {"n": 0}

    def broken(*a, **k):
        calls["n"] += 1
        raise RuntimeError("weird failure number 7")
    monkeypatch.setattr(wf.reel_writer, "research", broken)
    for _ in range(8):
        run_all_jobs(app)
        clock.advance(hours=2)
    assert calls["n"] == 5
    assert app.store.video(vid)["status"] == FAILED and app.store.video(vid)["last_error"]
    give_up = [i for i in error_items(app) if i.payload.get("buttons")]
    assert len(give_up) == 1
    text, buttons = give_up[0].payload["text"], give_up[0].payload["buttons"]
    assert "❌ «Mavzu qidirish» to'xtatildi" in text and "weird failure" in text and "5 marta" in text
    labels = [b[0] for row in buttons for b in row]
    assert labels == ["🔄 Qayta urinish", "🔎 Boshqa mavzu"]
    assert len(all_texts(app)) == 2                     # one first-failure message + the give-up, nothing more
    retry = buttons[0][0][1]
    monkeypatch.undo()
    bot = TelegramBot(app)
    ok, msg = press(bot, retry)
    assert ok and "Qayta urinyapman" in msg
    assert app.store.video(vid)["status"] == RESEARCHING
    assert not press(bot, retry)[0]                      # a used button does nothing twice
    assert run_all_jobs(app) == ["research"]
    assert app.store.video(vid)["status"] == TOPIC_PENDING


def test_render_give_up_keeps_the_reel_visible_with_its_error(app, clock):
    from socialauto.jobs import Job
    wf = app.workflow
    vid = app.store.create_video("rendering", "Suv", slot_at=wf.next_slot())
    app.store.update_video(vid, title="Suv quvurlari")
    jid = app.jobs.enqueue("render", {"video_id": vid, "voice_id": 1}, max_attempts=1)
    job = app.jobs.claim_next(now=clock().isoformat())
    assert job.id == jid
    wf._failed(job, RuntimeError("ffmpeg not found on PATH"))
    v = app.store.video(vid)
    assert v["status"] == FAILED and "ffmpeg" in v["last_error"]
    item = [i for i in error_items(app) if i.payload.get("buttons")][0]
    assert "«Video yig'ish» to'xtatildi" in item.payload["text"] and "«Suv quvurlari»" in item.payload["text"]
    assert [b[0] for row in item.payload["buttons"] for b in row] == ["🔄 Qayta urinish"]   # no «Boshqa mavzu» here
    assert isinstance(job, Job)


# --- research: zero usable topics -----------------------------------------------------------------------------------

def test_zero_topics_is_explained_and_other_topic_button_works(app, fake_claude):
    wf = app.workflow
    fake_claude.topics = [topic("Futbol chempionati"), topic("Yangi telefonlar"), topic("Kino yangiliklari"),
                          topic("Avtomobil narxlari"), topic("Ob-havo"), topic("Moda")]
    vid = wf.request_new()
    run_all_jobs(app)
    assert app.store.video(vid)["status"] == FAILED                       # no five pointless retries
    item = [i for i in error_items(app) if i.payload.get("buttons")][0]
    text = item.payload["text"]
    assert text.startswith("🔎 Mavzu topilmadi") and "suv / oqova suv yo'nalishiga mos kelmadi" in text
    assert "topilgan 12 ta mavzudan 12 tasi" in text                       # both Claude rounds counted
    other = item.payload["buttons"][1][0][1]
    fake_claude.topics = [topic("Toshkentda suv yo'qotilishi 40%"), topic("Oqova suvni qayta ishlash"),
                          topic("Orol dengizi va chang bo'ronlari")]
    ok, msg = press(TelegramBot(app), other)
    assert ok and "Boshqa mavzular" in msg
    assert run_all_jobs(app) == ["research"] and app.store.video(vid)["status"] == TOPIC_PENDING


def test_topics_without_sources_are_explained(app, fake_claude):
    fake_claude.topics = [topic("Suv tarifi", url="kun.uz"), topic("Suv quvurlari", url="")]
    app.workflow.request_new()
    run_all_jobs(app)
    assert any("manbasi" in t for t in all_texts(app))


# --- /new <idea> ----------------------------------------------------------------------------------------------------

def test_new_with_an_idea_researches_that_idea(app, fake_claude):
    bot = TelegramBot(app)
    # an earlier /new with the same idea that stopped: the idea itself is never "already covered"
    old = app.store.create_video(FAILED, "Toshkentda ichimlik suvi")
    del old
    fake_claude.topics = [topic("Toshkentda ichimlik suvi sifati: 2026 tahlillari"),
                          topic("Toshkentda ichimlik suvi quvurlari eskirgan"),
                          topic("Toshkentda ichimlik suvi tarifi oshdi")]
    reply, markup = asyncio.run(bot.new_command(111, "Toshkentda   ichimlik suvi"))
    assert reply.startswith("🔎 «Toshkentda ichimlik suvi» bo'yicha mavzular qidirilyapti") and "3–10 daqiqa" in reply
    assert markup is None
    assert run_all_jobs(app) == ["research"]
    task, prompt = [c for c in fake_claude.calls if c[0].startswith("research")][0]
    assert "«Toshkentda ichimlik suvi»" in prompt and "MAIN CONSTRAINT" in prompt and "idea_note" in prompt
    vid = app.store.videos([TOPIC_PENDING])[0]["id"]
    reel = app.workflow.reels.get(vid)
    assert len(reel["topics"]) == 3 and all("Toshkentda ichimlik suvi" in t["title"] for t in reel["topics"])
    assert reel["idea"] == "Toshkentda ichimlik suvi"
    from socialauto.telegram_bot import topic_message
    text = topic_message(reel["topics"], reel["insight"], True, reel["idea"], "Hammasi Toshkent suvi haqida")
    assert "«Toshkentda ichimlik suvi» bo'yicha mavzular tayyor" in text and "Hammasi Toshkent suvi haqida" in text
    md = open(reel["research_file"], encoding="utf-8").read()
    assert "**G'oya:** Toshkentda ichimlik suvi" in md
    # «Boshqa mavzular» keeps the idea
    token = app.store.pending_approval(vid, "topic")["id"]
    assert press(bot, f"t:m:{token}")[0]
    run_all_jobs(app)
    prompts = [p for t, p in fake_claude.calls if t.startswith("research")]
    assert "«Toshkentda ichimlik suvi»" in prompts[-1]


def test_new_alone_asks_then_skip_lets_the_bot_pick(app, fake_claude):
    bot = TelegramBot(app)
    reply, markup = asyncio.run(bot.new_command(111, ""))
    assert "Qaysi g'oya bo'yicha?" in reply and "/skip" in reply
    assert markup.inline_keyboard[0][0].text == "🎲 Bot o'zi tanlasin"
    assert app.store.videos([RESEARCHING]) == []
    ok, msg = press(bot, "nw:auto")                       # the same as /skip
    assert ok and msg.startswith("🔎 Bot o'zi yangi mavzular qidiryapti")
    run_all_jobs(app)
    prompt = [p for t, p in fake_claude.calls if t.startswith("research")][0]
    assert "MAIN CONSTRAINT" not in prompt and "LATEST Uzbekistan water" in prompt     # today's behaviour


def test_new_then_the_idea_as_the_next_message(app, fake_claude):
    bot = TelegramBot(app)
    asyncio.run(bot.new_command(111, ""))
    reply = asyncio.run(bot.handle_text(111, "Orol dengizi"))
    assert reply.startswith("🔎 «Orol dengizi» bo'yicha")
    run_all_jobs(app)
    assert "«Orol dengizi»" in [p for t, p in fake_claude.calls if t.startswith("research")][0]
    assert asyncio.run(bot.handle_text(111, "salom")) == "Buyruqlar: /help"     # asked only once


def test_cli_new_runs_the_research(app, settings, fake_claude, monkeypatch, capsys):
    from socialauto import __main__ as cli
    import socialauto.app as app_mod
    monkeypatch.setattr(app_mod, "build_app", lambda s: app)
    assert cli.cmd_new(settings, "Toshkentda ichimlik suvi", run_now=True) == 0
    out = capsys.readouterr().out
    assert "research queued about: Toshkentda ichimlik suvi" in out and "1. " in out and "topic_choice" in out


def test_paused_new_says_so(app):
    app.kv.set(PAUSED_KEY, True)
    bot = TelegramBot(app)
    reply, _ = asyncio.run(bot.new_command(111, "Suv"))
    assert reply.startswith("⏸ Avtomatik ish to'xtatilgan — /resume bosing")
    assert app.store.videos([RESEARCHING]) == []


def test_stuck_research_does_not_block_new(app):
    wf = app.workflow
    stuck = app.store.create_video(RESEARCHING, "eski g'oya")          # its job was lost
    res = wf.start_research("Yangi g'oya suv")
    assert res.status == "started" and res.video_id != stuck
    assert app.store.video(stuck)["status"] == FAILED
    # a research that is really alive blocks
    again = wf.start_research("Boshqa")
    assert again.status == "busy_research" and again.idea == "Yangi g'oya suv"
    reply = asyncio.run(TelegramBot(app).new_reply("Boshqa"))
    assert "allaqachon ketyapti" in reply and "«Yangi g'oya suv»" in reply


def test_research_waiting_to_retry_gives_way_to_a_new_idea(app, fake_claude):
    wf = app.workflow
    first = wf.request_new("Birinchi g'oya")
    fake_claude.error = ClaudeError("boom")
    run_all_jobs(app)                                      # failed once, waits to retry
    res = wf.start_research("Ikkinchi g'oya")
    assert res.status == "started"
    assert app.store.video(first)["status"] == FAILED
    assert not app.jobs.for_video(first)


def test_stuck_drafting_is_resumed_and_new_starts(app):
    wf = app.workflow
    vid = app.store.create_video(DRAFTING, "Suv")
    wf.reels.upsert(vid, base="2026-11-10-suv", topics=[topic("Suv")], topic_index=0)
    res = wf.start_research(None)
    assert res.status == "started"
    assert [j["kind"] for j in app.jobs.for_video(vid)] == ["propose"]
    assert wf.start_research(None).status == "busy_research"


# --- Telegram error handler, /status ---------------------------------------------------------------------------------

class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text, kw))


def test_telegram_handler_error_answers_in_uzbek(app):
    bot = TelegramBot(app)
    bot.bot = FakeBot()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=111), effective_chat=SimpleNamespace(id=111),
                             callback_query=None)
    text = asyncio.run(bot.report_handler_error(update, KeyError("approval")))
    assert text.startswith("⚠️ Buyruqni bajarib bo'lmadi") and bot.bot.sent[0][1] == text
    stranger = SimpleNamespace(effective_user=SimpleNamespace(id=5), effective_chat=SimpleNamespace(id=5),
                               callback_query=None)
    assert asyncio.run(bot.report_handler_error(stranger, KeyError("x"))) is None
    assert len(bot.bot.sent) == 1


def test_error_message_is_delivered_with_buttons(app):
    bot = TelegramBot(app)
    bot.bot = FakeBot()
    app.outbox.add("error", text="❌ test", buttons=[[["🔄 Qayta urinish", "er:r:1"]]])
    asyncio.run(bot.deliver_outbox())
    chat, text, kw = bot.bot.sent[0]
    assert text == "❌ test" and kw["reply_markup"].inline_keyboard[0][0].callback_data == "er:r:1"


def test_status_shows_the_last_error_and_retry_count(app, fake_claude, clock):
    assert "Xatolar yo'q" in status_text(app, False)
    app.workflow.request_new("Suv")
    fake_claude.error = ClaudeError("research-topics: timed out after 900s")
    run_all_jobs(app)
    text = status_text(app, False)
    assert "Oxirgi xato: Mavzu qidirish" in text and "(Toshkent)" in text and "vaqt tugadi" in text
    assert "Qayta urinishni kutayotgan ishlar: 1" in text


# --- network: one «internet yo'q», one «qayta ulandi» ----------------------------------------------------------------

def test_offline_is_one_message_then_one_back_online(app, fake_claude, clock):
    import requests
    app.workflow.request_new()
    fake_claude.error = requests.ConnectionError("Failed to establish a new connection")
    run_all_jobs(app)
    clock.advance(minutes=5)
    fake_claude.error = requests.ConnectionError("Failed to establish a new connection")
    run_all_jobs(app)
    assert all_texts(app) == [all_texts(app)[0]] and "Internet yo'q" in all_texts(app)[0]
    clock.advance(minutes=10)
    run_all_jobs(app)                                     # it works again
    texts = all_texts(app)
    assert len(texts) == 2 and texts[1].startswith("✅ Internet qayta ulandi")


# --- the watchdog -----------------------------------------------------------------------------------------------------

def test_watchdog_reports_and_requeues_a_stuck_job(app, monkeypatch):
    sched = Scheduler(app, lambda: None)
    sched.timeouts["research"] = 0.02                    # minutes (~1 s)
    vid = app.workflow.request_new("Suv")
    release = {"go": False}

    def slow(p):
        while not release["go"]:
            time.sleep(0.05)
    monkeypatch.setattr(type(app.workflow), "handlers", lambda self: {"research": slow})
    job = app.jobs.claim_next(now=app.clock().isoformat())

    async def go():
        await sched.run_one(job)
        assert sched.busy_kinds() == ("research",)       # no second research while the stuck one lives
        release["go"] = True
        await asyncio.sleep(0.3)
        assert sched.busy_kinds() == ()
    asyncio.run(go())
    texts = all_texts(app)
    assert len(texts) == 1 and texts[0].startswith("⏳ «Mavzu qidirish»") and "tugamadi" in texts[0]
    assert "«Suv»" in texts[0]
    row = app.jobs.get(job.id)
    assert row["status"] == "pending"                    # re-queued; the late finish did not mark it done
    assert app.store.video(vid)["status"] == RESEARCHING


def test_orphan_running_row_is_requeued(app, clock):
    sched = Scheduler(app, lambda: None)
    app.workflow.request_new()
    job = app.jobs.claim_next(now=clock().isoformat())
    app.db.execute("UPDATE jobs SET updated_at=? WHERE id=?", ((clock() - timedelta(hours=1)).isoformat(), job.id))
    assert sched.check_orphans() == 1
    assert app.jobs.get(job.id)["status"] == "pending"
    assert any("tugamadi" in t for t in all_texts(app))


# --- bot-level problems: scheduler, statistics, auto-update, startup checks -------------------------------------------

def test_periodic_problem_is_told_once_until_fixed(app):
    rep = app.workflow.reporter
    assert rep.problem("analytics", RuntimeError("Buffer 500"), text="⚠️ «Statistika» yangilanmadi")
    assert not rep.problem("analytics", RuntimeError("Buffer 500"), text="⚠️ «Statistika» yangilanmadi")
    rep.resolved("analytics")
    assert rep.problem("analytics", RuntimeError("Buffer 500"), text="⚠️ «Statistika» yangilanmadi")


def test_scheduler_loop_crash_reaches_the_owner(app, monkeypatch):
    sched = Scheduler(app, lambda: None)
    stop = asyncio.Event()

    async def deliver():
        pass
    sched.deliver = deliver
    monkeypatch.setattr(app.workflow, "tick", lambda: (_ for _ in ()).throw(RuntimeError("database is locked")))
    import socialauto.scheduler as sm
    monkeypatch.setattr(sm, "TICK_SECONDS", 0.01)

    async def go():
        task = asyncio.create_task(sched._jobs(stop))
        await asyncio.sleep(0.2)
        stop.set()
        await task
    asyncio.run(go())
    texts = all_texts(app)
    assert len(texts) == 1 and "Bot ishi (navbat)" in texts[0] and "database is locked" in texts[0]


class FakeUpdater:
    def __init__(self, status, apply=None):
        self.st, self.ap, self.applied = status, apply or {"ok": True, "updated": 3}, 0

    def status(self, fetch=True, force=False):
        return self.st

    def apply(self):
        self.applied += 1
        return self.ap


def test_auto_update_installs_and_reports_failures_once(app):
    ok = Scheduler(app, lambda: None, updater=FakeUpdater({"available": True, "can_update": True, "behind": 2}))
    assert ok.check_update()["ok"] and ok.updater.applied == 1 and all_texts(app) == []
    bad = Scheduler(app, lambda: None, updater=FakeUpdater({"available": True, "can_update": False, "behind": 2,
                                                            "reason": "local_changes"}))
    assert not bad.check_update()["ok"] and bad.updater.applied == 0
    bad.check_update()
    texts = all_texts(app)
    assert len(texts) == 1 and "Avtomatik yangilanish" in texts[0] and "qo'lda o'zgartirilgan" in texts[0]
    offline = Scheduler(app, lambda: None, updater=FakeUpdater({"available": False, "reason": "offline"}))
    offline.check_update()
    assert len(all_texts(app)) == 1


def test_startup_checks_alert_once(app, monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda b: None)
    failing = runner.startup_checks(app)
    assert "ffmpeg" in failing and "model" in failing
    n = len(all_texts(app))
    assert n == len(failing) and any("ffmpeg o'rnatilmagan" in t for t in all_texts(app))
    runner.startup_checks(app)
    assert len(all_texts(app)) == n                       # not again at the next start


def test_db_migration_adds_the_idea_columns(app):
    cols = {r[1] for r in app.db.query("PRAGMA table_info(reels)")}
    assert {"idea", "idea_note"} <= cols


@pytest.mark.parametrize("kind", sorted(errors.STEP_UZ))
def test_every_step_has_an_uzbek_name(kind):
    assert errors.STEP_UZ[kind][0].isupper()


def test_error_payloads_are_plain_json(app, fake_claude):
    app.workflow.request_new()
    fake_claude.error = ClaudeError("x")
    run_all_jobs(app)
    for i in error_items(app):
        json.dumps(i.payload)


# --- the website: a stopped reel stays visible with its reason ---------------------------------------------------------

def test_stopped_reel_is_visible_on_the_website_with_its_reason(app, settings, clock, fake_claude):
    from fastapi.testclient import TestClient

    from socialauto.web.server import create_app
    fake_claude.topics = [topic("Futbol"), topic("Kino")]
    vid = app.workflow.request_new("Toshkentda ichimlik suvi")
    run_all_jobs(app)
    assert app.store.video(vid)["status"] == FAILED
    old = app.store.create_video(FAILED, "")
    app.store.update_video(old, last_error="ValueError: research found no new water/wastewater topic")
    client = TestClient(create_app(settings, app.db, None, clock))
    assert client.post("/api/login", json={"password": "secret-pass"}).status_code == 200
    cols = {c["key"]: c["items"] for c in client.get("/api/pipeline").json()["columns"]}
    items = cols["research"]
    mine = [i for i in items if i["title"] == "G'oya: Toshkentda ichimlik suvi"][0]
    assert mine["who"] == "Siz" and "mos kelmadi" in mine["error"]
    raw = [i for i in items if i["title"] == "Yangi tadqiqot"][0]
    assert "ValueError" not in raw["error"]                       # older raw errors are shown in plain words
    detail = client.get(f"/api/reels/{mine['key']}").json()
    assert detail["error"] and detail["idea"] == "Toshkentda ichimlik suvi" and detail["stage_key"] == "research"
    body = json.dumps(client.get("/api/pipeline").json())
    assert "Traceback" not in body and "video_id" not in body


def test_a_stopped_research_is_not_restarted_automatically_in_a_loop(app, fake_claude, clock):
    fake_claude.topics = [topic("Futbol")]
    app.workflow.request_new()
    run_all_jobs(app)
    n = len(app.store.videos(limit=50))
    app.workflow.ensure_pipeline()
    assert len(app.store.videos(limit=50)) == n         # waits for the owner's button


def test_ensure_pipeline_still_starts_when_nothing_failed(app, clock):
    clock.advance(days=30)
    app.workflow.ensure_pipeline()
    assert app.store.videos([RESEARCHING])


def test_a_network_blip_while_online_is_not_internet_down(app, fake_claude):
    import requests
    app.workflow.reporter.online = lambda: True
    app.workflow.request_new("Suv")
    fake_claude.error = requests.ConnectionError("Connection reset by peer")
    run_all_jobs(app)
    texts = all_texts(app)
    assert len(texts) == 1 and "Internet yo'q" not in texts[0] and "internet" in texts[0]
    assert not app.workflow.reporter.net_down()
    assert not app.workflow.reporter.problem("scheduler", requests.ConnectionError("reset"))
    assert len(all_texts(app)) == 1

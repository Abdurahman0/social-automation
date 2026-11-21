"""The owner's own video (A-roll): after the voice is split into the 8 parts, the bot asks which parts get the owner's
clips, takes them one by one, and never replaces them with stock B-roll."""

import asyncio
import shutil
import subprocess
from dataclasses import replace

import pytest
from conftest import run_all_jobs

from socialauto.reel import broll as broll_mod
from socialauto.store import AROLL_PENDING, RENDERING, SCRIPT_PENDING, VIDEO_PENDING, VOICE_WAITING
from socialauto.telegram_bot import TelegramBot, aroll_keyboard, aroll_message
from socialauto.workflow import OWNER_PROVIDER


@pytest.fixture
def settings(settings):
    return replace(settings, reel=replace(settings.reel, ask_aroll=True))


@pytest.fixture(scope="module")
def owner_clip(tmp_path_factory):
    out = tmp_path_factory.mktemp("aroll") / "my_clip.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=540x960:rate=30",
                    "-t", "2", "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


def press(bot, data):
    return asyncio.run(bot.handle_button(111, data))


def voice_in(app, long_voice) -> int:
    bot, wf = TelegramBot(app), app.workflow
    vid = wf.request_new()
    run_all_jobs(app)
    press(bot, f"t:0:{app.store.pending_approval(vid, 'topic')['id']}")
    run_all_jobs(app)
    assert app.store.video(vid)["status"] == SCRIPT_PENDING
    press(bot, f"s:a:{app.store.pending_approval(vid, 'script')['id']}")
    assert app.store.video(vid)["status"] == VOICE_WAITING
    wf.route_voice(wf.save_raw_voice(long_voice, "voice", ".wav"))
    assert run_all_jobs(app) == ["process_voice"]                     # no render before the owner answers
    return vid


def test_owner_picks_parts_sends_clips_and_they_survive_new_broll(app, long_voice, owner_clip):
    bot, wf = TelegramBot(app), app.workflow
    vid = voice_in(app, long_voice)
    assert app.store.video(vid)["status"] == AROLL_PENDING
    assert "aroll_choice" in [i.kind for i in app.outbox.pending(300)]
    token = app.store.pending_approval(vid, "aroll")["id"]
    state = wf.aroll_state(vid)
    assert [s["part"] for s in state["spans"]][3] == "loop1" and state["spans"][0]["start"] == 0
    text = aroll_message("T", app.store.script(vid), state)
    assert "Ochiq savol 1" in text and "8 qismga" in text and "{" not in text
    assert not press(bot, f"ar:d:0:{token}")[0]                       # nothing ticked yet
    assert press(bot, f"ar:t:3:{token}")[0] and press(bot, f"ar:t:5:{token}")[0]
    assert press(bot, f"ar:t:5:{token}")[0]                           # untick
    assert press(bot, f"ar:t:1:{token}")[0]
    kb = aroll_keyboard(wf.aroll_state(vid), token)
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert "✅ 2. Kirish" in labels and "✅ 4. Ochiq savol 1" in labels and "⬜ 6. Ochiq savol 2" in labels
    assert all(len(b.callback_data) <= 64 for row in kb.inline_keyboard for b in row)
    ok, msg = press(bot, f"ar:d:0:{token}")
    assert ok and "«Kirish» qismi uchun videoni yuboring" in msg
    assert not press(bot, f"ar:t:2:{token}")[0]                       # the choice is closed

    async def dl(dest):
        shutil.copyfile(owner_clip, dest)
    reply = asyncio.run(bot.handle_aroll(owner_clip.stat().st_size, "my_clip.mp4", dl))
    assert "«Kirish» uchun videongiz qabul qilindi" in reply and "«Ochiq savol 1» qismi" in reply
    assert app.store.video(vid)["status"] == AROLL_PENDING
    ok, msg = press(bot, f"ar:s:{vid}")                               # loop1: stock B-roll after all
    assert ok and "tayyorlanmoqda" in msg and app.store.video(vid)["status"] == RENDERING
    assert not press(bot, f"ar:s:{vid}")[0]
    assert run_all_jobs(app) == ["render"]
    assert app.store.video(vid)["status"] == VIDEO_PENDING
    work = wf.places.work(wf.reels.get(vid)["base"])
    clips = broll_mod.load_sources(work)
    assert len(clips) == 8
    lead = next(c for c in clips if c.part == "lead")
    assert lead.provider == OWNER_PROVIDER and lead.file == "broll/02-lead.mp4" and (work / lead.file).exists()
    assert sum(c.provider == OWNER_PROVIDER for c in clips) == 1
    assert "Egasining o'z videosi" in (work / "SOURCES.md").read_text(encoding="utf-8")
    assert "broll/02-lead.mp4" in app.workflow.reel_renderer.calls[-1]["clips"]
    # «Yangi B-roll» replaces the stock clips only
    token = app.store.pending_approval(vid, "video")["id"]
    assert press(bot, f"v:g:{token}")[0]
    run_all_jobs(app)
    lead2 = next(c for c in broll_mod.load_sources(work) if c.part == "lead")
    assert lead2.provider == OWNER_PROVIDER and (work / lead2.file).read_bytes() == owner_clip.read_bytes()


def test_all_broll_renders_at_once(app, long_voice):
    bot = TelegramBot(app)
    vid = voice_in(app, long_voice)
    token = app.store.pending_approval(vid, "aroll")["id"]
    ok, msg = press(bot, f"ar:n:0:{token}")
    assert ok and "B-roll" in msg and app.store.video(vid)["status"] == RENDERING
    assert run_all_jobs(app) == ["render"] and app.store.video(vid)["status"] == VIDEO_PENDING
    assert not any(c.provider == OWNER_PROVIDER for c in broll_mod.load_sources(
        app.workflow.places.work(app.workflow.reels.get(vid)["base"])))


def test_not_a_video_is_refused_and_the_part_is_asked_again(app, long_voice, tmp_path):
    bot, wf = TelegramBot(app), app.workflow
    vid = voice_in(app, long_voice)
    token = app.store.pending_approval(vid, "aroll")["id"]
    press(bot, f"ar:t:0:{token}")
    press(bot, f"ar:d:0:{token}")
    junk = tmp_path / "x.mp4"
    junk.write_bytes(b"not a video")

    async def dl(dest):
        shutil.copyfile(junk, dest)
    reply = asyncio.run(bot.handle_aroll(10, "x.mp4", dl))
    assert reply.startswith("⚠️") and wf.aroll_state(vid)["queue"] == ["hook"]
    assert "MB" in asyncio.run(bot.handle_aroll(10 ** 9, "big.mp4", dl))
    assert app.store.video(vid)["status"] == AROLL_PENDING


def test_a_new_voice_asks_again(app, long_voice):
    wf = app.workflow
    vid = voice_in(app, long_voice)
    old = app.store.pending_approval(vid, "aroll")["id"]
    assert wf.assign_voice(wf.save_raw_voice(long_voice, "voice", ".wav"), vid).ok
    assert app.store.approval(old)["status"] == "superseded"
    run_all_jobs(app)
    assert app.store.video(vid)["status"] == AROLL_PENDING and app.store.pending_approval(vid, "aroll")["id"] != old

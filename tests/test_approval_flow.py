"""Owner approvals with versioned buttons: topic choice, script (single-use, stale buttons refused), edit, regenerate,
reject with a lesson, and the quiet-Telegram rule."""

import asyncio
import re

from conftest import outbox_kinds, run_all_jobs, script_pending, uz_script

from socialauto.store import REJECTED, SCRIPT_PENDING, TOPIC_PENDING, VOICE_WAITING
from socialauto.telegram_bot import (TelegramBot, reel_script_message, reel_video_keyboard, script_keyboard,
                                     topic_keyboard, topic_message, voice_request_message)


def press(bot, data, user=111):
    return asyncio.run(bot.handle_button(user, data))


def test_topic_choice_message_and_buttons(app):
    vid = app.workflow.request_new()
    assert run_all_jobs(app) == ["research"]
    assert app.store.video(vid)["status"] == TOPIC_PENDING
    reel = app.workflow.reels.get(vid)
    token = app.store.pending_approval(vid, "topic")["id"]
    text = topic_message(reel["topics"], reel["insight"], True)
    assert "Manbalar" in text and "Kun.uz" in text and token not in text
    kb = topic_keyboard(reel["topics"], token)
    assert [row[0].text for row in kb.inline_keyboard][-1] == "🔎 Boshqa mavzular"
    ok, msg = press(TelegramBot(app), f"t:m:{token}")                       # "other topics": research again
    assert ok and app.store.video(vid)["status"] == "researching"
    assert not press(TelegramBot(app), f"t:0:{token}")[0]                    # the old buttons stop working


def test_script_message_shows_8_parts_and_summary(app):
    vid = script_pending(app)
    assert app.store.video(vid)["status"] == SCRIPT_PENDING
    script = app.store.script(vid)
    text = reel_script_message(script, "10-noyabr, 19:00", True, 2.2).replace("&#x27;", "'")
    assert "Bu video nima haqida" in text and "8 qism" in text and "Birinchi 5 soniyadagi fakt" in text
    for p in script["parts"]:
        assert p["text"] in text
    token = app.store.pending_approval(vid, "script")["id"]
    assert token not in text and "{" not in text                             # no ids, no JSON (law 6)


def test_buttons_fit_telegram_and_carry_no_visible_ids():
    for kb in (script_keyboard("a1b2c3d4e5"), reel_video_keyboard("a1b2c3d4e5")):
        for row in kb.inline_keyboard:
            for b in row:
                assert len(b.callback_data.encode()) <= 64 and "a1b2" not in b.text
    labels = [b.text for row in reel_video_keyboard("a1b2c3d4e5").inline_keyboard for b in row]
    assert not any("joyla" in label.lower() for label in labels)            # law 15: no posting button


def test_approve_asks_for_voice(app):
    vid = script_pending(app)
    token = app.store.pending_approval(vid, "script")["id"]
    ok, reply = press(TelegramBot(app), f"s:a:{token}")
    assert ok and app.store.video(vid)["status"] == VOICE_WAITING
    assert "voice_request" in outbox_kinds(app)
    text = voice_request_message(app.store.script(vid), app.settings, [])
    assert "O'qiladigan matn" in text and "Maslahatlar" in text and "45–60" in text


def test_button_is_single_use(app):
    vid = script_pending(app)
    token = app.store.pending_approval(vid, "script")["id"]
    bot = TelegramBot(app)
    assert press(bot, f"s:a:{token}")[0]
    ok, reply = press(bot, f"s:a:{token}")
    assert not ok and "allaqachon" in reply


def test_edit_note_rewrites_and_old_buttons_stop_working(app, fake_claude):
    vid = script_pending(app)
    bot = TelegramBot(app)
    old = app.store.pending_approval(vid, "script")["id"]
    assert press(bot, f"s:e:{old}")[0]
    fake_claude.scripts.append(uz_script(title="Qisqaroq sarlavha"))
    reply = asyncio.run(bot.handle_text(111, "Hookni kuchliroq qiling"))
    assert "qayta yozilmoqda" in reply
    assert run_all_jobs(app) == ["rewrite"]
    assert "Hookni kuchliroq qiling" in fake_claude.calls[-1][1]             # the note reaches Claude
    assert app.store.video(vid)["script_version"] == 2
    new = app.store.pending_approval(vid, "script")["id"]
    assert new != old and not press(bot, f"s:a:{old}")[0] and press(bot, f"s:a:{new}")[0]


def test_pasted_full_script_replaces_the_text(app, fake_claude):
    from conftest import UZ_PARTS
    from socialauto.reel.script import PART_UZ, PARTS
    vid = script_pending(app)
    bot = TelegramBot(app)
    token = app.store.pending_approval(vid, "script")["id"]
    press(bot, f"s:e:{token}")
    pasted = "\n".join(f"{PART_UZ[k]}: {UZ_PARTS[k]} {'qo‘shimcha so‘z' if k == 'cta' else ''}" for k in PARTS)
    reply = asyncio.run(bot.handle_text(111, pasted))
    assert "8 qismga" in reply
    run_all_jobs(app)
    assert app.store.script(vid)["parts"][7]["text"].endswith("qo‘shimcha so‘z")
    assert not [c for c in fake_claude.calls if c[0].startswith("restructure")]   # labelled: split without Claude


def test_regenerate_makes_a_new_script_on_the_same_topic(app, fake_claude):
    vid = script_pending(app)
    token = app.store.pending_approval(vid, "script")["id"]
    ok, msg = press(TelegramBot(app), f"s:g:{token}")
    assert ok and "yangi ssenariy" in msg
    assert run_all_jobs(app) == ["regenerate"]
    assert app.store.video(vid)["script_version"] == 2


def test_reject_records_reason_as_lesson(app):
    vid = script_pending(app)
    bot = TelegramBot(app)
    token = app.store.pending_approval(vid, "script")["id"]
    assert press(bot, f"s:r:{token}")[0]
    assert app.store.video(vid)["status"] == REJECTED
    assert "Eslab qolindi" in asyncio.run(bot.handle_text(111, "juda zerikarli"))
    assert any("juda zerikarli" in r["text"] for r in app.lessons.all())
    assert "juda zerikarli" in app.claude._prompt("propose-reel-script", "x")   # fed into the next prompt (law 11)


def test_unknown_button(app):
    assert not press(TelegramBot(app), "zz:1")[0]


def test_only_owner_kinds_are_sent(app):
    """Law 5: anything that is not an owner step or an alert is silenced."""
    app.outbox.add("debug_info", text="internal")
    app.outbox.add("owner_action", text="🔑 login")

    class FakeBot:
        def __init__(self):
            self.sent = []

        async def send_message(self, chat_id, text, **kw):
            self.sent.append(text)

    bot = TelegramBot(app)
    bot.bot = FakeBot()
    asyncio.run(bot.deliver_outbox())
    assert bot.bot.sent == ["🔑 login"] and not re.search(r"internal", " ".join(bot.bot.sent))

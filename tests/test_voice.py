"""The owner's voice (law 14): intake of every file kind, limits, cleanup, newest voice wins, unsolicited voices,
one reminder + quiet date move, script-vs-speech mismatch buttons."""

import asyncio
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from conftest import SAMPLE_TEXT, SAMPLE_VOICE, outbox_kinds, run_all_jobs, voice_waiting

from socialauto.db import parse_iso
from socialauto.store import RENDERING, VIDEO_PENDING, VOICE_CHECK, VOICE_PROCESSING, VOICE_WAITING
from socialauto.telegram_bot import TelegramBot, voice_check_keyboard, voice_check_message
from socialauto.voice import Word, check_upload, compare, voice_problems


def copy_download(src: Path):
    async def download(dest: Path) -> None:
        shutil.copyfile(src, dest)
    return download


def make_media(src: Path, out: Path, video: bool) -> Path:
    args = ["ffmpeg", "-y", "-loglevel", "error"]
    if video:
        args += ["-f", "lavfi", "-i", "color=c=gray:s=240x240:d=60", "-i", str(src), "-shortest", "-c:v", "libx264",
                 "-c:a", "aac"]
    else:
        args += ["-i", str(src)] + (["-c:a", "libopus"] if out.suffix == ".ogg" else [])
    subprocess.run(args + [str(out)], check=True)
    return out


def test_check_upload_rules():
    assert check_upload("voice", 300_000, 20).ok
    assert check_upload("audio", 1_000_000, 20, "audio/mpeg", "take.mp3").suffix == ".mp3"
    assert check_upload("document", 1_000, 20, "audio/x-m4a", "voice.m4a").ok
    assert check_upload("document", 1_000, 20, "", "voice.opus").ok
    assert check_upload("video_note", 1_000, 20).ok and check_upload("video", 1_000, 20).ok
    assert check_upload("document", 1_000, 20, "application/pdf", "script.pdf").reason == "type"
    assert check_upload("voice", 21_000_000, 20).reason == "size"


@pytest.mark.parametrize("kind,name,mime,video", [
    ("voice", "v.ogg", "audio/ogg", False), ("audio", "v.mp3", "audio/mpeg", False), ("document", "v.wav", "audio/wav", False),
    ("video_note", "v.mp4", "video/mp4", True), ("video", "v.mp4", "video/mp4", True),
])
def test_every_kind_is_accepted_and_processed(app, tmp_path, long_voice, kind, name, mime, video):
    vid = voice_waiting(app)
    src = long_voice if name == "v.wav" else make_media(long_voice, tmp_path / name, video)
    reply, markup = asyncio.run(TelegramBot(app).handle_upload(kind, src.stat().st_size, mime, name, copy_download(src)))
    assert "qabul qilindi" in reply and markup is None
    assert app.store.video(vid)["status"] == VOICE_PROCESSING
    assert run_all_jobs(app, kinds_skip=("render",)) == ["process_voice"]
    assert app.store.video(vid)["status"] == RENDERING
    voice = app.store.voice(app.store.video(vid)["voice_id"])
    assert voice["status"] == "accepted" and voice["duration"] > 40 and voice["coverage"] >= 0.9
    assert Path(voice["raw_path"]).parent == app.settings.voices_dir      # raw file kept in data/voices/


def test_wrong_file_type_and_too_big(app):
    vid = voice_waiting(app)
    bot = TelegramBot(app)
    reply, _ = asyncio.run(bot.handle_upload("document", 1000, "application/pdf", "x.pdf", copy_download(SAMPLE_VOICE)))
    assert "ovoz emas" in reply
    reply, _ = asyncio.run(bot.handle_upload("voice", 25_000_000, "audio/ogg", "", copy_download(SAMPLE_VOICE)))
    assert "20 MB" in reply
    assert app.store.video(vid)["status"] == VOICE_WAITING


def test_cleanup_normalizes_loudness_and_trims_silence(app, long_voice):
    from socialauto.video import ffmpeg
    vid = voice_waiting(app)
    asyncio.run(TelegramBot(app).handle_upload("voice", 1000, "audio/wav", "v.wav", copy_download(long_voice)))
    run_all_jobs(app, kinds_skip=("render",))
    voice = app.store.voice(app.store.video(vid)["voice_id"])
    assert abs(ffmpeg.loudness(Path(voice["clean_path"]))["lufs"] + 14) < 2.0
    assert voice["duration"] < voice["levels"]["seconds"] - 0.5           # leading/trailing silence trimmed


def test_newest_voice_wins(app, long_voice):
    vid = voice_waiting(app)
    bot = TelegramBot(app)
    asyncio.run(bot.handle_upload("voice", 1000, "audio/wav", "a.wav", copy_download(long_voice)))
    first = app.store.video(vid)["voice_id"]
    run_all_jobs(app, kinds_skip=("render",))
    assert app.store.video(vid)["status"] == RENDERING
    reply, markup = asyncio.run(bot.handle_upload("voice", 1000, "audio/wav", "b.wav", copy_download(long_voice)))
    data = next(b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data.startswith("vo:"))
    assert asyncio.run(bot.handle_button(111, data))[0]
    second = app.store.video(vid)["voice_id"]
    assert second != first and app.store.voice(first)["status"] == "superseded"
    assert not [j for j in app.jobs.active(("render",)) if f":{first}" in (j["dedupe_key"] or "")]   # old render cancelled
    ran = run_all_jobs(app)
    assert ran.count("process_voice") == 1 and "render" in ran
    video = app.store.video(vid)
    assert video["status"] == VIDEO_PENDING and app.store.render(video["render_id"])["voice_id"] == second


def test_unsolicited_voice_offers_new_video(app, fake_claude, long_voice):
    bot = TelegramBot(app)
    reply, markup = asyncio.run(bot.handle_upload("voice", 1000, "audio/wav", "a.wav", copy_download(long_voice)))
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert "yangi video" in reply and len(buttons) == 1 and buttons[0].callback_data.startswith("vn:")
    assert asyncio.run(bot.handle_button(111, buttons[0].callback_data))[0]
    assert run_all_jobs(app) == ["plan_from_voice"]
    assert fake_claude.calls[-1][0] == "plan-reel-from-voice"
    video = [v for v in app.store.videos() if v["origin"] == "voice"][0]
    ok, reply = asyncio.run(bot.handle_button(111, f"s:a:{app.store.pending_approval(video['id'], 'script')['id']}"))
    assert ok and "Ovozingiz bor" in reply and "voice_request" not in outbox_kinds(app)
    run_all_jobs(app)
    assert app.store.video(video["id"])["status"] == VIDEO_PENDING
    assert not asyncio.run(bot.handle_button(111, buttons[0].callback_data))[0]   # used buttons stop working


def test_one_reminder_then_quiet_date_move(app, clock):
    vid = voice_waiting(app)
    slot = parse_iso(app.store.video(vid)["slot_at"])
    old_base = app.workflow.reels.get(vid)["base"]
    clock.now = slot - timedelta(hours=4)
    app.workflow.tick()
    assert outbox_kinds(app).count("voice_reminder") == 0
    clock.now = slot - timedelta(hours=2, minutes=50)
    app.workflow.tick()
    app.workflow.tick()
    assert outbox_kinds(app).count("voice_reminder") == 1                  # exactly one
    clock.now = slot + timedelta(minutes=1)
    before = len(app.outbox.pending(300))
    app.workflow.tick()
    new_slot = parse_iso(app.store.video(vid)["slot_at"])
    assert new_slot - slot == timedelta(days=1)
    assert len(app.outbox.pending(300)) == before                          # moved quietly
    assert app.workflow.reels.get(vid)["base"] != old_base                 # and everything renamed to the new date


def test_mismatch_asks_owner_with_buttons(app, transcriber, long_voice):
    vid = voice_waiting(app)
    transcriber.text = "Toshkentda suvning 40 foizi quvurlarda yo'qoladi."    # most of the script is missing
    asyncio.run(TelegramBot(app).handle_upload("voice", 1000, "audio/wav", "a.wav", copy_download(long_voice)))
    run_all_jobs(app)
    assert app.store.video(vid)["status"] == VOICE_CHECK
    item = [i for i in app.outbox.pending(50) if i.kind == "voice_check"][0]
    assert "eshitilmadi" in voice_check_message("T", item.payload["problems"])
    labels = [b.text for row in voice_check_keyboard(item.payload["approval"]).inline_keyboard for b in row]
    assert labels == ["▶️ Shu holicha davom et", "🎙 Qayta yozib yuboraman"]
    assert any("matnni oxirigacha" in t for t in app.lessons.voice_tips())    # a lesson becomes a recording tip
    ok, _ = asyncio.run(TelegramBot(app).handle_button(111, f"c:k:{item.payload['approval']}"))
    assert ok and app.store.video(vid)["status"] == RENDERING


def test_mismatch_redo_waits_for_new_voice(app, transcriber, long_voice):
    vid = voice_waiting(app)
    transcriber.text = "Bugun ob-havo juda yaxshi edi va biz bozorga bordik."
    asyncio.run(TelegramBot(app).handle_upload("voice", 1000, "audio/wav", "a.wav", copy_download(long_voice)))
    run_all_jobs(app)
    token = app.store.pending_approval(vid, "voice_check")["id"]
    ok, _ = asyncio.run(TelegramBot(app).handle_button(111, f"c:r:{token}"))
    assert ok and app.store.video(vid)["status"] == VOICE_WAITING


def test_compare_small_differences_are_fine():
    words = [Word(w, i * 0.3, i * 0.3 + 0.25) for i, w in enumerate(
        "Octopuses have got three hearts. Two pump blood to the gills and one pumps it to the rest of the body. "
        "When an octopus swims that third heart stops.".split())]
    c = compare(SAMPLE_TEXT, words)
    assert c.coverage > 0.9 and not c.missing
    assert voice_problems(c, 10, 59, 0.75) == [] and voice_problems(c, 70, 59, 0.75)[0].startswith("too_long")


@pytest.mark.render
def test_real_uzbek_stt_gives_word_timestamps(settings, tmp_path):
    """rubaiSTT on an espeak-ng Uzbek test clip: words with sane timestamps that align to the script."""
    from socialauto.reel.align import RubaiSTT, align
    from socialauto.voice import clean, decode
    model = Path(__file__).resolve().parent.parent / "models" / "rubaistt-medium-int8-ct2"
    if not (model / "model.bin").exists():
        pytest.skip("rubaiSTT model not downloaded")
    stt = RubaiSTT(model)
    sample = Path(__file__).resolve().parent / "fixtures" / "sample_voice_uz.wav"
    raw = decode(sample, tmp_path / "raw.wav")
    words = stt.transcribe(clean(raw, tmp_path / "c.wav", -14, compressor=True), "uz")
    assert len(words) >= 8 and all(w.end >= w.start for w in words)
    text = ["Toshkentda suvning qirq foizi quvurlarda yo'qoladi.",
            "Sabab eski quvurlar, ya'ni ellik yildan beri almashtirilmagan temir quvurlar."]
    assert align(text, words, words[-1].end).coverage >= 0.6

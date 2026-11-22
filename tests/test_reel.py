"""Task 04: the owner's reel flow — research dedupe, 8-part validator, safe zones, _vN, date rename, Buffer drafts,
story step, git reels/, and the whole Telegram flow with fakes (no network, no Remotion in unit tests)."""

import asyncio
import json
import shutil
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import (SAMPLE_VOICE, UZ_PARTS, FakeProvider, FileSession, dryrun_entries, run_all_jobs, topic,
                      script_pending as script_pending_,
                      uz_script)
from PIL import Image

from socialauto.platforms.dryrun import DryRunLog
from socialauto.reel import layout, naming, research, script as rs
from socialauto.reel.broll import Candidate, acceptable, collect, license_ok
from socialauto.reel.buffer import DryRunBuffer, GraphBuffer, story_meta, youtube_meta
from socialauto.reel.publish import create_story_draft, live_link, queue_posts
from socialauto.store import (BUFFER_PENDING, COVER_WAITING, DONE, SCRIPT_PENDING, STORY_PENDING, TOPIC_PENDING,
                              VIDEO_PENDING, VOICE_WAITING)
from socialauto.telegram_bot import TelegramBot

UTC = timezone.utc

# --- research ---------------------------------------------------------------------------------------------------

def test_research_dedupe_against_last_30_posts():
    recent = [f"Mavzu {i} haqida" for i in range(40)]
    recent[3] = "Toshkentda suv yo'qotilishi quvurlarda"
    recent[35] = "Orol dengizi qurishi va chang bo'ronlari"      # older than the last 30: allowed again
    cands = [topic("Toshkentda suv yo'qotilishi: quvurlarda 40%"), topic("Orol dengizi qurishi: chang bo'ronlari suvsiz"),
             topic("Yangi oqova suv tozalash inshooti Samarqandda"), topic("Futbol chempionati natijalari"),
             topic("Ichimlik suvi tariflari oshdi", url="not-a-link")]
    out = research.dedupe(cands, recent, recent_limit=30)
    titles = [t["title"] for t in out]
    assert "Toshkentda suv yo'qotilishi: quvurlarda 40%" not in titles       # repeats a recent post
    assert "Orol dengizi qurishi: chang bo'ronlari suvsiz" in titles          # only in older posts
    assert "Futbol chempionati natijalari" not in titles                      # off-scope
    assert "Ichimlik suvi tariflari oshdi" not in titles                       # a fact without a checkable source
    assert "Yangi oqova suv tozalash inshooti Samarqandda" in titles


def test_research_file_round_trip(tmp_path):
    topics = [topic("Ichimlik suvi sifati"), topic("Oqova suvdan biogaz")]
    f = research.write_markdown(tmp_path / "2026-11-10-ichimlik-suvi-sifati.md", topics, "Raqamli hooklar yaxshi", {"views": 1200}, date(2026, 11, 8))
    parsed = research.parse_markdown(f.read_text())
    assert [t["title"] for t in parsed["topics"]] == ["Ichimlik suvi sifati", "Oqova suvdan biogaz"]
    assert parsed["topics"][0]["facts"][0]["source"] == "Kun.uz" and parsed["insight"] == "Raqamli hooklar yaxshi"
    assert "Ichimlik suvi sifati" in research.earlier_research_titles(tmp_path)


# --- 8-part script ------------------------------------------------------------------------------------------------

def test_script_validator_accepts_a_good_script():
    s = uz_script()
    assert rs.problems(s) == [], rs.problems(s)


def test_script_validator_rules():
    good = uz_script()
    wrong_order = dict(good, parts=good["parts"][1:] + good["parts"][:1])
    assert any("8 parts in this order" in p for p in rs.problems(wrong_order))
    assert any("spoken length" in p for p in rs.problems(uz_script(pad_words=0)))          # too short
    assert any("spoken length" in p for p in rs.problems(uz_script(pad_words=200)))        # too long
    late = json.loads(json.dumps(good))
    late["parts"][0]["text"] = "Bugun sizga juda muhim bir narsani aytib bermoqchiman, oxirigacha ko'ring."
    assert any("first 5 seconds" in p for p in rs.problems(late))
    no_yani = json.loads(json.dumps(good))
    no_yani["parts"][2]["text"] = "Sabab eski quvurlar, ular zanglab teshiladi va suv oqib ketadi har kuni."
    assert any("ya'ni" in p and "eski quvurlar" in p for p in rs.problems(no_yani))


def test_pasted_script_is_split_into_8_parts():
    labelled = "\n".join(f"{rs.PART_UZ[k]}: {UZ_PARTS[k]}" for k in rs.PARTS)
    assert rs.parse_pasted(labelled) == [UZ_PARTS[k] for k in rs.PARTS]
    blank = "\n\n".join(UZ_PARTS[k] for k in rs.PARTS)
    assert rs.parse_pasted(blank) == [UZ_PARTS[k] for k in rs.PARTS]
    assert rs.parse_pasted("just one paragraph") is None


# --- safe zones -----------------------------------------------------------------------------------------------------

def test_safe_zone_check():
    lay = layout.default_layout()
    assert layout.safe_zone_problems(lay) == []
    bad = dict(lay, subtitle=layout.Box(64, 1500, 856, 200))                 # into the bottom 20 %
    assert any("bottom 20%" in p for p in layout.safe_zone_problems(bad))
    wide = dict(lay, title=layout.Box(64, 150, 1000, 200))                   # under the right-side buttons
    assert any("right-side buttons" in p for p in layout.safe_zone_problems(wide))
    high = dict(lay, subtitle=layout.Box(64, 300, 856, 200))                 # not at eye level
    assert any("eye level" in p for p in layout.safe_zone_problems(high))
    assert layout.text_fit_problems("Juda uzun sarlavha " * 6, lay["title"], 64, 3)


# --- naming: _vN and date rename ---------------------------------------------------------------------------------

@pytest.fixture
def places(tmp_path):
    return naming.Places(tmp_path / "work", tmp_path / "exports", tmp_path / "work" / "research", tmp_path / "repo" / "reels")


def test_versions_never_overwrite(places):
    base = "2026-11-10-suv-yoqotilishi"
    n1, p1 = places.next_export(base)
    p1.write_bytes(b"v1")
    n2, p2 = places.next_export(base)
    p2.write_bytes(b"v2")
    assert (n1, n2) == (1, 2) and p1.name == f"{base}_v1.mp4" and p2.name == f"{base}_v2.mp4"
    p2.unlink()                                                              # even a deleted number is not reused
    n3, p3 = places.next_export(base)
    assert n3 == 3 and p1.read_bytes() == b"v1"


def test_date_rename_moves_everything(places, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    old, new = "2026-11-10-suv", "2026-11-12-suv"
    (places.work(old) / "broll").mkdir(parents=True)
    (places.work(old) / "script.md").write_text("x")
    places.exports.mkdir(parents=True)
    for n in (1, 2):
        (places.exports / f"{old}_v{n}.mp4").write_bytes(b"x")
    places.research.mkdir(parents=True, exist_ok=True)
    places.research_file(old).write_text("# r")
    places.reel_dir(old).mkdir(parents=True)
    (places.reel_dir(old) / f"{old}.mp4").write_bytes(b"x")
    (places.reel_dir(old) / f"{old}_cover.jpg").write_bytes(b"x")
    done = naming.rename_all(places, old, new, repo)
    assert places.work(new).exists() and not places.work(old).exists()
    assert [p.name for p in places.versions(new)] == [f"{new}_v1.mp4", f"{new}_v2.mp4"] and not places.versions(old)
    assert places.research_file(new).exists() and not places.research_file(old).exists()
    assert sorted(p.name for p in places.reel_dir(new).iterdir()) == [f"{new}.mp4", f"{new}_cover.jpg"]
    assert "work" in done and "research" in done and "reels" in done


def test_slugify_uzbek():
    assert naming.slugify("Toshkentda suv yo'qotilishi 40%") == "toshkentda-suv-yoqotilishi-40"
    assert naming.slugify("Ўзбекистонда сув танқислиги") == "ozbekistonda-suv-tanqisligi"


# --- B-roll ------------------------------------------------------------------------------------------------------------

def test_broll_licence_and_realness_filter():
    assert license_ok("CC BY-SA 4.0") and license_ok("CC0") and license_ok("Public domain")
    assert not license_ok("CC BY-NC 4.0") and not license_ok("CC BY-ND 2.0") and not license_ok("")
    ok = Candidate("video", "u1", "Wikimedia Commons", "Water pipe repair Tashkent", "A", "CC BY 4.0", "s", 1080, 1920, 12)
    cartoon = Candidate("video", "u2", "Wikimedia Commons", "Water cycle animation", "A", "CC BY 4.0", "s", 1080, 1920, 12)
    nc = Candidate("image", "u3", "Wikimedia Commons", "River", "A", "CC BY-NC 2.0", "s", 2000, 3000)
    assert acceptable(ok, set()) and not acceptable(cartoon, set()) and not acceptable(nc, set())


def test_collect_records_source_and_licence(tmp_path):
    work = tmp_path / "w"
    clips = collect(uz_script()["parts"], work, [FakeProvider(tmp_path)], session=FileSession(), pause=0)
    assert len(clips) == 8 and all((work / c.file).exists() for c in clips)
    sources = json.loads((work / "broll" / "sources.json").read_text())
    assert sources[0]["license"] == "CC BY 4.0" and sources[0]["author"] == "Photographer"
    assert "| hook |" in (work / "SOURCES.md").read_text()


# --- Buffer -------------------------------------------------------------------------------------------------------------

class FakeHTTP:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(json)
        body = self.responses.pop(0)

        class R:
            status_code = 200

            def json(self_inner):
                return body
        return R()


def test_approved_reel_goes_into_the_buffer_queue_without_a_time(tmp_path):
    http = FakeHTTP([
        {"data": {"account": {"organizations": [{"id": "org1", "name": "Me"}]}}},
        {"data": {"channels": [{"id": "c-ig", "service": "instagram", "name": "ig"}, {"id": "c-yt", "service": "youtube", "name": "yt"},
                               {"id": "c-li", "service": "linkedin", "name": "li"}, {"id": "c-x", "service": "twitter", "name": "x"}]}},
        {"data": {"createPost": {"post": {"id": "p1", "text": "t", "status": "scheduled", "dueAt": "2026-11-10T14:00:00Z"}}}},
        {"data": {"createPost": {"post": {"id": "p2", "text": "t", "status": "scheduled", "dueAt": "2026-11-10T15:00:00Z"}}}},
        {"data": {"createPost": {"post": {"id": "p3", "text": "t", "status": "scheduled", "dueAt": None}}}},
    ])
    buf = GraphBuffer("key", session=http)
    caps = {"instagram": "IG text #suv", "youtube_title": "YT title", "youtube_description": "YT desc", "linkedin": "LI text",
            "story_text": "Yangi reel"}
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    ids, states = queue_posts(buf, caps, video, public_files=None)
    assert ids == {"instagram": "p1", "youtube": "p2", "linkedin": "p3"}
    assert states["instagram"] == {"status": "scheduled", "due_at": "2026-11-10T14:00:00Z", "sent_at": None, "link": None}
    inputs = [c["variables"]["input"] for c in http.calls[2:]]
    assert all(i["saveToDraft"] is False and i["mode"] == "addToQueue" and i["schedulingType"] == "automatic"
               and "dueAt" not in i for i in inputs)
    assert "dueAt" in http.calls[2]["query"]                                  # Buffer tells us the time it picked
    assert inputs[0]["metadata"] == {"instagram": {"type": "reel", "shouldShareToFeed": True}}
    assert inputs[1]["metadata"]["youtube"]["title"] == "YT title" and inputs[1]["metadata"]["youtube"]["categoryId"] == "27"
    assert inputs[0]["assets"][0]["video"]["url"]
    assert "createPost" in http.calls[2]["query"] and "MutationError" in http.calls[2]["query"]


def test_buffer_errors():
    from socialauto.reel.buffer import BufferAuthError, BufferError
    buf = GraphBuffer("key", session=FakeHTTP([{"data": None, "errors": [{"message": "no", "extensions": {"code": "UNAUTHORIZED"}}]}]))
    with pytest.raises(BufferAuthError):
        buf.org()
    # what Buffer really answers for a wrong or expired key (seen 2026-11-08)
    buf = GraphBuffer("key", session=FakeHTTP([{"data": None, "errors": [{"message": "Access token is not valid",
                                                                          "extensions": {"code": "UNAUTHENTICATED"}}]}]))
    with pytest.raises(BufferAuthError):
        buf.org()
    buf = GraphBuffer("key", session=FakeHTTP([{"data": {"account": {"organizations": [{"id": "o"}]}}},
                                               {"data": {"channels": [{"id": "c", "service": "instagram"}]}},
                                               {"data": {"createPost": {"message": "Text is required"}}}]))
    with pytest.raises(BufferError, match="Text is required"):
        buf.create_draft(buf.channels()[0], "", None, None, {})


def test_story_step_draft_with_link_reminder(tmp_path):
    log = DryRunLog(tmp_path / "d.json")
    buf = DryRunBuffer(log)
    cover = tmp_path / "c.jpg"
    Image.new("RGB", (1080, 1920)).save(cover)
    drafts = {"instagram": buf.create_draft({"service": "instagram", "id": "x"}, "t", "v", None, {})}
    assert live_link(buf, drafts) is None                                    # not live yet
    buf.live.add(drafts["instagram"])
    link = live_link(buf, drafts)
    assert link.startswith("https://www.instagram.com/reel/")
    sid = create_story_draft(buf, cover, link, "Yangi reel!")
    entry = [e for e in log.read() if e["remote_id"] == sid][0]["input"]
    assert entry["metadata"]["instagram"]["type"] == "story" and entry["metadata"]["instagram"]["stickerFields"]["other"] == link
    assert entry["saveToDraft"] is True and entry["schedulingType"] == "notification" and entry["assets"][0]["image"]
    assert "_scheduling" not in story_meta(link, "x") and youtube_meta("t" * 200)["youtube"]["title"] == "t" * 100


# --- git reels/ ---------------------------------------------------------------------------------------------------------

# --- the whole flow through Telegram (fakes: Claude, STT, B-roll, renderer) ----------------------------------------------

def press(bot, data):
    return asyncio.run(bot.handle_button(111, data))


def test_full_owner_flow(app, tmp_path, clock, long_voice):
    bot = TelegramBot(app)
    wf = app.workflow
    vid = wf.request_new()
    assert run_all_jobs(app) == ["research"]
    assert app.store.video(vid)["status"] == TOPIC_PENDING
    reel = wf.reels.get(vid)
    assert Path(reel["research_file"]).exists() and len(reel["topics"]) == 4
    token = app.store.pending_approval(vid, "topic")["id"]
    from socialauto.telegram_bot import topic_keyboard, topic_message
    kb = topic_keyboard(reel["topics"], token)
    assert kb.inline_keyboard[-1][0].text == "🔎 Boshqa mavzular" and "Manbalar" in topic_message(reel["topics"], "", True)
    ok, msg = press(bot, f"t:1:{token}")                                     # pick topic 2
    assert ok and "Oqova suvni" in msg
    reel = wf.reels.get(vid)
    publish_day = wf.publish_date(app.store.video(vid)).isoformat()
    assert reel["base"] == f"{publish_day}-oqova-suvni-qayta-ishlash-samarqandda"
    assert Path(reel["research_file"]).name == f"{reel['base']}.md"            # research renamed to the chosen topic
    run_all_jobs(app)
    assert app.store.video(vid)["status"] == SCRIPT_PENDING
    token = app.store.pending_approval(vid, "script")["id"]
    assert press(bot, f"s:a:{token}")[0]
    assert app.store.video(vid)["status"] == VOICE_WAITING
    # the owner's voice
    voice_id = wf.save_raw_voice(long_voice, "voice", ".wav")
    assert wf.route_voice(voice_id)[0] == "assigned"
    run_all_jobs(app)
    v = app.store.video(vid)
    assert v["status"] == VIDEO_PENDING
    work = wf.places.work(reel["base"])
    assert (work / "SOURCES.md").exists() and (work / "script.md").exists()
    assert wf.reels.get(vid)["version"] == 1 and wf.places.versions(reel["base"])[0].name == f"{reel['base']}_v1.mp4"
    assert (Path(app.settings.root) / "docs" / "reel-mistakes-checklist.md").exists()
    # a fix note -> v2 (only the asked part gets new footage)
    token = app.store.pending_approval(vid, "video")["id"]
    assert press(bot, f"v:e:{token}")[0]
    reply = asyncio.run(bot.handle_text(111, "3-qismda boshqa video qo'y"))
    assert "keyingi versiya" in reply
    run_all_jobs(app)
    assert wf.reels.get(vid)["version"] == 2 and len(wf.places.versions(reel["base"])) == 2
    assert app.store.script(vid)["parts"][2]["broll"] == "old rusty pipe"
    # approve -> cover request (no bot thumbnails)
    token = app.store.pending_approval(vid, "video")["id"]
    ok, msg = press(bot, f"v:a:{token}")
    assert ok and "muqova" in msg.lower() and app.store.video(vid)["status"] == COVER_WAITING
    cover = tmp_path / "cover.png"
    Image.new("RGB", (1080, 1920), (200, 50, 50)).save(cover)

    async def dl(dest):
        shutil.copyfile(cover, dest)
    assert "cover_request" in [i.kind for i in app.outbox.pending(300)]
    reply = asyncio.run(bot.handle_cover(dl))
    assert "Muqovangiz qabul qilindi" in reply and "o'zgartirilmasdan" in reply
    run_all_jobs(app)
    v = app.store.video(vid)
    assert v["status"] == BUFFER_PENDING
    reel = wf.reels.get(vid)
    assert set(reel["drafts"]) == {"instagram", "youtube", "linkedin"} and "GitHub ulanmagan" in reel["git_note"]
    assert not (Path(app.settings.root) / "reels").exists()                 # never in the code repo (Task 07)
    pushed_cover = app.workflow.content.reels / reel["base"] / f"{reel['base']}_cover.png"
    assert pushed_cover.read_bytes() == cover.read_bytes()                    # law 16: the owner's cover, unchanged
    queued = [e for e in dryrun_entries(app) if e.get("kind") == "queue"]
    assert len(queued) == 3 and all(d["input"]["mode"] == "addToQueue" and "dueAt" not in d["input"] for d in queued)
    assert {k: s["status"] for k, s in reel["buffer"].items()} == {"instagram": "scheduled", "youtube": "scheduled",
                                                                  "linkedin": "scheduled"}
    # it goes live -> story step
    app.workflow.buffer.live.add(reel["drafts"]["instagram"])
    wf.tick()
    assert app.store.video(vid)["status"] == STORY_PENDING
    states = wf.reels.get(vid)["buffer"]
    assert states["instagram"]["status"] == "sent" and states["instagram"]["link"] and states["youtube"]["status"] == "scheduled"
    assert [i.kind for i in app.outbox.pending(100)].count("story_ready") == 1
    ok, msg = press(bot, f"st:{vid}")
    assert ok and app.store.video(vid)["status"] == DONE
    assert not press(bot, f"st:{vid}")[0]


def test_too_short_voice_asks_the_owner_before_rendering(app):
    wf = app.workflow
    vid = wf.request_new()
    run_all_jobs(app)
    wf.topic_decision(app.store.pending_approval(vid, "topic")["id"], 0)
    run_all_jobs(app)
    wf.script_decision(app.store.pending_approval(vid, "script")["id"], "approve")
    wf.route_voice(wf.save_raw_voice(SAMPLE_VOICE, "voice", ".wav"))           # ~10 s: far too short
    run_all_jobs(app)
    assert app.store.video(vid)["status"] == "voice_check"
    item = [i for i in app.outbox.pending(50) if i.kind == "voice_check"][-1]
    assert any(p.startswith("too_short") for p in item.payload["problems"])


def test_publish_date_change_renames_everything(app, clock):
    wf = app.workflow
    vid = wf.request_new()
    run_all_jobs(app)
    token = app.store.pending_approval(vid, "topic")["id"]
    wf.topic_decision(token, 0)
    run_all_jobs(app)
    reel = wf.reels.get(vid)
    old = reel["base"]
    work = wf.places.work(old)
    work.mkdir(parents=True, exist_ok=True)
    (work / "note.txt").write_text("x")
    new_slot = datetime.fromisoformat(app.store.video(vid)["slot_at"]) + timedelta(days=3)
    wf.set_publish_date(vid, new_slot)
    new = wf.reels.get(vid)["base"]
    assert new != old and new[:10] == (datetime.fromisoformat(old[:10]) + timedelta(days=3)).date().isoformat()
    assert new[11:] == old[11:]
    assert (wf.places.work(new) / "note.txt").exists() and not wf.places.work(old).exists()
    assert Path(wf.reels.get(vid)["research_file"]).name == f"{new}.md"


def test_voice_note_fix_on_finished_reel(app, tmp_path, long_voice):
    wf = app.workflow
    vid = wf.request_new()
    run_all_jobs(app)
    wf.topic_decision(app.store.pending_approval(vid, "topic")["id"], 0)
    run_all_jobs(app)
    wf.script_decision(app.store.pending_approval(vid, "script")["id"], "approve")
    wf.route_voice(wf.save_raw_voice(long_voice, "voice", ".wav"))
    run_all_jobs(app)
    assert app.store.video(vid)["status"] == VIDEO_PENDING
    bot = TelegramBot(app)

    async def dl(dest):
        shutil.copyfile(SAMPLE_VOICE, dest)
    reply, markup = asyncio.run(bot.handle_upload("voice", 1000, "audio/wav", "n.wav", dl))
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert datas[0].startswith("vf:")                                        # offered as a fix note first
    ok, msg = press(bot, datas[0])
    assert ok and "Izohingiz" in msg
    run_all_jobs(app)
    assert wf.reels.get(vid)["version"] == 2


def test_alignment_survives_mishearings_and_cyrillic():
    from socialauto.reel.align import align, uz_latin
    from socialauto.voice import Word
    assert uz_latin("Сув танқислиги ўсмоқда") == "Suv tanqisligi o'smoqda"
    spoken = "toshkent va sunning qirq foizi kumurlarida yo'lqoladi. sababi eski kumurlar, ya'ni u kuyovdan beri almashdi bilmagan temir kumurlar.".split()
    ws = [Word(w, i * 0.4, i * 0.4 + 0.35) for i, w in enumerate(spoken)]
    a = align(["Toshkentda suvning qirq foizi quvurlarda yo'qoladi.",
               "Sabab eski quvurlar, ya'ni ellik yildan beri almashtirilmagan temir quvurlar."], ws, 9)
    assert a.coverage >= 0.75 and a.part_starts[1] == pytest.approx(2.8, abs=0.05)
    assert [w.text for w in a.words][:3] == ["Toshkentda", "suvning", "qirq"]     # the approved spelling is shown
    cyr = [Word(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate("Тошкентда сувнинг қирқ фоизи".split())]
    assert align(["Toshkentda suvning qirq foizi"], cyr, 2).coverage == 1.0


def test_slightly_long_take_is_sped_up_to_fit(app, tmp_path):
    """A 62-66 s take: the owner says "continue" and the voice is sped up (max 1.15x) to fit 60 s."""
    long = tmp_path / "sample_voice_66s.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "5", "-i", str(SAMPLE_VOICE), "-t", "66",
                    "-c", "copy", str(long)], check=True)
    vid = script_pending_(app)
    app.workflow.script_decision(app.store.pending_approval(vid, "script")["id"], "approve")
    app.workflow.route_voice(app.workflow.save_raw_voice(long, "voice", ".wav"))
    run_all_jobs(app)
    assert app.store.video(vid)["status"] == "voice_check"                   # too long: the owner is asked
    ok, _ = app.workflow.voice_check_decision(app.store.pending_approval(vid, "voice_check")["id"], "continue").__dict__.values()
    assert ok
    run_all_jobs(app)
    assert app.store.video(vid)["status"] == "video_pending"
    rendered = app.workflow.reel_renderer.calls[-1]
    assert rendered["starts"][-1] < 60


def test_broll_prefers_on_topic_clips():
    from socialauto.reel.broll import relevance, score
    on = Candidate("image", "u1", "Wikimedia Commons", "Water pipes repair in Tashkent", "A", "CC BY 4.0", "s", 1080, 1920)
    off = Candidate("video", "u2", "Wikimedia Commons", "Food demo sweet potato", "A", "CC BY 4.0", "s", 1080, 1920, 10)
    assert relevance(on, "water pipe repair") == 1.0 and relevance(off, "water pipe repair") == 0.0
    assert score(on, "water pipe repair") > score(off, "water pipe repair")


def test_decimal_key_fact_in_the_hook_is_heard():
    """27,7 / 1,7 / 1.5 stay one word: a decimal key fact in the hook used to fail the first-5-seconds rule twice."""
    for key, hook in (("27,7 foiz", "Chirchiq oqova suvi atigi 27,7 foiz tozalangan, qolgani esa daryoga ketadi."),
                      ("1,7 million", "Har yili 1,7 million kub metr suv quvurlarda yo'qoladi, hech kim sezmaydi."),
                      ("1.5", "Bir oilaga kuniga 1.5 kub suv kerak, lekin hammasiga ham yetmaydi.")):
        s = json.loads(json.dumps(uz_script()))
        s["key_fact"], s["parts"][0]["text"] = key, hook
        assert not any("first 5 seconds" in p for p in rs.problems(s)), (key, rs.problems(s))
    assert rs.words("atigi 27,7 foiz") == ["atigi", "27,7", "foiz"]


LATE_HOOK = ("Har kuni ichadigan suvimiz qayerdan kelishini va undan keyin qayerga ketishini hech o'ylab ko'rganmisiz? "
             "Chirchiq oqova suvi atigi 27,7 foiz tozalangan.")


def _late_hook_script():
    s = json.loads(json.dumps(uz_script()))
    s["key_fact"], s["parts"][0]["text"] = "27,7 foiz", LATE_HOOK
    return s


def test_hook_sentence_with_the_key_number_moves_to_the_front():
    """Last resort for the first-5-seconds rule: the hook's own key-number sentence goes first, no word changes."""
    s = _late_hook_script()
    assert any(rs.is_hook_problem(p) for p in rs.problems(s))
    fixed = rs.key_sentence_first(s)
    assert fixed and not any(rs.is_hook_problem(p) for p in rs.problems(fixed))
    assert fixed["parts"][0]["text"].startswith("Chirchiq oqova suvi atigi 27,7 foiz")
    assert sorted(rs.words(fixed["parts"][0]["text"])) == sorted(rs.words(LATE_HOOK))
    assert s["parts"][0]["text"] == LATE_HOOK                       # the input is not changed
    s["parts"][0]["text"] = "Bu haqda hech kim gapirmaydi. Suv kam tozalanadi."     # the number is not in the hook
    assert rs.key_sentence_first(s) is None


def test_writer_fixes_only_the_hook_when_that_is_the_last_broken_rule():
    """The same topic failed 5 times on «the script broke the rules twice: the strongest fact ...»: a third, hook-only
    call now fixes it and the other 7 parts stay as they were."""
    from socialauto.reel.writer import ReelWriter

    class Claude:
        def __init__(self, hook):
            self.calls, self.hook = [], hook

        def generate_json(self, task, prompt, schema, system, **kw):
            self.calls.append(task)
            if task == "fix-reel-hook":
                if self.hook is None:
                    raise RuntimeError("claude down")
                return {"hook": self.hook, "key_fact": "27,7 foiz"}
            return _late_hook_script()

    claude = Claude("Atigi 27,7 foiz: Chirchiq oqova suvi shuncha tozalangan, qolgani daryoga ketadi.")
    out = ReelWriter(claude, "suv", "uz", rs.WORDS_PER_SECOND).script(topic("Chirchiq oqova suvi"), "")
    assert claude.calls == ["propose-reel-script", "propose-reel-script-fix", "fix-reel-hook"]
    assert out["parts"][0]["text"].startswith("Atigi 27,7 foiz") and not rs.problems(out)
    assert [p["text"] for p in out["parts"][1:]] == [p["text"] for p in _late_hook_script()["parts"][1:]]
    # Claude fails on the hook too: the local sentence move still saves the script.
    out = ReelWriter(Claude(None), "suv", "uz", rs.WORDS_PER_SECOND).script(topic("Chirchiq oqova suvi"), "")
    assert out["parts"][0]["text"].startswith("Chirchiq oqova suvi atigi 27,7 foiz") and not rs.problems(out)


def test_black_fade_is_cut_out_of_a_broll_clip():
    """Stock clips fading in from / out to black failed the whole reel («Qora kadrlar yo'q») on every retry."""
    from socialauto.reel.render import lit_window
    assert lit_window([], 6) is None                                 # nothing to cut
    assert lit_window([(0, 0.5)], 6) == (0.6, 6)                      # fade-in
    assert lit_window([(0, 0.5), (5.2, 6)], 6) == (0.6, 5.1)          # fade-in and fade-out
    assert lit_window([(1, 1.4), (5.5, 6)], 6) == (1.5, 5.4)          # the longest lit stretch wins
    assert lit_window([(0, 6)], 6) is None                            # all black: kept, the gate reports it


# --- dark B-roll: skipped when collecting, replaced on the next try ------------------------------------------------

def test_dark_photo_and_video_are_too_dark(tmp_path):
    from socialauto.reel.broll import too_dark
    dark, bright = tmp_path / "d.jpg", tmp_path / "b.jpg"
    Image.new("RGB", (270, 480), (8, 8, 12)).save(dark)
    Image.new("RGB", (270, 480), (60, 120, 160)).save(bright)
    assert too_dark(dark, "image") and not too_dark(bright, "image")
    night, day = tmp_path / "n.mp4", tmp_path / "day.mp4"
    for out, color in ((night, "0x060608"), (day, "0x4080a0")):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s=320x568:d=4",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)], check=True)
    assert too_dark(night, "video") and not too_dark(day, "video")
    assert not too_dark(tmp_path / "missing.mp4", "video")                 # unreadable: left to the render checks


def test_collect_skips_dark_and_rejected_clips(tmp_path):
    class DarkFirst:
        name = "Wikimedia Commons"

        def search(self, query, kind, limit=8):
            if kind != "image":
                return []
            out = []
            for n, color in (("dark", (5, 5, 5)), ("old", (90, 120, 160)), ("good", (80, 130, 150))):
                f = tmp_path / f"{n}.jpg"
                Image.new("RGB", (1080, 1920), color).save(f)
                out.append(Candidate("image", f.as_uri(), self.name, f"Water {n}", "A", "CC BY 4.0", f"page/{n}", 1080, 1920))
            return out
    part = uz_script()["parts"][:1]
    clips = collect(part, tmp_path / "w", [DarkFirst()], session=FileSession(), pause=0, avoid={"page/old"})
    assert clips[0].source_url == "page/good"


def test_dark_parts_from_the_after_render_checks():
    from socialauto.reel.checklist import Report, dark_parts
    parts = list(rs.PARTS)
    starts = [0, 4, 10, 17, 22, 28, 33, 40]
    rep = Report("after")
    rep.add("Video uzunligi", True, "47 soniya")
    rep.add("Kadr: Ochiq savol 1 (17.6s)", False, "qora kadr")
    rep.add("Kadr: Hook (0.6s)", True, "yaxshi")
    rep.add("Qora kadrlar yo'q", False, "45.1–45.9s")
    assert dark_parts(rep, parts, starts) == ["loop1", "cta"]
    ok = Report("after")
    ok.add("Qora kadrlar yo'q", True, "yo'q")
    assert dark_parts(ok, parts, starts) == []


def test_render_failing_on_dark_broll_gets_new_clips_on_retry(app, clock, long_voice):
    """A reel stopped on «Qora kadrlar yo'q» on every retry: the same dark clips were reused each time."""
    from socialauto.reel.broll import load_rejected, load_sources
    from socialauto.reel.checklist import Report
    renderer = app.workflow.reel_renderer
    real_render = renderer.render

    def render_dark_once(**kw):
        rr = real_render(**kw)
        if len(renderer.calls) == 1:
            rr.after = Report("after")
            rr.after.add("Kadr: Ochiq savol 1 (17.6s)", False, "qora kadr")
        return rr
    renderer.render = render_dark_once
    wf = app.workflow
    vid = wf.request_new()
    run_all_jobs(app)
    wf.topic_decision(app.store.pending_approval(vid, "topic")["id"], 0)
    run_all_jobs(app)
    wf.script_decision(app.store.pending_approval(vid, "script")["id"], "approve")
    wf.route_voice(wf.save_raw_voice(long_voice, "voice", ".wav"))
    run_all_jobs(app)
    work = wf.places.work(wf.reels.get(vid)["base"])
    first = renderer.calls[0]["clips"]
    assert "loop1" not in {c.part for c in load_sources(work)} and load_rejected(work)   # the dark clip is dropped
    for _ in range(6):
        if app.store.video(vid)["status"] == VIDEO_PENDING:
            break
        clock.now += timedelta(hours=1)
        run_all_jobs(app)
    assert app.store.video(vid)["status"] == VIDEO_PENDING and len(renderer.calls) == 2
    after = {c.part: c for c in load_sources(work)}
    assert after["loop1"].source_url not in load_rejected(work) and (work / after["loop1"].file).exists()
    assert [f for f in renderer.calls[1]["clips"] if "loop1" not in f] == [f for f in first if "loop1" not in f]

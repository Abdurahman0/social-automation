"""The finished reel comes to the owner as ONE package (video + every post text) to approve, reject or change; the
approved texts are exactly what goes to Buffer. Buffer gets a link that stays up until it posts (GitHub Pages)."""

import asyncio
import base64
import shutil
from pathlib import Path

import pytest
from conftest import dryrun_entries, run_all_jobs, video_pending
from PIL import Image

from socialauto.reel import buffer
from socialauto.reel.media_host import GitHubPagesHost, MediaHostError
from socialauto.store import BUFFER_PENDING, COVER_WAITING, REJECTED, VIDEO_PENDING
from socialauto.telegram_bot import TelegramBot, field_keyboard, package_message, reel_video_keyboard


def press(bot, data):
    return asyncio.run(bot.handle_button(111, data))


def test_package_has_every_post_text_before_the_owner_sees_it(app, long_voice):
    vid = video_pending(app, long_voice)
    assert app.store.video(vid)["status"] == VIDEO_PENDING
    caps = app.workflow.reels.get(vid)["captions"]
    assert set(caps) >= {"instagram", "youtube_title", "youtube_description", "linkedin", "story_text"}
    bot = TelegramBot(app)
    token = app.store.pending_approval(vid, "video")["id"]
    text = bot.package_text(vid, token)
    for want in ("Ekrandagi sarlavha", "YouTube sarlavhasi", "Suv yo'qotilishi", "YouTube tavsifi", "Instagram (Reels)",
                 "IG #suv", "LinkedIn matni", "Story matni", "Heshteglar", "Davomiyligi", "Sinov rejimi yoqiq"):
        assert want in text, want
    assert "{" not in text and "dryrun" not in text
    labels = [b.callback_data for row in reel_video_keyboard(token).inline_keyboard for b in row]
    assert labels == [f"v:a:{token}", f"v:d:{token}", f"v:e:{token}", f"v:g:{token}", f"v:r:{token}"]
    fields = [b.callback_data for row in field_keyboard(token).inline_keyboard for b in row]
    assert f"f:yt:{token}" in fields and f"v:b:{token}" in fields and all(len(c) <= 64 for c in fields)
    assert "video_approval" in [i.kind for i in app.outbox.pending(300)]
    # one Claude call for the texts, before the owner was asked
    assert [t for t, _ in app.claude.calls].count("write-captions") == 1


def test_owner_changes_a_text_and_it_goes_to_buffer_as_typed(app, long_voice, tmp_path):
    bot, wf = TelegramBot(app), app.workflow
    vid = video_pending(app, long_voice)
    token = app.store.pending_approval(vid, "video")["id"]
    assert bot.package_markup(f"v:d:{token}") is not None and press(bot, f"v:d:{token}")[0]
    ok, msg = press(bot, f"f:yt:{token}")
    assert ok and "YouTube sarlavhasi" in msg and "Suv yo'qotilishi" in msg          # shows the current text
    reply = asyncio.run(bot.handle_text(111, "x" * 101))
    assert reply.startswith("⚠️") and "100" in reply                                 # too long: asked again
    reply = asyncio.run(bot.handle_text(111, "Toshkent suvining 40% i yo'qoladi"))
    assert "o'zgartirildi" in reply
    assert wf.reels.get(vid)["captions"]["youtube_title"] == "Toshkent suvining 40% i yo'qoladi"
    assert "video_details" in [i.kind for i in app.outbox.pending(300)]
    assert "Toshkent suvining 40% i yo'qoladi" in bot.package_text(vid, token)
    # a video fix (new script version) writes the other texts again but keeps the owner's own one
    assert press(bot, f"v:e:{token}")[0]
    asyncio.run(bot.handle_text(111, "3-qismda boshqa video qo'y"))
    run_all_jobs(app)
    assert [t for t, _ in app.claude.calls].count("write-captions") == 2
    assert wf.reels.get(vid)["captions"]["youtube_title"] == "Toshkent suvining 40% i yo'qoladi"
    # approve -> cover -> Buffer with exactly these texts, no new caption call
    token = app.store.pending_approval(vid, "video")["id"]
    assert press(bot, f"v:a:{token}")[0] and app.store.video(vid)["status"] == COVER_WAITING
    assert not press(bot, f"f:ig:{token}")[0]                                          # the package is closed
    cover = tmp_path / "c.png"
    Image.new("RGB", (1080, 1920), (9, 9, 9)).save(cover)

    async def dl(dest):
        shutil.copyfile(cover, dest)
    asyncio.run(bot.handle_cover(dl))
    run_all_jobs(app)
    assert app.store.video(vid)["status"] == BUFFER_PENDING
    assert [t for t, _ in app.claude.calls].count("write-captions") == 2
    yt = next(e for e in dryrun_entries(app) if e.get("platform") == "buffer:youtube")
    assert yt["input"]["metadata"]["youtube"]["title"] == "Toshkent suvining 40% i yo'qoladi"
    assert yt["input"]["needsApproval"] is False


def test_reject_from_the_package(app, long_voice):
    bot = TelegramBot(app)
    vid = video_pending(app, long_voice)
    token = app.store.pending_approval(vid, "video")["id"]
    assert press(bot, f"v:r:{token}")[0] and app.store.video(vid)["status"] == REJECTED
    assert bot.package_markup(f"v:d:{token}") is False


def test_package_message_counts_owner_clips():
    class C:
        def __init__(self, provider):
            self.provider = provider
    script = {"title": "T", "key_fact": "40%", "hashtags": ["suv"], "sources": [{"name": "Kun.uz"}],
              "parts": [{"part": p, "text": "a"} for p in ("hook", "lead", "body1")]}
    render = {"duration": 41.2, "report": {"version": 3}}
    reel = {"captions": {"instagram": "<b>IG</b>", "youtube_title": "Y", "youtube_description": "D", "linkedin": "L",
                         "story_text": "S"}}
    text = package_message(script, render, reel, [C("Siz (A-roll)"), C("Pexels")], dry_run=False)
    assert "1 tasida sizning videongiz" in text and "v3" in text and "&lt;b&gt;IG" in text and "Sinov" not in text


def test_buffer_input_has_the_required_fields():
    q = buffer.queue_input("c", "t", "https://x/v.mp4", buffer.youtube_meta("Sarlavha"))
    assert q["needsApproval"] is False and q["metadata"]["youtube"]["type"] == "short"
    d = buffer.draft_input("c", "t", None, "https://x/c.jpg", {})
    assert d["needsApproval"] is False and d["saveToDraft"] is True


# --- the stable public link (GitHub Pages) ----------------------------------------------------------------------

class Resp:
    def __init__(self, code, body=None, headers=None):
        self.status_code = code
        self._body = body or {}
        self.headers = headers or {}

    def json(self):
        return self._body


class FakeGitHub:
    def __init__(self, private=False, exists=False):
        self.files: dict[str, bytes] = {}
        self.repo = {"private": private, "default_branch": "main"} if exists else None
        self.pages = False
        self.calls: list[tuple[str, str]] = []

    def request(self, method, url, headers=None, timeout=None, json=None):
        path = url.replace("https://api.github.com", "")
        self.calls.append((method, path))
        base = "/repos/ali/social-automation-media"
        if method == "GET" and path == base:
            return Resp(200, self.repo) if self.repo else Resp(404)
        if method == "POST" and path == "/user/repos":
            assert json["private"] is False and json["name"] == "social-automation-media"
            self.repo = {"private": False, "default_branch": "main"}
            self.files["README.md"] = b"x"
            return Resp(201)
        if path == base + "/pages":
            if method == "POST":
                self.pages = True
                return Resp(201)
            return Resp(200, {"html_url": "https://ali.github.io/social-automation-media/"}) if self.pages else Resp(404)
        if path.startswith(base + "/contents/"):
            rel = path[len(base + "/contents/"):]
            if method == "GET":
                return Resp(200, {"sha": "s"}) if rel in self.files else Resp(404)
            if method == "PUT":
                self.files[rel] = base64.b64decode(json["content"])
                return Resp(201)
            if method == "DELETE":
                self.files.pop(rel, None)
                return Resp(200)
        raise AssertionError((method, path))

    def head(self, url, timeout=None, allow_redirects=None):
        rel = url.replace("https://ali.github.io/social-automation-media/", "")
        ok = rel in self.files
        return Resp(200 if ok else 404, headers={"content-type": "video/mp4" if ok else "text/html"})


class Account:
    def __init__(self, token="t"):
        self._t = token

    def token(self):
        return self._t

    def info(self):
        return {"login": "ali"} if self._t else None


def test_pages_host_gives_a_stable_link_and_deletes_it_after_posting(tmp_path):
    gh = FakeGitHub()
    video = tmp_path / "reel_v2.mp4"
    video.write_bytes(b"\x00video")
    host = GitHubPagesHost(Account(), tmp_path / "media_host.json", session=gh, wait_seconds=1, poll_seconds=0)
    with host.links([video]) as (url,):
        assert url.startswith("https://ali.github.io/social-automation-media/r/") and url.endswith("/reel_v2.mp4")
    rel = url.replace("https://ali.github.io/social-automation-media/", "")
    assert gh.files[rel] == b"\x00video" and ".nojekyll" in gh.files and gh.pages
    assert host.publish(video) == url                                   # the same link again, no second upload
    assert sum(1 for m, p in gh.calls if m == "PUT" and p.endswith("reel_v2.mp4")) == 1
    assert host.forget(video) and rel not in gh.files and host.forget(video)


def test_pages_host_explains_what_is_missing(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"v")
    with pytest.raises(MediaHostError, match="GitHub ulanmagan"):
        GitHubPagesHost(Account(""), tmp_path / "m.json", session=FakeGitHub()).publish(video)
    with pytest.raises(MediaHostError, match="yopiq"):
        GitHubPagesHost(Account(), tmp_path / "m.json", session=FakeGitHub(private=True, exists=True)).publish(video)


def test_posted_reel_link_is_deleted(app, long_voice, tmp_path):
    class Host:
        def __init__(self):
            self.forgot = []

        def forget(self, path: Path):
            self.forgot.append(path.name)
            return True
    wf = app.workflow
    wf.media_host = Host()
    vid = video_pending(app, long_voice)
    bot = TelegramBot(app)
    press(bot, f"v:a:{app.store.pending_approval(vid, 'video')['id']}")
    cover = tmp_path / "c.png"
    Image.new("RGB", (1080, 1920)).save(cover)

    async def dl(dest):
        shutil.copyfile(cover, dest)
    asyncio.run(bot.handle_cover(dl))
    run_all_jobs(app)
    reel = wf.reels.get(vid)
    for pid in reel["drafts"].values():
        wf.buffer.live.add(pid)
    wf.refresh_buffer_state(vid, reel)
    assert wf.media_host.forgot and wf.media_host.forgot[0].endswith(".mp4")

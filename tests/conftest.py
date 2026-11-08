"""Shared test wiring: a temporary project (its own git repo), a fake Claude, a fake transcriber, fake B-roll, a fake
Remotion renderer, and a controllable clock. No network and no Remotion in unit tests."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from socialauto.app import build_app, reel_places  # noqa: E402
from socialauto.config import ReelConfig, load_settings  # noqa: E402
from socialauto.reel import script as rs  # noqa: E402
from socialauto.reel.broll import Candidate  # noqa: E402
from socialauto.reel.checklist import Report  # noqa: E402
from socialauto.reel.render import ReelRender  # noqa: E402
from socialauto.voice import Word  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
SAMPLE_VOICE = FIXTURES / "sample_voice_short.wav"
SAMPLE_TEXT = ("Octopuses have three hearts. Two pump blood to the gills, and one pumps it to the rest of the body. "
               "When an octopus swims, that third heart stops beating.")

UZ_PARTS = {
    "hook": "Toshkentda suvning 40 foizi quvurlarda yo'qoladi.",
    "lead": "Bu raqam Suv xo'jaligi vazirligi hisobotidan olingan va har yili takrorlanadi.",
    "body1": "Sabab eski quvurlar, ya'ni ellik yildan beri almashtirilmagan temir quvurlar, ular zanglab teshiladi.",
    "loop1": "Lekin eng qizig'i, yo'qotishni kim to'laydi?",
    "body2": "Yo'qolgan suvni ham nasos stansiyalari, ya'ni suvni haydaydigan katta mashinalar, elektr sarflab tortadi.",
    "loop2": "Xo'sh, buni qanday to'xtatish mumkin?",
    "body3": "Yangi aqlli hisoblagichlar, ya'ni sizib chiqishni darhol ko'rsatadigan qurilmalar, yo'qotishni ikki baravar kamaytiradi.",
    "cta": "Mahallangizda suv tez-tez o'chadimi? Izohda yozing va kuzatishda qoling.",
}


def uz_script(title="Suvning 40 foizi yo'qoladi", pad_words=40):
    parts = []
    for k in rs.PARTS:
        text = UZ_PARTS[k]
        if k == "body3" and pad_words:
            text += " " + " ".join(["suv"] * pad_words)
        parts.append({"part": k, "text": text, "broll": "water pipe leak",
                      "info": {"value": "40%", "label": "suv yo'qoladi"} if k == "hook" else None})
    return {"title": title, "topic": "Suv yo'qotilishi", "key_fact": "40 foizi",
            "terms": ["eski quvurlar", "nasos stansiyalari", "aqlli hisoblagichlar"], "parts": parts,
            "hashtags": ["suv", "Toshkent", "oqovasuv"], "sources": [{"name": "Suv xo'jaligi vazirligi", "url": "https://water.gov.uz/"}]}


def topic(title, url="https://kun.uz/news/1"):
    return {"title": title, "angle": "a", "why_now": "b", "hook_idea": "40%",
            "facts": [{"claim": "c", "source": "Kun.uz", "url": url, "date": "2026-11-01"}]}


class FakeClaude:
    """Answers every Claude task of the flow; records (task, prompt)."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.scripts: list[dict] = []
        self.error: Exception | None = None
        self.topics = [topic("Toshkentda suv yo'qotilishi 40%"), topic("Oqova suvni qayta ishlash Samarqandda"),
                       topic("Orol dengizi va chang bo'ronlari"), topic("Ichimlik suvi tarifi")]

    def generate_json(self, task, prompt, schema, system_prompt, tools=(), timeout=None):
        self.calls.append((task, prompt))
        if self.error:
            err, self.error = self.error, None
            raise err
        if task.startswith("research"):
            return {"format_insight": "Raqam bilan boshlangan qisqa videolar ko'proq ko'riladi", "topics": self.topics}
        if task == "reel-fix-plan":
            return {"summary": "3-qism videosi almashadi", "title": None,
                    "parts": [{"part": "body1", "broll": "old rusty pipe", "info": None, "subtitle_fix": None}]}
        if task == "write-captions":
            return {"instagram": "IG #suv", "youtube_title": "Suv yo'qotilishi", "youtube_description": "YT",
                    "linkedin": "LI", "story_text": "Yangi reel!"}
        if self.scripts:
            return self.scripts.pop(0)
        return uz_script(title=f"Suv mavzusi {len(self.calls)}")


class FakeTranscriber:
    """Words spread evenly over the clean file (a fixed text)."""

    def __init__(self, text: str):
        self.text = text
        self.calls = 0

    def transcribe(self, wav: Path, language: str = "uz") -> list[Word]:
        from socialauto.voice import wav_duration
        self.calls += 1
        words = self.text.split()
        d = wav_duration(wav)
        step = d / max(1, len(words))
        return [Word(w, i * step, (i + 0.9) * step) for i, w in enumerate(words)]


class FakeProvider:
    name = "Wikimedia Commons"

    def __init__(self, folder: Path):
        self.folder = folder
        self.n = 0

    def search(self, query, kind, limit=8):
        if kind != "image":
            return []
        self.n += 1
        f = self.folder / f"img{self.n}.jpg"
        Image.new("RGB", (1080, 1920), (20 + self.n * 10 % 200, 80, 120)).save(f)
        return [Candidate("image", f.as_uri(), self.name, f"Water photo {self.n}", "Photographer", "CC BY 4.0",
                          f"https://commons.wikimedia.org/wiki/File:{self.n}.jpg", 1080, 1920)]


class FileSession:
    """requests-like session that serves file:// URLs (tests only)."""

    def get(self, url, stream=False, timeout=None, headers=None):
        class R:
            def __init__(self, data):
                self.data = data

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def raise_for_status(self):
                pass

            def iter_content(self, n):
                yield self.data
        return R(Path(url[7:]).read_bytes())


class FakeReelRenderer:
    """Stands in for Remotion: a tiny file per version, frames and a passing checklist."""

    def __init__(self, places):
        self.places = places
        self.calls = []

    def render(self, *, base, script, clips, voice_wav, words, part_starts, lines, voice_seconds):
        self.calls.append({"clips": [c.file for c in clips], "starts": part_starts, "lines": len(lines)})
        n, path = self.places.next_export(base)
        path.write_bytes(b"\x00" * 100)
        fdir = self.places.work(base) / f"frames_v{n}"
        fdir.mkdir(parents=True, exist_ok=True)
        frames = []
        for k, p in enumerate(script["parts"]):
            f = fdir / f"{k + 1:02d}-{p['part']}.jpg"
            Image.new("RGB", (108, 192), (90, 120, 160)).save(f)
            frames.append((p["part"], part_starts[k], f))
        after = Report("after")
        after.add("Video uzunligi", True, "ok")
        return ReelRender(n, path, voice_seconds + 0.8, frames, [], after, {})


class Clock:
    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now += timedelta(**kw)


@pytest.fixture
def clock():
    return Clock(datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc))   # 11:00 in Tashkent


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "proj"
    (r / "assets").mkdir(parents=True)
    shutil.copytree(ROOT / "assets" / "fonts", r / "assets" / "fonts")
    (r / "assets" / "music").mkdir()
    (r / "docs").mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@e"], ["config", "user.name", "T"]):
        subprocess.run(["git", "-C", str(r), *args], check=True)
    return r


@pytest.fixture
def settings(root, tmp_path):
    shutil.copyfile(ROOT / "config.toml", root / "config.toml")      # never this computer's config.local.toml
    s = load_settings(root / "config.toml", root / "missing.env", root=root)
    assert not s.github.content_remote                                  # tests never push anywhere real
    reel = ReelConfig(work_base=str(tmp_path / "mb" / "_work"), exports=str(tmp_path / "mb" / "exports"),
                      research_dir=str(tmp_path / "mb" / "_work" / "research"))
    return replace(s, reel=reel, allowed_user_ids=frozenset({111}), telegram_token="x", dashboard_password="secret-pass",
                   buffer_api_key="", pexels_api_key="", pixabay_api_key="", dry_run=True)


@pytest.fixture
def fake_claude():
    return FakeClaude()


@pytest.fixture
def transcriber():
    return FakeTranscriber(rs.full_text(uz_script()))


@pytest.fixture
def app(settings, fake_claude, transcriber, clock, tmp_path, monkeypatch):
    import socialauto.reel.broll as bm
    monkeypatch.setattr(bm.requests, "Session", FileSession)      # B-roll "downloads" come from file:// in tests
    return build_app(settings, claude=fake_claude, transcriber=transcriber, clock=clock,
                     broll_providers=[FakeProvider(tmp_path)], reel_renderer=FakeReelRenderer(reel_places(settings)))


@pytest.fixture(scope="session")
def long_voice(tmp_path_factory):
    """~51 s of test voice (the short fixture looped): long enough for a 45-60 s reel."""
    out = tmp_path_factory.mktemp("voice") / "sample_voice_long.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "4", "-i", str(SAMPLE_VOICE), "-c", "copy",
                    str(out)], check=True)
    return out


def run_all_jobs(app, limit: int = 40, kinds_skip: tuple = ()) -> list[str]:
    """Run due jobs until none is left; returns the kinds that ran."""
    ran = []
    for _ in range(limit):
        job = app.jobs.claim_next(exclude=kinds_skip, now=app.clock().isoformat())
        if not job:
            break
        ran.append(job.kind)
        app.workflow.run_job(job)
    return ran


def outbox_kinds(app) -> list[str]:
    return [i.kind for i in app.outbox.pending(300)]


def script_pending(app, topic_index: int = 0) -> int:
    """research -> topic chosen -> the script waits for the owner."""
    vid = app.workflow.request_new()
    run_all_jobs(app)
    token = app.store.pending_approval(vid, "topic")["id"]
    app.workflow.topic_decision(token, topic_index)
    run_all_jobs(app)
    return vid


def voice_waiting(app) -> int:
    vid = script_pending(app)
    app.workflow.script_decision(app.store.pending_approval(vid, "script")["id"], "approve")
    return vid


def video_pending(app, voice: Path) -> int:
    vid = voice_waiting(app)
    app.workflow.route_voice(app.workflow.save_raw_voice(voice, "voice", ".wav"))
    run_all_jobs(app)
    return vid


def dryrun_entries(app) -> list[dict]:
    path = app.settings.dryrun_posts_path
    return json.loads(path.read_text()) if path.exists() else []

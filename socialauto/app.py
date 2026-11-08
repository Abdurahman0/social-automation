"""Builds every component once, so the bot service, the website, the CLI, the demo and tests share the wiring.

Owner law 15: nothing here can publish or schedule. Buffer is used for drafts only (a dry-run stand-in while
`dry_run` is on); YouTube and Instagram clients are read-only and live in the analytics collector.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .claude_budget import Budget
from .claude_client import ClaudeClient
from .config import Settings
from .db import KV, Database
from .jobs import JobQueue
from .lessons import Lessons, LessonsClaude
from .outbox import Outbox
from .platforms.dryrun import DryRunLog
from .platforms.instagram import GraphInstagramClient
from .platforms.tunnel import make_public_files
from .platforms.youtube import YouTubeStats
from .reel.align import RubaiSTT
from .reel.broll import make_providers
from .reel.buffer import DryRunBuffer, GraphBuffer
from .reel.naming import Places
from .reel.render import ReelRenderer
from .reel.writer import ReelWriter
from .store import Store
from .voice import Transcriber, WhisperTranscriber
from .workflow import Workflow


@dataclass
class App:
    settings: Settings
    db: Database
    store: Store
    jobs: JobQueue
    kv: KV
    outbox: Outbox
    lessons: Lessons
    budget: Budget
    claude: Any
    workflow: Workflow
    clock: Callable[[], datetime]


def utc_clock() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def youtube_stats(settings: Settings) -> YouTubeStats:
    return YouTubeStats(settings.resolve(settings.youtube.client_secret_file), settings.resolve(settings.youtube.token_file),
                        settings.youtube.expected_channel_id)


def instagram_stats(settings: Settings) -> GraphInstagramClient:
    return GraphInstagramClient(settings.resolve(settings.instagram.token_file), settings.instagram.graph_version,
                                settings.meta_app_id, settings.meta_app_secret)


def reel_places(settings: Settings) -> Places:
    """reels/ lives in the user's own content repo (data/content-repo), never in the code repo (Task 07)."""
    content = settings.resolve(settings.github.content_dir)
    return Places(settings.resolve(settings.reel.work_base), settings.resolve(settings.reel.exports),
                  settings.resolve(settings.reel.research_dir), content / settings.reel.reels_dir)


def build_app(settings: Settings, *, claude=None, transcriber: Transcriber | None = None,
              clock: Callable[[], datetime] | None = None, public_files=None, buffer=None, buffer_stats=None,
              broll_providers=None, reel_renderer=None) -> App:
    for d in (settings.data_dir, settings.logs_dir, settings.claude_workdir, settings.voices_dir):
        d.mkdir(parents=True, exist_ok=True)
    db = Database(settings.db_path)
    db.migrate()
    clock = clock or utc_clock
    store, jobs, kv, outbox = Store(db), JobQueue(db, clock), KV(db), Outbox(db)
    lessons = Lessons(db, settings.data_dir / "lessons.md")
    budget = Budget(db, clock)
    if claude is None:
        claude = ClaudeClient(settings.claude, settings.claude_workdir, budget)
    claude = LessonsClaude(claude, lessons)                 # prompts learn from earlier mistakes (law 11)
    if transcriber is None:
        stt = RubaiSTT(settings.resolve(settings.reel.stt_model))
        transcriber = stt if stt.available() else WhisperTranscriber(settings.voice, settings.root / "models" / "whisper")
    if buffer_stats is None and settings.buffer_api_key:
        buffer_stats = GraphBuffer(settings.buffer_api_key)            # read-only use: statistics, past posts
    if buffer is None:
        buffer = DryRunBuffer(DryRunLog(settings.dryrun_posts_path), clock) if settings.dry_run else (
            GraphBuffer(settings.buffer_api_key) if settings.buffer_api_key else None)
    places = reel_places(settings)
    from .content_repo import ContentRepo
    from .github_account import GitHubAccount
    content = ContentRepo(settings, GitHubAccount(settings))
    if broll_providers is None:
        broll_providers = make_providers(tuple(settings.reel.broll_providers), settings.pexels_api_key,
                                         settings.pixabay_api_key)
    if reel_renderer is None:
        reel_renderer = ReelRenderer(settings.root, places, settings.resolve(settings.video.music_dir),
                                     settings.reel.music_volume_db, settings.reel.remotion_concurrency)
    writer = ReelWriter(claude, settings.content.niche, settings.reel.language, settings.reel.words_per_second, lessons)
    if public_files is None and not settings.dry_run:
        public_files = make_public_files(settings.root)   # Buffer fetches the draft's video from a temporary link
    workflow = Workflow(settings, store, jobs, outbox, kv, transcriber, budget, lessons, clock, buffer=buffer,
                        buffer_stats=buffer_stats, reel_writer=writer, places=places, reel_renderer=reel_renderer,
                        broll_providers=broll_providers, public_files=public_files, content=content)
    return App(settings, db, store, jobs, kv, outbox, lessons, budget, claude, workflow, clock)

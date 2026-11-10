"""Settings: config.toml (no secrets) + .env (secrets). One Settings object is shared by every component."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ContentConfig:
    niche: str = "water and wastewater in Uzbekistan and the world"
    audience: str = "people in Uzbekistan who care about water, utilities and the environment"


@dataclass(frozen=True)
class ScheduleConfig:
    timezone: str = "Asia/Tashkent"
    slot_times: tuple[str, ...] = ("19:00",)
    propose_lead_hours: int = 30
    min_lead_minutes: int = 30


@dataclass(frozen=True)
class ClaudeConfig:
    binary: str = "claude"
    config_dir: Path = Path("~/.claude")
    model: str = ""
    effort: str = "medium"
    timeout_seconds: int = 600
    min_interval_seconds: int = 5
    limit_backoff_minutes: int = 60


@dataclass(frozen=True)
class VideoConfig:
    music_dir: str = "assets/music"
    telegram_max_mb: int = 48


@dataclass(frozen=True)
class VoiceConfig:
    whisper_model: str = "base"
    whisper_compute: str = "int8"
    max_download_mb: int = 20
    target_lufs: float = -14
    min_coverage: float = 0.75
    reminder_hours: float = 3


@dataclass(frozen=True)
class ReelConfig:
    """Task 04: the owner's own reel flow (water / wastewater, Uzbek, Remotion, Buffer drafts)."""
    language: str = "uz"                       # video language (uz | ru | en)
    work_base: str = "~/MediaBuffer/_work"     # outside any cloud-synced folder
    exports: str = "~/MediaBuffer/exports"
    research_dir: str = "~/MediaBuffer/_work/research"
    reels_dir: str = "reels"                   # inside the content repo (github.content_dir)
    stt_model: str = "models/rubaistt-medium-int8-ct2"
    words_per_second: float = 2.2
    recent_posts: int = 30
    broll_providers: tuple[str, ...] = ("pexels", "pixabay", "commons")
    remotion_concurrency: int = 1
    music_volume_db: float = -20
    live_check_minutes: int = 15


@dataclass(frozen=True)
class YouTubeConfig:
    client_secret_file: str = "secrets/youtube_client_secret.json"
    token_file: str = "secrets/youtube_token.json"
    expected_channel_id: str = ""


@dataclass(frozen=True)
class InstagramConfig:
    graph_version: str = "v27.0"
    token_file: str = "secrets/instagram.json"


@dataclass(frozen=True)
class WebConfig:
    host: str = "127.0.0.1"
    port: int = 8090
    public_url: str = "http://localhost:8090"


@dataclass(frozen=True)
class GitHubConfig:
    """Task 07: the code repo is read-only (updates only); content goes to the user's OWN content repo."""
    code_repo: str = "Abdurahman0/social-automation"     # upstream code: fetch/pull only, never written by the app
    content_repo: str = "social-automation-content"     # created (private) in the user's own GitHub account
    content_dir: str = "data/content-repo"              # local clone of the content repo (git-ignored)
    content_remote: str = ""                            # optional fixed remote (SSH URL or a local bare repo)
    content_mode: str = ""                              # "" (not chosen yet) | "new" | "existing" (Task 09)
    content_existing: str = ""                          # "owner/name" of the user's existing repo (Task 09)
    oauth_client_id: str = ""                           # public id of the GitHub OAuth app (device flow, no secret)
    update_check_hours: int = 6


@dataclass(frozen=True)
class AnalyticsConfig:
    refresh_minutes: int = 30
    reports_refresh_hours: int = 6


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    dry_run: bool = True
    owner_language: str = "uz"
    content: ContentConfig = field(default_factory=ContentConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    reel: ReelConfig = field(default_factory=ReelConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    instagram: InstagramConfig = field(default_factory=InstagramConfig)
    web: WebConfig = field(default_factory=WebConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    # from .env
    telegram_token: str = ""
    allowed_user_ids: frozenset[int] = frozenset()
    dashboard_password: str = ""
    meta_app_id: str = ""
    meta_app_secret: str = ""
    buffer_api_key: str = ""
    pexels_api_key: str = ""
    pixabay_api_key: str = ""

    # --- paths -------------------------------------------------------------------------------
    def resolve(self, value: str | Path) -> Path:
        p = Path(os.path.expanduser(str(value)))
        return p if p.is_absolute() else self.root / p

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def work_dir(self) -> Path:
        return self.root / "data" / "videos"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "socialauto.db"

    @property
    def claude_workdir(self) -> Path:
        return self.data_dir / "claude-sandbox"

    @property
    def voices_dir(self) -> Path:
        return self.data_dir / "voices"

    @property
    def dryrun_posts_path(self) -> Path:
        return self.data_dir / "dryrun_posts.json"


def _build(cls, raw: dict[str, Any] | None):
    raw = raw or {}
    known = {f.name: f for f in fields(cls)}
    kwargs = {}
    for k, v in raw.items():
        if k not in known:
            continue
        if isinstance(v, list):
            v = tuple(v)
        if known[k].type in ("Path",) or k == "config_dir":
            v = Path(os.path.expanduser(str(v)))
        kwargs[k] = v
    return cls(**kwargs)


def parse_ids(text: str) -> frozenset[int]:
    out = set()
    for part in (text or "").replace(" ", "").split(","):
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return frozenset(out)


def load_settings(config_path: Path | None = None, env_path: Path | None = None, root: Path | None = None) -> Settings:
    root = root or ROOT
    config_path = config_path or root / "config.toml"
    env_path = env_path or root / ".env"
    raw: dict[str, Any] = {}
    if config_path.exists():
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    local = config_path.with_name("config.local.toml")         # this computer's own choices (git-ignored)
    if local.exists():
        raw = merge(raw, tomllib.loads(local.read_text(encoding="utf-8")))
    env: dict[str, str] = {}
    if env_path.exists():
        from dotenv import dotenv_values
        env = {k: v or "" for k, v in dotenv_values(env_path).items()}
    get = lambda k: os.environ.get(k) or env.get(k, "")   # noqa: E731
    claude = _build(ClaudeConfig, raw.get("claude"))
    if Path(os.path.expanduser("~/.claude-youtube")) == claude.config_dir:
        raise ValueError("claude.config_dir must not be ~/.claude-youtube (account 2 belongs to the YouTube bot)")
    return Settings(
        root=root,
        dry_run=bool(raw.get("dry_run", True)),
        owner_language=str(raw.get("owner_language", "uz")),
        content=_build(ContentConfig, raw.get("content")),
        schedule=_build(ScheduleConfig, raw.get("schedule")),
        claude=claude,
        video=_build(VideoConfig, raw.get("video")),
        voice=_build(VoiceConfig, raw.get("voice")),
        reel=_build(ReelConfig, raw.get("reel")),
        youtube=_build(YouTubeConfig, raw.get("youtube")),
        instagram=_build(InstagramConfig, raw.get("instagram")),
        web=_build(WebConfig, raw.get("web")),
        analytics=_build(AnalyticsConfig, raw.get("analytics")),
        github=_build(GitHubConfig, raw.get("github")),
        telegram_token=get("TELEGRAM_BOT_TOKEN"),
        allowed_user_ids=parse_ids(get("TELEGRAM_ALLOWED_USER_IDS")),
        dashboard_password=get("DASHBOARD_PASSWORD"),
        meta_app_id=get("META_APP_ID"),
        meta_app_secret=get("META_APP_SECRET"),
        buffer_api_key=get("BUFFER_API_KEY"),
        pexels_api_key=get("PEXELS_API_KEY"),
        pixabay_api_key=get("PIXABAY_API_KEY"),
    )


def with_overrides(settings: Settings, **kwargs: Any) -> Settings:
    return replace(settings, **kwargs)


def merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def set_local_value(root: Path, section: str | None, key: str, value: Any) -> None:
    """Save one setting of THIS computer in config.local.toml (git-ignored), so config.toml stays as in the code
    repo and updates are always a clean fast-forward."""
    path = root / "config.local.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if section:
        data.setdefault(section, {})[key] = value
    else:
        data[key] = value
    top = [f"{k} = {_toml_value(v)}" for k, v in data.items() if not isinstance(v, dict)]
    parts = ["# This computer's own settings (not in git). They override config.toml.", *top]
    for sec, vals in data.items():
        if isinstance(vals, dict):
            parts += ["", f"[{sec}]", *[f"{k} = {_toml_value(v)}" for k, v in vals.items()]]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(parts) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def set_config_value(path: Path, section: str | None, key: str, value: str) -> None:
    """Rewrite one `key = value` line of config.toml in place (keeps comments). `value` is TOML text."""
    lines = path.read_text(encoding="utf-8").splitlines()
    current = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            current = s[1:-1].strip()
            continue
        if current == section and s.split("=", 1)[0].strip() == key and "=" in s:
            comment = ""
            if "#" in line.split("=", 1)[1]:
                comment = "  #" + line.split("=", 1)[1].split("#", 1)[1]
            lines[i] = f"{key} = {value}{comment}"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    raise KeyError(f"{section}.{key} not found in {path}")

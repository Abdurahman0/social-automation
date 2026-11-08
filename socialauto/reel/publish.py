"""Step 5-6: the approved reel goes to git (`reels/<date>-<topic>/`) and to Buffer as DRAFTS; later the story step.

- git: video + the owner's cover + research file + script + source list, committed (only those paths) and pushed to
  `main` when a remote exists (never force). Files over 50 MB go through Git LFS. Without a remote the commit stays
  local and the site shows "kutilmoqda".
- Buffer: drafts for Instagram (reel), YouTube and LinkedIn with captions in the owner's style (style file learned
  from the owner's previous Buffer posts). Never scheduled or published: the owner approves and schedules in Buffer.
  Buffer fetches the video from a URL, so the files are served for a moment through the free quick tunnel.
- Story: when the reel is live (Buffer reports it sent, with its link), a story draft with the cover image and the
  reel link in the reminder sticker field; the owner also gets the image + link in Telegram.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .buffer import BufferClient, instagram_reel_meta, story_meta, youtube_meta

log = logging.getLogger(__name__)

LFS_BYTES = 50 * 1024 * 1024

CAPTION_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "required": ["instagram", "youtube_title", "youtube_description", "linkedin", "story_text"],
    "properties": {
        "instagram": {"type": "string", "description": "Instagram reel caption with hashtags, in the owner's style"},
        "youtube_title": {"type": "string", "description": "max 90 characters"},
        "youtube_description": {"type": "string"},
        "linkedin": {"type": "string", "description": "a slightly more professional LinkedIn post"},
        "story_text": {"type": "string", "description": "max 60 characters, invites to watch the new reel"},
    },
}
STYLE_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["style", "examples"],
    "properties": {"style": {"type": "string"}, "examples": {"type": "array", "items": {"type": "string"}, "maxItems": 5}},
}
DEFAULT_STYLE = ("Uzbek (Latin). Short first line that repeats the hook with one number. 2-4 short paragraphs, plain "
                 "words, one question to the audience, then 5-8 hashtags (#suv #oqovasuv #Uzbekistan ...). No clickbait.")


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    import os
    env = dict(os.environ)
    env["PATH"] = f"{repo / 'bin'}{os.pathsep}{env.get('PATH', '')}"      # git-lfs lives in ./bin (install_git_lfs.sh)
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check, timeout=600, env=env)


def has_remote(repo: Path) -> bool:
    return bool(git(repo, "remote", check=False).stdout.strip())


def lfs_available(repo: Path) -> bool:
    return git(repo, "lfs", "version", check=False).returncode == 0


@dataclass
class GitResult:
    folder: str
    committed: bool
    pushed: bool
    lfs_files: list[str]
    note: str


def publish_git(repo: Path, reels_dir: Path, base: str, files: dict[str, Path], title: str) -> GitResult:
    """Copy into reels/<base>/ and commit exactly those paths; push to main when a remote exists."""
    dest = reels_dir / base
    dest.mkdir(parents=True, exist_ok=True)
    rel_paths, lfs = [], []
    for name, src in files.items():
        target = dest / name
        shutil.copyfile(src, target)
        rel = str(target.relative_to(repo))
        rel_paths.append(rel)
        if target.stat().st_size > LFS_BYTES:
            if not lfs_available(repo):
                raise RuntimeError("a file is over 50 MB and Git LFS is not installed (Linux: scripts/install_git_lfs.sh, macOS: brew install git-lfs, Windows: winget install GitHub.GitLFS)")
            git(repo, "lfs", "track", rel)
            lfs.append(rel)
    if lfs:
        rel_paths.append(".gitattributes")
    git(repo, "add", "--", *rel_paths)
    staged = git(repo, "diff", "--cached", "--name-only", "--", *rel_paths).stdout.strip()
    committed = False
    if staged:
        git(repo, "commit", "-m", f"Reel: {title} ({base[:10]})", "--", *rel_paths)
        committed = True
    pushed, note = False, "GitHub ulanmagan: o'zgarish shu kompyuterda saqlandi (kutilmoqda)"
    if has_remote(repo):
        res = git(repo, "push", "origin", "HEAD:main", check=False)        # never --force
        pushed = res.returncode == 0
        if not pushed:                                                     # details to the log, not the UI (law 6)
            logging.getLogger("socialauto.publish").warning("git push failed: %s", res.stderr.strip()[:300])
        note = ("GitHub'ga yuklandi" if pushed else
                "GitHub'ga yuklab bo'lmadi (ruxsat yoki internet yo'q): o'zgarish shu kompyuterda saqlandi")
    return GitResult(str(dest.relative_to(repo)), committed, pushed, lfs, note)


def learn_style(claude, buffer: BufferClient | None, style_file: Path) -> str:
    """The owner's caption style, learned once from the previous Buffer posts (kept in a style file)."""
    if style_file.exists():
        return style_file.read_text(encoding="utf-8")
    posts = []
    if buffer is not None and not buffer.dry_run:
        try:
            posts = [p["text"] for p in buffer.sent_posts(30) if p.get("text")]
        except Exception as exc:        # noqa: BLE001
            log.warning("Could not read previous Buffer posts: %s", exc)
    if not posts:
        return DEFAULT_STYLE                     # not saved: replaced as soon as real posts can be read
    res = claude.generate_json("caption-style", "Describe the caption style of these posts (language, length, "
                               "structure, tone, emoji use, hashtags) so a writer can copy it, and pick up to 5 "
                               "representative examples verbatim:\n\n" + "\n---\n".join(posts[:30]),
                               STYLE_SCHEMA, "You analyse a social media author's writing style. Answer with JSON.")
    text = res["style"] + "\n\nExamples:\n" + "\n---\n".join(res["examples"])
    style_file.parent.mkdir(parents=True, exist_ok=True)
    style_file.write_text(text, encoding="utf-8")
    return text


def write_captions(claude, script: dict, style: str, language: str) -> dict:
    from .script import full_text
    return claude.generate_json(
        "write-captions", f"Write the post texts for this reel in {language}, in the author's style below.\n\n"
        f"STYLE:\n{style}\n\nREEL TITLE: {script['title']}\nKEY FACT: {script['key_fact']}\nSPOKEN TEXT:\n"
        f"{full_text(script)}\nHASHTAGS: {' '.join('#' + h.lstrip('#') for h in script.get('hashtags', []))}\n"
        f"SOURCES: {', '.join(s['name'] for s in script.get('sources', []))}",
        CAPTION_SCHEMA, "You write social media captions. Facts only from the given text. Answer with JSON.")


@contextmanager
def _local_urls(files: list[Path]):
    yield [str(f) for f in files]


def create_drafts(buffer: BufferClient, captions: dict, video: Path, public_files=None) -> dict[str, str]:
    """One draft per connected channel (instagram / youtube / linkedin). Returns {service: post id}."""
    wanted = {"instagram", "youtube", "linkedin"}
    channels = [c for c in buffer.channels() if c.get("service") in wanted]
    if not channels:
        raise RuntimeError("no Instagram / YouTube / LinkedIn channel is connected in Buffer")
    out: dict[str, str] = {}
    links = public_files([video]) if (public_files and not buffer.dry_run) else _local_urls([video])
    with links as (video_url,):
        for ch in channels:
            svc = ch["service"]
            if svc in out:
                continue
            if svc == "instagram":
                pid = buffer.create_draft(ch, captions["instagram"], video_url, None, instagram_reel_meta())
            elif svc == "youtube":
                pid = buffer.create_draft(ch, captions["youtube_description"], video_url, None,
                                          youtube_meta(captions["youtube_title"]))
            else:
                pid = buffer.create_draft(ch, captions["linkedin"], video_url, None, {})
            out[svc] = pid
    return out


def rename_drafts(buffer: BufferClient, drafts: dict[str, str], captions: dict, new_title: str) -> None:
    """The publish date changed: the YouTube draft title (and the texts) follow."""
    for svc, pid in drafts.items():
        if svc == "youtube":
            buffer.edit_post(pid, metadata=youtube_meta(new_title))


def live_link(buffer: BufferClient, drafts: dict[str, str]) -> str | None:
    pid = drafts.get("instagram")
    if not pid:
        return None
    p = buffer.post(pid)
    if p.get("status") == "sent" and p.get("externalLink"):
        return p["externalLink"]
    return None


def create_story_draft(buffer: BufferClient, cover: Path, link: str, text: str, public_files=None) -> str | None:
    ig = next((c for c in buffer.channels() if c.get("service") == "instagram"), None)
    if not ig:
        return None
    links = public_files([cover]) if (public_files and not buffer.dry_run) else _local_urls([cover])
    with links as (image_url,):
        return buffer.create_draft(ig, text, None, image_url, story_meta(link, text), reminder=True)


__all__ = ["publish_git", "learn_style", "write_captions", "create_drafts", "rename_drafts", "live_link",
           "create_story_draft", "GitResult", "json"]

"""Step 5-6: the approved reel goes to git (`reels/<date>-<topic>/`) and into Buffer's QUEUE; later the story step.

- git: video + the owner's cover + research file + script + source list go to the user's OWN content repo
  (socialauto/content_repo.py, Task 07) — never to the code repo. Files over 50 MB go through Git LFS.
- Buffer: queued posts for Instagram (reel), YouTube and LinkedIn with captions in the owner's style (style file
  learned from the owner's previous Buffer posts). The owner already approved the reel in Telegram; Buffer posts it at
  the channel's next free posting-schedule time (owner, 2026-11-09). The bot never picks the time itself.
  Buffer fetches the video from a URL, so the files are served for a moment through the free quick tunnel.
- Story: when the reel is live (Buffer reports it sent, with its link), a story draft with the cover image and the
  reel link in the reminder sticker field; the owner also gets the image + link in Telegram.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .buffer import BufferClient, instagram_reel_meta, story_meta, youtube_meta

log = logging.getLogger(__name__)

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


def post_state(p: dict) -> dict:
    """What the website shows about one Buffer post (no ids)."""
    return {"status": p.get("status") or "", "due_at": p.get("dueAt"), "sent_at": p.get("sentAt"),
            "link": p.get("externalLink")}


def queue_posts(buffer: BufferClient, captions: dict, video: Path, public_files=None) -> tuple[dict[str, str], dict]:
    """One queued post per connected channel (instagram / youtube / linkedin).
    Returns ({service: post id}, {service: post_state})."""
    wanted = {"instagram", "youtube", "linkedin"}
    channels = [c for c in buffer.channels() if c.get("service") in wanted]
    if not channels:
        raise RuntimeError("no Instagram / YouTube / LinkedIn channel is connected in Buffer")
    out: dict[str, str] = {}
    states: dict[str, dict] = {}
    links = public_files([video]) if (public_files and not buffer.dry_run) else _local_urls([video])
    with links as (video_url,):
        for ch in channels:
            svc = ch["service"]
            if svc in out:
                continue
            if svc == "instagram":
                p = buffer.queue_post(ch, captions["instagram"], video_url, instagram_reel_meta())
            elif svc == "youtube":
                p = buffer.queue_post(ch, captions["youtube_description"], video_url,
                                      youtube_meta(captions["youtube_title"]))
            else:
                p = buffer.queue_post(ch, captions["linkedin"], video_url, {})
            out[svc] = p["id"]
            states[svc] = post_state(p)
    return out, states


def rename_drafts(buffer: BufferClient, drafts: dict[str, str], captions: dict, new_title: str) -> None:
    """The publish date changed: the YouTube title follows while the post is still a draft. Queued posts keep their
    text (Buffer already owns them)."""
    from .buffer import BufferError
    for svc, pid in drafts.items():
        if svc == "youtube":
            try:
                buffer.edit_post(pid, metadata=youtube_meta(new_title))
            except BufferError as exc:
                log.info("YouTube title not renamed: %s", exc)


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


__all__ = ["learn_style", "write_captions", "queue_posts", "post_state", "rename_drafts", "live_link",
           "create_story_draft", "GitResult", "json"]

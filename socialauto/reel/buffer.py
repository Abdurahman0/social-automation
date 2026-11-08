"""Buffer (GraphQL API, https://api.buffer.com, personal API key from .env BUFFER_API_KEY; all Buffer plans include API
access). Used for:
- research: post metrics (views, shares, comments, averageTimeWatched…; personal keys only, refreshed ~daily);
- caption style: the owner's previous sent posts;
- DRAFTS for Instagram (reel), YouTube and LinkedIn: `createPost(saveToDraft: true)` — owner law 15: the bot NEVER
  schedules or publishes. `saveToDraft: true` is hard-coded below; no argument can turn it off, no due time is ever
  sent, and no other create/share mutation exists in this module. The owner approves and schedules in Buffer;
- live detection: Post.status == sent, sentAt, externalLink;
- the story step: an Instagram story draft (cover image) with the reel link in the reminder sticker field
  (Buffer has no link-sticker field; Instagram's API cannot publish link stickers at all), plus a Telegram message;
- renaming: `editPost` updates a DRAFT's text / YouTube title when the publish date changes (refused for any post that
  is no longer a draft).
Errors: HTTP is always 200; fixable problems come back as typed MutationError members, system ones in `errors`.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

import requests

from ..platforms.dryrun import DryRunLog

log = logging.getLogger(__name__)

API = "https://api.buffer.com"


class BufferError(RuntimeError):
    pass


class BufferAuthError(BufferError):
    pass


class BufferRateLimit(BufferError):
    pass


POST_FIELDS = "id text status sentAt dueAt externalLink channelId channelService createdAt"

Q_ORGS = "query { account { organizations { id name } } }"
Q_CHANNELS = """query Channels($org: OrganizationId!) {
  channels(input: { organizationId: $org }) { id name displayName service isDisconnected }
}"""
Q_CHANNELS_VIEW = """query Channels($org: OrganizationId!) {
  channels(input: { organizationId: $org }) { id name displayName service isDisconnected avatar }
}"""
Q_POSTS = """query Posts($org: OrganizationId!, $status: [PostStatus!], $channels: [ChannelId!], $after: String, $first: Int) {
  posts(after: $after, first: $first, input: { organizationId: $org, filter: { status: $status, channelIds: $channels } }) {
    pageInfo { endCursor hasNextPage }
    edges { node { %s metrics { type name value unit } } }
  }
}""" % POST_FIELDS
M_CREATE = """mutation Create($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id text status } }
    ... on MutationError { message }
  }
}"""
M_EDIT = """mutation Edit($input: EditPostInput!) {
  editPost(input: $input) {
    ... on PostActionSuccess { post { id text } }
    ... on MutationError { message }
  }
}"""


class BufferClient(Protocol):
    dry_run: bool

    def channels(self) -> list[dict]: ...
    def create_draft(self, channel: dict, text: str, video_url: str | None, image_url: str | None,
                     metadata: dict, reminder: bool = False) -> str: ...
    def edit_post(self, post_id: str, text: str | None = None, metadata: dict | None = None) -> None: ...
    def post(self, post_id: str) -> dict: ...
    def sent_posts(self, limit: int = 30) -> list[dict]: ...


def draft_input(channel_id: str, text: str, video_url: str | None, image_url: str | None, metadata: dict,
                reminder: bool = False) -> dict:
    """The one and only createPost input this project ever sends: always `saveToDraft: true`, never a due time."""
    assets = []
    if video_url:
        assets.append({"video": {"url": video_url, "metadata": {"thumbnailOffset": 0}}})
    if image_url:
        assets.append({"image": {"url": image_url}})
    inp = {"channelId": channel_id, "text": text, "schedulingType": "notification" if reminder else "automatic",
           "mode": "addToQueue", "assets": assets}
    if metadata:
        inp["metadata"] = metadata
    inp["saveToDraft"] = True                       # set last, so nothing above can ever override it
    return inp


class GraphBuffer:
    dry_run = False

    def __init__(self, api_key: str, session: requests.Session | None = None):
        if not api_key:
            raise BufferAuthError("BUFFER_API_KEY is not set")
        self.key = api_key
        self.s = session or requests.Session()
        self._org: str | None = None

    def gql(self, query: str, variables: dict | None = None) -> dict:
        try:
            r = self.s.post(API, json={"query": query, "variables": variables or {}},
                            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                            timeout=60)
        except requests.RequestException as exc:
            raise BufferError(f"network: {type(exc).__name__}") from exc
        try:
            body = r.json()
        except ValueError as exc:
            raise BufferError(f"HTTP {r.status_code}: not JSON") from exc
        for err in body.get("errors") or []:
            code = (err.get("extensions") or {}).get("code", "")
            if code in ("UNAUTHENTICATED", "UNAUTHORIZED", "FORBIDDEN"):       # Buffer says UNAUTHENTICATED for a bad key
                raise BufferAuthError(err.get("message", code))
            if code == "RATE_LIMIT_EXCEEDED":
                raise BufferRateLimit(err.get("message", code))
            raise BufferError(f"{code}: {err.get('message', '')}"[:300])
        return body.get("data") or {}

    def org(self) -> str:
        if not self._org:
            orgs = self.gql(Q_ORGS)["account"]["organizations"]
            if not orgs:
                raise BufferError("the Buffer account has no organization")
            self._org = orgs[0]["id"]
        return self._org

    def channels(self) -> list[dict]:
        return [c for c in self.gql(Q_CHANNELS, {"org": self.org()})["channels"] if not c.get("isDisconnected")]

    def channels_view(self) -> list[dict]:
        """Channels with their avatar for the website (read-only). Falls back to the plain list if Buffer's schema
        has no avatar field, so the drafts' own channel lookup is never affected."""
        try:
            data = self.gql(Q_CHANNELS_VIEW, {"org": self.org()})["channels"]
        except BufferAuthError:
            raise
        except BufferError:
            data = self.gql(Q_CHANNELS, {"org": self.org()})["channels"]
        return [c for c in data if not c.get("isDisconnected")]

    def create_draft(self, channel: dict, text: str, video_url: str | None, image_url: str | None,
                     metadata: dict, reminder: bool = False) -> str:
        """A DRAFT post. `reminder`: Instagram story drafts use Buffer's reminder publishing (the owner posts it)."""
        inp = draft_input(channel["id"], text, video_url, image_url, metadata, reminder)
        res = self.gql(M_CREATE, {"input": inp})["createPost"]
        if "post" not in res:
            raise BufferError(res.get("message", "createPost failed"))
        return res["post"]["id"]

    def edit_post(self, post_id: str, text: str | None = None, metadata: dict | None = None) -> None:
        """Edit a DRAFT only (text / metadata). Never touches scheduling."""
        state = self.post(post_id)
        if state.get("status") != "draft":
            raise BufferError("only drafts are edited by the bot; this post is no longer a draft")
        inp: dict[str, Any] = {"id": post_id}
        if text is not None:
            inp["text"] = text
        if metadata:
            inp["metadata"] = metadata
        res = self.gql(M_EDIT, {"input": inp})["editPost"]
        if "post" not in res:
            raise BufferError(res.get("message", "editPost failed"))

    def post(self, post_id: str) -> dict:
        """A post's state, found through the documented posts(...) listing (sent ones first, then the rest)."""
        for status in (["sent"], ["draft", "scheduled", "sending", "needs_approval", "error"]):
            data = self.gql(Q_POSTS, {"org": self.org(), "status": status, "channels": None, "after": None,
                                      "first": 50})["posts"]
            for e in data["edges"]:
                if e["node"]["id"] == post_id:
                    return e["node"]
        return {}

    def sent_posts(self, limit: int = 30, channel_ids: list[str] | None = None) -> list[dict]:
        out, after = [], None
        while len(out) < limit:
            data = self.gql(Q_POSTS, {"org": self.org(), "status": ["sent"], "channels": channel_ids,
                                      "after": after, "first": min(50, limit - len(out))})["posts"]
            out += [e["node"] for e in data["edges"]]
            if not data["pageInfo"]["hasNextPage"]:
                break
            after = data["pageInfo"]["endCursor"]
        return out[:limit]


class DryRunBuffer:
    """No network (law 4): drafts are written to data/dryrun_posts.json; nothing ever goes live."""
    dry_run = True

    def __init__(self, log_file: DryRunLog, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.log = log_file
        self.clock = clock
        self.live: set[str] = set()                  # tests mark drafts as "went live"

    def channels(self) -> list[dict]:
        return [{"id": "dry-ig", "name": "Instagram", "service": "instagram"},
                {"id": "dry-yt", "name": "YouTube", "service": "youtube"},
                {"id": "dry-li", "name": "LinkedIn", "service": "linkedin"}]

    def create_draft(self, channel: dict, text: str, video_url: str | None, image_url: str | None,
                     metadata: dict, reminder: bool = False) -> str:
        pid = "dryrun-buffer-" + secrets.token_hex(4)
        inp = draft_input(channel["id"], text, video_url, image_url, metadata, reminder)
        self.log.append({"platform": f"buffer:{channel['service']}", "remote_id": pid, "kind": "draft", "input": inp})
        return pid

    def edit_post(self, post_id: str, text: str | None = None, metadata: dict | None = None) -> None:
        if post_id in self.live:
            raise BufferError("only drafts are edited by the bot; this post is no longer a draft")
        self.log.append({"platform": "buffer", "remote_id": post_id, "kind": "edit", "text": text,
                         "metadata": metadata or {}})

    def post(self, post_id: str) -> dict:
        if post_id in self.live:
            return {"id": post_id, "status": "sent", "sentAt": self.clock().isoformat(),
                    "externalLink": "https://www.instagram.com/reel/dry-run-example/"}
        return {"id": post_id, "status": "draft", "sentAt": None, "externalLink": None}

    def sent_posts(self, limit: int = 30, channel_ids: list[str] | None = None) -> list[dict]:
        return []


def instagram_reel_meta() -> dict:
    return {"instagram": {"type": "reel", "shouldShareToFeed": True}}


def youtube_meta(title: str) -> dict:
    return {"youtube": {"title": title[:100], "categoryId": "27", "privacy": "public", "madeForKids": False}}


def story_meta(link: str, text: str) -> dict:
    return {"instagram": {"type": "story", "shouldShareToFeed": False, "stickerFields": {"text": text[:100], "other": link}}}


def metric_summary(posts: list[dict]) -> dict:
    """Average views/shares/comments/watch time over sent posts (for research: what format works)."""
    sums: dict[str, list[float]] = {}
    for p in posts:
        for m in p.get("metrics") or []:
            try:
                sums.setdefault(m["type"], []).append(float(m["value"]))
            except (TypeError, ValueError, KeyError):
                continue
    return {k: round(sum(v) / len(v), 1) for k, v in sums.items() if v}


def top_posts(posts: list[dict], n: int = 5) -> list[dict]:
    def views(p: dict) -> float:
        return next((float(m["value"]) for m in p.get("metrics") or [] if m.get("type") == "views"), 0.0)
    return sorted(posts, key=views, reverse=True)[:n]


__all__ = ["GraphBuffer", "DryRunBuffer", "BufferError", "BufferAuthError", "BufferRateLimit", "metric_summary",
           "top_posts", "instagram_reel_meta", "youtube_meta", "story_meta", "json"]

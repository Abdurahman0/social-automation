"""Instagram Graph API (Instagram API with Facebook Login) — READ-ONLY: account and media statistics.

Owner law 15: the bot never publishes anything. There are no container / publish / story calls here and the token is
requested only with read permissions: instagram_basic, instagram_manage_insights, pages_show_list,
pages_read_engagement. Tokens (secrets/instagram.json, chmod 600, written by `python -m socialauto instagram-connect`):
a long-lived user token (~60 days) refreshed automatically while valid (< 10 days left), and the Page token derived from
it (no fixed expiry), used for the calls. Metric names follow the 2026 docs (`views`; `impressions`/`plays` are gone).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import requests


log = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/{version}/"
REFRESH_BEFORE = timedelta(days=10)
PERMISSIONS = ("instagram_basic", "instagram_manage_insights", "pages_show_list", "pages_read_engagement")
MEDIA_FIELDS = "id,caption,media_type,media_product_type,permalink,thumbnail_url,media_url,timestamp,like_count,comments_count"
REEL_METRICS = ("views", "reach", "likes", "comments", "shares", "saved", "total_interactions",
                "ig_reels_avg_watch_time", "ig_reels_video_view_total_time")
ACCOUNT_DAY_METRICS = ("reach", "views", "accounts_engaged", "total_interactions", "likes", "comments", "shares",
                       "saves")


class InstagramError(RuntimeError):
    """Permanent problem (bad request, unsupported video): needs a human."""


class InstagramRetryable(InstagramError):
    """Temporary (network, 5xx, rate limit, media not ready)."""

    def __init__(self, message: str, wait_seconds: int = 120):
        super().__init__(message)
        self.wait_seconds = wait_seconds


class InstagramAuthError(InstagramError):
    """Token missing, expired or revoked: run `python -m socialauto instagram-connect` again."""


def classify(status: int, payload: dict[str, Any]) -> InstagramError:
    err = (payload or {}).get("error") or {}
    code, sub = err.get("code"), err.get("error_subcode")
    msg = f"HTTP {status} code {code}/{sub}: {err.get('message', '')}"[:400]
    if code in (190, 102) or (isinstance(code, int) and (code == 10 or 200 <= code <= 299)):
        return InstagramAuthError(msg)
    if code in (4, 17, 32, 613, 80002):
        return InstagramRetryable(msg, 900)
    if status >= 500 or code in (1, 2):
        return InstagramRetryable(msg, 120)
    return InstagramError(msg)


# --- token file ---------------------------------------------------------------------------------------------------

def load_tokens(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def save_tokens(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    tmp.touch(mode=0o600)
    tmp.write_text(json.dumps(data, indent=1))
    tmp.chmod(0o600)
    tmp.replace(path)


class GraphInstagramClient:
    dry_run = False

    def __init__(self, token_file: Path, version: str, app_id: str = "", app_secret: str = "",
                 session: requests.Session | None = None, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 sleep: Callable[[float], None] = time.sleep):
        self.token_file = token_file
        self.base = GRAPH.format(version=version)
        self.app_id = app_id
        self.app_secret = app_secret
        self.session = session or requests.Session()
        self.clock = clock
        self.sleep = sleep

    # --- plumbing -----------------------------------------------------------------------------------------
    def tokens(self) -> dict[str, Any]:
        data = load_tokens(self.token_file)
        if not data or not data.get("ig_user_id") or not (data.get("page_token") or data.get("user_token")):
            raise InstagramAuthError("Instagram is not connected yet: run `python -m socialauto instagram-connect`.")
        return data

    @property
    def connected(self) -> bool:
        try:
            self.tokens()
            return True
        except InstagramAuthError:
            return False

    @property
    def ig_user_id(self) -> str:
        return self.tokens()["ig_user_id"]

    def _request(self, path: str, params: dict[str, Any] | None = None, token: str | None = None) -> dict:
        """A GET request (this client never sends anything that changes the account)."""
        params = dict(params or {})
        if token is None:
            t = self.tokens()
            token = t.get("page_token") or t["user_token"]
        params["access_token"] = token
        url = path if path.startswith("http") else self.base + path.lstrip("/")
        try:
            resp = self.session.get(url, params=params, timeout=60)
        except requests.RequestException as exc:
            raise InstagramRetryable(f"network: {type(exc).__name__}") from exc
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        if resp.status_code >= 400 or (isinstance(payload, dict) and "error" in payload):
            raise classify(resp.status_code, payload if isinstance(payload, dict) else {})
        return payload

    def get(self, path: str, **params: Any) -> dict:
        return self._request(path, params)

    # --- tokens -------------------------------------------------------------------------------------------
    def refresh_if_needed(self) -> bool:
        """Exchange the long-lived user token for a fresh one when it has < 10 days left. True if refreshed."""
        data = self.tokens()
        expires = data.get("user_token_expires_at")
        if not expires or not data.get("user_token") or not (self.app_id and self.app_secret):
            return False
        if datetime.fromisoformat(expires) - self.clock() > REFRESH_BEFORE:
            return False
        fresh = self._request("oauth/access_token", {
            "grant_type": "fb_exchange_token", "client_id": self.app_id, "client_secret": self.app_secret,
            "fb_exchange_token": data["user_token"]}, token="")
        data["user_token"] = fresh["access_token"]
        data["user_token_expires_at"] = (self.clock() + timedelta(seconds=int(fresh.get("expires_in") or 5184000))
                                         ).isoformat(timespec="seconds")
        pages = self._request("me/accounts", {"fields": "id,name,access_token"}, token=data["user_token"])
        for page in pages.get("data", []):
            if page["id"] == data.get("page_id") and page.get("access_token"):
                data["page_token"] = page["access_token"]
        save_tokens(self.token_file, data)
        log.info("Instagram long-lived token refreshed")
        return True

    def recent_media(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.get(f"{self.ig_user_id}/media", fields=MEDIA_FIELDS, limit=limit).get("data", [])

    # --- analytics ----------------------------------------------------------------------------------------
    def account(self) -> dict[str, Any]:
        return self.get(self.ig_user_id, fields="username,name,followers_count,follows_count,media_count,"
                                                "profile_picture_url")

    def account_insights(self, since: datetime, until: datetime) -> dict[str, float]:
        """Totals per metric for [since, until) (metric_type=total_value, period=day)."""
        data = self.get(f"{self.ig_user_id}/insights", metric=",".join(ACCOUNT_DAY_METRICS), period="day",
                        metric_type="total_value", since=int(since.timestamp()), until=int(until.timestamp()))
        out = {}
        for item in data.get("data", []):
            value = (item.get("total_value") or {}).get("value")
            if value is not None:
                out[item["name"]] = float(value)
        return out

    def media_insights(self, media_id: str) -> dict[str, float]:
        try:
            data = self.get(f"{media_id}/insights", metric=",".join(REEL_METRICS))
        except InstagramError as exc:
            if isinstance(exc, (InstagramAuthError, InstagramRetryable)):
                raise
            data = self.get(f"{media_id}/insights", metric="reach,likes,comments,shares,saved")  # non-Reel media
        out = {}
        for item in data.get("data", []):
            values = item.get("values") or [{}]
            v = values[0].get("value") if values else None
            if v is None:
                v = (item.get("total_value") or {}).get("value")
            if isinstance(v, (int, float)):
                out[item["name"]] = float(v)
        return out


def connect(short_token: str, app_id: str, app_secret: str, version: str, token_file: Path,
            session: requests.Session | None = None, choose: Callable[[list[dict]], dict] | None = None) -> dict[str, Any]:
    """Exchange a short-lived user token (Graph API Explorer) for a long-lived one, find the Page with a linked
    Instagram Business/Creator account and save everything to the token file (chmod 600)."""
    s = session or requests.Session()
    base = GRAPH.format(version=version)

    def call(path: str, **params: Any) -> dict:
        resp = s.get(base + path, params=params, timeout=60)
        payload = resp.json() if resp.content else {}
        if resp.status_code >= 400 or "error" in payload:
            raise classify(resp.status_code, payload)
        return payload

    long = call("oauth/access_token", grant_type="fb_exchange_token", client_id=app_id, client_secret=app_secret,
                fb_exchange_token=short_token)
    user_token = long["access_token"]
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(long.get("expires_in") or 5184000))
    pages = call("me/accounts", fields="id,name,access_token,instagram_business_account{id,username}",
                 access_token=user_token).get("data", [])
    linked = [p for p in pages if p.get("instagram_business_account")]
    if not linked:
        raise InstagramError("none of your Facebook Pages has an Instagram Business/Creator account linked")
    page = choose(linked) if choose and len(linked) > 1 else linked[0]
    data = {"user_token": user_token, "user_token_expires_at": expires_at.isoformat(timespec="seconds"),
            "page_id": page["id"], "page_name": page.get("name", ""), "page_token": page.get("access_token", ""),
            "ig_user_id": page["instagram_business_account"]["id"],
            "username": page["instagram_business_account"].get("username", ""),
            "connected_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    save_tokens(token_file, data)
    return {"username": data["username"], "page_name": data["page_name"], "expires_at": data["user_token_expires_at"]}

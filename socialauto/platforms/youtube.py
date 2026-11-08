"""YouTube Data API v3 + YouTube Analytics API v2 — READ-ONLY (statistics for the dashboard).

Owner law 15: the bot never uploads, publishes or schedules anything. This client therefore has no upload, thumbnail
or update methods and asks Google only for read-only scopes. Quota: channels/videos/playlistItems lists cost 1 unit
each; Analytics reports use the separate Analytics quota.
"""

from __future__ import annotations

import json
import logging
import socket
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]


class YouTubeError(RuntimeError):
    """Permanent problem: needs a human."""


class YouTubeRetryable(YouTubeError):
    """Temporary problem (network, 5xx, 429)."""


class YouTubeQuotaError(YouTubeError):
    """Daily quota reached: wait until it resets (midnight Pacific)."""


class YouTubeAuthError(YouTubeError):
    """Token missing, expired or revoked: run `python -m socialauto youtube-auth` again."""


def watch_url(video_id: str) -> str:
    return f"https://youtube.com/shorts/{video_id}"


def classify_http_error(exc: Exception) -> YouTubeError:
    from googleapiclient.errors import HttpError

    if not isinstance(exc, HttpError):
        return YouTubeRetryable(f"{type(exc).__name__}: {exc}")
    status = exc.resp.status
    try:
        err = json.loads(exc.content.decode())["error"]
        reason = (err.get("errors") or [{}])[0].get("reason", "")
        message = err.get("message", "")
    except Exception:          # noqa: BLE001
        reason, message = "", str(exc)[:300]
    text = f"HTTP {status} {reason}: {message}".strip()
    if status == 401:
        return YouTubeAuthError(text)
    if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
        return YouTubeQuotaError(text)
    if status in (429, 500, 502, 503, 504):
        return YouTubeRetryable(text)
    return YouTubeError(text)


def save_token(path: Path, token_json: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    tmp.touch(mode=0o600)
    tmp.write_text(token_json)
    tmp.chmod(0o600)
    tmp.replace(path)


def authorize(client_secret: Path, token_file: Path) -> None:
    """Interactive browser consent for the read-only scopes (run once). Stores only the token file, chmod 600."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not client_secret.exists():
        raise YouTubeAuthError(f"OAuth client file not found: {client_secret}")
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True, prompt="consent",
                                  authorization_prompt_message="Open this URL in your browser: {url}")
    save_token(token_file, creds.to_json())


class YouTubeStats:
    """Read-only access to the owner's channel statistics."""

    def __init__(self, client_secret: Path, token_file: Path, expected_channel_id: str = ""):
        self.client_secret = client_secret
        self.token_file = token_file
        self.expected_channel_id = expected_channel_id
        self._service = None
        self._analytics = None
        self._uploads_playlist: str | None = None

    @property
    def connected(self) -> bool:
        return self.token_file.exists()

    def credentials(self):
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        if not self.token_file.exists():
            raise YouTubeAuthError("YouTube is not connected yet: run `python -m socialauto youtube-auth`.")
        creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
        if not creds.valid:
            if not creds.refresh_token:
                raise YouTubeAuthError("YouTube token has no refresh token: run `python -m socialauto youtube-auth`.")
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                raise YouTubeAuthError("YouTube token expired or was revoked: run "
                                       "`python -m socialauto youtube-auth`.") from exc
            except Exception as exc:   # noqa: BLE001
                raise YouTubeRetryable(f"token refresh failed: {type(exc).__name__}") from exc
            save_token(self.token_file, creds.to_json())
        return creds

    def service(self):
        if self._service is None:
            from googleapiclient.discovery import build
            self._service = build("youtube", "v3", credentials=self.credentials(), cache_discovery=False)
        return self._service

    def analytics_service(self):
        if self._analytics is None:
            from googleapiclient.discovery import build
            self._analytics = build("youtubeAnalytics", "v2", credentials=self.credentials(), cache_discovery=False)
        return self._analytics

    def _execute(self, request):
        try:
            return request.execute(num_retries=2)
        except (OSError, socket.timeout) as exc:
            raise YouTubeRetryable(f"network: {type(exc).__name__}") from exc
        except Exception as exc:   # noqa: BLE001
            raise classify_http_error(exc) from exc

    def channel(self) -> dict[str, Any]:
        resp = self._execute(self.service().channels().list(part="snippet,contentDetails,statistics", mine=True))
        items = resp.get("items") or []
        if not items:
            raise YouTubeError("the authorized Google account has no YouTube channel")
        return items[0]

    def recent_upload_ids(self, limit: int = 50) -> list[str]:
        if not self._uploads_playlist:
            self._uploads_playlist = self.channel()["contentDetails"]["relatedPlaylists"]["uploads"]
        items = self._execute(self.service().playlistItems().list(
            part="contentDetails", playlistId=self._uploads_playlist, maxResults=min(50, limit))).get("items", [])
        return [i["contentDetails"]["videoId"] for i in items]

    def videos(self, ids: list[str], parts: str = "snippet,statistics,contentDetails") -> list[dict[str, Any]]:
        out = []
        for i in range(0, len(ids), 50):
            out += self._execute(self.service().videos().list(part=parts, id=",".join(ids[i:i + 50]))).get("items", [])
        return out

    def report(self, **params: Any) -> dict[str, Any]:
        return self._execute(self.analytics_service().reports().query(ids="channel==MINE", **params))

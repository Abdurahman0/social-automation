"""Analytics logins on the website (Task 07): Instagram (Meta login with the user's own Meta app) and YouTube (Google
login with the user's own OAuth client, read-only scopes). The bot never posts: these logins only read statistics.

Both use a browser redirect back to this computer. The `state` value (random, single use, 15 minutes) is what
authorises the callback — the site's cookie is SameSite=Strict and is not sent on a redirect from facebook.com or
google.com. Tokens are written to secrets/ (chmod 600) and never shown; the site sees only the account name.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from ..platforms.instagram import PERMISSIONS
from ..platforms.youtube import SCOPES

log = logging.getLogger(__name__)
STATE_TTL = 900


class AccountError(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Accounts:
    def __init__(self, settings, session: requests.Session | None = None):
        self.settings = settings
        self.s = session or requests.Session()
        self._states: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    # --- state ----------------------------------------------------------------------------------------------------
    def _new_state(self, kind: str, **extra) -> str:
        st = secrets.token_urlsafe(24)
        with self._lock:
            now = time.time()
            self._states = {k: v for k, v in self._states.items() if v["at"] > now - STATE_TTL}
            self._states[st] = {"kind": kind, "at": now, **extra}
        return st

    def take_state(self, state: str, kind: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._states.pop(state or "", None)
        if not entry or entry["kind"] != kind or entry["at"] < time.time() - STATE_TTL:
            return None
        return entry

    def owns_state(self, state: str, kind: str) -> bool:
        with self._lock:
            e = self._states.get(state or "")
        return bool(e and e["kind"] == kind)

    # --- paths ------------------------------------------------------------------------------------------------------
    @property
    def base_url(self) -> str:
        return self.settings.web.public_url.rstrip("/")

    def ig_file(self) -> Path:
        return self.settings.resolve(self.settings.instagram.token_file)

    def yt_secret(self) -> Path:
        return self.settings.resolve(self.settings.youtube.client_secret_file)

    def yt_token(self) -> Path:
        return self.settings.resolve(self.settings.youtube.token_file)

    def ig_redirect(self) -> str:
        return self.base_url + "/api/accounts/instagram/callback"

    def yt_redirect(self) -> str:
        return self.base_url + "/"           # Google "Desktop app" clients accept any loopback address

    # --- Instagram ----------------------------------------------------------------------------------------------
    def meta_keys(self) -> tuple[str, str]:
        from .. import env_store
        env = env_store.read(self.settings.root / ".env")
        return (env.get("META_APP_ID") or self.settings.meta_app_id, env.get("META_APP_SECRET") or self.settings.meta_app_secret)

    def instagram_start(self) -> str:
        app_id, secret = self.meta_keys()
        if not (app_id and secret):
            raise AccountError("meta_keys")
        st = self._new_state("instagram")
        q = urlencode({"client_id": app_id, "redirect_uri": self.ig_redirect(), "state": st,
                       "scope": ",".join(PERMISSIONS), "response_type": "code"})
        return f"https://www.facebook.com/{self.settings.instagram.graph_version}/dialog/oauth?{q}"

    def instagram_callback(self, code: str, state: str) -> dict:
        if not self.take_state(state, "instagram"):
            raise AccountError("expired")
        app_id, secret = self.meta_keys()
        try:
            r = self.s.get(f"https://graph.facebook.com/{self.settings.instagram.graph_version}/oauth/access_token",
                           params={"client_id": app_id, "client_secret": secret, "redirect_uri": self.ig_redirect(),
                                   "code": code}, timeout=30)
            body = r.json()
        except (requests.RequestException, ValueError):
            raise AccountError("network") from None
        if "access_token" not in body:
            raise AccountError("rejected")
        return self.instagram_token(body["access_token"])

    def instagram_token(self, short_token: str) -> dict:
        from ..platforms.instagram import InstagramAuthError, InstagramError, connect
        app_id, secret = self.meta_keys()
        if not (app_id and secret):
            raise AccountError("meta_keys")
        try:
            info = connect(short_token.strip(), app_id, secret, self.settings.instagram.graph_version, self.ig_file(),
                           session=self.s)
        except InstagramAuthError:
            raise AccountError("rejected") from None
        except InstagramError as exc:
            raise AccountError("no_ig_account" if "linked" in str(exc) else "rejected") from None
        except requests.RequestException:
            raise AccountError("network") from None
        return {"username": info["username"], "page_name": info["page_name"]}

    def instagram_view(self) -> dict:
        from ..platforms.instagram import load_tokens
        data = load_tokens(self.ig_file()) if self.ig_file().exists() else None
        app_id, secret = self.meta_keys()
        return {"connected": bool(data), "username": (data or {}).get("username", ""),
                "page_name": (data or {}).get("page_name", ""), "keys": bool(app_id and secret),
                "redirect_uri": self.ig_redirect()}

    def instagram_disconnect(self) -> None:
        self.ig_file().unlink(missing_ok=True)

    # --- YouTube ------------------------------------------------------------------------------------------------
    def youtube_client(self, text: str) -> dict:
        """Save the Google OAuth client JSON (the user downloads it from Google Cloud)."""
        try:
            data = json.loads(text)
        except ValueError:
            raise AccountError("bad_client") from None
        kind = "installed" if "installed" in data else ("web" if "web" in data else "")
        if not kind or not data[kind].get("client_id") or not data[kind].get("client_secret"):
            raise AccountError("bad_client")
        from ..platforms.youtube import save_token
        save_token(self.yt_secret(), json.dumps(data))
        return {"ok": True, "kind": "desktop" if kind == "installed" else "web"}

    def youtube_start(self) -> str:
        if not self.yt_secret().exists():
            raise AccountError("no_client")
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_secrets_file(str(self.yt_secret()), scopes=SCOPES, redirect_uri=self.yt_redirect())
        url, state = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
        with self._lock:
            self._states[state] = {"kind": "youtube", "at": time.time(), "flow": flow}
        return url

    def youtube_callback(self, code: str, state: str) -> dict:
        entry = self.take_state(state, "youtube")
        if not entry:
            raise AccountError("expired")
        flow = entry["flow"]
        try:
            flow.fetch_token(code=code)
        except Exception:                                  # noqa: BLE001 - never echo the response (it has tokens)
            raise AccountError("rejected") from None
        granted = set(getattr(flow.credentials, "granted_scopes", None) or SCOPES)
        if not granted.issuperset(SCOPES) or any(not s.endswith(".readonly") for s in granted if "youtube" in s
                                                 or "yt-analytics" in s):
            raise AccountError("scopes")
        from ..platforms.youtube import YouTubeStats, save_token
        save_token(self.yt_token(), flow.credentials.to_json())
        try:
            channel = YouTubeStats(self.yt_secret(), self.yt_token()).channel()
        except Exception:                                  # noqa: BLE001
            return {"title": ""}
        from ..config import set_local_value
        set_local_value(self.settings.root, "youtube", "expected_channel_id", channel["id"])
        (self.yt_token().parent / "youtube_channel.json").write_text(
            json.dumps({"title": channel["snippet"]["title"]}), encoding="utf-8")
        return {"title": channel["snippet"]["title"]}

    def youtube_view(self) -> dict:
        title = ""
        f = self.yt_token().parent / "youtube_channel.json"
        if f.exists():
            try:
                title = json.loads(f.read_text(encoding="utf-8")).get("title", "")
            except ValueError:
                title = ""
        return {"connected": self.yt_token().exists(), "client": self.yt_secret().exists(), "title": title,
                "redirect_uri": self.yt_redirect()}

    def youtube_disconnect(self) -> None:
        self.yt_token().unlink(missing_ok=True)
        (self.yt_token().parent / "youtube_channel.json").unlink(missing_ok=True)


__all__ = ["Accounts", "AccountError"]

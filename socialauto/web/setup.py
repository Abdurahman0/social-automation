"""The checks behind the Setup page's "Tekshirish" buttons. Each value is sent only to the service it belongs to
(the Telegram token to api.telegram.org, the Buffer key to api.buffer.com); nothing is logged."""

from __future__ import annotations

import re
import shutil

import requests

from ..config import Settings

TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")
IDS_RE = re.compile(r"^\s*-?\d{3,15}(\s*,\s*-?\d{3,15})*\s*$")


class SetupChecks:
    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.s = session or requests.Session()

    @staticmethod
    def validate(key: str, value: str) -> str | None:
        """A reason code when a value cannot be right (empty clears a value and is always allowed)."""
        if not value:
            return None
        if key == "TELEGRAM_BOT_TOKEN" and not TOKEN_RE.match(value):
            return "bad_token"
        if key == "TELEGRAM_ALLOWED_USER_IDS" and not IDS_RE.match(value):
            return "bad_ids"
        if key == "META_APP_ID" and not value.isdigit():
            return "bad_app_id"
        if len(value) > 500:
            return "too_long"
        return None

    def telegram(self, token: str) -> dict:
        if not token:
            return {"ok": False, "reason": "missing"}
        if not TOKEN_RE.match(token):
            return {"ok": False, "reason": "bad_token"}
        try:
            r = self.s.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15)
            body = r.json()
        except Exception:                 # noqa: BLE001 - never echo the URL (it contains the token)
            return {"ok": False, "reason": "network"}
        if not body.get("ok"):
            return {"ok": False, "reason": "rejected"}
        me = body.get("result") or {}
        return {"ok": True, "name": me.get("first_name", ""), "username": me.get("username", "")}

    def buffer(self, key: str) -> dict:
        if not key:
            return {"ok": False, "reason": "missing"}
        from ..reel.buffer import BufferAuthError, BufferError, GraphBuffer
        try:
            channels = GraphBuffer(key, session=self.s).channels()
        except BufferAuthError:
            return {"ok": False, "reason": "rejected"}
        except BufferError as exc:        # only a failed connection is "network"; anything Buffer answered is a refusal
            return {"ok": False, "reason": "network" if str(exc).startswith(("network", "HTTP 5")) else "rejected"}
        except Exception:                 # noqa: BLE001
            return {"ok": False, "reason": "network"}
        names = {"instagram": "Instagram", "youtube": "YouTube", "linkedin": "LinkedIn"}
        return {"ok": True, "channels": [{"service": names.get(c.get("service"), (c.get("service") or "").title()),
                                          "name": c.get("displayName") or c.get("name") or ""} for c in channels]}

    def claude(self) -> dict:
        """Is the Claude Code CLI installed and logged in on THIS computer (the user's own account)?"""
        binary = shutil.which(self.settings.claude.binary)
        if not binary:
            return {"installed": False, "logged_in": False, "plan": ""}
        from ..claude_client import ClaudeClient
        st = ClaudeClient(self.settings.claude, self.settings.claude_workdir).auth_status()
        return {"installed": True, "logged_in": bool(st.get("loggedIn")),
                "plan": str(st.get("subscriptionType") or "").title()}

    def model(self) -> dict:
        path = self.settings.resolve(self.settings.reel.stt_model) / "model.bin"
        size = path.stat().st_size if path.exists() else 0
        return {"ready": size > 500_000_000, "size_mb": round(size / 1e6)}

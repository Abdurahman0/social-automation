"""How the bot service lives on any computer (Linux, macOS, Windows).

* No token yet (first start, before the Setup page is filled in): wait quietly and check `.env` every few seconds,
  instead of exiting and being restarted over and over.
* `.env` changed while running (the Setup / Settings page saved something): stop cleanly and exit with
  RESTART_CODE; the service manager (systemd Restart=always, launchd KeepAlive, the Windows wrapper loop) starts
  the bot again with the new values.
* Claude Code missing or logged out: the owner gets ONE Telegram alert (an alert he must act on, law 5); it is
  sent again only after Claude has worked in between.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Callable

log = logging.getLogger("socialauto.runner")
RESTART_CODE = 75
CLAUDE_ALERT_KEY = "claude_alert_sent"
CLAUDE_ALERT = ("⚠️ Claude Code {what}.\n\nBot ssenariy yoza olmaydi. Shu kompyuterda terminalni oching, "
                "«claude» deb yozing va o'z akkauntingiz bilan kiring. Keyin saytdagi «Sozlamalar» → "
                "«Qayta tekshirish» tugmasini bosing — bot o'zi davom etadi.")


def env_fingerprint(path: Path) -> str:
    """Changes whenever the file's content changes (mtime alone is too coarse on some file systems)."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def ready(settings) -> bool:
    return bool(settings.telegram_token and settings.allowed_user_ids)


def wait_for_token(load: Callable[[], object], stop: threading.Event | None = None, every: float = 5.0):
    """Return settings once the token and allowed ids are filled in (None if `stop` is set first)."""
    told = False
    while True:
        settings = load()
        if ready(settings):
            return settings
        if not told:
            log.info("Waiting for the Telegram token: fill it in on the website's Setup (Sozlash) page")
            told = True
        if stop is not None and stop.wait(every):
            return None
        if stop is None:
            time.sleep(every)


class EnvWatcher:
    """Calls `on_change` once when `.env` content changes."""

    def __init__(self, path: Path, on_change: Callable[[], None], every: float = 3.0):
        self.path, self.on_change, self.every = path, on_change, every
        self.start_print = env_fingerprint(path)
        self.stop = threading.Event()
        self.changed = False
        self.thread = threading.Thread(target=self._loop, name="env-watcher", daemon=True)

    def start(self) -> "EnvWatcher":
        self.thread.start()
        return self

    def check(self) -> bool:
        if not self.changed and env_fingerprint(self.path) != self.start_print:
            self.changed = True
            log.info(".env changed: restarting the bot with the new settings")
            self.on_change()
        return self.changed

    def _loop(self) -> None:
        while not self.stop.wait(self.every):
            if self.check():
                return


def claude_alert(app) -> bool:
    """Queue one owner alert if Claude Code is missing or logged out. True if an alert was queued."""
    from .claude_client import ClaudeClient
    s = app.settings
    if not shutil.which(s.claude.binary):
        what = "bu kompyuterda o'rnatilmagan"
    else:
        status = ClaudeClient(s.claude, s.claude_workdir).auth_status()
        if status.get("loggedIn"):
            app.kv.set(CLAUDE_ALERT_KEY, False)
            return False
        what = "akkauntiga kirilmagan"
    if app.kv.get(CLAUDE_ALERT_KEY):
        return False
    app.kv.set(CLAUDE_ALERT_KEY, True)
    app.outbox.add("owner_action", text=CLAUDE_ALERT.format(what=what))
    return True

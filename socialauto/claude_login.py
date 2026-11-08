"""Log in to the user's OWN Claude account from the website (Task 07). No API key, ever.

`claude auth login --claudeai` prints a sign-in link and waits for the code that claude.com shows after the user
signs in. We run it for THIS computer (the configured Claude config dir), show the link in the page, pass the pasted
code to it, then read `claude auth status`. The link is shown only to the logged-in website user and never logged.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time

log = logging.getLogger(__name__)

URL_OSC = re.compile(rb"\x1b\]8;;(https://[^\x07\x1b]+)")
URL_PLAIN = re.compile(rb"(https://claude\.(?:com|ai)/[^\s\x07\x1b]+)")
ANSI = re.compile(rb"\x1b\][^\x07]*\x07|\x1b\[[0-9;?]*[A-Za-z]")
TIMEOUT = 600


def install_hint() -> str:
    if sys.platform.startswith("win"):
        return "PowerShell'da: npm install -g @anthropic-ai/claude-code (yoki claude.ai/download)"
    if sys.platform == "darwin":
        return "Terminalda: npm install -g @anthropic-ai/claude-code (yoki: brew install --cask claude-code)"
    return "Terminalda: npm install -g @anthropic-ai/claude-code"


class ClaudeLogin:
    """One login at a time. States: idle → starting → waiting_code → checking → done | failed."""

    def __init__(self, settings, spawn=None):
        self.settings = settings
        self._spawn = spawn or self._spawn_cli
        self._lock = threading.Lock()
        self.state = "idle"
        self.url = ""
        self.reason = ""
        self._proc = None
        self._write = None
        self._started = 0.0
        self._buf = b""

    # --- process --------------------------------------------------------------------------------------------------
    def _env(self) -> dict[str, str]:
        from .claude_client import child_env
        env = dict(os.environ)
        env.update(child_env(self.settings.claude.config_dir))
        for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            env.pop(k, None)
        env["BROWSER"] = "true" if not sys.platform.startswith("win") else env.get("BROWSER", "")   # we show the link
        return env

    def _spawn_cli(self):
        """(read() -> bytes|None, write(bytes), wait() -> int|None, kill()) for `claude auth login`."""
        exe = shutil.which(self.settings.claude.binary)
        if not exe:
            raise FileNotFoundError("claude")
        args = [exe, "auth", "login", "--claudeai"]
        if not sys.platform.startswith("win"):
            import pty
            import select
            pid, fd = pty.fork()
            if pid == 0:                                   # child
                try:
                    os.execve(exe, args, self._env())
                finally:
                    os._exit(127)

            def read():
                r, _, _ = select.select([fd], [], [], 0.5)
                if not r:
                    return b""
                try:
                    return os.read(fd, 4096) or None
                except OSError:
                    return None

            def wait():
                try:
                    done, status = os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    return 0
                return None if done == 0 else os.waitstatus_to_exitcode(status)

            def kill():
                try:
                    os.kill(pid, 9)
                    os.waitpid(pid, 0)
                except (OSError, ChildProcessError):
                    pass
                try:
                    os.close(fd)
                except OSError:
                    pass
            return read, (lambda b: os.write(fd, b)), wait, kill
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env=self._env())

        def read_win():
            data = proc.stdout.read1(4096) if proc.stdout else b""
            return data or (None if proc.poll() is not None else b"")

        def write_win(b):
            proc.stdin.write(b)
            proc.stdin.flush()
        return read_win, write_win, proc.poll, proc.kill

    # --- public -------------------------------------------------------------------------------------------------
    def start(self) -> dict:
        with self._lock:
            self.stop()
            self.state, self.url, self.reason, self._buf = "starting", "", "", b""
            try:
                read, write, wait, kill = self._spawn()
            except FileNotFoundError:
                self.state, self.reason = "failed", "not_installed"
                return self.view()
            self._proc, self._write, self._started = (read, wait, kill), write, time.time()
            threading.Thread(target=self._reader, name="claude-login", daemon=True).start()
        for _ in range(60):                               # the link usually appears within a second or two
            if self.state != "starting":
                break
            time.sleep(0.25)
        return self.view()

    def _reader(self) -> None:
        read, wait, kill = self._proc
        while True:
            if time.time() - self._started > TIMEOUT:
                kill()
                self.state, self.reason = "failed", "timeout"
                return
            data = read()
            if data is None:
                break
            if data:
                self._buf += data
                if not self.url:
                    m = URL_OSC.search(self._buf) or URL_PLAIN.search(self._buf)
                    if m:
                        self.url = m.group(1).decode(errors="replace")
                        self.state = "waiting_code"
            code = wait()
            if code is not None:
                break
        rest = wait()
        self._finish(0 if rest in (0, None) else rest)

    def _finish(self, code: int) -> None:
        status = self.status()
        if status["logged_in"]:
            self.state, self.reason = "done", ""
        else:
            self.state = "failed"
            text = ANSI.sub(b"", self._buf).decode(errors="replace").lower()
            self.reason = "bad_code" if ("invalid" in text or "error" in text or code) else "not_finished"
        self._proc = None

    def submit_code(self, code: str) -> dict:
        code = code.strip()
        if not code or len(code) > 2000 or "\n" in code:
            return {**self.view(), "reason": "bad_code"}
        if self.state != "waiting_code" or not self._write:
            return {**self.view(), "reason": "not_started"}
        self.state = "checking"
        self._write(code.encode() + b"\r")
        for _ in range(120):
            if self.state in ("done", "failed"):
                break
            time.sleep(0.25)
        return self.view()

    def stop(self) -> None:
        if self._proc:
            try:
                self._proc[2]()
            except Exception:                              # noqa: BLE001
                pass
            self._proc = None

    def status(self) -> dict:
        if not shutil.which(self.settings.claude.binary):
            return {"installed": False, "logged_in": False, "plan": "", "email": "", "hint": install_hint()}
        from .claude_client import ClaudeClient
        st = ClaudeClient(self.settings.claude, self.settings.claude_workdir).auth_status()
        return {"installed": True, "logged_in": bool(st.get("loggedIn")),
                "plan": str(st.get("subscriptionType") or "").title(), "email": str(st.get("email") or ""),
                "hint": install_hint()}

    def view(self) -> dict:
        return {"state": self.state, "url": self.url if self.state == "waiting_code" else "", "reason": self.reason}


__all__ = ["ClaudeLogin", "install_hint"]

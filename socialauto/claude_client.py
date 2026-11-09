"""Claude Code CLI invocation (copied from ytauto, trimmed to one account).

Claude runs through the Claude Code subscription login of account 1 (the default `~/.claude`), never an API key
(law 8). Every call:
- sets CLAUDE_CONFIG_DIR from config (never inherited) and drops ANTHROPIC_* variables, so the subscription is
  used, not API billing;
- runs with `--safe-mode` (the owner's plugins, hooks and memory in ~/.claude do not load) and `--effort`;
- runs in an empty sandbox directory with every built-in tool disabled except, when asked, WebSearch/WebFetch
  (fact checking for the "surprising facts" niche). The child gets only an allowlist of environment variables,
  so this project's secrets (bot token, OAuth files) are unreachable from a Claude call;
- is recorded in the usage ledger (claude_budget); a usage-limit message pauses Claude work until the reset time
  the CLI printed.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import ClaudeConfig

log = logging.getLogger(__name__)

_ENV_ALLOWLIST = {"PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LANGUAGE", "TERM", "TZ", "TMPDIR",
                  "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
                  "SSL_CERT_FILE", "SSL_CERT_DIR",
                  # Windows: without these the CLI cannot find the user profile, temp dir or even start networking
                  # (os.environ keys are upper-case on Windows)
                  "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "USERPROFILE", "USERNAME",
                  "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES",
                  "PROGRAMFILES(X86)", "TEMP", "TMP", "OS", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS"}
_ENV_ALLOWED_PREFIXES = ("LC_", "XDG_")
_DENIED_TOOLS = ["Bash", "Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Agent", "Task",
                 "Read", "Glob", "Grep"]
WEB_TOOLS = ("WebSearch", "WebFetch")

_LIMIT_RE = re.compile(r"(usage limit|rate limit|hit your .*limit|limit reached|limit · resets|out of (extra )?usage)",
                       re.I)
_AUTH_RE = re.compile(r"(not logged in|please run /login|invalid api key|authentication|oauth token|401)", re.I)


class ClaudeError(RuntimeError):
    pass


class ClaudeUsageLimit(ClaudeError):
    def __init__(self, message: str, resume_at: datetime | None):
        super().__init__(message)
        self.resume_at = resume_at


class ClaudeAuthError(ClaudeError):
    pass


def child_env(config_dir: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in _ENV_ALLOWLIST or k.startswith(_ENV_ALLOWED_PREFIXES)}
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    return env


def extract_json(text: str) -> Any:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        return json.loads(fence.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("no JSON object in Claude output")


def classify_failure(text: str, now: datetime | None = None) -> ClaudeError:
    short = text.strip()[:500]
    if _LIMIT_RE.search(text):
        from .claude_budget import reset_time
        return ClaudeUsageLimit(short, reset_time(text, now or datetime.now(timezone.utc)))
    if _AUTH_RE.search(text):
        return ClaudeAuthError(short)
    return ClaudeError(short or "Claude Code failed without output")


class ClaudeClient:
    def __init__(self, cfg: ClaudeConfig, workdir: Path, budget=None):
        self.cfg = cfg
        self.workdir = workdir
        self.budget = budget
        self._lock = threading.Lock()
        self._last_call = 0.0

    def exe(self) -> str:
        """The CLI's full path (on Windows `claude` is a claude.cmd / claude.exe that subprocess cannot find alone)."""
        return shutil.which(self.cfg.binary) or self.cfg.binary

    def _base_command(self) -> list[str]:
        cmd = [self.exe(), "--safe-mode"]
        if self.cfg.effort:
            cmd += ["--effort", self.cfg.effort]
        if self.cfg.model:
            cmd += ["--model", self.cfg.model]
        return cmd

    def auth_status(self) -> dict[str, Any]:
        """`claude auth status --json` (contains no credentials)."""
        try:
            result = subprocess.run([self.exe(), "auth", "status", "--json"], env=child_env(self.cfg.config_dir),
                                    capture_output=True, text=True, timeout=60, check=False)
        except OSError as exc:
            return {"loggedIn": False, "error": str(exc)}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"loggedIn": False, "error": (result.stderr or result.stdout).strip()[:300]}

    def generate_json(self, task: str, prompt: str, schema: dict[str, Any], system_prompt: str,
                      tools: tuple[str, ...] = (), timeout: int | None = None) -> dict[str, Any]:
        """Run one non-interactive Claude Code call and return the JSON object it produced."""
        bad = [t for t in tools if t not in WEB_TOOLS]
        if bad:
            raise ValueError(f"{task}: only {', '.join(WEB_TOOLS)} can be enabled, not {', '.join(bad)}")
        self.workdir.mkdir(parents=True, exist_ok=True)
        cmd = self._base_command() + [
            "--print",
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            "--system-prompt", system_prompt,
            "--permission-mode", "dontAsk",
            "--tools", ",".join(tools),
            *(["--allowedTools", ",".join(tools)] if tools else []),
            "--disallowedTools", *[t for t in _DENIED_TOOLS if t not in tools],
            "--strict-mcp-config",
            "--no-session-persistence",
        ]
        timeout = timeout or self.cfg.timeout_seconds
        if self.budget is not None:
            self.budget.check()                         # raises ClaudeBudgetWait while a limit pause is on
        with self._lock:
            wait = self.cfg.min_interval_seconds - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            started = time.monotonic()
            try:
                result = subprocess.run(cmd, input=prompt, cwd=self.workdir, env=child_env(self.cfg.config_dir),
                                        capture_output=True, text=True, timeout=timeout, check=False)
            except subprocess.TimeoutExpired as exc:
                raise ClaudeError(f"{task}: timed out after {timeout}s") from exc
            except OSError as exc:
                raise ClaudeError(f"{task}: could not start Claude Code: {exc}") from exc
            finally:
                self._last_call = time.monotonic()
        seconds = time.monotonic() - started
        log.info("Claude call %s finished in %.0fs (exit %s)", task, seconds, result.returncode)
        try:
            data = self._parse(task, result.stdout or "", result.stderr or "", result.returncode, schema)
        except ClaudeUsageLimit as exc:
            self._ledger(task, seconds, result, limit=str(exc))
            raise
        except ClaudeError:
            self._ledger(task, seconds, result)
            raise
        self._ledger(task, seconds, result)
        return data

    def _ledger(self, task: str, seconds: float, result, limit: str = "") -> None:
        if self.budget is None:
            return
        try:
            from .claude_budget import envelope_usage
            try:
                envelope = json.loads(result.stdout or "")
            except json.JSONDecodeError:
                envelope = {}
            usage = envelope_usage(envelope if isinstance(envelope, dict) else {})
            self.budget.record(task, seconds, usage, result.returncode, bool(limit))
            if limit:
                self.budget.limit_hit(limit, self.cfg.limit_backoff_minutes)
            elif result.returncode == 0:
                self.budget.note_success()
        except Exception as exc:   # noqa: BLE001 - the ledger never breaks a call
            log.warning("Claude ledger not written: %s", exc)

    @staticmethod
    def _parse(task: str, stdout: str, stderr: str, returncode: int, schema: dict[str, Any]) -> dict[str, Any]:
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            envelope = None
        if not isinstance(envelope, dict):
            raise classify_failure(stdout + "\n" + stderr)
        text = str(envelope.get("result") or "")
        if envelope.get("is_error") or returncode != 0:
            raise classify_failure(text + "\n" + stderr)
        data = envelope.get("structured_output")
        if not isinstance(data, dict):
            try:
                data = extract_json(text)
            except (ValueError, json.JSONDecodeError) as exc:
                raise ClaudeError(f"{task}: output was not valid JSON") from exc
        missing = [k for k in schema.get("required", []) if k not in data]
        if missing:
            raise ClaudeError(f"{task}: JSON is missing required fields: {', '.join(missing)}")
        return data


def backoff_until(cfg: ClaudeConfig, err: ClaudeUsageLimit, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if err.resume_at and err.resume_at > now:
        return err.resume_at + timedelta(minutes=2)
    return now + timedelta(minutes=cfg.limit_backoff_minutes)

"""Updates from the owner's code repo (Task 07): read-only for everyone.

`git fetch` + `git merge --ff-only` and nothing else: never a push, never a reset, never a stash. The user's own
files (.env, secrets/, data/ with the content repo, config.local.toml, logs/, models/) are git-ignored, so a
fast-forward cannot touch them; if tracked files were changed by hand the update is refused with a plain reason.
After an update the Python / Remotion packages are refreshed when their lists changed, and both services restart
(the bot through data/restart_request, the website by exiting with RESTART_CODE).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

SAFE = {"fetch", "rev-parse", "rev-list", "log", "status", "merge-base", "merge", "diff", "remote", "symbolic-ref"}
RESTART_FILE = "data/restart_request"


class Updater:
    def __init__(self, root: Path, branch: str = "main", min_fetch_seconds: int = 600):
        self.root = root
        self.branch = branch
        self.min_fetch = min_fetch_seconds
        self._last_fetch = 0.0
        self._lock = threading.Lock()

    def git(self, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
        if args[0] not in SAFE:
            raise ValueError(f"git {args[0]} is not allowed in the updater")
        if args[0] == "merge" and "--ff-only" not in args:
            raise ValueError("only fast-forward merges")
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        # Anonymous: no credential helper, no prompt (the code repo is public; updates never need a login).
        return subprocess.run(["git", "-c", "credential.helper=", "-C", str(self.root), *args], capture_output=True, text=True, timeout=timeout,
                              env=env, check=False)

    def fetch(self, force: bool = False) -> bool:
        with self._lock:
            if not force and time.time() - self._last_fetch < self.min_fetch:
                return True
            res = self.git("fetch", "--quiet", "origin", self.branch)
            if res.returncode == 0:
                self._last_fetch = time.time()
            else:
                log.info("update check: fetch failed (%s)", res.stderr.strip()[:200])
            return res.returncode == 0

    def status(self, fetch: bool = True, force: bool = False) -> dict:
        if not (self.root / ".git").exists() or not self.git("remote").stdout.strip():
            return {"available": False, "reason": "no_repo", "commits": []}
        reachable = self.fetch(force) if fetch else True
        upstream = f"origin/{self.branch}"
        head = self.git("rev-parse", "HEAD").stdout.strip()
        theirs = self.git("rev-parse", upstream).stdout.strip()
        if not theirs:
            return {"available": False, "reason": "offline" if not reachable else "no_upstream", "commits": []}
        behind = int(self.git("rev-list", "--count", f"HEAD..{upstream}").stdout.strip() or 0)
        ahead = int(self.git("rev-list", "--count", f"{upstream}..HEAD").stdout.strip() or 0)
        commits = []
        if behind:
            out = self.git("log", "--format=%ct%x09%s", "-n", "10", f"HEAD..{upstream}").stdout
            for line in out.splitlines():
                ts, _, subject = line.partition("\t")
                commits.append({"title": subject.split("\n")[0][:140], "at": int(ts or 0)})
        reason = ""
        if behind and ahead:
            reason = "diverged"                      # local commits: a fast-forward is impossible, nothing is changed
        elif behind and self.dirty():
            reason = "local_changes"
        return {"available": bool(behind), "behind": behind, "can_update": bool(behind) and not reason,
                "reason": reason or ("offline" if not reachable else ""), "commits": commits,
                "current": head[:7] if head else "", "checked_at": int(self._last_fetch)}

    def dirty(self) -> bool:
        return bool(self.git("status", "--porcelain", "--untracked-files=no").stdout.strip())

    def apply(self) -> dict:
        st = self.status(fetch=True, force=True)
        if not st["available"]:
            return {"ok": False, "reason": st.get("reason") or "up_to_date"}
        if not st["can_update"]:
            return {"ok": False, "reason": st["reason"]}
        before = self.git("rev-parse", "HEAD").stdout.strip()
        res = self.git("merge", "--ff-only", "--quiet", f"origin/{self.branch}")
        if res.returncode != 0:
            log.warning("update failed: %s", res.stderr.strip()[:300])
            return {"ok": False, "reason": "merge_failed"}
        changed = self.git("diff", "--name-only", before, "HEAD").stdout.split()
        self.refresh_packages(changed)
        self.request_restart()
        return {"ok": True, "updated": len(changed), "commits": st["commits"]}

    def refresh_packages(self, changed: list[str]) -> None:
        py = self.root / ".venv" / ("Scripts/python.exe" if sys.platform.startswith("win") else "bin/python")
        if "requirements.txt" in changed and py.exists():
            subprocess.run([str(py), "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r",
                            str(self.root / "requirements.txt")], capture_output=True, timeout=1800, check=False)
        if any(c.startswith("remotion/package") for c in changed):
            npm = "npm.cmd" if sys.platform.startswith("win") else "npm"
            subprocess.run([npm, "install", "--no-audit", "--no-fund", "--loglevel=error"], cwd=self.root / "remotion",
                           capture_output=True, timeout=1800, check=False)

    def request_restart(self) -> None:
        """The bot watches this file (runner.EnvWatcher) and restarts; the website restarts itself after replying."""
        f = self.root / RESTART_FILE
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(str(time.time()), encoding="utf-8")


__all__ = ["Updater", "RESTART_FILE"]

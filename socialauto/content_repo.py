"""The user's OWN content repo (Task 07).

Two repos, never mixed:
- the CODE repo (this folder, `origin` = the owner's `Abdurahman0/social-automation`) is only read: updates are
  fetched and fast-forwarded (socialauto/updater.py). The app never commits or pushes content to it.
- the CONTENT repo (`data/content-repo/`, git-ignored by the code repo) holds reels/<date>-<topic>/ (video, the
  owner's cover, script, research, sources) and is pushed to the user's own GitHub account
  (`<login>/social-automation-content`, private, created by the app) or to a remote the user set himself.

Hard guard (every computer, the owner's too): a content push to any URL of the upstream code repo — its configured
name, or any remote of this code folder — or into the code folder itself is refused. Never a force push.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

LFS_BYTES = 50 * 1024 * 1024
NOTE_LOCAL = "GitHub ulanmagan: reel shu kompyuterda saqlandi (Sozlamalar → GitHub)"
NOTE_PUSHED = "Sizning GitHub'ingizga yuklandi"
NOTE_FAILED = "GitHub'ga yuklab bo'lmadi (internet yoki ruxsat yo'q): shu kompyuterda saqlandi, keyinroq yana urinadi"


class ContentPushRefused(RuntimeError):
    """A content push aimed at the upstream code repo (or the code folder). Never allowed."""


def canonical(url: str) -> str:
    """One comparable form for a remote: "github.com/owner/name" for GitHub URLs (https, ssh, git@, with or without
    credentials or .git), the resolved absolute path for local repos."""
    u = (url or "").strip()
    m = re.match(r"^(?:[a-z+]+://)?(?:[^@/]+@)?(github\.com)[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/*$", u, re.I)
    if m:
        return f"github.com/{m.group(2)}/{m.group(3)}".lower()
    if re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", u) and not Path(u).exists():   # "owner/name"
        return f"github.com/{u}".lower().removesuffix(".git")
    p = u[7:] if u.startswith("file://") else u
    try:
        return str(Path(os.path.expanduser(p)).resolve()).rstrip("/").lower()
    except OSError:
        return u.lower()


def git(repo: Path, *args: str, check: bool = True, env: dict | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    e = dict(os.environ)
    e["GIT_TERMINAL_PROMPT"] = "0"
    e.update(env or {})
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check,
                          timeout=timeout, env=e)


def code_repo_urls(code_root: Path, code_repo: str) -> set[str]:
    """Every way to name the upstream code repo: the configured "owner/name" and all remotes of the code folder."""
    out = {canonical(code_repo)} if code_repo else set()
    if (code_root / ".git").exists():
        res = git(code_root, "remote", "-v", check=False)
        for line in res.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                out.add(canonical(parts[1]))
    out.add(canonical(str(code_root)))
    return out


@dataclass
class GitResult:
    folder: str
    committed: bool
    pushed: bool
    lfs_files: list[str]
    note: str


class ContentRepo:
    def __init__(self, settings, account=None):
        self.settings = settings
        self.account = account                      # socialauto.github_account.GitHubAccount (or None)
        self.path = settings.resolve(settings.github.content_dir)

    # --- where things go ------------------------------------------------------------------------------------
    @property
    def reels(self) -> Path:
        return self.path / "reels"

    def remote_url(self) -> str:
        """The user's own content remote: a fixed one from config.local.toml, else his connected GitHub account."""
        if self.settings.github.content_remote:
            return self.settings.github.content_remote
        info = self.account.info() if self.account else None
        if info and info.get("login"):
            return f"https://github.com/{info['login']}/{self.settings.github.content_repo}.git"
        return ""

    def guard(self, url: str) -> None:
        """Refuse a content push to the upstream code repo (or into the code folder). Raised, logged, never skipped."""
        target = canonical(url)
        code = code_repo_urls(self.settings.root, self.settings.github.code_repo)
        root = canonical(str(self.settings.root))
        if target in code or target == root:
            log.error("Refused: content push to the code repo (%s)", target)
            raise ContentPushRefused("content never goes to the code repo")
        if canonical(str(self.path)) == root:
            raise ContentPushRefused("the content folder cannot be the code folder")

    # --- local repo -------------------------------------------------------------------------------------------
    def ensure_local(self) -> None:
        if canonical(str(self.path)) == canonical(str(self.settings.root)):
            raise ContentPushRefused("the content folder cannot be the code folder")
        if not (self.path / ".git").exists():
            self.path.mkdir(parents=True, exist_ok=True)
            git(self.path, "init", "-q", "-b", "main")
            (self.path / "README.md").write_text(
                "# Social Automation — content\n\nReels made with Social Automation: `reels/<date>-<topic>/` "
                "(video, cover, script, research, sources). This repo belongs to its owner; the app only adds "
                "files here.\n", encoding="utf-8")
            self._identity()
            git(self.path, "add", "README.md")
            git(self.path, "commit", "-q", "-m", "Content repo")
        self._identity()

    def _identity(self) -> None:
        """A commit identity for this repo only (a new computer may have none configured)."""
        if git(self.path, "config", "user.email", check=False).stdout.strip():
            return
        info = self.account.info() if self.account else None
        if info and info.get("login"):
            name, email = info["login"], f"{info.get('id', 0)}+{info['login']}@users.noreply.github.com"
        else:
            global_email = git(self.path, "config", "--global", "user.email", check=False).stdout.strip()
            if global_email:
                return
            name, email = "Social Automation", "social-automation@localhost"
        git(self.path, "config", "user.name", name)
        git(self.path, "config", "user.email", email)

    def adopt_old_reels(self) -> list[str]:
        """Before Task 07 reels lived in <code repo>/reels/. Move them (files not tracked by the code repo) here."""
        old = self.settings.root / "reels"
        moved: list[str] = []
        if not old.is_dir():
            return moved
        tracked = git(self.settings.root, "ls-files", "reels", check=False).stdout.strip()
        if tracked:
            log.warning("reels/ is tracked by the code repo; not moving it automatically")
            return moved
        self.ensure_local()
        for d in sorted(old.iterdir()):
            target = self.reels / d.name
            if target.exists():
                continue
            self.reels.mkdir(parents=True, exist_ok=True)
            shutil.move(str(d), str(target))
            moved.append(d.name)
        if moved:
            git(self.path, "add", "--", "reels")
            git(self.path, "commit", "-q", "-m", f"Reels moved from the code folder ({len(moved)})")
        if not any(old.iterdir()):
            old.rmdir()
        return moved

    # --- publish ----------------------------------------------------------------------------------------------
    def lfs_available(self) -> bool:
        return git(self.path, "lfs", "version", check=False, env=self._path_env()).returncode == 0

    def _path_env(self) -> dict:
        return {"PATH": f"{self.settings.root / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"}   # git-lfs in ./bin

    def publish(self, base: str, files: dict[str, Path], title: str) -> GitResult:
        """Copy into reels/<base>/, commit exactly those paths, then push to the user's own remote (if any)."""
        self.ensure_local()
        dest = self.reels / base
        dest.mkdir(parents=True, exist_ok=True)
        rel_paths, lfs = [], []
        for name, src in files.items():
            target = dest / name
            shutil.copyfile(src, target)
            rel = target.relative_to(self.path).as_posix()
            rel_paths.append(rel)
            if target.stat().st_size > LFS_BYTES:
                if not self.lfs_available():
                    raise RuntimeError("a file is over 50 MB and Git LFS is not installed (Linux: "
                                       "scripts/install_git_lfs.sh, macOS: brew install git-lfs, Windows: winget "
                                       "install GitHub.GitLFS)")
                git(self.path, "lfs", "track", rel, env=self._path_env())
                lfs.append(rel)
        if lfs:
            rel_paths.append(".gitattributes")
        git(self.path, "add", "--", *rel_paths, env=self._path_env())
        staged = git(self.path, "diff", "--cached", "--name-only", "--", *rel_paths).stdout.strip()
        committed = False
        if staged:
            git(self.path, "commit", "-q", "-m", f"Reel: {title} ({base[:10]})", "--", *rel_paths, env=self._path_env())
            committed = True
        pushed, note = self.push()
        return GitResult(dest.relative_to(self.path).as_posix(), committed, pushed, lfs, note)

    def push(self) -> tuple[bool, str]:
        """Push main to the user's own content remote. Guarded; never --force. (False, note) when not possible."""
        url = self.remote_url()
        if not url:
            return False, NOTE_LOCAL
        self.guard(url)
        if self.account is not None and url.startswith("https://github.com/"):
            try:
                self.account.ensure_content_repo()
            except Exception:                      # noqa: BLE001
                log.warning("could not make sure the content repo exists", exc_info=True)
        env = self._path_env()
        args = ["push", url, "HEAD:main"]
        token = self.account.token() if (self.account is not None and url.startswith("https://")) else ""
        if token:
            # The token reaches git only through the environment of this one command (not argv, not the config).
            env["SA_GH_TOKEN"] = token
            args = ["-c", "credential.helper=",
                    "-c", "credential.helper=!f() { echo username=x-access-token; echo \"password=$SA_GH_TOKEN\"; }; f",
                    *args]
        res = git(self.path, *args, check=False, env=env)
        if res.returncode != 0:
            log.warning("content push failed: %s", _redact(res.stderr, token)[:300])
            return False, NOTE_FAILED
        self.mark_pushed()
        return True, NOTE_PUSHED

    # --- for the website ----------------------------------------------------------------------------------------
    def status(self) -> dict:
        url = self.remote_url()
        exists = (self.path / ".git").exists()
        reels: list[dict] = []
        unpushed = 0
        if exists:
            log_out = git(self.path, "log", "-n", "12", "--format=%ct%x09%s", check=False).stdout.splitlines()
            for line in log_out:
                ts, _, subject = line.partition("\t")
                if subject.startswith("Reel: "):
                    m = re.match(r"^(.*) \((\d{4}-\d\d-\d\d)\)$", subject[6:])
                    reels.append({"title": m.group(1) if m else subject[6:], "date": m.group(2) if m else "",
                                  "at": int(ts or 0)})
            if url:
                last = git(self.path, "config", "socialauto.lastpushed", check=False).stdout.strip()
                head = git(self.path, "rev-parse", "HEAD", check=False).stdout.strip()
                if head and last != head:
                    rng = f"{last}..HEAD" if last else "HEAD"
                    unpushed = int(git(self.path, "rev-list", "--count", rng, check=False).stdout.strip() or 0)
        return {"exists": exists, "remote": _remote_label(url), "remote_url": _browse_url(url), "reels": reels,
                "unpushed": unpushed, "count": len(list(self.reels.iterdir())) if self.reels.is_dir() else 0}

    def mark_pushed(self) -> None:
        head = git(self.path, "rev-parse", "HEAD", check=False).stdout.strip()
        if head:
            git(self.path, "config", "socialauto.lastpushed", head, check=False)


def _redact(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


_GH = re.compile(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/*$", re.I)


def _remote_label(url: str) -> str:
    m = _GH.search(url or "")
    return f"{m.group(1)}/{m.group(2)}" if m else ("Shu kompyuterdagi papka" if url else "")


def _browse_url(url: str) -> str:
    m = _GH.search(url or "")
    return f"https://github.com/{m.group(1)}/{m.group(2)}" if m else ""


__all__ = ["ContentRepo", "ContentPushRefused", "canonical", "code_repo_urls", "GitResult", "NOTE_LOCAL",
           "NOTE_PUSHED", "NOTE_FAILED"]

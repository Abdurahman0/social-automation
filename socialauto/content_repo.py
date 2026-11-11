"""The user's OWN content repo (Task 07).

Two repos, never mixed:
- the CODE repo (this folder, `origin` = the owner's `Abdurahman0/social-automation`) is only read: updates are
  fetched and fast-forwarded (socialauto/updater.py). The app never commits or pushes content to it.
- the CONTENT repo (`data/content-repo/`, git-ignored by the code repo) holds reels/<date>-<topic>/ (video, the
  owner's cover, script, research, sources) and is pushed to the user's own GitHub account
  (`<login>/social-automation-content`, private, created by the app) or to a remote the user set himself.

Task 09: the user may instead connect his EXISTING repo (e.g. a repo where he already keeps his reels). It is cloned
(partial + sparse: videos are not downloaded), every publish works ON TOP of his history (fetch, fast-forward or
rebase, never --force), only the new reel folder and one `posted.md` line are committed, and his own layout
(`reels/<date>-<topic>/reel.mp4`, `cover.jpg`, `script.md`) and brand rules are followed.

Hard guard (every computer, the owner's too): a content push to any URL of the upstream code repo — its configured
name, or any remote of this code folder — or into the code folder itself is refused. Never a force push.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
import time
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

LFS_BYTES = 50 * 1024 * 1024
NOTE_LOCAL = "GitHub ulanmagan: reel shu kompyuterda saqlandi (Sozlamalar → GitHub)"
NOTE_PUSHED = "Sizning GitHub'ingizga yuklandi"
NOTE_FAILED = "GitHub'ga yuklab bo'lmadi (internet yoki ruxsat yo'q): shu kompyuterda saqlandi, keyinroq yana urinadi"
NOTE_CONFLICT = ("GitHub'ga yuklanmadi: repongizda shu payt boshqa o'zgarish bor edi va u reel bilan to'qnashdi. Reel shu "
                 "kompyuterda saqlandi, sizning fayllaringizga tegilmadi. Keyingi reel yuklanganda yana urinib ko'raman")
NOTE_TOO_BIG = ("GitHub'ga yuklanmadi: video 100 MB dan katta va bu kompyuterda Git LFS yo'q. Reel shu kompyuterda "
                "saqlandi")
GITHUB_FILE_LIMIT = 95 * 1024 * 1024          # GitHub refuses files over 100 MB without LFS
MEDIA_EXCLUDE = ("*.mp4", "*.mov", "*.m4a", "*.wav", "*.mp3", "*.mkv", "*.webm")
PENDING_PREFIX = "socialauto/kutilmoqda/"
TASHKENT = ZoneInfo("Asia/Tashkent")
DATED = re.compile(r"^\d{4}-\d\d-\d\d-.+")
_clone_state: dict[str, dict] = {}            # content_dir -> {"state": "cloning" | "error" | "done", "at": ts}
_locks: dict[str, threading.RLock] = {}


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
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=check,
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
    url: str = ""                    # the reel folder on GitHub (when pushed)
    conflict: bool = False
    files: list[str] = field(default_factory=list)


def parse_repo_ref(text: str) -> str:
    """A pasted link or "owner/name" -> "owner/name" ("" when it is not a GitHub repo)."""
    t = (text or "").strip()
    m = re.match(r"^(?:https?://)?(?:www\.)?github\.com[:/]+([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:[/?#].*)?$", t, re.I)
    if not m:
        m = re.match(r"^git@github\.com:([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?$", t, re.I)
    if not m:
        m = re.match(r"^([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?$", t)
    if not m or m.group(2) in (".", ".."):
        return ""
    return f"{m.group(1)}/{m.group(2)}"


def when(ts: float) -> str:
    """Tashkent time: "8-noyabr, 11:24"."""
    from .web.repo import MONTHS
    dt = datetime.fromtimestamp(ts, TASHKENT)
    return f"{dt.day}-{MONTHS[dt.month - 1]}, {dt:%H:%M}"


class ContentRepo:
    def __init__(self, settings, account=None):
        self.settings = settings
        self.account = account                      # socialauto.github_account.GitHubAccount (or None)
        self.path = settings.resolve(settings.github.content_dir)

    # --- the user's choice (live: the website may change it while the bot runs) -----------------------------------
    def choice(self) -> dict:
        """{"mode": "" | "new" | "existing", "existing": "owner/name", "remote": fixed URL}. config.local.toml is read
        on every call, so a choice made on the website reaches the bot without a restart."""
        g = self.settings.github
        out = {"mode": g.content_mode, "existing": g.content_existing, "remote": g.content_remote}
        local = self.settings.root / "config.local.toml"
        try:
            sec = tomllib.loads(local.read_text(encoding="utf-8")).get("github", {}) if local.exists() else {}
        except (OSError, ValueError):
            sec = {}
        for key, name in (("mode", "content_mode"), ("existing", "content_existing"), ("remote", "content_remote")):
            if name in sec:
                out[key] = str(sec[name])
        return out

    def is_existing(self) -> bool:
        return self.choice()["mode"] == "existing"

    def choose(self, mode: str, existing: str = "") -> None:
        """Save the user's choice for THIS computer (config.local.toml). The repo itself is prepared by prepare()."""
        from .config import set_local_value
        if mode == "existing":
            ref = parse_repo_ref(existing)
            if not ref:
                raise ValueError("bad_link")
            self.guard(f"https://github.com/{ref}.git")          # the code repo is never a content repo
            set_local_value(self.settings.root, "github", "content_existing", ref)
            set_local_value(self.settings.root, "github", "content_remote", "")
        elif mode == "new":
            set_local_value(self.settings.root, "github", "content_existing", "")
        else:
            raise ValueError("bad_mode")
        set_local_value(self.settings.root, "github", "content_mode", mode)

    # --- where things go ------------------------------------------------------------------------------------
    @property
    def reels(self) -> Path:
        return self.path / "reels"

    def remote_url(self) -> str:
        """The user's own content remote: his existing repo (Task 09), a fixed one from config.local.toml, else the
        new private repo in his connected GitHub account."""
        c = self.choice()
        if c["mode"] == "existing":
            if c["remote"]:
                return c["remote"]
            return f"https://github.com/{c['existing']}.git" if c["existing"] else ""
        if c["remote"]:
            return c["remote"]
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

    def _lock(self) -> threading.RLock:
        return _locks.setdefault(str(self.path), threading.RLock())

    # --- auth for network commands ----------------------------------------------------------------------------
    def _net(self, url: str) -> tuple[list[str], dict, str]:
        """git -c options + env so a network command can use the user's GitHub token. The token reaches git only
        through the environment of that one command (not argv, not the config)."""
        env = self._path_env()
        token = self.account.token() if (self.account is not None and url.startswith("https://")) else ""
        if not token:
            return [], env, ""
        env["SA_GH_TOKEN"] = token
        return ["-c", "credential.helper=",
                "-c", "credential.helper=!f() { echo username=x-access-token; echo \"password=$SA_GH_TOKEN\"; }; f"], env, token

    def _netgit(self, *args: str, url: str | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
        url = url if url is not None else self.remote_url()
        opts, env, token = self._net(url)
        res = git(cwd or self.path, *opts, *args, check=False, env=env, timeout=3600)
        if res.returncode != 0:
            log.warning("git %s failed: %s", args[0], _redact(res.stderr, token)[:300])
        return res

    # --- local repo -------------------------------------------------------------------------------------------
    def ensure_local(self) -> None:
        if canonical(str(self.path)) == canonical(str(self.settings.root)):
            raise ContentPushRefused("the content folder cannot be the code folder")
        if self.is_existing():
            self._ensure_clone()
            self._identity()
            return
        if (self.path / ".git").exists() and self._cfg("socialauto.kind") == "existing":
            self._move_aside()                      # switched back to a new repo: the old clone is kept, renamed
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
            url = self.remote_url()
            if url:
                git(self.path, "config", "socialauto.remote", canonical(url))
        self._identity()

    def _cfg(self, key: str) -> str:
        return git(self.path, "config", key, check=False).stdout.strip()

    def _move_aside(self) -> Path:
        """The old local clone is never deleted: it is renamed next to the new one."""
        label = re.sub(r"[^A-Za-z0-9_.-]+", "-", (self._cfg("socialauto.remote") or "eski").rsplit("/", 1)[-1])[:40]
        target = self.path.with_name(f"{self.path.name}.{label}-{datetime.now():%Y%m%d-%H%M%S}")
        self.path.rename(target)
        log.info("old content repo kept as %s", target.name)
        return target

    def _ensure_clone(self) -> None:
        url = self.remote_url()
        if not url:
            raise RuntimeError("no existing repo chosen")
        self.guard(url)
        want = canonical(url)
        if (self.path / ".git").exists():
            if self._cfg("socialauto.remote") == want:
                return
            self._move_aside()
        elif self.path.exists() and any(self.path.iterdir()):
            self._move_aside()
        self._clone(url, want)

    def _clone(self, url: str, want: str) -> None:
        """Partial + sparse clone: the full history and every text file, but no videos/audio on disk (the repo can
        be hundreds of MB). His history is kept as is — never `git init` over it."""
        tmp = self.path.with_name(self.path.name + ".cloning")
        if tmp.exists():
            shutil.rmtree(tmp)                     # our own unfinished clone from an interrupted run
        tmp.parent.mkdir(parents=True, exist_ok=True)
        res = self._netgit("clone", "-q", "--no-checkout", "--filter=blob:limit=1m", url, str(tmp), url=url,
                           cwd=tmp.parent)
        if res.returncode != 0:
            shutil.rmtree(tmp, ignore_errors=True)
            raise RuntimeError("clone failed")
        git(tmp, "config", "socialauto.remote", want)
        git(tmp, "config", "socialauto.kind", "existing")
        git(tmp, "config", "remote.origin.pushurl", url)
        git(tmp, "sparse-checkout", "set", "--no-cone", "/*", *[f"!{p}" for p in MEDIA_EXCLUDE])
        opts, env, _ = self._net(url)
        co = git(tmp, *opts, "checkout", "-q", self._branch(tmp), check=False, env=env, timeout=3600)
        if co.returncode != 0:
            co = git(tmp, *opts, "read-tree", "-mu", "HEAD", check=False, env=env, timeout=3600)
        if co.returncode != 0:
            shutil.rmtree(tmp, ignore_errors=True)
            raise RuntimeError("checkout failed")
        git(tmp, "config", "socialauto.lastsync", str(int(time.time())))
        tmp.rename(self.path)

    def _branch(self, repo: Path | None = None) -> str:
        repo = repo or self.path
        ref = git(repo, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD", check=False).stdout.strip()
        if ref.startswith("origin/"):
            return ref[7:]
        head = git(repo, "symbolic-ref", "-q", "--short", "HEAD", check=False).stdout.strip()
        return head or "main"

    def prepare(self) -> None:
        """Make the local repo ready (clone his repo / init a new one). Safe to call from a background thread."""
        key = str(self.path)
        with self._lock():
            _clone_state[key] = {"state": "cloning", "at": time.time()}
            try:
                self.ensure_local()
                _clone_state[key] = {"state": "done", "at": time.time()}
            except Exception:                        # noqa: BLE001 - shown on the website in plain words
                log.warning("content repo not prepared", exc_info=True)
                _clone_state[key] = {"state": "error", "at": time.time()}

    def prepare_async(self) -> None:
        threading.Thread(target=self.prepare, daemon=True, name="content-repo-prepare").start()

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
        if not old.is_dir() or self.is_existing():
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

    # --- his layout (Task 09) ---------------------------------------------------------------------------------
    def tree(self, prefix: str = "") -> list[str]:
        """Every tracked path at HEAD (works with the sparse checkout: files not on disk are listed too)."""
        if not (self.path / ".git").exists():
            return []
        args = ["ls-tree", "-r", "--name-only", "HEAD"] + ([prefix] if prefix else [])
        return [x for x in git(self.path, *args, check=False).stdout.splitlines() if x]

    def layout(self) -> str:
        """"named" when the repo keeps reels as reels/<date>-<topic>/reel.mp4 + cover.jpg (his layout), else our
        default (reels/<base>/<base>.mp4, <base>_cover.jpg)."""
        if not self.is_existing():
            return "default"
        for p in self.tree("reels"):
            parts = p.split("/")
            if len(parts) == 3 and DATED.match(parts[1]) and re.fullmatch(r"reel\.mp4|cover\.(jpe?g|png)", parts[2]):
                return "named"
        return "default"

    def reel_files(self, base: str, video: Path, cover: Path, script_md: Path,
                   extras: dict[str, Path] | None = None) -> dict[str, Path]:
        """The file names of a new reel folder, following the repo's own layout."""
        if self.is_existing() and not (self.path / ".git").exists():
            with self._lock():
                self.ensure_local()
        if self.layout() == "named":
            return {"reel.mp4": video, f"cover{cover.suffix.lower()}": cover, "script.md": script_md}
        out = {f"{base}.mp4": video, f"{base}_cover{cover.suffix}": cover, "script.md": script_md}
        out.update(extras or {})
        return out

    def uses_lfs(self) -> bool:
        try:
            text = git(self.path, "show", "HEAD:.gitattributes", check=False).stdout
        except Exception:                            # noqa: BLE001
            return False
        return "filter=lfs" in text

    def _free_folder(self, base: str, names: list[str]) -> str:
        """Never overwrite his files: if reels/<base>/ already holds a file of the same name that WE did not commit,
        the reel goes to reels/<base>-2/ (…-3, …)."""
        tracked = set(self.tree("reels"))
        candidate, n = base, 1
        while True:
            clash = [f"reels/{candidate}/{x}" for x in names if f"reels/{candidate}/{x}" in tracked]
            if not clash or all(self._ours(p) for p in clash):
                return candidate
            n += 1
            candidate = f"{base}-{n}"

    def _ours(self, path: str) -> bool:
        subjects = git(self.path, "log", "--format=%s", "--", path, check=False).stdout.splitlines()
        return bool(subjects) and all(s.startswith("Reel: ") for s in subjects)

    # --- sync with his remote (Task 09) -----------------------------------------------------------------------
    def sync(self) -> str:
        """Fetch his latest history, then fast-forward or rebase our local commits on top. Never --force, never a
        merge over his files. Returns "ok" | "offline" | "conflict" (the rebase is aborted, nothing is lost)."""
        branch = self._branch()
        res = self._netgit("fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}")
        if res.returncode != 0:
            return "offline"
        git(self.path, "config", "socialauto.lastsync", str(int(time.time())))
        upstream = f"refs/remotes/origin/{branch}"
        if git(self.path, "merge-base", "--is-ancestor", upstream, "HEAD", check=False).returncode == 0:
            return "ok"                                            # we are up to date (maybe ahead)
        if git(self.path, "merge-base", "--is-ancestor", "HEAD", upstream, check=False).returncode == 0:
            r = self._netgit("merge", "-q", "--ff-only", upstream)
            return "ok" if r.returncode == 0 else "conflict"
        r = self._netgit("rebase", "-q", upstream)
        if r.returncode != 0:
            git(self.path, "rebase", "--abort", check=False)
            return "conflict"
        return "ok"

    def _keep_pending(self, folder: str) -> None:
        """A conflict: our reel commit(s) are kept on a local branch, main follows his history again."""
        branch = self._branch()
        touched = git(self.path, "log", "-n1", "--name-only", "--format=", "--grep", "^Reel: ",
                      f"refs/remotes/origin/{branch}..HEAD", check=False).stdout.split()
        reel = next((t.split("/")[1] for t in touched if t.startswith("reels/") and t.count("/") >= 2), "")
        name = PENDING_PREFIX + (reel or folder.rsplit("/", 1)[-1])
        git(self.path, "branch", "-f", name, "HEAD")
        git(self.path, "reset", "-q", "--keep", f"refs/remotes/origin/{branch}", check=False)
        if git(self.path, "rev-parse", "HEAD").stdout.strip() != git(self.path, "rev-parse", f"refs/remotes/origin/{branch}").stdout.strip():
            opts, env, _ = self._net(self.remote_url())
            git(self.path, *opts, "checkout", "-q", "-B", branch, f"refs/remotes/origin/{branch}", check=False, env=env)

    def pending(self) -> list[str]:
        out = git(self.path, "for-each-ref", "--format=%(refname:short)", f"refs/heads/{PENDING_PREFIX}", check=False).stdout
        return [x[len(PENDING_PREFIX):] for x in out.splitlines() if x]

    def _retry_pending(self) -> None:
        """Earlier reels kept after a conflict: try once more to put them on top of his history."""
        for name in self.pending():
            ref = PENDING_PREFIX + name
            commits = git(self.path, "rev-list", "--reverse", f"HEAD..{ref}", check=False).stdout.split()
            ok = True
            for c in commits:
                r = self._netgit("cherry-pick", "--allow-empty", "--keep-redundant-commits", c)
                if r.returncode != 0:
                    git(self.path, "cherry-pick", "--abort", check=False)
                    ok = False
                    break
            if ok:
                git(self.path, "branch", "-D", ref, check=False)

    def _push_existing(self, folder: str) -> tuple[bool, str, bool]:
        """Push on top of his latest history: (pushed, note, conflict). A rejected push (he pushed meanwhile) is
        fetched and rebased again; never --force."""
        url = self.remote_url()
        self.guard(url)
        branch = self._branch()
        for _ in range(3):
            st = self.sync()
            if st == "offline":
                return False, NOTE_FAILED, False
            if st == "conflict":
                self._keep_pending(folder)
                return False, NOTE_CONFLICT, True
            res = self._netgit("push", "-q", url, f"HEAD:refs/heads/{branch}", url=url)
            if res.returncode == 0:
                self.mark_pushed()
                return True, self.pushed_note(), False
            if not re.search(r"rejected|non-fast-forward|fetch first", res.stderr, re.I):
                return False, NOTE_FAILED, False
        return False, NOTE_FAILED, False

    def pushed_note(self) -> str:
        label = self.choice()["existing"] or _remote_label(self.remote_url())
        if self.is_existing() and "/" in label:
            return f"Reel sizning {label.split('/', 1)[1]} repongizga yuklandi"
        return NOTE_PUSHED

    def browse_url(self) -> str:
        c = self.choice()
        if c["mode"] == "existing" and c["existing"]:
            return f"https://github.com/{c['existing']}"
        return _browse_url(self.remote_url())

    def folder_url(self, folder: str) -> str:
        browse = self.browse_url()
        if not browse:
            return ""
        branch = self._branch() if (self.path / ".git").exists() else "main"
        return f"{browse}/tree/{branch}/{folder}"

    # --- publish ----------------------------------------------------------------------------------------------
    def lfs_available(self) -> bool:
        return git(self.path, "lfs", "version", check=False, env=self._path_env()).returncode == 0

    def _path_env(self) -> dict:
        return {"PATH": f"{self.settings.root / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"}   # git-lfs in ./bin

    def publish(self, base: str, files: dict[str, Path], title: str) -> GitResult:
        """Copy into reels/<base>/, commit exactly those paths, then push to the user's own remote (if any)."""
        with self._lock():
            if self.is_existing():
                return self._publish_existing(base, files, title)
            return self._publish_new(base, files, title)

    def _publish_new(self, base: str, files: dict[str, Path], title: str) -> GitResult:
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
        folder = dest.relative_to(self.path).as_posix()
        return GitResult(folder, committed, pushed, lfs, note, self.folder_url(folder) if pushed else "",
                         files=rel_paths)

    def _publish_existing(self, base: str, files: dict[str, Path], title: str) -> GitResult:
        """His repo: sync first, add ONLY the new reel folder (his layout), commit, push on top of his history."""
        self.ensure_local()
        self._retry_pending()
        self.sync()                                   # start from his latest main (offline: we still commit locally)
        folder_name = self._free_folder(base, list(files))
        dest = self.reels / folder_name
        dest.mkdir(parents=True, exist_ok=True)
        rel_paths, lfs = [], []
        # Follow what he does: a repo without LFS gets files committed directly (as he does) up to GitHub's limit;
        # a repo that uses LFS gets LFS for big files, like ours.
        limit = LFS_BYTES if self.uses_lfs() else GITHUB_FILE_LIMIT
        lfs_names = [n for n, src in files.items() if Path(src).stat().st_size > limit]
        if lfs_names and not self.lfs_available():
            folder = f"reels/{folder_name}"
            return GitResult(folder, False, False, [], NOTE_TOO_BIG)
        for name, src in files.items():
            shutil.copyfile(src, dest / name)
            rel_paths.append(f"reels/{folder_name}/{name}")
        if lfs_names:
            # The LFS rule lives INSIDE the reel folder: his root .gitattributes is never touched.
            (dest / ".gitattributes").write_text(
                "".join(f"{n} filter=lfs diff=lfs merge=lfs -text\n" for n in lfs_names), encoding="utf-8")
            rel_paths.insert(0, f"reels/{folder_name}/.gitattributes")
            lfs = [f"reels/{folder_name}/{n}" for n in lfs_names]
        git(self.path, "add", "--sparse", "--", *rel_paths, env=self._path_env())
        staged = git(self.path, "diff", "--cached", "--name-only", "--", *rel_paths).stdout.strip()
        committed = False
        if staged:
            git(self.path, "commit", "-q", "-m", f"Reel: {title} ({base[:10]})", "--", *rel_paths, env=self._path_env())
            committed = True
        folder = f"reels/{folder_name}"
        if not self.remote_url():
            return GitResult(folder, committed, False, lfs, NOTE_LOCAL, files=rel_paths)
        pushed, note, conflict = self._push_existing(folder)
        return GitResult(folder, committed, pushed, lfs, note, self.folder_url(folder) if pushed else "", conflict,
                         rel_paths)

    def push(self) -> tuple[bool, str]:
        """Push main to the user's own content remote. Guarded; never --force. (False, note) when not possible."""
        url = self.remote_url()
        if not url:
            return False, NOTE_LOCAL
        self.guard(url)
        if self.is_existing():
            pushed, note, _ = self._push_existing("reels")
            return pushed, note
        if self.account is not None and url.startswith("https://github.com/"):
            try:
                self.account.ensure_content_repo()
            except Exception:                      # noqa: BLE001
                log.warning("could not make sure the content repo exists", exc_info=True)
        res = self._netgit("push", url, "HEAD:main", url=url)
        if res.returncode != 0:
            return False, NOTE_FAILED
        self.mark_pushed()
        return True, NOTE_PUSHED

    # --- posted.md (Task 09: his log, his format) ---------------------------------------------------------------
    def posted_line(self, values: dict[str, str]) -> str | None:
        """One line for posted.md in the file's own column format, or None when the repo has no posted.md."""
        if "posted.md" not in self.tree("posted.md"):
            return None
        text = git(self.path, "show", "HEAD:posted.md", check=False).stdout
        header = next((ln for ln in text.splitlines() if "|" in ln and re.search(r"YYYY|date|sana", ln, re.I)), "")
        rows = [ln for ln in text.splitlines() if re.match(r"^\s*\d{4}-\d\d-\d\d\s*\|", ln)]
        cols = [c.strip().lower() for c in header.split("|")] if header else []
        if not cols:
            n = len(rows[-1].split("|")) if rows else 5
            cols = ["yyyy-mm-dd", "pillar", "topic", "hook", "cta#"][:n] + [""] * max(0, n - 5)
        pillars = [r.split("|")[1].strip() for r in rows if len(r.split("|")) > 1]
        reel_pillar = next((p for p in pillars if p.lower() in ("reel", "reels")), "REEL")
        cta_vals = [r.split("|")[-1].strip() for r in rows if r.split("|")[1].strip() == reel_pillar]
        out = []
        for c in cols:
            if re.search(r"yyyy|date|sana", c):
                v = values["date"]
            elif re.search(r"pillar|rukn|turi|type", c):
                v = reel_pillar
            elif re.search(r"topic|mavzu|title", c):
                v = values["topic"]
            elif re.search(r"hook", c):
                v = values["hook"]
            elif re.search(r"cta", c):
                v = cta_vals[-1] if cta_vals else "-"
            else:
                v = "-"
            out.append(" ".join(str(v).replace("|", "/").split()))
        return " | ".join(out)

    def append_posted(self, values: dict[str, str]) -> bool:
        """Append one line to his posted.md (only in his repo, only when it exists), commit just that file, push on
        top of his history. A concurrent edit of posted.md is handled by re-reading his file and appending again."""
        if not self.is_existing():
            return False
        with self._lock():
            self.ensure_local()
            if self.sync() == "conflict":
                return False
            for _ in range(2):
                line = self.posted_line(values)
                if line is None:
                    return False
                text = git(self.path, "show", "HEAD:posted.md", check=False).stdout
                if values["topic"] in text:
                    return True                                       # already there (a retried job)
                body = text if text.endswith("\n") or not text else text + "\n"
                (self.path / "posted.md").write_text(body + line + "\n", encoding="utf-8")
                git(self.path, "add", "--", "posted.md")
                git(self.path, "commit", "-q", "-m", f"posted.md: {values['title']} (Buffer navbatida)", "--", "posted.md")
                if not self.remote_url():
                    return True
                pushed, _note, conflict = self._push_existing("posted.md")
                if pushed:
                    return True
                if not conflict:
                    return False                                      # offline: the commit stays, pushed next time
                branch = self._branch()
                git(self.path, "branch", "-D", PENDING_PREFIX + "posted.md", check=False)   # regenerated below
                git(self.path, "reset", "-q", "--keep", f"refs/remotes/origin/{branch}", check=False)
            return False

    # --- his brand and examples (read-only; Task 09) ------------------------------------------------------------
    def brand(self) -> dict | None:
        """His brand rules for Claude: brand/*.md (not templates), guidance-book.md, and his own brand/workflow
        skills. {"text", "max_seconds", "min_seconds", "files"} or None."""
        if not self.is_existing() or not self._ready():
            return None
        files: list[Path] = []
        files += sorted(p for p in (self.path / "brand").glob("*.md") if "template" not in p.name.lower())
        files += [p for p in (self.path / "guidance-book.md", self.path / "GUIDANCE.md") if p.exists()]
        skills = self.path / ".claude" / "skills"
        if skills.is_dir():
            files += sorted(p for p in skills.glob("*/SKILL.md")
                            if re.search(r"brand|workflow|voice|style|uslub", p.parent.name, re.I))
        parts, total = [], 0
        for f in files:
            try:
                t = f.read_text(encoding="utf-8")[:7000]
            except OSError:
                continue
            if total + len(t) > 24000:
                break
            total += len(t)
            parts.append(f"### {f.relative_to(self.path).as_posix()}\n{t.strip()}")
        if not parts:
            return None
        text = "\n\n".join(parts)
        max_s = None
        for f in files:                              # the first file that says it wins (voice.md is the newest rule)
            try:
                m = re.search(r"(?:maks(?:imum)?|max(?:imum)?)\.?\s*(\d{2})\s*(?:s\b|soniya|sec)", f.read_text(encoding="utf-8"), re.I)
            except OSError:
                m = None
            if m:
                max_s = int(m.group(1))
                break
        return {"text": text, "max_seconds": max_s, "min_seconds": max(20, max_s - 15) if max_s else None,
                "files": [f.relative_to(self.path).as_posix() for f in files]}

    def examples(self, limit: int = 10) -> str:
        """His past reels (title + first spoken line) and his latest audit, as examples for topic/hook ideas."""
        if not self.is_existing() or not self._ready() or not self.reels.is_dir():
            return ""
        lines = []
        folders = sorted({p.split("/")[1] for p in self.tree("reels") if p.count("/") >= 2}, reverse=True)
        for name in folders[:limit]:
            sm = self.reels / name / "script.md"
            title, first = name[11:].replace("-", " "), ""
            if sm.exists():
                text = sm.read_text(encoding="utf-8", errors="replace")
                m = re.search(r"^#\s+(.+)$", text, re.M)
                title = m.group(1).strip() if m else title
                m = re.search(r"^\s*1\.\s*(?:\([\d.,]+\s*s\)\s*)?(.+)$", text, re.M)
                first = m.group(1).strip()[:160] if m else ""
            lines.append(f"- {name[:10]} · {title}" + (f" — «{first}»" if first else ""))
        audits = sorted((self.path / "audits").glob("*.md")) if (self.path / "audits").is_dir() else []
        out = "HIS PAST REELS (newest first):\n" + "\n".join(lines)
        if audits:
            out += f"\n\nHIS LATEST AUDIT ({audits[-1].name}):\n" + audits[-1].read_text(encoding="utf-8", errors="replace")[:3000]
        return out

    def _ready(self) -> bool:
        """His repo is cloned (cloned now if it is not yet — e.g. the choice was made on another run)."""
        if (self.path / ".git").exists() and self._cfg("socialauto.remote") == canonical(self.remote_url()):
            return True
        if _clone_state.get(str(self.path), {}).get("state") == "cloning":
            return False
        try:
            with self._lock():
                self.ensure_local()
            return True
        except Exception:                            # noqa: BLE001 - brand rules are extra context, never a blocker
            log.warning("content repo not ready yet", exc_info=True)
            return False

    def skills_dir(self) -> Path | None:
        d = self.path / ".claude" / "skills"
        return d if self.is_existing() and d.is_dir() else None

    # --- for the website ----------------------------------------------------------------------------------------
    def status(self) -> dict:
        url = self.remote_url()
        exists = (self.path / ".git").exists()
        c = self.choice()
        reels: list[dict] = []
        unpushed = 0
        last_sync, branch, count, last = "", "", 0, None
        if exists:
            log_out = git(self.path, "log", "-n", "200", "--format=%ct%x09%s", check=False).stdout.splitlines()
            for line in log_out:
                ts, _, subject = line.partition("\t")
                if subject.startswith("Reel: ") and len(reels) < 12:
                    m = re.match(r"^(.*) \((\d{4}-\d\d-\d\d)\)$", subject[6:])
                    reels.append({"title": m.group(1) if m else subject[6:], "date": m.group(2) if m else "",
                                  "at": int(ts or 0)})
            if url:
                if c["mode"] == "existing":
                    br = self._branch()
                    unpushed = int(git(self.path, "rev-list", "--count", f"refs/remotes/origin/{br}..HEAD",
                                       check=False).stdout.strip() or 0)
                else:
                    lastp = git(self.path, "config", "socialauto.lastpushed", check=False).stdout.strip()
                    head = git(self.path, "rev-parse", "HEAD", check=False).stdout.strip()
                    if head and lastp != head:
                        rng = f"{lastp}..HEAD" if lastp else "HEAD"
                        unpushed = int(git(self.path, "rev-list", "--count", rng, check=False).stdout.strip() or 0)
            branch = self._branch()
            ls = self._cfg("socialauto.lastsync") or self._cfg("socialauto.lastpushedat")
            last_sync = when(int(ls)) if ls.isdigit() else ""
            count = len({p.split("/")[1] for p in self.tree("reels") if p.count("/") >= 2})
            if reels:
                r0 = reels[0]
                hit = git(self.path, "log", "-n1", "--name-only", "--format=", "--grep", "^Reel: ", check=False).stdout.split()
                folder = "/".join(hit[0].split("/")[:2]) if hit else ""
                last = {"title": r0["title"], "date": r0["date"], "when": when(r0["at"]) if r0["at"] else "",
                        "url": self.folder_url(folder) if folder and url else ""}
        prep = _clone_state.get(str(self.path), {}).get("state", "")
        return {"exists": exists, "mode": c["mode"] or ("new" if url else ""), "existing": c["existing"],
                "remote": c["existing"] if c["mode"] == "existing" and c["existing"] else _remote_label(url),
                "remote_url": self.browse_url(), "reels": reels, "unpushed": unpushed,
                "count": count, "branch": branch, "last_sync": last_sync, "last": last,
                "pending": len(self.pending()) if exists else 0, "preparing": prep,
                "layout": self.layout() if exists else "default"}

    def mark_pushed(self) -> None:
        head = git(self.path, "rev-parse", "HEAD", check=False).stdout.strip()
        if head:
            git(self.path, "config", "socialauto.lastpushed", head, check=False)
            git(self.path, "config", "socialauto.lastpushedat", str(int(time.time())), check=False)


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
           "NOTE_PUSHED", "NOTE_FAILED", "NOTE_CONFLICT", "parse_repo_ref"]

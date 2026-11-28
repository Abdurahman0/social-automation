"""A stable public link for the files Buffer must fetch (the reel's video, the story's cover).

Buffer has no upload endpoint: it takes a URL and fetches the file **when the post goes out**, which for a queued post
can be hours or days later ("the URL must stay reachable until the post publishes", developers.buffer.com/guides/
hosting-media). The old temporary Cloudflare quick tunnel was closed right after `createPost`, so a queued reel had no
video left to fetch at its posting time.

Here the files go to the user's OWN public GitHub Pages repo (`<login>/social-automation-media`, made by the app with
the GitHub login from the website; free): a direct HTTPS link with the right content type that stays up across
restarts. Each file sits under a random folder name. When Buffer reports the post sent (or the post is gone), the file
is deleted again (`forget`). The code repo is never touched; the private content repo stays private.
"""

from __future__ import annotations

import base64
import json
import logging
import secrets
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import requests

log = logging.getLogger(__name__)

API = "https://api.github.com"
REPO = "social-automation-media"
MAX_BYTES = 95 * 1024 * 1024              # GitHub refuses files over 100 MB
MIME = {".mp4": "video/", ".mov": "video/", ".jpg": "image/", ".jpeg": "image/", ".png": "image/"}


class MediaHostError(RuntimeError):
    """Plain-Uzbek reason (shown to the owner through the error reporter)."""


class GitHubPagesHost:
    def __init__(self, account, registry: Path, repo: str = REPO, session: requests.Session | None = None,
                 wait_seconds: float = 600.0, poll_seconds: float = 10.0):
        self.account = account                 # socialauto.github_account.GitHubAccount
        self.registry = registry               # data/media_host.json: {local path: repo path}
        self.repo = repo
        self.s = session or requests.Session()
        self.wait_seconds = wait_seconds
        self.poll_seconds = poll_seconds
        self._lock = threading.Lock()

    # --- GitHub -------------------------------------------------------------------------------------------------
    def _api(self, method: str, path: str, **kw) -> requests.Response:
        token = self.account.token() if self.account is not None else ""
        if not token:
            raise MediaHostError("GitHub ulanmagan: Buffer videoni ochiq havoladan oladi, havola esa GitHub orqali "
                                 "beriladi. Saytdagi «Sozlamalar → GitHub» da «GitHub'ni ulash» ni bosing.")
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "social-automation"}
        try:
            return self.s.request(method, API + path, headers=headers, timeout=300, **kw)
        except requests.RequestException:
            raise MediaHostError("GitHub bilan aloqa yo'q (internet?)") from None

    def _login(self) -> str:
        info = self.account.info() if self.account is not None else None
        if not info or not info.get("login"):
            raise MediaHostError("GitHub ulanmagan: saytdagi «Sozlamalar → GitHub» da «GitHub'ni ulash» ni bosing.")
        return info["login"]

    def _ensure_repo(self, login: str) -> None:
        r = self._api("GET", f"/repos/{login}/{self.repo}")
        if r.status_code == 200:
            if r.json().get("private"):
                raise MediaHostError(f"GitHub'dagi «{self.repo}» reposi yopiq (private): Buffer undan video ololmaydi. "
                                     "Uni ochiq (public) qiling yoki o'chirib yuboring — bot o'zi qayta yaratadi.")
            return
        r = self._api("POST", "/user/repos", json={
            "name": self.repo, "private": False, "auto_init": True, "has_issues": False, "has_wiki": False,
            "description": "Social Automation: reel files Buffer fetches at posting time (deleted after posting)"})
        if r.status_code in (403, 404):
            raise MediaHostError(f"GitHub kaliti yangi repo yarata olmaydi. github.com'da «{self.repo}» nomli OCHIQ "
                                 "(public) repo yarating yoki saytda GitHub'ni «GitHub'ni ulash» tugmasi bilan qayta ulang.")
        if r.status_code not in (201, 422):
            raise MediaHostError(f"GitHub'da «{self.repo}» reposini yaratib bo'lmadi")
        for _ in range(10):                    # auto_init's first commit appears a moment later
            if self._api("GET", f"/repos/{login}/{self.repo}/contents/README.md").status_code == 200:
                break
            time.sleep(1)
        self._put(login, ".nojekyll", b"", "no Jekyll: files are served as they are")

    def _pages_url(self, login: str) -> str:
        r = self._api("GET", f"/repos/{login}/{self.repo}/pages")
        if r.status_code != 200:
            branch = (self._api("GET", f"/repos/{login}/{self.repo}").json() or {}).get("default_branch") or "main"
            c = self._api("POST", f"/repos/{login}/{self.repo}/pages", json={"source": {"branch": branch, "path": "/"}})
            if c.status_code not in (201, 409):
                raise MediaHostError(f"«{self.repo}» uchun GitHub Pages yoqilmadi. github.com → {self.repo} → Settings "
                                     "→ Pages → Branch: main → Save ni bosing.")
            r = self._api("GET", f"/repos/{login}/{self.repo}/pages")
        url = (r.json() or {}).get("html_url") if r.status_code == 200 else None
        return (url or f"https://{login.lower()}.github.io/{self.repo}/").rstrip("/") + "/"

    def _put(self, login: str, path: str, data: bytes, message: str) -> None:
        body = {"message": message, "content": base64.b64encode(data).decode("ascii")}
        old = self._api("GET", f"/repos/{login}/{self.repo}/contents/{path}")
        if old.status_code == 200:
            body["sha"] = old.json().get("sha")
        r = self._api("PUT", f"/repos/{login}/{self.repo}/contents/{path}", json=body)
        if r.status_code not in (200, 201):
            raise MediaHostError("faylni GitHub'ga yuklab bo'lmadi")

    def _wait_live(self, url: str, suffix: str) -> None:
        want = MIME.get(suffix.lower(), "")
        deadline = time.monotonic() + self.wait_seconds
        while True:
            try:
                r = self.s.head(url, timeout=30, allow_redirects=False)
                if r.status_code == 200 and r.headers.get("content-type", "").startswith(want):
                    return
            except requests.RequestException:
                pass
            if time.monotonic() >= deadline:
                raise MediaHostError("GitHub Pages havolasi 10 daqiqada ochilmadi")
            time.sleep(self.poll_seconds)

    # --- registry -----------------------------------------------------------------------------------------------
    def _load(self) -> dict[str, str]:
        try:
            return json.loads(self.registry.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict[str, str]) -> None:
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        self.registry.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # --- public -------------------------------------------------------------------------------------------------
    def publish(self, path: Path) -> str:
        """A stable public URL for this file (the same URL again if it is already up)."""
        if path.stat().st_size > MAX_BYTES:
            raise MediaHostError(f"fayl {path.stat().st_size // 1_000_000} MB — GitHub 95 MB dan kattasini qabul qilmaydi")
        with self._lock:
            login = self._login()
            self._ensure_repo(login)
            base = self._pages_url(login)
            reg = self._load()
            rel = reg.get(str(path))
            if not rel:
                rel = f"r/{secrets.token_urlsafe(12)}/{path.name}"
                self._put(login, rel, path.read_bytes(), f"add {path.name}")
                reg[str(path)] = rel
                self._save(reg)
        url = base + rel
        self._wait_live(url, path.suffix)
        return url

    def forget(self, path: Path) -> bool:
        """Delete the file from the public repo (after Buffer posted it). True if it is gone."""
        with self._lock:
            reg = self._load()
            rel = reg.get(str(path))
            if not rel:
                return True
            login = self._login()
            r = self._api("GET", f"/repos/{login}/{self.repo}/contents/{rel}")
            if r.status_code == 200:
                d = self._api("DELETE", f"/repos/{login}/{self.repo}/contents/{rel}",
                              json={"message": f"remove {path.name} (posted)", "sha": r.json().get("sha")})
                if d.status_code not in (200, 404):
                    return False
            reg.pop(str(path), None)
            self._save(reg)
            return True

    def links(self, files: list[Path]):
        """The `public_files` interface of publish.queue_posts: URLs that stay up after the block ends."""
        @contextmanager
        def cm() -> Iterator[list[str]]:
            yield [self.publish(f) for f in files]
        return cm()


__all__ = ["GitHubPagesHost", "MediaHostError", "REPO"]

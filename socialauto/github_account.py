"""The user's OWN GitHub account (Task 07), connected on the website.

- Device flow (preferred): the page shows a short code and opens github.com/login/device; the user approves there.
  No password is ever typed into this site. The OAuth app's client id is public (device flow needs no secret).
- Fallback: a fine-grained personal access token limited to the content repo (Contents: read and write).

The token is stored only on this computer (secrets/github.json, chmod 600 / user-only ACL), never logged, never
returned to the browser (the site sees login, name, avatar and the content repo link only).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

API = "https://api.github.com"
DEVICE_CODE = "https://github.com/login/device/code"
ACCESS_TOKEN = "https://github.com/login/oauth/access_token"
SCOPE = "repo"          # OAuth apps have no narrower scope that can create a private repo and push to it


class GitHubError(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class GitHubAccount:
    def __init__(self, settings, session: requests.Session | None = None):
        self.settings = settings
        self.s = session or requests.Session()
        self.file = settings.root / "secrets" / "github.json"
        self._pending: dict[str, Any] | None = None          # the device flow in progress (device_code stays here)
        self._lock = threading.Lock()

    # --- storage ------------------------------------------------------------------------------------------------
    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        from .env_store import protect
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_name(self.file.name + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        protect(tmp)
        tmp.replace(self.file)
        protect(self.file)

    def token(self) -> str:
        return str(self._load().get("token", ""))

    def info(self) -> dict[str, Any] | None:
        d = self._load()
        if not d.get("token"):
            return None
        return {k: d.get(k) for k in ("login", "id", "name", "avatar_url", "method")}

    def disconnect(self) -> None:
        self.file.unlink(missing_ok=True)

    # --- HTTP ---------------------------------------------------------------------------------------------------
    def _api(self, method: str, path: str, token: str, **kw) -> requests.Response:
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "social-automation"}
        try:
            return self.s.request(method, API + path, headers=headers, timeout=20, **kw)
        except requests.RequestException:
            raise GitHubError("network") from None

    def _user(self, token: str) -> dict[str, Any]:
        r = self._api("GET", "/user", token)
        if r.status_code in (401, 403):
            raise GitHubError("rejected")
        if r.status_code != 200:
            raise GitHubError("network")
        return r.json()

    def _store_user(self, token: str, method: str) -> dict[str, Any]:
        u = self._user(token)
        self._save({"token": token, "method": method, "login": u.get("login", ""), "id": u.get("id", 0),
                    "name": u.get("name") or "", "avatar_url": u.get("avatar_url", ""),
                    "connected_at": int(time.time())})
        return self.info() or {}

    # --- device flow --------------------------------------------------------------------------------------------
    def start_device(self) -> dict[str, Any]:
        cid = self.settings.github.oauth_client_id
        if not cid:
            raise GitHubError("no_client_id")
        try:
            r = self.s.post(DEVICE_CODE, data={"client_id": cid, "scope": SCOPE},
                            headers={"Accept": "application/json"}, timeout=20)
            body = r.json()
        except (requests.RequestException, ValueError):
            raise GitHubError("network") from None
        if "device_code" not in body:
            raise GitHubError("rejected")
        with self._lock:
            self._pending = {"device_code": body["device_code"], "interval": int(body.get("interval", 5)),
                             "expires": time.time() + int(body.get("expires_in", 900)), "next": 0.0}
        return {"user_code": body["user_code"], "verification_uri": body.get("verification_uri",
                                                                            "https://github.com/login/device"),
                "interval": int(body.get("interval", 5)), "expires_in": int(body.get("expires_in", 900))}

    def poll_device(self) -> dict[str, Any]:
        """One check: {"state": "waiting" | "done" | "expired" | "denied" | "idle"}."""
        with self._lock:
            p = self._pending
            if not p:
                return {"state": "idle"}
            if time.time() > p["expires"]:
                self._pending = None
                return {"state": "expired"}
            if time.time() < p["next"]:
                return {"state": "waiting"}
            p["next"] = time.time() + p["interval"]
            device_code = p["device_code"]
        try:
            r = self.s.post(ACCESS_TOKEN, data={"client_id": self.settings.github.oauth_client_id,
                                                "device_code": device_code,
                                                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"},
                            headers={"Accept": "application/json"}, timeout=20)
            body = r.json()
        except (requests.RequestException, ValueError):
            return {"state": "waiting"}
        err = body.get("error")
        if err in ("authorization_pending", None) and not body.get("access_token"):
            return {"state": "waiting"}
        if err == "slow_down":
            with self._lock:
                if self._pending:
                    self._pending["interval"] += 5
            return {"state": "waiting"}
        if err == "expired_token":
            self._pending = None
            return {"state": "expired"}
        if err:
            self._pending = None
            return {"state": "denied"}
        self._pending = None
        self._store_user(body["access_token"], "device")
        if self._mode() == "new":                  # not chosen yet: the user picks «Yangi» or «Mavjud» first
            try:
                self.ensure_content_repo()
            except GitHubError:
                log.warning("content repo not created yet; will retry on the next push")
        return {"state": "done"}

    # --- personal token -----------------------------------------------------------------------------------------
    def use_token(self, token: str) -> dict[str, Any]:
        token = token.strip()
        if not token or len(token) > 400 or any(c.isspace() for c in token):
            raise GitHubError("bad_token")
        info = self._store_user(token, "token")
        if self._mode() != "new":
            return info
        try:
            self.ensure_content_repo()
        except GitHubError as exc:
            if exc.reason == "repo_missing":
                return {**info, "repo_missing": True}
            raise
        return info

    # --- content repo -------------------------------------------------------------------------------------------
    def _mode(self) -> str:
        from .content_repo import ContentRepo
        return ContentRepo(self.settings).choice()["mode"]

    def repos(self) -> list[dict[str, Any]]:
        """Task 09: the user's repos for «Mavjud repomni ulash» (his own, collaborator and organisation repos),
        newest first. Only what the website shows: names, private/public, last update, push right."""
        info = self.info()
        if not info:
            raise GitHubError("not_connected")
        out: list[dict[str, Any]] = []
        for page in range(1, 4):
            r = self._api("GET", f"/user/repos?per_page=100&page={page}&sort=pushed"
                                 "&affiliation=owner,collaborator,organization_member", self.token())
            if r.status_code in (401, 403):
                raise GitHubError("rejected")
            if r.status_code != 200:
                raise GitHubError("network")
            items = r.json() or []
            out += [_repo_view(x) for x in items]
            if len(items) < 100:
                break
        return out

    def check_repo(self, ref: str) -> dict[str, Any]:
        """One repo by "owner/name": exists for this account and he can push to it. GitHubError(reason) if not."""
        info = self.info()
        if not info:
            raise GitHubError("not_connected")
        r = self._api("GET", f"/repos/{ref}", self.token())
        if r.status_code == 404:
            raise GitHubError("repo_not_found")
        if r.status_code in (401, 403):
            raise GitHubError("rejected")
        if r.status_code != 200:
            raise GitHubError("network")
        view = _repo_view(r.json())
        if view["archived"]:
            raise GitHubError("repo_archived")
        if not view["can_push"]:
            raise GitHubError("no_push")
        return view

    def content_repo(self) -> dict[str, Any]:
        info = self.info()
        name = self.settings.github.content_repo
        if not info:
            return {"exists": False, "name": name, "url": ""}
        r = self._api("GET", f"/repos/{info['login']}/{name}", self.token())
        return {"exists": r.status_code == 200, "name": name, "url": f"https://github.com/{info['login']}/{name}",
                "private": bool(r.json().get("private")) if r.status_code == 200 else True}

    def ensure_content_repo(self) -> dict[str, Any]:
        """Create <login>/social-automation-content (private) if it does not exist."""
        state = self.content_repo()
        if state["exists"] or not self.info():
            return state
        r = self._api("POST", "/user/repos", self.token(), json={
            "name": self.settings.github.content_repo, "private": True, "auto_init": False,
            "description": "Reels made with Social Automation (video, cover, script, research, sources)"})
        if r.status_code in (201, 422):          # 422: it already exists (race) — fine
            return self.content_repo()
        if r.status_code in (403, 404):
            raise GitHubError("repo_missing")    # a fine-grained token may not create repos: the user makes it
        raise GitHubError("network")

    def public(self) -> dict[str, Any]:
        """What the website may show."""
        info = self.info()
        if not info:
            return {"connected": False, "device_flow": bool(self.settings.github.oauth_client_id),
                    "repo_name": self.settings.github.content_repo}
        mode = self._mode()
        out = {"connected": True, "login": info["login"], "name": info.get("name") or "",
               "avatar_url": info.get("avatar_url") or "", "method": info.get("method"),
               "profile_url": f"https://github.com/{info['login']}", "repo_name": self.settings.github.content_repo,
               "device_flow": bool(self.settings.github.oauth_client_id), "mode": mode}
        if mode == "existing":
            from .content_repo import ContentRepo
            ref = ContentRepo(self.settings).choice()["existing"]
            out.update(repo_name=ref, repo_url=f"https://github.com/{ref}", repo_exists=True, existing=True, choose=False)
            return out
        out["choose"] = mode == ""                 # not chosen yet: the website offers «Yangi» / «Mavjud»
        try:
            repo = self.content_repo()
            out.update(repo_exists=repo["exists"], repo_url=repo["url"])
        except GitHubError:
            out.update(repo_exists=None, repo_url=f"https://github.com/{info['login']}/{out['repo_name']}")
        return out


def _repo_view(x: dict[str, Any]) -> dict[str, Any]:
    perms = x.get("permissions") or {}
    return {"full_name": x.get("full_name", ""), "name": x.get("name", ""),
            "owner": (x.get("owner") or {}).get("login", ""), "private": bool(x.get("private")),
            "pushed_at": x.get("pushed_at") or x.get("updated_at") or "", "url": x.get("html_url", ""),
            "description": (x.get("description") or "")[:140], "archived": bool(x.get("archived")),
            "can_push": bool(perms.get("push") or perms.get("admin") or perms.get("maintain")),
            "default_branch": x.get("default_branch") or "main"}


__all__ = ["GitHubAccount", "GitHubError"]


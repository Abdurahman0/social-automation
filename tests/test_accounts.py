"""Task 07: the user's own accounts on the website — GitHub (device flow / token), Claude login, Instagram and
YouTube analytics logins. Tokens never reach the browser or the logs."""

import json
import logging
import stat
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from socialauto.github_account import GitHubAccount
from socialauto.web.accounts import Accounts
from socialauto.web.server import create_app

GH_TOKEN = "gho_" + "S3cretTok3n" * 3


class R:
    def __init__(self, status, body):
        self.status_code, self._b = status, body

    def json(self):
        return self._b


REPO_SUV = {"full_name": "eraliyev-j/the-suvyektiv-media", "name": "the-suvyektiv-media", "id": 987654,
            "owner": {"login": "eraliyev-j"}, "private": False, "pushed_at": "2026-11-10T04:44:08Z",
            "html_url": "https://github.com/eraliyev-j/the-suvyektiv-media", "default_branch": "main",
            "permissions": {"admin": True, "push": True, "pull": True}}
REPO_RO = {"full_name": "someone/read-only", "name": "read-only", "id": 5, "owner": {"login": "someone"},
           "private": True, "pushed_at": "2026-10-01T09:00:00Z", "html_url": "https://github.com/someone/read-only",
           "permissions": {"admin": False, "push": False, "pull": True}}


class FakeGitHub:
    """github.com device flow + api.github.com, enough for the account and the content repo."""

    def __init__(self, approve_after=1, repo_exists=False, create_status=201):
        self.polls, self.approve_after, self.repo_exists, self.create_status = 0, approve_after, repo_exists, create_status
        self.calls = []

    def post(self, url, data=None, headers=None, timeout=None):
        self.calls.append(("POST", url))
        if url.endswith("/login/device/code"):
            return R(200, {"device_code": "dev-secret", "user_code": "WDJB-MJHT", "verification_uri":
                           "https://github.com/login/device", "interval": 0, "expires_in": 900})
        self.polls += 1
        if self.polls <= self.approve_after:
            return R(200, {"error": "authorization_pending"})
        return R(200, {"access_token": GH_TOKEN, "token_type": "bearer", "scope": "repo"})

    def request(self, method, url, headers=None, timeout=None, json=None):
        self.calls.append((method, url))
        assert headers["Authorization"] == f"Bearer {GH_TOKEN}"
        if url.endswith("/user"):
            return R(200, {"login": "dost", "id": 42, "name": "Do'st", "avatar_url": "https://avatars.example/42"})
        if "/user/repos?" in url:
            return R(200, [REPO_SUV, REPO_RO, {**REPO_SUV, "full_name": "dost/old", "name": "old", "archived": True}])
        if url.endswith("/repos/eraliyev-j/the-suvyektiv-media"):
            return R(200, REPO_SUV)
        if url.endswith("/repos/someone/read-only"):
            return R(200, REPO_RO)
        if url.endswith("/repos/nobody/missing"):
            return R(404, {})
        if "/repos/dost/" in url:
            return R(200 if self.repo_exists else 404, {"private": True} if self.repo_exists else {})
        if url.endswith("/user/repos"):
            self.repo_exists = self.create_status == 201
            assert json["private"] is True and json["name"] == "social-automation-content"
            return R(self.create_status, {})
        raise AssertionError(url)


@pytest.fixture
def gh_settings(settings):
    return replace(settings, github=replace(settings.github, oauth_client_id="Iv1.public-id"))


def test_device_flow_connects_and_creates_the_private_content_repo(gh_settings):
    fake = FakeGitHub()
    acc = GitHubAccount(gh_settings, session=fake)
    start = acc.start_device()
    assert start["user_code"] == "WDJB-MJHT" and "device_code" not in start          # the device code stays here
    assert acc.poll_device()["state"] == "waiting"
    assert acc.poll_device()["state"] == "done"
    pub = acc.public()
    assert pub["choose"] is True and ("POST", "https://api.github.com/user/repos") not in fake.calls   # Task 09: user picks first
    from socialauto.content_repo import ContentRepo
    ContentRepo(gh_settings).choose("new")                                       # «Yangi repo yaratish»
    acc.ensure_content_repo()
    pub = acc.public()
    assert pub["login"] == "dost" and pub["repo_exists"] and pub["repo_url"].endswith("/dost/social-automation-content")
    assert pub["mode"] == "new" and not pub["choose"]
    assert GH_TOKEN not in json.dumps(pub)
    f = gh_settings.root / "secrets" / "github.json"
    assert stat.S_IMODE(f.stat().st_mode) == 0o600 and json.loads(f.read_text())["token"] == GH_TOKEN
    acc.disconnect()
    assert not f.exists() and acc.public()["connected"] is False


def test_fine_grained_token_without_repo_rights_asks_user_to_create_the_repo(gh_settings):
    from socialauto.content_repo import ContentRepo
    ContentRepo(gh_settings).choose("new")
    acc = GitHubAccount(gh_settings, session=FakeGitHub(create_status=403))
    info = acc.use_token(GH_TOKEN)
    assert info["repo_missing"] is True and acc.info()["method"] == "token"


def test_no_client_id_means_token_only(settings):
    from socialauto.github_account import GitHubError
    with pytest.raises(GitHubError):
        GitHubAccount(replace(settings, github=replace(settings.github, oauth_client_id="")), session=FakeGitHub()).start_device()


def test_content_push_uses_the_users_account_url(gh_settings):
    from socialauto.content_repo import ContentRepo
    acc = GitHubAccount(gh_settings, session=FakeGitHub(repo_exists=True))
    acc.use_token(GH_TOKEN)
    assert ContentRepo(gh_settings, acc).remote_url() == "https://github.com/dost/social-automation-content.git"


@pytest.fixture
def web(app, gh_settings, clock):
    fake = FakeGitHub()
    gh = GitHubAccount(gh_settings, session=fake)
    client = TestClient(create_app(gh_settings, app.db, None, clock, github=gh))
    return client, gh


def test_accounts_api_needs_login_and_never_returns_tokens(web, caplog):
    client, gh = web
    assert client.get("/api/accounts").status_code == 401
    client.post("/api/login", json={"password": "secret-pass"})
    caplog.set_level(logging.DEBUG)
    assert client.post("/api/accounts/github/device").json()["user_code"] == "WDJB-MJHT"
    client.post("/api/accounts/github/poll")
    res = client.post("/api/accounts/github/poll").json()
    assert res["state"] == "done" and res["account"]["login"] == "dost"
    page = client.get("/api/accounts").text + client.get("/api/repo").text + client.get("/").text
    assert GH_TOKEN not in page and "dev-secret" not in page
    assert GH_TOKEN not in caplog.text and "dev-secret" not in caplog.text


def test_instagram_callback_needs_the_single_use_state(app, settings, clock, monkeypatch):
    s = replace(settings, meta_app_id="123", meta_app_secret="shh")
    acc = Accounts(s)
    client = TestClient(create_app(s, app.db, None, clock, accounts=acc))
    r = client.get("/api/accounts/instagram/callback?code=x&state=forged", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("r=ig_expired")
    client.post("/api/login", json={"password": "secret-pass"})
    url = client.post("/api/accounts/instagram/start").json()["url"]
    assert "facebook.com" in url and "instagram_content_publish" not in url and "client_id=123" in url
    state = url.split("state=")[1].split("&")[0]
    monkeypatch.setattr(acc, "instagram_token", lambda tok: {"username": "suv_uz", "page_name": "Suv"})

    class S:
        def get(self, *a, **k):
            return R(200, {"access_token": "short"})
    acc.s = S()
    r = client.get(f"/api/accounts/instagram/callback?code=c&state={state}", follow_redirects=False)
    assert r.headers["location"].endswith("r=ig_ok")
    r = client.get(f"/api/accounts/instagram/callback?code=c&state={state}", follow_redirects=False)
    assert r.headers["location"].endswith("r=ig_expired")                      # single use


def test_youtube_client_file_is_validated_and_private(app, settings, clock):
    acc = Accounts(settings)
    client = TestClient(create_app(settings, app.db, None, clock, accounts=acc))
    client.post("/api/login", json={"password": "secret-pass"})
    assert client.post("/api/accounts/youtube/client", json={"text": "{}"}).json()["reason"] == "bad_client"
    good = {"installed": {"client_id": "1.apps.googleusercontent.com", "client_secret": "GOCSPX-x",
                          "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token",
                          "redirect_uris": ["http://localhost"]}}
    assert client.post("/api/accounts/youtube/client", json={"text": json.dumps(good)}).json()["kind"] == "desktop"
    assert stat.S_IMODE(acc.yt_secret().stat().st_mode) == 0o600
    url = client.post("/api/accounts/youtube/start").json()["url"]
    assert "accounts.google.com" in url and "youtube.readonly" in url and "youtube.upload" not in url
    view = client.get("/api/accounts").json()["youtube"]
    assert view["client"] and not view["connected"] and "GOCSPX" not in json.dumps(view)


def test_net_status_is_open(app, settings, clock, monkeypatch):
    import socialauto.web.server as srv
    client = TestClient(create_app(settings, app.db, None, clock))
    monkeypatch.setattr("socialauto.netcheck.online", lambda *a, **k: False)
    assert set(client.get("/api/net").json()) == {"online"}


# --- Task 09: «Mavjud repomni ulash» ---------------------------------------------------------------------------
@pytest.fixture
def connected(web, monkeypatch):
    from socialauto.content_repo import ContentRepo
    started = []
    monkeypatch.setattr(ContentRepo, "prepare_async", lambda self: started.append(self.remote_url()))   # no real clone
    client, gh = web
    client.post("/api/login", json={"password": "secret-pass"})
    client.post("/api/accounts/github/device")
    client.post("/api/accounts/github/poll")
    assert client.post("/api/accounts/github/poll").json()["state"] == "done"
    return client, gh, started


def test_repo_list_shows_names_badges_tashkent_time_and_push_rights(connected):
    client, _, _ = connected
    body = client.get("/api/accounts/github/repos")
    data = body.json()
    names = [r["full_name"] for r in data["repos"]]
    assert names == ["eraliyev-j/the-suvyektiv-media", "someone/read-only"]                # archived one hidden
    suv, ro = data["repos"]
    assert suv["can_push"] and not suv["private"] and suv["updated"] == "10-noyabr, 09:44"   # 04:44 UTC -> Tashkent
    assert not ro["can_push"] and ro["reason"] == "no_push" and ro["private"]
    assert "987654" not in body.text and '"id"' not in body.text and GH_TOKEN not in body.text   # no internal ids


def test_choosing_his_existing_repo(connected, gh_settings):
    client, gh, started = connected
    bad = client.post("/api/accounts/github/choice", json={"mode": "existing", "repo": "salom dunyo"})
    assert bad.status_code == 400 and bad.json()["reason"] == "bad_link"
    ro = client.post("/api/accounts/github/choice", json={"mode": "existing", "repo": "someone/read-only"})
    assert ro.status_code == 400 and ro.json()["reason"] == "no_push"
    code = client.post("/api/accounts/github/choice", json={"mode": "existing",
                                                            "repo": "https://github.com/Abdurahman0/social-automation"})
    assert code.status_code == 400 and code.json()["reason"] == "code_repo"
    missing = client.post("/api/accounts/github/choice", json={"mode": "existing", "repo": "nobody/missing"})
    assert missing.status_code == 400 and missing.json()["reason"] == "repo_not_found"
    ok = client.post("/api/accounts/github/choice", json={"mode": "existing",
                                                          "repo": "https://github.com/eraliyev-j/the-suvyektiv-media"})
    assert ok.status_code == 200
    acc = ok.json()["account"]
    assert acc["mode"] == "existing" and acc["repo_name"] == "eraliyev-j/the-suvyektiv-media" and not acc["choose"]
    assert started == ["https://github.com/eraliyev-j/the-suvyektiv-media.git"]
    local = (gh_settings.root / "config.local.toml").read_text()
    assert 'content_mode = "existing"' in local and "the-suvyektiv-media" in local
    assert ("POST", "https://api.github.com/user/repos") not in gh.s.calls                     # no extra repo created
    # switching to a new repo later is possible
    assert client.post("/api/accounts/github/choice", json={"mode": "new"}).json()["account"]["mode"] == "new"
    assert ("POST", "https://api.github.com/user/repos") in gh.s.calls

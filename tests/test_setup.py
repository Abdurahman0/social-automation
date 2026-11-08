"""Setup ("Sozlash") page: first-run redirect, localhost-only before a password, saving and masking, checks."""

import stat
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from socialauto import env_store
from socialauto.web.server import create_app
from socialauto.web.setup import SetupChecks

TOKEN = "123456789:AAH" + "x" * 32


class FakeChecks(SetupChecks):
    def __init__(self, settings):
        super().__init__(settings)
        self.sent = []

    def telegram(self, token):
        self.sent.append(token)
        return {"ok": token == TOKEN, "name": "Suv bot", "username": "suv_bot"} if token == TOKEN else {"ok": False, "reason": "rejected"}

    def claude(self):
        return {"installed": True, "logged_in": True, "plan": "Pro"}

    def model(self):
        return {"ready": True, "size_mb": 780}


@pytest.fixture
def fresh(app, settings, clock):
    """A first start: no password anywhere."""
    s = replace(settings, dashboard_password="")
    checks = FakeChecks(s)
    app_ = create_app(s, app.db, None, clock, checks=checks)
    local = TestClient(app_, client=("127.0.0.1", 50000))
    remote = TestClient(app_, client=("203.0.113.9", 50000))
    return s, local, remote, checks


def test_first_run_redirects_to_setup(fresh):
    _, local, _, _ = fresh
    r = local.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/setup"
    assert local.get("/api/overview").json() == {"ok": False, "reason": "setup"}
    assert local.get("/setup").status_code == 200
    assert local.get("/api/session").json() == {"authenticated": False, "configured": False}


def test_setup_only_from_this_computer_before_a_password(fresh):
    _, local, remote, _ = fresh
    assert remote.get("/api/setup/state").status_code == 403
    assert remote.post("/api/setup/password", json={"password": "hacker-pass"}).status_code == 403
    relayed = local.get("/api/setup/state", headers={"X-Forwarded-For": "203.0.113.9"})
    assert relayed.status_code == 403                                       # a tunnel/proxy is not "this computer"
    assert local.get("/api/setup/state").status_code == 200


def test_password_then_values_saved_masked_and_private(fresh):
    s, local, remote, _ = fresh
    assert local.post("/api/setup/save", json={"values": {"BUFFER_API_KEY": "k"}}).status_code == 400  # password first
    assert local.post("/api/setup/password", json={"password": "short"}).json()["reason"] == "too_short"
    assert local.post("/api/setup/password", json={"password": "uzun-parol-1"}).json() == {"ok": True}
    # now the password protects everything, also from this computer without the cookie
    assert remote.get("/api/setup/state").status_code == 401
    r = local.post("/api/setup/save", json={"values": {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_ALLOWED_USER_IDS": "12345, 67890",
                                                      "BUFFER_API_KEY": "buf-secret-key-123", "DASHBOARD_PASSWORD": "ignored"}})  # gitleaks:allow (fake test value)
    assert r.json()["saved"] == ["BUFFER_API_KEY", "TELEGRAM_ALLOWED_USER_IDS", "TELEGRAM_BOT_TOKEN"]
    env = s.root / ".env"
    values = env_store.read(env)
    assert values["TELEGRAM_BOT_TOKEN"] == TOKEN and values["DASHBOARD_PASSWORD"] == "uzun-parol-1"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    state = local.get("/api/setup/state").json()
    text = str(state)
    assert TOKEN not in text and "buf-secret-key-123" not in text and "uzun-parol-1" not in text
    assert state["values"]["BUFFER_API_KEY"] == {"set": True, "shown": "bu••••••23"}
    assert state["values"]["TELEGRAM_ALLOWED_USER_IDS"]["shown"] == "12345, 67890"
    assert state["values"]["PEXELS_API_KEY"] == {"set": False, "shown": ""}


def test_bad_values_are_refused(fresh):
    _, local, _, _ = fresh
    local.post("/api/setup/password", json={"password": "uzun-parol-1"})
    assert local.post("/api/setup/save", json={"values": {"TELEGRAM_BOT_TOKEN": "nonsense"}}).json()["reason"] == "bad_token"
    assert local.post("/api/setup/save", json={"values": {"TELEGRAM_ALLOWED_USER_IDS": "me"}}).json()["reason"] == "bad_ids"
    assert local.post("/api/setup/save", json={"values": {"BUFFER_API_KEY": "a\nEVIL=1"}}).status_code == 200
    assert "EVIL" not in env_store.read(fresh[0].root / ".env")                 # a value can never add a line


def test_telegram_check_uses_saved_token_and_never_echoes_it(fresh):
    _, local, _, checks = fresh
    local.post("/api/setup/password", json={"password": "uzun-parol-1"})
    local.post("/api/setup/save", json={"values": {"TELEGRAM_BOT_TOKEN": TOKEN}})
    r = local.post("/api/setup/check/telegram", json={})
    assert r.json() == {"ok": True, "name": "Suv bot", "username": "suv_bot"} and checks.sent == [TOKEN]
    assert local.post("/api/setup/check/telegram", json={"value": "1:bad"}).json()["ok"] is False


def test_validate_and_mask_units():
    assert SetupChecks.validate("TELEGRAM_BOT_TOKEN", TOKEN) is None
    assert SetupChecks.validate("META_APP_ID", "12a") == "bad_app_id"
    assert env_store.mask("abcdefghij") == "ab••••••ij" and env_store.mask("abc") == "••••••"
    assert SetupChecks(None).telegram("bad")["reason"] == "bad_token"     # never leaves the computer when malformed

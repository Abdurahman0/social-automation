"""Dashboard API: login/session security, every endpoint, connect state, no internal ids or secrets leak."""

import json
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from test_analytics import FakeIG, FakeYT

from socialauto.analytics.collector import Collector
from socialauto.db import KV
from socialauto.web.server import COOKIE, check_token, create_app, make_token

UTC = timezone.utc


@pytest.fixture
def web(app, settings, clock):
    yt, ig = FakeYT(), FakeIG()
    collector = Collector(settings, app.db, KV(app.db), lambda: yt, lambda: ig, clock)
    client = TestClient(create_app(settings, app.db, collector, clock))
    return client, collector


def login(client, password="secret-pass"):
    return client.post("/api/login", json={"password": password})


def connect(settings):
    for f in (settings.youtube.token_file, settings.instagram.token_file):
        p = settings.resolve(f)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")


def test_api_requires_login(web):
    client, _ = web
    for path in ("/api/overview", "/api/series", "/api/videos", "/api/insights", "/api/pipeline", "/api/status"):
        r = client.get(path)
        assert r.status_code == 401 and r.json() == {"ok": False, "reason": "login"}
    assert client.post("/api/refresh").status_code == 401
    assert client.get("/api/session").json() == {"authenticated": False, "configured": True}
    assert client.get("/").status_code == 200                 # the page itself has no data


def test_wrong_password_and_rate_limit(web):
    client, _ = web
    assert login(client, "nope").status_code == 401
    for _ in range(8):
        login(client, "nope")
    assert login(client, "secret-pass").status_code == 429     # slowed down after repeated failures


def test_login_cookie_is_httponly_and_strict(web):
    client, _ = web
    r = login(client)
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/session").json()["authenticated"] is True
    client.post("/api/logout")
    assert client.get("/api/overview").status_code == 401


def test_session_token_expiry_and_password_change():
    secret = b"k" * 32
    t = make_token(secret, "pw", now=1000)
    assert check_token(secret, "pw", t, now=2000)
    assert not check_token(secret, "pw", t, now=1000 + 31 * 86400)       # expired
    assert not check_token(secret, "other", t, now=2000)                  # password changed: logged out
    assert not check_token(secret, "pw", t[:-1] + ("0" if t[-1] != "0" else "1"), now=2000)
    assert not check_token(secret, "pw", None)


def test_connect_state_has_no_numbers(web):
    client, _ = web
    login(client)
    ov = client.get("/api/overview").json()
    assert ov["combined"] is None
    assert ov["status"]["platforms"]["youtube"] == {"connected": False, "source": None, "updated_minutes": None, "problem": None}
    assert ov["status"]["dry_run"] is True
    assert client.get("/api/videos").json() == {"videos": []}


def test_full_data_flow(web, settings, app, clock):
    client, collector = web
    connect(settings)
    collector.refresh()
    login(client)
    clock.advance(minutes=12)
    ov = client.get("/api/overview?days=30").json()
    assert ov["combined"]["followers"] == 1500
    assert ov["status"]["platforms"]["instagram"]["updated_minutes"] == 12
    sr = client.get("/api/series?metric=views&start=2026-11-01&end=2026-11-09").json()
    assert len(sr["days"]) == 9 and sr["youtube"][7] == 200
    assert client.get("/api/series?metric=bogus").status_code == 400
    assert client.get("/api/series?start=2026-11-09&end=2026-11-01").status_code == 400
    vids = client.get("/api/videos").json()["videos"]
    assert {v["title"] for v in vids} >= {"Octopus hearts", "Honey never spoils"}
    key = vids[0]["key"]
    assert client.get(f"/api/videos/{key}").status_code == 200
    assert client.get("/api/videos/doesnotexist").status_code == 404
    ins = client.get("/api/insights").json()
    assert ins["best_times"]["best_hour"] is not None and ins["comparison"]["youtube"]
    # permalinks are only used as link targets (never shown as text); everything else must be id-free
    text = re.sub(r'"permalink": "[^"]*"', "", json.dumps([ov, vids, ins]))
    for leak in ("yt1", "ig1", "UC1", "token", "secrets/", "/home/"):   # law 6: no platform ids, paths, secrets
        assert leak not in text


def test_pipeline_shows_the_six_stages_with_owner_and_bot(web, app):
    client, _ = web
    login(client)
    vid = app.store.create_video("voice_waiting", slot_at=datetime(2026, 11, 9, 14, tzinfo=UTC))
    app.store.add_script(vid, {"title": "Toshkentda suv tanqisligi", "topic": "suv"})
    cols = client.get("/api/pipeline").json()["columns"]
    assert [c["label"] for c in cols] == ["Tadqiqot va mavzu", "Ssenariy va ovoz", "B-roll va dizayn", "Ovoz va montaj",
                                          "Tasdiq va Buffer", "Efirdan keyin"]
    item = cols[1]["items"][0]
    assert item["title"] == "Toshkentda suv tanqisligi" and item["status"] == "Ovoz kutilmoqda" and item["who"] == "Siz"
    assert item["slot"] == "9-noyabr, 19:00"
    assert not re.search(r'"id"', json.dumps(cols))
    text = json.dumps(cols, ensure_ascii=False)
    assert "joylandi" not in text.lower() and "joylanadi" not in text.lower()


def test_refresh_endpoint_is_rate_limited(web, settings):
    client, collector = web
    connect(settings)
    login(client)
    assert client.post("/api/refresh").json()["skipped"] is False
    assert client.post("/api/refresh").json()["skipped"] is True


def test_security_headers(web):
    client, _ = web
    r = client.get("/")
    assert r.headers["x-frame-options"] == "DENY" and r.headers["x-content-type-options"] == "nosniff"
    assert COOKIE == "sa_session"
    assert timedelta  # noqa

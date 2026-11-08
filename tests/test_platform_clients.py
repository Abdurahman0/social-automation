"""Read-only platform clients against fake HTTP: error classification, expired auth, token auto-refresh, scopes."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from socialauto.platforms.instagram import (PERMISSIONS, GraphInstagramClient, InstagramAuthError, InstagramRetryable,
                                            classify, connect, load_tokens, save_tokens)
from socialauto.platforms.youtube import SCOPES, YouTubeAuthError, YouTubeStats

UTC = timezone.utc
NOW = datetime(2026, 11, 9, 6, tzinfo=UTC)


class Resp:
    def __init__(self, status, payload):
        self.status_code, self._p, self.content = status, payload, json.dumps(payload).encode()

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, routes):
        self.routes = routes          # [(method, url-substring, Resp)]
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(("GET", url, params))
        for m, frag, resp in self.routes:
            if m == "GET" and frag in url:
                return resp
        return Resp(404, {"error": {"code": 100, "message": "unknown"}})


def tokens(tmp_path, days_left=50):
    path = tmp_path / "instagram.json"
    save_tokens(path, {"user_token": "EAAuser", "user_token_expires_at": (NOW + timedelta(days=days_left)).isoformat(),
                       "page_id": "P1", "page_token": "EAApage", "ig_user_id": "IG1", "username": "facts"})
    return path


def test_token_file_is_private(tmp_path):
    path = tokens(tmp_path)
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_error_classification():
    assert isinstance(classify(400, {"error": {"code": 190, "error_subcode": 463}}), InstagramAuthError)
    assert isinstance(classify(400, {"error": {"code": 4}}), InstagramRetryable)
    assert isinstance(classify(500, {}), InstagramRetryable)


def test_expired_token_raises_auth_error(tmp_path):
    s = FakeSession([("GET", "IG1", Resp(400, {"error": {"code": 190, "message": "expired"}}))])
    ig = GraphInstagramClient(tokens(tmp_path), "v27.0", session=s, clock=lambda: NOW)
    with pytest.raises(InstagramAuthError):
        ig.account()


def test_not_connected_is_auth_error(tmp_path):
    ig = GraphInstagramClient(tmp_path / "none.json", "v27.0")
    assert not ig.connected
    with pytest.raises(InstagramAuthError):
        ig.ig_user_id


def test_long_lived_token_auto_refresh(tmp_path):
    path = tokens(tmp_path, days_left=5)
    s = FakeSession([("GET", "oauth/access_token", Resp(200, {"access_token": "EAAnew", "expires_in": 5184000})),
                     ("GET", "me/accounts", Resp(200, {"data": [{"id": "P1", "access_token": "EAApage2"}]}))])
    ig = GraphInstagramClient(path, "v27.0", "app", "secret", session=s, clock=lambda: NOW)
    assert ig.refresh_if_needed() is True
    data = load_tokens(path)
    assert data["user_token"] == "EAAnew" and data["page_token"] == "EAApage2"
    assert datetime.fromisoformat(data["user_token_expires_at"]) > NOW + timedelta(days=59)
    assert ig.refresh_if_needed() is False                     # fresh now: no call
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_statistics_calls_are_get_only(tmp_path):
    s = FakeSession([("GET", "IG1/media", Resp(200, {"data": [{"id": "M1"}]})),
                     ("GET", "IG1", Resp(200, {"followers_count": 10, "media_count": 1}))])
    ig = GraphInstagramClient(tokens(tmp_path), "v27.0", session=s, clock=lambda: NOW)
    assert ig.recent_media()[0]["id"] == "M1" and ig.account()["followers_count"] == 10
    assert all(c[0] == "GET" and "graph.facebook.com/v27.0/" in c[1] for c in s.calls)
    assert all(c[2]["access_token"] == "EAApage" for c in s.calls)        # the page token is used
    assert not hasattr(ig, "post") and not hasattr(ig, "publish")         # law 15: nothing that can post


def test_only_read_permissions_and_scopes():
    assert "instagram_content_publish" not in PERMISSIONS
    assert all(s.endswith(".readonly") for s in SCOPES)


def test_connect_finds_linked_instagram(tmp_path):
    s = FakeSession([("GET", "oauth/access_token", Resp(200, {"access_token": "EAAlong", "expires_in": 5184000})),
                     ("GET", "me/accounts", Resp(200, {"data": [
                         {"id": "P0", "name": "No IG", "access_token": "x"},
                         {"id": "P1", "name": "Facts Page", "access_token": "EAApage",
                          "instagram_business_account": {"id": "IG1", "username": "facts"}}]}))])
    info = connect("short", "app", "secret", "v27.0", tmp_path / "ig.json", session=s)
    assert info["username"] == "facts" and load_tokens(tmp_path / "ig.json")["ig_user_id"] == "IG1"


def test_youtube_missing_token_is_auth_error(tmp_path):
    yt = YouTubeStats(tmp_path / "secret.json", tmp_path / "token.json")
    with pytest.raises(YouTubeAuthError):
        yt.credentials()


def test_youtube_http_errors():
    from googleapiclient.errors import HttpError

    from socialauto.platforms.youtube import YouTubeQuotaError, YouTubeRetryable, classify_http_error

    class R(dict):
        def __init__(self, status):
            super().__init__()
            self.status, self.reason = status, ""

    def err(status, reason):
        return HttpError(R(status), json.dumps({"error": {"errors": [{"reason": reason}], "message": "m"}}).encode())
    assert isinstance(classify_http_error(err(401, "authError")), YouTubeAuthError)
    assert isinstance(classify_http_error(err(403, "quotaExceeded")), YouTubeQuotaError)
    assert isinstance(classify_http_error(err(503, "backendError")), YouTubeRetryable)

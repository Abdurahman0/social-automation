"""The bot service waits for the token, restarts when .env changes, and alerts once about Claude."""

import threading
from dataclasses import replace

from socialauto import runner


def test_waits_for_the_token_instead_of_exiting(settings):
    empty = replace(settings, telegram_token="", allowed_user_ids=frozenset())
    answers = [empty, empty, settings]
    got = runner.wait_for_token(lambda: answers.pop(0), stop=threading.Event(), every=0)
    assert got is settings and answers == []
    stop = threading.Event()
    stop.set()
    assert runner.wait_for_token(lambda: empty, stop=stop, every=0) is None


def test_env_change_triggers_one_restart(tmp_path):
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=\n")
    calls = []
    w = runner.EnvWatcher(env, lambda: calls.append(1))
    assert w.check() is False
    env.write_text("TELEGRAM_BOT_TOKEN=123:abc\n")
    assert w.check() is True and w.check() is True and calls == [1]


def test_claude_missing_alerts_once(app, monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda b: None)
    assert runner.claude_alert(app) is True
    assert runner.claude_alert(app) is False
    alerts = [i for i in app.outbox.pending(50) if i.kind == "owner_action"]
    assert len(alerts) == 1 and "o'rnatilmagan" in alerts[0].payload["text"]


def test_claude_logged_out_alerts_again_only_after_it_worked(app, monkeypatch):
    from socialauto import claude_client
    status = {"loggedIn": False}
    monkeypatch.setattr(runner.shutil, "which", lambda b: "/x/claude")
    monkeypatch.setattr(claude_client.ClaudeClient, "auth_status", lambda self: dict(status))
    assert runner.claude_alert(app) is True and runner.claude_alert(app) is False
    status["loggedIn"] = True
    assert runner.claude_alert(app) is False
    status["loggedIn"] = False
    assert runner.claude_alert(app) is True
    assert sum(i.kind == "owner_action" for i in app.outbox.pending(50)) == 2


def test_waits_quietly_for_internet_then_continues(monkeypatch):
    from socialauto import netcheck
    answers = [False, False, True]
    monkeypatch.setattr(netcheck, "online", lambda max_age=0: answers.pop(0))
    stop = threading.Event()
    assert netcheck.wait_until_online(stop=stop, every=0) is True and answers == []
    monkeypatch.setattr(netcheck, "online", lambda max_age=0: False)
    stop.set()
    assert netcheck.wait_until_online(stop=stop, every=0) is False


def test_update_request_restarts_the_bot(tmp_path):
    env, req = tmp_path / ".env", tmp_path / "data" / "restart_request"
    env.write_text("A=1\n")
    calls = []
    w = runner.EnvWatcher(env, lambda: calls.append(1), also=(req,))
    req.parent.mkdir()
    req.write_text("1")
    assert w.check() is True and calls == [1]

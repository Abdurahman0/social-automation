"""Task 07: updates from the owner's code repo are fetch + fast-forward only and never touch the user's data."""

import subprocess
from pathlib import Path

import pytest

from socialauto.updater import Updater


def run(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True).stdout


def commit(repo: Path, name: str, text: str, msg: str) -> None:
    (repo / name).write_text(text)
    run(repo, "add", name)
    run(repo, "commit", "-qm", msg)


@pytest.fixture
def world(tmp_path):
    """The owner's repo (bare, 'GitHub'), the owner's working copy, and a friend's clone with his own data."""
    upstream = tmp_path / "upstream.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(upstream)], check=True)
    owner = tmp_path / "owner"
    subprocess.run(["git", "clone", "-q", str(upstream), str(owner)], check=True)
    for k, v in (("user.email", "o@e"), ("user.name", "O")):
        run(owner, "config", k, v)
    (owner / ".gitignore").write_text(".env\n/data/\n/secrets/\n/config.local.toml\n")
    run(owner, "add", ".gitignore")
    commit(owner, "app.py", "v1", "v1")
    run(owner, "push", "-q", "origin", "main")
    friend = tmp_path / "friend"
    subprocess.run(["git", "clone", "-q", str(upstream), str(friend)], check=True)
    (friend / ".env").write_text("TELEGRAM_BOT_TOKEN=friend\n")
    (friend / "data" / "content-repo").mkdir(parents=True)
    (friend / "data" / "content-repo" / "reel.mp4").write_bytes(b"his reel")
    (friend / "config.local.toml").write_text("dry_run = false\n")
    return upstream, owner, friend


def snapshot(friend: Path) -> dict:
    return {p: (friend / p).read_bytes() for p in (".env", "data/content-repo/reel.mp4", "config.local.toml")}


def test_update_is_fast_forward_and_keeps_user_data(world):
    upstream, owner, friend = world
    before = snapshot(friend)
    upstream_refs = run(owner, "ls-remote", str(upstream))
    up = Updater(friend, min_fetch_seconds=0)
    assert up.status()["available"] is False
    commit(owner, "app.py", "v2", "Yangi imkoniyat")
    run(owner, "push", "-q", "origin", "main")
    st = up.status()
    assert st["available"] and st["can_update"] and st["commits"][0]["title"] == "Yangi imkoniyat"
    res = up.apply()
    assert res["ok"] and (friend / "app.py").read_text() == "v2"
    assert snapshot(friend) == before                                      # his .env, content and settings untouched
    assert (friend / "data" / "restart_request").exists()                  # the bot restarts with the new code
    assert run(owner, "ls-remote", str(upstream)) != upstream_refs         # (owner pushed v2)
    assert run(friend, "ls-remote", str(upstream)) == run(owner, "ls-remote", str(upstream))   # friend wrote nothing


def test_local_commits_block_the_update_without_changing_anything(world):
    upstream, owner, friend = world
    for k, v in (("user.email", "f@e"), ("user.name", "F")):
        run(friend, "config", k, v)
    commit(friend, "mine.txt", "x", "local")
    commit(owner, "app.py", "v2", "v2")
    run(owner, "push", "-q", "origin", "main")
    head = run(friend, "rev-parse", "HEAD")
    up = Updater(friend, min_fetch_seconds=0)
    assert up.status()["reason"] == "diverged"
    assert up.apply() == {"ok": False, "reason": "diverged"} and run(friend, "rev-parse", "HEAD") == head


def test_edited_tracked_files_block_the_update(world):
    upstream, owner, friend = world
    (friend / "app.py").write_text("edited by hand")
    commit(owner, "app.py", "v2", "v2")
    run(owner, "push", "-q", "origin", "main")
    up = Updater(friend, min_fetch_seconds=0)
    assert up.apply()["reason"] == "local_changes" and (friend / "app.py").read_text() == "edited by hand"


def test_updater_cannot_push_reset_or_merge_non_ff(tmp_path):
    up = Updater(tmp_path)
    for bad in (("push", "origin"), ("reset", "--hard"), ("merge", "origin/main"), ("stash",)):
        with pytest.raises(ValueError):
            up.git(*bad)

"""Task 07: content goes to the user's OWN content repo; the upstream code repo is never written."""

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from socialauto.content_repo import ContentPushRefused, ContentRepo, canonical


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def bare(path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(path)], check=True)
    return path


def heads(repo: Path) -> str:
    return subprocess.run(["git", "--git-dir", str(repo), "for-each-ref"], capture_output=True, text=True).stdout


def files(tmp_path):
    v, c = tmp_path / "v.mp4", tmp_path / "c.jpg"
    v.write_bytes(b"video")
    c.write_bytes(b"cover")
    return {"2026-11-10-suv.mp4": v, "2026-11-10-suv_cover.jpg": c}


@pytest.mark.parametrize("url", ["git@github.com:Abdurahman0/social-automation.git",
                                 "https://github.com/Abdurahman0/social-automation",
                                 "https://x-access-token:t@github.com/abdurahman0/Social-Automation.git/",
                                 "ssh://git@github.com/Abdurahman0/social-automation"])
def test_push_to_the_upstream_code_repo_is_refused(settings, url):
    with pytest.raises(ContentPushRefused):
        ContentRepo(settings).guard(url)


def test_push_to_any_remote_of_the_code_folder_is_refused(settings, tmp_path):
    upstream = bare(tmp_path / "upstream.git")
    git(settings.root, "remote", "add", "origin", str(upstream))
    repo = ContentRepo(replace(settings, github=replace(settings.github, content_remote=str(upstream))))
    with pytest.raises(ContentPushRefused):
        repo.guard(str(upstream))
    with pytest.raises(ContentPushRefused):
        repo.guard(str(settings.root))
    with pytest.raises(ContentPushRefused):               # the whole publish refuses, nothing reaches upstream
        repo.publish("2026-11-10-suv", files(tmp_path), "Suv")
    assert heads(upstream) == ""


def test_content_lands_in_the_users_own_repo_only(settings, tmp_path):
    upstream = bare(tmp_path / "upstream.git")
    git(settings.root, "remote", "add", "origin", str(upstream))
    mine = bare(tmp_path / "my-content.git")
    (settings.root / ".gitignore").write_text((Path(__file__).resolve().parent.parent / ".gitignore").read_text())
    s = replace(settings, github=replace(settings.github, content_remote=str(mine)))
    repo = ContentRepo(s)
    res = repo.publish("2026-11-10-suv", files(tmp_path), "Suv")
    assert res.committed and res.pushed and res.folder == "reels/2026-11-10-suv"
    pushed = subprocess.run(["git", "--git-dir", str(mine), "ls-tree", "-r", "--name-only", "main"],
                            capture_output=True, text=True).stdout.split()
    assert "reels/2026-11-10-suv/2026-11-10-suv_cover.jpg" in pushed
    assert heads(upstream) == ""                                         # the code repo was never written
    assert not (settings.root / "reels").exists()
    assert "data/" not in git(settings.root, "status", "--porcelain")   # the content repo is ignored by the code repo
    assert repo.status()["unpushed"] == 0 and repo.status()["reels"][0]["title"] == "Suv"


def test_without_github_content_stays_local(settings, tmp_path):
    res = ContentRepo(settings).publish("2026-11-10-suv", files(tmp_path), "Suv")
    assert res.committed and not res.pushed and "GitHub ulanmagan" in res.note


def test_old_reels_folder_is_moved_into_the_content_repo(settings, tmp_path):
    old = settings.root / "reels" / "2026-11-01-eski"
    old.mkdir(parents=True)
    (old / "a.mp4").write_bytes(b"x")
    repo = ContentRepo(settings)
    assert repo.adopt_old_reels() == ["2026-11-01-eski"]
    assert (repo.reels / "2026-11-01-eski" / "a.mp4").exists() and not (settings.root / "reels").exists()


def test_canonical_forms():
    assert canonical("git@github.com:A/b.git") == canonical("https://github.com/a/B") == "github.com/a/b"


def test_no_code_path_pushes_to_origin():
    """Nothing in the app pushes the code repo: the only `push` is ContentRepo.push (guarded)."""
    root = Path(__file__).resolve().parent.parent / "socialauto"
    import re
    git_push = re.compile(r'(git|_netgit|run)\(.*"push"|\["git",.*"push"')       # a git command line with "push"
    hits = sorted({str(p.relative_to(root)) for p in root.rglob("*.py")
                   for line in p.read_text(encoding="utf-8").splitlines() if git_push.search(line)})
    assert hits == ["content_repo.py"]

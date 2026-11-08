"""Task 03: Skills ("Ko'nikmalar") and GitHub sections — parsing, friendly data, read-only git, no secrets, auth."""

import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from socialauto.web import skills as skills_mod
from socialauto.web.repo import Git, category, group_files, is_secret, repo_name, status
from socialauto.web.server import create_app


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def claude_home(tmp_path):
    home = tmp_path / ".claude"
    write(home / "skills" / "caveman" / "SKILL.md",
          "---\nname: caveman\ndescription: >\n  Ultra-compressed communication mode. Cuts tokens.\n  Use when asked.\n---\nBODY SECRET TEXT\n")
    uuid = "ed503613-91a3-4fbc-8f07-022f5741d84d_0c2a1b59"
    for copy in ("a" + uuid, "b" + uuid):           # the same skill synced twice: shown once
        write(home / "skills" / "synced" / copy / "google-workspace" / "SKILL.md",
              '---\nname: google-workspace\ndescription: "Edit Google Docs. Also Sheets."\n---\n')
    write(home / "skills" / "broken" / "SKILL.md", "no frontmatter at all")
    write(home / "skills" / "half" / "SKILL.md", "---\nname: half\n---\n")              # no description: skipped
    plugin = tmp_path / "plugins-cache" / "caveman" / "3.2.0"
    write(plugin / "skills" / "caveman-commit" / "SKILL.md",
          "---\nname: caveman-commit\ndescription: Write a Conventional Commits message. Short.\n---\n")
    write(plugin / "commands" / "caveman-init.md", "---\ndescription: Drop the caveman rule into the repo\n---\nbody")
    write(plugin / "commands" / "nodesc.md", "just text")
    write(home / "plugins" / "installed_plugins.json", json.dumps(
        {"version": 2, "plugins": {"caveman@caveman": [{"scope": "user", "installPath": str(plugin)}]}}))
    return home


@pytest.fixture
def project(tmp_path):
    proj = tmp_path / "proj"
    write(proj / ".claude" / "skills" / "deploy-pdf" / "SKILL.md",
          "---\nname: deploy-pdf\ndescription: Builds the PDF report for the API team.\n---\n")
    return proj


def test_pretty_names():
    assert skills_mod.pretty_name("caveman-commit") == "Caveman commit"
    assert skills_mod.pretty_name("google_workspace") == "Google workspace"
    assert skills_mod.pretty_name("built-in-browser") == "Built-in browser"
    assert skills_mod.pretty_name("deploy-pdf") == "Deploy PDF"
    assert skills_mod.first_sentence("Edit Google Docs. Also Sheets.") == "Edit Google Docs."


def test_scan_personal_project_plugin(claude_home, project):
    data = skills_mod.scan(claude_home, project)
    by = {s["slug"]: s for s in data["skills"]}
    assert set(by) == {"caveman", "google-workspace", "deploy-pdf", "caveman-commit", "caveman-init"}
    assert by["caveman"]["source"] == "Shaxsiy" and by["caveman"]["invoke"] == "/caveman"
    assert by["caveman"]["short"] == "Ultra-compressed communication mode."
    assert by["caveman"]["description"] == "Ultra-compressed communication mode. Cuts tokens. Use when asked."
    assert by["google-workspace"]["synced"] is True
    assert by["deploy-pdf"]["source"] == "Loyiha" and by["deploy-pdf"]["name"] == "Deploy PDF"
    assert by["caveman-commit"]["source"] == "Plagin: Caveman" and by["caveman-commit"]["invoke"] == "/caveman:caveman-commit"
    assert by["caveman-init"]["kind"] == "command"
    assert [g["label"] for g in data["groups"]] == ["Shaxsiy", "Loyiha", "Plagin: Caveman"]
    assert data["total"] == 5
    text = json.dumps(data)
    for leak in ("ed503613", str(claude_home), "/tmp", "BODY SECRET", "SKILL.md", "installPath"):
        assert leak not in text                         # no UUIDs, paths or file contents


def test_used_badge_follows_the_pipeline(claude_home, project):
    used, note = skills_mod.pipeline_skills()
    assert used == set() and "safe-mode" in note       # the bot's Claude calls run with --safe-mode: no skills
    data = skills_mod.scan(claude_home, project, used={"caveman"})
    assert [s["slug"] for s in data["skills"] if s["used"]] == ["caveman"] and data["used_count"] == 1


def test_quoted_descriptions_are_unescaped(tmp_path):
    write(tmp_path / ".claude" / "skills" / "b" / "SKILL.md",
          '---\nname: b\ndescription: "Called \\"your own browser\\" too."\n---\n')
    s = skills_mod.scan(tmp_path / ".claude", tmp_path)["skills"][0]
    assert s["description"] == 'Called "your own browser" too.'


def test_empty_and_missing_sources(tmp_path):
    data = skills_mod.scan(tmp_path / "nothing", tmp_path / "noproject")
    assert data == {"skills": [], "groups": [], "total": 0, "used_count": 0}


# --- repo -----------------------------------------------------------------------------------------------------

def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "T")
    write(r / ".gitignore", ".env\nsecrets/\n/data/\n/logs/\n*.wav\n/models/\n.venv/\n")
    write(r / "socialauto" / "x.py", "print(1)\n")
    write(r / "README.md", "# hi\n")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "First version\n\nCo-Authored-By: Someone <a@b>")
    write(r / ".env", "TELEGRAM_BOT_TOKEN=123:SECRET\n")
    write(r / "secrets" / "youtube_token.json", "{}")
    return r


def test_no_remote(repo):
    s = status(repo)
    assert s["is_repo"] and not s["connected"] and s["repo"] is None
    assert s["ahead"] == 1 and s["ahead_commits"][0]["title"] == "First version"
    assert s["history"][0]["files"] == 3
    assert s["uncommitted"]["count"] == 0                 # .env and secrets/ are ignored, never listed


def test_remote_with_credentials_is_stripped_and_ahead_counted(repo, tmp_path):
    bare = tmp_path / "bare.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", "main")       # test setup only; the website never pushes
    git(repo, "remote", "set-url", "origin", "https://abdu:ghp_SUPERSECRET@github.com/abdu/social-automation.git")
    write(repo / "socialauto" / "web" / "static" / "app.js", "1")
    write(repo / "tests" / "test_a.py", "1")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "Add site and tests")
    write(repo / "docs" / "NEW.md", "x")                  # uncommitted
    write(repo / "proof" / "shot.png", "x")
    s = status(repo)
    assert s["connected"] and s["repo"] == "abdu/social-automation" and s["host"] == "GitHub"
    assert s["ahead"] == 1 and s["ahead_commits"][0]["title"] == "Add site and tests"
    assert s["last_push"]
    cats = {g["label"]: g["count"] for g in s["uncommitted"]["groups"]}
    assert cats == {"Hujjatlar": 1, "Media/rasmlar": 1}
    text = json.dumps(s)
    assert "SUPERSECRET" not in text and "abdu:" not in text and "https://" not in text
    assert "TELEGRAM" not in text and "youtube_token" not in text and ".env" not in text.replace(".env.example", "")


def test_secret_paths_never_listed_even_if_tracked():
    groups = group_files([".env", "secrets/youtube_token.json", "client_secret_123.json", "a/token.json", "app.py"])
    assert groups == [{"label": "Kod", "count": 1, "files": ["app.py"]}]
    assert is_secret(".env.local") and is_secret("secrets/a.json") and not is_secret(".env.example")


def test_categories():
    assert category("socialauto/workflow.py") == "Kod"
    assert category("socialauto/web/static/app.css") == "Sayt"
    assert category("docs/OWNER_TODO.md") == "Hujjatlar"
    assert category("tests/test_x.py") == "Testlar"
    assert category("config.toml") == "Sozlamalar" and category("systemd/x.service") == "Sozlamalar"
    assert category("proof/demo.mp4") == "Media/rasmlar" and category("assets/fonts/A.ttf") == "Media/rasmlar"


def test_remote_name_parsing():
    assert repo_name("git@github.com:abdu/sa.git") == "abdu/sa"
    assert repo_name("https://x:y@github.com/abdu/sa") == "abdu/sa"


def test_git_wrapper_refuses_write_commands(repo):
    for cmd in ("push", "fetch", "commit", "reset", "checkout"):
        with pytest.raises(ValueError):
            Git(repo).run(cmd)


def test_never_pushed_card_in_words(repo):
    s = status(repo)
    titles = [n["title"] for n in s["never"]]
    assert "Parollar, tokenlar va ruxsat fayllari" in titles
    assert "Ma'lumotlar bazasi va sizning ovoz yozuvlaringiz" in titles
    assert not any(".env" in json.dumps(n) for n in s["never"])


# --- API ------------------------------------------------------------------------------------------------------

def test_api_requires_login_and_returns_friendly_data(app, settings, clock, claude_home, project, repo):
    skills_mod._cache.clear()
    client = TestClient(create_app(settings, app.db, None, clock, claude_dir=claude_home, repo_dir=repo))
    assert client.get("/api/skills").status_code == 401
    assert client.get("/api/repo").status_code == 401
    client.post("/api/login", json={"password": "secret-pass"})
    sk = client.get("/api/skills").json()
    assert sk["total"] == 4 and "used_note" in sk         # project skills come from the repo dir here
    rp = client.get("/api/repo").json()
    assert rp["code"]["is_repo"] and rp["code"]["branch"] == "main" and rp["code"]["repo"] == "Abdurahman0/social-automation"
    assert rp["account"]["connected"] is False and rp["content"]["exists"] is False and rp["never"]
    assert "token" not in str(rp["account"]).lower()

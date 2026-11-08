"""Task 07 §7: the one-line installers clone anonymously (no login prompt) and keep no push address."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_install_sh_bootstrap_is_anonymous_and_read_only():
    t = (ROOT / "install.sh").read_text()
    assert "curl -fsSL https://raw.githubusercontent.com/Abdurahman0/social-automation/main/install.sh | bash" in t
    assert 'REPO_URL="https://github.com/Abdurahman0/social-automation.git"' in t        # public HTTPS, never SSH
    assert "credential.helper=" in t and "GIT_TERMINAL_PROMPT=0" in t
    assert "remote set-url --push origin" in t


def test_install_ps1_bootstrap_is_anonymous_and_never_exits_the_shell():
    t = (ROOT / "install.ps1").read_text()
    assert "irm https://raw.githubusercontent.com/Abdurahman0/social-automation/main/install.ps1 | iex" in t
    assert "$RepoUrl = 'https://github.com/Abdurahman0/social-automation.git'" in t
    assert "credential.helper=" in t and "GIT_TERMINAL_PROMPT = '0'" in t and "remote set-url --push origin" in t
    boot = t[t.index("# --- bootstrap"):t.index("$Root = Split-Path -Parent $SelfPath")]
    assert "exit" not in boot.replace("`exit`", "").replace("never `exit`", "").replace("exit would", "")


def test_readme_starts_with_the_one_liners():
    head = (ROOT / "README.md").read_text()[:1500]
    assert "| iex" in head and "| bash" in head


def test_updater_never_uses_credentials():
    t = (ROOT / "socialauto" / "updater.py").read_text()
    assert '"credential.helper="' in t and "push" not in t.replace("never a push", "").replace("Never pushes", "")

"""Installers and portability: shellcheck / PowerShell parse checks, no owner paths in tracked files, Windows
binary names, no API key field anywhere."""

import getpass
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "bin" / "tools"


def tracked() -> list[Path]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.splitlines() if (ROOT / p).is_file()]


def tool(name: str, *extra: Path) -> str | None:
    for p in (TOOLS / "venv" / "bin" / name, TOOLS / name, *extra):
        if p.exists():
            return str(p)
    return shutil.which(name)


def test_no_owner_paths_in_tracked_files():
    """The project runs from any folder on any computer: no home folder or user name of this machine."""
    home, user = str(Path.home()), getpass.getuser().lower()
    bad = []
    for f in tracked():
        if f.suffix in (".png", ".jpg", ".jpeg", ".wav", ".mp4", ".ico", ".woff2"):
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        if home in text or user in text.lower() or "Desktop" + "/social-automation" in text:
            bad.append(str(f.relative_to(ROOT)))
    assert bad == []


def test_proof_is_not_tracked():
    assert not [f for f in tracked() if f.relative_to(ROOT).parts[0] == "proof"]


def test_no_api_key_field_anywhere():
    """Claude runs through each user's own Claude Code login (law 8)."""
    from socialauto import env_store
    assert not any("ANTHROPIC" in k for k in env_store.KEYS)
    assert "ANTHROPIC_API_KEY" not in (ROOT / ".env.example").read_text()


def test_shellcheck_install_sh():
    sc = tool("shellcheck")
    if not sc:
        pytest.skip("shellcheck is not available")
    res = subprocess.run([sc, str(ROOT / "install.sh")], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout


def test_powershell_scripts_parse(tmp_path):
    pwsh = tool("pwsh", TOOLS / "pwshx" / "opt" / "microsoft" / "powershell" / "7" / "pwsh")
    if not pwsh:
        pytest.skip("PowerShell is not available")
    files = [ROOT / "install.ps1", ROOT / "scripts" / "windows_service.ps1"]
    check = tmp_path / "check.ps1"
    check.write_text("$n=0; foreach ($f in $args) { $t=$null; $e=$null; "
                     "[void][System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$t, [ref]$e); "
                     "$n += $e.Count; $e | % { Write-Output $_.Message } }; exit $n")
    res = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-File", str(check), *map(str, files)],
                         capture_output=True, text=True, env={"NO_COLOR": "1", "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    assert res.returncode == 0, res.stdout + res.stderr


def test_install_sh_has_uninstall_and_never_prints_env():
    text = (ROOT / "install.sh").read_text()
    assert "--uninstall" in text and "cat .env" not in text and "MemoryMax" in text
    ps = (ROOT / "install.ps1").read_text()
    assert "-Uninstall" in ps or "$Uninstall" in ps


def test_windows_binary_names(monkeypatch, tmp_path):
    from socialauto.platforms import tunnel
    from socialauto.reel.render import ReelRenderer
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "cloudflared.exe").write_text("")
    (tmp_path / "remotion" / "node_modules" / ".bin").mkdir(parents=True)
    (tmp_path / "remotion" / "node_modules" / ".bin" / "remotion.cmd").write_text("")
    monkeypatch.setattr(sys, "platform", "win32")
    assert tunnel.cloudflared_binary(tmp_path).endswith("cloudflared.exe")
    r = ReelRenderer.__new__(ReelRenderer)
    r.root = tmp_path
    assert r.remotion_bin().name == "remotion.cmd"

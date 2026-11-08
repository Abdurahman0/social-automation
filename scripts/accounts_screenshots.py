"""Task 07 visual check: the new Settings steps (Buffer channels, GitHub, Claude login, Instagram/YouTube statistics),
the update card, the GitHub page and the "Internet yo'q" banner — phone, tablet, desktop, light and dark.

Runs a temporary project (never the real one) with FAKE test accounts: a fake GitHub (device flow approves after
one check), a fake Claude CLI login, fake Buffer channels and a fake pending update. No real token is used.
Every page is checked for layout problems (overflow, outside the viewport, low contrast, console errors).

    systemd-run --user --scope -q -p MemoryMax=3G -p MemorySwapMax=1G -p OOMPolicy=continue -- \
        .venv/bin/python scripts/accounts_screenshots.py --out /tmp/social_task07
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from screenshots import CHECK_JS, DEVICES  # noqa: E402

from socialauto import netcheck  # noqa: E402
from socialauto.claude_login import ClaudeLogin  # noqa: E402
from socialauto.config import load_settings  # noqa: E402
from socialauto.github_account import GitHubAccount  # noqa: E402
from socialauto.web.setup import SetupChecks  # noqa: E402

PASSWORD = "sinov-paroli-123"   # test-only password of a temporary project  gitleaks:allow
ONLINE = {"value": True}


class R:
    def __init__(self, status, body):
        self.status_code, self._b = status, body

    def json(self):
        return self._b


class FakeGitHub:
    def __init__(self):
        self.polls = 0

    def post(self, url, data=None, headers=None, timeout=None):
        if url.endswith("/login/device/code"):
            self.polls = 0
            return R(200, {"device_code": "x", "user_code": "WDJB-MJHT", "verification_uri": "https://github.com/login/device",
                           "interval": 1, "expires_in": 900})
        self.polls += 1
        return R(200, {"error": "authorization_pending"} if self.polls < 2 else {"access_token": "test-only"})

    def request(self, method, url, headers=None, timeout=None, json=None):
        if url.endswith("/user"):
            return R(200, {"login": "dost-sinov", "id": 1, "name": "Do'st (sinov)", "avatar_url": ""})
        if url.endswith("/user/repos"):
            return R(201, {})
        return R(200, {"private": True})


class FakeClaude(ClaudeLogin):
    logged = False

    def status(self):
        return {"installed": True, "logged_in": self.logged, "plan": "Pro" if self.logged else "",
                "email": "dost@example.com" if self.logged else "", "hint": ""}

    def start(self):
        self.state, self.url = "waiting_code", "https://claude.com/cai/oauth/authorize?code=true&client_id=sinov"
        return self.view()

    def submit_code(self, code):
        FakeClaude.logged = True
        self.state = "done"
        return self.view()


class FakeChecks(SetupChecks):
    def buffer(self, key):
        return {"ok": True, "connect_url": "https://publish.buffer.com/channels/connect", "channels": [
            {"service": "Instagram", "kind": "instagram", "name": "suv_va_hayot", "avatar": ""},
            {"service": "YouTube", "kind": "youtube", "name": "Suv va Hayot", "avatar": ""},
            {"service": "LinkedIn", "kind": "linkedin", "name": "Suv va Hayot", "avatar": ""}]}

    def model(self):
        return {"ready": True, "size_mb": 775}


class FakeUpdater:
    def status(self, fetch=True, force=False):
        return {"available": True, "behind": 3, "can_update": True, "reason": "", "current": "abc1234", "checked_at": 0,
                "commits": [{"title": "Sozlamalar: yangi Statistika qadami", "at": 0},
                            {"title": "Reel: tezroq render", "at": 0}, {"title": "Tuzatish: Buffer qoralama nomi", "at": 0}]}

    def apply(self):
        return {"ok": False, "reason": "demo"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(root: Path):
    import uvicorn

    from socialauto.web.server import create_app
    s = load_settings(ROOT / "config.toml", root / ".env", root=root)
    s = replace(s, github=replace(s.github, oauth_client_id="sinov-client-id"),
                web=replace(s.web, public_url="http://localhost:8090"))
    app = create_app(s, checks=FakeChecks(s), github=GitHubAccount(s, session=FakeGitHub()),
                     claude_login=FakeClaude(s), updater=FakeUpdater())
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    return f"http://127.0.0.1:{port}", s


def chrome() -> str:
    for c in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium"):
        if Path(c).exists():
            return c
    raise SystemExit("Google Chrome is needed")


def run(out: Path) -> int:
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="sa-task07-"))
    root = tmp / "proj"
    root.mkdir()
    shutil.copyfile(ROOT / ".gitignore", root / ".gitignore")
    (root / ".env").write_text(f"DASHBOARD_PASSWORD={PASSWORD}\nBUFFER_API_KEY=sinov-kalit\n"
                               "TELEGRAM_BOT_TOKEN=\nTELEGRAM_ALLOWED_USER_IDS=\n")
    netcheck.online = lambda *a, **k: ONLINE["value"]                     # the banner is driven by the test
    import socialauto.web.server as srv                                   # noqa: F401 (already imported online)
    base, settings = start_server(root)
    report: dict[str, dict] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome(), headless=True)
        for device, (w, hgt) in DEVICES.items():
            for theme in ("dark", "light"):
                FakeClaude.logged = False
                (root / "secrets" / "github.json").unlink(missing_ok=True)
                ctx = browser.new_context(viewport={"width": w, "height": hgt})
                ctx.add_init_script(f"localStorage.setItem('sa_theme', '{theme}')")
                page = ctx.new_page()
                errors: list[str] = []
                page.on("console", lambda m, e=errors: m.type == "error" and "favicon" not in m.text and e.append(m.text))
                page.on("popup", lambda pop: pop.close())

                def shot(name):
                    page.wait_for_timeout(500)
                    key = f"{name}-{device}-{theme}"
                    page.screenshot(path=str(out / f"{key}.png"), full_page=True)
                    r = page.evaluate(CHECK_JS)
                    r["console_errors"] = list(errors)
                    r["ok"] = (r["docWidth"] <= r["viewport"] and not r["offenders"] and not r["overlaps"]
                               and not r["console_errors"] and not r["lowContrast"])
                    report[key] = r

                page.goto(base + "/")
                page.fill("input[type=password]", PASSWORD)
                page.keyboard.press("Enter")
                page.wait_for_selector(".shell")
                page.goto(base + "/#/settings/buffer")
                page.wait_for_selector(".chan-list .chan")
                shot("settings-3-buffer")
                page.goto(base + "/#/settings/github")
                page.wait_for_selector("text=GitHub'ni ulash")
                shot("settings-4-github")
                page.click("button:has-text(\"GitHub'ni ulash\")")
                page.wait_for_selector(".code-box")
                shot("settings-4-github-code")
                page.wait_for_selector(".acct", timeout=15000)
                shot("settings-4-github-connected")
                page.goto(base + "/#/settings/claude")
                page.wait_for_selector("text=Claude'ga kirish")
                shot("settings-5-claude")
                page.click("button:has-text(\"Claude'ga kirish\")")
                page.wait_for_selector("input[aria-label='Claude kodi']")
                page.fill("input[aria-label='Claude kodi']", "sinov-kodi")
                shot("settings-5-claude-code")
                page.click("button:has-text('Tasdiqlash')")
                page.wait_for_selector("text=Claude'ga kirilgan")
                shot("settings-5-claude-done")
                page.goto(base + "/#/settings/stats")
                page.wait_for_selector(".svc-grid")
                shot("settings-6-stats")
                page.goto(base + "/#/repo")
                page.wait_for_selector(".acct")
                shot("github-page")
                ONLINE["value"] = False
                page.goto(base + "/#/settings/done")
                page.wait_for_selector(".net-banner:not([hidden])", timeout=10000)
                shot("offline-banner")
                ONLINE["value"] = True
                ctx.close()
        browser.close()
    (out / "accounts_layout_check.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    shutil.rmtree(tmp, ignore_errors=True)
    bad = [k for k, v in report.items() if not v["ok"]]
    print(f"{len(report)} screenshots, layout problems: {bad or 'none'}")
    for k in bad[:5]:
        print(k, {x: report[k][x] for x in ("offenders", "overlaps", "console_errors", "lowContrast")})
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("/tmp/social_task07"))
    sys.exit(run(ap.parse_args().out))

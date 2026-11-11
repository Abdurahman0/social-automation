"""Task 09 visual check: Sozlamalar → GitHub «Yangi repo yaratish» / «Mavjud repomni ulash» (his repo list, search,
a read-only repo with its reason, the connected state) and the GitHub page of a connected existing repo — phone,
tablet, desktop, light and dark, every palette on the connected GitHub page.

A temporary project only, with a FAKE GitHub account (no real token). "His" repo is a LOCAL bare repo shaped like
the-suvyektiv-media (reels/<date>-<topic>/reel.mp4 + cover.jpg + script.md, posted.md, brand/, .claude/skills/):
the real GitHub repo is never contacted. Every page is checked for layout problems.

    systemd-run --user --scope -q -p MemoryMax=3G -p MemorySwapMax=1G -p OOMPolicy=continue -- \
        .venv/bin/python scripts/content_repo_screenshots.py --out /var/tmp/social_task09
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from accounts_screenshots import R, chrome, free_port  # noqa: E402
from screenshots import CHECK_JS, DEVICES  # noqa: E402

from socialauto import netcheck  # noqa: E402
from socialauto.config import load_settings  # noqa: E402
from socialauto.content_repo import ContentRepo  # noqa: E402
from socialauto.github_account import GitHubAccount  # noqa: E402

PASSWORD = "sinov-paroli-123"   # test-only password of a temporary project  gitleaks:allow
PALETTES = ["oltin", "okean", "zumrad", "lola", "binafsha", "shafaq"]


def repo(full, private, pushed, push=True, archived=False):
    owner, name = full.split("/")
    return {"full_name": full, "name": name, "owner": {"login": owner}, "private": private, "pushed_at": pushed,
            "html_url": f"https://github.com/{full}", "archived": archived, "description": "",
            "permissions": {"push": push, "admin": push, "pull": True}, "id": 1}


REPOS = [repo("eraliyev-j/the-suvyektiv-media", False, "2026-11-10T04:44:08Z"),
         repo("eraliyev-j/doktor-h2o-carousels", True, "2026-11-04T10:12:00Z"),
         repo("eraliyev-j/busan-lab-notes", True, "2026-10-21T08:00:00Z"),
         repo("water-lab-pnu/river-monitoring", True, "2026-10-02T03:00:00Z", push=False),
         repo("eraliyev-j/old-website", False, "2025-05-01T00:00:00Z")]


class FakeGitHub:
    def post(self, url, data=None, headers=None, timeout=None):
        return R(200, {"access_token": "test-only"})

    def request(self, method, url, headers=None, timeout=None, json=None):
        if url.endswith("/user"):
            return R(200, {"login": "eraliyev-j", "id": 1, "name": "Javohir (sinov)", "avatar_url": ""})
        if "/user/repos?" in url:
            return R(200, REPOS)
        for r in REPOS:
            if url.endswith("/repos/" + r["full_name"]):
                return R(200, r)
        if url.endswith("/user/repos"):
            return R(201, {})
        return R(404, {})


def git(repo_dir, *args):
    subprocess.run(["git", "-C", str(repo_dir), *args], check=True, capture_output=True)


def his_bare(tmp: Path) -> Path:
    """A small local repo in his layout (and one reel added by the app, so «oxirgi yuklangan reel» shows)."""
    work = tmp / "his-pc"
    git(tmp, "init", "-q", "-b", "main", str(work))
    files = {"posted.md": "# Posted log\n\nYYYY-MM-DD | pillar | topic | hook | CTA#\n",
             "brand/voice.md": "# voice\n- reel 30–40 s, maksimum 45 s.\n",
             ".claude/skills/doktor-h2o-workflow/SKILL.md": "---\nname: doktor-h2o-workflow\ndescription: Doktor H2O reel ish tartibi.\n---\n",
             ".claude/skills/doktor-h2o-brand/SKILL.md": "---\nname: doktor-h2o-brand\ndescription: Shaxsiy brend strategiyasi.\n---\n"}
    for d in ("2026-10-22-qaynatilgan-suv", "2026-10-29-salar-hid", "2026-11-05-layfhak", "2026-11-07-buloq-suvi",
              "2026-11-10-ichak-tayoqchasi"):
        files[f"reels/{d}/reel.mp4"] = "v"
        files[f"reels/{d}/cover.jpg"] = "c"
    for rel, text in files.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(text, encoding="utf-8")
    git(work, "add", "-A")
    git(work, "-c", "user.name=eraliyev-j", "-c", "user.email=j@example.com", "commit", "-q", "-m", "Add 10.11 ichak tayoqchasi reel")
    for rel in ("reels/2026-11-12-kran-suvi/reel.mp4", "reels/2026-11-12-kran-suvi/cover.jpg", "reels/2026-11-12-kran-suvi/script.md"):
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text("x", encoding="utf-8")
    git(work, "add", "-A")
    git(work, "-c", "user.name=eraliyev-j", "-c", "user.email=j@example.com", "commit", "-q", "-m", "Reel: Kran suvini ichsa bo'ladimi? (2026-11-12)")
    bare = tmp / "the-suvyektiv-media.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)], check=True)
    return bare


def start_server(root: Path, bare: Path):
    import uvicorn

    from socialauto.web.server import create_app
    s = load_settings(ROOT / "config.toml", root / ".env", root=root)
    s = replace(s, github=replace(s.github, oauth_client_id="sinov-client-id"))
    real_remote = ContentRepo.remote_url

    def remote_url(self):                       # his repo == the local bare copy (never the real GitHub)
        return str(bare) if self.is_existing() else real_remote(self)
    ContentRepo.remote_url = remote_url
    gh = GitHubAccount(s, session=FakeGitHub())
    gh._store_user("test-only", "device")
    app = create_app(s, github=gh)
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


def run(out: Path) -> int:
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="sa-task09-", dir="/var/tmp"))
    root = tmp / "proj"
    root.mkdir()
    shutil.copyfile(ROOT / ".gitignore", root / ".gitignore")
    (root / ".env").write_text(f"DASHBOARD_PASSWORD={PASSWORD}\nTELEGRAM_BOT_TOKEN=\nTELEGRAM_ALLOWED_USER_IDS=\n", encoding="utf-8")
    netcheck.online = lambda *a, **k: True
    bare = his_bare(tmp)
    base, settings = start_server(root, bare)
    local = root / "config.local.toml"
    report: dict[str, dict] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome(), headless=True)
        for device, (w, hgt) in DEVICES.items():
            for theme in ("dark", "light"):
                local.unlink(missing_ok=True)                       # every round starts with "not chosen yet"
                ctx = browser.new_context(viewport={"width": w, "height": hgt})
                ctx.add_init_script(f"localStorage.setItem('sa_theme', '{theme}')")
                page = ctx.new_page()
                errors: list[str] = []
                page.on("console", lambda m, e=errors: m.type == "error" and "favicon" not in m.text and e.append(m.text))
                page.on("popup", lambda pop: pop.close())

                def shot(name, palette=""):
                    page.wait_for_timeout(450)
                    key = f"{name}-{device}-{theme}" + (f"-{palette}" if palette else "")
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
                page.goto(base + "/#/settings/github")
                page.wait_for_selector(".rc-cards")
                shot("github-1-choose")
                page.click(".rc-card[data-key=existing]")
                page.wait_for_selector(".repo-item")
                shot("github-2-existing-list")
                page.fill(".rc-existing .search", "suv")
                page.wait_for_timeout(150)
                shot("github-3-existing-search")
                page.fill(".rc-existing .search", "")
                page.fill(".rc-link input", "github.com/salom")
                page.click(".rc-link .btn")
                page.wait_for_selector(".sf-result.bad")
                shot("github-4-bad-link")
                page.click(".repo-item:has-text('the-suvyektiv-media')")
                page.wait_for_selector("text=reposiga boradi", timeout=20000)
                page.wait_for_function("!document.body.innerText.includes('yuklab olinmoqda')", timeout=60000)
                shot("github-5-existing-connected")
                page.goto(base + "/#/repo")
                page.wait_for_selector(".acct")
                page.wait_for_selector("text=6 ta reel", timeout=20000)
                shot("github-page")
                if device == "desktop" or device == "phone":
                    for pal in PALETTES:
                        page.evaluate(f"localStorage.setItem('sa_palette', '{pal}')")
                        page.reload()
                        page.wait_for_selector("text=6 ta reel", timeout=20000)
                        shot("github-page", pal)
                    page.evaluate("localStorage.setItem('sa_palette', 'oltin')")
                page.goto(base + "/#/skills")
                page.wait_for_selector("text=Kontent reposi", timeout=20000)
                shot("skills-content-repo")
                ctx.close()
        browser.close()
    (out / "content_repo_layout_check.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    bad = [k for k, v in report.items() if not v["ok"]]
    print(f"{len(report)} screenshots, layout problems: {bad or 'none'}")
    for k in bad[:8]:
        print(k, {x: report[k][x] for x in ("offenders", "overlaps", "console_errors", "lowContrast")})
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("/var/tmp/social_task09"))
    sys.exit(run(ap.parse_args().out))

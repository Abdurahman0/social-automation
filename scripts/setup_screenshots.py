"""Walk the Setup ("Sozlash") wizard like a new user, on phone, tablet and desktop, in light and dark, and screenshot
every step. Each run starts from a first start (the .env reset to the template), fills in dry-run test values and
checks every page for layout problems (overflow, elements outside the viewport, low contrast, console errors).

The website must already run (for example from a fresh clone):
    .venv/bin/python -c "from socialauto.config import load_settings as l; from socialauto.web.server import create_app as c; \
        import uvicorn; uvicorn.run(c(l()), host='127.0.0.1', port=8091)"
then (memory cap on Linux, law 9):
    systemd-run --user --scope -q -p MemoryMax=3G -p MemorySwapMax=1G -p OOMPolicy=continue -- \
        .venv/bin/python scripts/setup_screenshots.py --url http://127.0.0.1:8091 --root <clone> --out <folder>
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshots import CHECK_JS, DEVICES  # noqa: E402

FAKE_TOKEN = "1234567890:AAH" + "TestOnlyDryRunValue_" + "x" * 16       # right shape, not a real bot
STEPS = ["1-password", "2-telegram", "3-buffer", "4-extra", "5-claude", "6-done"]


def chrome() -> str:
    for c in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium"):
        if Path(c).exists():
            return c
    raise SystemExit("Google Chrome is needed for the screenshots")


def check(page, errors) -> dict:
    r = page.evaluate(CHECK_JS)
    r["console_errors"] = list(errors)
    r["ok"] = (r["docWidth"] <= r["viewport"] and not r["offenders"] and not r["overlaps"]
               and not r["console_errors"] and not r["lowContrast"])
    return r


def run(url: str, root: Path, out: Path) -> int:
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    env, template = root / ".env", root / ".env.example"
    report: dict[str, dict] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome(), headless=True)
        for device, (w, hgt) in DEVICES.items():
            for theme in ("dark", "light"):
                shutil.copyfile(template, env)                       # a first start every time
                ctx = browser.new_context(viewport={"width": w, "height": hgt}, device_scale_factor=1)
                ctx.add_init_script(f"localStorage.setItem('sa_theme', '{theme}')")
                page = ctx.new_page()
                errors: list[str] = []
                page.on("console", lambda m, e=errors: m.type == "error" and e.append(m.text))

                def shot(step: str) -> None:
                    page.wait_for_timeout(350)
                    name = f"setup-{step}-{device}-{theme}"
                    page.screenshot(path=str(out / f"{name}.png"), full_page=True)
                    report[name] = check(page, errors)

                page.goto(url + "/", wait_until="networkidle")
                assert page.url.endswith("/setup"), page.url               # first start lands on the Setup page
                page.wait_for_selector("text=Sayt paroli")
                shot(STEPS[0])
                page.fill("input[aria-label='Yangi parol']", "sinov-paroli-123")
                page.fill("input[aria-label='Parolni takrorlang']", "sinov-paroli-123")
                page.click("button:has-text('Davom etish')")

                page.wait_for_selector("text=2. Telegram bot")
                page.fill("input[name=TELEGRAM_BOT_TOKEN]", FAKE_TOKEN)
                page.fill("input[name=TELEGRAM_ALLOWED_USER_IDS]", "123456789")
                page.click("button:has-text('Tekshirish')")
                page.wait_for_selector(".sf-result.good, .sf-result.bad", timeout=30000)
                shot(STEPS[1])
                page.click("button:has-text('Davom etish')")

                page.wait_for_selector("text=3. Buffer")
                page.fill("input[name=BUFFER_API_KEY]", "dry-run-test-key-not-real")
                page.click("button:has-text('Tekshirish')")
                page.wait_for_selector(".sf-result.good, .sf-result.bad", timeout=30000)
                shot(STEPS[2])
                page.click("button:has-text('Davom etish')")

                page.wait_for_selector("text=4. Qo'shimcha")
                shot(STEPS[3])
                page.click("button:has-text('Keyinroq')")

                page.wait_for_selector("text=5. Claude")
                shot(STEPS[4])
                page.click("button:has-text('Davom etish')")

                page.wait_for_selector("text=6. Tayyor")
                shot(STEPS[5])
                page.click("button:has-text('Boshlash')")
                page.wait_for_selector(".shell", timeout=15000)

                page.goto(url + "/#/settings", wait_until="networkidle")
                page.wait_for_selector(".setup-steps")
                page.wait_for_timeout(500)
                name = f"settings-{device}-{theme}"
                page.screenshot(path=str(out / f"{name}.png"), full_page=True)
                report[name] = check(page, errors)
                ctx.close()
        browser.close()
    (out / "setup_layout_check.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    bad = [k for k, v in report.items() if not v["ok"]]
    print(f"{len(report)} screenshots, layout problems: {bad or 'none'}")
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--root", required=True, type=Path, help="the project folder the website runs from")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    sys.exit(run(a.url.rstrip("/"), a.root, a.out))

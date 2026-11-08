"""Dashboard visual check (Playwright, installed Google Chrome, one worker) on phone, tablet and desktop widths.

Two runs:
1. REAL state of the demo project (work/demo): no account connected yet -> the honest "connect" screens, and the
   pipeline with the demo video. Screenshots: proof/dashboard_<page>_<device>.png
2. LAYOUT TEST with clearly labelled fixture numbers in a temporary database (never the real one), so charts, tables
   and cards can be checked for layout bugs with data in them. Screenshots: proof/layout-test/<page>_<device>.png

Every page is checked automatically for horizontal overflow (document wider than the viewport), elements sticking out
of the viewport, overlapping KPI tiles, and console errors. A report goes to proof/layout_check.json.

    systemd-run --user --scope -q -p MemoryMax=3G -p MemorySwapMax=1G -p OOMPolicy=continue -- \
        .venv/bin/python scripts/screenshots.py
"""

from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from socialauto.config import load_settings  # noqa: E402

PROOF = ROOT / "proof"
DEVICES = {"phone": (390, 844), "tablet": (820, 1180), "desktop": (1440, 900)}
PAGES = {"overview": "#/", "videos": "#/videos", "insights": "#/insights", "pipeline": "#/pipeline", "skills": "#/skills",
         "repo": "#/repo"}
PASSWORD = "layout-check-password"

CHECK_JS = r"""() => {
  const vw = document.documentElement.clientWidth;
  const out = {docWidth: document.documentElement.scrollWidth, viewport: vw, offenders: [], overlaps: 0};
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    if (el.closest('.board, .table-scroll, .tooltip, svg, .pop')) continue;   // intentional scroll areas
    if (r.right > vw + 1 || r.left < -1) out.offenders.push((el.className && el.className.baseVal === undefined ? el.className : el.tagName) + ' ' + Math.round(r.left) + '..' + Math.round(r.right));
  }
  const tiles = [...document.querySelectorAll('.kpi, .card')].map(e => e.getBoundingClientRect());
  for (let i = 0; i < tiles.length; i++) for (let j = i + 1; j < tiles.length; j++) {
    const a = tiles[i], b = tiles[j];
    const inside = (a.left <= b.left && a.right >= b.right && a.top <= b.top && a.bottom >= b.bottom) ||
                   (b.left <= a.left && b.right >= a.right && b.top <= a.top && b.bottom >= a.bottom);
    if (!inside && a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) out.overlaps++;
  }
  out.offenders = out.offenders.slice(0, 10);
  // colours must come from the theme: a dark page, and card headings readable on the dark cards
  const lum = (c) => { const m = c.match(/\d+(\.\d+)?/g).map(Number); const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(m[0]) + 0.7152 * f(m[1]) + 0.0722 * f(m[2]); };
  out.lowContrast = [];
  const bodyBg = getComputedStyle(document.body).backgroundColor;
  const light = document.documentElement.dataset.theme === 'light';
  if (light ? lum(bodyBg) < 0.6 : lum(bodyBg) > 0.2) out.lowContrast.push('page background does not match the theme: ' + bodyBg);
  for (const el of document.querySelectorAll('h1, h2, h3, .value, .vtitle, .banner b, td, .btn')) {
    let bg = null, n = el;
    while (n && n !== document.documentElement) { const c = getComputedStyle(n).backgroundColor; if (!c.startsWith('rgba(0, 0, 0, 0)') && c !== 'transparent') { bg = c; break; } n = n.parentElement; }
    bg = bg || bodyBg;
    if (bg.startsWith('rgba') && !bg.endsWith(', 1)')) continue;     // translucent layer: skip
    const a = lum(getComputedStyle(el).color), b = lum(bg);
    const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    if (ratio < 3) out.lowContrast.push(el.tagName + ' ' + (el.textContent || '').slice(0, 30) + ' ' + ratio.toFixed(1));
  }
  out.lowContrast = out.lowContrast.slice(0, 8);
  return out;
}"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(settings, db=None, collector=None, clock=None) -> str:
    """The dashboard for `settings`; the Skills and GitHub pages always show this real repo and ~/.claude."""
    import uvicorn

    from socialauto.web.server import create_app
    port = free_port()
    app = create_app(settings, db, collector, clock, repo_dir=ROOT)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return f"http://127.0.0.1:{port}"
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("server did not start")


def seed_fixture(settings) -> None:
    """Layout-test numbers (fake platform clients, temp DB only). Labelled as a test in the screenshots' folder."""
    from socialauto.analytics.collector import Collector
    from socialauto.app import build_app
    import random
    rnd = random.Random(7)
    app = build_app(settings)
    for f in (settings.youtube.token_file, settings.instagram.token_file):
        p = settings.resolve(f)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}")
    titles = ["This bell has rung since 1840 on the same batteries", "Octopuses have three hearts — one stops when they swim",
              "Honey found in Egyptian tombs was still edible", "Why Venus spins the wrong way",
              "The shortest war in history lasted 38 minutes", "Bananas are berries but strawberries are not",
              "A day on Venus is longer than its year", "Sharks are older than trees"]
    start = datetime(2026, 9, 1, 0, tzinfo=timezone.utc)

    class YT:
        def __init__(self): self.day = 0
        def channel(self):
            return {"statistics": {"subscriberCount": str(1200 + self.day * 23), "viewCount": str(40000 + self.day * 1900), "videoCount": "8"}}
        def recent_upload_ids(self, n=50): return [f"y{i}" for i in range(min(8, 1 + self.day // 8))]
        def videos(self, ids, parts=""):
            return [{"id": i, "snippet": {"title": titles[int(i[1:])], "publishedAt": (start + timedelta(days=int(i[1:]) * 8, hours=11 + int(i[1:]) % 3)).isoformat().replace("+00:00", "Z"), "thumbnails": {}},
                     "statistics": {"viewCount": str(800 + int(i[1:]) * 650 + self.day * 31), "likeCount": str(60 + int(i[1:]) * 20), "commentCount": str(4 + int(i[1:]))},
                     "contentDetails": {"duration": "PT42S"}} for i in ids]
        def report(self, **p):
            if p.get("dimensions") == "day":
                rows = []
                for k in range(self.day + 1):
                    d = (start + timedelta(days=k)).date().isoformat()
                    v = 900 + 40 * k + rnd.randint(-200, 300)
                    rows.append([d, v, v * 0.4, 28, v * 0.07, v * 0.01, v * 0.015, 20, 3])
                return {"columnHeaders": [{"name": n} for n in ("day", "views", "estimatedMinutesWatched", "averageViewDuration", "likes", "comments", "shares", "subscribersGained", "subscribersLost")], "rows": rows}
            if p.get("dimensions") == "elapsedVideoTimeRatio":
                return {"rows": [[k / 20, round(1.0 * (0.985 ** k) - 0.004 * k, 3)] for k in range(21)]}
            return {"columnHeaders": [{"name": n} for n in ("video", "views", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage", "shares")],
                    "rows": [[f"y{i}", 1000, 400, 25 + i, 55 + i * 3, 10 + i] for i in range(8)]}

    class IG:
        def __init__(self): self.day = 0
        def refresh_if_needed(self): pass
        def account(self): return {"followers_count": 800 + self.day * 31, "media_count": 8}
        def recent_media(self, n=50):
            return [{"id": f"g{i}", "caption": titles[i] + "\n#suv", "permalink": f"https://instagram.com/reel/g{i}/",
                     "timestamp": (start + timedelta(days=i * 8, hours=14)).strftime("%Y-%m-%dT%H:%M:%S+0000")} for i in range(min(8, 1 + self.day // 8))]
        def media_insights(self, mid):
            i = int(mid[1:])
            return {"views": 1400 + i * 900 + self.day * 40, "reach": 1100 + i * 600, "likes": 120 + i * 30, "comments": 6 + i, "shares": 15 + i * 4, "saved": 22 + i * 5,
                    "ig_reels_avg_watch_time": 11000 + i * 700, "ig_reels_video_view_total_time": 900000 + i * 100000}
        def account_insights(self, since, until):
            k = (since.date() - start.date()).days
            v = 1300 + 55 * k + rnd.randint(-250, 350)
            return {"views": v, "reach": v * 0.8, "likes": v * 0.08, "comments": v * 0.006, "shares": v * 0.012, "saves": v * 0.02} if k >= 0 else {}

    for i, title in enumerate(titles):          # our own reels: the owner scheduled them in Buffer; Buffer reported the links
        vid = app.store.create_video("done", slot_at=start + timedelta(days=i * 8, hours=14))
        app.store.add_script(vid, {"title": title, "topic": title})
        app.workflow.reels.upsert(vid, base=f"{(start + timedelta(days=i * 8)).date()}-reel-{i}", step="done",
                                  live_links={"youtube": f"https://youtube.com/shorts/y{i}",
                                              "instagram": f"https://instagram.com/reel/g{i}/"})
    yt, ig = YT(), IG()
    clock = {"now": start}
    from socialauto.db import KV
    col = Collector(settings, app.db, KV(app.db), lambda: yt, lambda: ig, lambda: clock["now"])
    for d in range(69):
        yt.day = ig.day = d
        clock["now"] = start + timedelta(days=d)
        col.refresh(force_reports=(d % 7 == 0 or d == 68))
    # pipeline items
    for status, title in (("voice_waiting", "Why flamingos are pink"), ("rendering", "The loudest sound ever recorded"),
                          ("video_pending", "Cleopatra lived closer to the Moon landing than to the pyramids"),
                          ("script_pending", "Wombats make cube-shaped poop")):
        vid = app.store.create_video(status, slot_at=datetime(2026, 11, 9, 14, tzinfo=timezone.utc) + timedelta(days=len(app.store.videos())))
        app.store.add_script(vid, {"title": title, "topic": title})


def shoot(base: str, out_dir: Path, report: dict, tag: str, scheme: str = "dark") -> None:
    from playwright.sync_api import sync_playwright
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, args=["--disable-gpu", "--no-sandbox"])
        for device, (w, h) in DEVICES.items():
            ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if device == "phone" else 1,
                                      is_mobile=device == "phone", has_touch=device != "desktop", color_scheme=scheme)
            sfx = "" if scheme == "dark" else "_light"
            page = ctx.new_page()
            errors = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base + "/")
            page.wait_for_selector("#pw")
            if device == "desktop":
                page.screenshot(path=str(out_dir / f"login_{device}{sfx}.png"))
            page.fill("#pw", PASSWORD)
            page.click("button[type=submit]")
            page.wait_for_selector(".shell")
            for name, hash_ in PAGES.items():
                page.goto(base + "/" + hash_)
                page.wait_for_selector(".shell")
                page.wait_for_timeout(900)
                result = page.evaluate(CHECK_JS)
                result["console_errors"] = list(errors)
                errors.clear()
                result["ok"] = result["docWidth"] <= result["viewport"] and not result["offenders"] and not result["overlaps"] and not result["console_errors"] and not result["lowContrast"]
                report[f"{tag}/{scheme}/{name}/{device}"] = result
                page.screenshot(path=str(out_dir / f"{name}_{device}{sfx}.png"), full_page=True)
                if name == "skills":              # an opened skill card
                    page.locator(".skill").first.click()
                    page.wait_for_timeout(200)
                    page.screenshot(path=str(out_dir / f"skills-open_{device}{sfx}.png"))
                if name == "repo":                # an expanded file category
                    btn = page.locator(".cat-btn")
                    if btn.count():
                        btn.first.click()
                        page.wait_for_timeout(200)
                        page.screenshot(path=str(out_dir / f"repo-files_{device}{sfx}.png"), full_page=True)
            if tag == "real":                    # the reel detail page (research, script, frames, checklist, sources)
                page.goto(base + "/#/pipeline")
                page.wait_for_selector(".shell")
                page.wait_for_timeout(500)
                cards = page.locator(".reel-card")
                if cards.count():
                    cards.first.click()
                    page.wait_for_selector(".stepper")
                    page.wait_for_timeout(1200)
                    r = page.evaluate(CHECK_JS)
                    r["console_errors"] = list(errors)
                    r["ok"] = (r["docWidth"] <= r["viewport"] and not r["offenders"] and not r["overlaps"]
                               and not r["console_errors"] and not r["lowContrast"])
                    report[f"{tag}/{scheme}/reel/{device}"] = r
                    page.screenshot(path=str(out_dir / f"reel_{device}{sfx}.png"), full_page=True)
            if tag == "layout-test" and scheme == "dark":
                # interactions: open the handmade date picker, the custom select, a video detail page, chart hover
                page.goto(base + "/#/")
                page.wait_for_selector(".shell")
                page.wait_for_timeout(500)
                page.click("button[aria-label=\"Sana oralig'i\"]")
                page.click("text=Boshqa oraliq…")
                page.wait_for_timeout(300)
                page.screenshot(path=str(out_dir / f"datepicker_{device}.png"))
                page.keyboard.press("Escape")
                page.click("button[aria-label='Ko\\'rsatkich']")
                page.wait_for_timeout(200)
                page.screenshot(path=str(out_dir / f"select_{device}.png"))
                page.keyboard.press("Escape")
                box = page.locator(".chart svg").first.bounding_box()
                if box:
                    page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] * 0.5)
                    page.wait_for_timeout(200)
                    page.screenshot(path=str(out_dir / f"chart_hover_{device}.png"))
                page.goto(base + "/#/videos")
                page.wait_for_selector(".shell")
                page.wait_for_timeout(500)
                page.locator(".vtable tbody tr:visible, .vcard:visible").first.click()
                page.wait_for_selector(".side-by-side")
                page.wait_for_timeout(600)
                r = page.evaluate(CHECK_JS)
                r["console_errors"] = list(errors)
                r["ok"] = r["docWidth"] <= r["viewport"] and not r["offenders"] and not r["overlaps"] and not r["console_errors"] and not r["lowContrast"]
                report[f"{tag}/{scheme}/video-detail/{device}"] = r
                page.screenshot(path=str(out_dir / f"video-detail_{device}.png"), full_page=True)
            ctx.close()
        browser.close()


def main() -> int:
    report: dict = {}
    # 1. the real demo project state
    demo = ROOT / "work" / "demo_reel"
    if not demo.exists():
        demo = ROOT / "work" / "demo"
    settings = load_settings(demo / "config.toml", ROOT / ".env", root=demo)
    settings = replace(settings, dashboard_password=PASSWORD)
    base = start_server(settings)
    for scheme in ("dark", "light"):
        shoot(base, PROOF / "dashboard", report, "real", scheme)
    # 2. layout test with fixture numbers in a temporary database
    with tempfile.TemporaryDirectory() as tmp:
        troot = Path(tmp)
        for name in ("assets", "models"):
            (troot / name).symlink_to(ROOT / name)
        (troot / "config.toml").write_text((ROOT / "config.toml").read_text())
        s2 = replace(load_settings(troot / "config.toml", troot / "none.env", root=troot), dashboard_password=PASSWORD)
        seed_fixture(s2)
        fixed = lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc)   # noqa: E731
        base2 = start_server(s2, clock=fixed)
        for scheme in ("dark", "light"):
            shoot(base2, PROOF / "layout-test", report, "layout-test", scheme)
    chat = PROOF / "reel" / "telegram_chat.html"
    if chat.exists():                       # the demo's recorded Telegram messages, rendered like the app
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True, args=["--disable-gpu", "--no-sandbox"])
            page = browser.new_page(viewport={"width": 480, "height": 900}, device_scale_factor=2)
            page.goto(chat.as_uri())
            page.wait_for_timeout(500)
            page.screenshot(path=str(PROOF / "reel" / "telegram_chat.png"), full_page=True)
            browser.close()
    (PROOF / "layout_check.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    bad = [k for k, v in report.items() if not v["ok"]]
    print("layout check:", "all OK" if not bad else f"problems in {bad}")
    for k in bad:
        print(k, json.dumps(report[k])[:400])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

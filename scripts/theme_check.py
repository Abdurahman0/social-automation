"""Task 08 proof: colour themes and the wave, in the real website (Playwright + installed Google Chrome).

* every palette in dark and light on phone (390), tablet (820) and desktop (1440) on the dashboard (layout-test
  fixture numbers in a temporary database, never the real one) — no horizontal overflow, no console errors;
* the picker (popover on desktop/tablet, bottom sheet on phone) on the dashboard, Setup and login pages;
* keyboard (Tab, arrows, Enter, Esc, focus back on the button), saving across a reload, "Tizim" following the OS live;
* the wave: a frame at ~50 % on desktop and phone, with the circle's centre compared to the clicked swatch/icon;
  a second click during a wave, reduced motion, the no-View-Transitions fallback, charts re-coloured, scroll kept;
* a short recording of the wave turned into a GIF.

    systemd-run --user --scope -q -p MemoryMax=3G -p MemorySwapMax=1G -p OOMPolicy=continue -- \
        .venv/bin/python scripts/theme_check.py
Screenshots go to /tmp/social_task08/, the report to /tmp/social_task08/theme_check.json; the best ones are copied
to docs/images/ with --publish.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from screenshots import DEVICES, PASSWORD, seed_fixture, start_server  # noqa: E402

from socialauto.config import load_settings  # noqa: E402

OUT = Path("/tmp/social_task08")
IMAGES = ROOT / "docs" / "images"
PALETTES = ["oltin", "okean", "zumrad", "lola", "binafsha", "shafaq"]

OVERFLOW_JS = "() => ({doc: document.documentElement.scrollWidth, vw: document.documentElement.clientWidth})"
# waits until the wave's animations exist, then freezes every animation at `ms` (the wave lasts 720 ms)
FREEZE_JS = r"""async (ms) => {
  for (let i = 0; i < 120; i++) {
    const anims = document.getAnimations();
    const wave = anims.find(a => a.effect && (a.effect.pseudoElement === '::view-transition-new(root)' || (a.effect.target && a.effect.target.classList && a.effect.target.classList.contains('wave-fill'))));
    if (wave) {
      for (const a of document.getAnimations()) { a.pause(); a.currentTime = ms; }
      const kf = wave.effect.getKeyframes()[0].clipPath;
      const m = kf.match(/at ([\d.]+)px ([\d.]+)px/);
      return {kind: wave.effect.pseudoElement ? 'view-transition' : 'fallback', x: +m[1], y: +m[2], count: document.getAnimations().length};
    }
    await new Promise(r => requestAnimationFrame(r));
  }
  return null;
}"""
RESUME_JS = "() => { for (const a of document.getAnimations()) { const end = a.effect.getComputedTiming().endTime; if (a.currentTime >= end) a.finish(); else a.play(); } }"
CENTER_JS = "(el) => { const r = el.getBoundingClientRect(); return {x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2)}; }"
STATE_JS = """() => ({mode: document.documentElement.dataset.mode, theme: document.documentElement.dataset.theme,
  palette: document.documentElement.dataset.palette, rings: document.querySelectorAll('.wave-ring, .wave-fill').length,
  waveClass: document.documentElement.classList.contains('vt-wave'), stored: [localStorage.getItem('sa_theme'), localStorage.getItem('sa_palette')],
  focus: document.activeElement && (document.activeElement.getAttribute('aria-label') || document.activeElement.textContent.trim()),
  meta: document.querySelector('meta[name=theme-color]').content})"""


def new_ctx(browser, device, **kw):
    w, h = DEVICES[device]
    return browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if device == "phone" else 1,
                               is_mobile=device == "phone", has_touch=device != "desktop", **kw)


def watch(page, errors):
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))


def login(page, base):
    page.goto(base + "/")
    page.wait_for_selector("#pw")
    page.fill("#pw", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_selector(".shell")


def set_theme(page, mode, palette):
    page.evaluate("([m, p]) => { localStorage.setItem('sa_theme', m); localStorage.setItem('sa_palette', p); }", [mode, palette])


def visible_theme_button(page):
    return page.locator(".theme-btn:visible").first


def wave_frame(page, target, shot, report, key):
    """Click `target` (a swatch dot or mode icon) and freeze the wave at 50 %; compare the circle centre to the target."""
    want = page.evaluate(CENTER_JS, target.element_handle())
    box = target.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    got = page.evaluate(FREEZE_JS, 360)
    ov = page.evaluate(OVERFLOW_JS)
    page.screenshot(path=str(shot))
    page.evaluate(RESUME_JS)
    page.wait_for_timeout(900)
    after = page.evaluate(STATE_JS)
    ok = bool(got) and abs(got["x"] - want["x"]) <= 2 and abs(got["y"] - want["y"]) <= 2 and ov["doc"] <= ov["vw"] and after["rings"] == 0 and not after["waveClass"]
    report[key] = {"clicked_centre": want, "wave_centre": got, "overflow": ov, "after": after, "ok": ok}
    return ok


def run(publish: bool) -> int:
    from playwright.sync_api import sync_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {}
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as tmp2:
        troot = Path(tmp)
        for name in ("assets", "models"):
            (troot / name).symlink_to(ROOT / name)
        (troot / "config.toml").write_text((ROOT / "config.toml").read_text(encoding="utf-8"), encoding="utf-8")
        s2 = replace(load_settings(troot / "config.toml", troot / "none.env", root=troot), dashboard_password=PASSWORD)
        seed_fixture(s2)
        base = start_server(s2, clock=lambda: datetime(2026, 11, 8, 12, tzinfo=timezone.utc))
        froot = Path(tmp2)                                   # an unconfigured copy: the first-run Setup page
        (froot / "config.toml").write_text((ROOT / "config.toml").read_text(encoding="utf-8"), encoding="utf-8")
        fresh = start_server(replace(load_settings(froot / "config.toml", froot / "none.env", root=froot), dashboard_password=""))

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True, args=["--disable-gpu", "--no-sandbox"])

            # 1. every palette x mode x device on the dashboard
            for device in DEVICES:
                ctx = new_ctx(browser, device)
                page = ctx.new_page()
                errors: list[str] = []
                watch(page, errors)
                login(page, base)
                for pal in PALETTES:
                    for mode in ("dark", "light"):
                        set_theme(page, mode, pal)
                        page.goto(base + "/#/")
                        page.reload()
                        page.wait_for_selector(".shell .chart svg")
                        page.wait_for_timeout(350)
                        st = page.evaluate(STATE_JS)
                        ov = page.evaluate(OVERFLOW_JS)
                        page.screenshot(path=str(OUT / f"dash_{pal}_{mode}_{device}.png"))
                        report[f"palette/{pal}/{mode}/{device}"] = {
                            "applied": st["palette"] == pal and st["theme"] == mode, "overflow": ov, "console_errors": list(errors),
                            "ok": st["palette"] == pal and st["theme"] == mode and ov["doc"] <= ov["vw"] and not errors}
                        errors.clear()
                ctx.close()

            # 2. desktop: picker, keyboard, persistence, wave, double click, charts, scroll, Tizim
            ctx = new_ctx(browser, "desktop", color_scheme="dark")
            page = ctx.new_page()
            errors = []
            watch(page, errors)
            login(page, base)
            set_theme(page, "dark", "oltin")
            page.reload()
            page.wait_for_selector(".shell .chart svg")
            page.wait_for_timeout(400)
            btn = visible_theme_button(page)
            btn.click()
            page.wait_for_selector(".theme-pop")
            page.wait_for_timeout(250)
            page.screenshot(path=str(OUT / "picker_desktop.png"))
            pop, bb = page.locator(".theme-pop").bounding_box(), btn.bounding_box()
            report["picker/desktop/anchored"] = {"pop": pop, "button": bb, "ok": abs(pop["x"] - bb["x"]) < 20 and pop["y"] + pop["height"] <= bb["y"]}
            # keyboard: focus starts on the chosen swatch, arrow right -> Okean, Enter picks it, Esc closes, focus returns
            k1 = page.evaluate(STATE_JS)["focus"]
            page.keyboard.press("ArrowRight")
            k2 = page.evaluate(STATE_JS)["focus"]
            page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
            k3 = page.evaluate(STATE_JS)
            page.keyboard.press("Shift+Tab")                       # back into the mode group (the chosen one: Qorong'i)
            k4 = page.evaluate(STATE_JS)["focus"]
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            k5 = page.evaluate(STATE_JS)
            report["keyboard"] = {"start": k1, "after_arrow": k2, "after_enter": k3["palette"], "shift_tab": k4, "after_esc_focus": k5["focus"],
                                  "closed": page.locator(".theme-pop").count() == 0,
                                  "ok": k1 == "Oltin" and k2 == "Okean" and k3["palette"] == "okean" and k4 == "Qorong'i"
                                  and k5["focus"] == "Mavzu va rang" and page.locator(".theme-pop").count() == 0}
            page.reload()
            page.wait_for_selector(".shell")
            st = page.evaluate(STATE_JS)
            report["persistence/reload"] = {"state": st, "ok": st["palette"] == "okean" and st["stored"] == ["dark", "okean"]}
            # the wave from a swatch, frozen at 50 %; plus a chart stroke before/after and the scroll position kept
            page.mouse.wheel(0, 400)
            page.wait_for_timeout(300)
            scroll_before = page.evaluate("() => window.scrollY")
            visible_theme_button(page).click()
            page.wait_for_selector(".theme-pop")
            page.wait_for_timeout(250)
            ok = wave_frame(page, page.locator('[data-palette-opt="zumrad"] .sw-dot'), OUT / "wave_mid_desktop.png", report, "wave/desktop/swatch")
            report["wave/desktop/scroll_kept"] = {"before": scroll_before, "after": page.evaluate("() => window.scrollY"),
                                                  "popover_still_open": page.locator(".theme-pop").count() == 1}
            report["wave/desktop/scroll_kept"]["ok"] = report["wave/desktop/scroll_kept"]["before"] == report["wave/desktop/scroll_kept"]["after"] and report["wave/desktop/scroll_kept"]["popover_still_open"]
            page.screenshot(path=str(OUT / "picker_after_wave_desktop.png"))
            stroke = "() => getComputedStyle(document.querySelector('.chart .line')).stroke"
            before = page.evaluate(stroke)
            wave_frame(page, page.locator('[data-mode-opt="light"] .seg-ico'), OUT / "wave_mid_mode_desktop.png", report, "wave/desktop/mode-icon")
            after = page.evaluate(stroke)
            report["charts/recoloured"] = {"before": before, "after": after, "ok": before != after}
            # a second click while the first wave runs: finish it and start from the new point
            page.locator('[data-palette-opt="lola"] .sw-dot').click()
            page.wait_for_timeout(180)
            page.locator('[data-palette-opt="binafsha"] .sw-dot').click()
            page.wait_for_timeout(1100)
            st = page.evaluate(STATE_JS)
            report["wave/double-click"] = {"state": st, "ok": st["palette"] == "binafsha" and st["rings"] == 0 and not st["waveClass"]}
            page.keyboard.press("Escape")
            # Tizim follows the OS live
            visible_theme_button(page).click()
            page.locator('[data-mode-opt="system"]').click()
            page.wait_for_timeout(900)
            t1 = page.evaluate(STATE_JS)["theme"]
            page.emulate_media(color_scheme="light")
            page.wait_for_timeout(600)
            t2 = page.evaluate(STATE_JS)["theme"]
            page.emulate_media(color_scheme="dark")
            page.wait_for_timeout(600)
            t3 = page.evaluate(STATE_JS)
            report["tizim/live"] = {"themes": [t1, t2, t3["theme"]], "stored": t3["stored"], "ok": [t1, t2, t3["theme"]] == ["dark", "light", "dark"] and t3["stored"][0] == "system"}
            report["desktop/console_errors"] = {"errors": list(errors), "ok": not errors}
            ctx.close()

            # 3. frames of the wave (desktop): each wave is frozen every 35 ms and captured, then turned into a GIF
            frames = OUT / "frames"
            shutil.rmtree(frames, ignore_errors=True)
            frames.mkdir()
            ctx = new_ctx(browser, "desktop")
            page = ctx.new_page()
            login(page, base)
            set_theme(page, "dark", "oltin")
            page.reload()
            page.wait_for_selector(".shell .chart svg")
            page.wait_for_timeout(500)
            visible_theme_button(page).click()
            page.wait_for_timeout(400)
            n = 0

            def grab(count):
                nonlocal n
                for _ in range(count):
                    page.screenshot(path=str(frames / f"f{n:04d}.jpg"), type="jpeg", quality=85)
                    n += 1
            grab(6)
            for target in ('[data-palette-opt="okean"] .sw-dot', '[data-mode-opt="light"] .seg-ico', '[data-palette-opt="shafaq"] .sw-dot',
                           '[data-mode-opt="dark"] .seg-ico', '[data-palette-opt="lola"] .sw-dot'):
                box = page.locator(target).bounding_box()
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                page.evaluate(FREEZE_JS, 0)
                for ms in range(0, 756, 36):
                    page.evaluate("(ms) => { for (const a of document.getAnimations()) a.currentTime = ms; }", ms)
                    grab(1)
                page.evaluate(RESUME_JS)
                page.wait_for_timeout(500)
                grab(8)
            ctx.close()

            # 4. phone: bottom sheet, wave from a swatch, mode icon in the sheet
            ctx = new_ctx(browser, "phone", color_scheme="dark")
            page = ctx.new_page()
            errors = []
            watch(page, errors)
            login(page, base)
            set_theme(page, "dark", "oltin")
            page.reload()
            page.wait_for_selector(".shell .chart svg")
            page.wait_for_timeout(400)
            visible_theme_button(page).click()
            page.wait_for_selector(".theme-layer.sheet .theme-pop")
            page.wait_for_timeout(400)
            page.screenshot(path=str(OUT / "picker_phone.png"))
            pop = page.locator(".theme-pop").bounding_box()
            report["picker/phone/sheet"] = {"pop": pop, "ok": abs(pop["y"] + pop["height"] - 844) <= 1 and pop["x"] == 0 and pop["width"] == 390}
            wave_frame(page, page.locator('[data-palette-opt="lola"] .sw-dot'), OUT / "wave_mid_phone.png", report, "wave/phone/swatch")
            page.screenshot(path=str(OUT / "picker_after_wave_phone.png"))
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            report["phone/esc_focus"] = {"focus": page.evaluate(STATE_JS)["focus"], "ok": page.evaluate(STATE_JS)["focus"] == "Mavzu va rang"}
            report["phone/console_errors"] = {"errors": list(errors), "ok": not errors}
            ctx.close()

            # 5. reduced motion: a short cross-fade only, no circle
            ctx = new_ctx(browser, "desktop", reduced_motion="reduce")
            page = ctx.new_page()
            login(page, base)
            visible_theme_button(page).click()
            page.locator('[data-palette-opt="okean"] .sw-dot').click()
            seen = page.evaluate("""async () => { let clip = false; for (let i = 0; i < 20; i++) {
                if (document.getAnimations().some(a => a.effect && a.effect.getKeyframes().some(k => k.clipPath))) clip = true;
                if (document.querySelector('.wave-ring')) clip = true;
                await new Promise(r => requestAnimationFrame(r)); } return clip; }""")
            page.wait_for_timeout(400)
            st = page.evaluate(STATE_JS)
            report["reduced-motion"] = {"circle_seen": seen, "state": st, "ok": not seen and st["palette"] == "okean"}
            ctx.close()

            # 6. fallback without View Transitions (Firefox / older Safari behaviour)
            ctx = new_ctx(browser, "desktop")
            ctx.add_init_script("delete Document.prototype.startViewTransition;")
            page = ctx.new_page()
            errors = []
            watch(page, errors)
            login(page, base)
            set_theme(page, "dark", "oltin")
            page.reload()
            page.wait_for_selector(".shell .chart svg")
            visible_theme_button(page).click()
            page.wait_for_timeout(250)
            wave_frame(page, page.locator('[data-palette-opt="shafaq"] .sw-dot'), OUT / "wave_mid_fallback.png", report, "wave/fallback")
            report["wave/fallback"]["ok"] = report["wave/fallback"]["ok"] and report["wave/fallback"]["wave_centre"]["kind"] == "fallback" and report["wave/fallback"]["after"]["palette"] == "shafaq"
            report["fallback/console_errors"] = {"errors": list(errors), "ok": not errors}
            ctx.close()

            # 7. the picker on the login page and the first-run Setup page, every device
            for device in DEVICES:
                ctx = new_ctx(browser, device)
                page = ctx.new_page()
                errors = []
                watch(page, errors)
                page.goto(base + "/")
                page.wait_for_selector("#pw")
                visible_theme_button(page).click()
                page.wait_for_selector(".theme-pop")
                page.wait_for_timeout(300)
                page.screenshot(path=str(OUT / f"login_picker_{device}.png"))
                page.locator('[data-palette-opt="binafsha"] .sw-dot').click()
                page.wait_for_timeout(1000)
                page.keyboard.press("Escape")
                ov = page.evaluate(OVERFLOW_JS)
                page.screenshot(path=str(OUT / f"login_binafsha_{device}.png"))
                login_ok = page.evaluate("() => document.documentElement.dataset.palette") == "binafsha"
                page.goto(fresh + "/setup")
                page.wait_for_selector(".setup-page .theme-btn")
                page.wait_for_timeout(300)
                visible_theme_button(page).click()
                page.wait_for_selector(".theme-pop")
                page.locator('[data-palette-opt="zumrad"] .sw-dot').click()
                page.wait_for_timeout(1000)
                page.locator('[data-mode-opt="light"] .seg-ico').click()
                page.wait_for_timeout(1000)
                st = page.evaluate(STATE_JS)
                ov2 = page.evaluate(OVERFLOW_JS)
                page.screenshot(path=str(OUT / f"setup_picker_{device}.png"))
                report[f"login+setup/{device}"] = {"login_page_ok": login_ok, "setup_page": [st["palette"], st["theme"]], "overflow": [ov, ov2], "errors": list(errors),
                                                   "ok": login_ok and st["palette"] == "zumrad" and st["theme"] == "light" and ov["doc"] <= ov["vw"] and ov2["doc"] <= ov2["vw"] and not errors}
                ctx.close()
            browser.close()

    gif = OUT / "wave.gif"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "20", "-i", str(OUT / "frames" / "f%04d.jpg"), "-vf",
                    "scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
                    str(gif)], check=True)
    (OUT / "theme_check.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    bad = [k for k, v in report.items() if not v.get("ok")]
    print(f"{len(report)} checks:", "all OK" if not bad else f"problems in {bad}")
    for k in bad:
        print(k, json.dumps(report[k])[:500])
    if publish and not bad:
        IMAGES.mkdir(parents=True, exist_ok=True)
        for src, dst in (("wave_mid_desktop.png", "task08-wave-mid-desktop.png"), ("wave_mid_phone.png", "task08-wave-mid-phone.png"),
                         ("picker_desktop.png", "task08-picker-desktop.png"), ("picker_phone.png", "task08-picker-phone.png"),
                         ("dash_okean_light_tablet.png", "task08-okean-light-tablet.png"), ("dash_lola_dark_desktop.png", "task08-lola-dark-desktop.png"),
                         ("wave.gif", "task08-wave.gif")):
            shutil.copy(OUT / src, IMAGES / dst)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(run("--publish" in sys.argv))

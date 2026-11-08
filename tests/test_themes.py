"""Task 08: colour themes. Every palette x mode sets the full token set, passes WCAG AA, and the choice is saved and
applied before first paint (the real inline <head> script is executed in Node with a fake browser)."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "socialauto" / "web" / "static"
CSS = (STATIC / "app.css").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
HTML = (STATIC / "index.html").read_text(encoding="utf-8")

PALETTES = ["oltin", "okean", "zumrad", "lola", "binafsha", "shafaq"]
MODES = ["dark", "light"]
TOKENS = ["bg", "surface-1", "surface-2", "surface-3", "hairline", "text-primary", "text-secondary", "text-muted",
          "accent", "accent-ink", "accent-text", "yt", "ig", "combined", "good", "bad", "shadow", "side-bg", "nav-bg",
          "tip-bg", "wash", "sheen", "col-bg", "banner-line", "banner-bg", "glow-1", "glow-2", "brand-1", "brand-2",
          "brand-ink"]


def blocks() -> dict:
    out = {}
    for mode, pal, body in re.findall(r'\[data-theme="(\w+)"\]\[data-palette="(\w+)"\]\s*\{([^}]*)\}', CSS):
        assert (mode, pal) not in out, f"{pal}/{mode} defined twice"
        out[(mode, pal)] = dict(re.findall(r"--([\w-]+):\s*([^;]+);", body))
        out[(mode, pal)]["color-scheme"] = re.search(r"color-scheme:\s*(\w+)", body).group(1)
    return out


def lum(hexc: str) -> float:
    h = hexc.lstrip("#")
    assert re.fullmatch(r"[0-9a-fA-F]{6}", h), hexc

    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a: str, b: str) -> float:
    x, y = lum(a), lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


def test_every_palette_and_mode_sets_the_full_token_set():
    b = blocks()
    assert set(b) == {(m, p) for m in MODES for p in PALETTES}
    for (mode, pal), t in b.items():
        missing = [k for k in TOKENS if k not in t]
        assert not missing, f"{pal}/{mode} misses {missing}"
        assert t["color-scheme"] == mode


def test_palettes_are_really_different():
    b = blocks()
    for mode in MODES:
        accents = {b[(mode, p)]["accent"].lower() for p in PALETTES}
        bgs = {b[(mode, p)]["bg"].lower() for p in PALETTES}
        assert len(accents) == len(PALETTES) and len(bgs) == len(PALETTES), mode   # not just the accent: tinted surfaces too


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("pal", PALETTES)
def test_wcag_aa_contrast(pal, mode):
    t = blocks()[(mode, pal)]
    problems = []
    for fg in ("text-primary", "text-secondary", "text-muted", "accent-text"):        # body text: AA 4.5:1
        for bg in ("bg", "surface-1", "surface-2"):
            if ratio(t[fg], t[bg]) < 4.5:
                problems.append(f"{fg} on {bg} {ratio(t[fg], t[bg]):.2f}")
    if ratio(t["text-secondary"], t["surface-3"]) < 4.5:                              # tags / counters
        problems.append("text-secondary on surface-3")
    if ratio(t["accent-ink"], t["accent"]) < 4.5:                                     # primary buttons, chosen chips
        problems.append(f"accent-ink on accent {ratio(t['accent-ink'], t['accent']):.2f}")
    if ratio(t["brand-ink"], t["brand-1"]) < 3:
        problems.append("brand mark")
    for g in ("yt", "ig", "combined", "good", "bad"):                                 # chart lines and status: 3:1 (graphics)
        for bg in ("surface-1", "surface-2"):
            if ratio(t[g], t[bg]) < 3:
                problems.append(f"{g} on {bg} {ratio(t[g], t[bg]):.2f}")
    assert not problems, f"{pal}/{mode}: {problems}"


def test_platform_colours_stay_recognisable():
    b = blocks()
    for mode in MODES:
        assert len({b[(mode, p)]["yt"] for p in PALETTES}) == 1 and len({b[(mode, p)]["ig"] for p in PALETTES}) == 1


def test_palette_lists_agree_everywhere():
    js = re.search(r"const PALETTES = \[(.*?)\];", JS, re.S).group(1)
    js_keys = re.findall(r'key: "(\w+)"', js)
    head = re.search(r"\[(\"oltin\"[^\]]*)\]", HTML).group(1)
    assert js_keys == PALETTES
    assert json.loads(f"[{head}]") == PALETTES
    names = re.findall(r'name: "([^"]+)"', js)
    assert names == ["Oltin", "Okean", "Zumrad", "Lola", "Binafsha", "Shafaq"]   # real Uzbek names in the UI


def test_no_native_controls_and_wave_wiring():
    for bad in ('h("select"', 'type: "checkbox"', 'type: "radio"', 'type: "color"'):
        assert bad not in JS
    assert "startViewTransition" in JS and "::view-transition-new(root)" in JS and "clipPath" in JS
    assert "prefers-reduced-motion: reduce" in JS
    assert "@property --wave-r" in CSS and ".wave-ring" in CSS and ".wave-fill" in CSS
    assert '"sa_theme"' in JS and '"sa_palette"' in JS
    assert "route();" not in re.search(r"function setTheme.*?\n}", JS, re.S).group(0)   # no re-render on a switch


HEAD_RUNNER = r"""
const vm = require("vm");
const src = process.argv[1];
const cases = JSON.parse(process.argv[2]);
const out = [];
for (const c of cases) {
  const attrs = {};
  const ctx = {
    localStorage: { getItem: (k) => (k in c.store ? c.store[k] : null) },
    document: { documentElement: { setAttribute: (k, v) => { attrs[k] = v; } } },
    window: {},
    matchMedia: (q) => ({ matches: q.includes("light") && c.osLight }),
  };
  ctx.window.matchMedia = ctx.matchMedia;
  if (c.storageThrows) ctx.localStorage = { getItem: () => { throw new Error("blocked"); } };
  vm.runInNewContext(src, ctx);
  out.push(attrs);
}
console.log(JSON.stringify(out));
"""


def run_head(cases):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    src = re.search(r"<script>(.*?)</script>", HTML, re.S).group(1)
    res = subprocess.run([node, "-e", HEAD_RUNNER, src, json.dumps(cases)], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def test_saved_choice_is_applied_before_first_paint():
    out = run_head([
        {"store": {}, "osLight": False},
        {"store": {"sa_theme": "light", "sa_palette": "okean"}, "osLight": False},
        {"store": {"sa_theme": "dark", "sa_palette": "lola"}, "osLight": True},
        {"store": {"sa_theme": "nonsense", "sa_palette": "<b>"}, "osLight": False},
        {"store": {}, "osLight": True, "storageThrows": True},
    ])
    assert out[0] == {"data-mode": "system", "data-theme": "dark", "data-palette": "oltin"}        # defaults
    assert out[1] == {"data-mode": "light", "data-theme": "light", "data-palette": "okean"}        # persisted
    assert out[2] == {"data-mode": "dark", "data-theme": "dark", "data-palette": "lola"}           # mode beats the OS
    assert out[3] == {"data-mode": "system", "data-theme": "dark", "data-palette": "oltin"}        # junk is ignored
    assert out[4] == {"data-mode": "system", "data-theme": "light", "data-palette": "oltin"}       # blocked storage


def test_system_mode_follows_the_os():
    out = run_head([{"store": {"sa_theme": "system", "sa_palette": "zumrad"}, "osLight": light} for light in (True, False)])
    assert [o["data-theme"] for o in out] == ["light", "dark"]
    assert all(o["data-mode"] == "system" and o["data-palette"] == "zumrad" for o in out)
    # live: app.js listens to the OS change and re-applies only while the mode is "Tizim"
    assert re.search(r'osLight\.addEventListener\("change", \(\) => \{ if \(currentTheme\(\)\.mode === "system"\)', JS)


def test_head_script_runs_before_the_stylesheet():
    assert HTML.index("<script>") < HTML.index('href="/static/app.css"') < HTML.index('src="/static/app.js"')

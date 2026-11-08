# TASK 08 — Colour themes + a wave transition that starts from the theme icon

Owner (2026-11-09): "Add in the social website the colour-changing theme modes, and when the theme is changed it
should feel like a wave that starts with that icon!"

Builds on the current dashboard (`socialauto/web/static/app.js`, `app.css`, `index.html`). Today there is only a
dark/light toggle (`applyTheme`, `themeButton`, `localStorage sa_theme`, `:root[data-theme="light"]`). Inspect it first.
All laws in CLAUDE.md still apply: handmade UI controls only (no native select/checkbox), never raw JSON / codes /
ids in the UI, Uzbek UI text, works on phone / tablet / desktop, no scroll or layout bugs, OOM limits
(systemd-run MemoryMax=3G for browsers/tests). Finish everything; decide defaults yourself; no questions.

## 1. Theme modes (colour palettes)
- Keep **mode** (Qorong'i / Yorug' / Tizim = follow OS) and add a **colour theme** on top of it, so each palette
  works in both dark and light. At least 6 palettes, each with a real name in Uzbek and a distinct feel, e.g.
  Oltin (current yellow, default), Okean (blue/teal), Zumrad (green), Lola (pink/magenta), Binafsha (violet),
  Shafaq (orange/sunset). Each palette sets the full token set (`--bg`, surfaces, hairline, `--accent`,
  `--accent-ink`, `--accent-text`, banner/wash colours, shadows) — not just the accent. Text and accent text must
  pass WCAG AA contrast on every palette × mode; add a test that checks it from the CSS tokens.
- Chart platform colours (`--yt`, `--ig`, `--combined`) stay recognisable and readable on every palette.
- A handmade **theme picker**: the current theme button opens a small popover (desktop: anchored to the button;
  phone: bottom sheet) with the mode segmented control (sun / moon / monitor icons) and palette swatches (colour
  circle + name, check mark on the active one). Keyboard accessible (Tab, arrows, Enter, Esc), focus returns to
  the button. Available on the dashboard sidebar, the mobile header, the Setup page and the login page.
- Saved in localStorage (`sa_theme` mode + `sa_palette`), applied before first paint (inline in `index.html`
  `<head>`) so there is no flash of the wrong theme on reload. "Tizim" follows OS changes live.

## 2. The wave transition (the main point)
- When the user picks a mode or palette, the new theme spreads as a **circular wave from the exact icon / swatch
  that was clicked** (its centre), growing until it covers the whole screen — like a ripple washing over the page.
- Use the View Transitions API (`document.startViewTransition`) with a `clip-path: circle()` animation on
  `::view-transition-new(root)` whose radius reaches the farthest viewport corner; ~600–750 ms, a soft ease-out.
  Add a subtle wave feel: a thin glowing ring in the new accent colour riding the edge of the circle (e.g. a
  pseudo/overlay ring that expands with it and fades), so it reads as a wave, not a plain wipe.
- Fallback for browsers without View Transitions (Firefox / older Safari): an overlay circle in the new `--bg`
  expanding from the same point, then the theme switches underneath and the overlay fades — no jump, no flash.
- `prefers-reduced-motion: reduce` → instant switch with a short cross-fade only.
- Must not break: re-render (`route()`) during the transition, open charts (re-colour after the switch), scroll
  position, open popover, fixed headers/nav. No layout shift, no horizontal scrollbar during the animation.
- Clicking again while a wave runs: finish/skip the current one cleanly, start the new one from the new point.

## 3. Proof
- Tests for: palette tokens complete for every palette × mode, contrast check, persistence, Tizim mode.
- Playwright (inside systemd-run MemoryMax=3G): screenshots of every palette in dark and light on phone (390),
  tablet (820), desktop (1440) for the dashboard; plus a mid-wave frame (≈50 % of the animation) on desktop and
  phone proving the circle starts from the clicked icon. Check no console errors and no horizontal overflow.
- Save 4–6 of the best screenshots + a short screen recording/GIF of the wave to `docs/images/`, the rest in
  `/tmp/social_task08/`.
- Write `docs/TASK_08_REPORT.md` in simple Uzbek (what changed, how to use it, what was not verifiable), commit,
  and push to `main` (normal push, never force).

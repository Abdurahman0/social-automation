/* Social Automation dashboard. Plain JS, no build step. All data text goes in via textContent (never innerHTML). */
"use strict";

// ---------------------------------------------------------------- helpers
const $app = document.getElementById("app");
const $tip = document.getElementById("tooltip");
const SVGNS = "http://www.w3.org/2000/svg";
const MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"];
const MON = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"];
const WEEKDAYS = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"];
const WEEKDAY_FULL = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"];
const PF = { youtube: { name: "YouTube", cls: "yt", color: "var(--yt)" }, instagram: { name: "Instagram", cls: "ig", color: "var(--ig)" } };

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
function s(tag, attrs, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) el.setAttribute(k, v);
  for (const kid of kids.flat()) if (kid) el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  return el;
}
const ICONS = {
  overview: "M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z",
  videos: "M4 5h16v14H4zM10 9l5 3-5 3z",
  insights: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  pipeline: "M4 4h4v16H4zM10 4h4v10h-4zM16 4h4v6h-4z",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7",
  check: "M5 12.5l4.5 4.5L19 7",
  chevron: "M6 9l6 6 6-6",
  left: "M15 6l-6 6 6 6",
  right: "M9 6l6 6-6 6",
  calendar: "M4 6h16v14H4zM4 10h16M9 3v4M15 3v4",
  logout: "M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  ext: "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
  yt: "M3 8.5c0-2 1.5-3.5 3.5-3.5h11C19.5 5 21 6.5 21 8.5v7c0 2-1.5 3.5-3.5 3.5h-11C4.5 19 3 17.5 3 15.5zM10 9v6l5-3z",
  ig: "M7 3h10a4 4 0 0 1 4 4v10a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V7a4 4 0 0 1 4-4zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM17.5 6.5h.01",
  mic: "M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3zM5 11a7 7 0 0 0 14 0M12 18v3",
  skills: "M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4 6.8 19.1l1-5.8L3.5 9.2l5.9-.9z",
  github: "M9 19c-4.3 1.4-4.3-2.5-6-3M15 22v-3.9a3.4 3.4 0 0 0-.9-2.6c3.1-.4 6.4-1.5 6.4-6.9A5.4 5.4 0 0 0 19 4.8 5 5 0 0 0 18.9 1S17.7.6 15 2.5a13.4 13.4 0 0 0-7 0C5.3.6 4.1 1 4.1 1A5 5 0 0 0 4 4.8a5.4 5.4 0 0 0-1.5 3.8c0 5.4 3.3 6.5 6.4 6.9a3.4 3.4 0 0 0-.9 2.6V22",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9 12l2 2 4-4",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  key: "M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4M12 15v2",
  send: "M22 2 11 13M22 2l-7 20-4-9-9-4z",
  layers: "M12 2 2 7l10 5 10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
  plus: "M12 5v14M5 12h14",
  cpu: "M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3M6 6h12v12H6zM10 10h4v4h-4z",
  flag: "M4 22V4M4 4h12l-2 4 2 4H4",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  cloud: "M7 18a5 5 0 1 1 .9-9.9A6 6 0 0 1 19 10a4 4 0 0 1 0 8z",
  monitor: "M3 4h18v12H3zM8 20h8M12 16v4",
  close: "M6 6l12 12M18 6 6 18",
  cloudOff: "M3 3l18 18M8.5 8.4A5 5 0 0 0 7 18h10M15.6 7.1A6 6 0 0 1 19 10a4 4 0 0 1 1.7 7.6",
};
function icon(name) {
  const svg = s("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" });
  svg.append(s("path", { d: ICONS[name] }));
  return svg;
}
function num(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const a = Math.abs(v);
  const fx = (x) => x.toFixed(1).replace(/\.0$/, "").replace(".", ",");
  if (a >= 1e6) return fx(v / 1e6) + " mln";
  if (a >= 1e4) return fx(v / 1e3) + " ming";
  return Math.round(v).toLocaleString("ru-RU").replace(/ /g, " ");
}
function full(v) { return v === null || v === undefined ? "—" : Math.round(v).toLocaleString("ru-RU").replace(/ /g, " "); }
function pct(v) { return v === null || v === undefined ? "—" : String(v.toFixed(1)).replace(".", ",") + "%"; }
function secs(v) {
  if (v === null || v === undefined) return "—";
  return v >= 60 ? `${Math.floor(v / 60)} daq ${Math.round(v % 60)} s` : `${String(v.toFixed(1)).replace(".", ",")} s`;
}
function signed(v) { if (v === null || v === undefined) return null; return (v >= 0 ? "+" : "−") + num(Math.abs(v)); }
function dayLabel(iso) { const d = new Date(iso + "T00:00:00"); return `${d.getDate()}-${MON[d.getMonth()]}`; }
function dayLong(iso) { const d = new Date(iso + "T00:00:00"); return `${d.getDate()}-${MONTHS[d.getMonth()]} ${d.getFullYear()}`; }
function postedLabel(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const t = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Tashkent" });
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tashkent" }).format(d);
  return `${dayLabel(day)}, ${t}`;
}
function isoDay(d) { return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tashkent" }).format(d); }
function addDays(iso, n) { const d = new Date(iso + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
function agoText(m) {
  if (m === null || m === undefined) return "hali yangilanmagan";
  if (m < 1) return "hozirgina yangilandi";
  if (m < 60) return `${m} daqiqa oldin yangilandi`;
  if (m < 1440) return `${Math.floor(m / 60)} soat oldin yangilandi`;
  return `${Math.floor(m / 1440)} kun oldin yangilandi`;
}

async function api(path, opts = {}) {
  const res = await fetch(path, { credentials: "same-origin", headers: { "Content-Type": "application/json" }, ...opts });
  if (res.status === 401 && !path.startsWith("/api/login")) {
    const d = await res.clone().json().catch(() => ({}));
    if (d.reason === "setup") { location.href = "/setup"; throw new Error("login"); }
    renderLogin(); throw new Error("login");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { const e = new Error(data.reason || "error"); e.status = res.status; throw e; }
  return data;
}

// ---------------------------------------------------------------- theme: mode + colour palette + the wave (Task 08)
// <head> already put data-mode / data-theme / data-palette on <html> before first paint (no flash). This keeps it in
// sync, saves the choice (localStorage sa_theme = light|dark|system, sa_palette) and plays the wave on every change.
const PALETTES = [
  { key: "oltin", name: "Oltin" }, { key: "okean", name: "Okean" }, { key: "zumrad", name: "Zumrad" },
  { key: "lola", name: "Lola" }, { key: "binafsha", name: "Binafsha" }, { key: "shafaq", name: "Shafaq" },
];
const MODES = [{ key: "light", name: "Yorug'", icon: "sun" }, { key: "dark", name: "Qorong'i", icon: "moon" }, { key: "system", name: "Tizim", icon: "monitor" }];
const WAVE_MS = 720;
const WAVE_EASE = "cubic-bezier(.4, .15, .2, 1)";   // soft ease-out: the ripple gathers, then washes out with a long gentle settle
const osLight = window.matchMedia ? matchMedia("(prefers-color-scheme: light)") : { matches: false, addEventListener() {} };
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode: the choice lives for this page only */ } },
};
function savedTheme() {
  const m = store.get("sa_theme"), p = store.get("sa_palette");
  return { mode: MODES.some((x) => x.key === m) ? m : "system", palette: PALETTES.some((x) => x.key === p) ? p : "oltin" };
}
function resolveMode(mode) { return mode === "system" ? (osLight.matches ? "light" : "dark") : mode; }
function currentTheme() { const r = document.documentElement.dataset; return { mode: r.mode || "system", palette: r.palette || "oltin", theme: r.theme || "dark" }; }
function paletteName(key) { return (PALETTES.find((p) => p.key === key) || PALETTES[0]).name; }

function applyTheme({ mode, palette }) {
  const r = document.documentElement, theme = resolveMode(mode);
  r.dataset.mode = mode; r.dataset.theme = theme; r.dataset.palette = palette;
  document.querySelectorAll(".sw-dot").forEach((d) => { d.dataset.theme = theme; });
  document.querySelectorAll("[data-mode-opt]").forEach((b) => { b.setAttribute("aria-checked", String(b.dataset.modeOpt === mode)); });
  document.querySelectorAll("[data-palette-opt]").forEach((b) => { b.setAttribute("aria-checked", String(b.dataset.paletteOpt === palette)); });
  document.querySelectorAll(".theme-btn .tb-name").forEach((n) => { n.textContent = paletteName(palette); });
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", getComputedStyle(r).getPropertyValue("--bg").trim() || "#0f1014");
  window.dispatchEvent(new CustomEvent("sa-themechange", { detail: { mode, palette, theme } }));
}
applyTheme(savedTheme());

// The wave. One at a time: a new click finishes the running wave at once and starts again from the new point.
let wave = null;
function originOf(el) {
  if (!el || !el.isConnected) return null;
  const r = el.getBoundingClientRect();
  if (!r.width && !r.height) return null;
  return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
}
function farthestCorner(pt) {
  const w = document.documentElement.clientWidth, hgt = window.innerHeight;
  return Math.ceil(Math.hypot(Math.max(pt.x, w - pt.x), Math.max(pt.y, hgt - pt.y))) + 2;
}
function waveRing(pt) {   // a thin glowing crest in the NEW accent, riding just inside the edge of the circle
  const ring = h("div", { class: "wave-ring", "aria-hidden": "true" });
  ring.style.setProperty("--wx", `${pt.x}px`); ring.style.setProperty("--wy", `${pt.y}px`);
  document.body.append(ring);
  return ring;
}
function animateRing(ring, R) {
  return ring.animate([{ "--wave-r": "0px", opacity: 1 }, { opacity: 1, offset: 0.62 }, { "--wave-r": `${R}px`, opacity: 0 }],
    { duration: WAVE_MS, easing: WAVE_EASE, fill: "forwards" });
}
function transitionTheme(next, pt) {
  if (wave) wave.finish();
  const now = currentTheme();
  if (now.palette === next.palette && now.theme === resolveMode(next.mode)) { applyTheme(next); return; }   // nothing to see
  const root = document.documentElement;
  const reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || !pt) {                       // reduced motion / OS switch: a short cross-fade only (or instant)
    if (!document.startViewTransition) { applyTheme(next); return; }
    root.classList.add("vt-fade");
    let over = false;
    const t = document.startViewTransition(() => applyTheme(next));
    const done = () => { if (over) return; over = true; root.classList.remove("vt-fade"); if (wave === w) wave = null; };
    const w = { finish() { t.skipTransition(); done(); } };
    wave = w;
    t.finished.then(done, done);
    return;
  }
  const R = farthestCorner(pt);
  if (document.startViewTransition) {
    let ring = null, over = false;
    root.classList.add("vt-wave");
    const anims = [];
    const t = document.startViewTransition(() => { applyTheme(next); ring = waveRing(pt); });
    const done = () => {
      if (over) return; over = true;
      anims.forEach((a) => { try { a.cancel(); } catch (e) { /* already gone */ } });
      if (ring) ring.remove();
      root.classList.remove("vt-wave");
      if (wave === w) wave = null;
    };
    const w = { finish() { try { t.skipTransition(); } catch (e) { /* already finished */ } done(); } };
    wave = w;
    t.ready.then(() => {
      if (over) return;
      anims.push(root.animate({ clipPath: [`circle(0px at ${pt.x}px ${pt.y}px)`, `circle(${R}px at ${pt.x}px ${pt.y}px)`] },
        { duration: WAVE_MS, easing: WAVE_EASE, pseudoElement: "::view-transition-new(root)" }));
      if (ring) anims.push(animateRing(ring, R));
    }, done);
    t.finished.then(done, done);
    return;
  }
  // Fallback (no View Transitions): a circle of the new background grows from the same point, the theme switches
  // underneath while it covers the page, then the circle fades away. No jump, no flash.
  const probe = h("div", { "data-theme": resolveMode(next.mode), "data-palette": next.palette, hidden: true });
  document.body.append(probe);
  const cs = getComputedStyle(probe);
  const bg = cs.getPropertyValue("--bg").trim(), accent = cs.getPropertyValue("--accent").trim();
  probe.remove();
  const fill = h("div", { class: "wave-fill", "aria-hidden": "true" });
  fill.style.background = bg;
  document.body.append(fill);
  const ring = waveRing(pt);
  ring.style.setProperty("--accent", accent);
  let over = false, switched = false;
  const sw = () => { if (!switched) { switched = true; applyTheme(next); } };
  const grow = fill.animate({ clipPath: [`circle(0px at ${pt.x}px ${pt.y}px)`, `circle(${R}px at ${pt.x}px ${pt.y}px)`] },
    { duration: WAVE_MS, easing: WAVE_EASE, fill: "forwards" });
  const ringAnim = animateRing(ring, R);
  const done = () => { if (over) return; over = true; grow.cancel(); ringAnim.cancel(); fill.remove(); ring.remove(); if (wave === w) wave = null; };
  const w = { finish() { sw(); done(); } };
  wave = w;
  grow.finished.then(() => {
    if (over) return;
    sw();
    fill.animate({ opacity: [1, 0] }, { duration: 260, easing: "ease-out", fill: "forwards" }).finished.then(done, done);
  }, () => {});
}
function setTheme(change, originEl) {
  const next = { ...savedTheme(), ...currentModePalette(), ...change };
  store.set("sa_theme", next.mode); store.set("sa_palette", next.palette);
  transitionTheme(next, originEl ? originOf(originEl) : null);
}
function currentModePalette() { const c = currentTheme(); return { mode: c.mode, palette: c.palette }; }
osLight.addEventListener("change", () => { if (currentTheme().mode === "system") transitionTheme(currentModePalette(), null); });   // "Tizim" follows the OS live
window.addEventListener("storage", (e) => { if (e.key === "sa_theme" || e.key === "sa_palette") transitionTheme(savedTheme(), null); });   // another tab

// While a View Transition runs, Chrome hit-tests every tap to <html> (the page is only a picture). A tap then finishes
// the running wave at once and is handed to the real control under the finger, so a second swatch starts a new wave.
let tapAfterWave = null;
document.addEventListener("pointerdown", (e) => {
  if (!wave || e.target !== document.documentElement) return;
  wave.finish();
  let el = document.elementFromPoint(e.clientX, e.clientY);
  if (!el || el === document.documentElement) {
    el = openPop && [...openPop.querySelectorAll("button")].find((b) => { const r = b.getBoundingClientRect(); return e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom; });
  }
  const target = el && el !== document.documentElement ? el.closest("button, a, [tabindex]") || el : null;
  if (!target) return;
  e.stopImmediatePropagation();               // not an "outside" tap: keep the popover open
  tapAfterWave = target;
}, true);
document.addEventListener("click", (e) => {
  if (!tapAfterWave) return;
  const t = tapAfterWave; tapAfterWave = null;
  if (e.target === t || t.contains(e.target)) return;   // the browser already delivered it
  e.stopImmediatePropagation(); e.preventDefault();
  if (t.focus) t.focus({ preventScroll: true });
  t.click();
}, true);

// The handmade picker: anchored popover on tablet/desktop, a bottom sheet on the phone.
function themeButton({ wide = false } = {}) {
  const ico = h("span", { class: "tb-ico" });
  MODES.forEach((m) => { const i = icon(m.icon); i.setAttribute("class", `m-${m.key}`); ico.append(i); });
  ico.append(h("span", { class: "tb-dot" }));
  const b = h("button", { class: `btn theme-btn${wide ? " wide" : " icon"}`, type: "button", "aria-haspopup": "dialog", "aria-expanded": "false",
    "data-popper": "1", "aria-label": "Mavzu va rang", title: "Mavzu va rang" }, ico,
    wide ? h("span", { class: "tb-text" }, "Mavzu", h("span", { class: "tb-name", text: paletteName(currentTheme().palette) })) : null);
  b.addEventListener("click", () => {
    if (openPop && openPop._owner === b) { closePop(true); return; }
    openThemePicker(b);
  });
  return b;
}
function rovingKeys(group, cols) {
  group.addEventListener("keydown", (e) => {
    const items = [...group.querySelectorAll("[role=radio]")]; const i = items.indexOf(document.activeElement);
    if (i < 0) return;
    const c = typeof cols === "function" ? cols() : cols;
    const step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: c, ArrowUp: -c, Home: -i, End: items.length - 1 - i }[e.key];
    if (step === undefined) return;
    e.preventDefault();
    const j = Math.max(0, Math.min(items.length - 1, i + step));
    items.forEach((it, k) => it.setAttribute("tabindex", k === j ? "0" : "-1"));
    items[j].focus();
  });
}
function openThemePicker(btn) {
  closePop();
  const sheet = window.matchMedia && matchMedia("(max-width: 720px)").matches;
  const now = currentTheme();
  const close = h("button", { class: "btn icon tp-close", type: "button", "aria-label": "Yopish" }, icon("close"));
  const modes = h("div", { class: "seg", role: "radiogroup", "aria-label": "Rejim" }, MODES.map((m) => {
    const ic = h("span", { class: "seg-ico" }, icon(m.icon));
    const b = h("button", { class: "seg-opt", type: "button", role: "radio", "data-mode-opt": m.key, "aria-checked": String(m.key === now.mode),
      tabindex: m.key === now.mode ? "0" : "-1" }, ic, h("span", { text: m.name }));
    b.addEventListener("click", () => setTheme({ mode: m.key }, ic));
    return b;
  }));
  const swatches = h("div", { class: "swatches", role: "radiogroup", "aria-label": "Rang" }, PALETTES.map((p) => {
    const dot = h("span", { class: "sw-dot", "data-theme": now.theme, "data-palette": p.key });
    const check = icon("check"); check.setAttribute("class", "sw-check");
    const b = h("button", { class: "sw", type: "button", role: "radio", "data-palette-opt": p.key, "aria-checked": String(p.key === now.palette),
      tabindex: p.key === now.palette ? "0" : "-1" }, dot, h("span", { class: "sw-name", text: p.name }), check);
    b.addEventListener("click", () => setTheme({ palette: p.key }, dot));
    return b;
  }));
  rovingKeys(modes, 1);
  rovingKeys(swatches, () => { const it = [...swatches.children]; const top = it[0].offsetTop; return Math.max(1, it.filter((x) => x.offsetTop === top).length); });
  const panel = h("div", { class: "theme-pop", role: "dialog", "aria-modal": sheet ? "true" : null, "aria-labelledby": "tp-title" },
    h("div", { class: "tp-head" }, h("div", {}, h("b", { id: "tp-title", text: "Mavzu" }), h("p", { text: "Rejim va rangni tanlang — saqlanib qoladi." })), close),
    h("div", { class: "tp-label", text: "Rejim" }), modes,
    h("div", { class: "tp-label", text: "Rang" }), swatches);
  const layer = h("div", { class: `theme-layer ${sheet ? "sheet" : "anchored"}`, "data-popper": "1" });
  if (sheet) { const backdrop = h("div", { class: "tp-backdrop" }); backdrop.addEventListener("click", () => closePop(true)); layer.append(backdrop); }
  layer.append(panel);
  document.body.append(layer);
  const place = () => {
    if (sheet || !btn.isConnected) return;
    const r = btn.getBoundingClientRect(), pw = panel.offsetWidth, ph = panel.offsetHeight, vw = document.documentElement.clientWidth;
    let top = r.bottom + 8;
    if (top + ph > window.innerHeight - 8) top = Math.max(8, r.top - ph - 8);
    let left = r.right - pw;
    if (left < 8) left = r.left;
    left = Math.max(8, Math.min(left, vw - pw - 8));
    panel.style.top = `${Math.round(top)}px`; panel.style.left = `${Math.round(left)}px`;
  };
  place();
  window.addEventListener("resize", place); window.addEventListener("scroll", place, { passive: true });
  close.addEventListener("click", () => closePop(true));
  panel.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.stopPropagation(); closePop(true); return; }
    if (e.key === "Tab" && sheet) {          // the sheet is modal: Tab cycles inside it
      const f = [close, modes.querySelector('[tabindex="0"]'), swatches.querySelector('[tabindex="0"]')];
      const i = f.indexOf(document.activeElement);
      if (i >= 0) { e.preventDefault(); f[(i + (e.shiftKey ? f.length - 1 : 1)) % f.length].focus(); }
    }
  });
  panel.addEventListener("focusout", (e) => { if (!sheet && e.relatedTarget && !panel.contains(e.relatedTarget) && e.relatedTarget !== btn) closePop(); });
  layer._owner = btn;
  layer._onClose = (returnFocus) => {
    window.removeEventListener("resize", place); window.removeEventListener("scroll", place);
    btn.setAttribute("aria-expanded", "false");
    if (returnFocus && btn.isConnected) btn.focus();
  };
  openPop = layer; btn.setAttribute("aria-expanded", "true");
  (swatches.querySelector('[aria-checked="true"]') || swatches.firstChild).focus({ preventScroll: true });
}

// ---------------------------------------------------------------- tooltip
function showTip(evt, head, rows) {
  $tip.replaceChildren(h("div", { class: "t-head", text: head }),
    ...rows.map((r) => h("div", { class: "t-row" }, h("span", { class: `key ${r.cls || ""}` }), h("b", { text: r.value }), h("span", { text: r.label }))));
  $tip.hidden = false;
  const pad = 14, w = $tip.offsetWidth, hgt = $tip.offsetHeight;
  let x = evt.clientX + pad, y = evt.clientY - hgt - pad;
  if (x + w > window.innerWidth - 8) x = evt.clientX - w - pad;
  if (y < 8) y = evt.clientY + pad;
  $tip.style.left = `${Math.max(8, x)}px`; $tip.style.top = `${y}px`;
}
function hideTip() { $tip.hidden = true; }
window.addEventListener("scroll", hideTip, { passive: true });

// ---------------------------------------------------------------- handmade controls
let openPop = null;
let silentRefresh = false;
function closePop(returnFocus = false) { if (!openPop) return; const p = openPop; openPop = null; p.remove(); if (p._onClose) p._onClose(returnFocus); }
document.addEventListener("pointerdown", (e) => { if (openPop && !openPop.contains(e.target) && !e.target.closest("[data-popper]")) closePop(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePop(true); });

function Select({ label, options, value, onChange, align = "right" }) {
  const wrap = h("div", { class: "dd" });
  const current = () => options.find((o) => o.value === value) || options[0];
  const btn = h("button", { class: "btn", type: "button", "aria-haspopup": "listbox", "aria-expanded": "false", "data-popper": "1", "aria-label": label },
    h("span", { text: current().label }), icon("chevron"));
  btn.addEventListener("click", () => {
    if (openPop && openPop.parentNode === wrap) { closePop(); btn.setAttribute("aria-expanded", "false"); return; }
    closePop();
    const list = h("div", { class: `pop ${align === "left" ? "left" : ""}`, role: "listbox", "aria-label": label });
    options.forEach((o) => {
      const check = icon("check"); check.setAttribute("class", "check");
      const opt = h("button", { class: "opt", type: "button", role: "option", "aria-selected": String(o.value === value) },
        h("span", { text: o.label }), check);
      opt.addEventListener("click", () => { value = o.value; btn.firstChild.textContent = o.label; closePop(); btn.setAttribute("aria-expanded", "false"); onChange(o.value); btn.focus(); });
      list.append(opt);
    });
    list.addEventListener("keydown", (e) => {
      const items = [...list.querySelectorAll(".opt")]; const i = items.indexOf(document.activeElement);
      if (e.key === "ArrowDown") { e.preventDefault(); items[Math.min(items.length - 1, i + 1)].focus(); }
      if (e.key === "ArrowUp") { e.preventDefault(); items[Math.max(0, i - 1)].focus(); }
    });
    wrap.append(list); openPop = list; btn.setAttribute("aria-expanded", "true");
    (list.querySelector('[aria-selected="true"]') || list.firstChild).focus();
  });
  wrap.append(btn);
  return wrap;
}

function Checkbox({ label, checked, cls = "", onChange }) {
  const box = h("span", { class: "box" }, icon("check"));
  const el = h("button", { class: `cbx ${cls}`, type: "button", role: "checkbox", "aria-checked": String(checked) }, box, h("span", { text: label }));
  el.addEventListener("click", () => { checked = !checked; el.setAttribute("aria-checked", String(checked)); onChange(checked); });
  return el;
}

const PRESETS = [{ days: 7, label: "Oxirgi 7 kun" }, { days: 30, label: "Oxirgi 30 kun" }, { days: 90, label: "Oxirgi 90 kun" }, { days: 365, label: "Oxirgi 1 yil" }];
function rangeLabel(r) {
  if (r.preset) return PRESETS.find((p) => p.days === r.preset).label;
  return `${dayLabel(r.start)} — ${dayLabel(r.end)}`;
}
function DateRange({ range, onChange }) {
  const wrap = h("div", { class: "dd grow" });
  const btn = h("button", { class: "btn", type: "button", "aria-haspopup": "dialog", "data-popper": "1", "aria-label": "Sana oralig'i" },
    icon("calendar"), h("span", { text: rangeLabel(range) }), icon("chevron"));
  function presetsView(pop) {
    pop.replaceChildren();
    PRESETS.forEach((p) => {
      const opt = h("button", { class: "opt", type: "button", role: "option", "aria-selected": String(range.preset === p.days) }, h("span", { text: p.label }));
      const c = icon("check"); c.setAttribute("class", "check"); opt.append(c);
      opt.addEventListener("click", () => { closePop(); onChange({ preset: p.days, ...presetDates(p.days) }); });
      pop.append(opt);
    });
    const custom = h("button", { class: "opt", type: "button", "aria-selected": String(!range.preset) }, h("span", { text: "Boshqa oraliq…" }));
    const c = icon("check"); c.setAttribute("class", "check"); custom.append(c);
    custom.addEventListener("click", () => calendarView(pop));
    pop.append(h("div", { class: "pop-foot" }, custom));
  }
  function calendarView(pop) {
    const today = isoDay(new Date());
    let start = range.preset ? null : range.start, end = range.preset ? null : range.end;
    let month = (end || today).slice(0, 7);
    const grid = h("div", { class: "cal-grid" });
    const title = h("span");
    const hint = h("span", { text: "Boshlanish kunini tanlang" });
    const apply = h("button", { class: "btn primary", type: "button", disabled: true }, "Qo'llash");
    apply.addEventListener("click", () => { closePop(); onChange({ preset: null, start, end }); });
    function draw() {
      const [y, m] = month.split("-").map(Number);
      title.textContent = `${MONTHS[m - 1][0].toUpperCase() + MONTHS[m - 1].slice(1)} ${y}`;
      grid.replaceChildren(...WEEKDAYS.map((w) => h("div", { class: "wd", text: w })));
      const first = new Date(Date.UTC(y, m - 1, 1)); const lead = (first.getUTCDay() + 6) % 7;
      const daysIn = new Date(Date.UTC(y, m, 0)).getUTCDate();
      for (let i = 0; i < lead; i++) grid.append(h("button", { class: "day out", type: "button", tabindex: "-1", "aria-hidden": "true" }));
      for (let d = 1; d <= daysIn; d++) {
        const iso = `${month}-${String(d).padStart(2, "0")}`;
        let cls = "day";
        if (start && end && iso > start && iso < end) cls += " in-range";
        if (iso === start || iso === end) cls += " edge";
        const b = h("button", { class: cls, type: "button", text: String(d), disabled: iso > today, "aria-label": dayLong(iso), "aria-pressed": String(iso === start || iso === end) });
        b.addEventListener("click", () => {
          if (!start || (start && end)) { start = iso; end = null; hint.textContent = "Tugash kunini tanlang"; }
          else if (iso < start) { end = start; start = iso; }
          else { end = iso; }
          if (start && end) hint.textContent = `${dayLabel(start)} — ${dayLabel(end)}`;
          apply.disabled = !(start && end);
          draw();
        });
        grid.append(b);
      }
    }
    const prev = h("button", { class: "btn icon", type: "button", "aria-label": "Oldingi oy" }, icon("left"));
    const next = h("button", { class: "btn icon", type: "button", "aria-label": "Keyingi oy" }, icon("right"));
    const shift = (n) => { const [y, m] = month.split("-").map(Number); const d = new Date(Date.UTC(y, m - 1 + n, 1)); month = d.toISOString().slice(0, 7); draw(); };
    prev.addEventListener("click", () => shift(-1)); next.addEventListener("click", () => shift(1));
    pop.replaceChildren(h("div", { class: "cal" }, h("div", { class: "cal-head" }, prev, title, next), grid, h("div", { class: "cal-foot" }, hint, apply)));
    draw();
  }
  btn.addEventListener("click", () => {
    if (openPop && openPop.parentNode === wrap) { closePop(); return; }
    closePop();
    const pop = h("div", { class: "pop", role: "dialog", "aria-label": "Sana oralig'i" });
    presetsView(pop); wrap.append(pop); openPop = pop;
    (pop.querySelector('[aria-selected="true"]') || pop.querySelector("button")).focus();
  });
  wrap.append(btn);
  return wrap;
}
function presetDates(days) { const end = isoDay(new Date()); return { start: addDays(end, -(days - 1)), end }; }

// ---------------------------------------------------------------- charts
function niceMax(v) { if (v <= 0) return 1; const p = Math.pow(10, Math.floor(Math.log10(v))); const n = v / p; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p; }

function lineChart(container, days, series, { format = num, height = 260 } = {}) {
  const shown = series.filter((sr) => sr.values.some((v) => v !== null && v !== undefined));
  if (!shown.length) {
    container.replaceChildren(h("div", { class: "chart-empty", text: "Bu oraliq uchun ma'lumot hali yo'q. Statistika har kuni yig'iladi — tarix shu yerda paydo bo'ladi." }));
    return;
  }
  const chart = h("div", { class: "chart" });
  container.replaceChildren(chart);
  const draw = () => {
    const W = Math.max(280, chart.clientWidth), H = height, L = 52, R = 70, T = 12, B = 28;
    const all = shown.flatMap((sr) => sr.values.filter((v) => v !== null && v !== undefined));
    const max = niceMax(Math.max(...all, 0)), min = Math.min(0, ...all);
    const x = (i) => L + (days.length === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (days.length - 1));
    const y = (v) => T + (H - T - B) * (1 - (v - min) / (max - min || 1));
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": shown.map((sr) => sr.label).join(", ") });
    for (let k = 0; k <= 4; k++) {
      const v = min + ((max - min) * k) / 4;
      svg.append(s("line", { class: "grid-line", x1: L, x2: W - R, y1: y(v), y2: y(v) }));
      svg.append(s("text", { class: "axis-text", x: L - 8, y: y(v) + 4, "text-anchor": "end" }, format(v)));
    }
    const ticks = Math.min(days.length, Math.max(2, Math.floor((W - L - R) / 90)));
    for (let k = 0; k < ticks; k++) {
      const i = Math.round((k * (days.length - 1)) / Math.max(1, ticks - 1));
      svg.append(s("text", { class: "axis-text", x: x(i), y: H - 6, "text-anchor": k === 0 ? "start" : k === ticks - 1 ? "end" : "middle" }, dayLabel(days[i])));
    }
    const labels = [];
    shown.forEach((sr) => {
      let d = "", pen = false;
      sr.values.forEach((v, i) => {
        if (v === null || v === undefined) { pen = false; return; }
        d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true;
      });
      svg.append(s("path", { class: "line", d, stroke: sr.color }));
      const pts = sr.values.map((v, i) => [v, i]).filter(([v]) => v !== null && v !== undefined);
      if (pts.length === 1) svg.append(s("circle", { cx: x(pts[0][1]), cy: y(pts[0][0]), r: 4, fill: sr.color, stroke: "var(--surface-1)", "stroke-width": 2 }));
      const last = pts[pts.length - 1];
      if (last) labels.push({ y: y(last[0]), text: sr.label, x: x(last[1]) });
    });
    labels.sort((a, b) => a.y - b.y);
    for (let i = 1; i < labels.length; i++) if (labels[i].y - labels[i - 1].y < 14) labels[i].y = labels[i - 1].y + 14;
    labels.forEach((l) => svg.append(s("text", { class: "end-label", x: l.x + 8, y: l.y + 4 }, l.text)));
    const cross = s("line", { class: "cross", y1: T, y2: H - B, visibility: "hidden" });
    const dots = shown.map((sr) => s("circle", { r: 4.5, fill: sr.color, stroke: "var(--surface-1)", "stroke-width": 2, visibility: "hidden" }));
    svg.append(cross, ...dots);
    const hit = s("rect", { x: L, y: T, width: W - L - R, height: H - T - B, fill: "transparent", tabindex: "0" });
    const at = (i, evt) => {
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
      shown.forEach((sr, k) => { const v = sr.values[i]; if (v === null || v === undefined) dots[k].setAttribute("visibility", "hidden"); else { dots[k].setAttribute("cx", x(i)); dots[k].setAttribute("cy", y(v)); dots[k].setAttribute("visibility", "visible"); } });
      showTip(evt, dayLong(days[i]), shown.map((sr) => ({ cls: sr.cls, value: format(sr.values[i]), label: sr.label })));
    };
    hit.addEventListener("pointermove", (e) => {
      const box = svg.getBoundingClientRect(); const px = ((e.clientX - box.left) / box.width) * W;
      const i = Math.max(0, Math.min(days.length - 1, Math.round(((px - L) / (W - L - R)) * (days.length - 1))));
      at(i, e);
    });
    let kb = days.length - 1;
    hit.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      kb = Math.max(0, Math.min(days.length - 1, kb + (e.key === "ArrowRight" ? 1 : -1)));
      const box = svg.getBoundingClientRect();
      at(kb, { clientX: box.left + (x(kb) / W) * box.width, clientY: box.top + 20 });
    });
    const leave = () => { cross.setAttribute("visibility", "hidden"); dots.forEach((d) => d.setAttribute("visibility", "hidden")); hideTip(); };
    hit.addEventListener("pointerleave", leave); hit.addEventListener("blur", leave);
    svg.append(hit);
    chart.replaceChildren(svg);
  };
  draw();
  new ResizeObserver(() => draw()).observe(chart);
}

function barChart(container, items, { color = "var(--accent)", format = num, height = 200, label = "" } = {}) {
  if (!items.length) { container.replaceChildren(h("div", { class: "chart-empty", text: "Hali yetarli video yo'q." })); return; }
  const chart = h("div", { class: "chart" });
  container.replaceChildren(chart);
  const draw = () => {
    const W = Math.max(260, chart.clientWidth), H = height, L = 8, R = 8, T = 18, B = 26;
    const max = niceMax(Math.max(...items.map((i) => i.value), 1));
    const bw = (W - L - R) / items.length, gap = Math.min(10, bw * 0.3);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": label });
    svg.append(s("line", { class: "grid-line", x1: L, x2: W - R, y1: H - B, y2: H - B }));
    const best = Math.max(...items.map((i) => i.value));
    items.forEach((it, k) => {
      const bh = Math.max(2, ((H - T - B) * it.value) / max);
      const x = L + k * bw + gap / 2, y0 = H - B - bh, w = bw - gap, r = Math.min(4, w / 2);
      const path = `M${x},${H - B} V${y0 + r} Q${x},${y0} ${x + r},${y0} H${x + w - r} Q${x + w},${y0} ${x + w},${y0 + r} V${H - B} Z`;
      const bar = s("path", { class: "bar", d: path, fill: color, tabindex: "0" });
      const tip = (e) => { bar.classList.add("hot"); showTip(e, it.label, [{ cls: "", value: format(it.value), label: it.sub || "" }]); };
      bar.addEventListener("pointermove", tip);
      bar.addEventListener("focus", () => { const b = bar.getBoundingClientRect(); tip({ clientX: b.left + b.width / 2, clientY: b.top }); });
      const off = () => { bar.classList.remove("hot"); hideTip(); };
      bar.addEventListener("pointerleave", off); bar.addEventListener("blur", off);
      svg.append(bar);
      if (it.value === best) svg.append(s("text", { class: "end-label", x: x + w / 2, y: y0 - 6, "text-anchor": "middle" }, format(it.value)));
      if (items.length <= 12 || k % Math.ceil(items.length / 12) === 0)
        svg.append(s("text", { class: "axis-text", x: x + w / 2, y: H - 8, "text-anchor": "middle" }, it.short || it.label));
    });
    chart.replaceChildren(svg);
  };
  draw();
  new ResizeObserver(() => draw()).observe(chart);
}

function tableView(days, series, format) {
  const head = h("tr", {}, h("th", { text: "Sana" }), ...series.map((sr) => h("th", { text: sr.label })));
  const rows = days.map((d, i) => h("tr", {}, h("td", { text: dayLong(d) }), ...series.map((sr) => h("td", { text: format(sr.values[i]) }))));
  return h("div", { class: "table-scroll" }, h("table", { class: "data-table" }, h("thead", {}, head), h("tbody", {}, rows.reverse())));
}

// ---------------------------------------------------------------- state + shell
const state = {
  range: JSON.parse(localStorage.getItem("sa_range") || "null") || { preset: 30, ...presetDates(30) },
  metric: "views",
  show: { youtube: true, instagram: true, combined: false },
  sort: "posted",
  status: null,
};
if (state.range.preset) Object.assign(state.range, presetDates(state.range.preset));
function rangeDays() { return Math.round((new Date(state.range.end) - new Date(state.range.start)) / 864e5) + 1; }

const ROUTES = [
  { key: "overview", hash: "#/", label: "Umumiy", icon: "overview" },
  { key: "videos", hash: "#/videos", label: "Videolar", icon: "videos" },
  { key: "insights", hash: "#/insights", label: "Tahlil", icon: "insights" },
  { key: "pipeline", hash: "#/pipeline", label: "Jarayon", icon: "pipeline" },
  { key: "skills", hash: "#/skills", label: "Ko'nikmalar", icon: "skills" },
  { key: "repo", hash: "#/repo", label: "GitHub", icon: "github" },
  { key: "settings", hash: "#/settings", label: "Sozlamalar", icon: "settings" },
];
function brand() {
  const mark = h("div", { class: "brand-mark" });
  const svg = s("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2.6", "stroke-linecap": "round", "stroke-linejoin": "round" });
  svg.append(s("path", { d: "M4 17 L10 11 L14 14 L20 7" })); mark.append(svg);
  return h("div", { class: "brand" }, mark, h("div", {}, "Social Automation", h("small", { text: "Reels · Buffer" })));
}
function shell(active, title, sub, controls, body) {
  const nav = (cls) => h("nav", { class: cls, "aria-label": "Bo'limlar" },
    ROUTES.map((r) => h("a", { href: r.hash, "aria-current": r.key === active ? "page" : null }, icon(r.icon), h("span", { text: r.label }))));
  const logout = h("button", { class: "btn", type: "button" }, icon("logout"), "Chiqish");
  logout.addEventListener("click", async () => { await api("/api/logout", { method: "POST" }).catch(() => {}); renderLogin(); });
  const side = h("aside", { class: "side" }, brand(), nav("nav"), h("div", { class: "side-foot" }, themeButton({ wide: true }), logout));
  const mobileBrand = h("div", { class: "mobile-brand", style: "justify-content:space-between" }, brand(), themeButton());
  const main = h("main", { class: "main" }, mobileBrand,
    h("div", { class: "topbar" }, h("div", {}, h("h1", { text: title }), sub ? h("div", { class: "sub" }, sub) : null), h("div", { class: "controls" }, controls)),
    body);
  const keep = silentRefresh ? window.scrollY : 0;
  $app.replaceChildren(h("div", { class: "shell" }, side, main), nav("bottom-nav"));
  window.scrollTo(0, keep);
}
// A platform has numbers when it is connected directly or (fallback) its posts are read through Buffer.
function hasStats(p) { return p.connected || p.source === "buffer"; }
function updatedNode(st) {
  const ms = Object.values(st.platforms).filter(hasStats).map((p) => p.updated_minutes).filter((m) => m !== null);
  const m = ms.length ? Math.max(...ms) : null;
  const anyConnected = Object.values(st.platforms).some(hasStats);
  if (!anyConnected) return h("span", { class: "updated", text: "Hisoblar hali ulanmagan" });
  return h("span", { class: "updated" }, h("span", { class: "pulse" }), agoText(m));
}
function refreshButton(after) {
  const b = h("button", { class: "btn icon", type: "button", "aria-label": "Hozir yangilash", title: "Hozir yangilash" }, icon("refresh"));
  b.addEventListener("click", async () => { b.disabled = true; try { await api("/api/refresh", { method: "POST" }); } catch (e) { /* shown via status */ } b.disabled = false; after(); });
  return b;
}
function banners(st) {
  const out = [];
  if (st.dry_run) out.push(h("div", { class: "banner" }, h("span", { text: "🧪" }), h("div", {}, h("b", { text: "Sinov rejimi yoqilgan. " }), "Buffer qoralamalari haqiqatda yaratilmaydi — faqat yozib qo'yiladi. Bot hech qachon o'zi joylamaydi yoki rejalashtirmaydi: Buffer'da qoralama tayyor bo'lgach, tasdiqlab rejalashtirish sizda.")));
  const viaBuffer = Object.entries(st.platforms).filter(([, info]) => !info.connected && info.source === "buffer").map(([p]) => PF[p].name);
  if (viaBuffer.length) out.push(h("div", { class: "banner" }, h("span", { text: "📊" }), h("div", {}, h("b", { text: `${viaBuffer.join(" va ")} statistikasi Buffer orqali. ` }), "Faqat Buffer'dan chiqqan postlar: ko'rish, layk, izoh, ulashish, saqlash, qamrov va o'rtacha tomosha. Buffer ularni kuniga taxminan bir marta yangilaydi. Obunachilar soni, kunlik grafik va retention uchun hisobni to'g'ridan-to'g'ri ulang (Sozlamalar).")));
  for (const [p, info] of Object.entries(st.platforms)) if (info.problem === "auth") out.push(h("div", { class: "banner" }, h("span", { text: "🔑" }), h("div", {}, h("b", { text: `${PF[p].name} ruxsati tugagan. ` }), "Statistika eski ko'rinishda qoldi. Qayta ulash: ", h("code", { text: `.venv/bin/python -m socialauto ${p === "youtube" ? "youtube-auth" : "instagram-connect"}` }))));
  return out;
}

// ---------------------------------------------------------------- connect state
const CONNECT_STEPS = {
  youtube: ["Google Cloud'da loyiha oching va «YouTube Data API v3» hamda «YouTube Analytics API» ni yoqing.", "OAuth mijozini (Desktop app) yarating va JSON faylni secrets/youtube_client_secret.json ga saqlang.", ["Terminalda ishga tushiring: ", "code:.venv/bin/python -m socialauto youtube-auth"], "Brauzerda kanalingizni tanlab, ruxsat bering. Tamom — statistika avtomatik yig'iladi."],
  instagram: ["Instagram hisobingizni Business yoki Creator turiga o'tkazing va Facebook sahifangizga bog'lang.", "developers.facebook.com da ilova oching; App ID va App Secret ni .env fayliga yozing.", "Graph API Explorer'da kerakli ruxsatlar bilan token oling.", ["Terminalda: ", "code:.venv/bin/python -m socialauto instagram-connect", " — tokenni qo'ying."]],
};
function connectCard(p, connected) {
  const steps = h("ol", { class: "steps" }, CONNECT_STEPS[p].map((st) => h("li", {}, (Array.isArray(st) ? st : [st]).map((part) => part.startsWith("code:") ? h("code", { text: part.slice(5) }) : part))));
  return h("div", { class: "card" }, h("div", { class: `glyph ${PF[p].cls}` }, icon(PF[p].cls)),
    h("h2", { text: connected ? `${PF[p].name} ulangan` : `${PF[p].name} ni ulang` }),
    connected ? h("p", { class: "hint", text: "Birinchi statistika yig'ilmoqda — bir necha daqiqada shu yerda ko'rinadi." })
      : h("p", { class: "hint", text: "Ulanmaguncha bu yerda hech qanday raqam ko'rsatilmaydi. To'liq yo'riqnoma: docs/OWNER_TODO.md" }),
    connected ? h("span", { class: "ok-badge" }, icon("check"), "Ulangan") : steps);
}

// ---------------------------------------------------------------- overview
function growthChips(g, suffix = "") {
  const chips = [["kun", g.day], ["hafta", g.week], ["oy", g.month]].map(([lbl, v]) => {
    const t = signed(v);
    return h("span", { class: "chip" }, lbl + ": ", t === null ? h("span", { text: "—" }) : h("span", { class: v >= 0 ? "up" : "down", text: t + suffix }));
  });
  return h("div", { class: "chips" }, chips);
}
function kpi(label, keyCls, value, split, chips) {
  return h("div", { class: "card kpi" }, h("div", { class: "label" }, keyCls ? h("span", { class: `dot ${keyCls}` }) : null, label), h("div", { class: "value", text: value }),
    split ? h("div", { class: "split" }, split) : null, chips || null);
}

async function renderOverview() {
  const days = rangeDays();
  const [ov, sr] = await Promise.all([api(`/api/overview?days=${days}`), api(`/api/series?metric=${state.metric}&start=${state.range.start}&end=${state.range.end}`)]);
  const st = ov.status; state.status = st;
  const controls = [updatedNode(st), DateRange({ range: state.range, onChange: (r) => { state.range = r; localStorage.setItem("sa_range", JSON.stringify(r)); renderOverview(); } }), refreshButton(renderOverview)];
  const body = h("div", {}, banners(st));
  const c = ov.combined, P = ov.platforms;
  const conn = { youtube: st.platforms.youtube.connected, instagram: st.platforms.instagram.connected };
  if (!c) {
    body.append(h("div", { class: "connect" }, connectCard("youtube", conn.youtube), connectCard("instagram", conn.instagram)));
    shell("overview", "Umumiy ko'rinish", "Ikkala platforma bo'yicha jonli statistika", controls, body);
    return;
  }
  const per = (p) => P[p] ? h("span", {}, h("span", { class: `key ${PF[p].cls}` }), " ", h("b", { text: num(P[p].followers) })) : null;
  body.append(h("div", { class: "grid kpis" },
    kpi("Obunachilar (jami)", null, num(c.followers), [per("youtube"), per("instagram")], growthChips(c.followers_growth)),
    kpi(`Ko'rishlar (${days} kun)`, null, num(c.views_period), [P.youtube ? h("span", {}, h("span", { class: "key yt" }), " ", h("b", { text: num(P.youtube.views_period) })) : null, P.instagram ? h("span", {}, h("span", { class: "key ig" }), " ", h("b", { text: num(P.instagram.views_period) })) : null], growthChips(c.views_growth)),
    kpi("Faollik darajasi", null, pct(c.engagement_rate), [h("span", { text: "(layk + izoh + ulashish + saqlash) / ko'rish" })]),
    kpi(`Qamrov (${days} kun)`, "ig", num(c.reach_period), [h("span", { text: "Instagram'da videoni ko'rgan noyob hisoblar" })], null)));
  const missing = ["youtube", "instagram"].filter((p) => !P[p]);
  // chart
  const chartBox = h("div");
  const tableBox = h("div", { hidden: true });
  const metricSel = Select({ label: "Ko'rsatkich", value: state.metric, options: [
    { value: "views", label: "Ko'rishlar" }, { value: "followers", label: "Obunachilar" }, { value: "engagement", label: "Faollik %" }, { value: "reach", label: "Qamrov (Instagram)" }],
    onChange: (v) => { state.metric = v; renderOverview(); } });
  const fmt = state.metric === "engagement" ? pct : num;
  const series = [
    { key: "youtube", label: "YouTube", cls: "yt", color: "var(--yt)", values: sr.youtube },
    { key: "instagram", label: "Instagram", cls: "ig", color: "var(--ig)", values: sr.instagram },
    { key: "combined", label: "Jami", cls: "all", color: "var(--combined)", values: sr.combined },
  ];
  const visible = () => series.filter((x) => state.show[x.key]);
  const redraw = () => { lineChart(chartBox, sr.days, visible(), { format: fmt }); tableBox.replaceChildren(tableView(sr.days, visible(), fmt)); };
  const toggles = h("div", { class: "legend" }, series.map((x) => Checkbox({ label: x.label, checked: state.show[x.key], cls: x.cls, onChange: (v) => { state.show[x.key] = v; redraw(); } })));
  const tableBtn = h("button", { class: "btn", type: "button", "aria-pressed": "false" }, "Jadval");
  tableBtn.addEventListener("click", () => { const on = tableBox.hidden; tableBox.hidden = !on; chartBox.hidden = on; tableBtn.setAttribute("aria-pressed", String(on)); tableBtn.textContent = on ? "Grafik" : "Jadval"; });
  const chartCard = h("div", { class: "card" }, h("div", { class: "card-head" }, h("div", {}, h("h2", { text: "Vaqt bo'yicha" }), h("p", { class: "hint", text: `${dayLong(state.range.start)} — ${dayLong(state.range.end)}` })), h("div", { class: "controls" }, metricSel, tableBtn)), chartBox, tableBox, toggles);
  // comparison
  const ins = await api(`/api/insights?days=${days}`);
  body.append(h("div", { class: "grid two section-gap" }, chartCard, comparisonCard(ins.comparison, days)));
  if (missing.length) body.append(h("div", { class: "connect section-gap" }, missing.map((p) => connectCard(p, conn[p]))));
  shell("overview", "Umumiy ko'rinish", "Ikkala platforma bo'yicha jonli statistika", controls, body);
  redraw();
}

function comparisonCard(cmp, days) {
  const rows = [["Ko'rishlar", "views", num], ["Faollik (harakatlar)", "interactions", num], ["Yangi obunachilar", "followers_gained", signed], ["Videolar soni", "videos", num], ["O'rtacha ko'rish / video", "avg_views_per_video", num], ["O'rtacha tomosha", "avg_view_seconds", secs]];
  const card = h("div", { class: "card" }, h("h2", { text: "YouTube va Instagram" }), h("p", { class: "hint", text: `Oxirgi ${days} kun, yonma-yon. Har qator o'z o'lchovida.` }));
  rows.forEach(([name, key, f]) => {
    const vals = { youtube: cmp.youtube ? cmp.youtube[key] : null, instagram: cmp.instagram ? cmp.instagram[key] : null };
    const max = Math.max(Math.abs(vals.youtube || 0), Math.abs(vals.instagram || 0), 1);
    card.append(h("div", { class: "cmp-row" }, h("div", { class: "name", text: name }), h("div", { class: "cmp-bars" },
      ["youtube", "instagram"].map((p) => h("div", { class: "cmp-bar", title: PF[p].name },
        h("div", { class: "cmp-track", role: "img", "aria-label": `${PF[p].name}: ${f(vals[p]) || "—"}` }, h("div", { class: `cmp-fill ${PF[p].cls}`, style: `width:${vals[p] === null ? 0 : Math.max(2, (100 * Math.abs(vals[p])) / max)}%` })),
        h("div", { class: "v", text: f(vals[p]) || "—" }))))));
  });
  card.append(h("div", { class: "legend" }, h("span", {}, h("span", { class: "key yt" }), "YouTube"), h("span", {}, h("span", { class: "key ig" }), "Instagram")));
  return card;
}

// ---------------------------------------------------------------- videos
function pfDots(v) { return h("span", { class: "pf" }, v.youtube ? h("span", { class: "dot yt", title: "YouTube" }) : null, v.instagram ? h("span", { class: "dot ig", title: "Instagram" }) : null); }
function thumbImg(src, cls = "thumb") { return src ? h("img", { class: cls, src, alt: "", loading: "lazy" }) : h("div", { class: cls }); }

async function renderVideos() {
  const data = await api("/api/videos");
  const st = state.status || (await api("/api/status"));
  let q = "", platform = "all";
  const tableBox = h("div");
  const SORTS = { posted: ["Eng yangi", (a, b) => (b.posted_at || "").localeCompare(a.posted_at || "")], views: ["Ko'p ko'rilgan", (a, b) => b.total_views - a.total_views], likes: ["Ko'p layk", (a, b) => b.total_likes - a.total_likes], comments: ["Ko'p izoh", (a, b) => b.total_comments - a.total_comments] };
  const draw = () => {
    let rows = data.videos.filter((v) => (!q || v.title.toLowerCase().includes(q)) && (platform === "all" || v[platform]));
    rows = rows.slice().sort(SORTS[state.sort][1]);
    if (!data.videos.length) {
      tableBox.replaceChildren(h("div", { class: "chart-empty", text: Object.values(st.platforms).some(hasStats) ? "Videolar statistikasi yig'ilmoqda…" : "Hisoblar ulangach, har bir video statistikasi shu yerda ko'rinadi. Hech qanday soxta raqam ko'rsatilmaydi." }));
      return;
    }
    if (!rows.length) { tableBox.replaceChildren(h("div", { class: "chart-empty", text: "Hech narsa topilmadi." })); return; }
    const go = (v) => { location.hash = `#/video/${v.key}`; };
    const head = h("tr", {}, ["Video", "Ko'rish", "Layk", "Izoh", "Ulashish", "Saqlash", "O'rt. tomosha"].map((t) => h("th", { text: t })));
    const body = rows.map((v) => {
      const avg = (v.youtube && v.youtube.avg_view_seconds) || (v.instagram && v.instagram.avg_view_seconds);
      const tr = h("tr", { tabindex: "0" },
        h("td", {}, h("div", { class: "vcell" }, thumbImg(v.thumb), h("div", { style: "min-width:0" }, h("div", { class: "vtitle", text: v.title }), h("div", { class: "vmeta" }, pfDots(v), " ", postedLabel(v.posted_at))))),
        h("td", { text: num(v.total_views) }), h("td", { text: num(v.total_likes) }), h("td", { text: num(v.total_comments) }), h("td", { text: num(v.total_shares) }), h("td", { text: num(v.total_saves) }), h("td", { text: secs(avg) }));
      tr.addEventListener("click", () => go(v)); tr.addEventListener("keydown", (e) => { if (e.key === "Enter") go(v); });
      return tr;
    });
    const cards = rows.map((v) => {
      const b = h("button", { class: "vcard", type: "button" }, thumbImg(v.thumb), h("div", { style: "min-width:0" }, h("div", { class: "vtitle", text: v.title }), h("div", { class: "vmeta" }, pfDots(v), " ", postedLabel(v.posted_at)),
        h("div", { class: "nums" }, h("span", {}, h("b", { text: num(v.total_views) }), " ko'rish"), h("span", {}, h("b", { text: num(v.total_likes) }), " layk"), h("span", {}, h("b", { text: num(v.total_comments) }), " izoh"))));
      b.addEventListener("click", () => go(v));
      return b;
    });
    tableBox.replaceChildren(h("div", { class: "vtable-wrap table-scroll", style: "max-height:none" }, h("table", { class: "vtable" }, h("thead", {}, head), h("tbody", {}, body))), h("div", { class: "vcards" }, cards));
  };
  const search = h("input", { class: "search", type: "search", placeholder: "Sarlavha bo'yicha qidirish", "aria-label": "Qidirish" });
  search.addEventListener("input", () => { q = search.value.trim().toLowerCase(); draw(); });
  const sortSel = Select({ label: "Saralash", value: state.sort, align: "left", options: Object.entries(SORTS).map(([k, v]) => ({ value: k, label: v[0] })), onChange: (v) => { state.sort = v; draw(); } });
  const pfSel = Select({ label: "Platforma", value: "all", align: "left", options: [{ value: "all", label: "Ikkala platforma" }, { value: "youtube", label: "Faqat YouTube" }, { value: "instagram", label: "Faqat Instagram" }], onChange: (v) => { platform = v; draw(); } });
  const card = h("div", { class: "card" }, h("div", { class: "toolbar" }, search, sortSel, pfSel), tableBox);
  shell("videos", "Videolar", `${data.videos.length} ta video · YouTube va Instagram birga`, [updatedNode(st), refreshButton(renderVideos)], h("div", {}, banners(st), card));
  draw();
}

async function renderVideo(key) {
  let v;
  try { v = await api(`/api/videos/${encodeURIComponent(key)}`); } catch (e) { if (e.status === 404) { location.hash = "#/videos"; return; } throw e; }
  const st = state.status || (await api("/api/status"));
  const col = (p) => {
    const d = v[p];
    if (!d) return h("div", { class: "pcol" }, h("h3", {}, h("span", { class: `dot ${PF[p].cls}` }), PF[p].name), h("p", { class: "hint", text: "Bu video bu platformada yo'q." }));
    const items = [["Ko'rish", num(d.views)], ["Layk", num(d.likes)], ["Izoh", num(d.comments)], ["Ulashish", num(d.shares)], ["Saqlash", num(d.saves)], ["Qamrov", num(d.reach)], ["Tomosha vaqti", d.watch_minutes === null || d.watch_minutes === undefined ? "—" : `${num(d.watch_minutes)} daq`], ["O'rtacha tomosha", secs(d.avg_view_seconds)]];
    if (p === "youtube") items.push(["O'rtacha ko'rilgan qism", pct(d.avg_view_pct)]);
    return h("div", { class: "pcol" }, h("h3", {}, h("span", { class: `dot ${PF[p].cls}` }), PF[p].name),
      h("div", { class: "stat-list" }, items.map(([a, b]) => h("div", {}, h("span", { text: a }), h("b", { text: b })))),
      d.permalink ? h("a", { class: "ext", href: d.permalink, target: "_blank", rel: "noopener noreferrer" }, icon("ext"), `${PF[p].name}da ochish`) : null);
  };
  const histBox = h("div");
  const retBox = h("div");
  const body = h("div", {}, h("a", { class: "back", href: "#/videos" }, icon("left"), "Videolar"),
    h("div", { class: "detail-head" }, h("div", { class: "card" }, thumbImg(v.thumb, "thumb big")),
      h("div", { class: "card" }, h("h2", { text: v.title }), h("p", { class: "hint" }, `Chiqqan vaqti: ${postedLabel(v.posted_at) || "—"}`, v.duration ? ` · ${Math.round(v.duration)} soniya` : ""),
        h("div", { class: "side-by-side" }, col("youtube"), col("instagram")))),
    h("div", { class: "grid halves section-gap" },
      h("div", { class: "card" }, h("h2", { text: "Ko'rishlar tarixi" }), h("p", { class: "hint", text: "Har kungi yig'ilgan jami ko'rishlar." }), histBox),
      h("div", { class: "card" }, h("h2", { text: "Tomoshabin ushlab qolinishi (YouTube)" }), h("p", { class: "hint", text: "Videoning qaysi joyida necha foiz tomoshabin qolgani." }), retBox)));
  shell("videos", "Video tafsilotlari", null, [updatedNode(st)], body);
  const daysSet = [...new Set(Object.values(v.history || {}).flat().map((r) => r.day))].sort();
  const ser = ["youtube", "instagram"].filter((p) => v.history && v.history[p]).map((p) => {
    const map = Object.fromEntries(v.history[p].map((r) => [r.day, r.views]));
    return { key: p, label: PF[p].name, cls: PF[p].cls, color: PF[p].color, values: daysSet.map((d) => (d in map ? map[d] : null)) };
  });
  lineChart(histBox, daysSet, ser, { height: 220 });
  if (v.retention && v.retention.length) {
    const pts = v.retention;
    retBox.replaceChildren();
    const chart = h("div", { class: "chart" }); retBox.append(chart);
    const draw = () => {
      const W = Math.max(260, chart.clientWidth), H = 220, L = 44, R = 12, T = 12, B = 26;
      const max = Math.max(1, ...pts.map((p) => p[1]));
      const x = (r) => L + r * (W - L - R), y = (v2) => T + (H - T - B) * (1 - v2 / max);
      const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": "Ushlab qolinish" });
      [0, 0.5, 1].forEach((g) => { svg.append(s("line", { class: "grid-line", x1: L, x2: W - R, y1: y(max * g), y2: y(max * g) })); svg.append(s("text", { class: "axis-text", x: L - 6, y: y(max * g) + 4, "text-anchor": "end" }, pct(100 * max * g))); });
      [0, 0.5, 1].forEach((g) => svg.append(s("text", { class: "axis-text", x: x(g), y: H - 6, "text-anchor": g === 0 ? "start" : g === 1 ? "end" : "middle" }, `${Math.round(g * 100)}%`)));
      svg.append(s("path", { class: "line", stroke: "var(--yt)", d: pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join("") }));
      const hit = s("rect", { x: L, y: T, width: W - L - R, height: H - T - B, fill: "transparent" });
      hit.addEventListener("pointermove", (e) => { const b = svg.getBoundingClientRect(); const r = Math.max(0, Math.min(1, (((e.clientX - b.left) / b.width) * W - L) / (W - L - R))); const p = pts.reduce((a, c) => (Math.abs(c[0] - r) < Math.abs(a[0] - r) ? c : a)); showTip(e, `Videoning ${Math.round(p[0] * 100)}% qismi`, [{ cls: "yt", value: pct(100 * p[1]), label: "tomoshabin" }]); });
      hit.addEventListener("pointerleave", hideTip);
      svg.append(hit); chart.replaceChildren(svg);
    };
    draw(); new ResizeObserver(draw).observe(chart);
  } else {
    retBox.replaceChildren(h("div", { class: "chart-empty", text: "YouTube ushlab qolinish ma'lumotini yetarlicha ko'rishdan keyin beradi (odatda 1–3 kun)." }));
  }
}

// ---------------------------------------------------------------- insights
async function renderInsights() {
  const days = rangeDays();
  const ins = await api(`/api/insights?days=${days}`);
  const st = state.status || (await api("/api/status"));
  const hoursBox = h("div"), daysBox = h("div");
  const bt = ins.best_times;
  const best = bt.best_hour !== null ? `${String(bt.best_hour).padStart(2, "0")}:00` : null;
  const top = h("div", {}, ins.top.length ? ins.top.map((v, i) => {
    const b = h("button", { class: "vcard", type: "button", style: "margin-bottom:10px" }, thumbImg(v.thumb), h("div", { style: "min-width:0" }, h("div", { class: "vtitle", text: `${i + 1}. ${v.title}` }), h("div", { class: "vmeta" }, pfDots(v), " ", postedLabel(v.posted_at)), h("div", { class: "nums" }, h("span", {}, h("b", { text: num(v.total_views) }), " ko'rish"), h("span", {}, h("b", { text: num(v.total_likes) }), " layk"))));
    b.addEventListener("click", () => { location.hash = `#/video/${v.key}`; });
    return b;
  }) : h("div", { class: "chart-empty", text: "Eng yaxshi videolar statistikasi yig'ilgach shu yerda bo'ladi." }));
  const body = h("div", {}, banners(st),
    h("div", { class: "grid halves" },
      h("div", { class: "card" }, h("h2", { text: "Eng yaxshi chiqish vaqti" }), h("p", { class: "hint", text: best ? `Eng ko'p ko'rilgan videolar soat ${best} atrofida chiqqan (Toshkent vaqti). Ustunlar — shu soatda chiqqan videolarning o'rtacha ko'rishi.` : "Bir necha video chiqqach, qaysi soat yaxshiroq ishlashi shu yerda ko'rinadi." }), hoursBox),
      h("div", { class: "card" }, h("h2", { text: "Hafta kunlari bo'yicha" }), h("p", { class: "hint", text: "Har kuni chiqqan videolarning o'rtacha ko'rishi." }), daysBox)),
    h("div", { class: "grid two section-gap" }, h("div", { class: "card" }, h("h2", { text: "Eng ko'p ko'rilgan videolar" }), h("p", { class: "hint", text: "Ikkala platformadagi jami ko'rish bo'yicha." }), top), comparisonCard(ins.comparison, days)));
  shell("insights", "Tahlil", "Nima yaxshi ishlayapti", [updatedNode(st), DateRange({ range: state.range, onChange: (r) => { state.range = r; localStorage.setItem("sa_range", JSON.stringify(r)); renderInsights(); } })], body);
  barChart(hoursBox, bt.hours.map((x) => ({ label: `Soat ${String(x.hour).padStart(2, "0")}:00`, short: String(x.hour).padStart(2, "0"), value: x.avg_views, sub: `${x.videos} ta video` })), { label: "Soatlar bo'yicha" });
  barChart(daysBox, bt.weekdays.map((x) => ({ label: WEEKDAY_FULL[x.weekday], short: WEEKDAYS[x.weekday], value: x.avg_views, sub: `${x.videos} ta video` })), { color: "var(--accent)", label: "Hafta kunlari" });
}

// ---------------------------------------------------------------- pipeline
async function renderPipeline() {
  const data = await api("/api/pipeline");
  return renderReelBoard(data);
}

// ---------------------------------------------------------------- the owner's reel flow
const STAGE_HINT = { research: "Bot tadqiqot qiladi · Siz mavzu tanlaysiz", script: "Bot yozadi · Siz tahrirlaysiz va ovoz yuborasiz",
  broll: "Bot haqiqiy video va rasmlarni yig'adi", edit: "Bot montaj qiladi · Siz ko'rib chiqasiz",
  publish: "Siz muqova tayyorlaysiz · Bot GitHub va Buffer qoralamalari · Siz Buffer'da tasdiqlab rejalashtirasiz", live: "Bot efirni kuzatadi · Siz storyni o'zingiz joylaysiz" };
function whoBadge(who) { return h("span", { class: `who ${who === "Siz" ? "you" : "bot"}`, text: who === "Siz" ? "Siz" : "Bot" }); }
async function renderReelBoard(data) {
  const st = state.status || (await api("/api/status"));
  const board = h("div", { class: "board reel-board" }, data.columns.map((c, i) => h("section", { class: `col ${c.key}`, "aria-label": c.label },
    h("h3", {}, h("span", {}, `${i + 1}. ${c.label}`), h("span", { class: "count", text: String(c.items.length) })),
    h("p", { class: "col-hint", text: STAGE_HINT[c.key] || "" }),
    c.items.length ? c.items.map((it) => {
      const card = h("a", { class: "pcard reel-card", href: `#/reel/${it.key}` }, h("div", { class: "ttl", text: it.title }),
        h("div", { class: "meta" }, whoBadge(it.who), h("span", { class: "tag", text: it.status }), it.version ? h("span", { class: "tag", text: `v${it.version}` }) : null),
        h("div", { class: "meta" }, it.slot ? h("span", { text: `🗓 ${it.slot}` }) : null, it.origin_voice ? h("span", { class: "tag", text: "ovozdan" }) : null));
      return card;
    }) : h("div", { class: "col-empty", text: "Bo'sh" }))));
  shell("pipeline", "Jarayon", "Reel bosqichlari: kim nima qiladi — «Siz» yoki «Bot». Bot faqat qoralama tayyorlaydi.", [updatedNode(st)], h("div", {}, banners({ ...st, dry_run: data.dry_run }), board));
}

async function renderReel(key) {
  let r;
  try { r = await api(`/api/reels/${encodeURIComponent(key)}`); } catch (e) { if (e.status === 404) { location.hash = "#/pipeline"; return; } throw e; }
  const stages = [["research", "Tadqiqot"], ["script", "Ssenariy"], ["broll", "B-roll"], ["edit", "Montaj"], ["publish", "Buffer"], ["live", "Efir"]];
  const cur = stages.findIndex((s) => s[0] === r.stage_key);
  const stepper = h("ol", { class: "stepper" }, stages.map(([k, label], i) => h("li", { class: i < cur ? "done" : i === cur ? "now" : "" }, h("span", { class: "n", text: String(i + 1) }), h("span", { text: label }))));
  const head = h("div", { class: "card" }, h("div", { class: "card-head" }, h("div", {}, h("h2", { text: r.title }),
    h("p", { class: "hint", style: "margin:4px 0 0" }, r.name ? `${r.name}` : "", r.slot ? ` · chiqish: ${r.slot}` : "")),
    h("div", { class: "chips-row" }, whoBadge(r.who), h("span", { class: "tag", text: r.status }), r.version ? h("span", { class: "tag", text: `v${r.version}` }) : null)), stepper);
  const cards = [head];
  if (r.research) {
    cards.push(h("div", { class: "card" }, h("h2", { text: "Tadqiqot" }), r.research.insight ? h("p", { class: "hint", text: r.research.insight }) : null,
      h("div", { class: "topics" }, r.research.topics.map((tp, i) => h("div", { class: `topic ${r.topic_index === i ? "chosen" : ""}` },
        h("div", { class: "t-title" }, `${i + 1}. ${tp.title}`, r.topic_index === i ? h("span", { class: "badge-used", style: "margin-left:8px", text: "tanlangan" }) : null),
        tp.angle ? h("div", { class: "t-sub", text: tp.angle }) : null,
        h("ul", { class: "facts" }, tp.facts.map((f) => h("li", {}, f.claim, " — ", f.url ? h("a", { href: f.url, target: "_blank", rel: "noopener noreferrer", text: f.source }) : h("span", { text: f.source })))))))));
  }
  if (r.script.parts.length) {
    cards.push(h("div", { class: "card" }, h("h2", { text: "Ssenariy (8 qism)" }), r.script.key_fact ? h("p", { class: "hint", text: `Birinchi 5 soniyadagi fakt: ${r.script.key_fact}` }) : null,
      h("ol", { class: "parts" }, r.script.parts.map((p) => h("li", {}, h("b", { text: p.label }), h("span", { text: p.text }), p.info ? h("span", { class: "tag", text: `${p.info.value} — ${p.info.label}` }) : null)))));
  }
  if (r.frames.length) {
    cards.push(h("div", { class: "card" }, h("h2", { text: `Bo'lim kadrlari (v${r.version})` }), h("p", { class: "hint", text: "Har bir qism boshidagi kadr — sifat tekshiruvi shularni ham ko'radi." }),
      h("div", { class: "frames" }, r.frames.map((f) => h("figure", {}, h("img", { src: f.src, alt: f.label }), h("figcaption", { text: f.label }))))));
  }
  const checks = [...((r.checklist.before || {}).checks || []).map((c) => ({ ...c, when: "oldin" })), ...((r.checklist.after || {}).checks || []).map((c) => ({ ...c, when: "keyin" }))];
  if (checks.length) {
    const ok = checks.filter((c) => c.ok).length;
    cards.push(h("div", { class: "card" }, h("h2", { text: "Reel xatolari ro'yxati" }), h("p", { class: "hint", text: `Renderdan oldin va keyin: ${ok}/${checks.length} o'tdi.` }),
      h("ul", { class: "checks" }, checks.map((c) => h("li", { class: c.ok ? "ok" : "bad" }, h("span", { class: "mark", text: c.ok ? "✓" : "✗" }), h("div", {}, h("b", { text: c.rule }), h("span", { text: ` — ${c.detail}` }), h("span", { class: "when", text: c.when })))))));
  }
  if (r.sources.length) {
    cards.push(h("div", { class: "card" }, h("h2", { text: "B-roll manbalari" }), h("p", { class: "hint", text: "Faqat haqiqiy video va fotosuratlar, qayta ishlatishga ruxsat berilgan litsenziyalar bilan." }),
      h("ul", { class: "sources" }, r.sources.map((s) => h("li", {}, h("span", { class: "tag", text: s.part }), h("span", { class: "tag", text: s.kind }),
        h("div", { style: "min-width:0" }, s.link ? h("a", { href: s.link, target: "_blank", rel: "noopener noreferrer", text: s.title || s.provider }) : h("span", { text: s.title || s.provider }),
          h("div", { class: "vmeta", text: `${s.provider} · ${s.author} · ${s.license}` })))))));
  }
  const pub = [];
  if (r.versions.length) pub.push(h("div", {}, h("span", { text: "Versiyalar" }), h("b", { text: r.versions.map((v) => `v${v.n}`).join(", ") })));
  pub.push(h("div", {}, h("span", { text: "GitHub" }), h("b", { text: r.git || "hali emas" })));
  pub.push(h("div", {}, h("span", { text: "Buffer qoralamalari" }), h("b", { text: r.drafts.length ? `${r.drafts.join(", ")} — tasdiqlab rejalashtirish sizda` + (r.dry_run ? " (sinov)" : "") : "hali yo'q" })));
  pub.push(h("div", {}, h("span", { text: "Muqova" }), h("b", { text: r.cover ? "sizning muqovangiz" : "kutilmoqda (siz tayyorlaysiz)" })));
  pub.push(h("div", {}, h("span", { text: "Efir" }), r.live ? h("a", { href: r.live, target: "_blank", rel: "noopener noreferrer", text: "reelni ochish" }) : h("b", { text: "hali chiqmagan" })));
  cards.push(h("div", { class: "card" }, h("h2", { text: "GitHub va Buffer" }), h("p", { class: "hint", text: "Bot faqat qoralama tayyorlaydi — hech narsani o'zi joylamaydi yoki rejalashtirmaydi." }), h("div", { class: "kv" }, pub)));
  if (r.fixes.length) cards.push(h("div", { class: "card" }, h("h2", { text: "Sizning tuzatishlaringiz" }), h("ul", { class: "never" }, r.fixes.map((f) => h("li", {}, h("span", { text: "✏️" }), h("div", { text: f }))))));
  const body = h("div", {}, h("a", { class: "back", href: "#/pipeline" }, icon("left"), "Jarayon"), h("div", { class: "reel-grid" }, cards));
  shell("pipeline", "Reel", null, [], body);
}

// ---------------------------------------------------------------- skills
const GROUP_TITLES = { personal: "Shaxsiy ko'nikmalar", project: "Shu loyihaning ko'nikmalari", plugin: "Plagin ko'nikmalari" };
async function renderSkills() {
  const data = await api("/api/skills");
  let q = "";
  const box = h("div", { class: "skill-groups" });
  const card = (sk) => {
    const el = h("button", { class: "skill", type: "button", "aria-expanded": "false" },
      h("div", { class: "s-top" }, h("div", { class: "s-name", text: sk.name }), sk.used ? h("span", { class: "badge-used", text: "Ishda ishlatiladi" }) : null),
      h("div", { class: "s-desc", text: sk.short }),
      h("div", { class: "s-full", text: sk.description }),
      h("div", { class: "s-meta" }, h("span", { class: "cmd", text: sk.invoke }), h("span", { class: "tag", text: sk.kind === "command" ? "buyruq" : "ko'nikma" }),
        sk.synced ? h("span", { class: "tag", text: "claude.ai dan" }) : null));
    el.addEventListener("click", () => el.setAttribute("aria-expanded", String(el.getAttribute("aria-expanded") !== "true")));
    return el;
  };
  const draw = () => {
    const match = (sk) => !q || `${sk.name} ${sk.slug} ${sk.description} ${sk.source}`.toLowerCase().includes(q);
    const rows = data.skills.filter(match);
    if (!data.total) { box.replaceChildren(h("div", { class: "chart-empty", text: "Hozircha birorta ko'nikma o'rnatilmagan. Claude'ga ko'nikma qo'shilsa, shu yerda paydo bo'ladi." })); return; }
    if (!rows.length) { box.replaceChildren(h("div", { class: "chart-empty", text: "Hech narsa topilmadi." })); return; }
    const groups = [];
    for (const g of data.groups) {
      const items = rows.filter((sk) => sk.source === g.label);
      if (!items.length) continue;
      groups.push(h("section", { "aria-label": g.label }, h("h2", { class: "group-head" }, h("span", { text: g.group === "plugin" ? g.label : GROUP_TITLES[g.group] }), h("span", { class: "count", text: String(items.length) })),
        h("div", { class: "skill-grid" }, items.map(card))));
    }
    box.replaceChildren(...groups);
  };
  const search = h("input", { class: "search", type: "search", placeholder: "Ko'nikma qidirish", "aria-label": "Ko'nikma qidirish" });
  search.addEventListener("input", () => { q = search.value.trim().toLowerCase(); draw(); });
  const summary = h("div", { class: "chips-row" }, data.groups.map((g) => h("span", { class: "chip" }, `${g.label}: `, h("b", { text: String(g.count) }))));
  const note = h("div", { class: "note" }, h("span", { text: "ℹ️" }), h("div", {}, h("b", { text: "Bot ishida: " }), data.used_count ? `${data.used_count} ta ko'nikma ishlatiladi («Ishda ishlatiladi» belgisi bilan).` : (data.used_note || "")));
  const body = h("div", {}, note, h("div", { class: "card" }, h("div", { class: "toolbar" }, search), summary), h("div", { class: "section-gap" }, box));
  shell("skills", "Ko'nikmalar", `Claude akkauntingizda o'rnatilgan ${data.total} ta ko'nikma. Kartani bossangiz, to'liq tavsif ochiladi.`, [], body);
  draw();
}

// ---------------------------------------------------------------- repo (GitHub): the user's OWN content repo
function avatarNode(url, label, cls = "avatar") {
  const fallback = h("span", { class: `${cls} fallback`, text: (label || "?").replace(/^@/, "").slice(0, 1).toUpperCase() });
  if (!url) return fallback;
  const img = h("img", { class: cls, src: url, alt: "", loading: "lazy", referrerpolicy: "no-referrer" });
  img.addEventListener("error", () => img.replaceWith(fallback));
  return img;
}
function extLink(href, text, cls = "link") { return h("a", { class: cls, href, target: "_blank", rel: "noopener noreferrer" }, text, icon("ext")); }
function accountCard(a, content) {
  if (!a.connected) {
    const local = content && content.remote;
    return h("div", { class: "card" }, h("div", { class: "big-state" }, h("div", { class: `glyph ${local ? "ok" : "off"}` }, icon(local ? "cloud" : "cloudOff")),
      h("div", {}, h("h2", { text: local ? "Kontent repo ulangan" : "GitHub hali ulanmagan" }),
        h("p", { class: "hint", style: "margin:4px 0 0", text: local ? `Reellar shu manzilga yuklanadi: ${content.remote}` : "Reellar hozircha shu kompyuterda saqlanadi. Sozlamalar → GitHub'da o'z akkauntingizni ulang — ular sizning yopiq repoingizga yuklanadi." }))),
      local && content.remote_url ? h("div", { class: "controls" }, extLink(content.remote_url, "Repoini ochish", "btn")) : h("div", { class: "controls" }, h("a", { class: "btn primary", href: "#/settings/github" }, icon("github"), "GitHub'ni ulash")));
  }
  return h("div", { class: "card" }, h("div", { class: "acct" }, avatarNode(a.avatar_url, a.login, "avatar lg"),
      h("div", { class: "acct-text" }, h("h2", { text: a.name || `@${a.login}` }), h("a", { class: "link", href: a.profile_url, target: "_blank", rel: "noopener noreferrer", text: `@${a.login}` }))),
    h("div", { class: "kv" }, h("div", {}, h("span", { text: "Kontent repo" }), a.repo_url ? h("a", { class: "link", href: a.repo_url, target: "_blank", rel: "noopener noreferrer", text: a.repo_name }) : h("b", { text: a.repo_name })),
      h("div", {}, h("span", { text: "Ko'rinishi" }), h("b", { text: a.repo_exists === false ? "hali yaratilmagan" : "yopiq (faqat siz)" })),
      content ? h("div", {}, h("span", { text: "Reellar" }), h("b", { text: `${content.count} ta` })) : null,
      content ? h("div", {}, h("span", { text: "Yuklanmagan" }), h("b", { text: content.unpushed ? `${content.unpushed} ta o'zgarish` : "yo'q" })) : null));
}
async function renderRepo() {
  const r = await api("/api/repo");
  const code = h("div", { class: "card" }, h("div", { class: "big-state" }, h("div", { class: "glyph ok" }, icon("shield")),
      h("div", {}, h("h2", { text: "Dastur kodi" }), h("p", { class: "hint", style: "margin:4px 0 0", text: "Faqat yangilanishlar olinadi. Ilova bu repoga hech qachon hech narsa yozmaydi — reellaringiz unga tushmaydi." }))),
    h("div", { class: "kv" }, h("div", {}, h("span", { text: "Manba" }), h("a", { class: "link", href: r.code.url, target: "_blank", rel: "noopener noreferrer", text: r.code.repo })),
      h("div", {}, h("span", { text: "Yangilanish" }), h("a", { class: "link", href: "#/settings", text: "Sozlamalarda tekshirish" }))));
  const reels = h("div", { class: "card" }, h("h2", { text: "Oxirgi reellar" }),
    r.content.reels.length ? h("ul", { class: "timeline" }, r.content.reels.map((x) => h("li", {}, h("div", { class: "t-title", text: x.title }), h("div", { class: "t-meta" }, h("span", { text: x.date ? fmtDay(x.date) : "" })))))
      : h("p", { class: "hint", text: "Hali reel yo'q. Tasdiqlangan har bir reel (video, muqovangiz, ssenariy, tadqiqot, manbalar) shu yerda paydo bo'ladi." }));
  const never = h("div", { class: "card" }, h("h2", { text: "Hech qachon yuklanmaydi" }), h("p", { class: "hint", text: "Bular faqat shu kompyuterda qoladi — hech qaysi GitHub'ga chiqmaydi:" }),
    h("ul", { class: "never" }, r.never.map((n) => h("li", {}, icon("shield"), h("div", {}, h("b", { text: n.title }), n.detail)))));
  const history = h("div", { class: "card" }, h("h2", { text: "Kontent reposi tarixi" }),
    r.history.length ? h("ul", { class: "timeline" }, r.history.map((c) => h("li", {}, h("div", { class: "t-title", text: c.title }), h("div", { class: "t-meta" }, h("span", { text: c.when }), h("span", { text: `${c.files} ta fayl` })))))
      : h("p", { class: "hint", text: "Hali bo'sh." }));
  const body = h("div", {}, h("div", { class: "repo-grid" }, accountCard(r.account, r.content), code), h("div", { class: "repo-grid section-gap" }, reels, never), h("div", { class: "section-gap" }, history));
  shell("repo", "GitHub", "Reellaringiz sizning o'z GitHub'ingizga boradi; dastur kodi faqat o'qiladi", [], body);
}
function fmtDay(iso) {
  const MON = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"];
  const [y, m, d] = iso.split("-").map(Number);
  return `${d}-${MON[m - 1]}, ${y}`;
}

// ---------------------------------------------------------------- setup ("Sozlash") and settings ("Sozlamalar")
const REASONS = {
  too_short: "Parol kamida 8 belgidan iborat bo'lsin.", bad_token: "Token ko'rinishi noto'g'ri. To'liq nusxalab qayta qo'ying.",
  bad_ids: "ID faqat raqamlardan iborat bo'ladi; bir nechta bo'lsa vergul bilan ajrating.", bad_app_id: "App ID faqat raqamlardan iborat.",
  missing: "Avval qiymatni kiriting.", rejected: "Xizmat bu qiymatni qabul qilmadi — qayta nusxalab ko'ring.",
  network: "Internetga ulanib bo'lmadi. Ulanishni tekshirib, qayta urinib ko'ring.", password_first: "Avval parolni o'rnating.",
  local_only: "Sozlash sahifasi faqat shu kompyuterning o'zidan ochiladi.", too_long: "Qiymat juda uzun.", mismatch: "Ikkala parol bir xil emas.",
  no_client_id: "Bu nusxada GitHub tugmasi sozlanmagan — pastdagi «token bilan» usulidan foydalaning.",
  meta_keys: "Avval Meta App ID va App Secret'ni saqlang.", no_client: "Avval Google'dan yuklab olingan JSON faylni tanlang.",
  bad_client: "Bu fayl Google OAuth mijoz fayliga o'xshamaydi. «Desktop app» turidagi mijozning JSON faylini tanlang.",
  bad_code: "Kod qabul qilinmadi. Kirish sahifasidagi kodni to'liq nusxalab qayta urinib ko'ring.", not_started: "Avval «Claude'ga kirish» tugmasini bosing.",
  not_installed: "Bu kompyuterda Claude Code o'rnatilmagan.", timeout: "Kutish vaqti tugadi — qaytadan boshlang.", not_finished: "Kirish tugallanmadi — qaytadan urinib ko'ring.",
  no_ig_account: "Facebook sahifalaringizdan hech biriga Instagram Business/Creator akkaunt bog'lanmagan.", expired: "Havola eskirdi — qaytadan bosing.",
  scopes: "Faqat statistika (o'qish) ruxsati kerak — qaytadan ulang.", cancel: "Ulanish bekor qilindi.",
};
function reasonText(r) { return REASONS[r] || "Saqlab bo'lmadi. Qayta urinib ko'ring."; }
const SETUP_STEPS = [
  { key: "password", icon: "key", label: "Parol" }, { key: "telegram", icon: "send", label: "Telegram" },
  { key: "buffer", icon: "layers", label: "Buffer" }, { key: "github", icon: "github", label: "GitHub" },
  { key: "claude", icon: "cpu", label: "Claude" }, { key: "stats", icon: "insights", label: "Statistika" },
  { key: "extra", icon: "plus", label: "Qo'shimcha" }, { key: "done", icon: "flag", label: "Tayyor" },
];
function secretField({ label, name, state, placeholder, help, plain = false }) {
  const info = state.values[name] || { set: false, shown: "" };
  const input = h("input", { type: plain ? "text" : "password", name, placeholder: placeholder || "", autocomplete: "off", spellcheck: "false", "aria-label": label });
  const eye = plain ? null : h("button", { class: "btn icon eye", type: "button", "aria-label": "Ko'rsatish" }, icon("eye"));
  if (eye) eye.addEventListener("click", () => { input.type = input.type === "password" ? "text" : "password"; });
  const field = h("div", { class: "field" }, input, eye);
  const wrap = h("div", { class: "sf" }, h("label", { class: "sf-label", text: label }), help ? h("p", { class: "sf-help" }, help) : null);
  if (info.set) {
    const changeBtn = h("button", { class: "btn", type: "button" }, "O'zgartirish");
    const saved = h("div", { class: "sf-saved" }, h("span", { class: "ok-badge" }, icon("check"), "Saqlangan"), h("code", { text: info.shown }), changeBtn);
    field.hidden = true;
    changeBtn.addEventListener("click", () => { saved.hidden = true; field.hidden = false; input.focus(); });
    wrap.append(saved, field);
  } else {
    wrap.append(field);
  }
  return { el: wrap, input, value: () => input.value.trim(), changed: () => !field.hidden && input.value.trim() !== "" };
}
function resultLine() { return h("div", { class: "sf-result", role: "status" }); }
function showResult(box, ok, text) { box.className = `sf-result ${ok ? "good" : "bad"}`; box.replaceChildren(h("span", { text: ok ? "✓" : "!", class: "mark" }), h("span", { text })); }
function copyButton(text, label = "Nusxalash") {
  const b = h("button", { class: "btn", type: "button" }, label);
  b.addEventListener("click", async () => { try { await navigator.clipboard.writeText(text); b.textContent = "Nusxalandi ✓"; setTimeout(() => { b.textContent = label; }, 1800); } catch (e) { /* the text stays visible to copy by hand */ } });
  return b;
}
function toggleBlock(label, body) {
  const btn = h("button", { class: "btn toggle", type: "button", "aria-expanded": "false" }, icon("chevron"), label);
  body.hidden = true;
  btn.addEventListener("click", () => { body.hidden = !body.hidden; btn.setAttribute("aria-expanded", String(!body.hidden)); btn.classList.toggle("open", !body.hidden); });
  return h("div", { class: "toggle-block" }, btn, body);
}
function guide(steps) { return h("ol", { class: "guide" }, steps.map((s) => h("li", {}, s))); }
function statusRow(ok, title, help) {
  return h("div", { class: `status-row ${ok ? "good" : "bad"}` }, h("span", { class: "mark", text: ok ? "✓" : "!" }), h("div", {}, h("b", { text: title }), help ? h("p", { class: "sf-help" }, help) : null));
}
function filePicker(label, accept, onText) {
  const input = h("input", { type: "file", accept, class: "visually-hidden", tabindex: "-1", "aria-hidden": "true" });
  const name = h("span", { class: "fp-name", text: "Fayl tanlanmagan" });
  const btn = h("button", { class: "btn", type: "button" }, icon("plus"), label);
  btn.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    const f = input.files && input.files[0];
    if (!f) return;
    name.textContent = f.name;
    const rd = new FileReader();
    rd.onload = () => onText(String(rd.result || ""));
    rd.readAsText(f);
  });
  return h("div", { class: "file-picker" }, btn, name, input);
}

async function renderSetup(firstRun, startKey) {
  let state;
  try { state = await api("/api/setup/state"); } catch (e) {
    if (e.status === 403) { $app.replaceChildren(h("div", { class: "login" }, h("div", { class: "card" }, brand(), h("h1", { text: "Sozlash" }), h("p", { text: reasonText("local_only") })))); return; }
    throw e;
  }
  const stepIndex = (k) => Math.max(0, SETUP_STEPS.findIndex((s) => s.key === k));
  let step = firstRun ? (state.values.DASHBOARD_PASSWORD.set ? 1 : 0) : (startKey ? stepIndex(startKey) : 1);
  const body = h("div", { class: "setup-body" });
  const stepper = h("ol", { class: "setup-steps" });
  let timers = [];
  const clearTimers = () => { timers.forEach(clearTimeout); timers = []; };
  const draw = async () => {
    clearTimers();
    stepper.replaceChildren(...SETUP_STEPS.map((s, i) => {
      const li = h("li", { class: i < step ? "done" : i === step ? "now" : "" }, h("span", { class: "si" }, icon(i < step ? "check" : s.icon)), h("span", { class: "sl", text: s.label }));
      if (!firstRun || i < step) { li.classList.add("go"); li.tabIndex = 0; li.setAttribute("role", "button"); li.setAttribute("aria-label", s.label);
        const go = () => { step = i; if (!firstRun) history.replaceState(null, "", `#/settings/${s.key}`); draw(); };
        li.addEventListener("click", go); li.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } }); }
      return li;
    }));
    body.replaceChildren(await stepView(SETUP_STEPS[step].key));
    if (firstRun) body.querySelector("input:not([type=file])")?.focus();
  };
  const next = async () => { state = await api("/api/setup/state"); step = Math.min(SETUP_STEPS.length - 1, step + 1); if (!firstRun) history.replaceState(null, "", `#/settings/${SETUP_STEPS[step].key}`); await draw(); };
  const nav = (onNext, { skip = false, label = "Davom etish" } = {}) => {
    const err = h("div", { class: "err", role: "alert" });
    const go = h("button", { class: "btn primary", type: "submit" }, label);
    const back = step > (firstRun ? 1 : 0) ? (() => { const b = h("button", { class: "btn", type: "button" }, "Orqaga"); b.addEventListener("click", () => { step -= 1; draw(); }); return b; })() : h("span");
    const row = h("div", { class: "setup-nav" }, back,
      h("div", { class: "controls" }, skip ? (() => { const b = h("button", { class: "btn", type: "button" }, "Keyinroq"); b.addEventListener("click", next); return b; })() : null, go));
    return { row, err, go, run: async (e) => { e && e.preventDefault(); err.textContent = ""; go.disabled = true; try { await onNext(); } catch (ex) { err.textContent = reasonText(ex.message); } go.disabled = false; } };
  };
  const saveValues = async (fields) => {
    const values = {};
    for (const [k, f] of Object.entries(fields)) if (f.changed()) values[k] = f.value();
    if (Object.keys(values).length) await api("/api/setup/save", { method: "POST", body: JSON.stringify({ values }) });
  };
  const form = (title, hint, ...kids) => h("form", { class: "setup-form" }, h("h2", { text: title }), hint ? h("p", { class: "hint", text: hint }) : null, ...kids);
  const n = (i) => `${i}. `;
  async function stepView(key) {
    if (key === "password") {
      const a = h("input", { type: "password", autocomplete: "new-password", placeholder: "Yangi parol (kamida 8 belgi)", "aria-label": "Yangi parol" });
      const b = h("input", { type: "password", autocomplete: "new-password", placeholder: "Parolni takrorlang", "aria-label": "Parolni takrorlang" });
      const nv = nav(async () => {
        if (a.value.length < 8) throw new Error("too_short");
        if (a.value !== b.value) throw new Error("mismatch");
        await api("/api/setup/password", { method: "POST", body: JSON.stringify({ password: a.value }) });
        await next();
      });
      const f = form(n(1) + "Sayt paroli", "Bu parol bilan statistika saytiga kirasiz. U faqat shu kompyuterda, .env faylida saqlanadi.",
        h("div", { class: "field" }, a), h("div", { class: "field" }, b), nv.err, nv.row);
      f.addEventListener("submit", nv.run);
      return f;
    }
    if (key === "telegram") {
      const token = secretField({ label: "Bot tokeni", name: "TELEGRAM_BOT_TOKEN", state, placeholder: "123456789:ABC...", help: "Telegram'da @BotFather → /newbot → bot nomi → u bergan tokenni shu yerga qo'ying." });
      const ids = secretField({ label: "Sizning Telegram ID'ingiz", name: "TELEGRAM_ALLOWED_USER_IDS", state, plain: true, placeholder: "123456789", help: "@userinfobot ga /start yozing — u ID raqamingizni beradi. Bir nechta bo'lsa, vergul bilan." });
      const res = resultLine();
      const check = h("button", { class: "btn", type: "button" }, icon("check"), "Tekshirish");
      check.addEventListener("click", async () => {
        check.disabled = true;
        try { const r = await api("/api/setup/check/telegram", { method: "POST", body: JSON.stringify({ value: token.changed() ? token.value() : "" }) });
          showResult(res, r.ok, r.ok ? `Bot topildi: ${r.name}${r.username ? " (@" + r.username + ")" : ""}` : reasonText(r.reason)); }
        catch (e) { showResult(res, false, reasonText(e.message)); }
        check.disabled = false;
      });
      const nv = nav(async () => { await saveValues({ TELEGRAM_BOT_TOKEN: token, TELEGRAM_ALLOWED_USER_IDS: ids }); await next(); }, { skip: true });
      const f = form(n(2) + "Telegram bot", "Bot sizga mavzular, ssenariy, video va qoralamalar haqida yozadi. Faqat siz kiritgan ID egalari u bilan ishlay oladi.",
        token.el, h("div", { class: "controls" }, check), res, ids.el, nv.err, nv.row);
      f.addEventListener("submit", nv.run);
      return f;
    }
    if (key === "buffer") {
      const k = secretField({ label: "Buffer API kaliti", name: "BUFFER_API_KEY", state, help: "publish.buffer.com → Settings → API → Create API key. Bot u bilan faqat QORALAMA yaratadi — hech narsani o'zi joylamaydi yoki rejalashtirmaydi." });
      const res = resultLine();
      const list = h("div", { class: "chan-list" });
      const check = h("button", { class: "btn", type: "button" }, icon("check"), "Tekshirish");
      const run = async (silent) => {
        check.disabled = true;
        try {
          const r = await api("/api/setup/check/buffer", { method: "POST", body: JSON.stringify({ value: k.changed() ? k.value() : "" }) });
          if (r.ok) {
            showResult(res, true, r.channels.length ? `Buffer'da ${r.channels.length} ta kanal ulangan — qoralamalar shularga tayyorlanadi:` : "Kalit ishlaydi, lekin Buffer'da hali kanal ulanmagan.");
            const icons = { instagram: "ig", youtube: "yt" };
            list.replaceChildren(...r.channels.map((c) => h("div", { class: "chan" }, avatarNode(c.avatar, c.name || c.service), h("div", {}, h("b", { text: c.name || c.service }), h("span", { class: "chan-svc" }, icons[c.kind] ? icon(icons[c.kind]) : null, c.service)))),
              h("div", { class: "chan more" }, extLink(r.connect_url, "Buffer'da yana kanal ulash")));
          } else if (!silent) { showResult(res, false, reasonText(r.reason)); list.replaceChildren(); }
        } catch (e) { if (!silent) showResult(res, false, reasonText(e.message)); }
        check.disabled = false;
      };
      check.addEventListener("click", () => run(false));
      if (state.values.BUFFER_API_KEY.set) run(true);
      const nv = nav(async () => { await saveValues({ BUFFER_API_KEY: k }); await next(); }, { skip: true });
      const f = form(n(3) + "Buffer (Instagram, YouTube, LinkedIn qoralamalari)", "Tayyor reel sizning Buffer'ingizda Instagram, YouTube va LinkedIn uchun qoralama bo'lib turadi; tasdiqlab rejalashtirish sizda. Instagram va YouTube'ni Buffer'ga o'zingiz ulaysiz.",
        k.el, h("div", { class: "controls" }, check), res, list, nv.err, nv.row);
      f.addEventListener("submit", nv.run);
      return f;
    }
    if (key === "github") return githubStep();
    if (key === "claude") return claudeStep();
    if (key === "stats") return statsStep();
    if (key === "extra") {
      const fields = {
        PEXELS_API_KEY: secretField({ label: "Pexels kaliti", name: "PEXELS_API_KEY", state, help: "Ko'proq bepul video uchun (ixtiyoriy): pexels.com/api." }),
        PIXABAY_API_KEY: secretField({ label: "Pixabay kaliti", name: "PIXABAY_API_KEY", state, help: "Ixtiyoriy: pixabay.com/api/docs (kirgandan keyin)." }),
      };
      const nv = nav(async () => { await saveValues(fields); await next(); }, { skip: true });
      const f = form(n(7) + "Qo'shimcha (ixtiyoriy)", "Bularsiz ham hammasi ishlaydi: videolar Wikimedia Commons'dan olinadi.",
        h("div", { class: "sf-grid" }, Object.values(fields).map((x) => x.el)), nv.err, nv.row);
      f.addEventListener("submit", nv.run);
      return f;
    }
    return doneStep();
  }

  async function githubStep() {
    const acc = await api("/api/accounts");
    const a = acc.github;
    const box = h("div", { class: "gh-box" });
    const res = resultLine();
    const nv = nav(async () => { await next(); }, { skip: !a.connected });
    if (a.connected) {
      const off = h("button", { class: "btn", type: "button" }, "Uzish");
      off.addEventListener("click", async () => {
        if (off.dataset.sure !== "1") { off.dataset.sure = "1"; off.textContent = "Rostdan uzilsinmi? Yana bosing"; return; }
        await api("/api/accounts/github/disconnect", { method: "POST", body: "{}" }); draw();
      });
      box.append(h("div", { class: "acct" }, avatarNode(a.avatar_url, a.login, "avatar lg"),
          h("div", { class: "acct-text" }, h("b", { text: a.name || `@${a.login}` }), h("a", { class: "link", href: a.profile_url, target: "_blank", rel: "noopener noreferrer", text: `@${a.login}` }))),
        statusRow(a.repo_exists !== false, a.repo_exists === false ? `«${a.repo_name}» repo hali yo'q` : `Reellar «${a.repo_name}» yopiq reposiga boradi`,
          a.repo_exists === false ? h("span", {}, "Token bilan ulangan bo'lsangiz, repoini o'zingiz yarating: ", extLink(`https://github.com/new?name=${a.repo_name}&visibility=private`, "yopiq repo yaratish"), ", keyin «Tekshirish»ni bosing.")
            : h("span", {}, extLink(a.repo_url, "Repoini ochish"))),
        h("div", { class: "controls" }, (() => { const b = h("button", { class: "btn", type: "button" }, icon("refresh"), "Tekshirish"); b.addEventListener("click", draw); return b; })(), off));
    } else {
      if (acc.content && acc.content.remote) box.append(statusRow(true, "Kontent repo qo'lda ulangan", `Reellar shu manzilga yuklanadi: ${acc.content.remote}. Xohlasangiz, GitHub akkauntingizni ham ulashingiz mumkin.`));
      const codeArea = h("div", { class: "device" });
      const startBtn = h("button", { class: "btn primary", type: "button" }, icon("github"), "GitHub'ni ulash");
      startBtn.disabled = !a.device_flow;
      startBtn.addEventListener("click", async () => {
        startBtn.disabled = true;
        try {
          const d = await api("/api/accounts/github/device", { method: "POST", body: "{}" });
          const wait = h("p", { class: "hint waiting" }, h("span", { class: "pulse" }), "GitHub'da tasdiqlashingizni kutyapman…");
          codeArea.replaceChildren(h("p", { class: "sf-help", text: "1) Kodni nusxalang. 2) GitHub sahifasini oching va kodni kiriting. 3) «Authorize» ni bosing — shu sahifa o'zi yangilanadi." }),
            h("div", { class: "code-box" }, h("span", { class: "code", text: d.user_code }), copyButton(d.user_code)),
            h("div", { class: "controls" }, extLink(d.verification_uri, "GitHub sahifasini ochish", "btn primary")), wait);
          window.open(d.verification_uri, "_blank", "noopener");
          const poll = async () => {
            try {
              const p = await api("/api/accounts/github/poll", { method: "POST", body: "{}" });
              if (p.state === "done") { draw(); return; }
              if (p.state === "expired" || p.state === "denied") { codeArea.replaceChildren(); showResult(res, false, p.state === "expired" ? "Kod eskirdi — qaytadan bosing." : "GitHub'da rad etildi."); startBtn.disabled = false; return; }
            } catch (e) { /* keep waiting */ }
            timers.push(setTimeout(poll, (d.interval + 1) * 1000));
          };
          timers.push(setTimeout(poll, (d.interval + 1) * 1000));
        } catch (e) { showResult(res, false, reasonText(e.message)); startBtn.disabled = false; }
      });
      const tok = h("input", { type: "password", autocomplete: "off", spellcheck: "false", placeholder: "github_pat_...", "aria-label": "GitHub token" });
      const save = h("button", { class: "btn", type: "button" }, "Saqlash");
      save.addEventListener("click", async () => {
        save.disabled = true;
        try { const r = await api("/api/accounts/github/token", { method: "POST", body: JSON.stringify({ token: tok.value }) }); tok.value = ""; draw(); if (r.repo_missing) showResult(res, false, "Ulandi, lekin repo yo'q — uni yarating."); }
        catch (e) { showResult(res, false, reasonText(e.message)); }
        save.disabled = false;
      });
      const tokenBody = h("div", { class: "toggle-body" },
        guide([h("span", {}, "Avval yopiq repo yarating: ", extLink(`https://github.com/new?name=${a.repo_name}&visibility=private`, a.repo_name), " (README qo'shmang)."),
          h("span", {}, "Token oching: ", extLink("https://github.com/settings/personal-access-tokens/new", "Fine-grained token"), " → Repository access: «Only select repositories» → ", h("b", { text: a.repo_name }), "."),
          h("span", {}, "Permissions → Repository permissions → ", h("b", { text: "Contents: Read and write" }), " (boshqa hech narsa kerak emas) → Generate token."),
          "Tokenni shu yerga qo'ying. U faqat shu kompyuterda saqlanadi va hech qachon ko'rsatilmaydi."]),
        h("div", { class: "field" }, tok), h("div", { class: "controls" }, save));
      box.append(h("p", { class: "sf-help", text: a.device_flow ? "Tugmani bosing — GitHub sahifasida qisqa kodni kiritasiz. Parolingiz bu saytga yozilmaydi." : "Bu nusxada GitHub tugmasi yo'q — token bilan ulang." }),
        h("div", { class: "controls" }, startBtn), codeArea, toggleBlock("Yoki token bilan ulash", tokenBody),
        h("p", { class: "sf-help muted-note", text: "GitHub'siz ham ishlaydi: reellar shu kompyuterda saqlanadi va sayt buni ko'rsatadi." }));
    }
    const f = form(n(4) + "Sizning GitHub'ingiz", "Har bir tasdiqlangan reel (video, muqovangiz, ssenariy, tadqiqot, manbalar) sizning O'Z GitHub akkauntingizdagi yopiq «social-automation-content» reposiga yuklanadi. Dastur kodi olingan repoga hech narsa yozilmaydi.",
      box, res, nv.err, nv.row);
    f.addEventListener("submit", nv.run);
    return f;
  }

  async function claudeStep() {
    const acc = await api("/api/accounts");
    const c = acc.claude;
    const box = h("div");
    const res = resultLine();
    const login = h("div", { class: "device" });
    box.append(statusRow(c.installed && c.logged_in, !c.installed ? "Claude Code o'rnatilmagan" : c.logged_in ? `Claude'ga kirilgan${c.email ? ": " + c.email : ""}${c.plan ? " (" + c.plan + ")" : ""}` : "Claude'ga hali kirilmagan",
      !c.installed ? h("span", {}, "O'rnatish: ", h("code", { text: c.hint })) : c.logged_in ? "Ssenariylar sizning o'z Claude obunangiz orqali yoziladi. API kalit kerak emas." : "Pastdagi tugmani bosing va o'z Claude akkauntingiz bilan kiring."),
      statusRow(state.model.ready, state.model.ready ? "O'zbekcha nutqni tanish modeli tayyor" : "Nutqni tanish modeli yuklanmagan", state.model.ready ? `rubaiSTT, ${state.model.size_mb} MB.` : h("span", {}, "O'rnatuvchini qayta ishga tushiring: ", h("code", { text: "./install.sh" }), " (Windows: install.ps1).")));
    if (c.installed) {
      const go = h("button", { class: c.logged_in ? "btn" : "btn primary", type: "button" }, icon("cpu"), c.logged_in ? "Boshqa akkaunt bilan kirish" : "Claude'ga kirish");
      go.addEventListener("click", async () => {
        go.disabled = true; showResult(res, true, "Kirish sahifasi tayyorlanmoqda…");
        try {
          const s = await api("/api/accounts/claude/start", { method: "POST", body: "{}" });
          if (s.state !== "waiting_code" || !s.url) { showResult(res, false, reasonText(s.reason || "not_finished")); go.disabled = false; return; }
          res.className = "sf-result";
          const code = h("input", { type: "text", autocomplete: "off", spellcheck: "false", placeholder: "Kirish sahifasi bergan kod", "aria-label": "Claude kodi" });
          const ok = h("button", { class: "btn primary", type: "button" }, "Tasdiqlash");
          ok.addEventListener("click", async () => {
            ok.disabled = true;
            try { const r = await api("/api/accounts/claude/code", { method: "POST", body: JSON.stringify({ code: code.value }) });
              if (r.state === "done" || r.logged_in) { draw(); return; } showResult(res, false, reasonText(r.reason)); }
            catch (e) { showResult(res, false, reasonText(e.message)); }
            ok.disabled = false;
          });
          login.replaceChildren(h("p", { class: "sf-help", text: "1) Kirish sahifasini oching va o'z Claude akkauntingiz bilan kiring. 2) Sahifa ko'rsatgan kodni nusxalab, shu yerga qo'ying. 3) «Tasdiqlash»." }),
            h("div", { class: "controls" }, extLink(s.url, "Claude kirish sahifasini ochish", "btn primary")), h("div", { class: "field" }, code), h("div", { class: "controls" }, ok));
          window.open(s.url, "_blank", "noopener");
        } catch (e) { showResult(res, false, reasonText(e.message)); }
        go.disabled = false;
      });
      box.append(h("div", { class: "controls" }, go, (() => { const b = h("button", { class: "btn", type: "button" }, icon("refresh"), "Qayta tekshirish"); b.addEventListener("click", draw); return b; })()), login);
    } else {
      box.append(h("div", { class: "controls" }, (() => { const b = h("button", { class: "btn", type: "button" }, icon("refresh"), "Qayta tekshirish"); b.addEventListener("click", draw); return b; })()));
    }
    const nv = nav(async () => { await next(); }, { skip: !(c.installed && c.logged_in) });
    const f = form(n(5) + "Claude va nutq modeli", "Bot har bir foydalanuvchining o'z Claude akkauntidan foydalanadi — shu kompyuterdagi Claude Code orqali. Kirish shu sahifadan qilinadi.",
      box, res, nv.err, nv.row);
    f.addEventListener("submit", nv.run);
    return f;
  }

  async function statsStep() {
    const acc = await api("/api/accounts");
    const ig = acc.instagram, yt = acc.youtube;
    const flash = h("div", { class: "sf-result", role: "status" });
    const q = new URLSearchParams((location.hash.split("?")[1]) || "");
    const r = q.get("r");
    if (r) {
      const [svc, out] = [r.slice(0, 2), r.slice(3)];
      const name = svc === "ig" ? "Instagram" : "YouTube";
      showResult(flash, out === "ok", out === "ok" ? `${name} statistikasi ulandi.` : `${name}: ${reasonText(out)}`);
      history.replaceState(null, "", location.hash.split("?")[0]);
    }
    // Instagram
    const igBox = h("div", { class: "svc-card" }, h("div", { class: "svc-head" }, h("span", { class: "svc-ico ig" }, icon("ig")), h("b", { text: "Instagram statistikasi" })));
    if (ig.connected) {
      const off = h("button", { class: "btn", type: "button" }, "Uzish");
      off.addEventListener("click", async () => { await api("/api/accounts/instagram/disconnect", { method: "POST", body: "{}" }); draw(); });
      igBox.append(statusRow(true, `@${ig.username} ulangan`, ig.page_name ? `Facebook sahifasi: ${ig.page_name}. Faqat statistika o'qiladi.` : "Faqat statistika o'qiladi."), h("div", { class: "controls" }, off));
    } else {
      const id = secretField({ label: "Meta App ID", name: "META_APP_ID", state, plain: true });
      const sec = secretField({ label: "Meta App Secret", name: "META_APP_SECRET", state });
      const igRes = resultLine();
      const saveKeys = h("button", { class: "btn", type: "button" }, "Kalitlarni saqlash");
      saveKeys.addEventListener("click", async () => { try { await saveValues({ META_APP_ID: id, META_APP_SECRET: sec }); state = await api("/api/setup/state"); draw(); } catch (e) { showResult(igRes, false, reasonText(e.message)); } });
      const connect = h("button", { class: "btn primary", type: "button" }, icon("ig"), "Instagram'ni ulash");
      connect.disabled = !ig.keys;
      connect.addEventListener("click", async () => { try { location.href = (await api("/api/accounts/instagram/start", { method: "POST", body: "{}" })).url; } catch (e) { showResult(igRes, false, reasonText(e.message)); } });
      const paste = h("input", { type: "password", autocomplete: "off", placeholder: "Graph API Explorer tokeni", "aria-label": "Instagram token" });
      const pasteBtn = h("button", { class: "btn", type: "button" }, "Ulash");
      pasteBtn.addEventListener("click", async () => { try { await api("/api/accounts/instagram/token", { method: "POST", body: JSON.stringify({ token: paste.value }) }); paste.value = ""; draw(); } catch (e) { showResult(igRes, false, reasonText(e.message)); } });
      igBox.append(guide([
        "Instagram akkauntingiz Business yoki Creator bo'lsin va Facebook sahifangizga bog'langan bo'lsin.",
        h("span", {}, extLink("https://developers.facebook.com/apps/creation/", "developers.facebook.com"), " → Create app (Business) → App settings → Basic: App ID va App Secret'ni pastga qo'ying."),
        h("span", {}, "Facebook Login → Settings → «Valid OAuth Redirect URIs» ga shuni qo'shing: ", h("code", { text: ig.redirect_uri }), " ", copyButton(ig.redirect_uri)),
        "«Instagram'ni ulash» ni bosing va ruxsat bering (faqat o'qish: instagram_basic, instagram_manage_insights)."]),
        h("div", { class: "sf-grid" }, id.el, sec.el), h("div", { class: "controls" }, saveKeys, connect), igRes,
        toggleBlock("Yoki token bilan", h("div", { class: "toggle-body" }, h("p", { class: "sf-help", text: "Graph API Explorer'da ilovangizni tanlab, faqat instagram_basic, instagram_manage_insights, pages_show_list, pages_read_engagement ruxsatlari bilan token oling." }), h("div", { class: "field" }, paste), h("div", { class: "controls" }, pasteBtn))));
    }
    // YouTube
    const ytBox = h("div", { class: "svc-card" }, h("div", { class: "svc-head" }, h("span", { class: "svc-ico yt" }, icon("yt")), h("b", { text: "YouTube statistikasi" })));
    if (yt.connected) {
      const off = h("button", { class: "btn", type: "button" }, "Uzish");
      off.addEventListener("click", async () => { await api("/api/accounts/youtube/disconnect", { method: "POST", body: "{}" }); draw(); });
      ytBox.append(statusRow(true, yt.title ? `«${yt.title}» kanali ulangan` : "YouTube ulangan", "Faqat statistika o'qiladi (youtube.readonly)."), h("div", { class: "controls" }, off));
    } else {
      const ytRes = resultLine();
      const connect = h("button", { class: "btn primary", type: "button" }, icon("yt"), "YouTube'ni ulash");
      connect.disabled = !yt.client;
      connect.addEventListener("click", async () => { try { location.href = (await api("/api/accounts/youtube/start", { method: "POST", body: "{}" })).url; } catch (e) { showResult(ytRes, false, reasonText(e.message)); } });
      const picker = filePicker("JSON faylni tanlash", ".json,application/json", async (text) => {
        try { await api("/api/accounts/youtube/client", { method: "POST", body: JSON.stringify({ text }) }); showResult(ytRes, true, "Google fayli saqlandi. Endi «YouTube'ni ulash» ni bosing."); connect.disabled = false; }
        catch (e) { showResult(ytRes, false, reasonText(e.message)); }
      });
      ytBox.append(h("ol", { class: "guide shots" },
        h("li", {}, h("span", {}, extLink("https://console.cloud.google.com/projectcreate", "Google Cloud"), " → yangi loyiha (nomi ixtiyoriy)."), h("div", { class: "mock" }, h("span", { class: "mock-btn", text: "CREATE" }))),
        h("li", {}, h("span", {}, "APIs & Services → Library: «YouTube Data API v3» va «YouTube Analytics API» → Enable."), h("div", { class: "mock" }, h("span", { class: "mock-chip", text: "YouTube Data API v3" }), h("span", { class: "mock-btn", text: "ENABLE" }))),
        h("li", {}, h("span", {}, "OAuth consent screen → External → o'z emailingizni «Test users» ga qo'shing."), h("div", { class: "mock" }, h("span", { class: "mock-chip", text: "External" }), h("span", { class: "mock-chip", text: "Test users +" }))),
        h("li", {}, h("span", {}, "Credentials → Create credentials → OAuth client ID → turi ", h("b", { text: "Desktop app" }), " → Create → Download JSON."), h("div", { class: "mock" }, h("span", { class: "mock-chip", text: "Desktop app" }), h("span", { class: "mock-btn", text: "DOWNLOAD JSON" }))),
        h("li", {}, h("span", {}, "Yuklab olingan faylni shu yerda tanlang, so'ng «YouTube'ni ulash» → kanalingizni tanlang → Allow."))),
        picker, h("div", { class: "controls" }, connect), ytRes, h("p", { class: "sf-help", text: yt.client ? "Google fayli saqlangan." : "" }));
    }
    const nv = nav(async () => { await next(); }, { skip: true });
    const f = form(n(6) + "Instagram va YouTube statistikasi (ixtiyoriy)", "Bot hech qachon joylamaydi: bu ulanishlar faqat saytdagi statistika uchun. Qoralamalar Buffer orqali tayyorlanadi.",
      flash, h("div", { class: "svc-grid" }, igBox, ytBox), nv.err, nv.row);
    f.addEventListener("submit", nv.run);
    return f;
  }

  async function doneStep() {
    state = await api("/api/setup/state");
    const acc = await api("/api/accounts");
    const v = state.values;
    const rows = [["Sayt paroli", v.DASHBOARD_PASSWORD.set, "o'rnatilgan"], ["Telegram bot", v.TELEGRAM_BOT_TOKEN.set && v.TELEGRAM_ALLOWED_USER_IDS.set, "kiritilgan"],
      ["Buffer", v.BUFFER_API_KEY.set, "kiritilgan"], ["GitHub", acc.github.connected || !!(acc.content && acc.content.remote), acc.github.connected ? `@${acc.github.login}` : "ulangan"],
      ["Claude", acc.claude.installed && acc.claude.logged_in, "tayyor"], ["Nutq modeli", state.model.ready, "tayyor"],
      ["Instagram statistikasi", acc.instagram.connected, "ulangan"], ["YouTube statistikasi", acc.youtube.connected, "ulangan"]];
    const start = h("button", { class: "btn primary", type: "button" }, firstRun ? "Boshlash" : "Saytga qaytish");
    start.addEventListener("click", () => { location.href = "/#/"; });
    return h("div", { class: "setup-form" }, h("h2", { text: firstRun ? n(8) + "Tayyor!" : "Holat" }),
      h("p", { class: "hint", text: (state.dry_run ? "Sinov rejimi yoqiq: Buffer qoralamalari haqiqatda yaratilmaydi, faqat yozib qo'yiladi. " : "Buffer qoralamalari haqiqatda yaratiladi. ")
        + "Bot hech qachon o'zi joylamaydi — qoralama tayyor bo'lgach, tasdiqlab rejalashtirish sizda. Kompyuter yonganda bot o'zi ishga tushadi." }),
      h("ul", { class: "checks" }, rows.map(([l, ok, word]) => h("li", { class: ok ? "ok" : "bad" }, h("span", { class: "mark", text: ok ? "✓" : "!" }), h("div", {}, h("b", { text: l }), h("span", { text: ok ? ` — ${word}` : " — hali sozlanmagan (keyinroq «Sozlamalar»da)" }))))),
      h("div", { class: "setup-nav" }, h("span"), start));
  }

  const page = h("div", { class: "setup-page" }, h("div", { class: "setup-head" }, brand(), themeButton()),
    h("h1", { class: "setup-title", text: firstRun ? "Sozlash" : "Sozlamalar" }),
    h("p", { class: "setup-sub", text: firstRun ? "Bir necha qadam — va bot sizning kompyuteringizda ishlay boshlaydi. Barcha kalitlar faqat shu kompyuterda saqlanadi." : "Istalgan qiymatni o'zgartiring. Saqlangan kalitlar yashirin ko'rinadi." }),
    firstRun ? null : updateCard(), stepper, h("div", { class: "card setup-card" }, body));
  if (firstRun) $app.replaceChildren(page);
  else shell("settings", "Sozlamalar", "Kalitlar, akkauntlar va yangilanish", [], page);
  await draw();
}

function updateCard() {
  const card = h("div", { class: "card update-card" }, h("div", { class: "update-row" }, h("span", { class: "si-mini" }, icon("refresh")), h("div", { class: "grow-text" }, h("b", { text: "Yangilanish" }), h("p", { class: "sf-help", text: "Tekshirilmoqda…" }))));
  const fill = (st) => {
    const text = card.querySelector(".grow-text p");
    const row = card.querySelector(".update-row");
    row.querySelector(".controls")?.remove();
    const list = card.querySelector(".update-list");
    list?.remove();
    if (!st.available) {
      text.textContent = st.reason === "offline" ? "Internet yo'q — keyinroq tekshiriladi." : st.reason === "no_repo" ? "Bu nusxa git orqali o'rnatilmagan — yangilanishni qo'lda oling." : "Sizda eng so'nggi versiya.";
      const b = h("button", { class: "btn", type: "button" }, "Tekshirish");
      b.addEventListener("click", async () => { b.disabled = true; try { fill(await api("/api/update?force=1")); } catch (e) { /* kept */ } b.disabled = false; });
      row.append(h("div", { class: "controls" }, b));
      return;
    }
    card.classList.add("has-update");
    text.textContent = st.can_update ? `Yangilanish bor: ${st.behind} ta o'zgarish. Sozlamalaringiz, kalitlaringiz va reellaringizga tegilmaydi.`
      : st.reason === "diverged" ? "Yangilanish bor, lekin bu papkada qo'lda saqlangan o'zgarishlar bor — avtomatik yangilab bo'lmaydi."
      : "Yangilanish bor, lekin dastur fayllari qo'lda o'zgartirilgan — avtomatik yangilab bo'lmaydi.";
    if (st.can_update) {
      const b = h("button", { class: "btn primary", type: "button" }, "Yangilash");
      b.addEventListener("click", async () => {
        b.disabled = true; text.textContent = "Yangilanmoqda… (bir necha daqiqa)";
        try { const r = await api("/api/update", { method: "POST", body: "{}" });
          if (r.ok) { text.textContent = "Yangilandi! Xizmat qayta ishga tushmoqda — sahifa o'zi yangilanadi."; setTimeout(() => location.reload(), 9000); }
          else { text.textContent = "Yangilab bo'lmadi. Keyinroq qayta urinib ko'ring."; b.disabled = false; } }
        catch (e) { text.textContent = "Yangilab bo'lmadi. Keyinroq qayta urinib ko'ring."; b.disabled = false; }
      });
      row.append(h("div", { class: "controls" }, b));
    }
    if (st.commits.length) card.append(h("ul", { class: "update-list" }, st.commits.slice(0, 5).map((c) => h("li", { text: c.title }))));
  };
  api("/api/update").then(fill).catch(() => fill({ available: false, reason: "offline" }));
  return card;
}

// ---------------------------------------------------------------- internet state (shown everywhere)
const netBanner = h("div", { class: "net-banner", role: "status", hidden: true }, h("span", { class: "pulse" }), h("span", { text: "Internet yo'q — kutyapman. Ulanish tiklanishi bilan hammasi o'zi davom etadi." }));
document.body.append(netBanner);
async function checkNet() {
  try { const r = await fetch("/api/net", { credentials: "same-origin" }); const d = await r.json(); netBanner.hidden = d.online !== false; }
  catch (e) { netBanner.hidden = false; }
}
checkNet(); setInterval(checkNet, 20000);

// ---------------------------------------------------------------- login
function renderLogin(message) {
  const input = h("input", { type: "password", id: "pw", autocomplete: "current-password", placeholder: "Parol", "aria-label": "Parol", required: true });
  const err = h("div", { class: "err", role: "alert", text: message || "" });
  const eye = h("button", { class: "btn icon eye", type: "button", "aria-label": "Parolni ko'rsatish" }, icon("eye"));
  eye.addEventListener("click", () => { input.type = input.type === "password" ? "text" : "password"; });
  const submit = h("button", { class: "btn primary", type: "submit" }, "Kirish");
  const form = h("form", {}, h("div", { class: "field" }, input, eye), err, submit);
  form.addEventListener("submit", async (e) => {
    e.preventDefault(); submit.disabled = true; err.textContent = "";
    try { await api("/api/login", { method: "POST", body: JSON.stringify({ password: input.value }) }); route(); }
    catch (ex) { err.textContent = ex.status === 429 ? "Juda ko'p urinish. 10 daqiqadan keyin qayta urinib ko'ring." : "Parol noto'g'ri."; submit.disabled = false; input.select(); }
  });
  $app.replaceChildren(h("div", { class: "login" }, h("div", { class: "corner-theme" }, themeButton()), h("div", { class: "card" }, brand(), h("h1", { text: "Xush kelibsiz" }), h("p", { text: "YouTube va Instagram statistikangizni ko'rish uchun parolni kiriting." }), form)));
  input.focus();
}

// ---------------------------------------------------------------- router
async function route() {
  closePop(); hideTip();
  const hash = location.hash || "#/";
  try {
    const sess = await api("/api/session");
    if (location.pathname === "/setup") {
      if (!sess.configured || sess.authenticated) { await renderSetup(!sess.configured); return; }
      renderLogin(); return;
    }
    if (!sess.configured) { location.href = "/setup"; return; }
    if (!sess.authenticated) { renderLogin(); return; }
    $app.classList.add("loading");
    if (hash.startsWith("#/video/")) await renderVideo(hash.slice(8));
    else if (hash.startsWith("#/reel/")) await renderReel(hash.slice(7));
    else if (hash === "#/videos") await renderVideos();
    else if (hash === "#/insights") await renderInsights();
    else if (hash === "#/pipeline") await renderPipeline();
    else if (hash === "#/skills") await renderSkills();
    else if (hash === "#/repo") await renderRepo();
    else if (hash.startsWith("#/settings")) await renderSetup(false, hash.slice(11).split("?")[0] || null);
    else await renderOverview();
  } catch (e) {
    if (e.message !== "login") $app.replaceChildren(h("div", { class: "login" }, h("div", { class: "card" }, brand(), h("h1", { text: "Ulanishda muammo" }), h("p", { text: "Server javob bermadi. Bir ozdan keyin sahifani yangilang." }))));
  } finally { $app.classList.remove("loading"); }
}
window.addEventListener("hashchange", route);
setInterval(async () => {
  if (openPop || document.visibilityState !== "visible" || document.querySelector(".login") || document.querySelector(".setup-page")) return;   // never wipe a form being filled
  silentRefresh = true;
  try { await route(); } finally { silentRefresh = false; }
}, 60000);
route();

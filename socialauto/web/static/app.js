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
  key: "M15 7a4 4 0 1 1-3.9 5H8v3H5v3H2v-4l6.1-6.1A4 4 0 0 1 15 7zM16 8h.01",
  send: "M22 2 11 13M22 2l-7 20-4-9-9-4z",
  layers: "M12 2 2 7l10 5 10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
  plus: "M12 5v14M5 12h14",
  cpu: "M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3M6 6h12v12H6zM10 10h4v4h-4z",
  flag: "M4 22V4M4 4h12l-2 4 2 4H4",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  cloud: "M7 18a5 5 0 1 1 .9-9.9A6 6 0 0 1 19 10a4 4 0 0 1 0 8z",
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

// ---------------------------------------------------------------- theme (dark / light)
function applyTheme(theme) { document.documentElement.dataset.theme = theme; }
applyTheme(localStorage.getItem("sa_theme") || (window.matchMedia && matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));
function themeButton() {
  const sun = icon("sun"); sun.setAttribute("class", "sun");
  const moon = icon("moon"); moon.setAttribute("class", "moon");
  const b = h("button", { class: "btn icon theme-btn", type: "button", "aria-label": "Yorug' / qorong'i rejim", title: "Yorug' / qorong'i rejim" }, sun, moon);
  b.addEventListener("click", () => { const next = document.documentElement.dataset.theme === "light" ? "dark" : "light"; localStorage.setItem("sa_theme", next); applyTheme(next); route(); });
  return b;
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
function closePop() { if (openPop) { openPop.remove(); openPop = null; } }
document.addEventListener("pointerdown", (e) => { if (openPop && !openPop.contains(e.target) && !e.target.closest("[data-popper]")) closePop(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePop(); });

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
  const svg = s("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "#1a1505", "stroke-width": "2.6", "stroke-linecap": "round", "stroke-linejoin": "round" });
  svg.append(s("path", { d: "M4 17 L10 11 L14 14 L20 7" })); mark.append(svg);
  return h("div", { class: "brand" }, mark, h("div", {}, "Social Automation", h("small", { text: "YouTube + Instagram" })));
}
function shell(active, title, sub, controls, body) {
  const nav = (cls) => h("nav", { class: cls, "aria-label": "Bo'limlar" },
    ROUTES.map((r) => h("a", { href: r.hash, "aria-current": r.key === active ? "page" : null }, icon(r.icon), h("span", { text: r.label }))));
  const logout = h("button", { class: "btn", type: "button" }, icon("logout"), "Chiqish");
  logout.addEventListener("click", async () => { await api("/api/logout", { method: "POST" }).catch(() => {}); renderLogin(); });
  const side = h("aside", { class: "side" }, brand(), nav("nav"), h("div", { class: "side-foot" }, themeButton(), logout));
  const mobileBrand = h("div", { class: "mobile-brand", style: "justify-content:space-between" }, brand(), themeButton());
  const main = h("main", { class: "main" }, mobileBrand,
    h("div", { class: "topbar" }, h("div", {}, h("h1", { text: title }), sub ? h("div", { class: "sub" }, sub) : null), h("div", { class: "controls" }, controls)),
    body);
  const keep = silentRefresh ? window.scrollY : 0;
  $app.replaceChildren(h("div", { class: "shell" }, side, main), nav("bottom-nav"));
  window.scrollTo(0, keep);
}
function updatedNode(st) {
  const ms = Object.values(st.platforms).filter((p) => p.connected).map((p) => p.updated_minutes).filter((m) => m !== null);
  const m = ms.length ? Math.max(...ms) : null;
  const anyConnected = Object.values(st.platforms).some((p) => p.connected);
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
      tableBox.replaceChildren(h("div", { class: "chart-empty", text: Object.values(st.platforms).some((p) => p.connected) ? "Videolar statistikasi yig'ilmoqda…" : "Hisoblar ulangach, har bir video statistikasi shu yerda ko'rinadi. Hech qanday soxta raqam ko'rsatilmaydi." }));
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

// ---------------------------------------------------------------- repo (GitHub)
function catList(groups) {
  return h("div", { class: "cat-list" }, groups.map((g) => {
    const btn = h("button", { class: "cat-btn", type: "button", "aria-expanded": "false" }, h("span", { text: g.label }), h("span", { class: "n", text: `${g.count} ta fayl` }), icon("chevron"));
    btn.addEventListener("click", () => btn.setAttribute("aria-expanded", String(btn.getAttribute("aria-expanded") !== "true")));
    return h("div", { class: "cat" }, btn, h("ul", { class: "file-list" }, g.files.map((f) => h("li", { text: f }))));
  }));
}
async function renderRepo() {
  const r = await api("/api/repo");
  if (!r.is_repo) { shell("repo", "GitHub", null, [], h("div", { class: "chart-empty", text: "Bu papka hali git loyihasi emas." })); return; }
  const conn = r.connected
    ? h("div", { class: "card" }, h("div", { class: "big-state" }, h("div", { class: "glyph ok" }, icon("cloud")), h("div", {}, h("h2", { text: `${r.host} ulangan` }), h("p", { class: "hint", style: "margin:4px 0 0", text: r.repo || "" }))),
        h("div", { class: "kv" }, h("div", {}, h("span", { text: "Loyiha" }), h("b", { text: r.repo || "—" })), h("div", {}, h("span", { text: "Tarmoq (branch)" }), h("b", { text: r.branch })),
          h("div", {}, h("span", { text: "Oxirgi yuklash" }), h("b", { text: r.last_push || "hali yuklanmagan" })), h("div", {}, h("span", { text: "Yuklanmagan o'zgarishlar" }), h("b", { text: `${r.ahead} ta` }))))
    : h("div", { class: "card" }, h("div", { class: "big-state" }, h("div", { class: "glyph off" }, icon("cloudOff")), h("div", {}, h("h2", { text: "GitHub hali ulanmagan" }), h("p", { class: "hint", style: "margin:4px 0 0", text: "Bo'sh GitHub repo oching va havolasini yuboring — men uni ulab, hammasini yuklayman." }))),
        h("div", { class: "kv" }, h("div", {}, h("span", { text: "Tarmoq (branch)" }), h("b", { text: r.branch })), h("div", {}, h("span", { text: "Saqlangan o'zgarishlar" }), h("b", { text: `${r.total_commits} ta` })),
          h("div", {}, h("span", { text: "Birinchi yuklashda ketadi" }), h("b", { text: `${r.ahead} ta o'zgarish` }))));
  const allPending = r.ahead && r.ahead >= r.total_commits;   // never pushed: the whole history goes
  const lastGroups = r.ahead_commits.length ? mergeGroups(r.ahead_commits) : [];
  const pending = h("div", { class: "card" }, h("h2", { text: "Keyingi yuklashda ketadi" }),
    h("p", { class: "hint", text: !r.ahead ? "Hamma saqlangan o'zgarishlar GitHub'da bor."
      : allPending ? `Hammasi: ${r.ahead} ta saqlangan o'zgarish (tarixi o'ng tomonda). GitHub ulangach, birinchi yuklashda ketadi.`
      : `${r.ahead} ta saqlangan o'zgarish hali GitHub'da yo'q:` }),
    r.ahead && !allPending ? h("ul", { class: "timeline" }, r.ahead_commits.slice(0, 10).map((c) => h("li", { class: "pending" }, h("div", { class: "t-title", text: c.title }), h("div", { class: "t-meta" }, h("span", { text: c.when }), h("span", { text: `${c.files} ta fayl` }))))) : null,
    lastGroups.length ? h("div", {}, h("p", { class: "hint", style: "margin:14px 0 0", text: "Ulardagi fayllar, turlari bo'yicha (bosib, nomlarini ko'ring):" }), catList(lastGroups)) : null,
    h("h2", { class: "section-gap", text: "Hali saqlanmagan o'zgarishlar" }),
    r.uncommitted.count ? h("div", {}, h("p", { class: "hint", text: `${r.uncommitted.count} ta fayl o'zgargan — saqlangach (commit), ular ham yuklanadi.` }), catList(r.uncommitted.groups))
      : h("p", { class: "hint", text: "Yo'q — hamma narsa saqlangan." }));
  const never = h("div", { class: "card" }, h("h2", { text: "Hech qachon yuklanmaydi" }), h("p", { class: "hint", text: "Bular faqat shu kompyuterda qoladi — GitHub'ga hech qachon chiqmaydi:" }),
    h("ul", { class: "never" }, r.never.map((n) => h("li", {}, icon("shield"), h("div", {}, h("b", { text: n.title }), n.detail)))));
  const history = h("div", { class: "card" }, h("h2", { text: "Oxirgi o'zgarishlar tarixi" }), h("p", { class: "hint", text: `Oxirgi ${r.history.length} ta saqlangan o'zgarish, eng yangisi tepada.` }),
    h("ul", { class: "timeline" }, r.history.map((c) => h("li", { class: r.ahead_commits.some((a) => a.short === c.short) ? "pending" : "" }, h("div", { class: "t-title", text: c.title }),
      h("div", { class: "t-meta" }, h("span", { text: c.when }), h("span", { text: `${c.files} ta fayl` }), h("span", { class: "short-hash", text: c.short }))))));
  const body = h("div", {}, h("div", { class: "repo-grid" }, conn, never), h("div", { class: "repo-grid section-gap" }, pending, history));
  shell("repo", "GitHub", "GitHub'ga nima yuklanadi va nima yuklanmaydi — oddiy so'zlar bilan", [], body);
}
function mergeGroups(list) {
  const map = new Map();
  for (const c of list) for (const g of c.groups) { const cur = map.get(g.label) || new Set(); g.files.forEach((f) => cur.add(f)); map.set(g.label, cur); }
  const order = ["Kod", "Sayt", "Hujjatlar", "Testlar", "Sozlamalar", "Media/rasmlar", "Boshqa"];
  return order.filter((k) => map.has(k)).map((k) => ({ label: k, count: map.get(k).size, files: [...map.get(k)].sort() }));
}

// ---------------------------------------------------------------- setup ("Sozlash") and settings ("Sozlamalar")
const REASONS = {
  too_short: "Parol kamida 8 belgidan iborat bo'lsin.", bad_token: "Token ko'rinishi noto'g'ri. BotFather bergan tokenni to'liq nusxalang (masalan 123456:ABC...).",
  bad_ids: "ID faqat raqamlardan iborat bo'ladi; bir nechta bo'lsa vergul bilan ajrating.", bad_app_id: "App ID faqat raqamlardan iborat.",
  missing: "Avval qiymatni kiriting.", rejected: "Xizmat bu qiymatni qabul qilmadi — qayta nusxalab ko'ring.",
  network: "Internetga ulanib bo'lmadi. Ulanishni tekshirib, qayta urinib ko'ring.", password_first: "Avval parolni o'rnating.",
  local_only: "Sozlash sahifasi faqat shu kompyuterning o'zidan ochiladi.", too_long: "Qiymat juda uzun.",
};
function reasonText(r) { return REASONS[r] || "Saqlab bo'lmadi. Qayta urinib ko'ring."; }
const SETUP_STEPS = [
  { key: "password", icon: "key", label: "Parol" }, { key: "telegram", icon: "send", label: "Telegram" },
  { key: "buffer", icon: "layers", label: "Buffer" }, { key: "extra", icon: "plus", label: "Qo'shimcha" },
  { key: "claude", icon: "cpu", label: "Claude" }, { key: "done", icon: "flag", label: "Tayyor" },
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
function showResult(box, ok, text) { box.className = `sf-result ${ok ? "good" : "bad"}`; box.replaceChildren(h("span", { text: ok ? "✓" : "!" , class: "mark" }), h("span", { text })); }

async function renderSetup(firstRun) {
  let state;
  try { state = await api("/api/setup/state"); } catch (e) {
    if (e.status === 403) { $app.replaceChildren(h("div", { class: "login" }, h("div", { class: "card" }, brand(), h("h1", { text: "Sozlash" }), h("p", { text: reasonText("local_only") })))); return; }
    throw e;
  }
  let step = firstRun ? (state.values.DASHBOARD_PASSWORD.set ? 1 : 0) : 1;
  const body = h("div", { class: "setup-body" });
  const stepper = h("ol", { class: "setup-steps" });
  const draw = async () => {
    stepper.replaceChildren(...SETUP_STEPS.map((s, i) => {
      const li = h("li", { class: i < step ? "done" : i === step ? "now" : "" }, h("span", { class: "si" }, icon(i < step ? "check" : s.icon)), h("span", { class: "sl", text: s.label }));
      if (!firstRun || i < step) { li.classList.add("go"); li.tabIndex = 0; li.addEventListener("click", () => { if (i === 0 && !firstRun) return; step = i; draw(); }); }
      return li;
    }));
    body.replaceChildren(await stepView(SETUP_STEPS[step].key));
    body.querySelector("input")?.focus();
  };
  const next = async () => { state = await api("/api/setup/state"); step = Math.min(SETUP_STEPS.length - 1, step + 1); await draw(); };
  const nav = (onNext, { skip = false, label = "Davom etish" } = {}) => {
    const err = h("div", { class: "err", role: "alert" });
    const go = h("button", { class: "btn primary", type: "submit" }, label);
    const row = h("div", { class: "setup-nav" }, step > (firstRun ? 1 : 1) ? (() => { const b = h("button", { class: "btn", type: "button" }, "Orqaga"); b.addEventListener("click", () => { step -= 1; draw(); }); return b; })() : h("span"),
      h("div", { class: "controls" }, skip ? (() => { const b = h("button", { class: "btn", type: "button" }, "Keyinroq"); b.addEventListener("click", next); return b; })() : null, go));
    return { row, err, go, run: async (e) => { e && e.preventDefault(); err.textContent = ""; go.disabled = true; try { await onNext(); } catch (ex) { err.textContent = reasonText(ex.message); } go.disabled = false; } };
  };
  const saveValues = async (fields) => {
    const values = {};
    for (const [k, f] of Object.entries(fields)) if (f.changed()) values[k] = f.value();
    if (Object.keys(values).length) await api("/api/setup/save", { method: "POST", body: JSON.stringify({ values }) });
  };
  async function stepView(key) {
    if (key === "password") {
      const a = h("input", { type: "password", autocomplete: "new-password", placeholder: "Yangi parol (kamida 8 belgi)", "aria-label": "Yangi parol" });
      const b = h("input", { type: "password", autocomplete: "new-password", placeholder: "Parolni takrorlang", "aria-label": "Parolni takrorlang" });
      const n = nav(async () => {
        if (a.value.length < 8) throw new Error("too_short");
        if (a.value !== b.value) { throw new Error("mismatch"); }
        await api("/api/setup/password", { method: "POST", body: JSON.stringify({ password: a.value }) });
        await next();
      });
      REASONS.mismatch = "Ikkala parol bir xil emas.";
      const form = h("form", { class: "setup-form" }, h("h2", { text: "1. Sayt paroli" }),
        h("p", { class: "hint", text: "Bu parol bilan statistika saytiga kirasiz. U faqat shu kompyuterda, .env faylida saqlanadi." }),
        h("div", { class: "field" }, a), h("div", { class: "field" }, b), n.err, n.row);
      form.addEventListener("submit", n.run);
      return form;
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
      const n = nav(async () => { await saveValues({ TELEGRAM_BOT_TOKEN: token, TELEGRAM_ALLOWED_USER_IDS: ids }); await next(); }, { skip: true });
      const form = h("form", { class: "setup-form" }, h("h2", { text: "2. Telegram bot" }), h("p", { class: "hint", text: "Bot sizga mavzular, ssenariy, video va qoralamalar haqida yozadi. Faqat siz kiritgan ID egalari u bilan ishlay oladi." }),
        token.el, h("div", { class: "controls" }, check), res, ids.el, n.err, n.row);
      form.addEventListener("submit", n.run);
      return form;
    }
    if (key === "buffer") {
      const k = secretField({ label: "Buffer API kaliti", name: "BUFFER_API_KEY", state, help: "publish.buffer.com → Settings → API → Create API key. Bot u bilan faqat QORALAMA yaratadi — hech narsani o'zi joylamaydi yoki rejalashtirmaydi." });
      const res = resultLine();
      const check = h("button", { class: "btn", type: "button" }, icon("check"), "Tekshirish");
      check.addEventListener("click", async () => {
        check.disabled = true;
        try { const r = await api("/api/setup/check/buffer", { method: "POST", body: JSON.stringify({ value: k.changed() ? k.value() : "" }) });
          showResult(res, r.ok, r.ok ? (r.channels.length ? "Ulangan kanallar: " + r.channels.map((c) => `${c.service}${c.name ? " — " + c.name : ""}`).join(", ") : "Kalit ishlaydi, lekin Buffer'da kanal ulanmagan.") : reasonText(r.reason)); }
        catch (e) { showResult(res, false, reasonText(e.message)); }
        check.disabled = false;
      });
      const n = nav(async () => { await saveValues({ BUFFER_API_KEY: k }); await next(); }, { skip: true });
      const form = h("form", { class: "setup-form" }, h("h2", { text: "3. Buffer" }), h("p", { class: "hint", text: "Tayyor reel Buffer'da Instagram, YouTube va LinkedIn uchun qoralama bo'lib turadi; tasdiqlab rejalashtirish sizda." }),
        k.el, h("div", { class: "controls" }, check), res, n.err, n.row);
      form.addEventListener("submit", n.run);
      return form;
    }
    if (key === "extra") {
      const fields = {
        META_APP_ID: secretField({ label: "Meta App ID", name: "META_APP_ID", state, plain: true, help: "Instagram statistikasi uchun (ixtiyoriy): developers.facebook.com → ilovangiz → App settings → Basic." }),
        META_APP_SECRET: secretField({ label: "Meta App Secret", name: "META_APP_SECRET", state }),
        PEXELS_API_KEY: secretField({ label: "Pexels kaliti", name: "PEXELS_API_KEY", state, help: "Ko'proq bepul video uchun (ixtiyoriy): pexels.com/api." }),
        PIXABAY_API_KEY: secretField({ label: "Pixabay kaliti", name: "PIXABAY_API_KEY", state, help: "Ixtiyoriy: pixabay.com/api/docs (kirgandan keyin)." }),
      };
      const n = nav(async () => { await saveValues(fields); await next(); }, { skip: true });
      const form = h("form", { class: "setup-form" }, h("h2", { text: "4. Qo'shimcha (ixtiyoriy)" }), h("p", { class: "hint", text: "Bularsiz ham hammasi ishlaydi. Keyinroq «Sozlamalar» sahifasida qo'shish mumkin." }),
        h("div", { class: "sf-grid" }, Object.values(fields).map((f) => f.el)), n.err, n.row);
      form.addEventListener("submit", n.run);
      return form;
    }
    if (key === "claude") {
      const box = h("div");
      const fill = (c, m) => {
        box.replaceChildren(
          h("div", { class: `status-row ${c.installed && c.logged_in ? "good" : "bad"}` }, h("span", { class: "mark", text: c.installed && c.logged_in ? "✓" : "!" }),
            h("div", {}, h("b", { text: !c.installed ? "Claude Code o'rnatilmagan" : c.logged_in ? `Claude'ga kirilgan${c.plan ? " (" + c.plan + ")" : ""}` : "Claude'ga kirilmagan" }),
              h("p", { class: "sf-help" }, !c.installed ? ["O'rnatish: ", h("code", { text: "npm install -g @anthropic-ai/claude-code" }), " (yoki claude.ai/download)."]
                : c.logged_in ? "Ssenariylar sizning o'z Claude akkauntingiz orqali yoziladi (API kalit kerak emas)."
                : ["Terminalda ", h("code", { text: "claude" }), " yozing va o'z akkauntingiz bilan kiring. Keyin «Qayta tekshirish»ni bosing."]))),
          h("div", { class: `status-row ${m.ready ? "good" : "bad"}` }, h("span", { class: "mark", text: m.ready ? "✓" : "!" }),
            h("div", {}, h("b", { text: m.ready ? "O'zbekcha nutqni tanish modeli tayyor" : "Nutqni tanish modeli yuklanmagan" }),
              h("p", { class: "sf-help" }, m.ready ? `rubaiSTT, ${m.size_mb} MB.` : ["O'rnatish skriptini qayta ishga tushiring: ", h("code", { text: "./install.sh" }), " (Windows: install.ps1)."]))));
      };
      fill(state.claude, state.model);
      const re = h("button", { class: "btn", type: "button" }, icon("refresh"), "Qayta tekshirish");
      re.addEventListener("click", async () => { re.disabled = true; try { fill(await api("/api/setup/check/claude", { method: "POST", body: "{}" }), await api("/api/setup/check/model", { method: "POST", body: "{}" })); } catch (e) { /* kept */ } re.disabled = false; });
      const n = nav(async () => { await next(); });
      const form = h("form", { class: "setup-form" }, h("h2", { text: "5. Claude va nutq modeli" }), h("p", { class: "hint", text: "Bot har bir foydalanuvchining o'z Claude akkauntidan foydalanadi — shu kompyuterdagi Claude Code orqali." }),
        box, h("div", { class: "controls" }, re), n.err, n.row);
      form.addEventListener("submit", n.run);
      return form;
    }
    const v = state.values;
    const rows = [["Sayt paroli", v.DASHBOARD_PASSWORD.set], ["Telegram bot", v.TELEGRAM_BOT_TOKEN.set && v.TELEGRAM_ALLOWED_USER_IDS.set], ["Buffer", v.BUFFER_API_KEY.set],
      ["Claude", state.claude.installed && state.claude.logged_in], ["Nutq modeli", state.model.ready]];
    const start = h("button", { class: "btn primary", type: "button" }, firstRun ? "Boshlash" : "Saytga qaytish");
    start.addEventListener("click", () => { location.href = "/#/"; });
    return h("div", { class: "setup-form" }, h("h2", { text: firstRun ? "6. Tayyor!" : "Holat" }),
      h("p", { class: "hint", text: "Sinov rejimi yoqiq: Buffer qoralamalari haqiqatda yaratilmaydi, faqat yozib qo'yiladi. Bot hech qachon o'zi joylamaydi — qoralama tayyor bo'lgach, tasdiqlab rejalashtirish sizda. O'zgarishlar saqlangach bot o'zi qayta ishga tushadi." }),
      h("ul", { class: "checks" }, rows.map(([l, ok]) => h("li", { class: ok ? "ok" : "bad" }, h("span", { class: "mark", text: ok ? "✓" : "!" }), h("div", {}, h("b", { text: l }), h("span", { text: ok ? " — tayyor" : " — hali sozlanmagan (keyinroq «Sozlamalar»da)" }))))),
      h("div", { class: "setup-nav" }, h("span"), start));
  }
  const page = h("div", { class: "setup-page" }, h("div", { class: "setup-head" }, brand(), themeButton()),
    h("h1", { class: "setup-title", text: firstRun ? "Sozlash" : "Sozlamalar" }),
    h("p", { class: "setup-sub", text: firstRun ? "Bir necha qadam — va bot sizning kompyuteringizda ishlay boshlaydi. Barcha kalitlar faqat shu kompyuterda saqlanadi." : "Istalgan qiymatni o'zgartiring. Saqlangan kalitlar yashirin ko'rinadi." }),
    stepper, h("div", { class: "card setup-card" }, body));
  if (firstRun) $app.replaceChildren(page);
  else shell("settings", "Sozlamalar", "Kalitlar va ulanishlar", [], page);
  await draw();
}

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
  $app.replaceChildren(h("div", { class: "login" }, h("div", { class: "card" }, brand(), h("h1", { text: "Xush kelibsiz" }), h("p", { text: "YouTube va Instagram statistikangizni ko'rish uchun parolni kiriting." }), form)));
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
    else if (hash === "#/settings") await renderSetup(false);
    else await renderOverview();
  } catch (e) {
    if (e.message !== "login") $app.replaceChildren(h("div", { class: "login" }, h("div", { class: "card" }, brand(), h("h1", { text: "Ulanishda muammo" }), h("p", { text: "Server javob bermadi. Bir ozdan keyin sahifani yangilang." }))));
  } finally { $app.classList.remove("loading"); }
}
window.addEventListener("hashchange", route);
setInterval(async () => {
  if (openPop || document.visibilityState !== "visible" || document.querySelector(".login")) return;
  silentRefresh = true;
  try { await route(); } finally { silentRefresh = false; }
}, 60000);
route();

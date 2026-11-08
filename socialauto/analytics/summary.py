"""/stats: a short Uzbek summary and the dashboard link."""

from __future__ import annotations

from datetime import datetime

from ..db import KV
from .collector import TASHKENT, UPDATED_KEY
from .metrics import Metrics

NAMES = {"youtube": "▶️ YouTube", "instagram": "📸 Instagram"}


def num(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    for div, suf in ((1e6, " mln"), (1e3, " ming")):
        if abs(v) >= div:
            return f"{v / div:.1f}".rstrip("0").rstrip(".") + suf
    return f"{v:.0f}"


def signed(v) -> str:
    return "—" if v is None else ("+" if v >= 0 else "−") + num(abs(v))


def ago(at: datetime | None, now: datetime) -> str:
    if not at:
        return "hali yangilanmagan"
    m = int((now - at).total_seconds() // 60)
    return "hozirgina" if m < 1 else f"{m} daqiqa oldin" if m < 60 else f"{m // 60} soat oldin"


def stats_text(app) -> str:
    s = app.settings
    now = app.clock()
    metrics = Metrics(app.db, now.astimezone(TASHKENT).date())
    ov = metrics.overview(7)
    kv = KV(app.db)
    lines = ["📈 <b>Statistika</b> (oxirgi 7 kun)"]
    for p in ("youtube", "instagram"):
        connected = s.resolve(getattr(s, p).token_file).exists()
        o = ov["platforms"][p]
        if not connected:
            lines.append(f"{NAMES[p]}: ulanmagan (docs/OWNER_TODO.md)")
        elif not o:
            lines.append(f"{NAMES[p]}: ulangan, birinchi ma'lumot yig'ilmoqda")
        else:
            from ..db import parse_iso
            upd = kv.get(UPDATED_KEY.format(p))
            lines.append(f"{NAMES[p]}: {num(o['followers'])} obunachi ({signed(o['followers_growth']['week'])} hafta), "
                         f"{num(o['views_period'])} ko'rish, faollik {o['engagement_rate'] if o['engagement_rate'] is not None else '—'}%"
                         f" · {ago(parse_iso(upd) if upd else None, now)}")
    posted = len([v for v in app.store.videos(["posted", "partial"], limit=1000)])
    lines.append(f"🎬 Joylangan videolar: {posted}")
    lines.append(f"🌐 Dashboard: {s.web.public_url}")
    return "\n".join(lines)

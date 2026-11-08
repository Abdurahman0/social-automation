"""The reel-mistakes checklist: run before AND after every render; the document grows with every lesson.

`docs/reel-mistakes-checklist.md` = the fixed rules of the owner's flow + every lesson the bot recorded (script,
voice, render, quality and the owner's own notes). It is rewritten whenever the checklist runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from ..lessons import STAGE_UZ, Lessons
from . import layout as layout_mod
from .script import MAX_SECONDS, MIN_SECONDS, PARTS, problems as script_problems

BASE_RULES = [
    ("Ssenariy", "8 qism tartibda: hook · kirish · asosiy 1 · ochiq savol · asosiy 2 · ochiq savol · asosiy 3 · CTA."),
    ("Ssenariy", f"Uzunlik {MIN_SECONDS}–{MAX_SECONDS} soniya."),
    ("Ssenariy", "Javob yoki eng kuchli fakt birinchi 5 soniyada aytiladi."),
    ("Ssenariy", "Har bir atamadan keyin oddiy «ya'ni ...» izohi bor."),
    ("Ssenariy", "Mavzu faqat suv / oqova suv; har bir raqamning manbasi bor."),
    ("B-roll", "Faqat haqiqiy video va fotosuratlar: multfilm, 3D va sun'iy intellekt rasmlari yo'q."),
    ("B-roll", "Har bir klipning manbasi va litsenziyasi yozib qo'yilgan; NC/ND litsenziyalar ishlatilmaydi."),
    ("Joylashuv", "Pastki ~20% va o'ng chetda matn yo'q (Instagram tugmalari zonasi)."),
    ("Joylashuv", "Sarlavha tepada, subtitrlar ko'z darajasida."),
    ("Ovoz", "Ovoz: highpass 80 Hz, kompressor; musiqa ovoz ostida pasayadi; umumiy −14 LUFS."),
    ("Ovoz", "Subtitrlar va sahnalar aytilgan so'zlarga moslangan."),
    ("Render", "Har render yangi _vN; eski versiya hech qachon ustidan yozilmaydi."),
    ("Render", "8 qism chegarasidagi kadrlar tekshiriladi: qora, bo'sh yoki xira emas."),
    ("Render", "Muqovani bot qilmaydi — egasi yuboradi."),
]


@dataclass
class Report:
    stage: str                                        # before | after
    checks: list[dict] = field(default_factory=list)

    def add(self, rule: str, ok: bool, detail: str) -> None:
        self.checks.append({"rule": rule, "ok": bool(ok), "detail": detail})

    @property
    def passed(self) -> bool:
        return all(c["ok"] for c in self.checks)

    @property
    def problems(self) -> list[str]:
        return [f"{c['rule']}: {c['detail']}" for c in self.checks if not c["ok"]]

    def as_dict(self) -> dict:
        return {"stage": self.stage, "passed": self.passed, "checks": self.checks}


def write_document(path: Path, lessons: Lessons | None) -> Path:
    lines = ["# Reel xatolari ro'yxati (checklist)", "",
             "Bot har renderdan **oldin va keyin** shu ro'yxat bo'yicha tekshiradi. Yangi xato topilsa, u shu yerga",
             "qo'shiladi (darslar bazasidan) va keyingi safar takrorlanmaydi.", "", "## Doimiy qoidalar", ""]
    lines += [f"- [{group}] {text}" for group, text in BASE_RULES]
    if lessons is not None:
        rows = [r for r in lessons.all() if r["stage"] in ("script", "voice", "render", "quality", "owner", "idea")]
        if rows:
            lines += ["", "## Darslardan (bot qilgan xatolar)", ""]
            for r in rows[:120]:
                fix = f" — yechim: {r['fix']}" if r["fix"] else ""
                lines.append(f"- [{STAGE_UZ.get(r['stage'], r['stage'])}] {r['text']} ({r['count']} marta){fix}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def before_render(script: dict, clips: list, voice_seconds: float, coverage: float, lay: dict,
                  title_px: int, info_px: int, wps: float) -> Report:
    rep = Report("before")
    sp = script_problems(script, wps)
    rep.add("8 qismli ssenariy qoidalari", not sp, "hammasi joyida" if not sp else "; ".join(sp))
    rep.add("Har qismga haqiqiy B-roll", len(clips) == len(PARTS) and all(c.kind in ("video", "image") for c in clips),
            f"{len(clips)} ta klip, {sum(c.kind == 'video' for c in clips)} tasi video")
    missing = [c.part for c in clips if not (c.license and c.source_url)]
    rep.add("Manba va litsenziya yozilgan", not missing, "hammasida bor" if not missing else f"yo'q: {', '.join(missing)}")
    from .broll import AI_WORDS, license_ok
    bad = [c.part for c in clips if AI_WORDS.search(c.title or "") or (c.provider == "Wikimedia Commons"
                                                                        and not license_ok(c.license))]
    rep.add("Multfilm / 3D / AI rasm yo'q, ruxsat etilgan litsenziya", not bad, "joyida" if not bad else ", ".join(bad))
    sz = layout_mod.safe_zone_problems(lay)
    rep.add("Xavfsiz zona (pastki 20%, o'ng chet)", not sz, "matn xavfsiz zonada" if not sz else "; ".join(sz))
    fit = layout_mod.text_fit_problems(script["title"], lay["title"], title_px, 3)
    for p in script["parts"]:
        if p.get("info"):
            fit += layout_mod.text_fit_problems(p["info"]["label"], lay["info"], int(info_px * 0.3), 3)
    rep.add("Matnlar o'z qutisiga sig'adi", not fit, "sig'adi" if not fit else "; ".join(fit))
    rep.add("Ovoz uzunligi", MIN_SECONDS - 5 <= voice_seconds <= MAX_SECONDS + 1,
            f"{voice_seconds:.1f} soniya (kerak {MIN_SECONDS}–{MAX_SECONDS})")
    rep.add("Ovoz matnga mos", coverage >= 0.75, f"{coverage:.0%} so'z topildi")
    return rep


def frame_problem(path: Path) -> str | None:
    """A section frame must not be black, flat or very blurry."""
    with Image.open(path) as im:
        g = np.asarray(im.convert("L").resize((270, 480)), dtype=np.float32)
    if g.mean() < 12:
        return "qora kadr"
    if g.std() < 8:
        return "bir xil (bo'sh) kadr"
    lap = np.abs(np.diff(g, 2, axis=0)).mean() + np.abs(np.diff(g, 2, axis=1)).mean()
    if lap < 1.2:
        return "juda xira kadr"
    return None


def after_render(video: Path, frames: list[tuple[str, float, Path]], gate_checks: list[dict], duration: float) -> Report:
    rep = Report("after")
    rep.add("Video uzunligi", MIN_SECONDS - 5 <= duration <= MAX_SECONDS + 2, f"{duration:.1f} soniya")
    for c in gate_checks:
        rep.add(c["name"], c["ok"], c["detail"])
    for part, t, path in frames:
        prob = frame_problem(path) if path.exists() else "kadr olinmadi"
        rep.add(f"Kadr: {part} ({t:.1f}s)", prob is None, "yaxshi" if prob is None else prob)
    return rep


def save(path: Path, before: Report, after: Report | None) -> None:
    path.write_text(json.dumps({"before": before.as_dict(), "after": after.as_dict() if after else None},
                               indent=1, ensure_ascii=False), encoding="utf-8")

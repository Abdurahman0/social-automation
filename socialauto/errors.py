"""Task 10: no silent failures. Every error reaches the owner's Telegram once, in plain Uzbek.

* `explain(error)` turns an exception (or its text) into (code, plain-Uzbek reason): no internet, timeouts, Claude
  web search / CLI problems, ffmpeg or the speech model missing, B-roll keys missing, disk full, GitHub push
  rejected, research results filtered out... Anything else becomes one shortened line with secrets removed.
* `ErrorReporter` writes the messages into the durable outbox (they survive restarts) and keeps them quiet:
  one message per job per distinct error, one «internet yo'q» while offline and one «qayta ulandi» after it,
  and a repeated periodic problem (statistics, auto-update, a startup check) only again after it was fixed.
* The last error (step, time, reason) is kept for /status.

Telegram texts never carry stack traces, raw JSON, ids or secrets (laws 6 and 7); the full error stays in the log.
"""

from __future__ import annotations

import errno
import hashlib
import logging
import re
from datetime import timedelta
from typing import Any

from .claude_budget import tashkent_time
from .db import KV, parse_iso

log = logging.getLogger(__name__)

# The step names the owner sees («qaysi bosqich»).
STEP_UZ = {
    "research": "Mavzu qidirish", "propose": "Ssenariy", "regenerate": "Ssenariy (yangi variant)",
    "rewrite": "Ssenariyni tahrirlash", "plan_from_voice": "Ovozdan reja", "process_voice": "Ovoz",
    "render": "Video yig'ish", "reel_fix": "Videoni tuzatish", "reel_publish": "GitHub va Buffer navbati",
    "story": "Story qoralamasi", "live_check": "Buffer holati", "analytics": "Statistika",
    "scheduler": "Bot ishi (navbat)", "telegram": "Telegram buyrug'i", "update": "Avtomatik yangilanish",
    "startup": "Ishga tushish tekshiruvi", "content_push": "GitHub'ga saqlash",
}
# How long one job may run before the watchdog reports it (minutes).
JOB_TIMEOUT_MIN = {"research": 20, "render": 60, "reel_publish": 30, "process_voice": 20, "plan_from_voice": 25}
DEFAULT_TIMEOUT_MIN = 30

LAST_ERROR_KEY = "last_error"
NET_DOWN_KEY = "net_down"

_SECRET_PATTERNS = [
    (re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}"), "<token>"),                    # Telegram bot token
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), "<token>"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "<token>"),
    (re.compile(r"(?i)\b(bearer|token|authorization)\s*[:=]?\s*[A-Za-z0-9._~+/=-]{16,}"), r"\1 <token>"),
    (re.compile(r"(?i)([?&](?:key|api_key|access_token|token|client_secret)=)[^&\s]+"), r"\1<token>"),
    (re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@"), r"\1<login>@"),             # credentials in a URL
    (re.compile(r"\b[A-Za-z0-9_-]{40,}\b"), "<…>"),                                  # any long opaque string
]


def redact(text: str) -> str:
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def short(text: str, limit: int = 160) -> str:
    """One line, secrets removed, file paths shortened to their name, cut to `limit` characters."""
    line = " ".join(str(text).split())
    line = re.sub(r"(?:/[\w.@+-]+){2,}/([\w.@+-]+)", r"\1", line)                   # /home/x/y/file.py -> file.py
    line = redact(line)
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


class NoTopicsError(RuntimeError):
    """Research ended with zero usable topics; `reason_uz` says why in plain Uzbek."""

    def __init__(self, reason_uz: str, detail: str = ""):
        super().__init__(detail or reason_uz)
        self.reason_uz = reason_uz


def _chain(exc: BaseException) -> list[BaseException]:
    out, seen = [], set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        out.append(exc)
        exc = exc.__cause__ or exc.__context__
    return out


def explain(error: BaseException | str) -> tuple[str, str]:
    """(code, plain-Uzbek reason). `code` groups the same problem so it is not sent twice."""
    if isinstance(error, NoTopicsError):
        return "no_topics", error.reason_uz
    excs = _chain(error) if isinstance(error, BaseException) else []
    text = " ".join(f"{type(e).__name__}: {e}" for e in excs) if excs else str(error)
    low = text.lower()
    names = {type(e).__name__ for e in excs}
    if any(isinstance(e, OSError) and e.errno == errno.ENOSPC for e in excs) or "no space left" in low:
        return "disk_full", "kompyuter diskida joy qolmadi — keraksiz fayllarni o'chiring (masalan eski videolar)"
    if (names & {"ConnectionError", "NewConnectionError", "MaxRetryError", "NameResolutionError", "gaierror",
                 "ConnectError", "NetworkError"} or re.search(
            r"name resolution|temporary failure in name|network is unreachable|no route to host|connection (refused|"
            r"reset|aborted)|could not resolve host|failed to establish a new connection|getaddrinfo|"
            r"unable to access 'https", low)):
        return "offline", "internet yo'q yoki juda sekin (ulanib bo'lmadi)"
    if "could not start claude code" in low or ("claude" in low and "no such file" in low):
        return "claude_missing", "Claude Code bu kompyuterda topilmadi yoki ishga tushmadi (terminalda «claude» ni tekshiring)"
    if re.search(r"web ?search|web ?fetch", low):
        return "claude_websearch", "Claude internetdan qidira olmadi (WebSearch ishlamadi) — keyinroq o'tib ketadi"
    if "timed out" in low or names & {"TimeoutExpired", "Timeout", "ReadTimeout", "ConnectTimeout", "TimeoutError"}:
        what = "Claude javobi" if "claude" in low or re.search(r"research|script|topics", low) else "ish"
        return "timeout", f"{what} juda uzoq cho'zildi (vaqt tugadi) — internet sekin yoki xizmat band"
    if "output was not valid json" in low or "missing required fields" in low:
        return "claude_bad_answer", "Claude to'liq javob bermadi (javob chala keldi)"
    if re.search(r"(ffmpeg|ffprobe) not found", low):
        return "ffmpeg_missing", "ffmpeg o'rnatilmagan (video va ovoz bilan ishlash uchun kerak) — o'rnatuvchini qayta ishga tushiring"
    if re.search(r"(rubai|stt|whisper).*(model|not found|missing)|model.*(not found|missing)", low):
        return "model_missing", "nutqni tanish modeli yo'q — «python -m socialauto download-model» ni ishga tushiring"
    if "no licensed real footage" in low or "brollerror" in low:
        return "broll_none", ("mos video/rasm topilmadi — Pexels yoki Pixabay bepul kalitini saytdagi «Sozlamalar» ga "
                              "qo'shsangiz, tanlov ancha ko'payadi")
    if re.search(r"(pexels|pixabay).*(401|403|unauthori[sz]ed|forbidden|api key)", low):
        return "broll_key", "Pexels/Pixabay kaliti noto'g'ri yoki eskirgan — saytdagi «Sozlamalar» da yangilang"
    if re.search(r"\[rejected\]|non-fast-forward|push.*(rejected|denied)|permission to .* denied|"
                 r"remote: permission|403.*github|authentication failed", low):
        return "push_rejected", "GitHub yuklashni rad etdi (ruxsat yo'q yoki repoda boshqa o'zgarish bor)"
    if "git lfs" in low:
        return "lfs_missing", "video 50 MB dan katta, Git LFS esa o'rnatilmagan"
    if "checklist failed" in low:
        return "checklist", "tayyor video sifat tekshiruvidan o'tmadi: " + short(text.split("checklist failed:", 1)[-1], 120)
    if "remotion" in low or "npx" in low or "node_modules" in low:
        return "render_tool", "video yig'uvchi (Remotion) ishlamadi: " + short(text, 110)
    if "claudeerror" in low or "claude code failed" in low:
        return "claude_error", "Claude xato qaytardi: " + short(str(excs[0]) if excs else text, 110)
    if "research found no" in low:                          # the wording before Task 10
        return "no_topics", "suv yo'nalishida manbasi bor yangi mavzu topilmadi"
    first = excs[0] if excs else None
    plain = re.sub(r"^\w+(Error|Exception|Expired)\s*:\s*", "", text)      # "ValueError: x" (a stored text) -> "x"
    msg = short(str(first) if first is not None and str(first) else plain, 140)
    return "other:" + hashlib.sha1(re.sub(r"\d+", "#", msg).encode()).hexdigest()[:10], msg


class ErrorReporter:
    """Writes owner messages about failures into the outbox, without spam."""

    def __init__(self, outbox, kv: KV, clock, online=None):
        self.outbox = outbox
        self.kv = kv
        self.clock = clock
        self.online = online          # () -> bool; the bot service sets netcheck.online (a blip is not "no internet")

    def _really_offline(self) -> bool:
        if self.online is None:
            return True
        try:
            return not self.online()
        except Exception:             # noqa: BLE001
            return True

    # --- bookkeeping --------------------------------------------------------------------------------------
    def _remember(self, step: str, reason: str, subject: str = "") -> None:
        self.kv.set(LAST_ERROR_KEY, {"step": step, "reason": reason, "subject": subject,
                                     "at": self.clock().isoformat()})

    def last_error(self) -> dict | None:
        return self.kv.get(LAST_ERROR_KEY)

    def _offline(self, step: str, subject: str = "") -> None:
        """One «internet yo'q» message until it is back (then one «qayta ulandi», see `back_online`)."""
        self._remember(step, "internet yo'q", subject)
        if self.kv.get(NET_DOWN_KEY):
            return
        self.kv.set(NET_DOWN_KEY, self.clock().isoformat())
        self.outbox.add("error", text="📡 Internet yo'q — bot ishlarni to'xtatib turibdi. Internet qaytishi bilan o'zi "
                                      "davom etadi (alohida xabar beraman).")

    def net_down(self) -> bool:
        return bool(self.kv.get(NET_DOWN_KEY))

    def back_online(self) -> bool:
        if not self.kv.get(NET_DOWN_KEY):
            return False
        self.kv.delete(NET_DOWN_KEY)
        self.outbox.add("error", text="✅ Internet qayta ulandi — ishlar davom etyapti.")
        return True

    # --- jobs ---------------------------------------------------------------------------------------------
    def job_failed(self, job, error: BaseException | str, retry_minutes: int, subject: str = "") -> bool:
        """A job failed and will be retried. True if a message was queued (first time for this distinct error)."""
        code, reason = explain(error)
        step = STEP_UZ.get(job.kind, job.kind)
        if code == "offline" and self._really_offline():
            self._offline(step, subject)
            return False
        self._remember(step, reason, subject)
        key = f"joberr:{job.id}"
        seen = self.kv.get(key) or []
        if code in seen:
            return False
        self.kv.set(key, seen + [code])
        when = f"{retry_minutes} daqiqadan" if retry_minutes < 120 else f"{round(retry_minutes / 60)} soatdan"
        self.outbox.add("error", text=(f"⚠️ «{step}» bosqichida xato" + (f"\n🎬 «{subject}»" if subject else "") +
                                       f"\nSabab: {reason}.\n🔁 {when} keyin o'zim qayta urinaman."))
        return True

    def job_gave_up(self, job, error: BaseException | str, subject: str = "", attempts: int | None = None) -> None:
        code, reason = explain(error)
        step = STEP_UZ.get(job.kind, job.kind)
        self._remember(step, reason, subject)
        self.kv.delete(f"joberr:{job.id}")
        tried = attempts if attempts is not None else job.attempts
        buttons = [[("🔄 Qayta urinish", f"er:r:{job.id}")]]
        if job.kind == "research":
            buttons.append([("🔎 Boshqa mavzu", f"er:o:{job.id}")])
        head = "🔎 Mavzu topilmadi" if code == "no_topics" else f"❌ «{step}» to'xtatildi"
        text = (head + (f"\n🎬 «{subject}»" if subject else "") + f"\nSabab: {reason}." +
                (f"\n{tried} marta urinib ko'rdim." if tried and tried > 1 else "") +
                "\nReel saytda «To'xtab qoldi» holatida turibdi. Qayta urinish uchun tugmani bosing." +
                ("\nYoki boshqa g'oya bilan yozing: /new <g'oya>." if code == "no_topics" else ""))
        self.outbox.add("error", text=text, buttons=buttons)

    def stuck(self, job, minutes: int, subject: str = "") -> None:
        step = STEP_UZ.get(job.kind, job.kind)
        self._remember(step, f"{minutes} daqiqadan ko'p davom etdi", subject)
        self.outbox.add("error", text=(f"⏳ «{step}» {minutes} daqiqadan beri tugamadi" +
                                       (f"\n🎬 «{subject}»" if subject else "") +
                                       "\nTo'xtatib, birozdan keyin o'zim qayta urinaman."))

    # --- periodic / bot-level problems --------------------------------------------------------------------
    def problem(self, where: str, error: BaseException | str, step_key: str | None = None,
                text: str | None = None) -> bool:
        """A problem outside jobs (statistics, auto-update, the scheduler loop, a startup check). Sent once; sent again
        only after `resolved(where)` was called (it worked in between) or after a day. True if queued."""
        code, reason = explain(error) if text is None else ("custom", text)
        step = STEP_UZ.get(step_key or where, step_key or where)
        if code == "offline":
            if self._really_offline():
                self._offline(step)
            return False                  # a blip while online: tried again anyway, not worth a message
        self._remember(step, reason)
        key = f"problem:{where}"
        prev = self.kv.get(key)
        now = self.clock()
        if prev and prev.get("code") == code and now - parse_iso(prev["at"]) < timedelta(hours=24):
            return False
        self.kv.set(key, {"code": code, "at": now.isoformat()})
        self.outbox.add("error", text=text if text is not None else f"⚠️ «{step}»: {reason}.")
        return True

    def resolved(self, where: str) -> None:
        if self.kv.get(f"problem:{where}"):
            self.kv.delete(f"problem:{where}")

    # --- /status --------------------------------------------------------------------------------------------
    def status_lines(self, jobs) -> list[str]:
        lines = []
        last = self.last_error()
        if last:
            at = tashkent_time(parse_iso(last["at"]), self.clock())
            subj = f" («{last['subject']}»)" if last.get("subject") else ""
            lines.append(f"⚠️ Oxirgi xato: {last['step']}{subj} — {at} (Toshkent): {last['reason']}")
        else:
            lines.append("✅ Xatolar yo'q")
        waiting = jobs.retry_waiting()
        if waiting:
            lines.append(f"🔁 Qayta urinishni kutayotgan ishlar: {waiting}")
        if self.net_down():
            lines.append("📡 Internet yo'q — qaytishini kutyapman")
        return lines


def subject_of(video: dict | None, payload: dict[str, Any] | None = None) -> str:
    """What the owner calls this reel: its title, else the idea, else «Yangi tadqiqot»."""
    if video:
        return video.get("title") or video.get("topic") or "Yangi tadqiqot"
    if payload and payload.get("topic"):
        return str(payload["topic"])
    return ""


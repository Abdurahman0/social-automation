"""The ONE Telegram bot: approvals with versioned buttons, the owner's voice intake, and commands.

Only user ids in TELEGRAM_ALLOWED_USER_IDS can use it. Texts to the owner are Uzbek (law 13) and never show raw
JSON, error codes or internal ids (law 6): titles, times and numbers only. Telegram is quiet (law 5): unprompted, the
owner only gets approval requests, the voice request/reminder/check for a video he approved, posted links and alerts
he must act on. Everything else goes to the log.

Buttons carry a random approval token ("s:a:<token>"); a new version of a script or video makes the old buttons
stop working (Store.open_approval), and a used button cannot be used twice.
"""

from __future__ import annotations

import asyncio
import functools
import html
import logging
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from .app import App
from .claude_budget import tashkent_time
from .db import parse_iso
from .lessons import safe_record
from . import slots
from .reel import script as rs
from .scheduler import PAUSED_KEY, Scheduler
from .store import ACTIVE, STATUS_UZ
from .video import ffmpeg
from .voice import check_upload

log = logging.getLogger(__name__)

MAX_CHUNK = 3900
CAPTION_MAX = 1024
SENT_KINDS = {"script_approval", "voice_request", "voice_reminder", "voice_check", "voice_unusable", "video_approval",
              "owner_action", "limit", "topic_choice", "cover_request", "buffer_ready", "story_ready"}
AWAIT_EDIT = "await_edit:{}"
AWAIT_REJECT = "await_reject:{}"
BUTTON_RE = re.compile(r"^(s|v|c):([a-z]):([0-9a-f]{10})$")
VOICE_TO_RE = re.compile(r"^vo:(\d+):(\d+)$")
VOICE_NEW_RE = re.compile(r"^vn:(\d+)$")
VOICE_FIX_RE = re.compile(r"^vf:(\d+):(\d+)$")
TOPIC_RE = re.compile(r"^t:(\d+|m):([0-9a-f]{10})$")
STORY_RE = re.compile(r"^st:(\d+)$")
PLATFORM_UZ = {"youtube": "YouTube", "instagram": "Instagram"}

HELP = """🎬 Social Automation — suv va oqova suv haqida reels

Siz qiladigan ishlar (har biri bitta xabar va tugmalar bilan keladi):
1) 🔎 Mavzuni tanlaysiz — bot tadqiqot qilib, 3–5 ta mavzu taklif qiladi.
2) 📝 Ssenariyni tahrirlaysiz yoki tasdiqlaysiz (8 qism, o'zbekcha).
3) 🎙 Matnni o'qib, ovozni yuborasiz.
4) 🎬 Videoni ko'rasiz: tuzatish (matn yoki ovozli xabar) yoki ✅ tasdiqlash.
5) 🖼 Muqovani o'zingiz tayyorlab yuborasiz (bot muqova qilmaydi) → bot GitHub'ga saqlaydi va Buffer navbatiga qo'shadi.
   👉 Buffer uni o'z jadvali bo'yicha, navbatdagi bo'sh vaqtda o'zi joylaydi.
6) 📱 Reel efirga chiqqach — story qoralamasi tayyor bo'ladi, uni o'zingiz joylaysiz.

Buyruqlar:
/new [mavzu] — yangi tadqiqot (mavzu ixtiyoriy)
/queue — navbat · /status — holat · /stats — statistika
/lessons — o'rganilgan xatolar · /usage — Claude sarfi
/pause, /resume · /cancel — matn kiritishni bekor qilish"""

RECORD_TIPS = ["Jim xonada yozing (eshik-deraza yopiq, konditsioner/TV o'chiq).",
               "Telefonni og'izdan 15–20 sm uzoqlikda tuting.",
               "Tabiiy, jonli ovozda o'qing; boshida 1 soniya jim turing.",
               "Xato qilsangiz, gapni boshidan qayta o'qing — bot eng to'g'ri qismini ishlatadi."]


def e(text: Any) -> str:
    return html.escape(str(text), quote=False)


def chunk(text: str, limit: int = MAX_CHUNK) -> list[str]:
    chunks, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def seconds_uz(s: float) -> str:
    s = round(s)
    return f"{s // 60} daq {s % 60} soniya" if s >= 60 else f"{s} soniya"


def source_name(text: str) -> str:
    """A source as a readable name: links and long titles are cut ("Smithsonian Magazine: The Mystery..." -> name)."""
    text = re.sub(r"\(?https?://\S+\)?", "", str(text)).strip(" ,;:-")
    return text.split(":")[0].strip()[:60]


# --- message texts (pure functions, tested) -------------------------------------------------------------------------

def topic_message(topics: list[dict], insight: str, dry_run: bool) -> str:
    lines = ["🔎 <b>Yangi mavzular tayyor</b>" + (" · 🧪 sinov rejimi" if dry_run else ""),
             f"\n📊 <i>{e(insight)}</i>" if insight else ""]
    for i, tp in enumerate(topics, start=1):
        sources = ", ".join(dict.fromkeys(f["source"] for f in tp.get("facts", [])))
        lines += [f"\n<b>{i}. {e(tp['title'])}</b>", f"• {e(tp.get('angle', ''))}",
                  f"• <b>Nega hozir:</b> {e(tp.get('why_now', ''))}",
                  f"• <b>Birinchi 5 soniya:</b> {e(tp.get('hook_idea', ''))}",
                  f"• <b>Manbalar:</b> {e(sources)}"]
    lines.append("\nQaysi mavzuda video qilamiz?")
    return "\n".join(x for x in lines if x)


def topic_keyboard(topics: list[dict], token: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"{i + 1}. {tp['title'][:48]}", callback_data=f"t:{i}:{token}")]
            for i, tp in enumerate(topics)]
    rows.append([InlineKeyboardButton("🔎 Boshqa mavzular", callback_data=f"t:m:{token}")])
    return InlineKeyboardMarkup(rows)


def reel_script_message(script: dict, slot: str | None, dry_run: bool, wps: float, from_voice: bool = False) -> str:
    from .reel import script as rs
    tags = " ".join(f"#{t.lstrip('#')}" for t in script.get("hashtags", []))
    sources = ", ".join(s["name"] for s in script.get("sources", []))
    head = "🎙 <b>Ovozingizdan reel rejasi</b>" if from_voice else "📝 <b>Reel ssenariysi</b>"
    parts = [head + (" · 🧪 sinov rejimi" if dry_run else ""), f"\n<b>{e(script['title'])}</b>",
             "\n📌 <b>Bu video nima haqida</b>",
             f"• <b>Mavzu:</b> {e(script.get('topic', ''))}",
             f"• <b>Birinchi 5 soniyadagi fakt:</b> {e(script.get('key_fact', ''))}",
             f"• <b>Uzunligi:</b> ~{seconds_uz(rs.estimated_seconds(script, wps))}",
             f"• <b>Ekrandagi sarlavha:</b> {e(script['title'])}",
             f"• <b>Heshteglar:</b> {e(tags)}"]
    if slot:
        parts.append(f"• <b>Chiqish sanasi:</b> {e(slot)} (Toshkent)")
    if sources:
        parts.append(f"• <b>Manbalar:</b> {e(sources)}")
    parts.append("\n📜 <b>To'liq matn (8 qism)</b>")
    for p in script["parts"]:
        parts.append(f"<b>{e(rs.PART_UZ.get(p['part'], p['part']))}:</b> {e(p['text'])}")
    parts.append("\n✏️ Tahrirlash: izoh yozing yoki butun matnni o'zgartirib, to'liq yuboring.")
    return "\n".join(parts)


def reel_video_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"v:a:{token}")],
        [InlineKeyboardButton("✏️ Tuzatish (matn yoki ovoz)", callback_data=f"v:e:{token}"),
         InlineKeyboardButton("🔄 Yangi B-roll", callback_data=f"v:g:{token}")],
        [InlineKeyboardButton("❌ Rad etish", callback_data=f"v:r:{token}")],
    ])


def reel_video_caption(title: str, version: int, duration: float, report: dict, dry_run: bool) -> str:
    checks = (report.get("before", {}).get("checks") or []) + (report.get("after", {}).get("checks") or [])
    ok = sum(1 for c in checks if c["ok"])
    text = (f"🎬 <b>v{version} tayyor — ko'rib chiqing</b>" + (" · 🧪 sinov rejimi" if dry_run else "") +
            f"\n\n<b>{e(title)}</b>\n⏱ {duration:.0f} soniya · ✅ tekshiruv: {ok}/{len(checks)}\n\n"
            "Hammasi yaxshi bo'lsa — ✅ Tasdiqlash (keyin muqovani so'rayman). Tuzatish kerak bo'lsa — ✏️ ni bosib, "
            "matn yoki ovozli xabar yuboring: keyingi versiya tayyorlanadi.")
    return text[:CAPTION_MAX]


def buffer_message(title: str, reel: dict, dry_run: bool) -> str:
    drafts = reel.get("drafts") or {}
    names = {"instagram": "Instagram (Reels)", "youtube": "YouTube (Shorts)", "linkedin": "LinkedIn"}
    lines = [f"📤 <b>«{e(title)}»</b>", f"• GitHub: {e(reel.get('git_note') or '—')}"]
    if drafts:
        lines.append("• 📅 <b>Buffer navbatiga qo'shildi — Buffer uni o'z vaqtida o'zi joylaydi.</b>")
        states = reel.get("buffer") or {}
        for k in drafts:
            due = (states.get(k) or {}).get("due_at")
            when = f": {tashkent_time(parse_iso(due), datetime.now(timezone.utc))} (Toshkent)" if due else ""
            lines.append(f"  – {names.get(k, k)}{when}")
        if dry_run:
            lines.append("🧪 Sinov rejimi: Buffer'ga haqiqatda yuborilmadi, faqat yozib qo'yildi.")
        lines.append("Vaqtni Buffer'da o'zgartirishingiz mumkin: https://publish.buffer.com")
    else:
        lines.append("• Buffer ulanmagan — reel Buffer'ga yuborilmadi (docs/OWNER_TODO.md).")
    lines.append("Reel efirga chiqqach, story qoralamasini (sizning muqovangiz + havola) tayyorlayman.")
    return "\n".join(lines)


def script_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"s:a:{token}")],
        [InlineKeyboardButton("🔄 Qayta yaratish", callback_data=f"s:g:{token}"),
         InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"s:e:{token}")],
        [InlineKeyboardButton("❌ Rad etish", callback_data=f"s:r:{token}")],
    ])


def voice_request_message(script: dict, cfg, tips_from_lessons: list[str], reminder: bool = False,
                          slot: str | None = None) -> str:
    est = rs.estimated_seconds(script, cfg.reel.words_per_second)
    head = ("⏰ <b>Eslatma:</b> bu video uchun ovoz hali kelmadi." if reminder else
            "🎙 <b>Endi ovoz yozing</b> — quyidagi matnni o'z ovozingiz bilan o'qib, shu chatga yuboring.")
    tips = tips_from_lessons + [t for t in RECORD_TIPS if t not in tips_from_lessons]
    lines = [head, f"\n<b>{e(script['title'])}</b>"]
    if slot:
        lines.append(f"🕖 Chiqish vaqti: {e(slot)} (Toshkent)")
    lines += [f"⏱ Mo'ljal: {rs.MIN_SECONDS}–{rs.MAX_SECONDS} soniya (~{seconds_uz(est)}).",
              "\n📜 <b>O'qiladigan matn:</b>", e(rs.full_text(script)),
              "\n💡 <b>Maslahatlar:</b>", *[f"• {e(t)}" for t in tips[:5]],
              "\nQabul qilinadi: ovozli xabar, audio fayl (mp3/m4a/wav/ogg), fayl sifatida audio, dumaloq video yoki "
              f"video. Hajmi {cfg.voice.max_download_mb} MB gacha."]
    return "\n".join(lines)


def voice_check_message(title: str, problems: list[str]) -> str:
    reasons = []
    for p in problems:
        code = p.split(":", 1)[0]
        if code == "missing":
            m = re.search(r"only (\d+)%", p)
            reasons.append(f"matnning bir qismi eshitilmadi (taxminan {m.group(1) if m else '?'}% o'qilgan)")
        elif code == "too_long":
            m = re.search(r"is (\d+)s", p)
            reasons.append(f"yozuv juda uzun ({m.group(1) if m else '?'} soniya)")
        elif code == "too_short":
            reasons.append("yozuv juda qisqa")
    return (f"🎙 «{e(title)}» uchun ovoz keldi, lekin " + "; ".join(reasons or ["matndan ancha farq qiladi"]) + ".\n"
            "Shu holicha davom etaymi yoki qayta yozib yuborasizmi?")


def voice_check_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Shu holicha davom et", callback_data=f"c:k:{token}")],
                                 [InlineKeyboardButton("🎙 Qayta yozib yuboraman", callback_data=f"c:r:{token}")]])


def voice_choice_keyboard(voice_id: int, videos: list[dict]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"🎬 {v['title'][:40] or 'Nomsiz video'} uchun", callback_data=f"vo:{voice_id}:{v['id']}")]
            for v in videos[:6]]
    rows.append([InlineKeyboardButton("✨ Shu ovozdan yangi video yasa", callback_data=f"vn:{voice_id}")])
    return InlineKeyboardMarkup(rows)


def queue_lines(app: App) -> list[str]:
    cfg = app.settings.schedule
    rows = app.store.videos(ACTIVE)
    if not rows:
        return ["Navbat bo'sh. /new — yangi video."]
    out = []
    for v in sorted(rows, key=lambda v: v["slot_at"] or "9999"):
        slot = slots.describe(cfg, parse_iso(v["slot_at"])) if v["slot_at"] else "—"
        out.append(f"• «{v['title'] or 'Yangi g‘oya'}» — {STATUS_UZ.get(v['status'], v['status'])} · {slot}")
    return out


def status_text(app: App, scheduler_paused: bool) -> str:
    s = app.settings
    now = app.clock()
    counts: dict[str, int] = {}
    for v in app.store.videos(limit=500):
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    paused = app.budget.paused_until()
    yt = "ulangan" if s.resolve(s.youtube.token_file).exists() else "ulanmagan"
    ig = "ulangan" if s.resolve(s.instagram.token_file).exists() else "ulanmagan"
    buf = "ulangan" if s.buffer_api_key else "ulanmagan"
    try:
        nxt = slots.describe(s.schedule, app.workflow.next_slot())
    except Exception:        # noqa: BLE001
        nxt = "—"
    lines = ["📊 <b>Bot holati</b>",
             f"🧪 Rejim: {'sinov — Buffer’ga hech narsa yuborilmaydi, faqat yozib qo‘yiladi' if s.dry_run else 'tasdiqlangan reel Buffer navbatiga yuboriladi, Buffer o‘zi joylaydi'}",
             f"⏯ Avtomatik ish: {'to‘xtatilgan (/resume)' if scheduler_paused else 'ishlayapti'}",
             f"🤖 Claude: {'limit, ' + tashkent_time(paused, now) + ' da ochiladi' if paused else 'ishlayapti'}",
             f"📝 Buffer: {buf} · 📊 YouTube statistikasi: {yt} · Instagram statistikasi: {ig}",
             f"🕖 Keyingi bo'sh vaqt: {nxt} (Toshkent)",
             "\n<b>Videolar:</b>"]
    lines += [f"• {STATUS_UZ.get(k, k)}: {n}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1])] or ["• hali yo'q"]
    return "\n".join(lines)


def authorized(handler):
    @functools.wraps(handler)
    async def wrapper(self: "TelegramBot", update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or user.id not in self.app.settings.allowed_user_ids:
            log.warning("Ignored update from an unauthorized user")
            if update.callback_query:
                await update.callback_query.answer()
            return
        return await handler(self, update, context)
    return wrapper


class TelegramBot:
    def __init__(self, app: App, analytics=None):
        self.app = app
        self.analytics = analytics
        self.application: Application | None = None
        self.bot = None                           # set in build(); tests inject a fake
        self.scheduler = Scheduler(app, self.deliver_outbox, analytics)
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._deliver_lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    # --- lifecycle ------------------------------------------------------------------------------------------
    def build(self) -> Application:
        application = (Application.builder().token(self.app.settings.telegram_token)
                       .post_init(self._post_init).post_stop(self._post_stop).build())
        for name, fn in [("start", self.cmd_help), ("help", self.cmd_help), ("new", self.cmd_new),
                         ("status", self.cmd_status), ("queue", self.cmd_queue), ("pause", self.cmd_pause),
                         ("resume", self.cmd_resume), ("stats", self.cmd_stats), ("lessons", self.cmd_lessons),
                         ("usage", self.cmd_usage), ("cancel", self.cmd_cancel)]:
            application.add_handler(CommandHandler(name, fn))
        application.add_handler(CallbackQueryHandler(self.on_button))
        media = filters.VOICE | filters.AUDIO | filters.Document.ALL | filters.VIDEO_NOTE | filters.VIDEO | filters.PHOTO
        application.add_handler(MessageHandler(media, self.on_media))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
        application.add_error_handler(self.on_error)
        self.application = application
        self.bot = application.bot
        return application

    def run(self) -> None:
        self.build().run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=-1)

    def request_stop(self) -> None:
        """Stop polling from another thread (the .env watcher); run() then returns."""
        if self._loop is not None and self.application is not None:
            self._loop.call_soon_threadsafe(self.application.stop_running)

    async def _post_init(self, application: Application) -> None:
        await application.bot.set_my_commands([
            BotCommand("new", "Yangi video g'oyasi"), BotCommand("queue", "Navbat"), BotCommand("status", "Holat"),
            BotCommand("stats", "Statistika"), BotCommand("lessons", "O'rganilgan xatolar"),
            BotCommand("usage", "Claude sarfi"), BotCommand("pause", "To'xtatish"), BotCommand("resume", "Davom ettirish"),
            BotCommand("help", "Yordam")])
        self._loop = asyncio.get_running_loop()
        self._tasks = [asyncio.create_task(self._guarded())]

    async def _guarded(self) -> None:
        delay = 5.0
        while not self._stop.is_set():
            try:
                await self.scheduler.run(self._stop)
                return
            except Exception:              # noqa: BLE001
                log.exception("Scheduler stopped; restarting in %.0fs", delay)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except TimeoutError:
                pass
            delay = min(300, delay * 2)

    async def _post_stop(self, application: Application) -> None:
        self._stop.set()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        if isinstance(context.error, NetworkError):
            log.warning("Telegram network error: %s", context.error)
        else:
            log.error("Telegram handler error", exc_info=context.error)

    # --- outgoing -------------------------------------------------------------------------------------------
    async def deliver_outbox(self) -> None:
        if self.bot is None:
            return
        async with self._deliver_lock:
            for item in self.app.outbox.pending(50):
                if item.kind not in SENT_KINDS:          # law 5: the one place the quiet rule is enforced
                    log.info("Not sent (quiet Telegram): %s", item.kind)
                    self.app.outbox.mark_silenced(item.id)
                    continue
                delivered = 0
                for chat_id in sorted(self.app.settings.allowed_user_ids):
                    try:
                        await self.send_item(chat_id, item.kind, item.payload)
                        delivered += 1
                    except (BadRequest, Forbidden) as exc:
                        log.warning("Could not deliver a %s message: %s", item.kind, exc)
                    except NetworkError:
                        if delivered:
                            self.app.outbox.mark_sent(item.id)
                        raise
                    except TelegramError as exc:
                        log.warning("Could not deliver a %s message: %s", item.kind, exc)
                if delivered:
                    self.app.outbox.mark_sent(item.id)
                else:
                    self.app.outbox.mark_attempt(item.id)

    def _slot(self, video: dict) -> str | None:
        return slots.describe(self.app.settings.schedule, parse_iso(video["slot_at"])) if video.get("slot_at") else None

    async def _send_long(self, chat_id: int, text: str, markup=None) -> None:
        parts = chunk(text)
        for i, part in enumerate(parts):
            await self.bot.send_message(chat_id, part, parse_mode=ParseMode.HTML,
                                        reply_markup=markup if i == len(parts) - 1 else None)

    async def send_item(self, chat_id: int, kind: str, p: dict) -> None:
        store = self.app.store
        if kind == "topic_choice":
            approval = store.approval(p["approval"])
            if not approval or approval["status"] != "pending":
                return
            reel = self.app.workflow.reels.get(p["video_id"])
            await self._send_long(chat_id, topic_message(reel["topics"], reel.get("insight", ""), bool(approval["dry_run"])),
                                  topic_keyboard(reel["topics"], p["approval"]))
        elif kind == "script_approval":
            approval = store.approval(p["approval"])
            if not approval or approval["status"] != "pending":
                return                                   # superseded before delivery
            video = store.video(p["video_id"])
            script = store.script(video["id"], approval["ref_version"])
            text = reel_script_message(script, self._slot(video), bool(approval["dry_run"]),
                                       self.app.settings.reel.words_per_second, video["origin"] == "voice")
            await self._send_long(chat_id, text, script_keyboard(p["approval"]))
        elif kind == "cover_request":
            video = store.video(p["video_id"])
            if video["status"] != "cover_waiting":
                return
            await self.bot.send_message(chat_id, f"🖼 <b>Muqova kerak</b>: «{e(video['title'])}»\nSiz muqova "
                                                 "tayyorlaysiz — bot muqova qo'shmaydi. Tayyor rasmni shu chatga yuboring "
                                                 "(1080×1920, JPG/PNG; yaxshisi «fayl» sifatida, shunda sifat saqlanadi). "
                                                 "U o'zgartirilmasdan ishlatiladi. Muqova kelmaguncha reel «Muqova "
                                                 "kutilmoqda» holatida turadi.",
                                        parse_mode=ParseMode.HTML)
        elif kind == "buffer_ready":
            video = store.video(p["video_id"])
            reel = self.app.workflow.reels.get(video["id"])
            await self.bot.send_message(chat_id, buffer_message(video["title"], reel, self.app.settings.dry_run),
                                        parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        elif kind == "story_ready":
            video = store.video(p["video_id"])
            reel = self.app.workflow.reels.get(video["id"])
            if video["status"] != "story_pending":
                return
            caption = (f"📱 <b>Story qoralamasi tayyor — joylash sizda.</b> «{e(video['title'])}» efirda!\nHavola: {e(reel.get('live_link') or '')}\n"
                       "Instagram'da: rasmni story qilib qo'ying → stiker → «Havola» → shu havolani qo'ying → Ulashish."
                       + ("\nBuffer'da story qoralamasi ham tayyor." if reel.get("story_draft") else ""))
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Storyni joyladim", callback_data=f"st:{video['id']}")]])
            cover = Path(reel["cover_path"]) if reel.get("cover_path") else None
            if cover and cover.exists():
                await self.bot.send_photo(chat_id, cover.read_bytes(), caption=caption[:CAPTION_MAX],
                                          parse_mode=ParseMode.HTML, reply_markup=markup)
            else:
                await self.bot.send_message(chat_id, caption, parse_mode=ParseMode.HTML, reply_markup=markup)
        elif kind in ("voice_request", "voice_reminder"):
            video = store.video(p["video_id"])
            if video["status"] not in ("voice_waiting", "voice_check"):
                return
            tips = self.app.lessons.voice_tips()
            await self._send_long(chat_id, voice_request_message(store.script(video["id"]), self.app.settings, tips,
                                                                 reminder=kind == "voice_reminder",
                                                                 slot=self._slot(video)))
        elif kind == "voice_check":
            approval = store.approval(p["approval"])
            if not approval or approval["status"] != "pending":
                return
            video = store.video(p["video_id"])
            await self.bot.send_message(chat_id, voice_check_message(video["title"], p.get("problems", [])),
                                        parse_mode=ParseMode.HTML, reply_markup=voice_check_keyboard(p["approval"]))
        elif kind == "voice_unusable":
            video = store.video(p["video_id"])
            if p.get("too_long"):
                text = (f"🎙 Yozuv {p['too_long']:.0f} soniya — video uchun juda uzun (eng ko'pi "
                        f"{self.app.settings.content.hard_max_seconds} soniya). Qisqaroq qilib qayta yuboring.")
            else:
                text = ("🎙 Yuborilgan yozuvdan nutqni ajratib bo'lmadi (ovoz juda past yoki fayl buzilgan). "
                        + (f"«{e(video['title'])}» uchun " if not p.get("new_video") else "")
                        + "iltimos, qayta yozib yuboring.")
            await self.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        elif kind == "video_approval":
            await self._send_video_approval(chat_id, p)
        else:                                            # owner_action, limit
            await self.bot.send_message(chat_id, p.get("text", ""))

    async def _send_video_approval(self, chat_id: int, p: dict) -> None:
        store = self.app.store
        approval = store.approval(p["approval"])
        if not approval or approval["status"] != "pending":
            return
        render = store.render(approval["ref_version"])
        path = await asyncio.to_thread(self._telegram_file, render)       # the owner makes the cover: none here
        rep = render.get("report") or {}
        with open(path, "rb") as f:
            await self.bot.send_video(chat_id, f, caption=reel_video_caption(render["title"], rep.get("version", 1),
                                                                             render["duration"] or 0, rep,
                                                                             bool(approval["dry_run"])),
                                      parse_mode=ParseMode.HTML, reply_markup=reel_video_keyboard(p["approval"]),
                                      supports_streaming=True, width=1080, height=1920,
                                      duration=round(render["duration"] or 0), read_timeout=300, write_timeout=300)

    def _telegram_file(self, render: dict) -> Path:
        path = Path(render["video_path"])
        limit = self.app.settings.video.telegram_max_mb * 1_000_000
        if path.stat().st_size <= limit:
            return path
        preview = path.with_name("preview.mp4")
        if not preview.exists():
            ffmpeg.make_preview(path, preview, limit)
            self.app.store.update_render(render["id"], preview_path=str(preview))
        return preview

    # --- buttons --------------------------------------------------------------------------------------------
    @authorized
    async def on_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        ok, reply = await self.handle_button(update.effective_user.id, query.data or "")
        if not ok:
            await query.answer(reply[:190], show_alert=True)
            return
        await query.answer()
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except TelegramError:
            pass
        if reply:
            await query.message.reply_text(reply)
        await self.deliver_outbox()

    async def handle_button(self, user_id: int, data: str) -> tuple[bool, str]:
        """(ok, reply text). Used by on_button and by tests."""
        wf, kv = self.app.workflow, self.app.kv
        m = BUTTON_RE.match(data)
        if m:
            group, action, token = m.groups()
            if group == "s":
                if action == "e":
                    approval = self.app.store.approval(token)
                    if not approval or approval["status"] != "pending":
                        return False, "Bu tugma endi ishlamaydi."
                    kv.set(AWAIT_EDIT.format(user_id), {"stage": "script", "token": token})
                    return True, "✏️ Nimani o'zgartirish kerak? Bitta xabarda yozing. (/cancel — bekor qilish)"
                res = await asyncio.to_thread(wf.script_decision, token,
                                              {"a": "approve", "r": "reject", "g": "regenerate"}[action])
                if res.ok and action == "r":
                    video_id = self.app.store.approval(token)["video_id"]
                    kv.set(AWAIT_REJECT.format(user_id), {"video_id": video_id})
                    return True, res.message + "\n💬 Nima yoqmadi? Bir og'iz yozsangiz, bot eslab qoladi (ixtiyoriy)."
                return res.ok, res.message
            if group == "v":
                if action == "e":
                    approval = self.app.store.approval(token)
                    if not approval or approval["status"] != "pending":
                        return False, "Bu tugma endi ishlamaydi."
                    kv.set(AWAIT_EDIT.format(user_id), {"stage": "video", "token": token})
                    return True, ("✏️ Nimani tuzatay? Matn bilan yozing yoki ovozli xabar yuboring (masalan: "
                                  "«3-qismda boshqa video qo'y, sarlavhani qisqartir»). (/cancel — bekor qilish)")
                res = await asyncio.to_thread(wf.video_decision, token, {"a": "approve", "r": "reject",
                                                                         "g": "regenerate"}[action])
                if res.ok and action == "r":
                    kv.set(AWAIT_REJECT.format(user_id), {"video_id": self.app.store.approval(token)["video_id"]})
                    return True, res.message + "\n💬 Nima yoqmadi? Bir og'iz yozsangiz, bot eslab qoladi (ixtiyoriy)."
                return res.ok, res.message
            res = await asyncio.to_thread(wf.voice_check_decision, token, "continue" if action == "k" else "redo")
            return res.ok, res.message
        m = TOPIC_RE.match(data)
        if m:
            choice = "more" if m.group(1) == "m" else int(m.group(1))
            res = await asyncio.to_thread(wf.topic_decision, m.group(2), choice)
            return res.ok, res.message
        m = STORY_RE.match(data)
        if m:
            res = await asyncio.to_thread(wf.story_done, int(m.group(1)))
            return res.ok, res.message
        m = VOICE_FIX_RE.match(data)
        if m:
            voice = self.app.store.voice(int(m.group(1)))
            if not voice or voice["status"] != "unassigned":
                return False, "Bu ovoz allaqachon ishlatilgan."
            res = await asyncio.to_thread(wf.fix_from_voice, int(m.group(1)), int(m.group(2)))
            return res.ok, res.message
        m = VOICE_TO_RE.match(data)
        if m:
            voice = self.app.store.voice(int(m.group(1)))
            if not voice or voice["status"] != "unassigned":
                return False, "Bu ovoz allaqachon ishlatilgan."
            res = await asyncio.to_thread(wf.assign_voice, int(m.group(1)), int(m.group(2)))
            return res.ok, res.message
        m = VOICE_NEW_RE.match(data)
        if m:
            voice = self.app.store.voice(int(m.group(1)))
            if not voice or voice["status"] != "unassigned":
                return False, "Bu ovoz allaqachon ishlatilgan."
            res = await asyncio.to_thread(wf.new_video_from_voice, int(m.group(1)))
            return res.ok, res.message
        return False, "Noma'lum tugma."

    # --- voice / media intake -------------------------------------------------------------------------------
    @authorized
    async def on_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.message
        if msg.photo or (msg.document and (msg.document.mime_type or "").startswith("image/")):
            obj = msg.photo[-1] if msg.photo else msg.document

            async def download_img(dest: Path) -> None:
                tg_file = await context.bot.get_file(obj.file_id)
                await tg_file.download_to_drive(custom_path=str(dest))
            await msg.reply_text(await self.handle_cover(download_img))
            return
        kind, obj = None, None
        for k in ("voice", "audio", "video_note", "video", "document"):
            if getattr(msg, k, None):
                kind, obj = k, getattr(msg, k)
                break
        if obj is None:
            return

        async def download(dest: Path) -> None:
            tg_file = await context.bot.get_file(obj.file_id)
            await tg_file.download_to_drive(custom_path=str(dest))

        reply, markup = await self.handle_upload(kind, obj.file_size, getattr(obj, "mime_type", "") or "",
                                                 getattr(obj, "file_name", "") or "", download,
                                                 user_id=update.effective_user.id)
        await msg.reply_text(reply, reply_markup=markup)
        await self.deliver_outbox()

    async def handle_cover(self, download) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "cover"
            await download(dest)
            res = await asyncio.to_thread(self.app.workflow.receive_cover, dest)
        await self.deliver_outbox()
        return res.message

    async def handle_upload(self, kind: str, size: int | None, mime: str, filename: str, download,
                            user_id: int | None = None) -> tuple[str, InlineKeyboardMarkup | None]:
        """Check, download and route one uploaded recording. Returns the reply (and buttons when asking)."""
        cfg = self.app.settings.voice
        intake = check_upload(kind, size, cfg.max_download_mb, mime, filename)
        if not intake.ok and intake.reason == "size":
            return (f"📦 Fayl {size / 1e6:.0f} MB — Telegram botlar {cfg.max_download_mb} MB gacha faylni yuklab oladi. "
                    "Iltimos, ovozli xabar sifatida yuboring yoki faylni siqib (masalan m4a/mp3) qayta yuboring."), None
        if not intake.ok:
            return ("🙂 Bu fayl ovoz emas. Ovozli xabar, audio fayl (mp3, m4a, wav, ogg, opus, aac), dumaloq video "
                    "yoki video yuboring."), None
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / f"upload{intake.suffix}"
            await download(dest)
            voice_id = await asyncio.to_thread(self.app.workflow.save_raw_voice, dest, kind, intake.suffix)
        if user_id is not None:
            pending_fix = self.app.kv.get(AWAIT_EDIT.format(user_id))
            if pending_fix and pending_fix.get("stage") == "video":          # a voice note with fixes for the reel
                self.app.kv.delete(AWAIT_EDIT.format(user_id))
                approval = self.app.store.approval(pending_fix["token"])
                if approval:
                    res = await asyncio.to_thread(self.app.workflow.fix_from_voice, voice_id, approval["video_id"])
                    return res.message, None
        outcome, videos = await asyncio.to_thread(self.app.workflow.route_voice, voice_id)
        if outcome == "assigned":
            return (f"🎙 Ovoz qabul qilindi: «{videos[0]['title']}». Tozalanmoqda va matnga solishtirilmoqda — "
                    "video tayyor bo'lgach, tasdiq uchun yuboraman."), None
        if videos:
            markup = voice_choice_keyboard(voice_id, videos)
            fixable = [v for v in videos if v["status"] == "video_pending"]
            if fixable:      # a finished reel is waiting: the voice may be a fix note rather than a new narration
                rows = [[InlineKeyboardButton(f"✏️ «{v['title'][:30]}» uchun tuzatish izohi", callback_data=f"vf:{voice_id}:{v['id']}")]
                        for v in fixable[:3]]
                markup = InlineKeyboardMarkup(rows + list(markup.inline_keyboard))
            return "🎙 Ovoz keldi. Bu nima uchun?", markup
        return ("🎙 Ovoz keldi, lekin hozir ovoz kutayotgan video yo'q. Shu ovozdan yangi video yasaymi?",
                voice_choice_keyboard(voice_id, []))

    # --- text replies ---------------------------------------------------------------------------------------
    @authorized
    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        reply = await self.handle_text(update.effective_user.id, update.message.text or "")
        await update.message.reply_text(reply)
        await self.deliver_outbox()

    async def handle_text(self, user_id: int, text: str) -> str:
        kv, wf = self.app.kv, self.app.workflow
        text = text.strip()
        edit = kv.get(AWAIT_EDIT.format(user_id))
        if edit:
            kv.delete(AWAIT_EDIT.format(user_id))
            fn = wf.script_decision if edit["stage"] == "script" else wf.video_decision
            res = await asyncio.to_thread(fn, edit["token"], "edit", text)
            return res.message if res.ok else f"⚠️ {res.message}"
        reject = kv.get(AWAIT_REJECT.format(user_id))
        if reject:
            kv.delete(AWAIT_REJECT.format(user_id))
            video = self.app.store.video(reject["video_id"])
            safe_record(self.app.lessons, "owner", [f"The owner rejected “{video['title']}”: {text[:300]}"])
            return "📝 Eslab qolindi — keyingi videolarda hisobga olinadi."
        return "Buyruqlar: /help"

    # --- commands -------------------------------------------------------------------------------------------
    @authorized
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(HELP)

    @authorized
    async def cmd_new(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        topic = " ".join(context.args or []).strip() or None
        await update.message.reply_text(await self.new_reply(topic))

    async def new_reply(self, topic: str | None) -> str:
        video_id = await asyncio.to_thread(self.app.workflow.request_new, topic)
        if video_id is None:
            return "🔎 Tadqiqot allaqachon ketyapti — mavzular tayyor bo'lishi bilan yuboraman."
        return "🔎 Tadqiqot boshlandi" + (f" («{topic}» yo'nalishida)" if topic else "") + \
               ". Bir necha daqiqada mavzular tanlash uchun keladi."

    @authorized
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(status_text(self.app, self.scheduler.paused()), parse_mode=ParseMode.HTML)

    @authorized
    async def cmd_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("📋 Navbat:\n" + "\n".join(queue_lines(self.app)))

    @authorized
    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.app.kv.set(PAUSED_KEY, True)
        await update.message.reply_text("⏸ Avtomatik ish to'xtatildi (tadqiqot, render va Buffer'ga yuborish). /resume")

    @authorized
    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.app.kv.set(PAUSED_KEY, False)
        await update.message.reply_text("▶️ Davom etmoqda.")

    @authorized
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from .analytics.summary import stats_text
        text = await asyncio.to_thread(stats_text, self.app)
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    @authorized
    async def cmd_lessons(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = self.app.lessons.text(limit=10)
        for part in chunk("📚 Bot o'rgangan xatolar:\n" + (text if text != "No lessons yet." else "Hali xato yo'q.")):
            await update.message.reply_text(part)

    @authorized
    async def cmd_usage(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(await asyncio.to_thread(self.app.budget.report))

    @authorized
    async def cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        for key in (AWAIT_EDIT, AWAIT_REJECT):
            self.app.kv.delete(key.format(update.effective_user.id))
        await update.message.reply_text("Bekor qilindi.")

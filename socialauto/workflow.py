"""The pipeline (the owner's reel flow): research -> topic -> 8-part script -> the owner's voice -> real B-roll +
Remotion render (_vN) -> the owner's review -> the owner's cover -> git reels/ + Buffer DRAFTS -> live -> story draft.

Owner law 15: the bot never publishes or schedules anything — it only creates Buffer drafts and a story draft; the owner
approves and schedules in Buffer and publishes the story himself. Owner law 16: the bot never makes a cover; it asks for
the owner's and uses it as is.

Six stages; "Bot" steps run as durable jobs, "Siz" (owner) steps are one Telegram message with buttons each:
    1 Tadqiqot va mavzu   Bot: research (Buffer stats, news, dedupe, research file)    Siz: pick a topic
    2 Ssenariy va ovoz    Bot: 8-part Uzbek script                                     Siz: edit/approve, send the voice
    3 B-roll va dizayn    Bot: real licensed B-roll, Remotion layout (safe zones)
    4 Ovoz va montaj      Bot: rubaiSTT + alignment, voice chain, render _vN, checklist Siz: watch, fixes or approve
    5 Tasdiq va Buffer    Siz: send the cover   Bot: git reels/ + Buffer drafts      Siz: approve & schedule in Buffer
    6 Efirdan keyin       Bot: detects "live", story draft                            Siz: publish the story
Every failure is recorded in the lessons store (law 11).
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from . import slots
from . import voice as voice_mod
from .claude_budget import Budget, ClaudeBudgetWait, tashkent_time
from .claude_client import ClaudeAuthError, ClaudeUsageLimit, backoff_until
from .config import Settings
from .db import KV, now_iso, parse_iso
from .jobs import Job, JobQueue
from .lessons import Lessons, safe_record
from .outbox import Outbox
from .reel import broll as broll_mod
from .reel import checklist, naming, publish, research as research_mod, script as script_mod
from .reel.align import align, subtitle_lines
from .reel.buffer import BufferAuthError, BufferRateLimit, metric_summary, top_posts
from .reel.layout import default_layout
from .reel.render import ReelRenderer
from .reel.state import Reels
from .store import (ACCEPTS_NEW_VOICE, ACTIVE, BUFFER_PENDING, COVER_WAITING, DONE, DRAFTING, FAILED, PUBLISHING,
                    REJECTED, RENDERING, RESEARCHING, REVISING, SCRIPT_PENDING, STORY_PENDING, TOPIC_PENDING,
                    VIDEO_PENDING, VOICE_CHECK, VOICE_PROCESSING, VOICE_WAITING, WAITS_FOR_VOICE, ApprovalError, Store)

log = logging.getLogger(__name__)

MAX_RENDER_TRIES = 3
AUTH_RETRY = timedelta(minutes=30)
CLAUDE_JOBS = ("research", "propose", "regenerate", "rewrite", "plan_from_voice", "reel_fix", "reel_publish")


@dataclass
class Result:
    ok: bool
    message: str


class Workflow:
    claude_jobs = CLAUDE_JOBS

    def __init__(self, settings: Settings, store: Store, jobs: JobQueue, outbox: Outbox, kv: KV,
                 transcriber: voice_mod.Transcriber, budget: Budget | None, lessons: Lessons | None,
                 clock: Callable[[], datetime], *, buffer=None, buffer_stats=None, reel_writer=None,
                 places: naming.Places, reel_renderer: ReelRenderer, broll_providers=None, public_files=None,
                 content=None):
        self.settings = settings
        if content is None:
            from .content_repo import ContentRepo
            content = ContentRepo(settings)
        self.content = content                    # the user's OWN content repo; the code repo is never written
        self.store = store
        self.jobs = jobs
        self.outbox = outbox
        self.kv = kv
        self.transcriber = transcriber
        self.budget = budget
        self.lessons = lessons
        self.clock = clock
        self.reels = Reels(store.db)
        self.buffer = buffer                  # drafts / story / live (dry-run stand-in while dry_run is on)
        self.buffer_stats = buffer_stats      # read-only: statistics and the owner's previous posts
        self.reel_writer = reel_writer
        self.places = places
        self.reel_renderer = reel_renderer
        self.broll_providers = broll_providers or []
        self.public_files = public_files
        self.cfg = settings.reel

    def next_slot(self) -> datetime:
        return slots.next_free_slot(self.settings.schedule, self.clock(), self.store.taken_slots())

    def ensure_pipeline(self) -> None:
        """Propose the next idea when the next free slot is close and nothing is in the pipeline."""
        if self.store.videos(ACTIVE, limit=1):
            return
        if self.next_slot() - self.clock() <= timedelta(hours=self.settings.schedule.propose_lead_hours):
            self.request_new()

    def _publish_script(self, video_id: int, script: dict, feedback: str | None = None) -> None:
        version = self.store.add_script(video_id, script, feedback)
        self.store.set_status(video_id, SCRIPT_PENDING)
        token = self.store.open_approval(video_id, "script", version, self.settings.dry_run)
        self.outbox.add("script_approval", video_id=video_id, approval=token)

    def _script_decision(self, token: str, action: str, note: str | None = None) -> Result:
        """action: approve | reject | regenerate | edit (with note)."""
        try:
            approval = self.store.decide(token, {"approve": "approved", "reject": "rejected",
                                                 "regenerate": "regenerate", "edit": "edit"}[action])
        except ApprovalError as exc:
            return Result(False, str(exc))
        video_id = approval["video_id"]
        video = self.store.video(video_id)
        if action == "approve":
            voice = self.store.voice(video["voice_id"]) if video["voice_id"] else None
            if voice and voice["status"] == "accepted":           # made from the owner's own recording
                self.store.set_status(video_id, RENDERING)
                self._enqueue_render(video_id, voice["id"])
                return Result(True, "✅ Tasdiqlandi. Ovozingiz bor — video tayyorlanmoqda.")
            self.store.set_status(video_id, VOICE_WAITING, reminded_at=None)
            self.outbox.add("voice_request", video_id=video_id)
            return Result(True, "✅ Ssenariy tasdiqlandi.")
        if action == "reject":
            self.store.set_status(video_id, REJECTED, slot_at=None)
            return Result(True, "❌ Rad etildi. Keyingi g'oya navbat bilan tayyorlanadi.")
        self.store.set_status(video_id, REVISING)
        if action == "regenerate":
            self.jobs.enqueue("regenerate", {"video_id": video_id}, dedupe_key=f"regenerate:{video_id}")
            return Result(True, "🔄 Shu mavzuda yangi ssenariy yozilmoqda.")
        safe_record(self.lessons, "owner", [f"The owner asked to change a script: {note}"])
        self.jobs.enqueue("rewrite", {"video_id": video_id, "note": note or ""}, dedupe_key=f"rewrite:{video_id}")
        return Result(True, "✏️ Qabul qilindi. Ssenariy izohingiz bo'yicha qayta yozilmoqda.")

    def save_raw_voice(self, src: Path, kind: str, suffix: str) -> int:
        """Keep the owner's raw file in data/voices/ and register it (unassigned until it has a video)."""
        voice_id = self.store.add_voice(None, kind, "", status="unassigned")
        dest = self.settings.voices_dir / f"voice_{voice_id:05d}{suffix}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        self.store.update_voice(voice_id, raw_path=str(dest))
        return voice_id

    def route_voice(self, voice_id: int) -> tuple[str, list[dict]]:
        """("assigned", [video]) when exactly one video waits; ("ask", candidates) otherwise."""
        waiting, rerecord = self.voice_targets()
        if len(waiting) == 1:
            self.assign_voice(voice_id, waiting[0]["id"])
            return "assigned", waiting
        return "ask", waiting or rerecord

    def assign_voice(self, voice_id: int, video_id: int) -> Result:
        video = self.store.video(video_id)
        if not video or video["status"] not in ACCEPTS_NEW_VOICE:
            return Result(False, "Bu video endi ovoz qabul qilmaydi (allaqachon tasdiqlangan yoki yopilgan).")
        self.store.update_voice(voice_id, video_id=video_id, status="received")
        self.store.supersede_voices(video_id, keep=voice_id)          # the newest voice wins
        self.store.supersede_approvals(video_id, ("video", "voice_check"))
        self.jobs.cancel_for_video(video_id, "a newer voice arrived", ("render", "process_voice"))
        self.store.set_status(video_id, VOICE_PROCESSING, voice_id=voice_id)
        self.jobs.enqueue("process_voice", {"video_id": video_id, "voice_id": voice_id},
                          dedupe_key=f"process_voice:{voice_id}")
        return Result(True, f"🎙 Ovoz qabul qilindi: «{video['title']}». Ishlanmoqda…")

    def _new_video_from_voice(self, voice_id: int) -> Result:
        video_id = self.store.create_video(DRAFTING, origin="voice", slot_at=self.next_slot())
        self.store.update_voice(voice_id, video_id=video_id, status="received")
        self.store.update_video(video_id, voice_id=voice_id)
        self.jobs.enqueue("plan_from_voice", {"video_id": video_id, "voice_id": voice_id},
                          dedupe_key=f"plan_from_voice:{video_id}")
        return Result(True, "🎙 Ovozingizdan yangi video tayyorlanmoqda: avval matn va reja tasdiqqa keladi.")

    def _accept_voice(self, video_id: int, voice_id: int) -> None:
        self.store.update_voice(voice_id, status="accepted")
        self.store.set_status(video_id, RENDERING)
        self._enqueue_render(video_id, voice_id)

    def voice_check_decision(self, token: str, action: str) -> Result:
        """action: continue | redo."""
        try:
            approval = self.store.decide(token, "approved" if action == "continue" else "rejected")
        except ApprovalError as exc:
            return Result(False, str(exc))
        video_id, voice_id = approval["video_id"], approval["ref_version"]
        video = self.store.video(video_id)
        if video["voice_id"] != voice_id or video["status"] != VOICE_CHECK:
            return Result(False, "Bu ovoz uchun qaror endi kerak emas (yangiroq ovoz bor).")
        if action == "continue":
            voice = self.store.voice(voice_id)
            limit = self.voice_limit()
            if voice["duration"] and voice["duration"] > limit * 1.15:
                self.store.set_status(video_id, VOICE_WAITING)
                return Result(False, f"Yozuv {voice['duration']:.0f} soniya — {script_mod.MAX_SECONDS} soniyalik "
                                     "chegaraga sig'maydi. Iltimos, qisqaroq qilib qayta yozib yuboring.")
            self._accept_voice(video_id, voice_id)
            return Result(True, "👍 Shu holicha davom etamiz — video tayyorlanmoqda.")
        self.store.update_voice(voice_id, status="superseded")
        self.store.set_status(video_id, VOICE_WAITING)
        return Result(True, "🎙 Yaxshi, yangi ovozni kutaman. Matnni oxirigacha o'qib yuboring.")

    def _enqueue_render(self, video_id: int, voice_id: int, note: str = "") -> None:
        self.jobs.enqueue("render", {"video_id": video_id, "voice_id": voice_id, "note": note},
                          dedupe_key=f"render:{video_id}:{voice_id}", max_attempts=MAX_RENDER_TRIES)

    # ------------------------------------------------------------------------------------------- names / dates
    def publish_date(self, video: dict) -> date:
        slot = parse_iso(video["slot_at"]) if video.get("slot_at") else self.next_slot()
        return slot.astimezone(slots.zone(self.settings.schedule)).date()

    def base_for(self, video: dict, topic_title: str) -> str:
        return naming.base_name(self.publish_date(video), naming.slugify(topic_title))

    def set_publish_date(self, video_id: int, new_slot: datetime) -> list[str]:
        """The publish date changed: rename every file and folder, and the Buffer drafts' titles."""
        video = self.store.video(video_id)
        reel = self.reels.get(video_id)
        self.store.update_video(video_id, slot_at=new_slot)
        if not reel:
            return []
        old = reel["base"]
        new = naming.base_name(new_slot.astimezone(slots.zone(self.settings.schedule)).date(), old[11:])
        done = naming.rename_all(self.places, old, new, self.content.path if self.content else None)
        fields: dict[str, Any] = {"base": new}
        if reel.get("research_file"):
            fields["research_file"] = str(self.places.research_file(new))
        if reel.get("cover_path"):
            fields["cover_path"] = reel["cover_path"].replace(old, new)
        if reel.get("git_folder"):
            fields["git_folder"] = reel["git_folder"].replace(old, new)
        self.reels.upsert(video_id, **fields)
        if reel.get("drafts") and self.buffer is not None:
            title = (reel.get("captions") or {}).get("youtube_title") or video["title"]
            publish.rename_drafts(self.buffer, reel["drafts"], reel.get("captions") or {}, title)
            done.append("buffer drafts")
        for r in self.store.db.query("SELECT id, video_path FROM renders WHERE video_id=?", (video_id,)):
            if r["video_path"] and old in r["video_path"]:
                self.store.update_render(r["id"], video_path=r["video_path"].replace(old, new))
        log.info("Reel %s renamed %s -> %s: %s", video_id, old, new, ", ".join(done))
        return done

    # ------------------------------------------------------------------------------------- 1. research + topic
    def request_new(self, topic: str | None = None) -> int | None:
        if self.store.videos([RESEARCHING, DRAFTING]):
            return None
        video_id = self.store.create_video(RESEARCHING, topic or "", slot_at=self.next_slot())
        self.reels.upsert(video_id, base=naming.base_name(self.publish_date(self.store.video(video_id)), "tadqiqot"),
                          step="research")
        self.jobs.enqueue("research", {"video_id": video_id, "topic": topic}, dedupe_key=f"research:{video_id}")
        return video_id

    def recent_titles(self) -> list[str]:
        titles = self.store.recent_topics(self.cfg.recent_posts)
        titles += [r["title"] for r in self.store.db.query("SELECT title FROM videos WHERE title<>'' ORDER BY id DESC LIMIT ?",
                                                             (self.cfg.recent_posts,))]
        return list(dict.fromkeys(titles + research_mod.earlier_research_titles(self.places.research)))

    def buffer_insight(self) -> tuple[str, dict]:
        if self.buffer_stats is None:
            return "no statistics yet (Buffer is not connected); prefer clear, number-led explainers", {}
        try:
            posts = self.buffer_stats.sent_posts(30)
        except BufferAuthError:
            raise
        except Exception as exc:      # noqa: BLE001 - research still works without the statistics
            log.warning("Buffer statistics not read: %s", exc)
            return "statistics unavailable right now", {}
        stats = metric_summary(posts)
        best = [p.get("text", "")[:80] for p in top_posts(posts, 3)]
        return f"average per post: {stats}; best posts start with: {best}", stats

    def job_research(self, p: dict) -> None:
        video = self.store.video(p["video_id"])
        if not video or video["status"] != RESEARCHING:
            return
        hint, stats = self.buffer_insight()
        if p.get("topic"):
            hint += f". The owner asked for this topic: {p['topic']} (stay within water/wastewater)."
        avoid = self.recent_titles() + list(p.get("avoid") or [])
        result = self.reel_writer.research(hint, avoid, self.clock().date())
        topics = research_mod.dedupe(result["topics"], avoid, recent_limit=0)
        if len(topics) < 3:
            safe_record(self.lessons, "idea", [f"research returned only {len(topics)} new in-scope topics with sources"])
            more = self.reel_writer.research(hint + " Find DIFFERENT topics than before.",
                                             avoid + [t["title"] for t in result["topics"]], self.clock().date())
            topics = research_mod.dedupe(topics + more["topics"], avoid, recent_limit=0)
        if not topics:
            raise ValueError("research found no new water/wastewater topic with checkable sources")
        topics = topics[:5]
        base = naming.base_name(self.publish_date(video), naming.slugify(topics[0]["title"]))
        path = research_mod.write_markdown(self.places.research_file(base), topics, result["format_insight"], stats,
                                           self.clock().date())
        self.reels.upsert(video["id"], base=base, research_file=str(path), topics=topics, insight=result["format_insight"],
                          step="research")
        self.store.set_status(video["id"], TOPIC_PENDING)
        token = self.store.open_approval(video["id"], "topic", len(topics), self.settings.dry_run)
        self.outbox.add("topic_choice", video_id=video["id"], approval=token)

    def topic_decision(self, token: str, choice: int | str) -> Result:
        """choice: topic index (0-based) or "more" (research other topics)."""
        try:
            approval = self.store.decide(token, "approved" if choice != "more" else "regenerate")
        except ApprovalError as exc:
            return Result(False, str(exc))
        video = self.store.video(approval["video_id"])
        reel = self.reels.get(video["id"])
        if choice == "more":
            self.store.set_status(video["id"], RESEARCHING)
            self.jobs.enqueue("research", {"video_id": video["id"], "avoid": [t["title"] for t in reel["topics"]]},
                              dedupe_key=f"research:{video['id']}:more:{token}")
            return Result(True, "🔎 Boshqa mavzular qidirilmoqda.")
        topic = reel["topics"][int(choice)]
        new_base = self.base_for(video, topic["title"])
        old_file = Path(reel["research_file"]) if reel.get("research_file") else None
        if old_file and old_file.exists() and old_file != self.places.research_file(new_base):
            old_file.rename(self.places.research_file(new_base))
        self.reels.upsert(video["id"], base=new_base, topic_index=int(choice), step="script",
                          research_file=str(self.places.research_file(new_base)))
        self.store.update_video(video["id"], topic=topic["title"], title=topic["title"])
        self.store.set_status(video["id"], DRAFTING)
        self.jobs.enqueue("propose", {"video_id": video["id"]}, dedupe_key=f"propose:{video['id']}")
        return Result(True, f"✅ Mavzu tanlandi: «{topic['title']}». Ssenariy yozilmoqda.")

    # ------------------------------------------------------------------------------------------- 2. script
    def job_propose(self, p: dict) -> None:
        video = self.store.video(p["video_id"])
        if not video or video["status"] != DRAFTING:
            return
        reel = self.reels.get(video["id"])
        topic = reel["topics"][reel["topic_index"] or 0]
        self._publish_script(video["id"], self.reel_writer.script(topic, reel.get("insight") or ""))

    def job_rewrite(self, p: dict) -> None:
        video = self.store.video(p["video_id"])
        if not video or video["status"] != REVISING:
            return
        current = self.store.script(video["id"])
        if p.get("pasted"):
            texts = script_mod.parse_pasted(p["note"])
            new = script_mod.apply_pasted(current, texts) if texts else self.reel_writer.restructure(current, p["note"])
            found = script_mod.problems(new, self.cfg.words_per_second)
            if found:
                safe_record(self.lessons, "script", [f"owner's edited script: {f}" for f in found])
            self._publish_script(video["id"], new, "egasi tahrir qildi")
            return
        self._publish_script(video["id"], self.reel_writer.rewrite(current, p["note"]), p["note"])

    def job_regenerate(self, p: dict) -> None:           # "Qayta yaratish" on the script: a new script, same topic
        video = self.store.video(p["video_id"])
        if not video or video["status"] != REVISING:
            return
        reel = self.reels.get(video["id"])
        topic = reel["topics"][reel["topic_index"] or 0]
        self._publish_script(video["id"], self.reel_writer.script(topic, reel.get("insight") or ""), "yangi variant")

    def script_decision(self, token: str, action: str, note: str | None = None) -> Result:
        if action == "edit" and note and len(note.split()) >= 40:
            try:
                approval = self.store.decide(token, "edit")
            except ApprovalError as exc:
                return Result(False, str(exc))
            self.store.set_status(approval["video_id"], REVISING)
            self.jobs.enqueue("rewrite", {"video_id": approval["video_id"], "note": note, "pasted": True},
                              dedupe_key=f"rewrite:{approval['video_id']}")
            return Result(True, "✏️ Tahrirlangan matningiz qabul qilindi — 8 qismga bo'linib, qayta tasdiqqa keladi.")
        res = self._script_decision(token, action, note)
        if res.ok and action == "approve":
            video = self.store.video(self.store.approval(token)["video_id"])
            self.reels.upsert(video["id"], step="voice")
            self._write_script_file(video["id"])
        if res.ok and action == "regenerate":
            res = Result(True, "🔄 Shu mavzuda yangi ssenariy yozilmoqda.")
        return res

    def _write_script_file(self, video_id: int) -> None:
        reel = self.reels.get(video_id)
        work = self.places.work(reel["base"])
        work.mkdir(parents=True, exist_ok=True)
        (work / "script.md").write_text(script_mod.as_markdown(self.store.script(video_id)), encoding="utf-8")

    # ------------------------------------------------------------------ an unsolicited voice -> a new reel
    def new_video_from_voice(self, voice_id: int) -> Result:
        res = self._new_video_from_voice(voice_id)
        video = self.store.videos([DRAFTING])[0]
        self.reels.upsert(video["id"], base=naming.base_name(self.publish_date(video), "ovozdan"), step="script")
        return res

    def job_plan_from_voice(self, p: dict) -> None:
        video = self.store.video(p["video_id"])
        if not video or video["status"] != DRAFTING:
            return
        voice = self.store.voice(p["voice_id"])
        if not voice.get("clean_path"):
            try:
                self._process(p["voice_id"])
            except voice_mod.VoiceError as exc:
                self.store.update_voice(p["voice_id"], status="failed", problems=[str(exc)])
                self.store.set_status(video["id"], "failed", slot_at=None, last_error=str(exc))
                self.outbox.add("voice_unusable", video_id=video["id"], new_video=True)
                return
            voice = self.store.voice(p["voice_id"])
        script = self.reel_writer.from_voice(voice["transcript"])
        base = self.base_for(video, script["title"])
        self.reels.upsert(video["id"], base=base, step="script")
        self.store.update_voice(p["voice_id"], status="accepted", coverage=1.0)
        self._publish_script(video["id"], script, "egasining ovozidan")

    # ----------------------------------------------------------------------------------- 4. voice -> alignment
    def voice_targets(self) -> tuple[list[dict], list[dict]]:
        waiting = self.store.videos(WAITS_FOR_VOICE)
        rerecord = [v for v in self.store.videos(ACCEPTS_NEW_VOICE) if v["status"] not in WAITS_FOR_VOICE]
        return waiting, rerecord

    def _process(self, voice_id: int) -> voice_mod.ProcessedVoice:
        voice = self.store.voice(voice_id)
        self.store.update_voice(voice_id, status="processing")
        workdir = self.settings.voices_dir / f"voice_{voice_id:05d}"
        pv = voice_mod.process(Path(voice["raw_path"]), workdir, self.settings.voice, self.transcriber,
                               self.cfg.language, compressor=True)
        if pv.level_problems:
            safe_record(self.lessons, "voice", pv.level_problems)
        self.store.update_voice(voice_id, clean_path=str(pv.clean_path), duration=pv.duration, levels=pv.levels,
                                transcript=pv.transcript, words=[w.as_dict() for w in pv.words],
                                problems=pv.level_problems)
        return pv

    def job_process_voice(self, p: dict) -> None:
        video = self.store.video(p["video_id"])
        if not video or video["voice_id"] != p["voice_id"] or video["status"] != VOICE_PROCESSING:
            return
        try:
            pv = self._process(p["voice_id"])
        except voice_mod.VoiceError as exc:
            self.store.update_voice(p["voice_id"], status="failed", problems=[str(exc)])
            safe_record(self.lessons, "voice", [f"missing: {exc}"])
            self.store.set_status(video["id"], VOICE_WAITING)
            self.outbox.add("voice_unusable", video_id=video["id"])
            return
        script = self.store.script(video["id"])
        al = align([pt["text"] for pt in script["parts"]], pv.words, pv.duration)
        self.store.update_voice(p["voice_id"], coverage=al.coverage)
        cmp = voice_mod.Comparison(al.coverage, al.skipped)
        problems = voice_mod.voice_problems(cmp, pv.duration, script_mod.MAX_SECONDS + 1, self.settings.voice.min_coverage,
                                            min_seconds=script_mod.MIN_SECONDS - 5)
        if problems:
            safe_record(self.lessons, "voice", problems)
            self.store.update_voice(p["voice_id"], status="mismatch", problems=pv.level_problems + problems)
            self.store.set_status(video["id"], VOICE_CHECK)
            token = self.store.open_approval(video["id"], "voice_check", p["voice_id"], self.settings.dry_run)
            self.outbox.add("voice_check", video_id=video["id"], approval=token, problems=problems)
            return
        self._accept_voice(video["id"], p["voice_id"])

    # ------------------------------------------------------------------------- 3-4. B-roll + render (_vN)
    def job_render(self, p: dict, job=None) -> None:
        video = self.store.video(p["video_id"])
        if not video or video["voice_id"] != p["voice_id"] or video["status"] != RENDERING:
            return
        reel = self.reels.get(video["id"])
        base, work = reel["base"], self.places.work(reel["base"])
        work.mkdir(parents=True, exist_ok=True)
        script = self.store.script(video["id"])
        self._write_script_file(video["id"])
        clips = broll_mod.load_sources(work)
        replace = set(p.get("replace_parts") or [])
        if replace and clips:                                        # a fix asked for new footage in some parts
            keep = [c for c in clips if c.part not in replace]
            for c in clips:
                if c.part in replace:
                    (work / c.file).unlink(missing_ok=True)
                    for norm in work.glob(f"broll/*-{c.part}.norm.*"):
                        norm.unlink(missing_ok=True)
            new = broll_mod.collect([pt for pt in script["parts"] if pt["part"] in replace], work, self.broll_providers)
            # keep the original numbering: re-collected clips get their part's position
            for c in new:
                idx = [pt["part"] for pt in script["parts"]].index(c.part) + 1
                target = f"broll/{idx:02d}-{c.part}{Path(c.file).suffix}"
                if c.file != target:
                    (work / c.file).rename(work / target)
                    c.file = target
            clips = sorted(keep + new, key=lambda c: script_mod.PARTS.index(c.part))
            broll_mod.write_sources(work, clips)
        if len(clips) != len(script_mod.PARTS):
            self.reels.upsert(video["id"], step="broll")
            clips = broll_mod.collect(script["parts"], work, self.broll_providers)
        voice = self.store.voice(video["voice_id"])
        wav, words, duration = self._voice_words(voice)
        al = align([pt["text"] for pt in script["parts"]], words, duration)
        lines = subtitle_lines(al.words)
        lay = default_layout()
        checklist.write_document(self.settings.root / "docs" / "reel-mistakes-checklist.md", self.lessons)
        before = checklist.before_render(script, clips, duration, al.coverage, lay, 64, 150, self.cfg.words_per_second)
        self.reels.upsert(video["id"], step="render")
        if not before.passed:
            safe_record(self.lessons, "render", before.problems)
        rr = self.reel_renderer.render(base=base, script=script, clips=clips, voice_wav=wav, words=al.words,
                                       part_starts=al.part_starts, lines=lines, voice_seconds=duration)
        checklist.save(work / f"checklist_v{rr.version}.json", before, rr.after)
        render_id, _ = self.store.add_render(video["id"], video["script_version"], voice["id"])
        fields = dict(video_path=str(rr.export), duration=rr.duration, title=script["title"],
                      caption=script.get("key_fact", ""), hashtags=script.get("hashtags", []),
                      report={"version": rr.version, "before": before.as_dict(), "after": rr.after.as_dict(),
                              "frames": [{"part": a, "t": round(b, 2), "file": str(c.relative_to(work))} for a, b, c in rr.frames]})
        self.reels.upsert(video["id"], version=rr.version, step="review",
                          checklist={"before": before.as_dict(), "after": rr.after.as_dict()})
        if not (before.passed and rr.after.passed):
            self.store.update_render(render_id, status="failed",
                                     last_error="; ".join(before.problems + rr.after.problems)[:1000], **fields)
            safe_record(self.lessons, "quality", before.problems + rr.after.problems)
            raise RuntimeError("checklist failed: " + "; ".join(before.problems + rr.after.problems)[:500])
        self.store.update_render(render_id, status="ready", **fields)
        if job and job.attempts > 1 and self.lessons:
            self.lessons.fix_open("quality", "a re-render (new footage / new version) passed the checklist")
        if not self.store.set_status(video["id"], VIDEO_PENDING, expected=(RENDERING,), render_id=render_id):
            return
        token = self.store.open_approval(video["id"], "video", render_id, self.settings.dry_run)
        self.outbox.add("video_approval", video_id=video["id"], approval=token)

    def voice_limit(self) -> float:
        return script_mod.MAX_SECONDS + 1.0

    def _voice_words(self, voice: dict):
        path, words, duration = Path(voice["clean_path"]), voice_mod.words_from_json(voice["words"]), voice["duration"]
        limit = self.voice_limit()
        if duration > limit:
            factor = duration / (limit - 0.2)
            fast = path.with_name("voice_fit.wav")
            from .video import ffmpeg
            ffmpeg.run([ffmpeg.binary("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", str(path), "-af",
                        f"atempo={factor:.4f}", str(fast)])
            words = [voice_mod.Word(w.text, w.start / factor, w.end / factor) for w in words]
            path, duration = fast, round(voice_mod.wav_duration(fast), 2)
        return path, words, duration

    # ------------------------------------------------------------------------------- 5. review, fixes, cover
    def video_decision(self, token: str, action: str, note: str | None = None) -> Result:
        """approve -> ask for the cover; edit (fix note) -> re-render as _v(N+1); reject; regenerate = new footage."""
        decision = {"approve": "approved", "reject": "rejected", "edit": "edit", "regenerate": "regenerate"}[action]
        try:
            approval = self.store.decide(token, decision)
        except ApprovalError as exc:
            return Result(False, str(exc))
        vid = approval["video_id"]
        video = self.store.video(vid)
        if action == "approve":
            self.store.set_status(vid, COVER_WAITING)
            self.reels.upsert(vid, step="cover")
            self.outbox.add("cover_request", video_id=vid)
            return Result(True, "✅ Video tasdiqlandi. Endi muqovani (rasm) shu chatga yuboring.")
        if action == "reject":
            self.store.set_status(vid, REJECTED, slot_at=None)
            return Result(True, "❌ Video rad etildi.")
        self.store.set_status(vid, RENDERING)
        if action == "regenerate":
            script = self.store.script(vid)
            self.jobs.enqueue("render", {"video_id": vid, "voice_id": video["voice_id"],
                                         "replace_parts": [p["part"] for p in script["parts"]]},
                              dedupe_key=f"render:{vid}:{video['voice_id']}:{token}", max_attempts=MAX_RENDER_TRIES)
            return Result(True, "🔁 Yangi B-roll bilan qayta tayyorlanmoqda (keyingi versiya).")
        reel = self.reels.get(vid)
        self.reels.upsert(vid, fix_notes=(reel.get("fix_notes") or []) + [note or ""])
        safe_record(self.lessons, "owner", [f"The owner's fix for a finished reel: {note}"])
        self.jobs.enqueue("reel_fix", {"video_id": vid, "note": note or ""}, dedupe_key=f"reel_fix:{vid}:{token}")
        return Result(True, "✏️ Tuzatish qabul qilindi — keyingi versiya tayyorlanmoqda.")

    def job_reel_fix(self, p: dict) -> None:
        video = self.store.video(p["video_id"])
        if not video or video["status"] != RENDERING:
            return
        script = self.store.script(video["id"])
        plan = self.reel_writer.fix_plan(script, p["note"])
        new = json.loads(json.dumps(script))
        replace = []
        if plan.get("title"):
            new["title"] = plan["title"][:45]
        for change in plan.get("parts") or []:
            part = next((x for x in new["parts"] if x["part"] == change["part"]), None)
            if not part:
                continue
            if change.get("broll"):
                part["broll"] = change["broll"]
                replace.append(part["part"])
            if change.get("info") is not None:
                part["info"] = change["info"]
            if change.get("subtitle_fix"):
                part["text"] = change["subtitle_fix"]
        self.store.add_script(video["id"], new, f"tuzatish: {p['note']}")
        self.jobs.enqueue("render", {"video_id": video["id"], "voice_id": video["voice_id"], "replace_parts": replace},
                          dedupe_key=f"render:{video['id']}:{video['voice_id']}:fix:{now_iso()}", max_attempts=MAX_RENDER_TRIES)

    def receive_cover(self, src: Path, suffix: str = "") -> Result:
        """Owner law 16: the owner's cover is used AS IS (same bytes: no crop, text, overlay or resize). Only a file
        in a format Buffer does not take (not JPEG/PNG) is converted to PNG, and the owner is told."""
        waiting = self.store.videos([COVER_WAITING])
        if not waiting:
            return Result(False, "Hozir muqova kutayotgan video yo'q.")
        video = waiting[0]
        reel = self.reels.get(video["id"])
        work = self.places.work(reel["base"])
        work.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        try:
            with Image.open(src) as im:
                im.verify()
            with Image.open(src) as im:
                fmt, size = im.format, im.size
                note = ""
                if fmt in ("JPEG", "PNG"):
                    cover = work / f"{reel['base']}_cover{'.jpg' if fmt == 'JPEG' else '.png'}"
                    shutil.copyfile(src, cover)                       # unchanged
                else:
                    cover = work / f"{reel['base']}_cover.png"
                    im.save(cover, "PNG")                             # same pixels, only the file format changes
                    note = f" (Fayl {fmt} formatida edi — Buffer JPG/PNG qabul qilgani uchun faqat formati PNG ga o'zgartirildi, rasm o'zi o'zgarmadi.)"
        except Exception:                                     # noqa: BLE001
            return Result(False, "Bu fayl rasm emas. Muqovani JPG yoki PNG rasm sifatida yuboring.")
        if size[1] < size[0]:
            note += " (Eslatma: muqova vertikal emas — Reels uchun 1080×1920 yaxshiroq; bot uni o'zgartirmaydi.)"
        for old in work.glob(f"{reel['base']}_cover.*"):
            if old != cover:
                old.unlink()
        self.reels.upsert(video["id"], cover_path=str(cover), step="publish")
        self.store.set_status(video["id"], PUBLISHING)
        self.jobs.enqueue("reel_publish", {"video_id": video["id"]}, dedupe_key=f"reel_publish:{video['id']}")
        return Result(True, f"🖼 Muqovangiz qabul qilindi (o'zgartirilmasdan): «{video['title']}». GitHub va Buffer "
                            f"qoralamalariga tayyorlanmoqda.{note}")

    def job_reel_publish(self, p: dict) -> None:
        video = self.store.video(p["video_id"])
        if not video or video["status"] != PUBLISHING:
            return
        reel = self.reels.get(video["id"])
        base, work = reel["base"], self.places.work(reel["base"])
        render = self.store.render(video["render_id"])
        script = self.store.script(video["id"])
        cover = Path(reel["cover_path"])
        files = {f"{base}.mp4": Path(render["video_path"]), f"{base}_cover{cover.suffix}": cover,
                 "script.md": work / "script.md"}
        if reel.get("research_file") and Path(reel["research_file"]).exists():
            files["research.md"] = Path(reel["research_file"])
        if (work / "SOURCES.md").exists():
            files["SOURCES.md"] = work / "SOURCES.md"
        gres = self.content.publish(base, files, script["title"])      # the user's OWN content repo (Task 07)
        self.reels.upsert(video["id"], git_note=gres.note, git_folder=gres.folder)
        drafts = reel.get("drafts") or {}
        if self.buffer is not None and not drafts:
            style = publish.learn_style(self.claude_for_captions(), self.buffer_stats,
                                        self.settings.data_dir / "style" / "caption_style.md")
            captions = publish.write_captions(self.claude_for_captions(), script, style, self.cfg.language)
            drafts = publish.create_drafts(self.buffer, captions, Path(render["video_path"]), self.public_files)
            self.reels.upsert(video["id"], captions=captions, drafts=drafts)
        self.store.set_status(video["id"], BUFFER_PENDING)
        self.reels.upsert(video["id"], step="buffer")
        self.outbox.add("buffer_ready", video_id=video["id"])

    def fix_from_voice(self, voice_id: int, video_id: int) -> Result:
        """A voice note with fixes for the finished reel: transcribed, then handled like a typed fix note."""
        approval = self.store.pending_approval(video_id, "video")
        if not approval:
            return Result(False, "Bu video uchun tuzatish endi kerak emas.")
        self.store.update_voice(voice_id, video_id=video_id, status="received")
        try:
            pv = self._process(voice_id)
        except voice_mod.VoiceError as exc:
            return Result(False, f"Ovozli izohni tushunib bo'lmadi ({exc}). Matn bilan yozib yuboring.")
        self.store.update_voice(voice_id, status="fix_note")
        res = self.video_decision(approval["id"], "edit", pv.transcript)
        return Result(res.ok, res.message + f"\n🗒 Izohingiz: «{pv.transcript[:300]}»" if res.ok else res.message)

    def claude_for_captions(self):
        return self.reel_writer.claude

    # ----------------------------------------------------------------------------------- 6. live + story
    def check_live(self, video: dict) -> bool:
        """Read-only: has the owner's scheduled Instagram post gone live? Then the story draft (owner's cover)."""
        reel = self.reels.get(video["id"])
        if not reel or not reel.get("drafts") or self.buffer is None:
            return False
        links = {}
        for svc, pid in reel["drafts"].items():
            p = self.buffer.post(pid)
            if p.get("status") == "sent" and p.get("externalLink"):
                links[svc] = p["externalLink"]
        if links:
            self.reels.upsert(video["id"], live_links=links)
        link = links.get("instagram")
        if not link:
            return False
        captions = reel.get("captions") or {}
        story = None
        try:
            story = publish.create_story_draft(self.buffer, Path(reel["cover_path"]), link,
                                               captions.get("story_text") or "Yangi reel!", self.public_files)
        except Exception as exc:                              # noqa: BLE001 - the Telegram message still goes out
            log.warning("Story draft not created: %s", exc)
        self.reels.upsert(video["id"], live_link=link, story_draft=story, step="story")
        self.store.set_status(video["id"], STORY_PENDING)
        self.outbox.add("story_ready", video_id=video["id"])
        return True

    def story_done(self, video_id: int) -> Result:
        video = self.store.video(video_id)
        if not video or video["status"] != STORY_PENDING:
            return Result(False, "Bu story allaqachon belgilangan.")
        self.store.set_status(video_id, DONE)
        self.reels.upsert(video_id, step="done")
        return Result(True, "🎉 Rahmat! Reel tugadi. Keyingi mavzu tadqiqoti vaqtida boshlanadi.")

    def tick(self) -> None:
        now = self.clock()
        for video in self.store.videos(ACTIVE):
            if video["status"] == BUFFER_PENDING:
                key = f"live_check:{video['id']}"
                last = self.kv.get(key)
                if not last or now - parse_iso(last) >= timedelta(minutes=self.cfg.live_check_minutes):
                    self.kv.set(key, now.isoformat())
                    try:
                        self.check_live(video)
                    except Exception as exc:                  # noqa: BLE001 - checked again next time
                        log.warning("Live check failed: %s", exc)
                continue
            if video["status"] in (PUBLISHING, STORY_PENDING, COVER_WAITING) or not video["slot_at"]:
                continue
            slot = parse_iso(video["slot_at"])
            if (video["status"] in WAITS_FOR_VOICE and not video["reminded_at"]
                    and timedelta(0) < slot - now <= timedelta(hours=self.settings.voice.reminder_hours)):
                self.store.update_video(video["id"], reminded_at=now)
                self.outbox.add("voice_reminder", video_id=video["id"])
            if slot <= now:                                   # not ready at its date: next free date, files renamed
                new = slots.next_free_slot(self.settings.schedule, now, self.store.taken_slots() - {slot})
                self.set_publish_date(video["id"], new)
        self.ensure_pipeline()

    # ----------------------------------------------------------------------------------------- jobs
    def handlers(self):
        return {"research": self.job_research, "propose": self.job_propose, "regenerate": self.job_regenerate,
                "rewrite": self.job_rewrite, "process_voice": self.job_process_voice,
                "plan_from_voice": self.job_plan_from_voice, "reel_fix": self.job_reel_fix,
                "reel_publish": self.job_reel_publish}

    def recover(self) -> list[str]:
        done = self._recover_generic()
        active = {(j["kind"], json.loads(j["payload_json"]).get("video_id")) for j in self.jobs.active()}
        for video in self.store.videos([RESEARCHING, PUBLISHING]):
            kind = "research" if video["status"] == RESEARCHING else "reel_publish"
            if (kind, video["id"]) not in active:
                self.jobs.enqueue(kind, {"video_id": video["id"]}, dedupe_key=f"{kind}:{video['id']}")
                done.append(f"video {video['id']}: {kind} resumed")
        return done

    def _recover_generic(self) -> list[str]:
        """After a restart: running jobs go back to the queue, and a video whose job was lost between two steps gets
        it again (every step re-checks the video's state, so nothing runs twice)."""
        done = []
        n = self.jobs.recover_running()
        if n:
            done.append(f"{n} interrupted job(s) re-queued")
        active = {(j["kind"], json.loads(j["payload_json"]).get("video_id")) for j in self.jobs.active()}
        kinds = {j[0] for j in active}
        for video in self.store.videos(ACTIVE):
            vid, st = video["id"], video["status"]
            mine = {k for k, v in active if v == vid}
            if st == DRAFTING and not mine & {"propose", "plan_from_voice"}:
                if video["origin"] == "voice" and video["voice_id"]:
                    self.jobs.enqueue("plan_from_voice", {"video_id": vid, "voice_id": video["voice_id"]},
                                      dedupe_key=f"plan_from_voice:{vid}")
                else:
                    self.jobs.enqueue("propose", {"video_id": vid, "topic": video["topic"] or None},
                                      dedupe_key=f"propose:{vid}")
                done.append(f"video {vid}: drafting resumed")
            elif st == VOICE_PROCESSING and "process_voice" not in mine and video["voice_id"]:
                self.jobs.enqueue("process_voice", {"video_id": vid, "voice_id": video["voice_id"]},
                                  dedupe_key=f"process_voice:{video['voice_id']}")
                done.append(f"video {vid}: voice processing resumed")
            elif st == RENDERING and not mine & {"render", "revise_package"} and video["voice_id"]:
                self._enqueue_render(vid, video["voice_id"])
                done.append(f"video {vid}: render resumed")
            elif st == REVISING and not mine & {"regenerate", "rewrite"}:
                self.jobs.enqueue("regenerate", {"video_id": vid}, dedupe_key=f"regenerate:{vid}")
                done.append(f"video {vid}: revision resumed")
        del kinds
        return done

    def run_job(self, job: Job) -> None:
        """Run one job and map every failure to the right reaction (postpone, retry, alert, give up)."""
        try:
            if job.kind == "render":
                self.job_render(job.payload, job)
            else:
                self.handlers()[job.kind](job.payload)
            self.jobs.complete(job.id)
        except ClaudeBudgetWait as exc:
            self.jobs.postpone(job, exc.until, exc.reason)
        except ClaudeUsageLimit as exc:
            until = backoff_until(self.settings.claude, exc, self.clock())
            self.jobs.postpone(job, until, "Claude usage limit")
            notice = self.budget.claim_limit_notice(str(exc), until) if self.budget else None
            if notice:
                self.outbox.add("limit", text=notice)
        except ClaudeAuthError as exc:
            self.jobs.postpone(job, self.clock() + AUTH_RETRY, str(exc))
            self._owner_alert("claude", "🔑 Claude tizimdan chiqib ketgan. Terminalda bir marta `claude` ni ishga "
                                        "tushirib, /login qiling (1-akkaunt). Ish o'zi davom etadi.")
        except BufferAuthError as exc:
            self.jobs.postpone(job, self.clock() + AUTH_RETRY, str(exc))
            self._owner_alert("buffer", "🔑 Buffer API kaliti ishlamayapti (eskirgan yoki o'chirilgan). Yangi kalitni "
                                        "`.env` dagi BUFFER_API_KEY ga yozing (docs/OWNER_TODO.md). Qoralamalar shundan "
                                        "keyin o'zi tayyorlanadi.")
        except BufferRateLimit as exc:
            self.jobs.postpone(job, self.clock() + timedelta(minutes=20), str(exc))
        except Exception as exc:   # noqa: BLE001 - logged, retried with back-off, then given up quietly
            log.exception("Job %s %s failed", job.id, job.kind)
            if not self.jobs.retry_later(job, f"{type(exc).__name__}: {exc}", min(3600, 60 * 2 ** job.attempts)):
                self._give_up(job, f"{type(exc).__name__}: {exc}")

    def _give_up(self, job: Job, error: str) -> None:
        p = job.payload
        stage = {"render": "render", "process_voice": "voice", "research": "idea"}.get(job.kind, "script")
        safe_record(self.lessons, stage, [f"{job.kind} gave up: {error[:300]}"])
        video = self.store.video(p.get("video_id", 0))
        if video and video["status"] in ACTIVE:
            self.store.set_status(video["id"], FAILED, slot_at=None, last_error=error[:1000])
        log.error("Job %s %s gave up: %s", job.id, job.kind, error[:300])

    def _owner_alert(self, what: str, text: str) -> None:
        """An alert the owner must act on, at most once a day per problem (law 5)."""
        key = f"alert:{what}"
        last = self.kv.get(key)
        now = self.clock()
        if last and now - parse_iso(last) < timedelta(hours=24):
            return
        self.kv.set(key, now.isoformat())
        self.outbox.add("owner_action", text=text)

    def _limit_alert(self, what: str, until: datetime, head: str) -> None:
        key = f"limit:{what}"
        if self.kv.get(key) == until.isoformat():
            return
        self.kv.set(key, until.isoformat())
        self.outbox.add("limit", text=f"⏸ {head}. Soat {tashkent_time(until, self.clock())} da (Toshkent vaqti) "
                                      "qayta ochiladi — ish o'zi davom etadi.")

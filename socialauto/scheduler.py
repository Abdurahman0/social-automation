"""The bot service's loop: delivers Telegram messages, runs the time-based checks and one job at a time.

Jobs run one by one in a worker thread (renders are memory-heavy; Claude usage stays predictable). Analytics are
refreshed in their own task so a long render never delays them.

Task 10 (no silent failures):
* a watchdog: a job running longer than its limit (research 20 min, render 60 min, ...) is reported to the owner and
  re-queued; the stuck thread is left alone (it cannot be killed safely) and no second job of the same kind starts
  while it is still alive (two renders at once would not fit in memory). A 'running' row nobody runs is re-queued;
* after an «internet yo'q» message the loop watches for the network and sends one «qayta ulandi»;
* a crash of the loop, a failed statistics refresh and a failed automatic update reach the owner once.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Awaitable, Callable

from .app import App
from .db import parse_iso
from .errors import DEFAULT_TIMEOUT_MIN, JOB_TIMEOUT_MIN
from .jobs import Job
from .workflow import CLAUDE_JOBS

log = logging.getLogger(__name__)

PAUSED_KEY = "paused"
TICK_SECONDS = 15
UPDATE_REASON_UZ = {
    "diverged": "bu kompyuterdagi kodda alohida o'zgarishlar (commit) bor, shuning uchun yangilanish ustiga "
                "qo'yilmadi",
    "local_changes": "bu kompyuterda dastur fayllari qo'lda o'zgartirilgan, shuning uchun yangilanish ularni "
                     "buzmaslik uchun o'rnatilmadi",
    "merge_failed": "yangilanishni qo'shib bo'lmadi (git rad etdi)",
}


class Scheduler:
    def __init__(self, app: App, deliver: Callable[[], Awaitable[None]], analytics=None, updater=None):
        self.app = app
        self.deliver = deliver
        self.analytics = analytics
        self.updater = updater
        self.timeouts = dict(JOB_TIMEOUT_MIN)          # minutes per job kind (tests make them short)
        self.current: Job | None = None
        self.abandoned: list[tuple[Job, asyncio.Future]] = []

    def paused(self) -> bool:
        return bool(self.app.kv.get(PAUSED_KEY, False))

    def limit_minutes(self, kind: str) -> int:
        return self.timeouts.get(kind, DEFAULT_TIMEOUT_MIN)

    async def run(self, stop: asyncio.Event) -> None:
        for line in await asyncio.to_thread(self.app.workflow.recover):
            log.info("Recovery: %s", line)
        tasks = [asyncio.create_task(self._jobs(stop))]
        if self.analytics is not None:
            tasks.append(asyncio.create_task(self._analytics(stop)))
        if self.updater is not None and self.app.settings.github.auto_update:
            tasks.append(asyncio.create_task(self._updates(stop)))
        await asyncio.gather(*tasks)

    async def _sleep(self, stop: asyncio.Event, seconds: float) -> None:
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except TimeoutError:
            pass

    def busy_kinds(self) -> tuple[str, ...]:
        """Kinds whose stuck (abandoned) run is still alive: no second one starts meanwhile."""
        self.abandoned = [(j, f) for j, f in self.abandoned if not f.done()]
        return tuple({j.kind for j, _ in self.abandoned})

    async def run_one(self, job: Job) -> None:
        """Run a job in a worker thread under the watchdog."""
        app = self.app
        self.current = job
        fut = asyncio.ensure_future(asyncio.to_thread(app.workflow.run_job, job))
        minutes = self.limit_minutes(job.kind)
        try:
            await asyncio.wait_for(asyncio.shield(fut), timeout=minutes * 60)
        except TimeoutError:
            log.error("Job %s %s ran longer than %s min: reported and re-queued", job.id, job.kind, minutes)
            self.abandoned.append((job, fut))
            await asyncio.to_thread(app.workflow.job_timed_out, job, minutes)
        finally:
            self.current = None

    def check_orphans(self) -> int:
        """'running' rows that nothing runs (and that are older than their limit) are reported and re-queued."""
        app, n = self.app, 0
        live = {j.id for j, _ in self.abandoned} | ({self.current.id} if self.current else set())
        now = app.clock()
        for row in app.jobs.running():
            if row["id"] in live:
                continue
            minutes = self.limit_minutes(row["kind"])
            if now - parse_iso(row["updated_at"]) < timedelta(minutes=minutes):
                continue                                    # maybe another process (the CLI) is running it
            app.workflow.job_timed_out(Job(row["id"], row["kind"], row["payload"], row["attempts"],
                                           row["max_attempts"]), minutes)
            n += 1
        return n

    async def _network(self) -> None:
        from . import netcheck
        rep = self.app.workflow.reporter
        if rep.net_down() and await asyncio.to_thread(netcheck.online):
            rep.back_online()

    async def _jobs(self, stop: asyncio.Event) -> None:
        app = self.app
        rep = app.workflow.reporter
        while not stop.is_set():
            try:
                await self.deliver()
                resume = app.budget.take_resume_notice()
                if resume:
                    app.outbox.add("limit", text=resume)
                await self._network()
                if not self.paused():
                    await asyncio.to_thread(app.workflow.tick)
                    await asyncio.to_thread(self.check_orphans)
                    claude_jobs = getattr(app.workflow, "claude_jobs", CLAUDE_JOBS)
                    exclude = (claude_jobs if app.budget.paused_until() else ()) + self.busy_kinds()
                    job = app.jobs.claim_next(exclude=exclude, now=app.clock().isoformat())
                    if job:
                        log.info("Running job %s %s (attempt %s)", job.id, job.kind, job.attempts)
                        await self.run_one(job)
                        await self.deliver()
                        rep.resolved("scheduler")
                        continue                # look for the next job right away
                rep.resolved("scheduler")
            except Exception as exc:            # noqa: BLE001 - the loop never dies; the owner hears about it once
                log.exception("Scheduler tick failed")
                try:
                    rep.problem("scheduler", exc)
                except Exception:               # noqa: BLE001
                    log.exception("could not queue the scheduler error message")
            await self._sleep(stop, TICK_SECONDS)

    async def _analytics(self, stop: asyncio.Event) -> None:
        minutes = self.app.settings.analytics.refresh_minutes
        rep = self.app.workflow.reporter
        await self._sleep(stop, 20)
        while not stop.is_set():
            try:
                alerts = await asyncio.to_thread(self.analytics.refresh)
                for what, text in alerts:
                    self.app.workflow._owner_alert(what, text)
                rep.resolved("analytics")
            except Exception as exc:            # noqa: BLE001
                log.exception("Analytics refresh failed")
                from .errors import explain
                rep.problem("analytics", exc, text=f"⚠️ «Statistika» yangilanmadi: {explain(exc)[1]}. "
                                                   f"{minutes} daqiqadan keyin o'zim qayta urinaman.")
            await self._sleep(stop, timedelta(minutes=minutes).total_seconds())

    def check_update(self) -> dict:
        """Fetch + fast-forward if a new version is there (Task 10: the bot updates itself). A failure that needs the
        owner reaches Telegram once; an offline check is just tried again later."""
        rep = self.app.workflow.reporter
        st = self.updater.status(fetch=True, force=True)
        if not st.get("available"):
            if st.get("reason") != "offline":
                rep.resolved("update")
            return {"ok": False, "reason": st.get("reason") or "up_to_date"}
        if not st.get("can_update"):
            res = {"ok": False, "reason": st.get("reason") or "merge_failed"}
        else:
            res = self.updater.apply()
        if res.get("ok"):
            rep.resolved("update")
            log.info("Update installed (%s files); the bot restarts", res.get("updated"))
        elif res.get("reason") in UPDATE_REASON_UZ:
            rep.problem("update", res["reason"], text=(
                f"⚠️ «Avtomatik yangilanish»: yangi versiya bor ({st.get('behind', 0)} ta o'zgarish), lekin "
                f"o'rnatilmadi — {UPDATE_REASON_UZ[res['reason']]}. Saytdagi «Sozlamalar» → «Yangilanish» bo'limida "
                "holatni ko'ring."))
        return res

    async def _updates(self, stop: asyncio.Event) -> None:
        hours = max(1, self.app.settings.github.update_check_hours)
        await self._sleep(stop, 120)                    # let the bot settle after a start (or the last update)
        while not stop.is_set():
            started = time.monotonic()
            try:
                await asyncio.to_thread(self.check_update)
            except Exception as exc:            # noqa: BLE001
                log.exception("Automatic update check failed")
                self.app.workflow.reporter.problem("update", exc)
            await self._sleep(stop, max(60.0, hours * 3600 - (time.monotonic() - started)))

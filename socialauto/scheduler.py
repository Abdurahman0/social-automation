"""The bot service's loop: delivers Telegram messages, runs the time-based checks and one job at a time.

Jobs run one by one in a worker thread (renders are memory-heavy; Claude usage stays predictable). Analytics are
refreshed in their own task so a long render never delays them.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Awaitable, Callable

from .app import App
from .workflow import CLAUDE_JOBS

log = logging.getLogger(__name__)

PAUSED_KEY = "paused"
TICK_SECONDS = 15


class Scheduler:
    def __init__(self, app: App, deliver: Callable[[], Awaitable[None]], analytics=None):
        self.app = app
        self.deliver = deliver
        self.analytics = analytics

    def paused(self) -> bool:
        return bool(self.app.kv.get(PAUSED_KEY, False))

    async def run(self, stop: asyncio.Event) -> None:
        for line in await asyncio.to_thread(self.app.workflow.recover):
            log.info("Recovery: %s", line)
        tasks = [asyncio.create_task(self._jobs(stop))]
        if self.analytics is not None:
            tasks.append(asyncio.create_task(self._analytics(stop)))
        await asyncio.gather(*tasks)

    async def _sleep(self, stop: asyncio.Event, seconds: float) -> None:
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except TimeoutError:
            pass

    async def _jobs(self, stop: asyncio.Event) -> None:
        app = self.app
        while not stop.is_set():
            try:
                await self.deliver()
                resume = app.budget.take_resume_notice()
                if resume:
                    app.outbox.add("limit", text=resume)
                if not self.paused():
                    await asyncio.to_thread(app.workflow.tick)
                    claude_jobs = getattr(app.workflow, "claude_jobs", CLAUDE_JOBS)
                    exclude = claude_jobs if app.budget.paused_until() else ()
                    job = app.jobs.claim_next(exclude=exclude, now=app.clock().isoformat())
                    if job:
                        log.info("Running job %s %s (attempt %s)", job.id, job.kind, job.attempts)
                        await asyncio.to_thread(app.workflow.run_job, job)
                        await self.deliver()
                        continue                # look for the next job right away
            except Exception:                   # noqa: BLE001 - the loop never dies
                log.exception("Scheduler tick failed")
            await self._sleep(stop, TICK_SECONDS)

    async def _analytics(self, stop: asyncio.Event) -> None:
        minutes = self.app.settings.analytics.refresh_minutes
        await self._sleep(stop, 20)
        while not stop.is_set():
            try:
                alerts = await asyncio.to_thread(self.analytics.refresh)
                for what, text in alerts:
                    self.app.workflow._owner_alert(what, text)
            except Exception:                   # noqa: BLE001
                log.exception("Analytics refresh failed")
            await self._sleep(stop, timedelta(minutes=minutes).total_seconds())

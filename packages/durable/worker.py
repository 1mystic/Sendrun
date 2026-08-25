"""The durable worker process: poll loop, dispatch, reaper, graceful shutdown.

This is the process you SIGKILL in the crash demo. Everything in it is written
to make that survivable:

  - The poll loop only ever holds a lease for the duration of one task's
    handler call — killing the process mid-handler leaves the lease to expire
    on its own; nothing needs cleanup on the way down.
  - The reaper runs as an independent async task on its own timer, so it
    keeps expiring stale leases even if the dispatch loop is wedged.
  - Graceful shutdown (SIGTERM) stops picking up new tasks and waits for
    in-flight ones to finish, but does NOT extend their leases indefinitely —
    a handler that hangs past its lease is exactly the case the reaper exists
    to recover from, by design.

NOTE ON VERIFICATION: the SQL this executes (DEQUEUE, REAP_EXPIRED, etc. in
queue.py) is Postgres-specific by design — FOR UPDATE SKIP LOCKED has no SQLite
equivalent, which is why the durability test suite (test_durability.py)
exercises the LOGIC here against an in-memory fake store rather than this
module directly. This file's SQL execution paths have NOT been run against a
live Postgres instance in this environment (no Postgres/Docker available
locally) — verify against a real Neon branch before relying on this in
production. See NEXT.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from packages.durable.queue import (
    COMPLETE,
    DEQUEUE,
    HEARTBEAT,
    KILL,
    REAP_EXPIRED,
    RETRY_LATER,
    PermanentTaskError,
    RetryPolicy,
    Task,
    TaskStatus,
    TransientTaskError,
)

log = logging.getLogger("sendrun.worker")

TaskHandler = Callable[[dict[str, Any]], Awaitable[None]]


def _row_to_task(row: Any) -> Task:
    return Task(
        id=row.id, queue=row.queue, task_type=row.task_type,
        payload=row.payload if isinstance(row.payload, dict) else json.loads(row.payload),
        idempotency_key=row.idempotency_key, status=TaskStatus(row.status),
        run_after=row.run_after, lease_until=row.lease_until, lease_owner=row.lease_owner,
        attempt=row.attempt, max_attempts=row.max_attempts, last_error=row.last_error,
        parent_id=row.parent_id, created_at=row.created_at, updated_at=row.updated_at,
    )


@dataclass(slots=True)
class WorkerConfig:
    worker_id: str
    queue: str = "sendrun-send"
    lease_seconds: int = 30
    poll_interval_seconds: float = 1.0
    reap_interval_seconds: float = 15.0
    batch_size: int = 10
    retry_policy: RetryPolicy = RetryPolicy()


class Worker:
    """Runs the dispatch loop and the reaper as two independent asyncio tasks,
    both stopping cleanly on `.stop()` — this is what a SIGTERM handler calls,
    and it is deliberately NOT what "the process got SIGKILLed" looks like.
    The whole point of the reaper is to make that second, uncontrolled case
    recoverable without any cleanup code running at all.
    """

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        handlers: dict[str, TaskHandler],
        config: WorkerConfig,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.handlers = handlers
        self.config = config
        self._stopping = asyncio.Event()
        self._inflight: set[asyncio.Task] = set()

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self.stop)
            except NotImplementedError:
                pass  # signals aren't available on every platform (e.g. some test runners)

        reaper = asyncio.create_task(self._reap_loop())
        try:
            await self._dispatch_loop()
        finally:
            self._stopping.set()
            reaper.cancel()
            if self._inflight:
                log.info("worker.draining", extra={"n": len(self._inflight)})
                await asyncio.gather(*self._inflight, return_exceptions=True)

    def stop(self) -> None:
        self._stopping.set()

    # ── dispatch ─────────────────────────────────────────────────────────

    async def _dispatch_loop(self) -> None:
        while not self._stopping.is_set():
            claimed = await self._dequeue_batch()
            if not claimed:
                await asyncio.sleep(self.config.poll_interval_seconds)
                continue
            for task in claimed:
                t = asyncio.create_task(self._run_one(task))
                self._inflight.add(t)
                t.add_done_callback(self._inflight.discard)

    async def _dequeue_batch(self) -> list[Task]:
        async with self.sessionmaker() as db:
            result = await db.execute(
                text(DEQUEUE),
                {
                    "owner": self.config.worker_id,
                    "lease_seconds": self.config.lease_seconds,
                    "queue": self.config.queue,
                    "limit": self.config.batch_size,
                },
            )
            rows = result.fetchall()
            await db.commit()
            return [_row_to_task(r) for r in rows]

    async def _run_one(self, task: Task) -> None:
        handler = self.handlers.get(task.task_type)
        if handler is None:
            log.error("worker.no_handler", extra={"task_type": task.task_type})
            await self._kill(task, "no handler registered", status=TaskStatus.DEAD)
            return

        try:
            await handler(task.payload)
        except PermanentTaskError as exc:
            await self._kill(task, str(exc), status=TaskStatus.FAILED)
        except TransientTaskError as exc:
            await self._retry_or_kill(task, str(exc))
        except Exception as exc:  # noqa: BLE001 — an unexpected handler bug is still transient
            log.exception("worker.handler_raised_unexpectedly", extra={"task_id": str(task.id)})
            await self._retry_or_kill(task, f"unexpected error: {exc}")
        else:
            await self._complete(task)

    async def _retry_or_kill(self, task: Task, error: str) -> None:
        policy = self.config.retry_policy
        if policy.exhausted(task.attempt):
            await self._kill(task, error, status=TaskStatus.DEAD)
            return
        delay = policy.delay_for(task.attempt)
        async with self.sessionmaker() as db:
            await db.execute(
                text(RETRY_LATER),
                {"id": str(task.id), "owner": self.config.worker_id,
                 "delay_seconds": delay, "error": error},
            )
            await db.commit()

    async def _complete(self, task: Task) -> None:
        async with self.sessionmaker() as db:
            await db.execute(text(COMPLETE), {"id": str(task.id), "owner": self.config.worker_id})
            await db.commit()

    async def _kill(self, task: Task, error: str, *, status: TaskStatus) -> None:
        async with self.sessionmaker() as db:
            await db.execute(
                text(KILL),
                {"id": str(task.id), "owner": self.config.worker_id,
                 "status": status.value, "error": error},
            )
            await db.commit()

    async def heartbeat(self, task_id: str) -> bool:
        """Called by a long-running handler to extend its own lease. Returns
        False if the lease was already reaped out from under it — the handler
        should stop work immediately in that case, since another worker may
        already be re-running the same task."""
        async with self.sessionmaker() as db:
            result = await db.execute(
                text(HEARTBEAT),
                {
                    "id": task_id,
                    "owner": self.config.worker_id,
                    "lease_seconds": self.config.lease_seconds,
                },
            )
            row = result.fetchone()
            await db.commit()
            return row is not None

    # ── reaper ───────────────────────────────────────────────────────────

    async def _reap_loop(self) -> None:
        """Independent of the dispatch loop on purpose — a wedged dispatcher
        must not stop leases from expiring, or a genuinely dead worker's tasks
        would never be recovered."""
        try:
            while not self._stopping.is_set():
                await self._reap_once()
                await asyncio.sleep(self.config.reap_interval_seconds)
        except asyncio.CancelledError:
            pass

    async def _reap_once(self) -> int:
        async with self.sessionmaker() as db:
            result = await db.execute(text(REAP_EXPIRED))
            reaped = result.fetchall()
            await db.commit()
        if reaped:
            log.warning(
                "worker.reaped",
                extra={"n": len(reaped), "ids": [str(r.id) for r in reaped]},
            )
        return len(reaped)

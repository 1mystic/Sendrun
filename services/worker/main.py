"""The worker entrypoint: registers task handlers and runs the poll loop.

Run with: uv run python -m services.worker.main
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from packages.durable.worker import Worker, WorkerConfig
from packages.shared.config import get_settings
from packages.shared.db import get_sessionmaker
from packages.shared.job_store import SQLAlchemyJobStore
from services.worker.tasks.send import send_email_task

log = logging.getLogger("sendrun.worker")


def get_provider():
    """Mirrors the pattern in packages/shared/providers/base.py: the provider
    is chosen once from settings, and every caller is written against the
    EmailProvider protocol so swapping fake -> resend touches nothing else."""
    settings = get_settings()
    if settings.email_provider == "fake":
        from packages.shared.providers.fake import ChaosConfig, FakeEmailProvider

        chaos = (
            ChaosConfig(seed=settings.chaos_seed) if settings.chaos_enabled else ChaosConfig.quiet()
        )
        return FakeEmailProvider(chaos, secret=settings.fake_webhook_secret)
    raise NotImplementedError(
        f"EMAIL_PROVIDER={settings.email_provider!r} is not wired yet — only 'fake' is implemented"
    )


async def handle_send_email(payload: dict[str, Any]) -> None:
    """Bridges the generic durable-task dispatch to send_email_task. Any
    provider error is re-raised as the matching PermanentTaskError /
    TransientTaskError — send_email_task already does this internally, so
    this handler mainly exists to construct the per-call JobStore against a
    fresh session, matching the one-session-per-unit-of-work pattern used
    everywhere else in the app."""
    settings = get_settings()
    sessionmaker = get_sessionmaker()
    provider = get_provider()

    async with sessionmaker() as db:
        store = SQLAlchemyJobStore(db)
        try:
            await send_email_task(
                payload, store=store, provider=provider,
                worker_id=settings.worker_id, from_addr=settings.from_address,
                attempt=1,  # the durable task's own `attempt` governs retry count, not this
            )
        finally:
            await db.commit()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()

    worker = Worker(
        sessionmaker=get_sessionmaker(),
        handlers={"send_email": handle_send_email},
        config=WorkerConfig(
            worker_id=settings.worker_id,
            lease_seconds=settings.lease_seconds,
            poll_interval_seconds=settings.poll_interval_seconds,
        ),
    )
    log.info("worker.starting", extra={"worker_id": settings.worker_id})
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())

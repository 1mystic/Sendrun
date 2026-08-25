"""Forward orphan resolution: periodically re-attempt the join for events
whose email_job_id is still NULL because they arrived before the send was
recorded.

This is the backstop, not the primary path — SQLAlchemyJobStore.mark_sent
already adopts waiting orphans the instant it learns the message id, which
resolves the common case in milliseconds. The sweeper exists for the case
where that adoption was itself missed (e.g. mark_sent ran before the event was
inserted at all — a race the backward adoption cannot close because the event
didn't exist yet). Run as a periodic task, exactly like the durable engine's
reaper (packages/durable/worker.py) — same shape, same reasoning: recovery
must not depend on any one code path succeeding.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from packages.shared.models import ProviderEvent

from .processor import process_one_event

log = logging.getLogger("sendrun.webhooks")

# After this long unresolved, an event is almost certainly not ours — a
# webhook from a different environment sharing the endpoint, or a message id
# we will simply never see. Mark it processed (with attempts already showing
# it was retried) rather than sweeping it forever.
ORPHAN_GIVE_UP_AFTER = timedelta(hours=24)


async def sweep_once(db: AsyncSession) -> tuple[int, int]:
    """Returns (resolved, still_orphaned)."""
    result = await db.execute(
        select(ProviderEvent).where(
            ProviderEvent.email_job_id.is_(None), ProviderEvent.processed_at.is_(None)
        )
    )
    orphans = result.scalars().all()

    resolved = 0
    for event in orphans:
        if datetime.now(UTC) - event.received_at.replace(tzinfo=UTC) > ORPHAN_GIVE_UP_AFTER:
            event.processed_at = datetime.now(UTC)
            log.warning(
                "webhook.orphan_abandoned",
                extra={"event_id": str(event.id), "provider_message_id": event.provider_message_id},
            )
            continue
        if await process_one_event(db, str(event.id)):
            resolved += 1

    await db.commit()
    return resolved, len(orphans) - resolved


async def sweep_loop(
    sessionmaker: async_sessionmaker[AsyncSession], *, interval_seconds: float = 30.0
) -> None:
    """Run forever until cancelled. Same independent-timer shape as the
    durable engine's reaper — see packages/durable/worker.py."""
    while True:
        try:
            async with sessionmaker() as db:
                resolved, remaining = await sweep_once(db)
            if resolved:
                log.info("webhook.sweep", extra={"resolved": resolved, "remaining": remaining})
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("webhook.sweep_failed")
        await asyncio.sleep(interval_seconds)

"""Applies one provider_events row to the EmailJob it belongs to.

Two things make this correct under duplicate and out-of-order delivery:

  1. **Orphan resolution.** If no EmailJob has this provider_message_id yet
     (the send hasn't been recorded — see the "webhook before send ack" chaos
     knob), the event stays with email_job_id=NULL and processed_at=NULL. The
     sweeper (sweeper.py) retries the join later; SQLAlchemyJobStore.mark_sent
     also adopts waiting orphans the moment it learns the message id, which
     resolves the common case in milliseconds without waiting for the sweeper
     at all.

  2. **Precedence, not sequence.** `sent`, `delivered`, `bounced`, and
     `complained` are applied only if they OUTRANK what is already recorded
     (transitions.DELIVERY_RANK). A duplicate or a late `sent` after a
     `delivered` is a correctly-discarded no-op, not a bug.

`opened` and `clicked` are handled separately — they are not part of the
delivery-status axis at all (CLAUDE.md invariant 3) and always apply as an
insert-plus-counter-increment, never a status transition.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.models import EmailEngagement, EmailJob, ProviderEvent
from packages.shared.transitions import DELIVERY_RANK, DeliveryStatus

log = logging.getLogger("sendrun.webhooks")

_DELIVERY_EVENT_TYPES = {"sent", "delivered", "deferred", "bounced", "complained"}
_ENGAGEMENT_EVENT_TYPES = {"opened", "clicked"}


async def process_one_event(db: AsyncSession, event_id: str) -> bool:
    """Returns True if the event was applied to a job, False if it is still
    an orphan (and should be retried by the sweeper)."""
    event = await db.get(ProviderEvent, UUID(event_id))
    if event is None:
        return False
    if event.processed_at is not None:
        return True  # already handled — a duplicate call, not an error

    job = await _find_job_for_event(db, event)
    if job is None:
        # Forward resolution: leave email_job_id NULL, do not mark processed.
        # The sweeper's next pass re-attempts this join.
        event.attempts += 1
        return False

    event.email_job_id = job.id

    if event.event_type in _ENGAGEMENT_EVENT_TYPES:
        await _apply_engagement(db, job, event)
    elif event.event_type in _DELIVERY_EVENT_TYPES:
        await _apply_delivery_status(db, job, event)
    else:
        log.warning("webhook.unknown_event_type", extra={"type": event.event_type})

    event.processed_at = datetime.now(UTC)
    return True


async def _find_job_for_event(db: AsyncSession, event: ProviderEvent) -> EmailJob | None:
    result = await db.execute(
        select(EmailJob).where(EmailJob.provider_message_id == event.provider_message_id)
    )
    return result.scalar_one_or_none()


async def _apply_delivery_status(db: AsyncSession, job: EmailJob, event: ProviderEvent) -> None:
    if event.event_type == "sent":
        # A `sent` webhook confirms what the send activity already recorded.
        # It never becomes the delivery_status itself — delivery_status stays
        # NULL until an actual delivery outcome (delivered/bounced/etc) arrives.
        return

    new_status = DeliveryStatus(event.event_type)
    current = DeliveryStatus(job.delivery_status) if job.delivery_status else None

    if DELIVERY_RANK[new_status] <= DELIVERY_RANK[current]:
        # Discarded as a no-op: this event does not outrank what is recorded.
        # This is the case that makes a duplicate or late-arriving `sent`
        # after a `delivered`, or a replayed `delivered`, harmless.
        return

    await db.execute(
        update(EmailJob)
        .where(EmailJob.id == job.id)
        .values(delivery_status=new_status.value)
    )


async def _apply_engagement(db: AsyncSession, job: EmailJob, event: ProviderEvent) -> None:
    """opened/clicked never touch delivery_status. A counter increment plus an
    engagement row — always applied, never rank-checked, since an email can
    legitimately be opened forty times."""
    db.add(EmailEngagement(
        email_job_id=job.id, kind=event.event_type, occurred_at=event.occurred_at,
        url=event.raw.get("data", {}).get("url") if isinstance(event.raw, dict) else None,
    ))

    if event.event_type == "opened":
        values = {"open_count": EmailJob.open_count + 1}
        if job.first_opened_at is None:
            values["first_opened_at"] = event.occurred_at
    else:
        values = {"click_count": EmailJob.click_count + 1}
        if job.first_clicked_at is None:
            values["first_clicked_at"] = event.occurred_at

    await db.execute(update(EmailJob).where(EmailJob.id == job.id).values(**values))

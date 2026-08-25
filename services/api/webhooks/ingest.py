"""Webhook ingestion. The four-step sequence is not optional:

    verify signature (over the RAW body) -> insert (dedup on provider_event_id)
    -> return 200 -> process asynchronously

Never process synchronously in the handler. Resend retries on any non-2xx, so
slow processing here directly causes duplicate deliveries and a thundering
herd — the handler's only job is to durably record the event and get out.

The processing step (join to EmailJob by provider_message_id, apply the
precedence-rank delivery-status update) happens in processor.py, invoked here
via a background task for the fake provider's low-volume dev use. In
production this would be a separate consumer polling `provider_events WHERE
processed_at IS NULL`, but for a fake provider running inside the same process
a fire-and-forget asyncio task is a faithful enough stand-in — it never blocks
the response, which is the property this module actually exists to guarantee.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.config import get_settings
from packages.shared.db import get_sessionmaker

from ..deps import get_db
from .processor import process_one_event

log = logging.getLogger("sendrun.webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Dedup on provider_event_id. Inserting the raw payload as JSON text keeps this
# portable across SQLite (tests) and Postgres (prod) — unlike queue.py's
# ENQUEUE, this table's payload column is plain JSONVariant via the ORM
# metadata, not a raw CAST, so no dialect-specific SQL is needed here.
_INSERT_EVENT = """
INSERT INTO provider_events
    (id, provider_event_id, provider_message_id, event_type, occurred_at, raw)
VALUES (:id, :provider_event_id, :provider_message_id, :event_type, :occurred_at, :raw)
ON CONFLICT (provider_event_id) DO NOTHING
RETURNING id;
"""


@router.post("/fake", status_code=status.HTTP_200_OK)
async def fake_provider_webhook(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Receives events emitted by FakeEmailProvider. A real Resend endpoint
    would live alongside this at /api/webhooks/resend with Resend's own
    Svix-based signature scheme; the sequence below is identical either way.
    """
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    from packages.shared.providers.fake import FakeEmailProvider

    provider = FakeEmailProvider(secret=get_settings().fake_webhook_secret)

    # ── 1. Verify, over the RAW body, before anything else ──────────────
    if not provider.verify_webhook(headers, body):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid webhook signature")

    events = provider.parse_webhook(body)

    # ── 2. Insert, deduplicated ──────────────────────────────────────────
    import json as jsonlib

    inserted_ids: list[str] = []
    for event in events:
        result = await db.execute(
            text(_INSERT_EVENT),
            {
                "id": str(uuid4()),
                "provider_event_id": event.provider_event_id,
                "provider_message_id": event.provider_message_id,
                "event_type": event.event_type,
                "occurred_at": event.occurred_at,
                "raw": jsonlib.dumps(event.raw),
            },
        )
        row = result.fetchone()
        if row is not None:
            inserted_ids.append(str(row.id))
    await db.commit()

    # ── 3. Return 200 immediately ────────────────────────────────────────
    # inserted_ids is computed before scheduling processing so the response
    # does not wait on step 4 at all.

    # ── 4. Process asynchronously, never inline ──────────────────────────
    if inserted_ids:
        asyncio.create_task(_process_events(inserted_ids))

    return {"received": str(len(events)), "new": str(len(inserted_ids))}


async def _process_events(event_ids: list[str]) -> None:
    """Runs after the response has already gone out. Each event gets its own
    session so one failure cannot roll back another's progress."""
    sessionmaker = get_sessionmaker()
    for event_id in event_ids:
        try:
            async with sessionmaker() as db:
                await process_one_event(db, event_id)
                await db.commit()
        except Exception:
            log.exception("webhook.process_failed", extra={"event_id": event_id})
            # Left with processed_at=NULL; the sweeper (Phase 4, sweeper.py)
            # picks it up on its next pass. Never silently drop an event.

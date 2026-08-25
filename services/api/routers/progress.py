"""SSE progress stream: the dashboard's live-updating campaign view.

Polls Postgres every second and pushes deltas — deliberately NOT a WebSocket
(no bidirectional need here) and NOT client-side polling (chatty, and every
open dashboard would duplicate the query load). See PLAN.md's rationale.

Reads the same aggregate query as GET /progress (campaigns.py) — this endpoint
is that same read, repeated on a timer and streamed, not a second source of
truth for campaign state.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.db import get_sessionmaker
from packages.shared.models import User

from ..deps import get_db, require_membership, require_user
from .campaigns import get_progress

router = APIRouter(prefix="/api/organizations/{org_id}/campaigns", tags=["progress"])

POLL_INTERVAL_SECONDS = 1.0
# A campaign that has been terminal for this long stops streaming — the
# client's EventSource should close, not poll a finished campaign forever.
STOP_STREAMING_AFTER_TERMINAL_TICKS = 5


@router.get("/{campaign_id}/progress/stream")
async def stream_progress(
    org_id: UUID,
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> StreamingResponse:
    # Auth is checked once, up front, on the request's own session — the
    # generator below opens its OWN sessions per tick rather than holding this
    # one across the whole stream's lifetime, since an SSE connection can be
    # open for minutes and a single long-lived session would pin a connection
    # from the pool for that entire time.
    await require_membership(org_id, db, user)

    async def event_stream() -> AsyncIterator[str]:
        sessionmaker = get_sessionmaker()
        terminal_ticks = 0

        while terminal_ticks < STOP_STREAMING_AFTER_TERMINAL_TICKS:
            async with sessionmaker() as tick_db:
                snapshot = await get_progress(org_id, campaign_id, tick_db, user)

            yield f"data: {json.dumps(snapshot.model_dump())}\n\n"

            if snapshot.status in ("completed", "cancelled", "failed"):
                terminal_ticks += 1
            else:
                terminal_ticks = 0

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx response buffering, if fronted by one
        },
    )

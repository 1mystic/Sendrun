"""Thin execution layer over packages/durable/queue.py's SQL constants.

queue.py deliberately holds only SQL text and dataclasses — it has no SQLAlchemy
dependency, so the durable engine's core stays testable and reviewable without
an ORM in the picture. This module is where that SQL actually gets run, using
raw `text()` execution against whatever AsyncSession the caller has open, so an
enqueue can share a transaction with the EmailJob insert that produced it (see
campaigns.launch_campaign).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.durable.queue import ENQUEUE, utcnow


async def enqueue_task(
    db: AsyncSession,
    *,
    queue: str,
    task_type: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
    max_attempts: int = 5,
    run_after: datetime | None = None,
    parent_id: UUID | None = None,
) -> UUID:
    """Insert one task row. ON CONFLICT (idempotency_key) DO NOTHING makes this
    safe to call twice for the same logical task — the janitor sweep in
    packages/durable/worker.py relies on that to re-drive an interrupted
    launch without risking a duplicate enqueue.
    """
    task_id = uuid4()
    await db.execute(
        text(ENQUEUE),
        {
            "id": str(task_id),
            "queue": queue,
            "task_type": task_type,
            "payload": json.dumps(payload),
            "idempotency_key": idempotency_key,
            "run_after": run_after or utcnow(),
            "max_attempts": max_attempts,
            "parent_id": str(parent_id) if parent_id else None,
        },
    )
    return task_id

"""Read-only inspector over the durable engine's own `tasks` table
(packages/durable/queue.py) — dead-lettered and in-flight/failed tasks,
scoped to one org.

`tasks` carries no org_id column by design (the durable engine is generic,
not Sendrun-specific) — payload carries email_job_id/campaign_id, so tenant
isolation here is a join through EmailJob -> Campaign -> org_id rather than a
direct WHERE. No requeue action: the payload's own retry/backoff machinery
already owns that, and a manual requeue button would bypass the very
idempotency guarantees the durable engine exists to provide.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db, require_membership

router = APIRouter(prefix="/api/organizations/{org_id}/jobs", tags=["jobs"])


class TaskOut(BaseModel):
    id: str
    queue: str
    task_type: str
    status: str
    attempt: int
    max_attempts: int
    last_error: str | None
    email_job_id: str | None
    campaign_id: str | None
    created_at: str
    updated_at: str


# Joins through EmailJob/Campaign so a task row is only visible if its
# email_job_id resolves to a job under a campaign in this org — the payload's
# own campaign_id is never trusted directly, since it is caller-supplied at
# enqueue time, not authorization data.
_SELECT_TASKS = """
SELECT t.id, t.queue, t.task_type, t.status, t.attempt, t.max_attempts, t.last_error,
       t.payload->>'email_job_id' AS email_job_id, t.payload->>'campaign_id' AS campaign_id,
       t.created_at, t.updated_at
FROM tasks t
JOIN email_jobs ej ON ej.id = (t.payload->>'email_job_id')::uuid
JOIN campaigns c ON c.id = ej.campaign_id
WHERE c.org_id = :org_id AND t.status = ANY(:statuses)
ORDER BY t.updated_at DESC
LIMIT :limit
"""


async def _fetch(db: AsyncSession, org_id: UUID, statuses: list[str], limit: int) -> list[TaskOut]:
    # The `tasks` table itself is Postgres-only by design (JSONB, see
    # packages/durable/queue.py's CREATE_TASKS_TABLE) — it is never created on
    # SQLite, which is what local dev / tests run against. Returning an empty
    # inspector result there is honest (there is truly nothing to show against
    # a store that doesn't exist) and avoids a 500 that a browser reports as a
    # misleading CORS failure.
    if db.bind.dialect.name != "postgresql":
        return []

    rows = (
        await db.execute(
            text(_SELECT_TASKS), {"org_id": str(org_id), "statuses": statuses, "limit": limit}
        )
    ).all()
    return [
        TaskOut(
            id=str(r.id), queue=r.queue, task_type=r.task_type, status=r.status,
            attempt=r.attempt, max_attempts=r.max_attempts, last_error=r.last_error,
            email_job_id=r.email_job_id, campaign_id=r.campaign_id,
            created_at=r.created_at.isoformat(), updated_at=r.updated_at.isoformat(),
        )
        for r in rows
    ]


@router.get("/dead-letter", response_model=list[TaskOut])
async def list_dead_letter(
    org_id: UUID,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_membership),
) -> list[TaskOut]:
    return await _fetch(db, org_id, ["dead"], min(limit, 500))


@router.get("/in-flight", response_model=list[TaskOut])
async def list_in_flight(
    org_id: UUID,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_membership),
) -> list[TaskOut]:
    """'in-flight' == leased (currently claimed by a worker) or pending with a
    nonzero attempt count (already retried at least once)."""
    return await _fetch(db, org_id, ["leased", "failed"], min(limit, 500))

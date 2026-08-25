"""Append-only audit trail. See models.AuditLog for why this exists — it is the
paper trail behind invariant 8: every AI-proposed action traces to the human who
approved it."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog


async def record(
    db: AsyncSession,
    *,
    org_id: UUID,
    action: str,
    actor_user_id: UUID | None = None,
    actor_kind: str = "user",
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        org_id=org_id,
        actor_user_id=actor_user_id,
        actor_kind=actor_kind,
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata_=metadata or {},
    )
    db.add(entry)
    await db.flush()
    return entry

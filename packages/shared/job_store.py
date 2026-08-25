"""The real JobStore: send_email_task's DB operations against the actual
EmailJob table, via SQLAlchemy. This is the production implementation of the
Protocol in services/worker/tasks/send.py — tests use InMemoryJobStore instead,
but the state-machine guards here must mirror it exactly, or a passing test
suite would prove nothing about production behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.models import EmailJob, ProviderEvent
from services.worker.tasks.send import ClaimedJob


class SQLAlchemyJobStore:
    """Implements the JobStore protocol from services/worker/tasks/send.py
    against real EmailJob rows. One instance per request/task — it holds no
    state of its own beyond the AsyncSession it's given.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def claim(self, job_id: UUID, worker: str, attempt: int) -> ClaimedJob | None:
        # The guard, mirroring CLAIM_SQL's predecessor set exactly: queued,
        # sending (a self-reclaim after a crash), or failed_transient (a retry).
        # A row in any other state matches nothing and this returns None.
        result = await self.db.execute(
            update(EmailJob)
            .where(
                EmailJob.id == job_id,
                EmailJob.send_status.in_(["queued", "sending", "failed_transient"]),
            )
            .values(
                send_status="sending", attempt=attempt,
                claimed_by=worker, claimed_at=datetime.now(UTC),
            )
            .returning(EmailJob)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _to_claimed(row)

    async def mark_sent(self, job_id: UUID, message_id: str, at: datetime) -> int:
        # Record the send, then adopt any orphan webhook events that arrived
        # before we knew the message id — the backward half of the orphan-event
        # fix (see CLAUDE.md invariant 7 / packages/shared/models.ProviderEvent).
        result = await self.db.execute(
            update(EmailJob)
            .where(EmailJob.id == job_id, EmailJob.send_status == "sending")
            .values(send_status="sent", provider_message_id=message_id, sent_at=at)
            .returning(EmailJob.id)
        )
        updated = result.scalar_one_or_none()
        if updated is None:
            return 0

        adopted = await self.db.execute(
            update(ProviderEvent)
            .where(
                ProviderEvent.provider_message_id == message_id,
                ProviderEvent.email_job_id.is_(None),
            )
            .values(email_job_id=job_id)
            .returning(ProviderEvent.id)
        )
        return len(adopted.fetchall())

    async def mark_transient(self, job_id: UUID, error: str) -> None:
        await self.db.execute(
            update(EmailJob)
            .where(EmailJob.id == job_id, EmailJob.send_status == "sending")
            .values(send_status="failed_transient", last_error=error)
        )

    async def mark_permanent(self, job_id: UUID, error: str, reason: str) -> None:
        await self.db.execute(
            update(EmailJob)
            .where(EmailJob.id == job_id, EmailJob.send_status == "sending")
            .values(send_status="failed_permanent", last_error=f"{reason}: {error}")
        )

    async def get(self, job_id: UUID) -> ClaimedJob | None:
        row = await self.db.get(EmailJob, job_id)
        return _to_claimed(row) if row is not None else None


def _to_claimed(row: EmailJob) -> ClaimedJob:
    return ClaimedJob(
        id=row.id,
        send_status=row.send_status,  # type: ignore[arg-type]
        provider_message_id=row.provider_message_id,
        attempt=row.attempt,
        to_addr=row.to_addr,
        subject=row.subject,
        html=row.html_body,
        text=row.text_body,
    )

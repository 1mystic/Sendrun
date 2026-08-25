"""Campaign lifecycle: create, launch, cancel, and read progress.

Launch is the one place in the whole system where care about ordering matters
most. See _launch_campaign for the exact sequence and why: it is the outbox
pattern the plan calls for, closed by a janitor sweep rather than a message
broker.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.audit import record
from packages.shared.authz import require_capability
from packages.shared.enqueue import enqueue_task
from packages.shared.models import Campaign, Contact, ContactTag, EmailJob, EmailTemplate, Tag, User
from packages.shared.render import TemplateValidationError, render_for_contact
from packages.shared.transitions import CampaignStatus, SendStatus

from ..deps import get_db, require_membership, require_user
from .contacts import SmartFilter
from .templates import _latest_version

router = APIRouter(prefix="/api/organizations/{org_id}/campaigns", tags=["campaigns"])

BATCH_SIZE = 500  # see PLAN.md §1 — batched fan-out keeps any single task small


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    template_id: UUID
    event_id: UUID | None = None
    recipients: SmartFilter
    send_rate_per_second: int = Field(default=8, ge=1, le=50)


class CampaignOut(BaseModel):
    id: str
    name: str
    status: str
    template_id: str
    template_version: int
    recipient_count: int | None = None


class ProgressOut(BaseModel):
    """Read from Postgres, never from the durable engine — the engine holds
    only what to do next; Postgres holds what happened. See CLAUDE.md
    invariant 6."""

    campaign_id: str
    status: str
    total: int
    delivered: int
    sending: int
    retrying: int
    failed_permanent: int
    bounced: int
    complained: int
    attempted: int


async def _resolve_contact_ids(db: AsyncSession, org_id: UUID, filt: SmartFilter) -> list[UUID]:
    from sqlalchemy import and_, or_

    stmt = select(Contact.id).where(Contact.org_id == org_id)
    if filt.tags:
        stmt = stmt.join(ContactTag, ContactTag.contact_id == Contact.id).join(
            Tag, and_(Tag.id == ContactTag.tag_id, Tag.name.in_(filt.tags))
        )
    if filt.exclude_suppressed:
        stmt = stmt.where(Contact.suppressed.is_(False))
    if filt.search:
        like = f"%{filt.search.lower()}%"
        stmt = stmt.where(or_(Contact.email.ilike(like), Contact.name.ilike(like)))
    result = await db.execute(stmt.distinct())
    return [cid for (cid,) in result.all()]


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    org_id: UUID,
    body: CampaignIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> CampaignOut:
    membership = await require_membership(org_id, db, user)
    require_capability(membership, "create_campaign")

    template = await db.get(EmailTemplate, body.template_id)
    if template is None or template.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found")

    campaign = Campaign(
        org_id=org_id, name=body.name.strip(), event_id=body.event_id,
        template_id=template.id, template_version=template.current_version,
        status=CampaignStatus.DRAFT.value, send_rate_per_second=body.send_rate_per_second,
        created_by=user.id,
    )
    db.add(campaign)
    await db.flush()

    recipient_ids = await _resolve_contact_ids(db, org_id, body.recipients)

    await record(db, org_id=org_id, actor_user_id=user.id, action="campaign.created",
                 target_type="campaign", target_id=str(campaign.id),
                 metadata={"recipient_count": len(recipient_ids)})
    await db.commit()
    return CampaignOut(
        id=str(campaign.id), name=campaign.name, status=campaign.status,
        template_id=str(template.id), template_version=campaign.template_version,
        recipient_count=len(recipient_ids),
    )


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    org_id: UUID, campaign_id: UUID,
    db: AsyncSession = Depends(get_db), user: User = Depends(require_user),
) -> CampaignOut:
    await require_membership(org_id, db, user)
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None or campaign.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    return CampaignOut(
        id=str(campaign.id), name=campaign.name, status=campaign.status,
        template_id=str(campaign.template_id), template_version=campaign.template_version,
    )


@router.post("/{campaign_id}/launch", response_model=CampaignOut)
async def launch_campaign(
    org_id: UUID, campaign_id: UUID,
    body: CampaignIn,
    db: AsyncSession = Depends(get_db), user: User = Depends(require_user),
) -> CampaignOut:
    """Fan out to one EmailJob + one durable task per recipient.

    The recipient list is RE-RESOLVED here from the SmartFilter, never trusted
    from what create_campaign returned — a contact who unsubscribed between
    preview and launch must not receive a send (packages/api/routers/contacts.py
    documents the same principle for resolve_recipients).

    Sequence, matching PLAN.md's outbox-pattern design:
      1. Campaign -> LAUNCHING, EmailJob rows inserted, all in one transaction.
      2. COMMIT.
      3. Enqueue one durable task per EmailJob, each carrying the job's own id
         as its idempotency key (== the future email idempotency key).
      4. Campaign -> RUNNING.
    If the process dies between (2) and (4), the campaign is stuck in LAUNCHING
    with real EmailJob rows already committed but no tasks enqueued — a
    janitor sweep (Phase 3, packages/durable/worker.py) finds these and
    re-drives them. It is safe to re-drive because task idempotency_key makes
    a duplicate enqueue of the same job a no-op (see queue.ENQUEUE's
    ON CONFLICT DO NOTHING).
    """
    membership = await require_membership(org_id, db, user)
    require_capability(membership, "launch_campaign")

    campaign = await db.get(Campaign, campaign_id)
    if campaign is None or campaign.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    if campaign.status not in (CampaignStatus.DRAFT.value, CampaignStatus.SCHEDULED.value):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"campaign is '{campaign.status}', not draft/scheduled — cannot launch",
        )

    template_version = await _latest_version(db, campaign.template_id, campaign.template_version)
    contact_ids = await _resolve_contact_ids(db, org_id, body.recipients)
    if not contact_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "no recipients resolved")

    contacts = (
        await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))
    ).scalars().all()

    # ── Step 1: LAUNCHING + EmailJob rows, one transaction ──────────────
    campaign.status = CampaignStatus.LAUNCHING.value
    job_ids: list[UUID] = []
    for contact in contacts:
        first_name = contact.name.split(" ")[0] if contact.name else ""
        try:
            rendered = render_for_contact(
                subject=template_version.subject, html_body=template_version.html_body,
                text_body=template_version.text_body,
                declared_variables=template_version.variables,
                contact_fields={**contact.fields, "first_name": first_name},
            )
        except TemplateValidationError:
            # A template that fails to render for this one contact is skipped
            # rather than aborting the whole batch.
            continue

        job = EmailJob(
            campaign_id=campaign.id, contact_id=contact.id, to_addr=contact.email,
            subject=rendered.subject, html_body=rendered.html_body, text_body=rendered.text_body,
            send_status=SendStatus.QUEUED.value,
        )
        db.add(job)
        await db.flush()
        job_ids.append(job.id)

    await db.commit()  # Step 2: COMMIT — job rows are durable even if the process dies next

    # ── Step 3: enqueue one durable task per job ─────────────────────────
    for job_id in job_ids:
        await enqueue_task(
            db, queue="sendrun-send", task_type="send_email",
            payload={"email_job_id": str(job_id), "campaign_id": str(campaign.id)},
            idempotency_key=f"enqueue:{job_id}",
            max_attempts=5,
        )
    await db.commit()

    # ── Step 4: RUNNING ───────────────────────────────────────────────────
    campaign.status = CampaignStatus.RUNNING.value
    campaign.started_at = datetime.now(UTC)
    await record(db, org_id=org_id, actor_user_id=user.id, action="campaign.launched",
                 target_type="campaign", target_id=str(campaign.id),
                 metadata={"job_count": len(job_ids)})
    await db.commit()

    return CampaignOut(
        id=str(campaign.id), name=campaign.name, status=campaign.status,
        template_id=str(campaign.template_id), template_version=campaign.template_version,
        recipient_count=len(job_ids),
    )


@router.post("/{campaign_id}/cancel", response_model=CampaignOut)
async def cancel_campaign(
    org_id: UUID, campaign_id: UUID,
    db: AsyncSession = Depends(get_db), user: User = Depends(require_user),
) -> CampaignOut:
    """Cancels every job that has not started. A job already `sending` or
    `sent` cannot be recalled — see CLAUDE.md invariant 5 and the durability
    guarantee card in the UI."""
    membership = await require_membership(org_id, db, user)
    require_capability(membership, "launch_campaign")

    campaign = await db.get(Campaign, campaign_id)
    if campaign is None or campaign.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    terminal = (
        CampaignStatus.COMPLETED.value,
        CampaignStatus.CANCELLED.value,
        CampaignStatus.FAILED.value,
    )
    if campaign.status in terminal:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"campaign already terminal: {campaign.status}"
        )

    from sqlalchemy import update

    await db.execute(
        update(EmailJob)
        .where(EmailJob.campaign_id == campaign_id, EmailJob.send_status == SendStatus.QUEUED.value)
        .values(send_status=SendStatus.CANCELLED.value)
    )
    campaign.status = CampaignStatus.CANCELLED.value
    await record(db, org_id=org_id, actor_user_id=user.id, action="campaign.cancelled",
                 target_type="campaign", target_id=str(campaign.id))
    await db.commit()
    return CampaignOut(
        id=str(campaign.id), name=campaign.name, status=campaign.status,
        template_id=str(campaign.template_id), template_version=campaign.template_version,
    )


@router.get("/{campaign_id}/progress", response_model=ProgressOut)
async def get_progress(
    org_id: UUID, campaign_id: UUID,
    db: AsyncSession = Depends(get_db), user: User = Depends(require_user),
) -> ProgressOut:
    """The dashboard's data source. A single aggregate query over Postgres —
    never a query against the durable engine's task table. See CLAUDE.md
    invariant 6."""
    await require_membership(org_id, db, user)
    campaign = await db.get(Campaign, campaign_id)
    if campaign is None or campaign.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")

    result = await db.execute(
        select(EmailJob.send_status, EmailJob.delivery_status, func.count())
        .where(EmailJob.campaign_id == campaign_id)
        .group_by(EmailJob.send_status, EmailJob.delivery_status)
    )
    counts = {(s, d): n for s, d, n in result.all()}

    total = sum(counts.values())
    delivered = sum(n for (s, d), n in counts.items() if d == "delivered")
    bounced = sum(n for (s, d), n in counts.items() if d == "bounced")
    complained = sum(n for (s, d), n in counts.items() if d == "complained")
    sending = sum(n for (s, d), n in counts.items() if s == "sending")
    retrying = sum(n for (s, d), n in counts.items() if s == "failed_transient")
    failed_permanent = sum(n for (s, d), n in counts.items() if s == "failed_permanent")
    attempted = sum(
        n for (s, d), n in counts.items()
        if s in ("sent", "failed_permanent", "cancelled", "skipped")
    )

    return ProgressOut(
        campaign_id=str(campaign_id), status=campaign.status, total=total,
        delivered=delivered, sending=sending, retrying=retrying,
        failed_permanent=failed_permanent, bounced=bounced, complained=complained,
        attempted=attempted,
    )

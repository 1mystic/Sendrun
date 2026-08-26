"""Agent endpoints — QA review and campaign analytics explanation, the two
agents built fully real (see packages/shared/agents/ for why the other three
stay documented extension points rather than production endpoints).

Every response here is an AgentProposal (packages/shared/agents/base.py) —
this router never writes to the database. A proposal becomes an action only
if a human later calls a DIFFERENT, already-existing endpoint to actually
apply it (e.g. "Set fallback" on a preflight finding already goes through
the normal template-edit endpoint, not through this agent layer) — matching
CLAUDE.md invariant 8.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.agents.analytics_agent import CampaignStats, explain_campaign
from packages.shared.agents.qa_agent import review_campaign
from packages.shared.audit import record
from packages.shared.models import Campaign, Contact, EmailJob, EmailTemplate, User
from packages.shared.providers.llm_factory import get_llm_provider

from ..deps import get_db, require_membership, require_user
from .templates import _latest_version

router = APIRouter(prefix="/api/organizations/{org_id}", tags=["agents"])


class ProposalOut(BaseModel):
    id: str
    agent_name: str
    summary: str
    detail: str
    action: dict | None
    status: str
    model_used: str


def _proposal_out(p) -> ProposalOut:
    return ProposalOut(
        id=str(p.id), agent_name=p.agent_name, summary=p.summary, detail=p.detail,
        action=p.action, status=p.status, model_used=p.model_used,
    )


class QAReviewRequest(BaseModel):
    template_id: UUID
    example_contact_id: UUID | None = None


@router.post("/templates/{template_id}/qa-review", response_model=ProposalOut)
async def qa_review_template(
    org_id: UUID,
    template_id: UUID,
    body: QAReviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> ProposalOut:
    """LLM-backed QA review, layered on top of the deterministic preflight
    checks (Phase 5) — never replacing them. See qa_agent.py's module
    docstring."""
    await require_membership(org_id, db, user)

    template = await db.get(EmailTemplate, template_id)
    if template is None or template.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found")
    version = await _latest_version(db, template.id, template.current_version)

    example_fields: dict[str, str] = {}
    if body.example_contact_id:
        contact = await db.get(Contact, body.example_contact_id)
        if contact is not None and contact.org_id == org_id:
            example_fields = {**contact.fields}
            if contact.name:
                example_fields.setdefault("first_name", contact.name.split(" ")[0])

    provider = get_llm_provider()
    _preflight, proposal = await review_campaign(
        provider, version, example_contact_fields=example_fields,
    )

    await record(
        db, org_id=org_id, actor_user_id=user.id, actor_kind="ai_agent",
        action="agent.qa_review_proposed", target_type="template",
        target_id=str(template_id), metadata={"proposal_id": str(proposal.id)},
    )
    await db.commit()
    return _proposal_out(proposal)


@router.post("/campaigns/{campaign_id}/analyze", response_model=ProposalOut)
async def analyze_campaign(
    org_id: UUID,
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> ProposalOut:
    """Explains a completed campaign's results against the org's recent
    history. Only aggregate EmailJob counts are ever sent to the LLM — see
    analytics_agent.py's CampaignStats, which has no field for a contact
    email or name."""
    await require_membership(org_id, db, user)

    campaign = await db.get(Campaign, campaign_id)
    if campaign is None or campaign.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")

    current_stats = await _campaign_stats(db, campaign)

    history_result = await db.execute(
        select(Campaign)
        .where(Campaign.org_id == org_id, Campaign.id != campaign_id,
               Campaign.status == "completed")
        .order_by(Campaign.completed_at.desc())
        .limit(5)
    )
    history = [await _campaign_stats(db, c) for c in history_result.scalars().all()]

    provider = get_llm_provider()
    proposal = await explain_campaign(provider, current_stats, history)

    await record(
        db, org_id=org_id, actor_user_id=user.id, actor_kind="ai_agent",
        action="agent.campaign_analysis_proposed", target_type="campaign",
        target_id=str(campaign_id), metadata={"proposal_id": str(proposal.id)},
    )
    await db.commit()
    return _proposal_out(proposal)


async def _campaign_stats(db: AsyncSession, campaign: Campaign) -> CampaignStats:
    from sqlalchemy import func

    result = await db.execute(
        select(EmailJob.send_status, EmailJob.delivery_status, func.count())
        .where(EmailJob.campaign_id == campaign.id)
        .group_by(EmailJob.send_status, EmailJob.delivery_status)
    )
    counts = {(s, d): n for s, d, n in result.all()}

    delivered = sum(n for (s, d), n in counts.items() if d == "delivered")
    bounced = sum(n for (s, d), n in counts.items() if d == "bounced")
    complained = sum(n for (s, d), n in counts.items() if d == "complained")
    failed = sum(n for (s, d), n in counts.items() if s == "failed_permanent")
    recipients = sum(counts.values())

    opened_result = await db.execute(
        select(func.count()).select_from(EmailJob).where(
            EmailJob.campaign_id == campaign.id, EmailJob.open_count > 0
        )
    )
    clicked_result = await db.execute(
        select(func.count()).select_from(EmailJob).where(
            EmailJob.campaign_id == campaign.id, EmailJob.click_count > 0
        )
    )

    return CampaignStats(
        campaign_id=str(campaign.id), campaign_name=campaign.name,
        recipients=recipients, delivered=delivered, bounced=bounced, failed=failed,
        opened=opened_result.scalar() or 0, clicked=clicked_result.scalar() or 0,
        complained=complained,
    )

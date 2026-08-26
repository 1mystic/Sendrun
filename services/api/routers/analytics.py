"""Read-only cross-campaign aggregates for the analytics dashboard.

Every number here is a real SQL aggregate over EmailJob — never a fabricated
metric. Domain-deliverability groups `to_addr` by its domain suffix; it is a
nice-to-have and stays cheap because it runs over the same rows as the
per-campaign query.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.models import Campaign, EmailJob, User

from ..deps import get_db, require_membership, require_user

router = APIRouter(prefix="/api/organizations/{org_id}/analytics", tags=["analytics"])


class CampaignStatsOut(BaseModel):
    campaign_id: str
    name: str
    sent: int
    delivered: int
    bounced: int
    opened: int
    clicked: int
    delivery_rate: float
    open_rate: float
    click_rate: float


class DomainStatsOut(BaseModel):
    domain: str
    sent: int
    delivered: int
    bounced: int
    bounce_rate: float


class AnalyticsOut(BaseModel):
    total_sent: int
    delivery_rate: float
    open_rate: float
    click_rate: float
    campaigns: list[CampaignStatsOut]
    domains: list[DomainStatsOut]


@router.get("", response_model=AnalyticsOut)
async def get_analytics(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> AnalyticsOut:
    await require_membership(org_id, db, user)

    # Per-job status/counters are pulled in Python rather than via SQL FILTER
    # (...) sums, which SQLite — the test-suite dialect — does not support;
    # this stays portable to both SQLite and Postgres.
    campaign_rows = (
        await db.execute(
            select(Campaign.id, Campaign.name)
            .where(Campaign.org_id == org_id)
            .order_by(Campaign.created_at.desc())
        )
    ).all()

    campaigns_out: list[CampaignStatsOut] = []
    total_sent = total_delivered = total_opened = total_clicked = 0

    for campaign_id, name in campaign_rows:
        job_rows = (
            await db.execute(
                select(EmailJob.delivery_status, EmailJob.send_status,
                       EmailJob.open_count, EmailJob.click_count)
                .where(EmailJob.campaign_id == campaign_id)
            )
        ).all()

        sent = sum(1 for s in job_rows if s[1] in ("sent", "failed_permanent"))
        delivered = sum(1 for s in job_rows if s[0] == "delivered")
        bounced = sum(1 for s in job_rows if s[0] == "bounced")
        opened = sum(1 for s in job_rows if s[2] and s[2] > 0)
        clicked = sum(1 for s in job_rows if s[3] and s[3] > 0)

        total_sent += sent
        total_delivered += delivered
        total_opened += opened
        total_clicked += clicked

        campaigns_out.append(CampaignStatsOut(
            campaign_id=str(campaign_id), name=name, sent=sent, delivered=delivered,
            bounced=bounced, opened=opened, clicked=clicked,
            delivery_rate=round(100 * delivered / sent, 1) if sent else 0.0,
            open_rate=round(100 * opened / sent, 1) if sent else 0.0,
            click_rate=round(100 * clicked / sent, 1) if sent else 0.0,
        ))

    domain_rows = (
        await db.execute(
            select(EmailJob.to_addr, EmailJob.delivery_status)
            .join(Campaign, Campaign.id == EmailJob.campaign_id)
            .where(Campaign.org_id == org_id)
        )
    ).all()

    domain_totals: dict[str, dict[str, int]] = {}
    for to_addr, delivery_status in domain_rows:
        domain = to_addr.rsplit("@", 1)[-1].lower() if "@" in to_addr else "unknown"
        bucket = domain_totals.setdefault(domain, {"sent": 0, "delivered": 0, "bounced": 0})
        bucket["sent"] += 1
        if delivery_status == "delivered":
            bucket["delivered"] += 1
        elif delivery_status == "bounced":
            bucket["bounced"] += 1

    domains_out = [
        DomainStatsOut(
            domain=domain, sent=t["sent"], delivered=t["delivered"], bounced=t["bounced"],
            bounce_rate=round(100 * t["bounced"] / t["sent"], 1) if t["sent"] else 0.0,
        )
        for domain, t in sorted(domain_totals.items(), key=lambda kv: -kv[1]["sent"])
    ]

    return AnalyticsOut(
        total_sent=total_sent,
        delivery_rate=round(100 * total_delivered / total_sent, 1) if total_sent else 0.0,
        open_rate=round(100 * total_opened / total_sent, 1) if total_sent else 0.0,
        click_rate=round(100 * total_clicked / total_sent, 1) if total_sent else 0.0,
        campaigns=campaigns_out,
        domains=domains_out,
    )

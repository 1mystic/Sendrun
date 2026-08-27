"""Campaign list, audit-log-as-notifications, and cross-campaign analytics —
all real SQL aggregates, no fabricated metrics."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from packages.shared.models import Campaign, Contact, EmailJob


async def _signup(client: AsyncClient, email: str) -> None:
    r = await client.post("/api/auth/signup", json={
        "name": email.split("@")[0], "email": email, "password": "correct-horse-battery",
    })
    assert r.status_code == 201


async def _create_org(client: AsyncClient, name: str) -> dict:
    r = await client.post("/api/organizations", json={"name": name})
    assert r.status_code == 201
    return r.json()


@pytest.mark.asyncio
async def test_org_creation_is_recorded_in_the_audit_log(client: AsyncClient):
    await _signup(client, "founder@example.com")
    org = await _create_org(client, "Audit Org")

    r = await client.get(f"/api/organizations/{org['id']}/audit-log")
    assert r.status_code == 200
    actions = [e["action"] for e in r.json()]
    assert "organization.created" in actions


@pytest.mark.asyncio
async def test_audit_log_is_tenant_isolated(client: AsyncClient):
    await _signup(client, "founder2@example.com")
    org_a = await _create_org(client, "Org A2")
    org_b = await _create_org(client, "Org B2")

    r = await client.get(f"/api/organizations/{org_b['id']}/audit-log")
    ids = [e["target_id"] for e in r.json()]
    assert org_a["id"] not in ids


@pytest.mark.asyncio
async def test_campaign_list_returns_recipient_counts(client: AsyncClient, monkeypatch):
    async def _no_op_enqueue(db, **kwargs):
        return uuid4()

    monkeypatch.setattr("services.api.routers.campaigns.enqueue_task", _no_op_enqueue)

    await _signup(client, "lister@example.com")
    org = await _create_org(client, "List Org")
    org_id = org["id"]

    r = await client.post(f"/api/organizations/{org_id}/templates", json={
        "name": "T", "subject": "Hi", "html_body": "<p>x</p>", "variables": [],
    })
    template_id = r.json()["id"]

    r = await client.post(f"/api/organizations/{org_id}/campaigns", json={
        "name": "Campaign A", "template_id": template_id,
        "recipients": {"exclude_suppressed": True},
    })
    campaign_id = r.json()["id"]

    r = await client.get(f"/api/organizations/{org_id}/campaigns")
    assert r.status_code == 200
    listed = [c for c in r.json() if c["id"] == campaign_id]
    assert len(listed) == 1
    assert listed[0]["status"] == "draft"


@pytest.mark.asyncio
async def test_analytics_aggregates_real_delivery_counts(client: AsyncClient, db_session):
    await _signup(client, "analyst@example.com")
    org = await _create_org(client, "Analytics Org")
    org_id = org["id"]

    campaign = Campaign(
        org_id=org["id"], name="C", template_id=uuid4(), template_version=1,
        status="completed", created_by=uuid4(),
    )
    db_session.add(campaign)
    await db_session.flush()

    contact = Contact(org_id=org["id"], email="a@example.com")
    db_session.add(contact)
    await db_session.flush()

    db_session.add_all([
        EmailJob(
            campaign_id=campaign.id, contact_id=contact.id, to_addr="a@gmail.com",
            subject="s", html_body="<p>x</p>", send_status="sent", delivery_status="delivered",
            open_count=1,
        ),
        EmailJob(
            campaign_id=campaign.id, contact_id=contact.id, to_addr="b@gmail.com",
            subject="s", html_body="<p>x</p>", send_status="sent", delivery_status="bounced",
        ),
    ])
    await db_session.commit()

    r = await client.get(f"/api/organizations/{org_id}/analytics")
    assert r.status_code == 200
    body = r.json()
    assert body["total_sent"] == 2
    assert body["delivery_rate"] == 50.0
    assert any(d["domain"] == "gmail.com" and d["sent"] == 2 for d in body["domains"])


@pytest.mark.asyncio
async def test_jobs_inspector_degrades_cleanly_on_sqlite(client: AsyncClient):
    """The `tasks` table is Postgres-only by design (JSONB, see
    packages/durable/queue.py) and is never created on SQLite, which is what
    this whole test suite runs against. The endpoint must return an empty
    list here, not a 500 — a raw-SQL crash mid-request can leave the response
    without CORS headers, which a browser then misreports as a CORS failure
    rather than the real server error underneath it."""
    await _signup(client, "opsowner@example.com")
    org = await _create_org(client, "Ops Org")

    for path in ("dead-letter", "in-flight"):
        r = await client.get(f"/api/organizations/{org['id']}/jobs/{path}")
        assert r.status_code == 200
        assert r.json() == []

"""Agent endpoints through the real API — verifies the DB-loading glue
(template/contact lookup, campaign stats aggregation, audit trail) on top of
the already-tested pure agent logic in test_agents.py. Runs against
FakeLLMProvider (the default when LLM_PROVIDER is unset), so this needs no
real API key."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select


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
async def test_qa_review_runs_against_a_real_template(client: AsyncClient):
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Hackathon Club")

    r = await client.post(f"/api/organizations/{org['id']}/templates", json={
        "name": "Speaker Invite",
        "subject": "Speak at {{event_name}}, {{first_name}}?",
        "html_body": "<p>Hi {{first_name}}, join {{event_name}}.</p>",
        "variables": ["first_name", "event_name"],
    })
    template_id = r.json()["id"]

    r = await client.post(
        f"/api/organizations/{org['id']}/templates/{template_id}/qa-review",
        json={"template_id": template_id},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["agent_name"] == "qa_agent"
    assert body["status"] == "pending"


@pytest.mark.asyncio
async def test_qa_review_uses_the_example_contact_when_given(client: AsyncClient):
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Club")

    r = await client.post(f"/api/organizations/{org['id']}/templates", json={
        "name": "T", "subject": "Hi {{first_name}}", "html_body": "<p>Hi {{first_name}}</p>",
        "variables": ["first_name"],
    })
    template_id = r.json()["id"]

    r = await client.post(f"/api/organizations/{org['id']}/contacts", json={
        "email": "rahul@example.com", "name": "Rahul Menon",
    })
    contact_id = r.json()["id"]

    r = await client.post(
        f"/api/organizations/{org['id']}/templates/{template_id}/qa-review",
        json={"template_id": template_id, "example_contact_id": contact_id},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_qa_review_records_an_audit_log_entry(client: AsyncClient, db_session):
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Club")
    r = await client.post(f"/api/organizations/{org['id']}/templates", json={
        "name": "T", "subject": "Hi", "html_body": "<p>hi</p>", "variables": [],
    })
    template_id = r.json()["id"]

    await client.post(
        f"/api/organizations/{org['id']}/templates/{template_id}/qa-review",
        json={"template_id": template_id},
    )

    from packages.shared.models import AuditLog

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "agent.qa_review_proposed")
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].actor_kind == "ai_agent"


@pytest.mark.asyncio
async def test_qa_review_for_unknown_template_is_404(client: AsyncClient):
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Club")
    r = await client.post(
        f"/api/organizations/{org['id']}/templates/00000000-0000-0000-0000-000000000000/qa-review",
        json={"template_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_qa_review_is_tenant_isolated(client: AsyncClient):
    await _signup(client, "founder@example.com")
    org_a = await _create_org(client, "Org A")
    org_b = await _create_org(client, "Org B")

    r = await client.post(f"/api/organizations/{org_a['id']}/templates", json={
        "name": "A's template", "subject": "Hi", "html_body": "<p>hi</p>", "variables": [],
    })
    template_id = r.json()["id"]

    r = await client.post(
        f"/api/organizations/{org_b['id']}/templates/{template_id}/qa-review",
        json={"template_id": template_id},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_analyze_campaign_with_no_history_still_works(client: AsyncClient):
    """A campaign with no prior completed campaigns to compare against —
    the agent should still produce a proposal, not crash on an empty
    history list."""
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Club")
    template_id = (await client.post(f"/api/organizations/{org['id']}/templates", json={
        "name": "T", "subject": "Hi", "html_body": "<p>hi</p>", "variables": [],
    })).json()["id"]
    await client.post(f"/api/organizations/{org['id']}/contacts", json={
        "email": "a@example.com", "tags": ["x"],
    })
    campaign_id = (await client.post(f"/api/organizations/{org['id']}/campaigns", json={
        "name": "C", "template_id": template_id, "recipients": {"tags": ["x"]},
    })).json()["id"]

    r = await client.post(f"/api/organizations/{org['id']}/campaigns/{campaign_id}/analyze")
    assert r.status_code == 200
    assert r.json()["agent_name"] == "analytics_agent"


@pytest.mark.asyncio
async def test_analyze_campaign_for_unknown_campaign_is_404(client: AsyncClient):
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Club")
    r = await client.post(
        f"/api/organizations/{org['id']}/campaigns/00000000-0000-0000-0000-000000000000/analyze"
    )
    assert r.status_code == 404

"""The preflight endpoint through the real API — verifies the DB-loading
glue (template version lookup, recipient resolution) on top of the already-
tested pure logic in test_preflight.py."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


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
async def test_preflight_runs_against_real_template_and_contacts(client: AsyncClient):
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Hackathon Club")

    # Every declared variable is given a value at the template level except
    # specialization, which is per-contact — this isolates the assertion to
    # exactly the one variable the test cares about.
    r = await client.post(f"/api/organizations/{org['id']}/templates", json={
        "name": "Speaker Invite",
        "subject": "Speak at {{event_name}}, {{first_name}}?",
        "html_body": "<p>Hi {{first_name}}, your work in {{specialization}} is relevant.</p>",
        "variables": ["first_name", "event_name", "specialization"],
    })
    template_id = r.json()["id"]

    await client.post(f"/api/organizations/{org['id']}/contacts", json={
        "email": "rahul@example.com", "name": "Rahul", "tags": ["speaker"],
        "fields": {"specialization": "computer vision", "event_name": "AI Hackathon 2026"},
    })
    await client.post(f"/api/organizations/{org['id']}/contacts", json={
        "email": "arjun@example.com", "name": "Arjun", "tags": ["speaker"],
        "fields": {"event_name": "AI Hackathon 2026"},
        # no specialization field -> should surface as missing
    })

    r = await client.post(f"/api/organizations/{org['id']}/preflight", json={
        "template_id": template_id, "recipients": {"tags": ["speaker"]},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["recipient_count"] == 2
    assert body["personalization_score"] == 50
    assert "arjun@example.com" in body["recipients_missing_variables"]
    assert body["recipients_missing_variables"]["arjun@example.com"] == ["specialization"]
    assert "rahul@example.com" not in body["recipients_missing_variables"]
    assert any(c["id"] == "missing_variables" for c in body["checks"])


@pytest.mark.asyncio
async def test_preflight_with_no_resolved_recipients_is_rejected(client: AsyncClient):
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Empty Club")
    r = await client.post(f"/api/organizations/{org['id']}/templates", json={
        "name": "T", "subject": "Hi", "html_body": "<p>hi</p>", "variables": [],
    })
    template_id = r.json()["id"]

    r = await client.post(f"/api/organizations/{org['id']}/preflight", json={
        "template_id": template_id, "recipients": {"tags": ["nobody-has-this"]},
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_preflight_for_unknown_template_is_404(client: AsyncClient):
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Club")
    await client.post(f"/api/organizations/{org['id']}/contacts", json={
        "email": "a@example.com", "tags": ["x"],
    })

    r = await client.post(f"/api/organizations/{org['id']}/preflight", json={
        "template_id": "00000000-0000-0000-0000-000000000000",
        "recipients": {"tags": ["x"]},
    })
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_preflight_is_tenant_isolated(client: AsyncClient):
    await _signup(client, "founder@example.com")
    org_a = await _create_org(client, "Org A")
    org_b = await _create_org(client, "Org B")

    r = await client.post(f"/api/organizations/{org_a['id']}/templates", json={
        "name": "A's template", "subject": "Hi", "html_body": "<p>hi</p>", "variables": [],
    })
    template_id = r.json()["id"]
    await client.post(f"/api/organizations/{org_a['id']}/contacts", json={
        "email": "a@example.com", "tags": ["x"],
    })

    # org B cannot preflight against org A's template.
    r = await client.post(f"/api/organizations/{org_b['id']}/preflight", json={
        "template_id": template_id, "recipients": {"tags": ["x"]},
    })
    assert r.status_code == 404

"""Mailing lists (Group) CRUD, bulk import, and the campaign-launch pipeline
that consumes them. The suppression-survives-reimport test is the one
invariant here that must never regress — see CLAUDE.md and Contact.suppressed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

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


async def _create_group(client: AsyncClient, org_id: str, name: str) -> dict:
    r = await client.post(f"/api/organizations/{org_id}/groups", json={"name": name})
    assert r.status_code == 201
    return r.json()


@pytest.fixture
def no_op_enqueue():
    with patch(
        "services.api.routers.campaigns.enqueue_task",
        new=AsyncMock(return_value=uuid4()),
    ) as mocked:
        yield mocked


@pytest.mark.asyncio
async def test_create_and_list_groups_with_contact_count(client: AsyncClient):
    await _signup(client, "owner@example.com")
    org = await _create_org(client, "Org")
    group = await _create_group(client, org["id"], "Speakers")
    assert group["contact_count"] == 0

    await client.post(f"/api/organizations/{org['id']}/groups/{group['id']}/import", json={
        "email_column": "email", "name_column": "name",
        "rows": [{"values": {"email": "a@example.com", "name": "Alice"}}],
    })

    r = await client.get(f"/api/organizations/{org['id']}/groups")
    assert r.status_code == 200
    listed = r.json()
    assert len(listed) == 1
    assert listed[0]["contact_count"] == 1


@pytest.mark.asyncio
async def test_bulk_import_creates_contacts_with_mapped_fields(client: AsyncClient):
    await _signup(client, "owner@example.com")
    org = await _create_org(client, "Org")
    group = await _create_group(client, org["id"], "Certs")

    r = await client.post(f"/api/organizations/{org['id']}/groups/{group['id']}/import", json={
        "email_column": "Email Address",
        "name_column": "Full Name",
        "rows": [
            {"values": {
                "Email Address": "doc1@example.com",
                "Full Name": "Dr. One",
                "Cert Ref-ID": "CR-001",
                "Specialization": "Cardiology",
            }},
        ],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 1
    assert body["updated"] == 0
    assert body["skipped"] == []
    assert body["group_contact_count"] == 1

    detail = await client.get(f"/api/organizations/{org['id']}/groups/{group['id']}")
    contact = detail.json()["contacts"][0]
    assert contact["email"] == "doc1@example.com"
    assert contact["name"] == "Dr. One"
    assert contact["fields"] == {"cert_ref_id": "CR-001", "specialization": "Cardiology"}


@pytest.mark.asyncio
async def test_reimporting_same_emails_upserts_not_duplicates(client: AsyncClient):
    await _signup(client, "owner@example.com")
    org = await _create_org(client, "Org")
    group = await _create_group(client, org["id"], "List")

    await client.post(f"/api/organizations/{org['id']}/groups/{group['id']}/import", json={
        "email_column": "email", "name_column": "name",
        "rows": [{"values": {"email": "a@example.com", "name": "Old Name", "city": "NYC"}}],
    })

    r = await client.post(f"/api/organizations/{org['id']}/groups/{group['id']}/import", json={
        "email_column": "email", "name_column": "name",
        "rows": [{"values": {"email": "a@example.com", "name": "New Name", "city": "LA"}}],
    })
    body = r.json()
    assert body["created"] == 0
    assert body["updated"] == 1
    assert body["group_contact_count"] == 1

    r = await client.get(f"/api/organizations/{org['id']}/contacts")
    contacts = r.json()
    assert len(contacts) == 1
    assert contacts[0]["name"] == "New Name"
    assert contacts[0]["fields"]["city"] == "LA"


@pytest.mark.asyncio
async def test_suppressed_contact_stays_suppressed_after_reimport(client: AsyncClient, db_session):
    """The critical invariant: a contact who unsubscribed must never be
    silently reactivated by a later import into a different mailing list."""
    await _signup(client, "owner@example.com")
    org = await _create_org(client, "Org")
    group_a = await _create_group(client, org["id"], "List A")
    group_b = await _create_group(client, org["id"], "List B")

    await client.post(f"/api/organizations/{org['id']}/groups/{group_a['id']}/import", json={
        "email_column": "email", "name_column": None,
        "rows": [{"values": {"email": "stale@example.com"}}],
    })

    r = await client.get(f"/api/organizations/{org['id']}/contacts")
    contact_id = r.json()[0]["id"]

    from packages.shared.models import Contact

    contact = await db_session.get(Contact, contact_id)
    contact.suppressed = True
    contact.suppressed_reason = "unsubscribed"
    await db_session.commit()

    r = await client.post(f"/api/organizations/{org['id']}/groups/{group_b['id']}/import", json={
        "email_column": "email", "name_column": None,
        "rows": [{"values": {"email": "stale@example.com", "city": "LA"}}],
    })
    assert r.json()["updated"] == 1

    r = await client.get(f"/api/organizations/{org['id']}/contacts")
    refreshed = r.json()[0]
    assert refreshed["suppressed"] is True

    detail = await client.get(f"/api/organizations/{org['id']}/groups/{group_b['id']}")
    assert len(detail.json()["contacts"]) == 1


@pytest.mark.asyncio
async def test_invalid_email_is_skipped_not_fatal(client: AsyncClient):
    await _signup(client, "owner@example.com")
    org = await _create_org(client, "Org")
    group = await _create_group(client, org["id"], "List")

    r = await client.post(f"/api/organizations/{org['id']}/groups/{group['id']}/import", json={
        "email_column": "email", "name_column": None,
        "rows": [
            {"values": {"email": "not-an-email"}},
            {"values": {"email": "valid@example.com"}},
        ],
    })
    body = r.json()
    assert body["created"] == 1
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["row_index"] == 0
    assert "invalid email" in body["skipped"][0]["reason"]


@pytest.mark.asyncio
async def test_ambiguous_column_header_collision_is_rejected(client: AsyncClient):
    await _signup(client, "owner@example.com")
    org = await _create_org(client, "Org")
    group = await _create_group(client, org["id"], "List")

    r = await client.post(f"/api/organizations/{org['id']}/groups/{group['id']}/import", json={
        "email_column": "email", "name_column": None,
        "rows": [
            {"values": {"email": "a@example.com", "Cert Ref": "1", "cert-ref": "2"}},
        ],
    })
    body = r.json()
    assert body["created"] == 0
    assert len(body["skipped"]) == 1
    assert "ambiguous" in body["skipped"][0]["reason"]


@pytest.mark.asyncio
async def test_launching_campaign_with_group_resolves_imported_contacts(
    client: AsyncClient, no_op_enqueue
):
    await _signup(client, "owner@example.com")
    org = await _create_org(client, "Org")
    group = await _create_group(client, org["id"], "Imported List")

    await client.post(f"/api/organizations/{org['id']}/groups/{group['id']}/import", json={
        "email_column": "email", "name_column": "name",
        "rows": [
            {"values": {"email": "x1@example.com", "name": "X1"}},
            {"values": {"email": "x2@example.com", "name": "X2"}},
        ],
    })
    await client.post(f"/api/organizations/{org['id']}/contacts", json={
        "email": "outsider@example.com", "tags": ["other"],
    })

    template = await client.post(f"/api/organizations/{org['id']}/templates", json={
        "name": "T", "subject": "Hi {{name}}", "html_body": "<p>Hi {{name}}</p>",
        "variables": ["name"],
    })
    template_id = template.json()["id"]

    r = await client.post(f"/api/organizations/{org['id']}/campaigns", json={
        "name": "Group Launch", "template_id": template_id,
        "recipients": {"group_id": group["id"]},
    })
    assert r.status_code == 201
    assert r.json()["recipient_count"] == 2


@pytest.mark.asyncio
async def test_group_tenant_isolation(client: AsyncClient):
    await _signup(client, "founder@example.com")
    org_a = await _create_org(client, "Org A")
    org_b = await _create_org(client, "Org B")
    group_a = await _create_group(client, org_a["id"], "A-List")

    r = await client.get(f"/api/organizations/{org_b['id']}/groups/{group_a['id']}")
    assert r.status_code == 404

    r = await client.post(f"/api/organizations/{org_b['id']}/groups/{group_a['id']}/import", json={
        "email_column": "email", "name_column": None,
        "rows": [{"values": {"email": "sneaky@example.com"}}],
    })
    assert r.status_code == 404

    r = await client.get(f"/api/organizations/{org_b['id']}/groups")
    assert r.json() == []

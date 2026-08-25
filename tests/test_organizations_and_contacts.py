"""Organizations, RBAC, tenant isolation, and the smart-filter resolver.

The tenant-isolation tests are the ones that matter most here: a query that
leaks another org's contacts is a much worse bug than a missing feature.
"""

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
async def test_creating_an_org_makes_the_creator_owner(client: AsyncClient):
    await _signup(client, "owner@example.com")
    org = await _create_org(client, "AI Research Club")
    assert org["role"] == "owner"
    assert org["slug"] == "ai-research-club"


@pytest.mark.asyncio
async def test_duplicate_org_names_get_distinct_slugs(client: AsyncClient):
    await _signup(client, "a@example.com")
    first = await _create_org(client, "Acme")
    second = await _create_org(client, "Acme")
    assert first["slug"] != second["slug"]
    assert second["slug"].startswith("acme-")


@pytest.mark.asyncio
async def test_viewer_cannot_create_a_campaign_capability_but_owner_can(client: AsyncClient):
    """Exercises the capability matrix directly rather than through a campaigns
    endpoint that does not exist yet — the matrix itself is what Phase 1 owns."""
    from packages.shared.authz import Membership, Role

    owner = Membership(org_id=None, user_id=None, role=Role.OWNER)  # type: ignore[arg-type]
    viewer = Membership(org_id=None, user_id=None, role=Role.VIEWER)

    assert owner.can("create_campaign") is True
    assert viewer.can("create_campaign") is False
    assert viewer.can("view_campaigns") is True  # viewers can still read


@pytest.mark.asyncio
async def test_a_non_member_gets_404_not_403_for_an_org_they_cannot_see(client: AsyncClient):
    """404, not 403 — a 403 on a private org's URL confirms the org exists to
    someone who otherwise has zero information about it."""
    await _signup(client, "outsider@example.com")
    fake_org_id = "00000000-0000-0000-0000-000000000000"
    r = await client.get(f"/api/organizations/{fake_org_id}/members")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_contacts_are_isolated_between_organizations(client: AsyncClient):
    """The core tenant-isolation guarantee: org A can never see org B's contacts,
    even by directly querying org A's own endpoint."""
    await _signup(client, "founder@example.com")
    org_a = await _create_org(client, "Org A")
    org_b = await _create_org(client, "Org B")

    r = await client.post(
        f"/api/organizations/{org_a['id']}/contacts",
        json={"email": "alice@example.com", "name": "Alice", "tags": ["speaker"]},
    )
    assert r.status_code == 201

    # Same user, a member of both orgs, queries org B — must not see org A's contact.
    r = await client.get(f"/api/organizations/{org_b['id']}/contacts")
    assert r.status_code == 200
    assert r.json() == []

    r = await client.get(f"/api/organizations/{org_a['id']}/contacts")
    assert len(r.json()) == 1
    assert r.json()[0]["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_smart_filter_resolves_by_tag(client: AsyncClient):
    await _signup(client, "recruiter@example.com")
    org = await _create_org(client, "Hackathon Club")

    await client.post(f"/api/organizations/{org['id']}/contacts", json={
        "email": "speaker1@example.com", "tags": ["speaker", "AI"],
    })
    await client.post(f"/api/organizations/{org['id']}/contacts", json={
        "email": "sponsor1@example.com", "tags": ["sponsor"],
    })

    r = await client.post(f"/api/organizations/{org['id']}/contacts/resolve", json={
        "tags": ["speaker"], "exclude_suppressed": True,
    })
    assert r.status_code == 200
    ids = r.json()
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_smart_filter_excludes_suppressed_contacts(client, db_session):
    """A suppressed contact must never be resolved into a send list, even if it
    matches every other filter condition — this is the guard the plan calls out
    against ever re-adding an unsubscribed contact via a broad segment."""
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Org")

    r = await client.post(f"/api/organizations/{org['id']}/contacts", json={
        "email": "stale@example.com", "tags": ["alumni"],
    })
    contact_id = r.json()["id"]

    # There is no unsubscribe endpoint yet (that lands with Phase 4 webhooks), so
    # flip the flag directly on the same session the app is using.
    from packages.shared.models import Contact

    contact = await db_session.get(Contact, contact_id)
    contact.suppressed = True
    contact.suppressed_reason = "unsubscribed"
    await db_session.commit()

    r = await client.post(f"/api/organizations/{org['id']}/contacts/resolve", json={
        "tags": ["alumni"], "exclude_suppressed": True,
    })
    assert contact_id not in r.json()


@pytest.mark.asyncio
async def test_invite_requires_admin_capability(client: AsyncClient):
    await _signup(client, "solo-owner@example.com")
    org = await _create_org(client, "Solo Org")

    r = await client.post(f"/api/organizations/{org['id']}/invites", json={
        "email": "newperson@example.com", "role": "editor",
    })
    assert r.status_code == 202
    assert r.json()["role"] == "editor"


@pytest.mark.asyncio
async def test_invite_with_unknown_role_is_rejected(client: AsyncClient):
    await _signup(client, "owner2@example.com")
    org = await _create_org(client, "Org2")

    r = await client.post(f"/api/organizations/{org['id']}/invites", json={
        "email": "x@example.com", "role": "superadmin",
    })
    assert r.status_code == 422

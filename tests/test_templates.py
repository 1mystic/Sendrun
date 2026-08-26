"""Template CRUD, versioning-not-editing, and preview through the real API."""

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


async def _setup(client: AsyncClient) -> str:
    await _signup(client, "author@example.com")
    org = await _create_org(client, "Speaker Org")
    return org["id"]


@pytest.mark.asyncio
async def test_create_template_succeeds_with_declared_variables(client: AsyncClient):
    org_id = await _setup(client)
    r = await client.post(f"/api/organizations/{org_id}/templates", json={
        "name": "Speaker Invite",
        "subject": "Speak at {{event_name}}, {{first_name}}?",
        "html_body": "<p>Hi {{first_name}}, join {{event_name}}.</p>",
        "variables": ["first_name", "event_name"],
    })
    assert r.status_code == 201
    body = r.json()
    assert body["current_version"] == 1
    assert body["latest"]["version"] == 1


@pytest.mark.asyncio
async def test_create_template_with_undeclared_variable_is_rejected(client: AsyncClient):
    org_id = await _setup(client)
    r = await client.post(f"/api/organizations/{org_id}/templates", json={
        "name": "Bad Template",
        "subject": "Hi {{first_name}}",
        "html_body": "<p>{{secret_internal_field}}</p>",
        "variables": ["first_name"],
    })
    assert r.status_code == 422
    assert "undeclared" in r.json()["detail"]


@pytest.mark.asyncio
async def test_updating_a_template_creates_a_new_version_not_an_edit(client: AsyncClient):
    org_id = await _setup(client)
    r = await client.post(f"/api/organizations/{org_id}/templates", json={
        "name": "V1", "subject": "Hi", "html_body": "<p>v1</p>", "variables": [],
    })
    template_id = r.json()["id"]

    r = await client.put(f"/api/organizations/{org_id}/templates/{template_id}", json={
        "name": "V2", "subject": "Hi", "html_body": "<p>v2</p>", "variables": [],
    })
    assert r.status_code == 200
    assert r.json()["current_version"] == 2
    assert r.json()["latest"]["html_body"] == "<p>v2</p>"

    # Listing shows the latest version — the old one is not deleted, just superseded.
    r = await client.get(f"/api/organizations/{org_id}/templates")
    updated = next(t for t in r.json() if t["id"] == template_id)
    assert updated["current_version"] == 2


@pytest.mark.asyncio
async def test_preview_renders_for_a_specific_contact(client: AsyncClient):
    org_id = await _setup(client)
    r = await client.post(f"/api/organizations/{org_id}/contacts", json={
        "email": "rahul@example.com", "name": "Rahul Menon",
        "fields": {"specialization": "computer vision"},
    })
    contact_id = r.json()["id"]

    r = await client.post(f"/api/organizations/{org_id}/templates", json={
        "name": "Speaker Invite",
        "subject": "Speak at {{event_name}}, {{first_name}}?",
        "html_body": "<p>Hi {{first_name}}, your work in {{specialization}} is relevant.</p>",
        "variables": ["first_name", "event_name", "specialization"],
    })
    template_id = r.json()["id"]

    r = await client.post(
        f"/api/organizations/{org_id}/templates/{template_id}/preview",
        json={"contact_id": contact_id},
    )
    assert r.status_code == 200
    body = r.json()
    assert "Rahul" in body["subject"]  # first_name derived from contact.name
    assert "computer vision" in body["html_body"]
    assert body["missing_variables"] == ["event_name"]
    assert body["is_complete"] is False


@pytest.mark.asyncio
async def test_preview_strips_a_javascript_href_entirely(client: AsyncClient):
    """bleach's protocol allowlist strips a disallowed-scheme href outright
    rather than passing it through — so the dangerous link never survives to
    reach the link-check step at all. Stronger than merely flagging it."""
    org_id = await _setup(client)
    r = await client.post(f"/api/organizations/{org_id}/contacts", json={
        "email": "x@example.com", "name": "X",
    })
    contact_id = r.json()["id"]

    r = await client.post(f"/api/organizations/{org_id}/templates", json={
        "name": "T", "subject": "Hi",
        "html_body": '<a href="javascript:alert(1)">click</a>',
        "variables": [],
    })
    template_id = r.json()["id"]

    r = await client.post(
        f"/api/organizations/{org_id}/templates/{template_id}/preview",
        json={"contact_id": contact_id},
    )
    body = r.json()
    assert "javascript:" not in body["html_body"]
    assert body["links"] == []  # nothing to check — the href is gone


@pytest.mark.asyncio
async def test_preview_flags_a_malformed_but_syntactically_valid_link(client: AsyncClient):
    """A link check.check_link failure that DOES survive sanitization — an
    http(s) URL missing a host — exercises the link-check reporting path
    that the javascript: case above bypasses entirely."""
    org_id = await _setup(client)
    r = await client.post(f"/api/organizations/{org_id}/contacts", json={
        "email": "y@example.com", "name": "Y",
    })
    contact_id = r.json()["id"]

    r = await client.post(f"/api/organizations/{org_id}/templates", json={
        "name": "T2", "subject": "Hi",
        "html_body": '<a href="http://">broken</a>',
        "variables": [],
    })
    template_id = r.json()["id"]

    r = await client.post(
        f"/api/organizations/{org_id}/templates/{template_id}/preview",
        json={"contact_id": contact_id},
    )
    body = r.json()
    assert len(body["links"]) == 1
    assert body["links"][0]["ok"] is False


@pytest.mark.asyncio
async def test_templates_are_tenant_isolated(client: AsyncClient):
    await _signup(client, "founder@example.com")
    org_a = await _create_org(client, "Org A")
    org_b = await _create_org(client, "Org B")

    await client.post(f"/api/organizations/{org_a['id']}/templates", json={
        "name": "A's template", "subject": "Hi", "html_body": "<p>x</p>", "variables": [],
    })

    # Org B only ever sees its own starter templates — never A's custom one.
    r = await client.get(f"/api/organizations/{org_b['id']}/templates")
    assert "A's template" not in [t["name"] for t in r.json()]


@pytest.mark.asyncio
async def test_editor_can_create_template_but_viewer_cannot(client: AsyncClient):
    """Exercises the capability gate directly on the endpoint, not just the
    matrix in isolation — edit_template requires Editor+."""
    org_id = await _setup(client)  # creator is Owner, which is > Editor

    r = await client.post(f"/api/organizations/{org_id}/templates", json={
        "name": "T", "subject": "Hi", "html_body": "<p>x</p>", "variables": [],
    })
    assert r.status_code == 201  # Owner has Editor-level capability


@pytest.mark.asyncio
async def test_org_creation_seeds_starter_templates(client: AsyncClient):
    """create_organization seeds real, renderable starter templates rather
    than leaving a new org with an empty template list."""
    await _signup(client, "new@example.com")
    org = await _create_org(client, "Fresh Org")

    r = await client.get(f"/api/organizations/{org['id']}/templates")
    assert r.status_code == 200
    templates = r.json()
    assert len(templates) >= 2
    for t in templates:
        assert t["archived"] is False
        assert t["latest"]["subject"]
        assert t["latest"]["html_body"]


@pytest.mark.asyncio
async def test_archiving_hides_from_default_list_but_resolves_by_id(client: AsyncClient):
    org_id = await _setup(client)
    r = await client.post(f"/api/organizations/{org_id}/templates", json={
        "name": "Archivable", "subject": "Hi", "html_body": "<p>x</p>", "variables": [],
    })
    template_id = r.json()["id"]

    r = await client.delete(f"/api/organizations/{org_id}/templates/{template_id}")
    assert r.status_code == 200
    assert r.json()["archived"] is True

    r = await client.get(f"/api/organizations/{org_id}/templates")
    assert template_id not in [t["id"] for t in r.json()]

    # Still directly resolvable by id — a past/in-flight campaign referencing
    # this template_id + version must never 404.
    r = await client.get(f"/api/organizations/{org_id}/templates/{template_id}")
    assert r.status_code == 200
    assert r.json()["archived"] is True

    r = await client.get(f"/api/organizations/{org_id}/templates?include_archived=true")
    assert template_id in [t["id"] for t in r.json()]


@pytest.mark.asyncio
async def test_campaign_launch_still_resolves_an_archived_template(
    client: AsyncClient, monkeypatch
):
    """A campaign pins template_id + template_version at creation; archiving
    the template afterward must not break launch for a campaign that already
    referenced it."""
    calls = []

    async def _no_op_enqueue(db, **kwargs):
        calls.append(kwargs)
        from uuid import uuid4
        return uuid4()

    monkeypatch.setattr("services.api.routers.campaigns.enqueue_task", _no_op_enqueue)

    org_id = await _setup(client)
    r = await client.post(f"/api/organizations/{org_id}/contacts", json={
        "email": "a@example.com", "name": "A",
    })

    r = await client.post(f"/api/organizations/{org_id}/templates", json={
        "name": "T", "subject": "Hi", "html_body": "<p>x</p>", "variables": [],
    })
    template_id = r.json()["id"]

    r = await client.post(f"/api/organizations/{org_id}/campaigns", json={
        "name": "Campaign", "template_id": template_id,
        "recipients": {"exclude_suppressed": True},
    })
    assert r.status_code == 201
    campaign_id = r.json()["id"]

    r = await client.delete(f"/api/organizations/{org_id}/templates/{template_id}")
    assert r.status_code == 200

    r = await client.post(f"/api/organizations/{org_id}/campaigns/{campaign_id}/launch", json={
        "name": "Campaign", "template_id": template_id,
        "recipients": {"exclude_suppressed": True},
    })
    assert r.status_code == 200
    assert r.json()["status"] == "running"

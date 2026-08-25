"""Campaign creation, launch fan-out, cancellation, and progress — through the
real API, against SQLite.

IMPORTANT SCOPE NOTE: `enqueue_task` (packages/shared/enqueue.py) executes
queue.py's ENQUEUE statement, which casts to Postgres's JSONB type and is not
valid SQLite SQL. These tests verify everything up to and INCLUDING the
EmailJob fan-out (recipient resolution, template rendering per contact,
LAUNCHING transition, job row creation) by monkeypatching enqueue_task to a
no-op, then assert on the resulting EmailJob rows directly. What is NOT
verified here is the real ENQUEUE SQL itself or the worker's DEQUEUE/reaper
loop — those need a live Postgres instance (a free Neon branch) to run at all,
which is not available in this environment. See NEXT.md.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from packages.shared.models import EmailJob


async def _signup(client: AsyncClient, email: str) -> None:
    r = await client.post("/api/auth/signup", json={
        "name": email.split("@")[0], "email": email, "password": "correct-horse-battery",
    })
    assert r.status_code == 201


async def _create_org(client: AsyncClient, name: str) -> dict:
    r = await client.post("/api/organizations", json={"name": name})
    assert r.status_code == 201
    return r.json()


async def _create_template(client: AsyncClient, org_id: str) -> str:
    r = await client.post(f"/api/organizations/{org_id}/templates", json={
        "name": "Speaker Invite",
        "subject": "Speak at {{event_name}}, {{first_name}}?",
        "html_body": "<p>Hi {{first_name}}, join {{event_name}}.</p>",
        "variables": ["first_name", "event_name"],
    })
    assert r.status_code == 201
    return r.json()["id"]


async def _create_contact(client: AsyncClient, org_id: str, email: str, tags: list[str]) -> str:
    r = await client.post(f"/api/organizations/{org_id}/contacts", json={
        "email": email, "name": email.split("@")[0].title(), "tags": tags,
    })
    assert r.status_code == 201
    return r.json()["id"]


@pytest.fixture
def no_op_enqueue():
    """The scope boundary this whole file is testing against — see the module
    docstring. Returns a fixed uuid so callers that inspect the return value
    still get something well-formed."""
    with patch(
        "services.api.routers.campaigns.enqueue_task",
        new=AsyncMock(return_value=uuid4()),
    ) as mocked:
        yield mocked


@pytest.mark.asyncio
async def test_create_campaign_resolves_recipient_count(client: AsyncClient):
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Hackathon Club")
    template_id = await _create_template(client, org["id"])
    await _create_contact(client, org["id"], "a@example.com", ["speaker"])
    await _create_contact(client, org["id"], "b@example.com", ["speaker"])
    await _create_contact(client, org["id"], "c@example.com", ["sponsor"])

    r = await client.post(f"/api/organizations/{org['id']}/campaigns", json={
        "name": "Speaker Outreach", "template_id": template_id,
        "recipients": {"tags": ["speaker"]},
    })
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "draft"
    assert body["recipient_count"] == 2


@pytest.mark.asyncio
async def test_launch_creates_one_email_job_per_resolved_contact(
    client: AsyncClient, db_session, no_op_enqueue,
):
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Hackathon Club")
    template_id = await _create_template(client, org["id"])
    await _create_contact(client, org["id"], "rahul@example.com", ["speaker"])
    await _create_contact(client, org["id"], "ananya@example.com", ["speaker"])
    await _create_contact(client, org["id"], "sponsor@example.com", ["sponsor"])

    r = await client.post(f"/api/organizations/{org['id']}/campaigns", json={
        "name": "Speaker Outreach", "template_id": template_id,
        "recipients": {"tags": ["speaker"]},
    })
    campaign_id = r.json()["id"]

    r = await client.post(
        f"/api/organizations/{org['id']}/campaigns/{campaign_id}/launch",
        json={"name": "x", "template_id": template_id, "recipients": {"tags": ["speaker"]}},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    assert r.json()["recipient_count"] == 2

    jobs = (
        await db_session.execute(select(EmailJob).where(EmailJob.campaign_id == campaign_id))
    ).scalars().all()
    assert len(jobs) == 2
    assert {j.to_addr for j in jobs} == {"rahul@example.com", "ananya@example.com"}
    assert all(j.send_status == "queued" for j in jobs)
    assert no_op_enqueue.call_count == 2  # one enqueue per job


@pytest.mark.asyncio
async def test_launch_renders_each_job_with_that_contacts_own_variables(
    client: AsyncClient, db_session, no_op_enqueue,
):
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Club")
    template_id = await _create_template(client, org["id"])
    await _create_contact(client, org["id"], "rahul@example.com", ["speaker"])

    r = await client.post(f"/api/organizations/{org['id']}/campaigns", json={
        "name": "X", "template_id": template_id, "recipients": {"tags": ["speaker"]},
    })
    campaign_id = r.json()["id"]

    await client.post(
        f"/api/organizations/{org['id']}/campaigns/{campaign_id}/launch",
        json={"name": "x", "template_id": template_id, "recipients": {"tags": ["speaker"]}},
    )

    job = (
        await db_session.execute(select(EmailJob).where(EmailJob.campaign_id == campaign_id))
    ).scalar_one()
    assert "Rahul" in job.subject  # first_name derived from contact.name
    assert "{{" not in job.subject  # fully rendered, no leftover template syntax
    assert "{{" not in job.html_body


@pytest.mark.asyncio
async def test_launch_re_resolves_recipients_rather_than_trusting_the_client(
    client: AsyncClient, db_session, no_op_enqueue,
):
    """A contact removed from the segment between create and launch must not
    receive a send — the launch endpoint re-runs the SmartFilter itself."""
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Club")
    template_id = await _create_template(client, org["id"])
    contact_id = await _create_contact(client, org["id"], "will-unsub@example.com", ["speaker"])

    r = await client.post(f"/api/organizations/{org['id']}/campaigns", json={
        "name": "X", "template_id": template_id, "recipients": {"tags": ["speaker"]},
    })
    campaign_id = r.json()["id"]

    from packages.shared.models import Contact
    contact = await db_session.get(Contact, contact_id)
    contact.suppressed = True
    await db_session.commit()

    await client.post(
        f"/api/organizations/{org['id']}/campaigns/{campaign_id}/launch",
        json={"name": "x", "template_id": template_id, "recipients": {"tags": ["speaker"]}},
    )

    jobs = (
        await db_session.execute(select(EmailJob).where(EmailJob.campaign_id == campaign_id))
    ).scalars().all()
    assert len(jobs) == 0  # the now-suppressed contact was excluded


@pytest.mark.asyncio
async def test_launch_with_zero_resolved_recipients_is_rejected(
    client: AsyncClient, no_op_enqueue,
):
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Empty Club")
    template_id = await _create_template(client, org["id"])
    empty_filter = {"tags": ["nobody-has-this-tag"]}

    r = await client.post(f"/api/organizations/{org['id']}/campaigns", json={
        "name": "X", "template_id": template_id, "recipients": empty_filter,
    })
    campaign_id = r.json()["id"]

    r = await client.post(
        f"/api/organizations/{org['id']}/campaigns/{campaign_id}/launch",
        json={"name": "x", "template_id": template_id, "recipients": empty_filter},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_cannot_launch_an_already_running_campaign_twice(
    client: AsyncClient, no_op_enqueue,
):
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Club")
    template_id = await _create_template(client, org["id"])
    await _create_contact(client, org["id"], "a@example.com", ["speaker"])

    r = await client.post(f"/api/organizations/{org['id']}/campaigns", json={
        "name": "X", "template_id": template_id, "recipients": {"tags": ["speaker"]},
    })
    campaign_id = r.json()["id"]
    launch_body = {"name": "x", "template_id": template_id, "recipients": {"tags": ["speaker"]}}

    r1 = await client.post(
        f"/api/organizations/{org['id']}/campaigns/{campaign_id}/launch", json=launch_body
    )
    assert r1.status_code == 200

    r2 = await client.post(
        f"/api/organizations/{org['id']}/campaigns/{campaign_id}/launch", json=launch_body
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_cancel_cancels_only_queued_jobs(client: AsyncClient, db_session, no_op_enqueue):
    """A job already 'sending' or 'sent' must survive a cancel untouched — see
    CLAUDE.md invariant 5, a send in flight cannot be recalled."""
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Club")
    template_id = await _create_template(client, org["id"])
    await _create_contact(client, org["id"], "a@example.com", ["speaker"])
    await _create_contact(client, org["id"], "b@example.com", ["speaker"])

    r = await client.post(f"/api/organizations/{org['id']}/campaigns", json={
        "name": "X", "template_id": template_id, "recipients": {"tags": ["speaker"]},
    })
    campaign_id = r.json()["id"]
    await client.post(
        f"/api/organizations/{org['id']}/campaigns/{campaign_id}/launch",
        json={"name": "x", "template_id": template_id, "recipients": {"tags": ["speaker"]}},
    )

    jobs = (
        await db_session.execute(select(EmailJob).where(EmailJob.campaign_id == campaign_id))
    ).scalars().all()
    already_sent = jobs[0]
    already_sent.send_status = "sent"
    already_sent.provider_message_id = "msg_already_sent"
    await db_session.commit()

    r = await client.post(f"/api/organizations/{org['id']}/campaigns/{campaign_id}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"

    await db_session.refresh(already_sent)
    assert already_sent.send_status == "sent"  # untouched

    still_queued = jobs[1]
    await db_session.refresh(still_queued)
    assert still_queued.send_status == "cancelled"


@pytest.mark.asyncio
async def test_progress_reflects_email_job_state_not_the_task_queue(
    client: AsyncClient, db_session, no_op_enqueue,
):
    """The progress endpoint must read Postgres (EmailJob rows), never the
    durable engine's task table — CLAUDE.md invariant 6."""
    await _signup(client, "sender@example.com")
    org = await _create_org(client, "Club")
    template_id = await _create_template(client, org["id"])
    await _create_contact(client, org["id"], "a@example.com", ["speaker"])
    await _create_contact(client, org["id"], "b@example.com", ["speaker"])
    await _create_contact(client, org["id"], "c@example.com", ["speaker"])

    r = await client.post(f"/api/organizations/{org['id']}/campaigns", json={
        "name": "X", "template_id": template_id, "recipients": {"tags": ["speaker"]},
    })
    campaign_id = r.json()["id"]
    await client.post(
        f"/api/organizations/{org['id']}/campaigns/{campaign_id}/launch",
        json={"name": "x", "template_id": template_id, "recipients": {"tags": ["speaker"]}},
    )

    jobs = (
        await db_session.execute(select(EmailJob).where(EmailJob.campaign_id == campaign_id))
    ).scalars().all()
    jobs[0].send_status = "sent"
    jobs[0].delivery_status = "delivered"
    jobs[1].send_status = "sending"
    await db_session.commit()

    r = await client.get(f"/api/organizations/{org['id']}/campaigns/{campaign_id}/progress")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["delivered"] == 1
    assert body["sending"] == 1
    assert body["attempted"] == 1  # only jobs[0] has reached a terminal send state

"""SQLAlchemyJobStore against real EmailJob rows on SQLite.

Unlike the ENQUEUE/DEQUEUE SQL in packages/durable/queue.py, this store is
plain SQLAlchemy ORM (no Postgres-only syntax), so it runs on SQLite exactly
as it will in production — this is real coverage, not a scope-limited stand-in
like test_campaign_launch.py's no_op_enqueue fixture.

These mirror test_durability.py's InMemoryJobStore tests one-for-one, which is
the point: the two stores must honor the identical contract, or a green test
suite proves nothing about what actually runs against Postgres.
"""

from __future__ import annotations

import uuid

import pytest

from packages.shared.job_store import SQLAlchemyJobStore
from packages.shared.models import Campaign, Contact, EmailJob, Organization, User


async def _make_job(
    db_session, *, send_status: str = "queued", provider_message_id=None
) -> uuid.UUID:
    org = Organization(name="O", slug=f"o-{uuid.uuid4().hex[:8]}")
    user = User(email=f"{uuid.uuid4().hex}@example.com", name="U", password_hash="x")
    db_session.add_all([org, user])
    await db_session.flush()

    contact = Contact(org_id=org.id, email="c@example.com")
    template_id = uuid.uuid4()
    campaign = Campaign(
        org_id=org.id, name="C", template_id=template_id, template_version=1,
        status="running", created_by=user.id,
    )
    db_session.add_all([contact, campaign])
    await db_session.flush()

    job = EmailJob(
        campaign_id=campaign.id, contact_id=contact.id, to_addr="c@example.com",
        subject="Hi", html_body="<p>hi</p>", send_status=send_status,
        provider_message_id=provider_message_id,
    )
    db_session.add(job)
    await db_session.flush()
    await db_session.commit()
    return job.id


@pytest.mark.asyncio
async def test_claim_moves_queued_to_sending(db_session):
    job_id = await _make_job(db_session)
    store = SQLAlchemyJobStore(db_session)

    claimed = await store.claim(job_id, "worker_a", attempt=1)
    await db_session.commit()

    assert claimed is not None
    assert claimed.send_status == "sending"
    assert claimed.attempt == 1


@pytest.mark.asyncio
async def test_claim_on_a_terminal_job_returns_none(db_session):
    job_id = await _make_job(db_session, send_status="sent", provider_message_id="msg_1")
    store = SQLAlchemyJobStore(db_session)

    claimed = await store.claim(job_id, "worker_a", attempt=1)
    assert claimed is None


@pytest.mark.asyncio
async def test_claim_can_reclaim_a_sending_row_after_a_crash(db_session):
    """The guard's whole point: SENDING is a valid predecessor of itself, so a
    retry after a crash mid-send can re-claim its own row."""
    job_id = await _make_job(db_session, send_status="sending")
    store = SQLAlchemyJobStore(db_session)

    claimed = await store.claim(job_id, "worker_b", attempt=2)
    assert claimed is not None
    assert claimed.attempt == 2


@pytest.mark.asyncio
async def test_mark_sent_records_the_message_id(db_session):
    from datetime import UTC, datetime

    job_id = await _make_job(db_session, send_status="sending")
    store = SQLAlchemyJobStore(db_session)

    adopted = await store.mark_sent(job_id, "msg_abc123", datetime.now(UTC))
    await db_session.commit()

    assert adopted == 0  # no orphan webhook events waiting
    job = await store.get(job_id)
    assert job.send_status == "sent"
    assert job.provider_message_id == "msg_abc123"


@pytest.mark.asyncio
async def test_mark_sent_adopts_a_waiting_orphan_webhook_event(db_session):
    """The backward half of the orphan-event fix: a webhook that arrived
    before we knew the message id gets claimed the moment we learn it."""
    from datetime import UTC, datetime

    from packages.shared.models import ProviderEvent

    job_id = await _make_job(db_session, send_status="sending")

    orphan = ProviderEvent(
        provider_event_id="evt_1", provider_message_id="msg_xyz", event_type="sent",
        occurred_at=datetime.now(UTC), raw={}, email_job_id=None,
    )
    db_session.add(orphan)
    await db_session.commit()

    store = SQLAlchemyJobStore(db_session)
    adopted = await store.mark_sent(job_id, "msg_xyz", datetime.now(UTC))
    await db_session.commit()

    assert adopted == 1
    await db_session.refresh(orphan)
    assert orphan.email_job_id == job_id


@pytest.mark.asyncio
async def test_mark_transient_records_the_error_and_status(db_session):
    job_id = await _make_job(db_session, send_status="sending")
    store = SQLAlchemyJobStore(db_session)

    await store.mark_transient(job_id, "503 service unavailable")
    await db_session.commit()

    job = await store.get(job_id)
    assert job.send_status == "failed_transient"


@pytest.mark.asyncio
async def test_mark_permanent_records_reason_and_error(db_session):
    job_id = await _make_job(db_session, send_status="sending")
    store = SQLAlchemyJobStore(db_session)

    await store.mark_permanent(job_id, "invalid recipient", "invalid_address")
    await db_session.commit()

    job = await store.get(job_id)
    assert job.send_status == "failed_permanent"


@pytest.mark.asyncio
async def test_two_concurrent_claims_only_one_wins(db_session):
    """The conditional UPDATE is the mutex — the second claim on an already
    'sending' row from a DIFFERENT attempt number should still succeed (it's a
    valid predecessor), but claiming a 'sent' row must fail for both."""
    job_id = await _make_job(db_session, send_status="sent", provider_message_id="msg_done")
    store = SQLAlchemyJobStore(db_session)

    first = await store.claim(job_id, "worker_a", attempt=1)
    second = await store.claim(job_id, "worker_b", attempt=1)

    assert first is None
    assert second is None

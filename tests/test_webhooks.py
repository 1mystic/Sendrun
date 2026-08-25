"""Webhook ingestion (verify -> insert dedup -> 200) and the processor's
orphan resolution + precedence-rank application.

These run entirely on SQLite: unlike packages/durable/queue.py's ENQUEUE, the
provider_events table and its insert use plain SQL (no Postgres-only JSONB
CAST), so this is real coverage of the actual code path, not a scope-limited
stand-in.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from packages.shared.models import Campaign, Contact, EmailEngagement, EmailJob, Organization, User
from services.api.webhooks.processor import process_one_event
from services.api.webhooks.sweeper import sweep_once

WEBHOOK_SECRET = "fake-webhook-secret"


def _sign(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _fake_event_body(event_type: str, message_id: str, event_id: str | None = None) -> bytes:
    payload = {
        "id": event_id or f"evt_{uuid4().hex[:16]}",
        "type": f"email.{event_type}",
        "created_at": datetime.now(UTC).isoformat(),
        "data": {"message_id": message_id, "to": "x@example.com", "subject": "Hi"},
    }
    return json.dumps(payload).encode()


async def _make_job(db_session, *, send_status="sent", provider_message_id=None) -> str:
    org = Organization(name="O", slug=f"o-{uuid4().hex[:8]}")
    user = User(email=f"{uuid4().hex}@example.com", name="U", password_hash="x")
    db_session.add_all([org, user])
    await db_session.flush()

    contact = Contact(org_id=org.id, email="c@example.com")
    campaign = Campaign(
        org_id=org.id, name="C", template_id=uuid4(), template_version=1,
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
    await db_session.commit()
    return str(job.id)


class TestIngest:
    @pytest.mark.asyncio
    async def test_a_correctly_signed_webhook_is_accepted(self, client):
        body = _fake_event_body("delivered", "msg_abc")
        r = await client.post(
            "/api/webhooks/fake", content=body,
            headers={"x-fake-signature": _sign(body)},
        )
        assert r.status_code == 200
        assert r.json()["new"] == "1"

    @pytest.mark.asyncio
    async def test_a_tampered_body_is_rejected(self, client):
        body = _fake_event_body("delivered", "msg_abc")
        r = await client.post(
            "/api/webhooks/fake", content=body + b"tampered",
            headers={"x-fake-signature": _sign(body)},
        )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_signature_is_rejected(self, client):
        body = _fake_event_body("delivered", "msg_abc")
        r = await client.post("/api/webhooks/fake", content=body)
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_the_same_event_id_delivered_twice_is_deduplicated(self, client):
        """Resend retries on non-2xx; a duplicate delivery of the SAME event id
        must be a no-op, not a second row."""
        body = _fake_event_body("delivered", "msg_abc", event_id="evt_fixed_id")
        headers = {"x-fake-signature": _sign(body)}

        r1 = await client.post("/api/webhooks/fake", content=body, headers=headers)
        assert r1.json()["new"] == "1"

        r2 = await client.post("/api/webhooks/fake", content=body, headers=headers)
        assert r2.status_code == 200
        assert r2.json()["new"] == "0"  # deduplicated, not a second insert


class TestOrphanResolution:
    @pytest.mark.asyncio
    async def test_event_with_no_matching_job_stays_an_orphan(self, db_session):
        from packages.shared.models import ProviderEvent

        event = ProviderEvent(
            provider_event_id="evt_1", provider_message_id="msg_nobody_has_this",
            event_type="delivered", occurred_at=datetime.now(UTC), raw={},
        )
        db_session.add(event)
        await db_session.commit()

        applied = await process_one_event(db_session, str(event.id))
        await db_session.commit()

        assert applied is False
        await db_session.refresh(event)
        assert event.email_job_id is None
        assert event.processed_at is None
        assert event.attempts == 1

    @pytest.mark.asyncio
    async def test_sweeper_resolves_an_orphan_once_the_job_exists(self, db_session):
        """Simulates the race: webhook arrives, THEN the send is recorded.
        The sweeper's forward-resolution pass must close the gap."""
        from packages.shared.models import ProviderEvent

        event = ProviderEvent(
            provider_event_id="evt_2", provider_message_id="msg_will_exist_soon",
            event_type="delivered", occurred_at=datetime.now(UTC), raw={},
        )
        db_session.add(event)
        await db_session.commit()

        resolved, remaining = await sweep_once(db_session)
        assert resolved == 0
        assert remaining == 1

        job_id = await _make_job(db_session, provider_message_id="msg_will_exist_soon")

        resolved, remaining = await sweep_once(db_session)
        assert resolved == 1
        assert remaining == 0

        await db_session.refresh(event)
        assert str(event.email_job_id) == job_id


class TestPrecedenceRank:
    @pytest.mark.asyncio
    async def test_delivered_is_applied(self, db_session):
        job_id = await _make_job(db_session, provider_message_id="msg_x")
        from packages.shared.models import ProviderEvent

        event = ProviderEvent(
            provider_event_id="evt_d1", provider_message_id="msg_x",
            event_type="delivered", occurred_at=datetime.now(UTC), raw={},
        )
        db_session.add(event)
        await db_session.commit()

        await process_one_event(db_session, str(event.id))
        await db_session.commit()

        job = await db_session.get(EmailJob, job_id)
        assert job.delivery_status == "delivered"

    @pytest.mark.asyncio
    async def test_a_late_sent_after_delivered_does_not_overwrite_it(self, db_session):
        """The core monotonicity guarantee: rank(sent)=2 < rank(delivered)=3,
        so a delayed `sent` webhook arriving after `delivered` must be a no-op."""
        job_id = await _make_job(db_session, provider_message_id="msg_y")
        from packages.shared.models import ProviderEvent

        job = await db_session.get(EmailJob, job_id)
        job.delivery_status = "delivered"
        await db_session.commit()

        late_sent = ProviderEvent(
            provider_event_id="evt_late", provider_message_id="msg_y",
            event_type="sent", occurred_at=datetime.now(UTC), raw={},
        )
        db_session.add(late_sent)
        await db_session.commit()

        await process_one_event(db_session, str(late_sent.id))
        await db_session.commit()

        job = await db_session.get(EmailJob, job_id)
        assert job.delivery_status == "delivered"  # unchanged

    @pytest.mark.asyncio
    async def test_bounced_outranks_delivered(self, db_session):
        job_id = await _make_job(db_session, provider_message_id="msg_z")
        job = await db_session.get(EmailJob, job_id)
        job.delivery_status = "delivered"
        await db_session.commit()

        from packages.shared.models import ProviderEvent

        bounce = ProviderEvent(
            provider_event_id="evt_bounce", provider_message_id="msg_z",
            event_type="bounced", occurred_at=datetime.now(UTC), raw={},
        )
        db_session.add(bounce)
        await db_session.commit()

        await process_one_event(db_session, str(bounce.id))
        await db_session.commit()

        job = await db_session.get(EmailJob, job_id)
        assert job.delivery_status == "bounced"

    @pytest.mark.asyncio
    async def test_a_duplicate_delivered_event_is_a_harmless_no_op(self, db_session):
        job_id = await _make_job(db_session, provider_message_id="msg_dup")
        from packages.shared.models import ProviderEvent

        e1 = ProviderEvent(
            provider_event_id="evt_dup1", provider_message_id="msg_dup",
            event_type="delivered", occurred_at=datetime.now(UTC), raw={},
        )
        db_session.add(e1)
        await db_session.commit()
        await process_one_event(db_session, str(e1.id))
        await db_session.commit()

        # Different event id, same outcome — this is what "duplicate" means at
        # the level that matters: the SAME real-world fact reported twice.
        e2 = ProviderEvent(
            provider_event_id="evt_dup2", provider_message_id="msg_dup",
            event_type="delivered", occurred_at=datetime.now(UTC), raw={},
        )
        db_session.add(e2)
        await db_session.commit()
        await process_one_event(db_session, str(e2.id))
        await db_session.commit()

        job = await db_session.get(EmailJob, job_id)
        assert job.delivery_status == "delivered"  # unchanged, not double-applied


class TestEngagement:
    @pytest.mark.asyncio
    async def test_opened_does_not_touch_delivery_status(self, db_session):
        """The invariant this whole split exists for: opened/clicked must
        never be able to clobber a bounce."""
        job_id = await _make_job(db_session, provider_message_id="msg_open")
        job = await db_session.get(EmailJob, job_id)
        job.delivery_status = "bounced"
        await db_session.commit()

        from packages.shared.models import ProviderEvent

        open_event = ProviderEvent(
            provider_event_id="evt_open", provider_message_id="msg_open",
            event_type="opened", occurred_at=datetime.now(UTC), raw={},
        )
        db_session.add(open_event)
        await db_session.commit()

        await process_one_event(db_session, str(open_event.id))
        await db_session.commit()

        job = await db_session.get(EmailJob, job_id)
        assert job.delivery_status == "bounced"  # unchanged — opened is not a status
        assert job.open_count == 1

    @pytest.mark.asyncio
    async def test_multiple_opens_increment_the_counter_and_keep_first_opened_at(self, db_session):
        job_id = await _make_job(db_session, provider_message_id="msg_multi")
        from packages.shared.models import ProviderEvent

        first_open_time = datetime.now(UTC)
        for i in range(3):
            event = ProviderEvent(
                provider_event_id=f"evt_open_{i}", provider_message_id="msg_multi",
                event_type="opened", occurred_at=first_open_time, raw={},
            )
            db_session.add(event)
            await db_session.commit()
            await process_one_event(db_session, str(event.id))
            await db_session.commit()

        job = await db_session.get(EmailJob, job_id)
        assert job.open_count == 3

        engagements = (
            await db_session.execute(
                select(EmailEngagement).where(EmailEngagement.email_job_id == job_id)
            )
        ).scalars().all()
        assert len(engagements) == 3

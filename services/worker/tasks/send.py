"""The three-phase idempotent send. This is the core of the durability thesis.

The whole system exists to make this one guarantee true:

    A send is attempted at-least-once by the queue, and lands at-most-once at the
    provider. Together: effectively-once.

The queue gives at-least-once (a lease expires, the task is re-picked). The provider's
idempotency key gives at-most-once. Neither alone is sufficient.

## The three phases

    1. CLAIM    conditional UPDATE. Wins the row or discovers someone else has it.
    2. SEND     provider call, carrying the idempotency key.
    3. RECORD   write message_id, and adopt any webhooks that arrived early.

Order matters enormously. The claim happens BEFORE the provider call so that a crash
between phases is always detectable afterwards: if we come back and the row is already
`sending` with a message_id, we know phase 2 completed and phase 3 did not.

## The failure cases, and why each is safe

| What happened                          | What the retry does                        |
|----------------------------------------|--------------------------------------------|
| Crash before phase 2                    | Row is `sending`, no message_id. Re-send.  |
|                                         | Provider has never seen the key. Sends once.|
| Provider accepted, crash before phase 3 | Row is `sending`, no message_id. Re-send.  |
|                                         | Provider recognises the key, returns the   |
|                                         | ORIGINAL message_id. No second email.      |
| Provider accepted, network timed out    | Identical to the above. This is exactly    |
|                                         | what the idempotency key is for.           |
| Two workers race the same row           | The conditional UPDATE is the mutex. The   |
|                                         | loser reads the winner's result.           |

Note the second row: we cannot distinguish "provider never saw it" from "provider saw
it but we lost the response". We do not have to. We re-send in both cases and let the
idempotency key decide - which is why the key must be stable across attempts, and why
it is `email_job_id` rather than a content hash.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from packages.durable.queue import PermanentTaskError, TransientTaskError
from packages.shared.providers.base import (
    EmailProvider,
    PermanentProviderError,
    SendRequest,
    TransientProviderError,
)
from packages.shared.transitions import SendStatus

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    """What the claim returned. `provider_message_id` non-null means phase 2 already ran."""

    id: UUID
    send_status: SendStatus
    provider_message_id: str | None
    attempt: int
    to_addr: str
    subject: str
    html: str
    text: str | None


@dataclass(frozen=True, slots=True)
class SendOutcome:
    email_job_id: UUID
    provider_message_id: str | None
    status: SendStatus
    resent: bool = False
    error: str | None = None


class JobStore(Protocol):
    """The DB operations the send needs. A Protocol so tests can supply a fake."""

    async def claim(self, job_id: UUID, worker: str, attempt: int) -> ClaimedJob | None: ...
    async def mark_sent(self, job_id: UUID, message_id: str, at: datetime) -> int: ...
    async def mark_transient(self, job_id: UUID, error: str) -> None: ...
    async def mark_permanent(self, job_id: UUID, error: str, reason: str) -> None: ...
    async def get(self, job_id: UUID) -> ClaimedJob | None: ...


# ── SQL, for reference by the concrete store ─────────────────────────────────

# PHASE 1. The guard is the mutex: only a row in one of these three states can be
# claimed. A row already `sent`/`cancelled`/`skipped` matches nothing and returns None,
# which the caller treats as "already done", not as an error.
#
# `sending` is deliberately an allowed predecessor - a worker that crashed mid-send left
# the row in `sending`, and the retry must be able to re-claim it. Without this the row
# would be stranded forever.
CLAIM_SQL = """
UPDATE email_jobs SET
    send_status = 'sending',
    attempt     = :attempt,
    claimed_by  = :worker,
    claimed_at  = now(),
    updated_at  = now()
WHERE id = :id
  AND send_status IN ('queued', 'sending', 'failed_transient')
RETURNING id, send_status, provider_message_id, attempt,
          to_addr, subject, html_body, text_body;
"""

# PHASE 3. Records the send AND adopts orphan webhooks in one statement.
#
# The adoption is the backward half of the orphan-event fix: events that arrived before
# we knew the message id are sitting in provider_events with email_job_id IS NULL. The
# moment we learn the id, we claim them - so the common case resolves in milliseconds
# instead of waiting for the sweeper.
MARK_SENT_SQL = """
WITH j AS (
    UPDATE email_jobs SET
        send_status         = 'sent',
        provider_message_id = :message_id,
        sent_at             = :sent_at,
        updated_at          = now()
    WHERE id = :id AND send_status = 'sending'
    RETURNING id
)
UPDATE provider_events SET email_job_id = (SELECT id FROM j)
WHERE provider_message_id = :message_id
  AND email_job_id IS NULL
  AND EXISTS (SELECT 1 FROM j)
RETURNING id;
"""


async def send_email_task(
    payload: dict[str, Any],
    *,
    store: JobStore,
    provider: EmailProvider,
    worker_id: str,
    from_addr: str,
    attempt: int = 1,
) -> SendOutcome:
    """Execute one email send. Safe to call any number of times for the same job."""

    job_id = UUID(str(payload["email_job_id"]))

    # ── PHASE 1: CLAIM ──────────────────────────────────────────────────
    claimed = await store.claim(job_id, worker_id, attempt)

    if claimed is None:
        # Terminal already. Another worker finished it, or it was cancelled while we
        # were queued. Not an error - report the settled state.
        existing = await store.get(job_id)
        if existing is None:
            raise PermanentTaskError(f"email job {job_id} does not exist")
        log.info("job.already_terminal", extra={"job": str(job_id), "status": existing.send_status})
        return SendOutcome(job_id, existing.provider_message_id, existing.send_status)

    if claimed.provider_message_id:
        # We crashed after the provider accepted but before recording it. The message
        # went out; do not send it again. Just complete phase 3.
        log.warning("job.recovering_unrecorded_send", extra={"job": str(job_id)})
        await store.mark_sent(job_id, claimed.provider_message_id, datetime.now(UTC))
        return SendOutcome(job_id, claimed.provider_message_id, SendStatus.SENT)

    # ── PHASE 2: SEND ───────────────────────────────────────────────────
    # The idempotency key is the job id: stable across every attempt of THIS job, and
    # different for a deliberate resend (which creates a new job row with a new id).
    request = SendRequest(
        idempotency_key=str(job_id),
        to=claimed.to_addr,
        from_addr=from_addr,
        subject=claimed.subject,
        html=claimed.html,
        text=claimed.text,
        tags={"email_job_id": str(job_id), "campaign_id": str(payload.get("campaign_id", ""))},
    )

    try:
        response = await provider.send(request)

    except TransientProviderError as e:
        # Record the reason, then re-raise so the queue reschedules with backoff.
        # The row stays `failed_transient`, which is a valid claim predecessor.
        await store.mark_transient(job_id, str(e))
        raise TransientTaskError(str(e)) from e

    except PermanentProviderError as e:
        # Retrying cannot help. Burn the job, do not consume the retry budget.
        await store.mark_permanent(job_id, str(e), e.reason)
        raise PermanentTaskError(str(e)) from e

    # ── PHASE 3: RECORD ─────────────────────────────────────────────────
    # If we crash here, the retry re-enters phase 2, the provider recognises the key,
    # and returns this same message id. Convergent either way.
    adopted = await store.mark_sent(job_id, response.provider_message_id, response.accepted_at)

    if response.idempotent_replay:
        log.info("job.idempotent_replay", extra={"job": str(job_id)})

    if adopted:
        log.info("job.adopted_orphan_events", extra={"job": str(job_id), "n": adopted})

    return SendOutcome(
        job_id,
        response.provider_message_id,
        SendStatus.SENT,
        resent=response.idempotent_replay,
    )

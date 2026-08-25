"""The test that defends the thesis.

If this test passes, the central claim of the project is true. If it is ever skipped or
weakened, the project no longer demonstrates what it says it demonstrates.

    Kill workers mid-campaign, at arbitrary points, repeatedly.
    Every job still reaches a terminal state, and no recipient is emailed twice.

The crash points are chosen adversarially - specifically the window between the provider
accepting a message and us recording that it did, which is the one place a naive
implementation silently double-sends.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from packages.durable.queue import PermanentTaskError, RetryPolicy, TransientTaskError
from packages.shared.providers.fake import ChaosConfig, FakeEmailProvider
from packages.shared.transitions import SendStatus
from services.worker.tasks.send import ClaimedJob, send_email_task


class WorkerCrash(Exception):
    """Simulates a SIGKILL: raised from inside the store, so no cleanup runs."""


class InMemoryJobStore:
    """A job store that can be told to die at a precise moment.

    Mirrors the real SQL guards exactly - especially the claim predecessor set, which is
    what makes a crashed row re-claimable instead of stranded.
    """

    def __init__(self, jobs: dict[UUID, ClaimedJob]) -> None:
        self.jobs = jobs
        self.crash_on_mark_sent: set[UUID] = set()
        self.mark_sent_calls = 0
        self.claims: list[UUID] = []

    async def claim(self, job_id: UUID, worker: str, attempt: int) -> ClaimedJob | None:
        job = self.jobs.get(job_id)
        if job is None:
            return None
        # The guard, exactly as in CLAIM_SQL.
        if job.send_status not in (
            SendStatus.QUEUED, SendStatus.SENDING, SendStatus.FAILED_TRANSIENT
        ):
            return None
        self.claims.append(job_id)
        self.jobs[job_id] = replace(job, send_status=SendStatus.SENDING, attempt=attempt)
        return self.jobs[job_id]

    async def mark_sent(self, job_id: UUID, message_id: str, at: datetime) -> int:
        # Crash AFTER the provider accepted but BEFORE we persist the message id.
        # This is the dangerous window; a naive implementation double-sends here.
        if job_id in self.crash_on_mark_sent:
            self.crash_on_mark_sent.discard(job_id)
            raise WorkerCrash(f"worker killed while recording {job_id}")
        self.mark_sent_calls += 1
        job = self.jobs[job_id]
        if job.send_status is not SendStatus.SENDING:
            return 0
        self.jobs[job_id] = replace(
            job, send_status=SendStatus.SENT, provider_message_id=message_id
        )
        return 0

    async def mark_transient(self, job_id: UUID, error: str) -> None:
        job = self.jobs[job_id]
        self.jobs[job_id] = replace(job, send_status=SendStatus.FAILED_TRANSIENT)

    async def mark_permanent(self, job_id: UUID, error: str, reason: str) -> None:
        job = self.jobs[job_id]
        self.jobs[job_id] = replace(job, send_status=SendStatus.FAILED_PERMANENT)

    async def get(self, job_id: UUID) -> ClaimedJob | None:
        return self.jobs.get(job_id)


def make_jobs(n: int) -> dict[UUID, ClaimedJob]:
    jobs = {}
    for i in range(n):
        jid = uuid4()
        jobs[jid] = ClaimedJob(
            id=jid,
            send_status=SendStatus.QUEUED,
            provider_message_id=None,
            attempt=0,
            to_addr=f"person{i}@example.com",
            subject=f"Hello {i}",
            html=f"<p>Hello {i}</p>",
            text=f"Hello {i}",
        )
    return jobs


async def run_job_with_retries(
    job_id: UUID, store: InMemoryJobStore, provider: FakeEmailProvider,
    *, worker: str = "w1", max_attempts: int = 6,
) -> SendStatus:
    """Drive one job the way the queue would: retry transient failures and crashes."""
    policy = RetryPolicy(max_attempts=max_attempts, initial_seconds=0, jitter=False)
    for attempt in range(1, max_attempts + 1):
        try:
            outcome = await send_email_task(
                {"email_job_id": str(job_id), "campaign_id": "c1"},
                store=store, provider=provider,
                worker_id=f"{worker}-a{attempt}",
                from_addr="hello@sendrun.test", attempt=attempt,
            )
            return outcome.status
        except PermanentTaskError:
            return SendStatus.FAILED_PERMANENT
        except (TransientTaskError, WorkerCrash):
            if policy.exhausted(attempt):
                return SendStatus.FAILED_TRANSIENT
            continue
    return SendStatus.FAILED_TRANSIENT


# ═════════════════════════════════════════════════════════════════════════════
# The invariant
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_crash_between_provider_accept_and_record_does_not_duplicate():
    """THE test. Crash in the dangerous window; assert the email is sent exactly once."""
    jobs = make_jobs(1)
    job_id = next(iter(jobs))
    store = InMemoryJobStore(jobs)
    provider = FakeEmailProvider(ChaosConfig.quiet())

    # Kill the worker after the provider accepts, before we persist the message id.
    store.crash_on_mark_sent.add(job_id)

    status = await run_job_with_retries(job_id, store, provider)

    assert status is SendStatus.SENT
    # Entered send() twice - once before the crash, once on the retry.
    assert provider.send_calls == 2
    # But the provider only ever created ONE message.
    assert provider.provider_sends == 1, "the recipient was emailed twice"
    assert provider.idempotent_replays == 1, "the retry should have hit the idempotency cache"
    assert provider.duplicate_sends == 0


@pytest.mark.asyncio
async def test_many_jobs_with_random_crashes_never_duplicate():
    """500 jobs, a third of them crashed mid-record. Zero duplicates, all terminal."""
    import random
    rng = random.Random(1234)

    jobs = make_jobs(500)
    store = InMemoryJobStore(jobs)
    provider = FakeEmailProvider(ChaosConfig.quiet())

    victims = {jid for jid in jobs if rng.random() < 0.33}
    store.crash_on_mark_sent |= victims

    results = await asyncio.gather(*[
        run_job_with_retries(jid, store, provider) for jid in jobs
    ])

    assert all(s is SendStatus.SENT for s in results)
    assert provider.provider_sends == 500, "one message per job, no more"
    assert provider.idempotent_replays == len(victims)
    assert provider.duplicate_sends == 0
    assert provider.send_calls == 500 + len(victims)


@pytest.mark.asyncio
async def test_transient_failures_retry_then_succeed_without_duplicating():
    """Chaos on. Transient errors retry; the totals still have to add up."""
    jobs = make_jobs(200)
    store = InMemoryJobStore(jobs)
    chaos = ChaosConfig(
        transient_error_rate=0.25, rate_limit_rate=0.0, permanent_error_rate=0.0,
        hard_bounce_rate=0.0, soft_bounce_rate=0.0, complaint_rate=0.0,
        latency_ms=(0, 0), webhook_delay_ms=(0, 0), webhook_before_send_ack_rate=0.0,
        seed=7,
    )
    provider = FakeEmailProvider(chaos)

    results = await asyncio.gather(*[
        run_job_with_retries(jid, store, provider) for jid in jobs
    ])

    sent = [s for s in results if s is SendStatus.SENT]
    assert len(sent) == 200, "every job should eventually send"
    assert provider.provider_sends == 200
    assert provider.duplicate_sends == 0


@pytest.mark.asyncio
async def test_claim_is_a_mutex_between_concurrent_workers():
    """Two workers racing one job: only one send happens."""
    jobs = make_jobs(1)
    job_id = next(iter(jobs))
    store = InMemoryJobStore(jobs)
    provider = FakeEmailProvider(ChaosConfig.quiet())

    a, b = await asyncio.gather(
        run_job_with_retries(job_id, store, provider, worker="wA"),
        run_job_with_retries(job_id, store, provider, worker="wB"),
    )

    assert a is SendStatus.SENT and b is SendStatus.SENT
    assert provider.provider_sends == 1, "concurrent workers double-sent"
    assert provider.duplicate_sends == 0


@pytest.mark.asyncio
async def test_terminal_job_is_never_resent():
    """Re-running an already-sent job is a no-op, not a second email."""
    jobs = make_jobs(1)
    job_id = next(iter(jobs))
    store = InMemoryJobStore(jobs)
    provider = FakeEmailProvider(ChaosConfig.quiet())

    assert await run_job_with_retries(job_id, store, provider) is SendStatus.SENT
    assert provider.provider_sends == 1

    for _ in range(5):
        assert await run_job_with_retries(job_id, store, provider) is SendStatus.SENT

    assert provider.provider_sends == 1, "a terminal job was re-sent"
    assert provider.send_calls == 1, "send() should not even be entered again"


@pytest.mark.asyncio
async def test_permanent_error_does_not_retry():
    """A 4xx burns the job immediately rather than consuming the retry budget."""
    jobs = make_jobs(1)
    job_id = next(iter(jobs))
    store = InMemoryJobStore(jobs)
    provider = FakeEmailProvider(ChaosConfig(
        permanent_error_rate=1.0, transient_error_rate=0.0, rate_limit_rate=0.0,
        latency_ms=(0, 0), seed=3,
    ))

    status = await run_job_with_retries(job_id, store, provider)

    assert status is SendStatus.FAILED_PERMANENT
    assert provider.send_calls == 1, "a permanent error must not be retried"
    assert provider.provider_sends == 0

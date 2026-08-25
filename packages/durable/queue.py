"""The durable task queue - the intellectual centre of Sendrun.

This is a from-scratch implementation of the primitives a workflow engine provides:
leasing, at-least-once delivery, retry with backoff, crash recovery, and a dead-letter
queue. Idempotency at the provider boundary converts at-least-once into effectively-once.

We built this rather than using Temporal because Temporal Cloud has no free tier and
self-hosting it needs Docker. Be honest about what this does NOT have: no event-sourced
replay, no cross-process determinism guarantees, no visibility store, no workflow-as-code
durability. It is a durable *task* queue, not a durable *execution* engine.

## How crash recovery works

A worker does not delete a task when it picks it up - it takes a time-boxed *lease*:

    status='leased', lease_owner='worker_a', lease_until=now()+30s

If that worker dies, nobody rolls anything back. The lease simply stops being renewed.
The reaper then finds tasks whose `lease_until` has passed and returns them to `pending`:

    UPDATE tasks SET status='pending' WHERE status='leased' AND lease_until < now()

That single statement is the entire durability guarantee. A killed worker's tasks are
re-picked by another worker within one lease period. Because every side effect downstream
carries an idempotency key, re-execution is safe.

## Why FOR UPDATE SKIP LOCKED

Many workers poll the same table concurrently. `SKIP LOCKED` lets each transaction claim
rows no one else has locked, without blocking. Without it, workers serialize behind one
another and throughput collapses to a single worker's rate.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Final
from uuid import UUID, uuid4


def utcnow() -> datetime:
    return datetime.now(UTC)


class TaskStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD = "dead"  # exhausted retries -> dead-letter queue


TASK_TERMINAL: Final[frozenset[TaskStatus]] = frozenset({
    TaskStatus.SUCCEEDED,
    TaskStatus.CANCELLED,
    TaskStatus.DEAD,
})


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Exponential backoff with full jitter.

    Full jitter (a uniform draw over the whole interval, not a small perturbation of it)
    is what prevents a thundering herd: when a provider outage fails 500 tasks at the
    same instant, undithered backoff would retry all 500 simultaneously and re-trigger
    the outage. See AWS's "Exponential Backoff and Jitter".
    """

    max_attempts: int = 5
    initial_seconds: float = 2.0
    multiplier: float = 2.0
    max_seconds: float = 300.0
    jitter: bool = True

    def delay_for(self, attempt: int, rng: random.Random | None = None) -> float:
        """Delay before `attempt` (1-based: attempt=1 is the first retry)."""
        if attempt < 1:
            return 0.0
        raw = self.initial_seconds * (self.multiplier ** (attempt - 1))
        capped = min(raw, self.max_seconds)
        if not self.jitter:
            return capped
        return (rng or random).uniform(0.0, capped)

    def exhausted(self, attempt: int) -> bool:
        return attempt >= self.max_attempts


@dataclass(slots=True)
class Task:
    """A unit of durable work.

    `idempotency_key` is UNIQUE where present. Enqueueing the same key twice is a no-op
    rather than an error, which makes the enqueue path itself safe to retry - important
    because the janitor may re-drive a campaign whose enqueue was interrupted.
    """

    id: UUID = field(default_factory=uuid4)
    queue: str = "default"
    task_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None

    status: TaskStatus = TaskStatus.PENDING
    run_after: datetime = field(default_factory=utcnow)
    lease_until: datetime | None = None
    lease_owner: str | None = None

    attempt: int = 0
    max_attempts: int = 5
    last_error: str | None = None

    parent_id: UUID | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def is_terminal(self) -> bool:
        return self.status in TASK_TERMINAL

    def lease_expired(self, now: datetime | None = None) -> bool:
        if self.status is not TaskStatus.LEASED or self.lease_until is None:
            return False
        return self.lease_until < (now or utcnow())


# ─────────────────────────────────────────────────────────────────────────────
# SQL
#
# Kept as named constants rather than built inline so the concurrency-critical
# statements can be read, reviewed, and tested in one place.
# ─────────────────────────────────────────────────────────────────────────────

CREATE_TASKS_TABLE: Final = """
CREATE TABLE IF NOT EXISTS tasks (
    id              UUID PRIMARY KEY,
    queue           TEXT        NOT NULL,
    task_type       TEXT        NOT NULL,
    payload         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key TEXT UNIQUE,
    status          TEXT        NOT NULL DEFAULT 'pending',
    run_after       TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_until     TIMESTAMPTZ,
    lease_owner     TEXT,
    attempt         INT         NOT NULL DEFAULT 0,
    max_attempts    INT         NOT NULL DEFAULT 5,
    last_error      TEXT,
    parent_id       UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The dequeue index. Partial on status='pending' so it stays small and hot
-- regardless of how many completed tasks accumulate in the table.
CREATE INDEX IF NOT EXISTS ix_tasks_dequeue
    ON tasks (queue, run_after)
    WHERE status = 'pending';

-- The reaper index. Also partial: only leased rows can ever expire.
CREATE INDEX IF NOT EXISTS ix_tasks_reap
    ON tasks (lease_until)
    WHERE status = 'leased';

CREATE INDEX IF NOT EXISTS ix_tasks_parent ON tasks (parent_id);
"""

# Claim up to :limit runnable tasks atomically.
#
# ORDER BY run_after, created_at gives FIFO within a due time, so a task that has been
# waiting does not starve behind newly-enqueued work.
#
# SKIP LOCKED is what makes this safe under N concurrent workers: each transaction takes
# only rows nobody else holds, and never blocks waiting for a peer.
DEQUEUE: Final = """
UPDATE tasks SET
    status      = 'leased',
    lease_owner = :owner,
    lease_until = now() + make_interval(secs => :lease_seconds),
    attempt     = attempt + 1,
    updated_at  = now()
WHERE id IN (
    SELECT id FROM tasks
    WHERE queue = :queue
      AND status = 'pending'
      AND run_after <= now()
    ORDER BY run_after, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :limit
)
RETURNING *;
"""

# Extend a lease for a long-running task. Guarded on lease_owner so a worker that was
# already reaped (its task now belongs to someone else) cannot resurrect its claim and
# create two concurrent executors.
HEARTBEAT: Final = """
UPDATE tasks SET
    lease_until = now() + make_interval(secs => :lease_seconds),
    updated_at  = now()
WHERE id = :id AND status = 'leased' AND lease_owner = :owner
RETURNING id;
"""

# Crash recovery. The entire durability guarantee is this statement.
REAP_EXPIRED: Final = """
UPDATE tasks SET
    status      = 'pending',
    lease_owner = NULL,
    lease_until = NULL,
    last_error  = COALESCE(last_error, 'lease expired; worker presumed dead'),
    updated_at  = now()
WHERE status = 'leased' AND lease_until < now()
RETURNING id, queue, task_type, attempt;
"""

COMPLETE: Final = """
UPDATE tasks SET
    status = 'succeeded', lease_owner = NULL, lease_until = NULL, updated_at = now()
WHERE id = :id AND status = 'leased' AND lease_owner = :owner
RETURNING id;
"""

# A transient failure. The task returns to `pending` with a future run_after, so the
# dequeue index simply will not see it until the backoff has elapsed - no sleeping
# worker, no in-memory timer to lose on restart.
RETRY_LATER: Final = """
UPDATE tasks SET
    status      = 'pending',
    lease_owner = NULL,
    lease_until = NULL,
    run_after   = now() + make_interval(secs => :delay_seconds),
    last_error  = :error,
    updated_at  = now()
WHERE id = :id AND status = 'leased' AND lease_owner = :owner
RETURNING id;
"""

# Terminal failure: either non-retryable, or retries exhausted. `dead` is the DLQ -
# rows stay for inspection and manual requeue rather than being deleted.
KILL: Final = """
UPDATE tasks SET
    status = :status, lease_owner = NULL, lease_until = NULL,
    last_error = :error, updated_at = now()
WHERE id = :id AND status = 'leased' AND lease_owner = :owner
RETURNING id;
"""

ENQUEUE: Final = """
INSERT INTO tasks (id, queue, task_type, payload, idempotency_key,
                   run_after, max_attempts, parent_id)
VALUES (:id, :queue, :task_type, CAST(:payload AS JSONB), :idempotency_key,
        :run_after, :max_attempts, :parent_id)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING id;
"""

# Cancel everything not yet started for a parent. Deliberately does NOT touch `leased`
# rows: a send already in flight cannot be recalled, and pretending otherwise would be
# a lie in the UI.
CANCEL_PENDING_CHILDREN: Final = """
UPDATE tasks SET
    status = 'cancelled', lease_owner = NULL, lease_until = NULL, updated_at = now()
WHERE parent_id = :parent_id AND status = 'pending'
RETURNING id;
"""

QUEUE_DEPTH: Final = """
SELECT status, count(*) AS n
FROM tasks
WHERE queue = :queue
GROUP BY status;
"""


# ─────────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────────

class PermanentTaskError(Exception):
    """Raised by a handler when retrying could not possibly help.

    Sends the task straight to `failed` without consuming the retry budget - e.g. an
    invalid email address, or a payload that fails validation.
    """


class TransientTaskError(Exception):
    """Raised by a handler when the failure is expected to be temporary.

    The task is rescheduled with backoff until the retry budget is exhausted, at which
    point it lands in the dead-letter queue.
    """

# `packages/durable/`

The durable task queue — this is why Temporal isn't a dependency. Built from scratch on
Postgres because Temporal Cloud has no free tier ($100/mo minimum) and self-hosting needs
Docker, unavailable in this environment. This is the intellectual centre of the project.

## The guarantee

A worker takes a task by leasing it, not by deleting it:

```sql
status='leased', lease_owner='worker_a', lease_until=now()+30s
```

If that worker is `SIGKILL`ed, nobody rolls anything back — the lease simply stops being
renewed. The reaper finds expired leases and returns them to `pending`:

```sql
UPDATE tasks SET status='pending' WHERE status='leased' AND lease_until < now()
```

That one statement is the entire crash-recovery guarantee. Combined with idempotency at
the call site (`services/worker/tasks/send.py`'s three-phase send), a killed worker's
tasks are re-picked and re-executed safely — the provider recognizes the repeated
idempotency key and returns the original result instead of sending twice.

## Files

| File | What |
|---|---|
| [`queue.py`](queue.py) | SQL text + dataclasses only — deliberately no SQLAlchemy dependency, so the primitives are reviewable without an ORM in the picture. `DEQUEUE`, `REAP_EXPIRED`, `RETRY_LATER`, `KILL`, `COMPLETE`, `ENQUEUE`, `HEARTBEAT`. `RetryPolicy` implements full-jitter exponential backoff. |
| [`worker.py`](worker.py) | `Worker` — the dispatch loop, an *independent* reaper task (so a wedged dispatcher can't stop leases from expiring), heartbeat support for long-running tasks, and graceful SIGTERM shutdown that drains in-flight work without extending leases (a hung handler is exactly what the reaper exists to recover from). |

The actual DB execution — `packages/shared/enqueue.py` and `packages/shared/job_store.py`
— lives outside this package on purpose. `queue.py` stays free of any ORM so its SQL can
be read and reasoned about on its own; the execution layer is where SQLAlchemy enters.

## Why this SQL is Postgres-only, by design

`FOR UPDATE SKIP LOCKED` lets N workers poll the same table concurrently without
serializing behind each other — without it, throughput collapses to one worker's rate.
SQLite has no equivalent. Neither does `make_interval()` or `JSONB`. This is not an
oversight; it's the actual point of the concurrency story, and it means:

- **`SQLAlchemyJobStore`** (`packages/shared/job_store.py`) — the send-activity's
  claim/mark-sent logic — is plain ORM code with no Postgres-only syntax, so it genuinely
  runs and is tested on SQLite (`tests/test_job_store.py`, 8 tests, real coverage).
- **The dequeue/reaper SQL in this package** has *not* been run against a live database
  in this dev environment (no Postgres, no Docker available). What's verified instead is
  the *logic* — lease semantics, backoff math, the claim mutex, retry/DLQ transitions —
  via `InMemoryJobStore` in `tests/test_durability.py`, which mirrors the same guards.

**Before deploying**, create a free Neon Postgres branch and actually run this package's
SQL for real, then the kill-worker demo against the live worker process. See
[`../../NEXT.md`](../../NEXT.md).

## The kill-worker test

`tests/test_durability.py::test_crash_between_provider_accept_and_record_does_not_duplicate`
is the test that proves the project's central claim. It kills a simulated worker in the
one dangerous window — after the provider accepts a send, before we've recorded that it
did — and asserts the email was sent exactly once. This test must never be skipped or
weakened; if it's red, the project's whole thesis is false.

## What this does *not* have, compared to Temporal

Stated honestly rather than glossed over: no event-sourced replay, no cross-process
determinism guarantees, no visibility store, no workflow-as-code durability. This is a
durable *task* queue — leasing, retry, crash recovery, a dead-letter queue — not a durable
*execution engine*. That comparison is worth making explicitly in any writeup of this
project, because it's the honest boundary of what "we built our own Temporal" means here.

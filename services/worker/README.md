# `services/worker/`

The process you `SIGKILL` in the durability demo. Run: `uv run python -m services.worker.main`.

## Files

| File | What |
|---|---|
| [`main.py`](main.py) | Entrypoint. Registers `send_email` → `handle_send_email`, constructs a `Worker` (from `packages/durable/worker.py`) with settings-driven config, runs its poll loop. |
| [`tasks/send.py`](tasks/send.py) | **The single most important file in the repo.** The three-phase idempotent send — this is the code that makes the durability thesis true. |

## The three-phase send

```
1. CLAIM    conditional UPDATE on send_status. Wins the row or discovers
            someone else already has it — a lost race is normal, not an error.
2. SEND     provider call, carrying the job's own id as the idempotency key.
3. RECORD   write provider_message_id, and in the same statement adopt any
            webhook events that arrived before we knew that id.
```

Why this order specifically: claiming *before* the provider call means a crash between
phases is always detectable on retry. If the row comes back `sending` with a
`provider_message_id` already set, phase 2 completed and phase 3 didn't — return the
existing result, don't resend. If it comes back `sending` with no message id, we don't
know whether the provider ever saw the request — re-send in both cases and let the
idempotency key decide, which is exactly what it's for.

| What happened | What the retry does |
|---|---|
| Crash before phase 2 | Provider has never seen the key. Sends once. |
| Provider accepted, crash before phase 3 | Provider recognizes the repeated key, returns the *original* message id. No second email. |
| Provider accepted, network timed out | Identical to the row above — this is precisely what the idempotency key is for. |
| Two workers race the same job | The conditional `UPDATE` in phase 1 is the mutex. The loser reads the winner's result. |

## Why the idempotency key is `email_job_id`, never a content hash

A hash of the email's content would make a *deliberate* resend indistinguishable from a
retry — the provider would see the same key and dedupe it, silently sending nothing. The
key is `email_job_id`, a UUID minted once at campaign launch. A deliberate resend
(`packages/shared/models.EmailJob`'s failed_permanent → new row transition) creates a
*new* job row with a *new* id, which is a *new* key — the provider correctly treats it as
a distinct send.

## Testing note

This code's own logic is proven by `tests/test_durability.py` against
`InMemoryJobStore`. The production glue — `SQLAlchemyJobStore`
(`packages/shared/job_store.py`) — is separately tested against real `EmailJob` rows on
SQLite in `tests/test_job_store.py`, since it's plain ORM code with no Postgres-only SQL.
See [`../../packages/durable/README.md`](../../packages/durable/README.md) for what part
of the stack still needs a real Postgres instance to verify.

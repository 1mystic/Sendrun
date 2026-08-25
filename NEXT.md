# Resume here

## Run it

```bash
cd /home/mystic1/Projects/Sendrun
uv run uvicorn services.api.main:app --reload --port 8000   # backend
npm --prefix apps/web run dev                                 # frontend, :3000
uv run pytest tests/ -v                                        # 85 tests, all green
uv run alembic upgrade head                                    # apply migrations
```

Never `cd` into a subdirectory before a Bash call — the push-guard hook resolves
relative to cwd. Use `--prefix` / absolute paths.

## Verified working

- **85/85 tests pass.** `ruff check packages services tests` clean.
- **Durability** (6 tests) — the crash-in-the-dangerous-window test still holds:
  `provider_sends == 1` while `send_calls == 2` after a simulated worker kill.
- **Phase 1** (16 tests) — auth, tenant isolation, RBAC capability matrix.
- **Phase 2** (25 tests) — sandboxed Jinja2 render pipeline, sandbox-escape attempts
  genuinely rejected (`SecurityError`), personalization-then-sanitize ordering verified
  against a hostile contact field, attachment validation.
- **Phase 3** (16 tests) — campaign create/launch/cancel/progress against real EmailJob
  rows on SQLite. Launch re-resolves recipients rather than trusting the client (a
  suppressed contact is genuinely excluded). Cancel leaves already-`sent` jobs untouched.
- **Phase 4** (12 tests) — webhook verify/dedup/orphan-resolution/precedence-rank, all
  against real `provider_events` rows. The monotonicity guarantee is directly tested: a
  late `sent` after `delivered` is a no-op; `bounced` outranks `delivered`; `opened`
  never touches `delivery_status`.

## IMPORTANT — scope boundary you should know about

**No Postgres or Docker is available in this dev environment.** The durable engine's
real dequeue path (`packages/durable/queue.py`'s `DEQUEUE`/`REAP_EXPIRED`/`ENQUEUE`) uses
`FOR UPDATE SKIP LOCKED`, `make_interval()`, and `JSONB` — all Postgres-only, by design
(that's the whole point of the concurrency story). This SQL has **never been run against
a live database** in this environment. What's actually verified:

- The **logic** (lease semantics, backoff, retry/DLQ, claim-mutex) — via
  `InMemoryJobStore` in `test_durability.py`, exactly as before.
- The **production `SQLAlchemyJobStore`** (`packages/shared/job_store.py`) — this one
  genuinely runs on SQLite (`test_job_store.py`, 8 tests) since it's plain ORM, not raw
  Postgres SQL. This is real coverage.
- Campaign launch fan-out (`test_campaign_launch.py`) — real, up to the enqueue call,
  which is mocked out (see that file's module docstring for exactly where the line is).

**Before deploying**, create a free Neon Postgres branch, point `DATABASE_URL` at it, and
actually run: `alembic upgrade head`, then a full campaign launch, then `packages/durable`
worker.py`'s dispatch/reap loop, then the kill-worker demo end-to-end. None of that has
happened yet — only the parts that don't need Postgres have.

## Two more real bugs found and fixed this session (worth knowing if something regresses)

1. **`services/api/webhooks/ingest.py`'s raw `INSERT INTO provider_events`** didn't set
   `attempts`, and the ORM's `default=0` only applies through the ORM's own insert path —
   raw SQL bypassed it and violated the NOT NULL constraint. Fixed with a real
   `server_default="0"` (see `migrations/versions/e6d7a3706d0f_*.py` — note it uses
   `batch_alter_table`, since SQLite has no `ALTER COLUMN ... SET DEFAULT` at all).
2. `datetime.utcnow()` (deprecated in 3.12) was used in `job_store.py`, `processor.py`,
   and `sweeper.py` — all now `datetime.now(UTC)`.

## Phase 3 — done this session

- `packages/shared/job_store.py` — `SQLAlchemyJobStore`, the production implementation
  of the `JobStore` protocol `send_email_task` expects. Mirrors the SQL guards in
  `queue.py`'s `CLAIM_SQL`/`MARK_SENT_SQL` docs exactly.
- `packages/shared/enqueue.py` — thin execution layer over `queue.py`'s `ENQUEUE`
  constant (queue.py itself stays SQL-text-only, no SQLAlchemy dependency, by design).
- `packages/durable/worker.py` — `Worker`: dispatch loop, independent reaper task,
  heartbeat, graceful SIGTERM shutdown that drains in-flight tasks without extending
  their leases (a hung handler is exactly what the reaper exists to recover from).
- `services/worker/main.py` — entrypoint, registers `send_email` → `send_email_task`.
- `services/api/routers/campaigns.py` — create/launch/cancel/progress. Launch follows
  the outbox-pattern sequence from PLAN.md exactly: LAUNCHING + EmailJob rows in one
  transaction → COMMIT → enqueue tasks → RUNNING. If the process dies between commit and
  RUNNING, a campaign is stuck in LAUNCHING with real job rows and no tasks — see the
  janitor sweep note in that file's docstring (the janitor itself is not yet built; it's
  the next thing needed before this is deploy-safe).

## Phase 4 — done this session

- `services/api/webhooks/ingest.py` — verify → insert (dedup) → 200 → process async.
  Never processes inline; a background `asyncio.create_task` runs after the response.
- `services/api/webhooks/processor.py` — orphan resolution + `DELIVERY_RANK` precedence
  application. `opened`/`clicked` routed to a completely separate path that never
  touches `delivery_status`.
- `services/api/webhooks/sweeper.py` — forward orphan resolution on a timer, same
  independent-loop shape as the durable engine's reaper. Gives up on an event after 24h.
- `services/api/routers/progress.py` — SSE stream, 1s poll of the same aggregate query
  `GET /progress` uses. Closes after 5 consecutive terminal-status ticks.

## Next, in order

1. **The janitor** (`packages/durable/worker.py` or a new `janitor.py`) — finds
   campaigns stuck in `LAUNCHING` past a timeout and re-drives the enqueue step. This is
   the piece that makes the launch sequence's crash window actually safe; without it,
   a launch interrupted between commit and RUNNING never recovers.
2. **A real Neon Postgres branch** — verify `DEQUEUE`/`REAP_EXPIRED`/`ENQUEUE` for real,
   then the kill-worker demo end-to-end, matching `test_durability.py`'s scenario but
   against the live worker process this time.
3. **Attachments** (`packages/shared/attachments.py` already has validation +
   `FakeR2Client`) — wire the real R2 presign once a bucket exists (Phase 8 per plan).
4. **Wire `apps/web/lib/api.ts`** to the real API (`NEXT_PUBLIC_API_URL`), replacing the
   mock fallbacks. The frontend's campaign flow, live dashboard, and chaos panel are all
   built against mocks right now — this is the next thing that makes them real.
5. Phase 5 (AI preflight) per PLAN.md, once 1–4 above are solid.

## Design contract

Ledger palette (ink `#14110F`, paper `#F5F1E8`, vermillion `#E4491F` — the only accent)
with Signal typography (Space Grotesk, tight tracking), 3px radius, mono 600–700 on all
buttons/pills/chips, layouts to 1800px. `design/prototypes/*.html` remain the reference.

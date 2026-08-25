# `tests/`

131 tests, all passing. `uv run pytest tests/ -v`. `ruff check` is clean across the whole
codebase.

## The one that matters most

**`test_durability.py::test_crash_between_provider_accept_and_record_does_not_duplicate`**
— kills a simulated worker in the exact dangerous window (after the provider accepts a
send, before we record it), then asserts the email was sent **exactly once**. This is the
test that proves the project's whole thesis. It must never be skipped or weakened; if it's
red, the durability claim on the front page is false.

## Files, by count

| File | Tests | Covers |
|---|---|---|
| `test_durability.py` | 6 | Crash recovery, the claim mutex, permanent-error non-retry |
| `test_auth.py` | 7 | Signup/signin/signout, tampered-cookie rejection, same-error-for-both-failure-modes |
| `test_organizations_and_contacts.py` | 9 | RBAC capability matrix, **tenant isolation** (org A cannot see org B's data), 404-not-403 for non-members |
| `test_render.py` | 20 | The sandboxed template pipeline — sandbox-escape attempts genuinely raise `SecurityError`, personalization-before-sanitization order verified against a hostile contact field |
| `test_templates.py` | 8 | Template versioning (never edited in place), preview rendering, tenant isolation |
| `test_attachments.py` | 7 | Size cap, extension allowlist, content-type/extension mismatch detection |
| `test_job_store.py` | 8 | `SQLAlchemyJobStore` against real `EmailJob` rows on SQLite — genuine coverage, not a scope-limited stand-in (see note below) |
| `test_campaign_launch.py` | 8 | Launch fan-out, recipient re-resolution at launch time (not trusted from the client), cancel leaving in-flight jobs untouched |
| `test_webhooks.py` | 12 | Ingest dedup, orphan resolution (forward + backward), the `DELIVERY_RANK` monotonicity guarantee directly tested |
| `test_preflight.py` | 19 | Every spam-risk signal (both triggered and clean case), personalization audit, link/bounce-risk checks |
| `test_preflight_api.py` | 4 | The same logic through the real API + DB, tenant-isolated |
| `test_llm_providers.py` | 15 | `FakeLLMProvider` determinism, the provider factory's env-driven selection, HTTP-backed providers against a mocked transport (no real API calls) |
| `test_drift.py` | 8 | PSI + KS-test drift detection, proven against synthetic drift (see scope note in `ml/README.md`) |

## Fixtures (`conftest.py`)

`db_session` — an in-memory SQLite DB, fresh per test, built from `Base.metadata` directly
(not via Alembic migrations — those are verified separately, see
[`../migrations/`](../migrations/)). `client` — an `httpx.AsyncClient` wired to the app via
FastAPI's dependency override, so no real network or process boundary exists between test
and app code.

## A scope note worth reading before trusting "131/131 green" as the whole story

`packages/durable/queue.py`'s real dequeue SQL (`FOR UPDATE SKIP LOCKED`, Postgres-only by
design) has never run against a live database in this dev environment — no Postgres, no
Docker available. What's actually verified:

- The **logic** (lease semantics, backoff, retry/DLQ) — via `InMemoryJobStore` in
  `test_durability.py`.
- The **production job store** (`SQLAlchemyJobStore`) — genuinely runs on SQLite since
  it's plain ORM with no Postgres-only syntax (`test_job_store.py`).
- Campaign launch fan-out — real up to the `enqueue_task` call, which
  `test_campaign_launch.py` mocks out; see that file's module docstring for exactly where
  the tested/untested line sits.

Before deploying, create a free Neon Postgres branch and run the actual dequeue/reaper SQL
and the kill-worker demo against the live worker process. See
[`../NEXT.md`](../NEXT.md) for the full accounting.

## Two bugs found by actually running tests, not by reading code

Both documented in full in `../NEXT.md`, but the short version: a preflight test asserted
a wrong score because the test itself forgot a template variable, not because the code was
wrong — caught by printing the real API response instead of trusting the assertion. And
`services/api/routers/auth.py` hardcoded `secure=True` on the session cookie, which
silently breaks sign-in under httpx's test client (and any plain-HTTP dev server) since a
`Secure` cookie is never sent over non-HTTPS — caught because a signup-then-`/me` test
returned `None` instead of the signed-in user.

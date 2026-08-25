# Sendrun

**Durable, AI-assisted email campaign platform.** A final-year AI/ML portfolio project
whose backbone is a from-scratch durable execution engine — not "a website that sends
emails," of which there are thousands.

> Every recipient is an **independent, idempotent job**. Kill a worker mid-campaign and
> nothing is lost and nothing is sent twice. Duplicate and out-of-order provider webhooks
> converge to correct state.

That claim is proven, not asserted: `tests/test_durability.py` kills a worker in the exact
window between the provider accepting a send and the record of it being written, then
asserts the email was sent **exactly once**.

---

## Why this exists

Most student email-sender projects are `POST /send → for email in list: send(email)`.
That collapses the moment a worker crashes mid-batch, a network call times out, or a
webhook arrives twice. Sendrun's actual subject is what it takes to make bulk operations
survive failure — the AI/ML layer sits on top of that foundation, not instead of it.

## Architecture

```
Next.js (Vercel) ──SSE──► FastAPI (Render)
                              │
        ┌─────────────────────┼──────────────────┐
        ▼                     ▼                  ▼
   Neon Postgres        Upstash Redis      Cloudflare R2
   source of truth      cache/chaos cfg    attachments
        │
        │ tasks table (FOR UPDATE SKIP LOCKED)
        ▼
   Worker process (Render background worker)
        │
        ▼
   EmailProvider ──► fake | Resend
        │
        └──webhooks──► /api/webhooks/* ──► provider_events ──► processor
```

No Docker, no Temporal. Temporal Cloud has no free tier ($100/mo minimum); self-hosting
needs Docker, which this environment doesn't have. So the durable engine
(`packages/durable/`) is built from scratch on Postgres — `FOR UPDATE SKIP LOCKED`
leasing, lease-expiry as crash detection, exponential backoff with full jitter, a
dead-letter queue. It's a from-scratch implementation of the same primitives Temporal
provides, honestly scoped: no event-sourced replay, no cross-process determinism
guarantees, no visibility store. See [`packages/durable/README.md`](packages/durable/README.md).

## The invariants

Eight rules the whole system is built to never violate — see [`CLAUDE.md`](CLAUDE.md)
for the full list with reasoning. The two that matter most:

- **The idempotency key is `email_job_id`**, a UUID minted at launch — never a content
  hash. A deliberate resend creates a *new* job row with a *new* key, or the provider
  would dedupe it and silently send nothing.
- **`EmailJob` has two orthogonal status axes**, never collapsed into one column:
  `send_status` (worker-owned) and `delivery_status` (webhook-owned). `opened`/`clicked`
  are not statuses at all — a late open must never be able to clobber a bounce.

## What's built

| Phase | What | Status |
|---|---|---|
| 0 | Monorepo, no-push guard, agent onboarding | ✅ |
| 1 | Auth, orgs, RBAC, tenant isolation, contacts | ✅ |
| 2 | Sandboxed template rendering, personalization, sanitization | ✅ |
| 3 | Durable engine, campaign launch/cancel, the worker process | ✅ |
| 4 | Webhook ingestion, dedup, orphan resolution, SSE progress | ✅ |
| 5 | AI preflight — spam-risk heuristic, missing-variable audit, link validation | ✅ |
| 6 | ML — bounce-risk model (ROC-AUC 0.84) trained, MLflow-tracked, drift detection | 🟡 partial |
| 7 | LLM-backed agents (planner, content, QA, recipient, analytics) | 🟡 provider layer only |
| 8 | Hardening, CI/CD, deploy | ⬜ |

**131 tests, all passing.** `uv run pytest tests/ -v`. See [`NEXT.md`](NEXT.md) for exactly
what's verified versus what still needs a real Postgres instance to prove (this dev
environment has no Docker/Postgres — see that file for the honest boundary).

## Stack

- **Frontend** — Next.js 16 + TypeScript + Tailwind 4. See [`apps/web/README.md`](apps/web/README.md).
- **Backend** — FastAPI + SQLAlchemy (async) + Alembic. See [`services/api/README.md`](services/api/README.md).
- **Worker** — the durable engine's dispatch loop. See [`services/worker/README.md`](services/worker/README.md).
- **ML** — scikit-learn + XGBoost + MLflow. See [`ml/README.md`](ml/README.md).
- **DB** — Postgres (Neon free tier) in production, SQLite for tests.
- **Deploy target** — Vercel (web) + Render (api + worker) + Neon + Upstash + R2, all
  card-free.

## Quickstart

```bash
git clone <this repo>
cd Sendrun
cp .env.example .env          # fake providers work out of the box, no keys needed

uv venv && uv pip install -e ".[dev]"
uv run alembic upgrade head
uv run pytest tests/ -v        # 131 tests

uv run uvicorn services.api.main:app --reload --port 8000
# in another terminal:
npm --prefix apps/web install && npm --prefix apps/web run dev
```

Everything runs against `FakeEmailProvider` and `FakeLLMProvider` by default — both are
real, deterministic, feature-complete implementations (with a genuine idempotency cache
and seeded chaos), not stubs. Real API keys drop into `.env` with zero code change.

## Repository layout

```
apps/web/          Next.js frontend — see apps/web/README.md
services/api/       FastAPI routers, auth, webhooks — see services/api/README.md
services/worker/    the durable worker process — see services/worker/README.md
packages/durable/   ★ the engine — see packages/durable/README.md
packages/shared/     models, transitions.py, providers/
ml/                 the ML pipeline — see ml/README.md
design/prototypes/   approved HTML prototypes — the visual contract
migrations/          Alembic
docs/                architecture notes (in progress)
tests/               131 tests across every phase
```

## The one hard rule

This repo never pushes to a remote from an agent session — enforced by a `PreToolUse`
hook, not just a convention. See [`CLAUDE.md`](CLAUDE.md).

## Documents worth reading

- [`PLAN.md`](PLAN.md) — the full phased plan, including what was deliberately **not**
  built and why (per-recipient workflows, a CDC outbox, per-org fair scheduling — all
  considered and rejected with reasons).
- [`NEXT.md`](NEXT.md) — exact current state: what's verified, what bugs were found and
  fixed, what's next, kept current at the end of every working session.
- [`CLAUDE.md`](CLAUDE.md) — the invariants, brand system, and conventions.

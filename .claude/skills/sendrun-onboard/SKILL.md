---
name: sendrun-onboard
description: Onboard onto the Sendrun codebase in one read. Use at the start of any new session, or when an agent needs project context - what Sendrun is, the durability thesis, the invariants that must not be broken, where the important code lives, how to run everything, and which approaches were already rejected and why. Fires on "what is this project", "get me up to speed", "onboard", or any first task in this repo.
---

# Sendrun — working context

Read this once and you can work. Do not re-derive it by exploring the tree.

**Current phase: Phases 1–4 done (domain, email engine, campaign launch, webhooks/SSE).
Next: the janitor + a real Postgres verification pass, then wiring the frontend to the
real API.** For exactly what was built, what's verified passing, and the next task in
order, read `NEXT.md` at the repo root — it is kept current at the end of every session
and is more precise than this file about "where things stand today." It also documents
an important scope boundary: no Postgres/Docker is available in this dev environment, so
the durable engine's real `FOR UPDATE SKIP LOCKED` dequeue SQL has never been run live —
only its logic (via fakes) and the ORM-based job store (which is dialect-portable) are
verified. Read that section before assuming the worker is deploy-ready.

---

## What it is

A durable, AI-assisted email campaign platform. Final-year AI/ML portfolio project. Deliberately
**not** "a website that sends emails" — the point is the execution engine underneath.

A user creates an **Organization**, imports **Contacts** (tags, groups, events), composes a
**Campaign** from a template with `{{variables}}`, runs an **AI preflight**, approves, and launches.
Launch fans out to **one independent EmailJob per recipient**. Provider webhooks drive real delivery
state. A live dashboard shows per-job progress.

---

## The thesis (this is what the project is defending)

> Every recipient is an independent, **idempotent** job. Kill a worker mid-campaign and nothing is
> lost and nothing is sent twice. Duplicate and out-of-order webhooks converge to correct state.

The demo that proves it: launch a campaign, `SIGKILL` the worker at ~50%, restart, show the campaign
completes with **zero duplicate provider calls**. That test runs in CI and must never be skipped.

Three things make it real, in priority order:
1. Three-phase idempotent send (claim → provider call → record)
2. `FakeEmailProvider` with an idempotency cache and deterministic seeded chaos
3. The kill-worker test

---

## THE HARD RULE

**Never `git push`, add a remote, or create a GitHub repo.** Local git is fine and encouraged.
A `PreToolUse` hook blocks pushes — don't work around it. Tell the user to push themselves.

---

## Invariants — breaking any of these is a bug, not a style choice

1. **All state changes go through `packages/shared/transitions.py`** — guarded
   (`WHERE status IN (<allowed predecessors>)`) and monotonic. No scattered `UPDATE`s.

2. **`EmailJob` has two orthogonal status axes.** Never one column.
   - `send_status` (worker): `queued → sending → sent | failed_transient ⇄ sending | failed_permanent | cancelled | skipped`
   - `delivery_status` (webhooks, only once sent): `NULL → delivered | bounced | complained | deferred`

3. **`opened`/`clicked` are NOT statuses** — `email_engagements` rows + counters. As a status, a late
   open would clobber a bounce.

4. **Idempotency key = `email_job_id`** (UUID minted by the API at launch), never a content hash.
   A deliberate resend creates a NEW row with a NEW key.

5. **Campaign `completed` = all sends ATTEMPTED**, not all delivered. `delivery_settled_pct` is separate.

6. **Postgres is the source of truth.** The engine holds only what to do next. The dashboard reads
   Postgres, never the engine.

7. **Webhooks: verify → insert (ON CONFLICT DO NOTHING) → enqueue → 200, under 50ms.** Never process
   synchronously. `provider_events.email_job_id` is nullable on purpose — events routinely arrive
   before the send is recorded.

8. **The LLM never mutates the DB directly** and never takes an irreversible action. Structured tool
   call → validation → authorization → DB. Contact data is untrusted input, never instructions.

---

## The five files that matter most

| File | Why |
|---|---|
| `services/worker/tasks/send.py` | The three-phase idempotent send. The core of the thesis. |
| `packages/durable/` | The engine: lease/dequeue with `FOR UPDATE SKIP LOCKED`, backoff, reaper, DLQ. |
| `packages/shared/transitions.py` | The single enforced writer for all state changes. |
| `packages/shared/providers/fake.py` | Idempotency cache + deterministic chaos + self-webhooks. |
| `services/api/webhooks/processor.py` | Dedup, orphan resolution, monotonic precedence-rank application. |

---

## Architecture in one diagram

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
   Worker (Render background worker)
        │
        ▼
   EmailProvider ──► fake | Resend
        │
        └──webhooks──► /api/webhooks/* ──► provider_events ──► processor
```

**Why we built the engine instead of using Temporal:** Temporal Cloud has no free tier ($100/mo
minimum) and self-hosting needs Docker, which isn't installed. Building it is also the stronger
portfolio claim. Be honest in docs about what it lacks versus Temporal: no event-sourced replay, no
cross-process determinism guarantees, no visibility store.

---

## Already rejected — do not rebuild these

Each looks rigorous and costs weeks for no marginal credit. Reasons are in `PLAN.md`.

- One workflow/task per recipient without batching (row/history explosion)
- Per-org fair scheduling and multi-tenant quota (real problem, not this project's)
- CDC/Debezium outbox (a ~30-line janitor sweep closes the same gap)
- Holding a campaign open until every webhook lands (unbounded, never terminates)
- Fine-tuning an LLM or RAG over email corpora (months; adds nothing to the durability story)
- WebSockets for the dashboard (SSE over a Postgres poll is enough)
- Custom template engine, custom retry logic, virus scanning, Kubernetes, microservices, billing

---

## Brand system (approved — do not drift)

Base ink `#14110F` · surfaces `#1C1815`/`#241F1B` · paper `#F5F1E8` · accent `#E4491F` vermillion
(the **only** accent) · semantic ok `#7FB069`, warn `#D9A441`, crit `#E4491F`.
Display **Space Grotesk** (tracking −.03/−.04em), mono **JetBrains Mono**, radius **3px**.

User-specified rules:
- Buttons/pills/chips/active states: mono, **weight 600–700**, uppercase, clear and bold
- Layouts **scale to wide screens** — `max-width: 1800px`, `clamp()` padding, never a stranded column
- Card padding `clamp(18px, 1.6vw, 26px)`
- Semantic color ≠ accent. Vermillion = running/attention, not error.

The approved visual contract lives in `design/prototypes/` (console, landing, auth). Match it.

---

## Running things

```bash
# api
uv run uvicorn services.api.main:app --reload --port 8000
# worker
uv run python -m services.worker.main
# web
cd apps/web && npm run dev
# tests
uv run pytest tests/ -v
# the one that matters
uv run pytest tests/test_durability.py -v
```

Everything runs against fakes by default (`EMAIL_PROVIDER=fake`, `LLM_PROVIDER=fake`) — no API keys
needed. Real keys go in `.env`.

---

## Where to look next

- `PLAN.md` — full phased plan, decisions, and rejected alternatives. Read before proposing
  architecture changes.
- `CLAUDE.md` — the short version of this, auto-loaded every session.
- `docs/` — ARCHITECTURE, DATA_MODEL, API_SPEC, AI_SPEC, SECURITY, ADRs.

## Keep this current

Update this skill, `CLAUDE.md`, and `PLAN.md` at the end of each phase. A stale onboarding doc is
worse than none.

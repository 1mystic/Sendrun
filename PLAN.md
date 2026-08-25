# Sendrun — Durable AI-Assisted Email Workflow Platform

## Context

Final-year AI/ML Data Science portfolio project. The goal is explicitly **not** "a website that sends emails" — thousands of those exist. The goal is a system whose backbone is a **durable, fault-tolerant execution engine**, with ML and LLM layers on top, deployable entirely on free tiers.

`/home/mystic1/Projects/Sendrun` is currently empty except `design-sources.zip`.

**What that zip actually is:** not image assets. It is [VibeCurb](https://vibecurb.pages.dev/) — 7 markdown *design skill* files (`awwwards-hero`, `awwwards-sections`, `awwwards-motion`, `brandkit-gen`, `pixel-perfect`, `visual-redesign`, `imagegen-frontend`). They are strict anti-generic-UI protocols (Design Read → Quality Gate → Build → Visual Diff). We install them into `.claude/skills/` and invoke them when building UI, so the frontend gets a real brand identity without a manual design phase.

### Decisions made with the user

| Decision | Choice | Why |
|---|---|---|
| Workflow engine | **Build our own on Postgres** | Temporal Cloud is $100/mo minimum with no free tier; self-hosting needs Docker (not installed). Building it is the *stronger* story: "I built durable execution" > "I called an SDK". |
| Stack | Next.js + TS / FastAPI + Python | Python keeps ML native to the backend. |
| Infra | Cloud free tiers, no local Docker | Neon, Upstash, R2. |
| Deploy | Vercel + Render + Neon + Upstash + R2 | All card-free. |
| Build order | Phases 1–4 fully, then AI, then ML | Durable core must be real before decoration. |
| Providers | Fake first, real behind same interface | No API keys yet; fakes are also the chaos-demo engine. |
| DE/MLOps | MLflow + dbt + feature store/model registry | Scoped in; built in later phases. |

### The non-negotiable rule

**Never `git push`. Never push to any remote.** `git init`, `add`, `commit`, `status`, `log`, `diff`, `branch`, `checkout` are all fine. Pushing is the user's action alone. This goes in `CLAUDE.md`, and is enforced by a `PreToolUse` hook that blocks `git push` outright.

---

## The Core Thesis

Everything else is surface area. This is the claim the project defends:

> One `EmailJob` per recipient, executed independently, exactly-once-ish, surviving worker crashes, network timeouts, and duplicate/out-of-order provider webhooks — and we can *prove* it live by killing a worker mid-campaign.

Three things make that demonstrable, and they are the highest priority in the whole build:

1. Three-phase idempotent send (claim → provider call → record).
2. `FakeEmailProvider` with an idempotency cache and deterministic seeded chaos.
3. A rehearsed **kill-the-worker** demo showing zero duplicate sends.

---

## Architecture

```
Next.js (Vercel) ──SSE──► FastAPI (Render)
                              │
        ┌─────────────────────┼──────────────────┐
        ▼                     ▼                  ▼
   Neon Postgres        Upstash Redis      Cloudflare R2
   source of truth      cache/chaos cfg    attachments
        │
        │ jobs table (FOR UPDATE SKIP LOCKED)
        ▼
   Worker process (Render background worker)
        │
        ▼
   EmailProvider ──► fake | Resend
        │
        └──webhooks──► /api/webhooks/* ──► provider_events ──► processor
```

### The durable engine (`packages/durable/`)

This replaces Temporal. It is the intellectual centre of the project.

**Design** (Postgres-only, no broker):

```sql
CREATE TABLE tasks (
  id              uuid PRIMARY KEY,
  queue           text NOT NULL,
  task_type       text NOT NULL,
  payload         jsonb NOT NULL,
  idempotency_key text UNIQUE,
  status          text NOT NULL,        -- pending|leased|succeeded|failed|cancelled|dead
  run_after       timestamptz NOT NULL, -- backoff scheduling
  lease_until     timestamptz,          -- heartbeat expiry -> crash detection
  lease_owner     text,                 -- worker id
  attempt         int NOT NULL DEFAULT 0,
  max_attempts    int NOT NULL DEFAULT 5,
  last_error      text,
  parent_id       uuid,                 -- fan-out tree
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON tasks (queue, status, run_after) WHERE status = 'pending';
CREATE INDEX ON tasks (lease_until) WHERE status = 'leased';
```

Dequeue is the classic pattern:

```sql
UPDATE tasks SET status='leased', lease_owner=$1, lease_until=now()+interval '30s', attempt=attempt+1
WHERE id IN (
  SELECT id FROM tasks
  WHERE queue=$2 AND status='pending' AND run_after<=now()
  ORDER BY run_after
  FOR UPDATE SKIP LOCKED LIMIT $3
) RETURNING *;
```

Crash recovery is a reaper: `UPDATE tasks SET status='pending' WHERE status='leased' AND lease_until < now()`. That single line is the durability guarantee — a killed worker's leases expire and its tasks are re-picked. Combined with idempotency keys, re-execution is safe.

Also provides: exponential backoff with jitter, `max_attempts` → `dead` (a DLQ), heartbeats extending the lease for long tasks, a rate limiter (Redis token bucket — here we *do* need it, since we have no Temporal task-queue limit), and batched fan-out (a campaign spawns batch tasks of 500, each spawning per-recipient sends) so no single task carries 10k items.

**Interview framing:** it is a from-scratch implementation of the same primitives Temporal provides — leasing, at-least-once delivery, retry policy, crash recovery, DLQ — with idempotency at the boundary converting at-least-once into effectively-once. Document explicitly what it does *not* have (no event-sourced replay, no cross-process determinism guarantees, no visibility store) so the comparison is honest.

### Source of truth

Postgres holds everything the user sees. The engine holds only *what to do next*. All state changes go through **one** module, `packages/shared/transitions.py`, whose writes are guarded (`WHERE status IN (<allowed predecessors>)`) and monotonic — so replays, duplicates, and late writes are no-ops rather than corruption.

### Send activity — the three-phase write

`services/worker/tasks/send.py`. This is the most important file in the repo.

1. **Claim** — conditional `UPDATE ... WHERE status IN ('queued','sending','failed_transient')`. If it returns nothing, the job is terminal → return the existing result. If it returns a row that already has a `provider_message_id`, we crashed after the provider call → return it without resending.
2. **Send** — call the provider with `Idempotency-Key: {email_job_id}`. `TransientProviderError` → mark and re-raise (engine retries). `PermanentProviderError` → mark failed, non-retryable.
3. **Record** — write `provider_message_id` + `status='sent'`, and in the *same statement* adopt any orphan webhook events already waiting on that message id.

The key is `email_job_id` (a UUID minted by the API at launch, in the same transaction as the campaign plan) — **not** a content hash. A deliberate resend must create a *new* job row with a *new* key, or the provider would dedupe it and silently send nothing.

### Webhooks

`verify signature → INSERT ... ON CONFLICT (provider_event_id) DO NOTHING → enqueue → return 200` in under 50ms. Never process synchronously.

`provider_events.email_job_id` is **nullable** — that is the whole point. Webhooks routinely arrive before the send activity has recorded the message id. Two mechanisms close the gap: forward resolution (a sweeper re-attempts the join every 30s) and backward resolution (Phase 3 adopts waiting orphans immediately).

Out-of-order events are handled by a **precedence rank**, not a sequence: `{sent:2, delivered:3, bounced:90, complained:95}`, applied `WHERE rank(new) > rank(current)`. `opened`/`clicked` are **not statuses** — they go to a separate `email_engagements` table plus denormalized counters. Modeling `opened` as a status would let a late open clobber a bounce; this is a subtle bug that would surface in the demo.

### Two orthogonal axes on EmailJob

Do not collapse these into one column:

- `send_status` (engine-owned): `queued → sending → sent | failed_transient ⇄ sending | failed_permanent | cancelled | skipped`
- `delivery_status` (webhook-owned, only meaningful once sent): `NULL → delivered | bounced | complained | deferred`

Campaign `completed` means **all sends attempted**, not all delivered. Webhooks keep arriving for hours; waiting for them is an unbounded wait with no clean end. `delivery_settled_pct` is surfaced separately in the UI.

### Providers

```python
class EmailProvider(Protocol):
    name: str
    async def send(self, req: SendRequest) -> SendResponse: ...
    def verify_webhook(self, headers, body: bytes) -> bool: ...
    def parse_webhook(self, body: bytes) -> list[ProviderEvent]: ...
```

Callers branch only on `TransientProviderError` / `PermanentProviderError`. All provider-specific status-code mapping lives inside the implementation.

`FakeEmailProvider` is a first-class feature, not a stub. Seeded per `idempotency_key` so a given job has the same fate every run (reproducible demos and tests). It maintains a real idempotency cache in Redis — **this is what proves the exactly-once story**. It emits genuinely HMAC-signed webhooks back to our own endpoint with configurable delay, duplication, reordering, and a `webhook_before_send_ack_rate` knob that fires `email.sent` *before* `send()` returns, reproducing the race on demand. Same pattern for `FakeLLMProvider` (canned fixtures, simulated streaming).

**Chaos Mode** is a dev panel writing this config to Redis, tunable live during a demo.

---

## Build Phases

### Phase 0 — Foundation
Monorepo scaffold; `uv` for Python, npm workspaces for TS. `.env.example`. Alembic. `git init` + first commit (no remote, ever).

**Agent onboarding (user-requested).** Any new session — a fresh Claude Code run, a subagent, another model, or a human dev — must get full project context fast, without re-deriving it:

- `PLAN.md` at the repo root — a copy of this plan, kept in the repo so it travels with the code and is versioned alongside it.
- `CLAUDE.md` — auto-loaded every session. Short and scannable: what Sendrun is, the core thesis in three lines, the repo map, run commands, the invariants that must never be broken (single transitions module; two orthogonal status axes; `opened` is not a status; idempotency key = `email_job_id`), and **THE NO-PUSH RULE**.
- `.claude/skills/sendrun-onboard/SKILL.md` — an invocable `/sendrun-onboard` skill giving a new agent, in one read: current phase and what's done, architecture in one diagram, the five files that matter most and why, how to run api/worker/web/tests, the conventions, the traps already ruled out (so nobody rebuilds them), and where to look next. Written so an agent can be productive within one tool call rather than exploring the tree.
- `.claude/settings.json` — a `PreToolUse` hook that hard-blocks `git push`, plus an allowlist for common read-only commands to cut permission prompts.
- VibeCurb skills installed into `.claude/skills/` for UI work.

`PLAN.md`, `CLAUDE.md`, and the onboarding skill are updated at the end of each phase so they never drift from reality — a stale onboarding doc is worse than none.

### Phase 1 — Domain
Auth (session-based, argon2; OAuth later). Organization, OrganizationMember, RBAC (Owner/Admin/Editor/Viewer). Contact, Tag, Group, Event, Job. Tenant isolation enforced at the query layer, not in handlers. Smart-filter query builder. AuditLog. No AI yet.

### Phase 2 — Email engine
EmailTemplate with versions. Jinja2 **sandboxed** environment, strict `{{variable}}` allowlist, declared-variables manifest. Render pipeline: resolve → validate → personalize → sanitize HTML (bleach) → validate links. "Preview as recipient" — pick a contact, see their exact email. Attachments via R2 presigned PUT, 10MB cap, extension allowlist; store keys, fetch bytes inside `send()`.

### Phase 3 — Durable engine ★ most important
`packages/durable/` as above. Campaign + EmailJob models and state machines. Batched fan-out. Three-phase send. `FakeEmailProvider` with idempotency cache + chaos. Worker process with graceful shutdown. Reaper. Redis rate limiter. Retry/DLQ. **Kill-worker test in CI** — start a campaign, SIGKILL the worker, restart, assert zero duplicate provider calls.

### Phase 4 — Observability
Webhook ingestion + dedup + orphan reconciliation + sweeper. SSE progress endpoint over a 1s Postgres aggregate poll, cached in Redis at 500ms TTL. Live campaign dashboard with per-job stream. Notifications (in-app + owner email). Structured logging, OpenTelemetry traces. Chaos Mode panel.

### Phase 5 — AI preflight
Preflight report: content quality, missing personalization variables per recipient, broken links, attachment validation, heuristic spam-risk score with *explanations*. Presented as a risk score, never as "we predict Gmail's filter".

**Agent security boundary** (a differentiator worth documenting): contact data is untrusted input, never instructions. LLM emits structured tool calls → validation → authorization → DB. The LLM never mutates the database directly, and never performs an irreversible action without explicit human approval.

### Phase 6 — ML + MLOps
Three models: bounce/delivery risk, engagement (open) probability, send-time recommendation. Trained on synthetic-then-real campaign history.

- **MLflow** — experiment tracking, params/metrics/artifacts, honest precision/recall/F1 reported in the README.
- **Feature store** — Postgres feature tables with **point-in-time correctness** (features as-of send time, never leaking future outcomes) to prevent train/serve skew.
- **Model registry** — versioned artifacts in R2, staged promotion, the API loading a pinned version.
- **dbt** — staging → fact/dim models over `email_jobs` / `provider_events` / `email_engagements`, feeding both the analytics dashboard and the feature pipeline. This layer is needed for analytics regardless, so dbt earns its place rather than being résumé decoration.
- A/B subject-line testing with proper randomization; multi-armed bandit later.

### Phase 7 — Agents
Campaign Planner, Content, QA, Recipient, Analytics agents. Every one *proposes*; the user approves. Explicit per-agent tool permissions. Agent evaluation suite.

### Phase 8 — Hardening + deploy
Rate limits, secrets, load test, CI/CD. Deploy: Vercel (web) + Render (api + worker) + Neon + Upstash + R2 — all card-free. Render free spins down at 15min idle, so the design must be cold-start-safe; a scheduled ping keeps the worker warm during demos.

---

## Repository layout

```
Sendrun/
├── CLAUDE.md                    # conventions + THE NO-PUSH RULE
├── .claude/{settings.json,skills/}   # push-blocking hook; VibeCurb skills
├── apps/web/                    # Next.js + TS + Tailwind + shadcn
├── services/
│   ├── api/                     # FastAPI: routers, auth, webhooks, providers
│   └── worker/                  # durable worker: tasks/send.py, reaper, sweeper
├── packages/
│   ├── durable/                 # ★ the engine: queue, lease, retry, reaper, ratelimit
│   └── shared/                  # models, transitions.py, providers/, config
├── ml/                          # features, training, evaluation, registry, mlflow
├── analytics/dbt/               # staging + marts
├── migrations/                  # alembic
├── docs/                        # ARCHITECTURE, DATA_MODEL, API_SPEC, AI_SPEC,
│                                # SECURITY, ADRs, THREAT_MODEL, ROADMAP
└── tests/
```

`services/api` and `services/worker` both import `packages/shared`. Transition logic is defined once.

---

## Explicitly NOT building

Each of these looks rigorous and costs weeks for no marginal credit:

- One workflow/task per recipient without batching — history/row explosion.
- Per-org fair scheduling and multi-tenant quota — a real distributed-systems problem, but not this project's.
- CDC/Debezium outbox — a 30-line janitor sweep closes the same gap.
- Holding a campaign open until every webhook lands — unbounded wait, never terminates.
- Fine-tuning an LLM or building RAG over email corpora — months, and adds nothing to the durability thesis.
- WebSockets for the dashboard — SSE over a Postgres poll is sufficient and far simpler.
- A custom template engine, custom retry logic, virus scanning, Kubernetes, microservices, billing.

---

## Verification

Per phase, not just at the end:

1. **Unit** — state machine transitions (every illegal transition rejected), template rendering, spam heuristics, provider error mapping.
2. **Integration** — full campaign against `FakeEmailProvider` on a Neon branch DB; assert exact job counts per terminal state.
3. **Durability (the critical one)** — launch 500 jobs, `SIGKILL` the worker at ~50%, restart, assert: campaign completes, **zero duplicate provider calls** (fake provider counts them), every job terminal. This test *is* the thesis; it runs in CI.
4. **Chaos** — enable all chaos knobs including `webhook_before_send_ack_rate`, assert convergence: no orphan events unresolved, no non-monotonic status writes.
5. **Webhook race** — force a webhook before the message id is known; assert it is adopted and applied exactly once.
6. **ML** — held-out evaluation with point-in-time-correct features; assert no future leakage; report honest metrics.
7. **E2E** — Playwright: create org → import contacts → compose → preflight → approve → launch → watch dashboard → completion.
8. **Manual demo rehearsal** — the 10-scene recruiter walkthrough, ending with the worker kill.

---

## Open items to settle during Phase 0

- Brand identity — I'll run the VibeCurb `brandkit-gen` / `awwwards-hero` skills and present directions before building UI.
- Neon / Upstash / R2 accounts need creating (all card-free); until then everything runs against a local SQLite-compatible dev path or a Neon free branch.
- Resend and LLM keys drop into `.env` later with zero code change.

---

## Sources

- [Temporal Pricing](https://temporal.io/pricing) — no free tier, $100/mo minimum
- [Platforms with a real free tier for developers in 2026](https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026)
- [GCP Free Tier Complete Guide 2026](https://agentdeals.dev/gcp-free-tier-2026) — card required for identity verification
- [Hatchet vs Trigger.dev vs Inngest 2026](https://www.pkgpulse.com/guides/hatchet-vs-trigger-dev-v3-vs-inngest-durable-workflows-2026)
- [VibeCurb](https://vibecurb.pages.dev/) — the design skills in `design-sources.zip`

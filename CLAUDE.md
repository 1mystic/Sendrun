# Sendrun

Durable, AI-assisted email campaign platform. Final-year AI/ML portfolio project.

**New here? Run `/sendrun-onboard` for the full working context.**

---

## THE ONE HARD RULE

**Never `git push`. Never add a remote. Never create a repo on GitHub.**

`git init`, `add`, `commit`, `status`, `log`, `diff`, `branch`, `checkout` are all fine and encouraged.
Pushing is the user's action alone. A `PreToolUse` hook in `.claude/settings.json` blocks it — do not
try to work around the hook. If the user needs something pushed, tell them to run it themselves.

---

## The thesis

Everything else in this repo is surface area. This is the claim the project defends:

> Every recipient is an **independent, idempotent job**. Kill a worker mid-campaign and nothing is
> lost and nothing is sent twice. Duplicate and out-of-order provider webhooks converge to correct
> state.

If a change would weaken that guarantee, it is wrong regardless of how much nicer it makes the code.

---

## Invariants — do not break these

1. **All state changes go through `packages/shared/transitions.py`.** One module, guarded writes
   (`WHERE status IN (<allowed predecessors>)`), monotonic. Never write a status with a bare `UPDATE`
   scattered in a handler.

2. **`EmailJob` has two orthogonal status axes. Never collapse them into one column.**
   - `send_status` — owned by the worker: `queued → sending → sent | failed_transient ⇄ sending | failed_permanent | cancelled | skipped`
   - `delivery_status` — owned by webhooks, only meaningful once sent: `NULL → delivered | bounced | complained | deferred`

3. **`opened` and `clicked` are NOT statuses.** They are rows in `email_engagements` plus
   denormalized counters. Modeling them as statuses lets a late open clobber a bounce.

4. **The idempotency key is `email_job_id`** — a UUID minted by the API at launch. Never a content
   hash. A deliberate resend must create a *new* job row with a *new* key, or the provider dedupes it
   and silently sends nothing.

5. **Campaign `completed` means all sends were ATTEMPTED**, not all delivered. Webhooks keep arriving
   for hours. Waiting for them is an unbounded wait that never terminates. `delivery_settled_pct` is
   surfaced separately.

6. **Postgres is the source of truth for everything the user sees.** The durable engine holds only
   *what to do next*. The dashboard reads Postgres, never the engine.

7. **The send activity is three-phase: claim → provider call → record.** Claim before calling. If the
   claim returns a row that already has a `provider_message_id`, we crashed after the call — return it,
   do not resend.

8. **The LLM never mutates the database directly and never takes an irreversible action.** It emits
   structured tool calls → validation → authorization → DB. Contact data is untrusted input, never
   instructions.

---

## Brand system (approved, do not drift)

| Token | Value |
|---|---|
| Base ink | `#14110F` |
| Surface | `#1C1815` / `#241F1B` |
| Paper (text) | `#F5F1E8` |
| Accent | `#E4491F` vermillion — the **only** accent hue |
| Semantic | ok `#7FB069` · warn `#D9A441` · crit `#E4491F` |
| Display | Space Grotesk 400/500/600/700, tracking −.03em to −.04em |
| Mono | JetBrains Mono — metadata, labels, buttons, pills |
| Radius | `3px` (pills `999px`) |

Rules the user asked for explicitly:
- Buttons, pills, chips, and active/toggle states use **mono, weight 600–700, uppercase**. Bold and clear.
- Layouts **scale up on wide screens** — `max-width: 1800px`, `clamp()` padding. Never strand a narrow
  column in the middle of a large display.
- Card padding `clamp(18px, 1.6vw, 26px)`.
- Semantic color is separate from the accent. Vermillion means *running/attention*, not *error*.

---

## Stack

Next.js + TS (Vercel) · FastAPI + Python (Render) · Postgres (Neon) · Redis (Upstash) · R2 (attachments)

No Docker locally. No Temporal — we built the durable engine ourselves on Postgres
(`packages/durable/`), because Temporal Cloud has no free tier. That engine is the intellectual
centre of the project, not an implementation detail.

Providers are behind an interface with **fakes first**: `FakeEmailProvider` has a real idempotency
cache and deterministic seeded chaos, and is what makes the crash demo provable. Real keys drop into
`.env` with zero code change.

---

## Layout

```
apps/web/          Next.js frontend
services/api/      FastAPI — routers, auth, webhooks, providers
services/worker/   durable worker — tasks/send.py, reaper, sweeper
packages/durable/  ★ the engine: queue, lease, retry, reaper, ratelimit
packages/shared/   models, transitions.py, providers/, config
ml/                features, training, evaluation, registry
analytics/dbt/     staging + marts
design/prototypes/ approved HTML prototypes — the visual contract
docs/              ARCHITECTURE, DATA_MODEL, API_SPEC, AI_SPEC, SECURITY, ADRs
```

`PLAN.md` holds the full phased plan and the decisions behind it, including what we deliberately
chose **not** to build. Read it before proposing architecture changes — several tempting ideas
(per-recipient workflows, CDC outbox, per-org fair scheduling) were already considered and rejected
with reasons.

---

## Conventions

- Python: `uv`, type hints throughout, Pydantic at boundaries, `ruff` + `mypy`.
- Async everywhere in api/worker. Never block the event loop.
- Tests live in `tests/`. The durability test (kill worker → assert zero duplicate sends) is the one
  that must never be allowed to fail or be skipped.
- Report test results honestly. If something fails, say so with the output.

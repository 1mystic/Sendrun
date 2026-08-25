# `packages/shared/`

Domain models, state machines, and provider interfaces — imported by both `services/api/`
and `services/worker/`, which is why it's a separate package rather than living inside
either. Transition logic is defined exactly once.

## The one file to read first

[`transitions.py`](transitions.py) — the single enforced writer for every `Campaign` and
`EmailJob` status change. Two properties make it correct:

- **Guarded**: every transition names its allowed predecessors and writes
  `WHERE status IN (<predecessors>)`. A write from a stale actor matches zero rows and
  returns `None` — not corrupted state, not an exception, a normal "lost the race."
- **Monotonic**: delivery outcomes (`DELIVERY_RANK`) are ranked, not sequenced. A
  late-arriving `sent` after `delivered` is discarded, not applied — this is what makes
  duplicate/out-of-order webhooks harmless. `opened`/`clicked` are deliberately *absent*
  from this rank table; they're not part of the delivery-status axis at all (see
  `models.py`'s `EmailEngagement`), because a status model would let a late open clobber
  a bounce.

## Files

| File | What |
|---|---|
| [`models.py`](models.py) | 18 SQLAlchemy tables. `GUID`/`JSONVariant` custom types make the same models run on Postgres (prod) and SQLite (tests) with one schema. |
| [`transitions.py`](transitions.py) | State machines — see above. |
| [`db.py`](db.py) / [`config.py`](config.py) | Async engine/session; `Settings` read once from `.env`. |
| [`auth.py`](auth.py) | argon2 hashing, server-side sessions (a DB row behind a signed cookie — sign-out is a real `DELETE`). |
| [`authz.py`](authz.py) | `Role` hierarchy (Viewer<Editor<Admin<Owner), a spelled-out `CAPABILITIES` matrix, `scoped()` — tenant isolation enforced by a mandatory function argument, not handler discipline. |
| [`audit.py`](audit.py) | Append-only trail. Every consequential action, human or (eventually) AI-agent, gets one row — the paper trail behind "the LLM never mutates the DB directly." |
| [`render.py`](render.py) | The sandboxed template pipeline: resolve → validate → personalize → sanitize (bleach) → check links. `ImmutableSandboxedEnvironment`, not plain `SandboxedEnvironment` — closes the classic Jinja2 sandbox-escape via object mutation. |
| [`preflight.py`](preflight.py) | AI preflight: a heuristic, explainable spam-risk score (every signal named, nothing "the model felt like 42"), a per-recipient missing-variable audit over *every* recipient (not a sample), link validation. Pure function — no DB, no network. |
| [`attachments.py`](attachments.py) | R2 presign validation: 10MB cap, extension allowlist, and a content-type/extension mismatch check (the classic disguised-file attack). `FakeR2Client` for dev. |
| [`enqueue.py`](enqueue.py) / [`job_store.py`](job_store.py) | The SQLAlchemy execution layer over `packages/durable/queue.py`'s SQL-only primitives — see that package's README for why they're kept separate. |
| [`providers/`](providers/) | Email and LLM provider interfaces — see below. |

## The provider pattern

Both provider families follow the identical shape: one `Protocol`, callers branch only on
`TransientXError` vs `PermanentXError`, every vendor-specific detail (status codes, auth,
payload shape) stays inside the concrete implementation. This is what lets a fake and a
real provider be swapped by one environment variable with zero change anywhere else.

**Email** ([`providers/base.py`](providers/base.py), [`providers/fake.py`](providers/fake.py)) —
`FakeEmailProvider` is a first-class feature, not a stub: a genuine idempotency cache
(what makes the crash demo provable), deterministic seeded chaos (bounce/latency/failure
rates), and self-signed webhook emission including a `webhook_before_send_ack_rate` knob
that reproduces the orphan-event race on demand.

**LLM** ([`providers/llm.py`](providers/llm.py)) — `FakeLLMProvider`, `AnthropicProvider`,
`OpenAIProvider`, and `OpenRouterProvider` (one API key routes to 100+ models — Claude,
GPT, Llama, Mistral, Gemini — through an OpenAI-compatible endpoint, useful here
specifically because it lets `LLM_PROVIDER=openrouter` try different underlying models
without juggling per-vendor keys). Not yet called from anywhere — this is the provider
layer Phase 7's agents will sit on top of. See `providers/llm_http.py` for the one real
shape difference between vendors: Anthropic's Messages API takes `system` as a top-level
field, not a role in the messages array.

## Testing

Every module here has direct unit tests in `tests/` — `test_render.py` (sandbox-escape
attempts genuinely rejected), `test_preflight.py` (19 tests, every heuristic signal has
both a triggered and a clean case), `test_llm_providers.py` (mocked HTTP, no real API
calls), `test_job_store.py`, `test_attachments.py`. See [`../../tests/README.md`](../../tests/README.md).

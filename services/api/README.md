# `services/api/`

FastAPI backend. Run: `uv run uvicorn services.api.main:app --reload --port 8000`. Docs at
`/docs` once running.

## Routers

| Router | Prefix | What |
|---|---|---|
| [`routers/auth.py`](routers/auth.py) | `/api/auth` | Signup, signin, signout. Server-side sessions (a DB row behind a signed opaque cookie, not a JWT) — sign-out is a real `DELETE`, not a hope that a token expires. |
| [`routers/organizations.py`](routers/organizations.py) | `/api/organizations` | Create/list orgs, members, invites. Creating an org and making the creator its Owner happen in one transaction. |
| [`routers/contacts.py`](routers/contacts.py) | `/api/organizations/{org_id}/contacts` | CRUD + the smart-filter resolver (`POST .../resolve`) that campaign launch and preflight both call to turn a `SmartFilter` into a concrete recipient list. |
| [`routers/templates.py`](routers/templates.py) | `/api/organizations/{org_id}/templates` | Templates are **versioned, never edited in place** — `PUT` always creates a new `TemplateVersion`. A campaign pins the exact version it launched with, so editing a template later can't change what a past campaign sent. Includes `/preview` — render for one specific contact. |
| [`routers/campaigns.py`](routers/campaigns.py) | `/api/organizations/{org_id}/campaigns` | List, create, launch (the outbox-pattern fan-out — see its docstring for the exact commit/enqueue sequence), cancel, progress. |
| [`routers/groups.py`](routers/groups.py) | `/api/organizations/{org_id}/groups` | Named mailing lists (`Group`/`ContactGroup`). CRUD plus `POST /{group_id}/import` — bulk create/upsert contacts from already-parsed rows (the frontend parses CSV/pasted text; this endpoint maps columns to `email`/`name`/arbitrary `{{variable}}` fields, dedupes by `(org_id, email)`, and never touches an existing contact's suppression). |
| [`routers/preflight.py`](routers/preflight.py) | `/api/organizations/{org_id}/preflight` | AI preflight — wraps `packages/shared/preflight.py`'s pure logic with the DB access to load a template version + resolved recipients. |
| [`routers/progress.py`](routers/progress.py) | `/api/organizations/{org_id}/campaigns/{id}/progress/stream` | SSE stream, 1s poll of the same aggregate query the plain `/progress` endpoint uses — not a second source of truth. |
| [`routers/analytics.py`](routers/analytics.py) | `/api/organizations/{org_id}/analytics` | Real per-campaign delivered/bounced/opened/clicked aggregates over `EmailJob`/`EmailEngagement` — no fabricated metrics. |
| [`routers/jobs.py`](routers/jobs.py) | `/api/organizations/{org_id}/jobs` | Read-only durable-engine task inspector (dead-letter + in-flight), tenant-scoped via a join through `EmailJob → Campaign → org_id` since `tasks` itself carries no `org_id` column. |
| [`routers/agents.py`](routers/agents.py) | `/api/organizations/{org_id}/...` | QA Agent (`/templates/{id}/qa-review`) and Analytics Agent (`/campaigns/{id}/analyze`) — structured tool calls only, human approves every irreversible action, see CLAUDE.md invariant 8. |
| `organizations.py`'s `/{org_id}/audit-log` | — | The notification feed's data source. `AuditLog` is already an append-only, actor-attributed, org-scoped event trail, so notifications are a read over it rather than a new model. |
| [`webhooks/ingest.py`](webhooks/ingest.py) | `/api/webhooks` | verify → insert (dedup) → 200 → process async. Never processes inline — see the module docstring for why that ordering is load-bearing, not a style choice. |
| [`rate_limit_middleware.py`](rate_limit_middleware.py) | — | Redis-backed token bucket, in-memory fallback. Off by default (`RATE_LIMIT_ENABLED=false`) — see `.env.example`. |

## The one query pattern every router follows

Every endpoint that touches organization-scoped data calls `require_membership()` (from
[`deps.py`](deps.py)) before doing anything else, and every subsequent query filters
`WHERE org_id = :org_id` — enforced by `packages/shared/authz.scoped()`'s mandatory
argument, not left to each handler's discipline. A cross-tenant leak is a genuinely hard
bug to write here by accident; see `tests/test_organizations_and_contacts.py`'s tenant-
isolation tests for what that guarantee looks like verified.

A non-member of an org gets **404, not 403** — a 403 on a private org's URL confirms the
org exists to someone who has zero other information about it.

## Campaign launch, in one paragraph

`POST .../campaigns/{id}/launch` re-resolves the recipient `SmartFilter` at launch time —
never trusts what the client sent — mints one `EmailJob` row per resolved contact with the
job's own `id` as the future idempotency key, commits, *then* enqueues one durable task
per job, then flips the campaign to `RUNNING`. If the process dies between the commit and
`RUNNING`, the campaign is stuck in `LAUNCHING` with real job rows and no tasks — a janitor
sweep (not yet built, see [`../../NEXT.md`](../../NEXT.md)) is what closes that gap safely,
because task idempotency keys make a duplicate enqueue a no-op.

## Webhooks: the ordering that matters

```
verify signature (over the RAW body)
  → insert, ON CONFLICT (provider_event_id) DO NOTHING
  → return 200
  → process asynchronously (never inline)
```

Processing an event synchronously in the handler is exactly what causes duplicate
deliveries under load — the provider retries on any non-2xx, so slow processing directly
causes a thundering herd. `services/api/webhooks/processor.py` applies the actual
delivery-status update using precedence ranking (`packages/shared/transitions.DELIVERY_RANK`),
not sequence — a duplicate or late-arriving event is a correctly-discarded no-op.

## Auth notes worth knowing

- Sessions are httponly + samesite=lax, and `Secure` only when `COOKIE_SECURE=true` — a
  real bug this session hit and fixed: hardcoding `secure=True` silently breaks sign-in
  over plain `http://localhost`, because a browser (and httpx's test client) will not
  attach a `Secure` cookie to a non-HTTPS request at all.
- Signin returns the *same* 401 for "no such account" and "wrong password," verified
  against a real hash even on a missing user — so response timing can't leak which case
  occurred.

## Not yet wired

- The bounce-risk ML model is off by default in preflight (`BOUNCE_MODEL_ENABLED=false`)
  — see `routers/preflight.py`'s `_load_bounce_model` for why an unset MLflow tracking URI
  is deliberately treated as "disabled" rather than "silently create a local store."
- OpenTelemetry tracing.
- A janitor sweep for the `LAUNCHING`-stuck-with-no-tasks gap described above.
- Settings: sending-rate-cap, provider switching, and org deletion have no endpoint yet —
  the frontend leaves those controls visibly disabled rather than faking a save.

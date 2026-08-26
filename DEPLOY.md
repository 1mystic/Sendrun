# Deploying Sendrun

Every account below is free-tier, card-free (except where noted). This is a set of
manual steps for **you** to run — an agent session never has your credentials and
should never attempt this; it can only prepare the config files (already done, see
below) and hand you this checklist.

## What's already prepared

- [`render.yaml`](render.yaml) — a Render Blueprint defining both the API and worker
  services (`uv pip install -e .`, correct start commands, the env var names each
  service needs).
- [`apps/web/vercel.json`](apps/web/vercel.json) — Vercel build config for the frontend.
- [`.github/workflows/ci.yml`](.github/workflows/ci.yml) — CI that must pass on `main`
  before deploying (lint, 179+ tests, migrations round-trip, secrets audit).
- [`.env.example`](.env.example) — every environment variable every service needs, with
  comments explaining each.
- [`scripts/audit_secrets.py`](scripts/audit_secrets.py) — run this once more locally
  right before you push, as a last check.

## Order matters: data stores first, then services that depend on them

### 1. Neon (Postgres) — free tier, no card

1. Sign up at [neon.tech](https://neon.tech) with GitHub/Google (no card required for
   the free tier).
2. Create a project. Copy the connection string — it looks like
   `postgresql://user:pass@ep-xxx.neon.tech/dbname?sslmode=require`.
3. **Convert it to the async driver form** Sendrun's `DATABASE_URL` expects:
   `postgresql+asyncpg://user:pass@ep-xxx.neon.tech/dbname` (drop `?sslmode=require`;
   asyncpg negotiates TLS automatically against Neon).
4. Apply migrations against it once, from your own machine, before wiring up Render:
   ```bash
   export DATABASE_URL="postgresql+asyncpg://...(your Neon URL)..."
   uv run alembic upgrade head
   ```
   **This is the first time this project's migrations run against real Postgres** — see
   [`NEXT.md`](NEXT.md)'s scope notes on why that verification hasn't happened yet in
   this dev environment (no local Postgres/Docker). Watch this step's output carefully.
5. Also apply the durable engine's raw SQL schema (the `tasks` table —
   deliberately outside Alembic, see [`packages/durable/README.md`](packages/durable/README.md)):
   ```bash
   uv run python -c "
   import asyncio
   from sqlalchemy.ext.asyncio import create_async_engine
   from sqlalchemy import text
   from packages.durable.queue import CREATE_TASKS_TABLE
   async def main():
       engine = create_async_engine('YOUR_DATABASE_URL_HERE')
       async with engine.begin() as conn:
           await conn.execute(text(CREATE_TASKS_TABLE))
   asyncio.run(main())
   "
   ```

### 2. Upstash (Redis) — free tier, no card

1. Sign up at [upstash.com](https://upstash.com).
2. Create a Redis database (choose a region close to your Render region — `oregon` if
   you keep Render's default).
3. Copy the `redis://` (or `rediss://` for TLS) connection URL from the dashboard.

### 3. Cloudflare R2 (attachments) — free tier, no card for the free quota

1. Sign up at [dash.cloudflare.com](https://dash.cloudflare.com), enable R2.
2. Create a bucket (e.g. `sendrun-attachments`).
3. Create an R2 API token with read/write access to that bucket. Note the Account ID,
   Access Key ID, and Secret Access Key.
4. **Not yet wired into the running app** — `packages/shared/attachments.py`'s
   `R2Client.presign_put` currently raises `NotImplementedError` until real credentials
   are plugged in (see that file). `FakeR2Client` is what runs today.

### 4. Render (API + worker) — free tier, no card

1. Sign up at [render.com](https://render.com) with GitHub.
2. New → Blueprint → connect this repo. Render reads `render.yaml` automatically and
   proposes both `sendrun-api` and `sendrun-worker`.
3. Before the first deploy, set these env vars in the Render dashboard for **both**
   services (the ones marked `sync: false` in `render.yaml` — Render won't have a value
   for them otherwise):
   - `DATABASE_URL` — the Neon URL from step 1
   - `REDIS_URL` — the Upstash URL from step 2
4. Deploy. `sendrun-api`'s health check hits `/api/health` — watch the Render logs for
   the first successful check.

**Free-tier caveat, real and worth knowing:** Render's free web service spins down after
15 minutes of no traffic and cold-starts on the next request (10-30s). The worker
service has no such spin-down (it's not a web service), but Render's free background
workers can still be resource-throttled. For a demo, hit the API once a few minutes
before you need it, or add a scheduled uptime ping (a free tier of
[UptimeRobot](https://uptimerobot.com) or similar, hitting `/api/health` every 10 min) —
this is a real tradeoff of the free tier, not a bug in this setup.

### 5. Vercel (frontend) — free tier, no card

1. Sign up at [vercel.com](https://vercel.com) with GitHub.
2. New Project → import this repo. Set the **Root Directory** to `apps/web` (Vercel
   asks this during import — the monorepo layout means it must not build from the repo
   root).
3. Set the environment variable `NEXT_PUBLIC_API_URL` to your deployed `sendrun-api`
   URL from Render (e.g. `https://sendrun-api.onrender.com`).
4. Deploy. Vercel auto-detects Next.js from `apps/web/vercel.json` + `package.json`.

### 6. GitHub Actions (CI) — already runs, nothing to set up

`.github/workflows/ci.yml` runs automatically on every push/PR once this repo is on
GitHub — no secrets needed for it, since it tests entirely against fakes and SQLite.

## Verify the deployment end to end

1. Open the Vercel URL. Sign up for an account, create an organization.
2. Create a contact, a template, launch a tiny test campaign (1-2 recipients) —
   this exercises the FULL path: API → Postgres → durable engine `tasks` table →
   Render worker → `FakeEmailProvider` → webhook → SSE progress stream.
3. Watch the campaign complete in the live dashboard. Check the Render worker's logs to
   confirm it picked up and processed the job.
4. **This is also the very first time the kill-worker demo can be run for real** — from
   the Render dashboard, manually restart the `sendrun-worker` service mid-campaign
   (launch a campaign with enough recipients that it's still running, say 500+, then hit
   "Restart" on the worker service) and confirm the campaign still completes with zero
   duplicate sends. This is the live version of `tests/test_durability.py`'s guarantee —
   see [`NEXT.md`](NEXT.md) for why this hadn't been verified against real infrastructure
   until now.

## What's still on fakes after this deploy

- `EMAIL_PROVIDER=fake` — no real email is sent until a Resend account + verified
  sending domain exist and `RESEND_API_KEY` is set.
- `LLM_PROVIDER=fake` — agents (Phase 7) run against `FakeLLMProvider` until an
  Anthropic/OpenAI/OpenRouter key is set.
- `BOUNCE_MODEL_ENABLED=false` — the ML bounce-risk model needs an MLflow tracking store
  reachable from Render, which isn't set up by this guide (see
  [`ml/README.md`](ml/README.md) for what a real deployment of that would need — likely
  a small managed MLflow instance, or the model artifact copied to R2 and loaded
  directly without a full MLflow server).

None of these are blockers to a working, demonstrable deployment — the durability
thesis, the whole point of this project, is fully real with fakes. Flipping each on is
a config change, not a code change, by design (see each provider's `Fake*` class docs).

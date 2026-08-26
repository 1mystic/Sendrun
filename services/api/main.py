"""FastAPI entrypoint. Phase 1 (auth, organizations, contacts) + Phase 2
(templates, the sandboxed render pipeline) + Phase 3 (campaign launch and
fan-out onto the durable engine) + Phase 4 (webhook ingestion and the SSE
progress stream) + Phase 5 (AI preflight) + Phase 7 (QA/Analytics agents) +
Phase 8 (rate limiting). See PLAN.md for the phase ordering and why."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from packages.shared.config import get_settings

from .rate_limit_middleware import RateLimitMiddleware
from .routers import (
    agents,
    auth,
    campaigns,
    contacts,
    organizations,
    preflight,
    progress,
    templates,
)
from .webhooks import ingest as webhooks_ingest

app = FastAPI(title="Sendrun API", version="0.1.0")

_settings = get_settings()
if _settings.rate_limit_enabled:
    app.add_middleware(
        RateLimitMiddleware,
        capacity=_settings.rate_limit_capacity,
        refill_per_second=_settings.rate_limit_refill_per_second,
    )

# Credentials + a specific origin, not "*" — a wildcard origin cannot carry
# credentials per the CORS spec, and the session cookie is httponly, so this
# must be an explicit allowlist regardless.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(contacts.router)
app.include_router(templates.router)
app.include_router(campaigns.router)
app.include_router(preflight.router)
app.include_router(progress.router)
app.include_router(webhooks_ingest.router)
app.include_router(agents.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

"""FastAPI entrypoint. Phase 1 (auth, organizations, contacts) + Phase 2
(templates, the sandboxed render pipeline) + Phase 3 (campaign launch and
fan-out onto the durable engine) + Phase 4 (webhook ingestion and the SSE
progress stream). See PLAN.md for the phase ordering and why."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import auth, campaigns, contacts, organizations, progress, templates
from .webhooks import ingest as webhooks_ingest

app = FastAPI(title="Sendrun API", version="0.1.0")

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
app.include_router(progress.router)
app.include_router(webhooks_ingest.router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

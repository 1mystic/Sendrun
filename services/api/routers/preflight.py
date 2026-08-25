"""AI preflight endpoint — the real backend behind the compose screen's
preflight step. Wraps packages/shared/preflight.py (pure, deterministic
logic) with the DB access to load the template version and the resolved
recipient list.

If the Phase 6 bounce-risk model is registered and promoted, predicted
delivery uses real per-contact bounce probabilities; otherwise it falls back
to a stated neutral estimate rather than fabricating precision — see
preflight.py's _predict_delivery_rate docstring.
"""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.shared.models import Contact, EmailTemplate, User
from packages.shared.preflight import PreflightCheck as _Check
from packages.shared.preflight import run_preflight

from ..deps import get_db, require_membership, require_user
from .campaigns import _resolve_contact_ids
from .contacts import SmartFilter
from .templates import _latest_version

router = APIRouter(prefix="/api/organizations/{org_id}/preflight", tags=["preflight"])


class PreflightRequest(BaseModel):
    template_id: UUID
    recipients: SmartFilter


class SpamSignalOut(BaseModel):
    name: str
    triggered: bool
    weight: int
    explanation: str


class CheckOut(BaseModel):
    id: str
    severity: str
    title: str
    detail: str
    action: str | None = None
    meta: str | None = None

    @classmethod
    def from_check(cls, c: _Check) -> CheckOut:
        return cls(id=c.id, severity=c.severity, title=c.title, detail=c.detail,
                    action=c.action, meta=c.meta)


class PreflightOut(BaseModel):
    spam_risk: int
    spam_signals: list[SpamSignalOut]
    personalization_score: int
    predicted_delivery: float
    checks: list[CheckOut]
    recipients_missing_variables: dict[str, list[str]]
    recipient_count: int


def _load_bounce_model():
    """Best-effort load of the registered production bounce model. Returns
    None immediately if BOUNCE_MODEL_ENABLED is unset — an unset MLflow
    tracking URI otherwise makes mlflow silently create a local ./mlruns
    store on first touch, which is exactly the kind of ambient filesystem
    side effect a request handler (and especially the test suite) must never
    trigger by accident. Preflight works end-to-end without this; Phase 5
    ships before every org necessarily has a trained model — see
    packages/shared/preflight.py's _predict_delivery_rate docstring for the
    stated-neutral-estimate fallback this leads to."""
    from packages.shared.config import get_settings

    settings = get_settings()
    if not settings.bounce_model_enabled:
        return None

    try:
        import mlflow

        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        from ml.registry.promote import load_production_model

        return load_production_model()
    except Exception:
        return None


def _score_bounce_risk(model, contacts: list[Contact]) -> tuple[list[float] | None, set[str]]:
    if model is None or not contacts:
        return None, set()

    import pandas as pd

    from ml.features.pipeline import ALL_INPUT_FEATURES

    # Contacts here carry only what our own schema tracks; features the
    # trained model expects but we cannot populate (send_hour, subject_length,
    # etc. are campaign-level, not contact-level, at this call site) are
    # filled with neutral defaults. This is an honest limitation, not a
    # silent one — see NEXT.md's ML section.
    rows = [{
        "contact_age_days": 180, "prior_sends": 0, "prior_bounces": 0, "prior_opens": 0,
        "send_hour": 10, "subject_length": 50, "attachment_count": 0,
        "has_engaged_ever": 0, "is_weekend": 0, "has_personalization": 1,
        "domain": (c.email.split("@")[-1] if "@" in c.email else "unknown"),
    } for c in contacts]
    X = pd.DataFrame(rows)[ALL_INPUT_FEATURES]

    try:
        probs = model.predict_proba(X)[:, 1]
    except Exception:
        return None, set()

    high_risk = {c.email for c, p in zip(contacts, probs, strict=True) if p > 0.5}
    return list(probs), high_risk


@router.post("", response_model=PreflightOut)
async def run_preflight_check(
    org_id: UUID,
    body: PreflightRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> PreflightOut:
    await require_membership(org_id, db, user)

    template = await db.get(EmailTemplate, body.template_id)
    if template is None or template.org_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found")
    version = await _latest_version(db, template.id, template.current_version)

    contact_ids = await _resolve_contact_ids(db, org_id, body.recipients)
    if not contact_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "no recipients resolved")
    contacts = (
        await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))
    ).scalars().all()

    model = _load_bounce_model()
    bounce_probs, high_risk_emails = _score_bounce_risk(model, list(contacts))

    report = run_preflight(
        version, list(contacts),
        bounce_probs=bounce_probs, high_risk_emails=high_risk_emails,
    )

    return PreflightOut(
        spam_risk=report.spam_risk,
        spam_signals=[SpamSignalOut(**asdict(s)) for s in report.spam_signals],
        personalization_score=report.personalization_score,
        predicted_delivery=report.predicted_delivery,
        checks=[CheckOut.from_check(c) for c in report.checks],
        recipients_missing_variables=report.recipients_missing_variables,
        recipient_count=len(contacts),
    )

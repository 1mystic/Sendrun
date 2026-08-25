"""AI preflight: content quality, per-recipient missing variables, link
validation, and a heuristic spam-risk score — run before a campaign can be
approved for launch.

CLAUDE.md invariant 8 governs this whole module: it never mutates anything.
Every check here PROPOSES a finding; a human decides what to do about it in
the approve step (services/api/routers/campaigns.py). Nothing in this module
is an LLM call — it's entirely deterministic heuristics, which is itself a
design choice worth stating explicitly: a spam-risk SCORE must be reproducible
and explainable, never "the model felt like 42." An LLM-backed content-quality
pass is a plausible Phase 5 extension, but heuristics are what actually earns
trust for a number displayed as "18/100."
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from packages.shared.models import Contact, TemplateVersion
from packages.shared.render import check_link, extract_links, extract_used_variables

Severity = Literal["ok", "warn", "crit"]

# Heuristic spam-risk signal weights. Each is independently explainable — the
# report names exactly which signals fired, never a bare number. This is NOT
# a prediction of what Gmail/Outlook will actually do; see the "never claim
# we predict Gmail's filter" instruction in PLAN.md Phase 5.
SPAM_KEYWORDS = [
    "free", "act now", "limited time", "click here", "buy now", "winner",
    "congratulations", "urgent", "guarantee", "risk-free", "no obligation",
    "cash", "prize", "100% free", "cancel at any time",
]


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    id: str
    severity: Severity
    title: str
    detail: str
    action: str | None = None
    meta: str | None = None


@dataclass(frozen=True, slots=True)
class SpamSignal:
    name: str
    triggered: bool
    weight: int
    explanation: str


@dataclass(frozen=True, slots=True)
class PreflightReport:
    spam_risk: int  # 0-100, higher = riskier
    spam_signals: tuple[SpamSignal, ...]
    personalization_score: int  # 0-100, % of recipients with every variable resolved
    predicted_delivery: float  # 0-100, informed by contact-level bounce risk if available
    checks: tuple[PreflightCheck, ...]
    recipients_missing_variables: dict[str, list[str]] = field(default_factory=dict)
    excluded_high_risk_count: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Spam-risk heuristic
# ─────────────────────────────────────────────────────────────────────────────

def _score_spam_risk(subject: str, html_body: str) -> tuple[int, list[SpamSignal]]:
    """Every signal is named and independently checkable — this is what makes
    the score an explanation, not a black box. Weights are additive and
    capped at 100, not learned; a learned spam classifier is real future
    work, but a heuristic must ship first because it's auditable on day one.
    """
    signals: list[SpamSignal] = []
    text = f"{subject} {html_body}".lower()

    keyword_hits = [kw for kw in SPAM_KEYWORDS if kw in text]
    signals.append(SpamSignal(
        name="promotional_keywords", triggered=bool(keyword_hits), weight=len(keyword_hits) * 6,
        explanation=f"{len(keyword_hits)} promotional phrase(s): {', '.join(keyword_hits[:5])}"
        if keyword_hits else "no promotional phrases detected",
    ))

    caps_ratio = sum(1 for c in subject if c.isupper()) / max(len(subject), 1)
    is_all_caps_heavy = caps_ratio > 0.5 and len(subject) > 8
    signals.append(SpamSignal(
        name="subject_all_caps", triggered=is_all_caps_heavy, weight=15 if is_all_caps_heavy else 0,
        explanation=f"{caps_ratio:.0%} of subject characters are uppercase"
        if is_all_caps_heavy else "subject capitalization looks normal",
    ))

    exclaim_count = subject.count("!")
    excessive_exclaim = exclaim_count >= 2
    signals.append(SpamSignal(
        name="excessive_punctuation", triggered=excessive_exclaim,
        weight=8 * exclaim_count if excessive_exclaim else 0,
        explanation=f"{exclaim_count} exclamation marks in subject"
        if excessive_exclaim else "punctuation looks normal",
    ))

    links = extract_links(html_body)
    word_count = max(len(re.findall(r"\w+", html_body)), 1)
    link_density = len(links) / word_count
    high_link_density = link_density > 0.05 and len(links) > 2
    signals.append(SpamSignal(
        name="link_density", triggered=high_link_density,
        weight=12 if high_link_density else 0,
        explanation=f"{len(links)} links in {word_count} words ({link_density:.1%} density)"
        if high_link_density else f"{len(links)} link(s), density normal",
    ))

    subject_len = len(subject)
    too_short_or_long = subject_len < 10 or subject_len > 100
    signals.append(SpamSignal(
        name="subject_length", triggered=too_short_or_long,
        weight=6 if too_short_or_long else 0,
        explanation=f"subject is {subject_len} characters (outside the 10-100 sweet spot)"
        if too_short_or_long else f"subject is {subject_len} characters",
    ))

    score = min(sum(s.weight for s in signals), 100)
    return score, signals


# ─────────────────────────────────────────────────────────────────────────────
# Personalization: per-recipient missing-variable audit
# ─────────────────────────────────────────────────────────────────────────────

def _audit_personalization(
    template: TemplateVersion, contacts: list[Contact]
) -> tuple[int, dict[str, list[str]]]:
    """For EVERY recipient (not a sample), which of the template's declared
    variables have no value in that contact's fields. This is what lets the
    UI say "7 of 127 recipients are missing {{specialization}}" with an exact
    list, not an estimate."""
    declared = set(template.variables)
    missing_by_email: dict[str, list[str]] = {}

    for contact in contacts:
        context = {**contact.fields}
        if "first_name" in declared and "first_name" not in context and contact.name:
            context["first_name"] = contact.name.split(" ")[0]

        missing = sorted(v for v in declared if not context.get(v))
        if missing:
            missing_by_email[contact.email] = missing

    complete_count = len(contacts) - len(missing_by_email)
    score = round(100 * complete_count / len(contacts)) if contacts else 100
    return score, missing_by_email


# ─────────────────────────────────────────────────────────────────────────────
# Delivery prediction (uses the Phase 6 bounce-risk model if available)
# ─────────────────────────────────────────────────────────────────────────────

def _predict_delivery_rate(contacts: list[Contact], bounce_probs: list[float] | None) -> float:
    """If a trained bounce-risk model is wired in (see ml/registry/promote.py),
    average its per-contact bounce probability into a predicted delivery rate.
    Otherwise fall back to a neutral estimate rather than fabricating false
    precision — this function's contract is explicit about which mode it's
    in via the `bounce_probs is None` branch, and callers should surface that
    distinction rather than hide it."""
    if not contacts:
        return 100.0
    if bounce_probs is None:
        return 95.0  # neutral prior, not a model output — see docstring
    avg_bounce = sum(bounce_probs) / len(bounce_probs)
    return round((1 - avg_bounce) * 100, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Assembly
# ─────────────────────────────────────────────────────────────────────────────

def run_preflight(
    template: TemplateVersion,
    contacts: list[Contact],
    *,
    bounce_probs: list[float] | None = None,
    high_risk_emails: set[str] | None = None,
) -> PreflightReport:
    """The single entrypoint. Pure function of its inputs — no DB access, no
    network — so it is trivially unit-testable and safe to call from the
    compose screen on every keystroke without rate-limiting concerns."""
    high_risk_emails = high_risk_emails or set()

    spam_score, spam_signals = _score_spam_risk(template.subject, template.html_body)
    personalization_score, missing_by_email = _audit_personalization(template, contacts)
    predicted_delivery = _predict_delivery_rate(contacts, bounce_probs)

    checks: list[PreflightCheck] = []

    if missing_by_email:
        affected_vars = sorted({v for vs in missing_by_email.values() for v in vs})
        checks.append(PreflightCheck(
            id="missing_variables",
            severity="warn",
            title=(
                f"{len(missing_by_email)} of {len(contacts)} recipients missing "
                f"{', '.join(affected_vars)}"
            ),
            detail="These recipients would see an incomplete sentence. Set a fallback phrase, "
                   "or exclude them from this send.",
            action="Set fallback",
        ))
    else:
        checks.append(PreflightCheck(
            id="missing_variables", severity="ok",
            title="All recipients have every declared variable",
            detail="Every {{variable}} in this template resolves for every selected recipient.",
        ))

    if high_risk_emails:
        checks.append(PreflightCheck(
            id="bounce_risk",
            severity="crit",
            title=f"{len(high_risk_emails)} addresses are high bounce risk",
            detail="Previously hard-bounced or on a domain with a poor delivery history. "
                   "Sending to them costs sender reputation for the whole campaign.",
            action=f"Exclude {len(high_risk_emails)}",
        ))
    else:
        checks.append(PreflightCheck(
            id="bounce_risk", severity="ok",
            title="No high-bounce-risk addresses detected",
            detail="Every selected recipient has a clean or unknown delivery history.",
        ))

    links = extract_links(template.html_body)
    link_checks = [check_link(u) for u in links]
    broken = [lc for lc in link_checks if not lc.ok]
    if broken:
        checks.append(PreflightCheck(
            id="links", severity="crit",
            title=f"{len(broken)} of {len(links)} link(s) are invalid",
            detail="; ".join(f"{lc.url}: {lc.reason}" for lc in broken),
        ))
    elif links:
        checks.append(PreflightCheck(
            id="links", severity="ok",
            title=f"All {len(links)} link(s) resolve",
            detail="Every link in this template has a valid scheme and host.",
            meta=f"{len(links)} checked",
        ))
    else:
        checks.append(PreflightCheck(
            id="links", severity="ok", title="No links in this template",
            detail="Nothing to validate.",
        ))

    subject_len = len(template.subject)
    subject_ok = 10 <= subject_len <= 100 and not template.subject.isupper()
    checks.append(PreflightCheck(
        id="subject", severity="ok" if subject_ok else "warn",
        title=(
            "Subject line is well-formed" if subject_ok
            else "Subject line may read as promotional"
        ),
        detail=(
            f"{subject_len} characters, "
            f"{'no all-caps' if not template.subject.isupper() else 'ALL CAPS'}."
        ),
        meta=f"{subject_len} chars",
    ))

    used_vars = extract_used_variables(template.subject, template.html_body, template.text_body)
    undeclared = used_vars - set(template.variables)
    if undeclared:
        checks.append(PreflightCheck(
            id="undeclared_variables", severity="crit",
            title=f"Template references undeclared variable(s): {', '.join(sorted(undeclared))}",
            detail="This should have been caught at save time — this template's variable "
                   "declaration is out of sync with its body. Fix before sending.",
        ))

    return PreflightReport(
        spam_risk=spam_score,
        spam_signals=tuple(spam_signals),
        personalization_score=personalization_score,
        predicted_delivery=predicted_delivery,
        checks=tuple(checks),
        recipients_missing_variables=missing_by_email,
        excluded_high_risk_count=len(high_risk_emails),
    )

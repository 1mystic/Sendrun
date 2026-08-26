"""QA Agent — reviews a campaign before launch and proposes issues to fix.

Deliberately layered on top of the DETERMINISTIC preflight checks
(packages/shared/preflight.py), not a replacement for them. The heuristic
checks (missing variables, broken links, spam-risk score) are fast,
reproducible, and free — they run on every compose-screen keystroke. This
agent adds what heuristics cannot: judgment about TONE, CLARITY, and whether
the message actually reads well for a human, which is exactly the kind of
question an LLM is suited for and a regex is not.

The agent NEVER overrides or hides a preflight finding — it can only ADD
findings on top. If preflight flags a broken link, that finding stays
regardless of what the LLM says about the email's tone.
"""

from __future__ import annotations

from packages.shared.agents.base import AgentProposal, run_agent
from packages.shared.models import TemplateVersion
from packages.shared.preflight import PreflightReport, run_preflight
from packages.shared.providers.llm import LLMProvider

SYSTEM_INSTRUCTIONS = """You are a QA reviewer for outbound email campaigns. You are \
given a rendered email (subject + body) and a summary of deterministic checks that \
already ran against it. Your job is to add ONLY issues those deterministic checks \
cannot catch: unclear phrasing, an awkward or overly casual tone for the stated \
audience, a call-to-action that is missing or confusing, or a factual inconsistency \
within the email itself (e.g. the subject promises one thing and the body says \
another).

Do NOT re-report anything already listed in the deterministic findings — you will be \
shown them, and duplicating them wastes the reader's attention. If the email has no \
issues beyond what's already flagged, say so plainly and briefly.

Respond via the qa_findings tool. Each finding must name specifically what is wrong \
and why it matters to a recipient — no vague notes like "could be improved."
"""

TOOL_SCHEMA = {
    "properties": {
        "summary": {"type": "string", "description": "One-sentence overall verdict"},
        "additional_issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "suggested_fix": {"type": "string"},
                },
            },
        },
        "has_no_additional_issues": {"type": "boolean"},
    },
}


async def review_campaign(
    provider: LLMProvider,
    template: TemplateVersion,
    *,
    example_contact_fields: dict[str, str] | None = None,
    model: str = "fake-model",
) -> tuple[PreflightReport, AgentProposal]:
    """Runs the deterministic preflight first, then hands its findings to the
    LLM as context so the agent adds to them rather than duplicating them.
    Returns both — the API layer shows the deterministic report as-is
    (unconditionally trustworthy, reproducible) alongside the agent's
    proposal (which the human evaluates on its own merits)."""
    # A representative single-contact render for the LLM to actually read —
    # sending it the raw {{template}} syntax instead would make tone/clarity
    # judgments meaningless, since {{first_name}} isn't a sentence.
    from packages.shared.render import render_for_contact

    rendered = render_for_contact(
        subject=template.subject, html_body=template.html_body,
        text_body=template.text_body, declared_variables=template.variables,
        contact_fields=example_contact_fields or {},
        fallback="[example value]",
    )

    # Template-level checks only — no recipients needed for these.
    preflight = run_preflight(template, [])

    proposal = await run_agent(
        provider,
        agent_name="qa_agent",
        system_instructions=SYSTEM_INSTRUCTIONS,
        untrusted_data={
            "rendered_subject": rendered.subject,
            "rendered_body_text": rendered.text_body or rendered.html_body,
            "deterministic_findings_already_reported": [
                {"id": c.id, "severity": c.severity, "title": c.title} for c in preflight.checks
            ],
        },
        tool_schema=TOOL_SCHEMA,
        model=model,
        data_label="EMAIL_UNDER_REVIEW",
    )
    return preflight, proposal

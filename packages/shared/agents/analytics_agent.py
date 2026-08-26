"""Analytics Agent — explains why a completed campaign performed the way it
did, and proposes concrete next steps. This is a read-only agent: it
receives aggregate campaign statistics (never raw contact PII beyond what a
dashboard already displays) and produces an explanation plus a list of
suggested actions, each of which is itself an AgentProposal a human approves
before anything happens — this agent recommends "retire 4 bounced
addresses," it does not retire them.
"""

from __future__ import annotations

from dataclasses import dataclass

from packages.shared.agents.base import AgentProposal, run_agent
from packages.shared.providers.llm import LLMProvider

SYSTEM_INSTRUCTIONS = """You are a campaign performance analyst for an email marketing \
platform. You are given aggregate statistics for one completed campaign, plus the \
statistics from the sender's recent campaign history for comparison. Explain in 2-4 \
sentences what happened and why, referencing SPECIFIC numbers from the data you were \
given — never a vague statement like "engagement was mixed."

Then propose 1-3 concrete, actionable next steps. Each suggestion must be something a \
human can approve with one click (e.g. "retire N bounced addresses," "shorten future \
subject lines," "test sending at a different hour") — not a vague directive like \
"improve engagement."

If the campaign performed unremarkably (no notable deviation from the sender's own \
history), say that plainly rather than inventing a narrative — a flat result is a \
valid, honest finding.

Respond via the campaign_analysis tool.
"""

TOOL_SCHEMA = {
    "properties": {
        "explanation": {"type": "string"},
        "suggested_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
            },
        },
        "notable_deviation": {"type": "boolean"},
    },
}


@dataclass(frozen=True, slots=True)
class CampaignStats:
    """Only aggregate numbers — never raw contact data. What the dashboard
    already shows the user, so this agent's input is a strict subset of
    information the human already has access to."""

    campaign_id: str
    campaign_name: str
    recipients: int
    delivered: int
    bounced: int
    failed: int
    opened: int
    clicked: int
    complained: int


def _rate(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 1) if denominator else 0.0


async def explain_campaign(
    provider: LLMProvider,
    current: CampaignStats,
    history: list[CampaignStats],
    *,
    model: str = "fake-model",
) -> AgentProposal:
    payload = {
        "current_campaign": {
            "name": current.campaign_name,
            "recipients": current.recipients,
            "delivery_rate_pct": _rate(current.delivered, current.recipients),
            "bounce_rate_pct": _rate(current.bounced, current.recipients),
            "open_rate_pct": _rate(current.opened, current.delivered),
            "click_rate_pct": _rate(current.clicked, current.opened),
            "complaint_rate_pct": _rate(current.complained, current.delivered),
        },
        "recent_campaign_history": [
            {
                "name": c.campaign_name,
                "delivery_rate_pct": _rate(c.delivered, c.recipients),
                "open_rate_pct": _rate(c.opened, c.delivered),
                "click_rate_pct": _rate(c.clicked, c.opened),
            }
            for c in history
        ],
    }

    return await run_agent(
        provider,
        agent_name="analytics_agent",
        system_instructions=SYSTEM_INSTRUCTIONS,
        untrusted_data=payload,
        tool_schema=TOOL_SCHEMA,
        model=model,
        data_label="CAMPAIGN_STATISTICS",
    )

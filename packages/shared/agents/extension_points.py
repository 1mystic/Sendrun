"""Campaign Planner, Content, and Recipient agents — real interfaces on the
same `run_agent` foundation as qa_agent.py and analytics_agent.py, each with
one concrete worked example, but not fully built out. Scoped this way
deliberately: the security boundary (labeled untrusted data, tool-schema-only
output, propose-never-mutate) is the load-bearing part of "an agent" in this
codebase, and that's identical across all five agents — the QA and Analytics
agents prove the pattern works end-to-end against both preflight and
aggregate-stats inputs. These three would each need real prompt iteration
against actual usage to be trustworthy, which needs a real LLM API key and
real campaign data neither of which exist yet (see NEXT.md). Building three
more thin, untested prompts would not add real coverage — it would just be
more surface pretending to be more finished than it is.

Each function below is a genuine, runnable example against FakeLLMProvider —
not a stub — but is explicitly a starting point, not a production agent.
"""

from __future__ import annotations

from packages.shared.agents.base import AgentProposal, run_agent
from packages.shared.providers.llm import LLMProvider

# ─────────────────────────────────────────────────────────────────────────────
# Campaign Planner Agent
#
# Turns a free-text ask ("invite past AI-event attendees who haven't heard
# about this year's hackathon") into a structured SmartFilter
# (packages/api/routers/contacts.py's SmartFilter) plus a template
# suggestion. The hard part this needs before being real: grounding "past
# AI-event attendees" in the org's ACTUAL tag/group vocabulary rather than
# hallucinating tag names that don't exist — that requires passing the org's
# real tag list as context and validating the model's output against it,
# which is real engineering work, not a prompt tweak.
# ─────────────────────────────────────────────────────────────────────────────

PLANNER_SYSTEM_INSTRUCTIONS = """You are a campaign planning assistant. Given a \
plain-language request and the organization's actual list of contact tags and \
groups, propose a SmartFilter (tags to include, whether to exclude suppressed \
contacts) that would resolve to the described audience. You may ONLY use tag/group \
names that appear in the provided list — never invent one that sounds plausible. If \
no combination of the available tags matches the request, say so rather than \
guessing.

Respond via the campaign_plan tool.
"""

PLANNER_TOOL_SCHEMA = {
    "properties": {
        "reasoning": {"type": "string"},
        "suggested_tags": {"type": "array", "items": {"type": "string"}},
        "exclude_suppressed": {"type": "boolean"},
        "confidence_the_tags_match_the_request": {"type": "number"},
    },
}


async def plan_campaign(
    provider: LLMProvider,
    request_text: str,
    available_tags: list[str],
    *,
    model: str = "fake-model",
) -> AgentProposal:
    """Worked example. A real implementation would additionally call
    contacts.resolve_recipients with the proposed tags and show the human
    the ACTUAL resolved count before they approve — a plan that resolves to
    zero contacts is a plan that failed, and the UI should say so
    immediately rather than after launch."""
    return await run_agent(
        provider,
        agent_name="campaign_planner_agent",
        system_instructions=PLANNER_SYSTEM_INSTRUCTIONS,
        untrusted_data={"request": request_text, "available_tags": available_tags},
        tool_schema=PLANNER_TOOL_SCHEMA,
        model=model,
        data_label="PLANNING_REQUEST",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Content Agent
#
# Drafts a subject line + body from a brief, grounded in DECLARED
# personalization variables only — never inventing an achievement or fact
# about a recipient the org didn't actually provide (PLAN.md's "AI
# personalization must be grounded in known data, no hallucinated
# achievements" principle). Needs real work before production: the output
# must be re-validated through validate_template() (render.py) before it can
# even be saved, since an LLM-authored template has no guarantee its
# {{variables}} match a declared list.
# ─────────────────────────────────────────────────────────────────────────────

CONTENT_SYSTEM_INSTRUCTIONS = """You are drafting an email template for an outreach \
campaign. You are given a brief and a list of variable names that will be available \
per-recipient at send time (e.g. first_name, event_name). Write a subject line and \
HTML body that uses ONLY {{variable}} placeholders from that list — never invent a \
new variable name, and never claim a specific fact about a recipient that isn't one \
of the provided variables (no fabricated achievements, titles, or history).

Respond via the draft_template tool.
"""

CONTENT_TOOL_SCHEMA = {
    "properties": {
        "subject": {"type": "string"},
        "html_body": {"type": "string"},
        "variables_used": {"type": "array", "items": {"type": "string"}},
    },
}


async def draft_content(
    provider: LLMProvider,
    brief: str,
    available_variables: list[str],
    *,
    model: str = "fake-model",
) -> AgentProposal:
    """Worked example. A real implementation pipes the result straight
    through validate_template() before ever showing it as savable — an
    LLM's own claim about which variables it used is not trustworthy
    on its own; the sandboxed parser is the actual check."""
    return await run_agent(
        provider,
        agent_name="content_agent",
        system_instructions=CONTENT_SYSTEM_INSTRUCTIONS,
        untrusted_data={"brief": brief, "available_variables": available_variables},
        tool_schema=CONTENT_TOOL_SCHEMA,
        model=model,
        data_label="CONTENT_BRIEF",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Recipient Agent
#
# Suggests which contacts match a described audience — the highest-risk
# agent of the five, since its output directly becomes a send list if
# approved uncritically. PLAN.md is explicit that this MUST be human-
# reviewed before launch, never auto-applied; the tool schema below returns
# CANDIDATE contact ids with reasoning, not a live query the agent executes
# itself — the actual contact lookup happens in application code using the
# agent's suggested TAGS/criteria, the same way plan_campaign works, not by
# handing the LLM raw contact rows to reason over freely.
# ─────────────────────────────────────────────────────────────────────────────

RECIPIENT_SYSTEM_INSTRUCTIONS = """You are suggesting a recipient segment for a \
campaign. Given a description of the desired audience and the organization's actual \
tag vocabulary, propose which tags define that audience and explain your reasoning. \
You do NOT have access to individual contact records — you reason about SEGMENTS \
(tags/groups), never named individuals, and your output is a criteria proposal a \
human must review before any email is sent to anyone.

Respond via the recipient_criteria tool.
"""

RECIPIENT_TOOL_SCHEMA = {
    "properties": {
        "reasoning": {"type": "string"},
        "suggested_tags": {"type": "array", "items": {"type": "string"}},
        "caveats": {
            "type": "string",
            "description": "Anything the human should double-check before approving",
        },
    },
}


async def suggest_recipients(
    provider: LLMProvider,
    audience_description: str,
    available_tags: list[str],
    *,
    model: str = "fake-model",
) -> AgentProposal:
    """Worked example, deliberately the thinnest of the three — this is the
    agent PLAN.md's "AI proposes recipient selection, human approves" human-
    in-the-loop principle applies to most directly, and shipping it
    without a very deliberate review-and-diff UI (showing exactly which
    contacts the proposal resolves to, before launch) would be the single
    easiest way to violate CLAUDE.md invariant 8 in this whole codebase."""
    return await run_agent(
        provider,
        agent_name="recipient_agent",
        system_instructions=RECIPIENT_SYSTEM_INSTRUCTIONS,
        untrusted_data={
            "audience_description": audience_description, "available_tags": available_tags,
        },
        tool_schema=RECIPIENT_TOOL_SCHEMA,
        model=model,
        data_label="AUDIENCE_REQUEST",
    )

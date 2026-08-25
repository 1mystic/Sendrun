"""The LLM provider boundary — mirrors packages/shared/providers/base.py's
EmailProvider pattern exactly: one Protocol, provider-specific details
isolated inside each implementation, callers never branch on provider type.

CLAUDE.md invariant 8 governs every caller of this module: an LLM response is
a proposal, never an executed action. Nothing in this file calls a database
or takes an irreversible step — see docs on the Agent Security Boundary in
PLAN.md Phase 5/7. Contact and campaign data passed into a prompt is
untrusted input, never instructions; callers must never interpolate raw
contact fields into a system prompt.

Providers implemented:
  - FakeLLMProvider    canned responses, deterministic, for dev/tests
  - AnthropicProvider   api.anthropic.com
  - OpenAIProvider      api.openai.com
  - OpenRouterProvider  openrouter.ai — one API key, routes to 100+ models
                         (Claude, GPT, Llama, Mistral, Gemini, etc.) through
                         an OpenAI-compatible endpoint. Useful for this
                         project specifically because it lets a single
                         LLM_PROVIDER=openrouter config try/compare multiple
                         underlying models without juggling separate API keys
                         per vendor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    messages: tuple[Message, ...]
    model: str
    max_tokens: int = 1024
    temperature: float = 0.3
    # Structured-output tool schema, when the caller needs a typed response
    # (e.g. the recipient-suggestion agent) rather than free text. Kept as a
    # plain dict (JSON Schema) rather than a provider SDK type, so callers
    # never import a vendor SDK type into their own code.
    tool_schema: dict | None = None


@dataclass(frozen=True, slots=True)
class CompletionResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    # Populated only when the request included a tool_schema and the model
    # returned structured output matching it.
    tool_call: dict | None = None


class LLMProviderError(Exception):
    pass


class LLMTransientError(LLMProviderError):
    """Rate limit, timeout, 5xx — retry with backoff."""


class LLMPermanentError(LLMProviderError):
    """Invalid request, auth failure, content policy rejection — do not retry."""


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        """Raises LLMTransientError or LLMPermanentError — never a bare
        provider-SDK exception, matching EmailProvider's contract."""
        ...

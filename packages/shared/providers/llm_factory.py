"""Selects the LLM provider from Settings — the same fake-first, env-driven
pattern services/worker/main.py's get_provider() uses for email. Every
caller depends on the LLMProvider Protocol, never a concrete class, so this
is the only place LLM_PROVIDER is branched on.
"""

from __future__ import annotations

from packages.shared.config import get_settings

from .llm import LLMProvider


def get_llm_provider() -> LLMProvider:
    settings = get_settings()

    match settings.llm_provider:
        case "fake":
            from .llm_fake import FakeLLMProvider

            return FakeLLMProvider()
        case "anthropic":
            from .llm_http import AnthropicProvider

            if not settings.anthropic_api_key:
                raise ValueError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
            return AnthropicProvider(settings.anthropic_api_key)
        case "openai":
            from .llm_http import OpenAIProvider

            if not settings.openai_api_key:
                raise ValueError("LLM_PROVIDER=openai requires OPENAI_API_KEY")
            return OpenAIProvider(settings.openai_api_key)
        case "openrouter":
            from .llm_http import OpenRouterProvider

            if not settings.openrouter_api_key:
                raise ValueError("LLM_PROVIDER=openrouter requires OPENROUTER_API_KEY")
            return OpenRouterProvider(
                settings.openrouter_api_key,
                site_url=settings.openrouter_site_url,
                app_name="Sendrun",
            )
        case _:
            raise ValueError(f"unknown LLM_PROVIDER: {settings.llm_provider!r}")

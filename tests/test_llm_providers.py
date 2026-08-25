"""LLM provider tests: FakeLLMProvider's real behavior, the factory's env-
driven selection (including the new openrouter option), and the HTTP-backed
providers' request/response shapes against a mocked transport — no real API
calls, matching the email provider test style."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from packages.shared.providers.llm import (
    CompletionRequest,
    LLMPermanentError,
    LLMTransientError,
    Message,
)
from packages.shared.providers.llm_factory import get_llm_provider
from packages.shared.providers.llm_fake import FakeLLMProvider
from packages.shared.providers.llm_http import (
    AnthropicProvider,
    OpenAIProvider,
    OpenRouterProvider,
)


class TestFakeLLMProvider:
    @pytest.mark.asyncio
    async def test_returns_deterministic_response_for_same_prompt(self):
        provider = FakeLLMProvider()
        req = CompletionRequest(messages=(Message("user", "hello"),), model="fake-model")
        r1 = await provider.complete(req)
        r2 = await provider.complete(req)
        assert r1.text == r2.text

    @pytest.mark.asyncio
    async def test_different_prompts_get_different_responses(self):
        provider = FakeLLMProvider()
        r1 = await provider.complete(
            CompletionRequest(messages=(Message("user", "hello"),), model="m")
        )
        r2 = await provider.complete(
            CompletionRequest(messages=(Message("user", "goodbye"),), model="m")
        )
        assert r1.text != r2.text

    @pytest.mark.asyncio
    async def test_fixture_matching_returns_the_registered_response(self):
        provider = FakeLLMProvider(fixtures={"spam risk": "This email scores 18/100."})
        req = CompletionRequest(
            messages=(Message("user", "What is the spam risk of this email?"),), model="m"
        )
        r = await provider.complete(req)
        assert r.text == "This email scores 18/100."

    @pytest.mark.asyncio
    async def test_tool_schema_produces_a_shape_matching_stub(self):
        provider = FakeLLMProvider()
        schema = {
            "properties": {
                "recipient_count": {"type": "integer"},
                "reasoning": {"type": "string"},
            }
        }
        req = CompletionRequest(
            messages=(Message("user", "plan a campaign"),), model="m", tool_schema=schema,
        )
        r = await provider.complete(req)
        assert r.tool_call is not None
        assert "recipient_count" in r.tool_call
        assert "reasoning" in r.tool_call
        assert isinstance(r.tool_call["recipient_count"], int)

    @pytest.mark.asyncio
    async def test_no_tool_schema_means_no_tool_call(self):
        provider = FakeLLMProvider()
        r = await provider.complete(
            CompletionRequest(messages=(Message("user", "hi"),), model="m")
        )
        assert r.tool_call is None


class TestProviderFactory:
    def test_defaults_to_fake(self):
        provider = get_llm_provider()
        assert provider.name == "fake"

    def test_openrouter_without_key_raises(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openrouter")
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
        from packages.shared.config import get_settings

        get_settings.cache_clear()
        try:
            with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
                get_llm_provider()
        finally:
            get_settings.cache_clear()

    def test_openrouter_with_key_selects_openrouter_provider(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openrouter")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key")
        from packages.shared.config import get_settings

        get_settings.cache_clear()
        try:
            provider = get_llm_provider()
            assert provider.name == "openrouter"
        finally:
            get_settings.cache_clear()


def _mock_response(status_code: int, json_body: dict) -> httpx.Response:
    return httpx.Response(status_code, json=json_body, request=httpx.Request("POST", "https://x"))


class TestOpenAICompatibleProviders:
    """OpenAI and OpenRouter share an implementation — testing OpenRouter
    here is exactly what verifies the shared code path works for a second
    consumer, not a redundant copy of the OpenAI test."""

    @pytest.mark.asyncio
    async def test_openrouter_parses_a_successful_completion(self):
        provider = OpenRouterProvider("sk-or-test", site_url="https://sendrun.app")
        fake_body = {
            "model": "anthropic/claude-sonnet-4.5",
            "choices": [{"message": {"content": "Hello from OpenRouter"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        mock_target = "httpx.AsyncClient.post"
        with patch(mock_target, return_value=_mock_response(200, fake_body)) as mock_post:
            req = CompletionRequest(
                messages=(Message("user", "hi"),), model="anthropic/claude-sonnet-4.5",
            )
            resp = await provider.complete(req)

        assert resp.text == "Hello from OpenRouter"
        assert resp.input_tokens == 10
        assert resp.output_tokens == 5

        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer sk-or-test"
        assert call_kwargs["headers"]["HTTP-Referer"] == "https://sendrun.app"
        assert call_kwargs["json"]["model"] == "anthropic/claude-sonnet-4.5"

    @pytest.mark.asyncio
    async def test_openrouter_parses_a_tool_call(self):
        provider = OpenRouterProvider("sk-or-test")
        fake_body = {
            "model": "openai/gpt-4o",
            "choices": [{"message": {
                "content": None,
                "tool_calls": [{"function": {
                    "arguments": json.dumps({"recipient_count": 42}),
                }}],
            }}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        with patch("httpx.AsyncClient.post", return_value=_mock_response(200, fake_body)):
            req = CompletionRequest(
                messages=(Message("user", "plan"),), model="openai/gpt-4o",
                tool_schema={"properties": {"recipient_count": {"type": "integer"}}},
            )
            resp = await provider.complete(req)
        assert resp.tool_call == {"recipient_count": 42}

    @pytest.mark.asyncio
    async def test_429_raises_transient_not_permanent(self):
        provider = OpenAIProvider("sk-test")
        with patch(
            "httpx.AsyncClient.post",
            return_value=_mock_response(429, {"error": "rate limited"}),
        ):
            with pytest.raises(LLMTransientError):
                await provider.complete(
                    CompletionRequest(messages=(Message("user", "hi"),), model="gpt-4o")
                )

    @pytest.mark.asyncio
    async def test_401_raises_permanent_not_transient(self):
        provider = OpenAIProvider("bad-key")
        with patch(
            "httpx.AsyncClient.post",
            return_value=_mock_response(401, {"error": "invalid api key"}),
        ):
            with pytest.raises(LLMPermanentError):
                await provider.complete(
                    CompletionRequest(messages=(Message("user", "hi"),), model="gpt-4o")
                )

    @pytest.mark.asyncio
    async def test_500_raises_transient(self):
        provider = OpenAIProvider("sk-test")
        with patch(
            "httpx.AsyncClient.post",
            return_value=_mock_response(500, {"error": "server error"}),
        ):
            with pytest.raises(LLMTransientError):
                await provider.complete(
                    CompletionRequest(messages=(Message("user", "hi"),), model="gpt-4o")
                )


class TestAnthropicProvider:
    @pytest.mark.asyncio
    async def test_system_message_is_extracted_as_top_level_field(self):
        """Anthropic's Messages API takes `system` as a top-level param, not
        a role in the messages array — this is the one real shape difference
        from the OpenAI-compatible providers, and it's the thing most likely
        to silently break if refactored carelessly."""
        provider = AnthropicProvider("sk-ant-test")
        fake_body = {
            "model": "claude-sonnet-4-5",
            "content": [{"type": "text", "text": "hi there"}],
            "usage": {"input_tokens": 5, "output_tokens": 3},
        }
        mock_target = "httpx.AsyncClient.post"
        with patch(mock_target, return_value=_mock_response(200, fake_body)) as mock_post:
            req = CompletionRequest(
                messages=(
                    Message("system", "You are a helpful assistant."),
                    Message("user", "hi"),
                ),
                model="claude-sonnet-4-5",
            )
            resp = await provider.complete(req)

        assert resp.text == "hi there"
        sent_payload = mock_post.call_args.kwargs["json"]
        assert sent_payload["system"] == "You are a helpful assistant."
        assert all(m["role"] != "system" for m in sent_payload["messages"])

    @pytest.mark.asyncio
    async def test_tool_use_block_is_parsed_as_tool_call(self):
        provider = AnthropicProvider("sk-ant-test")
        fake_body = {
            "model": "claude-sonnet-4-5",
            "content": [{"type": "tool_use", "input": {"recipient_count": 7}}],
            "usage": {"input_tokens": 5, "output_tokens": 3},
        }
        with patch("httpx.AsyncClient.post", return_value=_mock_response(200, fake_body)):
            req = CompletionRequest(
                messages=(Message("user", "plan"),), model="claude-sonnet-4-5",
                tool_schema={"properties": {"recipient_count": {"type": "integer"}}},
            )
            resp = await provider.complete(req)
        assert resp.tool_call == {"recipient_count": 7}

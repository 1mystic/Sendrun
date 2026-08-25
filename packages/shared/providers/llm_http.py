"""Real HTTP-backed LLM providers: Anthropic, OpenAI, and OpenRouter.

OpenAI and OpenRouter both speak the same OpenAI-compatible chat-completions
wire format, so `_OpenAICompatibleProvider` implements it once; OpenAIProvider
and OpenRouterProvider are thin subclasses differing only in base URL,
required headers, and how a model name is qualified.

Anthropic uses its own Messages API shape (system prompt is a top-level field,
not a "system"-role message), so it gets its own implementation rather than
being forced into the OpenAI shape.
"""

from __future__ import annotations

import json

import httpx

from .llm import (
    CompletionRequest,
    CompletionResponse,
    LLMPermanentError,
    LLMProvider,
    LLMTransientError,
)

_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


def _raise_for_status(status_code: int, body: str, provider: str) -> None:
    if status_code == 429 or status_code >= 500:
        raise LLMTransientError(f"{provider}: {status_code} — {body[:300]}")
    if status_code >= 400:
        raise LLMPermanentError(f"{provider}: {status_code} — {body[:300]}")


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    _BASE_URL = "https://api.anthropic.com/v1/messages"
    _API_VERSION = "2023-06-01"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        system = next((m.content for m in req.messages if m.role == "system"), None)
        turns = [{"role": m.role, "content": m.content} for m in req.messages if m.role != "system"]

        payload: dict = {
            "model": req.model, "max_tokens": req.max_tokens,
            "temperature": req.temperature, "messages": turns,
        }
        if system:
            payload["system"] = system
        if req.tool_schema:
            payload["tools"] = [{
                "name": "structured_output", "input_schema": req.tool_schema,
            }]
            payload["tool_choice"] = {"type": "tool", "name": "structured_output"}

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            try:
                resp = await client.post(
                    self._BASE_URL,
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": self._API_VERSION,
                        "content-type": "application/json",
                    },
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                raise LLMTransientError(f"anthropic: request timed out: {exc}") from exc
            except httpx.ConnectError as exc:
                raise LLMTransientError(f"anthropic: connection failed: {exc}") from exc

        _raise_for_status(resp.status_code, resp.text, "anthropic")
        data = resp.json()

        text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        tool_blocks = [b["input"] for b in data.get("content", []) if b.get("type") == "tool_use"]

        return CompletionResponse(
            text="".join(text_blocks), model=data.get("model", req.model),
            input_tokens=data.get("usage", {}).get("input_tokens", 0),
            output_tokens=data.get("usage", {}).get("output_tokens", 0),
            tool_call=tool_blocks[0] if tool_blocks else None,
        )


class _OpenAICompatibleProvider(LLMProvider):
    """Shared implementation for any provider speaking the OpenAI chat-
    completions format. Subclasses set _BASE_URL and _extra_headers."""

    name = "openai-compatible"
    _BASE_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _extra_headers(self) -> dict[str, str]:
        return {}

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        payload: dict = {
            "model": req.model,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }
        if req.tool_schema:
            payload["tools"] = [{
                "type": "function",
                "function": {"name": "structured_output", "parameters": req.tool_schema},
            }]
            payload["tool_choice"] = {
                "type": "function", "function": {"name": "structured_output"},
            }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers(),
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            try:
                resp = await client.post(self._BASE_URL, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                raise LLMTransientError(f"{self.name}: request timed out: {exc}") from exc
            except httpx.ConnectError as exc:
                raise LLMTransientError(f"{self.name}: connection failed: {exc}") from exc

        _raise_for_status(resp.status_code, resp.text, self.name)
        data = resp.json()

        choice = data["choices"][0]
        message = choice["message"]
        tool_call = None
        if message.get("tool_calls"):
            raw_args = message["tool_calls"][0]["function"]["arguments"]
            tool_call = json.loads(raw_args) if isinstance(raw_args, str) else raw_args

        usage = data.get("usage", {})
        return CompletionResponse(
            text=message.get("content") or "",
            model=data.get("model", req.model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            tool_call=tool_call,
        )


class OpenAIProvider(_OpenAICompatibleProvider):
    name = "openai"
    _BASE_URL = "https://api.openai.com/v1/chat/completions"


class OpenRouterProvider(_OpenAICompatibleProvider):
    """OpenRouter: one API key, one OpenAI-compatible endpoint, routes to
    100+ underlying models by qualifying the model name with a vendor prefix
    (e.g. "anthropic/claude-sonnet-4.5", "openai/gpt-4o", "meta-llama/llama-3.1-70b-instruct").

    The model string is passed through EXACTLY as given in CompletionRequest —
    this provider does not remap or default it, since OpenRouter's own model
    catalog is the source of truth for valid names and changes independently
    of this codebase. Pick the model at the call site (or via config), not here.
    """

    name = "openrouter"
    _BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str, *, site_url: str = "", app_name: str = "Sendrun") -> None:
        super().__init__(api_key)
        # OpenRouter uses these two OPTIONAL headers for attribution on
        # https://openrouter.ai/rankings — harmless to omit, but including
        # them is free and correct when known.
        self._site_url = site_url
        self._app_name = app_name

    def _extra_headers(self) -> dict[str, str]:
        headers = {"X-Title": self._app_name}
        if self._site_url:
            headers["HTTP-Referer"] = self._site_url
        return headers

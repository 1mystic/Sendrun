"""FakeLLMProvider — deterministic canned responses, no network, for dev and
tests. Mirrors FakeEmailProvider's standard: not a stub, a real feature. A
fixed seed means the same prompt always returns the same response, so agent
behavior is reproducible in tests and demos.
"""

from __future__ import annotations

import hashlib

from .llm import CompletionRequest, CompletionResponse, LLMProvider


class FakeLLMProvider(LLMProvider):
    name = "fake"

    def __init__(self, *, fixtures: dict[str, str] | None = None) -> None:
        # Keyed by a substring match against the last user message, so a test
        # can register "spam" -> a canned spam-risk explanation without
        # needing to match the whole prompt verbatim.
        self._fixtures = fixtures or {}

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        last_user = next((m.content for m in reversed(req.messages) if m.role == "user"), "")

        for key, response in self._fixtures.items():
            if key.lower() in last_user.lower():
                text = response
                break
        else:
            text = self._default_response(last_user)

        tool_call = None
        if req.tool_schema is not None:
            tool_call = self._fake_tool_call(req.tool_schema, last_user)

        # Deterministic pseudo-token counts from content length, not an LLM
        # call — good enough for cost-estimation code paths to exercise
        # without a network dependency.
        return CompletionResponse(
            text=text, model=req.model,
            input_tokens=sum(len(m.content) for m in req.messages) // 4,
            output_tokens=len(text) // 4,
            tool_call=tool_call,
        )

    def _default_response(self, prompt: str) -> str:
        # Deterministic but prompt-dependent, so different prompts in the
        # same test run don't collide on an identical canned string.
        digest = hashlib.sha256(prompt.encode()).hexdigest()[:8]
        return f"[fake-llm response {digest}] Acknowledged: {prompt[:80]}"

    def _fake_tool_call(self, schema: dict, prompt: str) -> dict:
        """Produces a minimally-valid stub matching the schema's declared
        properties, so a caller testing the tool-call code path (validate ->
        authorize -> DB, per CLAUDE.md invariant 8) has something schema-
        shaped to validate against without a real model call."""
        props = schema.get("properties", {})
        result = {}
        for key, spec in props.items():
            t = spec.get("type", "string")
            result[key] = {
                "string": f"fake-{key}", "integer": 0, "number": 0.0,
                "boolean": False, "array": [], "object": {},
            }.get(t, None)
        return result

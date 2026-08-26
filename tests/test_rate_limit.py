"""packages/shared/rate_limit.py — the token-bucket algorithm's actual
correctness (allows within capacity, blocks over it, refills over time), and
the middleware's identity resolution (authenticated user over IP)."""

from __future__ import annotations

import asyncio

import pytest

from packages.shared.rate_limit import InMemoryTokenBucket


class TestInMemoryTokenBucket:
    @pytest.mark.asyncio
    async def test_allows_requests_within_capacity(self):
        bucket = InMemoryTokenBucket()
        for _ in range(5):
            result = await bucket.consume("key1", capacity=5, refill_per_second=0)
            assert result.allowed

    @pytest.mark.asyncio
    async def test_blocks_requests_over_capacity(self):
        bucket = InMemoryTokenBucket()
        for _ in range(5):
            await bucket.consume("key1", capacity=5, refill_per_second=0)
        # The 6th request, with zero refill, must be blocked.
        result = await bucket.consume("key1", capacity=5, refill_per_second=0)
        assert not result.allowed

    @pytest.mark.asyncio
    async def test_different_keys_have_independent_buckets(self):
        """One user hitting their limit must never throttle a different
        user — this is the property that makes per-identity limiting
        meaningful at all."""
        bucket = InMemoryTokenBucket()
        for _ in range(5):
            await bucket.consume("user_a", capacity=5, refill_per_second=0)
        blocked = await bucket.consume("user_a", capacity=5, refill_per_second=0)
        assert not blocked.allowed

        # A different key starts with its own full bucket.
        allowed = await bucket.consume("user_b", capacity=5, refill_per_second=0)
        assert allowed.allowed

    @pytest.mark.asyncio
    async def test_tokens_refill_over_time(self):
        bucket = InMemoryTokenBucket()
        # Drain the bucket completely.
        for _ in range(3):
            await bucket.consume("key1", capacity=3, refill_per_second=100)
        blocked = await bucket.consume("key1", capacity=3, refill_per_second=100)
        assert not blocked.allowed

        # At 100 tokens/sec, waiting ~20ms should refill at least 1 token.
        await asyncio.sleep(0.02)
        result = await bucket.consume("key1", capacity=3, refill_per_second=100)
        assert result.allowed

    @pytest.mark.asyncio
    async def test_refill_never_exceeds_capacity(self):
        """A bucket left alone for a long time must cap at capacity, not
        accumulate unboundedly — an unbounded bucket would let a burst
        after an idle period bypass the rate limit entirely."""
        bucket = InMemoryTokenBucket()
        await bucket.consume("key1", capacity=5, refill_per_second=1000)
        await asyncio.sleep(0.05)  # plenty of time to "over-refill" if uncapped

        results = [
            await bucket.consume("key1", capacity=5, refill_per_second=1000)
            for _ in range(5)
        ]
        assert all(r.allowed for r in results)
        # The 6th immediately after should still be blocked — capacity is 5,
        # not unbounded.
        sixth = await bucket.consume("key1", capacity=5, refill_per_second=1000)
        assert not sixth.allowed

    @pytest.mark.asyncio
    async def test_requesting_more_than_one_token_is_supported(self):
        bucket = InMemoryTokenBucket()
        result = await bucket.consume("key1", capacity=10, refill_per_second=0, tokens=5)
        assert result.allowed
        assert result.remaining_tokens == pytest.approx(5.0)

        # Another 5-token request should exactly exhaust the bucket.
        result2 = await bucket.consume("key1", capacity=10, refill_per_second=0, tokens=5)
        assert result2.allowed
        assert result2.remaining_tokens == pytest.approx(0.0)

        result3 = await bucket.consume("key1", capacity=10, refill_per_second=0, tokens=1)
        assert not result3.allowed


class TestGetRateLimiter:
    def test_returns_in_memory_bucket_when_no_redis_url(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "")
        from packages.shared.config import get_settings
        from packages.shared.rate_limit import InMemoryTokenBucket, get_rate_limiter

        get_settings.cache_clear()
        try:
            limiter = get_rate_limiter()
            assert isinstance(limiter, InMemoryTokenBucket)
        finally:
            get_settings.cache_clear()


class TestRateLimitMiddlewareIdentity:
    def test_falls_back_to_ip_when_no_session_cookie(self):
        from unittest.mock import MagicMock

        from services.api.rate_limit_middleware import RateLimitMiddleware

        middleware = RateLimitMiddleware.__new__(RateLimitMiddleware)
        request = MagicMock()
        request.cookies = {}
        request.client.host = "203.0.113.7"

        identity = middleware._identify(request)
        assert identity == "ip:203.0.113.7"

    def test_uses_session_identity_when_a_valid_cookie_is_present(self):
        from unittest.mock import MagicMock

        from packages.shared.auth import COOKIE_NAME, sign_session_id
        from services.api.rate_limit_middleware import RateLimitMiddleware

        session_id = "12345678-1234-5678-1234-567812345678"
        import uuid as uuid_module

        signed = sign_session_id(uuid_module.UUID(session_id))

        middleware = RateLimitMiddleware.__new__(RateLimitMiddleware)
        request = MagicMock()
        request.cookies = {COOKIE_NAME: signed}

        identity = middleware._identify(request)
        assert identity == f"user:{session_id}"
        assert not identity.startswith("ip:")

    def test_a_tampered_cookie_falls_back_to_ip_not_a_crash(self):
        from unittest.mock import MagicMock

        from packages.shared.auth import COOKIE_NAME
        from services.api.rate_limit_middleware import RateLimitMiddleware

        middleware = RateLimitMiddleware.__new__(RateLimitMiddleware)
        request = MagicMock()
        request.cookies = {COOKIE_NAME: "not-a-real-signed-value"}
        request.client.host = "203.0.113.7"

        identity = middleware._identify(request)
        assert identity == "ip:203.0.113.7"

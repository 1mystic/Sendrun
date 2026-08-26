"""Redis-backed token bucket rate limiting.

Two distinct uses in this codebase, both built on the same primitive:

1. **API request rate limiting** — a FastAPI middleware/dependency guarding
   against abuse (many requests from one user/IP in a short window).
2. **Send-rate throttling** — the worker's outbound email rate must respect
   the provider's own limit (Resend free tier: ~2/sec). This is the "Redis
   rate limiter" PLAN.md's Phase 3/4 scope called for and that Phase 4
   shipped without — see NEXT.md.

Both use the same Lua-scripted atomic token-bucket check, which matters
because a naive "GET, check, INCR" sequence has a race: two concurrent
requests can both read the same pre-increment count and both pass, letting
through 2x the intended limit. The Lua script makes read-check-write atomic
inside Redis itself, so this doesn't happen no matter how many workers/API
instances share the same bucket.

Falls back to an in-process (non-distributed) limiter when no Redis URL is
configured — correct for local dev and tests, but NOT safe across multiple
processes/instances in production. See RateLimiter.__init__'s docstring.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

# Atomic token-bucket check-and-consume. KEYS[1] is the bucket key.
# ARGV: capacity, refill_rate_per_second, now, requested_tokens.
#
# Lazily refills based on elapsed time since the last update — no background
# job needed, and no bucket ever needs to be pre-initialized.
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local bucket = redis.call('HMGET', key, 'tokens', 'updated_at')
local tokens = tonumber(bucket[1])
local updated_at = tonumber(bucket[2])

if tokens == nil then
    tokens = capacity
    updated_at = now
end

local elapsed = math.max(now - updated_at, 0)
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
if tokens >= requested then
    tokens = tokens - requested
    allowed = 1
end

redis.call('HMSET', key, 'tokens', tokens, 'updated_at', now)
redis.call('EXPIRE', key, ttl)

return {allowed, tokens}
"""


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    remaining_tokens: float


class InMemoryTokenBucket:
    """Single-process fallback. Correct for local dev and the test suite,
    where there is exactly one process — NOT safe as a production rate
    limiter across multiple API/worker instances, since each process would
    have its own independent bucket and the real aggregate rate could
    exceed the intended limit by (number of instances)x."""

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, updated_at)

    async def consume(
        self, key: str, *, capacity: float, refill_per_second: float, tokens: float = 1.0
    ) -> RateLimitResult:
        now = time.monotonic()
        current_tokens, updated_at = self._buckets.get(key, (capacity, now))
        elapsed = max(now - updated_at, 0)
        current_tokens = min(capacity, current_tokens + elapsed * refill_per_second)

        if current_tokens >= tokens:
            current_tokens -= tokens
            self._buckets[key] = (current_tokens, now)
            return RateLimitResult(allowed=True, remaining_tokens=current_tokens)

        self._buckets[key] = (current_tokens, now)
        return RateLimitResult(allowed=False, remaining_tokens=current_tokens)


class RedisTokenBucket:
    """The real, distributed-safe limiter — every process sharing the same
    Redis instance shares the same bucket, so the aggregate rate across N
    API instances or worker processes stays correctly bounded."""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client
        self._script = redis_client.register_script(_TOKEN_BUCKET_LUA)

    async def consume(
        self, key: str, *, capacity: float, refill_per_second: float,
        tokens: float = 1.0, ttl_seconds: int = 3600,
    ) -> RateLimitResult:
        now = time.time()
        allowed, remaining = await self._script(
            keys=[f"ratelimit:{key}"],
            args=[capacity, refill_per_second, now, tokens, ttl_seconds],
        )
        return RateLimitResult(allowed=bool(allowed), remaining_tokens=float(remaining))


def get_rate_limiter():
    """Selects Redis-backed or in-memory based on REDIS_URL — the same
    fake-first pattern as the email/LLM providers. Callers depend on the
    `.consume()` interface both implementations share, never on which one
    is active."""
    from packages.shared.config import get_settings

    settings = get_settings()
    if not settings.redis_url:
        return InMemoryTokenBucket()

    import redis.asyncio as aioredis

    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return RedisTokenBucket(client)

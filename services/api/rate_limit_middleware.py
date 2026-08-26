"""Per-user (or per-IP, if unauthenticated) API rate limiting middleware.

Deliberately coarse — one global limit per identity, not per-endpoint tuning.
A student-project API serving a handful of orgs does not need the endpoint-
by-endpoint rate budgets a real multi-tenant SaaS would; the point here is
demonstrating the mechanism is real (Redis-backed, atomic, correctly bounded
across multiple processes) and wired into the request path, not a
comprehensive rate-limiting policy.
"""

from __future__ import annotations

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

from packages.shared.auth import COOKIE_NAME, unsign_session_id
from packages.shared.rate_limit import get_rate_limiter

DEFAULT_CAPACITY = 60.0       # burst allowance
DEFAULT_REFILL_PER_SECOND = 1.0  # steady-state: 60 req/min


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, capacity: float = DEFAULT_CAPACITY,
                 refill_per_second: float = DEFAULT_REFILL_PER_SECOND) -> None:
        super().__init__(app)
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self._limiter = get_rate_limiter()

    async def dispatch(self, request: Request, call_next):
        # Webhooks are excluded — they're rate-limited by the PROVIDER's own
        # send rate, not by us, and rejecting a legitimate webhook delivery
        # would cause the provider to retry it, working against the exact
        # dedup/ack-fast design in services/api/webhooks/ingest.py.
        if request.url.path.startswith("/api/webhooks"):
            return await call_next(request)

        identity = self._identify(request)
        result = await self._limiter.consume(
            identity, capacity=self.capacity, refill_per_second=self.refill_per_second,
        )
        if not result.allowed:
            return Response(
                content='{"detail":"rate limit exceeded"}',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
                headers={"Retry-After": "1"},
            )
        return await call_next(request)

    def _identify(self, request: Request) -> str:
        """Prefer the authenticated user (from the session cookie) over IP —
        a shared NAT/office IP must not throttle every user behind it
        together. Falls back to IP only when there's no valid session."""
        cookie = request.cookies.get(COOKIE_NAME)
        if cookie:
            session_id = unsign_session_id(cookie)
            if session_id is not None:
                return f"user:{session_id}"
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

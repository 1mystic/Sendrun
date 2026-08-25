"""A fake email provider that is a feature, not a stub.

Three things make it worth real effort:

1. **It has a genuine idempotency cache.** Re-sending with a used key returns the
   original message id and sets `idempotent_replay=True` instead of sending again.
   Without this the crash demo would prove nothing - the whole exactly-once claim is
   only observable because the fake enforces the same contract a real provider does.

2. **Its chaos is deterministic.** Every outcome is drawn from a PRNG seeded by
   (seed, idempotency_key), so a given job has the same fate on every run: the same
   bounces, the same transient failures, the same races. Demos are repeatable and
   tests are not flaky.

3. **It emits real webhooks.** Signed with HMAC, delivered asynchronously, optionally
   duplicated, delayed, reordered - or fired BEFORE `send()` returns, which is what
   reproduces the orphan-event race on demand.

Everything runs offline. No API keys.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .base import (
    EmailProvider,
    PermanentProviderError,
    ProviderEvent,
    SendRequest,
    SendResponse,
    TransientProviderError,
)


@dataclass(slots=True)
class ChaosConfig:
    """Failure injection knobs. Surfaced live in the Chaos Mode panel."""

    # ── send-path failures ──────────────────────────────────────────────
    latency_ms: tuple[int, int] = (40, 260)
    transient_error_rate: float = 0.05   # 5xx  -> retried with backoff
    rate_limit_rate: float = 0.02        # 429  -> retried, honours retry_after
    permanent_error_rate: float = 0.01   # 4xx  -> fails without retry

    # ── delivery outcomes (decided at send, delivered via webhook) ──────
    hard_bounce_rate: float = 0.03
    soft_bounce_rate: float = 0.02
    complaint_rate: float = 0.005
    open_rate: float = 0.40
    click_rate: float = 0.12

    # ── webhook chaos ───────────────────────────────────────────────────
    webhook_delay_ms: tuple[int, int] = (100, 4000)
    webhook_duplicate_rate: float = 0.10
    webhook_out_of_order: bool = True
    # The money knob: fire `sent` BEFORE send() returns, so the event arrives while the
    # job row still has no provider_message_id. Forces the orphan-event race on demand.
    webhook_before_send_ack_rate: float = 0.05

    seed: int = 42

    @classmethod
    def quiet(cls) -> ChaosConfig:
        """No failures. For tests asserting the happy path."""
        return cls(
            transient_error_rate=0.0, rate_limit_rate=0.0, permanent_error_rate=0.0,
            hard_bounce_rate=0.0, soft_bounce_rate=0.0, complaint_rate=0.0,
            webhook_duplicate_rate=0.0, webhook_before_send_ack_rate=0.0,
            latency_ms=(0, 0), webhook_delay_ms=(0, 0),
        )


class _MemoryIdempotencyCache:
    """Default cache. Redis-backed in deployment; this keeps tests dependency-free."""

    def __init__(self) -> None:
        self._d: dict[str, tuple[str, datetime]] = {}

    async def get(self, key: str) -> tuple[str, datetime] | None:
        return self._d.get(key)

    async def put(self, key: str, message_id: str, at: datetime) -> bool:
        """Returns True if this call created the entry (i.e. we are the first sender)."""
        if key in self._d:
            return False
        self._d[key] = (message_id, at)
        return True


class FakeEmailProvider(EmailProvider):
    name = "fake"

    def __init__(
        self,
        chaos: ChaosConfig | None = None,
        *,
        webhook_sink: Callable[[bytes, dict[str, str]], Awaitable[None]] | None = None,
        secret: str = "fake-webhook-secret",
        cache: Any | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.chaos = chaos or ChaosConfig()
        self._sink = webhook_sink
        self._secret = secret.encode()
        self._cache = cache or _MemoryIdempotencyCache()
        self._sleep = sleep

        # How many times send() has been entered per key. Folded into the failure
        # draw so a retry is an INDEPENDENT trial rather than a replay of the same
        # verdict. Without this a job that draws a transient failure would draw it
        # forever and never succeed - deterministic, but not a faithful simulation
        # of a transient fault. Determinism is preserved: attempt N of a given key
        # always has the same outcome across runs.
        self._attempts: dict[str, int] = {}

        # Observability for tests and the demo. `send_calls` counts every entry into
        # send(); `provider_sends` counts only those that actually produced a NEW
        # message. The invariant the whole project defends is:
        #     provider_sends == len(unique idempotency keys)
        # regardless of how many crashes and retries happened.
        self.send_calls = 0
        self.provider_sends = 0
        self.idempotent_replays = 0
        self._pending: list[asyncio.Task[None]] = []

    # ── deterministic randomness ────────────────────────────────────────
    def _rng(self, key: str, salt: str = "") -> random.Random:
        h = hashlib.sha256(f"{self.chaos.seed}:{key}:{salt}".encode()).digest()
        return random.Random(int.from_bytes(h[:8], "big"))

    async def send(self, req: SendRequest) -> SendResponse:
        self.send_calls += 1

        # ── 1. Idempotency check, before anything else ──────────────────
        # A crashed-and-retried send lands here and returns the original result.
        cached = await self._cache.get(req.idempotency_key)
        if cached is not None:
            mid, at = cached
            self.idempotent_replays += 1
            return SendResponse(mid, at, idempotent_replay=True)

        # Each entry is a fresh trial for this key. Seeded by (seed, key, attempt),
        # so runs stay reproducible while retries can genuinely succeed.
        n = self._attempts[req.idempotency_key] = (
            self._attempts.get(req.idempotency_key, 0) + 1
        )
        rng = self._rng(req.idempotency_key, f"attempt{n}")

        await self._sleep(rng.uniform(*self.chaos.latency_ms) / 1000.0)

        # ── 2. Injected failures ────────────────────────────────────────
        roll = rng.random()
        c = self.chaos
        if roll < c.permanent_error_rate:
            raise PermanentProviderError(
                f"invalid recipient: {req.to}", reason="invalid_address"
            )
        if roll < c.permanent_error_rate + c.rate_limit_rate:
            raise TransientProviderError("429 rate limit exceeded", retry_after=1.0)
        if roll < c.permanent_error_rate + c.rate_limit_rate + c.transient_error_rate:
            raise TransientProviderError("503 service unavailable")

        # ── 3. Accept, and claim the key ────────────────────────────────
        now = datetime.now(UTC)
        mid = "msg_" + hashlib.sha1(req.idempotency_key.encode()).hexdigest()[:20]

        created = await self._cache.put(req.idempotency_key, mid, now)
        if not created:
            # Lost a race with a concurrent send of the same key. The other caller
            # created the entry; adopt its result rather than double-sending.
            existing = await self._cache.get(req.idempotency_key)
            assert existing is not None
            self.idempotent_replays += 1
            return SendResponse(existing[0], existing[1], idempotent_replay=True)

        self.provider_sends += 1

        # ── 4. Schedule webhooks ────────────────────────────────────────
        if self._sink is not None:
            if rng.random() < c.webhook_before_send_ack_rate:
                # Deliver `sent` synchronously, BEFORE returning. The caller has not
                # recorded the message id yet, so this event arrives orphaned.
                await self._emit(mid, req, "sent", now)
                self._schedule_outcome(mid, req, now, skip_sent=True)
            else:
                self._schedule_outcome(mid, req, now, skip_sent=False)

        return SendResponse(mid, now, idempotent_replay=False)

    # ── webhook emission ────────────────────────────────────────────────
    def _schedule_outcome(
        self, mid: str, req: SendRequest, sent_at: datetime, *, skip_sent: bool
    ) -> None:
        task = asyncio.create_task(self._deliver_outcome(mid, req, sent_at, skip_sent))
        self._pending.append(task)
        task.add_done_callback(lambda t: self._pending.remove(t) if t in self._pending else None)

    async def _deliver_outcome(
        self, mid: str, req: SendRequest, sent_at: datetime, skip_sent: bool
    ) -> None:
        rng = self._rng(req.idempotency_key, "wh")
        c = self.chaos

        events: list[tuple[str, datetime, str | None]] = []
        if not skip_sent:
            events.append(("sent", sent_at, None))

        t = sent_at
        if rng.random() < c.hard_bounce_rate:
            t += timedelta(seconds=rng.uniform(1, 6))
            events.append(("bounced", t, "550 5.1.1 mailbox unavailable"))
        elif rng.random() < c.soft_bounce_rate:
            t += timedelta(seconds=rng.uniform(1, 4))
            events.append(("deferred", t, "451 4.7.1 try again later"))
            t += timedelta(seconds=rng.uniform(5, 20))
            events.append(("delivered", t, None))
        else:
            t += timedelta(seconds=rng.uniform(1, 5))
            events.append(("delivered", t, None))

            if rng.random() < c.open_rate:
                t += timedelta(seconds=rng.uniform(20, 600))
                events.append(("opened", t, None))
                if rng.random() < c.click_rate:
                    t += timedelta(seconds=rng.uniform(5, 90))
                    events.append(("clicked", t, None))
            if rng.random() < c.complaint_rate:
                t += timedelta(seconds=rng.uniform(60, 900))
                events.append(("complained", t, None))

        # Reorder before sending: real providers do not guarantee order, and the
        # consumer must not depend on it. The precedence-rank logic in transitions.py
        # is what makes this survivable.
        if c.webhook_out_of_order and len(events) > 1 and rng.random() < 0.35:
            i = rng.randrange(len(events) - 1)
            events[i], events[i + 1] = events[i + 1], events[i]

        for kind, occurred, reason in events:
            await self._sleep(rng.uniform(*c.webhook_delay_ms) / 1000.0)
            await self._emit(mid, req, kind, occurred, reason)
            if rng.random() < c.webhook_duplicate_rate:
                # Same provider_event_id: the consumer must dedup on it.
                await self._emit(mid, req, kind, occurred, reason)

    async def _emit(
        self,
        mid: str,
        req: SendRequest,
        kind: str,
        occurred: datetime,
        reason: str | None = None,
    ) -> None:
        if self._sink is None:
            return
        eid = "evt_" + hashlib.sha1(
            f"{mid}:{kind}:{occurred.isoformat()}".encode()
        ).hexdigest()[:20]
        body = json.dumps({
            "id": eid,
            "type": f"email.{kind}",
            "created_at": occurred.isoformat(),
            "data": {
                "message_id": mid,
                "to": req.to,
                "subject": req.subject,
                "reason": reason,
                "tags": req.tags,
            },
        }).encode()
        sig = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        await self._sink(body, {"x-fake-signature": sig, "x-fake-event-id": eid})

    # ── EmailProvider protocol ──────────────────────────────────────────
    def verify_webhook(self, headers: dict[str, str], body: bytes) -> bool:
        got = headers.get("x-fake-signature", "")
        want = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(got, want)

    def parse_webhook(self, body: bytes) -> list[ProviderEvent]:
        d = json.loads(body)
        data = d.get("data", {})
        return [ProviderEvent(
            provider_event_id=d["id"],
            provider_message_id=data["message_id"],
            event_type=d["type"].removeprefix("email."),  # type: ignore[arg-type]
            occurred_at=datetime.fromisoformat(d["created_at"]),
            raw=d,
            recipient=data.get("to"),
            reason=data.get("reason"),
        )]

    async def drain(self) -> None:
        """Await all in-flight webhook deliveries. For deterministic tests."""
        while self._pending:
            await asyncio.gather(*list(self._pending), return_exceptions=True)

    @property
    def duplicate_sends(self) -> int:
        """The invariant. Must be zero after any number of crashes and retries."""
        excess = self.provider_sends - self._unique_keys()
        return max(excess, 0)

    def _unique_keys(self) -> int:
        cache = self._cache
        return len(getattr(cache, "_d", {}))

"""The email provider boundary.

Callers - above all `send_email_task` - branch only on TransientProviderError vs
PermanentProviderError. Every provider-specific detail (status code mapping, auth,
payload shape, webhook signature scheme) lives inside an implementation. That is what
lets `FakeEmailProvider` and `ResendProvider` be swapped by an env var with no change
to calling code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

# ─────────────────────────────────────────────────────────────────────────────
# Wire types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Attachment:
    """Attachments travel as object-storage keys, never as bytes.

    Bytes in a task payload would bloat the queue table and blow past row limits on a
    10MB PDF. The provider fetches content at send time from the key.
    """

    filename: str
    storage_key: str
    content_type: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class SendRequest:
    idempotency_key: str
    to: str
    from_addr: str
    subject: str
    html: str
    text: str | None = None
    reply_to: str | None = None
    attachments: tuple[Attachment, ...] = ()
    # Echoed back on webhooks so events can be correlated even if our own
    # message_id write has not landed yet.
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SendResponse:
    provider_message_id: str
    accepted_at: datetime
    # True when the provider recognised the idempotency key and returned the original
    # result instead of sending again. This is the signal that proves exactly-once
    # behaviour after a crash, and the dashboard surfaces it directly.
    idempotent_replay: bool = False


EventType = Literal[
    "sent", "delivered", "deferred", "bounced", "complained", "opened", "clicked"
]


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    """A normalized webhook event.

    `provider_event_id` is the dedup key - unique per event, stable across the
    provider's own delivery retries. `occurred_at` is the provider's timestamp, never
    our receive time: ordering by arrival is exactly the bug that reordering causes.
    """

    provider_event_id: str
    provider_message_id: str
    event_type: EventType
    occurred_at: datetime
    raw: dict
    recipient: str | None = None
    reason: str | None = None
    url: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Errors - the actual contract
# ─────────────────────────────────────────────────────────────────────────────

class ProviderError(Exception):
    pass


class TransientProviderError(ProviderError):
    """5xx, 429, timeouts, connection resets. Retry with backoff."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class PermanentProviderError(ProviderError):
    """4xx. Retrying cannot help; do not consume the retry budget."""

    def __init__(
        self,
        message: str,
        *,
        reason: Literal[
            "invalid_address", "suppressed", "payload_too_large", "rejected", "unauthorized"
        ] = "rejected",
    ) -> None:
        super().__init__(message)
        self.reason = reason


# ─────────────────────────────────────────────────────────────────────────────
# The interface
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class EmailProvider(Protocol):
    name: str

    async def send(self, req: SendRequest) -> SendResponse:
        """Send one email.

        MUST honour `req.idempotency_key`: if the same key is seen again, return the
        original SendResponse with `idempotent_replay=True` rather than sending a second
        message. This is the guarantee the whole durability story rests on.

        Raises TransientProviderError or PermanentProviderError - never a bare
        exception, and never a provider-specific error type.
        """
        ...

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> bool:
        """Verify the signature over the RAW body. Never parse before verifying."""
        ...

    def parse_webhook(self, body: bytes) -> list[ProviderEvent]:
        """Normalize a payload into events. One request may carry several."""
        ...

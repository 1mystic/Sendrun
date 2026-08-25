"""The single enforced writer for all Campaign and EmailJob state changes.

Every status write in the system goes through this module. Nothing else may issue a
bare `UPDATE ... SET status = ...`. Two properties make the system correct under
retries, crashes, and duplicate/out-of-order provider events:

**Guarded.** Every transition names its allowed predecessors and writes with
`WHERE status IN (<predecessors>)`. A write from a stale actor affects zero rows and
returns None instead of corrupting state.

**Monotonic.** Delivery outcomes are ranked, not sequenced. A late-arriving event can
never move a job backwards. This is why `opened`/`clicked` are deliberately NOT part
of the delivery axis - see DELIVERY_RANK below.

The two axes on EmailJob are orthogonal and must never be collapsed into one column:

    send_status      owned by the worker      queued -> sending -> sent | failed_*
    delivery_status  owned by webhooks        NULL -> delivered | bounced | complained

Collapsing them would make a `delivered` webhook overwrite `sent`, losing the record
of whether we actually completed the send - and would let engagement events clobber
terminal failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

# ─────────────────────────────────────────────────────────────────────────────
# Campaign
# ─────────────────────────────────────────────────────────────────────────────

class CampaignStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    LAUNCHING = "launching"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


CAMPAIGN_TERMINAL: Final[frozenset[CampaignStatus]] = frozenset({
    CampaignStatus.COMPLETED,
    CampaignStatus.CANCELLED,
    CampaignStatus.FAILED,
})

# to -> allowed predecessors
CAMPAIGN_TRANSITIONS: Final[dict[CampaignStatus, frozenset[CampaignStatus]]] = {
    CampaignStatus.SCHEDULED: frozenset({CampaignStatus.DRAFT}),
    CampaignStatus.LAUNCHING: frozenset({CampaignStatus.DRAFT, CampaignStatus.SCHEDULED}),
    # LAUNCHING -> RUNNING is the normal path. The janitor may also re-drive a campaign
    # stuck in LAUNCHING (process died between COMMIT and enqueue), so RUNNING is
    # reachable from RUNNING itself: re-driving must be a harmless no-op, not an error.
    CampaignStatus.RUNNING: frozenset({
        CampaignStatus.LAUNCHING,
        CampaignStatus.PAUSED,
        CampaignStatus.RUNNING,
    }),
    CampaignStatus.PAUSED: frozenset({CampaignStatus.RUNNING}),
    CampaignStatus.COMPLETED: frozenset({CampaignStatus.RUNNING, CampaignStatus.PAUSED}),
    CampaignStatus.CANCELLED: frozenset({
        CampaignStatus.DRAFT,
        CampaignStatus.SCHEDULED,
        CampaignStatus.LAUNCHING,
        CampaignStatus.RUNNING,
        CampaignStatus.PAUSED,
    }),
    CampaignStatus.FAILED: frozenset({
        CampaignStatus.LAUNCHING,
        CampaignStatus.RUNNING,
        CampaignStatus.PAUSED,
    }),
}


# ─────────────────────────────────────────────────────────────────────────────
# EmailJob - axis 1: send status (worker-owned)
# ─────────────────────────────────────────────────────────────────────────────

class SendStatus(StrEnum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    FAILED_TRANSIENT = "failed_transient"
    FAILED_PERMANENT = "failed_permanent"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


SEND_TERMINAL: Final[frozenset[SendStatus]] = frozenset({
    SendStatus.SENT,
    SendStatus.FAILED_PERMANENT,
    SendStatus.CANCELLED,
    SendStatus.SKIPPED,
})

SEND_TRANSITIONS: Final[dict[SendStatus, frozenset[SendStatus]]] = {
    # The claim step. SENDING is reachable from SENDING so a retry after a crash
    # mid-send can re-claim its own row rather than deadlocking on it.
    SendStatus.SENDING: frozenset({
        SendStatus.QUEUED,
        SendStatus.SENDING,
        SendStatus.FAILED_TRANSIENT,
    }),
    SendStatus.SENT: frozenset({SendStatus.SENDING}),
    SendStatus.FAILED_TRANSIENT: frozenset({SendStatus.SENDING}),
    SendStatus.FAILED_PERMANENT: frozenset({SendStatus.SENDING, SendStatus.QUEUED}),
    SendStatus.CANCELLED: frozenset({SendStatus.QUEUED, SendStatus.FAILED_TRANSIENT}),
    SendStatus.SKIPPED: frozenset({SendStatus.QUEUED}),
}


# ─────────────────────────────────────────────────────────────────────────────
# EmailJob - axis 2: delivery status (webhook-owned)
# ─────────────────────────────────────────────────────────────────────────────

class DeliveryStatus(StrEnum):
    DEFERRED = "deferred"
    DELIVERED = "delivered"
    BOUNCED = "bounced"
    COMPLAINED = "complained"


# Precedence, not sequence. Provider events arrive out of order and duplicated;
# an event is applied only when it outranks what is already recorded.
#
# `complained` outranks `bounced` outranks `delivered`: a spam complaint is the most
# consequential fact about a send and must never be overwritten by a late `delivered`.
#
# Note what is absent: `opened` and `clicked`. They are not delivery states. They live
# in `email_engagements` with counters on the job row. If `opened` were ranked here, a
# late open would clobber a bounce - a subtle bug that only shows up in production.
DELIVERY_RANK: Final[dict[DeliveryStatus | None, int]] = {
    None: 0,
    DeliveryStatus.DEFERRED: 1,
    DeliveryStatus.DELIVERED: 3,
    DeliveryStatus.BOUNCED: 90,
    DeliveryStatus.COMPLAINED: 95,
}

DELIVERY_TERMINAL: Final[frozenset[DeliveryStatus]] = frozenset({
    DeliveryStatus.BOUNCED,
    DeliveryStatus.COMPLAINED,
})


# ─────────────────────────────────────────────────────────────────────────────
# Errors and results
# ─────────────────────────────────────────────────────────────────────────────

class IllegalTransition(Exception):
    """Raised when a transition is not permitted by the state machine at all.

    Distinct from a *lost race*, which is not an error: losing a race returns
    `applied=False` because some other actor legitimately got there first.
    """

    def __init__(self, entity: str, frm: str | None, to: str) -> None:
        self.entity, self.frm, self.to = entity, frm, to
        super().__init__(f"{entity}: {frm} -> {to} is not a legal transition")


@dataclass(frozen=True, slots=True)
class TransitionResult:
    """Outcome of an attempted transition.

    `applied=False` with no exception means the guard matched zero rows - a concurrent
    actor already moved the row. Callers should treat that as normal and re-read, never
    as a failure to retry.
    """

    applied: bool
    from_status: str | None
    to_status: str
    reason: str = ""

    def __bool__(self) -> bool:
        return self.applied


# ─────────────────────────────────────────────────────────────────────────────
# Pure guards - no I/O, exhaustively unit-testable
# ─────────────────────────────────────────────────────────────────────────────

def allowed_campaign_predecessors(to: CampaignStatus) -> frozenset[CampaignStatus]:
    if to not in CAMPAIGN_TRANSITIONS:
        raise IllegalTransition("Campaign", None, to)
    return CAMPAIGN_TRANSITIONS[to]


def allowed_send_predecessors(to: SendStatus) -> frozenset[SendStatus]:
    if to not in SEND_TRANSITIONS:
        raise IllegalTransition("EmailJob.send_status", None, to)
    return SEND_TRANSITIONS[to]


def can_transition_campaign(frm: CampaignStatus, to: CampaignStatus) -> bool:
    return to in CAMPAIGN_TRANSITIONS and frm in CAMPAIGN_TRANSITIONS[to]


def can_transition_send(frm: SendStatus, to: SendStatus) -> bool:
    return to in SEND_TRANSITIONS and frm in SEND_TRANSITIONS[to]


def outranks(new: DeliveryStatus, current: DeliveryStatus | None) -> bool:
    """True when a delivery event should be applied over what is recorded.

    Strictly greater, so a duplicate of the current status is discarded rather than
    rewritten - which keeps `first_*_at` timestamps stable under webhook replay.
    """
    return DELIVERY_RANK[new] > DELIVERY_RANK[current]


def is_campaign_terminal(s: CampaignStatus) -> bool:
    return s in CAMPAIGN_TERMINAL


def is_send_terminal(s: SendStatus) -> bool:
    return s in SEND_TERMINAL

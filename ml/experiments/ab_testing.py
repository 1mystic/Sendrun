"""A/B subject-line testing: real randomization + a proper significance test,
not "compare two percentages and eyeball it."

Two things make this a real experimentation system rather than decoration:

1. **Randomization is deterministic per-recipient, not per-request.** A
   contact assigned to variant A for a campaign must STAY on variant A even
   if the assignment function is called again (e.g. a retry, a preview
   re-render) — otherwise a single contact could see both variants, which
   contaminates the experiment. Assignment is a hash of (campaign_id,
   contact_id), not a live coin flip.

2. **Significance uses a two-proportion z-test**, not "A is bigger than B."
   A result is only reported as a winner when it clears both a minimum
   sample size AND a p-value threshold — an underpowered experiment reports
   "not yet significant," not a false winner.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from scipy.stats import norm

Variant = Literal["A", "B"]

# Below this many observations per arm, a significance test is unreliable
# regardless of what p-value it reports — the normal approximation the
# z-test relies on breaks down for small samples. Below this, report
# "insufficient data," not a number that looks precise but isn't.
MIN_SAMPLE_SIZE_PER_ARM = 100
SIGNIFICANCE_ALPHA = 0.05


def assign_variant(campaign_id: str, contact_id: str, *, split: float = 0.5) -> Variant:
    """Deterministic 50/50 (or custom-split) assignment. The same
    (campaign_id, contact_id) pair always returns the same variant — a retry
    of a failed send, or the compose screen re-rendering a preview, must
    never flip a contact from A to B mid-experiment."""
    digest = hashlib.sha256(f"{campaign_id}:{contact_id}".encode()).hexdigest()
    # First 8 hex chars -> a float in [0, 1), uniform by construction of sha256.
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return "A" if bucket < split else "B"


@dataclass(frozen=True, slots=True)
class ArmResult:
    variant: Variant
    sent: int
    opened: int

    @property
    def open_rate(self) -> float:
        return self.opened / self.sent if self.sent else 0.0


@dataclass(frozen=True, slots=True)
class SignificanceResult:
    winner: Variant | None  # None if not yet significant, or a tie
    p_value: float | None
    z_statistic: float | None
    is_significant: bool
    has_sufficient_data: bool
    arm_a: ArmResult
    arm_b: ArmResult
    lift: float | None  # relative lift of B over A, if computable


def two_proportion_z_test(arm_a: ArmResult, arm_b: ArmResult) -> SignificanceResult:
    """Standard two-proportion z-test for independent samples. Returns a
    result object that forces the caller to check has_sufficient_data before
    trusting is_significant — an underpowered test's p-value is not
    meaningful, and a caller that skips this check would report false
    winners on small early samples, exactly the mistake real A/B tooling
    exists to prevent."""
    has_sufficient_data = (
        arm_a.sent >= MIN_SAMPLE_SIZE_PER_ARM and arm_b.sent >= MIN_SAMPLE_SIZE_PER_ARM
    )
    if not has_sufficient_data:
        return SignificanceResult(
            winner=None, p_value=None, z_statistic=None,
            is_significant=False, has_sufficient_data=False,
            arm_a=arm_a, arm_b=arm_b, lift=None,
        )

    p1, p2 = arm_a.open_rate, arm_b.open_rate
    n1, n2 = arm_a.sent, arm_b.sent

    pooled_p = (arm_a.opened + arm_b.opened) / (n1 + n2)
    se = (pooled_p * (1 - pooled_p) * (1 / n1 + 1 / n2)) ** 0.5

    if se == 0:
        # Both arms identical (including both-zero) — no detectable difference.
        return SignificanceResult(
            winner=None, p_value=1.0, z_statistic=0.0,
            is_significant=False, has_sufficient_data=True,
            arm_a=arm_a, arm_b=arm_b, lift=0.0,
        )

    z = float((p2 - p1) / se)
    p_value = float(2 * (1 - norm.cdf(abs(z))))  # two-tailed
    # bool()/float(), not the bare values — scipy/numpy operations upstream
    # (norm.cdf, the arithmetic here) return numpy scalar types, and
    # np.True_/np.False_ fail `is True`/`is False` identity checks even
    # though they're truthy — a real trap for any caller (including a
    # FastAPI response model, which would silently serialize a numpy scalar
    # oddly) that does an identity comparison rather than a truthiness check.
    is_significant = bool(p_value < SIGNIFICANCE_ALPHA)

    lift = float((p2 - p1) / p1) if p1 > 0 else None
    winner: Variant | None = None
    if is_significant:
        winner = "B" if p2 > p1 else "A"

    return SignificanceResult(
        winner=winner, p_value=p_value, z_statistic=z,
        is_significant=is_significant, has_sufficient_data=True,
        arm_a=arm_a, arm_b=arm_b, lift=lift,
    )


def summarize(result: SignificanceResult) -> str:
    if not result.has_sufficient_data:
        needed = MIN_SAMPLE_SIZE_PER_ARM
        return (
            f"Not enough data yet — need {needed}+ sends per variant "
            f"(have A={result.arm_a.sent}, B={result.arm_b.sent})."
        )

    a_pct, b_pct = result.arm_a.open_rate, result.arm_b.open_rate
    if not result.is_significant:
        return (
            f"No significant difference yet (p={result.p_value:.3f}). "
            f"A: {a_pct:.1%} ({result.arm_a.opened}/{result.arm_a.sent}), "
            f"B: {b_pct:.1%} ({result.arm_b.opened}/{result.arm_b.sent})."
        )

    lift_pct = (result.lift or 0.0) * 100
    return (
        f"Variant {result.winner} wins (p={result.p_value:.4f}). "
        f"A: {a_pct:.1%}, B: {b_pct:.1%} — {abs(lift_pct):.1f}% "
        f"{'lift' if lift_pct > 0 else 'drop'} for B vs A."
    )

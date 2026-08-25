"""Stage 11: drift detection — PSI (Population Stability Index) for feature
drift, KS-test for prediction-distribution drift.

No live production traffic exists yet (Sendrun has never sent a real email),
so this cannot be wired to a real monitoring dashboard today — see NEXT.md.
What IS real: the detection mechanism itself, implemented correctly and
proven against synthetic drift below and in tests/test_drift.py. When real
traffic exists, the only new code needed is a scheduled job feeding it two
windows of real feature/prediction data instead of two synthetic ones.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import ks_2samp

# Conventional thresholds (Google/industry standard for PSI):
#   < 0.1  no significant shift
#   0.1-0.25  moderate shift, worth investigating
#   > 0.25  major shift, retraining likely needed
PSI_WARN_THRESHOLD = 0.10
PSI_ALERT_THRESHOLD = 0.25
KS_ALERT_P_VALUE = 0.01  # reject null (same distribution) at 99% confidence


@dataclass(frozen=True, slots=True)
class DriftResult:
    feature: str
    psi: float
    severity: str  # "none" | "warning" | "alert"


def population_stability_index(
    reference: np.ndarray, current: np.ndarray, *, n_bins: int = 10
) -> float:
    """PSI compares two distributions by binning the REFERENCE window and
    checking how much probability mass shifted between bins in the CURRENT
    window. Quantile bins (not equal-width) so each reference bin starts with
    equal weight, which is what makes the resulting PSI value comparable
    across features with very different scales."""
    quantiles = np.linspace(0, 1, n_bins + 1)
    bin_edges = np.unique(np.quantile(reference, quantiles))
    if len(bin_edges) < 3:
        # Degenerate reference distribution (e.g. a near-constant feature) —
        # PSI is not meaningful here; report 0 rather than divide-by-zero noise.
        return 0.0

    ref_counts, _ = np.histogram(reference, bins=bin_edges)
    cur_counts, _ = np.histogram(current, bins=bin_edges)

    ref_pct = np.clip(ref_counts / max(len(reference), 1), 1e-6, None)
    cur_pct = np.clip(cur_counts / max(len(current), 1), 1e-6, None)

    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def classify_psi(psi: float) -> str:
    if psi >= PSI_ALERT_THRESHOLD:
        return "alert"
    if psi >= PSI_WARN_THRESHOLD:
        return "warning"
    return "none"


def check_feature_drift(
    reference: dict[str, np.ndarray], current: dict[str, np.ndarray]
) -> list[DriftResult]:
    """One PSI per feature present in both windows. Missing-in-current is
    itself worth flagging separately (a schema change, not drift) — this
    function's contract is: give it two dicts of the SAME feature names."""
    results = []
    for feature in reference:
        if feature not in current:
            continue
        psi = population_stability_index(reference[feature], current[feature])
        results.append(DriftResult(feature=feature, psi=psi, severity=classify_psi(psi)))
    return sorted(results, key=lambda r: r.psi, reverse=True)


def check_prediction_drift(
    reference_predictions: np.ndarray, current_predictions: np.ndarray
) -> tuple[bool, float, float]:
    """KS-test on the model's OWN output distribution — catches drift the
    per-feature PSI check might miss (e.g. a shift in how features
    INTERACT, which individually-marginal PSI can't see). Returns
    (drifted, ks_statistic, p_value)."""
    statistic, p_value = ks_2samp(reference_predictions, current_predictions)
    drifted = p_value < KS_ALERT_P_VALUE
    return drifted, float(statistic), float(p_value)


def summarize(results: list[DriftResult]) -> str:
    lines = ["Drift report:"]
    for r in results:
        marker = {"none": "  ", "warning": "⚠ ", "alert": "✕ "}[r.severity]
        lines.append(f"  {marker}{r.feature}: PSI={r.psi:.4f} [{r.severity}]")
    n_alert = sum(1 for r in results if r.severity == "alert")
    n_warn = sum(1 for r in results if r.severity == "warning")
    lines.append(f"\n{n_alert} alert, {n_warn} warning, {len(results) - n_alert - n_warn} stable")
    return "\n".join(lines)


if __name__ == "__main__":
    # Self-demonstration: prove the mechanism actually detects a real shift,
    # since there is no live traffic to point it at yet.
    rng = np.random.default_rng(0)

    reference = {
        "prior_bounce_rate": rng.beta(2, 20, size=5000),  # mostly low bounce rate
        "contact_age_days": rng.exponential(400, size=5000),
    }
    # Simulate a genuine shift: a bad list import spikes prior_bounce_rate.
    current_drifted = {
        "prior_bounce_rate": rng.beta(8, 12, size=2000),  # shifted much higher
        "contact_age_days": rng.exponential(400, size=2000),  # unchanged
    }
    current_stable = {
        "prior_bounce_rate": rng.beta(2, 20, size=2000),  # same distribution
        "contact_age_days": rng.exponential(410, size=2000),  # trivial noise
    }

    print("=== scenario: a genuinely drifted feature ===")
    print(summarize(check_feature_drift(reference, current_drifted)))
    print("\n=== scenario: no real drift ===")
    print(summarize(check_feature_drift(reference, current_stable)))

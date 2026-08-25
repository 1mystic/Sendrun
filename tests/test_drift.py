"""ml/monitoring/drift.py exercised on synthetic drift — the honest scope
this session settled on, since no live production traffic exists yet to
monitor for real. These tests are what makes the drift MECHANISM itself a
verified claim rather than an unverified aspiration.
"""

from __future__ import annotations

import numpy as np

from ml.monitoring.drift import (
    check_feature_drift,
    check_prediction_drift,
    classify_psi,
    population_stability_index,
)


def test_identical_distributions_have_near_zero_psi():
    rng = np.random.default_rng(1)
    ref = rng.normal(0, 1, 5000)
    cur = rng.normal(0, 1, 5000)
    psi = population_stability_index(ref, cur)
    assert psi < 0.02


def test_a_shifted_distribution_has_high_psi():
    rng = np.random.default_rng(2)
    ref = rng.normal(0, 1, 5000)
    cur = rng.normal(3, 1, 5000)  # shifted 3 std devs
    psi = population_stability_index(ref, cur)
    assert psi > 0.25


def test_classify_psi_boundaries():
    assert classify_psi(0.05) == "none"
    assert classify_psi(0.15) == "warning"
    assert classify_psi(0.30) == "alert"


def test_a_near_constant_reference_does_not_crash():
    """Degenerate input (e.g. a feature that's almost always the same value)
    must not divide-by-zero or NaN — it should report 0, not crash the whole
    drift sweep over one bad feature."""
    ref = np.ones(1000)
    cur = np.ones(1000) * 1.001
    psi = population_stability_index(ref, cur)
    assert psi == 0.0


def test_check_feature_drift_flags_only_the_shifted_feature():
    rng = np.random.default_rng(3)
    reference = {
        "stable_feature": rng.normal(0, 1, 3000),
        "drifted_feature": rng.beta(2, 20, 3000),
    }
    current = {
        "stable_feature": rng.normal(0, 1, 1500),
        "drifted_feature": rng.beta(10, 10, 1500),  # genuinely different shape
    }
    results = check_feature_drift(reference, current)
    by_name = {r.feature: r for r in results}

    assert by_name["stable_feature"].severity == "none"
    assert by_name["drifted_feature"].severity == "alert"


def test_check_feature_drift_ignores_features_missing_from_current():
    reference = {
        "a": np.random.default_rng(4).normal(size=100),
        "b": np.random.default_rng(5).normal(size=100),
    }
    current = {"a": np.random.default_rng(4).normal(size=100)}
    results = check_feature_drift(reference, current)
    assert {r.feature for r in results} == {"a"}


def test_prediction_drift_detects_a_shifted_score_distribution():
    rng = np.random.default_rng(6)
    reference_predictions = rng.beta(2, 20, 2000)  # mostly low risk scores
    current_predictions = rng.beta(2, 20, 2000)
    drifted, stat, p_value = check_prediction_drift(reference_predictions, current_predictions)
    assert not drifted  # same distribution -> should NOT flag

    current_shifted = rng.beta(10, 10, 2000)  # scores got dramatically riskier
    drifted, stat, p_value = check_prediction_drift(reference_predictions, current_shifted)
    assert drifted
    assert p_value < 0.01


def test_drift_check_is_reproducible_with_a_fixed_seed():
    """Same seed, same verdict — required for CI stability; a flaky drift
    test would train the team to ignore drift alerts."""
    rng1 = np.random.default_rng(42)
    ref1 = rng1.normal(0, 1, 1000)
    cur1 = rng1.normal(1, 1, 1000)

    rng2 = np.random.default_rng(42)
    ref2 = rng2.normal(0, 1, 1000)
    cur2 = rng2.normal(1, 1, 1000)

    assert population_stability_index(ref1, cur1) == population_stability_index(ref2, cur2)

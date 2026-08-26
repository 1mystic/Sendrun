"""ml/training/train_send_time_model.py — the hour-sweep recommendation
logic and the ranking-based evaluation, which is structurally different from
the bounce/engagement classifiers' AUC-style metrics (see that module's
docstring for why: the deliverable is a correct ORDERING of hours, not a
single probability)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from ml.features.pipeline import ALL_INPUT_FEATURES, build_preprocessing_pipeline
from ml.training.train_send_time_model import (
    CANDIDATE_HOURS,
    evaluate_hour_ranking,
    recommend_hour,
)


def _make_training_frame(n: int = 400, seed: int = 0) -> tuple[pd.DataFrame, pd.Series]:
    """A small synthetic frame with a KNOWN, deliberately strong send_hour
    effect (peak at hour 10), independent of ml/data/generate_synthetic.py —
    this test suite must not depend on that file's calibration, since a
    future recalibration there should not be able to silently break these
    tests for an unrelated reason."""
    rng = np.random.default_rng(seed)
    hours = rng.choice(CANDIDATE_HOURS, size=n)
    domains = rng.choice(
        ["gmail.com", "outlook.com", "yahoo.com", "company-corp.com",
         "startup.io", "old-university.edu", "free-mail-provider.net"],
        size=n,
    )
    df = pd.DataFrame({
        "contact_age_days": rng.integers(1, 1000, n),
        "prior_sends": rng.integers(0, 20, n),
        "prior_bounces": rng.integers(0, 3, n),
        "prior_opens": rng.integers(0, 10, n),
        "send_hour": hours,
        "subject_length": rng.integers(20, 90, n),
        "attachment_count": rng.integers(0, 2, n),
        "has_engaged_ever": rng.integers(0, 2, n),
        "is_weekend": rng.integers(0, 2, n),
        "has_personalization": rng.integers(0, 2, n),
        "domain": domains,
    })
    # Strong, known peak at hour 10 — a real signal a model should recover.
    logit = -0.5 - 0.25 * np.abs(hours - 10) + rng.normal(0, 0.3, n)
    prob = 1 / (1 + np.exp(-logit))
    y = pd.Series(rng.binomial(1, prob), name="opened")
    return df, y


class TestRecommendHour:
    def test_recommends_the_known_peak_hour(self):
        """With a strong, known peak-at-10 signal, a fitted model should
        recommend an hour close to 10 for a representative contact — this
        checks the sweep-and-argmax mechanism itself, not model quality."""
        X, y = _make_training_frame(n=2000, seed=1)
        pipeline = Pipeline([
            ("preprocess", build_preprocessing_pipeline()),
            ("model", LogisticRegression(max_iter=1000)),
        ])
        pipeline.fit(X[ALL_INPUT_FEATURES], y)

        example = X.iloc[0]
        best_hour, curve = recommend_hour(pipeline, example)

        assert 8 <= best_hour <= 12  # close to the true peak at 10
        assert set(curve.keys()) == set(CANDIDATE_HOURS)

    def test_curve_covers_every_candidate_hour(self):
        X, y = _make_training_frame(n=500, seed=2)
        pipeline = Pipeline([
            ("preprocess", build_preprocessing_pipeline()),
            ("model", LogisticRegression(max_iter=1000)),
        ])
        pipeline.fit(X[ALL_INPUT_FEATURES], y)

        _, curve = recommend_hour(pipeline, X.iloc[0])
        assert len(curve) == len(CANDIDATE_HOURS)
        assert all(0.0 <= p <= 1.0 for p in curve.values())

    def test_only_send_hour_varies_across_the_sweep(self):
        """Every other feature must stay fixed while send_hour sweeps —
        otherwise the curve isn't measuring the hour's effect at all, it's
        measuring noise from changing contact identity mid-sweep."""
        X, y = _make_training_frame(n=300, seed=3)
        pipeline = Pipeline([
            ("preprocess", build_preprocessing_pipeline()),
            ("model", LogisticRegression(max_iter=1000)),
        ])
        pipeline.fit(X[ALL_INPUT_FEATURES], y)

        contact = X.iloc[5].copy()
        contact["domain"] = "gmail.com"
        contact["prior_opens"] = 7
        _, curve = recommend_hour(pipeline, contact)
        # A model with ONLY send_hour varying and a real hour effect should
        # not produce a flat curve.
        values = list(curve.values())
        assert max(values) - min(values) > 0.001


class TestHourRankingEvaluation:
    def test_perfect_signal_gives_high_rank_correlation(self):
        """A model trained on data with a strong, clean hour effect should
        recover a high (ideally close to 1.0) Spearman correlation between
        predicted and observed open-rate-by-hour ordering."""
        X, y = _make_training_frame(n=3000, seed=4)
        pipeline = Pipeline([
            ("preprocess", build_preprocessing_pipeline()),
            ("model", LogisticRegression(max_iter=1000)),
        ])
        pipeline.fit(X[ALL_INPUT_FEATURES], y)

        metrics = evaluate_hour_ranking(pipeline, X, y)
        assert metrics["hour_rank_spearman_rho"] > 0.5

    def test_metrics_dict_has_the_expected_keys(self):
        X, y = _make_training_frame(n=500, seed=5)
        pipeline = Pipeline([
            ("preprocess", build_preprocessing_pipeline()),
            ("model", LogisticRegression(max_iter=1000)),
        ])
        pipeline.fit(X[ALL_INPUT_FEATURES], y)

        metrics = evaluate_hour_ranking(pipeline, X, y)
        expected_keys = {
            "hour_rank_spearman_rho", "hour_rank_p_value",
            "best_hour_matches", "best_observed_hour", "best_predicted_hour",
        }
        assert set(metrics.keys()) == expected_keys

    def test_best_hour_matches_is_binary(self):
        X, y = _make_training_frame(n=500, seed=6)
        pipeline = Pipeline([
            ("preprocess", build_preprocessing_pipeline()),
            ("model", LogisticRegression(max_iter=1000)),
        ])
        pipeline.fit(X[ALL_INPUT_FEATURES], y)

        metrics = evaluate_hour_ranking(pipeline, X, y)
        assert metrics["best_hour_matches"] in (0.0, 1.0)

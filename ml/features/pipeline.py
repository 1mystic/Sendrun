"""Stage 3: preprocessing + feature engineering, as a single scikit-learn
Pipeline object rather than ad-hoc pandas transforms in a notebook.

Why this matters more than it looks: a Pipeline fit on TRAIN and reused
(never refit) on VALIDATION/TEST/SERVING is what prevents train-serve skew.
The same fitted object — encoders' learned categories, scaler's learned
mean/std — is what the deployed model actually needs at inference time. This
IS the beginning of the "feature store" the plan calls for: a versioned,
serializable transform with a fixed input/output contract, which
ml/registry/ later ships alongside the model artifact itself.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

# The exact feature contract. Any column not listed here is dropped; any
# column listed here that's missing from the input raises — a serving-time
# schema mismatch must fail loudly, not silently drop a feature the model
# was trained on.
NUMERIC_FEATURES = [
    "contact_age_days", "prior_sends", "prior_bounces", "prior_opens",
    "send_hour", "subject_length", "attachment_count",
]
BINARY_FEATURES = ["has_engaged_ever", "is_weekend", "has_personalization"]
CATEGORICAL_FEATURES = ["domain"]
ALL_INPUT_FEATURES = NUMERIC_FEATURES + BINARY_FEATURES + CATEGORICAL_FEATURES


class DerivedFeatures(TransformerMixin, BaseEstimator):
    """Feature ENGINEERING, not just preprocessing: ratios and interactions
    that are not literal columns in the raw data but are believed (and later
    verified via feature importance) to carry real signal.

    Written as a proper sklearn transformer — not a one-off pandas function —
    so it composes into the Pipeline and its parameters are none (stateless),
    which sklearn's clone/fit machinery needs to handle correctly during CV.
    """

    def fit(self, X: pd.DataFrame, y=None) -> DerivedFeatures:
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()

        # Historical bounce rate for this contact — a ratio, not a raw count,
        # because 2 bounces out of 3 sends means something very different
        # from 2 bounces out of 50. Guarded against div-by-zero for new
        # contacts with prior_sends=0.
        X["prior_bounce_rate"] = np.where(
            X["prior_sends"] > 0, X["prior_bounces"] / X["prior_sends"], 0.0
        )
        X["prior_open_rate"] = np.where(
            X["prior_sends"] > 0, X["prior_opens"] / X["prior_sends"], 0.0
        )

        # A contact with prior_sends=0 has NO history — that is itself
        # informative (cold-start risk) and distinct from "0 sends, 0
        # bounces = perfect record." Encode it as its own flag rather than
        # letting the ratio's 0.0 fallback silently conflate the two.
        X["is_cold_start"] = (X["prior_sends"] == 0).astype(int)

        # Distance from the empirically-best send hour (~10am, from EDA).
        # A derived, non-linear transform of send_hour that a linear-ish
        # model component benefits from having explicit rather than inferred.
        X["hours_from_optimal_send"] = (X["send_hour"] - 10).abs()

        return X[
            NUMERIC_FEATURES
            + ["prior_bounce_rate", "prior_open_rate", "is_cold_start", "hours_from_optimal_send"]
            + BINARY_FEATURES
            + CATEGORICAL_FEATURES
        ]


DERIVED_NUMERIC = NUMERIC_FEATURES + [
    "prior_bounce_rate", "prior_open_rate", "is_cold_start", "hours_from_optimal_send",
]


def build_preprocessing_pipeline() -> Pipeline:
    """The full preprocessing pipeline: derive features, then scale numerics
    and one-hot the categorical. `handle_unknown="ignore"` on the encoder is
    deliberate — a domain never seen in training (a brand-new contact list)
    must not crash inference; it degrades to the all-zeros encoding instead."""
    column_transform = ColumnTransformer(
        transformers=[
            ("numeric", StandardScaler(), DERIVED_NUMERIC),
            ("binary", "passthrough", BINARY_FEATURES),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
    )
    return Pipeline([
        ("derive", DerivedFeatures()),
        ("transform", column_transform),
    ])


def get_output_feature_names(pipeline: Pipeline) -> list[str]:
    """Recovers human-readable names for the transformed columns — needed
    because ColumnTransformer + OneHotEncoder produces opaque positional
    columns otherwise, and feature importance (ml/evaluation/) is unreadable
    without real names."""
    column_transform: ColumnTransformer = pipeline.named_steps["transform"]
    names: list[str] = list(DERIVED_NUMERIC) + list(BINARY_FEATURES)
    ohe: OneHotEncoder = column_transform.named_transformers_["categorical"]
    names.extend(ohe.get_feature_names_out(CATEGORICAL_FEATURES))
    return names


class ColumnMaskSelector(TransformerMixin, BaseEstimator):
    """A fitted feature-selection mask, wrapped as a pipeline step.

    Lives here (in an always-imported-by-name module) rather than in a
    training script, because pickle/skops serialize a class by its qualified
    module path — a class defined in a script run as `__main__` gets
    serialized as living in "__main__", and a DIFFERENT process loading that
    model later (a test, an evaluation script, a serving process) has its
    OWN unrelated `__main__` and fails with `AttributeError: module
    '__main__' has no attribute 'ColumnMaskSelector'`. This bit us once
    already during Phase 6 development — see ml/training/train_bounce_model.py.

    Necessary in the pipeline at all because the logged model must be ONE
    object a serving process can call .predict_proba() on directly. Without
    it, the mask applied at train time (`Xt[:, selected_mask]`) has no home
    in the saved pipeline — logging `Pipeline([preprocessor, model])` alone
    would silently feed the FULL feature set to a model trained on the
    SELECTED subset, a shape mismatch that fails at serve time in the worst
    possible way: silently wrong probabilities if the counts happen to
    coincide, or a crash if not.
    """

    def __init__(self, mask: np.ndarray) -> None:
        self.mask = mask

    def fit(self, X, y=None) -> ColumnMaskSelector:
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        return X[:, self.mask]

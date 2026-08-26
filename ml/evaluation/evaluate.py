"""Stage 9: evaluation report — feature importance, calibration, and a sanity
check that the model's top features roughly match what the synthetic
generator actually encoded as signal for THIS model
(ml/data/generate_synthetic.py's bounce logit or open logit). If they don't
match, either the model failed to find real signal, or the feature pipeline
has a bug feeding it the wrong columns — this check exists to distinguish
"the model is weak" from "the pipeline is broken."

Run: uv run python ml/evaluation/evaluate.py <model_uri> <bounce|engagement>
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.inspection import permutation_importance

from ml.features.pipeline import ALL_INPUT_FEATURES

DATA_PATH = Path("ml/data/sends_raw.parquet")
FIG_DIR = Path("ml/evaluation/figures")

# The generator's dominant drivers, by design — see generate_synthetic.py's
# bounce logit / open logit comments. Permutation importance should surface
# features DERIVED FROM these among the top ranks — not necessarily these
# exact raw column names, since feature engineering may have transformed
# them (e.g. prior_bounce_rate is engineered FROM prior_bounces/prior_sends).
EXPECTED_SIGNAL_SOURCES = {
    "bounce": {"domain", "prior_bounce", "contact_age"},
    "engagement": {"domain", "prior_open", "has_engaged", "has_personalization"},
}


def load_test_split(model_kind: str) -> tuple[pd.DataFrame, pd.Series]:
    """Reconstructs the SAME held-out test rows the matching training script
    used — same seed, same GroupShuffleSplit — so this evaluation is against
    data the model never trained on, not a re-shuffled leak. Which
    load_split/target column to use depends on which model is being
    evaluated: engagement's target is `opened` and its split additionally
    excludes bounced rows (see train_engagement_model.py's load_split
    docstring for why)."""
    df = pd.read_parquet(DATA_PATH)
    if model_kind == "bounce":
        from ml.training.train_bounce_model import load_split
    else:
        from ml.training.train_engagement_model import load_split

    _, _, _, _, X_test, y_test = load_split(df)
    return X_test, y_test


def plot_calibration(y_true: pd.Series, y_prob: np.ndarray) -> None:
    """A risk score the UI displays as '18/100' is only trustworthy if
    contacts scored ~0.18 actually bounce ~18% of the time — this is exactly
    what a calibration curve checks, and it's a materially different property
    from ranking ability (AUC)."""
    FIG_DIR.mkdir(exist_ok=True, parents=True)
    frac_pos, mean_pred = calibration_curve(y_true, y_prob, n_bins=10, strategy="quantile")

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], "k--", label="perfectly calibrated")
    ax.plot(mean_pred, frac_pos, marker="o", color="#E4491F", label="bounce-risk model")
    ax.set_xlabel("mean predicted probability")
    ax.set_ylabel("observed bounce rate")
    ax.set_title("Calibration curve (held-out test set)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "calibration.png", dpi=120)
    plt.close(fig)


def plot_feature_importance(
    pipeline, X_test: pd.DataFrame, y_test: pd.Series, report: list[str]
) -> list[str]:
    """Permutation importance on the FULL pipeline (raw features in) rather
    than on the model's internal coefficients — this measures importance in
    terms an operator actually understands (raw input columns), and works
    identically regardless of which candidate model won."""
    result = permutation_importance(
        pipeline, X_test[ALL_INPUT_FEATURES], y_test,
        n_repeats=10, random_state=42, scoring="average_precision", n_jobs=-1,
    )
    order = result.importances_mean.argsort()[::-1]
    names = X_test[ALL_INPUT_FEATURES].columns[order]
    means = result.importances_mean[order]
    stds = result.importances_std[order]

    report.append("\nPermutation feature importance (drop in PR-AUC when shuffled):")
    for name, mean, std in zip(names, means, stds, strict=True):
        report.append(f"  {name}: {mean:+.4f} (± {std:.4f})")

    FIG_DIR.mkdir(exist_ok=True, parents=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(names[:8][::-1], means[:8][::-1], xerr=stds[:8][::-1], color="#E4491F")
    ax.set_xlabel("importance (PR-AUC drop)")
    ax.set_title("Top 8 features by permutation importance")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "feature_importance.png", dpi=120)
    plt.close(fig)

    return list(names[:5])


def check_importance_matches_design(
    top_features: list[str], report: list[str], expected_sources: set[str]
) -> bool:
    matched_sources = set()
    for feature in top_features:
        for source in expected_sources:
            if source in feature.lower():
                matched_sources.add(source)

    ok = len(matched_sources) >= 2  # at least 2 of the designed drivers should surface
    report.append(f"\nDesign-consistency check: top-5 features touch {matched_sources or 'none'}")
    report.append(f"  of the designed signal sources {expected_sources}")
    report.append(f"  [{'OK' if ok else 'SUSPICIOUS — investigate before trusting this model'}]")
    return ok


def main(model_uri: str, model_kind: str) -> None:
    pipeline = mlflow.sklearn.load_model(model_uri)
    X_test, y_test = load_test_split(model_kind)
    y_prob = pipeline.predict_proba(X_test[ALL_INPUT_FEATURES])[:, 1]

    report: list[str] = [f"Evaluation report for {model_uri} ({model_kind})\n"]
    plot_calibration(y_test, y_prob)
    top_features = plot_feature_importance(pipeline, X_test, y_test, report)
    design_ok = check_importance_matches_design(
        top_features, report, EXPECTED_SIGNAL_SOURCES[model_kind]
    )

    report.append(f"\nFigures written to {FIG_DIR}/")
    text = "\n".join(report)
    print(text)
    (FIG_DIR / "report.txt").write_text(text)

    if not design_ok:
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[2] not in ("bounce", "engagement"):
        print("usage: uv run python ml/evaluation/evaluate.py <model_uri> <bounce|engagement>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

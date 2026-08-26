"""Engagement (open probability) model — the same pipeline shape as
train_bounce_model.py, reused deliberately rather than reinvented: split by
campaign_id, feature-select, compare 3 candidates + ensemble honestly, log
everything to MLflow, verify the reloaded artifact reproduces test metrics.

Key difference from bounce-risk: only rows where bounced=0 are eligible —
you cannot "open" an email that never arrived. Filtering happens BEFORE the
split, so a bounced row never leaks into train, val, or test for this model.
"""

from __future__ import annotations

import sys
from pathlib import Path

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.feature_selection import SelectFromModel
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from ml.features.pipeline import (
    ALL_INPUT_FEATURES,
    ColumnMaskSelector,
    build_preprocessing_pipeline,
    get_output_feature_names,
)

DATA_PATH = Path("ml/data/sends_raw.parquet")
MLFLOW_EXPERIMENT = "sendrun-engagement-risk"
RANDOM_STATE = 42

SplitResult = tuple[
    pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series
]


def load_split(df: pd.DataFrame) -> SplitResult:
    """Bounced rows excluded BEFORE splitting — an email that never arrived
    has no defined open outcome, and including it would let the model learn
    a spurious correlation between bounce-risk features and "not opened."""
    eligible = df[df.bounced == 0].reset_index(drop=True)
    X = eligible[ALL_INPUT_FEATURES]
    y = eligible["opened"]
    groups = eligible["campaign_id"]

    splitter1 = GroupShuffleSplit(n_splits=1, test_size=0.4, random_state=RANDOM_STATE)
    train_idx, rest_idx = next(splitter1.split(X, y, groups))

    rest_groups = groups.iloc[rest_idx]
    splitter2 = GroupShuffleSplit(n_splits=1, test_size=0.5, random_state=RANDOM_STATE)
    val_idx_rel, test_idx_rel = next(
        splitter2.split(X.iloc[rest_idx], y.iloc[rest_idx], rest_groups)
    )
    val_idx = rest_idx[val_idx_rel]
    test_idx = rest_idx[test_idx_rel]

    assert set(groups.iloc[train_idx]) & set(groups.iloc[val_idx]) == set()
    assert set(groups.iloc[train_idx]) & set(groups.iloc[test_idx]) == set()
    assert set(groups.iloc[val_idx]) & set(groups.iloc[test_idx]) == set()

    return (
        X.iloc[train_idx], y.iloc[train_idx],
        X.iloc[val_idx], y.iloc[val_idx],
        X.iloc[test_idx], y.iloc[test_idx],
    )


def evaluate(y_true: pd.Series, y_prob: np.ndarray) -> dict[str, float]:
    """Open rate here is ~38% — much less imbalanced than bounce's ~12%, so
    ROC-AUC is a meaningful headline metric too, but PR-AUC and calibration
    (Brier) still matter for a UI that displays a per-recipient probability."""
    return {
        "roc_auc": roc_auc_score(y_true, y_prob),
        "pr_auc": average_precision_score(y_true, y_prob),
        "brier_score": brier_score_loss(y_true, y_prob),
    }


def select_features(pipeline: Pipeline, X_train: pd.DataFrame, y_train: pd.Series) -> np.ndarray:
    Xt = pipeline.fit_transform(X_train, y_train)
    names = get_output_feature_names(pipeline)

    ranker = RandomForestClassifier(
        n_estimators=200, max_depth=8, class_weight="balanced",
        random_state=RANDOM_STATE, n_jobs=-1,
    )
    selector = SelectFromModel(ranker, threshold="median")
    selector.fit(Xt, y_train)

    kept_mask = selector.get_support()
    kept_names = [n for n, keep in zip(names, kept_mask, strict=True) if keep]
    dropped_names = [n for n, keep in zip(names, kept_mask, strict=True) if not keep]
    print(f"feature selection: kept {kept_mask.sum()}/{len(names)}")
    print(f"  kept: {kept_names}")
    print(f"  dropped: {dropped_names}")
    return kept_mask


def train_candidates(
    Xt_train: np.ndarray, y_train: pd.Series, Xt_val: np.ndarray, y_val: pd.Series
) -> dict[str, tuple[object, dict[str, float]]]:
    candidates = {
        "logistic_regression": LogisticRegression(
            class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300, max_depth=10, class_weight="balanced",
            random_state=RANDOM_STATE, n_jobs=-1,
        ),
        "xgboost": XGBClassifier(
            n_estimators=400, max_depth=4, learning_rate=0.04,
            min_child_weight=5, subsample=0.8, colsample_bytree=0.8,
            scale_pos_weight=(y_train == 0).sum() / max((y_train == 1).sum(), 1),
            eval_metric="aucpr", random_state=RANDOM_STATE, n_jobs=-1,
        ),
    }

    results = {}
    for name, model in candidates.items():
        model.fit(Xt_train, y_train)
        y_prob = model.predict_proba(Xt_val)[:, 1]
        metrics = evaluate(y_val, y_prob)
        results[name] = (model, metrics)
        print(f"{name}: {metrics}")
    return results


def build_ensemble(candidates: dict[str, tuple[object, dict]]) -> VotingClassifier:
    return VotingClassifier(
        estimators=[(name, model) for name, (model, _) in candidates.items()],
        voting="soft",
    )


def main() -> None:
    if not DATA_PATH.exists():
        print(f"missing {DATA_PATH} — run: uv run python ml/data/generate_synthetic.py")
        sys.exit(1)

    df = pd.read_parquet(DATA_PATH)
    X_train, y_train, X_val, y_val, X_test, y_test = load_split(df)
    print(f"split: train={len(X_train):,} val={len(X_val):,} test={len(X_test):,}")
    print(f"open rate (train): {y_train.mean():.2%}")

    mlflow.set_experiment(MLFLOW_EXPERIMENT)

    with mlflow.start_run(run_name="engagement-risk-full-pipeline") as run:
        mlflow.log_params({
            "n_train": len(X_train), "n_val": len(X_val), "n_test": len(X_test),
            "train_open_rate": float(y_train.mean()),
            "random_state": RANDOM_STATE,
        })

        preprocessor = build_preprocessing_pipeline()
        selected_mask = select_features(preprocessor, X_train, y_train)
        mlflow.log_param("n_features_selected", int(selected_mask.sum()))

        Xt_train = preprocessor.transform(X_train)[:, selected_mask]
        Xt_val = preprocessor.transform(X_val)[:, selected_mask]
        Xt_test = preprocessor.transform(X_test)[:, selected_mask]

        candidates = train_candidates(Xt_train, y_train, Xt_val, y_val)
        for name, (_, metrics) in candidates.items():
            for metric_name, value in metrics.items():
                mlflow.log_metric(f"val_{name}_{metric_name}", value)

        ensemble = build_ensemble(candidates)
        ensemble.fit(Xt_train, y_train)
        ensemble_val_prob = ensemble.predict_proba(Xt_val)[:, 1]
        ensemble_metrics = evaluate(y_val, ensemble_val_prob)
        for metric_name, value in ensemble_metrics.items():
            mlflow.log_metric(f"val_ensemble_{metric_name}", value)
        print(f"ensemble: {ensemble_metrics}")

        all_val_scores = {name: m["pr_auc"] for name, (_, m) in candidates.items()}
        all_val_scores["ensemble"] = ensemble_metrics["pr_auc"]
        winner_name = max(all_val_scores, key=all_val_scores.get)
        mlflow.log_param("winner", winner_name)
        mlflow.log_metric("winner_val_pr_auc", all_val_scores[winner_name])
        print(f"\nwinner (by val PR-AUC): {winner_name} ({all_val_scores[winner_name]:.4f})")

        final_model = ensemble if winner_name == "ensemble" else candidates[winner_name][0]

        test_prob = final_model.predict_proba(Xt_test)[:, 1]
        test_metrics = evaluate(y_test, test_prob)
        for metric_name, value in test_metrics.items():
            mlflow.log_metric(f"test_{metric_name}", value)
        print(f"HELD-OUT TEST metrics ({winner_name}): {test_metrics}")

        full_pipeline = Pipeline([
            ("preprocess", preprocessor),
            ("select", ColumnMaskSelector(selected_mask)),
            ("model", final_model),
        ])
        # Trust every candidate family's type unconditionally, not just the
        # winner's — the ensemble (if it wins) embeds all three, and which
        # single model wins is itself data-dependent (see this file's run:
        # engagement picked xgboost, bounce-risk picked logistic_regression,
        # on the same pipeline shape). Trusting only the actual winner's type
        # would make this script fail nondeterministically depending on
        # which candidate happens to score best on a given data regeneration.
        model_info = mlflow.sklearn.log_model(
            full_pipeline, name="model", input_example=X_train.head(3),
            skops_trusted_types=[
                "ml.features.pipeline.DerivedFeatures",
                "ml.features.pipeline.ColumnMaskSelector",
                "xgboost.core.Booster",
                "xgboost.sklearn.XGBClassifier",
            ],
        )
        mlflow.log_param("model_uri", model_info.model_uri)

        reloaded_pipeline = mlflow.sklearn.load_model(model_info.model_uri)
        reloaded_prob = reloaded_pipeline.predict_proba(X_test)[:, 1]
        np.testing.assert_allclose(reloaded_prob, test_prob, rtol=1e-6)
        print(f"verified: reloaded model from {model_info.model_uri} matches reported test metrics")

        print(f"\nMLflow run: {run.info.run_id}")
        print(f"model_uri: {model_info.model_uri}")
        return run.info.run_id, model_info.model_uri, winner_name, test_metrics


if __name__ == "__main__":
    main()

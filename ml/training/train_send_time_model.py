"""Send-time recommendation model.

Structurally different from bounce-risk/engagement, which predict "will X
happen" for a fixed context. This model answers "which hour maximizes open
probability for THIS contact" — there's no single (contact, campaign) row per
prediction; a recommendation requires comparing predicted open probability
ACROSS every candidate hour for the same contact.

Approach: train one probability-of-open regressor conditioned on send_hour as
an input feature (reusing the already-trained engagement classifier's
underlying mechanism would double-count; this is a dedicated, hour-focused
model instead), then at inference time sweep send_hour across the day and
recommend the argmax. This is standard "uplift by intervention" framing: the
model doesn't need a separate "send-time" label — it reuses the SAME opened
label the engagement model uses, but the deliverable is a per-hour sweep, not
a single probability.

Held-out evaluation here is NOT the same shape as a classifier's ROC-AUC.
What actually matters is whether the model's recommended-hour ordering
correlates with the TRUE population-level open-rate-by-hour curve. That's
what evaluate_hour_ranking() checks.
"""

from __future__ import annotations

import sys
from pathlib import Path

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline

from ml.features.pipeline import ALL_INPUT_FEATURES, build_preprocessing_pipeline

DATA_PATH = Path("ml/data/sends_raw.parquet")
MLFLOW_EXPERIMENT = "sendrun-send-time"
RANDOM_STATE = 42
CANDIDATE_HOURS = list(range(6, 22))  # matches the generator's send_hour range


def load_split(df: pd.DataFrame):
    """Same shape as train_engagement_model.py's split — bounced rows
    excluded, grouped by campaign_id. Reusing that exact discipline rather
    than a fresh implementation is deliberate: any divergence here would be
    a place for train/serve skew to creep in unnoticed."""
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

    return (
        X.iloc[train_idx], y.iloc[train_idx],
        X.iloc[val_idx], y.iloc[val_idx],
        X.iloc[test_idx], y.iloc[test_idx],
    )


def recommend_hour(pipeline: Pipeline, contact_row: pd.Series) -> tuple[int, dict[int, float]]:
    """Sweeps every candidate hour with everything else about the contact
    held fixed, and returns the argmax plus the full curve — the curve
    itself is what the UI would show ("predicted open rate by hour"), not
    just the single recommendation."""
    rows = pd.DataFrame([contact_row.to_dict()] * len(CANDIDATE_HOURS))
    rows["send_hour"] = CANDIDATE_HOURS
    rows["hours_from_optimal_send"] = (rows["send_hour"] - 10).abs()
    probs = pipeline.predict_proba(rows[ALL_INPUT_FEATURES])[:, 1]
    curve = dict(zip(CANDIDATE_HOURS, probs.tolist(), strict=True))
    best_hour = CANDIDATE_HOURS[int(np.argmax(probs))]
    return best_hour, curve


def evaluate_hour_ranking(
    pipeline: Pipeline, df_test: pd.DataFrame, y_test: pd.Series
) -> dict[str, float]:
    """The metric that actually matters for THIS model: does the model's
    predicted open-rate-by-hour ordering correlate with the observed
    open-rate-by-hour ordering in held-out data? Spearman rank correlation,
    not accuracy/AUC — we care about ORDER (which hours are better than
    which), not the absolute probability value at any one hour.
    """
    observed = df_test.assign(opened=y_test.values).groupby("send_hour").opened.mean()

    # Predict at each observed hour using the ACTUAL rows sent at that hour
    # (not a synthetic sweep) — this evaluates the model against its true
    # held-out conditional distribution, not an idealized held-fixed sweep.
    predicted_by_hour = {}
    for hour in observed.index:
        subset = df_test[df_test.send_hour == hour]
        if len(subset) == 0:
            continue
        probs = pipeline.predict_proba(subset[ALL_INPUT_FEATURES])[:, 1]
        predicted_by_hour[hour] = float(np.mean(probs))

    hours = sorted(predicted_by_hour.keys())
    observed_ordered = [observed[h] for h in hours]
    predicted_ordered = [predicted_by_hour[h] for h in hours]

    rho, p_value = spearmanr(observed_ordered, predicted_ordered)
    best_observed_hour = observed.idxmax()
    best_predicted_hour = max(predicted_by_hour, key=predicted_by_hour.get)

    return {
        "hour_rank_spearman_rho": float(rho),
        "hour_rank_p_value": float(p_value),
        "best_hour_matches": float(best_observed_hour == best_predicted_hour),
        "best_observed_hour": float(best_observed_hour),
        "best_predicted_hour": float(best_predicted_hour),
    }


def main() -> None:
    if not DATA_PATH.exists():
        print(f"missing {DATA_PATH} — run: uv run python ml/data/generate_synthetic.py")
        sys.exit(1)

    df = pd.read_parquet(DATA_PATH)
    X_train, y_train, X_val, y_val, X_test, y_test = load_split(df)
    print(f"split: train={len(X_train):,} val={len(X_val):,} test={len(X_test):,}")

    mlflow.set_experiment(MLFLOW_EXPERIMENT)

    with mlflow.start_run(run_name="send-time-full-pipeline") as run:
        mlflow.log_params({
            "n_train": len(X_train), "n_val": len(X_val), "n_test": len(X_test),
            "random_state": RANDOM_STATE, "candidate_hours": str(CANDIDATE_HOURS),
        })

        preprocessor = build_preprocessing_pipeline()

        # Two candidates, compared honestly — logistic regression as an
        # interpretable baseline, gradient boosting for the monotonic-ish
        # hour effect. No feature-selection step here: with only ~10 input
        # features and send_hour being load-bearing by construction, dropping
        # any of them risks removing exactly the signal this model exists to
        # capture (unlike bounce/engagement, where 21 engineered features
        # made selection worth doing).
        candidates = {
            "logistic_regression": Pipeline([
                ("preprocess", preprocessor),
                ("model", LogisticRegression(class_weight="balanced", max_iter=1000,
                                              random_state=RANDOM_STATE)),
            ]),
            "gradient_boosting": Pipeline([
                ("preprocess", preprocessor),
                ("model", GradientBoostingClassifier(
                    n_estimators=200, max_depth=3, learning_rate=0.05,
                    random_state=RANDOM_STATE,
                )),
            ]),
        }

        results = {}
        for name, pipe in candidates.items():
            pipe.fit(X_train, y_train)
            val_prob = pipe.predict_proba(X_val)[:, 1]
            standard_metrics = {
                "roc_auc": roc_auc_score(y_val, val_prob),
                "pr_auc": average_precision_score(y_val, val_prob),
            }
            ranking_metrics = evaluate_hour_ranking(pipe, X_val, y_val)
            results[name] = (pipe, standard_metrics, ranking_metrics)
            print(f"{name}: {standard_metrics} | hour-ranking: {ranking_metrics}")
            for k, v in {**standard_metrics, **ranking_metrics}.items():
                mlflow.log_metric(f"val_{name}_{k}", v)

        # Winner picked on hour-rank Spearman rho, NOT PR-AUC — this model's
        # deliverable is a correct ORDERING of hours, and a classifier can
        # have high PR-AUC while still ranking hours poorly if send_hour's
        # marginal contribution is swamped by stronger features like
        # prior_open_rate in the model's decision boundary.
        winner_name = max(results, key=lambda n: results[n][2]["hour_rank_spearman_rho"])
        mlflow.log_param("winner", winner_name)
        print(f"\nwinner (by hour-rank Spearman rho): {winner_name}")

        final_pipeline = results[winner_name][0]

        test_prob = final_pipeline.predict_proba(X_test)[:, 1]
        test_standard = {
            "roc_auc": roc_auc_score(y_test, test_prob),
            "pr_auc": average_precision_score(y_test, test_prob),
        }
        test_ranking = evaluate_hour_ranking(final_pipeline, X_test, y_test)
        for k, v in {**test_standard, **test_ranking}.items():
            mlflow.log_metric(f"test_{k}", v)
        print(f"HELD-OUT TEST ({winner_name}): {test_standard} | hour-ranking: {test_ranking}")

        model_info = mlflow.sklearn.log_model(
            final_pipeline, name="model", input_example=X_train.head(3),
            skops_trusted_types=[
                "ml.features.pipeline.DerivedFeatures",
                "xgboost.core.Booster",
                "xgboost.sklearn.XGBClassifier",
            ],
        )
        mlflow.log_param("model_uri", model_info.model_uri)

        reloaded = mlflow.sklearn.load_model(model_info.model_uri)
        reloaded_prob = reloaded.predict_proba(X_test)[:, 1]
        np.testing.assert_allclose(reloaded_prob, test_prob, rtol=1e-6)
        print(f"verified: reloaded model from {model_info.model_uri} matches reported test metrics")

        # Demonstrate the actual deliverable: a full per-hour curve for one
        # example contact, not just an aggregate metric.
        example = X_test.iloc[0]
        best_hour, curve = recommend_hour(final_pipeline, example)
        print(f"\nexample recommendation for one contact: best_hour={best_hour}")
        print(f"  full curve: {curve}")

        print(f"\nMLflow run: {run.info.run_id}")
        print(f"model_uri: {model_info.model_uri}")
        return run.info.run_id, model_info.model_uri, winner_name, test_ranking


if __name__ == "__main__":
    main()

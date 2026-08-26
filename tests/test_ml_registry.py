"""ml/registry/promote.py — the per-model-name fix.

This test suite exists specifically because of a real bug found during Phase
6 development: promote.py originally had a single hardcoded
REGISTERED_NAME, so registering the engagement model silently overwrote the
bounce-risk model's "production" alias. These tests assert the two models
stay genuinely independent under the registry's real MLflow-backed behavior.
"""

from __future__ import annotations

import uuid

import mlflow
import mlflow.sklearn
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from ml.registry.promote import (
    BOUNCE_RISK_MODEL_NAME,
    ENGAGEMENT_MODEL_NAME,
    load_production_model,
    register_and_promote,
)


@pytest.fixture
def mlflow_tmp_tracking(tmp_path, monkeypatch):
    """An isolated MLflow store per test — never touches ml/mlflow.db or any
    ambient store, so these tests cannot pollute or depend on real training
    runs."""
    uri = f"sqlite:///{tmp_path}/test_mlflow.db"
    mlflow.set_tracking_uri(uri)
    yield uri


def _log_dummy_model(tag: str) -> str:
    """A trivial fitted pipeline, just to get a real model_uri to register."""
    import numpy as np

    X = np.random.rand(20, 2)
    y = np.random.randint(0, 2, 20)
    model = LogisticRegression().fit(X, y)
    pipeline = Pipeline([("model", model)])

    experiment = f"test-{tag}-{uuid.uuid4().hex[:8]}"
    mlflow.set_experiment(experiment)
    with mlflow.start_run():
        info = mlflow.sklearn.log_model(pipeline, name="model")
    return info.model_uri


class TestRegistryIsolation:
    def test_registering_two_different_models_does_not_collide(self, mlflow_tmp_tracking):
        bounce_uri = _log_dummy_model("bounce")
        engagement_uri = _log_dummy_model("engagement")

        register_and_promote(bounce_uri, registered_name=BOUNCE_RISK_MODEL_NAME)
        register_and_promote(engagement_uri, registered_name=ENGAGEMENT_MODEL_NAME)

        client = mlflow.MlflowClient()
        bounce_version = client.get_model_version_by_alias(BOUNCE_RISK_MODEL_NAME, "production")
        engagement_version = client.get_model_version_by_alias(
            ENGAGEMENT_MODEL_NAME, "production"
        )

        # The two registered names must point at DISTINCT underlying source
        # models — this is the exact property the original bug violated.
        assert bounce_version.source == bounce_uri
        assert engagement_version.source == engagement_uri
        assert bounce_version.source != engagement_version.source

    def test_promoting_a_new_bounce_version_does_not_touch_engagement(self, mlflow_tmp_tracking):
        bounce_v1 = _log_dummy_model("bounce-v1")
        engagement_v1 = _log_dummy_model("engagement-v1")
        register_and_promote(bounce_v1, registered_name=BOUNCE_RISK_MODEL_NAME)
        register_and_promote(engagement_v1, registered_name=ENGAGEMENT_MODEL_NAME)

        bounce_v2 = _log_dummy_model("bounce-v2")
        register_and_promote(bounce_v2, registered_name=BOUNCE_RISK_MODEL_NAME)

        client = mlflow.MlflowClient()
        engagement_still = client.get_model_version_by_alias(ENGAGEMENT_MODEL_NAME, "production")
        assert engagement_still.source == engagement_v1  # untouched by the bounce promotion

    def test_load_production_model_defaults_to_bounce_risk(self, mlflow_tmp_tracking):
        bounce_uri = _log_dummy_model("bounce-default")
        register_and_promote(bounce_uri, registered_name=BOUNCE_RISK_MODEL_NAME)

        model = load_production_model()  # no args -> bounce-risk by default
        assert model is not None

    def test_load_production_model_can_target_engagement_explicitly(self, mlflow_tmp_tracking):
        engagement_uri = _log_dummy_model("engagement-explicit")
        register_and_promote(engagement_uri, registered_name=ENGAGEMENT_MODEL_NAME)

        model = load_production_model(ENGAGEMENT_MODEL_NAME)
        assert model is not None

    def test_repromoting_the_same_name_creates_a_new_version_not_a_new_model(
        self, mlflow_tmp_tracking
    ):
        uri1 = _log_dummy_model("v1")
        uri2 = _log_dummy_model("v2")
        register_and_promote(uri1, registered_name=BOUNCE_RISK_MODEL_NAME)
        register_and_promote(uri2, registered_name=BOUNCE_RISK_MODEL_NAME)

        client = mlflow.MlflowClient()
        versions = client.search_model_versions(f"name='{BOUNCE_RISK_MODEL_NAME}'")
        assert len(versions) == 2  # same registered model, two versions

        current = client.get_model_version_by_alias(BOUNCE_RISK_MODEL_NAME, "production")
        assert current.source == uri2  # alias moved to the latest promotion

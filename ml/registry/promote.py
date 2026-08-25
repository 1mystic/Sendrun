"""Stage 10: model registry — staged promotion (None -> Staging -> Production).

Minimal but real: MLflow's model-version aliasing, used to answer the one
question that matters operationally — "which model_uri does the API load
right now?" — without the API ever needing to know a run_id or hunt through
experiment history.
"""

from __future__ import annotations

import sys

import mlflow

REGISTERED_NAME = "sendrun-bounce-risk"


def register_and_promote(model_uri: str, *, alias: str = "production") -> str:
    """Registers a logged model under a stable name and points an alias at
    it. The API always loads by NAME + ALIAS (mlflow.sklearn.load_model(
    f"models:/{REGISTERED_NAME}@{alias}")) — never by a specific version
    number — so promoting a new model is one call here, with zero API
    redeploy."""
    client = mlflow.MlflowClient()
    try:
        client.get_registered_model(REGISTERED_NAME)
    except mlflow.exceptions.MlflowException:
        client.create_registered_model(REGISTERED_NAME)

    mv = mlflow.register_model(model_uri, REGISTERED_NAME)
    client.set_registered_model_alias(REGISTERED_NAME, alias, mv.version)
    print(f"registered {REGISTERED_NAME} v{mv.version}, alias '{alias}' -> this version")
    return f"models:/{REGISTERED_NAME}@{alias}"


def load_production_model():
    """What the serving process (services/api or a future ml-serving router)
    calls. A single line, insulated from run ids and experiment names."""
    return mlflow.sklearn.load_model(f"models:/{REGISTERED_NAME}@production")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: uv run python ml/registry/promote.py <model_uri>")
        sys.exit(1)
    register_and_promote(sys.argv[1])

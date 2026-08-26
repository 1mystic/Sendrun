"""Stage 10: model registry — staged promotion (None -> Staging -> Production).

Minimal but real: MLflow's model-version aliasing, used to answer the one
question that matters operationally — "which model_uri does the API load
right now, for THIS model?" — without the API ever needing to know a run_id
or hunt through experiment history.

Each trained model gets its OWN registered name (BOUNCE_RISK_MODEL_NAME,
ENGAGEMENT_MODEL_NAME) — registering under one shared name would silently
overwrite one model's production alias with another's, exactly the mistake
this file's own docstring exists to warn against after it happened once
during Phase 6 development (see NEXT.md).
"""

from __future__ import annotations

import sys

import mlflow

BOUNCE_RISK_MODEL_NAME = "sendrun-bounce-risk"
ENGAGEMENT_MODEL_NAME = "sendrun-engagement-risk"
SEND_TIME_MODEL_NAME = "sendrun-send-time"


def register_and_promote(
    model_uri: str, *, registered_name: str, alias: str = "production"
) -> str:
    """Registers a logged model under a stable, model-specific name and
    points an alias at it. Callers always load by NAME + ALIAS
    (mlflow.sklearn.load_model(f"models:/{name}@{alias}")) — never by a
    specific version number — so promoting a new model is one call here,
    with zero API redeploy."""
    client = mlflow.MlflowClient()
    try:
        client.get_registered_model(registered_name)
    except mlflow.exceptions.MlflowException:
        client.create_registered_model(registered_name)

    mv = mlflow.register_model(model_uri, registered_name)
    client.set_registered_model_alias(registered_name, alias, mv.version)
    print(f"registered {registered_name} v{mv.version}, alias '{alias}' -> this version")
    return f"models:/{registered_name}@{alias}"


def load_production_model(registered_name: str = BOUNCE_RISK_MODEL_NAME):
    """What a serving process calls. A single line, insulated from run ids
    and experiment names. Defaults to the bounce-risk model since that's
    the one wired into services/api/routers/preflight.py today; pass
    ENGAGEMENT_MODEL_NAME explicitly for the engagement model."""
    return mlflow.sklearn.load_model(f"models:/{registered_name}@production")


_KIND_TO_NAME = {
    "bounce": BOUNCE_RISK_MODEL_NAME,
    "engagement": ENGAGEMENT_MODEL_NAME,
    "send-time": SEND_TIME_MODEL_NAME,
}

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[2] not in _KIND_TO_NAME:
        kinds = "|".join(_KIND_TO_NAME)
        print(f"usage: uv run python ml/registry/promote.py <model_uri> <{kinds}>")
        sys.exit(1)
    register_and_promote(sys.argv[1], registered_name=_KIND_TO_NAME[sys.argv[2]])

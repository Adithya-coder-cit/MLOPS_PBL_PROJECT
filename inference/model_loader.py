"""Model-loading abstraction for the (future) FastAPI inference layer.
Never hardcodes a local filename — always goes through the MLflow Model
Registry, either by the "production" alias or an explicitly given version.

Known MLflow/XGBoost interop gap (discovered and verified during Stage 5):
`mlflow.xgboost.load_model()` reconstructs an XGBClassifier from the saved
Booster but does not restore the sklearn wrapper's `n_classes_` attribute,
which `predict_proba` depends on — it raises AttributeError otherwise.
Also, MLflow's generic pyfunc schema enforcement does not support pandas
'category' dtype columns (it downcasts them to "string" in the signature,
then fails to cast the actual category column back at inference time), so
XGBoost models trained with `enable_categorical=True` (see
training/prepare_inputs.py) cannot be served through
`mlflow.pyfunc.load_model()`. This module loads via each model's native
MLflow flavor instead and applies the `n_classes_` fix for XGBoost.
Verified to produce byte-identical predict_proba output vs. the original
in-memory model (see training/mlflow_tracking.py's signature validation,
which re-loads through this exact path before trusting a logged model).
"""
from __future__ import annotations

from dataclasses import dataclass

import mlflow
import mlflow.sklearn
import mlflow.xgboost
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

DEFAULT_REGISTERED_MODEL_NAME = "RouteWise-Disruption-Model"

_BINARY_CLASSIFIER_N_CLASSES = 2


class NoProductionModelError(Exception):
    """Raised when no model version has been promoted to the "production"
    alias yet. Honest failure — never silently falls back to some other
    version."""


@dataclass
class ModelMetadata:
    model_name: str
    model_version: str
    run_id: str
    git_commit_sha: str | None
    dataset_version: str | None
    feature_manifest_schema_version: str | None
    training_timestamp: str | None
    training_dataset_period: dict
    evaluation_metrics: dict
    lifecycle_stage: str | None
    model_flavor: str | None


def _metadata_from_run(client: MlflowClient, model_name: str, version: str) -> ModelMetadata:
    mv = client.get_model_version(model_name, version)
    run = client.get_run(mv.run_id)
    tags, params, metrics = run.data.tags, run.data.params, run.data.metrics

    return ModelMetadata(
        model_name=model_name,
        model_version=version,
        run_id=mv.run_id,
        git_commit_sha=tags.get("git_commit_sha"),
        dataset_version=params.get("dataset_version"),
        feature_manifest_schema_version=tags.get("feature_manifest_schema_version"),
        training_timestamp=run.info.start_time and str(run.info.start_time),
        training_dataset_period={
            "train": tags.get("train_date_range"),
            "val": tags.get("val_date_range"),
            "test": tags.get("test_date_range"),
        },
        evaluation_metrics={k: v for k, v in metrics.items() if k.startswith(("val_", "test_"))},
        lifecycle_stage=(mv.tags or {}).get("lifecycle_stage"),
        model_flavor=(mv.tags or {}).get("model_flavor"),
    )


def load_native_model(model_uri: str, flavor: str):
    """Loads a model via its native MLflow flavor (not the generic pyfunc
    path — see module docstring for why) and repairs the known XGBoost
    `n_classes_` gap. `flavor` must be "sklearn" or "xgboost".
    """
    if flavor == "xgboost":
        model = mlflow.xgboost.load_model(model_uri)
        if not hasattr(model, "n_classes_"):
            model.n_classes_ = _BINARY_CLASSIFIER_N_CLASSES
        return model
    if flavor == "sklearn":
        return mlflow.sklearn.load_model(model_uri)
    raise ValueError(f"Unsupported model_flavor '{flavor}' — expected 'sklearn' or 'xgboost'")


def load_production_model(model_name: str = DEFAULT_REGISTERED_MODEL_NAME, tracking_uri: str | None = None):
    """Loads whichever model version currently holds the "production"
    alias. Raises NoProductionModelError if none exists — the application
    must handle this explicitly (e.g. return 503 from /model/info) rather
    than silently serving an unvetted model.
    """
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()
    try:
        mv = client.get_model_version_by_alias(model_name, "production")
    except MlflowException as e:
        raise NoProductionModelError(
            f"No model version is aliased 'production' for registered model '{model_name}'. "
            "A candidate must pass the promotion gate and be explicitly promoted "
            "(training/promote_model.py) before it can be served."
        ) from e
    metadata = _metadata_from_run(client, model_name, mv.version)
    model = load_native_model(f"models:/{model_name}@production", metadata.model_flavor)
    return model, metadata


def load_model_version(version: str, model_name: str = DEFAULT_REGISTERED_MODEL_NAME, tracking_uri: str | None = None):
    """Loads an explicitly selected model version, bypassing the
    production alias — for debugging/comparison, not normal serving."""
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()
    metadata = _metadata_from_run(client, model_name, version)
    model = load_native_model(f"models:/{model_name}/{version}", metadata.model_flavor)
    return model, metadata

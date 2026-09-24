"""Business logic for GET /system/status and GET /model/info. Every
field here is either a live check, a config value, or read from the
actual loaded model's metadata — nothing fabricated.
"""
from __future__ import annotations

import logging

import mlflow
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from api.config import API_VERSION, APP_VERSION, Settings
from inference.model_loader import ModelMetadata

logger = logging.getLogger("routewise.api")

ROUTING_ENGINE_VERSION = "1.0.0"  # bumped when src/routing/ behavior changes meaningfully


def _is_production_model_available(registered_model_name: str, tracking_uri: str) -> bool:
    try:
        mlflow.set_tracking_uri(tracking_uri)
        MlflowClient().get_model_version_by_alias(registered_model_name, "production")
        return True
    except MlflowException:
        return False
    except Exception:
        logger.warning("Could not reach MLflow registry to check production model availability", exc_info=True)
        return False


def build_system_status(
    settings: Settings, metadata: ModelMetadata | None, graph_available: bool,
) -> dict:
    production_available = _is_production_model_available(settings.registered_model_name, settings.mlflow_tracking_uri)
    return {
        "application_version": APP_VERSION,
        "api_version": API_VERSION,
        "model_name": metadata.model_name if metadata else None,
        "model_version": metadata.model_version if metadata else None,
        "model_lifecycle_stage": metadata.lifecycle_stage if metadata else None,
        "is_production_model": bool(metadata and metadata.lifecycle_stage == "Production"),
        "production_model_available": production_available,
        "configured_model_source": settings.model_source,
        "dataset_version": metadata.dataset_version if metadata else None,
        "feature_manifest_version": metadata.feature_manifest_schema_version if metadata else None,
        "routing_graph_available": graph_available,
        "routing_engine_version": ROUTING_ENGINE_VERSION,
        "environment": settings.app_env,
        "monitoring_status": "not_implemented",
    }


def build_model_info(metadata: ModelMetadata) -> dict:
    val_metrics = {k.removeprefix("val_"): v for k, v in metadata.evaluation_metrics.items() if k.startswith("val_")}
    test_metrics = {k.removeprefix("test_"): v for k, v in metadata.evaluation_metrics.items()
                     if k.startswith("test_")}
    return {
        "model_name": metadata.model_name, "model_version": metadata.model_version,
        "model_type": metadata.model_flavor or "unknown",
        "lifecycle_stage": metadata.lifecycle_stage, "mlflow_run_id": metadata.run_id,
        "git_commit_sha": metadata.git_commit_sha, "dataset_version": metadata.dataset_version,
        "feature_manifest_version": metadata.feature_manifest_schema_version,
        "training_timestamp": metadata.training_timestamp,
        "validation_metrics": val_metrics, "test_metrics": test_metrics,
        "is_production_model": metadata.lifecycle_stage == "Production",
    }

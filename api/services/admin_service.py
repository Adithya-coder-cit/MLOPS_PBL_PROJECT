"""Business logic for the internal engineering/MLOps admin API. Every
builder here reads a real, already-generated artifact from disk or the
real MLflow tracking/registry store — nothing is computed from scratch
per-request (that would mean re-running heavy pipeline stages inside an
HTTP request) and nothing is invented when an artifact is missing.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import mlflow
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from api.config import Settings

logger = logging.getLogger("routewise.api")

MODEL_READINESS_PATH = Path("data/interim/real/model_readiness.json")
EVALUATION_PATH = Path("models/evaluation/evaluation.json")
STAGE5_TRACKING_PATH = Path("models/evaluation/stage5_tracking_result.json")
LATEST_RETRAIN_REPORT_PATH = Path("models/retraining/latest_retrain_report.json")
FEATURE_IMPORTANCE_PATHS = {
    "random_forest": Path("models/feature_importance/random_forest_importance.json"),
    "xgboost": Path("models/feature_importance/xgboost_importance.json"),
}
ELIGIBILITY_REPORT_PATH = Path("data/interim/real/eligibility_report.json")
REAL_DATASET_READINESS_PATH = Path("data/interim/real/real_dataset_readiness.json")
ELIGIBLE_TEMPORAL_SPLIT_PATH = Path("data/interim/real/eligible_temporal_split.json")
WEATHER_COVERAGE_REPORT_PATH = Path("data/interim/real/weather_coverage_report.json")
FEATURE_COVERAGE_REPORT_PATH = Path("data/interim/real/feature_coverage_report.json")


def _read_json_or_none(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Could not parse admin artifact at %s", path, exc_info=True)
        return None


def _ts(epoch_ms: int | None) -> str | None:
    return datetime.fromtimestamp(epoch_ms / 1000).isoformat() if epoch_ms else None


# --- training status ---

def build_training_status() -> dict:
    real_readiness = _read_json_or_none(MODEL_READINESS_PATH)
    evaluation = _read_json_or_none(EVALUATION_PATH)
    stage5 = _read_json_or_none(STAGE5_TRACKING_PATH) or {}
    retrain_report = _read_json_or_none(LATEST_RETRAIN_REPORT_PATH)

    latest_completed_run = None
    if evaluation:
        run_metadata = evaluation.get("run_metadata", {})
        row_counts = run_metadata.get("dataset_metadata", {}).get("row_counts", {})
        models = []
        for model_type in ("random_forest", "xgboost"):
            m = evaluation.get(model_type)
            if not m:
                continue
            gate = stage5.get(model_type, {}).get("gate_result", {})
            registered_version = stage5.get(model_type, {}).get("model_version")
            models.append({
                "model_type": model_type,
                "feature_count": m.get("feature_count"),
                "test_f1": m.get("test_metrics", {}).get("f1"),
                "test_roc_auc": m.get("test_metrics", {}).get("roc_auc"),
                "registered_version": str(registered_version) if registered_version is not None else None,
                "run_id": stage5.get(model_type, {}).get("run_id"),
                "gate_passed": gate.get("passed"),
            })
        latest_completed_run = {
            "training_timestamp": run_metadata.get("training_timestamp"),
            "git_commit_sha": run_metadata.get("git_commit_sha"),
            "dataset_label": "Synthetic development dataset (DATA_MODE=demo) — not the real ingested dataset.",
            "dataset_version": run_metadata.get("dataset_metadata", {}).get("dataset_version"),
            "train_records": row_counts.get("train"),
            "validation_records": row_counts.get("val"),
            "test_records": row_counts.get("test"),
            "models": models,
        }

    latest_retraining_check = None
    if retrain_report:
        latest_retraining_check = {
            "timestamp": retrain_report.get("retraining_timestamp"),
            "dry_run": retrain_report.get("dry_run"),
            "decision": retrain_report.get("decision"),
        }

    return {
        "real_data_model_ready": real_readiness.get("MODEL_READY") if real_readiness else None,
        "real_data_model_ready_reason": real_readiness.get("primary_reason") if real_readiness else None,
        "real_data_blocking_reasons": real_readiness.get("blocking_reasons", []) if real_readiness else [],
        "active_training_run": None,
        "latest_completed_run": latest_completed_run,
        "latest_retraining_check": latest_retraining_check,
    }


# --- evaluation ---

def build_evaluation_overview() -> dict:
    evaluation = _read_json_or_none(EVALUATION_PATH)
    comparison = _read_json_or_none(Path("models/evaluation/model_comparison.json"))

    if evaluation is None:
        return {
            "available": False,
            "reason": "No saved evaluation artifact at models/evaluation/evaluation.json.",
            "selection_metric": None, "models": [], "comparison": [],
        }

    diagnostics = evaluation.get("diagnostics", {})
    models = []
    for model_type in ("random_forest", "xgboost"):
        m = evaluation.get(model_type)
        if not m:
            continue
        diag = diagnostics.get(model_type, {})
        importance = _read_json_or_none(FEATURE_IMPORTANCE_PATHS[model_type])
        models.append({
            "model_type": model_type,
            "validation_metrics": {k: v for k, v in m.get("validation_metrics", {}).items()
                                    if isinstance(v, int | float) and k != "confusion_matrix"},
            "test_metrics": {k: v for k, v in m.get("test_metrics", {}).items()
                              if isinstance(v, int | float) and k != "confusion_matrix"},
            "confusion_matrix": m.get("test_metrics", {}).get("confusion_matrix"),
            "threshold_sensitivity": diag.get("val_threshold_sensitivity"),
            "feature_importance": importance.get("top_features") if importance else None,
            "roc_curve_available": False,
            "pr_curve_available": False,
        })

    return {
        "available": True,
        "reason": None,
        "selection_metric": evaluation.get("selection_metric"),
        "models": models,
        "comparison": comparison.get("table", []) if comparison else [],
    }


# --- data summary ---

def build_data_summary() -> dict:
    eligibility = _read_json_or_none(ELIGIBILITY_REPORT_PATH)
    readiness = _read_json_or_none(REAL_DATASET_READINESS_PATH)
    split = _read_json_or_none(ELIGIBLE_TEMPORAL_SPLIT_PATH)
    weather = _read_json_or_none(WEATHER_COVERAGE_REPORT_PATH)
    feature_coverage = _read_json_or_none(FEATURE_COVERAGE_REPORT_PATH)

    if eligibility is None or readiness is None:
        return {
            "available": False,
            "reason": "Real-data eligibility/readiness reports aren't available under data/interim/real/.",
            "data_source": "MBTA (transit) + NOAA GHCNh (weather)",
            "total_real_records": None, "eligible_records": None, "excluded_records": None,
            "historical_feature_coverage": None, "weather_coverage": None, "weather_coverage_by_mode": {},
            "modes": [], "splits": [], "dvc_configured": Path(".dvc").exists(), "real_dataset_ready": None,
        }

    historical_coverage = (
        feature_coverage.get("historical_delay_seconds", {}).get("coverage") if feature_coverage else None
    )

    splits = []
    modes: set[str] = set()
    if split:
        for split_name, split_data in split.get("splits", {}).items():
            mode_dist = split_data.get("mode_distribution", {})
            modes.update(mode_dist.keys())
            splits.append({
                "split": split_name,
                "records": split_data.get("row_count"),
                "positive_rate": split_data.get("positive_rate"),
                "modes": mode_dist,
            })

    return {
        "available": True,
        "reason": None,
        "data_source": "MBTA (transit) + NOAA GHCNh (weather)",
        "total_real_records": eligibility.get("total_real_records"),
        "eligible_records": eligibility.get("eligible_records"),
        "excluded_records": eligibility.get("excluded_records"),
        "historical_feature_coverage": historical_coverage,
        "weather_coverage": (
            readiness.get("weather_coverage_informational")
            or (weather.get("overall_coverage") if weather else None)
        ),
        "weather_coverage_by_mode": weather.get("coverage_by_mode", {}) if weather else {},
        "modes": sorted(modes),
        "splits": splits,
        "dvc_configured": Path(".dvc").exists(),
        "real_dataset_ready": readiness.get("REAL_DATASET_READY"),
    }


# --- model registry ---

def build_registry_overview(settings: Settings) -> dict:
    try:
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        client = MlflowClient()
        registered_models = client.search_registered_models()
    except Exception:
        logger.warning("Could not reach MLflow registry", exc_info=True)
        return {
            "available": False, "reason": "MLflow registry is unreachable.",
            "total_models": 0, "total_versions": 0, "stage_counts": {}, "models": [],
        }

    models_out = []
    total_versions = 0
    stage_counts: dict[str, int] = {}

    for rm in registered_models:
        versions = client.search_model_versions(f"name='{rm.name}'")
        total_versions += len(versions)

        production_version = None
        try:
            production_version = client.get_model_version_by_alias(rm.name, "production").version
        except MlflowException:
            pass

        version_rows = []
        for v in sorted(versions, key=lambda x: int(x.version), reverse=True):
            stage = (v.tags or {}).get("lifecycle_stage", "Unknown")
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
            metrics: dict = {}
            try:
                run = client.get_run(v.run_id)
                metrics = dict(run.data.metrics)
            except Exception:
                pass
            version_rows.append({
                "version": str(v.version),
                "lifecycle_stage": stage,
                "is_production": production_version is not None and str(v.version) == str(production_version),
                "test_f1": metrics.get("test_f1"),
                "test_roc_auc": metrics.get("test_roc_auc"),
                "created": _ts(v.creation_timestamp),
                "run_id": v.run_id,
            })

        latest = version_rows[0] if version_rows else None
        models_out.append({
            "name": rm.name,
            "description": rm.description,
            "latest_version": latest["version"] if latest else None,
            "latest_lifecycle_stage": latest["lifecycle_stage"] if latest else None,
            "production_version": str(production_version) if production_version else None,
            "created": _ts(rm.creation_timestamp),
            "versions": version_rows,
        })

    return {
        "available": True,
        "reason": None,
        "total_models": len(registered_models),
        "total_versions": total_versions,
        "stage_counts": stage_counts,
        "models": models_out,
    }


# --- run detail ---

def build_run_detail(settings: Settings, run_id: str) -> dict | None:
    try:
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        client = MlflowClient()
        run = client.get_run(run_id)
    except Exception:
        return None

    versions = client.search_model_versions(f"run_id='{run_id}'")
    version = versions[0] if versions else None

    artifact_paths: list[str] = []
    try:
        artifact_paths = [a.path for a in client.list_artifacts(run_id, path="evaluation")]
    except Exception:
        pass

    info, data = run.info, run.data
    return {
        "run_id": info.run_id,
        "run_name": data.tags.get("mlflow.runName"),
        "status": info.status,
        "start_time": _ts(info.start_time),
        "end_time": _ts(info.end_time),
        "params": dict(data.params),
        "metrics": dict(data.metrics),
        "tags": {k: v for k, v in data.tags.items() if not k.startswith("mlflow.")},
        "registered_version": str(version.version) if version else None,
        "lifecycle_stage": version.tags.get("lifecycle_stage") if version else None,
        "artifact_paths": artifact_paths,
    }

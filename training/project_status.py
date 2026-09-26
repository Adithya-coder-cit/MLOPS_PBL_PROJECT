"""Stage 10 §26: a single machine-readable snapshot of the whole RouteWise
MLOps lifecycle's real, current state — every value is read from an
actual artifact (MLflow registry, the last monitoring report, the last
retraining report, git) or explicitly set to null/NOT_AVAILABLE. Nothing
here is guessed or fabricated.

Run: python -m training.project_status
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import mlflow
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from src.monitoring.reports import read_latest_report as read_latest_monitoring_report
from training.retrain import LATEST_REPORT_PATH as LATEST_RETRAIN_REPORT_PATH

logger = logging.getLogger("routewise.training.project_status")

NOT_AVAILABLE = "NOT_AVAILABLE"
PROCESSED_DIR = Path("data/processed")
CI_WORKFLOW_PATH = Path(".github/workflows/ci.yml")

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT, text=True).strip()
    except Exception:
        return None


def _dataset_version() -> str | None:
    path = PROCESSED_DIR / "dataset_metadata.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("dataset_version")


def _feature_manifest_version() -> str | None:
    path = PROCESSED_DIR / "feature_manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("schema_version")


def _registry_snapshot(registered_model_name: str, tracking_uri: str) -> dict:
    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient()
    try:
        versions = client.search_model_versions(f"name='{registered_model_name}'")
    except MlflowException:
        return {"candidate_model_version": None, "production_model_version": None, "promotion_status": "NO_MODEL"}

    if not versions:
        return {"candidate_model_version": None, "production_model_version": None, "promotion_status": "NO_MODEL"}

    production_version = None
    try:
        production_version = client.get_model_version_by_alias(registered_model_name, "production").version
    except MlflowException:
        pass

    latest = max(versions, key=lambda mv: int(mv.version))
    candidate_version = latest.version

    if production_version is not None:
        promotion_status = "PRODUCTION_ACTIVE"
    elif any((mv.tags or {}).get("lifecycle_stage") == "Validated" for mv in versions):
        promotion_status = "VALIDATED_AWAITING_MANUAL_PROMOTION"
    else:
        promotion_status = "CANDIDATE_ONLY"

    return {
        "candidate_model_version": candidate_version,
        "production_model_version": production_version,
        "promotion_status": promotion_status,
    }


def build_project_status(
    registered_model_name: str = "RouteWise-Disruption-Model", tracking_uri: str = "./mlruns",
) -> dict:
    registry = _registry_snapshot(registered_model_name, tracking_uri)

    monitoring_report = read_latest_monitoring_report()
    monitoring_status = monitoring_report.get("decision") if monitoring_report else "NOT_RUN"
    last_monitoring_run = monitoring_report.get("monitoring_timestamp") if monitoring_report else None

    retraining_report = None
    if LATEST_RETRAIN_REPORT_PATH.exists():
        retraining_report = json.loads(LATEST_RETRAIN_REPORT_PATH.read_text(encoding="utf-8"))
    last_retraining_run = retraining_report.get("retraining_timestamp") if retraining_report else None

    return {
        "repository": "RouteWise",
        "git_sha": _git_sha(),
        "dataset_version": _dataset_version(),
        "feature_manifest_version": _feature_manifest_version(),
        "model_name": registered_model_name,
        "candidate_model_version": registry["candidate_model_version"],
        "production_model_version": registry["production_model_version"],
        "monitoring_status": monitoring_status,
        "last_monitoring_run": last_monitoring_run,
        "last_retraining_run": last_retraining_run,
        "promotion_status": registry["promotion_status"],
        "ci_status": NOT_AVAILABLE,
        "ci_status_note": (
            "CI pass/fail can only be verified via the actual GitHub Actions run for a given commit "
            f"(see {CI_WORKFLOW_PATH}); this local snapshot cannot observe that state, so it is never "
            "fabricated here."
        ),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    status = build_project_status()
    out_path = Path("models/project_status.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    logger.info("Project status written to %s", out_path)
    print(json.dumps(status, indent=2))

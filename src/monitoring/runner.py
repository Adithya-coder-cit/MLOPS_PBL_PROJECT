"""Stage 9 monitoring entry point — orchestrates data quality, feature
drift, prediction drift, and performance monitoring into one
MonitoringResult, then writes the machine-readable JSON report.

Run: python -m src.monitoring.runner
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import joblib
import yaml

from inference.model_loader import ModelMetadata
from src.monitoring import data_drift, data_quality, decision, performance, prediction_drift, reference, reports
from src.monitoring.schemas import DATASET_TYPE, MonitoringResult
from src.routing.prediction_source import get_prediction_source
from training.data_loader import manifest_feature_columns
from training.prepare_inputs import get_target

logger = logging.getLogger("routewise.monitoring")

PARAMS_PATH = Path("params.yaml")
PREPROCESSOR_PATH = Path("data/processed/preprocessor.joblib")


def _resolve_features(config: dict, feature_manifest: dict) -> list[str]:
    configured = config.get("monitored_features") or []
    return list(configured) if configured else manifest_feature_columns(feature_manifest)


def _load_source(
    model_source: str, candidate_version: str | None, registered_model_name: str, tracking_uri: str | None,
):
    if model_source == "production":
        return get_prediction_source(kind="production", model_name=registered_model_name, tracking_uri=tracking_uri)
    if not candidate_version:
        raise ValueError(
            "model_source='candidate' requires an explicit candidate_version "
            "(pass --candidate-version, or set MODEL_CANDIDATE_VERSION for the CLI entry point)."
        )
    return get_prediction_source(
        kind="candidate", candidate_version=candidate_version, model_name=registered_model_name,
        tracking_uri=tracking_uri,
    )


def run_monitoring(
    params_config: dict | None = None,
    model_source: str = "candidate",
    candidate_version: str | None = None,
    registered_model_name: str = "RouteWise-Disruption-Model",
    tracking_uri: str | None = "./mlruns",
    force_reference: bool = False,
) -> MonitoringResult:
    params_config = params_config or yaml.safe_load(PARAMS_PATH.read_text(encoding="utf-8"))
    cfg = params_config["monitoring"]

    dataset_metadata = reference.load_dataset_metadata()
    feature_manifest = reference.load_feature_manifest()
    features = _resolve_features(cfg, feature_manifest)

    ref_df = reference.load_split(cfg["reference"]["split"])
    cur_df = reference.load_split(cfg["current"]["split"])

    if len(cur_df) < cfg["minimum_batch_size"]:
        raise ValueError(
            f"Current batch has {len(cur_df)} rows, below the configured "
            f"minimum_batch_size={cfg['minimum_batch_size']} — refusing to run a statistically unreliable check."
        )

    source = _load_source(model_source, candidate_version, registered_model_name, tracking_uri)
    model_meta: ModelMetadata = source.metadata

    ref_meta = reference.establish_or_verify_reference(
        cfg["reference"]["split"], model_meta.model_name, model_meta.model_version, model_meta.git_commit_sha,
        force=force_reference,
    )

    # --- data quality ---
    dq_issues, dq_raw = data_quality.run_data_quality(ref_df, cur_df, feature_manifest, cfg["data_quality"])
    dq_status = data_quality.data_quality_status(dq_issues)

    # --- feature drift ---
    data_drift_html = reports.HTML_REPORTS_DIR / "data_drift.html"
    drift_result = data_drift.run_feature_drift(ref_df, cur_df, features, cfg["data_drift"], html_path=data_drift_html)
    drift_status = data_drift.feature_drift_status(drift_result)

    # --- predictions, shared by prediction drift + performance ---
    preprocessor = joblib.load(PREPROCESSOR_PATH) if PREPROCESSOR_PATH.exists() else None
    ref_prob = prediction_drift.predict_probabilities(source.model, model_meta.model_flavor, ref_df, preprocessor)
    cur_prob = prediction_drift.predict_probabilities(source.model, model_meta.model_flavor, cur_df, preprocessor)

    prediction_drift_html = reports.HTML_REPORTS_DIR / "prediction_drift.html"
    pred_drift_result = prediction_drift.run_prediction_drift(
        ref_prob, cur_prob, cfg["prediction_drift"], html_path=prediction_drift_html,
    )
    pred_drift_status = prediction_drift.prediction_drift_status(pred_drift_result)

    # --- performance (only meaningful if the current batch has labels) ---
    baseline_metrics = {
        k.removeprefix("test_"): v for k, v in model_meta.evaluation_metrics.items() if k.startswith("test_")
    }
    y_true = get_target(cur_df).to_numpy() if "disruption_flag" in cur_df.columns else None
    perf_result = performance.run_performance_monitoring(
        y_true, cur_prob, baseline_metrics, cfg["performance"]["regression_tolerance"],
    )
    perf_status = performance.performance_status(perf_result)

    decision_value, decision_reasons = decision.decide(
        dq_status, drift_status, pred_drift_status, perf_status, cfg["decision_policy"],
    )

    result = MonitoringResult(
        monitoring_timestamp=reports.now_iso(),
        dataset_type=DATASET_TYPE,
        reference_dataset_version=ref_meta["dataset_version"],
        current_dataset_version=dataset_metadata["dataset_version"],
        reference_period=ref_meta["reference_period"],
        current_period=reference.split_period(dataset_metadata, cfg["current"]["split"]),
        model_name=model_meta.model_name,
        model_version=model_meta.model_version,
        git_sha=model_meta.git_commit_sha,
        feature_manifest_version=feature_manifest["schema_version"],
        monitored_features=features,
        data_quality={"issues": [i.to_dict() for i in dq_issues], "evidently_missing_values_summary": dq_raw},
        data_quality_status=dq_status,
        data_drift=drift_result,
        data_drift_status=drift_status,
        prediction_drift=pred_drift_result,
        prediction_drift_status=pred_drift_status,
        performance=perf_result,
        performance_status=perf_status,
        operational_status="NOT_AVAILABLE",
        decision=decision_value,
        decision_reasons=decision_reasons,
        overall_status=decision_value,
        html_reports={"data_drift": str(data_drift_html), "prediction_drift": str(prediction_drift_html)},
    )
    reports.write_json_report(result)
    logger.info("Monitoring run complete: decision=%s (%s)", decision_value, "; ".join(decision_reasons))
    return result


if __name__ == "__main__":
    from api.config import get_settings

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-version", default=None)
    parser.add_argument("--force-reference", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    run_monitoring(
        model_source=settings.model_source,
        candidate_version=args.candidate_version or settings.model_candidate_version,
        registered_model_name=settings.registered_model_name,
        tracking_uri=settings.mlflow_tracking_uri,
        force_reference=args.force_reference,
    )

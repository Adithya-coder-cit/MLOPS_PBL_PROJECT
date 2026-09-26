"""Stage 5 orchestrator: connect the EXISTING Stage 4 training artifacts
to MLflow experiment tracking and the Model Registry. Does not retrain —
loads models/candidates/*.joblib and models/evaluation/evaluation.json
(both produced by `python -m training.train`) and logs them faithfully.

Run: python -m training.track_and_register
"""
from __future__ import annotations

import argparse
import json
import logging
import tempfile
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import mlflow.xgboost
import pandas as pd
import yaml

from training.data_loader import PROCESSED_DIR
from training.mlflow_tracking import log_and_register_model
from training.prepare_inputs import build_random_forest_matrix, build_xgboost_matrix
from training.reproducibility import capture_run_metadata

logger = logging.getLogger("routewise.training.track_and_register")

MODELS_DIR = Path("models")
PARAMS_PATH = Path("params.yaml")


VALID_MODELS = {"random_forest", "xgboost"}


def main(processed_dir: Path = PROCESSED_DIR, models_dir: Path = MODELS_DIR, models: set[str] | None = None) -> dict:
    """`models`: subset of {"random_forest", "xgboost"} to log+register —
    None (default) registers both, unchanged from the original Stage 5
    behavior. Used by Stage 10's retraining pipeline to optionally
    restrict a run to one model family without duplicating this function.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    models = models if models is not None else VALID_MODELS
    if not models <= VALID_MODELS:
        raise ValueError(f"Unknown model(s) {models - VALID_MODELS}, expected subset of {VALID_MODELS}")
    params = yaml.safe_load(PARAMS_PATH.read_text(encoding="utf-8"))

    logger.info("Loading EXISTING Stage 4 artifacts (no retraining)")
    evaluation = json.loads((models_dir / "evaluation" / "evaluation.json").read_text(encoding="utf-8"))
    feature_manifest = json.loads((processed_dir / "feature_manifest.json").read_text(encoding="utf-8"))
    rf_importance = json.loads(
        (models_dir / "feature_importance" / "random_forest_importance.json").read_text(encoding="utf-8")
    )
    xgb_importance = json.loads(
        (models_dir / "feature_importance" / "xgboost_importance.json").read_text(encoding="utf-8")
    )

    rf_model = joblib.load(models_dir / "candidates" / "random_forest_tuned.joblib")
    xgb_model = joblib.load(models_dir / "candidates" / "xgboost_tuned.joblib")
    preprocessor = joblib.load(processed_dir / "preprocessor.joblib")

    val_df = pd.read_parquet(processed_dir / "val.parquet").head(20)
    X_rf_sample = build_random_forest_matrix(val_df, preprocessor)
    X_xgb_sample = build_xgboost_matrix(val_df)

    run_metadata = capture_run_metadata(
        evaluation["run_metadata"]["dataset_metadata"], feature_manifest, params["training"]["seed"]
    )

    mlflow.set_tracking_uri(params["mlflow"]["tracking_uri"])
    mlflow.set_experiment(params["mlflow"]["experiment_name"])
    registered_model_name = params["mlflow"]["registered_model_name"]
    gate_config = params["evaluation"]["promotion_gates"]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        rf_summary = None
        if "random_forest" in models:
            logger.info("Logging + registering Random Forest (tuned)")
            rf_summary = log_and_register_model(
                model_label="random_forest", model_type="random_forest", model=rf_model,
                flavor_log_fn=mlflow.sklearn.log_model, model_flavor="sklearn", X_signature_sample=X_rf_sample,
                params=evaluation["random_forest"]["params"],
                val_metrics=evaluation["random_forest"]["validation_metrics"],
                test_metrics=evaluation["random_forest"]["test_metrics"],
                run_metadata=run_metadata, evaluation_payload=evaluation,
                feature_importance=rf_importance, feature_manifest=feature_manifest,
                registered_model_name=registered_model_name, gate_config=gate_config, artifacts_tmp_dir=tmp_dir,
            )

        xgb_summary = None
        if "xgboost" in models:
            logger.info("Logging + registering XGBoost (tuned)")
            xgb_summary = log_and_register_model(
                model_label="xgboost", model_type="xgboost", model=xgb_model,
                flavor_log_fn=mlflow.xgboost.log_model, model_flavor="xgboost", X_signature_sample=X_xgb_sample,
                params=evaluation["xgboost"]["params"],
                val_metrics=evaluation["xgboost"]["validation_metrics"],
                test_metrics=evaluation["xgboost"]["test_metrics"],
                run_metadata=run_metadata, evaluation_payload=evaluation,
                feature_importance=xgb_importance, feature_manifest=feature_manifest,
                registered_model_name=registered_model_name, gate_config=gate_config, artifacts_tmp_dir=tmp_dir,
            )

    result = {"random_forest": rf_summary, "xgboost": xgb_summary, "registered_model_name": registered_model_name,
              "experiment_name": params["mlflow"]["experiment_name"]}
    (models_dir / "evaluation" / "stage5_tracking_result.json").write_text(json.dumps(result, indent=2),
                                                                            encoding="utf-8")
    logger.info("Stage 5 tracking complete: %s", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--models-dir", default=str(MODELS_DIR))
    args = parser.parse_args()
    main(Path(args.processed_dir), Path(args.models_dir))

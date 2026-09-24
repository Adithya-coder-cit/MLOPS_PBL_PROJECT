"""Stage 5 §9: reproducibility test. Re-trains ONLY the final chosen
configuration for each model (not the full Stage 4 tuning grid — that
would be re-tuning, not reproducibility verification) against the exact
same Stage 3 processed dataset, and compares BOTH:

1. predictions — the rerun model's predict_proba on the test set vs. the
   ORIGINAL Stage 4 joblib artifact's predict_proba on the same rows.
2. metrics — the rerun's computed test metrics vs. the original
   evaluation.json test metrics.

Per the Stage 5 brief: byte-identical model files are not required —
predictions/metrics are compared instead, with an explicit tolerance.

Run: python -m training.reproducibility_check
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier

from training.data_loader import PROCESSED_DIR, TARGET_COLUMN, load_processed_datasets
from training.evaluate import compute_metrics
from training.prepare_inputs import build_random_forest_matrix, build_xgboost_matrix, get_target

logger = logging.getLogger("routewise.training.reproducibility_check")

METRIC_TOLERANCE = 1e-4
PREDICTION_TOLERANCE = 1e-4


def _compare_metric(name: str, original: float, rerun: float, tolerance: float) -> dict:
    diff = abs(original - rerun)
    return {"metric": name, "original": original, "rerun": rerun, "diff": diff,
            "within_tolerance": diff <= tolerance}


def check_model(
    label: str, model_ctor, model_params: dict, X_train, y_train, X_test, y_test,
    original_model, original_test_metrics: dict,
) -> dict:
    logger.info("Re-training %s with the FINAL chosen configuration only: %s", label, model_params)
    start = time.perf_counter()
    model = model_ctor(**model_params)
    model.fit(X_train, y_train)
    elapsed = time.perf_counter() - start

    rerun_prob = model.predict_proba(X_test)[:, 1]
    original_prob = original_model.predict_proba(X_test)[:, 1]

    max_prediction_diff = float(np.max(np.abs(rerun_prob - original_prob)))
    predictions_match = max_prediction_diff <= PREDICTION_TOLERANCE

    rerun_metrics = compute_metrics(y_test, rerun_prob, threshold=original_test_metrics["threshold"])
    metric_comparisons = [
        _compare_metric(m, original_test_metrics[m], rerun_metrics[m], METRIC_TOLERANCE)
        for m in ["accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc"]
    ]
    all_metrics_match = all(c["within_tolerance"] for c in metric_comparisons)

    return {
        "label": label, "rerun_training_time_seconds": elapsed,
        "prediction_comparison": {
            "n_predictions_compared": len(rerun_prob), "max_absolute_diff": max_prediction_diff,
            "tolerance": PREDICTION_TOLERANCE, "within_tolerance": predictions_match,
        },
        "metric_comparisons": metric_comparisons, "all_metrics_within_tolerance": all_metrics_match,
        "reproducible": predictions_match and all_metrics_match,
    }


def main(processed_dir: Path = PROCESSED_DIR, models_dir: Path = Path("models")) -> dict:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    logger.info("Loading the SAME Stage 3 processed dataset used originally")
    data = load_processed_datasets(processed_dir)
    y_train = get_target(data.train, TARGET_COLUMN)
    y_test = get_target(data.test, TARGET_COLUMN)

    original_evaluation = json.loads((models_dir / "evaluation" / "evaluation.json").read_text(encoding="utf-8"))
    original_xgb = joblib.load(models_dir / "candidates" / "xgboost_tuned.joblib")
    original_rf = joblib.load(models_dir / "candidates" / "random_forest_tuned.joblib")

    X_train_xgb = build_xgboost_matrix(data.train)
    X_test_xgb = build_xgboost_matrix(data.test)
    xgb_params = dict(original_evaluation["xgboost"]["params"])
    xgb_result = check_model(
        "xgboost", lambda **kw: XGBClassifier(**kw, enable_categorical=True, tree_method="hist"),
        xgb_params, X_train_xgb, y_train, X_test_xgb, y_test,
        original_xgb, original_evaluation["xgboost"]["test_metrics"],
    )

    X_train_rf = build_random_forest_matrix(data.train, data.preprocessor)
    X_test_rf = build_random_forest_matrix(data.test, data.preprocessor)
    rf_params = dict(original_evaluation["random_forest"]["params"])
    rf_result = check_model(
        "random_forest", RandomForestClassifier,
        rf_params, X_train_rf, y_train, X_test_rf, y_test,
        original_rf, original_evaluation["random_forest"]["test_metrics"],
    )

    result = {
        "metric_tolerance": METRIC_TOLERANCE, "prediction_tolerance": PREDICTION_TOLERANCE,
        "xgboost": xgb_result, "random_forest": rf_result,
        "overall_reproducible": xgb_result["reproducible"] and rf_result["reproducible"],
    }

    out_path = models_dir / "evaluation" / "reproducibility_check.json"
    out_path.write_text(json.dumps(result, indent=2, default=float), encoding="utf-8")
    logger.info("Reproducibility check complete. Overall reproducible: %s. Report: %s",
                result["overall_reproducible"], out_path)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--models-dir", default="models")
    args = parser.parse_args()
    main(Path(args.processed_dir), Path(args.models_dir))

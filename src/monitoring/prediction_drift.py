"""Prediction drift: reference vs current distribution of the model's OWN
outputs — predicted probability (numeric) and predicted class
(categorical) — deliberately distinct from feature drift
(src/monitoring/data_drift.py). See Stage 9 §11: prediction drift is
reported and decided on separately from feature drift, never conflated.

Predictions are generated through the exact same input-matrix builders
training uses (training/prepare_inputs.py) — no feature engineering is
re-derived here.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from evidently.metrics import ColumnDriftMetric
from evidently.pipeline.column_mapping import ColumnMapping
from evidently.report import Report

from src.monitoring.schemas import DRIFT_DETECTED, NO_DRIFT
from training.prepare_inputs import build_random_forest_matrix, build_xgboost_matrix

DEFAULT_DECISION_THRESHOLD = 0.5


def predict_probabilities(model, model_flavor: str, df: pd.DataFrame, preprocessor=None) -> np.ndarray:
    if model_flavor == "xgboost":
        X = build_xgboost_matrix(df)
    elif model_flavor == "sklearn":
        if preprocessor is None:
            raise ValueError("preprocessor is required to score a 'sklearn'-flavored model")
        X = build_random_forest_matrix(df, preprocessor)
    else:
        raise ValueError(f"Unsupported model_flavor '{model_flavor}' — expected 'xgboost' or 'sklearn'")
    return model.predict_proba(X)[:, 1]


def _summary(prob: np.ndarray) -> dict:
    return {
        "mean": float(np.mean(prob)), "std": float(np.std(prob)),
        "min": float(np.min(prob)), "max": float(np.max(prob)),
    }


def run_prediction_drift(
    reference_prob: np.ndarray, current_prob: np.ndarray, config: dict,
    decision_threshold: float = DEFAULT_DECISION_THRESHOLD,
    html_path: Path | None = None,
) -> dict:
    ref_df = pd.DataFrame({
        "predicted_probability": reference_prob,
        "predicted_class": (reference_prob >= decision_threshold).astype(int).astype(str),
    })
    cur_df = pd.DataFrame({
        "predicted_probability": current_prob,
        "predicted_class": (current_prob >= decision_threshold).astype(int).astype(str),
    })

    report = Report(metrics=[
        ColumnDriftMetric(column_name="predicted_probability", stattest=config["probability_stattest"],
                           stattest_threshold=config["probability_threshold"]),
        ColumnDriftMetric(column_name="predicted_class", stattest=config["class_stattest"],
                           stattest_threshold=config["class_threshold"]),
    ])
    report.run(
        reference_data=ref_df, current_data=cur_df,
        column_mapping=ColumnMapping(numerical_features=["predicted_probability"],
                                      categorical_features=["predicted_class"]),
    )
    if html_path is not None:
        html_path.parent.mkdir(parents=True, exist_ok=True)
        report.save_html(str(html_path))
    results = report.as_dict()["metrics"]
    prob_result = results[0]["result"]
    class_result = results[1]["result"]

    return {
        "decision_threshold": decision_threshold,
        "predicted_probability_drift": {
            "stattest": prob_result.get("stattest_name"), "drift_score": prob_result.get("drift_score"),
            "drift_detected": bool(prob_result.get("drift_detected")),
        },
        "predicted_class_drift": {
            "stattest": class_result.get("stattest_name"), "drift_score": class_result.get("drift_score"),
            "drift_detected": bool(class_result.get("drift_detected")),
        },
        "reference_probability_summary": _summary(reference_prob),
        "current_probability_summary": _summary(current_prob),
    }


def prediction_drift_status(result: dict) -> str:
    drifted = (
        result["predicted_probability_drift"]["drift_detected"]
        or result["predicted_class_drift"]["drift_detected"]
    )
    return DRIFT_DETECTED if drifted else NO_DRIFT

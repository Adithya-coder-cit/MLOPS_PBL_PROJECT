"""Feature (data) drift: reference vs current distribution of the
model's own input features, via Evidently's ColumnDriftMetric/
DatasetDriftMetric — the installed API (evidently==0.4.40, see
requirements.txt) was inspected directly before writing this, not assumed
from another version's docs. Methods and thresholds are configurable
(params.yaml monitoring.data_drift), never hardcoded here.

This is deliberately DISTINCT from prediction drift
(src/monitoring/prediction_drift.py) — see Stage 9 §11: the two are
reported and decided on separately, never conflated.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from evidently.metrics import ColumnDriftMetric, DatasetDriftMetric
from evidently.pipeline.column_mapping import ColumnMapping
from evidently.report import Report

from src.monitoring.schemas import DRIFT_DETECTED, NO_DRIFT


def split_feature_types(df: pd.DataFrame, features: list[str]) -> tuple[list[str], list[str]]:
    """Numeric vs categorical, read from the DataFrame's own dtypes —
    never a second hardcoded feature-type list to keep in sync."""
    numeric = [c for c in features if pd.api.types.is_numeric_dtype(df[c])]
    categorical = [c for c in features if c not in numeric]
    return numeric, categorical


def run_feature_drift(
    reference: pd.DataFrame, current: pd.DataFrame, features: list[str], config: dict,
    html_path: Path | None = None,
) -> dict:
    numeric, categorical = split_feature_types(reference, features)
    column_mapping = ColumnMapping(numerical_features=numeric, categorical_features=categorical)

    per_column_stattest = {c: config["numerical_stattest"] for c in numeric}
    per_column_stattest.update({c: config["categorical_stattest"] for c in categorical})
    per_column_threshold = {c: config["numerical_threshold"] for c in numeric}
    per_column_threshold.update({c: config["categorical_threshold"] for c in categorical})

    metrics = [
        ColumnDriftMetric(column_name=c, stattest=per_column_stattest[c], stattest_threshold=per_column_threshold[c])
        for c in features
    ]
    metrics.append(
        DatasetDriftMetric(
            columns=features,
            drift_share=config["dataset_drift_share"],
            per_column_stattest=per_column_stattest,
            per_column_stattest_threshold=per_column_threshold,
        )
    )

    report = Report(metrics=metrics)
    report.run(reference_data=reference[features], current_data=current[features], column_mapping=column_mapping)
    if html_path is not None:
        html_path.parent.mkdir(parents=True, exist_ok=True)
        report.save_html(str(html_path))
    results = report.as_dict()["metrics"]

    per_feature = {}
    for i, col in enumerate(features):
        r = results[i]["result"]
        per_feature[col] = {
            "column_type": "numerical" if col in numeric else "categorical",
            "stattest": r.get("stattest_name"),
            "drift_score": r.get("drift_score"),
            "drift_detected": bool(r.get("drift_detected")),
        }

    dataset_result = results[-1]["result"]
    return {
        "per_feature": per_feature,
        "number_of_columns": dataset_result.get("number_of_columns"),
        "number_of_drifted_columns": dataset_result.get("number_of_drifted_columns"),
        "share_of_drifted_columns": dataset_result.get("share_of_drifted_columns"),
        "dataset_drift_share_threshold": config["dataset_drift_share"],
        "dataset_drift_detected": bool(dataset_result.get("dataset_drift")),
    }


def feature_drift_status(result: dict) -> str:
    return DRIFT_DETECTED if result.get("dataset_drift_detected") else NO_DRIFT

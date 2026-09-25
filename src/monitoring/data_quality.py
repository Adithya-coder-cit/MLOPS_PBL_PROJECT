"""Data quality monitoring on the processed feature table: missing
values (via Evidently), schema changes, new/unseen categorical values,
values outside the reference-observed range, and duplicate records.

Reuses the existing ValidationIssue reporting primitive
(src/validation/validators.py) rather than inventing a second issue
type — Stage 3's validators check the RAW GTFS tables against fixed
schemas; these checks instead compare the CURRENT processed batch
against the REFERENCE processed batch, which is a distinct concern
(observability, not a pipeline gate) but the same reporting shape.
"""
from __future__ import annotations

import pandas as pd
from evidently.metrics import DatasetMissingValuesMetric
from evidently.pipeline.column_mapping import ColumnMapping
from evidently.report import Report

from src.monitoring.data_drift import split_feature_types
from src.monitoring.schemas import FAIL, PASS
from src.validation.validators import ERROR, WARNING, ValidationIssue

TABLE_NAME = "current_monitoring_batch"


def run_missing_values_check(
    reference: pd.DataFrame, current: pd.DataFrame, features: list[str], max_missing_share: float
) -> tuple[list[ValidationIssue], dict]:
    report = Report(metrics=[DatasetMissingValuesMetric()])
    report.run(reference_data=reference[features], current_data=current[features], column_mapping=ColumnMapping())
    raw = report.as_dict()["metrics"][0]["result"]["current"]

    issues = []
    for col, share in raw.get("share_of_missing_values_by_column", {}).items():
        if share > max_missing_share:
            issues.append(ValidationIssue(
                ERROR, TABLE_NAME, "missing_values",
                f"Column '{col}' has {share:.1%} missing values in the current batch, above the configured "
                f"max_missing_share={max_missing_share:.1%}",
                raw.get("number_of_missing_values_by_column", {}).get(col, 0),
            ))
    return issues, raw


def check_schema(current: pd.DataFrame, features: list[str]) -> list[ValidationIssue]:
    missing = [c for c in features if c not in current.columns]
    if missing:
        return [ValidationIssue(
            ERROR, TABLE_NAME, "schema_change",
            f"Monitored feature column(s) missing from the current batch: {missing}", len(missing),
        )]
    return []


def check_categorical_new_values(
    reference: pd.DataFrame, current: pd.DataFrame, categorical_features: list[str]
) -> list[ValidationIssue]:
    issues = []
    for col in categorical_features:
        known = set(reference[col].dropna().astype(str))
        observed = set(current[col].dropna().astype(str))
        unseen = observed - known
        if unseen:
            n = int(current[col].astype(str).isin(unseen).sum())
            issues.append(ValidationIssue(
                WARNING, TABLE_NAME, "categorical_value_change",
                f"Column '{col}' has value(s) {sorted(unseen)} not present in the reference distribution", n,
            ))
    return issues


def check_ranges_vs_reference(
    reference: pd.DataFrame, current: pd.DataFrame, numeric_features: list[str], tolerance_std: float
) -> list[ValidationIssue]:
    issues = []
    for col in numeric_features:
        ref_col = reference[col].dropna()
        if ref_col.empty:
            continue
        std = ref_col.std()
        lo = ref_col.min() - tolerance_std * std
        hi = ref_col.max() + tolerance_std * std
        out_of_range = current[col].notna() & ((current[col] < lo) | (current[col] > hi))
        n_bad = int(out_of_range.sum())
        if n_bad > 0:
            issues.append(ValidationIssue(
                WARNING, TABLE_NAME, "range_vs_reference",
                f"Column '{col}' has {n_bad} value(s) outside the reference-observed range "
                f"[{lo:.3f}, {hi:.3f}] (± {tolerance_std} reference std)", n_bad,
            ))
    return issues


def check_duplicates(current: pd.DataFrame, key_column: str = "record_id") -> list[ValidationIssue]:
    if key_column not in current.columns:
        return []
    n_dupes = int(current[key_column].duplicated().sum())
    if n_dupes > 0:
        return [ValidationIssue(
            ERROR, TABLE_NAME, "duplicate_records", f"{n_dupes} duplicate value(s) in key column '{key_column}'",
            n_dupes,
        )]
    return []


def run_data_quality(
    reference: pd.DataFrame, current: pd.DataFrame, feature_manifest: dict, config: dict
) -> tuple[list[ValidationIssue], dict]:
    features = [f["name"] for f in feature_manifest["features"] if f["model_usage"] == "feature"]
    numeric, categorical = split_feature_types(reference, features)

    issues: list[ValidationIssue] = []
    missing_issues, missing_raw = run_missing_values_check(reference, current, features, config["max_missing_share"])
    issues += missing_issues
    issues += check_schema(current, features)
    issues += check_categorical_new_values(reference, current, categorical)
    issues += check_ranges_vs_reference(reference, current, numeric, config["range_tolerance_std"])
    issues += check_duplicates(current)
    return issues, missing_raw


def data_quality_status(issues: list[ValidationIssue]) -> str:
    return FAIL if any(i.level == ERROR for i in issues) else PASS

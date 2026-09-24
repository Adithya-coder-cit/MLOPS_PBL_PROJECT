"""Load the Stage 3 DVC-versioned processed datasets and verify their
schema before any training happens. Fails loudly — training must never
proceed against a dataset that doesn't match what Stage 3 promised.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd

logger = logging.getLogger("routewise.training.data_loader")

PROCESSED_DIR = Path("data/processed")

TARGET_COLUMN = "disruption_flag"
IDENTIFIER_COLUMNS = {"record_id", "trip_id", "route_id", "stop_id", "zone_id", "service_date", "scheduled_time"}
DIAGNOSTIC_ONLY_COLUMNS = {"delay_minutes", "cancelled", "actual_time"}


class SchemaVerificationError(Exception):
    pass


@dataclass
class ProcessedDatasets:
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame
    feature_manifest: dict
    preprocessor: object
    dataset_metadata: dict


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_processed_datasets(processed_dir: Path = PROCESSED_DIR) -> ProcessedDatasets:
    train = pd.read_parquet(processed_dir / "train.parquet")
    val = pd.read_parquet(processed_dir / "val.parquet")
    test = pd.read_parquet(processed_dir / "test.parquet")
    feature_manifest = _load_json(processed_dir / "feature_manifest.json")
    dataset_metadata = _load_json(processed_dir / "dataset_metadata.json")
    preprocessor = joblib.load(processed_dir / "preprocessor.joblib")

    verify_schema(train, val, test, feature_manifest)
    verify_temporal_ordering(train, val, test)

    return ProcessedDatasets(
        train=train, val=val, test=test,
        feature_manifest=feature_manifest, preprocessor=preprocessor, dataset_metadata=dataset_metadata,
    )


def manifest_feature_columns(feature_manifest: dict) -> list[str]:
    """Columns the manifest marks model_usage == 'feature' — excludes
    identifiers, diagnostics, and the label itself."""
    return [f["name"] for f in feature_manifest["features"] if f["model_usage"] == "feature"]


def verify_schema(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame, feature_manifest: dict) -> None:
    manifest_columns = {f["name"] for f in feature_manifest["features"]}
    for split_name, df in [("train", train), ("val", val), ("test", test)]:
        if set(df.columns) != manifest_columns:
            missing = manifest_columns - set(df.columns)
            extra = set(df.columns) - manifest_columns
            raise SchemaVerificationError(
                f"{split_name}.parquet columns don't match feature_manifest.json "
                f"(missing={missing}, extra={extra})"
            )
        if TARGET_COLUMN not in df.columns:
            raise SchemaVerificationError(f"{split_name}.parquet is missing target column '{TARGET_COLUMN}'")

    feature_cols = manifest_feature_columns(feature_manifest)
    if not feature_cols:
        raise SchemaVerificationError("Feature manifest lists zero model_usage=='feature' columns")
    id_leak = IDENTIFIER_COLUMNS & set(feature_cols)
    if id_leak:
        raise SchemaVerificationError(f"Identifier column(s) leaked into feature set: {id_leak}")
    diagnostic_leak = DIAGNOSTIC_ONLY_COLUMNS & set(feature_cols)
    if diagnostic_leak:
        raise SchemaVerificationError(f"Diagnostic-only (outcome) column(s) leaked into feature set: {diagnostic_leak}")
    if TARGET_COLUMN in feature_cols:
        raise SchemaVerificationError("Target column is listed as a feature — would leak the label into X")

    train_dtypes = train[feature_cols].dtypes
    for split_name, df in [("val", val), ("test", test)]:
        mismatched = [c for c in feature_cols if df[c].dtype != train_dtypes[c]]
        if mismatched:
            raise SchemaVerificationError(f"{split_name} dtype mismatch vs train for columns: {mismatched}")

    logger.info("Schema verification passed: %d feature columns, target='%s'", len(feature_cols), TARGET_COLUMN)


def verify_temporal_ordering(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame) -> None:
    train_max = pd.to_datetime(train["service_date"]).max()
    val_min = pd.to_datetime(val["service_date"]).min()
    val_max = pd.to_datetime(val["service_date"]).max()
    test_min = pd.to_datetime(test["service_date"]).min()
    if not (train_max < val_min):
        raise SchemaVerificationError(f"train/val temporal overlap: train_max={train_max}, val_min={val_min}")
    if not (val_max < test_min):
        raise SchemaVerificationError(f"val/test temporal overlap: val_max={val_max}, test_min={test_min}")
    logger.info("Temporal ordering verified: train<=%s < val<=%s < test>=%s", train_max, val_max, test_min)

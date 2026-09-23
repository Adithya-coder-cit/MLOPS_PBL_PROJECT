"""Stage 3 orchestrator: Raw Data -> Validation -> Preprocessing ->
Feature Engineering -> Temporal Split -> (processed dataset, ready for
Stage 4 model training, which this script does NOT perform).

Run: python -m src.features.build_dataset
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import joblib
import pandas as pd
import yaml

from src.features.historical import join_historical_features
from src.features.manifest import FEATURE_MANIFEST, write_manifest
from src.features.manifest import SCHEMA_VERSION as FEATURE_SCHEMA_VERSION
from src.features.network import join_transfer_dependency
from src.features.split import apply_temporal_split, compute_split_boundaries
from src.features.temporal import add_temporal_features
from src.ingestion.load_raw import RAW_DIR, load_raw_tables
from src.preprocessing.clean import (
    drop_exact_duplicates,
    join_route_metadata,
    join_weather_asof,
    parse_datetimes,
    sort_by_time,
)
from src.preprocessing.pipeline import build_preprocessor
from src.utils.metadata import build_dataset_metadata, write_metadata
from src.validation.report import build_report, raise_if_errors, write_report
from src.validation.schemas import SCHEMA_VERSION as RAW_SCHEMA_VERSION
from src.validation.validators import ERROR, ValidationIssue, run_all_validations

logger = logging.getLogger("routewise.features.build_dataset")

INTERIM_DIR = Path("data/interim")
PROCESSED_DIR = Path("data/processed")
SYNTHETIC_CONFIG_PATH = Path("configs/synthetic_data.yaml")

FINAL_COLUMNS = [f["name"] for f in FEATURE_MANIFEST]


def validate_raw(tables: dict[str, pd.DataFrame], raw_dir: Path) -> None:
    issues = run_all_validations(tables, raw_dir)
    report = build_report(issues)
    write_report(report, INTERIM_DIR / "raw_validation_report.json")
    raise_if_errors(report)
    logger.info("Raw validation PASSED (%d warning(s))", report["summary"]["warnings"])


def validate_features(df: pd.DataFrame) -> None:
    """Post-feature-engineering sanity checks: ranges and null expectations
    on the engineered table (separate report from the raw-table one)."""
    issues: list[ValidationIssue] = []

    for col, (lo, hi) in {
        "precipitation_mm": (0.0, 150.0), "temperature_c": (-30.0, 55.0), "visibility_km": (0.0, 20.0),
        "transfer_dependency": (0, 1000),
    }.items():
        bad = df[col].notna() & ((df[col] < lo) | (df[col] > hi))
        if bad.any():
            issues.append(ValidationIssue(ERROR, "feature_table", "numeric_range",
                                           f"{col} has {int(bad.sum())} value(s) outside [{lo}, {hi}]", int(bad.sum())))

    if not df["disruption_flag"].isin([0, 1]).all():
        issues.append(ValidationIssue(ERROR, "feature_table", "label_validity",
                                       "disruption_flag has values outside {0,1}", 0))

    expected_nan_ok = {"historical_delay_minutes", "rolling_7d_delay_minutes", "historical_reliability",
                        "precipitation_mm", "temperature_c", "visibility_km"}
    for col in FINAL_COLUMNS:
        if col in expected_nan_ok or col not in df.columns:
            continue
        n_null = int(df[col].isna().sum())
        if n_null > 0:
            issues.append(ValidationIssue(ERROR, "feature_table", "unexpected_nulls",
                                           f"{col} has {n_null} unexpected null(s)", n_null))

    report = build_report(issues)
    write_report(report, PROCESSED_DIR / "feature_validation_report.json")
    raise_if_errors(report)
    logger.info("Feature validation PASSED")


def build_feature_table(tables: dict[str, pd.DataFrame], cfg: dict) -> pd.DataFrame:
    historical = parse_datetimes(tables["historical_operational_records"],
                                  ["scheduled_time", "actual_time", "service_date"])
    historical = drop_exact_duplicates(historical, "historical_operational_records")
    historical = sort_by_time(historical, "scheduled_time")

    weather = parse_datetimes(tables["weather_observations"], ["timestamp"])

    df = join_weather_asof(historical, weather, tables["stops"], tolerance_hours=2)  # also adds zone_id
    df = join_route_metadata(df, tables["trips"], tables["routes"])

    df = add_temporal_features(df, cfg)
    df = join_transfer_dependency(df, tables["stop_times"], tables["trips"], cfg["transfer"]["window_minutes"])
    df = join_historical_features(df, rolling_window_days=7)

    missing = [c for c in FINAL_COLUMNS if c not in df.columns]
    if missing:
        raise KeyError(f"Feature table is missing expected columns: {missing}")
    return df[FINAL_COLUMNS]


def main(raw_dir: Path = RAW_DIR, synthetic_config_path: Path = SYNTHETIC_CONFIG_PATH) -> dict:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    logger.info("Loading raw tables from %s", raw_dir)
    tables = load_raw_tables(raw_dir)

    logger.info("Validating raw tables")
    validate_raw(tables, raw_dir)

    logger.info("Building feature table (preprocessing + feature engineering)")
    cfg = yaml.safe_load(synthetic_config_path.read_text(encoding="utf-8"))
    feature_df = build_feature_table(tables, cfg)

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    interim_path = INTERIM_DIR / "joined_training_events.parquet"
    feature_df.to_parquet(interim_path, index=False)
    logger.info("Wrote interim feature table: %s (%d rows)", interim_path, len(feature_df))

    logger.info("Validating engineered features")
    validate_features(feature_df)

    logger.info("Computing chronological split boundaries")
    boundaries = compute_split_boundaries(
        feature_df["service_date"], cfg["calendar"]["train_fraction"], cfg["calendar"]["val_fraction"]
    )
    train_df, val_df, test_df = apply_temporal_split(feature_df, boundaries)

    assert train_df["service_date"].max() < val_df["service_date"].min(), "train/val overlap"
    assert val_df["service_date"].max() < test_df["service_date"].min(), "val/test overlap"
    for split_name, split_df in [("train", train_df), ("val", val_df), ("test", test_df)]:
        if len(split_df) == 0:
            raise ValueError(f"{split_name} split is empty")

    logger.info(
        "Split boundaries: train<=%s, val<=%s, test<=%s | rows: train=%d val=%d test=%d",
        boundaries.train_end, boundaries.val_end, boundaries.max_date, len(train_df), len(val_df), len(test_df),
    )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    train_df.to_parquet(PROCESSED_DIR / "train.parquet", index=False)
    val_df.to_parquet(PROCESSED_DIR / "val.parquet", index=False)
    test_df.to_parquet(PROCESSED_DIR / "test.parquet", index=False)

    logger.info("Fitting preprocessor on TRAIN split only")
    preprocessor = build_preprocessor()
    preprocessor.fit(train_df)
    joblib.dump(preprocessor, PROCESSED_DIR / "preprocessor.joblib")
    # Sanity check only — never persisted into the parquet output.
    preprocessor.transform(val_df)
    preprocessor.transform(test_df)

    write_manifest(PROCESSED_DIR / "feature_manifest.json")

    row_counts = {
        "raw": {name: len(df) for name, df in tables.items()},
        "interim_feature_table": len(feature_df),
        "train": len(train_df), "val": len(val_df), "test": len(test_df),
    }
    split_boundaries_dict = {
        "min_date": str(boundaries.min_date), "train_end": str(boundaries.train_end),
        "val_end": str(boundaries.val_end), "max_date": str(boundaries.max_date),
    }
    metadata = build_dataset_metadata(
        raw_dir, synthetic_config_path, RAW_SCHEMA_VERSION, FEATURE_SCHEMA_VERSION, row_counts, split_boundaries_dict
    )
    write_metadata(metadata, PROCESSED_DIR / "dataset_metadata.json")

    logger.info("Stage 3 complete. Feature count: %d (see feature_manifest.json)", len(FEATURE_MANIFEST))
    return {"row_counts": row_counts, "split_boundaries": split_boundaries_dict, "metadata": metadata}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--synthetic-config", default=str(SYNTHETIC_CONFIG_PATH))
    args = parser.parse_args()
    main(Path(args.raw_dir), Path(args.synthetic_config))

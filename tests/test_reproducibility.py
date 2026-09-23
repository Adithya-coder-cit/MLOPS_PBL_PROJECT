"""Reproducibility tests: the feature pipeline has no randomness — running
it twice on the same input must give identical output, at both the
unit (single transform) and full end-to-end pipeline level.
"""
import shutil
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.features.historical import join_historical_features
from src.features.temporal import add_temporal_features


def _fixture():
    rows = []
    for i in range(10):
        rows.append({
            "route_id": "R1", "service_date": date(2025, 6, 1 + i),
            "delay_minutes": float(i), "disruption_flag": i % 3 == 0,
        })
    return pd.DataFrame(rows)


def test_historical_features_are_deterministic():
    df = _fixture()
    out1 = join_historical_features(df.copy())
    out2 = join_historical_features(df.copy())
    pd.testing.assert_frame_equal(out1, out2)


def test_temporal_features_are_deterministic():
    df = pd.DataFrame({"scheduled_time": pd.date_range("2025-06-01", periods=48, freq="h")})
    cfg = {"day_periods": {"peak_windows": [["07:00", "09:00"], ["17:00", "19:00"]],
                            "night_window": ["22:00", "06:00"]}}
    out1 = add_temporal_features(df.copy(), cfg)
    out2 = add_temporal_features(df.copy(), cfg)
    pd.testing.assert_frame_equal(out1, out2)


RAW_EXISTS = Path("data/raw/gtfs/stops.csv").exists()


@pytest.mark.skipif(not RAW_EXISTS, reason="raw dataset not generated yet")
def test_full_pipeline_is_reproducible(tmp_path):
    """Runs the entire Stage 3 pipeline twice against the same DVC-tracked
    raw data and config, into two separate output directories, and asserts
    the resulting feature tables and split boundaries are byte-identical.
    """
    from src.features import build_dataset

    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"

    original_interim, original_processed = build_dataset.INTERIM_DIR, build_dataset.PROCESSED_DIR
    try:
        build_dataset.INTERIM_DIR, build_dataset.PROCESSED_DIR = out1 / "interim", out1 / "processed"
        result1 = build_dataset.main()

        build_dataset.INTERIM_DIR, build_dataset.PROCESSED_DIR = out2 / "interim", out2 / "processed"
        result2 = build_dataset.main()
    finally:
        build_dataset.INTERIM_DIR, build_dataset.PROCESSED_DIR = original_interim, original_processed

    assert result1["split_boundaries"] == result2["split_boundaries"]
    assert result1["row_counts"] == result2["row_counts"]

    for fname in ["train.parquet", "val.parquet", "test.parquet"]:
        df1 = pd.read_parquet(out1 / "processed" / fname)
        df2 = pd.read_parquet(out2 / "processed" / fname)
        pd.testing.assert_frame_equal(df1, df2)

    shutil.rmtree(out1, ignore_errors=True)
    shutil.rmtree(out2, ignore_errors=True)

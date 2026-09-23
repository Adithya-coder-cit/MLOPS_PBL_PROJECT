"""Tests for chronological (not random) train/val/test splitting."""
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from src.features.split import apply_temporal_split, compute_split_boundaries


def _dates(n_days: int, start: date = date(2025, 1, 1)) -> pd.Series:
    return pd.Series([start + timedelta(days=i) for i in range(n_days)])


def test_boundaries_computed_from_actual_dates_not_hardcoded():
    dates = _dates(100, start=date(2025, 3, 1))
    b = compute_split_boundaries(dates, train_fraction=0.7, val_fraction=0.15)
    assert b.min_date == date(2025, 3, 1)
    assert b.max_date == date(2025, 3, 1) + timedelta(days=99)
    # boundaries must fall inside the actual observed range
    assert b.min_date <= b.train_end < b.val_end < b.max_date


def test_boundaries_respect_fractions_within_one_day_tolerance():
    dates = _dates(100)
    b = compute_split_boundaries(dates, train_fraction=0.7, val_fraction=0.15)
    train_days = (b.train_end - b.min_date).days + 1
    assert abs(train_days - 70) <= 1


def test_split_produces_no_temporal_overlap():
    dates = _dates(120)
    df = pd.DataFrame({"service_date": dates})
    b = compute_split_boundaries(dates, 0.7, 0.15)
    train, val, test = apply_temporal_split(df, b)

    assert pd.to_datetime(train["service_date"]).max() < pd.to_datetime(val["service_date"]).min()
    assert pd.to_datetime(val["service_date"]).max() < pd.to_datetime(test["service_date"]).min()


def test_split_is_chronological_and_covers_all_rows():
    dates = _dates(120)
    df = pd.DataFrame({"service_date": dates, "value": range(120)})
    b = compute_split_boundaries(dates, 0.7, 0.15)
    train, val, test = apply_temporal_split(df, b)
    assert len(train) + len(val) + len(test) == len(df)
    assert len(train) > 0 and len(val) > 0 and len(test) > 0


def test_split_raises_when_no_room_for_test_period():
    dates = _dates(5)
    with pytest.raises(ValueError):
        compute_split_boundaries(dates, train_fraction=0.9, val_fraction=0.2)


PROCESSED_EXISTS = Path("data/processed/train.parquet").exists()


@pytest.mark.skipif(not PROCESSED_EXISTS, reason="processed dataset not generated yet")
def test_real_processed_splits_have_no_overlap():
    train = pd.read_parquet("data/processed/train.parquet", columns=["service_date"])
    val = pd.read_parquet("data/processed/val.parquet", columns=["service_date"])
    test = pd.read_parquet("data/processed/test.parquet", columns=["service_date"])
    assert pd.to_datetime(train["service_date"]).max() < pd.to_datetime(val["service_date"]).min()
    assert pd.to_datetime(val["service_date"]).max() < pd.to_datetime(test["service_date"]).min()

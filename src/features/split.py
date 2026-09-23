"""Chronological (not random) train/validation/test split, per the data
contract's §9 rationale: this is temporally autocorrelated data (rolling
features, weather persistence), so a random row-level split would leak
future dates into "training" rows once shuffled. Boundaries are computed
from the actual observed date range, not hardcoded row positions or dates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd


@dataclass
class SplitBoundaries:
    min_date: date
    train_end: date  # inclusive
    val_end: date  # inclusive
    max_date: date  # inclusive, end of test


def compute_split_boundaries(dates: pd.Series, train_fraction: float, val_fraction: float) -> SplitBoundaries:
    unique_dates = sorted(pd.to_datetime(dates).dt.date.unique())
    if not unique_dates:
        raise ValueError("No dates to split on")

    min_date, max_date = unique_dates[0], unique_dates[-1]
    n_days = (max_date - min_date).days + 1

    train_days = max(1, int(n_days * train_fraction))
    val_days = max(1, int(n_days * val_fraction))
    # test gets whatever remains, guaranteeing no overlap and full coverage

    train_end = min_date + timedelta(days=train_days - 1)
    val_end = train_end + timedelta(days=val_days)

    if val_end >= max_date:
        raise ValueError(
            f"train_fraction + val_fraction leave no room for a test period "
            f"(train_end={train_end}, val_end={val_end}, max_date={max_date})"
        )

    return SplitBoundaries(min_date=min_date, train_end=train_end, val_end=val_end, max_date=max_date)


def apply_temporal_split(
    df: pd.DataFrame, boundaries: SplitBoundaries, date_column: str = "service_date"
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = pd.to_datetime(df[date_column]).dt.date
    train = df[dates <= boundaries.train_end].reset_index(drop=True)
    val = df[(dates > boundaries.train_end) & (dates <= boundaries.val_end)].reset_index(drop=True)
    test = df[dates > boundaries.val_end].reset_index(drop=True)
    return train, val, test

"""Stage 11C Part J: the real-data temporal split. Computed from the
ACTUAL real coverage period observed in the ingested data -- never the
synthetic generator's date boundaries (which describe a different,
fictional calendar entirely).
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def compute_real_split_boundaries(
    service_dates: pd.Series, train_fraction: float = 0.70, val_fraction: float = 0.15,
) -> dict:
    unique_dates = sorted(pd.Series(service_dates).dropna().unique())
    if not unique_dates:
        raise ValueError("No service_date values to split on")

    min_date, max_date = unique_dates[0], unique_dates[-1]
    n_days = (max_date - min_date).days + 1
    if n_days < 3:
        raise ValueError(f"Only {n_days} distinct day(s) of real coverage -- too short for a "
                          f"chronological train/val/test split")

    train_days = max(1, int(n_days * train_fraction))
    val_days = max(1, int(n_days * val_fraction))
    train_end = min_date + timedelta(days=train_days - 1)
    val_end = train_end + timedelta(days=val_days)

    if val_end >= max_date:
        # Not enough real days for the requested fractions -- degrade to
        # a minimal-but-valid 1-day val/test rather than raising, since
        # the real coverage window is often short in this stage.
        val_end = max(train_end + timedelta(days=1), max_date - timedelta(days=1))
        train_end = min(train_end, val_end - timedelta(days=1))

    return {
        "min_date": str(min_date), "train_end": str(train_end), "val_end": str(val_end), "max_date": str(max_date),
        "n_days_total": n_days,
        "n_days_train": (train_end - min_date).days + 1,
        "n_days_val": (val_end - train_end).days,
        "n_days_test": (max_date - val_end).days,
    }


def apply_real_split(df: pd.DataFrame, boundaries: dict, date_column: str = "service_date") -> dict:
    dates = pd.to_datetime(df[date_column]).dt.date
    train_end = date.fromisoformat(boundaries["train_end"])
    val_end = date.fromisoformat(boundaries["val_end"])

    train = df[dates <= train_end]
    val = df[(dates > train_end) & (dates <= val_end)]
    test = df[dates > val_end]
    return {"train": train, "val": val, "test": test}

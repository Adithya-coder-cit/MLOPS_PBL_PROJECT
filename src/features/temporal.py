"""Temporal features — all derived purely from scheduled_time (the static
schedule), never from actual_time, so they carry no outcome information.
"""
from __future__ import annotations

import pandas as pd

from src.utils.time_buckets import classify_day_period
from src.utils.time_buckets import time_of_day_bucket as _time_of_day_bucket


def add_temporal_features(df: pd.DataFrame, cfg: dict, time_column: str = "scheduled_time") -> pd.DataFrame:
    df = df.copy()
    ts = df[time_column]
    df["hour"] = ts.dt.hour
    df["day_of_week"] = ts.dt.dayofweek  # 0=Monday
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["time_of_day_bucket"] = df["hour"].apply(_time_of_day_bucket)

    minute_of_day = ts.dt.hour * 60 + ts.dt.minute
    dp = cfg["day_periods"]
    df["day_period"] = minute_of_day.apply(
        lambda m: classify_day_period(int(m), dp["peak_windows"], dp["night_window"])
    )
    return df

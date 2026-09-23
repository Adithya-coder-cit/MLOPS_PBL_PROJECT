"""Leakage-safe historical/rolling features.

Design: aggregate to one row per (route_id, service_date), then use
`shift(1)` before any expanding/rolling window so a given day's feature
value is computed strictly from days *before* it — never the day itself.
This mirrors a realistic daily-batch production setup (today's features
only ever see "yesterday and earlier"), and makes the leakage guarantee
easy to test in isolation from the row-level join.

historical_delay_minutes / rolling_7d_delay_minutes / historical_reliability
are NaN for a route's first observed service_date (no prior history exists)
— this is left as NaN here, not silently imputed; see
src/preprocessing/pipeline.py for the train-fit imputer that handles it.
"""
from __future__ import annotations

import pandas as pd


def compute_daily_route_stats(historical_df: pd.DataFrame) -> pd.DataFrame:
    daily = (
        historical_df.groupby(["route_id", "service_date"])
        .agg(mean_delay=("delay_minutes", "mean"), disruption_rate=("disruption_flag", "mean"))
        .reset_index()
        .sort_values(["route_id", "service_date"])
    )
    return daily


def add_backward_looking_route_features(daily: pd.DataFrame, rolling_window_days: int = 7) -> pd.DataFrame:
    daily = daily.copy()
    grouped_delay = daily.groupby("route_id")["mean_delay"]
    grouped_disruption = daily.groupby("route_id")["disruption_rate"]

    daily["historical_delay_minutes"] = grouped_delay.transform(lambda s: s.shift(1).expanding().mean())
    daily["rolling_7d_delay_minutes"] = grouped_delay.transform(
        lambda s: s.shift(1).rolling(window=rolling_window_days, min_periods=1).mean()
    )
    daily["historical_reliability"] = grouped_disruption.transform(
        lambda s: 1 - s.shift(1).expanding().mean()
    )
    return daily[["route_id", "service_date", "historical_delay_minutes",
                   "rolling_7d_delay_minutes", "historical_reliability"]]


def join_historical_features(row_level_df: pd.DataFrame, rolling_window_days: int = 7) -> pd.DataFrame:
    daily = compute_daily_route_stats(row_level_df)
    daily_features = add_backward_looking_route_features(daily, rolling_window_days)
    return row_level_df.merge(daily_features, on=["route_id", "service_date"], how="left")

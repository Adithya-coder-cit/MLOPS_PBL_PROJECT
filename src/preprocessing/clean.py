"""Modular preprocessing steps applied to the validated raw tables before
feature engineering. Each function does exactly one documented
transformation and returns a new DataFrame — no step silently repairs data
that validation would have flagged as an error; these are legitimate,
expected transformations (parsing, sorting, joining), not data fixes.
"""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger("routewise.preprocessing")


def parse_datetimes(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Parse the given columns to pandas datetime64. Unparseable values
    become NaT (already caught earlier by validation's timestamp check —
    this step assumes validation has already passed).
    """
    df = df.copy()
    for col in columns:
        df[col] = pd.to_datetime(df[col])
    return df


def sort_by_time(df: pd.DataFrame, time_column: str, secondary: list[str] | None = None) -> pd.DataFrame:
    """Sort ascending by time (and optional secondary keys), reset index.
    Required before any asof-join or rolling/expanding window computation.
    """
    cols = [time_column] + (secondary or [])
    return df.sort_values(cols).reset_index(drop=True)


def drop_exact_duplicates(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    before = len(df)
    df = df.drop_duplicates()
    dropped = before - len(df)
    if dropped:
        logger.info("Dropped %d exact-duplicate row(s) from %s", dropped, table_name)
    return df.reset_index(drop=True)


def join_weather_asof(
    historical_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    stops_df: pd.DataFrame,
    tolerance_hours: int = 2,
) -> pd.DataFrame:
    """Attach the most recent weather observation at or before each
    stop-event's scheduled_time, within the same zone.

    Anti-leakage: direction="backward" guarantees only observations with
    timestamp <= scheduled_time are eligible — never a future reading.
    A bounded tolerance avoids silently pairing a stop-event with a
    weather reading from days earlier if none is close by.
    """
    left = historical_df.merge(stops_df[["stop_id", "zone_id"]], on="stop_id", how="left")
    left = left.sort_values("scheduled_time").reset_index(drop=True)

    right = weather_df.sort_values("timestamp").reset_index(drop=True)

    merged = pd.merge_asof(
        left, right[["zone_id", "timestamp", "precipitation_mm", "temperature_c", "visibility_km"]],
        left_on="scheduled_time", right_on="timestamp",
        by="zone_id", direction="backward",
        tolerance=pd.Timedelta(hours=tolerance_hours),
    )
    n_missing = int(merged["precipitation_mm"].isna().sum())
    if n_missing:
        logger.info(
            "%d row(s) have no weather observation within %dh before scheduled_time "
            "(edge-of-calendar effect) — left as NaN, to be imputed at the preprocessing-pipeline "
            "stage using train-only statistics, not silently filled here.",
            n_missing, tolerance_hours,
        )
    return merged.drop(columns=["timestamp"])


def join_route_metadata(historical_df: pd.DataFrame, trips_df: pd.DataFrame, routes_df: pd.DataFrame) -> pd.DataFrame:
    """Attach route_id, service_id, direction_id (from trips) and
    route_type_gtfs (from routes) to each stop-event. transport_mode is
    already present in historical_operational_records (denormalized at
    generation time, mirroring how a real GTFS-RT feed usually carries it).
    """
    merged = historical_df.merge(
        trips_df[["trip_id", "route_id", "service_id", "direction_id"]], on="trip_id", how="left"
    )
    merged = merged.merge(routes_df[["route_id", "route_type_gtfs"]], on="route_id", how="left")
    return merged

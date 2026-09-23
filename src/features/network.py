"""Network/transport features. transfer_dependency is recomputed here from
the static schedule (stop_times + trips), never read from a raw column —
the raw GTFS-like tables deliberately don't persist it, since it's a
derived feature by design (see data contract §3D / §6).
"""
from __future__ import annotations

import pandas as pd

from src.utils.network_topology import compute_transfer_dependency
from src.utils.time_buckets import hhmm_to_minutes


def compute_transfer_dependency_feature(
    stop_times_df: pd.DataFrame, trips_df: pd.DataFrame, window_minutes: int
) -> pd.DataFrame:
    """Returns a (trip_id, stop_id, transfer_dependency) table, one row per
    scheduled stop-time — ready to join onto the row-level historical table.
    """
    enriched = stop_times_df.merge(trips_df[["trip_id", "route_id", "service_id"]], on="trip_id", how="left")
    enriched["_arrival_minute"] = enriched["scheduled_arrival"].apply(hhmm_to_minutes)
    enriched["transfer_dependency"] = compute_transfer_dependency(enriched, window_minutes)
    return enriched[["trip_id", "stop_id", "transfer_dependency"]]


def join_transfer_dependency(row_level_df: pd.DataFrame, stop_times_df: pd.DataFrame,
                              trips_df: pd.DataFrame, window_minutes: int) -> pd.DataFrame:
    transfer_df = compute_transfer_dependency_feature(stop_times_df, trips_df, window_minutes)
    return row_level_df.merge(transfer_df, on=["trip_id", "stop_id"], how="left")

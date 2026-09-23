"""Transfer-dependency computation shared by data generation (to produce a
realistic delay correlation) and feature engineering (to derive the same
feature from the static schedule at inference/training time).

Structural — computed purely from the scheduled timetable (stop_id,
service_id/day-pattern, scheduled arrival minute, route_id). Never touches
realized/actual times, so it carries no label information.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_transfer_dependency(stop_times_df: pd.DataFrame, window_minutes: int) -> pd.Series:
    """stop_times_df must have columns: stop_id, service_id, route_id, _arrival_minute.

    Returns a Series aligned to stop_times_df.index: for each stop-time row,
    the count of *other-route* stop-times at the same stop and service_id
    scheduled within `window_minutes` of it.
    """
    counts = np.zeros(len(stop_times_df), dtype=int)
    for (_stop_id, _service_id), group in stop_times_df.groupby(["stop_id", "service_id"]):
        minutes = group["_arrival_minute"].to_numpy()
        routes = group["route_id"].to_numpy()
        for i in range(len(group)):
            close = np.abs(minutes - minutes[i]) <= window_minutes
            other_route = routes != routes[i]
            counts[group.index[i]] = int(np.sum(close & other_route))
    return pd.Series(counts, index=stop_times_df.index, name="transfer_dependency")

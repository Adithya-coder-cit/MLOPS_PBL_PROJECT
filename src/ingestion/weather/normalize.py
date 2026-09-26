"""Stage 11B §13/§14: normalize raw weather observations into the
canonical weather contract, and perform the deterministic, leakage-safe
spatial/temporal join against stops -- same backward-asof-join
discipline as the existing synthetic path
(src/preprocessing/clean.py::join_weather_asof), never a future
observation.
"""
from __future__ import annotations

import hashlib

import pandas as pd


def normalize_nws_observations(raw_df: pd.DataFrame, weather_zone_id: str) -> pd.DataFrame:
    """raw_df: the output of src.ingestion.weather.nws.observations_to_dataframe.
    Any field the source itself reported as null stays null here -- never
    fabricated (Stage 11B §13)."""
    out = raw_df.copy()
    out["weather_zone_id"] = weather_zone_id
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    out["observation_id"] = [
        hashlib.sha256(f"{weather_zone_id}|{ts.isoformat()}".encode()).hexdigest()[:16] for ts in out["timestamp"]
    ]
    return out[["observation_id", "weather_zone_id", "timestamp", "precipitation_mm", "temperature_c",
                "visibility_km"]]


def assign_weather_zone(stops: pd.DataFrame, station_id: str) -> pd.DataFrame:
    """Stage 11B §14: deterministic station assignment. This stage
    verified and uses exactly ONE real station (KBOS, Boston Logan --
    see configs/real_data.yaml weather.station), documented as covering
    the whole MBTA network within the configured max_distance_km
    tolerance -- every stop is assigned the same weather_zone_id. A
    multi-station nearest-station assignment is a documented extension
    point (Stage 11B report Limitations), not implemented here since
    only one station was verified.
    """
    out = stops.copy()
    out["weather_zone_id"] = station_id
    return out


def join_weather_asof(
    operational_events: pd.DataFrame, weather: pd.DataFrame, stops_with_zone: pd.DataFrame,
    tolerance_hours: int,
) -> pd.DataFrame:
    """Backward-only asof join, bounded tolerance -- identical leakage
    discipline to src/preprocessing/clean.py::join_weather_asof. Requires
    operational_events.scheduled_time to be timezone-aware (as produced
    by src.ingestion.historical.normalize) and weather.timestamp to be
    timezone-aware (as produced by normalize_nws_observations above).
    """
    left = operational_events.merge(stops_with_zone[["stop_id", "weather_zone_id"]], on="stop_id", how="left")
    left = left.dropna(subset=["scheduled_time"]).copy()
    # merge_asof requires identical tz representation on both join keys --
    # convert to UTC for the join only; this changes no instant, only the
    # displayed offset, so the asof comparison (and the leakage guarantee:
    # direction="backward" still means "never a later real instant") is
    # unaffected.
    left["_join_time"] = pd.to_datetime(left["scheduled_time"], utc=True)
    left = left.sort_values("_join_time").reset_index(drop=True)

    right = weather.sort_values("timestamp").reset_index(drop=True)

    merged = pd.merge_asof(
        left, right[["weather_zone_id", "timestamp", "precipitation_mm", "temperature_c", "visibility_km"]],
        left_on="_join_time", right_on="timestamp",
        by="weather_zone_id", direction="backward",
        tolerance=pd.Timedelta(hours=tolerance_hours),
    )
    return merged.drop(columns=["timestamp", "_join_time"])

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
    out["source"] = "NWS"
    return out[["observation_id", "weather_zone_id", "timestamp", "precipitation_mm", "temperature_c",
                "visibility_km", "source"]]


def normalize_ghcnh_observations(raw_df: pd.DataFrame, weather_zone_id: str) -> pd.DataFrame:
    """raw_df: the output of src.ingestion.weather.ghcnh.load_station_year(s)
    -- raw GHCNh PSV columns (STATION, DATE, LATITUDE, LONGITUDE,
    temperature, precipitation, wind_speed, visibility,
    station_level_pressure, sea_level_pressure). Any field GHCNh itself
    left blank is preserved as NaN, never fabricated.

    Unit/timezone notes verified against real downloaded data this stage
    (not assumed from documentation alone):
    - `DATE` has no UTC offset in the raw file; treated as UTC, consistent
      with ISD/METAR global-hourly-synthesis convention (GHCNh is built
      from ISD) and with how this project's NWS timestamps are already
      handled -- both weather sources end up UTC-aware in the canonical
      table.
    - `temperature` (Celsius), `precipitation` (mm), `wind_speed` (m/s),
      and `*_pressure` (hPa) are already decimal values in these units --
      no scaling applied.
    - `visibility`: verified against real values (e.g. 16.093, 4.828) that
      convert exactly to 10.0 and 3.0 US statute miles respectively --
      GHCNh's own documentation page states meters, but the actual bulk
      PSV data is in KILOMETERS for this station; the raw value is used
      directly as visibility_km, not divided by 1000.
    - `pressure_hpa` prefers sea_level_pressure (comparable across
      elevations, matches typical model-feature convention) and falls
      back to station_level_pressure only when sea-level is null.
    """
    out = raw_df.copy()
    out["weather_zone_id"] = weather_zone_id
    out["timestamp"] = pd.to_datetime(out["DATE"], utc=True)
    out["observation_id"] = [
        hashlib.sha256(f"{weather_zone_id}|ghcnh|{ts.isoformat()}".encode()).hexdigest()[:16]
        for ts in out["timestamp"]
    ]
    out["precipitation_mm"] = out.get("precipitation")
    out["temperature_c"] = out.get("temperature")
    out["visibility_km"] = out.get("visibility")
    out["wind_speed_ms"] = out.get("wind_speed")
    out["pressure_hpa"] = out.get("sea_level_pressure")
    if "station_level_pressure" in out.columns:
        out["pressure_hpa"] = out["pressure_hpa"].fillna(out["station_level_pressure"])
    out["station_lat"] = out.get("LATITUDE")
    out["station_lon"] = out.get("LONGITUDE")
    out["source"] = "NOAA GHCNh"
    return out[["observation_id", "weather_zone_id", "timestamp", "precipitation_mm", "temperature_c",
                "visibility_km", "wind_speed_ms", "pressure_hpa", "station_lat", "station_lon", "source"]]


WEATHER_FEATURE_COLUMNS = ["precipitation_mm", "temperature_c", "visibility_km", "wind_speed_ms", "pressure_hpa"]


def combine_weather_sources(sources: list[pd.DataFrame], source_priority: list[str]) -> pd.DataFrame:
    """Stage 11D: stacks multiple canonical weather tables (e.g. NOAA
    GHCNh + NWS) into one, resolving exact (weather_zone_id, timestamp)
    collisions by `source_priority` (earlier entries win) rather than
    arbitrarily -- never averages or otherwise fabricates a blended value
    for a colliding instant. Missing columns from a source that doesn't
    populate them (e.g. NWS has no wind_speed_ms) become NaN via concat,
    exactly as for any other unavailable measurement.
    """
    non_empty = [df for df in sources if df is not None and not df.empty]
    if not non_empty:
        return pd.DataFrame(columns=["observation_id", "weather_zone_id", "timestamp", "source"]
                             + WEATHER_FEATURE_COLUMNS)
    combined = pd.concat(non_empty, ignore_index=True, sort=False)
    priority = {name: i for i, name in enumerate(source_priority)}
    combined["_priority"] = combined["source"].map(priority).fillna(len(priority))
    combined = (
        combined.sort_values(["weather_zone_id", "timestamp", "_priority"])
        .drop_duplicates(["weather_zone_id", "timestamp"], keep="first")
        .drop(columns="_priority")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    return combined


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
    # Dynamically select whichever canonical weather feature columns this
    # `weather` frame actually has -- keeps this join backward-compatible
    # with NWS-only callers/tests (3 columns) while also carrying the
    # Stage 11D fields (wind_speed_ms, pressure_hpa) when a GHCNh-combined
    # frame supplies them, without ever fabricating a column that isn't there.
    feature_cols = [c for c in WEATHER_FEATURE_COLUMNS if c in right.columns]

    merged = pd.merge_asof(
        left, right[["weather_zone_id", "timestamp"] + feature_cols],
        left_on="_join_time", right_on="timestamp",
        by="weather_zone_id", direction="backward",
        tolerance=pd.Timedelta(hours=tolerance_hours),
    )
    return merged.drop(columns=["timestamp", "_join_time"])

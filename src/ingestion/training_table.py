"""Stage 11C Part I: the final real-world training table contract.

One row per scheduled stop-event (same grain as the existing synthetic
feature table). Every column's meaning is documented below; the target
(disruption_flag) is populated ONLY when label_available is true AND the
label policy is active -- never fabricated for label_available=false
rows, and never silently defaulted to 0.
"""
from __future__ import annotations

import pandas as pd

# Column documentation -- kept alongside the builder so the two never
# drift apart (mirrors src/features/manifest.py's own convention).
TRAINING_TABLE_SCHEMA = [
    {"name": "record_id", "role": "entity_identifier",
     "description": "stable hash of (trip_id, stop_id, service_date)"},
    {"name": "trip_id", "role": "entity_identifier", "description": "GTFS trip_id"},
    {"name": "route_id", "role": "entity_identifier", "description": "GTFS route_id"},
    {"name": "stop_id", "role": "entity_identifier", "description": "GTFS stop_id"},
    {"name": "service_date", "role": "entity_identifier", "description": "calendar service date"},
    {"name": "transport_mode", "role": "entity_identifier", "description": "RouteWise mode (Stage 11B mode mapping)"},
    {"name": "scheduled_time", "role": "prediction_timestamp",
     "description": "the instant this row's prediction is made FOR -- the scheduled stop-event itself "
                     "(Stage 11C Part B: label horizon = this single event, not a future window)"},
    {"name": "hour", "role": "feature", "description": "derived from scheduled_time"},
    {"name": "day_of_week", "role": "feature", "description": "derived from scheduled_time"},
    {"name": "day_period", "role": "feature", "description": "derived from scheduled_time, config-driven"},
    {"name": "time_of_day_bucket", "role": "feature", "description": "derived from scheduled_time"},
    {"name": "transfer_dependency", "role": "feature", "description": "structural, from stop_times+trips"},
    {"name": "precipitation_mm", "role": "feature", "description": "weather, backward asof-joined to scheduled_time"},
    {"name": "temperature_c", "role": "feature", "description": "weather, backward asof-joined to scheduled_time"},
    {"name": "visibility_km", "role": "feature", "description": "weather, backward asof-joined to scheduled_time"},
    {"name": "wind_speed_ms", "role": "feature",
     "description": "Stage 11D -- weather, backward asof-joined; only populated where a NOAA GHCNh "
                     "observation joined (NWS does not report it)"},
    {"name": "pressure_hpa", "role": "feature",
     "description": "Stage 11D -- weather, backward asof-joined; only populated where a NOAA GHCNh "
                     "observation joined (NWS does not report it)"},
    {"name": "historical_delay_seconds", "role": "feature",
     "description": "route-level expanding mean delay, STRICTLY prior service_dates only (shift(1))"},
    {"name": "rolling_7d_delay_seconds", "role": "feature",
     "description": "route-level 7-day rolling mean delay, STRICTLY prior service_dates only"},
    {"name": "historical_reliability", "role": "feature",
     "description": "1 - route-level expanding disruption rate, STRICTLY prior service_dates only; "
                     "NaN if the label policy is not active (no threshold to compute a disruption rate with)"},
    {"name": "delay_seconds", "role": "diagnostic_only",
     "description": "realized outcome -- NEVER a model input feature, label-derivative"},
    {"name": "label_available", "role": "metadata",
     "description": "Stage 11B/11C policy flag -- true only for modes with a verified real label source"},
    {"name": "disruption_flag", "role": "label",
     "description": "the training target -- populated ONLY when label_available AND the label policy "
                     "is active; NULL otherwise, NEVER 0"},
    {"name": "source_provider", "role": "provenance", "description": "e.g. 'MBTA LAMP', 'MBTA GTFS'"},
    {"name": "source_dataset_type", "role": "provenance", "description": "'REAL', never silently 'DEVELOPMENT/DEMO'"},
]

MODEL_FEATURE_COLUMNS = [f["name"] for f in TRAINING_TABLE_SCHEMA if f["role"] == "feature"]


def build_training_table(operational_events_with_features: pd.DataFrame) -> pd.DataFrame:
    """Assembles the final table from an operational_events frame that
    has already been through historical-feature joining
    (src.ingestion.historical_features) and weather joining
    (src.ingestion.weather.normalize) -- this function only selects,
    renames, and adds provenance/temporal columns, it computes nothing
    new.
    """
    # No copy needed: the caller (join_historical_features) already
    # returns a fresh object via .merge(), and never reuses its own
    # return value afterward -- mutating it here in place is safe and
    # avoids duplicating the widest table in the pipeline.
    df = operational_events_with_features

    scheduled = pd.to_datetime(df["scheduled_time"], utc=True, errors="coerce")
    df["hour"] = scheduled.dt.hour
    df["day_of_week"] = scheduled.dt.dayofweek

    df["source_provider"] = "MBTA LAMP"
    df["source_dataset_type"] = "REAL"

    for col in ["day_period", "time_of_day_bucket", "transfer_dependency", "precipitation_mm", "temperature_c",
                "visibility_km", "wind_speed_ms", "pressure_hpa",
                "historical_delay_seconds", "rolling_7d_delay_seconds", "historical_reliability"]:
        if col not in df.columns:
            df[col] = pd.NA

    keep = [f["name"] for f in TRAINING_TABLE_SCHEMA if f["name"] in df.columns or f["role"] != "entity_identifier"]
    keep = [c for c in [f["name"] for f in TRAINING_TABLE_SCHEMA] if c in df.columns]
    return df[keep]


def trainable_subset(training_table: pd.DataFrame) -> pd.DataFrame:
    """Rows where the target is genuinely observable -- Stage 11C Part I:
    'The target must be generated only when a valid real label exists.'
    """
    return training_table[training_table["label_available"] & training_table["disruption_flag"].notna()]

"""Machine-readable feature manifest: describes every column that reaches
data/processed/{train,val,test}.parquet, so the training and monitoring
stages (later) have a single source of truth for what each column is,
where it came from, and whether it's safe to feed to a model.
"""
from __future__ import annotations

import json
from pathlib import Path

# Each entry: name, dtype, source, description, unit, transformation,
# availability_time, leakage_risk, model_usage.
FEATURE_MANIFEST: list[dict] = [
    # --- identifiers / keys (never fed to the model) ---
    {"name": "record_id", "dtype": "string", "source": "historical_operational_records (raw)",
     "description": "Unique id of the historical stop-event record.", "unit": None,
     "transformation": "passthrough", "availability_time": "always", "leakage_risk": "none",
     "model_usage": "identifier"},
    {"name": "trip_id", "dtype": "string", "source": "GTFS trips.txt", "description": "Scheduled trip identifier.",
     "unit": None, "transformation": "passthrough", "availability_time": "always (static schedule)",
     "leakage_risk": "none", "model_usage": "identifier"},
    {"name": "route_id", "dtype": "string", "source": "GTFS routes.txt", "description": "Route identifier.",
     "unit": None, "transformation": "passthrough", "availability_time": "always (static schedule)",
     "leakage_risk": "none", "model_usage": "identifier"},
    {"name": "stop_id", "dtype": "string", "source": "GTFS stops.txt", "description": "Stop identifier.",
     "unit": None, "transformation": "passthrough", "availability_time": "always (static schedule)",
     "leakage_risk": "none", "model_usage": "identifier"},
    {"name": "zone_id", "dtype": "string", "source": "GTFS stops.txt", "description": "Weather-grid zone of the stop.",
     "unit": None, "transformation": "passthrough", "availability_time": "always (static schedule)",
     "leakage_risk": "none", "model_usage": "identifier"},
    {"name": "service_date", "dtype": "date", "source": "historical_operational_records (raw)",
     "description": "Calendar date the trip actually ran.", "unit": "date",
     "transformation": "passthrough", "availability_time": "always", "leakage_risk": "none",
     "model_usage": "identifier / split key"},
    {"name": "scheduled_time", "dtype": "datetime", "source": "GTFS stop_times.txt + service_date",
     "description": "Prediction reference time T — the scheduled arrival being predicted for.", "unit": "datetime",
     "transformation": "passthrough", "availability_time": "always (static schedule)", "leakage_risk": "none",
     "model_usage": "identifier / temporal reference"},

    # --- weather features ---
    {"name": "precipitation_mm", "dtype": "float", "source": "weather_observations (Weather API in production)",
     "description": "Precipitation at the stop's zone, nearest reading at or before scheduled_time.",
     "unit": "mm", "transformation": "asof-join backward, tolerance 2h; median-impute + scale at training time",
     "availability_time": "at or before T (backward asof join)",
     "leakage_risk": "low — demo uses observed weather; production should prefer a forecast issued before T",
     "model_usage": "feature"},
    {"name": "temperature_c", "dtype": "float", "source": "weather_observations (Weather API in production)",
     "description": "Temperature at the stop's zone, nearest reading at or before scheduled_time.",
     "unit": "°C", "transformation": "asof-join backward, tolerance 2h; median-impute + scale at training time",
     "availability_time": "at or before T", "leakage_risk": "low (see precipitation_mm)", "model_usage": "feature"},
    {"name": "visibility_km", "dtype": "float", "source": "weather_observations (Weather API in production)",
     "description": "Visibility at the stop's zone, nearest reading at or before scheduled_time.",
     "unit": "km", "transformation": "asof-join backward, tolerance 2h; median-impute + scale at training time",
     "availability_time": "at or before T", "leakage_risk": "low (see precipitation_mm)", "model_usage": "feature"},

    # --- temporal features ---
    {"name": "hour", "dtype": "int", "source": "derived from scheduled_time", "description": "Hour of day (0-23).",
     "unit": "hour", "transformation": "scheduled_time.hour; scaled at training time",
     "availability_time": "at T (from static schedule)", "leakage_risk": "none", "model_usage": "feature"},
    {"name": "day_of_week", "dtype": "int", "source": "derived from scheduled_time",
     "description": "Day of week, 0=Monday.", "unit": None,
     "transformation": "scheduled_time.dayofweek; scaled at training time",
     "availability_time": "at T (from static schedule)", "leakage_risk": "none", "model_usage": "feature"},
    {"name": "is_weekend", "dtype": "int (0/1)", "source": "derived from scheduled_time",
     "description": "1 if service_date is Saturday/Sunday.", "unit": None, "transformation": "day_of_week >= 5",
     "availability_time": "at T (from static schedule)", "leakage_risk": "none", "model_usage": "feature"},
    {"name": "time_of_day_bucket", "dtype": "category", "source": "derived from scheduled_time",
     "description": "Fixed 4-hour bucket of the hour, e.g. '08-12'.", "unit": None,
     "transformation": "hour // 4; one-hot encoded at training time",
     "availability_time": "at T (from static schedule)", "leakage_risk": "none", "model_usage": "feature"},
    {"name": "day_period", "dtype": "category", "source": "derived from scheduled_time + configs/synthetic_data.yaml",
     "description": "peak / off_peak / night, per the configured peak windows.", "unit": None,
     "transformation": "rule-based on minute-of-day; one-hot encoded at training time",
     "availability_time": "at T (from static schedule)", "leakage_risk": "none", "model_usage": "feature"},

    # --- network / transport features ---
    {"name": "transport_mode", "dtype": "category", "source": "GTFS routes.txt",
     "description": "bus/tram/metro/rail/ferry.",
     "unit": None, "transformation": "passthrough; one-hot encoded at training time",
     "availability_time": "always (static schedule)", "leakage_risk": "none", "model_usage": "feature"},
    {"name": "transfer_dependency", "dtype": "int", "source": "derived from GTFS stop_times.txt (structural)",
     "description": "Count of other-route stop-times at this stop within the configured transfer window.",
     "unit": "count", "transformation": "recomputed from static schedule; scaled at training time",
     "availability_time": "always (static schedule)", "leakage_risk": "none — never touches realized times",
     "model_usage": "feature"},

    # --- historical / rolling features (leakage-critical) ---
    {"name": "historical_delay_minutes", "dtype": "float", "source": "derived from historical_operational_records",
     "description": "Expanding mean delay for this route over all service_dates strictly before this row's date.",
     "unit": "minutes", "transformation": "groupby(route_id).shift(1).expanding().mean(); "
     "median-impute (train-fit) + scale at training time",
     "availability_time": "at T (uses only data before service_date)",
     "leakage_risk": "none by construction — shift(1) excludes the current day; NaN on a route's first day",
     "model_usage": "feature"},
    {"name": "rolling_7d_delay_minutes", "dtype": "float", "source": "derived from historical_operational_records",
     "description": "Trailing 7-day mean delay for this route, strictly before this row's date.",
     "unit": "minutes", "transformation": "groupby(route_id).shift(1).rolling(7, min_periods=1).mean(); "
     "median-impute (train-fit) + scale at training time",
     "availability_time": "at T (uses only data before service_date)",
     "leakage_risk": "none by construction — shift(1) excludes the current day; NaN on a route's first day",
     "model_usage": "feature"},
    {"name": "historical_reliability", "dtype": "float", "source": "derived from historical_operational_records",
     "description": "1 minus the expanding disruption rate for this route, strictly before this row's date.",
     "unit": "ratio [0,1]", "transformation": "1 - groupby(route_id).shift(1).expanding().mean(disruption_flag); "
     "median-impute (train-fit) + scale at training time",
     "availability_time": "at T (uses only data before service_date)",
     "leakage_risk": "none by construction — shift(1) excludes the current day; NaN on a route's first day",
     "model_usage": "feature"},

    # --- outcome fields kept for diagnostics ONLY — never model inputs ---
    {"name": "delay_minutes", "dtype": "float", "source": "historical_operational_records (raw)",
     "description": "Realized delay for this stop-event. The raw signal the label is derived from.",
     "unit": "minutes", "transformation": "passthrough",
     "availability_time": "only known after the event — NEVER available at prediction time",
     "leakage_risk": "critical if used as a feature — label-derivative", "model_usage": "excluded (diagnostic only)"},
    {"name": "cancelled", "dtype": "bool", "source": "historical_operational_records (raw)",
     "description": "Whether the trip was cancelled at/before this stop.", "unit": None,
     "transformation": "passthrough", "availability_time": "only known after the event",
     "leakage_risk": "critical if used as a feature — label-derivative", "model_usage": "excluded (diagnostic only)"},
    {"name": "actual_time", "dtype": "datetime", "source": "historical_operational_records (raw)",
     "description": "Realized arrival time.", "unit": "datetime", "transformation": "passthrough",
     "availability_time": "only known after the event",
     "leakage_risk": "critical if used as a feature — label-derivative", "model_usage": "excluded (diagnostic only)"},

    # --- label ---
    {"name": "disruption_flag", "dtype": "int (0/1)", "source": "derived from historical_operational_records "
     "(src/utils/disruption_rules.py)",
     "description": "Binary disruption label: mode-specific delay threshold exceeded, or cancelled.",
     "unit": None, "transformation": "rule-based on delay_minutes/cancelled/transport_mode (see disruption_rules.py)",
     "availability_time": "only known after the event — this IS the prediction target", "leakage_risk": "N/A (label)",
     "model_usage": "label"},
]

SCHEMA_VERSION = "1.0.0"


def write_manifest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": SCHEMA_VERSION, "features": FEATURE_MANIFEST}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def manifest_columns() -> set[str]:
    return {f["name"] for f in FEATURE_MANIFEST}

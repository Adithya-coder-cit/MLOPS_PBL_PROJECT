"""Stage 11B §6/§7: the canonical data contract every source adapter
(synthetic OR real) must produce before Stage 3's existing pipeline runs.
Mirrors docs/stage11-real-data-discovery.md Section 7 exactly -- this
module is the single machine-readable copy of that design, not a second,
divergent one.

Every field is classified SOURCE (comes directly from the upstream feed),
DERIVED (computed by an ingestion adapter before Stage 3 ever sees it), or
MODEL (computed later, unchanged, by Stage 3's existing feature pipeline).
"""
from __future__ import annotations

from dataclasses import dataclass

SOURCE = "SOURCE"
DERIVED = "DERIVED"
MODEL = "MODEL"

DATASET_TYPE_DEMO = "DEVELOPMENT/DEMO"
DATASET_TYPE_REAL = "REAL"


@dataclass
class FieldSpec:
    name: str
    field_class: str  # SOURCE | DERIVED | MODEL
    nullable: bool
    description: str


# --- canonical `stops` ---
STOPS_CONTRACT = [
    FieldSpec("stop_id", SOURCE, False, "GTFS stop_id"),
    FieldSpec("stop_name", SOURCE, False, "GTFS stop_name"),
    FieldSpec("stop_lat", SOURCE, False, "GTFS stop_lat"),
    FieldSpec("stop_lon", SOURCE, False, "GTFS stop_lon"),
    FieldSpec("weather_zone_id", DERIVED, True,
              "Weather-join key, derived from (stop_lat, stop_lon) + the chosen weather "
              "station/grid -- NEVER GTFS's own (different-meaning, fare-related) zone_id column"),
]

# --- canonical `routes` ---
ROUTES_CONTRACT = [
    FieldSpec("route_id", SOURCE, False, "GTFS route_id"),
    FieldSpec("route_short_name", SOURCE, True, "GTFS route_short_name"),
    FieldSpec("route_long_name", SOURCE, True, "GTFS route_long_name"),
    FieldSpec("route_type_gtfs", SOURCE, False, "GTFS numeric route_type code"),
    FieldSpec("transport_mode", DERIVED, False,
              "Looked up from route_type_gtfs via the shared mode-mapping table "
              "(configs/real_data.yaml mode_mapping) -- see Stage 11B Sec 9"),
]

# --- canonical `trips` ---
TRIPS_CONTRACT = [
    FieldSpec("trip_id", SOURCE, False, "GTFS trip_id"),
    FieldSpec("route_id", SOURCE, False, "GTFS route_id"),
    FieldSpec("service_id", SOURCE, False,
              "GTFS service_id -- an OPEN set resolved via service_calendar, "
              "never the synthetic 2-value {weekday,weekend} enum"),
    FieldSpec("direction_id", SOURCE, True, "GTFS direction_id (0/1); may be absent in some feeds"),
    FieldSpec("trip_headsign", SOURCE, True, "GTFS trip_headsign"),
    FieldSpec("route_pattern_id", SOURCE, True,
              "GTFS route_patterns.txt id (MBTA extension) -- the key to distinct stop "
              "patterns within one (route_id, direction_id); absent for feeds without it "
              "(e.g. the synthetic generator), in which case graph construction falls back "
              "to one representative trip per (route_id, direction_id)"),
]

# --- canonical `stop_times` ---
STOP_TIMES_CONTRACT = [
    FieldSpec("trip_id", SOURCE, False, "GTFS trip_id"),
    FieldSpec("stop_id", SOURCE, False, "GTFS stop_id"),
    FieldSpec("stop_sequence", SOURCE, False, "GTFS stop_sequence"),
    FieldSpec("scheduled_arrival", SOURCE, True,
              "GTFS arrival_time, extended clock (hours may exceed 23) -- parsed via "
              "src.utils.gtfs_time, never modulo-24 wrapped"),
    FieldSpec("scheduled_departure", SOURCE, True, "GTFS departure_time, same extended-clock parsing"),
]

# --- canonical `service_calendar` -- NEW, did not exist before Stage 11B ---
SERVICE_CALENDAR_CONTRACT = [
    FieldSpec("service_id", SOURCE, False, "from calendar.txt and/or calendar_dates.txt"),
    FieldSpec("service_date", DERIVED, False,
              "expanded from calendar.txt's weekday booleans + date range, with "
              "calendar_dates.txt exceptions (add/remove) applied"),
    FieldSpec("is_exception", DERIVED, False,
              "true if this (service_id, service_date) pair came from a calendar_dates.txt "
              "exception rather than the regular weekly pattern"),
]

# --- canonical `weather` ---
WEATHER_CONTRACT = [
    FieldSpec("observation_id", DERIVED, False, "adapter-assigned stable id"),
    FieldSpec("weather_zone_id", DERIVED, False, "matches stops.weather_zone_id"),
    FieldSpec("timestamp", SOURCE, False, "observation timestamp, timezone-aware"),
    FieldSpec("precipitation_mm", SOURCE, True, "unavailable is recorded as null, never fabricated"),
    FieldSpec("temperature_c", SOURCE, True, "same"),
    FieldSpec("visibility_km", SOURCE, True, "same"),
]

# --- canonical `operational_events` (replaces historical_operational_records for real data) ---
OPERATIONAL_EVENTS_CONTRACT = [
    FieldSpec("record_id", DERIVED, False, "stable hash of (trip_id, stop_id, service_date)"),
    FieldSpec("trip_id", SOURCE, False, ""),
    FieldSpec("stop_id", SOURCE, False, ""),
    FieldSpec("service_date", SOURCE, False, ""),
    FieldSpec("scheduled_time", SOURCE, True, "from the historical source's own scheduled field"),
    FieldSpec("actual_time", SOURCE, True, "NULLABLE -- absent whenever the source has no observed time"),
    FieldSpec("delay_seconds", DERIVED, True, "actual_time - scheduled_time; null when actual_time is null"),
    FieldSpec("cancelled", SOURCE, True, "NULLABLE -- not every source publishes a cancellation flag"),
    FieldSpec("transport_mode", DERIVED, False, "looked up via trip_id -> route_id -> transport_mode"),
    FieldSpec("route_id", DERIVED, False, "looked up via trip_id -> route_id"),
    FieldSpec("direction_id", SOURCE, True, ""),
    FieldSpec("is_static_schedule_trip", DERIVED, False,
              "false for GTFS-RT-injected trip_ids (ADDED-/NONREV- prefixes) whose 'scheduled' "
              "time is a real-time placeholder, not a genuine published schedule entry -- "
              "verified in Stage 11B to account for 95% of extreme (>1hr) delay outliers in a "
              "real sample. Never silently dropped; downstream delay/label computation should "
              "filter or segment on this flag explicitly."),
    FieldSpec("label_available", DERIVED, False,
              "Stage 11B Sec 11 policy flag -- true only for modes with a verified real "
              "scheduled-vs-actual source (bus, metro, tram); false for rail/ferry. "
              "NEVER defaulted to a fabricated 0/1 label when false."),
    FieldSpec("disruption_flag", DERIVED, True,
              "NULL when label_available is false -- never 0. Computed only when true, per "
              "the configurable real-world policy (Stage 11B Sec 12, not yet activated)."),
]

# --- canonical `fares` ---
FARES_CONTRACT = [
    FieldSpec("route_id", SOURCE, True, ""),
    FieldSpec("fare_amount", SOURCE, True, "null when fare_available is false"),
    FieldSpec("currency", SOURCE, True, ""),
    FieldSpec("fare_available", DERIVED, False,
              "false when the source's fare structure could not be confidently reduced to "
              "a flat per-route amount (e.g. MBTA's leg-based GTFS-Fares v2) -- see Stage "
              "11B Sec 15. Routing/decision-engine cost scoring must degrade gracefully, "
              "never fabricate a cost."),
]


def contract_column_names(contract: list[FieldSpec]) -> list[str]:
    return [f.name for f in contract]


def contract_required_columns(contract: list[FieldSpec]) -> list[str]:
    return [f.name for f in contract if not f.nullable]

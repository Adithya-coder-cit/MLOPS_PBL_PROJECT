"""Declarative schemas for every raw RouteWise table.

Bump SCHEMA_VERSION whenever a table's required columns, dtypes, or
constraints change — it travels with the processed dataset's metadata so a
downstream consumer can tell which contract a given feature table honors.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SCHEMA_VERSION = "1.0.0"

VALID_TRANSPORT_MODES = {"bus", "tram", "metro", "rail", "ferry"}

# Loose, source-agnostic sanity bounds (hold for any real city too), not the
# specific synthetic bbox in configs/synthetic_data.yaml.
LAT_RANGE = (-90.0, 90.0)
LON_RANGE = (-180.0, 180.0)

# Domain-plausible bounds for the synthetic generator's ranges, with a
# tolerance margin — wide enough not to falsely flag a config change,
# tight enough to catch corrupt/impossible values.
DELAY_MINUTES_RANGE = (-60.0, 300.0)
PRECIPITATION_MM_RANGE = (0.0, 150.0)
TEMPERATURE_C_RANGE = (-30.0, 55.0)
VISIBILITY_KM_RANGE = (0.0, 20.0)


@dataclass
class TableSchema:
    name: str
    required_columns: list[str]
    dtypes: dict[str, str] = field(default_factory=dict)  # column -> pandas-ish dtype hint
    primary_key: list[str] | None = None
    not_nullable: list[str] = field(default_factory=list)
    foreign_keys: dict[str, tuple[str, str]] = field(default_factory=dict)  # col -> (ref_table, ref_col)
    categorical: dict[str, set[str]] = field(default_factory=dict)  # col -> allowed values
    numeric_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)  # col -> (min, max)


STOPS = TableSchema(
    name="stops",
    required_columns=["stop_id", "stop_name", "stop_lat", "stop_lon", "zone_id"],
    dtypes={"stop_lat": "float", "stop_lon": "float"},
    primary_key=["stop_id"],
    not_nullable=["stop_id", "stop_lat", "stop_lon", "zone_id"],
    numeric_ranges={"stop_lat": LAT_RANGE, "stop_lon": LON_RANGE},
)

ROUTES = TableSchema(
    name="routes",
    required_columns=["route_id", "route_short_name", "route_long_name", "transport_mode", "route_type_gtfs"],
    primary_key=["route_id"],
    not_nullable=["route_id", "transport_mode"],
    categorical={"transport_mode": VALID_TRANSPORT_MODES},
)

TRIPS = TableSchema(
    name="trips",
    required_columns=["trip_id", "route_id", "service_id", "direction_id", "trip_headsign"],
    primary_key=["trip_id"],
    not_nullable=["trip_id", "route_id", "service_id"],
    foreign_keys={"route_id": ("routes", "route_id")},
    categorical={"service_id": {"weekday", "weekend"}, "direction_id": {"0", "1"}},
)

STOP_TIMES = TableSchema(
    name="stop_times",
    required_columns=["trip_id", "stop_id", "stop_sequence", "scheduled_arrival", "scheduled_departure"],
    primary_key=["trip_id", "stop_sequence"],
    not_nullable=["trip_id", "stop_id", "stop_sequence", "scheduled_arrival", "scheduled_departure"],
    foreign_keys={"trip_id": ("trips", "trip_id"), "stop_id": ("stops", "stop_id")},
)

FARES = TableSchema(
    name="fares",
    required_columns=["route_id", "fare_amount", "currency"],
    primary_key=["route_id"],
    not_nullable=["route_id", "fare_amount"],
    foreign_keys={"route_id": ("routes", "route_id")},
    numeric_ranges={"fare_amount": (0.0, 10_000.0)},
)

HISTORICAL_OPERATIONAL_RECORDS = TableSchema(
    name="historical_operational_records",
    required_columns=[
        "record_id", "trip_id", "stop_id", "service_date", "scheduled_time", "actual_time",
        "delay_minutes", "cancelled", "disruption_flag", "transport_mode",
    ],
    primary_key=["record_id"],
    not_nullable=["record_id", "trip_id", "stop_id", "service_date", "scheduled_time", "delay_minutes",
                  "disruption_flag", "transport_mode"],
    foreign_keys={"trip_id": ("trips", "trip_id"), "stop_id": ("stops", "stop_id")},
    categorical={"transport_mode": VALID_TRANSPORT_MODES, "disruption_flag": {"0", "1"}},
    numeric_ranges={"delay_minutes": DELAY_MINUTES_RANGE},
)

WEATHER_OBSERVATIONS = TableSchema(
    name="weather_observations",
    required_columns=["observation_id", "zone_id", "timestamp", "precipitation_mm", "temperature_c", "visibility_km"],
    primary_key=["observation_id"],
    not_nullable=["observation_id", "zone_id", "timestamp", "precipitation_mm", "temperature_c", "visibility_km"],
    numeric_ranges={
        "precipitation_mm": PRECIPITATION_MM_RANGE,
        "temperature_c": TEMPERATURE_C_RANGE,
        "visibility_km": VISIBILITY_KM_RANGE,
    },
)

ALL_SCHEMAS = {
    "stops": STOPS,
    "routes": ROUTES,
    "trips": TRIPS,
    "stop_times": STOP_TIMES,
    "fares": FARES,
    "historical_operational_records": HISTORICAL_OPERATIONAL_RECORDS,
    "weather_observations": WEATHER_OBSERVATIONS,
}

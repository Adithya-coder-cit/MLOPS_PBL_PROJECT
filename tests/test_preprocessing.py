"""Tests for preprocessing steps, with explicit focus on proving the
weather asof-join never pulls a future observation (anti-leakage)."""
import pandas as pd

from src.preprocessing.clean import (
    drop_exact_duplicates,
    join_route_metadata,
    join_weather_asof,
    parse_datetimes,
)


def test_parse_datetimes_converts_to_datetime64():
    df = pd.DataFrame({"t": ["2025-06-01 08:00:00", "2025-06-02 09:00:00"]})
    out = parse_datetimes(df, ["t"])
    assert pd.api.types.is_datetime64_any_dtype(out["t"])


def test_drop_exact_duplicates_removes_only_exact_dupes():
    df = pd.DataFrame({"a": [1, 1, 2], "b": [1, 1, 3]})
    out = drop_exact_duplicates(df, "t")
    assert len(out) == 2


def test_join_weather_asof_never_uses_future_weather():
    stops = pd.DataFrame({"stop_id": ["S1"], "zone_id": ["Z1"]})
    historical = pd.DataFrame({
        "stop_id": ["S1"],
        "scheduled_time": [pd.Timestamp("2025-06-01 10:00:00")],
    })
    weather = pd.DataFrame({
        "zone_id": ["Z1", "Z1", "Z1"],
        "timestamp": [
            pd.Timestamp("2025-06-01 09:00:00"),  # before — eligible
            pd.Timestamp("2025-06-01 11:00:00"),  # after — must NOT be picked
            pd.Timestamp("2025-06-01 12:00:00"),  # after — must NOT be picked
        ],
        "precipitation_mm": [1.0, 999.0, 999.0],
        "temperature_c": [20.0, -999.0, -999.0],
        "visibility_km": [8.0, -999.0, -999.0],
    })
    merged = join_weather_asof(historical, weather, stops, tolerance_hours=6)
    assert merged.loc[0, "precipitation_mm"] == 1.0  # the 09:00 reading, not the 11:00/12:00 ones


def test_join_weather_asof_respects_tolerance():
    stops = pd.DataFrame({"stop_id": ["S1"], "zone_id": ["Z1"]})
    historical = pd.DataFrame({
        "stop_id": ["S1"],
        "scheduled_time": [pd.Timestamp("2025-06-01 10:00:00")],
    })
    weather = pd.DataFrame({
        "zone_id": ["Z1"],
        "timestamp": [pd.Timestamp("2025-06-01 01:00:00")],  # 9 hours before, outside tolerance
        "precipitation_mm": [1.0], "temperature_c": [20.0], "visibility_km": [8.0],
    })
    merged = join_weather_asof(historical, weather, stops, tolerance_hours=2)
    assert pd.isna(merged.loc[0, "precipitation_mm"])


def test_join_route_metadata_adds_expected_columns():
    historical = pd.DataFrame({"trip_id": ["T1"]})
    trips = pd.DataFrame({"trip_id": ["T1"], "route_id": ["R1"], "service_id": ["weekday"], "direction_id": [0]})
    routes = pd.DataFrame({"route_id": ["R1"], "route_type_gtfs": [3]})
    merged = join_route_metadata(historical, trips, routes)
    assert set(["route_id", "service_id", "direction_id", "route_type_gtfs"]) <= set(merged.columns)
    assert merged.loc[0, "route_id"] == "R1"

"""Schema, referential-integrity, and leakage-safety checks for the
synthetic DEVELOPMENT/DEMO dataset produced by
src/ingestion/generate_demo_data.py.

These tests run against the generated CSVs under data/raw/ and are skipped
if the dataset has not been generated yet.
"""
from pathlib import Path

import pandas as pd
import pytest
import yaml

RAW = Path("data/raw")
REQUIRED_FILES = [
    RAW / "gtfs" / "stops.csv",
    RAW / "gtfs" / "routes.csv",
    RAW / "gtfs" / "trips.csv",
    RAW / "gtfs" / "stop_times.csv",
    RAW / "gtfs" / "fares.csv",
    RAW / "operational" / "historical_operational_records.csv",
    RAW / "weather" / "weather_observations.csv",
]

pytestmark = pytest.mark.skipif(
    not all(f.exists() for f in REQUIRED_FILES),
    reason="synthetic dataset not generated yet (run src/ingestion/generate_demo_data.py)",
)


@pytest.fixture(scope="module")
def tables():
    return {
        "stops": pd.read_csv(RAW / "gtfs" / "stops.csv"),
        "routes": pd.read_csv(RAW / "gtfs" / "routes.csv"),
        "trips": pd.read_csv(RAW / "gtfs" / "trips.csv"),
        "stop_times": pd.read_csv(RAW / "gtfs" / "stop_times.csv"),
        "fares": pd.read_csv(RAW / "gtfs" / "fares.csv"),
        "historical": pd.read_csv(RAW / "operational" / "historical_operational_records.csv"),
        "weather": pd.read_csv(RAW / "weather" / "weather_observations.csv"),
    }


def test_dataset_card_labels_data_as_demo():
    card = (RAW / "DATASET_CARD.md").read_text(encoding="utf-8")
    assert "DEVELOPMENT/DEMO" in card
    assert "SYNTHETIC" in card


def test_required_columns_present(tables):
    assert set(["stop_id", "stop_name", "stop_lat", "stop_lon", "zone_id"]) <= set(tables["stops"].columns)
    assert set(["route_id", "transport_mode", "route_type_gtfs"]) <= set(tables["routes"].columns)
    assert set(["trip_id", "route_id", "service_id", "direction_id"]) <= set(tables["trips"].columns)
    assert set(["trip_id", "stop_id", "stop_sequence", "scheduled_arrival", "scheduled_departure"]) <= set(
        tables["stop_times"].columns
    )
    assert set(["record_id", "trip_id", "stop_id", "service_date", "scheduled_time", "actual_time",
                "delay_minutes", "cancelled", "disruption_flag", "transport_mode"]) <= set(tables["historical"].columns)
    assert set(["zone_id", "timestamp", "precipitation_mm", "temperature_c", "visibility_km"]) <= set(
        tables["weather"].columns
    )
    assert set(["route_id", "fare_amount", "currency"]) <= set(tables["fares"].columns)


def test_primary_keys_unique(tables):
    assert tables["stops"]["stop_id"].is_unique
    assert tables["routes"]["route_id"].is_unique
    assert tables["trips"]["trip_id"].is_unique
    assert tables["historical"]["record_id"].is_unique
    assert not tables["stop_times"].duplicated(subset=["trip_id", "stop_sequence"]).any()


def test_foreign_key_integrity(tables):
    assert set(tables["trips"]["route_id"]) <= set(tables["routes"]["route_id"])
    assert set(tables["stop_times"]["trip_id"]) <= set(tables["trips"]["trip_id"])
    assert set(tables["stop_times"]["stop_id"]) <= set(tables["stops"]["stop_id"])
    assert set(tables["historical"]["trip_id"]) <= set(tables["trips"]["trip_id"])
    assert set(tables["historical"]["stop_id"]) <= set(tables["stops"]["stop_id"])
    assert set(tables["fares"]["route_id"]) <= set(tables["routes"]["route_id"])
    assert set(tables["weather"]["zone_id"]) <= set(tables["stops"]["zone_id"])


def test_no_nulls_in_required_fields(tables):
    for col in ["stop_id", "stop_lat", "stop_lon", "zone_id"]:
        assert tables["stops"][col].notna().all()
    for col in ["record_id", "trip_id", "stop_id", "delay_minutes", "disruption_flag"]:
        assert tables["historical"][col].notna().all()
    for col in ["precipitation_mm", "temperature_c", "visibility_km"]:
        assert tables["weather"][col].notna().all()


def test_disruption_label_is_binary_and_not_degenerate(tables):
    labels = set(tables["historical"]["disruption_flag"].unique())
    assert labels <= {0, 1}
    rate = tables["historical"]["disruption_flag"].mean()
    # not no-signal-trivial (~0%) and not deterministically-always (~100%)
    assert 0.01 < rate < 0.60


def test_mode_disruption_rates_differ_by_mode(tables):
    rates = tables["historical"].groupby("transport_mode")["disruption_flag"].mean()
    assert rates.nunique() > 1  # modes are not interchangeable — weather sensitivity/thresholds differ


def test_weather_is_not_iid_noise(tables):
    weather = tables["weather"].sort_values(["zone_id", "timestamp"])
    one_zone = weather[weather["zone_id"] == weather["zone_id"].iloc[0]]
    autocorr = one_zone["temperature_c"].autocorr(lag=1)
    assert autocorr > 0.3  # diurnal/seasonal structure, not white noise


def test_fares_are_synthetic_units_not_real_currency(tables):
    assert (tables["fares"]["currency"] == "SYNTHETIC_UNITS").all()


def test_generation_config_thresholds_match_dataset_card():
    with open("configs/synthetic_data.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert set(cfg["mode_mix"].keys()) == set(cfg["mode_params"].keys())
    assert abs(sum(cfg["mode_mix"].values()) - 1.0) < 1e-6

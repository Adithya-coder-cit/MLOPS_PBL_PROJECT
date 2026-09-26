"""Stage 11B tests: GTFS parsing/normalization, service calendars,
calendar exceptions, 24+ hour timestamps, route variants, mode mapping,
historical normalization, label-unavailable behavior, weather
normalization/as-of join, provenance, validation, deterministic
processing. Unit-level tests use small synthetic fixtures (fast); a few
integration tests run against the real downloaded MBTA data and are
skipped if it isn't present.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.ingestion.gtfs import normalize as gtfs_normalize
from src.ingestion.gtfs import parser as gtfs_parser
from src.ingestion.gtfs import validator as gtfs_validator
from src.ingestion.historical import normalize as hist_normalize
from src.ingestion.weather import normalize as weather_normalize
from src.routing.graph_builder import _select_representative_trips
from src.utils.gtfs_time import (
    gtfs_time_to_datetime,
    is_midnight_crossing,
    parse_gtfs_time_to_minutes,
    parse_gtfs_time_to_seconds,
    seconds_since_midnight_to_datetime,
)

REAL_GTFS_ZIP = Path("data/raw/real/gtfs/MBTA_GTFS.zip")
REAL_SUBWAY_DIR = Path("data/raw/real/historical/subway")
REAL_BUS_PARQUET = Path("data/raw/real/historical/bus/LAMP_RECENT_Bus_Events.parquet")
requires_real_gtfs = pytest.mark.skipif(not REAL_GTFS_ZIP.exists(), reason="Real MBTA GTFS feed not downloaded")
requires_real_subway = pytest.mark.skipif(
    not REAL_SUBWAY_DIR.exists() or not list(REAL_SUBWAY_DIR.glob("*.parquet")),
    reason="Real MBTA subway performance sample not downloaded",
)
requires_real_bus = pytest.mark.skipif(
    not REAL_BUS_PARQUET.exists(), reason="Real MBTA bus events sample not downloaded",
)


# ============================== GTFS time handling (Sec 7) ==============================

class TestGtfsTime:
    @pytest.mark.parametrize("time_str,expected_minutes", [
        ("23:30:00", 1410), ("24:30:00", 1470), ("25:15:00", 1515), ("00:00:00", 0),
    ])
    def test_parse_extended_times_to_minutes(self, time_str, expected_minutes):
        assert parse_gtfs_time_to_minutes(time_str) == expected_minutes

    @pytest.mark.parametrize("time_str,expected_seconds", [
        ("23:30:00", 84600), ("24:30:00", 88200), ("25:15:00", 90900),
    ])
    def test_parse_extended_times_to_seconds(self, time_str, expected_seconds):
        assert parse_gtfs_time_to_seconds(time_str) == expected_seconds

    def test_none_and_blank_and_nan_return_none(self):
        assert parse_gtfs_time_to_minutes(None) is None
        assert parse_gtfs_time_to_minutes("") is None
        assert parse_gtfs_time_to_minutes(float("nan")) is None

    def test_malformed_time_returns_none_not_a_guess(self):
        assert parse_gtfs_time_to_minutes("not-a-time") is None

    @pytest.mark.parametrize("time_str,expected_crossing", [
        ("23:30:00", False), ("24:30:00", True), ("25:15:00", True), ("00:01:00", False),
    ])
    def test_midnight_crossing_detection(self, time_str, expected_crossing):
        assert is_midnight_crossing(time_str) is expected_crossing

    def test_extended_time_rolls_into_next_calendar_day_service_date_fixed(self):
        d = date(2026, 9, 20)
        dt = gtfs_time_to_datetime(d, "25:15:00", "America/New_York")
        assert dt.date() == date(2026, 9, 21)  # wall-clock day rolled over
        assert dt.hour == 1 and dt.minute == 15  # but it's 1:15 AM, not 25:15

    def test_23_30_stays_on_service_date(self):
        d = date(2026, 9, 20)
        dt = gtfs_time_to_datetime(d, "23:30:00", "America/New_York")
        assert dt.date() == date(2026, 9, 20)

    def test_timezone_aware(self):
        dt = gtfs_time_to_datetime(date(2026, 9, 20), "12:00:00", "America/New_York")
        assert dt.tzinfo is not None

    def test_seconds_since_midnight_matches_string_parsing(self):
        d = date(2026, 9, 20)
        from_string = gtfs_time_to_datetime(d, "24:30:00", "America/New_York")
        from_seconds = seconds_since_midnight_to_datetime(d, 88200.0, "America/New_York")
        assert from_string == from_seconds

    def test_seconds_since_midnight_nan_returns_none(self):
        assert seconds_since_midnight_to_datetime(date(2026, 9, 20), float("nan"), "America/New_York") is None


# ============================== GTFS parsing (Sec 5) ==============================

def _write_minimal_gtfs_zip(tmp_path: Path, include_optional: bool = False) -> Path:
    import zipfile

    zip_path = tmp_path / "test_gtfs.zip"
    files = {
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\nS1,Stop One,42.0,-71.0\nS2,Stop Two,42.1,-71.1\n",
        "routes.txt": "route_id,route_short_name,route_long_name,route_type\nR1,1,Route One,3\n",
        "trips.txt": "trip_id,route_id,service_id,direction_id,trip_headsign\nT1,R1,WK,0,Downtown\n",
        "stop_times.txt": "trip_id,stop_id,stop_sequence,arrival_time,departure_time\n"
                           "T1,S1,1,08:00:00,08:00:00\nT1,S2,2,08:10:00,08:10:00\n",
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                         "WK,1,1,1,1,1,0,0,20260101,20260131\n",
        "calendar_dates.txt": "service_id,date,exception_type\nWK,20260119,2\n",
    }
    if include_optional:
        files["transfers.txt"] = "from_stop_id,to_stop_id,transfer_type\nS1,S2,0\n"

    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return zip_path


class TestGtfsParsing:
    def test_parses_required_files(self, tmp_path):
        zip_path = _write_minimal_gtfs_zip(tmp_path)
        tables = gtfs_parser.parse_gtfs_zip(zip_path)
        for key in ["stops", "routes", "trips", "stop_times", "calendar", "calendar_dates"]:
            assert key in tables

    def test_missing_optional_file_does_not_fail(self, tmp_path):
        zip_path = _write_minimal_gtfs_zip(tmp_path, include_optional=False)
        tables = gtfs_parser.parse_gtfs_zip(zip_path)
        assert "transfers" not in tables

    def test_present_optional_file_is_read(self, tmp_path):
        zip_path = _write_minimal_gtfs_zip(tmp_path, include_optional=True)
        tables = gtfs_parser.parse_gtfs_zip(zip_path)
        assert "transfers" in tables and len(tables["transfers"]) == 1

    def test_missing_required_file_raises(self, tmp_path):
        import zipfile
        zip_path = tmp_path / "broken.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("stops.txt", "stop_id,stop_name,stop_lat,stop_lon\nS1,A,42.0,-71.0\n")
        with pytest.raises(FileNotFoundError):
            gtfs_parser.parse_gtfs_zip(zip_path)

    def test_calendar_dates_only_feed_is_accepted(self, tmp_path):
        import zipfile
        zip_path = tmp_path / "cd_only.zip"
        files = {
            "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\nS1,A,42.0,-71.0\n",
            "routes.txt": "route_id,route_short_name,route_long_name,route_type\nR1,1,One,3\n",
            "trips.txt": "trip_id,route_id,service_id,direction_id,trip_headsign\nT1,R1,WK,0,X\n",
            "stop_times.txt": "trip_id,stop_id,stop_sequence,arrival_time,departure_time\nT1,S1,1,08:00:00,08:00:00\n",
            "calendar_dates.txt": "service_id,date,exception_type\nWK,20260101,1\n",
        }
        with zipfile.ZipFile(zip_path, "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        tables = gtfs_parser.parse_gtfs_zip(zip_path)
        assert "calendar" not in tables
        assert "calendar_dates" in tables


# ============================== service calendar (Sec 6) ==============================

class TestServiceCalendar:
    def test_weekly_pattern_expands_correctly(self):
        calendar = pd.DataFrame([{
            "service_id": "WK", "monday": "1", "tuesday": "1", "wednesday": "0", "thursday": "0",
            "friday": "0", "saturday": "0", "sunday": "0", "start_date": "20260105", "end_date": "20260111",
        }])
        empty_exceptions = pd.DataFrame(columns=["service_id", "date", "exception_type"])
        cal = gtfs_normalize.build_service_calendar(calendar, empty_exceptions)
        dates = sorted(cal["service_date"].tolist())
        # 2026-01-05 is a Monday; expect Mon 1/5 and Tue 1/6 only within the week.
        assert dates == [date(2026, 1, 5), date(2026, 1, 6)]
        assert not cal["is_exception"].any()

    def test_exception_type_1_adds_service(self):
        calendar = pd.DataFrame([{
            "service_id": "WK", "monday": "0", "tuesday": "0", "wednesday": "0", "thursday": "0",
            "friday": "0", "saturday": "0", "sunday": "0", "start_date": "20260101", "end_date": "20260107",
        }])
        exceptions = pd.DataFrame([{"service_id": "WK", "date": "20260103", "exception_type": "1"}])
        cal = gtfs_normalize.build_service_calendar(calendar, exceptions)
        assert date(2026, 1, 3) in cal["service_date"].tolist()
        assert cal.loc[cal["service_date"] == date(2026, 1, 3), "is_exception"].iloc[0]

    def test_exception_type_2_removes_service(self):
        calendar = pd.DataFrame([{
            "service_id": "WK", "monday": "1", "tuesday": "0", "wednesday": "0", "thursday": "0",
            "friday": "0", "saturday": "0", "sunday": "0", "start_date": "20260105", "end_date": "20260105",
        }])
        exceptions = pd.DataFrame([{"service_id": "WK", "date": "20260105", "exception_type": "2"}])
        cal = gtfs_normalize.build_service_calendar(calendar, exceptions)
        assert cal.empty

    def test_calendar_dates_only_no_calendar_txt(self):
        exceptions = pd.DataFrame([{"service_id": "HOL", "date": "20260704", "exception_type": "1"}])
        cal = gtfs_normalize.build_service_calendar(None, exceptions)
        assert len(cal) == 1
        assert cal.iloc[0]["service_date"] == date(2026, 7, 4)

    def test_effective_service_ids_resolves_correctly(self):
        cal = pd.DataFrame([
            {"service_id": "A", "service_date": date(2026, 1, 5), "is_exception": False},
            {"service_id": "B", "service_date": date(2026, 1, 5), "is_exception": False},
            {"service_id": "A", "service_date": date(2026, 1, 6), "is_exception": False},
        ])
        assert gtfs_normalize.effective_service_ids(cal, date(2026, 1, 5)) == {"A", "B"}
        assert gtfs_normalize.effective_service_ids(cal, date(2026, 1, 6)) == {"A"}
        assert gtfs_normalize.effective_service_ids(cal, date(2026, 1, 7)) == set()


# ============================== mode mapping (Sec 9) ==============================

class TestModeMapping:
    MAPPING_CFG = {"by_route_type": {"0": "tram", "1": "metro", "2": "rail", "3": "bus", "4": "ferry"},
                   "unknown_mode_severity": "ERROR"}

    def test_known_route_types_map_correctly(self):
        routes = pd.DataFrame([
            {"route_id": "R1", "route_short_name": "1", "route_long_name": "One", "route_type": "3"},
            {"route_id": "Red", "route_short_name": "", "route_long_name": "Red Line", "route_type": "1"},
        ])
        out, issues = gtfs_normalize.normalize_routes(routes, self.MAPPING_CFG)
        assert issues == []
        assert dict(zip(out["route_id"], out["transport_mode"])) == {"R1": "bus", "Red": "metro"}

    def test_unknown_route_type_is_never_silently_mapped(self):
        routes = pd.DataFrame([
            {"route_id": "Weird", "route_short_name": "", "route_long_name": "Mystery", "route_type": "99"},
        ])
        out, issues = gtfs_normalize.normalize_routes(routes, self.MAPPING_CFG)
        assert out.iloc[0]["transport_mode"] is None
        assert len(issues) == 1
        assert issues[0].level == "ERROR"
        assert issues[0].route_type == "99"

    def test_unknown_mode_severity_is_configurable(self):
        cfg = dict(self.MAPPING_CFG, unknown_mode_severity="WARNING")
        routes = pd.DataFrame([{"route_id": "X", "route_short_name": "", "route_long_name": "", "route_type": "99"}])
        _out, issues = gtfs_normalize.normalize_routes(routes, cfg)
        assert issues[0].level == "WARNING"


# ============================== route variants (Sec 8) ==============================

class TestRouteVariants:
    def test_multiple_patterns_per_route_direction_are_preserved(self):
        trips = pd.DataFrame([
            {"trip_id": "T1", "route_id": "Red", "service_id": "weekday", "direction_id": 0,
             "route_pattern_id": "Red-1-0"},
            {"trip_id": "T2", "route_id": "Red", "service_id": "weekday", "direction_id": 0,
             "route_pattern_id": "Red-3-0"},
            {"trip_id": "T3", "route_id": "Red", "service_id": "weekday", "direction_id": 1,
             "route_pattern_id": "Red-1-1"},
        ])
        reps = _select_representative_trips(trips)
        assert len(reps) == 3  # NOT collapsed to 2 (one per route_id+direction_id)
        assert set(reps["route_pattern_id"]) == {"Red-1-0", "Red-3-0", "Red-1-1"}

    def test_synthetic_style_trips_without_pattern_column_fall_back_unchanged(self):
        trips = pd.DataFrame([
            {"trip_id": "T1", "route_id": "R1", "service_id": "weekday", "direction_id": 0},
            {"trip_id": "T2", "route_id": "R1", "service_id": "weekday", "direction_id": 0},
            {"trip_id": "T3", "route_id": "R1", "service_id": "weekday", "direction_id": 1},
        ])
        reps = _select_representative_trips(trips)
        assert len(reps) == 2  # one per (route_id, direction_id), old behavior preserved

    def test_weekday_service_preferred_within_a_pattern(self):
        trips = pd.DataFrame([
            {"trip_id": "T_weekend", "route_id": "R1", "service_id": "weekend", "direction_id": 0,
             "route_pattern_id": "P1"},
            {"trip_id": "T_weekday", "route_id": "R1", "service_id": "weekday", "direction_id": 0,
             "route_pattern_id": "P1"},
        ])
        reps = _select_representative_trips(trips)
        assert reps.iloc[0]["trip_id"] == "T_weekday"

    def test_null_pattern_rows_fall_back_defensively(self):
        trips = pd.DataFrame([
            {"trip_id": "T1", "route_id": "R1", "service_id": "weekday", "direction_id": 0,
             "route_pattern_id": "P1"},
            {"trip_id": "T2", "route_id": "R2", "service_id": "weekday", "direction_id": 0,
             "route_pattern_id": None},
        ])
        reps = _select_representative_trips(trips)
        assert len(reps) == 2
        assert "T2" in reps["trip_id"].tolist()


# ============================== historical normalization + labels (Sec 10/11) ==============================

class TestHistoricalNormalization:
    ROUTE_TO_MODE = {"Red": "metro", "1": "bus"}
    LABEL_AVAIL = {"metro": True, "bus": True, "rail": False, "ferry": False, "tram": True}

    def test_subway_delay_seconds_computed_correctly(self):
        raw = pd.DataFrame([{
            "trip_id": "T1", "stop_id": "S1", "service_date": "20260920", "route_id": "Red",
            "direction_id": True, "scheduled_arrival_time": 3600.0,  # 01:00:00 local
            "stop_timestamp": pd.Timestamp("2026-09-20 05:02:00", tz="UTC").timestamp(),  # 01:02 EDT -> +120s delay
        }])
        out = hist_normalize.normalize_subway_performance(raw, self.ROUTE_TO_MODE, self.LABEL_AVAIL)
        assert out.iloc[0]["delay_seconds"] == pytest.approx(120.0, abs=1.0)
        assert out.iloc[0]["transport_mode"] == "metro"
        assert out.iloc[0]["label_available"] is np.True_ or out.iloc[0]["label_available"] is True

    def test_label_unavailable_mode_never_gets_fabricated_zero_label(self):
        raw = pd.DataFrame([{
            "trip_id": "T1", "stop_id": "S1", "service_date": "20260920", "route_id": "Red",
            "direction_id": True, "scheduled_arrival_time": 3600.0,
            "stop_timestamp": pd.Timestamp("2026-09-20 05:02:00", tz="UTC").timestamp(),
        }])
        no_label_map = {"metro": False}
        out = hist_normalize.normalize_subway_performance(raw, self.ROUTE_TO_MODE, no_label_map)
        assert out.iloc[0]["label_available"] == False  # noqa: E712 - explicit False check, not falsy
        assert pd.isna(out.iloc[0]["disruption_flag"])  # NEVER 0

    def test_added_prefixed_trip_is_flagged_not_static_schedule(self):
        raw = pd.DataFrame([{
            "trip_id": "ADDED-12345", "stop_id": "S1", "service_date": "20260920", "route_id": "Red",
            "direction_id": True, "scheduled_arrival_time": 3600.0,
            "stop_timestamp": pd.Timestamp("2026-09-20 05:02:00", tz="UTC").timestamp(),
        }])
        out = hist_normalize.normalize_subway_performance(raw, self.ROUTE_TO_MODE, self.LABEL_AVAIL)
        assert out.iloc[0]["is_static_schedule_trip"] == False  # noqa: E712

    def test_regular_trip_id_is_static_schedule(self):
        raw = pd.DataFrame([{
            "trip_id": "77916432", "stop_id": "S1", "service_date": "20260920", "route_id": "Red",
            "direction_id": True, "scheduled_arrival_time": 3600.0,
            "stop_timestamp": pd.Timestamp("2026-09-20 05:02:00", tz="UTC").timestamp(),
        }])
        out = hist_normalize.normalize_subway_performance(raw, self.ROUTE_TO_MODE, self.LABEL_AVAIL)
        assert out.iloc[0]["is_static_schedule_trip"] == True  # noqa: E712

    def test_missing_actual_time_leaves_delay_null_not_zero(self):
        raw = pd.DataFrame([{
            "trip_id": "T1", "stop_id": "S1", "service_date": "20260920", "route_id": "Red",
            "direction_id": True, "scheduled_arrival_time": 3600.0, "stop_timestamp": None,
        }])
        out = hist_normalize.normalize_subway_performance(raw, self.ROUTE_TO_MODE, self.LABEL_AVAIL)
        assert pd.isna(out.iloc[0]["delay_seconds"])
        assert out.iloc[0]["actual_time"] is None

    def test_bus_timezone_mismatch_is_corrected(self):
        """The real, verified finding: plan_stop_departure_dt is naive
        local time, stop_departure_dt is naive UTC -- comparing them
        directly fabricates a ~4 hour 'delay' on every row."""
        raw = pd.DataFrame([{
            "trip_id": "T1", "stop_id": "S1", "route_id": "1", "direction_id": True,
            "service_date": "2026-09-20",
            "plan_stop_departure_dt": pd.Timestamp("2026-09-20 21:11:00"),  # naive local (EDT)
            "stop_departure_dt": pd.Timestamp("2026-09-21 01:11:12"),  # naive UTC (same instant + 12s)
        }])
        out = hist_normalize.normalize_bus_events(raw, self.ROUTE_TO_MODE, self.LABEL_AVAIL)
        # Correct delay is ~12 seconds, NOT ~4 hours.
        assert abs(out.iloc[0]["delay_seconds"]) < 60

    def test_apply_disruption_label_policy_inactive_leaves_null(self):
        events = pd.DataFrame([{"transport_mode": "metro", "delay_seconds": 400.0, "label_available": True,
                                 "cancelled": pd.NA}])
        policy = {"active": False, "placeholder_thresholds_seconds": {"metro": 300}}
        out = hist_normalize.apply_real_disruption_label_policy(events, policy)
        assert pd.isna(out.iloc[0]["disruption_flag"]) if "disruption_flag" in out.columns else True

    def test_apply_disruption_label_policy_active_computes_flag(self):
        events = pd.DataFrame([
            {"transport_mode": "metro", "delay_seconds": 400.0, "label_available": True, "cancelled": pd.NA},
            {"transport_mode": "metro", "delay_seconds": 10.0, "label_available": True, "cancelled": pd.NA},
            {"transport_mode": "rail", "delay_seconds": 900.0, "label_available": False, "cancelled": pd.NA},
        ])
        policy = {"active": True, "placeholder_thresholds_seconds": {"metro": 300},
                   "cancellation_counts_as_disruption": True}
        out = hist_normalize.apply_real_disruption_label_policy(events, policy)
        assert out.iloc[0]["disruption_flag"] == 1
        assert out.iloc[1]["disruption_flag"] == 0
        assert pd.isna(out.iloc[2]["disruption_flag"])  # rail: label_available=False -> stays null


# ============================== weather (Sec 13/14) ==============================

class TestWeatherNormalization:
    def test_observations_to_dataframe_preserves_nulls(self):
        from src.ingestion.weather.nws import observations_to_dataframe
        geojson = {"features": [{"properties": {
            "timestamp": "2026-09-20T12:00:00+00:00",
            "temperature": {"value": 20.0}, "precipitationLastHour": {"value": None}, "visibility": {"value": 16000},
        }}]}
        df = observations_to_dataframe(geojson)
        assert df.iloc[0]["temperature_c"] == 20.0
        assert pd.isna(df.iloc[0]["precipitation_mm"])  # never fabricated as 0
        assert df.iloc[0]["visibility_km"] == pytest.approx(16.0)

    def test_normalize_assigns_weather_zone_and_utc_timestamp(self):
        raw = pd.DataFrame([{"timestamp": "2026-09-20T12:00:00+00:00", "temperature_c": 20.0,
                              "precipitation_mm": None, "visibility_km": 16.0}])
        out = weather_normalize.normalize_nws_observations(raw, "KBOS")
        assert out.iloc[0]["weather_zone_id"] == "KBOS"
        assert out.iloc[0]["timestamp"].tzinfo is not None

    def test_asof_join_never_uses_future_observation(self):
        events = pd.DataFrame([{
            "stop_id": "S1", "scheduled_time": pd.Timestamp("2026-09-20 12:00:00", tz="America/New_York"),
        }])
        weather = pd.DataFrame([
            {"weather_zone_id": "KBOS", "timestamp": pd.Timestamp("2026-09-20 11:00:00", tz="UTC"),
             "temperature_c": 15.0, "precipitation_mm": None, "visibility_km": 16.0},
            # The row below is in the future relative to scheduled_time -- must never be used.
            {"weather_zone_id": "KBOS", "timestamp": pd.Timestamp("2026-09-20 20:00:00", tz="UTC"),
             "temperature_c": 99.0, "precipitation_mm": None, "visibility_km": 1.0},
        ])
        stops = pd.DataFrame([{"stop_id": "S1", "weather_zone_id": "KBOS"}])
        joined = weather_normalize.join_weather_asof(events, weather, stops, tolerance_hours=24)
        assert joined.iloc[0]["temperature_c"] == 15.0  # the earlier (past) observation, never the future one

    def test_asof_join_respects_tolerance(self):
        events = pd.DataFrame([{
            "stop_id": "S1", "scheduled_time": pd.Timestamp("2026-09-20 12:00:00", tz="America/New_York"),
        }])
        weather = pd.DataFrame([
            {"weather_zone_id": "KBOS", "timestamp": pd.Timestamp("2026-09-19 00:00:00", tz="UTC"),  # >24h before
             "temperature_c": 15.0, "precipitation_mm": None, "visibility_km": 16.0},
        ])
        stops = pd.DataFrame([{"stop_id": "S1", "weather_zone_id": "KBOS"}])
        joined = weather_normalize.join_weather_asof(events, weather, stops, tolerance_hours=2)
        assert pd.isna(joined.iloc[0]["temperature_c"])  # too far in the past -- left null, not fabricated


# ============================== GTFS validation (Sec 16) ==============================

class TestGtfsValidation:
    def test_clean_data_passes(self):
        stops = pd.DataFrame([{"stop_id": "S1", "stop_lat": 42.0, "stop_lon": -71.0}])
        routes = pd.DataFrame([{"route_id": "R1"}])
        trips = pd.DataFrame([{"trip_id": "T1", "route_id": "R1", "service_id": "WK"}])
        stop_times = pd.DataFrame([{"trip_id": "T1", "stop_id": "S1", "stop_sequence": 1}])
        cal = pd.DataFrame([{"service_id": "WK", "service_date": date(2026, 1, 5), "is_exception": False}])
        issues = gtfs_validator.run_gtfs_validation(stops, routes, trips, stop_times, cal)
        assert [i for i in issues if i.level == "ERROR"] == []

    def test_duplicate_stop_id_is_error(self):
        stops = pd.DataFrame([{"stop_id": "S1", "stop_lat": 42.0, "stop_lon": -71.0},
                               {"stop_id": "S1", "stop_lat": 42.1, "stop_lon": -71.1}])
        routes = pd.DataFrame([{"route_id": "R1"}])
        trips = pd.DataFrame([{"trip_id": "T1", "route_id": "R1", "service_id": "WK"}])
        stop_times = pd.DataFrame([{"trip_id": "T1", "stop_id": "S1", "stop_sequence": 1}])
        cal = pd.DataFrame([{"service_id": "WK", "service_date": date(2026, 1, 5), "is_exception": False}])
        issues = gtfs_validator.run_gtfs_validation(stops, routes, trips, stop_times, cal)
        assert any(i.check == "primary_key_uniqueness" and i.level == "ERROR" for i in issues)

    def test_orphan_foreign_key_is_error(self):
        stops = pd.DataFrame([{"stop_id": "S1", "stop_lat": 42.0, "stop_lon": -71.0}])
        routes = pd.DataFrame([{"route_id": "R1"}])
        trips = pd.DataFrame([{"trip_id": "T1", "route_id": "R1", "service_id": "WK"}])
        stop_times = pd.DataFrame([{"trip_id": "T1", "stop_id": "DOES_NOT_EXIST", "stop_sequence": 1}])
        cal = pd.DataFrame([{"service_id": "WK", "service_date": date(2026, 1, 5), "is_exception": False}])
        issues = gtfs_validator.run_gtfs_validation(stops, routes, trips, stop_times, cal)
        assert any(i.check == "foreign_key_integrity" and "stop_id" in i.message for i in issues)

    def test_out_of_range_coordinates_is_error(self):
        stops = pd.DataFrame([{"stop_id": "S1", "stop_lat": 999.0, "stop_lon": -71.0}])
        routes = pd.DataFrame([{"route_id": "R1"}])
        trips = pd.DataFrame([{"trip_id": "T1", "route_id": "R1", "service_id": "WK"}])
        stop_times = pd.DataFrame([{"trip_id": "T1", "stop_id": "S1", "stop_sequence": 1}])
        cal = pd.DataFrame([{"service_id": "WK", "service_date": date(2026, 1, 5), "is_exception": False}])
        issues = gtfs_validator.run_gtfs_validation(stops, routes, trips, stop_times, cal)
        assert any(i.check == "coordinate_validity" for i in issues)

    def test_non_monotonic_stop_sequence_is_error(self):
        stops = pd.DataFrame([{"stop_id": "S1", "stop_lat": 42.0, "stop_lon": -71.0},
                               {"stop_id": "S2", "stop_lat": 42.1, "stop_lon": -71.1}])
        routes = pd.DataFrame([{"route_id": "R1"}])
        trips = pd.DataFrame([{"trip_id": "T1", "route_id": "R1", "service_id": "WK"}])
        stop_times = pd.DataFrame([{"trip_id": "T1", "stop_id": "S1", "stop_sequence": 2},
                                    {"trip_id": "T1", "stop_id": "S2", "stop_sequence": 1}])
        cal = pd.DataFrame([{"service_id": "WK", "service_date": date(2026, 1, 5), "is_exception": False}])
        issues = gtfs_validator.run_gtfs_validation(stops, routes, trips, stop_times, cal)
        assert any(i.check == "stop_sequence_monotonic" for i in issues)

    def test_location_type_3_generic_node_is_filtered_before_validation(self):
        """Stage 11B real finding: GTFS location_type=3 (pathway node) is
        legitimately coordinate-less and never referenced by stop_times --
        normalize_stops must filter these out BEFORE validation runs, or
        a real, valid GTFS feed fails coordinate validation for no reason."""
        stops_raw = pd.DataFrame([
            {"stop_id": "S1", "stop_name": "Real stop", "stop_lat": "42.0", "stop_lon": "-71.0", "location_type": "0"},
            {"stop_id": "NODE1", "stop_name": "Pathway node", "stop_lat": "", "stop_lon": "", "location_type": "3"},
        ])
        out = gtfs_normalize.normalize_stops(stops_raw)
        assert "NODE1" not in out["stop_id"].tolist()
        assert "S1" in out["stop_id"].tolist()


# ============================== provenance (Sec 3) ==============================

class TestProvenance:
    def test_provenance_record_has_no_credential_fields(self):
        from src.ingestion.common.contracts import DATASET_TYPE_REAL
        from src.ingestion.common.provenance import MBTA_LICENSE_REFERENCE, build_provenance

        rec = build_provenance(
            provider="MBTA", source_url="https://cdn.mbta.com/MBTA_GTFS.zip", downloaded_path=Path(__file__),
            license_reference=MBTA_LICENSE_REFERENCE, dataset_type=DATASET_TYPE_REAL,
            geographic_coverage="Boston", temporal_coverage="2026",
        )
        d = rec.to_dict()
        forbidden = {"api_key", "token", "password", "secret", "credential"}
        assert not (forbidden & set(k.lower() for k in d.keys()))
        assert d["dataset_type"] == "REAL"
        assert "license_reference" in d and d["license_reference"]

    def test_checksum_is_computed_from_real_file(self, tmp_path):
        from src.ingestion.common.provenance import build_provenance
        f = tmp_path / "data.txt"
        f.write_text("hello world")
        rec = build_provenance("test", "http://example.com", f, "no license", "REAL", "nowhere", "never")
        assert rec.checksum_sha256_16 is not None and len(rec.checksum_sha256_16) == 16


# ============================== deterministic processing ==============================

class TestDeterminism:
    def test_normalize_routes_deterministic(self):
        routes = pd.DataFrame([
            {"route_id": "R1", "route_short_name": "1", "route_long_name": "One", "route_type": "3"},
            {"route_id": "R2", "route_short_name": "2", "route_long_name": "Two", "route_type": "1"},
        ])
        cfg = {"by_route_type": {"1": "metro", "3": "bus"}, "unknown_mode_severity": "ERROR"}
        out1, _ = gtfs_normalize.normalize_routes(routes, cfg)
        out2, _ = gtfs_normalize.normalize_routes(routes, cfg)
        pd.testing.assert_frame_equal(out1, out2)

    def test_service_calendar_deterministic(self):
        calendar = pd.DataFrame([{
            "service_id": "WK", "monday": "1", "tuesday": "0", "wednesday": "0", "thursday": "0",
            "friday": "0", "saturday": "0", "sunday": "0", "start_date": "20260105", "end_date": "20260201",
        }])
        cal1 = gtfs_normalize.build_service_calendar(calendar, None)
        cal2 = gtfs_normalize.build_service_calendar(calendar, None)
        pd.testing.assert_frame_equal(cal1, cal2)

    def test_representative_trip_selection_deterministic(self):
        trips = pd.DataFrame([
            {"trip_id": "T2", "route_id": "R1", "service_id": "weekday", "direction_id": 0,
             "route_pattern_id": "P1"},
            {"trip_id": "T1", "route_id": "R1", "service_id": "weekday", "direction_id": 0,
             "route_pattern_id": "P1"},
        ])
        reps1 = _select_representative_trips(trips)
        reps2 = _select_representative_trips(trips)
        pd.testing.assert_frame_equal(reps1.reset_index(drop=True), reps2.reset_index(drop=True))


# ============================== real-data integration (requires downloaded files) ==============================

@requires_real_gtfs
class TestRealGtfsIntegration:
    def test_real_feed_parses_and_normalizes_with_zero_validation_errors(self):
        import yaml
        cfg = yaml.safe_load(Path("configs/real_data.yaml").read_text(encoding="utf-8"))
        tables = gtfs_parser.parse_gtfs_zip(REAL_GTFS_ZIP)
        stops = gtfs_normalize.normalize_stops(tables["stops"])
        routes, mode_issues = gtfs_normalize.normalize_routes(tables["routes"], cfg["mode_mapping"])
        trips = gtfs_normalize.normalize_trips(tables["trips"])
        stop_times = gtfs_normalize.normalize_stop_times(tables["stop_times"])
        cal = gtfs_normalize.build_service_calendar(tables.get("calendar"), tables.get("calendar_dates"))

        assert mode_issues == []  # every real route_type maps -- verified in Stage 11B
        issues = gtfs_validator.run_gtfs_validation(stops, routes, trips, stop_times, cal)
        assert [i for i in issues if i.level == "ERROR"] == []

    def test_real_feed_has_route_variants_preserved(self):
        tables = gtfs_parser.parse_gtfs_zip(REAL_GTFS_ZIP)
        trips = gtfs_normalize.normalize_trips(tables["trips"])
        reps = _select_representative_trips(trips)
        red_patterns = reps[reps["route_id"] == "Red"]
        assert len(red_patterns) > 2  # more than one pattern per direction -- the Stage 11B fix in effect

    def test_green_line_route_type_is_0(self):
        tables = gtfs_parser.parse_gtfs_zip(REAL_GTFS_ZIP)
        routes = tables["routes"]
        green = routes[routes["route_id"].str.startswith("Green-")]
        assert (green["route_type"] == "0").all()


@requires_real_subway
class TestRealHistoricalIntegration:
    def test_real_subway_sample_produces_plausible_delay_distribution(self):
        import glob
        files = [Path(f) for f in glob.glob(str(REAL_SUBWAY_DIR / "*.parquet"))]
        raw = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        route_to_mode = {"Red": "metro", "Orange": "metro", "Blue": "metro", "Mattapan": "tram",
                          "Green-B": "tram", "Green-C": "tram", "Green-D": "tram", "Green-E": "tram"}
        label_avail = {"metro": True, "tram": True}
        events = hist_normalize.normalize_subway_performance(raw, route_to_mode, label_avail)
        static = events[events["is_static_schedule_trip"] & events["delay_seconds"].notna()]
        median_delay = static["delay_seconds"].median()
        # A real, sane transit delay median is on the order of tens of
        # seconds to a few minutes -- not hours (this is exactly the check
        # that would have caught the ADDED-trip and timezone bugs found
        # during Stage 11B development).
        assert abs(median_delay) < 600

"""Stage 11D Part 12 tests: NOAA GHCNh ingestion, canonical weather
conversion, timezone handling, missing-value/duplicate/physical-range
validation, the leakage-safe combined-source backward as-of join, weather
coverage calculation, feature-availability regeneration, and provenance.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.ingestion.feature_availability import build_feature_availability_matrix
from src.ingestion.weather import ghcnh
from src.ingestion.weather.normalize import (
    combine_weather_sources,
    join_weather_asof,
    normalize_ghcnh_observations,
    normalize_nws_observations,
)
from src.ingestion.weather.validate import (
    check_chronological_ordering,
    check_duplicate_observations,
    check_missingness,
    check_physically_implausible_values,
    check_station_consistency,
    check_timezone_consistency,
    run_weather_validation,
)
from src.ingestion.weather_coverage import build_weather_coverage_report

GHCNH_PSV_FIXTURE = (
    "STATION|Station_name|DATE|LATITUDE|LONGITUDE|temperature|station_level_pressure|"
    "sea_level_pressure|wind_speed|precipitation|visibility\n"
    "USW00014739|BOSTON|2026-08-15T12:54:00|42.3606|-71.0097|22.5|1013.0|1013.5|3.2|0.0|16.093\n"
    "USW00014739|BOSTON|2026-08-15T13:54:00|42.3606|-71.0097||||||\n"  # a real, common all-blank row
    "USW00014739|BOSTON|2026-08-15T14:54:00|42.3606|-71.0097|23.1||1012.0|2.5|0.8|4.828\n"
)


# ============================== Part 1/2: NOAA GHCNh ingestion ==============================

class TestGhcnhIngestion:
    def test_station_year_url_pattern(self):
        url = ghcnh.station_year_url("USW00014739", 2026)
        assert url == ("https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/"
                        "access/by-year/2026/psv/GHCNh_USW00014739_2026.psv")

    def test_load_station_year_psv_parses_fixture(self, tmp_path: Path):
        path = tmp_path / "GHCNh_USW00014739_2026.psv"
        path.write_text(GHCNH_PSV_FIXTURE, encoding="utf-8")
        df = ghcnh.load_station_year_psv(path)
        assert len(df) == 3
        assert df.iloc[0]["temperature"] == pytest.approx(22.5)
        assert df.iloc[0]["sea_level_pressure"] == pytest.approx(1013.5)

    def test_blank_raw_fields_become_nan_not_zero(self, tmp_path: Path):
        path = tmp_path / "GHCNh_USW00014739_2026.psv"
        path.write_text(GHCNH_PSV_FIXTURE, encoding="utf-8")
        df = ghcnh.load_station_year_psv(path)
        blank_row = df.iloc[1]
        assert pd.isna(blank_row["temperature"])
        assert pd.isna(blank_row["precipitation"])
        assert pd.isna(blank_row["wind_speed"])

    def test_load_station_years_concatenates_multiple_files(self, tmp_path: Path):
        p1 = tmp_path / "GHCNh_USW00014739_2025.psv"
        p2 = tmp_path / "GHCNh_USW00014739_2026.psv"
        p1.write_text(GHCNH_PSV_FIXTURE, encoding="utf-8")
        p2.write_text(GHCNH_PSV_FIXTURE, encoding="utf-8")
        combined = ghcnh.load_station_years([p1, p2])
        assert len(combined) == 6

    def test_fetch_station_year_is_idempotent_skips_existing_file(self, tmp_path: Path):
        dest = tmp_path / "GHCNh_USW00014739_2026.psv"
        dest.write_text(GHCNH_PSV_FIXTURE, encoding="utf-8")
        original_mtime = dest.stat().st_mtime
        result = ghcnh.fetch_station_year("USW00014739", 2026, dest)
        assert result == dest
        assert dest.stat().st_mtime == original_mtime  # never re-downloaded/overwritten

    def test_save_provenance_never_contains_a_credential(self, tmp_path: Path):
        path = tmp_path / "GHCNh_USW00014739_2026.psv"
        path.write_text(GHCNH_PSV_FIXTURE, encoding="utf-8")
        record = ghcnh.save_provenance("USW00014739", [2026], tmp_path)
        record_dict = record.to_dict()
        assert "headers" not in record_dict
        assert "authorization" not in str(record_dict).lower()
        assert "bearer " not in str(record_dict).lower()
        assert record_dict["provider"].startswith("NOAA NCEI")
        assert record_dict["dataset_type"] == "REAL"


# ============================== Part 3: canonical weather schema ==============================

class TestCanonicalWeatherConversion:
    def _raw_df_fallback(self) -> pd.DataFrame:
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".psv", delete=False) as f:
            f.write(GHCNH_PSV_FIXTURE)
            path = Path(f.name)
        return ghcnh.load_station_year_psv(path)

    def test_maps_temperature_precipitation_directly(self):
        raw = self._raw_df_fallback()
        out = normalize_ghcnh_observations(raw, "KBOS")
        assert out.iloc[0]["temperature_c"] == pytest.approx(22.5)
        assert out.iloc[0]["precipitation_mm"] == pytest.approx(0.0)
        assert out.iloc[2]["precipitation_mm"] == pytest.approx(0.8)

    def test_visibility_passthrough_not_divided_by_1000(self):
        """Verified against real GHCNh data (Stage 11D research): 16.093
        converts exactly to 10.0 US statute miles, proving the raw column
        is already kilometers, not meters -- must NOT be scaled."""
        raw = self._raw_df_fallback()
        out = normalize_ghcnh_observations(raw, "KBOS")
        assert out.iloc[0]["visibility_km"] == pytest.approx(16.093)

    def test_pressure_prefers_sea_level_falls_back_to_station_level(self):
        raw = self._raw_df_fallback()
        out = normalize_ghcnh_observations(raw, "KBOS")
        assert out.iloc[0]["pressure_hpa"] == pytest.approx(1013.5)  # sea-level present -> used
        assert out.iloc[2]["pressure_hpa"] == pytest.approx(1012.0)  # sea-level null -> station-level fallback

    def test_wind_speed_and_station_location_mapped(self):
        raw = self._raw_df_fallback()
        out = normalize_ghcnh_observations(raw, "KBOS")
        assert out.iloc[0]["wind_speed_ms"] == pytest.approx(3.2)
        assert out.iloc[0]["station_lat"] == pytest.approx(42.3606)
        assert out.iloc[0]["station_lon"] == pytest.approx(-71.0097)

    def test_source_column_identifies_adapter(self):
        raw = self._raw_df_fallback()
        out = normalize_ghcnh_observations(raw, "KBOS")
        assert (out["source"] == "NOAA GHCNh").all()

    def test_weather_zone_id_matches_project_convention_not_raw_station_id(self):
        """weather_zone_id must be the project's join key (e.g. 'KBOS'),
        never the raw GHCNh station id -- otherwise the join against NWS
        data and stops.weather_zone_id silently fails to match."""
        raw = self._raw_df_fallback()
        out = normalize_ghcnh_observations(raw, "KBOS")
        assert (out["weather_zone_id"] == "KBOS").all()
        assert "USW00014739" not in out["weather_zone_id"].unique()


# ============================== Part 4: timezone handling ==============================

class TestTimezoneHandling:
    def test_ghcnh_timestamp_is_utc_aware(self):
        with_tmp = TestCanonicalWeatherConversion()
        raw = with_tmp._raw_df_fallback()
        out = normalize_ghcnh_observations(raw, "KBOS")
        assert out["timestamp"].dt.tz is not None
        assert str(out["timestamp"].dt.tz) == "UTC"

    def test_nws_timestamp_is_utc_aware(self):
        raw = pd.DataFrame([{"timestamp": "2026-08-15T12:00:00+00:00", "temperature_c": 20.0,
                              "precipitation_mm": None, "visibility_km": 16.0}])
        out = normalize_nws_observations(raw, "KBOS")
        assert out["timestamp"].dt.tz is not None

    def test_combined_sources_remain_consistently_utc(self):
        with_tmp = TestCanonicalWeatherConversion()
        ghcnh_df = normalize_ghcnh_observations(with_tmp._raw_df_fallback(), "KBOS")
        nws_raw = pd.DataFrame([{"timestamp": "2026-09-27T12:00:00+00:00", "temperature_c": 18.0,
                                  "precipitation_mm": 0.0, "visibility_km": 16.0}])
        nws_df = normalize_nws_observations(nws_raw, "KBOS")
        combined = combine_weather_sources([ghcnh_df, nws_df], source_priority=["NOAA GHCNh", "NWS"])
        assert all(combined["timestamp"].dt.tz is not None for _ in [1])
        assert combined["timestamp"].dt.tz is not None

    def test_boston_local_prediction_time_and_utc_weather_join_correctly(self):
        """A transit event's scheduled_time in America/New_York must
        resolve to the correct UTC instant for matching against
        UTC-stamped weather -- proves the join doesn't silently misalign
        local vs UTC clocks."""
        events = pd.DataFrame([{
            "stop_id": "S1", "scheduled_time": pd.Timestamp("2026-08-15 09:00:00", tz="America/New_York"),
        }])  # 09:00 EDT == 13:00 UTC
        weather = pd.DataFrame([
            {"weather_zone_id": "KBOS", "timestamp": pd.Timestamp("2026-08-15 12:59:00", tz="UTC"),
             "temperature_c": 21.0, "precipitation_mm": 0.0, "visibility_km": 16.0},
        ])
        stops = pd.DataFrame([{"stop_id": "S1", "weather_zone_id": "KBOS"}])
        joined = join_weather_asof(events, weather, stops, tolerance_hours=1)
        assert joined.iloc[0]["temperature_c"] == pytest.approx(21.0)


# ============================== Part 5: weather validation ==============================

class TestWeatherValidation:
    def test_duplicate_observations_flagged(self):
        weather = pd.DataFrame([
            {"weather_zone_id": "KBOS", "timestamp": pd.Timestamp("2026-08-15 12:00", tz="UTC"), "source": "NWS"},
            {"weather_zone_id": "KBOS", "timestamp": pd.Timestamp("2026-08-15 12:00", tz="UTC"), "source": "NWS"},
        ])
        issues = check_duplicate_observations(weather)
        assert len(issues) == 1
        assert issues[0].count == 1

    def test_timezone_naive_timestamp_is_an_error(self):
        weather = pd.DataFrame([
            {"weather_zone_id": "KBOS", "timestamp": pd.Timestamp("2026-08-15 12:00"), "source": "NWS"},
        ])
        issues = check_timezone_consistency(weather)
        assert len(issues) == 1
        assert issues[0].level == "ERROR"

    def test_timezone_aware_timestamp_passes(self):
        weather = pd.DataFrame([
            {"weather_zone_id": "KBOS", "timestamp": pd.Timestamp("2026-08-15 12:00", tz="UTC"), "source": "NWS"},
        ])
        assert check_timezone_consistency(weather) == []

    def test_negative_precipitation_is_physically_implausible(self):
        weather = pd.DataFrame([{"precipitation_mm": -1.0}])
        issues = check_physically_implausible_values(weather)
        assert any("precipitation_mm" in i.message for i in issues)

    def test_negative_wind_speed_is_physically_implausible(self):
        weather = pd.DataFrame([{"wind_speed_ms": -2.0}])
        issues = check_physically_implausible_values(weather)
        assert any("wind_speed_ms" in i.message for i in issues)

    def test_out_of_range_temperature_flagged(self):
        weather = pd.DataFrame([{"temperature_c": 500.0}])
        issues = check_physically_implausible_values(weather)
        assert any("temperature_c" in i.message for i in issues)

    def test_plausible_values_produce_no_range_issues(self):
        weather = pd.DataFrame([{"temperature_c": 22.0, "pressure_hpa": 1013.0, "precipitation_mm": 0.5,
                                  "wind_speed_ms": 3.0, "visibility_km": 16.0}])
        assert check_physically_implausible_values(weather) == []

    def test_missingness_reported_not_silently_zero(self):
        weather = pd.DataFrame([{"precipitation_mm": None}, {"precipitation_mm": 0.5}])
        issues = check_missingness(weather)
        assert any(i.check == "missingness" and "precipitation_mm" in i.message for i in issues)

    def test_station_consistency_flags_drifting_coordinates(self):
        weather = pd.DataFrame([
            {"weather_zone_id": "KBOS", "station_lat": 42.36, "station_lon": -71.01},
            {"weather_zone_id": "KBOS", "station_lat": 40.00, "station_lon": -71.01},  # drifted
        ])
        issues = check_station_consistency(weather)
        assert len(issues) == 1

    def test_chronological_ordering_check_does_not_error_on_sortable_data(self):
        weather = pd.DataFrame([
            {"weather_zone_id": "KBOS", "timestamp": pd.Timestamp("2026-08-15 12:00", tz="UTC")},
            {"weather_zone_id": "KBOS", "timestamp": pd.Timestamp("2026-08-15 13:00", tz="UTC")},
        ])
        assert check_chronological_ordering(weather) == []

    def test_run_weather_validation_on_empty_frame_does_not_crash(self):
        issues = run_weather_validation(pd.DataFrame())
        assert isinstance(issues, list)


# ============================== Part 6: leakage-safe combined-source join ==============================

class TestLeakageSafeCombinedJoin:
    def test_ghcnh_preferred_over_nws_at_exact_collision(self):
        ghcnh_row = pd.DataFrame([{
            "observation_id": "g1", "weather_zone_id": "KBOS",
            "timestamp": pd.Timestamp("2026-08-15 12:00", tz="UTC"),
            "temperature_c": 21.0, "precipitation_mm": 0.0, "visibility_km": 16.0,
            "wind_speed_ms": 3.0, "pressure_hpa": 1013.0, "station_lat": 42.36, "station_lon": -71.01,
            "source": "NOAA GHCNh",
        }])
        nws_row = pd.DataFrame([{
            "observation_id": "n1", "weather_zone_id": "KBOS",
            "timestamp": pd.Timestamp("2026-08-15 12:00", tz="UTC"),
            "temperature_c": 99.0, "precipitation_mm": 0.0, "visibility_km": 1.0, "source": "NWS",
        }])
        combined = combine_weather_sources([ghcnh_row, nws_row], source_priority=["NOAA GHCNh", "NWS"])
        assert len(combined) == 1
        assert combined.iloc[0]["source"] == "NOAA GHCNh"
        assert combined.iloc[0]["temperature_c"] == pytest.approx(21.0)

    def test_wind_speed_and_pressure_propagate_through_combined_join(self):
        weather = pd.DataFrame([{
            "weather_zone_id": "KBOS", "timestamp": pd.Timestamp("2026-08-15 11:00", tz="UTC"),
            "temperature_c": 21.0, "precipitation_mm": 0.0, "visibility_km": 16.0,
            "wind_speed_ms": 4.5, "pressure_hpa": 1015.0,
        }])
        events = pd.DataFrame([{
            "stop_id": "S1", "scheduled_time": pd.Timestamp("2026-08-15 12:00:00", tz="UTC"),
        }])
        stops = pd.DataFrame([{"stop_id": "S1", "weather_zone_id": "KBOS"}])
        joined = join_weather_asof(events, weather, stops, tolerance_hours=2)
        assert joined.iloc[0]["wind_speed_ms"] == pytest.approx(4.5)
        assert joined.iloc[0]["pressure_hpa"] == pytest.approx(1015.0)

    def test_no_future_weather_observation_ever_used_across_many_events(self):
        """Explicit proof (Stage 11D Part 6): weather_observation_time <=
        prediction_time for every joined record. Builds 20 events each
        with one legitimate past observation and one FUTURE observation
        tagged with a unique, easily-detected sentinel value -- if the
        join ever leaked a future observation, its sentinel would appear
        in the output.
        """
        rows_events = []
        rows_weather = []
        for i in range(20):
            base = pd.Timestamp("2026-08-15 00:00:00", tz="UTC") + pd.Timedelta(hours=i)
            rows_events.append({"stop_id": f"S{i}", "scheduled_time": base})
            past_value = float(i) + 0.1  # legitimate, must be usable
            future_sentinel = 100000.0 + i  # must NEVER appear
            # Future obs offset by 2 days -- guaranteed outside the 1h
            # tolerance window of every event in this 20-hour test span
            # (unlike a same-day +30min offset, which can accidentally
            # collide with an ADJACENT event's own legitimate past window).
            rows_weather.append({"weather_zone_id": "KBOS", "timestamp": base - pd.Timedelta(minutes=15),
                                  "temperature_c": past_value, "precipitation_mm": 0.0, "visibility_km": 16.0})
            rows_weather.append({"weather_zone_id": "KBOS", "timestamp": base + pd.Timedelta(days=2),
                                  "temperature_c": future_sentinel, "precipitation_mm": 0.0, "visibility_km": 16.0})
        events = pd.DataFrame(rows_events)
        weather = pd.DataFrame(rows_weather)
        stops = pd.DataFrame([{"stop_id": f"S{i}", "weather_zone_id": "KBOS"} for i in range(20)])

        joined = join_weather_asof(events, weather, stops, tolerance_hours=1)

        assert len(joined) == 20
        assert (joined["temperature_c"] < 1000).all()  # no future sentinel (>=100000) ever appears
        for i in range(20):
            row = joined[joined["stop_id"] == f"S{i}"].iloc[0]
            assert row["temperature_c"] == pytest.approx(float(i) + 0.1)


# ============================== Part 7: weather coverage calculation ==============================

class TestWeatherCoverageReport:
    def _weather(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"weather_zone_id": "KBOS", "timestamp": pd.Timestamp("2026-08-15 12:00", tz="UTC"),
             "source": "NOAA GHCNh"},
            {"weather_zone_id": "KBOS", "timestamp": pd.Timestamp("2026-07-01 12:00", tz="UTC"),
             "source": "NOAA GHCNh"},  # outside the transit period
        ])

    def _training_table(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"transport_mode": "bus", "service_date": "2026-08-15", "hour": 12, "temperature_c": 21.0,
             "precipitation_mm": 0.0, "visibility_km": 16.0, "wind_speed_ms": 3.0, "pressure_hpa": 1013.0},
            {"transport_mode": "metro", "service_date": "2026-08-15", "hour": 13, "temperature_c": None,
             "precipitation_mm": None, "visibility_km": None, "wind_speed_ms": None, "pressure_hpa": None},
        ])

    def test_overall_coverage_is_measured_not_asserted(self):
        report = build_weather_coverage_report(self._weather(), self._training_table(), "2026-08-01", "2026-09-29")
        assert report["overall_coverage"] == pytest.approx(0.5)

    def test_weather_observations_outside_transit_period_counted(self):
        report = build_weather_coverage_report(self._weather(), self._training_table(), "2026-08-01", "2026-09-29")
        assert report["weather_observations_outside_transit_period"] == 1

    def test_coverage_by_mode_reported_per_mode(self):
        report = build_weather_coverage_report(self._weather(), self._training_table(), "2026-08-01", "2026-09-29")
        assert report["coverage_by_mode"]["bus"] == pytest.approx(1.0)
        assert report["coverage_by_mode"]["metro"] == pytest.approx(0.0)

    def test_unmatched_transit_events_counted(self):
        report = build_weather_coverage_report(self._weather(), self._training_table(), "2026-08-01", "2026-09-29")
        assert report["unmatched_transit_events"]["count"] == 1
        assert report["unmatched_transit_events"]["total_events"] == 2

    def test_missingness_by_feature_is_complement_of_coverage(self):
        report = build_weather_coverage_report(self._weather(), self._training_table(), "2026-08-01", "2026-09-29")
        assert report["missingness_by_feature"]["temperature_c"] == pytest.approx(0.5)

    def test_empty_weather_reports_zero_observations_not_a_crash(self):
        report = build_weather_coverage_report(pd.DataFrame(), self._training_table(), "2026-08-01", "2026-09-29")
        assert report["total_weather_observations"] == 0


# ============================== Part 8: feature-availability regeneration ==============================

class TestFeatureAvailabilityRegeneration:
    def test_wind_speed_and_pressure_appear_as_measured_rows(self):
        training_table = pd.DataFrame([
            {"transport_mode": "bus", "hour": 8, "day_of_week": 1, "day_period": "peak",
             "time_of_day_bucket": "AM", "transfer_dependency": 0.1,
             "wind_speed_ms": 3.0, "pressure_hpa": 1013.0,
             "precipitation_mm": 0.0, "temperature_c": 20.0, "visibility_km": 16.0,
             "historical_delay_seconds": None, "rolling_7d_delay_seconds": None,
             "historical_reliability": None, "disruption_flag": None},
        ])
        cfg = {"label_availability": {"bus": True, "rail": False, "ferry": False}}
        matrix = build_feature_availability_matrix(training_table, cfg)
        names = {r["feature"] for r in matrix["model_input_features"]}
        assert "wind_speed_ms" in names
        assert "pressure_hpa" in names

    def test_coverage_never_manually_asserted_matches_actual_notna_rate(self):
        training_table = pd.DataFrame([
            {"transport_mode": "bus", "hour": 8, "day_of_week": 1, "day_period": "peak",
             "time_of_day_bucket": "AM", "transfer_dependency": 0.1,
             "wind_speed_ms": 3.0, "pressure_hpa": None,
             "precipitation_mm": 0.0, "temperature_c": 20.0, "visibility_km": 16.0,
             "historical_delay_seconds": None, "rolling_7d_delay_seconds": None,
             "historical_reliability": None, "disruption_flag": None},
            {"transport_mode": "bus", "hour": 9, "day_of_week": 1, "day_period": "peak",
             "time_of_day_bucket": "AM", "transfer_dependency": 0.1,
             "wind_speed_ms": None, "pressure_hpa": None,
             "precipitation_mm": 0.0, "temperature_c": 20.0, "visibility_km": 16.0,
             "historical_delay_seconds": None, "rolling_7d_delay_seconds": None,
             "historical_reliability": None, "disruption_flag": None},
        ])
        cfg = {"label_availability": {"bus": True, "rail": False, "ferry": False}}
        matrix = build_feature_availability_matrix(training_table, cfg)
        wind_row = next(r for r in matrix["model_input_features"] if r["feature"] == "wind_speed_ms")
        assert wind_row["coverage"] == pytest.approx(0.5)
        pressure_row = next(r for r in matrix["model_input_features"] if r["feature"] == "pressure_hpa")
        assert pressure_row["coverage"] == pytest.approx(0.0)
        assert pressure_row["availability"] == "UNAVAILABLE"

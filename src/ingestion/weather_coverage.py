"""Stage 11D Part 7: post-integration weather coverage analysis. Every
number here is measured directly from the combined weather table and the
joined training table -- never asserted, never a hard-coded pass/fail
threshold by itself (Part 7's explicit instruction: "the report must
contain measured values").
"""
from __future__ import annotations

import pandas as pd

WEATHER_FEATURE_COLUMNS = ["precipitation_mm", "temperature_c", "visibility_km", "wind_speed_ms", "pressure_hpa"]


def _rate(series: pd.Series) -> float | None:
    return float(series.notna().mean()) if len(series) else None


def build_weather_coverage_report(
    weather: pd.DataFrame, training_table: pd.DataFrame,
    transit_min_date: str, transit_max_date: str,
) -> dict:
    report: dict = {
        "transit_period": {"min_date": str(transit_min_date), "max_date": str(transit_max_date)},
        "total_weather_observations": int(len(weather)),
    }

    if weather.empty:
        report["date_range"] = None
        report["station_coverage"] = {}
        report["weather_observations_outside_transit_period"] = 0
    else:
        report["date_range"] = [str(weather["timestamp"].min()), str(weather["timestamp"].max())]
        station_rows = []
        for zone, group in weather.groupby("weather_zone_id"):
            for source, src_group in group.groupby("source"):
                station_rows.append({
                    "weather_zone_id": str(zone), "source": str(source),
                    "n_observations": int(len(src_group)),
                    "date_range": [str(src_group["timestamp"].min()), str(src_group["timestamp"].max())],
                })
        report["station_coverage"] = station_rows

        transit_start = pd.Timestamp(transit_min_date, tz="UTC")
        transit_end = pd.Timestamp(transit_max_date, tz="UTC") + pd.Timedelta(days=1)
        outside = weather[(weather["timestamp"] < transit_start) | (weather["timestamp"] >= transit_end)]
        report["weather_observations_outside_transit_period"] = int(len(outside))
        report["weather_observations_outside_transit_period_by_source"] = {
            str(src): int(n) for src, n in outside.groupby("source").size().items()
        } if len(outside) else {}

    if training_table.empty or "temperature_c" not in training_table.columns:
        report["overall_coverage"] = None
        return report

    report["overall_coverage"] = _rate(training_table["temperature_c"])
    report["coverage_by_feature"] = {
        col: _rate(training_table[col]) for col in WEATHER_FEATURE_COLUMNS if col in training_table.columns
    }
    report["missingness_by_feature"] = {
        col: 1.0 - _rate(training_table[col]) for col in WEATHER_FEATURE_COLUMNS
        if col in training_table.columns and _rate(training_table[col]) is not None
    }

    if "transport_mode" in training_table.columns:
        report["coverage_by_mode"] = {
            str(mode): _rate(group["temperature_c"]) for mode, group in training_table.groupby("transport_mode")
        }

    if "service_date" in training_table.columns:
        report["coverage_by_date"] = {
            str(date): _rate(group["temperature_c"]) for date, group in training_table.groupby("service_date")
        }

    if "hour" in training_table.columns:
        report["coverage_by_hour"] = {
            int(hour): _rate(group["temperature_c"]) for hour, group in training_table.groupby("hour")
            if pd.notna(hour)
        }

    unmatched = training_table[training_table["temperature_c"].isna()]
    report["unmatched_transit_events"] = {
        "count": int(len(unmatched)),
        "total_events": int(len(training_table)),
        "share": float(len(unmatched) / len(training_table)) if len(training_table) else None,
    }

    return report

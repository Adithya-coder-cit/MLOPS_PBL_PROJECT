"""Stage 11B §17: the real-data validation/quality report. Every number
here is computed from the actual ingested tables -- nothing is a
placeholder or an estimate.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from src.ingestion.common.contracts import DATASET_TYPE_REAL


def build_data_quality_report(tables: dict[str, pd.DataFrame], issues: list, cfg: dict) -> dict:
    stops, routes, trips, stop_times = tables["stops"], tables["routes"], tables["trips"], tables["stop_times"]
    service_calendar, events, weather = tables["service_calendar"], tables["operational_events"], tables["weather"]

    mode_counts = routes["transport_mode"].value_counts(dropna=False).to_dict()

    label_coverage = {}
    if not events.empty:
        for mode, group in events.groupby("transport_mode"):
            label_coverage[mode] = {
                "record_count": int(len(group)),
                "label_available": bool(group["label_available"].iloc[0]) if len(group) else None,
                "actual_time_null_rate": float(group["actual_time"].isna().mean()),
                "delay_seconds_null_rate": float(group["delay_seconds"].isna().mean()),
            }

    weather_coverage = {
        "record_count": int(len(weather)),
        "temperature_null_rate": float(weather["temperature_c"].isna().mean()) if not weather.empty else None,
        "precipitation_null_rate": float(weather["precipitation_mm"].isna().mean()) if not weather.empty else None,
        "visibility_null_rate": float(weather["visibility_km"].isna().mean()) if not weather.empty else None,
        "date_range": [str(weather["timestamp"].min()), str(weather["timestamp"].max())] if not weather.empty
        else None,
    }

    return {
        "source": "MBTA / MassDOT (real)",
        "dataset_type": DATASET_TYPE_REAL,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "record_counts": {
            "stops": int(len(stops)), "routes": int(len(routes)), "trips": int(len(trips)),
            "stop_times": int(len(stop_times)), "service_calendar_rows": int(len(service_calendar)),
            "operational_events": int(len(events)),
        },
        "date_ranges": {
            "service_calendar": [str(service_calendar["service_date"].min()),
                                  str(service_calendar["service_date"].max())] if not service_calendar.empty
            else None,
            "operational_events": [str(events["service_date"].min()), str(events["service_date"].max())]
            if not events.empty else None,
        },
        "mode_counts": {str(k): int(v) for k, v in mode_counts.items()},
        "missingness": {
            "stops_missing_coords": int(stops[["stop_lat", "stop_lon"]].isna().any(axis=1).sum()),
            "trips_missing_route_pattern_id": int(trips["route_pattern_id"].isna().sum()) if
            "route_pattern_id" in trips.columns else None,
        },
        "duplicate_counts": {
            "stop_times_trip_stop_sequence": int(stop_times.duplicated(subset=["trip_id", "stop_sequence"]).sum()),
        },
        "invalid_references": [i.to_dict() for i in issues if i.check == "foreign_key_integrity"],
        "calendar_coverage": {
            "n_service_ids": int(service_calendar["service_id"].nunique()) if not service_calendar.empty else 0,
            "n_exception_rows": int(service_calendar["is_exception"].sum()) if not service_calendar.empty else 0,
        },
        "label_coverage_by_mode": label_coverage,
        "weather_coverage": weather_coverage,
        "validation_issues": [i.to_dict() for i in issues],
        "validation_summary": {
            "total": len(issues),
            "errors": sum(1 for i in issues if i.level == "ERROR"),
            "warnings": sum(1 for i in issues if i.level == "WARNING"),
        },
    }

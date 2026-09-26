"""Stage 11B §18: real-world EDA, computed from the actual ingested
canonical tables. Deliberately does NOT compare real distributions
against the synthetic generator's distributions as if they should
match -- the synthetic dataset was a development fixture, not a ground
truth the real world is expected to resemble.
"""
from __future__ import annotations

import pandas as pd


def _delay_stats(series: pd.Series) -> dict:
    s = series.dropna()
    if s.empty:
        return {"count": 0}
    return {
        "count": int(len(s)), "mean": float(s.mean()), "median": float(s.median()),
        "std": float(s.std()), "min": float(s.min()), "max": float(s.max()),
        "pct_within_5min": float((s.abs() <= 300).mean()), "pct_within_10min": float((s.abs() <= 600).mean()),
        "p25": float(s.quantile(0.25)), "p75": float(s.quantile(0.75)),
    }


def build_eda_report(tables: dict[str, pd.DataFrame], cfg: dict) -> dict:
    stops, routes, trips = tables["stops"], tables["routes"], tables["trips"]
    events, weather = tables["operational_events"], tables["weather"]

    trips_by_mode = trips.merge(routes[["route_id", "transport_mode"]], on="route_id", how="left")[
        "transport_mode"].value_counts(dropna=False).to_dict()
    routes_by_mode = routes["transport_mode"].value_counts(dropna=False).to_dict()

    stops_per_route_mode = {}
    if not trips.empty:
        merged = trips.merge(routes[["route_id", "transport_mode"]], on="route_id", how="left")
        stops_per_route_mode = merged.groupby("transport_mode")["route_id"].nunique().to_dict()

    delay_by_mode_all = {}
    delay_by_mode_static_only = {}
    delay_by_hour = {}
    delay_by_route = {}
    if not events.empty:
        for mode, group in events.groupby("transport_mode"):
            delay_by_mode_all[str(mode)] = _delay_stats(group["delay_seconds"])
            static = group[group["is_static_schedule_trip"]] if "is_static_schedule_trip" in group.columns else group
            delay_by_mode_static_only[str(mode)] = _delay_stats(static["delay_seconds"])

        events_static = events[events["is_static_schedule_trip"]] if "is_static_schedule_trip" in events.columns \
            else events
        scheduled = pd.to_datetime(events_static["scheduled_time"], utc=True, errors="coerce")
        events_static = events_static.assign(_hour=scheduled.dt.hour)
        for hour, group in events_static.groupby("_hour"):
            if pd.isna(hour):
                continue
            delay_by_hour[int(hour)] = _delay_stats(group["delay_seconds"])

        top_routes = events_static["route_id"].value_counts().head(10).index
        for route_id in top_routes:
            delay_by_route[str(route_id)] = _delay_stats(events_static.loc[events_static["route_id"] == route_id,
                                                                             "delay_seconds"])

    missingness = {
        "operational_events_actual_time_null_rate": float(events["actual_time"].isna().mean())
        if not events.empty else None,
        "operational_events_weather_temp_null_rate": float(events["temperature_c"].isna().mean())
        if "temperature_c" in events.columns and not events.empty else None,
    }

    label_availability_summary = {
        str(mode): bool(available) for mode, available in cfg["label_availability"].items()
    }

    return {
        "dataset_type": "REAL",
        "note": "Real-world distributions are reported on their own terms and are NOT compared "
                "against the synthetic generator's distributions -- the synthetic dataset was a "
                "development fixture, not a ground truth the real world should resemble.",
        "trips_by_mode": {str(k): int(v) for k, v in trips_by_mode.items()},
        "routes_by_mode": {str(k): int(v) for k, v in routes_by_mode.items()},
        "distinct_routes_with_trips_by_mode": {str(k): int(v) for k, v in stops_per_route_mode.items()},
        "n_stops": int(len(stops)),
        "service_calendar_span_days": int(
            (tables["service_calendar"]["service_date"].max() - tables["service_calendar"]["service_date"].min()
             ).days
        ) if not tables["service_calendar"].empty else None,
        "delay_distribution_by_mode_ALL_TRIPS": delay_by_mode_all,
        "delay_distribution_by_mode_STATIC_SCHEDULE_TRIPS_ONLY": delay_by_mode_static_only,
        "delay_note": "ALL_TRIPS includes GTFS-RT-injected ADDED-/NONREV- trip_ids, whose "
                      "'scheduled' time is a real-time placeholder, not a genuine published "
                      "schedule entry (Stage 11B finding: these accounted for 95% of |delay|>1hr "
                      "outliers in the verified real sample) -- STATIC_SCHEDULE_TRIPS_ONLY excludes "
                      "them and is the more trustworthy distribution for label-policy decisions.",
        "delay_by_hour_STATIC_SCHEDULE_TRIPS_ONLY": delay_by_hour,
        "delay_by_top10_route_STATIC_SCHEDULE_TRIPS_ONLY": delay_by_route,
        "missingness": missingness,
        "label_availability_by_mode": label_availability_summary,
        "temporal_coverage": {
            "operational_events": [str(events["service_date"].min()), str(events["service_date"].max())]
            if not events.empty else None,
            "weather": [str(weather["timestamp"].min()), str(weather["timestamp"].max())]
            if not weather.empty else None,
            "coverage_gap_note": "The weather sample's earliest coverage does not reach back as far "
                                  "as the subway historical sample's earliest dates in this bounded "
                                  "Stage 11B ingestion -- see weather_coverage in the data quality "
                                  "report for the exact overlap.",
        },
    }

"""Stage 11B/11C §18/L: real-world EDA, computed from the actual
ingested canonical tables. Deliberately does NOT compare real
distributions against the synthetic generator's distributions as if
they should match -- the synthetic dataset was a development fixture,
not a ground truth the real world is expected to resemble. Every
relationship reported below (e.g. delay vs. weather) is observational,
not a causal claim.
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


def _rate(series: pd.Series) -> float | None:
    s = series.dropna()
    return float(s.mean()) if len(s) else None


def build_eda_report(tables: dict[str, pd.DataFrame], cfg: dict, training_table: pd.DataFrame | None = None) -> dict:
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
        # Memory: only these columns are read below -- projecting to them
        # before grouping avoids holding a full-width (incl. large_string
        # trip_id/stop_id) copy per group/filter on a 20M+-row table.
        _eda_cols = [c for c in ("transport_mode", "delay_seconds", "route_id",
                                  "scheduled_time", "is_static_schedule_trip") if c in events.columns]
        events_slim = events[_eda_cols]

        for mode, group in events_slim.groupby("transport_mode"):
            delay_by_mode_all[str(mode)] = _delay_stats(group["delay_seconds"])
            static = group[group["is_static_schedule_trip"]] if "is_static_schedule_trip" in group.columns else group
            delay_by_mode_static_only[str(mode)] = _delay_stats(static["delay_seconds"])

        events_static = events_slim[events_slim["is_static_schedule_trip"]] \
            if "is_static_schedule_trip" in events_slim.columns else events_slim
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

    report = {
        "dataset_type": "REAL",
        "note": "Real-world distributions and relationships are reported on their own terms and are "
                "NOT compared against the synthetic generator's distributions -- the synthetic "
                "dataset was a development fixture, not a ground truth the real world should "
                "resemble. All relationships below (e.g. delay vs. weather) are OBSERVATIONAL, not "
                "causal claims.",
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
                      "schedule entry (Stage 11B finding) -- STATIC_SCHEDULE_TRIPS_ONLY excludes "
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
        },
    }

    if training_table is not None and not training_table.empty:
        # No mutation happens below (.assign/.groupby/boolean-indexing all
        # return new frames) -- copying a 20M+-row table here was pure
        # memory waste, not a safety requirement.
        tt = training_table
        tt_static = tt
        scheduled = pd.to_datetime(tt_static["scheduled_time"], utc=True, errors="coerce")

        # Memory: each of the four groupbys below only reads
        # disruption_flag (+ its own grouper) -- grouping/iterating the
        # full 25-column, 23M+-row table for each one forces pandas to
        # materialize a full sorted copy per groupby, which is what
        # exhausted memory here. A slim 2-column projection is enough.
        disruption_slim = tt_static[["transport_mode", "route_id", "disruption_flag"]]

        report["disruption_rate_by_mode"] = {
            str(mode): _rate(group["disruption_flag"])
            for mode, group in disruption_slim.groupby("transport_mode")
        }
        report["disruption_rate_by_hour"] = {
            int(h): _rate(g["disruption_flag"])
            for h, g in disruption_slim[["disruption_flag"]].assign(_h=scheduled.dt.hour).groupby("_h")
            if pd.notna(h)
        }
        top10_routes = disruption_slim["route_id"].value_counts().head(10).index
        report["disruption_rate_by_route_top10"] = {
            str(r): _rate(g["disruption_flag"])
            for r, g in disruption_slim[disruption_slim["route_id"].isin(top10_routes)].groupby("route_id")
        }
        report["disruption_rate_by_day_of_week"] = {
            int(d): _rate(g["disruption_flag"])
            for d, g in disruption_slim[["disruption_flag"]].groupby(scheduled.dt.dayofweek) if pd.notna(d)
        }
        report["disruption_rate_note"] = ("NaN wherever disruption_flag is entirely null for that slice "
                                           "(label policy inactive, or the slice has no label_available rows) "
                                           "-- never treated as 0.")

        if "temperature_c" in tt.columns and tt["temperature_c"].notna().any():
            has_weather = tt[tt["temperature_c"].notna()]
            report["delay_vs_weather_OBSERVATIONAL"] = {
                "note": "Observational association only, computed over the small real window where "
                        "weather actually joined -- not a causal claim, and not representative of the "
                        "full training window given the documented weather coverage gap.",
                "n_rows_with_weather": int(len(has_weather)),
                "delay_stats_when_precip_gt_0": _delay_stats(
                    has_weather.loc[has_weather["precipitation_mm"].fillna(0) > 0, "delay_seconds"]
                ) if "precipitation_mm" in has_weather.columns else None,
                "delay_stats_when_precip_eq_0_or_null": _delay_stats(
                    has_weather.loc[has_weather["precipitation_mm"].fillna(0) == 0, "delay_seconds"]
                ) if "precipitation_mm" in has_weather.columns else None,
            }

        report["historical_feature_missingness"] = {
            col: float(tt[col].isna().mean()) for col in
            ["historical_delay_seconds", "rolling_7d_delay_seconds", "historical_reliability"]
            if col in tt.columns
        }
        report["label_coverage"] = {
            "total_rows": int(len(tt)),
            "label_available_rows": int(tt["label_available"].sum()) if "label_available" in tt.columns else None,
            "disruption_flag_non_null_rows": int(tt["disruption_flag"].notna().sum())
            if "disruption_flag" in tt.columns else None,
        }

    return report

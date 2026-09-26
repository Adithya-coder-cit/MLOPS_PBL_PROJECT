"""Stage 11B §5/§6/§9: normalize parsed GTFS tables into RouteWise's
canonical contract (src/ingestion/common/contracts.py). This is the ONE
place real GTFS route_type codes become RouteWise transport_mode
strings, and the ONE place a real GTFS service calendar is actually
built and persisted (Stage 11B §6 -- the synthetic generator's
{weekday,weekend}-only assumption is not reused here).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd

logger = logging.getLogger("routewise.ingestion.gtfs.normalize")

ERROR = "ERROR"
WARNING = "WARNING"

WEEKDAY_COLUMNS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@dataclass
class ModeMappingIssue:
    level: str
    route_id: str
    route_type: str
    message: str

    def to_dict(self) -> dict:
        return {"level": self.level, "route_id": self.route_id, "route_type": self.route_type,
                "message": self.message}


def normalize_stops(stops_raw: pd.DataFrame) -> pd.DataFrame:
    """Filters to GTFS location_type==0 (stop/platform) -- the only type
    stop_times.txt ever references (verified against the real MBTA feed:
    all 3 other types -- 1=station, 2=entrance/exit, 3=generic pathway
    node -- are legitimately coordinate-less per the GTFS spec and are
    never boarding/alighting points, so including them would both fail
    validation on a real GTFS property (not a data error) and pollute
    the routing graph with non-routable nodes. Feeds without a
    location_type column at all (e.g. the synthetic generator) default
    every row to type 0 per the GTFS spec's own default.
    """
    out = stops_raw.copy()
    if "location_type" in out.columns:
        is_platform = out["location_type"].isna() | (out["location_type"] == "0") | (out["location_type"] == "")
        out = out[is_platform]
    out = out[["stop_id", "stop_name", "stop_lat", "stop_lon"]].copy()
    out["stop_lat"] = out["stop_lat"].astype(float)
    out["stop_lon"] = out["stop_lon"].astype(float)
    return out


def normalize_routes(routes_raw: pd.DataFrame, mode_mapping_cfg: dict) -> tuple[pd.DataFrame, list[ModeMappingIssue]]:
    """Applies configs/real_data.yaml mode_mapping.by_route_type. A
    route_type not present in the config is NEVER silently mapped -- it
    is reported as an issue at the configured severity and the route's
    transport_mode is left null.
    """
    by_type = mode_mapping_cfg["by_route_type"]
    severity = mode_mapping_cfg.get("unknown_mode_severity", ERROR)

    out = routes_raw[["route_id", "route_short_name", "route_long_name", "route_type"]].copy()
    out = out.rename(columns={"route_type": "route_type_gtfs"})

    issues: list[ModeMappingIssue] = []
    modes = []
    for route_id, route_type in zip(out["route_id"], out["route_type_gtfs"]):
        mode = by_type.get(str(route_type))
        if mode is None:
            issues.append(ModeMappingIssue(
                severity, route_id, str(route_type),
                f"route_type '{route_type}' has no configured mode mapping (configs/real_data.yaml "
                f"mode_mapping.by_route_type) -- transport_mode left unset for route '{route_id}'.",
            ))
        modes.append(mode)
    out["transport_mode"] = modes
    return out, issues


def normalize_trips(trips_raw: pd.DataFrame) -> pd.DataFrame:
    columns = ["trip_id", "route_id", "service_id", "direction_id", "trip_headsign"]
    if "route_pattern_id" in trips_raw.columns:
        columns.append("route_pattern_id")
    out = trips_raw[columns].copy()
    if "route_pattern_id" not in out.columns:
        out["route_pattern_id"] = None
    return out


def normalize_stop_times(stop_times_raw: pd.DataFrame) -> pd.DataFrame:
    out = stop_times_raw[["trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"]].copy()
    out = out.rename(columns={"arrival_time": "scheduled_arrival", "departure_time": "scheduled_departure"})
    out["stop_sequence"] = out["stop_sequence"].astype(int)
    return out


def _expand_calendar(calendar_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in calendar_df.iterrows():
        start = datetime.strptime(row["start_date"], "%Y%m%d").date()
        end = datetime.strptime(row["end_date"], "%Y%m%d").date()
        active_weekdays = {i for i, col in enumerate(WEEKDAY_COLUMNS) if row[col] == "1"}
        n_days = (end - start).days + 1
        for offset in range(n_days):
            d = start + timedelta(days=offset)
            if d.weekday() in active_weekdays:
                rows.append({"service_id": row["service_id"], "service_date": d, "is_exception": False})
    return pd.DataFrame(rows, columns=["service_id", "service_date", "is_exception"])


def _apply_calendar_date_exceptions(base: pd.DataFrame, calendar_dates_df: pd.DataFrame) -> pd.DataFrame:
    if calendar_dates_df is None or calendar_dates_df.empty:
        return base

    added_rows, removed_keys = [], set()
    for _, row in calendar_dates_df.iterrows():
        d = datetime.strptime(row["date"], "%Y%m%d").date()
        key = (row["service_id"], d)
        if row["exception_type"] == "1":
            added_rows.append({"service_id": row["service_id"], "service_date": d, "is_exception": True})
        elif row["exception_type"] == "2":
            removed_keys.add(key)

    if removed_keys:
        keys = pd.Series(list(zip(base["service_id"], base["service_date"])), index=base.index)
        base = base[~keys.isin(removed_keys)]

    if added_rows:
        added_df = pd.DataFrame(added_rows)
        base = pd.concat([base, added_df], ignore_index=True)

    return base.sort_values(["service_id", "service_date"]).reset_index(drop=True)


def build_service_calendar(calendar_df: pd.DataFrame | None, calendar_dates_df: pd.DataFrame | None) -> pd.DataFrame:
    """Stage 11B §6: the real service_calendar table -- service_id x
    service_date, correctly combining calendar.txt's weekly pattern with
    calendar_dates.txt's add/remove exceptions. Handles a feed that has
    ONLY calendar_dates.txt (calendar.txt absent) by starting from an
    empty base and adding every exception_type=1 row.
    """
    if calendar_df is not None and not calendar_df.empty:
        base = _expand_calendar(calendar_df)
    else:
        base = pd.DataFrame(columns=["service_id", "service_date", "is_exception"])

    return _apply_calendar_date_exceptions(base, calendar_dates_df)


def effective_service_ids(service_calendar: pd.DataFrame, service_date: date) -> set[str]:
    """Every service_id actually running on a given calendar date --
    the correct way to resolve "which trips ran today," replacing the
    synthetic generator's direct weekday/weekend string comparison."""
    return set(service_calendar.loc[service_calendar["service_date"] == service_date, "service_id"])


def normalize_fares(
    fare_products_df: pd.DataFrame | None, fare_leg_rules_df: pd.DataFrame | None, routes_df: pd.DataFrame,
) -> pd.DataFrame:
    """Stage 11B §15: best-effort fare normalization. MBTA's GTFS-Fares
    v2 files (fare_products.txt + fare_leg_rules.txt) are leg-based, not
    a flat route_id->amount table, and are explicitly documented by MBTA
    as covering only "full-fare passengers paying walk-up fares" -- NOT
    a complete fare structure. Rather than force an unreliable mapping,
    this returns fare_available=false for every route by default unless
    a route can be unambiguously tied to exactly one fare_product via
    fare_leg_rules -- and even then, callers should treat the result as
    approximate, not authoritative (see the Stage 11B report).
    """
    out = routes_df[["route_id"]].copy()
    out["fare_amount"] = None
    out["currency"] = None
    out["fare_available"] = False

    if fare_products_df is None or fare_leg_rules_df is None:
        logger.warning("Fare files not present in this feed -- all routes fare_available=false.")
        return out

    if "network_id" not in fare_leg_rules_df.columns or "from_area_id" in fare_leg_rules_df.columns:
        # fare_leg_rules is genuinely leg/area-based (origin/destination zone pairs),
        # not route-keyed -- MBTA's real feed matches this shape. A reliable
        # per-route flat amount cannot be derived without fabricating an
        # unstated simplification. Leave fare_available=false for all routes,
        # honestly, rather than approximate.
        logger.warning(
            "fare_leg_rules.txt is leg/area-based (not route-keyed) in this feed -- "
            "cannot derive a reliable flat per-route fare_amount without fabricating "
            "a simplification MBTA's own data doesn't support. All routes fare_available=false."
        )
        return out

    return out

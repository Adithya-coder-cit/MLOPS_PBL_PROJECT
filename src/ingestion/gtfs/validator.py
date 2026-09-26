"""Stage 11B §16: real-GTFS-specific validation, reusing the existing
ValidationIssue reporting primitive (src/validation/validators.py) --
never a second issue type. Fails loudly on ERROR; never silently repairs
source data.
"""
from __future__ import annotations

import pandas as pd

from src.validation.validators import ERROR, WARNING, ValidationIssue

LAT_RANGE = (-90.0, 90.0)
LON_RANGE = (-180.0, 180.0)


def check_primary_keys(stops: pd.DataFrame, routes: pd.DataFrame, trips: pd.DataFrame) -> list[ValidationIssue]:
    issues = []
    for name, df, key in [("stops", stops, "stop_id"), ("routes", routes, "route_id"), ("trips", trips, "trip_id")]:
        n_dupes = int(df[key].duplicated().sum())
        if n_dupes:
            issues.append(ValidationIssue(ERROR, name, "primary_key_uniqueness",
                                           f"{n_dupes} duplicate '{key}' value(s)", n_dupes))
    return issues


def check_foreign_keys(stops: pd.DataFrame, routes: pd.DataFrame, trips: pd.DataFrame,
                        stop_times: pd.DataFrame) -> list[ValidationIssue]:
    issues = []
    orphan_trips = ~trips["route_id"].isin(routes["route_id"])
    if orphan_trips.any():
        n = int(orphan_trips.sum())
        issues.append(ValidationIssue(ERROR, "trips", "foreign_key_integrity",
                                       f"{n} trip(s) reference a route_id not in routes", n))

    orphan_st_trip = ~stop_times["trip_id"].isin(trips["trip_id"])
    if orphan_st_trip.any():
        n = int(orphan_st_trip.sum())
        issues.append(ValidationIssue(ERROR, "stop_times", "foreign_key_integrity",
                                       f"{n} stop_times row(s) reference a trip_id not in trips", n))

    orphan_st_stop = ~stop_times["stop_id"].isin(stops["stop_id"])
    if orphan_st_stop.any():
        n = int(orphan_st_stop.sum())
        issues.append(ValidationIssue(ERROR, "stop_times", "foreign_key_integrity",
                                       f"{n} stop_times row(s) reference a stop_id not in stops", n))
    return issues


def check_stop_coordinates(stops: pd.DataFrame) -> list[ValidationIssue]:
    issues = []
    out_of_range = (
        stops["stop_lat"].isna() | stops["stop_lon"].isna()
        | ~stops["stop_lat"].between(*LAT_RANGE) | ~stops["stop_lon"].between(*LON_RANGE)
    )
    if out_of_range.any():
        n = int(out_of_range.sum())
        issues.append(ValidationIssue(ERROR, "stops", "coordinate_validity",
                                       f"{n} stop(s) with missing/out-of-range lat/lon", n))
    # (0, 0) is a common "unknown location" placeholder some feeds use --
    # technically in-range, but implausible for a real stop.
    placeholder = (stops["stop_lat"] == 0.0) & (stops["stop_lon"] == 0.0)
    if placeholder.any():
        n = int(placeholder.sum())
        issues.append(ValidationIssue(
            WARNING, "stops", "coordinate_plausibility",
            f"{n} stop(s) at exactly (0, 0) -- likely a placeholder, not a real location", n,
        ))
    return issues


def check_stop_sequence_monotonic(stop_times: pd.DataFrame) -> list[ValidationIssue]:
    non_monotonic = 0
    for _trip_id, group in stop_times.groupby("trip_id")["stop_sequence"]:
        if not group.is_monotonic_increasing:
            non_monotonic += 1
    if non_monotonic:
        return [ValidationIssue(ERROR, "stop_times", "stop_sequence_monotonic",
                                 f"{non_monotonic} trip(s) have non-increasing stop_sequence", non_monotonic)]
    return []


def check_service_id_has_calendar_entry(trips: pd.DataFrame, service_calendar: pd.DataFrame) -> list[ValidationIssue]:
    known = set(service_calendar["service_id"].unique())
    orphaned = ~trips["service_id"].isin(known)
    if orphaned.any():
        n = int(orphaned.sum())
        return [ValidationIssue(WARNING, "trips", "service_id_calendar_coverage",
                                 f"{n} trip(s) reference a service_id with zero effective service_date "
                                 f"(never runs on any calendar date in this feed's validity window)", n)]
    return []


def check_duplicate_stop_times(stop_times: pd.DataFrame) -> list[ValidationIssue]:
    n_dupes = int(stop_times.duplicated(subset=["trip_id", "stop_sequence"]).sum())
    if n_dupes:
        return [ValidationIssue(ERROR, "stop_times", "duplicate_records",
                                 f"{n_dupes} duplicate (trip_id, stop_sequence) row(s)", n_dupes)]
    return []


def run_gtfs_validation(
    stops: pd.DataFrame, routes: pd.DataFrame, trips: pd.DataFrame, stop_times: pd.DataFrame,
    service_calendar: pd.DataFrame,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues += check_primary_keys(stops, routes, trips)
    issues += check_foreign_keys(stops, routes, trips, stop_times)
    issues += check_stop_coordinates(stops)
    issues += check_stop_sequence_monotonic(stop_times)
    issues += check_service_id_has_calendar_entry(trips, service_calendar)
    issues += check_duplicate_stop_times(stop_times)
    return issues

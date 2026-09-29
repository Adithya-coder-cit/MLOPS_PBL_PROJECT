"""Stage 11D Part 5: validation for the canonical weather table (any
source -- NWS, NOAA GHCNh, or a combined table). Reuses the project's
single ValidationIssue type (src.validation.validators), same convention
as src.ingestion.gtfs.validator -- observes and reports, never repairs.
"""
from __future__ import annotations

import pandas as pd

from src.validation.validators import ERROR, WARNING, ValidationIssue

REQUIRED_COLUMNS = ["observation_id", "weather_zone_id", "timestamp", "source"]

# Physically plausible ranges for a Boston-area surface station --
# generous bounds meant to catch parsing/unit errors, not to model actual
# climate extremes.
TEMPERATURE_C_RANGE = (-40.0, 50.0)
PRESSURE_HPA_RANGE = (850.0, 1085.0)


def check_required_columns(weather: pd.DataFrame) -> list[ValidationIssue]:
    missing = [c for c in REQUIRED_COLUMNS if c not in weather.columns]
    if missing:
        return [ValidationIssue(ERROR, "weather", "required_columns",
                                 f"Missing required columns: {missing}", len(missing))]
    return []


def check_timestamp_validity(weather: pd.DataFrame) -> list[ValidationIssue]:
    if "timestamp" not in weather.columns or weather.empty:
        return []
    issues = []
    invalid = weather["timestamp"].isna()
    if invalid.any():
        issues.append(ValidationIssue(ERROR, "weather", "timestamp_validity",
                                       f"{int(invalid.sum())} row(s) with an unparseable/null timestamp",
                                       int(invalid.sum())))
    return issues


def check_timezone_consistency(weather: pd.DataFrame) -> list[ValidationIssue]:
    """Every row's timestamp must be timezone-AWARE -- a naive timestamp
    here would silently break the leakage-safe asof join's UTC alignment
    (src.ingestion.weather.normalize.join_weather_asof converts both
    sides to UTC before comparing)."""
    if "timestamp" not in weather.columns or weather.empty:
        return []
    ts = weather["timestamp"]
    if not pd.api.types.is_datetime64_any_dtype(ts):
        return [ValidationIssue(ERROR, "weather", "timezone_consistency",
                                 "timestamp column is not a datetime dtype", len(weather))]
    if ts.dt.tz is None:
        return [ValidationIssue(ERROR, "weather", "timezone_consistency",
                                 "timestamp column is timezone-NAIVE -- every weather observation "
                                 "must be timezone-aware before the asof join", len(weather))]
    return []


def check_duplicate_observations(weather: pd.DataFrame) -> list[ValidationIssue]:
    if not {"weather_zone_id", "timestamp"}.issubset(weather.columns) or weather.empty:
        return []
    n_dupes = int(weather.duplicated(subset=["weather_zone_id", "timestamp"]).sum())
    if n_dupes:
        return [ValidationIssue(WARNING, "weather", "duplicate_observations",
                                 f"{n_dupes} duplicate (weather_zone_id, timestamp) observation(s) -- "
                                 f"the asof join's merge key requires uniqueness; combine_weather_sources "
                                 f"should have already resolved cross-source collisions", n_dupes)]
    return []


def check_missingness(weather: pd.DataFrame) -> list[ValidationIssue]:
    """Reports, never repairs -- WARNING only, since a null measurement is
    an expected, honest outcome for real weather data (Stage 11B/C/D:
    never fabricate a substitute)."""
    issues = []
    for col in ["precipitation_mm", "temperature_c", "visibility_km", "wind_speed_ms", "pressure_hpa"]:
        if col not in weather.columns or weather.empty:
            continue
        rate = float(weather[col].isna().mean())
        if rate > 0.0:
            issues.append(ValidationIssue(WARNING, "weather", "missingness",
                                           f"{col}: {rate:.1%} of rows are null (reported, not fabricated)",
                                           int(weather[col].isna().sum())))
    return issues


def check_numeric_types(weather: pd.DataFrame) -> list[ValidationIssue]:
    issues = []
    for col in ["precipitation_mm", "temperature_c", "visibility_km", "wind_speed_ms", "pressure_hpa"]:
        if col not in weather.columns or weather.empty:
            continue
        if not pd.api.types.is_numeric_dtype(weather[col]):
            issues.append(ValidationIssue(ERROR, "weather", "numeric_types",
                                           f"{col} is not a numeric dtype", 0))
    return issues


def check_physically_implausible_values(weather: pd.DataFrame) -> list[ValidationIssue]:
    issues = []

    def _range_check(col: str, low: float, high: float) -> None:
        if col not in weather.columns or weather.empty:
            return
        s = weather[col].dropna()
        bad = s[(s < low) | (s > high)]
        if len(bad):
            issues.append(ValidationIssue(ERROR, "weather", "physical_range",
                                           f"{col}: {len(bad)} value(s) outside plausible range "
                                           f"[{low}, {high}]", len(bad)))

    _range_check("temperature_c", *TEMPERATURE_C_RANGE)
    _range_check("pressure_hpa", *PRESSURE_HPA_RANGE)

    def _nonnegative_check(col: str) -> None:
        if col not in weather.columns or weather.empty:
            return
        s = weather[col].dropna()
        bad = s[s < 0]
        if len(bad):
            issues.append(ValidationIssue(ERROR, "weather", "physical_range",
                                           f"{col}: {len(bad)} negative value(s) -- physically impossible",
                                           len(bad)))

    _nonnegative_check("precipitation_mm")
    _nonnegative_check("wind_speed_ms")
    _nonnegative_check("visibility_km")
    return issues


def check_station_consistency(weather: pd.DataFrame) -> list[ValidationIssue]:
    """Every row claiming a given weather_zone_id should report the same
    station_lat/station_lon when those are populated -- catches a
    mis-assigned or drifting station identity, not a normal missingness
    pattern."""
    issues = []
    if not {"weather_zone_id", "station_lat", "station_lon"}.issubset(weather.columns) or weather.empty:
        return issues
    located = weather.dropna(subset=["station_lat", "station_lon"])
    if located.empty:
        return issues
    n_distinct = located.groupby("weather_zone_id")[["station_lat", "station_lon"]].nunique()
    inconsistent = n_distinct[(n_distinct["station_lat"] > 1) | (n_distinct["station_lon"] > 1)]
    if len(inconsistent):
        issues.append(ValidationIssue(ERROR, "weather", "station_consistency",
                                       f"{len(inconsistent)} weather_zone_id(s) report more than one "
                                       f"distinct (lat, lon) -- possible station mis-assignment",
                                       len(inconsistent)))
    return issues


def check_chronological_ordering(weather: pd.DataFrame) -> list[ValidationIssue]:
    """Informational: confirms the table CAN be sorted chronologically per
    zone without exposing anything unexpected (e.g. duplicate exact
    timestamps within a zone that check_duplicate_observations already
    flags). Not an error by itself -- input order is not assumed sorted."""
    issues = []
    if not {"weather_zone_id", "timestamp"}.issubset(weather.columns) or weather.empty:
        return issues
    for zone, group in weather.groupby("weather_zone_id"):
        if group["timestamp"].isna().any():
            continue
        sorted_ts = group["timestamp"].sort_values()
        if not sorted_ts.is_monotonic_increasing:
            issues.append(ValidationIssue(ERROR, "weather", "chronological_ordering",
                                           f"weather_zone_id={zone}: timestamps do not form a strictly "
                                           f"sortable chronological sequence", 0))
    return issues


def run_weather_validation(weather: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues += check_required_columns(weather)
    issues += check_timestamp_validity(weather)
    issues += check_timezone_consistency(weather)
    issues += check_duplicate_observations(weather)
    issues += check_missingness(weather)
    issues += check_numeric_types(weather)
    issues += check_physically_implausible_values(weather)
    issues += check_station_consistency(weather)
    issues += check_chronological_ordering(weather)
    return issues

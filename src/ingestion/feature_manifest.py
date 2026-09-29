"""Stage 11E Part 8: the definitive real-model feature manifest -- every
training-table column classified as exactly one of MODEL_FEATURE,
DIAGNOSTIC_ONLY, IDENTIFIER, LABEL, or PROVENANCE, built from
src.ingestion.training_table's structural schema plus
src.ingestion.feature_eligibility's measured, evidence-based strategy
decision (never a second, independently-maintained classification that
could drift from what was actually measured).
"""
from __future__ import annotations

from src.ingestion.feature_eligibility import EXCLUDE, INCLUDE_DIRECTLY, INCLUDE_WITH_STRATEGY
from src.ingestion.training_table import TRAINING_TABLE_SCHEMA

MODEL_FEATURE = "MODEL_FEATURE"
DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
IDENTIFIER = "IDENTIFIER"
LABEL = "LABEL"
PROVENANCE = "PROVENANCE"

ROLE_TO_MANIFEST_CATEGORY = {
    "entity_identifier": IDENTIFIER,
    "prediction_timestamp": IDENTIFIER,
    "metadata": IDENTIFIER,
    "diagnostic_only": DIAGNOSTIC_ONLY,
    "label": LABEL,
    "provenance": PROVENANCE,
    # "feature" role is resolved per-feature from feature_strategy below,
    # not statically -- its manifest category depends on measured coverage.
}

# Unit + plain-language meaning -- independent of measured coverage, part
# of the feature's fixed definition.
FEATURE_META = {
    "hour": {"unit": "integer, 0-23", "meaning": "hour of the scheduled stop-event"},
    "day_of_week": {"unit": "integer, 0=Monday..6=Sunday", "meaning": "day of week of the scheduled stop-event"},
    "day_period": {"unit": "categorical", "meaning": "config-driven peak/off_peak/night bucket"},
    "time_of_day_bucket": {"unit": "categorical", "meaning": "derived time-of-day bucket"},
    "transfer_dependency": {"unit": "float", "meaning": "structural transfer-dependency score (stop_times+trips)"},
    "precipitation_mm": {"unit": "millimeters",
                         "meaning": "hourly precipitation at the nearest asof-matched weather observation"},
    "temperature_c": {"unit": "degrees Celsius",
                      "meaning": "air temperature at the nearest asof-matched weather observation"},
    "visibility_km": {"unit": "kilometers",
                      "meaning": "visibility at the nearest asof-matched weather observation"},
    "wind_speed_ms": {"unit": "meters/second",
                      "meaning": "wind speed at the nearest asof-matched weather observation (NOAA GHCNh only)"},
    "pressure_hpa": {"unit": "hectopascals",
                     "meaning": "sea-level (preferred) or station-level pressure at the nearest asof-matched "
                                "weather observation (NOAA GHCNh only)"},
    "historical_delay_seconds": {"unit": "seconds",
                                 "meaning": "route-level expanding mean delay, strictly prior service_dates"},
    "rolling_7d_delay_seconds": {"unit": "seconds",
                                 "meaning": "route-level 7-day rolling mean delay, strictly prior service_dates"},
    "historical_reliability": {"unit": "float in [0, 1]",
                               "meaning": "1 - route-level expanding disruption rate, strictly prior service_dates"},
}

LEAKAGE_STATUS = {
    "hour": "none -- derived from scheduled_time, the prediction timestamp itself",
    "day_of_week": "none -- derived from scheduled_time, the prediction timestamp itself",
    "day_period": "none -- derived from scheduled_time, the prediction timestamp itself",
    "time_of_day_bucket": "none -- derived from scheduled_time, the prediction timestamp itself",
    "transfer_dependency": "none -- structural only, computed from stop_times+trips",
    "precipitation_mm": "none -- backward-only asof join, verified by test (never a future observation)",
    "temperature_c": "none -- backward-only asof join, verified by test (never a future observation)",
    "visibility_km": "none -- backward-only asof join, verified by test (never a future observation)",
    "wind_speed_ms": "none -- backward-only asof join, verified by test (never a future observation)",
    "pressure_hpa": "none -- backward-only asof join, verified by test (never a future observation)",
    "historical_delay_seconds": "none by construction -- shift(1) before any expanding/rolling window, "
                                "verified by test",
    "rolling_7d_delay_seconds": "none by construction -- shift(1) before any expanding/rolling window, "
                                "verified by test",
    "historical_reliability": "none by construction -- same shift(1) discipline, verified by test",
}

DATA_SOURCE = {
    "hour": "GTFS stop_times (scheduled), via src.utils.gtfs_time",
    "day_of_week": "derived from scheduled_time",
    "day_period": "derived from scheduled_time (NOT yet wired into the real ingestion pipeline)",
    "time_of_day_bucket": "derived from scheduled_time (NOT yet wired into the real ingestion pipeline)",
    "transfer_dependency": "GTFS stop_times + trips (NOT yet wired into the real ingestion pipeline)",
    "precipitation_mm": "NWS (api.weather.gov) + NOAA GHCNh, combined (src.ingestion.weather)",
    "temperature_c": "NWS (api.weather.gov) + NOAA GHCNh, combined (src.ingestion.weather)",
    "visibility_km": "NWS (api.weather.gov) + NOAA GHCNh, combined (src.ingestion.weather)",
    "wind_speed_ms": "NOAA GHCNh only (src.ingestion.weather.ghcnh)",
    "pressure_hpa": "NOAA GHCNh only (src.ingestion.weather.ghcnh)",
    "historical_delay_seconds": "MBTA LAMP delay_seconds, route-level aggregate (src.ingestion.historical_features)",
    "rolling_7d_delay_seconds": "MBTA LAMP delay_seconds, route-level aggregate (src.ingestion.historical_features)",
    "historical_reliability": "MBTA LAMP delay_seconds + frozen label policy (src.ingestion.historical_features)",
}


def build_feature_manifest(feature_strategy: dict) -> dict:
    entries = []
    for field in TRAINING_TABLE_SCHEMA:
        name, role = field["name"], field["role"]

        if role == "feature":
            strat = feature_strategy.get(name, {})
            strategy = strat.get("strategy")
            category = MODEL_FEATURE if strategy in (INCLUDE_DIRECTLY, INCLUDE_WITH_STRATEGY) else DIAGNOSTIC_ONLY
            missing_value_behavior = (
                "no missing values (>= 95% real coverage)" if strategy == INCLUDE_DIRECTLY else
                strat.get("missing_value_handling") if strategy == INCLUDE_WITH_STRATEGY else
                "NOT used as a model input -- retained in the training table for diagnostics/EDA only; "
                "a null value here has no defined model-input behavior" if strategy == DIAGNOSTIC_ONLY else
                f"excluded entirely (strategy={strategy})" if strategy == EXCLUDE else
                "strategy not determined (feature_strategy report missing this entry)"
            )
            entry = {
                "name": name, "category": category,
                "description": field["description"],
                "data_source": DATA_SOURCE.get(name, "see src.ingestion.training_table"),
                "measured_coverage": strat.get("coverage"),
                "eligibility_strategy": strategy,
                "missing_value_behavior": missing_value_behavior,
                "leakage_status": LEAKAGE_STATUS.get(name, "see src.ingestion.feature_availability"),
                "unit": FEATURE_META.get(name, {}).get("unit"),
                "meaning": FEATURE_META.get(name, {}).get("meaning"),
            }
        else:
            entry = {
                "name": name, "category": ROLE_TO_MANIFEST_CATEGORY[role],
                "description": field["description"],
            }

        entries.append(entry)

    summary = {}
    for entry in entries:
        summary[entry["category"]] = summary.get(entry["category"], 0) + 1

    return {"features": entries, "summary": summary}

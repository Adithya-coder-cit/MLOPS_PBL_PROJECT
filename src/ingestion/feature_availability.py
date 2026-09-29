"""Stage 11B/11C §19/G: feature availability matrix for every existing
Stage 4 model input feature (training/prepare_inputs.py::ALL_FEATURES).
No synthetic replacement is proposed for any UNAVAILABLE/PARTIAL feature
-- that would fabricate data. Stage 11C: every coverage number is
computed from the actual real ingested/joined tables, not asserted --
a feature is never marked AVAILABLE merely because its column exists.
"""
from __future__ import annotations

import pandas as pd

AVAILABLE = "AVAILABLE"
PARTIAL = "PARTIAL"
UNAVAILABLE = "UNAVAILABLE"

# A column is AVAILABLE only if its real non-null coverage clears this
# bar; below it, PARTIAL; a column that is entirely null (or genuinely
# absent) is UNAVAILABLE. An engineering choice, documented rather than
# implicit.
AVAILABLE_COVERAGE_THRESHOLD = 0.95
UNAVAILABLE_COVERAGE_THRESHOLD = 0.01


def _coverage(series: pd.Series | None) -> float:
    if series is None or len(series) == 0:
        return 0.0
    return float(series.notna().mean())


def _classify(coverage: float) -> str:
    if coverage >= AVAILABLE_COVERAGE_THRESHOLD:
        return AVAILABLE
    if coverage <= UNAVAILABLE_COVERAGE_THRESHOLD:
        return UNAVAILABLE
    return PARTIAL


def build_feature_availability_matrix(training_table: pd.DataFrame, cfg: dict) -> dict:
    label_avail = cfg["label_availability"]
    modes_with_labels = sorted([m for m, v in label_avail.items() if v])
    modes_without_labels = sorted([m for m, v in label_avail.items() if not v])

    def col(name: str) -> pd.Series | None:
        return training_table[name] if name in training_table.columns else None

    structural = [
        ("transport_mode", "GTFS routes.route_type -> mode mapping", "route_type -> mode lookup", "none"),
        ("hour", "GTFS stop_times (scheduled), via src.utils.gtfs_time", "extracted from scheduled_time", "none"),
        ("day_of_week", "derived from scheduled_time", "extracted from scheduled_time", "none"),
        ("day_period", "derived from scheduled_time", "config-driven peak/off_peak/night windows", "none"),
        ("time_of_day_bucket", "derived from scheduled_time", "unchanged bucketing mechanism", "none"),
        ("transfer_dependency", "GTFS stop_times + trips (structural)",
         "src.utils.network_topology.compute_transfer_dependency, unchanged", "none -- structural only"),
    ]
    rows = []
    for name, source, transformation, leakage in structural:
        coverage = _coverage(col(name))
        rows.append({"feature": name, "availability": _classify(coverage), "source": source,
                     "transformation": transformation, "coverage": round(coverage, 4), "leakage_risk": leakage})

    weather_note = ("real NWS station observations (Stage 11C: NWS is a SHORT ROLLING window, not a "
                     "historical archive -- confirmed empirically; NOAA NCEI's 2026 annual archive is "
                     "not yet published as of this run -- confirmed against the live directory listing)")
    for name in ["precipitation_mm", "temperature_c", "visibility_km"]:
        coverage = _coverage(col(name))
        rows.append({"feature": name, "availability": _classify(coverage), "source": weather_note,
                     "transformation": "src.ingestion.weather.normalize + leakage-safe backward asof-join",
                     "coverage": round(coverage, 4), "leakage_risk": "none (join direction verified backward-only)"})

    hist_note = (f"MBTA LAMP delay_seconds, route-level shift(1)-before-window aggregate "
                 f"(src.ingestion.historical_features) -- real label source verified for "
                 f"{modes_with_labels}; NOT available for {modes_without_labels}")
    for name in ["historical_delay_seconds", "rolling_7d_delay_seconds"]:
        coverage = _coverage(col(name))
        rows.append({"feature": name, "availability": _classify(coverage), "source": hist_note,
                     "transformation": "src.ingestion.historical_features.join_historical_features "
                                       "(shift(1) before expanding/rolling, same discipline as the synthetic pipeline)",
                     "coverage": round(coverage, 4),
                     "leakage_risk": "none by construction (shift(1) verified by test)"})

    reliability_coverage = _coverage(col("historical_reliability"))
    rows.append({
        "feature": "historical_reliability", "availability": _classify(reliability_coverage),
        "source": hist_note + "; additionally requires the label policy to be active "
                              "(computed from disruption_flag, not delay_seconds directly)",
        "transformation": "src.ingestion.historical_features.historical_reliability_from_labels",
        "coverage": round(reliability_coverage, 4),
        "leakage_risk": "same shift(1) discipline",
    })

    label_coverage = _coverage(col("disruption_flag")) if "disruption_flag" in training_table.columns else 0.0
    label_field = {
        "feature": "disruption_flag (the training LABEL, not a model input feature)",
        "availability": _classify(label_coverage),
        "source": f"available for {modes_with_labels}; UNAVAILABLE (by policy, not omission) for "
                  f"{modes_without_labels}",
        "transformation": "delay_seconds >= configured per-mode threshold OR cancellation "
                          "(src.ingestion.label_policy) -- see model_readiness.json for activation status",
        "coverage": round(label_coverage, 4),
        "leakage_risk": "none -- computed strictly from this row's own realized outcome fields, "
                        "never fed back as a model input",
    }

    return {"model_input_features": rows, "label": label_field,
            "summary": {
                "available": sum(1 for r in rows if r["availability"] == AVAILABLE),
                "partial": sum(1 for r in rows if r["availability"] == PARTIAL),
                "unavailable": sum(1 for r in rows if r["availability"] == UNAVAILABLE),
                "total": len(rows),
            }}

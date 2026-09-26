"""Stage 11B §19: feature availability matrix for every existing Stage 4
model input feature (training/prepare_inputs.py::ALL_FEATURES). No
synthetic replacement is proposed for any UNAVAILABLE/PARTIAL feature --
that would fabricate data (Stage 11B's explicit prohibition).
"""
from __future__ import annotations

AVAILABLE = "AVAILABLE"
PARTIAL = "PARTIAL"
UNAVAILABLE = "UNAVAILABLE"


def build_feature_availability_matrix(tables: dict, cfg: dict) -> dict:
    label_avail = cfg["label_availability"]
    modes_with_labels = sorted([m for m, v in label_avail.items() if v])
    modes_without_labels = sorted([m for m, v in label_avail.items() if not v])

    weather = tables.get("weather")
    weather_coverage_note = (
        f"real NWS station observations (Stage 11B verified), covering only a recent rolling "
        f"window ({str(weather['timestamp'].min())}..{str(weather['timestamp'].max())}), not a "
        f"deep historical backfill -- NOAA NCEI ISD is the recommended, not-yet-implemented, "
        f"source for that (docs/stage11a)."
    ) if weather is not None and not weather.empty else "no weather data ingested in this run"

    rows = [
        {"feature": "transport_mode", "availability": AVAILABLE, "source": "GTFS routes.route_type",
         "transformation": "route_type -> mode lookup (configs/real_data.yaml mode_mapping)",
         "leakage_risk": "none"},
        {"feature": "hour", "availability": AVAILABLE, "source": "GTFS stop_times (scheduled), via src.utils.gtfs_time",
         "transformation": "extracted from scheduled_time", "leakage_risk": "none"},
        {"feature": "day_of_week", "availability": AVAILABLE, "source": "GTFS service_calendar + scheduled_time",
         "transformation": "extracted from scheduled_time", "leakage_risk": "none"},
        {"feature": "day_period", "availability": AVAILABLE, "source": "derived from scheduled_time",
         "transformation": "config-driven peak/off_peak/night windows (unchanged mechanism; window "
                            "VALUES should be re-tuned for MBTA's real peak patterns, not ported "
                            "from the synthetic config)", "leakage_risk": "none"},
        {"feature": "time_of_day_bucket", "availability": AVAILABLE, "source": "derived from scheduled_time",
         "transformation": "unchanged bucketing mechanism", "leakage_risk": "none"},
        {"feature": "transfer_dependency", "availability": AVAILABLE,
         "source": "GTFS stop_times + trips (structural)",
         "transformation": "unchanged src.utils.network_topology.compute_transfer_dependency; "
                            "verified computable against the real feed's scale, though its O(n^2) "
                            "per-(stop,service_id)-group implementation is a documented performance "
                            "risk at real scale (Stage 11 discovery report Sec 11), not a "
                            "correctness one", "leakage_risk": "none -- structural only"},
        {"feature": "precipitation_mm", "availability": PARTIAL,
         "source": f"NWS api.weather.gov -- {weather_coverage_note}",
         "transformation": "src.ingestion.weather.normalize + leakage-safe backward asof-join",
         "leakage_risk": "none (join direction verified backward-only)"},
        {"feature": "temperature_c", "availability": PARTIAL if weather is None or weather.empty else AVAILABLE,
         "source": f"NWS api.weather.gov -- {weather_coverage_note}",
         "transformation": "same as precipitation_mm", "leakage_risk": "none"},
        {"feature": "visibility_km", "availability": PARTIAL if weather is None or weather.empty else AVAILABLE,
         "source": f"NWS api.weather.gov -- {weather_coverage_note}",
         "transformation": "same as precipitation_mm", "leakage_risk": "none"},
        {"feature": "historical_delay_minutes", "availability": PARTIAL,
         "source": f"MBTA LAMP delay_seconds -- real label source verified for modes {modes_with_labels}; "
                    f"NOT available for {modes_without_labels}",
         "transformation": "NOT YET IMPLEMENTED for real data (Stage 12 scope) -- would reuse "
                            "src/features/historical.py's shift(1)-before-any-window leakage-safe "
                            "pattern unchanged, applied per available mode only",
         "leakage_risk": "none by construction once implemented (same shift(1) discipline)"},
        {"feature": "rolling_7d_delay_minutes", "availability": PARTIAL,
         "source": "same as historical_delay_minutes", "transformation": "same", "leakage_risk": "same"},
        {"feature": "historical_reliability", "availability": PARTIAL,
         "source": "same as historical_delay_minutes, but ADDITIONALLY blocked on "
                    "real_disruption_label_policy.active being turned on (Stage 11B §12 -- not "
                    "activated in this stage) since it's computed from disruption_flag, not "
                    "delay_seconds directly",
         "transformation": "not yet implemented; blocked on the label-threshold approval decision",
         "leakage_risk": "same shift(1) discipline once implemented"},
    ]

    label_field = {
        "feature": "disruption_flag (the training LABEL, not a model input feature)",
        "availability": PARTIAL,
        "source": f"available for {modes_with_labels}; UNAVAILABLE (by policy, not by omission) for "
                  f"{modes_without_labels} -- see configs/real_data.yaml label_availability",
        "transformation": "delay_seconds >= configured threshold OR cancellation -- threshold NOT "
                          "yet approved/activated (Stage 11B §12)",
        "leakage_risk": "none -- computed strictly from realized outcome fields, never fed back as "
                        "a model input",
    }

    return {"model_input_features": rows, "label": label_field,
            "summary": {
                "available": sum(1 for r in rows if r["availability"] == AVAILABLE),
                "partial": sum(1 for r in rows if r["availability"] == PARTIAL),
                "unavailable": sum(1 for r in rows if r["availability"] == UNAVAILABLE),
                "total": len(rows),
            }}

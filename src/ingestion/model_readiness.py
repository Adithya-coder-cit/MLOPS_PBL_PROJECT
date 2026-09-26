"""Stage 11B §20: the model readiness gate. Training must never proceed
merely because ingestion succeeded -- this module makes that decision
explicit, reasoned, and machine-readable.
"""
from __future__ import annotations


def build_model_readiness_decision(tables: dict, issues: list, feature_matrix: dict, cfg: dict) -> dict:
    reasons_blocking: list[str] = []
    reasons_ok: list[str] = []

    errors = [i for i in issues if i.level == "ERROR"]
    if errors:
        reasons_blocking.append(f"{len(errors)} unresolved validation ERROR(s) remain.")
    else:
        reasons_ok.append("Zero validation ERRORs against the real ingested GTFS contract.")

    label_policy_active = cfg["real_disruption_label_policy"]["active"]
    if not label_policy_active:
        reasons_blocking.append(
            "The real-world disruption-label threshold has not been approved/activated "
            "(configs/real_data.yaml real_disruption_label_policy.active=false, Stage 11B §12) -- "
            "no disruption_flag values exist to train against."
        )
    else:
        reasons_ok.append("Real disruption-label policy is active.")

    unavailable_or_partial = [
        r["feature"] for r in feature_matrix["model_input_features"]
        if r["availability"] != "AVAILABLE"
    ]
    if unavailable_or_partial:
        reasons_blocking.append(
            f"{len(unavailable_or_partial)} of {feature_matrix['summary']['total']} model input "
            f"features are not fully AVAILABLE yet: {unavailable_or_partial} -- historical-delay "
            f"features in particular are not yet implemented for real data (Stage 12 scope, not "
            f"this stage)."
        )
    else:
        reasons_ok.append("All model input features are AVAILABLE.")

    modes_without_labels = [m for m, v in cfg["label_availability"].items() if not v]
    if modes_without_labels:
        reasons_blocking.append(
            f"No verified historical-label source exists for mode(s) {modes_without_labels} "
            f"(rail, ferry) -- any model trained now would silently exclude 2 of RouteWise's 5 "
            f"modes or require a labels-unavailable-mode design decision not yet made for training "
            f"(only for monitoring/inference, per Stage 9)."
        )

    weather = tables.get("weather")
    if weather is None or weather.empty:
        reasons_blocking.append("No weather data was successfully joined.")
    else:
        import pandas as pd
        span_days = (pd.to_datetime(weather["timestamp"]).max() - pd.to_datetime(weather["timestamp"]).min()).days
        if span_days < 30:
            reasons_blocking.append(
                f"Weather temporal coverage is only ~{span_days} day(s) in this bounded Stage 11B "
                f"ingestion -- inadequate for a real training window (NOAA NCEI ISD historical "
                f"backfill, not yet implemented, is required first)."
            )

    events = tables.get("operational_events")
    n_labeled_capable = 0
    if events is not None and not events.empty:
        n_labeled_capable = int(events["label_available"].sum())
    if n_labeled_capable < 10_000:
        reasons_blocking.append(
            f"Only {n_labeled_capable:,} operational_events rows are in a label-capable mode in "
            f"this bounded ingestion -- likely insufficient for a real training run even once the "
            f"threshold policy is approved (compare to the synthetic dataset's 272,160-row TRAIN "
            f"split alone); a deeper historical pull (the full LAMP_ALL_Bus_Events / a longer "
            f"subway index range) is needed first."
        )

    model_ready = len(reasons_blocking) == 0
    return {
        "MODEL_READY": model_ready,
        "model_ready": model_ready,
        "primary_reason": reasons_blocking[0] if reasons_blocking else "All readiness conditions satisfied.",
        "blocking_reasons": reasons_blocking,
        "satisfied_conditions": reasons_ok,
        "next_steps": [
            "Human review + approval of a real-world disruption-label threshold (Stage 11B §12), "
            "informed by data/interim/real/eda_report.json's delay-by-mode distributions.",
            "Implement real historical_delay_minutes/rolling_7d_delay_minutes/historical_reliability "
            "computation for the 3 label-available modes (Stage 12 scope) -- reusing "
            "src/features/historical.py's leakage-safe shift(1) pattern unchanged.",
            "Pull a deeper historical window (full LAMP_ALL_Bus_Events + a longer subway index "
            "range) and a deeper weather backfill (NOAA NCEI ISD) before attempting a real "
            "training run.",
            "Explicitly decide (not assume) how rail/ferry participate in training given no real "
            "label source -- exclude them from supervised training entirely, or extend the "
            "labels-unavailable INFERENCE mode (already built, Stage 9) to training too.",
        ],
    }

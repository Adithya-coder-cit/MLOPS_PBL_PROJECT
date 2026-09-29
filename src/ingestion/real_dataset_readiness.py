"""Stage 11E Part 10: REAL_DATASET_READY -- an evidence-based decision
about whether the real dataset is ready for model *training* to begin,
distinct from (and less strict than) MODEL_READY
(src.ingestion.model_readiness), which additionally requires >= 80%
weather coverage before a model may actually be trained/promoted. This
module explicitly does NOT require near-perfect weather coverage --
Stage 11E's instruction is to judge readiness on the full body of
evidence (labels, eligible-record count, a legitimate missing-value
strategy for sparse features, historical-feature coverage, leakage
tests, schema stability, provenance, rail/ferry treatment), with weather
coverage reported as one input among several rather than a single gate.
"""
from __future__ import annotations

import pandas as pd

from src.ingestion.feature_eligibility import INCLUDE_WITH_STRATEGY
from src.ingestion.model_readiness import (
    MINIMUM_HISTORICAL_FEATURE_COVERAGE,
    MINIMUM_LABELED_RECORDS,
    _feature_schema_stable_check,
    _leakage_smoke_check,
    _target_not_fabricated_check,
)


def build_real_dataset_readiness_decision(
    training_table: pd.DataFrame,
    eligible: pd.DataFrame,
    feature_coverage_report: dict,
    feature_strategy: dict,
    label_verification: dict,
    weather_coverage: float,
    split_boundaries: dict | None,
    split_error: str | None,
    eligible_split_summary: dict | None = None,
) -> dict:
    reasons_blocking: list[str] = []
    reasons_ok: list[str] = []
    caveats: list[str] = []

    if eligible_split_summary:
        all_modes = set(eligible["transport_mode"].unique()) if not eligible.empty else set()
        for split_name, summary in eligible_split_summary.items():
            missing_modes = all_modes - set(summary.get("mode_distribution", {}))
            if missing_modes:
                caveats.append(
                    f"Mode(s) {sorted(missing_modes)} have ZERO eligible records in the '{split_name}' "
                    f"split -- NOT a blocking condition per Task 10's criteria, but a model trained/"
                    f"evaluated on this split would see no examples of that mode there. Root cause "
                    f"(measured): the real bus historical-performance source "
                    f"(LAMP_RECENT_Bus_Events.parquet, Stage 11B) is a bounded ~7-9 day rolling window, "
                    f"not the deep archive subway/tram have -- that window falls entirely inside "
                    f"whichever split covers the most recent dates. See eligible_temporal_split.json."
                )

    labels_valid = label_verification.get("all_consistency_checks_passed", False)
    labels_msg = ("all modes match the recomputed disruption_flag" if labels_valid
                  else "MISMATCH found -- see label_verification_report.json")
    (reasons_ok if labels_valid else reasons_blocking).append(f"Frozen label policy consistency check: {labels_msg}.")

    n_eligible = len(eligible)
    sufficient_records = n_eligible >= MINIMUM_LABELED_RECORDS
    (reasons_ok if sufficient_records else reasons_blocking).append(
        f"{n_eligible:,} eligible supervised records (bar: >= {MINIMUM_LABELED_RECORDS:,})."
    )

    hist_features = ["historical_delay_seconds", "rolling_7d_delay_seconds"]
    hist_coverages = [feature_coverage_report[f]["coverage"] for f in hist_features
                       if f in feature_coverage_report]
    min_hist_coverage = min(hist_coverages) if hist_coverages else 0.0
    hist_ok = min_hist_coverage >= MINIMUM_HISTORICAL_FEATURE_COVERAGE
    (reasons_ok if hist_ok else reasons_blocking).append(
        f"Historical-delay feature coverage is {min_hist_coverage:.1%} "
        f"(bar: >= {MINIMUM_HISTORICAL_FEATURE_COVERAGE:.0%})."
    )

    strategy_features_with_missing_handling = [
        f for f, s in feature_strategy.items() if s["strategy"] == INCLUDE_WITH_STRATEGY
    ]
    strategy_documented = all(
        feature_strategy[f].get("missing_value_handling") for f in strategy_features_with_missing_handling
    )
    reasons_ok.append(
        f"Every INCLUDE_WITH_STRATEGY feature ({strategy_features_with_missing_handling}) has a "
        f"documented missing-value handling strategy: {strategy_documented}."
    ) if strategy_documented else reasons_blocking.append(
        "One or more INCLUDE_WITH_STRATEGY features are missing a documented missing-value strategy."
    )

    # Weather coverage is reported, NOT a hard gate -- explicit per Task 10.
    reasons_ok.append(
        f"Weather coverage is {weather_coverage:.1%} -- reported as evidence, not required to clear "
        f"any fixed bar for REAL_DATASET_READY (unlike the stricter MODEL_READY gate)."
    )

    leak_ok, leak_msg = _leakage_smoke_check(training_table)
    (reasons_ok if leak_ok else reasons_blocking).append(f"Leakage smoke check: {leak_msg}")

    fab_ok, fab_msg = _target_not_fabricated_check(training_table)
    (reasons_ok if fab_ok else reasons_blocking).append(f"Target-not-fabricated check: {fab_msg}")

    schema_ok, schema_msg = _feature_schema_stable_check(training_table)
    (reasons_ok if schema_ok else reasons_blocking).append(f"Feature-schema-stable check: {schema_msg}")

    if split_error:
        reasons_blocking.append(f"Temporal split on eligible records could not be constructed: {split_error}")
    else:
        reasons_ok.append(f"Temporal split on eligible records constructed: {split_boundaries}")

    has_provider = "source_provider" in eligible.columns and len(eligible)
    has_dataset_type = "source_dataset_type" in eligible.columns and len(eligible)
    provenance_ok = bool(
        (eligible["source_provider"].notna().all() if has_provider else True)
        and (eligible["source_dataset_type"].eq("REAL").all() if has_dataset_type else True)
    )
    prov_msg = (f"Provenance columns (source_provider, source_dataset_type='REAL') complete for all "
                f"eligible rows: {provenance_ok}.")
    (reasons_ok if provenance_ok else reasons_blocking).append(prov_msg)

    rail_ferry_modes = {"rail", "ferry"}
    present_modes = set(training_table["transport_mode"].unique()) if not training_table.empty else set()
    rail_ferry_ok = True
    for mode in rail_ferry_modes & present_modes:
        group = training_table[training_table["transport_mode"] == mode]
        if group["label_available"].any() or group["disruption_flag"].notna().any():
            rail_ferry_ok = False
    rf_msg = (f"Rail/ferry treatment correct (label_available=False, disruption_flag=NULL, never "
              f"fabricated): {rail_ferry_ok}.")
    (reasons_ok if rail_ferry_ok else reasons_blocking).append(rf_msg)

    real_dataset_ready = len(reasons_blocking) == 0
    primary_reason = reasons_blocking[0] if reasons_blocking else "All evidence-based readiness conditions satisfied."
    return {
        "REAL_DATASET_READY": real_dataset_ready,
        "real_dataset_ready": real_dataset_ready,
        "primary_reason": primary_reason,
        "blocking_reasons": reasons_blocking,
        "satisfied_conditions": reasons_ok,
        "caveats_non_blocking": caveats,
        "criteria_checked": {
            "valid_real_labels": labels_valid,
            "sufficient_labeled_records": sufficient_records,
            "historical_feature_coverage_acceptable": hist_ok,
            "legitimate_missing_value_strategy": strategy_documented,
            "leakage_tests_pass": leak_ok,
            "target_not_fabricated": fab_ok,
            "feature_schema_stable": schema_ok,
            "temporal_split_constructible": split_error is None,
            "provenance_complete": provenance_ok,
            "rail_ferry_treatment_correct": rail_ferry_ok,
        },
        "weather_coverage_informational": weather_coverage,
        "n_eligible_records": n_eligible,
        "note": "REAL_DATASET_READY does NOT require near-complete weather coverage -- it judges the "
                "full body of evidence, with weather coverage reported rather than gated. "
                "MODEL_READY (src.ingestion.model_readiness) remains the stricter, separate gate "
                "that DOES require >= 80% weather coverage before training/promotion; the two "
                "decisions are independent and intentionally not equal to each other. Neither "
                "decision authorizes training a model -- no model is trained in this stage.",
    }

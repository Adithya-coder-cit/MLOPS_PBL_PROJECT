"""Stage 11F §17: REAL_SUPERVISED_SPLIT_READY -- a third, distinct
readiness decision (alongside MODEL_READY and REAL_DATASET_READY) that
answers one specific question: does EVERY mode this project trains a
supervised model on (bus, metro, tram) have genuine, real, non-zero
eligible records in ALL THREE chronological splits (train/validation/
test)? This is the exact problem Stage 11F set out to fix -- bus
previously had zero eligible train/validation records because its only
real historical-performance source was a ~7-day rolling window that
fell entirely inside the test period.

Deliberately separate from REAL_DATASET_READY (which treats a mode
missing from a split as a non-blocking caveat, not a blocker -- see
src.ingestion.real_dataset_readiness) and from MODEL_READY (the
stricter weather-gated decision -- see src.ingestion.model_readiness).
Neither existing decision is modified by this module; this is an
additive, narrower check, and does not by itself authorize training.
"""
from __future__ import annotations

import pandas as pd

from src.ingestion.model_readiness import _feature_schema_stable_check, _leakage_smoke_check

SUPERVISED_MODES = ["bus", "metro", "tram"]
REQUIRED_SPLITS = ["train", "val", "test"]


def build_real_supervised_split_readiness_decision(
    training_table: pd.DataFrame,
    eligible: pd.DataFrame,
    eligible_split_summary: dict,
    eligible_split_error: str | None,
    label_verification: dict,
    bus_dedup_summary: dict,
) -> dict:
    reasons_blocking: list[str] = []
    reasons_ok: list[str] = []

    genuine_bus_history = bus_dedup_summary.get("records_before", 0) > 0
    (reasons_ok if genuine_bus_history else reasons_blocking).append(
        f"Genuine historical bus data ingested: {genuine_bus_history} "
        f"({bus_dedup_summary.get('records_before', 0):,} raw bus events before dedup)."
    )

    per_mode_split_counts: dict[str, dict[str, int]] = {mode: {} for mode in SUPERVISED_MODES}
    split_presence_ok = True
    if eligible_split_error:
        split_presence_ok = False
        reasons_blocking.append(f"Eligible-dataset temporal split could not be constructed: {eligible_split_error}")
    else:
        for split_name in REQUIRED_SPLITS:
            split_info = eligible_split_summary.get(split_name, {})
            mode_dist = split_info.get("mode_distribution", {})
            for mode in SUPERVISED_MODES:
                count = int(mode_dist.get(mode, 0))
                per_mode_split_counts[mode][split_name] = count
                if count <= 0:
                    split_presence_ok = False
                    reasons_blocking.append(
                        f"{mode} has ZERO eligible records in the '{split_name}' split "
                        f"(bar: > 0) -- see eligible_temporal_split.json."
                    )
                else:
                    reasons_ok.append(f"{mode} has {count:,} eligible records in the '{split_name}' split.")

    labels_genuine = label_verification.get("all_consistency_checks_passed", False)
    (reasons_ok if labels_genuine else reasons_blocking).append(
        f"Labels genuine (frozen-policy consistency check passed): {labels_genuine}."
    )

    leak_ok, leak_msg = _leakage_smoke_check(training_table)
    (reasons_ok if leak_ok else reasons_blocking).append(f"Historical-feature leakage tests pass: {leak_msg}")

    has_provider = "source_provider" in eligible.columns and len(eligible)
    has_dataset_type = "source_dataset_type" in eligible.columns and len(eligible)
    provenance_ok = bool(
        (eligible["source_provider"].notna().all() if has_provider else True)
        and (eligible["source_dataset_type"].eq("REAL").all() if has_dataset_type else True)
    )
    (reasons_ok if provenance_ok else reasons_blocking).append(
        f"Provenance complete for all eligible rows: {provenance_ok}."
    )

    schema_ok, schema_msg = _feature_schema_stable_check(training_table)
    (reasons_ok if schema_ok else reasons_blocking).append(f"Feature schema stable: {schema_msg}")

    real_supervised_split_ready = len(reasons_blocking) == 0
    primary_reason = (
        reasons_blocking[0] if reasons_blocking
        else "All modes (bus, metro, tram) have genuine eligible records in train, validation, and test."
    )

    return {
        "REAL_SUPERVISED_SPLIT_READY": real_supervised_split_ready,
        "real_supervised_split_ready": real_supervised_split_ready,
        "primary_reason": primary_reason,
        "blocking_reasons": reasons_blocking,
        "satisfied_conditions": reasons_ok,
        "criteria_checked": {
            "genuine_historical_bus_data_exists": genuine_bus_history,
            "chronological_split_valid": eligible_split_error is None,
            "all_modes_all_splits_present": split_presence_ok,
            "labels_genuine": labels_genuine,
            "leakage_tests_pass": leak_ok,
            "provenance_complete": provenance_ok,
            "schema_stable": schema_ok,
        },
        "per_mode_split_record_counts": per_mode_split_counts,
        "note": "REAL_SUPERVISED_SPLIT_READY answers a narrower question than REAL_DATASET_READY: "
                "not just 'is the dataset evidence-based and usable' but 'does every supervised mode "
                "genuinely appear in every chronological split.' This decision does not itself "
                "authorize training -- MODEL_READY (the stricter, separately-gated weather-coverage "
                "check) remains the decision that gates training/promotion, and is unchanged by this "
                "module.",
    }

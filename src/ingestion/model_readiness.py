"""Stage 11B/11C §20/K: the model readiness gate. Training must never
proceed merely because ingestion succeeded -- this module makes that
decision explicit, reasoned, and machine-readable, against ALL of Stage
11C's required conditions.
"""
from __future__ import annotations

import pandas as pd

# Engineering bars, documented here (not scattered through the codebase)
# so the gate's actual pass/fail numbers are traceable to one place.
MINIMUM_LABELED_RECORDS = 50_000
MINIMUM_HISTORICAL_FEATURE_COVERAGE = 0.50
MINIMUM_WEATHER_COVERAGE = 0.80


def _leakage_smoke_check(training_table: pd.DataFrame) -> tuple[bool, str]:
    """A lightweight, in-process structural leakage check, defense-in-depth
    alongside (not a replacement for) tests/test_real_ingestion.py's
    dedicated leakage tests: for every route, its FIRST observed
    service_date must have a null historical_delay_seconds (there is no
    strictly-prior day to compute it from) -- if any route's first day has
    a non-null value, the shift(1) discipline has been violated somewhere.
    """
    if "historical_delay_seconds" not in training_table.columns or training_table.empty:
        return True, "no historical_delay_seconds column present -- nothing to check yet."
    # NOTE: deliberately NOT groupby().first() -- its default skipna=True
    # returns the first NON-NULL value per column within each group, which
    # would silently skip past a correctly-NaN first day and grab a later
    # day's value instead, turning this into a false-positive generator.
    # drop_duplicates(keep="first") after sorting takes the actual first row.
    # Memory: project to the 3 columns this check reads before sorting --
    # sorting all 25 columns of a 20M+-row table is a full-frame copy.
    slim = training_table[["route_id", "service_date", "historical_delay_seconds"]]
    first_days = slim.sort_values("service_date").drop_duplicates("route_id", keep="first")
    violations = first_days[first_days["historical_delay_seconds"].notna()]
    if len(violations) > 0:
        return False, f"{len(violations)} route(s) have a non-null historical_delay_seconds on their " \
                       f"FIRST observed service_date -- this should be impossible under shift(1) and " \
                       f"indicates a leakage regression."
    return True, f"Verified: all {len(first_days)} routes' first observed service_date has a null " \
                 f"historical_delay_seconds (no strictly-prior day exists to compute it from)."


def _target_not_fabricated_check(training_table: pd.DataFrame) -> tuple[bool, str]:
    if "label_available" not in training_table.columns or "disruption_flag" not in training_table.columns:
        return False, "label_available/disruption_flag columns missing."
    violating = training_table[(~training_table["label_available"]) & training_table["disruption_flag"].notna()]
    if len(violating) > 0:
        return False, f"{len(violating)} row(s) with label_available=False have a non-null " \
                       f"disruption_flag -- a fabricated label."
    return True, "Verified: every row with label_available=False has disruption_flag=NULL."


def _feature_schema_stable_check(training_table: pd.DataFrame) -> tuple[bool, str]:
    from src.ingestion.training_table import TRAINING_TABLE_SCHEMA
    expected = {f["name"] for f in TRAINING_TABLE_SCHEMA}
    actual = set(training_table.columns)
    missing = expected - actual
    if missing:
        return False, f"Training table is missing documented column(s): {sorted(missing)}."
    return True, f"All {len(expected)} documented training-table columns are present."


def build_model_readiness_decision(
    training_table: pd.DataFrame, issues: list, feature_matrix: dict, cfg: dict,
    weather_coverage: float, split_boundaries: dict | None, split_error: str | None,
) -> dict:
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
            "(configs/real_data.yaml real_disruption_label_policy.active=false) -- see "
            "data/interim/real/label_candidate_report.json and label_policy_recommendation.json "
            "for the analysis a human should review before activating it."
        )
    else:
        reasons_ok.append("Real disruption-label policy is active (approved).")

    n_labeled = int(training_table["disruption_flag"].notna().sum()) if "disruption_flag" in \
        training_table.columns else 0
    if n_labeled < MINIMUM_LABELED_RECORDS:
        reasons_blocking.append(
            f"Only {n_labeled:,} rows have a real, non-null disruption_flag -- below the configured "
            f"minimum of {MINIMUM_LABELED_RECORDS:,} (compare to the synthetic TRAIN split's 272,160 "
            f"rows). This count is necessarily 0 while the label policy is inactive."
        )
    else:
        reasons_ok.append(f"{n_labeled:,} rows have a real, non-null disruption_flag (>= "
                           f"{MINIMUM_LABELED_RECORDS:,}).")

    hist_rows = [r for r in feature_matrix["model_input_features"]
                 if r["feature"] in ("historical_delay_seconds", "rolling_7d_delay_seconds")]
    min_hist_coverage = min((r["coverage"] for r in hist_rows), default=0.0)
    if min_hist_coverage < MINIMUM_HISTORICAL_FEATURE_COVERAGE:
        reasons_blocking.append(
            f"Historical-delay feature coverage is only {min_hist_coverage:.1%} (minimum bar: "
            f"{MINIMUM_HISTORICAL_FEATURE_COVERAGE:.0%}) -- either too few strictly-prior days exist "
            f"yet in the real ingestion window, or too many routes fall below the minimum-history "
            f"policy (src.ingestion.sparsity)."
        )
    else:
        reasons_ok.append(f"Historical-delay feature coverage is {min_hist_coverage:.1%} "
                           f"(>= {MINIMUM_HISTORICAL_FEATURE_COVERAGE:.0%}).")

    if weather_coverage < MINIMUM_WEATHER_COVERAGE:
        reasons_blocking.append(
            f"Weather feature coverage over the real ingested window is only {weather_coverage:.1%} "
            f"(minimum bar: {MINIMUM_WEATHER_COVERAGE:.0%}). Stage 11D integrated NOAA GHCNh (a real "
            f"official archive that DOES cover the transit window, confirmed by direct download) "
            f"alongside NWS, roughly doubling coverage from Stage 11C's 13.5% -- but GHCNh's Boston "
            f"Logan feed interleaves many partial reports (wind-direction-only, etc.) with fewer rows "
            f"that actually carry temperature/precipitation/visibility together, leaving real gaps "
            f"wider than the configured asof-join tolerance on many hours/days -- see "
            f"data/interim/real/weather_coverage_report.json (coverage_by_date/coverage_by_hour) for "
            f"the measured gap structure. No fabricated weather was substituted to close it."
        )
    else:
        reasons_ok.append(f"Weather feature coverage is {weather_coverage:.1%} (>= "
                           f"{MINIMUM_WEATHER_COVERAGE:.0%}).")

    leak_ok, leak_msg = _leakage_smoke_check(training_table)
    (reasons_ok if leak_ok else reasons_blocking).append(f"Leakage smoke check: {leak_msg}")

    fab_ok, fab_msg = _target_not_fabricated_check(training_table)
    (reasons_ok if fab_ok else reasons_blocking).append(f"Target-not-fabricated check: {fab_msg}")

    schema_ok, schema_msg = _feature_schema_stable_check(training_table)
    (reasons_ok if schema_ok else reasons_blocking).append(f"Feature-schema-stable check: {schema_msg}")

    if split_error:
        reasons_blocking.append(f"Temporal split could not be constructed: {split_error}")
    else:
        reasons_ok.append(f"Temporal split constructed: {split_boundaries}")

    modes_without_labels = [m for m, v in cfg["label_availability"].items() if not v]
    if modes_without_labels:
        reasons_blocking.append(
            f"No verified historical-label source exists for mode(s) {modes_without_labels} (rail, "
            f"ferry) -- they remain in the routing graph (never removed) but are excluded from the "
            f"trainable subset entirely; this is a standing, documented limitation, not a blocker "
            f"resolved by this stage (it requires a genuinely new data source, not more engineering)."
        )

    model_ready = len(reasons_blocking) == 0
    return {
        "MODEL_READY": model_ready,
        "model_ready": model_ready,
        "primary_reason": reasons_blocking[0] if reasons_blocking else "All readiness conditions satisfied.",
        "blocking_reasons": reasons_blocking,
        "satisfied_conditions": reasons_ok,
        "criteria_checked": {
            "approved_label_definition": label_policy_active,
            "sufficient_labeled_records": n_labeled >= MINIMUM_LABELED_RECORDS,
            "historical_features_acceptable_coverage": min_hist_coverage >= MINIMUM_HISTORICAL_FEATURE_COVERAGE,
            "weather_coverage_adequate": weather_coverage >= MINIMUM_WEATHER_COVERAGE,
            "no_critical_validation_errors": len(errors) == 0,
            "leakage_tests_pass": leak_ok,
            "temporal_split_constructible": split_error is None,
            "target_not_fabricated": fab_ok,
            "feature_schema_stable": schema_ok,
        },
        "next_steps": [
            "Human review + approval of the real-world disruption-label threshold "
            "(data/interim/real/label_policy_recommendation.json).",
            "Either widen the weather asof-join tolerance (configs/real_data.yaml "
            "weather_join.max_time_difference_hours, currently 2h) with an explicit, documented "
            "rationale for the wider window, or accept the current ~27% weather coverage and "
            "re-evaluate the readiness bar explicitly (data/interim/real/weather_coverage_report.json "
            "has the full per-date/per-hour gap structure) -- rather than silently lowering "
            "MINIMUM_WEATHER_COVERAGE without that documented decision.",
            "Continue accumulating real historical-performance data over time (both subway and bus) "
            "to grow n_labeled and historical-feature coverage past the configured minimums.",
            "Explicitly decide (not assume) how rail/ferry participate in training given no real "
            "label source -- exclude them from supervised training entirely, or extend the "
            "labels-unavailable INFERENCE mode (already built, Stage 9) to training too.",
        ],
    }

"""Stage 11E Parts 1/2/4: measures real per-feature coverage at a finer
grain than a single global number (by mode, by chronological split period,
and -- for the features named in the Stage 11E brief -- by date), then
applies an evidence-based, documented strategy per feature (INCLUDE
directly / INCLUDE with a missing-value strategy / EXCLUDE / DIAGNOSTIC
ONLY) rather than picking whatever maximizes apparent model performance.
Finally defines the reproducible row-eligibility rule for the real
supervised-training dataset.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.ingestion.training_table import MODEL_FEATURE_COLUMNS

# Named explicitly in the Stage 11E brief for a per-date breakdown, on top
# of the by-mode/by-split breakdown every model feature gets.
SPARSE_FEATURES_OF_INTEREST = [
    "precipitation_mm", "temperature_c", "visibility_km", "wind_speed_ms", "pressure_hpa",
    "historical_delay_seconds", "rolling_7d_delay_seconds", "historical_reliability",
]

INCLUDE_DIRECTLY = "INCLUDED_DIRECTLY"
INCLUDE_WITH_STRATEGY = "INCLUDED_WITH_MISSING_VALUE_STRATEGY"
EXCLUDE = "EXCLUDED"
DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"

# Evidence-based bands, not tuned for any particular model's apparent
# performance -- documented here as the single source of truth.
COVERAGE_INCLUDE_DIRECTLY = 0.95
COVERAGE_INCLUDE_WITH_STRATEGY = 0.50
COVERAGE_DIAGNOSTIC_ONLY_FLOOR = 0.05


def _split_label(d: date, boundaries: dict) -> str:
    train_end = date.fromisoformat(boundaries["train_end"])
    val_end = date.fromisoformat(boundaries["val_end"])
    if d <= train_end:
        return "train"
    if d <= val_end:
        return "val"
    return "test"


def build_feature_coverage_report(training_table: pd.DataFrame, split_boundaries: dict | None) -> dict:
    """Stage 11E Part 1: per-feature coverage -- never global-only. Every
    src.ingestion.training_table.MODEL_FEATURE_COLUMNS entry gets
    total/non-null/missing/coverage, coverage by mode, and coverage by
    chronological split period; the features named explicitly in the
    Stage 11E brief additionally get coverage by date.
    """
    report: dict = {}
    dates = None
    if split_boundaries is not None and "service_date" in training_table.columns:
        dates = pd.to_datetime(training_table["service_date"]).dt.date

    for feature in MODEL_FEATURE_COLUMNS:
        if feature not in training_table.columns:
            report[feature] = {"total_rows": int(len(training_table)), "non_null_rows": 0,
                                "missing_rows": int(len(training_table)), "coverage": 0.0,
                                "note": "column entirely absent from the real training table"}
            continue

        series = training_table[feature]
        total = int(len(series))
        non_null = int(series.notna().sum())
        entry = {
            "total_rows": total,
            "non_null_rows": non_null,
            "missing_rows": total - non_null,
            "coverage": float(non_null / total) if total else 0.0,
            "coverage_by_mode": {
                str(mode): float(group.notna().mean())
                for mode, group in training_table.groupby("transport_mode")[feature]
            },
        }

        if split_boundaries is not None and dates is not None:
            split_labels = dates.map(lambda d: _split_label(d, split_boundaries))
            entry["coverage_by_split"] = {
                str(split): float(training_table.loc[split_labels == split, feature].notna().mean())
                for split in ["train", "val", "test"]
                if (split_labels == split).any()
            }

        if feature in SPARSE_FEATURES_OF_INTEREST and dates is not None:
            entry["coverage_by_date"] = {
                str(d): float(group.notna().mean())
                for d, group in training_table.groupby(dates)[feature]
            }

        report[feature] = entry

    return report


def recommend_feature_strategy(coverage_report: dict) -> dict:
    """Stage 11E Part 2: evidence-based strategy per feature, from the
    measured global coverage in `coverage_report` -- never chosen to
    maximize apparent model performance. Structural features that were
    never actually wired into the real ingestion pipeline (0% coverage
    for a reason unrelated to real-world data sparsity -- e.g. day_period,
    time_of_day_bucket, transfer_dependency) are flagged distinctly from
    genuinely sparse real-world measurements (weather).
    """
    strategies = {}
    for feature, entry in coverage_report.items():
        coverage = entry["coverage"]

        if feature in ("day_period", "time_of_day_bucket", "transfer_dependency") and coverage == 0.0:
            strategies[feature] = {
                "strategy": EXCLUDE,
                "coverage": coverage,
                "rationale": f"{feature} is 0% covered not because of real-world data sparsity but "
                             f"because this structural feature was never wired into the real (non-"
                             f"synthetic) ingestion pipeline -- src.ingestion.run_real_ingestion does "
                             f"not yet call the Stage-3 derivation this feature needs. Excluded from "
                             f"the real model until that gap is closed in a future stage; NOT the "
                             f"same situation as a feature with genuine measured sparsity.",
                "missing_value_handling": None,
            }
            continue

        if feature == "historical_reliability" and coverage == 0.0:
            strategies[feature] = {
                "strategy": EXCLUDE,
                "coverage": coverage,
                "rationale": "historical_reliability requires the disruption-label policy to be "
                             "active (it is computed from disruption_flag, not delay_seconds "
                             "directly) -- if this report was generated before the label policy "
                             "was frozen/activated (Stage 11E), coverage is 0% for that structural "
                             "reason, not sparsity. Re-run after activation before trusting this "
                             "entry; see historical_delay_seconds' coverage for what this feature's "
                             "coverage should resemble once active.",
                "missing_value_handling": None,
            }
            continue

        if coverage >= COVERAGE_INCLUDE_DIRECTLY:
            strategy, handling = INCLUDE_DIRECTLY, None
        elif coverage >= COVERAGE_INCLUDE_WITH_STRATEGY:
            strategy = INCLUDE_WITH_STRATEGY
            handling = ("XGBoost: pass NaN through natively (its split-finding algorithm learns a "
                        "default direction for missing values, no imputation needed). Random Forest "
                        "(via the existing sklearn preprocessing pipeline): impute with a TRAIN-fit "
                        "median/most-frequent value plus an explicit missing-indicator column, per "
                        "the established synthetic-pipeline discipline (src/preprocessing) -- never "
                        "impute with a fixed global constant computed across train+val+test.")
        elif coverage >= COVERAGE_DIAGNOSTIC_ONLY_FLOOR:
            strategy, handling = DIAGNOSTIC_ONLY, None
        else:
            strategy, handling = EXCLUDE, None

        band = (f">= {COVERAGE_INCLUDE_DIRECTLY:.0%}" if strategy == INCLUDE_DIRECTLY else
                f">= {COVERAGE_INCLUDE_WITH_STRATEGY:.0%}" if strategy == INCLUDE_WITH_STRATEGY else
                f">= {COVERAGE_DIAGNOSTIC_ONLY_FLOOR:.0%}" if strategy == DIAGNOSTIC_ONLY else
                f"< {COVERAGE_DIAGNOSTIC_ONLY_FLOOR:.0%}")
        strategies[feature] = {
            "strategy": strategy,
            "coverage": coverage,
            "rationale": f"Measured real coverage {coverage:.1%} falls in the {band} band.",
            "missing_value_handling": handling,
        }

    return strategies


# Features whose absence does NOT disqualify a row from the eligible
# supervised dataset -- their strategy is INCLUDE_WITH_STRATEGY or
# DIAGNOSTIC_ONLY, meaning a null value there is handled at model-input
# time (native NaN handling / imputation), not by dropping the row.
NON_GATING_STRATEGIES = {INCLUDE_WITH_STRATEGY, DIAGNOSTIC_ONLY, EXCLUDE}


def build_eligible_dataset(
    training_table: pd.DataFrame, feature_strategy: dict, minimum_history_days: int,
) -> pd.DataFrame:
    """Stage 11E Part 4: the reproducible row-eligibility rule --

        label_available AND disruption_flag.notna()
        AND scheduled_time.notna()
        AND historical features valid per the minimum-history policy
        AND every INCLUDE_DIRECTLY feature present (features handled via a
            documented missing-value strategy, diagnostic-only, or excluded
            do NOT gate row eligibility -- their nulls are legitimate,
            handled at model-input time, not grounds for dropping the row)

    Never drops a row merely because a DIAGNOSTIC_ONLY or
    INCLUDE_WITH_STRATEGY feature happens to be null for that row -- that
    would silently discard most of the real dataset to chase 100% weather
    coverage, contradicting Part 4's explicit instruction.
    """
    from src.ingestion.sparsity import history_status_per_row

    df = training_table
    mask = df["label_available"] & df["disruption_flag"].notna() & df["scheduled_time"].notna()

    history_status = history_status_per_row(df, minimum_history_days)
    mask &= history_status == "valid"

    gating_features = [f for f, s in feature_strategy.items() if s["strategy"] == INCLUDE_DIRECTLY]
    for feature in gating_features:
        if feature in df.columns:
            mask &= df[feature].notna()

    return df[mask]


def build_eligibility_report(training_table: pd.DataFrame, eligible: pd.DataFrame, minimum_history_days: int) -> dict:
    """Stage 11E Part 4: total/eligible/excluded records and WHY, broken
    down by reason -- reasons are not mutually exclusive (a row can be
    excluded for more than one reason simultaneously), so percentages
    below can sum to more than the total exclusion count.
    """
    from src.ingestion.sparsity import history_status_per_row

    total = len(training_table)
    eligible_n = len(eligible)
    excluded_n = total - eligible_n

    label_unavailable = int((~training_table["label_available"]).sum())
    label_null_despite_available = int(
        (training_table["label_available"] & training_table["disruption_flag"].isna()).sum()
    )
    history_status = history_status_per_row(training_table, minimum_history_days)
    insufficient_history = int((history_status != "valid").sum())

    return {
        "total_real_records": int(total),
        "eligible_records": int(eligible_n),
        "excluded_records": int(excluded_n),
        "exclusion_percentage": float(excluded_n / total) if total else None,
        "exclusion_reasons": {
            "label_unavailable_mode_rail_ferry": label_unavailable,
            "label_null_despite_label_available_policy_inactive_or_no_threshold": label_null_despite_available,
            "insufficient_or_zero_historical_feature_history": insufficient_history,
        },
        "note": "Exclusion reasons are not mutually exclusive -- a row can be counted in more than "
                "one reason (e.g. a rail row is both label_unavailable and, trivially, excluded "
                "from the historical-feature aggregate entirely). eligible_records + excluded_records "
                "always equals total_real_records; the per-reason counts do not necessarily sum to "
                "excluded_records.",
    }

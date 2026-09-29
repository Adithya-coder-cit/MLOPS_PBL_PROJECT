"""Stage 11C Part D: real-world observation-density measurement and the
minimum-history policy. Never fabricates missing history -- routes below
the configured minimum simply carry NaN historical features (already
enforced by src.ingestion.historical_features's shift/min_periods
behavior); this module measures and reports the sparsity, and defines
the threshold used, rather than papering over it.
"""
from __future__ import annotations

import pandas as pd

# An engineering choice, not derived from theory: a route needs at least
# this many strictly-prior observed service_dates before its rolling/
# expanding historical features are considered minimally meaningful.
# Documented here as the single source of truth for the minimum-history
# policy (src.ingestion.historical_features.join_historical_features
# takes this as an explicit argument, never a silently-duplicated default).
MINIMUM_HISTORY_DAYS = 3


def observations_per_route(operational_events: pd.DataFrame) -> pd.DataFrame:
    usable = operational_events[operational_events["label_available"]]
    return (
        usable.groupby("route_id").size().reset_index(name="n_observations")
        .sort_values("n_observations", ascending=False)
    )


def observations_per_stop(operational_events: pd.DataFrame) -> pd.DataFrame:
    usable = operational_events[operational_events["label_available"]]
    return (
        usable.groupby("stop_id").size().reset_index(name="n_observations")
        .sort_values("n_observations", ascending=False)
    )


def observations_per_day(operational_events: pd.DataFrame) -> pd.DataFrame:
    usable = operational_events[operational_events["label_available"]]
    return (
        usable.groupby("service_date").size().reset_index(name="n_observations")
        .sort_values("service_date")
    )


def routes_with_insufficient_history(
    operational_events: pd.DataFrame, minimum_history_days: int = MINIMUM_HISTORY_DAYS,
) -> list[str]:
    usable = operational_events[operational_events["label_available"] & operational_events["delay_seconds"].notna()]
    n_days_per_route = usable.groupby("route_id")["service_date"].nunique()
    return sorted(n_days_per_route[n_days_per_route < minimum_history_days].index.tolist())


def history_status_per_row(training_table: pd.DataFrame, minimum_history_days: int = MINIMUM_HISTORY_DAYS) -> pd.Series:
    """Stage 11E Part 5: per-row history status -- 'zero' (this is the
    route's very first observed service_date, 0 strictly-prior days),
    'insufficient' (1..minimum_history_days-1 prior days -- below the
    policy bar), or 'valid' (>= minimum_history_days prior days). Computed
    from the route's cumulative count of distinct PRIOR service_dates,
    the same quantity src.ingestion.historical_features's shift(1) +
    min_periods discipline is keyed on -- never fabricated, never inferred
    from historical_delay_seconds being null (which could also be null
    for other reasons, e.g. label_available=False).
    """
    unique_dates = (
        training_table[["route_id", "service_date"]].drop_duplicates()
        .sort_values(["route_id", "service_date"])
    )
    unique_dates["prior_day_count"] = unique_dates.groupby("route_id").cumcount()
    merged = training_table[["route_id", "service_date"]].merge(
        unique_dates, on=["route_id", "service_date"], how="left",
    )

    def _status(n: int) -> str:
        if n >= minimum_history_days:
            return "valid"
        return "zero" if n == 0 else "insufficient"

    return merged["prior_day_count"].map(_status)


def build_history_status_report(training_table: pd.DataFrame, minimum_history_days: int = MINIMUM_HISTORY_DAYS) -> dict:
    """Stage 11E Part 5: reports records with zero/insufficient/valid
    history, by mode and by route -- never fabricates history to fill a
    gap, only measures and reports it."""
    status = history_status_per_row(training_table, minimum_history_days)
    df = training_table.assign(_history_status=status)

    counts = df["_history_status"].value_counts().to_dict()
    by_mode = (
        df.groupby(["transport_mode", "_history_status"]).size()
        .unstack(fill_value=0).to_dict(orient="index")
    )
    by_route_insufficient = (
        df[df["_history_status"].isin(["zero", "insufficient"])]
        .groupby("route_id").size().sort_values(ascending=False)
    )

    return {
        "minimum_history_days_policy": minimum_history_days,
        "total_records": int(len(df)),
        "records_with_zero_history": int(counts.get("zero", 0)),
        "records_with_insufficient_history": int(counts.get("insufficient", 0)),
        "records_with_valid_history": int(counts.get("valid", 0)),
        "coverage_by_mode": {str(mode): {str(k): int(v) for k, v in statuses.items()}
                             for mode, statuses in by_mode.items()},
        "top_routes_with_zero_or_insufficient_history": {
            str(route): int(n) for route, n in by_route_insufficient.head(20).items()
        },
    }


def build_sparsity_report(operational_events: pd.DataFrame, minimum_history_days: int = MINIMUM_HISTORY_DAYS) -> dict:
    per_route = observations_per_route(operational_events)
    per_stop = observations_per_stop(operational_events)
    per_day = observations_per_day(operational_events)
    insufficient = routes_with_insufficient_history(operational_events, minimum_history_days)

    def _quantiles(s: pd.Series) -> dict:
        if s.empty:
            return {}
        return {"min": int(s.min()), "p25": float(s.quantile(0.25)), "median": float(s.median()),
                "p75": float(s.quantile(0.75)), "max": int(s.max())}

    return {
        "minimum_history_days_policy": minimum_history_days,
        "observations_per_route": {
            "n_routes": int(len(per_route)), "distribution": _quantiles(per_route["n_observations"]),
        },
        "observations_per_stop": {
            "n_stops": int(len(per_stop)), "distribution": _quantiles(per_stop["n_observations"]),
        },
        "observations_per_day": {
            "n_days": int(len(per_day)), "distribution": _quantiles(per_day["n_observations"]),
        },
        "routes_with_insufficient_history": {
            "count": len(insufficient), "route_ids": insufficient[:50],
            "note": f"Routes observed on fewer than {minimum_history_days} distinct service_dates -- "
                    f"their historical_delay_seconds/rolling_7d_delay_seconds/historical_reliability "
                    f"are NaN by construction (shift+min_periods), never fabricated. Downstream "
                    f"preprocessing must impute using TRAIN-fit statistics only, per the existing "
                    f"synthetic pipeline's established discipline.",
        },
    }

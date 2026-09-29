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

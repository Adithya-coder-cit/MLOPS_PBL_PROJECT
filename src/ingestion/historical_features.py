"""Stage 11C Part C: real-data historical features -- historical delay,
7-day rolling average delay, and historical reliability. Reuses
src/features/historical.py's exact leakage-safe method (aggregate to one
row per grouping key + service_date, then shift(1) BEFORE any
expanding/rolling window, so a given day's feature value is computed
strictly from days *before* it) rather than reinventing it.

Grouping dimension: (route_id, service_date) -- chosen to match Stage 3's
EXISTING synthetic feature contract exactly (keeps
training/prepare_inputs.py and the downstream model input schema
unchanged), and confirmed appropriate for the real data by inspection
(see src.ingestion.sparsity): real per-route daily observation counts
are high enough (verified: even the least-active routes have dozens of
scheduled stop-events per service_date) for a route-level daily
aggregate to be statistically meaningful, whereas per-STOP aggregation
would be far sparser for many of the ~7,746 real stops (most individual
stops see only a handful of events per day), and per-(route+direction)
aggregation roughly halves an already-adequate route-level sample for no
demonstrated benefit to this project's existing feature set. Documented
here rather than assumed -- see the Stage 11C report for the actual
measured counts this decision is based on.
"""
from __future__ import annotations

import pandas as pd


def compute_daily_route_stats(operational_events: pd.DataFrame) -> pd.DataFrame:
    """Only rows with a genuinely observed delay_seconds contribute --
    label_available=False rows (rail/ferry) and rows with a null
    delay_seconds (no real actual_time) are excluded from the aggregate
    itself, not silently treated as zero-delay.
    """
    usable = operational_events[
        operational_events["label_available"] & operational_events["delay_seconds"].notna()
        & operational_events.get("is_static_schedule_trip", True)
    ]
    daily = (
        usable.groupby(["route_id", "service_date"])
        .agg(mean_delay_seconds=("delay_seconds", "mean"), n_observations=("delay_seconds", "size"))
        .reset_index()
        .sort_values(["route_id", "service_date"])
    )
    return daily


def add_backward_looking_route_features(
    daily: pd.DataFrame, rolling_window_days: int = 7, min_history_days: int = 1,
) -> pd.DataFrame:
    """Identical shift(1)-before-window discipline to
    src/features/historical.py::add_backward_looking_route_features.
    `min_history_days` (Stage 11C Part D): a route's first
    `min_history_days` observed service_dates have fewer than that many
    strictly-prior days of history -- their features are left NaN here
    (via `min_periods`), never fabricated, and the caller (Stage 3-style
    preprocessing) is expected to impute using TRAIN-fit statistics only,
    exactly as the existing synthetic pipeline already does.
    """
    daily = daily.copy()
    grouped_delay = daily.groupby("route_id")["mean_delay_seconds"]

    daily["historical_delay_seconds"] = grouped_delay.transform(
        lambda s: s.shift(1).expanding(min_periods=min_history_days).mean()
    )
    daily["rolling_7d_delay_seconds"] = grouped_delay.transform(
        lambda s: s.shift(1).rolling(window=rolling_window_days, min_periods=min_history_days).mean()
    )
    # Reliability defined analogously to the synthetic feature: the
    # complement of a route's historical rate of "disrupted" days, where
    # a day counts as disrupted if its OWN mean delay (not used for this
    # day's own feature, only future days') exceeded the recommended
    # threshold. This function does not itself decide the threshold --
    # see historical_reliability_from_labels below, which takes it as an
    # explicit argument, never a hardcoded default.
    return daily[["route_id", "service_date", "historical_delay_seconds", "rolling_7d_delay_seconds",
                  "n_observations"]]


def historical_reliability_from_labels(
    operational_events: pd.DataFrame, threshold_seconds: dict[str, int] | None,
) -> pd.DataFrame:
    """Historical reliability = 1 - the expanding, strictly-prior-day
    disruption rate per route. Requires a threshold (Stage 11C Part A) --
    if none is supplied (the label policy has not been approved/activated),
    returns an all-NaN reliability column rather than guessing one, so
    callers can tell "not computed" apart from "computed as 1.0".
    """
    usable = operational_events[
        operational_events["label_available"] & operational_events["delay_seconds"].notna()
        & operational_events.get("is_static_schedule_trip", True)
    ].copy()

    if threshold_seconds is None:
        daily_dates = usable[["route_id", "service_date"]].drop_duplicates()
        daily_dates["historical_reliability"] = float("nan")
        return daily_dates

    def _is_disrupted(row) -> bool:
        t = threshold_seconds.get(row["transport_mode"])
        if t is None:
            return False
        return bool(row["delay_seconds"] >= t)

    usable["_disrupted"] = usable.apply(_is_disrupted, axis=1)
    daily = usable.groupby(["route_id", "service_date"])["_disrupted"].mean().reset_index()
    daily = daily.rename(columns={"_disrupted": "daily_disruption_rate"}).sort_values(["route_id", "service_date"])
    daily["historical_reliability"] = 1 - daily.groupby("route_id")["daily_disruption_rate"].transform(
        lambda s: s.shift(1).expanding(min_periods=1).mean()
    )
    return daily[["route_id", "service_date", "historical_reliability"]]


def join_historical_features(
    operational_events: pd.DataFrame, rolling_window_days: int = 7, min_history_days: int = 1,
    threshold_seconds: dict[str, int] | None = None,
) -> pd.DataFrame:
    daily = compute_daily_route_stats(operational_events)
    features = add_backward_looking_route_features(daily, rolling_window_days, min_history_days)
    reliability = historical_reliability_from_labels(operational_events, threshold_seconds)
    features = features.merge(reliability, on=["route_id", "service_date"], how="left")
    return operational_events.merge(features, on=["route_id", "service_date"], how="left")

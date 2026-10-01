"""Stage 11B §10/§11/§12: normalize MBTA LAMP's real per-mode schemas
into RouteWise's canonical `operational_events` contract
(src/ingestion/common/contracts.py). This is the one place `delay_seconds`
is actually derived from real scheduled/actual timestamps -- and the one
place the label-availability policy (Stage 11B §11) is enforced: never
`disruption_flag = 0` where a mode has no verified real label source.
"""
from __future__ import annotations

import hashlib
from zoneinfo import ZoneInfo

import pandas as pd

from src.utils.gtfs_time import seconds_since_midnight_to_datetime

FEED_TIMEZONE = "America/New_York"


def _record_id(trip_id: str, stop_id: str, service_date: str) -> str:
    return hashlib.sha256(f"{trip_id}|{stop_id}|{service_date}".encode()).hexdigest()[:16]


def normalize_subway_performance(
    raw: pd.DataFrame, route_to_mode: dict[str, str], label_availability: dict[str, bool],
) -> pd.DataFrame:
    """Stage 11A/11B-verified fields: scheduled_arrival_time (seconds
    since midnight, local), stop_timestamp (Unix epoch seconds, the
    observed arrival-area status-change instant) -- both confirmed <2%
    null in a real 21-day sample. `stop_timestamp` is used as
    actual_time in preference to `move_timestamp` (departure-side, a
    separate, less-complete signal) since this canonical contract models
    per-stop arrival events, matching historical_delay_minutes'
    existing route/service_date grain downstream.
    """
    df = raw.copy()
    service_dates = pd.to_datetime(df["service_date"], format="%Y%m%d").dt.date

    scheduled_time = [
        seconds_since_midnight_to_datetime(d, s, FEED_TIMEZONE)
        for d, s in zip(service_dates, df["scheduled_arrival_time"])
    ]
    actual_time = pd.to_datetime(df["stop_timestamp"], unit="s", utc=True)
    actual_time = actual_time.dt.tz_convert(ZoneInfo(FEED_TIMEZONE))
    actual_time = [t.to_pydatetime() if pd.notna(t) else None for t in actual_time]

    out = pd.DataFrame({
        "trip_id": df["trip_id"],
        "stop_id": df["stop_id"],
        "service_date": service_dates,
        "route_id": df["route_id"],
        "direction_id": df["direction_id"],
        "scheduled_time": scheduled_time,
        "actual_time": actual_time,
    })
    return _finalize_operational_events(out, route_to_mode, label_availability)


def normalize_bus_events(
    raw: pd.DataFrame, route_to_mode: dict[str, str], label_availability: dict[str, bool],
) -> pd.DataFrame:
    """Stage 11A/11B-verified fields: plan_stop_departure_dt (scheduled,
    0% null in the real sample) and stop_departure_dt (observed, ~16%
    null) -- used as actual_time in preference to tm_actual_departure_dt
    (the TransitMaster-sourced field), which was found ~80% null in the
    real 7-day sample. This is a deliberate completeness-over-provenance
    trade-off, documented here rather than silently made: tm_actual_* is
    the more authoritative source per MBTA's own Data Dictionary, but is
    too sparse in practice to be the primary actual-time signal.

    Stage 11B finding (verified by cross-checking tm_actual_departure_dt,
    which is consistently within seconds of stop_departure_dt): the two
    real timestamp columns are stored in DIFFERENT, inconsistent
    representations -- plan_stop_departure_dt is naive LOCAL time
    (America/New_York), while stop_departure_dt/tm_actual_departure_dt
    are naive UTC. Both are explicitly localized here before any delay
    is computed; treating them as directly comparable (as their raw
    dtypes -- both plain datetime64[us] with no tz -- would invite)
    silently produces a fabricated ~4-hour "delay" on every row.
    """
    df = raw.copy()
    service_dates = pd.to_datetime(df["service_date"]).dt.date

    scheduled_local = pd.to_datetime(df["plan_stop_departure_dt"]).dt.tz_localize(
        FEED_TIMEZONE, ambiguous="NaT", nonexistent="NaT")
    actual_utc = pd.to_datetime(df["stop_departure_dt"]).dt.tz_localize("UTC")

    out = pd.DataFrame({
        "trip_id": df["trip_id"],
        "stop_id": df["stop_id"],
        "service_date": service_dates,
        "route_id": df["route_id"],
        "direction_id": df["direction_id"],
        "scheduled_time": scheduled_local,
        "actual_time": actual_utc,
    })
    return _finalize_operational_events(out, route_to_mode, label_availability)


# Stage 11B finding (verified against a real 21-day subway sample):
# GTFS-RT-injected trip_ids -- prefixed "ADDED-" (a vehicle move with no
# static-schedule counterpart) or "NONREV-" (a non-revenue move) -- carry
# a "scheduled" time that is a real-time placeholder, not a genuine
# published schedule entry. 95% of |delay_seconds| > 1 hour outliers in
# the verified sample were exactly these trip_ids (84,592 of 89,151).
# Flagged here, never silently dropped -- see the Stage 11B EDA report
# for the before/after delay-distribution comparison this produces.
_NON_STATIC_TRIP_PREFIXES = ("ADDED-", "NONREV-")


def _is_static_schedule_trip(trip_id: str) -> bool:
    return not str(trip_id).startswith(_NON_STATIC_TRIP_PREFIXES)


def _finalize_operational_events(
    out: pd.DataFrame, route_to_mode: dict[str, str], label_availability: dict[str, bool],
) -> pd.DataFrame:
    out["transport_mode"] = out["route_id"].map(route_to_mode)
    out["is_static_schedule_trip"] = out["trip_id"].apply(_is_static_schedule_trip)

    scheduled = pd.to_datetime(out["scheduled_time"], utc=True, errors="coerce")
    actual = pd.to_datetime(out["actual_time"], utc=True, errors="coerce")
    delay = (actual - scheduled).dt.total_seconds()
    out["delay_seconds"] = delay

    # Stage 11B §11: label availability is a MODE-level policy decision
    # (configs/real_data.yaml label_availability), never inferred
    # row-by-row from whether this particular row happens to have data.
    out["label_available"] = out["transport_mode"].map(label_availability).fillna(False)

    # cancellation: no confirmed boolean field in either real source
    # verified in Stage 11A/11B (see the report) -- left null, never
    # invented.
    out["cancelled"] = pd.array([None] * len(out), dtype="boolean")

    # disruption_flag: null unless a caller explicitly activates the
    # (not-yet-approved) real threshold policy elsewhere -- this module
    # never computes it, per Stage 11B §12's "do not activate" instruction.
    out["disruption_flag"] = pd.array([None] * len(out), dtype="Int64")

    out["record_id"] = [
        _record_id(str(t), str(s), str(d))
        for t, s, d in zip(out["trip_id"], out["stop_id"], out["service_date"])
    ]

    return out[["record_id", "trip_id", "stop_id", "service_date", "scheduled_time", "actual_time",
                "delay_seconds", "cancelled", "transport_mode", "route_id", "direction_id",
                "label_available", "disruption_flag", "is_static_schedule_trip"]]


def deduplicate_bus_events(normalized_bus_events: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Stage 11F §7: deterministic deduplication for bus events that may
    come from two overlapping LAMP sources -- the RECENT rolling-window
    export and a windowed extract of the ALL deep-history archive.

    Deduplication key: `record_id` (sha256[:16] of trip_id|stop_id|
    service_date -- the SAME identity already used everywhere else in
    this project, see _record_id above). When both sources report the
    same (trip_id, stop_id, service_date), the ALL-archive's row is kept
    (`keep="first"` with the ALL-archive rows sorted first by the
    caller) -- LAMP's own naming implies ALL is the canonical/complete
    export and RECENT a convenience rolling snapshot of the same
    underlying system, not a separately authoritative source.

    Takes the ALREADY-NORMALIZED (canonical-contract) frame, since
    record_id only exists post-normalization; the caller is expected to
    normalize each raw source, tag its provenance order, concat, then
    call this -- never silently dedup raw frames with different schemas.
    """
    before = len(normalized_bus_events)
    overlapping_dates = None
    if "service_date" in normalized_bus_events.columns and normalized_bus_events["record_id"].duplicated().any():
        dup_mask = normalized_bus_events["record_id"].duplicated(keep=False)
        overlapping_dates = sorted(str(d) for d in normalized_bus_events.loc[dup_mask, "service_date"].unique())

    deduped = normalized_bus_events.drop_duplicates(subset="record_id", keep="first").reset_index(drop=True)
    after = len(deduped)

    summary = {
        "dedup_key": "record_id (sha256[:16] of trip_id|stop_id|service_date)",
        "records_before": before,
        "records_after": after,
        "duplicates_removed": before - after,
        "overlapping_service_dates": overlapping_dates or [],
    }
    return deduped, summary


def apply_real_disruption_label_policy(
    operational_events: pd.DataFrame, policy_cfg: dict,
) -> pd.DataFrame:
    """Stage 11B §12: ONLY called if `real_disruption_label_policy.active`
    is explicitly true in configs/real_data.yaml -- computes
    disruption_flag from delay_seconds (+ cancellation) for
    label_available rows, leaving label_available=False rows null.
    Never invoked by the normalize functions above automatically.
    """
    if not policy_cfg.get("active", False):
        return operational_events

    thresholds = policy_cfg["placeholder_thresholds_seconds"]
    out = operational_events.copy()

    # Vectorized equivalent of the original per-row loop -- `.iterrows()`
    # over a real multi-million-row operational_events table (subway +
    # bus combined) took tens of minutes; this is the identical policy
    # (same thresholds dict, same cancellation rule, same NA handling),
    # just computed with pandas ops instead of a Python-level row loop.
    threshold_per_row = out["transport_mode"].map(thresholds)
    valid_mask = (
        out["label_available"].astype(bool)
        & threshold_per_row.notna()
        & out["delay_seconds"].notna()
    )
    is_disruption = out["delay_seconds"] >= threshold_per_row
    if policy_cfg.get("cancellation_counts_as_disruption", True):
        is_disruption = is_disruption | out["cancelled"].astype("boolean").fillna(False)

    flags = pd.Series(pd.NA, index=out.index, dtype="Int64")
    flags.loc[valid_mask] = is_disruption.loc[valid_mask].astype(int)
    out["disruption_flag"] = flags
    return out

"""Stage 11C Part A/B: real-world disruption-label analysis.

This module NEVER activates a threshold -- it only measures candidate
thresholds against the real delay distribution and returns a documented
recommendation for human approval. Activation remains a separate,
explicit step (configs/real_data.yaml real_disruption_label_policy.active),
unchanged from Stage 11B's design.

Label horizon (Stage 11C Part B): RouteWise predicts disruption risk for
a SINGLE scheduled stop-event -- "will this scheduled arrival/departure
at stop S on trip T be disrupted (delayed past threshold, or cancelled)
relative to its own scheduled time?" This is the same per-stop-event
granularity the synthetic generator and Stage 3's feature pipeline
already use (one row = one scheduled stop-event), not a rolling future
window. The label is computed from that SAME event's own realized
outcome (delay_seconds, cancelled) -- never from a later or different
event -- so by construction the label's time reference IS the prediction
timestamp; there is no separate "horizon" to define beyond "this event."
Features, by contrast, must be strictly PRE-T: scheduled_time, weather
asof-joined backward from scheduled_time, and historical aggregates
computed from strictly prior days (src/ingestion/historical_features.py).
"""
from __future__ import annotations

import pandas as pd

# Candidate thresholds span a operationally meaningful range: a rider
# would plausibly start calling a bus/train "late" somewhere between 3
# and 15 minutes past schedule, depending on mode expectations -- these
# are round, interpretable numbers, not fit to any particular class
# balance.
CANDIDATE_THRESHOLDS_SECONDS = [180, 300, 420, 600, 900]  # 3, 5, 7, 10, 15 minutes
PERCENTILES = [0.50, 0.75, 0.90, 0.95, 0.99]


def delay_distribution_summary(delay_seconds: pd.Series) -> dict:
    s = delay_seconds.dropna()
    if s.empty:
        return {"record_count": 0}
    return {
        "record_count": int(len(s)),
        "median_delay_seconds": float(s.median()),
        "mean_delay_seconds": float(s.mean()),
        "std_delay_seconds": float(s.std()),
        "percentiles_seconds": {f"P{int(p * 100)}": float(s.quantile(p)) for p in PERCENTILES},
    }


def threshold_candidates(delay_seconds: pd.Series, mode: str, thresholds: list[int] | None = None) -> list[dict]:
    thresholds = thresholds or CANDIDATE_THRESHOLDS_SECONDS
    s = delay_seconds.dropna()
    n = len(s)
    rows = []
    for t in thresholds:
        positive = int((s >= t).sum())
        rows.append({
            "threshold_seconds": t, "threshold_minutes": round(t / 60, 1), "mode": mode,
            "positive_rate": float(positive / n) if n else None,
            "negative_rate": float((n - positive) / n) if n else None,
            "sample_count": n,
            "pros": _pros_for_threshold(t),
            "limitations": _limitations_for_threshold(t, positive, n),
        })
    return rows


def _pros_for_threshold(t: int) -> str:
    minutes = t / 60
    if minutes <= 3:
        return ("Sensitive -- catches most real schedule deviations riders would notice; useful if "
                "false negatives (missed real disruptions) are the costlier error.")
    if minutes <= 5:
        return ("A common, easily-explained operational definition ('5 minutes late') -- "
                "interpretable to a non-technical stakeholder.")
    if minutes <= 7:
        return "Balances sensitivity against false-alarm rate; still short enough to matter to a rider's actual trip."
    if minutes <= 10:
        return "Conservative -- flags only more consequential delays, reducing false-alarm/rerouting cost."
    return "Very conservative -- reserved for delays a rider would very likely reroute around; lowest false-alarm rate."


def _limitations_for_threshold(t: int, positive: int, n: int) -> str:
    rate = positive / n if n else 0.0
    if rate > 0.5:
        return (f"Majority-positive class ({rate:.1%}) -- may not discriminate 'disrupted' from "
                f"'normal variation' meaningfully at this mode's typical delay level.")
    if rate < 0.02:
        return (f"Very low positive rate ({rate:.1%}) -- severe class imbalance, may need class "
                f"weighting/resampling policy review before training.")
    return f"Positive rate {rate:.1%} -- review against the mode's own operational tolerance before adopting."


def build_label_candidate_report(operational_events: pd.DataFrame, label_availability: dict[str, bool]) -> dict:
    """Stage 11C Part A: the full candidate report, restricted to
    STATIC-SCHEDULE trips only (Stage 11B finding: GTFS-RT-injected
    ADDED-/NONREV- trip_ids have placeholder scheduled times that would
    corrupt this analysis) and to modes with a verified real label
    source (Stage 11A/11B: bus, metro, tram)."""
    modes_with_labels = sorted([m for m, v in label_availability.items() if v])
    static = operational_events[operational_events["is_static_schedule_trip"]] if \
        "is_static_schedule_trip" in operational_events.columns else operational_events

    per_mode = {}
    for mode in modes_with_labels:
        mode_events = static[static["transport_mode"] == mode]
        summary = delay_distribution_summary(mode_events["delay_seconds"])
        candidates = threshold_candidates(mode_events["delay_seconds"], mode)
        per_mode[mode] = {"distribution": summary, "candidate_thresholds": candidates}

    return {
        "scope_note": "Restricted to is_static_schedule_trip=True rows and modes with a verified "
                       "real label source (Stage 11A/11B). Cancellation/service-alert-based signals "
                       "were investigated (Stage 11B) but no confirmed clean boolean cancellation "
                       "field was found in either real source at the field-name level -- delay-based "
                       "thresholds are therefore the only candidate basis actually usable from "
                       "verified fields; this is stated explicitly rather than assumed solvable.",
        "modes_analyzed": modes_with_labels,
        "modes_excluded_no_label_source": sorted([m for m, v in label_availability.items() if not v]),
        "per_mode": per_mode,
    }


def recommend_label_policy(candidate_report: dict) -> dict:
    """A documented, human-reviewable RECOMMENDATION -- never activated
    automatically. Chooses the threshold per mode whose positive rate
    falls in an operationally reasonable band (2%-40%), preferring the
    smallest (most sensitive) threshold in that band per mode, rather
    than picking whatever threshold happens to produce the "nicest"
    balance for its own sake.
    """
    recommendations = {}
    reasoning = []
    for mode, data in candidate_report["per_mode"].items():
        in_band = [c for c in data["candidate_thresholds"] if c["positive_rate"] is not None
                   and 0.02 <= c["positive_rate"] <= 0.40]
        if in_band:
            chosen = min(in_band, key=lambda c: c["threshold_seconds"])
            reasoning.append(f"{mode}: {chosen['threshold_seconds']}s ({chosen['positive_rate']:.1%} positive) "
                              f"-- smallest candidate threshold with an operationally reasonable class balance.")
        else:
            # Fall back to the median candidate threshold and say so plainly.
            chosen = data["candidate_thresholds"][len(data["candidate_thresholds"]) // 2]
            reasoning.append(f"{mode}: no candidate threshold fell in the 2%-40% positive-rate band -- "
                              f"defaulting to the middle candidate ({chosen['threshold_seconds']}s, "
                              f"{chosen['positive_rate']:.1%} positive); this mode's threshold needs "
                              f"dedicated human review, not just this heuristic.")
        recommendations[mode] = chosen["threshold_seconds"]

    return {
        "recommended_thresholds_seconds": recommendations,
        "reasoning": reasoning,
        "cancellation_counts_as_disruption": True,
        "status": "RECOMMENDATION ONLY -- NOT ACTIVATED. A human must set "
                  "configs/real_data.yaml real_disruption_label_policy.active=true and copy these "
                  "(or their own reviewed) values into placeholder_thresholds_seconds before any "
                  "real disruption_flag is computed.",
    }


def verify_frozen_label_policy(training_table: pd.DataFrame, frozen_thresholds: dict[str, int]) -> dict:
    """Stage 11E Part 6: re-verifies the FROZEN (already-activated) label
    policy against the real ingested/joined training table -- positive/
    negative rate, missing labels, distribution by mode, and a
    consistency check that recomputes disruption_flag from delay_seconds
    + the frozen threshold and confirms it matches the column the
    pipeline actually produced (catches config/activation drift; never
    assumes activation worked correctly). Does not change any threshold
    -- this function only measures.
    """
    # Memory: only these columns are read below -- filtering the full
    # 25-column, 20M+-row training table per mode would copy every
    # column along with it for no reason.
    slim = training_table[["transport_mode", "label_available", "disruption_flag", "delay_seconds"]]

    per_mode = {}
    for mode in sorted(frozen_thresholds):
        group = slim[slim["transport_mode"] == mode]
        if group.empty:
            per_mode[mode] = {"note": "no rows for this mode in the training table"}
            continue

        label_available = bool(group["label_available"].iloc[0]) if len(group) else None
        flag = group["disruption_flag"]
        n = len(group)
        n_missing = int(flag.isna().sum())
        n_labeled = n - n_missing
        positive = int((flag == 1).sum())
        negative = int((flag == 0).sum())

        threshold = frozen_thresholds[mode]
        recomputed = (group["delay_seconds"] >= threshold).astype("Int64")
        recomputed = recomputed.where(group["delay_seconds"].notna())
        comparable = flag.notna() & recomputed.notna()
        mismatches = int((flag[comparable] != recomputed[comparable]).sum())

        per_mode[mode] = {
            "label_available": label_available,
            "frozen_threshold_seconds": threshold,
            "total_rows": n,
            "labeled_rows": n_labeled,
            "missing_label_rows": n_missing,
            "positive_rate": float(positive / n_labeled) if n_labeled else None,
            "negative_rate": float(negative / n_labeled) if n_labeled else None,
            "consistency_check_mismatches": mismatches,
            "consistency_check_passed": mismatches == 0,
        }

    modes_without_labels = sorted(set(slim["transport_mode"].unique()) - set(frozen_thresholds))
    for mode in modes_without_labels:
        group = slim[slim["transport_mode"] == mode]
        per_mode[mode] = {
            "label_available": bool(group["label_available"].iloc[0]) if len(group) else False,
            "note": "no frozen threshold for this mode -- disruption_flag must be entirely null",
            "disruption_flag_all_null": bool(group["disruption_flag"].isna().all()) if len(group) else None,
        }

    return {
        "frozen_thresholds_seconds": frozen_thresholds,
        "per_mode": per_mode,
        "all_consistency_checks_passed": all(
            v.get("consistency_check_passed", True) for v in per_mode.values()
        ),
    }

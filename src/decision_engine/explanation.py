"""Generates a factual, template-based explanation string from a selected
route's ACTUAL computed values, optionally compared against the
next-best alternative. Never a hardcoded/canned sentence — every number
quoted comes from the aggregated path or the comparison.
"""
from __future__ import annotations


def _fmt_minutes(m: float) -> str:
    return f"{m:.1f} min"


def _fmt_pct(p: float) -> str:
    return f"{p * 100:.1f}%"


def generate_explanation(selected: dict, alternatives: list[dict], policy_label: str) -> str:
    """`selected` and each item in `alternatives` are aggregated-path
    dicts with at least: total_time, total_cost, reliability,
    disruption_risk, transfer_count, transport_modes, score.
    """
    parts = [
        f"Selected under the '{policy_label}' decision policy: "
        f"{_fmt_minutes(selected['total_time'])} total travel time, "
        f"cost {selected['total_cost']:.2f} units, "
        f"reliability {_fmt_pct(selected['reliability'])}, "
        f"disruption risk {_fmt_pct(selected['disruption_risk'])}, "
        f"{selected['transfer_count']} transfer(s) via "
        f"{'/'.join(selected['transport_modes'])}."
    ]

    others = [a for a in alternatives if a is not selected]
    if others:
        best_time_alt = min(others, key=lambda a: a["total_time"])
        best_cost_alt = min(others, key=lambda a: a["total_cost"])
        best_reliability_alt = max(others, key=lambda a: a["reliability"])

        if best_time_alt["total_time"] < selected["total_time"]:
            time_diff = selected["total_time"] - best_time_alt["total_time"]
            reliability_diff = selected["reliability"] - best_time_alt["reliability"]
            if reliability_diff > 0:
                parts.append(
                    f"A {_fmt_minutes(time_diff)} faster alternative exists but was not chosen because "
                    f"it has {_fmt_pct(reliability_diff)} lower reliability."
                )
        if best_cost_alt["total_cost"] < selected["total_cost"]:
            cost_diff = selected["total_cost"] - best_cost_alt["total_cost"]
            reliability_diff = selected["reliability"] - best_cost_alt["reliability"]
            if reliability_diff > 0:
                parts.append(
                    f"A {cost_diff:.2f}-unit cheaper alternative exists but was not chosen because "
                    f"it has {_fmt_pct(reliability_diff)} lower reliability."
                )
        if best_reliability_alt["reliability"] > selected["reliability"]:
            reliability_diff = best_reliability_alt["reliability"] - selected["reliability"]
            time_diff = best_reliability_alt["total_time"] - selected["total_time"]
            if time_diff > 0:
                parts.append(
                    f"A more reliable alternative exists ({_fmt_pct(reliability_diff)} higher) but was not "
                    f"chosen because it takes {_fmt_minutes(time_diff)} longer."
                )

    return " ".join(parts)

"""Configurable normalization for cost/time/reliability before they're
combined in Score = αC + βT − γR (mixing raw units directly — SYNTHETIC_UNITS
of cost, minutes of time, a [0,1] reliability ratio — would make α/β/γ
meaningless, since a 1-unit change in cost and a 1-unit change in minutes
are not comparable).

Two methods, chosen via params.yaml routing.normalization.method:

- "minmax_candidates": normalize each candidate against the min/max
  observed across the candidate SET being compared in this query. No
  hardcoded scale, adapts per query. Requires >=2 distinct-valued
  candidates; degenerates to 0.5 for every candidate when they're all
  equal (avoids an arbitrary winner from divide-by-zero).
- "fixed_bounds": normalize against configured fixed bounds — used
  automatically as a fallback when there's only one candidate (min-max
  over a single point is undefined) or when explicitly configured.
"""
from __future__ import annotations

import numpy as np


def minmax_normalize(values: list[float]) -> list[float]:
    arr = np.asarray(values, dtype=float)
    lo, hi = arr.min(), arr.max()
    if hi - lo < 1e-12:
        return [0.5] * len(values)
    return list((arr - lo) / (hi - lo))


def fixed_bounds_normalize(values: list[float], bounds: dict) -> list[float]:
    lo, hi = float(bounds["min"]), float(bounds["max"])
    if hi - lo < 1e-12:
        raise ValueError(f"Invalid fixed bounds (max <= min): {bounds}")
    arr = np.asarray(values, dtype=float)
    clipped = np.clip(arr, lo, hi)
    return list((clipped - lo) / (hi - lo))


def normalize_candidates(costs: list[float], times: list[float], reliabilities: list[float],
                          config: dict) -> tuple[list[float], list[float], list[float]]:
    """Returns (normalized_costs, normalized_times, normalized_reliabilities)
    — each in [0,1], higher-is-better preserved for reliability (NOT
    inverted here; the scoring formula itself subtracts it).
    """
    method = config["method"]
    n = len(costs)
    if method == "minmax_candidates" and n >= 2:
        return minmax_normalize(costs), minmax_normalize(times), minmax_normalize(reliabilities)

    bounds = config["fixed_bounds"]
    return (
        fixed_bounds_normalize(costs, bounds["cost"]),
        fixed_bounds_normalize(times, bounds["time_minutes"]),
        fixed_bounds_normalize(reliabilities, bounds["reliability"]),
    )

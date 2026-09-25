"""Deterministic controlled monitoring scenarios (Stage 9 §14). Every
scenario operates on IN-MEMORY copies only — nothing here ever writes to
data/processed, refits a preprocessor, retrains a model, or touches a
DVC artifact (Stage 9 §15). Where randomness is used it is seeded
(matching this project's existing convention of fixed seeds — see
params.yaml data.random_seed / training.seed), so results are
reproducible run to run.

These are CONTROLLED DEVELOPMENT EXPERIMENTS, not observations of real
drift — callers must label results accordingly (see Stage 9 §20).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SCENARIO_SEED = 42


def scenario_a_identical(reference: pd.DataFrame) -> pd.DataFrame:
    """Current == reference (a deep copy) — the deterministic zero-drift
    baseline case: no meaningful drift is expected."""
    return reference.copy(deep=True)


def scenario_b_feature_shift(
    current: pd.DataFrame, numeric_feature: str, shift_std_multiples: float = 4.0
) -> pd.DataFrame:
    """Shift one numeric feature by a fixed multiple of its own reference
    standard deviation — large and deterministic (no randomness), so
    feature drift detection is expected."""
    shifted = current.copy(deep=True)
    std = shifted[numeric_feature].std()
    shifted[numeric_feature] = shifted[numeric_feature] + shift_std_multiples * std
    return shifted


def scenario_c_prediction_shift(current_prob: np.ndarray, shift: float = 0.4) -> np.ndarray:
    """Push predicted probabilities toward 1.0 by a fixed amount (clipped
    to [0, 1]) — simulates the model's OUTPUT distribution changing
    without touching any input feature, so prediction drift detection is
    expected."""
    return np.clip(current_prob + shift, 0.0, 1.0)


def scenario_d_performance_degradation(y_prob: np.ndarray, degrade_fraction: float = 0.5) -> np.ndarray:
    """Deterministically (seeded) invert a fixed fraction of predicted
    probabilities (p -> 1-p) — simulates a model that has stopped
    discriminating well, without touching true labels or retraining
    anything, so performance degradation is expected."""
    rng = np.random.default_rng(SCENARIO_SEED)
    corrupted = y_prob.copy()
    n = len(corrupted)
    idx = rng.choice(n, size=int(n * degrade_fraction), replace=False)
    corrupted[idx] = 1.0 - corrupted[idx]
    return corrupted

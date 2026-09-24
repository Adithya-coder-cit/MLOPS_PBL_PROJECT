"""Class-distribution reporting and imbalance-strategy decision. The
strategy is computed from the TRAIN split only — validation/test class
balance is observed and reported but never used to decide the strategy.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class ClassDistribution:
    n_total: int
    n_positive: int
    n_negative: int
    positive_rate: float
    negative_to_positive_ratio: float

    def to_dict(self) -> dict:
        return {
            "n_total": self.n_total, "n_positive": self.n_positive, "n_negative": self.n_negative,
            "positive_rate": round(self.positive_rate, 4),
            "negative_to_positive_ratio": round(self.negative_to_positive_ratio, 4),
        }


def compute_class_distribution(y: pd.Series) -> ClassDistribution:
    n_total = len(y)
    n_positive = int((y == 1).sum())
    n_negative = int((y == 0).sum())
    return ClassDistribution(
        n_total=n_total, n_positive=n_positive, n_negative=n_negative,
        positive_rate=n_positive / n_total if n_total else 0.0,
        negative_to_positive_ratio=n_negative / n_positive if n_positive else float("inf"),
    )


def decide_imbalance_strategy(train_distribution: ClassDistribution, ratio_threshold: float) -> dict:
    """Decision is based purely on the TRAIN distribution."""
    apply_weighting = train_distribution.negative_to_positive_ratio > ratio_threshold
    return {
        "strategy": "class_weighting" if apply_weighting else "none",
        "reason": (
            f"train negative:positive ratio = {train_distribution.negative_to_positive_ratio:.2f}, "
            f"{'exceeds' if apply_weighting else 'does not exceed'} threshold {ratio_threshold} "
            f"-> {'applying' if apply_weighting else 'not applying'} class weighting "
            "(no oversampling used, per Stage 4 policy)."
        ),
        "scale_pos_weight": train_distribution.negative_to_positive_ratio if apply_weighting else 1.0,
        "sklearn_class_weight": "balanced" if apply_weighting else None,
    }

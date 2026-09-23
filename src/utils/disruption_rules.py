"""Shared disruption-labeling rule.

Used both by the synthetic demo generator (to bake in ground-truth labels)
and, later, by the real-data ingestion path (to derive labels from actual
vs. scheduled times the same way) — so the label definition never diverges
between development and production data.
"""
from __future__ import annotations

import yaml


def load_mode_thresholds(synthetic_config_path: str = "configs/synthetic_data.yaml") -> dict[str, float]:
    with open(synthetic_config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return {
        mode: params["disruption_threshold_minutes"]
        for mode, params in cfg["mode_params"].items()
    }


def is_disruption(delay_minutes: float, cancelled: bool, transport_mode: str, thresholds: dict[str, float]) -> bool:
    """Mode-specific disruption rule: cancelled, or delay past this mode's tolerance."""
    if cancelled:
        return True
    threshold = thresholds[transport_mode]
    return delay_minutes > threshold

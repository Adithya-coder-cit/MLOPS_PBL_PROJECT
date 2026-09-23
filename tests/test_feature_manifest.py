"""Tests that the feature manifest covers exactly the processed dataset's
columns and every entry has the required documentation fields."""
from pathlib import Path

import pandas as pd
import pytest

from src.features.manifest import FEATURE_MANIFEST, manifest_columns

REQUIRED_FIELDS = {"name", "dtype", "source", "description", "unit", "transformation",
                    "availability_time", "leakage_risk", "model_usage"}


def test_every_manifest_entry_has_required_fields():
    for entry in FEATURE_MANIFEST:
        assert REQUIRED_FIELDS <= set(entry.keys()), f"{entry.get('name')} missing fields"


def test_manifest_names_are_unique():
    names = [e["name"] for e in FEATURE_MANIFEST]
    assert len(names) == len(set(names))


def test_label_and_diagnostics_are_flagged_not_as_plain_feature():
    by_name = {e["name"]: e for e in FEATURE_MANIFEST}
    assert by_name["disruption_flag"]["model_usage"] == "label"
    for outcome_col in ["delay_minutes", "cancelled", "actual_time"]:
        assert "excluded" in by_name[outcome_col]["model_usage"]


PROCESSED_EXISTS = Path("data/processed/train.parquet").exists()


@pytest.mark.skipif(not PROCESSED_EXISTS, reason="processed dataset not generated yet")
def test_manifest_matches_real_processed_columns():
    train = pd.read_parquet("data/processed/train.parquet")
    assert set(train.columns) == manifest_columns()

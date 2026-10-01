"""Stage 11F tests: expanding real historical bus coverage so bus has
genuine train/validation/test records (not just test), while metro/tram
continue to, the frozen label policy stays unchanged, deduplication
between the two real bus sources (RECENT rolling window + a windowed
extract of the ALL deep-history archive) is deterministic and
documented, and historical-feature leakage discipline still holds.

Two kinds of tests here:
- Pure unit tests (synthetic small frames) for the dedup/readiness LOGIC
  -- always run, no dependency on any downloaded data.
- Real-artifact tests (skipped if the Stage 11F artifacts don't exist on
  disk yet) that check the ACTUAL regenerated real dataset -- mirrors
  the existing Stage 11C/D/E test pattern of asserting against real
  generated reports, never fabricated fixtures.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.ingestion.historical.normalize import _record_id, deduplicate_bus_events
from src.ingestion.supervised_split_readiness import (
    REQUIRED_SPLITS,
    SUPERVISED_MODES,
    build_real_supervised_split_readiness_decision,
)

OUT_DIR = Path("data/interim/real")


def _bus_event_row(**overrides) -> dict:
    base = {
        "record_id": None, "trip_id": "T1", "stop_id": "S1", "service_date": pd.Timestamp("2026-08-05").date(),
        "route_id": "R1", "direction_id": 0,
        "scheduled_time": pd.Timestamp("2026-08-05T08:00:00", tz="America/New_York"),
        "actual_time": pd.Timestamp("2026-08-05T13:05:00", tz="UTC"),
        "delay_seconds": 300.0, "cancelled": pd.NA, "transport_mode": "bus",
        "label_available": True, "disruption_flag": pd.NA, "is_static_schedule_trip": True,
    }
    base.update(overrides)
    if base["record_id"] is None:
        base["record_id"] = _record_id(str(base["trip_id"]), str(base["stop_id"]), str(base["service_date"]))
    return base


# --- 1/2: source ingestion + provenance (structural checks on the real code) ---

def test_download_bus_archive_window_is_a_real_function_with_expected_signature():
    import inspect

    from src.ingestion.historical.mbta_lamp import download_bus_archive_window

    params = list(inspect.signature(download_bus_archive_window).parameters)
    assert params == ["url", "dest_path", "min_service_date", "max_service_date", "timeout"]


def test_bus_archive_config_documents_a_real_url_and_window():
    import yaml

    cfg = yaml.safe_load(Path("configs/real_data.yaml").read_text(encoding="utf-8"))
    archive_cfg = cfg["sources"]["historical_bus_archive"]
    assert archive_cfg["url"] == "https://performancedata.mbta.com/lamp/tableau/bus/LAMP_ALL_Bus_Events.parquet"
    assert archive_cfg["window_start"] == "2026-08-01"
    assert archive_cfg["window_end"] == "2026-09-29"


# --- 4/5: overlap detection + deterministic deduplication ---

def test_dedup_removes_exact_overlap_between_the_two_real_bus_sources():
    archive_row = _bus_event_row(trip_id="T1", stop_id="S1", service_date=pd.Timestamp("2026-09-25").date())
    recent_row = _bus_event_row(trip_id="T1", stop_id="S1", service_date=pd.Timestamp("2026-09-25").date())
    unique_row = _bus_event_row(trip_id="T2", stop_id="S1", service_date=pd.Timestamp("2026-08-05").date())
    combined = pd.DataFrame([archive_row, recent_row, unique_row])

    deduped, summary = deduplicate_bus_events(combined)

    assert summary["records_before"] == 3
    assert summary["records_after"] == 2
    assert summary["duplicates_removed"] == 1
    assert summary["dedup_key"].startswith("record_id")
    assert "2026-09-25" in summary["overlapping_service_dates"]
    assert len(deduped) == 2


def test_dedup_keeps_the_first_row_for_a_duplicate_key_deterministically():
    # The caller concatenates [archive, recent] in that order so the
    # archive row wins ties -- verify keep="first" actually does that.
    archive_row = _bus_event_row(trip_id="T1", stop_id="S1", delay_seconds=111.0)
    recent_row = _bus_event_row(trip_id="T1", stop_id="S1", delay_seconds=999.0)
    combined = pd.DataFrame([archive_row, recent_row])

    deduped, _ = deduplicate_bus_events(combined)

    assert len(deduped) == 1
    assert deduped.iloc[0]["delay_seconds"] == 111.0


def test_dedup_is_idempotent_and_deterministic_across_reruns():
    rows = [_bus_event_row(trip_id=f"T{i}", stop_id="S1", service_date=pd.Timestamp("2026-08-10").date())
            for i in range(5)]
    combined = pd.DataFrame(rows)

    deduped1, summary1 = deduplicate_bus_events(combined)
    deduped2, summary2 = deduplicate_bus_events(combined)

    assert summary1 == summary2
    pd.testing.assert_frame_equal(deduped1.reset_index(drop=True), deduped2.reset_index(drop=True))


def test_dedup_no_duplicates_reports_zero_removed_and_empty_overlap():
    rows = [_bus_event_row(trip_id=f"T{i}", stop_id="S1") for i in range(3)]
    combined = pd.DataFrame(rows)

    deduped, summary = deduplicate_bus_events(combined)

    assert summary["duplicates_removed"] == 0
    assert summary["overlapping_service_dates"] == []
    assert len(deduped) == 3


# --- 6: bus labels (frozen threshold, unchanged) ---

def test_frozen_bus_threshold_is_unchanged_at_300_seconds():
    import yaml

    cfg = yaml.safe_load(Path("configs/real_data.yaml").read_text(encoding="utf-8"))
    thresholds = cfg["real_disruption_label_policy"]["placeholder_thresholds_seconds"]
    assert thresholds == {"bus": 300, "metro": 180, "tram": 180}


# --- REAL_SUPERVISED_SPLIT_READY unit tests (synthetic, always run) ---

def _fake_eligible_split_summary(bus_counts, metro_counts, tram_counts) -> dict:
    summary = {}
    for i, split in enumerate(REQUIRED_SPLITS):
        summary[split] = {
            "row_count": bus_counts[i] + metro_counts[i] + tram_counts[i],
            "mode_distribution": {"bus": bus_counts[i], "metro": metro_counts[i], "tram": tram_counts[i]},
        }
    return summary


def _fake_eligible_df(n=10) -> pd.DataFrame:
    return pd.DataFrame({
        "source_provider": ["MBTA LAMP"] * n, "source_dataset_type": ["REAL"] * n,
        "transport_mode": (["bus", "metro", "tram"] * n)[:n],
    })


def _fake_training_table(n=10) -> pd.DataFrame:
    return pd.DataFrame({
        "route_id": ["R1"] * n, "service_date": pd.date_range("2026-08-01", periods=n).date,
        "historical_delay_seconds": [None] * n, "delay_seconds": [100.0] * n,
    })


def test_supervised_split_readiness_true_when_all_modes_present_in_all_splits():
    # Fixture deliberately does NOT satisfy the unrelated schema/leakage
    # checks (that's covered by the real-artifact tests below) -- this
    # test isolates JUST the "does every mode appear in every split"
    # criterion this stage exists to fix.
    summary = _fake_eligible_split_summary(bus_counts=[10, 5, 8], metro_counts=[20, 10, 15], tram_counts=[15, 7, 9])
    decision = build_real_supervised_split_readiness_decision(
        training_table=_fake_training_table(), eligible=_fake_eligible_df(), eligible_split_summary=summary,
        eligible_split_error=None, label_verification={"all_consistency_checks_passed": True},
        bus_dedup_summary={"records_before": 100, "records_after": 90, "duplicates_removed": 10},
    )
    assert decision["criteria_checked"]["all_modes_all_splits_present"] is True
    assert not any(mode in r for r in decision["blocking_reasons"] for mode in SUPERVISED_MODES)
    for mode in SUPERVISED_MODES:
        for split in REQUIRED_SPLITS:
            assert decision["per_mode_split_record_counts"][mode][split] > 0


def test_supervised_split_readiness_false_when_bus_missing_from_train():
    # Exactly the original Stage 11E bug this stage fixes: bus=0 in train/val.
    summary = _fake_eligible_split_summary(bus_counts=[0, 0, 500], metro_counts=[20, 10, 15], tram_counts=[15, 7, 9])
    decision = build_real_supervised_split_readiness_decision(
        training_table=_fake_training_table(), eligible=_fake_eligible_df(), eligible_split_summary=summary,
        eligible_split_error=None, label_verification={"all_consistency_checks_passed": True},
        bus_dedup_summary={"records_before": 100, "records_after": 90, "duplicates_removed": 10},
    )
    assert decision["REAL_SUPERVISED_SPLIT_READY"] is False
    assert any("bus" in r and "train" in r for r in decision["blocking_reasons"])
    assert any("bus" in r and "val" in r for r in decision["blocking_reasons"])


def test_supervised_split_readiness_false_when_no_genuine_bus_history():
    summary = _fake_eligible_split_summary(bus_counts=[10, 5, 8], metro_counts=[20, 10, 15], tram_counts=[15, 7, 9])
    decision = build_real_supervised_split_readiness_decision(
        training_table=_fake_training_table(), eligible=_fake_eligible_df(), eligible_split_summary=summary,
        eligible_split_error=None, label_verification={"all_consistency_checks_passed": True},
        bus_dedup_summary={"records_before": 0, "records_after": 0, "duplicates_removed": 0},
    )
    assert decision["REAL_SUPERVISED_SPLIT_READY"] is False
    assert decision["criteria_checked"]["genuine_historical_bus_data_exists"] is False


def test_supervised_split_readiness_false_when_split_error_present():
    decision = build_real_supervised_split_readiness_decision(
        training_table=_fake_training_table(), eligible=_fake_eligible_df(), eligible_split_summary={},
        eligible_split_error="Only 2 distinct day(s) of real coverage",
        label_verification={"all_consistency_checks_passed": True},
        bus_dedup_summary={"records_before": 100, "records_after": 90, "duplicates_removed": 10},
    )
    assert decision["REAL_SUPERVISED_SPLIT_READY"] is False
    assert decision["criteria_checked"]["chronological_split_valid"] is False


def test_supervised_split_readiness_false_when_labels_not_genuine():
    summary = _fake_eligible_split_summary(bus_counts=[10, 5, 8], metro_counts=[20, 10, 15], tram_counts=[15, 7, 9])
    decision = build_real_supervised_split_readiness_decision(
        training_table=_fake_training_table(), eligible=_fake_eligible_df(), eligible_split_summary=summary,
        eligible_split_error=None, label_verification={"all_consistency_checks_passed": False},
        bus_dedup_summary={"records_before": 100, "records_after": 90, "duplicates_removed": 10},
    )
    assert decision["REAL_SUPERVISED_SPLIT_READY"] is False
    assert decision["criteria_checked"]["labels_genuine"] is False


# ============================================================
# Real-artifact tests -- only run once Stage 11F has actually
# regenerated data/interim/real/. Skipped (not failed) otherwise, same
# convention as tests/test_stage11c.py etc.
# ============================================================

_dedup_report_path = OUT_DIR / "bus_deduplication_report.json"
_split_readiness_path = OUT_DIR / "real_supervised_split_readiness.json"
_eligible_split_path = OUT_DIR / "eligible_temporal_split.json"

requires_stage11f_artifacts = pytest.mark.skipif(
    not _split_readiness_path.exists(), reason="Stage 11F has not regenerated data/interim/real/ artifacts yet"
)


@requires_stage11f_artifacts
def test_real_bus_deduplication_report_is_honest_and_well_formed():
    report = json.loads(_dedup_report_path.read_text(encoding="utf-8"))
    assert report["records_before"] >= report["records_after"] >= 0
    assert report["duplicates_removed"] == report["records_before"] - report["records_after"]
    assert report["dedup_key"].startswith("record_id")


@requires_stage11f_artifacts
def test_real_eligible_split_gives_bus_genuine_train_validation_test_presence():
    split = json.loads(_eligible_split_path.read_text(encoding="utf-8"))
    assert split["error"] is None, f"Split could not be constructed: {split['error']}"
    for split_name in REQUIRED_SPLITS:
        mode_dist = split["splits"][split_name]["mode_distribution"]
        assert mode_dist.get("bus", 0) > 0, f"bus has zero eligible records in '{split_name}' -- Stage 11F unresolved"


@requires_stage11f_artifacts
def test_real_eligible_split_gives_metro_and_tram_genuine_presence_too():
    split = json.loads(_eligible_split_path.read_text(encoding="utf-8"))
    for split_name in REQUIRED_SPLITS:
        mode_dist = split["splits"][split_name]["mode_distribution"]
        for mode in ("metro", "tram"):
            assert mode_dist.get(mode, 0) > 0, f"{mode} has zero eligible records in '{split_name}'"


@requires_stage11f_artifacts
def test_real_supervised_split_readiness_report_is_true():
    decision = json.loads(_split_readiness_path.read_text(encoding="utf-8"))
    assert decision["REAL_SUPERVISED_SPLIT_READY"] is True, decision["primary_reason"]
    assert decision["blocking_reasons"] == []


@requires_stage11f_artifacts
def test_real_model_readiness_unchanged_still_requires_80_percent_weather():
    model_readiness = json.loads((OUT_DIR / "model_readiness.json").read_text(encoding="utf-8"))
    # MODEL_READY must remain the stricter, separately-gated decision --
    # Stage 11F must not have relaxed the weather bar to make anything pass.
    assert model_readiness["criteria_checked"]["weather_coverage_adequate"] is (
        json.loads((OUT_DIR / "weather_coverage_report.json").read_text(encoding="utf-8"))["overall_coverage"] >= 0.80
    )


@requires_stage11f_artifacts
def test_real_historical_features_still_pass_leakage_smoke_check():
    from src.ingestion.model_readiness import _leakage_smoke_check

    training_table = pd.read_parquet(OUT_DIR / "training_table.parquet")
    ok, msg = _leakage_smoke_check(training_table)
    assert ok, msg

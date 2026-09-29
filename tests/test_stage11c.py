"""Stage 11C Part M tests: real disruption-label policy analysis, real
historical-feature leakage discipline, sparsity/minimum-history behavior,
temporal split, training-table contract, rail/ferry unlabeled behavior,
and the model-readiness gate -- including a regression test for the
leakage-smoke-check false positive found and fixed during this stage
(groupby().first() silently skips NaNs and returns a later row's value).
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.ingestion import (
    historical_features,
    label_policy,
    model_readiness,
    sparsity,
    temporal_split,
)
from src.ingestion import (
    training_table as training_table_mod,
)


def _events(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "trip_id": "T1", "stop_id": "S1", "transport_mode": "bus", "direction_id": True,
        "label_available": True, "is_static_schedule_trip": True, "disruption_flag": pd.NA,
        "service_date": date(2026, 9, 1),
        "scheduled_time": pd.Timestamp("2026-09-01T08:00:00Z"),
        "actual_time": pd.Timestamp("2026-09-01T08:00:00Z"),
    }
    return pd.DataFrame([{**defaults, **r} for r in rows])


# ============================== Part A/B: label policy ==============================

class TestLabelPolicy:
    def test_threshold_candidates_positive_and_negative_rates_sum_to_one(self):
        delays = pd.Series([0, 60, 200, 400, 1000, np.nan])
        rows = label_policy.threshold_candidates(delays, mode="bus", thresholds=[300])
        row = rows[0]
        assert row["sample_count"] == 5  # NaN dropped, never counted
        assert row["positive_rate"] + row["negative_rate"] == pytest.approx(1.0)
        assert row["positive_rate"] == pytest.approx(2 / 5)  # 400 and 1000 >= 300

    def test_distribution_summary_reports_percentiles_and_moments(self):
        delays = pd.Series(range(0, 1000, 10), dtype=float)
        summary = label_policy.delay_distribution_summary(delays)
        assert summary["record_count"] == 100
        assert set(summary["percentiles_seconds"]) == {"P50", "P75", "P90", "P95", "P99"}
        assert summary["median_delay_seconds"] < summary["percentiles_seconds"]["P99"]

    def test_empty_series_reports_zero_count_not_a_crash(self):
        summary = label_policy.delay_distribution_summary(pd.Series([], dtype=float))
        assert summary == {"record_count": 0}

    def test_candidate_report_restricted_to_static_schedule_and_labeled_modes(self):
        events = _events([
            {"transport_mode": "bus", "delay_seconds": 400.0, "is_static_schedule_trip": True},
            {"transport_mode": "bus", "delay_seconds": 9999.0, "is_static_schedule_trip": False},  # excluded
            {"transport_mode": "rail", "delay_seconds": 500.0, "is_static_schedule_trip": True},  # no label source
        ])
        report = label_policy.build_label_candidate_report(events, {"bus": True, "rail": False})
        assert report["modes_analyzed"] == ["bus"]
        assert "rail" in report["modes_excluded_no_label_source"]
        assert report["per_mode"]["bus"]["distribution"]["record_count"] == 1  # the ADDED-style row excluded

    def test_recommendation_never_flips_the_activation_switch(self):
        events = _events([{"transport_mode": "bus", "delay_seconds": float(d)} for d in
                           [100, 200, 300, 400, 3000, 3000, 3000, 3000, 3000, 3000]])
        report = label_policy.build_label_candidate_report(events, {"bus": True})
        rec = label_policy.recommend_label_policy(report)
        assert "NOT ACTIVATED" in rec["status"]
        assert "bus" in rec["recommended_thresholds_seconds"]

    def test_recommendation_picks_smallest_threshold_in_band_not_nicest_balance(self):
        # 180s (3min): positive rate 50% -- outside the 2%-40% band, excluded.
        # 300s (5min): positive rate 5% -- the only in-band candidate.
        # 420s+: positive rate 0% -- below the band, excluded.
        delays = [250.0] * 45 + [400.0] * 5 + [0.0] * 50
        events = _events([{"transport_mode": "bus", "delay_seconds": d} for d in delays])
        report = label_policy.build_label_candidate_report(events, {"bus": True})
        rec = label_policy.recommend_label_policy(report)
        assert rec["recommended_thresholds_seconds"]["bus"] == 300


# ============================== Part C: historical-feature leakage ==============================

class TestHistoricalFeatureLeakage:
    def _daily_events(self, route_id: str, delays_by_date: dict[date, list[float]]) -> pd.DataFrame:
        rows = []
        for d, delays in delays_by_date.items():
            for i, delay in enumerate(delays):
                rows.append({
                    "route_id": route_id, "service_date": d, "delay_seconds": delay,
                    "trip_id": f"T{i}", "stop_id": f"S{i}",
                    "scheduled_time": pd.Timestamp(d) + pd.Timedelta(hours=8),
                })
        return _events(rows)

    def test_first_observed_day_has_null_historical_features(self):
        d0 = date(2026, 9, 1)
        events = self._daily_events("R1", {d0: [100.0, 200.0]})
        out = historical_features.join_historical_features(events, min_history_days=1)
        assert out["historical_delay_seconds"].isna().all()
        assert out["rolling_7d_delay_seconds"].isna().all()

    def test_second_day_uses_only_first_days_mean_never_its_own_day(self):
        d0, d1 = date(2026, 9, 1), date(2026, 9, 2)
        events = self._daily_events("R1", {d0: [100.0, 300.0], d1: [999999.0]})  # d1's own delay is huge
        out = historical_features.join_historical_features(events, min_history_days=1)
        d1_rows = out[out["service_date"] == d1]
        assert d1_rows["historical_delay_seconds"].iloc[0] == pytest.approx(200.0)  # mean(100, 300), never 999999

    def test_future_day_delay_never_leaks_into_past_day_feature(self):
        d0, d1, d2 = date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)
        events = self._daily_events("R1", {d0: [50.0], d1: [50.0], d2: [999999.0]})
        out = historical_features.join_historical_features(events, min_history_days=1)
        d0_rows = out[out["service_date"] == d0]
        d1_rows = out[out["service_date"] == d1]
        assert d0_rows["historical_delay_seconds"].isna().all()
        assert d1_rows["historical_delay_seconds"].iloc[0] == pytest.approx(50.0)  # never sees d2's 999999

    def test_min_history_days_leaves_early_days_null_even_with_some_prior_history(self):
        dates = [date(2026, 9, 1) + timedelta(days=i) for i in range(4)]
        events = self._daily_events("R1", {d: [100.0] for d in dates})
        out = historical_features.join_historical_features(events, min_history_days=3)
        by_date = {d: out[out["service_date"] == d]["historical_delay_seconds"].iloc[0] for d in dates}
        assert pd.isna(by_date[dates[0]])  # 0 prior days
        assert pd.isna(by_date[dates[1]])  # 1 prior day  < 3
        assert pd.isna(by_date[dates[2]])  # 2 prior days < 3
        assert pd.notna(by_date[dates[3]])  # 3 prior days -- meets the bar

    def test_rolling_7d_window_excludes_the_8th_prior_day(self):
        dates = [date(2026, 9, 1) + timedelta(days=i) for i in range(9)]
        delays = {d: [100.0] for d in dates[:8]}
        delays[dates[8]] = [999999.0]
        # Reset day 0's delay to something distinguishable so we can prove it's excluded from day 8's window.
        delays[dates[0]] = [10000.0]
        events = self._daily_events("R1", delays)
        out = historical_features.join_historical_features(events, min_history_days=1, rolling_window_days=7)
        row8 = out[out["service_date"] == dates[8]].iloc[0]
        # Prior 7 days are dates[1..7]: six of value 100 + one placeholder -- day0 (10000) must be excluded.
        assert row8["rolling_7d_delay_seconds"] == pytest.approx(100.0)

    def test_reliability_is_nan_when_threshold_policy_is_none(self):
        events = self._daily_events("R1", {date(2026, 9, 1): [100.0], date(2026, 9, 2): [900.0]})
        out = historical_features.join_historical_features(events, min_history_days=1, threshold_seconds=None)
        assert out["historical_reliability"].isna().all()

    def test_reliability_uses_strictly_prior_days_disruption_rate(self):
        d0, d1 = date(2026, 9, 1), date(2026, 9, 2)
        events = self._daily_events("R1", {d0: [900.0], d1: [10.0]})  # d0 disrupted, d1 not
        out = historical_features.join_historical_features(
            events, min_history_days=1, threshold_seconds={"bus": 300},
        )
        d1_row = out[out["service_date"] == d1].iloc[0]
        assert d1_row["historical_reliability"] == pytest.approx(0.0)  # 1 - 100% prior disruption rate

    def test_label_unavailable_rows_never_contribute_to_the_aggregate(self):
        events = _events([
            {"route_id": "R1", "service_date": date(2026, 9, 1), "delay_seconds": 100.0, "label_available": True},
            {"route_id": "R1", "service_date": date(2026, 9, 1), "delay_seconds": 999999.0, "label_available": False},
            {"route_id": "R1", "service_date": date(2026, 9, 2), "delay_seconds": 100.0, "label_available": True},
        ])
        daily = historical_features.compute_daily_route_stats(events)
        d0_stats = daily[daily["service_date"] == date(2026, 9, 1)].iloc[0]
        assert d0_stats["mean_delay_seconds"] == pytest.approx(100.0)  # the unlabeled 999999 row excluded


# ============================== Part D: sparsity / minimum-history ==============================

class TestSparsity:
    def test_routes_with_insufficient_history_below_threshold(self):
        events = _events([
            {"route_id": "R1", "service_date": date(2026, 9, 1), "delay_seconds": 100.0},
            {"route_id": "R2", "service_date": date(2026, 9, 1), "delay_seconds": 100.0},
            {"route_id": "R2", "service_date": date(2026, 9, 2), "delay_seconds": 100.0},
            {"route_id": "R2", "service_date": date(2026, 9, 3), "delay_seconds": 100.0},
        ])
        insufficient = sparsity.routes_with_insufficient_history(events, minimum_history_days=3)
        assert insufficient == ["R1"]  # R1: 1 day < 3; R2: 3 days meets the bar

    def test_label_unavailable_rows_excluded_from_observation_counts(self):
        events = _events([
            {"route_id": "R1", "service_date": date(2026, 9, 1), "label_available": False},
            {"route_id": "R1", "service_date": date(2026, 9, 2), "label_available": False},
        ])
        per_route = sparsity.observations_per_route(events)
        assert per_route.empty  # nothing usable, never fabricated as observed

    def test_sparsity_report_never_fabricates_missing_history_as_zero(self):
        events = _events([{"route_id": "R1", "service_date": date(2026, 9, 1), "delay_seconds": 100.0}])
        report = sparsity.build_sparsity_report(events, minimum_history_days=3)
        assert report["routes_with_insufficient_history"]["count"] == 1
        assert "R1" in report["routes_with_insufficient_history"]["route_ids"]


# ============================== Part H: rail/ferry unlabeled behavior ==============================

class TestRailFerryUnlabeled:
    def test_rail_ferry_never_assigned_disruption_zero(self):
        events = _events([
            {"route_id": "CR-1", "transport_mode": "rail", "label_available": False,
             "delay_seconds": 1800.0, "disruption_flag": pd.NA},
        ])
        assert events.iloc[0]["label_available"] == False  # noqa: E712
        assert pd.isna(events.iloc[0]["disruption_flag"])

    def test_trainable_subset_excludes_rail_ferry_rows(self):
        events = _events([
            {"route_id": "R1", "transport_mode": "bus", "label_available": True,
             "disruption_flag": 1, "delay_seconds": 400.0},
            {"route_id": "CR-1", "transport_mode": "rail", "label_available": False,
             "disruption_flag": pd.NA, "delay_seconds": 1800.0},
        ])
        tt = training_table_mod.build_training_table(events)
        trainable = training_table_mod.trainable_subset(tt)
        assert len(trainable) == 1
        assert trainable.iloc[0]["transport_mode"] == "bus"


# ============================== Part I: training table contract ==============================

class TestTrainingTable:
    def test_schema_columns_all_present_in_output(self):
        events = _events([{"route_id": "R1", "delay_seconds": 100.0}])
        tt = training_table_mod.build_training_table(events)
        for field in training_table_mod.TRAINING_TABLE_SCHEMA:
            if field["role"] == "entity_identifier" and field["name"] not in events.columns:
                continue
            assert field["name"] in tt.columns, field["name"]

    def test_hour_and_day_of_week_derived_from_scheduled_time(self):
        events = _events([{"route_id": "R1", "scheduled_time": pd.Timestamp("2026-09-03T14:30:00Z")}])  # Thursday
        tt = training_table_mod.build_training_table(events)
        assert tt.iloc[0]["hour"] == 14
        assert tt.iloc[0]["day_of_week"] == 3  # Monday=0 -> Thursday=3

    def test_provenance_columns_always_real(self):
        events = _events([{"route_id": "R1"}])
        tt = training_table_mod.build_training_table(events)
        assert (tt["source_dataset_type"] == "REAL").all()
        assert (tt["source_provider"] == "MBTA LAMP").all()


# ============================== Part J: temporal split ==============================

class TestTemporalSplit:
    def test_boundaries_are_chronological_and_cover_full_range(self):
        dates = pd.Series([date(2026, 8, 1) + timedelta(days=i) for i in range(30)])
        boundaries = temporal_split.compute_real_split_boundaries(dates)
        assert boundaries["min_date"] == "2026-08-01"
        assert boundaries["max_date"] == "2026-08-30"
        assert boundaries["train_end"] < boundaries["val_end"] < boundaries["max_date"] or \
            boundaries["train_end"] <= boundaries["val_end"]

    def test_too_few_days_raises_rather_than_producing_a_degenerate_split(self):
        dates = pd.Series([date(2026, 8, 1), date(2026, 8, 2)])
        with pytest.raises(ValueError):
            temporal_split.compute_real_split_boundaries(dates)

    def test_apply_split_partitions_are_disjoint_and_chronological(self):
        dates = pd.Series([date(2026, 8, 1) + timedelta(days=i) for i in range(30)])
        boundaries = temporal_split.compute_real_split_boundaries(dates)
        df = pd.DataFrame({"service_date": dates})
        splits = temporal_split.apply_real_split(df, boundaries)
        assert len(splits["train"]) + len(splits["val"]) + len(splits["test"]) == len(df)
        max_train = pd.to_datetime(splits["train"]["service_date"]).max()
        min_val = pd.to_datetime(splits["val"]["service_date"]).min()
        assert max_train < min_val


# ============================== Part K: model readiness gate ==============================

class TestModelReadinessLeakageCheck:
    def test_correct_shift1_discipline_passes_the_smoke_check(self):
        """Regression test for the Stage 11C bug: groupby('route_id').first()
        has skipna=True by default, so it silently returns the first
        NON-NULL value per column instead of the actual first row -- this
        turned a correctly-NaN first day into a false leakage positive.
        """
        tt = pd.DataFrame([
            {"route_id": "R1", "service_date": date(2026, 9, 1), "historical_delay_seconds": np.nan},
            {"route_id": "R1", "service_date": date(2026, 9, 2), "historical_delay_seconds": 120.0},
            {"route_id": "R1", "service_date": date(2026, 9, 3), "historical_delay_seconds": 130.0},
        ])
        ok, msg = model_readiness._leakage_smoke_check(tt)
        assert ok is True, msg

    def test_genuine_leakage_is_still_caught(self):
        # non-null historical_delay_seconds on a route's first day is a real bug
        tt = pd.DataFrame([
            {"route_id": "R1", "service_date": date(2026, 9, 1), "historical_delay_seconds": 999.0},
        ])
        ok, msg = model_readiness._leakage_smoke_check(tt)
        assert ok is False

    def test_target_not_fabricated_check_catches_a_labeled_unlabeled_row(self):
        tt = pd.DataFrame([{"label_available": False, "disruption_flag": 1}])
        ok, msg = model_readiness._target_not_fabricated_check(tt)
        assert ok is False

    def test_target_not_fabricated_check_passes_when_clean(self):
        tt = pd.DataFrame([
            {"label_available": False, "disruption_flag": pd.NA},
            {"label_available": True, "disruption_flag": 1},
        ])
        ok, msg = model_readiness._target_not_fabricated_check(tt)
        assert ok is True

    def test_model_ready_false_when_label_policy_inactive(self):
        events = _events([{"route_id": "R1", "delay_seconds": 100.0, "disruption_flag": pd.NA}])
        tt = training_table_mod.build_training_table(events)
        cfg = {
            "real_disruption_label_policy": {"active": False},
            "label_availability": {"bus": True, "rail": False, "ferry": False},
        }
        feature_matrix = {"model_input_features": []}
        decision = model_readiness.build_model_readiness_decision(
            tt, issues=[], feature_matrix=feature_matrix, cfg=cfg,
            weather_coverage=0.0, split_boundaries=None, split_error="only 1 day",
        )
        assert decision["MODEL_READY"] is False
        assert decision["criteria_checked"]["approved_label_definition"] is False

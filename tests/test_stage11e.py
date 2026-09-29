"""Stage 11E Part 11 tests: feature eligibility, sparse-feature strategy,
missing-value handling, mode-specific coverage, frozen label-policy
verification, the eligible-records temporal split, the feature manifest,
rail/ferry exclusion, provenance, and leakage.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from src.ingestion import feature_eligibility as fe
from src.ingestion import feature_manifest as fm
from src.ingestion import historical_features, label_policy, sparsity
from src.ingestion import real_dataset_readiness as rdr


def _row(**overrides) -> dict:
    base = {
        "route_id": "R1", "service_date": date(2026, 8, 10), "transport_mode": "bus",
        "scheduled_time": pd.Timestamp("2026-08-10T08:00:00Z"), "hour": 8, "day_of_week": 0,
        "day_period": pd.NA, "time_of_day_bucket": pd.NA, "transfer_dependency": pd.NA,
        "precipitation_mm": pd.NA, "temperature_c": pd.NA, "visibility_km": pd.NA,
        "wind_speed_ms": pd.NA, "pressure_hpa": pd.NA,
        "historical_delay_seconds": pd.NA, "rolling_7d_delay_seconds": pd.NA, "historical_reliability": pd.NA,
        "delay_seconds": 100.0, "label_available": True, "disruption_flag": 0,
        "source_provider": "MBTA LAMP", "source_dataset_type": "REAL",
    }
    base.update(overrides)
    return base


def _training_table_with_history(route: str, n_days: int, mode: str = "bus") -> pd.DataFrame:
    """n_days distinct service_dates for `route`, each historically valid
    from the 4th day onward (min_history_days=3 -> day index 3+ has 3 prior days)."""
    rows = []
    for i in range(n_days):
        d = date(2026, 8, 1) + timedelta(days=i)
        rows.append(_row(
            route_id=route, service_date=d, transport_mode=mode,
            scheduled_time=pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=8),
            historical_delay_seconds=50.0 if i >= 3 else pd.NA,
            rolling_7d_delay_seconds=50.0 if i >= 3 else pd.NA,
            historical_reliability=0.9 if i >= 3 else pd.NA,
        ))
    return pd.DataFrame(rows)


# ============================== Part 1: feature coverage report ==============================

class TestFeatureCoverageReport:
    def test_total_nonnull_missing_coverage_reported(self):
        tt = pd.DataFrame([_row(temperature_c=20.0), _row(temperature_c=pd.NA)])
        report = fe.build_feature_coverage_report(tt, None)
        assert report["temperature_c"]["total_rows"] == 2
        assert report["temperature_c"]["non_null_rows"] == 1
        assert report["temperature_c"]["missing_rows"] == 1
        assert report["temperature_c"]["coverage"] == pytest.approx(0.5)

    def test_coverage_by_mode_is_not_global_only(self):
        tt = pd.DataFrame([
            _row(transport_mode="bus", temperature_c=20.0),
            _row(transport_mode="metro", temperature_c=pd.NA),
        ])
        report = fe.build_feature_coverage_report(tt, None)
        assert report["temperature_c"]["coverage_by_mode"]["bus"] == pytest.approx(1.0)
        assert report["temperature_c"]["coverage_by_mode"]["metro"] == pytest.approx(0.0)

    def test_coverage_by_split_period(self):
        boundaries = {"min_date": "2026-08-01", "train_end": "2026-08-10",
                      "val_end": "2026-08-15", "max_date": "2026-08-20"}
        tt = pd.DataFrame([
            _row(service_date=date(2026, 8, 5), temperature_c=20.0),   # train
            _row(service_date=date(2026, 8, 12), temperature_c=pd.NA),  # val
            _row(service_date=date(2026, 8, 18), temperature_c=20.0),  # test
        ])
        report = fe.build_feature_coverage_report(tt, boundaries)
        assert report["temperature_c"]["coverage_by_split"]["train"] == pytest.approx(1.0)
        assert report["temperature_c"]["coverage_by_split"]["val"] == pytest.approx(0.0)
        assert report["temperature_c"]["coverage_by_split"]["test"] == pytest.approx(1.0)

    def test_sparse_features_get_coverage_by_date_others_do_not(self):
        boundaries = {"min_date": "2026-08-01", "train_end": "2026-08-10",
                      "val_end": "2026-08-15", "max_date": "2026-08-20"}
        tt = pd.DataFrame([_row(service_date=date(2026, 8, 5), temperature_c=20.0, hour=8)])
        report = fe.build_feature_coverage_report(tt, boundaries)
        assert "coverage_by_date" in report["temperature_c"]
        assert "coverage_by_date" not in report["hour"]  # not in SPARSE_FEATURES_OF_INTEREST


# ============================== Part 2: feature strategy ==============================

class TestFeatureStrategy:
    def test_high_coverage_feature_included_directly(self):
        tt = pd.DataFrame([_row(hour=h) for h in range(10)])
        report = fe.build_feature_coverage_report(tt, None)
        strategy = fe.recommend_feature_strategy(report)
        assert strategy["hour"]["strategy"] == fe.INCLUDE_DIRECTLY

    def test_moderate_coverage_feature_included_with_strategy_and_documented_handling(self):
        rows = [_row(temperature_c=20.0) for _ in range(6)] + [_row(temperature_c=pd.NA) for _ in range(4)]
        report = fe.build_feature_coverage_report(pd.DataFrame(rows), None)
        strategy = fe.recommend_feature_strategy(report)
        assert strategy["temperature_c"]["strategy"] == fe.INCLUDE_WITH_STRATEGY
        assert strategy["temperature_c"]["missing_value_handling"] is not None
        assert "XGBoost" in strategy["temperature_c"]["missing_value_handling"]

    def test_very_sparse_feature_is_diagnostic_only(self):
        rows = [_row(wind_speed_ms=3.0) for _ in range(7)] + [_row(wind_speed_ms=pd.NA) for _ in range(93)]
        report = fe.build_feature_coverage_report(pd.DataFrame(rows), None)
        strategy = fe.recommend_feature_strategy(report)
        assert strategy["wind_speed_ms"]["strategy"] == fe.DIAGNOSTIC_ONLY

    def test_near_zero_coverage_feature_excluded(self):
        rows = [_row(pressure_hpa=1013.0)] + [_row(pressure_hpa=pd.NA) for _ in range(999)]
        report = fe.build_feature_coverage_report(pd.DataFrame(rows), None)
        strategy = fe.recommend_feature_strategy(report)
        assert strategy["pressure_hpa"]["strategy"] == fe.EXCLUDE

    def test_never_wired_structural_feature_excluded_with_distinct_rationale(self):
        tt = pd.DataFrame([_row()])
        report = fe.build_feature_coverage_report(tt, None)
        strategy = fe.recommend_feature_strategy(report)
        assert strategy["day_period"]["strategy"] == fe.EXCLUDE
        assert "never wired" in strategy["day_period"]["rationale"]

    def test_historical_reliability_zero_coverage_flagged_as_policy_inactive_not_sparsity(self):
        tt = pd.DataFrame([_row()])  # historical_reliability all NaN
        report = fe.build_feature_coverage_report(tt, None)
        strategy = fe.recommend_feature_strategy(report)
        assert strategy["historical_reliability"]["strategy"] == fe.EXCLUDE
        assert "label policy" in strategy["historical_reliability"]["rationale"]

    def test_strategy_never_maximizes_coverage_by_construction(self):
        """Regression guard: the bands are fixed constants, not derived
        from searching for whatever split looks best on this data."""
        assert fe.COVERAGE_INCLUDE_DIRECTLY == 0.95
        assert fe.COVERAGE_INCLUDE_WITH_STRATEGY == 0.50
        assert fe.COVERAGE_DIAGNOSTIC_ONLY_FLOOR == 0.05


# ============================== Part 4: eligible dataset ==============================

class TestEligibleDataset:
    def test_label_unavailable_rows_excluded(self):
        tt = pd.DataFrame([
            _row(label_available=True, disruption_flag=1, historical_delay_seconds=50.0),
            _row(route_id="CR-1", transport_mode="rail", label_available=False, disruption_flag=pd.NA),
        ])
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        eligible = fe.build_eligible_dataset(tt, strategy, minimum_history_days=0)
        assert len(eligible) == 1
        assert eligible.iloc[0]["transport_mode"] == "bus"

    def test_null_label_despite_availability_excluded(self):
        tt = pd.DataFrame([_row(label_available=True, disruption_flag=pd.NA, historical_delay_seconds=50.0)])
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        eligible = fe.build_eligible_dataset(tt, strategy, minimum_history_days=0)
        assert len(eligible) == 0

    def test_insufficient_history_excluded(self):
        tt = _training_table_with_history("R1", n_days=5)
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        eligible = fe.build_eligible_dataset(tt, strategy, minimum_history_days=3)
        # days 0,1,2 (indices) are zero/insufficient; days 3,4 are valid
        assert len(eligible) == 2

    def test_diagnostic_only_or_strategy_features_never_gate_eligibility(self):
        """A row must not be dropped merely because a sparse weather
        feature (INCLUDE_WITH_STRATEGY/DIAGNOSTIC_ONLY) is null -- that
        would silently discard most of the real dataset."""
        tt = _training_table_with_history("R1", n_days=4)  # index 3 is valid history
        # temperature_c is null for all rows in this fixture (never set) -> sparse -> non-gating
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        eligible = fe.build_eligible_dataset(tt, strategy, minimum_history_days=3)
        assert len(eligible) == 1  # the one valid-history row survives despite null temperature_c


# ============================== Part 4: eligibility report ==============================

class TestEligibilityReport:
    def test_totals_and_percentage(self):
        tt = pd.DataFrame([
            _row(label_available=True, disruption_flag=1, historical_delay_seconds=50.0),
            _row(route_id="CR-1", transport_mode="rail", label_available=False, disruption_flag=pd.NA),
        ])
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        eligible = fe.build_eligible_dataset(tt, strategy, minimum_history_days=0)
        report = fe.build_eligibility_report(tt, eligible, minimum_history_days=0)
        assert report["total_real_records"] == 2
        assert report["eligible_records"] == 1
        assert report["excluded_records"] == 1
        assert report["exclusion_percentage"] == pytest.approx(0.5)
        assert report["exclusion_reasons"]["label_unavailable_mode_rail_ferry"] == 1

    def test_never_silently_discards_without_a_reported_reason(self):
        tt = _training_table_with_history("R1", n_days=5)
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        eligible = fe.build_eligible_dataset(tt, strategy, minimum_history_days=3)
        report = fe.build_eligibility_report(tt, eligible, minimum_history_days=3)
        assert report["exclusion_reasons"]["insufficient_or_zero_historical_feature_history"] == 3


# ============================== Part 5: minimum history ==============================

class TestHistoryStatus:
    def test_zero_insufficient_valid_classification(self):
        tt = _training_table_with_history("R1", n_days=5)
        status = sparsity.history_status_per_row(tt, minimum_history_days=3)
        assert list(status) == ["zero", "insufficient", "insufficient", "valid", "valid"]

    def test_history_status_report_by_mode(self):
        bus = _training_table_with_history("R1", n_days=5, mode="bus")
        metro = _training_table_with_history("R2", n_days=1, mode="metro")
        tt = pd.concat([bus, metro], ignore_index=True)
        report = sparsity.build_history_status_report(tt, minimum_history_days=3)
        assert report["records_with_valid_history"] == 2
        assert report["records_with_zero_history"] == 2  # R1 day0 + R2 day0
        assert "bus" in report["coverage_by_mode"]
        assert "metro" in report["coverage_by_mode"]

    def test_never_fabricates_history_for_short_routes(self):
        tt = _training_table_with_history("R1", n_days=2)
        status = sparsity.history_status_per_row(tt, minimum_history_days=3)
        assert (status != "valid").all()


# ============================== Part 6: frozen label policy verification ==============================

class TestFrozenLabelVerification:
    FROZEN = {"bus": 300, "metro": 180, "tram": 180}

    def test_positive_negative_rate_computed(self):
        tt = pd.DataFrame([
            _row(transport_mode="bus", delay_seconds=400.0, disruption_flag=1),
            _row(transport_mode="bus", delay_seconds=10.0, disruption_flag=0),
        ])
        result = label_policy.verify_frozen_label_policy(tt, self.FROZEN)
        assert result["per_mode"]["bus"]["positive_rate"] == pytest.approx(0.5)
        assert result["per_mode"]["bus"]["negative_rate"] == pytest.approx(0.5)

    def test_consistency_check_passes_when_flag_matches_threshold(self):
        tt = pd.DataFrame([
            _row(transport_mode="bus", delay_seconds=400.0, disruption_flag=1),
            _row(transport_mode="bus", delay_seconds=10.0, disruption_flag=0),
        ])
        result = label_policy.verify_frozen_label_policy(tt, self.FROZEN)
        assert result["per_mode"]["bus"]["consistency_check_passed"] is True
        assert result["all_consistency_checks_passed"] is True

    def test_consistency_check_catches_a_mismatch(self):
        tt = pd.DataFrame([
            _row(transport_mode="bus", delay_seconds=400.0, disruption_flag=0),  # wrong: should be 1
        ])
        result = label_policy.verify_frozen_label_policy(tt, self.FROZEN)
        assert result["per_mode"]["bus"]["consistency_check_passed"] is False
        assert result["all_consistency_checks_passed"] is False

    def test_rail_ferry_have_no_frozen_threshold_and_stay_null(self):
        tt = pd.DataFrame([
            _row(route_id="CR-1", transport_mode="rail", label_available=False, disruption_flag=pd.NA),
        ])
        result = label_policy.verify_frozen_label_policy(tt, self.FROZEN)
        assert result["per_mode"]["rail"]["disruption_flag_all_null"] is True
        assert result["per_mode"]["rail"]["label_available"] is False

    def test_missing_labels_counted(self):
        tt = pd.DataFrame([
            _row(transport_mode="bus", delay_seconds=400.0, disruption_flag=1),
            _row(transport_mode="bus", delay_seconds=50.0, disruption_flag=pd.NA),
        ])
        result = label_policy.verify_frozen_label_policy(tt, self.FROZEN)
        assert result["per_mode"]["bus"]["missing_label_rows"] == 1


# ==================== Part 5: historical_reliability min_history_days consistency ====================

class TestHistoricalReliabilityMinHistoryConsistency:
    """Regression test for a real Stage 11E finding: historical_reliability
    used to hardcode min_periods=1 regardless of the caller's
    min_history_days, giving it a looser minimum-history bar than
    historical_delay_seconds/rolling_7d_delay_seconds computed from the
    SAME daily series -- on real data this produced 86.1% coverage for
    historical_reliability vs. 68.0% for the other two, despite all three
    nominally sharing one 3-day minimum-history policy.
    """

    def _events(self, route: str, n_days: int) -> pd.DataFrame:
        rows = []
        for i in range(n_days):
            d = date(2026, 8, 1) + timedelta(days=i)
            rows.append({
                "route_id": route, "service_date": d, "transport_mode": "bus",
                "delay_seconds": 100.0, "label_available": True, "is_static_schedule_trip": True,
                "disruption_flag": pd.NA, "trip_id": f"T{i}", "stop_id": f"S{i}",
                "scheduled_time": pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=8),
                "actual_time": pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=8),
            })
        return pd.DataFrame(rows)

    def test_reliability_respects_the_same_min_history_days_as_delay_features(self):
        events = self._events("R1", n_days=5)
        out = historical_features.join_historical_features(
            events, min_history_days=3, threshold_seconds={"bus": 300},
        )
        # day index 0,1,2 have < 3 strictly-prior days -- historical_reliability
        # must be NaN there too, matching historical_delay_seconds's own NaN pattern.
        by_date = out.sort_values("service_date")
        assert by_date["historical_delay_seconds"].isna().tolist() == by_date["historical_reliability"].isna().tolist()

    def test_min_history_days_1_still_works_as_before(self):
        events = self._events("R1", n_days=3)
        out = historical_features.join_historical_features(
            events, min_history_days=1, threshold_seconds={"bus": 300},
        )
        by_date = out.sort_values("service_date")
        # first day NaN (0 prior days); from day 2 onward (1+ prior day), both populated
        assert by_date["historical_reliability"].isna().tolist()[0] is True or pd.isna(
            by_date["historical_reliability"].iloc[0])
        assert by_date["historical_reliability"].notna().sum() == 2


# ============================== Part 7: eligible-dataset temporal split ==============================

class TestEligibleTemporalSplit:
    def test_split_preserves_chronological_order_no_leakage(self):
        from src.ingestion.temporal_split import apply_real_split, compute_real_split_boundaries

        rows = []
        for i in range(30):
            d = date(2026, 8, 1) + timedelta(days=i)
            rows.append(_row(service_date=d, disruption_flag=i % 2))
        eligible = pd.DataFrame(rows)
        boundaries = compute_real_split_boundaries(eligible["service_date"])
        splits = apply_real_split(eligible, boundaries)

        max_train = pd.to_datetime(splits["train"]["service_date"]).max()
        min_val = pd.to_datetime(splits["val"]["service_date"]).min()
        max_val = pd.to_datetime(splits["val"]["service_date"]).max()
        min_test = pd.to_datetime(splits["test"]["service_date"]).min()
        assert max_train < min_val
        assert max_val < min_test
        assert len(splits["train"]) + len(splits["val"]) + len(splits["test"]) == len(eligible)


# ============================== Part 8: feature manifest ==============================

class TestFeatureManifest:
    def test_every_column_classified_into_exactly_one_category(self):
        tt = pd.DataFrame([_row(hour=h) for h in range(20)])
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        manifest = fm.build_feature_manifest(strategy)
        categories = {e["category"] for e in manifest["features"]}
        assert categories <= {fm.MODEL_FEATURE, fm.DIAGNOSTIC_ONLY, fm.IDENTIFIER, fm.LABEL, fm.PROVENANCE}

    def test_label_and_provenance_columns_classified_correctly(self):
        tt = pd.DataFrame([_row(hour=h) for h in range(20)])
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        manifest = fm.build_feature_manifest(strategy)
        by_name = {e["name"]: e for e in manifest["features"]}
        assert by_name["disruption_flag"]["category"] == fm.LABEL
        assert by_name["source_provider"]["category"] == fm.PROVENANCE
        assert by_name["record_id"]["category"] == fm.IDENTIFIER

    def test_model_feature_entries_document_required_fields(self):
        rows = [_row(hour=h, temperature_c=20.0) for h in range(20)]
        tt = pd.DataFrame(rows)
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        manifest = fm.build_feature_manifest(strategy)
        by_name = {e["name"]: e for e in manifest["features"]}
        hour_entry = by_name["hour"]
        assert hour_entry["category"] == fm.MODEL_FEATURE
        for key in ["data_source", "measured_coverage", "missing_value_behavior", "leakage_status", "unit", "meaning"]:
            assert key in hour_entry


# ============================== Part 9/10: rail/ferry, real-dataset readiness ==============================

class TestRailFerryAndReadiness:
    def test_rail_ferry_excluded_from_eligible_dataset(self):
        tt = pd.DataFrame([
            _row(label_available=True, disruption_flag=1, historical_delay_seconds=50.0),
            _row(route_id="CR-1", transport_mode="rail", label_available=False, disruption_flag=pd.NA),
            _row(route_id="B-1", transport_mode="ferry", label_available=False, disruption_flag=pd.NA),
        ])
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        eligible = fe.build_eligible_dataset(tt, strategy, minimum_history_days=0)
        assert "rail" not in eligible["transport_mode"].unique()
        assert "ferry" not in eligible["transport_mode"].unique()

    def test_real_dataset_ready_false_when_labels_inconsistent(self):
        tt = pd.DataFrame([_row(transport_mode="bus", delay_seconds=400.0, disruption_flag=0)])  # wrong flag
        frozen = {"bus": 300, "metro": 180, "tram": 180}
        label_verification = label_policy.verify_frozen_label_policy(tt, frozen)
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        eligible = fe.build_eligible_dataset(tt, strategy, minimum_history_days=0)
        coverage_report = fe.build_feature_coverage_report(tt, None)
        decision = rdr.build_real_dataset_readiness_decision(
            tt, eligible, coverage_report, strategy, label_verification,
            weather_coverage=0.27, split_boundaries=None, split_error="only 1 day",
        )
        assert decision["REAL_DATASET_READY"] is False
        assert decision["criteria_checked"]["valid_real_labels"] is False

    def test_real_dataset_ready_does_not_require_high_weather_coverage(self):
        """Weather coverage is reported, not gated -- confirm a low
        weather_coverage value alone does not appear as a blocking reason."""
        tt = pd.DataFrame([_row(transport_mode="bus", delay_seconds=400.0, disruption_flag=1)])
        frozen = {"bus": 300, "metro": 180, "tram": 180}
        label_verification = label_policy.verify_frozen_label_policy(tt, frozen)
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        eligible = fe.build_eligible_dataset(tt, strategy, minimum_history_days=0)
        coverage_report = fe.build_feature_coverage_report(tt, None)
        decision = rdr.build_real_dataset_readiness_decision(
            tt, eligible, coverage_report, strategy, label_verification,
            weather_coverage=0.05, split_boundaries={"a": 1}, split_error=None,
        )
        assert not any("weather" in r.lower() and "coverage is" not in r.lower()
                        for r in decision["blocking_reasons"])

    def test_mode_missing_from_a_split_is_a_non_blocking_caveat(self):
        """Regression test for a real Stage 11E finding: bus's real
        historical-performance source is a bounded ~7-9 day rolling
        window (Stage 11B), so when the eligible-dataset chronological
        split lands that window entirely inside one split, the other
        splits have ZERO bus records -- this must be surfaced as a
        caveat, not silently dropped, but must NOT flip REAL_DATASET_READY
        to False since it isn't one of Task 10's listed criteria.
        """
        tt = pd.DataFrame([
            _row(transport_mode="bus", delay_seconds=400.0, disruption_flag=1),
            _row(transport_mode="metro", delay_seconds=400.0, disruption_flag=1),
        ])
        frozen = {"bus": 300, "metro": 180, "tram": 180}
        label_verification = label_policy.verify_frozen_label_policy(tt, frozen)
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        eligible = fe.build_eligible_dataset(tt, strategy, minimum_history_days=0)
        coverage_report = fe.build_feature_coverage_report(tt, None)
        eligible_split_summary = {
            "train": {"mode_distribution": {"metro": 1}},  # bus missing here
            "test": {"mode_distribution": {"bus": 1, "metro": 1}},
        }
        decision = rdr.build_real_dataset_readiness_decision(
            tt, eligible, coverage_report, strategy, label_verification,
            weather_coverage=0.27, split_boundaries={"a": 1}, split_error=None,
            eligible_split_summary=eligible_split_summary,
        )
        # the caveat itself must never appear as a blocking reason -- this
        # fixture is intentionally tiny and fails the record-count bar for
        # an unrelated reason, so REAL_DATASET_READY overall is not asserted here.
        assert not any("bus" in r.lower() and "train" in r.lower() for r in decision["blocking_reasons"])
        assert any("bus" in c and "train" in c for c in decision["caveats_non_blocking"])

    def test_no_caveat_when_all_modes_present_in_every_split(self):
        tt = pd.DataFrame([_row(transport_mode="bus", delay_seconds=400.0, disruption_flag=1)])
        frozen = {"bus": 300, "metro": 180, "tram": 180}
        label_verification = label_policy.verify_frozen_label_policy(tt, frozen)
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        eligible = fe.build_eligible_dataset(tt, strategy, minimum_history_days=0)
        coverage_report = fe.build_feature_coverage_report(tt, None)
        eligible_split_summary = {
            "train": {"mode_distribution": {"bus": 1}},
            "test": {"mode_distribution": {"bus": 1}},
        }
        decision = rdr.build_real_dataset_readiness_decision(
            tt, eligible, coverage_report, strategy, label_verification,
            weather_coverage=0.27, split_boundaries={"a": 1}, split_error=None,
            eligible_split_summary=eligible_split_summary,
        )
        assert decision["caveats_non_blocking"] == []


# ============================== Provenance ==============================

class TestProvenance:
    def test_eligible_rows_retain_real_provenance(self):
        tt = pd.DataFrame([_row(label_available=True, disruption_flag=1, historical_delay_seconds=50.0)])
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        eligible = fe.build_eligible_dataset(tt, strategy, minimum_history_days=0)
        assert (eligible["source_dataset_type"] == "REAL").all()
        assert eligible["source_provider"].notna().all()


# ============================== Leakage ==============================

class TestLeakage:
    def test_eligibility_rule_never_uses_disruption_flag_as_a_feature(self):
        """disruption_flag participates only in the eligibility MASK
        (row inclusion), never as a column inside feature_strategy's
        MODEL_FEATURE set -- it must never leak into model inputs."""
        tt = pd.DataFrame([_row(label_available=True, disruption_flag=1, historical_delay_seconds=50.0)])
        strategy = fe.recommend_feature_strategy(fe.build_feature_coverage_report(tt, None))
        assert "disruption_flag" not in strategy

    def test_history_status_uses_only_strictly_prior_days(self):
        tt = _training_table_with_history("R1", n_days=10)
        status = sparsity.history_status_per_row(tt, minimum_history_days=3)
        # day index 2 (3rd day) has exactly 2 prior days -> insufficient, never valid
        assert status.iloc[2] == "insufficient"
        assert status.iloc[3] == "valid"

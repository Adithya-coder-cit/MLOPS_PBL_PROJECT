"""Tests that specifically prove the historical/rolling features cannot see
same-day or future information — the core anti-leakage requirement for
this temporal prediction problem.
"""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.features.historical import join_historical_features
from src.features.network import compute_transfer_dependency_feature


def _make_fixture():
    # Route R1 runs 5 days with known delays: 10, 20, 30, 40, 50.
    # Route R2 runs 3 days with known delays: 0, 100, 0 (disruption on day 2 only).
    rows = []
    for i, delay in enumerate([10, 20, 30, 40, 50]):
        rows.append({"route_id": "R1", "service_date": date(2025, 6, 1 + i),
                      "delay_minutes": delay, "disruption_flag": 0})
    for i, (delay, flag) in enumerate([(0, 0), (100, 1), (0, 0)]):
        rows.append({"route_id": "R2", "service_date": date(2025, 6, 1 + i),
                      "delay_minutes": delay, "disruption_flag": flag})
    return pd.DataFrame(rows)


def test_historical_delay_first_day_is_nan():
    df = _make_fixture()
    out = join_historical_features(df)
    first_day = out[(out.route_id == "R1") & (out.service_date == date(2025, 6, 1))]
    assert first_day["historical_delay_minutes"].isna().all()
    assert first_day["rolling_7d_delay_minutes"].isna().all()


def test_historical_delay_excludes_current_day():
    df = _make_fixture()
    out = join_historical_features(df)
    # R1 day 3 (2025-06-03, delay=30): historical mean must be mean(10, 20) = 15, NOT including 30.
    day3 = out[(out.route_id == "R1") & (out.service_date == date(2025, 6, 3))].iloc[0]
    assert day3["historical_delay_minutes"] == pytest.approx(15.0)
    # It must NOT equal the mean including today (10+20+30)/3 = 20.
    assert day3["historical_delay_minutes"] != pytest.approx(20.0)


def test_historical_delay_never_uses_future_days():
    df = _make_fixture()
    out = join_historical_features(df)
    # R1 day 1 (earliest day): must never have used day 2-5's delays (20,30,40,50).
    day1 = out[(out.route_id == "R1") & (out.service_date == date(2025, 6, 1))].iloc[0]
    assert pd.isna(day1["historical_delay_minutes"])  # no prior data at all — proves no future leakage


def test_rolling_7d_matches_manual_backward_computation():
    df = _make_fixture()
    out = join_historical_features(df, rolling_window_days=7)
    # R1 day 5 (delay=50): all 4 prior days fit within a 7-day window -> mean(10,20,30,40) = 25.
    day5 = out[(out.route_id == "R1") & (out.service_date == date(2025, 6, 5))].iloc[0]
    assert day5["rolling_7d_delay_minutes"] == pytest.approx(25.0)


def test_historical_reliability_excludes_current_day_disruption():
    df = _make_fixture()
    out = join_historical_features(df)
    # R2 day 3 (2025-06-03): prior disruption_flags were [0, 1] (days 1,2) -> reliability = 1 - 0.5 = 0.5.
    day3 = out[(out.route_id == "R2") & (out.service_date == date(2025, 6, 3))].iloc[0]
    assert day3["historical_reliability"] == pytest.approx(0.5)


def test_historical_features_do_not_depend_on_other_routes():
    df = _make_fixture()
    out = join_historical_features(df)
    # R2's features must be computed only from R2's own history, never R1's.
    r2_day2 = out[(out.route_id == "R2") & (out.service_date == date(2025, 6, 2))].iloc[0]
    assert r2_day2["historical_delay_minutes"] == pytest.approx(0.0)  # only R2 day1's delay=0


def test_transfer_dependency_is_structural_only_no_outcome_columns_needed():
    """transfer_dependency must be computable from the static schedule alone
    — proves it cannot encode any realized-outcome information, since the
    function is never even given access to historical_operational_records."""
    stop_times = pd.DataFrame({
        "trip_id": ["T1", "T2"], "stop_id": ["S1", "S1"],
        "stop_sequence": [0, 0],
        "scheduled_arrival": ["08:00:00", "08:05:00"],
        "scheduled_departure": ["08:00:00", "08:05:00"],
    })
    trips = pd.DataFrame({
        "trip_id": ["T1", "T2"], "route_id": ["R1", "R2"], "service_id": ["weekday", "weekday"],
    })
    result = compute_transfer_dependency_feature(stop_times, trips, window_minutes=10)
    assert set(result.columns) == {"trip_id", "stop_id", "transfer_dependency"}
    # T1 and T2 are different routes, 5 min apart, within the 10-min window -> each sees the other.
    assert result.loc[result.trip_id == "T1", "transfer_dependency"].iloc[0] == 1
    assert result.loc[result.trip_id == "T2", "transfer_dependency"].iloc[0] == 1


def test_join_historical_features_output_is_backward_looking_for_every_row():
    """General property test over a larger random fixture: for every row,
    historical_delay_minutes must equal the mean of strictly-prior days'
    delays for that route (recomputed independently here)."""
    rng = np.random.default_rng(0)
    rows = []
    for route in ["A", "B", "C"]:
        for day_offset in range(15):
            rows.append({
                "route_id": route,
                "service_date": date(2025, 6, 1 + day_offset),
                "delay_minutes": float(rng.normal(5, 2)),
                "disruption_flag": int(rng.random() < 0.2),
            })
    df = pd.DataFrame(rows)
    out = join_historical_features(df)

    for _, row in out.iterrows():
        prior = df[(df.route_id == row.route_id) & (df.service_date < row.service_date)]
        if len(prior) == 0:
            assert pd.isna(row["historical_delay_minutes"])
        else:
            expected = prior["delay_minutes"].mean()
            assert row["historical_delay_minutes"] == pytest.approx(expected)

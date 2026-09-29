"""Stage 11C/11D orchestrator: INGEST (GTFS + historical + NWS/NOAA GHCNh
weather) -> NORMALIZE -> VALIDATE -> LABEL POLICY ANALYSIS -> HISTORICAL
FEATURES -> SPARSITY -> TRAINING TABLE -> TEMPORAL SPLIT -> WEATHER
COVERAGE ANALYSIS -> EDA -> FEATURE AVAILABILITY -> MODEL READINESS
DECISION.

Deliberately does NOT retrain, register, or promote any model (Stage 11B
Sec 23, unchanged in Stage 11C Part N) -- it stops after producing the
reports a human uses to decide whether Stage 12 (real feature-pipeline
integration + retraining) should proceed.

By default this reuses the raw files already downloaded under
data/raw/real/ rather than re-downloading on every run; pass --download
to fetch fresh copies first.

Run: python -m src.ingestion.run_real_ingestion
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
from pathlib import Path

import pandas as pd
import yaml

from src.ingestion.gtfs.normalize import (
    build_service_calendar,
    normalize_fares,
    normalize_routes,
    normalize_stop_times,
    normalize_stops,
    normalize_trips,
)
from src.ingestion.gtfs.parser import parse_gtfs_zip
from src.ingestion.gtfs.validator import run_gtfs_validation
from src.ingestion.historical.mbta_lamp import load_bus_events, load_subway_performance
from src.ingestion.historical.normalize import (
    apply_real_disruption_label_policy,
    normalize_bus_events,
    normalize_subway_performance,
)
from src.ingestion.weather import ghcnh
from src.ingestion.weather.normalize import (
    assign_weather_zone,
    combine_weather_sources,
    join_weather_asof,
    normalize_ghcnh_observations,
)
from src.ingestion.weather.validate import run_weather_validation

logger = logging.getLogger("routewise.ingestion.run_real_ingestion")

RAW_REAL_DIR = Path("data/raw/real")
OUT_DIR = Path("data/interim/real")
CONFIG_PATH = Path("configs/real_data.yaml")


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def ingest_ghcnh_weather(cfg: dict) -> pd.DataFrame:
    """Stage 11D: downloads (if not already present) and normalizes NOAA
    GHCNh station-year PSV files into the canonical weather contract.
    Idempotent -- reuses already-downloaded files under
    data/raw/real/weather/noaa/, same convention as GTFS/LAMP raw sources.
    """
    ghcnh_cfg = cfg["sources"].get("weather_ghcnh")
    if not ghcnh_cfg:
        return pd.DataFrame()

    dest_dir = RAW_REAL_DIR / "weather" / "noaa"
    station_id = ghcnh_cfg["station_id"]
    years = ghcnh_cfg["years"]
    paths = []
    for year in years:
        dest_path = dest_dir / f"GHCNh_{station_id}_{year}.psv"
        try:
            ghcnh.fetch_station_year(station_id, year, dest_path)
            paths.append(dest_path)
        except Exception as exc:  # noqa: BLE001 -- network source, log and continue with what's downloaded
            logger.warning("GHCNh fetch failed for %s %d: %s", station_id, year, exc)

    raw = ghcnh.load_station_years(paths)
    if raw.empty:
        return pd.DataFrame()

    provenance = ghcnh.save_provenance(station_id, years, dest_dir)
    logger.info("GHCNh provenance: %s", provenance.to_dict())

    return normalize_ghcnh_observations(raw, ghcnh_cfg["weather_zone_id"])


def ingest_and_normalize(cfg: dict) -> dict[str, pd.DataFrame]:
    logger.info("Parsing real GTFS feed")
    gtfs_tables = parse_gtfs_zip(RAW_REAL_DIR / "gtfs" / "MBTA_GTFS.zip")

    stops = normalize_stops(gtfs_tables["stops"])
    routes, mode_issues = normalize_routes(gtfs_tables["routes"], cfg["mode_mapping"])
    for issue in mode_issues:
        logger.warning("Mode mapping issue: %s", issue.to_dict())
    trips = normalize_trips(gtfs_tables["trips"])
    stop_times = normalize_stop_times(gtfs_tables["stop_times"])
    service_calendar = build_service_calendar(gtfs_tables.get("calendar"), gtfs_tables.get("calendar_dates"))
    fares = normalize_fares(gtfs_tables.get("fare_products"), gtfs_tables.get("fare_leg_rules"), routes)

    route_to_mode = dict(zip(routes["route_id"], routes["transport_mode"]))

    logger.info("Loading + normalizing real historical performance data")
    subway_files = sorted(glob.glob(str(RAW_REAL_DIR / "historical" / "subway" / "*.parquet")))
    subway_raw = load_subway_performance([Path(f) for f in subway_files])
    subway_events = normalize_subway_performance(subway_raw, route_to_mode, cfg["label_availability"])

    bus_path = RAW_REAL_DIR / "historical" / "bus" / "LAMP_RECENT_Bus_Events.parquet"
    bus_events = pd.DataFrame()
    if bus_path.exists():
        bus_raw = load_bus_events(bus_path)
        bus_events = normalize_bus_events(bus_raw, route_to_mode, cfg["label_availability"])

    operational_events = pd.concat([subway_events, bus_events], ignore_index=True)

    # Stage 11C Part A/K: the label-policy threshold is a config-driven,
    # human-approved switch -- if inactive (default), disruption_flag stays
    # null for every row, exactly as historical/normalize.py already left it.
    operational_events = apply_real_disruption_label_policy(
        operational_events, cfg["real_disruption_label_policy"],
    )

    weather_path = RAW_REAL_DIR / "weather" / "KBOS_observations.parquet"
    nws_raw = pd.read_parquet(weather_path) if weather_path.exists() else pd.DataFrame()
    nws_weather = pd.DataFrame()
    if not nws_raw.empty:
        # KBOS_observations.parquet is already the normalize_nws_observations
        # output from an earlier run (see nws.py) -- add the Stage 11D
        # `source` column if reused from before that column existed.
        nws_weather = nws_raw.copy()
        if "source" not in nws_weather.columns:
            nws_weather["source"] = "NWS"

    logger.info("Fetching NOAA GHCNh weather")
    ghcnh_weather = ingest_ghcnh_weather(cfg)

    # Stage 11D: GHCNh preferred (deeper QC'd official archive, richer
    # fields) wherever both sources report the exact same instant; NWS
    # fills in whatever GHCNh does not (currently: the recent window
    # GHCNh's publication lag has not yet reached).
    weather = combine_weather_sources([ghcnh_weather, nws_weather], source_priority=["NOAA GHCNh", "NWS"])

    weather_issues = run_weather_validation(weather)
    for issue in weather_issues:
        logger.warning("Weather validation issue: %s", issue.to_dict())

    stops_z = assign_weather_zone(stops, cfg["sources"]["weather"]["station"])
    if not weather.empty:
        operational_events = join_weather_asof(
            operational_events, weather, stops_z, cfg["weather_join"]["max_time_difference_hours"],
        )

    return {
        "stops": stops, "routes": routes, "trips": trips, "stop_times": stop_times,
        "service_calendar": service_calendar, "fares": fares,
        "operational_events": operational_events, "weather": weather, "mode_issues": mode_issues,
        "weather_issues": weather_issues,
    }


def write_canonical_tables(tables: dict[str, pd.DataFrame]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in ["stops", "routes", "trips", "stop_times", "service_calendar", "fares", "operational_events",
                 "weather"]:
        df = tables[name]
        if df is None or df.empty:
            logger.warning("Table '%s' is empty -- writing an empty Parquet file, not skipping.", name)
        df.to_parquet(OUT_DIR / f"{name}.parquet", index=False)
    logger.info("Wrote canonical real-data tables to %s", OUT_DIR)


def run_validation(tables: dict[str, pd.DataFrame]) -> list:
    return run_gtfs_validation(
        tables["stops"], tables["routes"], tables["trips"], tables["stop_times"], tables["service_calendar"],
    )


def main(skip_download: bool = True) -> dict:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    cfg = load_config()

    tables = ingest_and_normalize(cfg)
    write_canonical_tables(tables)

    issues = run_validation(tables) + tables["weather_issues"]
    errors = [i for i in issues if i.level == "ERROR"]
    logger.info("Validation: %d issue(s), %d error(s)", len(issues), len(errors))

    (OUT_DIR / "weather_validation_report.json").write_text(
        json.dumps([i.to_dict() for i in tables["weather_issues"]], indent=2, default=str), encoding="utf-8")

    from src.ingestion.data_quality_report import build_data_quality_report
    from src.ingestion.eda import build_eda_report
    from src.ingestion.feature_availability import build_feature_availability_matrix
    from src.ingestion.historical_features import join_historical_features
    from src.ingestion.label_policy import build_label_candidate_report, recommend_label_policy
    from src.ingestion.model_readiness import build_model_readiness_decision
    from src.ingestion.sparsity import build_sparsity_report
    from src.ingestion.temporal_split import apply_real_split, compute_real_split_boundaries
    from src.ingestion.training_table import build_training_table
    from src.ingestion.weather_coverage import build_weather_coverage_report

    dq_report = build_data_quality_report(tables, issues, cfg)
    (OUT_DIR / "data_quality_report.json").write_text(json.dumps(dq_report, indent=2, default=str), encoding="utf-8")

    # Part A/B: label candidate analysis + recommendation (never activates
    # anything -- purely descriptive, for human review).
    label_candidate_report = build_label_candidate_report(tables["operational_events"], cfg["label_availability"])
    (OUT_DIR / "label_candidate_report.json").write_text(
        json.dumps(label_candidate_report, indent=2, default=str), encoding="utf-8")

    label_recommendation = recommend_label_policy(label_candidate_report)
    (OUT_DIR / "label_policy_recommendation.json").write_text(
        json.dumps(label_recommendation, indent=2, default=str), encoding="utf-8")
    logger.info("Label policy recommendation (NOT activated): %s",
                label_recommendation["recommended_thresholds_seconds"])

    # Part D: sparsity report, computed BEFORE historical features so the
    # min_history_days policy used below is traceable to measured numbers.
    sparsity_report = build_sparsity_report(tables["operational_events"])
    (OUT_DIR / "sparsity_report.json").write_text(json.dumps(sparsity_report, indent=2, default=str), encoding="utf-8")

    # Part C: real historical features -- (route_id, service_date) grouping,
    # shift(1)-before-window, strictly-prior-day discipline. threshold_seconds
    # is only non-None if the label policy has actually been activated.
    active_thresholds = (
        cfg["real_disruption_label_policy"]["placeholder_thresholds_seconds"]
        if cfg["real_disruption_label_policy"]["active"] else None
    )
    events_with_features = join_historical_features(
        tables["operational_events"],
        rolling_window_days=7,
        min_history_days=sparsity_report["minimum_history_days_policy"],
        threshold_seconds=active_thresholds,
    )

    # Part I: assemble the final training-table contract.
    training_table = build_training_table(events_with_features)
    training_table.to_parquet(OUT_DIR / "training_table.parquet", index=False)
    logger.info("Training table: %d rows, %d columns", len(training_table), len(training_table.columns))

    # Part J: temporal split, from the ACTUAL real coverage period.
    split_error = None
    split_boundaries = None
    try:
        split_boundaries = compute_real_split_boundaries(training_table["service_date"])
        splits = apply_real_split(training_table, split_boundaries)
        for name, split_df in splits.items():
            split_df.to_parquet(OUT_DIR / f"training_table_{name}.parquet", index=False)
        logger.info("Temporal split: %s", split_boundaries)
    except ValueError as exc:
        split_error = str(exc)
        logger.warning("Temporal split could not be constructed: %s", split_error)
    (OUT_DIR / "temporal_split.json").write_text(
        json.dumps({"boundaries": split_boundaries, "error": split_error}, indent=2, default=str), encoding="utf-8")

    # Part 7: weather coverage analysis, measured directly -- no threshold
    # decides success/failure here, only the numbers themselves.
    transit_min = str(training_table["service_date"].min()) if not training_table.empty else None
    transit_max = str(training_table["service_date"].max()) if not training_table.empty else None
    weather_coverage_report = build_weather_coverage_report(tables["weather"], training_table, transit_min, transit_max)
    (OUT_DIR / "weather_coverage_report.json").write_text(
        json.dumps(weather_coverage_report, indent=2, default=str), encoding="utf-8")
    logger.info("Weather coverage: overall=%s, total_observations=%d",
                weather_coverage_report.get("overall_coverage"), weather_coverage_report["total_weather_observations"])

    eda_report = build_eda_report(tables, cfg, training_table)
    (OUT_DIR / "eda_report.json").write_text(json.dumps(eda_report, indent=2, default=str), encoding="utf-8")

    feature_matrix = build_feature_availability_matrix(training_table, cfg)
    (OUT_DIR / "feature_availability_matrix.json").write_text(json.dumps(feature_matrix, indent=2), encoding="utf-8")

    weather_coverage = weather_coverage_report.get("overall_coverage") or 0.0
    readiness = build_model_readiness_decision(
        training_table, issues, feature_matrix, cfg, weather_coverage, split_boundaries, split_error,
    )
    (OUT_DIR / "model_readiness.json").write_text(json.dumps(readiness, indent=2, default=str), encoding="utf-8")

    logger.info("MODEL_READY = %s (%s)", readiness["model_ready"], readiness["primary_reason"])

    return {
        "tables": {k: (v.shape if hasattr(v, "shape") else None) for k, v in tables.items()},
        "validation_issues": len(issues), "validation_errors": len(errors),
        "data_quality_report": dq_report,
        "label_candidate_report": label_candidate_report,
        "label_recommendation": label_recommendation,
        "sparsity_report": sparsity_report,
        "training_table_shape": training_table.shape,
        "split_boundaries": split_boundaries, "split_error": split_error,
        "eda_report": eda_report,
        "feature_availability_matrix": feature_matrix,
        "weather_coverage": weather_coverage,
        "weather_coverage_report": weather_coverage_report,
        "weather_validation_issues": len(tables["weather_issues"]),
        "model_readiness": readiness,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true",
                         help="Re-download raw sources before ingesting (default: reuse data/raw/real/)")
    args = parser.parse_args()
    main(skip_download=not args.download)

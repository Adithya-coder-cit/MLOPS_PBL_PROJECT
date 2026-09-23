"""Generate the RouteWise DEVELOPMENT/DEMO synthetic dataset.

Produces GTFS-like static schedule data, synthetic weather, and a synthetic
historical operational log with a generated disruption label, following the
methodology documented in configs/synthetic_data.yaml and
data/raw/DATASET_CARD.md (written by this script).

This is SYNTHETIC DATA for development only — never real operational data.
Run: python -m src.ingestion.generate_demo_data
"""
from __future__ import annotations

import argparse
import logging
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.utils.disruption_rules import is_disruption

logger = logging.getLogger("routewise.ingestion.generate_demo_data")

GTFS_ROUTE_TYPE = {"tram": 0, "metro": 1, "rail": 2, "bus": 3, "ferry": 4}
DAY_PERIOD_ORDER = ["night", "off_peak", "peak"]


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def minutes_to_hhmm(total_minutes: float) -> str:
    total_minutes = int(round(total_minutes)) % (24 * 60)
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}:00"


def hhmm_to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")[:2]
    return int(h) * 60 + int(m)


def classify_day_period(minute_of_day: int, cfg: dict) -> str:
    dp = cfg["day_periods"]
    for start, end in dp["peak_windows"]:
        if hhmm_to_minutes(start) <= minute_of_day < hhmm_to_minutes(end):
            return "peak"
    night_start, night_end = hhmm_to_minutes(dp["night_window"][0]), hhmm_to_minutes(dp["night_window"][1])
    if night_start > night_end:  # wraps past midnight
        if minute_of_day >= night_start or minute_of_day < night_end:
            return "night"
    elif night_start <= minute_of_day < night_end:
        return "night"
    return "off_peak"


def generate_stops(cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    n = cfg["network"]["n_stops"]
    bbox = cfg["network"]["bbox"]
    lats = rng.uniform(bbox["lat_min"], bbox["lat_max"], n)
    lons = rng.uniform(bbox["lon_min"], bbox["lon_max"], n)

    n_zones = cfg["network"]["n_zones"]
    grid_size = int(round(math.sqrt(n_zones)))
    lat_bins = np.linspace(bbox["lat_min"], bbox["lat_max"], grid_size + 1)
    lon_bins = np.linspace(bbox["lon_min"], bbox["lon_max"], grid_size + 1)
    lat_idx = np.clip(np.digitize(lats, lat_bins) - 1, 0, grid_size - 1)
    lon_idx = np.clip(np.digitize(lons, lon_bins) - 1, 0, grid_size - 1)
    zone_ids = [f"Z{r * grid_size + c:02d}" for r, c in zip(lat_idx, lon_idx)]

    return pd.DataFrame({
        "stop_id": [f"S{i:04d}" for i in range(n)],
        "stop_name": [f"Stop {i}" for i in range(n)],
        "stop_lat": lats,
        "stop_lon": lons,
        "zone_id": zone_ids,
    })


def generate_routes(cfg: dict, rng: np.random.Generator) -> pd.DataFrame:
    n = cfg["network"]["n_routes"]
    modes, weights = zip(*cfg["mode_mix"].items())

    # Guarantee every mode with nonzero weight appears at least once — with few
    # routes and low-probability modes (e.g. ferry at 5%), a pure weighted draw
    # can skip a mode entirely, which would silently erase transport-mode
    # differences the dataset is required to represent.
    guaranteed = list(modes)
    remaining_n = n - len(guaranteed)
    assigned = guaranteed + list(rng.choice(modes, size=remaining_n, p=weights)) if remaining_n > 0 else guaranteed[:n]
    rng.shuffle(assigned)

    return pd.DataFrame({
        "route_id": [f"R{i:03d}" for i in range(n)],
        "route_short_name": [f"{m.upper()[:2]}{i}" for i, m in enumerate(assigned)],
        "route_long_name": [f"Route {i} ({m})" for i, m in enumerate(assigned)],
        "transport_mode": assigned,
        "route_type_gtfs": [GTFS_ROUTE_TYPE[m] for m in assigned],
    })


def build_route_stop_sequence(route_id: str, stops_df: pd.DataFrame, cfg: dict, rng: np.random.Generator) -> list[str]:
    lo, hi = cfg["network"]["min_stops_per_route"], cfg["network"]["max_stops_per_route"]
    k = int(rng.integers(lo, hi + 1))
    candidates = stops_df.sample(n=k, random_state=rng.integers(0, 2**31 - 1)).reset_index(drop=True)

    remaining = candidates.to_dict("records")
    path = [remaining.pop(0)]
    while remaining:
        last = path[-1]
        dists = [haversine_km(last["stop_lat"], last["stop_lon"], r["stop_lat"], r["stop_lon"]) for r in remaining]
        nxt = remaining.pop(int(np.argmin(dists)))
        path.append(nxt)
    return [p["stop_id"] for p in path]


def build_daily_departures(cfg: dict) -> list[int]:
    dp = cfg["day_periods"]
    departures = []
    minute = 0
    while minute < 24 * 60:
        period = classify_day_period(minute, cfg)
        headway = {
            "peak": dp["peak_headway_minutes"],
            "off_peak": dp["offpeak_headway_minutes"],
            "night": dp["night_headway_minutes"],
        }[period]
        departures.append(minute)
        minute += headway
    return departures


def generate_trips_and_stop_times(routes_df, stops_lookup, cfg, rng):
    trip_rows, stop_time_rows = [], []
    daily_departures = build_daily_departures(cfg)
    trip_seq = 0

    for _, route in routes_df.iterrows():
        sequence = build_route_stop_sequence(route.route_id, stops_lookup, cfg, rng)
        mode_speed = cfg["mode_params"][route.transport_mode]["avg_speed_kmh"]

        leg_minutes = []
        for a, b in zip(sequence[:-1], sequence[1:]):
            sa = stops_lookup.loc[stops_lookup.stop_id == a].iloc[0]
            sb = stops_lookup.loc[stops_lookup.stop_id == b].iloc[0]
            dist_km = haversine_km(sa.stop_lat, sa.stop_lon, sb.stop_lat, sb.stop_lon)
            leg_minutes.append(max(1.0, dist_km / mode_speed * 60.0))

        for service_id in ("weekday", "weekend"):
            for direction_id, stops_in_order in enumerate([sequence, list(reversed(sequence))]):
                legs = leg_minutes if direction_id == 0 else list(reversed(leg_minutes))
                for start_min in daily_departures:
                    trip_id = f"T{trip_seq:06d}"
                    trip_seq += 1
                    trip_rows.append({
                        "trip_id": trip_id,
                        "route_id": route.route_id,
                        "service_id": service_id,
                        "direction_id": direction_id,
                        "trip_headsign": f"To {stops_in_order[-1]}",
                    })
                    cum = start_min
                    for seq, stop_id in enumerate(stops_in_order):
                        arrival = cum
                        departure = cum if seq == len(stops_in_order) - 1 else cum + 0.5
                        stop_time_rows.append({
                            "trip_id": trip_id,
                            "stop_id": stop_id,
                            "stop_sequence": seq,
                            "scheduled_arrival": minutes_to_hhmm(arrival),
                            "scheduled_departure": minutes_to_hhmm(departure),
                            "_arrival_minute": arrival % (24 * 60),
                            "route_id": route.route_id,
                            "transport_mode": route.transport_mode,
                            "service_id": service_id,
                        })
                        if seq < len(legs):
                            cum += legs[seq]

    trips_df = pd.DataFrame(trip_rows)
    stop_times_df = pd.DataFrame(stop_time_rows)
    return trips_df, stop_times_df


def compute_transfer_dependency(stop_times_df: pd.DataFrame, cfg: dict) -> pd.Series:
    window = cfg["transfer"]["window_minutes"]
    counts = np.zeros(len(stop_times_df), dtype=int)
    for (stop_id, service_id), group in stop_times_df.groupby(["stop_id", "service_id"]):
        minutes = group["_arrival_minute"].to_numpy()
        routes = group["route_id"].to_numpy()
        for i in range(len(group)):
            close = np.abs(minutes - minutes[i]) <= window
            other_route = routes != routes[i]
            counts[group.index[i]] = int(np.sum(close & other_route))
    return pd.Series(counts, index=stop_times_df.index, name="transfer_dependency")


def generate_weather(
    cfg: dict, zones: list[str], start_date: date, n_days: int, rng: np.random.Generator
) -> pd.DataFrame:
    wcfg = cfg["weather"]
    hours = pd.date_range(start=start_date, periods=n_days * 24, freq="h")
    rows = []
    for zone_id in zones:
        wet = False
        for ts in hours:
            day_of_year = ts.timetuple().tm_yday
            temp = (
                wcfg["temperature"]["annual_mean_c"]
                + wcfg["temperature"]["seasonal_amplitude_c"] * math.cos(2 * math.pi * day_of_year / 365)
                + wcfg["temperature"]["diurnal_amplitude_c"] * math.cos(2 * math.pi * (ts.hour - 15) / 24)
                + rng.normal(0, wcfg["temperature"]["noise_std_c"])
            )
            if wet:
                wet = rng.random() < wcfg["precipitation"]["storm_continue_prob"]
            else:
                wet = rng.random() < wcfg["precipitation"]["storm_start_prob_per_hour"]
            precip = max(0.0, rng.normal(
                wcfg["precipitation"]["storm_intensity_mean_mm"],
                wcfg["precipitation"]["storm_intensity_std_mm"],
            )) if wet else 0.0
            visibility = np.clip(
                wcfg["visibility"]["clear_km"]
                - wcfg["visibility"]["precip_visibility_coefficient"] * precip
                + rng.normal(0, wcfg["visibility"]["noise_std_km"]),
                wcfg["visibility"]["min_km"], wcfg["visibility"]["clear_km"],
            )
            rows.append((zone_id, ts, precip, temp, visibility))

    obs = pd.DataFrame(rows, columns=["zone_id", "timestamp", "precipitation_mm", "temperature_c", "visibility_km"])
    obs.insert(0, "observation_id", [f"W{i:07d}" for i in range(len(obs))])
    return obs


def generate_calendar(start_date: date, n_days: int) -> pd.DataFrame:
    dates = [start_date + timedelta(days=i) for i in range(n_days)]
    service_id = ["weekend" if d.weekday() >= 5 else "weekday" for d in dates]
    return pd.DataFrame({"service_date": dates, "service_id": service_id})


def generate_historical_records(stop_times_df, stops_lookup, weather_df, calendar_df, cfg, rng) -> pd.DataFrame:
    merged = stop_times_df.merge(calendar_df, on="service_id", how="left")
    merged = merged.merge(stops_lookup[["stop_id", "zone_id"]], on="stop_id", how="left")

    merged["scheduled_time"] = merged.apply(
        lambda r: datetime.combine(r.service_date, datetime.min.time()) + timedelta(minutes=r._arrival_minute), axis=1
    )
    merged["day_period"] = merged["_arrival_minute"].apply(lambda m: classify_day_period(int(m), cfg))

    weather_df = weather_df.copy()
    weather_df["hour_key"] = weather_df["timestamp"].dt.floor("h")
    merged["hour_key"] = merged["scheduled_time"].dt.floor("h")
    merged = merged.merge(
        weather_df[["zone_id", "hour_key", "precipitation_mm", "temperature_c", "visibility_km"]],
        on=["zone_id", "hour_key"], how="left",
    )

    n = len(merged)
    peak_effect = merged["day_period"].map({"peak": 1.5, "off_peak": 0.0, "night": -0.3}).to_numpy()
    thresholds, cancel_probs, sensitivities, base_mean, base_std = {}, {}, {}, {}, {}
    for mode, p in cfg["mode_params"].items():
        thresholds[mode] = p["disruption_threshold_minutes"]
        cancel_probs[mode] = p["cancellation_prob"]
        sensitivities[mode] = p["weather_sensitivity"]
        base_mean[mode] = p["base_delay_mean"]
        base_std[mode] = p["base_delay_std"]

    modes = merged["transport_mode"].to_numpy()
    base_delay = rng.normal(
        [base_mean[m] for m in modes], [base_std[m] for m in modes]
    )
    weather_effect = np.array([sensitivities[m] for m in modes]) * (
        merged["precipitation_mm"].fillna(0).to_numpy() * 0.4
        + np.maximum(0, 10 - merged["visibility_km"].fillna(10).to_numpy()) * 0.3
    )
    transfer_effect = merged["transfer_dependency"].to_numpy() * cfg["transfer"]["congestion_delay_per_transfer"]
    noise = rng.normal(0, 1.0, n)

    delay_minutes = base_delay + peak_effect + weather_effect + transfer_effect + noise

    cancel_p = np.clip(
        np.array([cancel_probs[m] for m in modes]) * (1 + weather_effect / 5), 0, 0.2
    )
    cancelled = rng.random(n) < cancel_p

    flip = rng.random(n) < cfg["disruption_noise"]["flip_probability"]
    disruption_flag = np.array([
        is_disruption(d, c, m, thresholds) for d, c, m in zip(delay_minutes, cancelled, modes)
    ])
    disruption_flag = np.where(flip, ~disruption_flag, disruption_flag)

    actual_time = merged["scheduled_time"] + pd.to_timedelta(delay_minutes, unit="m")

    records = pd.DataFrame({
        "record_id": [f"H{i:08d}" for i in range(n)],
        "trip_id": merged["trip_id"],
        "stop_id": merged["stop_id"],
        "service_date": merged["service_date"],
        "scheduled_time": merged["scheduled_time"],
        "actual_time": actual_time,
        "delay_minutes": delay_minutes.round(2),
        "cancelled": cancelled,
        "disruption_flag": disruption_flag.astype(int),
        "transport_mode": modes,
    })
    return records


def generate_fares(routes_df: pd.DataFrame, route_stop_counts: dict, cfg: dict) -> pd.DataFrame:
    rows = []
    for _, route in routes_df.iterrows():
        p = cfg["mode_params"][route.transport_mode]
        n_stops = route_stop_counts[route.route_id]
        fare = p["fare_base"] + p["fare_per_stop"] * max(0, n_stops - 1)
        rows.append({"route_id": route.route_id, "fare_amount": round(fare, 2), "currency": "SYNTHETIC_UNITS"})
    return pd.DataFrame(rows)


def write_dataset_card(out_dir: Path, cfg: dict, stats: dict) -> None:
    lines = [
        "# RouteWise Dataset Card",
        "",
        "**DEVELOPMENT/DEMO DATASET — SYNTHETIC, NOT REAL OPERATIONAL DATA.**",
        "",
        f"- Dataset version: {cfg['dataset_version']}",
        f"- Generation seed: {cfg['seed']}",
        f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
        "- Methodology: configs/synthetic_data.yaml + src/ingestion/generate_demo_data.py",
        "",
        "## Row counts",
        "",
    ]
    for k, v in stats["row_counts"].items():
        lines.append(f"- {k}: {v:,}")
    lines += ["", "## Label balance (disruption_flag)", ""]
    for k, v in stats["label_balance"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Per-mode disruption rate", ""]
    for k, v in stats["mode_disruption_rate"].items():
        lines.append(f"- {k}: {v:.3f}")
    lines += [
        "",
        "## Known limitations",
        "- Synthetic generative model; does not reflect any real transit system.",
        "- No real GTFS calendar exceptions (holidays) — weekday/weekend service_id only.",
        "- Weather is a simulated latent process, not sourced from any real meteorological model.",
        "- fares.csv values are in SYNTHETIC_UNITS, not real currency.",
        "",
    ]
    (out_dir / "DATASET_CARD.md").write_text("\n".join(lines), encoding="utf-8")


def main(config_path: str = "configs/synthetic_data.yaml") -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    cfg = load_config(config_path)
    rng = np.random.default_rng(cfg["seed"])

    gtfs_dir = Path("data/raw/gtfs")
    ops_dir = Path("data/raw/operational")
    weather_dir = Path("data/raw/weather")
    for d in (gtfs_dir, ops_dir, weather_dir):
        d.mkdir(parents=True, exist_ok=True)

    logger.info("Generating stops and routes")
    stops_df = generate_stops(cfg, rng)
    routes_df = generate_routes(cfg, rng)

    logger.info("Generating trips and stop_times")
    trips_df, stop_times_df = generate_trips_and_stop_times(routes_df, stops_df, cfg, rng)

    logger.info("Computing transfer dependency")
    stop_times_df["transfer_dependency"] = compute_transfer_dependency(stop_times_df, cfg)

    route_stop_counts = stop_times_df.groupby("route_id")["stop_id"].apply(
        lambda s: stop_times_df.loc[s.index, "stop_sequence"].max() + 1
    ).to_dict()

    start_date = datetime.strptime(cfg["calendar"]["service_date_start"], "%Y-%m-%d").date()
    n_days = cfg["calendar"]["service_date_days"]

    logger.info("Generating calendar (%d days from %s)", n_days, start_date)
    calendar_df = generate_calendar(start_date, n_days)

    logger.info("Generating weather (%d zones x %d days)", cfg["network"]["n_zones"], n_days)
    zones = sorted(stops_df["zone_id"].unique())
    weather_df = generate_weather(cfg, zones, start_date, n_days, rng)

    logger.info("Expanding historical operational records over the calendar")
    historical_df = generate_historical_records(stop_times_df, stops_df, weather_df, calendar_df, cfg, rng)

    logger.info("Generating fares")
    fares_df = generate_fares(routes_df, route_stop_counts, cfg)

    stop_times_out = stop_times_df[["trip_id", "stop_id", "stop_sequence", "scheduled_arrival", "scheduled_departure"]]

    stops_df.to_csv(gtfs_dir / "stops.csv", index=False)
    routes_df.to_csv(gtfs_dir / "routes.csv", index=False)
    trips_df.to_csv(gtfs_dir / "trips.csv", index=False)
    stop_times_out.to_csv(gtfs_dir / "stop_times.csv", index=False)
    fares_df.to_csv(gtfs_dir / "fares.csv", index=False)
    historical_df.to_csv(ops_dir / "historical_operational_records.csv", index=False)
    weather_df.drop(columns=["hour_key"], errors="ignore").to_csv(weather_dir / "weather_observations.csv", index=False)

    stats = {
        "row_counts": {
            "stops": len(stops_df), "routes": len(routes_df), "trips": len(trips_df),
            "stop_times": len(stop_times_out), "fares": len(fares_df),
            "historical_operational_records": len(historical_df), "weather_observations": len(weather_df),
        },
        "label_balance": {
            "disruption_rate": round(float(historical_df["disruption_flag"].mean()), 4),
            "cancelled_rate": round(float(historical_df["cancelled"].mean()), 4),
        },
        "mode_disruption_rate": historical_df.groupby("transport_mode")["disruption_flag"].mean().to_dict(),
    }
    write_dataset_card(Path("data/raw"), cfg, stats)

    logger.info("Done. Row counts: %s", stats["row_counts"])
    logger.info("Overall disruption rate: %.4f", stats["label_balance"]["disruption_rate"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/synthetic_data.yaml")
    args = parser.parse_args()
    main(args.config)

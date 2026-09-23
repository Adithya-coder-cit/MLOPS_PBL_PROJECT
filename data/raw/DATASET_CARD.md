# RouteWise Dataset Card

**DEVELOPMENT/DEMO DATASET — SYNTHETIC, NOT REAL OPERATIONAL DATA.**

- Dataset version: 0.1.0
- Generation seed: 42
- Generated at: 2026-09-23T21:20:38
- Methodology: configs/synthetic_data.yaml + src/ingestion/generate_demo_data.py

## Row counts

- stops: 70
- routes: 18
- trips: 864
- stop_times: 6,480
- fares: 18
- historical_operational_records: 388,800
- weather_observations: 46,080

## Label balance (disruption_flag)

- disruption_rate: 0.2675
- cancelled_rate: 0.0039

## Per-mode disruption rate

- bus: 0.278
- ferry: 0.128
- metro: 0.265
- rail: 0.344
- tram: 0.267

## Known limitations
- Synthetic generative model; does not reflect any real transit system.
- No real GTFS calendar exceptions (holidays) — weekday/weekend service_id only.
- Weather is a simulated latent process, not sourced from any real meteorological model.
- fares.csv values are in SYNTHETIC_UNITS, not real currency.

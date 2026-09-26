# Stage 11 Discovery Report: Migrating RouteWise from Synthetic to Real Transportation Data

**Status: DISCOVERY ONLY. No implementation code was written for this stage.**
Every finding below is grounded in the actual current repository (file paths and
line-level behavior verified by reading the code, not assumed) or in
externally verified sources (cited where used). Nothing about a real feed's
exact fields, update cadence, or license terms is asserted without a source.

---

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [Current synthetic dependencies (repository audit + dependency map)](#2-current-synthetic-dependencies)
3. [GTFS field mapping](#3-gtfs-field-mapping)
4. [Proposed real data source](#4-proposed-real-data-source)
5. [Weather integration](#5-weather-integration)
6. [Historical delay data availability](#6-historical-delay-data-availability)
7. [Canonical data contract](#7-canonical-data-contract)
8. [Ingestion architecture (dual-source)](#8-ingestion-architecture-dual-source)
9. [Data quality risks and validation requirements](#9-data-quality-risks-and-validation-requirements)
10. [Feature availability matrix](#10-feature-availability-matrix)
11. [Routing/graph changes required](#11-routinggraph-changes-required)
12. [Model implications](#12-model-implications)
13. [Monitoring implications](#13-monitoring-implications)
14. [Licensing and data-use considerations](#14-licensing-and-data-use-considerations)
15. [Implementation plan](#15-implementation-plan)

---

## 1. Executive summary

RouteWise's Stage 1–10 architecture (validation → preprocessing → feature
engineering → training → MLflow → routing → API → dashboard → monitoring →
retraining) is **largely data-source-agnostic already** — it was built to
consume tables shaped like GTFS + a weather table + a historical-events table,
not literally the synthetic generator's output. The migration is real but
bounded. Three findings dominate the plan:

1. **The synthetic generator is the only source of ground-truth labels.**
   `historical_operational_records` (scheduled time, actual time, delay,
   cancelled, `disruption_flag`) is *invented* by
   `src/ingestion/generate_demo_data.py` — no real GTFS feed contains this.
   A real deployment needs a genuinely separate historical-performance data
   source (GTFS-Realtime archives, or an agency's own performance API) or the
   model must run in a **labels-unavailable / limited mode** (Section 6,
   Section 12).
2. **One real architectural assumption must be redesigned, not just
   reconfigured**: `src/routing/graph_builder.py::_select_representative_trips`
   explicitly depends on the synthetic generator's guarantee that every trip
   of a given `(route_id, direction_id)` shares an identical stop sequence and
   leg times. Real GTFS feeds have route variants/branches — this assumption
   is false for real data and would silently drop real stop patterns
   (Section 11).
3. **Everything else is a schema/config problem, not a rewrite.** The
   feature manifest, preprocessing pipeline, temporal features, transfer
   dependency, chronological split, DVC tracking, the promotion gate, and the
   monitoring/retraining pipeline all operate on column names and generic
   statistical assumptions, not on synthetic-specific structure. They need a
   **canonical contract adapter** in front of them, not modification.

The recommended concrete first real source is the **MBTA (Massachusetts Bay
Transportation Authority, Boston)** open data program: it publishes standard
GTFS static + GTFS-Realtime, covers 4 of RouteWise's 5 existing transport
modes natively (subway/metro, bus, commuter rail, ferry — light rail/Green
Line can stand in for "tram"), and — unusually for an open feed — publishes a
**dedicated historical performance dataset with scheduled-vs-actual times per
route/direction/stop/trip**, which is exactly the shape RouteWise's
`historical_operational_records` needs. See Section 4 for full detail and
citations, and Section 14 for why this still requires a license review before
any ingestion.

---

## 2. Current synthetic dependencies

### 2.1 Stage 2 synthetic data contract

`configs/synthetic_data.yaml` is the single generation-methodology file
(`seed`, `dataset_version`, `network` size/bbox, `mode_mix`, per-mode
`mode_params` — speed, delay distribution, disruption threshold, cancellation
probability, weather sensitivity, fare scale — `calendar`, `day_periods`,
`transfer`, `weather` generative parameters, `disruption_noise`).
`src/ingestion/generate_demo_data.py` reads it and **fabricates every raw
table from scratch**: stops (random lat/lon in a fixed bbox), routes (mode
assigned by weighted draw), trips/stop_times (one fixed schedule template per
route+direction, walked nearest-neighbor for stop order), weather
(latent seasonal+diurnal+storm process per synthetic "zone"), and — critically
— `historical_operational_records`, where `delay_minutes` is drawn from a
parametric model (mode base delay + peak effect + weather effect + transfer
congestion + noise) and `disruption_flag` is a **rule computed from that same
synthetic delay**, with 3% label noise injected on purpose. This table is the
project's only source of "ground truth" and does not correspond to anything a
real GTFS static feed provides.

### 2.2 Stage 3 canonical/intermediate schemas

`src/validation/schemas.py` declares `TableSchema` objects for `stops`,
`routes`, `trips`, `stop_times`, `fares`, `historical_operational_records`,
`weather_observations`. Two things matter for the migration:

- `VALID_TRANSPORT_MODES = {"bus", "tram", "metro", "rail", "ferry"}` and
  `historical_operational_records.categorical["transport_mode"]` both close
  over exactly the synthetic `mode_mix` keys. A real feed's `route_type`
  values (GTFS numeric codes) map cleanly onto this set (Section 3) but the
  set itself needs to stay authoritative and shared, not re-declared per
  source.
- `trips.categorical["service_id"] = {"weekday", "weekend"}` is a **hard
  synthetic assumption** — real GTFS `service_id` values are agency-defined
  arbitrary strings (there can be dozens: school-day, Saturday, Sunday,
  summer, snow-emergency, etc.), governed by `calendar.txt`/
  `calendar_dates.txt`, which this project currently has **no schema for at
  all** (see 2.4).
- Numeric ranges (`delay_minutes: (-60, 300)`, `precipitation_mm: (0, 150)`,
  etc.) are explicitly documented in the file as "loose, source-agnostic
  sanity bounds (hold for any real city too)" — these were already written to
  survive this migration.

### 2.3 `feature_manifest.json` (`src/features/manifest.py`)

Already documents most feature sources as real-world concepts, not synthetic
ones — e.g. `precipitation_mm.source = "weather_observations (Weather API in
production)"`. This is a strong signal Stage 3 was written with this
migration in mind. The one field needing a new home:
`disruption_flag.source = "derived from historical_operational_records
(src/utils/disruption_rules.py)"` — the rule module itself is source-agnostic
(Section 2.6), but its **threshold config currently lives inside
`configs/synthetic_data.yaml`**, a file this migration should stop treating as
authoritative for anything except the demo generator.

### 2.4 Preprocessing pipeline (`src/preprocessing/clean.py`, `pipeline.py`)

`join_weather_asof` does a backward `merge_asof` keyed on `zone_id` +
timestamp with a bounded tolerance — this is source-agnostic *as long as*
real data provides a `zone_id`-equivalent join key between stops and weather
observations (Section 5 covers how). `join_route_metadata` assumes
`transport_mode` is already denormalized onto each historical record
("mirroring how a real GTFS-RT feed usually carries it" per its own
docstring) — real GTFS-RT `TripUpdate`s typically carry `trip_id` (and
sometimes `route_id`) but not always mode directly; the real adapter should
derive `transport_mode` from `routes.route_type` via the join that's already
partially there (`route_type_gtfs`), not assume it pre-populated.
`src/preprocessing/pipeline.py`'s `NUMERIC_FEATURES`/`CATEGORICAL_FEATURES`
column lists are pure names — no synthetic dependency.

**Gap**: there is no `calendar`/`calendar_dates` table anywhere in the raw
data, the loader (`src/ingestion/load_raw.py`), or the schema module. The
synthetic generator sidesteps this by generating a full per-date calendar
in-memory and never persisting it. A real ingestion path needs an explicit
service-calendar contract (Section 7).

### 2.5 Historical feature calculations (`src/features/historical.py`)

`compute_daily_route_stats` / `add_backward_looking_route_features` operate
purely on `route_id`, `service_date`, `delay_minutes`, `disruption_flag` —
fully source-agnostic, **but entirely dependent on real historical
delay/disruption records existing** (Section 6). If they don't,
`historical_delay_minutes`, `rolling_7d_delay_minutes`, and
`historical_reliability` are undefined for real data, not just degraded.

### 2.6 Disruption labeling rule (`src/utils/disruption_rules.py`)

`is_disruption(delay_minutes, cancelled, transport_mode, thresholds)` is
already written to be reused by "the real-data ingestion path" per its own
docstring — genuinely source-agnostic logic. Its only coupling problem:
`load_mode_thresholds()` hardcodes `configs/synthetic_data.yaml` as the
config path. This needs to move to a source-neutral config location so a
real deployment isn't forced to keep a file named `synthetic_data.yaml`
around as load-bearing configuration.

### 2.7 Network topology / transfer dependency (`src/utils/network_topology.py`, `src/features/network.py`)

`compute_transfer_dependency` is purely structural (stop_id, service_id,
route_id, scheduled arrival minute) — no synthetic dependency, and it's
already the module the routing graph builder reuses. The implementation is
O(n²) within each `(stop_id, service_id)` group; the synthetic dataset's
per-stop group sizes are small, but a real feed's busiest stops/service
patterns could have hundreds of scheduled events per day, worth flagging for
Section 11.

### 2.8 Routing graph assumptions (`src/routing/graph_builder.py`)

This is the one place with a **real, false-for-real-data architectural
assumption**, stated explicitly in its own module docstring: *"Stage 2's
generator uses a fixed schedule template per route+direction (identical stop
sequence and inter-stop travel times across all departures of that
route+direction), so a single REPRESENTATIVE trip_id per (route_id,
direction_id) fully characterizes the leg — confirmed against
src/ingestion/generate_demo_data.py."* `_select_representative_trips` then
literally picks one trip per `(route_id, direction_id)` and builds the whole
edge set from it. Real transit routes commonly have multiple stop patterns
(branches, short-turns, express variants) even within one
`(route_id, direction_id)`. See Section 11 for the required redesign.

No hardcoded stop/route counts (the "70 stops / 18 routes" figures) were
found anywhere in `src/routing/` or `src/decision_engine/` — node/edge
construction iterates over whatever `stops`/`routes`/`trips` contain. The
only synthetic-scale-specific value found is a **config** value:
`params.yaml routing.normalization.fixed_bounds.cost: {min: 0, max: 100}`,
explicitly commented `# SYNTHETIC_UNITS, matches fares.csv scale` — a config
edit, not a code change, once real fares are in a real currency/scale.

### 2.9 Model input schema (`training/prepare_inputs.py`, `src/preprocessing/pipeline.py`)

The model is fed exactly 12 columns: `NUMERIC_FEATURES` (`precipitation_mm`,
`temperature_c`, `visibility_km`, `historical_delay_minutes`,
`rolling_7d_delay_minutes`, `historical_reliability`, `transfer_dependency`,
`hour`, `day_of_week`) + `CATEGORICAL_FEATURES` (`transport_mode`,
`day_period`, `time_of_day_bucket`). Note: `feature_manifest.json` lists 13
"feature"-usage columns (it also includes `is_weekend`), but
`prepare_inputs.ALL_FEATURES` does **not** include `is_weekend` — the model
never actually consumes it, though Stage 9 monitoring currently watches it as
a "feature" since it derives its monitored-feature list from the manifest.
This is a pre-existing minor inconsistency, not something this migration
introduces, but worth resolving in the same pass (either feed it to the
model or mark it `model_usage: "derived, unused"` in the manifest).

### 2.10 Monitoring reference-data assumptions (`src/monitoring/`)

`src/monitoring/reference.py` hardcodes the split-file map
(`train.parquet`/`val.parquet`/`test.parquet`) and reads
`dataset_metadata.json`'s `dvc_raw_hashes` keys as exactly `gtfs`,
`operational`, `weather` (matching today's 3 raw directories 1:1). This is
architecture-agnostic to synthetic-vs-real **content**, but is coupled to
today's **directory layout**. If real ingestion adds new raw sources (e.g. a
separate GTFS-Realtime archive directory, a separate calendar directory),
`build_reference_metadata`'s hash-collection needs to generalize from 3 fixed
keys to an iterable list (Section 13).

### 2.11 DVC configuration

`.dvc/config` has **no remote configured** — everything is local-cache-only
today (confirmed: `cat .dvc/config` is empty). `data/raw/{gtfs,operational,
weather}` are each tracked as a single whole-directory hash via `dvc add`.
This layer is fully agnostic to what's inside those directories — swapping
synthetic CSVs for real ones and re-running `dvc add` works today with zero
DVC-level changes. The real gap is scale: real historical/GTFS-Realtime
archives can run into GBs, and local-cache-only DVC does not scale to that
without an actual remote (S3/GCS/Azure Blob) — flagged as a real
infrastructure requirement, not a code change (Section 15).

### 2.12 API assumptions about stops/routes/modes

`api/startup.py` loads stops generically off whatever `load_raw_tables()`
returns; `api/routers/stops.py` / `api/schemas/stops.py` expose
`stop_id, stop_name, lat, lon, zone_id` with no synthetic-specific logic.
No code-level dependency on synthetic data was found in `api/`. The one
non-code dependency is the dashboard's demo-data banner and the README's
DEVELOPMENT/DEMO language, which is a labeling/documentation obligation, not
an architecture change (Section 8 covers how to keep both sources honestly
labeled).

### 2.13 Dependency map

```
configs/synthetic_data.yaml ──────────────┐
                                           │ generation methodology only
src/ingestion/generate_demo_data.py ──────┤
   (fabricates ALL raw tables,            │
    INCLUDING ground-truth labels)        │
                                           ▼
data/raw/{gtfs,operational,weather}/*.csv  ← canonical raw-table SHAPE
                                           │ (this shape is what's reusable)
                                           ▼
src/ingestion/load_raw.py  ───────────────┤ format-agnostic loader (5 CSVs)
                                           │
src/validation/schemas.py ────────────────┤ ⚠ service_id={"weekday","weekend"}
                                           │   is synthetic-only; everything
                                           │   else is source-agnostic
                                           ▼
src/preprocessing/clean.py ───────────────┤ zone_id-keyed weather join;
                                           │   transport_mode assumed present
                                           ▼
src/features/{temporal,network,historical}.py
                                           │ historical.py needs REAL delay data;
                                           │   temporal/network are source-agnostic
                                           ▼
src/features/build_dataset.py ────────────┤ orchestrator; column-name driven
                                           ▼
data/processed/{train,val,test}.parquet ──┤ canonical processed shape
  + feature_manifest.json                 │ (already source-agnostic)
  + dataset_metadata.json                 │
                                           ▼
training/*.py, inference/*.py ────────────┤ fully source-agnostic (column names only)
                                           ▼
src/routing/graph_builder.py ─────────────┤ ⚠ ONE real architectural
                                           │   assumption: representative-trip
                                           │   simplification (Section 11)
                                           ▼
api/*, dashboard/* ────────────────────────  source-agnostic; labeling-only concern
src/monitoring/* ──────────────────────────  source-agnostic; directory-layout coupling
training/retrain.py, rollback.py ──────────  fully source-agnostic
```

---

## 3. GTFS field mapping

RouteWise's raw tables already resemble GTFS but are **not** literal GTFS
(different filenames, a subset of real GTFS columns, no `calendar.txt`, and a
completely custom `historical_operational_records`/`fares.csv`). The mapping
below covers the required files plus the optional ones the brief asks about.
Field names/types follow the [GTFS Static Reference](https://gtfs.org/schedule/reference/).

### `stops.txt` (required)

| GTFS field | RouteWise field | Current synthetic equivalent | Transformation required |
|---|---|---|---|
| `stop_id` | `stop_id` | `stop_id` (e.g. `S0040`) | passthrough |
| `stop_name` | `stop_name` | `stop_name` (e.g. `"Stop 40"`) | passthrough |
| `stop_lat` | `lat` / `stop_lat` | `stop_lat` | passthrough |
| `stop_lon` | `lon` / `stop_lon` | `stop_lon` | passthrough |
| *(none — synthetic-only)* | `zone_id` | `zone_id` (synthetic weather grid cell) | **must be derived**, not sourced — real GTFS has no `zone_id` field with this meaning (a `zone_id` column exists in old fare-zone GTFS but means something different). Needs a real geospatial join: assign each stop to a weather-grid cell from whichever weather API/provider is chosen (Section 5). |
| `parent_station`, `location_type` | *(unused)* | *(absent)* | optional: needed only if modeling station-vs-platform hierarchy; not required for RouteWise's current node-per-stop graph model. |
| `wheelchair_boarding` | *(unused)* | *(absent)* | not currently modeled; candidate future accessibility feature. |

### `routes.txt` (required)

| GTFS field | RouteWise field | Current synthetic equivalent | Transformation required |
|---|---|---|---|
| `route_id` | `route_id` | `route_id` | passthrough |
| `route_short_name` | `route_short_name` | `route_short_name` | passthrough |
| `route_long_name` | `route_long_name` | `route_long_name` | passthrough |
| `route_type` | `route_type_gtfs` → `transport_mode` | `route_type_gtfs` (already using real GTFS codes: 0=tram,1=metro/subway,2=rail,3=bus,4=ferry) | The synthetic generator **already encodes real GTFS `route_type` numeric codes** (`GTFS_ROUTE_TYPE` dict in `generate_demo_data.py` matches the spec exactly) — the mapping `route_type → transport_mode` (0→tram, 1→metro, 2→rail, 3→bus, 4→ferry) already exists conceptually and just needs to become the real ingestion adapter's canonical lookup table instead of a generation-time label. |

### `trips.txt` (required)

| GTFS field | RouteWise field | Current synthetic equivalent | Transformation required |
|---|---|---|---|
| `trip_id` | `trip_id` | `trip_id` | passthrough |
| `route_id` | `route_id` | `route_id` | passthrough |
| `service_id` | `service_id` | `service_id` (`"weekday"`/`"weekend"` only) | **schema change required** — must accept arbitrary agency-defined service IDs, resolved via a new `calendar`/`calendar_dates` contract (Section 7), not a 2-value enum. |
| `direction_id` | `direction_id` | `direction_id` (0/1) | passthrough, but real feeds sometimes omit it — see Section 9. |
| `trip_headsign` | `trip_headsign` | `trip_headsign` | passthrough |
| `shape_id` | *(unused directly)* | *(absent)* | not required for the current graph model (edges are stop-to-stop, not polyline-based); would matter if RouteWise ever renders route paths on a map. |
| `block_id`, `wheelchair_accessible`, `bikes_allowed` | *(unused)* | *(absent)* | not currently modeled. |

### `stop_times.txt` (required)

| GTFS field | RouteWise field | Current synthetic equivalent | Transformation required |
|---|---|---|---|
| `trip_id` | `trip_id` | `trip_id` | passthrough |
| `stop_id` | `stop_id` | `stop_id` | passthrough |
| `stop_sequence` | `stop_sequence` | `stop_sequence` | passthrough |
| `arrival_time` | `scheduled_arrival` | `scheduled_arrival` (`HH:MM:SS`, wrapped modulo 24h) | **bug-equivalent fix required**: real GTFS `arrival_time`/`departure_time` use an extended clock (hours can exceed 23, e.g. `25:30:00`) specifically to represent trips that start one service-day and run past midnight without changing `service_date`. The synthetic generator's `minutes_to_hhmm()` wraps with `% (24*60)`, which is fine for synthetic data (no trip actually spans midnight in a way that matters) but is **not** GTFS-correct and must be replaced with real extended-time parsing for real data (also flagged in Section 9, "midnight-crossing trips"). |
| `departure_time` | `scheduled_departure` | `scheduled_departure` | same as above |
| `pickup_type`, `drop_off_type` | *(unused)* | *(absent)* | worth ingesting: a non-default value (skip stop, must phone ahead, etc.) affects whether a stop is a valid boarding/alighting point for routing — currently every stop is assumed always boardable. |
| `shape_dist_traveled`, `timepoint` | *(unused)* | *(absent)* | not required for the current model. |

### `calendar.txt` (conditionally required by GTFS; **not currently modeled at all**)

| GTFS field | RouteWise field | Current synthetic equivalent | Transformation required |
|---|---|---|---|
| `service_id` | *(none yet)* | implicit, 2 values only | **new contract needed** (Section 7's `service_calendar` schema). |
| `monday`...`sunday` (booleans) | *(none yet)* | implicit (weekday/weekend split baked into generation) | must be expanded into a per-`service_date` lookup the same way the synthetic generator's in-memory `calendar_df` did — but the real version must live as its own persisted, validated table, not a throwaway in-memory frame. |
| `start_date`, `end_date` | *(none yet)* | implicit (`calendar.service_date_start` + `service_date_days` in `synthetic_data.yaml`) | must come from the real feed. |

### `calendar_dates.txt` (optional in GTFS; commonly used for holiday exceptions)

| GTFS field | RouteWise field | Current synthetic equivalent | Transformation required |
|---|---|---|---|
| `service_id`, `date`, `exception_type` (1=added, 2=removed) | *(none)* | **absent — no holiday/exception modeling exists anywhere in the current codebase** | new contract needed. A real feed may or may not publish this file (GTFS allows a feed to define service entirely via `calendar_dates.txt` with no `calendar.txt` at all, or vice versa, or both) — the ingestion adapter must handle both patterns, not assume `calendar.txt` always exists. |

### Optional files — recommendation

| File | Useful for RouteWise? | Reasoning |
|---|---|---|
| `transfers.txt` | **Useful, not required initially.** | RouteWise already *derives* a `transfer_dependency` feature structurally from `stop_times`+`trips` (`src/utils/network_topology.py`) rather than reading it from a raw file — this is actually more general than `transfers.txt` (which only encodes agency-declared transfer *rules*, e.g. minimum transfer time between specific stop pairs). `transfers.txt`, if present, would upgrade `transfer_penalty` in `params.yaml` from a single engineering estimate (5 min / 2 cost units) to per-pair real minimum transfer times — a genuine improvement, but additive, not blocking. |
| `fare_attributes.txt` + `fare_rules.txt` | **Useful, not required initially; often absent.** | Maps loosely onto `fares.csv`'s `route_id → fare_amount` if present, but many real GTFS feeds omit fare data entirely (unlike this project's synthetic data, which always includes it), and modern feeds increasingly use GTFS-Fares V2 (`fare_products.txt`, `fare_leg_rules.txt`) instead of the legacy files. **Do not assume any fare file exists** — degrade to `cost: null`/unavailable per candidate route rather than fabricating one, and document that cost-based scoring is unavailable until a fare source is confirmed for the chosen feed. |
| `shapes.txt` | **Not required.** | RouteWise's routing model is stop-to-stop graph edges, not polyline geometry — `shapes.txt` would only matter for map rendering, which is out of scope for the current dashboard. |

---

## 4. Proposed real data source

### Recommendation: MBTA (Massachusetts Bay Transportation Authority, Boston, USA)

| Attribute | Detail |
|---|---|
| Provider | Massachusetts Bay Transportation Authority (MassDOT) |
| Geographic coverage | Greater Boston metro area |
| Feed format | Standard GTFS static (ZIP, ~10–30 MB) **and** GTFS-Realtime (TripUpdates, VehiclePositions, ServiceAlerts, protobuf) **and** a REST "V3 API" wrapper |
| Update frequency | GTFS static: "updated several times per month, subject to change at any time" — the developer docs explicitly recommend checking daily and using the `Last-Modified` HTTP header rather than assuming a fixed cadence. GTFS-Realtime: updated continuously ("several times per day" at minimum). |
| Licensing/usage terms | Governed by the **MassDOT Developers License Agreement** (a PDF the developer portal links to) — **must be read and accepted before any ingestion**; not yet reviewed as part of this discovery (see Section 14). |
| Modes covered | Subway (Red/Orange/Blue Lines → `metro`), Green Line light rail (→ candidate mapping to `tram`), bus (→ `bus`), commuter rail (→ `rail`), ferry/"MBTA Boat" (→ `ferry`) — **4 of RouteWise's 5 existing modes map natively, and Green Line light rail is a reasonable (not perfect) stand-in for the 5th (`tram`)**. One documented exclusion: Massport airport shuttles are not in the GTFS feed as of Feb 2019 (alternative data available via Trillium Transit, not evaluated here). |
| Historical delay data | **Exists, and is unusually good for an open feed.** The MBTA publishes a dedicated "LAMP" performance dataset (`performancedata.mbta.com`) plus an open-source system (`github.com/mbta/transit-performance`, MIT-licensed) that explicitly computes **scheduled vs. predicted vs. actual arrival/departure events, organized by route, direction, stop, trip, and vehicle** — this is structurally very close to what `historical_operational_records` needs. Coverage note: subway/light rail/commuter rail on-time performance is confirmed; bus coverage is described as "select bus routes," not all of them — needs verification per-route before relying on it for the `bus` mode specifically. Data is offered as Parquet/SQLite/CSV, partitioned by service date, with GTFS archives extending back to 2009 (per the LAMP public-data page). |
| Limitations | (1) License terms not yet reviewed (Section 14) — **this alone blocks ingestion until resolved**, regardless of technical fit. (2) Historical performance API access may require developer registration separate from the open GTFS download. (3) Bus on-time performance coverage is only partial per the source's own description. (4) No confirmed weather-per-zone equivalent — a separate weather API is still required regardless of transit-data source (Section 5). |

Two fallback candidates, not deep-researched to the same level, worth
naming for completeness: **SEPTA (Philadelphia)** — bus, subway/metro,
trolley (a literal "tram" match), and regional rail, another strong
5-mode-ish fit — and **NYC MTA / WMATA**, both very well-documented but
missing a ferry mode and (for MTA) an unusually large network that would
stress-test scale (Section 11) sooner than may be wanted for a first
integration.

**Recommendation**: proceed with MBTA as the Stage 12 target *only after* a
named person reads the MassDOT Developers License Agreement in full and
confirms the intended use (a development/research MLOps demo, potentially
public on GitHub) is permitted — see Section 14. Do not begin ingestion
before that review.

Sources: [MBTA Developers portal](https://www.mbta.com/developers),
[MBTA GTFS page](https://www.mbta.com/developers/gtfs),
[MBTA GTFS-Realtime page](https://www.mbta.com/developers/gtfs-realtime),
[MBTA LAMP public performance data](https://performancedata.mbta.com/),
[mbta/transit-performance (GitHub)](https://github.com/mbta/transit-performance),
[Mass.gov MBTA/transit developer data list](https://www.mass.gov/lists/mbta-and-transit-data-for-developers).

---

## 5. Weather integration

### Current synthetic contract

`configs/synthetic_data.yaml`'s `weather` block generates, per synthetic
`zone_id` and per hour: `precipitation_mm` (storm-episode Markov process),
`temperature_c` (seasonal + diurnal + noise), `visibility_km` (derived from
precipitation + noise). `weather_observations` rows are
`(observation_id, zone_id, timestamp, precipitation_mm, temperature_c,
visibility_km)`. The join into the feature table
(`src/preprocessing/clean.py::join_weather_asof`) is a backward `merge_asof`
on `(zone_id, timestamp)` with a 2-hour tolerance — direction is enforced
`"backward"` specifically to prevent future-weather leakage, and is already
proven by a dedicated leakage test (`tests/test_feature_leakage.py`).

### Required fields for a real adapter

| Field | Timestamp resolution | Geographic requirement |
|---|---|---|
| `precipitation_mm` | Hourly (matches current `weather_observations` grain and the asof-join tolerance) | Per-zone — needs a real lat/lon → weather-grid-cell assignment |
| `temperature_c` | Hourly | same |
| `visibility_km` | Hourly | same |

### Geographic requirement — the real gap

The synthetic `zone_id` is an artifact of a fixed synthetic bounding box
split into an N×N grid. For real data, `zone_id` must become a **derived**
field: each real stop's `(stop_lat, stop_lon)` needs to be mapped to whatever
spatial unit the chosen weather API uses (a grid cell, a station ID, or a
lat/lon rounded to the provider's resolution). This is new adapter logic, not
present anywhere today.

### Candidate weather API adapter

Not selected as part of this discovery (out of scope per the brief — "do not
hardcode an API key"). Whichever provider is chosen (e.g. a
historical-weather API with an hourly-observations endpoint), the adapter
must:

- Read the API key from environment configuration only — `api/config.py`'s
  existing `Settings` (pydantic-settings, `.env`-driven) pattern is the
  established convention (`.env.example` documents every current key; a new
  `WEATHER_API_KEY`/`WEATHER_API_URL` pair is **already present as a
  placeholder** in `.env.example`, unused today — confirms this was
  anticipated).
- Produce output in exactly the `weather_observations` shape above, so
  downstream `join_weather_asof` needs zero changes.
- Define an explicit **missing-data strategy**: the current pipeline already
  leaves an unmatched asof-join as `NaN` and imputes only at the
  train-fit preprocessing stage (never silently filled at the raw-join
  step) — this policy should carry over unchanged. A real adapter should
  additionally decide, per Section 9, what to do when the API itself is
  unavailable for a given historical window (backfill from a different
  provider? leave the window's `disruption_flag`-relevant rows as
  weather-`NaN` and let the existing imputer handle it? — recommend the
  latter, since it requires no new missing-data-handling code path).

---

## 6. Historical delay data availability

**For the recommended source (MBTA):** historical delay/performance data
**does exist** via the LAMP performance dataset and the `transit-performance`
system (Section 4) — scheduled vs. actual times organized by
route/direction/stop/trip, which is structurally close to what
`historical_operational_records` needs. This has **not** been ingested,
schema-validated, or field-verified against RouteWise's exact contract as
part of this discovery — that verification is the first concrete task of
Stage 12, not something to assume solved.

**General finding, stated explicitly per the brief's instruction not to
fabricate:** most open GTFS feeds publish **only the static schedule** —
scheduled times, not realized ones. Actual/delay/cancellation data, when it
exists publicly at all, almost always comes from a **separate** source: a
GTFS-Realtime archive someone has captured over time (GTFS-RT itself is a
live feed, not historical, unless archived), or an agency's own
performance-reporting program (as MBTA has). This must be verified
per-agency; it should never be assumed to exist just because static GTFS
does.

### Design implication: the model must support a labels-unavailable mode

Per the brief's explicit instruction, RouteWise must not fabricate delay
labels if a chosen real feed turns out to lack them. Concretely:

- `training/retraining_safety.py`'s pre-flight checks should gain a check
  for "does the current ingestion source provide `disruption_flag` labels,"
  and refuse to run **supervised** retraining (not the whole pipeline) if
  not — this is additive to the existing safety-check list, not a rewrite.
- `src/monitoring/performance.py` **already has this exact behavior built
  in**: `run_performance_monitoring` explicitly returns
  `{"available": False, "message": LABEL_UNAVAILABLE_MESSAGE, ...}` when
  `y_true` is `None`, rather than fabricating a metric. This code path is
  ready for a labels-unavailable real deployment with zero changes.
- Until real labels exist, RouteWise's **routing/scoring can still run** —
  disruption *probability* is a model *output*, not an input, so a model
  trained on the synthetic label distribution (clearly flagged as such) could
  keep serving predictions while historical-label collection is bootstrapped
  from the real feed going forward (new records accumulate in real time even
  without a backfilled history) — this "limited mode" is a policy/labeling
  decision for Stage 12, not a code blocker uncovered here.

---

## 7. Canonical data contract

The contract below sits between the ingestion adapters (Synthetic / Real
GTFS / Real Weather / Real Operational — Section 8) and Stage 3's existing
pipeline. It reuses **exactly** today's raw-table shapes where they already
generalize, and adds one new table (`service_calendar`) that does not exist
today at all. Every field is marked SOURCE (comes directly from the
upstream feed), DERIVED (computed by the ingestion adapter from source
fields, before Stage 3 ever sees it), or MODEL (computed later, by Stage 3's
existing feature pipeline — unchanged).

### `stops`

| Field | Type | Class | Notes |
|---|---|---|---|
| `stop_id` | string | SOURCE | GTFS `stop_id` |
| `stop_name` | string | SOURCE | GTFS `stop_name` |
| `stop_lat` | float | SOURCE | GTFS `stop_lat` |
| `stop_lon` | float | SOURCE | GTFS `stop_lon` |
| `zone_id` | string | **DERIVED** | computed by the ingestion adapter from `(stop_lat, stop_lon)` + the chosen weather provider's spatial unit (Section 5) — never sourced from GTFS |

### `routes`

| Field | Type | Class | Notes |
|---|---|---|---|
| `route_id` | string | SOURCE | |
| `route_short_name` | string | SOURCE | |
| `route_long_name` | string | SOURCE | |
| `route_type_gtfs` | int | SOURCE | real GTFS numeric code |
| `transport_mode` | string | DERIVED | looked up from `route_type_gtfs` via the shared `GTFS_ROUTE_TYPE`-equivalent table (currently generation-time only; becomes an ingestion-time lookup) |

### `trips`

| Field | Type | Class | Notes |
|---|---|---|---|
| `trip_id`, `route_id`, `service_id`, `direction_id`, `trip_headsign` | | SOURCE | direction_id may be absent in some feeds — see Section 9 |

### `stop_times`

| Field | Type | Class | Notes |
|---|---|---|---|
| `trip_id`, `stop_id`, `stop_sequence` | | SOURCE | |
| `scheduled_arrival`, `scheduled_departure` | string (extended `HH:MM:SS`, hours may exceed 23) | SOURCE | **parsing must change** from the synthetic modulo-24h scheme (Section 3, Section 9) |

### `service_calendar` — **new table, does not exist today**

| Field | Type | Class | Notes |
|---|---|---|---|
| `service_id` | string | SOURCE | from `calendar.txt` and/or `calendar_dates.txt` |
| `service_date` | date | DERIVED | expanded from `calendar.txt`'s weekday booleans + date range, with `calendar_dates.txt` exceptions applied (add/remove) — this expansion is exactly what the synthetic generator's throwaway in-memory `calendar_df` already does; the real version persists it as its own validated artifact instead of discarding it |
| `is_exception` | bool | DERIVED | true if this `(service_id, service_date)` pair came from a `calendar_dates.txt` exception rather than the regular weekly pattern — useful for data-quality auditing, not currently modeled |

### `weather`

| Field | Type | Class | Notes |
|---|---|---|---|
| `observation_id`, `zone_id`, `timestamp`, `precipitation_mm`, `temperature_c`, `visibility_km` | | SOURCE (from the weather API) | `zone_id` here matches `stops.zone_id`'s derived value — join key consistency is the adapter's responsibility |

### `operational_events` (replaces `historical_operational_records`, renamed for honesty — see below)

| Field | Type | Class | Notes |
|---|---|---|---|
| `record_id` | string | DERIVED | synthetic key today; real version can be a stable hash of `(trip_id, stop_id, service_date)` |
| `trip_id`, `stop_id`, `service_date` | | SOURCE | |
| `scheduled_time` | datetime | SOURCE | from static GTFS `stop_times` + `service_date` |
| `actual_time` | datetime | SOURCE **or ABSENT** | from the real performance source (Section 6) — **must be nullable**, unlike today's synthetic contract where it's always present |
| `delay_minutes` | float | DERIVED | `actual_time - scheduled_time`, only computable when `actual_time` exists |
| `cancelled` | bool | SOURCE **or ABSENT** | from GTFS-RT `TripUpdate.schedule_relationship` or the agency's performance feed, if available |
| `disruption_flag` | int (0/1) | MODEL-ADJACENT DERIVED | unchanged rule (`src/utils/disruption_rules.py::is_disruption`), computed only when `delay_minutes`/`cancelled` are non-null — **this is the field that may be entirely absent for a real feed lacking historical performance data** (Section 6) |
| `transport_mode` | string | DERIVED | looked up via `trip_id → route_id → transport_mode`, not assumed pre-populated (Section 2.4) |

The rename from `historical_operational_records` to `operational_events` is
a **naming recommendation**, not a requirement — flagged because "historical
operational records" currently implies a completeness real data won't have;
"events" more honestly describes a stream that may have partial/missing
outcome fields. This is a Stage 12 naming decision, not asserted as
necessary here.

### `fares`

| Field | Type | Class | Notes |
|---|---|---|---|
| `route_id`, `fare_amount`, `currency` | | SOURCE **or entire table ABSENT** | must be optional at the contract level (Section 3) — routing/decision-engine cost scoring must degrade gracefully (`cost: null`/excluded from scoring) rather than assume a fare always exists |

Everything **downstream** of this contract — `src/features/*.py`,
`training/*.py`, `inference/*.py`, `api/*`, `src/monitoring/*` — is
unchanged, by design: they already consume exactly these table shapes today.

---

## 8. Ingestion architecture (dual-source)

Per the brief, the synthetic generator is **not deleted**. Both sources
converge on the Section 7 contract before Stage 3 ever runs:

```
Synthetic Generator ─────┐
(src/ingestion/           │
 generate_demo_data.py,   │
 UNCHANGED)                │
                            ├──→ Canonical Contract ──→ existing Stage 3+ pipeline
Real GTFS Adapter ─────────┤     (Section 7 schemas,      (UNCHANGED)
(new: static + calendar)   │      validated by an
                            │      extended
Real Weather Adapter ──────┤      src/validation/schemas.py)
(new: API-backed)          │
                            │
Real Operational Adapter ──┘
(new: GTFS-RT archive or
 agency performance API —
 MAY BE ABSENT, see §6)
```

Concretely:

- A new `src/ingestion/adapters/` package (or similar), one module per
  source, each producing the Section 7 contract tables and nothing else —
  Stage 3 (`src/features/build_dataset.py`) should not need to know or care
  which adapter ran.
- `data/raw/<source>/...` — today's `gtfs/operational/weather` directory
  split generalizes fine; add a `source` marker (e.g. a
  `data/raw/SOURCE_CARD.md`, mirroring today's `DATASET_CARD.md` pattern
  exactly) so DVC-tracked snapshots are unambiguous about which adapter
  produced them.
- `params.yaml data.mode: "demo" | "production"` **already exists** as a
  config field (confirmed in `params.yaml`) — it is not yet read by any code
  path found in this audit; wiring it to actually select an adapter is the
  natural integration point, not a new concept.
- The DEVELOPMENT/DEMO labeling that's pervasive today (dashboard banner,
  README, dataset card, `data_quality.py`'s demo-metadata check) must gain a
  real counterpart: whatever a real-source run produces must be labeled
  honestly too — e.g. `dataset_type = "REAL/<agency>"` vs. today's
  `"DEVELOPMENT/DEMO"` — following the exact same "never claim more than
  what was verified" discipline already established for monitoring
  (`src/monitoring/schemas.py::DATASET_TYPE`).

---

## 9. Data quality risks and validation requirements

| Risk | Where it would surface | Validation rule required |
|---|---|---|
| Timezone differences | `scheduled_time`/`timestamp` columns across GTFS, weather, and operational sources | Every ingestion adapter must normalize to a single explicit timezone (or store tz-aware timestamps) before any cross-source join — today's synthetic data is implicitly naive/local and this has never been tested against a real mismatch. New check: reject rows whose timestamp lacks explicit tz info once real sources are wired in. |
| DST transitions | Any date crossing a DST boundary in the feed's home timezone | GTFS's extended `HH:MM:SS` clock (hours >23) exists partly to sidestep DST ambiguity for late-night trips — the parser fix already required for midnight-crossing (below) should be DST-aware, not just wraparound-aware. New check: flag (not silently fix) any service_date where local-time arithmetic would be ambiguous (the "fall back" hour). |
| Missing `stop_times` for some trips | `trips.txt` referencing a `trip_id` with zero rows in `stop_times.txt` | New check (extends `src/validation/validators.py::check_required_columns`/FK pattern): every `trip_id` in `trips` must have ≥2 `stop_times` rows; otherwise it's unroutable and must be dropped with a WARNING, not silently included as a zero-leg edge. |
| Duplicate records | Any GTFS file, or the operational feed | Already handled generically: `src/preprocessing/clean.py::drop_exact_duplicates` + `src/validation/validators.py::check_duplicates` (exact + primary-key). Reused unchanged — no new code needed, just confirmed applicable. |
| Malformed feeds | Any GTFS file (missing required columns, wrong encoding, corrupt zip) | New check: adapter-level "does this ZIP even parse as GTFS" gate before any table reaches `src/validation/schemas.py` — today's loader assumes well-formed CSVs unconditionally. |
| Cancelled trips | `operational_events`/GTFS-RT `TripUpdate.schedule_relationship = CANCELED` | Contract already supports this (`cancelled: bool`) — `is_disruption()` already treats `cancelled=True` as disruptive unconditionally. No change needed once the field is populated; new check: a cancelled trip's remaining `stop_times` rows should not be treated as normal scheduled service for graph-building purposes. |
| Route variants | `trips.txt` — multiple distinct stop patterns sharing `(route_id, direction_id)` | **The central graph-builder redesign** (Section 11) — this is the risk the current `_select_representative_trips` assumption is not safe against. |
| Service calendars | `calendar.txt` + `calendar_dates.txt` | New contract + new validation entirely (Section 7's `service_calendar` table) — today there is none. |
| Midnight-crossing trips | `stop_times.arrival_time`/`departure_time` with hour ≥24 | New check + parser fix: replace `minutes_to_hhmm`'s modulo-24 wraparound (synthetic-only, not GTFS-correct) with real extended-time parsing that keeps `service_date` fixed and lets the clock exceed 24:00:00, as GTFS intends. `src/routing/graph_builder.py`'s existing `if travel_time < 0: travel_time += 24*60` heuristic (added for the synthetic wraparound case) should be revisited once real extended-time parsing is in place — it may become unnecessary or need to change. |
| Missing coordinates | `stops.txt` rows with null/zero `stop_lat`/`stop_lon` | New check: `src/validation/schemas.py::STOPS.not_nullable` already includes `stop_lat`/`stop_lon` — this already fires today; the new risk is **(0, 0)** as a silently "valid" but nonsensical placeholder some feeds use for unknown coordinates — add an explicit range/plausibility check beyond simple non-null. |
| Inconsistent route IDs | Feed updates renumbering/renaming `route_id`s between GTFS versions | New requirement: every ingested feed snapshot needs a captured feed version (GTFS `feed_info.txt` if present, or the download date) recorded in lineage — `dataset_metadata.json`'s existing pattern (Section 13) generalizes to this, but today assumes a single unversioned synthetic feed. |
| Feed updates | MBTA (and most agencies) update GTFS "several times per month" (confirmed, Section 4) | New requirement: ingestion must be idempotent and re-runnable against a new feed snapshot without silently mixing two feed versions' `stop_id`/`route_id` spaces — needs a pinned feed-version identifier per DVC-tracked snapshot (same DVC directory-hash mechanism already in use, just needs a documented "one snapshot = one feed version" discipline). |
| Historical schedule changes | A `route_id` whose stop pattern changed mid-history (e.g. a route extension) | This interacts directly with the "route variants" risk and the `historical.py` rolling-window features — a `route_id`'s historical delay stats implicitly assume a stable route identity over the rolling window; real agencies do restructure routes. Not solvable generically; flag as a known limitation requiring case-by-case judgment when the real feed is chosen, not a rule enforceable purely in code. |

---

## 10. Feature availability matrix

Evaluated against the model's actual 12 input features
(`training/prepare_inputs.py::ALL_FEATURES`) plus the label, using the MBTA
candidate as the concrete reference point (Section 4/6).

| Feature | Availability | Notes |
|---|---|---|
| `transport_mode` | **AVAILABLE** | direct from `routes.route_type` (Section 3) |
| `hour` | **AVAILABLE** | derived from `scheduled_time`, unchanged logic |
| `day_of_week` | **AVAILABLE** | same |
| `time_of_day_bucket` | **AVAILABLE** | same, config-driven buckets (no synthetic dependency) |
| `day_period` | **AVAILABLE** | same, config-driven peak/off-peak/night windows — the window *values* are a policy choice a real deployment should re-tune per city, but the mechanism is unchanged |
| `transfer_dependency` | **AVAILABLE** | fully structural, computable from real `stop_times`+`trips` (Section 2.7) — performance at real scale flagged (Section 11), not availability |
| `precipitation_mm` | **PARTIALLY AVAILABLE** | requires a weather API integration (Section 5) not yet built; available in principle, not in the current repo |
| `temperature_c` | **PARTIALLY AVAILABLE** | same |
| `visibility_km` | **PARTIALLY AVAILABLE** | same |
| `historical_delay_minutes` | **PARTIALLY AVAILABLE (MBTA)** / **NOT AVAILABLE (generic open GTFS)** | depends entirely on the chosen feed having a real performance-history source (Section 6) — confirmed to likely exist for MBTA subway/light rail/commuter rail, unconfirmed for MBTA bus, and not assumable for a generic feed |
| `rolling_7d_delay_minutes` | same as above | same source dependency |
| `historical_reliability` | same as above | same source dependency |

**Label (`disruption_flag`)**: same conditional status as the three
historical features above — it is *derived from* `delay_minutes`/`cancelled`
by the unchanged `is_disruption()` rule (Section 2.6), so its availability is
strictly gated on the same real performance-history source existing. No
feature here needs to be invented or replaced with synthetic-style data if
that source is genuinely absent — the correct response per the brief is
Section 6's labels-unavailable mode, not fabrication.

**Feature needing redesign, not just re-sourcing**: none of the 12 model
features themselves need redesigning — they're all either purely structural
(computable from GTFS alone) or purely weather/history-sourced (an
availability question, not a definitional one). The one thing that *does*
need redesign because the synthetic generator creates information a real
feed structurally cannot — a single fixed stop-pattern-per-route+direction —
is not a model *feature*, it's the **graph construction** step (Section 11).

---

## 11. Routing/graph changes required

**Finding: the "70-node/18-route" scale itself is not embedded anywhere in
code** — `src/routing/graph_builder.py` builds one node per row in `stops`
and iterates route/trip tables generically; no loop bound, array size, or
hardcoded count depends on the synthetic network's specific size.
`src/decision_engine/` similarly operates on however many candidates a query
produces. **The routing API contract (`RouteSchema`, `SegmentSchema`, the
`/recommend-route`/`/reroute` request/response shapes) has no size
dependency either.** Scaling to hundreds/thousands of stops and many routes
is not blocked by any hardcoded assumption.

**What genuinely must change**, in order of impact:

1. **`_select_representative_trips` / the representative-trip simplification
   (`src/routing/graph_builder.py`).** This is the one place the code
   explicitly documents its own synthetic-only correctness (Section 2.8).
   For real data, edge construction must instead group trips of a
   `(route_id, direction_id)` by their **actual distinct stop-sequence
   pattern** (a tuple of `stop_id`s in order, sometimes called a "trip
   pattern" or approximated via `shape_id` if present) and build a
   representative edge set **per distinct pattern**, not per
   `(route_id, direction_id)` alone. This changes the node/edge model from
   "one path per route+direction" to "one or more paths per route+direction,"
   which is a real (if contained) redesign of `build_routing_graph`'s core
   loop — not a config change.
2. **Performance at scale.** `compute_transfer_dependency`'s O(n²)-per-group
   nested loop (Section 2.7) and `build_routing_graph`'s per-edge Python-level
   iteration (no vectorization) are fine at synthetic scale (70 stops, 18
   routes, small per-group sizes) and are a real risk at "hundreds/thousands
   of stops, multiple modes" scale — flagged as a performance redesign
   candidate for Stage 12/13, not a correctness blocker for a first real
   integration at moderate scale.
3. **Config values that must be re-tuned, not redesigned**:
   `routing.normalization.fixed_bounds` (Section 2.8, tied to
   `SYNTHETIC_UNITS`), `routing.transfer_penalty` (currently "an engineering
   estimate, not measured from data" per its own comment — should ideally be
   informed by real `transfers.txt` minimum-transfer-times if the chosen feed
   publishes them, per Section 3), and `routing.candidate_generation.
   k_shortest_paths` (currently 5 — reasonable at any scale, but worth
   revisiting for a much larger real graph where 5 shortest paths may cluster
   too tightly to give meaningfully different candidates).
4. **`routing.prediction_context.default_datetime`/`default_weather`**
   (the fixed reference point used when a query doesn't supply its own) is
   currently a documented, fixed point "within the training data's date
   range" — this concept survives the migration unchanged, it just needs a
   real value once real data has a real date range.

No change is required to the **routing API contract** itself
(`RouteRecommendationRequest`/`Response`, `RerouteRequest`/`Response`) — it
already accepts arbitrary origin/destination stop IDs and returns whatever
candidates the graph produces, with no assumption about network size baked
into the schema.

---

## 12. Model implications

Summarized from Section 10's feature matrix:

- **7 of 12 features (`transport_mode`, `hour`, `day_of_week`,
  `time_of_day_bucket`, `day_period`, `transfer_dependency`, plus the derived
  `zone_id` join key) are AVAILABLE from static GTFS alone**, with no
  external dependency beyond the chosen feed itself.
- **3 features (`precipitation_mm`, `temperature_c`, `visibility_km`) are
  PARTIALLY AVAILABLE** — available in principle from a weather API
  integration not yet built (Section 5), zero risk to the model's
  *architecture*, pure integration work.
- **2 features + the label (`historical_delay_minutes`,
  `rolling_7d_delay_minutes`, `historical_reliability`, `disruption_flag`)
  are PARTIALLY AVAILABLE for the recommended MBTA source and NOT ASSUMABLE
  for a generic feed** — this is the one place real model behavior changes:
  if historical performance data can't be confirmed and ingested, **Stage 4
  training cannot run in its current supervised form at all** (there is no
  label), and the system must operate in the labels-unavailable mode
  described in Section 6 (serve an already-trained, honestly-labeled
  synthetic-trained model; monitor factually reports performance as
  `NOT_AVAILABLE`, exactly as `src/monitoring/performance.py` already does
  today for this exact scenario).
- **No feature needs to be invented or approximated with synthetic-style
  data to fill a gap** — every PARTIALLY/NOT AVAILABLE feature's correct
  handling is "integrate the real source" or "run in the already-built
  labels-unavailable mode," never fabrication.
- **The promotion gate, training pipeline, and retraining orchestration
  (Stages 4/5/10) need zero code changes** — they operate on
  `data/processed/{train,val,test}.parquet` + `feature_manifest.json`,
  both of which are already source-agnostic outputs of Stage 3. The gate's
  *threshold values* (`params.yaml evaluation.promotion_gates`) are
  explicitly documented as "engineering acceptance criteria, not
  scientifically derived" for the synthetic dataset's specific difficulty —
  they should be **re-evaluated, not assumed to transfer**, once real data's
  actual achievable metrics are known (a real feed's disruption base rate,
  noise characteristics, and feature predictiveness will likely differ from
  the synthetic generator's tuned parameters).

---

## 13. Monitoring implications

Stage 9's architecture (`src/monitoring/`) needs **no structural changes** —
its reference/current split, drift methods, decision policy, and API/
dashboard integration are already generic over "whatever's in
`data/processed/`." Three concrete adjustments are needed when moving from
DEVELOPMENT/DEMO to REAL DATA:

1. **Reference dataset re-establishment.** `src/monitoring/reference.py`'s
   `establish_or_verify_reference` already refuses to silently swap
   reference datasets (`ReferenceChangedError` unless `force=True`) — moving
   from synthetic to real data is exactly the kind of deliberate,
   intentional reference change this mechanism was built for. Use
   `--force-reference` explicitly, once, when the first real
   `train.parquet` replaces the synthetic one — and expect the monitoring
   report immediately after to show real (not fabricated) drift/quality
   results against the new reference, which may look very different from the
   synthetic baseline. This is correct behavior, not a bug to fix.
2. **`dataset_type` labeling.** `src/monitoring/schemas.py::DATASET_TYPE`
   is currently a hardcoded constant, `"DEVELOPMENT/DEMO"`. This should
   become a config-driven value (read from wherever Section 8's
   `data.mode`/source-selection config lives) so real-data monitoring runs
   correctly report e.g. `"REAL/MBTA"` — a one-field change, not an
   architecture change, but a real one: today's constant would otherwise
   *silently mislabel real monitoring results as demo data*, which directly
   violates the project's own established "never claim more than verified"
   discipline.
3. **Directory-layout generalization.** `reference.py`'s
   `build_reference_metadata` and `data/processed/dataset_metadata.json`'s
   `dvc_raw_hashes` currently assume exactly 3 fixed raw-source keys
   (`gtfs`, `operational`, `weather`) — Section 8's dual-source architecture
   may add more raw directories (e.g. a separate real-operational-events
   archive, a separate calendar source). This needs to generalize from 3
   fixed dict keys to an iterable list of `(name, path)` pairs, a small,
   contained change in `src/utils/metadata.py` and `src/monitoring/
   reference.py`, not a redesign.

DVC lineage tracking itself (Section 2.11) is fully preserved — real raw
data gets `dvc add`-ed into the same directory-hash mechanism synthetic data
already uses; the only new requirement is an actual remote once real data
volume grows past what local-cache-only DVC can reasonably hold (flagged
already in Section 2.11 and Section 15).

---

## 14. Licensing and data-use considerations

- **This discovery did not read the MassDOT Developers License Agreement.**
  It is a PDF linked from the MBTA developer portal, not fetched or
  summarized here — per the brief's instruction to not download/ingest
  anything yet, and because license terms deserve a careful, dedicated read
  rather than an AI summary standing in for it. **This is a hard blocker
  before Stage 12 ingestion begins**, regardless of the strong technical fit
  found above.
- **General GTFS licensing note** (from the Mobility Database/Transitland
  research, Section 4): GTFS as a *format* carries no license of its own;
  each *feed* is separately licensed by its publishing agency, commonly
  (but not universally) under a permissive/open license such as CC BY —
  Transitland's own summary explicitly states they review and summarize each
  feed's actual license individually because it varies feed-to-feed. This
  means **the license must be confirmed per chosen feed**, not assumed from
  "GTFS is generally open."
- **Historical performance data may carry separate terms** from the static
  GTFS feed itself — `transit-performance` (the GitHub code) is MIT-licensed,
  but that license covers the *analysis code*, not necessarily the
  *underlying MBTA performance data* it's applied to; the data access terms
  need separate confirmation, likely under the same MassDOT agreement or a
  developer-registration requirement mentioned on the LAMP page.
- **Attribution requirements**: not yet determined for the specific chosen
  feed — many open-data licenses (CC BY family in particular) require
  attribution in any derived product; if RouteWise's dashboard/README ever
  displays real transit data publicly, an attribution line will likely be a
  license requirement, not just good practice. Flag for the license review.
- **Commercial-use restrictions**: RouteWise is a development/MLOps
  demonstration project (per its own README, Section 1's problem
  statement) — most public agency open-data licenses permit this use case,
  but the license review (above) must confirm it explicitly, especially if
  the repository is or becomes public.
- **Weather API licensing**: whichever provider is selected (Section 5) will
  have its own terms of service and rate limits — not researched here since
  no specific provider was selected as part of this discovery, per the
  brief's "do not hardcode an API key" instruction implying provider
  selection itself is a later, separate decision.

---

## 15. Implementation plan

Phased, each phase gated on the previous one's real (not assumed) outcome —
consistent with this project's established "verify before claiming"
discipline throughout Stages 1–10.

**Phase 0 — Legal/licensing gate (blocking, no code).**
Read the MassDOT Developers License Agreement in full; confirm the intended
use (development/research MLOps project, potentially public repository) is
permitted; confirm whether the LAMP historical performance data has separate
terms; document the outcome. Do not proceed to Phase 1 until this is
resolved and recorded (a `docs/` license-review note, mirroring this
report's own location, is the natural place).

**Phase 1 — Canonical contract + validation extension (code, no real data
yet).**
Implement Section 7's contract as an extension to
`src/validation/schemas.py` (new `service_calendar` `TableSchema`, widen
`trips.service_id` from a 2-value enum to an open string set validated
against the new calendar table's actual values, make `fares`/`cancelled`/
`actual_time` nullable at the schema level). This can and should be built
and tested against the *existing synthetic data* first (synthetic data
already satisfies a superset of the loosened contract), proving no
regression before any real bytes are involved.

**Phase 2 — Real GTFS static adapter (code + real static data only, no
operational/weather yet).**
Build the `src/ingestion/adapters/gtfs_real.py`-equivalent module: download
(or accept a local path to) an MBTA GTFS ZIP, parse it into the Section 7
contract, run it through the Phase 1 validation, and confirm it produces a
graph via the **redesigned** `build_routing_graph` (Section 11's
representative-trip-pattern fix — this is the phase that fix belongs in,
since it can't be verified without real route-variant data). Track the
result via DVC exactly as synthetic data is today. The synthetic generator
and its `dvc`-tracked outputs remain fully intact and runnable throughout —
this is strictly additive.

**Phase 3 — Real weather adapter (code + a chosen, ToS-reviewed weather
API).**
Select a specific weather API (separate decision, not made in this
discovery), read its key from environment config only, implement the
`zone_id` derivation (Section 5), and confirm the existing `join_weather_asof`
requires no changes.

**Phase 4 — Real historical-performance adapter (the highest-uncertainty
phase).**
Attempt to ingest MBTA's LAMP performance data into the `operational_events`
contract; verify field-by-field whether it actually provides
`scheduled_time`/`actual_time` at the `(trip_id, stop_id)` grain
`historical.py` needs. **If it does not**, formally switch to the
labels-unavailable mode (Section 6/12) for the real-data path rather than
forcing a fit — this is a legitimate, already-anticipated outcome, not a
failure of the migration.

**Phase 5 — Feature pipeline + training run against real data.**
Run `src/features/build_dataset.py` (unchanged) against the real contract
tables; run `training/train.py`/`track_and_register.py`/the promotion gate
(unchanged) and **re-evaluate** (not assume) the gate's threshold values
against real data's actual achievable metrics (Section 12).

**Phase 6 — Monitoring reference re-establishment.**
`--force-reference` the real `train.parquet` as the new monitoring baseline
(Section 13); wire `dataset_type` to reflect the real source; generalize the
raw-hash-key list from 3 fixed names to N.

**Phase 7 — Dashboard/README honesty pass.**
Update the DEVELOPMENT/DEMO labeling pervasive across the dashboard, README,
and dataset cards to correctly distinguish "demo mode" from "real mode" runs
(Section 8), including a real license attribution line if Phase 0 determined
one is required.

Each phase produces its own artifacts/commits, mirroring the project's
existing per-stage convention — this plan does not itself constitute
Stage 12's implementation, only its roadmap.

---

*End of Stage 11 Discovery Report. No implementation code was written as
part of this stage, per the brief's explicit instruction.*

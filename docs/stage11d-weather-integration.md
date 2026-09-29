# Stage 11D: Historical Weather Integration (NOAA GHCNh)

**Status: NOAA GHCNh integrated and measured. MODEL_READY remains FALSE**
(weather coverage improved substantially but is not the only blocker, and
does not by itself clear the readiness bar -- see Section 6).

Stage 11C's `MODEL_READY = FALSE` decision listed real weather coverage
(13.5%, NWS-only, a short rolling window) as one of four blockers. This
stage replaces/augments NWS with an official, deep-historical NOAA source
-- **GHCNh (Global Historical Climatology Network hourly)** -- and measures
the actual resulting coverage, rather than assuming a deep archive would
automatically solve the problem.

---

## 1. Source verification

- **Product page**: https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly
- **Bulk access** (no API key, no token, confirmed empirically): one PSV
  (or parquet) file per station per year --
  `https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year/{year}/psv/GHCNh_{station_id}_{year}.psv`
- **Station used**: `USW00014739` (Boston Logan International Airport,
  42.3606 N / -71.0097 W) -- the physically same station as the Stage 11B
  NWS adapter's `KBOS`; both sources are joined under the same
  `weather_zone_id="KBOS"` project key so they combine correctly.
- **License**: NOAA data are not subject to U.S. copyright and are
  provided free of charge; no separate agreement or token, confirmed on
  the product page. See `GHCNH_LICENSE_REFERENCE` in
  `src/ingestion/common/provenance.py`.
- **Retrieval date**: 2026-09-29 (this stage). The full, complete download
  of the 2026 station-year file reaches into **October 2026** -- i.e. it
  comfortably covers the real MBTA training window established in Stage
  11C (2026-08-01 .. 2026-09-29).

### A finding this stage caught and corrected in itself

An early exploratory `curl --max-time 90` probe of the 2026 file appeared
to show data stopping at **2026-02-26** -- read at face value, that would
have meant GHCNh carries a multi-month publication lag, structurally
similar to the NOAA ISD-Lite finding from Stage 11C. That reading was
**wrong**: the probe's time budget cut the transfer short partway through
a 30+ MB file, and `curl` does not treat a truncated write as an error
without `-f`/`--fail` plus a `Content-Length` check. The project's own
ingestion code (`src/ingestion/weather/ghcnh.py::fetch_station_year`,
which imposes no such budget) downloaded the complete file and confirmed
real coverage through early October 2026. This is recorded here rather
than silently corrected, because "verify against real data, not
documentation or a quick probe" is exactly the discipline this project
has tried to hold itself to since Stage 11C -- including when the
project's own preliminary probe was the thing that needed re-checking.

---

## 2. Units and schema, verified against real downloaded values

GHCNh's raw PSV has ~50 columns; only the subset in
`src/ingestion/weather/ghcnh.py::RAW_COLUMNS` is read. Verified against
real Boston Logan rows (not assumed from documentation, which in one
place disagreed with the actual data):

| Raw column | Canonical field | Unit (verified) | Notes |
|---|---|---|---|
| `DATE` | `timestamp` | UTC, no offset in the raw file | Treated as UTC, consistent with ISD/METAR global-hourly convention (GHCNh is built from ISD) |
| `temperature` | `temperature_c` | Celsius, decimal | No scaling |
| `precipitation` | `precipitation_mm` | mm, decimal | No scaling |
| `wind_speed` | `wind_speed_ms` | m/s, decimal | No scaling |
| `sea_level_pressure` / `station_level_pressure` | `pressure_hpa` | hPa, decimal | Sea-level preferred; station-level as fallback when sea-level is null |
| `visibility` | `visibility_km` | **kilometers**, NOT meters | GHCNh's own documentation page states meters; the real data disagrees. Verified: raw value `16.093` converts exactly to 10.0 US statute miles, and `4.828` converts exactly to 3.0 miles -- both standard US ASOS visibility readings, proving the column is already km. Used directly, never divided by 1000. |
| `LATITUDE` / `LONGITUDE` | `station_lat` / `station_lon` | decimal degrees | |

The canonical `WEATHER_CONTRACT` (`src/ingestion/common/contracts.py`) was
extended with `wind_speed_ms`, `pressure_hpa`, `station_lat`,
`station_lon`, and `source` -- all nullable, since the pre-existing NWS
adapter does not populate the first four. Neither the training table nor
any downstream code depends on a NOAA-specific column name; both adapters
(`normalize_nws_observations`, `normalize_ghcnh_observations`) map into
these same canonical names.

---

## 3. Combining GHCNh and NWS

`src/ingestion/weather/normalize.py::combine_weather_sources` stacks both
canonical tables and resolves exact `(weather_zone_id, timestamp)`
collisions by an explicit priority order (`["NOAA GHCNh", "NWS"]` --
GHCNh preferred as the deeper, richer, QC'd source) -- never averaged or
otherwise blended. In practice, GHCNh (85,425 rows, 2025-01-01 ..
2026-10-06) and NWS (611 rows, 2026-09-27 .. 2026-09-29) barely overlap in
time, so this priority rule rarely fires; it exists for correctness, not
because this dataset exercises it heavily.

The existing leakage-safe backward asof-join
(`join_weather_asof`, unchanged in its join *logic*, only extended to
carry whichever weather feature columns are present in the input frame)
is applied to the combined table exactly as it was applied to NWS alone
in Stage 11B/C.

---

## 4. Leakage-safety

Unchanged guarantee from Stage 11B, re-verified against the combined
source: `pd.merge_asof(..., direction="backward", tolerance=...)` means
only observations with `timestamp <= scheduled_time` (within the
configured tolerance) are ever used. `tests/test_stage11d.py::
TestLeakageSafeCombinedJoin::test_no_future_weather_observation_ever_used_across_many_events`
proves this explicitly across 20 synthetic events, each paired with one
legitimate past observation and one observation tagged 2 days in the
future with a unique sentinel value -- the sentinel never appears in the
joined output.

---

## 5. Measured coverage (Stage 11D vs Stage 11C)

From `data/interim/real/weather_coverage_report.json`, generated against
the real 4,808,668-row training table:

| | Stage 11C (NWS only) | Stage 11D (NWS + GHCNh) |
|---|---|---|
| Overall weather coverage | 13.5% | **27.1%** |
| Total weather observations | 611 | 86,036 |
| Weather observation date range | 2026-09-27 .. 2026-09-29 | 2025-01-01 .. 2026-10-06 |

Coverage roughly doubled, but remains well below the 80% readiness bar.
**Root cause (measured, not assumed):** GHCNh's Boston Logan feed
interleaves many partial reports (e.g. wind-direction-only special
observations) with fewer rows that carry temperature/precipitation/
visibility/pressure together -- only ~1,736 of 14,574 raw GHCNh rows in
the Aug-Sep 2026 window have a non-null core temperature reading. With
the configured 2-hour asof-join tolerance
(`configs/real_data.yaml weather_join.max_time_difference_hours`), real
gaps between those core readings on some hours/days exceed the tolerance
window, leaving many transit events unmatched. `coverage_by_date` in the
report shows this directly: most Aug/early-Sep days sit around 3-25%
coverage, while 2026-09-27/28 (inside NWS's own dense rolling window)
reach 84%/99%.

This is a genuinely different root cause from Stage 11C's (a real archive
that reaches the window, but with denser gaps than a naive
"archive exists -> full coverage" assumption would suggest) -- documented
here rather than glossed over.

Per-feature coverage (all from the same report):

| Feature | Coverage |
|---|---|
| `precipitation_mm` | 32.0% |
| `temperature_c` | 27.1% |
| `visibility_km` | 20.2% |
| `wind_speed_ms` | 6.7% (GHCNh-only field, sparsest of the core measurements at Logan) |
| `pressure_hpa` | 11.4% |

Coverage by mode: bus 40.2%, metro 13.5%, tram 12.5% -- reflecting each
mode's own operating-hours distribution relative to when GHCNh's core
readings land, not a mode-specific data-quality difference.

---

## 6. Model-readiness impact

`weather_coverage_adequate` in `data/interim/real/model_readiness.json`
remains `false` (27.1% < the 80% bar). **`MODEL_READY` remains `FALSE`**
-- this stage does not claim otherwise. The blocking reasons list was
updated to describe the real, measured gap-structure root cause (Section
5) rather than repeating Stage 11C's now-superseded "NWS rolling window /
NOAA archive not yet published" narrative, which no longer describes the
actual constraint now that GHCNh is integrated.

Two options for a future stage, stated explicitly rather than silently
choosing one: (a) widen the asof-join tolerance beyond 2 hours with a
documented rationale, trading some temporal precision for coverage; or
(b) accept ~27% coverage and re-evaluate whether `MINIMUM_WEATHER_COVERAGE`
is the right bar for a weather feature at this density, rather than
silently lowering the constant.

---

## 7. What this stage did NOT do

- Did not train, register, or promote any model.
- Did not change `real_disruption_label_policy.active` (still `false`).
- Did not lower `MINIMUM_WEATHER_COVERAGE` or any other readiness bar.
- Did not modify the synthetic/demo data generation pipeline.
- Did not remove rail/ferry from the routing graph; both remain
  `label_available=false`, never assigned a fabricated label.
- Did not fetch a deeper GHCNh backfill beyond 2025-2026 -- the real MBTA
  historical-performance sample ingested so far is itself only a 60-day
  recent window (Stage 11B/C), so a multi-year weather backfill has no
  matching transit data to join against yet.

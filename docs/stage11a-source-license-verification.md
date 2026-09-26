# Stage 11A: Real-Data Source and Licensing Verification (MBTA/Boston)

**Status: VERIFICATION ONLY. No ingestion code was written for this stage.**

This report independently re-verifies the MBTA candidate identified in Stage
11 Discovery, using **official sources only** (MBTA developer portal,
MassDOT, MBTA's own GitHub documentation repositories, and NOAA/NWS federal
sources for weather). Every claim below is either a direct quote/close
paraphrase of an official document actually fetched during this stage, or is
explicitly marked as **NOT VERIFIED** / **NOT FOUND**. Nothing is asserted
from memory or from third-party blog summaries.

The full MassDOT Developers License Agreement — the actual governing legal
text — was located, downloaded, and read in full (see Section 3). This is
the single most important finding of this stage and the basis for the
go/no-go decision in Section 7.

---

## 1. Official source URLs

All sources actually fetched/read during this verification (not secondary
summaries):

| # | Source | URL | What was verified there |
|---|---|---|---|
| 1 | MBTA Developers portal | https://www.mbta.com/developers | Full resource inventory, license pointer |
| 2 | MBTA GTFS page | https://www.mbta.com/developers/gtfs | Static feed description, update cadence, mode coverage |
| 3 | MBTA GTFS-Realtime page | https://www.mbta.com/developers/gtfs-realtime | Feed format categories |
| 4 | MBTA GTFS-Realtime reference (GitHub) | https://github.com/mbta/gtfs-documentation/blob/master/reference/gtfs-realtime.md | Exact feed URLs, occupancy/non-revenue notes |
| 5 | MBTA GTFS static reference (GitHub) | https://github.com/mbta/gtfs-documentation/blob/master/reference/gtfs.md | Complete list of published GTFS static files incl. extensions |
| 6 | MBTA Historical Performance Data page | https://www.mbta.com/developers/historical-performance-data | LAMP + Open Data Portal product list, license pointer, coverage dates |
| 7 | MBTA LAMP GitHub repo | https://github.com/mbta/lamp | Confirms LAMP is the current rapid-transit + bus performance pipeline |
| 8 | **MBTA LAMP official Data Dictionary** | https://github.com/mbta/lamp/blob/main/Data_Dictionary.md | **Exact field-level schema for every LAMP export** (Section 3.3) |
| 9 | MassGIS/ArcGIS Open Data Hub dataset listing | https://gis.data.mass.gov/datasets/MassDOT::mbta-rapid-transit-events-2024-1 (and related "MBTA Rapid Transit Events/Headways/Travel Times" entries) | Confirms hosting platform and dataset naming; full field list was ultimately obtained from source #8, not this page (page is JS-rendered, not machine-readable via fetch — see Section 9 limitations) |
| 10 | **MassDOT Developers License Agreement (PDF, actual legal text)** | https://www.mass.gov/files/documents/2017/10/27/develop_license_agree_0.pdf (direct fetch returned HTTP 403; retrieved via the Internet Archive Wayback Machine snapshot dated 2026-08-22, which mirrors the same document mass.gov serves — see Section 3 for the access note) | **Full 4-page agreement text, read in full** (Section 3) |
| 11 | NWS (National Weather Service) API docs | https://www.weather.gov/documentation/services-web-api | Current/forecast data, no-key access, licensing |
| 12 | NOAA NCEI Access Services | https://www.ncei.noaa.gov/access | Historical data access options |
| 13 | NOAA Integrated Surface Dataset (ISD) product page(s) | https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database (and related NCEI pages) | Hourly historical fields incl. visibility, station coverage |

---

## 2. Exact data products verified

- **MBTA GTFS static feed**: bulk ZIP download (10–30 MB), "updated several
  times per month," explicitly covers **subway, bus, commuter rail, and
  ferry**; V3 API available as an alternative access method. One documented
  exclusion: Massport shuttles are not included as of Feb 21, 2019.
- **MBTA GTFS-Realtime**: three feeds — **TripUpdates, VehiclePositions,
  ServiceAlerts** — each published in three formats (standard protobuf,
  JSON, "enhanced" JSON with additional fields), at fixed CDN URLs (Section
  4). Occupancy/crowding data is explicitly limited to "bus, Orange Line,
  and some Red Line cars." Non-revenue-trip flagging exists only in the
  enhanced feeds and is explicitly documented as incomplete for light rail
  ("may appear as revenue trips").
- **Historical performance data**: the **LAMP** (Lightweight Application for
  Measuring Performance) pipeline, with an official, field-level Data
  Dictionary (Section 3.3) — this is the single most load-bearing source for
  RouteWise's disruption label and was verified at the field level, not just
  the product-description level.

---

## 3. License/terms findings

### 3.1 The governing document, and how it was actually obtained

Every MBTA developer page checked (portal, GTFS, GTFS-Realtime, Historical
Performance Data) states the identical sentence: **"Use of MBTA data is
governed by the MassDOT Developers License Agreement."** No page describes a
separate license specific to GTFS-Realtime or to historical/performance
data — the same single document governs all three, per MBTA's own pages.

The document itself is linked from mass.gov as a PDF:
`https://www.mass.gov/files/documents/2017/10/27/develop_license_agree_0.pdf`.
**A direct fetch of that URL (both via the automated web-fetch tool and via
a direct HTTPS request with a standard browser User-Agent) returned HTTP 403
"Not allowed."** This is recorded here as an access-method limitation, not a
finding about the document's status — mass.gov's edge/bot-protection layer
blocked the automated request; there is no indication the document itself is
unavailable to a human visiting the page in a normal browser.

To read the actual text despite that block, this stage retrieved a cached
copy via the **Internet Archive Wayback Machine** (a snapshot dated
2026-08-22, of the exact same mass.gov URL), which returned the real PDF
(4 pages, `application/pdf`, 87.5 KB) with matching content and structure to
what MBTA's own developer pages describe. **This is flagged explicitly**:
the agreement's full text below is read from an archived mirror of the
official document, not a live fetch of mass.gov itself. Before any
production ingestion, re-confirm this text still matches the live
mass.gov-hosted version (the document could have been updated since the
snapshot, though its own "Updated: November 13, 2009" footer — see below —
suggests it has been stable for a long time).

### 3.2 What the agreement actually says (quoted, not summarized)

The document is titled **"Massachusetts Department of Transportation
Developers License Agreement,"** footer-dated **"Updated: November 13,
2009."** Its own §1.1 defines "MassDOT" to explicitly **include the MBTA**,
and §1.2 defines "Data" broadly as *"the information and resources made
available on the Developers Page and the information and resources linked
to from the Developers Page and hosted by third parties with which MassDOT
has partnered."* Because GTFS, GTFS-Realtime, and the Historical Performance
Data page are all reached from (or are) MassDOT/MBTA "Developers Page"
content, and because MBTA's own pages point to this exact document for all
three, this document's broad "Data" definition is read here as covering all
three products — **this is an interpretation of a 2009-drafted, broadly
worded definition being applied to 2020s-era data products it could not have
named explicitly; it is not a certainty**, and is flagged as a residual risk
in Section 9.

Key clauses, quoted directly from the retrieved PDF:

- **§3.1 (License grant)**: *"MassDOT, subject to your acceptance of the
  Terms of this License Agreement, hereby grants You (Licensee)
  non-exclusive, limited, and revocable rights to use, reproduce, and
  redistribute the Data."* — **use, reproduction, and redistribution are
  all explicitly granted.**
- **§4.1 (Licensee obligations — attribution)**: *"You shall: Clearly
  acknowledge MassDOT as the provider of the Data."* — **attribution is a
  mandatory obligation**, not optional courtesy (Section 4 below).
- **§4.1 (other obligations)**: must *"Comply with all applicable laws,
  rules, and regulations,"* must **not** *"represent Yourself as MassDOT...
  or make any representations, warranties, or guarantees to Third Parties
  with respect to the Data,"* must **not** *"reproduce or use MassDOT or
  any of its agencies or authorities logos or trademarks,"* must **not**
  *"misrepresent the Data,"* and must **not** *"claim ownership of the
  Data in any manner, including but not limited to, on Your website, web
  application, or any other digital product."*
- **§4.2 (permitted combination)**: *"You may: Combine the Data with other
  data, provided such combination does not infringe any third party
  Intellectual Property Rights."* — directly relevant to RouteWise's own
  architecture, which combines GTFS + weather + historical performance data.
- **§5 (MassDOT's reserved rights)**: MassDOT may *"alter the Terms of this
  License Agreement at any time without notice,"* may *"make changes,
  modifications, or alterations to the Data without notice,"* may
  *"suspend or terminate the Data at any time without prior notice,"* and
  *"shall at all times maintain title, ownership, rights, and interest in
  and to the Data."*
- **§6 (Disclaimer and liability)**: the Data is provided *"'as is' and
  'with all faults'"* with **no warranty of accuracy, completeness, or
  continuity of access**, and MassDOT disclaims essentially all liability
  for any loss/damage from use of the Data.
- **§7.4 (Governing law)**: Massachusetts law; venue in Suffolk County
  Superior Court.
- **§8 (Entire agreement)**: this document is the entire agreement and
  supersedes prior agreements; MassDOT may modify or revoke it at any time,
  with notice to be given "on the Developers Page" if so.

### 3.3 What the agreement does NOT say (verified by absence, not assumed)

The following were specifically checked for and are **NOT present anywhere
in the 4-page document**:

- **No explicit commercial-use clause** — the license neither grants nor
  prohibits commercial use by name. §3.1's grant ("use, reproduce,
  redistribute") is not qualified by "non-commercial." Read together with
  the absence of any restriction, this supports a non-commercial
  academic/development project like RouteWise being permitted, but a
  commercial deployment would rest on the same silent, unqualified grant —
  worth a direct written confirmation from MassDOT/MBTA before any
  commercial use, since the document is old and silence is not the same as
  affirmative permission.
- **No explicit rate-limit clause** — rate limits, if any, are not defined
  in this legal document; they are an operational matter, not found on any
  of the pages checked (Section 9's limitations note this was searched for
  and not found on the developer/GTFS/GTFS-Realtime/historical pages).
- **No explicit storage/caching/archiving clause** — neither a restriction
  nor an explicit permission is stated beyond the general "reproduce" right
  in §3.1. DVC-tracking a downloaded snapshot is reasonably read as covered
  by "reproduce," but this is an inference, not a quoted permission.
- **No per-product (GTFS vs. GTFS-Realtime vs. historical performance)
  distinction of any kind** — one document, one set of terms, applied
  uniformly per MBTA's own pages (Section 3.1).
- **No explicit clause about GitHub/public-repository hosting of derived
  metadata**, nor about publicly displaying the data. §4.1's prohibition on
  claiming ownership and requirement to attribute MassDOT are the operative
  constraints for any public display; a public GitHub repo containing
  RouteWise's derived processed datasets (not the raw redistributed data
  itself) is a "derivative," not literally "the Data," and is not
  separately addressed.

### 3.4 Attribution requirements

**Mandatory, per §4.1**: *"Clearly acknowledge MassDOT as the provider of
the Data."* No specific wording, placement, or format is prescribed by the
agreement itself. Combined with §4.1's prohibition on using MassDOT/MBTA
logos or trademarks, the safe reading is: a **plain-text** acknowledgment
(e.g., "Transit data provided by MassDOT/MBTA") is required, but no logo or
trademark use is permitted alongside it.

### 3.5 Redistribution requirements

**Explicitly permitted** by §3.1 ("...redistribute the Data"), subject to
all of §4.1's obligations (attribution, no misrepresentation, no ownership
claims). No further conditions (e.g., "share-alike," specific license
pass-through to downstream recipients) are stated.

### 3.6 Commercial-use restrictions

**None stated explicitly** — see Section 3.3. Not a clean "yes," not a
clean "no." Recommend treating RouteWise's current, stated use (a
development/MLOps academic project) as clearly within the license's
unrestricted grant, and treating any future commercial use as requiring a
fresh, direct confirmation from MassDOT before proceeding — the license's
silence should not be read as a green light for a materially different use
case than what was verified here.

### 3.7 API/data rate limits

**Not found in the license agreement itself.** Not found on any of the MBTA
developer pages checked in this stage either (GTFS page, GTFS-Realtime page,
Historical Performance Data page). This is recorded as **NOT VERIFIED**,
not as "no rate limits exist" — an operational rate limit could exist at the
CDN/infrastructure level without being documented on these pages, and should
be discovered empirically (with conservative, polite request pacing) during
Stage 12 implementation rather than assumed either way.

### 3.8 Storage/caching restrictions

**Not found** — see Section 3.3. No explicit restriction located.

### 3.9 Requirements for derivative datasets

Not separately addressed beyond §4.1's blanket obligations (attribution, no
misrepresentation, no ownership claims, no MassDOT logo/trademark use) which
apply regardless of whether what's being distributed is the raw Data or a
derivative of it, per the plain reading of those clauses ("in any manner,
including but not limited to, on Your website, web application, or any
other digital product").

### 3.10 Requirements for displaying data publicly

Same governing clauses as above (§4.1) — no separate "public display"
clause exists. The practical requirement is: attribute MassDOT, don't use
their branding, don't misrepresent the data (e.g., don't present RouteWise's
own predictions as if they were MBTA-provided facts — already RouteWise's
existing, established practice per its honest-model-lifecycle-exposure
design from Stages 5–7), don't claim ownership of the underlying data.

### 3.11 Whether a GitHub repository may contain derived metadata

**Not separately addressed by the agreement.** Reasoned conclusion, not a
quoted permission: `feature_manifest.json`, `dataset_metadata.json`,
processed Parquet files with engineered features, trained model artifacts,
and monitoring reports are RouteWise's own derivative work built from the
Data, not "the Data" itself redistributed verbatim — the agreement's
obligations (attribution, no ownership claims over the source Data) apply to
how RouteWise describes its provenance, not to a categorical prohibition on
committing derived metadata. This is consistent with how RouteWise's own
existing `data/processed/*.json` metadata files are already handled
(committed to git, small, human-readable — Section 3.12 next).

### 3.12 Whether raw downloaded data should remain outside Git

**Recommended regardless of the license's silence on this point**, for two
independent reasons: (1) this project's own established DVC convention
(already used for all three synthetic raw-data directories) is exactly
"track large/raw data via DVC, commit only small derived JSON/metadata to
git" — a real GTFS ZIP + a real LAMP Parquet history would be considerably
larger than the synthetic CSVs and fit this existing convention even more
clearly; (2) §5.2's warning that MassDOT can change/alter the Data "without
notice" argues for DVC-versioning the exact snapshot actually used for a
given model, rather than assuming a re-download always reproduces the same
bytes — reinforcing, not just permitting, the existing DVC-first discipline.

---

## 4. Mode mapping

Per the official MBTA GTFS page (Source #2): the static feed *"encompasses
subway, bus, commuter rail, and ferry services."* Per the official MBTA GTFS
static-file reference (Source #5), `routes.txt` carries the standard GTFS
`route_type` field. RouteWise's synthetic generator already uses the
**standard GTFS route_type numeric codes** (confirmed in
`src/ingestion/generate_demo_data.py`'s `GTFS_ROUTE_TYPE` dict: tram=0,
metro=1, rail=2, bus=3, ferry=4 — these are exactly the GTFS spec's basic
route types), so the mapping mechanism is not new; only the real values need
confirming per mode:

| MBTA mode (as described on official pages) | Standard GTFS `route_type` | RouteWise mode | Confidence |
|---|---|---|---|
| Bus | 3 | `bus` | **Direct match.** Unambiguous. |
| Subway (Red, Orange, Blue Lines) | 1 (Subway/Metro) | `metro` | **Direct match.** Unambiguous. |
| Commuter Rail | 2 (Rail) | `rail` | **Direct match.** Unambiguous. |
| Ferry ("MBTA Boat") | 4 | `ferry` | **Direct match.** Unambiguous. |
| Green Line (light rail) | 0 (Tram/Light Rail), by standard GTFS convention | `tram` | **Reasonable, not certain.** GTFS `route_type=0` is literally named "Tram, Streetcar, Light rail" in the spec, and light rail is the closest real-world analog to "tram" among MBTA's services — but Green Line is not colloquially called a "tram" in Boston, and this mapping is a **judgment call being made explicitly here, not discovered as a documented MBTA-to-RouteWise equivalence**. The exact `route_type` value for MBTA's Green Line routes was **not independently confirmed against a downloaded `routes.txt`** in this stage (no GTFS ZIP was downloaded, per the "do not implement/ingest yet" instruction) — treat as "expected, to be confirmed in Stage 12." |

**Do not force this mapping further than shown.** No MBTA mode maps to more
than one RouteWise mode and vice versa; there is no ambiguous case requiring
a mode to be split or merged. The one genuine ambiguity is the `tram` label
itself (a naming/semantics judgment about Green Line light rail), not a data
availability question.

---

## 5. Historical-label feasibility

### 5.1 The current synthetic label rule (unchanged, for comparison)

From `src/utils/disruption_rules.py` (already read in Stage 11): a stop-event
is a disruption if `cancelled == True`, **or** `delay_minutes` exceeds a
**mode-specific threshold** read from `configs/synthetic_data.yaml`
(`disruption_threshold_minutes`: bus=5, tram=4, metro=3, rail=3, ferry=10
minutes). This rule is source-agnostic in its *logic* — it only needs
`delay_minutes`, `cancelled`, `transport_mode`, and a threshold table.

### 5.2 What LAMP's official Data Dictionary confirms is actually
computable per mode

Fetched and read in full (Source #8 — `mbta/lamp` repository's
`Data_Dictionary.md`). This is the single most important technical finding
of this stage:

| Mode | Dataset | Scheduled fields present | Actual/observed fields present | Verdict |
|---|---|---|---|---|
| Subway/light rail (rapid transit) | "Subway Performance Data" / "LAMP_ALL_RT_fields" | `scheduled_arrival_time`, `scheduled_departure_time`, `scheduled_travel_time` — explicitly documented as "Planned arrival/departure from GTFS schedule" | `stop_timestamp`, `move_timestamp`, `travel_time_seconds`, `dwell_time_seconds` — explicitly documented as observed status-transition timestamps | **A real `delay_minutes` (actual − scheduled) is directly derivable** for `metro` and the candidate `tram` (Green Line) mapping, at `trip_id`/`stop_id`/`route_id`/`direction_id`/`service_date` grain — exactly the grain RouteWise's `historical.py` needs. |
| Bus | "LAMP_ALL_Bus_Events" / "LAMP_RECENT_Bus_Events" | `plan_stop_departure_dt` ("Scheduled departure time at stop"), `plan_start_time`, `plan_travel_time_seconds` | `stop_arrival_dt`/`stop_departure_dt` (estimated), **and** `tm_actual_arrival_dt`/`tm_actual_departure_dt` — explicitly documented as *"Actual arrival/departure time at stop from TransitMaster"* (MBTA's bus AVL/dispatch system) | **A real `delay_minutes` is directly derivable for `bus`** — this is a stronger finding than Stage 11 Discovery's more cautious "select bus routes, unconfirmed" language; the official Data Dictionary shows a dedicated, real actual-time field sourced from the agency's own vehicle-tracking system, at `trip_id`/`stop_id`/`route_id`/`direction_id`/`service_date` grain. |
| Commuter rail | *(none found)* | — | — | **NOT FOUND.** No `LAMP_Commuter_Rail_Events` (or equivalently named) dataset appears anywhere in the official Data Dictionary's 13 documented tables. Not assumed absent from general knowledge — genuinely absent from the one authoritative field-level source checked. |
| Ferry | *(none found)* | — | — | **NOT FOUND.** Same conclusion as commuter rail — no ferry-specific performance dataset appears in the Data Dictionary. |

`cancelled`-equivalent status: not confirmed at the exact field-name level
in this pass (the Data Dictionary summary obtained did not surface an
explicit boolean cancellation field name for either dataset) — GTFS-Realtime
TripUpdates natively carries a `schedule_relationship` enum that includes a
`CANCELED` value (per the general GTFS-RT spec, referenced but not
re-verified field-by-field here since LAMP's *archived* exports were the
focus of this check, not the live TripUpdates feed itself); recommend
explicitly re-checking this specific field during Stage 12 rather than
assuming it transfers automatically from the live spec to the archived
export schema.

### 5.3 Direct comparison: current synthetic rule vs. real-world possibility

- **Where real data is available (bus, subway, light rail)**: the *shape* of
  the synthetic rule (delay-threshold-vs-mode, plus cancellation) is
  **structurally reproducible** with real fields — this is a genuine, load-
  bearing confirmation that the existing `is_disruption()` function's
  *signature* (`delay_minutes, cancelled, transport_mode, thresholds`) does
  not need to change, only its inputs' *source*.
- **Where real data is NOT available (commuter rail, ferry)**: the label
  cannot be computed at all for those two modes from the sources checked in
  this stage — this is **2 of RouteWise's 5 modes**, a materially different
  and more specific finding than Stage 11 Discovery's general "verify
  per-agency" caution.
- **The specific numeric thresholds (5/4/3/3/10 minutes per mode) must NOT
  be reused as-is.** These are documented in `synthetic_data.yaml` as
  generative *tuning* parameters chosen to produce a workable synthetic
  label balance for a demo dataset — they were never claimed to reflect real
  operational tolerances, and nothing in this verification stage supports
  carrying them over. **Recommendation for later approval** (not decided
  here, per the brief's explicit instruction not to force the mapping):
  derive real thresholds empirically from the actual real delay
  distribution per mode once ingested (e.g., a percentile-based or
  agency-published on-time-performance standard, if MBTA publishes one —
  not confirmed in this stage) rather than porting the synthetic numbers.
- **Recommended real-world label scope, pending later approval**: build the
  real disruption label **only for `bus`, `metro`, and `tram` (Green Line)**
  initially, and explicitly carry `rail` and `ferry` in the **labels-
  unavailable mode** already designed for in Stage 11 Discovery Section 6/12
  (and already implemented in `src/monitoring/performance.py`'s
  `LABEL_UNAVAILABLE_MESSAGE` path) rather than fabricating or
  approximating a label for those two modes from a different source.

---

## 6. Weather-source verification

No specific paid/commercial weather API was selected (consistent with the
brief's "do not hardcode an API key" and with this stage's official-sources
preference). Two **official, free, U.S. federal government** sources were
verified as complementary, not competing:

| Source | Role | API key | Historical depth | Fields confirmed | Geographic resolution | Licensing |
|---|---|---|---|---|---|---|
| **NWS (National Weather Service) API** — `api.weather.gov` | Current conditions + short-term forecast | **None required** — a `User-Agent` header identifying the application is mandatory instead (docs note this "will be replaced with an API key in the future") | **Limited** — explicitly not a historical archive; alerts endpoint only retains ~7 days | Temperature, wind, precipitation, visibility, general conditions (confirmed present) | ~2.5km × 2.5km gridpoints, organized by NWS Forecast Office | Explicitly stated: *"All of the information presented via the API is intended to be open data, free to use for any purpose... we do not charge any fees."* |
| **NOAA NCEI — Integrated Surface Dataset (ISD)**, accessed via NCEI Data Access services or the free AWS Registry of Open Data mirror | **Historical backfill** — this is the source that actually matches RouteWise's need to backfill a real training-data date range | CDO Web Services (a related NCEI product) requires a free token via email registration; the ISD dataset itself is also available with no token via the public AWS Registry of Open Data mirror (`registry.opendata.aws/noaa-isd/`) | **Confirmed deep** — official product description states station data extends "as far back as 1901" (with denser coverage from the 1940s/1970s onward), 35,000+ stations globally, 14,000+ active | Official ISD documentation confirms fields including temperature, **visibility**, and multiple precipitation-amount fields, at **hourly/sub-daily ("hourly and synoptic")** resolution — matches RouteWise's `weather_observations` hourly grain exactly | Station-based (point observations, not gridded) — Boston Logan International Airport is a long-running, essentially certain-to-be-included US ISD station, not independently confirmed by station ID in this stage | Standard U.S. federal government data — the CDO token-request service and NCEI Access pages are official NOAA/NCEI resources; no separate restrictive license found (not exhaustively re-verified to the same clause-by-clause depth as the MassDOT agreement, since this was a secondary verification target for this stage) |

**Recommendation, pending later approval**: use **NCEI ISD (Boston Logan
station)** for historical backfill (matches the hourly grain and multi-year
depth RouteWise's training data needs) and **NWS `api.weather.gov`** for any
future live/current-conditions use — both official, both free, both
explicitly stated as unrestricted U.S. government open data. Neither
requires a payment method or commercial license negotiation. Whichever is
implemented in Stage 12, its key/token (if any) goes through the project's
existing `.env`/`Settings` pattern (`WEATHER_API_KEY`/`WEATHER_API_URL`
placeholders already exist, unused, in `.env.example` — confirmed in Stage
11 Discovery) — **no credential of any kind was obtained, stored, or
committed during this verification stage.**

---

## 7. Final go/no-go

| Component | Verified? | Source | License/terms | Usable? | Notes |
|---|---|---|---|---|---|
| **Static GTFS** | **YES** | MBTA official GTFS page + MBTA GTFS static reference (GitHub) | MassDOT Developers License Agreement — full text read (Section 3) | **YES**, with mandatory attribution and the license's stated obligations | Covers all required files (stops/routes/trips/stop_times/calendar/calendar_dates) plus transfers.txt and shapes.txt; fares are present but in the more complex GTFS-Fares V2 format, explicitly documented as incomplete ("does not include all possible MBTA fares") |
| **GTFS-Realtime** | **YES** | MBTA GTFS-Realtime reference (GitHub) | Same agreement, per MBTA's own pages (no separate GTFS-RT terms found) | **YES**, same conditions as static GTFS | TripUpdates, VehiclePositions, ServiceAlerts all confirmed at exact CDN URLs, in 3 formats each; occupancy data explicitly partial (bus + Orange Line + some Red Line only) |
| **Historical performance** | **YES, per-mode** | MBTA Historical Performance Data page + official LAMP Data Dictionary (GitHub) | Same agreement, per MBTA's own page (no separate terms found) | **YES for bus, subway, light rail (Green Line)**; **NO/NOT FOUND for commuter rail and ferry** | This is the most consequential, most rigorously re-verified finding of this stage — see Section 5 |
| **Weather** | **YES (sources exist and are accessible); NOT YET INTEGRATED** | NWS `api.weather.gov` (current/forecast) + NOAA NCEI ISD (historical) | Both explicit U.S. federal open-data statements; no restrictive terms found | **YES** | No provider selected/implemented; no credentials obtained; recommendation given for later approval (Section 6) |

### DATA SOURCE STATUS: **PARTIAL**

Not GO, and not BLOCKED. Reasoning:

- **Not BLOCKED**: no finding in this stage contradicts MBTA/GTFS being a
  usable, well-documented, appropriately-licensed real data source for this
  project's stated purpose. The license grants use/reproduction/
  redistribution, with clear (satisfiable) obligations.
- **Not a full GO**: two conditions remain genuinely open, not because the
  evidence is negative but because this stage's own scope (verification, no
  ingestion) stops short of resolving them:
  1. **The license PDF could only be read via an archived mirror**, not a
     live fetch of the authoritative mass.gov URL (Section 3.1) — before
     Stage 12 ingestion, a human should confirm the live document is
     unchanged (or capture the current version) rather than proceeding
     solely on an archived copy.
  2. **Historical delay labels are confirmed for only 3 of 5 modes**
     (bus, metro, tram/Green-Line) — this is not a blocker to proceeding,
     but it does mean Stage 12 cannot deliver a real, fully-populated
     5-mode disruption label; it must explicitly scope to the 3 confirmed
     modes and run `rail`/`ferry` in the labels-unavailable mode, a
     **design decision requiring the same kind of explicit approval this
     report is being submitted for**, not something to decide unilaterally
     inside implementation.

---

## 8. Data limitations (recap, all sourced to Sections above)

- Fares: present but in GTFS-Fares V2 format, explicitly documented by MBTA
  as incomplete relative to all real MBTA fares (Section 1, source #5).
- Massport shuttles excluded from GTFS static since Feb 2019 (Section 2).
- Occupancy/crowding real-time data limited to bus + Orange Line + some Red
  Line cars (Section 3).
- Non-revenue-trip flagging in GTFS-Realtime explicitly incomplete for light
  rail (Section 3).
- Commuter rail and ferry: no confirmed historical scheduled-vs-actual
  performance data source found (Section 5) — the single largest limitation
  of this candidate source.
- `cancelled`-equivalent field name not confirmed at the LAMP-export level
  (Section 5.2) — flagged for direct re-check in Stage 12, not assumed.
- Green Line's exact GTFS `route_type` value not independently confirmed
  against a downloaded feed (Section 4) — no GTFS ZIP was downloaded in this
  stage, per instruction.
- Rate limits and storage/caching terms: not found in any official source
  checked (Section 3.7–3.8) — status is "not documented," not "none exist."

## 9. Risks

- **Legal-text access risk**: the governing license was read from an
  archived snapshot, not a live authoritative fetch (Section 3.1) — low
  probability the text has materially changed (footer-dated 2009, apparently
  stable for over a decade), but not zero, and worth a direct re-check
  before Stage 12 begins.
- **Interpretation risk**: applying a 2009-drafted agreement's broad "Data"
  definition to 2020s-era products (GTFS-Realtime, LAMP) it could not have
  named explicitly is a reasonable reading supported by MBTA's own current
  pages pointing to this exact document for all three products — but it is
  an interpretation, not a product-specific clause, and should be named as
  such in any downstream documentation (already done throughout this
  report).
- **Feed volatility risk**: §5.2's "MassDOT reserves the right to make
  changes... without notice" combined with GTFS being "updated several times
  a month" (confirmed, Section 2) means Stage 12 must pin/version every
  downloaded snapshot (already RouteWise's established DVC discipline,
  Section 3.12) rather than treat any single download as permanently
  representative.
- **Coverage risk**: the 2-of-5-modes gap in historical labels (Section 5)
  is a real design constraint on what Stage 12 can honestly claim to model,
  not merely a data-quality nuisance.
- **Access-method risk found and worked around during this very stage**:
  mass.gov's bot/edge protection blocked automated fetches of a public PDF —
  this is worth noting as a practical Stage 12 concern too: any automated
  ingestion script hitting mass.gov-hosted (as opposed to mbta.com- or
  cdn.mbta.com-hosted) resources should expect to need a real browser-like
  client or a documented API path, not a bare HTTP GET.

## 10. Final recommendation

**Proceed to Stage 12 planning for `bus`, `metro`, and `tram` (Green Line)
with real GTFS static + GTFS-Realtime + LAMP historical performance data,
under the MassDOT Developers License Agreement's stated terms (attribution
required, redistribution permitted, no ownership claims, no MassDOT
branding) — contingent on**:

1. A direct, human confirmation that the live mass.gov-hosted license text
   matches what was read here (Section 3.1/9), before any real ingestion.
2. Explicit approval of the recommended mode/label scope (3 modes with real
   labels; `rail` and `ferry` in labels-unavailable mode) — this is a
   product/design decision, not purely a technical one, and per the brief's
   own instruction ("If the existing disruption rule is inappropriate for
   real data, explicitly recommend a real-world label definition for later
   approval") is being surfaced here for approval, not decided unilaterally.
3. A real-world disruption-threshold definition (Section 5.3) to be derived
   from the actual ingested delay distribution once available, not ported
   from the synthetic config — also pending approval, not decided here.
4. A specific weather-provider choice between the two verified official
   NOAA/NWS options (Section 6) — both are viable; selecting one is a small
   remaining decision, not a blocker.

No code was written. No credentials were obtained or stored. No data was
downloaded or ingested, per the brief's explicit instruction.

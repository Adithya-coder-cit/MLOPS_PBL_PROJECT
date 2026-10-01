"""Stage 11B §1/§10: loaders for the official MBTA LAMP historical
performance exports (verified field-by-field against the official Data
Dictionary in Stage 11A -- https://github.com/mbta/lamp/blob/main/Data_Dictionary.md).

Two real, distinct datasets, each with its own schema (not unified here --
src.ingestion.historical.normalize is where they converge onto the
canonical contract):

- Subway/rapid-transit performance: one Parquet file per service_date,
  listed in a public index CSV.
- Bus performance: a single rolling-window Parquet
  ("LAMP_RECENT_Bus_Events.parquet" -- verified as a 7-day window at
  Stage 11B time) plus, as of Stage 11F, a windowed extract of the full
  deep-history archive ("LAMP_ALL_Bus_Events.parquet" -- confirmed real
  and downloadable, ~7.4GB / ~94.4M rows, covering service_date
  2025-12-29 through 2026-09-29 at Stage 11F verification time; see
  download_bus_archive_window below for why only a date-filtered window
  of it is ever kept on disk/tracked in DVC, never the full file).
"""
from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from src.ingestion.common.contracts import DATASET_TYPE_REAL
from src.ingestion.common.provenance import MBTA_LICENSE_REFERENCE, ProvenanceRecord, build_provenance
from src.ingestion.gtfs.download import USER_AGENT

logger = logging.getLogger("routewise.ingestion.historical.mbta_lamp")


def fetch_subway_index(index_url: str, timeout: int = 30) -> pd.DataFrame:
    """The public CSV listing every available subway-performance
    service_date and its Parquet URL."""
    response = requests.get(index_url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    from io import StringIO

    return pd.read_csv(StringIO(response.text))


def download_subway_day(file_url: str, dest_path: Path, timeout: int = 60) -> ProvenanceRecord:
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(file_url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    dest_path.write_bytes(response.content)
    return build_provenance(
        provider="MBTA LAMP", source_url=file_url, downloaded_path=dest_path,
        license_reference=MBTA_LICENSE_REFERENCE, dataset_type=DATASET_TYPE_REAL,
        geographic_coverage="MBTA rapid transit (subway + light rail)",
        temporal_coverage="single service_date",
    )


def download_bus_events(url: str, dest_path: Path, timeout: int = 300) -> ProvenanceRecord:
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading bus events from %s (this file is tens to hundreds of MB)", url)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    response.raise_for_status()
    dest_path.write_bytes(response.content)
    return build_provenance(
        provider="MBTA LAMP", source_url=url, downloaded_path=dest_path,
        license_reference=MBTA_LICENSE_REFERENCE, dataset_type=DATASET_TYPE_REAL,
        geographic_coverage="MBTA bus network",
        temporal_coverage="rolling recent window (verified 7 days at Stage 11B time; "
                           "re-verify at ingestion time, MBTA does not document a fixed retention period)",
        notes="LAMP_RECENT_Bus_Events.parquet -- the bounded rolling-window export. See "
              "download_bus_archive_window for the Stage 11F deep-history counterpart.",
    )


class _RangeHTTPFile:
    """Minimal pyarrow-NativeFile-compatible random-access reader backed
    by plain `requests.Session` Range GETs -- no caching/read-ahead
    cleverness, so behavior (and the number/size of real HTTP requests
    issued) is fully predictable. Used only to read the LAMP_ALL_Bus_Events
    archive's own Parquet footer (a few MB) and specific row groups
    without ever downloading the full ~7.4GB file.
    """

    def __init__(self, url: str, size: int, session: requests.Session, timeout: int = 240, max_retries: int = 5):
        self.url = url
        self._size = size
        self.pos = 0
        self.session = session
        self.timeout = timeout
        self.max_retries = max_retries

    def seek(self, pos: int, whence: int = 0) -> int:
        if whence == 0:
            self.pos = pos
        elif whence == 1:
            self.pos += pos
        elif whence == 2:
            self.pos = self._size + pos
        return self.pos

    def tell(self) -> int:
        return self.pos

    def read(self, nbytes: int | None = None) -> bytes:
        if nbytes is None or self.pos + nbytes > self._size:
            nbytes = self._size - self.pos
        if nbytes <= 0:
            return b""
        start, end = self.pos, self.pos + nbytes - 1

        # This environment's real, measured bandwidth to this host is
        # severely constrained (~0.4-0.5 MB/s, observed to vary and
        # occasionally stall entirely for a request) -- a single failed
        # Range GET must never lose all prior progress, so every read is
        # retried with backoff rather than propagating the first
        # transient timeout/connection error.
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                r = self.session.get(self.url, headers={"Range": f"bytes={start}-{end}", "User-Agent": USER_AGENT},
                                      timeout=self.timeout)
                r.raise_for_status()
                data = r.content
                self.pos += len(data)
                return data
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                last_exc = exc
                wait = min(60, 5 * attempt)
                logger.warning("Range GET [%d-%d] attempt %d/%d failed (%s) -- retrying in %ds",
                               start, end, attempt, self.max_retries, exc, wait)
                time.sleep(wait)
        raise ConnectionError(f"Range GET [{start}-{end}] failed after {self.max_retries} attempts") from last_exc

    def size(self) -> int:
        return self._size

    def close(self) -> None:
        pass

    @property
    def closed(self) -> bool:
        return False

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False


def download_bus_archive_window(
    url: str, dest_path: Path, min_service_date: date, max_service_date: date, timeout: int = 240,
) -> tuple[ProvenanceRecord, dict]:
    """Stage 11F: fetches ONLY the row groups of the full
    LAMP_ALL_Bus_Events.parquet archive (confirmed real via HTTP HEAD --
    ~7.39GB, ~94.4M rows, one row group per service_date, 275 row groups
    spanning 2025-12-29..2026-09-29 at verification time) whose
    service_date falls within [min_service_date, max_service_date],
    identified from the archive's own Parquet row-group statistics (read
    via a small Range request against the file's footer -- never the
    whole file). Writes ONLY the filtered window to dest_path as a
    normal, compact local Parquet file.

    This keeps what's actually downloaded/tracked in DVC proportional to
    what's used (one window, not the full multi-year-capable archive) --
    the full file is never held on disk, in full, at any point.

    This environment's real, measured outbound bandwidth to this host is
    severely constrained (~0.4-0.5 MB/s) and occasionally stalls a
    request entirely -- each row group is checkpointed to its own file
    under `<dest_path>.rowgroup_cache/` the moment it's fetched, and an
    already-checkpointed row group is loaded from disk (not re-fetched)
    on a subsequent call. A process crash/timeout partway through loses
    at most the row group in flight, never prior progress. The cache
    directory is removed once the final combined file is written.

    Returns (provenance, window_summary); window_summary documents
    exactly which row groups/dates were pulled, the archive's own total
    size/date range (for honest "this is a partial extract" reporting),
    and is written into the provenance record's `notes` field.
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    cache_dir = dest_path.parent / f"{dest_path.stem}.rowgroup_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    import pyarrow as pa
    import pyarrow.parquet as pq

    session = requests.Session()
    head = session.head(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    head.raise_for_status()
    archive_size = int(head.headers["Content-Length"])

    remote = _RangeHTTPFile(url, archive_size, session, timeout=timeout)
    pf = pq.ParquetFile(remote)
    col_idx = pf.schema_arrow.get_field_index("service_date")

    qualifying = []
    for i in range(pf.num_row_groups):
        stats = pf.metadata.row_group(i).column(col_idx).statistics
        if stats is not None and stats.has_min_max and stats.max >= min_service_date and stats.min <= max_service_date:
            qualifying.append(i)

    logger.info("LAMP_ALL_Bus_Events.parquet: %d/%d row groups fall in [%s, %s]",
                len(qualifying), pf.num_row_groups, min_service_date, max_service_date)

    tables = []
    for n, i in enumerate(qualifying, 1):
        checkpoint_path = cache_dir / f"rowgroup_{i:04d}.parquet"
        if checkpoint_path.exists():
            tables.append(pq.read_table(checkpoint_path))
            logger.info("  row group %d/%d (archive index %d): reused from cache", n, len(qualifying), i)
            continue
        table = pf.read_row_group(i)
        pq.write_table(table, checkpoint_path)
        tables.append(table)
        logger.info("  fetched row group %d/%d (archive index %d)", n, len(qualifying), i)

    combined = pa.concat_tables(tables) if tables else pa.Table.from_pydict({})
    pq.write_table(combined, dest_path)

    import shutil
    shutil.rmtree(cache_dir, ignore_errors=True)

    window_summary = {
        "archive_url": url,
        "archive_total_size_bytes": archive_size,
        "archive_num_row_groups": pf.num_row_groups,
        "extracted_row_groups": qualifying,
        "extracted_rows": combined.num_rows,
        "requested_window": [str(min_service_date), str(max_service_date)],
    }

    provenance = build_provenance(
        provider="MBTA LAMP", source_url=url, downloaded_path=dest_path,
        license_reference=MBTA_LICENSE_REFERENCE, dataset_type=DATASET_TYPE_REAL,
        geographic_coverage="MBTA bus network",
        temporal_coverage=f"windowed extract [{min_service_date}, {max_service_date}] of the full "
                           f"archive (archive itself spans a much longer real period; only this window "
                           f"was downloaded -- see notes)",
        notes=(
            f"LAMP_ALL_Bus_Events.parquet is a real, confirmed-downloadable {archive_size / 1e9:.2f}GB "
            f"archive with {pf.num_row_groups} row groups (one per service_date). Only "
            f"{len(qualifying)} row groups matching the requested window were fetched, via HTTP Range "
            f"requests against each row group's real byte offsets (read from the archive's own Parquet "
            f"footer) -- the full archive was never downloaded in full. This file "
            f"({combined.num_rows} rows) is that windowed extract, not the complete archive."
        ),
    )
    return provenance, window_summary


def load_subway_performance(parquet_paths: list[Path]) -> pd.DataFrame:
    frames = [pd.read_parquet(p) for p in parquet_paths]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_bus_events(parquet_path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    """`columns` (optional column projection) exists purely for memory
    reasons: the multi-million-row archive window has 59 columns, most
    of them large_string, and converting all of them to pandas objects
    would require far more memory than the file's on-disk size implies
    (Python string-object overhead per cell). Never used to drop fields
    normalize_bus_events actually reads -- callers must pass every
    column that downstream normalization needs.
    """
    return pd.read_parquet(parquet_path, columns=columns)


def load_bus_events_multi(parquet_paths: list[Path]) -> pd.DataFrame:
    """Stage 11F: loads and concatenates multiple bus-event Parquet files
    (e.g. the RECENT rolling window + the ALL-archive windowed extract)
    WITHOUT deduplicating -- deduplication is the caller's explicit,
    documented responsibility (src.ingestion.historical.normalize
    .deduplicate_bus_events), never silent here.
    """
    frames = [pd.read_parquet(p) for p in parquet_paths if Path(p).exists()]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

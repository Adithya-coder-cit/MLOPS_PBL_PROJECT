"""Stage 11B §7: correct GTFS extended-time handling.

GTFS `arrival_time`/`departure_time` use an EXTENDED clock -- hours may
exceed 23 (e.g. "25:15:00") specifically to represent a trip that starts
one service day and continues past midnight without changing
`service_date`. The synthetic generator's `minutes_to_hhmm()`
(src/ingestion/generate_demo_data.py) wraps with `% (24*60)`, which is
NOT GTFS-correct -- it was adequate only because no synthetic trip
actually depended on the distinction. This module replaces that
approach for real data: hours are preserved past 24, and a service date
+ extended time combination is resolved to a genuine timezone-aware
instant via the feed's documented timezone (MBTA: America/New_York,
from agency.txt's agency_timezone -- never hardcoded elsewhere).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_TIME_RE = re.compile(r"^(\d{1,3}):([0-5]\d):([0-5]\d)$")


def parse_gtfs_time_to_minutes(time_str: str | float | None) -> int | None:
    """'HH:MM:SS' (hours may exceed 23) -> minutes since midnight of the
    service_date (may exceed 1440). None for missing/blank/unparseable
    input -- never silently coerced to 0."""
    if time_str is None:
        return None
    if isinstance(time_str, float):
        return None  # NaN from pandas
    time_str = time_str.strip()
    if not time_str:
        return None
    match = _TIME_RE.match(time_str)
    if not match:
        return None
    hours, minutes, seconds = (int(g) for g in match.groups())
    return hours * 60 + minutes + (1 if seconds >= 30 else 0)


def parse_gtfs_time_to_seconds(time_str: str | float | None) -> int | None:
    """Same as parse_gtfs_time_to_minutes but exact, in seconds since
    midnight -- used where sub-minute precision matters (e.g. delay
    computation against LAMP's second-resolution timestamps)."""
    if time_str is None or isinstance(time_str, float):
        return None
    time_str = time_str.strip()
    if not time_str:
        return None
    match = _TIME_RE.match(time_str)
    if not match:
        return None
    hours, minutes, seconds = (int(g) for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def gtfs_time_to_datetime(service_date: date, time_str: str | float | None, feed_timezone: str) -> datetime | None:
    """service_date + an extended-clock GTFS time string -> a genuine,
    timezone-aware datetime. Hours >= 24 correctly roll into the next
    calendar day (service_date stays fixed, matching GTFS's own model of
    "service day", not the wall-clock day) -- this is the direct fix for
    the synthetic generator's modulo-24 wraparound.
    """
    seconds = parse_gtfs_time_to_seconds(time_str)
    if seconds is None:
        return None
    tz = ZoneInfo(feed_timezone)
    midnight = datetime(service_date.year, service_date.month, service_date.day, tzinfo=tz)
    return midnight + timedelta(seconds=seconds)


def seconds_since_midnight_to_datetime(
    service_date: date, seconds: float | None, feed_timezone: str,
) -> datetime | None:
    """Same extended-clock semantics as gtfs_time_to_datetime, but for a
    numeric seconds-since-midnight value (as LAMP's subway performance
    export uses for scheduled_arrival_time/scheduled_departure_time)
    rather than an 'HH:MM:SS' string."""
    if seconds is None or (isinstance(seconds, float) and seconds != seconds):  # NaN check without numpy import
        return None
    tz = ZoneInfo(feed_timezone)
    midnight = datetime(service_date.year, service_date.month, service_date.day, tzinfo=tz)
    return midnight + timedelta(seconds=float(seconds))


def is_midnight_crossing(time_str: str | float | None) -> bool:
    """True if this scheduled time is on the "past midnight" portion of
    an extended-clock service day (hour >= 24) -- a real, documented
    property of the source schedule, not an error."""
    seconds = parse_gtfs_time_to_seconds(time_str)
    return seconds is not None and seconds >= 24 * 3600

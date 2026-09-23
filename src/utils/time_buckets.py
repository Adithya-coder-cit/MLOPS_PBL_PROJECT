"""Time-of-day / day-period bucketing shared by data generation and feature
engineering, so the definition of "peak/off_peak/night" never diverges
between the two.
"""
from __future__ import annotations


def hhmm_to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")[:2]
    return int(h) * 60 + int(m)


def classify_day_period(minute_of_day: int, peak_windows: list[list[str]], night_window: list[str]) -> str:
    for start, end in peak_windows:
        if hhmm_to_minutes(start) <= minute_of_day < hhmm_to_minutes(end):
            return "peak"
    night_start, night_end = hhmm_to_minutes(night_window[0]), hhmm_to_minutes(night_window[1])
    if night_start > night_end:  # wraps past midnight
        if minute_of_day >= night_start or minute_of_day < night_end:
            return "night"
    elif night_start <= minute_of_day < night_end:
        return "night"
    return "off_peak"


def time_of_day_bucket(hour: int, bucket_hours: int = 4) -> str:
    """Coarse fixed-width bucket, independent of the peak/off_peak/night rule above."""
    start = (hour // bucket_hours) * bucket_hours
    end = start + bucket_hours
    return f"{start:02d}-{end:02d}"

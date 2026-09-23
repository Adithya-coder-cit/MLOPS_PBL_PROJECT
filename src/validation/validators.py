"""Individual validation checks. Each returns a list[ValidationIssue] and
never mutates or repairs the input DataFrame — validation only observes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.validation.schemas import ALL_SCHEMAS, TableSchema

ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"


@dataclass
class ValidationIssue:
    level: str  # ERROR | WARNING | INFO
    table: str
    check: str
    message: str
    count: int = 0

    def to_dict(self) -> dict:
        return {"level": self.level, "table": self.table, "check": self.check,
                "message": self.message, "count": self.count}


def check_required_columns(df: pd.DataFrame, schema: TableSchema) -> list[ValidationIssue]:
    missing = [c for c in schema.required_columns if c not in df.columns]
    if missing:
        return [ValidationIssue(ERROR, schema.name, "required_columns",
                                 f"Missing required columns: {missing}", len(missing))]
    return []


def check_nulls(df: pd.DataFrame, schema: TableSchema) -> list[ValidationIssue]:
    issues = []
    for col in schema.not_nullable:
        if col not in df.columns:
            continue
        n_null = int(df[col].isna().sum())
        if n_null > 0:
            issues.append(ValidationIssue(ERROR, schema.name, "nulls",
                                           f"Column '{col}' has {n_null} null value(s) but is required", n_null))
    return issues


def check_duplicates(df: pd.DataFrame, schema: TableSchema) -> list[ValidationIssue]:
    issues = []
    exact_dupes = int(df.duplicated().sum())
    if exact_dupes > 0:
        issues.append(ValidationIssue(WARNING, schema.name, "exact_duplicate_rows",
                                       f"{exact_dupes} fully duplicate row(s) found", exact_dupes))
    if schema.primary_key and all(c in df.columns for c in schema.primary_key):
        pk_dupes = int(df.duplicated(subset=schema.primary_key).sum())
        if pk_dupes > 0:
            issues.append(ValidationIssue(ERROR, schema.name, "primary_key_uniqueness",
                                           f"{pk_dupes} row(s) violate primary key uniqueness on {schema.primary_key}",
                                           pk_dupes))
    return issues


def check_foreign_keys(
    df: pd.DataFrame, schema: TableSchema, ref_tables: dict[str, pd.DataFrame]
) -> list[ValidationIssue]:
    issues = []
    for col, (ref_table, ref_col) in schema.foreign_keys.items():
        if col not in df.columns or ref_table not in ref_tables:
            continue
        ref_values = set(ref_tables[ref_table][ref_col])
        orphans = ~df[col].isin(ref_values)
        n_orphans = int(orphans.sum())
        if n_orphans > 0:
            issues.append(ValidationIssue(
                ERROR, schema.name, "foreign_key_integrity",
                f"{n_orphans} row(s) in '{col}' reference missing {ref_table}.{ref_col}", n_orphans,
            ))
    return issues


def check_categorical_values(df: pd.DataFrame, schema: TableSchema) -> list[ValidationIssue]:
    issues = []
    for col, allowed in schema.categorical.items():
        if col not in df.columns:
            continue
        observed = set(df[col].dropna().astype(str))
        invalid = observed - allowed
        if invalid:
            n_bad = int(df[col].astype(str).isin(invalid).sum())
            issues.append(ValidationIssue(ERROR, schema.name, "categorical_values",
                                           f"Column '{col}' has invalid values {invalid} (allowed: {allowed})", n_bad))
    return issues


def check_numeric_ranges(df: pd.DataFrame, schema: TableSchema) -> list[ValidationIssue]:
    issues = []
    for col, (lo, hi) in schema.numeric_ranges.items():
        if col not in df.columns:
            continue
        out_of_range = df[col].notna() & ((df[col] < lo) | (df[col] > hi))
        n_bad = int(out_of_range.sum())
        if n_bad > 0:
            issues.append(ValidationIssue(ERROR, schema.name, "numeric_range",
                                           f"Column '{col}' has {n_bad} value(s) outside plausible range [{lo}, {hi}]",
                                           n_bad))
    return issues


def check_timestamp_validity(df: pd.DataFrame, schema: TableSchema, timestamp_cols: list[str]) -> list[ValidationIssue]:
    issues = []
    for col in timestamp_cols:
        if col not in df.columns:
            continue
        parsed = pd.to_datetime(df[col], errors="coerce")
        n_unparseable = int(parsed.isna().sum() - df[col].isna().sum())
        if n_unparseable > 0:
            issues.append(ValidationIssue(ERROR, schema.name, "timestamp_validity",
                                           f"Column '{col}' has {n_unparseable} unparseable timestamp(s)",
                                           n_unparseable))
    return issues


def check_disruption_label_consistency(df: pd.DataFrame, expected_noise_rate: float = 0.03,
                                        tolerance: float = 0.12) -> list[ValidationIssue]:
    """Soft statistical check: cancelled trips should usually be flagged as
    disruptions. Some mismatch is expected by design (intentional label
    noise injection, see configs/synthetic_data.yaml disruption_noise), so
    this is a WARNING, not an ERROR, unless the mismatch is far beyond the
    documented noise rate.
    """
    if not {"cancelled", "disruption_flag"} <= set(df.columns):
        return []
    cancelled = df["cancelled"].astype(bool)
    if cancelled.sum() == 0:
        return []
    mismatch_rate = float((cancelled & (df["disruption_flag"] != 1)).sum() / cancelled.sum())
    if mismatch_rate > expected_noise_rate + tolerance:
        return [ValidationIssue(
            WARNING, "historical_operational_records", "disruption_label_consistency",
            f"{mismatch_rate:.1%} of cancelled trips are NOT flagged as disruptions "
            f"(expected ~{expected_noise_rate:.0%} from documented label noise)",
            int((cancelled & (df["disruption_flag"] != 1)).sum()),
        )]
    return []


def check_demo_metadata(raw_dir: Path) -> list[ValidationIssue]:
    card_path = raw_dir / "DATASET_CARD.md"
    if not card_path.exists():
        return [ValidationIssue(ERROR, "dataset", "demo_metadata_present",
                                 f"{card_path} is missing — dataset cannot be confirmed as DEVELOPMENT/DEMO", 1)]
    text = card_path.read_text(encoding="utf-8")
    if "DEVELOPMENT/DEMO" not in text or "SYNTHETIC" not in text:
        return [ValidationIssue(ERROR, "dataset", "demo_metadata_banner",
                                 f"{card_path} does not contain the required DEVELOPMENT/DEMO + SYNTHETIC banner", 1)]
    return [ValidationIssue(INFO, "dataset", "demo_metadata_banner", "DEVELOPMENT/DEMO banner confirmed present", 0)]


def run_table_checks(df: pd.DataFrame, schema: TableSchema, ref_tables: dict[str, pd.DataFrame],
                      timestamp_cols: list[str] | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues += check_required_columns(df, schema)
    if any(i.level == ERROR for i in issues):
        # Can't safely run the rest of the checks without the required columns.
        return issues
    issues += check_nulls(df, schema)
    issues += check_duplicates(df, schema)
    issues += check_foreign_keys(df, schema, ref_tables)
    issues += check_categorical_values(df, schema)
    issues += check_numeric_ranges(df, schema)
    if timestamp_cols:
        issues += check_timestamp_validity(df, schema, timestamp_cols)
    return issues


def run_all_validations(tables: dict[str, pd.DataFrame], raw_dir: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    timestamp_cols_by_table = {
        "historical_operational_records": ["scheduled_time", "actual_time", "service_date"],
        "weather_observations": ["timestamp"],
    }
    for name, schema in ALL_SCHEMAS.items():
        if name not in tables:
            issues.append(ValidationIssue(ERROR, name, "table_present", f"Table '{name}' was not loaded", 1))
            continue
        issues += run_table_checks(tables[name], schema, tables, timestamp_cols_by_table.get(name))

    if "historical_operational_records" in tables:
        issues += check_disruption_label_consistency(tables["historical_operational_records"])

    issues += check_demo_metadata(raw_dir)
    return issues

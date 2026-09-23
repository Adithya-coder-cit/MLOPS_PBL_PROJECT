"""Unit tests for the validation layer, plus an integration check against
the real generated raw dataset (skipped if not generated).
"""
import pandas as pd
import pytest

from src.ingestion.load_raw import RAW_DIR, load_raw_tables
from src.validation.report import ValidationError, build_report, raise_if_errors
from src.validation.schemas import TableSchema
from src.validation.validators import (
    ERROR,
    check_categorical_values,
    check_duplicates,
    check_foreign_keys,
    check_nulls,
    check_numeric_ranges,
    check_required_columns,
    run_all_validations,
)


def test_check_required_columns_flags_missing():
    schema = TableSchema(name="t", required_columns=["a", "b"])
    df = pd.DataFrame({"a": [1]})
    issues = check_required_columns(df, schema)
    assert len(issues) == 1
    assert issues[0].level == ERROR


def test_check_nulls_flags_required_nulls():
    schema = TableSchema(name="t", required_columns=["a"], not_nullable=["a"])
    df = pd.DataFrame({"a": [1, None, 3]})
    issues = check_nulls(df, schema)
    assert len(issues) == 1
    assert issues[0].count == 1


def test_check_duplicates_flags_pk_violation():
    schema = TableSchema(name="t", required_columns=["id"], primary_key=["id"])
    df = pd.DataFrame({"id": [1, 1, 2]})
    issues = check_duplicates(df, schema)
    pk_issues = [i for i in issues if i.check == "primary_key_uniqueness"]
    assert len(pk_issues) == 1
    assert pk_issues[0].level == ERROR


def test_check_foreign_keys_flags_orphans():
    schema = TableSchema(name="t", required_columns=["ref_id"], foreign_keys={"ref_id": ("parent", "id")})
    df = pd.DataFrame({"ref_id": [1, 2, 99]})
    ref_tables = {"parent": pd.DataFrame({"id": [1, 2]})}
    issues = check_foreign_keys(df, schema, ref_tables)
    assert len(issues) == 1
    assert issues[0].count == 1


def test_check_categorical_values_flags_invalid():
    schema = TableSchema(name="t", required_columns=["mode"], categorical={"mode": {"bus", "rail"}})
    df = pd.DataFrame({"mode": ["bus", "spaceship"]})
    issues = check_categorical_values(df, schema)
    assert len(issues) == 1
    assert issues[0].count == 1


def test_check_numeric_ranges_flags_out_of_range():
    schema = TableSchema(name="t", required_columns=["x"], numeric_ranges={"x": (0.0, 10.0)})
    df = pd.DataFrame({"x": [5.0, -1.0, 999.0]})
    issues = check_numeric_ranges(df, schema)
    assert len(issues) == 1
    assert issues[0].count == 2


def test_raise_if_errors_raises_on_errors():
    report = build_report([])
    report["summary"]["errors"] = 1
    report["errors"] = [{"table": "t", "check": "c", "message": "m", "level": ERROR, "count": 1}]
    with pytest.raises(ValidationError):
        raise_if_errors(report)


def test_raise_if_errors_passes_when_clean():
    report = build_report([])
    raise_if_errors(report)  # should not raise


RAW_FILES_EXIST = (RAW_DIR / "gtfs" / "stops.csv").exists()


@pytest.mark.skipif(not RAW_FILES_EXIST, reason="raw dataset not generated yet")
def test_real_raw_dataset_passes_validation():
    tables = load_raw_tables(RAW_DIR)
    issues = run_all_validations(tables, RAW_DIR)
    errors = [i for i in issues if i.level == ERROR]
    assert errors == [], f"Unexpected validation errors on real raw data: {errors}"

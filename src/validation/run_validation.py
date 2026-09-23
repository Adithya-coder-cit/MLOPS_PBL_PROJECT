"""Validation entry point: load raw tables, run every check, write the
report, and raise ValidationError if any ERROR-level issue exists.

Run: python -m src.validation.run_validation
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.ingestion.load_raw import RAW_DIR, load_raw_tables
from src.validation.report import build_report, raise_if_errors, write_report
from src.validation.validators import run_all_validations

logger = logging.getLogger("routewise.validation")


def main(raw_dir: Path = RAW_DIR, report_path: Path = Path("data/interim/raw_validation_report.json")) -> dict:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    logger.info("Loading raw tables from %s", raw_dir)
    tables = load_raw_tables(raw_dir)

    logger.info("Running validation checks")
    issues = run_all_validations(tables, raw_dir)
    report = build_report(issues)
    write_report(report, report_path)

    logger.info(
        "Validation summary: %d error(s), %d warning(s), %d info — report at %s",
        report["summary"]["errors"], report["summary"]["warnings"], report["summary"]["info"], report_path,
    )
    raise_if_errors(report)
    logger.info("Validation PASSED (no errors)")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--report-path", default="data/interim/raw_validation_report.json")
    args = parser.parse_args()
    main(Path(args.raw_dir), Path(args.report_path))

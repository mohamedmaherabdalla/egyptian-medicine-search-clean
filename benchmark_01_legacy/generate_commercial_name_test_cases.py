#!/usr/bin/env python3
"""Regenerate commercial-name stress-test CSV artifacts.

Problem: the repository previously contained expanded CSV artifacts without the
code that produced them; this script makes generation reproducible on the
non-main branch.
Inputs: canonical catalog CSV and the original manually curated seed CSV.
Outputs: expanded test-case CSV, inside/outside/semi-outside split CSVs, and
machine-readable summary JSON files.
Edge cases: missing source files, malformed rows, categories producing fewer
than target rows, duplicate rows, exact-like generated rows, and hard-case ratio
below the configured threshold.
Failure modes: any validation failure raises and prevents overwriting outputs;
partial writes only happen after all cases validate successfully.
Algorithm choice: a deterministic rule-based generator was chosen over random
noise injection because medical-search evaluation cases must be explainable,
auditable, and stable across runs.
"""

from __future__ import annotations

import logging
from pathlib import Path

from test_case_generation.catalog_io import CatalogIndex, load_catalog, load_seed_cases
from test_case_generation.config import (
    CATALOG_CSV_PATH,
    EXPANDED_CASES_PATH,
    EXPANDED_SUMMARY_PATH,
    INSIDE_CASES_PATH,
    OUTSIDE_CASES_PATH,
    SCOPE_SUMMARY_PATH,
    SEED_CASES_PATH,
    SEMI_OUTSIDE_CASES_PATH,
)
from test_case_generation.generators import generate_cases
from test_case_generation.splitters import split_by_scope
from test_case_generation.validators import (
    summary_payload,
    validate_cases,
    write_cases,
    write_summary,
)


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    """Run generation, validation, and artifact writes."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logger.info("Loading catalog from %s", CATALOG_CSV_PATH)
    catalog = load_catalog(CATALOG_CSV_PATH)
    index = CatalogIndex(catalog)
    logger.info("Loading seed cases from %s", SEED_CASES_PATH)
    seed_cases = load_seed_cases(SEED_CASES_PATH)
    cases = generate_cases(seed_cases, index)
    summary = validate_cases(cases)
    splits = split_by_scope(cases)
    write_cases(EXPANDED_CASES_PATH, cases)
    write_cases(INSIDE_CASES_PATH, splits["inside"])
    write_cases(SEMI_OUTSIDE_CASES_PATH, splits["semi_outside"])
    write_cases(OUTSIDE_CASES_PATH, splits["outside"])
    payload = summary_payload(summary, cases)
    write_summary(EXPANDED_SUMMARY_PATH, payload)
    write_summary(
        SCOPE_SUMMARY_PATH,
        {
            "source_file": str(EXPANDED_CASES_PATH.relative_to(PROJECT_ROOT)),
            "scopes": payload,
        },
    )
    logger.info("Wrote %d total cases", summary.total_cases)
    logger.info("Hard/extreme ratio %.3f", summary.hard_case_ratio)


if __name__ == "__main__":
    main()

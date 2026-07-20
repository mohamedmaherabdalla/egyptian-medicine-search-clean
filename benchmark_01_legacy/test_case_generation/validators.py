"""Validation and output helpers for generated commercial-name cases.

Problem: generated evaluation data must be internally consistent before it is
used to judge a medical search engine.
Inputs: final TestCase rows and scope splits.
Outputs: ValidationSummary plus CSV/JSON files.
Edge cases: empty files, duplicate rows, unknown labels, categories without
scope, and hard-case distribution below the configured minimum.
Failure modes: validation raises ValueError with a concrete reason; no caller
should write partial data after a validation failure.
Algorithm choice: explicit counters and schema checks are used over ad hoc
spreadsheet inspection because this generator runs in CI-like terminal workflows.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .config import CSV_FIELDNAMES, MIN_HARD_OR_EXTREME_RATIO
from .models import Scope, TestCase, ValidationSummary
from .normalization import compact_key
from .splitters import scope_for_category


VALID_DIFFICULTIES = {"EASY", "MEDIUM", "HARD", "EXTREME"}
VALID_DANGERS = {"SAFE", "CAUTION", "DANGEROUS"}


def validate_cases(cases: list[TestCase]) -> ValidationSummary:
    """Validate generated cases and return summary statistics.

    Args:
        cases: Generated and seed cases.

    Returns:
        Validation summary.

    Raises:
        ValueError: If any case is malformed or distribution gates fail.
    """

    if not cases:
        raise ValueError("cannot validate an empty test-case suite")
    _validate_rows(cases)
    _validate_no_duplicate_rows(cases)
    summary = _build_summary(cases)
    if summary.hard_case_ratio < MIN_HARD_OR_EXTREME_RATIO:
        raise ValueError(
            f"hard/extreme ratio {summary.hard_case_ratio:.3f} is below "
            f"required {MIN_HARD_OR_EXTREME_RATIO:.3f}"
        )
    return summary


def write_cases(path: Path, cases: list[TestCase]) -> None:
    """Write cases to a CSV path using the fixed schema."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for case in cases:
            writer.writerow(case.to_csv_row())


def write_summary(path: Path, payload: dict[str, Any]) -> None:
    """Write a machine-readable JSON summary."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summary_payload(summary: ValidationSummary, cases: list[TestCase]) -> dict[str, Any]:
    """Build JSON-serializable summary payload for generated data."""

    return {
        "total_cases": summary.total_cases,
        "hard_case_ratio": summary.hard_case_ratio,
        "category_counts": summary.category_counts,
        "difficulty_counts": summary.difficulty_counts,
        "danger_counts": summary.danger_counts,
        "scope_counts": summary.scope_counts,
        "exact_compact_match_count": _exact_compact_match_count(cases),
    }


def _validate_rows(cases: list[TestCase]) -> None:
    for index, case in enumerate(cases, start=1):
        if not case.input_value.strip() or not case.expected.strip():
            raise ValueError(f"case {index} has empty input or expected")
        if case.difficulty not in VALID_DIFFICULTIES:
            raise ValueError(f"case {index} has invalid difficulty {case.difficulty}")
        if case.danger not in VALID_DANGERS:
            raise ValueError(f"case {index} has invalid danger {case.danger}")
        scope_for_category(case.category)


def _validate_no_duplicate_rows(cases: list[TestCase]) -> None:
    seen: set[tuple[str, str, str, str]] = set()
    for index, case in enumerate(cases, start=1):
        key = (case.input_value, case.expected, case.error_type, case.category)
        if key in seen:
            raise ValueError(f"duplicate generated row at case {index}: {key}")
        seen.add(key)


def _build_summary(cases: list[TestCase]) -> ValidationSummary:
    difficulty_counts = Counter(case.difficulty for case in cases)
    hard_count = difficulty_counts["HARD"] + difficulty_counts["EXTREME"]
    scope_counts = Counter(scope_for_category(case.category) for case in cases)
    return ValidationSummary(
        total_cases=len(cases),
        hard_case_ratio=hard_count / len(cases),
        category_counts=dict(Counter(case.category for case in cases)),
        difficulty_counts=dict(difficulty_counts),
        danger_counts=dict(Counter(case.danger for case in cases)),
        scope_counts=dict(scope_counts),
    )


def _exact_compact_match_count(cases: list[TestCase]) -> int:
    return sum(1 for case in cases if compact_key(case.input_value) == compact_key(case.expected))


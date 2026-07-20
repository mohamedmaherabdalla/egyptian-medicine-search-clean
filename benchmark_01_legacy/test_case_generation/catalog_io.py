"""Catalog and seed-case loading for test generation.

Problem: generation must read source CSVs, validate required schema, and expose
indexes for collision-aware mutations.
Inputs: `data/canonical_candidates.csv` and the original seed test-case CSV.
Outputs: typed CatalogRecord rows, seed TestCase rows, and deterministic indexes.
Edge cases: missing columns, empty base groups, duplicate base groups, malformed
seed difficulty/danger labels, and short compact keys.
Failure modes: schema or row problems raise ValueError with row context; partial
loads are not allowed because they would skew medical safety statistics.
Algorithm choice: csv.DictReader is used instead of pandas because generation is
streaming-friendly, dependency-free, and schema validation is explicit.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .config import (
    CSV_FIELDNAMES,
    MAX_COLLISION_NAMES_IN_NOTE,
    MAX_PREFIX_LENGTH,
    MAX_SUFFIX_LENGTH,
    MIN_PREFIX_LENGTH,
    MIN_SUFFIX_LENGTH,
)
from .models import CatalogRecord, Danger, Difficulty, TestCase
from .normalization import compact_key, normalize_search


REQUIRED_CATALOG_COLUMNS = {
    "candidate_id",
    "commercial_name_en",
    "commercial_name_en_norm",
    "commercial_name_en_compact",
    "commercial_name_ar_norm",
    "base_group_key",
    "scientific_name",
    "ingredient_key",
    "manufacturer_primary",
    "drug_class_top",
    "route_family",
    "strengths_join",
    "review_reasons",
}
VALID_DIFFICULTIES = {"EASY", "MEDIUM", "HARD", "EXTREME"}
VALID_DANGERS = {"SAFE", "CAUTION", "DANGEROUS"}


class CatalogIndex:
    """Indexes over catalog records used by multiple generators.

    Args:
        records: Product-level catalog records.

    Raises:
        ValueError: If no usable records are provided.
    """

    def __init__(self, records: list[CatalogRecord]) -> None:
        if not records:
            raise ValueError("catalog index cannot be built from zero records")
        self.records = records
        self.base_records = self._dedupe_base_records(records)
        self.base_by_compact = self._build_base_compact_index(self.base_records)
        self.ingredients_by_base = self._build_ingredient_index(self.base_records)
        self.prefix_to_bases = self._build_prefix_index(self.base_records)
        self.suffix_to_bases = self._build_suffix_index(self.base_records)

    @staticmethod
    def _dedupe_base_records(records: list[CatalogRecord]) -> list[CatalogRecord]:
        seen: set[str] = set()
        out: list[CatalogRecord] = []
        for record in records:
            if record.base_group_compact in seen:
                continue
            seen.add(record.base_group_compact)
            out.append(record)
        return out

    @staticmethod
    def _build_base_compact_index(records: list[CatalogRecord]) -> dict[str, list[CatalogRecord]]:
        out: dict[str, list[CatalogRecord]] = defaultdict(list)
        for record in records:
            out[record.base_group_compact].append(record)
        return dict(out)

    @staticmethod
    def _build_ingredient_index(records: list[CatalogRecord]) -> dict[str, str]:
        return {record.base_group_key: record.ingredient_key for record in records}

    @staticmethod
    def _build_prefix_index(records: list[CatalogRecord]) -> dict[str, list[CatalogRecord]]:
        out: dict[str, list[CatalogRecord]] = defaultdict(list)
        for record in records:
            compact = record.base_group_compact
            for length in range(MIN_PREFIX_LENGTH, MAX_PREFIX_LENGTH + 1):
                if len(compact) >= length:
                    out[compact[:length]].append(record)
        return dict(out)

    @staticmethod
    def _build_suffix_index(records: list[CatalogRecord]) -> dict[str, list[CatalogRecord]]:
        out: dict[str, list[CatalogRecord]] = defaultdict(list)
        for record in records:
            compact = record.base_group_compact
            for length in range(MIN_SUFFIX_LENGTH, MAX_SUFFIX_LENGTH + 1):
                if len(compact) > length:
                    out[compact[-length:]].append(record)
        return dict(out)

    def collision_names_for(self, input_value: str, expected: str) -> str:
        """Return known different base groups matching the same compact input.

        Args:
            input_value: Mutated query.
            expected: Expected base group.

        Returns:
            Semicolon-separated collision names, capped for CSV readability.
        """

        compact = compact_key(input_value)
        matches = self.base_by_compact.get(compact, [])
        names = [r.base_group_key for r in matches if r.base_group_key != expected]
        return "; ".join(names[:MAX_COLLISION_NAMES_IN_NOTE])

    def prefix_collisions_for(self, prefix: str, expected: str) -> str:
        """Return other base groups sharing a compact prefix.

        Args:
            prefix: Compact or spaced prefix.
            expected: Expected base group to exclude.

        Returns:
            Semicolon-separated collision names.
        """

        compact = compact_key(prefix)
        matches = self.prefix_to_bases.get(compact, [])
        names = [r.base_group_key for r in matches if r.base_group_key != expected]
        return "; ".join(names[:MAX_COLLISION_NAMES_IN_NOTE])

    def suffix_collisions_for(self, suffix: str, expected: str) -> str:
        """Return other base groups sharing a compact suffix.

        Args:
            suffix: Compact suffix.
            expected: Expected base group to exclude.

        Returns:
            Semicolon-separated collision names.
        """

        compact = compact_key(suffix)
        matches = self.suffix_to_bases.get(compact, [])
        names = [r.base_group_key for r in matches if r.base_group_key != expected]
        return "; ".join(names[:MAX_COLLISION_NAMES_IN_NOTE])

    def has_ingredient_collision(self, expected: str, collision_names: str) -> bool:
        """Return whether collision names include a different ingredient key.

        Args:
            expected: Expected base group.
            collision_names: Semicolon-separated collision group names.

        Returns:
            True when at least one collision has a different ingredient key.
        """

        expected_key = self.ingredients_by_base.get(expected, "")
        for name in [part.strip() for part in collision_names.split(";")]:
            if name and self.ingredients_by_base.get(name, "") != expected_key:
                return True
        return False


def load_catalog(path: Path) -> list[CatalogRecord]:
    """Load canonical candidates as typed records.

    Args:
        path: Path to `canonical_candidates.csv`.

    Returns:
        Product-level catalog records with usable base-group keys.

    Raises:
        ValueError: If the file is missing required columns or usable rows.
    """

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        _validate_catalog_header(path, reader.fieldnames)
        records = [_record_from_row(row, line_no) for line_no, row in enumerate(reader, start=2)]
    usable = [record for record in records if record.base_group_compact]
    if not usable:
        raise ValueError(f"{path} did not contain any usable catalog records")
    return usable


def _validate_catalog_header(path: Path, fieldnames: list[str] | None) -> None:
    if fieldnames is None:
        raise ValueError(f"{path} is empty or has no CSV header")
    missing = sorted(REQUIRED_CATALOG_COLUMNS - set(fieldnames))
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")


def _record_from_row(row: dict[str, str], line_no: int) -> CatalogRecord:
    base_group_key = normalize_search(row.get("base_group_key", ""))
    commercial_name_en = row.get("commercial_name_en", "").strip()
    if not base_group_key or not commercial_name_en:
        raise ValueError(f"catalog line {line_no} lacks commercial name or base group")
    return CatalogRecord(
        candidate_id=row.get("candidate_id", "").strip(),
        commercial_name_en=commercial_name_en,
        commercial_name_norm=normalize_search(row.get("commercial_name_en_norm", commercial_name_en)),
        commercial_name_compact=compact_key(row.get("commercial_name_en_compact", commercial_name_en)),
        commercial_name_ar_norm=normalize_search(row.get("commercial_name_ar_norm", "")),
        base_group_key=base_group_key,
        base_group_compact=compact_key(base_group_key),
        scientific_name=normalize_search(row.get("scientific_name", "")),
        ingredient_key=normalize_search(row.get("ingredient_key", "")),
        manufacturer_primary=normalize_search(row.get("manufacturer_primary", "")),
        drug_class_top=normalize_search(row.get("drug_class_top", "")),
        route_family=normalize_search(row.get("route_family", "")).lower(),
        strengths_join=normalize_search(row.get("strengths_join", "")),
        review_reasons=row.get("review_reasons", "").strip(),
    )


def load_seed_cases(path: Path) -> list[TestCase]:
    """Load original manually curated seed cases.

    Args:
        path: Path to the original seed CSV.

    Returns:
        Seed TestCase objects.

    Raises:
        ValueError: If the schema or labels are invalid.
    """

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        _validate_seed_header(path, reader.fieldnames)
        return [_seed_case_from_row(row, line_no) for line_no, row in enumerate(reader, start=2)]


def _validate_seed_header(path: Path, fieldnames: list[str] | None) -> None:
    if fieldnames is None:
        raise ValueError(f"{path} is empty or has no CSV header")
    missing = sorted(set(CSV_FIELDNAMES) - set(fieldnames))
    if missing:
        raise ValueError(f"{path} is missing seed columns: {', '.join(missing)}")


def _seed_case_from_row(row: dict[str, str], line_no: int) -> TestCase:
    difficulty = _parse_difficulty(row.get("difficulty", ""), line_no)
    danger = _parse_danger(row.get("danger", ""), line_no)
    input_value = row.get("input", "").strip()
    expected = row.get("expected", "").strip()
    if not input_value or not expected:
        raise ValueError(f"seed line {line_no} lacks input or expected")
    return TestCase(
        input_value=input_value,
        expected=expected,
        error_type=row.get("error_type", "").strip(),
        category=row.get("category", "").strip(),
        difficulty=difficulty,
        danger=danger,
        collision_with=row.get("collision_with", "").strip(),
        notes=row.get("notes", "").strip(),
    )


def _parse_difficulty(value: str, line_no: int) -> Difficulty:
    if value not in VALID_DIFFICULTIES:
        raise ValueError(f"seed line {line_no} has invalid difficulty '{value}'")
    return value  # type: ignore[return-value]


def _parse_danger(value: str, line_no: int) -> Danger:
    if value not in VALID_DANGERS:
        raise ValueError(f"seed line {line_no} has invalid danger '{value}'")
    return value  # type: ignore[return-value]

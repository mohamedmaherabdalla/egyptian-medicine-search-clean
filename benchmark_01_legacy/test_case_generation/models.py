"""Typed domain models for commercial-name test generation.

Problem: the generator must convert catalog rows into deterministic evaluation
cases without passing raw dictionaries through the algorithm.
Inputs: CSV/JSON rows whose values are strings, plus generated mutation strings.
Outputs: dataclasses for catalog records, mutation candidates, and final cases.
Edge cases: missing required fields, empty generated inputs, duplicated cases,
and categories without configuration.
Failure modes: malformed catalog rows raise ValueError before generation starts;
silent fallback would create misleading medical-search tests, so it is blocked.
Algorithm choice: dataclasses were chosen over plain dicts because the schema is
small and stable; TypedDict would describe keys but would not centralize derived
fields such as compact commercial-name keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Difficulty = Literal["EASY", "MEDIUM", "HARD", "EXTREME"]
Danger = Literal["SAFE", "CAUTION", "DANGEROUS"]
Scope = Literal["inside", "semi_outside", "outside"]


@dataclass(frozen=True)
class CatalogRecord:
    """A normalized catalog row used as source material for generated cases.

    Args:
        candidate_id: Stable catalog row identifier.
        commercial_name_en: Original English product name.
        commercial_name_norm: Search-normalized English product name.
        commercial_name_compact: Compact English product key.
        commercial_name_ar_norm: Normalized Arabic alias.
        base_group_key: Normalized commercial family name.
        base_group_compact: Compact commercial family key.
        scientific_name: Source active-ingredient/composition text.
        ingredient_key: Normalized ingredient key used for collision risk.
        manufacturer_primary: Primary manufacturer text.
        drug_class_top: Top therapeutic-class bucket.
        route_family: Coarse route/form family.
        strengths_join: Extracted strength tokens.
        review_reasons: Data-quality warning text.
    """

    candidate_id: str
    commercial_name_en: str
    commercial_name_norm: str
    commercial_name_compact: str
    commercial_name_ar_norm: str
    base_group_key: str
    base_group_compact: str
    scientific_name: str
    ingredient_key: str
    manufacturer_primary: str
    drug_class_top: str
    route_family: str
    strengths_join: str
    review_reasons: str


@dataclass(frozen=True)
class Mutation:
    """An intermediate mutated query produced by one generator.

    Args:
        input_value: User-facing noisy query string.
        error_type: Specific error type within a broader category.
        notes: Human-readable generation note.
        collision_hint: Optional known colliding commercial family names.
        danger_override: Optional danger level when a row is riskier than its
            category default.
        difficulty_override: Optional difficulty when a row is harder than its
            category default.
    """

    input_value: str
    error_type: str
    notes: str
    collision_hint: str = ""
    danger_override: Danger | None = None
    difficulty_override: Difficulty | None = None


@dataclass(frozen=True)
class TestCase:
    """A final CSV evaluation case.

    Args:
        input_value: Query submitted to the search engine.
        expected: Expected commercial family or explicit ambiguous target text.
        error_type: Specific error type label.
        category: Broad category label used for metrics.
        difficulty: Difficulty bucket for stratified evaluation.
        danger: Safety severity bucket.
        collision_with: Known colliding family or candidate text.
        notes: Human-readable provenance and generation explanation.
    """

    input_value: str
    expected: str
    error_type: str
    category: str
    difficulty: Difficulty
    danger: Danger
    collision_with: str
    notes: str

    def to_csv_row(self) -> dict[str, str]:
        """Return this case using the exact CSV schema.

        Returns:
            A dictionary keyed by the generator's fixed CSV field names.
        """

        return {
            "input": self.input_value,
            "expected": self.expected,
            "error_type": self.error_type,
            "category": self.category,
            "difficulty": self.difficulty,
            "danger": self.danger,
            "collision_with": self.collision_with,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class CategorySpec:
    """Configuration for one generated category.

    Args:
        category: Broad category label.
        target_count: Maximum number of generated cases to emit.
        scope: Scope split used by evaluation files.
        difficulty: Default difficulty for the generated category.
        danger: Default danger for the generated category.
        rationale: Human-readable reason for the target and labels.
    """

    category: str
    target_count: int
    scope: Scope
    difficulty: Difficulty
    danger: Danger
    rationale: str


@dataclass(frozen=True)
class ValidationSummary:
    """Summary produced after validating the generated suite.

    Args:
        total_cases: Number of generated plus seed cases.
        hard_case_ratio: Fraction of HARD or EXTREME cases.
        category_counts: Count by category.
        difficulty_counts: Count by difficulty.
        danger_counts: Count by danger.
        scope_counts: Count by inside/outside/semi_outside split.
    """

    total_cases: int
    hard_case_ratio: float
    category_counts: dict[str, int]
    difficulty_counts: dict[str, int]
    danger_counts: dict[str, int]
    scope_counts: dict[str, int]


"""High-level generation orchestration for commercial-name test cases.

Problem: category-specific mutations must be converted into final CSV cases
with consistent difficulty, danger, collision, and deduplication behavior.
Inputs: CatalogIndex, seed TestCase rows, and CategorySpec configuration.
Outputs: a deterministic list of final TestCase rows.
Edge cases: duplicate mutations, exact-key generated inputs, categories that
produce fewer than their target count, and mutations that collide with a known
different commercial family.
Failure modes: missing transform functions or invalid category specs raise
ValueError before writing output files.
Algorithm choice: deterministic catalog-order generation was chosen over random
sampling so score changes reflect code/data changes rather than sample noise.
"""

from __future__ import annotations

import logging

from .catalog_io import CatalogIndex
from .config import (
    GENERATED_CATEGORY_SPECS,
    MAX_MUTATIONS_PER_RECORD_PER_CATEGORY,
    MIN_COMPACT_NAME_LENGTH,
)
from .models import CatalogRecord, Mutation, TestCase
from .normalization import compact_key
from .transforms import INDEX_TRANSFORMS, RECORD_TRANSFORMS


logger = logging.getLogger(__name__)
EXACT_KEY_ALLOWED_CATEGORIES = {
    "partial_prefix_ambiguity_catalog",
    "truncation_collision_expanded_catalog",
    "ingredient_name_query_catalog",
    "separator_removal_full_catalog",
    "space_insertion_inside_brand_catalog",
}


def generate_cases(seed_cases: list[TestCase], index: CatalogIndex) -> list[TestCase]:
    """Generate the full expanded suite.

    Args:
        seed_cases: Original manually curated seed cases.
        index: Catalog index built from canonical candidates.

    Returns:
        Seed cases followed by generated cases.

    Raises:
        ValueError: If a configured category lacks a transform.
    """

    generated: list[TestCase] = []
    for category in GENERATED_CATEGORY_SPECS:
        logger.info("Generating category %s", category)
        generated.extend(_generate_category(category, index))
    logger.info("Generated %d new rows across %d categories", len(generated), len(GENERATED_CATEGORY_SPECS))
    return [*seed_cases, *generated]


def _generate_category(category: str, index: CatalogIndex) -> list[TestCase]:
    spec = GENERATED_CATEGORY_SPECS[category]
    records = _records_for_category(category, index)
    seen: set[tuple[str, str, str]] = set()
    out: list[TestCase] = []
    for record in records:
        mutations = _mutations_for_category(category, record, index)
        for mutation in mutations[:MAX_MUTATIONS_PER_RECORD_PER_CATEGORY]:
            case = _case_from_mutation(category, record, mutation, index)
            if not _should_keep_case(case, record, seen):
                continue
            out.append(case)
            if len(out) >= spec.target_count:
                logger.info("Category %s reached target %d", category, spec.target_count)
                return out
    logger.warning("Category %s emitted %d of target %d", category, len(out), spec.target_count)
    return out


def _records_for_category(category: str, index: CatalogIndex) -> list[CatalogRecord]:
    product_level = {
        "strength_unit_noise_catalog",
        "decimal_slash_strength_noise_catalog",
        "symbol_synonym_catalog",
        "abbreviation_expansion_catalog",
        "manufacturer_noise_catalog",
        "ingredient_name_query_catalog",
        "brand_ingredient_mixed_query_catalog",
    }
    if category in product_level:
        return index.records
    return index.base_records


def _mutations_for_category(category: str, record: CatalogRecord, index: CatalogIndex) -> list[Mutation]:
    if category in RECORD_TRANSFORMS:
        return RECORD_TRANSFORMS[category](record)
    if category in INDEX_TRANSFORMS:
        return INDEX_TRANSFORMS[category](record, index)
    raise ValueError(f"category '{category}' has no registered transform")


def _case_from_mutation(
    category: str,
    record: CatalogRecord,
    mutation: Mutation,
    index: CatalogIndex,
) -> TestCase:
    spec = GENERATED_CATEGORY_SPECS[category]
    collision = mutation.collision_hint or index.collision_names_for(mutation.input_value, record.base_group_key)
    danger = mutation.danger_override or spec.danger
    difficulty = mutation.difficulty_override or spec.difficulty
    if collision and danger == "SAFE":
        danger = "DANGEROUS" if index.has_ingredient_collision(record.base_group_key, collision) else "CAUTION"
    notes = _notes_for_case(record, mutation, spec.rationale)
    return TestCase(
        input_value=mutation.input_value,
        expected=record.base_group_key,
        error_type=mutation.error_type,
        category=category,
        difficulty=difficulty,
        danger=danger,
        collision_with=collision,
        notes=notes,
    )


def _notes_for_case(record: CatalogRecord, mutation: Mutation, rationale: str) -> str:
    return (
        f"{mutation.notes}; expected={record.base_group_key}; "
        f"source_id={record.candidate_id}; rationale={rationale}"
    )


def _should_keep_case(
    case: TestCase,
    record: CatalogRecord,
    seen: set[tuple[str, str, str]],
) -> bool:
    compact_input = compact_key(case.input_value)
    if len(compact_input) < MIN_COMPACT_NAME_LENGTH and not case.category.startswith("partial_prefix"):
        return False
    if _is_unwanted_exact_key_case(case.category, compact_input, record.base_group_compact):
        return False
    key = (case.category, case.input_value, case.expected)
    if key in seen:
        return False
    seen.add(key)
    return True


def _is_unwanted_exact_key_case(category: str, input_compact: str, expected_compact: str) -> bool:
    if category in EXACT_KEY_ALLOWED_CATEGORIES:
        return False
    return input_compact == expected_compact

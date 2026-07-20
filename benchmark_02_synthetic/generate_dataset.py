#!/usr/bin/env python3
"""Generate the commercial-name testing dataset v2 from the attached plan.

Problem: create a 120,000-row commercial-name stress dataset where every row is
generated from code, every plan category is represented, and the outputs are
traceable to the exact generator function that emitted them.
Inputs:
    - data/canonical_candidates.csv, containing product rows and commercial
      family keys.
    - The static category plan encoded in CATEGORY_PLANS below, copied from the
      user-approved v2 distribution plan.
Outputs:
    - data/test_cases.csv: all generated rows with provenance columns.
    - data/category_summary.csv: target-vs-actual counts.
    - data/generation_summary.json: validation and distribution
      summary.
Edge cases:
    - Some catalog names are too short to mutate safely.
    - Some categories can naturally produce many duplicate noisy inputs.
    - Safety categories can have no single correct target because the desired
      behavior is ambiguity/no-match handling.
    - Score-gap cases require a live search engine in the plan; this script uses
      a deterministic catalog-collision proxy and labels the notes accordingly.
Failure modes:
    - Missing catalog columns, empty generated categories, target count misses,
      duplicated final rows, or a hard/extreme ratio below the configured floor
      raise explicit exceptions and stop the script.
Algorithm choice:
    - Rule-based generation was chosen over random mutation because this is a
      medical search benchmark. Every generated row needs an explainable reason,
      a category label, and stable reproducibility. Deterministic hash sampling
      is used instead of random sampling so repeated runs produce byte-stable
      outputs while avoiding catalog-order bias.
"""

from __future__ import annotations

import bisect
import csv
import difflib
import hashlib
import json
import logging
import re
import string
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterable, Literal, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark_01_legacy.test_case_generation.catalog_io import CatalogIndex, load_catalog
from benchmark_01_legacy.test_case_generation.models import CatalogRecord
from benchmark_01_legacy.test_case_generation.normalization import compact_key, normalize_search


logger = logging.getLogger(__name__)

Difficulty = Literal["EASY", "MEDIUM", "HARD", "EXTREME"]
Danger = Literal["SAFE", "CAUTION", "DANGEROUS"]
Scope = Literal["inside", "semi_outside", "outside", "safety", "smoke"]


# The user plan headline says approximately 120k rows, but the explicit 34
# category rows in the attached table sum to 115k. We keep both values visible
# and validate against the auditable per-category targets rather than inventing
# an undocumented 5k-row top-up category.
DECLARED_PLAN_TOTAL_CASES = 120_000

# The plan requires more than 60% hard cases. We validate against the stated
# threshold, not merely the intended split, because a category bug could
# accidentally flood the suite with easy cases.
MIN_HARD_OR_EXTREME_RATIO = 0.60

# Deterministic hash sampling uses this namespace string so future generators
# can change their sample without changing helper behavior globally.
SAMPLING_NAMESPACE = "commercial-name-testing-dataset-v2"

# Compact names below 3 characters create mostly noise and false collisions.
# Safety/prefix categories are allowed to use short inputs explicitly.
MIN_MUTATED_COMPACT_LENGTH = 3

# Collision notes can become enormous for common prefixes. Capping keeps the CSV
# auditable while the summary still counts full categories.
MAX_COLLISION_NAMES_IN_CELL = 8

# The output schema deliberately keeps the legacy evaluation columns first, then
# adds provenance fields proving that every row came from this script.
CSV_FIELDNAMES = [
    "input",
    "expected",
    "error_type",
    "category",
    "case_subcategory",
    "unreadable_continuation",
    "difficulty",
    "danger",
    "collision_with",
    "notes",
    "scope",
    "tier",
    "category_number",
    "expected_behavior",
    "generator_script",
    "generator_function",
    "source_candidate_id",
    "source_base_group",
]

NO_MATCH_EXPECTED = "__NO_MATCH__"
AMBIGUOUS_EXPECTED = "__AMBIGUOUS__"
VOWELS = "AEIOUY"
QWERTY_ROWS = ("QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM")


@dataclass(frozen=True)
class DifficultyMix:
    """Difficulty percentages copied from one plan row.

    The values are fractions summing to 1.0. Fractions are converted to exact
    row counts after category sampling so rounding cannot drift the final count.
    """

    easy: float = 0.0
    medium: float = 0.0
    hard: float = 0.0
    extreme: float = 0.0

    def as_pairs(self) -> list[tuple[Difficulty, float]]:
        """Return difficulty labels in stable order for quota allocation."""

        return [
            ("EASY", self.easy),
            ("MEDIUM", self.medium),
            ("HARD", self.hard),
            ("EXTREME", self.extreme),
        ]


@dataclass(frozen=True)
class CategoryPlan:
    """One v2 distribution-plan row."""

    number: int
    tier: str
    category: str
    target_count: int
    scope: Scope
    difficulty_mix: DifficultyMix
    default_danger: Danger
    generator_function: str
    description: str


@dataclass(frozen=True)
class GeneratedCase:
    """One generated dataset row before CSV serialization."""

    input_value: str
    expected: str
    error_type: str
    category: str
    case_subcategory: str
    unreadable_continuation: bool
    difficulty: Difficulty
    danger: Danger
    collision_with: str
    notes: str
    scope: str
    tier: str
    category_number: int
    expected_behavior: str
    generator_script: str
    generator_function: str
    source_candidate_id: str
    source_base_group: str

    def to_csv_row(self) -> dict[str, str]:
        """Return a stable CSV row using CSV_FIELDNAMES."""

        return {
            "input": self.input_value,
            "expected": self.expected,
            "error_type": self.error_type,
            "category": self.category,
            "case_subcategory": self.case_subcategory,
            "unreadable_continuation": "1" if self.unreadable_continuation else "0",
            "difficulty": self.difficulty,
            "danger": self.danger,
            "collision_with": self.collision_with,
            "notes": self.notes,
            "scope": self.scope,
            "tier": self.tier,
            "category_number": str(self.category_number),
            "expected_behavior": self.expected_behavior,
            "generator_script": self.generator_script,
            "generator_function": self.generator_function,
            "source_candidate_id": self.source_candidate_id,
            "source_base_group": self.source_base_group,
        }


@dataclass(frozen=True)
class IndexedCatalog:
    """Catalog plus extra indexes required by v2 safety generators."""

    index: CatalogIndex
    base_records: list[CatalogRecord]
    product_records: list[CatalogRecord]
    records_by_prefix_sort: list[tuple[str, CatalogRecord]]
    product_records_by_base: dict[str, list[CatalogRecord]]


CATEGORY_PLANS: list[CategoryPlan] = [
    CategoryPlan(1, "tier_1_product", "single_letter_visual_confusion", 8_000, "inside", DifficultyMix(medium=0.15, hard=0.60, extreme=0.25), "SAFE", "generate_single_letter_visual_confusion", "One letter is replaced by a visually similar letter at the same position."),
    CategoryPlan(2, "tier_1_product", "single_letter_phonetic_confusion", 6_000, "inside", DifficultyMix(medium=0.20, hard=0.60, extreme=0.20), "SAFE", "generate_single_letter_phonetic_confusion", "One letter is replaced by a sound-alike letter important for Egyptian Arabic pronunciation."),
    CategoryPlan(3, "tier_1_product", "multi_char_phonetic_confusion", 5_000, "inside", DifficultyMix(medium=0.20, hard=0.50, extreme=0.30), "SAFE", "generate_multi_char_phonetic_confusion", "A multi-character sound pattern such as ph/f or qu/kw is rewritten."),
    CategoryPlan(4, "tier_1_product", "ligature_confusion", 4_000, "inside", DifficultyMix(medium=0.10, hard=0.50, extreme=0.40), "SAFE", "generate_ligature_confusion", "Adjacent letters merge into or split from a visually similar glyph."),
    CategoryPlan(5, "tier_1_product", "single_char_deletion_position_weighted", 5_000, "inside", DifficultyMix(medium=0.20, hard=0.50, extreme=0.30), "SAFE", "generate_single_char_deletion_position_weighted", "One character is missing with position weights from the plan."),
    CategoryPlan(6, "tier_1_product", "single_char_insertion", 3_000, "inside", DifficultyMix(medium=0.30, hard=0.50, extreme=0.20), "SAFE", "generate_single_char_insertion", "One extra character is inserted, including duplicate and adjacent-key insertions."),
    CategoryPlan(7, "tier_1_product", "transposition_position_weighted", 3_000, "inside", DifficultyMix(medium=0.30, hard=0.50, extreme=0.20), "SAFE", "generate_transposition_position_weighted", "Adjacent letters are swapped with an end-weighted distribution."),
    CategoryPlan(8, "tier_1_product", "truncation_doctor_abbreviation", 6_000, "inside", DifficultyMix(easy=0.10, medium=0.30, hard=0.40, extreme=0.20), "CAUTION", "generate_truncation_doctor_abbreviation", "The user types only the first 3 to 6 compact characters."),
    CategoryPlan(9, "tier_1_product", "two_error_combinations", 8_000, "inside", DifficultyMix(medium=0.20, hard=0.60, extreme=0.20), "SAFE", "generate_two_error_combinations", "Two realistic corruption mechanisms are chained."),
    CategoryPlan(10, "tier_1_product", "three_error_combinations", 5_000, "inside", DifficultyMix(hard=0.40, extreme=0.60), "SAFE", "generate_three_error_combinations", "Three realistic corruption mechanisms are chained."),
    CategoryPlan(11, "tier_1_product", "speed_typing_errors", 3_000, "inside", DifficultyMix(easy=0.20, medium=0.40, hard=0.30, extreme=0.10), "SAFE", "generate_speed_typing_errors", "Motor-control typing artifacts such as repeats and skipped letters."),
    CategoryPlan(12, "tier_1_product", "wrong_vowels_in_consonant_frame", 5_000, "inside", DifficultyMix(medium=0.20, hard=0.50, extreme=0.30), "SAFE", "generate_wrong_vowels_in_consonant_frame", "Consonants are preserved while one to three vowels are guessed incorrectly."),
    CategoryPlan(13, "tier_1_product", "punctuation_whitespace_copy_paste_artifacts", 1_000, "inside", DifficultyMix(easy=0.80, medium=0.20), "SAFE", "generate_punctuation_whitespace_copy_paste_artifacts", "Copy-paste punctuation and whitespace artifacts wrap or split the name."),
    CategoryPlan(14, "tier_1_product", "case_sensitivity", 500, "inside", DifficultyMix(easy=1.00), "SAFE", "generate_case_sensitivity", "The same name is typed in lower, upper, title, and mixed case."),
    CategoryPlan(15, "tier_1_product", "number_word_confusion", 500, "inside", DifficultyMix(medium=0.30, hard=0.50, extreme=0.20), "SAFE", "generate_number_word_confusion", "Digits in commercial names are rewritten as words, spaces, or hyphenated forms."),
    CategoryPlan(16, "tier_1_product", "embedded_form_strength_parsing", 4_000, "semi_outside", DifficultyMix(medium=0.10, hard=0.50, extreme=0.40), "CAUTION", "generate_embedded_form_strength_parsing", "A brand fragment is mixed with strength and form tokens."),
    CategoryPlan(17, "tier_2_safety", "dangerous_ed1_pairs", 5_000, "safety", DifficultyMix(medium=0.20, hard=0.60, extreme=0.20), "DANGEROUS", "generate_dangerous_ed1_pairs", "Catalog pairs are one edit apart but have different ingredient keys."),
    CategoryPlan(18, "tier_2_safety", "substring_traps", 3_000, "safety", DifficultyMix(medium=0.20, hard=0.50, extreme=0.30), "DANGEROUS", "generate_substring_traps", "A short real drug is a prefix of a longer different-ingredient drug."),
    CategoryPlan(19, "tier_2_safety", "negative_no_match_expected", 3_000, "safety", DifficultyMix(easy=0.20, medium=0.40, hard=0.40), "DANGEROUS", "generate_negative_no_match_expected", "Inputs that should not produce a confident commercial-name match."),
    CategoryPlan(20, "tier_2_safety", "contradictory_form_route", 2_000, "safety", DifficultyMix(medium=0.30, hard=0.70), "CAUTION", "generate_contradictory_form_route", "The drug is real but the requested route or form conflicts with the catalog."),
    CategoryPlan(21, "tier_2_safety", "cancelled_na_drug_lookup", 1_000, "safety", DifficultyMix(easy=0.20, medium=0.50, hard=0.30), "CAUTION", "generate_cancelled_na_drug_lookup", "Cancelled, illegal import, N/A, or review-warning products are searched."),
    CategoryPlan(22, "tier_2_safety", "score_gap_ambiguity_detection", 4_000, "safety", DifficultyMix(medium=0.30, hard=0.50, extreme=0.20), "DANGEROUS", "generate_score_gap_ambiguity_detection", "Engine-independent proxy for small-gap ambiguity until live score mining is wired in."),
    CategoryPlan(23, "tier_3_algorithmic", "ocr_letter_digit_confusion", 4_000, "inside", DifficultyMix(medium=0.30, hard=0.50, extreme=0.20), "SAFE", "generate_ocr_letter_digit_confusion", "OCR letter/digit substitutions such as O/0 and B/8."),
    CategoryPlan(24, "tier_3_algorithmic", "ocr_plus_other_error_combined", 3_000, "inside", DifficultyMix(medium=0.10, hard=0.50, extreme=0.40), "SAFE", "generate_ocr_plus_other_error_combined", "An OCR substitution is followed by another realistic error."),
    CategoryPlan(25, "tier_3_algorithmic", "double_letter_reduction_expansion", 3_000, "inside", DifficultyMix(medium=0.40, hard=0.40, extreme=0.20), "SAFE", "generate_double_letter_reduction_expansion", "Repeated letters are reduced or single letters are doubled."),
    CategoryPlan(26, "tier_3_algorithmic", "keyboard_adjacent_sampled", 2_000, "inside", DifficultyMix(medium=0.50, hard=0.50), "SAFE", "generate_keyboard_adjacent_sampled", "Sampled QWERTY adjacent-key substitution cases."),
    CategoryPlan(27, "tier_3_algorithmic", "four_plus_error_combinations", 4_000, "inside", DifficultyMix(hard=0.30, extreme=0.70), "SAFE", "generate_four_plus_error_combinations", "Four or more simultaneous corruptions create barely readable queries."),
    CategoryPlan(28, "tier_3_algorithmic", "consonant_frame_wrong_vowels_heavy", 4_000, "inside", DifficultyMix(medium=0.10, hard=0.40, extreme=0.50), "SAFE", "generate_consonant_frame_wrong_vowels_heavy", "All or nearly all vowels are wrong while consonant clues remain."),
    CategoryPlan(29, "tier_3_algorithmic", "multi_word_name_fragmentation", 2_000, "inside", DifficultyMix(medium=0.10, hard=0.50, extreme=0.40), "CAUTION", "generate_multi_word_name_fragmentation", "Multi-word commercial families are merged, abbreviated, or partially dropped."),
    CategoryPlan(30, "tier_3_algorithmic", "autocorrect_artifacts", 2_000, "inside", DifficultyMix(medium=0.20, hard=0.50, extreme=0.30), "SAFE", "generate_autocorrect_artifacts", "Phone-style autocorrect and word-boundary artifacts are generated."),
    CategoryPlan(31, "tier_4_smoke", "exact_match_baseline", 2_000, "smoke", DifficultyMix(easy=1.00), "SAFE", "generate_exact_match_baseline", "Exact commercial family names establish the baseline."),
    CategoryPlan(32, "tier_4_smoke", "exact_match_with_strength", 2_000, "smoke", DifficultyMix(easy=0.80, medium=0.20), "SAFE", "generate_exact_match_with_strength", "Exact commercial names are combined with real strength tokens."),
    CategoryPlan(33, "tier_4_smoke", "keyboard_shift_whole_word", 500, "smoke", DifficultyMix(medium=0.20, extreme=0.80), "SAFE", "generate_keyboard_shift_whole_word", "The whole compact name is typed one keyboard key left or right."),
    CategoryPlan(34, "tier_4_smoke", "prefix_ambiguity_awareness", 1_500, "smoke", DifficultyMix(medium=0.30, hard=0.50, extreme=0.20), "CAUTION", "generate_prefix_ambiguity_awareness", "Very short prefixes with many ingredient collisions should be treated as ambiguous."),
]

TOTAL_TARGET_CASES = sum(plan.target_count for plan in CATEGORY_PLANS)


def main() -> None:
    """Generate all v2 outputs and fail loudly on distribution mistakes."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    output_dir = Path(__file__).resolve().parent / "data"
    catalog = build_indexed_catalog()

    all_cases: list[GeneratedCase] = []
    category_summaries: list[dict[str, str]] = []
    for plan in CATEGORY_PLANS:
        logger.info("generating category %02d %s", plan.number, plan.category)
        generator = GENERATORS.get(plan.generator_function)
        if generator is None:
            raise ValueError(f"category {plan.category} has no generator {plan.generator_function}")
        candidates = generator(plan, catalog)
        selected = select_category_cases(plan, candidates)
        selected = assign_difficulties(plan, selected)
        if len(selected) != plan.target_count:
            raise RuntimeError(
                f"{plan.category} generated {len(selected)} cases, target {plan.target_count}"
            )
        all_cases.extend(selected)
        category_summaries.append(category_summary(plan, selected, len(candidates)))

    validate_final_dataset(all_cases)
    write_cases_csv(output_dir / "test_cases.csv", all_cases)
    write_category_summary(output_dir / "category_summary.csv", category_summaries)
    write_generation_summary(output_dir / "generation_summary.json", all_cases, category_summaries)
    logger.info("wrote %d cases to %s", len(all_cases), output_dir)


def build_indexed_catalog() -> IndexedCatalog:
    """Load the canonical catalog and build v2-specific lookup tables."""

    catalog_path = ROOT / "data" / "canonical_candidates.csv"
    records = load_catalog(catalog_path)
    index = CatalogIndex(records)
    base_records = [record for record in index.base_records if len(record.base_group_compact) >= 2]
    if not base_records:
        raise ValueError("catalog has no usable base records")

    records_by_prefix_sort = sorted((record.base_group_compact, record) for record in base_records)
    product_records_by_base: dict[str, list[CatalogRecord]] = defaultdict(list)
    for record in records:
        product_records_by_base[record.base_group_key].append(record)

    return IndexedCatalog(
        index=index,
        base_records=base_records,
        product_records=records,
        records_by_prefix_sort=records_by_prefix_sort,
        product_records_by_base=dict(product_records_by_base),
    )


def make_case(
    plan: CategoryPlan,
    catalog: IndexedCatalog,
    record: CatalogRecord | None,
    input_value: str,
    error_type: str,
    mutation_note: str,
    *,
    expected: str | None = None,
    expected_behavior: str = "match",
    collision_with: str = "",
    danger: Danger | None = None,
    preserve_query_text: bool = False,
    case_subcategory: str = "standard",
    unreadable_continuation: bool = False,
) -> GeneratedCase:
    """Create a generated row with validation, collision detection, and provenance."""

    query = normalize_query_for_output(input_value, preserve_query_text)
    if not compact_key(query) and expected_behavior != "no_match":
        raise ValueError(f"{plan.category} generated an empty searchable query from {input_value!r}")

    expected_value = expected or (record.base_group_key if record else NO_MATCH_EXPECTED)
    source_base = record.base_group_key if record else ""
    source_id = record.candidate_id if record else ""
    collision = collision_with
    if not collision and record is not None and expected_behavior == "match":
        collision = catalog.index.collision_names_for(query, record.base_group_key)

    exact_collision_names = []
    if record is not None and expected_behavior == "match":
        exact_collision_names = [
            item.base_group_key
            for item in catalog.index.base_by_compact.get(compact_key(query), [])
            if item.base_group_key != expected_value
        ]
    resolved_subcategory = case_subcategory
    if exact_collision_names and case_subcategory == "standard":
        resolved_subcategory = "exact_real_name_collision"

    resolved_danger = danger or plan.default_danger
    if collision and record is not None and resolved_danger == "SAFE":
        resolved_danger = (
            "DANGEROUS"
            if catalog.index.has_ingredient_collision(record.base_group_key, collision)
            else "CAUTION"
        )

    notes = (
        f"{mutation_note}; plan_category={plan.number}; plan_description={plan.description}; "
        f"case_subcategory={resolved_subcategory}; "
        f"source_id={source_id or 'none'}; generated_by={plan.generator_function}"
    )
    return GeneratedCase(
        input_value=query,
        expected=expected_value,
        error_type=error_type,
        category=plan.category,
        case_subcategory=resolved_subcategory,
        unreadable_continuation=unreadable_continuation,
        difficulty="MEDIUM",
        danger=resolved_danger,
        collision_with=truncate_collision_cell(collision),
        notes=notes,
        scope=plan.scope,
        tier=plan.tier,
        category_number=plan.number,
        expected_behavior=expected_behavior,
        generator_script=str(Path(__file__).relative_to(ROOT)),
        generator_function=plan.generator_function,
        source_candidate_id=source_id,
        source_base_group=source_base,
    )


def normalize_query_for_output(input_value: str, preserve_query_text: bool) -> str:
    """Normalize most generated queries while preserving copy-paste/case artifacts when needed."""

    if preserve_query_text:
        text = str(input_value).replace("\r", " ")
        if not text:
            raise ValueError("generated preserved query is empty")
        return text
    normalized = normalize_search(input_value)
    if not normalized:
        raise ValueError(f"generated query {input_value!r} normalized to empty")
    return normalized.lower()


def truncate_collision_cell(collision: str) -> str:
    """Cap collision text so one prefix category cannot create unreadable CSV cells."""

    names = [part.strip() for part in collision.split(";") if part.strip()]
    return "; ".join(names[:MAX_COLLISION_NAMES_IN_CELL])


def select_category_cases(plan: CategoryPlan, candidates: list[GeneratedCase]) -> list[GeneratedCase]:
    """Deduplicate and deterministically sample a category to its target count."""

    deduped: dict[tuple[str, str, str, str], GeneratedCase] = {}
    for case in candidates:
        if len(compact_key(case.input_value)) < MIN_MUTATED_COMPACT_LENGTH and case.expected_behavior == "match":
            continue
        key = (case.category, case.input_value, case.expected, case.error_type)
        deduped.setdefault(key, case)

    if len(deduped) < plan.target_count:
        raise RuntimeError(
            f"{plan.category} only produced {len(deduped)} unique cases; target is {plan.target_count}"
        )

    rows = list(deduped.values())
    rows.sort(
        key=lambda case: (
            0 if case.collision_with else 1,
            stable_hash(f"{SAMPLING_NAMESPACE}|{case.category}|{case.input_value}|{case.expected}|{case.error_type}"),
        )
    )
    return rows[: plan.target_count]


def assign_difficulties(plan: CategoryPlan, cases: list[GeneratedCase]) -> list[GeneratedCase]:
    """Assign exact category-level difficulty counts from the plan percentages."""

    quotas = difficulty_quotas(plan.difficulty_mix, len(cases))
    ordered = sorted(
        cases,
        key=lambda case: stable_hash(f"difficulty|{case.category}|{case.input_value}|{case.expected}|{case.error_type}"),
    )
    assigned: list[GeneratedCase] = []
    cursor = 0
    for difficulty, count in quotas:
        for case in ordered[cursor : cursor + count]:
            assigned.append(replace(case, difficulty=difficulty))
        cursor += count
    assigned.sort(key=lambda case: (case.category_number, case.error_type, case.input_value, case.expected))
    return assigned


def difficulty_quotas(mix: DifficultyMix, total: int) -> list[tuple[Difficulty, int]]:
    """Convert fractional difficulty mix to exact integer quotas."""

    pairs = mix.as_pairs()
    raw_counts = [(label, fraction * total) for label, fraction in pairs]
    floors = [(label, int(value)) for label, value in raw_counts]
    remainder = total - sum(count for _, count in floors)
    fractions = sorted(
        ((value - int(value), label) for label, value in raw_counts),
        reverse=True,
    )
    counts = dict(floors)
    for _, label in fractions[:remainder]:
        counts[label] += 1
    return [(label, counts[label]) for label, _ in pairs if counts[label] > 0]


def stable_hash(value: str) -> str:
    """Return a deterministic hex digest used for stable sampling."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def top_base_records(catalog: IndexedCatalog, count: int) -> list[CatalogRecord]:
    """Return the first N base records by canonical catalog order."""

    return catalog.base_records[:count]


def all_base_records(catalog: IndexedCatalog) -> list[CatalogRecord]:
    """Return all usable base records."""

    return catalog.base_records


def generate_single_letter_visual_confusion(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Apply visual single-letter replacements from the plan matrix."""

    replacements = bidirectional_group_replacements(
        ("AOUE", "ILT", "HNBR", "MN", "GQY", "UVW", "FTL", "ECO", "PFR", "CGOQ", "BD", "IJT", "MW")
    )
    return single_char_replacement_cases(plan, catalog, all_base_records(catalog), replacements, "visual")


def generate_single_letter_phonetic_confusion(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Apply sound-alike single-letter replacements."""

    replacements = bidirectional_group_replacements(("BP", "DT", "GK", "SZ", "FV", "CKQ"))
    return single_char_replacement_cases(plan, catalog, all_base_records(catalog), replacements, "phonetic")


def generate_multi_char_phonetic_confusion(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Apply multi-character phonetic rewrites across the full catalog."""

    pairs = (
        ("PH", "F"), ("F", "PH"), ("CK", "K"), ("K", "CK"), ("X", "KS"),
        ("KS", "X"), ("CKS", "X"), ("QU", "KW"), ("KW", "QU"), ("QU", "CW"),
        ("GH", "G"), ("TH", "T"), ("TH", "S"), ("GHT", "T"), ("WH", "W"),
        ("SH", "CH"), ("CH", "SH"), ("TION", "SHUN"), ("Y", "I"), ("I", "Y"),
        ("Y", "EE"),
    )
    return substring_replacement_cases(plan, catalog, all_base_records(catalog), pairs, "multi_phonetic")


def generate_ligature_confusion(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Apply visual ligature merges and splits from the plan."""

    pairs = (
        ("RN", "M"), ("M", "RN"), ("CL", "D"), ("D", "CL"), ("LI", "H"),
        ("H", "LI"), ("RI", "N"), ("AL", "D"), ("NN", "M"), ("VV", "W"),
        ("W", "UU"), ("IA", "A"), ("II", "U"),
    )
    return substring_replacement_cases(plan, catalog, all_base_records(catalog), pairs, "ligature")


def generate_single_char_deletion_position_weighted(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Delete one character and pre-balance by the plan's position weights."""

    buckets: dict[str, list[GeneratedCase]] = defaultdict(list)
    for record in all_base_records(catalog):
        base = record.base_group_compact
        if len(base) < 4:
            continue
        for pos, char in enumerate(base):
            if pos == 0:
                bucket = "first_char"
            elif pos == len(base) - 1:
                bucket = "last_char"
            elif char in VOWELS:
                bucket = "middle_vowel"
            else:
                bucket = "middle_consonant"
            mutated = base[:pos] + base[pos + 1 :]
            buckets[bucket].append(
                make_case(
                    plan,
                    catalog,
                    record,
                    mutated,
                    f"deletion_{bucket}_pos_{pos}",
                    f"deleted {char} at compact position {pos}; bucket={bucket}",
                )
            )
    weighted = take_weighted_buckets(
        buckets,
        plan.target_count,
        {"last_char": 0.40, "middle_vowel": 0.30, "middle_consonant": 0.20, "first_char": 0.10},
    )
    return weighted


def generate_single_char_insertion(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Insert duplicated letters, adjacent-key letters, and extra vowels."""

    neighbors = qwerty_neighbors()
    out: list[GeneratedCase] = []
    for record in all_base_records(catalog):
        base = record.base_group_compact
        if len(base) < 4:
            continue
        positions = stable_positions(len(base), 5)
        for pos in positions:
            before = base[pos - 1] if pos > 0 else base[0]
            insertions = [
                ("duplicate_letter", before),
                ("adjacent_key_letter", (neighbors.get(before) or ["H"])[0]),
                ("extra_vowel", VOWELS[(pos + len(base)) % len(VOWELS)]),
            ]
            for label, inserted in insertions:
                mutated = base[:pos] + inserted + base[pos:]
                out.append(
                    make_case(
                        plan,
                        catalog,
                        record,
                        mutated,
                        f"insertion_{label}_at_pos_{pos}",
                        f"inserted {inserted} at compact position {pos}; insertion_type={label}",
                    )
                )
    return out


def generate_transposition_position_weighted(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Swap adjacent characters and weight later positions more heavily."""

    buckets: dict[str, list[GeneratedCase]] = defaultdict(list)
    for record in all_base_records(catalog):
        base = record.base_group_compact
        for pos in range(len(base) - 1):
            if base[pos] == base[pos + 1]:
                continue
            mutated = base[:pos] + base[pos + 1] + base[pos] + base[pos + 2 :]
            ratio = pos / max(len(base) - 1, 1)
            bucket = "late" if ratio >= 0.60 else "middle" if ratio >= 0.30 else "early"
            buckets[bucket].append(
                make_case(
                    plan,
                    catalog,
                    record,
                    mutated,
                    f"transposition_{bucket}_pos_{pos}",
                    f"swapped compact positions {pos} and {pos + 1}; bucket={bucket}",
                )
            )
    return take_weighted_buckets(buckets, plan.target_count, {"late": 0.50, "middle": 0.35, "early": 0.15})


def generate_truncation_doctor_abbreviation(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate prefix truncations at lengths 3 through 6 with collision notes."""

    out: list[GeneratedCase] = []
    for record in all_base_records(catalog):
        base = record.base_group_compact
        for length in (3, 4, 5, 6):
            if len(base) <= length:
                continue
            prefix = base[:length]
            collisions = prefix_collision_names(catalog, prefix, record.base_group_key)
            out.append(
                make_case(
                    plan,
                    catalog,
                    record,
                    prefix,
                    f"truncation_prefix_len_{length}",
                    f"typed first {length} compact characters; prefix_collision_count={count_collision_names(collisions)}",
                    collision_with=collisions,
                    danger=("DANGEROUS" if collisions and catalog.index.has_ingredient_collision(record.base_group_key, collisions) else "CAUTION"),
                )
            )
    return out


def generate_two_error_combinations(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate controlled edit-distance-two style chains."""

    chains = (
        ("vowel_plus_phonetic", ("vowel", "phonetic")),
        ("deletion_plus_phonetic", ("delete", "phonetic")),
        ("transposition_plus_deletion", ("transpose", "delete")),
        ("visual_plus_phonetic", ("visual", "phonetic")),
        ("ligature_plus_vowel", ("ligature", "vowel")),
    )
    return chained_error_cases(plan, catalog, chains, variants_per_record=4)


def generate_three_error_combinations(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate controlled three-error chains."""

    chains = (
        ("vowel_phonetic_deletion", ("vowel", "phonetic", "delete")),
        ("visual_visual_phonetic", ("visual", "visual", "phonetic")),
        ("ligature_vowel_transpose", ("ligature", "vowel", "transpose")),
        ("keyboard_vowel_delete", ("keyboard", "vowel", "delete")),
    )
    return chained_error_cases(plan, catalog, chains, variants_per_record=3)


def generate_speed_typing_errors(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate repeated, skipped, and stuttered typing artifacts."""

    out: list[GeneratedCase] = []
    for record in all_base_records(catalog):
        base = record.base_group_compact
        if len(base) < 4:
            continue
        mutations = [
            ("repeat_last_letter", base + base[-1], "repeated final letter"),
            ("double_first_letter", base[0] + base, "doubled first letter"),
            ("skip_second_letter", base[0] + base[2:], "skipped second compact character"),
            ("stutter_prefix_2", base[:2] + base, "stuttered first two compact characters"),
            ("stutter_prefix_3", base[:3] + base, "stuttered first three compact characters"),
        ]
        for error_type, mutated, note in mutations:
            out.append(make_case(plan, catalog, record, mutated, error_type, note))
    return out


def generate_wrong_vowels_in_consonant_frame(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Change one to three vowels while preserving consonant positions."""

    out: list[GeneratedCase] = []
    for record in all_base_records(catalog):
        for count in (1, 2, 3):
            for offset in range(3):
                mutated = change_some_vowels(record.base_group_compact, count, offset)
                if mutated and mutated != record.base_group_compact:
                    out.append(
                        make_case(
                            plan,
                            catalog,
                            record,
                            mutated,
                            f"wrong_{count}_vowels_variant_{offset}",
                            f"changed {count} vowel positions while preserving consonants",
                        )
                    )
    return out


def generate_punctuation_whitespace_copy_paste_artifacts(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Wrap exact names in punctuation and whitespace artifacts."""

    out: list[GeneratedCase] = []
    # The plan's 100-family / 10-pattern recipe is the baseline. The catalog
    # contains a few duplicate-looking base families after punctuation artifacts
    # are preserved, so we use a slightly wider source pool and still sample
    # exactly 1,000 rows. This preserves the category intent without silently
    # accepting fewer rows.
    records = top_base_records(catalog, 125)
    for record in records:
        name = record.base_group_key.lower()
        tokens = name.split()
        doubled_space = "  ".join(tokens) if len(tokens) > 1 else f"{name[:2]}  {name[2:]}"
        patterns = [
            f" {name}",
            f"{name} ",
            f"  {name}  ",
            f".{name}",
            f"{name},",
            f'"{name}"',
            f"({name})",
            doubled_space,
            f"{name}\t",
            f"[{name}]",
        ]
        for idx, value in enumerate(patterns):
            out.append(
                make_case(
                    plan,
                    catalog,
                    record,
                    value,
                    f"copy_paste_artifact_{idx}",
                    "copy-paste punctuation or whitespace artifact preserved in query text",
                    preserve_query_text=True,
                )
            )
    return out


def generate_case_sensitivity(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate exact names with different letter casing."""

    out: list[GeneratedCase] = []
    # Use more than 100 source families because some short alphanumeric base
    # groups produce identical casing variants. Sampling still returns exactly
    # the 500 rows required by the plan.
    for record in top_base_records(catalog, 125):
        name = record.base_group_key
        variants = [
            ("lowercase", name.lower()),
            ("uppercase", name.upper()),
            ("titlecase", name.title()),
            ("alternating_case", alternating_case(name)),
            ("mixed_case", mixed_case(name)),
        ]
        for label, value in variants:
            out.append(
                make_case(
                    plan,
                    catalog,
                    record,
                    value,
                    f"case_{label}",
                    f"case variant {label}; exact letters unchanged",
                    preserve_query_text=True,
                )
            )
    return out


def generate_number_word_confusion(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Rewrite digits as words and spacing/hyphen variants."""

    out: list[GeneratedCase] = []
    digit_records = [record for record in all_base_records(catalog) if any(char.isdigit() for char in record.base_group_key)]
    for record in digit_records:
        name = record.base_group_key
        variants = number_word_variants(name)
        for idx, value in enumerate(variants):
            out.append(
                make_case(
                    plan,
                    catalog,
                    record,
                    value,
                    f"number_word_variant_{idx}",
                    "digit/name number format rewritten",
                    preserve_query_text=True,
                )
            )
    return out


def generate_embedded_form_strength_parsing(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Combine base names with real strength and form tokens."""

    out: list[GeneratedCase] = []
    for record in catalog.product_records:
        strength = normalize_search(record.strengths_join)
        if not strength:
            continue
        form = form_word_for_route(record.route_family)
        base = record.base_group_key
        degraded = delete_one_preferred_char(record.base_group_compact, 1) or record.base_group_compact
        variants = [
            (f"{base} {strength}", "brand_strength"),
            (f"{base} {strength} {form}", "brand_strength_form"),
            (f"{strength} {base} {form}", "strength_brand_form"),
            (f"{degraded} {strength} {form}", "degraded_brand_strength_form"),
        ]
        for value, label in variants:
            out.append(make_case(plan, catalog, record, value, label, "embedded strength/form tokens"))
    return out


def generate_dangerous_ed1_pairs(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Find one-edit-apart different-ingredient pairs and test both sides."""

    pairs = find_edit_distance_one_pairs(catalog)
    out: list[GeneratedCase] = []
    for left, right in pairs:
        for expected_record, colliding_record in ((left, right), (right, left)):
            collision = colliding_record.base_group_key
            out.append(
                make_case(
                    plan,
                    catalog,
                    expected_record,
                    expected_record.base_group_key,
                    "dangerous_ed1_exact_pair",
                    "exact query has an edit-distance-one different-ingredient neighbor; UI should expose ambiguity",
                    collision_with=collision,
                    danger="DANGEROUS",
                )
            )
            # The catalog has a finite number of natural dangerous ed=1 pairs.
            # To hit the 5,000-row safety target without hand-authored cases, we
            # keep every discovered pair and generate several deterministic
            # degraded variants from each side. These variants test whether the
            # ambiguity survives when the typed query is also noisy.
            degraded_variants = {
                "dangerous_ed1_vowel_variant_0": change_some_vowels(expected_record.base_group_compact, 1, 0),
                "dangerous_ed1_vowel_variant_1": change_some_vowels(expected_record.base_group_compact, 1, 1),
                "dangerous_ed1_deletion_variant_0": delete_one_preferred_char(expected_record.base_group_compact, 0),
                "dangerous_ed1_deletion_variant_1": delete_one_preferred_char(expected_record.base_group_compact, 1),
                "dangerous_ed1_transpose_variant_0": transpose_at_offset(expected_record.base_group_compact, 0),
                "dangerous_ed1_transpose_variant_1": transpose_at_offset(expected_record.base_group_compact, 2),
                "dangerous_ed1_phonetic_variant_0": apply_named_operation(expected_record.base_group_compact, "phonetic", 0),
                "dangerous_ed1_phonetic_variant_1": apply_named_operation(expected_record.base_group_compact, "phonetic", 2),
                "dangerous_ed1_visual_variant_0": apply_named_operation(expected_record.base_group_compact, "visual", 0),
                "dangerous_ed1_keyboard_variant_0": apply_named_operation(expected_record.base_group_compact, "keyboard", 0),
            }
            for error_type, degraded in degraded_variants.items():
                if degraded and degraded != expected_record.base_group_compact:
                    out.append(
                        make_case(
                            plan,
                            catalog,
                            expected_record,
                            degraded,
                            error_type,
                            "extra deterministic typo added to a dangerous edit-distance-one family",
                            collision_with=collision,
                            danger="DANGEROUS",
                        )
                    )
    return out


def generate_substring_traps(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate short-prefix and long-name-truncated traps."""

    pairs = find_prefix_pairs_with_different_ingredients(catalog)
    out: list[GeneratedCase] = []
    for short, long in pairs:
        out.append(
            make_case(
                plan,
                catalog,
                short,
                short.base_group_key,
                "substring_short_exact",
                "short commercial family is a prefix of longer different-ingredient family",
                collision_with=long.base_group_key,
                danger="DANGEROUS",
            )
        )
        long_truncated = long.base_group_compact[: len(short.base_group_compact)]
        out.append(
            make_case(
                plan,
                catalog,
                long,
                long_truncated,
                "substring_long_truncated_to_short",
                "user can read the short prefix and confirms that unreadable characters continue after it",
                collision_with=short.base_group_key,
                danger="DANGEROUS",
                case_subcategory="known_prefix_unreadable_continuation",
                unreadable_continuation=True,
            )
        )
    return out


def generate_negative_no_match_expected(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate no-match inputs from garbage, metadata-only, and non-catalog strings."""

    out: list[GeneratedCase] = []
    base_set = {record.base_group_compact for record in all_base_records(catalog)}
    fixed_values = [
        "antibiotic",
        "pain killer",
        "blood pressure medicine",
        "foreign brand not in egypt",
        "unknown imported supplement",
        "tablet 500 mg",
        "cream only",
        "take after meal",
        "rx number missing",
        "price net public",
    ]
    for value in fixed_values:
        out.append(no_match_case(plan, catalog, value, "negative_fixed_phrase", "fixed negative phrase"))
    for idx, record in enumerate(catalog.product_records[:4_000]):
        metadata = record.drug_class_top or record.route_family or record.manufacturer_primary
        if metadata and compact_key(metadata) not in base_set:
            out.append(no_match_case(plan, catalog, metadata, "negative_catalog_metadata", "catalog metadata used without a brand"))
        if record.strengths_join:
            out.append(no_match_case(plan, catalog, record.strengths_join, "negative_strength_only", "strength-only query"))
        random_value = deterministic_garbage_string(idx, base_set)
        out.append(no_match_case(plan, catalog, random_value, "negative_random_string", "deterministic non-catalog random string"))
    for idx in range(4_000, 8_000):
        random_value = deterministic_garbage_string(idx, base_set)
        out.append(no_match_case(plan, catalog, random_value, "negative_random_string", "deterministic non-catalog random string"))
    return out


def generate_contradictory_form_route(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Pair real brands with forms that contradict their catalog route family."""

    out: list[GeneratedCase] = []
    for record in all_base_records(catalog):
        wrong_forms = contradictory_forms_for_route(record.route_family)
        for form in wrong_forms:
            out.append(
                make_case(
                    plan,
                    catalog,
                    record,
                    f"{record.base_group_key} {form}",
                    f"contradictory_form_{form.replace(' ', '_')}",
                    f"added form/route token not compatible with route_family={record.route_family}",
                    danger="CAUTION",
                )
            )
    return out


def generate_cancelled_na_drug_lookup(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate lookup cases for rows with cancellation or review warnings."""

    out: list[GeneratedCase] = []
    flagged = [
        record for record in catalog.product_records
        if has_status_warning(record)
    ]
    for record in flagged:
        base = record.base_group_key
        typo = delete_one_preferred_char(record.base_group_compact, 1) or record.base_group_compact
        form = form_word_for_route(record.route_family)
        variants = [
            ("cancelled_exact", base, "status-warning exact lookup"),
            ("cancelled_one_typo", typo, "status-warning lookup with one typo"),
            ("cancelled_form_hint", f"{base} {form}", "status-warning lookup with form hint"),
        ]
        for error_type, value, note in variants:
            out.append(make_case(plan, catalog, record, value, error_type, note, danger="CAUTION"))
    return out


def generate_score_gap_ambiguity_detection(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate catalog-collision proxy cases for score-gap ambiguity.

    The plan defines this category as engine-mined. To keep the v2 dataset fully
    script-generated without running a search engine inside data generation, this
    function uses high-risk catalog neighborhoods: short prefixes and edit-one
    pairs with different ingredients. The notes explicitly mark these rows as a
    proxy so they can later be replaced by live score mining.
    """

    out: list[GeneratedCase] = []
    for prefix, records in ambiguous_prefix_records(catalog, min_ingredients=2):
        collisions = "; ".join(record.base_group_key for record in records[:MAX_COLLISION_NAMES_IN_CELL])
        out.append(
            make_case(
                plan,
                catalog,
                None,
                prefix,
                "score_gap_prefix_collision_proxy",
                "engine-independent proxy: short prefix has multiple ingredient families",
                expected=AMBIGUOUS_EXPECTED,
                expected_behavior="ambiguous",
                collision_with=collisions,
                danger="DANGEROUS",
            )
        )
    for left, right in find_edit_distance_one_pairs(catalog):
        blended = shared_prefix(left.base_group_compact, right.base_group_compact)
        if len(blended) >= 3:
            out.append(
                make_case(
                    plan,
                    catalog,
                    None,
                    blended,
                    "score_gap_ed1_collision_proxy",
                    "engine-independent proxy: edit-distance-one pair should not get confident top-1",
                    expected=AMBIGUOUS_EXPECTED,
                    expected_behavior="ambiguous",
                    collision_with=f"{left.base_group_key}; {right.base_group_key}",
                    danger="DANGEROUS",
                )
            )
    grouped_len2: dict[str, list[CatalogRecord]] = defaultdict(list)
    for record in all_base_records(catalog):
        if len(record.base_group_compact) >= 2:
            grouped_len2[record.base_group_compact[:2]].append(record)
    for prefix, records in grouped_len2.items():
        ingredient_keys = {record.ingredient_key for record in records if record.ingredient_key}
        if len(ingredient_keys) < 2:
            continue
        unique = list({record.base_group_key: record for record in records}.values())
        unique.sort(key=lambda item: item.base_group_key)
        collisions = "; ".join(record.base_group_key for record in unique[:MAX_COLLISION_NAMES_IN_CELL])
        out.append(
            make_case(
                plan,
                catalog,
                None,
                prefix.lower(),
                "score_gap_short_prefix_len2_proxy",
                "engine-independent proxy: two-character prefix has multiple ingredient families",
                expected=AMBIGUOUS_EXPECTED,
                expected_behavior="ambiguous",
                collision_with=collisions,
                danger="DANGEROUS",
            )
        )
    grouped_suffix2: dict[str, list[CatalogRecord]] = defaultdict(list)
    for record in all_base_records(catalog):
        if len(record.base_group_compact) >= 4:
            grouped_suffix2[record.base_group_compact[-2:]].append(record)
    for suffix, records in grouped_suffix2.items():
        ingredient_keys = {record.ingredient_key for record in records if record.ingredient_key}
        if len(ingredient_keys) < 2:
            continue
        unique = list({record.base_group_key: record for record in records}.values())
        unique.sort(key=lambda item: item.base_group_key)
        collisions = "; ".join(record.base_group_key for record in unique[:MAX_COLLISION_NAMES_IN_CELL])
        out.append(
            make_case(
                plan,
                catalog,
                None,
                suffix.lower(),
                "score_gap_short_suffix_len2_proxy",
                "engine-independent proxy: two-character suffix has multiple ingredient families",
                expected=AMBIGUOUS_EXPECTED,
                expected_behavior="ambiguous",
                collision_with=collisions,
                danger="DANGEROUS",
            )
        )
    return out


def generate_ocr_letter_digit_confusion(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Apply OCR letter/digit replacements at every possible position."""

    replacements = {
        "O": ["0", "D", "Q"],
        "D": ["O", "0"],
        "Q": ["O", "0"],
        "I": ["1", "L"],
        "L": ["1", "I"],
        "S": ["5"],
        "B": ["8"],
        "Z": ["2"],
        "G": ["6"],
        "9": ["G", "Q"],
    }
    return single_char_replacement_cases(plan, catalog, all_base_records(catalog), replacements, "ocr")


def generate_ocr_plus_other_error_combined(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Apply OCR then one deletion, phonetic, or vowel mutation."""

    replacements = {"O": ["0"], "I": ["1"], "S": ["5"], "B": ["8"], "Z": ["2"], "G": ["6"], "L": ["1"]}
    out: list[GeneratedCase] = []
    for record in all_base_records(catalog):
        base = record.base_group_compact
        for pos, char in enumerate(base):
            for replacement in replacements.get(char, []):
                ocr = base[:pos] + replacement + base[pos + 1 :]
                variants = [
                    ("ocr_plus_deletion", delete_one_preferred_char(ocr, 1)),
                    ("ocr_plus_vowel", change_some_vowels(ocr, 1, pos)),
                    ("ocr_plus_phonetic", apply_named_operation(ocr, "phonetic", pos)),
                ]
                for label, mutated in variants:
                    if mutated and mutated != base:
                        out.append(
                            make_case(
                                plan,
                                catalog,
                                record,
                                mutated,
                                f"{label}_pos_{pos}",
                                f"OCR {char}->{replacement} at {pos}, then {label}",
                            )
                        )
    return out


def generate_double_letter_reduction_expansion(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate double-letter reductions and expansions."""

    out: list[GeneratedCase] = []
    double_pattern = re.compile(r"([A-Z])\1")
    for record in all_base_records(catalog):
        base = record.base_group_compact
        for match in double_pattern.finditer(base):
            pos = match.start()
            mutated = base[:pos] + base[pos + 1 :]
            char = base[pos]
            out.append(
                make_case(
                    plan,
                    catalog,
                    record,
                    mutated,
                    f"double_reduction_{char}{char}_to_{char}_pos_{pos}",
                    f"reduced double {char}{char} at compact position {pos}",
                )
            )
        for pos, char in enumerate(base):
            if char in "BCDFGHJKLMNPRSTVZ":
                mutated = base[:pos] + char + base[pos:]
                out.append(
                    make_case(
                        plan,
                        catalog,
                        record,
                        mutated,
                        f"double_expansion_{char}_to_{char}{char}_pos_{pos}",
                        f"expanded {char} to double {char}{char} at compact position {pos}",
                    )
                )
    return out


def generate_keyboard_adjacent_sampled(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate sampled adjacent-key substitutions."""

    neighbors = qwerty_neighbors()
    out: list[GeneratedCase] = []
    for record in all_base_records(catalog):
        base = record.base_group_compact
        for pos in stable_positions(len(base), 3):
            char = base[pos]
            for replacement in (neighbors.get(char) or [])[:2]:
                mutated = base[:pos] + replacement + base[pos + 1 :]
                out.append(
                    make_case(
                        plan,
                        catalog,
                        record,
                        mutated,
                        f"keyboard_adjacent_{char}_to_{replacement}_sampled_pos_{pos}",
                        f"sampled QWERTY adjacent-key typo {char}->{replacement} at position {pos}",
                    )
                )
    return out


def generate_four_plus_error_combinations(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate four-or-more-error chains."""

    chains = (
        ("two_vowels_phonetic_deletion", ("vowel", "vowel", "phonetic", "delete")),
        ("ligature_two_phonetic_delete", ("ligature", "phonetic", "phonetic", "delete")),
        ("visual_keyboard_vowel_transpose", ("visual", "keyboard", "vowel", "transpose")),
        ("ocr_vowel_phonetic_delete", ("ocr", "vowel", "phonetic", "delete")),
    )
    return chained_error_cases(plan, catalog, chains, variants_per_record=3)


def generate_consonant_frame_wrong_vowels_heavy(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate heavy wrong-vowel cases while preserving consonant clues."""

    out: list[GeneratedCase] = []
    for record in all_base_records(catalog):
        base = record.base_group_compact
        all_wrong = change_all_vowels(base)
        if all_wrong and all_wrong != base:
            out.append(
                make_case(
                    plan,
                    catalog,
                    record,
                    all_wrong,
                    "all_vowels_wrong",
                    "changed every vowel to a different vowel",
                )
            )
        skeleton_inserted = insert_wrong_vowels_into_skeleton(base)
        if skeleton_inserted and skeleton_inserted != base:
            out.append(
                make_case(
                    plan,
                    catalog,
                    record,
                    skeleton_inserted,
                    "skeleton_with_wrong_inserted_vowels",
                    "removed vowels, then inserted plausible but wrong vowels",
                )
            )
        for offset in range(2):
            partial = change_some_vowels(base, 4, offset)
            if partial and partial != base:
                out.append(
                    make_case(
                        plan,
                        catalog,
                        record,
                        partial,
                        f"four_wrong_vowels_variant_{offset}",
                        "changed up to four vowel positions",
                    )
                )
    return out


def generate_multi_word_name_fragmentation(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate dropped, merged, abbreviated, and standalone-token fragments."""

    out: list[GeneratedCase] = []
    for record in all_base_records(catalog):
        tokens = [token for token in normalize_search(record.base_group_key).split() if token]
        if len(tokens) < 2:
            continue
        variants = [
            ("words_merged", "".join(tokens), "removed spaces between all tokens"),
            ("drop_last_word", " ".join(tokens[:-1]), "dropped last token"),
            ("drop_first_word", " ".join(tokens[1:]), "dropped first token"),
            ("abbreviated_tokens", " ".join(token[:3] for token in tokens), "abbreviated each token to three letters"),
        ]
        for idx, token in enumerate(tokens):
            if len(token) >= 3:
                variants.append((f"standalone_token_{idx}", token, "searched one token from a multi-word family"))
        for error_type, value, note in variants:
            out.append(make_case(plan, catalog, record, value, error_type, note, danger="CAUTION"))
    return out


def generate_autocorrect_artifacts(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate phone-autocorrect-like word replacements and inserted spaces."""

    out: list[GeneratedCase] = []
    for record in all_base_records(catalog):
        base = record.base_group_compact
        if len(base) < 5:
            continue
        split = max(2, len(base) // 2)
        variants = [
            ("autocorrect_space_insert_mid", f"{base[:split]} {base[split:]}", "phone inserted word boundary"),
            ("autocorrect_space_insert_after_prefix", f"{base[:3]} {base[3:]}", "phone inserted space after prefix"),
        ]
        nearest = nearest_autocorrect_word(base)
        if nearest:
            variants.append(("autocorrect_word_replacement", nearest, "drug name replaced by a nearby English word"))
        vowel_corrected = change_some_vowels(base, 2, 1)
        if vowel_corrected:
            variants.append(("autocorrect_vowel_correction", vowel_corrected, "phone guessed a more common vowel pattern"))
        for error_type, value, note in variants:
            out.append(make_case(plan, catalog, record, value, error_type, note))
    return out


def generate_exact_match_baseline(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate exact commercial-family matches."""

    out: list[GeneratedCase] = []
    records = top_base_records(catalog, 500)
    # Generate more candidates than the final target because a few catalog base
    # groups collapse to duplicate exact query rows after normalization.
    remaining = deterministic_sample(all_base_records(catalog)[500:], 2_000, "exact_match_baseline")
    for record in [*records, *remaining]:
        out.append(
            make_case(
                plan,
                catalog,
                record,
                record.base_group_key,
                "exact_base_group",
                "exact commercial family from catalog",
                preserve_query_text=True,
            )
        )
    return out


def generate_exact_match_with_strength(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate exact brand plus real strength tokens."""

    out: list[GeneratedCase] = []
    for record in catalog.product_records:
        if not record.strengths_join:
            continue
        out.append(
            make_case(
                plan,
                catalog,
                record,
                f"{record.base_group_key} {record.strengths_join}",
                "exact_brand_with_real_strength",
                "exact commercial family plus real catalog strength",
                preserve_query_text=True,
            )
        )
        out.append(
            make_case(
                plan,
                catalog,
                record,
                record.commercial_name_en,
                "exact_product_name_with_strength",
                "exact product commercial name including strength/package text",
                preserve_query_text=True,
            )
        )
    return out


def generate_keyboard_shift_whole_word(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Shift every character one key left or right."""

    left_map, right_map = keyboard_shift_maps()
    out: list[GeneratedCase] = []
    for record in all_base_records(catalog):
        base = record.base_group_compact
        for direction, mapping in (("left", left_map), ("right", right_map)):
            shifted = "".join(mapping.get(char, char) for char in base)
            if shifted != base:
                out.append(
                    make_case(
                        plan,
                        catalog,
                        record,
                        shifted,
                        f"keyboard_shift_{direction}",
                        f"whole compact name shifted one key {direction}",
                    )
                )
    return out


def generate_prefix_ambiguity_awareness(plan: CategoryPlan, catalog: IndexedCatalog) -> list[GeneratedCase]:
    """Generate very short ambiguous prefixes with many ingredient families."""

    out: list[GeneratedCase] = []
    for prefix, records in ambiguous_prefix_records(catalog, min_ingredients=5):
        collisions = "; ".join(record.base_group_key for record in records[:MAX_COLLISION_NAMES_IN_CELL])
        out.append(
            make_case(
                plan,
                catalog,
                None,
                prefix,
                f"ambiguous_prefix_len_{len(prefix)}",
                "short prefix maps to at least five different ingredient families",
                expected=AMBIGUOUS_EXPECTED,
                expected_behavior="ambiguous",
                collision_with=collisions,
                danger="CAUTION",
            )
        )
    for prefix, records in ambiguous_prefix_records(catalog, min_ingredients=4):
        collisions = "; ".join(record.base_group_key for record in records[:MAX_COLLISION_NAMES_IN_CELL])
        out.append(
            make_case(
                plan,
                catalog,
                None,
                prefix,
                f"ambiguous_prefix_len_{len(prefix)}_min4_ingredient_families",
                "short prefix maps to at least four different ingredient families; fallback bucket used to satisfy v2 target count",
                expected=AMBIGUOUS_EXPECTED,
                expected_behavior="ambiguous",
                collision_with=collisions,
                danger="CAUTION",
            )
        )
    return out


def single_char_replacement_cases(
    plan: CategoryPlan,
    catalog: IndexedCatalog,
    records: Sequence[CatalogRecord],
    replacements: dict[str, list[str]],
    label: str,
) -> list[GeneratedCase]:
    """Generate same-position single-character replacements."""

    out: list[GeneratedCase] = []
    for record in records:
        base = record.base_group_compact
        for pos, char in enumerate(base):
            for replacement in replacements.get(char, []):
                mutated = base[:pos] + replacement + base[pos + 1 :]
                if mutated == base:
                    continue
                out.append(
                    make_case(
                        plan,
                        catalog,
                        record,
                        mutated,
                        f"{label}_{char}_to_{replacement}_pos_{pos}",
                        f"{label} same-position replacement {char}->{replacement} at compact position {pos}",
                    )
                )
    return out


def substring_replacement_cases(
    plan: CategoryPlan,
    catalog: IndexedCatalog,
    records: Sequence[CatalogRecord],
    pairs: Sequence[tuple[str, str]],
    label: str,
) -> list[GeneratedCase]:
    """Generate first-occurrence substring replacement cases."""

    out: list[GeneratedCase] = []
    for record in records:
        base = record.base_group_compact
        for source, replacement in pairs:
            start = base.find(source)
            while start != -1:
                mutated = base[:start] + replacement + base[start + len(source) :]
                if mutated != base:
                    out.append(
                        make_case(
                            plan,
                            catalog,
                            record,
                            mutated,
                            f"{label}_{source.lower()}_to_{replacement.lower()}_pos_{start}",
                            f"{label} substring replacement {source}->{replacement} at compact position {start}",
                        )
                    )
                start = base.find(source, start + 1)
    return out


def chained_error_cases(
    plan: CategoryPlan,
    catalog: IndexedCatalog,
    chains: Sequence[tuple[str, Sequence[str]]],
    variants_per_record: int,
) -> list[GeneratedCase]:
    """Apply named operation chains deterministically to catalog names."""

    out: list[GeneratedCase] = []
    for record in all_base_records(catalog):
        base = record.base_group_compact
        if len(base) < 5:
            continue
        for chain_name, operations in chains:
            for variant in range(variants_per_record):
                current = base
                notes: list[str] = []
                for op_index, operation in enumerate(operations):
                    mutated = apply_named_operation(current, operation, variant + op_index)
                    if not mutated or mutated == current:
                        mutated = fallback_mutation(current, variant + op_index)
                    notes.append(f"{operation}->{mutated}")
                    current = mutated
                if current != base:
                    out.append(
                        make_case(
                            plan,
                            catalog,
                            record,
                            current,
                            f"{chain_name}_variant_{variant}",
                            f"applied chain {chain_name}; operations={' | '.join(notes)}",
                        )
                    )
    return out


def apply_named_operation(value: str, operation: str, offset: int) -> str | None:
    """Apply one named mutation primitive used by chained categories."""

    if operation == "vowel":
        return change_some_vowels(value, 1, offset)
    if operation == "phonetic":
        return replace_first_from_map(value, bidirectional_group_replacements(("BP", "DT", "GK", "SZ", "FV", "CKQ")), offset)
    if operation == "visual":
        return replace_first_from_map(value, bidirectional_group_replacements(("AOUE", "ILT", "HNBR", "MN", "GQY", "UVW", "FTL", "ECO")), offset)
    if operation == "keyboard":
        return replace_first_from_map(value, qwerty_neighbors(), offset)
    if operation == "delete":
        return delete_one_preferred_char(value, offset)
    if operation == "transpose":
        return transpose_at_offset(value, offset)
    if operation == "ligature":
        return replace_first_substring(value, (("RN", "M"), ("M", "RN"), ("CL", "D"), ("D", "CL"), ("LI", "H"), ("H", "LI")), offset)
    if operation == "ocr":
        return replace_first_from_map(value, {"O": ["0"], "I": ["1"], "S": ["5"], "B": ["8"], "Z": ["2"], "G": ["6"]}, offset)
    raise ValueError(f"unknown chained operation {operation}")


def fallback_mutation(value: str, offset: int) -> str:
    """Apply a guaranteed non-empty fallback mutation for chain continuity."""

    deleted = delete_one_preferred_char(value, offset)
    if deleted and deleted != value:
        return deleted
    return value + VOWELS[offset % len(VOWELS)]


def bidirectional_group_replacements(groups: Sequence[str]) -> dict[str, list[str]]:
    """Build replacement lists from groups where every member can become every other member."""

    out: dict[str, set[str]] = defaultdict(set)
    for group in groups:
        for char in group:
            for replacement in group:
                if replacement != char:
                    out[char].add(replacement)
    return {char: sorted(values) for char, values in out.items()}


def qwerty_neighbors() -> dict[str, list[str]]:
    """Return adjacent-key neighbors using horizontal and selected vertical QWERTY relations."""

    neighbors: dict[str, set[str]] = defaultdict(set)
    for row in QWERTY_ROWS:
        for idx, char in enumerate(row):
            if idx > 0:
                neighbors[char].add(row[idx - 1])
            if idx < len(row) - 1:
                neighbors[char].add(row[idx + 1])
    vertical = {
        "A": "QWZ",
        "S": "QWEXZ",
        "D": "WERFCX",
        "F": "ERTGVC",
        "G": "RTYHBV",
        "H": "TYUJNB",
        "J": "YUIKNM",
        "K": "UIOLMJ",
        "L": "OPK",
    }
    for key, values in vertical.items():
        neighbors[key].update(values)
    return {key: sorted(values - {key}) for key, values in neighbors.items()}


def keyboard_shift_maps() -> tuple[dict[str, str], dict[str, str]]:
    """Return maps for whole-word keyboard left and right shifts."""

    left: dict[str, str] = {}
    right: dict[str, str] = {}
    for row in QWERTY_ROWS:
        for idx, char in enumerate(row):
            if idx > 0:
                left[char] = row[idx - 1]
            if idx < len(row) - 1:
                right[char] = row[idx + 1]
    return left, right


def stable_positions(length: int, count: int) -> list[int]:
    """Choose stable positions across a word without depending on randomness."""

    if length <= 0:
        return []
    if length <= count:
        return list(range(length))
    raw = {0, length - 1, length // 2, length // 3, (2 * length) // 3}
    positions = sorted(pos for pos in raw if 0 <= pos < length)
    return positions[:count]


def take_weighted_buckets(
    buckets: dict[str, list[GeneratedCase]],
    total: int,
    weights: dict[str, float],
) -> list[GeneratedCase]:
    """Take deterministic samples from precomputed buckets using target weights."""

    selected: list[GeneratedCase] = []
    for bucket, weight in weights.items():
        target = int(total * weight)
        selected.extend(deterministic_sample(buckets.get(bucket, []), target, f"bucket-{bucket}"))
    if len(selected) < total:
        leftovers = [case for cases in buckets.values() for case in cases if case not in selected]
        selected.extend(deterministic_sample(leftovers, total - len(selected), "bucket-leftover"))
    return selected


def deterministic_sample(items: Sequence[GeneratedCase] | Sequence[CatalogRecord], count: int, salt: str) -> list:
    """Deterministically sample items by stable hash."""

    if count <= 0:
        return []
    ordered = sorted(
        items,
        key=lambda item: stable_hash(f"{SAMPLING_NAMESPACE}|{salt}|{sample_identity(item)}"),
    )
    return list(ordered[:count])


def sample_identity(item: GeneratedCase | CatalogRecord) -> str:
    """Return a stable identity for deterministic sampling."""

    if isinstance(item, GeneratedCase):
        return f"{item.category}|{item.input_value}|{item.expected}|{item.error_type}"
    return f"{item.candidate_id}|{item.base_group_key}|{item.commercial_name_en}"


def change_some_vowels(value: str, count: int, offset: int) -> str | None:
    """Change up to count vowels to different vowels, preserving other characters."""

    positions = [idx for idx, char in enumerate(value) if char in VOWELS]
    if not positions:
        return None
    chars = list(value)
    for idx in positions[offset % len(positions) : offset % len(positions) + count]:
        pos = positions[idx % len(positions)]
        current = chars[pos]
        choices = [vowel for vowel in VOWELS if vowel != current]
        chars[pos] = choices[(offset + pos) % len(choices)]
    return "".join(chars)


def change_all_vowels(value: str) -> str | None:
    """Change every vowel to a deterministic different vowel."""

    chars = list(value)
    changed = False
    for pos, char in enumerate(chars):
        if char in VOWELS:
            choices = [vowel for vowel in VOWELS if vowel != char]
            chars[pos] = choices[pos % len(choices)]
            changed = True
    return "".join(chars) if changed else None


def insert_wrong_vowels_into_skeleton(value: str) -> str | None:
    """Strip vowels, then insert wrong vowels after alternating consonants."""

    skeleton = "".join(char for char in value if char not in VOWELS)
    if len(skeleton) < 3 or skeleton == value:
        return None
    out: list[str] = []
    for idx, char in enumerate(skeleton):
        out.append(char)
        if idx % 2 == 0:
            out.append(VOWELS[(idx + len(value)) % len(VOWELS)])
    return "".join(out)


def replace_first_from_map(value: str, replacements: dict[str, list[str]], offset: int) -> str | None:
    """Replace the first eligible character after offset using a replacement map."""

    if not value:
        return None
    for step in range(len(value)):
        pos = (offset + step) % len(value)
        char = value[pos]
        options = replacements.get(char)
        if options:
            replacement = options[(offset + step) % len(options)]
            return value[:pos] + replacement + value[pos + 1 :]
    return None


def replace_first_substring(value: str, pairs: Sequence[tuple[str, str]], offset: int) -> str | None:
    """Replace the first eligible substring after rotating the pair list."""

    ordered = list(pairs[offset % len(pairs) :]) + list(pairs[: offset % len(pairs)])
    for source, replacement in ordered:
        pos = value.find(source)
        if pos != -1:
            return value[:pos] + replacement + value[pos + len(source) :]
    return None


def delete_one_preferred_char(value: str, offset: int) -> str | None:
    """Delete one character, preferring vowels but falling back to any middle char."""

    if len(value) <= 3:
        return None
    positions = [idx for idx, char in enumerate(value) if char in VOWELS and 0 < idx < len(value) - 1]
    if not positions:
        positions = list(range(1, len(value) - 1))
    pos = positions[offset % len(positions)]
    return value[:pos] + value[pos + 1 :]


def transpose_at_offset(value: str, offset: int) -> str | None:
    """Swap adjacent characters at a deterministic offset."""

    if len(value) < 2:
        return None
    pos = offset % (len(value) - 1)
    if value[pos] == value[pos + 1]:
        pos = (pos + 1) % (len(value) - 1)
    return value[:pos] + value[pos + 1] + value[pos] + value[pos + 2 :]


def prefix_collision_names(catalog: IndexedCatalog, prefix: str, expected: str) -> str:
    """Return semicolon-separated base groups sharing a compact prefix."""

    matches = records_with_prefix(catalog, compact_key(prefix))
    names = [record.base_group_key for record in matches if record.base_group_key != expected]
    return "; ".join(dict.fromkeys(names))


def records_with_prefix(catalog: IndexedCatalog, prefix: str) -> list[CatalogRecord]:
    """Return base records whose compact key starts with prefix."""

    pairs = catalog.records_by_prefix_sort
    keys = [key for key, _ in pairs]
    start = bisect.bisect_left(keys, prefix)
    end = bisect.bisect_right(keys, prefix + "\uffff")
    return [record for key, record in pairs[start:end] if key.startswith(prefix)]


def count_collision_names(collision: str) -> int:
    """Count semicolon-separated collision names."""

    return len([part for part in collision.split(";") if part.strip()])


def find_edit_distance_one_pairs(catalog: IndexedCatalog) -> list[tuple[CatalogRecord, CatalogRecord]]:
    """Find compact-name pairs one edit apart with different ingredient keys."""

    buckets: dict[str, list[CatalogRecord]] = defaultdict(list)
    for record in all_base_records(catalog):
        compact = record.base_group_compact
        if len(compact) < 4:
            continue
        for pos in range(len(compact)):
            buckets[compact[:pos] + compact[pos + 1 :]].append(record)

    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[CatalogRecord, CatalogRecord]] = []
    for records in buckets.values():
        if len(records) < 2 or len(records) > 100:
            continue
        unique = list({record.base_group_key: record for record in records}.values())
        for left_index, left in enumerate(unique):
            for right in unique[left_index + 1 :]:
                if left.ingredient_key == right.ingredient_key:
                    continue
                if not is_edit_distance_one_or_less(left.base_group_compact, right.base_group_compact):
                    continue
                key = tuple(sorted((left.base_group_key, right.base_group_key)))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append((left, right))
    pairs.sort(key=lambda pair: stable_hash(f"ed1|{pair[0].base_group_key}|{pair[1].base_group_key}"))
    return pairs


def is_edit_distance_one_or_less(left: str, right: str) -> bool:
    """Return True when two compact strings differ by at most one edit."""

    if left == right:
        return False
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    short, long = (left, right) if len(left) < len(right) else (right, left)
    for pos in range(len(long)):
        if long[:pos] + long[pos + 1 :] == short:
            return True
    return False


def find_prefix_pairs_with_different_ingredients(catalog: IndexedCatalog) -> list[tuple[CatalogRecord, CatalogRecord]]:
    """Find prefix trap pairs where the short name is a prefix of the long name."""

    pairs: list[tuple[CatalogRecord, CatalogRecord]] = []
    seen: set[tuple[str, str]] = set()
    for short in all_base_records(catalog):
        short_key = short.base_group_compact
        if len(short_key) < 3:
            continue
        matches = records_with_prefix(catalog, short_key)
        for long in matches:
            if long.base_group_key == short.base_group_key:
                continue
            if long.ingredient_key == short.ingredient_key:
                continue
            key = (short.base_group_key, long.base_group_key)
            if key in seen:
                continue
            seen.add(key)
            pairs.append((short, long))
    pairs.sort(key=lambda pair: stable_hash(f"prefix-pair|{pair[0].base_group_key}|{pair[1].base_group_key}"))
    return pairs


def ambiguous_prefix_records(catalog: IndexedCatalog, min_ingredients: int) -> list[tuple[str, list[CatalogRecord]]]:
    """Return compact prefixes that map to at least min_ingredients ingredient keys."""

    grouped: dict[str, list[CatalogRecord]] = defaultdict(list)
    for record in all_base_records(catalog):
        for length in (3, 4):
            if len(record.base_group_compact) >= length:
                grouped[record.base_group_compact[:length]].append(record)
    out: list[tuple[str, list[CatalogRecord]]] = []
    for prefix, records in grouped.items():
        ingredient_keys = {record.ingredient_key for record in records if record.ingredient_key}
        if len(ingredient_keys) >= min_ingredients:
            unique = list({record.base_group_key: record for record in records}.values())
            unique.sort(key=lambda record: record.base_group_key)
            out.append((prefix.lower(), unique))
    out.sort(key=lambda item: stable_hash(f"ambiguous-prefix|{item[0]}"))
    return out


def no_match_case(plan: CategoryPlan, catalog: IndexedCatalog, value: str, error_type: str, note: str) -> GeneratedCase:
    """Build an explicit no-match expected row."""

    return make_case(
        plan,
        catalog,
        None,
        value,
        error_type,
        note,
        expected=NO_MATCH_EXPECTED,
        expected_behavior="no_match",
        danger="DANGEROUS",
    )


def deterministic_garbage_string(index: int, base_set: set[str]) -> str:
    """Return a deterministic random-looking string that is not a catalog base key."""

    alphabet = string.ascii_lowercase
    digest = stable_hash(f"negative-garbage|{index}")
    length = 5 + (index % 8)
    candidate = "".join(alphabet[int(digest[pos : pos + 2], 16) % len(alphabet)] for pos in range(0, length * 2, 2))
    if compact_key(candidate) in base_set:
        return f"{candidate}xx"
    return candidate


def contradictory_forms_for_route(route_family: str) -> list[str]:
    """Return route/form words that should be contradictory for a route family."""

    by_route = {
        "oral_solid": ["suppository", "ear drops", "iv vial"],
        "oral_liquid": ["skin gel", "eye drops", "suppository"],
        "injection": ["tablet", "oral syrup", "skin cream"],
        "topical": ["iv vial", "oral tablet", "eye drops"],
        "ophthalmic": ["oral tablet", "suppository", "skin cream"],
        "otic": ["oral tablet", "eye drops", "iv vial"],
        "rectal": ["oral tablet", "eye drops", "iv vial"],
        "vaginal": ["oral tablet", "ear drops", "iv vial"],
        "spray": ["suppository", "oral tablet", "iv vial"],
    }
    return by_route.get(route_family, ["suppository", "ear drops", "iv vial"])


def form_word_for_route(route_family: str) -> str:
    """Return one common form word for a route family."""

    forms = {
        "oral_solid": "tablet",
        "oral_liquid": "syrup",
        "injection": "vial",
        "topical": "gel",
        "ophthalmic": "eye drops",
        "otic": "ear drops",
        "rectal": "suppository",
        "vaginal": "pessary",
        "spray": "spray",
    }
    return forms.get(route_family, "tablet")


def has_status_warning(record: CatalogRecord) -> bool:
    """Return whether a product row carries a cancellation/N-A/review warning signal."""

    text = normalize_search(
        f"{record.commercial_name_en} {record.review_reasons} {record.drug_class_top} {record.route_family}"
    )
    keywords = ("CANCELLED", "ILLEGAL", "N A", "UNKNOWN", "MISSING", "PLACEHOLDER", "REVIEW")
    return any(keyword in text for keyword in keywords)


def number_word_variants(name: str) -> list[str]:
    """Return number formatting variants for a commercial family."""

    digit_words = {
        "0": "ZERO",
        "1": "ONE",
        "2": "TWO",
        "3": "THREE",
        "4": "FOUR",
        "5": "FIVE",
        "6": "SIX",
        "7": "SEVEN",
        "8": "EIGHT",
        "9": "NINE",
        "12": "TWELVE",
    }
    variants: set[str] = set()
    variants.add(re.sub(r"(\D)(\d)", r"\1 \2", name))
    variants.add(re.sub(r"(\d)(\D)", r"\1 \2", name))
    variants.add(name.replace(" ", ""))
    variants.add(name.replace(" ", "-"))
    for token, word in sorted(digit_words.items(), key=lambda item: -len(item[0])):
        if token in name:
            variants.add(name.replace(token, word))
            variants.add(name.replace(token, f" {word} "))
    return [normalize_search(value) for value in variants if normalize_search(value) and normalize_search(value) != normalize_search(name)]


def alternating_case(value: str) -> str:
    """Return alternating letter case while preserving nonletters."""

    out: list[str] = []
    toggle = False
    for char in value:
        if char.isalpha():
            out.append(char.upper() if toggle else char.lower())
            toggle = not toggle
        else:
            out.append(char)
    return "".join(out)


def mixed_case(value: str) -> str:
    """Return deterministic mixed case."""

    out: list[str] = []
    for idx, char in enumerate(value):
        out.append(char.upper() if idx % 3 == 0 else char.lower())
    return "".join(out)


AUTOCORRECT_WORDS = (
    "argument", "augment", "broken", "banana", "panama", "medium", "nexus",
    "control", "concert", "voltage", "glucose", "flag", "laser", "matrix",
    "motion", "garden", "january", "lipid", "capital", "profile", "serious",
    "vitamin", "saline", "marine", "active", "clinic", "clean", "fresh",
    "extra", "super", "rapid", "normal", "relief", "care", "daily",
)


def nearest_autocorrect_word(compact_name: str) -> str:
    """Return a plausible English autocorrect replacement for a compact drug name."""

    matches = difflib.get_close_matches(compact_name.lower(), AUTOCORRECT_WORDS, n=1, cutoff=0.45)
    return matches[0] if matches else ""


def shared_prefix(left: str, right: str) -> str:
    """Return the shared prefix of two strings."""

    chars: list[str] = []
    for a, b in zip(left, right):
        if a != b:
            break
        chars.append(a)
    return "".join(chars)


def category_summary(plan: CategoryPlan, cases: list[GeneratedCase], candidate_count: int) -> dict[str, str]:
    """Return one category summary row."""

    difficulties = Counter(case.difficulty for case in cases)
    dangers = Counter(case.danger for case in cases)
    return {
        "category_number": str(plan.number),
        "tier": plan.tier,
        "category": plan.category,
        "target_count": str(plan.target_count),
        "actual_count": str(len(cases)),
        "candidate_count_before_sampling": str(candidate_count),
        "scope": plan.scope,
        "easy": str(difficulties.get("EASY", 0)),
        "medium": str(difficulties.get("MEDIUM", 0)),
        "hard": str(difficulties.get("HARD", 0)),
        "extreme": str(difficulties.get("EXTREME", 0)),
        "safe": str(dangers.get("SAFE", 0)),
        "caution": str(dangers.get("CAUTION", 0)),
        "dangerous": str(dangers.get("DANGEROUS", 0)),
        "generator_function": plan.generator_function,
        "description": plan.description,
    }


def validate_final_dataset(cases: list[GeneratedCase]) -> None:
    """Validate row count, uniqueness, hard ratio, and category coverage."""

    if len(cases) != TOTAL_TARGET_CASES:
        raise RuntimeError(f"expected {TOTAL_TARGET_CASES} cases, generated {len(cases)}")

    keys = [(case.category, case.input_value, case.expected, case.error_type) for case in cases]
    duplicate_count = len(keys) - len(set(keys))
    if duplicate_count:
        raise RuntimeError(f"final dataset contains {duplicate_count} duplicate rows")

    categories = {case.category for case in cases}
    planned = {plan.category for plan in CATEGORY_PLANS}
    missing = sorted(planned - categories)
    extra = sorted(categories - planned)
    if missing or extra:
        raise RuntimeError(f"category coverage mismatch; missing={missing}; extra={extra}")

    difficulty_counts = Counter(case.difficulty for case in cases)
    hard_ratio = (difficulty_counts["HARD"] + difficulty_counts["EXTREME"]) / len(cases)
    if hard_ratio < MIN_HARD_OR_EXTREME_RATIO:
        raise RuntimeError(f"hard/extreme ratio {hard_ratio:.3f} below minimum {MIN_HARD_OR_EXTREME_RATIO:.3f}")

    blank_inputs = [case for case in cases if not str(case.input_value)]
    if blank_inputs:
        raise RuntimeError(f"found {len(blank_inputs)} rows with blank input")


def write_cases_csv(path: Path, cases: list[GeneratedCase]) -> None:
    """Write generated cases with stable field ordering."""

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for case in cases:
            writer.writerow(case.to_csv_row())


def write_category_summary(path: Path, summaries: list[dict[str, str]]) -> None:
    """Write category target-vs-actual summary."""

    fieldnames = [
        "category_number", "tier", "category", "target_count", "actual_count",
        "candidate_count_before_sampling", "scope", "easy", "medium", "hard",
        "extreme", "safe", "caution", "dangerous", "generator_function", "description",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summaries)


def write_generation_summary(path: Path, cases: list[GeneratedCase], category_summaries: list[dict[str, str]]) -> None:
    """Write JSON validation summary for reproducibility audits."""

    difficulty_counts = Counter(case.difficulty for case in cases)
    danger_counts = Counter(case.danger for case in cases)
    scope_counts = Counter(case.scope for case in cases)
    tier_counts = Counter(case.tier for case in cases)
    subcategory_counts = Counter(case.case_subcategory for case in cases)
    payload = {
        "declared_plan_total_cases": DECLARED_PLAN_TOTAL_CASES,
        "validated_total_cases_from_category_rows": TOTAL_TARGET_CASES,
        "plan_total_note": (
            "The attached plan headline says approximately 120,000 cases, but "
            "the explicit 34 category target counts sum to 115,000. This "
            "generator validates against the explicit category rows."
        ),
        "total_cases": len(cases),
        "hard_or_extreme_cases": difficulty_counts["HARD"] + difficulty_counts["EXTREME"],
        "hard_or_extreme_ratio": round((difficulty_counts["HARD"] + difficulty_counts["EXTREME"]) / len(cases), 6),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "danger_counts": dict(sorted(danger_counts.items())),
        "scope_counts": dict(sorted(scope_counts.items())),
        "tier_counts": dict(sorted(tier_counts.items())),
        "case_subcategory_counts": dict(sorted(subcategory_counts.items())),
        "unreadable_continuation_cases": sum(case.unreadable_continuation for case in cases),
        "category_count": len(category_summaries),
        "category_summaries": category_summaries,
        "source_catalog": str((ROOT / "data" / "canonical_candidates.csv").relative_to(ROOT)),
        "generator_script": str(Path(__file__).relative_to(ROOT)),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


GENERATORS: dict[str, Callable[[CategoryPlan, IndexedCatalog], list[GeneratedCase]]] = {
    "generate_single_letter_visual_confusion": generate_single_letter_visual_confusion,
    "generate_single_letter_phonetic_confusion": generate_single_letter_phonetic_confusion,
    "generate_multi_char_phonetic_confusion": generate_multi_char_phonetic_confusion,
    "generate_ligature_confusion": generate_ligature_confusion,
    "generate_single_char_deletion_position_weighted": generate_single_char_deletion_position_weighted,
    "generate_single_char_insertion": generate_single_char_insertion,
    "generate_transposition_position_weighted": generate_transposition_position_weighted,
    "generate_truncation_doctor_abbreviation": generate_truncation_doctor_abbreviation,
    "generate_two_error_combinations": generate_two_error_combinations,
    "generate_three_error_combinations": generate_three_error_combinations,
    "generate_speed_typing_errors": generate_speed_typing_errors,
    "generate_wrong_vowels_in_consonant_frame": generate_wrong_vowels_in_consonant_frame,
    "generate_punctuation_whitespace_copy_paste_artifacts": generate_punctuation_whitespace_copy_paste_artifacts,
    "generate_case_sensitivity": generate_case_sensitivity,
    "generate_number_word_confusion": generate_number_word_confusion,
    "generate_embedded_form_strength_parsing": generate_embedded_form_strength_parsing,
    "generate_dangerous_ed1_pairs": generate_dangerous_ed1_pairs,
    "generate_substring_traps": generate_substring_traps,
    "generate_negative_no_match_expected": generate_negative_no_match_expected,
    "generate_contradictory_form_route": generate_contradictory_form_route,
    "generate_cancelled_na_drug_lookup": generate_cancelled_na_drug_lookup,
    "generate_score_gap_ambiguity_detection": generate_score_gap_ambiguity_detection,
    "generate_ocr_letter_digit_confusion": generate_ocr_letter_digit_confusion,
    "generate_ocr_plus_other_error_combined": generate_ocr_plus_other_error_combined,
    "generate_double_letter_reduction_expansion": generate_double_letter_reduction_expansion,
    "generate_keyboard_adjacent_sampled": generate_keyboard_adjacent_sampled,
    "generate_four_plus_error_combinations": generate_four_plus_error_combinations,
    "generate_consonant_frame_wrong_vowels_heavy": generate_consonant_frame_wrong_vowels_heavy,
    "generate_multi_word_name_fragmentation": generate_multi_word_name_fragmentation,
    "generate_autocorrect_artifacts": generate_autocorrect_artifacts,
    "generate_exact_match_baseline": generate_exact_match_baseline,
    "generate_exact_match_with_strength": generate_exact_match_with_strength,
    "generate_keyboard_shift_whole_word": generate_keyboard_shift_whole_word,
    "generate_prefix_ambiguity_awareness": generate_prefix_ambiguity_awareness,
}


if __name__ == "__main__":
    main()

"""Configuration for reproducible commercial-name test generation.

Problem: generation needs many thresholds and category targets, and none should
be hidden as magic numbers inside transformation code.
Inputs: repository-relative source/output paths and fixed generation constants.
Outputs: named constants and CategorySpec objects consumed by the generator.
Edge cases: a category omitted from this file cannot be emitted, which prevents
unreviewed labels from leaking into the medical evaluation suite.
Failure modes: invalid counts or paths fail during import or validation instead
of creating partial CSV files.
Algorithm choice: static Python constants were chosen over a separate YAML file
because this repository already uses Python for evaluation and the values need
type checking through CategorySpec construction.
"""

from __future__ import annotations

from pathlib import Path

from .models import CategorySpec


ROOT = Path(__file__).resolve().parents[2]
CATALOG_CSV_PATH = ROOT / "data" / "canonical_candidates.csv"
DATA_DIR = ROOT / "benchmark_01_legacy" / "data"
SEED_CASES_PATH = DATA_DIR / "seed_test_cases.csv"
EXPANDED_CASES_PATH = DATA_DIR / "test_cases.csv"
INSIDE_CASES_PATH = DATA_DIR / "test_cases_inside.csv"
OUTSIDE_CASES_PATH = DATA_DIR / "test_cases_outside.csv"
SEMI_OUTSIDE_CASES_PATH = DATA_DIR / "test_cases_semi_outside.csv"
EXPANDED_SUMMARY_PATH = DATA_DIR / "generation_summary.json"
SCOPE_SUMMARY_PATH = DATA_DIR / "scope_summary.json"

# Fixed CSV schema. Keeping the order stable makes diffs meaningful and allows
# downstream reports to read the files without schema discovery.
CSV_FIELDNAMES = [
    "input",
    "expected",
    "error_type",
    "category",
    "difficulty",
    "danger",
    "collision_with",
    "notes",
]

# The suite is a stress-test distribution, not a production query-frequency
# distribution. More than 60% hard/extreme cases keeps the benchmark from being
# inflated by exact and easy matches while still leaving medium typo coverage.
MIN_HARD_OR_EXTREME_RATIO = 0.60

# Generated rows are deterministic. The ordering is catalog order plus category
# order, so no pseudo-random seed is required or allowed.
MAX_COLLISION_NAMES_IN_NOTE = 4
MIN_COMPACT_NAME_LENGTH = 3
MIN_PREFIX_LENGTH = 2
MAX_PREFIX_LENGTH = 4
MIN_SUFFIX_LENGTH = 4
MAX_SUFFIX_LENGTH = 8
MIN_SHARED_SUFFIX_FAMILY_SIZE = 8
MAX_MUTATIONS_PER_RECORD_PER_CATEGORY = 4

# Counts are intentionally close to the previous expanded suite so evaluation
# runtime remains comparable. Difficulty labels are changed where the category
# is known to be ambiguous, cross-token, phonetic, or safety-sensitive.
GENERATED_CATEGORY_SPECS: dict[str, CategorySpec] = {
    "all_position_deletion_full_catalog": CategorySpec(
        "all_position_deletion_full_catalog", 25_000, "inside", "HARD", "SAFE",
        "Deletion can remove the strongest distinguishing letter in a brand.",
    ),
    "keyboard_adjacent_expanded_catalog": CategorySpec(
        "keyboard_adjacent_expanded_catalog", 22_000, "inside", "HARD", "SAFE",
        "Single-key slips often remain plausible medicine strings.",
    ),
    "vowel_substitution_full_catalog": CategorySpec(
        "vowel_substitution_full_catalog", 22_000, "inside", "MEDIUM", "SAFE",
        "Vowel substitutions are common heard-spelling errors but usually recoverable.",
    ),
    "all_position_transposition_full_catalog": CategorySpec(
        "all_position_transposition_full_catalog", 20_000, "inside", "HARD", "SAFE",
        "Adjacent swaps can defeat prefix-heavy ranking.",
    ),
    "phonetic_substitution_full_catalog": CategorySpec(
        "phonetic_substitution_full_catalog", 18_000, "inside", "HARD", "SAFE",
        "Sound-equivalent substitutions are hard without phonetic matching.",
    ),
    "strength_unit_noise_catalog": CategorySpec(
        "strength_unit_noise_catalog", 18_000, "semi_outside", "HARD", "CAUTION",
        "Wrong or rewritten units can change clinical interpretation.",
    ),
    "initial_sound_confusion_full_catalog": CategorySpec(
        "initial_sound_confusion_full_catalog", 16_000, "inside", "HARD", "SAFE",
        "Initial-letter errors are difficult because engines overweight prefixes.",
    ),
    "single_vowel_deletion_full_catalog": CategorySpec(
        "single_vowel_deletion_full_catalog", 14_000, "inside", "MEDIUM", "SAFE",
        "Single missing vowels are frequent and should be recoverable.",
    ),
    "consonant_skeleton_expanded_catalog": CategorySpec(
        "consonant_skeleton_expanded_catalog", 12_000, "inside", "HARD", "SAFE",
        "Vowel-stripped names require non-exact candidate generation.",
    ),
    "form_word_noise_catalog": CategorySpec(
        "form_word_noise_catalog", 12_000, "outside", "HARD", "CAUTION",
        "Dosage-form words are context and should not override name evidence.",
    ),
    "mobile_keypad_confusion_catalog": CategorySpec(
        "mobile_keypad_confusion_catalog", 10_000, "inside", "HARD", "SAFE",
        "Same-key mobile substitutions can create plausible alternatives.",
    ),
    "partial_prefix_ambiguity_catalog": CategorySpec(
        "partial_prefix_ambiguity_catalog", 10_000, "inside", "EXTREME", "CAUTION",
        "Short prefixes are inherently ambiguous and should trigger clarification.",
    ),
    "truncation_collision_expanded_catalog": CategorySpec(
        "truncation_collision_expanded_catalog", 9_500, "inside", "EXTREME", "DANGEROUS",
        "A real short family can be a prefix of a different longer family.",
    ),
    "separator_removal_full_catalog": CategorySpec(
        "separator_removal_full_catalog", 9_000, "inside", "MEDIUM", "SAFE",
        "Separator removal tests compact matching.",
    ),
    "token_order_transposition_catalog": CategorySpec(
        "token_order_transposition_catalog", 9_000, "inside", "HARD", "SAFE",
        "Users can remember words but reverse catalog order.",
    ),
    "ingredient_name_query_catalog": CategorySpec(
        "ingredient_name_query_catalog", 9_000, "outside", "HARD", "CAUTION",
        "Ingredient-only queries are outside commercial-name-only matching.",
    ),
    "ocr_digit_letter_full_catalog": CategorySpec(
        "ocr_digit_letter_full_catalog", 8_000, "inside", "HARD", "SAFE",
        "OCR substitutions are visual, not lexical, and require special handling.",
    ),
    "manufacturer_noise_catalog": CategorySpec(
        "manufacturer_noise_catalog", 8_000, "outside", "HARD", "SAFE",
        "Manufacturer terms are context and should not be treated as brand tokens.",
    ),
    "space_insertion_inside_brand_catalog": CategorySpec(
        "space_insertion_inside_brand_catalog", 8_000, "inside", "MEDIUM", "SAFE",
        "Inserted spaces test tokenization and compact keys.",
    ),
    "decimal_slash_strength_noise_catalog": CategorySpec(
        "decimal_slash_strength_noise_catalog", 7_500, "semi_outside", "EXTREME", "CAUTION",
        "Decimal/slash mistakes can alter dose interpretation.",
    ),
    "visual_ligature_full_catalog": CategorySpec(
        "visual_ligature_full_catalog", 7_000, "inside", "HARD", "SAFE",
        "Ligature-like confusions model OCR and low-resolution screenshots.",
    ),
    "therapeutic_class_noise_catalog": CategorySpec(
        "therapeutic_class_noise_catalog", 7_000, "outside", "HARD", "SAFE",
        "Therapeutic classes are context, not commercial names.",
    ),
    "route_word_noise_catalog": CategorySpec(
        "route_word_noise_catalog", 7_000, "outside", "HARD", "CAUTION",
        "Route words can change product interpretation.",
    ),
    "status_marker_noise_catalog": CategorySpec(
        "status_marker_noise_catalog", 7_000, "outside", "HARD", "CAUTION",
        "Status words must become warnings, not ranking tokens.",
    ),
    "prefix_suffix_extra_noise_catalog": CategorySpec(
        "prefix_suffix_extra_noise_catalog", 7_000, "semi_outside", "MEDIUM", "SAFE",
        "Generic words around a brand should be ignored as weak noise.",
    ),
    "keyboard_shift_whole_word_catalog": CategorySpec(
        "keyboard_shift_whole_word_catalog", 7_000, "inside", "HARD", "SAFE",
        "Whole-word keyboard shifts are far from edit-distance-one.",
    ),
    "symbol_synonym_catalog": CategorySpec(
        "symbol_synonym_catalog", 7_000, "semi_outside", "HARD", "CAUTION",
        "Symbols such as percent, plus, ampersand, and slash carry meaning.",
    ),
    "qualifier_synonym_noise_catalog": CategorySpec(
        "qualifier_synonym_noise_catalog", 6_000, "semi_outside", "HARD", "CAUTION",
        "PLUS/XR/SR/EXTRA variants are clinically relevant qualifiers.",
    ),
    "brand_ingredient_mixed_query_catalog": CategorySpec(
        "brand_ingredient_mixed_query_catalog", 6_000, "outside", "HARD", "CAUTION",
        "Mixed brand and ingredient queries need evidence-aware ranking.",
    ),
    "suffix_family_confusion_expanded_catalog": CategorySpec(
        "suffix_family_confusion_expanded_catalog", 5_500, "inside", "EXTREME", "CAUTION",
        "Shared drug-family suffixes create many plausible wrong targets.",
    ),
    "parenthetical_noise_catalog": CategorySpec(
        "parenthetical_noise_catalog", 5_000, "semi_outside", "HARD", "CAUTION",
        "Parenthetical package/company text is common and noisy.",
    ),
    "duplicate_syllable_catalog": CategorySpec(
        "duplicate_syllable_catalog", 5_000, "inside", "HARD", "SAFE",
        "Duplicated syllables are edit-distance-large but user-realistic.",
    ),
    "digraph_soundalike_catalog": CategorySpec(
        "digraph_soundalike_catalog", 3_000, "inside", "HARD", "SAFE",
        "CH/SH/TH/PH/QU/X style confusions need rule-based expansion.",
    ),
    "abbreviation_expansion_catalog": CategorySpec(
        "abbreviation_expansion_catalog", 1_000, "semi_outside", "HARD", "CAUTION",
        "Expanded medical abbreviations must not break commercial-name matching.",
    ),
    "token_drop_expanded_catalog": CategorySpec(
        "token_drop_expanded_catalog", 900, "inside", "HARD", "CAUTION",
        "Dropping qualifiers can collapse distinct product families.",
    ),
}

SEED_CATEGORY_SCOPES: dict[str, str] = {
    "keyboard_adjacent": "inside",
    "truncation_collision": "inside",
    "ph_f_confusion": "inside",
    "ligature_confusion": "inside",
    "syllable_transposition": "inside",
    "position_deletion": "inside",
    "voiced_unvoiced_swap": "inside",
    "consonant_skeleton": "inside",
    "mirror_letter_confusion": "inside",
    "c_k_q_interchange": "inside",
    "ocr_digit_letter": "inside",
    "suffix_family_confusion": "inside",
    "letter_insertion": "inside",
    "multi_error_chain": "inside",
    "cross_script": "inside",
    "arabic_dot_confusion": "inside",
    "double_letter": "inside",
}

VOWELS = "AEIOUY"
QWERTY_ROWS = ("QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM")
T9_GROUPS = ("ABC", "DEF", "GHI", "JKL", "MNO", "PQRS", "TUV", "WXYZ")
SOUND_GROUPS = ("BP", "FV", "DT", "GKQC", "SZ")
SUFFIX_FAMILIES = ("AZOLE", "PRIL", "STATIN", "OLOL", "SARTAN", "CILLIN", "MYCIN", "DIPINE", "FLOXACIN")

FORM_WORD_BY_ROUTE = {
    "oral_solid": ("tablet", "capsule", "tab"),
    "oral_liquid": ("syrup", "suspension", "drops"),
    "injection": ("injection", "vial", "ampoule"),
    "topical": ("cream", "gel", "ointment"),
    "ophthalmic": ("eye drops", "ophthalmic"),
    "otic": ("ear drops", "otic"),
    "rectal": ("suppository", "rectal"),
    "vaginal": ("vaginal", "pessary"),
    "spray": ("spray", "nasal spray"),
}

ROUTE_NOISE_WORDS = {
    "oral_solid": "oral tablet",
    "oral_liquid": "oral syrup",
    "injection": "iv im",
    "topical": "topical skin",
    "ophthalmic": "eye",
    "otic": "ear",
    "rectal": "rectal",
    "vaginal": "vaginal",
    "spray": "spray",
    "mouth": "mouth oral",
}

STATUS_MARKERS = ("n/a", "cancelled", "illegal import", "hospital only", "net price")
GENERIC_PREFIX_SUFFIX_WORDS = ("drug", "medicine", "price", "dose", "uses", "generic")
QUALIFIER_SYNONYMS = (("PLUS", "+"), ("EXTRA", "XTRA"), ("XR", "EXTENDED RELEASE"), ("SR", "SUSTAINED RELEASE"))
ABBREVIATION_EXPANSIONS = {
    "F C": "film coated",
    "I V": "intravenous",
    "I M": "intramuscular",
    "S R": "sustained release",
    "X R": "extended release",
    "TAB": "tablet",
    "TABS": "tablets",
    "CAPS": "capsules",
    "AMP": "ampoule",
    "INJ": "injection",
    "INF": "infusion",
    "SUSP": "suspension",
}

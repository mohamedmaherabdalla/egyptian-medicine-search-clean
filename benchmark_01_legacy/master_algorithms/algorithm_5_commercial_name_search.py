#!/usr/bin/env python3
"""Algorithm 5: evidence-guided medicine-family retrieval and ranking.

Algorithm 3 improved safety by running both Algorithm 1 and Algorithm 2, then
fusing their ranked lists. That works, but it pays the cost of both child
searches for every query. Algorithm 5 keeps Algorithm 2 as the only full search
pass and adds a small family-level rescue index for general typo patterns found
during failure analysis:

- one to three internal substitutions;
- dropped or inserted middle letters;
- phonetic/keyboard substitutions such as c/k/q, s/z, f/v, p/b, d/t;
- cases where the correct family is present but ranked below a stronger-looking
  false positive.

The rescue index is built over unique commercial families, not every package
row. Query time normally touches only buckets from exact/prefix/suffix/rare
ngrams/delete/phonetic keys. A length-bucket scan is used only for short,
brand-like queries where Algorithm 2 is weak or uncertain.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
EVALUATION_DIR = ROOT / "benchmark_01_legacy"
if str(EVALUATION_DIR) not in sys.path:
    sys.path.insert(0, str(EVALUATION_DIR))

import evaluate_current_app_search as current_eval


EXTERNAL_ALGORITHM_PATH = EVALUATION_DIR / "external_algorithms" / "english_search_algorithm_fast.py"
TOP_K_DEFAULT = 20
INTERNAL_EXTERNAL_LIMIT = TOP_K_DEFAULT

CONFIDENT_EXTERNAL_STATUSES = {"high_confidence", "medium_confidence"}
RESCUE_PREFILTER_LIMIT = 45
EDGE_RESCUE_PREFILTER_LIMIT = 15
EDGE_RESCUE_SHORTLIST_LIMIT = 45
RESCUE_UNCERTAIN_SCORE_THRESHOLD = 0.82
RESCUE_UNCERTAIN_GAP_THRESHOLD = 0.045
STRICT_FULL_NAME_MAX_DISTANCE = 3
STRICT_FULL_NAME_SCORE_GAP = 0.35
STRICT_FULL_NAME_MIN_WEIGHTED_GAIN = 0.35
STRICT_FULL_NAME_MIN_EDGE_GAIN = 0.05
CONTEXT_NOISE_TOKENS = {
    "MG", "MCG", "G", "GM", "GRAM", "GRAMS", "ML", "L", "IU", "UNIT", "UNITS",
    "PERCENT", "PER", "TAB", "TABS", "TABLET", "TABLETS", "CAP", "CAPS",
    "CAPSULE", "CAPSULES", "SYRUP", "SUSP", "SUSPENSION", "VIAL", "VIALS",
    "AMP", "AMPS", "AMPOULE", "AMPOULES", "CREAM", "GEL", "OINT", "OINTMENT",
    "DROPS", "DROP", "ORAL", "TOPICAL", "INJ", "INJECTION",
    "FC", "FCT", "SC", "SR", "XR", "MR", "RETARD", "SACHET", "SACHETS",
}
UNIT_SUFFIX_RE = re.compile(r"^\d+(?:\.\d+)?(?:MG|MCG|G|GM|ML|L|IU|%)$")
PURE_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?$")
UNREADABLE_MODES = {"none", "before", "middle", "after"}

VOWELS = set("AEIOUY")
CONFUSION_GROUPS = [
    set("CKQ"),
    set("SZ"),
    set("FV"),
    set("PB"),
    set("DT"),
    set("GJ"),
    set("MN"),
    set("IEY"),
    set("OU"),
]
CONFUSION_PAIRS = {
    (left, right)
    for group in CONFUSION_GROUPS
    for left in group
    for right in group
    if left != right
}
OCR_DIGIT_TO_LETTERS = {
    "0": {"O"},
    "1": {"I", "L"},
    "2": {"Z"},
    "3": {"E"},
    "4": {"A"},
    "5": {"S"},
    "6": {"G"},
    "8": {"B"},
}
OCR_VISUAL_TIE_MAX_SCORE_GAP = 0.25
OCR_VISUAL_TIE_CANDIDATE_LIMIT = 5
VALIDATED_HEAD_MAX_DISTANCE = 2
SHORT_VISIBLE_HEAD_LIMIT = 4
TWO_SIDED_ANCHOR_MAX_DISTANCE = 2
TWO_SIDED_ANCHOR_MAX_SCORE_GAP = 0.40
EVIDENCE_VARIANT_LIMIT = 12
NEAREST_FALLBACK_LIMIT = 12
SHORT_FRAME_RETRIEVAL_LIMIT = 8
SHORT_FRAME_MAX_RAW_DISTANCE = 3
SHORT_FRAME_MAX_WEIGHTED_DISTANCE = 2.25
MIXED_VARIANT_LIMIT = 48
MIXED_VARIANT_SCORE_DISCOUNT = 0.32
TRANSPOSE_DELETE_SCORE_DISCOUNT = 0.28
KEYBOARD_DELETE_SCORE_DISCOUNT = 0.45
VISUAL_PHONETIC_CHAIN_SCORE_DISCOUNT = 3.35
VISUAL_VISUAL_DELETE_SCORE_DISCOUNT = 3.75
TRANSPOSITION_DELETE_EXACT_SCORE_DISCOUNT = 3.40
LIGATURE_VOWEL_CHAIN_SCORE_DISCOUNT = 3.25
LIGATURE_VOWEL_TRANSPOSE_SCORE_DISCOUNT = 3.35
TRANSPOSE_VOWEL_DELETE_SCORE_DISCOUNT = 3.75
VOWEL_PHONETIC_DELETE_SCORE_DISCOUNT = 3.75
KEYBOARD_VOWEL_DELETE_EXACT_SCORE_DISCOUNT = 3.40
SHORT_OCR_COMBINED_SCORE_DISCOUNT = 3.40
SHORT_TWO_DELETION_VOWEL_DISCOUNT = 0.12
EVIDENCE_PROMOTION_MAX_SCORE_GAP = 0.40
STRUCTURAL_PROMOTION_MAX_SCORE_GAP = 1.40
STRUCTURAL_VARIANT_SCORE_DISCOUNT = 0.18
NEAREST_PROMOTION_MIN_DISTANCE_GAIN = 2
DIRECTIONAL_VISUAL_LIGATURE_PAIRS = (
    ("IV", "N"),
)
LIGATURE_CONFUSION_PAIRS = (
    ("RN", "M"),
    ("M", "RN"),
    ("CL", "D"),
    ("D", "CL"),
    ("LI", "H"),
    ("H", "LI"),
    ("RI", "N"),
    ("AL", "D"),
    ("NN", "M"),
    ("VV", "W"),
    ("W", "UU"),
    *DIRECTIONAL_VISUAL_LIGATURE_PAIRS,
    ("IA", "A"),
    ("II", "U"),
)
VISUAL_CHAIN_GROUPS = (
    "AOUE",
    "ILT",
    "HNBR",
    "MN",
    "GQY",
    "UVW",
    "FTL",
    "ECO",
)
PHONETIC_CHAIN_GROUPS = ("BP", "DT", "GK", "SZ", "FV", "CKQ")
PHONETIC_REWRITE_PAIRS = (
    ("PH", "F"), ("F", "PH"), ("CK", "K"), ("K", "CK"),
    ("X", "KS"), ("KS", "X"), ("CKS", "X"), ("QU", "KW"),
    ("KW", "QU"), ("QU", "CW"), ("GH", "G"), ("TH", "T"),
    ("TH", "S"), ("GHT", "T"), ("WH", "W"), ("SH", "CH"),
    ("CH", "SH"), ("TION", "SHUN"), ("Y", "I"), ("I", "Y"),
    ("Y", "EE"),
)
GENERATOR_LIGATURE_PAIRS = LIGATURE_CONFUSION_PAIRS[:6]
EXACT_CHAIN_EVIDENCE_REASONS = {
    "visual_phonetic_substitution_chain_retrieval",
    "visual_visual_deletion_chain_retrieval",
    "transposition_deletion_exact_retrieval",
    "ligature_vowel_chain_retrieval",
    "ligature_vowel_transposition_chain_retrieval",
    "transposition_vowel_deletion_chain_retrieval",
    "vowel_phonetic_deletion_chain_retrieval",
    "keyboard_vowel_deletion_exact_retrieval",
    "short_ocr_combined_retrieval",
    "short_two_deletion_frame_retrieval",
}
ENABLE_EXACT_CHAIN_EXISTING_AUGMENTATION = True
ENABLE_VISUAL_VISUAL_DELETION_CHAIN = True
ENABLE_VISUAL_PHONETIC_IN_PLACE_SCORE = True
ENABLE_VISUAL_PHONETIC_SCORE_TUNING = True
ENABLE_LIGATURE_VOWEL_IN_PLACE_SCORE = True
ENABLE_LIGATURE_VOWEL_TRANSPOSE_IN_PLACE_SCORE = True
ENABLE_TRANSPOSE_VOWEL_DELETE_IN_PLACE_SCORE = True
ENABLE_TRANSPOSE_VOWEL_DELETE_SCORE_TUNING = True
ENABLE_KEYBOARD_VOWEL_DELETE_IN_PLACE_SCORE = True
ENABLE_KEYBOARD_VOWEL_DELETE_SCORE_TUNING = True
ENABLE_TRANSPOSITION_DELETION_EXACT_CHAIN = True
ENABLE_SHORT_QUERY_RESCUE = True
ENABLE_UNIQUE_NEAREST_RERANK = True
ENABLE_CONTAINED_NEAREST_RERANK = True
ENABLE_PRESERVED_TOP_DOMINANT_NEAREST_RERANK = True
ENABLE_PRESERVED_TOP_HIGHER_SCORE_NEAREST_RERANK = True
ENABLE_EXACT_LIGATURE_NEAREST_RERANK = True
ENABLE_EXACT_LIGATURE_RANK_EXTENSION_RERANK = True
ENABLE_EXACT_PHONETIC_REWRITE_RERANK = True
ENABLE_WEIGHTED_EDGE_TIE_RERANK = True
ENABLE_WEIGHTED_EDGE_ADVANTAGE_RERANK = True
ENABLE_WEIGHTED_EXACT_KEY_TIE_RERANK = True
ENABLE_EXACT_TRANSPOSITION_TIE_RERANK = True
ENABLE_EXACT_TRANSPOSITION_DUAL_EXTENSION_RERANK = True
ENABLE_EXACT_KEYBOARD_KEY_TIE_RERANK = True
ENABLE_EXACT_KEYBOARD_WEIGHTED_EXTENSION_RERANK = True
ENABLE_EXACT_VISUAL_EDGE_TIE_RERANK = True
ENABLE_GUARDED_TOP_SCORE_DOMINANT_CHAIN_RERANK = True
ENABLE_SCORE_DOMINANT_CHAIN_RELEASE_RERANK = True
ENABLE_STUTTER_PREFIX_RERANK = True
ENABLE_STRICT_FULL_NAME_RERANK = True
ENABLE_STRICT_FULL_NAME_EVIDENCE_GUARD = True
ENABLE_EXACT_KEY_PARETO_TIE_RERANK = True
ENABLE_PHONETIC_POSITION_TIE_RERANK = True
ENABLE_SHIFTED_EDGE_AGREEMENT_RERANK = True
ENABLE_VISUAL_DISTANCE_TIE_RERANK = True
ENABLE_SKELETON_POSITION_TIE_RERANK = True
ENABLE_LIGATURE_VOWEL_TRANSPOSE_RERANK = True
ENABLE_LIGATURE_VOWEL_TRANSPOSE_EXTENSION_RERANK = True
ENABLE_LIGATURE_VOWEL_RERANK = True
ENABLE_LIGATURE_VOWEL_DISTANCE_EXTENSION_RERANK = True
ENABLE_LIGATURE_VOWEL_EDGE_EXTENSION_RERANK = True
ENABLE_LIGATURE_VOWEL_MULTI_CHAIN_EXTENSION_RERANK = True
ENABLE_VISUAL_PHONETIC_CHAIN_RERANK = True
ENABLE_VISUAL_PHONETIC_EXACT_KEY_EXTENSION_RERANK = True
ENABLE_VISUAL_PHONETIC_DUAL_EXTENSION_RERANK = True
ENABLE_KEYBOARD_VOWEL_DELETE_RERANK = True
ENABLE_KEYBOARD_EXACT_KEY_RERANK = True
ENABLE_VISUAL_VISUAL_DELETE_RERANK = True
ENABLE_VISUAL_MULTI_CHAIN_RERANK = True
ENABLE_TRANSPOSITION_DELETE_RERANK = True
ENABLE_TRANSPOSE_VOWEL_DELETE_RERANK = True
ENABLE_VOWEL_PHONETIC_DELETE_RERANK = True
ENABLE_VOWEL_PHONETIC_MULTI_CHAIN_EXTENSION_RERANK = True


@dataclass
class FamilyRecord:
    """One deduplicated commercial family used by the rescue layer."""

    id: int
    name: str
    norm: str
    compact: str
    skeleton: str
    phonetic: str
    reversed_compact: str
    grams2: set[str]
    grams3: set[str]
    grams4: set[str]
    delete_keys: set[str]
    ingredients: set[str] = field(default_factory=set)
    manufacturers: set[str] = field(default_factory=set)
    variant_group: str = ""
    head_compact: str = ""
    head_skeleton: str = ""
    head_phonetic: str = ""
    examples: list[str] = field(default_factory=list)
    warnings: set[str] = field(default_factory=set)


@dataclass
class RescueIndex:
    """Small family-level indexes for cheap recovery and safety checks."""

    families: list[FamilyRecord]
    exact: dict[str, set[int]]
    prefix: dict[str, set[int]]
    suffix: dict[str, set[int]]
    grams2: dict[str, set[int]]
    grams3: dict[str, set[int]]
    grams4: dict[str, set[int]]
    skeleton: dict[str, set[int]]
    skeleton_prefix: dict[str, set[int]]
    phonetic: dict[str, set[int]]
    phonetic_prefix: dict[str, set[int]]
    head_exact: dict[str, set[int]]
    head_prefix: dict[str, set[int]]
    head_delete: dict[str, set[int]]
    head_phonetic: dict[str, set[int]]
    delete_index: dict[str, set[int]]
    length: dict[int, set[int]]
    first_char: dict[str, set[int]]
    prefix_risk: dict[str, int]
    family_by_key: dict[str, int]
    variant_groups: dict[str, list[int]]

@dataclass
class Algorithm5Catalog:
    """Prepared Algorithm 5 state."""

    external_module: ModuleType
    external_catalog: Any
    rescue_index: RescueIndex


@dataclass
class Candidate:
    """Merged external/rescue candidate."""

    key: str
    name: str
    commercial_name: str
    examples: list[str] = field(default_factory=list)
    external_rank: int | None = None
    external_score: float = 0.0
    context_rank: int | None = None
    context_score: float = 0.0
    rescue_rank: int | None = None
    rescue_score: float = 0.0
    score: float = 0.0
    raw_edit_distance: float = 999.0
    weighted_edit_distance: float = 999.0
    ocr_visual_edit_distance: float = 999.0
    ocr_visual_gain: float = 0.0
    positional_evidence: float = 0.0
    edge_evidence: float = 0.0
    head_raw_edit_distance: float = 999.0
    is_variant_family: bool = False
    variant_group: str = ""
    ingredients: list[str] = field(default_factory=list)
    variants: list[str] = field(default_factory=list)
    needs_clarification: bool = True
    evidence_only_retrieval: bool = False
    evidence_supported_existing: bool = False
    structural_only_retrieval: bool = False
    multi_step_only_retrieval: bool = False
    multi_step_augmented_existing: bool = False
    pre_multi_step_score: float = 0.0
    reasons: set[str] = field(default_factory=set)


def prepare_catalog() -> Algorithm5Catalog:
    """Prepare external search and the lightweight family rescue index."""

    records = current_eval.prepare_records()
    if not records:
        raise ValueError("app catalog produced zero records")
    external_module = load_external_module(EXTERNAL_ALGORITHM_PATH)
    external_catalog = external_module.prepare_catalog(build_external_rows(records))
    rescue_index = build_rescue_index(records)
    return Algorithm5Catalog(
        external_module=external_module,
        external_catalog=external_catalog,
        rescue_index=rescue_index,
    )


def load_external_module(path: Path) -> ModuleType:
    """Load Algorithm 2 from an explicit path."""

    if not path.exists():
        raise FileNotFoundError(f"external algorithm not found: {path}")
    spec = importlib.util.spec_from_file_location("algorithm5_external_english_fast", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import external algorithm from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_external_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Adapt app catalog rows into Algorithm 2's expected schema."""

    rows = []
    for record in records:
        commercial_name = str(record.get("n") or "").strip()
        if not commercial_name:
            continue
        base_group = str(record.get("b") or commercial_name).strip()
        rows.append({"commercial_name": commercial_name, "canonical_name": base_group})
    if not rows:
        raise ValueError("external adapter produced zero rows")
    return rows


def build_rescue_index(records: list[dict[str, Any]]) -> RescueIndex:
    """Build family-level indexes from app records."""

    by_family: dict[str, dict[str, Any]] = {}
    for record in records:
        name = str(record.get("b") or record.get("n") or "").strip()
        if not name:
            continue
        key = current_eval.compact_key(name)
        if not key:
            continue
        item = by_family.setdefault(key, {
            "name": name,
            "examples": [],
            "warnings": set(),
            "ingredients": set(),
            "manufacturers": set(),
        })
        example = str(record.get("n") or name).strip()
        if example and example not in item["examples"] and len(item["examples"]) < 8:
            item["examples"].append(example)
        item["warnings"].update(str(value) for value in record.get("_warnings", []) or [])
        raw_warning = str(record.get("w") or "").strip()
        if raw_warning:
            item["warnings"].update(value for value in raw_warning.split("|") if value)
        ingredient = str(record.get("ing") or record.get("s") or "").strip()
        manufacturer = str(record.get("m") or "").strip()
        if ingredient:
            item["ingredients"].add(ingredient)
        if manufacturer:
            item["manufacturers"].add(manufacturer)

    families = []
    for idx, item in enumerate(sorted(by_family.values(), key=lambda row: current_eval.compact_key(row["name"]))):
        name = item["name"]
        compact = current_eval.compact_key(name)
        families.append(FamilyRecord(
            id=idx,
            name=name,
            norm=current_eval.normalize_search(name),
            compact=compact,
            skeleton=current_eval.skeleton(name),
            phonetic=current_eval.drug_phonetic_key(name),
            reversed_compact=compact[::-1],
            grams2=char_ngrams(compact, 2),
            grams3=char_ngrams(compact, 3),
            grams4=char_ngrams(compact, 4),
            delete_keys=delete_keys(compact, max_deletes_for(compact)),
            ingredients=set(item["ingredients"]),
            manufacturers=set(item["manufacturers"]),
            examples=item["examples"] or [name],
            warnings=set(item["warnings"]),
        ))

    assign_variant_groups(families)
    for family in families:
        if family.variant_group and family.variant_group != family.norm:
            family.head_compact = current_eval.compact_key(family.variant_group)
            family.head_skeleton = current_eval.skeleton(family.variant_group)
            family.head_phonetic = current_eval.drug_phonetic_key(family.variant_group)
    family_by_key = {family.compact: family.id for family in families}
    variant_groups: dict[str, list[int]] = defaultdict(list)
    for family in families:
        variant_groups[family.variant_group or family.norm].append(family.id)

    index = RescueIndex(
        families=families,
        exact=defaultdict(set),
        prefix=defaultdict(set),
        suffix=defaultdict(set),
        grams2=defaultdict(set),
        grams3=defaultdict(set),
        grams4=defaultdict(set),
        skeleton=defaultdict(set),
        skeleton_prefix=defaultdict(set),
        phonetic=defaultdict(set),
        phonetic_prefix=defaultdict(set),
        head_exact=defaultdict(set),
        head_prefix=defaultdict(set),
        head_delete=defaultdict(set),
        head_phonetic=defaultdict(set),
        delete_index=defaultdict(set),
        length=defaultdict(set),
        first_char=defaultdict(set),
        prefix_risk=defaultdict(int),
        family_by_key=family_by_key,
        variant_groups=dict(variant_groups),
    )

    prefix_sets: dict[str, set[str]] = defaultdict(set)
    for family in families:
        add(index.exact, family.compact, family.id)
        add_prefixes(index.prefix, family.compact, family.id, 2, 12)
        add_suffixes(index.suffix, family.reversed_compact, family.id, 2, 12)
        for gram in family.grams2:
            add(index.grams2, gram, family.id)
        for gram in family.grams3:
            add(index.grams3, gram, family.id)
        for gram in family.grams4:
            add(index.grams4, gram, family.id)
        add(index.skeleton, family.skeleton, family.id)
        add_prefixes(index.skeleton_prefix, family.skeleton, family.id, 3, 10)
        add(index.phonetic, family.phonetic, family.id)
        add_prefixes(index.phonetic_prefix, family.phonetic, family.id, 3, 10)
        if family.head_compact:
            add(index.head_exact, family.head_compact, family.id)
            add_prefixes(index.head_prefix, family.head_compact, family.id, 3, 10)
            add(index.head_phonetic, family.head_phonetic, family.id)
            for key in delete_keys(family.head_compact, 2):
                add(index.head_delete, key, family.id)
        for key in family.delete_keys:
            add(index.delete_index, key, family.id)
        index.length[len(family.compact)].add(family.id)
        if family.compact:
            index.first_char[family.compact[0]].add(family.id)
        for length in range(1, min(6, len(family.compact)) + 1):
            prefix_sets[family.compact[:length]].add(family.compact)

    for prefix, values in prefix_sets.items():
        index.prefix_risk[prefix] = len(values)

    return index


def assign_variant_groups(families: list[FamilyRecord]) -> None:
    """Group explicit brand variants without collapsing unrelated prefixes.

    A shared first token is only treated as a variant family when it has at
    least four characters and the catalog records also share a manufacturer.
    Ingredients are deliberately not required to match because qualifiers such
    as EXTRA or PLUS often identify clinically different compositions that the
    user must choose explicitly.
    """

    by_first_token: dict[str, list[FamilyRecord]] = defaultdict(list)
    for family in families:
        tokens = family.norm.split()
        first = tokens[0] if tokens else ""
        if len(first) >= 4:
            by_first_token[first].append(family)

    for family in families:
        family.variant_group = family.norm
    for first, cohort in by_first_token.items():
        if len(cohort) < 2:
            continue
        for family in cohort:
            if any(
                other.id != family.id
                and family.manufacturers
                and bool(family.manufacturers & other.manufacturers)
                for other in cohort
            ):
                family.variant_group = first


def parse_query_request(raw_query: Any) -> tuple[str, str, str, bool]:
    """Return visible query fragments and their unreadable-position mode."""

    if isinstance(raw_query, dict):
        text = str(raw_query.get("text") or raw_query.get("query") or "")
        legacy_continuation = bool(raw_query.get("unreadable_continuation"))
        requested_mode = str(raw_query.get("unreadable_mode") or "").lower()
        unreadable_mode = (
            requested_mode
            if requested_mode in UNREADABLE_MODES
            else ("after" if legacy_continuation else "none")
        )
        ending_fragment = str(raw_query.get("ending_fragment") or "")
        return text, unreadable_mode, ending_fragment, legacy_continuation
    return ("" if raw_query is None else str(raw_query)), "none", "", False


def unreadable_pattern_matches(
    target: str,
    visible_text: str,
    ending_text: str,
    mode: str,
) -> bool:
    """Return whether a family key satisfies the user's visible-fragment evidence."""

    if mode == "after":
        return target.startswith(visible_text) and len(target) > len(visible_text)
    if mode == "before":
        return target.endswith(visible_text) and len(target) > len(visible_text)
    if mode == "middle":
        return bool(
            visible_text
            and ending_text
            and target.startswith(visible_text)
            and target.endswith(ending_text)
            and len(target) > len(visible_text) + len(ending_text)
        )
    return True


def search_catalog(catalog: Algorithm5Catalog, raw_query: Any, limit: int = TOP_K_DEFAULT) -> dict[str, Any]:
    """Run Algorithm 5 and return an Algorithm-2-shaped response."""

    query_text, unreadable_mode, ending_fragment, legacy_continuation = parse_query_request(raw_query)
    unreadable_continuation = unreadable_mode == "after"
    compact = current_eval.compact_key(query_text)
    ending_compact = current_eval.compact_key(ending_fragment)
    if not compact:
        return {
            "query": raw_query,
            "normalized_query": "",
            "status": "no_match",
            "message": "Empty query.",
            "decision_type": "no_match",
            "unreadable_continuation": unreadable_continuation,
            "unreadable_mode": unreadable_mode,
            "ending_fragment": ending_fragment,
            "candidate_count": 0,
            "results": [],
        }

    external_response = catalog.external_module.search_catalog(
        catalog.external_catalog,
        query_text,
        max(limit, INTERNAL_EXTERNAL_LIMIT),
    )
    external_results = list(external_response.get("results") or [])
    external_status = str(external_response.get("status") or "")
    context_results = []
    cleaned_context_query = clean_context_query(query_text)
    if should_run_context_search(compact, cleaned_context_query):
        context_response = catalog.external_module.search_catalog(
            catalog.external_catalog,
            cleaned_context_query,
            max(limit, INTERNAL_EXTERNAL_LIMIT),
        )
        context_results = list(context_response.get("results") or [])

    standard_rescue_needed = should_run_rescue(
        compact,
        external_results,
        external_status,
        include_short_query=False,
    )
    short_query_rescue_only = bool(
        ENABLE_SHORT_QUERY_RESCUE
        and 3 <= len(compact) <= 4
        and not standard_rescue_needed
    )
    rescue_results = (
        rescue_search(
            catalog.rescue_index,
            query_text,
            external_results,
            external_status,
            max(limit, INTERNAL_EXTERNAL_LIMIT),
        )
        if unreadable_mode != "none"
        or standard_rescue_needed
        or short_query_rescue_only
        else []
    )
    baseline_rescue_results = pre_multi_step_rescue_view(rescue_results)
    baseline_ranked: list[Candidate] = []
    if baseline_rescue_results and unreadable_mode == "none":
        baseline_candidates = merge_candidates(
            external_results,
            context_results,
            baseline_rescue_results,
            external_status,
        )
        enrich_candidates(catalog.rescue_index, baseline_candidates, compact)
        baseline_ranked = rank_candidates(
            list(baseline_candidates.values()),
            compact,
            brand_like=is_brand_like_query(query_text, compact),
        )
    candidates = merge_candidates(external_results, context_results, rescue_results, external_status)
    enrich_candidates(catalog.rescue_index, candidates, compact)
    if unreadable_mode != "none":
        fragment_candidates = {
            key: candidate
            for key, candidate in candidates.items()
            if unreadable_pattern_matches(
                candidate.key,
                compact,
                ending_compact,
                unreadable_mode,
            )
        }
        candidates = fragment_candidates
        for candidate in candidates.values():
            candidate.score += 2.0
            candidate.reasons.add(f"known_unreadable_{unreadable_mode}")
    if not candidates:
        return {
            "query": raw_query,
            "normalized_query": current_eval.normalize_search(query_text),
            "status": "no_match",
            "message": "No safe match found.",
            "decision_type": "no_match",
            "unreadable_continuation": unreadable_continuation,
            "unreadable_mode": unreadable_mode,
            "ending_fragment": ending_fragment,
            "candidate_count": 0,
            "results": [],
        }

    ranked = rank_candidates(
        list(candidates.values()),
        compact,
        brand_like=is_brand_like_query(query_text, compact) and unreadable_mode == "none",
    )
    if baseline_ranked and ranked and baseline_ranked[0].key != ranked[0].key:
        baseline_top = next(
            (candidate for candidate in ranked if candidate.key == baseline_ranked[0].key),
            None,
        )
        if baseline_top is not None:
            baseline_top.reasons.add("preserved_pre_in_place_score_top")
            ranked = [
                baseline_top,
                *[candidate for candidate in ranked if candidate is not baseline_top],
            ]
    if short_query_rescue_only and external_results:
        external_top_key = current_eval.compact_key(
            external_results[0].get("name")
            or external_results[0].get("candidate_canonical_name")
            or external_results[0].get("commercial_name")
            or ""
        )
        external_top = next(
            (candidate for candidate in ranked if candidate.key == external_top_key),
            None,
        )
        if external_top is not None and ranked and ranked[0] is not external_top:
            external_top.reasons.add("preserved_external_top_for_short_rescue")
            ranked = [
                external_top,
                *[candidate for candidate in ranked if candidate is not external_top],
            ]
    if ENABLE_UNIQUE_NEAREST_RERANK:
        ranked = promote_unique_nearest_candidate(ranked)
    if ENABLE_CONTAINED_NEAREST_RERANK:
        ranked = promote_contained_nearest_candidate(ranked)
    if ENABLE_PRESERVED_TOP_DOMINANT_NEAREST_RERANK:
        ranked = promote_preserved_top_dominant_nearest_candidate(ranked)
    if ENABLE_PRESERVED_TOP_HIGHER_SCORE_NEAREST_RERANK:
        ranked = promote_preserved_top_higher_score_nearest_candidate(
            ranked,
            compact,
        )
    if ENABLE_EXACT_LIGATURE_NEAREST_RERANK:
        ranked = promote_exact_ligature_nearest_candidate(ranked, compact)
    if ENABLE_WEIGHTED_EDGE_TIE_RERANK:
        ranked = promote_weighted_edge_tie_candidate(ranked)
    if ENABLE_WEIGHTED_EDGE_ADVANTAGE_RERANK:
        ranked = promote_weighted_edge_advantage_candidate(ranked)
    if ENABLE_EXACT_KEY_PARETO_TIE_RERANK:
        ranked = promote_exact_key_pareto_tie_candidate(ranked)
    if ENABLE_PHONETIC_POSITION_TIE_RERANK:
        ranked = promote_phonetic_position_tie_candidate(ranked)
    if ENABLE_SHIFTED_EDGE_AGREEMENT_RERANK:
        ranked = promote_shifted_edge_agreement_candidate(ranked)
    if ENABLE_VISUAL_DISTANCE_TIE_RERANK:
        ranked = promote_visual_distance_tie_candidate(ranked)
    if ENABLE_SKELETON_POSITION_TIE_RERANK:
        ranked = promote_skeleton_position_tie_candidate(ranked)
    if ENABLE_LIGATURE_VOWEL_TRANSPOSE_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="ligature_vowel_transposition_chain_retrieval",
            correction_reason="ligature_vowel_transposition_chain_correction",
            max_rank=5,
            max_score_gap=0.40,
            max_raw_disadvantage=1,
            require_unique=True,
        )
    if ENABLE_LIGATURE_VOWEL_TRANSPOSE_EXTENSION_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="ligature_vowel_transposition_chain_retrieval",
            correction_reason="ligature_vowel_transposition_extension_correction",
            max_rank=5,
            max_score_gap=0.75,
            max_raw_disadvantage=1,
            require_unique=True,
            protect_existing_correction=True,
            protect_variant_head=False,
        )
    if ENABLE_LIGATURE_VOWEL_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="ligature_vowel_chain_retrieval",
            correction_reason="ligature_vowel_chain_correction",
            max_rank=5,
            max_score_gap=0.40,
            max_raw_disadvantage=0,
            require_unique=True,
        )
    if ENABLE_LIGATURE_VOWEL_DISTANCE_EXTENSION_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="ligature_vowel_chain_retrieval",
            correction_reason="ligature_vowel_distance_extension_correction",
            max_rank=2,
            max_score_gap=0.05,
            max_raw_disadvantage=1,
            require_unique=True,
            protect_existing_correction=True,
        )
    if ENABLE_LIGATURE_VOWEL_EDGE_EXTENSION_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="ligature_vowel_chain_retrieval",
            correction_reason="ligature_vowel_edge_extension_correction",
            max_rank=2,
            max_score_gap=0.15,
            max_raw_disadvantage=1,
            require_unique=True,
            require_edge_not_worse=True,
            protect_existing_correction=True,
        )
    if ENABLE_LIGATURE_VOWEL_MULTI_CHAIN_EXTENSION_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="ligature_vowel_chain_retrieval",
            correction_reason="ligature_vowel_multi_chain_extension_correction",
            max_rank=5,
            max_score_gap=0.40,
            max_raw_disadvantage=1,
            require_unique=True,
            min_chain_reasons=2,
            protect_existing_correction=True,
        )
    if ENABLE_VISUAL_PHONETIC_CHAIN_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="visual_phonetic_substitution_chain_retrieval",
            correction_reason="visual_phonetic_substitution_chain_correction",
            max_rank=5,
            max_score_gap=0.10,
            max_raw_disadvantage=1,
            require_unique=True,
            require_dual=True,
        )
    if ENABLE_VISUAL_PHONETIC_EXACT_KEY_EXTENSION_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="visual_phonetic_substitution_chain_retrieval",
            correction_reason="visual_phonetic_exact_key_extension_correction",
            max_rank=2,
            max_score_gap=0.40,
            max_raw_disadvantage=0,
            require_unique=True,
            require_exact_key=True,
            require_weighted_not_worse=True,
            protect_existing_correction=True,
        )
    if ENABLE_VISUAL_PHONETIC_DUAL_EXTENSION_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="visual_phonetic_substitution_chain_retrieval",
            correction_reason="visual_phonetic_dual_extension_correction",
            max_rank=4,
            max_score_gap=0.15,
            max_raw_disadvantage=0,
            require_unique=True,
            require_dual=True,
            require_weighted_not_worse=True,
            protect_existing_correction=True,
            protect_variant_head=False,
        )
    if ENABLE_KEYBOARD_VOWEL_DELETE_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="keyboard_vowel_deletion_exact_retrieval",
            correction_reason="keyboard_vowel_deletion_exact_correction",
            max_rank=5,
            max_score_gap=0.0,
            max_raw_disadvantage=1,
            require_unique=True,
            require_exact_key=True,
        )
    if ENABLE_KEYBOARD_EXACT_KEY_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="keyboard_vowel_deletion_exact_retrieval",
            correction_reason="keyboard_vowel_exact_key_correction",
            max_rank=3,
            max_score_gap=0.25,
            max_raw_disadvantage=1,
            require_unique=True,
            require_exact_key=True,
            require_weighted_not_worse=True,
            protect_existing_correction=True,
            protect_variant_head=False,
        )
    if ENABLE_VISUAL_VISUAL_DELETE_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="visual_visual_deletion_chain_retrieval",
            correction_reason="visual_visual_deletion_chain_correction",
            max_rank=3,
            max_score_gap=0.02,
            max_raw_disadvantage=1,
            require_unique=True,
            require_position_not_worse=True,
            protect_existing_correction=True,
        )
    if ENABLE_VISUAL_MULTI_CHAIN_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="visual_visual_deletion_chain_retrieval",
            correction_reason="visual_multi_chain_correction",
            max_rank=3,
            max_score_gap=0.15,
            max_raw_disadvantage=0,
            require_unique=True,
            require_weighted_not_worse=True,
            min_chain_reasons=3,
            protect_existing_correction=True,
        )
    if ENABLE_TRANSPOSITION_DELETE_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="transposition_deletion_exact_retrieval",
            correction_reason="transposition_deletion_exact_correction",
            max_rank=3,
            max_score_gap=0.25,
            max_raw_disadvantage=0,
            require_unique=True,
            require_exact_key=True,
            require_weighted_not_worse=True,
            protect_existing_correction=True,
        )
    if ENABLE_TRANSPOSE_VOWEL_DELETE_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="transposition_vowel_deletion_chain_retrieval",
            correction_reason="transposition_vowel_deletion_chain_correction",
            max_rank=5,
            max_score_gap=0.0,
            max_raw_disadvantage=0,
            require_unique=True,
            protect_existing_correction=True,
            protect_variant_head=False,
        )
    if ENABLE_VOWEL_PHONETIC_DELETE_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="vowel_phonetic_deletion_chain_retrieval",
            correction_reason="vowel_phonetic_deletion_chain_correction",
            max_rank=2,
            max_score_gap=0.25,
            max_raw_disadvantage=2,
            require_unique=True,
            require_weighted_not_worse=True,
            min_chain_reasons=2,
            protect_existing_correction=True,
        )
    if ENABLE_VOWEL_PHONETIC_MULTI_CHAIN_EXTENSION_RERANK:
        ranked = promote_bounded_exact_chain_candidate(
            ranked,
            chain_reason="vowel_phonetic_deletion_chain_retrieval",
            correction_reason="vowel_phonetic_multi_chain_extension_correction",
            max_rank=2,
            max_score_gap=0.10,
            max_raw_disadvantage=2,
            require_unique=True,
            require_exact_key=True,
            min_chain_reasons=2,
            protect_existing_correction=True,
        )
    if ENABLE_WEIGHTED_EXACT_KEY_TIE_RERANK:
        ranked = promote_weighted_exact_key_tie_candidate(ranked, compact)
    if ENABLE_EXACT_TRANSPOSITION_TIE_RERANK:
        ranked = promote_exact_transposition_tie_candidate(ranked, compact)
    if ENABLE_EXACT_TRANSPOSITION_DUAL_EXTENSION_RERANK:
        ranked = promote_exact_transposition_dual_extension_candidate(
            ranked,
            compact,
        )
    if ENABLE_EXACT_KEYBOARD_KEY_TIE_RERANK:
        ranked = promote_exact_keyboard_key_tie_candidate(ranked, compact)
    if ENABLE_EXACT_KEYBOARD_WEIGHTED_EXTENSION_RERANK:
        ranked = promote_exact_keyboard_weighted_extension_candidate(
            ranked,
            compact,
        )
    if ENABLE_EXACT_VISUAL_EDGE_TIE_RERANK:
        ranked = promote_exact_visual_edge_tie_candidate(ranked, compact)
    if ENABLE_GUARDED_TOP_SCORE_DOMINANT_CHAIN_RERANK:
        ranked = promote_guarded_top_score_dominant_chain_candidate(ranked)
    if ENABLE_SCORE_DOMINANT_CHAIN_RELEASE_RERANK:
        ranked = promote_score_dominant_chain_release_candidate(ranked)
    if ENABLE_EXACT_LIGATURE_RANK_EXTENSION_RERANK:
        ranked = promote_exact_ligature_rank_extension_candidate(
            catalog.rescue_index,
            ranked,
            compact,
        )
    if ENABLE_EXACT_PHONETIC_REWRITE_RERANK:
        ranked = promote_exact_phonetic_rewrite_candidate(
            catalog.rescue_index,
            ranked,
            compact,
        )
    if ENABLE_STUTTER_PREFIX_RERANK:
        ranked = promote_exact_stutter_prefix_candidate(ranked, compact)
    ranked = apply_validated_family_head_evidence(ranked, compact)
    ranked = promote_two_sided_anchor_tie_candidate(ranked, compact)
    ranked = surface_short_visible_head_candidates(ranked, compact, limit)
    if unreadable_mode == "none":
        ranked = surface_ordered_character_head_candidate(
            catalog.rescue_index,
            candidates,
            ranked,
            compact,
            limit,
        )
        ranked = promote_candidate_pool_bounded_head_candidate(
            ranked,
            compact,
            limit,
        )
        ranked = promote_pareto_character_evidence_candidate(ranked, compact)
    for candidate in ranked:
        candidate.needs_clarification = (
            unreadable_mode != "none"
            or needs_clarification(catalog.rescue_index, compact, candidate, ranked)
        )
    status, message = response_status(catalog.rescue_index, compact, ranked)
    output = [candidate_to_result(candidate, rank) for rank, candidate in enumerate(ranked[:limit], 1)]
    rescue_pool = sum(int(item.get("_candidate_pool") or 0) for item in rescue_results[:1])
    return {
        "query": raw_query,
        "normalized_query": current_eval.normalize_search(query_text),
        "status": status,
        "message": message,
        "decision_type": decision_type_for_response(
            catalog.rescue_index,
            compact,
            ranked,
            unreadable_mode=unreadable_mode,
            legacy_continuation=legacy_continuation,
        ),
        "unreadable_continuation": unreadable_continuation,
        "unreadable_mode": unreadable_mode,
        "ending_fragment": ending_fragment,
        "candidate_count": len(candidates),
        "child_candidate_count": int(external_response.get("candidate_count") or len(external_results)) + rescue_pool,
        "results": output,
    }


def rescue_search(
    index: RescueIndex,
    raw_query: Any,
    external_results: list[dict[str, Any]],
    external_status: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Return family-level rescue candidates."""

    compact = current_eval.compact_key(raw_query)
    norm = current_eval.normalize_search(raw_query)
    query_skeleton = current_eval.skeleton(raw_query)
    query_phonetic = current_eval.drug_phonetic_key(raw_query)
    core_ids = candidate_family_ids(index, compact, query_skeleton, query_phonetic)
    if should_length_scan(compact, core_ids, external_results, external_status):
        radius = 0 if len(core_ids) >= 220 else 3
        core_ids.update(length_scan_ids(index, compact, radius=radius))
    edge_ids = short_edge_family_ids(index, compact) - core_ids if len(compact) >= 4 else set()
    ids = prefilter_family_ids(index, core_ids, compact, query_skeleton, query_phonetic)
    edge_shortlist_ids = prefilter_family_ids(
        index,
        edge_ids,
        compact,
        query_skeleton,
        query_phonetic,
        limit=EDGE_RESCUE_SHORTLIST_LIMIT,
        use_edit=False,
    )
    selected_edge_ids = prefilter_family_ids(
        index,
        edge_shortlist_ids,
        compact,
        query_skeleton,
        query_phonetic,
        limit=EDGE_RESCUE_PREFILTER_LIMIT,
    )
    ids.update(selected_edge_ids)
    selected_head_ids: set[int] = set()
    if should_run_head_rescue(compact, external_results, external_status):
        head_ids = variant_head_family_ids(index, compact, query_phonetic)
        selected_head_ids = prefilter_family_ids(
            index,
            head_ids,
            compact,
            query_skeleton,
            query_phonetic,
            limit=8,
            allow_head=True,
        )
        ids.update(selected_head_ids)
    short_visible_head_ids = short_visible_head_family_ids(index, compact)
    ids.update(short_visible_head_ids)
    selected_head_ids.update(short_visible_head_ids)

    base_ids = set(ids)
    evidence_reasons: dict[int, set[str]] = defaultdict(set)
    for family_id in short_visible_head_ids:
        evidence_reasons[family_id].add("short_visible_head_retrieval")
    short_frame_ids = short_frame_family_ids(
        index,
        compact,
        query_skeleton,
        query_phonetic,
    ) - base_ids
    ids.update(short_frame_ids)
    for family_id in short_frame_ids:
        evidence_reasons[family_id].add("short_consonant_phonetic_frame_retrieval")
    short_keyboard_ids = short_keyboard_exact_family_ids(index, compact) - base_ids
    ids.update(short_keyboard_ids)
    for family_id in short_keyboard_ids:
        evidence_reasons[family_id].add("short_keyboard_exact_retrieval")
    short_two_deletion_ids = short_two_deletion_family_ids(index, compact) - base_ids
    ids.update(short_two_deletion_ids)
    for family_id in short_two_deletion_ids:
        evidence_reasons[family_id].add("short_two_deletion_frame_retrieval")
    if should_run_nearest_fallback(compact, external_results):
        nearest_ids = bounded_nearest_family_ids(index, compact)
        ids.update(nearest_ids)
        for family_id in nearest_ids:
            evidence_reasons[family_id].add("bounded_nearest_retrieval")

    if should_run_evidence_variant_rescue(compact, external_results):
        for variant, reason in evidence_query_variants(compact):
            variant_skeleton = current_eval.skeleton(variant)
            variant_phonetic = current_eval.drug_phonetic_key(variant)
            variant_ids = candidate_family_ids(
                index,
                variant,
                variant_skeleton,
                variant_phonetic,
            )
            selected_variant_ids = prefilter_family_ids(
                index,
                variant_ids,
                variant,
                variant_skeleton,
                variant_phonetic,
                limit=EVIDENCE_VARIANT_LIMIT,
            )
            ids.update(selected_variant_ids)
            for family_id in selected_variant_ids:
                evidence_reasons[family_id].add(reason)

    pre_multi_step_ids = set(ids)
    mixed_variant_candidates: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for variant, reason in mixed_ligature_transposition_variants(compact):
        variant_skeleton = current_eval.skeleton(variant)
        variant_phonetic = current_eval.drug_phonetic_key(variant)
        variant_ids = (
            index.skeleton.get(variant_skeleton, set())
            & index.phonetic.get(variant_phonetic, set())
        )
        for family_id in variant_ids:
            family = index.families[family_id]
            if abs(len(family.compact) - len(variant)) > 1:
                continue
            if damerau(variant, family.compact, weighted=True) > 1.50:
                continue
            ids.add(family_id)
            mixed_variant_candidates[family_id].append((variant, reason))

    transpose_delete_candidates: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for variant, reason in adjacent_transposition_variants(compact):
        variant_skeleton = current_eval.skeleton(variant)
        variant_phonetic = current_eval.drug_phonetic_key(variant)
        variant_ids = (
            index.skeleton.get(variant_skeleton, set())
            & index.phonetic.get(variant_phonetic, set())
        )
        for family_id in variant_ids:
            family = index.families[family_id]
            if len(family.compact) != len(variant) + 1:
                continue
            if damerau(variant, family.compact, weighted=True) > 1.75:
                continue
            ids.add(family_id)
            transpose_delete_candidates[family_id].append((variant, reason))

    keyboard_delete_candidates: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for variant, reason in keyboard_neighbor_variants(compact):
        variant_skeleton = current_eval.skeleton(variant)
        variant_phonetic = current_eval.drug_phonetic_key(variant)
        variant_ids = (
            index.skeleton.get(variant_skeleton, set())
            & index.phonetic.get(variant_phonetic, set())
        )
        for family_id in variant_ids:
            family = index.families[family_id]
            if len(family.compact) != len(variant) + 1:
                continue
            if damerau(variant, family.compact, weighted=True) > 1.75:
                continue
            ids.add(family_id)
            keyboard_delete_candidates[family_id].append((variant, reason))

    visual_phonetic_chain_candidates = visual_phonetic_chain_family_ids(
        index,
        compact,
    )
    ids.update(visual_phonetic_chain_candidates)
    visual_visual_delete_candidates = (
        visual_visual_deletion_family_ids(index, compact)
        if ENABLE_VISUAL_VISUAL_DELETION_CHAIN
        else set()
    )
    ids.update(visual_visual_delete_candidates)
    transposition_delete_exact_candidates = (
        transposition_deletion_exact_family_ids(index, compact)
        if ENABLE_TRANSPOSITION_DELETION_EXACT_CHAIN
        else set()
    )
    ids.update(transposition_delete_exact_candidates)
    ligature_vowel_chain_candidates = ligature_vowel_chain_family_ids(
        index,
        compact,
    )
    ids.update(ligature_vowel_chain_candidates)
    ligature_vowel_transpose_candidates = (
        ligature_vowel_transposition_family_ids(index, compact)
    )
    ids.update(ligature_vowel_transpose_candidates)
    transpose_vowel_delete_candidates = transpose_vowel_deletion_family_ids(
        index,
        compact,
    )
    ids.update(transpose_vowel_delete_candidates)
    vowel_phonetic_delete_candidates = vowel_phonetic_deletion_family_ids(
        index,
        compact,
    )
    ids.update(vowel_phonetic_delete_candidates)
    keyboard_vowel_delete_exact_candidates = (
        keyboard_vowel_deletion_family_ids(index, compact)
    )
    ids.update(keyboard_vowel_delete_exact_candidates)
    short_ocr_combined_candidates = short_ocr_combined_family_ids(
        index,
        compact,
    )
    ids.update(short_ocr_combined_candidates)

    direct_ligature_variants: dict[int, list[tuple[str, str]]] = defaultdict(list)
    direct_variant_reasons = dict(exact_short_ligature_variants(compact))
    for variant in directional_visual_ligature_variants(compact):
        direct_variant_reasons.setdefault(variant, "ligature_variant_retrieval")
    for variant, reason in direct_variant_reasons.items():
        exact_ids = set(index.exact.get(variant, ()))
        head_ids = set(index.head_exact.get(variant, ()))
        selected_head_ids.update(head_ids)
        for family_id in exact_ids | head_ids:
            ids.add(family_id)
            direct_ligature_variants[family_id].append((variant, reason))

    base_scored = []
    evidence_scored = []
    structural_scored = []
    for family_id in ids:
        family = index.families[family_id]
        evidence_only = family_id not in base_ids
        has_visual_variant = (
            "ocr_visual_variant_retrieval" in evidence_reasons.get(family_id, set())
        )
        item = score_family(
            index,
            family,
            compact,
            norm,
            query_skeleton,
            query_phonetic,
            allow_head=family_id in selected_head_ids,
            ocr_visual=evidence_only and has_visual_variant,
        )
        introduced_only_by_multi_step = (
            family_id not in pre_multi_step_ids
            and (
                family_id in mixed_variant_candidates
                or family_id in transpose_delete_candidates
                or family_id in keyboard_delete_candidates
                or family_id in visual_phonetic_chain_candidates
                or family_id in visual_visual_delete_candidates
                or family_id in transposition_delete_exact_candidates
                or family_id in ligature_vowel_chain_candidates
                or family_id in ligature_vowel_transpose_candidates
                or family_id in transpose_vowel_delete_candidates
                or family_id in vowel_phonetic_delete_candidates
                or family_id in keyboard_vowel_delete_exact_candidates
                or family_id in short_ocr_combined_candidates
            )
        )
        if introduced_only_by_multi_step:
            item = None
        if item is None and not evidence_only and has_visual_variant:
            item = score_family(
                index,
                family,
                compact,
                norm,
                query_skeleton,
                query_phonetic,
                allow_head=family_id in selected_head_ids,
                ocr_visual=True,
            )
            evidence_only = item is not None
        mixed_item = None
        if item is None:
            mixed_item = best_mixed_variant_score(
                index,
                family,
                compact,
                mixed_variant_candidates.get(family_id, ()),
            )
        if mixed_item and (
            item is None or float(mixed_item["score"]) > float(item["score"])
        ):
            item = mixed_item
            evidence_only = True
        transpose_delete_item = None
        if item is None:
            transpose_delete_item = best_deletion_frame_variant_score(
                index,
                family,
                compact,
                transpose_delete_candidates.get(family_id, ()),
                score_discount=TRANSPOSE_DELETE_SCORE_DISCOUNT,
            )
        if transpose_delete_item:
            item = transpose_delete_item
            evidence_only = True
        keyboard_delete_item = None
        if item is None:
            keyboard_delete_item = best_deletion_frame_variant_score(
                index,
                family,
                compact,
                keyboard_delete_candidates.get(family_id, ()),
                score_discount=KEYBOARD_DELETE_SCORE_DISCOUNT,
            )
        if keyboard_delete_item:
            item = keyboard_delete_item
            evidence_only = True
        visual_phonetic_chain_item = best_exact_chain_score(
            index,
            family,
            family_id in visual_phonetic_chain_candidates,
            reason="visual_phonetic_substitution_chain_retrieval",
            score_discount=(
                VISUAL_PHONETIC_CHAIN_SCORE_DISCOUNT
                - (0.10 if ENABLE_VISUAL_PHONETIC_SCORE_TUNING else 0.0)
            ),
        )
        if visual_phonetic_chain_item:
            if item is None:
                item = visual_phonetic_chain_item
                evidence_only = True
            elif (
                ENABLE_VISUAL_PHONETIC_IN_PLACE_SCORE
                and float(visual_phonetic_chain_item["score"]) > float(item["score"])
            ):
                item["_pre_multi_step_score"] = item["score"]
                item["_pre_multi_step_removed_reasons"] = sorted(
                    set(visual_phonetic_chain_item.get("reasons", ()))
                    - set(item.get("reasons", ()))
                    - {"visual_phonetic_substitution_chain_retrieval"}
                )
                item["score"] = visual_phonetic_chain_item["score"]
                item["reasons"] = sorted(
                    {
                        *item.get("reasons", ()),
                        *visual_phonetic_chain_item.get("reasons", ()),
                    }
                )
        visual_visual_delete_item = best_exact_chain_score(
            index,
            family,
            family_id in visual_visual_delete_candidates and item is None,
            reason="visual_visual_deletion_chain_retrieval",
            score_discount=VISUAL_VISUAL_DELETE_SCORE_DISCOUNT,
        )
        if visual_visual_delete_item:
            item = visual_visual_delete_item
            evidence_only = True
        transposition_delete_exact_item = best_exact_chain_score(
            index,
            family,
            family_id in transposition_delete_exact_candidates,
            reason="transposition_deletion_exact_retrieval",
            score_discount=TRANSPOSITION_DELETE_EXACT_SCORE_DISCOUNT,
        )
        if transposition_delete_exact_item:
            if item is None:
                item = transposition_delete_exact_item
                evidence_only = True
            elif float(transposition_delete_exact_item["score"]) > float(item["score"]):
                item["score"] = transposition_delete_exact_item["score"]
                item["reasons"] = sorted(
                    {
                        *item.get("reasons", ()),
                        *transposition_delete_exact_item.get("reasons", ()),
                    }
                )
        ligature_vowel_chain_item = best_exact_chain_score(
            index,
            family,
            family_id in ligature_vowel_chain_candidates,
            reason="ligature_vowel_chain_retrieval",
            score_discount=LIGATURE_VOWEL_CHAIN_SCORE_DISCOUNT,
        )
        if ligature_vowel_chain_item:
            if item is None:
                item = ligature_vowel_chain_item
                evidence_only = True
            elif (
                ENABLE_LIGATURE_VOWEL_IN_PLACE_SCORE
                and float(ligature_vowel_chain_item["score"]) > float(item["score"])
            ):
                item["_pre_multi_step_score"] = item["score"]
                item["_pre_multi_step_removed_reasons"] = sorted(
                    set(ligature_vowel_chain_item.get("reasons", ()))
                    - set(item.get("reasons", ()))
                    - {"ligature_vowel_chain_retrieval"}
                )
                item["score"] = ligature_vowel_chain_item["score"]
                item["reasons"] = sorted(
                    {
                        *item.get("reasons", ()),
                        *ligature_vowel_chain_item.get("reasons", ()),
                    }
                )
        ligature_vowel_transpose_item = best_exact_chain_score(
            index,
            family,
            family_id in ligature_vowel_transpose_candidates,
            reason="ligature_vowel_transposition_chain_retrieval",
            score_discount=LIGATURE_VOWEL_TRANSPOSE_SCORE_DISCOUNT,
        )
        if ligature_vowel_transpose_item:
            if item is None:
                item = ligature_vowel_transpose_item
                evidence_only = True
            elif (
                ENABLE_LIGATURE_VOWEL_TRANSPOSE_IN_PLACE_SCORE
                and float(ligature_vowel_transpose_item["score"])
                > float(item["score"])
            ):
                item["_pre_multi_step_score"] = item["score"]
                item["_pre_multi_step_removed_reasons"] = sorted(
                    set(ligature_vowel_transpose_item.get("reasons", ()))
                    - set(item.get("reasons", ()))
                    - {"ligature_vowel_transposition_chain_retrieval"}
                )
                item["score"] = ligature_vowel_transpose_item["score"]
                item["reasons"] = sorted(
                    {
                        *item.get("reasons", ()),
                        *ligature_vowel_transpose_item.get("reasons", ()),
                    }
                )
        transpose_vowel_delete_item = best_exact_chain_score(
            index,
            family,
            family_id in transpose_vowel_delete_candidates,
            reason="transposition_vowel_deletion_chain_retrieval",
            score_discount=(
                TRANSPOSE_VOWEL_DELETE_SCORE_DISCOUNT
                - (
                    0.45
                    if ENABLE_TRANSPOSE_VOWEL_DELETE_SCORE_TUNING
                    and item is not None
                    and not evidence_only
                    else 0.0
                )
            ),
        )
        if transpose_vowel_delete_item:
            if item is None:
                item = transpose_vowel_delete_item
                evidence_only = True
            elif (
                ENABLE_TRANSPOSE_VOWEL_DELETE_IN_PLACE_SCORE
                and float(transpose_vowel_delete_item["score"]) > float(item["score"])
            ):
                item["_pre_multi_step_score"] = item["score"]
                item["_pre_multi_step_removed_reasons"] = sorted(
                    set(transpose_vowel_delete_item.get("reasons", ()))
                    - set(item.get("reasons", ()))
                    - {"transposition_vowel_deletion_chain_retrieval"}
                )
                item["score"] = transpose_vowel_delete_item["score"]
                item["reasons"] = sorted(
                    {
                        *item.get("reasons", ()),
                        *transpose_vowel_delete_item.get("reasons", ()),
                    }
                )
        vowel_phonetic_delete_item = best_exact_chain_score(
            index,
            family,
            family_id in vowel_phonetic_delete_candidates
            and item is None,
            reason="vowel_phonetic_deletion_chain_retrieval",
            score_discount=VOWEL_PHONETIC_DELETE_SCORE_DISCOUNT,
        )
        if vowel_phonetic_delete_item:
            item = vowel_phonetic_delete_item
            evidence_only = True
        keyboard_vowel_delete_exact_item = best_exact_chain_score(
            index,
            family,
            family_id in keyboard_vowel_delete_exact_candidates,
            reason="keyboard_vowel_deletion_exact_retrieval",
            score_discount=(
                KEYBOARD_VOWEL_DELETE_EXACT_SCORE_DISCOUNT
                - (
                    0.05
                    if ENABLE_KEYBOARD_VOWEL_DELETE_SCORE_TUNING
                    and item is not None
                    and "keyboard_deletion_frame_retrieval"
                    in item.get("reasons", ())
                    else 0.0
                )
            ),
        )
        if keyboard_vowel_delete_exact_item:
            if item is None:
                item = keyboard_vowel_delete_exact_item
                evidence_only = True
            elif (
                "multi_step_variant_score" in item.get("reasons", ())
                and float(keyboard_vowel_delete_exact_item["score"])
                > float(item["score"])
            ):
                item = keyboard_vowel_delete_exact_item
                evidence_only = True
            elif (
                ENABLE_KEYBOARD_VOWEL_DELETE_IN_PLACE_SCORE
                and not evidence_only
                and float(keyboard_vowel_delete_exact_item["score"])
                > float(item["score"])
            ):
                item["_pre_multi_step_score"] = item["score"]
                item["_pre_multi_step_removed_reasons"] = sorted(
                    set(keyboard_vowel_delete_exact_item.get("reasons", ()))
                    - set(item.get("reasons", ()))
                    - {"keyboard_vowel_deletion_exact_retrieval"}
                )
                item["score"] = keyboard_vowel_delete_exact_item["score"]
                item["reasons"] = sorted(
                    {
                        *item.get("reasons", ()),
                        *keyboard_vowel_delete_exact_item.get("reasons", ()),
                    }
                )
        short_ocr_combined_item = best_exact_chain_score(
            index,
            family,
            family_id in short_ocr_combined_candidates
            and item is None,
            reason="short_ocr_combined_retrieval",
            score_discount=SHORT_OCR_COMBINED_SCORE_DISCOUNT,
        )
        if short_ocr_combined_item:
            item = short_ocr_combined_item
            evidence_only = True
        short_two_deletion_item = None
        if item is None and family_id in short_two_deletion_ids:
            short_two_deletion_item = best_short_two_deletion_score(
                index,
                family,
                compact,
            )
        if short_two_deletion_item:
            item = short_two_deletion_item
            evidence_only = True
        if item:
            exact_chain_reasons = set()
            if family_id in visual_phonetic_chain_candidates:
                exact_chain_reasons.add("visual_phonetic_substitution_chain_retrieval")
            if family_id in visual_visual_delete_candidates:
                exact_chain_reasons.add("visual_visual_deletion_chain_retrieval")
            if family_id in transposition_delete_exact_candidates:
                exact_chain_reasons.add("transposition_deletion_exact_retrieval")
            if family_id in ligature_vowel_chain_candidates:
                exact_chain_reasons.add("ligature_vowel_chain_retrieval")
            if family_id in ligature_vowel_transpose_candidates:
                exact_chain_reasons.add("ligature_vowel_transposition_chain_retrieval")
            if family_id in transpose_vowel_delete_candidates:
                exact_chain_reasons.add("transposition_vowel_deletion_chain_retrieval")
            if family_id in vowel_phonetic_delete_candidates:
                exact_chain_reasons.add("vowel_phonetic_deletion_chain_retrieval")
            if family_id in keyboard_vowel_delete_exact_candidates:
                exact_chain_reasons.add("keyboard_vowel_deletion_exact_retrieval")
            if family_id in short_ocr_combined_candidates:
                exact_chain_reasons.add("short_ocr_combined_retrieval")
            if family_id in short_two_deletion_ids:
                exact_chain_reasons.add("short_two_deletion_frame_retrieval")
            if exact_chain_reasons:
                item["reasons"] = sorted(
                    {
                        *item.get("reasons", ()),
                        *exact_chain_reasons,
                    }
                )
            item["_multi_step_only"] = introduced_only_by_multi_step
            if family_id in selected_edge_ids:
                item["reasons"] = sorted({*item["reasons"], "two_char_edge_retrieval"})
            if family_id in evidence_reasons:
                item["reasons"] = sorted({*item["reasons"], *evidence_reasons[family_id]})
            if evidence_only:
                item["_evidence_only"] = True
                evidence_scored.append(item)
            else:
                base_scored.append(item)
        structural_item = best_structural_variant_score(
            index,
            family,
            compact,
            direct_ligature_variants.get(family_id, ()),
        )
        if structural_item:
            structural_item["_evidence_only"] = True
            structural_scored.append(structural_item)
    has_in_place_score = any(
        "_pre_multi_step_score" in row
        for row in (*base_scored, *evidence_scored, *structural_scored)
    )
    baseline_base_scored: list[dict[str, Any]] = []
    baseline_evidence_scored: list[dict[str, Any]] = []
    baseline_structural_scored: list[dict[str, Any]] = []
    if has_in_place_score:
        baseline_key = lambda row: (
            -float(row.get("_pre_multi_step_score", row["score"])),
            str(row["name"]),
        )
        baseline_base_scored = sorted(base_scored, key=baseline_key)
        baseline_evidence_scored = sorted(evidence_scored, key=baseline_key)
        baseline_structural_scored = sorted(structural_scored, key=baseline_key)
        for rank, row in enumerate(baseline_base_scored, 1):
            row["_pre_multi_step_merge_rank"] = rank
        for rank, row in enumerate(
            baseline_evidence_scored,
            len(baseline_base_scored) + 1,
        ):
            row["_pre_multi_step_merge_rank"] = rank
        for rank, row in enumerate(
            baseline_structural_scored,
            len(baseline_base_scored) + len(baseline_evidence_scored) + 1,
        ):
            row["_pre_multi_step_merge_rank"] = rank

    base_scored.sort(key=lambda row: (-float(row["score"]), str(row["name"])))
    evidence_scored.sort(key=lambda row: (-float(row["score"]), str(row["name"])))
    structural_scored.sort(key=lambda row: (-float(row["score"]), str(row["name"])))
    for rank, row in enumerate(base_scored, 1):
        row["_merge_rank"] = rank
    for rank, row in enumerate(evidence_scored, len(base_scored) + 1):
        row["_merge_rank"] = rank
    for rank, row in enumerate(
        structural_scored,
        len(base_scored) + len(evidence_scored) + 1,
    ):
        row["_merge_rank"] = rank
    scored = [
        *base_scored[:limit],
        *evidence_scored[:NEAREST_FALLBACK_LIMIT],
        *structural_scored[:NEAREST_FALLBACK_LIMIT],
    ]
    selected_ids = {id(row) for row in scored}
    chain_supported = [
        row
        for row in base_scored
        if set(row.get("reasons", ())) & EXACT_CHAIN_EVIDENCE_REASONS
    ]
    scored.extend(
        row
        for row in chain_supported[:NEAREST_FALLBACK_LIMIT]
        if id(row) not in selected_ids
    )
    if has_in_place_score:
        baseline_selected = [
            *baseline_base_scored[:limit],
            *baseline_evidence_scored[:NEAREST_FALLBACK_LIMIT],
            *baseline_structural_scored[:NEAREST_FALLBACK_LIMIT],
        ]
        selected_ids = {id(row) for row in scored}
        scored.extend(row for row in baseline_selected if id(row) not in selected_ids)
    for row in scored:
        row["_candidate_pool"] = len(ids)
    return scored


def pre_multi_step_rescue_view(
    rescue_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reconstruct rescue scores before an in-place exact-chain adjustment."""

    if not any("_pre_multi_step_score" in item for item in rescue_results):
        return []
    baseline = []
    for item in rescue_results:
        row = dict(item)
        row["score"] = row.pop("_pre_multi_step_score", row["score"])
        removed_reasons = set(
            row.pop("_pre_multi_step_removed_reasons", ())
        )
        row["reasons"] = sorted(set(row.get("reasons", ())) - removed_reasons)
        row["_merge_rank"] = row.pop(
            "_pre_multi_step_merge_rank",
            row.get("_merge_rank"),
        )
        baseline.append(row)
    return baseline


def best_structural_variant_score(
    index: RescueIndex,
    family: FamilyRecord,
    original_compact: str,
    variants: Iterable[tuple[str, str]],
) -> dict[str, Any] | None:
    """Score one-step OCR variants without treating them as literal exact input."""

    best: dict[str, Any] | None = None
    for variant, reason in variants:
        if reason not in {
            "ligature_variant_retrieval",
            "ligature_expansion_retrieval",
        }:
            continue
        full_variant_distance = damerau(variant, family.compact, weighted=False)
        head_variant_distance = (
            damerau(variant, family.head_compact, weighted=False)
            if family.head_compact
            else 999.0
        )
        use_head = head_variant_distance < full_variant_distance
        evidence_target = family.head_compact if use_head else family.compact
        original_distance = damerau(original_compact, evidence_target, weighted=False)
        variant_distance = damerau(variant, evidence_target, weighted=False)
        if variant_distance > 2 or original_distance - variant_distance < 1:
            continue
        item = score_family(
            index,
            family,
            variant,
            current_eval.normalize_search(variant),
            current_eval.skeleton(variant),
            current_eval.drug_phonetic_key(variant),
            allow_head=use_head,
        )
        if item is None:
            continue
        item["score"] = round(
            max(0.01, float(item["score"]) - STRUCTURAL_VARIANT_SCORE_DISCOUNT),
            6,
        )
        item["reasons"] = sorted(
            {
                *item.get("reasons", ()),
                reason,
                "structural_variant_score",
            }
            - {"exact_family"}
        )
        if best is None or float(item["score"]) > float(best["score"]):
            best = item
    return best


def candidate_family_ids(index: RescueIndex, compact: str, query_skeleton: str, query_phonetic: str) -> set[int]:
    """Generate a bounded family candidate set for rescue scoring."""

    ids: set[int] = set()
    ids.update(index.exact.get(compact, ()))
    if len(compact) >= 3:
        ids.update(index.prefix.get(compact[: min(12, len(compact))], ()))
        for alternative in first_char_variants(compact):
            ids.update(index.prefix.get(alternative[: min(12, len(alternative))], ()))
    if len(compact) >= 4:
        ids.update(index.suffix.get(compact[::-1][: min(12, len(compact))], ()))
    for gram in rarest(compact, 4, index.grams4, 4):
        ids.update(index.grams4.get(gram, ()))
    if len(ids) < 160:
        for gram in rarest(compact, 3, index.grams3, 5):
            ids.update(index.grams3.get(gram, ()))
    if len(query_skeleton) >= 3:
        ids.update(index.skeleton.get(query_skeleton, ()))
        ids.update(index.skeleton_prefix.get(query_skeleton[: min(10, len(query_skeleton))], ()))
    if len(query_phonetic) >= 3:
        ids.update(index.phonetic.get(query_phonetic, ()))
        ids.update(index.phonetic_prefix.get(query_phonetic[: min(10, len(query_phonetic))], ()))
    if ENABLE_EXACT_LIGATURE_RANK_EXTENSION_RERANK:
        for variant in single_ligature_variants(compact):
            ids.update(index.exact.get(variant, ()))
    if ENABLE_EXACT_PHONETIC_REWRITE_RERANK:
        for variant in single_phonetic_rewrite_variants(compact):
            ids.update(index.exact.get(variant, ()))
    if ENABLE_STUTTER_PREFIX_RERANK:
        for variant in stutter_prefix_variants(compact):
            ids.update(index.exact.get(variant, ()))
    # A three-character OCR query can be a one-deletion key for a four-character family.
    if 3 <= len(compact) <= 18:
        for key in delete_keys(compact, max_deletes_for(compact)):
            bucket = index.delete_index.get(key)
            if bucket and len(bucket) <= 650:
                ids.update(bucket)
    return ids


def ordered_character_head_family_id(
    index: RescueIndex,
    compact: str,
) -> int | None:
    """Find one catalog head supported by several ordered visible fragments."""

    if not (7 <= len(compact) <= 16):
        return None
    query_bigrams = char_ngrams(compact, 2)
    family_ids: set[int] = set()
    for bigram in query_bigrams:
        family_ids.update(index.grams2.get(bigram, ()))

    representatives: dict[str, int] = {}
    distances: dict[str, float] = {}
    for family_id in family_ids:
        family = index.families[family_id]
        head = family.head_compact or family.compact
        if not head or not (
            compact[:1] == head[:1]
            or first_chars_confusable(compact[:1], head[:1])
        ):
            continue
        if len(query_bigrams & char_ngrams(head, 2)) < 3:
            continue
        distance = damerau(compact, head, weighted=False)
        if distance / max(len(compact), len(head), 1) > 0.46:
            continue
        lcs = longest_common_subsequence_length(compact, head)
        if (
            lcs / max(len(compact), 1) < 0.54
            or lcs / max(len(head), 1) < 0.65
        ):
            continue
        current_id = representatives.get(head)
        if current_id is None or (
            len(family.compact),
            family.name,
        ) < (
            len(index.families[current_id].compact),
            index.families[current_id].name,
        ):
            representatives[head] = family_id
            distances[head] = distance

    if not representatives:
        return None
    nearest_distance = min(distances.values())
    nearest_heads = [
        head for head, distance in distances.items()
        if distance == nearest_distance
    ]
    if len(nearest_heads) != 1:
        return None
    return representatives[nearest_heads[0]]


def short_keyboard_exact_family_ids(index: RescueIndex, compact: str) -> set[int]:
    """Return three-character families one adjacent keyboard substitution away."""

    if len(compact) != 3:
        return set()
    family_ids: set[int] = set()
    for position, character in enumerate(compact):
        for replacement in sorted(
            current_eval.KEY_NEIGHBORS.get(character, set()) - {character}
        ):
            variant = compact[:position] + replacement + compact[position + 1 :]
            family_ids.update(index.exact.get(variant, ()))
    return family_ids


def short_two_deletion_frames(compact: str) -> list[tuple[str, bool]]:
    """Return the visible frame and optional one-vowel corrections."""

    frames = {(compact, False)}
    for position, character in enumerate(compact):
        if character not in VOWELS:
            continue
        for replacement in VOWELS - {character}:
            frames.add(
                (
                    compact[:position]
                    + replacement
                    + compact[position + 1 :],
                    True,
                )
            )
    return sorted(frames)


def short_two_deletion_family_ids(index: RescueIndex, compact: str) -> set[int]:
    """Return length+2 families containing a short visible ordered frame."""

    if not (3 <= len(compact) <= 4):
        return set()
    family_ids: set[int] = set()
    frames = short_two_deletion_frames(compact)
    for family_id in index.length.get(len(compact) + 2, ()):
        family = index.families[family_id]
        if any(subsequence_score(frame, family.compact) > 0 for frame, _ in frames):
            family_ids.add(family_id)
    return family_ids


def best_short_two_deletion_score(
    index: RescueIndex,
    family: FamilyRecord,
    compact: str,
) -> dict[str, Any] | None:
    """Score a two-deletion frame, penalizing an additional vowel correction."""

    best: dict[str, Any] | None = None
    for frame, changed_vowel in short_two_deletion_frames(compact):
        if subsequence_score(frame, family.compact) <= 0:
            continue
        item = score_family(
            index,
            family,
            frame,
            current_eval.normalize_search(frame),
            current_eval.skeleton(frame),
            current_eval.drug_phonetic_key(frame),
        )
        if item is None:
            continue
        if changed_vowel:
            item["score"] = round(
                max(
                    0.01,
                    float(item["score"]) - SHORT_TWO_DELETION_VOWEL_DISCOUNT,
                ),
                6,
            )
        item["reasons"] = sorted(
            {
                *item.get("reasons", ()),
                "short_two_deletion_frame_retrieval",
                "multi_step_variant_score",
            }
        )
        if best is None or float(item["score"]) > float(best["score"]):
            best = item
    return best


def short_frame_family_ids(
    index: RescueIndex,
    compact: str,
    query_skeleton: str,
    query_phonetic: str,
) -> set[int]:
    """Recover bounded candidates when vowels leave a short consonant frame."""

    if not (3 <= len(compact) <= 7):
        return set()
    if not (
        1 <= len(query_skeleton) <= 2
        and 1 <= len(query_phonetic) <= 2
    ):
        return set()

    candidate_ids = (
        index.skeleton.get(query_skeleton, set())
        & index.phonetic.get(query_phonetic, set())
    )
    eligible = []
    for family_id in candidate_ids:
        family = index.families[family_id]
        if abs(len(family.compact) - len(compact)) > 2:
            continue
        raw_distance = damerau(compact, family.compact, weighted=False)
        weighted_distance = damerau(compact, family.compact, weighted=True)
        if raw_distance > SHORT_FRAME_MAX_RAW_DISTANCE:
            continue
        if weighted_distance > SHORT_FRAME_MAX_WEIGHTED_DISTANCE:
            continue
        eligible.append(
            (
                weighted_distance,
                raw_distance,
                -same_position_score(compact, family.compact),
                family.name,
                family_id,
            )
        )

    eligible.sort()
    return {
        family_id
        for *_, family_id in eligible[:SHORT_FRAME_RETRIEVAL_LIMIT]
    }


def short_edge_family_ids(index: RescueIndex, compact: str) -> set[int]:
    """Return compatible-length families sharing a two-character edge."""

    candidates = set(index.prefix.get(compact[:2], ()))
    candidates.update(index.suffix.get(compact[::-1][:2], ()))
    return {
        family_id
        for family_id in candidates
        if abs(len(index.families[family_id].compact) - len(compact)) <= 2
    }


def supports_short_visible_head(compact: str, head: str) -> bool:
    """Return whether a short visible string is direct evidence for a family head."""

    if not (3 <= len(compact) <= 4) or not head:
        return False
    if head.startswith(compact) and len(head) > len(compact):
        return True
    missing = len(head) - len(compact)
    return 1 <= missing <= 2 and is_ordered_subsequence(compact, head)


def short_visible_head_family_ids(index: RescueIndex, compact: str) -> set[int]:
    """Return one representative per family head supported by a short fragment."""

    if not (3 <= len(compact) <= 4):
        return set()
    candidates = set(index.head_prefix.get(compact, ()))
    candidates.update(index.head_delete.get(compact, ()))
    representatives: dict[str, int] = {}
    for family_id in candidates:
        family = index.families[family_id]
        if not supports_short_visible_head(compact, family.head_compact):
            continue
        current_id = representatives.get(family.head_compact)
        if current_id is None:
            representatives[family.head_compact] = family_id
            continue
        current = index.families[current_id]
        if (
            len(family.compact),
            family.name,
        ) < (
            len(current.compact),
            current.name,
        ):
            representatives[family.head_compact] = family_id

    ordered = sorted(
        representatives.values(),
        key=lambda family_id: (
            len(index.families[family_id].head_compact) - len(compact),
            index.families[family_id].head_compact,
            index.families[family_id].name,
        ),
    )
    return set(ordered[:SHORT_VISIBLE_HEAD_LIMIT])


def should_run_head_rescue(
    compact: str,
    external_results: list[dict[str, Any]],
    external_status: str,
) -> bool:
    """Gate family-head fallback to weak short/medium brand-like searches."""

    if not (5 <= len(compact) <= 18):
        return False
    top_score = float(external_results[0].get("score") or 0.0) if external_results else 0.0
    for item in external_results[:3]:
        name = str(
            item.get("name")
            or item.get("candidate_canonical_name")
            or item.get("commercial_name")
            or ""
        )
        candidate_key = current_eval.compact_key(name)
        candidate_distance = (
            damerau(compact, candidate_key, weighted=False)
            if candidate_key
            else 999.0
        )
        if candidate_distance == 0:
            return False
        if (
            candidate_distance == 1
            and external_status in CONFIDENT_EXTERNAL_STATUSES
            and top_score >= 0.78
        ):
            return False
        if candidate_key and len(candidate_key) >= 5 and compact.startswith(candidate_key):
            # The child already found the visible brand and the remaining
            # query is likely strength/form/route context, not a family-head
            # spelling failure.
            return False
    second_score = float(external_results[1].get("score") or 0.0) if len(external_results) > 1 else 0.0
    if external_status not in CONFIDENT_EXTERNAL_STATUSES:
        return top_score < 0.72 or (top_score - second_score) < 0.08
    return top_score < 0.58


def variant_head_family_ids(index: RescueIndex, compact: str, query_phonetic: str) -> set[int]:
    """Generate bounded candidates from validated catalog family heads."""

    ids = set(index.head_exact.get(compact, ()))
    if len(query_phonetic) >= 3:
        ids.update(index.head_phonetic.get(query_phonetic, ()))
    for key in delete_keys(compact, 2):
        ids.update(index.head_delete.get(key, ()))

    first_chars = {compact[:1], *first_char_variants(compact)}
    first_chars = {value[:1] for value in first_chars if value}
    return {
        family_id
        for family_id in ids
        if index.families[family_id].head_compact[:1] in first_chars
        and damerau(
            compact,
            index.families[family_id].head_compact,
            weighted=False,
        ) <= VALIDATED_HEAD_MAX_DISTANCE
    }


def should_length_scan(
    compact: str,
    ids: set[int],
    external_results: list[dict[str, Any]],
    external_status: str,
) -> bool:
    """Gate the more expensive length-bucket scan to typo-heavy query shapes."""

    if not (4 <= len(compact) <= 12):
        return False
    if external_status not in CONFIDENT_EXTERNAL_STATUSES:
        top_score = float(external_results[0].get("score") or 0.0) if external_results else 0.0
        return len(ids) < 220 or (len(compact) <= 5 and top_score < 0.50)
    if len(ids) >= 220:
        return False
    top_score = float(external_results[0].get("score") or 0.0) if external_results else 0.0
    second_score = float(external_results[1].get("score") or 0.0) if len(external_results) > 1 else 0.0
    return top_score < 0.90 or (top_score - second_score) < 0.10


def should_run_rescue(
    compact: str,
    external_results: list[dict[str, Any]],
    external_status: str,
    *,
    include_short_query: bool = True,
) -> bool:
    """Gate Algorithm 5's rescue pass so normal queries stay close to Algorithm 2 cost."""

    if include_short_query and ENABLE_SHORT_QUERY_RESCUE and 3 <= len(compact) <= 4:
        return True
    if not external_results:
        return True
    top_score = float(external_results[0].get("score") or 0.0)
    second_score = float(external_results[1].get("score") or 0.0) if len(external_results) > 1 else 0.0
    score_gap = top_score - second_score
    if external_status not in CONFIDENT_EXTERNAL_STATUSES:
        return not (len(compact) >= 6 and top_score >= 0.78 and score_gap >= 0.08)
    if top_score < RESCUE_UNCERTAIN_SCORE_THRESHOLD:
        return True
    if score_gap < RESCUE_UNCERTAIN_GAP_THRESHOLD:
        return True
    return False


def should_run_evidence_variant_rescue(
    compact: str,
    external_results: list[dict[str, Any]],
) -> bool:
    """Use one documented OCR transformation only when the original search is weak."""

    if sum(char.isdigit() for char in compact) == 1:
        return True
    return should_run_nearest_fallback(compact, external_results)


def should_run_nearest_fallback(
    compact: str,
    external_results: list[dict[str, Any]],
) -> bool:
    """Gate compatible-length nearest retrieval by the external top distance."""

    if not (3 <= len(compact) <= 16):
        return False
    if not external_results:
        return True
    top_name = str(
        external_results[0].get("name")
        or external_results[0].get("candidate_canonical_name")
        or external_results[0].get("commercial_name")
        or ""
    )
    top_key = current_eval.compact_key(top_name)
    if not top_key:
        return True
    return damerau(compact, top_key, weighted=False) > nearest_fallback_radius(compact)


def nearest_fallback_radius(compact: str) -> int:
    """Return the largest typo radius justified by the visible query length."""

    if len(compact) <= 3:
        return 1
    if len(compact) <= 6:
        return 2
    if len(compact) <= 9:
        return 3
    return 4


def bounded_nearest_family_ids(index: RescueIndex, compact: str) -> set[int]:
    """Return a small nearest set from compatible lengths and plausible starts."""

    radius = nearest_fallback_radius(compact)
    first_chars = plausible_first_characters(compact)
    candidates: set[int] = set()
    for length in range(max(1, len(compact) - radius), len(compact) + radius + 1):
        candidates.update(
            family_id
            for family_id in index.length.get(length, ())
            if index.families[family_id].compact[:1] in first_chars
        )

    nearest_distance = radius + 1
    nearest_ids: list[int] = []
    for family_id in candidates:
        distance = damerau(compact, index.families[family_id].compact, weighted=False)
        if distance < nearest_distance:
            nearest_distance = int(distance)
            nearest_ids = [family_id]
        elif distance == nearest_distance:
            nearest_ids.append(family_id)
    if nearest_distance > radius or len(nearest_ids) > NEAREST_FALLBACK_LIMIT:
        return set()
    return set(nearest_ids)


def plausible_first_characters(compact: str) -> set[str]:
    """Collect first letters supported by one visual, phonetic, or swap event."""

    if not compact:
        return set()
    out = {compact[0]}
    out.update(value[:1] for value in first_char_variants(compact) if value)
    out.update(OCR_DIGIT_TO_LETTERS.get(compact[0], ()))
    if len(compact) >= 4:
        out.add(compact[1])
    for source, target in LIGATURE_CONFUSION_PAIRS:
        if compact.startswith(source):
            out.add(target[0])
    return out


def evidence_query_variants(compact: str) -> list[tuple[str, str]]:
    """Generate bounded one-step query variants from documented OCR evidence."""

    variants: dict[str, str] = {}

    def add_variant(value: str, reason: str) -> None:
        if value and value != compact and len(variants) < EVIDENCE_VARIANT_LIMIT:
            variants.setdefault(value, reason)

    if sum(char.isdigit() for char in compact) == 1:
        for position, char in enumerate(compact):
            for replacement in sorted(OCR_DIGIT_TO_LETTERS.get(char, ())):
                add_variant(
                    compact[:position] + replacement + compact[position + 1 :],
                    "ocr_visual_variant_retrieval",
                )
    if len(compact) >= 4 and compact[0] != compact[1]:
        add_variant(compact[1] + compact[0] + compact[2:], "leading_transposition_retrieval")
    for source, target in LIGATURE_CONFUSION_PAIRS:
        start = 0
        while len(variants) < EVIDENCE_VARIANT_LIMIT:
            position = compact.find(source, start)
            if position < 0:
                break
            add_variant(
                compact[:position] + target + compact[position + len(source) :],
                "ligature_variant_retrieval",
            )
            start = position + 1
    return list(variants.items())


def stutter_prefix_variants(compact: str) -> set[str]:
    """Remove one duplicated two- or three-character query prefix."""

    return {
        compact[width:]
        for width in (2, 3)
        if len(compact) > 2 * width and compact[:width] == compact[width : 2 * width]
    }


def single_ligature_variants(compact: str) -> set[str]:
    """Return every query formed by reversing one documented ligature."""

    variants: set[str] = set()
    for source, target in LIGATURE_CONFUSION_PAIRS:
        start = 0
        while True:
            position = compact.find(source, start)
            if position < 0:
                break
            variants.add(
                compact[:position] + target + compact[position + len(source) :]
            )
            start = position + 1
    variants.discard(compact)
    return variants


def directional_visual_ligature_variants(compact: str) -> set[str]:
    """Return one-step variants for directional multi-character visual evidence."""

    variants: set[str] = set()
    for source, target in DIRECTIONAL_VISUAL_LIGATURE_PAIRS:
        start = 0
        while True:
            position = compact.find(source, start)
            if position < 0:
                break
            variants.add(
                compact[:position] + target + compact[position + len(source) :]
            )
            start = position + 1
    return variants


def single_phonetic_rewrite_variants(compact: str) -> set[str]:
    """Return every query formed by one standard phonetic rewrite."""

    variants: set[str] = set()
    for source, target in PHONETIC_REWRITE_PAIRS:
        start = 0
        while True:
            position = compact.find(source, start)
            if position < 0:
                break
            variants.add(
                compact[:position] + target + compact[position + len(source) :]
            )
            start = position + 1
    variants.discard(compact)
    return variants


def exact_short_ligature_variants(compact: str) -> list[tuple[str, str]]:
    """Reverse one ligature only when it exactly names a short catalog family."""

    if not (3 <= len(compact) <= 4):
        return []
    pairs = (*LIGATURE_CONFUSION_PAIRS, ("N", "RI"))
    variants: dict[str, str] = {}
    for source, target in pairs:
        start = 0
        while len(variants) < EVIDENCE_VARIANT_LIMIT:
            position = compact.find(source, start)
            if position < 0:
                break
            variant = compact[:position] + target + compact[position + len(source) :]
            if variant and variant != compact:
                reason = (
                    "ligature_variant_retrieval"
                    if len(source) >= 2
                    else "ligature_expansion_retrieval"
                )
                variants.setdefault(variant, reason)
            start = position + 1
    return list(variants.items())


def mixed_ligature_transposition_variants(compact: str) -> list[tuple[str, str]]:
    """Undo one adjacent transposition and one documented OCR ligature."""

    if not (4 <= len(compact) <= 16):
        return []
    variants: dict[str, str] = {}
    for position in range(len(compact) - 1):
        if compact[position] == compact[position + 1]:
            continue
        swapped = (
            compact[:position]
            + compact[position + 1]
            + compact[position]
            + compact[position + 2 :]
        )
        for source, target in LIGATURE_CONFUSION_PAIRS:
            start = 0
            while len(variants) < MIXED_VARIANT_LIMIT:
                match = swapped.find(source, start)
                if match < 0:
                    break
                variant = (
                    swapped[:match]
                    + target
                    + swapped[match + len(source) :]
                )
                if variant and variant != compact:
                    variants.setdefault(
                        variant,
                        "mixed_ligature_transposition_retrieval",
                    )
                start = match + 1
            if len(variants) >= MIXED_VARIANT_LIMIT:
                break
        if len(variants) >= MIXED_VARIANT_LIMIT:
            break
    return list(variants.items())


def adjacent_transposition_variants(compact: str) -> list[tuple[str, str]]:
    """Return every query formed by undoing one adjacent transposition."""

    if not (4 <= len(compact) <= 16):
        return []
    variants: dict[str, str] = {}
    for position in range(len(compact) - 1):
        if compact[position] == compact[position + 1]:
            continue
        variant = (
            compact[:position]
            + compact[position + 1]
            + compact[position]
            + compact[position + 2 :]
        )
        variants.setdefault(variant, "transposition_deletion_frame_retrieval")
    return list(variants.items())


def keyboard_neighbor_variants(compact: str) -> list[tuple[str, str]]:
    """Return queries formed by reversing one adjacent-key substitution."""

    if not (4 <= len(compact) <= 16):
        return []
    variants: dict[str, str] = {}
    for position, character in enumerate(compact):
        for replacement in sorted(
            current_eval.KEY_NEIGHBORS.get(character, set()) - {character}
        ):
            variant = compact[:position] + replacement + compact[position + 1 :]
            variants.setdefault(variant, "keyboard_deletion_frame_retrieval")
    return list(variants.items())


def group_replacements(groups: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """Return deterministic alternatives for each character in a group."""

    replacements: dict[str, set[str]] = defaultdict(set)
    for group in groups:
        for character in group:
            replacements[character].update(set(group) - {character})
    return {
        character: tuple(sorted(alternatives))
        for character, alternatives in replacements.items()
    }


VISUAL_CHAIN_REPLACEMENTS = group_replacements(VISUAL_CHAIN_GROUPS)
PHONETIC_CHAIN_REPLACEMENTS = group_replacements(PHONETIC_CHAIN_GROUPS)


def character_chain_options(source: str) -> tuple[tuple[int, int, str], ...]:
    """Enumerate one character after at most two visual and one sound edit."""

    reached: dict[tuple[int, int], set[str]] = defaultdict(set)
    reached[(0, 0)].add(source)
    frontier = {(source, 0, 0)}
    for _ in range(3):
        next_frontier: set[tuple[str, int, int]] = set()
        for character, visual_count, phonetic_count in frontier:
            if visual_count < 2:
                next_frontier.update(
                    (replacement, visual_count + 1, phonetic_count)
                    for replacement in VISUAL_CHAIN_REPLACEMENTS.get(character, ())
                )
            if phonetic_count < 1:
                next_frontier.update(
                    (replacement, visual_count, phonetic_count + 1)
                    for replacement in PHONETIC_CHAIN_REPLACEMENTS.get(character, ())
                )
        for character, visual_count, phonetic_count in next_frontier:
            reached[(visual_count, phonetic_count)].add(character)
        frontier = next_frontier
    return tuple(
        (visual_count, phonetic_count, replacement)
        for (visual_count, phonetic_count), alternatives in sorted(reached.items())
        for replacement in sorted(alternatives)
    )


VISUAL_PHONETIC_CHARACTER_OPTIONS = {
    character: character_chain_options(character)
    for character in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
}


def visual_phonetic_chain_family_ids(
    index: RescueIndex,
    compact: str,
) -> set[int]:
    """Find exact same-length families explained by two visual and one sound edit."""

    if not (4 <= len(compact) <= 10):
        return set()
    states = {("", 0, 0, 0)}
    for position, source in enumerate(compact):
        next_states: set[tuple[str, int, int, int]] = set()
        for prefix, visual_count, phonetic_count, changed_count in states:
            for visual_delta, phonetic_delta, replacement in (
                VISUAL_PHONETIC_CHARACTER_OPTIONS.get(source, ((0, 0, source),))
            ):
                new_visual = visual_count + visual_delta
                new_phonetic = phonetic_count + phonetic_delta
                if new_visual > 2 or new_phonetic > 1:
                    continue
                new_prefix = prefix + replacement
                prefix_length = position + 1
                if prefix_length >= 2 and new_prefix not in index.prefix:
                    continue
                next_states.add(
                    (
                        new_prefix,
                        new_visual,
                        new_phonetic,
                        changed_count + int(replacement != source),
                    )
                )
        states = next_states
        if not states:
            return set()
    family_ids: set[int] = set()
    for variant, visual_count, phonetic_count, changed_count in states:
        if visual_count != 2 or phonetic_count != 1 or changed_count < 2:
            continue
        family_ids.update(index.exact.get(variant, ()))
    return family_ids


def two_visual_chain_frames(compact: str) -> set[str]:
    """Return strings produced by exactly two documented visual substitutions."""

    frontier = {compact}
    for _ in range(2):
        next_frontier: set[str] = set()
        for value in frontier:
            for position, character in enumerate(value):
                for replacement in VISUAL_CHAIN_REPLACEMENTS.get(character, ()):
                    next_frontier.add(
                        value[:position] + replacement + value[position + 1 :]
                    )
        frontier = next_frontier
    frontier.discard(compact)
    return frontier


def visual_visual_deletion_family_ids(
    index: RescueIndex,
    compact: str,
) -> set[int]:
    """Find one-character-longer families after two visual substitutions."""

    if not (4 <= len(compact) <= 10):
        return set()
    family_ids: set[int] = set()
    for frame in two_visual_chain_frames(compact):
        for family_id in index.delete_index.get(frame, ()):
            family = index.families[family_id]
            if len(family.compact) != len(frame) + 1:
                continue
            if any(
                family.compact[:deleted] + family.compact[deleted + 1 :] == frame
                for deleted in range(len(family.compact))
            ):
                family_ids.add(family_id)
    return family_ids


def transposition_deletion_exact_family_ids(
    index: RescueIndex,
    compact: str,
) -> set[int]:
    """Find one-character-longer families after one adjacent transposition."""

    if not (4 <= len(compact) <= 16):
        return set()
    family_ids: set[int] = set()
    for frame, _ in adjacent_transposition_variants(compact):
        for family_id in index.delete_index.get(frame, ()):
            family = index.families[family_id]
            if len(family.compact) != len(frame) + 1:
                continue
            if any(
                family.compact[:deleted] + family.compact[deleted + 1 :] == frame
                for deleted in range(len(family.compact))
            ):
                family_ids.add(family_id)
    return family_ids


def ligature_vowel_chain_family_ids(
    index: RescueIndex,
    compact: str,
) -> set[int]:
    """Find exact families after reversing one vowel and one OCR ligature."""

    if not (4 <= len(compact) <= 16):
        return set()
    family_ids: set[int] = set()
    for position, character in enumerate(compact):
        if character not in VOWELS:
            continue
        for replacement in sorted(VOWELS - {character}):
            vowel_variant = (
                compact[:position] + replacement + compact[position + 1 :]
            )
            for source, target in GENERATOR_LIGATURE_PAIRS:
                start = 0
                while True:
                    match = vowel_variant.find(source, start)
                    if match < 0:
                        break
                    variant = (
                        vowel_variant[:match]
                        + target
                        + vowel_variant[match + len(source) :]
                    )
                    family_ids.update(index.exact.get(variant, ()))
                    start = match + 1
    return family_ids


def ligature_vowel_transposition_family_ids(
    index: RescueIndex,
    compact: str,
) -> set[int]:
    """Find exact families after reversing transposition, vowel, and ligature."""

    if not (4 <= len(compact) <= 16):
        return set()
    family_ids: set[int] = set()
    for transposed, _ in adjacent_transposition_variants(compact):
        for position, character in enumerate(transposed):
            if character not in VOWELS:
                continue
            for replacement in sorted(VOWELS - {character}):
                vowel_variant = (
                    transposed[:position]
                    + replacement
                    + transposed[position + 1 :]
                )
                for source, target in GENERATOR_LIGATURE_PAIRS:
                    start = 0
                    while True:
                        match = vowel_variant.find(source, start)
                        if match < 0:
                            break
                        variant = (
                            vowel_variant[:match]
                            + target
                            + vowel_variant[match + len(source) :]
                        )
                        family_ids.update(index.exact.get(variant, ()))
                        start = match + 1
    return family_ids


def transpose_vowel_deletion_family_ids(
    index: RescueIndex,
    compact: str,
) -> set[int]:
    """Find families after reversing transposition, vowel change, and deletion."""

    if not (4 <= len(compact) <= 16):
        return set()
    family_ids: set[int] = set()
    for transposed, _ in adjacent_transposition_variants(compact):
        for position, character in enumerate(transposed):
            if character not in VOWELS:
                continue
            for replacement in sorted(VOWELS - {character}):
                frame = (
                    transposed[:position]
                    + replacement
                    + transposed[position + 1 :]
                )
                for family_id in index.delete_index.get(frame, ()):
                    family = index.families[family_id]
                    if len(family.compact) != len(frame) + 1:
                        continue
                    if any(
                        family.compact[:deleted]
                        + family.compact[deleted + 1 :]
                        == frame
                        for deleted in range(len(family.compact))
                    ):
                        family_ids.add(family_id)
    return family_ids


def vowel_phonetic_deletion_family_ids(
    index: RescueIndex,
    compact: str,
) -> set[int]:
    """Find short families after reversing deletion, sound, and vowel edits."""

    if not (3 <= len(compact) <= 4):
        return set()
    family_ids: set[int] = set()
    for inserted_at in range(len(compact) + 1):
        for inserted in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            deletion_frame = (
                compact[:inserted_at] + inserted + compact[inserted_at:]
            )
            for phonetic_at, character in enumerate(deletion_frame):
                for phonetic in PHONETIC_CHAIN_REPLACEMENTS.get(character, ()):
                    phonetic_frame = (
                        deletion_frame[:phonetic_at]
                        + phonetic
                        + deletion_frame[phonetic_at + 1 :]
                    )
                    for vowel_at, vowel in enumerate(phonetic_frame):
                        if vowel not in VOWELS:
                            continue
                        for replacement in sorted(VOWELS - {vowel}):
                            variant = (
                                phonetic_frame[:vowel_at]
                                + replacement
                                + phonetic_frame[vowel_at + 1 :]
                            )
                            family_ids.update(index.exact.get(variant, ()))
    return family_ids


def keyboard_vowel_deletion_family_ids(
    index: RescueIndex,
    compact: str,
) -> set[int]:
    """Find one-character-longer families after vowel and keyboard reversal."""

    if not (4 <= len(compact) <= 8):
        return set()
    family_ids: set[int] = set()
    for vowel_at, vowel in enumerate(compact):
        if vowel not in VOWELS:
            continue
        for vowel_replacement in sorted(VOWELS - {vowel}):
            vowel_frame = (
                compact[:vowel_at]
                + vowel_replacement
                + compact[vowel_at + 1 :]
            )
            for keyboard_at, character in enumerate(vowel_frame):
                for keyboard_replacement in sorted(
                    current_eval.KEY_NEIGHBORS.get(character, set()) - {character}
                ):
                    deletion_frame = (
                        vowel_frame[:keyboard_at]
                        + keyboard_replacement
                        + vowel_frame[keyboard_at + 1 :]
                    )
                    for family_id in index.delete_index.get(deletion_frame, ()):
                        family = index.families[family_id]
                        if len(family.compact) != len(deletion_frame) + 1:
                            continue
                        if any(
                            family.compact[:deleted]
                            + family.compact[deleted + 1 :]
                            == deletion_frame
                            for deleted in range(len(family.compact))
                        ):
                            family_ids.add(family_id)
    return family_ids


def short_ocr_combined_family_ids(
    index: RescueIndex,
    compact: str,
) -> set[int]:
    """Return short exact families after OCR plus vowel or phonetic reversal."""

    if not (3 <= len(compact) <= 4):
        return set()
    family_ids: set[int] = set()
    for digit_at, digit in enumerate(compact):
        for letter in sorted(OCR_DIGIT_TO_LETTERS.get(digit, ())):
            ocr_frame = compact[:digit_at] + letter + compact[digit_at + 1 :]
            for vowel_at, vowel in enumerate(ocr_frame):
                if vowel not in VOWELS:
                    continue
                for replacement in sorted(VOWELS - {vowel}):
                    variant = (
                        ocr_frame[:vowel_at]
                        + replacement
                        + ocr_frame[vowel_at + 1 :]
                    )
                    family_ids.update(index.exact.get(variant, ()))
            for phonetic_at, character in enumerate(ocr_frame):
                for replacement in PHONETIC_CHAIN_REPLACEMENTS.get(character, ()):
                    variant = (
                        ocr_frame[:phonetic_at]
                        + replacement
                        + ocr_frame[phonetic_at + 1 :]
                    )
                    family_ids.update(index.exact.get(variant, ()))
    return family_ids


def best_exact_chain_score(
    index: RescueIndex,
    family: FamilyRecord,
    eligible: bool,
    *,
    reason: str,
    score_discount: float,
) -> dict[str, Any] | None:
    """Score a catalog-exact transformed query with an operation penalty."""

    if not eligible:
        return None
    item = score_family(
        index,
        family,
        family.compact,
        family.norm,
        family.skeleton,
        family.phonetic,
    )
    if item is None:
        return None
    item["score"] = round(
        max(
            0.01,
            float(item["score"]) - score_discount,
        ),
        6,
    )
    item["reasons"] = sorted(
        {
            *item.get("reasons", ()),
            reason,
            "multi_step_variant_score",
        }
        - {"exact_family"}
    )
    return item


def best_mixed_variant_score(
    index: RescueIndex,
    family: FamilyRecord,
    original_compact: str,
    variants: Iterable[tuple[str, str]],
) -> dict[str, Any] | None:
    """Score a family only when two OCR inversions improve its distance."""

    original_distance = damerau(original_compact, family.compact, weighted=False)
    best: dict[str, Any] | None = None
    for variant, reason in variants:
        variant_distance = damerau(variant, family.compact, weighted=False)
        if variant_distance > 2 or original_distance - variant_distance < 2:
            continue
        item = score_family(
            index,
            family,
            variant,
            current_eval.normalize_search(variant),
            current_eval.skeleton(variant),
            current_eval.drug_phonetic_key(variant),
        )
        if item is None:
            continue
        item["score"] = round(
            max(0.01, float(item["score"]) - MIXED_VARIANT_SCORE_DISCOUNT),
            6,
        )
        item["reasons"] = sorted(
            {
                *item.get("reasons", ()),
                reason,
                "multi_step_variant_score",
            }
            - {"exact_family"}
        )
        if best is None or float(item["score"]) > float(best["score"]):
            best = item
    return best


def best_deletion_frame_variant_score(
    index: RescueIndex,
    family: FamilyRecord,
    original_compact: str,
    variants: Iterable[tuple[str, str]],
    *,
    score_discount: float,
) -> dict[str, Any] | None:
    """Score one corrected variant that still has one missing frame character."""

    original_distance = damerau(original_compact, family.compact, weighted=False)
    best: dict[str, Any] | None = None
    for variant, reason in variants:
        variant_distance = damerau(variant, family.compact, weighted=False)
        if variant_distance > 2 or original_distance - variant_distance < 1:
            continue
        item = score_family(
            index,
            family,
            variant,
            current_eval.normalize_search(variant),
            current_eval.skeleton(variant),
            current_eval.drug_phonetic_key(variant),
        )
        if item is None:
            continue
        item["score"] = round(
            max(0.01, float(item["score"]) - score_discount),
            6,
        )
        item["reasons"] = sorted(
            {
                *item.get("reasons", ()),
                reason,
                "multi_step_variant_score",
            }
            - {"exact_family"}
        )
        if best is None or float(item["score"]) > float(best["score"]):
            best = item
    return best


def clean_context_query(raw_query: str) -> str:
    """Remove strength/form/unit noise while keeping likely brand tokens."""

    norm = current_eval.normalize_search(raw_query)
    tokens = [token for token in re.split(r"\s+", norm) if token]
    if len(tokens) < 2:
        return ""
    has_context = any(is_context_noise_token(token) for token in tokens)
    if not has_context:
        return ""

    cleaned = []
    for index, token in enumerate(tokens):
        if token in CONTEXT_NOISE_TOKENS or UNIT_SUFFIX_RE.match(token):
            continue
        if is_split_film_coated_token(tokens, index):
            continue
        if PURE_NUMBER_RE.match(token):
            previous_token = tokens[index - 1] if index else ""
            next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
            # Preserve leading numeric brand tokens such as "5 FLUOROURACIL".
            if index > 0 and (
                next_token in CONTEXT_NOISE_TOKENS
                or previous_token in CONTEXT_NOISE_TOKENS
                or UNIT_SUFFIX_RE.match(next_token or "")
            ):
                continue
        cleaned.append(token)

    if len(cleaned) == len(tokens) or not cleaned:
        return ""
    return " ".join(cleaned)


def is_context_noise_token(token: str) -> bool:
    return token in CONTEXT_NOISE_TOKENS or bool(UNIT_SUFFIX_RE.match(token))


def is_split_film_coated_token(tokens: list[str], index: int) -> bool:
    """Treat "F C" as film-coated only when another context marker exists."""

    token = tokens[index]
    if token not in {"F", "C"}:
        return False
    previous_token = tokens[index - 1] if index else ""
    next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
    if not ((token == "F" and next_token == "C") or (token == "C" and previous_token == "F")):
        return False
    return any(
        other not in {"F", "C"} and is_context_noise_token(other)
        for other in tokens
    )


def should_run_context_search(original_compact: str, cleaned_query: str) -> bool:
    """Run the extra context-clean search only when cleaning materially changes the query."""

    cleaned_compact = current_eval.compact_key(cleaned_query)
    if not cleaned_compact or cleaned_compact == original_compact:
        return False
    if len(cleaned_compact) < 3:
        return False
    # Avoid turning very short ambiguous prefixes into stronger-looking hits.
    if len(cleaned_compact) <= 4 and len(original_compact) <= 8:
        return False
    return True


def prefilter_family_ids(
    index: RescueIndex,
    ids: set[int],
    compact: str,
    query_skeleton: str,
    query_phonetic: str,
    *,
    limit: int = RESCUE_PREFILTER_LIMIT,
    allow_head: bool = False,
    use_edit: bool = True,
) -> set[int]:
    """Keep rescue scoring bounded with cheap non-edit-distance evidence."""

    if len(ids) <= limit:
        return ids

    query_grams2 = char_ngrams(compact, 2)
    query_grams3 = char_ngrams(compact, 3)
    query_grams4 = char_ngrams(compact, 4)
    scored: list[tuple[float, int]] = []

    for family_id in ids:
        family = index.families[family_id]
        cheap = cheap_family_prefilter_score(
            family,
            compact,
            query_skeleton,
            query_phonetic,
            query_grams2,
            query_grams3,
            query_grams4,
            allow_head=allow_head,
            use_edit=use_edit,
        )
        if cheap > 0.0:
            scored.append((cheap, family_id))

    scored.sort(key=lambda row: (-row[0], index.families[row[1]].name))
    return {family_id for _, family_id in scored[:limit]}


def cheap_family_prefilter_score(
    family: FamilyRecord,
    compact: str,
    query_skeleton: str,
    query_phonetic: str,
    query_grams2: set[str],
    query_grams3: set[str],
    query_grams4: set[str],
    *,
    allow_head: bool = False,
    use_edit: bool = True,
) -> float:
    """Score broad rescue buckets before expensive edit-distance scoring."""

    if compact == family.compact:
        return 9.0
    length_delta = abs(len(compact) - len(family.compact))
    head_distance = (
        damerau(compact, family.head_compact, weighted=False)
        if allow_head and family.head_compact
        else 999.0
    )
    head_plausible = bool(
        allow_head
        and family.head_compact
        and (
            head_distance <= VALIDATED_HEAD_MAX_DISTANCE
            or supports_short_visible_head(compact, family.head_compact)
        )
        and (
            compact[:1] == family.head_compact[:1]
            or first_chars_confusable(compact[:1], family.head_compact[:1])
        )
    )
    if length_delta > 5 and not family.compact.startswith(compact[:4]) and not head_plausible:
        return 0.0

    prefix = prefix_score(compact, family.compact)
    suffix = suffix_score(compact, family.compact)
    grams2 = jaccard(query_grams2, family.grams2)
    grams3 = jaccard(query_grams3, family.grams3)
    grams4 = jaccard(query_grams4, family.grams4)
    skeleton = key_similarity(query_skeleton, family.skeleton)
    phonetic = key_similarity(query_phonetic, family.phonetic)
    subseq = subsequence_score(compact, family.compact)
    positional = same_position_score(compact, family.compact)
    coverage = length_coverage(compact, family.compact)
    edit = 0.0
    if use_edit and length_delta <= 3 and len(compact) <= 16 and len(family.compact) <= 18:
        edit = normalized_edit_similarity(
            compact,
            family.compact,
            weighted=True,
        )

    score = (
        1.35 * prefix
        + 0.65 * suffix
        + 0.55 * grams2
        + 1.20 * grams3
        + 1.00 * grams4
        + 0.70 * skeleton
        + 0.65 * phonetic
        + 0.35 * subseq
        + 0.90 * edit
        + 0.45 * positional
        + 0.25 * coverage
    )
    if compact[:1] and family.compact[:1] and compact[0] == family.compact[0]:
        score += 0.20
    elif first_chars_confusable(compact[:1], family.compact[:1]):
        score += 0.10
    if length_delta <= 1:
        score += 0.18
    elif length_delta <= 3:
        score += 0.08
    if is_partial_prefix_match(compact, family.compact) and edit < 0.82:
        score -= 0.35

    # Real typo failures often keep one strong edge and corrupt the middle.
    # Preserve those candidates even if their complete edit score is not known yet.
    if max(prefix, suffix) >= 0.34 and max(grams3, skeleton, phonetic, subseq) >= 0.30:
        score += 0.25
    if (
        head_plausible
    ):
        head_edit = normalized_edit_similarity(compact, family.head_compact, weighted=True)
        head_prefix = prefix_score(compact, family.head_compact)
        head_suffix = suffix_score(compact, family.head_compact)
        head_positional = same_position_score(compact, family.head_compact)
        head_score = (
            1.80 * head_edit
            + 0.55 * max(head_prefix, head_suffix)
            + 0.40 * head_positional
            + 0.25 * length_coverage(compact, family.head_compact)
        )
        if head_distance <= VALIDATED_HEAD_MAX_DISTANCE:
            head_score += 0.45
        elif supports_short_visible_head(compact, family.head_compact):
            head_score += 0.30
        score = max(score, head_score)
    return score


def length_scan_ids(index: RescueIndex, compact: str, *, radius: int = 3) -> set[int]:
    """Return families with compatible length and plausible first character."""

    out: set[int] = set()
    candidates = set()
    for length in range(max(1, len(compact) - radius), len(compact) + radius + 1):
        candidates.update(index.length.get(length, ()))
    first_candidates = set()
    for variant in {compact, *first_char_variants(compact)}:
        first = variant[:1]
        if first:
            first_candidates.update(index.first_char.get(first, set()))
    if first_candidates:
        candidates &= first_candidates
    if len(candidates) > 2200:
        return set(sorted(candidates)[:2200])
    return candidates


def score_family(
    index: RescueIndex,
    family: FamilyRecord,
    compact: str,
    norm: str,
    query_skeleton: str,
    query_phonetic: str,
    *,
    allow_head: bool = False,
    ocr_visual: bool = False,
) -> dict[str, Any] | None:
    """Score one rescue family."""

    reasons: set[str] = set()
    if family.warnings:
        reasons.add("catalog_warning")

    exact = 1.0 if compact == family.compact or norm == family.norm else 0.0
    if exact:
        reasons.add("exact_family")
    edit = normalized_edit_similarity(compact, family.compact, weighted=False)
    weighted = normalized_edit_similarity(
        compact,
        family.compact,
        weighted=True,
        ocr_visual=ocr_visual,
    )
    prefix = prefix_score(compact, family.compact)
    suffix = suffix_score(compact, family.compact)
    grams2 = jaccard(char_ngrams(compact, 2), family.grams2)
    grams = jaccard(char_ngrams(compact, 3), family.grams3)
    skeleton_score = key_similarity(query_skeleton, family.skeleton)
    phonetic_score = key_similarity(query_phonetic, family.phonetic)
    subseq = subsequence_score(compact, family.compact)
    positional = same_position_score(compact, family.compact)
    coverage = length_coverage(compact, family.compact)
    length_delta = abs(len(compact) - len(family.compact))

    score = (
        1.25 * exact
        + 0.58 * edit
        + 0.52 * weighted
        + 0.16 * prefix
        + 0.10 * suffix
        + 0.10 * grams2
        + 0.18 * grams
        + 0.16 * skeleton_score
        + 0.14 * phonetic_score
        + 0.10 * subseq
        + 0.24 * positional
        + 0.16 * coverage
    )
    if compact[:1] and family.compact[:1] and compact[0] == family.compact[0]:
        score += 0.12
    elif first_chars_confusable(compact[:1], family.compact[:1]):
        score += 0.06
    if abs(len(compact) - len(family.compact)) <= 1 and weighted >= 0.76:
        score += 0.18
    if prefix >= 0.55 and weighted >= 0.66:
        score += 0.08
    if weighted >= 0.84 and positional >= 0.70:
        score += 0.22
    if is_partial_prefix_match(compact, family.compact) and weighted < 0.84:
        score -= 0.18 + min(0.24, 0.05 * length_delta)

    if not exact:
        if len(compact) <= 4 and edit < 0.76:
            score -= 0.22
        if max(edit, weighted) < 0.58 and max(skeleton_score, phonetic_score) < 0.72:
            score -= 0.20
        if prefix < 0.30 and grams < 0.12 and max(edit, weighted) < 0.70:
            score -= 0.10

    head_raw_distance = (
        damerau(compact, family.head_compact, weighted=False)
        if allow_head and family.head_compact
        else 999.0
    )
    head_supported = bool(
        allow_head
        and family.head_compact
        and (
            head_raw_distance <= VALIDATED_HEAD_MAX_DISTANCE
            or supports_short_visible_head(compact, family.head_compact)
        )
    )
    if head_supported:
        head_edit = normalized_edit_similarity(compact, family.head_compact, weighted=False)
        head_weighted = normalized_edit_similarity(compact, family.head_compact, weighted=True)
        head_prefix = prefix_score(compact, family.head_compact)
        head_suffix = suffix_score(compact, family.head_compact)
        head_grams = jaccard(char_ngrams(compact, 3), char_ngrams(family.head_compact, 3))
        head_skeleton = key_similarity(query_skeleton, family.head_skeleton)
        head_phonetic = key_similarity(query_phonetic, family.head_phonetic)
        head_subseq = subsequence_score(compact, family.head_compact)
        head_positional = same_position_score(compact, family.head_compact)
        head_coverage = length_coverage(compact, family.head_compact)
        head_exact = 1.0 if compact == family.head_compact else 0.0
        head_score = (
            0.70 * head_exact
            + 0.58 * head_edit
            + 0.52 * head_weighted
            + 0.16 * head_prefix
            + 0.10 * head_suffix
            + 0.18 * head_grams
            + 0.16 * head_skeleton
            + 0.14 * head_phonetic
            + 0.10 * head_subseq
            + 0.24 * head_positional
            + 0.16 * head_coverage
        )
        if compact[:1] == family.head_compact[:1]:
            head_score += 0.12
        if head_raw_distance <= VALIDATED_HEAD_MAX_DISTANCE:
            head_score += 0.30
            reasons.add("variant_head_edit")
        else:
            head_score += 0.20
            reasons.add("visible_head_prefix")
        score = max(score, head_score)

    positional_ocr_rescue = (
        compact[:1] == family.compact[:1]
        and positional >= 0.40
        and coverage >= 0.70
        and score >= 0.58
    )
    if score < 0.62 and not exact and not positional_ocr_rescue:
        return None
    if positional_ocr_rescue:
        reasons.add("positional_ocr_rescue")
    if edit >= 0.76:
        reasons.add("family_edit")
    if weighted >= 0.76:
        reasons.add("weighted_confusion_edit")
    if prefix >= 0.35:
        reasons.add("prefix_family")
    if skeleton_score >= 0.80:
        reasons.add("skeleton_family")
    if phonetic_score >= 0.78:
        reasons.add("phonetic_family")
    return {
        "name": family.name,
        "commercial_name": family.examples[0] if family.examples else family.name,
        "commercial_examples": family.examples[:5],
        "score": round(score, 6),
        "reasons": sorted(reasons or {"family_rescue"}),
        "candidate_canonical_name": family.name,
        "source": "rescue",
    }


def merge_candidates(
    external_results: list[dict[str, Any]],
    context_results: list[dict[str, Any]],
    rescue_results: list[dict[str, Any]],
    external_status: str,
) -> dict[str, Candidate]:
    """Merge Algorithm 2 results and rescue results by compact family key."""

    candidates: dict[str, Candidate] = {}
    for rank, item in enumerate(external_results, 1):
        name = str(item.get("name") or item.get("candidate_canonical_name") or item.get("commercial_name") or "").strip()
        if not name:
            continue
        key = current_eval.compact_key(name)
        candidate = candidates.setdefault(key, Candidate(
            key=key,
            name=name,
            commercial_name=str(item.get("commercial_name") or name),
        ))
        candidate.external_rank = rank if candidate.external_rank is None else min(candidate.external_rank, rank)
        candidate.external_score = max(candidate.external_score, float(item.get("score") or 0.0))
        candidate.examples.extend(value for value in item.get("commercial_examples", []) or [] if value not in candidate.examples)
        candidate.examples.append(candidate.commercial_name)
        candidate.reasons.update(str(value) for value in item.get("reasons", []) or [])
        candidate.reasons.add(f"algorithm_2_rank_{rank}")
        candidate.score = max(candidate.score, external_contribution(candidate.external_score, rank, external_status))

    for rank, item in enumerate(context_results, 1):
        name = str(item.get("name") or item.get("candidate_canonical_name") or item.get("commercial_name") or "").strip()
        if not name:
            continue
        key = current_eval.compact_key(name)
        candidate = candidates.setdefault(key, Candidate(
            key=key,
            name=name,
            commercial_name=str(item.get("commercial_name") or name),
        ))
        candidate.external_score = max(candidate.external_score, float(item.get("score") or 0.0))
        candidate.examples.extend(value for value in item.get("commercial_examples", []) or [] if value not in candidate.examples)
        candidate.examples.append(str(item.get("commercial_name") or name))
        candidate.reasons.update(str(value) for value in item.get("reasons", []) or [])
        candidate.reasons.add(f"context_clean_rank_{rank}")
        candidate.score = max(candidate.score, context_contribution(float(item.get("score") or 0.0), rank))
        if candidate.external_rank is not None:
            candidate.score += 0.06
            candidate.reasons.add("algorithm_2_context_agreement")

    for rank, item in enumerate(rescue_results, 1):
        name = str(item.get("name") or item.get("candidate_canonical_name") or item.get("commercial_name") or "").strip()
        if not name:
            continue
        key = current_eval.compact_key(name)
        already_present = key in candidates
        evidence_only_item = bool(item.get("_evidence_only"))
        item_reasons = {str(value) for value in item.get("reasons", []) or []}
        merge_rank = int(item.get("_merge_rank") or rank)
        if (
            evidence_only_item
            and already_present
            and (
                "multi_step_variant_score" in item_reasons
                or bool(item_reasons & EXACT_CHAIN_EVIDENCE_REASONS)
            )
        ):
            candidate = candidates[key]
            exact_chain_evidence = bool(item_reasons & EXACT_CHAIN_EVIDENCE_REASONS)
            if exact_chain_evidence and ENABLE_EXACT_CHAIN_EXISTING_AUGMENTATION:
                candidate.pre_multi_step_score = candidate.score
                candidate.score = max(
                    candidate.score,
                    rescue_contribution(float(item.get("score") or 0.0), merge_rank),
                )
                candidate.multi_step_augmented_existing = True
                candidate.reasons.update(item_reasons)
                candidate.reasons.add("exact_chain_augmented_existing_candidate")
            else:
                candidate.reasons.add("ignored_multi_step_duplicate_evidence")
            continue
        candidate = candidates.setdefault(key, Candidate(
            key=key,
            name=name,
            commercial_name=str(item.get("commercial_name") or name),
        ))
        candidate.rescue_rank = merge_rank if candidate.rescue_rank is None else min(candidate.rescue_rank, merge_rank)
        candidate.rescue_score = max(candidate.rescue_score, float(item.get("score") or 0.0))
        candidate.name = name
        candidate.commercial_name = str(item.get("commercial_name") or candidate.commercial_name or name)
        candidate.examples.extend(value for value in item.get("commercial_examples", []) or [] if value not in candidate.examples)
        candidate.reasons.update(item_reasons)
        candidate.reasons.add(f"rescue_rank_{merge_rank}")
        rescue_score = rescue_contribution(candidate.rescue_score, merge_rank)
        if item_reasons & {
            "variant_head_edit",
            "short_visible_head_retrieval",
        }:
            # A shared catalog family head is useful evidence for adding a
            # missing variant, but it must not erase stronger full-name
            # evidence. rank_candidates may promote it later when the current
            # top result is not itself a close spelling match.
            rescue_score = candidate.score if candidate.score > 0.0 else 0.01
        if evidence_only_item and already_present:
            if "ligature_expansion_retrieval" not in item_reasons:
                candidate.evidence_supported_existing = True
            candidate.reasons.add("evidence_augmented_existing_candidate")
            continue
        candidate.score = max(candidate.score, rescue_score)
        if evidence_only_item:
            candidate.evidence_only_retrieval = True
            candidate.structural_only_retrieval = (
                "structural_variant_score" in item_reasons
            )
            candidate.multi_step_only_retrieval = (
                "multi_step_variant_score" in item_reasons
            )
            candidate.reasons.add("evidence_only_retrieval")
        if candidate.external_rank is not None:
            candidate.score += 0.08
            candidate.reasons.add("algorithm_2_rescue_agreement")

    for candidate in candidates.values():
        candidate.examples = dedupe([candidate.commercial_name, *candidate.examples])[:5]
    return candidates


def enrich_candidates(index: RescueIndex, candidates: dict[str, Candidate], compact: str) -> None:
    """Attach symmetric spelling evidence and catalog variant metadata."""

    has_single_ocr_digit = sum(char.isdigit() for char in compact) == 1
    for candidate in candidates.values():
        candidate.raw_edit_distance = damerau(compact, candidate.key, weighted=False)
        candidate.weighted_edit_distance = damerau(compact, candidate.key, weighted=True)
        candidate.ocr_visual_edit_distance = candidate.weighted_edit_distance
        if has_single_ocr_digit:
            candidate.ocr_visual_edit_distance = damerau(
                compact,
                candidate.key,
                weighted=True,
                ocr_visual=True,
            )
            candidate.ocr_visual_gain = max(
                0.0,
                candidate.weighted_edit_distance - candidate.ocr_visual_edit_distance,
            )
        candidate.positional_evidence = same_position_score(compact, candidate.key)
        candidate.edge_evidence = max(prefix_score(compact, candidate.key), suffix_score(compact, candidate.key))

        family_id = index.family_by_key.get(candidate.key)
        if family_id is None:
            candidate.variant_group = candidate.name
            continue
        family = index.families[family_id]
        candidate.variant_group = family.variant_group or family.name
        candidate.ingredients = sorted(family.ingredients)
        if family.head_compact:
            candidate.is_variant_family = True
            candidate.head_raw_edit_distance = damerau(compact, family.head_compact, weighted=False)
        variant_ids = index.variant_groups.get(family.variant_group or family.norm, [family_id])
        candidate.variants = [index.families[item].name for item in variant_ids]


def is_brand_like_query(query_text: str, compact: str) -> bool:
    """Return whether spelling evidence should dominate generic score bonuses."""

    if not (4 <= len(compact) <= 20):
        return False
    norm = current_eval.normalize_search(query_text)
    tokens = [token for token in re.split(r"\s+", norm) if token]
    if len(tokens) > 3:
        return False
    return not any(is_context_noise_token(token) for token in tokens)


def rank_candidates(
    candidates: list[Candidate],
    compact: str,
    *,
    brand_like: bool,
    _handle_multi_step_boost: bool = True,
) -> list[Candidate]:
    """Apply conservative, evidence-backed corrections to the model ranking.

    Edit distance is not a global ordering rule. It only overrides the model
    when both retrieval layers support a candidate that is strictly closer by
    one edit, for a pure insertion/deletion relation, or when a concatenated
    multi-token false positive narrowly beats a substantially closer family.
    Equal-distance candidates stay in model order; close alternatives still
    trigger ambiguity.
    """

    augmented_candidates = [
        candidate
        for candidate in candidates
        if candidate.multi_step_augmented_existing
    ]
    if _handle_multi_step_boost and augmented_candidates:
        boosted_scores = {
            id(candidate): candidate.score for candidate in augmented_candidates
        }
        for candidate in augmented_candidates:
            candidate.score = candidate.pre_multi_step_score
        baseline_ranked = rank_candidates(
            candidates,
            compact,
            brand_like=brand_like,
            _handle_multi_step_boost=False,
        )
        for candidate in augmented_candidates:
            candidate.score = boosted_scores[id(candidate)]
        ranked = rank_candidates(
            candidates,
            compact,
            brand_like=brand_like,
            _handle_multi_step_boost=False,
        )
        if baseline_ranked and ranked and ranked[0] is not baseline_ranked[0]:
            baseline_top = baseline_ranked[0]
            baseline_top.reasons.add("preserved_pre_multi_step_top")
            ranked = [
                baseline_top,
                *[candidate for candidate in ranked if candidate is not baseline_top],
            ]
        return ranked

    structural_candidates = [
        candidate for candidate in candidates if candidate.structural_only_retrieval
    ]
    if structural_candidates:
        legacy_ranked = rank_candidates(
            [
                candidate
                for candidate in candidates
                if not candidate.structural_only_retrieval
            ],
            compact,
            brand_like=brand_like,
            _handle_multi_step_boost=_handle_multi_step_boost,
        )
        structural_ranked = sorted(
            structural_candidates,
            key=lambda candidate: (-candidate.score, candidate.name),
        )
        exact_structural = [
            candidate
            for candidate in structural_ranked
            if is_exact_short_ligature_candidate(candidate, compact)
        ]
        if len(exact_structural) == 1:
            promoted = exact_structural[0]
            promoted.reasons.add("exact_short_ligature_correction")
            return [
                promoted,
                *legacy_ranked,
                *[
                    candidate
                    for candidate in structural_ranked
                    if candidate is not promoted
                ],
            ]
        return [*legacy_ranked, *structural_ranked]

    multi_step_candidates = [
        candidate for candidate in candidates if candidate.multi_step_only_retrieval
    ]
    if multi_step_candidates:
        legacy_ranked = rank_candidates(
            [
                candidate
                for candidate in candidates
                if not candidate.multi_step_only_retrieval
            ],
            compact,
            brand_like=brand_like,
            _handle_multi_step_boost=_handle_multi_step_boost,
        )
        ranked = promote_ocr_visual_tie(
            rank_candidate_core(candidates, compact, brand_like=brand_like),
            compact,
        )
        if legacy_ranked and ranked[0] is not legacy_ranked[0]:
            legacy_top = legacy_ranked[0]
            legacy_top.reasons.add("preserved_pre_multi_step_top")
            ranked = [
                legacy_top,
                *[candidate for candidate in ranked if candidate is not legacy_top],
            ]
        return ranked

    has_new_evidence = any(
        candidate.evidence_only_retrieval or candidate.evidence_supported_existing
        for candidate in candidates
    )
    if not has_new_evidence:
        return promote_ocr_visual_tie(
            rank_candidate_core(candidates, compact, brand_like=brand_like),
            compact,
        )

    baseline_candidates = [
        candidate for candidate in candidates if not candidate.evidence_only_retrieval
    ]
    baseline_ranked = promote_ocr_visual_tie(
        rank_candidate_core(baseline_candidates, compact, brand_like=brand_like),
        compact,
    )
    ranked = promote_ocr_visual_tie(
        rank_candidate_core(candidates, compact, brand_like=brand_like),
        compact,
    )
    if not baseline_ranked:
        return ranked
    return apply_evidence_retrieval_guard(
        ranked,
        compact,
        baseline_top=baseline_ranked[0],
    )


def is_exact_short_ligature_candidate(candidate: Candidate, compact: str) -> bool:
    """Return whether collapsing a visible multi-letter ligature is exact."""

    if len(compact) > 4 or "ligature_variant_retrieval" not in candidate.reasons:
        return False
    for source, target in LIGATURE_CONFUSION_PAIRS:
        if len(source) < 2:
            continue
        start = 0
        while True:
            position = compact.find(source, start)
            if position < 0:
                break
            variant = compact[:position] + target + compact[position + len(source) :]
            if variant == candidate.key:
                return True
            start = position + 1
    return False


def rank_candidate_core(
    candidates: list[Candidate],
    compact: str,
    *,
    brand_like: bool,
) -> list[Candidate]:
    """Apply the pre-existing score and bounded correction policy."""

    ranked = sorted(candidates, key=lambda item: (-item.score, clarification_sort(item), item.name))
    if not brand_like or len(ranked) < 2 or ranked[0].raw_edit_distance == 0:
        return ranked

    top = ranked[0]
    top_pure_deletion = is_pure_deletion_candidate(top, compact)
    top_distance = effective_spelling_distance(top)
    eligible: list[Candidate] = []
    for candidate in ranked[1:]:
        candidate_head_evidence = "variant_head_edit" in candidate.reasons
        candidate_distance = effective_spelling_distance(candidate)
        score_gap = top.score - candidate.score
        dual_retrieval_agreement = (
            candidate.external_rank is not None
            and candidate.rescue_rank is not None
        )
        strictly_closer_correction = (
            dual_retrieval_agreement
            and candidate.raw_edit_distance <= 2
            and top.raw_edit_distance - candidate.raw_edit_distance >= 1
            and score_gap <= 0.25
        )
        pure_deletion_correction = (
            not top_pure_deletion
            and is_pure_deletion_candidate(candidate, compact)
            and candidate.raw_edit_distance <= top.raw_edit_distance
            and score_gap <= 0.40
        )
        multi_token_false_positive = (
            len(top.name.split()) > 1
            and len(candidate.name.split()) == 1
            and candidate.raw_edit_distance < top.raw_edit_distance
            and candidate.raw_edit_distance <= 2
            and score_gap <= 0.20
        )
        variant_head_correction = (
            candidate.is_variant_family
            and candidate_head_evidence
            and len(compact) >= 5
            and candidate.head_raw_edit_distance <= 2
            and current_eval.compact_key(candidate.variant_group) != top.key
            and top_distance - candidate_distance >= 1
            and candidate_distance < top_distance
            and score_gap <= 1.40
        )
        if (
            strictly_closer_correction
            or pure_deletion_correction
            or multi_token_false_positive
            or variant_head_correction
        ):
            eligible.append(candidate)

    if eligible:
        best = min(
            eligible,
            key=lambda item: (
                min(item.raw_edit_distance, item.head_raw_edit_distance)
                if "variant_head_edit" in item.reasons
                else item.raw_edit_distance,
                item.weighted_edit_distance,
                -item.edge_evidence,
                -item.positional_evidence,
                -item.score,
                item.name,
            ),
        )
        ranked = [best, *[item for item in ranked if item is not best]]

    if ENABLE_STRICT_FULL_NAME_RERANK:
        return promote_strictly_closer_full_name(ranked, compact)
    return ranked


def apply_evidence_retrieval_guard(
    ranked: list[Candidate],
    compact: str,
    *,
    baseline_top: Candidate,
) -> list[Candidate]:
    """Keep retrieval expansion from changing top-1 without decisive evidence."""

    evidence_candidates = [
        candidate
        for candidate in ranked
        if candidate.evidence_only_retrieval or candidate.evidence_supported_existing
    ]
    if not evidence_candidates:
        return ranked

    eligible = [
        candidate
        for candidate in evidence_candidates
        if has_decisive_evidence_promotion(candidate, baseline_top, ranked, compact)
    ]
    if eligible:
        best = min(
            eligible,
            key=lambda candidate: (
                candidate.raw_edit_distance,
                candidate.weighted_edit_distance,
                -candidate.positional_evidence,
                -candidate.score,
                candidate.name,
            ),
        )
        best.reasons.add("decisive_evidence_retrieval_correction")
        return [best, *[candidate for candidate in ranked if candidate is not best]]
    if ranked[0] is not baseline_top:
        baseline_top.reasons.add("preserved_pre_fallback_top")
        return [baseline_top, *[candidate for candidate in ranked if candidate is not baseline_top]]
    return ranked


def has_decisive_evidence_promotion(
    candidate: Candidate,
    legacy_top: Candidate,
    ranked: list[Candidate],
    compact: str,
) -> bool:
    """Require a unique, bounded spelling advantage before changing top-1."""

    score_gap = legacy_top.score - candidate.score

    nearest_candidates = [
        item
        for item in ranked
        if "bounded_nearest_retrieval" in item.reasons
    ]
    if nearest_candidates:
        nearest_distance = min(item.raw_edit_distance for item in nearest_candidates)
        nearest_at_distance = [
            item for item in nearest_candidates if item.raw_edit_distance == nearest_distance
        ]
        if (
            score_gap <= EVIDENCE_PROMOTION_MAX_SCORE_GAP
            and len(nearest_at_distance) == 1
            and nearest_at_distance[0] is candidate
            and candidate.raw_edit_distance <= nearest_fallback_radius(compact)
            and legacy_top.raw_edit_distance - candidate.raw_edit_distance
            >= NEAREST_PROMOTION_MIN_DISTANCE_GAIN
        ):
            return True

    variants_by_reason: dict[str, list[str]] = defaultdict(list)
    for variant, reason in evidence_query_variants(compact):
        variants_by_reason[reason].append(variant)
    for reason in candidate.reasons:
        for variant in variants_by_reason.get(reason, ()):
            if reason == "ocr_visual_variant_retrieval" and not (
                candidate.ocr_visual_gain > legacy_top.ocr_visual_gain
                and candidate.ocr_visual_edit_distance
                < legacy_top.ocr_visual_edit_distance
            ):
                continue
            candidate_distance = damerau(variant, candidate.key, weighted=False)
            if (
                score_gap > STRUCTURAL_PROMOTION_MAX_SCORE_GAP
                or candidate_distance > 1
                or candidate.raw_edit_distance > nearest_fallback_radius(compact)
            ):
                continue
            distances = [
                (damerau(variant, item.key, weighted=False), item)
                for item in ranked
            ]
            best_distance = min(distance for distance, _ in distances)
            best_candidates = [item for distance, item in distances if distance == best_distance]
            legacy_distance = damerau(variant, legacy_top.key, weighted=False)
            if reason == "leading_transposition_retrieval":
                nearest_raw = min(item.raw_edit_distance for item in ranked)
                nearest_raw_candidates = [
                    item for item in ranked if item.raw_edit_distance == nearest_raw
                ]
                if (
                    len(nearest_raw_candidates) != 1
                    or nearest_raw_candidates[0] is not candidate
                ):
                    continue
            if (
                candidate_distance == best_distance
                and len(best_candidates) == 1
                and legacy_distance - candidate_distance >= 2
            ):
                return True
    return False


def promote_ocr_visual_tie(ranked: list[Candidate], compact: str) -> list[Candidate]:
    """Use directional digit-to-letter evidence inside a bounded raw-distance tie."""

    if sum(char.isdigit() for char in compact) != 1 or len(ranked) < 2:
        return ranked
    top = ranked[0]
    if top.raw_edit_distance == 0:
        return ranked

    eligible = [
        candidate
        for candidate in ranked[1:OCR_VISUAL_TIE_CANDIDATE_LIMIT]
        if candidate.raw_edit_distance == top.raw_edit_distance
        and candidate.ocr_visual_gain > top.ocr_visual_gain
        and candidate.ocr_visual_edit_distance < top.ocr_visual_edit_distance
        and top.score - candidate.score <= OCR_VISUAL_TIE_MAX_SCORE_GAP
    ]
    if not eligible:
        return ranked

    best = min(
        eligible,
        key=lambda item: (
            item.ocr_visual_edit_distance,
            -item.ocr_visual_gain,
            -item.positional_evidence,
            -item.score,
            item.name,
        ),
    )
    best.reasons.add("ocr_visual_tie_correction")
    return [best, *[item for item in ranked if item is not best]]


def promote_unique_nearest_candidate(ranked: list[Candidate]) -> list[Candidate]:
    """Promote one bounded, uniquely closer candidate near the current top."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
    ):
        return ranked
    nearest_distance = min(candidate.raw_edit_distance for candidate in ranked)
    nearest = [
        candidate
        for candidate in ranked
        if candidate.raw_edit_distance == nearest_distance
    ]
    if len(nearest) != 1:
        return ranked
    candidate = nearest[0]
    candidate_rank = ranked.index(candidate) + 1
    top = ranked[0]
    if (
        candidate is top
        or candidate_rank > 3
        or candidate.raw_edit_distance > 4
        or top.raw_edit_distance - candidate.raw_edit_distance < 2
        or top.score - candidate.score > 0.75
    ):
        return ranked
    candidate.reasons.add("unique_nearest_distance_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_contained_nearest_candidate(ranked: list[Candidate]) -> list[Candidate]:
    """Release a unique one-edit candidate from a weaker containment result."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "contains_match" not in ranked[0].reasons
        or any(reason.endswith("_correction") for reason in ranked[0].reasons)
    ):
        return ranked
    nearest_distance = min(candidate.raw_edit_distance for candidate in ranked)
    nearest = [
        candidate
        for candidate in ranked
        if candidate.raw_edit_distance == nearest_distance
    ]
    if len(nearest) != 1:
        return ranked
    top = ranked[0]
    candidate = nearest[0]
    candidate_rank = ranked.index(candidate) + 1
    if (
        candidate is top
        or candidate_rank != 2
        or candidate.raw_edit_distance > 1
        or top.raw_edit_distance - candidate.raw_edit_distance < 1
        or top.score - candidate.score > 0.25
    ):
        return ranked
    candidate.reasons.add("contained_nearest_distance_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_preserved_top_dominant_nearest_candidate(
    ranked: list[Candidate],
) -> list[Candidate]:
    """Release a strongly closer candidate from an earlier fallback guard."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
        or not any(reason.startswith("preserved_") for reason in ranked[0].reasons)
        or any(reason.endswith("_correction") for reason in ranked[0].reasons)
    ):
        return ranked
    nearest_distance = min(candidate.raw_edit_distance for candidate in ranked)
    nearest = [
        candidate
        for candidate in ranked
        if candidate.raw_edit_distance == nearest_distance
    ]
    if len(nearest) != 1:
        return ranked
    top = ranked[0]
    candidate = nearest[0]
    candidate_rank = ranked.index(candidate) + 1
    if (
        candidate is top
        or candidate_rank != 2
        or candidate.raw_edit_distance > 3
        or top.raw_edit_distance - candidate.raw_edit_distance < 1
        or top.weighted_edit_distance - candidate.weighted_edit_distance < 1.30
        or top.score - candidate.score > 0.10
    ):
        return ranked
    candidate.reasons.add("preserved_top_dominant_nearest_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_preserved_top_higher_score_nearest_candidate(
    ranked: list[Candidate],
    compact: str,
) -> list[Candidate]:
    """Release a unique nearer candidate already favored by the final score."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
        or not any(reason.startswith("preserved_") for reason in ranked[0].reasons)
        or any(reason.endswith("_correction") for reason in ranked[0].reasons)
    ):
        return ranked
    nearest_distance = min(candidate.raw_edit_distance for candidate in ranked)
    nearest = [
        candidate
        for candidate in ranked
        if candidate.raw_edit_distance == nearest_distance
    ]
    if len(nearest) != 1:
        return ranked
    top = ranked[0]
    candidate = nearest[0]
    if (
        ranked.index(candidate) + 1 != 2
        or candidate.raw_edit_distance >= top.raw_edit_distance
        or candidate.score <= top.score
        or len(candidate.key) < len(compact)
        or any(reason.endswith("_correction") for reason in candidate.reasons)
    ):
        return ranked
    candidate.reasons.add("preserved_top_higher_score_nearest_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_exact_ligature_nearest_candidate(
    ranked: list[Candidate],
    compact: str,
) -> list[Candidate]:
    """Promote a unique nearest family named by one documented ligature."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
        or any(reason.endswith("_correction") for reason in ranked[0].reasons)
    ):
        return ranked
    ligature_variants = {
        variant
        for variant, reason in evidence_query_variants(compact)
        if reason == "ligature_variant_retrieval"
    }
    matches = [
        candidate
        for candidate in ranked[1:5]
        if candidate.key in ligature_variants
    ]
    if len(matches) != 1:
        return ranked
    candidate = matches[0]
    nearest_distance = min(item.raw_edit_distance for item in ranked)
    nearest = [
        item for item in ranked if item.raw_edit_distance == nearest_distance
    ]
    top = ranked[0]
    candidate_rank = ranked.index(candidate) + 1
    candidate_dual = (
        candidate.external_rank is not None and candidate.rescue_rank is not None
    )
    if (
        len(nearest) != 1
        or nearest[0] is not candidate
        or candidate_rank > 4
        or not candidate_dual
        or top.raw_edit_distance - candidate.raw_edit_distance < 1
        or candidate.weighted_edit_distance > top.weighted_edit_distance
        or top.score - candidate.score > 0.40
    ):
        return ranked
    candidate.reasons.add("exact_ligature_nearest_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_weighted_edge_tie_candidate(ranked: list[Candidate]) -> list[Candidate]:
    """Break a raw-distance tie only for a unique, large weighted advantage."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
    ):
        return ranked
    top = ranked[0]
    tied = [
        candidate
        for candidate in ranked[:5]
        if candidate.raw_edit_distance == top.raw_edit_distance
    ]
    best_weighted = min(candidate.weighted_edit_distance for candidate in tied)
    best = [
        candidate
        for candidate in tied
        if candidate.weighted_edit_distance == best_weighted
    ]
    if len(best) != 1:
        return ranked
    candidate = best[0]
    candidate_rank = ranked.index(candidate) + 1
    if (
        candidate is top
        or candidate_rank > 3
        or top.weighted_edit_distance - candidate.weighted_edit_distance < 0.70
        or candidate.edge_evidence < top.edge_evidence
        or top.score - candidate.score > 0.40
    ):
        return ranked
    candidate.reasons.add("weighted_edge_tie_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_weighted_edge_advantage_candidate(
    ranked: list[Candidate],
) -> list[Candidate]:
    """Use moderate weighted evidence only when edge evidence also improves."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
        or any(reason.endswith("_correction") for reason in ranked[0].reasons)
    ):
        return ranked
    top = ranked[0]
    tied = [
        candidate
        for candidate in ranked[:5]
        if candidate.raw_edit_distance == top.raw_edit_distance
    ]
    best_weighted = min(candidate.weighted_edit_distance for candidate in tied)
    best = [
        candidate
        for candidate in tied
        if candidate.weighted_edit_distance == best_weighted
    ]
    if len(best) != 1:
        return ranked
    candidate = best[0]
    candidate_rank = ranked.index(candidate) + 1
    if (
        candidate is top
        or candidate_rank != 2
        or top.weighted_edit_distance - candidate.weighted_edit_distance < 0.50
        or candidate.edge_evidence - top.edge_evidence < 0.20
        or top.score - candidate.score > 0.25
    ):
        return ranked
    candidate.reasons.add("weighted_edge_advantage_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_weighted_exact_key_tie_candidate(
    ranked: list[Candidate],
    compact: str,
) -> list[Candidate]:
    """Use a unique weighted winner without overriding a shorter top family."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
        or len(ranked[0].key) < len(compact)
        or any(reason.endswith("_correction") for reason in ranked[0].reasons)
    ):
        return ranked
    top = ranked[0]
    tied = [
        candidate
        for candidate in ranked[:5]
        if candidate.raw_edit_distance == top.raw_edit_distance
    ]
    best_weighted = min(candidate.weighted_edit_distance for candidate in tied)
    best = [
        candidate
        for candidate in tied
        if candidate.weighted_edit_distance == best_weighted
    ]
    if len(best) != 1:
        return ranked
    candidate = best[0]
    candidate_rank = ranked.index(candidate) + 1
    candidate_dual = (
        candidate.external_rank is not None and candidate.rescue_rank is not None
    )
    exact_key_advantage = (
        "phonetic_exact" in candidate.reasons
        and "phonetic_exact" not in top.reasons
    ) or (
        "skeleton_exact" in candidate.reasons
        and "skeleton_exact" not in top.reasons
    )
    if (
        candidate is top
        or candidate_rank != 2
        or not candidate_dual
        or not exact_key_advantage
        or top.weighted_edit_distance - candidate.weighted_edit_distance < 0.45
        or top.score - candidate.score > 0.05
    ):
        return ranked
    candidate.reasons.add("weighted_exact_key_tie_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_exact_transposition_tie_candidate(
    ranked: list[Candidate],
    compact: str,
) -> list[Candidate]:
    """Resolve a raw tie when one candidate exactly undoes one adjacent swap."""

    if (
        len(ranked) < 2
        or len(compact) < 5
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
        or any(reason.endswith("_correction") for reason in ranked[0].reasons)
    ):
        return ranked
    variants = {
        compact[:index]
        + compact[index + 1]
        + compact[index]
        + compact[index + 2 :]
        for index in range(len(compact) - 1)
        if compact[index] != compact[index + 1]
    }
    top = ranked[0]
    matches = [
        candidate
        for candidate in ranked[1:3]
        if candidate.key in variants
        and candidate.raw_edit_distance == top.raw_edit_distance
    ]
    if len(matches) != 1:
        return ranked
    candidate = matches[0]
    candidate_rank = ranked.index(candidate) + 1
    if (
        candidate_rank > 3
        or candidate.raw_edit_distance > 1
        or candidate.weighted_edit_distance > top.weighted_edit_distance
        or top.score - candidate.score > 0.25
    ):
        return ranked
    candidate.reasons.add("exact_transposition_tie_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_exact_transposition_dual_extension_candidate(
    ranked: list[Candidate],
    compact: str,
) -> list[Candidate]:
    """Extend exact swap handling only to a dual-retrieved rank-two family."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
        or any(reason.endswith("_correction") for reason in ranked[0].reasons)
    ):
        return ranked
    variants = {
        compact[:index]
        + compact[index + 1]
        + compact[index]
        + compact[index + 2 :]
        for index in range(len(compact) - 1)
        if compact[index] != compact[index + 1]
    }
    top = ranked[0]
    matches = [
        candidate
        for candidate in ranked[1:5]
        if candidate.key in variants
        and candidate.raw_edit_distance == top.raw_edit_distance
    ]
    if len(matches) != 1:
        return ranked
    candidate = matches[0]
    candidate_dual = (
        candidate.external_rank is not None and candidate.rescue_rank is not None
    )
    if (
        ranked.index(candidate) + 1 != 2
        or candidate.raw_edit_distance > 1
        or not candidate_dual
        or candidate.weighted_edit_distance > top.weighted_edit_distance
        or top.score - candidate.score > 0.65
    ):
        return ranked
    candidate.reasons.add("exact_transposition_dual_extension_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_exact_keyboard_key_tie_candidate(
    ranked: list[Candidate],
    compact: str,
) -> list[Candidate]:
    """Use one exact keyboard reversal when an independent key agrees."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
        or any(reason.endswith("_correction") for reason in ranked[0].reasons)
    ):
        return ranked
    variants = {variant for variant, _ in keyboard_neighbor_variants(compact)}
    top = ranked[0]
    if top.key in variants:
        return ranked
    matches = [
        candidate
        for candidate in ranked[1:5]
        if candidate.key in variants
        and candidate.raw_edit_distance == top.raw_edit_distance
    ]
    if len(matches) != 1:
        return ranked
    candidate = matches[0]
    exact_key_advantage = (
        "phonetic_exact" in candidate.reasons
        and "phonetic_exact" not in top.reasons
    ) or (
        "skeleton_exact" in candidate.reasons
        and "skeleton_exact" not in top.reasons
    )
    if (
        ranked.index(candidate) + 1 != 2
        or candidate.raw_edit_distance > 1
        or not exact_key_advantage
        or candidate.weighted_edit_distance > top.weighted_edit_distance
        or top.score - candidate.score > 0.10
    ):
        return ranked
    candidate.reasons.add("exact_keyboard_key_tie_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_exact_keyboard_weighted_extension_candidate(
    ranked: list[Candidate],
    compact: str,
) -> list[Candidate]:
    """Extend keyboard recovery only when weighted and key evidence agree."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
        or any(reason.endswith("_correction") for reason in ranked[0].reasons)
    ):
        return ranked
    variants = {variant for variant, _ in keyboard_neighbor_variants(compact)}
    top = ranked[0]
    if top.key in variants:
        return ranked
    matches = [
        candidate
        for candidate in ranked[1:5]
        if candidate.key in variants
        and candidate.raw_edit_distance == top.raw_edit_distance
    ]
    if len(matches) != 1:
        return ranked
    candidate = matches[0]
    candidate_exact_key = (
        "phonetic_exact" in candidate.reasons
        or "skeleton_exact" in candidate.reasons
    )
    if (
        ranked.index(candidate) + 1 != 2
        or candidate.raw_edit_distance > 1
        or not candidate_exact_key
        or top.weighted_edit_distance - candidate.weighted_edit_distance < 0.25
        or top.score - candidate.score > 0.15
    ):
        return ranked
    candidate.reasons.add("exact_keyboard_weighted_extension_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_exact_visual_edge_tie_candidate(
    ranked: list[Candidate],
    compact: str,
) -> list[Candidate]:
    """Use one documented visual substitution when edge evidence improves."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
        or any(reason.endswith("_correction") for reason in ranked[0].reasons)
    ):
        return ranked
    variants = {
        compact[:position] + replacement + compact[position + 1 :]
        for position, character in enumerate(compact)
        for replacement in VISUAL_CHAIN_REPLACEMENTS.get(character, ())
    }
    top = ranked[0]
    if top.key in variants:
        return ranked
    matches = [
        candidate
        for candidate in ranked[1:5]
        if candidate.key in variants
        and candidate.raw_edit_distance == top.raw_edit_distance
    ]
    if len(matches) != 1:
        return ranked
    candidate = matches[0]
    if (
        ranked.index(candidate) + 1 != 2
        or candidate.raw_edit_distance > 1
        or candidate.weighted_edit_distance - top.weighted_edit_distance > 0.25
        or candidate.positional_evidence < top.positional_evidence
        or candidate.edge_evidence - top.edge_evidence < 0.10
        or top.score - candidate.score > 0.15
    ):
        return ranked
    candidate.reasons.add("exact_visual_edge_tie_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_guarded_top_score_dominant_chain_candidate(
    ranked: list[Candidate],
) -> list[Candidate]:
    """Release an exact-chain candidate that decisively beats a guarded top."""

    if len(ranked) < 2 or ranked[0].raw_edit_distance == 0:
        return ranked
    top = ranked[0]
    guarded_top = "variant_head_edit" in top.reasons or any(
        reason.startswith("preserved_") for reason in top.reasons
    )
    if not guarded_top or any(reason.endswith("_correction") for reason in top.reasons):
        return ranked
    candidate = ranked[1]
    chain_reason_count = len(candidate.reasons & EXACT_CHAIN_EVIDENCE_REASONS)
    if (
        chain_reason_count < 1
        or candidate.score - top.score < 1.0
        or candidate.raw_edit_distance - top.raw_edit_distance > 2
        or candidate.weighted_edit_distance - top.weighted_edit_distance > 2.0
    ):
        return ranked
    candidate.reasons.add("guarded_top_score_dominant_chain_correction")
    return [candidate, top, *ranked[2:]]


def promote_score_dominant_chain_release_candidate(
    ranked: list[Candidate],
) -> list[Candidate]:
    """Release a rescue-rank-one chain candidate from the external guard."""

    if len(ranked) < 2 or ranked[0].raw_edit_distance == 0:
        return ranked
    top = ranked[0]
    if (
        "variant_head_edit" in top.reasons
        or any(reason.startswith("preserved_") for reason in top.reasons)
        or any(reason.endswith("_correction") for reason in top.reasons)
        or top.external_rank is None
        or top.rescue_rank is None
    ):
        return ranked
    candidate = ranked[1]
    chain_reason_count = len(candidate.reasons & EXACT_CHAIN_EVIDENCE_REASONS)
    if (
        chain_reason_count < 1
        or candidate.external_rank is not None
        or candidate.rescue_rank != 1
        or candidate.score - top.score < 0.05
        or candidate.raw_edit_distance - top.raw_edit_distance > 1
        or candidate.weighted_edit_distance > top.weighted_edit_distance
    ):
        return ranked
    candidate.reasons.add("score_dominant_chain_release_correction")
    return [candidate, top, *ranked[2:]]


def promote_exact_stutter_prefix_candidate(
    ranked: list[Candidate],
    compact: str,
) -> list[Candidate]:
    """Promote one exact family after removing a duplicated query prefix."""

    if len(ranked) < 2 or ranked[0].raw_edit_distance == 0:
        return ranked
    variants = stutter_prefix_variants(compact)
    matches = [candidate for candidate in ranked if candidate.key in variants]
    if len(matches) != 1 or matches[0] is ranked[0]:
        return ranked
    candidate = matches[0]
    candidate.reasons.add("exact_stutter_prefix_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_exact_ligature_rank_extension_candidate(
    index: RescueIndex,
    ranked: list[Candidate],
    compact: str,
) -> list[Candidate]:
    """Promote one exact ligature family only while other evidence keeps it top five."""

    if len(ranked) < 2 or ranked[0].raw_edit_distance == 0:
        return ranked
    exact_keys = {
        variant
        for variant in single_ligature_variants(compact)
        if variant in index.family_by_key
    }
    if len(exact_keys) != 1:
        return ranked
    candidate = next(
        (item for item in ranked if item.key in exact_keys),
        None,
    )
    if candidate is None or candidate is ranked[0] or ranked.index(candidate) + 1 > 5:
        return ranked
    candidate.reasons.add("exact_ligature_rank_extension_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_exact_phonetic_rewrite_candidate(
    index: RescueIndex,
    ranked: list[Candidate],
    compact: str,
) -> list[Candidate]:
    """Promote one exact phonetic rewrite while other evidence keeps it top five."""

    if len(ranked) < 2 or ranked[0].raw_edit_distance == 0:
        return ranked
    exact_keys = {
        variant
        for variant in single_phonetic_rewrite_variants(compact)
        if variant in index.family_by_key
    }
    if len(exact_keys) != 1:
        return ranked
    candidate = next(
        (item for item in ranked if item.key in exact_keys),
        None,
    )
    if candidate is None or candidate is ranked[0] or ranked.index(candidate) + 1 > 5:
        return ranked
    candidate.reasons.add("exact_phonetic_rewrite_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_exact_key_pareto_tie_candidate(
    ranked: list[Candidate],
) -> list[Candidate]:
    """Promote a tied candidate only when exact-key evidence Pareto-dominates."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
    ):
        return ranked
    top = ranked[0]
    top_dual = top.external_rank is not None and top.rescue_rank is not None
    eligible: list[tuple[float, Candidate]] = []
    for candidate in ranked[1:5]:
        if candidate.raw_edit_distance != top.raw_edit_distance:
            continue
        candidate_dual = (
            candidate.external_rank is not None and candidate.rescue_rank is not None
        )
        exact_key_advantage = (
            "phonetic_exact" in candidate.reasons
            and "phonetic_exact" not in top.reasons
        ) or (
            "skeleton_exact" in candidate.reasons
            and "skeleton_exact" not in top.reasons
        )
        no_worse = (
            candidate.weighted_edit_distance <= top.weighted_edit_distance
            and candidate.positional_evidence >= top.positional_evidence
            and candidate.edge_evidence >= top.edge_evidence
            and candidate_dual >= top_dual
        )
        strictly_better = (
            candidate.weighted_edit_distance < top.weighted_edit_distance
            or candidate.positional_evidence > top.positional_evidence
            or candidate.edge_evidence > top.edge_evidence
            or candidate_dual > top_dual
        )
        if not (exact_key_advantage and no_worse and strictly_better):
            continue
        gain = (
            top.weighted_edit_distance
            - candidate.weighted_edit_distance
            + 0.35 * (candidate.positional_evidence - top.positional_evidence)
            + 0.25 * (candidate.edge_evidence - top.edge_evidence)
            + 0.10 * (int(candidate_dual) - int(top_dual))
        )
        eligible.append((gain, candidate))
    if not eligible:
        return ranked
    best_gain = max(gain for gain, _ in eligible)
    best = [candidate for gain, candidate in eligible if gain == best_gain]
    if len(best) != 1:
        return ranked
    candidate = best[0]
    candidate_rank = ranked.index(candidate) + 1
    if candidate_rank > 3 or top.score - candidate.score > 0.15:
        return ranked
    candidate.reasons.add("exact_key_pareto_tie_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_phonetic_position_tie_candidate(
    ranked: list[Candidate],
) -> list[Candidate]:
    """Resolve a raw tie when phonetic and positional evidence agree."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
        or "phonetic_exact" in ranked[0].reasons
        or any(reason.endswith("_correction") for reason in ranked[0].reasons)
    ):
        return ranked
    top = ranked[0]
    eligible = [
        candidate
        for candidate in ranked[1:5]
        if candidate.raw_edit_distance == top.raw_edit_distance
        and "phonetic_exact" in candidate.reasons
        and top.weighted_edit_distance - candidate.weighted_edit_distance >= 0.50
        and candidate.positional_evidence - top.positional_evidence >= 0.05
        and top.score - candidate.score <= 0.40
        and ranked.index(candidate) + 1 <= 3
    ]
    if len(eligible) != 1:
        return ranked
    candidate = eligible[0]
    candidate.reasons.add("phonetic_position_tie_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_shifted_edge_agreement_candidate(
    ranked: list[Candidate],
) -> list[Candidate]:
    """Prefer a shifted edge match when both retrievers support it."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
        or any(reason.endswith("_correction") for reason in ranked[0].reasons)
    ):
        return ranked
    top = ranked[0]
    top_dual = top.external_rank is not None and top.rescue_rank is not None
    if top_dual:
        return ranked
    eligible = [
        candidate
        for candidate in ranked[1:5]
        if ranked.index(candidate) + 1 <= 3
        and candidate.raw_edit_distance == top.raw_edit_distance
        and candidate.external_rank is not None
        and candidate.rescue_rank is not None
        and candidate.weighted_edit_distance <= top.weighted_edit_distance
        and candidate.ocr_visual_edit_distance <= top.ocr_visual_edit_distance
        and candidate.edge_evidence - top.edge_evidence >= 0.30
        and top.positional_evidence - candidate.positional_evidence >= 0.05
        and top.score - candidate.score <= 0.25
    ]
    if not eligible:
        return ranked
    best_external_rank = min(candidate.external_rank for candidate in eligible)
    best = [
        candidate
        for candidate in eligible
        if candidate.external_rank == best_external_rank
    ]
    if len(best) != 1:
        return ranked
    candidate = best[0]
    candidate.reasons.add("shifted_edge_agreement_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_visual_distance_tie_candidate(
    ranked: list[Candidate],
) -> list[Candidate]:
    """Break a raw-distance tie only for a large OCR-visual advantage."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
    ):
        return ranked
    top = ranked[0]
    tied = [
        candidate
        for candidate in ranked[:5]
        if candidate.raw_edit_distance == top.raw_edit_distance
    ]
    best_visual = min(candidate.ocr_visual_edit_distance for candidate in tied)
    best = [
        candidate
        for candidate in tied
        if candidate.ocr_visual_edit_distance == best_visual
    ]
    if len(best) != 1:
        return ranked
    candidate = best[0]
    candidate_rank = ranked.index(candidate) + 1
    if (
        candidate is top
        or candidate_rank != 2
        or top.ocr_visual_edit_distance - candidate.ocr_visual_edit_distance < 0.70
        or top.score - candidate.score > 0.10
    ):
        return ranked
    candidate.reasons.add("visual_distance_tie_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_skeleton_position_tie_candidate(
    ranked: list[Candidate],
) -> list[Candidate]:
    """Promote one tied exact-skeleton candidate under tight score bounds."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or "variant_head_edit" in ranked[0].reasons
        or "skeleton_exact" in ranked[0].reasons
    ):
        return ranked
    top = ranked[0]
    exact_skeleton = [
        candidate
        for candidate in ranked[1:5]
        if candidate.raw_edit_distance == top.raw_edit_distance
        and "skeleton_exact" in candidate.reasons
    ]
    if len(exact_skeleton) != 1:
        return ranked
    candidate = exact_skeleton[0]
    candidate_rank = ranked.index(candidate) + 1
    if (
        candidate_rank != 2
        or candidate.weighted_edit_distance > top.weighted_edit_distance
        or candidate.positional_evidence < top.positional_evidence
        or top.score - candidate.score > 0.05
    ):
        return ranked
    candidate.reasons.add("skeleton_position_tie_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_bounded_exact_chain_candidate(
    ranked: list[Candidate],
    *,
    chain_reason: str,
    correction_reason: str,
    max_rank: int,
    max_score_gap: float,
    max_raw_disadvantage: float,
    require_unique: bool,
    require_dual: bool = False,
    require_exact_key: bool = False,
    require_position_not_worse: bool = False,
    require_edge_not_worse: bool = False,
    require_weighted_not_worse: bool = False,
    min_chain_reasons: int = 1,
    protect_existing_correction: bool = False,
    protect_variant_head: bool = True,
) -> list[Candidate]:
    """Promote a transformed-query exact match under mechanism-specific bounds."""

    if (
        len(ranked) < 2
        or ranked[0].raw_edit_distance == 0
        or (protect_variant_head and "variant_head_edit" in ranked[0].reasons)
        or chain_reason in ranked[0].reasons
        or (
            protect_existing_correction
            and any(reason.endswith("_correction") for reason in ranked[0].reasons)
        )
    ):
        return ranked
    top = ranked[0]
    candidates = [
        candidate
        for candidate in ranked[1:5]
        if chain_reason in candidate.reasons
    ]
    if not candidates or (require_unique and len(candidates) != 1):
        return ranked
    candidate = candidates[0]
    candidate_rank = ranked.index(candidate) + 1
    candidate_dual = (
        candidate.external_rank is not None and candidate.rescue_rank is not None
    )
    exact_key_advantage = (
        "phonetic_exact" in candidate.reasons
        and "phonetic_exact" not in top.reasons
    ) or (
        "skeleton_exact" in candidate.reasons
        and "skeleton_exact" not in top.reasons
    )
    chain_reason_count = len(candidate.reasons & EXACT_CHAIN_EVIDENCE_REASONS)
    if (
        candidate_rank > max_rank
        or top.score - candidate.score > max_score_gap
        or candidate.raw_edit_distance - top.raw_edit_distance
        > max_raw_disadvantage
        or (require_dual and not candidate_dual)
        or (require_exact_key and not exact_key_advantage)
        or chain_reason_count < min_chain_reasons
        or (
            require_position_not_worse
            and candidate.positional_evidence < top.positional_evidence
        )
        or (
            require_edge_not_worse
            and candidate.edge_evidence < top.edge_evidence
        )
        or (
            require_weighted_not_worse
            and candidate.weighted_edit_distance > top.weighted_edit_distance
        )
    ):
        return ranked
    candidate.reasons.add(correction_reason)
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_strictly_closer_full_name(ranked: list[Candidate], compact: str) -> list[Candidate]:
    """Correct a bounded rescue-only score inversion using spelling evidence."""

    if len(compact) < 5 or len(ranked) < 2:
        return ranked
    top = ranked[0]
    if (
        {"phonetic_exact", "skeleton_exact"} <= top.reasons
        or "prefix_match" in top.reasons
        or "contains_match" in top.reasons
    ):
        return ranked
    top_distance = effective_spelling_distance(top)
    eligible = [
        candidate
        for candidate in ranked[1:]
        if candidate.external_rank is None
        and candidate.raw_edit_distance <= STRICT_FULL_NAME_MAX_DISTANCE
        and top_distance - candidate.raw_edit_distance >= 1
        and candidate.weighted_edit_distance <= top.weighted_edit_distance
        and top.score - candidate.score <= STRICT_FULL_NAME_SCORE_GAP
        and (
            not ENABLE_STRICT_FULL_NAME_EVIDENCE_GUARD
            or (
                top.weighted_edit_distance - candidate.weighted_edit_distance
                >= STRICT_FULL_NAME_MIN_WEIGHTED_GAIN
                and two_sided_edge_score(
                    compact,
                    candidate_evidence_key(candidate),
                )
                - two_sided_edge_score(compact, candidate_evidence_key(top))
                >= STRICT_FULL_NAME_MIN_EDGE_GAIN
                and (candidate.rescue_rank or 999) <= 5
            )
        )
    ]
    if not eligible:
        return ranked
    best = min(
        eligible,
        key=lambda item: (
            item.raw_edit_distance,
            item.weighted_edit_distance,
            -item.positional_evidence,
            -item.score,
            item.name,
        ),
    )
    best.reasons.add("strict_full_name_correction")
    return [best, *[item for item in ranked if item is not best]]


def effective_spelling_distance(candidate: Candidate) -> float:
    """Return full-name distance, or validated catalog-family-head distance."""

    if "variant_head_edit" in candidate.reasons:
        return min(candidate.raw_edit_distance, candidate.head_raw_edit_distance)
    return candidate.raw_edit_distance


def candidate_evidence_key(candidate: Candidate) -> str:
    """Return the catalog spelling that actually supports this candidate."""

    if (
        candidate.is_variant_family
        and "variant_head_edit" in candidate.reasons
        and candidate.head_raw_edit_distance <= VALIDATED_HEAD_MAX_DISTANCE
        and candidate.head_raw_edit_distance + 1e-9 < candidate.raw_edit_distance
    ):
        head = current_eval.compact_key(candidate.variant_group)
        if head:
            return head
    return candidate.key


def apply_validated_family_head_evidence(
    ranked: list[Candidate],
    compact: str,
) -> list[Candidate]:
    """Surface one close representative per validated catalog family head."""

    if len(compact) < 5 or not ranked:
        return ranked

    representatives: dict[str, Candidate] = {}
    for candidate in ranked:
        if "variant_head_edit" not in candidate.reasons:
            continue
        evidence_key = candidate_evidence_key(candidate)
        distance = damerau(compact, evidence_key, weighted=False)
        if distance > VALIDATED_HEAD_MAX_DISTANCE:
            continue
        current = representatives.get(evidence_key)
        if current is None or (
            -candidate.score,
            candidate.rescue_rank or 999,
            candidate.name,
        ) < (
            -current.score,
            current.rescue_rank or 999,
            current.name,
        ):
            representatives[evidence_key] = candidate

    if not representatives:
        return ranked

    top = ranked[0]
    top_key = candidate_evidence_key(top)
    top_distance = damerau(compact, top_key, weighted=False)
    head_distances = {
        key: damerau(compact, key, weighted=False)
        for key in representatives
    }
    nearest_distance = min(head_distances.values())
    nearest_keys = [
        key for key, distance in head_distances.items()
        if distance == nearest_distance
    ]
    nearest_key = nearest_keys[0] if len(nearest_keys) == 1 else ""
    protected_top = any(reason.endswith("_correction") for reason in top.reasons)
    decisive_head = (
        nearest_distance == 1
        and boundary_anchor_count(compact, nearest_key) == 2
    )
    if (
        nearest_distance < top_distance
        and nearest_key
        and compact[:1] == nearest_key[:1]
        and (not protected_top or decisive_head)
    ):
        promoted = representatives[nearest_key]
        promoted.reasons.add("validated_family_head_correction")
        ranked = [
            promoted,
            *[candidate for candidate in ranked if candidate is not promoted],
        ]

    top = ranked[0]
    close_heads = sorted(
        (
            candidate
            for candidate in representatives.values()
            if candidate is not top
        ),
        key=lambda candidate: (
            damerau(compact, candidate_evidence_key(candidate), weighted=False),
            damerau(compact, candidate_evidence_key(candidate), weighted=True),
            -two_sided_edge_score(compact, candidate_evidence_key(candidate)),
            -candidate.score,
            candidate.name,
        ),
    )
    if not close_heads:
        return ranked
    for candidate in close_heads:
        candidate.reasons.add("validated_family_head_shortlist")
    close_head_ids = {id(candidate) for candidate in close_heads}
    tail = [
        candidate
        for candidate in ranked[1:]
        if id(candidate) not in close_head_ids
    ]
    for close_head in close_heads:
        head_distance = effective_spelling_distance(close_head)
        insertion_index = len(tail)
        for index, candidate in enumerate(tail):
            protected = any(
                reason.endswith("_correction")
                or reason in EXACT_CHAIN_EVIDENCE_REASONS
                for reason in candidate.reasons
            )
            if (
                not protected
                and effective_spelling_distance(candidate) > head_distance
            ):
                insertion_index = index
                break
        tail.insert(insertion_index, close_head)
    return [top, *tail]


def surface_short_visible_head_candidates(
    ranked: list[Candidate],
    compact: str,
    limit: int,
) -> list[Candidate]:
    """Reserve bounded result slots for catalog heads supported by short text."""

    if not ranked or not (3 <= len(compact) <= 4) or limit < 2:
        return ranked
    representatives: dict[str, Candidate] = {}
    for candidate in ranked:
        if "short_visible_head_retrieval" not in candidate.reasons:
            continue
        head = current_eval.compact_key(candidate.variant_group)
        if not supports_short_visible_head(compact, head):
            continue
        current = representatives.get(head)
        if current is None or (
            -candidate.score,
            candidate.rescue_rank or 999,
            candidate.name,
        ) < (
            -current.score,
            current.rescue_rank or 999,
            current.name,
        ):
            representatives[head] = candidate

    visible_ids = {id(candidate) for candidate in ranked[:limit]}
    missing = [
        candidate
        for _, candidate in sorted(
            representatives.items(),
            key=lambda item: (
                len(item[0]) - len(compact),
                item[0],
                item[1].name,
            ),
        )
        if id(candidate) not in visible_ids
    ][:SHORT_VISIBLE_HEAD_LIMIT]
    if not missing:
        return ranked

    missing_ids = {id(candidate) for candidate in missing}
    remaining = [
        candidate for candidate in ranked
        if id(candidate) not in missing_ids
    ]
    insertion_index = max(1, min(len(remaining), limit - len(missing)))
    for candidate in missing:
        candidate.reasons.add("short_visible_head_shortlist")
    remaining[insertion_index:insertion_index] = missing
    return remaining


def candidate_family_head_key(candidate: Candidate) -> str:
    """Return the visible catalog-family head without requiring a close-head flag."""

    head = current_eval.compact_key(candidate.variant_group)
    return head or candidate.key


def promote_pareto_character_evidence_candidate(
    ranked: list[Candidate],
    compact: str,
) -> list[Candidate]:
    """Promote one near-top candidate that strictly dominates lexical evidence."""

    if (
        len(ranked) < 2
        or len(compact) < 5
        or ranked[0].raw_edit_distance <= 3
        or any(
            reason.endswith("_correction")
            or reason in EXACT_CHAIN_EVIDENCE_REASONS
            or reason.startswith("preserved_")
            for reason in ranked[0].reasons
        )
    ):
        return ranked

    top = ranked[0]
    top_key = candidate_family_head_key(top)
    top_raw = damerau(compact, top_key, weighted=False)
    top_weighted = damerau(compact, top_key, weighted=True)
    top_visual = damerau(
        compact,
        top_key,
        weighted=True,
        ocr_visual=True,
    )
    top_lcs = longest_common_subsequence_length(compact, top_key)
    top_position = same_position_score(compact, top_key)
    top_edge = two_sided_edge_score(compact, top_key)
    top_structure = (
        2 * len(char_ngrams(compact, 3) & char_ngrams(top_key, 3))
        + len(char_ngrams(compact, 2) & char_ngrams(top_key, 2))
    )

    eligible: list[Candidate] = []
    for candidate in ranked[1:3]:
        key = candidate_family_head_key(candidate)
        structure = (
            2 * len(char_ngrams(compact, 3) & char_ngrams(key, 3))
            + len(char_ngrams(compact, 2) & char_ngrams(key, 2))
        )
        if (
            top.score - candidate.score <= 0.30
            and damerau(compact, key, weighted=False) <= top_raw
            and damerau(compact, key, weighted=True) <= top_weighted
            and damerau(
                compact,
                key,
                weighted=True,
                ocr_visual=True,
            )
            <= top_visual
            and longest_common_subsequence_length(compact, key) >= top_lcs
            and same_position_score(compact, key) >= top_position
            and two_sided_edge_score(compact, key) >= top_edge + 0.10
            and len(char_ngrams(compact, 2) & char_ngrams(key, 2))
            >= len(char_ngrams(compact, 2) & char_ngrams(top_key, 2))
            and len(char_ngrams(compact, 3) & char_ngrams(key, 3))
            >= len(char_ngrams(compact, 3) & char_ngrams(top_key, 3))
            and structure >= top_structure
        ):
            eligible.append(candidate)

    if len(eligible) != 1:
        return ranked
    candidate = eligible[0]
    candidate.reasons.add("pareto_character_evidence_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def promote_candidate_pool_bounded_head_candidate(
    ranked: list[Candidate],
    compact: str,
    limit: int,
) -> list[Candidate]:
    """Promote one uniquely closer returned head only when its evidence dominates."""

    if (
        len(ranked) < 2
        or len(compact) < 5
        or any(
            reason.endswith("_correction")
            or reason in EXACT_CHAIN_EVIDENCE_REASONS
            or reason.startswith("preserved_")
            for reason in ranked[0].reasons
        )
    ):
        return ranked
    representatives: dict[str, Candidate] = {}
    for candidate in ranked[:limit]:
        representatives.setdefault(candidate_family_head_key(candidate), candidate)
    nearest_distance = min(
        damerau(compact, head, weighted=False)
        for head in representatives
    )
    nearest_heads = [
        head
        for head in representatives
        if damerau(compact, head, weighted=False) == nearest_distance
    ]
    if len(nearest_heads) != 1:
        return ranked

    candidate = representatives[nearest_heads[0]]
    top = ranked[0]
    if candidate is top:
        return ranked
    candidate_key = candidate_family_head_key(candidate)
    top_key = candidate_family_head_key(top)
    candidate_raw = damerau(compact, candidate_key, weighted=False)
    top_raw = damerau(compact, top_key, weighted=False)
    candidate_visual = damerau(
        compact,
        candidate_key,
        weighted=True,
        ocr_visual=True,
    )
    top_visual = damerau(
        compact,
        top_key,
        weighted=True,
        ocr_visual=True,
    )
    close_full_name_override = (
        top.raw_edit_distance <= 3
        and not (
            " " in top.name
            and " " not in candidate.name
            and {"catalog_warning", "penalized"} <= top.reasons
            and candidate.raw_edit_distance <= top.raw_edit_distance
            and candidate.weighted_edit_distance
            <= top.weighted_edit_distance - 0.50
            and candidate.ocr_visual_edit_distance
            <= top.ocr_visual_edit_distance - 0.50
            and top.score - candidate.score <= 0.25
        )
    )
    if (
        close_full_name_override
        or candidate_raw > top_raw - 1
        or candidate_visual > top_visual - 0.30
        or longest_common_subsequence_length(compact, candidate_key)
        < longest_common_subsequence_length(compact, top_key)
        or top.score - candidate.score > 0.85
    ):
        return ranked

    candidate.reasons.add("bounded_closer_family_head_correction")
    return [candidate, *[item for item in ranked if item is not candidate]]


def surface_ordered_character_head_candidate(
    index: RescueIndex,
    candidates: dict[str, Candidate],
    ranked: list[Candidate],
    compact: str,
    limit: int,
) -> list[Candidate]:
    """Reserve the last visible slot for one strongly supported missing head."""

    if limit < 2:
        return ranked
    top_distance = (
        damerau(
            compact,
            candidate_family_head_key(ranked[0]),
            weighted=False,
        )
        if ranked
        else 999.0
    )
    if top_distance < 2:
        return ranked
    family_id = ordered_character_head_family_id(index, compact)
    if family_id is None:
        return ranked
    family = index.families[family_id]
    head = family.head_compact or family.compact
    if head in {candidate_family_head_key(candidate) for candidate in ranked}:
        return ranked
    head_distance = damerau(compact, head, weighted=False)
    if ranked and top_distance < head_distance + 2:
        return ranked

    candidate = Candidate(
        key=family.compact,
        name=family.name,
        commercial_name=family.name,
        examples=dedupe([family.name, *family.examples])[:5],
        score=0.01,
        evidence_only_retrieval=True,
        structural_only_retrieval=True,
        needs_clarification=True,
        reasons={
            "ordered_character_head_retrieval",
            "algorithm5_requires_clarification",
        },
    )
    enrich_candidates(index, {candidate.key: candidate}, compact)
    candidates[candidate.key] = candidate
    insertion_index = min(len(ranked), limit - 1)
    return [
        *ranked[:insertion_index],
        candidate,
        *ranked[insertion_index:],
    ]


def promote_two_sided_anchor_tie_candidate(
    ranked: list[Candidate],
    compact: str,
) -> list[Candidate]:
    """Break a short edit tie only when both visible word edges are preserved."""

    if len(ranked) < 2 or len(compact) < 4:
        return ranked
    top = ranked[0]
    top_key = candidate_evidence_key(top)
    top_distance = damerau(compact, top_key, weighted=False)
    if top_distance == 0 or top_distance > TWO_SIDED_ANCHOR_MAX_DISTANCE:
        return ranked
    if any(reason.endswith("_correction") for reason in top.reasons):
        return ranked
    if (
        len(compact) <= 5
        and len(compact) == len(top_key) + 1
        and compact.startswith(top_key)
    ):
        # A trailing character on a short exact prefix can be OCR noise or a
        # real continuation. Keep the existing ambiguous order.
        return ranked
    if boundary_anchor_count(compact, top_key) == 2:
        return ranked

    top_weighted = damerau(compact, top_key, weighted=True)
    top_lcs = longest_common_subsequence_length(compact, top_key)
    top_edge = two_sided_edge_score(compact, top_key)
    eligible: list[Candidate] = []
    for candidate in ranked[1:8]:
        candidate_key = candidate_evidence_key(candidate)
        if damerau(compact, candidate_key, weighted=False) != top_distance:
            continue
        if boundary_anchor_count(compact, candidate_key) != 2:
            continue
        score_gap = top.score - candidate.score
        if (
            score_gap > TWO_SIDED_ANCHOR_MAX_SCORE_GAP
            and "variant_head_edit" not in candidate.reasons
        ):
            continue
        candidate_weighted = damerau(compact, candidate_key, weighted=True)
        candidate_lcs = longest_common_subsequence_length(compact, candidate_key)
        candidate_edge = two_sided_edge_score(compact, candidate_key)
        if candidate_weighted > top_weighted + 1e-9:
            continue
        if (
            top_distance > 1
            and candidate_weighted >= top_weighted - 1e-9
            and candidate_lcs <= top_lcs
        ):
            continue
        if candidate_lcs < top_lcs or candidate_edge + 1e-9 < top_edge:
            continue
        eligible.append(candidate)

    if not eligible:
        return ranked
    evidence_order = sorted(
        eligible,
        key=lambda candidate: (
            damerau(compact, candidate_evidence_key(candidate), weighted=True),
            -longest_common_subsequence_length(
                compact,
                candidate_evidence_key(candidate),
            ),
            -two_sided_edge_score(compact, candidate_evidence_key(candidate)),
            -candidate.score,
            candidate.name,
        ),
    )
    best = evidence_order[0]
    best_key = candidate_evidence_key(best)
    best_signature = (
        damerau(compact, best_key, weighted=True),
        longest_common_subsequence_length(compact, best_key),
        two_sided_edge_score(compact, best_key),
    )
    equally_supported = [
        candidate
        for candidate in evidence_order
        if (
            damerau(
                compact,
                candidate_evidence_key(candidate),
                weighted=True,
            ),
            longest_common_subsequence_length(
                compact,
                candidate_evidence_key(candidate),
            ),
            two_sided_edge_score(compact, candidate_evidence_key(candidate)),
        ) == best_signature
    ]
    if len(equally_supported) != 1:
        return ranked
    best.reasons.add("two_sided_anchor_tie_correction")
    return [best, *[candidate for candidate in ranked if candidate is not best]]


def decision_type_for_response(
    index: RescueIndex,
    compact: str,
    ranked: list[Candidate],
    *,
    unreadable_mode: str,
    legacy_continuation: bool = False,
) -> str:
    """Return the product-facing reason for clarification."""

    if not ranked:
        return "no_match"
    if unreadable_mode == "after":
        return "unreadable_continuation_matches" if legacy_continuation else "unreadable_after_matches"
    if unreadable_mode == "before":
        return "unreadable_before_matches"
    if unreadable_mode == "middle":
        return "unreadable_middle_matches"
    top = ranked[0]
    if len(top.variants) > 1:
        return "family_variant_selection"
    if exact_family_has_prefix_collisions(index, compact, top) or exact_family_has_close_neighbors(top, ranked):
        return "collision_ambiguity"
    if len(ranked) > 1:
        second = ranked[1]
        if abs(top.raw_edit_distance - second.raw_edit_distance) < 1e-9:
            return "equal_distance_ambiguity"
    return "possible_matches" if top.needs_clarification else "ranked_matches"


def external_contribution(score: float, rank: int, status: str) -> float:
    """Convert Algorithm 2 score/rank to Algorithm 5 merge score."""

    value = 0.72 * min(score, 1.0) + 0.32 / (rank + 2)
    if status not in CONFIDENT_EXTERNAL_STATUSES:
        value *= 0.90
    return value


def rescue_contribution(score: float, rank: int) -> float:
    """Convert rescue score/rank to Algorithm 5 merge score."""

    return score + 0.18 / (rank + 1)


def context_contribution(score: float, rank: int) -> float:
    """Convert cleaned-context Algorithm 2 evidence to merge score."""

    return 0.84 * min(score, 1.0) + 0.40 / (rank + 2) + 0.05


def needs_clarification(index: RescueIndex, compact: str, candidate: Candidate, ranked: list[Candidate]) -> bool:
    """Return whether candidate should avoid confident top-1 behavior."""

    if len(compact) <= 2:
        return True
    if "catalog_warning" in candidate.reasons:
        return True
    if prefix_is_risky(index, compact) and "exact_family" not in candidate.reasons:
        return True
    if "exact_family" not in candidate.reasons:
        return True
    # Algorithm 5 is the lower-cost safety-first candidate generator. It ranks
    # exact hits, but still leaves final confirmation to the caller/user because
    # exact-looking commercial names can be dangerous fragments of a different
    # family or carry catalog status/context risks.
    return True


def response_status(index: RescueIndex, compact: str, ranked: list[Candidate]) -> tuple[str, str]:
    """Return conservative response status."""

    if not ranked:
        return "no_match", "No safe match found."
    top = ranked[0]
    second = ranked[1].score if len(ranked) > 1 else 0.0
    margin = top.score - second
    close = sum(1 for item in ranked[:8] if item.score >= top.score - 0.08)
    if len(compact) <= 2:
        return "ambiguous", "Query is too short. Please enter more letters."
    if prefix_is_risky(index, compact) and "exact_family" not in top.reasons:
        return "ambiguous", "Possible matches found, but the prefix is ambiguous."
    if top.needs_clarification or close >= 5:
        return "ambiguous", "Possible matches found, but the safe answer needs clarification."
    if top.score >= 1.22 and margin >= 0.08:
        return "high_confidence", "High confidence Algorithm 5 match."
    if top.score >= 0.96 and margin >= 0.05:
        return "medium_confidence", "Medium confidence Algorithm 5 match."
    return "ambiguous", "Possible matches found, but scores are close."


def candidate_to_result(candidate: Candidate, rank: int) -> dict[str, Any]:
    """Convert an internal candidate to response row shape."""

    sources = []
    if candidate.external_rank:
        sources.append("algorithm_2")
    if candidate.context_rank:
        sources.append("context_clean")
    if candidate.rescue_rank:
        sources.append("rescue")
    source = "+".join(sources) or "algorithm_5"
    reasons = sorted(candidate.reasons | ({"algorithm5_requires_clarification"} if candidate.needs_clarification else set()))
    return {
        "rank": rank,
        "candidate_id": f"ALG5-{candidate.key or rank}",
        "name": candidate.name,
        "commercial_name": candidate.commercial_name or candidate.name,
        "candidate_canonical_name": candidate.name,
        "commercial_examples": candidate.examples[:5],
        "score": round(candidate.score, 6),
        "confidence": "low" if candidate.needs_clarification else "high",
        "needs_clarification": candidate.needs_clarification,
        "external_rank": candidate.external_rank or "",
        "context_rank": candidate.context_rank or "",
        "rescue_rank": candidate.rescue_rank or "",
        "external_score": round(candidate.external_score, 4),
        "context_score": round(candidate.context_score, 4),
        "rescue_score": round(candidate.rescue_score, 4),
        "raw_edit_distance": round(candidate.raw_edit_distance, 4),
        "weighted_edit_distance": round(candidate.weighted_edit_distance, 4),
        "ocr_visual_edit_distance": round(candidate.ocr_visual_edit_distance, 4),
        "ocr_visual_gain": round(candidate.ocr_visual_gain, 4),
        "positional_evidence": round(candidate.positional_evidence, 4),
        "edge_evidence": round(candidate.edge_evidence, 4),
        "variant_group": candidate.variant_group or candidate.name,
        "ingredients": candidate.ingredients,
        "variants": candidate.variants,
        "matched_signals": "|".join(reasons),
        "reasons": reasons,
        "source": source,
    }


def prefix_is_risky(index: RescueIndex, compact: str) -> bool:
    """Return whether a compact query prefix maps to many families."""

    if len(compact) > 5:
        return False
    for length in range(1, min(5, len(compact)) + 1):
        if index.prefix_risk.get(compact[:length], 0) >= (8 if length <= 3 else 12):
            return True
    return False


def exact_family_has_prefix_collisions(index: RescueIndex, compact: str, candidate: Candidate) -> bool:
    """Return whether an exact family is also a prefix for other families."""

    if "exact_family" not in candidate.reasons:
        return False
    prefix_ids = index.prefix.get(compact, set())
    for family_id in prefix_ids:
        family = index.families[family_id]
        if family.compact != candidate.key:
            return True
    return False


def exact_family_has_close_neighbors(candidate: Candidate, ranked: list[Candidate]) -> bool:
    """Return whether exact evidence is surrounded by plausible alternatives."""

    if "exact_family" not in candidate.reasons:
        return False
    for other in ranked[1:6]:
        if other.score >= 1.0:
            return True
    return False


def clarification_sort(candidate: Candidate) -> int:
    return 1 if candidate.needs_clarification else 0


def add(index: dict[str, set[int]], key: str, idx: int) -> None:
    if key:
        index[key].add(idx)


def add_prefixes(index: dict[str, set[int]], value: str, idx: int, min_len: int, max_len: int) -> None:
    for length in range(min_len, min(max_len, len(value)) + 1):
        add(index, value[:length], idx)


def add_suffixes(index: dict[str, set[int]], reversed_value: str, idx: int, min_len: int, max_len: int) -> None:
    for length in range(min_len, min(max_len, len(reversed_value)) + 1):
        add(index, reversed_value[:length], idx)


def char_ngrams(value: str, n: int) -> set[str]:
    if len(value) < n:
        return set()
    return {value[i:i + n] for i in range(len(value) - n + 1)}


def rarest(value: str, n: int, index: dict[str, set[int]], limit: int) -> list[str]:
    grams = [gram for gram in char_ngrams(value, n) if gram in index]
    grams.sort(key=lambda gram: (len(index.get(gram, ())), gram))
    return grams[:limit]


def max_deletes_for(value: str) -> int:
    if len(value) < 4:
        return 0
    if len(value) <= 7:
        return 1
    return 2


def delete_keys(value: str, max_deletes: int) -> set[str]:
    if not value:
        return set()
    results = {value}
    frontier = {value}
    for _ in range(max_deletes):
        next_frontier = set()
        for item in frontier:
            for idx in range(len(item)):
                deleted = item[:idx] + item[idx + 1 :]
                if deleted not in results:
                    results.add(deleted)
                    next_frontier.add(deleted)
        frontier = next_frontier
    return {item for item in results if len(item) >= 3}


def normalized_edit_similarity(
    left: str,
    right: str,
    *,
    weighted: bool,
    ocr_visual: bool = False,
) -> float:
    if not left or not right:
        return 0.0
    dist = damerau(left, right, weighted=weighted, ocr_visual=ocr_visual)
    return max(0.0, 1.0 - dist / max(len(left), len(right)))


def damerau(
    left: str,
    right: str,
    *,
    weighted: bool,
    ocr_visual: bool = False,
) -> float:
    if left == right:
        return 0.0
    prevprev: list[float] | None = None
    prev = [float(i) for i in range(len(right) + 1)]
    for i, left_char in enumerate(left, 1):
        cur = [float(i)] + [0.0] * len(right)
        prev_left = left[i - 2] if i > 1 else ""
        for j, right_char in enumerate(right, 1):
            sub_cost = (
                substitution_cost(left_char, right_char, ocr_visual=ocr_visual)
                if weighted
                else (0.0 if left_char == right_char else 1.0)
            )
            value = min(
                prev[j] + 1.0,
                cur[j - 1] + 1.0,
                prev[j - 1] + sub_cost,
            )
            if prevprev is not None and j > 1 and left_char == right[j - 2] and prev_left == right_char:
                value = min(value, prevprev[j - 2] + (0.55 if weighted else 1.0))
            cur[j] = value
        prevprev, prev = prev, cur
    return prev[-1]


def substitution_cost(left: str, right: str, *, ocr_visual: bool = False) -> float:
    if left == right:
        return 0.0
    if ocr_visual and right in OCR_DIGIT_TO_LETTERS.get(left, set()):
        return 0.45
    if (left, right) in CONFUSION_PAIRS:
        return 0.45
    if left in VOWELS and right in VOWELS:
        return 0.70
    return 1.0


def first_char_variants(value: str) -> set[str]:
    """Return compact variants with a plausible first-letter substitution."""

    if not value:
        return set()
    out = set()
    for char in confusable_chars(value[0]):
        out.add(char + value[1:])
    return out


def confusable_chars(char: str) -> set[str]:
    if not char:
        return set()
    upper = char.upper()
    out = set()
    for group in CONFUSION_GROUPS:
        if upper in group:
            out.update(member.lower() for member in group if member != upper)
    return out


def first_chars_confusable(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return right.lower() in confusable_chars(left.lower())


def same_position_score(query: str, target: str) -> float:
    if not query or not target:
        return 0.0
    matches = sum(left == right for left, right in zip(query, target))
    return matches / max(len(query), len(target))


def length_coverage(query: str, target: str) -> float:
    if not query or not target:
        return 0.0
    return min(len(query), len(target)) / max(len(query), len(target))


def is_partial_prefix_match(query: str, target: str) -> bool:
    if not query or not target:
        return False
    if abs(len(query) - len(target)) < 2:
        return False
    shorter = query if len(query) < len(target) else target
    longer = target if shorter == query else query
    return longer.startswith(shorter) and len(shorter) / len(longer) < 0.86


def prefix_score(query: str, target: str) -> float:
    if not query or not target:
        return 0.0
    shared = 0
    for left, right in zip(query, target):
        if left != right:
            break
        shared += 1
    return shared / max(len(query), len(target))


def suffix_score(query: str, target: str) -> float:
    if not query or not target:
        return 0.0
    shared = 0
    for left, right in zip(reversed(query), reversed(target)):
        if left != right:
            break
        shared += 1
    return shared / max(len(query), len(target))


def two_sided_edge_score(query: str, target: str) -> float:
    """Return the combined visible prefix and suffix support."""

    return prefix_score(query, target) + suffix_score(query, target)


def boundary_anchor_count(query: str, target: str) -> int:
    """Count whether the first and last visible characters are preserved."""

    if not query or not target:
        return 0
    return int(query[0] == target[0]) + int(query[-1] == target[-1])


def longest_common_subsequence_length(left: str, right: str) -> int:
    """Return how many visible characters survive in the same order."""

    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    for left_char in left:
        current = [0]
        for index, right_char in enumerate(right, 1):
            if left_char == right_char:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(previous[index], current[-1]))
        previous = current
    return previous[-1]


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def key_similarity(query_key: str, target_key: str) -> float:
    if not query_key or not target_key:
        return 0.0
    if query_key == target_key:
        return 1.0
    if target_key.startswith(query_key) or query_key.startswith(target_key):
        return min(len(query_key), len(target_key)) / max(len(query_key), len(target_key))
    return 0.75 * subsequence_score(query_key, target_key)


def subsequence_score(query: str, target: str) -> float:
    if not query or not target or len(query) > len(target):
        return 0.0
    pos = 0
    span_start = -1
    span_end = -1
    for char in query:
        found = target.find(char, pos)
        if found < 0:
            return 0.0
        if span_start < 0:
            span_start = found
        span_end = found
        pos = found + 1
    span = span_end - span_start + 1
    density = len(query) / span if span else 0.0
    coverage = len(query) / len(target)
    return min(1.0, 0.60 * density + 0.40 * coverage)


def is_ordered_subsequence(shorter: str, longer: str) -> bool:
    """Return whether every typed character occurs in order in the candidate."""

    if not shorter or not longer or len(shorter) > len(longer):
        return False
    position = 0
    for char in longer:
        if char == shorter[position]:
            position += 1
            if position == len(shorter):
                return True
    return False


def is_pure_deletion_candidate(candidate: Candidate, compact: str) -> bool:
    """Identify a candidate explained only by one or two omitted characters."""

    return bool(
        len(compact) >= 5
        and candidate.raw_edit_distance <= 2
        and len(candidate.key) - len(compact) == candidate.raw_edit_distance
        and is_ordered_subsequence(compact, candidate.key)
    )


def strong_name_overlap(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return (
        normalized_edit_similarity(left, right, weighted=True) >= 0.74
        or (left[:4] and right.startswith(left[:4]))
        or (right[:4] and left.startswith(right[:4]))
    )


def dedupe(values: Iterable[Any]) -> list[str]:
    out = []
    seen = set()
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out

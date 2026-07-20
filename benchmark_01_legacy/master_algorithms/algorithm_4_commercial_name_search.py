#!/usr/bin/env python3
"""Algorithm 4: fast external search plus lightweight family rescue.

Algorithm 3 improved safety by running both Algorithm 1 and Algorithm 2, then
fusing their ranked lists. That works, but it pays the cost of both child
searches for every query. Algorithm 4 keeps Algorithm 2 as the only full search
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
    head_delete: dict[str, set[int]]
    head_phonetic: dict[str, set[int]]
    head_length: dict[int, set[int]]
    delete_index: dict[str, set[int]]
    length: dict[int, set[int]]
    first_char: dict[str, set[int]]
    prefix_risk: dict[str, int]
    family_by_key: dict[str, int]
    variant_groups: dict[str, list[int]]

@dataclass
class Algorithm4Catalog:
    """Prepared Algorithm 4 state."""

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
    positional_evidence: float = 0.0
    edge_evidence: float = 0.0
    head_raw_edit_distance: float = 999.0
    is_variant_family: bool = False
    variant_group: str = ""
    ingredients: list[str] = field(default_factory=list)
    variants: list[str] = field(default_factory=list)
    needs_clarification: bool = True
    reasons: set[str] = field(default_factory=set)


def prepare_catalog() -> Algorithm4Catalog:
    """Prepare external search and the lightweight family rescue index."""

    records = current_eval.prepare_records()
    if not records:
        raise ValueError("app catalog produced zero records")
    external_module = load_external_module(EXTERNAL_ALGORITHM_PATH)
    external_catalog = external_module.prepare_catalog(build_external_rows(records))
    rescue_index = build_rescue_index(records)
    return Algorithm4Catalog(
        external_module=external_module,
        external_catalog=external_catalog,
        rescue_index=rescue_index,
    )


def load_external_module(path: Path) -> ModuleType:
    """Load Algorithm 2 from an explicit path."""

    if not path.exists():
        raise FileNotFoundError(f"external algorithm not found: {path}")
    spec = importlib.util.spec_from_file_location("algorithm4_external_english_fast", path)
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
        head_delete=defaultdict(set),
        head_phonetic=defaultdict(set),
        head_length=defaultdict(set),
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
            add(index.head_phonetic, family.head_phonetic, family.id)
            index.head_length[len(family.head_compact)].add(family.id)
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


def search_catalog(catalog: Algorithm4Catalog, raw_query: Any, limit: int = TOP_K_DEFAULT) -> dict[str, Any]:
    """Run Algorithm 4 and return an Algorithm-2-shaped response."""

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

    rescue_results = (
        rescue_search(
            catalog.rescue_index,
            query_text,
            external_results,
            external_status,
            max(limit, INTERNAL_EXTERNAL_LIMIT),
        )
        if unreadable_mode != "none" or should_run_rescue(compact, external_results, external_status)
        else []
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

    scored = []
    for family_id in ids:
        family = index.families[family_id]
        item = score_family(
            index,
            family,
            compact,
            norm,
            query_skeleton,
            query_phonetic,
            allow_head=family_id in selected_head_ids,
        )
        if item:
            if family_id in selected_edge_ids:
                item["reasons"] = sorted({*item["reasons"], "two_char_edge_retrieval"})
            scored.append(item)
    scored.sort(key=lambda row: (-float(row["score"]), str(row["name"])))
    for row in scored[:limit]:
        row["_candidate_pool"] = len(ids)
    return scored[:limit]


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
    # A three-character OCR query can be a one-deletion key for a four-character family.
    if 3 <= len(compact) <= 18:
        for key in delete_keys(compact, max_deletes_for(compact)):
            bucket = index.delete_index.get(key)
            if bucket and len(bucket) <= 650:
                ids.update(bucket)
    return ids


def short_edge_family_ids(index: RescueIndex, compact: str) -> set[int]:
    """Return compatible-length families sharing a two-character edge."""

    candidates = set(index.prefix.get(compact[:2], ()))
    candidates.update(index.suffix.get(compact[::-1][:2], ()))
    return {
        family_id
        for family_id in candidates
        if abs(len(index.families[family_id].compact) - len(compact)) <= 2
    }


def should_run_head_rescue(
    compact: str,
    external_results: list[dict[str, Any]],
    external_status: str,
) -> bool:
    """Gate family-head fallback to weak short/medium brand-like searches."""

    if not (5 <= len(compact) <= 18):
        return False
    for item in external_results[:3]:
        name = str(
            item.get("name")
            or item.get("candidate_canonical_name")
            or item.get("commercial_name")
            or ""
        )
        candidate_key = current_eval.compact_key(name)
        if candidate_key and damerau(compact, candidate_key, weighted=False) <= 2:
            return False
        if candidate_key and len(candidate_key) >= 5 and compact.startswith(candidate_key):
            # The child already found the visible brand and the remaining
            # query is likely strength/form/route context, not a family-head
            # spelling failure.
            return False
    top_score = float(external_results[0].get("score") or 0.0) if external_results else 0.0
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
    scanned = 0
    for length in range(max(1, len(compact) - 2), len(compact) + 3):
        for family_id in sorted(index.head_length.get(length, ())):
            if scanned >= 1200:
                return ids
            scanned += 1
            family = index.families[family_id]
            if (
                family.head_compact[:1] in first_chars
                and damerau(compact, family.head_compact, weighted=False) <= 2
            ):
                ids.add(family_id)
    return ids


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


def should_run_rescue(compact: str, external_results: list[dict[str, Any]], external_status: str) -> bool:
    """Gate Algorithm 4's rescue pass so normal queries stay close to Algorithm 2 cost."""

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
    head_plausible = bool(
        allow_head
        and family.head_compact
        and abs(len(compact) - len(family.head_compact)) <= 2
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
        edit = normalized_edit_similarity(compact, family.compact, weighted=True)

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
        allow_head
        and family.head_compact
        and damerau(compact, family.head_compact, weighted=False) <= 2
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
        if damerau(compact, family.head_compact, weighted=False) <= 2:
            head_score += 0.45
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
) -> dict[str, Any] | None:
    """Score one rescue family."""

    reasons: set[str] = set()
    if family.warnings:
        reasons.add("catalog_warning")

    exact = 1.0 if compact == family.compact or norm == family.norm else 0.0
    if exact:
        reasons.add("exact_family")
    edit = normalized_edit_similarity(compact, family.compact, weighted=False)
    weighted = normalized_edit_similarity(compact, family.compact, weighted=True)
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

    head_raw_distance = 999.0
    if (
        allow_head
        and family.head_compact
        and damerau(compact, family.head_compact, weighted=False) <= 2
    ):
        head_raw_distance = damerau(compact, family.head_compact, weighted=False)
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
        if head_raw_distance <= 2:
            head_score += 0.30
            reasons.add("variant_head_edit")
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
        candidate = candidates.setdefault(key, Candidate(
            key=key,
            name=name,
            commercial_name=str(item.get("commercial_name") or name),
        ))
        candidate.rescue_rank = rank if candidate.rescue_rank is None else min(candidate.rescue_rank, rank)
        candidate.rescue_score = max(candidate.rescue_score, float(item.get("score") or 0.0))
        candidate.name = name
        candidate.commercial_name = str(item.get("commercial_name") or candidate.commercial_name or name)
        candidate.examples.extend(value for value in item.get("commercial_examples", []) or [] if value not in candidate.examples)
        item_reasons = {str(value) for value in item.get("reasons", []) or []}
        candidate.reasons.update(item_reasons)
        candidate.reasons.add(f"rescue_rank_{rank}")
        rescue_score = rescue_contribution(candidate.rescue_score, rank)
        if "variant_head_edit" in item_reasons:
            # A shared catalog family head is useful evidence for adding a
            # missing variant, but it must not erase stronger full-name
            # evidence. rank_candidates may promote it later when the current
            # top result is not itself a close spelling match.
            rescue_score = candidate.score if candidate.score > 0.0 else 0.01
        candidate.score = max(candidate.score, rescue_score)
        if candidate.external_rank is not None:
            candidate.score += 0.08
            candidate.reasons.add("algorithm_2_rescue_agreement")

    for candidate in candidates.values():
        candidate.examples = dedupe([candidate.commercial_name, *candidate.examples])[:5]
    return candidates


def enrich_candidates(index: RescueIndex, candidates: dict[str, Candidate], compact: str) -> None:
    """Attach symmetric spelling evidence and catalog variant metadata."""

    for candidate in candidates.values():
        candidate.raw_edit_distance = damerau(compact, candidate.key, weighted=False)
        candidate.weighted_edit_distance = damerau(compact, candidate.key, weighted=True)
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


def rank_candidates(candidates: list[Candidate], compact: str, *, brand_like: bool) -> list[Candidate]:
    """Apply conservative, evidence-backed corrections to the model ranking.

    Edit distance is not a global ordering rule. It only overrides the model
    when both retrieval layers support a candidate that is strictly closer by
    one edit, for a pure insertion/deletion relation, or when a concatenated
    multi-token false positive narrowly beats a substantially closer family.
    Equal-distance candidates stay in model order; close alternatives still
    trigger ambiguity.
    """

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

    return promote_strictly_closer_full_name(ranked, compact)


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
    """Convert Algorithm 2 score/rank to Algorithm 4 merge score."""

    value = 0.72 * min(score, 1.0) + 0.32 / (rank + 2)
    if status not in CONFIDENT_EXTERNAL_STATUSES:
        value *= 0.90
    return value


def rescue_contribution(score: float, rank: int) -> float:
    """Convert rescue score/rank to Algorithm 4 merge score."""

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
    # Algorithm 4 is the lower-cost safety-first candidate generator. It ranks
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
        return "high_confidence", "High confidence Algorithm 4 match."
    if top.score >= 0.96 and margin >= 0.05:
        return "medium_confidence", "Medium confidence Algorithm 4 match."
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
    source = "+".join(sources) or "algorithm_4"
    reasons = sorted(candidate.reasons | ({"algorithm4_requires_clarification"} if candidate.needs_clarification else set()))
    return {
        "rank": rank,
        "candidate_id": f"ALG4-{candidate.key or rank}",
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
    grams.sort(key=lambda gram: len(index.get(gram, ())))
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


def normalized_edit_similarity(left: str, right: str, *, weighted: bool) -> float:
    if not left or not right:
        return 0.0
    dist = damerau(left, right, weighted=weighted)
    return max(0.0, 1.0 - dist / max(len(left), len(right)))


def damerau(left: str, right: str, *, weighted: bool) -> float:
    if left == right:
        return 0.0
    prevprev: list[float] | None = None
    prev = [float(i) for i in range(len(right) + 1)]
    for i, left_char in enumerate(left, 1):
        cur = [float(i)] + [0.0] * len(right)
        prev_left = left[i - 2] if i > 1 else ""
        for j, right_char in enumerate(right, 1):
            sub_cost = substitution_cost(left_char, right_char) if weighted else (0.0 if left_char == right_char else 1.0)
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


def substitution_cost(left: str, right: str) -> float:
    if left == right:
        return 0.0
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

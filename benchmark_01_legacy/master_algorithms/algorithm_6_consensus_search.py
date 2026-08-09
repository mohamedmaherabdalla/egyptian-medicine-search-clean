#!/usr/bin/env python3
"""Algorithm 6: Algorithm 5 plus calibrated multi-retriever consensus.

Algorithm 6 keeps Algorithm 5 as the base search. Nine independent lightweight
retrievers then vote on the same family catalog. A bounded gate may reorder an
existing Algorithm 5 top-three candidate, and one strong consensus-only
candidate may replace rank 20. The thresholds were selected with target-family
cross-fitting, not with medicine-specific exceptions.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Sequence

import jellyfish
import numpy as np
import scipy.sparse as sp
from rapidfuzz import fuzz, process
from rapidfuzz.distance import JaroWinkler, Levenshtein
from sklearn.feature_extraction.text import CountVectorizer
from symspellpy import SymSpell, Verbosity


ROOT = Path(__file__).resolve().parents[2]
ALGORITHM_5_PATH = Path(__file__).with_name(
    "algorithm_5_commercial_name_search.py"
)
DEFAULT_POLICY_PATH = Path(__file__).with_name("algorithm_6_policy.json")
TOP_K_DEFAULT = 20
RRF_CONSTANT = 60
RETRIEVER_NAMES = (
    "algorithm_5",
    "jaro_winkler",
    "match_rating",
    "rapidfuzz_wratio",
    "nysiis",
    "bm25_plus_char3",
    "symspell_uniform_ed3",
    "rapidfuzz_token_sort",
    "soundex",
    "dice_char2",
)

for import_path in (ROOT / "benchmark_01_legacy",):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import evaluate_current_app_search as current_app


DEFAULT_POLICY = {
    "evaluation_version": "algorithm_6_consensus_v1",
    "rank_1_gate": {
        "minimum_sources": 7,
        "minimum_source_advantage": 1,
        "minimum_levenshtein_advantage": 0.02,
        "maximum_jaro_disadvantage": 0.02,
        "minimum_bigram_advantage": 0.0,
        "maximum_algorithm_5_rank": 3,
    },
    "top_20_gate": {
        "slots": 1,
        "minimum_sources": 3,
        "minimum_levenshtein_similarity": 0.55,
        "minimum_jaro_winkler": 0.85,
    },
    "confusion_costs": {
        "substitution": {},
        "insertion": {},
        "deletion": {},
    },
}


@dataclass(frozen=True)
class Family:
    key: str
    name: str
    normalized: str
    frequency: int


@dataclass
class ConsensusCandidate:
    key: str
    name: str
    source_ranks: dict[str, int] = field(default_factory=dict)
    algorithm_5_result: dict[str, Any] | None = None
    levenshtein_similarity: float = 0.0
    jaro_winkler: float = 0.0
    bigram_dice: float = 0.0
    learned_similarity: float = 0.0

    @property
    def source_count(self) -> int:
        return len(self.source_ranks)

    @property
    def reciprocal_rank_fusion(self) -> float:
        return sum(
            1 / (RRF_CONSTANT + rank)
            for rank in self.source_ranks.values()
        )

    @property
    def algorithm_5_rank(self) -> int:
        return self.source_ranks.get("algorithm_5", 999)


@dataclass
class Algorithm6Catalog:
    algorithm_5_module: ModuleType
    algorithm_5_catalog: Any
    families: list[Family]
    family_index: dict[str, int]
    compact_choices: list[str]
    normalized_choices: list[str]
    phonetic_choices: dict[str, list[str]]
    char2_vectorizer: CountVectorizer
    char2_binary: sp.csr_matrix
    char2_cardinality: np.ndarray
    char3_vectorizer: CountVectorizer
    bm25_plus_char3: sp.csr_matrix
    symspell: SymSpell
    variant_family_keys: set[str]
    policy: dict[str, Any]


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_policy(path: Path | None) -> dict[str, Any]:
    policy_path = path or DEFAULT_POLICY_PATH
    if not policy_path.exists():
        return json.loads(json.dumps(DEFAULT_POLICY))
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    for required in ("rank_1_gate", "top_20_gate", "confusion_costs"):
        if required not in policy:
            raise ValueError(f"Algorithm 6 policy is missing {required}")
    return policy


def build_families(records: Sequence[dict[str, Any]]) -> list[Family]:
    names: dict[str, str] = {}
    frequencies: Counter[str] = Counter()
    for record in records:
        name = str(record.get("b") or record.get("n") or "").strip()
        key = current_app.compact_key(name)
        if not key:
            continue
        names.setdefault(key, name)
        frequencies[key] += 1
    families = [
        Family(
            key=key,
            name=names[key],
            normalized=current_app.normalize_search(names[key]),
            frequency=frequencies[key],
        )
        for key in sorted(
            names,
            key=lambda value: (names[value].casefold(), value),
        )
    ]
    if len(families) != 17_476:
        raise ValueError(
            f"expected 17,476 medicine families, found {len(families)}"
        )
    return families


def bm25_plus_weights(
    counts: sp.csr_matrix,
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> sp.csr_matrix:
    matrix = counts.copy().astype(np.float32)
    lengths = np.asarray(matrix.sum(axis=1)).ravel()
    average_length = float(lengths.mean())
    frequency = np.asarray((matrix > 0).sum(axis=0)).ravel()
    inverse_document_frequency = (
        np.log(matrix.shape[0] + 1.0) - np.log(frequency)
    )
    for row_index in range(matrix.shape[0]):
        start, end = matrix.indptr[row_index : row_index + 2]
        if start == end:
            continue
        term_indexes = matrix.indices[start:end]
        term_frequency = matrix.data[start:end]
        normalizer = 1.0 - b + b * lengths[row_index] / average_length
        matrix.data[start:end] = (
            inverse_document_frequency[term_indexes]
            * term_frequency
            * (k1 + 1.0)
            / (k1 * normalizer + term_frequency)
        ).astype(np.float32)
    return matrix


def prepare_catalog(
    policy_path: Path | None = None,
) -> Algorithm6Catalog:
    records = current_app.prepare_records()
    algorithm_5_module = load_module(
        ALGORITHM_5_PATH,
        "algorithm_6_base_algorithm_5",
    )
    algorithm_5_catalog = algorithm_5_module.prepare_catalog()
    families = build_families(records)
    compact_choices = [family.key for family in families]
    normalized_choices = [family.normalized for family in families]

    char2_vectorizer = CountVectorizer(
        analyzer="char",
        ngram_range=(2, 2),
        lowercase=False,
        dtype=np.float32,
    )
    char2_binary = char2_vectorizer.fit_transform(
        compact_choices
    ).tocsr()
    char2_binary.data[:] = 1.0
    char2_cardinality = np.asarray(
        char2_binary.sum(axis=1)
    ).ravel()

    char3_vectorizer = CountVectorizer(
        analyzer="char",
        ngram_range=(3, 3),
        lowercase=False,
        dtype=np.float32,
    )
    char3_counts = char3_vectorizer.fit_transform(
        compact_choices
    ).tocsr()

    symspell = SymSpell(
        max_dictionary_edit_distance=3,
        prefix_length=7,
        count_threshold=1,
    )
    for family in families:
        symspell.create_dictionary_entry(family.key, 1)

    phonetic_choices = {
        name: [encode_phonetic(family.normalized, encoder) for family in families]
        for name, encoder in (
            ("match_rating", jellyfish.match_rating_codex),
            ("nysiis", jellyfish.nysiis),
            ("soundex", jellyfish.soundex),
        )
    }
    variant_family_keys = {
        family.compact
        for family in algorithm_5_catalog.rescue_index.families
        if family.variant_group
        and family.variant_group != family.norm
    }
    return Algorithm6Catalog(
        algorithm_5_module=algorithm_5_module,
        algorithm_5_catalog=algorithm_5_catalog,
        families=families,
        family_index={
            family.key: index for index, family in enumerate(families)
        },
        compact_choices=compact_choices,
        normalized_choices=normalized_choices,
        phonetic_choices=phonetic_choices,
        char2_vectorizer=char2_vectorizer,
        char2_binary=char2_binary,
        char2_cardinality=char2_cardinality,
        char3_vectorizer=char3_vectorizer,
        bm25_plus_char3=bm25_plus_weights(char3_counts),
        symspell=symspell,
        variant_family_keys=variant_family_keys,
        policy=load_policy(policy_path),
    )


def encode_phonetic(
    value: str,
    encoder: Callable[[str], str],
) -> str:
    letters = "".join(
        character
        for character in current_app.normalize_search(value)
        if character.isalpha()
    )
    return encoder(letters) if letters else ""


def rapidfuzz_names(
    catalog: Algorithm6Catalog,
    query: str,
    choices: Sequence[str],
    scorer: Callable[..., Any],
    *,
    limit: int,
) -> list[str]:
    if not query:
        return []
    return [
        catalog.families[index].name
        for _, _, index in process.extract(
            query,
            choices,
            scorer=scorer,
            limit=limit,
        )
    ]


def phonetic_names(
    catalog: Algorithm6Catalog,
    raw_query: str,
    source: str,
    encoder: Callable[[str], str],
    *,
    limit: int,
) -> list[str]:
    query = encode_phonetic(raw_query, encoder)
    return rapidfuzz_names(
        catalog,
        query,
        catalog.phonetic_choices[source],
        Levenshtein.distance,
        limit=limit,
    )


def bm25_names(
    catalog: Algorithm6Catalog,
    compact_query: str,
    *,
    limit: int,
) -> list[str]:
    query = catalog.char3_vectorizer.transform([compact_query]).tocsr()
    scores = (query @ catalog.bm25_plus_char3.T).toarray().ravel()
    return positive_score_names(catalog, scores, limit)


def dice_names(
    catalog: Algorithm6Catalog,
    compact_query: str,
    *,
    limit: int,
) -> list[str]:
    query = catalog.char2_vectorizer.transform(
        [compact_query]
    ).tocsr()
    query.data[:] = 1.0
    intersections = (
        query @ catalog.char2_binary.T
    ).toarray().ravel().astype(np.float32)
    query_cardinality = float(query.sum())
    denominator = query_cardinality + catalog.char2_cardinality
    scores = np.divide(
        2.0 * intersections,
        denominator,
        out=np.zeros_like(intersections),
        where=denominator > 0,
    )
    return positive_score_names(catalog, scores, limit)


def positive_score_names(
    catalog: Algorithm6Catalog,
    scores: np.ndarray,
    limit: int,
) -> list[str]:
    valid = np.flatnonzero(np.isfinite(scores) & (scores > 0))
    if not len(valid):
        return []
    order = np.lexsort((valid, -scores[valid]))
    return [
        catalog.families[index].name
        for index in valid[order[:limit]]
    ]


def symspell_names(
    catalog: Algorithm6Catalog,
    compact_query: str,
    *,
    limit: int,
) -> list[str]:
    suggestions = catalog.symspell.lookup(
        compact_query,
        Verbosity.ALL,
        max_edit_distance=3,
        include_unknown=False,
        transfer_casing=False,
    )
    return [
        catalog.families[catalog.family_index[suggestion.term]].name
        for suggestion in suggestions
        if suggestion.term in catalog.family_index
    ][:limit]


def selected_rankings(
    catalog: Algorithm6Catalog,
    raw_query: str,
    compact_query: str,
    normalized_query: str,
    algorithm_5_results: list[dict[str, Any]],
    *,
    limit: int,
) -> dict[str, list[str]]:
    return {
        "algorithm_5": [
            result_name(item) for item in algorithm_5_results[:limit]
        ],
        "jaro_winkler": rapidfuzz_names(
            catalog,
            compact_query,
            catalog.compact_choices,
            JaroWinkler.similarity,
            limit=limit,
        ),
        "match_rating": phonetic_names(
            catalog,
            raw_query,
            "match_rating",
            jellyfish.match_rating_codex,
            limit=limit,
        ),
        "rapidfuzz_wratio": rapidfuzz_names(
            catalog,
            normalized_query,
            catalog.normalized_choices,
            fuzz.WRatio,
            limit=limit,
        ),
        "nysiis": phonetic_names(
            catalog,
            raw_query,
            "nysiis",
            jellyfish.nysiis,
            limit=limit,
        ),
        "bm25_plus_char3": bm25_names(
            catalog,
            compact_query,
            limit=limit,
        ),
        "symspell_uniform_ed3": symspell_names(
            catalog,
            compact_query,
            limit=limit,
        ),
        "rapidfuzz_token_sort": rapidfuzz_names(
            catalog,
            normalized_query,
            catalog.normalized_choices,
            fuzz.token_sort_ratio,
            limit=limit,
        ),
        "soundex": phonetic_names(
            catalog,
            raw_query,
            "soundex",
            jellyfish.soundex,
            limit=limit,
        ),
        "dice_char2": dice_names(
            catalog,
            compact_query,
            limit=limit,
        ),
    }


def result_name(item: dict[str, Any]) -> str:
    return str(
        item.get("name")
        or item.get("candidate_canonical_name")
        or item.get("commercial_name")
        or ""
    ).strip()


def ngrams(value: str, size: int) -> set[str]:
    if len(value) < size:
        return set()
    return {
        value[index : index + size]
        for index in range(len(value) - size + 1)
    }


def dice(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return 2 * len(left & right) / (len(left) + len(right))


def learned_confusion_distance(
    observed: str,
    target: str,
    policy: dict[str, Any],
) -> float:
    costs = policy.get("confusion_costs", {})
    substitutions = costs.get("substitution", {})
    insertions = costs.get("insertion", {})
    deletions = costs.get("deletion", {})
    previous = [0.0]
    for target_character in target:
        previous.append(
            previous[-1] + float(insertions.get(target_character, 1.0))
        )
    for observed_character in observed:
        current = [
            previous[0]
            + float(deletions.get(observed_character, 1.0))
        ]
        for column, target_character in enumerate(target, 1):
            substitution = (
                0.0
                if observed_character == target_character
                else float(
                    substitutions.get(
                        f"{observed_character}>{target_character}",
                        1.0,
                    )
                )
            )
            current.append(
                min(
                    previous[column]
                    + float(deletions.get(observed_character, 1.0)),
                    current[column - 1]
                    + float(insertions.get(target_character, 1.0)),
                    previous[column - 1] + substitution,
                )
            )
        previous = current
    return previous[-1]


def build_consensus(
    catalog: Algorithm6Catalog,
    compact_query: str,
    rankings: dict[str, list[str]],
    algorithm_5_results: list[dict[str, Any]],
) -> dict[str, ConsensusCandidate]:
    candidates: dict[str, ConsensusCandidate] = {}
    algorithm_5_by_key = {
        current_app.compact_key(result_name(item)): item
        for item in algorithm_5_results
        if current_app.compact_key(result_name(item))
    }
    for source, names in rankings.items():
        for rank, name in enumerate(names, 1):
            key = current_app.compact_key(name)
            if not key:
                continue
            candidate = candidates.setdefault(
                key,
                ConsensusCandidate(key=key, name=name),
            )
            candidate.source_ranks.setdefault(source, rank)
            candidate.algorithm_5_result = algorithm_5_by_key.get(key)
    query_bigrams = ngrams(compact_query, 2)
    for candidate in candidates.values():
        maximum = max(len(compact_query), len(candidate.key), 1)
        candidate.levenshtein_similarity = (
            1
            - Levenshtein.distance(compact_query, candidate.key)
            / maximum
        )
        candidate.jaro_winkler = JaroWinkler.similarity(
            compact_query,
            candidate.key,
        )
        candidate.bigram_dice = dice(
            query_bigrams,
            ngrams(candidate.key, 2),
        )
        learned_distance = learned_confusion_distance(
            compact_query,
            candidate.key,
            catalog.policy,
        )
        candidate.learned_similarity = 1 - learned_distance / maximum
    return candidates


def consensus_order(
    candidates: dict[str, ConsensusCandidate],
) -> list[ConsensusCandidate]:
    return sorted(
        candidates.values(),
        key=lambda candidate: (
            -candidate.source_count,
            -candidate.reciprocal_rank_fusion,
            -candidate.levenshtein_similarity,
            -candidate.jaro_winkler,
            candidate.name.casefold(),
            candidate.key,
        ),
    )


def should_promote(
    base: ConsensusCandidate,
    proposed: ConsensusCandidate,
    catalog: Algorithm6Catalog,
) -> bool:
    gate = catalog.policy["rank_1_gate"]
    if not gate.get("enabled", False):
        return False
    if proposed.key == base.key:
        return False
    if base.key in catalog.variant_family_keys:
        return False
    return bool(
        proposed.algorithm_5_rank
        <= int(gate["maximum_algorithm_5_rank"])
        and proposed.source_count >= int(gate["minimum_sources"])
        and proposed.source_count
        >= base.source_count + int(gate["minimum_source_advantage"])
        and proposed.levenshtein_similarity
        >= base.levenshtein_similarity
        + float(gate["minimum_levenshtein_advantage"])
        and proposed.jaro_winkler
        >= base.jaro_winkler
        - float(gate["maximum_jaro_disadvantage"])
        and proposed.bigram_dice
        >= base.bigram_dice
        + float(gate["minimum_bigram_advantage"])
    )


def augment_result(
    item: dict[str, Any],
    candidate: ConsensusCandidate,
    *,
    reason: str,
) -> dict[str, Any]:
    output = dict(item)
    reasons = list(output.get("reasons") or [])
    if reason not in reasons:
        reasons.append(reason)
    output.update(
        {
            "candidate_id": f"ALG6-{candidate.key}",
            "source": "algorithm_6_consensus",
            "consensus_source_count": candidate.source_count,
            "consensus_sources": sorted(candidate.source_ranks),
            "consensus_rrf": round(
                candidate.reciprocal_rank_fusion,
                6,
            ),
            "consensus_levenshtein_similarity": round(
                candidate.levenshtein_similarity,
                6,
            ),
            "consensus_jaro_winkler": round(
                candidate.jaro_winkler,
                6,
            ),
            "learned_confusion_similarity": round(
                candidate.learned_similarity,
                6,
            ),
            "needs_clarification": True,
            "confidence": "low",
            "reasons": reasons,
            "matched_signals": "|".join(sorted(set(reasons))),
        }
    )
    return output


def external_result(
    candidate: ConsensusCandidate,
) -> dict[str, Any]:
    return augment_result(
        {
            "rank": 0,
            "name": candidate.name,
            "commercial_name": candidate.name,
            "candidate_canonical_name": candidate.name,
            "commercial_examples": [candidate.name],
            "score": round(candidate.reciprocal_rank_fusion, 6),
            "variant_group": candidate.name,
            "ingredients": [],
            "variants": [],
            "reasons": [],
        },
        candidate,
        reason="algorithm6_external_consensus_slot",
    )


def rerank_results(
    catalog: Algorithm6Catalog,
    candidates: dict[str, ConsensusCandidate],
    base_results: list[dict[str, Any]],
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], bool, bool]:
    base_keys = [
        current_app.compact_key(result_name(item))
        for item in base_results[:limit]
    ]
    ranked = [
        augment_result(
            item,
            candidates[key],
            reason="algorithm6_preserved_algorithm5_order",
        )
        for key, item in zip(base_keys, base_results[:limit])
        if key and key in candidates
    ]
    promoted = False
    ordered_consensus = consensus_order(candidates)
    if ranked and ordered_consensus:
        base_key = current_app.compact_key(result_name(ranked[0]))
        base_candidate = candidates[base_key]
        proposed = ordered_consensus[0]
        if should_promote(base_candidate, proposed, catalog):
            proposed_index = next(
                (
                    index
                    for index, item in enumerate(ranked)
                    if current_app.compact_key(result_name(item))
                    == proposed.key
                ),
                None,
            )
            if proposed_index is not None:
                promoted_item = ranked.pop(proposed_index)
                promoted_item = augment_result(
                    promoted_item,
                    proposed,
                    reason="algorithm6_bounded_consensus_promotion",
                )
                ranked.insert(0, promoted_item)
                promoted = True

    top_20_gate = catalog.policy["top_20_gate"]
    base_key_set = set(base_keys)
    external_limit = (
        limit - len(ranked)
        if len(ranked) < limit
        else int(top_20_gate["slots"])
    )
    external = [
        candidate
        for candidate in ordered_consensus
        if candidate.key not in base_key_set
        and candidate.source_count
        >= int(top_20_gate["minimum_sources"])
        and candidate.levenshtein_similarity
        >= float(top_20_gate["minimum_levenshtein_similarity"])
        and candidate.jaro_winkler
        >= float(top_20_gate["minimum_jaro_winkler"])
    ][:external_limit]
    inserted = False
    for candidate in external:
        if len(ranked) >= limit:
            ranked.pop()
        ranked.append(external_result(candidate))
        inserted = True
    for rank, item in enumerate(ranked, 1):
        item["rank"] = rank
    return ranked, promoted, inserted


def calibrated_probability(
    catalog: Algorithm6Catalog,
    candidates: dict[str, ConsensusCandidate],
    results: list[dict[str, Any]],
    compact_query: str,
    *,
    promoted: bool,
    inserted: bool,
) -> tuple[float, bool]:
    calibration = catalog.policy.get("abstention")
    if not calibration or not results:
        return 0.0, False
    ordered = [
        candidates.get(current_app.compact_key(result_name(item)))
        for item in results
    ]
    ordered = [candidate for candidate in ordered if candidate]
    if not ordered:
        return 0.0, False
    top = ordered[0]
    second = ordered[1] if len(ordered) > 1 else None
    values = {
        "top_1_source_count": top.source_count,
        "top_1_rrf": top.reciprocal_rank_fusion,
        "top_1_levenshtein_similarity": top.levenshtein_similarity,
        "top_1_jaro_winkler": top.jaro_winkler,
        "top_1_bigram_dice": top.bigram_dice,
        "top_1_minus_top_2_source_count": (
            top.source_count - second.source_count
            if second
            else top.source_count
        ),
        "top_1_minus_top_2_rrf": (
            top.reciprocal_rank_fusion
            - second.reciprocal_rank_fusion
            if second
            else top.reciprocal_rank_fusion
        ),
        "top_1_minus_top_2_levenshtein": (
            top.levenshtein_similarity
            - second.levenshtein_similarity
            if second
            else top.levenshtein_similarity
        ),
        "top_1_minus_top_2_jaro": (
            top.jaro_winkler - second.jaro_winkler
            if second
            else top.jaro_winkler
        ),
        "returned_candidates": len(results),
        "algorithm_6_promoted": int(promoted),
        "algorithm_6_external_slot_used": int(inserted),
        "input_compact_length": len(compact_query),
    }
    features = calibration["features"]
    standardized = [
        (
            float(values[feature]) - float(mean)
        )
        / (float(scale) or 1.0)
        for feature, mean, scale in zip(
            features,
            calibration["mean"],
            calibration["scale"],
        )
    ]
    logit = float(calibration["intercept"]) + sum(
        float(coefficient) * value
        for coefficient, value in zip(
            calibration["coefficients"],
            standardized,
        )
    )
    probability = (
        1.0
        if logit >= 40
        else 0.0
        if logit <= -40
        else 1 / (1 + math.exp(-logit))
    )
    evidence_passes = all(
        float(values.get(feature, 0.0)) >= float(minimum)
        for feature, minimum in calibration.get(
            "evidence_minimums",
            {},
        ).items()
    )
    return (
        probability,
        evidence_passes
        and probability >= float(calibration["threshold"]),
    )


def search_catalog(
    catalog: Algorithm6Catalog,
    raw_query: Any,
    limit: int = TOP_K_DEFAULT,
) -> dict[str, Any]:
    base_response = catalog.algorithm_5_module.search_catalog(
        catalog.algorithm_5_catalog,
        raw_query,
        max(limit, TOP_K_DEFAULT),
    )
    base_results = list(base_response.get("results") or [])
    if isinstance(raw_query, dict):
        query_text = str(
            raw_query.get("text") or raw_query.get("query") or ""
        )
    else:
        query_text = "" if raw_query is None else str(raw_query)
    compact_query = current_app.compact_key(query_text)
    if not compact_query:
        output = dict(base_response)
        output["algorithm"] = "algorithm_6"
        output["evaluation_version"] = catalog.policy.get(
            "evaluation_version",
            "algorithm_6_consensus_v1",
        )
        return output

    normalized_query = current_app.normalize_search(query_text)
    rankings = selected_rankings(
        catalog,
        query_text,
        compact_query,
        normalized_query,
        base_results,
        limit=TOP_K_DEFAULT,
    )
    candidates = build_consensus(
        catalog,
        compact_query,
        rankings,
        base_results,
    )
    results, promoted, inserted = rerank_results(
        catalog,
        candidates,
        base_results,
        limit=limit,
    )
    probability, likely_match = calibrated_probability(
        catalog,
        candidates,
        results,
        compact_query,
        promoted=promoted,
        inserted=inserted,
    )
    if results:
        results[0]["estimated_correctness_probability"] = round(
            probability,
            6,
        )
        results[0]["calibrated_likely_match"] = likely_match
    output = dict(base_response)
    output.update(
        {
            "algorithm": "algorithm_6",
            "evaluation_version": catalog.policy.get(
                "evaluation_version",
                "algorithm_6_consensus_v1",
            ),
            "status": "ambiguous" if results else "no_match",
            "message": (
                "Likely match found. Confirm it against the prescription."
                if likely_match
                else "Possible matches found. Compare the evidence and "
                "confirm the medicine name."
                if results
                else "No safe match found."
            ),
            "decision_type": (
                "likely_match_requires_confirmation"
                if likely_match
                else "bounded_consensus_promotion"
                if promoted
                else "consensus_candidate_set"
                if inserted
                else "algorithm_5_order_preserved"
            ),
            "candidate_count": len(candidates),
            "algorithm_6_promoted": promoted,
            "algorithm_6_external_slot_used": inserted,
            "estimated_correctness_probability": round(
                probability,
                6,
            ),
            "calibrated_likely_match": likely_match,
            "results": results,
        }
    )
    return output


if __name__ == "__main__":
    prepared = prepare_catalog()
    for query in sys.argv[1:]:
        print(json.dumps(search_catalog(prepared, query), indent=2))

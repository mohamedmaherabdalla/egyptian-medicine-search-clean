#!/usr/bin/env python3
"""Run reproducible Algorithm 5 component ablations on the locked test sets."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import multiprocessing as mp
import statistics
import sys
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from unittest.mock import patch


BENCHMARK_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BENCHMARK_ROOT.parent
OCR_ROOT = PROJECT_ROOT / "benchmark_03_ocr"
LEGACY_ROOT = PROJECT_ROOT / "benchmark_01_legacy"
DEFAULT_ARTIFACTS = BENCHMARK_ROOT / "artifacts/06_competitor_benchmark"
DEFAULT_RESULTS = BENCHMARK_ROOT / "results/06_competitor_benchmark"
ALGORITHM_PATH = (
    LEGACY_ROOT / "master_algorithms/algorithm_5_commercial_name_search.py"
)
TOP_K = 20
EVALUATION_VERSION = "algorithm_5_ablation_v1"

for import_path in (BENCHMARK_ROOT, OCR_ROOT, LEGACY_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import evaluate_current_app_search as current_app
import evaluate_search_algorithms as existing_evaluator
import run_competitor_benchmark as competitors


@dataclass(frozen=True)
class Ablation:
    name: str
    display_name: str
    definition: str
    level: str


BASE_ABLATIONS = (
    Ablation("full_algorithm_5", "Complete Algorithm 5", "No component removed.", "reference"),
    Ablation(
        "without_external_retriever",
        "Without external retriever",
        "Remove Algorithm 2 candidate retrieval, including its cleaned-context pass.",
        "component",
    ),
    Ablation(
        "without_context_cleanup",
        "Without context cleanup",
        "Suppress the second external search on context-cleaned query text.",
        "component",
    ),
    Ablation(
        "without_rescue_layer",
        "Without family rescue",
        "Remove the complete Algorithm 5 family-rescue result list.",
        "component",
    ),
    Ablation(
        "without_raw_edit_similarity",
        "Without raw edit similarity",
        "Set unweighted normalized edit similarity to zero while retaining distances used by guards.",
        "signal",
    ),
    Ablation(
        "without_weighted_edit_similarity",
        "Without weighted edit similarity",
        "Set confusion-weighted normalized edit similarity to zero.",
        "signal",
    ),
    Ablation(
        "without_prefix_signal",
        "Without prefix evidence",
        "Set prefix similarity to zero in retrieval, scoring, and corrections.",
        "signal",
    ),
    Ablation(
        "without_suffix_signal",
        "Without suffix evidence",
        "Set suffix similarity to zero in retrieval, scoring, and corrections.",
        "signal",
    ),
    Ablation(
        "without_ngram_signal",
        "Without character n-grams",
        "Remove character n-gram retrieval and scoring evidence.",
        "signal",
    ),
    Ablation(
        "without_phonetic_signal",
        "Without phonetic evidence",
        "Remove the phonetic key from candidate retrieval and scoring.",
        "signal",
    ),
    Ablation(
        "without_skeleton_signal",
        "Without consonant skeleton",
        "Remove the consonant-skeleton key from candidate retrieval and scoring.",
        "signal",
    ),
    Ablation(
        "without_subsequence_signal",
        "Without subsequence evidence",
        "Set ordered-subsequence similarity to zero.",
        "signal",
    ),
    Ablation(
        "without_positional_signal",
        "Without positional evidence",
        "Set same-position character evidence to zero.",
        "signal",
    ),
    Ablation(
        "without_length_coverage_signal",
        "Without length coverage",
        "Set query-to-family length coverage to zero.",
        "signal",
    ),
    Ablation(
        "without_delete_key_retrieval",
        "Without delete-key retrieval",
        "Remove deletion-key lookup for full names and family heads.",
        "retrieval",
    ),
    Ablation(
        "without_short_edge_retrieval",
        "Without short-edge retrieval",
        "Remove short-query prefix and suffix retrieval.",
        "retrieval",
    ),
    Ablation(
        "without_confusable_first_character_expansion",
        "Without first-character expansion",
        "Remove first-character confusion expansion and plausibility matching.",
        "retrieval",
    ),
    Ablation(
        "without_length_bucket_scan",
        "Without compatible-length scan",
        "Suppress fallback scanning of compatible-length family buckets.",
        "retrieval",
    ),
    Ablation(
        "without_variant_head_rescue",
        "Without family-head rescue",
        "Remove matching against validated catalog family heads.",
        "retrieval",
    ),
    Ablation(
        "without_weighted_confusion_cost",
        "Without weighted confusion costs",
        "Give every non-identical replacement unit cost.",
        "signal",
    ),
    Ablation(
        "without_retrieval_agreement_bonus",
        "Without retriever agreement",
        "Remove external/context and external/rescue agreement bonuses.",
        "signal",
    ),
    Ablation(
        "without_strict_full_name_correction",
        "Without strict full-name correction",
        "Suppress the bounded promotion of a strictly closer rescue-only full name.",
        "reranker",
    ),
    Ablation(
        "without_all_reranking",
        "Without all reranking",
        "Keep merged score order and remove Algorithm 5 top-rank corrections.",
        "reranker",
    ),
    Ablation(
        "without_safety_clarification_gate",
        "Without safety clarification gate",
        "Return the same ranking without Algorithm 5 clarification flags.",
        "safety",
    ),
    Ablation(
        "without_short_query_rescue",
        "Without short-query rescue",
        "Disable rescue triggered only because the compact query has three or four characters.",
        "retrieval",
    ),
    Ablation(
        "without_nearest_fallback",
        "Without bounded-nearest fallback",
        "Remove the bounded exhaustive nearest-family fallback.",
        "retrieval",
    ),
    Ablation(
        "without_evidence_variant_rescue",
        "Without evidence-query variants",
        "Remove one-step visual, ligature, stutter, and phonetic query variants.",
        "retrieval",
    ),
    Ablation(
        "without_short_visible_head_rescue",
        "Without short visible-head rescue",
        "Remove candidates supported by a short visible catalog-family head.",
        "retrieval",
    ),
    Ablation(
        "without_short_frame_rescue",
        "Without short-frame rescue",
        "Remove short consonant/phonetic frames and two-deletion frame candidates.",
        "retrieval",
    ),
    Ablation(
        "without_keyboard_variant_rescue",
        "Without keyboard rescue",
        "Remove keyboard-neighbor variants and keyboard-plus-deletion chains.",
        "retrieval",
    ),
    Ablation(
        "without_ligature_variant_rescue",
        "Without ligature rescue",
        "Remove direct ligature variants and ligature-plus-vowel/transposition chains.",
        "retrieval",
    ),
    Ablation(
        "without_transposition_variant_rescue",
        "Without transposition rescue",
        "Remove adjacent-transposition variants and transposition-plus-deletion chains.",
        "retrieval",
    ),
    Ablation(
        "without_visual_phonetic_chain_rescue",
        "Without visual-phonetic chains",
        "Remove exact candidates requiring a visual replacement followed by a phonetic replacement.",
        "retrieval",
    ),
    Ablation(
        "without_visual_deletion_chain_rescue",
        "Without visual-deletion chains",
        "Remove exact candidates requiring visual confusions plus a missing character.",
        "retrieval",
    ),
    Ablation(
        "without_all_multi_step_chain_rescue",
        "Without all multi-step chains",
        "Remove every Algorithm 5 multi-operation variant and exact-chain retrieval path.",
        "retrieval",
    ),
    Ablation(
        "without_exact_chain_score_augmentation",
        "Without exact-chain score augmentation",
        "Do not raise an existing candidate score from exact multi-step-chain evidence.",
        "scoring",
    ),
    Ablation(
        "without_nearest_rerankers",
        "Without nearest-candidate rerankers",
        "Disable all bounded-nearest promotion variants after initial ranking.",
        "reranker",
    ),
    Ablation(
        "without_weighted_edge_rerankers",
        "Without weighted-edge rerankers",
        "Disable weighted-distance and prefix/suffix tie corrections.",
        "reranker",
    ),
    Ablation(
        "without_exact_key_rerankers",
        "Without exact-key rerankers",
        "Disable exact transformed-key corrections for ligatures, transpositions, keyboard errors, and phonetics.",
        "reranker",
    ),
    Ablation(
        "without_chain_rerankers",
        "Without multi-step-chain rerankers",
        "Disable every exact-chain promotion after candidate retrieval.",
        "reranker",
    ),
    Ablation(
        "without_character_evidence_rerankers",
        "Without character-evidence rerankers",
        "Disable Pareto, positional, visual, skeleton, shifted-edge, and two-sided-anchor corrections.",
        "reranker",
    ),
    Ablation(
        "without_candidate_pool_head_rerankers",
        "Without candidate-pool/head rerankers",
        "Disable validated-head, short-visible-head, ordered-head, and candidate-pool head corrections.",
        "reranker",
    ),
    Ablation(
        "without_in_place_chain_score_tuning",
        "Without in-place chain score tuning",
        "Keep chain retrieval but prevent it from replacing an existing candidate score.",
        "scoring",
    ),
)

FLAG_NAMES = (
    "ENABLE_EXACT_CHAIN_EXISTING_AUGMENTATION",
    "ENABLE_VISUAL_VISUAL_DELETION_CHAIN",
    "ENABLE_VISUAL_PHONETIC_IN_PLACE_SCORE",
    "ENABLE_VISUAL_PHONETIC_SCORE_TUNING",
    "ENABLE_LIGATURE_VOWEL_IN_PLACE_SCORE",
    "ENABLE_LIGATURE_VOWEL_TRANSPOSE_IN_PLACE_SCORE",
    "ENABLE_TRANSPOSE_VOWEL_DELETE_IN_PLACE_SCORE",
    "ENABLE_TRANSPOSE_VOWEL_DELETE_SCORE_TUNING",
    "ENABLE_KEYBOARD_VOWEL_DELETE_IN_PLACE_SCORE",
    "ENABLE_KEYBOARD_VOWEL_DELETE_SCORE_TUNING",
    "ENABLE_TRANSPOSITION_DELETION_EXACT_CHAIN",
    "ENABLE_SHORT_QUERY_RESCUE",
    "ENABLE_UNIQUE_NEAREST_RERANK",
    "ENABLE_CONTAINED_NEAREST_RERANK",
    "ENABLE_PRESERVED_TOP_DOMINANT_NEAREST_RERANK",
    "ENABLE_PRESERVED_TOP_HIGHER_SCORE_NEAREST_RERANK",
    "ENABLE_EXACT_LIGATURE_NEAREST_RERANK",
    "ENABLE_EXACT_LIGATURE_RANK_EXTENSION_RERANK",
    "ENABLE_EXACT_PHONETIC_REWRITE_RERANK",
    "ENABLE_WEIGHTED_EDGE_TIE_RERANK",
    "ENABLE_WEIGHTED_EDGE_ADVANTAGE_RERANK",
    "ENABLE_WEIGHTED_EXACT_KEY_TIE_RERANK",
    "ENABLE_EXACT_TRANSPOSITION_TIE_RERANK",
    "ENABLE_EXACT_TRANSPOSITION_DUAL_EXTENSION_RERANK",
    "ENABLE_EXACT_KEYBOARD_KEY_TIE_RERANK",
    "ENABLE_EXACT_KEYBOARD_WEIGHTED_EXTENSION_RERANK",
    "ENABLE_EXACT_VISUAL_EDGE_TIE_RERANK",
    "ENABLE_GUARDED_TOP_SCORE_DOMINANT_CHAIN_RERANK",
    "ENABLE_SCORE_DOMINANT_CHAIN_RELEASE_RERANK",
    "ENABLE_STUTTER_PREFIX_RERANK",
    "ENABLE_STRICT_FULL_NAME_RERANK",
    "ENABLE_STRICT_FULL_NAME_EVIDENCE_GUARD",
    "ENABLE_EXACT_KEY_PARETO_TIE_RERANK",
    "ENABLE_PHONETIC_POSITION_TIE_RERANK",
    "ENABLE_SHIFTED_EDGE_AGREEMENT_RERANK",
    "ENABLE_VISUAL_DISTANCE_TIE_RERANK",
    "ENABLE_SKELETON_POSITION_TIE_RERANK",
    "ENABLE_LIGATURE_VOWEL_TRANSPOSE_RERANK",
    "ENABLE_LIGATURE_VOWEL_TRANSPOSE_EXTENSION_RERANK",
    "ENABLE_LIGATURE_VOWEL_RERANK",
    "ENABLE_LIGATURE_VOWEL_DISTANCE_EXTENSION_RERANK",
    "ENABLE_LIGATURE_VOWEL_EDGE_EXTENSION_RERANK",
    "ENABLE_LIGATURE_VOWEL_MULTI_CHAIN_EXTENSION_RERANK",
    "ENABLE_VISUAL_PHONETIC_CHAIN_RERANK",
    "ENABLE_VISUAL_PHONETIC_EXACT_KEY_EXTENSION_RERANK",
    "ENABLE_VISUAL_PHONETIC_DUAL_EXTENSION_RERANK",
    "ENABLE_KEYBOARD_VOWEL_DELETE_RERANK",
    "ENABLE_KEYBOARD_EXACT_KEY_RERANK",
    "ENABLE_VISUAL_VISUAL_DELETE_RERANK",
    "ENABLE_VISUAL_MULTI_CHAIN_RERANK",
    "ENABLE_TRANSPOSITION_DELETE_RERANK",
    "ENABLE_TRANSPOSE_VOWEL_DELETE_RERANK",
    "ENABLE_VOWEL_PHONETIC_DELETE_RERANK",
    "ENABLE_VOWEL_PHONETIC_MULTI_CHAIN_EXTENSION_RERANK",
)

FLAG_ABLATIONS = tuple(
    Ablation(
        f"without_flag__{flag.removeprefix('ENABLE_').lower()}",
        f"Flag off: {flag.removeprefix('ENABLE_').lower().replace('_', ' ')}",
        f"Set only {flag}=False; every other Algorithm 5 switch remains enabled.",
        "atomic_flag",
    )
    for flag in FLAG_NAMES
)

ABLATIONS = (*BASE_ABLATIONS, *FLAG_ABLATIONS)
ABLATION_BY_NAME = {item.name: item for item in ABLATIONS}

NEAREST_FLAGS = (
    "ENABLE_UNIQUE_NEAREST_RERANK",
    "ENABLE_CONTAINED_NEAREST_RERANK",
    "ENABLE_PRESERVED_TOP_DOMINANT_NEAREST_RERANK",
    "ENABLE_PRESERVED_TOP_HIGHER_SCORE_NEAREST_RERANK",
    "ENABLE_EXACT_LIGATURE_NEAREST_RERANK",
)
WEIGHTED_EDGE_FLAGS = (
    "ENABLE_WEIGHTED_EDGE_TIE_RERANK",
    "ENABLE_WEIGHTED_EDGE_ADVANTAGE_RERANK",
)
EXACT_KEY_FLAGS = (
    "ENABLE_EXACT_LIGATURE_NEAREST_RERANK",
    "ENABLE_EXACT_LIGATURE_RANK_EXTENSION_RERANK",
    "ENABLE_EXACT_PHONETIC_REWRITE_RERANK",
    "ENABLE_WEIGHTED_EXACT_KEY_TIE_RERANK",
    "ENABLE_EXACT_TRANSPOSITION_TIE_RERANK",
    "ENABLE_EXACT_TRANSPOSITION_DUAL_EXTENSION_RERANK",
    "ENABLE_EXACT_KEYBOARD_KEY_TIE_RERANK",
    "ENABLE_EXACT_KEYBOARD_WEIGHTED_EXTENSION_RERANK",
    "ENABLE_EXACT_VISUAL_EDGE_TIE_RERANK",
    "ENABLE_STUTTER_PREFIX_RERANK",
)
CHAIN_RERANK_FLAGS = tuple(
    flag
    for flag in FLAG_NAMES
    if any(
        token in flag
        for token in (
            "LIGATURE_VOWEL",
            "VISUAL_PHONETIC",
            "KEYBOARD_VOWEL",
            "VISUAL_VISUAL",
            "VISUAL_MULTI_CHAIN",
            "TRANSPOSITION_DELETE_RERANK",
            "TRANSPOSE_VOWEL",
            "VOWEL_PHONETIC",
        )
    )
    and "RERANK" in flag
)
CHARACTER_EVIDENCE_FLAGS = (
    "ENABLE_EXACT_KEY_PARETO_TIE_RERANK",
    "ENABLE_PHONETIC_POSITION_TIE_RERANK",
    "ENABLE_SHIFTED_EDGE_AGREEMENT_RERANK",
    "ENABLE_VISUAL_DISTANCE_TIE_RERANK",
    "ENABLE_SKELETON_POSITION_TIE_RERANK",
)
IN_PLACE_FLAGS = tuple(
    flag
    for flag in FLAG_NAMES
    if "IN_PLACE_SCORE" in flag or "SCORE_TUNING" in flag
)

SYNTHETIC_CONFIRMATION = (
    "full_algorithm_5",
    "without_external_retriever",
    "without_context_cleanup",
    "without_rescue_layer",
    "without_raw_edit_similarity",
    "without_weighted_edit_similarity",
    "without_ngram_signal",
    "without_phonetic_signal",
    "without_skeleton_signal",
    "without_variant_head_rescue",
    "without_all_multi_step_chain_rescue",
    "without_all_reranking",
    "without_safety_clarification_gate",
)

RESULT_FIELDS = (
    "evaluation_version",
    "dataset",
    "case_id",
    "algorithm",
    "algorithm_name",
    "ablation_level",
    "input",
    "input_compact",
    "expected_family_keys",
    "expected_family_name",
    "split",
    "category",
    "error_type",
    "operation_family",
    "edit_distance",
    "normalized_distance",
    "distance_band",
    "query_length_band",
    "shared_bigram_band",
    "response_status",
    "decision_type",
    "needs_clarification",
    "unsafe_confident_top1",
    "first_relevant_rank",
    "hit_at_1",
    "hit_at_5",
    "hit_at_10",
    "hit_at_20",
    "reciprocal_rank_at_20",
    "no_result",
    "candidate_count",
    "latency_ms",
    "top_1",
    "top_20",
)

_WORKER_MODULE: Any = None
_WORKER_CATALOG: Any = None
_WORKER_CASES: Sequence[competitors.SearchCase] = ()
_WORKER_ARGS: argparse.Namespace | None = None
_WORKER_PREPARATION_MS = 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=("ocr", "synthetic"), required=True)
    parser.add_argument(
        "--profile",
        choices=("components", "atomic", "all", "synthetic_confirmation"),
        default="components",
    )
    parser.add_argument("--ablations", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--list", action="store_true")
    return parser.parse_args()


def load_algorithm_5() -> tuple[Any, Any, float]:
    started = time.perf_counter()
    module = existing_evaluator.load_module(
        ALGORITHM_PATH,
        "benchmark_04_algorithm_5_ablation",
    )
    catalog = module.prepare_catalog()
    return module, catalog, (time.perf_counter() - started) * 1000


def selected_ablations(args: argparse.Namespace) -> list[Ablation]:
    if args.ablations:
        names = [value.strip() for value in args.ablations.split(",") if value.strip()]
    elif args.profile == "components":
        names = [item.name for item in BASE_ABLATIONS]
    elif args.profile == "atomic":
        names = ["full_algorithm_5", *[item.name for item in FLAG_ABLATIONS]]
    elif args.profile == "synthetic_confirmation":
        names = list(SYNTHETIC_CONFIRMATION)
    else:
        names = [item.name for item in ABLATIONS]
    unknown = sorted(set(names) - set(ABLATION_BY_NAME))
    if unknown:
        raise ValueError(f"unknown ablations: {unknown}")
    return [ABLATION_BY_NAME[name] for name in names]


def empty_response(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"status": "no_match", "candidate_count": 0, "results": []}


def identity_ranked(ranked: list[Any], *_args: Any, **_kwargs: Any) -> list[Any]:
    return ranked


def plain_rank(module: Any) -> Callable[..., list[Any]]:
    def rank(
        candidates: list[Any],
        compact: str,
        *,
        brand_like: bool,
        _handle_multi_step_boost: bool = True,
    ) -> list[Any]:
        del compact, brand_like, _handle_multi_step_boost
        return sorted(
            candidates,
            key=lambda item: (-item.score, module.clarification_sort(item), item.name),
        )

    return rank


def selective_edit_similarity(
    original: Callable[..., float],
    *,
    remove_weighted: bool,
) -> Callable[..., float]:
    def similarity(
        left: str,
        right: str,
        *,
        weighted: bool,
        ocr_visual: bool = False,
    ) -> float:
        if weighted == remove_weighted:
            return 0.0
        return original(
            left,
            right,
            weighted=weighted,
            ocr_visual=ocr_visual,
        )

    return similarity


def merge_without_agreement(module: Any) -> Callable[..., dict[str, Any]]:
    original = module.merge_candidates

    def merge(*args: Any, **kwargs: Any) -> dict[str, Any]:
        candidates = original(*args, **kwargs)
        for candidate in candidates.values():
            if "algorithm_2_context_agreement" in candidate.reasons:
                candidate.score -= 0.06
                candidate.reasons.remove("algorithm_2_context_agreement")
            if "algorithm_2_rescue_agreement" in candidate.reasons:
                candidate.score -= 0.08
                candidate.reasons.remove("algorithm_2_rescue_agreement")
        return candidates

    return merge


def disable_flags(stack: ExitStack, module: Any, names: Sequence[str]) -> None:
    for name in names:
        stack.enter_context(patch.object(module, name, False))


def disable_chain_retrieval(stack: ExitStack, module: Any) -> None:
    list_functions = (
        "mixed_ligature_transposition_variants",
        "adjacent_transposition_variants",
        "keyboard_neighbor_variants",
    )
    set_functions = (
        "visual_phonetic_chain_family_ids",
        "visual_visual_deletion_family_ids",
        "transposition_deletion_exact_family_ids",
        "ligature_vowel_chain_family_ids",
        "ligature_vowel_transposition_family_ids",
        "transpose_vowel_deletion_family_ids",
        "vowel_phonetic_deletion_family_ids",
        "keyboard_vowel_deletion_family_ids",
        "short_ocr_combined_family_ids",
    )
    for name in list_functions:
        stack.enter_context(patch.object(module, name, lambda *_args: []))
    for name in set_functions:
        stack.enter_context(patch.object(module, name, lambda *_args: set()))


def disable_post_rankers(stack: ExitStack, module: Any) -> None:
    disable_flags(
        stack,
        module,
        [name for name in FLAG_NAMES if "RERANK" in name],
    )
    for name in (
        "apply_validated_family_head_evidence",
        "promote_two_sided_anchor_tie_candidate",
        "surface_short_visible_head_candidates",
        "promote_candidate_pool_bounded_head_candidate",
        "promote_pareto_character_evidence_candidate",
    ):
        stack.enter_context(patch.object(module, name, identity_ranked))

    def ordered_head_identity(
        _index: Any,
        _candidates: dict[str, Any],
        ranked: list[Any],
        _compact: str,
        _limit: int,
    ) -> list[Any]:
        return ranked

    stack.enter_context(
        patch.object(
            module,
            "surface_ordered_character_head_candidate",
            ordered_head_identity,
        )
    )


@contextmanager
def apply_ablation(
    module: Any,
    catalog: Any,
    name: str,
) -> Iterator[None]:
    with ExitStack() as stack:
        if name == "full_algorithm_5":
            yield
            return
        if name.startswith("without_flag__"):
            flag = "ENABLE_" + name.removeprefix("without_flag__").upper()
            stack.enter_context(patch.object(module, flag, False))
        elif name == "without_external_retriever":
            stack.enter_context(
                patch.object(catalog.external_module, "search_catalog", empty_response)
            )
        elif name == "without_context_cleanup":
            stack.enter_context(
                patch.object(module, "should_run_context_search", lambda *_args: False)
            )
        elif name == "without_rescue_layer":
            stack.enter_context(patch.object(module, "rescue_search", lambda *_args, **_kwargs: []))
        elif name == "without_raw_edit_similarity":
            stack.enter_context(
                patch.object(
                    module,
                    "normalized_edit_similarity",
                    selective_edit_similarity(
                        module.normalized_edit_similarity,
                        remove_weighted=False,
                    ),
                )
            )
        elif name == "without_weighted_edit_similarity":
            stack.enter_context(
                patch.object(
                    module,
                    "normalized_edit_similarity",
                    selective_edit_similarity(
                        module.normalized_edit_similarity,
                        remove_weighted=True,
                    ),
                )
            )
        elif name == "without_prefix_signal":
            stack.enter_context(patch.object(module, "prefix_score", lambda *_args: 0.0))
        elif name == "without_suffix_signal":
            stack.enter_context(patch.object(module, "suffix_score", lambda *_args: 0.0))
        elif name == "without_ngram_signal":
            stack.enter_context(patch.object(module, "char_ngrams", lambda *_args: set()))
        elif name == "without_phonetic_signal":
            stack.enter_context(
                patch.object(module.current_eval, "drug_phonetic_key", lambda *_args: "")
            )
        elif name == "without_skeleton_signal":
            stack.enter_context(
                patch.object(module.current_eval, "skeleton", lambda *_args: "")
            )
        elif name == "without_subsequence_signal":
            stack.enter_context(
                patch.object(module, "subsequence_score", lambda *_args: 0.0)
            )
        elif name == "without_positional_signal":
            stack.enter_context(
                patch.object(module, "same_position_score", lambda *_args: 0.0)
            )
        elif name == "without_length_coverage_signal":
            stack.enter_context(
                patch.object(module, "length_coverage", lambda *_args: 0.0)
            )
        elif name == "without_delete_key_retrieval":
            stack.enter_context(patch.object(module, "delete_keys", lambda *_args: set()))
        elif name == "without_short_edge_retrieval":
            stack.enter_context(
                patch.object(module, "short_edge_family_ids", lambda *_args: set())
            )
        elif name == "without_confusable_first_character_expansion":
            stack.enter_context(
                patch.object(module, "first_char_variants", lambda *_args: set())
            )
            stack.enter_context(
                patch.object(module, "first_chars_confusable", lambda *_args: False)
            )
        elif name == "without_length_bucket_scan":
            stack.enter_context(
                patch.object(module, "should_length_scan", lambda *_args: False)
            )
        elif name == "without_variant_head_rescue":
            stack.enter_context(
                patch.object(module, "should_run_head_rescue", lambda *_args: False)
            )
            stack.enter_context(
                patch.object(module, "variant_head_family_ids", lambda *_args: set())
            )
        elif name == "without_weighted_confusion_cost":
            stack.enter_context(
                patch.object(
                    module,
                    "substitution_cost",
                    lambda left, right, *, ocr_visual=False: (
                        0.0 if left == right else 1.0
                    ),
                )
            )
        elif name == "without_retrieval_agreement_bonus":
            stack.enter_context(
                patch.object(module, "merge_candidates", merge_without_agreement(module))
            )
        elif name == "without_strict_full_name_correction":
            stack.enter_context(
                patch.object(
                    module,
                    "promote_strictly_closer_full_name",
                    identity_ranked,
                )
            )
            stack.enter_context(patch.object(module, "ENABLE_STRICT_FULL_NAME_RERANK", False))
        elif name == "without_all_reranking":
            stack.enter_context(patch.object(module, "rank_candidates", plain_rank(module)))
            disable_post_rankers(stack, module)
        elif name == "without_safety_clarification_gate":
            stack.enter_context(
                patch.object(module, "needs_clarification", lambda *_args: False)
            )
        elif name == "without_short_query_rescue":
            stack.enter_context(patch.object(module, "ENABLE_SHORT_QUERY_RESCUE", False))
        elif name == "without_nearest_fallback":
            stack.enter_context(
                patch.object(module, "should_run_nearest_fallback", lambda *_args: False)
            )
            stack.enter_context(
                patch.object(module, "bounded_nearest_family_ids", lambda *_args: set())
            )
        elif name == "without_evidence_variant_rescue":
            stack.enter_context(
                patch.object(
                    module,
                    "should_run_evidence_variant_rescue",
                    lambda *_args: False,
                )
            )
            stack.enter_context(
                patch.object(module, "evidence_query_variants", lambda *_args: [])
            )
        elif name == "without_short_visible_head_rescue":
            stack.enter_context(
                patch.object(module, "short_visible_head_family_ids", lambda *_args: set())
            )
        elif name == "without_short_frame_rescue":
            stack.enter_context(
                patch.object(module, "short_frame_family_ids", lambda *_args: set())
            )
            stack.enter_context(
                patch.object(module, "short_two_deletion_family_ids", lambda *_args: set())
            )
        elif name == "without_keyboard_variant_rescue":
            stack.enter_context(
                patch.object(module, "keyboard_neighbor_variants", lambda *_args: [])
            )
            stack.enter_context(
                patch.object(module, "short_keyboard_exact_family_ids", lambda *_args: set())
            )
            stack.enter_context(
                patch.object(module, "keyboard_vowel_deletion_family_ids", lambda *_args: set())
            )
            disable_flags(
                stack,
                module,
                [flag for flag in FLAG_NAMES if "KEYBOARD" in flag],
            )
        elif name == "without_ligature_variant_rescue":
            for function_name, empty in (
                ("exact_short_ligature_variants", []),
                ("single_ligature_variants", set()),
                ("directional_visual_ligature_variants", set()),
                ("mixed_ligature_transposition_variants", []),
                ("ligature_vowel_chain_family_ids", set()),
                ("ligature_vowel_transposition_family_ids", set()),
            ):
                stack.enter_context(
                    patch.object(
                        module,
                        function_name,
                        lambda *_args, _empty=empty: _empty.copy(),
                    )
                )
            disable_flags(
                stack,
                module,
                [flag for flag in FLAG_NAMES if "LIGATURE" in flag],
            )
        elif name == "without_transposition_variant_rescue":
            stack.enter_context(
                patch.object(module, "adjacent_transposition_variants", lambda *_args: [])
            )
            stack.enter_context(
                patch.object(
                    module,
                    "transposition_deletion_exact_family_ids",
                    lambda *_args: set(),
                )
            )
            stack.enter_context(
                patch.object(
                    module,
                    "transpose_vowel_deletion_family_ids",
                    lambda *_args: set(),
                )
            )
            disable_flags(
                stack,
                module,
                [
                    flag
                    for flag in FLAG_NAMES
                    if "TRANSPOSITION" in flag or "TRANSPOSE" in flag
                ],
            )
        elif name == "without_visual_phonetic_chain_rescue":
            stack.enter_context(
                patch.object(
                    module,
                    "visual_phonetic_chain_family_ids",
                    lambda *_args: set(),
                )
            )
            disable_flags(
                stack,
                module,
                [flag for flag in FLAG_NAMES if "VISUAL_PHONETIC" in flag],
            )
        elif name == "without_visual_deletion_chain_rescue":
            stack.enter_context(
                patch.object(
                    module,
                    "visual_visual_deletion_family_ids",
                    lambda *_args: set(),
                )
            )
            disable_flags(
                stack,
                module,
                [
                    flag
                    for flag in FLAG_NAMES
                    if "VISUAL_VISUAL" in flag or "VISUAL_MULTI_CHAIN" in flag
                ],
            )
        elif name == "without_all_multi_step_chain_rescue":
            disable_chain_retrieval(stack, module)
            disable_flags(
                stack,
                module,
                [
                    flag
                    for flag in FLAG_NAMES
                    if "CHAIN" in flag
                    or "TRANSPOSITION_DELETE" in flag
                    or "TRANSPOSE_VOWEL" in flag
                    or "KEYBOARD_VOWEL" in flag
                ],
            )
        elif name == "without_exact_chain_score_augmentation":
            stack.enter_context(
                patch.object(module, "ENABLE_EXACT_CHAIN_EXISTING_AUGMENTATION", False)
            )
        elif name == "without_nearest_rerankers":
            disable_flags(stack, module, NEAREST_FLAGS)
        elif name == "without_weighted_edge_rerankers":
            disable_flags(stack, module, WEIGHTED_EDGE_FLAGS)
        elif name == "without_exact_key_rerankers":
            disable_flags(stack, module, EXACT_KEY_FLAGS)
        elif name == "without_chain_rerankers":
            disable_flags(stack, module, CHAIN_RERANK_FLAGS)
        elif name == "without_character_evidence_rerankers":
            disable_flags(stack, module, CHARACTER_EVIDENCE_FLAGS)
            stack.enter_context(
                patch.object(
                    module,
                    "promote_two_sided_anchor_tie_candidate",
                    identity_ranked,
                )
            )
            stack.enter_context(
                patch.object(
                    module,
                    "promote_pareto_character_evidence_candidate",
                    identity_ranked,
                )
            )
        elif name == "without_candidate_pool_head_rerankers":
            for function_name in (
                "apply_validated_family_head_evidence",
                "surface_short_visible_head_candidates",
                "promote_candidate_pool_bounded_head_candidate",
            ):
                stack.enter_context(
                    patch.object(module, function_name, identity_ranked)
                )

            def ordered_head_identity(
                _index: Any,
                _candidates: dict[str, Any],
                ranked: list[Any],
                _compact: str,
                _limit: int,
            ) -> list[Any]:
                return ranked

            stack.enter_context(
                patch.object(
                    module,
                    "surface_ordered_character_head_candidate",
                    ordered_head_identity,
                )
            )
        elif name == "without_in_place_chain_score_tuning":
            disable_flags(stack, module, IN_PLACE_FLAGS)
        else:
            raise ValueError(f"unknown ablation: {name}")
        yield


def result_name(item: dict[str, Any]) -> str:
    return str(
        item.get("name")
        or item.get("candidate_canonical_name")
        or item.get("canonical_name")
        or item.get("commercial_name")
        or ""
    ).strip()


def evaluate_case(
    case: competitors.SearchCase,
    ablation: Ablation,
    runner: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    started = time.perf_counter()
    output = runner(case.input)
    latency_ms = (time.perf_counter() - started) * 1000
    results = list(output.get("results") or [])[:TOP_K]
    names = [result_name(item) for item in results]
    expected = set(case.expected_family_keys)
    ranks = [
        rank
        for rank, name in enumerate(names, 1)
        if current_app.compact_key(name) in expected
    ]
    rank = ranks[0] if ranks else 999
    status = str(output.get("status") or "")
    top_clarifies = bool(results and results[0].get("needs_clarification"))
    confident = status in {"high_confidence", "medium_confidence"} and not top_clarifies
    return {
        "evaluation_version": EVALUATION_VERSION,
        "dataset": case.dataset,
        "case_id": case.case_id,
        "algorithm": ablation.name,
        "algorithm_name": ablation.display_name,
        "ablation_level": ablation.level,
        "input": case.input,
        "input_compact": case.input_compact,
        "expected_family_keys": ";".join(case.expected_family_keys),
        "expected_family_name": case.expected_family_name,
        "split": case.split,
        "category": case.category,
        "error_type": case.error_type,
        "operation_family": case.operation_family,
        "edit_distance": case.edit_distance,
        "normalized_distance": round(case.normalized_distance, 8),
        "distance_band": case.distance_band,
        "query_length_band": case.query_length_band,
        "shared_bigram_band": case.shared_bigram_band,
        "response_status": status,
        "decision_type": str(output.get("decision_type") or status),
        "needs_clarification": int(bool(results) and (top_clarifies or not confident)),
        "unsafe_confident_top1": int(bool(results) and confident and rank != 1),
        "first_relevant_rank": rank,
        "hit_at_1": int(rank <= 1),
        "hit_at_5": int(rank <= 5),
        "hit_at_10": int(rank <= 10),
        "hit_at_20": int(rank <= 20),
        "reciprocal_rank_at_20": round(1 / rank, 8) if rank <= 20 else 0.0,
        "no_result": int(not results),
        "candidate_count": int(output.get("candidate_count") or len(results)),
        "latency_ms": round(latency_ms, 6),
        "top_1": names[0] if names else "",
        "top_20": ";".join(names),
    }


def artifact_path(root: Path, dataset: str, name: str) -> Path:
    return root / f"a5_ablation_{dataset}" / f"{name}.csv.gz"


def expected_row_count(path: Path, count: int) -> bool:
    if not path.exists():
        return False
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return sum(1 for _ in handle) - 1 == count


def write_ablation(
    path: Path,
    rows: Sequence[dict[str, Any]],
    ablation: Ablation,
    preparation_ms: float,
    wall_ms: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    latencies = [float(row["latency_ms"]) for row in rows]
    metadata = {
        "evaluation_version": EVALUATION_VERSION,
        "algorithm": ablation.name,
        "algorithm_name": ablation.display_name,
        "ablation_level": ablation.level,
        "definition": ablation.definition,
        "cases": len(rows),
        "preparation_ms": preparation_ms,
        "wall_ms": wall_ms,
        "mean_latency_ms": statistics.fmean(latencies),
        "median_latency_ms": statistics.median(latencies),
    }
    path.with_suffix(".metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )


def write_inventory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("name", "display_name", "definition", "level"),
        )
        writer.writeheader()
        writer.writerows(
            {
                "name": item.name,
                "display_name": item.display_name,
                "definition": item.definition,
                "level": item.level,
            }
            for item in ABLATIONS
        )


def write_metrics(args: argparse.Namespace) -> None:
    rows: list[dict[str, Any]] = []
    for dataset in ("ocr_464", "synthetic_66257"):
        root = args.artifacts_dir / f"a5_ablation_{dataset}"
        if not root.exists():
            continue
        for path in sorted(root.glob("*.csv.gz")):
            rows.extend(competitors.aggregate_result_file(path))
    if not rows:
        return
    args.results_dir.mkdir(parents=True, exist_ok=True)
    output = args.results_dir / "a5_ablation_metrics.csv"
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows):,} Algorithm 5 ablation metric rows to {output}")


def run_one_ablation(ablation: Ablation) -> dict[str, Any]:
    if _WORKER_ARGS is None:
        raise RuntimeError("ablation worker was not initialized")
    output = artifact_path(
        _WORKER_ARGS.artifacts_dir,
        _WORKER_CASES[0].dataset,
        ablation.name,
    )
    if not _WORKER_ARGS.force and expected_row_count(output, len(_WORKER_CASES)):
        return {
            "name": ablation.name,
            "cached": True,
            "cases": len(_WORKER_CASES),
        }

    def run(query: str) -> dict[str, Any]:
        return _WORKER_MODULE.search_catalog(_WORKER_CATALOG, query, TOP_K)

    started = time.perf_counter()
    with apply_ablation(_WORKER_MODULE, _WORKER_CATALOG, ablation.name):
        rows = [
            evaluate_case(case, ablation, run)
            for case in _WORKER_CASES
        ]
    wall_ms = (time.perf_counter() - started) * 1000
    write_ablation(
        output,
        rows,
        ablation,
        _WORKER_PREPARATION_MS,
        wall_ms,
    )
    return {
        "name": ablation.name,
        "cached": False,
        "cases": len(rows),
        "hit_at_1": sum(row["hit_at_1"] for row in rows) / len(rows),
        "hit_at_20": sum(row["hit_at_20"] for row in rows) / len(rows),
        "wall_ms": wall_ms,
    }


def initialize_worker_state(
    module: Any,
    catalog: Any,
    cases: Sequence[competitors.SearchCase],
    args: argparse.Namespace,
    preparation_ms: float,
) -> None:
    global _WORKER_MODULE
    global _WORKER_CATALOG
    global _WORKER_CASES
    global _WORKER_ARGS
    global _WORKER_PREPARATION_MS
    _WORKER_MODULE = module
    _WORKER_CATALOG = catalog
    _WORKER_CASES = cases
    _WORKER_ARGS = args
    _WORKER_PREPARATION_MS = preparation_ms


def print_result(
    result: dict[str, Any],
    position: int,
    count: int,
) -> None:
    if result["cached"]:
        print(
            f"[{position}/{count}] {result['name']}: cached",
            flush=True,
        )
        return
    print(
        f"[{position}/{count}] {result['name']}: "
        f"H@1={result['hit_at_1']:.4%}, "
        f"H@20={result['hit_at_20']:.4%}, "
        f"elapsed={result['wall_ms'] / 1000:.1f}s",
        flush=True,
    )


def main() -> None:
    args = parse_args()
    write_inventory(args.results_dir / "a5_ablation_inventory.csv")
    selected = selected_ablations(args)
    if args.list:
        for item in selected:
            print(f"{item.name}: {item.definition}")
        return
    cases = (
        competitors.load_ocr_cases(competitors.DEFAULT_OCR_CASES, args.limit)
        if args.dataset == "ocr"
        else competitors.load_synthetic_cases(
            competitors.DEFAULT_SYNTHETIC_CASES,
            args.limit,
        )
    )
    module, catalog, preparation_ms = load_algorithm_5()
    initialize_worker_state(module, catalog, cases, args, preparation_ms)
    if args.jobs > 1:
        context = mp.get_context("fork")
        with context.Pool(processes=args.jobs) as pool:
            for position, result in enumerate(
                pool.imap_unordered(run_one_ablation, selected),
                1,
            ):
                print_result(result, position, len(selected))
    else:
        for position, ablation in enumerate(selected, 1):
            print_result(
                run_one_ablation(ablation),
                position,
                len(selected),
            )
    write_metrics(args)


if __name__ == "__main__":
    main()

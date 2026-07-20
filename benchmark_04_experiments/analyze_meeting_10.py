#!/usr/bin/env python3
"""Build the Meeting 10 OCR-error, fairness, and equal-distance analyses."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cache")

import matplotlib
matplotlib.use("Agg", force=True)

import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt
from matplotlib.ticker import PercentFormatter
from scipy.stats import binomtest, spearmanr
from sklearn.metrics import confusion_matrix

import run_retrieval_experiments as experiments


BENCHMARK_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BENCHMARK_ROOT.parent
DEFAULT_CASES = (
    PROJECT_ROOT
    / "benchmark_03_ocr/artifacts/04_model_predictions/search_cases.csv"
)
DEFAULT_RESULTS = (
    PROJECT_ROOT
    / "benchmark_03_ocr/artifacts/04_model_predictions/algorithm_4_results.csv"
)
DEFAULT_SYNTHETIC_RESULTS = (
    PROJECT_ROOT
    / "benchmark_02_synthetic/artifacts/01_full_benchmark/algorithm_4_cases.csv"
)
RESULTS_DIR = BENCHMARK_ROOT / "results/04_meeting_10"
ARTIFACTS_DIR = BENCHMARK_ROOT / "artifacts/04_meeting_10"
FIGURES_DIR = RESULTS_DIR / "figures"
SYNTHETIC_ROOT = PROJECT_ROOT / "benchmark_02_synthetic"
SYNTHETIC_CASE_PATHS = {
    number: SYNTHETIC_ROOT
    / f"artifacts/01_full_benchmark/algorithm_{number}_cases.csv"
    for number in range(1, 5)
}
SYNTHETIC_CATEGORY_METRICS = (
    SYNTHETIC_ROOT / "results/01_full_benchmark/metrics_by_category.csv"
)
CASE_RESULTS_PATH = BENCHMARK_ROOT / "artifacts/case_results.csv"
EXPERIMENT_METRICS_PATH = BENCHMARK_ROOT / "results/metrics.csv"
PAIRED_COMPARISONS_PATH = BENCHMARK_ROOT / "results/paired_comparisons.csv"
PHARMACIST_ASSIGNMENTS_PATH = (
    BENCHMARK_ROOT / "artifacts/03_pharmacist_study/assignments.csv"
)

RANDOM_SEED = 20260719
BOOTSTRAP_ITERATIONS = 10_000

BLUE = "#4477AA"
CYAN = "#66CCEE"
GREEN = "#228833"
YELLOW = "#CCBB44"
ORANGE = "#EE7733"
RED = "#CC6677"
PURPLE = "#AA3377"
GRAY = "#66717D"
LIGHT_GRAY = "#E5E7EB"

ALGORITHM_LABELS = {
    "baseline_exact_prefix": "Exact or prefix match",
    "baseline_levenshtein": "Exhaustive Levenshtein",
    "baseline_jaro_winkler": "Jaro-Winkler",
    "baseline_char_3gram_tfidf": "Character 3-gram TF-IDF",
    "baseline_rapidfuzz_token_ratio": "RapidFuzz token ratio",
    "baseline_phonetic": "Phonetic baseline",
    "algorithm_1_current_app": "Algorithm 1, current app",
    "algorithm_2_external_fast": "Algorithm 2, external fast",
    "algorithm_3_rank_fusion": "Algorithm 3, rank fusion",
    "algorithm_4_family_rescue": "Algorithm 4, family rescue",
    "full_algorithm_4": "Complete Algorithm 4",
}

RETRIEVAL_ORDER = [
    "baseline_exact_prefix",
    "baseline_levenshtein",
    "baseline_jaro_winkler",
    "baseline_char_3gram_tfidf",
    "baseline_rapidfuzz_token_ratio",
    "baseline_phonetic",
    "algorithm_1_current_app",
    "algorithm_2_external_fast",
    "algorithm_3_rank_fusion",
    "algorithm_4_family_rescue",
]

OPERATION_ORDER = [
    "Extra characters only",
    "Missing characters only",
    "Replacements only",
    "Mixed operations",
]

BIGRAM_ORDER = [
    "No shared bigram",
    "One shared bigram",
    "Two or more shared bigrams",
]

ABLATION_LABELS = {
    "without_external_retriever": "External retriever",
    "without_context_cleanup": "Context cleanup",
    "without_rescue_layer": "Family rescue layer",
    "without_raw_edit_similarity": "Raw edit similarity",
    "without_weighted_edit_similarity": "Weighted edit similarity",
    "without_prefix_signal": "Prefix evidence",
    "without_suffix_signal": "Suffix evidence",
    "without_ngram_signal": "Character n-grams",
    "without_phonetic_signal": "Phonetic evidence",
    "without_skeleton_signal": "Consonant skeleton",
    "without_subsequence_signal": "Subsequence evidence",
    "without_positional_signal": "Position evidence",
    "without_length_coverage_signal": "Length coverage",
    "without_delete_key_retrieval": "Delete-key retrieval",
    "without_short_edge_retrieval": "Short-edge retrieval",
    "without_confusable_first_character_expansion": "First-character expansion",
    "without_length_bucket_scan": "Compatible-length scan",
    "without_variant_head_rescue": "Family-head rescue",
    "without_weighted_confusion_cost": "Weighted confusion costs",
    "without_retrieval_agreement_bonus": "Retriever agreement",
    "without_strict_full_name_correction": "Strict full-name correction",
    "without_conservative_reranker": "Conservative reranker",
    "without_safety_clarification_gate": "Safety clarification gate",
}

COHORT_LABELS = {
    "normalized_exact_match": "Exact after normalization",
    "standard_ocr_error": "Standard OCR error",
    "visible_name_fragment": "Visible name fragment",
    "high_distance_prediction": "High-distance prediction",
    "extreme_distance_prediction": "Extreme-distance prediction",
    "real_drug_name_collision": "Real-drug-name collision",
}

DISTANCE_LABELS = {
    "0_exact_after_normalization": "0 edits",
    "1_single_edit": "1 edit",
    "2_3_edits": "2-3 edits",
    "4_5_edits": "4-5 edits",
    "6_plus_edits": "6+ edits",
}

MISTAKE_LABELS = {
    "type_1_exact_real_name_collision": "Type 1, exact real-name collision",
    "type_2_equal_edit_evidence": "Type 2, equal edit evidence",
    "type_3_unreadable_continuation": "Type 3, unreadable continuation",
    "type_4_family_variant": "Type 4, family or variant mismatch",
    "type_5_candidate_generation": "Type 5, candidate-generation failure",
    "type_6_candidate_ranking": "Type 6, candidate-ranking failure",
}

TIE_RULE_LABELS = {
    "current_model_order": "Current full-evidence order",
    "weighted_then_position": "Weighted distance, then position",
    "position_then_weighted": "Position, then weighted distance",
    "edge_then_weighted": "Edge evidence, then distance",
    "composite_evidence": "Composite lexical evidence",
    "pareto_evidence_025": "Pareto evidence, gap 0.25",
    "pareto_evidence_015": "Pareto evidence, gap 0.15",
    "pareto_evidence_010": "Pareto evidence, gap 0.10",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument(
        "--synthetic-results",
        type=Path,
        default=DEFAULT_SYNTHETIC_RESULTS,
    )
    return parser.parse_args()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"refusing to write empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def compact_pair(row: dict[str, Any]) -> tuple[str, str]:
    return (
        experiments.current_app.compact_key(row["input"]),
        str(row["expected_family_key"]),
    )


def deduplicate(rows: Iterable[dict[str, Any]], *, scored_only: bool) -> list[dict[str, Any]]:
    output = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if scored_only and int(row["scored_case"]) != 1:
            continue
        key = compact_pair(row)
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def load_joined_rows(cases_path: Path, results_path: Path) -> list[dict[str, Any]]:
    cases = experiments.load_cases(cases_path, 0)
    result_rows = experiments.read_csv(results_path)
    by_case = {row["case_id"]: row for row in result_rows}
    if len(by_case) != len(result_rows):
        raise ValueError("Algorithm 4 result case_id values are not unique")
    missing = [row["case_id"] for row in cases if row["case_id"] not in by_case]
    if missing:
        raise ValueError(f"Algorithm 4 results miss {len(missing)} accepted cases")

    joined = []
    for case in cases:
        result = by_case[case["case_id"]]
        joined.append(
            {
                **case,
                "first_relevant_rank": int(float(result["first_relevant_rank"])),
                "hit_at_1": int(float(result["hit_at_1"])),
                "hit_at_20": int(float(result["hit_at_20"])),
                "top_1": result["top_1"],
            }
        )
    return joined


def operation_profile(row: dict[str, Any]) -> str:
    counts = (
        int(float(row["source_additions_count"])),
        int(float(row["source_deletions_count"])),
        int(float(row["source_flip_count"])),
    )
    active = sum(value > 0 for value in counts)
    if active > 1:
        return "mixed_operations"
    if counts[0]:
        return "missing_characters_only"
    if counts[1]:
        return "extra_characters_only"
    if counts[2]:
        return "substitutions_only"
    return "formatting_only"


def query_length_band(row: dict[str, Any]) -> str:
    length = len(experiments.current_app.compact_key(row["input"]))
    if length <= 3:
        return "1_3_characters"
    if length <= 5:
        return "4_5_characters"
    if length <= 7:
        return "6_7_characters"
    if length <= 9:
        return "8_9_characters"
    return "10_plus_characters"


def count_band(value: str, *, zero: str, one: str, many: str) -> str:
    count = int(float(value))
    if count == 0:
        return zero
    if count == 1:
        return one
    return many


def operation_count_band(value: str) -> str:
    count = int(float(value))
    if count == 0:
        return "0"
    if count == 1:
        return "1"
    if count == 2:
        return "2"
    return "3_plus"


def length_direction(row: dict[str, Any]) -> str:
    difference = int(float(row["source_length_difference"]))
    if difference > 0:
        return "ocr_output_shorter"
    if difference < 0:
        return "ocr_output_longer"
    return "equal_length"


def dimension_values(row: dict[str, Any]) -> dict[str, str]:
    return {
        "overall": "all",
        "analysis_cohort": str(row["analysis_cohort"]),
        "mistake_type": str(row["mistake_type"]),
        "distance_band": str(row["distance_band"]),
        "difficulty": str(row["difficulty"]),
        "danger": str(row["danger"]),
        "operation_profile": operation_profile(row),
        "source_addition_count": operation_count_band(row["source_additions_count"]),
        "source_deletion_count": operation_count_band(row["source_deletions_count"]),
        "source_replacement_count": operation_count_band(row["source_flip_count"]),
        "length_direction": length_direction(row),
        "query_length_band": query_length_band(row),
        "shared_character_band": count_band(
            row["shared_character_count"],
            zero="0_shared_characters",
            one="1_shared_character",
            many="2_plus_shared_characters",
        ),
        "shared_bigram_band": count_band(
            row["shared_ngram_count"],
            zero="0_shared_bigrams",
            one="1_shared_bigram",
            many="2_plus_shared_bigrams",
        ),
        "ocr_output_catalog_status": (
            "names_a_catalog_family"
            if int(float(row["ocr_output_in_egypt_db"]))
            else "not_a_catalog_family"
        ),
        "source_model": str(row["model_name"]),
        "target_family": str(row["expected_family_name"]),
    }


def mean(rows: list[dict[str, Any]], field: str) -> float:
    return statistics.fmean(float(row[field]) for row in rows)


def build_metric_rows(scopes: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    output = []
    for scope, rows in scopes.items():
        total_h20_failures = sum(1 - int(row["hit_at_20"]) for row in rows)
        dimensions: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for row in rows:
            for dimension, value in dimension_values(row).items():
                dimensions.setdefault(dimension, {}).setdefault(value, []).append(row)

        for dimension, groups in dimensions.items():
            for group, grouped in sorted(groups.items()):
                failures = sum(1 - int(row["hit_at_20"]) for row in grouped)
                output.append(
                    {
                        "scope": scope,
                        "dimension": dimension,
                        "group": group,
                        "cases": len(grouped),
                        "share_of_scope": round(len(grouped) / len(rows), 8),
                        "mean_edit_distance": round(mean(grouped, "edit_distance"), 6),
                        "mean_normalized_edit_distance": round(
                            mean(grouped, "normalized_edit_distance"), 6
                        ),
                        "mean_compact_query_length": round(
                            statistics.fmean(
                                len(experiments.current_app.compact_key(row["input"]))
                                for row in grouped
                            ),
                            6,
                        ),
                        "hit_at_1": round(mean(grouped, "hit_at_1"), 8),
                        "hit_at_20": round(mean(grouped, "hit_at_20"), 8),
                        "top_1_failures": sum(1 - int(row["hit_at_1"]) for row in grouped),
                        "top_20_failures": failures,
                        "top_20_failure_rate": round(failures / len(grouped), 8),
                        "share_of_scope_top_20_failures": round(
                            failures / total_h20_failures if total_h20_failures else 0.0,
                            8,
                        ),
                    }
                )
    return output


def denominator_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scopes = {
        "inclusive_observations": rows,
        "scored_observations": [row for row in rows if int(row["scored_case"]) == 1],
        "all_unique_pairs": deduplicate(rows, scored_only=False),
        "primary_fair_unique": deduplicate(rows, scored_only=True),
    }
    output = []
    for scope, scoped in scopes.items():
        output.append(
            {
                "scope": scope,
                "cases": len(scoped),
                "real_drug_collisions": sum(
                    row["mistake_type"] == "real_drug_name_collision" for row in scoped
                ),
                "hit_at_1": round(mean(scoped, "hit_at_1"), 8),
                "hit_at_20": round(mean(scoped, "hit_at_20"), 8),
            }
        )
    primary = output[-1]
    for row in output:
        row["delta_hit_at_1_vs_inclusive"] = round(
            row["hit_at_1"] - output[0]["hit_at_1"], 8
        )
        row["delta_hit_at_20_vs_inclusive"] = round(
            row["hit_at_20"] - output[0]["hit_at_20"], 8
        )
        row["delta_hit_at_1_vs_primary"] = round(
            row["hit_at_1"] - primary["hit_at_1"], 8
        )
        row["delta_hit_at_20_vs_primary"] = round(
            row["hit_at_20"] - primary["hit_at_20"], 8
        )
    return output


def synthetic_metric(
    mistake_type: str,
    dimension: str,
    group: str,
    rows: list[dict[str, str]],
    type_count: int,
) -> dict[str, Any]:
    return {
        "mistake_type": mistake_type,
        "dimension": dimension,
        "group": group,
        "cases": len(rows),
        "share_of_mistake_type": round(len(rows) / type_count, 8),
        "hit_at_1": round(mean(rows, "hit_at_1"), 8),
        "hit_at_20": round(mean(rows, "hit_at_20"), 8),
        "behavior_success": round(mean(rows, "behavior_success"), 8),
        "unsafe_confident_top1_rate": round(
            mean(rows, "unsafe_confident_top1"), 8
        ),
    }


def synthetic_mistake_metrics(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    output = []
    by_type: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_type.setdefault(str(row["mistake_type"]), []).append(row)

    for mistake_type, typed_rows in sorted(by_type.items()):
        type_count = len(typed_rows)
        output.append(
            synthetic_metric(mistake_type, "overall", "all", typed_rows, type_count)
        )
        for dimension in ("scope", "category", "difficulty", "danger", "decision_type"):
            groups: dict[str, list[dict[str, str]]] = {}
            for row in typed_rows:
                groups.setdefault(str(row[dimension]), []).append(row)
            for group, grouped in sorted(groups.items()):
                output.append(
                    synthetic_metric(
                        mistake_type,
                        dimension,
                        group,
                        grouped,
                        type_count,
                    )
                )

        error_counts = Counter(str(row["error_type"]) for row in typed_rows)
        top_errors = {error for error, _ in error_counts.most_common(10)}
        for error_type in sorted(top_errors, key=lambda value: (-error_counts[value], value)):
            grouped = [row for row in typed_rows if row["error_type"] == error_type]
            output.append(
                synthetic_metric(
                    mistake_type,
                    "top_error_type",
                    error_type,
                    grouped,
                    type_count,
                )
            )
    return output


def synthetic_denominator_metrics(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    scopes = {
        "inclusive_115k": rows,
        "fair_collision_excluded": [row for row in rows if int(row["scored_case"]) == 1],
    }
    output = []
    inclusive_h1 = mean(rows, "hit_at_1")
    inclusive_h20 = mean(rows, "hit_at_20")
    for scope, scoped in scopes.items():
        output.append(
            {
                "scope": scope,
                "cases": len(scoped),
                "excluded_exact_real_name_collisions": len(rows) - len(scoped),
                "hit_at_1": round(mean(scoped, "hit_at_1"), 8),
                "hit_at_20": round(mean(scoped, "hit_at_20"), 8),
                "behavior_success": round(mean(scoped, "behavior_success"), 8),
                "unsafe_confident_top1_rate": round(
                    mean(scoped, "unsafe_confident_top1"), 8
                ),
                "delta_hit_at_1_vs_inclusive": round(
                    mean(scoped, "hit_at_1") - inclusive_h1, 8
                ),
                "delta_hit_at_20_vs_inclusive": round(
                    mean(scoped, "hit_at_20") - inclusive_h20, 8
                ),
            }
        )
    return output


def result_key(result: dict[str, Any]) -> str:
    return experiments.current_app.compact_key(experiments.result_name(result))


def numeric(result: dict[str, Any], field: str, default: float = 0.0) -> float:
    value = result.get(field, default)
    return float(value) if value not in {None, ""} else default


def dual_agreement(result: dict[str, Any]) -> int:
    return int(bool(result.get("external_rank")) and bool(result.get("rescue_rank")))


def tie_evidence(result: dict[str, Any]) -> float:
    """Combine independent tie evidence on comparable scales."""

    return (
        -numeric(result, "weighted_edit_distance", 999.0)
        + 0.35 * numeric(result, "positional_evidence")
        + 0.25 * numeric(result, "edge_evidence")
        + 0.10 * dual_agreement(result)
    )


TieRule = Callable[[dict[str, Any]], tuple[Any, ...]]


TIE_RULES: dict[str, TieRule] = {
    "current_model_order": lambda result: (0,),
    "weighted_then_position": lambda result: (
        numeric(result, "weighted_edit_distance", 999.0),
        -numeric(result, "positional_evidence"),
        -numeric(result, "edge_evidence"),
        -dual_agreement(result),
        -numeric(result, "score"),
    ),
    "position_then_weighted": lambda result: (
        -numeric(result, "positional_evidence"),
        numeric(result, "weighted_edit_distance", 999.0),
        -numeric(result, "edge_evidence"),
        -dual_agreement(result),
        -numeric(result, "score"),
    ),
    "edge_then_weighted": lambda result: (
        -numeric(result, "edge_evidence"),
        numeric(result, "weighted_edit_distance", 999.0),
        -numeric(result, "positional_evidence"),
        -dual_agreement(result),
        -numeric(result, "score"),
    ),
    "composite_evidence": lambda result: (
        -tie_evidence(result),
        -numeric(result, "score"),
    ),
    "pareto_evidence_025": lambda result: (
        numeric(result, "weighted_edit_distance", 999.0),
        -numeric(result, "positional_evidence"),
        -numeric(result, "edge_evidence"),
        -dual_agreement(result),
        -numeric(result, "score"),
    ),
    "pareto_evidence_015": lambda result: (
        numeric(result, "weighted_edit_distance", 999.0),
        -numeric(result, "positional_evidence"),
        -numeric(result, "edge_evidence"),
        -dual_agreement(result),
        -numeric(result, "score"),
    ),
    "pareto_evidence_010": lambda result: (
        numeric(result, "weighted_edit_distance", 999.0),
        -numeric(result, "positional_evidence"),
        -numeric(result, "edge_evidence"),
        -dual_agreement(result),
        -numeric(result, "score"),
    ),
}


def pareto_dominates(candidate: dict[str, Any], top: dict[str, Any]) -> bool:
    candidate_values = (
        -numeric(candidate, "weighted_edit_distance", 999.0),
        numeric(candidate, "positional_evidence"),
        numeric(candidate, "edge_evidence"),
        dual_agreement(candidate),
    )
    top_values = (
        -numeric(top, "weighted_edit_distance", 999.0),
        numeric(top, "positional_evidence"),
        numeric(top, "edge_evidence"),
        dual_agreement(top),
    )
    return all(left >= right for left, right in zip(candidate_values, top_values)) and any(
        left > right for left, right in zip(candidate_values, top_values)
    )


def rerank_equal_distance(
    module: Any,
    query: str,
    results: list[dict[str, Any]],
    rule_name: str,
    *,
    maximum_score_gap: float = 0.25,
) -> list[dict[str, Any]]:
    if rule_name == "current_model_order" or len(results) < 2:
        return results
    compact = experiments.current_app.compact_key(query)
    if not module.is_brand_like_query(query, compact):
        return results
    top = results[0]
    top_distance = numeric(top, "raw_edit_distance", 999.0)
    if top_distance == 0 or top_distance >= 999:
        return results
    top_score = numeric(top, "score")
    pareto_limits = {
        "pareto_evidence_025": 0.25,
        "pareto_evidence_015": 0.15,
        "pareto_evidence_010": 0.10,
    }
    score_gap_limit = pareto_limits.get(rule_name, maximum_score_gap)
    eligible = [
        result
        for result in results
        if numeric(result, "raw_edit_distance", 999.0) == top_distance
        and top_score - numeric(result, "score") <= score_gap_limit
    ]
    if rule_name in pareto_limits:
        eligible = [result for result in eligible if result is not top and pareto_dominates(result, top)]
        if not eligible:
            return results
    if len(eligible) < 2:
        if rule_name not in pareto_limits:
            return results
    order = {id(result): index for index, result in enumerate(results)}
    best = min(eligible, key=lambda result: (*TIE_RULES[rule_name](result), order[id(result)]))
    if best is top:
        return results
    return [best, *[result for result in results if result is not best]]


def relevant_rank(results: list[dict[str, Any]], expected_keys: set[str]) -> int:
    for rank, result in enumerate(results, 1):
        if result_key(result) in expected_keys:
            return rank
    return 999


def candidate_feature(result: dict[str, Any] | None, field: str) -> Any:
    if result is None:
        return ""
    value = result.get(field, "")
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    return value


def analyze_equal_distance(
    cases: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    module, catalog, _ = experiments.load_algorithm_4()
    primary_keys = {compact_pair(row) for row in deduplicate(cases, scored_only=True)}
    detail_rows = []
    rule_rows = []

    for case in cases:
        output = module.search_catalog(catalog, case["input"], experiments.TOP_K)
        results = list(output.get("results") or [])[: experiments.TOP_K]
        expected_keys = {
            key for key in str(case["expected_family_key"]).split(";") if key
        }
        current_rank = relevant_rank(results, expected_keys)
        top = results[0] if results else None
        expected = next((result for result in results if result_key(result) in expected_keys), None)
        top_distance = numeric(top, "raw_edit_distance", 999.0) if top else 999.0
        tied = [
            result
            for result in results
            if numeric(result, "raw_edit_distance", 999.0) == top_distance
        ]
        is_primary = compact_pair(case) in primary_keys
        if is_primary:
            primary_keys.remove(compact_pair(case))
        policy_rankings = {
            rule_name: rerank_equal_distance(
                module,
                case["input"],
                results,
                rule_name,
            )
            for rule_name in TIE_RULES
        }
        policy_fields: dict[str, Any] = {}
        for rule_name, ranked in policy_rankings.items():
            policy_fields[f"{rule_name}_top_1"] = (
                experiments.result_name(ranked[0]) if ranked else ""
            )
            policy_fields[f"{rule_name}_expected_rank"] = relevant_rank(
                ranked, expected_keys
            )
        detail_rows.append(
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "is_primary_fair_unique": int(is_primary),
                "input": case["input"],
                "expected_family_name": case["expected_family_name"],
                "mistake_type": case["mistake_type"],
                "analysis_cohort": case["analysis_cohort"],
                "distance_band": case["distance_band"],
                "current_expected_rank": current_rank,
                "current_top_1": experiments.result_name(top) if top else "",
                "top_distance_tie_count": len(tied),
                "top_distance_tied_names": "|".join(
                    experiments.result_name(result) for result in tied
                ),
                "equal_distance_rank_failure": int(
                    expected is not None
                    and current_rank > 1
                    and numeric(expected, "raw_edit_distance", 999.0) == top_distance
                ),
                "top_score": candidate_feature(top, "score"),
                "expected_score": candidate_feature(expected, "score"),
                "top_raw_edit_distance": candidate_feature(top, "raw_edit_distance"),
                "expected_raw_edit_distance": candidate_feature(
                    expected, "raw_edit_distance"
                ),
                "top_weighted_edit_distance": candidate_feature(
                    top, "weighted_edit_distance"
                ),
                "expected_weighted_edit_distance": candidate_feature(
                    expected, "weighted_edit_distance"
                ),
                "top_positional_evidence": candidate_feature(
                    top, "positional_evidence"
                ),
                "expected_positional_evidence": candidate_feature(
                    expected, "positional_evidence"
                ),
                "top_edge_evidence": candidate_feature(top, "edge_evidence"),
                "expected_edge_evidence": candidate_feature(
                    expected, "edge_evidence"
                ),
                "top_dual_agreement": dual_agreement(top) if top else "",
                "expected_dual_agreement": dual_agreement(expected) if expected else "",
                "top_matched_signals": candidate_feature(top, "matched_signals"),
                "expected_matched_signals": candidate_feature(
                    expected, "matched_signals"
                ),
                **policy_fields,
            }
        )

        if not is_primary:
            continue
        for rule_name in TIE_RULES:
            ranked = policy_rankings[rule_name]
            rank = relevant_rank(ranked, expected_keys)
            rule_rows.append(
                {
                    "case_id": case["case_id"],
                    "split": case["split"],
                    "rule": rule_name,
                    "current_rank": current_rank,
                    "rule_rank": rank,
                    "current_hit_at_1": int(current_rank == 1),
                    "rule_hit_at_1": int(rank == 1),
                    "switched_top_1": int(
                        bool(results)
                        and bool(ranked)
                        and result_key(results[0]) != result_key(ranked[0])
                    ),
                }
            )

    summaries = []
    for rule_name in TIE_RULES:
        selected = [row for row in rule_rows if row["rule"] == rule_name]
        for split in ("all", "development", "holdout"):
            scoped = selected if split == "all" else [row for row in selected if row["split"] == split]
            summaries.append(
                {
                    "rule": rule_name,
                    "split": split,
                    "cases": len(scoped),
                    "hit_at_1": round(mean(scoped, "rule_hit_at_1"), 8),
                    "delta_hit_at_1_vs_current": round(
                        mean(scoped, "rule_hit_at_1")
                        - mean(scoped, "current_hit_at_1"),
                        8,
                    ),
                    "top_1_switches": sum(int(row["switched_top_1"]) for row in scoped),
                    "wins": sum(
                        int(row["rule_hit_at_1"]) > int(row["current_hit_at_1"])
                        for row in scoped
                    ),
                    "losses": sum(
                        int(row["rule_hit_at_1"]) < int(row["current_hit_at_1"])
                        for row in scoped
                    ),
                }
            )
    return detail_rows, summaries


FIELD_LABELS = {
    "case_id": "Case identifier",
    "sample_id": "Source-model observation identifier",
    "observation_id": "OCR observation identifier",
    "image_id": "Source prescription-crop identifier",
    "source_row": "Synthetic source row",
    "source_model": "OCR source model",
    "model_name": "OCR source model",
    "model_version": "OCR model version",
    "preprocessing_id": "Image-preprocessing configuration",
    "edited_name": "OCR-predicted medicine text",
    "edited_length": "OCR-output length in source characters",
    "input": "Search query",
    "ground_truth_raw": "Raw human-verified transcription",
    "matched_canonical_name_norm": "Verified medicine family",
    "expected_family_name": "Verified medicine family",
    "expected_family_key": "Relevant catalog-family keys",
    "expected": "Expected medicine family",
    "canonical_length": "Verified-target length in source characters",
    "length_difference": "Verified-target length minus OCR-output length",
    "top_1": "First-ranked family",
    "top1_base": "First-ranked commercial family",
    "top1_product": "First-ranked catalog product",
    "top_5": "First five returned families",
    "top_20": "First twenty returned families",
    "first_relevant_rank": "Verified-family rank",
    "first_rank": "Verified-family rank",
    "hit_at_1": "Hit at rank 1",
    "hit_at_5": "Hit by rank 5",
    "hit_at_10": "Hit by rank 10",
    "hit_at_20": "Hit by rank 20",
    "reciprocal_rank": "Reciprocal rank",
    "reciprocal_rank_at_20": "Reciprocal rank through 20",
    "mrr_at_20": "Mean reciprocal rank through 20",
    "ap20": "Average precision through 20",
    "ndcg20": "Normalized discounted gain through 20",
    "latency_ms": "Warm query latency, milliseconds",
    "mean_latency_ms": "Mean warm query latency, milliseconds",
    "median_latency_ms": "Median warm query latency, milliseconds",
    "preparation_ms": "Index preparation time, milliseconds",
    "candidate_count": "Returned family count",
    "candidate_pool": "Families evaluated before output",
    "result_count": "Returned result count",
    "edit_distance": "Compact Levenshtein distance",
    "edit_distance_count": "Source alignment edit count",
    "source_edit_distance": "Source alignment edit count",
    "source_edit_similarity": "Source alignment similarity",
    "normalized_edit_distance": "Compact distance divided by target length",
    "edit_distance_over_canonical_length": "Source edits divided by target length",
    "edit_distance_over_edited_length": "Source edits divided by OCR-output length",
    "similarity_over_canonical_length": "Source similarity to verified target",
    "additions_count": "Missing OCR characters",
    "deletions_count": "Extra OCR characters",
    "flip_count": "OCR character replacements",
    "matches_count": "Aligned matching characters",
    "operation_sequence": "Ordered source alignment operations",
    "source_addition_count": "Source missing-character count",
    "source_deletion_count": "Source extra-character count",
    "source_replacement_count": "Source replacement count",
    "shared_character_count": "Shared character count",
    "shared_ngram_count": "Shared adjacent-character pair count",
    "compact_query": "Normalized alphanumeric search query",
    "compact_target": "Normalized alphanumeric verified target",
    "analysis_cohort": "OCR severity cohort",
    "distance_band": "Compact edit-distance band",
    "mistake_type": "Search failure mechanism",
    "category": "Synthetic mutation category",
    "error_type": "Detailed mutation rule",
    "difficulty": "Planned difficulty",
    "danger": "Medical consequence label",
    "split": "Target-family-disjoint split",
    "scored_case": "Fair-score eligibility",
    "accepted": "Automatic benchmark acceptance flag",
    "rejection_reason": "Automatic-review reason",
    "ground_truth_in_egypt_db": "Verified target found in Egyptian catalog",
    "ocr_output_in_egypt_db": "OCR output exactly names an Egyptian catalog family",
    "ocr_output_catalog_families": "Catalog families exactly named by OCR output",
    "dangerous_collision_families": "Conflicting exact catalog families",
    "provenance": "Row-generation or source provenance",
    "expected_behavior": "Expected safe search response",
    "case_subcategory": "Detailed benchmark subcategory",
    "unreadable_continuation": "User reports additional unreadable letters",
    "unsafe_confident_top1": "Unsafe confident first result",
    "unsafe_confident_top1_rate": "Unsafe confident first-result rate",
    "needs_clarification": "Clarification required",
    "behavior_success": "Expected response behavior achieved",
    "behavior_success_rate": "Expected response behavior rate",
    "decision_type": "Search response branch",
    "response_status": "Search response status",
    "experiment": "Experiment family",
    "algorithm": "Retrieval system or ablation",
    "scope": "Evaluation denominator or data scope",
    "cases": "Cases in denominator",
}


def human_label(value: Any) -> str:
    text = str(value)
    if text in ALGORITHM_LABELS:
        return ALGORITHM_LABELS[text]
    if text in ABLATION_LABELS:
        return ABLATION_LABELS[text]
    if text in COHORT_LABELS:
        return COHORT_LABELS[text]
    if text in DISTANCE_LABELS:
        return DISTANCE_LABELS[text]
    if text in MISTAKE_LABELS:
        return MISTAKE_LABELS[text]
    if text in TIE_RULE_LABELS:
        return TIE_RULE_LABELS[text]
    return text.replace("__ALL__", "All cases").replace("_", " ").strip().title()


def compact_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.lower().str.replace(
        r"[^a-z0-9]", "", regex=True
    )


def primary_unique_frame(frame: pd.DataFrame) -> pd.DataFrame:
    selected = frame[frame["scored_case"].astype(int).eq(1)].copy()
    selected["compact_query"] = compact_series(selected["input"])
    return selected.drop_duplicates(
        ["compact_query", "expected_family_key"], keep="first"
    )


def binary_rate_ci(
    values: Iterable[float],
    *,
    seed: int,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> tuple[float, float, float]:
    array = np.asarray(list(values), dtype=float)
    if array.size == 0:
        return math.nan, math.nan, math.nan
    rate = float(array.mean())
    rng = np.random.default_rng(seed)
    samples = rng.binomial(array.size, rate, size=iterations) / array.size
    lower, upper = np.quantile(samples, [0.025, 0.975])
    return rate, float(lower), float(upper)


def paired_effect(
    reference: Iterable[int],
    comparison: Iterable[int],
    *,
    seed: int,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> dict[str, float | int]:
    reference_array = np.asarray(list(reference), dtype=int)
    comparison_array = np.asarray(list(comparison), dtype=int)
    if reference_array.shape != comparison_array.shape:
        raise ValueError("paired effect inputs have different shapes")
    differences = reference_array - comparison_array
    gains = int(np.sum(differences == 1))
    losses = int(np.sum(differences == -1))
    ties = int(np.sum(differences == 0))
    n = int(differences.size)
    probabilities = np.array([losses, ties, gains], dtype=float) / n
    rng = np.random.default_rng(seed)
    sampled = rng.multinomial(n, probabilities, size=iterations)
    deltas = (sampled[:, 2] - sampled[:, 0]) / n
    lower, upper = np.quantile(deltas, [0.025, 0.975])
    discordant = gains + losses
    p_value = (
        float(binomtest(min(gains, losses), discordant, 0.5).pvalue)
        if discordant
        else 1.0
    )
    return {
        "cases": n,
        "gains": gains,
        "losses": losses,
        "ties": ties,
        "delta": float(differences.mean()),
        "ci_low": float(lower),
        "ci_high": float(upper),
        "mcnemar_exact_p": p_value,
        "matched_odds_ratio": float((gains + 0.5) / (losses + 0.5)),
    }


def configure_plot_style() -> None:
    sns.set_theme(
        style="whitegrid",
        context="paper",
        font="DejaVu Sans",
        rc={
            "figure.dpi": 150,
            "savefig.dpi": 180,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "axes.edgecolor": GRAY,
            "grid.color": LIGHT_GRAY,
            "grid.linewidth": 0.7,
        },
    )


def save_figure(fig: plt.Figure, stem: str) -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(
        FIGURES_DIR / f"{stem}.png",
        dpi=180,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(fig)


def add_percent_labels(ax: plt.Axes, bars: Any, *, digits: int = 1) -> None:
    for bar in bars:
        value = float(bar.get_height())
        ax.annotate(
            f"{value:.{digits}f}%",
            (bar.get_x() + bar.get_width() / 2, value),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )


def add_horizontal_labels(ax: plt.Axes, bars: Any, *, percent: bool = False) -> None:
    limit = ax.get_xlim()[1]
    for bar in bars:
        value = float(bar.get_width())
        text = f"{value:.1f}%" if percent else f"{value:,.0f}"
        ax.text(
            value + limit * 0.012,
            bar.get_y() + bar.get_height() / 2,
            text,
            ha="left",
            va="center",
            fontsize=8,
        )


def write_data_inventory(
    dataframes: dict[str, pd.DataFrame | Path]
) -> None:
    roles = {
        "OCR predictions": "Raw OCR text, verified target, and source alignment fields",
        "OCR search cases": "Accepted search cases, fair-score labels, and evidence fields",
        "OCR Algorithm 4 results": "Latest Algorithm 4 rankings, safety state, and latency",
        "Retrieval and ablation rows": "Ten retrieval systems and 24 Algorithm 4 variants",
        "Retrieval aggregate metrics": "Metrics by denominator, split, cohort, distance, and mistake type",
        "Retrieval paired comparisons": "Exact paired gains, losses, and McNemar tests",
        "Synthetic test cases": "Deterministic 115,000-row mutation benchmark",
        "Synthetic Algorithm 1 rows": "Algorithm 1 row-level synthetic outcomes",
        "Synthetic Algorithm 2 rows": "Algorithm 2 row-level synthetic outcomes",
        "Synthetic Algorithm 3 rows": "Algorithm 3 row-level synthetic outcomes",
        "Synthetic Algorithm 4 rows": "Latest Algorithm 4 row-level synthetic outcomes",
        "Synthetic category metrics": "Algorithms 1-4 metrics over 34 mutation categories",
        "Equal-distance evidence": "Candidate evidence and eight tie-policy results",
        "Pharmacist assignments": "Prepared counterbalanced trials, no participant outcomes",
    }
    inventory_rows = []
    dictionary_rows = []
    for name, source in dataframes.items():
        frame = (
            pd.read_csv(source, low_memory=False)
            if isinstance(source, Path)
            else source
        )
        inventory_rows.append(
            {
                "dataset": name,
                "rows": len(frame),
                "columns": len(frame.columns),
                "role": roles[name],
                "time_coverage": "No timestamp column; Meeting 10 snapshot regenerated 2026-07-19",
            }
        )
        for column in frame.columns:
            dictionary_rows.append(
                {
                    "dataset": name,
                    "raw_field": column,
                    "human_name": FIELD_LABELS.get(column, human_label(column)),
                    "data_type": str(frame[column].dtype),
                    "non_null_rows": int(frame[column].notna().sum()),
                }
            )
    write_csv(RESULTS_DIR / "source_inventory.csv", inventory_rows)
    write_csv(RESULTS_DIR / "data_dictionary.csv", dictionary_rows)


MODEL_LABELS = {
    "easyocr": "EasyOCR",
    "got_ocr2": "GOT-OCR2",
    "minicpm_v_46": "MiniCPM-V 4.6",
    "qwen25_vl_3b": "Qwen2.5-VL 3B",
    "paddleocr_vl_space": "PaddleOCR-VL",
    "llava_onevision_qwen2_7b_ov_hf": "LLaVA-OneVision 7B",
    "llava_onevision_qwen2_05b_ov": "LLaVA-OneVision 0.5B",
    "qwen3_vl_4b": "Qwen3-VL 4B",
    "internvl3_1b_hf": "InternVL3 1B",
    "qwen25_vl_7b": "Qwen2.5-VL 7B",
    "qwen3_vl_8b": "Qwen3-VL 8B",
    "trocr": "TrOCR",
    "internvl3_14b_hf": "InternVL3 14B",
    "internvl3_8b_hf": "InternVL3 8B",
}


def prepare_ocr_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    numeric = [
        "edit_distance",
        "normalized_edit_distance",
        "shared_character_count",
        "shared_ngram_count",
        "source_additions_count",
        "source_deletions_count",
        "source_flip_count",
        "source_matches_count",
        "source_length_difference",
        "hit_at_1",
        "hit_at_20",
        "first_relevant_rank",
    ]
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame["compact_query"] = compact_series(frame["input"])
    frame["compact_query_length"] = frame["compact_query"].str.len()
    active_operations = (
        frame[
            [
                "source_additions_count",
                "source_deletions_count",
                "source_flip_count",
            ]
        ]
        .gt(0)
        .sum(axis=1)
    )
    frame["operation_profile"] = np.select(
        [
            active_operations.gt(1),
            frame["source_additions_count"].gt(0),
            frame["source_deletions_count"].gt(0),
            frame["source_flip_count"].gt(0),
        ],
        [
            "Mixed operations",
            "Missing characters only",
            "Extra characters only",
            "Replacements only",
        ],
        default="Formatting only",
    )
    frame["query_length_band"] = pd.cut(
        frame["compact_query_length"],
        [0, 3, 5, 7, 9, np.inf],
        labels=["1-3", "4-5", "6-7", "8-9", "10+"],
        include_lowest=True,
    )
    frame["shared_bigram_band"] = np.select(
        [frame["shared_ngram_count"].eq(0), frame["shared_ngram_count"].eq(1)],
        ["No shared bigram", "One shared bigram"],
        default="Two or more shared bigrams",
    )
    frame["search_outcome"] = np.select(
        [frame["hit_at_1"].eq(1), frame["hit_at_20"].eq(1)],
        ["Correct at rank 1", "Found at ranks 2-20"],
        default="Outside top 20",
    )
    return frame


def grouped_binary_rates(
    frame: pd.DataFrame,
    field: str,
    order: list[str],
    metric: str,
    *,
    seed_offset: int,
) -> pd.DataFrame:
    rows = []
    for index, group in enumerate(order):
        selected = frame[frame[field].astype(str).eq(group)]
        if selected.empty:
            continue
        rate, lower, upper = binary_rate_ci(
            selected[metric], seed=RANDOM_SEED + seed_offset + index
        )
        rows.append(
            {
                "group": group,
                "label": human_label(group),
                "n": len(selected),
                "rate": rate,
                "ci_low": lower,
                "ci_high": upper,
            }
        )
    return pd.DataFrame(rows)


def plot_denominator_sensitivity(ocr: pd.DataFrame) -> None:
    all_unique = ocr.drop_duplicates(
        ["compact_query", "expected_family_key"], keep="first"
    )
    scopes = [
        ("All observations", ocr),
        ("Scored observations", ocr[ocr["scored_case"].astype(int).eq(1)]),
        ("All unique pairs", all_unique),
        ("Primary fair unique", all_unique[all_unique["scored_case"].astype(int).eq(1)]),
    ]
    names = [f"{name}\n(n={len(frame)})" for name, frame in scopes]
    x = np.arange(len(scopes))
    width = 0.34
    fig, ax = plt.subplots(figsize=(10, 6))
    for offset, metric, color, label_text in [
        (-width / 2, "hit_at_1", BLUE, "Hit@1"),
        (width / 2, "hit_at_20", ORANGE, "Hit@20"),
    ]:
        summaries = [
            binary_rate_ci(frame[metric], seed=RANDOM_SEED + index)
            for index, (_, frame) in enumerate(scopes)
        ]
        values = np.array([summary[0] for summary in summaries]) * 100
        errors = np.array(
            [
                [summary[0] - summary[1] for summary in summaries],
                [summary[2] - summary[0] for summary in summaries],
            ]
        ) * 100
        bars = ax.bar(
            x + offset,
            values,
            width,
            yerr=errors,
            capsize=3,
            color=color,
            label=label_text,
        )
        add_percent_labels(ax, bars, digits=2)
    ax.set_title("OCR recovery changes when duplicate and collision weights change")
    ax.set_xlabel("Evaluation denominator")
    ax.set_ylabel("Recovery rate (%)")
    ax.set_xticks(x, names)
    ax.set_ylim(0, 85)
    ax.yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    ax.legend(loc="upper center", ncol=2)
    save_figure(fig, "01_denominator_sensitivity")


def plot_ocr_composition(ocr: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    cohort_order = list(COHORT_LABELS)
    cohort_counts = ocr["analysis_cohort"].value_counts().reindex(cohort_order).fillna(0)
    bars = axes[0, 0].barh(
        [COHORT_LABELS[key] for key in cohort_order],
        cohort_counts,
        color=BLUE,
    )
    axes[0, 0].invert_yaxis()
    axes[0, 0].set_title("A. OCR severity cohorts")
    axes[0, 0].set_xlabel("OCR observations (count)")
    axes[0, 0].set_ylabel("Cohort")
    axes[0, 0].set_xlim(0, cohort_counts.max() * 1.24)
    add_horizontal_labels(axes[0, 0], bars)

    distance_order = list(DISTANCE_LABELS)
    distance_counts = ocr["distance_band"].value_counts().reindex(distance_order).fillna(0)
    bars = axes[0, 1].bar(
        [DISTANCE_LABELS[key] for key in distance_order],
        distance_counts,
        color=CYAN,
    )
    axes[0, 1].set_title("B. Compact edit-distance bands")
    axes[0, 1].set_xlabel("Compact Levenshtein distance")
    axes[0, 1].set_ylabel("OCR observations (count)")
    axes[0, 1].tick_params(axis="x", rotation=20)
    axes[0, 1].bar_label(bars, padding=2, fontsize=8)

    split_counts = ocr["split"].value_counts().reindex(["development", "holdout"])
    bars = axes[1, 0].bar(
        ["Development", "Holdout"], split_counts, color=[PURPLE, YELLOW]
    )
    axes[1, 0].set_title("C. Target-family-disjoint split")
    axes[1, 0].set_xlabel("Split")
    axes[1, 0].set_ylabel("OCR observations (count)")
    axes[1, 0].bar_label(
        bars,
        labels=[f"{value} ({value / len(ocr) * 100:.1f}%)" for value in split_counts],
        padding=3,
        fontsize=8,
    )

    outcome_order = ["Correct at rank 1", "Found at ranks 2-20", "Outside top 20"]
    outcome_counts = ocr["search_outcome"].value_counts().reindex(outcome_order)
    bars = axes[1, 1].bar(
        outcome_order,
        outcome_counts,
        color=[BLUE, CYAN, ORANGE],
    )
    axes[1, 1].set_title("D. Latest Algorithm 4 outcomes")
    axes[1, 1].set_xlabel("Mutually exclusive search outcome")
    axes[1, 1].set_ylabel("OCR observations (count)")
    axes[1, 1].tick_params(axis="x", rotation=18)
    axes[1, 1].bar_label(
        bars,
        labels=[f"{value} ({value / len(ocr) * 100:.1f}%)" for value in outcome_counts],
        padding=3,
        fontsize=8,
    )
    fig.suptitle("The 595-row OCR benchmark mixes severity, split, and outcome", y=1.01)
    save_figure(fig, "02_ocr_dataset_composition")


def plot_model_case_mix(ocr: pd.DataFrame) -> None:
    rows = []
    for model, group in ocr.groupby("model_name", sort=False):
        standard = group[group["analysis_cohort"].eq("standard_ocr_error")]
        rows.append(
            {
                "model": MODEL_LABELS.get(model, human_label(model)),
                "n": len(group),
                "raw_h1": group["hit_at_1"].mean() * 100,
                "standard_h1": standard["hit_at_1"].mean() * 100 if len(standard) else np.nan,
                "extreme_share": group["analysis_cohort"].eq("extreme_distance_prediction").mean() * 100,
            }
        )
    metrics = pd.DataFrame(rows).sort_values("raw_h1", ascending=False).reset_index(drop=True)
    fig, axes = plt.subplots(1, 2, figsize=(14, 8), sharex=True)
    for panel, ax in enumerate(axes):
        selected = metrics.iloc[panel * 7 : (panel + 1) * 7]
        y = np.arange(len(selected))
        ax.barh(y - 0.18, selected["raw_h1"], 0.34, color=BLUE, label="All supplied rows")
        ax.barh(y + 0.18, selected["standard_h1"], 0.34, color=ORANGE, label="Standard errors only")
        ax.set_yticks(
            y,
            [
                f"{row.model} (n={row.n}, extreme={row.extreme_share:.0f}%)"
                for row in selected.itertuples()
            ],
        )
        ax.invert_yaxis()
        ax.set_xlim(0, 105)
        ax.set_xlabel("Algorithm 4 Hit@1 within model rows (%)")
        ax.set_ylabel("OCR source model and supplied case mix")
        ax.xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    axes[0].legend(loc="lower right")
    fig.suptitle("Raw OCR-model ordering changes after controlling for error severity")
    save_figure(fig, "03_model_case_mix")


def plot_distance_recovery(primary: pd.DataFrame) -> None:
    order = list(DISTANCE_LABELS)
    x = np.arange(len(order))
    width = 0.34
    fig, ax = plt.subplots(figsize=(10, 6))
    for offset, metric, color, metric_label, seed_offset in [
        (-width / 2, "hit_at_1", BLUE, "Hit@1", 100),
        (width / 2, "hit_at_20", ORANGE, "Hit@20", 200),
    ]:
        summaries = grouped_binary_rates(
            primary, "distance_band", order, metric, seed_offset=seed_offset
        )
        values = summaries["rate"].to_numpy() * 100
        errors = np.vstack(
            [
                (summaries["rate"] - summaries["ci_low"]).to_numpy(),
                (summaries["ci_high"] - summaries["rate"]).to_numpy(),
            ]
        ) * 100
        bars = ax.bar(x + offset, values, width, yerr=errors, capsize=3, color=color, label=metric_label)
        add_percent_labels(ax, bars)
    counts = primary["distance_band"].value_counts().reindex(order)
    ax.set_xticks(x, [f"{DISTANCE_LABELS[key]}\n(n={counts[key]})" for key in order])
    ax.set_ylim(0, 112)
    ax.set_xlabel("Compact edit-distance band")
    ax.set_ylabel("Recovery within band (%)")
    ax.set_title("Search retrieval breaks after three compact character edits")
    ax.yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    ax.legend(loc="upper right")
    save_figure(fig, "04_distance_recovery")


def plot_evidence_recovery(primary: pd.DataFrame) -> None:
    panels = [
        (
            "operation_profile",
            ["Formatting only", "Replacements only", "Missing characters only", "Extra characters only", "Mixed operations"],
            "A. Character-operation profile",
        ),
        (
            "shared_bigram_band",
            ["No shared bigram", "One shared bigram", "Two or more shared bigrams"],
            "B. Adjacent-character evidence",
        ),
        (
            "query_length_band",
            ["1-3", "4-5", "6-7", "8-9", "10+"],
            "C. Visible compact query length",
        ),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(16, 7), sharex=True)
    for panel_index, (field, order, title) in enumerate(panels):
        ax = axes[panel_index]
        rates = grouped_binary_rates(
            primary, field, order, "hit_at_20", seed_offset=300 + panel_index * 10
        )
        y = np.arange(len(rates))
        bars = ax.barh(y, rates["rate"] * 100, color=[BLUE, CYAN, YELLOW, ORANGE, PURPLE][: len(rates)])
        ax.set_yticks(y, [f"{row.label} (n={row.n})" for row in rates.itertuples()])
        ax.invert_yaxis()
        ax.set_xlim(0, 112)
        ax.set_xlabel("Hit@20 within group (%)")
        ax.set_ylabel(title.split(". ", 1)[1])
        ax.set_title(title)
        ax.xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
        add_horizontal_labels(ax, bars, percent=True)
    fig.suptitle("Remaining character evidence, not query length alone, controls recovery", y=1.01)
    save_figure(fig, "05_error_evidence_recovery")


def plot_extreme_profile(ocr: pd.DataFrame) -> None:
    extreme = ocr[ocr["analysis_cohort"].eq("extreme_distance_prediction")].copy()
    fig, axes = plt.subplots(2, 3, figsize=(18, 8.4))
    views = [
        ("distance_band", list(DISTANCE_LABELS), DISTANCE_LABELS, "A. Compact edit count"),
        (
            "operation_profile",
            ["Formatting only", "Replacements only", "Missing characters only", "Extra characters only", "Mixed operations"],
            None,
            "B. Character-operation profile",
        ),
        (
            "shared_bigram_band",
            ["No shared bigram", "One shared bigram", "Two or more shared bigrams"],
            None,
            "C. Shared adjacent characters",
        ),
        (
            "query_length_band",
            ["1-3", "4-5", "6-7", "8-9", "10+"],
            None,
            "D. Visible compact query length",
        ),
    ]
    for ax, (field, order, labels, title) in zip(axes.flat[:4], views):
        counts = extreme[field].astype(str).value_counts().reindex(order).fillna(0)
        names = [labels.get(key, key) if labels else key for key in order]
        bars = ax.barh(names, counts, color=ORANGE)
        ax.invert_yaxis()
        ax.set_xlabel("Extreme observations (count)")
        ax.set_ylabel(title.split(". ", 1)[1])
        ax.set_title(title)
        ax.set_xlim(0, max(counts.max() * 1.28, 1))
        add_horizontal_labels(ax, bars)

    outcome_order = ["Correct at rank 1", "Found at ranks 2-20", "Outside top 20"]
    outcome_counts = extreme["search_outcome"].value_counts().reindex(outcome_order).fillna(0)
    bars = axes[1, 1].barh(
        outcome_order,
        outcome_counts,
        color=[GREEN, BLUE, RED],
    )
    axes[1, 1].invert_yaxis()
    axes[1, 1].set_xlabel("Extreme observations (count)")
    axes[1, 1].set_ylabel("Algorithm 4 rank outcome")
    axes[1, 1].set_title("E. Search outcome")
    axes[1, 1].set_xlim(0, max(outcome_counts.max() * 1.28, 1))
    add_horizontal_labels(axes[1, 1], bars)

    model_counts = extreme["model_name"].value_counts()
    top = model_counts.head(7)
    if len(model_counts) > 7:
        top.loc["Other seven models"] = model_counts.iloc[7:].sum()
    names = [MODEL_LABELS.get(key, key) for key in top.index]
    bars = axes[1, 2].barh(names, top.values, color=PURPLE)
    axes[1, 2].invert_yaxis()
    axes[1, 2].set_xlabel("Extreme observations (count)")
    axes[1, 2].set_ylabel("OCR source model")
    axes[1, 2].set_title("F. Source-model contribution")
    axes[1, 2].set_xlim(0, top.max() * 1.28)
    add_horizontal_labels(axes[1, 2], bars)
    fig.suptitle(
        "Extreme >0.60 predictions are mixed, low-bigram, and usually outside top 20",
        y=1.01,
    )
    save_figure(fig, "06_extreme_cohort_profile")


def plot_ocr_correlations(primary: pd.DataFrame) -> pd.DataFrame:
    fields = {
        "edit_distance": "Compact edits",
        "normalized_edit_distance": "Normalized distance",
        "compact_query_length": "Query length",
        "shared_character_count": "Shared characters",
        "shared_ngram_count": "Shared bigrams",
        "source_additions_count": "Missing characters",
        "source_deletions_count": "Extra characters",
        "source_flip_count": "Replacements",
        "hit_at_1": "Hit@1",
        "hit_at_20": "Hit@20",
    }
    selected = primary[list(fields)].astype(float)
    matrix = pd.DataFrame(index=fields.values(), columns=fields.values(), dtype=float)
    for left_raw, left_label in fields.items():
        for right_raw, right_label in fields.items():
            coefficient = spearmanr(
                selected[left_raw], selected[right_raw], nan_policy="omit"
            ).statistic
            matrix.loc[left_label, right_label] = coefficient
    fig, ax = plt.subplots(figsize=(12, 9))
    sns.heatmap(
        matrix,
        vmin=-1,
        vmax=1,
        center=0,
        cmap="vlag",
        annot=True,
        fmt=".2f",
        square=True,
        linewidths=0.4,
        cbar_kws={"label": "Spearman rank correlation"},
        ax=ax,
    )
    ax.set_title("Character evidence and recovery have monotonic but non-causal relationships")
    ax.set_xlabel("Numeric benchmark field")
    ax.set_ylabel("Numeric benchmark field")
    save_figure(fig, "07_ocr_correlation_matrix")
    return matrix


def plot_distance_bigram_interaction(primary: pd.DataFrame) -> pd.DataFrame:
    distance_order = list(DISTANCE_LABELS)
    bigram_order = ["No shared bigram", "One shared bigram", "Two or more shared bigrams"]
    grouped = (
        primary.groupby(["distance_band", "shared_bigram_band"], observed=True)
        .agg(n=("case_id", "size"), hit_at_20=("hit_at_20", "mean"))
        .reset_index()
    )
    rate = grouped.pivot(index="distance_band", columns="shared_bigram_band", values="hit_at_20").reindex(index=distance_order, columns=bigram_order)
    counts = grouped.pivot(index="distance_band", columns="shared_bigram_band", values="n").reindex(index=distance_order, columns=bigram_order).fillna(0)
    annotation = rate.copy().astype(object)
    for row in rate.index:
        for column in rate.columns:
            value = rate.loc[row, column]
            annotation.loc[row, column] = (
                "No rows" if pd.isna(value) else f"{value * 100:.1f}%\nn={int(counts.loc[row, column])}"
            )
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    sns.heatmap(
        rate * 100,
        vmin=0,
        vmax=100,
        cmap="YlGnBu",
        annot=annotation,
        fmt="",
        linewidths=0.5,
        cbar_kws={"label": "Hit@20 (%)"},
        ax=axes[0],
    )
    axes[0].set_title("A. Recovery rate")
    axes[0].set_xlabel("Shared adjacent-character evidence")
    axes[0].set_ylabel("Compact edit-distance band")
    axes[0].set_yticklabels([DISTANCE_LABELS[key] for key in distance_order], rotation=0)

    sns.heatmap(
        counts,
        cmap="Blues",
        annot=True,
        fmt=".0f",
        linewidths=0.5,
        cbar_kws={"label": "Primary cases (count)"},
        ax=axes[1],
    )
    axes[1].set_title("B. Case count")
    axes[1].set_xlabel("Shared adjacent-character evidence")
    axes[1].set_ylabel("Compact edit-distance band")
    axes[1].set_yticklabels([DISTANCE_LABELS[key] for key in distance_order], rotation=0)
    fig.suptitle("Shared bigrams moderate recovery only while edit corruption remains bounded", y=1.02)
    save_figure(fig, "08_distance_bigram_interaction")
    return grouped


def prepare_primary_experiment_rows(
    case_results: pd.DataFrame, experiment: str
) -> pd.DataFrame:
    output = []
    selected = case_results[case_results["experiment"].eq(experiment)]
    for algorithm, group in selected.groupby("algorithm", sort=False):
        primary = primary_unique_frame(group)
        if len(primary) != 464:
            raise ValueError(
                f"{experiment}/{algorithm} has {len(primary)} primary pairs, expected 464"
            )
        output.append(primary)
    return pd.concat(output, ignore_index=True)


def enrich_retrieval_rows(
    retrieval_rows: pd.DataFrame,
    primary_ocr: pd.DataFrame,
) -> pd.DataFrame:
    evidence_columns = [
        "case_id",
        "operation_profile",
        "shared_bigram_band",
        "query_length_band",
    ]
    evidence = primary_ocr[evidence_columns].copy()
    if not evidence["case_id"].is_unique:
        raise ValueError("primary OCR evidence contains duplicate case IDs")
    enriched = retrieval_rows.merge(
        evidence,
        on="case_id",
        how="left",
        validate="many_to_one",
    )
    if enriched[evidence_columns[1:]].isna().any().any():
        raise ValueError("retrieval profile join left missing OCR evidence")
    return enriched


def retrieval_profile_metrics(rows: pd.DataFrame) -> pd.DataFrame:
    dimensions = [
        "distance_band",
        "analysis_cohort",
        "mistake_type",
        "operation_profile",
        "shared_bigram_band",
        "query_length_band",
    ]
    output = []
    for algorithm in RETRIEVAL_ORDER:
        algorithm_rows = rows[rows["algorithm"].eq(algorithm)]
        total_misses = int((1 - algorithm_rows["hit_at_20"]).sum())
        for dimension in dimensions:
            for group, selected in algorithm_rows.groupby(dimension, observed=True):
                misses = int((1 - selected["hit_at_20"]).sum())
                output.append(
                    {
                        "algorithm": algorithm,
                        "algorithm_label": ALGORITHM_LABELS[algorithm],
                        "dimension": dimension,
                        "group": str(group),
                        "cases": len(selected),
                        "hit_at_1": float(selected["hit_at_1"].mean()),
                        "hit_at_20": float(selected["hit_at_20"].mean()),
                        "top_20_misses": misses,
                        "top_20_failure_rate": misses / len(selected),
                        "share_of_algorithm_top_20_misses": (
                            misses / total_misses if total_misses else 0.0
                        ),
                    }
                )
    return pd.DataFrame(output)


def retrieval_failure_examples(rows: pd.DataFrame) -> pd.DataFrame:
    output = []
    for algorithm in RETRIEVAL_ORDER:
        algorithm_rows = rows[rows["algorithm"].eq(algorithm)]
        failures = {
            "ranking_failure": algorithm_rows[
                algorithm_rows["hit_at_1"].eq(0)
                & algorithm_rows["hit_at_20"].eq(1)
            ],
            "retrieval_failure": algorithm_rows[algorithm_rows["hit_at_20"].eq(0)],
        }
        for failure_type, selected in failures.items():
            if selected.empty:
                continue
            example = selected.sort_values(
                ["edit_distance", "normalized_edit_distance", "case_id"]
            ).iloc[0]
            output.append(
                {
                    "algorithm": algorithm,
                    "algorithm_label": ALGORITHM_LABELS[algorithm],
                    "failure_type": failure_type,
                    "case_id": example["case_id"],
                    "input": example["input"],
                    "expected_family": example["expected_family_name"],
                    "top_1": example["top_1"] if pd.notna(example["top_1"]) else "",
                    "first_relevant_rank": int(example["first_relevant_rank"]),
                    "compact_edit_distance": int(example["edit_distance"]),
                    "distance_band": example["distance_band"],
                    "mistake_type": example["mistake_type"],
                }
            )
    return pd.DataFrame(output)


def retrieval_metric_matrix(
    rows: pd.DataFrame,
    dimension: str,
    order: list[str],
    metric: str,
) -> pd.DataFrame:
    matrix = rows.pivot_table(
        index="algorithm",
        columns=dimension,
        values=metric,
        aggfunc="mean",
    )
    return matrix.reindex(index=RETRIEVAL_ORDER, columns=order) * 100


def plot_retrieval_distance_profiles(rows: pd.DataFrame) -> None:
    distance_order = list(DISTANCE_LABELS)
    labels = [DISTANCE_LABELS[value] for value in distance_order]
    fig, axes = plt.subplots(1, 2, figsize=(16, 10), sharey=True)
    for ax, metric, title in [
        (axes[0], "hit_at_1", "A. Correct family ranked first"),
        (axes[1], "hit_at_20", "B. Correct family recovered by rank 20"),
    ]:
        matrix = retrieval_metric_matrix(rows, "distance_band", distance_order, metric)
        matrix.columns = labels
        matrix.index = [ALGORITHM_LABELS[value] for value in matrix.index]
        sns.heatmap(
            matrix,
            vmin=0,
            vmax=100,
            cmap="YlGnBu",
            annot=True,
            fmt=".1f",
            linewidths=0.45,
            cbar_kws={"label": "Recovery rate within edit-distance band (%)"},
            ax=ax,
        )
        ax.set_title(title)
        ax.set_xlabel("Compact Levenshtein edit-distance band")
        ax.set_ylabel("Retrieval system")
        ax.tick_params(axis="x", rotation=0)
        ax.tick_params(axis="y", rotation=0)
    fig.suptitle(
        "Experiment 1: every retrieval method degrades as character evidence disappears",
        y=1.01,
    )
    save_figure(fig, "27_retrieval_distance_profiles")


def plot_retrieval_error_evidence_profiles(rows: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(16, 10), sharey=True)
    specifications = [
        (
            axes[0],
            "operation_profile",
            OPERATION_ORDER,
            "A. Character-operation profile",
            "OCR alignment operation profile",
        ),
        (
            axes[1],
            "shared_bigram_band",
            BIGRAM_ORDER,
            "B. Remaining adjacent-character evidence",
            "Shared query-target bigrams",
        ),
    ]
    for ax, dimension, order, title, xlabel in specifications:
        matrix = retrieval_metric_matrix(rows, dimension, order, "hit_at_20")
        matrix.index = [ALGORITHM_LABELS[value] for value in matrix.index]
        sns.heatmap(
            matrix,
            vmin=0,
            vmax=100,
            cmap="YlGnBu",
            annot=True,
            fmt=".1f",
            linewidths=0.45,
            cbar_kws={"label": "Hit@20 within evidence group (%)"},
            ax=ax,
        )
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Retrieval system")
        ax.tick_params(axis="x", rotation=15)
        ax.tick_params(axis="y", rotation=0)
    fig.suptitle(
        "Mixed edits and missing bigrams expose different baseline assumptions",
        y=1.01,
    )
    save_figure(fig, "28_retrieval_error_evidence_profiles")


def plot_retrieval_failure_composition(rows: pd.DataFrame) -> None:
    distance_order = list(DISTANCE_LABELS)
    failures = rows[rows["hit_at_20"].eq(0)]
    counts = failures.pivot_table(
        index="algorithm",
        columns="distance_band",
        values="case_id",
        aggfunc="count",
        fill_value=0,
    ).reindex(index=RETRIEVAL_ORDER, columns=distance_order, fill_value=0)
    shares = counts.div(counts.sum(axis=1), axis=0) * 100
    colors = [CYAN, BLUE, YELLOW, ORANGE, PURPLE]
    fig, ax = plt.subplots(figsize=(14, 8))
    y = np.arange(len(shares))
    left = np.zeros(len(shares))
    for column, color in zip(distance_order, colors):
        values = shares[column].to_numpy(float)
        bars = ax.barh(
            y,
            values,
            left=left,
            height=0.62,
            color=color,
            label=DISTANCE_LABELS[column],
        )
        for bar, value in zip(bars, values):
            if value >= 7:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_y() + bar.get_height() / 2,
                    f"{value:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=8,
                )
        left += values
    totals = counts.sum(axis=1).astype(int)
    ax.set_yticks(
        y,
        [f"{ALGORITHM_LABELS[key]} (misses={totals.loc[key]})" for key in shares.index],
    )
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of that system's top-20 misses (%)")
    ax.set_ylabel("Retrieval system")
    ax.xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.10), ncol=5)
    ax.set_title(
        "Experiment 1 failure composition: severe edits dominate most systems, while exact/prefix fails earlier"
    )
    save_figure(fig, "29_retrieval_failure_composition")


def plot_retrieval_performance(metrics: pd.DataFrame) -> None:
    selected = metrics[
        metrics["experiment"].eq("retrieval")
        & metrics["scope"].eq("primary_fair_unique")
    ].copy()
    selected["label"] = selected["algorithm"].map(ALGORITHM_LABELS)
    selected = selected.sort_values("hit_at_1", ascending=False).reset_index(drop=True)
    fig, axes = plt.subplots(1, 2, figsize=(15, 8), sharex=True)
    for panel, ax in enumerate(axes):
        part = selected.iloc[panel * 5 : (panel + 1) * 5]
        y = np.arange(len(part))
        h1 = ax.barh(y - 0.18, part["hit_at_1"] * 100, 0.34, color=BLUE, label="Hit@1")
        h20 = ax.barh(y + 0.18, part["hit_at_20"] * 100, 0.34, color=ORANGE, label="Hit@20")
        ax.set_yticks(y, part["label"])
        ax.invert_yaxis()
        ax.set_xlim(0, 82)
        ax.set_xlabel("Recovery on 464 primary fair pairs (%)")
        ax.set_ylabel("Retrieval system")
        ax.xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
        for bars in (h1, h20):
            add_horizontal_labels(ax, bars, percent=True)
    axes[0].legend(loc="lower right")
    fig.suptitle("Algorithm 4 leads all nine tested retrieval alternatives")
    save_figure(fig, "09_retrieval_system_performance")


def retrieval_paired_statistics(primary_rows: pd.DataFrame) -> pd.DataFrame:
    reference_name = "algorithm_4_family_rescue"
    reference = primary_rows[primary_rows["algorithm"].eq(reference_name)].set_index("case_id")
    output = []
    for index, algorithm in enumerate(
        algorithm
        for algorithm in primary_rows["algorithm"].drop_duplicates()
        if algorithm != reference_name
    ):
        comparison = primary_rows[primary_rows["algorithm"].eq(algorithm)].set_index("case_id")
        common = reference.index.intersection(comparison.index)
        if len(common) != 464:
            raise ValueError(f"paired retrieval comparison has {len(common)} cases")
        for cutoff, field in [(1, "hit_at_1"), (20, "hit_at_20")]:
            effect = paired_effect(
                reference.loc[common, field],
                comparison.loc[common, field],
                seed=RANDOM_SEED + index * 100 + cutoff,
            )
            output.append(
                {
                    "experiment": "retrieval",
                    "reference": ALGORITHM_LABELS[reference_name],
                    "comparison": ALGORITHM_LABELS[algorithm],
                    "comparison_id": algorithm,
                    "cutoff": cutoff,
                    **effect,
                }
            )
    return pd.DataFrame(output)


def plot_retrieval_paired_effects(statistics_frame: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(15, 8), sharex=True)
    for ax, cutoff, color in zip(axes, [1, 20], [BLUE, ORANGE]):
        selected = statistics_frame[statistics_frame["cutoff"].eq(cutoff)].copy()
        selected = selected.sort_values("delta", ascending=True)
        y = np.arange(len(selected))
        values = selected["delta"].to_numpy() * 100
        errors = np.vstack(
            [
                (selected["delta"] - selected["ci_low"]).to_numpy(),
                (selected["ci_high"] - selected["delta"]).to_numpy(),
            ]
        ) * 100
        ax.errorbar(values, y, xerr=errors, fmt="o", color=color, capsize=3)
        ax.axvline(0, color=GRAY, linewidth=1)
        ax.set_yticks(
            y,
            [
                f"{row.comparison}\n{row.gains} gains / {row.losses} losses"
                for row in selected.itertuples()
            ],
        )
        ax.set_xlabel(f"Algorithm 4 minus comparison Hit@{cutoff} (percentage points)")
        ax.set_ylabel("Paired comparison")
        ax.set_title(f"Hit@{cutoff} paired risk difference, 95% bootstrap CI")
        ax.grid(axis="y", visible=False)
    fig.suptitle("Algorithm 4 gains exceed losses against every retrieval baseline", y=1.01)
    save_figure(fig, "10_retrieval_paired_effects")


def plot_efficiency_frontier(metrics: pd.DataFrame) -> pd.DataFrame:
    selected = metrics[
        metrics["experiment"].eq("retrieval")
        & metrics["scope"].eq("primary_fair_unique")
    ].copy()
    selected["label"] = selected["algorithm"].map(ALGORITHM_LABELS)
    selected["pareto"] = False
    for index, row in selected.iterrows():
        dominated = (
            (selected["median_latency_ms"] <= row["median_latency_ms"])
            & (selected["hit_at_20"] >= row["hit_at_20"])
            & (
                (selected["median_latency_ms"] < row["median_latency_ms"])
                | (selected["hit_at_20"] > row["hit_at_20"])
            )
        ).any()
        selected.loc[index, "pareto"] = not dominated

    fig, ax = plt.subplots(figsize=(11, 7))
    colors = np.where(selected["pareto"], ORANGE, BLUE)
    sizes = 70 + selected["hit_at_1"] * 260
    ax.scatter(
        selected["median_latency_ms"],
        selected["hit_at_20"] * 100,
        s=sizes,
        c=colors,
        alpha=0.88,
        edgecolor="white",
        linewidth=0.8,
    )
    for row in selected.itertuples():
        ax.annotate(
            row.label.replace(", ", "\n"),
            (row.median_latency_ms, row.hit_at_20 * 100),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=8,
        )
    frontier = selected[selected["pareto"]].sort_values("median_latency_ms")
    ax.plot(
        frontier["median_latency_ms"],
        frontier["hit_at_20"] * 100,
        color=ORANGE,
        linestyle="--",
        linewidth=1.2,
        label="Observed Pareto frontier",
    )
    ax.set_xscale("log")
    ax.set_xlabel("Median warm-query latency (milliseconds, log scale)")
    ax.set_ylabel("Hit@20 on 464 primary fair pairs (%)")
    ax.set_title("Algorithm 4 buys the highest retrieval coverage with the highest query latency")
    ax.yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    ax.legend(loc="lower right")
    save_figure(fig, "11_efficiency_pareto_frontier")
    return selected


def plot_latency_distributions(primary_rows: pd.DataFrame) -> None:
    ordering = (
        primary_rows.groupby("algorithm")["latency_ms"].median().sort_values().index.tolist()
    )
    fig, axes = plt.subplots(1, 2, figsize=(15, 8), sharex=False)
    for panel, ax in enumerate(axes):
        algorithms = ordering[panel * 5 : (panel + 1) * 5]
        part = primary_rows[primary_rows["algorithm"].isin(algorithms)].copy()
        part["system"] = pd.Categorical(
            part["algorithm"].map(ALGORITHM_LABELS),
            [ALGORITHM_LABELS[value] for value in algorithms],
            ordered=True,
        )
        sns.boxplot(
            data=part,
            y="system",
            x="latency_ms",
            hue="system",
            palette="colorblind",
            showfliers=False,
            legend=False,
            ax=ax,
        )
        ax.set_xlabel("Warm-query latency (milliseconds)")
        ax.set_ylabel("Retrieval system")
        ax.set_title("Lower-latency half" if panel == 0 else "Higher-latency half")
    fig.suptitle("Latency distributions reveal tails hidden by mean query time")
    save_figure(fig, "12_query_latency_distributions")


def plot_retrieval_tradeoff_radar(metrics: pd.DataFrame) -> None:
    selected_ids = [
        "baseline_levenshtein",
        "baseline_jaro_winkler",
        "algorithm_1_current_app",
        "algorithm_2_external_fast",
        "algorithm_3_rank_fusion",
        "algorithm_4_family_rescue",
    ]
    selected = metrics[
        metrics["experiment"].eq("retrieval")
        & metrics["scope"].eq("primary_fair_unique")
        & metrics["algorithm"].isin(selected_ids)
    ].set_index("algorithm").reindex(selected_ids)
    if selected.isna().all(axis=None):
        raise ValueError("retrieval trade-off radar has no metrics")

    query_latency = np.log1p(selected["median_latency_ms"].astype(float))
    preparation = np.log1p(selected["preparation_ms"].astype(float))

    def inverse_minmax(values: pd.Series) -> pd.Series:
        span = values.max() - values.min()
        if span == 0:
            return pd.Series(1.0, index=values.index)
        return 1.0 - (values - values.min()) / span

    profile = pd.DataFrame(
        {
            "Hit@1": selected["hit_at_1"].astype(float),
            "Hit@20": selected["hit_at_20"].astype(float),
            "MRR@20": selected["mrr_at_20"].astype(float),
            "Warm-query speed": inverse_minmax(query_latency),
            "Preparation speed": inverse_minmax(preparation),
        }
    )
    angles = np.linspace(0, 2 * np.pi, len(profile.columns), endpoint=False)
    closed_angles = np.concatenate([angles, angles[:1]])
    fig, ax = plt.subplots(figsize=(11, 8), subplot_kw={"projection": "polar"})
    colors = [CYAN, YELLOW, BLUE, ORANGE, PURPLE, RED]
    for algorithm, color in zip(selected_ids, colors):
        values = profile.loc[algorithm].to_numpy(float)
        closed_values = np.concatenate([values, values[:1]])
        ax.plot(
            closed_angles,
            closed_values,
            linewidth=2,
            color=color,
            label=ALGORITHM_LABELS[algorithm],
        )
        ax.fill(closed_angles, closed_values, color=color, alpha=0.035)
    ax.set_xticks(angles, profile.columns)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.50, 0.75, 1.00])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=9)
    ax.set_title(
        "Retrieval systems occupy different accuracy and efficiency profiles",
        pad=28,
    )
    ax.legend(loc="center left", bbox_to_anchor=(1.13, 0.5))
    fig.text(
        0.5,
        0.02,
        "Accuracy axes retain their 0-1 values. Speed axes are inverse min-max scores of log latency within these six systems; farther is better.",
        ha="center",
        color=GRAY,
        fontsize=10,
    )
    save_figure(fig, "26_retrieval_tradeoff_radar")


def plot_success_overlap(primary_rows: pd.DataFrame) -> pd.DataFrame:
    reference = primary_rows[
        primary_rows["algorithm"].eq("algorithm_4_family_rescue")
    ].set_index("case_id")
    comparison_ids = [
        "baseline_levenshtein",
        "baseline_jaro_winkler",
        "algorithm_3_rank_fusion",
    ]
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    output = []
    for column, comparison_id in enumerate(comparison_ids):
        comparison = primary_rows[primary_rows["algorithm"].eq(comparison_id)].set_index("case_id")
        common = reference.index.intersection(comparison.index)
        for row_index, field in enumerate(["hit_at_1", "hit_at_20"]):
            matrix = confusion_matrix(
                comparison.loc[common, field].astype(int),
                reference.loc[common, field].astype(int),
                labels=[0, 1],
            )
            sns.heatmap(
                matrix,
                annot=True,
                fmt="d",
                cmap="Blues",
                cbar=False,
                square=True,
                xticklabels=["A4 miss", "A4 hit"],
                yticklabels=["Other miss", "Other hit"],
                ax=axes[row_index, column],
            )
            axes[row_index, column].set_xlabel("Algorithm 4 outcome")
            axes[row_index, column].set_ylabel(f"{ALGORITHM_LABELS[comparison_id]} outcome")
            axes[row_index, column].set_title(
                f"{ALGORITHM_LABELS[comparison_id]} at Hit@{1 if field == 'hit_at_1' else 20}"
            )
            output.append(
                {
                    "comparison": ALGORITHM_LABELS[comparison_id],
                    "cutoff": 1 if field == "hit_at_1" else 20,
                    "both_miss": int(matrix[0, 0]),
                    "a4_only": int(matrix[0, 1]),
                    "comparison_only": int(matrix[1, 0]),
                    "both_hit": int(matrix[1, 1]),
                }
            )
    fig.suptitle("Algorithm 4 recovers many cases missed by strong alternatives, but not all", y=1.01)
    save_figure(fig, "13_success_overlap")
    return pd.DataFrame(output)


def plot_ablation_deltas(metrics: pd.DataFrame) -> None:
    selected = metrics[
        metrics["experiment"].eq("ablation")
        & metrics["scope"].eq("primary_fair_unique")
        & ~metrics["algorithm"].eq("full_algorithm_4")
    ].copy()
    selected["component"] = selected["algorithm"].map(ABLATION_LABELS)
    selected = selected.sort_values(["delta_hit_at_20", "delta_hit_at_1"])
    panel_size = math.ceil(len(selected) / 3)
    panels = [
        selected.iloc[index * panel_size : (index + 1) * panel_size]
        for index in range(3)
    ]
    fig, axes = plt.subplots(1, 3, figsize=(18, 10), sharex=True)
    for ax, panel in zip(axes, panels):
        y = np.arange(len(panel))
        ax.barh(y - 0.18, panel["delta_hit_at_1"] * 100, 0.34, color=BLUE, label="Hit@1 change")
        ax.barh(y + 0.18, panel["delta_hit_at_20"] * 100, 0.34, color=ORANGE, label="Hit@20 change")
        ax.set_yticks(y, panel["component"])
        ax.invert_yaxis()
        ax.axvline(0, color=GRAY, linewidth=1)
        ax.set_xlabel("Ablation minus complete A4 (percentage points)")
        ax.set_ylabel("Removed component")
    axes[0].legend(loc="lower left")
    fig.suptitle("Removing the family rescue layer causes the largest accuracy loss")
    save_figure(fig, "14_ablation_metric_deltas")


def plot_ablation_switches(paired: pd.DataFrame) -> None:
    selected = paired[paired["experiment"].eq("ablation")].copy()
    selected["component"] = selected["comparison_algorithm"].map(ABLATION_LABELS)
    selected["impact"] = (
        selected["net_reference_wins_hit_at_1"].abs()
        + selected["net_reference_wins_hit_at_20"].abs()
    )
    selected = selected.nlargest(8, "impact").sort_values("impact")
    fig, axes = plt.subplots(1, 2, figsize=(15, 7), sharey=True)
    y = np.arange(len(selected))
    for ax, cutoff, color in zip(axes, [1, 20], [BLUE, ORANGE]):
        gains = selected[f"reference_only_hit_at_{cutoff}"].to_numpy()
        losses = selected[f"comparison_only_hit_at_{cutoff}"].to_numpy()
        ax.barh(y, gains, color=color, label="Complete A4 only")
        ax.barh(y, -losses, color=RED, label="Ablation only")
        ax.axvline(0, color=GRAY, linewidth=1)
        ax.set_yticks(y, selected["component"])
        ax.set_xlabel("Paired case switches (losses left, gains right)")
        ax.set_title(f"Hit@{cutoff}")
    axes[0].set_ylabel("Removed component")
    axes[0].legend(loc="lower right")
    fig.suptitle("Paired switches distinguish net value from harmless score movement")
    save_figure(fig, "15_ablation_paired_switches")


def plot_safety_gate(metrics: pd.DataFrame) -> None:
    selected = metrics[
        metrics["experiment"].eq("ablation")
        & metrics["scope"].eq("primary_fair_unique")
        & metrics["algorithm"].isin(
            ["full_algorithm_4", "without_safety_clarification_gate"]
        )
    ].copy()
    selected["system"] = selected["algorithm"].map(
        {
            "full_algorithm_4": "Complete Algorithm 4",
            "without_safety_clarification_gate": "Safety gate removed",
        }
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    retrieval = selected.set_index("system")[["hit_at_1", "hit_at_20"]] * 100
    retrieval.plot(kind="bar", color=[BLUE, ORANGE], ax=axes[0], rot=0)
    axes[0].set_title("A. Retrieval is unchanged")
    axes[0].set_xlabel("System state")
    axes[0].set_ylabel("Recovery rate (%)")
    axes[0].set_ylim(0, 82)
    axes[0].yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    axes[0].legend(["Hit@1", "Hit@20"])
    unsafe = selected.set_index("system")["unsafe_confident_top1_rate"] * 100
    bars = axes[1].bar(unsafe.index, unsafe.values, color=[BLUE, RED])
    axes[1].set_title("B. Unsafe confidence rises")
    axes[1].set_xlabel("System state")
    axes[1].set_ylabel("Unsafe confident first results (%)")
    axes[1].set_ylim(0, 30)
    axes[1].yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    add_percent_labels(axes[1], bars, digits=2)
    fig.suptitle("The safety gate changes response behavior, not candidate ranking")
    save_figure(fig, "16_safety_gate_ablation")


def plot_tie_policies(tie_metrics: pd.DataFrame) -> None:
    selected = tie_metrics.copy()
    selected["rule_label"] = selected["rule"].map(TIE_RULE_LABELS)
    pivot = selected.pivot(index="rule_label", columns="split", values="hit_at_1")
    order = [TIE_RULE_LABELS[key] for key in TIE_RULES]
    pivot = pivot.reindex(order)
    fig, ax = plt.subplots(figsize=(12, 7))
    x = np.arange(len(pivot))
    width = 0.25
    colors = [BLUE, CYAN, ORANGE]
    for offset, split, color in zip([-width, 0, width], ["all", "development", "holdout"], colors):
        bars = ax.bar(x + offset, pivot[split] * 100, width, color=color, label=human_label(split))
        if split == "all":
            add_percent_labels(ax, bars, digits=1)
    current = float(pivot.loc[TIE_RULE_LABELS["current_model_order"], "all"] * 100)
    ax.axhline(current, color=GRAY, linestyle="--", linewidth=1, label="Current overall reference")
    ax.set_xticks(x, pivot.index, rotation=28, ha="right")
    ax.set_ylim(40, 52)
    ax.set_xlabel("Equal-distance top-order policy")
    ax.set_ylabel("Hit@1 on primary fair pairs (%)")
    ax.set_title("No generic equal-distance rule improves both development and holdout")
    ax.yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    ax.legend(loc="upper center", ncol=2)
    save_figure(fig, "17_equal_distance_policy_comparison")


def synthetic_algorithm_label(number: int) -> str:
    return ALGORITHM_LABELS[
        {
            1: "algorithm_1_current_app",
            2: "algorithm_2_external_fast",
            3: "algorithm_3_rank_fusion",
            4: "algorithm_4_family_rescue",
        }[number]
    ]


def synthetic_paired_statistics(
    synthetic_algorithms: dict[int, pd.DataFrame]
) -> pd.DataFrame:
    reference = synthetic_algorithms[4].set_index("source_row")
    output = []
    for number in [1, 2, 3]:
        comparison = synthetic_algorithms[number].set_index("source_row")
        common = reference.index.intersection(comparison.index)
        if len(common) != 115_000:
            raise ValueError(f"synthetic paired comparison has {len(common)} rows")
        for cutoff, field in [(1, "hit_at_1"), (20, "hit_at_20")]:
            effect = paired_effect(
                reference.loc[common, field],
                comparison.loc[common, field],
                seed=RANDOM_SEED + 1000 + number * 100 + cutoff,
            )
            output.append(
                {
                    "experiment": "synthetic_115000",
                    "reference": synthetic_algorithm_label(4),
                    "comparison": synthetic_algorithm_label(number),
                    "comparison_id": f"algorithm_{number}",
                    "cutoff": cutoff,
                    **effect,
                }
            )
    return pd.DataFrame(output)


def plot_synthetic_overall(category_metrics: pd.DataFrame) -> None:
    selected = category_metrics[
        category_metrics["scope"].eq("__ALL__")
        & category_metrics["category"].eq("__ALL__")
    ].copy()
    selected["label"] = selected["algorithm"].map(ALGORITHM_LABELS)
    selected = selected.sort_values("algorithm")
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    x = np.arange(len(selected))
    width = 0.25
    metric_specs = [
        ("hit_at_1", BLUE, "Hit@1"),
        ("hit_at_20", ORANGE, "Hit@20"),
        ("behavior_success_rate", CYAN, "Behavior success"),
    ]
    for offset, (field, color, label_text) in zip([-width, 0, width], metric_specs):
        bars = axes[0].bar(x + offset, selected[field] * 100, width, color=color, label=label_text)
        if field == "hit_at_1":
            add_percent_labels(axes[0], bars, digits=1)
    axes[0].set_xticks(x, [value.replace(", ", "\n") for value in selected["label"]])
    axes[0].set_ylim(65, 98)
    axes[0].set_xlabel("Search algorithm")
    axes[0].set_ylabel("Rate across 115,000 synthetic cases (%)")
    axes[0].set_title("A. Retrieval and behavior")
    axes[0].yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    axes[0].legend(loc="upper left")

    bars = axes[1].bar(
        [value.replace(", ", "\n") for value in selected["label"]],
        selected["unsafe_confident_top1_rate"] * 100,
        color=[BLUE, RED, CYAN, ORANGE],
    )
    axes[1].set_xlabel("Search algorithm")
    axes[1].set_ylabel("Unsafe confident first-result rate (%)")
    axes[1].set_title("B. Medical-safety behavior, lower is better")
    axes[1].set_ylim(0, 7.5)
    axes[1].yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    add_percent_labels(axes[1], bars, digits=2)
    fig.suptitle("Algorithm 4 has the best combined synthetic retrieval and safety result", y=1.01)
    save_figure(fig, "18_synthetic_algorithm_comparison")


def plot_synthetic_scope_heatmaps(category_metrics: pd.DataFrame) -> None:
    selected = category_metrics[
        category_metrics["category"].eq("__ALL__")
        & ~category_metrics["scope"].eq("__ALL__")
    ].copy()
    selected["algorithm_label"] = selected["algorithm"].map(ALGORITHM_LABELS)
    selected["scope_label"] = selected["scope"].map(
        {
            "inside": "Inside-catalog corruptions",
            "safety": "Safety cases",
            "semi_outside": "Context-heavy cases",
            "smoke": "Regression smoke cases",
        }
    )
    algorithm_order = [synthetic_algorithm_label(number) for number in range(1, 5)]
    scope_order = [
        "Inside-catalog corruptions",
        "Safety cases",
        "Context-heavy cases",
        "Regression smoke cases",
    ]
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for ax, field, title in [
        (axes[0], "hit_at_1", "A. Hit@1"),
        (axes[1], "hit_at_20", "B. Hit@20"),
    ]:
        matrix = selected.pivot(index="scope_label", columns="algorithm_label", values=field).reindex(index=scope_order, columns=algorithm_order) * 100
        sns.heatmap(
            matrix,
            vmin=50,
            vmax=100,
            cmap="YlGnBu",
            annot=True,
            fmt=".1f",
            linewidths=0.5,
            cbar_kws={"label": "Recovery rate (%)"},
            ax=ax,
        )
        ax.set_title(title)
        ax.set_xlabel("Search algorithm")
        ax.set_ylabel("Synthetic benchmark scope")
        ax.tick_params(axis="x", rotation=20)
        ax.tick_params(axis="y", rotation=0)
    fig.suptitle("Algorithm rankings differ by query scope, especially at rank 1", y=1.02)
    save_figure(fig, "19_synthetic_scope_performance")


def plot_synthetic_category_heatmaps(category_metrics: pd.DataFrame) -> None:
    selected = category_metrics[
        ~category_metrics["category"].eq("__ALL__")
    ].copy()
    selected["algorithm_label"] = selected["algorithm"].map(ALGORITHM_LABELS)
    selected["category_label"] = selected["category"].map(human_label)
    algorithm_order = [synthetic_algorithm_label(number) for number in range(1, 5)]
    a4_order = (
        selected[selected["algorithm"].eq("algorithm_4_family_rescue")]
        .sort_values("hit_at_1")
        ["category_label"]
        .tolist()
    )
    fig, axes = plt.subplots(1, 2, figsize=(16, 16), sharey=True)
    for ax, field, title in [
        (axes[0], "hit_at_1", "A. Hit@1 by mutation category"),
        (axes[1], "hit_at_20", "B. Hit@20 by mutation category"),
    ]:
        matrix = selected.pivot(index="category_label", columns="algorithm_label", values=field).reindex(index=a4_order, columns=algorithm_order) * 100
        sns.heatmap(
            matrix,
            vmin=0,
            vmax=100,
            cmap="YlGnBu",
            annot=True,
            fmt=".0f",
            linewidths=0.35,
            cbar_kws={"label": "Recovery rate (%)"},
            ax=ax,
        )
        ax.set_title(title)
        ax.set_xlabel("Search algorithm")
        ax.set_ylabel("Synthetic mutation category")
        ax.tick_params(axis="x", rotation=20)
        ax.tick_params(axis="y", rotation=0, labelsize=8)
    fig.suptitle("All 34 synthetic categories reveal gains and persistent structural failures", y=1.005)
    save_figure(fig, "20_all_synthetic_categories")


def plot_synthetic_failure_impact(a4: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        a4.groupby("category", observed=True)
        .agg(cases=("source_row", "size"), failures=("hit_at_20", lambda values: int((1 - values).sum())))
        .reset_index()
    )
    grouped["failure_rate"] = grouped["failures"] / grouped["cases"]
    grouped["failure_share"] = grouped["failures"] / grouped["failures"].sum()
    grouped["label"] = grouped["category"].map(human_label)
    selected = grouped.nlargest(12, "failures").sort_values("failures")
    fig, axes = plt.subplots(1, 2, figsize=(15, 8), sharey=True)
    y = np.arange(len(selected))
    rate_bars = axes[0].barh(y, selected["failure_rate"] * 100, color=ORANGE)
    axes[0].set_yticks(y, [f"{row.label} (n={row.cases:,})" for row in selected.itertuples()])
    axes[0].set_xlabel("Top-20 failure rate within category (%)")
    axes[0].set_ylabel("Mutation category")
    axes[0].set_title("A. Within-category difficulty")
    axes[0].set_xlim(0, 108)
    axes[0].xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    add_horizontal_labels(axes[0], rate_bars, percent=True)

    share_bars = axes[1].barh(y, selected["failure_share"] * 100, color=RED)
    axes[1].set_yticks(y, [f"{row.label} (misses={row.failures:,})" for row in selected.itertuples()])
    axes[1].set_xlabel("Share of all synthetic top-20 misses (%)")
    axes[1].set_ylabel("Mutation category")
    axes[1].set_title("B. Absolute benchmark impact")
    axes[1].set_xlim(0, max(selected["failure_share"].max() * 125, 10))
    axes[1].xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    add_horizontal_labels(axes[1], share_bars, percent=True)
    fig.suptitle("Failure rate and failure share produce different engineering priorities", y=1.01)
    save_figure(fig, "21_synthetic_category_failure_impact")
    return grouped


def plot_synthetic_mistake_types(a4: pd.DataFrame) -> pd.DataFrame:
    selected = a4[
        a4["mistake_type"].notna()
        & ~a4["mistake_type"].astype(str).isin(["", "none"])
    ].copy()
    grouped = (
        selected.groupby("mistake_type", observed=True)
        .agg(rows=("source_row", "size"), hit_at_20=("hit_at_20", "mean"), behavior=("behavior_success", "mean"))
        .reset_index()
    )
    order = [
        "type_1_exact_real_name_collision",
        "type_2_equal_edit_evidence",
        "type_3_unreadable_continuation",
        "type_4_family_variant",
        "type_5_candidate_generation",
        "type_6_candidate_ranking",
    ]
    grouped["sort"] = grouped["mistake_type"].map({value: index for index, value in enumerate(order)})
    grouped = grouped.sort_values("sort").drop(columns="sort")
    grouped["label"] = grouped["mistake_type"].map(MISTAKE_LABELS)
    fig, axes = plt.subplots(1, 2, figsize=(15, 7))
    bars = axes[0].barh(grouped["label"], grouped["rows"], color=BLUE)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("Rows assigned to mistake type (count)")
    axes[0].set_ylabel("Search mistake type")
    axes[0].set_title("A. Diagnostic and failed rows")
    axes[0].set_xlim(0, grouped["rows"].max() * 1.22)
    add_horizontal_labels(axes[0], bars)

    bars = axes[1].barh(grouped["label"], grouped["hit_at_20"] * 100, color=ORANGE)
    axes[1].invert_yaxis()
    axes[1].set_xlabel("Verified family recovered by rank 20 (%)")
    axes[1].set_ylabel("Search mistake type")
    axes[1].set_title("B. Retrieval state inside each type")
    axes[1].set_xlim(0, 112)
    axes[1].xaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    add_horizontal_labels(axes[1], bars, percent=True)
    fig.suptitle("Candidate-generation and candidate-ranking failures require different fixes", y=1.01)
    save_figure(fig, "22_synthetic_mistake_types")
    return grouped


def synthetic_fairness_metrics(
    synthetic_algorithms: dict[int, pd.DataFrame],
) -> pd.DataFrame:
    reference = synthetic_algorithms[4].set_index("source_row")
    fair_source_rows = reference.index[reference["scored_case"].astype(int).eq(1)]
    output = []
    for number in range(1, 5):
        algorithm = {
            1: "algorithm_1_current_app",
            2: "algorithm_2_external_fast",
            3: "algorithm_3_rank_fusion",
            4: "algorithm_4_family_rescue",
        }[number]
        frame = synthetic_algorithms[number].set_index("source_row")
        for denominator, selected in [
            ("inclusive_115000", frame),
            ("fair_collision_excluded", frame.loc[fair_source_rows]),
        ]:
            output.append(
                {
                    "algorithm": algorithm,
                    "algorithm_label": ALGORITHM_LABELS[algorithm],
                    "denominator": denominator,
                    "cases": len(selected),
                    "hit_at_1": float(selected["hit_at_1"].mean()),
                    "hit_at_20": float(selected["hit_at_20"].mean()),
                    "behavior_success": float(selected["behavior_success"].mean()),
                    "unsafe_confident_top1_rate": float(
                        selected["unsafe_confident_top1"].mean()
                    ),
                }
            )
    metrics = pd.DataFrame(output)
    inclusive = metrics[metrics["denominator"].eq("inclusive_115000")].set_index(
        "algorithm"
    )
    for field in ["hit_at_1", "hit_at_20", "behavior_success"]:
        metrics[f"delta_{field}_vs_inclusive"] = metrics.apply(
            lambda row: row[field] - inclusive.loc[row["algorithm"], field], axis=1
        )
    return metrics


def plot_synthetic_fairness(
    synthetic_algorithms: dict[int, pd.DataFrame],
) -> pd.DataFrame:
    metrics = synthetic_fairness_metrics(synthetic_algorithms)
    order = [
        "algorithm_1_current_app",
        "algorithm_2_external_fast",
        "algorithm_3_rank_fusion",
        "algorithm_4_family_rescue",
    ]
    fig, axes = plt.subplots(1, 2, figsize=(15, 7), sharey=True)
    x = np.arange(len(order))
    width = 0.34
    for ax, field, title in [
        (axes[0], "hit_at_1", "A. Correct family ranked first"),
        (axes[1], "hit_at_20", "B. Correct family recovered by rank 20"),
    ]:
        for offset, denominator, color, label_text in [
            (-width / 2, "inclusive_115000", BLUE, "Inclusive, 115,000 rows"),
            (
                width / 2,
                "fair_collision_excluded",
                ORANGE,
                "Fair, 109,974 rows",
            ),
        ]:
            selected = metrics[metrics["denominator"].eq(denominator)].set_index(
                "algorithm"
            ).reindex(order)
            bars = ax.bar(x + offset, selected[field] * 100, width, color=color, label=label_text)
            add_percent_labels(ax, bars, digits=2)
        ax.set_xticks(x, [f"Algorithm {number}" for number in range(1, 5)])
        ax.set_ylim(70, 100)
        ax.set_xlabel("Search algorithm")
        ax.set_ylabel("Recovery rate (%)")
        ax.set_title(title)
        ax.yaxis.set_major_formatter(PercentFormatter(100, decimals=0))
    axes[0].legend(loc="upper left")
    fig.suptitle(
        "Fair scoring raises every algorithm because exact real-name collisions are not single-answer questions",
        y=1.01,
    )
    save_figure(fig, "23_synthetic_fair_vs_inclusive")
    return metrics


def plot_synthetic_collision_distribution(a4: pd.DataFrame) -> pd.DataFrame:
    collisions = a4[a4["scored_case"].astype(int).eq(0)].copy()
    grouped = (
        collisions.groupby("category", observed=True)
        .agg(rows=("source_row", "size"))
        .reset_index()
        .sort_values(["rows", "category"], ascending=[False, True])
    )
    grouped["share_of_excluded_rows"] = grouped["rows"] / len(collisions)
    grouped["label"] = grouped["category"].map(human_label)
    display = grouped.sort_values("rows")
    fig, ax = plt.subplots(figsize=(12, 10))
    bars = ax.barh(display["label"], display["rows"], color=PURPLE)
    ax.set_xlabel("Excluded exact-real-name collision rows (count)")
    ax.set_ylabel("Synthetic mutation category")
    ax.set_xlim(0, display["rows"].max() * 1.20)
    ax.set_title(
        "The 5,026 fair-score exclusions are concentrated in fragmentation and autocorrect artifacts"
    )
    add_horizontal_labels(ax, bars)
    save_figure(fig, "30_synthetic_collision_distribution")
    return grouped


def plot_synthetic_overlap(synthetic_algorithms: dict[int, pd.DataFrame]) -> pd.DataFrame:
    merged = synthetic_algorithms[1][["source_row", "hit_at_20"]].rename(columns={"hit_at_20": "a1"})
    for number in [2, 3, 4]:
        merged = merged.merge(
            synthetic_algorithms[number][["source_row", "hit_at_20"]].rename(columns={"hit_at_20": f"a{number}"}),
            on="source_row",
            validate="one_to_one",
        )
    merged["pattern"] = merged.apply(
        lambda row: " ".join(
            f"A{number}" for number in range(1, 5) if int(row[f"a{number}"])
        )
        or "None",
        axis=1,
    )
    counts = merged["pattern"].value_counts().rename_axis("pattern").reset_index(name="rows")
    counts["share"] = counts["rows"] / len(merged)
    display = counts.head(8).sort_values("rows")
    fig, ax = plt.subplots(figsize=(11, 7))
    bars = ax.barh(display["pattern"], display["rows"], color=PURPLE)
    ax.set_xlabel("Synthetic cases with this Hit@20 success combination (count)")
    ax.set_ylabel("Algorithms that recover the expected family")
    ax.set_title("Most top-20 outcomes are shared, but algorithm complementarity remains")
    ax.set_xlim(0, display["rows"].max() * 1.22)
    add_horizontal_labels(ax, bars)
    save_figure(fig, "24_synthetic_recovery_overlap")
    return counts


def plot_pharmacist_assignment_balance(assignments: pd.DataFrame) -> None:
    participant = assignments.pivot_table(
        index="participant_id", columns="condition", values="case_id", aggfunc="count", fill_value=0
    ).reindex(columns=["no_tool", "drugeye", "algorithm_4"])
    case = assignments.pivot_table(
        index="case_id", columns="condition", values="participant_id", aggfunc="count", fill_value=0
    ).reindex(columns=["no_tool", "drugeye", "algorithm_4"])
    fig, axes = plt.subplots(1, 2, figsize=(14, 8))
    sns.heatmap(
        participant,
        annot=True,
        fmt="d",
        cmap="Blues",
        cbar_kws={"label": "Assigned trials (count)"},
        ax=axes[0],
    )
    axes[0].set_title("A. Each participant receives 25 trials per condition")
    axes[0].set_xlabel("Study condition")
    axes[0].set_ylabel("Anonymous participant")

    case_distribution = case.stack().value_counts().sort_index()
    bars = axes[1].bar(case_distribution.index.astype(str), case_distribution.values, color=BLUE)
    axes[1].set_title("B. Every case-condition cell has five assignments")
    axes[1].set_xlabel("Participants assigned per case and condition")
    axes[1].set_ylabel("Case-condition cells (count)")
    axes[1].bar_label(bars, padding=3)
    fig.suptitle("The pharmacist study is counterbalanced, but no response outcome exists", y=1.01)
    save_figure(fig, "25_pharmacist_assignment_balance")


def load_synthetic_algorithm_frames() -> dict[int, pd.DataFrame]:
    common_columns = [
        "source_row",
        "input",
        "expected",
        "scope",
        "category",
        "hit_at_1",
        "hit_at_20",
        "behavior_success",
        "unsafe_confident_top1",
        "candidate_pool",
    ]
    output = {}
    reference_keys: pd.DataFrame | None = None
    for number, path in SYNTHETIC_CASE_PATHS.items():
        header = pd.read_csv(path, nrows=0).columns
        optional = [
            column
            for column in ["mistake_type", "scored_case", "decision_type"]
            if column in header
        ]
        frame = pd.read_csv(path, usecols=common_columns + optional, low_memory=False)
        if len(frame) != 115_000 or not frame["source_row"].is_unique:
            raise ValueError(f"{path} does not contain 115,000 unique source rows")
        keys = frame[["source_row", "input", "expected"]].sort_values("source_row").reset_index(drop=True)
        if reference_keys is None:
            reference_keys = keys
        elif not reference_keys.equals(keys):
            raise ValueError(f"{path} is not aligned with the common synthetic cases")
        output[number] = frame
    return output


def build_report_figures_and_statistics(
    rows: list[dict[str, Any]],
    tie_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    configure_plot_style()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    for old_figure in FIGURES_DIR.glob("*.png"):
        old_figure.unlink()

    ocr = prepare_ocr_frame(rows)
    primary = primary_unique_frame(ocr)
    if len(ocr) != 595 or len(primary) != 464:
        raise ValueError(
            f"OCR denominator mismatch: {len(ocr)} observations, {len(primary)} primary"
        )
    case_results = pd.read_csv(CASE_RESULTS_PATH, low_memory=False)
    experiment_metrics = pd.read_csv(EXPERIMENT_METRICS_PATH, low_memory=False)
    paired_comparisons = pd.read_csv(PAIRED_COMPARISONS_PATH, low_memory=False)
    retrieval_primary = prepare_primary_experiment_rows(case_results, "retrieval")
    prepare_primary_experiment_rows(case_results, "ablation")
    retrieval_primary = enrich_retrieval_rows(retrieval_primary, primary)
    synthetic_algorithms = load_synthetic_algorithm_frames()
    synthetic_category_metrics = pd.read_csv(SYNTHETIC_CATEGORY_METRICS, low_memory=False)
    assignments = pd.read_csv(PHARMACIST_ASSIGNMENTS_PATH)
    tie_metrics = pd.DataFrame(tie_summaries)

    write_data_inventory(
        {
            "OCR predictions": PROJECT_ROOT / "benchmark_03_ocr/data/04_model_predictions/predictions.csv",
            "OCR search cases": DEFAULT_CASES,
            "OCR Algorithm 4 results": DEFAULT_RESULTS,
            "Retrieval and ablation rows": CASE_RESULTS_PATH,
            "Retrieval aggregate metrics": EXPERIMENT_METRICS_PATH,
            "Retrieval paired comparisons": PAIRED_COMPARISONS_PATH,
            "Synthetic test cases": SYNTHETIC_ROOT / "data/test_cases.csv",
            "Synthetic Algorithm 1 rows": SYNTHETIC_CASE_PATHS[1],
            "Synthetic Algorithm 2 rows": SYNTHETIC_CASE_PATHS[2],
            "Synthetic Algorithm 3 rows": SYNTHETIC_CASE_PATHS[3],
            "Synthetic Algorithm 4 rows": SYNTHETIC_CASE_PATHS[4],
            "Synthetic category metrics": SYNTHETIC_CATEGORY_METRICS,
            "Equal-distance evidence": pd.read_csv(
                ARTIFACTS_DIR / "equal_distance_cases.csv", low_memory=False
            ),
            "Pharmacist assignments": PHARMACIST_ASSIGNMENTS_PATH,
        }
    )

    plot_denominator_sensitivity(ocr)
    plot_ocr_composition(ocr)
    plot_model_case_mix(ocr)
    plot_distance_recovery(primary)
    plot_evidence_recovery(primary)
    plot_extreme_profile(ocr)
    correlation_matrix = plot_ocr_correlations(primary)
    interaction_metrics = plot_distance_bigram_interaction(primary)
    plot_retrieval_performance(experiment_metrics)
    retrieval_statistics = retrieval_paired_statistics(retrieval_primary)
    plot_retrieval_paired_effects(retrieval_statistics)
    efficiency = plot_efficiency_frontier(experiment_metrics)
    plot_latency_distributions(retrieval_primary)
    plot_retrieval_tradeoff_radar(experiment_metrics)
    retrieval_overlap = plot_success_overlap(retrieval_primary)
    retrieval_profiles = retrieval_profile_metrics(retrieval_primary)
    retrieval_examples = retrieval_failure_examples(retrieval_primary)
    plot_retrieval_distance_profiles(retrieval_primary)
    plot_retrieval_error_evidence_profiles(retrieval_primary)
    plot_retrieval_failure_composition(retrieval_primary)
    plot_ablation_deltas(experiment_metrics)
    plot_ablation_switches(paired_comparisons)
    plot_safety_gate(experiment_metrics)
    plot_tie_policies(tie_metrics)
    plot_synthetic_overall(synthetic_category_metrics)
    plot_synthetic_scope_heatmaps(synthetic_category_metrics)
    plot_synthetic_category_heatmaps(synthetic_category_metrics)
    synthetic_failure_impact = plot_synthetic_failure_impact(synthetic_algorithms[4])
    synthetic_mistake_types = plot_synthetic_mistake_types(synthetic_algorithms[4])
    synthetic_fairness = plot_synthetic_fairness(synthetic_algorithms)
    synthetic_overlap = plot_synthetic_overlap(synthetic_algorithms)
    synthetic_collision_distribution = plot_synthetic_collision_distribution(
        synthetic_algorithms[4]
    )
    plot_pharmacist_assignment_balance(assignments)

    synthetic_statistics = synthetic_paired_statistics(synthetic_algorithms)
    statistical_comparisons = pd.concat(
        [retrieval_statistics, synthetic_statistics], ignore_index=True
    )
    write_csv(
        RESULTS_DIR / "statistical_comparisons.csv",
        statistical_comparisons.to_dict("records"),
    )
    correlation_output = correlation_matrix.reset_index(names="field")
    write_csv(
        RESULTS_DIR / "ocr_spearman_correlations.csv",
        correlation_output.to_dict("records"),
    )
    write_csv(
        RESULTS_DIR / "distance_bigram_interaction.csv",
        interaction_metrics.to_dict("records"),
    )
    write_csv(
        RESULTS_DIR / "retrieval_overlap.csv",
        retrieval_overlap.to_dict("records"),
    )
    write_csv(
        RESULTS_DIR / "retrieval_error_profiles.csv",
        retrieval_profiles.to_dict("records"),
    )
    write_csv(
        ARTIFACTS_DIR / "retrieval_failure_examples.csv",
        retrieval_examples.to_dict("records"),
    )
    write_csv(
        RESULTS_DIR / "synthetic_fairness_by_algorithm.csv",
        synthetic_fairness.to_dict("records"),
    )
    write_csv(
        RESULTS_DIR / "synthetic_collision_distribution.csv",
        synthetic_collision_distribution.to_dict("records"),
    )
    write_csv(
        RESULTS_DIR / "synthetic_recovery_overlap.csv",
        synthetic_overlap.to_dict("records"),
    )

    development_targets = set(
        ocr.loc[ocr["split"].eq("development"), "expected_family_key"]
    )
    holdout_targets = set(
        ocr.loc[ocr["split"].eq("holdout"), "expected_family_key"]
    )
    figures = sorted(FIGURES_DIR.glob("*.png"))
    if len(figures) != 30:
        raise RuntimeError(f"expected 30 report figures, generated {len(figures)}")

    best_classical_h1 = experiment_metrics[
        experiment_metrics["experiment"].eq("retrieval")
        & experiment_metrics["scope"].eq("primary_fair_unique")
        & experiment_metrics["algorithm"].str.startswith("baseline_")
    ].nlargest(1, "hit_at_1").iloc[0]
    best_classical_h20 = experiment_metrics[
        experiment_metrics["experiment"].eq("retrieval")
        & experiment_metrics["scope"].eq("primary_fair_unique")
        & experiment_metrics["algorithm"].str.startswith("baseline_")
    ].nlargest(1, "hit_at_20").iloc[0]
    a4_retrieval = experiment_metrics[
        experiment_metrics["experiment"].eq("retrieval")
        & experiment_metrics["scope"].eq("primary_fair_unique")
        & experiment_metrics["algorithm"].eq("algorithm_4_family_rescue")
    ].iloc[0]
    rescue_ablation = experiment_metrics[
        experiment_metrics["experiment"].eq("ablation")
        & experiment_metrics["scope"].eq("primary_fair_unique")
        & experiment_metrics["algorithm"].eq("without_rescue_layer")
    ].iloc[0]
    return {
        "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
        "random_seed": RANDOM_SEED,
        "generated_figures": len(figures),
        "ocr_rows": len(ocr),
        "ocr_primary_pairs": len(primary),
        "ocr_duplicate_observations": len(ocr)
        - len(ocr.drop_duplicates(["compact_query", "expected_family_key"])),
        "target_split_overlap": len(development_targets & holdout_targets),
        "retrieval_systems": int(
            experiment_metrics[
                experiment_metrics["experiment"].eq("retrieval")
                & experiment_metrics["scope"].eq("primary_fair_unique")
            ]["algorithm"].nunique()
        ),
        "ablation_variants": int(
            experiment_metrics[
                experiment_metrics["experiment"].eq("ablation")
                & experiment_metrics["scope"].eq("primary_fair_unique")
            ]["algorithm"].nunique()
        ),
        "a4_hit_at_1": float(a4_retrieval["hit_at_1"]),
        "a4_hit_at_20": float(a4_retrieval["hit_at_20"]),
        "a4_gain_over_best_classical_hit_at_1": float(
            a4_retrieval["hit_at_1"] - best_classical_h1["hit_at_1"]
        ),
        "a4_gain_over_best_classical_hit_at_20": float(
            a4_retrieval["hit_at_20"] - best_classical_h20["hit_at_20"]
        ),
        "rescue_ablation_delta_hit_at_1": float(rescue_ablation["delta_hit_at_1"]),
        "rescue_ablation_delta_hit_at_20": float(rescue_ablation["delta_hit_at_20"]),
        "pareto_systems": efficiency.loc[efficiency["pareto"], "label"].tolist(),
        "synthetic_categories": int(
            synthetic_category_metrics.loc[
                ~synthetic_category_metrics["category"].eq("__ALL__"), "category"
            ].nunique()
        ),
        "synthetic_top_failure_category": str(
            synthetic_failure_impact.nlargest(1, "failures").iloc[0]["category"]
        ),
        "synthetic_mistake_types": int(len(synthetic_mistake_types)),
        "pharmacist_study_status": "prepared_not_executed",
        "pharmacist_trials": len(assignments),
        "unsupported_analyses": [
            "training curves: no learned-model training logs in Meeting 10 inputs",
            "calibration: retrieval systems do not emit calibrated probabilities",
            "GPU efficiency and memory: no comparable resource telemetry was logged",
            "pharmacist outcomes: assignments exist but participant responses do not",
        ],
    }


def main() -> int:
    args = parse_args()
    rows = load_joined_rows(args.cases, args.results)
    primary = deduplicate(rows, scored_only=True)
    extreme = [row for row in rows if row["analysis_cohort"] == "extreme_distance_prediction"]
    scopes = {
        "inclusive_observations": rows,
        "primary_fair_unique": primary,
        "primary_development": [row for row in primary if row["split"] == "development"],
        "primary_holdout": [row for row in primary if row["split"] == "holdout"],
        "extreme_observations": extreme,
        "extreme_primary_unique": deduplicate(extreme, scored_only=True),
    }

    metric_rows = build_metric_rows(scopes)
    denominator_rows = denominator_metrics(rows)
    tie_rows, tie_summaries = analyze_equal_distance(rows)
    synthetic_rows = experiments.read_csv(args.synthetic_results)
    synthetic_metrics = synthetic_mistake_metrics(synthetic_rows)
    synthetic_denominators = synthetic_denominator_metrics(synthetic_rows)
    write_csv(RESULTS_DIR / "analysis_metrics.csv", metric_rows)
    write_csv(RESULTS_DIR / "denominator_metrics.csv", denominator_rows)
    write_csv(RESULTS_DIR / "equal_distance_rule_metrics.csv", tie_summaries)
    write_csv(RESULTS_DIR / "synthetic_mistake_metrics.csv", synthetic_metrics)
    write_csv(
        RESULTS_DIR / "synthetic_denominator_metrics.csv",
        synthetic_denominators,
    )
    write_csv(ARTIFACTS_DIR / "equal_distance_cases.csv", tie_rows)

    report_analysis = build_report_figures_and_statistics(rows, tie_summaries)

    summary = {
        "inclusive_observations": len(rows),
        "primary_fair_unique_pairs": len(primary),
        "extreme_threshold": "normalized_edit_distance > 0.60",
        "extreme_observations": len(extreme),
        "extreme_share": round(len(extreme) / len(rows), 8),
        "normalized_exact_observations": sum(
            row["analysis_cohort"] == "normalized_exact_match" for row in rows
        ),
        "real_drug_collision_observations": sum(
            row["mistake_type"] == "real_drug_name_collision" for row in rows
        ),
        "equal_distance_primary_rank_failures": sum(
            int(row["equal_distance_rank_failure"])
            for row in tie_rows
            if int(row["is_primary_fair_unique"])
        ),
        "synthetic_cases": len(synthetic_rows),
        "synthetic_fair_cases": sum(
            int(row["scored_case"]) for row in synthetic_rows
        ),
        "synthetic_exact_real_name_collisions": sum(
            row["mistake_type"] == "type_1_exact_real_name_collision"
            for row in synthetic_rows
        ),
        "research_update": report_analysis,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

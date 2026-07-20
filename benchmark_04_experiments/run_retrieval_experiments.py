#!/usr/bin/env python3
"""Run classical retrieval baselines, Algorithms 1-4, and Algorithm 4 ablations."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator
from unittest.mock import patch

import numpy as np
from rapidfuzz import fuzz, process
from rapidfuzz.distance import JaroWinkler, Levenshtein
from sklearn.feature_extraction.text import TfidfVectorizer


BENCHMARK_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BENCHMARK_ROOT.parent
OCR_ROOT = PROJECT_ROOT / "benchmark_03_ocr"
LEGACY_ROOT = PROJECT_ROOT / "benchmark_01_legacy"
DEFAULT_CASES = OCR_ROOT / "artifacts/04_model_predictions/search_cases.csv"

for import_path in (OCR_ROOT, LEGACY_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import evaluate_current_app_search as current_app
import evaluate_search_algorithms as existing_evaluator


TOP_K = 20
SCOPES = (
    "inclusive_observations",
    "primary_fair_unique",
    "primary_development",
    "primary_holdout",
)
ABLATION_DEFINITIONS = {
    "full_algorithm_4": "No component removed.",
    "without_external_retriever": "Replace the Algorithm 2 external pass, including its cleaned-context call, with an empty response; keep family rescue.",
    "without_context_cleanup": "Suppress the second external search on strength/form/context-cleaned query text.",
    "without_rescue_layer": "Suppress the complete family-rescue pass; keep the external and context searches.",
    "without_raw_edit_similarity": "Set the unweighted normalized edit-similarity feature to zero in rescue prefiltering and family scoring; keep raw distance for conservative rank checks.",
    "without_weighted_edit_similarity": "Set the confusion-weighted normalized edit-similarity feature to zero; keep unweighted edit evidence.",
    "without_prefix_signal": "Set prefix similarity to zero in prefiltering, family scoring, edge evidence, and correction logic.",
    "without_suffix_signal": "Set suffix similarity to zero in prefiltering, family scoring, edge evidence, and correction logic.",
    "without_ngram_signal": "Remove character 2-, 3-, and 4-gram candidate retrieval and rescue scoring.",
    "without_phonetic_signal": "Remove the query phonetic key from rescue candidate retrieval and scoring.",
    "without_skeleton_signal": "Remove the consonant-skeleton key from rescue candidate retrieval and scoring.",
    "without_subsequence_signal": "Set ordered-subsequence similarity to zero in rescue prefiltering and family scoring.",
    "without_positional_signal": "Set same-position character evidence to zero in rescue scoring and conservative corrections.",
    "without_length_coverage_signal": "Set query-to-family length coverage to zero in rescue scoring.",
    "without_delete_key_retrieval": "Remove deletion-key lookup for full-family and variant-head candidates.",
    "without_short_edge_retrieval": "Remove the short-query prefix and suffix candidate-retrieval pass.",
    "without_confusable_first_character_expansion": "Remove first-character confusion expansions from candidate retrieval and plausibility checks; exact first-character equality remains.",
    "without_length_bucket_scan": "Suppress fallback scanning of compatible-length family buckets.",
    "without_variant_head_rescue": "Suppress matching against validated catalog family heads and variants.",
    "without_weighted_confusion_cost": "Set every non-identical substitution cost to one, removing reduced costs for known phonetic/vowel confusions.",
    "without_retrieval_agreement_bonus": "Remove score bonuses for external/context and external/rescue agreement while retaining each retriever's candidates.",
    "without_strict_full_name_correction": "Suppress the bounded rescue-only promotion of a full-name candidate that is strictly closer than the current first result.",
    "without_conservative_reranker": "Keep the merged score order and suppress evidence-backed top-rank corrections.",
    "without_safety_clarification_gate": "Allow candidates through without Algorithm 4's always-clarify safety gate; retrieval ranking is unchanged.",
}


@dataclass(frozen=True)
class Family:
    key: str
    name: str
    normalized: str
    phonetic: str


@dataclass
class PreparedRunner:
    name: str
    run: Callable[[str], dict[str, Any]]
    preparation_ms: float
    definition: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument(
        "--experiment",
        choices=("all", "retrieval", "ablation"),
        default="all",
    )
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"refusing to write empty table: {path}")
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_cases(path: Path, limit: int) -> list[dict[str, str]]:
    cases = [row for row in read_csv(path) if row.get("accepted") == "1"]
    cases.sort(key=lambda row: (row.get("split", ""), row.get("case_id", "")))
    if limit:
        cases = cases[:limit]
    if not cases:
        raise ValueError("no accepted OCR cases were loaded")
    return cases


def build_families(records: list[dict[str, Any]]) -> list[Family]:
    names: dict[str, str] = {}
    for record in records:
        name = str(record.get("b") or record.get("n") or "").strip()
        key = current_app.compact_key(name)
        if key and key not in names:
            names[key] = name
    return [
        Family(
            key=key,
            name=names[key],
            normalized=current_app.normalize_search(names[key]),
            phonetic=current_app.drug_phonetic_key(names[key]),
        )
        for key in sorted(names, key=lambda value: (names[value], value))
    ]


def response(names: list[str], candidate_count: int) -> dict[str, Any]:
    return {
        "status": "ambiguous" if names else "no_match",
        "decision_type": "ranked_candidates" if names else "no_match",
        "candidate_count": candidate_count,
        "results": [
            {"name": name, "needs_clarification": True}
            for name in names[:TOP_K]
        ],
    }


def prepare_exact_prefix(families: list[Family]) -> PreparedRunner:
    started = time.perf_counter()
    by_exact: dict[str, list[Family]] = {}
    for family in families:
        by_exact.setdefault(family.key, []).append(family)

    def run(query: str) -> dict[str, Any]:
        key = current_app.compact_key(query)
        if not key:
            return response([], 0)
        exact = by_exact.get(key, [])
        prefix = [family for family in families if family.key.startswith(key) and family.key != key]
        prefix.sort(key=lambda family: (len(family.key) - len(key), family.name))
        ranked = [*exact, *prefix]
        return response([family.name for family in ranked], len(ranked))

    return PreparedRunner(
        "baseline_exact_prefix",
        run,
        (time.perf_counter() - started) * 1000,
        "Exact compact match first, then catalog families beginning with the compact query.",
    )


def rapidfuzz_runner(
    name: str,
    families: list[Family],
    choices: list[str],
    scorer: Callable[..., float],
    definition: str,
) -> PreparedRunner:
    started = time.perf_counter()

    def run(query: str) -> dict[str, Any]:
        compact = current_app.compact_key(query)
        if not compact:
            return response([], 0)
        matches = process.extract(compact, choices, scorer=scorer, limit=TOP_K)
        return response([families[index].name for _, _, index in matches], len(families))

    return PreparedRunner(name, run, (time.perf_counter() - started) * 1000, definition)


def prepare_token_ratio(families: list[Family]) -> PreparedRunner:
    started = time.perf_counter()
    choices = [family.normalized for family in families]

    def run(query: str) -> dict[str, Any]:
        normalized = current_app.normalize_search(query)
        if not normalized:
            return response([], 0)
        matches = process.extract(normalized, choices, scorer=fuzz.token_ratio, limit=TOP_K)
        return response([families[index].name for _, _, index in matches], len(families))

    return PreparedRunner(
        "baseline_rapidfuzz_token_ratio",
        run,
        (time.perf_counter() - started) * 1000,
        "RapidFuzz token_ratio, the maximum of token-set and token-sort ratios.",
    )


def prepare_phonetic(families: list[Family]) -> PreparedRunner:
    started = time.perf_counter()
    phonetic_choices = [family.phonetic for family in families]

    def run(query: str) -> dict[str, Any]:
        key = current_app.drug_phonetic_key(query)
        if not key:
            return response([], 0)
        matches = process.extract(
            key,
            phonetic_choices,
            scorer=Levenshtein.distance,
            limit=TOP_K,
        )
        return response([families[index].name for _, _, index in matches], len(families))

    return PreparedRunner(
        "baseline_phonetic",
        run,
        (time.perf_counter() - started) * 1000,
        "Egyptian-medicine phonetic key ranked by unweighted Levenshtein distance between keys.",
    )


def prepare_char_tfidf(families: list[Family]) -> PreparedRunner:
    started = time.perf_counter()
    vectorizer = TfidfVectorizer(
        analyzer="char",
        ngram_range=(3, 3),
        lowercase=False,
        norm="l2",
        dtype=np.float64,
    )
    matrix = vectorizer.fit_transform([family.key for family in families])

    def run(query: str) -> dict[str, Any]:
        key = current_app.compact_key(query)
        if len(key) < 3:
            return response([], 0)
        query_vector = vectorizer.transform([key])
        scores = (matrix @ query_vector.T).toarray().ravel()
        nonzero = np.flatnonzero(scores > 0)
        if not len(nonzero):
            return response([], 0)
        shortlist_size = min(max(TOP_K * 4, TOP_K), len(nonzero))
        if len(nonzero) > shortlist_size:
            selected = nonzero[np.argpartition(scores[nonzero], -shortlist_size)[-shortlist_size:]]
        else:
            selected = nonzero
        ranked = sorted(selected, key=lambda index: (-scores[index], families[index].name))[:TOP_K]
        return response([families[index].name for index in ranked], len(nonzero))

    return PreparedRunner(
        "baseline_char_3gram_tfidf",
        run,
        (time.perf_counter() - started) * 1000,
        "Cosine similarity over L2-normalized TF-IDF vectors of compact character trigrams.",
    )


def prepare_existing_algorithms(records: list[dict[str, Any]]) -> list[PreparedRunner]:
    runners: list[PreparedRunner] = []
    definitions = {
        "algorithm_1_current_app": "Algorithm 1, current application candidate generation and safety ranking.",
        "algorithm_2_external_fast": "Algorithm 2, external English fast lexical search.",
        "algorithm_3_rank_fusion": "Algorithm 3, weighted rank fusion of Algorithms 1 and 2.",
        "algorithm_4_family_rescue": "Algorithm 4, Algorithm 2 plus family-level rescue and conservative reranking.",
    }
    for number in ("1", "2", "3", "4"):
        started = time.perf_counter()
        prepared = existing_evaluator.prepare_algorithms({number}, records)
        preparation_ms = (time.perf_counter() - started) * 1000
        for name, run in prepared.items():
            runners.append(PreparedRunner(name, run, preparation_ms, definitions[name]))
    return runners


def prepare_retrieval_runners(records: list[dict[str, Any]]) -> list[PreparedRunner]:
    families = build_families(records)
    compact_choices = [family.key for family in families]
    return [
        prepare_exact_prefix(families),
        rapidfuzz_runner(
            "baseline_levenshtein",
            families,
            compact_choices,
            Levenshtein.distance,
            "Exhaustive unweighted Levenshtein distance over all compact family names.",
        ),
        rapidfuzz_runner(
            "baseline_jaro_winkler",
            families,
            compact_choices,
            JaroWinkler.similarity,
            "Exhaustive Jaro-Winkler similarity over all compact family names.",
        ),
        prepare_char_tfidf(families),
        prepare_token_ratio(families),
        prepare_phonetic(families),
        *prepare_existing_algorithms(records),
    ]


def result_name(item: dict[str, Any]) -> str:
    return str(
        item.get("name")
        or item.get("candidate_canonical_name")
        or item.get("canonical_name")
        or item.get("commercial_name")
        or ""
    ).strip()


def evaluate_case(
    case: dict[str, str],
    algorithm: str,
    runner: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    started = time.perf_counter()
    output = runner(case["input"])
    latency_ms = (time.perf_counter() - started) * 1000
    results = list(output.get("results") or [])[:TOP_K]
    names = [result_name(item) for item in results]
    expected = {key for key in case["expected_family_key"].split(";") if key}
    relevant = [
        rank
        for rank, name in enumerate(names, 1)
        if current_app.compact_key(name) in expected
    ]
    rank = relevant[0] if relevant else 999
    top_clarifies = bool(results and results[0].get("needs_clarification"))
    status = str(output.get("status") or "")
    confident = status in {"high_confidence", "medium_confidence"} and not top_clarifies
    return {
        "case_id": case["case_id"],
        "sample_id": case["sample_id"],
        "split": case["split"],
        "input": case["input"],
        "expected_family_name": case["expected_family_name"],
        "expected_family_key": case["expected_family_key"],
        "scored_case": int(case.get("scored_case", "1")),
        "analysis_cohort": case.get("analysis_cohort", ""),
        "distance_band": case.get("distance_band", ""),
        "mistake_type": case.get("mistake_type", ""),
        "difficulty": case.get("difficulty", ""),
        "danger": case.get("danger", ""),
        "edit_distance": case.get("edit_distance", ""),
        "normalized_edit_distance": case.get("normalized_edit_distance", ""),
        "algorithm": algorithm,
        "first_relevant_rank": rank,
        "hit_at_1": int(rank <= 1),
        "hit_at_5": int(rank <= 5),
        "hit_at_10": int(rank <= 10),
        "hit_at_20": int(rank <= 20),
        "reciprocal_rank_at_20": round(1 / rank, 8) if rank <= 20 else 0.0,
        "unsafe_confident_top1": int(confident and rank != 1),
        "needs_clarification": int(bool(results) and (top_clarifies or not confident)),
        "latency_ms": round(latency_ms, 4),
        "candidate_count": int(output.get("candidate_count") or len(results)),
        "top_1": names[0] if names else "",
        "top_5": ";".join(names[:5]),
        "top_20": ";".join(names),
    }


def rows_for_scope(rows: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    if scope == "inclusive_observations":
        return rows
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (current_app.compact_key(row["input"]), str(row["expected_family_key"]))
        if key in seen or not int(row["scored_case"]):
            continue
        seen.add(key)
        unique.append(row)
    if scope == "primary_fair_unique":
        return unique
    split = scope.removeprefix("primary_")
    return [row for row in unique if row["split"] == split]


def metric_row(
    experiment: str,
    algorithm: str,
    scope: str,
    rows: list[dict[str, Any]],
    preparation_ms: float,
) -> dict[str, Any]:
    latencies = [float(row["latency_ms"]) for row in rows]
    count = len(rows)
    return {
        "experiment": experiment,
        "algorithm": algorithm,
        "scope": scope,
        "cases": count,
        "hit_at_1": round(sum(row["hit_at_1"] for row in rows) / count, 6),
        "hit_at_5": round(sum(row["hit_at_5"] for row in rows) / count, 6),
        "hit_at_10": round(sum(row["hit_at_10"] for row in rows) / count, 6),
        "hit_at_20": round(sum(row["hit_at_20"] for row in rows) / count, 6),
        "mrr_at_20": round(sum(row["reciprocal_rank_at_20"] for row in rows) / count, 6),
        "unsafe_confident_top1_rate": round(
            sum(row["unsafe_confident_top1"] for row in rows) / count,
            6,
        ),
        "clarification_rate": round(sum(row["needs_clarification"] for row in rows) / count, 6),
        "mean_latency_ms": round(statistics.fmean(latencies), 4),
        "median_latency_ms": round(statistics.median(latencies), 4),
        "preparation_ms": round(preparation_ms, 3),
    }


def evaluate_runners(
    experiment: str,
    cases: list[dict[str, str]],
    runners: list[PreparedRunner],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    case_rows: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    for prepared in runners:
        algorithm_rows = [
            {
                "experiment": experiment,
                **evaluate_case(case, prepared.name, prepared.run),
            }
            for case in cases
        ]
        case_rows.extend(algorithm_rows)
        for scope in SCOPES:
            scoped = rows_for_scope(algorithm_rows, scope)
            if not scoped:
                continue
            metrics.append(
                metric_row(
                    experiment,
                    prepared.name,
                    scope,
                    scoped,
                    prepared.preparation_ms,
                )
            )
        primary = rows_for_scope(algorithm_rows, "primary_fair_unique")
        for field in ("analysis_cohort", "distance_band", "mistake_type"):
            for value in sorted({str(row[field]) for row in primary}):
                scoped = [row for row in primary if row[field] == value]
                metrics.append(
                    metric_row(
                        experiment,
                        prepared.name,
                        f"primary_{field}:{value}",
                        scoped,
                        prepared.preparation_ms,
                    )
                )
    return case_rows, metrics


def load_algorithm_4() -> tuple[Any, Any, float]:
    started = time.perf_counter()
    module = existing_evaluator.load_module(
        LEGACY_ROOT / "master_algorithms/algorithm_4_commercial_name_search.py",
        "benchmark_04_algorithm_4",
    )
    catalog = module.prepare_catalog()
    return module, catalog, (time.perf_counter() - started) * 1000


def plain_rank(module: Any) -> Callable[..., list[Any]]:
    def rank(candidates: list[Any], compact: str, *, brand_like: bool) -> list[Any]:
        del compact, brand_like
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
    def similarity(left: str, right: str, *, weighted: bool) -> float:
        if weighted == remove_weighted:
            return 0.0
        return original(left, right, weighted=weighted)

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


@contextmanager
def apply_ablation(module: Any, catalog: Any, component: str) -> Iterator[None]:
    with ExitStack() as stack:
        if component == "full_algorithm_4":
            yield
            return
        if component == "without_external_retriever":
            stack.enter_context(
                patch.object(
                    catalog.external_module,
                    "search_catalog",
                    lambda *_args, **_kwargs: {
                        "status": "no_match",
                        "candidate_count": 0,
                        "results": [],
                    },
                )
            )
        elif component == "without_context_cleanup":
            stack.enter_context(patch.object(module, "should_run_context_search", lambda *_args: False))
        elif component == "without_rescue_layer":
            stack.enter_context(patch.object(module, "should_run_rescue", lambda *_args: False))
        elif component == "without_raw_edit_similarity":
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
        elif component == "without_weighted_edit_similarity":
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
        elif component == "without_prefix_signal":
            stack.enter_context(patch.object(module, "prefix_score", lambda *_args: 0.0))
        elif component == "without_suffix_signal":
            stack.enter_context(patch.object(module, "suffix_score", lambda *_args: 0.0))
        elif component == "without_ngram_signal":
            stack.enter_context(patch.object(module, "char_ngrams", lambda *_args: set()))
        elif component == "without_phonetic_signal":
            stack.enter_context(patch.object(module.current_eval, "drug_phonetic_key", lambda *_args: ""))
        elif component == "without_skeleton_signal":
            stack.enter_context(patch.object(module.current_eval, "skeleton", lambda *_args: ""))
        elif component == "without_subsequence_signal":
            stack.enter_context(patch.object(module, "subsequence_score", lambda *_args: 0.0))
        elif component == "without_positional_signal":
            stack.enter_context(patch.object(module, "same_position_score", lambda *_args: 0.0))
        elif component == "without_length_coverage_signal":
            stack.enter_context(patch.object(module, "length_coverage", lambda *_args: 0.0))
        elif component == "without_delete_key_retrieval":
            stack.enter_context(patch.object(module, "delete_keys", lambda *_args: set()))
        elif component == "without_short_edge_retrieval":
            stack.enter_context(patch.object(module, "short_edge_family_ids", lambda *_args: set()))
        elif component == "without_confusable_first_character_expansion":
            stack.enter_context(patch.object(module, "first_char_variants", lambda *_args: set()))
            stack.enter_context(patch.object(module, "first_chars_confusable", lambda *_args: False))
        elif component == "without_length_bucket_scan":
            stack.enter_context(patch.object(module, "should_length_scan", lambda *_args: False))
        elif component == "without_variant_head_rescue":
            stack.enter_context(patch.object(module, "should_run_head_rescue", lambda *_args: False))
        elif component == "without_weighted_confusion_cost":
            stack.enter_context(
                patch.object(
                    module,
                    "substitution_cost",
                    lambda left, right: 0.0 if left == right else 1.0,
                )
            )
        elif component == "without_retrieval_agreement_bonus":
            stack.enter_context(
                patch.object(module, "merge_candidates", merge_without_agreement(module))
            )
        elif component == "without_strict_full_name_correction":
            stack.enter_context(
                patch.object(
                    module,
                    "promote_strictly_closer_full_name",
                    lambda ranked, _compact: ranked,
                )
            )
        elif component == "without_conservative_reranker":
            stack.enter_context(patch.object(module, "rank_candidates", plain_rank(module)))
        elif component == "without_safety_clarification_gate":
            stack.enter_context(
                patch.object(module, "needs_clarification", lambda *_args: False)
            )
        else:
            raise ValueError(f"unknown ablation: {component}")
        yield


def prepare_ablation_runners() -> list[PreparedRunner]:
    module, catalog, preparation_ms = load_algorithm_4()
    components = [
        "full_algorithm_4",
        "without_external_retriever",
        "without_context_cleanup",
        "without_rescue_layer",
        "without_raw_edit_similarity",
        "without_weighted_edit_similarity",
        "without_prefix_signal",
        "without_suffix_signal",
        "without_ngram_signal",
        "without_phonetic_signal",
        "without_skeleton_signal",
        "without_subsequence_signal",
        "without_positional_signal",
        "without_length_coverage_signal",
        "without_delete_key_retrieval",
        "without_short_edge_retrieval",
        "without_confusable_first_character_expansion",
        "without_length_bucket_scan",
        "without_variant_head_rescue",
        "without_weighted_confusion_cost",
        "without_retrieval_agreement_bonus",
        "without_strict_full_name_correction",
        "without_conservative_reranker",
        "without_safety_clarification_gate",
    ]
    runners: list[PreparedRunner] = []
    for component in components:
        def run(query: str, disabled: str = component) -> dict[str, Any]:
            with apply_ablation(module, catalog, disabled):
                return module.search_catalog(catalog, query, TOP_K)

        runners.append(
            PreparedRunner(
                component,
                run,
                preparation_ms,
                ABLATION_DEFINITIONS[component],
            )
        )
    return runners


def add_ablation_deltas(metrics: list[dict[str, Any]]) -> None:
    full = {
        row["scope"]: row
        for row in metrics
        if row["algorithm"] == "full_algorithm_4"
    }
    for row in metrics:
        baseline = full[row["scope"]]
        row["delta_hit_at_1"] = round(row["hit_at_1"] - baseline["hit_at_1"], 6)
        row["delta_hit_at_20"] = round(row["hit_at_20"] - baseline["hit_at_20"], 6)
        row["delta_mrr_at_20"] = round(row["mrr_at_20"] - baseline["mrr_at_20"], 6)
        row["delta_mean_latency_ms"] = round(
            row["mean_latency_ms"] - baseline["mean_latency_ms"],
            4,
        )


def validate_metric_coverage(metrics: list[dict[str, Any]]) -> None:
    """Require every algorithm in an experiment to expose identical groups."""

    for experiment in sorted({str(row["experiment"]) for row in metrics}):
        experiment_rows = [row for row in metrics if row["experiment"] == experiment]
        algorithms = sorted({str(row["algorithm"]) for row in experiment_rows})
        if not algorithms:
            raise ValueError(f"{experiment}: no algorithms were evaluated")
        reference = {
            (str(row["scope"]), int(row["cases"]))
            for row in experiment_rows
            if row["algorithm"] == algorithms[0]
        }
        for algorithm in algorithms[1:]:
            observed = {
                (str(row["scope"]), int(row["cases"]))
                for row in experiment_rows
                if row["algorithm"] == algorithm
            }
            if observed != reference:
                missing = sorted(reference - observed)
                extra = sorted(observed - reference)
                raise ValueError(
                    f"{experiment}/{algorithm}: metric coverage mismatch; "
                    f"missing={missing}, extra={extra}"
                )


def exact_mcnemar_p(reference_only: int, comparison_only: int) -> float:
    """Return the two-sided exact McNemar p-value for discordant pairs."""

    discordant = reference_only + comparison_only
    if not discordant:
        return 1.0
    smaller = min(reference_only, comparison_only)
    tail = sum(math.comb(discordant, value) for value in range(smaller + 1)) / (2 ** discordant)
    return min(1.0, 2 * tail)


def paired_comparisons(
    experiment: str,
    rows: list[dict[str, Any]],
    reference_algorithm: str,
) -> list[dict[str, Any]]:
    """Compare each algorithm with the reference on identical primary pairs."""

    by_algorithm: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for algorithm in sorted({str(row["algorithm"]) for row in rows}):
        scoped = rows_for_scope(
            [row for row in rows if row["algorithm"] == algorithm],
            "primary_fair_unique",
        )
        by_algorithm[algorithm] = {
            (current_app.compact_key(row["input"]), str(row["expected_family_key"])): row
            for row in scoped
        }
    reference = by_algorithm[reference_algorithm]
    output = []
    for algorithm, comparison in by_algorithm.items():
        if algorithm == reference_algorithm:
            continue
        if comparison.keys() != reference.keys():
            raise ValueError(
                f"{experiment}/{algorithm}: paired case IDs do not match "
                f"{reference_algorithm}"
            )
        keys = sorted(reference.keys() & comparison.keys())
        result: dict[str, Any] = {
            "experiment": experiment,
            "reference_algorithm": reference_algorithm,
            "comparison_algorithm": algorithm,
            "paired_cases": len(keys),
        }
        for cutoff in (1, 20):
            field = f"hit_at_{cutoff}"
            reference_only = sum(
                int(reference[key][field] == 1 and comparison[key][field] == 0)
                for key in keys
            )
            comparison_only = sum(
                int(reference[key][field] == 0 and comparison[key][field] == 1)
                for key in keys
            )
            result[f"reference_only_hit_at_{cutoff}"] = reference_only
            result[f"comparison_only_hit_at_{cutoff}"] = comparison_only
            result[f"net_reference_wins_hit_at_{cutoff}"] = reference_only - comparison_only
            result[f"mcnemar_exact_p_hit_at_{cutoff}"] = exact_mcnemar_p(
                reference_only,
                comparison_only,
            )
        output.append(result)
    return output


def comparison_examples(
    experiment: str,
    rows: list[dict[str, Any]],
    reference_algorithm: str,
    per_direction: int = 3,
) -> list[dict[str, Any]]:
    by_algorithm: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for algorithm in sorted({str(row["algorithm"]) for row in rows}):
        scoped = rows_for_scope(
            [row for row in rows if row["algorithm"] == algorithm],
            "primary_fair_unique",
        )
        by_algorithm[algorithm] = {
            (current_app.compact_key(row["input"]), str(row["expected_family_key"])): row
            for row in scoped
        }
    reference = by_algorithm[reference_algorithm]
    output = []
    for algorithm, comparison in by_algorithm.items():
        if algorithm == reference_algorithm:
            continue
        for cutoff in (1, 20):
            field = f"hit_at_{cutoff}"
            directions = (
                ("reference_only", 1, 0),
                ("comparison_only", 0, 1),
            )
            for direction, reference_value, comparison_value in directions:
                matching = [
                    key
                    for key in reference.keys() & comparison.keys()
                    if reference[key][field] == reference_value
                    and comparison[key][field] == comparison_value
                ]
                matching.sort(
                    key=lambda key: (
                        reference[key]["analysis_cohort"],
                        reference[key]["distance_band"],
                        reference[key]["case_id"],
                    )
                )
                for key in matching[:per_direction]:
                    reference_row = reference[key]
                    comparison_row = comparison[key]
                    output.append(
                        {
                            "experiment": experiment,
                            "reference_algorithm": reference_algorithm,
                            "comparison_algorithm": algorithm,
                            "cutoff": cutoff,
                            "direction": direction,
                            "case_id": reference_row["case_id"],
                            "input": reference_row["input"],
                            "expected_family_name": reference_row["expected_family_name"],
                            "analysis_cohort": reference_row["analysis_cohort"],
                            "distance_band": reference_row["distance_band"],
                            "reference_rank": reference_row["first_relevant_rank"],
                            "comparison_rank": comparison_row["first_relevant_rank"],
                            "reference_top_1": reference_row["top_1"],
                            "comparison_top_1": comparison_row["top_1"],
                        }
                    )
    return output


def percent(value: Any) -> str:
    return f"{100 * float(value):.2f}%"


def markdown_table(rows: list[dict[str, Any]], ablation: bool = False) -> str:
    if ablation:
        lines = [
            "| Variant | n | Hit@1 | Hit@20 | MRR@20 | Delta H@1 | Delta H@20 | Mean ms/query |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for row in rows:
            lines.append(
                f"| {row['algorithm']} | {int(row['cases'])} | {percent(row['hit_at_1'])} | "
                f"{percent(row['hit_at_20'])} | {row['mrr_at_20']:.4f} | "
                f"{100 * row['delta_hit_at_1']:+.2f} pp | {100 * row['delta_hit_at_20']:+.2f} pp | "
                f"{row['mean_latency_ms']:.2f} |"
            )
        return "\n".join(lines)
    lines = [
        "| Algorithm | n | Hit@1 | Hit@5 | Hit@20 | MRR@20 | Mean ms/query | Build ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['algorithm']} | {int(row['cases'])} | {percent(row['hit_at_1'])} | "
            f"{percent(row['hit_at_5'])} | {percent(row['hit_at_20'])} | "
            f"{row['mrr_at_20']:.4f} | {row['mean_latency_ms']:.2f} | {row['preparation_ms']:.1f} |"
        )
    return "\n".join(lines)


def paired_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Comparison | Ref-only H@1 | Other-only H@1 | Exact p | Ref-only H@20 | Other-only H@20 | Exact p |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['comparison_algorithm']} | {int(row['reference_only_hit_at_1'])} | "
            f"{int(row['comparison_only_hit_at_1'])} | {row['mcnemar_exact_p_hit_at_1']:.4g} | "
            f"{int(row['reference_only_hit_at_20'])} | {int(row['comparison_only_hit_at_20'])} | "
            f"{row['mcnemar_exact_p_hit_at_20']:.4g} |"
        )
    return "\n".join(lines)


def example_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Other system | Input | Expected | Outcome | Reference rank | Other rank | Reference top 1 | Other top 1 |",
        "|---|---|---|---|---:|---:|---|---|",
    ]
    for row in rows:
        direction = "reference only" if row["direction"] == "reference_only" else "other only"
        outcome = f"{direction} at Hit@{int(row['cutoff'])}"
        lines.append(
            f"| `{row['comparison_algorithm']}` | `{row['input']}` | `{row['expected_family_name']}` | {outcome} | "
            f"{int(row['reference_rank'])} | {int(row['comparison_rank'])} | "
            f"`{row['reference_top_1']}` | `{row['comparison_top_1']}` |"
        )
    return "\n".join(lines)


def write_report(
    retrieval_metrics: list[dict[str, Any]],
    ablation_metrics: list[dict[str, Any]],
    definitions: dict[str, str],
    retrieval_pairs: list[dict[str, Any]],
    ablation_pairs: list[dict[str, Any]],
    retrieval_examples: list[dict[str, Any]],
    ablation_examples: list[dict[str, Any]],
) -> None:
    lines = [
        "# Retrieval Baselines and Algorithm 4 Ablations",
        "",
        "## Evaluation contract",
        "",
        "The primary comparison uses 464 distinct scored compact query-target pairs. The inclusive view keeps all 595 OCR observations, including repeats and 17 real-drug-name collisions. Index construction happens once and is excluded from per-query latency.",
        "",
        "Hit@1 means the verified commercial family is first. Hit@20 means it appears anywhere in the first 20. MRR@20 rewards earlier relevant ranks and gives zero to top-20 misses.",
        "",
    ]
    if retrieval_metrics:
        primary = [row for row in retrieval_metrics if row["scope"] == "primary_fair_unique"]
        primary.sort(key=lambda row: (-row["hit_at_1"], -row["hit_at_20"], row["algorithm"]))
        primary_by_name = {row["algorithm"]: row for row in primary}
        a4 = primary_by_name["algorithm_4_family_rescue"]
        levenshtein = primary_by_name["baseline_levenshtein"]
        jaro = primary_by_name["baseline_jaro_winkler"]
        lines.extend(["## Experiment 1: retrieval methods", "", markdown_table(primary), "", "### Method definitions", ""])
        for algorithm in sorted(definitions):
            lines.append(f"- `{algorithm}`: {definitions[algorithm]}")
        lines.extend(
            [
                "",
                "### Paired comparison with Algorithm 4",
                "",
                "Reference-only counts are pairs recovered by A4 but missed by the comparison. Other-only counts are the reverse. The exact McNemar p-value tests whether the discordant counts are balanced; it does not measure effect size. P-values are exploratory and are not adjusted for multiple comparisons.",
                "",
                paired_markdown(retrieval_pairs),
                "",
                (
                    f"A4 exceeds the strongest classical Hit@1 baseline, exhaustive Levenshtein, by "
                    f"{100 * (a4['hit_at_1'] - levenshtein['hit_at_1']):.2f} percentage points. "
                    f"Jaro-Winkler is the strongest classical Hit@20 baseline; A4 leads it by "
                    f"{100 * (a4['hit_at_20'] - jaro['hit_at_20']):.2f} points."
                ),
                "",
                "### Concrete ranking switches",
                "",
                "The reference is Algorithm 4; the other system is exhaustive Levenshtein.",
                "",
                example_markdown(
                    [
                        row
                        for row in retrieval_examples
                        if row["comparison_algorithm"] == "baseline_levenshtein"
                        and row["cutoff"] == 1
                    ]
                ),
                "",
            ]
        )
    if ablation_metrics:
        primary = [row for row in ablation_metrics if row["scope"] == "primary_fair_unique"]
        primary.sort(key=lambda row: (row["algorithm"] != "full_algorithm_4", row["algorithm"]))
        pairs_by_name = {row["comparison_algorithm"]: row for row in ablation_pairs}
        rescue_pair = pairs_by_name["without_rescue_layer"]
        phonetic_pair = pairs_by_name["without_phonetic_signal"]
        lines.extend(
            [
                "## Experiment 2: Algorithm 4 one-component ablations",
                "",
                "Each row disables exactly the named query-time component. Negative deltas mean the complete A4 is better; positive deltas mean the ablation performed better and the removed component needs review.",
                "",
                markdown_table(primary, ablation=True),
                "",
                "### Exact removal made by each ablation",
                "",
                *[
                    f"- `{name}`: {definition}"
                    for name, definition in ABLATION_DEFINITIONS.items()
                ],
                "",
                "### Paired switches from full Algorithm 4",
                "",
                paired_markdown(ablation_pairs),
                "",
                (
                    f"Removing the rescue layer loses {int(rescue_pair['net_reference_wins_hit_at_1'])} net Hit@1 pairs "
                    f"and {int(rescue_pair['net_reference_wins_hit_at_20'])} net Hit@20 pairs. Removing phonetic evidence "
                    f"produces only {int(abs(phonetic_pair['net_reference_wins_hit_at_1']))} net switches in the opposite "
                    f"direction, with exact p={phonetic_pair['mcnemar_exact_p_hit_at_1']:.3f}; this is not evidence "
                    f"for deleting the phonetic component."
                ),
                "",
                "### Concrete component switches",
                "",
                "The reference is full Algorithm 4; examples compare it with the named ablation.",
                "",
                example_markdown(
                    [
                        row
                        for row in ablation_examples
                        if row["comparison_algorithm"]
                        in {"without_rescue_layer", "without_conservative_reranker"}
                        and row["cutoff"] == 1
                    ]
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation limits",
            "",
            "The OCR models supplied unequal cases, so these experiments compare search methods on a fixed query set, not OCR model quality. Classical baselines always request clarification; their unsafe-confidence rate is therefore not comparable with a product that emits confident decisions. The pharmacist study remains unexecuted until real participants complete the protocol.",
            "",
        ]
    )
    path = BENCHMARK_ROOT / "results/report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    cases = load_cases(args.cases, args.limit)
    records = current_app.prepare_records()
    definitions: dict[str, str] = {}
    retrieval_metrics: list[dict[str, Any]] = []
    ablation_metrics: list[dict[str, Any]] = []
    retrieval_pairs: list[dict[str, Any]] = []
    ablation_pairs: list[dict[str, Any]] = []
    retrieval_examples: list[dict[str, Any]] = []
    ablation_examples: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []

    if args.experiment in {"all", "retrieval"}:
        runners = prepare_retrieval_runners(records)
        definitions.update({runner.name: runner.definition for runner in runners})
        rows, retrieval_metrics = evaluate_runners("retrieval", cases, runners)
        retrieval_pairs = paired_comparisons(
            "retrieval",
            rows,
            "algorithm_4_family_rescue",
        )
        retrieval_examples = comparison_examples(
            "retrieval",
            rows,
            "algorithm_4_family_rescue",
        )
        case_rows.extend(rows)

    if args.experiment in {"all", "ablation"}:
        runners = prepare_ablation_runners()
        rows, ablation_metrics = evaluate_runners("ablation", cases, runners)
        add_ablation_deltas(ablation_metrics)
        ablation_pairs = paired_comparisons("ablation", rows, "full_algorithm_4")
        ablation_examples = comparison_examples(
            "ablation",
            rows,
            "full_algorithm_4",
        )
        case_rows.extend(rows)

    all_metrics = [*retrieval_metrics, *ablation_metrics]
    validate_metric_coverage(all_metrics)
    write_csv(BENCHMARK_ROOT / "artifacts/case_results.csv", case_rows)
    write_csv(
        BENCHMARK_ROOT / "results/metrics.csv",
        all_metrics,
    )
    write_csv(
        BENCHMARK_ROOT / "results/paired_comparisons.csv",
        [*retrieval_pairs, *ablation_pairs],
    )
    write_csv(
        BENCHMARK_ROOT / "results/comparison_examples.csv",
        [*retrieval_examples, *ablation_examples],
    )

    write_report(
        retrieval_metrics,
        ablation_metrics,
        definitions,
        retrieval_pairs,
        ablation_pairs,
        retrieval_examples,
        ablation_examples,
    )
    summary = {
        "input_cases": len(cases),
        "primary_fair_unique_cases": len(
            rows_for_scope(
                [evaluate_case(case, "scope_count", lambda _query: response([], 0)) for case in cases],
                "primary_fair_unique",
            )
        ),
        "retrieval_algorithms": sorted(definitions),
        "ablation_variants": sorted({row["algorithm"] for row in ablation_metrics}),
    }
    write_json(BENCHMARK_ROOT / "results/summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

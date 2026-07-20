#!/usr/bin/env python3
"""Evaluate current and external search algorithms on testing dataset v2.

Problem: score every v2 generated case against both the current app evaluator
and the external English fast algorithm, then write the same full Markdown
comparison style used for the previous commercial-name report.
Inputs:
    - benchmark_02_synthetic/data/test_cases.csv
    - app/data/catalog.json
    - benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py
Outputs:
    - Raw case rows under `artifacts/01_full_benchmark/`.
    - Aggregate source tables under `artifacts/01_full_benchmark/source_tables/`.
Edge cases:
    - v2 includes `match`, `ambiguous`, and `no_match` expected behaviors.
    - Ambiguous/no-match rows have no single expected commercial family.
    - Markdown table cells can contain pipes, newlines, or blank values.
Failure modes:
    - Missing input files, missing category descriptions, row-count mismatch, or
      incomplete category/error-type joins raise explicit exceptions.
Algorithm choice:
    - The script reuses the existing current-app scorer and external algorithm
      adapter because those are the tested implementations from the previous
      report. A separate v2 wrapper is used only for the new expected-behavior
      semantics and output paths, avoiding any mutation of the old 341k report.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import logging
import multiprocessing
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
EVALUATION_DIR = ROOT / "benchmark_01_legacy"
if str(EVALUATION_DIR) not in sys.path:
    sys.path.insert(0, str(EVALUATION_DIR))

import evaluate_current_app_search as current_eval


LOGGER = logging.getLogger(__name__)

DATASET_DIR = Path(__file__).resolve().parent
DATASET_PATH = DATASET_DIR / "data" / "test_cases.csv"
CATEGORY_SUMMARY_PATH = DATASET_DIR / "data" / "category_summary.csv"
RESULTS_DIR = DATASET_DIR / "artifacts" / "01_full_benchmark" / "source_tables"
CATALOG_PATH = ROOT / "app" / "data" / "catalog.json"
EXTERNAL_ALGORITHM_PATH = ROOT / "benchmark_01_legacy" / "external_algorithms" / "english_search_algorithm_fast.py"

TOP_K_RESULTS = 20
DEFAULT_CHUNK_SIZE = 200
DEFAULT_MAX_WORKERS = 8
CONFIDENT_EXTERNAL_STATUSES = {"high_confidence", "medium_confidence"}
NO_MATCH_EXPECTED = "__NO_MATCH__"
AMBIGUOUS_EXPECTED = "__AMBIGUOUS__"

CURRENT_ALL_RESULTS_PATH = DATASET_DIR / "artifacts" / "01_full_benchmark" / "algorithm_1_cases.csv"
CURRENT_METRICS_BY_CATEGORY_PATH = RESULTS_DIR / "algorithm_1_metrics_by_category.csv"
CURRENT_METRICS_BY_ERROR_TYPE_PATH = RESULTS_DIR / "algorithm_1_metrics_by_error_type.csv"
CURRENT_FAILURE_SAMPLES_PATH = RESULTS_DIR / "algorithm_1_failure_samples.csv"

EXTERNAL_ALL_RESULTS_PATH = DATASET_DIR / "artifacts" / "01_full_benchmark" / "algorithm_2_cases.csv"
EXTERNAL_METRICS_BY_CATEGORY_PATH = RESULTS_DIR / "algorithm_2_metrics_by_category.csv"
EXTERNAL_METRICS_BY_ERROR_TYPE_PATH = RESULTS_DIR / "algorithm_2_metrics_by_error_type.csv"
EXTERNAL_FAILURE_SAMPLES_PATH = RESULTS_DIR / "algorithm_2_failure_samples.csv"

COMPARISON_BY_CATEGORY_PATH = RESULTS_DIR / "comparison_1_2_by_category.csv"
COMPARISON_BY_ERROR_TYPE_PATH = RESULTS_DIR / "comparison_1_2_by_error_type.csv"
COMPARISON_REPORT_PATH = RESULTS_DIR / "comparison_1_2.md"
SUMMARY_PATH = RESULTS_DIR / "algorithm_2_summary.json"

COMPARISON_METRICS = [
    "hit_at_1",
    "hit_at_5",
    "hit_at_10",
    "hit_at_20",
    "mrr_at_20",
    "map_at_20",
    "ndcg_at_20",
    "no_result_rate",
    "unsafe_confident_top1_rate",
    "missing_clarification_rate",
    "behavior_success_rate",
    "avg_candidate_pool",
]

CaseRow = dict[str, Any]
ResultRow = dict[str, Any]
MetricRow = dict[str, Any]
ExternalModule = ModuleType

CURRENT_INDEX: current_eval.SearchIndex | None = None
EXTERNAL_MODULE: ExternalModule | None = None
EXTERNAL_CATALOG: Any | None = None
REL_COUNT_CACHE: dict[tuple[tuple[str, str], ...], int] = {}


def parse_args() -> argparse.Namespace:
    """Parse CLI options for smoke and full evaluation runs."""

    parser = argparse.ArgumentParser(description="Evaluate testing dataset v2 with current and external search.")
    parser.add_argument("--limit", type=int, default=0, help="Optional smoke-run row limit. Zero means full dataset.")
    parser.add_argument(
        "--workers",
        type=int,
        default=min(DEFAULT_MAX_WORKERS, max(1, os.cpu_count() or 1)),
        help="Worker process count. Defaults to min(8, CPU count).",
    )
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Rows per worker chunk.")
    return parser.parse_args()


def configure_logging() -> None:
    """Configure concise progress logging."""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


def main() -> int:
    """Run v2 current/external evaluation and full report generation."""

    configure_logging()
    args = parse_args()
    if args.workers <= 0:
        raise ValueError(f"--workers must be positive, got {args.workers}")
    if args.chunk_size <= 0:
        raise ValueError(f"--chunk-size must be positive, got {args.chunk_size}")

    started = time.time()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    initialize_global_state()
    cases = read_cases(args.limit)
    LOGGER.info("loaded v2 cases=%d workers=%d chunk_size=%d", len(cases), args.workers, args.chunk_size)

    current_rows, external_rows = run_evaluation(cases, args.workers, args.chunk_size)
    if len(current_rows) != len(cases) or len(external_rows) != len(cases):
        raise RuntimeError(
            f"row-count mismatch: cases={len(cases)} current={len(current_rows)} external={len(external_rows)}"
        )

    current_metrics = metric_rows_by_scope_category(current_rows)
    external_metrics = metric_rows_by_scope_category(external_rows)
    current_error_metrics = metric_rows_by_error_type(current_rows)
    external_error_metrics = metric_rows_by_error_type(external_rows)
    comparison = comparison_rows(current_metrics, external_metrics, ("scope", "category"))
    error_comparison = comparison_rows(current_error_metrics, external_error_metrics, ("scope", "category", "error_type"))
    comparison = enrich_category_comparison_rows(comparison)
    error_comparison = enrich_error_comparison_rows(error_comparison)

    current_failures = failure_samples(current_rows, "current")
    external_failures = failure_samples(external_rows, "external")

    write_csv(CURRENT_ALL_RESULTS_PATH, current_rows)
    write_csv(EXTERNAL_ALL_RESULTS_PATH, external_rows)
    write_csv(CURRENT_METRICS_BY_CATEGORY_PATH, current_metrics)
    write_csv(EXTERNAL_METRICS_BY_CATEGORY_PATH, external_metrics)
    write_csv(CURRENT_METRICS_BY_ERROR_TYPE_PATH, current_error_metrics)
    write_csv(EXTERNAL_METRICS_BY_ERROR_TYPE_PATH, external_error_metrics)
    write_csv(COMPARISON_BY_CATEGORY_PATH, comparison)
    write_csv(COMPARISON_BY_ERROR_TYPE_PATH, error_comparison)
    write_csv(CURRENT_FAILURE_SAMPLES_PATH, current_failures)
    write_csv(EXTERNAL_FAILURE_SAMPLES_PATH, external_failures)

    elapsed_seconds = time.time() - started
    write_comparison_report(comparison, error_comparison, elapsed_seconds, len(cases))
    write_summary(elapsed_seconds, len(cases), args)
    LOGGER.info("wrote v2 report: %s", COMPARISON_REPORT_PATH)
    return 0


def initialize_global_state() -> None:
    """Prepare current app index and external catalog once for forked workers."""

    global CURRENT_INDEX, EXTERNAL_MODULE, EXTERNAL_CATALOG
    CURRENT_INDEX = current_eval.SearchIndex(current_eval.prepare_records())
    EXTERNAL_MODULE = load_external_module(EXTERNAL_ALGORITHM_PATH)
    external_rows = build_external_catalog_rows(load_catalog_payload())
    EXTERNAL_CATALOG = EXTERNAL_MODULE.prepare_catalog(external_rows)


def load_external_module(path: Path) -> ExternalModule:
    """Import the external algorithm snapshot from disk."""

    if not path.exists():
        raise FileNotFoundError(f"external algorithm snapshot not found: {path}")
    spec = importlib.util.spec_from_file_location("external_english_search_algorithm_fast_v2", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to import external algorithm: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_catalog_payload() -> list[dict[str, Any]]:
    """Load the app catalog JSON records."""

    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError(f"catalog payload lacks list records: {CATALOG_PATH}")
    return records


def build_external_catalog_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Adapt app catalog rows to the external algorithm input schema."""

    rows: list[dict[str, str]] = []
    for raw in records:
        commercial_name = str(raw.get("n") or "").strip()
        if not commercial_name:
            continue
        base_group = str(raw.get("b") or "").strip()
        rows.append({"commercial_name": commercial_name, "canonical_name": base_group or commercial_name})
    if not rows:
        raise ValueError("no catalog rows available for external algorithm")
    return rows


def read_cases(limit: int) -> list[CaseRow]:
    """Read v2 generated cases from the single all-cases CSV."""

    with DATASET_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "input", "expected", "category", "error_type", "difficulty", "danger",
            "scope", "expected_behavior", "collision_with", "source_base_group",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{DATASET_PATH} missing required columns: {', '.join(sorted(missing))}")
        cases: list[CaseRow] = []
        for source_row, row in enumerate(reader, 1):
            cases.append({
                "source_row": source_row,
                "input": row["input"],
                "expected": row["expected"],
                "category": row["category"],
                "error_type": row["error_type"],
                "difficulty": row["difficulty"],
                "danger": row["danger"],
                "scope": row["scope"],
                "expected_behavior": row["expected_behavior"],
                "collision_with": row["collision_with"],
                "source_base_group": row["source_base_group"],
                "generator_function": row.get("generator_function", ""),
            })
            if limit and len(cases) >= limit:
                return cases
    return cases


def run_evaluation(cases: list[CaseRow], workers: int, chunk_size: int) -> tuple[list[ResultRow], list[ResultRow]]:
    """Evaluate cases serially or with forked worker chunks."""

    chunks = [cases[index : index + chunk_size] for index in range(0, len(cases), chunk_size)]
    if workers <= 1:
        current_rows: list[ResultRow] = []
        external_rows: list[ResultRow] = []
        for chunk in chunks:
            current_chunk, external_chunk = evaluate_chunk(chunk)
            current_rows.extend(current_chunk)
            external_rows.extend(external_chunk)
            if len(current_rows) % 5_000 == 0 or len(current_rows) == len(cases):
                LOGGER.info("processed=%d", len(current_rows))
        return current_rows, external_rows

    context_name = "fork" if "fork" in multiprocessing.get_all_start_methods() else None
    context = multiprocessing.get_context(context_name) if context_name else multiprocessing.get_context()
    current_rows = []
    external_rows = []
    started = time.time()
    with context.Pool(processes=workers) as pool:
        for current_chunk, external_chunk in pool.imap(evaluate_chunk, chunks):
            current_rows.extend(current_chunk)
            external_rows.extend(external_chunk)
            if len(current_rows) % 5_000 == 0 or len(current_rows) == len(cases):
                LOGGER.info("processed=%d elapsed_s=%.1f", len(current_rows), time.time() - started)
    return current_rows, external_rows


def evaluate_chunk(cases: list[CaseRow]) -> tuple[list[ResultRow], list[ResultRow]]:
    """Evaluate one chunk of cases for both algorithms."""

    return ([evaluate_current_case(case) for case in cases], [evaluate_external_case(case) for case in cases])


def evaluate_current_case(case: CaseRow) -> ResultRow:
    """Evaluate one v2 case with the current app scoring logic."""

    if CURRENT_INDEX is None:
        raise RuntimeError("CURRENT_INDEX is not initialized")
    targets = targets_for_case(case)
    rel_total = relevant_total(targets)
    results, candidate_pool = current_eval.search(CURRENT_INDEX, case["input"], TOP_K_RESULTS)
    relevances = [current_eval.relevance(item["record"], targets) for item in results]
    top1 = results[0] if results else None
    top1_rel = relevances[0] if relevances else 0
    first_rank, ap20, ndcg20 = ranking_metrics(relevances, rel_total, case, bool(results), top1_confident=bool(top1 and not top1["needs_clarification"]))
    behavior_success = current_behavior_success(case, first_rank, top1)
    unsafe_confident_top1 = bool(top1 and top1_rel == 0 and not top1["needs_clarification"] and case["expected_behavior"] != "no_match")
    missing_clarification = bool(
        top1
        and case["danger"] in {"CAUTION", "DANGEROUS"}
        and case["expected_behavior"] in {"ambiguous", "match"}
        and not top1["needs_clarification"]
    )
    return base_result_row(
        case,
        algorithm="current_app",
        first_rank=first_rank,
        ap20=ap20,
        ndcg20=ndcg20,
        result_count=len(results),
        candidate_pool=candidate_pool,
        top1_base=top1["record"].get("b") if top1 else "",
        top1_product=top1["record"].get("n") if top1 else "",
        top1_score=top1["score"] if top1 else "",
        top1_relevance=top1_rel,
        top1_status="clarification" if top1 and top1["needs_clarification"] else "confident" if top1 else "no_result",
        top1_signals="|".join(sorted(top1["signals"])) if top1 else "",
        unsafe_confident_top1=unsafe_confident_top1,
        missing_clarification=missing_clarification,
        behavior_success=behavior_success,
        top5_bases="|".join(item["record"].get("b") or item["record"].get("n") or "" for item in results[:5]),
    )


def evaluate_external_case(case: CaseRow) -> ResultRow:
    """Evaluate one v2 case with the external English fast algorithm."""

    if EXTERNAL_MODULE is None or EXTERNAL_CATALOG is None:
        raise RuntimeError("external algorithm state is not initialized")
    targets = targets_for_case(case)
    rel_total = relevant_total(targets)
    response = EXTERNAL_MODULE.search_catalog(EXTERNAL_CATALOG, case["input"], TOP_K_RESULTS)
    results = list(response.get("results") or [])
    status = str(response.get("status") or "")
    relevances = [external_relevance(item, targets) for item in results]
    top1 = results[0] if results else None
    top1_rel = relevances[0] if relevances else 0
    top1_confident = bool(top1 and status in CONFIDENT_EXTERNAL_STATUSES)
    first_rank, ap20, ndcg20 = ranking_metrics(relevances, rel_total, case, bool(results), top1_confident=top1_confident)
    behavior_success = external_behavior_success(case, first_rank, status, bool(results))
    unsafe_confident_top1 = bool(top1 and top1_rel == 0 and status in CONFIDENT_EXTERNAL_STATUSES and case["expected_behavior"] != "no_match")
    missing_clarification = bool(
        top1
        and case["danger"] in {"CAUTION", "DANGEROUS"}
        and case["expected_behavior"] in {"ambiguous", "match"}
        and status in CONFIDENT_EXTERNAL_STATUSES
    )
    return base_result_row(
        case,
        algorithm="external_english_fast",
        first_rank=first_rank,
        ap20=ap20,
        ndcg20=ndcg20,
        result_count=len(results),
        candidate_pool=len(results),
        top1_base=top1.get("name", "") if top1 else "",
        top1_product=top1.get("commercial_name", "") if top1 else "",
        top1_score=top1.get("score", "") if top1 else "",
        top1_relevance=top1_rel,
        top1_status=status or "no_result",
        top1_signals="|".join(top1.get("signals", []) or []) if top1 else "",
        unsafe_confident_top1=unsafe_confident_top1,
        missing_clarification=missing_clarification,
        behavior_success=behavior_success,
        top5_bases="|".join(str(item.get("name", "")) for item in results[:5]),
    )


def targets_for_case(case: CaseRow) -> list[tuple[str, str]]:
    """Return normalized targets for match or ambiguity candidate checks."""

    if case["expected_behavior"] == "match":
        return current_eval.parse_expected_targets(case["expected"])
    if case["expected_behavior"] == "ambiguous":
        names = [case.get("source_base_group", "")]
        names.extend(part.strip() for part in str(case.get("collision_with", "")).split(";") if part.strip())
        targets = [(current_eval.normalize_search(name), current_eval.compact_key(name)) for name in names if name]
        return list(dict.fromkeys(targets)) or [(AMBIGUOUS_EXPECTED, AMBIGUOUS_EXPECTED)]
    return [(NO_MATCH_EXPECTED, NO_MATCH_EXPECTED)]


def relevant_total(targets: list[tuple[str, str]]) -> int:
    """Return cached relevant total for ranking metrics."""

    if CURRENT_INDEX is None:
        raise RuntimeError("CURRENT_INDEX is not initialized")
    target_key = tuple(targets)
    if target_key not in REL_COUNT_CACHE:
        if target_key in {((NO_MATCH_EXPECTED, NO_MATCH_EXPECTED),), ((AMBIGUOUS_EXPECTED, AMBIGUOUS_EXPECTED),)}:
            REL_COUNT_CACHE[target_key] = 1
        else:
            REL_COUNT_CACHE[target_key] = current_eval.relevant_total(CURRENT_INDEX, targets)
    return REL_COUNT_CACHE[target_key]


def ranking_metrics(
    relevances: list[int],
    rel_total: int,
    case: CaseRow,
    has_results: bool,
    *,
    top1_confident: bool,
) -> tuple[int, float, float]:
    """Compute rank/AP/nDCG with v2 no-match behavior support."""

    if case["expected_behavior"] == "no_match":
        success = not has_results or not top1_confident
        return (1 if success else 999, 1.0 if success else 0.0, 1.0 if success else 0.0)

    first_rank = 999
    relevant_seen = 0
    ap = 0.0
    for rank, rel in enumerate(relevances, 1):
        if rel > 0:
            if first_rank == 999:
                first_rank = rank
            relevant_seen += 1
            ap += relevant_seen / rank
    ap20 = ap / min(rel_total, TOP_K_RESULTS)
    ndcg20 = current_eval.ndcg(relevances, rel_total)
    return first_rank, ap20, ndcg20


def current_behavior_success(case: CaseRow, first_rank: int, top1: dict[str, Any] | None) -> bool:
    """Return whether current app behavior satisfies the v2 expected behavior."""

    if case["expected_behavior"] == "match":
        return first_rank <= TOP_K_RESULTS
    if case["expected_behavior"] == "ambiguous":
        return bool(top1 and top1.get("needs_clarification"))
    return top1 is None or bool(top1.get("needs_clarification"))


def external_behavior_success(case: CaseRow, first_rank: int, status: str, has_results: bool) -> bool:
    """Return whether external behavior satisfies the v2 expected behavior."""

    if case["expected_behavior"] == "match":
        return first_rank <= TOP_K_RESULTS
    if case["expected_behavior"] == "ambiguous":
        return status not in CONFIDENT_EXTERNAL_STATUSES and has_results
    return (not has_results) or status not in CONFIDENT_EXTERNAL_STATUSES


def external_relevance(result: dict[str, Any], targets: list[tuple[str, str]]) -> int:
    """Compute external result relevance against normalized target names."""

    product_values = normalized_values([result.get("commercial_name"), *result.get("commercial_examples", [])])
    group_values = normalized_values([result.get("name"), result.get("candidate_canonical_name")])
    for target_norm, target_compact in targets:
        if (target_norm, target_compact) in product_values:
            return 3
        if (target_norm, target_compact) in group_values:
            return 2
    return 0


def normalized_values(values: Iterable[Any]) -> set[tuple[str, str]]:
    """Normalize candidate fields for relevance matching."""

    out: set[tuple[str, str]] = set()
    for value in values:
        norm = current_eval.normalize_search(value)
        compact = current_eval.compact_key(value)
        if norm or compact:
            out.add((norm, compact))
    return out


def base_result_row(
    case: CaseRow,
    *,
    algorithm: str,
    first_rank: int,
    ap20: float,
    ndcg20: float,
    result_count: int,
    candidate_pool: int,
    top1_base: Any,
    top1_product: Any,
    top1_score: Any,
    top1_relevance: int,
    top1_status: str,
    top1_signals: str,
    unsafe_confident_top1: bool,
    missing_clarification: bool,
    behavior_success: bool,
    top5_bases: str,
) -> ResultRow:
    """Build one row-level result with the same metric columns for both algorithms."""

    return {
        "algorithm": algorithm,
        "scope": case["scope"],
        "source_row": case["source_row"],
        "category": case["category"],
        "error_type": case["error_type"],
        "difficulty": case["difficulty"],
        "danger": case["danger"],
        "expected_behavior": case["expected_behavior"],
        "input": case["input"],
        "expected": case["expected"],
        "first_rank": first_rank,
        "hit_at_1": int(first_rank <= 1),
        "hit_at_5": int(first_rank <= 5),
        "hit_at_10": int(first_rank <= 10),
        "hit_at_20": int(first_rank <= 20),
        "ap20": ap20,
        "ndcg20": ndcg20,
        "result_count": result_count,
        "candidate_pool": candidate_pool,
        "top1_base": top1_base,
        "top1_product": top1_product,
        "top1_score": top1_score,
        "top1_relevance": top1_relevance,
        "top1_status": top1_status,
        "top1_signals": top1_signals,
        "top5_bases": top5_bases,
        "unsafe_confident_top1": int(unsafe_confident_top1),
        "missing_clarification": int(missing_clarification),
        "behavior_success": int(behavior_success),
    }


def metric_rows_by_scope_category(rows: list[ResultRow]) -> list[MetricRow]:
    """Aggregate metrics by scope/category, including scope and global totals."""

    by_scope_category: dict[tuple[str, str], list[ResultRow]] = defaultdict(list)
    by_scope: dict[str, list[ResultRow]] = defaultdict(list)
    for row in rows:
        by_scope_category[(row["scope"], row["category"])].append(row)
        by_scope[row["scope"]].append(row)
    metrics: list[MetricRow] = []
    for scope, group in sorted(by_scope.items()):
        metrics.append(metric_row(scope, "__ALL__", group))
    metrics.append(metric_row("__ALL__", "__ALL__", rows))
    for (scope, category), group in sorted(by_scope_category.items()):
        metrics.append(metric_row(scope, category, group))
    return metrics


def metric_rows_by_error_type(rows: list[ResultRow]) -> list[MetricRow]:
    """Aggregate metrics by scope/category/error_type."""

    grouped: dict[tuple[str, str, str], list[ResultRow]] = defaultdict(list)
    for row in rows:
        grouped[(row["scope"], row["category"], row["error_type"])].append(row)
    return [
        {**metric_row(scope, category, group), "error_type": error_type}
        for (scope, category, error_type), group in sorted(grouped.items())
    ]


def metric_row(scope: str, category: str, rows: list[ResultRow]) -> MetricRow:
    """Return the metric row format used by comparison tables."""

    n = len(rows)
    if not n:
        raise ValueError(f"cannot aggregate empty group {scope}/{category}")
    return {
        "scope": scope,
        "category": category,
        "cases": n,
        "hit_at_1": sum(row["first_rank"] <= 1 for row in rows) / n,
        "hit_at_5": sum(row["first_rank"] <= 5 for row in rows) / n,
        "hit_at_10": sum(row["first_rank"] <= 10 for row in rows) / n,
        "hit_at_20": sum(row["first_rank"] <= 20 for row in rows) / n,
        "mrr_at_20": sum((1 / row["first_rank"]) if row["first_rank"] <= TOP_K_RESULTS else 0 for row in rows) / n,
        "map_at_20": sum(row["ap20"] for row in rows) / n,
        "ndcg_at_20": sum(row["ndcg20"] for row in rows) / n,
        "no_result_rate": sum(row["result_count"] == 0 for row in rows) / n,
        "unsafe_confident_top1_rate": sum(row["unsafe_confident_top1"] for row in rows) / n,
        "missing_clarification_rate": sum(row["missing_clarification"] for row in rows) / n,
        "behavior_success_rate": sum(row["behavior_success"] for row in rows) / n,
        "avg_candidate_pool": sum(row["candidate_pool"] for row in rows) / n,
    }


def comparison_rows(
    current_metrics: list[MetricRow],
    external_metrics: list[MetricRow],
    key_names: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Join current and external metric rows without dropping any shared key."""

    current = {tuple(str(row[name]) for name in key_names): row for row in current_metrics}
    external = {tuple(str(row[name]) for name in key_names): row for row in external_metrics}
    missing_current = sorted(set(external) - set(current))
    missing_external = sorted(set(current) - set(external))
    if missing_current or missing_external:
        raise RuntimeError(f"metric key mismatch: missing_current={missing_current[:5]} missing_external={missing_external[:5]}")
    out: list[dict[str, Any]] = []
    for key in sorted(current):
        row = {name: value for name, value in zip(key_names, key)}
        row["cases"] = int(current[key]["cases"])
        for metric in COMPARISON_METRICS:
            current_value = float(current[key].get(metric, 0.0))
            external_value = float(external[key].get(metric, 0.0))
            row[f"current_{metric}"] = current_value
            row[f"external_{metric}"] = external_value
            row[f"delta_external_minus_current_{metric}"] = external_value - current_value
        out.append(row)
    return out


def enrich_category_comparison_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add non-empty category context to every category-comparison CSV/report row."""

    context = load_category_context()
    category_examples, _ = load_examples()
    categories = {row["category"] for row in rows if row["category"] != "__ALL__"}
    missing_context = sorted(categories - set(context))
    missing_examples = sorted(
        (row["scope"], row["category"])
        for row in rows
        if row["category"] != "__ALL__" and (row["scope"], row["category"]) not in category_examples
    )
    if missing_context or missing_examples:
        raise RuntimeError(
            f"category context join failed: missing_context={missing_context[:5]} "
            f"missing_examples={missing_examples[:5]}"
        )

    enriched: list[dict[str, Any]] = []
    for row in rows:
        scope = row["scope"]
        category = row["category"]
        if category == "__ALL__":
            category_number = "n/a"
            example = "Aggregate summary row"
            description = f"Aggregate metrics for scope {scope}."
        else:
            category_number = context[category]["category_number"]
            example = category_examples[(scope, category)]
            description = context[category]["description"]
        if not str(example).strip() or not str(description).strip():
            raise RuntimeError(f"blank category context cell for {scope}/{category}")
        metric_payload = {key: value for key, value in row.items() if key not in {"scope", "category"}}
        enriched.append({
            "scope": scope,
            "category": category,
            "category_number": category_number,
            "example": example,
            "description": description,
            **metric_payload,
        })
    return enriched


def enrich_error_comparison_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add non-empty error-type context to every detailed CSV/report row."""

    context = load_category_context()
    _, error_examples = load_examples()
    categories = {row["category"] for row in rows}
    missing_context = sorted(categories - set(context))
    missing_examples = sorted(
        (row["scope"], row["category"], row["error_type"])
        for row in rows
        if (row["scope"], row["category"], row["error_type"]) not in error_examples
    )
    if missing_context or missing_examples:
        raise RuntimeError(
            f"error-type context join failed: missing_context={missing_context[:5]} "
            f"missing_examples={missing_examples[:5]}"
        )

    enriched: list[dict[str, Any]] = []
    for row in rows:
        scope = row["scope"]
        category = row["category"]
        error_type = row["error_type"]
        example = error_examples[(scope, category, error_type)]
        description = context[category]["description"]
        if not str(example).strip() or not str(description).strip():
            raise RuntimeError(f"blank error-type context cell for {scope}/{category}/{error_type}")
        metric_payload = {
            key: value
            for key, value in row.items()
            if key not in {"scope", "category", "error_type"}
        }
        enriched.append({
            "scope": scope,
            "category": category,
            "error_type": error_type,
            "category_number": context[category]["category_number"],
            "example": example,
            "description": description,
            **metric_payload,
        })
    return enriched


def failure_samples(rows: list[ResultRow], algorithm: str) -> list[dict[str, Any]]:
    """Return bounded failure rows for audit CSVs."""

    failures: list[dict[str, Any]] = []
    for row in rows:
        if row["behavior_success"] and row["first_rank"] <= TOP_K_RESULTS:
            continue
        failures.append({
            "algorithm": algorithm,
            "scope": row["scope"],
            "category": row["category"],
            "error_type": row["error_type"],
            "expected_behavior": row["expected_behavior"],
            "danger": row["danger"],
            "input": row["input"],
            "expected": row["expected"],
            "top1_base": row["top1_base"],
            "top1_product": row["top1_product"],
            "top1_score": row["top1_score"],
            "top1_status": row["top1_status"],
            "top1_signals": row["top1_signals"],
            "top5_bases": row["top5_bases"],
        })
        if len(failures) >= 1_500:
            break
    return failures or [{
        "algorithm": algorithm,
        "scope": "",
        "category": "",
        "error_type": "",
        "expected_behavior": "",
        "danger": "",
        "input": "",
        "expected": "",
        "top1_base": "",
        "top1_product": "",
        "top1_score": "",
        "top1_status": "",
        "top1_signals": "",
        "top5_bases": "",
    }]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write a non-empty CSV with stable field order from the first row."""

    if not rows:
        raise ValueError(f"cannot write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def load_category_context() -> dict[str, dict[str, str]]:
    """Load category descriptions and target metadata from the v2 generator summary."""

    with CATEGORY_SUMMARY_PATH.open(newline="", encoding="utf-8") as handle:
        return {row["category"]: row for row in csv.DictReader(handle)}


def load_examples() -> tuple[dict[tuple[str, str], str], dict[tuple[str, str, str], str]]:
    """Load deterministic first examples for every category and error type."""

    category_examples: dict[tuple[str, str], str] = {}
    error_examples: dict[tuple[str, str, str], str] = {}
    with DATASET_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            category_key = (row["scope"], row["category"])
            category_examples.setdefault(
                category_key,
                markdown_cell(f"{row['input']} => {row['expected']} ({row['error_type']})"),
            )
            error_key = (row["scope"], row["category"], row["error_type"])
            error_examples.setdefault(error_key, markdown_cell(f"{row['input']} => {row['expected']}"))
    return category_examples, error_examples


def write_comparison_report(
    comparison: list[dict[str, Any]],
    error_comparison: list[dict[str, Any]],
    elapsed_seconds: float,
    evaluated_cases: int,
) -> None:
    """Write full Markdown report with every category and error type."""

    by_key = {(row["scope"], row["category"]): row for row in comparison}
    scope_order = ["inside", "safety", "semi_outside", "smoke", "__ALL__"]
    scope_rows = [by_key[(scope, "__ALL__")] for scope in scope_order if (scope, "__ALL__") in by_key]
    category_rows = [row for row in comparison if row["category"] != "__ALL__"]

    lines = [
        "# Testing Dataset V2 External English Fast Search Comparison",
        "",
        "This report compares `benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py` against the current app evaluator on `benchmark_02_synthetic/data/test_cases.csv`.",
        "",
        "Important scoring note: v2 has `match`, `ambiguous`, and `no_match` expected behaviors. Hit metrics use the expected target for `match`, the known collision set for `ambiguous`, and correct refusal/non-confident behavior for `no_match`. The behavior-success columns directly score the intended v2 behavior.",
        "",
        "## Outputs",
        "",
        "| file | purpose |",
        "| --- | --- |",
        "| `benchmark_02_synthetic/artifacts/01_full_benchmark/algorithm_1_cases.csv` | one row per current-app evaluated case |",
        "| `benchmark_02_synthetic/artifacts/01_full_benchmark/algorithm_2_cases.csv` | one row per external evaluated case |",
        "| `benchmark_02_synthetic/artifacts/01_full_benchmark/source_tables/algorithm_1_metrics_by_category.csv` | current metrics by scope/category |",
        "| `benchmark_02_synthetic/artifacts/01_full_benchmark/source_tables/algorithm_2_metrics_by_category.csv` | external metrics by scope/category |",
        "| `benchmark_02_synthetic/artifacts/01_full_benchmark/source_tables/algorithm_1_metrics_by_error_type.csv` | current metrics by scope/category/error_type |",
        "| `benchmark_02_synthetic/artifacts/01_full_benchmark/source_tables/algorithm_2_metrics_by_error_type.csv` | external metrics by scope/category/error_type |",
        "| `benchmark_02_synthetic/artifacts/01_full_benchmark/source_tables/comparison_1_2_by_category.csv` | side-by-side category deltas |",
        "| `benchmark_02_synthetic/artifacts/01_full_benchmark/source_tables/comparison_1_2_by_error_type.csv` | side-by-side error-type deltas |",
        "",
        "## Headline",
        "",
        f"- Evaluated cases: `{evaluated_cases:,}`.",
        f"- Runtime: `{elapsed_seconds:.2f}` seconds.",
        "",
        "| scope | cases | current Hit@1 | external Hit@1 | delta | current Hit@20 | external Hit@20 | delta | current behavior success | external behavior success | delta | current unsafe top1 | external unsafe top1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in scope_rows:
        lines.append(
            f"| `{row['scope']}` | {row['cases']:,} | "
            f"{pct(row['current_hit_at_1'])} | {pct(row['external_hit_at_1'])} | {pct(row['delta_external_minus_current_hit_at_1'])} | "
            f"{pct(row['current_hit_at_20'])} | {pct(row['external_hit_at_20'])} | {pct(row['delta_external_minus_current_hit_at_20'])} | "
            f"{pct(row['current_behavior_success_rate'])} | {pct(row['external_behavior_success_rate'])} | {pct(row['delta_external_minus_current_behavior_success_rate'])} | "
            f"{pct(row['current_unsafe_confident_top1_rate'])} | {pct(row['external_unsafe_confident_top1_rate'])} |"
        )

    lines += [
        "",
        "## Full Category Comparison",
        "",
        "This table includes every category in testing dataset v2. No category is filtered out.",
        "",
        "| scope | category | example | description | cases | current Hit@1 | external Hit@1 | delta | current Hit@20 | external Hit@20 | delta | current behavior success | external behavior success | delta | current unsafe top-1 | external unsafe top-1 | current no-result | external no-result |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(category_rows, key=lambda item: (item["scope"], int(item["category_number"]))):
        category = row["category"]
        example = markdown_cell(row["example"])
        description = markdown_cell(row["description"])
        lines.append(
            f"| `{row['scope']}` | `{category}` | {example} | {description} | {row['cases']:,} | "
            f"{pct(row['current_hit_at_1'])} | {pct(row['external_hit_at_1'])} | {pct(row['delta_external_minus_current_hit_at_1'])} | "
            f"{pct(row['current_hit_at_20'])} | {pct(row['external_hit_at_20'])} | {pct(row['delta_external_minus_current_hit_at_20'])} | "
            f"{pct(row['current_behavior_success_rate'])} | {pct(row['external_behavior_success_rate'])} | {pct(row['delta_external_minus_current_behavior_success_rate'])} | "
            f"{pct(row['current_unsafe_confident_top1_rate'])} | {pct(row['external_unsafe_confident_top1_rate'])} | "
            f"{pct(row['current_no_result_rate'])} | {pct(row['external_no_result_rate'])} |"
        )

    lines += [
        "",
        "## Full Error-Type Comparison",
        "",
        "This table includes every `(scope, category, error_type)` bucket in testing dataset v2. No error type is filtered out.",
        "",
        "| scope | category | error_type | example | description | cases | current Hit@1 | external Hit@1 | delta | current Hit@20 | external Hit@20 | delta | current behavior success | external behavior success | delta | current unsafe top-1 | external unsafe top-1 | current no-result | external no-result |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(error_comparison, key=lambda item: (item["scope"], int(item["category_number"]), item["error_type"])):
        example = markdown_cell(row["example"])
        description = markdown_cell(row["description"])
        lines.append(
            f"| `{row['scope']}` | `{row['category']}` | `{markdown_cell(row['error_type'])}` | {example} | {description} | {row['cases']:,} | "
            f"{pct(row['current_hit_at_1'])} | {pct(row['external_hit_at_1'])} | {pct(row['delta_external_minus_current_hit_at_1'])} | "
            f"{pct(row['current_hit_at_20'])} | {pct(row['external_hit_at_20'])} | {pct(row['delta_external_minus_current_hit_at_20'])} | "
            f"{pct(row['current_behavior_success_rate'])} | {pct(row['external_behavior_success_rate'])} | {pct(row['delta_external_minus_current_behavior_success_rate'])} | "
            f"{pct(row['current_unsafe_confident_top1_rate'])} | {pct(row['external_unsafe_confident_top1_rate'])} | "
            f"{pct(row['current_no_result_rate'])} | {pct(row['external_no_result_rate'])} |"
        )

    COMPARISON_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(elapsed_seconds: float, evaluated_cases: int, args: argparse.Namespace) -> None:
    """Write compact JSON summary for the full v2 evaluation."""

    payload = {
        "evaluated_cases": evaluated_cases,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "workers": args.workers,
        "chunk_size": args.chunk_size,
        "limit": args.limit,
        "dataset_csv": str(DATASET_PATH.relative_to(ROOT)),
        "current_all_results_csv": str(CURRENT_ALL_RESULTS_PATH.relative_to(ROOT)),
        "external_all_results_csv": str(EXTERNAL_ALL_RESULTS_PATH.relative_to(ROOT)),
        "comparison_report_md": str(COMPARISON_REPORT_PATH.relative_to(ROOT)),
        "external_algorithm_path": str(EXTERNAL_ALGORITHM_PATH.relative_to(ROOT)),
        "external_algorithm_sha256": hashlib.sha256(EXTERNAL_ALGORITHM_PATH.read_bytes()).hexdigest(),
    }
    SUMMARY_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def markdown_cell(value: Any) -> str:
    """Return a Markdown table-safe cell."""

    text = str(value).replace("\r", " ").replace("\n", " ").strip().replace("|", "/")
    return text or "n/a"


def pct(value: Any) -> str:
    """Format a float as a percent string."""

    return f"{float(value) * 100:.2f}%"


if __name__ == "__main__":
    raise SystemExit(main())

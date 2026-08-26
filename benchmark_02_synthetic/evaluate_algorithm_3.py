#!/usr/bin/env python3
"""Evaluate the master commercial-name algorithm on testing dataset v2.

Problem: prove whether the new master algorithm beats both child algorithms on
the generated v2 commercial-name dataset without dropping any category or
error-type bucket.
Inputs:
    - benchmark_02_synthetic/data/test_cases.csv.
    - benchmark_02_synthetic existing current/external v2 metrics and row results.
    - benchmark_01_legacy/master_algorithms/master_commercial_name_search.py.
Outputs:
    - Master row-level CSV, aggregate CSVs, failure samples, JSON summary, and a
      Markdown report comparing current, external, and master.
Edge cases:
    - v2 rows can expect match, ambiguity, or no confident match.
    - Master can return a candidate list while still marking the response
      ambiguous; retrieval metrics and behavior-success metrics are distinct.
    - Category names and error types must be present in every comparison row,
      including examples and descriptions.
Failure modes:
    - Missing existing child metrics, row-count mismatch, or missing context
      raises explicitly because silent omissions would hide medical search risk.
Algorithm choice:
    - The evaluator reuses the v2 metric semantics from
      evaluate_algorithms_1_2.py and adds a three-way comparison layer. This
      avoids changing the previous current/external artifacts and makes the
      master run independently reproducible.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import multiprocessing
import sys
import time
from pathlib import Path
from typing import Any


DATASET_DIR = Path(__file__).resolve().parent
ROOT = DATASET_DIR.parents[0]
EVALUATION_DIR = ROOT / "benchmark_01_legacy"
MASTER_DIR = EVALUATION_DIR / "master_algorithms"
for path in [str(DATASET_DIR), str(EVALUATION_DIR), str(MASTER_DIR)]:
    if path not in sys.path:
        sys.path.insert(0, path)

import evaluate_algorithms_1_2 as v2_eval
import master_commercial_name_search as master_search


LOGGER = logging.getLogger(__name__)

RESULTS_DIR = DATASET_DIR / "artifacts" / "01_full_benchmark" / "source_tables"
PUBLISHED_RESULTS_DIR = DATASET_DIR / "results" / "01_full_benchmark"
MASTER_ALL_RESULTS_PATH = DATASET_DIR / "artifacts" / "01_full_benchmark" / "algorithm_3_cases.csv"
MASTER_METRICS_BY_CATEGORY_PATH = RESULTS_DIR / "algorithm_3_metrics_by_category.csv"
MASTER_METRICS_BY_ERROR_TYPE_PATH = RESULTS_DIR / "algorithm_3_metrics_by_error_type.csv"
MASTER_FAILURE_SAMPLES_PATH = RESULTS_DIR / "algorithm_3_failure_samples.csv"
MASTER_COMPARISON_BY_CATEGORY_PATH = PUBLISHED_RESULTS_DIR / "algorithm_1_3_comparison_by_category.csv"
MASTER_COMPARISON_BY_ERROR_TYPE_PATH = PUBLISHED_RESULTS_DIR / "algorithm_1_3_comparison_by_error_type.csv"
MASTER_REPORT_PATH = PUBLISHED_RESULTS_DIR / "algorithm_1_3_comparison.md"
MASTER_SUMMARY_PATH = RESULTS_DIR / "algorithm_3_summary.json"

CONFIDENT_MASTER_STATUSES = {"high_confidence", "medium_confidence"}
DEFAULT_CHUNK_SIZE = 200
DEFAULT_MAX_WORKERS = 8

MASTER_CATALOG: master_search.MasterCatalog | None = None


def parse_args() -> argparse.Namespace:
    """Parse CLI options for smoke and full v2 master evaluation."""

    parser = argparse.ArgumentParser(description="Evaluate master search on testing dataset v2.")
    parser.add_argument("--limit", type=int, default=0, help="Optional smoke-run row limit. Zero means full dataset.")
    parser.add_argument(
        "--workers",
        type=int,
        default=min(DEFAULT_MAX_WORKERS, max(1, multiprocessing.cpu_count())),
        help="Worker process count. Defaults to min(8, CPU count).",
    )
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Rows per worker chunk.")
    return parser.parse_args()


def configure_logging() -> None:
    """Configure concise progress logging."""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


def main() -> int:
    """Run master evaluation and write all comparison artifacts."""

    configure_logging()
    args = parse_args()
    if args.workers <= 0:
        raise ValueError(f"--workers must be positive, got {args.workers}")
    if args.chunk_size <= 0:
        raise ValueError(f"--chunk-size must be positive, got {args.chunk_size}")

    started = time.time()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PUBLISHED_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    initialize_global_state()
    cases = v2_eval.read_cases(args.limit)
    LOGGER.info("loaded v2 cases=%d workers=%d chunk_size=%d", len(cases), args.workers, args.chunk_size)

    master_rows = run_master_evaluation(cases, args.workers, args.chunk_size)
    if len(master_rows) != len(cases):
        raise RuntimeError(f"row-count mismatch: cases={len(cases)} master={len(master_rows)}")

    master_metrics = v2_eval.metric_rows_by_scope_category(master_rows)
    master_error_metrics = v2_eval.metric_rows_by_error_type(master_rows)
    if args.limit:
        LOGGER.info("limit mode: evaluating child algorithms on the same limited case slice")
        v2_eval.initialize_global_state()
        current_rows, external_rows = v2_eval.run_evaluation(cases, 1, args.chunk_size)
        current_metrics = v2_eval.metric_rows_by_scope_category(current_rows)
        external_metrics = v2_eval.metric_rows_by_scope_category(external_rows)
        current_error_metrics = v2_eval.metric_rows_by_error_type(current_rows)
        external_error_metrics = v2_eval.metric_rows_by_error_type(external_rows)
    else:
        current_metrics = read_metric_csv(v2_eval.CURRENT_METRICS_BY_CATEGORY_PATH)
        external_metrics = read_metric_csv(v2_eval.EXTERNAL_METRICS_BY_CATEGORY_PATH)
        current_error_metrics = read_metric_csv(v2_eval.CURRENT_METRICS_BY_ERROR_TYPE_PATH)
        external_error_metrics = read_metric_csv(v2_eval.EXTERNAL_METRICS_BY_ERROR_TYPE_PATH)

    comparison = three_way_comparison_rows(current_metrics, external_metrics, master_metrics, ("scope", "category"))
    error_comparison = three_way_comparison_rows(
        current_error_metrics,
        external_error_metrics,
        master_error_metrics,
        ("scope", "category", "error_type"),
    )
    comparison = enrich_category_rows(comparison)
    error_comparison = enrich_error_rows(error_comparison)
    failure_rows = failure_samples(master_rows)

    v2_eval.write_csv(MASTER_ALL_RESULTS_PATH, master_rows)
    v2_eval.write_csv(MASTER_METRICS_BY_CATEGORY_PATH, master_metrics)
    v2_eval.write_csv(MASTER_METRICS_BY_ERROR_TYPE_PATH, master_error_metrics)
    v2_eval.write_csv(MASTER_COMPARISON_BY_CATEGORY_PATH, comparison)
    v2_eval.write_csv(MASTER_COMPARISON_BY_ERROR_TYPE_PATH, error_comparison)
    v2_eval.write_csv(MASTER_FAILURE_SAMPLES_PATH, failure_rows)

    elapsed_seconds = time.time() - started
    write_master_report(comparison, error_comparison, elapsed_seconds, len(cases))
    write_summary(elapsed_seconds, len(cases), args)
    LOGGER.info("wrote master report: %s", MASTER_REPORT_PATH)
    return 0


def initialize_global_state() -> None:
    """Prepare master catalog and current index used by v2 relevance helpers."""

    global MASTER_CATALOG
    MASTER_CATALOG = master_search.prepare_catalog()
    v2_eval.CURRENT_INDEX = MASTER_CATALOG.current_index


def run_master_evaluation(cases: list[dict[str, Any]], workers: int, chunk_size: int) -> list[dict[str, Any]]:
    """Evaluate all cases serially or with forked worker chunks."""

    chunks = [cases[index : index + chunk_size] for index in range(0, len(cases), chunk_size)]
    if workers <= 1:
        rows: list[dict[str, Any]] = []
        for chunk in chunks:
            rows.extend(evaluate_chunk(chunk))
            if len(rows) % 5_000 == 0 or len(rows) == len(cases):
                LOGGER.info("processed=%d", len(rows))
        return rows

    context_name = "fork" if "fork" in multiprocessing.get_all_start_methods() else None
    context = multiprocessing.get_context(context_name) if context_name else multiprocessing.get_context()
    rows = []
    started = time.time()
    with context.Pool(processes=workers) as pool:
        for chunk_rows in pool.imap(evaluate_chunk, chunks):
            rows.extend(chunk_rows)
            if len(rows) % 5_000 == 0 or len(rows) == len(cases):
                LOGGER.info("processed=%d elapsed_s=%.1f", len(rows), time.time() - started)
    return rows


def evaluate_chunk(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evaluate one worker chunk."""

    return [evaluate_master_case(case) for case in cases]


def evaluate_master_case(case: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one case with the master algorithm using v2 scoring semantics."""

    if MASTER_CATALOG is None:
        raise RuntimeError("MASTER_CATALOG is not initialized")
    targets = v2_eval.targets_for_case(case)
    rel_total = v2_eval.relevant_total(targets)
    response = master_search.search_catalog(MASTER_CATALOG, case["input"], v2_eval.TOP_K_RESULTS)
    results = list(response.get("results") or [])
    status = str(response.get("status") or "")
    relevances = [v2_eval.external_relevance(item, targets) for item in results]
    top1 = results[0] if results else None
    top1_rel = relevances[0] if relevances else 0
    top1_confident = bool(
        top1
        and status in CONFIDENT_MASTER_STATUSES
        and not bool(top1.get("needs_clarification"))
    )
    first_rank, ap20, ndcg20 = v2_eval.ranking_metrics(
        relevances,
        rel_total,
        case,
        bool(results),
        top1_confident=top1_confident,
    )
    behavior_success = master_behavior_success(case, first_rank, status, bool(results), top1)
    unsafe_confident_top1 = bool(
        top1
        and top1_rel == 0
        and top1_confident
        and case["expected_behavior"] != "no_match"
    )
    missing_clarification = bool(
        top1
        and case["danger"] in {"CAUTION", "DANGEROUS"}
        and case["expected_behavior"] in {"ambiguous", "match"}
        and top1_confident
    )
    return {
        "algorithm": "master_algorithm",
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
        "result_count": len(results),
        "candidate_pool": int(response.get("candidate_count") or len(results)),
        "top1_base": top1.get("name", "") if top1 else "",
        "top1_product": top1.get("commercial_name", "") if top1 else "",
        "top1_score": top1.get("score", "") if top1 else "",
        "top1_relevance": top1_rel,
        "top1_status": status or "no_result",
        "top1_needs_clarification": int(bool(top1.get("needs_clarification"))) if top1 else "",
        "top1_source": top1.get("source", "") if top1 else "",
        "top1_signals": "|".join(top1.get("reasons", []) or []) if top1 else "",
        "unsafe_confident_top1": int(unsafe_confident_top1),
        "missing_clarification": int(missing_clarification),
        "behavior_success": int(behavior_success),
        "top5_bases": "|".join(str(item.get("name", "")) for item in results[:5]),
        "top5_sources": "|".join(str(item.get("source", "")) for item in results[:5]),
    }


def master_behavior_success(
    case: dict[str, Any],
    first_rank: int,
    status: str,
    has_results: bool,
    top1: dict[str, Any] | None,
) -> bool:
    """Return whether master behavior satisfies the v2 expected behavior."""

    if case["expected_behavior"] == "match":
        return first_rank <= v2_eval.TOP_K_RESULTS
    non_confident = status not in CONFIDENT_MASTER_STATUSES or bool(top1 and top1.get("needs_clarification"))
    if case["expected_behavior"] == "ambiguous":
        return has_results and non_confident
    return (not has_results) or non_confident


def read_metric_csv(path: Path) -> list[dict[str, Any]]:
    """Read an existing metric CSV and coerce metric values to floats."""

    if not path.exists():
        raise FileNotFoundError(f"required metric file not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"metric CSV is empty: {path}")
    converted: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = dict(row)
        item["cases"] = int(float(item["cases"]))
        for metric in v2_eval.COMPARISON_METRICS:
            if metric in item:
                item[metric] = float(item[metric])
        converted.append(item)
    return converted


def three_way_comparison_rows(
    current_metrics: list[dict[str, Any]],
    external_metrics: list[dict[str, Any]],
    master_metrics: list[dict[str, Any]],
    key_names: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Join current, external, and master metrics without dropping any key."""

    current = {tuple(str(row[name]) for name in key_names): row for row in current_metrics}
    external = {tuple(str(row[name]) for name in key_names): row for row in external_metrics}
    master = {tuple(str(row[name]) for name in key_names): row for row in master_metrics}
    all_keys = set(current) | set(external) | set(master)
    missing = {
        "current": sorted(all_keys - set(current)),
        "external": sorted(all_keys - set(external)),
        "master": sorted(all_keys - set(master)),
    }
    if any(missing.values()):
        raise RuntimeError(f"metric key mismatch: {missing}")

    out: list[dict[str, Any]] = []
    for key in sorted(all_keys):
        row = {name: value for name, value in zip(key_names, key)}
        row["cases"] = int(master[key]["cases"])
        for metric in v2_eval.COMPARISON_METRICS:
            current_value = float(current[key].get(metric, 0.0))
            external_value = float(external[key].get(metric, 0.0))
            master_value = float(master[key].get(metric, 0.0))
            best_child = max(current_value, external_value)
            row[f"current_{metric}"] = current_value
            row[f"external_{metric}"] = external_value
            row[f"master_{metric}"] = master_value
            row[f"best_child_{metric}"] = best_child
            row[f"delta_master_minus_current_{metric}"] = master_value - current_value
            row[f"delta_master_minus_external_{metric}"] = master_value - external_value
            row[f"delta_master_minus_best_child_{metric}"] = master_value - best_child
        out.append(row)
    return out


def enrich_category_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add examples and descriptions to every category comparison row."""

    context = v2_eval.load_category_context()
    category_examples, _ = v2_eval.load_examples()
    enriched: list[dict[str, Any]] = []
    for row in rows:
        category = row["category"]
        scope = row["scope"]
        if category == "__ALL__":
            category_number = "n/a"
            example = "Aggregate summary row"
            description = f"Aggregate metrics for scope {scope}."
        else:
            if category not in context:
                raise RuntimeError(f"missing category context for {category}")
            key = (scope, category)
            if key not in category_examples:
                raise RuntimeError(f"missing category example for {key}")
            category_number = context[category]["category_number"]
            example = category_examples[key]
            description = context[category]["description"]
        if not str(example).strip() or not str(description).strip():
            raise RuntimeError(f"blank category context for {scope}/{category}")
        payload = {key: value for key, value in row.items() if key not in {"scope", "category"}}
        enriched.append({
            "scope": scope,
            "category": category,
            "category_number": category_number,
            "example": example,
            "description": description,
            **payload,
        })
    return enriched


def enrich_error_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add examples and descriptions to every error-type comparison row."""

    context = v2_eval.load_category_context()
    _, error_examples = v2_eval.load_examples()
    enriched: list[dict[str, Any]] = []
    for row in rows:
        scope = row["scope"]
        category = row["category"]
        error_type = row["error_type"]
        key = (scope, category, error_type)
        if category not in context:
            raise RuntimeError(f"missing category context for {category}")
        if key not in error_examples:
            raise RuntimeError(f"missing error-type example for {key}")
        example = error_examples[key]
        description = context[category]["description"]
        if not str(example).strip() or not str(description).strip():
            raise RuntimeError(f"blank error-type context for {key}")
        payload = {
            item_key: value
            for item_key, value in row.items()
            if item_key not in {"scope", "category", "error_type"}
        }
        enriched.append({
            "scope": scope,
            "category": category,
            "error_type": error_type,
            "category_number": context[category]["category_number"],
            "example": example,
            "description": description,
            **payload,
        })
    return enriched


def failure_samples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return bounded master failure rows for audit."""

    failures: list[dict[str, Any]] = []
    for row in rows:
        if row["behavior_success"] and row["first_rank"] <= v2_eval.TOP_K_RESULTS:
            continue
        failures.append({
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
            "top1_needs_clarification": row["top1_needs_clarification"],
            "top1_source": row["top1_source"],
            "top1_signals": row["top1_signals"],
            "top5_bases": row["top5_bases"],
            "top5_sources": row["top5_sources"],
        })
        if len(failures) >= 1_500:
            break
    return failures or [{
        "scope": "n/a",
        "category": "n/a",
        "error_type": "n/a",
        "expected_behavior": "n/a",
        "danger": "n/a",
        "input": "n/a",
        "expected": "n/a",
        "top1_base": "n/a",
        "top1_product": "n/a",
        "top1_score": "n/a",
        "top1_status": "n/a",
        "top1_needs_clarification": "n/a",
        "top1_source": "n/a",
        "top1_signals": "n/a",
        "top5_bases": "n/a",
        "top5_sources": "n/a",
    }]


def write_master_report(
    comparison: list[dict[str, Any]],
    error_comparison: list[dict[str, Any]],
    elapsed_seconds: float,
    evaluated_cases: int,
) -> None:
    """Write a full Markdown report with every category and error type."""

    by_key = {(row["scope"], row["category"]): row for row in comparison}
    scope_order = ["inside", "safety", "semi_outside", "smoke", "__ALL__"]
    scope_rows = [by_key[(scope, "__ALL__")] for scope in scope_order if (scope, "__ALL__") in by_key]
    category_rows = [row for row in comparison if row["category"] != "__ALL__"]

    lines = [
        "# Testing Dataset V2 Master Algorithm Comparison",
        "",
        "This report compares the current app evaluator, the external English fast algorithm, and the new master rank-fusion algorithm on `benchmark_02_synthetic/data/test_cases.csv`.",
        "",
        "Important scoring note: v2 has `match`, `ambiguous`, and `no_match` expected behaviors. Hit metrics score retrieval; behavior-success scores whether the algorithm returned the intended confident match, clarification, or non-confident/no-match behavior.",
        "",
        "## Outputs",
        "",
        "| file | purpose |",
        "| --- | --- |",
        "| `benchmark_02_synthetic/artifacts/01_full_benchmark/algorithm_3_cases.csv` | one row per master evaluated case |",
        "| `benchmark_02_synthetic/artifacts/01_full_benchmark/source_tables/algorithm_3_metrics_by_category.csv` | master metrics by scope/category |",
        "| `benchmark_02_synthetic/artifacts/01_full_benchmark/source_tables/algorithm_3_metrics_by_error_type.csv` | master metrics by scope/category/error_type |",
        "| `benchmark_02_synthetic/artifacts/01_full_benchmark/source_tables/comparison_1_3_by_category.csv` | three-way category comparison |",
        "| `benchmark_02_synthetic/artifacts/01_full_benchmark/source_tables/comparison_1_3_by_error_type.csv` | three-way detailed error-type comparison |",
        "| `benchmark_02_synthetic/artifacts/01_full_benchmark/source_tables/algorithm_3_failure_samples.csv` | first master failures for audit |",
        "",
        "## Headline",
        "",
        f"- Evaluated cases: `{evaluated_cases:,}`.",
        f"- Runtime: `{elapsed_seconds:.2f}` seconds.",
        "",
        "| scope | cases | current Hit@1 | external Hit@1 | master Hit@1 | master vs best | current Hit@20 | external Hit@20 | master Hit@20 | master vs best | current behavior | external behavior | master behavior | master vs best | current unsafe | external unsafe | master unsafe |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in scope_rows:
        lines.append(
            f"| `{row['scope']}` | {row['cases']:,} | "
            f"{pct(row['current_hit_at_1'])} | {pct(row['external_hit_at_1'])} | {pct(row['master_hit_at_1'])} | {pct(row['delta_master_minus_best_child_hit_at_1'])} | "
            f"{pct(row['current_hit_at_20'])} | {pct(row['external_hit_at_20'])} | {pct(row['master_hit_at_20'])} | {pct(row['delta_master_minus_best_child_hit_at_20'])} | "
            f"{pct(row['current_behavior_success_rate'])} | {pct(row['external_behavior_success_rate'])} | {pct(row['master_behavior_success_rate'])} | {pct(row['delta_master_minus_best_child_behavior_success_rate'])} | "
            f"{pct(row['current_unsafe_confident_top1_rate'])} | {pct(row['external_unsafe_confident_top1_rate'])} | {pct(row['master_unsafe_confident_top1_rate'])} |"
        )

    lines += [
        "",
        "## Full Category Comparison",
        "",
        "This table includes every category in testing dataset v2. No category is filtered out.",
        "",
        "| scope | category | example | description | cases | current Hit@1 | external Hit@1 | master Hit@1 | master vs best | current Hit@20 | external Hit@20 | master Hit@20 | master vs best | current behavior | external behavior | master behavior | master vs best | current unsafe | external unsafe | master unsafe |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(category_rows, key=lambda item: (item["scope"], int(item["category_number"]))):
        lines.append(
            f"| `{row['scope']}` | `{row['category']}` | {v2_eval.markdown_cell(row['example'])} | {v2_eval.markdown_cell(row['description'])} | {row['cases']:,} | "
            f"{pct(row['current_hit_at_1'])} | {pct(row['external_hit_at_1'])} | {pct(row['master_hit_at_1'])} | {pct(row['delta_master_minus_best_child_hit_at_1'])} | "
            f"{pct(row['current_hit_at_20'])} | {pct(row['external_hit_at_20'])} | {pct(row['master_hit_at_20'])} | {pct(row['delta_master_minus_best_child_hit_at_20'])} | "
            f"{pct(row['current_behavior_success_rate'])} | {pct(row['external_behavior_success_rate'])} | {pct(row['master_behavior_success_rate'])} | {pct(row['delta_master_minus_best_child_behavior_success_rate'])} | "
            f"{pct(row['current_unsafe_confident_top1_rate'])} | {pct(row['external_unsafe_confident_top1_rate'])} | {pct(row['master_unsafe_confident_top1_rate'])} |"
        )

    lines += [
        "",
        "## Full Error-Type Comparison",
        "",
        "This table includes every `(scope, category, error_type)` bucket in testing dataset v2. No error type is filtered out.",
        "",
        "| scope | category | error_type | example | description | cases | current Hit@1 | external Hit@1 | master Hit@1 | master vs best | current Hit@20 | external Hit@20 | master Hit@20 | master vs best | current behavior | external behavior | master behavior | master vs best | current unsafe | external unsafe | master unsafe |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(error_comparison, key=lambda item: (item["scope"], int(item["category_number"]), item["error_type"])):
        lines.append(
            f"| `{row['scope']}` | `{row['category']}` | `{v2_eval.markdown_cell(row['error_type'])}` | {v2_eval.markdown_cell(row['example'])} | {v2_eval.markdown_cell(row['description'])} | {row['cases']:,} | "
            f"{pct(row['current_hit_at_1'])} | {pct(row['external_hit_at_1'])} | {pct(row['master_hit_at_1'])} | {pct(row['delta_master_minus_best_child_hit_at_1'])} | "
            f"{pct(row['current_hit_at_20'])} | {pct(row['external_hit_at_20'])} | {pct(row['master_hit_at_20'])} | {pct(row['delta_master_minus_best_child_hit_at_20'])} | "
            f"{pct(row['current_behavior_success_rate'])} | {pct(row['external_behavior_success_rate'])} | {pct(row['master_behavior_success_rate'])} | {pct(row['delta_master_minus_best_child_behavior_success_rate'])} | "
            f"{pct(row['current_unsafe_confident_top1_rate'])} | {pct(row['external_unsafe_confident_top1_rate'])} | {pct(row['master_unsafe_confident_top1_rate'])} |"
        )

    MASTER_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(elapsed_seconds: float, evaluated_cases: int, args: argparse.Namespace) -> None:
    """Write compact JSON summary for the master evaluation."""

    payload = {
        "evaluated_cases": evaluated_cases,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "workers": args.workers,
        "chunk_size": args.chunk_size,
        "limit": args.limit,
        "dataset_csv": str(v2_eval.DATASET_PATH.relative_to(ROOT)),
        "master_algorithm_path": str((MASTER_DIR / "master_commercial_name_search.py").relative_to(ROOT)),
        "master_all_results_csv": str(MASTER_ALL_RESULTS_PATH.relative_to(ROOT)),
        "master_comparison_report_md": str(MASTER_REPORT_PATH.relative_to(ROOT)),
    }
    MASTER_SUMMARY_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def pct(value: Any) -> str:
    """Format a float as a percent string."""

    return f"{float(value) * 100:.2f}%"


if __name__ == "__main__":
    raise SystemExit(main())

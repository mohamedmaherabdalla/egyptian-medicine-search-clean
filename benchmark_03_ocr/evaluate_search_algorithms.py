#!/usr/bin/env python3
"""Evaluate Algorithms 1-4 on accepted Data 3 OCR-error observations."""

from __future__ import annotations

import argparse
import collections
import csv
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from benchmark_common import (
    DEFAULT_ARTIFACTS_DIR,
    DEFAULT_RESULTS_DIR,
    PROJECT_ROOT,
    compact_text,
    read_csv,
    write_csv,
    write_json,
)


EVALUATION_DIR = PROJECT_ROOT / "benchmark_01_legacy"
if str(EVALUATION_DIR) not in sys.path:
    sys.path.insert(0, str(EVALUATION_DIR))

import evaluate_current_app_search as algorithm_1_module


RESULT_FIELDS = [
    "case_id", "sample_id", "image_id", "split", "ocr_model", "input",
    "expected_family_name", "expected_family_key", "difficulty", "mistake_type", "danger",
    "analysis_cohort", "distance_band", "scored_case",
    "algorithm", "response_status", "decision_type", "needs_clarification", "candidate_count",
    "first_relevant_rank", "hit_at_1", "hit_at_5", "hit_at_10", "hit_at_20",
    "reciprocal_rank", "unsafe_confident_top1", "latency_ms", "top_1",
    "top_5", "top_20", "edit_distance", "normalized_edit_distance",
    "source_edit_distance", "source_additions_count", "source_deletions_count",
    "source_flip_count", "source_matches_count", "source_edited_length",
    "source_canonical_length", "source_length_difference",
    "source_edit_distance_over_edited_length",
    "source_edit_distance_over_canonical_length",
    "source_similarity_over_canonical_length", "source_operation_sequence",
]

METRIC_FIELDS = [
    "algorithm", "scope", "cases", "hit_at_1", "hit_at_5", "hit_at_10",
    "hit_at_20", "mrr_at_20", "unsafe_confident_top1_rate", "clarification_rate",
    "mean_latency_ms", "median_latency_ms",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_ARTIFACTS_DIR / "search_cases.csv")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--raw-output-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--algorithms", default="1,2,3,4")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--case-mode", choices=("accepted", "all_mapped"), default="accepted")
    parser.add_argument("--output-prefix", default="search")
    return parser.parse_args()


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def prepare_algorithms(selected: set[str], records: list[dict[str, Any]]) -> dict[str, Callable[[str], dict[str, Any]]]:
    runners: dict[str, Callable[[str], dict[str, Any]]] = {}
    if "1" in selected:
        index = algorithm_1_module.SearchIndex(records)

        def run_1(query: str) -> dict[str, Any]:
            results, candidate_count = algorithm_1_module.search(index, query, 20)
            adapted = []
            for item in results:
                record = item["record"]
                adapted.append({
                    "name": record.get("b") or record.get("n") or "",
                    "needs_clarification": bool(item.get("needs_clarification")),
                })
            clarification = bool(adapted and adapted[0]["needs_clarification"])
            return {
                "results": adapted,
                "candidate_count": candidate_count,
                "status": "low_confidence" if clarification else ("high_confidence" if adapted else "no_match"),
                "decision_type": "ambiguous" if clarification else ("match" if adapted else "no_match"),
            }

        runners["algorithm_1_current_app"] = run_1

    if "2" in selected:
        module = load_module(
            EVALUATION_DIR / "external_algorithms" / "english_search_algorithm_fast.py",
            "data3_algorithm_2",
        )
        external_rows = [
            {
                "commercial_name": str(record.get("n") or ""),
                "canonical_name": str(record.get("b") or record.get("n") or ""),
            }
            for record in records
            if record.get("n")
        ]
        catalog = module.prepare_catalog(external_rows)
        runners["algorithm_2_external_fast"] = lambda query: module.search_catalog(catalog, query, 20)

    if "3" in selected:
        module = load_module(
            EVALUATION_DIR / "master_algorithms" / "master_commercial_name_search.py",
            "data3_algorithm_3",
        )
        catalog = module.prepare_catalog()
        runners["algorithm_3_rank_fusion"] = lambda query: module.search_catalog(catalog, query, 20)

    if "4" in selected:
        module = load_module(
            EVALUATION_DIR / "master_algorithms" / "algorithm_4_commercial_name_search.py",
            "data3_algorithm_4",
        )
        catalog = module.prepare_catalog()
        runners["algorithm_4_family_rescue"] = lambda query: module.search_catalog(catalog, query, 20)
    return runners


def result_name(item: dict[str, Any]) -> str:
    return str(
        item.get("name")
        or item.get("candidate_canonical_name")
        or item.get("canonical_name")
        or item.get("commercial_name")
        or ""
    ).strip()


def evaluate_case(case: dict[str, str], algorithm: str, runner: Callable[[str], dict[str, Any]]) -> dict[str, object]:
    started = time.perf_counter()
    response = runner(case["input"])
    latency_ms = (time.perf_counter() - started) * 1000
    results = list(response.get("results") or [])[:20]
    names = [result_name(item) for item in results]
    expected_keys = {key for key in case["expected_family_key"].split(";") if key}
    relevant_ranks = [
        rank for rank, name in enumerate(names, 1)
        if compact_text(name) in expected_keys
    ]
    first_rank = relevant_ranks[0] if relevant_ranks else 999
    response_status = str(response.get("status") or "")
    top_needs_clarification = bool(results and results[0].get("needs_clarification"))
    decision_type = str(response.get("decision_type") or response.get("status") or "")
    confident_statuses = {"high_confidence", "medium_confidence"}
    confident = bool(results) and response_status in confident_statuses and not top_needs_clarification
    clarification = bool(results) and (top_needs_clarification or response_status not in confident_statuses)
    unsafe = confident and first_rank != 1
    return {
        "case_id": case["case_id"],
        "sample_id": case["sample_id"],
        "image_id": case["image_id"],
        "split": case["split"],
        "ocr_model": case["model_name"],
        "input": case["input"],
        "expected_family_name": case["expected_family_name"],
        "expected_family_key": case["expected_family_key"],
        "difficulty": case["difficulty"],
        "mistake_type": case["mistake_type"],
        "danger": case["danger"],
        "analysis_cohort": case.get("analysis_cohort", "unclassified"),
        "distance_band": case.get("distance_band", "unclassified"),
        "scored_case": int(str(case.get("scored_case", "1")).lower() not in {"", "0", "false"}),
        "algorithm": algorithm,
        "response_status": response_status,
        "decision_type": decision_type,
        "needs_clarification": int(clarification),
        "candidate_count": int(response.get("candidate_count") or len(results)),
        "first_relevant_rank": first_rank,
        "hit_at_1": int(first_rank <= 1),
        "hit_at_5": int(first_rank <= 5),
        "hit_at_10": int(first_rank <= 10),
        "hit_at_20": int(first_rank <= 20),
        "reciprocal_rank": round(1 / first_rank, 8) if first_rank <= 20 else 0.0,
        "unsafe_confident_top1": int(unsafe),
        "latency_ms": round(latency_ms, 3),
        "top_1": names[0] if names else "",
        "top_5": ";".join(names[:5]),
        "top_20": ";".join(names),
        "edit_distance": case.get("edit_distance", ""),
        "normalized_edit_distance": case.get("normalized_edit_distance", ""),
        "source_edit_distance": case.get("source_edit_distance", ""),
        "source_additions_count": case.get("source_additions_count", ""),
        "source_deletions_count": case.get("source_deletions_count", ""),
        "source_flip_count": case.get("source_flip_count", ""),
        "source_matches_count": case.get("source_matches_count", ""),
        "source_edited_length": case.get("source_edited_length", ""),
        "source_canonical_length": case.get("source_canonical_length", ""),
        "source_length_difference": case.get("source_length_difference", ""),
        "source_edit_distance_over_edited_length": case.get(
            "source_edit_distance_over_edited_length", ""
        ),
        "source_edit_distance_over_canonical_length": case.get(
            "source_edit_distance_over_canonical_length", ""
        ),
        "source_similarity_over_canonical_length": case.get(
            "source_similarity_over_canonical_length", ""
        ),
        "source_operation_sequence": case.get("source_operation_sequence", ""),
    }


def metric_row(algorithm: str, scope: str, rows: list[dict[str, object]]) -> dict[str, object]:
    count = len(rows)
    latencies = [float(row["latency_ms"]) for row in rows]
    return {
        "algorithm": algorithm,
        "scope": scope,
        "cases": count,
        "hit_at_1": sum(int(row["hit_at_1"]) for row in rows) / count,
        "hit_at_5": sum(int(row["hit_at_5"]) for row in rows) / count,
        "hit_at_10": sum(int(row["hit_at_10"]) for row in rows) / count,
        "hit_at_20": sum(int(row["hit_at_20"]) for row in rows) / count,
        "mrr_at_20": sum(float(row["reciprocal_rank"]) for row in rows) / count,
        "unsafe_confident_top1_rate": sum(int(row["unsafe_confident_top1"]) for row in rows) / count,
        "clarification_rate": sum(int(row["needs_clarification"]) for row in rows) / count,
        "mean_latency_ms": statistics.fmean(latencies),
        "median_latency_ms": statistics.median(latencies),
    }


def main() -> int:
    args = parse_args()
    selected = {value.strip() for value in args.algorithms.split(",") if value.strip()}
    all_cases = read_csv(args.cases)
    if args.case_mode == "accepted":
        cases = [row for row in all_cases if row.get("accepted") == "1"]
    else:
        cases = [
            row for row in all_cases
            if row.get("expected_family_key")
            and row.get("rejection_reason") != "ocr_runtime_error"
            and not row.get("rejection_reason", "").startswith("source_ground_truth_excluded:")
        ]
    cases.sort(key=lambda row: (row.get("split", ""), row.get("case_id", "")))
    if args.limit:
        cases = cases[:args.limit]
    records = algorithm_1_module.prepare_records()
    available_family_keys = {
        compact_text(record.get("b") or record.get("n"))
        for record in records
        if compact_text(record.get("b") or record.get("n"))
    }
    requested_target_keys = {
        key
        for case in cases
        for key in case.get("expected_family_key", "").split(";")
        if key
    }
    missing_target_keys = sorted(requested_target_keys - available_family_keys)
    if missing_target_keys:
        raise ValueError(
            "verified mapping targets are absent from the runtime app catalog: "
            + ", ".join(missing_target_keys)
        )
    runners = prepare_algorithms(selected, records)
    output = []
    for algorithm, runner in runners.items():
        for case in cases:
            output.append(evaluate_case(case, algorithm, runner))
    write_csv(args.raw_output_dir / f"{args.output_prefix}_results.csv", output, RESULT_FIELDS)

    grouped: dict[tuple[str, str], list[dict[str, object]]] = collections.defaultdict(list)
    for row in output:
        grouped[(str(row["algorithm"]), "all")].append(row)
        grouped[(str(row["algorithm"]), f"split:{row['split']}")].append(row)
        grouped[(str(row["algorithm"]), f"ocr:{row['ocr_model']}")].append(row)
        grouped[(str(row["algorithm"]), f"mistake:{row['mistake_type']}")].append(row)
        grouped[(str(row["algorithm"]), f"difficulty:{row['difficulty']}")].append(row)
        grouped[(str(row["algorithm"]), f"danger:{row['danger']}")].append(row)
        grouped[(str(row["algorithm"]), f"cohort:{row['analysis_cohort']}")].append(row)
        grouped[(str(row["algorithm"]), f"distance_band:{row['distance_band']}")].append(row)
        grouped[(str(row["algorithm"]), f"target:{row['expected_family_name']}")].append(row)
    seen_pairs: set[tuple[str, str, str]] = set()
    for row in output:
        pair = (
            str(row["algorithm"]),
            compact_text(row["input"]),
            str(row["expected_family_key"]),
        )
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        algorithm = str(row["algorithm"])
        grouped[(algorithm, "unique_pairs")].append(row)
        grouped[(algorithm, f"unique_split:{row['split']}")].append(row)
        if int(row["scored_case"]):
            grouped[(algorithm, "scored_unique_pairs")].append(row)
            grouped[(algorithm, f"scored_unique_split:{row['split']}")].append(row)
    metrics = [
        metric_row(algorithm, scope, rows)
        for (algorithm, scope), rows in sorted(grouped.items())
        if rows
    ]
    write_csv(args.results_dir / f"{args.output_prefix}_metrics.csv", metrics, METRIC_FIELDS)
    summary = {
        "accepted_cases": len(cases),
        "case_mode": args.case_mode,
        "algorithms": list(runners),
        "result_rows": len(output),
        "all_scope_metrics": [row for row in metrics if row["scope"] == "all"],
        "primary_scope_metrics": [
            row for row in metrics
            if row["scope"] in {
                "scored_unique_pairs",
                "scored_unique_split:development",
                "scored_unique_split:holdout",
            }
        ],
    }
    write_json(args.results_dir / f"{args.output_prefix}_evaluation_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

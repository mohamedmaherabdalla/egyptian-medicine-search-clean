#!/usr/bin/env python3
"""Evaluate the fixed retrieval roster on the cleaned synthetic core dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Iterable


BENCHMARK_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BENCHMARK_ROOT.parent
LEGACY_ROOT = PROJECT_ROOT / "benchmark_01_legacy"
DEFAULT_CASES = BENCHMARK_ROOT / "data/05_synthetic_clean_core/test_cases.csv"
DEFAULT_RESULTS = BENCHMARK_ROOT / "results/05_synthetic_clean_core"
DEFAULT_ARTIFACTS = BENCHMARK_ROOT / "artifacts/05_synthetic_clean_core"

for import_path in (BENCHMARK_ROOT, LEGACY_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import evaluate_current_app_search as current_app
import run_retrieval_experiments as retrieval


EVALUATION_VERSION = "synthetic_clean_core_v2"
RUN_ID = "05_synthetic_clean_core"
DATASET_ID = "synthetic_clean_core_66257"
TOP_K = 20
ALGORITHM_ORDER = (
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
    "algorithm_5_evidence_rescue",
)
DISPLAY_NAMES = {
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
    "algorithm_5_evidence_rescue": "Algorithm 5, evidence-guided rescue",
}
RESULT_FIELDS = (
    "evaluation_version",
    "run_id",
    "dataset",
    "case_id",
    "algorithm",
    "algorithm_name",
    "input",
    "input_compact",
    "expected",
    "acceptable_targets",
    "expected_family_keys",
    "split",
    "clean_categories",
    "primary_category",
    "clean_error_types",
    "primary_error_type",
    "operation_family",
    "difficulty",
    "danger",
    "scope",
    "tier",
    "evaluation_track_memberships",
    "effective_levenshtein",
    "effective_damerau",
    "normalized_levenshtein",
    "distance_band",
    "query_length",
    "target_length",
    "query_length_band",
    "shared_characters",
    "shared_bigrams",
    "shared_bigram_band",
    "occurrence_count",
    "response_status",
    "decision_type",
    "needs_clarification",
    "candidate_count",
    "first_relevant_rank",
    "hit_at_1",
    "hit_at_5",
    "hit_at_10",
    "hit_at_20",
    "reciprocal_rank_at_20",
    "unsafe_confident_top1",
    "no_result",
    "latency_ms",
    "top_1",
    "top_5",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--algorithms", default=",".join(ALGORITHM_ORDER))
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def split_labels(value: Any) -> list[str]:
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def target_keys(value: str) -> list[str]:
    return sorted(
        {
            current_app.compact_key(part)
            for part in split_labels(value)
            if current_app.compact_key(part)
        }
    )


def assign_split(expected_keys: list[str]) -> str:
    key = ";".join(expected_keys)
    bucket = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16) % 5
    return "holdout" if bucket == 0 else "development"


def distance_band(distance: int) -> str:
    if distance == 1:
        return "1_edit"
    if distance <= 3:
        return "2_3_edits"
    return "4_5_edits"


def length_band(length: int) -> str:
    if length <= 4:
        return "1_4_characters"
    if length <= 7:
        return "5_7_characters"
    if length <= 10:
        return "8_10_characters"
    return "11_plus_characters"


def character_ngrams(value: str, size: int) -> set[str]:
    if len(value) < size:
        return set()
    return {value[index : index + size] for index in range(len(value) - size + 1)}


def bigram_band(count: int) -> str:
    if count == 0:
        return "0_shared_bigrams"
    if count == 1:
        return "1_shared_bigram"
    if count <= 3:
        return "2_3_shared_bigrams"
    return "4_plus_shared_bigrams"


def classify_operation(categories: list[str], error_types: list[str]) -> str:
    text = " ".join([*categories, *error_types]).lower()
    mechanisms = set()
    keyword_groups = {
        "deletion": ("deletion", "missing_char", "skip_"),
        "insertion": ("insertion", "extra_char", "repeat_"),
        "transposition": ("transposition", "swap"),
        "phonetic": ("phonetic",),
        "vowel": ("vowel",),
        "visual_or_ocr": ("visual", "ocr_", "ligature"),
        "keyboard": ("keyboard",),
    }
    for mechanism, keywords in keyword_groups.items():
        if any(keyword in text for keyword in keywords):
            mechanisms.add(mechanism)
    if "combined_error" in text or "plus_error" in text or len(mechanisms) > 1:
        return "mixed_operations"
    if mechanisms:
        return next(iter(mechanisms))
    return "other"


def prepare_case(row: dict[str, str]) -> dict[str, Any]:
    expected_keys = target_keys(row["acceptable_targets"])
    if not expected_keys:
        raise ValueError(f"{row.get('case_id')}: no acceptable target")
    input_compact = current_app.compact_key(row["input"])
    target_compact = current_app.compact_key(row["expected"])
    categories = split_labels(row["clean_categories"])
    error_types = split_labels(row["clean_error_types"])
    distance = int(row["effective_levenshtein"])
    shared_characters = len(set(input_compact) & set(target_compact))
    shared_bigrams = len(character_ngrams(input_compact, 2) & character_ngrams(target_compact, 2))
    return {
        **row,
        "expected_family_keys": ";".join(expected_keys),
        "split": assign_split(expected_keys),
        "primary_category": categories[0],
        "primary_error_type": error_types[0],
        "operation_family": classify_operation(categories, error_types),
        "effective_levenshtein": distance,
        "effective_damerau": int(row["effective_damerau"]),
        "normalized_levenshtein": distance / max(len(target_compact), 1),
        "distance_band": distance_band(distance),
        "query_length": len(input_compact),
        "target_length": len(target_compact),
        "query_length_band": length_band(len(input_compact)),
        "shared_characters": shared_characters,
        "shared_bigrams": shared_bigrams,
        "shared_bigram_band": bigram_band(shared_bigrams),
        "occurrence_count": int(row["occurrence_count"]),
    }


def load_cases(path: Path, limit: int) -> list[dict[str, Any]]:
    rows = read_csv(path)
    required = {
        "case_id",
        "input",
        "input_compact",
        "expected",
        "acceptable_targets",
        "use_in_primary_score",
        "clean_categories",
        "clean_error_types",
        "effective_levenshtein",
        "effective_damerau",
    }
    missing = required - set(rows[0]) if rows else required
    if missing:
        raise ValueError(f"missing clean-core columns: {sorted(missing)}")
    rows = [row for row in rows if row["use_in_primary_score"] == "1"]
    if limit:
        rows = rows[:limit]
    cases = [prepare_case(row) for row in rows]
    case_ids = [case["case_id"] for case in cases]
    pairs = [(case["input_compact"], case["expected_family_keys"]) for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("case IDs are not unique")
    if len(pairs) != len(set(pairs)):
        raise ValueError("compact query-target pairs are not unique")
    if not cases:
        raise ValueError("no primary clean-core cases were loaded")
    return cases


def result_name(item: dict[str, Any]) -> str:
    return str(
        item.get("name")
        or item.get("candidate_canonical_name")
        or item.get("canonical_name")
        or item.get("commercial_name")
        or ""
    ).strip()


def evaluate_case(
    case: dict[str, Any],
    algorithm: str,
    runner: Any,
) -> dict[str, Any]:
    started = time.perf_counter()
    output = runner(case["input"])
    latency_ms = (time.perf_counter() - started) * 1000
    results = list(output.get("results") or [])[:TOP_K]
    names = [result_name(item) for item in results]
    expected = set(case["expected_family_keys"].split(";"))
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
        "run_id": RUN_ID,
        "dataset": DATASET_ID,
        "case_id": case["case_id"],
        "algorithm": algorithm,
        "algorithm_name": DISPLAY_NAMES[algorithm],
        **{field: case[field] for field in RESULT_FIELDS if field in case},
        "response_status": status,
        "decision_type": str(output.get("decision_type") or status),
        "needs_clarification": int(bool(results) and (top_clarifies or not confident)),
        "candidate_count": int(output.get("candidate_count") or len(results)),
        "first_relevant_rank": rank,
        "hit_at_1": int(rank <= 1),
        "hit_at_5": int(rank <= 5),
        "hit_at_10": int(rank <= 10),
        "hit_at_20": int(rank <= 20),
        "reciprocal_rank_at_20": round(1 / rank, 8) if rank <= 20 else 0.0,
        "unsafe_confident_top1": int(bool(results) and confident and rank != 1),
        "no_result": int(not results),
        "latency_ms": round(latency_ms, 4),
        "top_1": names[0] if names else "",
        "top_5": ";".join(names[:5]),
    }


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    index = min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def metric_row(
    algorithm: str,
    dimension: str,
    group: str,
    rows: list[dict[str, Any]],
    total_failures: int,
    preparation_ms: float,
) -> dict[str, Any]:
    count = len(rows)
    failures = sum(1 - int(row["hit_at_20"]) for row in rows)
    latencies = [float(row["latency_ms"]) for row in rows]
    return {
        "evaluation_version": EVALUATION_VERSION,
        "run_id": RUN_ID,
        "dataset": DATASET_ID,
        "algorithm": algorithm,
        "algorithm_name": DISPLAY_NAMES[algorithm],
        "denominator": "primary_clean_unique_pair",
        "split": group if dimension == "split" else "all",
        "dimension": dimension,
        "group": group,
        "cases": count,
        "hit_at_1": sum(int(row["hit_at_1"]) for row in rows) / count,
        "hit_at_5": sum(int(row["hit_at_5"]) for row in rows) / count,
        "hit_at_10": sum(int(row["hit_at_10"]) for row in rows) / count,
        "hit_at_20": sum(int(row["hit_at_20"]) for row in rows) / count,
        "mrr_at_20": sum(float(row["reciprocal_rank_at_20"]) for row in rows) / count,
        "behavior_success_rate": sum(int(row["hit_at_20"]) for row in rows) / count,
        "unsafe_confident_top1_rate": sum(int(row["unsafe_confident_top1"]) for row in rows) / count,
        "clarification_rate": sum(int(row["needs_clarification"]) for row in rows) / count,
        "no_result_rate": sum(int(row["no_result"]) for row in rows) / count,
        "failure_count": failures,
        "failure_rate": failures / count,
        "failure_share": failures / total_failures if total_failures else 0.0,
        "mean_candidate_count": statistics.fmean(int(row["candidate_count"]) for row in rows),
        "mean_latency_ms": statistics.fmean(latencies),
        "median_latency_ms": statistics.median(latencies),
        "p95_latency_ms": percentile(latencies, 0.95),
        "p99_latency_ms": percentile(latencies, 0.99),
        "preparation_ms": preparation_ms,
    }


def grouped_rows(
    rows: list[dict[str, Any]],
    field: str,
    *,
    memberships: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        values = split_labels(row[field]) if memberships else [str(row[field])]
        for value in values:
            groups.setdefault(value or "unknown", []).append(row)
    return groups


def aggregate_metrics(
    algorithm: str,
    rows: list[dict[str, Any]],
    preparation_ms: float,
) -> list[dict[str, Any]]:
    total_failures = sum(1 - int(row["hit_at_20"]) for row in rows)
    output = [
        metric_row(algorithm, "overall", "all", rows, total_failures, preparation_ms)
    ]
    dimensions = (
        ("split", "split", False),
        ("difficulty", "difficulty", False),
        ("danger", "danger", False),
        ("effective_levenshtein", "effective_levenshtein", False),
        ("effective_damerau", "effective_damerau", False),
        ("distance_band", "distance_band", False),
        ("operation_family", "operation_family", False),
        ("query_length_band", "query_length_band", False),
        ("shared_bigram_band", "shared_bigram_band", False),
        ("clean_category", "clean_categories", True),
        ("clean_error_type", "clean_error_types", True),
        ("evaluation_track", "evaluation_track_memberships", True),
    )
    for dimension, field, memberships in dimensions:
        groups = grouped_rows(rows, field, memberships=memberships)
        for group in sorted(groups):
            output.append(
                metric_row(
                    algorithm,
                    dimension,
                    group,
                    groups[group],
                    total_failures,
                    preparation_ms,
                )
            )
    return output


def validate_catalog(cases: list[dict[str, Any]], records: list[dict[str, Any]]) -> None:
    catalog_keys = {
        current_app.compact_key(record.get("b") or record.get("n") or "")
        for record in records
    }
    missing = sorted(
        {
            key
            for case in cases
            for key in case["expected_family_keys"].split(";")
            if key not in catalog_keys
        }
    )
    if missing:
        raise ValueError(f"{len(missing)} acceptable targets are absent from the catalog")


def run() -> None:
    args = parse_args()
    cases = load_cases(args.cases, args.limit)
    records = current_app.prepare_records()
    validate_catalog(cases, records)

    requested = [value.strip() for value in args.algorithms.split(",") if value.strip()]
    unknown = set(requested) - set(ALGORITHM_ORDER)
    if unknown:
        raise ValueError(f"unknown algorithms: {sorted(unknown)}")
    prepared = {
        runner.name: runner
        for runner in retrieval.prepare_retrieval_runners(records)
        if runner.name in requested
    }
    if set(prepared) != set(requested):
        raise ValueError(f"failed to prepare: {sorted(set(requested) - set(prepared))}")

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    args.results_dir.mkdir(parents=True, exist_ok=True)
    case_path = args.artifacts_dir / "case_results.csv"
    metric_path = args.results_dir / "metrics.csv"
    all_metrics: list[dict[str, Any]] = []

    with case_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for position, algorithm in enumerate(requested, 1):
            runner = prepared[algorithm]
            started = time.perf_counter()
            rows = [evaluate_case(case, algorithm, runner.run) for case in cases]
            writer.writerows(rows)
            handle.flush()
            algorithm_metrics = aggregate_metrics(algorithm, rows, runner.preparation_ms)
            all_metrics.extend(algorithm_metrics)
            elapsed = time.perf_counter() - started
            overall = algorithm_metrics[0]
            print(
                f"[{position}/{len(requested)}] {algorithm}: "
                f"H@1={overall['hit_at_1']:.4%}, H@20={overall['hit_at_20']:.4%}, "
                f"elapsed={elapsed:.1f}s",
                flush=True,
            )

    metric_fields = list(all_metrics[0])
    write_csv(metric_path, all_metrics, metric_fields)
    print(f"Wrote {len(cases) * len(requested):,} case rows to {case_path}")
    print(f"Wrote {len(all_metrics):,} aggregate rows to {metric_path}")


if __name__ == "__main__":
    run()

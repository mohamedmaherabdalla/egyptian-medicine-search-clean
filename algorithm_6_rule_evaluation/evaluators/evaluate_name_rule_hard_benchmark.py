#!/usr/bin/env python3
"""Evaluate the hard name-reading benchmark against the public Algorithm 6 API.

Accuracy rows measure rank and never become green simply because a target was
selected while generating the data.  Safety and source-boundary rows are hard
contracts.  Every run snapshots the exact CSVs and manifest beside row-level
responses so later documentation cannot silently point at a regenerated set.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from provenance import collect_provenance


MANIFEST_PATH = PACKAGE / "test_sets" / "manifests" / "name_rule_hard_benchmark.manifest.json"
RESULTS = PACKAGE / "results" / "name_rule_hard_benchmark"
CATALOG_SHA256 = "d234edaa2669d1eeb46b962e7e3e02df52c6f4d2fd3eca7a2fbf3bc7d159fd9c"
ALGORITHM_DIR = REPO / "benchmark_01_legacy" / "master_algorithms"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compact(value: object) -> str:
    import re

    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def split_values(value: object) -> list[str]:
    return [compact(item) for item in str(value or "").split(";") if compact(item)]


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return float(ordered[index])


def get_json(url: str, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[dict[str, Any], float]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.load(response)
    return body, (time.perf_counter() - started) * 1000


def result_family_key(item: dict[str, Any]) -> str:
    if item.get("source") == "algorithm_6_visual_gap":
        return compact(
            item.get("matched_family_key")
            or item.get("matched_family_name")
            or item.get("base_group_key")
        )
    return compact(
        item.get("base_group_key")
        or item.get("matched_family_key")
        or item.get("variant_group")
        or item.get("name")
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def verify_manifest() -> tuple[dict[str, Any], list[tuple[str, Path, list[dict[str, str]]]]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["catalog"]["sha256"] != CATALOG_SHA256:
        raise RuntimeError("manifest does not reference the final catalog")
    datasets = []
    for record in manifest["files"]:
        path = REPO / record["path"]
        if sha256_path(path) != record["sha256"]:
            raise RuntimeError(f"dataset hash mismatch: {path}")
        rows = read_csv(path)
        if len(rows) != record["rows"]:
            raise RuntimeError(f"dataset row mismatch: {path}")
        datasets.append((record["name"], path, rows))
    return manifest, datasets


def confirmation_failures(response: dict[str, Any]) -> list[str]:
    failures = []
    if response.get("confirmation_required") is not True:
        failures.append("response_confirmation_required_false")
    for index, item in enumerate(response.get("results", ()), 1):
        if item.get("confirmation_required") is not True:
            failures.append(f"row_{index}_confirmation_required_false")
        if item.get("needs_clarification") is not True:
            failures.append(f"row_{index}_needs_clarification_false")
    return failures


def evaluate_api_row(
    dataset: str,
    row: dict[str, str],
    *,
    search_url: str,
    timeout: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    response, elapsed_ms = post_json(
        search_url,
        {
            "query": row["query"],
            "product_context": "",
            "limit": int(row.get("request_limit") or 20),
        },
        timeout,
    )
    failures = []
    if response.get("algorithm") != "algorithm_6":
        failures.append("wrong_algorithm_identity")
    if row.get("confirmation_required") == "1":
        failures.extend(confirmation_failures(response))

    observed = [result_family_key(item) for item in response.get("results", ())]
    relevant = split_values(row.get("relevant_family_keys"))
    ranks = [observed.index(family) + 1 for family in relevant if family in observed]
    visible_relevant = [family for family in relevant if family in observed]
    best_rank = min(ranks) if ranks else None
    hit1 = best_rank is not None and best_rank <= 1
    hit5 = best_rank is not None and best_rank <= 5
    hit20 = best_rank is not None and best_rank <= 20
    safety_pass = True
    policy = row.get("match_policy") or ""
    if row.get("evaluation_kind") == "safety":
        if policy == "literal_exact_rank1":
            expected = compact(row.get("source_family_key"))
            if not observed or observed[0] != expected:
                failures.append(f"literal_exact_not_rank1:{observed[:1]}!={expected}")
        elif policy == "all_relevant_visible":
            missing = [family for family in relevant if family not in observed]
            if missing:
                failures.append("missing_relevant:" + ";".join(missing))
        else:
            failures.append(f"unknown_safety_policy:{policy}")
        safety_pass = not failures
    elif row.get("evaluation_kind") == "diagnostic":
        if policy != "diagnostic_all_relevant":
            failures.append(f"unknown_diagnostic_policy:{policy}")

    result = {
        "dataset": dataset,
        "case_id": row["case_id"],
        "evaluation_kind": row["evaluation_kind"],
        "case_type": row["case_type"],
        "difficulty_level": row["difficulty_level"],
        "rule_family": row["rule_family"],
        "rule_id": row["rule_id"],
        "mapping": row.get("mapping") or "",
        "channels": row.get("channels") or "",
        "composition_signature": row.get("composition_signature") or "",
        "position_stratum": row.get("position_stratum") or "",
        "length_bucket": row.get("length_bucket") or "",
        "split": row["split"],
        "query": row["query"],
        "relevant_family_keys": relevant,
        "observed_family_keys": observed,
        "relevant_visible_count": len(visible_relevant),
        "relevant_count": len(relevant),
        "relevant_recall20": (len(visible_relevant) / len(relevant)) if relevant else 0.0,
        "best_rank": best_rank,
        "hit1": hit1,
        "hit5": hit5,
        "hit20": hit20,
        "reciprocal_rank": (1.0 / best_rank) if best_rank else 0.0,
        "safety_pass": safety_pass,
        "contract_pass": not failures,
        "failures": failures,
        "decision_type": response.get("decision_type"),
        "status": response.get("status"),
        "candidate_count": response.get("candidate_count", len(observed)),
        "elapsed_ms": elapsed_ms,
    }
    raw = {
        "dataset": dataset,
        "case_id": row["case_id"],
        "request": {"query": row["query"], "product_context": "", "limit": int(row.get("request_limit") or 20)},
        "elapsed_ms": elapsed_ms,
        "response": response,
    }
    return result, raw


def load_algorithm5() -> Any:
    if str(ALGORITHM_DIR) not in sys.path:
        sys.path.insert(0, str(ALGORITHM_DIR))
    import algorithm_6_consensus_search as algorithm_6  # type: ignore

    return algorithm_6.prepare_catalog().algorithm_5_module


def evaluate_source_row(dataset: str, row: dict[str, str], algorithm_5: Any) -> dict[str, Any]:
    contract = row["expected_source_contract"]
    query = row["query"]
    expected = row.get("expected_source_value") or ""
    forbidden = row.get("forbidden_source_value") or ""
    observed: Any = None
    passed = False
    if contract == "maximum_grapheme_confusions":
        observed = algorithm_5.maximum_grapheme_confusions(query)
        passed = observed == int(expected)
    elif contract == "variant_absent":
        variants = [value for value, _, _ in algorithm_5.grapheme_confusion_variants(query, output_limit=None)]
        observed = variants
        passed = forbidden not in variants
    elif contract == "first_char_variants_exact":
        observed_set = sorted(algorithm_5.first_char_variants(query))
        expected_set = sorted(item for item in expected.split(";") if item)
        observed = observed_set
        passed = observed_set == expected_set
    elif contract == "variant_count_at_most":
        observed = len(algorithm_5.grapheme_confusion_variants(query))
        passed = observed <= int(expected)
    elif contract == "variants_repeat_exactly":
        first = algorithm_5.grapheme_confusion_variants(query)
        second = algorithm_5.grapheme_confusion_variants(query)
        observed = {"count": len(first), "equal": first == second}
        passed = first == second
    else:
        observed = "unknown_contract"
    failures = [] if passed else [f"source_contract_failed:{contract}:{observed}!={expected}"]
    return {
        "dataset": dataset,
        "case_id": row["case_id"],
        "evaluation_kind": row["evaluation_kind"],
        "case_type": row["case_type"],
        "difficulty_level": row["difficulty_level"],
        "rule_family": row["rule_family"],
        "rule_id": row["rule_id"],
        "mapping": "",
        "channels": "source_function",
        "composition_signature": "",
        "position_stratum": row.get("position_stratum") or "",
        "length_bucket": row.get("length_bucket") or "",
        "split": row["split"],
        "query": query,
        "relevant_family_keys": [],
        "observed_family_keys": [],
        "best_rank": None,
        "hit1": False,
        "hit5": False,
        "hit20": False,
        "reciprocal_rank": 0.0,
        "safety_pass": passed,
        "contract_pass": passed,
        "failures": failures,
        "source_contract": contract,
        "source_observed": observed,
        "elapsed_ms": 0.0,
    }


def aggregate_accuracy(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    metric_rows = [row for row in rows if row["evaluation_kind"] == "accuracy"]
    return {
        "cases": len(metric_rows),
        "hit1": sum(bool(row["hit1"]) for row in metric_rows),
        "hit5": sum(bool(row["hit5"]) for row in metric_rows),
        "hit20": sum(bool(row["hit20"]) for row in metric_rows),
        "mrr20": sum(float(row["reciprocal_rank"]) for row in metric_rows) / len(metric_rows) if metric_rows else 0.0,
        "empty": sum(not row["observed_family_keys"] for row in metric_rows),
    }


def grouped_accuracy(rows: Sequence[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["evaluation_kind"] == "accuracy":
            groups[str(row.get(field) or "unspecified")].append(row)
    return {key: aggregate_accuracy(values) for key, values in sorted(groups.items())}


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8014")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--run-id", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest, datasets = verify_manifest()
    provenance = collect_provenance(REPO)
    base_url = args.base_url.rstrip("/")
    runtime = get_json(base_url + "/api/runtime", args.timeout)
    health = get_json(base_url + "/health", args.timeout)
    if runtime.get("algorithm") != "algorithm_6" or runtime.get("family_count") != 17_476:
        raise RuntimeError(f"unexpected runtime identity: {runtime}")
    if health.get("status") not in {"ok", "healthy"}:
        raise RuntimeError(f"unhealthy endpoint: {health}")

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RESULTS / "runs" / run_id
    if run_dir.exists():
        raise FileExistsError(run_dir)
    snapshot_dir = run_dir / "input_snapshot"
    snapshot_dir.mkdir(parents=True)
    shutil.copy2(MANIFEST_PATH, snapshot_dir / MANIFEST_PATH.name)
    for _, path, _ in datasets:
        shutil.copy2(path, snapshot_dir / path.name)

    algorithm_5 = load_algorithm5()
    api_jobs: list[tuple[str, dict[str, str]]] = []
    source_jobs: list[tuple[str, dict[str, str]]] = []
    for name, _, rows in datasets:
        for row in rows:
            (source_jobs if row["evaluation_kind"] == "source_contract" else api_jobs).append((name, row))

    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                evaluate_api_row,
                dataset,
                row,
                search_url=base_url + "/api/search",
                timeout=args.timeout,
            ): (dataset, row["case_id"])
            for dataset, row in api_jobs
        }
        for future in as_completed(futures):
            result, raw = future.result()
            results.append(result)
            raw_rows.append(raw)
    for dataset, row in source_jobs:
        results.append(evaluate_source_row(dataset, row, algorithm_5))
    results.sort(key=lambda row: (row["dataset"], row["case_id"]))
    raw_rows.sort(key=lambda row: (row["dataset"], row["case_id"]))
    wall_seconds = time.perf_counter() - started

    safety = [row for row in results if row["evaluation_kind"] == "safety"]
    diagnostic = [row for row in results if row["evaluation_kind"] == "diagnostic"]
    source = [row for row in results if row["evaluation_kind"] == "source_contract"]
    contract_failures = [row for row in results if not row["contract_pass"]]
    latencies = [float(row["elapsed_ms"]) for row in results if row["evaluation_kind"] != "source_contract"]
    summary = {
        "schema_version": 2,
        "run_id": run_id,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "workers": args.workers,
        "timeout_seconds": args.timeout,
        "wall_seconds": wall_seconds,
        "runtime": runtime,
        "health": health,
        "source_provenance": provenance,
        "manifest": {
            "path": str(MANIFEST_PATH.relative_to(REPO)),
            "sha256": sha256_path(MANIFEST_PATH),
            "generator_sha256": manifest["generator_sha256"],
            "seed": manifest["seed"],
        },
        "evaluator": {
            "path": str(Path(__file__).relative_to(REPO)),
            "sha256": sha256_path(Path(__file__)),
        },
        "row_counts": dict(Counter(row["dataset"] for row in results)),
        "accuracy": {
            "overall": aggregate_accuracy(results),
            "by_dataset": grouped_accuracy(results, "dataset"),
            "by_split": grouped_accuracy(results, "split"),
            "by_difficulty": grouped_accuracy(results, "difficulty_level"),
            "by_rule_family": grouped_accuracy(results, "rule_family"),
            "by_composition_signature": grouped_accuracy(results, "composition_signature"),
            "by_position": grouped_accuracy(results, "position_stratum"),
            "by_length": grouped_accuracy(results, "length_bucket"),
        },
        "safety": {
            "cases": len(safety),
            "passed": sum(bool(row["safety_pass"]) for row in safety),
            "failed": sum(not row["safety_pass"] for row in safety),
            "by_case_type": {
                key: {
                    "cases": len(values),
                    "passed": sum(bool(row["safety_pass"]) for row in values),
                }
                for key, values in sorted(
                    (
                        key,
                        [row for row in safety if row["case_type"] == key],
                    )
                    for key in {row["case_type"] for row in safety}
                )
            },
        },
        "diagnostics": {
            "cases": len(diagnostic),
            "relevant_labels": sum(int(row["relevant_count"]) for row in diagnostic),
            "visible_relevant_labels": sum(int(row["relevant_visible_count"]) for row in diagnostic),
            "micro_recall20": (
                sum(int(row["relevant_visible_count"]) for row in diagnostic)
                / sum(int(row["relevant_count"]) for row in diagnostic)
            ) if diagnostic else 0.0,
            "complete_visibility_cases": sum(
                int(row["relevant_visible_count"]) == int(row["relevant_count"])
                for row in diagnostic
            ),
            "interpretation": (
                "Cross-rule query collisions can involve unlike transformations and costs; "
                "breadth is reported, not treated as an equal-evidence safety gate."
            ),
        },
        "source_boundaries": {
            "cases": len(source),
            "passed": sum(bool(row["contract_pass"]) for row in source),
            "failed": sum(not row["contract_pass"] for row in source),
        },
        "contract_failures": len(contract_failures),
        "latency_ms": {
            "count": len(latencies),
            "mean": sum(latencies) / len(latencies) if latencies else 0.0,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": max(latencies) if latencies else 0.0,
            "note": "Concurrent HTTP diagnostic; not comparable to a serial warmed runtime benchmark.",
        },
        "claim_boundaries": [
            "Catalog-derived development/holdout rows are retrospective and not blind natural OCR.",
            "Accuracy misses stay in the denominator and do not fail the evaluator process.",
            "Safety and source-boundary failures are hard contract failures.",
            "Cross-rule collision diagnostics are not equal-evidence safety labels.",
            "The relevance oracle covers declared generation channels, not every clinically plausible fuzzy interpretation.",
        ],
    }
    write_jsonl(run_dir / "per_case.jsonl", results)
    write_jsonl(run_dir / "raw_responses.jsonl", raw_rows)
    write_jsonl(run_dir / "failures.jsonl", contract_failures)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    RESULTS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run_dir / "summary.json", RESULTS / "latest_summary.json")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if contract_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

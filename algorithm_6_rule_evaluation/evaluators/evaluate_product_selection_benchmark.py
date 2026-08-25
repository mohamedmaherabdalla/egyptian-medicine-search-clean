#!/usr/bin/env python3
"""Evaluate strict product-ID selection on the generated benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().parents[1]
DATASET = PACKAGE / "test_sets" / "generated" / "product_selection_strict.csv"
DATASET_MANIFEST = PACKAGE / "test_sets" / "manifests" / "product_selection_strict.manifest.json"
RESULTS = PACKAGE / "results" / "product_selection_strict"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_set(value: object) -> set[str]:
    return {item for item in str(value or "").split(";") if item}


def request_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[dict[str, Any], float]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response), (time.perf_counter() - started) * 1000


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def source_hashes() -> dict[str, str]:
    paths = {
        "algorithm_5": REPO / "benchmark_01_legacy/master_algorithms/algorithm_5_commercial_name_search.py",
        "algorithm_6": REPO / "benchmark_01_legacy/master_algorithms/algorithm_6_consensus_search.py",
        "product_reranker": REPO / "app/product_context_reranker.py",
        "api": REPO / "app/api.py",
        "catalog": REPO / "app/data/catalog.json",
        "evaluator": Path(__file__),
    }
    return {name: sha256_path(path) for name, path in paths.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8014")
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()

    manifest = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
    if sha256_path(DATASET) != manifest["dataset_sha256"]:
        raise SystemExit("strict product dataset hash does not match its manifest")
    with DATASET.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    search_url = args.base_url.rstrip("/") + "/api/search"
    results: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    for row in rows:
        response, elapsed = request_json(
            search_url,
            {"query": row["query"], "product_context": row["product_context"], "limit": 20},
            args.timeout,
        )
        returned = response.get("results", [])
        selected = [str(item.get("selected_product_id") or "") for item in returned if item.get("selected_product_id")]
        observed_families = {
            "".join(ch for ch in str(item.get("base_group_key") or item.get("name") or "").upper() if ch.isalnum())
            for item in returned
        }
        acceptable = split_set(row["acceptable_product_ids"])
        forbidden = split_set(row["forbidden_product_ids"])
        failures: list[str] = []
        if response.get("algorithm") != "algorithm_6":
            failures.append("wrong_algorithm")
        if response.get("confirmation_required") is not True:
            failures.append("response_not_confirmation_required")
        if any(item.get("confirmation_required") is not True for item in returned):
            failures.append("row_not_confirmation_required")
        if response.get("decision_type") != row["expected_decision"]:
            failures.append(f"decision:{response.get('decision_type')}!={row['expected_decision']}")
        if row["expected_family"] not in observed_families:
            failures.append("expected_family_missing")

        if row["match_policy"] == "abstain_no_product":
            if selected:
                failures.append("product_selected_during_required_abstention")
        else:
            if not selected:
                failures.append("no_product_selected")
            if acceptable and not acceptable.issubset(set(selected)):
                failures.append("not_all_acceptable_product_ids_returned")
            unexpected = set(selected) - acceptable
            if unexpected:
                failures.append("unexpected_selected_product_ids:" + ",".join(sorted(unexpected)))
        leaked = set(selected) & forbidden
        if leaked:
            failures.append("forbidden_product_ids_returned:" + ",".join(sorted(leaked)))

        result = dict(row)
        result.update({
            "passed": not failures,
            "failures": failures,
            "observed_decision": response.get("decision_type"),
            "observed_product_ids": selected,
            "observed_family_keys": sorted(observed_families),
            "elapsed_ms": elapsed,
        })
        results.append(result)
        raw.append({"case_id": row["case_id"], "response": response})

    RESULTS.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RESULTS / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    per_case = run_dir / "per_case.jsonl"
    with per_case.open("w", encoding="utf-8") as handle:
        for row in results:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    raw_path = run_dir / "raw_responses.jsonl"
    with raw_path.open("w", encoding="utf-8") as handle:
        for row in raw:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        grouped[row["stratum"]].append(row)
    latencies = [float(row["elapsed_ms"]) for row in results]
    summary = {
        "run_id": run_id,
        "endpoint": args.base_url.rstrip("/"),
        "source_hashes": source_hashes(),
        "dataset": manifest,
        "cases": len(results),
        "passed": sum(bool(row["passed"]) for row in results),
        "failed": sum(not bool(row["passed"]) for row in results),
        "by_stratum": {
            name: {
                "cases": len(members),
                "passed": sum(bool(row["passed"]) for row in members),
                "failed": sum(not bool(row["passed"]) for row in members),
            }
            for name, members in sorted(grouped.items())
        },
        "failure_reasons": dict(Counter(reason for row in results for reason in row["failures"])),
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "mean": statistics.mean(latencies) if latencies else 0.0,
        },
        "artifacts": {
            "per_case_sha256": sha256_path(per_case),
            "raw_responses_sha256": sha256_path(raw_path),
        },
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "latest_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Compare two Algorithm 6 APIs on the locked fair-OCR case set.

Visual-gap responses changed from exposing the broad variant group as their
public name to exposing the exact matched base family.  This evaluator uses the
exact visual identity on both sides, so representation-only changes cannot be
counted as retrieval gains or losses.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any


LOCKED_SHA256 = "3ad1a423cadc96b29665a8c600c27eb25bc743a5274f4a2c7917402fe09979bd"


def compact(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def result_identity(item: dict[str, Any]) -> str:
    if item.get("source") == "algorithm_6_visual_gap":
        return compact(
            item.get("matched_family_key")
            or item.get("matched_family_name")
            or item.get("commercial_name")
        )
    return compact(
        item.get("base_group_key")
        or item.get("variant_group")
        or item.get("name")
    )


def get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=90) as response:
        return json.load(response)


def fetch(
    base_url: str,
    query: str,
    *,
    require_confirmation: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/search",
        data=json.dumps(
            {"query": query, "product_context": "", "limit": 20}
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.load(response)
    except Exception as error:
        raise RuntimeError(f"request failed for {query!r}: {error}") from error
    elapsed_ms = (time.perf_counter() - started) * 1000
    results = payload.get("results", [])
    assert payload.get("algorithm") == "algorithm_6", query
    assert len(results) <= 20, query
    if require_confirmation:
        assert payload.get("confirmation_required") is True, query
        assert all(item.get("confirmation_required") is True for item in results), query
        assert all(item.get("needs_clarification") is True for item in results), query
    return {
        "keys": [result_identity(item) for item in results],
        "elapsed_ms": elapsed_ms,
        "empty": not results,
    }


def result_rank(keys: list[str], expected: set[str]) -> int | None:
    return next((index for index, key in enumerate(keys, 1) if key in expected), None)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * fraction))
    return ordered[index]


def metrics(outputs: list[dict[str, Any]], ranks: list[int | None]) -> dict[str, Any]:
    return {
        "cases": len(ranks),
        "hit1": sum(value == 1 for value in ranks),
        "hit5": sum(value is not None and value <= 5 for value in ranks),
        "hit20": sum(value is not None and value <= 20 for value in ranks),
        "mrr20": sum(
            1 / value for value in ranks if value is not None and value <= 20
        ) / len(ranks),
        "empty_results": sum(bool(item["empty"]) for item in outputs),
        "p50_ms": percentile([float(item["elapsed_ms"]) for item in outputs], 0.50),
        "p95_ms": percentile([float(item["elapsed_ms"]) for item in outputs], 0.95),
        "p99_ms": percentile([float(item["elapsed_ms"]) for item in outputs], 0.99),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--old", required=True, help="Old API base URL")
    parser.add_argument("--new", required=True, help="Candidate API base URL")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--allow-unlocked-csv",
        action="store_true",
        help="Report another compatible CSV without enforcing the locked hash",
    )
    args = parser.parse_args()

    csv_bytes = args.csv.read_bytes()
    csv_sha256 = hashlib.sha256(csv_bytes).hexdigest()
    if not args.allow_unlocked_csv and csv_sha256 != LOCKED_SHA256:
        raise SystemExit(
            f"locked CSV hash mismatch: expected {LOCKED_SHA256}, got {csv_sha256}"
        )

    with args.csv.open(newline="", encoding="utf-8-sig") as handle:
        all_rows = list(csv.DictReader(handle))
    cases = [
        row
        for row in all_rows
        if row.get("accepted") == "1" and row.get("scored_case") == "1"
    ]
    if not cases:
        raise SystemExit("the CSV contains no accepted, scored cases")
    case_ids = [row["case_id"] for row in cases]
    if len(set(case_ids)) != len(case_ids):
        raise SystemExit("accepted/scored case_id values are not unique")
    expected = [
        {compact(value) for value in row["expected_family_key"].split(";") if value}
        for row in cases
    ]
    if any(not values for values in expected):
        raise SystemExit("an accepted/scored case has no expected family key")

    old_runtime = get_json(args.old.rstrip("/") + "/api/runtime")
    new_runtime = get_json(args.new.rstrip("/") + "/api/runtime")
    if old_runtime.get("algorithm") != "algorithm_6":
        raise SystemExit("old endpoint is not Algorithm 6")
    if new_runtime.get("algorithm") != "algorithm_6" or not new_runtime.get("ready"):
        raise SystemExit("new endpoint is not a ready Algorithm 6 runtime")

    def run(base_url: str, *, require_confirmation: bool) -> list[dict[str, Any]]:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            return list(
                pool.map(
                    lambda row: fetch(
                        base_url,
                        row["input"],
                        require_confirmation=require_confirmation,
                    ),
                    cases,
                )
            )

    old_outputs = run(args.old, require_confirmation=False)
    new_outputs = run(args.new, require_confirmation=True)
    old_ranks = [
        result_rank(output["keys"], target)
        for output, target in zip(old_outputs, expected)
    ]
    new_ranks = [
        result_rank(output["keys"], target)
        for output, target in zip(new_outputs, expected)
    ]

    changes: list[dict[str, Any]] = []
    rank1_losses: list[dict[str, Any]] = []
    hit20_losses: list[dict[str, Any]] = []
    hit5_losses: list[dict[str, Any]] = []
    for row, old_rank, new_rank in zip(cases, old_ranks, new_ranks):
        if old_rank == new_rank:
            continue
        change = {
            "case_id": row["case_id"],
            "query": row["input"],
            "expected": row["expected_family_key"],
            "old_rank": old_rank,
            "new_rank": new_rank,
        }
        changes.append(change)
        if old_rank == 1 and new_rank != 1:
            rank1_losses.append(change)
        if old_rank is not None and old_rank <= 20 and new_rank is None:
            hit20_losses.append(change)
        if (
            old_rank is not None
            and old_rank <= 5
            and (new_rank is None or new_rank > 5)
        ):
            hit5_losses.append(change)

    report = {
        "dataset": {
            "path": str(args.csv),
            "sha256": csv_sha256,
            "rows": len(all_rows),
            "accepted_scored_cases": len(cases),
            "splits": dict(Counter(row.get("split") or "" for row in cases)),
            "multi_expected_cases": sum(len(values) > 1 for values in expected),
        },
        "old_runtime": old_runtime,
        "new_runtime": new_runtime,
        "old": metrics(old_outputs, old_ranks),
        "new": metrics(new_outputs, new_ranks),
        "rank1_losses": rank1_losses,
        "hit20_losses": hit20_losses,
        "hit5_losses": hit5_losses,
        "changed_case_count": len(changes),
        "changes": changes,
    }
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.report:
        args.report.write_text(rendered + "\n", encoding="utf-8")

    passed = (
        not rank1_losses
        and not hit5_losses
        and not hit20_losses
        and report["new"]["hit5"] >= report["old"]["hit5"]
        and report["new"]["mrr20"] >= report["old"]["mrr20"]
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

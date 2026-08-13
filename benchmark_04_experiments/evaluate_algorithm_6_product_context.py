#!/usr/bin/env python3
"""Evaluate exact product evidence on 200 deterministic name-error cases.

The sample definition intentionally matches the August 11 release check that
measured 197/200 baseline Hit@1 and 200/200 after exact-strength reranking.
Run it against a healthy one-worker Algorithm 6 API; it exits nonzero if exact
context fails to reach every target or regresses any baseline-correct case.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "app" / "data" / "catalog.json"
LOCKED_CATALOG_SHA256 = "d234edaa2669d1eeb46b962e7e3e02df52c6f4d2fd3eca7a2fbf3bc7d159fd9c"
LOCKED_CASES_SHA256 = "21e0992188f27364582660b8072837c9d5d0fd3bcb3bbbf9c41bf7e471fd7ff5"


def compact(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def mutate(name: str) -> str:
    index = len(name) // 2
    replacement = "A" if name[index] != "A" else "O"
    return name[:index] + replacement + name[index + 1 :]


def search(url: str, query: str, context: str = "") -> dict[str, Any]:
    body = json.dumps(
        {"query": query, "product_context": context, "limit": 20}
    ).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def deterministic_cases(catalog_path: Path) -> list[tuple[str, str, str]]:
    records = json.loads(catalog_path.read_text(encoding="utf-8"))["records"]
    families: dict[str, str] = {}
    for record in records:
        family = compact(record.get("b"))
        strength = str(record.get("st") or "").strip()
        if not (
            4 <= len(family) <= 12
            and family.isalpha()
            and re.search(r"\d", strength)
        ):
            continue
        families.setdefault(family, strength)
    return sorted(
        (
            (mutate(family), family, strength)
            for family, strength in families.items()
        ),
        key=lambda row: hashlib.sha256("|".join(row).encode()).hexdigest(),
    )[:200]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8013/api/search",
        help="Algorithm 6 search endpoint",
    )
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional JSON report path",
    )
    parser.add_argument(
        "--expected-baseline",
        type=int,
        default=197,
        help="Required baseline Hit@1 count; use -1 to report without enforcing",
    )
    parser.add_argument(
        "--allow-unlocked-catalog",
        action="store_true",
        help="Evaluate another catalog without enforcing the August sample hashes",
    )
    args = parser.parse_args()

    catalog_sha256 = hashlib.sha256(args.catalog.read_bytes()).hexdigest()
    if not args.allow_unlocked_catalog and catalog_sha256 != LOCKED_CATALOG_SHA256:
        raise SystemExit(
            "locked catalog hash mismatch: "
            f"expected {LOCKED_CATALOG_SHA256}, got {catalog_sha256}"
        )
    cases = deterministic_cases(args.catalog)
    cases_sha256 = hashlib.sha256(
        json.dumps(
            cases,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if not args.allow_unlocked_catalog and cases_sha256 != LOCKED_CASES_SHA256:
        raise SystemExit(
            "locked deterministic sample hash mismatch: "
            f"expected {LOCKED_CASES_SHA256}, got {cases_sha256}"
        )
    baseline_hits = 0
    context_hits = 0
    regressions: list[dict[str, str]] = []
    recoveries: list[dict[str, str]] = []
    context_misses: list[dict[str, str]] = []

    for query, expected, strength in cases:
        baseline = search(args.url, query)
        reranked = search(args.url, query, strength)
        baseline_names = [
            compact(row.get("base_group_key"))
            for row in baseline.get("results", [])
        ]
        context_names = [
            compact(row.get("base_group_key"))
            for row in reranked.get("results", [])
        ]
        baseline_hit = bool(baseline_names and baseline_names[0] == expected)
        top_context_result = (
            reranked.get("results", [])[0]
            if reranked.get("results")
            else {}
        )
        context_hit = bool(
            context_names
            and context_names[0] == expected
            and reranked.get("decision_type")
            in {
                "product_context_selection",
                "numeric_commercial_alias_product_context_selection",
            }
            and top_context_result.get("selected_product_id")
            and top_context_result.get("context_match_status")
            != "no_compatible_product"
        )
        baseline_hits += baseline_hit
        context_hits += context_hit
        detail = {
            "query": query,
            "expected": expected,
            "strength": strength,
            "baseline_top": baseline_names[0] if baseline_names else "",
            "context_top": context_names[0] if context_names else "",
            "context_decision": str(reranked.get("decision_type") or ""),
            "selected_product_id": str(top_context_result.get("selected_product_id") or ""),
        }
        if baseline_hit and not context_hit:
            regressions.append(detail)
        if not baseline_hit and context_hit:
            recoveries.append(detail)
        if not context_hit:
            context_misses.append(detail)

    report = {
        "dataset": {
            "catalog_path": str(args.catalog),
            "catalog_sha256": catalog_sha256,
            "cases_sha256": cases_sha256,
        },
        "cases": len(cases),
        "baseline_hit1": baseline_hits,
        "expected_baseline_hit1": args.expected_baseline,
        "context_hit1": context_hits,
        "baseline_hit1_regressions": len(regressions),
        "recoveries": recoveries,
        "context_misses": context_misses,
        "regressions": regressions,
    }
    print(json.dumps(report, indent=2))
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    baseline_matches = (
        args.expected_baseline < 0
        or baseline_hits == args.expected_baseline
    )
    return 0 if baseline_matches and context_hits == len(cases) and not regressions else 1


if __name__ == "__main__":
    sys.exit(main())

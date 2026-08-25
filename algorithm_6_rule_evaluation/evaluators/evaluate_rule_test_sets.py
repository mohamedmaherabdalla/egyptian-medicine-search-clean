#!/usr/bin/env python3
"""Evaluate generated Algorithm 6 rule datasets against the public API."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import statistics
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from provenance import collect_provenance
from evaluators.result_contracts import validate_result_contract

GENERATED = PACKAGE / "test_sets" / "generated"
MANIFEST = PACKAGE / "test_sets" / "manifests" / "generation_manifest.json"
RESULTS = PACKAGE / "results"
CATALOG_SHA256 = "d234edaa2669d1eeb46b962e7e3e02df52c6f4d2fd3eca7a2fbf3bc7d159fd9c"


def compact(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def split_values(value: object) -> list[str]:
    return [compact(item) for item in str(value or "").split(";") if compact(item)]


def split_tokens(value: object) -> list[str]:
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return float(ordered[index])


def result_family_key(item: dict[str, Any]) -> str:
    if item.get("source") == "algorithm_6_visual_gap":
        return compact(
            item.get("matched_family_key")
            or item.get("matched_family_name")
            or item.get("base_group_key")
            or item.get("commercial_name")
        )
    return compact(
        item.get("base_group_key")
        or item.get("matched_family_key")
        or item.get("variant_group")
        or item.get("name")
    )


def reasons(item: dict[str, Any]) -> set[str]:
    value = item.get("reasons") or []
    if isinstance(value, str):
        return {part for part in value.split("|") if part}
    return {str(part) for part in value}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def verify_generation_manifest() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest["catalog"]["sha256"] != CATALOG_SHA256:
        raise RuntimeError("generation manifest catalog hash is not the final catalog")
    for record in manifest["generated_files"] + manifest["locked_files"]:
        path = REPO / record["file"]
        if sha256_path(path) != record["sha256"]:
            raise RuntimeError(f"dataset hash mismatch: {path}")
    return manifest


def validate_confirmation(response: dict[str, Any], failures: list[str]) -> None:
    if response.get("confirmation_required") is not True:
        failures.append("response_confirmation_required_false")
    for index, item in enumerate(response.get("results", []), 1):
        if item.get("confirmation_required") is not True:
            failures.append(f"row_{index}_confirmation_required_false")
        if item.get("needs_clarification") is not True:
            failures.append(f"row_{index}_needs_clarification_false")


def extend_unique(failures: list[str], additions: Iterable[str]) -> None:
    """Append contract failures once while preserving their stable order."""

    for failure in additions:
        if failure not in failures:
            failures.append(failure)


def evaluate_retrieval_case(
    row: dict[str, str],
    *,
    search_url: str,
    timeout: float,
) -> tuple[dict[str, str], dict[str, Any]]:
    request_limit = int(row.get("request_limit") or 20)
    response, elapsed_ms = post_json(
        search_url,
        {
            "query": row["query"],
            "product_context": row.get("product_context") or "",
            "limit": request_limit,
        },
        timeout,
    )
    failures: list[str] = []
    if response.get("algorithm") != "algorithm_6":
        failures.append("wrong_algorithm_identity")
    if row.get("confirmation_required") == "1":
        validate_confirmation(response, failures)
    extend_unique(failures, validate_result_contract(row, response))

    observed = [result_family_key(item) for item in response.get("results", [])]
    expected = split_values(row.get("expected_families"))
    forbidden = set(split_values(row.get("forbidden_families")))
    maximum_rank = int(row["maximum_rank"]) if row.get("maximum_rank") else 20
    for family in expected:
        if family not in observed:
            failures.append(f"missing_expected_family:{family}")
        elif observed.index(family) + 1 > maximum_rank:
            failures.append(f"expected_family_below_rank:{family}:{observed.index(family)+1}")
    for family in forbidden:
        if family in observed:
            failures.append(f"forbidden_family_returned:{family}:{observed.index(family)+1}")

    expected_decision = row.get("expected_decision") or ""
    decision = str(response.get("decision_type") or "")
    if expected_decision == "not_visual_gap":
        if decision == "visual_gap_matches":
            failures.append("unexpected_visual_gap_dispatch")
    elif expected_decision and decision != expected_decision:
        failures.append(f"decision:{decision}!={expected_decision}")
    expected_mode = row.get("expected_mode") or ""
    observed_mode = str((response.get("visual_gap") or {}).get("mode") or "")
    if expected_mode and observed_mode != expected_mode:
        failures.append(f"visual_mode:{observed_mode}!={expected_mode}")

    expected_candidate_count = row.get("expected_candidate_count") or ""
    if expected_candidate_count and int(response.get("candidate_count") or 0) != int(expected_candidate_count):
        failures.append(
            f"candidate_count:{response.get('candidate_count')}!={expected_candidate_count}"
        )

    target_family = compact(row.get("target_family_key"))
    if target_family:
        target_row = next(
            (item for item in response.get("results", []) if result_family_key(item) == target_family),
            None,
        )
        if target_row is None:
            failures.append(f"metric_target_missing:{target_family}")
        else:
            expected_hidden = row.get("expected_hidden_character_count") or ""
            if expected_hidden and int(target_row.get("hidden_character_count", -1)) != int(expected_hidden):
                failures.append(
                    "hidden_character_count:"
                    f"{target_row.get('hidden_character_count')}!={expected_hidden}"
                )
            expected_coverage = row.get("expected_visible_coverage") or ""
            if expected_coverage and abs(float(target_row.get("visible_coverage", -1)) - float(expected_coverage)) > 1e-5:
                failures.append(
                    f"visible_coverage:{target_row.get('visible_coverage')}!={expected_coverage}"
                )

    required_reason = row.get("required_reason") or ""
    forbidden_reason = row.get("forbidden_reason") or ""
    all_reasons = set().union(*(reasons(item) for item in response.get("results", []))) if response.get("results") else set()
    if required_reason and required_reason not in all_reasons:
        failures.append(f"required_reason_missing:{required_reason}")
    if forbidden_reason and forbidden_reason in all_reasons:
        failures.append(f"forbidden_reason_present:{forbidden_reason}")

    if row.get("rule_id") == "VG-PERFORMANCE-CAP" and elapsed_ms >= 2000:
        failures.append(f"latency_ms:{elapsed_ms:.3f}>=2000")

    result = {
        "case_id": row["case_id"],
        "suite": "visual_gap" if row["rule_id"].startswith("VG-") else "ocr_grapheme",
        "rule_id": row["rule_id"],
        "case_type": row["case_type"],
        "split": row["split"],
        "query": row["query"],
        "product_context": row.get("product_context") or "",
        "passed": "1" if not failures else "0",
        "failure_count": str(len(failures)),
        "failures": "|".join(failures),
        "expected_families": ";".join(expected),
        "observed_families": ";".join(observed),
        "decision_type": decision,
        "status": str(response.get("status") or ""),
        "candidate_count": str(response.get("candidate_count") or len(observed)),
        "elapsed_ms": f"{elapsed_ms:.3f}",
    }
    raw = {
        "case_id": row["case_id"],
        "request": {"query": row["query"], "product_context": row.get("product_context") or "", "limit": request_limit},
        "elapsed_ms": elapsed_ms,
        "response": response,
    }
    return result, raw


def evaluate_ordinary_typo_case(
    row: dict[str, str],
    *,
    search_url: str,
    timeout: float,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Evaluate ranking separately from safety-contract pass/fail.

    Accuracy-benchmark retrieval misses are measurements, not regression
    execution failures.  Collision and exact-name safety rows remain gating.
    """

    request_limit = int(row.get("request_limit") or 20)
    response, elapsed_ms = post_json(
        search_url,
        {
            "query": row["query"],
            "product_context": "",
            "limit": request_limit,
        },
        timeout,
    )
    failures: list[str] = []
    if response.get("algorithm") != "algorithm_6":
        failures.append("wrong_algorithm_identity")
    if row.get("confirmation_required") == "1":
        validate_confirmation(response, failures)

    decision = str(response.get("decision_type") or "")
    if decision == "visual_gap_matches":
        failures.append("unexpected_visual_gap_dispatch")

    observed = [result_family_key(item) for item in response.get("results", [])]
    expected = split_values(row.get("expected_families"))
    ranks = [observed.index(family) + 1 for family in expected if family in observed]
    first_relevant_rank = min(ranks) if ranks else 0
    hit1 = bool(first_relevant_rank and first_relevant_rank <= 1)
    hit5 = bool(first_relevant_rank and first_relevant_rank <= 5)
    hit20 = bool(first_relevant_rank and first_relevant_rank <= 20)
    reciprocal_rank = 1.0 / first_relevant_rank if first_relevant_rank else 0.0
    relevant_found_20 = sum(family in observed[:20] for family in expected)
    relevant_recall_20 = relevant_found_20 / len(expected) if expected else 0.0

    evaluation_kind = row.get("evaluation_kind") or "accuracy_benchmark"
    gating = evaluation_kind != "accuracy_benchmark"
    if gating:
        extend_unique(failures, validate_result_contract(row, response))
    if evaluation_kind == "collision_safety":
        for family in expected:
            if family not in observed[:20]:
                failures.append(f"missing_collision_family_top20:{family}")
    elif evaluation_kind == "exact_name_safety":
        expected_exact = expected[0] if expected else ""
        observed_top = observed[0] if observed else ""
        if observed_top != expected_exact:
            failures.append(f"exact_name_top1:{observed_top}!={expected_exact}")

    result = {
        "case_id": row["case_id"],
        "suite": (
            "ordinary_typo_benchmark"
            if evaluation_kind == "accuracy_benchmark"
            else "ordinary_typo_collision_safety"
        ),
        "evaluation_kind": evaluation_kind,
        "gating": "1" if gating else "0",
        "rule_id": row["rule_id"],
        "case_type": row["case_type"],
        "split": row["split"],
        "query": row["query"],
        "product_context": "",
        "passed": "1" if not failures else "0",
        "failure_count": str(len(failures)),
        "failures": "|".join(failures),
        "expected_families": ";".join(expected),
        "observed_families": ";".join(observed),
        "decision_type": decision,
        "status": str(response.get("status") or ""),
        "candidate_count": str(response.get("candidate_count") or len(observed)),
        "elapsed_ms": f"{elapsed_ms:.3f}",
        "primary_mutation": row.get("primary_mutation") or "",
        "mutation_strata": row.get("mutation_strata") or "",
        "query_length_bucket": row.get("query_length_bucket") or "",
        "collision_component_id": row.get("collision_component_id") or "",
        "relevance_count": str(len(expected)),
        "first_relevant_rank": str(first_relevant_rank),
        "hit1": "1" if hit1 else "0",
        "hit5": "1" if hit5 else "0",
        "hit20": "1" if hit20 else "0",
        "reciprocal_rank": f"{reciprocal_rank:.12f}",
        "relevant_found_20": str(relevant_found_20),
        "relevant_recall_20": f"{relevant_recall_20:.12f}",
    }
    raw = {
        "case_id": row["case_id"],
        "evaluation_kind": evaluation_kind,
        "request": {"query": row["query"], "product_context": "", "limit": request_limit},
        "ranking_metrics": {
            "first_relevant_rank": first_relevant_rank,
            "hit1": hit1,
            "hit5": hit5,
            "hit20": hit20,
            "reciprocal_rank": reciprocal_rank,
            "relevant_found_20": relevant_found_20,
            "relevant_recall_20": relevant_recall_20,
        },
        "elapsed_ms": elapsed_ms,
        "response": response,
    }
    return result, raw


def evaluate_product_case(
    row: dict[str, str],
    *,
    search_url: str,
    timeout: float,
) -> tuple[dict[str, str], dict[str, Any]]:
    baseline, baseline_ms = post_json(
        search_url,
        {"query": row["query"], "product_context": "", "limit": 20},
        timeout,
    )
    context, context_ms = post_json(
        search_url,
        {"query": row["query"], "product_context": row["product_context"], "limit": 20},
        timeout,
    )
    expected = split_values(row["expected_families"])[0]
    baseline_rows = baseline.get("results", [])
    context_rows = context.get("results", [])
    baseline_top = result_family_key(baseline_rows[0]) if baseline_rows else ""
    context_top = result_family_key(context_rows[0]) if context_rows else ""
    selected_id = str(context_rows[0].get("selected_product_id") or "") if context_rows else ""
    failures: list[str] = []
    validate_confirmation(context, failures)
    extend_unique(failures, validate_result_contract(row, context))
    if context_top != expected:
        failures.append(f"context_top:{context_top}!={expected}")
    if context.get("decision_type") not in {
        "product_context_selection",
        "numeric_commercial_alias_product_context_selection",
    }:
        failures.append(f"context_decision:{context.get('decision_type')}")
    if not selected_id:
        failures.append("selected_product_id_missing")
    if context_rows and context_rows[0].get("context_match_status") == "no_compatible_product":
        failures.append("no_compatible_product_placeholder")
    result = {
        "case_id": row["case_id"],
        "suite": "product_context_200",
        "rule_id": row["rule_id"],
        "case_type": row["case_type"],
        "split": row["split"],
        "query": row["query"],
        "product_context": row["product_context"],
        "passed": "1" if not failures else "0",
        "failure_count": str(len(failures)),
        "failures": "|".join(failures),
        "expected_families": expected,
        "observed_families": context_top,
        "decision_type": str(context.get("decision_type") or ""),
        "status": str(context.get("status") or ""),
        "candidate_count": str(context.get("candidate_count") or len(context_rows)),
        "elapsed_ms": f"{context_ms:.3f}",
        "baseline_top": baseline_top,
        "baseline_hit": "1" if baseline_top == expected else "0",
        "selected_product_id": selected_id,
        "baseline_elapsed_ms": f"{baseline_ms:.3f}",
    }
    raw = {
        "case_id": row["case_id"],
        "baseline_request": {"query": row["query"], "product_context": "", "limit": 20},
        "context_request": {"query": row["query"], "product_context": row["product_context"], "limit": 20},
        "baseline_elapsed_ms": baseline_ms,
        "context_elapsed_ms": context_ms,
        "baseline_response": baseline,
        "context_response": context,
    }
    return result, raw


def evaluate_source_contract(row: dict[str, str]) -> tuple[dict[str, str], dict[str, Any]]:
    algorithm_dir = REPO / "benchmark_01_legacy" / "master_algorithms"
    sys.path.insert(0, str(algorithm_dir))
    import algorithm_5_commercial_name_search as algorithm_5  # type: ignore

    started = time.perf_counter()
    failures: list[str] = []
    observed: dict[str, Any] = {}
    if row["rule_id"] == "OCR-NONTRANSITIVE-SPANS":
        variants = {
            value
            for value, _, _ in algorithm_5.grapheme_confusion_variants(
                row["query"], max_confusions=2
            )
        }
        observed["variant_count"] = len(variants)
        observed["contains_GARDX"] = "GARDX" in variants
        if "GARDX" in variants:
            failures.append("transitive_variant_generated:GARDX")
    elif row["rule_id"] == "OCR-MAX-INPUT-LENGTH":
        variants = algorithm_5.grapheme_confusion_variants(
            row["query"], max_confusions=2
        )
        observed["variant_count"] = len(variants)
        if variants:
            failures.append(f"long_input_variants:{len(variants)}")
    else:
        failures.append("unknown_source_contract")
    elapsed_ms = (time.perf_counter() - started) * 1000
    if row["rule_id"] == "OCR-MAX-INPUT-LENGTH" and elapsed_ms >= 100:
        failures.append(f"source_latency_ms:{elapsed_ms:.3f}>=100")
    result = {
        "case_id": row["case_id"],
        "suite": "ocr_grapheme_source",
        "rule_id": row["rule_id"],
        "case_type": row["case_type"],
        "split": row["split"],
        "query": row["query"],
        "product_context": "",
        "passed": "1" if not failures else "0",
        "failure_count": str(len(failures)),
        "failures": "|".join(failures),
        "expected_families": row.get("expected_families") or "",
        "observed_families": "",
        "decision_type": "source_function",
        "status": "passed" if not failures else "failed",
        "candidate_count": str(observed.get("variant_count", "")),
        "elapsed_ms": f"{elapsed_ms:.3f}",
    }
    return result, {"case_id": row["case_id"], "source_contract": observed, "elapsed_ms": elapsed_ms}


def write_csv(path: Path, rows: Sequence[dict[str, str]]) -> None:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def ordinary_ranking_metrics(rows: Sequence[dict[str, str]]) -> dict[str, Any]:
    if not rows:
        return {
            "cases": 0,
            "hit1": 0,
            "hit5": 0,
            "hit20": 0,
            "hit1_rate": 0.0,
            "hit5_rate": 0.0,
            "hit20_rate": 0.0,
            "mrr": 0.0,
            "macro_relevant_recall20": 0.0,
        }
    hit1 = sum(row.get("hit1") == "1" for row in rows)
    hit5 = sum(row.get("hit5") == "1" for row in rows)
    hit20 = sum(row.get("hit20") == "1" for row in rows)
    count = len(rows)
    return {
        "cases": count,
        "hit1": hit1,
        "hit5": hit5,
        "hit20": hit20,
        "hit1_rate": hit1 / count,
        "hit5_rate": hit5 / count,
        "hit20_rate": hit20 / count,
        "mrr": statistics.fmean(float(row.get("reciprocal_rank") or 0.0) for row in rows),
        "macro_relevant_recall20": statistics.fmean(
            float(row.get("relevant_recall_20") or 0.0) for row in rows
        ),
    }


def summary_for(rows: Sequence[dict[str, str]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["suite"]].append(row)
    suites = {}
    for suite, members in sorted(grouped.items()):
        latencies = [float(row["elapsed_ms"]) for row in members]
        suites[suite] = {
            "cases": len(members),
            "passed": sum(row["passed"] == "1" for row in members),
            "failed": sum(row["passed"] != "1" for row in members),
            "p50_ms": percentile(latencies, 0.50),
            "p95_ms": percentile(latencies, 0.95),
            "p99_ms": percentile(latencies, 0.99),
            "by_split": dict(Counter(row["split"] for row in members)),
            "by_rule": dict(Counter(row["rule_id"] for row in members)),
        }
        if suite == "product_context_200":
            suites[suite]["baseline_hit1"] = sum(row.get("baseline_hit") == "1" for row in members)
            suites[suite]["context_hit1"] = sum(row["passed"] == "1" for row in members)
        if suite in {"ordinary_typo_benchmark", "ordinary_typo_collision_safety"}:
            suites[suite]["ranking"] = ordinary_ranking_metrics(members)
            primary_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
            length_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in members:
                primary_groups[row.get("primary_mutation") or "unclassified"].append(row)
                length_groups[row.get("query_length_bucket") or "unclassified"].append(row)
            suites[suite]["by_primary_mutation"] = {
                stratum: ordinary_ranking_metrics(stratum_rows)
                for stratum, stratum_rows in sorted(primary_groups.items())
            }
            suites[suite]["by_query_length"] = {
                bucket: ordinary_ranking_metrics(bucket_rows)
                for bucket, bucket_rows in sorted(length_groups.items())
            }
            suites[suite]["gating_cases"] = sum(row.get("gating") == "1" for row in members)
            suites[suite]["metric_only_cases"] = sum(row.get("gating") != "1" for row in members)
            suites[suite]["complete_relevance_set_at20"] = sum(
                abs(float(row.get("relevant_recall_20") or 0.0) - 1.0) <= 1e-12
                for row in members
            )
    return suites


def update_failure_log(failures: Sequence[dict[str, str]], run_id: str) -> None:
    path = RESULTS / "failure_analysis.md"
    lines = [
        "# Failure analysis log",
        "",
        f"Run `{run_id}` produced {len(failures)} failed rows. Failures are preserved below; no row was deleted or relabeled.",
        "",
    ]
    if not failures:
        lines.extend(["No gating or execution failures were observed in this evaluation.", ""])
    else:
        lines.extend([
            "| Case | Suite | Rule | Split | Query | Failure |",
            "| --- | --- | --- | --- | --- | --- |",
        ])
        for row in failures:
            safe_query = row["query"].replace("|", "\\|")
            safe_failure = row["failures"].replace("|", "; ")
            lines.append(
                f"| `{row['case_id']}` | {row['suite']} | `{row['rule_id']}` | {row['split']} | `{safe_query}` | {safe_failure} |"
            )
        lines.extend([
            "",
            "Each row still requires a root-cause classification and, if a source fix is justified, a focused and paired-regression rerun record.",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8013")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--skip-product", action="store_true")
    parser.add_argument("--skip-ordinary-typos", action="store_true")
    parser.add_argument(
        "--only-ordinary-typos",
        action="store_true",
        help="run only the ordinary-typo benchmark and collision/safety rows",
    )
    args = parser.parse_args()
    if args.only_ordinary_typos and args.skip_ordinary_typos:
        parser.error("--only-ordinary-typos conflicts with --skip-ordinary-typos")

    run_provenance = collect_provenance(REPO)
    RESULTS.mkdir(parents=True, exist_ok=True)
    generation = verify_generation_manifest()
    base = args.base_url.rstrip("/")
    runtime = get_json(base + "/api/runtime", args.timeout)
    health = get_json(base + "/health", args.timeout)
    if runtime.get("algorithm") != "algorithm_6" or not runtime.get("ready"):
        raise SystemExit("endpoint is not a ready Algorithm 6 runtime")
    if health != {"status": "ok", "algorithm": "algorithm_6"}:
        raise SystemExit(f"unexpected health response: {health}")

    started = datetime.now(timezone.utc)
    results: list[dict[str, str]] = []
    raw: list[dict[str, Any]] = []
    if not args.only_ordinary_typos:
        retrieval_rows: list[dict[str, str]] = []
        for filename in (
            "visual_gap_adversarial.csv",
            "visual_gap_protocol.csv",
            "visual_gap_catalog_generated.csv",
            "visual_gap_catalog_collisions.csv",
            "ocr_grapheme_adversarial.csv",
            "ocr_grapheme_catalog_generated.csv",
        ):
            retrieval_rows.extend(read_csv(GENERATED / filename))

        source_rows = [
            row for row in retrieval_rows if row.get("expected_decision") == "source_function"
        ]
        retrieval_rows = [
            row for row in retrieval_rows if row.get("expected_decision") != "source_function"
        ]

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            evaluated = list(pool.map(
                lambda row: evaluate_retrieval_case(
                    row, search_url=base + "/api/search", timeout=args.timeout
                ),
                retrieval_rows,
            ))
        results.extend(item[0] for item in evaluated)
        raw.extend(item[1] for item in evaluated)
        source_evaluated = [evaluate_source_contract(row) for row in source_rows]
        results.extend(item[0] for item in source_evaluated)
        raw.extend(item[1] for item in source_evaluated)

    if not args.skip_ordinary_typos:
        ordinary_rows: list[dict[str, str]] = []
        for filename in (
            "ordinary_typo_catalog_benchmark.csv",
            "ordinary_typo_collision_safety.csv",
        ):
            ordinary_rows.extend(read_csv(GENERATED / filename))
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            ordinary_evaluated = list(pool.map(
                lambda row: evaluate_ordinary_typo_case(
                    row,
                    search_url=base + "/api/search",
                    timeout=args.timeout,
                ),
                ordinary_rows,
            ))
        results.extend(item[0] for item in ordinary_evaluated)
        raw.extend(item[1] for item in ordinary_evaluated)

    if not args.skip_product and not args.only_ordinary_typos:
        product_rows = read_csv(GENERATED / "product_context_200.csv")
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            product_evaluated = list(pool.map(
                lambda row: evaluate_product_case(row, search_url=base + "/api/search", timeout=args.timeout),
                product_rows,
            ))
        results.extend(item[0] for item in product_evaluated)
        raw.extend(item[1] for item in product_evaluated)

    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    run_directory = RESULTS / "runs" / run_id
    run_directory.mkdir(parents=True, exist_ok=True)
    result_path = run_directory / "case_results.csv"
    failure_path = run_directory / "failures.csv"
    raw_path = run_directory / "raw_responses.jsonl"
    summary_path = run_directory / "summary.json"
    write_csv(result_path, results)
    failures = [row for row in results if row["passed"] != "1"]
    write_csv(failure_path, failures or [{"case_id": "", "passed": "1", "failures": ""}])
    with raw_path.open("w", encoding="utf-8") as handle:
        for item in raw:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")

    summary = {
        "run_id": run_id,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": base,
        "runtime": runtime,
        "health": health,
        "source_provenance": run_provenance,
        "generation_manifest_sha256": sha256_path(MANIFEST),
        "source_commit_expected": generation["source_commit_expected"],
        "catalog_sha256": generation["catalog"]["sha256"],
        "total_cases": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "metric_only_cases": sum(row.get("gating") == "0" for row in results),
        "gating_cases": sum(row.get("gating") != "0" for row in results),
        "suites": summary_for(results),
        "artifacts": {},
    }
    for path in (result_path, failure_path, raw_path):
        summary["artifacts"][path.name] = {
            "sha256": sha256_path(path),
            "bytes": path.stat().st_size,
        }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for source_path in (result_path, failure_path, raw_path, summary_path):
        shutil.copy2(source_path, RESULTS / source_path.name)
    update_failure_log(failures, run_id)
    print(json.dumps(summary, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

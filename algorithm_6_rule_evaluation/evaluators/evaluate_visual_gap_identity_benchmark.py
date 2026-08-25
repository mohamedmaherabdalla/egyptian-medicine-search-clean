#!/usr/bin/env python3
"""Evaluate the exact-identity visual-gap benchmark against the public API.

The evaluator intentionally ignores ``variant_group``.  Visual results are
identified only by ``matched_family_key``, the exact catalog base family that
satisfied the positional evidence.  Full exact-oracle recall, source recovery,
safety guards, non-exact candidate indicators, and latency are retained per
case so a headline pass count cannot hide the nature of a failure.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import statistics
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().parents[1]
DATASET = PACKAGE / "test_sets" / "generated" / "visual_gap_identity_benchmark.csv"
MANIFEST = (
    PACKAGE / "test_sets" / "manifests" / "visual_gap_identity_benchmark.manifest.json"
)
RESULTS = PACKAGE / "results" / "visual_gap_identity"
GENERATOR = (
    PACKAGE / "generators" / "generate_visual_gap_identity_benchmark.py"
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compact(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def split_set(value: object) -> set[str]:
    return {compact(item) for item in str(value or "").split(";") if compact(item)}


def result_reasons(item: dict[str, Any]) -> set[str]:
    value = item.get("reasons") or []
    if isinstance(value, str):
        return {part for part in value.split("|") if part}
    return {str(part) for part in value}


def get_json(url: str, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def post_json(
    url: str,
    payload: dict[str, Any],
    timeout: float,
) -> tuple[dict[str, Any], float]:
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


def current_source_provenance() -> dict[str, Any]:
    if str(PACKAGE) not in sys.path:
        sys.path.insert(0, str(PACKAGE))
    from provenance import DEFAULT_FILE_PATHS, collect_provenance

    paths = dict(DEFAULT_FILE_PATHS)
    paths["generator"] = GENERATOR.relative_to(REPO)
    paths["evaluator"] = Path(__file__).relative_to(REPO)
    return collect_provenance(REPO, file_paths=paths)


def load_and_verify() -> tuple[dict[str, Any], list[dict[str, str]]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("dataset_id") != "visual_gap_exact_identity_v1":
        raise RuntimeError("unexpected visual-gap dataset identity")
    if sha256_path(DATASET) != manifest.get("dataset_sha256"):
        raise RuntimeError("visual-gap dataset hash does not match its manifest")

    with DATASET.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != int(manifest.get("rows") or -1):
        raise RuntimeError("visual-gap dataset row count does not match its manifest")

    # Git status can legitimately change when generated artifacts are added.
    # The executable/data file digests may not: verify each recorded source
    # directly, including this evaluator and its generator.
    provenance = manifest.get("source_provenance") or {}
    for name, record in (provenance.get("files") or {}).items():
        path = REPO / str(record.get("path") or "")
        expected = str(record.get("sha256") or "")
        if not path.is_file() or sha256_path(path) != expected:
            raise RuntimeError(f"manifest source hash mismatch: {name}:{path}")
    return manifest, rows


def visual_identity(item: dict[str, Any]) -> str:
    if item.get("source") != "algorithm_6_visual_gap":
        return ""
    return compact(item.get("matched_family_key"))


def evaluate_case(
    row: dict[str, str],
    *,
    search_url: str,
    timeout: float,
    response_override: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    request_limit = int(row.get("request_limit") or 20)
    if response_override is None:
        response, elapsed_ms = post_json(
            search_url,
            {"query": row["query"], "product_context": "", "limit": request_limit},
            timeout,
        )
    else:
        response = response_override
        # Preloaded responses are produced by direct curl calls when the local
        # execution sandbox permits curl but denies Python sockets.  Preserve
        # the API's own measured search time as the comparable latency field.
        elapsed_ms = float(response.get("server_elapsed_ms") or 0.0)
    failures: list[str] = []
    if response.get("algorithm") != "algorithm_6":
        failures.append("wrong_algorithm_identity")

    decision = str(response.get("decision_type") or "")
    expected_decision = row.get("expected_decision") or ""
    expects_visual = expected_decision == "visual_gap_matches"
    if expected_decision == "not_visual_gap":
        if decision == "visual_gap_matches":
            failures.append("unexpected_visual_gap_dispatch")
    elif decision != expected_decision:
        failures.append(f"decision:{decision}!={expected_decision}")

    expected_mode = row.get("expected_mode") or ""
    observed_mode = str((response.get("visual_gap") or {}).get("mode") or "")
    if expected_mode and observed_mode != expected_mode:
        failures.append(f"visual_mode:{observed_mode}!={expected_mode}")

    returned = list(response.get("results") or [])
    visual_rows = [item for item in returned if item.get("source") == "algorithm_6_visual_gap"]
    observed_keys: list[str] = []
    for index, item in enumerate(visual_rows, 1):
        key = visual_identity(item)
        if not key:
            failures.append(f"visual_row_{index}_missing_matched_family_key")
        else:
            observed_keys.append(key)
    observed_set = set(observed_keys)
    duplicate_keys = sorted(key for key, count in Counter(observed_keys).items() if count > 1)
    if duplicate_keys:
        failures.append("duplicate_exact_identities:" + ",".join(duplicate_keys))

    if expects_visual:
        if response.get("confirmation_required") is not True:
            failures.append("response_confirmation_required_false")
        for index, item in enumerate(returned, 1):
            if item.get("confirmation_required") is not True:
                failures.append(f"row_{index}_confirmation_required_false")
            if item.get("needs_clarification") is not True:
                failures.append(f"row_{index}_needs_clarification_false")
        non_visual_sources = [
            str(item.get("source") or "")
            for item in returned
            if item.get("source") != "algorithm_6_visual_gap"
        ]
        if non_visual_sources:
            failures.append("non_visual_rows_in_visual_response")

    relevant = split_set(row.get("relevant_exact_family_keys"))
    forbidden = split_set(row.get("forbidden_exact_family_keys"))
    source = compact(row.get("source_exact_family_key"))
    missing_relevant = sorted(relevant - observed_set)
    forbidden_returned = sorted(forbidden & observed_set)

    policy = row.get("match_policy") or ""
    if "all_relevant" in policy and missing_relevant:
        failures.append("missing_exact_relevant:" + ",".join(missing_relevant))
    if policy.startswith("source_and") and source and source not in observed_set:
        failures.append(f"source_exact_identity_missing:{source}")
    if forbidden_returned:
        failures.append("forbidden_exact_identity_returned:" + ",".join(forbidden_returned))

    source_row = next(
        (item for item in visual_rows if visual_identity(item) == source),
        None,
    )
    required_reason = row.get("required_reason_on_source") or ""
    if required_reason:
        if source_row is None:
            failures.append(f"required_reason_target_missing:{source}")
        elif required_reason not in result_reasons(source_row):
            failures.append(f"required_reason_missing_on_source:{required_reason}")

    forbidden_reason = row.get("forbidden_reason_any_result") or ""
    if forbidden_reason and any(
        forbidden_reason in result_reasons(item) for item in visual_rows
    ):
        failures.append(f"forbidden_reason_present:{forbidden_reason}")

    found_relevant = relevant & observed_set
    unexpected = observed_set - relevant
    exact_recall = len(found_relevant) / len(relevant) if relevant else 1.0
    exact_indicator_precision = (
        len(found_relevant) / len(observed_set) if observed_set else (1.0 if not relevant else 0.0)
    )
    source_required = policy.startswith("source_and")
    source_rank = observed_keys.index(source) + 1 if source in observed_keys else 0
    result = dict(row)
    result.update({
        "passed": not failures,
        "failures": failures,
        "observed_decision": decision,
        "observed_mode": observed_mode,
        "observed_status": str(response.get("status") or ""),
        # Keep public API order for reproducible source Hit@k/MRR metrics.
        # The set-valued fields below remain sorted for stable diagnostics.
        "observed_visual_exact_family_keys": observed_keys,
        "missing_relevant_exact_family_keys": missing_relevant,
        "unexpected_nonexact_or_fuzzy_family_keys": sorted(unexpected),
        "forbidden_returned_exact_family_keys": forbidden_returned,
        "source_required": source_required,
        "source_hit": bool(source and source in observed_set),
        "source_rank": source_rank,
        "relevant_count": len(relevant),
        "relevant_found": len(found_relevant),
        "exact_relevance_recall": exact_recall,
        "exact_oracle_precision_indicator": exact_indicator_precision,
        "visual_result_count": len(visual_rows),
        "api_candidate_count": int(response.get("candidate_count") or 0),
        "elapsed_ms": elapsed_ms,
        "server_elapsed_ms": float(response.get("server_elapsed_ms") or 0.0),
    })
    raw = {
        "case_id": row["case_id"],
        "request": {"query": row["query"], "product_context": "", "limit": request_limit},
        "elapsed_ms": elapsed_ms,
        "response": response,
    }
    return result, raw


def summarize_group(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    relevant_total = sum(int(row["relevant_count"]) for row in rows)
    relevant_found = sum(int(row["relevant_found"]) for row in rows)
    observed_total = sum(int(row["visual_result_count"]) for row in rows)
    source_rows = [row for row in rows if row["source_required"]]
    source_ranks = [int(row["source_rank"]) for row in source_rows]
    latencies = [float(row["elapsed_ms"]) for row in rows]
    return {
        "cases": len(rows),
        "passed": sum(bool(row["passed"]) for row in rows),
        "failed": sum(not bool(row["passed"]) for row in rows),
        "contract_pass_rate": (
            sum(bool(row["passed"]) for row in rows) / len(rows) if rows else 0.0
        ),
        "source_recovery": {
            "required_cases": len(source_rows),
            "hits": sum(bool(row["source_hit"]) for row in source_rows),
            "rate": (
                sum(bool(row["source_hit"]) for row in source_rows) / len(source_rows)
                if source_rows
                else None
            ),
            "hit1": sum(rank == 1 for rank in source_ranks),
            "hit5": sum(0 < rank <= 5 for rank in source_ranks),
            "hit20": sum(0 < rank <= 20 for rank in source_ranks),
            "mrr_at20": (
                statistics.mean(1.0 / rank if rank else 0.0 for rank in source_ranks)
                if source_ranks
                else None
            ),
        },
        "exact_relevance_micro_recall": (
            relevant_found / relevant_total if relevant_total else None
        ),
        "exact_oracle_micro_precision_indicator": (
            relevant_found / observed_total if observed_total else None
        ),
        "exact_relevant_labels": relevant_total,
        "exact_relevant_labels_found": relevant_found,
        "visual_results": observed_total,
        "unexpected_nonexact_or_fuzzy_identities": sum(
            len(row["unexpected_nonexact_or_fuzzy_family_keys"]) for row in rows
        ),
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "mean": statistics.mean(latencies) if latencies else 0.0,
        },
    }


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8014")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument(
        "--responses-dir",
        type=Path,
        help=(
            "directory containing runtime.json and one <case_id>.json API response per row; "
            "supports restricted environments where only direct curl has local-network access"
        ),
    )
    args = parser.parse_args()

    manifest, rows = load_and_verify()
    base_url = args.base_url.rstrip("/")
    responses_dir = args.responses_dir.resolve() if args.responses_dir else None
    runtime = (
        json.loads((responses_dir / "runtime.json").read_text(encoding="utf-8"))
        if responses_dir
        else get_json(base_url + "/api/runtime", args.timeout)
    )
    if (
        runtime.get("ready") is not True
        or runtime.get("algorithm") != "algorithm_6"
        or int(runtime.get("family_count") or 0) != 17_476
    ):
        raise RuntimeError(f"endpoint runtime identity mismatch: {runtime}")

    evaluated: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    search_url = base_url + "/api/search"
    for index, row in enumerate(rows, 1):
        response_override = None
        if responses_dir:
            response_path = responses_dir / f"{row['case_id']}.json"
            if not response_path.is_file():
                raise RuntimeError(f"missing preloaded API response: {response_path}")
            response_override = json.loads(response_path.read_text(encoding="utf-8"))
        result, raw = evaluate_case(
            row,
            search_url=search_url,
            timeout=args.timeout,
            response_override=response_override,
        )
        evaluated.append(result)
        raw_rows.append(raw)
        if index % 50 == 0 or index == len(rows):
            print(f"evaluated {index}/{len(rows)}", file=sys.stderr, flush=True)

    RESULTS.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RESULTS / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    per_case_path = run_dir / "per_case.jsonl"
    raw_path = run_dir / "raw_responses.jsonl"
    failures_path = run_dir / "failures.csv"
    write_jsonl(per_case_path, evaluated)
    write_jsonl(raw_path, raw_rows)

    failure_columns = [
        "case_id",
        "evaluation_kind",
        "case_type",
        "stratum",
        "split",
        "query",
        "source_exact_family_key",
        "relevant_exact_family_keys",
        "forbidden_exact_family_keys",
        "observed_decision",
        "observed_mode",
        "observed_visual_exact_family_keys",
        "failures",
    ]
    with failures_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=failure_columns, extrasaction="ignore")
        writer.writeheader()
        for result in evaluated:
            if result["passed"]:
                continue
            output = dict(result)
            for field in (
                "observed_visual_exact_family_keys",
                "failures",
            ):
                output[field] = ";".join(map(str, output[field]))
            writer.writerow(output)

    grouped_stratum: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evaluated:
        grouped_stratum[row["stratum"]].append(row)
        grouped_split[row["split"]].append(row)
        grouped_kind[row["evaluation_kind"]].append(row)

    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": base_url,
        "transport": "preloaded_direct_curl" if responses_dir else "python_urllib",
        "runtime": runtime,
        "evaluation_source_provenance": current_source_provenance(),
        "dataset": {
            "dataset_id": manifest["dataset_id"],
            "dataset_file": manifest["dataset_file"],
            "dataset_sha256": manifest["dataset_sha256"],
            "rows": manifest["rows"],
            "generator_seed": manifest["generator_seed"],
            "source_provenance": manifest["source_provenance"],
        },
        "metric_interpretation": {
            "contract_pass_rate": "gating API identity, dispatch, safety, reason-scope, and exact-recall checks",
            "source_recovery": "cases whose generated source exact family must be returned",
            "source_recovery.hit1/hit5/hit20": (
                "rank of the preselected source exact family in public visual-result order; "
                "retrospective catalog challenge, not blind external accuracy"
            ),
            "exact_relevance_micro_recall": "retrieved exact oracle identities / all exact oracle identities",
            "exact_oracle_micro_precision_indicator": (
                "retrieved exact oracle identities / all visual identities returned; diagnostic only, "
                "because bounded fuzzy candidates can be valid outside the exact oracle"
            ),
        },
        "overall": summarize_group(evaluated),
        "by_stratum": {
            name: summarize_group(members) for name, members in sorted(grouped_stratum.items())
        },
        "by_split": {
            name: summarize_group(members) for name, members in sorted(grouped_split.items())
        },
        "by_evaluation_kind": {
            name: summarize_group(members) for name, members in sorted(grouped_kind.items())
        },
        "failure_reasons": dict(sorted(Counter(
            failure for row in evaluated for failure in row["failures"]
        ).items())),
        "failed_case_ids": [row["case_id"] for row in evaluated if not row["passed"]],
        "artifacts": {
            "per_case": str(per_case_path.relative_to(REPO)),
            "per_case_sha256": sha256_path(per_case_path),
            "raw_responses": str(raw_path.relative_to(REPO)),
            "raw_responses_sha256": sha256_path(raw_path),
            "failures": str(failures_path.relative_to(REPO)),
            "failures_sha256": sha256_path(failures_path),
        },
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "latest_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if not summary["overall"]["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

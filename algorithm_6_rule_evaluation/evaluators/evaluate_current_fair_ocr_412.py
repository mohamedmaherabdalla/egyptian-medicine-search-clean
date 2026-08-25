#!/usr/bin/env python3
"""Evaluate the current public Algorithm 6 API on the locked fair-OCR set.

This is a retrospective accuracy/non-regression evaluation.  The cases have
already been used during development, so neither the development split nor the
historical holdout split is a blind external-generalization test.

The identity contract is deliberately source-aware and strict:

* ``algorithm_6_visual_gap`` results are scored only from
  ``matched_family_key`` or ``matched_family_name``;
* every other result is scored only from the public API ``base_group_key``.

There is no fallback to variant groups, candidate names, or commercial display
names.  Every response is retained case-by-case with its top 20 identities,
decision fields, and confirmation fields.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from algorithm_6_rule_evaluation.provenance import (  # noqa: E402
    DEFAULT_FILE_PATHS,
    collect_provenance,
    sha256_path,
)


EVALUATOR_RELATIVE_PATH = Path(
    "algorithm_6_rule_evaluation/evaluators/evaluate_current_fair_ocr_412.py"
)
DEFAULT_DATASET = Path(
    "algorithm_6_rule_evaluation/test_sets/locked/fair_ocr_412.csv"
)
DEFAULT_RESULTS_ROOT = Path(
    "algorithm_6_rule_evaluation/results/fair_ocr_412_current"
)

LOCKED_DATASET_SHA256 = (
    "3ad1a423cadc96b29665a8c600c27eb25bc743a5274f4a2c7917402fe09979bd"
)
LOCKED_DATASET_BYTES = 161_231
LOCKED_TOTAL_ROWS = 412
LOCKED_ACCEPTED_SCORED_ROWS = 412
LOCKED_SPLITS = {"development": 324, "holdout": 88}
LOCKED_MULTI_EXPECTED_CASES = 42

# These hashes freeze the current runtime source under evaluation.  The
# evaluator and generator are recorded by provenance too, but only executable
# runtime/data inputs are fixed here.
EXPECTED_CURRENT_RUNTIME_SHA256 = {
    "algorithm_5": "c5faefb2bfb54c4dfbe4a059b120aaa4121db3c2bdf0606ab0cdef4f56bbbee7",
    "algorithm_6": "cedf1fce3dac214f5533707c031051efec7343aa8d4342e9ddf7cfe31940fbcb",
    "product_reranker": "03780539f9449323a641ab6ad9d2f505f0ed167e6741c63c858bc0b7d873caea",
    "api": "752399eec3caf486d1242d61d9176625cd0e42605e6553487e466bd56b8bc6de",
    "catalog": "d234edaa2669d1eeb46b962e7e3e02df52c6f4d2fd3eca7a2fbf3bc7d159fd9c",
}
EXPECTED_RUNTIME_COUNTS = {"medicine_count": 25_066, "family_count": 17_476}
REQUIRED_DATASET_COLUMNS = {
    "case_id",
    "split",
    "model_name",
    "input",
    "expected_family_key",
    "expected_family_name",
    "difficulty",
    "mistake_type",
    "danger",
    "analysis_cohort",
    "distance_band",
    "accepted",
    "scored_case",
}
VISUAL_SOURCE = "algorithm_6_visual_gap"
IDENTITY_NORMALIZATION = "uppercase ASCII alphanumeric compaction"


class EvaluationContractError(RuntimeError):
    """Raised when the locked input or runtime violates the evaluation contract."""


def compact(value: object) -> str:
    """Canonicalize API family keys exactly as the locked oracle does."""

    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_locked_cases(path: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    payload = path.read_bytes()
    digest = sha256_bytes(payload)
    if digest != LOCKED_DATASET_SHA256:
        raise EvaluationContractError(
            "locked dataset SHA-256 mismatch: "
            f"expected {LOCKED_DATASET_SHA256}, got {digest}"
        )
    if len(payload) != LOCKED_DATASET_BYTES:
        raise EvaluationContractError(
            f"locked dataset byte count mismatch: expected {LOCKED_DATASET_BYTES}, "
            f"got {len(payload)}"
        )

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing_columns = sorted(REQUIRED_DATASET_COLUMNS - columns)
        if missing_columns:
            raise EvaluationContractError(
                "locked dataset is missing required columns: "
                + ", ".join(missing_columns)
            )
        all_rows = list(reader)

    if len(all_rows) != LOCKED_TOTAL_ROWS:
        raise EvaluationContractError(
            f"locked row count mismatch: expected {LOCKED_TOTAL_ROWS}, got {len(all_rows)}"
        )
    cases = [
        row
        for row in all_rows
        if row.get("accepted") == "1" and row.get("scored_case") == "1"
    ]
    if len(cases) != LOCKED_ACCEPTED_SCORED_ROWS:
        raise EvaluationContractError(
            "accepted/scored row count mismatch: expected "
            f"{LOCKED_ACCEPTED_SCORED_ROWS}, got {len(cases)}"
        )

    case_ids = [row["case_id"] for row in cases]
    if len(case_ids) != len(set(case_ids)):
        duplicates = sorted(
            case_id for case_id, count in Counter(case_ids).items() if count > 1
        )
        raise EvaluationContractError(
            "duplicate accepted/scored case IDs: " + ", ".join(duplicates[:10])
        )

    splits = dict(sorted(Counter(row["split"] for row in cases).items()))
    if splits != LOCKED_SPLITS:
        raise EvaluationContractError(
            f"locked split counts mismatch: expected {LOCKED_SPLITS}, got {splits}"
        )

    multi_expected = 0
    for row in cases:
        raw_targets = [value.strip() for value in row["expected_family_key"].split(";")]
        targets = [compact(value) for value in raw_targets if value]
        if not targets or any(not target for target in targets):
            raise EvaluationContractError(
                f"case {row['case_id']} has no valid expected family identity"
            )
        if len(targets) != len(set(targets)):
            raise EvaluationContractError(
                f"case {row['case_id']} contains duplicate expected identities"
            )
        if len(targets) > 1:
            multi_expected += 1
        row["_expected_keys_json"] = json.dumps(targets)

    if multi_expected != LOCKED_MULTI_EXPECTED_CASES:
        raise EvaluationContractError(
            "multi-expected count mismatch: expected "
            f"{LOCKED_MULTI_EXPECTED_CASES}, got {multi_expected}"
        )

    validation = {
        "sha256": digest,
        "bytes": len(payload),
        "rows": len(all_rows),
        "accepted_scored_cases": len(cases),
        "splits": splits,
        "unique_case_ids": len(set(case_ids)),
        "multi_expected_cases": multi_expected,
        "required_columns_present": True,
        "all_fixed_contract_checks_passed": True,
    }
    return cases, validation


def get_json(url: str, *, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise EvaluationContractError(f"GET {url} did not return a JSON object")
    return payload


def post_search(
    base_url: str,
    query: str,
    *,
    timeout: float,
    retries: int,
) -> tuple[dict[str, Any], float, int]:
    url = base_url.rstrip("/") + "/api/search"
    body = json.dumps(
        {"query": query, "product_context": "", "limit": 20},
        ensure_ascii=False,
    ).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if not isinstance(payload, dict):
                raise EvaluationContractError(
                    f"search for {query!r} did not return a JSON object"
                )
            return payload, elapsed_ms, attempt
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as error:
            last_error = error
            if attempt < retries:
                time.sleep(0.25 * (attempt + 1))
    raise EvaluationContractError(
        f"search request failed for {query!r} after {retries + 1} attempt(s): "
        f"{last_error}"
    )


def result_identity(item: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return (canonical identity, legal source field, raw field value)."""

    if item.get("source") == VISUAL_SOURCE:
        raw_key = str(item.get("matched_family_key") or "").strip()
        if raw_key:
            return compact(raw_key), "matched_family_key", raw_key
        raw_name = str(item.get("matched_family_name") or "").strip()
        return compact(raw_name), "matched_family_name", raw_name

    raw_base = str(item.get("base_group_key") or "").strip()
    return compact(raw_base), "base_group_key", raw_base


def slim_result(item: Mapping[str, Any], position: int) -> dict[str, Any]:
    identity, identity_field, identity_raw = result_identity(item)
    return {
        "position": position,
        "api_rank": item.get("rank"),
        "candidate_id": item.get("candidate_id"),
        "source": item.get("source"),
        "identity_contract_field": identity_field,
        "identity_raw": identity_raw,
        "identity_key": identity,
        "name": item.get("name"),
        "commercial_name": item.get("commercial_name"),
        "base_group_key": item.get("base_group_key"),
        "matched_family_key": item.get("matched_family_key"),
        "matched_family_name": item.get("matched_family_name"),
        "variant_group": item.get("variant_group"),
        "score": item.get("score"),
        "confidence": item.get("confidence"),
        "needs_clarification": item.get("needs_clarification"),
        "confirmation_required": item.get("confirmation_required"),
        "matched_signals": item.get("matched_signals"),
        "reasons": item.get("reasons"),
    }


def evaluate_case(
    base_url: str,
    row: Mapping[str, str],
    *,
    timeout: float,
    retries: int,
) -> dict[str, Any]:
    payload, client_elapsed_ms, retry_count = post_search(
        base_url,
        row["input"],
        timeout=timeout,
        retries=retries,
    )
    if payload.get("algorithm") != "algorithm_6":
        raise EvaluationContractError(
            f"case {row['case_id']} response algorithm is not algorithm_6"
        )
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise EvaluationContractError(
            f"case {row['case_id']} response results is not a list"
        )
    if len(raw_results) > 20:
        raise EvaluationContractError(
            f"case {row['case_id']} returned {len(raw_results)} results, limit was 20"
        )

    top20 = [slim_result(item, index) for index, item in enumerate(raw_results, 1)]
    expected_keys = set(json.loads(row["_expected_keys_json"]))
    matching = [item for item in top20 if item["identity_key"] in expected_keys]
    rank = matching[0]["position"] if matching else None
    matched_item = matching[0] if matching else None

    missing_identity_positions = [
        item["position"] for item in top20 if not item["identity_key"]
    ]
    api_rank_mismatches = [
        {
            "position": item["position"],
            "api_rank": item["api_rank"],
        }
        for item in top20
        if item["api_rank"] != item["position"]
    ]

    return {
        "case_id": row["case_id"],
        "split": row["split"],
        "model_name": row["model_name"],
        "input": row["input"],
        "expected_family_keys": sorted(expected_keys),
        "expected_family_name": row["expected_family_name"],
        "difficulty": row["difficulty"],
        "mistake_type": row["mistake_type"],
        "danger": row["danger"],
        "analysis_cohort": row["analysis_cohort"],
        "distance_band": row["distance_band"],
        "rank": rank,
        "hit1": rank == 1,
        "hit5": rank is not None and rank <= 5,
        "hit20": rank is not None and rank <= 20,
        "reciprocal_rank20": (1.0 / rank) if rank is not None and rank <= 20 else 0.0,
        "matched_candidate_id": matched_item.get("candidate_id") if matched_item else None,
        "matched_identity_field": (
            matched_item.get("identity_contract_field") if matched_item else None
        ),
        "matched_identity_raw": matched_item.get("identity_raw") if matched_item else None,
        "decision": {
            "status": payload.get("status"),
            "decision_type": payload.get("decision_type"),
            "message": payload.get("message"),
            "normalized_query": payload.get("normalized_query"),
            "candidate_count": payload.get("candidate_count"),
            "child_candidate_count": payload.get("child_candidate_count"),
            "unreadable_mode": payload.get("unreadable_mode"),
            "unreadable_continuation": payload.get("unreadable_continuation"),
            "ending_fragment": payload.get("ending_fragment"),
        },
        "confirmation": {
            "response_confirmation_required": payload.get("confirmation_required"),
            "result_count": len(top20),
            "results_confirmation_true": sum(
                item["confirmation_required"] is True for item in top20
            ),
            "results_needs_clarification_true": sum(
                item["needs_clarification"] is True for item in top20
            ),
            "all_returned_results_require_confirmation": bool(top20)
            and all(item["confirmation_required"] is True for item in top20),
            "all_returned_results_need_clarification": bool(top20)
            and all(item["needs_clarification"] is True for item in top20),
        },
        "response_contract": {
            "algorithm": payload.get("algorithm"),
            "evaluation_version": payload.get("evaluation_version"),
            "result_count": len(top20),
            "visual_result_count": sum(item["source"] == VISUAL_SOURCE for item in top20),
            "missing_legal_identity_positions": missing_identity_positions,
            "api_rank_mismatches": api_rank_mismatches,
            "retry_count": retry_count,
        },
        "timing": {
            "client_elapsed_ms": client_elapsed_ms,
            "server_elapsed_ms": payload.get("server_elapsed_ms"),
        },
        "top20": top20,
    }


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def metric_block(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    cases = list(records)
    count = len(cases)
    ranks = [record.get("rank") for record in cases]
    return {
        "cases": count,
        "hit1": sum(rank == 1 for rank in ranks),
        "hit1_rate": sum(rank == 1 for rank in ranks) / count if count else 0.0,
        "hit5": sum(rank is not None and rank <= 5 for rank in ranks),
        "hit5_rate": (
            sum(rank is not None and rank <= 5 for rank in ranks) / count
            if count
            else 0.0
        ),
        "hit20": sum(rank is not None and rank <= 20 for rank in ranks),
        "hit20_rate": (
            sum(rank is not None and rank <= 20 for rank in ranks) / count
            if count
            else 0.0
        ),
        "miss20": sum(rank is None or rank > 20 for rank in ranks),
        "mrr20": (
            sum(float(record["reciprocal_rank20"]) for record in cases) / count
            if count
            else 0.0
        ),
        "empty_results": sum(
            record["response_contract"]["result_count"] == 0 for record in cases
        ),
    }


def grouped_metrics(
    records: list[dict[str, Any]],
    field: str,
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record.get(field) or "(empty)")].append(record)
    return {key: metric_block(groups[key]) for key in sorted(groups)}


def timing_metrics(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = [
        float(record["timing"][field])
        for record in records
        if isinstance(record["timing"].get(field), (int, float))
    ]
    return {
        "count": len(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "mean_ms": sum(values) / len(values) if values else None,
        "max_ms": max(values) if values else None,
    }


def counter_dict(values: Iterable[object]) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def artifact_record(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "sha256": sha256_path(path),
        "bytes": path.stat().st_size,
    }


def validate_runtime(
    runtime: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> None:
    if runtime.get("ready") is not True or runtime.get("algorithm") != "algorithm_6":
        raise EvaluationContractError(
            "endpoint is not a ready Algorithm 6 runtime: " + json.dumps(runtime)
        )
    for field, expected in EXPECTED_RUNTIME_COUNTS.items():
        if runtime.get(field) != expected:
            raise EvaluationContractError(
                f"runtime {field} mismatch: expected {expected}, got {runtime.get(field)}"
            )
    files = provenance.get("files") or {}
    for key, expected in EXPECTED_CURRENT_RUNTIME_SHA256.items():
        observed = (files.get(key) or {}).get("sha256")
        if observed != expected:
            raise EvaluationContractError(
                f"current-source hash mismatch for {key}: expected {expected}, got {observed}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8014",
        help="Base URL for the current Algorithm 6 public API",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPO_ROOT / DEFAULT_DATASET,
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=REPO_ROOT / DEFAULT_RESULTS_ROOT,
    )
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()
    if args.workers < 1:
        raise SystemExit("--workers must be at least 1")
    if args.retries < 0:
        raise SystemExit("--retries must be non-negative")

    dataset_path = args.dataset.expanduser().resolve()
    results_root = args.results_root.expanduser().resolve()
    cases, dataset_validation = read_locked_cases(dataset_path)

    provenance_paths = dict(DEFAULT_FILE_PATHS)
    provenance_paths["evaluator"] = EVALUATOR_RELATIVE_PATH
    provenance = collect_provenance(REPO_ROOT, file_paths=provenance_paths)

    base_url = args.base_url.rstrip("/")
    runtime = get_json(base_url + "/api/runtime", timeout=args.timeout)
    health = get_json(base_url + "/health", timeout=args.timeout)
    validate_runtime(runtime, provenance)
    if health.get("status") != "ok":
        raise EvaluationContractError(
            "endpoint health is not ok: " + json.dumps(health)
        )

    started_at = datetime.now(timezone.utc)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    run_dir = results_root / "runs" / run_id
    if run_dir.exists():
        raise EvaluationContractError(f"run directory already exists: {run_dir}")

    def run_one(row: Mapping[str, str]) -> dict[str, Any]:
        return evaluate_case(
            base_url,
            row,
            timeout=args.timeout,
            retries=args.retries,
        )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        records = list(pool.map(run_one, cases))

    finished_at = datetime.now(timezone.utc)
    failures = [record for record in records if not record["hit20"]]
    contract_issues = [
        {
            "case_id": record["case_id"],
            "missing_legal_identity_positions": record["response_contract"][
                "missing_legal_identity_positions"
            ],
            "api_rank_mismatches": record["response_contract"]["api_rank_mismatches"],
        }
        for record in records
        if record["response_contract"]["missing_legal_identity_positions"]
        or record["response_contract"]["api_rank_mismatches"]
    ]

    per_case_path = run_dir / "per_case.jsonl"
    failures_path = run_dir / "failures.jsonl"
    summary_path = run_dir / "summary.json"
    write_jsonl(per_case_path, records)
    write_jsonl(failures_path, failures)

    summary: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "wall_seconds": (finished_at - started_at).total_seconds(),
        "evaluation_claim": {
            "class": "retrospective_accuracy_and_non_regression",
            "blind": False,
            "external_generalization_claim": False,
            "statement": (
                "The locked cases and both named splits have already been visible "
                "during development. Results measure retrospective accuracy and "
                "current-source non-regression, not blind generalization."
            ),
        },
        "target": {
            "interface": "public_api_/api/search",
            "base_url": base_url,
            "request": {"product_context": "", "limit": 20},
            "workers": args.workers,
            "runtime": runtime,
            "health": health,
            "endpoint_source_binding": (
                "The loopback runtime was launched from this worktree. The runtime "
                "endpoint does not publish source hashes; exact local runtime bytes "
                "are frozen below in source_provenance."
            ),
        },
        "identity_contract": {
            "normalization": IDENTITY_NORMALIZATION,
            "visual_result_source": VISUAL_SOURCE,
            "visual_fields_in_priority_order": [
                "matched_family_key",
                "matched_family_name",
            ],
            "non_visual_field": "base_group_key",
            "forbidden_fallbacks": [
                "variant_group",
                "name",
                "candidate_canonical_name",
                "commercial_name",
            ],
        },
        "dataset": {
            "path": dataset_path.relative_to(REPO_ROOT).as_posix(),
            **dataset_validation,
            "interpretation": (
                "Locked historical fair-OCR cohort. Development/holdout labels are "
                "preserved for stratification only; neither is blind in this report."
            ),
        },
        "source_provenance": provenance,
        "metrics": {
            "overall": metric_block(records),
            "by_split": grouped_metrics(records, "split"),
            "by_difficulty": grouped_metrics(records, "difficulty"),
            "by_mistake_type": grouped_metrics(records, "mistake_type"),
            "by_danger": grouped_metrics(records, "danger"),
            "by_model": grouped_metrics(records, "model_name"),
            "by_analysis_cohort": grouped_metrics(records, "analysis_cohort"),
            "by_distance_band": grouped_metrics(records, "distance_band"),
        },
        "response_behavior": {
            "status_counts": counter_dict(
                record["decision"]["status"] for record in records
            ),
            "decision_type_counts": counter_dict(
                record["decision"]["decision_type"] for record in records
            ),
            "response_confirmation_required_counts": counter_dict(
                record["confirmation"]["response_confirmation_required"]
                for record in records
            ),
            "all_results_confirmation_true_cases": sum(
                record["confirmation"]["all_returned_results_require_confirmation"]
                for record in records
            ),
            "all_results_need_clarification_true_cases": sum(
                record["confirmation"]["all_returned_results_need_clarification"]
                for record in records
            ),
            "cases_with_visual_results": sum(
                record["response_contract"]["visual_result_count"] > 0
                for record in records
            ),
            "total_visual_results": sum(
                record["response_contract"]["visual_result_count"]
                for record in records
            ),
            "total_retries": sum(
                record["response_contract"]["retry_count"] for record in records
            ),
            "contract_issue_case_count": len(contract_issues),
            "contract_issues": contract_issues,
        },
        "timing": {
            "client": timing_metrics(records, "client_elapsed_ms"),
            "server": timing_metrics(records, "server_elapsed_ms"),
            "note": (
                "Default workers=1 is intended for interpretable latency against "
                "the single-worker local endpoint."
            ),
        },
        "failure_count": len(failures),
        "failure_case_ids": [record["case_id"] for record in failures],
        "artifacts": {},
    }

    # Hash data artifacts before writing the summary.  The summary cannot
    # truthfully contain its own digest, so latest_summary records only the
    # immutable per-case and failure artifacts too.
    summary["artifacts"] = {
        "per_case": artifact_record(per_case_path),
        "failures": artifact_record(failures_path),
    }
    write_json(summary_path, summary)
    latest_summary_path = results_root / "latest_summary.json"
    write_json(latest_summary_path, summary)

    rendered = {
        "run_id": run_id,
        "metrics": summary["metrics"]["overall"],
        "failures": len(failures),
        "contract_issue_cases": len(contract_issues),
        "run_dir": run_dir.relative_to(REPO_ROOT).as_posix(),
        "summary_sha256": sha256_path(summary_path),
        "per_case_sha256": sha256_path(per_case_path),
        "failures_sha256": sha256_path(failures_path),
    }
    print(json.dumps(rendered, indent=2))
    return 0 if not contract_issues else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except EvaluationContractError as error:
        print(f"evaluation contract error: {error}", file=sys.stderr)
        sys.exit(2)

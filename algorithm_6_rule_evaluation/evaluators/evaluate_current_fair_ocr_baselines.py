#!/usr/bin/env python3
"""Run current A5 and simple lexical baselines on the locked fair-OCR 412.

These are same-data reference baselines for the current Algorithm 6 API report,
not new blind accuracy estimates.  Every method receives the identical raw 412
queries, identical accepted family oracle, and the same 17,476-family catalog.

Comparability boundary:

* current Algorithm 5 is invoked directly because it has no separate public
  endpoint; its exact candidate ``name`` is adapted to the family key;
* Damerau-Levenshtein and Jaro-Winkler rank all exact compact family keys and
  have no safety, visual-gap, consensus, or confirmation behavior;
* therefore the hit/MRR columns are retrieval references, not claims that the
  baseline systems are product-equivalent to the public Algorithm 6 API.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from algorithm_6_rule_evaluation.evaluators.evaluate_current_fair_ocr_412 import (  # noqa: E402
    DEFAULT_DATASET,
    DEFAULT_RESULTS_ROOT,
    EXPECTED_CURRENT_RUNTIME_SHA256,
    LOCKED_ACCEPTED_SCORED_ROWS,
    compact,
    read_locked_cases,
)
from algorithm_6_rule_evaluation.provenance import (  # noqa: E402
    DEFAULT_FILE_PATHS,
    collect_provenance,
    sha256_path,
)


try:
    from rapidfuzz import process
    from rapidfuzz.distance import DamerauLevenshtein, JaroWinkler
except ImportError as error:  # pragma: no cover - environment failure
    raise SystemExit(
        "rapidfuzz is required for the declared lexical baselines"
    ) from error


EVALUATOR_RELATIVE_PATH = Path(
    "algorithm_6_rule_evaluation/evaluators/evaluate_current_fair_ocr_baselines.py"
)
CURRENT_A6_EVALUATOR_PATH = Path(
    "algorithm_6_rule_evaluation/evaluators/evaluate_current_fair_ocr_412.py"
)
ALGORITHM_5_PATH = Path(
    "benchmark_01_legacy/master_algorithms/algorithm_5_commercial_name_search.py"
)
ALGORITHM_5_SUPPORT_PATHS = {
    "current_app_catalog_adapter": Path(
        "benchmark_01_legacy/evaluate_current_app_search.py"
    ),
    "algorithm_2_external_search": Path(
        "benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py"
    ),
}
BASELINE_RESULTS_ROOT = DEFAULT_RESULTS_ROOT.parent / "fair_ocr_412_baselines_current"
EXPECTED_FAMILY_COUNT = 17_476
METHODS = ("current_algorithm_5", "damerau_levenshtein", "jaro_winkler")


class BaselineContractError(RuntimeError):
    """Raised when a baseline cannot satisfy the declared comparison contract."""


def load_module(path: Path, name: str) -> ModuleType:
    absolute = (REPO_ROOT / path).resolve()
    spec = importlib.util.spec_from_file_location(name, absolute)
    if spec is None or spec.loader is None:
        raise BaselineContractError(f"cannot load module from {absolute}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def rank_for(identities: Iterable[str], expected: set[str]) -> int | None:
    return next(
        (index for index, identity in enumerate(identities, 1) if identity in expected),
        None,
    )


def result_metrics(records: list[Mapping[str, Any]], method: str) -> dict[str, Any]:
    ranks = [record["methods"][method]["rank"] for record in records]
    count = len(ranks)
    return {
        "cases": count,
        "hit1": sum(rank == 1 for rank in ranks),
        "hit1_rate": sum(rank == 1 for rank in ranks) / count,
        "hit5": sum(rank is not None and rank <= 5 for rank in ranks),
        "hit5_rate": sum(rank is not None and rank <= 5 for rank in ranks) / count,
        "hit20": sum(rank is not None and rank <= 20 for rank in ranks),
        "hit20_rate": sum(rank is not None and rank <= 20 for rank in ranks) / count,
        "miss20": sum(rank is None or rank > 20 for rank in ranks),
        "mrr20": sum(1.0 / rank for rank in ranks if rank is not None and rank <= 20)
        / count,
        "empty_results": sum(
            not record["methods"][method]["top20"] for record in records
        ),
    }


def grouped_metrics(
    records: list[dict[str, Any]],
    field: str,
) -> dict[str, dict[str, dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record.get(field) or "(empty)")].append(record)
    return {
        group: {method: result_metrics(rows, method) for method in METHODS}
        for group, rows in sorted(groups.items())
    }


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def timing_summary(records: list[dict[str, Any]], method: str) -> dict[str, Any]:
    values = [float(record["methods"][method]["elapsed_ms"]) for record in records]
    return {
        "count": len(values),
        "mean_ms": sum(values) / len(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "max_ms": max(values),
        "warning": (
            "Direct in-process timings are diagnostic only and are not comparable "
            "to public-API end-to-end latency."
        ),
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def family_universe_hash(keys: list[str]) -> str:
    return hashlib.sha256(("\n".join(keys) + "\n").encode("ascii")).hexdigest()


def lexical_top20(
    query: str,
    choices: list[str],
    *,
    scorer: Any,
) -> list[dict[str, Any]]:
    matches = process.extract(query, choices, scorer=scorer, limit=20, score_cutoff=0)
    return [
        {
            "position": index,
            "identity_key": identity,
            "similarity": float(score),
            "candidate_index": candidate_index,
        }
        for index, (identity, score, candidate_index) in enumerate(matches, 1)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPO_ROOT / DEFAULT_DATASET,
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=REPO_ROOT / BASELINE_RESULTS_ROOT,
    )
    args = parser.parse_args()

    dataset_path = args.dataset.expanduser().resolve()
    results_root = args.results_root.expanduser().resolve()
    cases, dataset_validation = read_locked_cases(dataset_path)
    if len(cases) != LOCKED_ACCEPTED_SCORED_ROWS:
        raise BaselineContractError("locked case-count validation unexpectedly failed")

    provenance_paths = dict(DEFAULT_FILE_PATHS)
    provenance_paths["evaluator"] = EVALUATOR_RELATIVE_PATH
    provenance = collect_provenance(REPO_ROOT, file_paths=provenance_paths)
    for key, expected in EXPECTED_CURRENT_RUNTIME_SHA256.items():
        observed = provenance["files"][key]["sha256"]
        if observed != expected:
            raise BaselineContractError(
                f"current-source hash mismatch for {key}: expected {expected}, got {observed}"
            )

    supporting_source = {
        "current_a6_evaluator": {
            "path": CURRENT_A6_EVALUATOR_PATH.as_posix(),
            "sha256": sha256_path(REPO_ROOT / CURRENT_A6_EVALUATOR_PATH),
        }
    }
    for key, path in ALGORITHM_5_SUPPORT_PATHS.items():
        supporting_source[key] = {
            "path": path.as_posix(),
            "sha256": sha256_path(REPO_ROOT / path),
        }

    initialization_started = time.perf_counter()
    algorithm_5 = load_module(ALGORITHM_5_PATH, "fair_ocr_current_algorithm_5")
    catalog = algorithm_5.prepare_catalog()
    initialization_seconds = time.perf_counter() - initialization_started

    families = list(catalog.rescue_index.families)
    family_keys = [str(family.compact) for family in families]
    if len(family_keys) != EXPECTED_FAMILY_COUNT:
        raise BaselineContractError(
            f"family universe count mismatch: expected {EXPECTED_FAMILY_COUNT}, "
            f"got {len(family_keys)}"
        )
    if len(family_keys) != len(set(family_keys)):
        raise BaselineContractError("family candidate universe contains duplicate keys")
    if family_keys != sorted(family_keys):
        raise BaselineContractError("family candidate universe is not deterministically sorted")

    started_at = datetime.now(timezone.utc)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    run_dir = results_root / "runs" / run_id
    if run_dir.exists():
        raise BaselineContractError(f"run directory already exists: {run_dir}")

    records: list[dict[str, Any]] = []
    for row in cases:
        expected = set(json.loads(row["_expected_keys_json"]))
        query_key = compact(row["input"])

        a5_started = time.perf_counter()
        a5_response = algorithm_5.search_catalog(catalog, row["input"], limit=20)
        a5_elapsed_ms = (time.perf_counter() - a5_started) * 1000.0
        a5_results = list(a5_response.get("results") or [])
        if len(a5_results) > 20:
            raise BaselineContractError(
                f"Algorithm 5 returned over 20 results for {row['case_id']}"
            )
        a5_top20 = [
            {
                "position": index,
                "api_rank": item.get("rank"),
                "candidate_id": item.get("candidate_id"),
                "identity_key": compact(item.get("name")),
                "identity_adapter_field": "name",
                "name": item.get("name"),
                "variant_group": item.get("variant_group"),
                "score": item.get("score"),
                "source": item.get("source"),
                "needs_clarification": item.get("needs_clarification"),
                "reasons": item.get("reasons"),
            }
            for index, item in enumerate(a5_results, 1)
        ]
        if any(not item["identity_key"] for item in a5_top20):
            raise BaselineContractError(
                f"Algorithm 5 emitted an empty exact candidate name for {row['case_id']}"
            )

        damerau_started = time.perf_counter()
        damerau_top20 = lexical_top20(
            query_key,
            family_keys,
            scorer=DamerauLevenshtein.normalized_similarity,
        )
        damerau_elapsed_ms = (time.perf_counter() - damerau_started) * 1000.0

        jaro_started = time.perf_counter()
        jaro_top20 = lexical_top20(
            query_key,
            family_keys,
            scorer=JaroWinkler.normalized_similarity,
        )
        jaro_elapsed_ms = (time.perf_counter() - jaro_started) * 1000.0

        method_rows = {
            "current_algorithm_5": {
                "rank": rank_for(
                    (item["identity_key"] for item in a5_top20), expected
                ),
                "top20": a5_top20,
                "elapsed_ms": a5_elapsed_ms,
                "decision": {
                    "status": a5_response.get("status"),
                    "decision_type": a5_response.get("decision_type"),
                    "message": a5_response.get("message"),
                },
            },
            "damerau_levenshtein": {
                "rank": rank_for(
                    (item["identity_key"] for item in damerau_top20), expected
                ),
                "top20": damerau_top20,
                "elapsed_ms": damerau_elapsed_ms,
            },
            "jaro_winkler": {
                "rank": rank_for(
                    (item["identity_key"] for item in jaro_top20), expected
                ),
                "top20": jaro_top20,
                "elapsed_ms": jaro_elapsed_ms,
            },
        }
        records.append(
            {
                "case_id": row["case_id"],
                "split": row["split"],
                "model_name": row["model_name"],
                "input": row["input"],
                "query_key": query_key,
                "expected_family_keys": sorted(expected),
                "expected_family_name": row["expected_family_name"],
                "difficulty": row["difficulty"],
                "danger": row["danger"],
                "mistake_type": row["mistake_type"],
                "methods": method_rows,
            }
        )

    finished_at = datetime.now(timezone.utc)
    per_case_path = run_dir / "per_case.jsonl"
    write_jsonl(per_case_path, records)
    failure_paths: dict[str, Path] = {}
    for method in METHODS:
        path = run_dir / f"failures_{method}.jsonl"
        write_jsonl(path, [row for row in records if row["methods"][method]["rank"] is None])
        failure_paths[method] = path

    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "wall_seconds_excluding_catalog_initialization": (
            finished_at - started_at
        ).total_seconds(),
        "catalog_initialization_seconds": initialization_seconds,
        "evaluation_claim": {
            "class": "retrospective_same_data_retrieval_reference",
            "blind": False,
            "external_generalization_claim": False,
            "product_equivalence_claim": False,
            "statement": (
                "These methods use the same locked queries, oracle, and exact "
                "family universe as the current A6 evaluation. A5 is a direct "
                "in-process candidate-family scorer; the lexical methods lack A6 "
                "visual-gap, safety, consensus, and confirmation behavior."
            ),
        },
        "dataset": {
            "path": dataset_path.relative_to(REPO_ROOT).as_posix(),
            **dataset_validation,
        },
        "candidate_universe": {
            "source": "current Algorithm 5 rescue_index.families",
            "count": len(family_keys),
            "sha256_newline_delimited_compact_keys": family_universe_hash(family_keys),
            "identity": "exact compact base-family key",
            "ordering": "ascending compact family key (stable tie order)",
        },
        "methodology": {
            "current_algorithm_5": {
                "input": "unchanged raw locked query",
                "top_k": 20,
                "identity_adapter": (
                    "compact(result.name); direct A5 has no public base_group_key field"
                ),
                "confirmation_comparability": False,
            },
            "damerau_levenshtein": {
                "input": "uppercase ASCII alphanumeric compact query",
                "candidate_set": "all 17,476 exact compact family keys",
                "score": "RapidFuzz DamerauLevenshtein.normalized_similarity",
                "top_k": 20,
                "feature_limitations": [
                    "no explicit visual-gap semantics",
                    "no OCR learned costs",
                    "no consensus",
                    "no safety decision or confirmation contract",
                ],
            },
            "jaro_winkler": {
                "input": "uppercase ASCII alphanumeric compact query",
                "candidate_set": "all 17,476 exact compact family keys",
                "score": "RapidFuzz JaroWinkler.normalized_similarity",
                "top_k": 20,
                "feature_limitations": [
                    "no explicit visual-gap semantics",
                    "no OCR learned costs",
                    "no consensus",
                    "no safety decision or confirmation contract",
                ],
            },
        },
        "source_provenance": provenance,
        "supporting_source": supporting_source,
        "rapidfuzz_version": getattr(__import__("rapidfuzz"), "__version__", "unknown"),
        "metrics": {
            "overall": {method: result_metrics(records, method) for method in METHODS},
            "by_split": grouped_metrics(records, "split"),
            "by_difficulty": grouped_metrics(records, "difficulty"),
            "by_danger": grouped_metrics(records, "danger"),
        },
        "timing": {method: timing_summary(records, method) for method in METHODS},
        "artifacts": {
            "per_case": {
                "path": per_case_path.relative_to(REPO_ROOT).as_posix(),
                "sha256": sha256_path(per_case_path),
                "bytes": per_case_path.stat().st_size,
            },
            "failures": {
                method: {
                    "path": path.relative_to(REPO_ROOT).as_posix(),
                    "sha256": sha256_path(path),
                    "bytes": path.stat().st_size,
                }
                for method, path in failure_paths.items()
            },
        },
    }
    summary_path = run_dir / "summary.json"
    write_json(summary_path, summary)
    write_json(results_root / "latest_summary.json", summary)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "metrics": summary["metrics"]["overall"],
                "run_dir": run_dir.relative_to(REPO_ROOT).as_posix(),
                "summary_sha256": sha256_path(summary_path),
                "per_case_sha256": sha256_path(per_case_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BaselineContractError as error:
        print(f"baseline contract error: {error}", file=sys.stderr)
        sys.exit(2)

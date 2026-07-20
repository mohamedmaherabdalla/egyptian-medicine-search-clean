#!/usr/bin/env python3
"""Evaluate Algorithm 4 on testing dataset v2 or the manual failed cases."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import multiprocessing
import sys
import time
from pathlib import Path
from typing import Any


DATASET_DIR = Path(__file__).resolve().parent
ROOT = DATASET_DIR.parents[0]
EVALUATION_DIR = ROOT / "benchmark_01_legacy"
MASTER_DIR = EVALUATION_DIR / "master_algorithms"
for path in [str(DATASET_DIR), str(EVALUATION_DIR), str(MASTER_DIR)]:
    if path not in sys.path:
        sys.path.insert(0, path)

import algorithm_4_commercial_name_search as algorithm4
import evaluate_current_app_search as current_eval
import evaluate_algorithms_1_2 as v2_eval


LOGGER = logging.getLogger(__name__)

RESULTS_DIR = DATASET_DIR / "artifacts" / "01_full_benchmark" / "source_tables"
DEFAULT_OUTPUT_PREFIX = "algorithm_4"
DEFAULT_CASE_OUTPUT = DATASET_DIR / "artifacts" / "01_full_benchmark" / "algorithm_4_cases.csv"
DEFAULT_CHUNK_SIZE = 200
DEFAULT_MAX_WORKERS = 8
CONFIDENT_ALGORITHM_4_STATUSES = {"high_confidence", "medium_confidence"}
MISTAKE_METRIC_FIELDS = [
    "mistake_type",
    "failures",
    "failure_share",
    "hit_at_20",
    "behavior_success",
    "unsafe_confident_top1",
]

ALGORITHM_4_CATALOG: algorithm4.Algorithm4Catalog | None = None

MANUAL_CASES = [
    ("optraderolpl", "optaderol"),
    ("Auticax", "ANTI COX II"),
    ("couphseed", "COUGHSED PARACETAMOL CHILDREN OR COUGHSED PARACETAMOL INFANTS"),
    ("ivybnon", "IVY BRONCH"),
    ("sauovent", "salbovent"),
    ("garaxy", "garamycin"),
    ("colchicime", "colchicine"),
    ("flacton", "flector"),
    ("levohista", "LEVOHISTAM"),
    ("oplax", "OPLEX N OR OPLEX MONO"),
    ("oplox", "OPLEX N OR OPLEX MONO"),
    ("moxclar", "e-moxclav"),
    ("Ezogoat", "Ezogast"),
    ("healreptic", "healioreptic"),
    ("colovarin", "COLOVERIN D"),
    ("Eucavban", "eucarbon"),
    ("librux", "LIBRAX SUGAR"),
    ("mebula", "nebula"),
    ("dexazue", "dexazone"),
    ("octotron", "OCTATRON"),
    ("revanoglob", "Revanoglow"),
    ("jvsprin", "jusprin"),
    ("mixmail", "mixmazil"),
    ("puresmin", "PURESAMINE"),
    ("biato", "ibiacto"),
    ("salire", "saline"),
    ("devamol", "DEVAROL S"),
    ("calcihon", "calcitron"),
    ("broncholrn", "BRONCHOLIN S"),
    ("apido", "apidone"),
    ("tavaric", "tavanic"),
    ("flopudex", "flopadex"),
    ("metaps", "metapsin"),
    ("arymentin", "augmentin"),
    ("centerloc", "controloc"),
    ("moxauidey", "moxavidex"),
    ("codlor", "codilar"),
    ("Duncof", "Duncef"),
    ("Cndalenz", "Ondalenz"),
    ("Duphlac", "Duphalac"),
    ("Dophlac", "Duphalac"),
    ("Conlentin", "Conventin"),
    ("taves", "tareg"),
    ("cyprocin", "ciprocin"),
    ("cyprocen", "ciprocin"),
    ("vonifrton", "vomifraton"),
    ("awndisb", "awadist"),
    ("vonaspine", "vonaspire"),
    ("Ketostenil", "Ketosteril"),
    ("Ketostenl", "Ketosteril"),
]

UNSCORABLE_MANUAL_INPUTS = {"mebula", "revanoglob", "duncof"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Algorithm 4 on V2 data.")
    parser.add_argument("--input-csv", type=Path, default=v2_eval.DATASET_PATH, help="Dataset CSV to evaluate.")
    parser.add_argument("--manual", action="store_true", help="Evaluate the 50 manually supplied failed cases.")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit. Zero means all selected rows.")
    parser.add_argument(
        "--workers",
        type=int,
        default=min(DEFAULT_MAX_WORKERS, max(1, multiprocessing.cpu_count())),
        help="Worker process count.",
    )
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Rows per worker chunk.")
    parser.add_argument("--output-prefix", default=DEFAULT_OUTPUT_PREFIX, help="Prefix for generated result filenames.")
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--case-output", type=Path, default=DEFAULT_CASE_OUTPUT)
    return parser.parse_args()


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")


def main() -> int:
    configure_logging()
    args = parse_args()
    if args.workers <= 0:
        raise ValueError("--workers must be positive")
    if args.chunk_size <= 0:
        raise ValueError("--chunk-size must be positive")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.case_output.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    initialize_global_state()
    cases = manual_case_rows() if args.manual else read_cases(args.input_csv)
    if args.limit:
        cases = cases[: args.limit]
    LOGGER.info("loaded cases=%d workers=%d chunk_size=%d", len(cases), args.workers, args.chunk_size)

    rows = run_evaluation(cases, args.workers, args.chunk_size)
    if len(rows) != len(cases):
        raise RuntimeError(f"row-count mismatch: cases={len(cases)} rows={len(rows)}")

    metrics = v2_eval.metric_rows_by_scope_category(rows)
    error_metrics = v2_eval.metric_rows_by_error_type(rows)
    mistake_metrics = metric_rows_by_mistake_type(rows)
    failures = v2_eval.failure_samples(rows, "algorithm_4")
    elapsed = time.time() - started

    paths = output_paths(args.output_dir, args.output_prefix)
    v2_eval.write_csv(args.case_output, rows)
    v2_eval.write_csv(paths["metrics"], metrics)
    v2_eval.write_csv(paths["error_metrics"], error_metrics)
    write_mistake_metrics(paths["mistake_metrics"], mistake_metrics)
    v2_eval.write_csv(paths["failures"], failures)
    write_report(paths["report"], rows, metrics, elapsed, args)
    write_summary(paths["summary"], rows, elapsed, args)
    LOGGER.info("wrote Algorithm 4 report: %s", paths["report"])
    return 0


def initialize_global_state() -> None:
    """Prepare Algorithm 4 and the relevance index used by V2 metrics."""

    global ALGORITHM_4_CATALOG
    ALGORITHM_4_CATALOG = algorithm4.prepare_catalog()
    # This relevance index is evaluator-only. Algorithm 4 itself does not use
    # Algorithm 1 search or Algorithm 1's full SearchIndex at query time.
    v2_eval.CURRENT_INDEX = current_eval.SearchIndex(current_eval.prepare_records())


def read_cases(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        cases = []
        for source_row, row in enumerate(reader, 1):
            cases.append({
                "source_row": row.get("source_row") or source_row,
                "input": row["input"],
                "expected": row["expected"],
                "category": row["category"],
                "error_type": row["error_type"],
                "case_subcategory": row.get("case_subcategory", "standard"),
                "unreadable_continuation": row.get("unreadable_continuation", "0") in {"1", "true", "True"},
                "difficulty": row["difficulty"],
                "danger": row["danger"],
                "scope": row["scope"],
                "expected_behavior": row["expected_behavior"],
                "collision_with": row.get("collision_with", ""),
                "source_base_group": row.get("source_base_group", ""),
                "generator_function": row.get("generator_function", ""),
            })
    return cases


def manual_case_rows() -> list[dict[str, Any]]:
    rows = []
    for index, (edited, right) in enumerate(MANUAL_CASES, 1):
        case_subcategory = (
            "catalog_target_absent"
            if edited.lower() in UNSCORABLE_MANUAL_INPUTS
            else "standard"
        )
        rows.append({
            "source_row": f"manual_{index:03d}",
            "input": edited,
            "expected": right,
            "category": "manual_failed_cases",
            "error_type": "manual_observed_typo",
            "case_subcategory": case_subcategory,
            "unreadable_continuation": False,
            "difficulty": "EXTREME",
            "danger": "DANGEROUS",
            "scope": "manual",
            "expected_behavior": "match",
            "collision_with": "",
            "source_base_group": right,
            "generator_function": "manual_cases",
        })
    return rows


def run_evaluation(cases: list[dict[str, Any]], workers: int, chunk_size: int) -> list[dict[str, Any]]:
    chunks = [cases[index : index + chunk_size] for index in range(0, len(cases), chunk_size)]
    if workers <= 1:
        rows = []
        for chunk in chunks:
            rows.extend(evaluate_chunk(chunk))
        return rows

    context_name = "fork" if "fork" in multiprocessing.get_all_start_methods() else None
    context = multiprocessing.get_context(context_name) if context_name else multiprocessing.get_context()
    rows = []
    with context.Pool(processes=workers) as pool:
        for chunk_rows in pool.imap(evaluate_chunk, chunks):
            rows.extend(chunk_rows)
            if len(rows) % 5_000 == 0 or len(rows) == len(cases):
                LOGGER.info("processed=%d", len(rows))
    return rows


def evaluate_chunk(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [evaluate_algorithm_4_case(case) for case in cases]


def evaluate_algorithm_4_case(case: dict[str, Any]) -> dict[str, Any]:
    if ALGORITHM_4_CATALOG is None:
        raise RuntimeError("ALGORITHM_4_CATALOG is not initialized")
    targets = v2_eval.targets_for_case(case)
    rel_total = v2_eval.relevant_total(targets)
    query_request: Any = case["input"]
    if case.get("unreadable_continuation"):
        query_request = {
            "text": case["input"],
            "unreadable_continuation": True,
        }
    response = algorithm4.search_catalog(ALGORITHM_4_CATALOG, query_request, v2_eval.TOP_K_RESULTS)
    results = list(response.get("results") or [])
    status = str(response.get("status") or "")
    relevances = [v2_eval.external_relevance(item, targets) for item in results]
    top1 = results[0] if results else None
    top1_rel = relevances[0] if relevances else 0
    top1_confident = bool(
        top1
        and status in CONFIDENT_ALGORITHM_4_STATUSES
        and not bool(top1.get("needs_clarification"))
    )
    first_rank, ap20, ndcg20 = v2_eval.ranking_metrics(
        relevances,
        rel_total,
        case,
        bool(results),
        top1_confident=top1_confident,
    )
    behavior_success = algorithm_4_behavior_success(case, first_rank, status, bool(results))
    unsafe_confident_top1 = bool(
        top1
        and top1_rel == 0
        and top1_confident
        and case["expected_behavior"] != "no_match"
    )
    missing_clarification = bool(
        top1
        and case["danger"] in {"CAUTION", "DANGEROUS"}
        and case["expected_behavior"] in {"ambiguous", "match"}
        and top1_confident
    )
    mistake_type = classify_mistake_type(case, results, first_rank)
    scored_case = case.get("case_subcategory") not in {
        "exact_real_name_collision",
        "catalog_target_absent",
    }
    expected_distance = edit_distance(case["input"], case["expected"])
    top1_distance = edit_distance(case["input"], top1.get("name", "")) if top1 else 999
    return {
        "algorithm": "algorithm_4",
        "scope": case["scope"],
        "source_row": case["source_row"],
        "category": case["category"],
        "error_type": case["error_type"],
        "case_subcategory": case.get("case_subcategory", "standard"),
        "unreadable_continuation": int(bool(case.get("unreadable_continuation"))),
        "mistake_type": mistake_type,
        "scored_case": int(scored_case),
        "difficulty": case["difficulty"],
        "danger": case["danger"],
        "expected_behavior": case["expected_behavior"],
        "input": case["input"],
        "expected": case["expected"],
        "first_rank": first_rank,
        "hit_at_1": int(first_rank <= 1),
        "hit_at_5": int(first_rank <= 5),
        "hit_at_10": int(first_rank <= 10),
        "hit_at_20": int(first_rank <= 20),
        "ap20": ap20,
        "ndcg20": ndcg20,
        "result_count": len(results),
        "candidate_pool": int(response.get("candidate_count") or len(results)),
        "top1_base": top1.get("name", "") if top1 else "",
        "top1_product": top1.get("commercial_name", "") if top1 else "",
        "top1_score": top1.get("score", "") if top1 else "",
        "expected_edit_distance": expected_distance,
        "top1_edit_distance": top1_distance,
        "decision_type": response.get("decision_type", ""),
        "top1_variant_group": top1.get("variant_group", "") if top1 else "",
        "top1_relevance": top1_rel,
        "top1_status": status or "no_result",
        "top1_needs_clarification": int(bool(top1.get("needs_clarification"))) if top1 else "",
        "top1_source": top1.get("source", "") if top1 else "",
        "top1_signals": "|".join(top1.get("reasons", []) or []) if top1 else "",
        "top5_bases": "|".join(str(item.get("name") or "") for item in results[:5]),
        "unsafe_confident_top1": int(unsafe_confident_top1),
        "missing_clarification": int(missing_clarification),
        "behavior_success": int(behavior_success),
    }


def algorithm_4_behavior_success(case: dict[str, Any], first_rank: int, status: str, has_results: bool) -> bool:
    if case["expected_behavior"] == "match":
        return first_rank <= v2_eval.TOP_K_RESULTS
    if case["expected_behavior"] == "ambiguous":
        return status not in CONFIDENT_ALGORITHM_4_STATUSES and has_results
    return (not has_results) or status not in CONFIDENT_ALGORITHM_4_STATUSES


def edit_distance(left: Any, right: Any) -> int:
    """Return compact unweighted Damerau distance for evaluator diagnostics."""

    left_key = current_eval.compact_key(left)
    right_key = current_eval.compact_key(right)
    if not left_key or not right_key:
        return 999
    return int(algorithm4.damerau(left_key, right_key, weighted=False))


def expected_variant_group(expected: str) -> str:
    """Resolve the expected family to Algorithm 4's catalog variant group."""

    if ALGORITHM_4_CATALOG is None:
        return current_eval.normalize_search(expected)
    key = current_eval.compact_key(expected)
    family_id = ALGORITHM_4_CATALOG.rescue_index.family_by_key.get(key)
    if family_id is None:
        return current_eval.normalize_search(expected)
    family = ALGORITHM_4_CATALOG.rescue_index.families[family_id]
    return family.variant_group or family.norm


def classify_mistake_type(case: dict[str, Any], results: list[dict[str, Any]], first_rank: int) -> str:
    """Classify a failed row by the six user-approved mistake mechanisms."""

    if case.get("case_subcategory") == "exact_real_name_collision":
        return "type_1_exact_real_name_collision"
    if first_rank <= 1:
        return "none"
    if case.get("unreadable_continuation"):
        return "type_3_unreadable_continuation"

    top1 = results[0] if results else None
    if top1:
        expected_group = expected_variant_group(case["expected"])
        top_group = str(top1.get("variant_group") or "")
        if expected_group and top_group and expected_group == top_group:
            return "type_4_family_variant"

        expected_distance = edit_distance(case["input"], case["expected"])
        top_distance = edit_distance(case["input"], top1.get("name", ""))
        if expected_distance == top_distance:
            return "type_2_equal_edit_evidence"

    if first_rank > v2_eval.TOP_K_RESULTS:
        return "type_5_candidate_generation"
    return "type_6_candidate_ranking"


def output_paths(output_dir: Path, prefix: str) -> dict[str, Path]:
    return {
        "metrics": output_dir / f"{prefix}_metrics_by_category.csv",
        "error_metrics": output_dir / f"{prefix}_metrics_by_error_type.csv",
        "mistake_metrics": output_dir / f"{prefix}_metrics_by_mistake_type.csv",
        "failures": output_dir / f"{prefix}_failure_samples.csv",
        "report": output_dir / f"{prefix}_report.md",
        "summary": output_dir / f"{prefix}_summary.json",
    }


def write_mistake_metrics(path: Path, rows: list[dict[str, Any]]) -> None:
    if rows:
        v2_eval.write_csv(path, rows)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=MISTAKE_METRIC_FIELDS).writeheader()


def write_report(path: Path, rows: list[dict[str, Any]], metrics: list[dict[str, Any]], elapsed: float, args: argparse.Namespace) -> None:
    total = aggregate(rows)
    mistake_metrics = metric_rows_by_mistake_type(rows)
    lines = [
        "# Algorithm 4 Benchmark Report",
        "",
        "Algorithm 4 = Algorithm 2 full search + lightweight family-level rescue/safety layer.",
        "",
        "## Run",
        "",
        f"- Cases: `{len(rows):,}`",
        f"- Runtime: `{elapsed:.2f}` seconds",
        f"- Input: `manual cases`" if args.manual else f"- Input: `{args.input_csv}`",
        "",
        "## Overall",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| Hit@1 | {total['hit_at_1']:.2%} |",
        f"| Hit@20 | {total['hit_at_20']:.2%} |",
        f"| Fair Hit@1 (diagnostic rows excluded) | {total['fair_hit_at_1']:.2%} |",
        f"| Fair Hit@20 (diagnostic rows excluded) | {total['fair_hit_at_20']:.2%} |",
        f"| Fair scored cases | {int(total['fair_cases']):,} |",
        f"| Diagnostic/unscorable cases | {int(total['diagnostic_cases']):,} |",
        f"| Behavior success | {total['behavior_success']:.2%} |",
        f"| Unsafe confident top-1 | {total['unsafe_confident_top1']:.2%} |",
        f"| Missing clarification | {total['missing_clarification']:.2%} |",
        f"| No result | {total['no_result']:.2%} |",
        f"| Average candidate pool | {total['avg_candidate_pool']:.2f} |",
        "",
        "## By Mistake Type",
        "",
        "The existing mutation category and the mistake type are independent dimensions. "
        "Diagnostic rows remain visible but are excluded from fair retrieval accuracy.",
        "",
        "| mistake type | failed rows | share of failures | recovered@20 | behavior success |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in mistake_metrics:
        lines.append(
            "| {mistake_type} | {failures:,} | {failure_share:.2%} | {hit_at_20:.2%} | {behavior_success:.2%} |".format(
                mistake_type=row["mistake_type"],
                failures=int(row["failures"]),
                failure_share=float(row["failure_share"]),
                hit_at_20=float(row["hit_at_20"]),
                behavior_success=float(row["behavior_success"]),
            )
        )
    lines.extend([
        "",
        "## By Scope / Category",
        "",
        "| scope | category | cases | Hit@1 | Hit@20 | behavior | unsafe | no result |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in metrics:
        lines.append(
            "| {scope} | {category} | {cases} | {hit_at_1:.2%} | {hit_at_20:.2%} | {behavior_success_rate:.2%} | {unsafe_confident_top1_rate:.2%} | {no_result_rate:.2%} |".format(
                scope=row["scope"],
                category=row["category"],
                cases=int(row["cases"]),
                hit_at_1=float(row["hit_at_1"]),
                hit_at_20=float(row["hit_at_20"]),
                behavior_success_rate=float(row["behavior_success_rate"]),
                unsafe_confident_top1_rate=float(row["unsafe_confident_top1_rate"]),
                no_result_rate=float(row["no_result_rate"]),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def aggregate(rows: list[dict[str, Any]]) -> dict[str, float]:
    count = max(len(rows), 1)
    fair_rows = [row for row in rows if int(row.get("scored_case", 1))]
    fair_count = max(len(fair_rows), 1)
    return {
        "hit_at_1": sum(int(row["hit_at_1"]) for row in rows) / count,
        "hit_at_20": sum(int(row["hit_at_20"]) for row in rows) / count,
        "fair_hit_at_1": sum(int(row["hit_at_1"]) for row in fair_rows) / fair_count,
        "fair_hit_at_20": sum(int(row["hit_at_20"]) for row in fair_rows) / fair_count,
        "fair_cases": float(len(fair_rows)),
        "diagnostic_cases": float(len(rows) - len(fair_rows)),
        "behavior_success": sum(int(row["behavior_success"]) for row in rows) / count,
        "unsafe_confident_top1": sum(int(row["unsafe_confident_top1"]) for row in rows) / count,
        "missing_clarification": sum(int(row["missing_clarification"]) for row in rows) / count,
        "no_result": sum(int(row["result_count"]) == 0 for row in rows) / count,
        "avg_candidate_pool": sum(int(row["candidate_pool"]) for row in rows) / count,
    }


def metric_rows_by_mistake_type(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate raw outcomes by the independent mistake-type dimension."""

    failed_rows = [
        row for row in rows
        if int(row.get("scored_case", 1)) and not int(row["hit_at_1"])
    ]
    total_failures = max(len(failed_rows), 1)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in failed_rows:
        mistake_type = str(row.get("mistake_type") or "unclassified")
        grouped.setdefault(mistake_type, []).append(row)
    output = []
    for mistake_type, group in sorted(grouped.items()):
        count = len(group)
        output.append({
            "mistake_type": mistake_type,
            "failures": count,
            "failure_share": count / total_failures,
            "hit_at_20": sum(int(row["hit_at_20"]) for row in group) / count,
            "behavior_success": sum(int(row["behavior_success"]) for row in group) / count,
            "unsafe_confident_top1": sum(int(row["unsafe_confident_top1"]) for row in group) / count,
        })
    return output


def write_summary(path: Path, rows: list[dict[str, Any]], elapsed: float, args: argparse.Namespace) -> None:
    input_path = args.input_csv.resolve()
    path.write_text(json.dumps({
        "cases": len(rows),
        "elapsed_seconds": elapsed,
        "manual": bool(args.manual),
        "input_csv": str(input_path.relative_to(ROOT) if input_path.is_relative_to(ROOT) else input_path),
        "output_prefix": args.output_prefix,
        "overall": aggregate(rows),
        "mistake_types": metric_rows_by_mistake_type(rows),
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

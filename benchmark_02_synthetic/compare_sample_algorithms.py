#!/usr/bin/env python3
"""Compare Algorithm 1, Algorithm 2, Algorithm 3, and DrugEye on the same V2 sample rows."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DATASET_DIR = Path(__file__).resolve().parent
RESULTS_DIR = DATASET_DIR / "results" / "03_sample_6000"
FULL_ARTIFACTS_DIR = DATASET_DIR / "artifacts" / "01_full_benchmark"
SAMPLE_ARTIFACTS_DIR = DATASET_DIR / "artifacts" / "03_sample_6000"
FULL_DATASET_PATH = DATASET_DIR / "data" / "test_cases.csv"


DEFAULT_ALGORITHMS = {
    "current_app": FULL_ARTIFACTS_DIR / "algorithm_1_cases.csv",
    "external_english_fast": FULL_ARTIFACTS_DIR / "algorithm_2_cases.csv",
    "master_algorithm": FULL_ARTIFACTS_DIR / "algorithm_3_cases.csv",
    "drugeye_trade": SAMPLE_ARTIFACTS_DIR / "drugeye_cases.csv",
}

DISPLAY_NAMES = {
    "current_app": "Algorithm 1",
    "external_english_fast": "Algorithm 2",
    "master_algorithm": "Algorithm 3",
    "drugeye_trade": "DrugEye trade",
}

DISPLAY_ORDER = ["current_app", "external_english_fast", "master_algorithm", "drugeye_trade"]


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(DATASET_DIR.parent))
    except ValueError:
        return str(resolved)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare algorithms on the same proportional V2 sample.")
    parser.add_argument(
        "--sample", type=Path, default=DATASET_DIR / "data" / "samples" / "proportional_6000.csv"
    )
    parser.add_argument("--output-prefix", default="four_way")
    parser.add_argument("--drugeye-results", type=Path, default=DEFAULT_ALGORITHMS["drugeye_trade"])
    return parser.parse_args()


def load_sample(path: Path) -> tuple[set[int], Counter[tuple[str, str]], dict[int, dict[str, str]]]:
    source_rows: set[int] = set()
    counts: Counter[tuple[str, str]] = Counter()
    rows_by_source: dict[int, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, 1):
            source_row = int(row.get("source_row") or row_number)
            source_rows.add(source_row)
            counts[(row["scope"], row["category"])] += 1
            rows_by_source[source_row] = dict(row)
    return source_rows, counts, rows_by_source


def full_counts() -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    with FULL_DATASET_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            counts[(row["scope"], row["category"])] += 1
    return counts


def load_algorithm_rows(path: Path, sample_rows: set[int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source_row = int(row["source_row"])
            if source_row not in sample_rows:
                continue
            rows.append(dict(row))
    return rows


def fnum(value: Any) -> float:
    if value in ("", None):
        return 0.0
    return float(value)


def metric_row(algorithm: str, scope: str, category: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    if count == 0:
        return {
            "algorithm": algorithm,
            "scope": scope,
            "category": category,
            "cases": 0,
            "hit_at_1": 0.0,
            "hit_at_20": 0.0,
            "behavior_success_rate": 0.0,
            "unsafe_confident_top1_rate": 0.0,
            "no_result_rate": 0.0,
            "network_error_rate": 0.0,
            "avg_candidate_pool": 0.0,
        }
    return {
        "algorithm": algorithm,
        "scope": scope,
        "category": category,
        "cases": count,
        "hit_at_1": sum(fnum(row.get("hit_at_1")) for row in rows) / count,
        "hit_at_20": sum(fnum(row.get("hit_at_20")) for row in rows) / count,
        "behavior_success_rate": sum(fnum(row.get("behavior_success")) for row in rows) / count,
        "unsafe_confident_top1_rate": sum(fnum(row.get("unsafe_confident_top1")) for row in rows) / count,
        "no_result_rate": sum(1 for row in rows if str(row.get("top1_status") or "") == "no_result") / count,
        "network_error_rate": sum(1 for row in rows if str(row.get("network_error") or "")) / count,
        "avg_candidate_pool": sum(fnum(row.get("candidate_pool")) for row in rows) / count,
    }


def aggregate(algorithm: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metrics = [metric_row(algorithm, "__ALL__", "__ALL__", rows)]
    by_scope: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_category: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_scope[row["scope"]].append(row)
        by_category[(row["scope"], row["category"])].append(row)
    for scope, group in sorted(by_scope.items()):
        metrics.append(metric_row(algorithm, scope, "__ALL__", group))
    for (scope, category), group in sorted(by_category.items()):
        metrics.append(metric_row(algorithm, scope, category, group))
    return metrics


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def pct(value: Any) -> str:
    return f"{float(value) * 100:.2f}%"


def write_report(
    path: Path,
    sample_path: Path,
    sample_rows: set[int],
    sample_counts: Counter[tuple[str, str]],
    full_category_counts: Counter[tuple[str, str]],
    algorithm_rows: dict[str, list[dict[str, Any]]],
    metrics: list[dict[str, Any]],
) -> None:
    overall = {
        row["algorithm"]: row
        for row in metrics
        if row["scope"] == "__ALL__" and row["category"] == "__ALL__"
    }
    scope_rows = [
        row for row in metrics
        if row["category"] == "__ALL__" and row["scope"] != "__ALL__"
    ]
    category_rows = [
        row for row in metrics
        if row["category"] != "__ALL__"
    ]
    category_total = sum(sample_counts.values())

    lines = [
        "# V2 Proportional Sample Four-Way Benchmark",
        "",
        f"Sample file: `{sample_path}`.",
        f"Sample rows: `{len(sample_rows):,}`.",
        f"Categories covered: `{len(sample_counts)}`.",
        "",
        "The sample preserves the full V2 category distribution using deterministic hash ordering inside each category. All four systems are scored on exactly the same `source_row` set.",
        "",
        "Algorithm naming: Algorithm 1 = current app evaluator, Algorithm 2 = external English fast algorithm, Algorithm 3 = master rank-fusion algorithm.",
        "",
        "## Row Coverage",
        "",
        "| algorithm | result rows on sample | expected rows | complete |",
        "| --- | ---: | ---: | --- |",
    ]
    for algorithm, rows in algorithm_rows.items():
        complete = "yes" if len(rows) == len(sample_rows) else "no"
        lines.append(f"| `{DISPLAY_NAMES.get(algorithm, algorithm)}` | {len(rows):,} | {len(sample_rows):,} | {complete} |")

    lines += [
        "",
        "## Overall Scores",
        "",
        "| algorithm | cases | Hit@1 | Hit@20 | behavior success | unsafe top-1 | no-result | network error | avg candidates |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for algorithm in DISPLAY_ORDER:
        row = overall[algorithm]
        lines.append(
            f"| `{DISPLAY_NAMES.get(algorithm, algorithm)}` | {row['cases']:,} | {pct(row['hit_at_1'])} | {pct(row['hit_at_20'])} | "
            f"{pct(row['behavior_success_rate'])} | {pct(row['unsafe_confident_top1_rate'])} | "
            f"{pct(row['no_result_rate'])} | {pct(row['network_error_rate'])} | {float(row['avg_candidate_pool']):.2f} |"
        )

    lines += [
        "",
        "## Scope Scores",
        "",
        "| algorithm | scope | cases | Hit@1 | Hit@20 | behavior success | unsafe top-1 | no-result | network error |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(scope_rows, key=lambda item: (item["scope"], item["algorithm"])):
        lines.append(
            f"| `{DISPLAY_NAMES.get(row['algorithm'], row['algorithm'])}` | `{row['scope']}` | {row['cases']:,} | {pct(row['hit_at_1'])} | "
            f"{pct(row['hit_at_20'])} | {pct(row['behavior_success_rate'])} | "
            f"{pct(row['unsafe_confident_top1_rate'])} | {pct(row['no_result_rate'])} | {pct(row['network_error_rate'])} |"
        )

    lines += [
        "",
        "## Sample Distribution",
        "",
        "| scope | category | full rows | sample rows | sample share |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for key in sorted(sample_counts):
        lines.append(
            f"| `{key[0]}` | `{key[1]}` | {full_category_counts[key]:,} | {sample_counts[key]:,} | "
            f"{sample_counts[key] / category_total * 100:.2f}% |"
        )

    lines += [
        "",
        "## Category Scores",
        "",
        "| algorithm | scope | category | cases | Hit@1 | Hit@20 | behavior success | no-result | network error |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(category_rows, key=lambda item: (item["scope"], item["category"], item["algorithm"])):
        lines.append(
            f"| `{DISPLAY_NAMES.get(row['algorithm'], row['algorithm'])}` | `{row['scope']}` | `{row['category']}` | {row['cases']:,} | "
            f"{pct(row['hit_at_1'])} | {pct(row['hit_at_20'])} | {pct(row['behavior_success_rate'])} | "
            f"{pct(row['no_result_rate'])} | {pct(row['network_error_rate'])} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    sample_rows, sample_counts, _ = load_sample(args.sample)
    paths = dict(DEFAULT_ALGORITHMS)
    paths["drugeye_trade"] = args.drugeye_results

    algorithm_rows = {
        algorithm: load_algorithm_rows(path, sample_rows)
        for algorithm, path in paths.items()
    }
    metrics: list[dict[str, Any]] = []
    for algorithm, rows in algorithm_rows.items():
        metrics.extend(aggregate(algorithm, rows))

    metrics_path = RESULTS_DIR / f"{args.output_prefix}_metrics.csv"
    report_path = RESULTS_DIR / f"{args.output_prefix}_report.md"
    summary_path = RESULTS_DIR / f"{args.output_prefix}_summary.json"
    write_csv(metrics_path, metrics)
    write_report(
        report_path,
        args.sample,
        sample_rows,
        sample_counts,
        full_counts(),
        algorithm_rows,
        metrics,
    )
    summary = {
        "sample": display_path(args.sample),
        "sample_rows": len(sample_rows),
        "categories": len(sample_counts),
        "algorithm_rows": {algorithm: len(rows) for algorithm, rows in algorithm_rows.items()},
        "metrics": display_path(metrics_path),
        "report": display_path(report_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

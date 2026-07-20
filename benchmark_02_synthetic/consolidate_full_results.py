#!/usr/bin/env python3
"""Consolidate compatible full-run algorithm tables into canonical outputs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_SOURCE_DIR = HERE / "artifacts" / "01_full_benchmark" / "source_tables"
DEFAULT_OUTPUT_DIR = HERE / "results" / "01_full_benchmark"

ALGORITHM_SOURCES = {
    "algorithm_1_current_app": "algorithm_1",
    "algorithm_2_external_fast": "algorithm_2",
    "algorithm_3_rank_fusion": "algorithm_3",
    "algorithm_4_family_rescue": "algorithm_4",
}

TABLE_SUFFIXES = {
    "metrics_by_category.csv": "metrics_by_category.csv",
    "metrics_by_error_type.csv": "metrics_by_error_type.csv",
    "failure_samples.csv": "failure_samples.csv",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def merge_tables(source_dir: Path, output_dir: Path, output_name: str, suffix: str) -> int:
    inputs: list[tuple[str, Path]] = []
    fieldnames = ["algorithm"]
    for algorithm, prefix in ALGORITHM_SOURCES.items():
        path = source_dir / f"{prefix}_{suffix}"
        if not path.exists():
            raise FileNotFoundError(path)
        fields, _ = read_rows(path)
        for field in fields:
            if field != "algorithm" and field not in fieldnames:
                fieldnames.append(field)
        inputs.append((algorithm, path))

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_name
    row_count = 0
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for algorithm, path in inputs:
            _, rows = read_rows(path)
            for row in rows:
                row["algorithm"] = algorithm
                writer.writerow(row)
                row_count += 1
    return row_count


def overall_metrics(path: Path) -> dict[str, str]:
    _, rows = read_rows(path)
    for row in rows:
        if row["scope"] == "__ALL__" and row["category"] == "__ALL__":
            return row
    raise ValueError(f"missing overall row in {path}")


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    counts = {
        output_name: merge_tables(source_dir, output_dir, output_name, suffix)
        for output_name, suffix in TABLE_SUFFIXES.items()
    }
    algorithms = {}
    for algorithm, prefix in ALGORITHM_SOURCES.items():
        metrics_path = source_dir / f"{prefix}_metrics_by_category.csv"
        algorithms[algorithm] = overall_metrics(metrics_path)
    summary = {
        "dataset": "benchmark_02_synthetic/data/test_cases.csv",
        "cases_per_algorithm": 115000,
        "algorithms": algorithms,
        "canonical_tables": counts,
        "raw_case_tables": "benchmark_02_synthetic/artifacts/01_full_benchmark/",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    for name, count in counts.items():
        print(f"{name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

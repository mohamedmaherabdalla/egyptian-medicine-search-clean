#!/usr/bin/env python3
"""Aggregate OCR observations without conflating OCR and search metrics."""

from __future__ import annotations

import argparse
import collections
import json
import statistics
from pathlib import Path

from benchmark_common import DEFAULT_DATA_DIR, DEFAULT_RESULTS_DIR, read_csv, write_csv, write_json


FIELDS = [
    "model_name", "model_version", "preprocessing_id", "scope", "rows",
    "scored_rows", "source_excluded_rows", "successful_rows", "runtime_error_rate",
    "exact_match_accuracy", "word_error_rate",
    "mean_character_error_rate", "median_character_error_rate", "empty_output_rate",
    "mean_latency_ms", "median_latency_ms", "p95_latency_ms",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("observations", nargs="+", type=Path)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_DATA_DIR / "dataset_manifest.csv")
    return parser.parse_args()


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def aggregate(
    key: tuple[str, str, str, str],
    rows: list[dict[str, str]],
    usable_samples: set[str],
) -> dict[str, object]:
    model_name, model_version, preprocessing_id, scope = key
    scored = [row for row in rows if row.get("sample_id") in usable_samples]
    successful = [row for row in scored if row.get("run_status") == "ok"]
    denominator = max(len(successful), 1)
    latencies = [float(row.get("latency_ms") or 0) for row in successful]
    character_errors = [float(row.get("normalized_edit_distance") or 0) for row in successful]
    exact = sum(int(row.get("exact_match") or 0) for row in successful)
    return {
        "model_name": model_name,
        "model_version": model_version,
        "preprocessing_id": preprocessing_id,
        "scope": scope,
        "rows": len(rows),
        "scored_rows": len(scored),
        "source_excluded_rows": len(rows) - len(scored),
        "successful_rows": len(successful),
        "runtime_error_rate": (len(scored) - len(successful)) / max(len(scored), 1),
        "exact_match_accuracy": exact / denominator,
        "word_error_rate": (len(successful) - exact) / denominator,
        "mean_character_error_rate": statistics.fmean(character_errors) if character_errors else 0.0,
        "median_character_error_rate": statistics.median(character_errors) if character_errors else 0.0,
        "empty_output_rate": sum(int(row.get("empty_output") or 0) for row in successful) / denominator,
        "mean_latency_ms": statistics.fmean(latencies) if latencies else 0.0,
        "median_latency_ms": statistics.median(latencies) if latencies else 0.0,
        "p95_latency_ms": percentile(latencies, 0.95),
    }


def main() -> int:
    args = parse_args()
    usable_samples = {
        row["sample_id"]
        for row in read_csv(args.manifest)
        if row.get("ground_truth_usable") == "1"
    }
    observations = []
    for path in args.observations:
        observations.extend(read_csv(path))
    grouped: dict[tuple[str, str, str, str], list[dict[str, str]]] = collections.defaultdict(list)
    for row in observations:
        base = (row["model_name"], row["model_version"], row["preprocessing_id"])
        grouped[(*base, "all")].append(row)
        grouped[(*base, f"split:{row['split']}")].append(row)
        grouped[(*base, f"difficulty:{row['difficulty']}")].append(row)
    metrics = [aggregate(key, rows, usable_samples) for key, rows in sorted(grouped.items())]
    write_csv(args.results_dir / "ocr_metrics.csv", metrics, FIELDS)
    summary = {
        "observation_rows": len(observations),
        "source_usable_sample_count": len(usable_samples),
        "model_configurations": len({(row["model_name"], row["model_version"], row["preprocessing_id"]) for row in observations}),
        "all_scope_metrics": [row for row in metrics if row["scope"] == "all"],
    }
    write_json(args.results_dir / "ocr_metrics_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

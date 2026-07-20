#!/usr/bin/env python3
"""Measure train/test label overlap and OCR quality on seen versus unseen labels."""

from __future__ import annotations

import argparse
import collections
import statistics
from pathlib import Path

from benchmark_common import DEFAULT_DATA_DIR, DEFAULT_RESULTS_DIR, read_csv, write_csv, write_json


METRIC_FIELDS = [
    "model_name", "model_version", "preprocessing_id", "label_novelty", "rows",
    "exact_matches", "exact_accuracy", "mean_character_error_rate", "empty_rate",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("observations", nargs="*", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_DATA_DIR / "dataset_manifest.csv")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR / "analysis")
    return parser.parse_args()


def metric_row(key: tuple[str, str, str, str], rows: list[dict[str, str]]) -> dict[str, object]:
    model_name, model_version, preprocessing_id, novelty = key
    count = len(rows)
    exact = sum(int(row.get("exact_match") or 0) for row in rows)
    return {
        "model_name": model_name,
        "model_version": model_version,
        "preprocessing_id": preprocessing_id,
        "label_novelty": novelty,
        "rows": count,
        "exact_matches": exact,
        "exact_accuracy": round(exact / count, 8),
        "mean_character_error_rate": round(
            statistics.fmean(float(row.get("normalized_edit_distance") or 0) for row in rows), 8
        ),
        "empty_rate": round(
            sum(int(row.get("empty_output") or 0) for row in rows) / count, 8
        ),
    }


def main() -> int:
    args = parse_args()
    manifest = read_csv(args.manifest)
    usable = [row for row in manifest if row.get("ground_truth_usable") == "1"]
    train = [row for row in usable if row["split"] == "train"]
    test = [row for row in usable if row["split"] == "test"]
    train_labels = {row["ground_truth_compact"] for row in train}
    test_labels = {row["ground_truth_compact"] for row in test}
    novelty_by_sample = {
        row["sample_id"]: (
            "seen_in_train" if row["ground_truth_compact"] in train_labels else "unseen_in_train"
        )
        for row in test
    }

    grouped: dict[tuple[str, str, str, str], list[dict[str, str]]] = collections.defaultdict(list)
    files = args.observations or sorted(args.results_dir.glob("ocr_*_raw_all.csv"))
    for path in files:
        for row in read_csv(path):
            if row.get("sample_id") not in novelty_by_sample:
                continue
            key = (
                row["model_name"], row["model_version"], row["preprocessing_id"],
                novelty_by_sample[row["sample_id"]],
            )
            grouped[key].append(row)
    metrics = [metric_row(key, rows) for key, rows in sorted(grouped.items())]
    write_csv(args.output_dir / "ocr_metrics_by_test_label_novelty.csv", metrics, METRIC_FIELDS)

    test_seen = [row for row in test if row["ground_truth_compact"] in train_labels]
    test_unseen = [row for row in test if row["ground_truth_compact"] not in train_labels]
    test_frequency = collections.Counter(row["ground_truth_compact"] for row in test)
    summary = {
        "usable_train_rows": len(train),
        "usable_test_rows": len(test),
        "unique_train_labels": len(train_labels),
        "unique_test_labels": len(test_labels),
        "unique_label_overlap": len(train_labels & test_labels),
        "unique_test_labels_unseen_in_train": len(test_labels - train_labels),
        "test_rows_seen_label": len(test_seen),
        "test_rows_unseen_label": len(test_unseen),
        "test_seen_label_rate": len(test_seen) / max(len(test), 1),
        "most_repeated_test_labels": [
            {"label": label, "rows": count}
            for label, count in test_frequency.most_common(20)
        ],
        "primary_ocr_files": [path.name for path in files],
        "metrics_file": "ocr_metrics_by_test_label_novelty.csv",
    }
    write_json(args.output_dir / "label_novelty_summary.json", summary)
    print(args.output_dir / "label_novelty_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

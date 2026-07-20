#!/usr/bin/env python3
"""Profile RxHandBD images and explain current OCR failure patterns."""

from __future__ import annotations

import argparse
import collections
import statistics
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from benchmark_common import (
    DEFAULT_ARTIFACTS_DIR,
    DEFAULT_DATA_DIR,
    DEFAULT_RESULTS_DIR,
    compact_text,
    read_csv,
    write_csv,
    write_json,
)


PROFILE_FIELDS = [
    "sample_id", "image_id", "split", "ground_truth_raw", "label_length",
    "token_count", "width", "height", "gray_p05", "gray_p50", "gray_p95",
    "otsu_threshold", "ink_fraction", "ink_bbox_x", "ink_bbox_y",
    "ink_bbox_width", "ink_bbox_height", "ink_bbox_width_fraction",
    "ink_bbox_height_fraction", "ink_bbox_area_fraction", "ink_contrast",
    "laplacian_variance", "source_usable",
]

FAILURE_FIELDS = [
    "model_name", "sample_id", "image_id", "split", "ground_truth", "ocr_output",
    "exact_match", "edit_distance", "character_error_rate", "failure_type",
    "label_length", "ink_bbox_area_fraction", "ink_contrast", "laplacian_variance",
    "ocr_confidence", "latency_ms", "source_usable",
]

GROUP_FIELDS = [
    "model_name", "dimension", "bucket", "rows", "exact_matches",
    "exact_accuracy", "mean_character_error_rate", "empty_rate",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("observations", nargs="*", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_DATA_DIR / "dataset_manifest.csv")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR / "analysis")
    parser.add_argument("--representatives-per-model", type=int, default=25)
    return parser.parse_args()


def otsu_threshold(gray: np.ndarray) -> int:
    histogram = np.bincount(gray.reshape(-1), minlength=256).astype(np.float64)
    total = gray.size
    cumulative_count = np.cumsum(histogram)
    cumulative_sum = np.cumsum(histogram * np.arange(256))
    global_sum = cumulative_sum[-1]
    denominator = cumulative_count * (total - cumulative_count)
    denominator[denominator == 0] = 1
    between = (global_sum * cumulative_count - cumulative_sum * total) ** 2 / denominator
    return int(np.argmax(between[:-1]))


def retained_ink_mask(gray: np.ndarray, threshold: int) -> np.ndarray:
    raw_mask = (gray <= threshold).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(raw_mask, connectivity=8)
    minimum_area = max(8, int(gray.size * 0.00004))
    keep = np.zeros_like(raw_mask, dtype=bool)
    for component in range(1, count):
        if int(stats[component, cv2.CC_STAT_AREA]) >= minimum_area:
            keep |= labels == component
    return keep


def image_profile(row: dict[str, str]) -> dict[str, object]:
    with Image.open(row["image_path"]) as source:
        gray = np.asarray(source.convert("L"), dtype=np.uint8)
    height, width = gray.shape
    threshold = otsu_threshold(gray)
    mask = retained_ink_mask(gray, threshold)
    ys, xs = np.where(mask)
    if len(xs):
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        y0, y1 = int(ys.min()), int(ys.max()) + 1
    else:
        x0 = x1 = y0 = y1 = 0
    bbox_width = x1 - x0
    bbox_height = y1 - y0
    background = gray[~mask]
    ink = gray[mask]
    background_median = float(np.median(background)) if background.size else 255.0
    ink_median = float(np.median(ink)) if ink.size else background_median
    normalized_label = compact_text(row["ground_truth_raw"])
    return {
        "sample_id": row["sample_id"],
        "image_id": row["image_id"],
        "split": row["split"],
        "ground_truth_raw": row["ground_truth_raw"],
        "label_length": len(normalized_label),
        "token_count": len(str(row["ground_truth_raw"]).split()),
        "width": width,
        "height": height,
        "gray_p05": round(float(np.percentile(gray, 5)), 3),
        "gray_p50": round(float(np.percentile(gray, 50)), 3),
        "gray_p95": round(float(np.percentile(gray, 95)), 3),
        "otsu_threshold": threshold,
        "ink_fraction": round(float(mask.mean()), 6),
        "ink_bbox_x": x0,
        "ink_bbox_y": y0,
        "ink_bbox_width": bbox_width,
        "ink_bbox_height": bbox_height,
        "ink_bbox_width_fraction": round(bbox_width / max(width, 1), 6),
        "ink_bbox_height_fraction": round(bbox_height / max(height, 1), 6),
        "ink_bbox_area_fraction": round(
            (bbox_width * bbox_height) / max(width * height, 1), 6
        ),
        "ink_contrast": round(background_median - ink_median, 3),
        "laplacian_variance": round(
            float(cv2.Laplacian(gray, cv2.CV_64F).var()), 3
        ),
        "source_usable": int(row.get("ground_truth_usable") == "1"),
    }


def failure_type(ground_truth: str, output: str, edit_distance: int) -> str:
    expected = compact_text(ground_truth)
    actual = compact_text(output)
    if not actual:
        return "empty"
    if actual == expected:
        return "exact"
    if edit_distance == 1:
        return "single_edit"
    ratio = len(actual) / max(len(expected), 1)
    if ratio < 0.60:
        return "severe_under_read"
    if ratio > 1.40:
        return "severe_over_read"
    return "multi_edit_similar_length"


def bucket_for(dimension: str, row: dict[str, object]) -> str:
    if dimension == "label_length":
        value = int(row[dimension])
        return "1-5" if value <= 5 else "6-8" if value <= 8 else "9+"
    if dimension == "ink_bbox_area_fraction":
        value = float(row[dimension])
        return "<0.25" if value < 0.25 else "0.25-0.50" if value < 0.50 else ">=0.50"
    if dimension == "ink_contrast":
        value = float(row[dimension])
        return "<80" if value < 80 else "80-140" if value < 140 else ">=140"
    if dimension == "laplacian_variance":
        value = float(row[dimension])
        return "<4" if value < 4 else "4-10" if value < 10 else ">=10"
    raise ValueError(dimension)


def aggregate_group(model_name: str, dimension: str, bucket: str, rows: list[dict[str, object]]) -> dict[str, object]:
    count = len(rows)
    exact = sum(int(row["exact_match"]) for row in rows)
    return {
        "model_name": model_name,
        "dimension": dimension,
        "bucket": bucket,
        "rows": count,
        "exact_matches": exact,
        "exact_accuracy": round(exact / count, 8),
        "mean_character_error_rate": round(
            statistics.fmean(float(row["character_error_rate"]) for row in rows), 8
        ),
        "empty_rate": round(
            sum(row["failure_type"] == "empty" for row in rows) / count, 8
        ),
    }


def describe(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "min": round(ordered[0], 6),
        "median": round(statistics.median(ordered), 6),
        "mean": round(statistics.fmean(ordered), 6),
        "p95": round(float(np.percentile(ordered, 95)), 6),
        "max": round(ordered[-1], 6),
    }


def main() -> int:
    args = parse_args()
    manifest = [row for row in read_csv(args.manifest) if row.get("image_valid") == "1"]
    profiles = [image_profile(row) for row in manifest]
    profile_by_sample = {str(row["sample_id"]): row for row in profiles}
    write_csv(args.output_dir / "image_profiles.csv", profiles, PROFILE_FIELDS)

    canonical_paths = args.observations or sorted(args.results_dir.glob("ocr_*_raw_all.csv"))
    observations: list[dict[str, object]] = []
    for path in canonical_paths:
        for row in read_csv(path):
            profile = profile_by_sample[row["sample_id"]]
            distance = int(row.get("edit_distance") or 0)
            observations.append({
                "model_name": row["model_name"],
                "sample_id": row["sample_id"],
                "image_id": row["image_id"],
                "split": row["split"],
                "ground_truth": row["ground_truth_raw"],
                "ocr_output": row["ocr_output_raw"],
                "exact_match": int(row.get("exact_match") or 0),
                "edit_distance": distance,
                "character_error_rate": float(row.get("normalized_edit_distance") or 0),
                "failure_type": failure_type(
                    row["ground_truth_raw"], row["ocr_output_raw"], distance
                ),
                "label_length": profile["label_length"],
                "ink_bbox_area_fraction": profile["ink_bbox_area_fraction"],
                "ink_contrast": profile["ink_contrast"],
                "laplacian_variance": profile["laplacian_variance"],
                "ocr_confidence": row.get("ocr_confidence", ""),
                "latency_ms": row.get("latency_ms", ""),
                "source_usable": profile["source_usable"],
            })
    write_csv(args.output_dir / "ocr_failure_observations.csv", observations, FAILURE_FIELDS)

    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = collections.defaultdict(list)
    dimensions = (
        "label_length", "ink_bbox_area_fraction", "ink_contrast", "laplacian_variance"
    )
    scored_observations = [row for row in observations if row["source_usable"]]
    for row in scored_observations:
        for dimension in dimensions:
            grouped[(str(row["model_name"]), dimension, bucket_for(dimension, row))].append(row)
    grouped_rows = [
        aggregate_group(model, dimension, bucket, rows)
        for (model, dimension, bucket), rows in sorted(grouped.items())
    ]
    write_csv(args.output_dir / "ocr_metrics_by_image_feature.csv", grouped_rows, GROUP_FIELDS)

    representatives: list[dict[str, object]] = []
    for model in sorted({str(row["model_name"]) for row in observations}):
        failures = [
            row for row in scored_observations
            if row["model_name"] == model and not row["exact_match"]
        ]
        failures.sort(key=lambda row: (
            -float(row["character_error_rate"]),
            str(row["sample_id"]),
        ))
        representatives.extend(failures[:args.representatives_per_model])
    write_csv(args.output_dir / "representative_ocr_failures.csv", representatives, FAILURE_FIELDS)

    usable_ids = {
        row["sample_id"] for row in manifest if row.get("ground_truth_usable") == "1"
    }
    exact_by_sample: dict[str, set[str]] = collections.defaultdict(set)
    for row in scored_observations:
        if row["exact_match"]:
            exact_by_sample[str(row["sample_id"])].add(str(row["model_name"]))
    models = sorted({str(row["model_name"]) for row in observations})
    exact_sets = {
        model: {sample for sample, winners in exact_by_sample.items() if model in winners}
        for model in models
    }
    complementarity = []
    for model in models:
        other_union = set().union(*(exact_sets[other] for other in models if other != model))
        complementarity.append({
            "model_name": model,
            "exact_samples": len(exact_sets[model]),
            "unique_exact_samples": len(exact_sets[model] - other_union),
            "missed_but_another_model_exact": len(other_union - exact_sets[model]),
        })
    write_csv(
        args.output_dir / "model_complementarity.csv",
        complementarity,
        ["model_name", "exact_samples", "unique_exact_samples", "missed_but_another_model_exact"],
    )

    usable_profiles = [row for row in profiles if row["source_usable"]]
    failure_counts = collections.Counter(
        (str(row["model_name"]), str(row["failure_type"])) for row in scored_observations
    )
    summary = {
        "profiled_images": len(profiles),
        "source_usable_images": len(usable_profiles),
        "canonical_ocr_files": [path.name for path in canonical_paths],
        "image_characteristics": {
            key: describe([float(row[key]) for row in usable_profiles])
            for key in (
                "ink_fraction", "ink_bbox_width_fraction", "ink_bbox_height_fraction",
                "ink_bbox_area_fraction", "ink_contrast", "laplacian_variance",
            )
        },
        "label_length": describe([float(row["label_length"]) for row in usable_profiles]),
        "failure_type_counts": {
            model: {
                failure: failure_counts[(model, failure)]
                for failure in sorted({item[1] for item in failure_counts if item[0] == model})
            }
            for model in models
        },
        "oracle_exact": {
            "samples_exact_in_any_model": len(exact_by_sample),
            "accuracy": len(exact_by_sample) / max(len(usable_ids), 1),
        },
        "outputs": {
            "profiles": "image_profiles.csv",
            "failure_observations": "ocr_failure_observations.csv",
            "metrics_by_feature": "ocr_metrics_by_image_feature.csv",
            "representative_failures": "representative_ocr_failures.csv",
            "model_complementarity": "model_complementarity.csv",
        },
    }
    write_json(args.output_dir / "image_and_failure_analysis_summary.json", summary)
    print(args.output_dir / "image_and_failure_analysis_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

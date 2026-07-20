#!/usr/bin/env python3
"""Evaluate the deterministic page-segmentation integration fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

from benchmark_common import compact_text, levenshtein, read_csv, write_csv, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--regions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def contains_center(ground_truth: dict[str, str], region: dict[str, str]) -> bool:
    center_x = int(region["x"]) + int(region["width"]) / 2
    center_y = int(region["y"]) + int(region["height"]) / 2
    left = int(ground_truth["x"])
    top = int(ground_truth["y"])
    return (
        left <= center_x <= left + int(ground_truth["width"])
        and top <= center_y <= top + int(ground_truth["height"])
    )


def main() -> int:
    args = parse_args()
    expected = sorted(read_csv(args.ground_truth), key=lambda row: int(row["reading_order"]))
    regions = sorted(read_csv(args.regions), key=lambda row: int(row["reading_order"]))
    assignments: list[dict[str, object]] = []
    used_region_ids: set[str] = set()

    for target in expected:
        compatible = [
            region for region in regions
            if region["region_id"] not in used_region_ids and contains_center(target, region)
        ]
        if compatible:
            region = min(
                compatible,
                key=lambda item: abs(int(item["reading_order"]) - int(target["reading_order"])),
            )
            used_region_ids.add(region["region_id"])
            output = region["ocr_output_raw"]
            status = "matched"
        else:
            region = {}
            output = ""
            status = "missed"
        expected_key = compact_text(target["ground_truth"])
        output_key = compact_text(output)
        distance = levenshtein(output_key, expected_key)
        assignments.append({
            "expected_order": target["reading_order"],
            "expected_line": target["line_index"],
            "image_id": target["image_id"],
            "ground_truth": target["ground_truth"],
            "region_id": region.get("region_id", ""),
            "detected_order": region.get("reading_order", ""),
            "detected_line": region.get("line_index", ""),
            "ocr_output": output,
            "detection_status": status,
            "exact_match": int(bool(expected_key) and expected_key == output_key),
            "edit_distance": distance,
            "character_error_rate": round(distance / max(len(expected_key), 1), 6),
        })

    detected = sum(row["detection_status"] == "matched" for row in assignments)
    exact = sum(int(row["exact_match"]) for row in assignments)
    summary = {
        "ground_truth_regions": len(expected),
        "detected_regions": len(regions),
        "matched_regions": detected,
        "detection_recall": detected / max(len(expected), 1),
        "detection_precision": detected / max(len(regions), 1),
        "reading_order_exact": int(
            detected == len(expected)
            and all(
                int(row["expected_order"]) == int(row["detected_order"])
                for row in assignments
            )
        ),
        "line_assignment_exact": int(
            detected == len(expected)
            and all(
                int(row["expected_line"]) == int(row["detected_line"])
                for row in assignments
            )
        ),
        "ocr_exact_matches": exact,
        "ocr_exact_accuracy": exact / max(len(expected), 1),
        "mean_character_error_rate": (
            sum(float(row["character_error_rate"]) for row in assignments)
            / max(len(assignments), 1)
        ),
        "scope": "synthetic layout assembled from real RxHandBD word images; integration fixture only",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.output_dir / "aligned_regions.csv",
        assignments,
        (
            "expected_order", "expected_line", "image_id", "ground_truth", "region_id",
            "detected_order", "detected_line", "ocr_output", "detection_status",
            "exact_match", "edit_distance", "character_error_rate",
        ),
    )
    write_json(args.output_dir / "evaluation_summary.json", summary)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build deterministic, disjoint train-only OCR selection manifests."""

from __future__ import annotations

import argparse
import collections
import hashlib
import math
from pathlib import Path

from benchmark_common import (
    DEFAULT_ARTIFACTS_DIR,
    DEFAULT_DATA_DIR,
    DEFAULT_RESULTS_DIR,
    read_csv,
    write_csv,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_DATA_DIR / "dataset_manifest.csv")
    parser.add_argument(
        "--profiles",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "analysis" / "image_profiles.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_ARTIFACTS_DIR / "experiments" / "selection",
    )
    parser.add_argument("--screening-size", type=int, default=600)
    parser.add_argument("--validation-size", type=int, default=1000)
    parser.add_argument("--seed", default="data3-ocr-selection-v2")
    return parser.parse_args()


def stable_order(seed: str, sample_id: str) -> str:
    return hashlib.sha256(f"{seed}\x1f{sample_id}".encode()).hexdigest()


def feature_bucket(profile: dict[str, str]) -> str:
    length = int(float(profile["label_length"]))
    length_bucket = "short" if length <= 5 else "medium" if length <= 8 else "long"
    contrast = float(profile["ink_contrast"])
    contrast_bucket = "low" if contrast < 80 else "medium" if contrast < 140 else "high"
    area = float(profile["ink_bbox_area_fraction"])
    area_bucket = "small" if area < 0.25 else "medium" if area < 0.50 else "large"
    return f"{length_bucket}|{contrast_bucket}|{area_bucket}"


def proportional_quotas(groups: dict[str, list[dict[str, str]]], target: int) -> dict[str, int]:
    available = sum(len(rows) for rows in groups.values())
    if target > available:
        raise ValueError(f"requested {target} rows from only {available} available")
    raw = {key: target * len(rows) / available for key, rows in groups.items()}
    quotas = {key: min(len(groups[key]), math.floor(value)) for key, value in raw.items()}
    remaining = target - sum(quotas.values())
    priority = sorted(
        groups,
        key=lambda key: (-(raw[key] - quotas[key]), key),
    )
    while remaining:
        progressed = False
        for key in priority:
            if quotas[key] < len(groups[key]):
                quotas[key] += 1
                remaining -= 1
                progressed = True
                if not remaining:
                    break
        if not progressed:
            raise RuntimeError("unable to fill proportional quotas")
    return quotas


def select(
    rows: list[dict[str, str]],
    profile_by_sample: dict[str, dict[str, str]],
    size: int,
    seed: str,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    groups: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for row in rows:
        groups[feature_bucket(profile_by_sample[row["sample_id"]])].append(row)
    for group_rows in groups.values():
        group_rows.sort(key=lambda row: stable_order(seed, row["sample_id"]))
    quotas = proportional_quotas(groups, size)
    selected = [row for key, group_rows in groups.items() for row in group_rows[:quotas[key]]]
    selected.sort(key=lambda row: (row["image_id"], row["sample_id"]))
    return selected, dict(sorted(quotas.items()))


def main() -> int:
    args = parse_args()
    manifest = read_csv(args.manifest)
    profiles = read_csv(args.profiles)
    profile_by_sample = {row["sample_id"]: row for row in profiles}
    eligible = [
        row for row in manifest
        if row.get("split") == "train"
        and row.get("image_valid") == "1"
        and row.get("ground_truth_usable") == "1"
        and row.get("ground_truth_compact")
    ]
    screening, screening_quotas = select(
        eligible, profile_by_sample, args.screening_size, f"{args.seed}:screening"
    )
    screening_ids = {row["sample_id"] for row in screening}
    remaining = [row for row in eligible if row["sample_id"] not in screening_ids]
    validation, validation_quotas = select(
        remaining, profile_by_sample, args.validation_size, f"{args.seed}:validation"
    )
    validation_ids = {row["sample_id"] for row in validation}
    finetune = [row for row in eligible if row["sample_id"] not in validation_ids]
    finetune_ids = {row["sample_id"] for row in finetune}
    fields = list(manifest[0])
    screening_path = args.output_dir / f"train_screening_manifest_{len(screening)}.csv"
    validation_path = args.output_dir / f"train_validation_manifest_{len(validation)}.csv"
    finetune_path = args.output_dir / f"train_finetune_manifest_{len(finetune)}.csv"
    write_csv(screening_path, screening, fields)
    write_csv(validation_path, validation, fields)
    write_csv(finetune_path, finetune, fields)
    summary = {
        "seed": args.seed,
        "eligible_train_rows": len(eligible),
        "screening_rows": len(screening),
        "validation_rows": len(validation),
        "finetune_rows": len(finetune),
        "screening_validation_overlap": len(screening_ids & validation_ids),
        "finetune_validation_overlap": len(finetune_ids & validation_ids),
        "official_test_rows_used": 0,
        "stratification": ["label_length", "ink_contrast", "ink_bbox_area_fraction"],
        "screening_quotas": screening_quotas,
        "validation_quotas": validation_quotas,
        "screening_manifest": str(screening_path),
        "validation_manifest": str(validation_path),
        "finetune_manifest": str(finetune_path),
    }
    write_json(args.output_dir / "selection_manifest_summary.json", summary)
    print(args.output_dir / "selection_manifest_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

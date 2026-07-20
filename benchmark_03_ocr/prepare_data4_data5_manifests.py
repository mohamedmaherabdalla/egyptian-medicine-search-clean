#!/usr/bin/env python3
"""Audit local data4/data5 exports and build canonical OCR manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from benchmark_common import (
    catalog_alias_index,
    compact_text,
    load_catalog_families,
    normalize_text,
    read_csv,
    stable_id,
    write_csv,
    write_json,
)


MANIFEST_FIELDS = (
    "sample_id", "dataset_name", "dataset_version", "image_id", "split",
    "sample_level", "language", "ground_truth_raw", "ground_truth_normalized",
    "ground_truth_compact", "image_path", "image_valid", "image_width",
    "image_height", "source_representation", "ground_truth_usable", "exclusion_reason",
)

MAPPING_FIELDS = (
    "sample_id", "dataset_name", "image_id", "split", "ground_truth_raw",
    "mapping_status", "expected_family_key", "expected_family_name",
    "eligible_for_search_benchmark",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data4-root", type=Path, default=Path(__file__).resolve().parents[2] / "data4")
    parser.add_argument("--data5-root", type=Path, default=Path(__file__).resolve().parents[2] / "data5")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "data" / "02_data4_data5",
    )
    return parser.parse_args()


def pixel_hash(path: Path) -> str:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
    digest = hashlib.sha256()
    digest.update(f"{rgb.width}x{rgb.height}:RGB:".encode())
    digest.update(rgb.tobytes())
    return digest.hexdigest()


def normalized_ink(path: Path) -> np.ndarray:
    with Image.open(path) as source:
        gray = np.asarray(source.convert("L"))
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    points = cv2.findNonZero(mask)
    if points is None:
        return np.zeros((32, 96), dtype=np.uint8)
    x, y, width, height = cv2.boundingRect(points)
    crop = mask[y:y + height, x:x + width]
    scale = min(88 / max(width, 1), 26 / max(height, 1))
    resized = cv2.resize(
        crop,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    canvas = np.zeros((32, 96), dtype=np.uint8)
    top = (32 - resized.shape[0]) // 2
    left = (96 - resized.shape[1]) // 2
    canvas[top:top + resized.shape[0], left:left + resized.shape[1]] = resized
    return canvas


def ink_similarity(left: Path, right: Path) -> float:
    first = normalized_ink(left).astype(np.float32) / 255.0
    second = normalized_ink(right).astype(np.float32) / 255.0
    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    return float(np.sum(first * second) / denominator) if denominator else 0.0


def image_info(path: Path) -> tuple[int, int, bool]:
    try:
        with Image.open(path) as image:
            image.load()
            return image.width, image.height, image.width > 0 and image.height > 0
    except Exception:
        return 0, 0, False


def manifest_row(
    *,
    dataset_name: str,
    image_id: str,
    split: str,
    label: str,
    image_path: Path,
    representation: str,
) -> dict[str, object]:
    width, height, valid = image_info(image_path)
    return {
        "sample_id": stable_id(dataset_name, split, image_id),
        "dataset_name": dataset_name,
        "dataset_version": "local_export_1",
        "image_id": image_id,
        "split": split,
        "sample_level": "word",
        "language": "English",
        "ground_truth_raw": label,
        "ground_truth_normalized": normalize_text(label),
        "ground_truth_compact": compact_text(label),
        "image_path": str(image_path.resolve()),
        "image_valid": int(valid),
        "image_width": width,
        "image_height": height,
        "source_representation": representation,
        "ground_truth_usable": int(bool(compact_text(label))),
        "exclusion_reason": "" if compact_text(label) else "blank_ground_truth",
    }


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    processed = args.data4_root / "data" / "processed"
    mapping = json.loads((processed / "mapping.json").read_text(encoding="utf-8"))
    inverse_mapping = {str(value): key for key, value in mapping.items()}
    layouts = (
        (
            "train", processed / "train" / "images", processed / "train_labels.csv",
            args.data5_root / "Training" / "training_words",
            args.data5_root / "Training" / "training_labels.csv",
        ),
        (
            "validation", processed / "val" / "images", processed / "val_labels.csv",
            args.data5_root / "Validation" / "validation_words",
            args.data5_root / "Validation" / "validation_labels.csv",
        ),
        (
            "test", processed / "test" / "images", processed / "test_labels.csv",
            args.data5_root / "Testing" / "testing_words",
            args.data5_root / "Testing" / "testing_labels.csv",
        ),
    )

    data4_rows: list[dict[str, object]] = []
    data5_rows: list[dict[str, object]] = []
    pair_rows: list[dict[str, object]] = []
    label_mismatches: list[dict[str, object]] = []
    for split, image_dir4, labels4_path, image_dir5, labels5_path in layouts:
        labels4 = {row["IMAGE"].strip(): row["MEDICINE_NAME"].strip() for row in read_csv(labels4_path)}
        labels5 = {row["IMAGE"].strip(): row["MEDICINE_NAME"].strip() for row in read_csv(labels5_path)}
        for image_id in sorted(set(labels4) | set(labels5), key=lambda value: int(Path(value).stem)):
            decoded4 = inverse_mapping.get(labels4.get(image_id, ""), "")
            label5 = labels5.get(image_id, "")
            path4 = image_dir4 / image_id
            path5 = image_dir5 / image_id
            data4_rows.append(manifest_row(
                dataset_name="data4_processed84",
                image_id=image_id,
                split=split,
                label=decoded4,
                image_path=path4,
                representation="processed_84x84",
            ))
            data5_rows.append(manifest_row(
                dataset_name="data5_original_words",
                image_id=image_id,
                split=split,
                label=label5,
                image_path=path5,
                representation="original_variable_size",
            ))
            if decoded4 != label5:
                label_mismatches.append({
                    "split": split,
                    "image_id": image_id,
                    "data4_label": decoded4,
                    "data5_label": label5,
                })
            similarity = ink_similarity(path4, path5) if path4.is_file() and path5.is_file() else 0.0
            pair_rows.append({
                "split": split,
                "image_id": image_id,
                "data4_label": decoded4,
                "data5_label": label5,
                "labels_equal": int(decoded4 == label5),
                "pixel_hash_equal": int(
                    path4.is_file() and path5.is_file() and pixel_hash(path4) == pixel_hash(path5)
                ),
                "normalized_ink_similarity": round(similarity, 6),
            })

    write_csv(args.output_dir / "data4_manifest.csv", data4_rows, MANIFEST_FIELDS)
    write_csv(args.output_dir / "data5_manifest.csv", data5_rows, MANIFEST_FIELDS)
    combined_rows = [*data4_rows, *data5_rows]
    combined_rows.sort(key=lambda row: (str(row["dataset_name"]), str(row["split"]), str(row["image_id"])))
    write_csv(args.output_dir / "combined_manifest.csv", combined_rows, MANIFEST_FIELDS)

    families = load_catalog_families()
    family_by_key = {family.key: family for family in families}
    alias_index = catalog_alias_index(families)
    catalog_mapping: list[dict[str, object]] = []
    for row in combined_rows:
        matches = sorted(alias_index.get(compact_text(row["ground_truth_raw"]), ()))
        unique = len(matches) == 1
        family_key = matches[0] if unique else ""
        catalog_mapping.append({
            "sample_id": row["sample_id"],
            "dataset_name": row["dataset_name"],
            "image_id": row["image_id"],
            "split": row["split"],
            "ground_truth_raw": row["ground_truth_raw"],
            "mapping_status": "exact_unique" if unique else ("exact_ambiguous" if matches else "unmatched"),
            "expected_family_key": family_key,
            "expected_family_name": family_by_key[family_key].name if family_key else "",
            "eligible_for_search_benchmark": int(unique),
        })
    write_csv(args.output_dir / "catalog_mapping.csv", catalog_mapping, MAPPING_FIELDS)
    write_csv(
        args.output_dir / "representation_pair_audit.csv",
        pair_rows,
        (
            "split", "image_id", "data4_label", "data5_label", "labels_equal",
            "pixel_hash_equal", "normalized_ink_similarity",
        ),
    )
    write_csv(
        args.output_dir / "label_mismatches.csv",
        label_mismatches,
        ("split", "image_id", "data4_label", "data5_label"),
    )

    similarities = [float(row["normalized_ink_similarity"]) for row in pair_rows]
    summary = {
        "data4_rows": len(data4_rows),
        "data5_rows": len(data5_rows),
        "split_counts": dict(Counter(str(row["split"]) for row in data5_rows)),
        "classes": len({str(row["ground_truth_raw"]) for row in data5_rows}),
        "egypt_catalog_exact_classes": len({
            str(row["ground_truth_raw"])
            for row, mapping_row in zip(combined_rows, catalog_mapping)
            if mapping_row["eligible_for_search_benchmark"] == 1
        }),
        "egypt_catalog_eligible_rows": sum(
            int(row["eligible_for_search_benchmark"]) for row in catalog_mapping
        ),
        "label_mismatches": len(label_mismatches),
        "exact_pixel_pairs": sum(int(row["pixel_hash_equal"]) for row in pair_rows),
        "mean_normalized_ink_similarity": sum(similarities) / max(len(similarities), 1),
        "pairs_with_similarity_at_least_0_70": sum(value >= 0.70 for value in similarities),
        "interpretation": (
            "data4 is an 84x84 processed representation of the same labeled examples "
            "stored at original variable sizes in data5; results are paired, not independent"
        ),
    }
    write_json(args.output_dir / "dataset_audit_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if not label_mismatches else 2


if __name__ == "__main__":
    raise SystemExit(main())

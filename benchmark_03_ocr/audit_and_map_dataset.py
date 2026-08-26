#!/usr/bin/env python3
"""Audit RxHandBD and conservatively resolve labels to Egyptian drug families."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

from PIL import Image

from benchmark_common import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_DATA_DIR,
    DEFAULT_DATASET_ROOT,
    catalog_alias_index,
    compact_text,
    file_sha256,
    load_catalog_families,
    load_dataset_rows,
    medicine_head,
    normalize_text,
    read_csv,
    repository_path,
    similarity,
    stable_id,
    write_csv,
    write_json,
)


DATASET_FIELDS = [
    "sample_id", "dataset_name", "dataset_version", "image_id", "split",
    "sample_level", "language", "image_path", "ground_truth_raw",
    "ground_truth_normalized", "ground_truth_compact", "image_sha256",
    "pixel_sha256", "width", "height", "mode", "image_valid", "raw_copy_equal",
    "ground_truth_usable", "exclusion_reason",
]

MAPPING_FIELDS = [
    "sample_id", "image_id", "split", "ground_truth_raw", "ground_truth_normalized",
    "mapping_status", "mapping_method", "expected_family_key", "expected_family_name",
    "expected_candidate_ids", "expected_ingredients", "family_count", "best_similarity",
    "second_similarity", "review_candidate_1", "review_candidate_2", "review_candidate_3",
    "eligible_for_search_benchmark", "mapping_note",
]

REVIEW_FIELDS = [
    "ground_truth_normalized", "example_ground_truth_raw", "occurrences", "splits",
    "mapping_status", "best_similarity", "second_similarity", "review_candidate_1",
    "review_candidate_2", "review_candidate_3", "human_decision", "approved_family_key",
    "reviewer", "review_note",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--skip-image-verification", action="store_true")
    return parser.parse_args()


def char_ngrams(value: str, size: int) -> set[str]:
    if len(value) < size:
        return {value} if value else set()
    return {value[index:index + size] for index in range(len(value) - size + 1)}


def build_suggestion_index(families) -> dict[str, object]:
    gram_index: dict[str, set[str]] = collections.defaultdict(set)
    first_length_index: dict[tuple[str, int], set[str]] = collections.defaultdict(set)
    alias_keys: dict[str, tuple[str, ...]] = {}
    for family in families:
        keys = tuple(sorted({compact_text(alias) for alias in family.aliases if compact_text(alias)}))
        alias_keys[family.key] = keys
        for key in keys:
            for gram in char_ngrams(key, 3 if len(key) >= 5 else 2):
                gram_index[gram].add(family.key)
            first_length_index[(key[:1], len(key))].add(family.key)
    return {
        "gram_index": gram_index,
        "first_length_index": first_length_index,
        "alias_keys": alias_keys,
        "family_by_key": {family.key: family for family in families},
    }


def suggestion_candidates(label: str, suggestion_index: dict[str, object], limit: int = 100):
    query = compact_text(label)
    gram_index = suggestion_index["gram_index"]
    first_length_index = suggestion_index["first_length_index"]
    family_by_key = suggestion_index["family_by_key"]
    assert isinstance(gram_index, dict)
    assert isinstance(first_length_index, dict)
    assert isinstance(family_by_key, dict)
    size = 3 if len(query) >= 5 else 2
    overlap: collections.Counter[str] = collections.Counter()
    for gram in char_ngrams(query, size):
        overlap.update(gram_index.get(gram, ()))
    max_delta = max(2, round(len(query) * 0.35))
    for length in range(max(1, len(query) - max_delta), len(query) + max_delta + 1):
        overlap.update(first_length_index.get((query[:1], length), ()))
    ranked_keys = [key for key, _ in overlap.most_common(limit)]
    return [family_by_key[key] for key in ranked_keys]


def resolve_label(label: str, families, alias_index, suggestion_index) -> dict[str, object]:
    family_by_key = suggestion_index["family_by_key"]
    assert isinstance(family_by_key, dict)
    full_key = compact_text(label)
    head_key = compact_text(medicine_head(label))
    keys = [key for key in dict.fromkeys((full_key, head_key)) if key]
    exact_families: set[str] = set()
    exact_method = ""
    for index, key in enumerate(keys):
        found = alias_index.get(key, set())
        if found:
            exact_families.update(found)
            exact_method = "exact_normalized" if index == 0 else "exact_after_context_strip"

    if len(exact_families) == 1:
        family = family_by_key[next(iter(exact_families))]
        return {
            "mapping_status": "mapped_exact",
            "mapping_method": exact_method,
            "expected_family_key": family.key,
            "expected_family_name": family.name,
            "expected_candidate_ids": ";".join(family.candidate_ids),
            "expected_ingredients": ";".join(family.ingredients),
            "family_count": 1,
            "best_similarity": 1.0,
            "second_similarity": "",
            "eligible_for_search_benchmark": 1,
            "mapping_note": "Unique catalog family resolved without fuzzy inference.",
        }
    if len(exact_families) > 1:
        names = [family_by_key[key].name for key in sorted(exact_families)]
        return {
            "mapping_status": "ambiguous_exact",
            "mapping_method": exact_method,
            "expected_family_key": ";".join(sorted(exact_families)),
            "expected_family_name": ";".join(names),
            "expected_candidate_ids": "",
            "expected_ingredients": "",
            "family_count": len(exact_families),
            "best_similarity": 1.0,
            "second_similarity": 1.0,
            "eligible_for_search_benchmark": 0,
            "mapping_note": "The normalized label resolves to multiple commercial families.",
        }

    query = medicine_head(label) or label
    candidates = suggestion_candidates(query, suggestion_index)
    suggestions = sorted(
        ((max(similarity(query, alias) for alias in family.aliases[:16]), family) for family in candidates),
        key=lambda item: (-item[0], item[1].name),
    )[:3]
    best = suggestions[0][0] if suggestions else 0.0
    second = suggestions[1][0] if len(suggestions) > 1 else 0.0
    result: dict[str, object] = {
        "mapping_status": "review_fuzzy" if best >= 0.75 else "unresolved",
        "mapping_method": "fuzzy_suggestion_only",
        "expected_family_key": "",
        "expected_family_name": "",
        "expected_candidate_ids": "",
        "expected_ingredients": "",
        "family_count": 0,
        "best_similarity": round(best, 6),
        "second_similarity": round(second, 6),
        "eligible_for_search_benchmark": 0,
        "mapping_note": "Suggestion requires human review; fuzzy similarity never establishes ground truth.",
    }
    for index, (_, family) in enumerate(suggestions, 1):
        result[f"review_candidate_{index}"] = family.name
    return result


def main() -> int:
    args = parse_args()
    rows = load_dataset_rows(args.dataset_root)
    families = load_catalog_families(args.catalog)
    family_by_key = {family.key: family for family in families}
    alias_index = catalog_alias_index(families)
    suggestion_index = build_suggestion_index(families)
    ingredient_index: dict[str, set[str]] = collections.defaultdict(set)
    for family in families:
        for ingredient in family.ingredients:
            ingredient_key = compact_text(ingredient)
            if ingredient_key:
                ingredient_index[ingredient_key].add(family.key)
    raw_root = args.dataset_root / "RxHandBD-Raw"
    raw_image_dir = raw_root / "RxHand-Handwritten Prescription Word Image Dataset"
    raw_labels = {
        str(row.get("Images") or "").strip(): str(row.get("Text") or "").strip()
        for row in read_csv(raw_root / "Prescription_Labels.csv")
    }

    dataset_output = []
    mapping_output = []
    ingredient_output = []
    invalid_images = []
    official_hash_to_samples: dict[str, list[str]] = collections.defaultdict(list)
    label_disagreements = []
    mapping_cache: dict[str, dict[str, object]] = {}
    for row in rows:
        sample_id = stable_id("rxhandbd-v2", row.split, row.image_id)
        image_valid = False
        width = height = 0
        mode = ""
        image_hash = ""
        raw_copy_equal = False
        official_pixel_hash = ""
        raw_path = raw_image_dir / row.image_id
        try:
            image_hash = file_sha256(row.image_path)
            if args.skip_image_verification:
                image_valid = row.image_path.is_file()
                raw_copy_equal = raw_path.is_file()
            else:
                with Image.open(row.image_path) as image:
                    image.verify()
                with Image.open(row.image_path) as image:
                    width, height = image.size
                    mode = image.mode
                    pixels = image.convert("RGB").tobytes()
                    official_pixel_hash = hashlib.sha256(pixels).hexdigest()
                if raw_path.exists():
                    with Image.open(raw_path) as raw_image:
                        raw_pixels = raw_image.convert("RGB").tobytes()
                        raw_pixel_hash = hashlib.sha256(raw_pixels).hexdigest()
                    raw_copy_equal = raw_pixel_hash == official_pixel_hash
                official_hash_to_samples[official_pixel_hash].append(sample_id)
                image_valid = width > 0 and height > 0
            if args.skip_image_verification:
                official_hash_to_samples[image_hash].append(sample_id)
        except Exception as exc:  # audit output must record corrupt files instead of aborting
            invalid_images.append({"image_id": row.image_id, "error": repr(exc)})

        raw_label = raw_labels.get(row.image_id, "")
        if normalize_text(raw_label) != normalize_text(row.ground_truth_raw):
            label_disagreements.append({
                "image_id": row.image_id,
                "ml_label": row.ground_truth_raw,
                "raw_label": raw_label,
            })
        base = {
            "sample_id": sample_id,
            "dataset_name": "RxHandBD",
            "dataset_version": "2",
            "image_id": row.image_id,
            "split": row.split,
            "sample_level": "word",
            "language": "en",
            "image_path": str(row.image_path.resolve()),
            "ground_truth_raw": row.ground_truth_raw,
            "ground_truth_normalized": normalize_text(row.ground_truth_raw),
            "ground_truth_compact": compact_text(row.ground_truth_raw),
            "image_sha256": image_hash,
            "pixel_sha256": official_pixel_hash or image_hash,
            "width": width,
            "height": height,
            "mode": mode,
            "image_valid": int(image_valid),
            "raw_copy_equal": int(raw_copy_equal),
        }
        dataset_output.append(base)
        mapping_cache_key = normalize_text(row.ground_truth_raw)
        if mapping_cache_key not in mapping_cache:
            mapping_cache[mapping_cache_key] = resolve_label(
                row.ground_truth_raw,
                families,
                alias_index,
                suggestion_index,
            )
        mapped = mapping_cache[mapping_cache_key]
        mapping_output.append({
            "sample_id": sample_id,
            "image_id": row.image_id,
            "split": row.split,
            "ground_truth_raw": row.ground_truth_raw,
            "ground_truth_normalized": normalize_text(row.ground_truth_raw),
            **mapped,
        })
        if mapped["mapping_status"] != "mapped_exact":
            ingredient_keys = {
                key
                for candidate in (row.ground_truth_raw, medicine_head(row.ground_truth_raw))
                for key in (compact_text(candidate),)
                if key in ingredient_index
            }
            matched_families = sorted({
                family_key
                for ingredient_key in ingredient_keys
                for family_key in ingredient_index[ingredient_key]
            })
            if matched_families:
                ingredient_output.append({
                    "sample_id": sample_id,
                    "image_id": row.image_id,
                    "split": row.split,
                    "ground_truth_raw": row.ground_truth_raw,
                    "ground_truth_normalized": normalize_text(row.ground_truth_raw),
                    "ingredient_keys": ";".join(sorted(ingredient_keys)),
                    "relevant_family_count": len(matched_families),
                    "relevant_family_keys": ";".join(matched_families),
                    "relevant_family_names": ";".join(family_by_key[key].name for key in matched_families),
                    "benchmark_track": "ingredient_query_separate",
                })

    split_counts = collections.Counter(row.split for row in rows)
    mapping_counts = collections.Counter(str(row["mapping_status"]) for row in mapping_output)
    duplicate_groups = [samples for samples in official_hash_to_samples.values() if len(samples) > 1]
    duplicate_cross_split = []
    split_by_sample = {row["sample_id"]: row["split"] for row in dataset_output}
    label_by_sample = {row["sample_id"]: row["ground_truth_normalized"] for row in dataset_output}
    duplicate_label_conflicts = []
    for samples in duplicate_groups:
        splits = {split_by_sample[sample] for sample in samples}
        if len(splits) > 1:
            duplicate_cross_split.append(samples)
        labels = {label_by_sample[sample] for sample in samples}
        if len(labels) > 1:
            duplicate_label_conflicts.append(samples)
    conflict_samples = {
        sample_id
        for samples in duplicate_label_conflicts
        for sample_id in samples
    }
    for row in dataset_output:
        if not row["ground_truth_compact"]:
            row["ground_truth_usable"] = 0
            row["exclusion_reason"] = "blank_ground_truth"
        elif "?" in str(row["ground_truth_raw"]):
            row["ground_truth_usable"] = 0
            row["exclusion_reason"] = "uncertain_ground_truth_placeholder"
        elif not row["image_valid"]:
            row["ground_truth_usable"] = 0
            row["exclusion_reason"] = "invalid_image"
        elif row["sample_id"] in conflict_samples:
            row["ground_truth_usable"] = 0
            row["exclusion_reason"] = "duplicate_pixels_conflicting_ground_truth"
        else:
            row["ground_truth_usable"] = 1
            row["exclusion_reason"] = ""

    summary = {
        "dataset": "RxHandBD",
        "dataset_version": "2",
        "source_license": "CC BY 4.0 (declared by Mendeley dataset page)",
        "official_rows": len(rows),
        "split_counts": dict(sorted(split_counts.items())),
        "unique_image_ids": len({row.image_id for row in rows}),
        "unique_ground_truth_normalized": len({normalize_text(row.ground_truth_raw) for row in rows}),
        "blank_ground_truth": sum(not normalize_text(row.ground_truth_raw) for row in rows),
        "uncertain_ground_truth_placeholders": sum(
            "?" in row.ground_truth_raw and bool(compact_text(row.ground_truth_raw))
            for row in rows
        ),
        "invalid_images": invalid_images,
        "raw_copy_mismatches": sum(not row["raw_copy_equal"] for row in dataset_output),
        "label_disagreements": label_disagreements,
        "duplicate_image_hash_groups": len(duplicate_groups),
        "cross_split_duplicate_groups": duplicate_cross_split,
        "duplicate_label_conflict_groups": duplicate_label_conflicts,
        "duplicate_label_conflict_rows": len(conflict_samples),
        "ocr_observation_rows": sum(
            bool(row["image_valid"] and row["ground_truth_compact"])
            for row in dataset_output
        ),
        "ocr_scored_rows": sum(int(row["ground_truth_usable"]) for row in dataset_output),
        "catalog_rows_path": repository_path(args.catalog),
        "catalog_family_count": len(families),
        "mapping_counts": dict(sorted(mapping_counts.items())),
        "search_eligible_rows": sum(int(row["eligible_for_search_benchmark"]) for row in mapping_output),
        "search_eligible_test_rows": sum(
            row["split"] == "test" and int(row["eligible_for_search_benchmark"])
            for row in mapping_output
        ),
        "ingredient_query_rows": len(ingredient_output),
        "ingredient_query_unique_labels": len({row["ground_truth_normalized"] for row in ingredient_output}),
        "mapping_policy": "Only unique normalized exact matches are accepted automatically.",
    }

    write_csv(args.results_dir / "dataset_manifest.csv", dataset_output, DATASET_FIELDS)
    duplicate_rows = []
    for group_index, samples in enumerate(duplicate_groups, 1):
        for sample_id in samples:
            duplicate_rows.append({
                "duplicate_group": group_index,
                "sample_id": sample_id,
                "split": split_by_sample[sample_id],
                "ground_truth_normalized": label_by_sample[sample_id],
                "cross_split": int(samples in duplicate_cross_split),
                "label_conflict": int(samples in duplicate_label_conflicts),
            })
    write_csv(
        args.results_dir / "duplicate_image_audit.csv",
        duplicate_rows,
        [
            "duplicate_group", "sample_id", "split", "ground_truth_normalized",
            "cross_split", "label_conflict",
        ],
    )
    write_csv(args.results_dir / "catalog_mapping.csv", mapping_output, MAPPING_FIELDS)
    write_csv(
        args.results_dir / "ingredient_query_mapping.csv",
        ingredient_output,
        [
            "sample_id", "image_id", "split", "ground_truth_raw", "ground_truth_normalized",
            "ingredient_keys", "relevant_family_count", "relevant_family_keys",
            "relevant_family_names", "benchmark_track",
        ],
    )
    review_groups: dict[str, list[dict[str, object]]] = collections.defaultdict(list)
    for row in mapping_output:
        if row["mapping_status"] != "mapped_exact":
            review_groups[str(row["ground_truth_normalized"])].append(row)
    review_path = args.results_dir / "catalog_mapping_review_queue.csv"
    existing_review = (
        {row["ground_truth_normalized"]: row for row in read_csv(review_path)}
        if review_path.exists() else {}
    )
    review_rows = []
    for normalized, grouped_rows in review_groups.items():
        example = grouped_rows[0]
        prior = existing_review.get(normalized, {})
        review_rows.append({
            "ground_truth_normalized": normalized,
            "example_ground_truth_raw": example["ground_truth_raw"],
            "occurrences": len(grouped_rows),
            "splits": ";".join(sorted({str(row["split"]) for row in grouped_rows})),
            "mapping_status": example["mapping_status"],
            "best_similarity": example.get("best_similarity", ""),
            "second_similarity": example.get("second_similarity", ""),
            "review_candidate_1": example.get("review_candidate_1", ""),
            "review_candidate_2": example.get("review_candidate_2", ""),
            "review_candidate_3": example.get("review_candidate_3", ""),
            "human_decision": prior.get("human_decision", ""),
            "approved_family_key": prior.get("approved_family_key", ""),
            "reviewer": prior.get("reviewer", ""),
            "review_note": prior.get("review_note", ""),
        })
    review_rows.sort(key=lambda row: (-float(row["best_similarity"] or 0), str(row["ground_truth_normalized"])))
    write_csv(review_path, review_rows, REVIEW_FIELDS)
    write_csv(
        args.results_dir / "dataset_registry.csv",
        [{
            "dataset_name": "RxHandBD",
            "dataset_version": "2",
            "source_url": "https://data.mendeley.com/datasets/dsb5r6vskg/2",
            "license": "CC BY 4.0",
            "sample_level": "word",
            "language": "English",
            "rows": len(rows),
            "train_rows": split_counts.get("train", 0),
            "test_rows": split_counts.get("test", 0),
            "ground_truth_type": "human transcription supplied by dataset",
            "local_source_root": str(args.dataset_root.resolve()),
        }],
        [
            "dataset_name", "dataset_version", "source_url", "license", "sample_level",
            "language", "rows", "train_rows", "test_rows", "ground_truth_type",
            "local_source_root",
        ],
    )
    write_json(args.results_dir / "dataset_audit_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not invalid_images and not label_disagreements and not duplicate_cross_split else 2


if __name__ == "__main__":
    raise SystemExit(main())

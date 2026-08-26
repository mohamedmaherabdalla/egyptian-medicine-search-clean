#!/usr/bin/env python3
"""Compare the promoted OCR checkpoint with frozen full-run comparators."""

from __future__ import annotations

import argparse
import collections
import json
import statistics
from pathlib import Path

from benchmark_common import (
    DEFAULT_ARTIFACTS_DIR,
    DEFAULT_DATA_DIR,
    DEFAULT_RESULTS_DIR,
    read_csv,
    write_csv,
    write_json,
)


PAIR_FIELDS = [
    "scope", "candidate_model", "comparator_model", "rows", "both_exact",
    "candidate_only_exact", "comparator_only_exact", "neither_exact",
    "candidate_exact_accuracy", "comparator_exact_accuracy", "net_exact_gain",
]

EXAMPLE_FIELDS = [
    "example_type", "sample_id", "image_id", "image_path", "split",
    "label_novelty", "ground_truth", "candidate_output", "candidate_exact",
    "candidate_character_error_rate", "comparator_outputs", "selection_rule",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--comparators", nargs="+", type=Path, required=True)
    parser.add_argument(
        "--manifest", type=Path, default=DEFAULT_DATA_DIR / "dataset_manifest.csv"
    )
    parser.add_argument(
        "--training-run",
        type=Path,
        default=DEFAULT_ARTIFACTS_DIR.parent / "models" / "training" / "trocr_base_rxhandbd" / "training_run.json",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_RESULTS_DIR / "final_analysis"
    )
    parser.add_argument("--examples-per-type", type=int, default=10)
    return parser.parse_args()


def load_observations(path: Path) -> tuple[str, dict[str, dict[str, str]]]:
    rows = read_csv(path)
    if not rows:
        raise ValueError(f"empty OCR observation file: {path}")
    name = rows[0]["model_name"]
    by_sample = {row["sample_id"]: row for row in rows}
    if len(by_sample) != len(rows):
        raise ValueError(f"duplicate sample IDs in {path}")
    return name, by_sample


def exact_ids(rows: dict[str, dict[str, str]], sample_ids: set[str]) -> set[str]:
    return {
        sample_id
        for sample_id in sample_ids
        if sample_id in rows and rows[sample_id].get("exact_match") == "1"
    }


def comparator_text(
    sample_id: str, comparators: dict[str, dict[str, dict[str, str]]]
) -> str:
    return "; ".join(
        f"{name}={rows[sample_id]['ocr_output_raw']}"
        for name, rows in sorted(comparators.items())
        if sample_id in rows
    )


def main() -> int:
    args = parse_args()
    manifest_rows = read_csv(args.manifest)
    manifest = {row["sample_id"]: row for row in manifest_rows}
    usable_ids = {
        row["sample_id"] for row in manifest_rows if row.get("ground_truth_usable") == "1"
    }
    test_ids = {
        row["sample_id"]
        for row in manifest_rows
        if row.get("ground_truth_usable") == "1" and row.get("split") == "test"
    }
    train_labels = {
        row["ground_truth_compact"]
        for row in manifest_rows
        if row.get("ground_truth_usable") == "1" and row.get("split") == "train"
    }

    candidate_name, candidate = load_observations(args.candidate)
    comparator_runs = dict(load_observations(path) for path in args.comparators)
    expected_ids = {
        row["sample_id"]
        for row in manifest_rows
        if row.get("image_valid") == "1" and row.get("ground_truth_compact")
    }
    for name, rows in [(candidate_name, candidate), *comparator_runs.items()]:
        if set(rows) != expected_ids:
            raise ValueError(f"{name} does not exactly cover the OCR-eligible manifest")

    pair_rows = []
    for scope, scope_ids in (("all", usable_ids), ("official_test", test_ids)):
        candidate_exact = exact_ids(candidate, scope_ids)
        for comparator_name, comparator in sorted(comparator_runs.items()):
            comparator_exact = exact_ids(comparator, scope_ids)
            both = candidate_exact & comparator_exact
            candidate_only = candidate_exact - comparator_exact
            comparator_only = comparator_exact - candidate_exact
            neither = scope_ids - (candidate_exact | comparator_exact)
            pair_rows.append({
                "scope": scope,
                "candidate_model": candidate_name,
                "comparator_model": comparator_name,
                "rows": len(scope_ids),
                "both_exact": len(both),
                "candidate_only_exact": len(candidate_only),
                "comparator_only_exact": len(comparator_only),
                "neither_exact": len(neither),
                "candidate_exact_accuracy": len(candidate_exact) / len(scope_ids),
                "comparator_exact_accuracy": len(comparator_exact) / len(scope_ids),
                "net_exact_gain": (len(candidate_exact) - len(comparator_exact)) / len(scope_ids),
            })

    candidate_test_exact = exact_ids(candidate, test_ids)
    comparator_test_exact = {
        name: exact_ids(rows, test_ids) for name, rows in comparator_runs.items()
    }
    comparator_union = set().union(*comparator_test_exact.values())
    base_name = next(
        (
            name
            for name in comparator_runs
            if name in {"trocr", "trocr_base_handwritten"}
        ),
        sorted(comparator_runs)[0],
    )
    base_exact = comparator_test_exact[base_name]

    groups = {
        "candidate_unique_exact": candidate_test_exact - comparator_union,
        "candidate_fixed_zero_shot_base": candidate_test_exact - base_exact,
        "candidate_regressed_vs_zero_shot_base": base_exact - candidate_test_exact,
        "candidate_near_miss_all_models_wrong": {
            sample_id
            for sample_id in test_ids - (candidate_test_exact | comparator_union)
            if float(candidate[sample_id]["normalized_edit_distance"]) <= 0.25
        },
        "all_models_severe_failure": {
            sample_id
            for sample_id in test_ids - (candidate_test_exact | comparator_union)
            if float(candidate[sample_id]["normalized_edit_distance"]) > 0.40
        },
    }
    rules = {
        "candidate_unique_exact": "candidate exact; every frozen comparator wrong",
        "candidate_fixed_zero_shot_base": "candidate exact; zero-shot TrOCR Base wrong",
        "candidate_regressed_vs_zero_shot_base": "zero-shot TrOCR Base exact; candidate wrong",
        "candidate_near_miss_all_models_wrong": "all models wrong; candidate CER <= 0.25",
        "all_models_severe_failure": "all models wrong; candidate CER > 0.40",
    }
    examples = []
    for example_type, sample_ids in groups.items():
        ordered = sorted(
            sample_ids,
            key=lambda sample_id: (
                float(candidate[sample_id]["normalized_edit_distance"]),
                manifest[sample_id]["image_id"],
                sample_id,
            ),
        )
        if example_type == "all_models_severe_failure":
            ordered.reverse()
        for sample_id in ordered[: args.examples_per_type]:
            source = manifest[sample_id]
            examples.append({
                "example_type": example_type,
                "sample_id": sample_id,
                "image_id": source["image_id"],
                "image_path": source["image_path"],
                "split": source["split"],
                "label_novelty": (
                    "seen_in_train"
                    if source["ground_truth_compact"] in train_labels
                    else "unseen_in_train"
                ),
                "ground_truth": source["ground_truth_raw"],
                "candidate_output": candidate[sample_id]["ocr_output_raw"],
                "candidate_exact": candidate[sample_id]["exact_match"],
                "candidate_character_error_rate": candidate[sample_id][
                    "normalized_edit_distance"
                ],
                "comparator_outputs": comparator_text(sample_id, comparator_runs),
                "selection_rule": rules[example_type],
            })

    training_run = json.loads(args.training_run.read_text(encoding="utf-8"))
    successful_candidate = [candidate[sample_id] for sample_id in usable_ids]
    failure_counts = collections.Counter(
        "exact" if row["exact_match"] == "1"
        else "empty" if row["empty_output"] == "1"
        else "single_edit" if int(row["edit_distance"]) == 1
        else "multi_edit"
        for row in successful_candidate
    )
    summary = {
        "candidate_model": candidate_name,
        "candidate_version": next(iter(candidate.values()))["model_version"],
        "source_manifest_rows": len(manifest_rows),
        "ocr_eligible_rows": len(expected_ids),
        "scored_usable_rows": len(usable_ids),
        "official_test_rows": len(test_ids),
        "training": {
            "train_rows": training_run["train_rows"],
            "validation_rows": training_run["validation_rows"],
            "official_test_rows_used": training_run["official_test_rows_used"],
            "baseline_validation": training_run["baseline_validation"],
            "epochs": [
                {
                    "epoch": row["epoch"],
                    "mean_train_loss": row["mean_train_loss"],
                    "exact_accuracy": row["validation"]["exact_accuracy"],
                    "mean_character_error_rate": row["validation"][
                        "mean_character_error_rate"
                    ],
                }
                for row in training_run["history"]
            ],
            "best_epoch": training_run["best_epoch"],
            "best_model_sha256": training_run["best_model_sha256"],
        },
        "candidate_full": {
            "exact_matches": failure_counts["exact"],
            "exact_accuracy": failure_counts["exact"] / len(successful_candidate),
            "mean_character_error_rate": statistics.fmean(
                float(row["normalized_edit_distance"]) for row in successful_candidate
            ),
            "failure_counts": dict(sorted(failure_counts.items())),
        },
        "official_test_example_group_counts": {
            key: len(value) for key, value in groups.items()
        },
        "comparators": sorted(comparator_runs),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "promoted_model_pairwise.csv", pair_rows, PAIR_FIELDS)
    write_csv(args.output_dir / "promoted_model_examples.csv", examples, EXAMPLE_FIELDS)
    write_json(args.output_dir / "promoted_model_summary.json", summary)
    print(args.output_dir / "promoted_model_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

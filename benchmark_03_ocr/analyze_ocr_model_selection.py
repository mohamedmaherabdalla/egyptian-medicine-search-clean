#!/usr/bin/env python3
"""Rank validated OCR models and quantify complementary exact recoveries."""

from __future__ import annotations

import argparse
import collections
import itertools
import statistics
from pathlib import Path

from benchmark_common import DEFAULT_ARTIFACTS_DIR, DEFAULT_RESULTS_DIR, read_csv, write_csv, write_json


MODEL_FIELDS = [
    "model_name", "model_version", "preprocessing_id", "rows", "exact_matches",
    "exact_accuracy", "mean_character_error_rate", "empty_rate", "mean_latency_ms",
    "short_exact_accuracy", "medium_exact_accuracy", "long_exact_accuracy",
    "unique_exact_vs_all_other_models", "unique_exact_rate", "promoted_to_full",
    "promotion_reason",
]

PAIR_FIELDS = [
    "model_a", "model_b", "both_exact", "a_only_exact", "b_only_exact",
    "either_exact", "oracle_exact_accuracy",
]

EXAMPLE_FIELDS = [
    "model_name", "sample_id", "image_id", "ground_truth", "model_output",
    "other_outputs",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("observations", nargs="+", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_ARTIFACTS_DIR / "experiments" / "selection" / "train_validation_manifest_1000.csv",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR / "model_selection")
    parser.add_argument("--max-gap", type=float, default=0.05)
    parser.add_argument("--min-unique-rate", type=float, default=0.02)
    return parser.parse_args()


def length_bucket(value: str) -> str:
    length = len("".join(character for character in value if character.isalnum()))
    return "short" if length <= 5 else "medium" if length <= 8 else "long"


def main() -> int:
    args = parse_args()
    manifest = {row["sample_id"]: row for row in read_csv(args.manifest)}
    runs: dict[str, dict[str, dict[str, str]]] = {}
    metadata: dict[str, dict[str, str]] = {}
    for path in args.observations:
        rows = read_csv(path)
        if not rows:
            raise ValueError(f"empty observation file: {path}")
        name = rows[0]["model_name"]
        if name in runs:
            raise ValueError(f"duplicate selected model name: {name}")
        by_sample = {row["sample_id"]: row for row in rows}
        if set(by_sample) != set(manifest):
            raise ValueError(f"{path} does not exactly cover the model-selection manifest")
        runs[name] = by_sample
        metadata[name] = rows[0]

    exact_sets = {
        name: {sample_id for sample_id, row in rows.items() if row["exact_match"] == "1"}
        for name, rows in runs.items()
    }
    summaries = []
    for name, rows in runs.items():
        successful = [row for row in rows.values() if row["run_status"] == "ok"]
        by_length: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
        for row in successful:
            bucket = length_bucket(manifest[row["sample_id"]]["ground_truth_compact"])
            by_length[bucket].append(row)

        def bucket_accuracy(bucket: str) -> float:
            members = by_length[bucket]
            return sum(int(row["exact_match"]) for row in members) / max(len(members), 1)

        other_exact = set().union(*(values for other, values in exact_sets.items() if other != name))
        unique = exact_sets[name] - other_exact
        summaries.append({
            "model_name": name,
            "model_version": metadata[name]["model_version"],
            "preprocessing_id": metadata[name]["preprocessing_id"],
            "rows": len(successful),
            "exact_matches": len(exact_sets[name]),
            "exact_accuracy": len(exact_sets[name]) / max(len(successful), 1),
            "mean_character_error_rate": statistics.fmean(
                float(row["normalized_edit_distance"]) for row in successful
            ),
            "empty_rate": sum(int(row["empty_output"]) for row in successful) / max(len(successful), 1),
            "mean_latency_ms": statistics.fmean(float(row["latency_ms"]) for row in successful),
            "short_exact_accuracy": bucket_accuracy("short"),
            "medium_exact_accuracy": bucket_accuracy("medium"),
            "long_exact_accuracy": bucket_accuracy("long"),
            "unique_exact_vs_all_other_models": len(unique),
            "unique_exact_rate": len(unique) / max(len(successful), 1),
            "promoted_to_full": 0,
            "promotion_reason": "",
        })

    best_accuracy = max(float(row["exact_accuracy"]) for row in summaries)
    promoted = []
    for row in summaries:
        gap = best_accuracy - float(row["exact_accuracy"])
        unique_rate = float(row["unique_exact_rate"])
        if gap <= args.max_gap and unique_rate >= args.min_unique_rate:
            row["promoted_to_full"] = 1
            row["promotion_reason"] = (
                f"accuracy gap {gap:.4f} <= {args.max_gap:.4f} and unique exact rate "
                f"{unique_rate:.4f} >= {args.min_unique_rate:.4f}"
            )
            promoted.append(str(row["model_name"]))
        else:
            row["promotion_reason"] = (
                f"accuracy gap {gap:.4f}; unique exact rate {unique_rate:.4f}"
            )

    pairwise = []
    for model_a, model_b in itertools.combinations(sorted(runs), 2):
        a, b = exact_sets[model_a], exact_sets[model_b]
        pairwise.append({
            "model_a": model_a,
            "model_b": model_b,
            "both_exact": len(a & b),
            "a_only_exact": len(a - b),
            "b_only_exact": len(b - a),
            "either_exact": len(a | b),
            "oracle_exact_accuracy": len(a | b) / len(manifest),
        })

    examples = []
    for name in sorted(runs):
        other_exact = set().union(*(values for other, values in exact_sets.items() if other != name))
        unique_ids = sorted(
            exact_sets[name] - other_exact,
            key=lambda sample_id: (manifest[sample_id]["image_id"], sample_id),
        )[:10]
        for sample_id in unique_ids:
            examples.append({
                "model_name": name,
                "sample_id": sample_id,
                "image_id": manifest[sample_id]["image_id"],
                "ground_truth": runs[name][sample_id]["ground_truth_raw"],
                "model_output": runs[name][sample_id]["ocr_output_raw"],
                "other_outputs": "; ".join(
                    f"{other}={runs[other][sample_id]['ocr_output_raw']}"
                    for other in sorted(runs) if other != name
                ),
            })

    all_oracle = set().union(*exact_sets.values())
    summaries.sort(key=lambda row: (-float(row["exact_accuracy"]), float(row["mean_character_error_rate"])))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "validated_model_comparison.csv", summaries, MODEL_FIELDS)
    write_csv(args.output_dir / "validated_model_pairwise.csv", pairwise, PAIR_FIELDS)
    write_csv(args.output_dir / "validated_model_unique_examples.csv", examples, EXAMPLE_FIELDS)
    write_json(args.output_dir / "model_selection_decision.json", {
        "selection_manifest": str(args.manifest),
        "rows": len(manifest),
        "official_test_rows_used": 0,
        "promotion_rule": {
            "max_exact_accuracy_gap_from_best": args.max_gap,
            "minimum_unique_exact_rate": args.min_unique_rate,
        },
        "promoted_to_full": promoted,
        "all_model_oracle_exact_matches": len(all_oracle),
        "all_model_oracle_exact_accuracy": len(all_oracle) / len(manifest),
        "oracle_is_diagnostic_not_a_deployable_score": True,
    })
    print(args.output_dir / "model_selection_decision.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Compare paired OCR screens and select configurations for validation."""

from __future__ import annotations

import argparse
import collections
import math
import statistics
from pathlib import Path

from benchmark_common import DEFAULT_ARTIFACTS_DIR, read_csv, write_csv, write_json


SUMMARY_FIELDS = [
    "configuration_id", "model_name", "model_version", "preprocessing_id", "rows",
    "exact_matches", "exact_accuracy", "mean_character_error_rate", "empty_rate",
    "mean_latency_ms", "short_exact_accuracy", "medium_exact_accuracy",
    "long_exact_accuracy", "raw_to_candidate_wins", "raw_to_candidate_losses",
    "mcnemar_two_sided_p", "promotion_stage", "promotion_reason",
]

CHANGE_FIELDS = [
    "model_name", "candidate_preprocessing", "change", "sample_id", "image_id",
    "ground_truth", "raw_output", "candidate_output", "raw_cer", "candidate_cer",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("observations", nargs="+", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_ARTIFACTS_DIR / "experiments" / "selection" / "train_screening_manifest_600.csv",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR / "experiments" / "screening"
    )
    return parser.parse_args()


def length_bucket(value: str) -> str:
    length = len("".join(character for character in value if character.isalnum()))
    return "short" if length <= 5 else "medium" if length <= 8 else "long"


def binomial_two_sided(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = min(wins, losses)
    probability = sum(math.comb(discordant, k) for k in range(tail + 1)) / (2 ** discordant)
    return min(1.0, 2 * probability)


def summarize(rows: list[dict[str, str]], manifest: dict[str, dict[str, str]]) -> dict[str, object]:
    successful = [row for row in rows if row.get("run_status") == "ok"]
    exact = sum(int(row["exact_match"]) for row in successful)
    by_length: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for row in successful:
        by_length[length_bucket(manifest[row["sample_id"]]["ground_truth_compact"])].append(row)

    def bucket_accuracy(bucket: str) -> float:
        members = by_length[bucket]
        return sum(int(row["exact_match"]) for row in members) / max(len(members), 1)

    first = rows[0]
    return {
        "configuration_id": f"{first['model_name']}::{first['preprocessing_id']}",
        "model_name": first["model_name"],
        "model_version": first["model_version"],
        "preprocessing_id": first["preprocessing_id"],
        "rows": len(successful),
        "exact_matches": exact,
        "exact_accuracy": exact / max(len(successful), 1),
        "mean_character_error_rate": statistics.fmean(
            float(row["normalized_edit_distance"]) for row in successful
        ),
        "empty_rate": sum(int(row["empty_output"]) for row in successful) / max(len(successful), 1),
        "mean_latency_ms": statistics.fmean(float(row["latency_ms"]) for row in successful),
        "short_exact_accuracy": bucket_accuracy("short"),
        "medium_exact_accuracy": bucket_accuracy("medium"),
        "long_exact_accuracy": bucket_accuracy("long"),
        "raw_to_candidate_wins": "",
        "raw_to_candidate_losses": "",
        "mcnemar_two_sided_p": "",
        "promotion_stage": "screened",
        "promotion_reason": "",
    }


def main() -> int:
    args = parse_args()
    manifest = {row["sample_id"]: row for row in read_csv(args.manifest)}
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for path in args.observations:
        rows = read_csv(path)
        if not rows:
            raise ValueError(f"empty observation file: {path}")
        key = (rows[0]["model_name"], rows[0]["preprocessing_id"])
        if key in grouped:
            raise ValueError(f"duplicate model/preprocessing configuration: {key}")
        sample_ids = {row["sample_id"] for row in rows}
        if sample_ids != set(manifest):
            raise ValueError(
                f"{path} does not cover the selection manifest: "
                f"missing={len(set(manifest) - sample_ids)}, extra={len(sample_ids - set(manifest))}"
            )
        grouped[key] = rows

    summaries = [summarize(rows, manifest) for rows in grouped.values()]
    summary_by_key = {(row["model_name"], row["preprocessing_id"]): row for row in summaries}
    changes: list[dict[str, object]] = []
    selected: dict[str, str] = {}

    for model_name in sorted({key[0] for key in grouped}):
        raw_rows = grouped.get((model_name, "raw"))
        if raw_rows is None:
            raise ValueError(f"missing raw control for {model_name}")
        raw_by_sample = {row["sample_id"]: row for row in raw_rows}
        raw_summary = summary_by_key[(model_name, "raw")]
        candidates = []
        for (candidate_model, preprocessing), rows in grouped.items():
            if candidate_model != model_name or preprocessing == "raw":
                continue
            by_sample = {row["sample_id"]: row for row in rows}
            wins = losses = 0
            for sample_id, raw in raw_by_sample.items():
                candidate = by_sample[sample_id]
                raw_exact = int(raw["exact_match"])
                candidate_exact = int(candidate["exact_match"])
                if candidate_exact > raw_exact:
                    wins += 1
                    change = "wrong_to_exact"
                elif candidate_exact < raw_exact:
                    losses += 1
                    change = "exact_to_wrong"
                else:
                    continue
                changes.append({
                    "model_name": model_name,
                    "candidate_preprocessing": preprocessing,
                    "change": change,
                    "sample_id": sample_id,
                    "image_id": raw["image_id"],
                    "ground_truth": raw["ground_truth_raw"],
                    "raw_output": raw["ocr_output_raw"],
                    "candidate_output": candidate["ocr_output_raw"],
                    "raw_cer": raw["normalized_edit_distance"],
                    "candidate_cer": candidate["normalized_edit_distance"],
                })
            summary = summary_by_key[(model_name, preprocessing)]
            summary["raw_to_candidate_wins"] = wins
            summary["raw_to_candidate_losses"] = losses
            summary["mcnemar_two_sided_p"] = binomial_two_sided(wins, losses)
            candidates.append(summary)

        eligible = [
            row for row in candidates
            if int(row["exact_matches"]) > int(raw_summary["exact_matches"])
            and float(row["mean_character_error_rate"])
            <= float(raw_summary["mean_character_error_rate"])
        ]
        if eligible:
            winner = min(
                eligible,
                key=lambda row: (
                    -int(row["exact_matches"]),
                    float(row["mean_character_error_rate"]),
                    float(row["mean_latency_ms"]),
                ),
            )
            winner["promotion_stage"] = "promoted_to_validation"
            winner["promotion_reason"] = (
                "more exact matches than raw and no CER regression; "
                "best eligible configuration by exact, CER, then latency"
            )
            selected[model_name] = str(winner["preprocessing_id"])
        else:
            raw_summary["promotion_stage"] = "promoted_to_validation"
            raw_summary["promotion_reason"] = "no candidate improved exact count without worsening CER"
            selected[model_name] = "raw"

    summaries.sort(key=lambda row: (str(row["model_name"]), str(row["preprocessing_id"])))
    changes.sort(
        key=lambda row: (
            str(row["model_name"]), str(row["candidate_preprocessing"]),
            str(row["change"]), str(row["image_id"]),
        )
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "screening_comparison.csv", summaries, SUMMARY_FIELDS)
    write_csv(args.output_dir / "screening_paired_changes.csv", changes, CHANGE_FIELDS)
    write_json(args.output_dir / "screening_decision.json", {
        "selection_manifest": str(args.manifest),
        "selection_rows": len(manifest),
        "official_test_rows_used": 0,
        "promotion_rule": (
            "candidate exact count must exceed raw and mean CER must not regress; "
            "ties resolve by exact count, CER, then latency"
        ),
        "selected_for_disjoint_validation": selected,
        "screened_configurations": len(summaries),
    })
    print(args.output_dir / "screening_decision.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

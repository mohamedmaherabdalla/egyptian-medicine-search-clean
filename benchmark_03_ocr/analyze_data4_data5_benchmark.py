#!/usr/bin/env python3
"""Build the consolidated folder-4/folder-5 OCR and search benchmark report."""

from __future__ import annotations

import argparse
import collections
import json
import statistics
from pathlib import Path

from benchmark_common import read_csv, write_csv, write_json


HERE = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = HERE / "data" / "02_data4_data5"
DEFAULT_ARTIFACTS_DIR = HERE / "artifacts" / "02_data4_data5"
DEFAULT_RESULTS_DIR = HERE / "results" / "02_data4_data5"

RUNS = (
    ("Fine-tuned TrOCR Base", "data4_processed84", "ocr_finetuned_trocr_data4_test.csv"),
    ("Fine-tuned TrOCR Base", "data5_original", "ocr_finetuned_trocr_data5_test.csv"),
    ("PaddleOCR PP-OCRv6 medium", "data4_processed84", "ocr_paddle_v6_data4_test.csv"),
    ("PaddleOCR PP-OCRv6 medium", "data5_original", "ocr_paddle_v6_data5_test.csv"),
    ("Zero-shot TrOCR Base", "data4_processed84", "ocr_trocr_zero_shot_data4_test.csv"),
    ("Zero-shot TrOCR Base", "data5_original", "ocr_trocr_zero_shot_data5_test.csv"),
    ("Tesseract 5.5.1", "data4_processed84", "ocr_tesseract_data4_test.csv"),
    ("Tesseract 5.5.1", "data5_original", "ocr_tesseract_data5_test.csv"),
)

OCR_METRIC_FIELDS = [
    "model", "representation", "rows", "exact_matches", "exact_accuracy",
    "mean_normalized_edit_distance", "median_latency_ms", "mean_latency_ms",
    "p95_latency_ms", "empty_outputs", "empty_output_rate", "runtime_errors",
]
CLASS_METRIC_FIELDS = [
    "model", "representation", "ground_truth", "rows", "exact_matches",
    "exact_accuracy", "mean_normalized_edit_distance",
]
PAIR_FIELDS = [
    "model", "paired_rows", "data4_exact", "data5_exact", "accuracy_delta_data5_minus_data4",
    "both_exact", "data4_only_exact", "data5_only_exact", "neither_exact",
    "data4_mean_normalized_edit_distance", "data5_mean_normalized_edit_distance",
    "mean_distance_delta_data5_minus_data4",
]
EXAMPLE_FIELDS = [
    "model", "example_type", "image_id", "ground_truth", "data4_output",
    "data4_exact", "data4_normalized_edit_distance", "data5_output", "data5_exact",
    "data5_normalized_edit_distance", "selection_rule",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--examples-per-model", type=int, default=3)
    return parser.parse_args()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction)))
    return ordered[index]


def load_runs(artifacts_dir: Path) -> dict[tuple[str, str], list[dict[str, str]]]:
    runs: dict[tuple[str, str], list[dict[str, str]]] = {}
    for model, representation, filename in RUNS:
        path = artifacts_dir / filename
        rows = read_csv(path)
        if len(rows) != 780:
            raise ValueError(f"{path} has {len(rows)} rows; expected the complete 780-row test split")
        image_ids = [row["image_id"] for row in rows]
        if len(set(image_ids)) != len(image_ids):
            raise ValueError(f"duplicate image IDs in {path}")
        if any(row["split"] != "test" for row in rows):
            raise ValueError(f"non-test row found in {path}")
        runs[(model, representation)] = rows
    return runs


def build_ocr_metrics(
    runs: dict[tuple[str, str], list[dict[str, str]]]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    overall: list[dict[str, object]] = []
    by_class: list[dict[str, object]] = []
    for (model, representation), rows in runs.items():
        latencies = [float(row["latency_ms"]) for row in rows]
        distances = [float(row["normalized_edit_distance"]) for row in rows]
        exact = sum(row["exact_match"] == "1" for row in rows)
        empty = sum(row["empty_output"] == "1" for row in rows)
        errors = sum(row["run_status"] != "ok" for row in rows)
        overall.append({
            "model": model,
            "representation": representation,
            "rows": len(rows),
            "exact_matches": exact,
            "exact_accuracy": exact / len(rows),
            "mean_normalized_edit_distance": statistics.fmean(distances),
            "median_latency_ms": statistics.median(latencies),
            "mean_latency_ms": statistics.fmean(latencies),
            "p95_latency_ms": percentile(latencies, 0.95),
            "empty_outputs": empty,
            "empty_output_rate": empty / len(rows),
            "runtime_errors": errors,
        })
        groups: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
        for row in rows:
            groups[row["ground_truth_raw"]].append(row)
        for ground_truth, group in sorted(groups.items()):
            class_exact = sum(row["exact_match"] == "1" for row in group)
            by_class.append({
                "model": model,
                "representation": representation,
                "ground_truth": ground_truth,
                "rows": len(group),
                "exact_matches": class_exact,
                "exact_accuracy": class_exact / len(group),
                "mean_normalized_edit_distance": statistics.fmean(
                    float(row["normalized_edit_distance"]) for row in group
                ),
            })
    return overall, by_class


def paired_rows(
    runs: dict[tuple[str, str], list[dict[str, str]]], model: str
) -> list[tuple[dict[str, str], dict[str, str]]]:
    data4 = {row["image_id"]: row for row in runs[(model, "data4_processed84")]}
    data5 = {row["image_id"]: row for row in runs[(model, "data5_original")]}
    if set(data4) != set(data5):
        raise ValueError(f"folder representations do not cover the same image IDs for {model}")
    pairs = []
    for image_id in sorted(data4, key=lambda value: int(Path(value).stem)):
        left, right = data4[image_id], data5[image_id]
        if left["ground_truth_normalized"] != right["ground_truth_normalized"]:
            raise ValueError(f"ground-truth mismatch for {model} image {image_id}")
        pairs.append((left, right))
    return pairs


def build_pairwise(
    runs: dict[tuple[str, str], list[dict[str, str]]], examples_per_model: int
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    metrics: list[dict[str, object]] = []
    examples: list[dict[str, object]] = []
    model_order = [model for model, representation, _ in RUNS if representation == "data4_processed84"]
    for model in model_order:
        pairs = paired_rows(runs, model)
        data4_exact = sum(left["exact_match"] == "1" for left, _ in pairs)
        data5_exact = sum(right["exact_match"] == "1" for _, right in pairs)
        both = sum(left["exact_match"] == right["exact_match"] == "1" for left, right in pairs)
        data4_only = sum(left["exact_match"] == "1" and right["exact_match"] == "0" for left, right in pairs)
        data5_only = sum(left["exact_match"] == "0" and right["exact_match"] == "1" for left, right in pairs)
        neither = len(pairs) - both - data4_only - data5_only
        data4_distance = statistics.fmean(float(left["normalized_edit_distance"]) for left, _ in pairs)
        data5_distance = statistics.fmean(float(right["normalized_edit_distance"]) for _, right in pairs)
        metrics.append({
            "model": model,
            "paired_rows": len(pairs),
            "data4_exact": data4_exact,
            "data5_exact": data5_exact,
            "accuracy_delta_data5_minus_data4": (data5_exact - data4_exact) / len(pairs),
            "both_exact": both,
            "data4_only_exact": data4_only,
            "data5_only_exact": data5_only,
            "neither_exact": neither,
            "data4_mean_normalized_edit_distance": data4_distance,
            "data5_mean_normalized_edit_distance": data5_distance,
            "mean_distance_delta_data5_minus_data4": data5_distance - data4_distance,
        })

        groups = {
            "data5_recovers_data4_failure": [
                pair for pair in pairs if pair[0]["exact_match"] == "0" and pair[1]["exact_match"] == "1"
            ],
            "data4_recovers_data5_failure": [
                pair for pair in pairs if pair[0]["exact_match"] == "1" and pair[1]["exact_match"] == "0"
            ],
            "both_wrong_near_miss": [
                pair for pair in pairs
                if pair[0]["exact_match"] == pair[1]["exact_match"] == "0"
                and min(float(pair[0]["normalized_edit_distance"]), float(pair[1]["normalized_edit_distance"])) <= 0.25
            ],
        }
        rules = {
            "data5_recovers_data4_failure": "same indexed sample; folder 5 exact and folder 4 wrong",
            "data4_recovers_data5_failure": "same indexed sample; folder 4 exact and folder 5 wrong",
            "both_wrong_near_miss": "both wrong; at least one normalized edit distance <= 0.25",
        }
        selected_ground_truths: set[tuple[str, str]] = set()
        for example_type, candidates in groups.items():
            ordered = sorted(
                candidates,
                key=lambda pair: (
                    min(float(pair[0]["normalized_edit_distance"]), float(pair[1]["normalized_edit_distance"])),
                    int(Path(pair[0]["image_id"]).stem),
                ),
            )
            chosen = 0
            for left, right in ordered:
                uniqueness_key = (example_type, left["ground_truth_normalized"])
                if uniqueness_key in selected_ground_truths:
                    continue
                selected_ground_truths.add(uniqueness_key)
                examples.append({
                    "model": model,
                    "example_type": example_type,
                    "image_id": left["image_id"],
                    "ground_truth": left["ground_truth_raw"],
                    "data4_output": left["ocr_output_raw"],
                    "data4_exact": left["exact_match"],
                    "data4_normalized_edit_distance": left["normalized_edit_distance"],
                    "data5_output": right["ocr_output_raw"],
                    "data5_exact": right["exact_match"],
                    "data5_normalized_edit_distance": right["normalized_edit_distance"],
                    "selection_rule": rules[example_type],
                })
                chosen += 1
                if chosen >= examples_per_model:
                    break
    return metrics, examples


def algorithm_equivalence(search_results: list[dict[str, str]]) -> dict[str, object]:
    by_case: dict[str, dict[str, dict[str, str]]] = collections.defaultdict(dict)
    for row in search_results:
        by_case[row["case_id"]][row["algorithm"]] = row
    algorithms = (
        "algorithm_2_external_fast",
        "algorithm_3_rank_fusion",
        "algorithm_4_family_rescue",
    )
    retrieval_fields = (
        "first_relevant_rank", "hit_at_1", "hit_at_5", "hit_at_10", "hit_at_20",
        "reciprocal_rank", "top_1", "top_5", "top_20",
    )
    decision_fields = (
        "response_status", "decision_type", "needs_clarification", "unsafe_confident_top1",
    )
    complete = 0
    same_retrieval = 0
    same_decision = 0
    for rows in by_case.values():
        if not all(name in rows for name in algorithms):
            continue
        complete += 1
        baseline = rows[algorithms[0]]
        if all(
            all(rows[name][field] == baseline[field] for field in retrieval_fields)
            for name in algorithms[1:]
        ):
            same_retrieval += 1
        if all(
            all(rows[name][field] == baseline[field] for field in decision_fields)
            for name in algorithms[1:]
        ):
            same_decision += 1
    return {
        "compared_cases": complete,
        "algorithms": list(algorithms),
        "identical_retrieval_cases": same_retrieval,
        "identical_decision_cases": same_decision,
    }


def percent(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def markdown_table(headers: list[str], rows: list[list[object]], align: str | None = None) -> str:
    separator = ["---"] * len(headers)
    if align:
        separator = ["---" if marker == "l" else "---:" for marker in align]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def build_report(
    results_dir: Path,
    audit: dict[str, object],
    ocr_metrics: list[dict[str, object]],
    pair_metrics: list[dict[str, object]],
    examples: list[dict[str, object]],
    generation: dict[str, object],
    search_summary: dict[str, object],
    accepted_cases: list[dict[str, str]],
    equivalence: dict[str, object],
) -> str:
    ocr_rows = [
        [
            row["model"], row["representation"], row["rows"], row["exact_matches"],
            percent(float(row["exact_accuracy"])), f'{float(row["mean_normalized_edit_distance"]):.3f}',
            f'{float(row["mean_latency_ms"]):.1f}', row["empty_outputs"], row["runtime_errors"],
        ]
        for row in ocr_metrics
    ]
    pair_rows = [
        [
            row["model"], row["data4_exact"], row["data5_exact"],
            percent(float(row["accuracy_delta_data5_minus_data4"])), row["both_exact"],
            row["data4_only_exact"], row["data5_only_exact"], row["neither_exact"],
        ]
        for row in pair_metrics
    ]
    search_rows = [
        [
            row["algorithm"], row["cases"], percent(float(row["hit_at_1"])),
            percent(float(row["hit_at_5"])), percent(float(row["hit_at_20"])),
            f'{float(row["mrr_at_20"]):.3f}', percent(float(row["unsafe_confident_top1_rate"])),
            f'{float(row["mean_latency_ms"]):.2f}',
        ]
        for row in search_summary["all_scope_metrics"]
    ]
    example_rows = [
        [
            row["model"], row["example_type"], row["image_id"], row["ground_truth"],
            row["data4_output"] or "(empty)", row["data5_output"] or "(empty)",
        ]
        for row in examples
    ]
    dangerous = [row for row in accepted_cases if row["danger"] == "DANGEROUS"]
    dangerous_rows = [
        [row["model_name"], row["image_id"], row["input"], row["expected_family_name"], row["dangerous_collision_families"]]
        for row in dangerous
    ]
    accepted_by_model = collections.Counter(row["model_name"] for row in accepted_cases)
    accepted_by_representation = collections.Counter(
        "data4_processed84" if "data4" in row["model_name"] else "data5_original"
        for row in accepted_cases
    )
    accepted_by_target = collections.Counter(row["expected_family_name"] for row in accepted_cases)
    accepted_model_rows = [[key, value] for key, value in accepted_by_model.most_common()]
    accepted_representation_rows = [[key, value] for key, value in accepted_by_representation.items()]
    accepted_target_rows = [[key, value] for key, value in accepted_by_target.most_common()]
    mapped_test_observations = (
        int(generation["observation_rows"])
        - int(generation["rejection_counts"]["ground_truth_not_uniquely_catalog_resolved"])
    )
    rejection_rows = [[key, value] for key, value in generation["rejection_counts"].items()]
    mistake_rows = [[key, value] for key, value in generation["mistake_type_counts"].items()]
    lines = [
        "# Folder 4 and Folder 5 OCR and Search Benchmark",
        "",
        "## Executive Result",
        "",
        "Folders 4 and 5 contain the same indexed 4,680 labeled medicine-word samples in two representations. "
        "Folder 4 stores processed `84x84` images; folder 5 stores the original variable-size crops. "
        "Their labels match for every corresponding sample, so this report treats them as paired views rather than 9,360 independent examples.",
        "",
        f"The locked test split contains `{audit['split_counts']['test']}` paired samples across `{audit['classes']}` classes. "
        "All four OCR configurations completed all test rows on both representations with zero runtime errors. "
        "The best exact OCR result was **PaddleOCR on folder 5: 352/780 (45.13%)**. "
        "The fine-tuned TrOCR checkpoint was second on folder 5 at **313/780 (40.13%)**.",
        "",
        "## Dataset Audit",
        "",
        markdown_table(
            ["Check", "Result"],
            [
                ["Rows per representation", audit["data4_rows"]],
                ["Train / validation / test", f"{audit['split_counts']['train']} / {audit['split_counts']['validation']} / {audit['split_counts']['test']}"],
                ["Medicine classes", audit["classes"]],
                ["Paired label mismatches", audit["label_mismatches"]],
                ["Exact Egyptian catalog classes", audit["egypt_catalog_exact_classes"]],
                ["Catalog-eligible rows across both representations and all splits", audit["egypt_catalog_eligible_rows"]],
            ],
        ),
        "",
        "The two image files for a corresponding ID are not byte-identical. That is expected: folder 4 is a resized/processed export. "
        "The evidence for pairing is the shared split, filename index, numeric class mapping, and exact decoded label agreement, not pixel identity.",
        "",
        "## OCR Results",
        "",
        markdown_table(
            ["OCR system", "Representation", "Rows", "Exact", "Accuracy", "Mean NED", "Mean ms", "Empty", "Errors"],
            ocr_rows,
            "llrrrrrrr",
        ),
        "",
        "`NED` is normalized edit distance: `0` is an exact transcription and larger values mean more character corruption. "
        "Exact accuracy ignores case and punctuation through the benchmark's normalized comparison.",
        "",
        "## Paired Representation Effect",
        "",
        markdown_table(
            ["OCR system", "Folder 4 exact", "Folder 5 exact", "F5-F4 accuracy", "Both exact", "F4 only", "F5 only", "Neither"],
            pair_rows,
            "lrrrrrrr",
        ),
        "",
        "Folder 5 improved every OCR system. The largest gain was PaddleOCR: `+24.10` percentage points. "
        "This is a preprocessing/domain result, not extra training data: both sides contain the same test words. "
        "The aggressive fixed-size representation removes detail and changes aspect ratios that recognition models use.",
        "",
        "## Paired Examples",
        "",
        markdown_table(
            ["OCR system", "Example type", "Image", "Truth", "Folder 4 output", "Folder 5 output"],
            example_rows,
        ),
        "",
        "Examples are selected deterministically from paired test rows and use different ground-truth labels within each example type when available.",
        "",
        "## Egyptian Catalog Filter and Generated Search Set",
        "",
        f"Only `{audit['egypt_catalog_exact_classes']}` of `{audit['classes']}` source labels resolve uniquely and exactly to the Egyptian medicine catalog. "
        "The eligible classes are `Baclofen`, `Conaz`, `Flexilax`, `Ketoral`, `Maxpro`, `Rivotril`, and `Telfast`. "
        "No fuzzy catalog suggestion was promoted to ground truth.",
        "",
        markdown_table(["Generation result", "Rows"], [
            ["OCR observations considered", generation["observation_rows"]],
            ["Catalog-mapped test observations before error filters", mapped_test_observations],
            ["Accepted observation cases", generation["accepted_observation_cases"]],
            ["Unique query-target pairs", generation["accepted_unique_query_target_pairs"]],
            ["Rejected observations", generation["rejected_rows"]],
            ["Dangerous real-drug collisions retained", generation["dangerous_collision_cases"]],
        ]),
        "",
        f"The {mapped_test_observations} pre-filter observations are `7 mapped test classes x 10 images x 2 representations x 4 OCR systems`. "
        "The accepted cases are OCR errors only; exact OCR output is intentionally excluded from the search-recovery test.",
        "",
        "### Accepted Cases by Representation",
        "",
        markdown_table(["Representation", "Accepted cases"], accepted_representation_rows),
        "",
        "### Accepted Cases by OCR System",
        "",
        markdown_table(["OCR run", "Accepted cases"], accepted_model_rows),
        "",
        "### Accepted Cases by Expected Egyptian Family",
        "",
        markdown_table(["Expected family", "Accepted cases"], accepted_target_rows),
        "",
        "### Rejections",
        "",
        markdown_table(["Reason", "Rows"], rejection_rows),
        "",
        "### Accepted Mistake Types",
        "",
        markdown_table(["Mistake type", "Rows"], mistake_rows),
        "",
        "### Dangerous Accepted Collisions",
        "",
        markdown_table(["OCR system", "Image", "OCR input", "Expected", "Input is real family"], dangerous_rows),
        "",
        "These rows are not ordinary spelling errors. The OCR output is itself another real catalog family, so blindly trusting an exact database hit would produce the wrong medicine.",
        "",
        "## Downstream Search Results",
        "",
        markdown_table(
            ["Algorithm", "Cases", "Hit@1", "Hit@5", "Hit@20", "MRR@20", "Unsafe top-1", "Mean ms"],
            search_rows,
            "lrrrrrrr",
        ),
        "",
        f"Algorithms 2, 3, and 4 had identical ranked retrieval on `{equivalence['identical_retrieval_cases']}` of "
        f"`{equivalence['compared_cases']}` compared cases. Their response/safety decisions were identical on "
        f"`{equivalence['identical_decision_cases']}` cases. This narrow seven-class subset therefore does not distinguish "
        "the later fusion/rescue logic; it only shows that all three recover the same candidates here.",
        "",
        "## What The Result Means",
        "",
        "- Use folder 5 originals as the primary OCR input. Folder 4 remains useful as a controlled degraded representation.",
        "- PaddleOCR is the strongest frozen recognizer on these original crops, while the RxHandBD-tuned TrOCR model does not transfer as well to this source.",
        "- The 780-image OCR result is valid across all 78 classes. The 300-case search result is much narrower because only seven classes have verified Egyptian-catalog targets.",
        "- Do not report 9,360 independent images or 1,560 independent test images. They are paired representations of 4,680 source samples and 780 test samples.",
        "- The benchmark contains isolated word crops, not complete prescription pages. Full pages still require detection/segmentation before recognition.",
        "- Folder source metadata is not present in the local export, so this report does not claim patient/site provenance beyond what the files prove.",
        "",
        "## Reproducibility Outputs",
        "",
        "- `ocr_metrics.csv`: all eight OCR configuration summaries.",
        "- `ocr_metrics_by_class.csv`: every OCR system/representation/class bucket.",
        "- `representation_pairwise.csv`: paired improvements and regressions.",
        "- `representative_examples.csv`: deterministic paired examples.",
        "- `artifacts/02_data4_data5/search_cases.csv`: accepted and rejected OCR-derived observations.",
        "- `artifacts/02_data4_data5/search_results.csv`: row-level Algorithms 1-4 results.",
        "- `results/02_data4_data5/search_metrics.csv`: aggregate Algorithms 1-4 results.",
        "- `analysis_summary.json`: machine-readable reconciliation summary.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir.resolve()
    artifacts_dir = args.artifacts_dir.resolve()
    results_dir = args.results_dir.resolve()
    runs = load_runs(artifacts_dir)
    ocr_metrics, class_metrics = build_ocr_metrics(runs)
    pair_metrics, examples = build_pairwise(runs, args.examples_per_model)

    audit = json.loads((data_dir / "dataset_audit_summary.json").read_text(encoding="utf-8"))
    generation = json.loads((results_dir / "search_case_generation_summary.json").read_text(encoding="utf-8"))
    search_summary = json.loads((results_dir / "search_evaluation_summary.json").read_text(encoding="utf-8"))
    search_cases = read_csv(artifacts_dir / "search_cases.csv")
    accepted_cases = [row for row in search_cases if row["accepted"] == "1"]
    search_results = read_csv(artifacts_dir / "search_results.csv")
    equivalence = algorithm_equivalence(search_results)

    if len(search_results) != generation["accepted_observation_cases"] * 4:
        raise ValueError("search result rows do not reconcile to accepted cases x four algorithms")
    if len(accepted_cases) != generation["accepted_observation_cases"]:
        raise ValueError("accepted search-case count does not reconcile")

    summary = {
        "source": audit,
        "ocr_observation_rows": sum(int(row["rows"]) for row in ocr_metrics),
        "ocr_configurations": len(ocr_metrics),
        "ocr_runtime_errors": sum(int(row["runtime_errors"]) for row in ocr_metrics),
        "best_ocr_configuration": max(ocr_metrics, key=lambda row: float(row["exact_accuracy"])),
        "search_case_generation": generation,
        "search_evaluation": search_summary,
        "algorithm_2_3_4_equivalence": equivalence,
    }
    write_csv(results_dir / "ocr_metrics.csv", ocr_metrics, OCR_METRIC_FIELDS)
    write_csv(results_dir / "ocr_metrics_by_class.csv", class_metrics, CLASS_METRIC_FIELDS)
    write_csv(results_dir / "representation_pairwise.csv", pair_metrics, PAIR_FIELDS)
    write_csv(results_dir / "representative_examples.csv", examples, EXAMPLE_FIELDS)
    write_json(results_dir / "analysis_summary.json", summary)
    report = build_report(
        results_dir, audit, ocr_metrics, pair_metrics, examples, generation,
        search_summary, accepted_cases, equivalence,
    )
    report_path = results_dir / "DATA4_DATA5_BENCHMARK_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

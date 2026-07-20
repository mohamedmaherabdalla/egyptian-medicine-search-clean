#!/usr/bin/env python3
"""Build one consolidated, paper-oriented Data 3 Markdown report."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from benchmark_common import DEFAULT_ARTIFACTS_DIR, DEFAULT_DATA_DIR, DEFAULT_RESULTS_DIR, read_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_first_json(paths: list[Path]) -> dict:
    for path in paths:
        if path.exists():
            return load_json(path)
    return {}


def percent(value: object) -> str:
    return f"{100 * float(value or 0):.2f}%"


def md_escape(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def display_version(value: object) -> str:
    text = str(value or "")
    if "models--" in text and "/snapshots/" in text:
        model = text.split("models--", 1)[1].split("/snapshots/", 1)[0].replace("--", "/")
        revision = text.rsplit("@", 1)[-1]
        return md_escape(f"{model}@{revision}")
    return md_escape(text)


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir
    artifacts_dir = args.artifacts_dir
    results_dir = args.results_dir
    output_path = args.output or results_dir / "DATA3_BENCHMARK_REPORT.md"
    audit = load_json(data_dir / "dataset_audit_summary.json")
    case_summary = load_first_json([
        results_dir / "search_case_generation_summary.json",
        artifacts_dir / "search_case_generation_summary.json",
    ])
    search_summary = load_json(results_dir / "search_evaluation_summary.json")
    end_to_end_summary = load_json(results_dir / "end_to_end_evaluation_summary.json")
    validation = load_json(results_dir / "validation_summary.json")
    image_analysis = load_json(results_dir / "analysis" / "image_and_failure_analysis_summary.json")
    screening_decision = load_json(
        artifacts_dir / "experiments" / "screening" / "screening_decision.json"
    )
    model_selection = load_json(results_dir / "model_selection_final" / "model_selection_decision.json")
    training_run = load_json(
        artifacts_dir.parent / "models" / "training" / "trocr_base_rxhandbd" / "training_run.json"
    )
    promoted_summary = load_json(results_dir / "final_analysis" / "promoted_model_summary.json")
    summary_paths = {
        path.name: path
        for directory in (results_dir, artifacts_dir)
        for path in directory.glob("ocr_*.summary.json")
    }
    ocr_summaries = [load_json(summary_paths[name]) for name in sorted(summary_paths)]
    calibration_summaries = [
        load_json(path)
        for path in sorted((artifacts_dir / "experiments" / "calibration").glob("pilot_*.summary.json"))
    ]
    secondary_summaries = [
        load_json(path)
        for path in sorted((artifacts_dir / "experiments" / "secondary").glob("*.summary.json"))
    ]
    search_metrics = read_csv(results_dir / "search_metrics.csv") if (results_dir / "search_metrics.csv").exists() else []
    ocr_metrics = read_csv(results_dir / "ocr_metrics.csv") if (results_dir / "ocr_metrics.csv").exists() else []
    search_cases = read_csv(artifacts_dir / "search_cases.csv") if (artifacts_dir / "search_cases.csv").exists() else []
    search_results = read_csv(artifacts_dir / "search_results.csv") if (artifacts_dir / "search_results.csv").exists() else []
    end_to_end_metrics = read_csv(results_dir / "end_to_end_metrics.csv") if (results_dir / "end_to_end_metrics.csv").exists() else []
    execution_status = read_csv(results_dir / "model_execution_status.csv") if (results_dir / "model_execution_status.csv").exists() else []
    duplicate_audit = read_csv(data_dir / "duplicate_image_audit.csv") if (data_dir / "duplicate_image_audit.csv").exists() else []
    model_selection_rows = read_csv(results_dir / "model_selection_final" / "validated_model_comparison.csv") if (results_dir / "model_selection_final" / "validated_model_comparison.csv").exists() else []
    promoted_examples = read_csv(results_dir / "final_analysis" / "promoted_model_examples.csv") if (results_dir / "final_analysis" / "promoted_model_examples.csv").exists() else []
    novelty_metrics = read_csv(results_dir / "analysis" / "ocr_metrics_by_test_label_novelty.csv") if (results_dir / "analysis" / "ocr_metrics_by_test_label_novelty.csv").exists() else []
    ocr_all_by_config = {
        (row.get("model_name"), row.get("model_version"), row.get("preprocessing_id")): row
        for row in ocr_metrics
        if row.get("scope") == "all"
    }

    lines = [
        "# Data 3: Real Handwritten Prescription OCR Benchmark",
        "",
        "## Executive Summary",
        "",
        "Data 3 evaluates three different questions separately: raw handwriting OCR, medicine-search recovery from real OCR errors, and the end-to-end image-to-medicine outcome. It does not merge these into one misleading accuracy number.",
        "",
        f"- RxHandBD rows audited: `{audit.get('official_rows', 0):,}`.",
        f"- Official train/test split: `{audit.get('split_counts', {}).get('train', 0):,}` / `{audit.get('split_counts', {}).get('test', 0):,}`.",
        f"- Unique normalized labels: `{audit.get('unique_ground_truth_normalized', 0):,}`.",
        f"- OCR observations / source-valid scored rows: `{audit.get('ocr_observation_rows', 0):,}` / `{audit.get('ocr_scored_rows', 0):,}`.",
        f"- Exact, unique Egyptian commercial-family mappings: `{audit.get('search_eligible_rows', 0):,}`.",
        f"- Exact mapped rows in the official test split: `{audit.get('search_eligible_test_rows', 0):,}`.",
        f"- Separate exact ingredient-query rows: `{audit.get('ingredient_query_rows', 0):,}`.",
        f"- Accepted OCR-error observations: `{case_summary.get('accepted_observation_cases', 0):,}`.",
        f"- Unique accepted query/target pairs: `{case_summary.get('accepted_unique_query_target_pairs', 0):,}`.",
        f"- Cross-file validation: `{'PASS' if validation.get('passed') else 'NOT YET PASSED'}`.",
        "",
        "The small catalog overlap is a measured limitation: the complete RxHandBD dataset remains valid for OCR evaluation, while only verified Egyptian matches enter the search benchmark.",
        "",
        "## Benchmark Pipeline",
        "",
        "```mermaid",
        "flowchart LR",
        "  A[RxHandBD word image] --> B[OCR model]",
        "  B --> C[OCR transcription metrics]",
        "  B --> D{Verified Egyptian family?}",
        "  D -- No --> E[Rejected with reason or mapping review]",
        "  D -- Yes --> F{Realistic wrong OCR output?}",
        "  F -- No --> G[Exact, empty, or extreme audit class]",
        "  F -- Yes --> H[Algorithms 1-4]",
        "  H --> I[Hit@K, MRR, safety, latency]",
        "```",
        "",
        "## Evidence-Led OCR Upgrade",
        "",
        "The upgrade was selected in stages rather than by trying one model on the official test set. Image profiling first identified large white margins, variable contrast, and a strong accuracy decline as labels became longer. Preprocessing and model candidates were then screened on training rows, checked on a disjoint training-validation split, and only promoted when they passed the frozen rule. The official test split remained unused for selection and training.",
        "",
        "| Decision stage | Input | Output used for the next decision |",
        "| --- | --- | --- |",
        f"| Image audit | {image_analysis.get('profiled_images', 0):,} RxHandBD crops | Ink geometry, contrast, sharpness, label length, and baseline failure buckets |",
        "| Preprocessing screen | 600 deterministic training rows | Raw, autocontrast, crop, and crop+autocontrast comparisons |",
        "| Disjoint validation | 1,000 training rows excluded from fine-tuning | Repeated preprocessing gain and zero-shot candidate comparison |",
        f"| Domain fine-tuning | {training_run.get('train_rows', 0):,} train rows | Best checkpoint chosen by exact accuracy then CER |",
        f"| Frozen full run | {promoted_summary.get('ocr_eligible_rows', 0):,} OCR-eligible images | Primary all-data and official-test OCR results |",
        "",
        "The research matrix in `docs/OCR_CANDIDATE_RESEARCH.md` covers TrOCR Base/Large, PaddleOCR, GOT-OCR2, Donut, DeepSeek-OCR, PaddleOCR-VL, Qwen2.5-VL, and commercial OCR APIs. Models blocked by incompatible input, unavailable hardware, credentials, or privacy approval are listed explicitly instead of receiving invented scores.",
        "",
        "## Dataset Audit",
        "",
        "| Check | Result |",
        "| --- | ---: |",
        f"| Valid labeled rows | {audit.get('official_rows', 0):,} |",
        f"| Blank labels | {audit.get('blank_ground_truth', 0):,} |",
        f"| Nonblank uncertain-placeholder labels | {audit.get('uncertain_ground_truth_placeholders', 0):,} |",
        f"| Invalid images | {len(audit.get('invalid_images', [])):,} |",
        f"| Raw/ML pixel mismatches | {audit.get('raw_copy_mismatches', 0):,} |",
        f"| Label disagreements | {len(audit.get('label_disagreements', [])):,} |",
        f"| Cross-split duplicate image groups | {len(audit.get('cross_split_duplicate_groups', [])):,} |",
        f"| Duplicate groups with conflicting labels | {len(audit.get('duplicate_label_conflict_groups', [])):,} |",
        f"| Conflicting-label rows excluded from scoring | {audit.get('duplicate_label_conflict_rows', 0):,} |",
        f"| Egyptian catalog families | {audit.get('catalog_family_count', 0):,} |",
        "",
        "### Conflicting Duplicate Labels",
        "",
        "These rows contain identical decoded pixels but different supplied labels. They are processed by OCR, retained for traceability, and excluded from accuracy denominators.",
        "",
        "| Duplicate group | Supplied labels | Split |",
        "| ---: | --- | --- |",
    ]
    conflict_groups: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for row in duplicate_audit:
        if row.get("label_conflict") == "1":
            conflict_groups[row["duplicate_group"]].append(row)
    for group, rows in sorted(conflict_groups.items(), key=lambda item: int(item[0])):
        labels = "; ".join(sorted({row["ground_truth_normalized"] for row in rows}))
        splits = "; ".join(sorted({row["split"] for row in rows}))
        lines.append(f"| {md_escape(group)} | {md_escape(labels)} | {md_escape(splits)} |")

    lines.extend([
        "",
        "## Catalog Mapping Outcomes",
        "",
        "| Mapping status | Rows |",
        "| --- | ---: |",
    ])
    for status, count in sorted(audit.get("mapping_counts", {}).items()):
        lines.append(f"| {md_escape(status)} | {int(count):,} |")

    lines.extend([
        "",
        "## OCR Results",
        "",
        "| Model | Version | Preprocessing | Observed | Scored | Source excluded | Exact | WER | Mean CER | Empty | Mean latency |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in ocr_summaries:
        metric = ocr_all_by_config.get(
            (row.get("model_name"), row.get("model_version"), row.get("preprocessing_id")),
            {},
        )
        lines.append(
            "| {model} | {version} | {prep} | {observed:,} | {scored:,} | {excluded:,} | {exact} | {wer} | {distance:.4f} | {empty} | {latency:.1f} ms |".format(
                model=md_escape(row.get("model_name")),
                version=display_version(row.get("model_version")),
                prep=md_escape(row.get("preprocessing_id")),
                observed=int(row.get("completed_rows") or 0),
                scored=int(metric.get("scored_rows") or row.get("successful_rows") or 0),
                excluded=int(metric.get("source_excluded_rows") or 0),
                exact=percent(metric.get("exact_match_accuracy", row.get("exact_match_accuracy"))),
                wer=percent(metric.get("word_error_rate", 1 - float(row.get("exact_match_accuracy") or 0))),
                distance=float(metric.get("mean_character_error_rate", row.get("mean_normalized_edit_distance")) or 0),
                empty=percent(metric.get("empty_output_rate", row.get("empty_output_rate"))),
                latency=float(row.get("mean_latency_ms") or 0),
            )
        )

    lines.extend([
        "",
        "### Train-Only Model Selection",
        "",
        "The promotion rule required a model to be within five exact-accuracy points of the best validated model and to contribute at least two percent unique exact recoveries. After domain fine-tuning, only the fine-tuned TrOCR checkpoint passed. Oracle unions are diagnostic upper bounds, not deployable scores.",
        "",
        "| Model | Preprocessing | Validation rows | Exact | CER | Short exact | Medium exact | Long exact | Unique exact | Promoted |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for row in model_selection_rows:
        lines.append(
            f"| {md_escape(row['model_name'])} | {md_escape(row['preprocessing_id'])} | "
            f"{int(row['rows']):,} | {percent(row['exact_accuracy'])} | "
            f"{float(row['mean_character_error_rate']):.4f} | "
            f"{percent(row['short_exact_accuracy'])} | {percent(row['medium_exact_accuracy'])} | "
            f"{percent(row['long_exact_accuracy'])} | {int(row['unique_exact_vs_all_other_models']):,} | "
            f"{'YES' if row['promoted_to_full'] == '1' else 'NO'} |"
        )

    lines.extend([
        "",
        "### Domain Fine-Tuning Curve",
        "",
        f"Training used `{training_run.get('train_rows', 0):,}` rows, validation used a disjoint `{training_run.get('validation_rows', 0):,}` rows, and official-test rows used for selection were `{training_run.get('official_test_rows_used', 0):,}`. The frozen checkpoint SHA-256 is `{training_run.get('best_model_sha256', '')}`.",
        "",
        "| Stage | Validation exact | Validation CER | Mean training loss |",
        "| --- | ---: | ---: | ---: |",
    ])
    baseline_validation = training_run.get("baseline_validation", {})
    if baseline_validation:
        lines.append(
            f"| Zero-shot baseline | {percent(baseline_validation.get('exact_accuracy'))} | "
            f"{float(baseline_validation.get('mean_character_error_rate') or 0):.4f} | -- |"
        )
    for epoch in training_run.get("history", []):
        epoch_validation = epoch.get("validation", {})
        lines.append(
            f"| Epoch {int(epoch.get('epoch') or 0)} | "
            f"{percent(epoch_validation.get('exact_accuracy'))} | "
            f"{float(epoch_validation.get('mean_character_error_rate') or 0):.4f} | "
            f"{float(epoch.get('mean_train_loss') or 0):.4f} |"
        )

    lines.extend([
        "",
        "### Training-Only Calibration and Smoke Tests",
        "",
        "These small runs select a feasible configuration and catch adapter failures. They are not official benchmark scores and use different sample counts.",
        "",
        "| Model | Version | Preprocessing | Rows | Exact | Mean normalized edit distance | Empty | Mean latency |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in calibration_summaries:
        lines.append(
            f"| {md_escape(row.get('model_name'))} | {display_version(row.get('model_version'))} | "
            f"{md_escape(row.get('preprocessing_id'))} | "
            f"{int(row.get('successful_rows') or 0):,} | {percent(row.get('exact_match_accuracy'))} | "
            f"{float(row.get('mean_normalized_edit_distance') or 0):.4f} | "
            f"{percent(row.get('empty_output_rate'))} | {float(row.get('mean_latency_ms') or 0):.1f} ms |"
        )

    lines.extend([
        "",
        "### Secondary Full Configurations (Excluded from Primary Aggregate)",
        "",
        "| Model | Version | Rows | Exact | Mean normalized edit distance | Empty | Mean latency |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in secondary_summaries:
        lines.append(
            f"| {md_escape(row.get('model_name'))} | {display_version(row.get('model_version'))} | "
            f"{int(row.get('successful_rows') or 0):,} | {percent(row.get('exact_match_accuracy'))} | "
            f"{float(row.get('mean_normalized_edit_distance') or 0):.4f} | "
            f"{percent(row.get('empty_output_rate'))} | {float(row.get('mean_latency_ms') or 0):.1f} ms |"
        )

    lines.extend([
        "",
        "### Official Test Split",
        "",
        "| Model | Rows | Exact | CER | WER | Empty | Median latency | P95 latency |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in ocr_metrics:
        if row.get("scope") != "split:test":
            continue
        lines.append(
            f"| {md_escape(row['model_name'])} | {int(row['successful_rows']):,} | "
            f"{percent(row['exact_match_accuracy'])} | {float(row['mean_character_error_rate']):.4f} | "
            f"{percent(row['word_error_rate'])} | {percent(row['empty_output_rate'])} | "
            f"{float(row['median_latency_ms']):.1f} ms | {float(row['p95_latency_ms']):.1f} ms |"
        )

    lines.extend([
        "",
        "### Official-Test Label Novelty",
        "",
        "A test label is `seen_in_train` when the same compact transcription occurs anywhere in the fine-tuning split. The unseen rows are the stricter vocabulary-generalization check.",
        "",
        "| Model | Test-label group | Rows | Exact | CER |",
        "| --- | --- | ---: | ---: | ---: |",
    ])
    for row in novelty_metrics:
        lines.append(
            f"| {md_escape(row['model_name'])} | {md_escape(row['label_novelty'])} | "
            f"{int(row['rows']):,} | {percent(row['exact_accuracy'])} | "
            f"{float(row['mean_character_error_rate']):.4f} |"
        )

    lines.extend([
        "",
        "### Promoted-Model Input/Output Examples",
        "",
        "These examples come only from the untouched official test split and are selected by deterministic rules. They show both improvements and remaining errors; they are not hand-picked success cases.",
        "",
        "| Type | Image input | Expected text | Promoted output | Comparator outputs | Novelty |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    per_type = collections.Counter()
    displayed_sample_ids = set()
    for row in promoted_examples:
        example_type = row.get("example_type", "")
        if per_type[example_type] >= 3 or row.get("sample_id") in displayed_sample_ids:
            continue
        per_type[example_type] += 1
        displayed_sample_ids.add(row.get("sample_id"))
        lines.append(
            f"| {md_escape(example_type)} | `{md_escape(row.get('image_id'))}` | "
            f"`{md_escape(row.get('ground_truth'))}` | `{md_escape(row.get('candidate_output'))}` | "
            f"{md_escape(row.get('comparator_outputs'))} | {md_escape(row.get('label_novelty'))} |"
        )

    lines.extend([
        "",
        "## Model Execution Status",
        "",
        "| System | Type | Independent | Status | Rows | Reason or scope |",
        "| --- | --- | ---: | --- | ---: | --- |",
    ])
    for row in execution_status:
        lines.append(
            f"| {md_escape(row['system'])} | {md_escape(row['system_type'])} | "
            f"{md_escape(row['independent_model'])} | {md_escape(row['status'])} | "
            f"{int(row['completed_rows'] or 0):,} | {md_escape(row['reason_or_scope'])} |"
        )

    lines.extend([
        "",
        "## Search-Case Filtering",
        "",
        "Only unique exact catalog mappings are automatic ground truth. Fuzzy catalog matches remain review suggestions. Wrong OCR outputs that exactly equal another real Egyptian family are preserved as dangerous collision cases.",
        "",
        "| Outcome | Count |",
        "| --- | ---: |",
        f"| Accepted OCR observations | {case_summary.get('accepted_observation_cases', 0):,} |",
        f"| Accepted official-test observations | {case_summary.get('accepted_test_cases', 0):,} |",
        f"| Dangerous real-drug collisions | {case_summary.get('dangerous_collision_cases', 0):,} |",
        f"| Rejected observations | {case_summary.get('rejected_rows', 0):,} |",
        "",
        "### Rejection Breakdown",
        "",
        "| Reason | Rows |",
        "| --- | ---: |",
    ])
    for reason, count in sorted(case_summary.get("rejection_counts", {}).items()):
        lines.append(f"| {md_escape(reason)} | {int(count):,} |")

    lines.extend([
        "",
        "### Accepted Mistake Types",
        "",
        "| Mistake type | Rows |",
        "| --- | ---: |",
    ])
    for mistake, count in sorted(case_summary.get("mistake_type_counts", {}).items()):
        lines.append(f"| {md_escape(mistake)} | {int(count):,} |")

    lines.extend([
        "",
        "## Search Results",
        "",
        "| Algorithm | Cases | Hit@1 | Hit@5 | Hit@20 | MRR@20 | Unsafe confident top-1 | Mean latency |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in search_metrics:
        if row.get("scope") != "all":
            continue
        lines.append(
            f"| {md_escape(row['algorithm'])} | {int(row['cases']):,} | {percent(row['hit_at_1'])} | "
            f"{percent(row['hit_at_5'])} | {percent(row['hit_at_20'])} | {float(row['mrr_at_20']):.4f} | "
            f"{percent(row['unsafe_confident_top1_rate'])} | {float(row['mean_latency_ms']):.2f} ms |"
        )

    by_case: dict[str, dict[str, tuple[str, str, str]]] = collections.defaultdict(dict)
    tied_algorithms = {
        "algorithm_2_external_fast",
        "algorithm_3_rank_fusion",
        "algorithm_4_family_rescue",
    }
    for row in search_results:
        if row.get("algorithm") not in tied_algorithms:
            continue
        by_case[row["case_id"]][row["algorithm"]] = (
            row.get("top_20", ""),
            row.get("response_status", ""),
            row.get("decision_type", ""),
        )
    complete_tie_cases = [values for values in by_case.values() if set(values) == tied_algorithms]
    identical_tie_cases = sum(len(set(values.values())) == 1 for values in complete_tie_cases)
    lines.extend([
        "",
        f"Algorithms 2, 3, and 4 returned identical top-20 lists and decision states on `{identical_tie_cases:,}` of `{len(complete_tie_cases):,}` accepted cases. Their tie is genuine for this narrow subset, but the subset does not discriminate their broader ranking behavior.",
    ])

    lines.extend([
        "",
        "### Search Results by Split and OCR Model",
        "",
        "| Algorithm | Scope | Cases | Hit@1 | Hit@20 | MRR@20 | Unsafe |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in search_metrics:
        if not (row.get("scope", "").startswith("split:") or row.get("scope", "").startswith("ocr:")):
            continue
        lines.append(
            f"| {md_escape(row['algorithm'])} | {md_escape(row['scope'])} | {int(row['cases']):,} | "
            f"{percent(row['hit_at_1'])} | {percent(row['hit_at_20'])} | "
            f"{float(row['mrr_at_20']):.4f} | {percent(row['unsafe_confident_top1_rate'])} |"
        )

    lines.extend([
        "",
        "### Search Results by OCR Difficulty",
        "",
        "| Algorithm | Difficulty | Cases | Hit@1 | Hit@5 | Hit@20 | MRR@20 | Unsafe |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in search_metrics:
        if not row.get("scope", "").startswith("difficulty:"):
            continue
        lines.append(
            f"| {md_escape(row['algorithm'])} | {md_escape(row['scope'].split(':', 1)[1])} | "
            f"{int(row['cases']):,} | {percent(row['hit_at_1'])} | {percent(row['hit_at_5'])} | "
            f"{percent(row['hit_at_20'])} | {float(row['mrr_at_20']):.4f} | "
            f"{percent(row['unsafe_confident_top1_rate'])} |"
        )

    lines.extend([
        "",
        "### Search Results by OCR Mistake Type",
        "",
        "| Algorithm | Mistake type | Cases | Hit@1 | Hit@20 | MRR@20 | Unsafe | Clarification |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in search_metrics:
        if not row.get("scope", "").startswith("mistake:"):
            continue
        lines.append(
            f"| {md_escape(row['algorithm'])} | {md_escape(row['scope'].split(':', 1)[1])} | "
            f"{int(row['cases']):,} | {percent(row['hit_at_1'])} | {percent(row['hit_at_20'])} | "
            f"{float(row['mrr_at_20']):.4f} | {percent(row['unsafe_confident_top1_rate'])} | "
            f"{percent(row['clarification_rate'])} |"
        )

    lines.extend([
        "",
        "### Search Results by Safety Label",
        "",
        "| Algorithm | Danger | Cases | Hit@1 | Hit@20 | Unsafe | Clarification |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in search_metrics:
        if not row.get("scope", "").startswith("danger:"):
            continue
        lines.append(
            f"| {md_escape(row['algorithm'])} | {md_escape(row['scope'].split(':', 1)[1])} | "
            f"{int(row['cases']):,} | {percent(row['hit_at_1'])} | {percent(row['hit_at_20'])} | "
            f"{percent(row['unsafe_confident_top1_rate'])} | {percent(row['clarification_rate'])} |"
        )

    lines.extend([
        "",
        "## End-to-End Image-to-Medicine Results",
        "",
        "This table includes every uniquely catalog-mapped OCR observation, including exact OCR, empty output, and severe corruption. It therefore answers a different question from OCR-error recovery.",
        "",
        "| Algorithm | Cases | Hit@1 | Hit@5 | Hit@20 | MRR@20 | Unsafe confident top-1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in end_to_end_metrics:
        if row.get("scope") != "all":
            continue
        lines.append(
            f"| {md_escape(row['algorithm'])} | {int(row['cases']):,} | {percent(row['hit_at_1'])} | "
            f"{percent(row['hit_at_5'])} | {percent(row['hit_at_20'])} | {float(row['mrr_at_20']):.4f} | "
            f"{percent(row['unsafe_confident_top1_rate'])} |"
        )

    lines.extend([
        "",
        "## Representative Accepted Cases",
        "",
        "| OCR input | Expected Egyptian family | OCR model | Difficulty | Mistake type | Danger |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    accepted = [row for row in search_cases if row.get("accepted") == "1"]
    accepted.sort(key=lambda row: (row.get("danger") != "DANGEROUS", row.get("difficulty", ""), row.get("case_id", "")))
    seen_types = set()
    examples = []
    for row in accepted:
        key = row.get("mistake_type")
        if key not in seen_types or len(examples) < 3:
            examples.append(row)
            seen_types.add(key)
        if len(examples) >= 10:
            break
    for row in examples:
        lines.append(
            f"| `{md_escape(row['input'])}` | `{md_escape(row['expected_family_name'])}` | "
            f"{md_escape(row['model_name'])} | {md_escape(row['difficulty'])} | "
            f"{md_escape(row['mistake_type'])} | {md_escape(row['danger'])} |"
        )

    lines.extend([
        "",
        "## Interpretation Rules",
        "",
        "- OCR exact accuracy measures transcription only; search cannot receive credit for OCR success.",
        "- Same-pixel rows with contradictory source labels are processed but excluded from scoring; no label is guessed.",
        "- Search recovery is measured only on wrong, non-empty OCR outputs with verified Egyptian targets.",
        "- End-to-end success means the final search ranking contains the verified family after starting from the image.",
        "- Results from RxHandBD training images and official test images are reported separately.",
        "- No fuzzy catalog suggestion is accepted as ground truth without review.",
        "- Model or API systems that could not be executed are listed in the execution-status table rather than omitted.",
        "- The benchmark is publishable as an OCR study, but the Egyptian search-recovery subset remains exploratory until its verified overlap is materially larger.",
        "",
        "## Validation Contract",
        "",
        f"Overall validation status: **{'PASS' if validation.get('passed') else 'NOT PASSED'}**.",
        "",
        "| Validation check | Status | Expected rows | Actual rows |",
        "| --- | --- | ---: | ---: |",
    ])
    for check in validation.get("checks", []):
        lines.append(
            f"| {md_escape(check.get('check'))} | {'PASS' if check.get('passed') else 'FAIL'} | "
            f"{int(check.get('expected_rows') or check.get('expected_cases_per_algorithm') or 0):,} | "
            f"{int(check.get('actual_rows') or 0):,} |"
        )

    lines.extend([
        "",
        "## Known Limitations",
        "",
        "- RxHandBD is a Bangladesh-oriented word-image dataset, so overlap with the Egyptian catalog is naturally limited.",
        "- Word crops do not measure full-prescription text detection or layout understanding.",
        "- The dataset does not provide writer identifiers, so writer-disjoint leakage cannot be independently verified.",
        "- Commercial APIs require credentials, privacy approval, and an identical deidentified sample before comparison.",
        "- Fuzzy mapping review can expand coverage later, but those rows must not enter the benchmark automatically.",
        "",
        "## Reproduction",
        "",
        "See `README.md` for the exact commands, dependency isolation, output contract, and execution-status policy.",
        "",
    ])
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

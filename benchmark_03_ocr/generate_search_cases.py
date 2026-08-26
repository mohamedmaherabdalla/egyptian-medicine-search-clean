#!/usr/bin/env python3
"""Convert wrong OCR observations into auditable Egyptian search cases."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from benchmark_common import (
    DEFAULT_ARTIFACTS_DIR,
    DEFAULT_CATALOG_PATH,
    DEFAULT_DATA_DIR,
    DEFAULT_RESULTS_DIR,
    catalog_alias_index,
    compact_text,
    difficulty_for_distance,
    levenshtein,
    load_catalog_families,
    normalize_text,
    read_csv,
    stable_id,
    write_csv,
    write_json,
)


CASE_FIELDS = [
    "case_id", "observation_id", "sample_id", "image_id", "split", "model_name",
    "model_version", "preprocessing_id", "input", "expected_family_key",
    "expected_family_name", "ground_truth_raw", "ground_truth_in_egypt_db",
    "ocr_output_in_egypt_db", "ocr_output_catalog_families", "edit_distance",
    "normalized_edit_distance", "difficulty", "mistake_type", "danger",
    "analysis_cohort", "distance_band",
    "dangerous_collision_families", "shared_character_count", "shared_ngram_count",
    "source_ground_truth_usable", "source_exclusion_reason", "accepted", "scored_case",
    "rejection_reason", "source_edit_distance", "source_additions_count",
    "source_deletions_count", "source_flip_count", "source_matches_count",
    "source_edited_length", "source_canonical_length", "source_length_difference",
    "source_edit_distance_over_edited_length",
    "source_edit_distance_over_canonical_length",
    "source_similarity_over_canonical_length", "source_operation_sequence", "provenance",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("observations", nargs="+", type=Path)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_DATA_DIR / "catalog_mapping.csv")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_DATA_DIR / "dataset_manifest.csv")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--raw-output-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--max-distance", type=float, default=0.60)
    return parser.parse_args()


def grams(value: str, size: int = 2) -> set[str]:
    if len(value) < size:
        return {value} if value else set()
    return {value[index:index + size] for index in range(len(value) - size + 1)}


def classify_mistake(output: str, expected: str, distance: int, collisions: set[str]) -> str:
    if collisions:
        return "real_drug_name_collision"
    if output and len(output) >= 3 and (expected.startswith(output) or expected.endswith(output)):
        return "visible_prefix_or_suffix_fragment"
    if output and len(output) >= 3 and output in expected:
        return "visible_internal_fragment"
    if distance == 1:
        return "single_edit_ocr_error"
    if distance in {2, 3}:
        return "two_or_three_edit_ocr_error"
    return "multi_edit_ocr_error"


def distance_band(distance: int) -> str:
    if distance == 0:
        return "0_exact_after_normalization"
    if distance == 1:
        return "1_single_edit"
    if distance <= 3:
        return "2_3_edits"
    if distance <= 5:
        return "4_5_edits"
    return "6_plus_edits"


def prediction_analysis_cohort(
    query: str,
    expected: str,
    normalized_distance: float,
    maximum_standard_distance: float,
    collisions: set[str],
    shared_characters: int,
    shared_grams: int,
) -> str:
    """Describe every mapped prediction without using severity as an exclusion rule."""

    if collisions:
        return "real_drug_name_collision"
    if query == expected:
        return "normalized_exact_match"
    if normalized_distance > maximum_standard_distance:
        return "extreme_distance_prediction"
    if len(query) < 2 or shared_characters == 0 or (shared_grams == 0 and shared_characters < 2):
        return "limited_character_evidence"
    if query and len(query) >= 3 and query in expected:
        return "visible_name_fragment"
    if normalized_distance > 0.40:
        return "high_distance_prediction"
    return "standard_ocr_error"


def rejection_reason(
    observation: dict[str, str],
    mapping: dict[str, str] | None,
    max_distance: float,
    collisions: set[str],
    shared_characters: int,
    shared_grams: int,
    source_ground_truth_usable: bool,
    source_exclusion_reason: str,
) -> str:
    if not source_ground_truth_usable:
        return f"source_ground_truth_excluded:{source_exclusion_reason or 'unspecified'}"
    if observation.get("run_status") != "ok":
        return "ocr_runtime_error"
    if not mapping or mapping.get("eligible_for_search_benchmark") != "1":
        return "ground_truth_not_uniquely_catalog_resolved"
    if observation.get("empty_output") == "1":
        return "empty_ocr_output"
    if observation.get("exact_match") == "1":
        return "ocr_exact_match_not_an_error_case"
    if collisions:
        return ""
    if float(observation.get("normalized_edit_distance") or 999) > max_distance:
        return "extreme_distance_requires_manual_review"
    if len(compact_text(observation.get("ocr_output_raw"))) < 2:
        return "too_little_textual_evidence"
    if shared_characters == 0 or (shared_grams == 0 and shared_characters < 2):
        return "insufficient_shared_character_evidence"
    return ""


def resolve_target_keys(target: str, families: list) -> tuple[str, ...]:
    """Resolve a supplied medicine label to exact or explicit catalog variants."""

    target_key = compact_text(target)
    exact = tuple(family.key for family in families if family.key == target_key)
    if exact:
        return exact
    target_name = normalize_text(target)
    if len(target_key) < 4:
        return ()
    return tuple(
        family.key
        for family in families
        if normalize_text(family.name).startswith(f"{target_name} ")
    )


def target_split(target_key: str) -> str:
    """Keep all observations for one medicine family in one evaluation split."""

    bucket = int(stable_id("ocr-target-split", target_key, length=8), 16) % 3
    return "holdout" if bucket == 0 else "development"


def flat_prediction_cases(
    observations: list[dict[str, str]],
    families: list,
    max_distance: float,
) -> list[dict[str, object]]:
    """Adapt OCR predictions that already contain their source ground truth."""

    family_by_key = {family.key: family for family in families}
    alias_index = catalog_alias_index(families)
    output: list[dict[str, object]] = []
    for source_row, observation in enumerate(observations, 1):
        raw_query = str(observation.get("edited_name") or "").strip()
        raw_target = str(observation.get("matched_canonical_name_norm") or "").strip()
        query_key = compact_text(raw_query)
        target_key = compact_text(raw_target)
        expected_keys = resolve_target_keys(raw_target, families)
        expected_key_set = set(expected_keys)
        output_catalog_keys = set(alias_index.get(query_key, ()))
        collision_keys = output_catalog_keys - expected_key_set
        distance = levenshtein(query_key, target_key)
        normalized_distance = distance / max(len(target_key), 1)
        shared_characters = len(set(query_key) & set(target_key))
        shared_grams = len(grams(query_key) & grams(target_key))

        if not expected_keys:
            reason = "ground_truth_not_catalog_resolved"
        elif not query_key:
            reason = "empty_ocr_output"
        else:
            reason = ""

        collision_names = [
            family_by_key[key].name for key in sorted(collision_keys) if key in family_by_key
        ]
        output_catalog_names = [
            family_by_key[key].name for key in sorted(output_catalog_keys) if key in family_by_key
        ]
        accepted = not reason
        mistake_type = classify_mistake(query_key, target_key, distance, collision_keys)
        cohort = prediction_analysis_cohort(
            query_key,
            target_key,
            normalized_distance,
            max_distance,
            collision_keys,
            shared_characters,
            shared_grams,
        )
        if collision_keys:
            danger = "DANGEROUS"
        elif len(query_key) <= 4 or normalized_distance > 0.40:
            danger = "CAUTION"
        else:
            danger = "SAFE"
        model_name = str(observation.get("source_model") or "unknown")
        observation_id = stable_id(
            "flat-ocr-prediction", source_row, model_name, query_key, target_key
        )
        output.append({
            "case_id": stable_id("flat-ocr-search", observation_id),
            "observation_id": observation_id,
            "sample_id": f"{model_name}:{source_row}",
            "image_id": "",
            "split": target_split(target_key),
            "model_name": model_name,
            "model_version": "",
            "preprocessing_id": "provided_prediction",
            "input": raw_query,
            "expected_family_key": ";".join(expected_keys),
            "expected_family_name": raw_target,
            "ground_truth_raw": raw_target,
            "ground_truth_in_egypt_db": int(bool(expected_keys)),
            "ocr_output_in_egypt_db": int(bool(output_catalog_keys)),
            "ocr_output_catalog_families": ";".join(output_catalog_names),
            "edit_distance": distance,
            "normalized_edit_distance": round(normalized_distance, 8),
            "difficulty": difficulty_for_distance(
                normalized_distance,
                exact=query_key == target_key,
                empty=not query_key,
            ),
            "mistake_type": mistake_type,
            "danger": danger,
            "analysis_cohort": cohort,
            "distance_band": distance_band(distance),
            "dangerous_collision_families": ";".join(collision_names),
            "shared_character_count": shared_characters,
            "shared_ngram_count": shared_grams,
            "source_ground_truth_usable": int(bool(expected_keys)),
            "source_exclusion_reason": "" if expected_keys else "target_not_in_catalog",
            "accepted": int(accepted),
            "scored_case": int(accepted and not collision_keys),
            "rejection_reason": reason,
            "source_edit_distance": observation.get("edit_distance_count", ""),
            "source_additions_count": observation.get("additions_count", ""),
            "source_deletions_count": observation.get("deletions_count", ""),
            "source_flip_count": observation.get("flip_count", ""),
            "source_matches_count": observation.get("matches_count", ""),
            "source_edited_length": observation.get("edited_length", ""),
            "source_canonical_length": observation.get("canonical_length", ""),
            "source_length_difference": observation.get("length_difference", ""),
            "source_edit_distance_over_edited_length": observation.get(
                "edit_distance_over_edited_length", ""
            ),
            "source_edit_distance_over_canonical_length": observation.get(
                "edit_distance_over_canonical_length", ""
            ),
            "source_similarity_over_canonical_length": observation.get(
                "similarity_over_canonical_length", ""
            ),
            "source_operation_sequence": observation.get("operation_sequence", ""),
            "provenance": f"Provided OCR prediction from {model_name}; source row {source_row}.",
        })
    return output


def main() -> int:
    args = parse_args()
    families = load_catalog_families(args.catalog)
    observations = []
    for path in args.observations:
        observations.extend(read_csv(path))
    if observations and "edited_name" in observations[0]:
        output = flat_prediction_cases(observations, families, args.max_distance)
    else:
        mapping_by_sample = {row["sample_id"]: row for row in read_csv(args.mapping)}
        manifest_by_sample = {row["sample_id"]: row for row in read_csv(args.manifest)}
        output = mapped_observation_cases(
            observations,
            families,
            mapping_by_sample,
            manifest_by_sample,
            args.max_distance,
        )

    output.sort(key=lambda row: (str(row["accepted"]), str(row["model_name"]), str(row["case_id"])))
    accepted_rows = [row for row in output if row["accepted"] == 1]
    rejected_rows = [row for row in output if row["accepted"] == 0]
    write_csv(args.raw_output_dir / "search_cases.csv", output, CASE_FIELDS)

    reason_counts = collections.Counter(str(row["rejection_reason"]) for row in rejected_rows)
    mistake_counts = collections.Counter(str(row["mistake_type"]) for row in accepted_rows)
    cohort_counts = collections.Counter(str(row["analysis_cohort"]) for row in accepted_rows)
    distance_band_counts = collections.Counter(str(row["distance_band"]) for row in accepted_rows)
    unique_pairs = {(compact_text(row["input"]), row["expected_family_key"]) for row in accepted_rows}
    summary = {
        "input_format": "predictions_with_targets" if observations and "edited_name" in observations[0] else "mapped_ocr_observations",
        "observation_rows": len(output),
        "accepted_observation_cases": len(accepted_rows),
        "scored_observation_cases": sum(int(row.get("scored_case") or 0) for row in accepted_rows),
        "accepted_unique_query_target_pairs": len(unique_pairs),
        "accepted_test_cases": sum(row["split"] in {"test", "holdout"} for row in accepted_rows),
        "accepted_cases_by_split": dict(sorted(collections.Counter(str(row["split"]) for row in accepted_rows).items())),
        "accepted_cases_by_model": dict(sorted(collections.Counter(str(row["model_name"]) for row in accepted_rows).items())),
        "dangerous_collision_cases": sum(row["danger"] == "DANGEROUS" for row in accepted_rows),
        "rejected_rows": len(rejected_rows),
        "rejection_counts": dict(sorted(reason_counts.items())),
        "mistake_type_counts": dict(sorted(mistake_counts.items())),
        "analysis_cohort_counts": dict(sorted(cohort_counts.items())),
        "distance_band_counts": dict(sorted(distance_band_counts.items())),
        "filter_policy": {
            "maximum_standard_normalized_edit_distance": args.max_distance,
            "distance_is_a_reporting_cohort_not_an_exclusion_rule_for_prediction_exports": True,
            "normalized_exact_predictions_are_preserved": True,
            "dangerous_real-drug_collisions_are_preserved": True,
            "fuzzy_catalog_suggestions_are_never_ground_truth": True,
            "target_family_split_prevents_development_holdout_leakage": True,
        },
    }
    write_json(args.results_dir / "search_case_generation_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def mapped_observation_cases(
    observations: list[dict[str, str]],
    families: list,
    mapping_by_sample: dict[str, dict[str, str]],
    manifest_by_sample: dict[str, dict[str, str]],
    max_distance: float,
) -> list[dict[str, object]]:
    """Build cases from OCR observations that require dataset mapping files."""

    family_by_key = {family.key: family for family in families}
    alias_index = catalog_alias_index(families)
    output = []
    for observation in observations:
        mapping = mapping_by_sample.get(observation.get("sample_id", ""))
        source_row = manifest_by_sample.get(observation.get("sample_id", ""), {})
        source_ground_truth_usable = source_row.get("ground_truth_usable") == "1"
        source_exclusion_reason = str(source_row.get("exclusion_reason") or "")
        expected_key = str(mapping.get("expected_family_key") if mapping else "")
        output_key = compact_text(observation.get("ocr_output_raw"))
        output_catalog_keys = set(alias_index.get(output_key, ()))
        collision_keys = output_catalog_keys - ({expected_key} if expected_key else set())
        expected_compact = expected_key
        shared_characters = len(set(output_key) & set(expected_compact))
        shared_grams = len(grams(output_key) & grams(expected_compact))
        reason = rejection_reason(
            observation,
            mapping,
            max_distance,
            collision_keys,
            shared_characters,
            shared_grams,
            source_ground_truth_usable,
            source_exclusion_reason,
        )
        distance = int(observation.get("edit_distance") or levenshtein(output_key, expected_compact))
        collision_names = [family_by_key[key].name for key in sorted(collision_keys) if key in family_by_key]
        output_catalog_names = [
            family_by_key[key].name for key in sorted(output_catalog_keys) if key in family_by_key
        ]
        accepted = not reason
        mistake_type = classify_mistake(output_key, expected_compact, distance, collision_keys)
        if collision_keys:
            danger = "DANGEROUS"
        elif len(output_key) <= 4 or float(observation.get("normalized_edit_distance") or 0) > 0.40:
            danger = "CAUTION"
        else:
            danger = "SAFE"
        output.append({
            "case_id": stable_id("data3-search", observation.get("observation_id")),
            "observation_id": observation.get("observation_id", ""),
            "sample_id": observation.get("sample_id", ""),
            "image_id": observation.get("image_id", ""),
            "split": observation.get("split", ""),
            "model_name": observation.get("model_name", ""),
            "model_version": observation.get("model_version", ""),
            "preprocessing_id": observation.get("preprocessing_id", ""),
            "input": observation.get("ocr_output_raw", ""),
            "expected_family_key": expected_key,
            "expected_family_name": mapping.get("expected_family_name", "") if mapping else "",
            "ground_truth_raw": observation.get("ground_truth_raw", ""),
            "ground_truth_in_egypt_db": int(
                bool(mapping and mapping.get("eligible_for_search_benchmark") == "1")
            ),
            "ocr_output_in_egypt_db": int(bool(output_catalog_keys)),
            "ocr_output_catalog_families": ";".join(output_catalog_names),
            "edit_distance": distance,
            "normalized_edit_distance": observation.get("normalized_edit_distance", ""),
            "difficulty": observation.get("difficulty", ""),
            "mistake_type": mistake_type,
            "danger": danger,
            "analysis_cohort": "legacy_mapped_ocr_observation",
            "distance_band": distance_band(distance),
            "dangerous_collision_families": ";".join(collision_names),
            "shared_character_count": shared_characters,
            "shared_ngram_count": shared_grams,
            "source_ground_truth_usable": int(source_ground_truth_usable),
            "source_exclusion_reason": source_exclusion_reason,
            "accepted": int(accepted),
            "scored_case": int(accepted and not collision_keys),
            "rejection_reason": reason,
            "provenance": (
                f"{observation.get('dataset_name') or 'OCR dataset'} image "
                f"{observation.get('image_id')} read by "
                f"{observation.get('model_name')} ({observation.get('preprocessing_id')})."
            ),
        })

    return output


if __name__ == "__main__":
    raise SystemExit(main())

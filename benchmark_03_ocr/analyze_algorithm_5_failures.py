#!/usr/bin/env python3
"""Audit every Algorithm 5 Hit@1 failure in the primary OCR benchmark."""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rapidfuzz import process
from rapidfuzz.distance import Levenshtein, OSA


BENCHMARK_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BENCHMARK_ROOT.parent
DEFAULT_RESULTS = (
    BENCHMARK_ROOT
    / "artifacts/04_model_predictions/algorithm_5_human_evidence_results.csv"
)
DEFAULT_OUTPUT = (
    BENCHMARK_ROOT
    / "artifacts/04_model_predictions/algorithm_5_failure_case_audit.csv"
)
DEFAULT_SIMULATION_OUTPUT = (
    BENCHMARK_ROOT
    / "artifacts/04_model_predictions/algorithm_5_general_rule_simulation.csv"
)
DEFAULT_SOLVABILITY_OUTPUT = (
    BENCHMARK_ROOT
    / "artifacts/04_model_predictions/algorithm_5_failure_solvability.csv"
)
ALGORITHM_5_PATH = (
    PROJECT_ROOT
    / "benchmark_01_legacy/master_algorithms/algorithm_5_commercial_name_search.py"
)
PARETO_CORRECTION_REASON = "pareto_character_evidence_correction"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--simulation-output",
        type=Path,
        default=DEFAULT_SIMULATION_OUTPUT,
    )
    parser.add_argument(
        "--solvability-output",
        type=Path,
        default=DEFAULT_SOLVABILITY_OUTPUT,
    )
    return parser.parse_args()


def compact_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def load_algorithm_5() -> Any:
    module_name = "ocr_failure_audit_algorithm_5"
    spec = importlib.util.spec_from_file_location(module_name, ALGORITHM_5_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load Algorithm 5 from {ALGORITHM_5_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def primary_pairs(results_path: Path) -> pd.DataFrame:
    data = pd.read_csv(results_path, encoding="utf-8-sig", low_memory=False)
    data["query_compact"] = data["input"].map(compact_text)
    unique = data.drop_duplicates(
        ["query_compact", "expected_family_key"],
        keep="first",
    )
    primary = unique[unique["scored_case"] == 1].copy()
    if len(data) != 595 or len(unique) != 477 or len(primary) != 464:
        raise ValueError(
            "unexpected denominator: "
            f"{len(data)} observations, {len(unique)} unique pairs, "
            f"{len(primary)} primary pairs"
        )
    return primary


def catalog_heads(catalog: Any) -> tuple[list[str], dict[str, str]]:
    names: dict[str, str] = {}
    for family in catalog.rescue_index.families:
        key = family.head_compact or family.compact
        name = family.variant_group or family.name
        if key and key not in names:
            names[key] = name
    keys = sorted(names)
    return keys, names


def geometry(
    rows: pd.DataFrame,
    head_keys: list[str],
    head_names: dict[str, str],
    *,
    scorer: Any,
    prefix: str,
) -> pd.DataFrame:
    queries = rows["query_compact"].tolist()
    matrix = process.cdist(
        queries,
        head_keys,
        scorer=scorer,
        dtype=np.int16,
        workers=-1,
    )
    output: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows.itertuples(index=False)):
        expected_key = compact_text(row.expected_family_name)
        expected_distance = int(scorer(queries[row_index], expected_key))
        nearest_distance = int(matrix[row_index].min())
        nearest_indexes = np.flatnonzero(matrix[row_index] == nearest_distance)
        nearest_names = sorted(head_names[head_keys[index]] for index in nearest_indexes)
        if nearest_distance < expected_distance:
            status = "catalog_competitor_strictly_closer"
        elif len(nearest_indexes) == 1:
            status = "expected_unique_nearest"
        else:
            status = "expected_tied_nearest"
        output.append(
            {
                "case_id": row.case_id,
                f"{prefix}_expected_distance": expected_distance,
                f"{prefix}_nearest_distance": nearest_distance,
                f"{prefix}_nearest_count": int(len(nearest_indexes)),
                f"{prefix}_nearest_keys": ";".join(
                    head_keys[index] for index in nearest_indexes
                ),
                f"{prefix}_nearest_names": "; ".join(nearest_names[:12]),
                f"{prefix}_closer_head_count": int(
                    (matrix[row_index] < expected_distance).sum()
                ),
                f"{prefix}_same_distance_head_count": int(
                    (matrix[row_index] == expected_distance).sum()
                ),
                f"{prefix}_geometry": status,
            }
        )
    return pd.DataFrame(output)


def result_name(item: dict[str, Any]) -> str:
    return str(
        item.get("name")
        or item.get("candidate_canonical_name")
        or item.get("commercial_name")
        or ""
    ).strip()


def expected_result(
    results: list[dict[str, Any]],
    expected_keys: set[str],
) -> tuple[int, dict[str, Any]]:
    for rank, item in enumerate(results, 1):
        if compact_text(result_name(item)) in expected_keys:
            return rank, item
    return 999, {}


def rerun_primary(
    primary: pd.DataFrame,
    module: Any,
    catalog: Any,
) -> dict[str, dict[str, Any]]:
    responses: dict[str, dict[str, Any]] = {}
    for row in primary.itertuples(index=False):
        response = module.search_catalog(catalog, row.input, 20)
        results = list(response.get("results") or [])[:20]
        expected_keys = {
            key for key in str(row.expected_family_key).split(";") if key
        }
        expected_rank, _ = expected_result(results, expected_keys)
        rerun_top = result_name(results[0]) if results else ""
        recorded_top = "" if pd.isna(row.top_1) else str(row.top_1)
        if rerun_top != recorded_top or expected_rank != int(row.first_relevant_rank):
            raise ValueError(
                f"rerun mismatch for {row.case_id}: "
                f"{rerun_top!r}/{expected_rank} != "
                f"{recorded_top!r}/{int(row.first_relevant_rank)}"
            )
        responses[row.case_id] = {**response, "results": results}
    if len(responses) != len(primary):
        raise ValueError("primary case IDs are not unique")
    return responses


def operation_profile(row: Any) -> str:
    additions = int(row.source_additions_count)
    deletions = int(row.source_deletions_count)
    replacements = int(row.source_flip_count)
    active = sum(value > 0 for value in (additions, deletions, replacements))
    if active > 1:
        return "mixed_operations"
    if additions:
        return "missing_characters_only"
    if deletions:
        return "extra_characters_only"
    if replacements:
        return "substitutions_only"
    return "formatting_only"


def evidence(module: Any, query: str, target: str, prefix: str) -> dict[str, Any]:
    query_skeleton = module.current_eval.skeleton(query)
    target_skeleton = module.current_eval.skeleton(target)
    query_phonetic = module.current_eval.drug_phonetic_key(query)
    target_phonetic = module.current_eval.drug_phonetic_key(target)
    lcs = module.longest_common_subsequence_length(query, target)
    return {
        f"{prefix}_head": target,
        f"{prefix}_raw_distance": module.damerau(query, target, weighted=False),
        f"{prefix}_weighted_distance": module.damerau(query, target, weighted=True),
        f"{prefix}_visual_distance": module.damerau(
            query,
            target,
            weighted=True,
            ocr_visual=True,
        ),
        f"{prefix}_position": module.same_position_score(query, target),
        f"{prefix}_prefix": module.prefix_score(query, target),
        f"{prefix}_suffix": module.suffix_score(query, target),
        f"{prefix}_edge": module.two_sided_edge_score(query, target),
        f"{prefix}_boundary_anchors": module.boundary_anchor_count(query, target),
        f"{prefix}_length_delta": abs(len(query) - len(target)),
        f"{prefix}_length_coverage": module.length_coverage(query, target),
        f"{prefix}_lcs": lcs,
        f"{prefix}_lcs_query_coverage": lcs / max(len(query), 1),
        f"{prefix}_lcs_target_coverage": lcs / max(len(target), 1),
        f"{prefix}_shared_bigrams": len(
            module.char_ngrams(query, 2) & module.char_ngrams(target, 2)
        ),
        f"{prefix}_bigram_jaccard": module.jaccard(
            module.char_ngrams(query, 2),
            module.char_ngrams(target, 2),
        ),
        f"{prefix}_shared_trigrams": len(
            module.char_ngrams(query, 3) & module.char_ngrams(target, 3)
        ),
        f"{prefix}_trigram_jaccard": module.jaccard(
            module.char_ngrams(query, 3),
            module.char_ngrams(target, 3),
        ),
        f"{prefix}_skeleton": query_skeleton,
        f"{prefix}_target_skeleton": target_skeleton,
        f"{prefix}_skeleton_similarity": module.key_similarity(
            query_skeleton,
            target_skeleton,
        ),
        f"{prefix}_phonetic": query_phonetic,
        f"{prefix}_target_phonetic": target_phonetic,
        f"{prefix}_phonetic_similarity": module.key_similarity(
            query_phonetic,
            target_phonetic,
        ),
        f"{prefix}_query_is_subsequence": int(
            module.is_ordered_subsequence(query, target)
        ),
        f"{prefix}_target_is_subsequence": int(
            module.is_ordered_subsequence(target, query)
        ),
    }


def candidate_fields(item: dict[str, Any], prefix: str) -> dict[str, Any]:
    if not item:
        return {
            f"{prefix}_ranked_score": np.nan,
            f"{prefix}_source": "",
            f"{prefix}_reasons": "",
        }
    return {
        f"{prefix}_ranked_score": item.get("score", np.nan),
        f"{prefix}_source": item.get("source", ""),
        f"{prefix}_external_rank": item.get("external_rank", ""),
        f"{prefix}_context_rank": item.get("context_rank", ""),
        f"{prefix}_rescue_rank": item.get("rescue_rank", ""),
        f"{prefix}_ranked_raw_distance": item.get("raw_edit_distance", np.nan),
        f"{prefix}_ranked_weighted_distance": item.get(
            "weighted_edit_distance",
            np.nan,
        ),
        f"{prefix}_ranked_visual_distance": item.get(
            "ocr_visual_edit_distance",
            np.nan,
        ),
        f"{prefix}_ranked_position": item.get("positional_evidence", np.nan),
        f"{prefix}_ranked_edge": item.get("edge_evidence", np.nan),
        f"{prefix}_reasons": ";".join(item.get("reasons", []) or []),
    }


def failure_cause(row: pd.Series) -> str:
    if len(row["query_compact"]) <= 3:
        return "insufficient_visible_evidence"
    if row["osa_geometry"] == "catalog_competitor_strictly_closer":
        return "another_catalog_head_is_strictly_closer"
    if row["osa_geometry"] == "expected_tied_nearest":
        return "expected_head_ties_with_catalog_neighbors"
    if int(row["hit_at_20"]) == 0:
        return "unique_nearest_expected_family_not_retrieved"
    if row["expected_raw_distance"] < row["top_raw_distance"]:
        return "closer_expected_family_under_ranked"
    if row["expected_raw_distance"] == row["top_raw_distance"]:
        return "equal_distance_evidence_ranked_wrong"
    return "supplied_expected_family_is_lexically_farther"


def remedy(cause: str, row: pd.Series) -> str:
    if cause == "insufficient_visible_evidence":
        return "ask_for_more_visible_letters_or_position"
    if cause == "another_catalog_head_is_strictly_closer":
        return "do_not_force_label; show_closer_family_and_request_confirmation"
    if cause == "expected_head_ties_with_catalog_neighbors":
        return "show_tied_families_and_request_discriminating_letters"
    if cause == "unique_nearest_expected_family_not_retrieved":
        if row["expected_lcs_query_coverage"] >= 0.75:
            return "expand_retrieval_with_bounded_ordered_character_evidence"
        if row["expected_visual_distance"] < row["expected_raw_distance"]:
            return "expand_retrieval_with_directional_visual_confusions"
        return "add_candidate_recall_only_if_global_simulation_has_no_losses"
    if cause == "closer_expected_family_under_ranked":
        return "test_bounded_unique_closer_candidate_rerank_globally"
    if cause == "equal_distance_evidence_ranked_wrong":
        return "test_pareto_evidence_tie_break; keep_ambiguity_if_no_dominance"
    return "audit_label_or_collect_non_lexical_evidence"


def explain_case(row: pd.Series) -> str:
    return (
        f"Expected {row['expected_family_name']} vs top {row['top_1']}: "
        f"raw {row['expected_raw_distance']:.2f}/{row['top_raw_distance']:.2f}, "
        f"visual {row['expected_visual_distance']:.2f}/{row['top_visual_distance']:.2f}, "
        f"LCS {int(row['expected_lcs'])}/{int(row['top_lcs'])}, "
        f"bigrams {int(row['expected_shared_bigrams'])}/"
        f"{int(row['top_shared_bigrams'])}."
    )


def audit_failures(
    primary: pd.DataFrame,
    module: Any,
    catalog: Any,
    responses: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    failures = primary[primary["hit_at_1"] == 0].copy()
    expected_failures = len(primary) - int(primary["hit_at_1"].sum())
    expected_top_20_misses = len(primary) - int(primary["hit_at_20"].sum())
    if (
        len(failures) != expected_failures
        or int((failures["hit_at_20"] == 0).sum()) != expected_top_20_misses
    ):
        raise ValueError(
            f"expected {expected_failures} Hit@1 failures and "
            f"{expected_top_20_misses} top-20 misses, found "
            f"{len(failures)} and {int((failures['hit_at_20'] == 0).sum())}"
        )

    details: list[dict[str, Any]] = []
    for row in failures.itertuples(index=False):
        response = responses[row.case_id]
        results = list(response.get("results") or [])[:20]
        names = [result_name(item) for item in results]
        accepted_keys = {
            key for key in str(row.expected_family_key).split(";") if key
        }
        expected_rank, expected_item = expected_result(results, accepted_keys)
        recorded_top = "" if pd.isna(row.top_1) else str(row.top_1)
        top_item = results[0] if results else {}
        query = compact_text(row.input)
        expected_head = compact_text(row.expected_family_name)
        top_head = compact_text(
            top_item.get("variant_group") or result_name(top_item)
        )
        item = {
            "case_id": row.case_id,
            "sample_id": row.sample_id,
            "split": row.split,
            "ocr_model": row.ocr_model,
            "input": row.input,
            "query_compact": query,
            "expected_family_name": row.expected_family_name,
            "expected_family_key": row.expected_family_key,
            "top_1": recorded_top,
            "first_relevant_rank": int(row.first_relevant_rank),
            "hit_at_20": int(row.hit_at_20),
            "failure_level": "ranking" if int(row.hit_at_20) else "retrieval",
            "analysis_cohort": row.analysis_cohort,
            "distance_band": row.distance_band,
            "mistake_type": row.mistake_type,
            "danger": row.danger,
            "operation_profile": operation_profile(row),
            "source_edit_distance": row.source_edit_distance,
            "source_operation_sequence": row.source_operation_sequence,
            "response_status": response.get("status", ""),
            "decision_type": response.get("decision_type", ""),
            "candidate_count": response.get("candidate_count", len(results)),
        }
        item.update(evidence(module, query, expected_head, "expected"))
        item.update(evidence(module, query, top_head, "top"))
        item.update(candidate_fields(top_item, "top"))
        item.update(candidate_fields(expected_item, "expected"))
        item["ranked_score_gap"] = (
            float(top_item["score"]) - float(expected_item["score"])
            if top_item and expected_item
            else np.nan
        )
        details.append(item)

    audited = pd.DataFrame(details)
    head_keys, head_names = catalog_heads(catalog)
    for scorer, prefix in ((OSA.distance, "osa"), (Levenshtein.distance, "lev")):
        audited = audited.merge(
            geometry(
                audited,
                head_keys,
                head_names,
                scorer=scorer,
                prefix=prefix,
            ),
            on="case_id",
            validate="one_to_one",
        )
    audited["failure_cause"] = audited.apply(failure_cause, axis=1)
    audited["general_remedy_to_test"] = audited.apply(
        lambda row: remedy(row["failure_cause"], row),
        axis=1,
    )
    audited["case_evidence_summary"] = audited.apply(explain_case, axis=1)
    return audited.sort_values(
        ["failure_level", "failure_cause", "source_edit_distance", "case_id"],
        ascending=[False, True, True, True],
    )


def add_deep_candidate_status(
    audit: pd.DataFrame,
    module: Any,
    catalog: Any,
) -> pd.DataFrame:
    """Record whether each expected family is visible in a deeper result pool."""

    enriched = audit.copy()
    enriched["deep_rank"] = enriched["first_relevant_rank"]
    enriched["deep_candidate_count"] = enriched["candidate_count"]
    enriched["deep_reasons"] = enriched["expected_reasons"].fillna("")
    enriched["deep_status"] = "rank_2_20"

    for row in enriched[enriched["hit_at_20"] == 0].itertuples(index=False):
        response = module.search_catalog(catalog, row.input, 100)
        results = list(response.get("results") or [])
        expected_keys = {
            key for key in str(row.expected_family_key).split(";") if key
        }
        rank, item = expected_result(results, expected_keys)
        index = enriched["case_id"] == row.case_id
        enriched.loc[index, "deep_rank"] = rank
        enriched.loc[index, "deep_candidate_count"] = response.get(
            "candidate_count",
            len(results),
        )
        enriched.loc[index, "deep_reasons"] = (
            ";".join(item.get("reasons", []) or []) if item else ""
        )
        enriched.loc[index, "deep_status"] = (
            "rank_21_100" if 21 <= rank <= 100 else "not_generated_in_top_100"
        )
    return enriched


def pareto_rule_gains(
    primary: pd.DataFrame,
    module: Any,
    catalog: Any,
    responses: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    """Ablate the new rule on affected rows and retain only verified gains."""

    affected = []
    for row in primary.itertuples(index=False):
        results = list(responses[row.case_id].get("results") or [])
        if (
            results
            and PARETO_CORRECTION_REASON in set(results[0].get("reasons") or [])
        ):
            affected.append(row)

    original = module.promote_pareto_character_evidence_candidate
    module.promote_pareto_character_evidence_candidate = (
        lambda ranked, compact: ranked
    )
    changes: list[dict[str, Any]] = []
    try:
        for row in affected:
            response = module.search_catalog(catalog, row.input, 20)
            results = list(response.get("results") or [])[:20]
            expected_keys = {
                key for key in str(row.expected_family_key).split(";") if key
            }
            baseline_rank, _ = expected_result(results, expected_keys)
            baseline_top = result_name(results[0]) if results else ""
            current_results = list(
                responses[row.case_id].get("results") or []
            )[:20]
            current_rank, current_item = expected_result(
                current_results,
                expected_keys,
            )
            current_top = (
                result_name(current_results[0]) if current_results else ""
            )
            changes.append(
                {
                    "case_id": row.case_id,
                    "sample_id": row.sample_id,
                    "split": row.split,
                    "ocr_model": row.ocr_model,
                    "input": row.input,
                    "expected_family_name": row.expected_family_name,
                    "expected_family_key": row.expected_family_key,
                    "baseline_top_1": baseline_top,
                    "baseline_expected_rank": baseline_rank,
                    "current_top_1": current_top,
                    "current_expected_rank": current_rank,
                    "current_reasons": ";".join(
                        current_item.get("reasons", []) or []
                    ),
                    "hit_at_1_gain": int(
                        baseline_rank != 1 and current_rank == 1
                    ),
                    "hit_at_1_loss": int(
                        baseline_rank == 1 and current_rank != 1
                    ),
                }
            )
    finally:
        module.promote_pareto_character_evidence_candidate = original

    changes_frame = pd.DataFrame(changes)
    if not changes_frame.empty and int(changes_frame["hit_at_1_loss"].sum()):
        raise ValueError("Pareto correction has a verified Hit@1 regression")
    return changes_frame[
        changes_frame["hit_at_1_gain"] == 1
    ].copy() if not changes_frame.empty else changes_frame


def unresolved_solving_note(row: pd.Series) -> str:
    if row["failure_cause"] == "insufficient_visible_evidence":
        return (
            f"Only {len(row['query_compact'])} compact characters are visible; "
            f"the expected family needs {int(row['osa_expected_distance'])} "
            "ordinary edits, so the text does not identify it."
        )
    if row["failure_cause"] == "expected_head_ties_with_catalog_neighbors":
        return (
            f"The expected family and {int(row['osa_nearest_count']) - 1} "
            f"other nearest catalog heads all need "
            f"{int(row['osa_expected_distance'])} ordinary edits."
        )
    return (
        f"A catalog head is only {int(row['osa_nearest_distance'])} edits from "
        f"the query while the expected family needs "
        f"{int(row['osa_expected_distance'])}; forcing the expected label "
        "would override stronger visible spelling evidence."
    )


def required_evidence(row: pd.Series) -> str:
    if row["failure_cause"] == "insufficient_visible_evidence":
        return (
            "Enter at least two more visible characters and mark whether "
            "unreadable characters occur before, after, or in the middle."
        )
    if row["failure_cause"] == "expected_head_ties_with_catalog_neighbors":
        return (
            "Provide one character at a position where the tied names differ, "
            "or confirm strength, dosage form, or visible continuation."
        )
    return (
        "Confirm the source image or provide a discriminating substring, "
        "strength, dosage form, or unreadable-character position."
    )


def recommended_action(row: pd.Series) -> str:
    if row["deep_status"] == "rank_2_20":
        return (
            "Keep the ambiguous candidate list and ask the user to confirm; "
            "do not certify the hidden expected family automatically."
        )
    if row["deep_status"] == "rank_21_100":
        return (
            "Use the deeper candidate only after new user evidence narrows the "
            "list; no validated general rule safely moves it into the top 20."
        )
    return (
        "Request more text or a clearer crop, then rerun retrieval; the "
        "expected family is absent from the first 100 results."
    )


def build_solvability_ledger(
    audit: pd.DataFrame,
    gains: pd.DataFrame,
) -> pd.DataFrame:
    """Create one explicit disposition for every failure examined this round."""

    unresolved = pd.DataFrame(
        {
            "case_id": audit["case_id"],
            "sample_id": audit["sample_id"],
            "split": audit["split"],
            "ocr_model": audit["ocr_model"],
            "input": audit["input"],
            "expected_family_name": audit["expected_family_name"],
            "baseline_top_1": audit["top_1"],
            "current_top_1": audit["top_1"],
            "baseline_expected_rank": audit["first_relevant_rank"],
            "current_expected_rank": audit["first_relevant_rank"],
            "review_outcome": "not_safely_solvable_from_current_text",
            "safe_text_only_fix_available": 0,
            "implementation_status": "no_automatic_rule_deployed",
            "solvability_class": audit["failure_cause"],
            "candidate_availability": audit["deep_status"],
            "deep_expected_rank": audit["deep_rank"],
            "nearest_catalog_names": audit["osa_nearest_names"],
            "why": audit.apply(unresolved_solving_note, axis=1),
            "additional_evidence_required": audit.apply(
                required_evidence,
                axis=1,
            ),
            "recommended_system_action": audit.apply(
                recommended_action,
                axis=1,
            ),
        }
    )

    solved = pd.DataFrame()
    if not gains.empty:
        solved = pd.DataFrame(
            {
                "case_id": gains["case_id"],
                "sample_id": gains["sample_id"],
                "split": gains["split"],
                "ocr_model": gains["ocr_model"],
                "input": gains["input"],
                "expected_family_name": gains["expected_family_name"],
                "baseline_top_1": gains["baseline_top_1"],
                "current_top_1": gains["current_top_1"],
                "baseline_expected_rank": gains["baseline_expected_rank"],
                "current_expected_rank": gains["current_expected_rank"],
                "review_outcome": "solved_by_general_evidence_rule",
                "safe_text_only_fix_available": 1,
                "implementation_status": "deployed_and_regression_tested",
                "solvability_class": (
                    "pareto_character_structure_dominates_near_top_candidate"
                ),
                "candidate_availability": "promoted_to_rank_1",
                "deep_expected_rank": 1,
                "nearest_catalog_names": "",
                "why": (
                    "One near-top candidate is no worse on raw, weighted, "
                    "visual, position, LCS, bigram, and trigram evidence and "
                    "has stronger two-sided edge evidence."
                ),
                "additional_evidence_required": (
                    "No extra text is required for benchmark rank 1; the "
                    "interface still presents the result as needing confirmation."
                ),
                "recommended_system_action": (
                    "Place the structurally dominant candidate first and keep "
                    "the clarification state."
                ),
            }
        )

    ledger = pd.concat([solved, unresolved], ignore_index=True)
    ledger["_outcome_order"] = ledger["safe_text_only_fix_available"].map(
        {1: 0, 0: 1}
    )
    ledger = ledger.sort_values(
        ["_outcome_order", "solvability_class", "split", "case_id"],
    ).drop(columns="_outcome_order")
    return ledger


def result_head(item: dict[str, Any]) -> str:
    return compact_text(item.get("variant_group") or result_name(item))


def policy_evidence(module: Any, query: str, item: dict[str, Any]) -> dict[str, Any]:
    head = result_head(item)
    query_skeleton = module.current_eval.skeleton(query)
    target_skeleton = module.current_eval.skeleton(head)
    query_phonetic = module.current_eval.drug_phonetic_key(query)
    target_phonetic = module.current_eval.drug_phonetic_key(head)
    return {
        "item": item,
        "head": head,
        "score": float(item.get("score") or 0.0),
        "raw": float(module.damerau(query, head, weighted=False)),
        "weighted": float(module.damerau(query, head, weighted=True)),
        "visual": float(
            module.damerau(query, head, weighted=True, ocr_visual=True)
        ),
        "position": module.same_position_score(query, head),
        "edge": module.two_sided_edge_score(query, head),
        "anchors": module.boundary_anchor_count(query, head),
        "coverage": module.length_coverage(query, head),
        "lcs": module.longest_common_subsequence_length(query, head),
        "bigrams": len(
            module.char_ngrams(query, 2) & module.char_ngrams(head, 2)
        ),
        "trigrams": len(
            module.char_ngrams(query, 3) & module.char_ngrams(head, 3)
        ),
        "skeleton": module.key_similarity(query_skeleton, target_skeleton),
        "phonetic": module.key_similarity(query_phonetic, target_phonetic),
    }


def deduplicated_candidate_evidence(
    module: Any,
    query: str,
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in results:
        candidate = policy_evidence(module, query, item)
        if candidate["head"] and candidate["head"] not in seen:
            seen.add(candidate["head"])
            candidates.append(candidate)
    return candidates


def evidence_vote(
    challenger: dict[str, Any],
    current: dict[str, Any],
) -> tuple[int, int]:
    epsilon = 1e-9
    comparisons = [
        (challenger["weighted"], current["weighted"], "lower"),
        (challenger["visual"], current["visual"], "lower"),
        (challenger["position"], current["position"], "higher"),
        (challenger["edge"], current["edge"], "higher"),
        (challenger["lcs"], current["lcs"], "higher"),
        (
            2 * challenger["trigrams"] + challenger["bigrams"],
            2 * current["trigrams"] + current["bigrams"],
            "higher",
        ),
        (challenger["anchors"], current["anchors"], "higher"),
        (challenger["coverage"], current["coverage"], "higher"),
        (challenger["skeleton"], current["skeleton"], "higher"),
        (challenger["phonetic"], current["phonetic"], "higher"),
    ]
    wins = 0
    losses = 0
    for left, right, direction in comparisons:
        delta = left - right
        if abs(delta) <= epsilon:
            continue
        challenger_wins = delta < 0 if direction == "lower" else delta > 0
        wins += int(challenger_wins)
        losses += int(not challenger_wins)
    return wins, losses


def choose_tie_candidate(
    candidates: list[dict[str, Any]],
    *,
    minimum_wins: int,
    maximum_losses: int,
) -> dict[str, Any] | None:
    if not candidates:
        return None
    current = candidates[0]
    eligible: list[tuple[int, int, dict[str, Any]]] = []
    for challenger in candidates[1:]:
        if challenger["raw"] != current["raw"]:
            continue
        if current["score"] - challenger["score"] > 0.40:
            continue
        wins, losses = evidence_vote(challenger, current)
        if wins >= minimum_wins and losses <= maximum_losses:
            eligible.append((wins, losses, challenger))
    if not eligible:
        return current
    eligible.sort(
        key=lambda value: (
            -(value[0] - value[1]),
            -value[0],
            value[1],
            value[2]["visual"],
            -value[2]["lcs"],
            -value[2]["score"],
            value[2]["head"],
        )
    )
    return eligible[0][2]


def choose_unique_nearest_closer(
    candidates: list[dict[str, Any]],
    nearest_key: str,
    *,
    maximum_score_gap: float = 0.75,
) -> dict[str, Any] | None:
    if not candidates:
        return None
    current = candidates[0]
    nearest = next(
        (candidate for candidate in candidates if candidate["head"] == nearest_key),
        None,
    )
    if nearest is None or nearest is current:
        return current
    if (
        nearest["raw"] <= current["raw"] - 1
        and nearest["visual"] <= current["visual"] - 0.30
        and nearest["lcs"] >= current["lcs"]
        and current["score"] - nearest["score"] <= maximum_score_gap
    ):
        return nearest
    return current


def choose_candidate_pool_bounded_closer(
    candidates: list[dict[str, Any]],
    *,
    maximum_score_gap: float = 0.75,
) -> dict[str, Any] | None:
    if not candidates:
        return None
    nearest_distance = min(candidate["raw"] for candidate in candidates)
    nearest = [
        candidate for candidate in candidates if candidate["raw"] == nearest_distance
    ]
    if len(nearest) != 1:
        return candidates[0]
    return choose_unique_nearest_closer(
        candidates,
        nearest[0]["head"],
        maximum_score_gap=maximum_score_gap,
    )


def head_representatives(catalog: Any) -> dict[str, str]:
    representatives: dict[str, str] = {}
    for family in catalog.rescue_index.families:
        head = family.head_compact or family.compact
        current = representatives.get(head)
        if not current or len(compact_text(family.name)) < len(compact_text(current)):
            representatives[head] = family.name
    return representatives


def indexed_ordered_head_candidate(
    module: Any,
    catalog: Any,
    query: str,
) -> dict[str, Any] | None:
    if not (7 <= len(query) <= 16):
        return None
    family_ids: set[int] = set()
    for bigram in module.char_ngrams(query, 2):
        family_ids.update(catalog.rescue_index.grams2.get(bigram, ()))

    by_head: dict[str, dict[str, Any]] = {}
    for family_id in family_ids:
        family = catalog.rescue_index.families[family_id]
        head = family.head_compact or family.compact
        if not head or not (
            query[:1] == head[:1]
            or module.first_chars_confusable(query[:1], head[:1])
        ):
            continue
        shared_bigrams = len(
            module.char_ngrams(query, 2) & module.char_ngrams(head, 2)
        )
        if shared_bigrams < 3:
            continue
        raw = module.damerau(query, head, weighted=False)
        if raw / max(len(query), len(head), 1) > 0.46:
            continue
        lcs = module.longest_common_subsequence_length(query, head)
        if (
            lcs / max(len(query), 1) < 0.54
            or lcs / max(len(head), 1) < 0.65
        ):
            continue
        item = policy_evidence(
            module,
            query,
            {
                "name": family.name,
                "variant_group": family.variant_group or family.name,
            },
        )
        current = by_head.get(head)
        if current is None or (
            len(compact_text(family.name)),
            family.name,
        ) < (
            len(compact_text(result_name(current["item"]))),
            result_name(current["item"]),
        ):
            by_head[head] = item

    if not by_head:
        return None
    nearest_distance = min(item["raw"] for item in by_head.values())
    nearest = [
        item for item in by_head.values() if item["raw"] == nearest_distance
    ]
    return nearest[0] if len(nearest) == 1 else None


def relevant(name: str, expected_keys: set[str]) -> int:
    return int(compact_text(name) in expected_keys)


def simulate_general_rules(
    primary: pd.DataFrame,
    module: Any,
    catalog: Any,
    responses: dict[str, dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    head_keys, head_names = catalog_heads(catalog)
    nearest = geometry(
        primary,
        head_keys,
        head_names,
        scorer=OSA.distance,
        prefix="osa",
    ).set_index("case_id")
    representatives = head_representatives(catalog)
    outcomes: list[dict[str, Any]] = []

    for row in primary.itertuples(index=False):
        response = responses[row.case_id]
        results = list(response.get("results") or [])[:20]
        names = [result_name(item) for item in results]
        expected_keys = {
            key for key in str(row.expected_family_key).split(";") if key
        }
        query = compact_text(row.input)
        candidates = deduplicated_candidate_evidence(module, query, results)
        current = candidates[0] if candidates else None
        nearest_row = nearest.loc[row.case_id]
        nearest_key = (
            str(nearest_row["osa_nearest_keys"])
            if int(nearest_row["osa_nearest_count"]) == 1
            else ""
        )

        choices: dict[str, dict[str, Any] | None] = {
            "current_algorithm_5": current,
            "minimum_raw_head_distance": (
                min(candidates, key=lambda item: (item["raw"], -item["score"]))
                if candidates
                else None
            ),
            "minimum_visual_head_distance": (
                min(
                    candidates,
                    key=lambda item: (
                        item["visual"],
                        item["raw"],
                        -item["score"],
                    ),
                )
                if candidates
                else None
            ),
            "raw_visual_lcs_lexicographic": (
                min(
                    candidates,
                    key=lambda item: (
                        item["raw"],
                        item["visual"],
                        item["weighted"],
                        -item["lcs"],
                        -item["trigrams"],
                        -item["bigrams"],
                        -item["score"],
                    ),
                )
                if candidates
                else None
            ),
            "strict_equal_distance_dominance": choose_tie_candidate(
                candidates,
                minimum_wins=3,
                maximum_losses=0,
            ),
            "bounded_equal_distance_vote": choose_tie_candidate(
                candidates,
                minimum_wins=4,
                maximum_losses=1,
            ),
            "unique_nearest_bounded_closer": choose_unique_nearest_closer(
                candidates,
                nearest_key,
            ),
            "candidate_pool_bounded_closer": (
                choose_candidate_pool_bounded_closer(candidates)
            ),
            "candidate_pool_closer_gap_0_85": (
                choose_candidate_pool_bounded_closer(
                    candidates,
                    maximum_score_gap=0.85,
                )
            ),
            "candidate_pool_closer_gap_1_00": (
                choose_candidate_pool_bounded_closer(
                    candidates,
                    maximum_score_gap=1.00,
                )
            ),
        }
        closer = choices["unique_nearest_bounded_closer"]
        reordered = (
            [closer]
            + [
                candidate
                for candidate in candidates
                if closer is not None and candidate["head"] != closer["head"]
            ]
            if closer is not None
            else []
        )
        choices["closer_then_strict_tie"] = choose_tie_candidate(
            reordered,
            minimum_wins=3,
            maximum_losses=0,
        )
        choices["closer_then_bounded_tie"] = choose_tie_candidate(
            reordered,
            minimum_wins=4,
            maximum_losses=1,
        )

        current_h20 = int(any(relevant(name, expected_keys) for name in names))
        for policy, choice in choices.items():
            chosen_name = result_name(choice["item"]) if choice else ""
            outcomes.append(
                {
                    "case_id": row.case_id,
                    "split": row.split,
                    "input": row.input,
                    "expected": row.expected_family_name,
                    "policy": policy,
                    "selected": chosen_name,
                    "changed": int(chosen_name != (names[0] if names else "")),
                    "hit_at_1": relevant(chosen_name, expected_keys),
                    "hit_at_20": current_h20,
                }
            )

        retrieval_names = names.copy()
        nearest_candidate = (
            policy_evidence(
                module,
                query,
                {
                    "name": representatives[nearest_key],
                    "variant_group": head_names[nearest_key],
                },
            )
            if nearest_key and nearest_key in representatives
            else None
        )
        heads_in_results = {candidate["head"] for candidate in candidates}
        retrieval_triggered = bool(
            nearest_candidate
            and nearest_key not in heads_in_results
            and len(query) >= 7
            and nearest_candidate["raw"] / max(len(query), len(nearest_key), 1)
            <= 0.46
            and nearest_candidate["lcs"] / max(len(query), 1) >= 0.54
            and nearest_candidate["lcs"] / max(len(nearest_key), 1) >= 0.65
            and nearest_candidate["bigrams"] >= 3
            and (
                current is None
                or current["raw"] >= nearest_candidate["raw"] + 2
            )
        )
        if retrieval_triggered:
            inserted = result_name(nearest_candidate["item"])
            if len(retrieval_names) >= 20:
                retrieval_names = retrieval_names[:19] + [inserted]
            else:
                retrieval_names.append(inserted)
        outcomes.append(
            {
                "case_id": row.case_id,
                "split": row.split,
                "input": row.input,
                "expected": row.expected_family_name,
                "policy": "bounded_unique_nearest_retrieval",
                "selected": names[0] if names else "",
                "changed": int(retrieval_triggered),
                "hit_at_1": int(row.hit_at_1),
                "hit_at_20": int(
                    any(relevant(name, expected_keys) for name in retrieval_names)
                ),
            }
        )

        indexed_candidate = indexed_ordered_head_candidate(
            module,
            catalog,
            query,
        )
        indexed_names = names.copy()
        indexed_triggered = bool(
            indexed_candidate
            and indexed_candidate["head"] not in heads_in_results
            and (
                current is None
                or current["raw"] >= indexed_candidate["raw"] + 2
            )
        )
        if indexed_triggered:
            inserted = result_name(indexed_candidate["item"])
            if len(indexed_names) >= 20:
                indexed_names = indexed_names[:19] + [inserted]
            else:
                indexed_names.append(inserted)
        outcomes.append(
            {
                "case_id": row.case_id,
                "split": row.split,
                "input": row.input,
                "expected": row.expected_family_name,
                "policy": "indexed_ordered_head_retrieval",
                "selected": names[0] if names else "",
                "changed": int(indexed_triggered),
                "hit_at_1": int(row.hit_at_1),
                "hit_at_20": int(
                    any(relevant(name, expected_keys) for name in indexed_names)
                ),
            }
        )

    cases = pd.DataFrame(outcomes)
    baseline = cases[cases["policy"] == "current_algorithm_5"].set_index("case_id")
    metrics: list[dict[str, Any]] = []
    for policy, group in cases.groupby("policy", sort=False):
        indexed = group.set_index("case_id")
        h1_gain = (indexed["hit_at_1"] > baseline["hit_at_1"]).sum()
        h1_loss = (indexed["hit_at_1"] < baseline["hit_at_1"]).sum()
        h20_gain = (indexed["hit_at_20"] > baseline["hit_at_20"]).sum()
        h20_loss = (indexed["hit_at_20"] < baseline["hit_at_20"]).sum()
        metrics.append(
            {
                "policy": policy,
                "changed_cases": int(group["changed"].sum()),
                "hit_at_1_count": int(group["hit_at_1"].sum()),
                "hit_at_1_percent": group["hit_at_1"].mean() * 100,
                "hit_at_1_gains": int(h1_gain),
                "hit_at_1_losses": int(h1_loss),
                "hit_at_1_net": int(h1_gain - h1_loss),
                "development_hit_at_1_percent": (
                    group.loc[group["split"] == "development", "hit_at_1"].mean()
                    * 100
                ),
                "holdout_hit_at_1_percent": (
                    group.loc[group["split"] == "holdout", "hit_at_1"].mean()
                    * 100
                ),
                "hit_at_20_count": int(group["hit_at_20"].sum()),
                "hit_at_20_percent": group["hit_at_20"].mean() * 100,
                "hit_at_20_gains": int(h20_gain),
                "hit_at_20_losses": int(h20_loss),
                "hit_at_20_net": int(h20_gain - h20_loss),
            }
        )
    return pd.DataFrame(metrics), cases


def print_summary(primary: pd.DataFrame, audit: pd.DataFrame) -> None:
    print(
        f"Primary fair pairs: {len(primary)}; "
        f"Hit@1: {int(primary['hit_at_1'].sum())}/{len(primary)} "
        f"({primary['hit_at_1'].mean() * 100:.4f}%)"
    )
    print(
        f"Audited failures: {len(audit)}; ranking: "
        f"{int((audit['failure_level'] == 'ranking').sum())}; retrieval: "
        f"{int((audit['failure_level'] == 'retrieval').sum())}"
    )
    print("\nFailure causes:")
    print(audit["failure_cause"].value_counts().to_string())
    print("\nFailure operation profiles:")
    print(
        pd.crosstab(
            audit["operation_profile"],
            audit["failure_level"],
            margins=True,
        ).to_string()
    )
    print("\nFailure cohorts:")
    print(
        pd.crosstab(
            audit["analysis_cohort"],
            audit["failure_level"],
            margins=True,
        ).to_string()
    )


def print_simulation(metrics: pd.DataFrame, cases: pd.DataFrame) -> None:
    columns = [
        "policy",
        "changed_cases",
        "hit_at_1_count",
        "hit_at_1_percent",
        "hit_at_1_gains",
        "hit_at_1_losses",
        "hit_at_1_net",
        "hit_at_20_count",
        "hit_at_20_percent",
        "hit_at_20_gains",
        "hit_at_20_losses",
    ]
    print("\nGeneral-rule simulation over all 464 primary pairs:")
    print(metrics[columns].to_string(index=False, float_format=lambda value: f"{value:.4f}"))

    baseline = (
        cases[cases["policy"] == "current_algorithm_5"]
        .set_index("case_id")["hit_at_1"]
    )
    for policy in (
        "unique_nearest_bounded_closer",
        "candidate_pool_bounded_closer",
        "strict_equal_distance_dominance",
        "bounded_equal_distance_vote",
        "bounded_unique_nearest_retrieval",
        "indexed_ordered_head_retrieval",
    ):
        group = cases[cases["policy"] == policy].copy()
        group["baseline_hit_at_1"] = group["case_id"].map(baseline)
        changed = group[group["changed"] == 1]
        if not changed.empty:
            print(f"\n{policy} affected cases:")
            print(
                changed[
                    [
                        "input",
                        "expected",
                        "selected",
                        "baseline_hit_at_1",
                        "hit_at_1",
                        "hit_at_20",
                    ]
                ].to_string(index=False)
            )


def main() -> None:
    args = parse_args()
    primary = primary_pairs(args.results)
    module = load_algorithm_5()
    catalog = module.prepare_catalog()
    responses = rerun_primary(primary, module, catalog)
    audit = audit_failures(primary, module, catalog, responses)
    audit = add_deep_candidate_status(audit, module, catalog)
    gains = pareto_rule_gains(primary, module, catalog, responses)
    solvability = build_solvability_ledger(audit, gains)
    simulation, simulation_cases = simulate_general_rules(
        primary,
        module,
        catalog,
        responses,
    )
    for policy in (
        "unique_nearest_bounded_closer",
        "candidate_pool_bounded_closer",
        "bounded_unique_nearest_retrieval",
        "indexed_ordered_head_retrieval",
    ):
        policy_cases = simulation_cases[
            simulation_cases["policy"] == policy
        ].set_index("case_id")
        audit[f"{policy}_selected"] = audit["case_id"].map(
            policy_cases["selected"]
        )
        audit[f"{policy}_changed"] = audit["case_id"].map(
            policy_cases["changed"]
        )
        audit[f"{policy}_hit_at_1"] = audit["case_id"].map(
            policy_cases["hit_at_1"]
        )
        audit[f"{policy}_hit_at_20"] = audit["case_id"].map(
            policy_cases["hit_at_20"]
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(args.output, index=False, encoding="utf-8")
    simulation.to_csv(args.simulation_output, index=False, encoding="utf-8")
    solvability.to_csv(
        args.solvability_output,
        index=False,
        encoding="utf-8",
    )
    print_summary(primary, audit)
    print(
        "\nSolvability review: "
        f"{len(gains)} solved by the accepted general rule; "
        f"{len(audit)} require additional evidence."
    )
    print(audit["deep_status"].value_counts().to_string())
    print_simulation(simulation, simulation_cases)
    print(f"\nWrote {len(audit)} case-by-case rows to {args.output}")
    print(f"Wrote {len(simulation)} rule comparisons to {args.simulation_output}")
    print(
        f"Wrote {len(solvability)} solvability decisions to "
        f"{args.solvability_output}"
    )


if __name__ == "__main__":
    main()

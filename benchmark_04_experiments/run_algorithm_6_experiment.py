#!/usr/bin/env python3
"""Prepare, train, and evaluate Algorithm 6 without target-family leakage."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterable

import lightgbm as lgb
import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from rapidfuzz import process
from rapidfuzz.distance import (
    DamerauLevenshtein,
    JaroWinkler,
    LCSseq,
    Levenshtein,
)
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
LEGACY_ROOT = PROJECT_ROOT / "benchmark_01_legacy"
OCR_ROOT = PROJECT_ROOT / "benchmark_03_ocr"
DEFAULT_OCR_CASES = ROOT / "data/01_ocr_fair/test_cases.csv"
DEFAULT_COMPETITOR_ARTIFACTS = ROOT / "artifacts/06_competitor_benchmark"
DEFAULT_ARTIFACTS = ROOT / "artifacts/07_algorithm_6"
DEFAULT_RESULTS = ROOT / "results/07_algorithm_6"
ALGORITHM_6_PATH = (
    LEGACY_ROOT / "master_algorithms/algorithm_6_consensus_search.py"
)
ALGORITHM_6_POLICY_PATH = (
    LEGACY_ROOT / "master_algorithms/algorithm_6_policy.json"
)
EVALUATION_VERSION = "algorithm_6_evidence_learning_v1"
CROSS_FIT_FOLDS = 5
OPERATION_RE = re.compile(r"([MIDR])\(([^)]*)\)")
RANK_1_GATE = {
    "enabled": False,
    "minimum_sources": 7,
    "minimum_source_advantage": 1,
    "minimum_levenshtein_advantage": 0.02,
    "maximum_jaro_disadvantage": 0.02,
    "minimum_bigram_advantage": 0.0,
    "maximum_algorithm_5_rank": 3,
}
TOP_20_GATE = {
    "slots": 1,
    "minimum_sources": 3,
    "minimum_levenshtein_similarity": 0.55,
    "minimum_jaro_winkler": 0.85,
}

for import_path in (LEGACY_ROOT, OCR_ROOT, ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import evaluate_current_app_search as current_app


SELECTED_RETRIEVERS = (
    "algorithm_5",
    "baseline_jaro_winkler",
    "jellyfish_match_rating",
    "rapidfuzz_wratio",
    "jellyfish_nysiis",
    "bm25_plus_char3",
    "symspell_uniform_ed3",
    "rapidfuzz_token_sort",
    "jellyfish_soundex",
    "dice_char2",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocr-cases", type=Path, default=DEFAULT_OCR_CASES)
    parser.add_argument(
        "--competitor-artifacts",
        type=Path,
        default=DEFAULT_COMPETITOR_ARTIFACTS,
    )
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--skip-runtime-validation", action="store_true")
    parser.add_argument("--skip-synthetic", action="store_true")
    return parser.parse_args()


def compact(value: Any) -> str:
    return current_app.compact_key("" if pd.isna(value) else str(value))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_primary_ocr_cases(path: Path) -> pd.DataFrame:
    source = pd.read_csv(path, encoding="utf-8-sig")
    source = source[
        source["accepted"].eq(1) & source["scored_case"].eq(1)
    ].copy()
    source["input_compact"] = source["input"].map(compact)
    source = source.drop_duplicates(
        ["input_compact", "expected_family_key"],
        keep="first",
    )
    if len(source) != 412:
        raise ValueError(f"expected 412 adjudicated OCR pairs, found {len(source)}")
    if source.groupby("expected_family_key")["split"].nunique().max() != 1:
        raise ValueError("one target family appears in more than one legacy split")
    return source.reset_index(drop=True)


def balanced_family_folds(cases: pd.DataFrame) -> dict[str, int]:
    development = cases[cases["split"].eq("development")]
    family_counts = development["expected_family_key"].value_counts()
    ordered = sorted(
        family_counts.items(),
        key=lambda item: (
            -item[1],
            hashlib.sha256(item[0].encode("utf-8")).hexdigest(),
        ),
    )
    fold_sizes = [0] * CROSS_FIT_FOLDS
    assignments: dict[str, int] = {}
    for family, count in ordered:
        fold = min(range(CROSS_FIT_FOLDS), key=lambda index: (fold_sizes[index], index))
        assignments[family] = fold
        fold_sizes[fold] += int(count)
    if len(set(assignments)) != development["expected_family_key"].nunique():
        raise ValueError("development family fold assignment is incomplete")
    return assignments


def build_evaluation_contract(cases: pd.DataFrame) -> pd.DataFrame:
    fold_by_family = balanced_family_folds(cases)
    contract = cases[
        [
            "case_id",
            "observation_id",
            "sample_id",
            "image_id",
            "input",
            "input_compact",
            "expected_family_key",
            "expected_family_name",
            "split",
            "analysis_cohort",
            "distance_band",
            "mistake_type",
            "normalized_edit_distance",
        ]
    ].copy()
    contract["evaluation_version"] = EVALUATION_VERSION
    contract["model_role"] = contract["split"].map(
        {
            "development": "crossfit_development",
            "holdout": "retrospective_holdout",
        }
    )
    contract["crossfit_fold"] = contract["expected_family_key"].map(fold_by_family)
    contract.loc[contract["split"].eq("holdout"), "crossfit_fold"] = pd.NA
    contract["fresh_blind_claim_allowed"] = 0
    contract["contract_note"] = contract["split"].map(
        {
            "development": (
                "Each cross-fit prediction is produced by a model trained on "
                "the other target families."
            ),
            "holdout": (
                "Historical family-disjoint holdout retained for comparison; "
                "it is not fresh because prior work inspected its outcomes."
            ),
        }
    )

    development = contract[contract["split"].eq("development")]
    for fold in range(CROSS_FIT_FOLDS):
        validation_families = set(
            development.loc[
                development["crossfit_fold"].eq(fold),
                "expected_family_key",
            ]
        )
        training_families = set(
            development.loc[
                development["crossfit_fold"].ne(fold),
                "expected_family_key",
            ]
        )
        if validation_families & training_families:
            raise ValueError(f"target-family leakage in cross-fit fold {fold}")
    return contract


def load_ranked_outputs(
    competitor_root: Path,
    primary_case_ids: set[str],
) -> dict[str, pd.DataFrame]:
    a5_path = competitor_root / "a5_ablation_ocr_464/full_algorithm_5.csv.gz"
    outputs = {
        "algorithm_5": pd.read_csv(
            a5_path,
            usecols=["case_id", "top_1", "top_20"],
        )
    }
    legacy = pd.read_csv(
        ROOT / "artifacts/case_results.csv",
        usecols=["experiment", "case_id", "algorithm", "top_20"],
    )
    outputs["baseline_jaro_winkler"] = legacy[
        legacy["experiment"].eq("retrieval")
        & legacy["algorithm"].eq("baseline_jaro_winkler")
        & legacy["case_id"].isin(primary_case_ids)
    ][["case_id", "top_20"]]
    for retriever in SELECTED_RETRIEVERS:
        if retriever in outputs:
            continue
        path = competitor_root / f"ocr_464/{retriever}.csv.gz"
        outputs[retriever] = pd.read_csv(
            path,
            usecols=["case_id", "top_20"],
        )

    expected_ids = primary_case_ids
    for retriever, frame in outputs.items():
        actual_ids = set(frame["case_id"])
        if actual_ids != expected_ids:
            raise ValueError(
                f"{retriever} case IDs do not match the 464-pair contract: "
                f"{len(actual_ids)} found"
            )
    return outputs


def ranked_key_sets(
    outputs: dict[str, pd.DataFrame],
) -> dict[str, dict[str, set[str]]]:
    result: dict[str, dict[str, set[str]]] = {}
    for retriever, frame in outputs.items():
        result[retriever] = {}
        for row in frame.itertuples():
            names = [] if pd.isna(row.top_20) else str(row.top_20).split(";")
            result[retriever][row.case_id] = {
                key for key in (compact(name) for name in names) if key
            }
    return result


def nearest_catalog(
    query: str,
    catalog_keys: list[str],
    catalog_names: dict[str, str],
) -> tuple[int, str]:
    matches = process.extract(
        query,
        catalog_keys,
        scorer=Levenshtein.distance,
        limit=5,
    )
    if not matches:
        return 999, ""
    minimum = int(matches[0][1])
    nearest = [
        catalog_names[key]
        for key, score, _ in matches
        if int(score) == minimum
    ]
    return minimum, "; ".join(nearest)


def audit_reasons(row: pd.Series) -> list[str]:
    reasons = []
    if row["query_is_different_catalog_family"]:
        reasons.append("query_exactly_names_another_catalog_family")
    if row["expected_minus_nearest_distance"] >= 2:
        reasons.append("another_catalog_family_is_at_least_two_edits_closer")
    elif row["expected_minus_nearest_distance"] == 1:
        reasons.append("another_catalog_family_is_one_edit_closer")
    if row["normalized_edit_distance"] > 0.60:
        reasons.append("extreme_normalized_distance_above_0_60")
    if not row["selected_union_contains_expected"]:
        reasons.append("expected_absent_from_selected_candidate_union")
    if not row["all_measured_union_contains_expected"]:
        reasons.append("expected_absent_from_all_measured_top20_lists")
    if row["query_length"] <= 2:
        reasons.append("one_or_two_visible_characters")
    if not row["source_image_reference_available"]:
        reasons.append("source_image_reference_missing")
    return reasons


def build_label_audit_queue(
    cases: pd.DataFrame,
    competitor_root: Path,
) -> pd.DataFrame:
    records = current_app.prepare_records()
    catalog_names: dict[str, str] = {}
    for record in records:
        name = str(record.get("b") or record.get("n") or "").strip()
        key = compact(name)
        if key:
            catalog_names.setdefault(key, name)
    catalog_keys = sorted(catalog_names)
    outputs = load_ranked_outputs(competitor_root, set(cases["case_id"]))
    selected = ranked_key_sets(outputs)

    all_outputs = {
        path.name.removesuffix(".csv.gz"): pd.read_csv(
            path,
            usecols=["case_id", "top_20"],
        )
        for path in sorted((competitor_root / "ocr_464").glob("*.csv.gz"))
    }
    all_outputs.update(outputs)
    all_ranked = ranked_key_sets(all_outputs)
    a5_top = outputs["algorithm_5"].set_index("case_id")["top_1"].to_dict()

    rows = []
    for source_row in cases.to_dict("records"):
        query = source_row["input_compact"]
        expected = set(str(source_row["expected_family_key"]).split(";"))
        expected_lexical_forms = {
            *expected,
            compact(source_row["expected_family_name"]),
        }
        expected_lexical_forms.discard("")
        expected_distance = min(
            Levenshtein.distance(query, target)
            for target in expected_lexical_forms
        )
        nearest_distance, nearest_names = nearest_catalog(
            query,
            catalog_keys,
            catalog_names,
        )
        selected_union = set().union(
            *(mapping[source_row["case_id"]] for mapping in selected.values())
        )
        all_union = set().union(
            *(mapping[source_row["case_id"]] for mapping in all_ranked.values())
        )
        top_name = a5_top.get(source_row["case_id"], "")
        top_key = compact(top_name)
        query_catalog_name = catalog_names.get(query, "")
        row = {
            "evaluation_version": EVALUATION_VERSION,
            "case_id": source_row["case_id"],
            "sample_id": source_row["sample_id"],
            "split": source_row["split"],
            "ocr_model": source_row["model_name"],
            "image_id": source_row["image_id"],
            "source_image_reference_available": int(
                not pd.isna(source_row["image_id"])
                and bool(str(source_row["image_id"]).strip())
            ),
            "input": source_row["input"],
            "input_compact": query,
            "query_length": len(query),
            "expected_family_name": source_row["expected_family_name"],
            "expected_family_keys": source_row["expected_family_key"],
            "algorithm_5_top_1": top_name,
            "algorithm_5_top_1_distance": (
                Levenshtein.distance(query, top_key) if top_key else 999
            ),
            "expected_distance": expected_distance,
            "nearest_catalog_distance": nearest_distance,
            "expected_minus_nearest_distance": (
                expected_distance - nearest_distance
            ),
            "nearest_catalog_names": nearest_names,
            "query_is_catalog_family": int(bool(query_catalog_name)),
            "query_catalog_family": query_catalog_name,
            "query_is_different_catalog_family": int(
                bool(query_catalog_name) and query not in expected_lexical_forms
            ),
            "normalized_edit_distance": source_row["normalized_edit_distance"],
            "analysis_cohort": source_row["analysis_cohort"],
            "distance_band": source_row["distance_band"],
            "mistake_type": source_row["mistake_type"],
            "selected_union_contains_expected": int(bool(selected_union & expected)),
            "all_measured_union_contains_expected": int(bool(all_union & expected)),
        }
        reasons = audit_reasons(pd.Series(row))
        if (
            row["query_is_different_catalog_family"]
            or row["expected_minus_nearest_distance"] >= 2
            or not row["all_measured_union_contains_expected"]
        ):
            priority = "P0"
        elif (
            row["expected_minus_nearest_distance"] == 1
            or row["normalized_edit_distance"] > 0.60
            or not row["selected_union_contains_expected"]
            or row["query_length"] <= 2
        ):
            priority = "P1"
        else:
            priority = "P2"
        provisionally_eligible = priority == "P2"
        row.update(
            {
                "audit_priority": priority,
                "automated_audit_reasons": ";".join(reasons) or "none",
                "provisional_model_training_eligibility": int(
                    provisionally_eligible
                ),
                "human_image_review_status": "pending",
                "adjudicated_expected_family": "",
                "adjudicator_notes": "",
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        [
            "audit_priority",
            "expected_minus_nearest_distance",
            "normalized_edit_distance",
            "case_id",
        ],
        ascending=[True, False, False, True],
    )


def split_distribution(contract: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for (role, fold), frame in contract.groupby(
        ["model_role", "crossfit_fold"],
        dropna=False,
    ):
        rows.append(
            {
                "model_role": role,
                "crossfit_fold": None if pd.isna(fold) else int(fold),
                "cases": len(frame),
                "target_families": frame["expected_family_key"].nunique(),
            }
        )
    return rows


def prepare(
    args: argparse.Namespace,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cases = load_primary_ocr_cases(args.ocr_cases)
    contract = build_evaluation_contract(cases)
    audit = build_label_audit_queue(cases, args.competitor_artifacts)

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    args.results_dir.mkdir(parents=True, exist_ok=True)
    contract_path = args.results_dir / "evaluation_contract.csv"
    audit_path = args.artifacts_dir / "ocr_label_audit_queue.csv"
    summary_path = args.results_dir / "preparation_summary.json"
    contract.to_csv(contract_path, index=False)
    audit.to_csv(audit_path, index=False)

    summary = {
        "evaluation_version": EVALUATION_VERSION,
        "source": str(args.ocr_cases.relative_to(PROJECT_ROOT)),
        "source_sha256": sha256(args.ocr_cases),
        "cases": len(cases),
        "target_families": cases["expected_family_key"].nunique(),
        "selected_retrievers": list(SELECTED_RETRIEVERS),
        "split_distribution": split_distribution(contract),
        "family_overlap_between_legacy_splits": 0,
        "fresh_blind_claim_allowed": False,
        "audit_priority_counts": audit["audit_priority"].value_counts().to_dict(),
        "provisional_training_eligible_cases": int(
            audit["provisional_model_training_eligibility"].sum()
        ),
        "selected_union_recall_cases": int(
            audit["selected_union_contains_expected"].sum()
        ),
        "all_measured_union_recall_cases": int(
            audit["all_measured_union_contains_expected"].sum()
        ),
        "source_image_references_available": int(
            audit["source_image_reference_available"].sum()
        ),
        "label_audit_status": "pending_human_image_review",
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {contract_path}")
    print(f"Wrote {audit_path}")
    print(f"Wrote {summary_path}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return cases, contract, audit


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def discounted_cost(
    count: int,
    maximum: int,
    *,
    scale: float,
    floor: float,
) -> float:
    if count <= 0:
        return 1.0
    strength = (count / max(maximum, 1)) * (count / (count + 3))
    return max(floor, 1 - scale * strength)


def learn_confusion_policy(
    cases: pd.DataFrame,
    audit: pd.DataFrame,
) -> tuple[dict[str, Any], pd.DataFrame]:
    eligible = set(
        audit.loc[
            audit["provisional_model_training_eligibility"].eq(1),
            "case_id",
        ]
    )
    source = cases[
        cases["split"].eq("development")
        & cases["case_id"].isin(eligible)
    ]
    substitutions: Counter[tuple[str, str]] = Counter()
    insertions: Counter[str] = Counter()
    deletions: Counter[str] = Counter()
    for sequence in source["source_operation_sequence"].fillna(""):
        for operation, payload in OPERATION_RE.findall(str(sequence)):
            if operation == "R" and "->" in payload:
                observed, target = payload.split("->", 1)
                if (
                    len(observed) == 1
                    and len(target) == 1
                    and observed.isalnum()
                    and target.isalnum()
                ):
                    substitutions[(observed.upper(), target.upper())] += 1
            elif (
                operation == "I"
                and len(payload) == 1
                and payload.isalnum()
            ):
                insertions[payload.upper()] += 1
            elif (
                operation == "D"
                and len(payload) == 1
                and payload.isalnum()
            ):
                deletions[payload.upper()] += 1

    maximum_by_observed: dict[str, int] = defaultdict(int)
    for (observed, _), count in substitutions.items():
        maximum_by_observed[observed] = max(
            maximum_by_observed[observed],
            count,
        )
    maximum_insertion = max(insertions.values(), default=1)
    maximum_deletion = max(deletions.values(), default=1)
    table_rows = []
    substitution_costs = {}
    for (observed, target), count in sorted(substitutions.items()):
        cost = discounted_cost(
            count,
            maximum_by_observed[observed],
            scale=0.80,
            floor=0.20,
        )
        substitution_costs[f"{observed}>{target}"] = round(cost, 8)
        table_rows.append(
            {
                "operation": "substitution",
                "observed": observed,
                "target": target,
                "count": count,
                "cost": cost,
            }
        )
    insertion_costs = {}
    for target, count in sorted(insertions.items()):
        cost = discounted_cost(
            count,
            maximum_insertion,
            scale=0.55,
            floor=0.45,
        )
        insertion_costs[target] = round(cost, 8)
        table_rows.append(
            {
                "operation": "missing_character",
                "observed": "",
                "target": target,
                "count": count,
                "cost": cost,
            }
        )
    deletion_costs = {}
    for observed, count in sorted(deletions.items()):
        cost = discounted_cost(
            count,
            maximum_deletion,
            scale=0.55,
            floor=0.45,
        )
        deletion_costs[observed] = round(cost, 8)
        table_rows.append(
            {
                "operation": "extra_character",
                "observed": observed,
                "target": "",
                "count": count,
                "cost": cost,
            }
        )
    policy = {
        "evaluation_version": "algorithm_6_consensus_v1",
        "training_contract": {
            "source": str(
                DEFAULT_OCR_CASES.relative_to(PROJECT_ROOT)
            ),
            "split": "development",
            "provisionally_eligible_cases": len(source),
            "target_families": source["expected_family_key"].nunique(),
            "holdout_rows_used": 0,
            "case_specific_rules": 0,
        },
        "rank_1_gate": RANK_1_GATE,
        "top_20_gate": TOP_20_GATE,
        "confusion_costs": {
            "substitution": substitution_costs,
            "insertion": insertion_costs,
            "deletion": deletion_costs,
        },
    }
    table = pd.DataFrame(table_rows).sort_values(
        ["operation", "count", "observed", "target"],
        ascending=[True, False, True, True],
    )
    return policy, table


SOURCE_COLUMN_BY_RETRIEVER = {
    "algorithm_5": "algorithm_5",
    "baseline_jaro_winkler": "jaro_winkler",
    "jellyfish_match_rating": "match_rating",
    "rapidfuzz_wratio": "rapidfuzz_wratio",
    "jellyfish_nysiis": "nysiis",
    "bm25_plus_char3": "bm25_plus_char3",
    "symspell_uniform_ed3": "symspell_uniform_ed3",
    "rapidfuzz_token_sort": "rapidfuzz_token_sort",
    "jellyfish_soundex": "soundex",
    "dice_char2": "dice_char2",
}


def load_replay_frame(
    dataset: str,
    competitor_root: Path,
) -> pd.DataFrame:
    suffix = "ocr_464" if dataset == "ocr" else "synthetic_66257"
    base_path = (
        competitor_root
        / f"a5_ablation_{suffix}/full_algorithm_5.csv.gz"
    )
    frame = pd.read_csv(base_path)
    frame = frame.rename(columns={"top_20": "algorithm_5"})
    legacy_path = (
        ROOT / "artifacts/case_results.csv"
        if dataset == "ocr"
        else ROOT / "artifacts/05_synthetic_clean_core/case_results.csv"
    )
    if not legacy_path.exists():
        archived_path = legacy_path.with_suffix(legacy_path.suffix + ".gz")
        if archived_path.exists():
            legacy_path = archived_path
    legacy_rank_column = "top_20" if dataset == "ocr" else "top_5"
    legacy = pd.read_csv(
        legacy_path,
        usecols=["case_id", "algorithm", legacy_rank_column],
    )
    jaro = legacy[
        legacy["algorithm"].eq("baseline_jaro_winkler")
        & legacy["case_id"].isin(set(frame["case_id"]))
    ][["case_id", legacy_rank_column]].rename(
        columns={legacy_rank_column: "jaro_winkler"}
    )
    frame = frame.merge(
        jaro,
        on="case_id",
        how="left",
        validate="one_to_one",
    )
    for artifact_name, column in SOURCE_COLUMN_BY_RETRIEVER.items():
        if artifact_name in {"algorithm_5", "baseline_jaro_winkler"}:
            continue
        source = pd.read_csv(
            competitor_root / f"{suffix}/{artifact_name}.csv.gz",
            usecols=["case_id", "top_20"],
        ).rename(columns={"top_20": column})
        frame = frame.merge(
            source,
            on="case_id",
            how="left",
            validate="one_to_one",
        )
    expected = 464 if dataset == "ocr" else 66_257
    if len(frame) != expected:
        raise ValueError(
            f"{dataset}: expected {expected} replay rows, found {len(frame)}"
        )
    return frame


def split_names(value: Any) -> list[str]:
    if pd.isna(value):
        return []
    return [
        name.strip()
        for name in str(value).split(";")
        if name.strip()
    ]


def character_ngrams(value: str, size: int) -> set[str]:
    if len(value) < size:
        return set()
    return {
        value[index : index + size]
        for index in range(len(value) - size + 1)
    }


def dice(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return 2 * len(left & right) / (len(left) + len(right))


def replay_candidates(
    row: Any,
    source_columns: list[str],
) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for source in source_columns:
        for rank, name in enumerate(
            split_names(getattr(row, source)),
            1,
        ):
            key = compact(name)
            if not key:
                continue
            candidate = by_key.setdefault(
                key,
                {
                    "key": key,
                    "name": name,
                    "source_ranks": {},
                },
            )
            candidate["source_ranks"].setdefault(source, rank)
    query = row.input_compact
    query_bigrams = character_ngrams(query, 2)
    for candidate in by_key.values():
        maximum = max(len(query), len(candidate["key"]), 1)
        candidate["levenshtein_similarity"] = (
            1
            - Levenshtein.distance(query, candidate["key"])
            / maximum
        )
        candidate["jaro_winkler"] = JaroWinkler.similarity(
            query,
            candidate["key"],
        )
        candidate["bigram_dice"] = dice(
            query_bigrams,
            character_ngrams(candidate["key"], 2),
        )
    return list(by_key.values())


def expected_candidate_evidence(
    candidates: list[dict[str, Any]],
    expected: set[str],
) -> dict[str, Any]:
    """Describe why the expected family can or cannot pass the top-20 gate."""

    matching = [
        active_candidate_view(candidate, None)
        for candidate in candidates
        if candidate["key"] in expected
    ]
    matching = [candidate for candidate in matching if candidate is not None]
    if not matching:
        return {
            "expected_source_count": 0,
            "expected_sources": "",
            "expected_source_ranks": "",
            "expected_levenshtein_similarity": 0.0,
            "expected_jaro_winkler": 0.0,
            "expected_bigram_dice": 0.0,
            "expected_passes_top_20_gate": 0,
            "expected_gate_failure": "absent_from_all_selected_source_top20_lists",
        }

    candidate = sorted(
        matching,
        key=lambda item: (
            -item["source_count"],
            -item["rrf"],
            -item["levenshtein_similarity"],
            -item["jaro_winkler"],
            item["name"].casefold(),
            item["key"],
        ),
    )[0]
    failures = []
    if candidate["source_count"] < TOP_20_GATE["minimum_sources"]:
        failures.append("fewer_than_three_supporting_sources")
    if (
        candidate["levenshtein_similarity"]
        < TOP_20_GATE["minimum_levenshtein_similarity"]
    ):
        failures.append("levenshtein_similarity_below_0_55")
    if candidate["jaro_winkler"] < TOP_20_GATE["minimum_jaro_winkler"]:
        failures.append("jaro_winkler_below_0_85")
    return {
        "expected_source_count": candidate["source_count"],
        "expected_sources": ";".join(sorted(candidate["active_ranks"])),
        "expected_source_ranks": ";".join(
            f"{source}:{rank}"
            for source, rank in sorted(candidate["active_ranks"].items())
        ),
        "expected_levenshtein_similarity": candidate[
            "levenshtein_similarity"
        ],
        "expected_jaro_winkler": candidate["jaro_winkler"],
        "expected_bigram_dice": candidate["bigram_dice"],
        "expected_passes_top_20_gate": int(not failures),
        "expected_gate_failure": ";".join(failures) or "none",
    }


def active_candidate_view(
    candidate: dict[str, Any],
    excluded_source: str | None,
) -> dict[str, Any] | None:
    ranks = {
        source: rank
        for source, rank in candidate["source_ranks"].items()
        if source != excluded_source
    }
    if not ranks:
        return None
    return {
        **candidate,
        "active_ranks": ranks,
        "source_count": len(ranks),
        "rrf": sum(1 / (60 + rank) for rank in ranks.values()),
        "algorithm_5_rank": ranks.get("algorithm_5", 999),
    }


def replay_order(
    candidates: list[dict[str, Any]],
    base_names: list[str],
    variant_family_keys: set[str],
    *,
    excluded_source: str | None = None,
    enable_rank_1_gate: bool = True,
    enable_top_20_gate: bool = True,
) -> tuple[list[dict[str, Any]], bool, bool]:
    active = [
        view
        for candidate in candidates
        if (
            view := active_candidate_view(candidate, excluded_source)
        )
        is not None
    ]
    active.sort(
        key=lambda candidate: (
            -candidate["source_count"],
            -candidate["rrf"],
            -candidate["levenshtein_similarity"],
            -candidate["jaro_winkler"],
            candidate["name"].casefold(),
            candidate["key"],
        )
    )
    by_key = {candidate["key"]: candidate for candidate in active}
    base = [
        by_key[key]
        for key in (compact(name) for name in base_names[:20])
        if key in by_key
    ]
    promoted = False
    if enable_rank_1_gate and base and active:
        current = base[0]
        proposed = active[0]
        gate = RANK_1_GATE
        if (
            proposed["key"] != current["key"]
            and current["key"] not in variant_family_keys
            and proposed["algorithm_5_rank"]
            <= gate["maximum_algorithm_5_rank"]
            and proposed["source_count"] >= gate["minimum_sources"]
            and proposed["source_count"]
            >= current["source_count"]
            + gate["minimum_source_advantage"]
            and proposed["levenshtein_similarity"]
            >= current["levenshtein_similarity"]
            + gate["minimum_levenshtein_advantage"]
            and proposed["jaro_winkler"]
            >= current["jaro_winkler"]
            - gate["maximum_jaro_disadvantage"]
            and proposed["bigram_dice"]
            >= current["bigram_dice"]
            + gate["minimum_bigram_advantage"]
        ):
            index = next(
                (
                    position
                    for position, candidate in enumerate(base)
                    if candidate["key"] == proposed["key"]
                ),
                None,
            )
            if index is not None:
                base.insert(0, base.pop(index))
                promoted = True

    inserted = False
    if enable_top_20_gate:
        base_keys = {
            compact(name) for name in base_names[:20] if compact(name)
        }
        available = (
            20 - len(base)
            if len(base) < 20
            else TOP_20_GATE["slots"]
        )
        external = [
            candidate
            for candidate in active
            if candidate["key"] not in base_keys
            and candidate["source_count"]
            >= TOP_20_GATE["minimum_sources"]
            and candidate["levenshtein_similarity"]
            >= TOP_20_GATE["minimum_levenshtein_similarity"]
            and candidate["jaro_winkler"]
            >= TOP_20_GATE["minimum_jaro_winkler"]
        ][:available]
        for candidate in external:
            if len(base) >= 20:
                base.pop()
            base.append(candidate)
            inserted = True
    return base[:20], promoted, inserted


def first_relevant_rank(
    ordered: list[dict[str, Any]],
    expected: set[str],
) -> int:
    return next(
        (
            rank
            for rank, candidate in enumerate(ordered, 1)
            if candidate["key"] in expected
        ),
        999,
    )


def metric_row(
    dataset: str,
    split: str,
    configuration: str,
    ranks: list[int],
) -> dict[str, Any]:
    values = np.asarray(ranks)
    return {
        "dataset": dataset,
        "split": split,
        "configuration": configuration,
        "cases": len(values),
        "hit_at_1": float(np.mean(values <= 1)),
        "hit_at_5": float(np.mean(values <= 5)),
        "hit_at_20": float(np.mean(values <= 20)),
        "mrr_at_20": float(
            np.mean(np.where(values <= 20, 1 / values, 0))
        ),
        "outside_top_20": int(np.sum(values > 20)),
    }


def replay_dataset(
    dataset: str,
    frame: pd.DataFrame,
    variant_family_keys: set[str],
    artifacts_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    source_columns = list(SOURCE_COLUMN_BY_RETRIEVER.values())
    rank_1_enabled = bool(RANK_1_GATE["enabled"])
    configurations = {
        "algorithm_6_full": (None, rank_1_enabled, True),
        "algorithm_5_reference": (None, False, False),
        "exploratory_with_rank_1_consensus_gate": (
            None,
            True,
            True,
        ),
        "without_top_20_consensus_slot": (
            None,
            rank_1_enabled,
            False,
        ),
        **{
            f"without_{source}": (
                source,
                rank_1_enabled,
                True,
            )
            for source in source_columns
            if source != "algorithm_5"
        },
    }
    ranks_by_configuration: dict[str, list[int]] = {
        name: [] for name in configurations
    }
    split_ranks: dict[tuple[str, str], list[int]] = defaultdict(list)
    result_rows = []
    change_rows = []
    started = time.perf_counter()
    for index, row in enumerate(frame.itertuples(), 1):
        candidates = replay_candidates(row, source_columns)
        base_names = split_names(row.algorithm_5)
        expected = {
            key
            for key in str(row.expected_family_keys).split(";")
            if key
        }
        full_order: list[dict[str, Any]] = []
        full_promoted = False
        full_inserted = False
        current_ranks: dict[str, int] = {}
        for configuration, (
            excluded_source,
            enable_rank_1,
            enable_top_20,
        ) in configurations.items():
            if configuration == "algorithm_5_reference":
                ordered = [
                    {
                        "key": compact(name),
                        "name": name,
                        "source_count": 1,
                        "rrf": 1 / (60 + rank),
                        "levenshtein_similarity": 0.0,
                        "jaro_winkler": 0.0,
                        "bigram_dice": 0.0,
                    }
                    for rank, name in enumerate(base_names[:20], 1)
                    if compact(name)
                ]
                promoted = False
                inserted = False
            else:
                ordered, promoted, inserted = replay_order(
                    candidates,
                    base_names,
                    variant_family_keys,
                    excluded_source=excluded_source,
                    enable_rank_1_gate=enable_rank_1,
                    enable_top_20_gate=enable_top_20,
                )
            rank = first_relevant_rank(ordered, expected)
            ranks_by_configuration[configuration].append(rank)
            split_ranks[(configuration, row.split)].append(rank)
            current_ranks[configuration] = rank
            if configuration == "algorithm_6_full":
                full_order = ordered
                full_promoted = promoted
                full_inserted = inserted
        rank = ranks_by_configuration["algorithm_6_full"][-1]
        top_names = [candidate["name"] for candidate in full_order]
        top = full_order[0] if full_order else None
        second = full_order[1] if len(full_order) > 1 else None
        expected_evidence = expected_candidate_evidence(candidates, expected)
        if rank > 20 and expected_evidence["expected_passes_top_20_gate"]:
            expected_evidence["expected_gate_failure"] = (
                "passes_gate_but_loses_single_external_slot"
            )
        result_rows.append(
            {
                "evaluation_version": "algorithm_6_consensus_v1",
                "dataset": dataset,
                "case_id": row.case_id,
                "input": row.input,
                "input_compact": row.input_compact,
                "input_compact_length": len(row.input_compact),
                "expected_family_keys": row.expected_family_keys,
                "expected_family_name": row.expected_family_name,
                "split": row.split,
                "category": row.category,
                "error_type": row.error_type,
                "operation_family": row.operation_family,
                "edit_distance": row.edit_distance,
                "normalized_distance": row.normalized_distance,
                "first_relevant_rank": rank,
                "hit_at_1": int(rank <= 1),
                "hit_at_5": int(rank <= 5),
                "hit_at_20": int(rank <= 20),
                "reciprocal_rank_at_20": (
                    1 / rank if rank <= 20 else 0.0
                ),
                "algorithm_6_promoted": int(full_promoted),
                "algorithm_6_external_slot_used": int(full_inserted),
                **expected_evidence,
                "top_1_source_count": (
                    top["source_count"] if top else 0
                ),
                "top_1_rrf": top["rrf"] if top else 0.0,
                "top_1_levenshtein_similarity": (
                    top["levenshtein_similarity"] if top else 0.0
                ),
                "top_1_jaro_winkler": (
                    top["jaro_winkler"] if top else 0.0
                ),
                "top_1_bigram_dice": (
                    top["bigram_dice"] if top else 0.0
                ),
                "top_1_minus_top_2_source_count": (
                    top["source_count"] - second["source_count"]
                    if top and second
                    else top["source_count"] if top else 0
                ),
                "top_1_minus_top_2_rrf": (
                    top["rrf"] - second["rrf"]
                    if top and second
                    else top["rrf"] if top else 0.0
                ),
                "top_1_minus_top_2_levenshtein": (
                    top["levenshtein_similarity"]
                    - second["levenshtein_similarity"]
                    if top and second
                    else top["levenshtein_similarity"] if top else 0.0
                ),
                "top_1_minus_top_2_jaro": (
                    top["jaro_winkler"] - second["jaro_winkler"]
                    if top and second
                    else top["jaro_winkler"] if top else 0.0
                ),
                "returned_candidates": len(full_order),
                "top_1": top_names[0] if top_names else "",
                "top_20": ";".join(top_names),
                "algorithm_5_top_1": row.top_1,
                "algorithm_5_top_20": row.algorithm_5,
                "algorithm_5_first_relevant_rank": (
                    row.first_relevant_rank
                ),
                "algorithm_5_hit_at_1": row.hit_at_1,
                "algorithm_5_hit_at_20": row.hit_at_20,
                "exploratory_first_relevant_rank": current_ranks[
                    "exploratory_with_rank_1_consensus_gate"
                ],
                "exploratory_hit_at_1": int(
                    current_ranks[
                        "exploratory_with_rank_1_consensus_gate"
                    ]
                    <= 1
                ),
                "exploratory_hit_at_20": int(
                    current_ranks[
                        "exploratory_with_rank_1_consensus_gate"
                    ]
                    <= 20
                ),
            }
        )
        if (
            full_promoted
            or full_inserted
            or int(rank <= 1) != int(row.hit_at_1)
            or int(rank <= 20) != int(row.hit_at_20)
        ):
            change_rows.append(
                {
                    "dataset": dataset,
                    "case_id": row.case_id,
                    "split": row.split,
                    "input": row.input,
                    "expected": row.expected_family_name,
                    "algorithm_5_top_1": row.top_1,
                    "algorithm_6_top_1": top_names[0] if top_names else "",
                    "algorithm_5_rank": row.first_relevant_rank,
                    "algorithm_6_rank": rank,
                    "promoted": int(full_promoted),
                    "external_slot_used": int(full_inserted),
                    "hit_1_delta": int(rank <= 1) - int(row.hit_at_1),
                    "hit_20_delta": int(rank <= 20) - int(row.hit_at_20),
                }
            )
        if index % 5_000 == 0:
            print(
                f"[replay] {dataset}: {index:,}/{len(frame):,} "
                f"({time.perf_counter() - started:.1f}s)",
                flush=True,
            )

    metrics = []
    for configuration, ranks in ranks_by_configuration.items():
        metrics.append(
            metric_row(dataset, "all", configuration, ranks)
        )
        for split in sorted(frame["split"].unique()):
            metrics.append(
                metric_row(
                    dataset,
                    split,
                    configuration,
                    split_ranks[(configuration, split)],
                )
            )
    results = pd.DataFrame(result_rows)
    changes = pd.DataFrame(change_rows)
    metrics_frame = pd.DataFrame(metrics)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(
        artifacts_dir / f"algorithm_6_{dataset}_results.csv.gz",
        index=False,
        compression="gzip",
    )
    changes.to_csv(
        artifacts_dir / f"algorithm_6_{dataset}_changes.csv",
        index=False,
    )
    return results, changes, metrics_frame


def replay_nested_algorithm_5_ablations(
    dataset: str,
    frame: pd.DataFrame,
    reference_results: pd.DataFrame,
    variant_family_keys: set[str],
    competitor_root: Path,
) -> pd.DataFrame:
    """Ablate Algorithm 5 internals while keeping Algorithm 6 consensus active."""

    suffix = "ocr_464" if dataset == "ocr" else "synthetic_66257"
    ablation_dir = competitor_root / f"a5_ablation_{suffix}"
    paths = sorted(ablation_dir.glob("without_*.csv.gz"))
    if not paths:
        raise FileNotFoundError(
            f"no nested Algorithm 5 ablations found in {ablation_dir}"
        )

    inventory_path = (
        ROOT / "results/06_competitor_benchmark/a5_ablation_inventory.csv"
    )
    inventory = pd.read_csv(inventory_path).set_index("name")
    reference = reference_results.set_index("case_id").to_dict("index")
    expected_ids = set(frame["case_id"])
    source_columns = list(SOURCE_COLUMN_BY_RETRIEVER.values())
    variants = {}
    for path in paths:
        name = path.name.removesuffix(".csv.gz")
        variant = pd.read_csv(
            path,
            usecols=["case_id", "top_20"],
        )
        if set(variant["case_id"]) != expected_ids:
            raise ValueError(
                f"{dataset}/{name}: case IDs do not match the replay contract"
            )
        variants[name] = variant.set_index("case_id")["top_20"].to_dict()

    states = {
        name: {
            "ranks": defaultdict(list),
            "switches": defaultdict(Counter),
            "examples": {},
        }
        for name in variants
    }
    started = time.perf_counter()
    for index, row in enumerate(frame.itertuples(), 1):
        expected = {
            key
            for key in str(row.expected_family_keys).split(";")
            if key
        }
        reference_row = reference[row.case_id]
        reference_rank = int(reference_row["first_relevant_rank"])
        reference_top_1 = reference_row["top_1"]
        full_base_names = split_names(row.algorithm_5)
        cached_results: dict[str, tuple[int, str]] = {}
        for name, values_by_case in variants.items():
            raw_top_20 = values_by_case[row.case_id]
            cache_key = "" if pd.isna(raw_top_20) else str(raw_top_20)
            if cache_key not in cached_results:
                base_names = split_names(raw_top_20)
                row_values = row._asdict()
                row_values["algorithm_5"] = raw_top_20
                replay_row = SimpleNamespace(**row_values)
                candidates = replay_candidates(replay_row, source_columns)
                ordered, _, _ = replay_order(
                    candidates,
                    base_names,
                    variant_family_keys,
                    enable_rank_1_gate=bool(RANK_1_GATE["enabled"]),
                    enable_top_20_gate=True,
                )
                cached_results[cache_key] = (
                    first_relevant_rank(ordered, expected),
                    ordered[0]["name"] if ordered else "",
                )
            rank, top_1 = cached_results[cache_key]
            state = states[name]
            for split in ("all", row.split):
                state["ranks"][split].append(rank)
                switches = state["switches"][split]
                switches["hit_at_1_gains"] += int(
                    reference_rank > 1 and rank <= 1
                )
                switches["hit_at_1_losses"] += int(
                    reference_rank <= 1 and rank > 1
                )
                switches["hit_at_20_gains"] += int(
                    reference_rank > 20 and rank <= 20
                )
                switches["hit_at_20_losses"] += int(
                    reference_rank <= 20 and rank > 20
                )

                effect = ""
                priority = 999
                if reference_rank <= 20 and rank > 20:
                    effect, priority = "lost_hit_at_20", 0
                elif reference_rank > 20 and rank <= 20:
                    effect, priority = "gained_hit_at_20", 1
                elif reference_rank <= 1 and rank > 1:
                    effect, priority = "lost_hit_at_1", 2
                elif reference_rank > 1 and rank <= 1:
                    effect, priority = "gained_hit_at_1", 3
                elif reference_top_1 != top_1:
                    effect, priority = "ranking_changed_without_top_k_change", 4
                elif split_names(raw_top_20) != full_base_names:
                    effect, priority = (
                        "base_candidate_list_changed_without_rank_change",
                        5,
                    )
                if effect:
                    current = state["examples"].get(split)
                    candidate = {
                        "priority": priority,
                        "case_id": row.case_id,
                        "effect": effect,
                        "input": row.input,
                        "expected": row.expected_family_name,
                        "reference_rank": reference_rank,
                        "ablation_rank": rank,
                    }
                    if current is None or (
                        priority,
                        row.case_id,
                    ) < (current["priority"], current["case_id"]):
                        state["examples"][split] = candidate
        if index % 5_000 == 0:
            print(
                f"[ablation] {dataset}: {index:,}/{len(frame):,} "
                f"({time.perf_counter() - started:.1f}s)",
                flush=True,
            )

    metric_rows = []
    for name, state in states.items():
        metadata = inventory.loc[name]
        for split, ranks in state["ranks"].items():
            row = metric_row(
                dataset,
                split,
                f"algorithm_6_nested__{name}",
                ranks,
            )
            switches = state["switches"][split]
            example = state["examples"].get(split)
            row.update(
                {
                    "ablation_scope": "nested_algorithm_5_component",
                    "removed_component": str(metadata["display_name"]).removeprefix(
                        "Without "
                    ),
                    "component_definition": metadata["definition"],
                    "ablation_level": metadata["level"],
                    "paired_hit_at_1_gains": switches["hit_at_1_gains"],
                    "paired_hit_at_1_losses": switches["hit_at_1_losses"],
                    "paired_hit_at_20_gains": switches["hit_at_20_gains"],
                    "paired_hit_at_20_losses": switches["hit_at_20_losses"],
                    "example_effect": example["effect"] if example else "",
                    "example_input": example["input"] if example else "",
                    "example_expected": example["expected"] if example else "",
                    "example_reference_rank": (
                        example["reference_rank"] if example else ""
                    ),
                    "example_ablation_rank": (
                        example["ablation_rank"] if example else ""
                    ),
                }
            )
            metric_rows.append(row)
    return pd.DataFrame(metric_rows)


def common_prefix(left: str, right: str) -> int:
    for index, (left_character, right_character) in enumerate(
        zip(left, right)
    ):
        if left_character != right_character:
            return index
    return min(len(left), len(right))


def same_position(left: str, right: str) -> float:
    return sum(
        left_character == right_character
        for left_character, right_character in zip(left, right)
    ) / max(len(left), len(right), 1)


def candidate_feature_row(
    query: str,
    candidate: dict[str, Any],
    source_columns: list[str],
) -> dict[str, float]:
    target = candidate["key"]
    maximum = max(len(query), len(target), 1)
    query_length = max(len(query), 1)
    target_length = max(len(target), 1)
    prefix = common_prefix(query, target)
    suffix = common_prefix(query[::-1], target[::-1])
    query_bigrams = character_ngrams(query, 2)
    target_bigrams = character_ngrams(target, 2)
    query_trigrams = character_ngrams(query, 3)
    target_trigrams = character_ngrams(target, 3)
    ranks = candidate["source_ranks"]
    result = {
        "exact": float(query == target),
        "levenshtein_similarity": (
            1 - Levenshtein.distance(query, target) / maximum
        ),
        "damerau_similarity": (
            1 - DamerauLevenshtein.distance(query, target) / maximum
        ),
        "jaro_winkler": JaroWinkler.similarity(query, target),
        "rapidfuzz_ratio": fuzz.ratio(query, target) / 100,
        "rapidfuzz_wratio": fuzz.WRatio(query, target) / 100,
        "lcs_similarity": LCSseq.normalized_similarity(query, target),
        "bigram_dice": dice(query_bigrams, target_bigrams),
        "trigram_dice": dice(query_trigrams, target_trigrams),
        "prefix_query": prefix / query_length,
        "prefix_candidate": prefix / target_length,
        "suffix_query": suffix / query_length,
        "suffix_candidate": suffix / target_length,
        "same_position": same_position(query, target),
        "length_ratio": (
            min(query_length, target_length)
            / max(query_length, target_length)
        ),
        "length_delta": abs(query_length - target_length),
        "first_same": float(query[:1] == target[:1]),
        "last_same": float(query[-1:] == target[-1:]),
        "query_is_candidate_prefix": float(query in target),
        "candidate_is_query_prefix": float(target in query),
        "skeleton_equal": float(
            current_app.skeleton(query)
            == current_app.skeleton(target)
        ),
        "phonetic_equal": float(
            current_app.drug_phonetic_key(query)
            == current_app.drug_phonetic_key(target)
        ),
        "source_count": len(ranks),
        "rrf": sum(1 / (60 + rank) for rank in ranks.values()),
        "best_rank_reciprocal": 1 / min(ranks.values()),
        "mean_rank_reciprocal": (
            len(ranks) / sum(ranks.values())
        ),
    }
    for source in source_columns:
        rank = ranks.get(source)
        result[f"{source}_present"] = float(rank is not None)
        result[f"{source}_reciprocal_rank"] = (
            1 / rank if rank else 0.0
        )
    return result


RANKER_METADATA_COLUMNS = {
    "case_id",
    "candidate_key",
    "candidate_name",
    "expected_family_keys",
    "split",
    "crossfit_fold",
    "training_eligible",
    "label",
}


def build_ranker_matrix(
    frame: pd.DataFrame,
    contract: pd.DataFrame,
    audit: pd.DataFrame,
    output_path: Path,
) -> pd.DataFrame:
    source_columns = list(SOURCE_COLUMN_BY_RETRIEVER.values())
    fold_by_case = contract.set_index("case_id")[
        "crossfit_fold"
    ].to_dict()
    eligible_by_case = audit.set_index("case_id")[
        "provisional_model_training_eligibility"
    ].to_dict()
    rows = []
    for row in frame.itertuples():
        expected = {
            key
            for key in str(row.expected_family_keys).split(";")
            if key
        }
        for candidate in replay_candidates(row, source_columns):
            values: dict[str, Any] = {
                "case_id": row.case_id,
                "candidate_key": candidate["key"],
                "candidate_name": candidate["name"],
                "expected_family_keys": row.expected_family_keys,
                "split": row.split,
                "crossfit_fold": fold_by_case.get(row.case_id),
                "training_eligible": int(
                    eligible_by_case.get(row.case_id, 0)
                ),
                "label": int(candidate["key"] in expected),
            }
            values.update(
                candidate_feature_row(
                    row.input_compact,
                    candidate,
                    source_columns,
                )
            )
            rows.append(values)
    matrix = pd.DataFrame(rows)
    matrix.to_csv(output_path, index=False, compression="gzip")
    return matrix


def rank_groups(frame: pd.DataFrame) -> list[int]:
    return frame.groupby("case_id", sort=False).size().tolist()


def ranker_metrics(
    frame: pd.DataFrame,
    scores: np.ndarray,
) -> dict[str, Any]:
    scored = frame[["case_id", "label"]].copy()
    scored["score"] = scores
    ranks = []
    for _, group in scored.groupby("case_id", sort=False):
        ordered = group.sort_values(
            "score",
            ascending=False,
            kind="mergesort",
        )
        relevant = np.flatnonzero(
            ordered["label"].to_numpy() == 1
        )
        ranks.append(
            int(relevant[0] + 1) if len(relevant) else 999
        )
    values = np.asarray(ranks)
    return {
        "cases": len(values),
        "hit_at_1": float(np.mean(values <= 1)),
        "hit_at_5": float(np.mean(values <= 5)),
        "hit_at_20": float(np.mean(values <= 20)),
        "mrr_at_20": float(
            np.mean(np.where(values <= 20, 1 / values, 0))
        ),
    }


def fit_ranker(
    train: pd.DataFrame,
    features: list[str],
) -> lgb.LGBMRanker:
    ordered = train.sort_values(
        ["case_id", "candidate_key"],
        kind="mergesort",
    )
    model = lgb.LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        n_estimators=180,
        num_leaves=15,
        min_child_samples=40,
        learning_rate=0.03,
        reg_lambda=3.0,
        reg_alpha=0.2,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=20260724,
        verbosity=-1,
    )
    model.fit(
        ordered[features],
        ordered["label"],
        group=rank_groups(ordered),
        feature_name=features,
    )
    return model


def run_learned_ranker_study(
    matrix: pd.DataFrame,
    artifacts_dir: Path,
    results_dir: Path,
) -> pd.DataFrame:
    all_features = sorted(
        set(matrix.columns) - RANKER_METADATA_COLUMNS
    )
    source_features = [
        feature
        for feature in all_features
        if feature.endswith("_present")
        or feature.endswith("_reciprocal_rank")
        or feature
        in {
            "source_count",
            "rrf",
            "best_rank_reciprocal",
            "mean_rank_reciprocal",
        }
    ]
    edit_features = [
        feature
        for feature in (
            "levenshtein_similarity",
            "damerau_similarity",
            "jaro_winkler",
            "rapidfuzz_ratio",
            "rapidfuzz_wratio",
            "lcs_similarity",
        )
        if feature in all_features
    ]
    structure_features = [
        feature
        for feature in (
            "bigram_dice",
            "trigram_dice",
            "prefix_query",
            "prefix_candidate",
            "suffix_query",
            "suffix_candidate",
            "same_position",
        )
        if feature in all_features
    ]
    phonetic_features = [
        feature
        for feature in ("skeleton_equal", "phonetic_equal")
        if feature in all_features
    ]
    length_features = [
        feature
        for feature in (
            "length_ratio",
            "length_delta",
            "first_same",
            "last_same",
            "query_is_candidate_prefix",
            "candidate_is_query_prefix",
        )
        if feature in all_features
    ]
    configurations = {
        "full_learned_ranker": all_features,
        "without_retriever_features": [
            feature
            for feature in all_features
            if feature not in source_features
        ],
        "without_edit_features": [
            feature
            for feature in all_features
            if feature not in edit_features
        ],
        "without_ngram_and_edge_features": [
            feature
            for feature in all_features
            if feature not in structure_features
        ],
        "without_phonetic_features": [
            feature
            for feature in all_features
            if feature not in phonetic_features
        ],
        "without_length_and_position_features": [
            feature
            for feature in all_features
            if feature not in length_features
        ],
    }
    development = matrix[matrix["split"].eq("development")].copy()
    holdout = matrix[matrix["split"].eq("holdout")].copy()
    metrics = []
    full_importance = None
    for name, features in configurations.items():
        oof_scores = np.full(len(development), np.nan)
        for fold in range(CROSS_FIT_FOLDS):
            validation_mask = development["crossfit_fold"].eq(fold)
            train = development[
                ~validation_mask
                & development["training_eligible"].eq(1)
            ].copy()
            train = train[
                train.groupby("case_id")["label"]
                .transform("max")
                .eq(1)
            ]
            model = fit_ranker(train, features)
            oof_scores[validation_mask.to_numpy()] = model.predict(
                development.loc[validation_mask, features]
            )
        development_metrics = ranker_metrics(
            development,
            oof_scores,
        )
        metrics.append(
            {
                "configuration": name,
                "split": "crossfit_development",
                **development_metrics,
            }
        )
        final_train = development[
            development["training_eligible"].eq(1)
        ].copy()
        final_train = final_train[
            final_train.groupby("case_id")["label"]
            .transform("max")
            .eq(1)
        ]
        model = fit_ranker(final_train, features)
        holdout_scores = model.predict(holdout[features])
        metrics.append(
            {
                "configuration": name,
                "split": "retrospective_holdout",
                **ranker_metrics(holdout, holdout_scores),
            }
        )
        if name == "full_learned_ranker":
            model.booster_.save_model(
                str(artifacts_dir / "advisory_ranker.txt")
            )
            development_scores = development[
                ["case_id", "candidate_key", "label"]
            ].copy()
            development_scores["score"] = oof_scores
            development_scores.to_csv(
                artifacts_dir
                / "advisory_ranker_crossfit_scores.csv.gz",
                index=False,
                compression="gzip",
            )
            full_importance = pd.DataFrame(
                {
                    "feature": features,
                    "gain": model.booster_.feature_importance("gain"),
                }
            ).sort_values("gain", ascending=False)
    if full_importance is not None:
        full_importance.to_csv(
            results_dir / "learned_ranker_feature_importance.csv",
            index=False,
        )
    output = pd.DataFrame(metrics)
    output.to_csv(
        results_dir / "learned_ranker_ablation_metrics.csv",
        index=False,
    )
    return output


def validate_runtime_ocr(
    algorithm_6: ModuleType,
    catalog: Any,
    replay: pd.DataFrame,
    output_dir: Path,
) -> pd.DataFrame:
    expected_replay = replay.set_index("case_id")
    rows = []
    started = time.perf_counter()
    for index, replay_row in enumerate(replay.itertuples(), 1):
        response = algorithm_6.search_catalog(
            catalog,
            replay_row.input,
            20,
        )
        names = [
            algorithm_6.result_name(item)
            for item in response.get("results") or []
        ][:20]
        expected = {
            key
            for key in str(replay_row.expected_family_keys).split(";")
            if key
        }
        keys = [compact(name) for name in names]
        rank = next(
            (
                position
                for position, key in enumerate(keys, 1)
                if key in expected
            ),
            999,
        )
        cached = expected_replay.loc[replay_row.case_id]
        rows.append(
            {
                "case_id": replay_row.case_id,
                "input": replay_row.input,
                "expected": replay_row.expected_family_name,
                "runtime_rank": rank,
                "runtime_top_1": names[0] if names else "",
                "runtime_top_20": ";".join(names),
                "replay_rank": cached["first_relevant_rank"],
                "replay_top_1": cached["top_1"],
                "replay_top_20": cached["top_20"],
                "rank_match": int(
                    rank == cached["first_relevant_rank"]
                ),
                "top_1_match": int(
                    (names[0] if names else "") == cached["top_1"]
                ),
                "top_20_match": int(
                    ";".join(names) == cached["top_20"]
                ),
                "status": response.get("status", ""),
                "decision_type": response.get("decision_type", ""),
            }
        )
        if index % 50 == 0:
            print(
                f"[runtime] OCR: {index}/{len(replay)} "
                f"({time.perf_counter() - started:.1f}s)",
                flush=True,
            )
    validation = pd.DataFrame(rows)
    validation.to_csv(
        output_dir / "runtime_replay_validation.csv",
        index=False,
    )
    return validation


ABSTENTION_FEATURES = [
    "top_1_source_count",
    "top_1_rrf",
    "top_1_levenshtein_similarity",
    "top_1_jaro_winkler",
    "top_1_bigram_dice",
    "top_1_minus_top_2_source_count",
    "top_1_minus_top_2_rrf",
    "top_1_minus_top_2_levenshtein",
    "top_1_minus_top_2_jaro",
    "returned_candidates",
    "algorithm_6_promoted",
    "algorithm_6_external_slot_used",
    "input_compact_length",
]
ABSTENTION_EVIDENCE_MINIMUMS = {
    "top_1_source_count": 7,
    "top_1_levenshtein_similarity": 0.70,
}


def wilson_lower_bound(
    successes: int,
    total: int,
    z: float = 1.96,
) -> float:
    if total == 0:
        return 0.0
    probability = successes / total
    denominator = 1 + z * z / total
    center = probability + z * z / (2 * total)
    adjustment = z * math.sqrt(
        (
            probability * (1 - probability)
            + z * z / (4 * total)
        )
        / total
    )
    return (center - adjustment) / denominator


def run_abstention_study(
    results: pd.DataFrame,
    contract: pd.DataFrame,
    audit: pd.DataFrame,
    results_dir: Path,
) -> tuple[dict[str, Any], pd.DataFrame]:
    data = results.merge(
        contract[["case_id", "crossfit_fold"]],
        on="case_id",
        how="left",
        validate="one_to_one",
    )
    data = data.merge(
        audit[
            [
                "case_id",
                "provisional_model_training_eligibility",
            ]
        ],
        on="case_id",
        how="left",
        validate="one_to_one",
    )
    development = data[data["split"].eq("development")].copy()
    holdout = data[data["split"].eq("holdout")].copy()
    oof_probability = np.full(len(development), np.nan)
    for fold in range(CROSS_FIT_FOLDS):
        validation = development["crossfit_fold"].eq(fold)
        train = development[
            ~validation
            & development[
                "provisional_model_training_eligibility"
            ].eq(1)
        ]
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(
                C=0.25,
                class_weight="balanced",
                max_iter=2_000,
                random_state=20260724,
            ),
        )
        model.fit(train[ABSTENTION_FEATURES], train["hit_at_1"])
        oof_probability[validation.to_numpy()] = model.predict_proba(
            development.loc[validation, ABSTENTION_FEATURES]
        )[:, 1]
    development["probability"] = oof_probability
    calibration_source = development[
        development[
            "provisional_model_training_eligibility"
        ].eq(1)
    ]
    evidence_guard = pd.Series(True, index=calibration_source.index)
    for feature, minimum in ABSTENTION_EVIDENCE_MINIMUMS.items():
        evidence_guard &= calibration_source[feature].ge(minimum)
    threshold_rows = []
    for threshold in np.linspace(0.00, 0.995, 200):
        accepted = (
            calibration_source["probability"].ge(threshold)
            & evidence_guard
        )
        total = int(accepted.sum())
        correct = int(
            calibration_source.loc[accepted, "hit_at_1"].sum()
        )
        threshold_rows.append(
            {
                "threshold": threshold,
                "accepted": total,
                "coverage": total / len(calibration_source),
                "correct": correct,
                "errors": total - correct,
                "precision": correct / total if total else 0.0,
                "wilson_lower_95": wilson_lower_bound(
                    correct,
                    total,
                ),
            }
        )
    threshold_table = pd.DataFrame(threshold_rows)
    eligible_thresholds = threshold_table[
        threshold_table["errors"].eq(0)
        & threshold_table["accepted"].ge(5)
    ]
    if eligible_thresholds.empty:
        selected_threshold = 1.0
    else:
        selected_threshold = float(
            eligible_thresholds.sort_values(
                ["coverage", "threshold"],
                ascending=[False, False],
            ).iloc[0]["threshold"]
        )

    final_train = development[
        development[
            "provisional_model_training_eligibility"
        ].eq(1)
    ]
    final_model = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            C=0.25,
            class_weight="balanced",
            max_iter=2_000,
            random_state=20260724,
        ),
    )
    final_model.fit(
        final_train[ABSTENTION_FEATURES],
        final_train["hit_at_1"],
    )
    holdout["probability"] = final_model.predict_proba(
        holdout[ABSTENTION_FEATURES]
    )[:, 1]
    calibration_rows = pd.concat(
        [
            development.assign(calibration_view="crossfit_development"),
            holdout.assign(calibration_view="retrospective_holdout"),
        ],
        ignore_index=True,
    )
    calibration_rows[
        [
            "case_id",
            "input",
            "expected_family_name",
            "split",
            "calibration_view",
            "provisional_model_training_eligibility",
            "top_1",
            "hit_at_1",
            "probability",
            *ABSTENTION_FEATURES,
        ]
    ].to_csv(
        results_dir / "abstention_case_scores.csv",
        index=False,
    )
    evaluation_rows = []
    for split_name, split_data in (
        (
            "crossfit_development_all",
            development,
        ),
        (
            "crossfit_development_audit_clean",
            development[
                development[
                    "provisional_model_training_eligibility"
                ].eq(1)
            ],
        ),
        (
            "retrospective_holdout_all",
            holdout,
        ),
        (
            "retrospective_holdout_audit_clean",
            holdout[
                holdout[
                    "provisional_model_training_eligibility"
                ].eq(1)
            ],
        ),
    ):
        accepted = split_data["probability"].ge(selected_threshold)
        for feature, minimum in ABSTENTION_EVIDENCE_MINIMUMS.items():
            accepted &= split_data[feature].ge(minimum)
        correct = int(split_data.loc[accepted, "hit_at_1"].sum())
        total = int(accepted.sum())
        evaluation_rows.append(
            {
                "split": split_name,
                "threshold": selected_threshold,
                "cases": len(split_data),
                "accepted": total,
                "coverage": total / len(split_data),
                "correct": correct,
                "errors": total - correct,
                "selective_accuracy": (
                    correct / total if total else 0.0
                ),
                "wilson_lower_95": wilson_lower_bound(
                    correct,
                    total,
                ),
                "abstained": len(split_data) - total,
            }
        )
    evaluation = pd.DataFrame(evaluation_rows)
    threshold_table.to_csv(
        results_dir / "abstention_threshold_sweep.csv",
        index=False,
    )
    evaluation.to_csv(
        results_dir / "abstention_metrics.csv",
        index=False,
    )
    scaler = final_model.named_steps["standardscaler"]
    logistic = final_model.named_steps["logisticregression"]
    policy = {
        "mode": "logistic_correctness_gate",
        "features": ABSTENTION_FEATURES,
        "mean": [float(value) for value in scaler.mean_],
        "scale": [float(value) for value in scaler.scale_],
        "coefficients": [
            float(value) for value in logistic.coef_[0]
        ],
        "intercept": float(logistic.intercept_[0]),
        "threshold": selected_threshold,
        "evidence_minimums": ABSTENTION_EVIDENCE_MINIMUMS,
        "selection_rule": (
            "Largest target-family-cross-fit P2-audit-clean coverage with "
            "zero observed errors, at least five accepted cases, and fixed "
            "minimum consensus and lexical evidence."
        ),
        "output_semantics": (
            "A passing score means likely match requiring user confirmation; "
            "it never certifies clinical correctness."
        ),
    }
    return policy, evaluation


def main() -> None:
    args = parse_args()
    cases, contract, audit = prepare(args)
    if args.prepare_only:
        return

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    args.results_dir.mkdir(parents=True, exist_ok=True)

    policy, confusion_table = learn_confusion_policy(cases, audit)
    confusion_table.to_csv(
        args.results_dir / "learned_ocr_confusion_costs.csv",
        index=False,
    )
    ALGORITHM_6_POLICY_PATH.write_text(
        json.dumps(policy, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    algorithm_6 = load_module(
        ALGORITHM_6_PATH,
        "algorithm_6_experiment_runtime",
    )
    print("[prepare] Building Algorithm 6 catalog and retrieval indexes")
    catalog = algorithm_6.prepare_catalog(ALGORITHM_6_POLICY_PATH)

    metric_frames = []
    replay_frames: dict[str, pd.DataFrame] = {}
    replay_results: dict[str, pd.DataFrame] = {}
    replay_changes: dict[str, pd.DataFrame] = {}
    datasets = ["ocr"]
    if not args.skip_synthetic:
        datasets.append("synthetic")
    for dataset in datasets:
        print(f"[replay] Loading cached {dataset} candidate sources")
        frame = load_replay_frame(dataset, args.competitor_artifacts)
        results, changes, metrics = replay_dataset(
            dataset,
            frame,
            catalog.variant_family_keys,
            args.artifacts_dir,
        )
        reference = metrics[
            metrics["configuration"].eq("algorithm_5_reference")
            & metrics["split"].eq("all")
        ].iloc[0]
        if not (
            math.isclose(
                reference["hit_at_1"],
                frame["hit_at_1"].mean(),
                abs_tol=1e-12,
            )
            and math.isclose(
                reference["hit_at_20"],
                frame["hit_at_20"].mean(),
                abs_tol=1e-12,
            )
        ):
            raise ValueError(
                f"{dataset}: Algorithm 5 replay does not match its artifact"
            )
        replay_frames[dataset] = frame
        replay_results[dataset] = results
        replay_changes[dataset] = changes
        metric_frames.append(metrics)
        print(
            f"[ablation] Replaying nested Algorithm 5 components inside "
            f"Algorithm 6 on {dataset}"
        )
        metric_frames.append(
            replay_nested_algorithm_5_ablations(
                dataset,
                frame,
                results,
                catalog.variant_family_keys,
                args.competitor_artifacts,
            )
        )

    abstention_policy, abstention_metrics = run_abstention_study(
        replay_results["ocr"],
        contract,
        audit,
        args.results_dir,
    )
    policy["abstention"] = abstention_policy
    policy["deployment_decision"] = {
        "ranking": "algorithm_5_rank_1_plus_bounded_consensus_retrieval",
        "learned_ranker": "advisory_only",
        "reason": (
            "Neither the learned reranker nor the exploratory rank-1 consensus "
            "gate established a zero-loss gain across OCR and synthetic data. "
            "Algorithm 6 therefore preserves Algorithm 5 rank 1 and uses "
            "consensus only for bounded top-20 candidate recovery."
        ),
        "fresh_blind_claim_allowed": False,
    }
    ALGORITHM_6_POLICY_PATH.write_text(
        json.dumps(policy, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    catalog.policy = policy

    print("[ranker] Building the OCR candidate matrix")
    matrix = build_ranker_matrix(
        replay_frames["ocr"],
        contract,
        audit,
        args.artifacts_dir / "advisory_ranker_matrix.csv.gz",
    )
    print("[ranker] Running family-disjoint cross-fit ablations")
    learned_metrics = run_learned_ranker_study(
        matrix,
        args.artifacts_dir,
        args.results_dir,
    )

    runtime_validation = pd.DataFrame()
    if not args.skip_runtime_validation:
        print("[runtime] Comparing the live implementation with cached replay")
        runtime_validation = validate_runtime_ocr(
            algorithm_6,
            catalog,
            replay_results["ocr"],
            args.results_dir,
        )

    replay_metrics = pd.concat(metric_frames, ignore_index=True)
    replay_metrics.to_csv(
        args.results_dir / "algorithm_6_replay_metrics.csv",
        index=False,
    )

    def selected_metric(
        dataset: str,
        configuration: str,
    ) -> dict[str, Any]:
        row = replay_metrics[
            replay_metrics["dataset"].eq(dataset)
            & replay_metrics["split"].eq("all")
            & replay_metrics["configuration"].eq(configuration)
        ].iloc[0]
        return {
            "cases": int(row["cases"]),
            "hit_at_1": float(row["hit_at_1"]),
            "hit_at_5": float(row["hit_at_5"]),
            "hit_at_20": float(row["hit_at_20"]),
            "mrr_at_20": float(row["mrr_at_20"]),
            "outside_top_20": int(row["outside_top_20"]),
        }

    def paired_outcomes(dataset: str) -> dict[str, Any]:
        results = replay_results[dataset]

        def switches(
            candidate_hit_1: pd.Series,
            candidate_hit_20: pd.Series,
        ) -> dict[str, int]:
            reference_hit_1 = results["algorithm_5_hit_at_1"]
            reference_hit_20 = results["algorithm_5_hit_at_20"]
            return {
                "hit_at_1_gains": int(
                    ((candidate_hit_1 == 1) & (reference_hit_1 == 0)).sum()
                ),
                "hit_at_1_losses": int(
                    ((candidate_hit_1 == 0) & (reference_hit_1 == 1)).sum()
                ),
                "hit_at_20_gains": int(
                    ((candidate_hit_20 == 1) & (reference_hit_20 == 0)).sum()
                ),
                "hit_at_20_losses": int(
                    ((candidate_hit_20 == 0) & (reference_hit_20 == 1)).sum()
                ),
            }

        return {
            "deployed_algorithm_6": switches(
                results["hit_at_1"],
                results["hit_at_20"],
            ),
            "rejected_rank_1_consensus_gate": switches(
                results["exploratory_hit_at_1"],
                results["exploratory_hit_at_20"],
            ),
        }

    summary: dict[str, Any] = {
        "evaluation_version": policy["evaluation_version"],
        "fresh_blind_claim_allowed": False,
        "deployment": policy["deployment_decision"],
        "candidate_source_depth": {
            "ocr": {
                source: 20 for source in SELECTED_RETRIEVERS
            },
            "synthetic": {
                source: (
                    5
                    if source == "baseline_jaro_winkler"
                    else 20
                )
                for source in SELECTED_RETRIEVERS
            },
        },
        "ocr": {
            "algorithm_5": selected_metric(
                "ocr",
                "algorithm_5_reference",
            ),
            "algorithm_6": selected_metric(
                "ocr",
                "algorithm_6_full",
            ),
            "changed_rows": len(replay_changes["ocr"]),
            "rank_1_promotions": int(
                replay_results["ocr"]["algorithm_6_promoted"].sum()
            ),
            "external_top_20_slots": int(
                replay_results["ocr"][
                    "algorithm_6_external_slot_used"
                ].sum()
            ),
            "exploratory_rank_1_gate": selected_metric(
                "ocr",
                "exploratory_with_rank_1_consensus_gate",
            ),
            "paired_outcomes": paired_outcomes("ocr"),
        },
        "label_audit": {
            "human_image_review_status": "pending",
            "priority_counts": audit[
                "audit_priority"
            ].value_counts().to_dict(),
            "provisional_training_eligible_cases": int(
                audit["provisional_model_training_eligibility"].sum()
            ),
            "source_image_references_available": int(
                audit["source_image_reference_available"].sum()
            ),
        },
        "abstention": {
            "threshold": abstention_policy["threshold"],
            "metrics": abstention_metrics.to_dict("records"),
            "semantics": abstention_policy["output_semantics"],
        },
        "learned_ranker": {
            "status": "advisory_only",
            "metrics": learned_metrics.to_dict("records"),
        },
        "runtime_validation": {
            "executed": not args.skip_runtime_validation,
            "cases": len(runtime_validation),
            "rank_matches": (
                int(runtime_validation["rank_match"].sum())
                if len(runtime_validation)
                else None
            ),
            "top_1_matches": (
                int(runtime_validation["top_1_match"].sum())
                if len(runtime_validation)
                else None
            ),
            "top_20_matches": (
                int(runtime_validation["top_20_match"].sum())
                if len(runtime_validation)
                else None
            ),
        },
    }
    if "synthetic" in replay_results:
        summary["synthetic"] = {
            "algorithm_5": selected_metric(
                "synthetic",
                "algorithm_5_reference",
            ),
            "algorithm_6": selected_metric(
                "synthetic",
                "algorithm_6_full",
            ),
            "changed_rows": len(replay_changes["synthetic"]),
            "rank_1_promotions": int(
                replay_results["synthetic"][
                    "algorithm_6_promoted"
                ].sum()
            ),
            "external_top_20_slots": int(
                replay_results["synthetic"][
                    "algorithm_6_external_slot_used"
                ].sum()
            ),
            "exploratory_rank_1_gate": selected_metric(
                "synthetic",
                "exploratory_with_rank_1_consensus_gate",
            ),
            "paired_outcomes": paired_outcomes("synthetic"),
        }
    summary_path = args.results_dir / "algorithm_6_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {summary_path}")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

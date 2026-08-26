#!/usr/bin/env python3
"""Validate clean-core results and generate the report's compact table data."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import random
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from rapidfuzz import process
from rapidfuzz.distance import DamerauLevenshtein, Levenshtein, OSA
from scipy.stats import binomtest


BENCHMARK_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BENCHMARK_ROOT.parent
DEFAULT_CASES = BENCHMARK_ROOT / "data/05_synthetic_clean_core/test_cases.csv"
DEFAULT_OLD_CASES = PROJECT_ROOT / "benchmark_02_synthetic/data/test_cases.csv"
DEFAULT_OLD_FAIR_METRICS = (
    BENCHMARK_ROOT / "results/04_meeting_10/synthetic_fairness_by_algorithm.csv"
)
DEFAULT_RESULTS = BENCHMARK_ROOT / "results/05_synthetic_clean_core"
DEFAULT_ARTIFACTS = BENCHMARK_ROOT / "artifacts/05_synthetic_clean_core"
CATALOG_PATH = PROJECT_ROOT / "app/data/catalog.json"
ALGORITHM_5_PATH = (
    PROJECT_ROOT
    / "benchmark_01_legacy/master_algorithms/algorithm_5_commercial_name_search.py"
)
ALGORITHM_ORDER = (
    "baseline_exact_prefix",
    "baseline_levenshtein",
    "baseline_jaro_winkler",
    "baseline_char_3gram_tfidf",
    "baseline_rapidfuzz_token_ratio",
    "baseline_phonetic",
    "algorithm_1_current_app",
    "algorithm_2_external_fast",
    "algorithm_3_rank_fusion",
    "algorithm_4_family_rescue",
    "algorithm_5_evidence_rescue",
)
A4 = "algorithm_4_family_rescue"
A5 = "algorithm_5_evidence_rescue"
ALGORITHM_NAMES = {
    "baseline_exact_prefix": "Exact or prefix match",
    "baseline_levenshtein": "Exhaustive Levenshtein",
    "baseline_jaro_winkler": "Jaro-Winkler",
    "baseline_char_3gram_tfidf": "Character 3-gram TF-IDF",
    "baseline_rapidfuzz_token_ratio": "RapidFuzz token ratio",
    "baseline_phonetic": "Phonetic baseline",
    "algorithm_1_current_app": "Algorithm 1, current app",
    "algorithm_2_external_fast": "Algorithm 2, external fast",
    "algorithm_3_rank_fusion": "Algorithm 3, rank fusion",
    "algorithm_4_family_rescue": "Algorithm 4, family rescue",
    "algorithm_5_evidence_rescue": "Algorithm 5, evidence-guided rescue",
}


def compact_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def shared_bigram_count(query: Any, target: Any) -> int:
    left = compact_text(query)
    right = compact_text(target)
    left_pairs = {left[index : index + 2] for index in range(max(0, len(left) - 1))}
    right_pairs = {right[index : index + 2] for index in range(max(0, len(right) - 1))}
    return len(left_pairs & right_pairs)


def shared_bigram_band(count: int) -> str:
    if count == 0:
        return "0_shared_bigrams"
    if count == 1:
        return "1_shared_bigram"
    if count <= 3:
        return "2_3_shared_bigrams"
    return "4_plus_shared_bigrams"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--old-cases", type=Path, default=DEFAULT_OLD_CASES)
    parser.add_argument("--old-fair-metrics", type=Path, default=DEFAULT_OLD_FAIR_METRICS)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument(
        "--fresh-a5-results",
        type=Path,
        help="Optional independent Algorithm 5 case-results CSV for reproducibility checks.",
    )
    return parser.parse_args()


def read_metrics(path: Path) -> pd.DataFrame:
    metrics = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    observed = set(metrics.loc[metrics["dimension"] == "overall", "algorithm"])
    if observed != set(ALGORITHM_ORDER):
        raise ValueError(f"overall algorithm coverage mismatch: {sorted(observed)}")
    return metrics


def read_results(path: Path, expected_cases: int) -> pd.DataFrame:
    if not path.exists():
        archived_path = path.with_suffix(path.suffix + ".gz")
        if archived_path.exists():
            path = archived_path
    columns = [
        "case_id",
        "algorithm",
        "algorithm_name",
        "input",
        "input_compact",
        "expected",
        "expected_family_keys",
        "clean_categories",
        "primary_category",
        "clean_error_types",
        "operation_family",
        "difficulty",
        "danger",
        "split",
        "effective_levenshtein",
        "effective_damerau",
        "query_length",
        "shared_bigrams",
        "shared_bigram_band",
        "first_relevant_rank",
        "hit_at_1",
        "hit_at_5",
        "hit_at_10",
        "hit_at_20",
        "unsafe_confident_top1",
        "needs_clarification",
        "no_result",
        "candidate_count",
        "latency_ms",
        "top_1",
        "top_5",
    ]
    data = pd.read_csv(path, usecols=columns, encoding="utf-8-sig", low_memory=False)
    expected_rows = expected_cases * len(ALGORITHM_ORDER)
    if len(data) != expected_rows:
        raise ValueError(f"expected {expected_rows:,} result rows, found {len(data):,}")
    counts = data.groupby("algorithm")["case_id"].agg(["size", "nunique"])
    if not ((counts["size"] == expected_cases) & (counts["nunique"] == expected_cases)).all():
        raise ValueError(f"result coverage mismatch:\n{counts}")
    target_lengths = data["expected"].map(lambda value: max(len(compact_text(value)), 1))
    data["normalized_distance"] = data["effective_levenshtein"] / target_lengths
    data["severity_cohort"] = np.select(
        [data["normalized_distance"] > 0.60, data["normalized_distance"] > 0.40],
        ["extreme", "high_distance"],
        default="standard",
    )
    return data


def compare_fresh_a5_results(
    recorded_a5: pd.DataFrame,
    fresh_path: Path | None,
) -> dict[str, int]:
    if fresh_path is None:
        return {}
    columns = [
        "case_id",
        "algorithm",
        "top_1",
        "first_relevant_rank",
        "hit_at_1",
        "hit_at_5",
        "hit_at_10",
        "hit_at_20",
        "candidate_count",
    ]
    fresh = pd.read_csv(
        fresh_path,
        usecols=columns,
        encoding="utf-8-sig",
        low_memory=False,
    )
    fresh = fresh[fresh["algorithm"] == A5].drop(columns="algorithm")
    comparison_columns = [column for column in columns if column not in {"case_id", "algorithm"}]
    joined = recorded_a5[["case_id", *comparison_columns]].merge(
        fresh,
        on="case_id",
        suffixes=("_recorded", "_fresh"),
        validate="one_to_one",
    )
    if len(joined) != len(recorded_a5):
        raise ValueError(
            f"fresh A5 coverage mismatch: {len(joined):,} joined rows for "
            f"{len(recorded_a5):,} recorded rows"
        )

    def mismatch_count(column: str) -> int:
        left = joined[f"{column}_recorded"].fillna("").astype(str)
        right = joined[f"{column}_fresh"].fillna("").astype(str)
        return int((left != right).sum())

    return {
        "fresh_rerun_rows": len(joined),
        "fresh_rank_mismatches": mismatch_count("first_relevant_rank"),
        "fresh_hit_flag_mismatches": sum(
            mismatch_count(column)
            for column in ("hit_at_1", "hit_at_5", "hit_at_10", "hit_at_20")
        ),
        "fresh_top_name_differences": mismatch_count("top_1"),
        "fresh_candidate_count_differences": mismatch_count("candidate_count"),
    }


def split_labels(series: pd.Series) -> pd.DataFrame:
    return series.str.split("; ").explode().rename("label").to_frame()


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        raise ValueError(f"refusing to write empty table: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def paired_comparisons(data: pd.DataFrame) -> list[dict[str, Any]]:
    reference = data[data["algorithm"] == A5].set_index("case_id")
    output = []
    for algorithm in ALGORITHM_ORDER:
        if algorithm == A5:
            continue
        other = data[data["algorithm"] == algorithm].set_index("case_id").loc[reference.index]
        row: dict[str, Any] = {
            "reference_algorithm": A5,
            "comparison_algorithm": algorithm,
            "cases": len(reference),
        }
        for cutoff in (1, 20):
            field = f"hit_at_{cutoff}"
            reference_values = reference[field].to_numpy(dtype=int)
            other_values = other[field].to_numpy(dtype=int)
            difference = reference_values - other_values
            gained = int((difference == 1).sum())
            lost = int((difference == -1).sum())
            discordant = gained + lost
            p_value = float(binomtest(min(gained, lost), discordant, 0.5).pvalue) if discordant else 1.0
            mean = float(difference.mean())
            standard_error = float(difference.std(ddof=1) / math.sqrt(len(difference)))
            row.update(
                {
                    f"delta_hit_at_{cutoff}": mean,
                    f"ci95_low_hit_at_{cutoff}": mean - 1.96 * standard_error,
                    f"ci95_high_hit_at_{cutoff}": mean + 1.96 * standard_error,
                    f"a5_only_hit_at_{cutoff}": gained,
                    f"comparison_only_hit_at_{cutoff}": lost,
                    f"mcnemar_p_hit_at_{cutoff}": p_value,
                }
            )
        output.append(row)
    return output


def category_membership_counts(cases: pd.DataFrame) -> pd.Series:
    membership = cases[["case_id", "clean_categories"]].copy()
    membership["clean_category"] = membership["clean_categories"].str.split("; ")
    return membership.explode("clean_category")["clean_category"].value_counts()


def source_category_transition(old: pd.DataFrame, cases: pd.DataFrame) -> list[dict[str, Any]]:
    clean = cases[["case_id", "original_categories"]].copy()
    clean["original_category"] = clean["original_categories"].str.split("; ")
    clean_counts = clean.explode("original_category")["original_category"].value_counts()
    old_counts = old.groupby("category").size()
    category_numbers = old.groupby("category")["category_number"].min()
    rows = []
    for category in sorted(old_counts.index, key=lambda value: int(category_numbers[value])):
        source_rows = int(old_counts[category])
        clean_pairs = int(clean_counts.get(category, 0))
        if clean_pairs == 0:
            role = "Absent from positive-retrieval core"
        elif clean_pairs < 100:
            role = "Small stress subset retained"
        else:
            role = "Core corruption retained"
        rows.append(
            {
                "original_category": category,
                "category_number": int(category_numbers[category]),
                "source_rows": source_rows,
                "clean_unique_memberships": clean_pairs,
                "membership_share_of_source": clean_pairs / source_rows,
                "clean_core_role": role,
            }
        )
    return rows


def dataset_audit(cases: pd.DataFrame, old: pd.DataFrame) -> list[dict[str, Any]]:
    source_occurrences = int(cases["source_row_count"].sum())
    return [
        {"metric": "Original generated rows", "value": len(old), "meaning": "Complete 34-category source benchmark."},
        {"metric": "Source rows represented in clean core", "value": source_occurrences, "meaning": "Rows retained before duplicate pair collapse."},
        {"metric": "Source rows outside clean core", "value": len(old) - source_occurrences, "meaning": "Behavioral, ambiguous, exact, no-match, or unsupported rows not used in this positive-retrieval denominator."},
        {"metric": "Primary clean unique pairs", "value": len(cases), "meaning": "Every row receives one vote in the headline score."},
        {"metric": "Collapsed duplicate occurrences", "value": source_occurrences - len(cases), "meaning": "Repeated query-target occurrences removed from weighting."},
        {"metric": "Unique corrupted queries", "value": cases["input_compact"].nunique(), "meaning": "No compact query is repeated."},
        {"metric": "Verified target families", "value": cases["expected"].nunique(), "meaning": "All targets resolve to the 25,066-row runtime catalog."},
        {"metric": "Clean category labels", "value": split_labels(cases["clean_categories"])["label"].nunique(), "meaning": "Membership labels; rare rows can carry more than one."},
        {"metric": "Clean error-type labels", "value": split_labels(cases["clean_error_types"])["label"].nunique(), "meaning": "Exact mutation labels after corrections."},
        {"metric": "Rows with a cleaning note", "value": int(cases["cleaning_notes"].notna().sum()), "meaning": "Rows relabelled or retained after a documented safety comparison."},
        {"metric": "Dangerous gold-closer pairs", "value": int((cases["danger"] == "DANGEROUS").sum()), "meaning": "Gold target is closer than the recorded alternative; both remain visible for safety analysis."},
    ]


def load_catalog_families() -> tuple[list[str], dict[str, str]]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    names: dict[str, str] = {}
    for record in payload["records"]:
        name = str(record.get("b") or record.get("n") or "").strip()
        key = compact_text(name)
        if key and key not in names:
            names[key] = name
    keys = sorted(names, key=lambda key: (names[key], key))
    if len(keys) != 17_476:
        raise ValueError(f"expected 17,476 catalog family keys, found {len(keys):,}")
    return keys, names


def nearest_catalog_geometry(
    rows: pd.DataFrame,
    family_keys: list[str],
    family_names: dict[str, str],
    *,
    scorer: Any,
    prefix: str,
    chunk_size: int = 1_000,
) -> pd.DataFrame:
    output: list[dict[str, Any]] = []
    for start in range(0, len(rows), chunk_size):
        chunk = rows.iloc[start : start + chunk_size]
        queries = chunk["input"].map(compact_text).tolist()
        distances = process.cdist(
            queries,
            family_keys,
            scorer=scorer,
            dtype=np.int16,
            workers=-1,
        )
        nearest_distances = distances.min(axis=1)
        expected_distances = np.array(
            [
                scorer(query, compact_text(expected))
                for query, expected in zip(queries, chunk["expected"])
            ],
            dtype=int,
        )
        top_distances = np.array(
            [
                scorer(query, compact_text(top))
                if compact_text(top)
                else 999
                for query, top in zip(queries, chunk["top_1"])
            ],
            dtype=int,
        )
        for position, case_id in enumerate(chunk["case_id"]):
            nearest = int(nearest_distances[position])
            expected = int(expected_distances[position])
            nearest_indexes = np.flatnonzero(distances[position] == nearest)
            nearest_names = sorted(
                family_names[family_keys[index]] for index in nearest_indexes
            )
            if nearest < expected:
                gold_status = "competitor_strictly_closer"
            elif len(nearest_indexes) > 1:
                gold_status = "gold_tied_nearest"
            else:
                gold_status = "gold_unique_nearest"
            top = int(top_distances[position])
            top_relation = (
                "top_closer"
                if top < expected
                else "equal_distance"
                if top == expected
                else "top_farther"
            )
            output.append(
                {
                    "case_id": case_id,
                    f"{prefix}_expected_distance": expected,
                    f"{prefix}_nearest_distance": nearest,
                    f"{prefix}_nearest_count": int(len(nearest_indexes)),
                    f"{prefix}_nearest_names": "; ".join(nearest_names[:8]),
                    f"{prefix}_closer_catalog_count": int(
                        (distances[position] < expected).sum()
                    ),
                    f"{prefix}_gold_distance_count": int(
                        (distances[position] == expected).sum()
                    ),
                    f"{prefix}_top_distance": top,
                    f"{prefix}_gold_status": gold_status,
                    f"{prefix}_top_relation": top_relation,
                }
            )
    return pd.DataFrame(output)


def load_algorithm_5() -> Any:
    module_name = "synthetic_clean_core_failure_audit_algorithm_5"
    spec = importlib.util.spec_from_file_location(module_name, ALGORITHM_5_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load Algorithm 5 from {ALGORITHM_5_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def algorithm_result_name(item: dict[str, Any]) -> str:
    return str(
        item.get("name")
        or item.get("candidate_canonical_name")
        or item.get("canonical_name")
        or item.get("commercial_name")
        or ""
    ).strip()


def inspect_unique_nearest_failures(
    failures: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    unique = failures[failures["osa_gold_status"] == "gold_unique_nearest"]
    module = load_algorithm_5()
    catalog = module.prepare_catalog()
    details: list[dict[str, Any]] = []
    for row in unique.itertuples(index=False):
        response = module.search_catalog(catalog, row.input, 20)
        results = list(response.get("results") or [])
        names = [algorithm_result_name(item) for item in results]
        recorded_top = "" if pd.isna(row.top_1) else str(row.top_1)
        expected_key = compact_text(row.expected)
        ranks = [
            rank
            for rank, name in enumerate(names, 1)
            if compact_text(name) == expected_key
        ]
        rank = ranks[0] if ranks else 999
        top = results[0] if results else {}
        expected = results[rank - 1] if rank <= 20 else {}
        details.append(
            {
                "case_id": row.case_id,
                "rerun_top_1": names[0] if names else "",
                "rerun_expected_rank": rank,
                "rerun_matches_recorded": int(
                    (names[0] if names else "") == recorded_top
                    and rank == int(row.first_relevant_rank)
                ),
                "top_score": top.get("score", np.nan),
                "expected_score": expected.get("score", np.nan),
                "score_gap": (
                    float(top["score"]) - float(expected["score"])
                    if top and expected
                    else np.nan
                ),
                "top_raw_distance": top.get("raw_edit_distance", np.nan),
                "expected_raw_distance": expected.get("raw_edit_distance", np.nan),
                "top_weighted_distance": top.get("weighted_edit_distance", np.nan),
                "expected_weighted_distance": expected.get(
                    "weighted_edit_distance", np.nan
                ),
                "top_position": top.get("positional_evidence", np.nan),
                "expected_position": expected.get("positional_evidence", np.nan),
                "top_edge": top.get("edge_evidence", np.nan),
                "expected_edge": expected.get("edge_evidence", np.nan),
                "top_source": top.get("source", ""),
                "expected_source": expected.get("source", ""),
                "top_reasons": ";".join(top.get("reasons", []) or []),
                "expected_reasons": ";".join(
                    expected.get("reasons", []) or []
                ),
            }
        )

    detail_frame = pd.DataFrame(details)
    if not detail_frame["rerun_matches_recorded"].eq(1).all():
        mismatches = detail_frame[detail_frame["rerun_matches_recorded"] != 1]
        raise ValueError(
            "Algorithm 5 unique-nearest rerun mismatch:\n"
            + mismatches[["case_id", "rerun_top_1", "rerun_expected_rank"]].to_string(
                index=False
            )
        )

    rng = random.Random(20260722)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    distance_mismatches = 0
    for _ in range(10_000):
        left = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 18)))
        right = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 18)))
        if module.damerau(left, right, weighted=False) != OSA.distance(left, right):
            distance_mismatches += 1
    return detail_frame, {
        "rerun_cases": len(detail_frame),
        "rerun_mismatches": int((detail_frame["rerun_matches_recorded"] != 1).sum()),
        "osa_equivalence_pairs": 10_000,
        "osa_equivalence_mismatches": distance_mismatches,
    }


def classify_failure_root(row: pd.Series) -> str:
    if row["osa_gold_status"] == "competitor_strictly_closer":
        return "another_catalog_family_is_closer"
    if row["osa_gold_status"] == "gold_tied_nearest":
        return "gold_tied_with_catalog_neighbors"
    if not int(row["hit_at_20"]):
        return (
            "unique_nearest_no_result"
            if int(row["no_result"])
            else "unique_nearest_outside_top_20"
        )
    if float(row["score_gap"]) < 0:
        return "unique_nearest_bounded_correction_override"
    return "unique_nearest_combined_score_inversion"


def build_failure_audit(
    data: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, str]]:
    family_keys, family_names = load_catalog_families()
    a5 = data[data["algorithm"] == A5].copy()
    osa = nearest_catalog_geometry(
        a5,
        family_keys,
        family_names,
        scorer=OSA.distance,
        prefix="osa",
    )
    a5 = a5.merge(osa, on="case_id", validate="one_to_one")
    failures = a5[a5["hit_at_1"] == 0].copy()
    levenshtein = nearest_catalog_geometry(
        failures,
        family_keys,
        family_names,
        scorer=Levenshtein.distance,
        prefix="levenshtein",
    )
    failures = failures.merge(levenshtein, on="case_id", validate="one_to_one")
    details, rerun_audit = inspect_unique_nearest_failures(failures)
    failures = failures.merge(details, on="case_id", how="left", validate="one_to_one")
    failures["failure_level"] = np.where(
        failures["hit_at_20"] == 1, "ranking", "retrieval"
    )

    other_algorithms = [algorithm for algorithm in ALGORITHM_ORDER if algorithm != A5]
    h1 = data.pivot(index="case_id", columns="algorithm", values="hit_at_1")
    h20 = data.pivot(index="case_id", columns="algorithm", values="hit_at_20")
    failure_h1 = h1.loc[failures["case_id"], other_algorithms]
    failure_h20 = h20.loc[failures["case_id"], other_algorithms]
    failures["other_h1_rescue_count"] = failure_h1.sum(axis=1).to_numpy(dtype=int)
    failures["other_h20_rescue_count"] = failure_h20.sum(axis=1).to_numpy(dtype=int)
    failures["h1_rescued_by"] = [
        "; ".join(
            ALGORITHM_NAMES[algorithm]
            for algorithm in other_algorithms
            if int(failure_h1.loc[case_id, algorithm])
        )
        for case_id in failures["case_id"]
    ]
    failures["h20_rescued_by"] = [
        "; ".join(
            ALGORITHM_NAMES[algorithm]
            for algorithm in other_algorithms
            if int(failure_h20.loc[case_id, algorithm])
        )
        for case_id in failures["case_id"]
    ]
    failures["failure_root"] = failures.apply(classify_failure_root, axis=1)

    expected_levenshtein = np.array(
        [
            Levenshtein.distance(compact_text(query), compact_text(expected))
            for query, expected in zip(a5["input"], a5["expected"])
        ]
    )
    expected_damerau = np.array(
        [
            DamerauLevenshtein.distance(
                compact_text(query), compact_text(expected)
            )
            for query, expected in zip(a5["input"], a5["expected"])
        ]
    )
    expected_osa = a5["osa_expected_distance"].to_numpy(dtype=int)
    calculated_h1 = np.array(
        [
            int(
                compact_text(top)
                in {
                    compact_text(key)
                    for key in str(expected_keys).split(";")
                    if compact_text(key)
                }
            )
            for top, expected_keys in zip(a5["top_1"], a5["expected_family_keys"])
        ]
    )
    catalog_keys = set(family_keys)
    exact_other_catalog = sum(
        compact_text(query) in catalog_keys
        and compact_text(query) != compact_text(expected)
        for query, expected in zip(a5["input"], a5["expected"])
    )
    validity = {
        **rerun_audit,
        "case_rows": len(a5),
        "unique_case_ids": int(a5["case_id"].nunique()),
        "hit_at_1_flag_mismatches": int(
            (calculated_h1 != a5["hit_at_1"].to_numpy(dtype=int)).sum()
        ),
        "rank_flag_mismatches": int(
            (
                (a5["first_relevant_rank"].to_numpy(dtype=int) <= 20)
                != a5["hit_at_20"].to_numpy(dtype=bool)
            ).sum()
        ),
        "levenshtein_distance_mismatches": int(
            (
                expected_levenshtein
                != a5["effective_levenshtein"].to_numpy(dtype=int)
            ).sum()
        ),
        "damerau_distance_mismatches": int(
            (
                expected_damerau
                != a5["effective_damerau"].to_numpy(dtype=int)
            ).sum()
        ),
        "stored_damerau_osa_differences": int(
            (expected_osa != a5["effective_damerau"].to_numpy(dtype=int)).sum()
        ),
        "exact_other_catalog_queries": int(exact_other_catalog),
    }
    return a5, failures, validity, family_names


def failure_analysis_tables(
    data: pd.DataFrame,
    a5: pd.DataFrame,
    failures: pd.DataFrame,
    validity: dict[str, Any],
) -> dict[str, pd.DataFrame]:
    ranks = a5["first_relevant_rank"].to_numpy(dtype=int)
    rank_groups = [
        ("Correct at rank 1", ranks == 1),
        ("Expected at ranks 2--5", (ranks >= 2) & (ranks <= 5)),
        ("Expected at ranks 6--10", (ranks >= 6) & (ranks <= 10)),
        ("Expected at ranks 11--20", (ranks >= 11) & (ranks <= 20)),
        ("Expected outside top 20", ranks > 20),
    ]
    rank_breakdown = pd.DataFrame(
        [
            {
                "group": label,
                "cases": int(mask.sum()),
                "share": float(mask.mean()),
            }
            for label, mask in rank_groups
        ]
    )

    geometry_rows = []
    for distance_name, status_field in (
        ("OSA, used by A5", "osa_gold_status"),
        ("Levenshtein, report metric", "levenshtein_gold_status"),
    ):
        source = a5 if status_field == "osa_gold_status" else failures
        for status, group in source.groupby(status_field):
            geometry_rows.append(
                {
                    "distance": distance_name,
                    "gold_status": status,
                    "cases": len(group),
                    "share": len(group) / len(source),
                    "hit_at_1": group["hit_at_1"].mean(),
                    "hit_at_20": group["hit_at_20"].mean(),
                }
            )
    geometry = pd.DataFrame(geometry_rows)

    root_rows = []
    for status, group in failures.groupby("osa_gold_status"):
        root_rows.append(
            {
                "gold_status": status,
                "cases": len(group),
                "share_of_a5_h1_failures": len(group) / len(failures),
                "ranking_failures": int(group["hit_at_20"].sum()),
                "retrieval_failures": int((1 - group["hit_at_20"]).sum()),
            }
        )
    root_causes = pd.DataFrame(root_rows)

    unique = failures[failures["osa_gold_status"] == "gold_unique_nearest"]
    unique_ranking = unique[unique["hit_at_20"] == 1]
    unique_retrieval = unique[unique["hit_at_20"] == 0]
    unique_mechanisms = pd.DataFrame(
        [
            {
                "group": "Combined-score inversion",
                "cases": int((unique_ranking["score_gap"] >= 0).sum()),
                "meaning": "Expected family is present, uniquely nearest, but has a lower combined score.",
            },
            {
                "group": "Bounded correction override",
                "cases": int((unique_ranking["score_gap"] < 0).sum()),
                "meaning": "A correction moved a lower-score family above the uniquely nearest target.",
            },
            {
                "group": "No candidates returned",
                "cases": int(unique_retrieval["no_result"].sum()),
                "meaning": "Candidate generation returned an empty list.",
            },
            {
                "group": "Target outside top 20",
                "cases": int((1 - unique_retrieval["no_result"]).sum()),
                "meaning": "Other candidates were returned, but the uniquely nearest target was absent.",
            },
        ]
    )

    rescue_rows = []
    for algorithm in ALGORITHM_ORDER:
        if algorithm == A5:
            continue
        algorithm_rows = data[data["algorithm"] == algorithm].set_index("case_id")
        selected = algorithm_rows.loc[failures["case_id"]]
        rescue_rows.append(
            {
                "algorithm": algorithm,
                "algorithm_name": ALGORITHM_NAMES[algorithm],
                "hit_at_1_rescues": int(selected["hit_at_1"].sum()),
                "hit_at_20_retrievals": int(selected["hit_at_20"].sum()),
            }
        )
    rescue = pd.DataFrame(rescue_rows).sort_values(
        ["hit_at_1_rescues", "hit_at_20_retrievals"], ascending=False
    )

    top_distances = a5["osa_top_distance"]
    fallback_rules = (
        ("Any unique nearest family", pd.Series(True, index=a5.index)),
        ("Only when A5 returns no result", a5["no_result"].eq(1)),
        ("Only queries of at most four characters", a5["query_length"].le(4)),
        (
            "At most four characters and at most one bigram",
            a5["query_length"].le(4) & a5["shared_bigrams"].le(1),
        ),
    )
    fallback_rows = []
    baseline_correct = int(a5["hit_at_1"].sum())
    for rule, extra_condition in fallback_rules:
        trigger = (
            a5["osa_nearest_count"].eq(1)
            & top_distances.gt(a5["osa_nearest_distance"])
            & extra_condition
        )
        gains = trigger & a5["osa_gold_status"].eq("gold_unique_nearest") & a5[
            "hit_at_1"
        ].eq(0)
        harms = (
            trigger
            & a5["osa_gold_status"].eq("competitor_strictly_closer")
            & a5["hit_at_1"].eq(1)
        )
        net = int(gains.sum() - harms.sum())
        fallback_rows.append(
            {
                "rule": rule,
                "changed_cases": int(trigger.sum()),
                "corrected_failures": int(gains.sum()),
                "broken_successes": int(harms.sum()),
                "net_correct": net,
                "counterfactual_hit_at_1": (baseline_correct + net) / len(a5),
            }
        )
    fallback = pd.DataFrame(fallback_rows)

    family = a5.groupby("expected").agg(
        cases=("case_id", "size"),
        hit_at_1=("hit_at_1", "mean"),
        hit_at_20=("hit_at_20", "mean"),
        h1_failures=("hit_at_1", lambda values: int((1 - values).sum())),
        h20_failures=("hit_at_20", lambda values: int((1 - values).sum())),
    )
    family_summary = pd.DataFrame(
        [
            {
                "denominator": "Pair micro-average",
                "units": len(a5),
                "hit_at_1": a5["hit_at_1"].mean(),
                "hit_at_20": a5["hit_at_20"].mean(),
                "meaning": "Every distinct query-target pair receives one vote.",
            },
            {
                "denominator": "Family macro-average",
                "units": len(family),
                "hit_at_1": family["hit_at_1"].mean(),
                "hit_at_20": family["hit_at_20"].mean(),
                "meaning": "Every verified family receives one vote after averaging its cases.",
            },
        ]
    )
    family_concentration = pd.DataFrame(
        [
            {
                "metric": "Families with at least one Hit@1 failure",
                "value": int((family["h1_failures"] > 0).sum()),
                "share": float((family["h1_failures"] > 0).mean()),
            },
            {
                "metric": "Families with at least one Hit@20 failure",
                "value": int((family["h20_failures"] > 0).sum()),
                "share": float((family["h20_failures"] > 0).mean()),
            },
            {
                "metric": "Top ten families' share of Hit@1 failures",
                "value": int(family.nlargest(10, "h1_failures")["h1_failures"].sum()),
                "share": float(
                    family.nlargest(10, "h1_failures")["h1_failures"].sum()
                    / family["h1_failures"].sum()
                ),
            },
        ]
    )

    validity_rows = pd.DataFrame(
        [
            {"check": key, "value": value}
            for key, value in validity.items()
        ]
    )
    return {
        "rank_breakdown": rank_breakdown,
        "geometry": geometry,
        "root_causes": root_causes,
        "unique_mechanisms": unique_mechanisms,
        "rescue": rescue,
        "fallback": fallback,
        "family_summary": family_summary,
        "family_concentration": family_concentration,
        "validity": validity_rows,
    }


MANUAL_FAILURE_REVIEWS = {
    "SC-344B95443D7F97": (
        "Unique nearest, ranking",
        "TRENDO is the only OSA-nearest family at distance 2, but rescue-only evidence leaves it 0.0114 score below TERNICOL.",
    ),
    "SC-413102D124577B": (
        "Unique nearest, ranking",
        "SOLVIN N is uniquely nearest at distance 1, but the shorter SOLVIN family receives a much larger family score and pushes it to rank 20.",
    ),
    "SC-E7B76E61A5CA48": (
        "Unique nearest, correction",
        "MONGER has the higher score, 1.3803 versus 0.3964, but a variant-head correction promotes RINGER MUP.",
    ),
    "SC-217002B847CEC7": (
        "Unique nearest, no result",
        "COQ is the only nearest family at distance 1; the three-character query with zero shared bigrams returns no candidates.",
    ),
    "SC-814364A3430496": (
        "Unique nearest, retrieval",
        "BIOFRAICHE is uniquely nearest under OSA at distance 4, but severe mixed corruption keeps it outside the top 20.",
    ),
    "SC-18D5473EEA2C40": (
        "Nearest-distance tie",
        "COBAL and CONIL are both one edit from CONAL, so raw distance cannot decide; A5 ranks COBAL third.",
    ),
    "SC-6B69113BC799B0": (
        "Nearest-distance tie",
        "GINKO shares distance 3 with AM GINKO, CIOGINO, and GINGINORM; A5 puts GINGINORM first and GINKO second.",
    ),
    "SC-124CE7F15A2244": (
        "Nearest-distance tie",
        "APIXOL is one of fourteen families at distance 3, so a single required winner is not supported by edit distance.",
    ),
    "SC-04E415D8DC15C2": (
        "Another family closer",
        "NIFUNAL is distance 2 while source target REMINYL is distance 3; A5's first result is the literal nearest family.",
    ),
    "SC-F133FC19C7B698": (
        "Another family closer",
        "FLAX SEED OIL is distance 2 while BLACK SEED OIL is distance 3, making the generated phonetic corruption a real catalog near-collision.",
    ),
    "SC-08469B02B2E73A": (
        "Another family closer",
        "GORY is distance 1 while GOSAY is distance 2; the wrong first result follows the stronger visible spelling.",
    ),
    "SC-1DE8168DA84436": (
        "Severe unrecoverable row",
        "NATEAD is OSA distance 4 and many catalog families are closer; no evaluated system retrieves it within the top 20.",
    ),
}


def manual_failure_review(failures: pd.DataFrame) -> pd.DataFrame:
    indexed = failures.set_index("case_id")
    remaining_ids = [
        case_id for case_id in MANUAL_FAILURE_REVIEWS if case_id in indexed.index
    ]
    selected = indexed.loc[remaining_ids].copy()
    selected["review_class"] = [
        MANUAL_FAILURE_REVIEWS[case_id][0] for case_id in selected.index
    ]
    selected["manual_review"] = [
        MANUAL_FAILURE_REVIEWS[case_id][1] for case_id in selected.index
    ]
    return selected.reset_index()


def write_failure_summary(
    path: Path,
    tables: dict[str, pd.DataFrame],
) -> None:
    rows: list[dict[str, Any]] = []
    for table_name, table in tables.items():
        for row in table.to_dict(orient="records"):
            rows.append({"analysis_table": table_name, **row})
    write_csv(path, rows)


def equal_distance_rows(data: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summaries = []
    examples = []
    for algorithm in ALGORITHM_ORDER:
        rows = data[(data["algorithm"] == algorithm) & (data["hit_at_1"] == 0)].copy()
        rows = rows[rows["top_1"].fillna("") != ""]
        rows["top_distance"] = [
            Levenshtein.distance(compact_text(query), compact_text(top))
            for query, top in zip(rows["input_compact"], rows["top_1"])
        ]
        tied = rows[rows["top_distance"] == rows["effective_levenshtein"]]
        rank_only = tied[tied["hit_at_20"] == 1]
        retrieval = tied[tied["hit_at_20"] == 0]
        summaries.append(
            {
                "algorithm": algorithm,
                "wrong_top1_with_result": len(rows),
                "equal_distance_wrong_top1": len(tied),
                "equal_distance_rank_only": len(rank_only),
                "equal_distance_retrieval_miss": len(retrieval),
                "equal_distance_share_of_wrong_top1": len(tied) / len(rows) if len(rows) else 0.0,
            }
        )
        if algorithm == A5:
            candidates = tied.sort_values(
                ["effective_levenshtein", "clean_categories", "case_id"]
            )
            used_categories: set[str] = set()
            for row in candidates.itertuples(index=False):
                category = str(row.primary_category)
                if category in used_categories and len(examples) < 6:
                    continue
                used_categories.add(category)
                examples.append(
                    {
                        "case_id": row.case_id,
                        "input": row.input,
                        "expected": row.expected,
                        "a5_top_1": row.top_1,
                        "equal_edit_distance": int(row.effective_levenshtein),
                        "expected_rank": int(row.first_relevant_rank),
                        "clean_category": row.primary_category,
                        "failure_level": "ranking" if row.hit_at_20 else "retrieval",
                    }
                )
                if len(examples) == 10:
                    break
    return summaries, examples


def select_failure_examples(data: pd.DataFrame) -> list[dict[str, Any]]:
    output = []
    for algorithm in ALGORITHM_ORDER:
        rows = data[data["algorithm"] == algorithm]
        for failure_type, mask in (
            ("ranking", (rows["hit_at_1"] == 0) & (rows["hit_at_20"] == 1)),
            ("retrieval", rows["hit_at_20"] == 0),
        ):
            eligible = rows[mask & rows["input"].str.len().between(5, 16)].copy()
            if eligible.empty:
                eligible = rows[mask].copy()
            if eligible.empty:
                continue
            eligible["preferred"] = (
                eligible["effective_levenshtein"]
                - (1 if failure_type == "ranking" else 4)
            ).abs()
            row = eligible.sort_values(
                ["preferred", "primary_category", "case_id"]
            ).iloc[0]
            output.append(
                {
                    "algorithm": algorithm,
                    "failure_type": failure_type,
                    "case_id": row["case_id"],
                    "input": row["input"],
                    "expected": row["expected"],
                    "top_1": row["top_1"],
                    "expected_rank": int(row["first_relevant_rank"]),
                    "effective_levenshtein": int(row["effective_levenshtein"]),
                    "clean_category": row["primary_category"],
                }
            )
    return output


def select_a5_gain_examples(data: pd.DataFrame) -> list[dict[str, Any]]:
    a5 = data[data["algorithm"] == A5].set_index("case_id")
    output = []
    used_categories: set[str] = set()
    for algorithm in ALGORITHM_ORDER:
        if algorithm == A5:
            continue
        other = data[data["algorithm"] == algorithm].set_index("case_id").loc[a5.index]
        keys = a5.index[(a5["hit_at_1"] == 1) & (other["hit_at_1"] == 0)]
        candidates = a5.loc[keys].sort_values(
            ["effective_levenshtein", "primary_category", "case_id"],
            ascending=[False, True, True],
        )
        if candidates.empty:
            continue
        novel = candidates[~candidates["primary_category"].isin(used_categories)]
        row = novel.iloc[0] if not novel.empty else candidates.iloc[0]
        used_categories.add(str(row["primary_category"]))
        output.append(
            {
                "comparison_algorithm": algorithm,
                "case_id": row.name,
                "input": row["input"],
                "expected": row["expected"],
                "a5_top_1": row["top_1"],
                "comparison_top_1": other.loc[row.name, "top_1"],
                "comparison_rank": int(other.loc[row.name, "first_relevant_rank"]),
                "effective_levenshtein": int(row["effective_levenshtein"]),
                "clean_category": row["primary_category"],
            }
        )
    return output


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def tex_escape(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value)
    replacements = (
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    )
    for source, target in replacements:
        text = text.replace(source, target)
    return text


def human_label(value: Any) -> str:
    text = str(value).replace("_", " ").replace("plus", "+").title()
    for source, target in (
        ("Ocr", "OCR"),
        ("Tfidf", "TF-IDF"),
        ("Ed1", "ED1"),
        ("Damerau", "Damerau"),
    ):
        text = text.replace(source, target)
    return tex_escape(text)


def percent(value: Any, decimals: int = 2) -> str:
    if pd.isna(value):
        return "--"
    return f"{100 * float(value):.{decimals}f}\\%"


def integer(value: Any) -> str:
    if pd.isna(value):
        return "--"
    return f"{int(value):,}"


def bold(value: str, condition: bool) -> str:
    return rf"\textbf{{{value}}}" if condition else value


def p_value(value: Any) -> str:
    number = float(value)
    if number < 0.0001:
        exponent = int(math.floor(math.log10(number))) if number > 0 else -999
        coefficient = number / (10**exponent) if number > 0 else 0
        return rf"${coefficient:.2f}\times10^{{{exponent}}}$" if number > 0 else "$<10^{-300}$"
    return f"{number:.4f}"


def write_macro(handle: Any, name: str, body: str) -> None:
    handle.write(rf"\newcommand{{\{name}}}{{%" + "\n")
    handle.write(body.rstrip() + "\n")
    handle.write("}\n\n")


def metric_lookup(metrics: pd.DataFrame, algorithm: str, dimension: str, group: str) -> pd.Series:
    selected = metrics[
        (metrics["algorithm"] == algorithm)
        & (metrics["dimension"] == dimension)
        & (metrics["group"].astype(str) == str(group))
    ]
    if selected.empty:
        return pd.Series(
            {
                "cases": 0,
                "hit_at_1": np.nan,
                "hit_at_5": np.nan,
                "hit_at_10": np.nan,
                "hit_at_20": np.nan,
                "mrr_at_20": np.nan,
                "unsafe_confident_top1_rate": np.nan,
                "failure_count": 0,
                "failure_rate": np.nan,
                "failure_share": np.nan,
            }
        )
    if len(selected) != 1:
        raise ValueError(f"metric lookup expected one row: {algorithm}/{dimension}/{group}")
    return selected.iloc[0]


def latex_rows(rows: Iterable[Iterable[Any]]) -> str:
    return "\n".join(" & ".join(str(cell) for cell in row) + r" \\" for row in rows)


def build_report_tables(
    path: Path,
    cases: pd.DataFrame,
    old: pd.DataFrame,
    old_fair_metrics: pd.DataFrame,
    metrics: pd.DataFrame,
    report_data: pd.DataFrame,
    audit: list[dict[str, Any]],
    transition: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
    ties: list[dict[str, Any]],
    tie_examples: list[dict[str, Any]],
    failure_examples: list[dict[str, Any]],
    gain_examples: list[dict[str, Any]],
    failure_tables: dict[str, pd.DataFrame],
    a5_audit: pd.DataFrame,
    failure_audit: pd.DataFrame,
    manual_review: pd.DataFrame,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metrics = metrics.copy()
    metrics["group"] = metrics["group"].astype(str)
    overall = metrics[metrics["dimension"] == "overall"].set_index("algorithm")
    a5 = overall.loc[A5]
    source_occurrences = int(cases["source_row_count"].sum())
    best_h1_algorithm = str(overall["hit_at_1"].idxmax())
    best_h20_algorithm = str(overall["hit_at_20"].idxmax())
    a5_rows = a5_audit
    a5_h1_failures = a5_rows[a5_rows["hit_at_1"] == 0]
    a5_extreme = report_data[
        (report_data["algorithm"] == A5) & (report_data["severity_cohort"] == "extreme")
    ]
    a5_category_metrics = metrics[
        (metrics["algorithm"] == A5) & (metrics["dimension"] == "clean_category")
    ].copy()
    a5_category_metrics["h1_failure_count"] = np.rint(
        a5_category_metrics["cases"] * (1 - a5_category_metrics["hit_at_1"])
    ).astype(int)
    a5_category_metrics["h1_failure_rate"] = 1 - a5_category_metrics["hit_at_1"]
    a5_category_metrics["h1_failure_share"] = (
        a5_category_metrics["h1_failure_count"] / len(a5_h1_failures)
        if len(a5_h1_failures)
        else 0.0
    )
    a5_category_metrics = a5_category_metrics.sort_values(
        ["h1_failure_count", "cases"], ascending=False
    )
    worst_category = a5_category_metrics.iloc[0]
    unique_osa = a5_rows[a5_rows["osa_gold_status"] == "gold_unique_nearest"]
    rank_breakdown = failure_tables["rank_breakdown"]
    root_causes = failure_tables["root_causes"]
    family_summary = failure_tables["family_summary"]
    family_concentration = failure_tables["family_concentration"]
    unique_mechanisms = failure_tables["unique_mechanisms"].set_index("group")
    fallback = failure_tables["fallback"].set_index("rule")
    all_system_misses = failure_audit[
        (failure_audit["hit_at_20"] == 0)
        & (failure_audit["other_h20_rescue_count"] == 0)
    ]

    with path.open("w", encoding="utf-8") as handle:
        scalar_macros = {
            "DatasetCases": integer(len(cases)),
            "TargetFamilies": integer(cases["expected"].nunique()),
            "RepresentedSourceRows": integer(source_occurrences),
            "RemovedSourceRows": integer(len(old) - source_occurrences),
            "CollapsedOccurrences": integer(source_occurrences - len(cases)),
            "ErrorTypeLabels": integer(split_labels(cases["clean_error_types"])["label"].nunique()),
            "DangerCases": integer((cases["danger"] == "DANGEROUS").sum()),
            "GeneratorExtremeCases": integer((cases["difficulty"] == "EXTREME").sum()),
            "AFiveHOne": percent(a5["hit_at_1"], 4),
            "AFiveHTwenty": percent(a5["hit_at_20"], 4),
            "BestHOneSystem": tex_escape(ALGORITHM_NAMES[best_h1_algorithm]),
            "BestHOneScore": percent(overall.loc[best_h1_algorithm, "hit_at_1"], 4),
            "BestHTwentySystem": tex_escape(ALGORITHM_NAMES[best_h20_algorithm]),
            "BestHTwentyScore": percent(overall.loc[best_h20_algorithm, "hit_at_20"], 4),
            "AFiveVsLevenHOne": f"{100 * (a5['hit_at_1'] - overall.loc['baseline_levenshtein', 'hit_at_1']):+.4f}\\pp",
            "AFiveVsLevenHTwenty": f"{100 * (a5['hit_at_20'] - overall.loc['baseline_levenshtein', 'hit_at_20']):+.4f}\\pp",
            "ExtremeCases": integer(len(a5_extreme)),
            "AFiveExtremeHOne": percent(a5_extreme["hit_at_1"].mean(), 2),
            "AFiveExtremeHTwenty": percent(a5_extreme["hit_at_20"].mean(), 2),
            "AFiveZeroBigramHOne": percent(
                metric_lookup(metrics, A5, "shared_bigram_band", "0_shared_bigrams")["hit_at_1"],
                2,
            ),
            "AFiveWorstCategory": human_label(worst_category["group"]),
            "AFiveWorstCategoryMisses": integer(worst_category["h1_failure_count"]),
            "AFiveCorrectAtOne": integer(a5_rows["hit_at_1"].sum()),
            "AFiveHOneFailures": integer(len(a5_h1_failures)),
            "AFiveHOneFailureRate": percent(len(a5_h1_failures) / len(a5_rows), 4),
            "AFiveRankingFailures": integer(
                ((a5_rows["hit_at_1"] == 0) & (a5_rows["hit_at_20"] == 1)).sum()
            ),
            "AFiveRetrievalFailures": integer((a5_rows["hit_at_20"] == 0).sum()),
            "AFiveNoResults": integer(a5_rows["no_result"].sum()),
            "UniqueOSACases": integer(len(unique_osa)),
            "UniqueOSAHOne": percent(unique_osa["hit_at_1"].mean(), 4),
            "UniqueOSAFailures": integer((unique_osa["hit_at_1"] == 0).sum()),
            "NonUniqueOSAFailures": integer(
                len(a5_h1_failures) - (unique_osa["hit_at_1"] == 0).sum()
            ),
            "FailureDistanceLabelDifferences": integer(
                (
                    failure_audit["levenshtein_gold_status"]
                    != failure_audit["osa_gold_status"]
                ).sum()
            ),
            "UniqueScoreInversions": integer(
                unique_mechanisms.loc["Combined-score inversion", "cases"]
            ),
            "UniqueCorrectionOverrides": integer(
                unique_mechanisms.loc["Bounded correction override", "cases"]
            ),
            "UniqueRankingFailures": integer(
                unique_mechanisms.loc["Combined-score inversion", "cases"]
                + unique_mechanisms.loc["Bounded correction override", "cases"]
            ),
            "UniqueRetrievalFailures": integer(
                unique_mechanisms.loc["No candidates returned", "cases"]
                + unique_mechanisms.loc["Target outside top 20", "cases"]
            ),
            "AllSystemMissCount": integer(len(all_system_misses)),
            "FallbackAnyChanged": integer(
                fallback.loc["Any unique nearest family", "changed_cases"]
            ),
            "FallbackAnyFixed": integer(
                fallback.loc["Any unique nearest family", "corrected_failures"]
            ),
            "FallbackAnyBroken": integer(
                fallback.loc["Any unique nearest family", "broken_successes"]
            ),
            "FallbackAnyNet": f"{int(fallback.loc['Any unique nearest family', 'net_correct']):+d}",
            "FallbackNoResultFixed": integer(
                fallback.loc["Only when A5 returns no result", "corrected_failures"]
            ),
            "FallbackNoResultBroken": integer(
                fallback.loc["Only when A5 returns no result", "broken_successes"]
            ),
            "ManualReviewCount": integer(len(manual_review)),
            "FailureFamilies": integer(family_concentration.iloc[0]["value"]),
            "TopTenFailureShare": percent(family_concentration.iloc[2]["share"], 2),
            "FamilyMacroHOne": percent(family_summary.iloc[1]["hit_at_1"], 4),
            "FamilyMacroHTwenty": percent(family_summary.iloc[1]["hit_at_20"], 4),
        }
        for name, value in scalar_macros.items():
            handle.write(rf"\newcommand{{\{name}}}{{{value}}}" + "\n")
        handle.write("\n")

        audit_rows = [
            (tex_escape(row["metric"]), integer(row["value"]), tex_escape(row["meaning"]))
            for row in audit
        ]
        write_macro(handle, "DatasetAuditRows", latex_rows(audit_rows))

        transition_rows = [
            (
                f"{row['category_number']}. {human_label(row['original_category'])}",
                integer(row["source_rows"]),
                integer(row["clean_unique_memberships"]),
                tex_escape(row["clean_core_role"]),
            )
            for row in transition
        ]
        write_macro(handle, "SourceTransitionRows", latex_rows(transition_rows))

        old_fair = old_fair_metrics[
            old_fair_metrics["denominator"] == "fair_collision_excluded"
        ].set_index("algorithm")
        fair_transition_rows = []
        for algorithm in (
            "algorithm_1_current_app",
            "algorithm_2_external_fast",
            "algorithm_3_rank_fusion",
            "algorithm_4_family_rescue",
        ):
            previous = old_fair.loc[algorithm]
            current = overall.loc[algorithm]
            fair_transition_rows.append(
                (
                    tex_escape(ALGORITHM_NAMES[algorithm]),
                    percent(previous["hit_at_1"], 4),
                    percent(current["hit_at_1"], 4),
                    f"{100 * (current['hit_at_1'] - previous['hit_at_1']):+.4f}\\pp",
                    percent(previous["hit_at_20"], 4),
                    percent(current["hit_at_20"], 4),
                    f"{100 * (current['hit_at_20'] - previous['hit_at_20']):+.4f}\\pp",
                )
            )
        write_macro(handle, "FairTransitionRows", latex_rows(fair_transition_rows))

        notes = cases["cleaning_notes"].fillna("No relabelling needed").value_counts()
        note_meanings = {
            "No relabelling needed": "Original label agreed with the observed final mutation.",
            "combined-operation case relabelled by final effective Damerau distance": "The final string, rather than the planned chain length, sets the clean category.",
            "declared subtype corrected from 3 to 2 actual vowel changes": "Two vowels changed even though the generator subtype said three.",
            "declared subtype corrected from 3 to 1 actual vowel changes": "One vowel changed even though the generator subtype said three.",
            "declared subtype corrected from 2 to 1 actual vowel changes": "One vowel changed even though the generator subtype said two.",
            "gold distance 1; closest competitor distance 2": "The dangerous pair stays scoreable because the gold family is strictly closer.",
        }
        cleaning_rows = []
        for note, count in notes.items():
            if len(cleaning_rows) == 8:
                break
            cleaning_rows.append(
                (
                    tex_escape(note),
                    integer(count),
                    percent(count / len(cases), 2),
                    tex_escape(note_meanings.get(note, "Several documented corrections apply to the same row.")),
                )
            )
        write_macro(handle, "CleaningNoteRows", latex_rows(cleaning_rows))

        composition_specs = (
            ("Effective Levenshtein", "effective_levenshtein", "Ordinary insertion, deletion, or replacement count."),
            ("Effective Damerau", "effective_damerau", "Adjacent transposition counts as one edit."),
            ("Difficulty", "difficulty", "Generator-assigned challenge level."),
            ("Danger", "danger", "Safety label for a close named competitor."),
            ("Shared bigrams", "shared_bigram_band", "Adjacent two-character anchors retained in the target."),
        )
        composition_rows = []
        for dimension_name, field, meaning in composition_specs:
            counts = cases[field].value_counts().sort_index()
            for group, count in counts.items():
                composition_rows.append(
                    (
                        tex_escape(dimension_name),
                        human_label(group),
                        integer(count),
                        percent(count / len(cases), 2),
                        tex_escape(meaning),
                    )
                )
        write_macro(handle, "CompositionRows", latex_rows(composition_rows))

        category_data = cases.copy()
        category_data["label"] = category_data["clean_categories"].str.split("; ")
        category_data = category_data.explode("label")
        category_rows = []
        category_groups = sorted(
            category_data.groupby("label", sort=False),
            key=lambda item: -len(item[1]),
        )
        used_category_examples: set[str] = set()
        for label, group in category_groups:
            ordered = group.sort_values(["effective_levenshtein", "case_id"])
            unused = ordered[~ordered["case_id"].isin(used_category_examples)]
            example = unused.iloc[0] if not unused.empty else ordered.iloc[0]
            used_category_examples.add(str(example["case_id"]))
            category_rows.append(
                (
                    human_label(label),
                    integer(len(group)),
                    percent(len(group) / len(cases), 2),
                    rf"\code{{{tex_escape(example['input'])}}}",
                    rf"\code{{{tex_escape(example['expected'])}}}",
                    int(example["effective_levenshtein"]),
                )
            )
        category_rows.sort(key=lambda row: -int(str(row[1]).replace(",", "")))
        write_macro(handle, "CategoryRows", latex_rows(category_rows))

        error_data = cases.copy()
        error_data["label"] = error_data["clean_error_types"].str.split("; ")
        error_data = error_data.explode("label")
        error_rows = []
        error_groups = sorted(
            error_data.groupby("label"),
            key=lambda item: -len(item[1]),
        )
        used_error_examples: set[str] = set()
        for label, group in error_groups:
            ordered = group.sort_values("case_id")
            unused = ordered[~ordered["case_id"].isin(used_error_examples)]
            example = unused.iloc[0] if not unused.empty else ordered.iloc[0]
            used_error_examples.add(str(example["case_id"]))
            error_rows.append(
                (
                    human_label(label),
                    integer(len(group)),
                    percent(len(group) / len(cases), 2),
                    rf"\code{{{tex_escape(example['input'])}}}",
                    rf"\code{{{tex_escape(example['expected'])}}}",
                )
            )
        error_rows.sort(key=lambda row: -int(str(row[1]).replace(",", "")))
        write_macro(handle, "ErrorTypeRows", latex_rows(error_rows[:25]))

        accuracy_fields = ("hit_at_1", "hit_at_5", "hit_at_10", "hit_at_20", "mrr_at_20")
        accuracy_best = {field: overall[field].max() for field in accuracy_fields}
        latency_best = {field: overall[field].min() for field in ("median_latency_ms", "p95_latency_ms")}
        preparation_best = overall["preparation_ms"].min()
        unsafe_best = overall["unsafe_confident_top1_rate"].min()
        overall_rows = []
        for algorithm in ALGORITHM_ORDER:
            row = overall.loc[algorithm]
            cells = [tex_escape(ALGORITHM_NAMES[algorithm])]
            for field in accuracy_fields:
                formatted = percent(row[field], 4) if field != "mrr_at_20" else f"{row[field]:.6f}"
                cells.append(bold(formatted, np.isclose(row[field], accuracy_best[field])))
            cells.extend(
                [
                    bold(f"{row['preparation_ms']:.1f}", np.isclose(row["preparation_ms"], preparation_best)),
                    bold(f"{row['median_latency_ms']:.4f}", np.isclose(row["median_latency_ms"], latency_best["median_latency_ms"])),
                    bold(f"{row['p95_latency_ms']:.4f}", np.isclose(row["p95_latency_ms"], latency_best["p95_latency_ms"])),
                    f"{row['mean_candidate_count']:.2f}",
                    bold(percent(row["unsafe_confident_top1_rate"], 4), np.isclose(row["unsafe_confident_top1_rate"], unsafe_best)),
                ]
            )
            overall_rows.append(tuple(cells))
        write_macro(handle, "OverallRows", latex_rows(overall_rows))

        behavior_rows = [
            (
                tex_escape(ALGORITHM_NAMES[algorithm]),
                percent(overall.loc[algorithm, "clarification_rate"], 2),
                percent(overall.loc[algorithm, "no_result_rate"], 2),
                percent(overall.loc[algorithm, "unsafe_confident_top1_rate"], 4),
                f"{overall.loc[algorithm, 'mean_candidate_count']:.2f}",
            )
            for algorithm in ALGORITHM_ORDER
        ]
        write_macro(handle, "BehaviorRows", latex_rows(behavior_rows))

        paired_rows = []
        for row in pairs:
            paired_rows.append(
                (
                    tex_escape(ALGORITHM_NAMES[row["comparison_algorithm"]]),
                    f"{100 * row['delta_hit_at_1']:+.4f}\\pp",
                    integer(row["a5_only_hit_at_1"]),
                    integer(row["comparison_only_hit_at_1"]),
                    p_value(row["mcnemar_p_hit_at_1"]),
                    f"{100 * row['delta_hit_at_20']:+.4f}\\pp",
                    p_value(row["mcnemar_p_hit_at_20"]),
                )
            )
        write_macro(handle, "PairedRows", latex_rows(paired_rows))

        split_rows = []
        for algorithm in ALGORITHM_ORDER:
            development = metric_lookup(metrics, algorithm, "split", "development")
            holdout = metric_lookup(metrics, algorithm, "split", "holdout")
            split_rows.append(
                (
                    tex_escape(ALGORITHM_NAMES[algorithm]),
                    percent(development["hit_at_1"], 2),
                    percent(holdout["hit_at_1"], 2),
                    percent(development["hit_at_20"], 2),
                    percent(holdout["hit_at_20"], 2),
                )
            )
        write_macro(handle, "SplitRows", latex_rows(split_rows))

        for metric_field, command in (("hit_at_1", "DistanceHOneRows"), ("hit_at_20", "DistanceHTwentyRows")):
            rows = []
            values = {
                (algorithm, distance): metric_lookup(metrics, algorithm, "effective_levenshtein", str(distance))[metric_field]
                for algorithm in ALGORITHM_ORDER
                for distance in range(1, 6)
            }
            column_best = {distance: max(values[(algorithm, distance)] for algorithm in ALGORITHM_ORDER) for distance in range(1, 6)}
            overall_best = overall[metric_field].max()
            for algorithm in ALGORITHM_ORDER:
                cells = [
                    tex_escape(ALGORITHM_NAMES[algorithm]),
                    bold(percent(overall.loc[algorithm, metric_field], 2), np.isclose(overall.loc[algorithm, metric_field], overall_best)),
                ]
                for distance in range(1, 6):
                    value = values[(algorithm, distance)]
                    cells.append(bold(percent(value, 2), np.isclose(value, column_best[distance])))
                rows.append(tuple(cells))
            write_macro(handle, command, latex_rows(rows))

        operation_order = (
            "mixed_operations",
            "visual_or_ocr",
            "phonetic",
            "vowel",
            "deletion",
            "transposition",
            "insertion",
            "keyboard",
            "other",
        )
        operation_rows = []
        for algorithm in ALGORITHM_ORDER:
            operation_rows.append(
                (
                    tex_escape(ALGORITHM_NAMES[algorithm]),
                    *[
                        percent(metric_lookup(metrics, algorithm, "operation_family", group)["hit_at_1"], 1)
                        for group in operation_order
                    ],
                )
            )
        write_macro(handle, "OperationRows", latex_rows(operation_rows))

        bigram_order = ("0_shared_bigrams", "1_shared_bigram", "2_3_shared_bigrams", "4_plus_shared_bigrams")
        bigram_rows = []
        for algorithm in ALGORITHM_ORDER:
            bigram_rows.append(
                (
                    tex_escape(ALGORITHM_NAMES[algorithm]),
                    percent(overall.loc[algorithm, "hit_at_1"], 2),
                    *[
                        percent(metric_lookup(metrics, algorithm, "shared_bigram_band", group)["hit_at_1"], 2)
                        for group in bigram_order
                    ],
                )
            )
        write_macro(handle, "BigramRows", latex_rows(bigram_rows))

        cohort_order = ("standard", "high_distance", "extreme")
        cohort_rows = []
        for algorithm in ALGORITHM_ORDER:
            algorithm_data = report_data[report_data["algorithm"] == algorithm]
            cells = [tex_escape(ALGORITHM_NAMES[algorithm])]
            for cohort in cohort_order:
                group = algorithm_data[algorithm_data["severity_cohort"] == cohort]
                cells.extend(
                    [
                        integer(len(group)),
                        percent(group["hit_at_1"].mean(), 2),
                        percent(group["hit_at_20"].mean(), 2),
                    ]
                )
            cohort_rows.append(tuple(cells))
        write_macro(handle, "CohortRows", latex_rows(cohort_rows))

        extreme = report_data[
            (report_data["algorithm"] == A5) & (report_data["severity_cohort"] == "extreme")
        ]
        extreme_rows = []
        for dimension, field in (
            ("Effective edits", "effective_levenshtein"),
            ("Operation family", "operation_family"),
            ("Shared bigrams", "shared_bigram_band"),
            ("Difficulty", "difficulty"),
        ):
            for group, values in extreme.groupby(field):
                extreme_rows.append(
                    (
                        tex_escape(dimension),
                        human_label(group),
                        integer(len(values)),
                        percent(len(values) / len(extreme), 2),
                        percent(values["hit_at_1"].mean(), 2),
                        percent(values["hit_at_20"].mean(), 2),
                    )
                )
        write_macro(handle, "ExtremeDistributionRows", latex_rows(extreme_rows))

        extreme_examples = []
        used_categories: set[str] = set()
        for row in extreme.sort_values(
            ["hit_at_20", "effective_levenshtein", "primary_category", "case_id"],
            ascending=[False, False, True, True],
        ).itertuples(index=False):
            if row.primary_category in used_categories and len(extreme_examples) < 6:
                continue
            used_categories.add(row.primary_category)
            extreme_examples.append(
                (
                    rf"\code{{{tex_escape(row.input)}}}",
                    rf"\code{{{tex_escape(row.expected)}}}",
                    f"{row.normalized_distance:.3f}",
                    int(row.shared_bigrams),
                    rf"\code{{{tex_escape(row.top_1)}}}",
                    "$>20$" if row.first_relevant_rank > 20 else int(row.first_relevant_rank),
                    human_label(row.primary_category),
                )
            )
            if len(extreme_examples) == 10:
                break
        write_macro(handle, "ExtremeExampleRows", latex_rows(extreme_examples))

        a_algorithms = ALGORITHM_ORDER[-5:]
        category_metrics = metrics[metrics["dimension"] == "clean_category"]
        category_names = sorted(
            category_metrics[category_metrics["algorithm"] == A5]["group"],
            key=lambda group: -int(metric_lookup(metrics, A5, "clean_category", group)["cases"]),
        )
        classical_category_rows = []
        for category in category_names:
            rows = [
                metric_lookup(metrics, algorithm, "clean_category", category)
                for algorithm in ALGORITHM_ORDER[:6]
            ]
            classical_category_rows.append(
                (
                    human_label(category),
                    integer(rows[0]["cases"]),
                    *[percent(row["hit_at_20"], 1) for row in rows],
                )
            )
        write_macro(handle, "ClassicalCategoryRows", latex_rows(classical_category_rows))

        category_algorithm_rows = []
        for category in category_names:
            rows = [metric_lookup(metrics, algorithm, "clean_category", category) for algorithm in a_algorithms]
            category_algorithm_rows.append(
                (
                    human_label(category),
                    integer(rows[0]["cases"]),
                    *[percent(row["hit_at_1"], 1) for row in rows],
                    *[percent(row["hit_at_20"], 1) for row in rows],
                )
            )
        write_macro(handle, "CategoryAlgorithmRows", latex_rows(category_algorithm_rows))

        impact_rows = [
            (
                human_label(row.group),
                integer(row.cases),
                percent(row.hit_at_1, 2),
                percent(row.hit_at_20, 2),
                integer(row.h1_failure_count),
                percent(row.h1_failure_rate, 2),
                percent(row.h1_failure_share, 2),
            )
            for row in a5_category_metrics.itertuples(index=False)
        ]
        write_macro(handle, "AFiveImpactRows", latex_rows(impact_rows))

        danger_rows = []
        for algorithm in ALGORITHM_ORDER:
            row = metric_lookup(metrics, algorithm, "danger", "DANGEROUS")
            danger_rows.append(
                (
                    tex_escape(ALGORITHM_NAMES[algorithm]),
                    integer(row["cases"]),
                    percent(row["hit_at_1"], 2),
                    percent(row["hit_at_20"], 2),
                    percent(row["unsafe_confident_top1_rate"], 2),
                )
            )
        write_macro(handle, "DangerRows", latex_rows(danger_rows))

        dangerous = cases[cases["danger"] == "DANGEROUS"].sort_values("case_id").head(8)
        danger_example_rows = [
            (
                rf"\code{{{tex_escape(row.input)}}}",
                rf"\code{{{tex_escape(row.expected)}}}",
                rf"\code{{{tex_escape(row.alternative_targets)}}}",
                int(row.effective_levenshtein),
                Levenshtein.distance(compact_text(row.input), compact_text(row.alternative_targets)),
                "Gold family is strictly closer, so one expected answer remains defensible.",
            )
            for row in dangerous.itertuples(index=False)
        ]
        write_macro(handle, "DangerExampleRows", latex_rows(danger_example_rows))

        tie_rows = [
            (
                tex_escape(ALGORITHM_NAMES[row["algorithm"]]),
                integer(row["wrong_top1_with_result"]),
                integer(row["equal_distance_wrong_top1"]),
                percent(row["equal_distance_share_of_wrong_top1"], 2),
                integer(row["equal_distance_rank_only"]),
                integer(row["equal_distance_retrieval_miss"]),
            )
            for row in ties
        ]
        write_macro(handle, "EqualDistanceRows", latex_rows(tie_rows))

        tie_example_rows = [
            (
                rf"\code{{{tex_escape(row['input'])}}}",
                rf"\code{{{tex_escape(row['expected'])}}}",
                rf"\code{{{tex_escape(row['a5_top_1'])}}}",
                row["equal_edit_distance"],
                "$>20$" if row["expected_rank"] > 20 else row["expected_rank"],
                human_label(row["clean_category"]),
                tex_escape(row["failure_level"]),
            )
            for row in tie_examples
        ]
        write_macro(handle, "EqualDistanceExampleRows", latex_rows(tie_example_rows))

        gain_rows = []
        for row in gain_examples:
            rank = "$>20$" if row["comparison_rank"] > 20 else row["comparison_rank"]
            gain_rows.append(
                (
                    tex_escape(ALGORITHM_NAMES[row["comparison_algorithm"]]),
                    rf"\code{{{tex_escape(row['input'])}}}",
                    rf"\code{{{tex_escape(row['expected'])}}}",
                    rf"\code{{{tex_escape(row['comparison_top_1'])}}}",
                    rank,
                    f"A5 ranks the verified family first at {row['effective_levenshtein']} edits; {human_label(row['clean_category'])}.",
                )
            )
        write_macro(handle, "AFiveGainRows", latex_rows(gain_rows))

        failure_rows = []
        for row in failure_examples:
            rank = "$>20$" if row["expected_rank"] > 20 else row["expected_rank"]
            failure_rows.append(
                (
                    tex_escape(ALGORITHM_NAMES[row["algorithm"]]),
                    tex_escape(row["failure_type"]),
                    rf"\code{{{tex_escape(row['input'])}}}",
                    rf"\code{{{tex_escape(row['expected'])}}}",
                    rf"\code{{{tex_escape(row['top_1'])}}}",
                    rank,
                    row["effective_levenshtein"],
                    human_label(row["clean_category"]),
                )
            )
        write_macro(handle, "FailureExampleRows", latex_rows(failure_rows))

        score_reconciliation_rows = [
            (
                tex_escape(row.group),
                integer(row.cases),
                percent(row.share, 4),
            )
            for row in rank_breakdown.itertuples(index=False)
        ]
        write_macro(
            handle,
            "ScoreReconciliationRows",
            latex_rows(score_reconciliation_rows),
        )

        validity_labels = {
            "case_rows": ("A5 rows", "Must equal the clean-core denominator."),
            "unique_case_ids": ("Unique A5 case IDs", "One result row per test case."),
            "hit_at_1_flag_mismatches": ("Recomputed Hit@1 mismatches", "Top name was compared again with the expected family key."),
            "rank_flag_mismatches": ("Recomputed Hit@20 mismatches", "Stored rank and Hit@20 flag must agree."),
            "levenshtein_distance_mismatches": ("Levenshtein mismatches", "Every stored distance was recalculated from query and target."),
            "damerau_distance_mismatches": ("Unrestricted Damerau mismatches", "The stored effective-Damerau field was recalculated with its own distance definition."),
            "stored_damerau_osa_differences": ("Stored Damerau versus A5 OSA differences", "These are expected definition differences, not Hit@k scoring errors."),
            "exact_other_catalog_queries": ("Exact different-family queries", "A positive value would be an unfair real-name collision."),
            "fresh_rerun_rows": ("Independent full-rerun rows", "A5 was rebuilt and executed again over the complete clean-core dataset."),
            "fresh_rank_mismatches": ("Independent expected-rank mismatches", "Fresh and recorded ranks of the verified family must agree."),
            "fresh_hit_flag_mismatches": ("Independent Hit@1/5/10/20 mismatches", "All four rank-cutoff decisions must reproduce."),
            "fresh_top_name_differences": ("Independent first-name differences", "A changed wrong alternative can leave the verified rank and Hit@k unchanged."),
            "fresh_candidate_count_differences": ("Independent candidate-count differences", "Candidate-pool size is diagnostic and does not enter Hit@k directly."),
            "rerun_cases": ("Unique-nearest failures rerun", "Current A5 was executed again with candidate scores exposed."),
            "rerun_mismatches": ("Unique-nearest rerun mismatches", "Fresh top name and expected rank must match the benchmark."),
            "osa_equivalence_pairs": ("A5/OSA distance test pairs", "Random string pairs used to verify the distance implementation."),
            "osa_equivalence_mismatches": ("A5/OSA implementation mismatches", "A positive value would invalidate OSA geometry labels."),
        }
        validity_values = failure_tables["validity"].set_index("check")["value"]
        validity_rows = [
            (
                tex_escape(label),
                integer(validity_values[key]),
                tex_escape(meaning),
            )
            for key, (label, meaning) in validity_labels.items()
            if key in validity_values.index
        ]
        write_macro(handle, "FailureValidityRows", latex_rows(validity_rows))
        if "fresh_rerun_rows" in validity_values.index:
            mismatch_fields = (
                "fresh_rank_mismatches",
                "fresh_hit_flag_mismatches",
                "fresh_top_name_differences",
                "fresh_candidate_count_differences",
            )
            mismatch_counts = {
                field: int(validity_values.get(field, 0)) for field in mismatch_fields
            }
            if not any(mismatch_counts.values()):
                caption = (
                    "A fresh full run reproduces every verified-family rank, "
                    "Hit@1/5/10/20 flag, first displayed family, and candidate count."
                )
                rerun_text = (
                    "The independent full rerun matched all "
                    f"{integer(len(a5_rows))} rows on expected "
                    "rank, every Hit@k flag, the first displayed family, and candidate "
                    "count. Candidate generation now resolves equal-frequency n-gram "
                    "and index ties with explicit sorting, so the previous non-scoring "
                    "ordering instability is no longer present."
                )
            else:
                caption = "The fresh full run exposed differences that require review."
                rerun_text = (
                    "The independent full rerun produced "
                    f"{integer(mismatch_counts['fresh_rank_mismatches'])} expected-rank "
                    "differences, "
                    f"{integer(mismatch_counts['fresh_hit_flag_mismatches'])} Hit@k "
                    "differences, "
                    f"{integer(mismatch_counts['fresh_top_name_differences'])} first-name "
                    "differences, and "
                    f"{integer(mismatch_counts['fresh_candidate_count_differences'])} "
                    "candidate-count differences. Resolve these differences before "
                    "treating the artifact as reproducible."
                )
            write_macro(handle, "FreshRerunCaption", caption)
            write_macro(handle, "FreshRerunAuditText", rerun_text)
        else:
            write_macro(handle, "FreshRerunCaption", "")
            write_macro(handle, "FreshRerunAuditText", "")

        family_rows = [
            (
                tex_escape(row.denominator),
                integer(row.units),
                percent(row.hit_at_1, 4),
                percent(row.hit_at_20, 4),
                tex_escape(row.meaning),
            )
            for row in family_summary.itertuples(index=False)
        ]
        write_macro(handle, "FamilyDenominatorRows", latex_rows(family_rows))
        concentration_rows = [
            (
                tex_escape(row.metric),
                integer(row.value),
                percent(row.share, 2),
            )
            for row in family_concentration.itertuples(index=False)
        ]
        write_macro(
            handle,
            "FailureConcentrationRows",
            latex_rows(concentration_rows),
        )

        status_labels = {
            "gold_unique_nearest": "Gold is the unique nearest family",
            "gold_tied_nearest": "Gold ties with catalog neighbors",
            "competitor_strictly_closer": "Another catalog family is closer",
        }
        status_order = (
            "gold_unique_nearest",
            "gold_tied_nearest",
            "competitor_strictly_closer",
        )
        catalog_geometry_rows = []
        for status in status_order:
            group = a5_rows[a5_rows["osa_gold_status"] == status]
            catalog_geometry_rows.append(
                (
                    tex_escape(status_labels[status]),
                    integer(len(group)),
                    percent(len(group) / len(a5_rows), 2),
                    percent(group["hit_at_1"].mean(), 4),
                    percent(group["hit_at_20"].mean(), 4),
                    integer((group["hit_at_1"] == 0).sum()),
                )
            )
        write_macro(
            handle,
            "CatalogGeometryRows",
            latex_rows(catalog_geometry_rows),
        )

        root_index = root_causes.set_index("gold_status")
        failure_root_rows = [
            (
                tex_escape(status_labels[status]),
                integer(root_index.loc[status, "cases"]),
                percent(root_index.loc[status, "share_of_a5_h1_failures"], 2),
                integer(root_index.loc[status, "ranking_failures"]),
                integer(root_index.loc[status, "retrieval_failures"]),
            )
            for status in status_order
        ]
        write_macro(handle, "FailureRootRows", latex_rows(failure_root_rows))

        distance_geometry_rows = []
        for status in status_order:
            osa_count = int((failure_audit["osa_gold_status"] == status).sum())
            leven_count = int(
                (failure_audit["levenshtein_gold_status"] == status).sum()
            )
            distance_geometry_rows.append(
                (
                    tex_escape(status_labels[status]),
                    integer(leven_count),
                    percent(leven_count / len(failure_audit), 2),
                    integer(osa_count),
                    percent(osa_count / len(failure_audit), 2),
                )
            )
        write_macro(
            handle,
            "FailureDistanceDefinitionRows",
            latex_rows(distance_geometry_rows),
        )

        geometry_map = a5_rows[["case_id", "osa_gold_status"]]
        geometry_data = report_data.merge(
            geometry_map, on="case_id", how="left", validate="many_to_one"
        )
        system_geometry_rows = []
        for algorithm in ALGORITHM_ORDER:
            algorithm_rows = geometry_data[geometry_data["algorithm"] == algorithm]
            cells: list[Any] = [tex_escape(ALGORITHM_NAMES[algorithm])]
            for status in status_order:
                group = algorithm_rows[algorithm_rows["osa_gold_status"] == status]
                cells.extend(
                    [
                        percent(group["hit_at_1"].mean(), 2),
                        percent(group["hit_at_20"].mean(), 2),
                    ]
                )
            system_geometry_rows.append(tuple(cells))
        write_macro(
            handle,
            "SystemGeometryRows",
            latex_rows(system_geometry_rows),
        )

        unique_mechanism_rows = [
            (
                tex_escape(row.group),
                integer(row.cases),
                percent(row.cases / len(failure_audit), 2),
                tex_escape(row.meaning),
            )
            for row in failure_tables["unique_mechanisms"].itertuples(index=False)
        ]
        write_macro(
            handle,
            "UniqueFailureMechanismRows",
            latex_rows(unique_mechanism_rows),
        )

        unique_failure = failure_audit[
            failure_audit["osa_gold_status"] == "gold_unique_nearest"
        ]
        unique_ranking = unique_failure[unique_failure["hit_at_20"] == 1]
        unique_retrieval = unique_failure[unique_failure["hit_at_20"] == 0]
        unique_pattern_rows = [
            (
                "Expected already in top 20",
                integer(len(unique_ranking)),
                integer((unique_ranking["shared_bigrams"] >= 4).sum()),
                integer((unique_ranking["query_length"] <= 4).sum()),
                integer(unique_ranking["no_result"].sum()),
                (
                    "Reranking problem: "
                    f"{int((unique_ranking['score_gap'] >= 0).sum())} combined-score "
                    "inversions and "
                    f"{int((unique_ranking['score_gap'] < 0).sum())} bounded-correction "
                    "overrides."
                ),
            ),
            (
                "Expected outside top 20",
                integer(len(unique_retrieval)),
                integer((unique_retrieval["shared_bigrams"] >= 4).sum()),
                integer((unique_retrieval["query_length"] <= 4).sum()),
                integer(unique_retrieval["no_result"].sum()),
                (
                    "No remaining candidate-generation failures; every verified family "
                    "is in the top 20."
                    if unique_retrieval.empty
                    else "Candidate-generation problem: most rows are short or retain at most one bigram."
                ),
            ),
        ]
        write_macro(handle, "UniqueFailurePatternRows", latex_rows(unique_pattern_rows))

        rescue_rows = [
            (
                tex_escape(row.algorithm_name),
                integer(row.hit_at_1_rescues),
                percent(row.hit_at_1_rescues / len(failure_audit), 2),
                integer(row.hit_at_20_retrievals),
                percent(row.hit_at_20_retrievals / len(failure_audit), 2),
            )
            for row in failure_tables["rescue"].itertuples(index=False)
        ]
        write_macro(handle, "FailureRescueRows", latex_rows(rescue_rows))

        all_system_misses = failure_audit[
            (failure_audit["hit_at_20"] == 0)
            & (failure_audit["other_h20_rescue_count"] == 0)
        ]
        all_system_rows = [
            ("Total", integer(len(all_system_misses))),
            (
                "Mixed-operation rows",
                integer((all_system_misses["operation_family"] == "mixed_operations").sum()),
            ),
            (
                "Effective Levenshtein distance 3--5",
                integer(all_system_misses["effective_levenshtein"].between(3, 5).sum()),
            ),
            (
                "Another family closer",
                integer((all_system_misses["osa_gold_status"] == "competitor_strictly_closer").sum()),
            ),
            (
                "Gold tied nearest",
                integer((all_system_misses["osa_gold_status"] == "gold_tied_nearest").sum()),
            ),
            (
                "Gold unique nearest",
                integer((all_system_misses["osa_gold_status"] == "gold_unique_nearest").sum()),
            ),
        ]
        write_macro(handle, "AllSystemMissRows", latex_rows(all_system_rows))

        fallback_rows = [
            (
                tex_escape(row.rule),
                integer(row.changed_cases),
                integer(row.corrected_failures),
                integer(row.broken_successes),
                f"{row.net_correct:+d}",
                percent(row.counterfactual_hit_at_1, 4),
            )
            for row in failure_tables["fallback"].itertuples(index=False)
        ]
        write_macro(handle, "FallbackRows", latex_rows(fallback_rows))

        review_rows = []
        for row in manual_review.itertuples(index=False):
            rank = "$>20$" if row.first_relevant_rank > 20 else int(row.first_relevant_rank)
            top = "no result" if pd.isna(row.top_1) or not str(row.top_1) else row.top_1
            nearest = (
                f"{row.osa_nearest_names} (d={int(row.osa_nearest_distance)}, "
                f"n={int(row.osa_nearest_count)})"
            )
            review_rows.append(
                (
                    tex_escape(row.review_class),
                    rf"\code{{{tex_escape(row.input)}}}",
                    rf"\code{{{tex_escape(row.expected)}}}",
                    rf"\code{{{tex_escape(top)}}}" if top != "no result" else "no result",
                    rank,
                    int(row.osa_expected_distance),
                    tex_escape(nearest),
                    tex_escape(row.manual_review),
                )
            )
        write_macro(handle, "ManualFailureReviewRows", latex_rows(review_rows))

        score_example_notes = {
            "SC-7EC921D4F5412F": "The uniquely nearest target is one edit closer, but the long-name neighbor leads the combined score by 0.3309.",
            "SC-413102D124577B": "Shorter-family evidence overwhelms the full SOLVIN N spelling by 1.1046 score units.",
            "SC-399FB2BE6E3A9B": "The structural CL-to-D target is one edit closer but remains at rank 9 after bounded corrections.",
            "SC-07A0590E5E0CF1": "The uniquely nearest target trails the displayed family by only 0.0294 score units.",
        }
        score_example_rows = []
        indexed_failures = failure_audit.set_index("case_id")
        for case_id, note in score_example_notes.items():
            if case_id not in indexed_failures.index:
                continue
            row = indexed_failures.loc[case_id]
            score_example_rows.append(
                (
                    rf"\code{{{tex_escape(row['input'])}}}",
                    rf"\code{{{tex_escape(row['expected'])}}}",
                    rf"\code{{{tex_escape(row['top_1'])}}}",
                    f"{row['expected_raw_distance']:.0f}/{row['top_raw_distance']:.0f}",
                    f"{row['expected_score']:.4f}/{row['top_score']:.4f}",
                    int(row["first_relevant_rank"]),
                    tex_escape(note),
                )
            )
        write_macro(
            handle,
            "UniqueScoreExampleRows",
            latex_rows(score_example_rows),
        )


def main() -> None:
    args = parse_args()
    cases = pd.read_csv(args.cases, encoding="utf-8-sig", low_memory=False)
    cases["shared_bigrams"] = [
        shared_bigram_count(query, target)
        for query, target in zip(cases["input"], cases["expected"])
    ]
    cases["shared_bigram_band"] = cases["shared_bigrams"].map(shared_bigram_band)
    old = pd.read_csv(args.old_cases, encoding="utf-8-sig", low_memory=False)
    old_fair_metrics = pd.read_csv(
        args.old_fair_metrics, encoding="utf-8-sig", low_memory=False
    )
    metrics = read_metrics(args.results_dir / "metrics.csv")
    data = read_results(args.artifacts_dir / "case_results.csv", len(cases))

    pairs = paired_comparisons(data)
    transition = source_category_transition(old, cases)
    audit = dataset_audit(cases, old)
    ties, tie_examples = equal_distance_rows(data)
    failure_examples = select_failure_examples(data)
    gain_examples = select_a5_gain_examples(data)
    a5_audit, failure_audit, failure_validity, _family_names = build_failure_audit(data)
    failure_validity.update(
        compare_fresh_a5_results(a5_audit, args.fresh_a5_results)
    )
    failure_tables = failure_analysis_tables(
        data,
        a5_audit,
        failure_audit,
        failure_validity,
    )
    reviewed_failures = manual_failure_review(failure_audit)

    write_csv(args.results_dir / "paired_comparisons.csv", pairs)
    write_csv(args.results_dir / "dataset_audit.csv", audit)
    write_csv(args.results_dir / "source_category_transition.csv", transition)
    write_csv(args.results_dir / "equal_distance_summary.csv", ties)
    write_csv(args.artifacts_dir / "equal_distance_examples.csv", tie_examples)
    write_csv(args.artifacts_dir / "failure_examples.csv", failure_examples)
    write_csv(args.artifacts_dir / "a5_gain_examples.csv", gain_examples)
    failure_audit.to_csv(
        args.artifacts_dir / "a5_failure_audit.csv",
        index=False,
        encoding="utf-8",
    )
    write_failure_summary(
        args.results_dir / "a5_failure_analysis.csv",
        failure_tables,
    )
    build_report_tables(
        args.results_dir / "report_tables.tex",
        cases,
        old,
        old_fair_metrics,
        metrics,
        data,
        audit,
        transition,
        pairs,
        ties,
        tie_examples,
        failure_examples,
        gain_examples,
        failure_tables,
        a5_audit,
        failure_audit,
        reviewed_failures,
    )

    overall = metrics[metrics["dimension"] == "overall"].set_index("algorithm")
    summary = {
        "evaluation_version": str(metrics.iloc[0]["evaluation_version"]),
        "dataset_rows": len(cases),
        "source_rows": len(old),
        "represented_source_occurrences": int(cases["source_row_count"].sum()),
        "target_families": int(cases["expected"].nunique()),
        "algorithms": len(ALGORITHM_ORDER),
        "algorithm_4": {
            "hit_at_1": float(overall.loc[A4, "hit_at_1"]),
            "hit_at_20": float(overall.loc[A4, "hit_at_20"]),
            "mrr_at_20": float(overall.loc[A4, "mrr_at_20"]),
            "unsafe_confident_top1_rate": float(
                overall.loc[A4, "unsafe_confident_top1_rate"]
            ),
        },
        "algorithm_5": {
            "hit_at_1": float(overall.loc[A5, "hit_at_1"]),
            "hit_at_20": float(overall.loc[A5, "hit_at_20"]),
            "mrr_at_20": float(overall.loc[A5, "mrr_at_20"]),
            "unsafe_confident_top1_rate": float(overall.loc[A5, "unsafe_confident_top1_rate"]),
            "hit_at_1_failures": int((a5_audit["hit_at_1"] == 0).sum()),
            "ranking_failures": int(
                ((a5_audit["hit_at_1"] == 0) & (a5_audit["hit_at_20"] == 1)).sum()
            ),
            "retrieval_failures": int((a5_audit["hit_at_20"] == 0).sum()),
            "unique_osa_nearest_hit_at_1": float(
                a5_audit.loc[
                    a5_audit["osa_gold_status"] == "gold_unique_nearest",
                    "hit_at_1",
                ].mean()
            ),
        },
        "algorithm_5_vs_algorithm_4": {
            "hit_at_1_delta_percentage_points": float(
                (overall.loc[A5, "hit_at_1"] - overall.loc[A4, "hit_at_1"]) * 100
            ),
            "hit_at_20_delta_percentage_points": float(
                (overall.loc[A5, "hit_at_20"] - overall.loc[A4, "hit_at_20"]) * 100
            ),
        },
    }
    write_json(args.results_dir / "summary.json", summary)
    print(
        f"Validated {len(data):,} result rows and wrote clean-core analysis for "
        f"{len(cases):,} primary cases."
    )


if __name__ == "__main__":
    main()

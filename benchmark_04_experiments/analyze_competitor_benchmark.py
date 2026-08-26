#!/usr/bin/env python3
"""Analyze cached and newly evaluated retrieval systems on both locked datasets."""

from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.metadata
import json
import math
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter
from scipy.stats import binomtest, spearmanr


BENCHMARK_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BENCHMARK_ROOT.parent
OCR_ROOT = PROJECT_ROOT / "benchmark_03_ocr"
LEGACY_ROOT = PROJECT_ROOT / "benchmark_01_legacy"
COMPETITOR_RESULTS = BENCHMARK_ROOT / "results/06_competitor_benchmark"
COMPETITOR_ARTIFACTS = BENCHMARK_ROOT / "artifacts/06_competitor_benchmark"
OUTPUT = COMPETITOR_RESULTS / "analysis"
FIGURES = COMPETITOR_RESULTS / "figures"
OCR_CACHED = BENCHMARK_ROOT / "artifacts/case_results.csv"
_SYNTHETIC_CSV = (
    BENCHMARK_ROOT / "artifacts/05_synthetic_clean_core/case_results.csv"
)
SYNTHETIC_CACHED = (
    _SYNTHETIC_CSV
    if _SYNTHETIC_CSV.exists()
    else _SYNTHETIC_CSV.with_suffix(_SYNTHETIC_CSV.suffix + ".gz")
)
SYNTHETIC_A5_CURRENT = (
    COMPETITOR_ARTIFACTS / "a5_current/case_results.csv"
)
LEGACY_RETRIEVAL_METRICS = BENCHMARK_ROOT / "results/metrics.csv"
SYNTHETIC_RETRIEVAL_METRICS = (
    BENCHMARK_ROOT / "results/05_synthetic_clean_core/metrics.csv"
)
OCR_CASES = OCR_ROOT / "artifacts/04_model_predictions/search_cases.csv"
TOP_K = 20

for import_path in (BENCHMARK_ROOT, OCR_ROOT, LEGACY_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import evaluate_current_app_search as current_app
import run_competitor_benchmark as competitor_runner
import run_synthetic_clean_core as synthetic_core


BLUE = "#4477AA"
CYAN = "#66CCEE"
ORANGE = "#EE7733"
PURPLE = "#AA3377"
GRAY = "#66717D"
LIGHT_GRAY = "#D9DEE5"

CACHED_ALGORITHMS = (
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
)

DISPLAY_NAMES = {
    **synthetic_core.DISPLAY_NAMES,
    "algorithm_5_evidence_rescue": "Algorithm 5, evidence-guided rescue",
    **{
        item.algorithm: item.display_name
        for item in competitor_runner.EVALUATED_COMPETITORS
    },
}

ALL_ALGORITHM_IDS = (
    *CACHED_ALGORITHMS,
    *(item.algorithm for item in competitor_runner.EVALUATED_COMPETITORS),
    "algorithm_5_evidence_rescue",
)
ALGORITHM_DTYPE = pd.CategoricalDtype(
    categories=list(ALL_ALGORITHM_IDS),
    ordered=False,
)
ALGORITHM_NAME_DTYPE = pd.CategoricalDtype(
    categories=[DISPLAY_NAMES[value] for value in ALL_ALGORITHM_IDS],
    ordered=False,
)

PROJECT_ALGORITHMS = {
    "algorithm_1_current_app",
    "algorithm_2_external_fast",
    "algorithm_3_rank_fusion",
    "algorithm_4_family_rescue",
    "algorithm_5_evidence_rescue",
}

CORRELATION_FEATURES = {
    "edit_distance": "Edit distance (operations)",
    "normalized_distance": "Normalized distance (ratio)",
    "query_length": "Query length (characters)",
    "shared_bigrams": "Shared-bigram evidence",
    "candidate_count": "Candidate count",
    "hit_at_1": "Hit@1 indicator",
    "hit_at_20": "Hit@20 indicator",
    "latency_ms": "Latency (ms)",
}

DATASET_NAMES = {
    "ocr_464": "464 fair OCR pairs",
    "synthetic_66257": "66,257 synthetic pairs",
}

COMPONENT_GROUP_NAMES = {
    "bm25": "BM25 character retrieval",
    "dense": "Biomedical dense encoders",
    "phonetic": "Phonetic encoders",
    "preon": "preon staged normalizer",
    "qgram": "Character q-gram retrieval",
    "rapidfuzz": "Character-similarity scorers",
    "symspell": "SymSpell delete-index retrieval",
}

REPRESENTATIVE_SYSTEMS = (
    "algorithm_5_evidence_rescue",
    "algorithm_4_family_rescue",
    "algorithm_3_rank_fusion",
    "damerau_levenshtein",
    "symspell_frequency_ed3",
    "rapidfuzz_ratio",
    "jaro_similarity",
    "dice_char2",
    "bm25_okapi_char2",
    "baseline_phonetic",
    "coderpp_dense_hnsw",
    "biosyn_hybrid_w50",
    "preon_default",
    "fuse_default_bitap",
    "flexsearch_tolerant_extra",
)

EXTERNAL_COMPONENT_COMPARISONS = (
    (
        "BioSyn 0.50",
        "biosyn_hybrid_w50",
        "sapbert_dense_hnsw",
        "Remove sparse TF-IDF branch",
        "strict_component",
    ),
    (
        "BioSyn 0.50",
        "biosyn_hybrid_w50",
        "baseline_char_3gram_tfidf",
        "Remove dense SapBERT branch",
        "strict_component",
    ),
    (
        "xMEN RRF",
        "xmen_sapbert_tfidf_rrf",
        "sapbert_dense_hnsw",
        "Remove sparse TF-IDF branch",
        "strict_component",
    ),
    (
        "xMEN RRF",
        "xmen_sapbert_tfidf_rrf",
        "baseline_char_3gram_tfidf",
        "Remove dense SapBERT branch",
        "strict_component",
    ),
    (
        "SymSpell distance 3",
        "symspell_frequency_ed3",
        "symspell_uniform_ed3",
        "Remove catalog-frequency tie evidence",
        "strict_component",
    ),
    (
        "SymSpell catalog frequency",
        "symspell_frequency_ed3",
        "symspell_frequency_ed2",
        "Reduce maximum edit radius from 3 to 2",
        "parameter_sensitivity",
    ),
    (
        "BM25 Okapi bigrams",
        "bm25_okapi_char2",
        "bm25_okapi_char3",
        "Replace character bigrams with trigrams",
        "parameter_sensitivity",
    ),
    (
        "BM25 Okapi trigrams",
        "bm25_okapi_char3",
        "bm25_l_char3",
        "Replace Okapi length normalization with BM25L",
        "parameter_sensitivity",
    ),
    (
        "BM25 Okapi trigrams",
        "bm25_okapi_char3",
        "bm25_plus_char3",
        "Replace Okapi length normalization with BM25Plus",
        "parameter_sensitivity",
    ),
    (
        "QuickUMLS Dice",
        "quickumls_dice_char3",
        "quickumls_jaccard_char3",
        "Replace Dice with Jaccard",
        "parameter_sensitivity",
    ),
    (
        "QuickUMLS Dice",
        "quickumls_dice_char3",
        "quickumls_cosine_char3",
        "Replace Dice with cosine",
        "parameter_sensitivity",
    ),
    (
        "QuickUMLS Dice",
        "quickumls_dice_char3",
        "quickumls_overlap_char3",
        "Replace Dice with overlap coefficient",
        "parameter_sensitivity",
    ),
    (
        "RapidFuzz WRatio",
        "rapidfuzz_wratio",
        "rapidfuzz_ratio",
        "Use full-string ratio only",
        "parameter_sensitivity",
    ),
    (
        "RapidFuzz WRatio",
        "rapidfuzz_wratio",
        "rapidfuzz_partial_ratio",
        "Use partial-string ratio only",
        "parameter_sensitivity",
    ),
    (
        "RapidFuzz WRatio",
        "rapidfuzz_wratio",
        "rapidfuzz_token_sort",
        "Use token-sort ratio only",
        "parameter_sensitivity",
    ),
    (
        "RapidFuzz WRatio",
        "rapidfuzz_wratio",
        "rapidfuzz_token_set",
        "Use token-set ratio only",
        "parameter_sensitivity",
    ),
    (
        "preon default cascade",
        "preon_default",
        "preon_without_token",
        "Remove exact-token stage",
        "strict_component",
    ),
    (
        "preon default cascade",
        "preon_default",
        "preon_without_partial",
        "Remove normalized-Levenshtein partial stage",
        "strict_component",
    ),
    (
        "Fuse.js token search",
        "fuse_token_search",
        "fuse_default_bitap",
        "Disable token-aware matching",
        "parameter_sensitivity",
    ),
    (
        "FlexSearch tolerant, Latin advanced",
        "flexsearch_tolerant_advanced",
        "flexsearch_tolerant_default",
        "Replace Latin advanced encoding with the default encoder",
        "parameter_sensitivity",
    ),
    (
        "FlexSearch tolerant, Latin extra",
        "flexsearch_tolerant_extra",
        "flexsearch_tolerant_default",
        "Replace Latin extra encoding with the default encoder",
        "parameter_sensitivity",
    ),
    (
        "FlexSearch full, Latin advanced",
        "flexsearch_full_advanced",
        "flexsearch_tolerant_advanced",
        "Replace full tokenization with tolerant tokenization",
        "parameter_sensitivity",
    ),
)

NEW_RESULT_COLUMNS = (
    "dataset",
    "case_id",
    "algorithm",
    "algorithm_name",
    "input",
    "input_compact",
    "expected_family_keys",
    "expected_family_name",
    "split",
    "category",
    "error_type",
    "operation_family",
    "edit_distance",
    "normalized_distance",
    "distance_band",
    "query_length_band",
    "shared_bigram_band",
    "first_relevant_rank",
    "hit_at_1",
    "hit_at_5",
    "hit_at_10",
    "hit_at_20",
    "no_result",
    "candidate_count",
    "latency_ms",
    "top_1",
)

CATEGORY_COLUMNS = (
    "dataset",
    "case_id",
    "algorithm",
    "algorithm_name",
    "pair_key",
    "input",
    "input_compact",
    "expected_family_keys",
    "expected_family_name",
    "split",
    "category",
    "error_type",
    "operation_family",
    "operation_profile",
    "distance_band",
    "query_length_band",
    "shared_bigram_band",
    "top_1",
    "source_operation_sequence",
)


def compact(value: Any) -> str:
    return current_app.compact_key(str(value or ""))


def read_gzip_csv(
    path: Path,
    usecols: Sequence[str] | None = None,
) -> pd.DataFrame:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return pd.read_csv(handle, usecols=usecols)


def operation_profile(row: pd.Series) -> str:
    additions = int(row["source_additions_count"])
    deletions = int(row["source_deletions_count"])
    replacements = int(row["source_flip_count"])
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


def pair_key(input_value: Any, expected_keys: Any) -> str:
    return f"{compact(input_value)}|{str(expected_keys)}"


def load_ocr_case_metadata() -> pd.DataFrame:
    data = pd.read_csv(OCR_CASES, encoding="utf-8-sig")
    data = data[
        data["accepted"].eq(1) & data["scored_case"].eq(1)
    ].copy()
    data["pair_key"] = [
        pair_key(query, expected)
        for query, expected in zip(data["input"], data["expected_family_key"])
    ]
    data = data.drop_duplicates("pair_key", keep="first")
    if len(data) != 464:
        raise ValueError(f"expected 464 fair OCR pairs, found {len(data)}")
    data["operation_profile"] = data.apply(operation_profile, axis=1)
    data["query_length"] = data["input"].map(lambda value: len(compact(value)))
    data["shared_bigrams"] = data["shared_ngram_count"].astype(int)
    data["dataset"] = "ocr_464"
    data["input_compact"] = data["input"].map(compact)
    data["expected_family_keys"] = data["expected_family_key"]
    data["expected_family_name"] = data["expected_family_name"]
    data["category"] = data["analysis_cohort"]
    data["error_type"] = data["mistake_type"]
    data["operation_family"] = data["mistake_type"]
    data["normalized_distance"] = data["normalized_edit_distance"]
    data["query_length_band"] = data["query_length"].map(
        competitor_runner.query_length_band
    )
    data["shared_bigram_band"] = data["shared_bigrams"].map(
        competitor_runner.shared_bigram_band
    )
    data["case_index"] = np.arange(len(data), dtype=np.int32)
    return data[
        [
            "case_index",
            "dataset",
            "case_id",
            "pair_key",
            "input",
            "input_compact",
            "expected_family_keys",
            "expected_family_name",
            "split",
            "category",
            "error_type",
            "operation_family",
            "edit_distance",
            "normalized_distance",
            "distance_band",
            "query_length_band",
            "shared_bigram_band",
            "operation_profile",
            "source_additions_count",
            "source_deletions_count",
            "source_flip_count",
            "source_matches_count",
            "query_length",
            "shared_bigrams",
            "source_operation_sequence",
        ]
    ]


def load_synthetic_case_metadata() -> pd.DataFrame:
    first = sorted(
        (COMPETITOR_ARTIFACTS / "synthetic_66257").glob("*.csv.gz")
    )[0]
    fields = (
        "dataset",
        "case_id",
        "input",
        "input_compact",
        "expected_family_keys",
        "expected_family_name",
        "split",
        "category",
        "error_type",
        "operation_family",
        "edit_distance",
        "normalized_distance",
        "distance_band",
        "query_length_band",
        "shared_bigram_band",
    )
    data = read_gzip_csv(first, fields)
    if len(data) != 66257:
        raise ValueError(f"expected 66,257 synthetic metadata rows, found {len(data)}")
    data["pair_key"] = [
        pair_key(query, expected)
        for query, expected in zip(
            data["input"],
            data["expected_family_keys"],
        )
    ]
    data["case_index"] = np.arange(len(data), dtype=np.int32)
    data["query_length"] = data["input_compact"].str.len()
    data["shared_bigrams"] = data["shared_bigram_band"].map(
        {
            "0_shared_bigrams": 0,
            "1_shared_bigram": 1,
            "2_3_shared_bigrams": 2,
            "4_plus_shared_bigrams": 4,
        }
    )
    data["operation_profile"] = data["operation_family"]
    return data


def optimize_metadata(data: pd.DataFrame) -> pd.DataFrame:
    output = data.copy()
    for field in CATEGORY_COLUMNS:
        if field in output:
            output[field] = output[field].astype("category")
    for field in ("case_index", "edit_distance", "query_length", "shared_bigrams"):
        if field in output:
            output[field] = pd.to_numeric(output[field], downcast="integer")
    if "normalized_distance" in output:
        output["normalized_distance"] = pd.to_numeric(
            output["normalized_distance"],
            downcast="float",
        )
    return output


def normalize_new_rows(data: pd.DataFrame) -> pd.DataFrame:
    output = data.copy()
    output["pair_key"] = [
        pair_key(query, expected)
        for query, expected in zip(
            output["input"],
            output["expected_family_keys"],
        )
    ]
    output["rank"] = output["first_relevant_rank"].astype(int)
    output["query_length"] = output["input_compact"].str.len()
    for cutoff in (1, 5, 10, 20):
        field = f"hit_at_{cutoff}"
        output[field] = output[field].astype(int)
        expected_hit = output["rank"].le(cutoff).astype(int)
        if not output[field].equals(expected_hit):
            mismatches = int(output[field].ne(expected_hit).sum())
            raise ValueError(
                f"{mismatches:,} rows disagree between {field} and "
                "first_relevant_rank"
            )
    expected_no_result = output["candidate_count"].astype(int).eq(0).astype(int)
    if not output["no_result"].astype(int).equals(expected_no_result):
        mismatches = int(
            output["no_result"].astype(int).ne(expected_no_result).sum()
        )
        raise ValueError(
            f"{mismatches:,} rows disagree between no_result and "
            "candidate_count"
        )
    output["latency_ms"] = output["latency_ms"].astype(float)
    return output


def load_new_competitors(dataset: str) -> pd.DataFrame:
    root = COMPETITOR_ARTIFACTS / dataset
    files = sorted(root.glob("*.csv.gz"))
    expected = len(competitor_runner.EVALUATED_COMPETITORS)
    if len(files) != expected:
        raise ValueError(
            f"{dataset}: expected {expected} competitor files, found {len(files)}"
        )
    return pd.concat(
        [
            normalize_new_rows(read_gzip_csv(path, NEW_RESULT_COLUMNS))
            for path in files
        ],
        ignore_index=True,
    )


def normalize_cached_ocr() -> pd.DataFrame:
    data = pd.read_csv(
        OCR_CACHED,
        usecols=(
            "experiment",
            "case_id",
            "split",
            "input",
            "expected_family_name",
            "expected_family_key",
            "scored_case",
            "analysis_cohort",
            "distance_band",
            "mistake_type",
            "edit_distance",
            "normalized_edit_distance",
            "algorithm",
            "first_relevant_rank",
            "hit_at_1",
            "hit_at_5",
            "hit_at_10",
            "hit_at_20",
            "candidate_count",
            "latency_ms",
            "top_1",
        ),
    )
    data = data[
        data["experiment"].eq("retrieval")
        & data["algorithm"].isin(CACHED_ALGORITHMS)
        & data["scored_case"].eq(1)
    ].copy()
    data["pair_key"] = [
        pair_key(query, expected)
        for query, expected in zip(data["input"], data["expected_family_key"])
    ]
    data = data.drop_duplicates(["algorithm", "pair_key"], keep="first")
    counts = data.groupby("algorithm").size()
    if not counts.eq(464).all() or len(counts) != len(CACHED_ALGORITHMS):
        raise ValueError(f"cached OCR coverage mismatch:\n{counts}")
    data["dataset"] = "ocr_464"
    data["algorithm_name"] = data["algorithm"].map(DISPLAY_NAMES)
    data["expected_family_keys"] = data["expected_family_key"]
    data["category"] = data["analysis_cohort"]
    data["error_type"] = data["mistake_type"]
    data["operation_family"] = data["mistake_type"]
    data["normalized_distance"] = data["normalized_edit_distance"]
    data["rank"] = data["first_relevant_rank"].astype(int)
    data["input_compact"] = data["input"].map(compact)
    data["query_length"] = data["input_compact"].str.len()
    data["query_length_band"] = data["query_length"].map(
        competitor_runner.query_length_band
    )
    data["shared_bigram_band"] = ""
    data["no_result"] = data["candidate_count"].eq(0).astype(int)
    return data


def normalize_cached_synthetic() -> pd.DataFrame:
    data = pd.read_csv(
        SYNTHETIC_CACHED,
        usecols=(
            "dataset",
            "case_id",
            "algorithm",
            "algorithm_name",
            "input",
            "input_compact",
            "expected",
            "expected_family_keys",
            "split",
            "primary_category",
            "primary_error_type",
            "operation_family",
            "effective_levenshtein",
            "normalized_levenshtein",
            "distance_band",
            "query_length",
            "query_length_band",
            "shared_bigrams",
            "shared_bigram_band",
            "first_relevant_rank",
            "hit_at_1",
            "hit_at_5",
            "hit_at_10",
            "hit_at_20",
            "no_result",
            "candidate_count",
            "latency_ms",
            "top_1",
        ),
    )
    data = data[data["algorithm"].isin(CACHED_ALGORITHMS)].copy()
    counts = data.groupby("algorithm").size()
    if not counts.eq(66257).all() or len(counts) != len(CACHED_ALGORITHMS):
        raise ValueError(f"cached synthetic coverage mismatch:\n{counts}")
    data["pair_key"] = [
        pair_key(query, expected)
        for query, expected in zip(data["input"], data["expected_family_keys"])
    ]
    data["category"] = data["primary_category"]
    data["error_type"] = data["primary_error_type"]
    data["edit_distance"] = data["effective_levenshtein"]
    data["normalized_distance"] = data["normalized_levenshtein"]
    data["rank"] = data["first_relevant_rank"].astype(int)
    return data


def load_current_a5_ocr() -> pd.DataFrame:
    path = (
        COMPETITOR_ARTIFACTS
        / "a5_ablation_ocr_464/full_algorithm_5.csv.gz"
    )
    if not path.exists():
        raise FileNotFoundError(f"current Algorithm 5 OCR result is not ready: {path}")
    data = normalize_new_rows(read_gzip_csv(path, NEW_RESULT_COLUMNS))
    data["algorithm"] = "algorithm_5_evidence_rescue"
    data["algorithm_name"] = DISPLAY_NAMES["algorithm_5_evidence_rescue"]
    return data


def load_current_a5_synthetic() -> pd.DataFrame:
    if not SYNTHETIC_A5_CURRENT.exists():
        raise FileNotFoundError(
            f"current Algorithm 5 synthetic result is not ready: {SYNTHETIC_A5_CURRENT}"
        )
    data = pd.read_csv(
        SYNTHETIC_A5_CURRENT,
        usecols=(
            "dataset",
            "case_id",
            "algorithm",
            "algorithm_name",
            "input",
            "input_compact",
            "expected",
            "expected_family_keys",
            "split",
            "primary_category",
            "primary_error_type",
            "operation_family",
            "effective_levenshtein",
            "normalized_levenshtein",
            "distance_band",
            "query_length",
            "query_length_band",
            "shared_bigrams",
            "shared_bigram_band",
            "first_relevant_rank",
            "hit_at_1",
            "hit_at_5",
            "hit_at_10",
            "hit_at_20",
            "no_result",
            "candidate_count",
            "latency_ms",
            "top_1",
        ),
    )
    data = data[data["algorithm"].eq("algorithm_5_evidence_rescue")].copy()
    if len(data) != 66257:
        raise ValueError(f"expected 66,257 current A5 rows, found {len(data)}")
    data["pair_key"] = [
        pair_key(query, expected)
        for query, expected in zip(data["input"], data["expected_family_keys"])
    ]
    data["category"] = data["primary_category"]
    data["error_type"] = data["primary_error_type"]
    data["edit_distance"] = data["effective_levenshtein"]
    data["normalized_distance"] = data["normalized_levenshtein"]
    data["rank"] = data["first_relevant_rank"].astype(int)
    data["algorithm_name"] = DISPLAY_NAMES["algorithm_5_evidence_rescue"]
    return data


def finalize_rows(data: pd.DataFrame, ocr_metadata: pd.DataFrame | None) -> pd.DataFrame:
    output = data.copy()
    if ocr_metadata is not None:
        output = output.drop(
            columns=[
                column
                for column in ("operation_profile", "query_length", "shared_bigrams")
                if column in output
            ],
            errors="ignore",
        ).merge(
            ocr_metadata,
            on="pair_key",
            how="left",
            validate="many_to_one",
        )
        if output["operation_profile"].isna().any():
            raise ValueError("OCR operation metadata did not join to every result")
    else:
        output["operation_profile"] = output["operation_family"]
        output["query_length"] = output["input_compact"].str.len()
        output["shared_bigrams"] = output["shared_bigram_band"].map(
            {
                "0_shared_bigrams": 0,
                "1_shared_bigram": 1,
                "2_3_shared_bigrams": 2,
                "4_plus_shared_bigrams": 4,
            }
        )
    for field in (
        "hit_at_1",
        "hit_at_5",
        "hit_at_10",
        "hit_at_20",
        "rank",
        "edit_distance",
        "query_length",
    ):
        output[field] = pd.to_numeric(output[field], errors="raise").astype(int)
    for field in ("normalized_distance", "latency_ms"):
        output[field] = pd.to_numeric(output[field], errors="raise").astype(float)
    output["algorithm_name"] = output["algorithm_name"].fillna(output["algorithm"])
    output["rank"] = pd.to_numeric(output["rank"], downcast="integer")
    output["edit_distance"] = pd.to_numeric(
        output["edit_distance"],
        downcast="integer",
    )
    output["query_length"] = pd.to_numeric(
        output["query_length"],
        downcast="integer",
    )
    output["shared_bigrams"] = pd.to_numeric(
        output["shared_bigrams"],
        errors="coerce",
        downcast="integer",
    )
    output["normalized_distance"] = pd.to_numeric(
        output["normalized_distance"],
        downcast="float",
    )
    output["latency_ms"] = pd.to_numeric(output["latency_ms"], downcast="float")
    for field in ("hit_at_1", "hit_at_5", "hit_at_10", "hit_at_20"):
        output[field] = pd.to_numeric(output[field], downcast="integer")
    for field in CATEGORY_COLUMNS:
        if field in output:
            output[field] = output[field].astype("category")
    return output


OUTCOME_COLUMNS = (
    "case_id",
    "algorithm",
    "algorithm_name",
    "first_relevant_rank",
    "hit_at_1",
    "hit_at_5",
    "hit_at_10",
    "hit_at_20",
    "no_result",
    "candidate_count",
    "latency_ms",
)


def compact_outcomes(data: pd.DataFrame) -> pd.DataFrame:
    output = data.rename(columns={"first_relevant_rank": "rank"}).copy()
    for field in (
        "rank",
        "hit_at_1",
        "hit_at_5",
        "hit_at_10",
        "hit_at_20",
        "no_result",
        "candidate_count",
    ):
        output[field] = pd.to_numeric(output[field], downcast="integer")
    output["latency_ms"] = pd.to_numeric(output["latency_ms"], downcast="float")
    output["algorithm"] = output["algorithm"].astype(ALGORITHM_DTYPE)
    output["algorithm_name"] = output["algorithm_name"].astype(
        ALGORITHM_NAME_DTYPE
    )
    return output[
        [
            "case_index",
            "algorithm",
            "algorithm_name",
            "rank",
            "hit_at_1",
            "hit_at_5",
            "hit_at_10",
            "hit_at_20",
            "no_result",
            "candidate_count",
            "latency_ms",
        ]
    ]


def map_case_ids(
    data: pd.DataFrame,
    metadata: pd.DataFrame,
) -> pd.DataFrame:
    positions = metadata.set_index("case_id")["case_index"]
    data = data.copy()
    data["case_index"] = data["case_id"].map(positions)
    if data["case_index"].isna().any():
        missing = data.loc[data["case_index"].isna(), "case_id"].head().tolist()
        raise ValueError(f"case IDs did not map to locked metadata: {missing}")
    data["case_index"] = data["case_index"].astype(np.int32)
    return data


def load_new_outcomes(dataset: str, metadata: pd.DataFrame) -> pd.DataFrame:
    root = COMPETITOR_ARTIFACTS / dataset
    files = sorted(root.glob("*.csv.gz"))
    expected = len(competitor_runner.EVALUATED_COMPETITORS)
    if len(files) != expected:
        raise ValueError(
            f"{dataset}: expected {expected} competitor files, found {len(files)}"
        )
    frames = []
    for path in files:
        frame = read_gzip_csv(path, OUTCOME_COLUMNS)
        frame = map_case_ids(frame, metadata)
        frames.append(compact_outcomes(frame))
    return pd.concat(frames, ignore_index=True)


def load_cached_ocr_outcomes(metadata: pd.DataFrame) -> pd.DataFrame:
    data = pd.read_csv(
        OCR_CACHED,
        usecols=(
            "experiment",
            "case_id",
            "input",
            "expected_family_key",
            "scored_case",
            "algorithm",
            "first_relevant_rank",
            "hit_at_1",
            "hit_at_5",
            "hit_at_10",
            "hit_at_20",
            "candidate_count",
            "latency_ms",
        ),
    )
    data = data[
        data["experiment"].eq("retrieval")
        & data["algorithm"].isin(CACHED_ALGORITHMS)
        & data["scored_case"].eq(1)
    ].copy()
    data["pair_key"] = [
        pair_key(query, expected)
        for query, expected in zip(data["input"], data["expected_family_key"])
    ]
    data = data.drop_duplicates(["algorithm", "pair_key"], keep="first")
    positions = metadata.set_index("pair_key")["case_index"]
    data["case_index"] = data["pair_key"].map(positions)
    data["algorithm_name"] = data["algorithm"].map(DISPLAY_NAMES)
    data["no_result"] = data["candidate_count"].eq(0).astype(int)
    counts = data.groupby("algorithm").size()
    if len(counts) != 10 or not counts.eq(464).all():
        raise ValueError(f"cached OCR outcome mismatch:\n{counts}")
    return compact_outcomes(data)


def load_cached_synthetic_outcomes(metadata: pd.DataFrame) -> pd.DataFrame:
    data = pd.read_csv(
        SYNTHETIC_CACHED,
        usecols=(
            "case_id",
            "algorithm",
            "algorithm_name",
            "first_relevant_rank",
            "hit_at_1",
            "hit_at_5",
            "hit_at_10",
            "hit_at_20",
            "no_result",
            "candidate_count",
            "latency_ms",
        ),
    )
    data = data[data["algorithm"].isin(CACHED_ALGORITHMS)].copy()
    data = map_case_ids(data, metadata)
    counts = data.groupby("algorithm").size()
    if len(counts) != 10 or not counts.eq(66257).all():
        raise ValueError(f"cached synthetic outcome mismatch:\n{counts}")
    return compact_outcomes(data)


def load_a5_outcomes(dataset: str, metadata: pd.DataFrame) -> pd.DataFrame:
    if dataset == "ocr_464":
        path = (
            COMPETITOR_ARTIFACTS
            / "a5_ablation_ocr_464/full_algorithm_5.csv.gz"
        )
        data = read_gzip_csv(path, OUTCOME_COLUMNS)
    else:
        data = pd.read_csv(
            SYNTHETIC_A5_CURRENT,
            usecols=OUTCOME_COLUMNS,
        )
        data = data[data["algorithm"].eq("algorithm_5_evidence_rescue")].copy()
        if len(data) != len(metadata):
            raise ValueError(
                f"expected {len(metadata):,} current A5 synthetic rows, "
                f"found {len(data):,}"
            )
    data = map_case_ids(data, metadata)
    data["algorithm"] = "algorithm_5_evidence_rescue"
    data["algorithm_name"] = DISPLAY_NAMES["algorithm_5_evidence_rescue"]
    return compact_outcomes(data)


def combine_outcomes(
    metadata: pd.DataFrame,
    outcomes: Sequence[pd.DataFrame],
) -> pd.DataFrame:
    merged = pd.concat(outcomes, ignore_index=True)
    merged = merged.merge(
        metadata,
        on="case_index",
        how="left",
        validate="many_to_one",
    )
    if merged["pair_key"].isna().any():
        raise ValueError("outcome rows did not join to case metadata")
    return merged


def load_all_rows() -> tuple[pd.DataFrame, pd.DataFrame]:
    ocr_metadata = optimize_metadata(load_ocr_case_metadata())
    synthetic_metadata = optimize_metadata(load_synthetic_case_metadata())
    ocr = combine_outcomes(
        ocr_metadata,
        (
            load_cached_ocr_outcomes(ocr_metadata),
            load_new_outcomes("ocr_464", ocr_metadata),
            load_a5_outcomes("ocr_464", ocr_metadata),
        ),
    )
    synthetic = combine_outcomes(
        synthetic_metadata,
        (
            load_cached_synthetic_outcomes(synthetic_metadata),
            load_new_outcomes("synthetic_66257", synthetic_metadata),
            load_a5_outcomes("synthetic_66257", synthetic_metadata),
        ),
    )
    for name, data, expected in (
        ("ocr", ocr, 464),
        ("synthetic", synthetic, 66257),
    ):
        counts = data.groupby("algorithm").size()
        expected_systems = len(ALL_ALGORITHM_IDS)
        if len(counts) != expected_systems or not counts.eq(expected).all():
            raise ValueError(f"{name} system coverage mismatch:\n{counts}")
        expected_pairs = set(
            data[data["algorithm"].eq("algorithm_5_evidence_rescue")][
                "pair_key"
            ].astype(str)
        )
        for algorithm, group in data.groupby("algorithm"):
            if set(group["pair_key"].astype(str)) != expected_pairs:
                raise ValueError(f"{name}/{algorithm}: paired cases do not match")
    return ocr, synthetic


def inventory_lookup() -> pd.DataFrame:
    inventory = pd.read_csv(COMPETITOR_RESULTS / "competitor_inventory.csv")
    expected = {item.algorithm for item in competitor_runner.ALL_COMPETITORS}
    actual = set(inventory["algorithm"].astype(str))
    if len(inventory) != len(expected) or actual != expected:
        raise ValueError(
            "competitor inventory is stale: regenerate it with "
            "run_competitor_benchmark.py --aggregate-only"
        )
    return inventory


def method_family_map() -> dict[str, str]:
    output = {
        "baseline_exact_prefix": "exact and prefix",
        "baseline_levenshtein": "edit distance",
        "baseline_jaro_winkler": "character similarity",
        "baseline_char_3gram_tfidf": "sparse character retrieval",
        "baseline_rapidfuzz_token_ratio": "token-aware similarity",
        "baseline_phonetic": "phonetic",
        "algorithm_1_current_app": "project algorithm",
        "algorithm_2_external_fast": "project algorithm",
        "algorithm_3_rank_fusion": "project algorithm",
        "algorithm_4_family_rescue": "project algorithm",
        "algorithm_5_evidence_rescue": "project algorithm",
    }
    inventory = inventory_lookup()
    output.update(
        inventory[inventory["status"].eq("evaluated")]
        .set_index("algorithm")["family"]
        .to_dict()
    )
    return output


def wilson_interval(successes: int, count: int, z: float = 1.95996398454) -> tuple[float, float]:
    proportion = successes / count
    denominator = 1 + z * z / count
    center = (proportion + z * z / (2 * count)) / denominator
    spread = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / count
            + z * z / (4 * count * count)
        )
        / denominator
    )
    return center - spread, center + spread


def percentile(values: Sequence[float], fraction: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=float), fraction))


def preparation_time_lookup(dataset: str) -> dict[str, float]:
    """Read one-time index preparation from each system's canonical run."""

    output: dict[str, float] = {}
    if dataset == "ocr_464":
        cached = pd.read_csv(
            LEGACY_RETRIEVAL_METRICS,
            usecols=("experiment", "algorithm", "scope", "preparation_ms"),
        )
        cached = cached[
            cached["experiment"].eq("retrieval")
            & cached["scope"].eq("primary_fair_unique")
            & cached["algorithm"].isin(CACHED_ALGORITHMS)
        ]
    else:
        cached = pd.read_csv(
            SYNTHETIC_RETRIEVAL_METRICS,
            usecols=(
                "algorithm",
                "denominator",
                "split",
                "dimension",
                "preparation_ms",
            ),
        )
        cached = cached[
            cached["denominator"].eq("primary_clean_unique_pair")
            & cached["split"].eq("all")
            & cached["dimension"].eq("overall")
            & cached["algorithm"].isin(CACHED_ALGORITHMS)
        ]
    output.update(
        cached.set_index("algorithm")["preparation_ms"].astype(float).to_dict()
    )

    for competitor in competitor_runner.EVALUATED_COMPETITORS:
        metadata = (
            COMPETITOR_ARTIFACTS
            / dataset
            / f"{competitor.algorithm}.csv.metadata.json"
        )
        values = json.loads(metadata.read_text(encoding="utf-8"))
        output[competitor.algorithm] = float(values["preparation_ms"])

    a5_metadata = (
        COMPETITOR_ARTIFACTS
        / f"a5_ablation_{dataset}"
        / "full_algorithm_5.csv.metadata.json"
    )
    values = json.loads(a5_metadata.read_text(encoding="utf-8"))
    output["algorithm_5_evidence_rescue"] = float(values["preparation_ms"])
    return output


def overall_metrics(data: pd.DataFrame) -> pd.DataFrame:
    families = method_family_map()
    dataset = str(data["dataset"].iloc[0])
    preparation = preparation_time_lookup(dataset)
    rows = []
    for algorithm, group in data.groupby("algorithm", sort=False):
        count = len(group)
        hit1 = int(group["hit_at_1"].sum())
        hit20 = int(group["hit_at_20"].sum())
        h1_low, h1_high = wilson_interval(hit1, count)
        h20_low, h20_high = wilson_interval(hit20, count)
        rows.append(
            {
                "dataset": group["dataset"].iloc[0],
                "algorithm": algorithm,
                "algorithm_name": group["algorithm_name"].iloc[0],
                "method_family": families.get(algorithm, "other"),
                "cases": count,
                "hit_at_1": hit1 / count,
                "hit_at_1_ci_low": h1_low,
                "hit_at_1_ci_high": h1_high,
                "hit_at_5": group["hit_at_5"].mean(),
                "hit_at_10": group["hit_at_10"].mean(),
                "hit_at_20": hit20 / count,
                "hit_at_20_ci_low": h20_low,
                "hit_at_20_ci_high": h20_high,
                "mrr_at_20": np.where(
                    group["rank"].to_numpy() <= 20,
                    1 / group["rank"].to_numpy(),
                    0,
                ).mean(),
                "failure_count": count - hit20,
                "no_result_rate": group["no_result"].mean(),
                "mean_candidate_count": group["candidate_count"].mean(),
                "preparation_ms": preparation.get(algorithm, math.nan),
                "mean_latency_ms": group["latency_ms"].mean(),
                "median_latency_ms": group["latency_ms"].median(),
                "p95_latency_ms": percentile(group["latency_ms"], 0.95),
            }
        )
    output = pd.DataFrame(rows)
    return output.sort_values(
        ["dataset", "hit_at_1", "hit_at_20", "mrr_at_20"],
        ascending=[True, False, False, False],
    )


def metric_distribution_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    """Summarize the complete system distribution without hiding extremes."""

    definitions = (
        ("hit_at_1", "Hit@1", "higher"),
        ("hit_at_5", "Hit@5", "higher"),
        ("hit_at_20", "Hit@20", "higher"),
        ("mrr_at_20", "MRR@20", "higher"),
        ("no_result_rate", "No-result rate", "lower"),
        ("preparation_ms", "Preparation time (ms)", "lower"),
        ("median_latency_ms", "Median measured time/query (ms)", "lower"),
        ("p95_latency_ms", "P95 measured time/query (ms)", "lower"),
    )
    rows = []
    for dataset, frame in metrics.groupby("dataset", observed=True):
        for field, metric_name, direction in definitions:
            valid = frame[np.isfinite(frame[field])].copy()
            if valid.empty:
                continue
            best_index = (
                valid[field].idxmax()
                if direction == "higher"
                else valid[field].idxmin()
            )
            worst_index = (
                valid[field].idxmin()
                if direction == "higher"
                else valid[field].idxmax()
            )
            rows.append(
                {
                    "dataset": dataset,
                    "metric": metric_name,
                    "direction": direction,
                    "systems": len(valid),
                    "best_system": valid.loc[best_index, "algorithm_name"],
                    "best_value": valid.loc[best_index, field],
                    "worst_system": valid.loc[worst_index, "algorithm_name"],
                    "worst_value": valid.loc[worst_index, field],
                    "mean": valid[field].mean(),
                    "median": valid[field].median(),
                    "standard_deviation": valid[field].std(ddof=1),
                }
            )
    return pd.DataFrame(rows)


def runtime_environment() -> pd.DataFrame:
    """Record the exact numerical and retrieval packages used by this run."""

    packages = (
        ("Python", None),
        ("NumPy", "numpy"),
        ("pandas", "pandas"),
        ("SciPy", "scipy"),
        ("scikit-learn", "scikit-learn"),
        ("RapidFuzz", "rapidfuzz"),
        ("jellyfish", "jellyfish"),
        ("symspellpy", "symspellpy"),
        ("rank-bm25", "rank-bm25"),
        ("hnswlib", "hnswlib"),
        ("PyTorch", "torch"),
        ("Transformers", "transformers"),
    )
    rows = [
            {
                "software": display_name,
                "version": (
                    sys.version.split()[0]
                    if distribution is None
                    else importlib.metadata.version(distribution)
                ),
            }
            for display_name, distribution in packages
    ]

    def sysctl_value(name: str) -> str:
        result = subprocess.run(
            ("sysctl", "-n", name),
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    package_lock = json.loads(
        (BENCHMARK_ROOT / "package-lock.json").read_text(encoding="utf-8")
    )
    node_version = subprocess.run(
        ("node", "--version"),
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    memory_bytes = sysctl_value("hw.memsize")
    rows.extend(
        [
            {
                "software": "Node.js",
                "version": node_version.removeprefix("v"),
            },
            {
                "software": "Fuse.js",
                "version": package_lock["packages"]["node_modules/fuse.js"][
                    "version"
                ],
            },
            {
                "software": "FlexSearch",
                "version": package_lock["packages"][
                    "node_modules/flexsearch"
                ]["version"],
            },
            {
                "software": "Operating system",
                "version": platform.platform(),
            },
            {
                "software": "CPU",
                "version": sysctl_value("machdep.cpu.brand_string")
                or platform.processor()
                or platform.machine(),
            },
            {
                "software": "Logical CPU cores",
                "version": str(sysctl_value("hw.logicalcpu") or "unknown"),
            },
            {
                "software": "Memory",
                "version": (
                    f"{int(memory_bytes) / (1024 ** 3):.1f} GiB"
                    if memory_bytes.isdigit()
                    else "unknown"
                ),
            },
        ]
    )
    return pd.DataFrame(rows)


def dataset_fingerprints() -> pd.DataFrame:
    """Fingerprint the exact source files behind the two locked denominators."""

    definitions = (
        (
            "OCR source cases",
            OCR_CASES,
            595,
            464,
            "Accepted, scored, collision-free unique query-target pairs",
        ),
        (
            "Synthetic clean core",
            competitor_runner.DEFAULT_SYNTHETIC_CASES,
            66257,
            66257,
            "All unique catalog-resolvable query-target pairs",
        ),
    )
    rows = []
    for dataset, path, source_rows, evaluated_pairs, selection in definitions:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        rows.append(
            {
                "dataset": dataset,
                "source_rows": source_rows,
                "evaluated_pairs": evaluated_pairs,
                "selection": selection,
                "sha256": digest.hexdigest(),
            }
        )
    return pd.DataFrame(rows)


def dense_model_configuration() -> pd.DataFrame:
    """Record checkpoint and index settings shared by dense competitors."""

    rows = []
    for algorithm, model_name in competitor_runner.DENSE_MODELS.items():
        rows.append(
            {
                "algorithm": algorithm,
                "algorithm_name": DISPLAY_NAMES[algorithm],
                "model_name": model_name,
                "model_revision": competitor_runner.DENSE_MODEL_REVISIONS[
                    model_name
                ],
                "pooling": "CLS before pooler, then L2 normalization",
                "dimensions": 768,
                "hnsw_m": 32,
                "hnsw_ef_construction": 400,
                "hnsw_ef_search": 500,
                "hnsw_seed": 20260723,
            }
        )
    return pd.DataFrame(rows)


def accuracy_latency_pareto(metrics: pd.DataFrame) -> pd.DataFrame:
    """Return systems not dominated on Hit@1 and measured time per query."""

    rows = []
    for dataset, frame in metrics.groupby("dataset", observed=True):
        frame = frame[
            np.isfinite(frame["hit_at_1"])
            & np.isfinite(frame["median_latency_ms"])
        ].copy()
        for row in frame.itertuples():
            dominated = (
                frame["median_latency_ms"].le(row.median_latency_ms)
                & frame["hit_at_1"].ge(row.hit_at_1)
                & (
                    frame["median_latency_ms"].lt(row.median_latency_ms)
                    | frame["hit_at_1"].gt(row.hit_at_1)
                )
            ).any()
            if not dominated:
                rows.append(
                    {
                        "dataset": dataset,
                        "algorithm": row.algorithm,
                        "algorithm_name": row.algorithm_name,
                        "hit_at_1": row.hit_at_1,
                        "hit_at_20": row.hit_at_20,
                        "median_latency_ms": row.median_latency_ms,
                        "p95_latency_ms": row.p95_latency_ms,
                        "preparation_ms": row.preparation_ms,
                    }
                )
    return pd.DataFrame(rows).sort_values(
        ["dataset", "median_latency_ms", "hit_at_1"],
        ascending=[True, True, False],
    )


def exact_mcnemar(reference_only: int, comparison_only: int) -> float:
    discordant = reference_only + comparison_only
    if discordant == 0:
        return 1.0
    return float(
        binomtest(
            min(reference_only, comparison_only),
            discordant,
            0.5,
            alternative="two-sided",
        ).pvalue
    )


def paired_difference_interval(
    reference_only: int,
    comparison_only: int,
    ties: int,
    *,
    seed: int,
    draws: int = 20000,
) -> tuple[float, float]:
    count = reference_only + comparison_only + ties
    rng = np.random.default_rng(seed)
    samples = rng.multinomial(
        count,
        [
            reference_only / count,
            comparison_only / count,
            ties / count,
        ],
        size=draws,
    )
    differences = (samples[:, 0] - samples[:, 1]) / count
    return tuple(float(value) for value in np.quantile(differences, [0.025, 0.975]))


def holm_adjust(p_values: Sequence[float]) -> np.ndarray:
    """Return Holm family-wise-error adjusted p-values."""

    values = np.asarray(p_values, dtype=float)
    order = np.argsort(values)
    adjusted_sorted = np.maximum.accumulate(
        (len(values) - np.arange(len(values))) * values[order]
    )
    adjusted = np.empty_like(values)
    adjusted[order] = np.minimum(adjusted_sorted, 1.0)
    return adjusted


def paired_comparisons(data: pd.DataFrame) -> pd.DataFrame:
    reference_name = "algorithm_5_evidence_rescue"
    reference = (
        data[data["algorithm"].eq(reference_name)]
        .set_index("pair_key")
        .sort_index()
    )
    rows = []
    for algorithm, comparison in data.groupby("algorithm"):
        if algorithm == reference_name:
            continue
        comparison = comparison.set_index("pair_key").loc[reference.index]
        row: dict[str, Any] = {
            "dataset": data["dataset"].iloc[0],
            "reference_algorithm": reference_name,
            "comparison_algorithm": algorithm,
            "comparison_name": comparison["algorithm_name"].iloc[0],
            "cases": len(reference),
        }
        for cutoff in (1, 20):
            field = f"hit_at_{cutoff}"
            ref = reference[field].to_numpy(int)
            comp = comparison[field].to_numpy(int)
            reference_only = int(((ref == 1) & (comp == 0)).sum())
            comparison_only = int(((ref == 0) & (comp == 1)).sum())
            ties = len(ref) - reference_only - comparison_only
            low, high = paired_difference_interval(
                reference_only,
                comparison_only,
                ties,
                seed=20260723 + cutoff,
            )
            row.update(
                {
                    f"a5_only_hit_at_{cutoff}": reference_only,
                    f"comparison_only_hit_at_{cutoff}": comparison_only,
                    f"net_a5_wins_hit_at_{cutoff}": (
                        reference_only - comparison_only
                    ),
                    f"difference_hit_at_{cutoff}": (
                        reference_only - comparison_only
                    )
                    / len(ref),
                    f"difference_ci_low_hit_at_{cutoff}": low,
                    f"difference_ci_high_hit_at_{cutoff}": high,
                    f"mcnemar_p_hit_at_{cutoff}": exact_mcnemar(
                        reference_only,
                        comparison_only,
                    ),
                    f"matched_odds_ratio_hit_at_{cutoff}": (
                        (reference_only + 0.5) / (comparison_only + 0.5)
                    ),
                }
            )
        rows.append(row)
    output = pd.DataFrame(rows)
    for cutoff in (1, 20):
        output[f"mcnemar_holm_p_hit_at_{cutoff}"] = holm_adjust(
            output[f"mcnemar_p_hit_at_{cutoff}"]
        )
    return output.sort_values("difference_hit_at_1", ascending=False)


def grouped_metrics(
    data: pd.DataFrame,
    dimensions: Sequence[str],
) -> pd.DataFrame:
    rows = []
    for keys, frame in data.groupby(
        ["algorithm", *dimensions],
        dropna=False,
        observed=True,
    ):
        if not isinstance(keys, tuple):
            keys = (keys,)
        algorithm, *groups = keys
        values = dict(zip(dimensions, groups))
        rows.append(
            {
                "dataset": frame["dataset"].iloc[0],
                "algorithm": algorithm,
                "algorithm_name": frame["algorithm_name"].iloc[0],
                **values,
                "cases": len(frame),
                "hit_at_1": frame["hit_at_1"].mean(),
                "hit_at_20": frame["hit_at_20"].mean(),
                "failures_at_20": int((1 - frame["hit_at_20"]).sum()),
            }
        )
    return pd.DataFrame(rows)


def all_system_slices(data: pd.DataFrame) -> pd.DataFrame:
    """Return one normalized table for every supported error-analysis dimension."""

    dimensions = (
        "split",
        "category",
        "error_type",
        "operation_family",
        "operation_profile",
        "distance_band",
        "query_length_band",
        "shared_bigram_band",
    )
    frames = []
    for dimension in dimensions:
        frame = grouped_metrics(data, [dimension]).rename(
            columns={dimension: "group"}
        )
        frame.insert(3, "dimension", dimension)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def a5_failure_taxonomy(data: pd.DataFrame) -> pd.DataFrame:
    """Separate subgroup difficulty from each subgroup's share of A5 misses."""

    a5 = data[data["algorithm"].eq("algorithm_5_evidence_rescue")]
    total_failures = int((1 - a5["hit_at_20"]).sum())
    rows = []
    for dimension in (
        "category",
        "error_type",
        "operation_family",
        "operation_profile",
        "distance_band",
        "query_length_band",
        "shared_bigram_band",
    ):
        for group_name, group in a5.groupby(
            dimension,
            observed=True,
            dropna=False,
        ):
            failures = int((1 - group["hit_at_20"]).sum())
            rows.append(
                {
                    "dataset": data["dataset"].iloc[0],
                    "dimension": dimension,
                    "group": group_name,
                    "cases": len(group),
                    "hit_at_1": group["hit_at_1"].mean(),
                    "hit_at_20": group["hit_at_20"].mean(),
                    "failure_count": failures,
                    "failure_rate": failures / len(group),
                    "failure_share": (
                        failures / total_failures if total_failures else 0.0
                    ),
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["dimension", "failure_count", "failure_rate"],
        ascending=[True, False, False],
    )


def controlled_variant_sensitivity(metrics: pd.DataFrame) -> pd.DataFrame:
    """Compare configurations within one implementation family."""

    inventory = inventory_lookup()
    evaluated = (
        inventory[inventory["status"].eq("evaluated")]
        .set_index("algorithm")[["component_group", "family"]]
    )

    def sensitivity_group(algorithm: str) -> str:
        component_group = evaluated.loc[algorithm, "component_group"]
        family = evaluated.loc[algorithm, "family"]
        if component_group == "node_search":
            return "Fuse.js" if algorithm.startswith("fuse_") else "FlexSearch"
        if component_group == "hybrid":
            return str(family).title()
        return COMPONENT_GROUP_NAMES.get(component_group, str(component_group))

    rows = []
    for dataset, dataset_metrics in metrics.groupby("dataset", observed=True):
        external = dataset_metrics[
            ~dataset_metrics["algorithm"].isin(PROJECT_ALGORITHMS)
        ].copy()
        external["component_group"] = external["algorithm"].map(
            lambda algorithm: (
                sensitivity_group(algorithm)
                if algorithm in evaluated.index
                else math.nan
            )
        )
        for component_group, group in external.dropna(
            subset=["component_group"]
        ).groupby("component_group", observed=True):
            if len(group) < 2:
                continue
            best_h1 = float(group["hit_at_1"].max())
            best_h20 = float(group["hit_at_20"].max())
            for row in group.sort_values(
                ["hit_at_1", "hit_at_20"],
                ascending=False,
            ).itertuples():
                rows.append(
                    {
                        "dataset": dataset,
                        "component_group": component_group,
                        "algorithm": row.algorithm,
                        "algorithm_name": row.algorithm_name,
                        "hit_at_1": row.hit_at_1,
                        "hit_at_20": row.hit_at_20,
                        "delta_from_group_best_hit_at_1": row.hit_at_1 - best_h1,
                        "delta_from_group_best_hit_at_20": row.hit_at_20 - best_h20,
                    }
                )
    return pd.DataFrame(rows)


def composite_component_study(metrics: pd.DataFrame) -> pd.DataFrame:
    """Report complete composites beside their measured component removals."""

    studies = {
        "BioSyn sparse-dense mixture": {
            "reference": "biosyn_hybrid_w50",
            "algorithms": (
                ("sapbert_dense_hnsw", "Dense component only"),
                ("biosyn_hybrid_w25", "25% sparse, 75% dense"),
                ("biosyn_hybrid_w50", "50% sparse, 50% dense"),
                ("biosyn_hybrid_w75", "75% sparse, 25% dense"),
                ("baseline_char_3gram_tfidf", "Sparse component only"),
            ),
        },
        "xMEN rank fusion": {
            "reference": "xmen_sapbert_tfidf_rrf",
            "algorithms": (
                ("sapbert_dense_hnsw", "Dense component only"),
                ("baseline_char_3gram_tfidf", "Sparse component only"),
                ("xmen_sapbert_tfidf_rrf", "Complete reciprocal-rank fusion"),
            ),
        },
        "preon staged normalizer": {
            "reference": "preon_default",
            "algorithms": (
                ("preon_default", "Complete exact, token, partial cascade"),
                ("preon_without_token", "Token stage removed"),
                ("preon_without_partial", "Partial edit stage removed"),
            ),
        },
    }
    rows = []
    indexed = metrics.set_index(["dataset", "algorithm"])
    for dataset in metrics["dataset"].unique():
        for study, specification in studies.items():
            reference = indexed.loc[(dataset, specification["reference"])]
            for algorithm, role in specification["algorithms"]:
                if (dataset, algorithm) not in indexed.index:
                    continue
                result = indexed.loc[(dataset, algorithm)]
                rows.append(
                    {
                        "dataset": dataset,
                        "study": study,
                        "configuration": result["algorithm_name"],
                        "component_role": role,
                        "hit_at_1": result["hit_at_1"],
                        "hit_at_20": result["hit_at_20"],
                        "delta_from_complete_hit_at_1": (
                            result["hit_at_1"] - reference["hit_at_1"]
                        ),
                        "delta_from_complete_hit_at_20": (
                            result["hit_at_20"] - reference["hit_at_20"]
                        ),
                    }
                )
    return pd.DataFrame(rows)


def oracle_coverage(data: pd.DataFrame) -> pd.DataFrame:
    """Measure complementarity without claiming an implementable oracle."""

    pivot = data.pivot(
        index="pair_key",
        columns="algorithm",
        values="hit_at_20",
    )
    external = [
        column for column in pivot if column not in PROJECT_ALGORITHMS
    ]
    project = [column for column in pivot if column in PROJECT_ALGORITHMS]
    a5 = pivot["algorithm_5_evidence_rescue"].astype(bool)
    external_any = pivot[external].astype(bool).any(axis=1)
    project_any = pivot[project].astype(bool).any(axis=1)
    rows = [
        ("Algorithm 5", a5),
        ("Any external or classical system", external_any),
        ("Algorithm 5 plus any external system", a5 | external_any),
        ("Any project Algorithm 1-5", project_any),
        ("Any measured system", pivot.astype(bool).any(axis=1)),
    ]
    return pd.DataFrame(
        [
            {
                "dataset": data["dataset"].iloc[0],
                "system_set": name,
                "cases": len(values),
                "hit_at_20": values.mean(),
                "failures": int((~values).sum()),
            }
            for name, values in rows
        ]
    )


def ocr_top1_lookup(algorithm: str) -> pd.Series:
    """Load display output only for the small OCR example tables."""

    if algorithm == "algorithm_5_evidence_rescue":
        path = (
            COMPETITOR_ARTIFACTS
            / "a5_ablation_ocr_464/full_algorithm_5.csv.gz"
        )
        data = read_gzip_csv(
            path,
            ("input", "expected_family_keys", "top_1"),
        )
    elif algorithm in {
        item.algorithm for item in competitor_runner.EVALUATED_COMPETITORS
    }:
        data = read_gzip_csv(
            COMPETITOR_ARTIFACTS / "ocr_464" / f"{algorithm}.csv.gz",
            ("input", "expected_family_keys", "top_1"),
        )
    else:
        data = pd.read_csv(
            OCR_CACHED,
            usecols=(
                "experiment",
                "algorithm",
                "input",
                "expected_family_key",
                "scored_case",
                "top_1",
            ),
        )
        data = data[
            data["experiment"].eq("retrieval")
            & data["algorithm"].eq(algorithm)
            & data["scored_case"].eq(1)
        ].rename(columns={"expected_family_key": "expected_family_keys"})
    data["pair_key"] = [
        pair_key(query, expected)
        for query, expected in zip(
            data["input"],
            data["expected_family_keys"],
        )
    ]
    return data.drop_duplicates("pair_key").set_index("pair_key")["top_1"]


def comparative_ocr_examples(data: pd.DataFrame) -> pd.DataFrame:
    """Show concrete paired wins, losses, and common failures."""

    comparisons = (
        "algorithm_4_family_rescue",
        "baseline_jaro_winkler",
        "damerau_levenshtein",
        "jaro_similarity",
        "symspell_frequency_ed3",
        "preon_default",
    )
    a5 = (
        data[data["algorithm"].eq("algorithm_5_evidence_rescue")]
        .set_index("pair_key")
        .sort_index()
    )
    a5_top = ocr_top1_lookup("algorithm_5_evidence_rescue")
    rows = []
    for algorithm in comparisons:
        comparison = (
            data[data["algorithm"].eq(algorithm)]
            .set_index("pair_key")
            .loc[a5.index]
        )
        comparison_top = ocr_top1_lookup(algorithm)
        scenarios = {
            "Algorithm 5 only recovers within top 20": (
                a5["hit_at_20"].eq(1) & comparison["hit_at_20"].eq(0)
            ),
            "Competitor only recovers within top 20": (
                a5["hit_at_20"].eq(0) & comparison["hit_at_20"].eq(1)
            ),
            "Both miss top 20": (
                a5["hit_at_20"].eq(0) & comparison["hit_at_20"].eq(0)
            ),
        }
        for scenario, mask in scenarios.items():
            selected = a5[mask].sort_values(
                ["edit_distance", "normalized_distance", "pair_key"]
            ).head(5)
            for pair, source in selected.iterrows():
                other = comparison.loc[pair]
                rows.append(
                    {
                        "comparison_algorithm": algorithm,
                        "comparison_name": other["algorithm_name"],
                        "scenario": scenario,
                        "input": source["input"],
                        "expected": source["expected_family_name"],
                        "edit_distance": source["edit_distance"],
                        "operation_profile": source["operation_profile"],
                        "shared_bigrams": source["shared_bigrams"],
                        "a5_rank": source["rank"],
                        "a5_top_1": a5_top.get(pair, ""),
                        "comparison_rank": other["rank"],
                        "comparison_top_1": comparison_top.get(pair, ""),
                    }
                )
    return pd.DataFrame(rows)


def a5_remaining_ocr_failures(data: pd.DataFrame) -> pd.DataFrame:
    """List every A5 top-20 miss and whether another measured method retrieves it."""

    a5 = (
        data[data["algorithm"].eq("algorithm_5_evidence_rescue")]
        .set_index("pair_key")
        .sort_index()
    )
    failures = a5[a5["hit_at_20"].eq(0)].copy()
    external = data[
        ~data["algorithm"].isin(PROJECT_ALGORITHMS)
    ].pivot(
        index="pair_key",
        columns="algorithm",
        values="hit_at_20",
    )
    names = {
        algorithm: DISPLAY_NAMES[algorithm]
        for algorithm in external.columns
    }
    top1 = ocr_top1_lookup("algorithm_5_evidence_rescue")
    rows = []
    for pair, row in failures.iterrows():
        successful = [
            names[algorithm]
            for algorithm, value in external.loc[pair].items()
            if int(value) == 1
        ]
        rows.append(
            {
                "case_id": row["case_id"],
                "input": row["input"],
                "expected": row["expected_family_name"],
                "a5_top_1": top1.get(pair, ""),
                "edit_distance": row["edit_distance"],
                "normalized_distance": row["normalized_distance"],
                "operation_profile": row["operation_profile"],
                "query_length": row["query_length"],
                "shared_bigrams": row["shared_bigrams"],
                "analysis_cohort": row["category"],
                "external_recovery_count": len(successful),
                "external_systems_recovering": "; ".join(successful),
                "evidence_class": (
                    "recoverable by at least one measured external rule"
                    if successful
                    else "not recovered by any measured external rule"
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["external_recovery_count", "edit_distance", "input"],
        ascending=[False, True, True],
    )


def a5_feature_correlations(
    ocr: pd.DataFrame,
    synthetic: pd.DataFrame,
) -> pd.DataFrame:
    """Compute rank correlations for Algorithm 5 inputs and outcomes."""

    rows: list[dict[str, Any]] = []
    fields = list(CORRELATION_FEATURES)
    for dataset, data in (("ocr_464", ocr), ("synthetic_66257", synthetic)):
        frame = data[data["algorithm"].eq("algorithm_5_evidence_rescue")][
            fields
        ].astype(float)
        matrix = frame.corr(method="spearman")
        for feature_x in fields:
            for feature_y in fields:
                rows.append(
                    {
                        "dataset": dataset,
                        "feature_x": feature_x,
                        "feature_x_name": CORRELATION_FEATURES[feature_x],
                        "feature_y": feature_y,
                        "feature_y_name": CORRELATION_FEATURES[feature_y],
                        "spearman_rho": matrix.loc[feature_x, feature_y],
                    }
                )
    return pd.DataFrame(rows)


def recovery_or_nan(frame: pd.DataFrame, mask: pd.Series, field: str) -> float:
    selected = frame[mask]
    return float(selected[field].mean()) if len(selected) else math.nan


def system_failure_drivers(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for algorithm, group in data.groupby("algorithm"):
        distance_low = group["edit_distance"].le(3)
        distance_high = group["edit_distance"].ge(4)
        no_bigram = group["shared_bigrams"].eq(0)
        several_bigrams = group["shared_bigrams"].ge(2)
        short = group["query_length"].le(4)
        longer = group["query_length"].ge(8)
        mixed = group["operation_profile"].eq("mixed_operations")
        isolated = ~mixed
        extreme = group["normalized_distance"].gt(0.60)
        standard = group["normalized_distance"].le(0.40)
        correlation = (
            spearmanr(
                group["edit_distance"],
                group["hit_at_20"],
            ).statistic
            if group["hit_at_20"].nunique() > 1
            else math.nan
        )
        rows.append(
            {
                "dataset": group["dataset"].iloc[0],
                "algorithm": algorithm,
                "algorithm_name": group["algorithm_name"].iloc[0],
                "distance_0_3_hit_at_20": recovery_or_nan(
                    group, distance_low, "hit_at_20"
                ),
                "distance_4_plus_hit_at_20": recovery_or_nan(
                    group, distance_high, "hit_at_20"
                ),
                "distance_penalty": recovery_or_nan(
                    group, distance_low, "hit_at_20"
                )
                - recovery_or_nan(group, distance_high, "hit_at_20"),
                "zero_bigram_hit_at_20": recovery_or_nan(
                    group, no_bigram, "hit_at_20"
                ),
                "two_plus_bigram_hit_at_20": recovery_or_nan(
                    group, several_bigrams, "hit_at_20"
                ),
                "bigram_penalty": recovery_or_nan(
                    group, several_bigrams, "hit_at_20"
                )
                - recovery_or_nan(group, no_bigram, "hit_at_20"),
                "short_query_hit_at_20": recovery_or_nan(
                    group, short, "hit_at_20"
                ),
                "long_query_hit_at_20": recovery_or_nan(
                    group, longer, "hit_at_20"
                ),
                "length_penalty": recovery_or_nan(
                    group, longer, "hit_at_20"
                )
                - recovery_or_nan(group, short, "hit_at_20"),
                "mixed_hit_at_20": recovery_or_nan(
                    group, mixed, "hit_at_20"
                ),
                "isolated_hit_at_20": recovery_or_nan(
                    group, isolated, "hit_at_20"
                ),
                "mixed_penalty": recovery_or_nan(
                    group, isolated, "hit_at_20"
                )
                - recovery_or_nan(group, mixed, "hit_at_20"),
                "standard_hit_at_20": recovery_or_nan(
                    group, standard, "hit_at_20"
                ),
                "extreme_hit_at_20": recovery_or_nan(
                    group, extreme, "hit_at_20"
                ),
                "extreme_penalty": recovery_or_nan(
                    group, standard, "hit_at_20"
                )
                - recovery_or_nan(group, extreme, "hit_at_20"),
                "spearman_edit_distance_vs_hit_at_20": correlation,
            }
        )
    return pd.DataFrame(rows)


def failure_overlap(data: pd.DataFrame) -> pd.DataFrame:
    reference = (
        data[data["algorithm"].eq("algorithm_5_evidence_rescue")]
        .set_index("pair_key")
        .sort_index()
    )
    rows = []
    for algorithm, comparison in data.groupby("algorithm"):
        if algorithm == "algorithm_5_evidence_rescue":
            continue
        comparison = comparison.set_index("pair_key").loc[reference.index]
        a5 = reference["hit_at_20"].to_numpy(int)
        other = comparison["hit_at_20"].to_numpy(int)
        a5_only = int(((a5 == 1) & (other == 0)).sum())
        other_only = int(((a5 == 0) & (other == 1)).sum())
        both_success = int(((a5 == 1) & (other == 1)).sum())
        both_fail = int(((a5 == 0) & (other == 0)).sum())
        miss_union = int(((a5 == 0) | (other == 0)).sum())
        rows.append(
            {
                "dataset": data["dataset"].iloc[0],
                "comparison_algorithm": algorithm,
                "comparison_name": comparison["algorithm_name"].iloc[0],
                "both_success": both_success,
                "a5_only_success": a5_only,
                "comparison_only_success": other_only,
                "both_fail": both_fail,
                "oracle_union_hit_at_20": (
                    both_success + a5_only + other_only
                )
                / len(reference),
                "failure_jaccard": both_fail / miss_union if miss_union else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["oracle_union_hit_at_20", "comparison_only_success"],
        ascending=False,
    )


def equivalence_groups(
    ocr: pd.DataFrame,
    synthetic: pd.DataFrame,
) -> pd.DataFrame:
    fingerprints: dict[tuple[str, str], list[str]] = {}
    for dataset, data in (("ocr_464", ocr), ("synthetic_66257", synthetic)):
        for algorithm, group in data.groupby("algorithm"):
            group = group.sort_values("pair_key")
            payload = np.stack(
                [
                    group["rank"].to_numpy(np.int32),
                    group["hit_at_1"].to_numpy(np.int32),
                    group["hit_at_20"].to_numpy(np.int32),
                ],
                axis=1,
            ).tobytes()
            digest = hashlib.sha256(payload).hexdigest()
            fingerprints.setdefault((dataset, digest), []).append(algorithm)
    rows = []
    ocr_groups = {
        tuple(sorted(values)): digest
        for (dataset, digest), values in fingerprints.items()
        if dataset == "ocr_464" and len(values) > 1
    }
    synthetic_groups = {
        tuple(sorted(values)): digest
        for (dataset, digest), values in fingerprints.items()
        if dataset == "synthetic_66257" and len(values) > 1
    }
    for algorithms in sorted(set(ocr_groups) | set(synthetic_groups)):
        rows.append(
            {
                "algorithms": ";".join(algorithms),
                "same_on_ocr": int(algorithms in ocr_groups),
                "same_on_synthetic": int(algorithms in synthetic_groups),
                "same_on_both": int(
                    algorithms in ocr_groups and algorithms in synthetic_groups
                ),
            }
        )
    return pd.DataFrame(rows)


def load_ablation_rows(dataset: str) -> pd.DataFrame:
    root = COMPETITOR_ARTIFACTS / f"a5_ablation_{dataset}"
    files = sorted(root.glob("*.csv.gz"))
    expected_files = {
        "ocr_464": 97,
        "synthetic_66257": 13,
    }[dataset]
    if len(files) != expected_files:
        raise ValueError(
            f"{dataset}: expected {expected_files} Algorithm 5 ablation "
            f"artifacts, found {len(files)}"
        )
    return pd.concat(
        [
            normalize_new_rows(
                read_gzip_csv(
                    path,
                    (*NEW_RESULT_COLUMNS, "ablation_level"),
                )
            )
            for path in files
        ],
        ignore_index=True,
    )


def ablation_effects(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if data.empty:
        return pd.DataFrame(), pd.DataFrame()
    reference = (
        data[data["algorithm"].eq("full_algorithm_5")]
        .set_index("pair_key")
        .sort_index()
    )
    if reference.empty:
        raise ValueError("Algorithm 5 ablation set lacks full reference")
    metrics = []
    examples = []
    for algorithm, group in data.groupby("algorithm"):
        group = group.set_index("pair_key").loc[reference.index]
        row: dict[str, Any] = {
            "dataset": data["dataset"].iloc[0],
            "ablation": algorithm,
            "ablation_name": group["algorithm_name"].iloc[0],
            "ablation_level": group["ablation_level"].iloc[0],
            "cases": len(group),
            "hit_at_1": group["hit_at_1"].mean(),
            "hit_at_20": group["hit_at_20"].mean(),
            "mean_latency_ms": group["latency_ms"].mean(),
            "median_latency_ms": group["latency_ms"].median(),
        }
        for cutoff in (1, 20):
            field = f"hit_at_{cutoff}"
            ref_values = reference[field].to_numpy(int)
            values = group[field].to_numpy(int)
            full_only = int(((ref_values == 1) & (values == 0)).sum())
            ablation_only = int(((ref_values == 0) & (values == 1)).sum())
            row[f"delta_hit_at_{cutoff}"] = (
                values.mean() - ref_values.mean()
            )
            row[f"full_only_hit_at_{cutoff}"] = full_only
            row[f"ablation_only_hit_at_{cutoff}"] = ablation_only
            row[f"mcnemar_p_hit_at_{cutoff}"] = exact_mcnemar(
                full_only,
                ablation_only,
            )
        metrics.append(row)
        if algorithm == "full_algorithm_5":
            continue
        changed = group[
            group["hit_at_1"].ne(reference["hit_at_1"])
            | group["hit_at_20"].ne(reference["hit_at_20"])
            | group["rank"].ne(reference["rank"])
        ].copy()
        for pair, changed_row in changed.head(8).iterrows():
            ref_row = reference.loc[pair]
            examples.append(
                {
                    "dataset": data["dataset"].iloc[0],
                    "ablation": algorithm,
                    "input": ref_row["input"],
                    "expected": ref_row["expected_family_name"],
                    "full_rank": int(ref_row["rank"]),
                    "ablation_rank": int(changed_row["rank"]),
                    "full_top_1": ref_row["top_1"],
                    "ablation_top_1": changed_row["top_1"],
                }
            )
    return (
        pd.DataFrame(metrics).sort_values(
            ["ablation_level", "delta_hit_at_1", "delta_hit_at_20"]
        ),
        pd.DataFrame(examples),
    )


def representative_ablation_examples(
    metrics: pd.DataFrame,
    examples: pd.DataFrame,
    *,
    limit: int,
) -> pd.DataFrame:
    """Select one paired row for each of the most influential removals."""

    if metrics.empty or examples.empty:
        return pd.DataFrame()
    ranked = metrics[metrics["ablation"].ne("full_algorithm_5")].copy()
    ranked["impact"] = np.maximum(
        ranked["delta_hit_at_1"].abs(),
        ranked["delta_hit_at_20"].abs(),
    )
    order = ranked.sort_values(
        ["impact", "delta_hit_at_1", "delta_hit_at_20"],
        ascending=[False, True, True],
    )["ablation"].tolist()
    order_lookup = {name: position for position, name in enumerate(order)}
    selected = examples[examples["ablation"].isin(order_lookup)].copy()
    selected["order"] = selected["ablation"].map(order_lookup)
    selected = (
        selected.sort_values(
            ["order", "full_rank", "ablation_rank", "input"],
        )
        .groupby("ablation", as_index=False, observed=True)
        .head(1)
        .sort_values("order")
        .head(limit)
        .drop(columns="order")
    )
    names = metrics.set_index("ablation")["ablation_name"]
    selected["ablation_name"] = selected["ablation"].map(names)
    return selected


def algorithm_5_revision_drift() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare the historical clean-core artifact with the current source."""

    historical = pd.read_csv(
        SYNTHETIC_CACHED,
        usecols=(
            "case_id",
            "algorithm",
            "split",
            "input",
            "expected",
            "hit_at_1",
            "hit_at_20",
            "first_relevant_rank",
            "top_1",
        ),
    )
    historical = historical[
        historical["algorithm"].eq("algorithm_5_evidence_rescue")
    ].drop(columns="algorithm")
    current = read_gzip_csv(
        COMPETITOR_ARTIFACTS
        / "a5_ablation_synthetic_66257/full_algorithm_5.csv.gz",
        (
            "case_id",
            "input",
            "expected_family_name",
            "hit_at_1",
            "hit_at_20",
            "first_relevant_rank",
            "top_1",
        ),
    ).rename(columns={"expected_family_name": "expected"})
    merged = historical.merge(
        current,
        on="case_id",
        how="inner",
        suffixes=("_historical", "_current"),
        validate="one_to_one",
    )
    if len(merged) != 66257:
        raise ValueError(
            "Algorithm 5 revision comparison requires 66,257 paired rows, "
            f"found {len(merged):,}"
        )
    if not (
        merged["input_historical"].eq(merged["input_current"]).all()
        and merged["expected_historical"].eq(merged["expected_current"]).all()
    ):
        raise ValueError(
            "Algorithm 5 source revisions do not use identical inputs and targets"
        )

    summaries = []
    for split, frame in (
        ("all", merged),
        *merged.groupby("split", observed=True),
    ):
        summaries.append(
            {
                "split": split,
                "cases": len(frame),
                "historical_hit_at_1": frame["hit_at_1_historical"].mean(),
                "current_hit_at_1": frame["hit_at_1_current"].mean(),
                "hit_at_1_gains": int(
                    (
                        frame["hit_at_1_historical"].eq(0)
                        & frame["hit_at_1_current"].eq(1)
                    ).sum()
                ),
                "hit_at_1_losses": int(
                    (
                        frame["hit_at_1_historical"].eq(1)
                        & frame["hit_at_1_current"].eq(0)
                    ).sum()
                ),
                "historical_hit_at_20": frame["hit_at_20_historical"].mean(),
                "current_hit_at_20": frame["hit_at_20_current"].mean(),
                "hit_at_20_gains": int(
                    (
                        frame["hit_at_20_historical"].eq(0)
                        & frame["hit_at_20_current"].eq(1)
                    ).sum()
                ),
                "hit_at_20_losses": int(
                    (
                        frame["hit_at_20_historical"].eq(1)
                        & frame["hit_at_20_current"].eq(0)
                    ).sum()
                ),
                "rank_changes": int(
                    frame["first_relevant_rank_historical"].ne(
                        frame["first_relevant_rank_current"]
                    ).sum()
                ),
            }
        )

    changed = merged[
        merged["first_relevant_rank_historical"].ne(
            merged["first_relevant_rank_current"]
        )
    ].copy()
    changed["change_type"] = np.select(
        [
            changed["hit_at_20_historical"].eq(1)
            & changed["hit_at_20_current"].eq(0),
            changed["hit_at_20_historical"].eq(0)
            & changed["hit_at_20_current"].eq(1),
            changed["hit_at_1_historical"].eq(0)
            & changed["hit_at_1_current"].eq(1),
            changed["hit_at_1_historical"].eq(1)
            & changed["hit_at_1_current"].eq(0),
        ],
        ["Hit@20 loss", "Hit@20 gain", "Hit@1 gain", "Hit@1 loss"],
        default="rank-only change",
    )
    changed = changed[
        [
            "case_id",
            "split",
            "change_type",
            "input_historical",
            "expected_historical",
            "top_1_historical",
            "first_relevant_rank_historical",
            "top_1_current",
            "first_relevant_rank_current",
        ]
    ].rename(
        columns={
            "input_historical": "input",
            "expected_historical": "expected",
            "first_relevant_rank_historical": "historical_rank",
            "first_relevant_rank_current": "current_rank",
        }
    )
    changed["change_order"] = changed["change_type"].map(
        {
            "Hit@20 loss": 0,
            "Hit@20 gain": 1,
            "Hit@1 gain": 2,
            "Hit@1 loss": 3,
            "rank-only change": 4,
        }
    )
    return (
        pd.DataFrame(summaries),
        changed.sort_values(
            ["change_order", "split", "case_id"]
        ).drop(columns="change_order"),
    )


def extreme_analysis(
    ocr: pd.DataFrame,
    metrics: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    a5 = ocr[ocr["algorithm"].eq("algorithm_5_evidence_rescue")].copy()
    detail_path = (
        COMPETITOR_ARTIFACTS
        / "a5_ablation_ocr_464/full_algorithm_5.csv.gz"
    )
    details = read_gzip_csv(detail_path, ("case_id", "top_1")).set_index(
        "case_id"
    )["top_1"]
    a5["top_1"] = a5["case_id"].astype(str).map(details)
    extreme = a5[a5["normalized_distance"].gt(0.60)].copy()
    if len(extreme) != 113:
        raise ValueError(f"expected 113 fair extreme OCR pairs, found {len(extreme)}")
    distributions = []
    for dimension in (
        "operation_profile",
        "distance_band",
        "query_length_band",
        "shared_bigram_band",
    ):
        for value, group in extreme.groupby(dimension):
            distributions.append(
                {
                    "dimension": dimension,
                    "group": value,
                    "cases": len(group),
                    "share": len(group) / len(extreme),
                    "a5_hit_at_1": group["hit_at_1"].mean(),
                    "a5_hit_at_20": group["hit_at_20"].mean(),
                    "failures_at_20": int((1 - group["hit_at_20"]).sum()),
                }
            )
    system_metrics = grouped_metrics(
        ocr[ocr["normalized_distance"].gt(0.60)],
        [],
    )
    success = extreme[extreme["hit_at_20"].eq(1)].copy()
    failure = extreme[extreme["hit_at_20"].eq(0)].copy()
    examples = pd.concat(
        [
            success.sort_values(
                ["rank", "edit_distance", "pair_key"]
            ).head(10),
            failure.sort_values(
                ["operation_profile", "edit_distance", "pair_key"]
            ).groupby("operation_profile", group_keys=False).head(5),
        ]
    )[
        [
            "case_id",
            "input",
            "expected_family_name",
            "operation_profile",
            "edit_distance",
            "normalized_distance",
            "shared_bigrams",
            "rank",
            "top_1",
            "hit_at_20",
            "source_operation_sequence",
        ]
    ].drop_duplicates("case_id")
    return pd.DataFrame(distributions), system_metrics, examples


def representative_breakdowns(data: pd.DataFrame) -> pd.DataFrame:
    selected = data[data["algorithm"].isin(REPRESENTATIVE_SYSTEMS)]
    return grouped_metrics(
        selected,
        ["distance_band", "operation_profile"],
    )


def family_sensitivity(metrics: pd.DataFrame) -> pd.DataFrame:
    evaluated = metrics[
        ~metrics["algorithm"].isin(PROJECT_ALGORITHMS)
    ].copy()
    rows = []
    for (dataset, family), group in evaluated.groupby(
        ["dataset", "method_family"]
    ):
        best_h1 = group.loc[group["hit_at_1"].idxmax()]
        best_h20 = group.loc[group["hit_at_20"].idxmax()]
        worst_h1 = group.loc[group["hit_at_1"].idxmin()]
        rows.append(
            {
                "dataset": dataset,
                "method_family": family,
                "configurations": len(group),
                "best_hit_at_1_system": best_h1["algorithm_name"],
                "best_hit_at_1": best_h1["hit_at_1"],
                "worst_hit_at_1_system": worst_h1["algorithm_name"],
                "worst_hit_at_1": worst_h1["hit_at_1"],
                "hit_at_1_spread": (
                    best_h1["hit_at_1"] - worst_h1["hit_at_1"]
                ),
                "best_hit_at_20_system": best_h20["algorithm_name"],
                "best_hit_at_20": best_h20["hit_at_20"],
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["dataset", "best_hit_at_1"],
        ascending=[True, False],
    )


def external_component_ablations(
    ocr: pd.DataFrame,
    synthetic: pd.DataFrame,
) -> pd.DataFrame:
    """Measure strict component removals and controlled external sensitivities."""

    rows: list[dict[str, Any]] = []
    for dataset, data in (("ocr_464", ocr), ("synthetic_66257", synthetic)):
        by_algorithm = {
            algorithm: frame.set_index("pair_key").sort_index()
            for algorithm, frame in data.groupby("algorithm")
        }
        for (
            system_name,
            reference_algorithm,
            comparison_algorithm,
            change,
            study_type,
        ) in EXTERNAL_COMPONENT_COMPARISONS:
            reference = by_algorithm[reference_algorithm]
            comparison = by_algorithm[comparison_algorithm].loc[reference.index]
            row: dict[str, Any] = {
                "dataset": dataset,
                "study_type": study_type,
                "system": system_name,
                "reference_algorithm": reference_algorithm,
                "reference_name": reference["algorithm_name"].iloc[0],
                "changed_algorithm": comparison_algorithm,
                "changed_name": comparison["algorithm_name"].iloc[0],
                "change": change,
                "cases": len(reference),
            }
            for cutoff in (1, 20):
                field = f"hit_at_{cutoff}"
                full = reference[field].to_numpy(np.int8)
                changed = comparison[field].to_numpy(np.int8)
                full_only = int(((full == 1) & (changed == 0)).sum())
                changed_only = int(((full == 0) & (changed == 1)).sum())
                row.update(
                    {
                        f"reference_hit_at_{cutoff}": float(full.mean()),
                        f"changed_hit_at_{cutoff}": float(changed.mean()),
                        f"delta_hit_at_{cutoff}": float(
                            changed.mean() - full.mean()
                        ),
                        f"reference_only_hit_at_{cutoff}": full_only,
                        f"changed_only_hit_at_{cutoff}": changed_only,
                        f"mcnemar_p_hit_at_{cutoff}": exact_mcnemar(
                            full_only,
                            changed_only,
                        ),
                    }
                )
            rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["dataset", "study_type", "system", "change"]
    )


def worst_supported_slices(
    ocr: pd.DataFrame,
    synthetic: pd.DataFrame,
    *,
    minimum_cases: int = 10,
) -> pd.DataFrame:
    """Find the weakest sufficiently populated data slice for every system."""

    dimensions = (
        "category",
        "error_type",
        "operation_family",
        "distance_band",
        "operation_profile",
        "query_length_band",
        "shared_bigram_band",
    )
    rows: list[dict[str, Any]] = []
    for dataset, data in (("ocr_464", ocr), ("synthetic_66257", synthetic)):
        for algorithm, system in data.groupby("algorithm"):
            for dimension in dimensions:
                groups = (
                    system.groupby(dimension, observed=True)
                    .agg(
                        cases=("case_index", "size"),
                        hit_at_1=("hit_at_1", "mean"),
                        hit_at_20=("hit_at_20", "mean"),
                    )
                    .reset_index()
                )
                groups = groups[groups["cases"].ge(minimum_cases)]
                if groups.empty:
                    continue
                weakest = groups.sort_values(
                    ["hit_at_20", "hit_at_1", "cases"],
                    ascending=[True, True, False],
                ).iloc[0]
                rows.append(
                    {
                        "dataset": dataset,
                        "algorithm": algorithm,
                        "algorithm_name": system["algorithm_name"].iloc[0],
                        "dimension": dimension,
                        "weakest_group": weakest[dimension],
                        "cases": int(weakest["cases"]),
                        "hit_at_1": float(weakest["hit_at_1"]),
                        "hit_at_20": float(weakest["hit_at_20"]),
                    }
                )
    return pd.DataFrame(rows).sort_values(
        ["dataset", "algorithm_name", "dimension"]
    )


def save_csv(path: Path, data: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def latex_escape(value: Any) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


def latex_percent(value: float, *, bold: bool = False) -> str:
    text = f"{value * 100:.4f}\\%"
    return rf"\textbf{{{text}}}" if bold else text


def latex_delta(value: float) -> str:
    return f"{value * 100:+.4f}"


def append_longtable(
    lines: list[str],
    *,
    column_format: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    caption: str,
    label: str,
    landscape: bool = True,
    font_size: str = r"\scriptsize",
) -> None:
    if landscape:
        lines.append(r"\begin{landscape}")
    lines.extend(
        [
            font_size,
            r"\setlength{\tabcolsep}{3pt}",
            rf"\begin{{longtable}}{{{column_format}}}",
            rf"\caption{{{caption}}}\label{{{label}}}\\",
            r"\toprule",
            " & ".join(headers) + r" \\",
            r"\midrule",
            r"\endfirsthead",
            r"\toprule",
            " & ".join(headers) + r" \\",
            r"\midrule",
            r"\endhead",
        ]
    )
    lines.extend(" & ".join(row) + r" \\" for row in rows)
    lines.extend([r"\bottomrule", r"\end{longtable}", r"\normalsize"])
    if landscape:
        lines.append(r"\end{landscape}")
    lines.append("")


def write_meeting_10_tables(
    path: Path,
    *,
    inventory: pd.DataFrame,
    metrics: pd.DataFrame,
    external_ablations: pd.DataFrame,
    drivers: pd.DataFrame,
    a5_ocr_metrics: pd.DataFrame,
    a5_ocr_examples: pd.DataFrame,
    a5_synthetic_metrics: pd.DataFrame,
    a5_synthetic_examples: pd.DataFrame,
    extreme_systems: pd.DataFrame,
    ann_audit: pd.DataFrame,
) -> None:
    """Write exact large tables included by the Meeting 10 LaTeX report."""

    lines = [
        "% Generated by analyze_competitor_benchmark.py. Do not edit manually.",
        "",
    ]
    inventory_rows = []
    for row in inventory.itertuples():
        source_label = row.source_url.rstrip("/").split("/")[-1] or "source"
        source = rf"\href{{{row.source_url}}}{{{latex_escape(source_label)}}}"
        inventory_rows.append(
            (
                latex_escape(row.display_name),
                latex_escape(row.family),
                latex_escape(row.status),
                source,
                latex_escape(row.reason),
            )
        )
    append_longtable(
        lines,
        column_format=r"@{}L{0.17\linewidth}L{0.14\linewidth}L{0.08\linewidth}L{0.12\linewidth}Y@{}",
        headers=(
            r"\textbf{Repository or configuration}",
            r"\textbf{Method family}",
            r"\textbf{Status}",
            r"\textbf{Source}",
            r"\textbf{Measured, represented, or excluded because}",
        ),
        rows=inventory_rows,
        caption=(
            "Complete external-method inventory. Evaluated entries produce new "
            "row-level predictions; cached entries reuse locked predictions; "
            "represented and duplicate entries add no distinct ranking; excluded "
            "entries lack compatible inputs, labels, or reproducible inference."
        ),
        label="tab:expanded-competitor-inventory",
    )

    for dataset, label_name, caption_name in (
        ("ocr_464", "ocr", "464 collision-free unique OCR query-target pairs"),
        (
            "synthetic_66257",
            "synthetic",
            "66,257 unique synthetic clean-core query-target pairs",
        ),
    ):
        frame = metrics[metrics["dataset"].eq(dataset)].copy()
        frame = frame.sort_values(
            ["hit_at_1", "hit_at_20", "mrr_at_20"],
            ascending=False,
        ).reset_index(drop=True)
        best_h1 = frame["hit_at_1"].max()
        best_h20 = frame["hit_at_20"].max()
        best_latency = frame["median_latency_ms"].min()
        rows = []
        for rank, row in enumerate(frame.itertuples(), 1):
            rows.append(
                (
                    str(rank),
                    latex_escape(row.algorithm_name),
                    latex_escape(row.method_family),
                    latex_percent(row.hit_at_1, bold=row.hit_at_1 == best_h1),
                    latex_percent(row.hit_at_5),
                    latex_percent(
                        row.hit_at_20,
                        bold=row.hit_at_20 == best_h20,
                    ),
                    f"{row.mrr_at_20:.6f}",
                    (
                        rf"\textbf{{{row.median_latency_ms:.4f}}}"
                        if row.median_latency_ms == best_latency
                        else f"{row.median_latency_ms:.4f}"
                    ),
                    f"{row.p95_latency_ms:.4f}",
                )
            )
        append_longtable(
            lines,
            column_format=r"@{}rL{0.25\linewidth}L{0.16\linewidth}rrrrrr@{}",
            headers=(
                r"\textbf{Rank}",
                r"\textbf{System}",
                r"\textbf{Method family}",
                r"\textbf{H@1}",
                r"\textbf{H@5}",
                r"\textbf{H@20}",
                r"\textbf{MRR@20}",
                r"\textbf{Median ms}",
                r"\textbf{P95 ms}",
            ),
            rows=rows,
            caption=(
                f"Complete leaderboard on {caption_name}. Every system receives "
                "the identical locked pairs. Accuracy confidence intervals and "
                "paired tests are reported in the companion analysis tables."
            ),
            label=f"tab:expanded-{label_name}-leaderboard",
        )

    for dataset, label_name in (
        ("ocr_464", "ocr"),
        ("synthetic_66257", "synthetic"),
    ):
        frame = external_ablations[
            external_ablations["dataset"].eq(dataset)
        ]
        rows = [
            (
                latex_escape(row.study_type.replace("_", " ")),
                latex_escape(row.system),
                latex_escape(row.change),
                latex_percent(row.reference_hit_at_1),
                latex_percent(row.changed_hit_at_1),
                latex_delta(row.delta_hit_at_1),
                latex_percent(row.reference_hit_at_20),
                latex_percent(row.changed_hit_at_20),
                latex_delta(row.delta_hit_at_20),
            )
            for row in frame.itertuples()
        ]
        append_longtable(
            lines,
            column_format=r"@{}L{0.12\linewidth}L{0.15\linewidth}L{0.24\linewidth}rrrrrr@{}",
            headers=(
                r"\textbf{Study}",
                r"\textbf{Reference}",
                r"\textbf{Removal or controlled change}",
                r"\textbf{Ref H@1}",
                r"\textbf{Changed H@1}",
                r"\textbf{$\Delta$ pp}",
                r"\textbf{Ref H@20}",
                r"\textbf{Changed H@20}",
                r"\textbf{$\Delta$ pp}",
            ),
            rows=rows,
            caption=(
                f"External composite ablations and parameter sensitivity on "
                f"{'464 OCR' if dataset == 'ocr_464' else '66,257 synthetic'} "
                "pairs. Delta is changed configuration minus the named reference "
                "in percentage points."
            ),
            label=f"tab:external-{label_name}-ablations",
        )

    for dataset, label_name in (
        ("ocr_464", "ocr"),
        ("synthetic_66257", "synthetic"),
    ):
        frame = drivers[drivers["dataset"].eq(dataset)].sort_values(
            "distance_4_plus_hit_at_20",
            ascending=False,
        )
        rows = [
            (
                latex_escape(row.algorithm_name),
                latex_percent(row.distance_0_3_hit_at_20),
                latex_percent(row.distance_4_plus_hit_at_20),
                latex_percent(row.zero_bigram_hit_at_20),
                latex_percent(row.two_plus_bigram_hit_at_20),
                latex_percent(row.short_query_hit_at_20),
                latex_percent(row.long_query_hit_at_20),
                latex_percent(row.mixed_hit_at_20),
                latex_percent(row.extreme_hit_at_20),
            )
            for row in frame.itertuples()
        ]
        append_longtable(
            lines,
            column_format=r"@{}L{0.27\linewidth}rrrrrrrr@{}",
            headers=(
                r"\textbf{System}",
                r"\textbf{Edits 0--3}",
                r"\textbf{Edits 4+}",
                r"\textbf{0 bigrams}",
                r"\textbf{2+ bigrams}",
                r"\textbf{Short}",
                r"\textbf{Long}",
                r"\textbf{Mixed}",
                r"\textbf{Extreme}",
            ),
            rows=rows,
            caption=(
                f"Hit@20 failure drivers for every system on "
                f"{'OCR' if dataset == 'ocr_464' else 'synthetic'} data. "
                "Short means compact query length at most four, long means at "
                "least eight, mixed means multiple edit mechanisms, and extreme "
                "means normalized compact edit distance above 0.60."
            ),
            label=f"tab:{label_name}-system-failure-drivers",
        )

    for frame, label_name, caption_name in (
        (
            a5_ocr_metrics,
            "ocr",
            "all 97 complete, component, signal, retrieval, reranker, safety, and atomic-flag configurations on 464 OCR pairs",
        ),
        (
            a5_synthetic_metrics,
            "synthetic",
            "the 13 confirmation configurations on 66,257 synthetic pairs",
        ),
    ):
        rows = [
            (
                latex_escape(row.ablation_name),
                latex_escape(row.ablation_level),
                latex_percent(row.hit_at_1),
                latex_delta(row.delta_hit_at_1),
                str(int(row.full_only_hit_at_1)),
                str(int(row.ablation_only_hit_at_1)),
                latex_percent(row.hit_at_20),
                latex_delta(row.delta_hit_at_20),
                str(int(row.full_only_hit_at_20)),
                str(int(row.ablation_only_hit_at_20)),
            )
            for row in frame.itertuples()
        ]
        append_longtable(
            lines,
            column_format=r"@{}L{0.28\linewidth}L{0.10\linewidth}rrrrrrrr@{}",
            headers=(
                r"\textbf{Algorithm 5 configuration}",
                r"\textbf{Level}",
                r"\textbf{H@1}",
                r"\textbf{$\Delta$1 pp}",
                r"\textbf{Full-only 1}",
                r"\textbf{Abl.-only 1}",
                r"\textbf{H@20}",
                r"\textbf{$\Delta$20 pp}",
                r"\textbf{Full-only 20}",
                r"\textbf{Abl.-only 20}",
            ),
            rows=rows,
            caption=(
                f"Algorithm 5 ablation results for {caption_name}. Delta is "
                "ablation minus complete Algorithm 5. Full-only and ablation-only "
                "are paired case-switch counts."
            ),
            label=f"tab:a5-{label_name}-full-ablation",
        )

    extreme = extreme_systems.sort_values(
        ["hit_at_20", "hit_at_1"],
        ascending=False,
    )
    extreme_rows = [
        (
            latex_escape(row.algorithm_name),
            str(int(row.cases)),
            latex_percent(row.hit_at_1),
            latex_percent(row.hit_at_20),
            str(int(row.failures_at_20)),
        )
        for row in extreme.itertuples()
    ]
    append_longtable(
        lines,
        column_format=r"@{}L{0.55\linewidth}rrrr@{}",
        headers=(
            r"\textbf{System}",
            r"\textbf{Cases}",
            r"\textbf{H@1}",
            r"\textbf{H@20}",
            r"\textbf{Top-20 misses}",
        ),
        rows=extreme_rows,
        caption=(
            "Every system on the 113 fair extreme OCR pairs. Extreme means "
            "$L(q_c,y_c)/\\max(|y_c|,1)>0.60$ after compact normalization."
        ),
        label="tab:expanded-extreme-system-results",
        landscape=False,
        font_size=r"\footnotesize",
    )

    ann_rows = [
        (
            latex_escape(DISPLAY_NAMES[row.algorithm]),
            latex_escape(DATASET_NAMES.get(row.dataset, row.dataset)),
            str(int(row.audited_queries)),
            latex_percent(row.exact_top1_agreement),
            latex_percent(row.mean_exact_top20_recall),
            latex_percent(row.minimum_exact_top20_recall),
        )
        for row in ann_audit.itertuples()
    ]
    append_longtable(
        lines,
        column_format=r"@{}L{0.30\linewidth}L{0.18\linewidth}rrrr@{}",
        headers=(
            r"\textbf{Dense model}",
            r"\textbf{Dataset}",
            r"\textbf{Audited}",
            r"\textbf{Exact/HNSW top-1}",
            r"\textbf{Mean top-20 recall}",
            r"\textbf{Minimum top-20 recall}",
        ),
        rows=ann_rows,
        caption=(
            "Exact dense-retrieval audit. All 464 OCR queries and a fixed "
            "1,000-query synthetic sample compare exact cosine top 20 with the "
            "reported HNSW top 20."
        ),
        label="tab:dense-ann-audit",
        landscape=False,
        font_size=r"\small",
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def configure_plots() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "axes.edgecolor": GRAY,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": LIGHT_GRAY,
            "grid.linewidth": 0.7,
            "grid.alpha": 0.8,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def save_figure(
    fig: plt.Figure,
    name: str,
    *,
    apply_tight_layout: bool = True,
) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    if apply_tight_layout:
        fig.tight_layout()
    fig.savefig(FIGURES / f"{name}.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_leaderboard(metrics: pd.DataFrame, dataset: str, name: str) -> None:
    selected = metrics[metrics["dataset"].eq(dataset)].nlargest(
        15, ["hit_at_1", "hit_at_20"]
    )
    project = metrics[
        metrics["dataset"].eq(dataset)
        & metrics["algorithm"].isin(PROJECT_ALGORITHMS)
    ]
    selected = (
        pd.concat([selected, project])
        .drop_duplicates("algorithm")
        .sort_values("hit_at_1")
    )
    fig, ax = plt.subplots(figsize=(11, max(7, 0.42 * len(selected) + 2)))
    y = np.arange(len(selected))
    hit_at_1 = selected["hit_at_1"].to_numpy() * 100
    hit_at_20 = selected["hit_at_20"].to_numpy() * 100
    hit_at_1_error = np.vstack(
        (
            hit_at_1 - selected["hit_at_1_ci_low"].to_numpy() * 100,
            selected["hit_at_1_ci_high"].to_numpy() * 100 - hit_at_1,
        )
    )
    hit_at_20_error = np.vstack(
        (
            hit_at_20 - selected["hit_at_20_ci_low"].to_numpy() * 100,
            selected["hit_at_20_ci_high"].to_numpy() * 100 - hit_at_20,
        )
    )
    ax.barh(
        y - 0.17,
        hit_at_1,
        0.32,
        color=BLUE,
        label="Hit@1",
        xerr=hit_at_1_error,
        capsize=2,
    )
    ax.barh(
        y + 0.17,
        hit_at_20,
        0.32,
        color=ORANGE,
        label="Hit@20",
        xerr=hit_at_20_error,
        capsize=2,
    )
    ax.set_yticks(y, selected["algorithm_name"])
    ax.set_xlim(0, 105)
    ax.xaxis.set_major_formatter(PercentFormatter(100))
    ax.set_xlabel("Queries with verified family recovered (%)")
    ax.set_ylabel("Retrieval system")
    ax.set_title(
        f"Best retrieval systems on {DATASET_NAMES[dataset]}",
        loc="left",
    )
    ax.legend(loc="lower right")
    save_figure(fig, name)


def plot_cross_dataset(metrics: pd.DataFrame) -> None:
    pivot = metrics.pivot(
        index=["algorithm", "algorithm_name", "method_family"],
        columns="dataset",
        values="hit_at_1",
    ).reset_index()
    fig, ax = plt.subplots(figsize=(10.5, 7.0))
    project = pivot["algorithm"].isin(PROJECT_ALGORITHMS)
    ax.scatter(
        pivot.loc[~project, "ocr_464"] * 100,
        pivot.loc[~project, "synthetic_66257"] * 100,
        color=BLUE,
        alpha=0.72,
        s=55,
        label="External or classical method",
    )
    ax.scatter(
        pivot.loc[project, "ocr_464"] * 100,
        pivot.loc[project, "synthetic_66257"] * 100,
        color=ORANGE,
        marker="D",
        s=78,
        label="Project Algorithm 1-5",
    )
    label_algorithms = {
        "algorithm_4_family_rescue",
        "algorithm_5_evidence_rescue",
        "damerau_levenshtein",
        "symspell_frequency_ed3",
        "coderpp_dense_hnsw",
        "biosyn_hybrid_w50",
        "baseline_jaro_winkler",
    }
    annotation_layout = {
        "algorithm_5_evidence_rescue": ((-8, 8), "right"),
        "algorithm_4_family_rescue": ((-8, -12), "right"),
        "damerau_levenshtein": ((8, 8), "left"),
        "symspell_frequency_ed3": ((8, -14), "left"),
        "coderpp_dense_hnsw": ((8, 4), "left"),
        "biosyn_hybrid_w50": ((-8, -14), "right"),
        "baseline_jaro_winkler": ((8, -10), "left"),
    }
    for row in pivot[pivot["algorithm"].isin(label_algorithms)].itertuples():
        offset, horizontal_alignment = annotation_layout[row.algorithm]
        ax.annotate(
            row.algorithm_name,
            (row.ocr_464 * 100, row.synthetic_66257 * 100),
            xytext=offset,
            textcoords="offset points",
            fontsize=8,
            ha=horizontal_alignment,
            bbox={
                "boxstyle": "round,pad=0.12",
                "facecolor": "white",
                "edgecolor": "none",
                "alpha": 0.76,
            },
        )
    ax.set_xlabel("Hit@1 on 464 fair OCR pairs (%)")
    ax.set_ylabel("Hit@1 on 66,257 synthetic pairs (%)")
    ax.set_xlim(-2, 58)
    ax.set_ylim(-5, 104)
    ax.set_title("Synthetic accuracy overstates observed OCR recovery", loc="left")
    ax.legend(loc="lower right")
    save_figure(fig, "03_cross_dataset_hit_at_1")


def plot_distance_profiles(ocr: pd.DataFrame, synthetic: pd.DataFrame) -> None:
    systems = (
        "algorithm_5_evidence_rescue",
        "algorithm_4_family_rescue",
        "damerau_levenshtein",
        "symspell_frequency_ed3",
        "jaro_similarity",
        "coderpp_dense_hnsw",
    )
    colors = [ORANGE, PURPLE, BLUE, CYAN, "#228833", GRAY]
    fig, axes = plt.subplots(1, 2, figsize=(16.5, 6.2), sharey=True)
    for ax, data, title in (
        (axes[0], ocr, "464 fair OCR pairs"),
        (axes[1], synthetic, "66,257 synthetic pairs"),
    ):
        ordered_distances = sorted(data["edit_distance"].unique())
        distance_counts = (
            data.loc[
                data["algorithm"].eq("algorithm_5_evidence_rescue"),
                "edit_distance",
            ]
            .value_counts()
        )
        for algorithm, color in zip(systems, colors):
            frame = (
                data[data["algorithm"].eq(algorithm)]
                .groupby("edit_distance")["hit_at_20"]
                .agg(["mean", "size"])
                .reindex(ordered_distances)
            )
            ax.plot(
                ordered_distances,
                frame["mean"] * 100,
                marker="o",
                linewidth=1.8,
                color=color,
                label=data[data["algorithm"].eq(algorithm)][
                    "algorithm_name"
                ].iloc[0],
            )
        ax.set_title(title, loc="left")
        ax.set_xlabel("Compact Levenshtein edit distance (operations)")
        ax.set_ylabel("Hit@20 within distance group (%)")
        ax.set_xticks(
            ordered_distances,
            [
                f"{distance}\nn={int(distance_counts.get(distance, 0)):,}"
                for distance in ordered_distances
            ],
            rotation=45,
            ha="right",
            fontsize=7.2,
        )
        ax.yaxis.set_major_formatter(PercentFormatter(100))
        ax.set_ylim(-3, 103)
    axes[1].legend(loc="center left", bbox_to_anchor=(1.02, 0.5))
    save_figure(fig, "04_hit_at_20_by_edit_distance")


def plot_a5_feature_correlations(correlations: pd.DataFrame) -> None:
    fields = list(CORRELATION_FEATURES)
    labels = [CORRELATION_FEATURES[field] for field in fields]
    fig, axes = plt.subplots(1, 2, figsize=(18, 8.4))
    fig.subplots_adjust(
        left=0.18,
        right=0.91,
        bottom=0.31,
        top=0.94,
        wspace=0.72,
    )
    image = None
    for ax, dataset, title in (
        (axes[0], "ocr_464", "464 fair OCR pairs"),
        (axes[1], "synthetic_66257", "66,257 synthetic pairs"),
    ):
        frame = correlations[correlations["dataset"].eq(dataset)].pivot(
            index="feature_y",
            columns="feature_x",
            values="spearman_rho",
        ).reindex(index=fields, columns=fields)
        values = frame.to_numpy(float)
        image = ax.imshow(values, cmap="RdBu_r", vmin=-1, vmax=1)
        ax.set_xticks(
            np.arange(len(fields)),
            labels,
            rotation=38,
            ha="right",
            fontsize=8.5,
        )
        ax.set_yticks(np.arange(len(fields)), labels, fontsize=8.5)
        for row in range(len(fields)):
            for column in range(len(fields)):
                value = values[row, column]
                ax.text(
                    column,
                    row,
                    f"{value:.2f}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white" if abs(value) >= 0.55 else "#1F2937",
                )
        ax.set_xlabel("Feature or outcome")
        ax.set_ylabel("Feature or outcome")
        ax.set_title(title, loc="left")
        ax.grid(False)
    if image is not None:
        colorbar_axis = fig.add_axes((0.94, 0.24, 0.014, 0.62))
        colorbar = fig.colorbar(image, cax=colorbar_axis)
        colorbar.set_label("Spearman rank correlation")
    save_figure(
        fig,
        "13_algorithm_5_feature_correlations",
        apply_tight_layout=False,
    )


def plot_a5_ablation(
    metrics: pd.DataFrame,
    *,
    title: str,
    output_name: str,
    limit: int = 20,
) -> None:
    selected = metrics[
        metrics["ablation_level"].ne("atomic_flag")
        & metrics["ablation"].ne("full_algorithm_5")
    ].copy()
    selected["max_effect"] = selected[
        ["delta_hit_at_1", "delta_hit_at_20"]
    ].abs().max(axis=1)
    selected = selected.nlargest(limit, "max_effect").sort_values("delta_hit_at_1")
    fig, ax = plt.subplots(figsize=(11, 9.4))
    y = np.arange(len(selected))
    ax.barh(
        y - 0.17,
        selected["delta_hit_at_1"] * 100,
        0.32,
        color=BLUE,
        label="Change in Hit@1",
    )
    ax.barh(
        y + 0.17,
        selected["delta_hit_at_20"] * 100,
        0.32,
        color=ORANGE,
        label="Change in Hit@20",
    )
    ax.axvline(0, color=GRAY, linewidth=1)
    ax.set_yticks(y, selected["ablation_name"])
    ax.set_xlabel("Ablation minus complete Algorithm 5 (percentage points)")
    ax.set_ylabel("Removed component")
    ax.set_title(title, loc="left")
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.08),
        ncol=2,
    )
    save_figure(fig, output_name)


def plot_a5_operation_profiles(
    ocr: pd.DataFrame,
    synthetic: pd.DataFrame,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(15.5, 6.5), sharey=False)
    for ax, data, title in (
        (axes[0], ocr, "464 fair OCR pairs"),
        (axes[1], synthetic, "66,257 synthetic pairs"),
    ):
        frame = (
            data[data["algorithm"].eq("algorithm_5_evidence_rescue")]
            .groupby("operation_profile", observed=True)
            .agg(
                cases=("case_id", "size"),
                hit_at_1=("hit_at_1", "mean"),
                hit_at_20=("hit_at_20", "mean"),
            )
            .sort_values("hit_at_20")
        )
        y = np.arange(len(frame))
        ax.barh(y - 0.17, frame["hit_at_1"] * 100, 0.32, color=BLUE, label="Hit@1")
        ax.barh(y + 0.17, frame["hit_at_20"] * 100, 0.32, color=ORANGE, label="Hit@20")
        ax.set_yticks(
            y,
            [
                f"{str(name).replace('_', ' ').title()} (n={count:,})"
                for name, count in zip(frame.index, frame["cases"])
            ],
        )
        ax.set_xlim(0, 105)
        ax.xaxis.set_major_formatter(PercentFormatter(100))
        ax.set_xlabel("Algorithm 5 recovery within operation group (%)")
        ax.set_ylabel("Character-error operation profile")
        ax.set_title(title, loc="left")
    axes[0].legend(loc="lower right")
    save_figure(fig, "09_algorithm_5_by_operation_profile")


def plot_composite_components(study: pd.DataFrame) -> None:
    selected = study[
        study["study"].isin(
            ("BioSyn sparse-dense mixture", "xMEN rank fusion", "preon staged normalizer")
        )
    ].copy()
    fig, axes = plt.subplots(1, 2, figsize=(15, 8), sharey=False)
    for ax, dataset in zip(axes, ("ocr_464", "synthetic_66257")):
        frame = selected[selected["dataset"].eq(dataset)].copy()
        frame["label"] = frame["study"] + ": " + frame["component_role"]
        frame = frame.sort_values(["study", "hit_at_1"])
        y = np.arange(len(frame))
        ax.barh(y, frame["hit_at_1"] * 100, color=BLUE, height=0.62)
        ax.set_yticks(y, frame["label"])
        ax.set_xlim(0, 105)
        ax.xaxis.set_major_formatter(PercentFormatter(100))
        ax.set_xlabel("Hit@1 (%)")
        ax.set_ylabel("Composite and measured component removal")
        ax.set_title(DATASET_NAMES[dataset], loc="left")
    save_figure(fig, "10_external_composite_component_study")


def plot_extreme_performance(
    extreme_systems: pd.DataFrame,
) -> None:
    selected = extreme_systems.nlargest(15, ["hit_at_20", "hit_at_1"]).sort_values(
        "hit_at_20"
    )
    fig, ax = plt.subplots(figsize=(10.5, 7.2))
    y = np.arange(len(selected))
    ax.barh(y - 0.17, selected["hit_at_1"] * 100, 0.32, color=BLUE, label="Hit@1")
    ax.barh(y + 0.17, selected["hit_at_20"] * 100, 0.32, color=ORANGE, label="Hit@20")
    ax.set_yticks(y, selected["algorithm_name"])
    ax.set_xlim(0, max(20, selected["hit_at_20"].max() * 115))
    ax.xaxis.set_major_formatter(PercentFormatter(100))
    ax.set_xlabel("Recovery within 113 fair extreme pairs (%)")
    ax.set_ylabel("Retrieval system")
    ax.set_title("No tested system reliably recovers the extreme OCR cohort", loc="left")
    ax.legend(loc="lower right")
    save_figure(fig, "06_extreme_cohort_recovery")


def plot_latency_frontier(metrics: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    annotation_layout = {
        "ocr_464": {
            "algorithm_5_evidence_rescue": ((5, 5), "left"),
            "symspell_frequency_ed3": ((5, 6), "left"),
            "damerau_levenshtein": ((5, -13), "left"),
        },
        "synthetic_66257": {
            "algorithm_5_evidence_rescue": ((5, 5), "left"),
            "symspell_frequency_ed3": ((5, -14), "left"),
            "damerau_levenshtein": ((5, 6), "left"),
        },
    }
    for ax, dataset in zip(axes, ("ocr_464", "synthetic_66257")):
        frame = metrics[metrics["dataset"].eq(dataset)]
        project = frame["algorithm"].isin(PROJECT_ALGORITHMS)
        ax.scatter(
            frame.loc[~project, "median_latency_ms"],
            frame.loc[~project, "hit_at_1"] * 100,
            color=BLUE,
            alpha=0.68,
            s=45,
            label="External or classical",
        )
        ax.scatter(
            frame.loc[project, "median_latency_ms"],
            frame.loc[project, "hit_at_1"] * 100,
            color=ORANGE,
            marker="D",
            s=70,
            label="Project Algorithm 1-5",
        )
        for algorithm in (
            "algorithm_5_evidence_rescue",
            "damerau_levenshtein",
            "symspell_frequency_ed3",
        ):
            row = frame[frame["algorithm"].eq(algorithm)].iloc[0]
            offset, alignment = annotation_layout[dataset][algorithm]
            ax.annotate(
                row["algorithm_name"],
                (row["median_latency_ms"], row["hit_at_1"] * 100),
                xytext=offset,
                textcoords="offset points",
                fontsize=7.5,
                ha=alignment,
                bbox={
                    "boxstyle": "square,pad=0.08",
                    "facecolor": "white",
                    "edgecolor": "none",
                    "alpha": 0.78,
                },
            )
        ax.set_xscale("log")
        ax.set_ylim(-2, 104)
        ax.set_xlabel("Measured scoring time per query (ms, log scale)")
        ax.set_ylabel("Hit@1 (%)")
        ax.set_title(DATASET_NAMES[dataset], loc="left")
    axes[0].legend(loc="lower right")
    save_figure(fig, "07_accuracy_latency_tradeoff")


def plot_coverage_recovery(metrics: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharex=True, sharey=True)
    labels = {
        "algorithm_5_evidence_rescue",
        "baseline_jaro_winkler",
        "baseline_exact_prefix",
        "flexsearch_tolerant_default",
        "flexsearch_tolerant_extra",
    }
    for ax, dataset in zip(axes, ("ocr_464", "synthetic_66257")):
        frame = metrics[metrics["dataset"].eq(dataset)]
        project = frame["algorithm"].isin(PROJECT_ALGORITHMS)
        ax.scatter(
            frame.loc[~project, "no_result_rate"] * 100,
            frame.loc[~project, "hit_at_20"] * 100,
            color=BLUE,
            alpha=0.68,
            s=45,
            label="External or classical",
        )
        ax.scatter(
            frame.loc[project, "no_result_rate"] * 100,
            frame.loc[project, "hit_at_20"] * 100,
            color=ORANGE,
            marker="D",
            s=70,
            label="Project Algorithm 1-5",
        )
        for row in frame[frame["algorithm"].isin(labels)].itertuples():
            if row.algorithm == "algorithm_5_evidence_rescue":
                offset = (4, 2)
                annotation = "Algorithm 5"
            elif row.algorithm == "baseline_jaro_winkler":
                offset = (4, -11)
                annotation = row.algorithm_name
            else:
                offset = (4, 4)
                annotation = row.algorithm_name
            ax.annotate(
                annotation,
                (row.no_result_rate * 100, row.hit_at_20 * 100),
                xytext=offset,
                textcoords="offset points",
                fontsize=7.2,
                bbox={
                    "boxstyle": "round,pad=0.10",
                    "facecolor": "white",
                    "edgecolor": "none",
                    "alpha": 0.76,
                },
            )
        ax.set_xlim(-2, 102)
        ax.set_ylim(-2, 106)
        ax.xaxis.set_major_formatter(PercentFormatter(100))
        ax.yaxis.set_major_formatter(PercentFormatter(100))
        ax.set_xlabel("Queries returning zero candidates (%)")
        ax.set_ylabel("Hit@20 (%)")
        ax.set_title(DATASET_NAMES[dataset], loc="left")
    axes[0].legend(loc="lower left")
    save_figure(fig, "12_candidate_coverage_vs_recovery")


def plot_external_component_effects(effects: pd.DataFrame) -> None:
    selected = effects[
        effects["study_type"].eq("strict_component")
    ].copy()
    selected["label"] = (
        selected["system"]
        + ": "
        + selected["change"].str.replace(" branch", "", regex=False)
    )
    datasets = ("ocr_464", "synthetic_66257")
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.5), sharey=True)
    for ax, dataset in zip(axes, datasets):
        frame = selected[selected["dataset"].eq(dataset)].copy()
        frame = frame.sort_values("delta_hit_at_1")
        y = np.arange(len(frame))
        ax.barh(
            y - 0.17,
            frame["delta_hit_at_1"] * 100,
            0.32,
            color=BLUE,
            label="Change in Hit@1",
        )
        ax.barh(
            y + 0.17,
            frame["delta_hit_at_20"] * 100,
            0.32,
            color=ORANGE,
            label="Change in Hit@20",
        )
        ax.axvline(0, color=GRAY, linewidth=1)
        ax.set_yticks(y, frame["label"])
        ax.set_xlabel("Changed configuration minus full system (percentage points)")
        ax.set_title(DATASET_NAMES[dataset], loc="left")
    axes[0].set_ylabel("External composite component removal")
    axes[1].legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.13),
        ncol=2,
    )
    save_figure(fig, "08_external_composite_ablation")


def ann_exact_recall_audit() -> pd.DataFrame:
    model_files = {
        "biomedbert_dense_hnsw": "microsoft__BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext",
        "sapbert_dense_hnsw": "cambridgeltl__SapBERT-from-PubMedBERT-fulltext",
        "coderpp_dense_hnsw": "GanjinZero__coder_eng_pp",
    }
    families = competitor_runner.load_catalog()
    family_index = {family.key: index for index, family in enumerate(families)}
    cache = COMPETITOR_ARTIFACTS / "embedding_cache"
    rows = []
    for dataset, sample_size in (("ocr_464", 464), ("synthetic_66257", 1000)):
        rng = np.random.default_rng(20260723)
        for algorithm, stem in model_files.items():
            catalog = np.load(cache / f"{stem}__catalog.npy", mmap_mode="r")
            queries = np.load(cache / f"{stem}__{dataset}.npy", mmap_mode="r")
            if len(queries) <= sample_size:
                indices = np.arange(len(queries))
            else:
                indices = np.sort(
                    rng.choice(len(queries), size=sample_size, replace=False)
                )
            result_rows = read_gzip_csv(
                COMPETITOR_ARTIFACTS / dataset / f"{algorithm}.csv.gz"
            )
            overlaps = []
            top1_matches = 0
            for start in range(0, len(indices), 64):
                batch_indices = indices[start : start + 64]
                scores = np.asarray(queries[batch_indices]) @ np.asarray(catalog).T
                candidate = np.argpartition(
                    scores,
                    -TOP_K,
                    axis=1,
                )[:, -TOP_K:]
                candidate_scores = np.take_along_axis(scores, candidate, axis=1)
                order = np.argsort(-candidate_scores, axis=1)
                exact = np.take_along_axis(candidate, order, axis=1)
                for local, source_index in enumerate(batch_indices):
                    hnsw_keys = [
                        compact(name)
                        for name in str(
                            result_rows.iloc[source_index]["top_20"]
                        ).split(";")
                        if name
                    ]
                    hnsw = [family_index[key] for key in hnsw_keys if key in family_index]
                    exact_values = [int(value) for value in exact[local]]
                    overlaps.append(len(set(hnsw) & set(exact_values)) / TOP_K)
                    top1_matches += int(bool(hnsw) and hnsw[0] == exact_values[0])
            rows.append(
                {
                    "dataset": dataset,
                    "algorithm": algorithm,
                    "audited_queries": len(indices),
                    "exact_top1_agreement": top1_matches / len(indices),
                    "mean_exact_top20_recall": float(np.mean(overlaps)),
                    "minimum_exact_top20_recall": float(np.min(overlaps)),
                }
            )
    return pd.DataFrame(rows)


def summary_values(
    metrics: pd.DataFrame,
    paired: pd.DataFrame,
    extreme_distribution: pd.DataFrame,
    a5_ocr_ablation: pd.DataFrame,
    a5_revision_summary: pd.DataFrame,
) -> dict[str, Any]:
    competitor_count = len(competitor_runner.EVALUATED_COMPETITORS)
    inventory = inventory_lookup()
    output: dict[str, Any] = {
        "systems_per_dataset": int(
            metrics.groupby("dataset")["algorithm"].nunique().min()
        ),
        "inventory_entries": len(inventory),
        "inventory_status_counts": {
            str(status): int(count)
            for status, count in inventory["status"].value_counts().items()
        },
        "new_competitor_configurations": competitor_count,
        "ocr_pairs": 464,
        "synthetic_pairs": 66257,
        "total_new_competitor_rows": competitor_count * (464 + 66257),
        "total_evaluated_rows": len(ALL_ALGORITHM_IDS) * (464 + 66257),
        "fair_extreme_pairs": int(
            extreme_distribution["cases"].groupby(
                extreme_distribution["dimension"]
            ).sum().iloc[0]
        ),
    }
    for dataset in ("ocr_464", "synthetic_66257"):
        frame = metrics[metrics["dataset"].eq(dataset)]
        a5 = frame[frame["algorithm"].eq("algorithm_5_evidence_rescue")].iloc[0]
        external = frame[
            ~frame["algorithm"].isin(PROJECT_ALGORITHMS)
        ]
        best_external_hit_at_1 = external.sort_values(
            ["hit_at_1", "hit_at_20"],
            ascending=False,
        ).iloc[0]
        best_external_hit_at_20 = external.sort_values(
            ["hit_at_20", "hit_at_1"],
            ascending=False,
        ).iloc[0]
        output[dataset] = {
            "a5_hit_at_1": float(a5["hit_at_1"]),
            "a5_hit_at_20": float(a5["hit_at_20"]),
            "best_external_hit_at_1_name": best_external_hit_at_1[
                "algorithm_name"
            ],
            "best_external_hit_at_1": float(
                best_external_hit_at_1["hit_at_1"]
            ),
            "best_external_hit_at_20_name": best_external_hit_at_20[
                "algorithm_name"
            ],
            "best_external_hit_at_20": float(
                best_external_hit_at_20["hit_at_20"]
            ),
        }
    if not a5_ocr_ablation.empty:
        rescue = a5_ocr_ablation[
            a5_ocr_ablation["ablation"].eq("without_rescue_layer")
        ].iloc[0]
        output["a5_without_rescue"] = {
            "hit_at_1": float(rescue["hit_at_1"]),
            "hit_at_20": float(rescue["hit_at_20"]),
            "delta_hit_at_1": float(rescue["delta_hit_at_1"]),
            "delta_hit_at_20": float(rescue["delta_hit_at_20"]),
        }
    revision = a5_revision_summary[
        a5_revision_summary["split"].eq("all")
    ].iloc[0]
    output["a5_synthetic_source_revision"] = {
        "historical_hit_at_1": float(revision["historical_hit_at_1"]),
        "current_hit_at_1": float(revision["current_hit_at_1"]),
        "hit_at_1_gains": int(revision["hit_at_1_gains"]),
        "hit_at_1_losses": int(revision["hit_at_1_losses"]),
        "historical_hit_at_20": float(revision["historical_hit_at_20"]),
        "current_hit_at_20": float(revision["current_hit_at_20"]),
        "hit_at_20_gains": int(revision["hit_at_20_gains"]),
        "hit_at_20_losses": int(revision["hit_at_20_losses"]),
        "rank_changes": int(revision["rank_changes"]),
    }
    return output


def latex_escape(value: Any) -> str:
    if value is None or (
        isinstance(value, (float, np.floating)) and math.isnan(float(value))
    ):
        return "none"
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(
        replacements.get(character, character) for character in str(value)
    )


def latex_percent(value: Any, decimals: int = 2) -> str:
    if pd.isna(value):
        return "--"
    return f"{float(value) * 100:.{decimals}f}\\%"


def latex_points(value: Any, decimals: int = 2) -> str:
    if pd.isna(value):
        return "--"
    return f"{float(value) * 100:+.{decimals}f}"


def append_longtable(
    lines: list[str],
    *,
    columns: str,
    headers: Sequence[str],
    rows: Iterable[Sequence[Any]],
    caption: str,
    label_name: str,
    font_size: str = "scriptsize",
    tabcolsep: str = "1.5pt",
) -> None:
    header = " & ".join(f"\\textbf{{{latex_escape(value)}}}" for value in headers)
    lines.extend(
        [
            f"\\begin{{{font_size}}}",
            f"\\setlength{{\\tabcolsep}}{{{tabcolsep}}}",
            "\\renewcommand{\\arraystretch}{1.05}",
            f"\\begin{{longtable}}{{@{{}}{columns}@{{}}}}",
            f"\\caption{{{caption}}}\\label{{{label_name}}}\\\\",
            "\\toprule",
            f"{header} \\\\",
            "\\midrule",
            "\\endfirsthead",
            "\\toprule",
            f"{header} \\\\",
            "\\midrule",
            "\\endhead",
        ]
    )
    for row in rows:
        lines.append(
            " & ".join(str(value) for value in row) + r" \\"
        )
    lines.extend(
        [
            "\\bottomrule",
            "\\end{longtable}",
            f"\\end{{{font_size}}}",
            "",
        ]
    )


def append_figure(
    lines: list[str],
    *,
    filename: str,
    caption: str,
    label_name: str,
    insights: Sequence[str],
) -> None:
    lines.extend(
        [
            "\\clearpage",
            "\\begin{figure}[htbp]",
            "\\centering",
            (
                "\\includegraphics[width=0.96\\linewidth,"
                f"height=0.58\\textheight,keepaspectratio]{{{filename}}}"
            ),
            f"\\caption{{{caption}}}",
            f"\\label{{{label_name}}}",
        ]
    )
    if insights:
        lines.append("\\begin{minipage}{0.94\\linewidth}")
        lines.append("\\raggedright")
        lines.append("\\textbf{Figure insights}")
        lines.append("\\begin{enumerate}")
        lines.extend(f"\\item {insight}" for insight in insights)
        lines.append("\\end{enumerate}")
        lines.append("\\end{minipage}")
    lines.extend(["\\end{figure}", "\\FloatBarrier", ""])


def write_meeting_10_competitor_section(
    *,
    metrics: pd.DataFrame,
    runtime: pd.DataFrame,
    fingerprints: pd.DataFrame,
    dense_config: pd.DataFrame,
    metric_summary: pd.DataFrame,
    pareto: pd.DataFrame,
    paired: pd.DataFrame,
    paired_examples: pd.DataFrame,
    drivers: pd.DataFrame,
    worst_slices: pd.DataFrame,
    a5_taxonomy: pd.DataFrame,
    oracle: pd.DataFrame,
    sensitivity: pd.DataFrame,
    variant_sensitivity: pd.DataFrame,
    external_ablations: pd.DataFrame,
    a5_ocr_metrics: pd.DataFrame,
    a5_ocr_examples: pd.DataFrame,
    a5_synthetic_metrics: pd.DataFrame,
    a5_synthetic_examples: pd.DataFrame,
    a5_revision_summary: pd.DataFrame,
    a5_revision_examples: pd.DataFrame,
    extreme_distribution: pd.DataFrame,
    extreme_systems: pd.DataFrame,
    extreme_examples: pd.DataFrame,
    remaining_ocr_failures: pd.DataFrame,
    correlations: pd.DataFrame,
    ann_audit: pd.DataFrame,
) -> None:
    inventory = inventory_lookup()
    lines = [
        r"\section{Expanded GitHub Competitor and Algorithm 5 Benchmark}",
        (
            f"This locked extension compares {len(ALL_ALGORITHM_IDS)} retrieval "
            f"configurations on the same 464 fair OCR pairs and 66,257 synthetic "
            f"clean-core pairs against the same 17,476-family Egyptian medicine "
            f"catalog. The external inventory contains {len(inventory)} "
            "evaluated, cached, represented, duplicate, or excluded entries. "
            "Algorithms 1--3 use their cached row-level predictions; they were "
            "not executed again."
        ),
        "",
        r"\subsection{Scope and Counting Rules}",
        (
            "A system earns one vote per distinct query-target pair. Hit@1 means "
            "the verified family is first. Hit@20 means it occurs anywhere in the "
            "first 20. Each system rate has a 95\\% Wilson interval. Paired "
            "system differences use matched case switches, multinomial 95\\% "
            "intervals, exact McNemar tests, and Holm correction."
        ),
        (
            "Dense biomedical baselines use their published checkpoints as "
            "frozen encoders and index the Egyptian family names directly. No "
            "OCR target labels are used for fine-tuning, so these rows measure "
            "off-the-shelf retrieval rather than a supervised upper bound."
        ),
        (
            "The repository search, completed on 24 July 2026, covered fuzzy "
            "and approximate string matching, spelling correction, browser and "
            "server search, drug-name normalization, biomedical entity "
            "normalization, and sparse or dense retrieval. The final inventory "
            "records method-level inclusion decisions instead of counting "
            "multiple wrappers around the same ranking rule as new evidence."
        ),
        "",
    ]

    status_counts = inventory["status"].value_counts()
    append_longtable(
        lines,
        columns="L{0.24\\linewidth}rrL{0.36\\linewidth}",
        headers=("Benchmark group", "Systems or entries", "Executed rows", "Meaning"),
        rows=(
            (
                "Newly evaluated configurations",
                int(status_counts.get("evaluated", 0)),
                f"{len(competitor_runner.EVALUATED_COMPETITORS) * (464 + 66257):,}",
                "A distinct scoring or retrieval configuration was executed on both locked datasets.",
            ),
            (
                "Cached classical baselines",
                6,
                f"{6 * (464 + 66257):,}",
                "Six existing classical row-level rankings were reused.",
            ),
            (
                "Cached project Algorithms 1--4",
                4,
                f"{4 * (464 + 66257):,}",
                "Existing paired rows were reused; Algorithms 1--3 were not executed again.",
            ),
            (
                "Current Algorithm 5",
                1,
                f"{464 + 66257:,}",
                "The complete evidence-guided system was evaluated on both locked datasets.",
            ),
            (
                "Represented by measured components",
                int(status_counts.get("represented", 0)),
                "0",
                "The repository wraps or serves a scoring family already measured directly.",
            ),
            (
                "Duplicate implementation",
                int(status_counts.get("duplicate", 0)),
                "0",
                "The implementation changes speed, not candidate ordering.",
            ),
            (
                "Not comparable",
                int(status_counts.get("excluded", 0)),
                "0",
                "The system needs a different ontology, contextual training data, or a server-specific ranking contract.",
            ),
        ),
        caption=(
            "Benchmark and open-source inventory disposition. The "
            f"{len(competitor_runner.EVALUATED_COMPETITORS)} new, six "
            "classical, four cached project, and one current project systems sum "
            f"to {len(ALL_ALGORITHM_IDS)}. The {len(inventory)}-entry repository "
            "inventory covers the "
            "distinct feasible method families found in the documented search; "
            "it is not a claim that every GitHub repository ever created was "
            "enumerated."
        ),
        label_name="tab:expanded-inventory-counts",
        font_size="small",
    )
    append_longtable(
        lines,
        columns="L{0.35\\linewidth}L{0.35\\linewidth}",
        headers=("Runtime component", "Recorded value"),
        rows=(
            (
                latex_escape(row.software),
                latex_escape(row.version),
            )
            for row in runtime.itertuples()
        ),
        caption=(
            "Software versions and hardware used to generate the expanded "
            "benchmark. The pinned requirements file matches the package rows; "
            "latency values are specific to this machine."
        ),
        label_name="tab:expanded-runtime-versions",
        font_size="small",
    )
    append_longtable(
        lines,
        columns="L{0.14\\linewidth}rrL{0.23\\linewidth}L{0.38\\linewidth}",
        headers=(
            "Dataset file",
            "Source rows",
            "Evaluated pairs",
            "Selection",
            "SHA-256",
        ),
        rows=(
            (
                latex_escape(DATASET_NAMES.get(row.dataset, row.dataset)),
                int(row.source_rows),
                int(row.evaluated_pairs),
                latex_escape(row.selection),
                f"\\texttt{{\\seqsplit{{{row.sha256}}}}}",
            )
            for row in fingerprints.itertuples()
        ),
        caption=(
            "Exact input-file fingerprints and denominator construction. The "
            "OCR source retains 595 diagnostic rows; accepted fair filtering "
            "and query-target deduplication produce 464 evaluated pairs."
        ),
        label_name="tab:expanded-dataset-fingerprints",
        font_size="scriptsize",
        tabcolsep="1pt",
    )
    lines.append("\\begin{landscape}")
    append_longtable(
        lines,
        columns="L{0.16\\linewidth}L{0.27\\linewidth}L{0.22\\linewidth}rrrr",
        headers=(
            "Dense system",
            "Checkpoint",
            "Snapshot revision",
            "Dim.",
            "HNSW M",
            "Build ef",
            "Search ef",
        ),
        rows=(
            (
                latex_escape(row.algorithm_name),
                f"\\path{{{row.model_name}}}",
                f"\\path{{{row.model_revision}}}",
                int(row.dimensions),
                int(row.hnsw_m),
                int(row.hnsw_ef_construction),
                int(row.hnsw_ef_search),
            )
            for row in dense_config.itertuples()
        ),
        caption=(
            "Exact frozen biomedical checkpoints and shared HNSW settings. "
            "Every encoder uses CLS pooling before the pooler, L2 normalization, "
            "top 20 retrieval, and index seed 20260723."
        ),
        label_name="tab:expanded-dense-configuration",
        font_size="tiny",
        tabcolsep="1pt",
    )
    lines.extend(["\\end{landscape}", ""])

    for dataset, title, case_count, table_label in (
        ("ocr_464", "464 fair OCR query-target pairs", 464, "ocr"),
        (
            "synthetic_66257",
            "66,257 synthetic clean-core query-target pairs",
            66257,
            "synthetic",
        ),
    ):
        frame = metrics[metrics["dataset"].eq(dataset)].reset_index(drop=True)
        best_hit_at_1 = frame["hit_at_1"].max()
        best_hit_at_20 = frame["hit_at_20"].max()
        best_latency = frame["median_latency_ms"].min()
        leaderboard_rows = []
        for rank, row in enumerate(frame.itertuples(), 1):
            h1 = (
                f"{latex_percent(row.hit_at_1)} "
                f"[{latex_percent(row.hit_at_1_ci_low)}, "
                f"{latex_percent(row.hit_at_1_ci_high)}]"
            )
            h20 = (
                f"{latex_percent(row.hit_at_20)} "
                f"[{latex_percent(row.hit_at_20_ci_low)}, "
                f"{latex_percent(row.hit_at_20_ci_high)}]"
            )
            if row.hit_at_1 == best_hit_at_1:
                h1 = f"\\textbf{{{h1}}}"
            if row.hit_at_20 == best_hit_at_20:
                h20 = f"\\textbf{{{h20}}}"
            latency = f"{row.median_latency_ms:.3f}"
            if row.median_latency_ms == best_latency:
                latency = f"\\textbf{{{latency}}}"
            leaderboard_rows.append(
                (
                    rank,
                    latex_escape(row.algorithm_name),
                    latex_escape(row.method_family),
                    h1,
                    latex_percent(row.hit_at_5),
                    h20,
                    f"{row.mrr_at_20:.4f}",
                    latex_percent(row.no_result_rate),
                    f"{row.mean_candidate_count:.1f}",
                    f"{row.preparation_ms / 1000:.3f}",
                    latency,
                    f"{row.p95_latency_ms:.3f}",
                    int(row.failure_count),
                )
            )
        lines.extend(["\\begin{landscape}", f"\\subsection{{Full Leaderboard: {title}}}"])
        append_longtable(
            lines,
            columns="rL{0.18\\linewidth}L{0.11\\linewidth}rrrrrrrrrr",
            headers=(
                "Rank",
                "System",
                "Method family",
                "Hit@1 (95% CI)",
                "Hit@5",
                "Hit@20 (95% CI)",
                "MRR@20",
                "No result",
                "Mean cand.",
                "Prep. s",
                "Median ms",
                "P95 ms",
                "H@20 misses",
            ),
            rows=leaderboard_rows,
            caption=(
                f"Complete {len(frame)}-system leaderboard on {case_count:,} "
                "locked pairs. Prep is one-time index construction. Median and "
                "P95 are measured scoring time per query; vectorized methods "
                "divide batch time by batch size, while project algorithms time "
                "individual calls. No result means zero returned "
                "families. Mean candidates is the implementation-reported list "
                "size; external adapters expose at most 20 while project systems "
                "can expose a larger internal list, so this column is diagnostic "
                "rather than a normalized efficiency comparison."
            ),
            label_name=f"tab:expanded-{table_label}-leaderboard",
            font_size="tiny",
            tabcolsep="0.7pt",
        )
        lines.append("\\end{landscape}")
        lines.append("")

    flex_default_ocr = metrics[
        metrics["dataset"].eq("ocr_464")
        & metrics["algorithm"].eq("flexsearch_tolerant_default")
    ].iloc[0]
    flex_extra_ocr = metrics[
        metrics["dataset"].eq("ocr_464")
        & metrics["algorithm"].eq("flexsearch_tolerant_extra")
    ].iloc[0]
    append_figure(
        lines,
        filename="12_candidate_coverage_vs_recovery.png",
        caption=(
            "Each point is one retrieval system. The x-axis is the percentage "
            "of queries returning zero candidates, and the y-axis is Hit@20; "
            "upper-left therefore combines broad candidate coverage with high "
            "verified-family recovery. The left panel contains 464 fair OCR "
            "pairs and the right contains 66,257 synthetic pairs."
        ),
        label_name="fig:expanded-coverage-recovery",
        insights=(
            "A zero-candidate error is a retrieval failure and cannot be fixed by reranking the returned list.",
            (
                "On OCR, FlexSearch tolerant default returns no candidate for "
                f"{flex_default_ocr.no_result_rate * 100:.2f}\\% of queries; "
                "LatinExtra lowers that rate to "
                f"{flex_extra_ocr.no_result_rate * 100:.2f}\\% and raises "
                f"Hit@20 from {flex_default_ocr.hit_at_20 * 100:.2f}\\% to "
                f"{flex_extra_ocr.hit_at_20 * 100:.2f}\\%."
            ),
        ),
    )

    lines.extend(
        [
            r"\subsection{System Distribution and Efficiency Frontier}",
            (
                f"Distribution statistics use all {len(ALL_ALGORITHM_IDS)} "
                "systems. The Pareto table "
                "keeps a system only when no measured alternative is both at "
                "least as accurate at Hit@1 and at least as fast in median "
                "measured scoring time per query."
            ),
            "",
        ]
    )
    lines.append("\\begin{landscape}")
    append_longtable(
        lines,
        columns="L{0.10\\linewidth}L{0.13\\linewidth}L{0.19\\linewidth}rL{0.19\\linewidth}rrrr",
        headers=(
            "Dataset",
            "Metric",
            "Best system",
            "Best",
            "Worst system",
            "Worst",
            "Mean",
            "Median",
            "Std. dev.",
        ),
        rows=(
            (
                latex_escape(DATASET_NAMES.get(row.dataset, row.dataset)),
                latex_escape(row.metric),
                latex_escape(row.best_system),
                f"{row.best_value:.4f}",
                latex_escape(row.worst_system),
                f"{row.worst_value:.4f}",
                f"{row.mean:.4f}",
                f"{row.median:.4f}",
                f"{row.standard_deviation:.4f}",
            )
            for row in metric_summary.itertuples()
        ),
        caption=(
            "Best, worst, mean, median, and sample standard deviation across "
            f"the complete {len(ALL_ALGORITHM_IDS)}-system roster. Rate metrics "
            "are fractions; time metrics are milliseconds."
        ),
        label_name="tab:expanded-metric-distribution",
        font_size="tiny",
        tabcolsep="0.8pt",
    )
    lines.extend(["\\end{landscape}", ""])
    append_longtable(
        lines,
        columns="L{0.14\\linewidth}L{0.35\\linewidth}rrrrr",
        headers=(
            "Dataset",
            "Non-dominated system",
            "Hit@1",
            "Hit@20",
            "Median ms",
            "P95 ms",
            "Prep. s",
        ),
        rows=(
            (
                latex_escape(DATASET_NAMES.get(row.dataset, row.dataset)),
                latex_escape(row.algorithm_name),
                latex_percent(row.hit_at_1),
                latex_percent(row.hit_at_20),
                f"{row.median_latency_ms:.4f}",
                f"{row.p95_latency_ms:.4f}",
                f"{row.preparation_ms / 1000:.3f}",
            )
            for row in pareto.itertuples()
        ),
        caption=(
            "Measured Hit@1 versus scoring-time Pareto frontier. Timing "
            "includes vectorized batch methods and per-query project methods, "
            "so this table identifies measured tradeoffs rather than production "
            "throughput guarantees."
        ),
        label_name="tab:expanded-pareto-frontier",
    )

    lines.extend(
        [
            r"\subsection{Algorithm 5 Source-Revision Audit}",
            (
                "The earlier clean-core acceptance artifact and the current "
                "Algorithm 5 source are paired by the same 66,257 case IDs. "
                "The current-source result is the value used everywhere in the "
                "expanded benchmark; the older value remains historical."
            ),
            "",
        ]
    )
    append_longtable(
        lines,
        columns="L{0.13\\linewidth}rrrrrrrrrr",
        headers=(
            "Split",
            "Cases",
            "Old H@1",
            "Current H@1",
            "H@1 gains",
            "H@1 losses",
            "Old H@20",
            "Current H@20",
            "H@20 gains",
            "H@20 losses",
            "Rank changes",
        ),
        rows=(
            (
                latex_escape(str(row.split).title()),
                int(row.cases),
                latex_percent(row.historical_hit_at_1, 4),
                latex_percent(row.current_hit_at_1, 4),
                int(row.hit_at_1_gains),
                int(row.hit_at_1_losses),
                latex_percent(row.historical_hit_at_20, 4),
                latex_percent(row.current_hit_at_20, 4),
                int(row.hit_at_20_gains),
                int(row.hit_at_20_losses),
                int(row.rank_changes),
            )
            for row in a5_revision_summary.itertuples()
        ),
        caption=(
            "Paired source-revision audit. The current OCR-oriented rules gain "
            "44 and lose 55 clean-core Hit@1 cases overall; holdout gains one "
            "net Hit@1 case, while development loses 12 and one development "
            "target moves outside the top 20."
        ),
        label_name="tab:expanded-a5-revision-drift",
        font_size="tiny",
        tabcolsep="1pt",
    )
    revision_examples = pd.concat(
        [
            a5_revision_examples[
                a5_revision_examples["change_type"].eq(change_type)
            ].head(limit)
            for change_type, limit in (
                ("Hit@20 loss", 1),
                ("Hit@20 gain", 1),
                ("Hit@1 gain", 5),
                ("Hit@1 loss", 5),
                ("rank-only change", 3),
            )
        ],
        ignore_index=True,
    )
    append_longtable(
        lines,
        columns="L{0.13\\linewidth}L{0.11\\linewidth}L{0.14\\linewidth}L{0.14\\linewidth}rL{0.14\\linewidth}r",
        headers=(
            "Change",
            "Input",
            "Expected",
            "Old top 1",
            "Old rank",
            "Current top 1",
            "Current rank",
        ),
        rows=(
            (
                latex_escape(row.change_type),
                f"\\texttt{{\\seqsplit{{{latex_escape(row.input)}}}}}",
                latex_escape(row.expected),
                latex_escape(row.top_1_historical),
                int(row.historical_rank),
                latex_escape(row.top_1_current),
                int(row.current_rank),
            )
            for row in revision_examples.itertuples()
        ),
        caption=(
            "Concrete paired changes between the historical and current "
            "Algorithm 5 source. Rank 999 means the verified family is outside "
            "the returned top 20."
        ),
        label_name="tab:expanded-a5-revision-examples",
    )

    ocr_metrics = metrics[metrics["dataset"].eq("ocr_464")]
    synthetic_metrics = metrics[metrics["dataset"].eq("synthetic_66257")]
    a5_ocr = ocr_metrics[
        ocr_metrics["algorithm"].eq("algorithm_5_evidence_rescue")
    ].iloc[0]
    a5_synthetic = synthetic_metrics[
        synthetic_metrics["algorithm"].eq("algorithm_5_evidence_rescue")
    ].iloc[0]
    best_ocr_external = ocr_metrics[
        ~ocr_metrics["algorithm"].isin(PROJECT_ALGORITHMS)
    ].iloc[0]
    best_ocr_external_hit_at_20 = ocr_metrics[
        ~ocr_metrics["algorithm"].isin(PROJECT_ALGORITHMS)
    ].sort_values(["hit_at_20", "hit_at_1"], ascending=False).iloc[0]
    best_synthetic_external = synthetic_metrics[
        ~synthetic_metrics["algorithm"].isin(PROJECT_ALGORITHMS)
    ].iloc[0]
    best_synthetic_external_hit_at_20 = synthetic_metrics[
        ~synthetic_metrics["algorithm"].isin(PROJECT_ALGORITHMS)
    ].sort_values(["hit_at_20", "hit_at_1"], ascending=False).iloc[0]
    cross_dataset = metrics.pivot(
        index="algorithm",
        columns="dataset",
        values="hit_at_1",
    )
    cross_dataset_rho = spearmanr(
        cross_dataset["ocr_464"],
        cross_dataset["synthetic_66257"],
    ).statistic

    append_figure(
        lines,
        filename="01_ocr_leaderboard.png",
        caption=(
            "Bars report Hit@1 and Hit@20 on the 464 fair OCR pairs. The x-axis "
            "is the percentage of queries whose verified family is recovered; "
            "the y-axis lists the leading systems plus project algorithms. "
            "Whiskers are 95\\% Wilson confidence intervals."
        ),
        label_name="fig:expanded-ocr-leaderboard",
        insights=(
            (
                f"Algorithm 5 reaches {latex_percent(a5_ocr['hit_at_1'])} Hit@1 "
                f"and {latex_percent(a5_ocr['hit_at_20'])} Hit@20."
            ),
            (
                f"The strongest external Hit@1 system is "
                f"{latex_escape(best_ocr_external['algorithm_name'])} at "
                f"{latex_percent(best_ocr_external['hit_at_1'])}; the strongest "
                f"external Hit@20 system is "
                f"{latex_escape(best_ocr_external_hit_at_20['algorithm_name'])} "
                f"at {latex_percent(best_ocr_external_hit_at_20['hit_at_20'])}."
            ),
        ),
    )
    append_figure(
        lines,
        filename="02_synthetic_leaderboard.png",
        caption=(
            "Bars report Hit@1 and Hit@20 on 66,257 synthetic clean-core pairs. "
            "The x-axis is recovery percentage and the y-axis lists systems. "
            "Whiskers are 95\\% Wilson confidence intervals."
        ),
        label_name="fig:expanded-synthetic-leaderboard",
        insights=(
            (
                f"Algorithm 5 reaches {latex_percent(a5_synthetic['hit_at_1'])} "
                f"Hit@1 and {latex_percent(a5_synthetic['hit_at_20'])} Hit@20."
            ),
            (
                f"The best external Hit@1 result is "
                f"{latex_escape(best_synthetic_external['algorithm_name'])} at "
                f"{latex_percent(best_synthetic_external['hit_at_1'])}."
            ),
            (
                f"The best external Hit@20 result is "
                f"{latex_escape(best_synthetic_external_hit_at_20['algorithm_name'])} "
                f"at {latex_percent(best_synthetic_external_hit_at_20['hit_at_20'])}."
            ),
        ),
    )
    append_figure(
        lines,
        filename="03_cross_dataset_hit_at_1.png",
        caption=(
            "Each point is one system. The x-axis is Hit@1 on real OCR pairs and "
            "the y-axis is Hit@1 on synthetic pairs. Upper-left points perform "
            "well on generated edits but poorly on observed OCR corruption."
        ),
        label_name="fig:expanded-cross-dataset",
        insights=(
            (
                "System ordering transfers strongly but not perfectly "
                f"(Spearman rank correlation $\\rho={cross_dataset_rho:.3f}$), "
                "while absolute synthetic scores remain much higher."
            ),
            "Damerau-Levenshtein is strong on controlled edits, while Algorithm 5 retains the best observed OCR result.",
        ),
    )

    for dataset, dataset_metrics, dataset_name, table_label in (
        ("ocr_464", ocr_metrics, "464 fair OCR pairs", "ocr"),
        (
            "synthetic_66257",
            synthetic_metrics,
            "66,257 synthetic pairs",
            "synthetic",
        ),
    ):
        paired_table = paired[paired["dataset"].eq(dataset)].copy()
        paired_table = paired_table.merge(
            dataset_metrics[["algorithm", "hit_at_1", "hit_at_20"]],
            left_on="comparison_algorithm",
            right_on="algorithm",
            how="left",
        ).sort_values("hit_at_1", ascending=False)
        lines.append("\\begin{landscape}")
        append_longtable(
            lines,
            columns="L{0.22\\linewidth}rrrrrrrrrr",
            headers=(
                "Comparison",
                "Comp. H@1",
                "A5-comp. H@1 (95% CI)",
                "A5-only 1",
                "Comp.-only 1",
                "Holm p1",
                "Comp. H@20",
                "A5-comp. H@20 (95% CI)",
                "A5-only 20",
                "Comp.-only 20",
                "Holm p20",
            ),
            rows=(
                (
                    latex_escape(row.comparison_name),
                    latex_percent(row.hit_at_1),
                    (
                        f"{latex_points(row.difference_hit_at_1)} "
                        f"[{latex_points(row.difference_ci_low_hit_at_1)}, "
                        f"{latex_points(row.difference_ci_high_hit_at_1)}]"
                    ),
                    int(row.a5_only_hit_at_1),
                    int(row.comparison_only_hit_at_1),
                    f"{row.mcnemar_holm_p_hit_at_1:.4g}",
                    latex_percent(row.hit_at_20),
                    (
                        f"{latex_points(row.difference_hit_at_20)} "
                        f"[{latex_points(row.difference_ci_low_hit_at_20)}, "
                        f"{latex_points(row.difference_ci_high_hit_at_20)}]"
                    ),
                    int(row.a5_only_hit_at_20),
                    int(row.comparison_only_hit_at_20),
                    f"{row.mcnemar_holm_p_hit_at_20:.4g}",
                )
                for row in paired_table.itertuples()
            ),
            caption=(
                f"Every paired system comparison against Algorithm 5 on "
                f"{dataset_name}. A5-only and comparison-only counts are the "
                "discordant cases. Exact McNemar p-values are Holm-adjusted "
                f"across the {len(ALL_ALGORITHM_IDS) - 1} comparisons; deltas "
                "and paired 95\\% intervals "
                "are in percentage points."
            ),
            label_name=f"tab:expanded-paired-{table_label}",
            font_size="tiny",
            tabcolsep="0.8pt",
        )
        lines.extend(["\\end{landscape}", ""])

    report_paired_examples = (
        paired_examples.sort_values(
            ["comparison_name", "scenario", "edit_distance", "input"]
        )
        .groupby(
            ["comparison_algorithm", "scenario"],
            observed=True,
            as_index=False,
        )
        .head(2)
    )
    lines.append("\\begin{landscape}")
    append_longtable(
        lines,
        columns="L{0.14\\linewidth}L{0.17\\linewidth}L{0.09\\linewidth}L{0.10\\linewidth}rL{0.10\\linewidth}rrL{0.10\\linewidth}rL{0.10\\linewidth}",
        headers=(
            "Comparison",
            "Paired outcome",
            "Input",
            "Expected",
            "Edits",
            "Operation",
            "Bigrams",
            "A5 rank",
            "A5 top 1",
            "Comp. rank",
            "Comp. top 1",
        ),
        rows=(
            (
                latex_escape(row.comparison_name),
                latex_escape(row.scenario),
                latex_escape(row.input),
                latex_escape(row.expected),
                int(row.edit_distance),
                latex_escape(str(row.operation_profile).replace("_", " ")),
                int(row.shared_bigrams),
                int(row.a5_rank),
                latex_escape(row.a5_top_1),
                int(row.comparison_rank),
                latex_escape(row.comparison_top_1),
            )
            for row in report_paired_examples.itertuples()
        ),
        caption=(
            "Concrete paired OCR outcomes for six representative competitors. "
            "Two rows are shown per comparison and outcome class; rank 999 "
            "means the verified family is outside the top 20. The complete "
            "example set remains in "
            "\\texttt{paired\\_ocr\\_examples.csv}."
        ),
        label_name="tab:expanded-paired-ocr-examples",
        font_size="tiny",
        tabcolsep="0.8pt",
    )
    lines.extend(["\\end{landscape}", ""])

    for dataset, dataset_name, table_label in (
        ("ocr_464", "464 fair OCR pairs", "ocr"),
        ("synthetic_66257", "66,257 synthetic pairs", "synthetic"),
    ):
        driver_rows = drivers[drivers["dataset"].eq(dataset)].sort_values(
            ["distance_4_plus_hit_at_20", "mixed_hit_at_20"],
            ascending=False,
        )
        lines.append("\\begin{landscape}")
        append_longtable(
            lines,
            columns="L{0.25\\linewidth}rrrrrrrrr",
            headers=(
                "System",
                "d<=3 H@20",
                "d>=4 H@20",
                "rho(d,H@20)",
                "0 bigrams",
                "2+ bigrams",
                "short query",
                "long query",
                "mixed ops.",
                "extreme",
            ),
            rows=(
                (
                    latex_escape(row.algorithm_name),
                    latex_percent(row.distance_0_3_hit_at_20),
                    latex_percent(row.distance_4_plus_hit_at_20),
                    (
                        "--"
                        if pd.isna(row.spearman_edit_distance_vs_hit_at_20)
                        else f"{row.spearman_edit_distance_vs_hit_at_20:+.3f}"
                    ),
                    latex_percent(row.zero_bigram_hit_at_20),
                    latex_percent(row.two_plus_bigram_hit_at_20),
                    latex_percent(row.short_query_hit_at_20),
                    latex_percent(row.long_query_hit_at_20),
                    latex_percent(row.mixed_hit_at_20),
                    latex_percent(row.extreme_hit_at_20),
                )
                for row in driver_rows.itertuples()
            ),
            caption=(
                f"Failure-driver profile for every system on {dataset_name}. "
                "A bigram is two adjacent characters, for example AB, BA, and "
                "AS in ABAS. Short means at most four compact characters; long "
                "means at least eight; mixed combines two or more edit "
                "mechanisms; extreme means compact edit distance divided by "
                "compact target length exceeds 0.60. Spearman rho reports the "
                "monotonic association between edit count and binary Hit@20; "
                "negative values mean recovery tends to fall as edits increase."
            ),
            label_name=f"tab:expanded-{table_label}-error-drivers",
            font_size="tiny",
            tabcolsep="1pt",
        )
        lines.extend(["\\end{landscape}", ""])
        weakest = (
            worst_slices[worst_slices["dataset"].eq(dataset)]
            .sort_values(
                ["hit_at_20", "hit_at_1", "cases"],
                ascending=[True, True, False],
            )
            .groupby("algorithm", as_index=False, observed=True)
            .head(1)
            .sort_values(["hit_at_20", "algorithm_name"])
        )
        append_longtable(
            lines,
            columns="L{0.35\\linewidth}L{0.18\\linewidth}L{0.23\\linewidth}rrr",
            headers=(
                "System",
                "Worst dimension",
                "Worst supported group",
                "Cases",
                "Hit@1",
                "Hit@20",
            ),
            rows=(
                (
                    latex_escape(row.algorithm_name),
                    latex_escape(row.dimension.replace("_", " ")),
                    latex_escape(str(row.weakest_group).replace("_", " ")),
                    int(row.cases),
                    latex_percent(row.hit_at_1),
                    latex_percent(row.hit_at_20),
                )
                for row in weakest.itertuples()
            ),
            caption=(
                f"Worst sufficiently populated slice for every system on "
                f"{dataset_name}. The search considers mistake category, error "
                "type, operation family and profile, edit distance, query "
                "length, and shared-bigram evidence. A group needs at least 10 "
                "cases before it can be called a system's weakest slice."
            ),
            label_name=f"tab:expanded-{table_label}-weakest-slice",
        )

    lines.extend(
        [
            r"\subsection{Algorithm 5 Failure Taxonomy}",
            (
                "Failure rate is misses divided by rows in one subgroup. Failure "
                "share is subgroup misses divided by all Algorithm 5 top-20 "
                "misses in that dataset."
            ),
            "",
        ]
    )
    for dataset, dataset_name, table_label in (
        ("ocr_464", "464 fair OCR pairs", "ocr"),
        ("synthetic_66257", "66,257 synthetic pairs", "synthetic"),
    ):
        taxonomy_rows = a5_taxonomy[a5_taxonomy["dataset"].eq(dataset)]
        taxonomy_scope = "every measured"
        if dataset == "synthetic_66257":
            broad_rows = taxonomy_rows[
                taxonomy_rows["dimension"].ne("error_type")
            ]
            high_impact_error_rows = (
                taxonomy_rows[taxonomy_rows["dimension"].eq("error_type")]
                .sort_values(
                    ["failure_count", "failure_rate", "cases"],
                    ascending=[False, False, False],
                )
                .head(50)
            )
            taxonomy_rows = pd.concat(
                [broad_rows, high_impact_error_rows],
                ignore_index=True,
            )
            taxonomy_scope = (
                "all broader groups and the 50 error labels with the largest "
                "top-20 failure impact"
            )
        lines.append("\\begin{landscape}")
        append_longtable(
            lines,
            columns="L{0.16\\linewidth}L{0.22\\linewidth}rrrrrr",
            headers=(
                "Dimension",
                "Group",
                "Cases",
                "H@1",
                "H@20",
                "Misses",
                "Failure rate",
                "Failure share",
            ),
            rows=(
                (
                    latex_escape(row.dimension.replace("_", " ")),
                    latex_escape(str(row.group).replace("_", " ")),
                    int(row.cases),
                    latex_percent(row.hit_at_1),
                    latex_percent(row.hit_at_20),
                    int(row.failure_count),
                    latex_percent(row.failure_rate),
                    latex_percent(row.failure_share),
                )
                for row in taxonomy_rows.itertuples()
            ),
            caption=(
                f"Complete Algorithm 5 mistake and evidence taxonomy on "
                f"{dataset_name}. The report retains {taxonomy_scope}. "
                "The full row-level taxonomy, including all 4,184 synthetic "
                "error labels, remains in "
                "\\texttt{a5\\_failure\\_taxonomy.csv}."
            ),
            label_name=f"tab:expanded-a5-{table_label}-taxonomy",
            font_size="tiny",
            tabcolsep="0.8pt",
        )
        lines.extend(["\\end{landscape}", ""])
    append_figure(
        lines,
        filename="09_algorithm_5_by_operation_profile.png",
        caption=(
            "Blue bars report Hit@1 and orange bars report Hit@20 within each "
            "Algorithm 5 operation group. The OCR panel uses mechanical edit "
            "profiles such as substitution-only and mixed operations. The "
            "synthetic panel uses generator families such as visual/OCR, "
            "keyboard, phonetic, and vowel corruption. Each y-axis label prints "
            "its own denominator, so labels are not assumed equivalent across "
            "the two datasets."
        ),
        label_name="fig:expanded-a5-operation-profile",
        insights=(
            "Mixed-operation corruption is materially harder than a single isolated edit mechanism.",
            "The OCR and synthetic gaps differ, so synthetic operation labels cannot replace observed OCR evaluation.",
        ),
    )
    append_figure(
        lines,
        filename="04_hit_at_20_by_edit_distance.png",
        caption=(
            "The x-axis is compact Levenshtein edit count and the y-axis is "
            "Hit@20 within that exact-distance group. The left panel uses OCR "
            "pairs; the right uses synthetic pairs. Each x-axis tick also gives "
            "the number of query-target pairs at that distance."
        ),
        label_name="fig:expanded-distance-profile",
        insights=(
            "All lexical systems lose recall as edits accumulate, but the decline is much sharper on observed OCR.",
            "Algorithm 5 gains are concentrated in multi-edit retrieval, not exact matching.",
        ),
    )
    correlation_features = (
        "edit_distance",
        "normalized_distance",
        "query_length",
        "shared_bigrams",
        "candidate_count",
        "latency_ms",
    )
    h20_correlations = correlations[
        correlations["feature_y"].eq("hit_at_20")
        & correlations["feature_x"].isin(correlation_features)
    ].copy()
    h20_correlations["direction"] = np.select(
        [
            h20_correlations["spearman_rho"].gt(0),
            h20_correlations["spearman_rho"].lt(0),
        ],
        [
            "higher values occur with more recovery",
            "higher values occur with less recovery",
        ],
        default="no monotonic association",
    )
    append_longtable(
        lines,
        columns="L{0.19\\linewidth}L{0.25\\linewidth}rL{0.38\\linewidth}",
        headers=("Dataset", "Measured variable", "Spearman rho", "Reading"),
        rows=(
            (
                (
                    "464 fair OCR pairs"
                    if row.dataset == "ocr_464"
                    else "66,257 synthetic pairs"
                ),
                latex_escape(row.feature_x_name),
                (
                    "--"
                    if pd.isna(row.spearman_rho)
                    else f"{float(row.spearman_rho):+.3f}"
                ),
                latex_escape(row.direction),
            )
            for row in h20_correlations.itertuples()
        ),
        caption=(
            "Algorithm 5 rank correlations with Hit@20. Spearman rho measures "
            "whether larger values tend to occur with higher or lower recovery; "
            "it does not establish causation. OCR shared-bigram evidence is the "
            "exact count. Synthetic artifacts retain bands, encoded 0, 1, 2, "
            "and 4 for zero, one, two-to-three, and four-plus shared bigrams."
        ),
        label_name="tab:expanded-a5-h20-correlations",
        font_size="small",
    )
    strongest_relations = []
    for dataset, dataset_name in (
        ("ocr_464", "OCR"),
        ("synthetic_66257", "synthetic"),
    ):
        if dataset == "synthetic_66257":
            synthetic_misses = int(
                round((1.0 - float(a5_synthetic["hit_at_20"])) * 66_257)
            )
            if synthetic_misses <= 5:
                strongest_relations.append(
                    f"Synthetic Hit@20 has only {synthetic_misses} miss"
                    f"{'' if synthetic_misses == 1 else 'es'}, so its near-zero "
                    "feature correlations are a ceiling effect rather than "
                    "stable failure-driver estimates."
                )
                continue
        dataset_rows = h20_correlations[
            h20_correlations["dataset"].eq(dataset)
            & h20_correlations["spearman_rho"].notna()
        ].copy()
        if dataset_rows.empty:
            continue
        strongest = dataset_rows.loc[
            dataset_rows["spearman_rho"].abs().idxmax()
        ]
        strongest_relations.append(
            f"On {dataset_name}, the strongest measured monotonic relation "
            f"with Hit@20 is {latex_escape(strongest.feature_x_name)} "
            f"($\\rho={float(strongest.spearman_rho):+.3f}$)."
        )
    append_figure(
        lines,
        filename="13_algorithm_5_feature_correlations.png",
        caption=(
            "Each cell reports Spearman rank correlation for Algorithm 5. Rows "
            "and columns contain compact edit count, edit count divided by "
            "target length, query length, shared-bigram evidence, returned "
            "candidate count, Hit@1, Hit@20, and latency. Blue cells are "
            "positive, red cells are negative, and values near zero have little "
            "monotonic association. Synthetic shared-bigram evidence uses the "
            "ordinal band encoding defined in Table "
            "\\ref{tab:expanded-a5-h20-correlations}."
        ),
        label_name="fig:expanded-a5-correlations",
        insights=tuple(strongest_relations),
    )

    lines.extend(
        [
            r"\subsection{External Composite Ablations and Controlled Variants}",
            (
                "A strict component ablation replaces a complete composite with "
                "one measured branch. Parameter sensitivity changes a radius, "
                "similarity, tokenizer, encoder, or weighting rule without "
                "claiming that the changed configuration is a component removal."
            ),
            "",
        ]
    )
    lines.append("\\begin{landscape}")
    append_longtable(
        lines,
        columns="L{0.20\\linewidth}L{0.18\\linewidth}L{0.54\\linewidth}",
        headers=(
            "Method family",
            "Analysis type",
            "What is compared",
        ),
        rows=(
            (
                "RapidFuzz and character distances",
                "Atomic scorer or controlled variant",
                "Full, partial, token, Jaro, LCS, Levenshtein, OSA, and Damerau orderings are separate complete scorers; removing a component from one is undefined.",
            ),
            (
                "q-gram and BM25 retrieval",
                "Parameter sensitivity",
                "Two- versus three-character grams, four QuickUMLS coefficients, and Okapi versus BM25L/BM25Plus isolate token size and scoring formula.",
            ),
            (
                "SymSpell",
                "Component plus radius",
                "Uniform versus catalog frequency removes tie evidence; maximum edit radius two versus three changes candidate coverage.",
            ),
            (
                "Phonetic encoders",
                "Model-family comparison",
                "Soundex, Metaphone, NYSIIS, Match Rating Codex, and the domain phonetic baseline are atomic encoders followed by the same edit tie ordering.",
            ),
            (
                "Biomedical dense retrieval",
                "Checkpoint and index audit",
                "BiomedBERT, SapBERT, and CODER++ use the same pooling and catalog; HNSW top-20 recall is checked against exact dense search.",
            ),
            (
                "BioSyn and xMEN",
                "Strict branch removal",
                "Dense-only and sparse-only branches are compared with weighted hybrid or reciprocal-rank fusion.",
            ),
            (
                "preon",
                "Strict stage removal",
                "The token stage and normalized-Levenshtein partial stage are each removed from the published cascade.",
            ),
            (
                "Fuse.js",
                "Parameter sensitivity",
                "The default Bitap ranking is compared with the library's token-search mode on the same catalog and queries.",
            ),
            (
                "FlexSearch",
                "Tokenizer and encoder sensitivity",
                "Tolerant versus full tokenization and default, LatinAdvanced, and LatinExtra encoders isolate index expansion and phonetic normalization.",
            ),
            (
                "Algorithm 5",
                "Named and atomic removal",
                "Forty-two named components or groups and 54 feature flags are removed on OCR, alongside one complete reference; 12 broad removals plus the complete reference are rerun on all synthetic pairs.",
            ),
        ),
        caption=(
            "Ablation coverage by method family. A component removal is reported "
            "only when a complete system contains separable branches; atomic "
            "scorers receive controlled variants instead of artificial ablations."
        ),
        label_name="tab:expanded-ablation-coverage",
        font_size="scriptsize",
        tabcolsep="1.2pt",
    )
    lines.extend(["\\end{landscape}", ""])
    lines.append("\\begin{landscape}")
    append_longtable(
        lines,
        columns="L{0.09\\linewidth}L{0.13\\linewidth}rL{0.17\\linewidth}rL{0.17\\linewidth}rrL{0.17\\linewidth}r",
        headers=(
            "Dataset",
            "Method family",
            "Configs.",
            "Best Hit@1 system",
            "Best H@1",
            "Worst Hit@1 system",
            "Worst H@1",
            "H@1 spread",
            "Best Hit@20 system",
            "Best H@20",
        ),
        rows=(
            (
                latex_escape(DATASET_NAMES.get(row.dataset, row.dataset)),
                latex_escape(row.method_family),
                int(row.configurations),
                latex_escape(row.best_hit_at_1_system),
                latex_percent(row.best_hit_at_1),
                latex_escape(row.worst_hit_at_1_system),
                latex_percent(row.worst_hit_at_1),
                latex_points(row.hit_at_1_spread),
                latex_escape(row.best_hit_at_20_system),
                latex_percent(row.best_hit_at_20),
            )
            for row in sensitivity.itertuples()
        ),
        caption=(
            "Configuration sensitivity inside every measured external method "
            "family. Hit@1 spread is the best minus worst configuration in "
            "percentage points; a large spread means the implementation choice "
            "matters as much as the family label."
        ),
        label_name="tab:expanded-method-family-sensitivity",
        font_size="tiny",
        tabcolsep="0.7pt",
    )
    append_longtable(
        lines,
        columns="L{0.10\\linewidth}L{0.14\\linewidth}L{0.22\\linewidth}rrrr",
        headers=(
            "Dataset",
            "Implementation family",
            "Configuration",
            "Hit@1",
            "Delta from family best H@1",
            "Hit@20",
            "Delta from family best H@20",
        ),
        rows=(
            (
                latex_escape(DATASET_NAMES.get(row.dataset, row.dataset)),
                latex_escape(row.component_group),
                latex_escape(row.algorithm_name),
                latex_percent(row.hit_at_1),
                latex_points(row.delta_from_group_best_hit_at_1),
                latex_percent(row.hit_at_20),
                latex_points(row.delta_from_group_best_hit_at_20),
            )
            for row in variant_sensitivity.itertuples()
        ),
        caption=(
            "Complete controlled-variant sensitivity for implementation "
            "families with at least two evaluated configurations. Deltas are "
            "relative to that family's best measured configuration on the same "
            "dataset, not relative to Algorithm 5."
        ),
        label_name="tab:expanded-controlled-variant-sensitivity",
        font_size="tiny",
        tabcolsep="0.7pt",
    )
    lines.extend(["\\end{landscape}", ""])
    lines.append("\\begin{landscape}")
    append_longtable(
        lines,
        columns="L{0.10\\linewidth}L{0.14\\linewidth}L{0.30\\linewidth}rrrr",
        headers=(
            "Dataset",
            "Study",
            "Change",
            "Reference H@1",
            "Changed H@1",
            "Delta H@1",
            "Delta H@20",
        ),
        rows=(
            (
                latex_escape(DATASET_NAMES.get(row.dataset, row.dataset)),
                latex_escape(row.system),
                latex_escape(row.change),
                latex_percent(row.reference_hit_at_1),
                latex_percent(row.changed_hit_at_1),
                latex_points(row.delta_hit_at_1),
                latex_points(row.delta_hit_at_20),
            )
            for row in external_ablations.itertuples()
        ),
        caption=(
            "Every external composite removal and controlled parameter contrast. "
            "Deltas are changed configuration minus the stated reference."
        ),
        label_name="tab:expanded-external-ablations",
        font_size="tiny",
        tabcolsep="0.8pt",
    )
    lines.extend(["\\end{landscape}", ""])
    append_figure(
        lines,
        filename="08_external_composite_ablation.png",
        caption=(
            "The x-axis is the change in Hit@1 or Hit@20 after removing one "
            "external composite branch. Negative values mean the complete "
            "composite performed better."
        ),
        label_name="fig:expanded-external-ablation",
        insights=(
            "Sparse character evidence contributes more than dense biomedical embeddings on isolated OCR strings.",
            "preon's partial edit stage is measured separately from its token stage.",
        ),
    )
    append_figure(
        lines,
        filename="10_external_composite_component_study.png",
        caption=(
            "Each bar is Hit@1 for a complete composite or one measured branch "
            "on the named dataset. BioSyn compares sparse and dense branches "
            "with their weighted hybrid; xMEN compares reciprocal-rank fusion "
            "with each branch; preon compares its cascade with token and partial "
            "stages removed."
        ),
        label_name="fig:expanded-composite-components",
        insights=(
            "The sparse character branch is stronger than isolated biomedical dense embeddings for OCR strings.",
            "preon's normalized-Levenshtein partial stage supplies nearly all of its retrieval coverage.",
        ),
    )

    lines.extend(
        [
            "\\begin{landscape}",
            r"\subsection{Algorithm 5 Ablation}",
            (
                "The OCR experiment disables 43 named components or groups and "
                "54 individual feature flags, one at a time. The synthetic "
                "confirmation reruns the 13 broad removals over all 66,257 pairs."
            ),
            "",
        ]
    )
    append_longtable(
        lines,
        columns="L{0.30\\linewidth}L{0.11\\linewidth}rrrrrrrrr",
        headers=(
            "Ablation",
            "Level",
            "Hit@1",
            "Delta H@1",
            "Full-only H@1",
            "Abl.-only H@1",
            "Hit@20",
            "Delta H@20",
            "Full-only H@20",
            "Abl.-only H@20",
            "Median ms",
        ),
        rows=(
            (
                latex_escape(row.ablation_name),
                latex_escape(row.ablation_level),
                latex_percent(row.hit_at_1),
                latex_points(row.delta_hit_at_1),
                int(row.full_only_hit_at_1),
                int(row.ablation_only_hit_at_1),
                latex_percent(row.hit_at_20),
                latex_points(row.delta_hit_at_20),
                int(row.full_only_hit_at_20),
                int(row.ablation_only_hit_at_20),
                f"{row.median_latency_ms:.3f}",
            )
            for row in a5_ocr_metrics.itertuples()
        ),
        caption=(
            "Complete Algorithm 5 ablation result on all 464 fair OCR pairs. "
            "Zero delta means that switch did not alter Hit@1 or Hit@20 on this "
            "locked dataset; it may still change lower ranks or safety output. "
            "Median milliseconds are measured per warm query in the same run."
        ),
        label_name="tab:expanded-a5-ocr-ablations",
        font_size="tiny",
        tabcolsep="1pt",
    )
    lines.extend(["\\end{landscape}", ""])
    append_figure(
        lines,
        filename="05_algorithm_5_ablation_deltas.png",
        caption=(
            "The x-axis is ablated minus complete Algorithm 5 in percentage "
            "points. The y-axis lists the 20 broad removals with the largest "
            "absolute effect on the 464 OCR pairs."
        ),
        label_name="fig:expanded-a5-ocr-ablation",
        insights=(
            "Family rescue supplies the largest candidate-recall gain.",
            "Reranking mainly changes Hit@1, while weighted edit evidence has a larger Hit@20 effect.",
        ),
    )
    ocr_ablation_examples = representative_ablation_examples(
        a5_ocr_metrics,
        a5_ocr_examples,
        limit=12,
    )
    append_longtable(
        lines,
        columns="L{0.20\\linewidth}L{0.10\\linewidth}L{0.12\\linewidth}L{0.12\\linewidth}rL{0.12\\linewidth}r",
        headers=(
            "OCR removal",
            "Input",
            "Expected",
            "Full top 1",
            "Full rank",
            "Ablated top 1",
            "Ablated rank",
        ),
        rows=(
            (
                latex_escape(row.ablation_name),
                latex_escape(row.input),
                latex_escape(row.expected),
                latex_escape(row.full_top_1),
                int(row.full_rank),
                latex_escape(row.ablation_top_1),
                int(row.ablation_rank),
            )
            for row in ocr_ablation_examples.itertuples()
        ),
        caption=(
            "One concrete paired rank change for each of the most influential "
            "Algorithm 5 OCR removals. Rank 999 means outside the top 20."
        ),
        label_name="tab:expanded-a5-ocr-ablation-examples",
        font_size="tiny",
        tabcolsep="0.8pt",
    )
    if not a5_synthetic_metrics.empty:
        append_longtable(
            lines,
            columns="L{0.38\\linewidth}rrrrrrr",
            headers=(
                "Synthetic ablation",
                "Hit@1",
                "Delta H@1",
                "Full-only H@1",
                "Hit@20",
                "Delta H@20",
                "Full-only H@20",
                "Median ms",
            ),
            rows=(
                (
                    latex_escape(row.ablation_name),
                    latex_percent(row.hit_at_1, 4),
                    latex_points(row.delta_hit_at_1, 4),
                    int(row.full_only_hit_at_1),
                    latex_percent(row.hit_at_20, 4),
                    latex_points(row.delta_hit_at_20, 4),
                    int(row.full_only_hit_at_20),
                    f"{row.median_latency_ms:.3f}",
                )
                for row in a5_synthetic_metrics.itertuples()
            ),
            caption=(
                "Algorithm 5 broad-component confirmation on all 66,257 "
                "synthetic clean-core pairs; median milliseconds are measured "
                "per warm query."
            ),
            label_name="tab:expanded-a5-synthetic-ablations",
            font_size="tiny",
            tabcolsep="1pt",
        )
        append_figure(
            lines,
            filename="11_algorithm_5_synthetic_ablation_deltas.png",
            caption=(
                "The x-axis is the synthetic accuracy change after one broad "
                "Algorithm 5 component is removed; the y-axis identifies the removal."
            ),
            label_name="fig:expanded-a5-synthetic-ablation",
            insights=(
                "Synthetic ablations test whether OCR gains generalize across generated edit mechanisms.",
            ),
        )
        synthetic_ablation_examples = representative_ablation_examples(
            a5_synthetic_metrics,
            a5_synthetic_examples,
            limit=12,
        )
        append_longtable(
            lines,
            columns="L{0.20\\linewidth}L{0.10\\linewidth}L{0.12\\linewidth}L{0.12\\linewidth}rL{0.12\\linewidth}r",
            headers=(
                "Synthetic removal",
                "Input",
                "Expected",
                "Full top 1",
                "Full rank",
                "Ablated top 1",
                "Ablated rank",
            ),
            rows=(
                (
                    latex_escape(row.ablation_name),
                    latex_escape(row.input),
                    latex_escape(row.expected),
                    latex_escape(row.full_top_1),
                    int(row.full_rank),
                    latex_escape(row.ablation_top_1),
                    int(row.ablation_rank),
                )
                for row in synthetic_ablation_examples.itertuples()
            ),
            caption=(
                "One concrete paired rank change for each influential synthetic "
                "Algorithm 5 removal. Rank 999 means outside the top 20."
            ),
            label_name="tab:expanded-a5-synthetic-ablation-examples",
            font_size="tiny",
            tabcolsep="0.8pt",
        )

    lines.extend(
        [
            r"\subsection{The 0.60 Extreme OCR Cohort}",
            (
                "For compact query $q_c$ and compact verified target $y_c$, "
                "the normalized distance is"
            ),
            r"\[r=\frac{L(q_c,y_c)}{\max(|y_c|,1)},\qquad \text{extreme when }r>0.60.\]",
            (
                "Compacting removes case, spaces, and punctuation before "
                "Levenshtein distance $L$ is calculated. The fair denominator "
                "contains 113 extreme pairs; the older inclusive 595-row view "
                "contains 121 because it retains duplicates and collision rows."
            ),
            "",
        ]
    )
    append_longtable(
        lines,
        columns="L{0.24\\linewidth}L{0.27\\linewidth}rrrr",
        headers=(
            "Dimension",
            "Group",
            "Cases",
            "Share",
            "A5 H@1",
            "A5 H@20",
        ),
        rows=(
            (
                latex_escape(row.dimension.replace("_", " ").title()),
                latex_escape(str(row.group).replace("_", " ").title()),
                int(row.cases),
                latex_percent(row.share),
                latex_percent(row.a5_hit_at_1),
                latex_percent(row.a5_hit_at_20),
            )
            for row in extreme_distribution.itertuples()
        ),
        caption=(
            "Distribution of all 113 fair extreme OCR pairs by operation, edit "
            "band, visible length, and shared-bigram evidence."
        ),
        label_name="tab:expanded-extreme-distribution",
    )
    append_figure(
        lines,
        filename="06_extreme_cohort_recovery.png",
        caption=(
            "The x-axis is recovery within the 113 fair extreme pairs and the "
            "y-axis lists the 15 strongest systems by Hit@20. Extreme means "
            "$L(q_c,y_c)/|y_c|>0.60$."
        ),
        label_name="fig:expanded-extreme-recovery",
        insights=(
            "The extreme cohort is a low-evidence stress test, not an ordinary typo benchmark.",
            "No measured method converts extreme corruption into reliable top-20 recovery.",
        ),
    )
    append_longtable(
        lines,
        columns="L{0.14\\linewidth}L{0.16\\linewidth}L{0.17\\linewidth}L{0.15\\linewidth}rrrr",
        headers=(
            "Input",
            "Expected",
            "A5 top 1",
            "Operation",
            "Edits",
            "r",
            "Bigrams",
            "Expected rank",
        ),
        rows=(
            (
                latex_escape(row.input),
                latex_escape(row.expected_family_name),
                latex_escape(row.top_1),
                latex_escape(str(row.operation_profile).replace("_", " ")),
                int(row.edit_distance),
                f"{row.normalized_distance:.3f}",
                int(row.shared_bigrams),
                int(row.rank),
            )
            for row in extreme_examples.head(30).itertuples()
        ),
        caption=(
            "Concrete extreme-pair successes and failures. Rank 999 means the "
            "verified family is outside the returned top 20."
        ),
        label_name="tab:expanded-extreme-examples",
    )

    recoverable_count = int(
        remaining_ocr_failures["external_recovery_count"].gt(0).sum()
    )
    unrecovered_count = len(remaining_ocr_failures) - recoverable_count
    lines.extend(
        [
            r"\subsection{Remaining Algorithm 5 Failures and Complementarity}",
            (
                f"Algorithm 5 has {len(remaining_ocr_failures)} top-20 OCR "
                f"misses. At least one measured external method recovers "
                f"{recoverable_count}; all measured external methods also miss "
                f"{unrecovered_count}. The first group exposes candidate rules "
                "worth studying. The second group lacks a demonstrated lexical "
                "solution in this benchmark. External recovery means that the "
                "supplied target appears in a ranking; it does not validate the "
                r"label. Pairs such as \code{LACTULOSE}$\rightarrow$\code{LACTO} "
                "require source-image and label audit before an external rule is "
                "copied into Algorithm 5."
            ),
            "",
        ]
    )
    append_longtable(
        lines,
        columns="L{0.20\\linewidth}L{0.42\\linewidth}rr",
        headers=("Dataset", "System set", "Hit@20", "Failures"),
        rows=(
            (
                latex_escape(DATASET_NAMES[row.dataset]),
                latex_escape(row.system_set),
                latex_percent(row.hit_at_20),
                int(row.failures),
            )
            for row in oracle.itertuples()
        ),
        caption=(
            "Oracle unions on both locked datasets answer whether methods fail "
            "on the same cases. They are diagnostic upper bounds, not deployable "
            "ranking algorithms."
        ),
        label_name="tab:expanded-oracle",
        font_size="small",
    )
    recoverable = remaining_ocr_failures[
        remaining_ocr_failures["external_recovery_count"].gt(0)
    ].head(15)
    unrecovered = remaining_ocr_failures[
        remaining_ocr_failures["external_recovery_count"].eq(0)
    ].head(15)
    failure_examples = pd.concat([recoverable, unrecovered], ignore_index=True)
    lines.append("\\begin{landscape}")
    append_longtable(
        lines,
        columns="L{0.08\\linewidth}L{0.09\\linewidth}L{0.09\\linewidth}rrL{0.10\\linewidth}rL{0.18\\linewidth}L{0.12\\linewidth}",
        headers=(
            "Input",
            "Expected",
            "A5 top 1",
            "Edits",
            "Bigrams",
            "Operation",
            "External recoveries",
            "Example recovering systems",
            "Evidence class",
        ),
        rows=(
            (
                latex_escape(row.input),
                latex_escape(row.expected),
                latex_escape(row.a5_top_1),
                int(row.edit_distance),
                int(row.shared_bigrams),
                latex_escape(str(row.operation_profile).replace("_", " ")),
                int(row.external_recovery_count),
                latex_escape(
                    "; ".join(
                        str(row.external_systems_recovering).split("; ")[:3]
                    )
                    if row.external_recovery_count
                    else "none"
                ),
                latex_escape(row.evidence_class),
            )
            for row in failure_examples.itertuples()
        ),
        caption=(
            "Thirty concrete Algorithm 5 top-20 misses, split between cases "
            "recovered by at least one external method and cases missed by every "
            "measured external method. The complete 126-row audit is stored as CSV."
        ),
        label_name="tab:expanded-a5-failure-examples",
        font_size="tiny",
        tabcolsep="0.7pt",
    )
    lines.extend(["\\end{landscape}", ""])
    append_figure(
        lines,
        filename="07_accuracy_latency_tradeoff.png",
        caption=(
            "The x-axis is measured scoring time per query on a logarithmic "
            "scale and the y-axis is Hit@1. Separate panels show OCR and "
            "synthetic results. Vectorized methods use batch elapsed time "
            "divided by batch size; project methods time individual calls, so "
            "deployment latency still needs one isolated end-to-end harness."
        ),
        label_name="fig:expanded-latency",
        insights=(
            "No single method dominates both latency and OCR accuracy.",
            "Fast synthetic edit-distance methods remain materially weaker on observed OCR.",
        ),
    )

    lines.append("\\begin{landscape}")
    append_longtable(
        lines,
        columns="L{0.16\\linewidth}L{0.22\\linewidth}rrrr",
        headers=(
            "Dataset",
            "Dense system",
            "Queries audited",
            "Exact top-1 agreement",
            "Mean exact top-20 recall",
            "Minimum recall",
        ),
        rows=(
            (
                latex_escape(DATASET_NAMES.get(row.dataset, row.dataset)),
                latex_escape(DISPLAY_NAMES[row.algorithm]),
                int(row.audited_queries),
                latex_percent(row.exact_top1_agreement),
                latex_percent(row.mean_exact_top20_recall),
                latex_percent(row.minimum_exact_top20_recall),
            )
            for row in ann_audit.itertuples()
        ),
        caption=(
            "HNSW approximation audit against exact dense cosine ranking. OCR "
            "uses all 464 queries; synthetic uses a deterministic 1,000-query sample."
        ),
        label_name="tab:expanded-ann-audit",
        font_size="scriptsize",
        tabcolsep="1pt",
    )
    lines.extend(["\\end{landscape}", ""])

    lines.extend(["\\begin{landscape}", r"\subsection{Complete External Repository Disposition}"])
    append_longtable(
        lines,
        columns="L{0.24\\linewidth}L{0.15\\linewidth}L{0.12\\linewidth}L{0.42\\linewidth}",
        headers=("Repository or configuration", "Method family", "Status", "Reason"),
        rows=(
            (
                f"\\href{{{row.source_url}}}{{{latex_escape(row.display_name)}}}",
                latex_escape(row.family),
                latex_escape(row.status),
                latex_escape(row.reason),
            )
            for row in inventory.itertuples()
        ),
        caption=(
            "Every repository or distinct configuration found in the competitor "
            "search, including measured, cached, represented, duplicate, and "
            "non-comparable entries."
        ),
        label_name="tab:expanded-complete-inventory",
    )
    lines.extend(
        [
            "\\end{landscape}",
            "",
            r"\subsection{Reproducible Artifacts}",
            r"\begin{itemize}",
            r"\item Competitor runner: \path{benchmark_04_experiments/run_competitor_benchmark.py}.",
            r"\item Algorithm 5 ablation runner: \path{benchmark_04_experiments/run_algorithm_5_ablations.py}.",
            r"\item Analysis and figure generator: \path{benchmark_04_experiments/analyze_competitor_benchmark.py}.",
            r"\item Row-level results: \path{benchmark_04_experiments/artifacts/06_competitor_benchmark/}.",
            r"\item Statistical tables and figures: \path{benchmark_04_experiments/results/06_competitor_benchmark/}.",
            r"\end{itemize}",
            "",
        ]
    )
    output = OUTPUT / "meeting_10_competitor_section.tex"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    configure_plots()
    ocr, synthetic = load_all_rows()
    metrics = pd.concat(
        [overall_metrics(ocr), overall_metrics(synthetic)],
        ignore_index=True,
    ).sort_values(
        ["dataset", "hit_at_1", "hit_at_20", "mrr_at_20"],
        ascending=[True, False, False, False],
    )
    runtime = runtime_environment()
    fingerprints = dataset_fingerprints()
    dense_config = dense_model_configuration()
    metric_summary = metric_distribution_summary(metrics)
    pareto = accuracy_latency_pareto(metrics)
    paired = pd.concat(
        [paired_comparisons(ocr), paired_comparisons(synthetic)],
        ignore_index=True,
    )
    drivers = pd.concat(
        [system_failure_drivers(ocr), system_failure_drivers(synthetic)],
        ignore_index=True,
    )
    slices = pd.concat(
        [all_system_slices(ocr), all_system_slices(synthetic)],
        ignore_index=True,
    )
    a5_taxonomy = pd.concat(
        [a5_failure_taxonomy(ocr), a5_failure_taxonomy(synthetic)],
        ignore_index=True,
    )
    overlap = pd.concat(
        [failure_overlap(ocr), failure_overlap(synthetic)],
        ignore_index=True,
    )
    oracle = pd.concat(
        [oracle_coverage(ocr), oracle_coverage(synthetic)],
        ignore_index=True,
    )
    equivalence = equivalence_groups(ocr, synthetic)
    breakdowns = pd.concat(
        [representative_breakdowns(ocr), representative_breakdowns(synthetic)],
        ignore_index=True,
    )
    sensitivity = family_sensitivity(metrics)
    variant_sensitivity = controlled_variant_sensitivity(metrics)
    composite_study = composite_component_study(metrics)
    external_ablations = external_component_ablations(ocr, synthetic)
    worst_slices = worst_supported_slices(ocr, synthetic)
    paired_examples = comparative_ocr_examples(ocr)
    remaining_ocr_failures = a5_remaining_ocr_failures(ocr)
    correlations = a5_feature_correlations(ocr, synthetic)

    a5_ocr_rows = load_ablation_rows("ocr_464")
    a5_synthetic_rows = load_ablation_rows("synthetic_66257")
    a5_ocr_metrics, a5_ocr_examples = ablation_effects(a5_ocr_rows)
    a5_synthetic_metrics, a5_synthetic_examples = ablation_effects(
        a5_synthetic_rows
    )
    a5_revision_summary, a5_revision_examples = algorithm_5_revision_drift()

    extreme_distribution, extreme_systems, extreme_examples = extreme_analysis(
        ocr,
        metrics,
    )
    ann_audit = ann_exact_recall_audit()

    outputs = {
        "combined_leaderboard.csv": metrics,
        "runtime_environment.csv": runtime,
        "dataset_fingerprints.csv": fingerprints,
        "dense_model_configuration.csv": dense_config,
        "system_metric_distribution.csv": metric_summary,
        "accuracy_latency_pareto.csv": pareto,
        "a5_paired_comparisons.csv": paired,
        "system_failure_drivers.csv": drivers,
        "all_system_error_slices.csv": slices,
        "a5_failure_taxonomy.csv": a5_taxonomy,
        "failure_overlap_and_oracle.csv": overlap,
        "system_set_oracle_coverage.csv": oracle,
        "equivalent_rankings.csv": equivalence,
        "representative_distance_operation_breakdown.csv": breakdowns,
        "competitor_family_sensitivity.csv": sensitivity,
        "controlled_variant_sensitivity.csv": variant_sensitivity,
        "external_composite_component_study.csv": composite_study,
        "external_component_ablations.csv": external_ablations,
        "system_worst_supported_slices.csv": worst_slices,
        "paired_ocr_examples.csv": paired_examples,
        "a5_remaining_ocr_failures.csv": remaining_ocr_failures,
        "a5_feature_correlations.csv": correlations,
        "a5_ocr_ablation_effects.csv": a5_ocr_metrics,
        "a5_ocr_ablation_examples.csv": a5_ocr_examples,
        "a5_synthetic_ablation_effects.csv": a5_synthetic_metrics,
        "a5_synthetic_ablation_examples.csv": a5_synthetic_examples,
        "a5_source_revision_summary.csv": a5_revision_summary,
        "a5_source_revision_examples.csv": a5_revision_examples,
        "extreme_cohort_distribution.csv": extreme_distribution,
        "extreme_cohort_system_metrics.csv": extreme_systems,
        "extreme_cohort_examples.csv": extreme_examples,
        "dense_ann_exact_recall_audit.csv": ann_audit,
    }
    for name, data in outputs.items():
        save_csv(OUTPUT / name, data)

    plot_leaderboard(metrics, "ocr_464", "01_ocr_leaderboard")
    plot_leaderboard(metrics, "synthetic_66257", "02_synthetic_leaderboard")
    plot_cross_dataset(metrics)
    plot_distance_profiles(ocr, synthetic)
    plot_a5_feature_correlations(correlations)
    if not a5_ocr_metrics.empty:
        plot_a5_ablation(
            a5_ocr_metrics,
            title="Largest Algorithm 5 ablation effects on 464 fair OCR pairs",
            output_name="05_algorithm_5_ablation_deltas",
        )
    plot_extreme_performance(extreme_systems)
    plot_latency_frontier(metrics)
    plot_coverage_recovery(metrics)
    plot_external_component_effects(external_ablations)
    plot_a5_operation_profiles(ocr, synthetic)
    plot_composite_components(composite_study)
    if not a5_synthetic_metrics.empty:
        plot_a5_ablation(
            a5_synthetic_metrics,
            title="Algorithm 5 component effects on 66,257 synthetic pairs",
            output_name="11_algorithm_5_synthetic_ablation_deltas",
            limit=12,
        )

    write_meeting_10_competitor_section(
        metrics=metrics,
        runtime=runtime,
        fingerprints=fingerprints,
        dense_config=dense_config,
        metric_summary=metric_summary,
        pareto=pareto,
        paired=paired,
        paired_examples=paired_examples,
        drivers=drivers,
        worst_slices=worst_slices,
        a5_taxonomy=a5_taxonomy,
        oracle=oracle,
        sensitivity=sensitivity,
        variant_sensitivity=variant_sensitivity,
        external_ablations=external_ablations,
        a5_ocr_metrics=a5_ocr_metrics,
        a5_ocr_examples=a5_ocr_examples,
        a5_synthetic_metrics=a5_synthetic_metrics,
        a5_synthetic_examples=a5_synthetic_examples,
        a5_revision_summary=a5_revision_summary,
        a5_revision_examples=a5_revision_examples,
        extreme_distribution=extreme_distribution,
        extreme_systems=extreme_systems,
        extreme_examples=extreme_examples,
        remaining_ocr_failures=remaining_ocr_failures,
        correlations=correlations,
        ann_audit=ann_audit,
    )

    summary = summary_values(
        metrics,
        paired,
        extreme_distribution,
        a5_ocr_metrics,
        a5_revision_summary,
    )
    (OUTPUT / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Analyzed {metrics['algorithm'].nunique()} systems on both datasets; "
        f"wrote {len(outputs)} tables and "
        f"{len(list(FIGURES.glob('*.png')))} figures to {OUTPUT.parent}",
        flush=True,
    )


if __name__ == "__main__":
    main()

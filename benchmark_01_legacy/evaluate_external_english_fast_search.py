#!/usr/bin/env python3
"""
Evaluate the external `english_search_algorithm_fast.py` against this suite.

Problem: compare the external English-only commercial-name retrieval algorithm
with the current app search evaluator on the same generated commercial-name
stress data.

Inputs:
- `app/data/catalog.json`: app catalog with product name `n`, base group `b`,
  ingredient fields, and internal normalized keys.
- `benchmark_01_legacy/data/test_cases_{inside,semi_outside,outside}.csv`: test
  cases with `input`, `expected`, `category`, `error_type`, `difficulty`, and
  `danger` columns.
- `benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py`: fetched
  snapshot of the external algorithm from
  `https://github.com/youssefkhalil320/drugs_search/blob/main/app/english_search_algorithm_fast.py`.
- `benchmark_01_legacy/results/01_current_app/metrics_by_category.csv`: current app
  aggregate metrics used as the comparison baseline.

Outputs:
- `benchmark_01_legacy/artifacts/02_external_fast/case_results.csv`
- `benchmark_01_legacy/results/02_external_fast/metrics_by_category.csv`
- `benchmark_01_legacy/results/02_external_fast/metrics_by_error_type.csv`
- `benchmark_01_legacy/results/03_comparison/metrics_by_category.csv`
- `benchmark_01_legacy/results/03_comparison/report.md`
- `benchmark_01_legacy/results/02_external_fast/summary.json`

Edge cases:
- Ambiguous expected values such as `A OR B -- AMBIGUOUS`.
- Arabic and mixed-script rows that the external English-only normalizer cannot
  represent well.
- No-result rows and rows where the external algorithm returns a low-confidence
  status but still has ranked candidates.
- Product-level expected names versus base-family expected names.

Failure modes:
- Missing external snapshot raises `FileNotFoundError` with the path.
- A malformed external algorithm module raises an import error before any
  output is written.
- Row-count mismatch between input tests and raw output raises `RuntimeError`
  because partial score tables would be misleading in a medical-search audit.

Algorithm choice:
- We adapt the app catalog into the external algorithm's expected
  `(commercial_name, canonical_name)` rows with `canonical_name = base_group`.
  This matches the commercial-name test-suite target, which mostly evaluates
  base-family retrieval. The alternative, using each product name as canonical,
  would make top-level grouped results variant-specific and not comparable with
  the current app's base-aware scoring.
- We evaluate with multiprocessing using `fork` when available. A serial loop is
  simpler, but the external algorithm is materially slower on this 341k-row
  suite; forking lets workers share the prepared catalog copy-on-write instead
  of rebuilding it for every chunk.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import logging
import multiprocessing
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

import evaluate_current_app_search as current_eval


LOGGER = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "app" / "data" / "catalog.json"
OUT_DIR = ROOT / "benchmark_01_legacy" / "results" / "02_external_fast"
COMPARISON_DIR = ROOT / "benchmark_01_legacy" / "results" / "03_comparison"
ARTIFACT_DIR = ROOT / "benchmark_01_legacy" / "artifacts" / "02_external_fast"
EXTERNAL_ALGORITHM_PATH = ROOT / "benchmark_01_legacy" / "external_algorithms" / "english_search_algorithm_fast.py"
CURRENT_METRICS_PATH = ROOT / "benchmark_01_legacy" / "results" / "01_current_app" / "metrics_by_category.csv"
CURRENT_ERROR_TYPE_METRICS_PATH = ROOT / "benchmark_01_legacy" / "results" / "01_current_app" / "metrics_by_error_type.csv"

TEST_FILES = {
    "inside": ROOT / "benchmark_01_legacy" / "data" / "test_cases_inside.csv",
    "semi_outside": ROOT / "benchmark_01_legacy" / "data" / "test_cases_semi_outside.csv",
    "outside": ROOT / "benchmark_01_legacy" / "data" / "test_cases_outside.csv",
}

# The external algorithm's default top-k is 20. We keep the same cutoff because
# current-app metrics are Hit@1/5/10/20 and MRR/MAP/nDCG@20.
TOP_K_RESULTS = 20

# Chunk size balances multiprocessing overhead against progress visibility. A
# value of 250 keeps per-chunk results small enough for IPC while avoiding one
# process call per test case.
DEFAULT_CHUNK_SIZE = 250

# Cap workers to avoid saturating the machine and to keep memory pressure
# reasonable with a 25k-record prepared catalog. The user cares about score
# parity more than benchmark stress.
DEFAULT_MAX_WORKERS = 8

# External statuses that would normally be shown without asking the user to
# clarify. We treat low-confidence/ambiguous/no-match as clarification states.
CONFIDENT_EXTERNAL_STATUSES = {"high_confidence", "medium_confidence"}

COMPARISON_METRIC_NAMES = [
    "hit_at_1",
    "hit_at_5",
    "hit_at_10",
    "hit_at_20",
    "mrr_at_20",
    "map_at_20",
    "ndcg_at_20",
    "no_result_rate",
    "unsafe_confident_top1_rate",
    "missing_clarification_rate",
    "avg_candidate_pool",
]

ALL_RESULTS_PATH = ARTIFACT_DIR / "case_results.csv"
METRICS_BY_CATEGORY_PATH = OUT_DIR / "metrics_by_category.csv"
METRICS_BY_ERROR_TYPE_PATH = OUT_DIR / "metrics_by_error_type.csv"
FAILURE_SAMPLES_PATH = OUT_DIR / "failure_samples.csv"
TOP_WRONG_BASES_PATH = OUT_DIR / "top_wrong_families.csv"
COMPARISON_CSV_PATH = COMPARISON_DIR / "metrics_by_category.csv"
COMPARISON_ERROR_TYPE_CSV_PATH = COMPARISON_DIR / "metrics_by_error_type.csv"
COMPARISON_REPORT_PATH = COMPARISON_DIR / "report.md"
SUMMARY_PATH = OUT_DIR / "summary.json"

ExternalModule = ModuleType
CaseRow = dict[str, Any]
MetricRow = dict[str, Any]

EXTERNAL_MODULE: ExternalModule | None = None
EXTERNAL_CATALOG: Any | None = None
REL_COUNT_CACHE: dict[tuple[tuple[str, str], ...], int] = {}
CURRENT_INDEX: current_eval.SearchIndex | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate external English fast search against commercial-name tests.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of test cases for a smoke run. Zero means all cases.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=min(DEFAULT_MAX_WORKERS, max(1, os.cpu_count() or 1)),
        help="Worker process count. Defaults to min(8, CPU count).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Number of test cases sent to each worker call.",
    )
    return parser.parse_args()


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def load_external_module(path: Path) -> ExternalModule:
    if not path.exists():
        raise FileNotFoundError(f"External algorithm snapshot not found: {path}")
    spec = importlib.util.spec_from_file_location("external_english_search_algorithm_fast", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to create import spec for external algorithm: {path}")
    module = importlib.util.module_from_spec(spec)
    # Dataclasses inspect sys.modules during decoration, so the module must be
    # registered before executing it. Without this, Python 3.9 raises an
    # AttributeError inside dataclasses for dynamically loaded modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def external_source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_catalog_payload() -> list[dict[str, Any]]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError(f"Expected catalog payload to contain a list at 'records': {CATALOG_PATH}")
    return records


def build_external_catalog_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw in records:
        commercial_name = str(raw.get("n") or "").strip()
        if not commercial_name:
            continue
        base_group = str(raw.get("b") or "").strip()
        rows.append({
            "commercial_name": commercial_name,
            "canonical_name": base_group or commercial_name,
        })
    if not rows:
        raise ValueError("No valid commercial_name rows were derived for the external algorithm.")
    return rows


def initialize_global_state() -> None:
    global EXTERNAL_MODULE, EXTERNAL_CATALOG, CURRENT_INDEX
    EXTERNAL_MODULE = load_external_module(EXTERNAL_ALGORITHM_PATH)
    records = load_catalog_payload()
    external_rows = build_external_catalog_rows(records)
    started = time.time()
    EXTERNAL_CATALOG = EXTERNAL_MODULE.prepare_catalog(external_rows)
    CURRENT_INDEX = current_eval.SearchIndex(current_eval.prepare_records())
    LOGGER.info(
        "prepared external catalog rows=%d records=%d elapsed_s=%.2f",
        len(external_rows),
        len(EXTERNAL_CATALOG.records),
        time.time() - started,
    )


def read_cases(limit: int) -> list[CaseRow]:
    cases: list[CaseRow] = []
    for scope, path in TEST_FILES.items():
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for source_row, row in enumerate(reader, 1):
                cases.append({
                    "scope": scope,
                    "source_row": source_row,
                    "category": row["category"],
                    "error_type": row["error_type"],
                    "difficulty": row.get("difficulty", ""),
                    "danger": row.get("danger", ""),
                    "input": row["input"],
                    "expected": row["expected"],
                })
                if limit and len(cases) >= limit:
                    return cases
    return cases


def chunked(items: list[CaseRow], chunk_size: int) -> list[list[CaseRow]]:
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    return [items[index:index + chunk_size] for index in range(0, len(items), chunk_size)]


def relevant_total(targets: list[tuple[str, str]]) -> int:
    if CURRENT_INDEX is None:
        raise RuntimeError("CURRENT_INDEX is not initialized.")
    target_key = tuple(targets)
    if target_key not in REL_COUNT_CACHE:
        REL_COUNT_CACHE[target_key] = current_eval.relevant_total(CURRENT_INDEX, targets)
    return REL_COUNT_CACHE[target_key]


def normalized_values(values: Iterable[Any]) -> set[tuple[str, str]]:
    normalized: set[tuple[str, str]] = set()
    for value in values:
        norm = current_eval.normalize_search(value)
        compact = current_eval.compact_key(value)
        if norm or compact:
            normalized.add((norm, compact))
    return normalized


def external_relevance(result: dict[str, Any], targets: list[tuple[str, str]]) -> int:
    product_values = normalized_values(
        [result.get("commercial_name"), *result.get("commercial_examples", [])]
    )
    group_values = normalized_values([result.get("name"), result.get("candidate_canonical_name")])
    for target_norm, target_compact in targets:
        if (target_norm, target_compact) in product_values:
            return 3
        if (target_norm, target_compact) in group_values:
            return 2
    return 0


def evaluate_case(case: CaseRow) -> dict[str, Any]:
    if EXTERNAL_MODULE is None or EXTERNAL_CATALOG is None:
        raise RuntimeError("External algorithm state is not initialized.")

    targets = current_eval.parse_expected_targets(case["expected"])
    rel_total = relevant_total(targets)
    response = EXTERNAL_MODULE.search_catalog(EXTERNAL_CATALOG, case["input"], TOP_K_RESULTS)
    results: list[dict[str, Any]] = list(response.get("results") or [])
    rels = [external_relevance(item, targets) for item in results]

    first_rank = 999
    relevant_seen = 0
    average_precision_sum = 0.0
    for rank, rel in enumerate(rels, 1):
        if rel > 0:
            if first_rank == 999:
                first_rank = rank
            relevant_seen += 1
            average_precision_sum += relevant_seen / rank

    top1 = results[0] if results else None
    top1_rel = rels[0] if rels else 0
    status = str(response.get("status") or "")
    needs_clarification = status not in CONFIDENT_EXTERNAL_STATUSES
    unsafe_confident_top1 = bool(top1 and top1_rel == 0 and not needs_clarification)
    missing_clarification = bool(
        top1
        and case["danger"] in {"CAUTION", "DANGEROUS"}
        and not needs_clarification
    )

    top5_names = [str(item.get("name") or "") for item in results[:5]]
    top5_scores = [str(item.get("score") or "") for item in results[:5]]

    return {
        "scope": case["scope"],
        "source_row": case["source_row"],
        "category": case["category"],
        "error_type": case["error_type"],
        "difficulty": case["difficulty"],
        "danger": case["danger"],
        "input": case["input"],
        "expected": case["expected"],
        "external_status": status,
        "external_message": response.get("message") or "",
        "first_rank": first_rank,
        "hit_at_1": int(first_rank <= 1),
        "hit_at_5": int(first_rank <= 5),
        "hit_at_10": int(first_rank <= 10),
        "hit_at_20": int(first_rank <= 20),
        "ap20": average_precision_sum / min(rel_total, TOP_K_RESULTS),
        "ndcg20": current_eval.ndcg(rels, rel_total),
        "result_count": len(results),
        "candidate_pool": int(response.get("candidate_count") or 0),
        "top1_base": top1.get("name") if top1 else "",
        "top1_product": top1.get("commercial_name") if top1 else "",
        "top1_score": top1.get("score") if top1 else "",
        "top1_relevance": top1_rel,
        "top1_signals": top1.get("matched_signals") if top1 else "",
        "top1_needs_clarification": int(needs_clarification) if top1 else "",
        "top5_bases": "|".join(top5_names),
        "top5_scores": "|".join(top5_scores),
        "unsafe_confident_top1": int(unsafe_confident_top1),
        "missing_clarification": int(missing_clarification),
    }


def evaluate_chunk(cases: list[CaseRow]) -> list[dict[str, Any]]:
    return [evaluate_case(case) for case in cases]


def metric_rows_by_scope_category(rows: list[dict[str, Any]]) -> list[MetricRow]:
    by_scope_category: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_scope: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_scope_category[(row["scope"], row["category"])].append(row)
        by_scope[row["scope"]].append(row)

    metrics: list[MetricRow] = []
    for scope, group in sorted(by_scope.items()):
        metrics.append(current_eval.metric_row(scope, "__ALL__", group))
    metrics.append(current_eval.metric_row("__ALL__", "__ALL__", rows))
    for (scope, category), group in sorted(by_scope_category.items()):
        metrics.append(current_eval.metric_row(scope, category, group))
    return metrics


def metric_rows_by_error_type(rows: list[dict[str, Any]]) -> list[MetricRow]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["scope"], row["category"], row["error_type"])].append(row)

    metrics: list[MetricRow] = []
    for (scope, category, error_type), group in sorted(grouped.items()):
        base = current_eval.metric_row(scope, category, group)
        metrics.append({
            "scope": base["scope"],
            "category": base["category"],
            "error_type": error_type,
            "cases": base["cases"],
            "hit_at_1": base["hit_at_1"],
            "hit_at_5": base["hit_at_5"],
            "hit_at_10": base["hit_at_10"],
            "hit_at_20": base["hit_at_20"],
            "mrr_at_20": base["mrr_at_20"],
            "map_at_20": base["map_at_20"],
            "ndcg_at_20": base["ndcg_at_20"],
            "no_result_rate": base["no_result_rate"],
            "unsafe_confident_top1_rate": base["unsafe_confident_top1_rate"],
            "missing_clarification_rate": base["missing_clarification_rate"],
            "avg_candidate_pool": base["avg_candidate_pool"],
        })
    return metrics


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_metric_rows(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            (row["scope"], row["category"]): row
            for row in csv.DictReader(handle)
        }


def read_error_type_metric_rows(path: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            (row["scope"], row["category"], row["error_type"]): row
            for row in csv.DictReader(handle)
        }


def metric_float(row: dict[str, Any], key: str) -> float:
    return float(row.get(key) or 0.0)


def side_by_side_metric_row(
    key: tuple[str, ...],
    current_row: dict[str, Any],
    external_row: dict[str, Any],
    key_names: tuple[str, ...],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        name: value
        for name, value in zip(key_names, key)
    }
    row["cases"] = int(float(current_row["cases"]))
    for metric in COMPARISON_METRIC_NAMES:
        current_value = metric_float(current_row, metric)
        external_value = metric_float(external_row, metric)
        row[f"current_{metric}"] = current_value
        row[f"external_{metric}"] = external_value
        row[f"delta_external_minus_current_{metric}"] = external_value - current_value
    return row


def comparison_rows(external_metrics: list[MetricRow]) -> list[dict[str, Any]]:
    current = read_metric_rows(CURRENT_METRICS_PATH)
    external = {
        (str(row["scope"]), str(row["category"])): row
        for row in external_metrics
    }

    rows: list[dict[str, Any]] = []
    for key in sorted(set(current) & set(external)):
        current_row = current[key]
        external_row = external[key]
        rows.append(side_by_side_metric_row(key, current_row, external_row, ("scope", "category")))
    return rows


def comparison_error_type_rows(external_metrics: list[MetricRow]) -> list[dict[str, Any]]:
    current = read_error_type_metric_rows(CURRENT_ERROR_TYPE_METRICS_PATH)
    external = {
        (str(row["scope"]), str(row["category"]), str(row["error_type"])): row
        for row in external_metrics
    }

    rows: list[dict[str, Any]] = []
    for key in sorted(set(current) & set(external)):
        current_row = current[key]
        external_row = external[key]
        rows.append(
            side_by_side_metric_row(
                key,
                current_row,
                external_row,
                ("scope", "category", "error_type"),
            )
        )
    return rows


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


# One sentence per generated category. These descriptions are kept in the
# evaluator because the Markdown report is the reviewer-facing artifact; keeping
# the map here lets the report generator fail fast if a new category is added
# without human-readable context.
CATEGORY_DESCRIPTIONS = {
    "abbreviation_expansion_catalog": "Expands dosage-form abbreviations such as F.C. into full words.",
    "all_position_deletion_full_catalog": "Deletes one character from a commercial family name at every possible position.",
    "all_position_transposition_full_catalog": "Swaps adjacent characters throughout the commercial family name.",
    "arabic_dot_confusion": "Uses Arabic letters with visually similar dot patterns.",
    "brand_ingredient_mixed_query_catalog": "Combines the brand family with its active ingredient words.",
    "c_k_q_interchange": "Tests spelling interchange among C, K, and Q.",
    "consonant_skeleton": "Removes vowels and searches with only the consonant skeleton.",
    "consonant_skeleton_expanded_catalog": "Catalog-wide consonant-only commercial-family queries.",
    "cross_script": "Mixes Latin and Arabic script inside one commercial-name query.",
    "decimal_slash_strength_noise_catalog": "Adds decimal, slash, or per-unit strength wording around the brand.",
    "digraph_soundalike_catalog": "Replaces digraphs with sound-alike spellings such as TH to T.",
    "double_letter": "Adds or removes repeated letters in the commercial name.",
    "duplicate_syllable_catalog": "Duplicates a short prefix or syllable in the commercial family name.",
    "form_word_noise_catalog": "Adds dosage-form words such as tablet, syrup, cream, or vial.",
    "ingredient_name_query_catalog": "Uses the active ingredient/composition text instead of the brand name.",
    "initial_sound_confusion_full_catalog": "Changes the initial letter to a common sound-alike letter.",
    "keyboard_adjacent": "Seed QWERTY adjacent-key typo cases.",
    "keyboard_adjacent_expanded_catalog": "Catalog-wide single-character adjacent-key typo cases.",
    "keyboard_shift_whole_word_catalog": "Simulates a whole word typed with hands shifted on the keyboard.",
    "letter_insertion": "Inserts one extra letter into the intended commercial name.",
    "ligature_confusion": "Uses visual ligature confusions such as rn/m or cl/d.",
    "manufacturer_noise_catalog": "Adds manufacturer/company text to the commercial-name query.",
    "mirror_letter_confusion": "Swaps mirror-like letters such as b/d, p/q, n/u, or m/w.",
    "mobile_keypad_confusion_catalog": "Replaces letters with nearby mobile-keypad letters.",
    "multi_error_chain": "Combines more than one typo type in the same query.",
    "ocr_digit_letter": "Seed OCR confusion between digits and letters.",
    "ocr_digit_letter_full_catalog": "Catalog-wide OCR digit/letter replacements such as O/0 or I/1.",
    "parenthetical_noise_catalog": "Adds parenthetical or context-like text around the brand.",
    "partial_prefix_ambiguity_catalog": "Uses very short prefixes that can match many families.",
    "ph_f_confusion": "Tests PH versus F spelling confusion.",
    "phonetic_substitution_full_catalog": "Applies sound-alike consonant substitutions across the catalog.",
    "position_deletion": "Seed first/middle/last character deletion cases.",
    "prefix_suffix_extra_noise_catalog": "Adds generic prefix or suffix words around the commercial family.",
    "qualifier_synonym_noise_catalog": "Adds qualifier words such as plus, extra, max, or forte.",
    "route_word_noise_catalog": "Uses route/form context words as part of the query.",
    "separator_removal_full_catalog": "Removes spaces, hyphens, and separators from the commercial name.",
    "single_vowel_deletion_full_catalog": "Deletes one vowel from the commercial family name.",
    "space_insertion_inside_brand_catalog": "Inserts an extra space inside a single commercial family token.",
    "status_marker_noise_catalog": "Adds status or marker text such as N/A around the brand.",
    "strength_unit_noise_catalog": "Adds synthetic strength and unit text to the brand query.",
    "suffix_family_confusion": "Seed cases where a clear drug suffix remains but the prefix is degraded.",
    "suffix_family_confusion_expanded_catalog": "Catalog-wide suffix-family cases with degraded prefixes.",
    "syllable_transposition": "Swaps nearby letters or syllable-like chunks in the name.",
    "symbol_synonym_catalog": "Rewrites symbols such as slash or plus into words.",
    "therapeutic_class_noise_catalog": "Adds therapeutic-class text to the commercial-name query.",
    "token_drop_expanded_catalog": "Drops one token from a multi-token commercial family.",
    "token_order_transposition_catalog": "Reorders tokens in a multi-token commercial family.",
    "truncation_collision": "Seed ambiguous truncations where a short brand is also another brand prefix.",
    "truncation_collision_expanded_catalog": "Catalog-wide truncated prefixes that collide with longer families.",
    "visual_ligature_full_catalog": "Catalog-wide visual letter-shape confusions.",
    "voiced_unvoiced_swap": "Swaps voiced and unvoiced consonant pairs such as B/P or D/T.",
    "vowel_substitution_full_catalog": "Substitutes one vowel for another inside the commercial family.",
}


def markdown_cell(value: Any) -> str:
    """Return a non-empty Markdown table cell that cannot shift columns."""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    # Pipes break Markdown tables. Replace them with a slash instead of escaping
    # so simple table-cell validation can still count columns accurately.
    text = text.replace("|", "/")
    return text or "n/a"


def load_category_examples() -> dict[tuple[str, str], str]:
    """Load one concrete generated test case per scope/category pair."""
    examples: dict[tuple[str, str], str] = {}
    for scope, path in TEST_FILES.items():
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                key = (scope, row["category"])
                if key in examples:
                    continue
                examples[key] = markdown_cell(
                    f"{row['input']} => {row['expected']} ({row['error_type']})"
                )
    return examples


def load_error_type_examples() -> dict[tuple[str, str, str], str]:
    """Load one concrete generated test case per scope/category/error_type row."""
    examples: dict[tuple[str, str, str], str] = {}
    for scope, path in TEST_FILES.items():
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                key = (scope, row["category"], row["error_type"])
                if key in examples:
                    continue
                examples[key] = markdown_cell(f"{row['input']} => {row['expected']}")
    return examples


def category_context(category_rows: list[dict[str, Any]]) -> dict[tuple[str, str], tuple[str, str]]:
    """Return example/description context for every category row.

    The report compares dozens of categories, so a metric-only table makes it
    too easy to miss what a row actually tests. We use the first generated case
    from each category as a deterministic example, rather than hand-picking an
    example, so repeated report generation stays stable and traceable to the
    source CSVs.
    """
    examples = load_category_examples()
    context: dict[tuple[str, str], tuple[str, str]] = {}
    missing: list[str] = []
    for row in category_rows:
        key = (row["scope"], row["category"])
        description = CATEGORY_DESCRIPTIONS.get(row["category"])
        example = examples.get(key)
        if not description or not example:
            missing.append(f"{key[0]}/{key[1]}")
            continue
        context[key] = (example, markdown_cell(description))
    if missing:
        raise RuntimeError(f"Missing category report context for: {', '.join(sorted(missing))}")
    return context


def error_type_context(error_type_rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], tuple[str, str]]:
    """Return example/description context for every detailed error-type row."""
    examples = load_error_type_examples()
    context: dict[tuple[str, str, str], tuple[str, str]] = {}
    missing: list[str] = []
    for row in error_type_rows:
        key = (row["scope"], row["category"], row["error_type"])
        description = CATEGORY_DESCRIPTIONS.get(row["category"])
        example = examples.get(key)
        if not description or not example:
            missing.append(f"{key[0]}/{key[1]}/{key[2]}")
            continue
        context[key] = (example, markdown_cell(description))
    if missing:
        raise RuntimeError(f"Missing error-type report context for: {', '.join(sorted(missing))}")
    return context


def write_comparison_report(
    comparison: list[dict[str, Any]],
    error_type_comparison: list[dict[str, Any]],
    elapsed_seconds: float,
    evaluated_cases: int,
) -> None:
    by_key = {(row["scope"], row["category"]): row for row in comparison}
    scope_rows = [
        by_key[(scope, "__ALL__")]
        for scope in ["inside", "semi_outside", "outside", "__ALL__"]
        if (scope, "__ALL__") in by_key
    ]
    category_rows = [row for row in comparison if row["category"] != "__ALL__"]
    category_details = category_context(category_rows)
    error_type_details = error_type_context(error_type_comparison)
    worst_external_gap = sorted(category_rows, key=lambda row: row["delta_external_minus_current_hit_at_20"])[:20]
    best_external_gap = sorted(category_rows, key=lambda row: row["delta_external_minus_current_hit_at_20"], reverse=True)[:20]

    lines = [
        "# External English Fast Search Comparison",
        "",
        "This report compares `benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py` against the current app evaluator on the generated commercial-name stress suite.",
        "",
        "Important adaptation: the external algorithm expects `commercial_name,canonical_name` CSV rows. The evaluator maps app product name `n` to `commercial_name` and app base group `b` to `canonical_name`, so grouped external results can be compared to the suite's commercial-family expected targets.",
        "",
        "## Outputs",
        "",
        "| file | purpose |",
        "| --- | --- |",
        "| `benchmark_01_legacy/artifacts/02_external_fast/case_results.csv` | one row per external evaluated test case |",
        "| `benchmark_01_legacy/results/02_external_fast/metrics_by_category.csv` | external metrics by scope/category |",
        "| `benchmark_01_legacy/results/02_external_fast/metrics_by_error_type.csv` | external metrics by scope/category/error_type |",
        "| `benchmark_01_legacy/results/03_comparison/metrics_by_category.csv` | side-by-side deltas versus current app metrics |",
        "| `benchmark_01_legacy/results/03_comparison/metrics_by_error_type.csv` | side-by-side deltas versus current app metrics by scope/category/error_type |",
        "| `benchmark_01_legacy/results/02_external_fast/failure_samples.csv` | first external unrecovered failures |",
        "",
        "## Headline",
        "",
        f"- Evaluated cases: `{evaluated_cases:,}`.",
        f"- Runtime: `{elapsed_seconds:.2f}` seconds.",
        "",
        "| scope | cases | current Hit@1 | external Hit@1 | delta | current Hit@20 | external Hit@20 | delta | current unsafe top1 | external unsafe top1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in scope_rows:
        lines.append(
            f"| `{row['scope']}` | {row['cases']:,} | "
            f"{pct(row['current_hit_at_1'])} | {pct(row['external_hit_at_1'])} | {pct(row['delta_external_minus_current_hit_at_1'])} | "
            f"{pct(row['current_hit_at_20'])} | {pct(row['external_hit_at_20'])} | {pct(row['delta_external_minus_current_hit_at_20'])} | "
            f"{pct(row['current_unsafe_confident_top1_rate'])} | {pct(row['external_unsafe_confident_top1_rate'])} |"
        )

    lines += [
        "",
        "## Full Category Comparison",
        "",
        "This table includes every category in the generated commercial-name suite. Metric values mirror `benchmark_01_legacy/results/03_comparison/metrics_by_category.csv`; examples and descriptions come from the test definitions.",
        "",
        "| scope | category | example | description | cases | current Hit@1 | external Hit@1 | delta | current Hit@20 | external Hit@20 | delta | current unsafe top-1 | external unsafe top-1 | current no-result | external no-result |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(category_rows, key=lambda item: (item["scope"], item["category"])):
        example, description = category_details[(row["scope"], row["category"])]
        lines.append(
            f"| `{row['scope']}` | `{row['category']}` | {example} | {description} | {row['cases']:,} | "
            f"{pct(row['current_hit_at_1'])} | {pct(row['external_hit_at_1'])} | {pct(row['delta_external_minus_current_hit_at_1'])} | "
            f"{pct(row['current_hit_at_20'])} | {pct(row['external_hit_at_20'])} | {pct(row['delta_external_minus_current_hit_at_20'])} | "
            f"{pct(row['current_unsafe_confident_top1_rate'])} | {pct(row['external_unsafe_confident_top1_rate'])} | "
            f"{pct(row['current_no_result_rate'])} | {pct(row['external_no_result_rate'])} |"
        )

    lines += [
        "",
        "## Full Error-Type Comparison",
        "",
        "This table includes every detailed `(scope, category, error_type)` bucket in the generated commercial-name suite. It is the row-level view needed for exact mutation families such as deletion position, phonetic substitution, token drop, and separator removal.",
        "",
        "| scope | category | error_type | example | description | cases | current Hit@1 | external Hit@1 | delta | current Hit@20 | external Hit@20 | delta | current unsafe top-1 | external unsafe top-1 | current no-result | external no-result |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(error_type_comparison, key=lambda item: (item["scope"], item["category"], item["error_type"])):
        key = (row["scope"], row["category"], row["error_type"])
        example, description = error_type_details[key]
        lines.append(
            f"| `{row['scope']}` | `{row['category']}` | `{markdown_cell(row['error_type'])}` | {example} | {description} | {row['cases']:,} | "
            f"{pct(row['current_hit_at_1'])} | {pct(row['external_hit_at_1'])} | {pct(row['delta_external_minus_current_hit_at_1'])} | "
            f"{pct(row['current_hit_at_20'])} | {pct(row['external_hit_at_20'])} | {pct(row['delta_external_minus_current_hit_at_20'])} | "
            f"{pct(row['current_unsafe_confident_top1_rate'])} | {pct(row['external_unsafe_confident_top1_rate'])} | "
            f"{pct(row['current_no_result_rate'])} | {pct(row['external_no_result_rate'])} |"
        )

    lines += [
        "",
        "## Largest External Regressions By Hit@20",
        "",
        "| scope | category | cases | current Hit@20 | external Hit@20 | delta |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in worst_external_gap:
        lines.append(
            f"| `{row['scope']}` | `{row['category']}` | {row['cases']:,} | "
            f"{pct(row['current_hit_at_20'])} | {pct(row['external_hit_at_20'])} | {pct(row['delta_external_minus_current_hit_at_20'])} |"
        )

    lines += [
        "",
        "## Largest External Gains By Hit@20",
        "",
        "| scope | category | cases | current Hit@20 | external Hit@20 | delta |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in best_external_gap:
        lines.append(
            f"| `{row['scope']}` | `{row['category']}` | {row['cases']:,} | "
            f"{pct(row['current_hit_at_20'])} | {pct(row['external_hit_at_20'])} | {pct(row['delta_external_minus_current_hit_at_20'])} |"
        )

    COMPARISON_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def failure_and_wrong_base_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    wrong = Counter()
    for row in rows:
        if row["first_rank"] > TOP_K_RESULTS and len(failures) < 1200:
            failures.append({
                "scope": row["scope"],
                "category": row["category"],
                "error_type": row["error_type"],
                "danger": row["danger"],
                "input": row["input"],
                "expected": row["expected"],
                "external_status": row["external_status"],
                "top1": row["top1_base"],
                "top1_product": row["top1_product"],
                "top1_score": row["top1_score"],
                "top1_signals": row["top1_signals"],
                "candidate_pool": row["candidate_pool"],
            })
        if row["top1_relevance"] == 0 and row["top1_base"]:
            wrong[(row["category"], row["top1_base"])] += 1
    wrong_rows = [
        {"category": category, "top_wrong_base": base, "count": count}
        for (category, base), count in wrong.most_common(500)
    ]
    return failures, wrong_rows


def run_multiprocess(cases: list[CaseRow], workers: int, chunk_size: int) -> list[dict[str, Any]]:
    chunks = chunked(cases, chunk_size)
    started = time.time()
    processed = 0
    rows: list[dict[str, Any]] = []

    if workers <= 1:
        for chunk in chunks:
            result_chunk = evaluate_chunk(chunk)
            rows.extend(result_chunk)
            processed += len(result_chunk)
            if processed % 5000 == 0 or processed == len(cases):
                LOGGER.info("processed=%d elapsed_s=%.1f", processed, time.time() - started)
        return rows

    context_name = "fork" if "fork" in multiprocessing.get_all_start_methods() else None
    context = multiprocessing.get_context(context_name) if context_name else multiprocessing.get_context()
    with context.Pool(processes=workers) as pool:
        for result_chunk in pool.imap(evaluate_chunk, chunks):
            rows.extend(result_chunk)
            processed += len(result_chunk)
            if processed % 5000 == 0 or processed == len(cases):
                LOGGER.info("processed=%d elapsed_s=%.1f", processed, time.time() - started)
    return rows


def main() -> int:
    configure_logging()
    args = parse_args()
    if args.workers <= 0:
        raise ValueError(f"--workers must be positive, got {args.workers}")
    if args.chunk_size <= 0:
        raise ValueError(f"--chunk-size must be positive, got {args.chunk_size}")

    started = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    COMPARISON_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    initialize_global_state()
    cases = read_cases(args.limit)
    LOGGER.info("loaded cases=%d workers=%d chunk_size=%d", len(cases), args.workers, args.chunk_size)

    rows = run_multiprocess(cases, args.workers, args.chunk_size)
    if len(rows) != len(cases):
        raise RuntimeError(f"Expected {len(cases)} evaluated rows, got {len(rows)}")

    metrics = metric_rows_by_scope_category(rows)
    metrics_by_error_type = metric_rows_by_error_type(rows)
    comparison = comparison_rows(metrics)
    error_type_comparison = comparison_error_type_rows(metrics_by_error_type)
    failures, wrong_rows = failure_and_wrong_base_rows(rows)

    write_csv(ALL_RESULTS_PATH, rows)
    write_csv(METRICS_BY_CATEGORY_PATH, metrics)
    write_csv(METRICS_BY_ERROR_TYPE_PATH, metrics_by_error_type)
    write_csv(COMPARISON_CSV_PATH, comparison)
    write_csv(COMPARISON_ERROR_TYPE_CSV_PATH, error_type_comparison)
    write_csv(FAILURE_SAMPLES_PATH, failures or [{
        "scope": "",
        "category": "",
        "error_type": "",
        "danger": "",
        "input": "",
        "expected": "",
        "external_status": "",
        "top1": "",
        "top1_product": "",
        "top1_score": "",
        "top1_signals": "",
        "candidate_pool": "",
    }])
    write_csv(TOP_WRONG_BASES_PATH, wrong_rows or [{"category": "", "top_wrong_base": "", "count": 0}])

    elapsed_seconds = time.time() - started
    write_comparison_report(comparison, error_type_comparison, elapsed_seconds, len(rows))
    summary = {
        "evaluated_cases": len(rows),
        "elapsed_seconds": round(elapsed_seconds, 2),
        "workers": args.workers,
        "chunk_size": args.chunk_size,
        "limit": args.limit,
        "external_algorithm_path": str(EXTERNAL_ALGORITHM_PATH.relative_to(ROOT)),
        "external_algorithm_sha256": external_source_sha256(EXTERNAL_ALGORITHM_PATH),
        "all_test_results_csv": str(ALL_RESULTS_PATH.relative_to(ROOT)),
        "metrics_csv": str(METRICS_BY_CATEGORY_PATH.relative_to(ROOT)),
        "metrics_by_error_type_csv": str(METRICS_BY_ERROR_TYPE_PATH.relative_to(ROOT)),
        "comparison_csv": str(COMPARISON_CSV_PATH.relative_to(ROOT)),
        "comparison_by_error_type_csv": str(COMPARISON_ERROR_TYPE_CSV_PATH.relative_to(ROOT)),
        "comparison_report_md": str(COMPARISON_REPORT_PATH.relative_to(ROOT)),
        "failure_samples_csv": str(FAILURE_SAMPLES_PATH.relative_to(ROOT)),
        "top_wrong_bases_csv": str(TOP_WRONG_BASES_PATH.relative_to(ROOT)),
        "catalog_adaptation": "commercial_name=app record n; canonical_name=app record b or n",
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    LOGGER.info("summary=%s", json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

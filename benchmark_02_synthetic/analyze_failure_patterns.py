#!/usr/bin/env python3
"""Analyze V2 failed cases and manually reported failures.

This report intentionally uses presentation labels:
Algorithm 1 = current app evaluator
Algorithm 2 = external English fast algorithm
Algorithm 3 = master rank-fusion algorithm
"""

from __future__ import annotations

import csv
import difflib
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = Path(__file__).resolve().parent
FULL_ARTIFACTS_DIR = DATASET_DIR / "artifacts" / "01_full_benchmark"
FULL_RESULTS_DIR = DATASET_DIR / "results" / "01_full_benchmark"
MANUAL_RESULTS_DIR = DATASET_DIR / "results" / "02_manual_cases"
EVALUATION_DIR = ROOT / "benchmark_01_legacy"
if str(EVALUATION_DIR) not in sys.path:
    sys.path.insert(0, str(EVALUATION_DIR))
if str(DATASET_DIR) not in sys.path:
    sys.path.insert(0, str(DATASET_DIR))

import evaluate_algorithms_1_2 as v2_eval
import evaluate_algorithm_3 as master_eval


ALGORITHMS = {
    "algorithm_1": {
        "label": "Algorithm 1",
        "legacy": "current app evaluator",
        "path": FULL_ARTIFACTS_DIR / "algorithm_1_cases.csv",
    },
    "algorithm_2": {
        "label": "Algorithm 2",
        "legacy": "external English fast algorithm",
        "path": FULL_ARTIFACTS_DIR / "algorithm_2_cases.csv",
    },
    "algorithm_3": {
        "label": "Algorithm 3",
        "legacy": "master rank-fusion algorithm",
        "path": FULL_ARTIFACTS_DIR / "algorithm_3_cases.csv",
    },
}

MANUAL_CASES = [
    ("optraderolpl", "optaderol"),
    ("Auticax", "ANTI COX II"),
    ("couphseed", "COUGHSED PARACETAMOL CHILDREN OR COUGHSED PARACETAMOL INFANTS"),
    ("ivybnon", "IVY BRONCH"),
    ("sauovent", "salbovent"),
    ("garaxy", "garamycin"),
    ("colchicime", "colchicine"),
    ("flacton", "flector"),
    ("levohista", "LEVOHISTAM"),
    ("oplax", "OPLEX N OR OPLEX MONO"),
    ("oplox", "OPLEX N OR OPLEX MONO"),
    ("moxclar", "e-moxclav"),
    ("Ezogoat", "Ezogast"),
    ("healreptic", "healioreptic"),
    ("colovarin", "COLOVERIN D"),
    ("Eucavban", "eucarbon"),
    ("librux", "LIBRAX SUGAR"),
    ("mebula", "nebula"),
    ("dexazue", "dexazone"),
    ("octotron", "OCTATRON"),
    ("revanoglob", "Revanoglow"),
    ("jvsprin", "jusprin"),
    ("mixmail", "mixmazil"),
    ("puresmin", "PURESAMINE"),
    ("biato", "ibiacto"),
    ("salire", "saline"),
    ("devamol", "DEVAROL S"),
    ("calcihon", "calcitron"),
    ("broncholrn", "BRONCHOLIN S"),
    ("apido", "apidone"),
    ("tavaric", "tavanic"),
    ("flopudex", "flopadex"),
    ("metaps", "metapsin"),
    ("arymentin", "augmentin"),
    ("centerloc", "controloc"),
    ("moxauidey", "moxavidex"),
    ("codlor", "codilar"),
    ("Duncof", "Duncef"),
    ("Cndalenz", "Ondalenz"),
    ("Duphlac", "Duphalac"),
    ("Dophlac", "Duphalac"),
    ("Conlentin", "Conventin"),
    ("taves", "tareg"),
    ("cyprocin", "ciprocin"),
    ("cyprocen", "ciprocin"),
    ("vonifrton", "vomifraton"),
    ("awndisb", "awadist"),
    ("vonaspine", "vonaspire"),
    ("Ketostenil", "Ketosteril"),
    ("Ketostenl", "Ketosteril"),
]


def compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def fnum(value: Any) -> float:
    if value in ("", None):
        return 0.0
    return float(value)


def pct(value: Any) -> str:
    return f"{float(value) * 100:.2f}%"


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def is_failure(row: dict[str, Any]) -> bool:
    return (
        str(row.get("hit_at_20")) != "1"
        or str(row.get("behavior_success")) != "1"
        or str(row.get("unsafe_confident_top1")) == "1"
        or str(row.get("missing_clarification")) == "1"
    )


def failure_modes(row: dict[str, Any]) -> list[str]:
    modes: list[str] = []
    if str(row.get("hit_at_20")) != "1":
        modes.append("retrieval_miss")
    if str(row.get("behavior_success")) != "1":
        modes.append("behavior_miss")
    if str(row.get("unsafe_confident_top1")) == "1":
        modes.append("unsafe_confident_top1")
    if str(row.get("missing_clarification")) == "1":
        modes.append("missing_clarification")
    if str(row.get("top1_status")) == "no_result" or str(row.get("result_count")) == "0":
        modes.append("no_result")
    return modes or ["pass"]


def root_cause(row: dict[str, Any]) -> str:
    category = str(row.get("category") or "")
    error_type = str(row.get("error_type") or "")
    modes = set(failure_modes(row))
    if "unsafe_confident_top1" in modes:
        return "unsafe false-positive confidence"
    if "missing_clarification" in modes:
        return "safety gate failed to ask for clarification"
    if row.get("expected_behavior") == "no_match":
        return "negative/no-match query accepted too strongly"
    if category in {"three_error_combinations", "four_plus_error_combinations", "two_error_combinations"}:
        return "multi-error typo chain"
    if "consonant" in category or "wrong_vowels" in category:
        return "consonant-frame or wrong-vowel corruption"
    if any(token in category for token in ("truncation", "prefix", "substring", "score_gap")):
        return "short-prefix / collision ambiguity"
    if any(token in category for token in ("form", "route", "strength", "cancelled", "status")):
        return "context, strength, route, or status handling"
    if any(token in category for token in ("autocorrect", "fragmentation")):
        return "word-boundary or autocorrect artifact"
    if any(token in category for token in ("ocr", "visual", "phonetic", "ligature", "keyboard", "transposition", "insertion", "deletion", "double", "speed")):
        return "single-family typo mutation"
    if "no_result" in modes:
        return "candidate generation returned no result"
    return error_type or "unclassified"


def aggregate_algorithm(rows: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [row for row in rows if is_failure(row)]
    return {
        "cases": len(rows),
        "failures": len(failures),
        "failure_rate": len(failures) / len(rows) if rows else 0.0,
        "retrieval_misses": sum(str(row.get("hit_at_20")) != "1" for row in rows),
        "behavior_misses": sum(str(row.get("behavior_success")) != "1" for row in rows),
        "unsafe_confident_top1": sum(str(row.get("unsafe_confident_top1")) == "1" for row in rows),
        "missing_clarification": sum(str(row.get("missing_clarification")) == "1" for row in rows),
        "no_result": sum(str(row.get("top1_status")) == "no_result" or str(row.get("result_count")) == "0" for row in rows),
    }


def top_group(rows: list[dict[str, Any]], field_names: tuple[str, ...], limit: int = 12) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(str(row.get(name) or "") for name in field_names)].append(row)
    out = []
    for key, group in grouped.items():
        failures = [row for row in group if is_failure(row)]
        if not failures:
            continue
        out.append({
            **{name: value for name, value in zip(field_names, key)},
            "cases": len(group),
            "failures": len(failures),
            "failure_rate": len(failures) / len(group),
            "top_cause": Counter(root_cause(row) for row in failures).most_common(1)[0][0],
        })
    return sorted(out, key=lambda row: (-row["failures"], -row["failure_rate"]))[:limit]


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + (ca != cb),
            ))
        previous = current
    return previous[-1]


def adjacent_transposition(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    diffs = [i for i, (ca, cb) in enumerate(zip(a, b)) if ca != cb]
    return len(diffs) == 2 and diffs[1] == diffs[0] + 1 and a[diffs[0]] == b[diffs[1]] and a[diffs[1]] == b[diffs[0]]


def nearest_expected_name(input_name: str, expected: str) -> str:
    """Choose the nearest catalog-valid alternative for typo diagnostics."""

    left = compact(input_name)
    alternatives = [part.strip() for part in re.split(r"\s+OR\s+", expected, flags=re.I) if part.strip()]
    return min(alternatives, key=lambda value: levenshtein(left, compact(value)))


def manual_error_type(input_name: str, right_name: str) -> str:
    left = compact(input_name)
    right = compact(nearest_expected_name(input_name, right_name))
    if adjacent_transposition(left, right):
        return "adjacent transposition"
    distance = levenshtein(left, right)
    if distance <= 1:
        return "single edit"
    pairs = [("c", "k"), ("c", "q"), ("s", "z"), ("f", "v"), ("p", "b"), ("d", "t"), ("g", "j")]
    if any((x in left and y in right) or (y in left and x in right) for x, y in pairs):
        return "phonetic/keyboard letter substitution"
    if abs(len(left) - len(right)) >= 2:
        return "multi-character insertion/deletion"
    if left[:2] == right[:2] or left[-2:] == right[-2:]:
        return "same-prefix/suffix multi-edit typo"
    return "multi-edit typo"


def manual_note(input_name: str, right_name: str) -> str:
    left = compact(input_name)
    right = compact(nearest_expected_name(input_name, right_name))
    distance = levenshtein(left, right)
    kind = manual_error_type(input_name, right_name)
    if kind == "single edit":
        return f"Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance={distance}."
    if "phonetic" in kind:
        return f"Looks like a sound-alike or keyboard-neighbor substitution. edit_distance={distance}."
    if "multi-character" in kind:
        return f"More than one inserted/deleted character; needs stronger fuzzy candidate generation. edit_distance={distance}."
    if "same-prefix" in kind:
        return f"Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance={distance}."
    return f"Compound typo; likely needs manual alias or stronger multi-error handling. edit_distance={distance}."


def manual_case_rows() -> list[dict[str, Any]]:
    rows = []
    for index, (edited, right) in enumerate(MANUAL_CASES, 1):
        rows.append({
            "source_row": f"manual_{index:03d}",
            "input": edited,
            "expected": right,
            "category": "manual_failed_cases",
            "error_type": manual_error_type(edited, right),
            "difficulty": "EXTREME",
            "danger": "DANGEROUS",
            "scope": "manual",
            "expected_behavior": "match",
            "collision_with": "",
            "source_base_group": right,
        })
    return rows


def evaluate_manual_cases() -> list[dict[str, Any]]:
    v2_eval.initialize_global_state()
    master_eval.initialize_global_state()
    rows = []
    for case in manual_case_rows():
        algorithm_rows = {
            "algorithm_1": v2_eval.evaluate_current_case(case),
            "algorithm_2": v2_eval.evaluate_external_case(case),
            "algorithm_3": master_eval.evaluate_master_case(case),
        }
        row = {
            "input": case["input"],
            "right_name": case["expected"],
            "manual_error_type": case["error_type"],
            "analysis_note": manual_note(case["input"], case["expected"]),
        }
        for key, result in algorithm_rows.items():
            row[f"{key}_hit_at_1"] = result.get("hit_at_1")
            row[f"{key}_hit_at_20"] = result.get("hit_at_20")
            row[f"{key}_first_rank"] = result.get("first_rank")
            row[f"{key}_top1"] = result.get("top1_base")
            row[f"{key}_top5"] = result.get("top5_bases")
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def table_line(values: list[Any]) -> str:
    return "| " + " | ".join(str(value).replace("\n", " ") for value in values) + " |"


def first_examples(rows: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    failures = [row for row in rows if is_failure(row)]
    return failures[:limit]


def write_report(
    path: Path,
    all_rows: dict[str, list[dict[str, Any]]],
    manual_rows: list[dict[str, Any]],
) -> None:
    summaries = {key: aggregate_algorithm(rows) for key, rows in all_rows.items()}
    failure_sets = {
        key: {str(row["source_row"]) for row in rows if is_failure(row)}
        for key, rows in all_rows.items()
    }
    all_three_fail = failure_sets["algorithm_1"] & failure_sets["algorithm_2"] & failure_sets["algorithm_3"]
    child_fail_master_pass = (failure_sets["algorithm_1"] & failure_sets["algorithm_2"]) - failure_sets["algorithm_3"]
    master_only_fail = failure_sets["algorithm_3"] - failure_sets["algorithm_1"] - failure_sets["algorithm_2"]

    lines = [
        "# V2 Failure Analysis Report",
        "",
        "## Algorithm Names",
        "",
        "| label | implementation used in older files |",
        "| --- | --- |",
    ]
    for key in ["algorithm_1", "algorithm_2", "algorithm_3"]:
        lines.append(table_line([ALGORITHMS[key]["label"], ALGORITHMS[key]["legacy"]]))

    lines += [
        "",
        "## Failure Definition",
        "",
        "A row is counted as failed when any of these is true: expected target is not in top 20, behavior_success is 0, unsafe_confident_top1 is 1, or missing_clarification is 1.",
        "",
        "## Overall Failure Counts On The Previous Full V2 Run",
        "",
        "| algorithm | cases | any failure | failure rate | retrieval misses | behavior misses | unsafe top-1 | missing clarification | no result |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key in ["algorithm_1", "algorithm_2", "algorithm_3"]:
        item = summaries[key]
        lines.append(table_line([
            ALGORITHMS[key]["label"],
            f"{item['cases']:,}",
            f"{item['failures']:,}",
            pct(item["failure_rate"]),
            f"{item['retrieval_misses']:,}",
            f"{item['behavior_misses']:,}",
            f"{item['unsafe_confident_top1']:,}",
            f"{item['missing_clarification']:,}",
            f"{item['no_result']:,}",
        ]))

    lines += [
        "",
        "## Cross-Algorithm Failure Overlap",
        "",
        f"- All three algorithms failed the same row: `{len(all_three_fail):,}` rows.",
        f"- Algorithm 1 and Algorithm 2 failed, but Algorithm 3 recovered: `{len(child_fail_master_pass):,}` rows.",
        f"- Algorithm 3 failed while both child algorithms passed: `{len(master_only_fail):,}` rows.",
        "",
        "## Top Failure Categories",
    ]
    for key in ["algorithm_1", "algorithm_2", "algorithm_3"]:
        lines += [
            "",
            f"### {ALGORITHMS[key]['label']}",
            "",
            "| scope | category | cases | failures | failure rate | main cause |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
        for row in top_group(all_rows[key], ("scope", "category"), limit=12):
            lines.append(table_line([
                f"`{row['scope']}`",
                f"`{row['category']}`",
                f"{row['cases']:,}",
                f"{row['failures']:,}",
                pct(row["failure_rate"]),
                row["top_cause"],
            ]))

    lines += [
        "",
        "## Root Causes Across Failed Rows",
        "",
        "| algorithm | root cause | failed rows |",
        "| --- | --- | ---: |",
    ]
    for key in ["algorithm_1", "algorithm_2", "algorithm_3"]:
        counter = Counter(root_cause(row) for row in all_rows[key] if is_failure(row))
        for cause, count in counter.most_common(12):
            lines.append(table_line([ALGORITHMS[key]["label"], cause, f"{count:,}"]))

    lines += [
        "",
        "## What The Mistakes Are Coming From",
        "",
        "- The hardest failures are not ordinary one-letter typos. They cluster around multi-error chains, wrong-vowel/consonant-frame inputs, autocorrect or word-boundary artifacts, and short-prefix collisions.",
        "- Algorithm 2 has strong retrieval but produces many unsafe confident false positives. Its main weakness is safety behavior, not only ranking.",
        "- Algorithm 1 is safer, but it loses more rows when the query is heavily corrupted or when candidate generation returns no result.",
        "- Algorithm 3 improves the combined behavior by keeping Algorithm 2's recall and Algorithm 1's safety gates, but it still fails when neither child produces the correct family or when the correct family is too low after fusion.",
        "- Manual failures are mostly real-world compound typos: phonetic substitutions, dropped letters, added letters, and middle-of-word corruption. These are not well represented by a single edit operation.",
        "",
        "## Manual Failed Cases",
        "",
        "| edited input | right name | error type | Algorithm 1 rank/top1 | Algorithm 2 rank/top1 | Algorithm 3 rank/top1 | note |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in manual_rows:
        lines.append(table_line([
            f"`{row['input']}`",
            f"`{row['right_name']}`",
            row["manual_error_type"],
            f"{row['algorithm_1_first_rank']} / `{row['algorithm_1_top1']}`",
            f"{row['algorithm_2_first_rank']} / `{row['algorithm_2_top1']}`",
            f"{row['algorithm_3_first_rank']} / `{row['algorithm_3_top1']}`",
            row["analysis_note"],
        ]))

    manual_counts = Counter(row["manual_error_type"] for row in manual_rows)
    lines += [
        "",
        "## Manual Case Root-Cause Counts",
        "",
        "| manual error type | cases |",
        "| --- | ---: |",
    ]
    for kind, count in manual_counts.most_common():
        lines.append(table_line([kind, count]))

    lines += [
        "",
        "## Recommended Fixes",
        "",
        "1. Add a curated alias layer for repeated real-world misspellings from the manual table. These are high-value because they came from actual manual observation, not synthetic generation.",
        "2. Add stronger candidate generation for compound typos: edit distance 2-4, middle-character substitutions, dropped nasal/liquid consonants, and suffix corruption.",
        "3. Add phonetic rewrite rules for common pairs seen here: c/k/q, s/z, f/v, p/b, d/t, g/j, ch/sh, and Arabic-English hearing mistakes.",
        "4. Keep Algorithm 3's safety gate: do not turn every fuzzy recovery into a confident top-1. Use the new aliases as retrieval evidence, then still require confidence checks for dangerous short or colliding names.",
        "5. Add the manual cases as a small regression file and run them separately from the generated V2 benchmark so real user failures remain visible.",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    all_rows = {key: read_rows(config["path"]) for key, config in ALGORITHMS.items()}
    manual_rows = evaluate_manual_cases()

    manual_path = MANUAL_RESULTS_DIR / "algorithm_1_3_results.csv"
    report_path = FULL_RESULTS_DIR / "failure_analysis.md"
    summary_path = FULL_RESULTS_DIR / "failure_analysis_summary.json"

    write_csv(manual_path, manual_rows)
    write_report(report_path, all_rows, manual_rows)
    summary = {
        "algorithm_names": {key: config["legacy"] for key, config in ALGORITHMS.items()},
        "full_rows": {key: len(rows) for key, rows in all_rows.items()},
        "manual_cases": len(manual_rows),
        "manual_results": str(manual_path.relative_to(ROOT)),
        "report": str(report_path.relative_to(ROOT)),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

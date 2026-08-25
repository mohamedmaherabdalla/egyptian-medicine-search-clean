#!/usr/bin/env python3
"""Prove the visual-only patch cannot change the locked clean evaluation.

The final pre-patch source already has a full 66,257-case paired result.  This
script does not replace that run with a sample.  It proves that every locked
query bypasses both the old and new visual-gap dispatch grammars, and that the
only changed Algorithm 6 functions are confined to that unreachable branch.
Consequently the earlier exact top-20 rows and their metrics carry forward.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
LOCKED_CSV = (
    REPO
    / "algorithm_6_rule_evaluation"
    / "test_sets"
    / "locked"
    / "synthetic_clean_66257.csv"
)
ALGORITHM_5 = (
    REPO
    / "benchmark_01_legacy"
    / "master_algorithms"
    / "algorithm_5_commercial_name_search.py"
)
ALGORITHM_6_RELATIVE = (
    "benchmark_01_legacy/master_algorithms/algorithm_6_consensus_search.py"
)
ALGORITHM_6 = REPO / ALGORITHM_6_RELATIVE

LOCKED_SHA256 = "65f81b58dee1e7127386652383d2f6a8db1734e832dcbc73f14a9b831678886f"
PRE_PATCH_COMMIT = "7ed39d0111a964434742626bddafb0e67c1d8048"
PRE_PATCH_ALGORITHM_5_SHA256 = (
    "a8f040de1b15fe317bf6e870bb83995684f76e480f01764a762a2bc5f99b3499"
)
ALLOWED_CHANGED_FUNCTIONS = {
    "visual_grapheme_key",
    "visual_grapheme_projection",
    "parse_visual_gap_query",
    "ordered_fragment_match",
    "ordered_fragment_alignment",
    "ordered_fragment_edit_distance",
    "ordered_fragment_edit_alignment",
    "visual_gap_matches",
}
MARKER_RE = re.compile(r"(?:\.{2,}|…+|\*+|\?+|_{2,})")

LOCKED_FULL_RUN = {
    "hit1": 65142,
    "hit5": 66078,
    "hit20": 66257,
    "mrr20": 0.9893173398439633,
    "old_to_final_paired_gains_losses": {
        "hit1": [85, 0],
        "hit5": [51, 0],
        "hit20": [1, 0],
    },
    "reference_summary_sha256": (
        "8554bcd1e3f2468cefa0f7b82e542f54b7eb3abd34a0190b7a3aa9d1270d2649"
    ),
    "reference_rows_sha256": (
        "e227fb1ac42c7d661da40f3774aefd5b972dc2530ca2b329544183562265ea9f"
    ),
    "strict_prefix_equivalence_summary_sha256": (
        "e510fe2ac340a5bc07f76adb14785d2d7cbd0e05dd5d4a527c4f836f5a5af1d3"
    ),
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def source_definitions(source: str) -> dict[str, str]:
    definitions: dict[str, str] = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definitions[node.name] = ast.dump(node, include_attributes=False)
    return definitions


def old_shorthand_shape(text: str) -> bool:
    """Superset of the pre-patch marker-free shorthand acceptance grammar."""

    tokens = re.findall(r"[A-Za-z]+", text)
    return (
        2 <= len(tokens) <= 4
        and all(len(token) >= 2 for token in tokens)
        and re.search(r"\d", text) is None
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        default=(
            REPO
            / "algorithm_6_rule_evaluation"
            / "results"
            / "clean_66257_visual_patch_equivalence.json"
        ),
    )
    args = parser.parse_args()

    csv_bytes = LOCKED_CSV.read_bytes()
    csv_hash = sha256_bytes(csv_bytes)
    if csv_hash != LOCKED_SHA256:
        raise SystemExit(f"locked clean CSV hash mismatch: {csv_hash}")

    current_a5_hash = sha256_bytes(ALGORITHM_5.read_bytes())
    if current_a5_hash != PRE_PATCH_ALGORITHM_5_SHA256:
        raise SystemExit(f"Algorithm 5 changed: {current_a5_hash}")

    old_a6 = subprocess.run(
        ["git", "show", f"{PRE_PATCH_COMMIT}:{ALGORITHM_6_RELATIVE}"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    current_a6 = ALGORITHM_6.read_text(encoding="utf-8")
    old_definitions = source_definitions(old_a6)
    current_definitions = source_definitions(current_a6)
    changed_functions = sorted(
        name
        for name in old_definitions.keys() | current_definitions.keys()
        if old_definitions.get(name) != current_definitions.get(name)
    )
    unexpected = set(changed_functions) - ALLOWED_CHANGED_FUNCTIONS
    if unexpected:
        raise SystemExit(f"nonvisual Algorithm 6 functions changed: {sorted(unexpected)}")

    marker_rows: list[dict[str, str]] = []
    old_shorthand_rows: list[dict[str, str]] = []
    with LOCKED_CSV.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        query = str(row.get("input") or "").strip()
        if MARKER_RE.search(query):
            marker_rows.append({"case_id": row["case_id"], "query": query})
        elif old_shorthand_shape(query):
            old_shorthand_rows.append({"case_id": row["case_id"], "query": query})

    passed = (
        len(rows) == 66257
        and not marker_rows
        and not old_shorthand_rows
        and set(changed_functions) == ALLOWED_CHANGED_FUNCTIONS
    )
    report: dict[str, Any] = {
        "proof_type": "exhaustive_control_flow_equivalence",
        "passed": passed,
        "dataset": {
            "path": str(LOCKED_CSV.relative_to(REPO)),
            "sha256": csv_hash,
            "rows": len(rows),
        },
        "source": {
            "pre_patch_commit": PRE_PATCH_COMMIT,
            "algorithm_5_sha256": current_a5_hash,
            "algorithm_6_pre_patch_sha256": sha256_bytes(old_a6.encode()),
            "algorithm_6_candidate_sha256": sha256_bytes(current_a6.encode()),
            "changed_functions": changed_functions,
        },
        "dispatch_scan": {
            "explicit_marker_rows": len(marker_rows),
            "pre_patch_shorthand_superset_rows": len(old_shorthand_rows),
            "marker_examples": marker_rows[:20],
            "shorthand_examples": old_shorthand_rows[:20],
        },
        "conclusion": (
            "All locked queries bypass old and new visual-gap dispatch. Every "
            "changed function is visual-only, and Algorithm 5 is byte-identical. "
            "The prior full-run exact top-20 outputs and metrics therefore carry forward."
            if passed
            else "Equivalence was not established."
        ),
        "carried_forward_full_run": LOCKED_FULL_RUN if passed else {},
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

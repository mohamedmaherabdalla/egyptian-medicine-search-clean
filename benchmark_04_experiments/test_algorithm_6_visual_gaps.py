#!/usr/bin/env python3
"""Regression and generated-catalog tests for Algorithm 6 visual gaps."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALGORITHM_DIR = ROOT / "benchmark_01_legacy" / "master_algorithms"
sys.path.insert(0, str(ALGORITHM_DIR))

import algorithm_6_consensus_search as algorithm_6


def family_names(response: dict) -> list[str]:
    return [algorithm_6.result_name(item) for item in response["results"]]


def generated_targets(catalog: algorithm_6.Algorithm6Catalog) -> list[tuple[str, str]]:
    targets: dict[tuple[str, str], None] = {}
    for family in catalog.algorithm_5_catalog.rescue_index.families:
        group = family.variant_group or family.name
        for target in (family.head_compact, family.compact):
            if 8 <= len(target) <= 18:
                targets[(group, target)] = None
    ordered = sorted(targets)
    step = max(1, len(ordered) // 64)
    return ordered[::step][:64]


def main() -> None:
    catalog = algorithm_6.prepare_catalog()

    expected_cases = {
        "PANA...OL": ("PANADOL", "internal"),
        "JAK...ODAN": ("JACKODAN", "internal"),
        "RIVO...": ("RIVOTRIL", "trailing"),
        "...TRIL": ("RIVOTRIL", "leading"),
        "...VOT...": ("RIVOTRIL", "both_ends"),
        "...VOT...IL": ("RIVOTRIL", "leading"),
        "MELI CAM": ("MELOXICAM", "internal"),
    }
    for query, (expected, gap_mode) in expected_cases.items():
        response = algorithm_6.search_catalog(catalog, query, 20)
        assert response["decision_type"] == "visual_gap_matches", query
        assert expected in family_names(response), (query, family_names(response))
        assert response["visual_gap"]["mode"] == gap_mode, query
        assert response["confirmation_required"] is True, query
        assert all(item["needs_clarification"] for item in response["results"]), query

    ordinary = algorithm_6.search_catalog(catalog, "PANADOL EXTRA", 20)
    assert ordinary["decision_type"] != "visual_gap_matches"
    assert family_names(ordinary)[0] == "PANADOL EXTRA"

    generated = generated_targets(catalog)
    hits = 0
    for expected_group, target in generated:
        query = f"{target[:3]}...{target[-3:]}"
        response = algorithm_6.search_catalog(catalog, query, 20)
        hits += expected_group in family_names(response)
        assert response["decision_type"] == "visual_gap_matches", query
        assert response["confirmation_required"] is True, query

    hit_rate = hits / len(generated)
    assert hit_rate >= 0.95, f"generated visual-gap Hit@20={hit_rate:.3%}"
    print(
        f"Algorithm 6 visual gaps: {hits}/{len(generated)} "
        f"generated Hit@20 ({hit_rate:.2%}); 5/5 acceptance cases passed"
    )


if __name__ == "__main__":
    main()

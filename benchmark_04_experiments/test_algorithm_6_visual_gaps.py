#!/usr/bin/env python3
"""Regression and generated-catalog tests for Algorithm 6 visual gaps."""

from __future__ import annotations

import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALGORITHM_DIR = ROOT / "benchmark_01_legacy" / "master_algorithms"
sys.path.insert(0, str(ALGORITHM_DIR))

import algorithm_6_consensus_search as algorithm_6


def family_names(response: dict) -> list[str]:
    return [algorithm_6.result_name(item) for item in response["results"]]


def variant_group_names(response: dict) -> list[str]:
    return [
        str(item.get("variant_group") or item.get("name") or "")
        for item in response["results"]
    ]


def exact_family_names(response: dict) -> list[str]:
    return [str(item.get("matched_family_name") or "") for item in response["results"]]


def exact_family_row(response: dict, family_name: str) -> dict:
    family_key = algorithm_6.current_app.compact_key(family_name)
    return next(
        item
        for item in response["results"]
        if item.get("matched_family_key") == family_key
    )


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

    # Twenty explicit hard patterns cover all four gap modes, both edge
    # directions, internal fragments, and one/two shared OCR grapheme rules.
    expected_cases = {
        "PANA...OL": ("PANADOL", "internal"),
        "JAK...ODAN": ("JACKODAN", "internal"),
        "RIVO...": ("RIVOTRIL", "trailing"),
        "...TRIL": ("RIVOTRIL", "leading"),
        "...VOT...": ("RIVOTRIL", "both_ends"),
        "...VOT...IL": ("RIVOTRIL", "leading"),
        "MELI CAM": ("MELOXICAM", "internal"),
        "CLICY...": ("DICYNONE", "trailing"),
        "...TIDOR": ("BACTICLOR", "leading"),
        "BA...TIDOR": ("BACTICLOR", "internal"),
        "ALEPI...": ("DEPIDERM", "trailing"),
        "...PIALERM": ("DEPIDERM", "leading"),
        "...GTHOTRGXAT...": ("METHOTREXATE", "both_ends"),
        "...ITHOTRIXAT...": ("METHOTREXATE", "both_ends"),
        "AUEM...TIN": ("AUGMENTIN", "internal"),
        "...UEMENTIN": ("AUGMENTIN", "leading"),
        "AUGMGN...": ("AUGMENTIN", "trailing"),
        "...UEMENTI...": ("AUGMENTIN", "both_ends"),
        "...CANDI": ("OMEGA RX JELLY CANDY", "leading"),
        "DICI...ONE": ("DICYNONE", "internal"),
    }
    assert len(expected_cases) == 20
    for query, (expected, gap_mode) in expected_cases.items():
        response = algorithm_6.search_catalog(catalog, query, 20)
        assert response["decision_type"] == "visual_gap_matches", query
        assert expected in variant_group_names(response), (
            query,
            variant_group_names(response),
        )
        assert family_names(response) == exact_family_names(response), query
        assert response["visual_gap"]["mode"] == gap_mode, query
        assert response["confirmation_required"] is True, query
        assert all(item["needs_clarification"] for item in response["results"]), query
        assert all(item["confirmation_required"] for item in response["results"]), query
        assert all(item.get("matched_family_name") for item in response["results"]), query
        assert all(
            item.get("matched_family_key")
            == algorithm_6.current_app.compact_key(item["matched_family_name"])
            for item in response["results"]
        ), query

    # The same OCR-confusion targets must stay recoverable through the public
    # exact-base display identity used by the API.  A leading marker is not
    # present because these targets begin at the corrected visible fragment.
    for query, expected in (
        ("CLICY...", "DICYNONE"),
        ("BACTID...", "BACTICLOR"),
        ("ALEPI...", "DEPIDERM"),
    ):
        response = algorithm_6.search_catalog(catalog, query, 20)
        assert expected in family_names(response), (query, family_names(response))

    # Edge markers are strict: a leading/trailing gap must hide at least one
    # character at that edge.  Confusion tolerance must not erase that rule.
    edge_negatives = {
        "...PANADOL": "PANADOL",
        "PANADOL...": "PANADOL",
        "...DICYNONE": "DICYNONE",
        "BACTICLOR...": "BACTICLOR",
        "...PANA...DOL": "PANADOL",
        "PANA...DOL...": "PANADOL",
        "...CLICY...": "DICYNONE",
        "...BACTID...": "BACTICLOR",
        "...ALEPI...": "DEPIDERM",
    }
    for query, forbidden in edge_negatives.items():
        response = algorithm_6.search_catalog(catalog, query, 20)
        forbidden_target = algorithm_6.current_app.compact_key(forbidden)
        assert all(
            item["matched_target"] != forbidden_target
            for item in response["results"]
        ), (query, [item["matched_target"] for item in response["results"]])
        assert all(item["hidden_character_count"] > 0 for item in response["results"]), query
        assert response["confirmation_required"] is True, query

    # Every explicit internal marker hides at least one target character.
    # Multiple markers enforce that independently, while marker-free shorthand
    # deliberately retains its zero-character internal-gap behavior.
    internal_gap_negatives = {
        "PANA...DOL": "PANADOL",
        "PAN...ADOL": "PANADOL",
        "RI...VO...TRIL": "RIVOTRIL",
    }
    for query, forbidden in internal_gap_negatives.items():
        response = algorithm_6.search_catalog(catalog, query, 20)
        forbidden_target = algorithm_6.current_app.compact_key(forbidden)
        assert all(
            item["matched_target"] != forbidden_target
            for item in response["results"]
        ), (query, [item["matched_target"] for item in response["results"]])
        assert response["confirmation_required"] is True, query

    multi_gap = algorithm_6.search_catalog(catalog, "RI...OT...IL", 20)
    assert "RIVOTRIL" in variant_group_names(multi_gap), variant_group_names(multi_gap)
    assert family_names(multi_gap) == exact_family_names(multi_gap)
    assert multi_gap["confirmation_required"] is True

    # Broad variant groups must not erase the exact bases that independently
    # satisfy a gap. Optional product context needs every matched BRUFEN base
    # in order to distinguish the plain, COLD, and FLU catalogs safely.
    folded_bases = algorithm_6.search_catalog(catalog, "BRU...", 20)
    folded_names = {
        item["matched_family_name"] for item in folded_bases["results"]
    }
    assert {"BRUFEN", "BRUFEN COLD", "BRUFEN FLU"} <= folded_names, folded_names
    assert all(
        item["candidate_id"]
        == f"ALG6-GAP-{item['matched_family_key']}"
        for item in folded_bases["results"]
    )

    repeated_leading = algorithm_6.ordered_fragment_match(
        "ABABC",
        ("AB",),
        anchor_start=False,
        anchor_end=False,
        require_edge_gap=True,
    )
    assert repeated_leading is True

    repeated_suffix = algorithm_6.ordered_fragment_match(
        "ATENOLOL",
        ("AT", "OL"),
        anchor_start=True,
        anchor_end=True,
        require_edge_gap=True,
    )
    assert repeated_suffix is True
    repeated_suffix_response = algorithm_6.search_catalog(catalog, "AT...OL", 20)
    assert "ATENOLOL" in exact_family_names(repeated_suffix_response), exact_family_names(
        repeated_suffix_response
    )

    # Only whitespace-separated words are shorthand. A period or hyphen is an
    # ordinary spelling separator and must not silently acquire gap semantics.
    for ordinary_separator_query in ("PANA.DOL", "PANA-DOL"):
        ordinary_separator = algorithm_6.search_catalog(
            catalog,
            ordinary_separator_query,
            20,
        )
        assert ordinary_separator["decision_type"] != "visual_gap_matches", (
            ordinary_separator_query,
            ordinary_separator["decision_type"],
        )

    # Punctuation beside an explicit edge marker carries no visible evidence.
    # Compact fragments, rather than raw marker offsets, decide the anchors.
    for punctuation_query, expected_mode in (
        ("(...TRIL", "leading"),
        ("...TRIL)", "leading"),
        ("RIVO... )", "trailing"),
    ):
        punctuation_response = algorithm_6.search_catalog(
            catalog,
            punctuation_query,
            20,
        )
        assert punctuation_response["decision_type"] == "visual_gap_matches", (
            punctuation_query,
            punctuation_response["decision_type"],
        )
        assert punctuation_response["visual_gap"]["mode"] == expected_mode
        assert "RIVOTRIL" in exact_family_names(punctuation_response), (
            punctuation_query,
            exact_family_names(punctuation_response),
        )

    # Alignment metrics describe target characters, not raw OCR characters.
    # This matters when one observed grapheme expands or contracts (CL <-> D).
    for metric_query, metric_family, hidden, coverage in (
        ("CLICY...", "DICYNONE", 4, 0.5),
        ("BACTID...", "BACTICLOR", 2, 7 / 9),
        ("...TIDOR", "BACTICLOR", 3, 6 / 9),
    ):
        metric_response = algorithm_6.search_catalog(catalog, metric_query, 20)
        metric_row = exact_family_row(metric_response, metric_family)
        assert metric_row["hidden_character_count"] == hidden, (
            metric_query,
            metric_row["hidden_character_count"],
        )
        assert abs(metric_row["visible_coverage"] - coverage) < 1e-6, (
            metric_query,
            metric_row["visible_coverage"],
        )
        assert "visual_gap_grapheme_confusion" in metric_row["reasons"]

    shorthand = algorithm_6.search_catalog(catalog, "PANA DOL", 20)
    assert shorthand["decision_type"] == "visual_gap_matches"
    assert "PANADOL" in variant_group_names(shorthand), variant_group_names(shorthand)
    assert family_names(shorthand) == exact_family_names(shorthand)
    assert shorthand["confirmation_required"] is True

    # A gap plus a low-cost confusion can support two literal catalog names.
    # Both must remain visible and the response must stay confirmation-only.
    collision_patterns = {
        "TRICHO...": {"TRICHOGEL", "TRICHOGYL"},
        "AMOX...CILLIN": {"AMOXICILLIN", "AMOXYCILLIN"},
        "MEL...NO": {"MELANO", "MILANO"},
        "BALM...": {"BALMEX", "BALMIX"},
    }
    for query, expected in collision_patterns.items():
        response = algorithm_6.search_catalog(catalog, query, 20)
        keys = {
            algorithm_6.current_app.compact_key(name)
            for name in variant_group_names(response)
        }
        assert expected <= keys, (query, keys)
        assert response["confirmation_required"] is True, query
        assert all(item["confirmation_required"] for item in response["results"]), query

    # One-to-four visible characters are too weak to justify OCR-confusion
    # expansion.  Raw edge/internal matching may still return choices, but no
    # result may claim a direct grapheme-confusion match below the five-character
    # evidence floor shared with ordinary fuzzy gap matching.
    short_confusion_guards = [
        "IE...",
        "...GE",
        "D...R",
        "...IE...",
        "E...D",
        "CL...",
        "...AL",
        "I...Y",
    ]
    for query in short_confusion_guards:
        response = algorithm_6.search_catalog(catalog, query, 20)
        assert response["decision_type"] == "visual_gap_matches", query
        assert all(
            "visual_gap_grapheme_confusion"
            not in set(item.get("reasons") or ())
            for item in response["results"]
        ), (query, response["results"][:3])
        assert response["confirmation_required"] is True, query
        assert all(item["confirmation_required"] for item in response["results"]), query

    # The maximum supported visible confusion input stays bounded in both
    # variant count and loaded-catalog latency.  More than four fragments are
    # not parsed as a visual-gap request, preventing marker-heavy expansion.
    heavy_fragment = "E" * 24
    heavy_patterns = algorithm_6.visual_gap_confusion_patterns(
        catalog,
        (heavy_fragment,),
        maximum_cost=1.40,
        maximum_confusions=2,
    )
    assert len(heavy_patterns) <= algorithm_6.VISUAL_GAP_CONFUSION_PATTERN_LIMIT
    started = time.perf_counter()
    heavy_response = algorithm_6.search_catalog(
        catalog,
        f"{heavy_fragment}...",
        20,
    )
    heavy_elapsed = time.perf_counter() - started
    assert heavy_elapsed < 2.0, heavy_elapsed
    assert heavy_response["confirmation_required"] is True
    assert algorithm_6.parse_visual_gap_query(
        "IE...GE...YI...EG...DI",
        catalog,
    ) is None

    ordinary = algorithm_6.search_catalog(catalog, "PANADOL EXTRA", 20)
    assert ordinary["decision_type"] != "visual_gap_matches"
    assert family_names(ordinary)[0] == "PANADOL EXTRA"

    generated = generated_targets(catalog)
    hits = 0
    for expected_group, target in generated:
        query = f"{target[:3]}...{target[-3:]}"
        response = algorithm_6.search_catalog(catalog, query, 20)
        hits += expected_group in variant_group_names(response)
        assert family_names(response) == exact_family_names(response), query
        assert response["decision_type"] == "visual_gap_matches", query
        assert response["confirmation_required"] is True, query

    hit_rate = hits / len(generated)
    assert hit_rate >= 0.95, f"generated visual-gap Hit@20={hit_rate:.3%}"
    print(
        f"Algorithm 6 visual gaps: {hits}/{len(generated)} "
        f"generated Hit@20 ({hit_rate:.2%}); "
        f"{len(expected_cases)}/20 explicit hard cases and "
        f"{len(edge_negatives)}/9 edge negatives and "
        f"{len(internal_gap_negatives)}/3 internal-gap negatives and "
        f"{len(collision_patterns)}/4 collision patterns and "
        f"{len(short_confusion_guards)}/8 short-confusion guards passed; "
        f"heavy gap {len(heavy_patterns)}/512 variants in "
        f"{heavy_elapsed:.3f}s"
    )


if __name__ == "__main__":
    main()

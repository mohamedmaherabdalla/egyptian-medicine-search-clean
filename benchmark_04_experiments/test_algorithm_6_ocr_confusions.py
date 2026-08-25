#!/usr/bin/env python3
"""Explicit hard OCR-confusion and exact-name safety tests for Algorithm 6."""

from __future__ import annotations

import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALGORITHM_DIR = ROOT / "benchmark_01_legacy" / "master_algorithms"
sys.path.insert(0, str(ALGORITHM_DIR))

import algorithm_6_consensus_search as algorithm_6


def compact(value: object) -> str:
    return algorithm_6.current_app.compact_key(value)


def result_keys(response: dict) -> list[str]:
    return [compact(algorithm_6.result_name(item)) for item in response["results"]]


def main() -> None:
    catalog = algorithm_6.prepare_catalog()

    # Twenty-three explicit, catalog-backed positives cover one/two E-G, I-E-Y,
    # D-CL, D-AL, edge, middle, and first-character handwriting confusions.
    positives = [
        ("AUEMENTIN", "AUGMENTIN", 1),
        ("AUGMGNTIN", "AUGMENTIN", 1),
        ("EARDX", "GARDX", 1),
        ("NGXIUM", "NEXIUM", 1),
        ("BRUFGN", "BRUFEN", 1),
        ("AEEL", "AGEAL", 20),
        ("AGGL", "AGEAL", 20),
        ("MGTHOTRGXATE", "METHOTREXATE", 1),
        ("MITHOTRIXATE", "METHOTREXATE", 1),
        ("MYTHOTRYXATE", "METHOTREXATE", 1),
        ("CANDI", "CANDY", 1),
        ("EILIA", "EYLEA", 20),
        ("DICINONE", "DICYNONE", 1),
        ("CLICYNONE", "DICYNONE", 1),
        ("BACTIDOR", "BACTICLOR", 1),
        ("ALEPIDERM", "DEPIDERM", 1),
        ("DEEN", "ALEEN", 1),
        ("DEXA", "ALEXA", 1),
        ("ACLCLOH", "ADDOH", 1),
        ("DKDINE", "ALKALINE", 1),
        ("OMGPRAZOLG", "OMEPRAZOLESPLENDIDPHARMA", 20),
        ("OMIPRAZOLI", "OMEPRAZOLESPLENDIDPHARMA", 20),
        ("OMYPRAZOLY", "OMEPRAZOLESPLENDIDPHARMA", 20),
    ]
    for query, expected, maximum_rank in positives:
        response = algorithm_6.search_catalog(catalog, query, 20)
        keys = result_keys(response)
        assert expected in keys, (query, keys)
        assert keys.index(expected) + 1 <= maximum_rank, (query, keys)
        assert response["confirmation_required"] is True, query
        assert all(item["needs_clarification"] for item in response["results"]), query
        assert all(item["confirmation_required"] for item in response["results"]), query

    # Locked fair-OCR regressions.  These queries exposed two unsafe ways of
    # applying the new confusion rules globally: E/G must stay bounded to the
    # explicit grapheme paths, and legacy first-character groups must not
    # inflate the retrieval pool.  Keep the historical targets/ranks intact.
    locked_regressions = [
        ("LGCMU", "LACTO", 1),
        ("KEONOOL", "KETOROLAC", 20),
    ]
    for query, expected, maximum_rank in locked_regressions:
        response = algorithm_6.search_catalog(catalog, query, 20)
        keys = result_keys(response)
        assert expected in keys, (query, keys)
        assert keys.index(expected) + 1 <= maximum_rank, (query, keys)
        assert response["confirmation_required"] is True, query
        assert all(item["needs_clarification"] for item in response["results"]), query
        assert all(item["confirmation_required"] for item in response["results"]), query

    # Lock the clean-66,257 safety repairs, their first-pass collateral guards,
    # the sole historical Hit@20 recovery, and the strict-prefix family-head
    # exception verified by the fair-412 set.  These cases make the expensive
    # paired evaluations reproducible as a fast source-level regression gate.
    clean_and_fair_regressions = [
        ("ACTIVEN", "ACTIVENT", 1),
        ("CITAL", "CITALO", 1),
        ("GVITON", "K VITON", 1),
        ("PEXE", "PEXO", 1),
        ("RONE", "RONEX", 1),
        ("SILDAN", "SILDEN", 1),
        ("CLAZOL", "CALAZOL", 1),
        ("PANAL", "PABAL", 1),
        ("BJEIND", "H JOINT", 1),
        ("SEORPIPUHAIRCONCLITIONER", "SEROPIPE HAIR CONDITIONER", 1),
        ("YRSOCLIOL", "URSOCHOL", 1),
        ("CLOLOCL", "DOLCYL", 5),
        ("ACLOX", "ADOX", 1),
        ("OMEG", "OMEGY", 1),
        ("ROXI", "ROXID", 1),
        ("TIMOGE", "TIMOGEL", 1),
        ("TLAVI", "TALAVI", 1),
        ("URSOCLOL", "URSODOL", 1),
        ("VITALIAIR", "VITA HAIR", 1),
        ("ABDSOGOG LAY", "ABASAGLAR CARTRIDGES", 1),
        ("ABDUSONG LAR", "ABASAGLAR CARTRIDGES", 1),
        ("ALBA SAGL ATZ", "ABASAGLAR CARTRIDGES", 1),
        ("ABACAVIR LAR", "ABASAGLAR CARTRIDGES", 1),
    ]
    for query, expected, maximum_rank in clean_and_fair_regressions:
        response = algorithm_6.search_catalog(catalog, query, 20)
        keys = result_keys(response)
        expected_key = compact(expected)
        assert expected_key in keys, (query, keys)
        assert keys.index(expected_key) + 1 <= maximum_rank, (query, keys)
        assert response["confirmation_required"] is True, query
        assert all(item["needs_clarification"] for item in response["results"]), query
        assert all(item["confirmation_required"] for item in response["results"]), query

    # Literal catalog names always remain first even when a confusion rewrite
    # reaches another real family.  These are the catalog's known collision
    # directions, not fabricated negatives.
    exact_guards = [
        "ORDEX", "ORALEX", "TDA", "TALA", "TOBRADEX", "TOBRAALEX",
        "URAL", "AMOXICILLIN", "AMOXYCILLIN", "CODE", "CODY", "SELE",
        "SYLE", "TRICHOGEL", "TRICHOGYL", "BALMEX", "BALMIX", "CEFEX",
        "CEFIX", "MELANO", "MILANO",
    ]
    for query in exact_guards:
        response = algorithm_6.search_catalog(catalog, query, 20)
        assert result_keys(response)[0] == query, (query, result_keys(response))
        assert response["confirmation_required"] is True, query
        assert response["results"][0]["needs_clarification"] is True, query
        assert response["results"][0]["confirmation_required"] is True, query

    # A non-catalog spelling can be one direct rewrite away from two catalog
    # families.  Both alternatives may be shown, but neither may receive the
    # deterministic bounded-confusion correction reserved for a unique target.
    ambiguous_rewrites = [
        ("MYLANO", {"MELANO", "MILANO"}),
        ("SILE", {"SELE", "SYLE"}),
        ("CODI", {"CODE", "CODY"}),
        ("TRICHOGIL", {"TRICHOGEL", "TRICHOGYL"}),
        ("AMOXECILLIN", {"AMOXICILLIN", "AMOXYCILLIN"}),
        ("CEFYX", {"CEFEX", "CEFIX"}),
        ("BALMYX", {"BALMEX", "BALMIX"}),
    ]
    for query, expected in ambiguous_rewrites:
        response = algorithm_6.search_catalog(catalog, query, 20)
        keys = set(result_keys(response))
        assert expected <= keys, (query, keys)
        assert all(
            "bounded_grapheme_confusion_correction"
            not in set(item.get("reasons") or ())
            for item in response["results"]
        ), (query, response["results"][:3])
        assert response["confirmation_required"] is True, query
        assert all(item["needs_clarification"] for item in response["results"]), query
        assert all(item["confirmation_required"] for item in response["results"]), query

    # Long phonetic collapses such as CKS->X and GHT->T can hide one further
    # ordinary edit behind a two-character length change.  The bounded helper
    # must enumerate the complete exact-family set, protect the character
    # created by the collapse from a second rewrite, and surface every member
    # without changing the incumbent rank-one result.
    collapse_cases = [
        ("CKSEFO", {"XEFO"}),
        ("GHTAXA", {"TADA", "TALA"}),
        ("OGHTA", {"OTAL", "VOTA", "YOTA"}),
        ("XSSACKS", {"ASSAX"}),
    ]
    for query, expected in collapse_cases:
        evidence = catalog.algorithm_5_module.phonetic_collapse_one_edit_family_evidence(
            catalog.algorithm_5_catalog.rescue_index,
            query,
        )
        evidence_keys = {
            catalog.algorithm_5_catalog.rescue_index.families[family_id].compact
            for family_id in evidence
        }
        assert evidence_keys == expected, (query, evidence_keys)
        response = algorithm_6.search_catalog(catalog, query, 20)
        keys = set(result_keys(response))
        assert expected <= keys, (query, keys)
        assert response["status"] == "ambiguous", (query, response["status"])
        assert response["confirmation_required"] is True, query
        assert response.get("calibrated_likely_match") is not True, query
        expected_rows = [
            item
            for item in response["results"]
            if compact(algorithm_6.result_name(item)) in expected
        ]
        assert len(expected_rows) == len(expected), (query, expected_rows)
        assert all(item["needs_clarification"] for item in expected_rows), query
        assert all(item["confirmation_required"] for item in response["results"]), query
    assert "OXA" not in {
        catalog.algorithm_5_catalog.rescue_index.families[family_id].compact
        for family_id in (
            catalog.algorithm_5_module.phonetic_collapse_one_edit_family_evidence(
                catalog.algorithm_5_catalog.rescue_index,
                "OGHTA",
            )
        )
    }
    atomic_collapse_guards = [
        ("OGHTAL", "OTAL"),
        ("GHTADA", "TADA"),
        ("GHTALA", "TALA"),
        ("TADA", "TADA"),
        ("TALA", "TALA"),
    ]
    for query, expected in atomic_collapse_guards:
        response = algorithm_6.search_catalog(catalog, query, 20)
        assert result_keys(response)[0] == expected, (query, result_keys(response))
        assert response["confirmation_required"] is True, query

    # Non-transitivity guard: the two direct rules I->E and E->G must not
    # compose on one original character into I->G.
    variants = {
        value
        for value, _, _ in catalog.algorithm_5_module.grapheme_confusion_variants(
            "IARDX",
            max_confusions=2,
        )
    }
    assert "GARDX" not in variants, variants

    started = time.perf_counter()
    long_variants = catalog.algorithm_5_module.grapheme_confusion_variants(
        "IEYG" * 30,
        max_confusions=2,
    )
    elapsed = time.perf_counter() - started
    assert long_variants == []
    assert elapsed < 0.10, elapsed

    print(
        "Algorithm 6 OCR confusions: "
        f"{len(positives)}/23 positives, "
        f"{len(locked_regressions)}/2 locked regressions, "
        f"{len(clean_and_fair_regressions)}/23 clean/fair safety regressions, "
        f"{len(exact_guards)}/21 exact guards, "
        f"{len(ambiguous_rewrites)}/7 ambiguity guards, "
        f"{len(collapse_cases)}/4 long-phonetic-collapse guards, "
        f"{len(atomic_collapse_guards)}/5 collapse rank-one guards, "
        "and non-transitivity passed"
    )


if __name__ == "__main__":
    main()

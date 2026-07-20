#!/usr/bin/env python3
"""Focused regression tests for the six-type search mistake framework."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MASTER_DIR = ROOT / "benchmark_01_legacy" / "master_algorithms"
if str(MASTER_DIR) not in sys.path:
    sys.path.insert(0, str(MASTER_DIR))

import algorithm_4_commercial_name_search as algorithm4


class MistakeFrameworkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = algorithm4.prepare_catalog()

    def search(self, query: object) -> dict[str, object]:
        return algorithm4.search_catalog(self.catalog, query, 20)

    def test_plain_exact_name_stays_exact_and_exposes_variants(self) -> None:
        response = self.search("abimol")
        top = response["results"][0]
        self.assertEqual(top["name"], "ABIMOL")
        self.assertEqual(response["decision_type"], "family_variant_selection")
        self.assertIn("ABIMOL EXTRA", top["variants"])

    def test_unreadable_continuation_excludes_completed_short_name(self) -> None:
        response = self.search({
            "text": "abimol",
            "unreadable_continuation": True,
        })
        self.assertEqual(response["decision_type"], "unreadable_continuation_matches")
        self.assertEqual(response["results"][0]["name"], "ABIMOL EXTRA")
        self.assertNotIn("ABIMOL", [row["name"] for row in response["results"]])

    def test_unreadable_after_matches_longer_family(self) -> None:
        response = self.search({
            "text": "abimol",
            "unreadable_mode": "after",
        })
        self.assertEqual(response["decision_type"], "unreadable_after_matches")
        self.assertEqual(response["results"][0]["name"], "ABIMOL EXTRA")

    def test_unreadable_before_matches_visible_ending(self) -> None:
        response = self.search({
            "text": "molextra",
            "unreadable_mode": "before",
        })
        self.assertEqual(response["decision_type"], "unreadable_before_matches")
        self.assertEqual(response["results"][0]["name"], "ABIMOL EXTRA")

    def test_unreadable_middle_uses_both_visible_fragments(self) -> None:
        response = self.search({
            "text": "abi",
            "unreadable_mode": "middle",
            "ending_fragment": "extra",
        })
        self.assertEqual(response["decision_type"], "unreadable_middle_matches")
        self.assertEqual(response["results"][0]["name"], "ABIMOL EXTRA")

    def test_impossible_unreadable_pattern_does_not_fall_back(self) -> None:
        response = self.search({
            "text": "abimol",
            "unreadable_mode": "before",
        })
        self.assertEqual(response["status"], "no_match")
        self.assertEqual(response["results"], [])

    def test_equal_distance_candidates_remain_ambiguous(self) -> None:
        response = self.search("conal")
        self.assertEqual(response["decision_type"], "equal_distance_ambiguity")
        self.assertTrue(all(row["needs_clarification"] for row in response["results"][:3]))

    def test_multi_token_false_positive_no_longer_beats_flector(self) -> None:
        response = self.search("flacton")
        self.assertEqual(response["results"][0]["name"], "FLECTOR")

    def test_low_confidence_short_query_keeps_length_compatible_candidates(self) -> None:
        response = self.search("taves")
        names = [row["name"] for row in response["results"]]
        self.assertIn("TAREG", names)

    def test_three_character_query_uses_the_delete_index(self) -> None:
        response = self.search("rio")
        self.assertEqual(response["results"][0]["name"], "RIVO")

    def test_ordered_two_letter_omission_can_break_an_equal_edit_tie(self) -> None:
        response = self.search("biato")
        self.assertEqual(response["results"][0]["name"], "IBIACTO")

    def test_validated_family_heads_recover_different_typo_shapes(self) -> None:
        cases = [
            ("coushsed", "COUGHSED"),
            ("opelx", "OPLEX"),
            ("devaol", "DEVAROL"),
            ("bronchloin", "BRONCHOLIN"),
        ]
        for query, expected_head in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertTrue(response["results"][0]["name"].startswith(expected_head))
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_dual_supported_strictly_closer_candidate_can_move_first(self) -> None:
        top = algorithm4.Candidate(
            key="ALPHA",
            name="ALPHA",
            commercial_name="ALPHA",
            external_rank=1,
            rescue_rank=1,
            score=1.0,
            raw_edit_distance=2,
        )
        closer = algorithm4.Candidate(
            key="BETA",
            name="BETA",
            commercial_name="BETA",
            external_rank=3,
            rescue_rank=2,
            score=0.9,
            raw_edit_distance=1,
        )
        ranked = algorithm4.rank_candidates([top, closer], "QUERY", brand_like=True)
        self.assertIs(ranked[0], closer)

    def test_equal_distance_candidates_keep_the_model_order(self) -> None:
        top = algorithm4.Candidate(
            key="ALPHA",
            name="ALPHA",
            commercial_name="ALPHA",
            external_rank=1,
            rescue_rank=1,
            score=1.0,
            raw_edit_distance=1,
        )
        equal = algorithm4.Candidate(
            key="BETA",
            name="BETA",
            commercial_name="BETA",
            external_rank=2,
            rescue_rank=2,
            score=0.9,
            raw_edit_distance=1,
        )
        ranked = algorithm4.rank_candidates([top, equal], "QUERY", brand_like=True)
        self.assertIs(ranked[0], top)

    def test_bounded_full_name_correction_does_not_require_dual_retrieval(self) -> None:
        top = algorithm4.Candidate(
            key="ALPHA",
            name="ALPHA",
            commercial_name="ALPHA",
            external_rank=1,
            rescue_rank=1,
            score=1.0,
            raw_edit_distance=3,
            weighted_edit_distance=2.5,
        )
        closer = algorithm4.Candidate(
            key="BETA",
            name="BETA",
            commercial_name="BETA",
            rescue_rank=2,
            score=0.7,
            raw_edit_distance=2,
            weighted_edit_distance=2.0,
        )
        ranked = algorithm4.rank_candidates([top, closer], "QUERY", brand_like=True)
        self.assertIs(ranked[0], closer)
        self.assertIn("strict_full_name_correction", closer.reasons)

    def test_full_name_correction_preserves_a_closer_validated_family_head(self) -> None:
        family_head = algorithm4.Candidate(
            key="ALPHAPACK",
            name="ALPHAPACK",
            commercial_name="ALPHAPACK",
            external_rank=1,
            rescue_rank=1,
            score=1.0,
            raw_edit_distance=8,
            weighted_edit_distance=1.0,
            head_raw_edit_distance=1,
            is_variant_family=True,
            variant_group="ALPHA",
            reasons={"variant_head_edit"},
        )
        full_name = algorithm4.Candidate(
            key="BETA",
            name="BETA",
            commercial_name="BETA",
            rescue_rank=2,
            score=0.8,
            raw_edit_distance=2,
            weighted_edit_distance=0.8,
        )
        ranked = algorithm4.rank_candidates(
            [family_head, full_name],
            "QUERY",
            brand_like=True,
        )
        self.assertIs(ranked[0], family_head)

    def test_full_name_correction_preserves_combined_phonetic_evidence(self) -> None:
        supported_top = algorithm4.Candidate(
            key="ALPHA",
            name="ALPHA",
            commercial_name="ALPHA",
            external_rank=1,
            rescue_rank=1,
            score=1.0,
            raw_edit_distance=3,
            weighted_edit_distance=2.5,
            reasons={"phonetic_exact", "skeleton_exact"},
        )
        spelling_only = algorithm4.Candidate(
            key="BETA",
            name="BETA",
            commercial_name="BETA",
            rescue_rank=2,
            score=0.7,
            raw_edit_distance=2,
            weighted_edit_distance=2.0,
        )
        ranked = algorithm4.rank_candidates(
            [supported_top, spelling_only],
            "QUERY",
            brand_like=True,
        )
        self.assertIs(ranked[0], supported_top)

    def test_validated_family_head_uses_head_distance(self) -> None:
        top = algorithm4.Candidate(
            key="ALPHA",
            name="ALPHA",
            commercial_name="ALPHA",
            external_rank=1,
            rescue_rank=1,
            score=1.0,
            raw_edit_distance=2,
        )
        family_variant = algorithm4.Candidate(
            key="BETAPACK",
            name="BETA PACK",
            commercial_name="BETA PACK",
            external_rank=2,
            rescue_rank=1,
            score=0.1,
            raw_edit_distance=8,
            head_raw_edit_distance=1,
            is_variant_family=True,
            variant_group="BETA",
            reasons={"variant_head_edit"},
        )
        ranked = algorithm4.rank_candidates([top, family_variant], "QUERY", brand_like=True)
        self.assertIs(ranked[0], family_variant)


if __name__ == "__main__":
    unittest.main()

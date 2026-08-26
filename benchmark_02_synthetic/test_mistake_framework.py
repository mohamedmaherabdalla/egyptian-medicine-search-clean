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

import algorithm_5_commercial_name_search as algorithm5
import algorithm_4_commercial_name_search as algorithm4


class Algorithm4ContextParserTest(unittest.TestCase):
    def test_strength_form_route_and_release_are_separate_evidence(self) -> None:
        context = algorithm4.parse_query_context("voltaren 100mg sr tablet")

        self.assertEqual(context.strengths, frozenset({"100MG"}))
        self.assertEqual(context.forms, frozenset({"tablet"}))
        self.assertEqual(context.routes, frozenset({"oral_solid"}))
        self.assertEqual(context.release_types, frozenset({"sustained_release"}))

    def test_catalog_and_user_thousands_punctuation_normalize_equally(self) -> None:
        user = algorithm4.parse_strengths("200,000 I.U amp")
        catalog = algorithm4.parse_strengths("200.000 I.U / 2 ML amp")

        self.assertTrue(algorithm4.strength_sets_compatible(user, catalog))

    def test_context_cleaning_keeps_only_brand_evidence(self) -> None:
        self.assertEqual(
            algorithm4.clean_context_query("augmentin 457mg/5ml suspension"),
            "AUGMENTIN",
        )


class MistakeFrameworkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = algorithm5.prepare_catalog()

    def search(self, query: object) -> dict[str, object]:
        return algorithm5.search_catalog(self.catalog, query, 20)

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

    def test_validated_family_head_uses_compacted_visible_letters(self) -> None:
        response = self.search("A BAA G LAR")

        self.assertTrue(response["results"][0]["name"].startswith("ABASAGLAR"))
        self.assertIn("variant_head_edit", response["results"][0]["reasons"])

    def test_low_confidence_decoy_does_not_disable_closer_family_head(self) -> None:
        response = self.search("LANFUS")

        self.assertTrue(response["results"][0]["name"].startswith("LANTUS"))
        self.assertIn("variant_head_edit", response["results"][0]["reasons"])

    def test_short_visible_prefix_surfaces_catalog_family_heads(self) -> None:
        response = self.search("LAN")
        lantus = [
            row for row in response["results"]
            if row["name"].startswith("LANTUS")
        ]

        self.assertTrue(lantus)
        self.assertTrue(lantus[0]["needs_clarification"])
        self.assertIn("short_visible_head_shortlist", lantus[0]["reasons"])

    def test_short_ordered_fragment_surfaces_catalog_family_head(self) -> None:
        response = self.search("LANS")
        lantus = [
            row for row in response["results"]
            if row["name"].startswith("LANTUS")
        ]

        self.assertTrue(lantus)
        self.assertTrue(lantus[0]["needs_clarification"])

    def test_iv_visual_ligature_is_directional_evidence(self) -> None:
        self.assertIn(
            "LANTUS",
            algorithm5.single_ligature_variants("LAIVTUS"),
        )
        self.assertNotIn(
            "LAIVTUS",
            algorithm5.single_ligature_variants("LANTUS"),
        )
        response = self.search("LAIVTUS")
        self.assertTrue(
            any(
                row["name"].startswith("LANTUS")
                for row in response["results"]
            )
        )

    def test_decisive_family_head_can_override_a_weaker_chain(self) -> None:
        cases = [
            ("LANUS", "LANTUS"),
            ("ABRASAGLAR", "ABASAGLAR"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertTrue(response["results"][0]["name"].startswith(expected))
                self.assertIn(
                    "validated_family_head_correction",
                    response["results"][0]["reasons"],
                )

    def test_unique_closer_returned_family_head_uses_bounded_evidence(self) -> None:
        cases = [
            ("ALBA SAGL ATZ", "ABASAGLAR"),
            ("ANNIKAAIN", "AMIKACIN"),
            ("NIGROHEX", "VIGOREX"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                top = response["results"][0]
                self.assertTrue(top["name"].startswith(expected))
                self.assertIn(
                    "bounded_closer_family_head_correction",
                    top["reasons"],
                )

    def test_family_head_rule_preserves_a_close_complete_name(self) -> None:
        response = self.search("bobiasportwaterresistantsunscreen")

        self.assertEqual(
            response["results"][0]["name"],
            "BOBAI SPORT WATER RESISTANT SUNSCREEN",
        )
        self.assertNotIn(
            "bounded_closer_family_head_correction",
            response["results"][0]["reasons"],
        )

    def test_pareto_character_evidence_promotes_one_dominant_candidate(self) -> None:
        cases = [
            ("KEFONOLAE", "KETOROLAC"),
            ("RIVOFN2", "RIVOTRIL"),
            ("RIVOFOLOL", "RIVOTRIL"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertTrue(response["results"][0]["name"].startswith(expected))
                self.assertIn(
                    "pareto_character_evidence_correction",
                    response["results"][0]["reasons"],
                )

    def test_pareto_character_evidence_preserves_corrected_family_head(self) -> None:
        for query in ("ABDUSONG LAR", "ABACAVIR LAR"):
            with self.subTest(query=query):
                response = self.search(query)
                top = response["results"][0]
                self.assertTrue(top["name"].startswith("ABASAGLAR"))
                self.assertNotIn(
                    "pareto_character_evidence_correction",
                    top["reasons"],
                )

    def test_ordered_character_head_retrieval_surfaces_missing_family(self) -> None:
        for query in ("ABDUSONG LAR", "ABACAVIR LAR", "ABDSOGOG LAY"):
            with self.subTest(query=query):
                response = self.search(query)
                matches = [
                    row
                    for row in response["results"]
                    if row["name"].startswith("ABASAGLAR")
                ]
                self.assertEqual(len(matches), 1)
                self.assertIn(
                    "ordered_character_head_retrieval",
                    matches[0]["reasons"],
                )
                self.assertTrue(matches[0]["needs_clarification"])

    def test_equal_distance_uses_two_sided_visible_anchors(self) -> None:
        cases = [
            ("CEFAXIME", "CEFIXIME"),
            ("LAMIX", "LASIX"),
            ("CLARANE", "CLEXANE"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "two_sided_anchor_tie_correction",
                    response["results"][0]["reasons"],
                )

    def test_two_edit_anchor_tie_requires_better_weighted_evidence(self) -> None:
        cases = [
            ("KETONOLAE", "KETOROLAC"),
            ("OSMOCALM", "OSTOCAL"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)

    def test_dual_supported_strictly_closer_candidate_can_move_first(self) -> None:
        top = algorithm5.Candidate(
            key="ALPHA",
            name="ALPHA",
            commercial_name="ALPHA",
            external_rank=1,
            rescue_rank=1,
            score=1.0,
            raw_edit_distance=2,
        )
        closer = algorithm5.Candidate(
            key="BETA",
            name="BETA",
            commercial_name="BETA",
            external_rank=3,
            rescue_rank=2,
            score=0.9,
            raw_edit_distance=1,
        )
        ranked = algorithm5.rank_candidates([top, closer], "QUERY", brand_like=True)
        self.assertIs(ranked[0], closer)

    def test_equal_distance_candidates_keep_the_model_order(self) -> None:
        top = algorithm5.Candidate(
            key="ALPHA",
            name="ALPHA",
            commercial_name="ALPHA",
            external_rank=1,
            rescue_rank=1,
            score=1.0,
            raw_edit_distance=1,
        )
        equal = algorithm5.Candidate(
            key="BETA",
            name="BETA",
            commercial_name="BETA",
            external_rank=2,
            rescue_rank=2,
            score=0.9,
            raw_edit_distance=1,
        )
        ranked = algorithm5.rank_candidates([top, equal], "QUERY", brand_like=True)
        self.assertIs(ranked[0], top)

    def test_visual_ocr_evidence_breaks_an_equal_distance_tie(self) -> None:
        top = algorithm5.Candidate(
            key="SIENTA",
            name="SIENTA",
            commercial_name="SIENTA",
            score=1.210048,
            raw_edit_distance=2,
            weighted_edit_distance=1.70,
            ocr_visual_edit_distance=1.70,
            ocr_visual_gain=0.0,
        )
        visual_match = algorithm5.Candidate(
            key="OIANDA",
            name="OIANDA",
            commercial_name="OIANDA",
            score=1.194095,
            raw_edit_distance=2,
            weighted_edit_distance=1.45,
            ocr_visual_edit_distance=0.90,
            ocr_visual_gain=0.55,
        )

        ranked = algorithm5.rank_candidates(
            [top, visual_match],
            "0IANTA",
            brand_like=True,
        )

        self.assertIs(ranked[0], visual_match)
        self.assertIn("ocr_visual_tie_correction", visual_match.reasons)

    def test_equal_visual_evidence_does_not_reorder_a_tie(self) -> None:
        top = algorithm5.Candidate(
            key="SIGMAGREL",
            name="SIGMAGREL",
            commercial_name="SIGMAGREL",
            score=1.0,
            raw_edit_distance=2,
            ocr_visual_edit_distance=1.45,
            ocr_visual_gain=0.55,
        )
        equal_visual = algorithm5.Candidate(
            key="SIGAGREL",
            name="SIGAGREL",
            commercial_name="SIGAGREL",
            score=0.95,
            raw_edit_distance=2,
            ocr_visual_edit_distance=1.45,
            ocr_visual_gain=0.55,
        )

        ranked = algorithm5.rank_candidates(
            [top, equal_visual],
            "5IGMGREL",
            brand_like=True,
        )

        self.assertIs(ranked[0], top)

    def test_visual_ocr_tie_correction_respects_the_score_gap(self) -> None:
        top = algorithm5.Candidate(
            key="SIENTA",
            name="SIENTA",
            commercial_name="SIENTA",
            score=1.20,
            raw_edit_distance=2,
            ocr_visual_edit_distance=1.70,
        )
        visual_match = algorithm5.Candidate(
            key="OIANDA",
            name="OIANDA",
            commercial_name="OIANDA",
            score=0.90,
            raw_edit_distance=2,
            ocr_visual_edit_distance=0.90,
            ocr_visual_gain=0.55,
        )

        ranked = algorithm5.rank_candidates(
            [top, visual_match],
            "0IANTA",
            brand_like=True,
        )

        self.assertIs(ranked[0], top)

    def test_multiple_digits_do_not_activate_visual_tie_correction(self) -> None:
        top = algorithm5.Candidate(
            key="HYDRO",
            name="HYDRO",
            commercial_name="HYDRO",
            score=1.0,
            raw_edit_distance=3,
            ocr_visual_edit_distance=3.0,
        )
        alternative = algorithm5.Candidate(
            key="HYPOL",
            name="HYPOL",
            commercial_name="HYPOL",
            score=0.95,
            raw_edit_distance=3,
            ocr_visual_edit_distance=2.45,
            ocr_visual_gain=0.55,
        )

        ranked = algorithm5.rank_candidates(
            [top, alternative],
            "HYY05",
            brand_like=True,
        )

        self.assertIs(ranked[0], top)

    def test_mixed_evidence_retrieval_recovers_unique_nearest_families(self) -> None:
        cases = [
            ("vu1l", "VALL", 1),
            ("lfuvr", "FLUVER", 1),
            ("bscteclr", "BACTICLOR", 2),
            ("bwnzinl", "BENZANIL", 2),
            ("carnprant", "CAMPRONT", 1),
            ("clicynane", "DICYNONE", 20),
            ("hsrtefrn", "HARTIFRIN", 1),
            ("rclamints", "ROTAMIND S", 2),
            ("byofariclie", "BIOFRAICHE", 2),
            ("claflaroses", "DALFAROSIS", 1),
            ("clelrtexene", "DELTREXONE", 1),
            ("clepdiyrm", "DEPIDERM", 20),
            ("1osuc", "LOSEC", 1),
            ("2akun", "ZAKAN", 1),
            ("f0rtam", "FORTUM", 1),
        ]
        for query, expected, maximum_rank in cases:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertLessEqual(names.index(expected) + 1, maximum_rank)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_structural_ligature_variants_are_scored_before_truncation(self) -> None:
        cases = [
            ("cldb", "D D B"),
            ("nin", "NIRI"),
            ("rnol", "MOL"),
            ("rrn", "R M"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_short_consonant_phonetic_frames_recover_vowel_heavy_candidates(self) -> None:
        cases = [
            ("qla", "CLA"),
            ("ard", "UR D"),
            ("etolyl", "ATELOL"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_mixed_ligature_transposition_path_recovers_candidates(self) -> None:
        cases = [
            ("aclgaol", "ADAGEL"),
            ("cl3lbo", "D3LAB"),
            ("clafuln", "DAFLON"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_transposition_deletion_frame_recovers_fallback_cases(self) -> None:
        cases = [
            ("anvi", "AVENE"),
            ("altsren", "ALSOTRIN"),
            ("blyrf", "BLEFIR"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_keyboard_deletion_frame_recovers_mixed_cases(self) -> None:
        cases = [
            ("bonin", "GENION"),
            ("brppe", "GRIPPO"),
            ("cpnvintn", "CONVENTIN"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_visual_phonetic_substitution_chain_recovers_exact_families(self) -> None:
        cases = [
            ("bcbci", "REPCI"),
            ("bihof", "RTHOV"),
            ("deutn", "TEVIN"),
            ("tuxfl", "DUXIL"),
            ("cileg", "CITAK"),
            ("femura", "VENERA"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_visual_visual_deletion_chain_recovers_exact_families(self) -> None:
        for query, expected in [("ahnal", "ORANAL"), ("eenx", "EURAX")]:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_short_query_rescue_exposes_vowel_deletion_alternative(self) -> None:
        response = self.search("nutr")
        names = [row["name"] for row in response["results"]]
        self.assertEqual(names[0], "NUTRI")
        self.assertIn("NOTAR", names)
        self.assertTrue(response["results"][0]["needs_clarification"])

    def test_ligature_vowel_chain_recovers_exact_families(self) -> None:
        cases = [
            ("dopim", "CLOPAM"),
            ("htyk", "LITAK"),
            ("uxohp", "AXOLIP"),
            ("liamix", "HEMIX"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_ligature_vowel_transposition_chain_recovers_exact_family(self) -> None:
        cases = [
            ("lyayra", "HAYAR"),
            ("clopregan", "DOPERGIN"),
            ("disoane", "CLIOSONE"),
            ("mudira", "MUCLEAR"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_transposition_vowel_deletion_chain_recovers_exact_family(self) -> None:
        cases = [
            ("epyr", "ELPRO"),
            ("betirc", "BETACOR"),
            ("valtco", "VALCYTE"),
            ("ropil", "ORA PAL"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_transposition_deletion_exact_chain_recovers_family(self) -> None:
        response = self.search("epro")
        names = [row["name"] for row in response["results"]]
        self.assertIn("PEDRO", names)
        self.assertTrue(response["results"][0]["needs_clarification"])

    def test_vowel_phonetic_deletion_chain_recovers_exact_families(self) -> None:
        cases = [("amka", "UMEGA"), ("esdo", "OSTEO"), ("krmi", "GERMA")]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_keyboard_vowel_deletion_exact_chain_recovers_families(self) -> None:
        cases = [
            ("cwnbo", "CRANBY"),
            ("orna", "PRINU"),
            ("clime", "COKAME"),
            ("urast", "E YEAST"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_short_keyboard_exact_reversal_returns_ambiguous_families(self) -> None:
        cases = [("bew", "NEW"), ("six", "AIX"), ("taz", "YAZ"), ("yda", "TDA")]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_unique_nearest_rerank_uses_large_distance_advantage(self) -> None:
        cases = [
            ("bew", "NEW"),
            ("cligoraisa", "DIGORAISE"),
            ("tiaclohairconditioner", "TIA DO HAIR CONDITIONER"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_weighted_edge_tie_rerank_requires_large_confusion_advantage(self) -> None:
        cases = [
            ("hurnara", "HUMIRA"),
            ("viruat", "VIREAD"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_exact_key_pareto_tie_rerank_requires_no_weaker_signal(self) -> None:
        cases = [
            ("carved", "CARVID"),
            ("dermzo", "DERMOSO"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_visual_distance_tie_rerank_uses_large_ocr_advantage(self) -> None:
        cases = [
            ("benefo", "BENIVO"),
            ("vana8e", "VONABE"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_skeleton_position_tie_rerank_requires_unique_exact_key(self) -> None:
        cases = [
            ("epoxyl", "APIXOL"),
            ("neacef", "NEOCEF"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_ligature_vowel_transpose_rerank_uses_exact_chain_evidence(self) -> None:
        cases = [
            ("icitrnar", "ACTIMAR"),
            ("byofariclie", "BIOFRAICHE"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_ligature_vowel_rerank_requires_unique_nonfarther_candidate(self) -> None:
        cases = [
            ("apihpix", "APILIPEX"),
            ("uctifecl", "ACTIFED"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_visual_phonetic_chain_rerank_requires_dual_retrieval(self) -> None:
        cases = [
            ("eyaztina", "AGASTINA"),
            ("lcrdymox", "FORTYMOX"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_visual_phonetic_exact_key_extension_requires_raw_tie(self) -> None:
        for query, expected in [("nalevin", "NALUFIN"), ("ezomipe", "AZEMIBE")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "visual_phonetic_exact_key_extension_correction",
                    response["results"][0]["reasons"],
                )

    def test_visual_phonetic_dual_extension_requires_two_retrievers(self) -> None:
        for query, expected in [("candiswab", "CARTISWAB"), ("ahiqtam", "UNICTAM")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "visual_phonetic_dual_extension_correction",
                    response["results"][0]["reasons"],
                )

    def test_keyboard_vowel_delete_rerank_releases_exact_key_winner(self) -> None:
        cases = [
            ("cacort", "ACUCORT"),
            ("avrzirg", "AVRISURG"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_keyboard_exact_key_rerank_accepts_small_score_gap(self) -> None:
        for query, expected in [("bluzd", "BLOSED"), ("serl", "SORAL")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_ligature_vowel_transpose_extension_is_chain_specific(self) -> None:
        for query, expected in [("luipanthen", "HIPANTHEN"), ("rnitxone", "MIXTANE")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_ligature_vowel_distance_extension_keeps_tight_gap(self) -> None:
        for query, expected in [("hexaxorn", "HEXAXIM"), ("sertrahno", "SERTRALINE")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_ligature_vowel_edge_extension_preserves_edge_evidence(self) -> None:
        for query, expected in [("freshrnu", "FRESHME"), ("matima", "MATERNA")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "ligature_vowel_edge_extension_correction",
                    response["results"][0]["reasons"],
                )

    def test_ligature_vowel_multi_chain_cases_keep_exact_chain_evidence(self) -> None:
        cases = [
            ("meddiud", "MEDCLOUD", "ligature_vowel_chain_retrieval"),
            ("teme", "TERNA", "ligature_vowel_multi_chain_extension_correction"),
        ]
        for query, expected, expected_reason in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    expected_reason,
                    response["results"][0]["reasons"],
                )

    def test_visual_visual_delete_rerank_preserves_position_evidence(self) -> None:
        cases = [
            ("ontlfu", "ANTIFLU"),
            ("fclo", "FALCO"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_visual_visual_delete_rerank_does_not_override_stronger_chain(self) -> None:
        response = self.search("sanelcox")
        self.assertEqual(response["results"][0]["name"], "SANIDOX")
        self.assertIn(
            "ligature_vowel_transposition_chain_correction",
            response["results"][0]["reasons"],
        )

    def test_visual_multi_chain_rerank_requires_three_independent_chains(self) -> None:
        for query, expected in [("obrto", "ABERTO"), ("omeg", "OMEGY")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "visual_multi_chain_correction",
                    response["results"][0]["reasons"],
                )

    def test_transposition_delete_rerank_uses_exact_key_support(self) -> None:
        for query, expected in [("amrcl", "MARCAL"), ("ivacn", "IVYCAN")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_contained_nearest_rerank_prefers_unique_one_edit_family(self) -> None:
        for query, expected in [("gyt", "GIT"), ("pri", "PRO")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_preserved_top_nearest_rerank_requires_large_weighted_gain(self) -> None:
        for query, expected in [("bwnzinl", "BENZANIL"), ("nta", "NAT")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "preserved_top_dominant_nearest_correction",
                    response["results"][0]["reasons"],
                )

    def test_preserved_top_releases_higher_score_unique_nearest(self) -> None:
        for query, expected in [("ekaus", "OKAYS"), ("rclamints", "ROTAMIND S")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "preserved_top_higher_score_nearest_correction",
                    response["results"][0]["reasons"],
                )
        self.assertEqual(self.search("rma")["results"][0]["name"], "GERMA")
        self.assertEqual(self.search("vrnade")["results"][0]["name"], "VIXADEP")

    def test_exact_ligature_nearest_cases_keep_direct_retrieval_evidence(self) -> None:
        for query, expected in [("cloxydox", "DOXYDOX"), ("vencloty", "VENDOTY")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "bounded_grapheme_confusion_retrieval",
                    response["results"][0]["reasons"],
                )

    def test_exact_ligature_rank_extension_stays_inside_top_five(self) -> None:
        cases = [
            ("clapsone", "DAPSONE", "bounded_grapheme_confusion_retrieval"),
            ("dearair", "CLEAR AIR", "bounded_grapheme_confusion_retrieval"),
            ("rnapi", "MAPI", "exact_ligature_rank_extension_correction"),
            ("hpicontrol", "LIPICONTROL", "exact_ligature_rank_extension_correction"),
        ]
        for query, expected, expected_reason in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    expected_reason,
                    response["results"][0]["reasons"],
                )
        for query, expected in [("clazol", "CALAZOL"), ("lomox", "LOMEX"), ("panal", "PABAL")]:
            with self.subTest(query=query):
                self.assertEqual(self.search(query)["results"][0]["name"], expected)

    def test_exact_phonetic_rewrite_uses_the_complete_rule_family(self) -> None:
        for query, expected in [
            ("alphadep", "ALFADEP"),
            ("aloksi", "ALOXI"),
            ("kwatro", "QUATRO"),
            ("fli", "FLY"),
        ]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                if query != "fli":
                    self.assertIn(
                        "exact_phonetic_rewrite_correction",
                        response["results"][0]["reasons"],
                    )

    def test_weighted_edge_advantage_breaks_bounded_raw_tie(self) -> None:
        for query, expected in [("fcnsy", "FERZY"), ("ptnavavi", "PIRAFAVI")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_weighted_exact_key_tie_does_not_override_shorter_top(self) -> None:
        for query, expected in [("multidreat", "MULTI TREAT"), ("octas", "ACTOS")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "weighted_exact_key_tie_correction",
                    response["results"][0]["reasons"],
                )
        ambiguous = self.search("rofal")
        self.assertEqual(ambiguous["results"][0]["name"], "ROFA")
        self.assertTrue(ambiguous["results"][0]["needs_clarification"])

    def test_exact_transposition_tie_undoes_one_adjacent_swap(self) -> None:
        for query, expected in [("notron", "NORTON"), ("cativate", "ACTIVATE")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "exact_transposition_tie_correction",
                    response["results"][0]["reasons"],
                )

    def test_exact_transposition_dual_extension_requires_both_retrievers(self) -> None:
        for query, expected in [("kats", "KAST"), ("firt", "FRIT"), ("aleska", "ALEKSA")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "exact_transposition_dual_extension_correction",
                    response["results"][0]["reasons"],
                )
        self.assertEqual(self.search("rio")["results"][0]["name"], "RIVO")

    def test_exact_keyboard_tie_requires_independent_key_evidence(self) -> None:
        for query, expected in [("itrocare", "UTROCARE"), ("seleni", "SELENO")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "exact_keyboard_key_tie_correction",
                    response["results"][0]["reasons"],
                )

    def test_exact_keyboard_weighted_extension_requires_both_signals(self) -> None:
        for query, expected in [("ferronz", "FERRO N S"), ("tabune", "TABINE")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "exact_keyboard_weighted_extension_correction",
                    response["results"][0]["reasons"],
                )

    def test_exact_visual_tie_requires_stronger_edge_evidence(self) -> None:
        for query, expected in [("ard", "UR D"), ("pexe", "PEXO")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "exact_visual_edge_tie_correction",
                    response["results"][0]["reasons"],
                )
        preserved = self.search("cativate")
        self.assertEqual(preserved["results"][0]["name"], "ACTIVATE")
        self.assertIn(
            "exact_transposition_tie_correction",
            preserved["results"][0]["reasons"],
        )
        self.assertEqual(self.search("nonen")["results"][0]["name"], "NONAN")

    def test_score_dominant_chain_can_release_a_guarded_top(self) -> None:
        for query, expected in [("aqoef", "AQUA V"), ("bdee", "BECLO")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "guarded_top_score_dominant_chain_correction",
                    response["results"][0]["reasons"],
                )

    def test_score_dominant_chain_can_release_the_external_guard(self) -> None:
        for query, expected in [("bontatex", "BOMIADEX"), ("ranzaom", "RAMSOOM")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "score_dominant_chain_release_correction",
                    response["results"][0]["reasons"],
                )

    def test_stutter_prefix_rerank_removes_one_repeated_chunk(self) -> None:
        for query, expected in [
            ("facfactive", "FACTIVE"),
            ("vitvitamine", "VITAMIN E"),
            ("vavano", "VANO"),
            ("carcaro", "CARO"),
        ]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "exact_stutter_prefix_correction",
                    response["results"][0]["reasons"],
                )
        self.assertEqual(self.search("acaccolate")["results"][0]["name"], "ACCOLATE")

    def test_phonetic_position_tie_requires_both_signals(self) -> None:
        for query, expected in [("vidop", "VITOP"), ("entocough", "ENDO COUGH")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_shifted_edge_agreement_uses_external_rank(self) -> None:
        for query, expected in [("liydro", "HYDRO"), ("liulio", "HULIO")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_transpose_vowel_delete_rerank_releases_higher_score_exact_chain(self) -> None:
        for query, expected in [("lacftor", "LACTOFER"), ("inorcn", "UNOCRON")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_vowel_phonetic_delete_rerank_requires_multiple_chains(self) -> None:
        for query, expected in [("mfuy", "MAVEY"), ("opon", "PEPON")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_vowel_phonetic_extension_requires_exact_key_and_two_chains(self) -> None:
        for query, expected in [("zlax", "SALEX"), ("lmaz", "LEMOS")]:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "vowel_phonetic_multi_chain_extension_correction",
                    response["results"][0]["reasons"],
                )

    def test_short_ocr_combination_recovers_exact_families(self) -> None:
        for query, expected in [("2ix", "ZEX"), ("pb5", "BBS")]:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_short_two_deletion_frames_return_catalog_families(self) -> None:
        cases = [
            ("rma", "RONMA"),
            ("qvp", "QV LIP"),
            ("ena", "EMANA"),
            ("mly", "MERLO"),
            ("rjy", "RONJA"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                names = [row["name"] for row in response["results"]]
                self.assertIn(expected, names)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_exact_chain_can_raise_existing_candidate_without_changing_top(self) -> None:
        response = self.search("carcaprl")
        names = [row["name"] for row in response["results"]]
        self.assertEqual(names[0], "CARBATOL")
        self.assertIn("FARCOPRIL", names)
        self.assertTrue(response["results"][0]["needs_clarification"])

    def test_short_query_does_not_use_leading_transposition_expansion(self) -> None:
        self.assertNotIn(
            ("IRO", "leading_transposition_retrieval"),
            algorithm5.evidence_query_variants("RIO"),
        )
        response = self.search("rio")
        self.assertEqual(response["results"][0]["name"], "RIVO")

    def test_evidence_ranking_handles_a_previous_no_match(self) -> None:
        candidate = algorithm5.Candidate(
            key="VALL",
            name="VALL",
            commercial_name="VALL",
            score=0.9,
            raw_edit_distance=2,
            evidence_only_retrieval=True,
        )

        ranked = algorithm5.rank_candidates(
            [candidate],
            "VU1L",
            brand_like=True,
        )

        self.assertEqual(ranked, [candidate])

    def test_equal_visual_explanations_preserve_the_existing_winner(self) -> None:
        cases = [
            ("amriz0ln", "AMRIZOLE N"),
            ("asc0", "ASICO"),
            ("sigm6rel", "SIGMAGREL"),
            ("5igmgrel", "SIGMAGREL"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertTrue(response["results"][0]["needs_clarification"])

    def test_bounded_full_name_correction_does_not_require_dual_retrieval(self) -> None:
        top = algorithm5.Candidate(
            key="MYOLASTAN",
            name="MYOLASTAN",
            commercial_name="MYOLASTAN",
            external_rank=1,
            rescue_rank=1,
            score=1.0,
            raw_edit_distance=3,
            weighted_edit_distance=2.55,
        )
        closer = algorithm5.Candidate(
            key="MYOLAX",
            name="MYOLAX",
            commercial_name="MYOLAX",
            rescue_rank=2,
            score=0.7,
            raw_edit_distance=2,
            weighted_edit_distance=2.0,
        )
        ranked = algorithm5.rank_candidates(
            [top, closer],
            "MYOLANA",
            brand_like=True,
        )
        self.assertIs(ranked[0], closer)
        self.assertIn("strict_full_name_correction", closer.reasons)

    def test_strict_full_name_uses_weighted_and_edge_agreement(self) -> None:
        cases = [
            ("MYOLANA", "MYOLAX"),
            ("NEITROSET", "NEUROCET"),
            ("LGCMU", "LACTO"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                response = self.search(query)
                self.assertEqual(response["results"][0]["name"], expected)
                self.assertIn(
                    "strict_full_name_correction",
                    response["results"][0]["reasons"],
                )

    def test_full_name_correction_preserves_a_closer_validated_family_head(self) -> None:
        family_head = algorithm5.Candidate(
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
        full_name = algorithm5.Candidate(
            key="BETA",
            name="BETA",
            commercial_name="BETA",
            rescue_rank=2,
            score=0.8,
            raw_edit_distance=2,
            weighted_edit_distance=0.8,
        )
        ranked = algorithm5.rank_candidates(
            [family_head, full_name],
            "QUERY",
            brand_like=True,
        )
        self.assertIs(ranked[0], family_head)

    def test_full_name_correction_preserves_combined_phonetic_evidence(self) -> None:
        supported_top = algorithm5.Candidate(
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
        spelling_only = algorithm5.Candidate(
            key="BETA",
            name="BETA",
            commercial_name="BETA",
            rescue_rank=2,
            score=0.7,
            raw_edit_distance=2,
            weighted_edit_distance=2.0,
        )
        ranked = algorithm5.rank_candidates(
            [supported_top, spelling_only],
            "QUERY",
            brand_like=True,
        )
        self.assertIs(ranked[0], supported_top)

    def test_validated_family_head_uses_head_distance(self) -> None:
        top = algorithm5.Candidate(
            key="ALPHA",
            name="ALPHA",
            commercial_name="ALPHA",
            external_rank=1,
            rescue_rank=1,
            score=1.0,
            raw_edit_distance=2,
        )
        family_variant = algorithm5.Candidate(
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
        ranked = algorithm5.rank_candidates([top, family_variant], "QUERY", brand_like=True)
        self.assertIs(ranked[0], family_variant)


if __name__ == "__main__":
    unittest.main()

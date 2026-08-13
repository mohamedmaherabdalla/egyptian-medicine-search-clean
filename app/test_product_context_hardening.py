#!/usr/bin/env python3
"""Adversarial contracts for product-context parsing and reranking.

These tests intentionally describe safety behavior rather than implementation
details.  In particular, incomplete or conflicting product details must never
be turned into an apparently compatible product merely because one candidate
is the least-wrong item in a family.
"""

from __future__ import annotations

import json
import unittest
from decimal import Decimal
from pathlib import Path

from app import product_context_reranker as reranker


def compact(value: object) -> str:
    return "".join(
        character for character in str(value or "").upper() if character.isalnum()
    )


def algorithm_response(*names: str) -> dict:
    return {
        "algorithm": "algorithm_6",
        "status": "ambiguous" if names else "no_match",
        "decision_type": "algorithm_5_order_preserved" if names else "no_match",
        "results": [
            {
                "rank": rank,
                "name": name,
                "variant_group": name,
                "commercial_name": name,
                "raw_edit_distance": 1.0,
                "consensus_levenshtein_similarity": 0.8,
            }
            for rank, name in enumerate(names, 1)
        ],
    }


def build_catalog(records: list[dict]) -> reranker.ProductCatalog:
    return reranker.build_product_catalog(records, {}, compact)


BRUFEN_RECORDS = [
    {
        "n": "BRUFEN 200 MG 30 TABS.",
        "b": "BRUFEN",
        "st": "200MG",
        "f": "oral_solid",
        "r": "oral_solid",
    },
    {
        "n": "BRUFEN 400 MG 30 TABS.",
        "b": "BRUFEN",
        "st": "400MG",
        "f": "oral_solid",
        "r": "oral_solid",
    },
    {
        "n": "BRUFEN 600 MG 10 EFF. GR. IN SACHETS",
        "b": "BRUFEN",
        "st": "600MG",
        "f": "effervescent",
        "r": "effervescent",
    },
    {
        "n": "BRUFEN 600 MG 20 EFF. GR. IN SACHETS",
        "b": "BRUFEN",
        "st": "600MG",
        "f": "effervescent",
        "r": "effervescent",
    },
    {
        "n": "BRUFEN 600 MG 30 TABS.",
        "b": "BRUFEN",
        "st": "600MG",
        "f": "oral_solid",
        "r": "oral_solid",
    },
    {
        "n": "BRUFEN RETARD 800 MG 20 MODIFIED R. F.C.TABS.",
        "b": "BRUFEN",
        "st": "800MG",
        "f": "oral_solid",
        "r": "oral_solid",
    },
]


class ContextParsingHardeningTests(unittest.TestCase):
    def test_bare_number_is_retained_as_context_evidence(self) -> None:
        evidence = reranker.parse_evidence("600")
        self.assertTrue(evidence.present)
        self.assertEqual(evidence.bare_numbers, frozenset({Decimal("600")}))
        self.assertFalse(evidence.strengths)

    def test_number_attached_to_a_brand_token_is_not_bare_context(self) -> None:
        self.assertFalse(reranker.parse_evidence("D3").bare_numbers)
        self.assertFalse(reranker.parse_evidence("A1").bare_numbers)
        self.assertFalse(reranker.parse_evidence("V2").bare_numbers)

    def test_large_number_before_tablet_is_not_forced_to_be_pack_count(self) -> None:
        evidence = reranker.parse_evidence("500 tab")
        self.assertEqual(evidence.forms, frozenset({"tablet"}))
        self.assertEqual(evidence.bare_numbers, frozenset({Decimal("500")}))
        self.assertFalse(evidence.package_counts)
        self.assertFalse(evidence.ambiguous_numbers)

    def test_plausible_count_before_tablet_keeps_both_safe_hypotheses(self) -> None:
        evidence = reranker.parse_evidence("30 tabs")
        self.assertEqual(evidence.forms, frozenset({"tablet"}))
        self.assertEqual(evidence.ambiguous_numbers, frozenset({Decimal("30")}))
        self.assertEqual(evidence.package_counts, frozenset({30}))
        self.assertFalse(evidence.bare_numbers)

    def test_known_form_modifiers_do_not_hide_a_package_count(self) -> None:
        for text in (
            "30 film coated tablets",
            "30 coated tablets",
            "30 FC tablets",
            "30 chewable tablets",
            "30 dispersible tablets",
            "30 softgel capsules",
        ):
            with self.subTest(text=text):
                evidence = reranker.parse_evidence(text)
                self.assertEqual(evidence.package_counts, frozenset({30}))
                self.assertEqual(evidence.ambiguous_numbers, frozenset({Decimal("30")}))
                self.assertFalse(evidence.bare_numbers)

    def test_multipack_and_prefilled_container_counts_are_explicit(self) -> None:
        self.assertEqual(
            reranker.parse_evidence("20*10 film coated tablets").package_counts,
            frozenset({200}),
        )
        self.assertEqual(
            reranker.parse_evidence("2 pref. syringes").package_counts,
            frozenset({2}),
        )
        self.assertEqual(
            reranker.parse_evidence("2 pref. pens").package_counts,
            frozenset({2}),
        )

    def test_unit_dose_phrase_is_package_not_activity_strength(self) -> None:
        evidence = reranker.parse_evidence("250 mcg/2 ml 20 unit doses")
        self.assertEqual(evidence.package_counts, frozenset({20}))
        self.assertNotIn(
            Decimal("20"),
            {item.observed_value for item in evidence.strengths},
        )
        semicolon = reranker.parse_evidence("250 mcg/1 ml; 20 unit")
        self.assertEqual(semicolon.package_counts, frozenset({20}))
        self.assertEqual(len(semicolon.strengths), 1)

    def test_high_risk_catalog_notations_keep_their_exact_meaning(self) -> None:
        self.assertEqual(
            reranker.parse_strengths("100 000 I.U."),
            reranker.parse_strengths("100000 IU"),
        )
        self.assertFalse(reranker.parse_strengths("0 IU vial"))
        self.assertTrue(reranker.parse_evidence("0 IU vial").invalid_numeric)
        self.assertEqual(
            reranker.parse_evidence("30 H.G. CAPS").package_counts,
            frozenset({30}),
        )
        self.assertEqual(
            reranker.parse_evidence("224 caps").package_counts,
            frozenset({224}),
        )
        self.assertIn(
            "extended_release",
            reranker.parse_evidence("30 EXT. REL. F.C. TABS").release_types,
        )
        self.assertIn(
            "sustained_release",
            reranker.parse_evidence("14 S.R. CAPS").release_types,
        )

    def test_shared_denominators_and_structural_ratios_are_preserved(self) -> None:
        conventional = reranker.parse_strengths("2 mg/ml + 5 mg/ml")
        self.assertEqual(reranker.parse_strengths("2mg+5mg/ml"), conventional)
        self.assertEqual(reranker.parse_strengths("2/5 mg/ml"), conventional)
        self.assertEqual(
            reranker.parse_evidence("30/70 100 IU/ml vial").structural_ratios,
            frozenset({"30/70"}),
        )
        self.assertEqual(
            reranker.parse_evidence("1:100000 cartridge").structural_ratios,
            frozenset({"1:100000"}),
        )

    def test_semicolon_strength_fields_separate_later_presentations(self) -> None:
        topical = reranker.parse_evidence("2%; 10G")
        self.assertEqual(len(topical.strengths), 1)
        self.assertEqual(len(topical.presentation_quantities), 1)
        liquid = reranker.parse_evidence("10.8G; 100ML; 100ML")
        self.assertEqual(len(liquid.strengths), 1)
        self.assertEqual(liquid.strengths[0].denominator_value, Decimal("100"))
        self.assertEqual(len(liquid.presentation_quantities), 1)

    def test_strength_and_pack_can_be_inferred_from_two_unitless_numbers(self) -> None:
        evidence = reranker.parse_evidence("500 20 tablets")
        self.assertEqual(evidence.bare_numbers, frozenset({Decimal("500")}))
        self.assertEqual(evidence.ambiguous_numbers, frozenset({Decimal("20")}))
        self.assertEqual(evidence.package_counts, frozenset({20}))

    def test_decimal_before_form_is_never_parsed_from_its_fractional_tail(self) -> None:
        for text, expected in (("1.2 vial", "1.2"), ("0.5 tablet", "0.5")):
            with self.subTest(text=text):
                evidence = reranker.parse_evidence(text)
                self.assertEqual(
                    evidence.bare_numbers,
                    frozenset({Decimal(expected)}),
                )
                self.assertFalse(evidence.package_counts)
                self.assertFalse(evidence.ambiguous_numbers)

    def test_arabic_digits_follow_the_same_unitless_number_rules(self) -> None:
        evidence = reranker.parse_evidence("٦٠٠ قرص")
        self.assertEqual(evidence.bare_numbers, frozenset({Decimal("600")}))
        self.assertEqual(evidence.forms, frozenset({"tablet"}))

    def test_arabic_decimal_and_thousands_separators_are_numeric(self) -> None:
        self.assertEqual(
            reranker.parse_strengths("١٫٥ مجم"),
            reranker.parse_strengths("1.5 mg"),
        )
        self.assertEqual(
            reranker.parse_strengths("٠٫٥ مجم"),
            reranker.parse_strengths("0.5 mg"),
        )
        self.assertEqual(
            reranker.parse_strengths("١٬٠٠٠ مجم"),
            reranker.parse_strengths("1000 mg"),
        )

    def test_unicode_micro_symbols_keep_micro_magnitude(self) -> None:
        for text in ("20 µg", "20 μg"):
            with self.subTest(text=text):
                self.assertEqual(
                    reranker.parse_strengths(text),
                    reranker.parse_strengths("20 mcg"),
                )
        for text in ("100 µl", "100 μl"):
            with self.subTest(text=text):
                self.assertEqual(
                    reranker.parse_strengths(text),
                    reranker.parse_strengths("100 ul"),
                )

    def test_decimal_comma_and_equivalent_mass_units_normalize(self) -> None:
        self.assertEqual(
            reranker.parse_strengths("0,5 g"),
            reranker.parse_strengths("500 mg"),
        )

    def test_leading_zero_decimal_comma_is_not_a_thousands_group(self) -> None:
        self.assertEqual(
            reranker.parse_strengths("0,125 mg"),
            reranker.parse_strengths("0.125 mg"),
        )

    def test_separator_comma_does_not_hide_a_unitless_number(self) -> None:
        evidence = reranker.parse_evidence("600, tablets")
        self.assertEqual(evidence.bare_numbers, frozenset({Decimal("600")}))
        self.assertEqual(evidence.forms, frozenset({"tablet"}))

    def test_combination_strength_keeps_every_component(self) -> None:
        parsed = reranker.parse_strengths("2/500 mg")
        self.assertEqual(len(parsed), 2)
        self.assertEqual(
            {item.value for item in parsed},
            {Decimal("2000"), Decimal("500000")},
        )
        self.assertNotEqual(parsed, reranker.parse_strengths("500 mg"))

    def test_repeated_combination_components_are_not_collapsed(self) -> None:
        parsed = reranker.parse_strengths("125/125 mg")
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0], parsed[1])

    def test_explicit_units_on_every_combination_component_are_preserved(self) -> None:
        same_dimension = reranker.parse_strengths("5 mg/500 mg")
        mixed_dimension = reranker.parse_strengths("70 mg/2800 IU")
        self.assertEqual(len(same_dimension), 2)
        self.assertEqual(
            [(item.kind, item.value) for item in same_dimension],
            [("mass", Decimal("5000")), ("mass", Decimal("500000"))],
        )
        self.assertEqual(len(mixed_dimension), 2)
        self.assertEqual(
            [(item.kind, item.value) for item in mixed_dimension],
            [("mass", Decimal("70000")), ("activity", Decimal("2800"))],
        )

    def test_percent_before_a_label_word_is_still_a_strength(self) -> None:
        self.assertEqual(
            reranker.parse_strengths("1%TOPICAL SPRAY 120 ML")[0],
            reranker.parse_strengths("1% spray")[0],
        )

    def test_dotted_thousands_in_i_u_are_not_read_as_a_decimal_dose(self) -> None:
        # Egyptian catalog labels commonly print 200.000 I.U. for 200,000 IU.
        self.assertEqual(
            reranker.parse_strengths("200.000 I.U."),
            reranker.parse_strengths("200,000 IU"),
        )

    def test_dotted_thousands_before_written_units_is_idempotent(self) -> None:
        for text in ("30.000 UNITS", "30.000 UNIT", "30.000 IU"):
            with self.subTest(text=text):
                normalized = reranker.normalize_context(text)
                self.assertEqual(
                    reranker.normalize_context(normalized),
                    normalized,
                )
                self.assertEqual(
                    reranker.parse_strengths(text),
                    reranker.parse_strengths("30000 IU"),
                )

    def test_leading_zero_decimal_mg_is_not_changed_by_thousands_normalization(self) -> None:
        self.assertEqual(
            reranker.parse_strengths("0.125 mg"),
            reranker.parse_strengths("125 mcg"),
        )
        self.assertNotEqual(
            reranker.parse_strengths("0.125 mg"),
            reranker.parse_strengths("125 mg"),
        )

    def test_leading_dot_decimal_is_not_parsed_from_its_fractional_tail(self) -> None:
        self.assertEqual(
            reranker.parse_strengths(".5 mg tablet"),
            reranker.parse_strengths("0.5 mg tablet"),
        )
        self.assertEqual(
            reranker.parse_strengths("-.5 mg tablet"),
            reranker.parse_strengths("0.5 mg tablet"),
        )
        self.assertFalse(reranker.parse_strengths("1..5 mg tablet"))

    def test_attached_dotted_unit_abbreviations_parse_like_plain_units(self) -> None:
        cases = (
            ("100I.U.", "100 IU"),
            ("500M.G.", "500 MG"),
            ("5M.L.", "5 ML"),
        )
        for dotted, plain in cases:
            with self.subTest(dotted=dotted):
                self.assertEqual(
                    reranker.parse_strengths(dotted),
                    reranker.parse_strengths(plain),
                )

    def test_million_iu_time_and_microlitre_denominators_are_preserved(self) -> None:
        self.assertEqual(
            reranker.parse_strengths("3 M.I.U"),
            reranker.parse_strengths("3000000 IU"),
        )
        self.assertEqual(
            reranker.parse_strengths("30 MIU/0.5 ML"),
            reranker.parse_strengths("30000000 IU/0.5 ML"),
        )
        self.assertNotEqual(
            reranker.parse_strengths("9.5 mg/24 h"),
            reranker.parse_strengths("9.5 mg/48 h"),
        )
        self.assertEqual(
            reranker.parse_strengths("20 mcg/80 mcl"),
            reranker.parse_strengths("20 mcg/80 ul"),
        )

    def test_dotted_i_u_concentration_keeps_implicit_ml_denominator(self) -> None:
        expected = reranker.parse_strengths("200 IU/ML")
        self.assertEqual(reranker.parse_strengths("200I.U./ML"), expected)
        self.assertEqual(reranker.parse_strengths("200 I.U./ML"), expected)

    def test_concentration_denominator_is_part_of_the_signature(self) -> None:
        five_ml = reranker.parse_strengths("156 mg/5 ml")
        ten_ml = reranker.parse_strengths("156 mg/10 ml")
        no_denominator = reranker.parse_strengths("156 mg")
        self.assertNotEqual(five_ml, ten_ml)
        self.assertNotEqual(five_ml, no_denominator)

    def test_presentation_volume_is_not_dose_strength(self) -> None:
        evidence = reranker.parse_evidence("80 ml suspension")
        self.assertFalse(evidence.strengths)
        self.assertEqual(len(evidence.presentation_quantities), 1)
        self.assertEqual(evidence.presentation_quantities[0].kind, "volume")
        self.assertEqual(evidence.presentation_quantities[0].value, Decimal("80"))

    def test_topical_package_weight_is_not_dose_strength(self) -> None:
        evidence = reranker.parse_evidence("50 g cream")
        self.assertFalse(evidence.strengths)
        self.assertEqual(len(evidence.presentation_quantities), 1)
        self.assertEqual(evidence.presentation_quantities[0].kind, "mass")
        self.assertEqual(evidence.presentation_quantities[0].value, Decimal("50000000"))

    def test_strength_and_presentation_volume_remain_separate(self) -> None:
        evidence = reranker.parse_evidence("156 mg/5 ml suspension 80 ml")
        self.assertEqual(len(evidence.strengths), 1)
        self.assertEqual(evidence.strengths[0].value, Decimal("156000"))
        self.assertEqual(evidence.strengths[0].denominator_value, Decimal("5"))
        self.assertEqual(len(evidence.presentation_quantities), 1)
        self.assertEqual(evidence.presentation_quantities[0].value, Decimal("80"))

    def test_explicit_large_pack_word_overrides_the_heuristic_ceiling(self) -> None:
        evidence = reranker.parse_evidence("500 pack")
        self.assertEqual(evidence.package_counts, frozenset({500}))
        self.assertFalse(evidence.bare_numbers)

    def test_every_explicit_package_word_is_supported(self) -> None:
        for word in (
            "pack",
            "packs",
            "packet",
            "packets",
            "box",
            "boxes",
            "bottle",
            "bottles",
            "piece",
            "pieces",
            "pcs",
            "pen",
            "pens",
        ):
            with self.subTest(word=word):
                evidence = reranker.parse_evidence(f"24 {word}")
                self.assertEqual(evidence.package_counts, frozenset({24}))
                self.assertFalse(evidence.bare_numbers)

    def test_common_form_aliases_are_recognized(self) -> None:
        cases = {
            "caplet": "tablet",
            "eff": "effervescent",
            "effervescent": "effervescent",
            "granules": "granules",
            "solution": "solution",
            "ovules": "ovule",
            "patch": "patch",
            "inhaler": "inhalation",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertIn(expected, reranker.parse_evidence(text).forms)

    def test_written_out_release_aliases_are_recognized(self) -> None:
        cases = {
            "extended release": "extended_release",
            "sustained release": "sustained_release",
            "controlled release": "controlled_release",
            "modified release": "modified_release",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertIn(expected, reranker.parse_evidence(text).release_types)

    def test_alias_context_suffix_must_be_fully_recognized(self) -> None:
        for text in (
            "600 tab",
            "500 mg 20 tablets",
            "1.2 g vial",
            "156 mg/5 ml suspension",
            "500 mg extended release tablet",
        ):
            with self.subTest(valid=text):
                self.assertTrue(reranker.context_suffix_is_fully_recognized(text))
        for text in (
            "junk 20 tab",
            "600 tab unknown",
            "mystery 500 mg",
            "بانادول 20 tab",
            "دواء مجهول 20 tab",
        ):
            with self.subTest(invalid=text):
                self.assertFalse(reranker.context_suffix_is_fully_recognized(text))


class ProductCompatibilityHardeningTests(unittest.TestCase):
    def test_equivalent_scaled_concentrations_match_exactly(self) -> None:
        for query_text, product_strength in (
            ("20 mg/ml", "100MG/5ML"),
            ("1 mg/ml", "5MG/5ML"),
        ):
            with self.subTest(query=query_text, product=product_strength):
                score = reranker.score_product(
                    reranker.parse_evidence(query_text),
                    {
                        "n": f"TEST {product_strength}",
                        "b": "TEST",
                        "st": product_strength,
                        "f": "oral_liquid",
                        "r": "oral_liquid",
                    },
                )
                self.assertTrue(score.compatible)
                self.assertFalse(score.exact_strength_signature)
                self.assertIn("strength_concentration_equivalent", score.matches)

    def test_exact_concentration_total_beats_same_reduced_ratio(self) -> None:
        records = [
            {
                "id": "D2-00035",
                "n": "ABEVMY 100MG/4ML CONC. VIAL FOR I.V. INF.",
                "b": "ABEVMY",
                "st": "100MG/4ML",
                "f": "injection",
                "r": "injection",
            },
            {
                "id": "D2-00036",
                "n": "ABEVMY 400MG/16ML CONC. VIAL FOR I.V. INF.",
                "b": "ABEVMY",
                "st": "400MG/16ML",
                "f": "injection",
                "r": "injection",
            },
        ]
        for context, expected in (
            ("100 mg/4 ml iv vial", "D2-00035"),
            ("400 mg/16 ml iv vial", "D2-00036"),
        ):
            with self.subTest(context=context):
                output = reranker.rerank_products(
                    algorithm_response("ABEVMY"),
                    context,
                    build_catalog(records),
                    limit=1,
                    name_query="abevmy",
                )
                self.assertEqual(output["results"][0]["selected_product_id"], expected)
                self.assertIn("strength_exact", output["results"][0]["matched_context"])

    def test_different_concentration_denominator_is_hard_incompatibility(self) -> None:
        query = reranker.parse_evidence("156 mg/10 ml suspension")
        product = {
            "n": "TEST 156 MG/5 ML SUSPENSION 80 ML",
            "b": "TEST",
            "st": "156MG/5ML; 80ML",
            "f": "oral_liquid",
            "r": "oral_liquid",
        }
        score = reranker.score_product(query, product)
        self.assertFalse(score.compatible)
        self.assertFalse(score.exact_strength_signature)
        self.assertIn("strength_conflict", score.conflicts)
        self.assertNotIn("strength_exact", score.matches)

    def test_omitted_concentration_denominator_is_partial_never_exact(self) -> None:
        query = reranker.parse_evidence("156 mg suspension")
        product = {
            "n": "TEST 156 MG/5 ML SUSPENSION 80 ML",
            "b": "TEST",
            "st": "156MG/5ML; 80ML",
            "f": "oral_liquid",
            "r": "oral_liquid",
        }
        score = reranker.score_product(query, product)
        self.assertTrue(score.compatible)
        self.assertFalse(score.exact_strength_signature)
        self.assertIn("strength_numerator_only", score.matches)
        self.assertIn("strength_signature_incomplete", score.conflicts)
        self.assertNotIn("strength_exact", score.matches)

    def test_full_combination_matches_but_different_component_does_not(self) -> None:
        product = {
            "n": "COMBO 2/500 MG 30 F.C.TABS.",
            "b": "COMBO",
            "st": "500MG",
            "f": "oral_solid",
            "r": "oral_solid",
        }
        exact = reranker.score_product(
            reranker.parse_evidence("2/500 mg tablet"), product
        )
        wrong = reranker.score_product(
            reranker.parse_evidence("5/500 mg tablet"), product
        )
        self.assertTrue(exact.compatible)
        self.assertTrue(exact.exact_strength_signature)
        self.assertIn("strength_exact", exact.matches)
        self.assertFalse(wrong.compatible)
        self.assertIn("strength_conflict", wrong.conflicts)

    def test_wrong_unit_scale_does_not_match_same_visible_number(self) -> None:
        product = {
            "n": "TEST 500 MG 20 TABS.",
            "b": "TEST",
            "st": "500MG",
            "f": "oral_solid",
            "r": "oral_solid",
        }
        wrong = reranker.score_product(
            reranker.parse_evidence("500 mcg tablet"), product
        )
        equivalent = reranker.score_product(
            reranker.parse_evidence("0.5 g tablet"), product
        )
        self.assertFalse(wrong.compatible)
        self.assertIn("strength_conflict", wrong.conflicts)
        self.assertTrue(equivalent.compatible)
        self.assertTrue(equivalent.exact_strength_signature)

    def test_tablet_and_capsule_are_hard_form_conflicts(self) -> None:
        product = {
            "n": "TEST 500 MG 20 CAPS.",
            "b": "TEST",
            "st": "500MG",
            "f": "oral_solid",
            "r": "oral_solid",
        }
        score = reranker.score_product(
            reranker.parse_evidence("500 mg tablet"), product
        )
        self.assertFalse(score.compatible)
        self.assertIn("dosage_form_conflict", score.conflicts)

    def test_effervescent_modifier_does_not_match_plain_tablet(self) -> None:
        product = {
            "n": "TEST 500 MG 20 TABS.",
            "b": "TEST",
            "st": "500MG",
            "f": "oral_solid",
            "r": "oral_solid",
        }
        score = reranker.score_product(
            reranker.parse_evidence("500 mg effervescent tablet"), product
        )
        self.assertFalse(score.compatible)
        self.assertIn("dosage_form_conflict", score.conflicts)

    def test_effervescent_tablet_does_not_match_effervescent_sachet(self) -> None:
        product = {
            "n": "TEST 500 MG 20 EFF. GR. IN SACHETS",
            "b": "TEST",
            "st": "500MG",
            "f": "effervescent",
            "r": "effervescent",
        }
        score = reranker.score_product(
            reranker.parse_evidence("500 mg effervescent tablet"), product
        )
        self.assertFalse(score.compatible)
        self.assertIn("dosage_form_conflict", score.conflicts)

    def test_chewable_modifier_does_not_match_plain_tablet(self) -> None:
        product = {
            "n": "TEST 500 MG 20 TABS.",
            "b": "TEST",
            "st": "500MG",
            "f": "oral_solid",
            "r": "oral_solid",
        }
        score = reranker.score_product(
            reranker.parse_evidence("500 mg chewable tablet"), product
        )
        self.assertFalse(score.compatible)
        self.assertIn("dosage_form_conflict", score.conflicts)

    def test_plain_tablet_query_accepts_a_chewable_tablet_subtype(self) -> None:
        product = {
            "n": "TEST 500 MG 20 CHEWABLE TABS.",
            "b": "TEST",
            "st": "500MG",
            "f": "oral_solid",
            "r": "oral_solid",
        }
        score = reranker.score_product(
            reranker.parse_evidence("500 mg tablet"), product
        )
        self.assertTrue(score.compatible)
        self.assertIn("dosage_form_match", score.matches)

    def test_catalog_chew_and_dis_abbreviations_preserve_form_subtypes(self) -> None:
        for record, query, expected_form in (
            (
                {
                    "n": "ACICONE 720 MG 20 CHEW. TAB.",
                    "b": "ACICONE",
                    "st": "720MG",
                    "f": "oral_solid",
                    "r": "oral_solid",
                },
                "720 mg chewable tablet",
                "chewable_tablet",
            ),
            (
                {
                    "n": "ANTIMIGROZAN 2.5MG 6 DIS. TABS.",
                    "b": "ANTIMIGROZAN",
                    "st": "2.5MG",
                    "f": "oral_solid",
                    "r": "oral_solid",
                },
                "2.5 mg dispersible tablet",
                "dispersible_tablet",
            ),
        ):
            with self.subTest(query=query):
                self.assertIn(expected_form, reranker.product_evidence(record).forms)
                score = reranker.score_product(reranker.parse_evidence(query), record)
                self.assertTrue(score.compatible)
                self.assertIn("dosage_form_match", score.matches)

    def test_injection_subtype_exact_match_breaks_iv_im_tie(self) -> None:
        records = [
            {
                "id": "IM",
                "n": "CEFAXONE 1 GM I.M. VIAL",
                "b": "CEFAXONE",
                "st": "1G",
                "f": "injection",
                "r": "injection",
            },
            {
                "id": "IV",
                "n": "CEFAXONE 1 GM I.V. VIAL",
                "b": "CEFAXONE",
                "st": "1G",
                "f": "injection",
                "r": "injection",
            },
        ]
        for route, expected in (("iv", "IV"), ("im", "IM")):
            with self.subTest(route=route):
                output = reranker.rerank_products(
                    algorithm_response("CEFAXONE"),
                    f"1 g {route} vial",
                    build_catalog(records),
                    limit=1,
                    name_query="cefaxone",
                )
                self.assertEqual(output["results"][0]["selected_product_id"], expected)

    def test_injection_container_exact_match_breaks_vial_ampoule_tie(self) -> None:
        records = [
            {
                "id": "AMP",
                "n": "CALCIUM FOLINATE 50MG/5ML 5 AMPS.",
                "b": "CALCIUM FOLINATE",
                "st": "50MG/5ML",
                "f": "injection",
                "r": "injection",
            },
            {
                "id": "VIAL",
                "n": "CALCIUM FOLINATE 50MG/5ML VIAL",
                "b": "CALCIUM FOLINATE",
                "st": "50MG/5ML",
                "f": "injection",
                "r": "injection",
            },
        ]
        output = reranker.rerank_products(
            algorithm_response("CALCIUM FOLINATE"),
            "50 mg/5 ml vial",
            build_catalog(records),
            limit=1,
            name_query="calcium folinate",
        )
        self.assertEqual(output["results"][0]["selected_product_id"], "VIAL")

    def test_unknown_explicit_presentation_or_package_cannot_claim_match(self) -> None:
        record = {
            "n": "ABEVAC 1MG/ML VIAL",
            "b": "ABEVAC",
            "st": "1MG/ML",
            "f": "injection",
            "r": "injection",
        }
        for query, conflict in (
            ("1 mg/ml 999 ml vial", "presentation_quantity_unknown"),
            ("1 mg/ml 999 bottles vial", "package_count_unknown"),
        ):
            with self.subTest(query=query):
                score = reranker.score_product(reranker.parse_evidence(query), record)
                self.assertFalse(score.compatible)
                self.assertIn(conflict, score.conflicts)

    def test_every_explicit_package_constraint_must_match(self) -> None:
        record = {
            "n": "BRUFEN 600 MG 30 TABS.",
            "b": "BRUFEN",
            "st": "600MG",
            "f": "oral_solid",
            "r": "oral_solid",
        }
        score = reranker.score_product(
            reranker.parse_evidence("600 mg 30 tablets 999 bottles"),
            record,
        )
        self.assertFalse(score.compatible)
        self.assertIn("package_count_conflict", score.conflicts)

    def test_explicit_zero_dose_fails_closed_instead_of_becoming_form_only(self) -> None:
        record = {
            "n": "ANGIKINASE 100000 I.U. VIAL",
            "b": "ANGIKINASE",
            "st": "100000 IU",
            "f": "injection",
            "r": "injection",
        }
        score = reranker.score_product(
            reranker.parse_evidence("0 IU vial"), record
        )
        self.assertFalse(score.compatible)
        self.assertIn("invalid_numeric_evidence", score.conflicts)

    def test_shared_denominator_and_ratio_conflicts_are_hard(self) -> None:
        combo = {
            "n": "COMBIGAN 2MG+5MG/ML EYE DROPS",
            "b": "COMBIGAN",
            "st": "2MG+5MG/ML",
            "f": "ophthalmic",
            "r": "ophthalmic",
        }
        exact = reranker.score_product(
            reranker.parse_evidence("2 mg/ml + 5 mg/ml eye drops"), combo
        )
        self.assertTrue(exact.compatible)
        self.assertTrue(exact.exact_strength_signature)

        insulin = {
            "n": "HUMAN INSULIN MIX 30/70 100IU/ML VIAL",
            "b": "HUMAN INSULIN MIX",
            "st": "100IU/ML",
            "f": "injection",
            "r": "injection",
        }
        wrong = reranker.score_product(
            reranker.parse_evidence("70/30 100 IU/ml vial"), insulin
        )
        self.assertFalse(wrong.compatible)
        self.assertIn("structural_ratio_conflict", wrong.conflicts)

    def test_specific_tablet_is_compatible_with_broad_oral_solid_metadata(self) -> None:
        product = {
            "n": "TEST 500 MG",
            "b": "TEST",
            "st": "500MG",
            "f": "oral_solid",
            "r": "oral_solid",
        }
        score = reranker.score_product(
            reranker.parse_evidence("500 mg tablet"), product
        )
        self.assertTrue(score.compatible)
        self.assertIn("dosage_form_compatible", score.matches)

    def test_written_release_phrase_matches_abbreviated_product(self) -> None:
        product = {
            "n": "TEST XR 500 MG 30 TABS.",
            "b": "TEST",
            "st": "500MG",
            "f": "oral_solid",
            "r": "oral_solid",
        }
        score = reranker.score_product(
            reranker.parse_evidence("500 mg extended release tablet"), product
        )
        self.assertTrue(score.compatible)
        self.assertIn("release_type_match", score.matches)

    def test_known_route_and_release_conflicts_are_incompatible(self) -> None:
        injection = {
            "n": "TEST 500 MG XR VIAL FOR I.V. INJECTION",
            "b": "TEST",
            "st": "500MG",
            "f": "injection",
            "r": "injection",
        }
        route_conflict = reranker.score_product(
            reranker.parse_evidence("500 mg oral"), injection
        )
        self.assertFalse(route_conflict.compatible)
        self.assertIn("route_conflict", route_conflict.conflicts)

        route_unknown = reranker.score_product(
            reranker.parse_evidence("500 mg oral"),
            {
                "n": "TEST 500 MG",
                "b": "TEST",
                "st": "500MG",
                "f": "unknown",
                "r": "unknown",
            },
        )
        self.assertFalse(route_unknown.compatible)
        self.assertIn("route_unknown", route_unknown.conflicts)

        immediate_release = {
            "n": "TEST 500 MG 20 TABS.",
            "b": "TEST",
            "st": "500MG",
            "f": "oral_solid",
            "r": "oral_solid",
        }
        release_unknown = reranker.score_product(
            reranker.parse_evidence("500 mg extended release tablet"),
            immediate_release,
        )
        self.assertFalse(release_unknown.compatible)
        self.assertNotIn("release_type_match", release_unknown.matches)
        self.assertIn("release_type_unknown", release_unknown.conflicts)

        different_release = {
            **immediate_release,
            "n": "TEST CR 500 MG 20 TABS.",
        }
        release_conflict = reranker.score_product(
            reranker.parse_evidence("500 mg extended release tablet"),
            different_release,
        )
        self.assertFalse(release_conflict.compatible)
        self.assertIn("release_type_conflict", release_conflict.conflicts)

    def test_topical_weight_matches_presentation_not_strength(self) -> None:
        product = {
            "n": "JAVA CREAM 50 GM",
            "b": "JAVA",
            "st": "50G",
            "f": "topical",
            "r": "topical",
        }
        score = reranker.score_product(
            reranker.parse_evidence("50 g cream"), product
        )
        self.assertTrue(score.compatible)
        self.assertFalse(score.exact_strength_signature)
        self.assertIn("presentation_quantity_match", score.matches)
        self.assertNotIn("strength_exact", score.matches)


class ProductSelectionHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.brufen_catalog = build_catalog(BRUFEN_RECORDS)

    def rerank_brufen(self, context: str) -> dict:
        return reranker.rerank_products(
            algorithm_response("BRUFEN"),
            context,
            self.brufen_catalog,
            limit=20,
            name_query="brufen",
        )

    def test_unitless_600_returns_all_equally_supported_600_products(self) -> None:
        output = self.rerank_brufen("600")
        names = {item["commercial_name"] for item in output["results"]}
        self.assertEqual(
            names,
            {
                "BRUFEN 600 MG 10 EFF. GR. IN SACHETS",
                "BRUFEN 600 MG 20 EFF. GR. IN SACHETS",
                "BRUFEN 600 MG 30 TABS.",
            },
        )
        self.assertTrue(
            all(item["context_match_status"] == "ambiguous_products" for item in output["results"])
        )
        self.assertTrue(all(item["context_tie_count"] == 3 for item in output["results"]))

    def test_exact_numbered_brand_is_not_reinterpreted_without_context_field(self) -> None:
        numbered_catalog = build_catalog(
            [
                {
                    "n": "D3 30 TABS.",
                    "b": "D3",
                    "st": "",
                    "f": "oral_solid",
                    "r": "oral_solid",
                }
            ]
        )
        original = algorithm_response("D3")
        output = reranker.rerank_products(
            original,
            "D3",
            numbered_catalog,
            limit=20,
            name_query="D3",
            explicit_product_context=False,
        )
        self.assertIs(output, original)

    def test_unitless_600_tablet_selects_the_600_mg_tablet(self) -> None:
        output = self.rerank_brufen("600 tab")
        self.assertEqual(len(output["results"]), 1)
        self.assertEqual(output["results"][0]["commercial_name"], "BRUFEN 600 MG 30 TABS.")
        self.assertIn("unitless_strength_match", output["results"][0]["matched_context"])
        self.assertNotIn("unitless_package_match", output["results"][0]["matched_context"])

    def test_30_tablets_returns_strength_variants_as_an_explicit_tie(self) -> None:
        output = self.rerank_brufen("30 tab")
        names = {item["commercial_name"] for item in output["results"]}
        self.assertEqual(
            names,
            {
                "BRUFEN 200 MG 30 TABS.",
                "BRUFEN 400 MG 30 TABS.",
                "BRUFEN 600 MG 30 TABS.",
            },
        )
        self.assertTrue(all(item["context_tie_count"] == 3 for item in output["results"]))

    def test_explicit_600_mg_without_form_keeps_form_variants_tied(self) -> None:
        output = self.rerank_brufen("600 mg")
        self.assertEqual(len(output["results"]), 3)
        self.assertTrue(
            all("strength_exact" in item["matched_context"] for item in output["results"])
        )

    def test_tied_product_output_is_capped_but_discloses_full_tie_count(self) -> None:
        records = [
            {
                "n": f"TIE 600 MG {index + 1} PACK",
                "b": "TIE",
                "st": "600MG",
                "f": "oral_solid",
                "r": "oral_solid",
            }
            for index in range(8)
        ]
        output = reranker.rerank_products(
            algorithm_response("TIE"),
            "600 mg",
            build_catalog(records),
            limit=20,
            name_query="tie",
        )
        self.assertEqual(len(output["results"]), 6)
        self.assertTrue(
            all(item["context_tie_count"] == 8 for item in output["results"])
        )

    def test_tied_products_cannot_hide_another_retrieved_family(self) -> None:
        records = [
            *[
                {
                    "n": f"FIRST 600 MG {index + 1} PACK",
                    "b": "FIRST",
                    "st": "600MG",
                    "f": "oral_solid",
                    "r": "oral_solid",
                }
                for index in range(8)
            ],
            {
                "n": "SECOND 600 MG 20 TABS.",
                "b": "SECOND",
                "st": "600MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        output = reranker.rerank_products(
            algorithm_response("FIRST", "SECOND"),
            "600 mg",
            build_catalog(records),
            limit=3,
            name_query="firse",
        )
        self.assertEqual([item["name"] for item in output["results"][:2]], ["FIRST", "SECOND"])

    def test_all_conflicting_products_do_not_select_the_least_wrong_variant(self) -> None:
        records = [
            {
                "n": "XANAX 0.25 MG 100 TABS.",
                "b": "XANAX",
                "st": "0.25MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
            {
                "n": "XANAX 0.5 MG 100 TABS.",
                "b": "XANAX",
                "st": "0.5MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        original = algorithm_response("XANAX")
        output = reranker.rerank_products(
            original,
            "500 mg tab",
            build_catalog(records),
            limit=20,
            name_query="xanax",
        )
        self.assertEqual(output["decision_type"], "product_context_no_compatible_product")
        self.assertFalse(output["context_family_reranked"])
        self.assertEqual(output["results"][0]["commercial_name"], "XANAX")
        self.assertNotIn("selected_product_key", output["results"][0])

    def test_context_does_not_introduce_an_unretrieved_unrelated_family(self) -> None:
        records = [
            {
                "n": "XANAX 0.5 MG 100 TABS.",
                "b": "XANAX",
                "st": "0.5MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
            {
                "n": "XELODA 500 MG 120 TABS.",
                "b": "XELODA",
                "st": "500MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        output = reranker.rerank_products(
            algorithm_response("XANAX"),
            "500 mg tab",
            build_catalog(records),
            limit=20,
            name_query="xanax",
        )
        self.assertEqual(output["decision_type"], "product_context_no_compatible_product")
        self.assertEqual({item["name"] for item in output["results"]}, {"XANAX"})
        self.assertNotIn("XELODA", {item["name"] for item in output["results"]})

    def test_exact_name_is_a_hard_family_boundary_for_context(self) -> None:
        records = [
            *BRUFEN_RECORDS,
            {
                "n": "PROFINAL 600 MG 20 TABS.",
                "b": "PROFINAL",
                "st": "600MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        output = reranker.rerank_products(
            algorithm_response("BRUFEN", "PROFINAL"),
            "600",
            build_catalog(records),
            limit=20,
            name_query="brufen",
        )
        self.assertEqual(
            {item["commercial_name"] for item in output["results"]},
            {
                "BRUFEN 600 MG 10 EFF. GR. IN SACHETS",
                "BRUFEN 600 MG 20 EFF. GR. IN SACHETS",
                "BRUFEN 600 MG 30 TABS.",
            },
        )
        self.assertNotIn("PROFINAL", {item["name"] for item in output["results"]})

    def test_exact_name_conflict_cannot_jump_to_a_rank_two_strength_match(self) -> None:
        records = [
            {
                "n": "XANAX 0.5 MG 100 TABS.",
                "b": "XANAX",
                "st": "0.5MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
            {
                "n": "XELODA 500 MG 120 TABS.",
                "b": "XELODA",
                "st": "500MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        output = reranker.rerank_products(
            algorithm_response("XANAX", "XELODA"),
            "500 mg tab",
            build_catalog(records),
            limit=20,
            name_query="xanax",
        )
        self.assertEqual(output["decision_type"], "product_context_no_compatible_product")
        self.assertEqual([item["name"] for item in output["results"]], ["XANAX"])

    def test_exact_base_name_does_not_open_a_variant_group_sibling(self) -> None:
        records = [
            {
                "n": "BRUFEN 600 MG 30 TABS.",
                "b": "BRUFEN",
                "st": "600MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
            {
                "n": "BRUFEN COLD 10 MG 20 TABS.",
                "b": "BRUFEN COLD",
                "st": "10MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        catalog = reranker.build_product_catalog(
            records,
            {"BRUFEN": "BRUFEN", "BRUFENCOLD": "BRUFEN"},
            compact,
        )
        output = reranker.rerank_products(
            algorithm_response("BRUFEN"),
            "10 mg tab",
            catalog,
            limit=20,
            name_query="brufen",
        )
        self.assertEqual(output["decision_type"], "product_context_no_compatible_product")
        self.assertEqual([item["name"] for item in output["results"]], ["BRUFEN"])
        self.assertNotIn("selected_product_key", output["results"][0])

    def test_typoed_variant_context_cannot_open_unretrieved_sibling_bases(self) -> None:
        records = [
            {
                "n": "BRUFEN 600 MG 30 TABS.",
                "b": "BRUFEN",
                "st": "600MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
            {
                "n": "BRUFEN FLU 10 F.C.TABS.",
                "b": "BRUFEN FLU",
                "st": "",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        catalog = reranker.build_product_catalog(
            records,
            {"BRUFEN": "BRUFEN", "BRUFENFLU": "BRUFEN"},
            compact,
        )
        response = algorithm_response("BRUFEN FLU")
        response["results"][0]["variant_group"] = "BRUFEN"

        strength = reranker.rerank_products(
            response,
            "600 mg",
            catalog,
            limit=20,
            name_query="brufen fli",
        )
        self.assertEqual(
            strength["decision_type"],
            "product_context_no_compatible_product",
        )
        self.assertEqual([item["name"] for item in strength["results"]], ["BRUFEN FLU"])

        form_only = reranker.rerank_products(
            response,
            "tablet",
            catalog,
            limit=20,
            name_query="brufen fli",
        )
        self.assertEqual({item["name"] for item in form_only["results"]}, {"BRUFEN FLU"})
        self.assertNotIn("BRUFEN", {item["name"] for item in form_only["results"]})

    def test_visual_gap_context_uses_the_exact_matched_base_family(self) -> None:
        records = [
            {
                "n": "BRUFEN 600 MG 30 TABS.",
                "b": "BRUFEN",
                "st": "600MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
            {
                "n": "BRUFEN COLD 10 MG 20 TABS.",
                "b": "BRUFEN COLD",
                "st": "10MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        catalog = reranker.build_product_catalog(
            records,
            {"BRUFEN": "BRUFEN", "BRUFENCOLD": "BRUFEN"},
            compact,
        )
        response = {
            "decision_type": "visual_gap_matches",
            "results": [
                {
                    "rank": 1,
                    "name": "BRUFEN",
                    "variant_group": "BRUFEN",
                    "commercial_name": "BRUFEN COLD",
                    "matched_family_name": "BRUFEN COLD",
                    "matched_family_key": "BRUFENCOLD",
                    "source": "algorithm_6_visual_gap",
                }
            ],
        }
        selected = reranker.rerank_products(
            response,
            "10 mg tab",
            catalog,
            limit=20,
            name_query="BRU...COLD",
        )
        self.assertEqual(
            [item["commercial_name"] for item in selected["results"]],
            ["BRUFEN COLD 10 MG 20 TABS."],
        )
        conflict = reranker.rerank_products(
            response,
            "600 mg tab",
            catalog,
            limit=20,
            name_query="BRU...COLD",
        )
        self.assertEqual(
            conflict["decision_type"],
            "product_context_no_compatible_product",
        )
        self.assertFalse(
            any(
                item.get("selected_product_key") == "BRUFEN600MG30TABS"
                for item in conflict["results"]
            )
        )

    def test_visual_gap_top_three_have_structural_admission_without_name_metrics(self) -> None:
        records = [
            {
                "n": f"{name} {strength} MG 20 TABS.",
                "b": name,
                "st": f"{strength}MG",
                "f": "oral_solid",
                "r": "oral_solid",
            }
            for name, strength in (("FIRST", 10), ("SECOND", 500), ("THIRD", 20))
        ]
        response = {
            "decision_type": "visual_gap_matches",
            "results": [
                {
                    "rank": rank,
                    "name": name,
                    "variant_group": name,
                    "matched_family_name": name,
                    "matched_family_key": compact(name),
                    "source": "algorithm_6_visual_gap",
                }
                for rank, name in enumerate(("FIRST", "SECOND", "THIRD"), 1)
            ],
        }
        output = reranker.rerank_products(
            response,
            "500 mg tab",
            build_catalog(records),
            limit=20,
            name_query="...ECON...",
        )
        self.assertEqual([item["name"] for item in output["results"]], ["SECOND"])

    def test_visual_gap_name_digits_are_not_implicit_product_context(self) -> None:
        original = {
            "decision_type": "visual_gap_matches",
            "results": [
                {
                    "rank": 1,
                    "name": "VIT D3",
                    "variant_group": "VIT D3",
                    "commercial_name": "VIT D3",
                    "matched_family_name": "VIT D3",
                    "matched_family_key": "VITD3",
                    "source": "algorithm_6_visual_gap",
                }
            ],
        }
        output = reranker.rerank_products(
            original,
            "VIT__3",
            build_catalog(
                [
                    {
                        "id": "VISUAL-1",
                        "n": "VIT D3 30 TABS.",
                        "b": "VIT D3",
                        "st": "",
                        "f": "oral_solid",
                        "r": "oral_solid",
                    }
                ]
            ),
            limit=20,
            name_query="VIT__3",
            explicit_product_context=False,
        )
        self.assertIs(output, original)
        self.assertNotIn("product_context", output)

    def test_secondary_candidates_enforce_each_available_name_diagnostic(self) -> None:
        records = [
            {
                "n": "FIRST 10 MG 20 TABS.",
                "b": "FIRST",
                "st": "10MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
            {
                "n": "FAR 500 MG 20 TABS.",
                "b": "FAR",
                "st": "500MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        for diagnostic in ("low_similarity", "high_distance", "both_missing"):
            with self.subTest(diagnostic=diagnostic):
                response = algorithm_response("FIRST", "FAR")
                far = response["results"][1]
                if diagnostic == "low_similarity":
                    far.pop("raw_edit_distance")
                    far["consensus_levenshtein_similarity"] = 0.55
                elif diagnostic == "high_distance":
                    far["raw_edit_distance"] = 3.0
                    far.pop("consensus_levenshtein_similarity")
                else:
                    far.pop("raw_edit_distance")
                    far.pop("consensus_levenshtein_similarity")
                output = reranker.rerank_products(
                    response,
                    "500 mg tab",
                    build_catalog(records),
                    limit=20,
                    name_query="firse",
                )
                self.assertEqual(
                    output["decision_type"],
                    "product_context_no_compatible_product",
                )
                self.assertNotIn("FAR", {item["name"] for item in output["results"]})

    def test_rank_four_strength_match_is_outside_context_admission(self) -> None:
        records = [
            {
                "n": f"{name} {strength} MG 20 TABS.",
                "b": name,
                "st": f"{strength}MG",
                "f": "oral_solid",
                "r": "oral_solid",
            }
            for name, strength in (
                ("FIRST", 10),
                ("SECOND", 20),
                ("THIRD", 30),
                ("FOURTH", 500),
            )
        ]
        response = algorithm_response("FIRST", "SECOND", "THIRD", "FOURTH")
        for index, item in enumerate(response["results"]):
            item["raw_edit_distance"] = 1.0
            item["consensus_levenshtein_similarity"] = 0.8
        output = reranker.rerank_products(
            response,
            "500 mg tab",
            build_catalog(records),
            limit=20,
            name_query="firth",
        )
        self.assertEqual(output["decision_type"], "product_context_no_compatible_product")
        self.assertNotIn("FOURTH", {item["name"] for item in output["results"]})

    def test_unitless_strength_plus_form_can_promote_one_unique_compatible_family(self) -> None:
        records = [
            {
                "n": "FIRST 400 MG 20 TABS.",
                "b": "FIRST",
                "st": "400MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
            {
                "n": "SECOND 600 MG 20 TABS.",
                "b": "SECOND",
                "st": "600MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        output = reranker.rerank_products(
            algorithm_response("FIRST", "SECOND"),
            "600 tab",
            build_catalog(records),
            limit=20,
            name_query="secod",
        )
        self.assertEqual(output["results"][0]["name"], "SECOND")
        self.assertTrue(output["context_family_reranked"])

    def test_unitless_strength_does_not_reorder_when_multiple_families_match(self) -> None:
        records = [
            {
                "n": "FIRST 600 MG 20 TABS.",
                "b": "FIRST",
                "st": "600MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
            {
                "n": "SECOND 600 MG 30 TABS.",
                "b": "SECOND",
                "st": "600MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        output = reranker.rerank_products(
            algorithm_response("FIRST", "SECOND"),
            "600 tab",
            build_catalog(records),
            limit=20,
            name_query="firse",
        )
        self.assertEqual(output["results"][0]["name"], "FIRST")
        self.assertFalse(output["context_family_reranked"])

    def test_numerator_only_concentration_evidence_never_reorders_families(self) -> None:
        records = [
            {
                "n": "FIRST 312 MG/5 ML SUSPENSION 80 ML",
                "b": "FIRST",
                "st": "312MG/5ML; 80ML",
                "f": "oral_liquid",
                "r": "oral_liquid",
            },
            {
                "n": "SECOND 156 MG/5 ML SUSPENSION 80 ML",
                "b": "SECOND",
                "st": "156MG/5ML; 80ML",
                "f": "oral_liquid",
                "r": "oral_liquid",
            },
        ]
        output = reranker.rerank_products(
            algorithm_response("FIRST", "SECOND"),
            "156 mg suspension",
            build_catalog(records),
            limit=20,
            name_query="firse",
        )
        self.assertEqual(output["results"][0]["name"], "FIRST")
        self.assertFalse(output["context_family_reranked"])

    def test_exact_strength_still_corrects_javaki_java_family_order(self) -> None:
        records = [
            {
                "n": "JAVA CREAM 50 GM",
                "b": "JAVA",
                "st": "50G",
                "f": "topical",
                "r": "topical",
            },
            {
                "n": "JAKAVI 5 MG 56 TABS.",
                "b": "JAKAVI",
                "st": "5MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        output = reranker.rerank_products(
            algorithm_response("JAVA", "JAKAVI"),
            "5 mg",
            build_catalog(records),
            limit=20,
            name_query="javaki",
        )
        self.assertEqual(output["results"][0]["name"], "JAKAVI")
        self.assertEqual([item["name"] for item in output["results"]], ["JAKAVI"])
        self.assertEqual(output["results"][0]["name_match_rank"], 2)
        self.assertTrue(output["context_family_reranked"])

    def test_locked_rank_two_exact_presentation_recoveries_beat_name_tie_breaker(self) -> None:
        cases = (
            (
                "leal",
                "100 g",
                ("LED", "LEIL", "LEMAH"),
                (
                    ("LED.G 30 TABS", "LED", "", "oral_solid"),
                    ("LEIL 100GM CREAM", "LEIL", "100G", "topical"),
                    ("LEMAH CREAM 100 GM", "LEMAH", "100G", "topical"),
                ),
                "LEIL",
            ),
            (
                "argatex",
                "50 g",
                ("ARGITEX", "ARGOTEX", "ATLATEX"),
                (
                    ("ARGITEX 500 MG 20 CAPS.", "ARGITEX", "500MG", "oral_solid"),
                    ("ARGOTEX CREAM 50 GM", "ARGOTEX", "50G", "topical"),
                    ("ATLATEX CREAM 50 GM", "ATLATEX", "50G", "topical"),
                ),
                "ARGOTEX",
            ),
        )
        for name_query, context, names, rows, expected in cases:
            with self.subTest(name_query=name_query):
                response = algorithm_response(*names)
                for rank, item in enumerate(response["results"], 1):
                    item["raw_edit_distance"] = 2.0 if rank == 1 else 1.0
                    item["consensus_levenshtein_similarity"] = (
                        0.5 if rank == 1 else 0.75
                    )
                records = [
                    {"n": n, "b": b, "st": st, "f": form, "r": form}
                    for n, b, st, form in rows
                ]
                output = reranker.rerank_products(
                    response,
                    context,
                    build_catalog(records),
                    limit=20,
                    name_query=name_query,
                )
                self.assertEqual(output["results"][0]["name"], expected)
                self.assertEqual(output["results"][0]["name_match_rank"], 2)
                self.assertTrue(output["context_family_reranked"])

    def test_form_only_never_reorders_name_families(self) -> None:
        records = [
            {
                "n": "FIRST 50 G CREAM",
                "b": "FIRST",
                "st": "50G",
                "f": "topical",
                "r": "topical",
            },
            {
                "n": "SECOND 5 MG 20 TABS.",
                "b": "SECOND",
                "st": "5MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        output = reranker.rerank_products(
            algorithm_response("FIRST", "SECOND"),
            "tablet",
            build_catalog(records),
            limit=20,
            name_query="firzt",
        )
        self.assertEqual(output["results"][0]["name"], "FIRST")
        self.assertFalse(output["context_family_reranked"])

    def test_exact_presentation_plus_form_can_reorder_admitted_name_families(self) -> None:
        records = [
            {
                "n": "FIRST CREAM 100 GM",
                "b": "FIRST",
                "st": "100G",
                "f": "topical",
                "r": "topical",
            },
            {
                "n": "SECOND CREAM 50 GM",
                "b": "SECOND",
                "st": "50G",
                "f": "topical",
                "r": "topical",
            },
        ]
        output = reranker.rerank_products(
            algorithm_response("FIRST", "SECOND"),
            "50 g cream",
            build_catalog(records),
            limit=20,
            name_query="firse",
        )
        self.assertEqual(output["results"][0]["name"], "SECOND")
        self.assertTrue(output["context_family_reranked"])

    def test_unit_qualified_presentation_can_reorder_admitted_name_families(self) -> None:
        records = [
            {
                "n": "FIRST CREAM 100 GM",
                "b": "FIRST",
                "st": "100G",
                "f": "topical",
                "r": "topical",
            },
            {
                "n": "SECOND CREAM 50 GM",
                "b": "SECOND",
                "st": "50G",
                "f": "topical",
                "r": "topical",
            },
        ]
        output = reranker.rerank_products(
            algorithm_response("FIRST", "SECOND"),
            "50 g",
            build_catalog(records),
            limit=20,
            name_query="firse",
        )
        self.assertEqual(output["results"][0]["name"], "SECOND")
        self.assertTrue(output["context_family_reranked"])

    def test_bare_presentation_number_without_form_never_reorders_name_families(self) -> None:
        records = [
            {
                "n": "FIRST CREAM 100 GM",
                "b": "FIRST",
                "st": "100G",
                "f": "topical",
                "r": "topical",
            },
            {
                "n": "SECOND CREAM 50 GM",
                "b": "SECOND",
                "st": "50G",
                "f": "topical",
                "r": "topical",
            },
        ]
        output = reranker.rerank_products(
            algorithm_response("FIRST", "SECOND"),
            "50",
            build_catalog(records),
            limit=20,
            name_query="firse",
        )
        self.assertEqual(output["results"][0]["name"], "FIRST")
        self.assertFalse(output["context_family_reranked"])


class ShortPrefixContextTests(unittest.TestCase):
    def test_explicit_pack_and_form_can_filter_a_short_prefix(self) -> None:
        catalog = build_catalog(
            [
                {
                    "n": "XPACK 500 MG 24 TABS.",
                    "b": "XPACK",
                    "st": "500MG",
                    "f": "oral_solid",
                    "r": "oral_solid",
                },
                {
                    "n": "XPACK 500 MG 30 TABS.",
                    "b": "XPACK",
                    "st": "500MG",
                    "f": "oral_solid",
                    "r": "oral_solid",
                },
            ]
        )
        output = reranker.rerank_products(
            algorithm_response(),
            "24 pack tablet",
            catalog,
            limit=20,
            name_query="x",
        )
        self.assertEqual(output["decision_type"], "context_assisted_prefix_candidates")
        self.assertEqual(len(output["results"]), 1)
        self.assertEqual(output["results"][0]["commercial_name"], "XPACK 500 MG 24 TABS.")

    def test_x_plus_500_tablet_returns_bounded_ambiguous_prefix_candidates(self) -> None:
        records = [
            {"n": "XELODA 500 MG 120 TABS.", "b": "XELODA", "st": "500MG", "f": "oral_solid", "r": "oral_solid"},
            {"n": "XEREXOMAIR 500 MG 3 TABS.", "b": "XEREXOMAIR", "st": "500MG", "f": "oral_solid", "r": "oral_solid"},
            {"n": "XEROVIRINC 500 MG 18 TABS.", "b": "XEROVIRINC", "st": "500MG", "f": "oral_solid", "r": "oral_solid"},
            {"n": "XITHRONE 500 MG 3 TABS.", "b": "XITHRONE", "st": "500MG", "f": "oral_solid", "r": "oral_solid"},
            {"n": "XITHRONE 500 MG 5 TABS.", "b": "XITHRONE", "st": "500MG", "f": "oral_solid", "r": "oral_solid"},
            {"n": "XITHRONE 500 MG VIAL", "b": "XITHRONE", "st": "500MG", "f": "injection", "r": "injection"},
            {"n": "ALTERNATE 500 MG 20 TABS.", "b": "ALTERNATE", "st": "500MG", "f": "oral_solid", "r": "oral_solid"},
        ]
        output = reranker.rerank_products(
            algorithm_response(),
            "500 tab",
            build_catalog(records),
            limit=20,
            name_query="x",
        )
        self.assertEqual(output["decision_type"], "context_assisted_prefix_candidates")
        self.assertEqual(output["status"], "ambiguous")
        self.assertEqual(output["candidate_count"], 4)
        self.assertTrue(output["confirmation_required"])
        self.assertEqual(
            {item["name"] for item in output["results"]},
            {"XELODA", "XEREXOMAIR", "XEROVIRINC", "XITHRONE"},
        )
        self.assertTrue(
            all(item["name_match_type"] == "strict_prefix" for item in output["results"])
        )
        self.assertTrue(
            all(item["confidence"] == "low" for item in output["results"])
        )

    def test_two_character_prefix_uses_the_same_strict_boundary(self) -> None:
        records = [
            {"n": "XELODA 500 MG 120 TABS.", "b": "XELODA", "st": "500MG", "f": "oral_solid", "r": "oral_solid"},
            {"n": "XEROVIRINC 500 MG 18 TABS.", "b": "XEROVIRINC", "st": "500MG", "f": "oral_solid", "r": "oral_solid"},
            {"n": "XITHRONE 500 MG 3 TABS.", "b": "XITHRONE", "st": "500MG", "f": "oral_solid", "r": "oral_solid"},
        ]
        output = reranker.rerank_products(
            algorithm_response(),
            "500 tab",
            build_catalog(records),
            limit=20,
            name_query="xe",
        )
        self.assertEqual(output["decision_type"], "context_assisted_prefix_candidates")
        self.assertEqual({item["name"] for item in output["results"]}, {"XELODA", "XEROVIRINC"})

    def test_short_prefix_does_not_open_global_fuzzy_candidates(self) -> None:
        records = [
            {"n": "XELODA 500 MG 120 TABS.", "b": "XELODA", "st": "500MG", "f": "oral_solid", "r": "oral_solid"},
            {"n": "ALTERNATE 500 MG 20 TABS.", "b": "ALTERNATE", "st": "500MG", "f": "oral_solid", "r": "oral_solid"},
        ]
        output = reranker.rerank_products(
            algorithm_response(),
            "500 tab",
            build_catalog(records),
            limit=20,
            name_query="x",
        )
        self.assertEqual(output["candidate_count"], 1)
        self.assertEqual({item["name"] for item in output["results"]}, {"XELODA"})
        self.assertEqual(output["status"], "ambiguous")

    def test_short_prefix_without_both_numeric_and_form_evidence_does_not_rescue(self) -> None:
        records = [
            {"n": "XELODA 500 MG 120 TABS.", "b": "XELODA", "st": "500MG", "f": "oral_solid", "r": "oral_solid"},
        ]
        output = reranker.rerank_products(
            algorithm_response(),
            "500",
            build_catalog(records),
            limit=20,
            name_query="x",
        )
        self.assertEqual(output["decision_type"], "product_context_no_compatible_product")
        self.assertFalse(output["results"])

    def test_too_many_short_prefix_families_abstains(self) -> None:
        records = [
            {
                "n": f"XTEST{index:02d} 500 MG 20 TABS.",
                "b": f"XTEST{index:02d}",
                "st": "500MG",
                "f": "oral_solid",
                "r": "oral_solid",
            }
            for index in range(21)
        ]
        output = reranker.rerank_products(
            algorithm_response(),
            "500 tab",
            build_catalog(records),
            limit=20,
            name_query="x",
        )
        self.assertEqual(output["decision_type"], "context_assisted_prefix_too_broad")
        self.assertEqual(output["candidate_count"], 21)
        self.assertFalse(output["results"])

    def test_short_prefix_counts_folded_base_families_not_variant_groups(self) -> None:
        records = [
            {
                "n": f"XBASE{index} 500 MG 20 TABS.",
                "b": f"XBASE{index}",
                "st": "500MG",
                "f": "oral_solid",
                "r": "oral_solid",
            }
            for index in range(7)
        ]
        catalog = reranker.build_product_catalog(
            records,
            {compact(record["b"]): "XFOLDED" for record in records},
            compact,
        )
        output = reranker.rerank_products(
            algorithm_response(),
            "500 tab",
            catalog,
            limit=20,
            name_query="x",
        )
        self.assertEqual(output["candidate_count"], 7)
        self.assertEqual(
            {item["name"] for item in output["results"]},
            {f"XBASE{index}" for index in range(7)},
        )

    def test_short_visual_gap_query_never_opens_global_prefix_rescue(self) -> None:
        records = [
            {
                "n": "BRAN 5 MG 20 TABS.",
                "b": "BRAN",
                "st": "5MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
            {
                "n": "BRINTELLIX 10 MG 20 TABS.",
                "b": "BRINTELLIX",
                "st": "10MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        visual = {
            "decision_type": "visual_gap_matches",
            "results": [
                {
                    "rank": 1,
                    "name": "BRAN",
                    "variant_group": "BRAN",
                    "matched_family_name": "BRAN",
                    "matched_family_key": "BRAN",
                    "source": "algorithm_6_visual_gap",
                }
            ],
        }
        output = reranker.rerank_products(
            visual,
            "10 mg tab",
            build_catalog(records),
            limit=20,
            name_query="BR...",
        )
        self.assertEqual(
            output["decision_type"],
            "product_context_no_compatible_product",
        )
        self.assertEqual([item["name"] for item in output["results"]], ["BRAN"])
        self.assertNotIn("BRINTELLIX", {item["name"] for item in output["results"]})


class NumericCommercialAliasTests(unittest.TestCase):
    @staticmethod
    def catalog() -> reranker.ProductCatalog:
        return build_catalog(
            [
                {
                    "n": "1 2 3 (ONE TWO THREE) 20 F.C.TABS.",
                    "b": "ONE TWO THREE",
                    "st": "",
                    "f": "oral_solid",
                    "r": "oral_solid",
                },
                {
                    "n": "1 2 3 (ONE TWO THREE) SUSP. 120 ML",
                    "b": "ONE TWO THREE",
                    "st": "120ML",
                    "f": "oral_liquid",
                    "r": "oral_liquid",
                },
                {
                    "n": "1 2 3 (ONE TWO THREE) EXTRA 20 F.C.TABS.",
                    "b": "ONE TWO THREE EXTRA",
                    "st": "",
                    "f": "oral_solid",
                    "r": "oral_solid",
                },
                {
                    "n": "1 2 4 UNRELATED 20 TABS.",
                    "b": "UNRELATED",
                    "st": "",
                    "f": "oral_solid",
                    "r": "oral_solid",
                },
            ]
        )

    def test_exact_multi_number_alias_rescues_only_its_catalog_families(self) -> None:
        output = reranker.rerank_products(
            algorithm_response(),
            "1 2 3",
            self.catalog(),
            limit=20,
            name_query="1 2 3",
            explicit_product_context=False,
        )
        self.assertEqual(output["decision_type"], "numeric_commercial_alias_matches")
        self.assertEqual(output["status"], "ambiguous")
        self.assertEqual(output["candidate_count"], 2)
        self.assertTrue(output["confirmation_required"])
        self.assertEqual(
            {item["name"] for item in output["results"]},
            {"ONE TWO THREE", "ONE TWO THREE EXTRA"},
        )
        self.assertTrue(
            all(item["confirmation_required"] for item in output["results"])
        )

    def test_explicit_context_never_uses_numeric_alias_rescue(self) -> None:
        output = reranker.rerank_products(
            algorithm_response(),
            "20 tab",
            self.catalog(),
            limit=20,
            name_query="1 2 3",
            explicit_product_context=True,
        )
        self.assertEqual(output["decision_type"], "product_context_no_compatible_product")
        self.assertFalse(output["results"])

    def test_nearby_numbers_and_unknown_suffix_do_not_open_numeric_search(self) -> None:
        for query in ("1 2 9", "1 2 3 unknown"):
            with self.subTest(query=query):
                output = reranker.rerank_products(
                    algorithm_response(),
                    query,
                    self.catalog(),
                    limit=20,
                    name_query=query,
                    explicit_product_context=False,
                )
                self.assertEqual(
                    output["decision_type"],
                    "product_context_no_compatible_product",
                )
                self.assertFalse(output["results"])

    def test_trailing_details_filter_products_inside_every_alias_family(self) -> None:
        output = reranker.rerank_products(
            algorithm_response(),
            "1 2 3 20 tab",
            self.catalog(),
            limit=20,
            name_query="1 2 3 20 tab",
            explicit_product_context=False,
        )
        self.assertEqual(
            output["decision_type"],
            "numeric_commercial_alias_product_context_selection",
        )
        self.assertEqual(output["candidate_count"], 2)
        self.assertEqual(
            {item["commercial_name"] for item in output["results"]},
            {
                "1 2 3 (ONE TWO THREE) 20 F.C.TABS.",
                "1 2 3 (ONE TWO THREE) EXTRA 20 F.C.TABS.",
            },
        )
        self.assertTrue(
            all("package_count_match" in item["matched_context"] for item in output["results"])
        )

    def test_conflicting_trailing_details_do_not_select_a_least_wrong_product(self) -> None:
        output = reranker.rerank_products(
            algorithm_response(),
            "1 2 3 10 tab",
            self.catalog(),
            limit=20,
            name_query="1 2 3 10 tab",
            explicit_product_context=False,
        )
        self.assertEqual(
            output["decision_type"],
            "numeric_commercial_alias_no_compatible_product",
        )
        self.assertEqual(output["candidate_count"], 2)
        self.assertEqual(len(output["results"]), 2)
        self.assertTrue(
            all(
                item["context_match_status"] == "no_compatible_product"
                for item in output["results"]
            )
        )

    def test_all_exact_alias_bases_bypass_ordinary_top_three_admission(self) -> None:
        family_names = ("ALPHA", "BETA", "GAMMA", "DELTA")
        records = [
            {
                "n": f"9 8 7 {name} 500 MG 20 TABS.",
                "b": name,
                "st": "500MG",
                "f": "oral_solid",
                "r": "oral_solid",
            }
            for name in family_names
        ]
        catalog = reranker.build_product_catalog(
            records,
            {compact(name): "SHARED" for name in family_names},
            compact,
        )
        output = reranker.rerank_products(
            algorithm_response(),
            "9 8 7 500 mg tab",
            catalog,
            limit=20,
            name_query="9 8 7 500 mg tab",
            explicit_product_context=False,
        )
        self.assertEqual(
            output["decision_type"],
            "numeric_commercial_alias_product_context_selection",
        )
        self.assertEqual(output["candidate_count"], 4)
        self.assertEqual({item["name"] for item in output["results"]}, set(family_names))

    def test_alias_failure_honors_result_limit_but_discloses_full_count(self) -> None:
        records = [
            {
                "n": f"9 8 7 FAMILY {index} 10 MG 20 TABS.",
                "b": f"FAMILY {index}",
                "st": "10MG",
                "f": "oral_solid",
                "r": "oral_solid",
            }
            for index in range(8)
        ]
        output = reranker.rerank_products(
            algorithm_response(),
            "9 8 7 999 mg tab",
            build_catalog(records),
            limit=3,
            name_query="9 8 7 999 mg tab",
            explicit_product_context=False,
        )
        self.assertEqual(
            output["decision_type"],
            "numeric_commercial_alias_no_compatible_product",
        )
        self.assertEqual(output["candidate_count"], 8)
        self.assertEqual(len(output["results"]), 3)

    def test_alias_context_order_uses_product_score_not_alphabetic_position(self) -> None:
        records = [
            {
                "n": "9 8 7 ALPHA 500/10 MG 20 TABS.",
                "b": "ALPHA",
                "st": "500/10MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
            {
                "n": "9 8 7 ZULU 500 MG 20 TABS.",
                "b": "ZULU",
                "st": "500MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        output = reranker.rerank_products(
            algorithm_response(),
            "9 8 7 500 mg tab",
            build_catalog(records),
            limit=1,
            name_query="9 8 7 500 mg tab",
            explicit_product_context=False,
        )
        self.assertEqual(output["candidate_count"], 2)
        self.assertEqual(output["results"][0]["name"], "ZULU")

    def test_longer_numbered_brand_alias_precedes_numeric_only_alias(self) -> None:
        output = reranker.rerank_products(
            algorithm_response(),
            "1 2 3 ONE TWO THREE 20 tab",
            self.catalog(),
            limit=20,
            name_query="1 2 3 ONE TWO THREE 20 tab",
            explicit_product_context=False,
        )
        self.assertEqual(output["decision_type"], "product_context_selection")
        self.assertEqual({item["name"] for item in output["results"]}, {"ONE TWO THREE"})

    def test_mixed_unknown_and_valid_alias_suffix_never_rescues(self) -> None:
        output = reranker.rerank_products(
            algorithm_response(),
            "1 2 3 junk 20 tab",
            self.catalog(),
            limit=20,
            name_query="1 2 3 junk 20 tab",
            explicit_product_context=False,
        )
        self.assertNotIn("alias", output["decision_type"])
        self.assertFalse(output["results"])


class NumericCommercialBrandAliasTests(unittest.TestCase):
    def test_exact_numbered_brand_with_context_uses_its_catalog_base(self) -> None:
        records = [
            {
                "n": "3 FLY 600 MG 20 TABS.",
                "b": "FLY",
                "st": "600MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
            {
                "n": "OTHER 600 MG 20 TABS.",
                "b": "OTHER",
                "st": "600MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        output = reranker.rerank_products(
            algorithm_response("OTHER"),
            "3 FLY 600 tab",
            build_catalog(records),
            limit=20,
            name_query="3 FLY 600 tab",
            explicit_product_context=False,
        )
        self.assertEqual(
            output["decision_type"],
            "product_context_selection",
        )
        self.assertEqual([item["name"] for item in output["results"]], ["FLY"])
        self.assertEqual(
            output["results"][0]["commercial_name"],
            "3 FLY 600 MG 20 TABS.",
        )

    def test_mixed_unknown_numbered_brand_suffix_does_not_rescue(self) -> None:
        records = [
            {
                "n": "3 FLY 600 MG 20 TABS.",
                "b": "FLY",
                "st": "600MG",
                "f": "oral_solid",
                "r": "oral_solid",
            }
        ]
        output = reranker.rerank_products(
            algorithm_response(),
            "3 FLY junk 600 tab",
            build_catalog(records),
            limit=20,
            name_query="3 FLY junk 600 tab",
            explicit_product_context=False,
        )
        self.assertNotIn("alias", output["decision_type"])
        self.assertFalse(output["results"])

    def test_no_context_brand_alias_only_preserves_a_unique_top_name_match(self) -> None:
        records = [
            {
                "n": "3 FLY 600 MG 20 TABS.",
                "b": "FLY",
                "st": "600MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
            {
                "n": "OTHER 10 MG 20 TABS.",
                "b": "OTHER",
                "st": "10MG",
                "f": "oral_solid",
                "r": "oral_solid",
            },
        ]
        original = algorithm_response("OTHER", "FLY")
        output = reranker.rerank_products(
            original,
            "3 FLY",
            build_catalog(records),
            limit=20,
            name_query="3 FLY",
            explicit_product_context=False,
        )
        self.assertEqual(
            output["decision_type"],
            "numeric_commercial_brand_alias_matches",
        )
        self.assertEqual([item["name"] for item in output["results"]], ["FLY"])

    def test_visual_markers_never_dispatch_to_numbered_alias_rescue(self) -> None:
        records = [
            {
                "n": "3 FLY 600 MG 20 TABS.",
                "b": "FLY",
                "st": "600MG",
                "f": "oral_solid",
                "r": "oral_solid",
            }
        ]
        for query in ("3__FLY", "3**FLY", "3…FLY"):
            with self.subTest(query=query):
                visual = {
                    "decision_type": "visual_gap_matches",
                    "results": [
                        {
                            "rank": 1,
                            "name": "FLY",
                            "variant_group": "FLY",
                            "matched_family_name": "FLY",
                            "matched_family_key": "FLY",
                            "source": "algorithm_6_visual_gap",
                        }
                    ],
                }
                output = reranker.rerank_products(
                    visual,
                    query,
                    build_catalog(records),
                    limit=20,
                    name_query=query,
                    explicit_product_context=False,
                )
                self.assertNotIn("alias", output["decision_type"])


class RealCatalogProductContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        catalog_path = Path(__file__).resolve().parent / "data" / "catalog.json"
        records = json.loads(catalog_path.read_text(encoding="utf-8"))["records"]
        cls.catalog = build_catalog(records)

    def test_real_catalog_x_plus_500_tablet_has_four_ambiguous_families(self) -> None:
        output = reranker.rerank_products(
            algorithm_response(),
            "500 tab",
            self.catalog,
            limit=20,
            name_query="x",
        )
        self.assertEqual(output["decision_type"], "context_assisted_prefix_candidates")
        self.assertEqual(output["candidate_count"], 4)
        self.assertEqual(
            {item["name"] for item in output["results"]},
            {"XELODA", "XEREXOMAIR", "XEROVIRINC", "XITHRONE"},
        )
        self.assertEqual(output["status"], "ambiguous")

    def test_real_catalog_brufen_600_tablet_selects_600_mg_tablet(self) -> None:
        output = reranker.rerank_products(
            algorithm_response("BRUFEN"),
            "600 tab",
            self.catalog,
            limit=20,
            name_query="brufen",
        )
        self.assertEqual(len(output["results"]), 1)
        self.assertEqual(output["results"][0]["commercial_name"], "BRUFEN 600 MG 30 TABS.")

    def test_real_catalog_brufen_comma_unitless_tablet_matches_strength(self) -> None:
        output = reranker.rerank_products(
            algorithm_response("BRUFEN"),
            "600, tab",
            self.catalog,
            limit=20,
            name_query="brufen",
        )
        self.assertEqual(
            [item["commercial_name"] for item in output["results"]],
            ["BRUFEN 600 MG 30 TABS."],
        )

    def test_duplicate_normalized_product_names_keep_unique_catalog_ids(self) -> None:
        output = reranker.rerank_products(
            algorithm_response("CITICOLINE"),
            "500 mg cap",
            self.catalog,
            limit=20,
            name_query="citicoline",
        )
        self.assertEqual(len(output["results"]), 2)
        self.assertEqual(
            {item.get("selected_product_id") for item in output["results"]},
            {"D2-04517", "D2-04518"},
        )
        self.assertEqual(
            len({item.get("selected_product_key") for item in output["results"]}),
            1,
        )

    def test_written_pack_modifier_does_not_select_a_same_number_strength(self) -> None:
        catalog = build_catalog(
            [
                {
                    "id": "PACK-30",
                    "n": "TEST 500 MG 30 F.C.TABS.",
                    "b": "TEST",
                    "st": "500MG",
                    "f": "oral_solid",
                    "r": "oral_solid",
                },
                {
                    "id": "DOSE-30",
                    "n": "TEST 30 MG 20 F.C.TABS.",
                    "b": "TEST",
                    "st": "30MG",
                    "f": "oral_solid",
                    "r": "oral_solid",
                },
            ]
        )
        output = reranker.rerank_products(
            algorithm_response("TEST"),
            "30 film coated tablets",
            catalog,
            limit=20,
            name_query="test",
        )
        self.assertEqual(
            [item["selected_product_id"] for item in output["results"]],
            ["PACK-30"],
        )
        self.assertIn("package_count_match", output["results"][0]["matched_context"])

    def test_real_catalog_xanax_500_mg_tablet_abstains(self) -> None:
        output = reranker.rerank_products(
            algorithm_response("XANAX"),
            "500 mg tab",
            self.catalog,
            limit=20,
            name_query="xanax",
        )
        self.assertEqual(output["decision_type"], "product_context_no_compatible_product")
        self.assertEqual(output["results"][0]["commercial_name"], "XANAX")
        self.assertNotIn("selected_product_key", output["results"][0])

    def test_real_catalog_percent_attached_to_label_word_remains_selectable(self) -> None:
        output = reranker.rerank_products(
            algorithm_response("ECONAZOLE"),
            "1% spray",
            self.catalog,
            limit=20,
            name_query="econazole",
        )
        self.assertEqual(output["decision_type"], "product_context_selection")
        self.assertEqual(output["results"][0]["selected_product_id"], "D2-06821")
        self.assertIn("strength_exact", output["results"][0]["matched_context"])

    def test_real_catalog_dotted_units_keep_complete_phesgo_signature(self) -> None:
        output = reranker.rerank_products(
            algorithm_response("PHESGO"),
            "1200 mg/600 mg/30000 units injection",
            self.catalog,
            limit=20,
            name_query="phesgo",
        )
        self.assertEqual([item["selected_product_id"] for item in output["results"]], ["D2-17345"])
        self.assertIn("strength_exact", output["results"][0]["matched_context"])

    def test_real_catalog_dose_count_selects_the_right_inhaler(self) -> None:
        output = reranker.rerank_products(
            algorithm_response("ALVESCO"),
            "160 mcg inhaler 120 doses",
            self.catalog,
            limit=20,
            name_query="alvesco",
        )
        self.assertEqual([item["selected_product_id"] for item in output["results"]], ["D2-00836"])
        self.assertIn("package_count_match", output["results"][0]["matched_context"])

    def test_real_numeric_word_brand_is_not_product_context(self) -> None:
        original = algorithm_response("FLY")
        output = reranker.rerank_products(
            original,
            "3 FLY",
            self.catalog,
            limit=20,
            name_query="3 FLY",
            explicit_product_context=False,
        )
        self.assertIs(output, original)
        self.assertEqual(output["decision_type"], "algorithm_5_order_preserved")
        self.assertNotIn("product_context", output)

    def test_real_numeric_alias_expands_an_incomplete_name_response_safely(self) -> None:
        output = reranker.rerank_products(
            algorithm_response("ONE TWO THREE"),
            "1 2 3",
            self.catalog,
            limit=20,
            name_query="1 2 3",
            explicit_product_context=False,
        )
        self.assertEqual(output["decision_type"], "numeric_commercial_alias_matches")
        self.assertEqual(
            {item["name"] for item in output["results"]},
            {"ONE TWO THREE", "ONE TWO THREE EXTRA"},
        )

    def test_real_numeric_alias_recovers_both_families_from_no_name_results(self) -> None:
        output = reranker.rerank_products(
            algorithm_response(),
            "1 2 3",
            self.catalog,
            limit=20,
            name_query="1 2 3",
            explicit_product_context=False,
        )
        self.assertEqual(output["decision_type"], "numeric_commercial_alias_matches")
        self.assertEqual(
            {item["name"] for item in output["results"]},
            {"ONE TWO THREE", "ONE TWO THREE EXTRA"},
        )

    def test_real_numeric_alias_keeps_trailing_tablet_details(self) -> None:
        output = reranker.rerank_products(
            algorithm_response(),
            "1 2 3 20 tab",
            self.catalog,
            limit=20,
            name_query="1 2 3 20 tab",
            explicit_product_context=False,
        )
        self.assertEqual(
            output["decision_type"],
            "numeric_commercial_alias_product_context_selection",
        )
        self.assertEqual(
            {item["commercial_name"] for item in output["results"]},
            {
                "1 2 3 (ONE TWO THREE) 20 F.C.TABS.",
                "1 2 3 (ONE TWO THREE) EXTRA 20 F.C.TABS.",
            },
        )

    def test_real_numeric_brand_keeps_trailing_combined_product_details(self) -> None:
        output = reranker.rerank_products(
            algorithm_response("FLY"),
            "3 FLY 600 tab",
            self.catalog,
            limit=20,
            name_query="3 FLY 600 tab",
            explicit_product_context=False,
        )
        self.assertEqual(output["decision_type"], "product_context_selection")
        self.assertEqual(len(output["results"]), 1)
        self.assertEqual(output["results"][0]["commercial_name"], "3 FLY 600 MG 20 TABS.")
        self.assertIn("unitless_strength_match", output["results"][0]["matched_context"])


if __name__ == "__main__":
    unittest.main()

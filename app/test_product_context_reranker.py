#!/usr/bin/env python3
"""Focused tests for the post-family product-context reranker."""

from __future__ import annotations

import unittest

from app import product_context_reranker as reranker


def compact(value: object) -> str:
    return "".join(character for character in str(value or "").upper() if character.isalnum())


RECORDS = [
    {"n": "AUGMENTIN 1 GM 14 F.C.TABS.", "b": "AUGMENTIN", "st": "1G", "f": "oral_solid", "r": "oral_solid"},
    {"n": "AUGMENTIN 1.2G VIAL FOR I.V. INJ.", "b": "AUGMENTIN", "st": "1.2G", "f": "injection", "r": "injection"},
    {"n": "AUGMENTIN 156 MG/5 ML SUSP. 80 ML", "b": "AUGMENTIN", "st": "156MG/5ML; 80ML", "f": "oral_liquid", "r": "oral_liquid"},
    {"n": "JAKAVI 5 MG 56 TABS.", "b": "JAKAVI", "st": "5MG", "f": "oral_solid", "r": "oral_solid"},
    {"n": "JAKAVI 15 MG 56 TABS.", "b": "JAKAVI", "st": "15MG", "f": "oral_solid", "r": "oral_solid"},
    {"n": "JAKAVI 20 MG 56 TABS.", "b": "JAKAVI", "st": "20MG", "f": "oral_solid", "r": "oral_solid"},
]


def response(name: str) -> dict:
    return {
        "decision_type": "algorithm_5_order_preserved",
        "results": [
            {"rank": 1, "name": name, "variant_group": name, "commercial_name": name}
        ],
    }


class ProductContextRerankerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = reranker.build_product_catalog(
            RECORDS,
            {"AUGMENTIN": "AUGMENTIN", "JAKAVI": "JAKAVI"},
            compact,
        )

    def selected_product(self, query: str, name: str) -> dict:
        result = reranker.rerank_products(response(name), query, self.catalog, limit=20)
        self.assertEqual(result["decision_type"], "product_context_selection")
        self.assertEqual(result["name_decision_type"], "algorithm_5_order_preserved")
        return result["results"][0]

    def test_mass_units_normalize_to_the_same_measurement(self) -> None:
        self.assertEqual(
            reranker.parse_strengths("1 gm"),
            reranker.parse_strengths("1000 mg"),
        )
        self.assertEqual(
            reranker.parse_strengths("1.2 g"),
            reranker.parse_strengths("1200mg"),
        )
        self.assertEqual(
            reranker.parse_strengths("one 1 gram"),
            reranker.parse_strengths("1,000 m.g."),
        )

    def test_dotted_tablet_form_and_pack_size_normalize(self) -> None:
        evidence = reranker.parse_evidence("14 F.C.Tabs.")
        self.assertEqual(evidence.forms, frozenset({"tablet"}))
        self.assertEqual(evidence.package_counts, frozenset({14}))

    def test_tablet_alias_and_strength_select_product(self) -> None:
        product = self.selected_product("augmentin 1000 mg tablets", "AUGMENTIN")
        self.assertEqual(product["commercial_name"], "AUGMENTIN 1 GM 14 F.C.TABS.")
        self.assertIn("strength_exact", product["matched_context"])
        self.assertIn("dosage_form_match", product["matched_context"])

    def test_vial_context_selects_injection(self) -> None:
        product = self.selected_product("augmentin 1.2 g vial", "AUGMENTIN")
        self.assertEqual(product["commercial_name"], "AUGMENTIN 1.2G VIAL FOR I.V. INJ.")
        self.assertNotIn("strength_conflict", product["context_conflicts"])

    def test_ratio_strength_selects_suspension(self) -> None:
        product = self.selected_product("augmentin 156mg / 5ml suspension", "AUGMENTIN")
        self.assertEqual(product["commercial_name"], "AUGMENTIN 156 MG/5 ML SUSP. 80 ML")

    def test_same_family_strength_selects_jakavi_5mg(self) -> None:
        product = self.selected_product("jakavi 5 mg 56 tabs", "JAKAVI")
        self.assertEqual(product["commercial_name"], "JAKAVI 5 MG 56 TABS.")
        self.assertIn("package_count_match", product["matched_context"])

    def test_name_only_query_does_not_invoke_context_reranker(self) -> None:
        original = response("JAKAVI")
        self.assertIs(
            reranker.rerank_products(original, "jakavi", self.catalog, limit=20),
            original,
        )


if __name__ == "__main__":
    unittest.main()

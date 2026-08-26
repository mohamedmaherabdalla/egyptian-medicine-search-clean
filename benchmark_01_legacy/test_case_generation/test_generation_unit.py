"""Unit tests for commercial-name test generation helpers.

Problem: generator helpers must reject malformed data and produce deterministic
mutations before the full CSV suite is regenerated.
Inputs: small in-memory CatalogRecord and TestCase fixtures.
Outputs: unittest assertions over normalization, indexing, generation, scoping,
and validation behavior.
Edge cases: empty generated query, duplicate rows, unknown category, compact
collisions, and hard-case ratio below threshold.
Failure modes: any regression raises an assertion failure during unittest.
Algorithm choice: unittest is used instead of pytest so the checks run with the
standard Python runtime available in the repository.
"""

from __future__ import annotations

import unittest

from .catalog_io import CatalogIndex
from .generators import _case_from_mutation
from .models import CatalogRecord, Mutation, TestCase
from .normalization import compact_key, lower_query, normalize_search
from .splitters import scope_for_category
from .validators import validate_cases


def _record(name: str, ingredient: str = "ING") -> CatalogRecord:
    compact = compact_key(name)
    return CatalogRecord(
        candidate_id=f"TEST-{compact}",
        commercial_name_en=name,
        commercial_name_norm=normalize_search(name),
        commercial_name_compact=compact,
        commercial_name_ar_norm="",
        base_group_key=normalize_search(name),
        base_group_compact=compact,
        scientific_name=ingredient,
        ingredient_key=ingredient,
        manufacturer_primary="TEST PHARMA",
        drug_class_top="TEST CLASS",
        route_family="oral_solid",
        strengths_join="",
        review_reasons="",
    )


class TestNormalization(unittest.TestCase):
    """Tests for normalization helpers."""

    def test_arabic_digits_normalize_to_ascii(self) -> None:
        self.assertEqual(normalize_search("دواء ١٢٣"), "دواء 123")

    def test_compact_key_removes_punctuation(self) -> None:
        self.assertEqual(compact_key("A.C.E 500 mg"), "ACE500MG")

    def test_lower_query_rejects_empty_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "empty"):
            lower_query("!!!")


class TestCatalogIndex(unittest.TestCase):
    """Tests for compact and prefix collision indexes."""

    def test_collision_names_exclude_expected(self) -> None:
        index = CatalogIndex([_record("BEDO", "A"), _record("BECLO", "B")])
        self.assertEqual(index.collision_names_for("bedo", "BEDO"), "")
        self.assertEqual(index.collision_names_for("bedo", "BECLO"), "BEDO")

    def test_ingredient_collision_detects_different_key(self) -> None:
        index = CatalogIndex([_record("BEDO", "A"), _record("BECLO", "B")])
        self.assertTrue(index.has_ingredient_collision("BECLO", "BEDO"))


class TestGenerationSemantics(unittest.TestCase):
    """Tests for case construction and validation gates."""

    def test_collision_escalates_safe_category_to_dangerous(self) -> None:
        index = CatalogIndex([_record("BEDO", "A"), _record("BECLO", "B")])
        mutation = Mutation("bedo", "test_error", "forced collision")
        case = _case_from_mutation("visual_ligature_full_catalog", _record("BECLO", "B"), mutation, index)
        self.assertEqual(case.danger, "DANGEROUS")

    def test_scope_for_generated_inside_category(self) -> None:
        self.assertEqual(scope_for_category("keyboard_adjacent_expanded_catalog"), "inside")

    def test_validation_rejects_easy_heavy_suite(self) -> None:
        cases = [
            TestCase(f"a{index}", "A", "exact", "keyboard_adjacent", "EASY", "SAFE", "", "test")
            for index in range(3)
        ]
        with self.assertRaisesRegex(ValueError, "hard/extreme ratio"):
            validate_cases(cases)


if __name__ == "__main__":
    unittest.main()

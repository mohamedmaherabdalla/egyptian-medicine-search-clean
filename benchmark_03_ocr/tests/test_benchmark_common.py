#!/usr/bin/env python3

import unittest

from benchmark_common import (
    compact_text,
    difficulty_for_distance,
    levenshtein,
    medicine_head,
    normalized_edit_distance,
)


class BenchmarkCommonTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(compact_text("Augmentin 1 g"), "AUGMENTIN1G")

    def test_context_stripping_is_trailing_and_conservative(self):
        self.assertEqual(medicine_head("M-Lucas 10 mg"), "M LUCAS")
        self.assertEqual(medicine_head("5% DNS"), "5 DNS")

    def test_edit_distance(self):
        self.assertEqual(levenshtein("AUGMNTIN", "AUGMENTIN"), 1)
        self.assertAlmostEqual(normalized_edit_distance("augmntin", "augmentin"), 1 / 9)

    def test_difficulty(self):
        self.assertEqual(difficulty_for_distance(0.0, exact=True), "EXACT")
        self.assertEqual(difficulty_for_distance(0.25), "MEDIUM")
        self.assertEqual(difficulty_for_distance(1.0, empty=True), "EMPTY")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3

import unittest
from types import SimpleNamespace

from generate_search_cases import (
    classify_mistake,
    distance_band,
    flat_prediction_cases,
    prediction_analysis_cohort,
    rejection_reason,
)


class SearchCaseFilteringTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {"eligible_for_search_benchmark": "1"}
        self.observation = {
            "run_status": "ok",
            "empty_output": "0",
            "exact_match": "0",
            "normalized_edit_distance": "0.25",
            "ocr_output_raw": "augmntin",
        }

    def test_real_drug_collision_is_preserved_even_when_distance_is_large(self):
        observation = {**self.observation, "normalized_edit_distance": "0.95"}
        reason = rejection_reason(
            observation, self.mapping, 0.60, {"OTHERDRUG"}, 1, 0, True, ""
        )
        self.assertEqual(reason, "")
        self.assertEqual(
            classify_mistake("OTHERDRUG", "EXPECTED", 8, {"OTHERDRUG"}),
            "real_drug_name_collision",
        )

    def test_unresolved_mapping_is_never_ground_truth(self):
        self.assertEqual(
            rejection_reason(self.observation, None, 0.60, set(), 5, 3, True, ""),
            "ground_truth_not_uniquely_catalog_resolved",
        )

    def test_extreme_non_collision_requires_review(self):
        observation = {**self.observation, "normalized_edit_distance": "0.75"}
        self.assertEqual(
            rejection_reason(observation, self.mapping, 0.60, set(), 4, 1, True, ""),
            "extreme_distance_requires_manual_review",
        )

    def test_conflicting_source_label_is_never_accepted(self):
        self.assertEqual(
            rejection_reason(
                self.observation,
                self.mapping,
                0.60,
                set(),
                5,
                3,
                False,
                "duplicate_pixels_conflicting_ground_truth",
            ),
            "source_ground_truth_excluded:duplicate_pixels_conflicting_ground_truth",
        )

    def test_extreme_prediction_is_represented_as_a_cohort(self):
        self.assertEqual(
            prediction_analysis_cohort("GHONT", "CALAMINE", 0.875, 0.60, set(), 1, 0),
            "extreme_distance_prediction",
        )

    def test_normalized_exact_prediction_is_represented_as_a_cohort(self):
        self.assertEqual(
            prediction_analysis_cohort("CLEXANE", "CLEXANE", 0.0, 0.60, set(), 7, 6),
            "normalized_exact_match",
        )

    def test_distance_band_keeps_extreme_cases_visible(self):
        self.assertEqual(distance_band(7), "6_plus_edits")

    def test_flat_prediction_export_does_not_reject_extreme_distance(self):
        families = [
            SimpleNamespace(key="CALAMINE", name="CALAMINE", aliases=("CALAMINE",))
        ]
        cases = flat_prediction_cases(
            [{
                "edited_name": "GHONT",
                "matched_canonical_name_norm": "CALAMINE",
                "source_model": "example_model",
                "edit_distance_count": "7",
            }],
            families,
            0.60,
        )
        self.assertEqual(cases[0]["accepted"], 1)
        self.assertEqual(cases[0]["analysis_cohort"], "extreme_distance_prediction")
        self.assertEqual(cases[0]["rejection_reason"], "")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from analyze_data4_data5_benchmark import algorithm_equivalence, percent


def result(case_id: str, algorithm: str, top_1: str, decision: str = "ambiguous") -> dict[str, str]:
    return {
        "case_id": case_id,
        "algorithm": algorithm,
        "first_relevant_rank": "1",
        "hit_at_1": "1",
        "hit_at_5": "1",
        "hit_at_10": "1",
        "hit_at_20": "1",
        "reciprocal_rank": "1.0",
        "top_1": top_1,
        "top_5": top_1,
        "top_20": top_1,
        "response_status": "low_confidence",
        "decision_type": decision,
        "needs_clarification": "1",
        "unsafe_confident_top1": "0",
    }


class Data4Data5AnalysisTests(unittest.TestCase):
    def test_percent_formats_fraction_as_percentage(self) -> None:
        self.assertEqual(percent(352 / 780), "45.13%")

    def test_algorithm_equivalence_counts_rank_and_decision_matches(self) -> None:
        algorithms = (
            "algorithm_2_external_fast",
            "algorithm_3_rank_fusion",
            "algorithm_4_family_rescue",
        )
        rows = [result("same", algorithm, "CONAZ") for algorithm in algorithms]
        rows.extend([
            result("different", algorithms[0], "CONAZ"),
            result("different", algorithms[1], "CONAZ"),
            result("different", algorithms[2], "RIVOTRIL"),
        ])
        summary = algorithm_equivalence(rows)
        self.assertEqual(summary["compared_cases"], 2)
        self.assertEqual(summary["identical_retrieval_cases"], 1)
        self.assertEqual(summary["identical_decision_cases"], 2)


if __name__ == "__main__":
    unittest.main()

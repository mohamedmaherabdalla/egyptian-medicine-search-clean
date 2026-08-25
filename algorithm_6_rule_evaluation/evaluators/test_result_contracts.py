#!/usr/bin/env python3
"""Meta-tests for the pure rule-evaluation result contract."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from result_contracts import validate_result_contract


def result(family: str, **values: object) -> dict[str, object]:
    item: dict[str, object] = {
        "base_group_key": family,
        "reasons": [],
    }
    item.update(values)
    return item


class ResultContractMetaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = {
            "case_id": "META-VALID",
            "case_type": "positive",
            "expected_families": "JAKAVI",
            "forbidden_families": "",
            "expected_products": "D2-10000",
            "expected_decision": "product_context_selection",
            "match_policy": "only",
            "target_family_key": "JAKAVI",
            "required_reason": "strength_exact",
        }
        self.response = {
            "decision_type": "product_context_selection",
            "results": [
                result(
                    "JAKAVI",
                    selected_product_id="D2-10000",
                    context_match_status="compatible_product",
                    reasons=["strength_exact"],
                )
            ],
        }

    def assert_rejected(
        self,
        case: dict[str, object],
        response: dict[str, object],
        failure_prefix: str,
    ) -> None:
        failures = validate_result_contract(case, response)
        self.assertTrue(
            any(failure.startswith(failure_prefix) for failure in failures),
            (failure_prefix, failures),
        )

    def test_valid_control_is_accepted(self) -> None:
        self.assertEqual(validate_result_contract(self.case, self.response), [])

    def test_rejects_wrong_stable_product_id(self) -> None:
        response = copy.deepcopy(self.response)
        response["results"][0]["selected_product_id"] = "D2-WRONG"
        self.assert_rejected(
            self.case,
            response,
            "unexpected_selected_product_id:D2-WRONG",
        )

    def test_product_any_policy_accepts_one_allowed_id(self) -> None:
        case = copy.deepcopy(self.case)
        case["match_policy"] = "any"
        case["expected_products"] = "D2-10000;D2-ALTERNATE"
        self.assertEqual(validate_result_contract(case, self.response), [])

    def test_family_any_policy_does_not_require_unreturned_alternative(self) -> None:
        case = copy.deepcopy(self.case)
        case["expected_families"] = "JAKAVI;JAVA"
        case["target_family_key"] = ""
        case["required_reason"] = ""
        case["expected_products"] = ""
        case["match_policy"] = "any"
        self.assertEqual(validate_result_contract(case, self.response), [])

    def test_product_all_policy_rejects_a_missing_id(self) -> None:
        case = copy.deepcopy(self.case)
        case["match_policy"] = "all"
        case["expected_products"] = "D2-10000;D2-ALTERNATE"
        self.assert_rejected(
            case,
            self.response,
            "missing_expected_product:D2-ALTERNATE",
        )

    def test_standalone_strict_product_schema_is_accepted(self) -> None:
        case = {
            "case_id": "PCS-TIE-META",
            "case_type": "positive",
            "expected_family": "ESTEROMAP",
            "acceptable_product_ids": "D2-07545;D2-07546",
            "forbidden_product_ids": "D2-07547",
            "expected_decision": "product_context_selection",
            "match_policy": "all_expected_only",
        }
        response = {
            "decision_type": "product_context_selection",
            "results": [
                result("ESTEROMAP", selected_product_id="D2-07545"),
                result("ESTEROMAP", selected_product_id="D2-07546"),
            ],
        }
        self.assertEqual(validate_result_contract(case, response), [])

    def test_strict_product_schema_rejects_missing_and_extra_tie_ids(self) -> None:
        case = {
            "case_id": "PCS-TIE-MUTATED",
            "case_type": "positive",
            "expected_family": "ESTEROMAP",
            "acceptable_product_ids": "D2-07545;D2-07546",
            "forbidden_product_ids": "D2-07547",
            "expected_decision": "product_context_selection",
            "match_policy": "all_expected_only",
        }
        response = {
            "decision_type": "product_context_selection",
            "results": [
                result("ESTEROMAP", selected_product_id="D2-07545"),
                result("ESTEROMAP", selected_product_id="D2-07547"),
            ],
        }
        failures = validate_result_contract(case, response)
        self.assertIn("missing_expected_product:D2-07546", failures)
        self.assertIn("forbidden_product_returned:D2-07547", failures)
        self.assertTrue(
            any(
                failure.startswith("unexpected_selected_product_id:D2-07547")
                for failure in failures
            ),
            failures,
        )

    def test_standalone_strict_abstention_schema_rejects_a_product(self) -> None:
        case = {
            "case_id": "PCS-CON-META",
            "case_type": "negative",
            "expected_family": "DORMICUM",
            "acceptable_product_ids": "",
            "forbidden_product_ids": "D2-06486;D2-06487",
            "expected_decision": "product_context_no_compatible_product",
            "match_policy": "abstain_no_product",
        }
        response = {
            "decision_type": "product_context_no_compatible_product",
            "results": [
                result("DORMICUM", selected_product_id="D2-06486")
            ],
        }
        self.assert_rejected(
            case,
            response,
            "product_returned_during_abstention:rows=1",
        )

    def test_rejects_extra_irrelevant_family_under_only_policy(self) -> None:
        case = copy.deepcopy(self.case)
        case["expected_products"] = ""
        case["required_reason"] = ""
        response = copy.deepcopy(self.response)
        response["results"].append(result("UNRELATED"))
        self.assert_rejected(
            case,
            response,
            "unexpected_family_under_only:UNRELATED",
        )

    def test_rejects_forbidden_family(self) -> None:
        case = copy.deepcopy(self.case)
        case["expected_products"] = ""
        case["required_reason"] = ""
        case["match_policy"] = "all"
        case["forbidden_families"] = "DANGEROUS LOOKALIKE"
        response = copy.deepcopy(self.response)
        response["results"].append(result("DANGEROUS LOOKALIKE"))
        self.assert_rejected(
            case,
            response,
            "forbidden_family_returned:DANGEROUSLOOKALIKE",
        )

    def test_rejects_required_reason_attached_to_wrong_row(self) -> None:
        case = copy.deepcopy(self.case)
        case["expected_products"] = ""
        case["match_policy"] = "all"
        response = copy.deepcopy(self.response)
        response["results"] = [
            result("JAKAVI"),
            result("JAVA", reasons=["strength_exact"]),
        ]
        self.assert_rejected(
            case,
            response,
            "required_reason_missing_on_family:JAKAVI:strength_exact",
        )

    def test_rejects_collapsed_ambiguity_even_under_any_policy(self) -> None:
        case = {
            "case_id": "META-AMBIGUITY",
            "case_type": "ambiguity",
            "expected_families": "TRICHOGEL;TRICHOGYL",
            "match_policy": "any",
        }
        response = {"results": [result("TRICHOGEL")]}
        self.assert_rejected(case, response, "ambiguity_collapsed:missing=TRICHOGYL")

    def test_rejects_selected_product_when_abstention_is_expected(self) -> None:
        case = {
            "case_id": "META-ABSTAIN",
            "case_type": "negative",
            "query": "XANAX",
            "product_context": "500 mg tab",
            "expected_families": "XANAX",
            "expected_decision": "product_context_no_compatible_product",
            "match_policy": "abstain_no_product",
        }
        response = {
            "decision_type": "product_context_no_compatible_product",
            "results": [
                result(
                    "XANAX",
                    selected_product_id="D2-UNSAFE",
                    context_match_status="compatible_product",
                )
            ],
        }
        self.assert_rejected(
            case,
            response,
            "product_returned_during_abstention:rows=1",
        )

    def test_family_placeholder_is_allowed_during_product_abstention(self) -> None:
        case = {
            "case_id": "META-ABSTAIN-CONTROL",
            "case_type": "negative",
            "query": "XANAX",
            "product_context": "500 mg tab",
            "expected_families": "XANAX",
            "expected_decision": "product_context_no_compatible_product",
            "match_policy": "abstain_no_product",
        }
        response = {
            "decision_type": "product_context_no_compatible_product",
            "results": [
                result("XANAX", context_match_status="no_compatible_product")
            ],
        }
        self.assertEqual(validate_result_contract(case, response), [])


if __name__ == "__main__":
    unittest.main()

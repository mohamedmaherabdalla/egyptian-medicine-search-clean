#!/usr/bin/env python3
"""Pure validation of one rule-evaluation case against one API response.

The validator deliberately has no catalog, network, or Algorithm 6 imports.  A
test-set row and a decoded ``/api/search`` response are sufficient, which makes
the result contract independently unit-testable and safe to reuse from the
live evaluator.

``expected_products`` (or the strict product benchmark's
``acceptable_product_ids``) is a set of stable catalog product IDs interpreted
by ``match_policy`` (``any``, ``all``, ``only``, or the strict tie policy
``all_expected_only``).  Product abstention is expressed by
``match_policy=abstain_no_product`` together with an ``expected_decision``
ending in ``no_compatible_product``.  The explicit sentinels ``__NONE__``,
``NONE``, ``ABSTAIN``, and ``NO_PRODUCT`` remain accepted for older rows.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


MATCH_POLICIES = frozenset(
    {"all", "any", "only", "all_expected_only", "abstain_no_product"}
)
PRODUCT_ABSTENTION_SENTINELS = frozenset(
    {"__NONE__", "NONE", "ABSTAIN", "NO_PRODUCT"}
)


def compact(value: object) -> str:
    """Return the API's punctuation-insensitive family identity."""

    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _split(value: object, *, normalize: bool) -> list[str]:
    if isinstance(value, str):
        raw_values: Sequence[object] = value.split(";")
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        raw_values = value
    elif value is None:
        raw_values = ()
    else:
        raw_values = (value,)

    values: list[str] = []
    for raw in raw_values:
        item = compact(raw) if normalize else str(raw or "").strip()
        if item and item not in values:
            values.append(item)
    return values


def split_families(value: object) -> list[str]:
    return _split(value, normalize=True)


def split_exact_values(value: object) -> list[str]:
    return _split(value, normalize=False)


def result_family_key(item: Mapping[str, Any]) -> str:
    """Extract the exact matched base-family identity from a public result."""

    if item.get("source") == "algorithm_6_visual_gap":
        return compact(
            item.get("matched_family_key")
            or item.get("matched_family_name")
            or item.get("base_group_key")
            or item.get("commercial_name")
        )
    return compact(
        item.get("base_group_key")
        or item.get("matched_family_key")
        or item.get("matched_family_name")
        or item.get("variant_group")
        or item.get("name")
    )


def result_reasons(item: Mapping[str, Any]) -> set[str]:
    value = item.get("reasons") or []
    if isinstance(value, str):
        return {part.strip() for part in value.split("|") if part.strip()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return {str(part).strip() for part in value if str(part).strip()}
    return set()


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _response_results(
    response: Mapping[str, Any], failures: list[str]
) -> list[Mapping[str, Any]]:
    raw_results = response.get("results", [])
    if not isinstance(raw_results, list):
        failures.append("results_not_a_list")
        return []
    results: list[Mapping[str, Any]] = []
    for index, item in enumerate(raw_results, 1):
        if not isinstance(item, Mapping):
            failures.append(f"row_{index}_not_an_object")
            continue
        results.append(item)
    return results


def _expects_product_abstention(case: Mapping[str, Any]) -> bool:
    if _truthy(case.get("expect_product_abstention")):
        return True
    outcome = str(case.get("expected_product_outcome") or "").strip().lower()
    if outcome in {"abstain", "abstention", "none", "no_product"}:
        return True
    expected_products = {
        value.upper()
        for value in split_exact_values(
            case.get("expected_products") or case.get("acceptable_product_ids")
        )
    }
    if expected_products & PRODUCT_ABSTENTION_SENTINELS:
        return True

    policy = str(case.get("match_policy") or "").strip().lower()
    decision = str(case.get("expected_decision") or "").strip().lower()
    return policy == "abstain_no_product" and decision.endswith(
        "no_compatible_product"
    )


def _has_selected_product(item: Mapping[str, Any]) -> bool:
    return bool(
        str(item.get("selected_product_id") or "").strip()
        or str(item.get("selected_product_key") or "").strip()
        or item.get("context_match_status") == "compatible_product"
    )


def _target_rows_for_reason(
    case: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    expected_families: Sequence[str],
) -> tuple[list[tuple[str, Mapping[str, Any]]], list[str]]:
    explicit_target = compact(case.get("target_family_key"))
    target_families = [explicit_target] if explicit_target else list(expected_families)
    if not target_families:
        return [], []

    located: list[tuple[str, Mapping[str, Any]]] = []
    missing: list[str] = []
    for family in target_families:
        item = next(
            (result for result in results if result_family_key(result) == family),
            None,
        )
        if item is None:
            missing.append(family)
        else:
            located.append((family, item))
    return located, missing


def _validate_products(
    case: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    failures: list[str],
) -> None:
    selected_rows = [
        index
        for index, item in enumerate(results, 1)
        if _has_selected_product(item)
    ]
    if _expects_product_abstention(case):
        if selected_rows:
            failures.append(
                "product_returned_during_abstention:rows="
                + ",".join(str(index) for index in selected_rows)
            )
        return

    expected_products = [
        value
        for value in split_exact_values(
            case.get("expected_products") or case.get("acceptable_product_ids")
        )
        if value.upper() not in PRODUCT_ABSTENTION_SENTINELS
    ]
    forbidden_products = split_exact_values(
        case.get("forbidden_products") or case.get("forbidden_product_ids")
    )

    observed_products: list[str] = []
    for index, item in enumerate(results, 1):
        selected_id = str(item.get("selected_product_id") or "").strip()
        if selected_id and selected_id not in observed_products:
            observed_products.append(selected_id)
        elif _has_selected_product(item):
            failures.append(f"selected_product_id_missing:row_{index}")

    for product_id in observed_products:
        if product_id in forbidden_products:
            failures.append(f"forbidden_product_returned:{product_id}")

    if not expected_products:
        return

    policy = str(case.get("match_policy") or "all").strip().lower()
    if policy == "any":
        if not (set(expected_products) & set(observed_products)):
            failures.append(
                "missing_any_expected_product:" + ",".join(expected_products)
            )
        return

    for product_id in expected_products:
        if product_id not in observed_products:
            failures.append(f"missing_expected_product:{product_id}")
    if policy in {"only", "all_expected_only"}:
        for product_id in observed_products:
            if product_id not in expected_products:
                failures.append(
                    f"unexpected_selected_product_id:{product_id}:expected="
                    + ",".join(expected_products)
                )


def validate_result_contract(
    case: Mapping[str, Any], response: Mapping[str, Any]
) -> list[str]:
    """Return stable, human-readable contract failures for one case/response.

    An empty return value means that every populated result-level expectation
    was satisfied.  The function does not mutate either input.
    """

    failures: list[str] = []
    if not isinstance(case, Mapping):
        return ["case_not_an_object"]
    if not isinstance(response, Mapping):
        return ["response_not_an_object"]

    results = _response_results(response, failures)
    observed_families = [result_family_key(item) for item in results]
    observed_set = {family for family in observed_families if family}
    expected_families = split_families(
        case.get("expected_families") or case.get("expected_family")
    )
    expected_set = set(expected_families)
    forbidden_families = set(split_families(case.get("forbidden_families")))

    policy = str(case.get("match_policy") or "all").strip().lower()
    if policy not in MATCH_POLICIES:
        failures.append(f"invalid_match_policy:{policy}")
        policy = "all"

    family_policy = {
        "abstain_no_product": "all",
        "all_expected_only": "only",
    }.get(policy, policy)
    if policy == "abstain_no_product" and not _expects_product_abstention(case):
        failures.append(
            "abstain_no_product_requires_no_compatible_product_decision"
        )

    if family_policy in {"all", "only"}:
        for family in expected_families:
            if family not in observed_set:
                failures.append(f"missing_expected_family:{family}")
    elif expected_set and not (expected_set & observed_set):
        failures.append(
            "missing_any_expected_family:" + ",".join(expected_families)
        )

    if family_policy == "only":
        for family in sorted(observed_set - expected_set):
            failures.append(f"unexpected_family_under_only:{family}")

    for family in sorted(forbidden_families & observed_set):
        failures.append(f"forbidden_family_returned:{family}")

    if str(case.get("case_type") or "").strip().lower() == "ambiguity":
        preserved = expected_set & observed_set
        if len(expected_set) >= 2 and preserved != expected_set:
            missing = sorted(expected_set - preserved)
            failures.append("ambiguity_collapsed:missing=" + ",".join(missing))

    maximum_rank_text = str(case.get("maximum_rank") or "").strip()
    if maximum_rank_text:
        try:
            maximum_rank = int(maximum_rank_text)
        except ValueError:
            failures.append(f"invalid_maximum_rank:{maximum_rank_text}")
        else:
            ranked_targets = (
                expected_families
                if family_policy in {"all", "only"}
                else [family for family in expected_families if family in observed_set]
            )
            for family in ranked_targets:
                if family in observed_families:
                    rank = observed_families.index(family) + 1
                    if rank > maximum_rank:
                        failures.append(
                            f"expected_family_below_rank:{family}:{rank}>{maximum_rank}"
                        )

    expected_decision = str(case.get("expected_decision") or "").strip()
    observed_decision = str(response.get("decision_type") or "").strip()
    if expected_decision == "not_visual_gap":
        if observed_decision == "visual_gap_matches":
            failures.append("unexpected_visual_gap_dispatch")
    elif expected_decision and observed_decision != expected_decision:
        failures.append(
            f"decision:{observed_decision or '<missing>'}!={expected_decision}"
        )

    expected_mode = str(case.get("expected_mode") or "").strip()
    visual_gap = response.get("visual_gap") or {}
    observed_mode = (
        str(visual_gap.get("mode") or "").strip()
        if isinstance(visual_gap, Mapping)
        else ""
    )
    if expected_mode and observed_mode != expected_mode:
        failures.append(f"visual_mode:{observed_mode or '<missing>'}!={expected_mode}")

    expected_count_text = str(case.get("expected_candidate_count") or "").strip()
    if expected_count_text:
        try:
            expected_count = int(expected_count_text)
            observed_count = int(response.get("candidate_count"))
        except (TypeError, ValueError):
            failures.append("candidate_count_not_an_integer")
        else:
            if observed_count != expected_count:
                failures.append(f"candidate_count:{observed_count}!={expected_count}")

    required_reasons = split_exact_values(case.get("required_reason"))
    if required_reasons:
        reason_rows, missing_reason_targets = _target_rows_for_reason(
            case, results, expected_families
        )
        for family in missing_reason_targets:
            failures.append(f"required_reason_target_missing:{family}")
        for required_reason in required_reasons:
            if reason_rows:
                for family, item in reason_rows:
                    if required_reason not in result_reasons(item):
                        failures.append(
                            f"required_reason_missing_on_family:{family}:{required_reason}"
                        )
            elif not missing_reason_targets:
                all_reasons = set().union(
                    *(result_reasons(item) for item in results)
                ) if results else set()
                if required_reason not in all_reasons:
                    failures.append(f"required_reason_missing:{required_reason}")

    forbidden_reasons = split_exact_values(case.get("forbidden_reason"))
    all_reasons = set().union(
        *(result_reasons(item) for item in results)
    ) if results else set()
    for forbidden_reason in forbidden_reasons:
        if forbidden_reason in all_reasons:
            failures.append(f"forbidden_reason_present:{forbidden_reason}")

    target_family = compact(case.get("target_family_key"))
    if target_family:
        target = next(
            (item for item in results if result_family_key(item) == target_family),
            None,
        )
        expected_hidden = str(
            case.get("expected_hidden_character_count") or ""
        ).strip()
        expected_coverage = str(
            case.get("expected_visible_coverage") or ""
        ).strip()
        if target is None:
            if expected_hidden or expected_coverage:
                failures.append(f"metric_target_missing:{target_family}")
        else:
            if expected_hidden:
                try:
                    hidden_matches = int(target.get("hidden_character_count")) == int(
                        expected_hidden
                    )
                except (TypeError, ValueError):
                    hidden_matches = False
                if not hidden_matches:
                    failures.append(
                        "hidden_character_count:"
                        f"{target.get('hidden_character_count')}!={expected_hidden}"
                    )

            if expected_coverage:
                try:
                    coverage_matches = abs(
                        float(target.get("visible_coverage")) - float(expected_coverage)
                    ) <= 1e-5
                except (TypeError, ValueError):
                    coverage_matches = False
                if not coverage_matches:
                    failures.append(
                        "visible_coverage:"
                        f"{target.get('visible_coverage')}!={expected_coverage}"
                    )

    if _truthy(case.get("confirmation_required")):
        if response.get("confirmation_required") is not True:
            failures.append("response_confirmation_required_false")
        for index, item in enumerate(results, 1):
            if item.get("confirmation_required") is not True:
                failures.append(f"row_{index}_confirmation_required_false")
            if item.get("needs_clarification") is not True:
                failures.append(f"row_{index}_needs_clarification_false")

    _validate_products(case, results, failures)
    return failures


__all__ = [
    "compact",
    "result_family_key",
    "result_reasons",
    "split_exact_values",
    "split_families",
    "validate_result_contract",
]

"""Scope splitting for commercial-name evaluation cases.

Problem: the expanded suite mixes pure commercial-name errors with contextual
queries, so evaluation needs explicit inside/outside/semi-outside files.
Inputs: final TestCase rows with category labels.
Outputs: three deterministic lists keyed by scope.
Edge cases: seed categories, generated categories, and unknown categories.
Failure modes: unknown categories raise ValueError; silently defaulting to one
scope would corrupt category-level metrics.
Algorithm choice: category-level mapping is used instead of heuristic text
inspection because the generator knows why each row was created.
"""

from __future__ import annotations

from .config import GENERATED_CATEGORY_SPECS, SEED_CATEGORY_SCOPES
from .models import Scope, TestCase


def scope_for_category(category: str) -> Scope:
    """Return the evaluation scope for a category.

    Args:
        category: Test-case category.

    Returns:
        One of inside, semi_outside, or outside.

    Raises:
        ValueError: If the category is unknown.
    """

    if category in GENERATED_CATEGORY_SPECS:
        return GENERATED_CATEGORY_SPECS[category].scope
    if category in SEED_CATEGORY_SCOPES:
        return SEED_CATEGORY_SCOPES[category]  # type: ignore[return-value]
    raise ValueError(f"unknown category cannot be scoped: {category}")


def split_by_scope(cases: list[TestCase]) -> dict[Scope, list[TestCase]]:
    """Split final cases into inside/outside/semi-outside buckets.

    Args:
        cases: Final generated and seed cases.

    Returns:
        Dictionary with all three scope keys present.
    """

    out: dict[Scope, list[TestCase]] = {"inside": [], "semi_outside": [], "outside": []}
    for case in cases:
        out[scope_for_category(case.category)].append(case)
    return out


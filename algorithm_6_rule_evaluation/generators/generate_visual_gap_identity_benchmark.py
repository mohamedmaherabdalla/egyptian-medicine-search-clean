#!/usr/bin/env python3
"""Generate a fresh exact-identity visual-gap benchmark.

This generator is deliberately independent of Algorithm 6 search output.  It
reads the current catalog, reconstructs exact base-family and family-head
surfaces from catalog fields, creates masks, and computes every family that
satisfies the literal positional evidence with its own ordered-gap matcher.

The benchmark fixes the historical ``variant_group`` oracle problem.  Every
row stores both the exact source family key and the complete set of exact base
family keys relevant to the generated evidence.  The evaluator must use the
API's ``matched_family_key`` field; broad display groups are never labels.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().parents[1]
CATALOG = REPO / "app" / "data" / "catalog.json"
OUTPUT = PACKAGE / "test_sets" / "generated" / "visual_gap_identity_benchmark.csv"
MANIFEST = (
    PACKAGE / "test_sets" / "manifests" / "visual_gap_identity_benchmark.manifest.json"
)
EVALUATOR = (
    PACKAGE / "evaluators" / "evaluate_visual_gap_identity_benchmark.py"
)
SEED = "algorithm-6-visual-gap-exact-identity-v1"
REQUEST_LIMIT = 20


COLUMNS = [
    "case_id",
    "evaluation_kind",
    "case_type",
    "stratum",
    "split",
    "split_group_id",
    "query",
    "expected_decision",
    "expected_mode",
    "match_policy",
    "request_limit",
    "source_exact_family_key",
    "relevant_exact_family_keys",
    "forbidden_exact_family_keys",
    "oracle_fragments",
    "oracle_anchor_start",
    "oracle_anchor_end",
    "oracle_explicit",
    "oracle_substitution",
    "required_reason_on_source",
    "forbidden_reason_any_result",
    "confirmation_required",
    "generation_method",
    "notes",
]


MAIN_QUOTAS = {"development": 32, "holdout": 8}
OCR_QUOTAS = {"development": 24, "holdout": 6}
AMBIGUITY_QUOTAS = {"development": 24, "holdout": 6}
MARKER_QUOTAS = {"development": 18, "holdout": 6}
NUMERIC_POSITIVE_QUOTAS = {"development": 16, "holdout": 4}
NUMERIC_GUARD_QUOTAS = {"development": 8, "holdout": 2}
ZERO_WIDTH_QUOTAS = {"development": 8, "holdout": 2}
SHORT_FLOOR_QUOTAS = {"development": 16, "holdout": 4}
PUNCTUATION_QUOTAS = {"development": 16, "holdout": 4}


# Directional observed OCR text -> catalog spelling rules.  These literals
# are copied into the manifest as part of the benchmark protocol; the
# generator does not import the runtime registry or call its variant function.
OCR_RULES: tuple[tuple[str, str, float], ...] = (
    ("E", "G", 0.60),
    ("G", "E", 0.60),
    ("I", "E", 0.45),
    ("E", "I", 0.45),
    ("Y", "E", 0.45),
    ("E", "Y", 0.45),
    ("I", "Y", 0.45),
    ("Y", "I", 0.45),
    ("CL", "D", 0.40),
    ("D", "CL", 0.55),
    ("AL", "D", 0.45),
    ("D", "AL", 0.70),
)


@dataclass(frozen=True)
class Family:
    key: str
    name: str
    normalized: str
    manufacturers: frozenset[str]
    head_key: str

    @property
    def surfaces(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(value for value in (self.key, self.head_key) if value))


@dataclass(frozen=True)
class Pattern:
    fragments: tuple[str, ...]
    anchor_start: bool
    anchor_end: bool
    explicit: bool


@dataclass
class VisualIndexes:
    """Independent exact-surface indexes keyed by retained fragments."""

    leading: dict[tuple[str, ...], set[str]]
    trailing: dict[tuple[str, ...], set[str]]
    both_ends: dict[tuple[str, ...], set[str]]
    internal: dict[tuple[str, ...], set[str]]
    multi_fragment: dict[tuple[str, ...], set[str]]
    shorthand: dict[tuple[str, ...], set[str]]


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(*values: object) -> str:
    return hashlib.sha256("|".join(map(str, values)).encode("utf-8")).hexdigest()


def normalize(value: object) -> str:
    text = str(value or "").upper()
    text = re.sub(r"[^0-9A-Z]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact(value: object) -> str:
    return re.sub(r"[^0-9A-Z]", "", normalize(value))


def split_for_family(family_key: str) -> str:
    return (
        "holdout"
        if int(stable_hash(SEED, "split", family_key)[:8], 16) % 5 == 0
        else "development"
    )


def row_split(keys: Iterable[str]) -> str | None:
    values = sorted({key for key in keys if key})
    if not values:
        return None
    splits = {split_for_family(key) for key in values}
    return next(iter(splits)) if len(splits) == 1 else None


def group_id(keys: Iterable[str]) -> str:
    values = sorted({key for key in keys if key})
    return "VG-GROUP-" + stable_hash(SEED, "group", *values)[:14].upper()


def build_families(records: Sequence[dict[str, Any]]) -> list[Family]:
    """Reconstruct exact family and catalog-derived family-head surfaces.

    The family-head derivation mirrors the documented catalog rule using only
    base names and manufacturer overlap: a first token of at least four
    characters becomes a head when another family with that token shares a
    manufacturer.  The algorithm module is not imported.
    """

    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        name = str(record.get("b") or record.get("n") or "").strip()
        key = compact(name)
        if not key:
            continue
        item = grouped.setdefault(
            key,
            {"name": name, "normalized": normalize(name), "manufacturers": set()},
        )
        # Preserve the catalog's exact manufacturer spelling.  The runtime
        # family-head rule intersects these raw strings; normalizing them here
        # could invent overlap between differently punctuated manufacturers.
        manufacturer = str(record.get("m") or "").strip()
        if manufacturer:
            item["manufacturers"].add(manufacturer)

    first_token_groups: dict[str, list[str]] = defaultdict(list)
    for key, item in grouped.items():
        tokens = item["normalized"].split()
        first = tokens[0] if tokens else ""
        if len(first) >= 4:
            first_token_groups[first].append(key)

    head_by_key: dict[str, str] = {}
    for first, keys in first_token_groups.items():
        if len(keys) < 2:
            continue
        for key in keys:
            own = grouped[key]["manufacturers"]
            if own and any(
                other != key and bool(own & grouped[other]["manufacturers"])
                for other in keys
            ):
                head_by_key[key] = compact(first)

    families = [
        Family(
            key=key,
            name=item["name"],
            normalized=item["normalized"],
            manufacturers=frozenset(item["manufacturers"]),
            head_key=head_by_key.get(key, ""),
        )
        for key, item in sorted(grouped.items())
    ]
    if len(families) != 17_476:
        raise RuntimeError(f"expected 17,476 exact families, found {len(families)}")
    return families


def ordered_gap_match(target: str, pattern: Pattern) -> bool:
    """Independent literal ordered-fragment oracle.

    Every explicit marker must hide at least one target character, including
    a leading or trailing marker.  Shorthand preserves order and anchors but
    does not impose a minimum hidden width.
    """

    if not target or not pattern.fragments or any(not part for part in pattern.fragments):
        return False

    def search(fragment_index: int, previous_end: int) -> bool:
        fragment = pattern.fragments[fragment_index]
        minimum_start = previous_end
        if pattern.explicit and (
            fragment_index > 0 or (fragment_index == 0 and not pattern.anchor_start)
        ):
            minimum_start += 1

        if fragment_index == 0 and pattern.anchor_start:
            starts: Iterable[int] = (0,)
        elif fragment_index == len(pattern.fragments) - 1 and pattern.anchor_end:
            starts = (len(target) - len(fragment),)
        else:
            starts = range(max(0, minimum_start), len(target) - len(fragment) + 1)

        for start in starts:
            if start < minimum_start or not target.startswith(fragment, start):
                continue
            end = start + len(fragment)
            if fragment_index == len(pattern.fragments) - 1:
                if pattern.explicit and not pattern.anchor_end and end >= len(target):
                    continue
                return True
            if search(fragment_index + 1, end):
                return True
        return False

    return search(0, 0)


def exact_relevance(families: Sequence[Family], patterns: Sequence[Pattern]) -> set[str]:
    return {
        family.key
        for family in families
        if any(
            ordered_gap_match(surface, pattern)
            for pattern in patterns
            for surface in family.surfaces
        )
    }


def build_visual_indexes(families: Sequence[Family]) -> VisualIndexes:
    """Enumerate literal fragment constraints once for the complete catalog.

    This is equivalent to repeatedly calling :func:`ordered_gap_match`, but it
    makes candidate generation linear in catalog size instead of quadratic.
    Prefix/suffix widths cover every generated ordinary, OCR, short-floor, and
    zero-width edge pattern in this benchmark.
    """

    stores: dict[str, defaultdict[tuple[str, ...], set[str]]] = {
        name: defaultdict(set)
        for name in (
            "leading",
            "trailing",
            "both_ends",
            "internal",
            "multi_fragment",
            "shorthand",
        )
    }
    for family in families:
        for surface in family.surfaces:
            length = len(surface)
            for width in range(2, min(18, length - 1) + 1):
                stores["leading"][(surface[-width:],)].add(family.key)
                stores["trailing"][(surface[:width],)].add(family.key)

            for left_width in range(2, 7):
                for right_width in range(2, 7):
                    if length > left_width + right_width:
                        stores["internal"][(
                            surface[:left_width],
                            surface[-right_width:],
                        )].add(family.key)

            if length >= 6:
                stores["shorthand"][(surface[:3], surface[-3:])].add(family.key)

            for width in range(2, min(6, length - 2) + 1):
                for start in range(1, length - width):
                    stores["both_ends"][(surface[start : start + width],)].add(family.key)

            if length >= 8:
                for middle_start in range(3, length - 4):
                    stores["multi_fragment"][(
                        surface[:2],
                        surface[middle_start : middle_start + 2],
                        surface[-2:],
                    )].add(family.key)

    return VisualIndexes(**{name: dict(values) for name, values in stores.items()})


def indexed_relevance(
    indexes: VisualIndexes,
    mode: str,
    pattern: Pattern,
) -> set[str]:
    store = getattr(indexes, mode)
    return set(store.get(pattern.fragments, set()))


def mode_pattern(mode: str, target: str, salt: str) -> tuple[str, Pattern]:
    selector = int(stable_hash(SEED, mode, target, salt)[:8], 16)
    if mode == "leading":
        visible = 5 + selector % 2
        fragment = target[-visible:]
        return f"...{fragment}", Pattern((fragment,), False, True, True)
    if mode == "trailing":
        visible = 5 + selector % 2
        fragment = target[:visible]
        return f"{fragment}...", Pattern((fragment,), True, False, True)
    if mode == "both_ends":
        width = 4 + selector % 2
        available = len(target) - width - 1
        start = 1 + selector % max(1, available)
        start = min(start, len(target) - width - 1)
        fragment = target[start : start + width]
        return f"...{fragment}...", Pattern((fragment,), False, False, True)
    if mode == "internal":
        left_width = 3 + selector % 2
        right_width = 3 + (selector // 2) % 2
        left, right = target[:left_width], target[-right_width:]
        return f"{left}...{right}", Pattern((left, right), True, True, True)
    if mode == "multi_fragment":
        middle_start = 3 + selector % max(1, len(target) - 7)
        middle_start = min(middle_start, len(target) - 4)
        fragments = (target[:2], target[middle_start : middle_start + 2], target[-2:])
        return "...".join(fragments), Pattern(fragments, True, True, True)
    if mode == "shorthand":
        fragments = (target[:3], target[-3:])
        return " ".join(fragments), Pattern(fragments, True, True, False)
    raise ValueError(f"unknown mode: {mode}")


def make_row(
    *,
    case_type: str,
    stratum: str,
    query: str,
    source: str,
    relevant: Iterable[str] = (),
    forbidden: Iterable[str] = (),
    pattern: Pattern | None = None,
    expected_decision: str = "visual_gap_matches",
    expected_mode: str = "",
    match_policy: str = "source_and_all_relevant",
    evaluation_kind: str = "catalog_challenge",
    substitution: str = "",
    required_reason: str = "visual_gap_ordered_fragments",
    forbidden_reason: str = "",
    confirmation_required: bool = True,
    generation_method: str,
    notes: str = "",
) -> dict[str, str]:
    relevant_values = sorted(set(relevant))
    forbidden_values = sorted(set(forbidden))
    split_keys = set(relevant_values) | set(forbidden_values) | ({source} if source else set())
    split = row_split(split_keys)
    if split is None:
        raise ValueError("a benchmark row crossed family-stable split boundaries")
    identity = stable_hash(
        SEED,
        stratum,
        query,
        source,
        ";".join(relevant_values),
        ";".join(forbidden_values),
    )
    return {
        "case_id": "VGI-" + identity[:16].upper(),
        "evaluation_kind": evaluation_kind,
        "case_type": case_type,
        "stratum": stratum,
        "split": split,
        "split_group_id": group_id(split_keys),
        "query": query,
        "expected_decision": expected_decision,
        "expected_mode": expected_mode,
        "match_policy": match_policy,
        "request_limit": str(REQUEST_LIMIT),
        "source_exact_family_key": source,
        "relevant_exact_family_keys": ";".join(relevant_values),
        "forbidden_exact_family_keys": ";".join(forbidden_values),
        "oracle_fragments": ";".join(pattern.fragments) if pattern else "",
        "oracle_anchor_start": "1" if pattern and pattern.anchor_start else "0",
        "oracle_anchor_end": "1" if pattern and pattern.anchor_end else "0",
        "oracle_explicit": "1" if pattern and pattern.explicit else "0",
        "oracle_substitution": substitution,
        "required_reason_on_source": required_reason,
        "forbidden_reason_any_result": forbidden_reason,
        "confirmation_required": "1" if confirmation_required else "0",
        "generation_method": generation_method,
        "notes": notes,
    }


def select_by_split(
    candidates: Sequence[dict[str, str]],
    quotas: dict[str, int],
    *,
    salt: str,
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for split, required in quotas.items():
        eligible = [row for row in candidates if row["split"] == split]
        eligible.sort(key=lambda row: stable_hash(SEED, salt, row["case_id"]))
        if len(eligible) < required:
            raise RuntimeError(
                f"not enough {salt}/{split} candidates: {len(eligible)} < {required}"
            )
        selected.extend(eligible[:required])
    return selected


def build_main_positive_rows(
    families: Sequence[Family],
    indexes: VisualIndexes,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    used_sources: set[str] = set()
    for mode in (
        "leading",
        "trailing",
        "both_ends",
        "internal",
        "multi_fragment",
        "shorthand",
    ):
        candidates: list[dict[str, str]] = []
        for family in families:
            target = family.key
            if (
                family.key in used_sources
                or not target.isalpha()
                or len(target) < 9
                or len(target) > 18
            ):
                continue
            query, pattern = mode_pattern(mode, target, "main")
            relevant = indexed_relevance(indexes, mode, pattern)
            if relevant != {family.key}:
                continue
            candidates.append(make_row(
                case_type="positive",
                stratum=mode,
                query=query,
                source=family.key,
                relevant=relevant,
                pattern=pattern,
                expected_mode="internal" if mode in {"multi_fragment", "shorthand"} else mode,
                generation_method=(
                    "catalog base selected before evaluation; independent ordered-gap oracle "
                    "found one exact base/head family"
                ),
                notes="Unique exact-relevance row; bounded fuzzy candidates are measured separately.",
            ))
        chosen = select_by_split(candidates, MAIN_QUOTAS, salt=f"main-{mode}")
        used_sources.update(row["source_exact_family_key"] for row in chosen)
        rows.extend(chosen)
    return rows


def build_ambiguity_rows(
    families: Sequence[Family],
    indexes: VisualIndexes,
) -> list[dict[str, str]]:
    groups: dict[str, set[str]] = defaultdict(set)
    patterns: dict[str, Pattern] = {}
    for family in families:
        for surface in family.surfaces:
            if not surface.isalpha() or not 8 <= len(surface) <= 20:
                continue
            fragments = (surface[:3], surface[-3:])
            query = f"{fragments[0]}...{fragments[1]}"
            pattern = Pattern(fragments, True, True, True)
            if ordered_gap_match(surface, pattern):
                groups[query].add(family.key)
                patterns[query] = pattern

    candidates: list[dict[str, str]] = []
    for query, indexed in groups.items():
        if not 2 <= len(indexed) <= 8:
            continue
        pattern = patterns[query]
        relevant = indexed_relevance(indexes, "internal", pattern)
        if relevant != indexed or row_split(relevant) is None:
            continue
        source = min(relevant)
        candidates.append(make_row(
            case_type="ambiguity",
            stratum="exact_identity_ambiguity",
            query=query,
            source=source,
            relevant=relevant,
            pattern=pattern,
            expected_mode="internal",
            match_policy="all_relevant",
            evaluation_kind="safety",
            generation_method=(
                "all exact base/head surfaces grouped by the same anchored prefix/suffix mask; "
                "complete relevance set computed before evaluation"
            ),
            notes=f"Ambiguity must preserve {len(relevant)} distinct exact base identities.",
        ))
    return select_by_split(candidates, AMBIGUITY_QUOTAS, salt="ambiguity")


def one_rule_rewrites(value: str) -> list[tuple[str, str, str, float]]:
    """Return observed forms that rewrite once into ``value``.

    Each tuple is ``(observed_value, observed_grapheme, catalog_grapheme, cost)``.
    Replacements operate on original target spans and never chain.
    """

    variants: list[tuple[str, str, str, float]] = []
    for observed, catalog, cost in OCR_RULES:
        cursor = 0
        while True:
            position = value.find(catalog, cursor)
            if position < 0:
                break
            candidate = value[:position] + observed + value[position + len(catalog) :]
            if candidate != value:
                variants.append((candidate, observed, catalog, cost))
            cursor = position + 1
    return variants


def build_ocr_gap_rows(
    families: Sequence[Family],
    indexes: VisualIndexes,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for family in families:
        target = family.key
        if not target.isalpha() or not 9 <= len(target) <= 18:
            continue
        selector = int(stable_hash(SEED, "ocr", target)[:8], 16)
        mode = "trailing" if selector % 2 == 0 else "internal"
        if mode == "trailing":
            corrected_fragments = (target[:6],)
            corrected_pattern = Pattern(corrected_fragments, True, False, True)
        else:
            corrected_fragments = (target[:4], target[-3:])
            corrected_pattern = Pattern(corrected_fragments, True, True, True)

        for fragment_index, corrected_fragment in enumerate(corrected_fragments):
            for observed_fragment, observed, catalog, cost in one_rule_rewrites(corrected_fragment):
                raw_fragments = list(corrected_fragments)
                raw_fragments[fragment_index] = observed_fragment
                raw_pattern = Pattern(
                    tuple(raw_fragments),
                    corrected_pattern.anchor_start,
                    corrected_pattern.anchor_end,
                    True,
                )
                query = "...".join(raw_fragments)
                if not raw_pattern.anchor_start:
                    query = "..." + query
                if not raw_pattern.anchor_end:
                    query += "..."
                raw_relevance = indexed_relevance(indexes, mode, raw_pattern)
                corrected_relevance = indexed_relevance(indexes, mode, corrected_pattern)
                relevant = raw_relevance | corrected_relevance
                if (
                    family.key not in corrected_relevance
                    or family.key in raw_relevance
                    or not relevant
                    or len(relevant) > REQUEST_LIMIT
                    or row_split(relevant) is None
                ):
                    continue
                candidates.append(make_row(
                    case_type="positive_ocr_composition",
                    stratum="one_ocr_confusion_plus_gap",
                    query=query,
                    source=family.key,
                    relevant=relevant,
                    pattern=raw_pattern,
                    expected_mode=mode,
                    substitution=f"{observed}>{catalog}@fragment{fragment_index + 1};cost={cost:.2f}",
                    required_reason="visual_gap_grapheme_confusion",
                    generation_method=(
                        "one literal observed-to-catalog grapheme rewrite composed with an explicit gap; "
                        "independent oracle is the union of raw and corrected exact positional matches"
                    ),
                    notes=(
                        f"raw_exact={len(raw_relevance)}; corrected_exact={len(corrected_relevance)}; "
                        "no chained rewrites"
                    ),
                ))
    return select_by_split(candidates, OCR_QUOTAS, salt="ocr-gap")


def build_marker_rows(
    families: Sequence[Family],
    indexes: VisualIndexes,
) -> list[dict[str, str]]:
    # A single star or question mark is intentionally a marker in the current
    # grammar (``\*+`` / ``\?+``).  Dot requires at least two characters and
    # underscore requires at least two.  Keep those boundaries explicit here.
    markers = ("..", ".....", "…", "*", "***", "?", "???", "__", "...__")
    candidates: list[dict[str, str]] = []
    for family in families:
        target = family.key
        if not target.isalpha() or not 9 <= len(target) <= 18:
            continue
        _, pattern = mode_pattern("internal", target, "marker")
        relevant = indexed_relevance(indexes, "internal", pattern)
        if relevant != {family.key}:
            continue
        marker = markers[int(stable_hash(SEED, "marker", target)[:8], 16) % len(markers)]
        query = marker.join(pattern.fragments)
        candidates.append(make_row(
            case_type="positive_marker_grammar",
            stratum="marker_glyph_equivalence",
            query=query,
            source=family.key,
            relevant=relevant,
            pattern=pattern,
            expected_mode="internal",
            evaluation_kind="contract",
            generation_method=(
                "catalog-derived internal mask rendered with one documented explicit marker glyph; "
                "oracle semantics remain the same literal fragments"
            ),
            notes=f"marker={marker.encode('unicode_escape').decode('ascii')}",
        ))
    selected = select_by_split(candidates, MARKER_QUOTAS, salt="marker-glyph")
    represented = {row["notes"].split("=", 1)[-1] for row in selected}
    expected = {marker.encode("unicode_escape").decode("ascii") for marker in markers}
    for missing in sorted(expected - represented):
        replacements = [
            row
            for row in candidates
            if row["notes"].split("=", 1)[-1] == missing and row not in selected
        ]
        replacements.sort(key=lambda row: stable_hash(SEED, "marker-coverage", row["case_id"]))
        if not replacements:
            raise RuntimeError(f"no marker candidate available for {missing}")
        replacement = replacements[0]
        split = replacement["split"]
        counts = Counter(
            row["notes"].split("=", 1)[-1]
            for row in selected
            if row["split"] == split
        )
        victim = next(
            (
                row
                for row in reversed(selected)
                if row["split"] == split
                and counts[row["notes"].split("=", 1)[-1]] > 1
            ),
            None,
        )
        if victim is None:
            raise RuntimeError(f"cannot preserve split quota while adding marker {missing}")
        selected[selected.index(victim)] = replacement
        represented.add(missing)
    if represented != expected:
        raise RuntimeError(
            "marker sample did not cover the complete grammar: "
            f"missing={sorted(expected - represented)}"
        )
    return selected


def build_zero_width_rows(
    families: Sequence[Family],
    indexes: VisualIndexes,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    modes = ("internal", "leading", "trailing")
    for mode in modes:
        candidates: list[dict[str, str]] = []
        for family in families:
            target = family.key
            if not target.isalpha() or not 7 <= len(target) <= 14:
                continue
            if mode == "internal":
                position = 2 + int(stable_hash(SEED, "zero", target)[:4], 16) % (len(target) - 3)
                fragments = (target[:position], target[position:])
                query = "...".join(fragments)
                pattern = Pattern(fragments, True, True, True)
                expected_mode = "internal"
            elif mode == "leading":
                fragments = (target,)
                query = "..." + target
                pattern = Pattern(fragments, False, True, True)
                expected_mode = "leading"
            else:
                fragments = (target,)
                query = target + "..."
                pattern = Pattern(fragments, True, False, True)
                expected_mode = "trailing"
            relevant = indexed_relevance(indexes, mode, pattern)
            if family.key in relevant or len(relevant) > REQUEST_LIMIT:
                continue
            split_keys = relevant | {family.key}
            if row_split(split_keys) is None:
                continue
            candidates.append(make_row(
                case_type="negative_zero_width",
                stratum=f"zero_width_{mode}",
                query=query,
                source=family.key,
                relevant=relevant,
                forbidden=[family.key],
                pattern=pattern,
                expected_mode=expected_mode,
                match_policy="all_relevant_and_forbid_source",
                evaluation_kind="safety",
                required_reason="",
                generation_method=(
                    "marker inserted where the source has zero hidden characters; independent "
                    "oracle requires one hidden character at every explicit gap"
                ),
                notes="The source exact identity is forbidden even when other exact identities satisfy the mask.",
            ))
        rows.extend(select_by_split(candidates, ZERO_WIDTH_QUOTAS, salt=f"zero-{mode}"))
    return rows


def build_short_floor_rows(
    families: Sequence[Family],
    indexes: VisualIndexes,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for family in families:
        target = family.key
        if not target.isalpha() or not 7 <= len(target) <= 16:
            continue
        for visible_width in (3, 4):
            corrected = target[:visible_width]
            for observed_fragment, observed, catalog, cost in one_rule_rewrites(corrected):
                if len(observed_fragment) > 4:
                    continue
                raw_pattern = Pattern((observed_fragment,), True, False, True)
                corrected_pattern = Pattern((corrected,), True, False, True)
                raw_relevance = indexed_relevance(indexes, "trailing", raw_pattern)
                corrected_relevance = indexed_relevance(indexes, "trailing", corrected_pattern)
                if (
                    family.key not in corrected_relevance
                    or family.key in raw_relevance
                    or len(raw_relevance) > REQUEST_LIMIT
                    or row_split(raw_relevance | {family.key}) is None
                ):
                    continue
                candidates.append(make_row(
                    case_type="negative_short_confusion_floor",
                    stratum="short_visible_confusion_floor",
                    query=observed_fragment + "...",
                    source=family.key,
                    relevant=raw_relevance,
                    forbidden=[family.key],
                    pattern=raw_pattern,
                    expected_mode="trailing",
                    match_policy="all_raw_relevant_and_forbid_corrected_source",
                    evaluation_kind="safety",
                    substitution=f"{observed}>{catalog};cost={cost:.2f}",
                    required_reason="",
                    forbidden_reason="visual_gap_grapheme_confusion",
                    generation_method=(
                        "one OCR rewrite would reach the source, but retained visible evidence is "
                        "only three or four characters; direct confusion expansion must remain disabled"
                    ),
                    notes=f"visible_characters={len(observed_fragment)}",
                ))
    return select_by_split(candidates, SHORT_FLOOR_QUOTAS, salt="short-floor")


def build_punctuation_guard_rows(families: Sequence[Family]) -> list[dict[str, str]]:
    punctuation = ("-", ".", "/", ":", "+", "_")
    candidates: list[dict[str, str]] = []
    for family in families:
        target = family.key
        if not target.isalpha() or not 8 <= len(target) <= 16:
            continue
        position = 3 + int(stable_hash(SEED, "punct", target)[:4], 16) % (len(target) - 6)
        mark = punctuation[int(stable_hash(SEED, "punct-mark", target)[:8], 16) % len(punctuation)]
        query = target[:position] + mark + target[position:]
        candidates.append(make_row(
            case_type="negative_non_marker_punctuation",
            stratum="punctuation_marker_collision_guard",
            query=query,
            source=family.key,
            pattern=None,
            expected_decision="not_visual_gap",
            match_policy="no_visual_dispatch",
            evaluation_kind="safety",
            required_reason="",
            confirmation_required=False,
            generation_method=(
                "single punctuation glyph inserted into an exact catalog family; single glyphs "
                "are ordinary spelling punctuation, not hidden-text markers"
            ),
            notes=f"single_non_marker_glyph={mark}",
        ))
    return select_by_split(candidates, PUNCTUATION_QUOTAS, salt="punctuation")


def build_numeric_rows(
    families: Sequence[Family],
    indexes: VisualIndexes,
) -> list[dict[str, str]]:
    positive_candidates: list[dict[str, str]] = []
    guard_candidates: list[dict[str, str]] = []
    for family in families:
        target = family.key
        if not any(character.isdigit() for character in target) or not 7 <= len(target) <= 18:
            continue
        query, pattern = mode_pattern("internal", target, "numeric")
        relevant = indexed_relevance(indexes, "internal", pattern)
        if family.key in relevant and len(relevant) <= REQUEST_LIMIT and row_split(relevant) is not None:
            positive_candidates.append(make_row(
                case_type="positive_numeric_name",
                stratum="cross_mode_numeric_visual_name",
                query=query,
                source=family.key,
                relevant=relevant,
                pattern=pattern,
                expected_mode="internal",
                evaluation_kind="cross_mode",
                generation_method=(
                    "explicit internal mask derived from an exact catalog base containing a digit; "
                    "the digit is name evidence, not inferred strength context"
                ),
                notes="Exercises interaction between visual parsing and numeric product-context extraction.",
            ))

        # Whitespace shorthand containing digits is intentionally outside the
        # marker-free grammar and must stay on the ordinary-search path.
        split_position = next(
            (index for index, character in enumerate(target) if character.isdigit() and index >= 2),
            max(2, len(target) // 2),
        )
        split_position = min(max(2, split_position), len(target) - 2)
        query_guard = target[:split_position] + " " + target[split_position:]
        guard_candidates.append(make_row(
            case_type="negative_numeric_shorthand",
            stratum="cross_mode_numeric_shorthand_guard",
            query=query_guard,
            source=family.key,
            pattern=None,
            expected_decision="not_visual_gap",
            match_policy="no_visual_dispatch",
            evaluation_kind="cross_mode",
            required_reason="",
            confirmation_required=False,
            generation_method=(
                "exact numeric catalog key split with whitespace; digit-bearing shorthand is "
                "excluded from implicit hidden-gap parsing"
            ),
            notes="Confirms that product-strength-like digits do not trigger marker-free visual mode.",
        ))

    return (
        select_by_split(positive_candidates, NUMERIC_POSITIVE_QUOTAS, salt="numeric-positive")
        + select_by_split(guard_candidates, NUMERIC_GUARD_QUOTAS, salt="numeric-guard")
    )


def build_rows(
    families: Sequence[Family],
    indexes: VisualIndexes,
) -> list[dict[str, str]]:
    rows = (
        build_main_positive_rows(families, indexes)
        + build_ambiguity_rows(families, indexes)
        + build_ocr_gap_rows(families, indexes)
        + build_marker_rows(families, indexes)
        + build_zero_width_rows(families, indexes)
        + build_short_floor_rows(families, indexes)
        + build_punctuation_guard_rows(families)
        + build_numeric_rows(families, indexes)
    )
    case_ids = [row["case_id"] for row in rows]
    if len(case_ids) != len(set(case_ids)):
        raise RuntimeError("duplicate deterministic case IDs")
    return sorted(rows, key=lambda row: row["case_id"])


def source_provenance() -> dict[str, Any]:
    if str(PACKAGE) not in sys.path:
        sys.path.insert(0, str(PACKAGE))
    from provenance import DEFAULT_FILE_PATHS, collect_provenance

    paths = dict(DEFAULT_FILE_PATHS)
    paths["generator"] = Path(__file__).relative_to(REPO)
    paths["evaluator"] = EVALUATOR.relative_to(REPO)
    return collect_provenance(REPO, file_paths=paths)


def main() -> None:
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    records = payload.get("records") or []
    if len(records) != 25_066:
        raise SystemExit(f"expected 25,066 catalog records, found {len(records)}")
    families = build_families(records)
    indexes = build_visual_indexes(families)
    rows = build_rows(families, indexes)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)

    by_stratum = Counter(row["stratum"] for row in rows)
    by_split = Counter(row["split"] for row in rows)
    by_kind = Counter(row["evaluation_kind"] for row in rows)
    manifest = {
        "schema_version": 1,
        "dataset_id": "visual_gap_exact_identity_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator_seed": SEED,
        "dataset_file": str(OUTPUT.relative_to(REPO)),
        "dataset_sha256": sha256_path(OUTPUT),
        "rows": len(rows),
        "by_stratum": dict(sorted(by_stratum.items())),
        "by_split": dict(sorted(by_split.items())),
        "by_evaluation_kind": dict(sorted(by_kind.items())),
        "catalog_records": len(records),
        "exact_family_count": len(families),
        "selection_policy": (
            "Catalog and literal protocol only. The generator never imports Algorithm 5/6, "
            "calls the search API, or reads prior result artifacts."
        ),
        "oracle_policy": {
            "identity": "exact compact base-family key from catalog b (fallback n)",
            "surfaces": (
                "exact base key plus independently reconstructed first-token family head when "
                "catalog families share that token and a manufacturer"
            ),
            "matching": (
                "independent ordered literal fragments; each explicit internal/leading/trailing "
                "gap hides at least one target character"
            ),
            "ocr_composition": (
                "union of exact positional matches for the observed fragments and the single "
                "declared observed-to-catalog correction; no chained rewrites"
            ),
            "api_identity_field": "matched_family_key",
            "variant_group_is_never_a_label": True,
        },
        "split_policy": (
            "SHA-256(seed, exact family key) modulo 5; zero is holdout. Every multi-family "
            "row is retained only when all relevant/forbidden/source families share the split."
        ),
        "source_provenance": source_provenance(),
        "ocr_rules": [
            {"observed": observed, "catalog": catalog, "cost": cost}
            for observed, catalog, cost in OCR_RULES
        ],
        "limitations": [
            "This is a deterministic retrospective catalog challenge set, not a blind external set.",
            "The exact-relevance oracle measures literal and declared one-confusion evidence; extra bounded-fuzzy API candidates are reported separately rather than automatically called wrong.",
            "The benchmark evaluates retrieval identity and visual-mode safety, not clinical substitutability.",
        ],
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

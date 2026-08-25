#!/usr/bin/env python3
"""Generate deterministic Algorithm 6 rule-evaluation datasets.

Generation depends only on the frozen catalog, source registries, and literal
hand-audited cases.  It never reads algorithm result files, so failures cannot
be selected out of a regenerated dataset.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from provenance import collect_provenance

GENERATED = PACKAGE / "test_sets" / "generated"
LOCKED = PACKAGE / "test_sets" / "locked"
MANIFESTS = PACKAGE / "test_sets" / "manifests"
CATALOG_PATH = REPO / "app" / "data" / "catalog.json"
ALGORITHM_DIR = REPO / "benchmark_01_legacy" / "master_algorithms"
SOURCE_COMMIT = "d5b0e7efe5c5164635962c74bce12c8668c50d86"
DEPLOYMENT_RECORD_COMMIT = "7ed39d0111a964434742626bddafb0e67c1d8048"
CATALOG_SHA256 = "d234edaa2669d1eeb46b962e7e3e02df52c6f4d2fd3eca7a2fbf3bc7d159fd9c"
GENERATOR_SEED = "algorithm-6-rule-evaluation-v1"

LOCKED_INPUTS = {
    "fair_ocr_412.csv": (
        REPO.parent / "medicine-search-clean" / "benchmark_04_experiments"
        / "data" / "01_ocr_fair" / "test_cases.csv",
        "3ad1a423cadc96b29665a8c600c27eb25bc743a5274f4a2c7917402fe09979bd",
    ),
    "fair_ocr_excluded_52.csv": (
        REPO.parent / "medicine-search-clean" / "benchmark_04_experiments"
        / "data" / "01_ocr_fair" / "excluded_cases.csv",
        "56c52e5d3e69ea9d87547c6a4ae9b010611e06347fa2296e45bce040581ff3ee",
    ),
    "synthetic_clean_66257.csv": (
        REPO.parent / "medicine-search-clean" / "benchmark_04_experiments"
        / "data" / "05_synthetic_clean_core" / "test_cases.csv",
        "65f81b58dee1e7127386652383d2f6a8db1734e832dcbc73f14a9b831678886f",
    ),
}

COMMON_COLUMNS = [
    "case_id",
    "rule_id",
    "case_type",
    "source",
    "generation_method",
    "seed",
    "split",
    "query",
    "product_context",
    "expected_families",
    "forbidden_families",
    "expected_products",
    "expected_decision",
    "expected_mode",
    "match_policy",
    "request_limit",
    "expected_candidate_count",
    "target_family_key",
    "expected_hidden_character_count",
    "expected_visible_coverage",
    "maximum_rank",
    "required_reason",
    "forbidden_reason",
    "confirmation_required",
    "notes",
]

ORDINARY_TYPO_COLUMNS = COMMON_COLUMNS + [
    "evaluation_kind",
    "primary_mutation",
    "mutation_strata",
    "query_length_bucket",
    "source_family_keys",
    "collision_component_id",
    "relevance_count",
    "exact_catalog_query",
]

ORDINARY_TYPO_SEED = "algorithm-6-ordinary-typo-benchmark-v1"
ORDINARY_TYPO_BENCHMARK_QUOTAS = {
    "development": 160,
    "holdout": 40,
}
ORDINARY_TYPO_COLLISION_QUOTAS = {
    "development": 80,
    "holdout": 20,
}
ORDINARY_TYPO_EXACT_GUARD_QUOTAS = {
    "development": 40,
    "holdout": 10,
}

# Horizontal QWERTY neighbors give a narrow, ordinary typo channel without
# importing the medicine-specific E/G, I/E/Y, CL/D, or AL/D OCR registry.
_KEYBOARD_ROWS = ("QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM")
KEYBOARD_NEIGHBORS: dict[str, tuple[str, ...]] = {}
for _keyboard_row in _KEYBOARD_ROWS:
    for _keyboard_index, _keyboard_character in enumerate(_keyboard_row):
        KEYBOARD_NEIGHBORS[_keyboard_character] = tuple(
            _keyboard_row[index]
            for index in (_keyboard_index - 1, _keyboard_index + 1)
            if 0 <= index < len(_keyboard_row)
        )


def compact(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_digest(*parts: object) -> str:
    text = "|".join(str(part) for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def case_id(prefix: str, *parts: object) -> str:
    return f"{prefix}-{stable_digest(GENERATOR_SEED, *parts)[:14].upper()}"


def split_for_family(family_key: str) -> str:
    return "holdout" if int(stable_digest("split", family_key)[:8], 16) % 5 == 0 else "development"


def base_row(**values: object) -> dict[str, str]:
    row = {column: "" for column in COMMON_COLUMNS}
    for key, value in values.items():
        if key not in row:
            raise KeyError(f"unknown case column: {key}")
        if isinstance(value, (list, tuple, set, frozenset)):
            row[key] = ";".join(sorted(str(item) for item in value))
        elif isinstance(value, bool):
            row[key] = "1" if value else "0"
        else:
            row[key] = str(value)
    return row


def write_csv(path: Path, rows: Sequence[dict[str, str]], columns: Sequence[str] = COMMON_COLUMNS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def ordinary_query_length_bucket(query: str) -> str:
    length = len(query)
    if length <= 6:
        return "4-6"
    if length <= 9:
        return "7-9"
    if length <= 12:
        return "10-12"
    return "13-17"


def ordinary_typo_mutations(family: str) -> dict[str, set[str]]:
    """Enumerate the locked ordinary-edit channel for one exact family.

    The channel is deliberately separate from the medicine-specific grapheme
    registry.  Every emitted query is derived from source text only; no search
    output, rank, score, or learned confusion table is consulted.
    """

    mutations: dict[str, set[str]] = defaultdict(set)
    for index, character in enumerate(family):
        deleted = family[:index] + family[index + 1 :]
        if len(deleted) >= 4:
            mutations[deleted].add("deletion")

        duplicated = family[: index + 1] + character + family[index + 1 :]
        if len(duplicated) <= 17:
            mutations[duplicated].add("duplicate_character")

        for neighbor in KEYBOARD_NEIGHBORS.get(character, ()):
            substituted = family[:index] + neighbor + family[index + 1 :]
            if substituted != family:
                mutations[substituted].add("keyboard_neighbor")

        if index + 1 < len(family) and character != family[index + 1]:
            transposed = (
                family[:index]
                + family[index + 1]
                + character
                + family[index + 2 :]
            )
            mutations[transposed].add("adjacent_transposition")
    mutations.pop(family, None)
    return mutations


class DisjointFamilyComponents:
    """Small union-find used to keep every typo collision in one split."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, value: str) -> None:
        self.parent.setdefault(value, value)

    def find(self, value: str) -> str:
        self.add(value)
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, first: str, second: str) -> None:
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root == second_root:
            return
        # Lexicographic parent selection makes the component construction
        # independent of catalog/dictionary iteration order.
        lower, higher = sorted((first_root, second_root))
        self.parent[higher] = lower


def _ordinary_row(
    *,
    evaluation_kind: str,
    primary_mutation: str,
    mutation_strata: Sequence[str],
    source_family_keys: Sequence[str],
    collision_component_id: str,
    relevance_count: int,
    exact_catalog_query: bool,
    **values: object,
) -> dict[str, str]:
    row = base_row(**values)
    row.update({
        "evaluation_kind": evaluation_kind,
        "primary_mutation": primary_mutation,
        "mutation_strata": ";".join(sorted(set(mutation_strata))),
        "query_length_bucket": ordinary_query_length_bucket(row["query"]),
        "source_family_keys": ";".join(sorted(set(source_family_keys))),
        "collision_component_id": collision_component_id,
        "relevance_count": str(relevance_count),
        "exact_catalog_query": "1" if exact_catalog_query else "0",
    })
    return row


def build_ordinary_typo_datasets(
    records: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    """Build a deterministic accuracy benchmark and collision/safety set.

    Relevance is the inverse image of a documented edit channel over every
    eligible exact catalog family.  A query with one relevant family is an
    accuracy-benchmark candidate; a query with multiple relevant families is
    a collision/safety candidate.  Queries that are themselves exact catalog
    families become exact-name guards rather than typo accuracy rows.
    """

    exact_families = {
        compact(record.get("b"))
        for record in records
        if compact(record.get("b"))
    }
    eligible_families = sorted(
        family
        for family in exact_families
        if 5 <= len(family) <= 16 and family.isalpha() and family.isascii()
    )

    # query -> source family -> mutation strata.  This is the independent
    # relevance oracle used by both output files.
    origins_by_query: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for family in eligible_families:
        for query, mutation_strata in ordinary_typo_mutations(family).items():
            origins_by_query[query][family].update(mutation_strata)

    components = DisjointFamilyComponents()
    for family in eligible_families:
        components.add(family)
    for query, origins in origins_by_query.items():
        related = sorted(set(origins) | ({query} if query in exact_families else set()))
        for family in related:
            components.add(family)
        for family in related[1:]:
            components.union(related[0], family)

    members_by_root: dict[str, list[str]] = defaultdict(list)
    for family in sorted(components.parent):
        members_by_root[components.find(family)].append(family)

    component_id_by_family: dict[str, str] = {}
    split_by_family: dict[str, str] = {}
    for members in members_by_root.values():
        canonical_members = tuple(sorted(members))
        component_id = "OTC-" + stable_digest(
            ORDINARY_TYPO_SEED, "collision-component", *canonical_members
        )[:12].upper()
        split = (
            "holdout"
            if int(stable_digest(ORDINARY_TYPO_SEED, "component-split", component_id)[:8], 16) % 5 == 0
            else "development"
        )
        for family in canonical_members:
            component_id_by_family[family] = component_id
            split_by_family[family] = split

    mutation_priority = (
        "deletion",
        "adjacent_transposition",
        "duplicate_character",
        "keyboard_neighbor",
    )

    benchmark_candidates: dict[str, dict[str, list[dict[str, Any]]]] = {
        stratum: {"development": [], "holdout": []}
        for stratum in mutation_priority
    }
    collision_candidates: dict[str, list[dict[str, Any]]] = {
        "development": [],
        "holdout": [],
    }
    exact_guard_candidates: dict[str, list[dict[str, Any]]] = {
        "development": [],
        "holdout": [],
    }

    for query, origin_map in origins_by_query.items():
        origins = tuple(sorted(origin_map))
        all_strata = tuple(sorted({value for values in origin_map.values() for value in values}))
        related_family = query if query in exact_families else origins[0]
        component_id = component_id_by_family[related_family]
        split = split_by_family[related_family]
        candidate = {
            "query": query,
            "origins": origins,
            "strata": all_strata,
            "component_id": component_id,
            "split": split,
        }
        if query in exact_families:
            exact_guard_candidates[split].append(candidate)
        elif len(origins) == 1:
            primary = next(stratum for stratum in mutation_priority if stratum in all_strata)
            candidate["primary"] = primary
            benchmark_candidates[primary][split].append(candidate)
        elif 2 <= len(origins) <= 10:
            collision_candidates[split].append(candidate)

    benchmark_rows: list[dict[str, str]] = []
    used_benchmark_families: set[str] = set()
    used_benchmark_queries: set[str] = set()
    for primary in mutation_priority:
        for split in ("development", "holdout"):
            pool = sorted(
                benchmark_candidates[primary][split],
                key=lambda item: stable_digest(
                    ORDINARY_TYPO_SEED,
                    "benchmark-selection",
                    primary,
                    item["query"],
                    *item["origins"],
                ),
            )
            required = ORDINARY_TYPO_BENCHMARK_QUOTAS[split]
            selected: list[dict[str, Any]] = []
            for item in pool:
                family = item["origins"][0]
                if family in used_benchmark_families or item["query"] in used_benchmark_queries:
                    continue
                selected.append(item)
                used_benchmark_families.add(family)
                used_benchmark_queries.add(item["query"])
                if len(selected) == required:
                    break
            if len(selected) != required:
                raise RuntimeError(
                    f"not enough diverse ordinary typo rows for {primary}/{split}: "
                    f"{len(selected)} != {required}"
                )
            for item in selected:
                family = item["origins"][0]
                benchmark_rows.append(_ordinary_row(
                    evaluation_kind="accuracy_benchmark",
                    primary_mutation=primary,
                    mutation_strata=item["strata"],
                    source_family_keys=item["origins"],
                    collision_component_id=item["component_id"],
                    relevance_count=1,
                    exact_catalog_query=False,
                    case_id=case_id(
                        "TYPO-BENCH", ORDINARY_TYPO_SEED, primary, item["query"], family
                    ),
                    rule_id=f"TYPO-ORDINARY-{primary.upper().replace('_', '-')}",
                    case_type="benchmark",
                    source="catalog-derived exact base families",
                    generation_method=(
                        "inverse relevance under locked deletion/transposition/duplicate/"
                        "horizontal-keyboard edit channel; unique family label fixed before evaluation"
                    ),
                    seed=ORDINARY_TYPO_SEED,
                    split=split,
                    query=item["query"],
                    expected_families=[family],
                    match_policy="any",
                    request_limit=20,
                    confirmation_required=True,
                    notes="metric-only accuracy row; retrieval misses do not become regression-contract failures",
                ))

    safety_rows: list[dict[str, str]] = []

    def select_component_diverse(
        pool: Sequence[dict[str, Any]],
        *,
        required: int,
        salt: str,
    ) -> list[dict[str, Any]]:
        ordered = sorted(
            pool,
            key=lambda item: stable_digest(
                ORDINARY_TYPO_SEED, salt, item["component_id"], item["query"]
            ),
        )
        selected: list[dict[str, Any]] = []
        used_components: set[str] = set()
        for item in ordered:
            if item["component_id"] in used_components:
                continue
            selected.append(item)
            used_components.add(item["component_id"])
            if len(selected) == required:
                return selected
        # Some dense medicine-name neighborhoods contain several useful
        # collisions in one connected component.  Permit a second query only
        # after maximizing component diversity.
        selected_queries = {item["query"] for item in selected}
        for item in ordered:
            if item["query"] in selected_queries:
                continue
            selected.append(item)
            selected_queries.add(item["query"])
            if len(selected) == required:
                return selected
        raise RuntimeError(f"not enough ordinary typo {salt} rows: {len(selected)} != {required}")

    for split in ("development", "holdout"):
        for item in select_component_diverse(
            collision_candidates[split],
            required=ORDINARY_TYPO_COLLISION_QUOTAS[split],
            salt=f"collision-selection-{split}",
        ):
            safety_rows.append(_ordinary_row(
                evaluation_kind="collision_safety",
                primary_mutation="collision",
                mutation_strata=item["strata"],
                source_family_keys=item["origins"],
                collision_component_id=item["component_id"],
                relevance_count=len(item["origins"]),
                exact_catalog_query=False,
                case_id=case_id(
                    "TYPO-COLL", ORDINARY_TYPO_SEED, item["query"], *item["origins"]
                ),
                rule_id="TYPO-ORDINARY-COLLISION-PRESERVE",
                case_type="ambiguity",
                source="catalog-derived exact base collision",
                generation_method=(
                    "all exact families that independently produce the same query under the locked ordinary-edit channel"
                ),
                seed=ORDINARY_TYPO_SEED,
                split=split,
                query=item["query"],
                expected_families=item["origins"],
                match_policy="all",
                request_limit=20,
                maximum_rank=20,
                confirmation_required=True,
                notes="gating safety row; all independently relevant exact families must remain visible",
            ))

        for item in select_component_diverse(
            exact_guard_candidates[split],
            required=ORDINARY_TYPO_EXACT_GUARD_QUOTAS[split],
            salt=f"exact-guard-selection-{split}",
        ):
            safety_rows.append(_ordinary_row(
                evaluation_kind="exact_name_safety",
                primary_mutation="exact_catalog_guard",
                mutation_strata=item["strata"],
                source_family_keys=item["origins"],
                collision_component_id=item["component_id"],
                relevance_count=1,
                exact_catalog_query=True,
                case_id=case_id(
                    "TYPO-EXACT", ORDINARY_TYPO_SEED, item["query"], *item["origins"]
                ),
                rule_id="TYPO-ORDINARY-EXACT-NAME-PROTECT",
                case_type="exact_guard",
                source="catalog-derived exact-name collision",
                generation_method=(
                    "query is an exact catalog family and also one ordinary edit from another family; exact identity wins"
                ),
                seed=ORDINARY_TYPO_SEED,
                split=split,
                query=item["query"],
                expected_families=[item["query"]],
                match_policy="any",
                request_limit=20,
                maximum_rank=1,
                confirmation_required=True,
                notes="gating safety row; an exact catalog family must remain rank one",
            ))

    metadata = {
        "seed": ORDINARY_TYPO_SEED,
        "eligible_exact_families": len(eligible_families),
        "independent_mutated_queries": len(origins_by_query),
        "collision_components": len(members_by_root),
        "edit_channel": [
            "one deletion",
            "one adjacent unequal-character transposition",
            "one duplicated source character",
            "one horizontal QWERTY-neighbor substitution",
        ],
        "family_eligibility": "ASCII alphabetic exact base, compact length 5-16",
        "label_policy": (
            "inverse catalog relevance under the locked edit channel; exact catalog queries become guards; no algorithm output read"
        ),
        "split_policy": (
            "union every family sharing a generated query, include an exact catalog query family, then SHA-256 split the full connected component 80/20"
        ),
        "selection": {
            "benchmark_per_primary_mutation": ORDINARY_TYPO_BENCHMARK_QUOTAS,
            "collision_safety": ORDINARY_TYPO_COLLISION_QUOTAS,
            "exact_name_safety": ORDINARY_TYPO_EXACT_GUARD_QUOTAS,
        },
    }
    return (
        sorted(benchmark_rows, key=lambda row: row["case_id"]),
        sorted(safety_rows, key=lambda row: row["case_id"]),
        metadata,
    )


def literal_assignments(path: Path, names: Iterable[str]) -> dict[str, Any]:
    wanted = set(names)
    found: dict[str, Any] = {}
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        for target in targets:
            if isinstance(target, ast.Name) and target.id in wanted:
                found[target.id] = ast.literal_eval(value)
    missing = wanted - set(found)
    if missing:
        raise RuntimeError(f"missing literal assignments in {path}: {sorted(missing)}")
    return found


def ordered_gap_match(
    target: str,
    fragments: Sequence[str],
    *,
    anchor_start: bool,
    anchor_end: bool,
    explicit: bool,
) -> bool:
    """Independent exact-fragment oracle with one hidden char per explicit gap."""

    if not fragments or any(not fragment for fragment in fragments):
        return False
    minimum_between = 1 if explicit else 0

    def search(index: int, previous_end: int) -> bool:
        fragment = fragments[index]
        start_at = previous_end + (minimum_between if index else 0)
        if index == 0 and anchor_start:
            positions = [0] if target.startswith(fragment) else []
        elif index == len(fragments) - 1 and anchor_end:
            position = len(target) - len(fragment)
            positions = [position] if position >= start_at and target.endswith(fragment) else []
        else:
            positions = []
            cursor = max(0, start_at)
            while True:
                position = target.find(fragment, cursor)
                if position < 0:
                    break
                positions.append(position)
                cursor = position + 1
        for position in positions:
            if index == 0 and explicit and not anchor_start and position < 1:
                continue
            end = position + len(fragment)
            if index == len(fragments) - 1:
                if explicit and not anchor_end and end >= len(target):
                    continue
                return True
            if search(index + 1, end):
                return True
        return False

    return search(0, 0)


@dataclass(frozen=True)
class VisualPattern:
    mode: str
    query: str
    fragments: tuple[str, ...]
    anchor_start: bool
    anchor_end: bool
    explicit: bool = True


def visual_pattern(mode: str, target: str) -> VisualPattern:
    if mode == "internal":
        return VisualPattern(mode, f"{target[:3]}...{target[-3:]}", (target[:3], target[-3:]), True, True)
    if mode == "leading":
        return VisualPattern(mode, f"...{target[-5:]}", (target[-5:],), False, True)
    if mode == "trailing":
        return VisualPattern(mode, f"{target[:5]}...", (target[:5],), True, False)
    if mode == "both_ends":
        middle = len(target) // 2 - 2
        fragment = target[middle : middle + 4]
        return VisualPattern(mode, f"...{fragment}...", (fragment,), False, False)
    if mode == "multiple_internal":
        middle = len(target) // 2 - 1
        fragments = (target[:2], target[middle : middle + 2], target[-2:])
        return VisualPattern(mode, "...".join(fragments), fragments, True, True)
    if mode == "shorthand":
        fragments = (target[:3], target[-3:])
        return VisualPattern(mode, " ".join(fragments), fragments, True, True, False)
    raise ValueError(mode)


def relevance_for_pattern(
    surfaces_by_family: dict[str, tuple[str, ...]],
    pattern: VisualPattern,
) -> set[str]:
    return {
        family
        for family, surfaces in surfaces_by_family.items()
        if any(
            ordered_gap_match(
                surface,
                pattern.fragments,
                anchor_start=pattern.anchor_start,
                anchor_end=pattern.anchor_end,
                explicit=pattern.explicit,
            )
            for surface in surfaces
        )
    }


def build_visual_query_index(
    surfaces_by_family: dict[str, tuple[str, ...]],
) -> dict[str, dict[str, set[str]]]:
    """Index every exact-base/head surface by every generated mask it satisfies.

    This is an independent catalog oracle.  It enumerates surface constraints
    once instead of running the search algorithm or comparing every query with
    every catalog family.
    """

    indexes: dict[str, dict[str, set[str]]] = {
        mode: defaultdict(set)
        for mode in (
            "internal",
            "leading",
            "trailing",
            "both_ends",
            "multiple_internal",
            "shorthand",
        )
    }
    for family, surfaces in surfaces_by_family.items():
        for surface in surfaces:
            if len(surface) >= 7:
                indexes["internal"][f"{surface[:3]}...{surface[-3:]}"].add(family)
            if len(surface) >= 6:
                indexes["leading"][f"...{surface[-5:]}"] .add(family)
                indexes["trailing"][f"{surface[:5]}..."].add(family)
                indexes["shorthand"][f"{surface[:3]} {surface[-3:]}"].add(family)
            if len(surface) >= 6:
                for position in range(1, len(surface) - 4):
                    indexes["both_ends"][f"...{surface[position:position + 4]}..."].add(family)
            if len(surface) >= 8:
                prefix = surface[:2]
                suffix = surface[-2:]
                for position in range(3, len(surface) - 4):
                    middle = surface[position:position + 2]
                    indexes["multiple_internal"][f"{prefix}...{middle}...{suffix}"].add(family)
    return indexes


def build_visual_adversarial(catalog: Any) -> list[dict[str, str]]:
    source = REPO / "benchmark_04_experiments" / "test_algorithm_6_visual_gaps.py"
    values = literal_assignments(
        source,
        {
            "expected_cases",
            "edge_negatives",
            "internal_gap_negatives",
            "collision_patterns",
            "short_confusion_guards",
        },
    )
    surfaces_by_family = {
        family.compact: tuple(dict.fromkeys(
            value for value in (family.compact, family.head_compact) if value
        ))
        for family in catalog.algorithm_5_catalog.rescue_index.families
    }
    rows: list[dict[str, str]] = []
    for query, (expected, mode) in values["expected_cases"].items():
        expected_families = [compact(expected)]
        notes = "Expected identity is the exact matched base family at the API boundary."
        if query == "PANA...OL":
            # The historical test asserted the broad PANADOL variant group.
            # There is no exact PANADOL base in the final catalog.  Re-label
            # this raw pattern with every exact base/head family satisfying the
            # positional evidence, independently of Algorithm 6 output.
            pattern = VisualPattern("internal", query, ("PANA", "OL"), True, True)
            expected_families = sorted(relevance_for_pattern(surfaces_by_family, pattern))
            notes = "Re-oracled from the broad historical PANADOL label to all exact raw-relevant bases."
        rows.append(base_row(
            case_id=case_id("VG-MAN-POS", query, expected),
            rule_id=f"VG-{mode.upper().replace('_', '-')}",
            case_type="positive",
            source=str(source.relative_to(REPO)),
            generation_method="hand-audited catalog-backed hard case",
            seed="manual-final-d5b0e7e",
            split="challenge",
            query=query,
            expected_families=expected_families,
            expected_decision="visual_gap_matches",
            expected_mode=mode,
            match_policy="all",
            maximum_rank=20,
            confirmation_required=True,
            notes=notes,
        ))
    for query, forbidden in values["edge_negatives"].items():
        rows.append(base_row(
            case_id=case_id("VG-MAN-EDGE-NEG", query, forbidden),
            rule_id="VG-EXPLICIT-EDGE-MIN1",
            case_type="negative",
            source=str(source.relative_to(REPO)),
            generation_method="hand-audited explicit-edge zero-hidden-character guard",
            seed="manual-final-d5b0e7e",
            split="challenge",
            query=query,
            forbidden_families=[compact(forbidden)],
            expected_decision="visual_gap_matches",
            confirmation_required=True,
        ))
    for query, forbidden in values["internal_gap_negatives"].items():
        rows.append(base_row(
            case_id=case_id("VG-MAN-INT-NEG", query, forbidden),
            rule_id="VG-EXPLICIT-INTERNAL-MIN1",
            case_type="negative",
            source=str(source.relative_to(REPO)),
            generation_method="hand-audited explicit-internal zero-hidden-character guard",
            seed="manual-final-d5b0e7e",
            split="challenge",
            query=query,
            forbidden_families=[compact(forbidden)],
            expected_decision="visual_gap_matches",
            confirmation_required=True,
        ))
    for query, expected in values["collision_patterns"].items():
        rows.append(base_row(
            case_id=case_id("VG-MAN-COLL", query, *sorted(expected)),
            rule_id="VG-AMBIGUITY-PRESERVE",
            case_type="ambiguity",
            source=str(source.relative_to(REPO)),
            generation_method="real-catalog confusion collision",
            seed="manual-final-d5b0e7e",
            split="challenge",
            query=query,
            expected_families=sorted(expected),
            expected_decision="visual_gap_matches",
            maximum_rank=20,
            confirmation_required=True,
        ))
    for query in values["short_confusion_guards"]:
        rows.append(base_row(
            case_id=case_id("VG-MAN-SHORT", query),
            rule_id="VG-DIRECT-CONFUSION-MIN5",
            case_type="boundary",
            source=str(source.relative_to(REPO)),
            generation_method="one-to-four-visible-character direct-confusion guard",
            seed="manual-final-d5b0e7e",
            split="challenge",
            query=query,
            expected_decision="visual_gap_matches",
            forbidden_reason="visual_gap_grapheme_confusion",
            confirmation_required=True,
        ))
    extra = [
        ("VG-EXPLICIT-INTERNAL-MIN1", "negative", "PANA...DOL", "", "PANADOL", "internal zero-gap"),
        ("VG-REPEATED-OCCURRENCE", "positive", "AT...OL", "ATENOLOL", "", "anchored suffix must try the later repeated occurrence"),
        ("VG-EXACT-BASE-IDENTITY", "positive", "BRU...", "BRUFEN;BRUFENCOLD;BRUFENFLU", "", "broad variant group must retain three exact bases"),
        ("VG-MARKER-FRAGMENT-CAP", "boundary", "IE...GE...YI...EG...DI", "", "", "more than four retained fragments is not parsed as visual gap"),
        ("VG-PERFORMANCE-CAP", "performance", "EEEEEEEEEEEEEEEEEEEEEEEE...", "", "", "24 visible characters; <=512 patterns and loaded latency <2s"),
    ]
    for rule_id, kind, query, expected, forbidden, notes in extra:
        rows.append(base_row(
            case_id=case_id("VG-MAN-EXTRA", rule_id, query),
            rule_id=rule_id,
            case_type=kind,
            source=str(source.relative_to(REPO)),
            generation_method="source-level hard boundary extracted from final regression",
            seed="manual-final-d5b0e7e",
            split="challenge",
            query=query,
            expected_families=expected.split(";") if expected else [],
            forbidden_families=[forbidden] if forbidden else [],
            expected_decision="not_visual_gap" if rule_id == "VG-MARKER-FRAGMENT-CAP" else "visual_gap_matches",
            maximum_rank=20 if expected else "",
            confirmation_required=True,
            notes=notes,
        ))
    return sorted(rows, key=lambda row: row["case_id"])


def build_visual_protocol() -> list[dict[str, str]]:
    """Hard parser, stage, alignment-metric, and integration contracts."""

    rows: list[dict[str, str]] = []

    def add(
        rule_id: str,
        query: str,
        *,
        case_type: str = "positive",
        expected: Sequence[str] = (),
        forbidden: Sequence[str] = (),
        decision: str = "visual_gap_matches",
        mode: str = "internal",
        required_reason: str = "",
        forbidden_reason: str = "",
        target_family: str = "",
        hidden: str = "",
        coverage: str = "",
        candidate_count: str = "",
        notes: str = "",
    ) -> None:
        rows.append(base_row(
            case_id=case_id("VG-PROTO", rule_id, query, *expected, *forbidden),
            rule_id=rule_id,
            case_type=case_type,
            source="protocol-v1 hand-audited boundary",
            generation_method="specification-derived parser/matcher boundary; label fixed before execution",
            seed=GENERATOR_SEED,
            split="challenge",
            query=query,
            expected_families=list(expected),
            forbidden_families=list(forbidden),
            expected_decision=decision,
            expected_mode=mode,
            match_policy="all",
            request_limit=20,
            expected_candidate_count=candidate_count,
            target_family_key=target_family,
            expected_hidden_character_count=hidden,
            expected_visible_coverage=coverage,
            maximum_rank=20 if expected else "",
            required_reason=required_reason,
            forbidden_reason=forbidden_reason,
            # Confirmation is a visual-gap output contract. Boundary rows
            # whose expected decision is not visual are not required to opt in.
            confirmation_required=decision == "visual_gap_matches",
            notes=notes,
        ))

    for marker_name, marker in (
        ("DOT2", ".."),
        ("DOT5", "....."),
        ("ELLIPSIS", "…"),
        ("STAR", "***"),
        ("QUESTION", "???"),
        ("UNDERSCORE", "____"),
        ("MIXED_ADJACENT", "...__"),
    ):
        add(
            f"VG-MARKER-{marker_name}",
            f"AT{marker}OL",
            expected=["ATENOLOL"],
            target_family="ATENOLOL",
            hidden="4",
            coverage="0.5",
            notes="All documented explicit marker spellings must preserve the same internal-gap semantics.",
        )

    add("VG-PARSER-MARKER-ONLY", "...", case_type="boundary", decision="not_visual_gap", mode="")
    add("VG-PARSER-MIN-VISIBLE", "...A...", case_type="boundary", decision="not_visual_gap", mode="")
    add("VG-PARSER-TWO-VISIBLE", "...AT...", case_type="boundary", mode="both_ends")
    add(
        "VG-PARSER-FOUR-FRAGMENTS",
        "R...V...T...I...",
        expected=["RIVOTRIL"],
        mode="trailing",
        target_family="RIVOTRIL",
        hidden="4",
        coverage="0.5",
    )
    add(
        "VG-PARSER-FIVE-FRAGMENTS",
        "R...I...V...O...T...R",
        case_type="boundary",
        decision="not_visual_gap",
        mode="",
    )

    add("VG-SHORTHAND-WHITESPACE", "PANA DOL", expected=["PANADOLADVANCE"], mode="internal")
    add("VG-SHORTHAND-PUNCTUATION-GUARD", "PANA-DOL", case_type="negative", decision="not_visual_gap", mode="")
    add("VG-SHORTHAND-PUNCTUATION-GUARD", "PANA.DOL", case_type="negative", decision="not_visual_gap", mode="")
    add("VG-SHORTHAND-EXACT-MULTIWORD", "PANADOL EXTRA", case_type="negative", decision="not_visual_gap", mode="")

    add("VG-EDGE-COMPACT-ANCHOR", "(...TRIL", expected=["RIVOTRIL"], mode="leading")
    add("VG-EDGE-COMPACT-ANCHOR", "...TRIL)", expected=["RIVOTRIL"], mode="leading")
    add("VG-EDGE-COMPACT-ANCHOR", "RIVO... )", expected=["RIVOTRIL"], mode="trailing")

    add(
        "VG-METRIC-DIRECT-CL-TO-D",
        "CLICY...",
        expected=["DICYNONE"],
        mode="trailing",
        target_family="DICYNONE",
        hidden="4",
        coverage="0.5",
        required_reason="visual_gap_grapheme_confusion",
        notes="Observed CLICY becomes target-visible DICY; four target characters remain hidden.",
    )
    add(
        "VG-METRIC-DIRECT-D-TO-CL",
        "BACTID...",
        expected=["BACTICLOR"],
        mode="trailing",
        target_family="BACTICLOR",
        hidden="2",
        coverage="0.7777777778",
        required_reason="visual_gap_grapheme_confusion",
    )
    add(
        "VG-METRIC-DIRECT-D-TO-CL",
        "...TIDOR",
        expected=["BACTICLOR"],
        mode="leading",
        target_family="BACTICLOR",
        hidden="3",
        coverage="0.6666666667",
        required_reason="visual_gap_grapheme_confusion",
    )

    add("VG-FUZZY-SUBSTITUTION", "AUXMEN...", expected=["AUGMENTIN"], mode="trailing", required_reason="visual_gap_bounded_visible_edit")
    add("VG-FUZZY-DELETION", "AUMEN...", expected=["AUGMENTIN"], mode="trailing", required_reason="visual_gap_bounded_visible_edit")
    add("VG-FUZZY-INSERTION", "AUGXMEN...", expected=["AUGMENTIN"], mode="trailing", required_reason="visual_gap_bounded_visible_edit")
    add(
        "VG-FUZZY-SHARED-BUDGET",
        "AUX...TINX",
        case_type="negative",
        forbidden=["AUGMENTIN"],
        mode="internal",
        notes="Two separate ordinary errors must not pass a query-wide one-edit budget.",
    )

    # Lock the exact relevance/truncation semantics exposed by the historical
    # broad PANADOL group case.
    add(
        "VG-CANDIDATE-COUNT",
        "PANA...OL",
        expected=[
            "PANADOLACUTEHEADCOLD",
            "PANADOLADVANCE",
            "PANADOLCOLDFLUDAY",
            "PANADOLCOLDFLUVAPOURRELEASE",
            "PANADOLEXTRA",
            "PANADOLEXTRAOPTIZORB",
            "PANADOLJOINTER",
            "PANADOLMIGRAINE",
            "PANADOLSINUSRELIEFPE",
            "PANAXPANTHENOL",
        ],
        candidate_count="21",
        notes="All ten exact raw-relevant families fit inside top20; total visual candidates are 21.",
    )
    return sorted(rows, key=lambda row: row["case_id"])


def build_visual_generated(catalog: Any) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    families = catalog.algorithm_5_catalog.rescue_index.families
    surfaces_by_family: dict[str, tuple[str, ...]] = {}
    target_by_family: dict[str, str] = {}
    for family in families:
        surfaces = tuple(dict.fromkeys(
            value for value in (family.compact, family.head_compact) if value
        ))
        if 8 <= len(family.compact) <= 18:
            surfaces_by_family[family.compact] = surfaces
            target_by_family[family.compact] = family.compact

    query_indexes = build_visual_query_index(surfaces_by_family)

    rows: list[dict[str, str]] = []
    used_families: set[str] = set()
    modes = ["internal", "leading", "trailing", "both_ends", "multiple_internal", "shorthand"]
    for mode in modes:
        candidates: list[tuple[str, VisualPattern, set[str]]] = []
        for family, target in target_by_family.items():
            if family in used_families:
                continue
            pattern = visual_pattern(mode, target)
            relevant = set(query_indexes[mode].get(pattern.query, set()))
            if relevant == {family}:
                candidates.append((family, pattern, relevant))
        for split, required in (("development", 36), ("holdout", 12)):
            eligible = [
                item for item in candidates
                if split_for_family(item[0]) == split and item[0] not in used_families
            ]
            eligible.sort(key=lambda item: stable_digest(GENERATOR_SEED, mode, item[0]))
            selected = eligible[:required]
            if len(selected) != required:
                raise RuntimeError(f"not enough unique {mode}/{split} visual targets")
            for family, pattern, relevant in selected:
                used_families.add(family)
                rows.append(base_row(
                    case_id=case_id("VG-GEN", mode, family, pattern.query),
                    rule_id=f"VG-{mode.upper().replace('_', '-')}",
                    case_type="positive",
                    source="catalog-derived",
                    generation_method="SHA-256-stratified exact-base mask; unique catalog relevance computed before evaluation",
                    seed=GENERATOR_SEED,
                    split=split,
                    query=pattern.query,
                    expected_families=sorted(relevant),
                    expected_decision="visual_gap_matches",
                    expected_mode="internal" if mode in {"multiple_internal", "shorthand"} else mode,
                    maximum_rank=20,
                    confirmation_required=True,
                    notes=f"source_exact_family={family}; visible_mode={mode}",
                ))

    # Independently generated ambiguity masks.  These are not sampled from
    # algorithm output; grouping uses exact catalog prefix/suffix evidence.
    collision_rows: list[dict[str, str]] = []
    groups = [
        (query, families_set)
        for query, families_set in query_indexes["internal"].items()
        if 2 <= len(families_set) <= 20
    ]
    groups.sort(key=lambda item: stable_digest("visual-collision", item[0]))
    for query, relevant in groups[:40]:
        collision_rows.append(base_row(
            case_id=case_id("VG-GEN-COLL", query, *sorted(relevant)),
            rule_id="VG-AMBIGUITY-PRESERVE",
            case_type="ambiguity",
            source="catalog-derived",
            generation_method="group exact bases by the same anchored three-character prefix/suffix mask",
            seed=GENERATOR_SEED,
            split="challenge",
            query=query,
            expected_families=sorted(relevant),
            expected_decision="visual_gap_matches",
            expected_mode="internal",
            maximum_rank=20,
            confirmation_required=True,
            notes=f"independent_relevance_count={len(relevant)}",
        ))
    return sorted(rows, key=lambda row: row["case_id"]), sorted(collision_rows, key=lambda row: row["case_id"])


def direct_variants(query: str, rules: Sequence[tuple[str, str, float]], depth: int) -> dict[str, float]:
    """Apply rules to original spans without transitive rewriting of output."""

    results: dict[str, float] = {query: 0.0}

    def walk(position: int, output: str, cost: float, used: int) -> None:
        if position >= len(query):
            known = results.get(output)
            if known is None or cost < known:
                results[output] = cost
            return
        walk(position + 1, output + query[position], cost, used)
        if used >= depth:
            return
        for source, target, rule_cost in rules:
            if query.startswith(source, position):
                walk(
                    position + len(source),
                    output + target,
                    cost + float(rule_cost),
                    used + 1,
                )

    walk(0, "", 0.0, 0)
    results.pop(query, None)
    return results


def build_ocr_adversarial() -> list[dict[str, str]]:
    source = REPO / "benchmark_04_experiments" / "test_algorithm_6_ocr_confusions.py"
    values = literal_assignments(
        source,
        {
            "positives",
            "locked_regressions",
            "clean_and_fair_regressions",
            "exact_guards",
            "ambiguous_rewrites",
        },
    )
    rows: list[dict[str, str]] = []
    for label, cases in (
        ("hard", values["positives"]),
        ("locked", values["locked_regressions"]),
        ("clean_fair", values["clean_and_fair_regressions"]),
    ):
        for query, expected, maximum_rank in cases:
            rows.append(base_row(
                case_id=case_id("OCR-MAN-POS", label, query, expected),
                rule_id="OCR-REGISTRY-RETRIEVAL" if label == "hard" else "OCR-CLEAN-SAFETY-GUARD",
                case_type="positive" if label == "hard" else "regression",
                source=str(source.relative_to(REPO)),
                generation_method=f"hand-audited {label} regression",
                seed="manual-final-d5b0e7e",
                split="challenge" if label == "hard" else "regression",
                query=query,
                expected_families=[compact(expected)],
                maximum_rank=maximum_rank,
                confirmation_required=True,
            ))
    for query in values["exact_guards"]:
        rows.append(base_row(
            case_id=case_id("OCR-EXACT", query),
            rule_id="OCR-EXACT-NAME-PROTECT",
            case_type="negative",
            source=str(source.relative_to(REPO)),
            generation_method="real exact-family collision guard",
            seed="manual-final-d5b0e7e",
            split="challenge",
            query=query,
            expected_families=[compact(query)],
            maximum_rank=1,
            confirmation_required=True,
        ))
    for query, expected in values["ambiguous_rewrites"]:
        rows.append(base_row(
            case_id=case_id("OCR-AMB", query, *sorted(expected)),
            rule_id="OCR-GLOBAL-UNIQUE-PROMOTION",
            case_type="ambiguity",
            source=str(source.relative_to(REPO)),
            generation_method="noncatalog query one direct rewrite from two real families",
            seed="manual-final-d5b0e7e",
            split="challenge",
            query=query,
            expected_families=sorted(expected),
            maximum_rank=20,
            forbidden_reason="bounded_grapheme_confusion_correction",
            confirmation_required=True,
        ))
    rows.append(base_row(
        case_id="OCR-NONTRANS-IARDX-GARDX",
        rule_id="OCR-NONTRANSITIVE-SPANS",
        case_type="boundary",
        source=str(source.relative_to(REPO)),
        generation_method="direct source-level variant enumeration",
        seed="manual-final-d5b0e7e",
        split="challenge",
        query="IARDX",
        forbidden_families=["GARDX"],
        notes="I->E and E->G must not compose on one original character.",
        expected_decision="source_function",
    ))
    rows.append(base_row(
        case_id="OCR-LENGTH-CAP-120",
        rule_id="OCR-MAX-INPUT-LENGTH",
        case_type="boundary",
        source=str(source.relative_to(REPO)),
        generation_method="direct source-level variant enumeration",
        seed="manual-final-d5b0e7e",
        split="challenge",
        query="IEYG" * 30,
        expected_decision="source_function",
        notes="Inputs above 24 characters must return zero direct variants in under 100 ms.",
    ))
    return sorted(rows, key=lambda row: row["case_id"])


def build_ocr_generated(catalog: Any, rules: Sequence[tuple[str, str, float]]) -> list[dict[str, str]]:
    family_keys = {
        family.compact
        for family in catalog.algorithm_5_catalog.rescue_index.families
        if 4 <= len(family.compact) <= 24
    }
    rows: list[dict[str, str]] = []
    used: set[tuple[str, str, str]] = set()
    for source, target, cost in rules:
        candidates: list[tuple[str, str]] = []
        for family in family_keys:
            start = 0
            while True:
                position = family.find(target, start)
                if position < 0:
                    break
                query = family[:position] + source + family[position + len(target):]
                start = position + 1
                if query == family or query in family_keys or not (4 <= len(query) <= 24):
                    continue
                variants = direct_variants(query, rules, 1)
                exact = {key: value for key, value in variants.items() if key in family_keys}
                if not exact:
                    continue
                minimum = min(exact.values())
                minima = {key for key, value in exact.items() if abs(value - minimum) <= 1e-9}
                if minima == {family}:
                    candidates.append((family, query))
        candidates = sorted(
            set(candidates),
            key=lambda item: stable_digest("ocr", source, target, item[0], item[1]),
        )
        for split, required in (("development", 8), ("holdout", 2)):
            chosen = [item for item in candidates if split_for_family(item[0]) == split][:required]
            for family, query in chosen:
                marker = (source, target, family)
                if marker in used:
                    continue
                used.add(marker)
                rows.append(base_row(
                    case_id=case_id("OCR-GEN1", source, target, family, query),
                    rule_id=f"OCR-DIRECT-{compact(source)}-TO-{compact(target)}",
                    case_type="positive",
                    source="catalog-derived",
                    generation_method="invert one directional registry rule; retain only globally unique minimum-cost exact target",
                    seed=GENERATOR_SEED,
                    split=split,
                    query=query,
                    expected_families=[family],
                    maximum_rank=20,
                    confirmation_required=True,
                    notes=f"observed={source};catalog={target};cost={cost}",
                ))

    # Two-operation cases are generated independently of runtime output.
    double_candidates: list[tuple[str, str, float]] = []
    for family in sorted(family_keys):
        inverse_once: set[str] = set()
        for source, target, _ in rules:
            for match in re.finditer(re.escape(target), family):
                inverse_once.add(family[:match.start()] + source + family[match.end():])
        for intermediate in inverse_once:
            for source, target, _ in rules:
                for match in re.finditer(re.escape(target), intermediate):
                    query = intermediate[:match.start()] + source + intermediate[match.end():]
                    if query == family or query in family_keys or not (6 <= len(query) <= 24):
                        continue
                    variants = direct_variants(query, rules, 2)
                    exact = {key: value for key, value in variants.items() if key in family_keys and value <= 1.40 + 1e-9}
                    if not exact:
                        continue
                    minimum = min(exact.values())
                    minima = {key for key, value in exact.items() if abs(value - minimum) <= 1e-9}
                    if minima == {family}:
                        double_candidates.append((family, query, minimum))
    double_candidates = sorted(
        set(double_candidates),
        key=lambda item: stable_digest("ocr-depth2", item[0], item[1]),
    )
    selected: list[tuple[str, str, float]] = []
    selected.extend([item for item in double_candidates if split_for_family(item[0]) == "development"][:32])
    selected.extend([item for item in double_candidates if split_for_family(item[0]) == "holdout"][:8])
    for family, query, cost in selected:
        rows.append(base_row(
            case_id=case_id("OCR-GEN2", family, query),
            rule_id="OCR-DIRECT-DEPTH2",
            case_type="positive",
            source="catalog-derived",
            generation_method="invert two directional rules; globally unique minimum exact target; total cost <=1.40",
            seed=GENERATOR_SEED,
            split=split_for_family(family),
            query=query,
            expected_families=[family],
            maximum_rank=20,
            confirmation_required=True,
            notes=f"minimum_direct_cost={cost:.2f}",
        ))
    return sorted(rows, key=lambda row: row["case_id"])


def deterministic_product_cases(records: Sequence[dict[str, Any]]) -> list[tuple[str, str, str]]:
    families: dict[str, str] = {}
    for record in records:
        family = compact(record.get("b"))
        strength = str(record.get("st") or "").strip()
        if not (4 <= len(family) <= 12 and family.isalpha() and re.search(r"\d", strength)):
            continue
        families.setdefault(family, strength)
    def mutate(name: str) -> str:
        index = len(name) // 2
        replacement = "A" if name[index] != "A" else "O"
        return name[:index] + replacement + name[index + 1:]
    return sorted(
        ((mutate(family), family, strength) for family, strength in families.items()),
        key=lambda row: hashlib.sha256("|".join(row).encode()).hexdigest(),
    )[:200]


def build_product_context_200(records: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for query, expected, strength in deterministic_product_cases(records):
        rows.append(base_row(
            case_id=case_id("PC-200", query, expected, strength),
            rule_id="PC-EXACT-CONTEXT-CROSS-FAMILY",
            case_type="regression",
            source="catalog-derived locked August-11 method",
            generation_method="middle-character mutation; first strength per eligible exact base; SHA-256 sort; first 200",
            seed="21e0992188f27364582660b8072837c9d5d0fd3bcb3bbbf9c41bf7e471fd7ff5",
            split="locked",
            query=query,
            product_context=strength,
            expected_families=[expected],
            expected_decision="product_context_selection",
            maximum_rank=1,
            confirmation_required=True,
        ))
    return rows


def classify_test(name: str) -> tuple[str, str]:
    value = name.lower()
    if "visual_gap" in value or "visual_marker" in value:
        return "visual_gap", "VG-PRODUCT-BOUNDARY"
    if "alias" in value or "numbered_brand" in value or "numeric_word_brand" in value:
        return "numeric_brand_alias", "PC-NUMERIC-BRAND-ALIASES"
    if "short_prefix" in value or "x_plus" in value or "two_character_prefix" in value:
        return "short_prefix", "PC-SHORT-PREFIX"
    if "release" in value:
        return "release", "PC-RELEASE"
    if "route" in value or "injection" in value:
        return "route", "PC-ROUTE-CONTAINER"
    if any(token in value for token in ("package", "pack", "multipack", "dose_count", "tablets_returns")):
        return "package", "PC-PACKAGE"
    if any(token in value for token in ("concentration", "denominator", "combination", "ratio", "strength", "mass", "percent", "micro", "iu", "decimal", "zero_dose")):
        return "strength", "PC-STRENGTH"
    if any(token in value for token in ("form", "tablet", "capsule", "chew", "effervescent", "vial", "ampoule")):
        return "form_container", "PC-FORM-CONTAINER"
    if "tie" in value or "duplicate" in value:
        return "identity_ties", "PC-TIES-IDENTITY"
    if "reorder" in value or "family" in value or "javaki" in value or "presentation" in value:
        return "family_admission", "PC-FAMILY-ADMISSION"
    return "product_context_other", "PC-GENERAL"


def build_unit_test_inventory() -> list[dict[str, str]]:
    columns = ["test_id", "file", "line", "class", "method", "layer", "rule_id", "source_hash"]
    rows: list[dict[str, str]] = []
    for relative in ("app/test_product_context_reranker.py", "app/test_product_context_hardening.py"):
        path = REPO / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        source_hash = sha256_path(path)
        for class_node in [node for node in tree.body if isinstance(node, ast.ClassDef)]:
            for node in class_node.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                    layer, rule_id = classify_test(node.name)
                    rows.append({
                        "test_id": f"{class_node.name}.{node.name}",
                        "file": relative,
                        "line": str(node.lineno),
                        "class": class_node.name,
                        "method": node.name,
                        "layer": layer,
                        "rule_id": rule_id,
                        "source_hash": source_hash,
                    })
    rows.sort(key=lambda row: row["test_id"])
    return rows


def build_api_inventory() -> list[dict[str, str]]:
    # One row per distinct black-box contract group. Some rows execute several
    # catalog probes in the source script; the final script labels 38 scenarios.
    scenarios = [
        ("runtime", "GET", "/api/runtime", "", "", "API-RUNTIME"),
        ("health", "GET", "/health", "", "", "API-HEALTH"),
        ("javaki_5mg", "POST", "/api/search", "javaki", "5mg", "PC-EXACT-CONTEXT-CROSS-FAMILY"),
        ("brufen_600_ties", "POST", "/api/search", "brufen", "600", "PC-TIES-IDENTITY"),
        ("brufen_600_tab", "POST", "/api/search", "brufen", "600 tab", "PC-UNITLESS"),
        ("brufen_600_comma_tab", "POST", "/api/search", "brufen", "600, tab", "PC-NUMERIC-NORMALIZATION"),
        ("brufen_30_tab", "POST", "/api/search", "brufen", "30 tab", "PC-PACKAGE"),
        ("x_500_tab", "POST", "/api/search", "x", "500 tab", "PC-SHORT-PREFIX"),
        ("x_600_tab", "POST", "/api/search", "x", "600 tab", "PC-SHORT-PREFIX"),
        ("xanax_conflict", "POST", "/api/search", "xanax", "500 mg tab", "PC-CONFLICT-ABSTAIN"),
        ("augmentin_vial", "POST", "/api/search", "augmentin", "1.2 g vial", "PC-ROUTE-CONTAINER"),
        ("augmentin_denominator_conflict", "POST", "/api/search", "augmentin", "156 mg/10 ml suspension", "PC-CONFLICT-ABSTAIN"),
        ("leil_presentation", "POST", "/api/search", "leal", "100 g cream", "PC-QUALIFIED-PRESENTATION"),
        ("argotex_presentation", "POST", "/api/search", "argatex", "50 g cream", "PC-QUALIFIED-PRESENTATION"),
        ("weak_presentation", "POST", "/api/search", "argatex", "50", "PC-WEAK-NO-REORDER"),
        ("d3_exact", "POST", "/api/search", "D3", "", "PC-NUMERIC-BRAND-ALIASES"),
        ("3_fly", "POST", "/api/search", "3 FLY", "", "PC-NUMERIC-BRAND-ALIASES"),
        ("1_2_3", "POST", "/api/search", "1 2 3", "", "PC-NUMERIC-BRAND-ALIASES"),
        ("1_2_3_20_tab", "POST", "/api/search", "1 2 3 20 tab", "", "PC-NUMERIC-BRAND-ALIASES"),
        ("3_fly_600_tab", "POST", "/api/search", "3 FLY 600 tab", "", "PC-NUMERIC-BRAND-ALIASES"),
        ("longest_brand_alias", "POST", "/api/search", "1 2 3 ONE TWO THREE 20 tab", "", "PC-NUMERIC-BRAND-ALIASES"),
        ("unknown_alias_suffix", "POST", "/api/search", "1 2 3 junk 20 tab", "", "PC-NUMERIC-BRAND-ALIASES"),
        ("ocr_registry_group", "POST", "/api/search", "OMGPRAZOLG|OMIPRAZOLI|ACLCLOH|DKDINE", "", "OCR-REGISTRY-RETRIEVAL"),
        ("strict_both_edge_group", "POST", "/api/search", "...CLICY...|...BACTID...|...ALEPI...", "", "VG-EXPLICIT-EDGE-MIN1"),
        ("suffix_positive_group", "POST", "/api/search", "CLICY...|BACTID...|ALEPI...", "", "VG-TRAILING"),
        ("strict_panadol_edge", "POST", "/api/search", "...PANADOL", "", "VG-EXPLICIT-EDGE-MIN1"),
        ("visual_product", "POST", "/api/search", "BRU...", "600 mg tab", "VG-PRODUCT-BOUNDARY"),
        ("short_visual_no_prefix", "POST", "/api/search", "BR...", "10 mg tab", "VG-PRODUCT-BOUNDARY"),
        ("numeric_visual_no_alias", "POST", "/api/search", "3__FLY", "", "VG-PRODUCT-BOUNDARY"),
        ("visual_number_no_context", "POST", "/api/search", "VIT__3", "", "VG-PRODUCT-BOUNDARY"),
        ("duplicate_product_ids", "POST", "/api/search", "citicoline", "500 mg cap", "PC-TIES-IDENTITY"),
        ("attached_percent", "POST", "/api/search", "econazole", "1% spray", "PC-STRENGTH"),
    ]
    columns = ["scenario_id", "method", "path", "query", "product_context", "rule_id", "source", "reported_suite_count"]
    return [
        {
            "scenario_id": scenario_id,
            "method": method,
            "path": path,
            "query": query,
            "product_context": context,
            "rule_id": rule_id,
            "source": "benchmark_04_experiments/test_algorithm_6_api_hardening.py",
            "reported_suite_count": "38",
        }
        for scenario_id, method, path, query, context, rule_id in scenarios
    ]


def load_algorithm6() -> Any:
    sys.path.insert(0, str(ALGORITHM_DIR))
    import algorithm_6_consensus_search as algorithm_6  # type: ignore
    return algorithm_6


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def copy_locked_inputs() -> list[dict[str, Any]]:
    records = []
    LOCKED.mkdir(parents=True, exist_ok=True)
    for filename, (source, expected_hash) in LOCKED_INPUTS.items():
        if not source.exists():
            raise FileNotFoundError(source)
        observed = sha256_path(source)
        if observed != expected_hash:
            raise RuntimeError(f"locked source hash mismatch for {source}: {observed}")
        destination = LOCKED / filename
        shutil.copy2(source, destination)
        copied = sha256_path(destination)
        if copied != expected_hash:
            raise RuntimeError(f"copied hash mismatch for {destination}: {copied}")
        with destination.open("r", encoding="utf-8-sig", newline="") as handle:
            row_count = sum(1 for _ in csv.reader(handle)) - 1
        records.append({
            "file": str(destination.relative_to(REPO)),
            "source": str(source),
            "sha256": copied,
            "rows": row_count,
            "bytes": destination.stat().st_size,
        })
    return records


def main() -> None:
    run_provenance = collect_provenance(REPO)
    for directory in (GENERATED, LOCKED, MANIFESTS):
        directory.mkdir(parents=True, exist_ok=True)
    if sha256_path(CATALOG_PATH) != CATALOG_SHA256:
        raise RuntimeError("catalog hash differs from the locked final catalog")

    algorithm_6 = load_algorithm6()
    catalog = algorithm_6.prepare_catalog()
    rules = tuple(catalog.algorithm_5_module.GRAPHEME_CONFUSION_RULES)
    catalog_records = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["records"]

    visual_adversarial = build_visual_adversarial(catalog)
    visual_protocol = build_visual_protocol()
    visual_generated, visual_collisions = build_visual_generated(catalog)
    ocr_adversarial = build_ocr_adversarial()
    ocr_generated = build_ocr_generated(catalog, rules)
    ordinary_typo_benchmark, ordinary_typo_safety, ordinary_typo_metadata = (
        build_ordinary_typo_datasets(catalog_records)
    )
    product_200 = build_product_context_200(catalog_records)
    unit_inventory = build_unit_test_inventory()
    api_inventory = build_api_inventory()

    outputs: list[tuple[Path, Sequence[dict[str, str]], Sequence[str]]] = [
        (GENERATED / "visual_gap_adversarial.csv", visual_adversarial, COMMON_COLUMNS),
        (GENERATED / "visual_gap_protocol.csv", visual_protocol, COMMON_COLUMNS),
        (GENERATED / "visual_gap_catalog_generated.csv", visual_generated, COMMON_COLUMNS),
        (GENERATED / "visual_gap_catalog_collisions.csv", visual_collisions, COMMON_COLUMNS),
        (GENERATED / "ocr_grapheme_adversarial.csv", ocr_adversarial, COMMON_COLUMNS),
        (GENERATED / "ocr_grapheme_catalog_generated.csv", ocr_generated, COMMON_COLUMNS),
        (
            GENERATED / "ordinary_typo_catalog_benchmark.csv",
            ordinary_typo_benchmark,
            ORDINARY_TYPO_COLUMNS,
        ),
        (
            GENERATED / "ordinary_typo_collision_safety.csv",
            ordinary_typo_safety,
            ORDINARY_TYPO_COLUMNS,
        ),
        (GENERATED / "product_context_200.csv", product_200, COMMON_COLUMNS),
        (GENERATED / "unit_test_inventory.csv", unit_inventory, list(unit_inventory[0])),
        (GENERATED / "api_scenario_inventory.csv", api_inventory, list(api_inventory[0])),
    ]
    file_records = []
    for path, rows, columns in outputs:
        write_csv(path, rows, columns)
        file_records.append({
            "file": str(path.relative_to(REPO)),
            "sha256": sha256_path(path),
            "rows": len(rows),
            "bytes": path.stat().st_size,
        })
    locked_records = copy_locked_inputs()

    cases_json = json.dumps(
        deterministic_product_cases(catalog_records),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    product_cases_hash = hashlib.sha256(cases_json).hexdigest()
    if product_cases_hash != "21e0992188f27364582660b8072837c9d5d0fd3bcb3bbbf9c41bf7e471fd7ff5":
        raise RuntimeError(f"product 200 sample hash mismatch: {product_cases_hash}")

    manifest = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": str(Path(__file__).relative_to(REPO)),
        "generator_sha256": sha256_path(Path(__file__)),
        "generator_seed": GENERATOR_SEED,
        "source_commit_expected": SOURCE_COMMIT,
        "deployment_record_commit": DEPLOYMENT_RECORD_COMMIT,
        "worktree_head": git_output("rev-parse", "HEAD"),
        "source_provenance": run_provenance,
        "catalog": {
            "path": str(CATALOG_PATH.relative_to(REPO)),
            "sha256": sha256_path(CATALOG_PATH),
            "product_rows": len(catalog_records),
            "algorithm6_family_count": len(catalog.algorithm_5_catalog.rescue_index.families),
        },
        "split_policy": (
            "Visual sets: SHA-256(exact family key) modulo 5. Ordinary typo sets: "
            "SHA-256 over the complete query-collision connected component. Zero is "
            "holdout; related families cannot cross splits."
        ),
        "selection_policy": "Catalog/source only; no algorithm outputs are read during generation",
        "generated_files": file_records,
        "locked_files": locked_records,
        "ordinary_typo": ordinary_typo_metadata,
        "product_200_cases_sha256": product_cases_hash,
        "grapheme_registry": [
            {"observed": observed, "catalog": target, "cost": cost}
            for observed, target, cost in rules
        ],
    }
    manifest_path = MANIFESTS / "generation_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "manifest": str(manifest_path.relative_to(REPO)),
        "manifest_sha256": sha256_path(manifest_path),
        "generated_rows": {record["file"]: record["rows"] for record in file_records},
        "locked_rows": {record["file"]: record["rows"] for record in locked_records},
    }, indent=2))


if __name__ == "__main__":
    main()

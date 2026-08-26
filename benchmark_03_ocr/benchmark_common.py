#!/usr/bin/env python3
"""Shared, dependency-light utilities for the Data 3 OCR benchmark."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence


BENCHMARK_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BENCHMARK_DIR.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
DEFAULT_DATASET_ROOT = WORKSPACE_ROOT / "data3 (RxHandBD)"
DEFAULT_CATALOG_PATH = PROJECT_ROOT / "data" / "canonical_candidates.csv"
DEFAULT_DATA_DIR = BENCHMARK_DIR / "data" / "01_rxhandbd"
DEFAULT_RESULTS_DIR = BENCHMARK_DIR / "results" / "01_rxhandbd"
DEFAULT_ARTIFACTS_DIR = BENCHMARK_DIR / "artifacts" / "01_rxhandbd"

CONTEXT_TOKENS = {
    "AMP", "AMPOULE", "AMPOULES", "CAP", "CAPS", "CAPSULE", "CAPSULES",
    "CREAM", "DROP", "DROPS", "DS", "FORTE", "G", "GEL", "GM", "INJ",
    "INJECTION", "IU", "L", "MG", "MCG", "ML", "OINT", "OINTMENT",
    "ORAL", "PLUS", "SACHET", "SACHETS", "SR", "SUSP", "SUSPENSION",
    "SW", "SYRUP", "TAB", "TABS", "TABLET", "TABLETS", "VIAL", "VIALS",
    "XR",
}
NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?(?:MG|MCG|G|GM|ML|L|IU|%)?$")


def repository_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


@dataclass(frozen=True)
class DatasetRow:
    image_id: str
    ground_truth_raw: str
    split: str
    image_path: Path


@dataclass(frozen=True)
class CatalogFamily:
    key: str
    name: str
    aliases: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    ingredients: tuple[str, ...]


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^0-9A-Za-z]+", " ", text.upper())
    return re.sub(r"\s+", " ", text).strip()


def compact_text(value: object) -> str:
    return re.sub(r"[^0-9A-Z]+", "", normalize_text(value))


def medicine_head(value: object) -> str:
    """Remove only obvious trailing form/strength context from a label."""

    tokens = normalize_text(value).split()
    while len(tokens) > 1 and (tokens[-1] in CONTEXT_TOKENS or NUMBER_RE.fullmatch(tokens[-1])):
        tokens.pop()
    return " ".join(tokens)


def levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    if len(left) > len(right):
        left, right = right, left
    previous = list(range(len(left) + 1))
    for row_index, right_char in enumerate(right, 1):
        current = [row_index]
        for col_index, left_char in enumerate(left, 1):
            current.append(min(
                current[-1] + 1,
                previous[col_index] + 1,
                previous[col_index - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def normalized_edit_distance(left: object, right: object) -> float:
    left_key = compact_text(left)
    right_key = compact_text(right)
    denominator = max(len(right_key), 1)
    return levenshtein(left_key, right_key) / denominator


def similarity(left: object, right: object) -> float:
    left_key = compact_text(left)
    right_key = compact_text(right)
    denominator = max(len(left_key), len(right_key), 1)
    return 1.0 - (levenshtein(left_key, right_key) / denominator)


def difficulty_for_distance(distance: float, *, exact: bool = False, empty: bool = False) -> str:
    if empty:
        return "EMPTY"
    if exact:
        return "EXACT"
    if distance <= 0.20:
        return "EASY"
    if distance <= 0.40:
        return "MEDIUM"
    if distance <= 0.60:
        return "HARD"
    return "EXTREME_REVIEW"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: Path, rows: Iterable[dict[str, object]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(*parts: object, length: int = 20) -> str:
    text = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def load_dataset_rows(dataset_root: Path = DEFAULT_DATASET_ROOT) -> list[DatasetRow]:
    ml_root = dataset_root / "RxHandBD-ML"
    layouts = (
        ("train", ml_root / "Train_Label.csv", ml_root / "Train_Set"),
        ("test", ml_root / "Test_Labels.csv", ml_root / "Test_Set"),
    )
    rows: list[DatasetRow] = []
    for split, label_path, image_dir in layouts:
        for row in read_csv(label_path):
            image_id = str(row.get("Images") or "").strip()
            ground_truth = str(row.get("Text") or "").strip()
            if image_id:
                rows.append(DatasetRow(image_id, ground_truth, split, image_dir / image_id))
    return rows


def load_catalog_families(catalog_path: Path = DEFAULT_CATALOG_PATH) -> list[CatalogFamily]:
    grouped: dict[str, dict[str, set[str] | str]] = {}
    for row in read_csv(catalog_path):
        family_name = str(row.get("base_group_key") or row.get("commercial_name_en") or "").strip()
        family_key = compact_text(family_name)
        if not family_key:
            continue
        item = grouped.setdefault(family_key, {
            "name": family_name,
            "aliases": set(),
            "candidate_ids": set(),
            "ingredients": set(),
        })
        aliases = item["aliases"]
        assert isinstance(aliases, set)
        for value in (
            family_name,
            row.get("commercial_name_en"),
            row.get("commercial_name_en_norm"),
        ):
            normalized = normalize_text(value)
            if normalized:
                aliases.add(normalized)
        candidate_ids = item["candidate_ids"]
        assert isinstance(candidate_ids, set)
        if row.get("candidate_id"):
            candidate_ids.add(str(row["candidate_id"]))
        ingredients = item["ingredients"]
        assert isinstance(ingredients, set)
        if row.get("ingredient_key"):
            ingredients.add(str(row["ingredient_key"]))
    return [
        CatalogFamily(
            key=key,
            name=str(item["name"]),
            aliases=tuple(sorted(item["aliases"])),
            candidate_ids=tuple(sorted(item["candidate_ids"])),
            ingredients=tuple(sorted(item["ingredients"])),
        )
        for key, item in sorted(grouped.items())
    ]


def catalog_alias_index(families: Sequence[CatalogFamily]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for family in families:
        for alias in family.aliases:
            key = compact_text(alias)
            if key:
                index.setdefault(key, set()).add(family.key)
    return index


def batched(values: Sequence[DatasetRow], size: int) -> Iterator[Sequence[DatasetRow]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]

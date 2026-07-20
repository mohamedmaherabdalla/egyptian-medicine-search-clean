#!/usr/bin/env python3
"""Prepare unique DrugEye query keys for the V2 live benchmark."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


DATASET_DIR = Path(__file__).resolve().parent
DATASET_PATH = DATASET_DIR / "data" / "test_cases.csv"
RESULTS_DIR = DATASET_DIR / "artifacts" / "04_drugeye"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write unique DrugEye V2 queries as TSV.")
    parser.add_argument("--mode", default="trade", help="DrugEye mode name used in the cache key.")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-cached", action="store_true", help="Do not skip queries already in JSONL cache.")
    return parser.parse_args()


def cache_key(mode: str, query: str) -> str:
    return f"{mode}\t{query}"


def stable_id(mode: str, query: str) -> str:
    return hashlib.sha1(cache_key(mode, query).encode("utf-8")).hexdigest()


def cached_keys(path: Path | None) -> set[str]:
    keys: set[str] = set()
    if path is None or not path.exists():
        return keys
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            key = str(item.get("key") or "")
            if key:
                keys.add(key)
    return keys


def main() -> int:
    args = parse_args()
    seen_queries: set[str] = set()
    already_cached = set() if args.include_cached else cached_keys(args.cache)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with args.dataset.open(newline="", encoding="utf-8") as source, args.output.open("w", encoding="utf-8") as out:
        reader = csv.DictReader(source)
        for row in reader:
            query = row["input"]
            key = cache_key(args.mode, query)
            if query in seen_queries or key in already_cached:
                continue
            seen_queries.add(query)
            out.write(f"{stable_id(args.mode, query)}\t{query}\n")
            written += 1
    print(f"wrote {written} unique queries to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

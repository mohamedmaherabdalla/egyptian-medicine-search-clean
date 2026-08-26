#!/usr/bin/env python3
"""Create a deterministic proportional V2 sample for live website benchmarking."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
from collections import defaultdict
from pathlib import Path


DATASET_DIR = Path(__file__).resolve().parent
DATASET_PATH = DATASET_DIR / "data" / "test_cases.csv"
RESULTS_DIR = DATASET_DIR / "data" / "samples"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a deterministic V2 sample preserving category ratios.")
    parser.add_argument("--total", type=int, default=6000, help="Target total rows across all categories.")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS_DIR / "proportional_6000.csv",
    )
    return parser.parse_args()


def stable_key(row: dict[str, str]) -> str:
    text = "|".join([
        row.get("scope", ""),
        row.get("category", ""),
        row.get("error_type", ""),
        row.get("source_base_group", ""),
        row.get("input", ""),
        row.get("expected", ""),
    ])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    args = parse_args()
    if args.total <= 0:
        raise ValueError("--total must be positive")

    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    with args.dataset.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise ValueError(f"{args.dataset} has no header")
        for source_row, row in enumerate(reader, 1):
            row = dict(row)
            row["source_row"] = str(source_row)
            grouped[(row["scope"], row["category"])].append(row)

    total_rows = sum(len(rows) for rows in grouped.values())
    raw_targets = {
        key: (len(rows) * args.total / total_rows)
        for key, rows in grouped.items()
    }
    targets = {
        key: min(len(grouped[key]), max(1, math.floor(raw)))
        for key, raw in raw_targets.items()
    }
    remaining = args.total - sum(targets.values())
    if remaining > 0:
        ordered = sorted(
            grouped,
            key=lambda key: (raw_targets[key] - math.floor(raw_targets[key]), len(grouped[key])),
            reverse=True,
        )
        for key in ordered:
            if remaining <= 0:
                break
            if targets[key] < len(grouped[key]):
                targets[key] += 1
                remaining -= 1

    sampled_rows: list[dict[str, str]] = []
    for key in sorted(grouped):
        candidates = sorted(grouped[key], key=stable_key)
        sampled_rows.extend(candidates[: targets[key]])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_fields = ["source_row", *[field for field in fieldnames if field != "source_row"]]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields)
        writer.writeheader()
        for row in sampled_rows:
            writer.writerow({field: row.get(field, "") for field in output_fields})

    print(
        f"wrote {len(sampled_rows)} rows from {len(grouped)} categories "
        f"using proportional allocation to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

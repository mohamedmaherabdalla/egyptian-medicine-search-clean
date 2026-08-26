#!/usr/bin/env python3
"""Validate human catalog decisions and create an adjudicated mapping artifact."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from audit_and_map_dataset import MAPPING_FIELDS
from benchmark_common import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_DATA_DIR,
    load_catalog_families,
    read_csv,
    repository_path,
    write_csv,
    write_json,
)


ALLOWED_DECISIONS = {
    "",
    "approve_commercial_family",
    "ingredient_query",
    "regional_brand_only",
    "non_medicine_text",
    "ambiguous",
    "invalid_ground_truth",
    "reject_unclear",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mapping", type=Path, default=DEFAULT_DATA_DIR / "catalog_mapping.csv")
    parser.add_argument("--reviews", type=Path, default=DEFAULT_DATA_DIR / "catalog_mapping_review_queue.csv")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_DATA_DIR / "catalog_mapping_adjudicated.csv")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mappings = read_csv(args.mapping)
    reviews = {row["ground_truth_normalized"]: row for row in read_csv(args.reviews)}
    family_by_key = {family.key: family for family in load_catalog_families(args.catalog)}
    errors = []
    applied = 0
    output = []
    for row in mappings:
        review = reviews.get(row["ground_truth_normalized"], {})
        decision = str(review.get("human_decision") or "").strip()
        if decision not in ALLOWED_DECISIONS:
            errors.append(f"{row['ground_truth_normalized']}: invalid decision {decision!r}")
            output.append(row)
            continue
        if not decision:
            output.append(row)
            continue
        if not str(review.get("reviewer") or "").strip():
            errors.append(f"{row['ground_truth_normalized']}: reviewed decision has no reviewer")
            output.append(row)
            continue
        updated = dict(row)
        if decision == "approve_commercial_family":
            family_key = str(review.get("approved_family_key") or "").strip()
            family = family_by_key.get(family_key)
            if family is None:
                errors.append(f"{row['ground_truth_normalized']}: unknown family key {family_key!r}")
                output.append(row)
                continue
            updated.update({
                "mapping_status": "mapped_human_review",
                "mapping_method": "human_adjudication",
                "expected_family_key": family.key,
                "expected_family_name": family.name,
                "expected_candidate_ids": ";".join(family.candidate_ids),
                "expected_ingredients": ";".join(family.ingredients),
                "family_count": 1,
                "eligible_for_search_benchmark": 1,
                "mapping_note": f"Approved by {review['reviewer']}: {review.get('review_note', '')}",
            })
        else:
            updated.update({
                "mapping_status": f"reviewed_{decision}",
                "mapping_method": "human_adjudication",
                "eligible_for_search_benchmark": 0,
                "mapping_note": f"Reviewed by {review['reviewer']}: {review.get('review_note', '')}",
            })
        output.append(updated)
        applied += 1

    if errors:
        write_json(args.output.with_suffix(".errors.json"), {"errors": sorted(set(errors))})
        raise SystemExit("mapping review validation failed; see the errors JSON")
    write_csv(args.output, output, MAPPING_FIELDS)
    counts = collections.Counter(row["mapping_status"] for row in output)
    summary = {
        "rows": len(output),
        "reviewed_rows_applied": applied,
        "eligible_rows": sum(str(row["eligible_for_search_benchmark"]) == "1" for row in output),
        "mapping_counts": dict(sorted(counts.items())),
        "output": repository_path(args.output),
    }
    write_json(args.output.with_suffix(".summary.json"), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

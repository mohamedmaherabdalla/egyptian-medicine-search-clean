#!/usr/bin/env python3
"""Validate Data 3 row coverage and cross-file reconciliation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmark_common import (
    DEFAULT_ARTIFACTS_DIR,
    DEFAULT_DATA_DIR,
    DEFAULT_RESULTS_DIR,
    read_csv,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir
    artifacts_dir = args.artifacts_dir
    results_dir = args.results_dir
    manifest = read_csv(data_dir / "dataset_manifest.csv")
    eligible_manifest = {
        row["sample_id"]
        for row in manifest
        if row.get("image_valid") == "1" and row.get("ground_truth_compact")
    }
    mapping = read_csv(data_dir / "catalog_mapping_adjudicated.csv")
    mapped_samples = {
        row["sample_id"]
        for row in mapping
        if row.get("eligible_for_search_benchmark") == "1"
    }

    checks: list[dict[str, object]] = []
    ocr_paths = sorted(artifacts_dir.glob("ocr_*_all.csv"))
    observation_rows = 0
    for path in ocr_paths:
        rows = read_csv(path)
        sample_ids = [row.get("sample_id", "") for row in rows]
        sample_set = set(sample_ids)
        observation_rows += len(rows)
        missing = sorted(eligible_manifest - sample_set)
        extras = sorted(sample_set - eligible_manifest)
        duplicate_count = len(sample_ids) - len(sample_set)
        checks.append({
            "check": f"ocr_coverage:{path.name}",
            "passed": not missing and not extras and duplicate_count == 0,
            "expected_rows": len(eligible_manifest),
            "actual_rows": len(rows),
            "missing_rows": len(missing),
            "extra_rows": len(extras),
            "duplicate_rows": duplicate_count,
        })

    search_cases = read_csv(artifacts_dir / "search_cases.csv")
    checks.append({
        "check": "search_cases_reconcile_with_ocr_observations",
        "passed": len(search_cases) == observation_rows,
        "expected_rows": observation_rows,
        "actual_rows": len(search_cases),
    })

    accepted_cases = [row for row in search_cases if row.get("accepted") == "1"]
    all_mapped_cases = [
        row for row in search_cases
        if row.get("sample_id") in mapped_samples
        and row.get("rejection_reason") != "ocr_runtime_error"
        and not row.get("rejection_reason", "").startswith("source_ground_truth_excluded:")
    ]
    for prefix, expected_cases in (
        ("search", len(accepted_cases)),
        ("end_to_end", len(all_mapped_cases)),
    ):
        rows = read_csv(artifacts_dir / f"{prefix}_results.csv")
        algorithms = {row.get("algorithm", "") for row in rows}
        expected_rows = expected_cases * 4
        per_algorithm = {
            algorithm: sum(row.get("algorithm") == algorithm for row in rows)
            for algorithm in sorted(algorithms)
        }
        checks.append({
            "check": f"{prefix}_algorithm_coverage",
            "passed": (
                len(algorithms) == 4
                and len(rows) == expected_rows
                and all(count == expected_cases for count in per_algorithm.values())
            ),
            "expected_cases_per_algorithm": expected_cases,
            "expected_rows": expected_rows,
            "actual_rows": len(rows),
            "algorithm_count": len(algorithms),
            "per_algorithm": per_algorithm,
        })

    audit_path = data_dir / "dataset_audit_summary.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    conflict_sample_ids = {
        sample_id
        for group in audit.get("duplicate_label_conflict_groups", [])
        for sample_id in group
    }
    excluded_conflicts = {
        row["sample_id"]
        for row in manifest
        if row.get("exclusion_reason") == "duplicate_pixels_conflicting_ground_truth"
    }
    uncertain_placeholder_ids = {
        row["sample_id"]
        for row in manifest
        if "?" in row.get("ground_truth_raw", "") and row.get("ground_truth_compact")
    }
    excluded_uncertain_placeholders = {
        row["sample_id"]
        for row in manifest
        if row.get("exclusion_reason") == "uncertain_ground_truth_placeholder"
    }
    checks.append({
        "check": "dataset_integrity",
        "passed": (
            not audit.get("invalid_images")
            and not audit.get("label_disagreements")
            and not audit.get("cross_split_duplicate_groups")
            and conflict_sample_ids == excluded_conflicts
            and uncertain_placeholder_ids == excluded_uncertain_placeholders
        ),
        "invalid_images": len(audit.get("invalid_images", [])),
        "label_disagreements": len(audit.get("label_disagreements", [])),
        "cross_split_duplicate_groups": len(audit.get("cross_split_duplicate_groups", [])),
        "duplicate_label_conflict_groups": len(audit.get("duplicate_label_conflict_groups", [])),
        "conflicting_rows_explicitly_excluded": len(excluded_conflicts),
        "uncertain_placeholder_rows_explicitly_excluded": len(
            excluded_uncertain_placeholders
        ),
    })

    failed = [check for check in checks if not check["passed"]]
    summary = {
        "passed": not failed,
        "manifest_rows": len(manifest),
        "ocr_eligible_manifest_rows": len(eligible_manifest),
        "ocr_model_configurations": len(ocr_paths),
        "mapped_samples": len(mapped_samples),
        "checks": checks,
        "failed_checks": [check["check"] for check in failed],
    }
    write_json(results_dir / "validation_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Prepare and analyze the randomized within-subject pharmacist study."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
SOURCE_DATA = PROJECT_ROOT / "benchmark_03_ocr/data/01_rxhandbd"
DEFAULT_MANIFEST = SOURCE_DATA / "dataset_manifest.csv"
DEFAULT_MAPPING = SOURCE_DATA / "catalog_mapping_adjudicated.csv"
STUDY_DATA = ROOT / "data/03_pharmacist_study"
STUDY_ARTIFACTS = ROOT / "artifacts/03_pharmacist_study"
STUDY_RESULTS = ROOT / "results/03_pharmacist_study"
CONDITIONS = ("no_tool", "drugeye", "algorithm_4")
ACTIONS = {"select", "cannot_decide", "call_doctor"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    prepare.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    prepare.add_argument("--participants", type=int, default=15)
    prepare.add_argument("--cases", type=int, default=75)
    prepare.add_argument("--seed", type=int, default=20260716)

    analyze = subparsers.add_parser("analyze")
    analyze.add_argument(
        "--responses",
        type=Path,
        default=STUDY_ARTIFACTS / "response_template.csv",
    )
    analyze.add_argument("--bootstrap-samples", type=int, default=10000)
    analyze.add_argument("--seed", type=int, default=20260716)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"refusing to write empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def compact(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def stable_case_id(sample_id: str) -> str:
    digest = hashlib.sha256(f"pharmacist-study:{sample_id}".encode()).hexdigest()[:12]
    return f"RX-{digest}"


def eligible_cases(manifest_path: Path, mapping_path: Path) -> list[dict[str, str]]:
    manifests = {row["sample_id"]: row for row in read_csv(manifest_path)}
    cases = []
    for mapping in read_csv(mapping_path):
        if mapping.get("eligible_for_search_benchmark") != "1":
            continue
        manifest = manifests.get(mapping["sample_id"])
        if not manifest or manifest.get("image_valid") != "1":
            continue
        image_path = Path(manifest["image_path"])
        if not image_path.exists():
            continue
        cases.append(
            {
                "case_id": stable_case_id(mapping["sample_id"]),
                "sample_id": mapping["sample_id"],
                "image_id": mapping["image_id"],
                "source_split": mapping["split"],
                "image_path": str(image_path),
                "expected_family_key": mapping["expected_family_key"],
                "expected_family_name": mapping["expected_family_name"],
                "ground_truth_raw": mapping["ground_truth_raw"],
            }
        )
    return cases


def balanced_case_sample(cases: list[dict[str, str]], count: int, seed: int) -> list[dict[str, str]]:
    if count > len(cases):
        raise ValueError(f"requested {count} cases, but only {len(cases)} eligible crops exist")
    rng = random.Random(seed)
    buckets: dict[str, deque[dict[str, str]]] = {}
    for target in sorted({row["expected_family_key"] for row in cases}):
        values = [row for row in cases if row["expected_family_key"] == target]
        rng.shuffle(values)
        buckets[target] = deque(values)
    selected: list[dict[str, str]] = []
    while len(selected) < count:
        available = [key for key, values in buckets.items() if values]
        if not available:
            break
        available.sort(key=lambda key: (sum(row["expected_family_key"] == key for row in selected), key))
        for target in available:
            if len(selected) == count:
                break
            selected.append(buckets[target].popleft())
    rng.shuffle(selected)
    return selected


def prepare_study(args: argparse.Namespace) -> int:
    if not 10 <= args.participants <= 20:
        raise ValueError("the requested design requires 10 to 20 participants")
    if not 50 <= args.cases <= 100:
        raise ValueError("the requested design requires 50 to 100 prescription crops")
    selected = balanced_case_sample(
        eligible_cases(args.manifest, args.mapping),
        args.cases,
        args.seed,
    )
    public_cases = [
        {
            "case_id": row["case_id"],
            "image_id": row["image_id"],
            "source_split": row["source_split"],
            "image_path": row["image_path"],
        }
        for row in selected
    ]
    answer_key = [
        {
            "case_id": row["case_id"],
            "sample_id": row["sample_id"],
            "expected_family_key": row["expected_family_key"],
            "expected_family_name": row["expected_family_name"],
            "ground_truth_raw": row["ground_truth_raw"],
        }
        for row in selected
    ]
    write_csv(STUDY_DATA / "case_manifest.csv", public_cases)
    write_csv(STUDY_DATA / "answer_key.csv", answer_key)

    stable_case_order = {row["case_id"]: index for index, row in enumerate(selected)}
    assignments = []
    responses = []
    for participant_index in range(args.participants):
        participant_id = f"P{participant_index + 1:03d}"
        participant_cases = list(public_cases)
        random.Random(args.seed + participant_index + 1).shuffle(participant_cases)
        for trial_order, case in enumerate(participant_cases, 1):
            condition = CONDITIONS[(participant_index + stable_case_order[case["case_id"]]) % len(CONDITIONS)]
            assignment = {
                "participant_id": participant_id,
                "trial_order": trial_order,
                "case_id": case["case_id"],
                "condition": condition,
                "image_path": case["image_path"],
            }
            assignments.append(assignment)
            responses.append(
                {
                    **assignment,
                    "entered_query": "",
                    "tool_output_snapshot_id": "",
                    "action": "",
                    "selected_family": "",
                    "decision_time_seconds": "",
                    "confidence_1_to_5": "",
                    "notes": "",
                }
            )
    write_csv(STUDY_ARTIFACTS / "assignments.csv", assignments)
    write_csv(STUDY_ARTIFACTS / "response_template.csv", responses)

    per_condition = defaultdict(int)
    for row in assignments:
        per_condition[row["condition"]] += 1
    summary = {
        "status": "prepared_not_executed",
        "participants": args.participants,
        "cases": args.cases,
        "trials": len(assignments),
        "unique_target_families": len({row["expected_family_key"] for row in selected}),
        "trials_per_condition": dict(per_condition),
        "seed": args.seed,
    }
    STUDY_RESULTS.mkdir(parents=True, exist_ok=True)
    (STUDY_RESULTS / "preparation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def participant_condition_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["participant_id"], row["condition"])].append(row)
    output = []
    for (participant, condition), values in sorted(grouped.items()):
        output.append(
            {
                "participant_id": participant,
                "condition": condition,
                "trials": len(values),
                "correct_rate": statistics.fmean(row["correct"] for row in values),
                "unsafe_error_rate": statistics.fmean(row["unsafe_error"] for row in values),
                "safe_deferral_rate": statistics.fmean(row["safe_deferral"] for row in values),
                "mean_decision_time_seconds": statistics.fmean(row["decision_time_seconds"] for row in values),
            }
        )
    return output


def bootstrap_condition_ci(
    participant_rows: list[dict[str, Any]],
    condition: str,
    metric: str,
    samples: int,
    rng: random.Random,
) -> tuple[float, float]:
    values = [float(row[metric]) for row in participant_rows if row["condition"] == condition]
    estimates = [statistics.fmean(rng.choices(values, k=len(values))) for _ in range(samples)]
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def paired_difference_rows(
    participant_rows: list[dict[str, Any]],
    samples: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    by_participant = {
        (row["participant_id"], row["condition"]): row
        for row in participant_rows
    }
    participants = sorted({row["participant_id"] for row in participant_rows})
    comparisons = (
        ("algorithm_4", "no_tool"),
        ("algorithm_4", "drugeye"),
        ("drugeye", "no_tool"),
    )
    output = []
    for left, right in comparisons:
        paired_participants = [
            participant
            for participant in participants
            if (participant, left) in by_participant and (participant, right) in by_participant
        ]
        if not paired_participants:
            raise ValueError(f"no participants completed both {left} and {right}")
        for metric in (
            "correct_rate",
            "unsafe_error_rate",
            "safe_deferral_rate",
            "mean_decision_time_seconds",
        ):
            differences = [
                float(by_participant[(participant, left)][metric])
                - float(by_participant[(participant, right)][metric])
                for participant in paired_participants
            ]
            estimates = [
                statistics.fmean(rng.choices(differences, k=len(differences)))
                for _ in range(samples)
            ]
            output.append(
                {
                    "left_condition": left,
                    "right_condition": right,
                    "metric": metric,
                    "paired_participants": len(paired_participants),
                    "mean_left_minus_right": statistics.fmean(differences),
                    "ci_low": percentile(estimates, 0.025),
                    "ci_high": percentile(estimates, 0.975),
                }
            )
    return output


def analyze_study(args: argparse.Namespace) -> int:
    answers = {row["case_id"]: row for row in read_csv(STUDY_DATA / "answer_key.csv")}
    assignments = {
        (row["participant_id"], row["case_id"]): row
        for row in read_csv(STUDY_ARTIFACTS / "assignments.csv")
    }
    completed = []
    seen_trials: set[tuple[str, str]] = set()
    for row in read_csv(args.responses):
        action = row.get("action", "").strip().lower()
        if not action:
            continue
        trial_key = (row["participant_id"], row["case_id"])
        if trial_key in seen_trials:
            raise ValueError(f"duplicate completed trial: {trial_key}")
        seen_trials.add(trial_key)
        assignment = assignments.get(trial_key)
        if not assignment or assignment["condition"] != row["condition"]:
            raise ValueError(f"response does not match locked assignment: {trial_key}")
        if action not in ACTIONS:
            raise ValueError(f"invalid action {action!r} for {row['participant_id']} {row['case_id']}")
        answer = answers[row["case_id"]]
        selected = compact(row.get("selected_family", ""))
        expected = compact(answer["expected_family_key"])
        decision_time = float(row["decision_time_seconds"])
        if decision_time <= 0:
            raise ValueError(f"decision time must be positive: {trial_key}")
        confidence = row.get("confidence_1_to_5", "").strip()
        if confidence and not 1 <= int(confidence) <= 5:
            raise ValueError(f"confidence must be 1 to 5: {trial_key}")
        is_selection = action == "select"
        if is_selection and not selected:
            raise ValueError(f"selected family is required for select action: {trial_key}")
        if row["condition"] in {"drugeye", "algorithm_4"}:
            if not row.get("entered_query", "").strip():
                raise ValueError(f"entered query is required for tool trial: {trial_key}")
            if not row.get("tool_output_snapshot_id", "").strip():
                raise ValueError(f"tool-output snapshot is required for tool trial: {trial_key}")
        elif row.get("entered_query", "").strip() or row.get("tool_output_snapshot_id", "").strip():
            raise ValueError(f"no-tool trial must not contain tool input or output: {trial_key}")
        completed.append(
            {
                **row,
                "expected_family_name": answer["expected_family_name"],
                "correct": int(is_selection and selected == expected),
                "unsafe_error": int(is_selection and selected != expected),
                "safe_deferral": int(action in {"cannot_decide", "call_doctor"}),
                "decision_time_seconds": decision_time,
            }
        )
    if not completed:
        raise ValueError("no completed participant responses; the study has not been executed")

    participant_rows = participant_condition_metrics(completed)
    write_csv(STUDY_ARTIFACTS / "participant_condition_metrics.csv", participant_rows)
    rng = random.Random(args.seed)
    condition_rows = []
    for condition in CONDITIONS:
        subset = [row for row in participant_rows if row["condition"] == condition]
        if not subset:
            raise ValueError(f"no completed observations for condition: {condition}")
        row: dict[str, Any] = {
            "condition": condition,
            "participants": len(subset),
            "trials": sum(int(value["trials"]) for value in subset),
        }
        for metric in (
            "correct_rate",
            "unsafe_error_rate",
            "safe_deferral_rate",
            "mean_decision_time_seconds",
        ):
            row[metric] = statistics.fmean(float(value[metric]) for value in subset)
            low, high = bootstrap_condition_ci(
                participant_rows,
                condition,
                metric,
                args.bootstrap_samples,
                rng,
            )
            row[f"{metric}_ci_low"] = low
            row[f"{metric}_ci_high"] = high
        condition_rows.append(row)
    write_csv(STUDY_RESULTS / "condition_metrics.csv", condition_rows)
    paired_rows = paired_difference_rows(
        participant_rows,
        args.bootstrap_samples,
        rng,
    )
    write_csv(STUDY_RESULTS / "paired_differences.csv", paired_rows)

    report = [
        "# Pharmacist Study Results",
        "",
        f"Completed response rows: {len(completed)}.",
        "",
        "| Condition | Participants | Trials | Correct | Unsafe error | Safe deferral | Mean seconds |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in condition_rows:
        report.append(
            f"| {row['condition']} | {row['participants']} | {row['trials']} | "
            f"{100 * row['correct_rate']:.2f}% | {100 * row['unsafe_error_rate']:.2f}% | "
            f"{100 * row['safe_deferral_rate']:.2f}% | {row['mean_decision_time_seconds']:.2f} |"
        )
    report.extend(
        [
            "",
            "## Paired condition differences",
            "",
            "Each value is the participant-level mean in the left condition minus the same participant's mean in the right condition.",
            "",
            "| Left - right | Metric | Participants | Difference | 95% bootstrap interval |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for row in paired_rows:
        report.append(
            f"| {row['left_condition']} - {row['right_condition']} | {row['metric']} | "
            f"{row['paired_participants']} | {row['mean_left_minus_right']:.4f} | "
            f"[{row['ci_low']:.4f}, {row['ci_high']:.4f}] |"
        )
    report.extend(
        [
            "",
            "Confidence intervals in `condition_metrics.csv` are participant-level paired-design bootstrap intervals. Clinical interpretation still requires the preregistered protocol and source-label audit.",
            "",
        ]
    )
    (STUDY_RESULTS / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps(condition_rows, indent=2))
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        return prepare_study(args)
    return analyze_study(args)


if __name__ == "__main__":
    raise SystemExit(main())

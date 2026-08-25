#!/usr/bin/env python3
"""Build the team handbook's metric evidence and LaTeX macro files.

This script is intentionally a strict assembler, not an evaluator.  It reads
only preserved result artifacts, verifies that they describe the frozen
datasets and the exact current core source bytes, and then emits deterministic
JSON and TeX.  Any drift aborts generation instead of silently mixing results
from different algorithm or catalog versions.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "algorithm_6_rule_evaluation"

EVIDENCE_PATH = PACKAGE / "results" / "team_handbook_evidence.json"
TEX_PATH = PACKAGE / "latex" / "generated" / "team_results.tex"

ARTIFACT_PATHS = {
    "ordinary_typo": "algorithm_6_rule_evaluation/results/runs/20260822T230616Z/summary.json",
    "fair_ocr_algorithm_6": "algorithm_6_rule_evaluation/results/fair_ocr_412_current/latest_summary.json",
    "fair_ocr_baselines": "algorithm_6_rule_evaluation/results/fair_ocr_412_baselines_current/latest_summary.json",
    "visual_gap_identity": "algorithm_6_rule_evaluation/results/visual_gap_identity/latest_summary.json",
    "strict_product_current": "algorithm_6_rule_evaluation/results/product_selection_strict/latest_summary.json",
    "strict_product_initial_oracle": "algorithm_6_rule_evaluation/results/product_selection_strict/runs/20260822T171120Z/summary.json",
    "product_context_200": "algorithm_6_rule_evaluation/results/product_context_200_current.json",
    "unified_regression": "algorithm_6_rule_evaluation/results/runs/20260822T230951Z/summary.json",
    "hard_name_current": "algorithm_6_rule_evaluation/results/name_rule_hard_benchmark/latest_summary.json",
    "generation_manifest": "algorithm_6_rule_evaluation/test_sets/manifests/generation_manifest.json",
    "strict_product_manifest": "algorithm_6_rule_evaluation/test_sets/manifests/product_selection_strict.manifest.json",
    "visual_gap_manifest": "algorithm_6_rule_evaluation/test_sets/manifests/visual_gap_identity_benchmark.manifest.json",
    "hard_name_manifest": "algorithm_6_rule_evaluation/test_sets/manifests/name_rule_hard_benchmark.manifest.json",
}
EXPECTED_ARTIFACT_HASHES = {
    "ordinary_typo": "322d7833f8d42498b77e17e40d9a0d28f791b54eeef8f9b2517e4422c3336044",
    "fair_ocr_algorithm_6": "f2e6074a7f600a9e47fb084e6b4d7af5cd92bd26480cd1d2c2e91372744a53a9",
    "fair_ocr_baselines": "be8b191cc2a5470684d2a5a0fb7b24411aac77ce6ada9498970018275e66af52",
    "visual_gap_identity": "7c277d4f842cee550c72fbc81ecc2bcd27c73c77b260677a775c9cae5c0ac035",
    "strict_product_current": "c40bd6be4635551289509e6dabc9be2c88a0c9d08790933df46edb91470fc197",
    "strict_product_initial_oracle": "17a3b380a9b6b3f6fba26bf04949cf8ff9386f443c5da286e6b5023b90a10341",
    "product_context_200": "a6b65a28c382545ebc7e1c43d7f5ce536aeea03601cb0e24266bdc51686b9803",
    "unified_regression": "3e661c9a7bfc927797306f53941066fc717d7baa1d591eb9251fa807b82d109a",
    "hard_name_current": "55fbcd7190f4bf360cf1352a2892cd02a8e984a26ef9f6982650ce3fd9c9e9a0",
    "generation_manifest": "e7ee08de28f5ae5d46740b1e2fc82ae88763d8e6fb99bd5baba63420e281d077",
    "strict_product_manifest": "7a61e079ac15e3ba514ccf4039cb7181639b89d3792f2191f648a2b0eb9d8278",
    "visual_gap_manifest": "ca7cfa0353b0d0f9333265df4ad83c456a3a9410d8b309d703302d8c189263cf",
    "hard_name_manifest": "48c1df5ec62fde377e3ec5e89fc3133808296ccfdcf16fcbb6e2dd0cd1741d1c",
}

EXPECTED_GIT_HEAD = "7ed39d0111a964434742626bddafb0e67c1d8048"
EXPECTED_GENERATION_MANIFEST_SHA256 = (
    "e7ee08de28f5ae5d46740b1e2fc82ae88763d8e6fb99bd5baba63420e281d077"
)
EXPECTED_SOURCE_HASHES = {
    "algorithm_5": "c5faefb2bfb54c4dfbe4a059b120aaa4121db3c2bdf0606ab0cdef4f56bbbee7",
    "algorithm_6": "cedf1fce3dac214f5533707c031051efec7343aa8d4342e9ddf7cfe31940fbcb",
    "product_reranker": "03780539f9449323a641ab6ad9d2f505f0ed167e6741c63c858bc0b7d873caea",
    "api": "752399eec3caf486d1242d61d9176625cd0e42605e6553487e466bd56b8bc6de",
    "catalog": "d234edaa2669d1eeb46b962e7e3e02df52c6f4d2fd3eca7a2fbf3bc7d159fd9c",
}
PRE_PHONETIC_REPAIR_SOURCE_HASHES = {
    **EXPECTED_SOURCE_HASHES,
    "algorithm_5": "a8f040de1b15fe317bf6e870bb83995684f76e480f01764a762a2bc5f99b3499",
    "algorithm_6": "3ea34909e2fbb4bdd04f338c3bbd42ff1c3288caa4e96a0bdd022eddc8e93030",
}
SOURCE_PATHS = {
    "algorithm_5": "benchmark_01_legacy/master_algorithms/algorithm_5_commercial_name_search.py",
    "algorithm_6": "benchmark_01_legacy/master_algorithms/algorithm_6_consensus_search.py",
    "product_reranker": "app/product_context_reranker.py",
    "api": "app/api.py",
    "catalog": "app/data/catalog.json",
}

EXPECTED_DATASETS = {
    "ordinary_typo_accuracy": {
        "path": "algorithm_6_rule_evaluation/test_sets/generated/ordinary_typo_catalog_benchmark.csv",
        "sha256": "5c00ce528f06486b4b7fd2c6b98d90446f16ea3dbea02ca9477ce333a48e25d4",
        "rows": 800,
    },
    "ordinary_typo_safety": {
        "path": "algorithm_6_rule_evaluation/test_sets/generated/ordinary_typo_collision_safety.csv",
        "sha256": "fab3459db7c237a01a6d278db6c58ef351c65f79504e73bd5e78e66e0989e558",
        "rows": 150,
    },
    "fair_ocr_412": {
        "path": "algorithm_6_rule_evaluation/test_sets/locked/fair_ocr_412.csv",
        "sha256": "3ad1a423cadc96b29665a8c600c27eb25bc743a5274f4a2c7917402fe09979bd",
        "rows": 412,
    },
    "visual_gap_identity": {
        "path": "algorithm_6_rule_evaluation/test_sets/generated/visual_gap_identity_benchmark.csv",
        "sha256": "01d2aa319edb34311649af168fa0535f655d9c96f11f0163eddb08f4d27fafcf",
        "rows": 424,
    },
    "strict_product": {
        "path": "algorithm_6_rule_evaluation/test_sets/generated/product_selection_strict.csv",
        "sha256": "ce3d09e3446c4ede09289407910a3638f7ab1d164368f5e8a8b871b6d528d624",
        "rows": 440,
    },
    "product_context_200_csv": {
        "path": "algorithm_6_rule_evaluation/test_sets/generated/product_context_200.csv",
        "sha256": "e5f7283b19f8eb13175cd489844932f395270d041887f34bef8b6b1142ee2949",
        "rows": 200,
    },
    "ocr_generated": {
        "path": "algorithm_6_rule_evaluation/test_sets/generated/ocr_grapheme_catalog_generated.csv",
        "sha256": "aa59b1af04a45dd6b530e2a25e5e130bce05d1f3af31615e203734d341e61625",
        "rows": 160,
    },
    "ocr_challenge": {
        "path": "algorithm_6_rule_evaluation/test_sets/generated/ocr_grapheme_adversarial.csv",
        "sha256": "948afeea479d4311fa64f193a32061319693af012372443d6dac958e70ea3984",
        "rows": 78,
    },
    "hard_name_atomic": {
        "path": "algorithm_6_rule_evaluation/test_sets/generated/name_reading_atomic_accuracy.csv",
        "sha256": "f5f607c28b50874412b8a5305e55e251270e72d84f17ec2c097307389669c688",
        "rows": 1724,
    },
    "hard_name_composed": {
        "path": "algorithm_6_rule_evaluation/test_sets/generated/name_reading_composed_accuracy.csv",
        "sha256": "f1a32d1ece286b4e6d09d8d373f7b3cd5e740d5df22920c694a6a091e0a1a183",
        "rows": 1560,
    },
    "hard_name_safety": {
        "path": "algorithm_6_rule_evaluation/test_sets/generated/name_reading_collision_safety.csv",
        "sha256": "4c655a65acbcc1398dff1cd8bc5b8620538fbc4ae836a8508bdd9685c5ce5af3",
        "rows": 272,
    },
    "hard_name_diagnostic": {
        "path": "algorithm_6_rule_evaluation/test_sets/generated/name_reading_cross_channel_diagnostics.csv",
        "sha256": "fdd5e2651d56da08b34d8231841500f6f63d8d360d1f5a57c208728669d14663",
        "rows": 100,
    },
    "hard_name_boundary": {
        "path": "algorithm_6_rule_evaluation/test_sets/generated/name_reading_source_boundaries.csv",
        "sha256": "d0a450698ccab3031b672fc692e71826e44b26df0848f85a3ec29fbcd0b5b9df",
        "rows": 11,
    },
}
EXPECTED_PRODUCT_200_LOGICAL_SHA256 = (
    "21e0992188f27364582660b8072837c9d5d0fd3bcb3bbbf9c41bf7e471fd7ff5"
)


class EvidenceError(RuntimeError):
    """Raised when a preserved artifact is stale or internally inconsistent."""


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def expect(actual: Any, expected: Any, label: str) -> None:
    if isinstance(expected, float):
        valid = isinstance(actual, (int, float)) and math.isclose(
            float(actual), expected, rel_tol=0.0, abs_tol=1e-12
        )
    else:
        valid = actual == expected
    if not valid:
        raise EvidenceError(f"{label}: expected {expected!r}, got {actual!r}")


def load_json(relative_path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = REPO / relative_path
    require(path.is_file(), f"missing preserved artifact: {relative_path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read {relative_path}: {exc}") from exc
    require(isinstance(data, dict), f"artifact must be a JSON object: {relative_path}")
    return data, {
        "path": relative_path,
        "sha256": sha256_path(path),
        "bytes": path.stat().st_size,
    }


def csv_row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for row in reader if row)


def compact(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def product_200_logical_hash() -> str:
    catalog = json.loads((REPO / SOURCE_PATHS["catalog"]).read_text(encoding="utf-8"))
    records = catalog.get("records")
    require(isinstance(records, list), "catalog.records must be a list")
    families: dict[str, str] = {}
    for record in records:
        require(isinstance(record, Mapping), "catalog record must be an object")
        family = compact(record.get("b"))
        strength = str(record.get("st") or "").strip()
        if 4 <= len(family) <= 12 and family.isalpha() and re.search(r"\d", strength):
            families.setdefault(family, strength)

    def mutate(name: str) -> str:
        index = len(name) // 2
        replacement = "A" if name[index] != "A" else "O"
        return name[:index] + replacement + name[index + 1 :]

    cases = sorted(
        ((mutate(family), family, strength) for family, strength in families.items()),
        key=lambda row: hashlib.sha256("|".join(row).encode()).hexdigest(),
    )[:200]
    encoded = json.dumps(cases, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def provenance_hashes(record: Mapping[str, Any], label: str) -> dict[str, str]:
    files = record.get("files")
    require(isinstance(files, Mapping), f"{label}.files must be an object")
    result: dict[str, str] = {}
    for key in EXPECTED_SOURCE_HASHES:
        item = files.get(key)
        require(isinstance(item, Mapping), f"{label}.files.{key} must be an object")
        digest = item.get("sha256")
        require(isinstance(digest, str), f"{label}.files.{key}.sha256 must be text")
        result[key] = digest
    return result


def validate_source_identity(artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    current: dict[str, dict[str, Any]] = {}
    for key, relative_path in SOURCE_PATHS.items():
        path = REPO / relative_path
        require(path.is_file(), f"missing source authority file: {relative_path}")
        digest = sha256_path(path)
        expect(digest, EXPECTED_SOURCE_HASHES[key], f"current source hash {key}")
        current[key] = {
            "path": relative_path,
            "sha256": digest,
            "bytes": path.stat().st_size,
        }

    provenance_locations: Sequence[tuple[str, Mapping[str, Any]]] = (
        ("ordinary_typo", artifacts["ordinary_typo"]["source_provenance"]),
        ("fair_ocr_algorithm_6", artifacts["fair_ocr_algorithm_6"]["source_provenance"]),
        ("fair_ocr_baselines", artifacts["fair_ocr_baselines"]["source_provenance"]),
        ("visual_gap_identity", artifacts["visual_gap_identity"]["evaluation_source_provenance"]),
        ("visual_gap_dataset_generation", artifacts["visual_gap_identity"]["dataset"]["source_provenance"]),
        ("visual_gap_manifest", artifacts["visual_gap_manifest"]["source_provenance"]),
        ("unified_regression", artifacts["unified_regression"]["source_provenance"]),
        ("hard_name_current", artifacts["hard_name_current"]["source_provenance"]),
        ("hard_name_manifest", artifacts["hard_name_manifest"]["source_provenance"]),
    )
    for label, provenance in provenance_locations:
        require(isinstance(provenance, Mapping), f"missing source provenance: {label}")
        expect(
            provenance.get("git", {}).get("head"),
            EXPECTED_GIT_HEAD,
            f"{label} provenance Git HEAD",
        )
        hashes = provenance_hashes(provenance, f"{label}.source_provenance")
        expect(hashes, EXPECTED_SOURCE_HASHES, f"{label} core source hashes")

    strict_hashes = artifacts["strict_product_current"].get("source_hashes")
    require(isinstance(strict_hashes, Mapping), "strict product source_hashes missing")
    expect(
        {key: strict_hashes.get(key) for key in EXPECTED_SOURCE_HASHES},
        EXPECTED_SOURCE_HASHES,
        "strict product core source hashes",
    )
    initial_strict_hashes = artifacts["strict_product_initial_oracle"].get("source_hashes")
    require(isinstance(initial_strict_hashes, Mapping), "initial strict product source_hashes missing")
    expect(
        {key: initial_strict_hashes.get(key) for key in EXPECTED_SOURCE_HASHES},
        PRE_PHONETIC_REPAIR_SOURCE_HASHES,
        "historical initial strict product core source hashes",
    )
    # The preserved evaluations were executed from EXPECTED_GIT_HEAD with a
    # dirty worktree. Publication commits can differ while containing the same
    # evaluated source bytes, so the byte hashes above are the current-tree
    # authority and the historical commit remains the run provenance.
    return {"git_head": EXPECTED_GIT_HEAD, "files": current}


def validate_datasets(
    artifacts: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    datasets: dict[str, dict[str, Any]] = {}
    for name, expected in EXPECTED_DATASETS.items():
        path = REPO / expected["path"]
        require(path.is_file(), f"missing dataset: {expected['path']}")
        digest = sha256_path(path)
        rows = csv_row_count(path)
        expect(digest, expected["sha256"], f"{name} SHA-256")
        expect(rows, expected["rows"], f"{name} row count")
        datasets[name] = {
            "path": expected["path"],
            "sha256": digest,
            "rows": rows,
            "bytes": path.stat().st_size,
        }

    generation_manifest_path = REPO / ARTIFACT_PATHS["generation_manifest"]
    generation_manifest_hash = sha256_path(generation_manifest_path)
    expect(
        generation_manifest_hash,
        EXPECTED_GENERATION_MANIFEST_SHA256,
        "generation manifest SHA-256",
    )
    manifest = artifacts["generation_manifest"]
    generated_entries = {
        item["file"]: item
        for item in manifest.get("generated_files", [])
        if isinstance(item, Mapping) and isinstance(item.get("file"), str)
    }
    locked_entries = {
        item["file"]: item
        for item in manifest.get("locked_files", [])
        if isinstance(item, Mapping) and isinstance(item.get("file"), str)
    }
    for name in (
        "ordinary_typo_accuracy",
        "ordinary_typo_safety",
        "product_context_200_csv",
        "ocr_generated",
        "ocr_challenge",
    ):
        dataset = datasets[name]
        expect(generated_entries.get(dataset["path"], {}).get("sha256"), dataset["sha256"], f"manifest {name} SHA-256")
        expect(generated_entries.get(dataset["path"], {}).get("rows"), dataset["rows"], f"manifest {name} rows")
    fair = datasets["fair_ocr_412"]
    expect(locked_entries.get(fair["path"], {}).get("sha256"), fair["sha256"], "manifest fair OCR SHA-256")
    expect(locked_entries.get(fair["path"], {}).get("rows"), fair["rows"], "manifest fair OCR rows")

    strict_manifest = artifacts["strict_product_manifest"]
    strict = datasets["strict_product"]
    expect(strict_manifest.get("dataset_sha256"), strict["sha256"], "strict manifest dataset SHA-256")
    expect(strict_manifest.get("rows"), strict["rows"], "strict manifest rows")
    visual_manifest = artifacts["visual_gap_manifest"]
    visual = datasets["visual_gap_identity"]
    expect(visual_manifest.get("dataset_sha256"), visual["sha256"], "visual manifest dataset SHA-256")
    expect(visual_manifest.get("rows"), visual["rows"], "visual manifest rows")

    hard_manifest = artifacts["hard_name_manifest"]
    hard_entries = {
        item.get("name"): item
        for item in hard_manifest.get("files", [])
        if isinstance(item, Mapping)
    }
    for dataset_name, manifest_name in (
        ("hard_name_atomic", "atomic"),
        ("hard_name_composed", "composed"),
        ("hard_name_safety", "safety"),
        ("hard_name_diagnostic", "diagnostic"),
        ("hard_name_boundary", "boundary"),
    ):
        dataset = datasets[dataset_name]
        entry = hard_entries.get(manifest_name, {})
        expect(entry.get("path"), dataset["path"], f"hard manifest {manifest_name} path")
        expect(entry.get("sha256"), dataset["sha256"], f"hard manifest {manifest_name} SHA-256")
        expect(entry.get("rows"), dataset["rows"], f"hard manifest {manifest_name} rows")

    logical_hash = product_200_logical_hash()
    expect(logical_hash, EXPECTED_PRODUCT_200_LOGICAL_SHA256, "product 200 logical sample SHA-256")
    expect(manifest.get("product_200_cases_sha256"), logical_hash, "manifest product 200 logical sample SHA-256")
    datasets["product_context_200_csv"]["logical_cases_sha256"] = logical_hash
    return datasets


def validate_and_extract_metrics(
    artifacts: Mapping[str, Mapping[str, Any]],
    datasets: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    ordinary = artifacts["ordinary_typo"]
    expect(ordinary.get("run_id"), "20260822T230616Z", "ordinary run ID")
    expect(ordinary.get("generation_manifest_sha256"), EXPECTED_GENERATION_MANIFEST_SHA256, "ordinary generation manifest")
    for field, value in (("total_cases", 950), ("gating_cases", 150), ("metric_only_cases", 800), ("passed", 950), ("failed", 0)):
        expect(ordinary.get(field), value, f"ordinary {field}")
    ordinary_accuracy = ordinary["suites"]["ordinary_typo_benchmark"]
    ordinary_safety = ordinary["suites"]["ordinary_typo_collision_safety"]
    ordinary_ranking = ordinary_accuracy["ranking"]
    for field, value in (("cases", 800), ("hit1", 799), ("hit5", 800), ("hit20", 800)):
        expect(ordinary_ranking.get(field), value, f"ordinary accuracy {field}")
    expect(ordinary_ranking.get("mrr"), 0.999375, "ordinary accuracy MRR")
    for field, value in (("cases", 150), ("passed", 150), ("failed", 0), ("gating_cases", 150)):
        expect(ordinary_safety.get(field), value, f"ordinary safety {field}")

    fair = artifacts["fair_ocr_algorithm_6"]
    expect(fair.get("run_id"), "20260822T230528Z", "fair OCR Algorithm 6 run ID")
    expect(fair["dataset"].get("sha256"), datasets["fair_ocr_412"]["sha256"], "fair OCR Algorithm 6 dataset")
    fair_overall = fair["metrics"]["overall"]
    fair_expected = {"cases": 412, "hit1": 234, "hit5": 296, "hit20": 340, "miss20": 72, "mrr20": 0.6339070132545293, "empty_results": 1}
    for field, value in fair_expected.items():
        expect(fair_overall.get(field), value, f"fair OCR Algorithm 6 {field}")

    baseline_artifact = artifacts["fair_ocr_baselines"]
    expect(baseline_artifact.get("run_id"), "20260822T230532Z", "fair OCR baseline run ID")
    expect(baseline_artifact["dataset"].get("sha256"), datasets["fair_ocr_412"]["sha256"], "fair OCR baseline dataset")
    baseline_metrics = baseline_artifact["metrics"]["overall"]
    expected_baselines = {
        "current_algorithm_5": (234, 296, 338, 0.6336642948079272),
        "damerau_levenshtein": (179, 251, 299, 0.5158099909402736),
        "jaro_winkler": (149, 256, 312, 0.4789351970052281),
    }
    for name, (hit1, hit5, hit20, mrr20) in expected_baselines.items():
        row = baseline_metrics[name]
        for field, value in (("cases", 412), ("hit1", hit1), ("hit5", hit5), ("hit20", hit20), ("mrr20", mrr20)):
            expect(row.get(field), value, f"fair OCR baseline {name} {field}")

    visual = artifacts["visual_gap_identity"]
    expect(visual.get("run_id"), "20260822T230942Z", "visual run ID")
    expect(visual["dataset"].get("dataset_id"), "visual_gap_exact_identity_v1", "visual dataset ID")
    expect(visual["dataset"].get("dataset_sha256"), datasets["visual_gap_identity"]["sha256"], "visual dataset SHA-256")
    visual_overall = visual["overall"]
    visual_source = visual_overall["source_recovery"]
    for field, value in (("cases", 424), ("passed", 424), ("failed", 0), ("exact_relevant_labels", 400), ("exact_relevant_labels_found", 400), ("unexpected_nonexact_or_fuzzy_identities", 1410)):
        expect(visual_overall.get(field), value, f"visual {field}")
    for field, value in (("required_cases", 314), ("hits", 314), ("hit1", 313), ("hit5", 314), ("hit20", 314), ("mrr_at20", 0.9984076433121019)):
        expect(visual_source.get(field), value, f"visual source recovery {field}")
    expect(visual_overall.get("exact_oracle_micro_precision_indicator"), 0.22099447513812154, "visual exact-oracle precision indicator")
    visual_safety = visual["by_evaluation_kind"]["safety"]
    for field, value in (("cases", 100), ("passed", 100), ("failed", 0)):
        expect(visual_safety.get(field), value, f"visual safety {field}")
    visual_holdout = visual["by_split"]["holdout"]
    for field, value in (("cases", 86), ("passed", 86), ("failed", 0)):
        expect(visual_holdout.get(field), value, f"visual holdout {field}")

    product = artifacts["strict_product_current"]
    expect(product.get("run_id"), "20260822T230841Z", "strict product run ID")
    expect(product["dataset"].get("dataset_id"), "product_selection_strict_v1", "strict product dataset ID")
    expect(product["dataset"].get("dataset_sha256"), datasets["strict_product"]["sha256"], "strict product dataset SHA-256")
    for field, value in (("cases", 440), ("passed", 440), ("failed", 0)):
        expect(product.get(field), value, f"strict product {field}")
    expected_product_strata = {
        "exact_strength_unique": 240,
        "exact_strength_tie": 40,
        "same_strength_form_disambiguation": 80,
        "impossible_strength_abstention": 80,
    }
    for name, cases in expected_product_strata.items():
        row = product["by_stratum"][name]
        for field, value in (("cases", cases), ("passed", cases), ("failed", 0)):
            expect(row.get(field), value, f"strict product {name} {field}")
    product_initial = artifacts["strict_product_initial_oracle"]
    expect(product_initial.get("run_id"), "20260822T171120Z", "initial strict product run ID")
    for field, value in (("cases", 440), ("passed", 435), ("failed", 5)):
        expect(product_initial.get(field), value, f"initial strict product {field}")

    context = artifacts["product_context_200"]
    expect(context["dataset"].get("catalog_sha256"), EXPECTED_SOURCE_HASHES["catalog"], "product context catalog SHA-256")
    expect(context["dataset"].get("cases_sha256"), EXPECTED_PRODUCT_200_LOGICAL_SHA256, "product context cases SHA-256")
    for field, value in (("cases", 200), ("baseline_hit1", 197), ("expected_baseline_hit1", 197), ("context_hit1", 200), ("baseline_hit1_regressions", 0)):
        expect(context.get(field), value, f"product context 200 {field}")
    expect(len(context.get("recoveries", [])), 3, "product context recovery count")
    expect(len(context.get("context_misses", [])), 0, "product context miss count")
    expect(len(context.get("regressions", [])), 0, "product context regression count")

    unified = artifacts["unified_regression"]
    expect(unified.get("run_id"), "20260822T230951Z", "unified regression run ID")
    expect(unified.get("generation_manifest_sha256"), EXPECTED_GENERATION_MANIFEST_SHA256, "unified generation manifest")
    for field, value in (("total_cases", 1792), ("gating_cases", 992), ("metric_only_cases", 800), ("passed", 1792), ("failed", 0)):
        expect(unified.get(field), value, f"unified regression {field}")
    ocr = unified["suites"]["ocr_grapheme"]
    ocr_source = unified["suites"]["ocr_grapheme_source"]
    legacy_visual = unified["suites"]["visual_gap"]
    for row, label, cases in ((ocr, "OCR/API", 236), (ocr_source, "OCR source guards", 2), (legacy_visual, "legacy visual", 404)):
        for field, value in (("cases", cases), ("passed", cases), ("failed", 0)):
            expect(row.get(field), value, f"unified {label} {field}")
    generated_ocr_cases = ocr["by_split"]["development"] + ocr["by_split"]["holdout"]
    challenge_ocr_cases = ocr["by_split"]["challenge"] + ocr["by_split"]["regression"] + ocr_source["cases"]
    expect(generated_ocr_cases, 160, "generated OCR case derivation")
    expect(challenge_ocr_cases, 78, "OCR challenge/guard case derivation")
    unified_product = unified["suites"]["product_context_200"]
    for field, value in (("cases", 200), ("passed", 200), ("failed", 0), ("baseline_hit1", 197), ("context_hit1", 200)):
        expect(unified_product.get(field), value, f"unified product context {field}")

    hard = artifacts["hard_name_current"]
    expect(hard.get("run_id"), "20260822T225802Z", "hard name run ID")
    expect(hard.get("contract_failures"), 0, "hard name contract failures")
    expect(hard.get("manifest", {}).get("sha256"), EXPECTED_ARTIFACT_HASHES["hard_name_manifest"], "hard name manifest SHA-256")
    expected_hard_counts = {
        "atomic": 1724,
        "composed": 1560,
        "safety": 272,
        "diagnostic": 100,
        "boundary": 11,
    }
    expect(hard.get("row_counts"), expected_hard_counts, "hard name row counts")
    hard_accuracy = hard["accuracy"]["by_dataset"]
    expected_hard_accuracy = {
        "atomic": (1724, 1717, 1721, 1724, 0.9971239365815933),
        "composed": (1560, 1504, 1549, 1556, 0.9766467471275164),
    }
    for name, (cases, hit1, hit5, hit20, mrr20) in expected_hard_accuracy.items():
        row = hard_accuracy[name]
        for field, value in (("cases", cases), ("hit1", hit1), ("hit5", hit5), ("hit20", hit20), ("mrr20", mrr20), ("empty", 0)):
            expect(row.get(field), value, f"hard name {name} {field}")
    hard_overall = hard["accuracy"]["overall"]
    for field, value in (("cases", 3284), ("hit1", 3221), ("hit5", 3270), ("hit20", 3280), ("mrr20", 0.9873966480467697), ("empty", 0)):
        expect(hard_overall.get(field), value, f"hard name overall {field}")
    for field, value in (("cases", 272), ("passed", 272), ("failed", 0)):
        expect(hard["safety"].get(field), value, f"hard name safety {field}")
    for field, value in (("cases", 11), ("passed", 11), ("failed", 0)):
        expect(hard["source_boundaries"].get(field), value, f"hard name boundary {field}")
    for field, value in (("cases", 100), ("relevant_labels", 201), ("visible_relevant_labels", 190), ("complete_visibility_cases", 92), ("micro_recall20", 0.945273631840796)):
        expect(hard["diagnostics"].get(field), value, f"hard name diagnostic {field}")

    return {
        "ordinary_typo": {
            "claim_type": "retrospective catalog-derived ranking accuracy",
            "run_id": ordinary["run_id"],
            "cases": 800,
            "hit1": 799,
            "hit5": 800,
            "hit20": 800,
            "mrr": 0.999375,
            "safety_contracts": {"cases": 150, "passed": 150},
        },
        "reviewed_fair_ocr": {
            "claim_type": "retrospective locked reviewed cohort; not blind",
            "run_id": fair["run_id"],
            "dataset_cases": 412,
            "algorithm_6": {key: fair_overall[key] for key in fair_expected},
            "same_data_baselines": {
                name: {key: baseline_metrics[name][key] for key in ("cases", "hit1", "hit5", "hit20", "mrr20")}
                for name in expected_baselines
            },
            "comparison_boundary": "All methods use the same 412 queries and 17,476 exact-family universe; lexical baselines are not product-equivalent systems.",
        },
        "visual_gap_identity": {
            "claim_type": "retrospective catalog-derived exact-identity contracts and source-family ranking",
            "run_id": visual["run_id"],
            "contracts": {"cases": 424, "passed": 424},
            "source_family_ranking": dict(visual_source),
            "exact_relevance": {"labels": 400, "labels_found": 400},
            "safety_contracts": {"cases": 100, "passed": 100},
            "holdout_contracts": {"cases": 86, "passed": 86},
            "candidate_breadth_diagnostic": {
                "exact_oracle_micro_precision_indicator": visual_overall["exact_oracle_micro_precision_indicator"],
                "unexpected_nonexact_or_fuzzy_identities": 1410,
                "interpretation": "Diagnostic only: bounded fuzzy candidates can be valid outside the literal exact oracle.",
            },
        },
        "strict_product_selection": {
            "claim_type": "retrospective catalog-derived exact product-ID or fail-closed contract",
            "run_id": product["run_id"],
            "cases": 440,
            "passed": 440,
            "by_stratum": expected_product_strata,
            "initial_oracle_audit": {
                "run_id": product_initial["run_id"],
                "passed": 435,
                "failed": 5,
                "interpretation": "Five independent-oracle defects were repaired; this is not an algorithm accuracy gain.",
            },
        },
        "product_context_200": {
            "claim_type": "locked August 11 same-case product-context regression",
            "cases": 200,
            "baseline_hit1": 197,
            "context_hit1": 200,
            "recoveries": 3,
            "regressions": 0,
            "recovery_examples": context["recoveries"],
        },
        "unified_regression": {
            "claim_type": "developer regression contracts; pass fraction is not general accuracy",
            "run_id": unified["run_id"],
            "cases": 642,
            "passed": 642,
            "ocr_api_retrieval": {"cases": 236, "passed": 236},
            "ocr_source_guards": {"cases": 2, "passed": 2},
            "legacy_visual_matrix": {"cases": 404, "passed": 404},
            "generated_directional_ocr": {"cases": generated_ocr_cases, "passed": generated_ocr_cases},
            "ocr_challenge_and_guards": {"cases": challenge_ocr_cases, "passed": challenge_ocr_cases},
        },
        "hard_name_reading": {
            "claim_type": "retrospective catalog-derived hard ranking, strict ambiguity, diagnostic breadth, and source-boundary contracts",
            "run_id": hard["run_id"],
            "total_rows": sum(expected_hard_counts.values()),
            "accuracy": {
                "overall": dict(hard_overall),
                "atomic": dict(hard_accuracy["atomic"]),
                "composed": dict(hard_accuracy["composed"]),
            },
            "safety": {key: hard["safety"][key] for key in ("cases", "passed", "failed")},
            "source_boundaries": dict(hard["source_boundaries"]),
            "diagnostics": dict(hard["diagnostics"]),
            "manifest_sha256": hard["manifest"]["sha256"],
            "interpretation": "Accuracy misses remain misses; strict safety and source rows gate release; cross-channel breadth is diagnostic only.",
        },
    }


def format_decimal(value: float, digits: int = 6) -> str:
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def render_tex(evidence: Mapping[str, Any]) -> str:
    metrics = evidence["metrics"]
    source = evidence["source_identity"]
    ordinary = metrics["ordinary_typo"]
    fair = metrics["reviewed_fair_ocr"]
    a6 = fair["algorithm_6"]
    baselines = fair["same_data_baselines"]
    visual = metrics["visual_gap_identity"]
    visual_rank = visual["source_family_ranking"]
    product = metrics["strict_product_selection"]
    context = metrics["product_context_200"]
    unified = metrics["unified_regression"]
    hard = metrics["hard_name_reading"]
    hard_atomic = hard["accuracy"]["atomic"]
    hard_composed = hard["accuracy"]["composed"]
    hard_diagnostic = hard["diagnostics"]

    commands: list[tuple[str, str]] = [
        ("OrdinaryCases", str(ordinary["cases"])),
        ("OrdinaryHitOne", str(ordinary["hit1"])),
        ("OrdinaryHitFive", str(ordinary["hit5"])),
        ("OrdinaryHitTwenty", str(ordinary["hit20"])),
        ("OrdinaryMRR", format_decimal(ordinary["mrr"])),
        ("OrdinarySafetyCases", str(ordinary["safety_contracts"]["cases"])),
        ("OrdinarySafetyPass", str(ordinary["safety_contracts"]["passed"])),
        ("FairCases", str(fair["dataset_cases"])),
        ("FairHitOne", str(a6["hit1"])),
        ("FairHitFive", str(a6["hit5"])),
        ("FairHitTwenty", str(a6["hit20"])),
        ("FairMissTwenty", str(a6["miss20"])),
        ("FairMRR", format_decimal(a6["mrr20"])),
        ("FairAFiveHitOne", str(baselines["current_algorithm_5"]["hit1"])),
        ("FairAFiveHitFive", str(baselines["current_algorithm_5"]["hit5"])),
        ("FairAFiveHitTwenty", str(baselines["current_algorithm_5"]["hit20"])),
        ("FairAFiveMRR", format_decimal(baselines["current_algorithm_5"]["mrr20"])),
        ("FairDamerauHitOne", str(baselines["damerau_levenshtein"]["hit1"])),
        ("FairDamerauHitFive", str(baselines["damerau_levenshtein"]["hit5"])),
        ("FairDamerauHitTwenty", str(baselines["damerau_levenshtein"]["hit20"])),
        ("FairDamerauMRR", format_decimal(baselines["damerau_levenshtein"]["mrr20"])),
        ("DamerauHitOne", str(baselines["damerau_levenshtein"]["hit1"])),
        ("DamerauHitFive", str(baselines["damerau_levenshtein"]["hit5"])),
        ("DamerauHitTwenty", str(baselines["damerau_levenshtein"]["hit20"])),
        ("DamerauMRR", format_decimal(baselines["damerau_levenshtein"]["mrr20"])),
        ("FairJaroHitOne", str(baselines["jaro_winkler"]["hit1"])),
        ("FairJaroHitFive", str(baselines["jaro_winkler"]["hit5"])),
        ("FairJaroHitTwenty", str(baselines["jaro_winkler"]["hit20"])),
        ("FairJaroMRR", format_decimal(baselines["jaro_winkler"]["mrr20"])),
        ("JaroHitOne", str(baselines["jaro_winkler"]["hit1"])),
        ("JaroHitFive", str(baselines["jaro_winkler"]["hit5"])),
        ("JaroHitTwenty", str(baselines["jaro_winkler"]["hit20"])),
        ("JaroMRR", format_decimal(baselines["jaro_winkler"]["mrr20"])),
        ("VisualTotalCases", str(visual["contracts"]["cases"])),
        ("VisualContractPass", str(visual["contracts"]["passed"])),
        ("VisualSourceCases", str(visual_rank["required_cases"])),
        ("VisualSourceHits", str(visual_rank["hits"])),
        ("VisualHitOne", str(visual_rank["hit1"])),
        ("VisualHitFive", str(visual_rank["hit5"])),
        ("VisualHitTwenty", str(visual_rank["hit20"])),
        ("VisualMRR", format_decimal(visual_rank["mrr_at20"])),
        ("VisualSafetyCases", str(visual["safety_contracts"]["cases"])),
        ("VisualSafetyPass", str(visual["safety_contracts"]["passed"])),
        ("VisualExactLabels", str(visual["exact_relevance"]["labels"])),
        ("VisualExactLabelsFound", str(visual["exact_relevance"]["labels_found"])),
        ("VisualPrecisionIndicator", format_decimal(100 * visual["candidate_breadth_diagnostic"]["exact_oracle_micro_precision_indicator"], 1)),
        ("VisualUnexpectedFuzzyIdentities", str(visual["candidate_breadth_diagnostic"]["unexpected_nonexact_or_fuzzy_identities"])),
        ("VisualExtraIdentities", str(visual["candidate_breadth_diagnostic"]["unexpected_nonexact_or_fuzzy_identities"])),
        ("VisualHoldoutCases", str(visual["holdout_contracts"]["cases"])),
        ("VisualHoldoutPass", str(visual["holdout_contracts"]["passed"])),
        # Compatibility alias: a Hit@k denominator must be the 314 source-required
        # cases, never all 424 heterogeneous contract rows.
        ("VisualCases", r"\VisualSourceCases"),
        ("ProductCases", str(product["cases"])),
        ("ProductPass", str(product["passed"])),
        ("ProductFirstPass", str(product["initial_oracle_audit"]["passed"])),
        ("ProductFirstFail", str(product["initial_oracle_audit"]["failed"])),
        ("ProductUniqueStrengthCases", str(product["by_stratum"]["exact_strength_unique"])),
        ("ProductTieCases", str(product["by_stratum"]["exact_strength_tie"])),
        ("ProductFormCases", str(product["by_stratum"]["same_strength_form_disambiguation"])),
        ("ProductAbstentionCases", str(product["by_stratum"]["impossible_strength_abstention"])),
        ("ProductContextCases", str(context["cases"])),
        ("ProductBaselineHitOne", str(context["baseline_hit1"])),
        ("ProductContextBaseline", str(context["baseline_hit1"])),
        ("ProductContextHitOne", str(context["context_hit1"])),
        ("ProductContextRecoveries", str(context["recoveries"])),
        ("ProductContextRegressions", str(context["regressions"])),
        ("OcrGeneratedCases", str(unified["generated_directional_ocr"]["cases"])),
        ("OcrGeneratedHitTwenty", str(unified["generated_directional_ocr"]["passed"])),
        ("OcrChallengeCases", str(unified["ocr_challenge_and_guards"]["cases"])),
        ("OcrChallengePass", str(unified["ocr_challenge_and_guards"]["passed"])),
        ("UnifiedCases", str(unified["cases"])),
        ("UnifiedPass", str(unified["passed"])),
        ("UnifiedOcrApiCases", str(unified["ocr_api_retrieval"]["cases"])),
        ("UnifiedOcrSourceCases", str(unified["ocr_source_guards"]["cases"])),
        ("UnifiedLegacyVisualCases", str(unified["legacy_visual_matrix"]["cases"])),
        ("HardTotalCases", str(hard["total_rows"])),
        ("HardAtomicCases", str(hard_atomic["cases"])),
        ("HardAtomicHitOne", str(hard_atomic["hit1"])),
        ("HardAtomicHitFive", str(hard_atomic["hit5"])),
        ("HardAtomicHitTwenty", str(hard_atomic["hit20"])),
        ("HardAtomicMRR", format_decimal(hard_atomic["mrr20"])),
        ("HardComposedCases", str(hard_composed["cases"])),
        ("HardComposedHitOne", str(hard_composed["hit1"])),
        ("HardComposedHitFive", str(hard_composed["hit5"])),
        ("HardComposedHitTwenty", str(hard_composed["hit20"])),
        ("HardComposedMRR", format_decimal(hard_composed["mrr20"])),
        ("HardSafetyCases", str(hard["safety"]["cases"])),
        ("HardSafetyPass", str(hard["safety"]["passed"])),
        ("HardBoundaryCases", str(hard["source_boundaries"]["cases"])),
        ("HardBoundaryPass", str(hard["source_boundaries"]["passed"])),
        ("HardDiagnosticCases", str(hard_diagnostic["cases"])),
        ("HardDiagnosticComplete", str(hard_diagnostic["complete_visibility_cases"])),
        ("HardDiagnosticLabels", str(hard_diagnostic["relevant_labels"])),
        ("HardDiagnosticVisibleLabels", str(hard_diagnostic["visible_relevant_labels"])),
        ("HardDiagnosticRecall", format_decimal(hard_diagnostic["micro_recall20"])),
        ("HardRunId", hard["run_id"]),
        ("HardManifestHash", hard["manifest_sha256"][:12]),
        ("HardManifestHashFull", hard["manifest_sha256"]),
        ("HardSummaryHash", evidence["input_artifacts"]["hard_name_current"]["sha256"][:12]),
        ("HardSummaryHashFull", evidence["input_artifacts"]["hard_name_current"]["sha256"]),
        ("HardAtomicDatasetHash", evidence["dataset_identity"]["hard_name_atomic"]["sha256"][:12]),
        ("HardComposedDatasetHash", evidence["dataset_identity"]["hard_name_composed"]["sha256"][:12]),
        ("HardSafetyDatasetHash", evidence["dataset_identity"]["hard_name_safety"]["sha256"][:12]),
        ("CatalogProducts", "25066"),
        ("CatalogFamilies", "17476"),
        ("OrdinaryDatasetHash", evidence["dataset_identity"]["ordinary_typo_accuracy"]["sha256"][:12]),
        ("OrdinaryDatasetHashFull", evidence["dataset_identity"]["ordinary_typo_accuracy"]["sha256"]),
        ("FairDatasetHash", evidence["dataset_identity"]["fair_ocr_412"]["sha256"][:12]),
        ("FairDatasetHashFull", evidence["dataset_identity"]["fair_ocr_412"]["sha256"]),
        ("VisualDatasetHash", evidence["dataset_identity"]["visual_gap_identity"]["sha256"][:12]),
        ("VisualDatasetHashFull", evidence["dataset_identity"]["visual_gap_identity"]["sha256"]),
        ("ProductDatasetHash", evidence["dataset_identity"]["strict_product"]["sha256"][:12]),
        ("ProductDatasetHashFull", evidence["dataset_identity"]["strict_product"]["sha256"]),
        ("OrdinaryRunId", ordinary["run_id"]),
        ("FairRunId", fair["run_id"]),
        ("VisualRunId", visual["run_id"]),
        ("ProductRunId", product["run_id"]),
        ("OcrRunId", unified["run_id"]),
    ]
    for key, macro_name in (
        ("algorithm_5", "AlgorithmFiveHash"),
        ("algorithm_6", "AlgorithmSixHash"),
        ("product_reranker", "ProductHash"),
        ("api", "ApiHash"),
        ("catalog", "CatalogHash"),
    ):
        digest = source["files"][key]["sha256"]
        commands.extend(((macro_name, digest[:8]), (macro_name + "Full", digest)))
    commands.extend(
        (
            ("EvidenceGitHead", source["git_head"]),
            ("EvidenceGitHeadShort", source["git_head"][:8]),
        )
    )

    lines = [
        "% AUTO-GENERATED by generate_team_handbook_results.py; do not edit.",
        "% Metrics are bound to preserved artifacts, frozen datasets, and exact core-source hashes.",
        "% Accuracy, safety contracts, and developer regression coverage are deliberately separate.",
    ]
    lines.extend(f"\\newcommand{{\\{name}}}{{{value}}}" for name, value in commands)
    return "\n".join(lines) + "\n"


def write_outputs(evidence: Mapping[str, Any]) -> None:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    TEX_PATH.write_text(render_tex(evidence), encoding="utf-8")


def main() -> int:
    artifacts: dict[str, dict[str, Any]] = {}
    input_records: dict[str, dict[str, Any]] = {}
    for name, relative_path in ARTIFACT_PATHS.items():
        artifacts[name], input_records[name] = load_json(relative_path)
        expect(
            input_records[name]["sha256"],
            EXPECTED_ARTIFACT_HASHES[name],
            f"preserved artifact SHA-256 {name}",
        )

    source_identity = validate_source_identity(artifacts)
    datasets = validate_datasets(artifacts)
    metrics = validate_and_extract_metrics(artifacts, datasets)
    evidence = {
        "schema_version": 1,
        "purpose": "Deterministic evidence ledger for the team-facing medicine-search handbook.",
        "claim_boundaries": {
            "accuracy": "Only labeled ranking cohorts report Hit@k or MRR.",
            "safety": "Contract pass counts are reported separately from ranking accuracy.",
            "regression": "Developer regression pass fractions are coverage evidence, not estimates of general accuracy.",
            "retrospective": "Catalog-derived and reviewed historical cohorts are not blind or clinical validation.",
        },
        "source_identity": source_identity,
        "dataset_identity": datasets,
        "input_artifacts": input_records,
        "metrics": metrics,
    }
    write_outputs(evidence)
    print(f"wrote {EVIDENCE_PATH.relative_to(REPO)} ({sha256_path(EVIDENCE_PATH)})")
    print(f"wrote {TEX_PATH.relative_to(REPO)} ({sha256_path(TEX_PATH)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

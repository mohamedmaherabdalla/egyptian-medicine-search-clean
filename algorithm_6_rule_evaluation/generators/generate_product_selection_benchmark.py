#!/usr/bin/env python3
"""Generate a strict, catalog-derived product-selection benchmark.

The generator never calls the search API.  It chooses exact catalog families
and product records first, derives simple strength/form evidence from the
frozen catalog, and then records the complete set of product IDs compatible
with that evidence.  Positive rows test exact product selection; conflict rows
test fail-closed behavior.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
PACKAGE = Path(__file__).resolve().parents[1]
CATALOG = REPO / "app" / "data" / "catalog.json"
OUTPUT = PACKAGE / "test_sets" / "generated" / "product_selection_strict.csv"
MANIFEST = PACKAGE / "test_sets" / "manifests" / "product_selection_strict.manifest.json"
SEED = "algorithm-6-product-selection-strict-v1"


FORM_PATTERNS = (
    ("tablet", re.compile(r"\b(?:F\.?\s*C\.?\s*)?(?:TAB|TABS|TABLET|TABLETS)\b", re.I)),
    ("capsule", re.compile(r"\b(?:CAP|CAPS|CAPSULE|CAPSULES)\b", re.I)),
    ("cream", re.compile(r"\bCREAM\b", re.I)),
    ("gel", re.compile(r"\bGEL\b", re.I)),
    ("ointment", re.compile(r"\b(?:OINT|OINTMENT)\b", re.I)),
    ("syrup", re.compile(r"\b(?:SYP|SYRUP)\b", re.I)),
    ("suspension", re.compile(r"\b(?:SUSP|SUSPENSION)\b", re.I)),
    ("vial", re.compile(r"\b(?:VIAL|VIALS)\b", re.I)),
    ("ampoule", re.compile(r"\b(?:AMP|AMPS|AMPOULE|AMPOULES)\b", re.I)),
    ("spray", re.compile(r"\bSPRAY\b", re.I)),
    ("drops", re.compile(r"\b(?:DROP|DROPS)\b", re.I)),
    ("suppository", re.compile(r"\b(?:SUPP|SUPPOSITORY|SUPPOSITORIES)\b", re.I)),
    ("patch", re.compile(r"\b(?:PATCH|PATCHES)\b", re.I)),
    ("sachet", re.compile(r"\b(?:SACHET|SACHETS)\b", re.I)),
    ("pen", re.compile(r"\b(?:PEN|PENS)\b", re.I)),
    ("cartridge", re.compile(r"\b(?:CARTRIDGE|CARTRIDGES)\b", re.I)),
    ("inhaler", re.compile(r"\b(?:INHALER|INHALATION)\b", re.I)),
)

SIMPLE_STRENGTH = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(MG|MCG|UG|G|GM|IU|MIU|%)"
    r"(?:\s*/\s*(\d+(?:\.\d+)?)?\s*(ML|L|G|GM|H|HR))?\s*$",
    re.I,
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(*values: object) -> str:
    return hashlib.sha256("|".join(map(str, values)).encode()).hexdigest()


def compact(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def decimal_text(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def canonical_strength(raw: object) -> str | None:
    text = str(raw or "").strip().upper().replace("I.U.", "IU").replace("I.U", "IU")
    if not text or ";" in text or "+" in text:
        return None
    match = SIMPLE_STRENGTH.fullmatch(text)
    if not match:
        return None
    amount = Decimal(match.group(1))
    unit = match.group(2).upper()
    if unit in {"MCG", "UG"}:
        amount *= Decimal("0.001")
        unit = "MG"
    elif unit in {"G", "GM"}:
        amount *= Decimal("1000")
        unit = "MG"
    elif unit == "MIU":
        amount *= Decimal("1000000")
        unit = "IU"
    numerator = f"{decimal_text(amount)}{unit}"
    denominator_amount = match.group(3)
    denominator_unit = match.group(4)
    if not denominator_unit:
        return numerator
    denominator = Decimal(denominator_amount or "1")
    denominator_unit = denominator_unit.upper()
    if denominator_unit == "L":
        denominator *= Decimal("1000")
        denominator_unit = "ML"
    elif denominator_unit in {"G", "GM"}:
        denominator *= Decimal("1000")
        denominator_unit = "MG"
    elif denominator_unit == "HR":
        denominator_unit = "H"
    return f"{numerator}/{decimal_text(denominator)}{denominator_unit}"


def form_token(record: dict[str, Any]) -> str:
    name = str(record.get("n") or "")
    return next((token for token, pattern in FORM_PATTERNS if pattern.search(name)), "")


def split_for_family(family: str) -> str:
    return "holdout" if int(stable_hash("split", family)[:8], 16) % 5 == 0 else "development"


def row_id(kind: str, family: str, context: str) -> str:
    return f"PCS-{kind[:3].upper()}-{stable_hash(SEED, kind, family, context)[:14].upper()}"


def sample(rows: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: stable_hash(SEED, row["case_id"]))[:count]


def build(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    all_by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        family = compact(record.get("b"))
        if family and record.get("id"):
            all_by_family[family].append(record)
        strength = canonical_strength(record.get("st"))
        if not family or not strength or not record.get("id"):
            continue
        enriched = dict(record)
        enriched["_family"] = family
        enriched["_strength"] = strength
        enriched["_form"] = form_token(record)
        by_family[family].append(enriched)

    strength_rows: list[dict[str, str]] = []
    form_rows: list[dict[str, str]] = []
    tie_rows: list[dict[str, str]] = []
    conflict_rows: list[dict[str, str]] = []

    for family, members in sorted(by_family.items()):
        complete_family = all_by_family[family]
        # A simple-string oracle is not allowed to ignore complex sibling
        # products.  Exclude the whole family if any sibling has a composite
        # catalog strength, a printed combination such as 10/40 MG, or a
        # printed concentration denominator missing from its ``st`` field.
        # These belong in the separately adjudicated parser regression set.
        unsafe_oracle = False
        for record in complete_family:
            raw_strength = str(record.get("st") or "").upper()
            printed = str(record.get("n") or "").upper()
            if not canonical_strength(raw_strength):
                unsafe_oracle = True
                break
            if re.search(r"\b\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?\s*(?:MG|MCG|UG|G|GM|IU|MIU|%)\b", printed):
                unsafe_oracle = True
                break
            if (
                re.search(r"(?:MG|MCG|UG|G|GM|IU|MIU|%)\s*/\s*(?:ML|L|G|GM|H|HR)\b", printed)
                and "/" not in raw_strength
            ):
                unsafe_oracle = True
                break
        if unsafe_oracle:
            continue
        by_strength: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_signature: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for member in members:
            by_strength[member["_strength"]].append(member)
            if member["_form"]:
                by_signature[(member["_strength"], member["_form"])].append(member)
        if len(by_strength) < 2:
            continue
        all_ids = {str(member["id"]) for member in complete_family}

        for strength, compatible in sorted(by_strength.items()):
            allowed = sorted({str(member["id"]) for member in compatible})
            forbidden = sorted(all_ids - set(allowed))
            if not forbidden or len(allowed) > 6:
                continue
            raw_context = min(str(member.get("st") or "") for member in compatible)
            kind = "tie" if len(allowed) > 1 else "strength"
            target = tie_rows if kind == "tie" else strength_rows
            target.append({
                "case_id": row_id(kind, family, raw_context),
                "evaluation_kind": "benchmark",
                "case_type": "positive_tie" if kind == "tie" else "positive",
                "stratum": "exact_strength_tie" if kind == "tie" else "exact_strength_unique",
                "split": split_for_family(family),
                "query": str(compatible[0].get("b") or family),
                "product_context": raw_context,
                "expected_family": family,
                "acceptable_product_ids": ";".join(allowed),
                "forbidden_product_ids": ";".join(forbidden),
                "expected_decision": "product_context_selection",
                "match_policy": "all_expected_only",
                "generation_method": "catalog family chosen before evaluation; simple canonical strength uniquely defines the allowed product-ID set",
                "source_family_key": family,
                "source_record_ids": ";".join(allowed),
                "notes": "Exact family query isolates strict product selection from name-retrieval accuracy.",
            })

        for (strength, form), compatible in sorted(by_signature.items()):
            same_strength = by_strength[strength]
            other_forms = {member["_form"] for member in same_strength if member["_form"] and member["_form"] != form}
            if not other_forms:
                continue
            allowed = sorted({str(member["id"]) for member in compatible})
            forbidden = sorted({str(member["id"]) for member in same_strength} - set(allowed))
            if not forbidden or len(allowed) > 6:
                continue
            raw_strength = min(str(member.get("st") or "") for member in compatible)
            context = f"{raw_strength} {form}"
            form_rows.append({
                "case_id": row_id("form", family, context),
                "evaluation_kind": "benchmark",
                "case_type": "positive",
                "stratum": "same_strength_form_disambiguation",
                "split": split_for_family(family),
                "query": str(compatible[0].get("b") or family),
                "product_context": context,
                "expected_family": family,
                "acceptable_product_ids": ";".join(allowed),
                "forbidden_product_ids": ";".join(forbidden),
                "expected_decision": "product_context_selection",
                "match_policy": "all_expected_only",
                "generation_method": "same family and canonical strength but different explicit catalog form tokens; target form chosen before evaluation",
                "source_family_key": family,
                "source_record_ids": ";".join(allowed),
                "notes": f"Competing forms in family: {','.join(sorted(other_forms | {form}))}.",
            })

        numeric_strengths = []
        for strength in by_strength:
            match = re.match(r"^(\d+(?:\.\d+)?)(MG|IU|%)$", strength)
            if match:
                numeric_strengths.append((Decimal(match.group(1)), match.group(2)))
        if numeric_strengths:
            amount, unit = max(numeric_strengths)
            impossible = f"{decimal_text(amount * Decimal('10') + Decimal('7'))}{unit}"
            if impossible not in by_strength:
                conflict_rows.append({
                    "case_id": row_id("conflict", family, impossible),
                    "evaluation_kind": "safety",
                    "case_type": "negative",
                    "stratum": "impossible_strength_abstention",
                    "split": split_for_family(family),
                    "query": str(members[0].get("b") or family),
                    "product_context": impossible,
                    "expected_family": family,
                    "acceptable_product_ids": "",
                    "forbidden_product_ids": ";".join(sorted(all_ids)),
                    "expected_decision": "product_context_no_compatible_product",
                    "match_policy": "abstain_no_product",
                    "generation_method": "deterministic out-of-catalog strength derived from the maximum simple strength in an exact family",
                    "source_family_key": family,
                    "source_record_ids": "",
                    "notes": "Every product ID is forbidden; the API must retain family identity without selecting a product.",
                })

    chosen = (
        sample(strength_rows, 240)
        + sample(form_rows, 80)
        + sample(tie_rows, 40)
        + sample(conflict_rows, 80)
    )
    return sorted(chosen, key=lambda row: row["case_id"])


def main() -> None:
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    rows = build(payload["records"])
    if not rows:
        raise SystemExit("no product benchmark rows generated")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    strata: dict[str, int] = defaultdict(int)
    splits: dict[str, int] = defaultdict(int)
    for row in rows:
        strata[row["stratum"]] += 1
        splits[row["split"]] += 1
    manifest = {
        "dataset_id": "product_selection_strict_v1",
        "evaluation_scope": "strict catalog product-ID selection and fail-closed conflict handling",
        "generator": str(Path(__file__).relative_to(REPO)),
        "generator_sha256": sha256_path(Path(__file__)),
        "seed": SEED,
        "catalog_sha256": sha256_path(CATALOG),
        "selection_policy": "catalog/source only; generator never imports or calls the search algorithm",
        "split_policy": "SHA-256 exact family key modulo 5; family-stable",
        "rows": len(rows),
        "by_stratum": dict(sorted(strata.items())),
        "by_split": dict(sorted(splits.items())),
        "dataset_sha256": sha256_path(OUTPUT),
        "limitations": [
            "The benchmark uses exact family queries, so it measures product selection rather than name retrieval.",
            "Only simple catalog strength strings and explicit form tokens are included; parser edge cases remain regression tests.",
            "Catalog-derived labels are retrospective and are not clinical validation.",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

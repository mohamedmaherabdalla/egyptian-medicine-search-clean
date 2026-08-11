#!/usr/bin/env python3
"""Rank catalog products after Algorithm 6 has ranked medicine families."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Iterable


ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
UNIT_ALIASES = {
    "UG": "MCG",
    "GM": "G",
    "U": "IU",
}
UNIT_FACTORS = {
    "MCG": ("mass", Decimal("1")),
    "MG": ("mass", Decimal("1000")),
    "G": ("mass", Decimal("1000000")),
    "KG": ("mass", Decimal("1000000000")),
    "ML": ("volume", Decimal("1")),
    "L": ("volume", Decimal("1000")),
    "IU": ("activity", Decimal("1")),
    "%": ("percent", Decimal("1")),
}
STRENGTH_RE = re.compile(
    r"(?P<amount>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>MCG|UG|MG|GM|KG|IU|ML|G|L|U|%)"
    r"(?:\s*/\s*(?P<den_amount>\d+(?:\.\d+)?)?\s*"
    r"(?P<den_unit>MCG|UG|MG|GM|KG|IU|ML|G|L|U|%))?"
)
PACKAGE_RE = re.compile(
    r"\b(\d+)\s*(?:FCT\s*)?"
    r"(?:TAB(?:LET)?S?|CAP(?:SULE)?S?|SACHETS?|VIALS?|AMPS?|AMPOULES?)\b"
)

FORM_ALIASES = {
    "TAB": "tablet",
    "TABS": "tablet",
    "TABLET": "tablet",
    "TABLETS": "tablet",
    "FCT": "tablet",
    "CAP": "capsule",
    "CAPS": "capsule",
    "CAPSULE": "capsule",
    "CAPSULES": "capsule",
    "PILL": "tablet",
    "PILLS": "tablet",
    "SYRUP": "syrup",
    "SYP": "syrup",
    "SUSP": "suspension",
    "SUSPENSION": "suspension",
    "DROPS": "drops",
    "DROP": "drops",
    "VIAL": "injection",
    "VIALS": "injection",
    "AMP": "injection",
    "AMPS": "injection",
    "AMPOULE": "injection",
    "AMPOULES": "injection",
    "INJ": "injection",
    "INJECTION": "injection",
    "SC": "injection",
    "INFUSION": "injection",
    "CREAM": "cream",
    "GEL": "gel",
    "OINT": "ointment",
    "OINTMENT": "ointment",
    "LOTION": "lotion",
    "SHAMPOO": "shampoo",
    "POWDER": "powder",
    "SPRAY": "spray",
    "SUPP": "suppository",
    "SUPPOSITORY": "suppository",
    "SACHET": "sachet",
    "SACHETS": "sachet",
}
ROUTE_ALIASES = {
    "IV": "injection",
    "INTRAVENOUS": "injection",
    "IM": "injection",
    "INTRAMUSCULAR": "injection",
    "ORAL": "oral",
    "PO": "oral",
    "TOPICAL": "topical",
    "OPHTHALMIC": "ophthalmic",
    "OCULAR": "ophthalmic",
    "NASAL": "nasal",
    "VAGINAL": "vaginal",
    "RECTAL": "rectal",
}
RELEASE_ALIASES = {
    "CR": "controlled_release",
    "ER": "extended_release",
    "XR": "extended_release",
    "SR": "sustained_release",
    "MR": "modified_release",
    "RETARD": "modified_release",
    "CHRONO": "modified_release",
    "PROLONGED": "modified_release",
    "XL": "extended_release",
}


@dataclass(frozen=True, order=True)
class Measurement:
    kind: str
    value: Decimal
    denominator_kind: str = ""
    denominator_value: Decimal = Decimal("0")


@dataclass(frozen=True)
class ContextEvidence:
    strengths: frozenset[Measurement]
    forms: frozenset[str]
    routes: frozenset[str]
    release_types: frozenset[str]
    package_counts: frozenset[int]

    @property
    def present(self) -> bool:
        return any(
            (
                self.strengths,
                self.forms,
                self.routes,
                self.release_types,
                self.package_counts,
            )
        )


@dataclass(frozen=True)
class ProductCatalog:
    records_by_group: dict[str, tuple[dict[str, Any], ...]]
    compact_key: Callable[[Any], str]


def normalize_context(value: Any) -> str:
    text = str(value or "").translate(ARABIC_DIGITS).upper()
    for source, replacement in (
        ("ميكروجرام", " MCG "),
        ("مجم", " MG "),
        ("ملجم", " MG "),
        ("جرام", " G "),
        ("جم", " G "),
        ("مل", " ML "),
        ("اقراص", " TABLETS "),
        ("أقراص", " TABLETS "),
        ("قرص", " TABLET "),
        ("كبسولات", " CAPSULES "),
        ("كبسولة", " CAPSULE "),
        ("شراب", " SYRUP "),
        ("حقن", " INJECTION "),
    ):
        text = text.replace(source, replacement)
    for pattern, replacement in (
        (r"\bMICROGRAMS?\b", " MCG "),
        (r"\bMILLIGRAMS?\b", " MG "),
        (r"\bKILOGRAMS?\b", " KG "),
        (r"\bGRAMS?\b", " G "),
        (r"\bMILLILIT(?:ER|RE)S?\b", " ML "),
        (r"\bLIT(?:ER|RE)S?\b", " L "),
        (r"\bM\s*\.\s*G\.?\b", " MG "),
        (r"\bG\s*\.\s*M\.?\b", " G "),
        (r"\bM\s*\.\s*L\.?\b", " ML "),
        (r"\bI\s*\.\s*U\.?\b", " IU "),
        (r"\bF\s*\.\s*C\s*\.\s*(?=TABS?\b)", " FCT "),
    ):
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"(\d),(?=\d{3}\b)", r"\1", text).replace(",", ".")
    text = re.sub(r"\bI\s*\.?\s*V\.?(?=[^A-Z]|$)", " IV ", text)
    text = re.sub(r"\bI\s*\.?\s*M\.?(?=[^A-Z]|$)", " IM ", text)
    text = re.sub(r"\bF\s*\.?\s*C\s*\.?\s*T\.?(?=[^A-Z]|$)", " FCT ", text)
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9%./]+", " ", text)).strip()


def measurement(
    amount: str,
    unit: str,
    denominator_amount: str = "",
    denominator_unit: str = "",
) -> Measurement:
    unit = UNIT_ALIASES.get(unit, unit)
    kind, factor = UNIT_FACTORS[unit]
    denominator_kind = ""
    denominator_value = Decimal("0")
    if denominator_unit:
        denominator_unit = UNIT_ALIASES.get(denominator_unit, denominator_unit)
        denominator_kind, denominator_factor = UNIT_FACTORS[denominator_unit]
        denominator_value = Decimal(denominator_amount or "1") * denominator_factor
    return Measurement(
        kind=kind,
        value=Decimal(amount) * factor,
        denominator_kind=denominator_kind,
        denominator_value=denominator_value,
    )


def parse_strengths(value: Any) -> frozenset[Measurement]:
    text = normalize_context(value)
    return frozenset(
        measurement(
            match.group("amount"),
            match.group("unit"),
            match.group("den_amount") or "",
            match.group("den_unit") or "",
        )
        for match in STRENGTH_RE.finditer(text)
    )


def mapped_tokens(text: str, aliases: dict[str, str]) -> frozenset[str]:
    tokens = set(re.findall(r"[A-Z]+", text))
    return frozenset(aliases[token] for token in tokens if token in aliases)


def parse_evidence(value: Any) -> ContextEvidence:
    text = normalize_context(value)
    return ContextEvidence(
        strengths=parse_strengths(text),
        forms=mapped_tokens(text, FORM_ALIASES),
        routes=mapped_tokens(text, ROUTE_ALIASES),
        release_types=mapped_tokens(text, RELEASE_ALIASES),
        package_counts=frozenset(int(match) for match in PACKAGE_RE.findall(text)),
    )


def build_product_catalog(
    records: Iterable[dict[str, Any]],
    family_to_group: dict[str, str],
    compact_key: Callable[[Any], str],
) -> ProductCatalog:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        family_key = compact_key(record.get("b") or record.get("n") or "")
        if not family_key:
            continue
        group_key = family_to_group.get(family_key, family_key)
        grouped.setdefault(group_key, []).append(record)
    return ProductCatalog(
        records_by_group={
            key: tuple(sorted(values, key=lambda row: str(row.get("n") or "").casefold()))
            for key, values in grouped.items()
        },
        compact_key=compact_key,
    )


def product_evidence(record: dict[str, Any]) -> ContextEvidence:
    text = " ".join(
        str(record.get(field) or "")
        for field in ("st", "n", "f", "r")
    )
    parsed = parse_evidence(text)
    explicit_forms = frozenset(
        value
        for value in (str(record.get("f") or ""), str(record.get("r") or ""))
        if value and value != "unknown"
    )
    return ContextEvidence(
        strengths=parsed.strengths,
        forms=parsed.forms | explicit_forms,
        routes=parsed.routes | explicit_forms,
        release_types=parsed.release_types,
        package_counts=parsed.package_counts,
    )


def score_product(
    query: ContextEvidence,
    record: dict[str, Any],
) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    product = product_evidence(record)
    score = 0
    matches: list[str] = []
    conflicts: list[str] = []

    exact_strengths = query.strengths & product.strengths
    numerator_strengths = {
        left
        for left in query.strengths - exact_strengths
        if any(
            left.kind == right.kind and left.value == right.value
            for right in product.strengths
        )
    }
    covered_strengths = exact_strengths | numerator_strengths
    missing_strengths = query.strengths - covered_strengths
    if query.strengths and not missing_strengths:
        score += 120 + 10 * len(exact_strengths)
        matches.append("strength_exact")
    elif covered_strengths:
        score += 55 + 10 * len(covered_strengths) - 65 * len(missing_strengths)
        matches.append("strength_numerator_match")
        conflicts.append("strength_conflict")
    elif query.strengths and product.strengths:
        score -= 90
        conflicts.append("strength_conflict")

    for query_values, product_values, weight, match_name, conflict_name in (
        (query.forms, product.forms, 45, "dosage_form_match", "dosage_form_conflict"),
        (query.routes, product.routes, 35, "route_match", "route_conflict"),
        (query.release_types, product.release_types, 35, "release_type_match", "release_type_conflict"),
        (query.package_counts, product.package_counts, 20, "package_count_match", "package_count_conflict"),
    ):
        if not query_values:
            continue
        if query_values & product_values:
            score += weight
            matches.append(match_name)
        elif product_values:
            score -= weight // 2
            conflicts.append(conflict_name)
    return score, tuple(matches), tuple(conflicts)


def rerank_products(
    response: dict[str, Any],
    raw_query: str,
    catalog: ProductCatalog,
    *,
    limit: int,
) -> dict[str, Any]:
    query = parse_evidence(raw_query)
    if not query.present or not response.get("results"):
        return response

    grouped_results: dict[str, list[dict[str, Any]]] = {}
    group_order: list[str] = []
    for result in response["results"]:
        group_key = catalog.compact_key(
            result.get("variant_group") or result.get("name") or ""
        )
        if not group_key:
            continue
        if group_key not in grouped_results:
            grouped_results[group_key] = []
            group_order.append(group_key)
        grouped_results[group_key].append(result)

    ranked_groups: list[tuple[int, int, dict[str, Any]]] = []
    product_candidates = 0
    for group_position, group_key in enumerate(group_order):
        family_results = grouped_results[group_key]
        records = catalog.records_by_group.get(group_key, ())
        if not records:
            ranked_groups.append((group_position, 0, dict(family_results[0])))
            continue
        base_rank = {
            catalog.compact_key(item.get("name") or ""): index
            for index, item in enumerate(family_results)
        }
        scored = []
        for record in records:
            score, matches, conflicts = score_product(query, record)
            family_key = catalog.compact_key(record.get("b") or record.get("n") or "")
            scored.append(
                (
                    -score,
                    base_rank.get(family_key, 999),
                    str(record.get("n") or "").casefold(),
                    record,
                    matches,
                    conflicts,
                    score,
                )
            )
        product_candidates += len(scored)
        _, selected_family_rank, _, record, matches, conflicts, score = min(scored)
        source = (
            family_results[selected_family_rank]
            if selected_family_rank < len(family_results)
            else family_results[0]
        )
        result = dict(source)
        result.update(
            {
                "name_match_rank": source.get("rank"),
                "name_match_name": source.get("name"),
                "name": record.get("b") or record.get("n") or source.get("name"),
                "candidate_canonical_name": record.get("b") or source.get("name"),
                "commercial_name": record.get("n") or source.get("commercial_name"),
                "selected_product_key": catalog.compact_key(record.get("n") or ""),
                "product_context_score": score,
                "product_context_rank": 1,
                "matched_context": "|".join(matches),
                "context_conflicts": "|".join(conflicts),
            }
        )
        ranked_groups.append((group_position, score, result))

    original_order = [item[2].get("name") for item in ranked_groups]
    has_exact_strength = bool(query.strengths) and any(
        "strength_exact" in split_evidence(item[2].get("matched_context"))
        for item in ranked_groups
    )
    if has_exact_strength:
        ranked_groups.sort(key=lambda item: (-(item[1] - 14 * item[0]), item[0]))
    reranked = [item[2] for item in ranked_groups]
    context_family_reranked = original_order != [item.get("name") for item in reranked]

    output = dict(response)
    output.update(
        {
            "name_decision_type": response.get("decision_type"),
            "decision_type": "product_context_selection",
            "message": "Medicine families were ranked by name, then products were ranked by normalized context evidence.",
            "product_context": {
                "strengths": [format_measurement(value) for value in sorted(query.strengths)],
                "forms": sorted(query.forms),
                "routes": sorted(query.routes),
                "release_types": sorted(query.release_types),
                "package_counts": sorted(query.package_counts),
                "candidate_products": product_candidates,
            },
            "context_family_reranked": context_family_reranked,
            "results": reranked[:limit],
        }
    )
    for rank, result in enumerate(output["results"], 1):
        result["rank"] = rank
        result["product_context_rank"] = rank
    return output


def split_evidence(value: Any) -> frozenset[str]:
    return frozenset(part for part in str(value or "").split("|") if part)


def format_measurement(value: Measurement) -> str:
    base = f"{value.kind}:{value.value.normalize()}"
    if value.denominator_kind:
        return f"{base}/{value.denominator_kind}:{value.denominator_value.normalize()}"
    return base

#!/usr/bin/env python3
"""Rank catalog products after Algorithm 6 has ranked medicine families."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Iterable


ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
CONTEXT_LITERAL_REPLACEMENTS = (
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
)
UNIT_ALIASES = {
    "UG": "MCG",
    "MCL": "UL",
    "GM": "G",
    "U": "IU",
    "UNIT": "IU",
    "UNITS": "IU",
    "MIU": "MIU",
    "HR": "H",
    "HOUR": "H",
    "HOURS": "H",
}
UNIT_FACTORS = {
    "MCG": ("mass", Decimal("1")),
    "MG": ("mass", Decimal("1000")),
    "G": ("mass", Decimal("1000000")),
    "KG": ("mass", Decimal("1000000000")),
    "UL": ("volume", Decimal("0.001")),
    "ML": ("volume", Decimal("1")),
    "L": ("volume", Decimal("1000")),
    "IU": ("activity", Decimal("1")),
    "MIU": ("activity", Decimal("1000000")),
    "MMOL": ("substance", Decimal("1")),
    "MEQ": ("equivalent", Decimal("1")),
    "H": ("time", Decimal("1")),
    "%": ("percent", Decimal("1")),
}
UNIT_PATTERN = (
    r"(?:(?:MCG|MCL|UG|MG|GM|KG|MMOL|MEQ|MIU|UNITS|UNIT|IU|UL|ML|G|L|U)"
    r"(?![A-Z])|%)"
)
DENOMINATOR_UNIT_PATTERN = (
    rf"(?:{UNIT_PATTERN}|(?:HR|HOURS|HOUR|H)(?![A-Z]))"
)
STRENGTH_RE = re.compile(
    r"(?<![\d.])(?P<amount>(?:\d+(?:\.\d+)?|\.\d+))\s*"
    rf"(?P<unit>{UNIT_PATTERN})"
    r"(?:\s*/\s*(?P<den_amount>\d+(?:\.\d+)?)?\s*"
    rf"(?P<den_unit>{DENOMINATOR_UNIT_PATTERN}))?"
)
COMBINATION_STRENGTH_RE = re.compile(
    r"(?<![\d.])(?P<amounts>\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)+)\s*"
    r"(?P<unit>(?:MCG|UG|MG|GM|KG|MMOL|MEQ|MIU|UNITS|UNIT|IU|G|U)"
    r"(?![A-Z])|%)"
)
EXPLICIT_COMBINATION_RE = re.compile(
    rf"(?<![\d.])(?P<components>"
    rf"\d+(?:\.\d+)?\s*(?:{UNIT_PATTERN})"
    rf"(?:\s*/\s*\d+(?:\.\d+)?\s*(?:{UNIT_PATTERN}))+"
    rf")"
)
QUALIFIED_COMPONENT_RE = re.compile(
    rf"(?<![\d.])(?P<amount>(?:\d+(?:\.\d+)?|\.\d+))\s*(?P<unit>{UNIT_PATTERN})"
)
SHARED_DENOMINATOR_COMBINATION_RE = re.compile(
    rf"(?<![\d.])(?P<components>"
    rf"(?:\d+(?:\.\d+)?\s*{UNIT_PATTERN}\s*\+\s*)+"
    rf"\d+(?:\.\d+)?\s*{UNIT_PATTERN})"
    rf"\s*/\s*(?P<den_amount>\d+(?:\.\d+)?)?\s*"
    rf"(?P<den_unit>(?:MCL|UL|ML|L|GM|G|KG|HR|HOURS|HOUR|H)(?![A-Z]))"
)
SHARED_SHORTHAND_DENOMINATOR_RE = re.compile(
    r"(?<![\d.])(?P<amounts>\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)+)\s*"
    rf"(?P<unit>{UNIT_PATTERN})\s*/\s*"
    r"(?P<den_amount>\d+(?:\.\d+)?)?\s*"
    r"(?P<den_unit>(?:MCL|UL|ML|L|GM|G|KG|HR|HOURS|HOUR|H)(?![A-Z]))"
)
STRUCTURAL_RATIO_RE = re.compile(
    r"(?<![\d.])(?P<left>\d{1,6})\s*(?P<separator>[:/])\s*"
    r"(?P<right>\d{1,6})(?![\d.])"
    r"(?!\s*(?:MCG|MCL|UG|MG|GM|KG|MMOL|MEQ|MIU|UNITS?|IU|UL|ML|G|L|U)\b)"
)
NUMBER_RE = re.compile(r"(?<![A-Z\d.])\d+(?:\.\d+)?(?![A-Z\d.])")
PACKAGE_FORM_RE = re.compile(
    r"(?<![A-Z\d.])(?P<count>\d{1,4})(?![\d.])\s*"
    r"(?:(?:FCT|FC|FILM|COATED|CHEW|CHEWABLE|DISPERSIBLE|ORAL|DIS|SOFTGELS?|"
    r"HARD|GELATIN|VEG|VEGETARIAN|PREF|PREFILLED|ADULT|INFANTILE|SUBLINGUAL|IM|IV|SC|"
    r"SR|MR|ER|CR|XR|EXT|EXTENDED|REL|RELEASE|PROL|PROLONGED|SUST|SUSTAINED|MOD|MODIFIED|"
    r"EFF|EFFERVESCENT|GR|GRAN|GRANULES?|IN|OF)\.?\s*){0,6}"
    r"(?P<form>TAB(?:LET)?S?|CAP(?:SULE)?S?|PILLS?|SACHETS?|VIALS?|AMPS?|"
    r"AMPOULES?|DOSES?|ACTUATIONS?|PATCH(?:ES)?|SUPP(?:S|OSITORY|OSITORIES)?|"
    r"PENS?|SYRINGES?|CARTRIDGES?|INHALERS?|NEBULES?|DROPS?|SPRAYS?|OVULES?)\b"
)
MULTIPACK_FORM_RE = re.compile(
    r"(?<![A-Z\d.])(?P<outer>\d{1,4})\s*[*X]\s*(?P<inner>\d{1,4})\s*"
    r"(?:(?:FCT|FC|FILM|COATED|CHEW|CHEWABLE|DISPERSIBLE|ORAL|DIS|"
    r"SOFTGELS?|GELATIN|VEG|VEGETARIAN)\.?\s*){0,6}"
    r"(?P<form>TAB(?:LET)?S?|CAP(?:SULE)?S?|PILLS?|SACHETS?|VIALS?|AMPS?|"
    r"AMPOULES?|DOSES?|PATCH(?:ES)?|PENS?|SYRINGES?)\b"
)
EXPLICIT_PACKAGE_RE = re.compile(
    r"(?<![\d.])(?P<count>\d{1,4})(?![\d.])\s*"
    r"(?:PACKS?|PACKETS?|BOX(?:ES)?|BOTTLES?|PIECES?|PCS?|PENS?)\b"
)
UNIT_DOSE_PACKAGE_RE = re.compile(
    r"(?<![\d.])(?P<count>\d{1,4})(?![\d.])\s+(?:UNITS?|IU)\s+DOSES?\b"
)
MAX_PLAUSIBLE_PACKAGE_COUNT = 400
CONTEXT_FAMILY_ADMISSION_LIMIT = 3
CONTEXT_FAMILY_MAX_RAW_EDIT_DISTANCE = 2.0
CONTEXT_FAMILY_MIN_LEVENSHTEIN_SIMILARITY = 0.60
CONTEXT_SUFFIX_FILLER_TOKENS = frozenset(
    {
        "AND",
        "COATED",
        "DIS",
        "DOSE",
        "FC",
        "FOR",
        "IN",
        "OF",
        "PER",
        "RELEASE",
    }
)

FORM_ALIASES = {
    "TAB": "tablet",
    "TABS": "tablet",
    "TABLET": "tablet",
    "TABLETS": "tablet",
    "CAPLET": "tablet",
    "CAPLETS": "tablet",
    "CHEWABLE": "chewable_tablet",
    "CHEW": "chewable_tablet",
    "DISPERSIBLE": "dispersible_tablet",
    "DIS": "dispersible_tablet",
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
    "VIAL": "vial",
    "VIALS": "vial",
    "AMP": "ampoule",
    "AMPS": "ampoule",
    "AMPOULE": "ampoule",
    "AMPOULES": "ampoule",
    "SYRINGE": "syringe",
    "SYRINGES": "syringe",
    "PEN": "pen",
    "PENS": "pen",
    "CARTRIDGE": "cartridge",
    "CARTRIDGES": "cartridge",
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
    "EFF": "effervescent",
    "EFFERVESCENT": "effervescent",
    "GR": "granules",
    "GRAN": "granules",
    "GRANULE": "granules",
    "GRANULES": "granules",
    "SOL": "solution",
    "SOLUTION": "solution",
    "OVULE": "ovule",
    "OVULES": "ovule",
    "PATCH": "patch",
    "PATCHES": "patch",
    "INHALER": "inhalation",
    "INHALATION": "inhalation",
    "SUBLINGUAL": "sublingual",
    "NEBULE": "inhalation",
    "NEBULES": "inhalation",
}
ROUTE_ALIASES = {
    "IV": "iv",
    "INTRAVENOUS": "iv",
    "IM": "im",
    "INTRAMUSCULAR": "im",
    "ORAL": "oral",
    "PO": "oral",
    "TOPICAL": "topical",
    "OPHTHALMIC": "ophthalmic",
    "OCULAR": "ophthalmic",
    "NASAL": "nasal",
    "VAGINAL": "vaginal",
    "RECTAL": "rectal",
    "SC": "sc",
    "SUBCUTANEOUS": "sc",
    "SUBLINGUAL": "sublingual",
    "INHALATION": "inhalation",
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
    "EXTENDED": "extended_release",
    "SUSTAINED": "sustained_release",
    "CONTROLLED": "controlled_release",
    "MODIFIED": "modified_release",
}

SPECIFIC_ORAL_SOLID_FORMS = frozenset(
    {
        "tablet",
        "chewable_tablet",
        "dispersible_tablet",
        "capsule",
        "sachet",
        "effervescent",
        "granules",
    }
)
ORAL_SOLID_MODIFIERS = frozenset(
    {"chewable_tablet", "dispersible_tablet", "effervescent"}
)
TOPICAL_FORMS = frozenset({"cream", "gel", "ointment", "lotion", "shampoo"})
INJECTION_ROUTES = frozenset({"injection", "iv", "im", "sc"})


@dataclass(frozen=True, order=True)
class Measurement:
    kind: str
    value: Decimal
    denominator_kind: str = ""
    denominator_value: Decimal = Decimal("0")
    observed_value: Decimal = field(default=Decimal("0"), compare=False)
    observed_unit: str = field(default="", compare=False)


@dataclass(frozen=True)
class ContextEvidence:
    strengths: tuple[Measurement, ...]
    bare_numbers: frozenset[Decimal]
    ambiguous_numbers: frozenset[Decimal]
    presentation_quantities: tuple[Measurement, ...]
    forms: frozenset[str]
    routes: frozenset[str]
    release_types: frozenset[str]
    package_counts: frozenset[int]
    structural_ratios: frozenset[str]
    invalid_numeric: bool

    @property
    def present(self) -> bool:
        return any(
            (
                self.strengths,
                self.bare_numbers,
                self.ambiguous_numbers,
                self.presentation_quantities,
                self.forms,
                self.routes,
                self.release_types,
                self.package_counts,
                self.structural_ratios,
                self.invalid_numeric,
            )
        )


@dataclass(frozen=True)
class ProductCatalog:
    records_by_group: dict[str, tuple[dict[str, Any], ...]]
    records_by_family: dict[str, tuple[dict[str, Any], ...]]
    group_names: dict[str, str]
    family_names: dict[str, str]
    family_group_keys: dict[str, str]
    numeric_alias_groups: dict[str, tuple[str, ...]]
    numeric_brand_alias_families: dict[str, tuple[str, ...]]
    compact_key: Callable[[Any], str]


@dataclass(frozen=True)
class ProductScore:
    score: int
    matches: tuple[str, ...]
    conflicts: tuple[str, ...]
    compatible: bool
    exact_strength_signature: bool
    numeric_match: bool


def normalize_context(value: Any) -> str:
    text = (
        str(value or "")
        .translate(ARABIC_DIGITS)
        .replace("µ", "U")
        .replace("μ", "U")
        .replace("٫", ".")
        .replace("٬", ",")
        .upper()
    )
    text = re.sub(r"(?<=\d)\s*[*×]\s*(?=\d)", "X", text)
    for source, replacement in CONTEXT_LITERAL_REPLACEMENTS:
        text = text.replace(source, replacement)
    # Normalize dotted label modifiers before generic punctuation cleanup.
    # In particular, `30 H.G. CAPS` is a hard-gelatin pack, not 30 hours.
    for pattern, replacement in (
        (r"(?<![A-Z])H\s*\.\s*G\.?(?![A-Z])", " HARD GELATIN "),
        (r"(?<![A-Z])EXT\s*\.?\s*REL\.?(?![A-Z])", " ER "),
        (r"(?<![A-Z])PROL\s*\.?\s*REL\.?(?![A-Z])", " ER "),
        (r"(?<![A-Z])SUST\s*\.?\s*REL\.?(?![A-Z])", " SR "),
        (r"(?<![A-Z])MOD\s*\.?\s*REL\.?(?![A-Z])", " MR "),
        (r"(?<![A-Z])S\s*\.\s*R\.?(?![A-Z])", " SR "),
        (r"(?<![A-Z])M\s*\.\s*R\.?(?![A-Z])", " MR "),
        (r"(?<![A-Z])E\s*\.\s*R\.?(?![A-Z])", " ER "),
        (r"(?<![A-Z])C\s*\.\s*R\.?(?![A-Z])", " CR "),
        (r"(?<![A-Z])X\s*\.\s*R\.?(?![A-Z])", " XR "),
    ):
        text = re.sub(pattern, replacement, text)
    # Dotted abbreviations occur both attached to numbers (`100I.U.`) and
    # before slash denominators (`200 I.U./ML`). Normalize them before the
    # word-based rules so a trailing dot cannot break the concentration.
    for pattern, replacement in (
        (r"(?<![A-Z])M\s*\.\s*I\s*\.\s*U\.?(?![A-Z])", " MIU "),
        (r"(?<![A-Z])I\s*\.\s*U\.?(?![A-Z])", " IU "),
        (r"(?<![A-Z])M\s*\.\s*G\.?(?![A-Z])", " MG "),
        (r"(?<![A-Z])G\s*\.\s*M\.?(?![A-Z])", " G "),
        (r"(?<![A-Z])M\s*\.\s*L\.?(?![A-Z])", " ML "),
        (r"(?<![A-Z])U\s*\.\s*G\.?(?![A-Z])", " MCG "),
    ):
        text = re.sub(pattern, replacement, text)
    # A few activity labels group thousands with spaces rather than comma/dot.
    # Scope the rewrite to an immediately following activity unit.
    text = re.sub(
        r"(?<![\d./:])(\d{1,3}(?:\s+\d{3})+)(?=\s*(?:MIU|IU|UNITS?|U)\b)",
        lambda match: re.sub(r"\s+", "", match.group(1)),
        text,
    )
    # Egyptian labels use a full stop as an activity-unit thousands separator
    # (for example 200.000 I.U.). Limit this rewrite to IU so ordinary decimal
    # doses such as 1.2 G and 0.5 MG retain their decimal meaning.
    text = re.sub(
        r"(?<![\d.])(\d{1,3})\.(\d{3})(?=\s*(?:IU|UNITS?|U)\b)",
        r"\1\2",
        text,
    )
    for pattern, replacement in (
        (r"\bMICROGRAMS?\b", " MCG "),
        (r"\bMICROLIT(?:ER|RE)S?\b", " UL "),
        (r"\bMILLIGRAMS?\b", " MG "),
        (r"\bMILLIMOLES?\b", " MMOL "),
        (r"\bMILLIEQUIVALENTS?\b", " MEQ "),
        (r"\bKILOGRAMS?\b", " KG "),
        (r"\bGRAMS?\b", " G "),
        (r"\bMILLILIT(?:ER|RE)S?\b", " ML "),
        (r"\bLIT(?:ER|RE)S?\b", " L "),
        (r"\bM\s*\.\s*G\.?\b", " MG "),
        (r"\bG\s*\.\s*M\.?\b", " G "),
        (r"\bM\s*\.\s*L\.?\b", " ML "),
        (r"\bI\s*\.\s*U\.?\b", " IU "),
        (r"\bUNITS?\b", " IU "),
        (r"\bF\s*\.\s*C\s*\.\s*(?=TABS?\b)", " FCT "),
    ):
        text = re.sub(pattern, replacement, text)
    # A comma can be a thousands separator, a decimal separator, or ordinary
    # field punctuation.  Preserve only the first two numeric cases; turning
    # `600, tablets` into `600. TABLETS` would hide the bare number from the
    # boundary-aware number parser.
    text = re.sub(r"(?<![\d])([1-9]\d*),(?=\d{3}\b)", r"\1", text)
    text = re.sub(r"(?<=\d),(?=\d)", ".", text).replace(",", " ")
    text = re.sub(r"\bI\s*\.?\s*V\.?(?=[^A-Z]|$)", " IV ", text)
    text = re.sub(r"\bI\s*\.?\s*M\.?(?=[^A-Z]|$)", " IM ", text)
    text = re.sub(r"\bF\s*\.?\s*C\s*\.?\s*T\.?(?=[^A-Z]|$)", " FCT ", text)
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9%./:+]+", " ", text)).strip()


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
        observed_value=Decimal(amount),
        observed_unit=unit,
    )


def parse_strengths(value: Any) -> tuple[Measurement, ...]:
    """Parse complete dose signatures, preserving repeated combination components."""

    text = UNIT_DOSE_PACKAGE_RE.sub(" ", normalize_context(value))
    strengths: list[Measurement] = []
    masked = list(text)
    for match in SHARED_DENOMINATOR_COMBINATION_RE.finditer(text):
        components = tuple(QUALIFIED_COMPONENT_RE.finditer(match.group("components")))
        strengths.extend(
            measurement(
                component.group("amount"),
                component.group("unit"),
                match.group("den_amount") or "",
                match.group("den_unit"),
            )
            for component in components
        )
        masked[match.start() : match.end()] = " " * (match.end() - match.start())
    current = "".join(masked)
    for match in SHARED_SHORTHAND_DENOMINATOR_RE.finditer(current):
        strengths.extend(
            measurement(
                amount.strip(),
                match.group("unit"),
                match.group("den_amount") or "",
                match.group("den_unit"),
            )
            for amount in match.group("amounts").split("/")
        )
        masked[match.start() : match.end()] = " " * (match.end() - match.start())
    current = "".join(masked)
    for match in EXPLICIT_COMBINATION_RE.finditer(current):
        components = tuple(QUALIFIED_COMPONENT_RE.finditer(match.group("components")))
        denominator_unit = UNIT_ALIASES.get(components[-1].group("unit"), components[-1].group("unit"))
        # A final ML/UL/L or G/KG is a concentration/presentation denominator.
        # Dose-unit denominators such as 5MG/500MG and 70MG/2800IU are
        # multi-active signatures and must retain every component.
        if denominator_unit in {"UL", "ML", "L", "G", "KG", "H"}:
            continue
        strengths.extend(
            measurement(component.group("amount"), component.group("unit"))
            for component in components
        )
        masked[match.start() : match.end()] = " " * (match.end() - match.start())
    partially_masked = "".join(masked)
    for match in COMBINATION_STRENGTH_RE.finditer(partially_masked):
        unit = match.group("unit")
        strengths.extend(
            measurement(amount.strip(), unit)
            for amount in match.group("amounts").split("/")
        )
        masked[match.start() : match.end()] = " " * (match.end() - match.start())
    remaining = "".join(masked)
    strengths.extend(
        measurement(
            match.group("amount"),
            match.group("unit"),
            match.group("den_amount") or "",
            match.group("den_unit") or "",
        )
        for match in STRENGTH_RE.finditer(remaining)
    )
    return tuple(
        item
        for item in strengths
        if item.value > 0
        and (not item.denominator_kind or item.denominator_value > 0)
    )


def mapped_tokens(text: str, aliases: dict[str, str]) -> frozenset[str]:
    tokens = set(re.findall(r"[A-Z]+", text))
    return frozenset(aliases[token] for token in tokens if token in aliases)


def masked_numeric_text(text: str) -> str:
    """Hide qualified measurements and explicit package expressions."""

    masked = list(text)
    for pattern in (
        SHARED_DENOMINATOR_COMBINATION_RE,
        SHARED_SHORTHAND_DENOMINATOR_RE,
        COMBINATION_STRENGTH_RE,
        STRENGTH_RE,
        STRUCTURAL_RATIO_RE,
        EXPLICIT_PACKAGE_RE,
        MULTIPACK_FORM_RE,
        UNIT_DOSE_PACKAGE_RE,
    ):
        current = "".join(masked)
        for match in pattern.finditer(current):
            masked[match.start() : match.end()] = " " * (match.end() - match.start())
    return "".join(masked)


def split_context_numbers(
    text: str,
) -> tuple[frozenset[Decimal], frozenset[Decimal], frozenset[int]]:
    """Separate bare numbers from plausible/ambiguous dosage-unit counts."""

    explicit_packages = {
        int(match.group("count"))
        for match in EXPLICIT_PACKAGE_RE.finditer(text)
        if int(match.group("count")) > 0
    }
    explicit_packages.update(
        int(match.group("outer")) * int(match.group("inner"))
        for match in MULTIPACK_FORM_RE.finditer(text)
        if int(match.group("outer")) > 0 and int(match.group("inner")) > 0
    )
    explicit_packages.update(
        int(match.group("count"))
        for match in UNIT_DOSE_PACKAGE_RE.finditer(text)
        if int(match.group("count")) > 0
    )
    bare: set[Decimal] = set()
    ambiguous: set[Decimal] = set()
    package_counts = set(explicit_packages)
    masked = list(masked_numeric_text(text))
    current = "".join(masked)
    for match in PACKAGE_FORM_RE.finditer(current):
        count = int(match.group("count"))
        value = Decimal(match.group("count"))
        if 0 < count <= MAX_PLAUSIBLE_PACKAGE_COUNT:
            package_counts.add(count)
            ambiguous.add(value)
        else:
            bare.add(value)
        masked[match.start() : match.end()] = " " * (match.end() - match.start())
    for match in NUMBER_RE.finditer("".join(masked)):
        bare.add(Decimal(match.group(0)))
    return frozenset(bare), frozenset(ambiguous), frozenset(package_counts)


def is_presentation_measurement(
    strength: Measurement,
    forms: frozenset[str],
    routes: frozenset[str],
) -> bool:
    if strength.denominator_kind:
        return False
    if strength.kind == "volume":
        return True
    return bool(strength.kind in {"mass", "volume"} and forms & TOPICAL_FORMS)


def parse_evidence(value: Any) -> ContextEvidence:
    raw_value = str(value or "")
    text = normalize_context(raw_value)
    forms = mapped_tokens(text, FORM_ALIASES)
    routes = mapped_tokens(text, ROUTE_ALIASES)
    strengths = parse_strengths(text)
    # Semicolon-separated catalog `st` values often store one active dose
    # followed by presentation metadata.  Interpret later standalone
    # mass/volume components as presentation quantities when an earlier dose
    # component exists; a lone `50 G` remains a valid bare strength unless the
    # user supplied a structural topical/liquid form.
    semicolon_parts = [
        part.strip()
        for part in re.split(r";", raw_value)
        if part.strip()
    ]
    semicolon_presentations: list[Measurement] = []
    inferred_semicolon_strength: tuple[Measurement, Measurement] | None = None
    if len(semicolon_parts) > 1:
        first_part_strengths = parse_strengths(semicolon_parts[0])
        later_part_strengths = [
            parse_strengths(part) for part in semicolon_parts[1:]
        ]
        # Some catalog fields flatten `10.8G/100ML; 100ML` into
        # `10.8G; 100ML; 100ML`: the first repeated volume is the active
        # concentration denominator and the second is the bottle volume.
        # Reconstruct that signature only when the three-part structure is
        # explicit and unambiguous.
        if (
            len(semicolon_parts) >= 3
            and len(first_part_strengths) == 1
            and not first_part_strengths[0].denominator_kind
            and len(later_part_strengths[0]) == 1
            and not later_part_strengths[0][0].denominator_kind
            and later_part_strengths[0][0].kind in {"mass", "volume"}
            and any(
                later_part_strengths[0][0] in part_strengths
                for part_strengths in later_part_strengths[1:]
            )
        ):
            numerator = first_part_strengths[0]
            denominator = later_part_strengths[0][0]
            inferred = measurement(
                str(numerator.observed_value),
                numerator.observed_unit,
                str(denominator.observed_value),
                denominator.observed_unit,
            )
            inferred_semicolon_strength = (numerator, inferred)
            later_part_strengths = later_part_strengths[1:]
        for part_strengths in later_part_strengths:
            if (
                first_part_strengths
                and part_strengths
                and all(
                    item.kind in {"mass", "volume"}
                    and not item.denominator_kind
                    for item in part_strengths
                )
            ):
                semicolon_presentations.extend(part_strengths)
    if inferred_semicolon_strength is not None:
        original, inferred = inferred_semicolon_strength
        replaced = False
        denominator_removed = False
        reconstructed: list[Measurement] = []
        for item in strengths:
            if not replaced and item == original:
                reconstructed.append(inferred)
                replaced = True
            elif (
                replaced
                and not denominator_removed
                and item.kind == inferred.denominator_kind
                and item.value == inferred.denominator_value
                and not item.denominator_kind
            ):
                denominator_removed = True
            else:
                reconstructed.append(item)
        strengths = tuple(reconstructed)
    if semicolon_presentations:
        remaining_presentations = Counter(semicolon_presentations)
        kept_strengths: list[Measurement] = []
        for item in strengths:
            if remaining_presentations[item] > 0:
                remaining_presentations[item] -= 1
            else:
                kept_strengths.append(item)
        strengths = tuple(kept_strengths)
    semicolon_unit_dose_counts = {
        int(match.group("count"))
        for part in semicolon_parts[1:]
        for match in re.finditer(
            r"(?<![\d.])(?P<count>\d{1,4})(?![\d.])\s*(?:UNITS?|IU)\b",
            normalize_context(part),
        )
        if int(match.group("count")) > 0
    }
    if semicolon_unit_dose_counts:
        strengths = tuple(
            item
            for item in strengths
            if not (
                item.kind == "activity"
                and not item.denominator_kind
                and int(item.observed_value) in semicolon_unit_dose_counts
            )
        )
    presentation = tuple(
        item for item in strengths if is_presentation_measurement(item, forms, routes)
    )
    presentation = tuple((*presentation, *semicolon_presentations))
    dose_strengths = tuple(item for item in strengths if item not in presentation)
    bare, ambiguous, package_counts = split_context_numbers(text)
    package_counts = frozenset((*package_counts, *semicolon_unit_dose_counts))
    structural_ratios = frozenset(
        f"{match.group('left')}{match.group('separator')}{match.group('right')}"
        for match in STRUCTURAL_RATIO_RE.finditer(text)
    )
    invalid_numeric = any(
        Decimal(match.group("amount")) <= 0
        or (
            match.group("den_unit")
            and match.group("den_amount")
            and Decimal(match.group("den_amount")) <= 0
        )
        for match in STRENGTH_RE.finditer(text)
    )
    return ContextEvidence(
        strengths=dose_strengths,
        bare_numbers=bare,
        ambiguous_numbers=ambiguous,
        presentation_quantities=presentation,
        forms=forms,
        routes=routes,
        release_types=mapped_tokens(text, RELEASE_ALIASES),
        package_counts=package_counts,
        structural_ratios=structural_ratios,
        invalid_numeric=invalid_numeric,
    )


def context_suffix_is_fully_recognized(value: Any) -> bool:
    """Require alias suffixes to contain only known product-detail words.

    Exact catalog aliases are a deliberately narrow rescue path. A suffix may
    contain numbers, punctuation, units, forms, routes, release descriptors,
    package words, and a few harmless connective label words. Any other word
    prevents rescue even when some valid evidence is also present, so
    ``junk 20 tab`` cannot silently degrade to ``20 tab``.
    """

    untranslated = (
        str(value or "")
        .translate(ARABIC_DIGITS)
        .replace("µ", "U")
        .replace("μ", "U")
        .replace("٫", ".")
        .replace("٬", ",")
        .upper()
    )
    for source, replacement in CONTEXT_LITERAL_REPLACEMENTS:
        untranslated = untranslated.replace(source, replacement)
    if re.search(r"[\u0600-\u06ff]", untranslated):
        return False
    text = normalize_context(value)
    if not text or not parse_evidence(text).present:
        return False
    allowed = (
        set(UNIT_FACTORS)
        | set(UNIT_ALIASES)
        | set(FORM_ALIASES)
        | set(ROUTE_ALIASES)
        | set(RELEASE_ALIASES)
        | CONTEXT_SUFFIX_FILLER_TOKENS
        | {
            "PACK",
            "PACKS",
            "PACKET",
            "PACKETS",
            "BOX",
            "BOXES",
            "BOTTLE",
            "BOTTLES",
            "PIECE",
            "PIECES",
            "PCS",
            "PEN",
            "PENS",
            "DOSE",
            "DOSES",
            "ACTUATION",
            "ACTUATIONS",
        }
    )
    return all(token in allowed for token in re.findall(r"[A-Z]+", text))


def build_product_catalog(
    records: Iterable[dict[str, Any]],
    family_to_group: dict[str, str],
    compact_key: Callable[[Any], str],
) -> ProductCatalog:
    grouped: dict[str, list[dict[str, Any]]] = {}
    families: dict[str, list[dict[str, Any]]] = {}
    group_names: dict[str, str] = {}
    family_names: dict[str, str] = {}
    family_group_keys: dict[str, str] = {}
    numeric_alias_groups: dict[str, set[str]] = {}
    numeric_brand_alias_families: dict[str, set[str]] = {}
    for record in records:
        family_key = compact_key(record.get("b") or record.get("n") or "")
        if not family_key:
            continue
        group_key = family_to_group.get(family_key, family_key)
        grouped.setdefault(group_key, []).append(record)
        families.setdefault(family_key, []).append(record)
        group_names.setdefault(group_key, str(record.get("b") or record.get("n") or group_key))
        family_names.setdefault(
            family_key,
            str(record.get("b") or record.get("n") or family_key),
        )
        family_group_keys.setdefault(family_key, group_key)
        name_tokens = normalize_context(record.get("n") or "").split()
        leading_numbers: list[str] = []
        for token in name_tokens:
            if NUMBER_RE.fullmatch(token):
                leading_numbers.append(token)
            else:
                break
        if len(leading_numbers) >= 2:
            numeric_alias_groups.setdefault(" ".join(leading_numbers), set()).add(
                family_key
            )
        family_tokens = normalize_context(record.get("b") or record.get("n") or "").split()
        family_start = len(leading_numbers)
        if (
            leading_numbers
            and family_tokens
            and name_tokens[family_start : family_start + len(family_tokens)]
            == family_tokens
        ):
            numeric_brand_alias_families.setdefault(
                " ".join(leading_numbers + family_tokens),
                set(),
            ).add(family_key)
    return ProductCatalog(
        records_by_group={
            key: tuple(
                sorted(
                    values,
                    key=lambda row: (
                        str(row.get("n") or "").casefold(),
                        str(row.get("id") or ""),
                    ),
                )
            )
            for key, values in grouped.items()
        },
        records_by_family={
            key: tuple(
                sorted(
                    values,
                    key=lambda row: (
                        str(row.get("n") or "").casefold(),
                        str(row.get("id") or ""),
                    ),
                )
            )
            for key, values in families.items()
        },
        group_names=group_names,
        family_names=family_names,
        family_group_keys=family_group_keys,
        numeric_alias_groups={
            alias: tuple(
                sorted(
                    family_keys,
                    key=lambda key: (
                        family_names.get(key, key).casefold(),
                        key,
                    ),
                )
            )
            for alias, family_keys in numeric_alias_groups.items()
        },
        numeric_brand_alias_families={
            alias: tuple(
                sorted(
                    family_keys,
                    key=lambda key: (
                        family_names.get(key, key).casefold(),
                        key,
                    ),
                )
            )
            for alias, family_keys in numeric_brand_alias_families.items()
        },
        compact_key=compact_key,
    )


def concentration_ratio_key(value: Measurement) -> tuple[str, Decimal, str] | None:
    if not value.denominator_kind or not value.denominator_value:
        return None
    return (
        value.kind,
        value.value / value.denominator_value,
        value.denominator_kind,
    )


def product_evidence(record: dict[str, Any]) -> ContextEvidence:
    name_text = str(record.get("n") or "")
    metadata_text = " ".join(
        str(record.get(field) or "") for field in ("f", "r")
    )
    parsed_name = parse_evidence(name_text)
    parsed_metadata = parse_evidence(metadata_text)
    strength_field = str(record.get("st") or "")
    strength_parts = [part.strip() for part in strength_field.split(";") if part.strip()]
    parsed_primary = parse_evidence(strength_parts[0]) if strength_parts else parsed_name
    secondary_measurements = tuple(
        item
        for part in strength_parts[1:]
        for item in parse_strengths(part)
    )
    name_strengths = parse_strengths(name_text)
    # The display name often contains a fuller signature than `st` (especially
    # combinations and microlitre concentrations). Prefer it whenever present;
    # presentation quantities are separated below rather than treated as dose.
    strengths = tuple(name_strengths) or parsed_primary.strengths
    raw_form = str(record.get("f") or "").strip().lower()
    raw_route = str(record.get("r") or "").strip().lower()
    explicit_forms = frozenset(
        value for value in (raw_form,) if value and value != "unknown"
    )
    explicit_routes = frozenset(
        value for value in (raw_route,) if value and value != "unknown"
    )
    forms = parsed_name.forms | parsed_metadata.forms | explicit_forms
    routes = parsed_name.routes | parsed_metadata.routes | explicit_routes
    topical_or_liquid_presentation = tuple(
        item for item in strengths if is_presentation_measurement(item, forms, routes)
    )
    parsed_presentations = tuple(
        item
        for item in secondary_measurements
        if is_presentation_measurement(item, forms, routes)
    )
    if not name_strengths:
        strengths = tuple(strengths) + tuple(
            item for item in secondary_measurements if item not in parsed_presentations
        )
    if topical_or_liquid_presentation:
        strengths = tuple(item for item in strengths if item not in topical_or_liquid_presentation)
    return ContextEvidence(
        strengths=tuple(strengths),
        bare_numbers=frozenset(),
        ambiguous_numbers=frozenset(),
        presentation_quantities=tuple(
            dict.fromkeys(
                parsed_presentations
                + parsed_name.presentation_quantities
                + topical_or_liquid_presentation
            )
        ),
        forms=forms,
        routes=routes,
        release_types=parsed_name.release_types | parsed_metadata.release_types,
        package_counts=parsed_name.package_counts,
        structural_ratios=(
            parsed_name.structural_ratios
            | parsed_primary.structural_ratios
            | parse_evidence(strength_field).structural_ratios
        ),
        invalid_numeric=False,
    )


def score_product(
    query: ContextEvidence,
    record: dict[str, Any],
) -> ProductScore:
    product = product_evidence(record)
    score = 0
    matches: list[str] = []
    conflicts: list[str] = []
    compatible = True
    exact_strength_signature = False
    numeric_match = False

    if query.invalid_numeric:
        conflicts.append("invalid_numeric_evidence")
        compatible = False

    # Exact printed/canonical signatures retain numerator and denominator
    # totals.  Equivalent reduced concentrations are useful secondary evidence
    # but must never tie 100MG/4ML with 400MG/16ML when the total was explicit.
    query_counter = Counter(query.strengths)
    product_counter = Counter(product.strengths)
    if query_counter:
        # Catalog labels often store a topical weight (for example ``50 G``
        # cream) in the same strength field used for dose strengths.  Product
        # parsing correctly classifies it as presentation quantity, but a user
        if query_counter == product_counter:
            score += 130 + 10 * (sum(query_counter.values()) - 1)
            matches.append("strength_exact")
            exact_strength_signature = True
            numeric_match = True
        elif all(product_counter[item] >= count for item, count in query_counter.items()):
            score += 55
            matches.append("strength_component_match")
            conflicts.append("strength_signature_incomplete")
            numeric_match = True
        elif (
            len(query.strengths) == 1
            and len(product.strengths) == 1
            and concentration_ratio_key(query.strengths[0]) is not None
            and concentration_ratio_key(query.strengths[0])
            == concentration_ratio_key(product.strengths[0])
        ):
            score += 70
            matches.append("strength_concentration_equivalent")
            conflicts.append("strength_total_differs")
            numeric_match = True
        elif product_counter:
            numerator_overlap = any(
                left.kind == right.kind and left.value == right.value
                for left in query.strengths
                for right in product.strengths
            )
            denominator_conflict = any(
                left.kind == right.kind
                and left.value == right.value
                and left.denominator_kind
                and right.denominator_kind
                and (
                    left.denominator_kind != right.denominator_kind
                    or left.denominator_value != right.denominator_value
                )
                for left in query.strengths
                for right in product.strengths
            )
            incompatible_combination = (
                sum(query_counter.values()) > 1
                or sum(product_counter.values()) > 1
            )
            if (
                numerator_overlap
                and not denominator_conflict
                and not incompatible_combination
            ):
                score += 35
                matches.append("strength_numerator_only")
                conflicts.append("strength_signature_incomplete")
                numeric_match = True
            else:
                score -= 120
                conflicts.append("strength_conflict")
                compatible = False
        else:
            score -= 35
            conflicts.append("strength_unknown")

    if query.structural_ratios:
        if query.structural_ratios <= product.structural_ratios:
            score += 70
            matches.append("structural_ratio_match")
            numeric_match = True
        elif product.structural_ratios:
            score -= 90
            conflicts.append("structural_ratio_conflict")
            compatible = False
        else:
            conflicts.append("structural_ratio_unknown")
            compatible = False

    strength_numbers = {item.observed_value for item in product.strengths}
    presentation_numbers = {
        item.observed_value for item in product.presentation_quantities
    }
    package_numbers = {Decimal(value) for value in product.package_counts}
    known_numbers = strength_numbers | presentation_numbers | package_numbers
    for number in sorted(query.bare_numbers):
        if number in strength_numbers:
            score += 85
            matches.append("unitless_strength_match")
            numeric_match = True
        elif number in package_numbers:
            score += 60
            matches.append("unitless_package_match")
            numeric_match = True
        elif number in presentation_numbers:
            score += 45
            matches.append("unitless_presentation_match")
            numeric_match = True
        elif known_numbers:
            score -= 85
            conflicts.append("unitless_number_conflict")
            compatible = False

    for number in sorted(query.ambiguous_numbers):
        if number in package_numbers:
            score += 75
            matches.append("ambiguous_number_package_match")
            numeric_match = True
        elif number in strength_numbers:
            score += 55
            matches.append("ambiguous_number_strength_match")
            numeric_match = True
        elif number in presentation_numbers:
            score += 35
            matches.append("ambiguous_number_presentation_match")
            numeric_match = True
        elif known_numbers:
            score -= 60
            conflicts.append("ambiguous_number_conflict")
            compatible = False

    if query.presentation_quantities:
        query_presentations = Counter(query.presentation_quantities)
        product_presentations = Counter(product.presentation_quantities)
        if all(
            product_presentations[item] >= count
            for item, count in query_presentations.items()
        ):
            score += 55
            matches.append("presentation_quantity_match")
            numeric_match = True
        elif product_presentations:
            score -= 55
            conflicts.append("presentation_quantity_conflict")
            compatible = False
        else:
            conflicts.append("presentation_quantity_unknown")
            compatible = False

    form_match, form_conflict = compare_forms(query.forms, product.forms)
    if form_match:
        score += 45 if form_match == "exact" else 20
        matches.append("dosage_form_match" if form_match == "exact" else "dosage_form_compatible")
    elif form_conflict:
        score -= 45
        conflicts.append("dosage_form_conflict")
        compatible = False

    if query.routes:
        exact_routes = query.routes & product.routes
        query_injection = bool(query.routes & INJECTION_ROUTES)
        product_injection = bool(product.routes & INJECTION_ROUTES)
        query_subtypes = query.routes & (INJECTION_ROUTES - {"injection"})
        product_subtypes = product.routes & (INJECTION_ROUTES - {"injection"})
        if exact_routes:
            score += 35
            matches.append("route_match")
        elif query_injection and product_injection and not (
            query_subtypes and product_subtypes and query_subtypes.isdisjoint(product_subtypes)
        ):
            score += 15
            matches.append("route_compatible")
        elif product.routes:
            score -= 35
            conflicts.append("route_conflict")
            compatible = False
        else:
            conflicts.append("route_unknown")
            compatible = False

    if query.release_types:
        if query.release_types & product.release_types:
            score += 35
            matches.append("release_type_match")
        elif product.release_types:
            score -= 35
            conflicts.append("release_type_conflict")
            compatible = False
        else:
            conflicts.append("release_type_unknown")
            compatible = False

    if query.package_counts:
        if query.package_counts <= product.package_counts:
            score += 20
            matches.append("package_count_match")
            numeric_match = True
        elif product.package_counts:
            score -= 20
            conflicts.append("package_count_conflict")
            compatible = False
        else:
            conflicts.append("package_count_unknown")
            compatible = False

    return ProductScore(
        score=score,
        matches=tuple(dict.fromkeys(matches)),
        conflicts=tuple(dict.fromkeys(conflicts)),
        compatible=compatible,
        exact_strength_signature=exact_strength_signature,
        numeric_match=numeric_match,
    )


def compare_forms(
    query_forms: frozenset[str],
    product_forms: frozenset[str],
) -> tuple[str, bool]:
    if not query_forms:
        return "", False
    query_modifiers = query_forms & ORAL_SOLID_MODIFIERS
    if query_modifiers:
        if not query_modifiers <= product_forms:
            if product_forms & SPECIFIC_ORAL_SOLID_FORMS:
                return "", True
            if "oral_solid" in product_forms:
                return "compatible", False
        query_base = query_forms - ORAL_SOLID_MODIFIERS
        product_base = product_forms - ORAL_SOLID_MODIFIERS - {"oral_solid"}
        if query_base and product_base and not query_base & product_base:
            return "", True
        if query_modifiers <= product_forms and (
            not query_base or query_base & product_base
        ):
            return "exact", False
        if query_modifiers <= product_forms and "oral_solid" in product_forms:
            return "compatible", False
    if query_forms & product_forms:
        return "exact", False
    container_forms = frozenset({"vial", "ampoule", "syringe", "pen"})
    query_containers = query_forms & container_forms
    product_containers = product_forms & container_forms
    if query_containers and product_containers and query_containers.isdisjoint(product_containers):
        return "", True
    query_specific = query_forms & (
        SPECIFIC_ORAL_SOLID_FORMS | TOPICAL_FORMS | container_forms
    )
    product_specific = product_forms & (
        SPECIFIC_ORAL_SOLID_FORMS | TOPICAL_FORMS | container_forms
    )
    if query_specific and product_specific:
        return "", True
    if query_specific & SPECIFIC_ORAL_SOLID_FORMS and "oral_solid" in product_forms:
        return "compatible", False
    if product_specific & SPECIFIC_ORAL_SOLID_FORMS and "oral_solid" in query_forms:
        return "compatible", False
    if query_specific & TOPICAL_FORMS and "topical" in product_forms:
        return "compatible", False
    if product_specific & TOPICAL_FORMS and "topical" in query_forms:
        return "compatible", False
    known_product_forms = product_forms - {"unknown"}
    return "", bool(known_product_forms)


def result_family_key(
    result: dict[str, Any],
    catalog: ProductCatalog,
) -> str:
    """Return the exact base-family identity represented by a name result."""

    if result.get("source") == "algorithm_6_visual_gap":
        matched_key = catalog.compact_key(result.get("matched_family_key") or "")
        if matched_key:
            return matched_key
    return catalog.compact_key(result.get("name") or "")


def context_after_numeric_commercial_brand_prefix(
    raw_query: str,
    response: dict[str, Any],
    catalog: ProductCatalog,
) -> str | None:
    """Remove an exact catalog brand prefix whose number is part of the name.

    Some catalog families omit a leading numeric brand token: ``3 FLY`` is
    stored under family ``FLY``, and ``1 2 3`` is stored under ``ONE TWO
    THREE``.  In the legacy combined-query path those name numbers must not be
    treated as unitless strength evidence.  A trailing remainder is retained,
    so ``3 FLY 600 tab`` still supplies real product context.

    Only records belonging to a family already retrieved by the name search
    are considered.  Single-number aliases are accepted only when followed by
    the catalog family text; a number-only alias requires at least two leading
    numeric tokens.  These bounds avoid opening a global numeric-brand rescue.
    """

    query_tokens = normalize_context(raw_query).split()
    if not query_tokens:
        return None
    best_remainder: str | None = None
    best_alias_length = -1
    for result in response.get("results", []):
        family_key = result_family_key(result, catalog)
        for record in catalog.records_by_family.get(family_key, ()):
            name_tokens = normalize_context(record.get("n") or "").split()
            family_tokens = normalize_context(
                record.get("b") or record.get("n") or ""
            ).split()
            leading_numbers: list[str] = []
            for token in name_tokens:
                if NUMBER_RE.fullmatch(token):
                    leading_numbers.append(token)
                else:
                    break
            if not leading_numbers or not family_tokens:
                continue
            family_start = len(leading_numbers)
            if (
                name_tokens[family_start : family_start + len(family_tokens)]
                != family_tokens
            ):
                continue
            aliases = [leading_numbers + family_tokens]
            if len(leading_numbers) >= 2:
                aliases.append(leading_numbers)
            for alias in aliases:
                if query_tokens[: len(alias)] != alias:
                    continue
                remainder = " ".join(query_tokens[len(alias) :])
                if (
                    (not remainder or context_suffix_is_fully_recognized(remainder))
                    and len(alias) > best_alias_length
                ):
                    best_alias_length = len(alias)
                    best_remainder = remainder
    return best_remainder


def numeric_commercial_alias_response(
    original_response: dict[str, Any],
    raw_query: str,
    catalog: ProductCatalog,
    *,
    limit: int,
) -> dict[str, Any] | None:
    """Rescue an exact multi-number catalog alias without fuzzy expansion.

    This path is intentionally limited to commercial names whose first two or
    more normalized tokens are numbers.  An all-numeric query must equal that
    leading alias exactly.  A longer query is admitted only when everything
    after the exact alias contains genuine product evidence, which lets a
    combined query such as ``1 2 3 20 tab`` retain normal product filtering.
    """

    query_tokens = normalize_context(raw_query).split()
    leading_numbers: list[str] = []
    for token in query_tokens:
        if NUMBER_RE.fullmatch(token):
            leading_numbers.append(token)
        else:
            break
    if len(leading_numbers) < 2:
        return None

    matched_alias = ""
    matched_families: tuple[str, ...] = ()
    remainder = ""
    for length in range(len(leading_numbers), 1, -1):
        alias = " ".join(leading_numbers[:length])
        family_keys = catalog.numeric_alias_groups.get(alias, ())
        if not family_keys:
            continue
        candidate_remainder = " ".join(query_tokens[length:])
        if (
            candidate_remainder
            and not context_suffix_is_fully_recognized(candidate_remainder)
        ):
            continue
        matched_alias = alias
        matched_families = family_keys
        remainder = candidate_remainder
        break
    if not matched_families:
        return None

    results: list[dict[str, Any]] = []
    for rank, family_key in enumerate(matched_families, 1):
        family_name = catalog.family_names.get(family_key, family_key)
        group_key = catalog.family_group_keys.get(family_key, family_key)
        results.append(
            {
                "rank": rank,
                "name": family_name,
                # Keep the compact group identity for the product-catalog
                # lookup even when a family was folded into a variant group.
                "variant_group": group_key,
                "commercial_name": family_name,
                "candidate_canonical_name": family_name,
                "name_match_type": "exact_numeric_commercial_alias",
                "needs_clarification": True,
                "confirmation_required": True,
                "confidence": "low",
                "source": "exact_numeric_commercial_alias",
                "matched_signals": "exact_numeric_commercial_alias",
                "reasons": ["exact_numeric_commercial_alias"],
            }
        )

    alias_response = dict(original_response)
    alias_response.update(
        {
            "status": "ambiguous",
            "decision_type": "numeric_commercial_alias_matches",
            "message": (
                "The numeric text exactly matches a catalog commercial-name alias. "
                "Compare every listed family and confirm the package."
            ),
            "candidate_count": len(matched_families),
            "confirmation_required": True,
            "context_family_reranked": False,
            "numeric_commercial_alias": matched_alias,
            # Product filtering must see every exact alias family before the
            # public result limit is applied.  The no-remainder path remains
            # capped immediately because it returns this response directly.
            "results": results if remainder else results[:limit],
        }
    )
    if not remainder:
        return alias_response

    filtered = rerank_products(
        alias_response,
        remainder,
        catalog,
        limit=limit,
        name_query=matched_alias,
        explicit_product_context=True,
    )
    filtered["status"] = "ambiguous"
    filtered["candidate_count"] = len(matched_families)
    filtered["confirmation_required"] = True
    filtered["numeric_commercial_alias"] = matched_alias
    if filtered.get("decision_type") == "product_context_selection":
        filtered["name_decision_type"] = "numeric_commercial_alias_matches"
        filtered["decision_type"] = "numeric_commercial_alias_product_context_selection"
        filtered["message"] = (
            "The numeric text exactly matches catalog commercial-name aliases, "
            "then the trailing product details selected compatible products. "
            "Compare every listed family and confirm the package."
        )
    elif filtered.get("decision_type") == "product_context_no_compatible_product":
        filtered["name_decision_type"] = "numeric_commercial_alias_matches"
        filtered["decision_type"] = "numeric_commercial_alias_no_compatible_product"
    filtered["results"] = filtered.get("results", [])[:limit]
    return filtered


def numeric_commercial_brand_alias_response(
    original_response: dict[str, Any],
    raw_query: str,
    catalog: ProductCatalog,
    *,
    limit: int,
) -> dict[str, Any] | None:
    """Resolve an exact leading-number-plus-family commercial-name alias.

    Unlike the numeric-only alias path, this key contains the written family
    text as well as at least one leading numeric token (for example ``3 FLY``).
    Matching is exact and catalog-prepared; a suffix is accepted only when it
    parses as genuine product evidence.
    """

    query_tokens = normalize_context(raw_query).split()
    if not query_tokens or not NUMBER_RE.fullmatch(query_tokens[0]):
        return None

    matched_alias = ""
    matched_families: tuple[str, ...] = ()
    remainder = ""
    for alias, family_keys in catalog.numeric_brand_alias_families.items():
        alias_tokens = alias.split()
        if len(alias_tokens) <= len(matched_alias.split()):
            continue
        if query_tokens[: len(alias_tokens)] != alias_tokens:
            continue
        candidate_remainder = " ".join(query_tokens[len(alias_tokens) :])
        if (
            candidate_remainder
            and not context_suffix_is_fully_recognized(candidate_remainder)
        ):
            continue
        matched_alias = alias
        matched_families = family_keys
        remainder = candidate_remainder
    if not matched_families:
        return None

    results: list[dict[str, Any]] = []
    for rank, family_key in enumerate(matched_families, 1):
        family_name = catalog.family_names.get(family_key, family_key)
        group_key = catalog.family_group_keys.get(family_key, family_key)
        results.append(
            {
                "rank": rank,
                "name": family_name,
                "variant_group": group_key,
                "commercial_name": family_name,
                "candidate_canonical_name": family_name,
                "name_match_type": "exact_numeric_brand_alias",
                "needs_clarification": True,
                "confirmation_required": True,
                "confidence": "low",
                "source": "exact_numeric_brand_alias",
                "matched_signals": "exact_numeric_brand_alias",
                "reasons": ["exact_numeric_brand_alias"],
            }
        )

    alias_response = dict(original_response)
    alias_response.update(
        {
            "status": "ambiguous",
            "decision_type": "numeric_commercial_brand_alias_matches",
            "message": (
                "The text exactly matches a numbered catalog commercial name. "
                "Compare every listed family and confirm the package."
            ),
            "candidate_count": len(matched_families),
            "confirmation_required": True,
            "context_family_reranked": False,
            "numeric_commercial_brand_alias": matched_alias,
            "results": results if remainder else results[:limit],
        }
    )
    if not remainder:
        top_family_key = (
            result_family_key(original_response["results"][0], catalog)
            if original_response.get("results")
            else ""
        )
        if len(matched_families) == 1 and top_family_key == matched_families[0]:
            return original_response
        return alias_response

    filtered = rerank_products(
        alias_response,
        remainder,
        catalog,
        limit=limit,
        name_query=matched_alias,
        explicit_product_context=True,
    )
    filtered["status"] = "ambiguous"
    filtered["candidate_count"] = len(matched_families)
    filtered["confirmation_required"] = True
    filtered["numeric_commercial_brand_alias"] = matched_alias
    if filtered.get("decision_type") == "product_context_selection":
        filtered["name_decision_type"] = "numeric_commercial_brand_alias_matches"
        filtered["message"] = (
            "The text exactly matches a numbered catalog commercial name, then "
            "the trailing product details selected compatible products. Confirm "
            "the medicine and package."
        )
    elif filtered.get("decision_type") == "product_context_no_compatible_product":
        filtered["name_decision_type"] = "numeric_commercial_brand_alias_matches"
    filtered["results"] = filtered.get("results", [])[:limit]
    return filtered


def rerank_products(
    response: dict[str, Any],
    raw_query: str,
    catalog: ProductCatalog,
    *,
    limit: int,
    name_query: str = "",
    explicit_product_context: bool = True,
) -> dict[str, Any]:
    evidence_text = raw_query
    visual_gap_mode = response.get("decision_type") == "visual_gap_matches"
    if not explicit_product_context and not visual_gap_mode:
        brand_alias_response = numeric_commercial_brand_alias_response(
            response,
            raw_query,
            catalog,
            limit=limit,
        )
        if brand_alias_response is not None:
            return brand_alias_response
        alias_response = numeric_commercial_alias_response(
            response,
            raw_query,
            catalog,
            limit=limit,
        )
        if alias_response is not None:
            return alias_response
        commercial_remainder = context_after_numeric_commercial_brand_prefix(
            raw_query,
            response,
            catalog,
        )
        if commercial_remainder is not None:
            evidence_text = commercial_remainder
    # With no separately supplied details, the entire query is used only for
    # legacy combined-name support.  It must never be reparsed as context for
    # an explicit visual-gap response: visible digits such as `VIT__3` belong
    # to the name pattern, not to a hidden strength or package request.
    if visual_gap_mode and not explicit_product_context:
        return response
    query = parse_evidence(evidence_text)
    if not query.present:
        return response
    # A unit-qualified mass/volume is explicit numeric catalog evidence even
    # when product metadata later classifies that exact value as a topical or
    # liquid presentation. Preserve the observed qualified measurement here;
    # bare numbers remain separate and cannot use this path.
    qualified_query_measurements = parse_strengths(evidence_text)
    qualified_presentation_only = bool(
        qualified_query_measurements
        and all(
            item.kind in {"mass", "volume"} and not item.denominator_kind
            for item in qualified_query_measurements
        )
    )

    # A bare number inside a medicine name can be part of the literal brand
    # (for example A1, D3, V2, or a numbered product line). When the caller did
    # not supply the separate Product details field, an exact name result owns
    # that number; it is not silently reinterpreted as an unknown strength.
    if (
        not explicit_product_context
        and query.bare_numbers
        and not any(
            (
                query.strengths,
                query.ambiguous_numbers,
                query.presentation_quantities,
                query.forms,
                query.routes,
                query.release_types,
                query.package_counts,
                query.structural_ratios,
                query.invalid_numeric,
            )
        )
    ):
        compact_full_query = catalog.compact_key(name_query)
        if any(
            catalog.compact_key(item.get("name") or "") == compact_full_query
            for item in response.get("results", [])
        ):
            return response

    compact_name = catalog.compact_key(name_query)
    if not visual_gap_mode and 1 <= len(compact_name) <= 2:
        short_response = short_prefix_context_response(
            response,
            compact_name,
            query,
            catalog,
            limit=limit,
        )
        if short_response is not None:
            return short_response
    if not response.get("results"):
        return context_failure_response(
            response,
            query,
            candidate_products=0,
            reason="No medicine family was retrieved from the visible name.",
        )

    # A separately supplied exact medicine name is a hard family boundary.
    # Product evidence may select a presentation inside that family, but it
    # must never jump to another retrieved name merely because that product
    # happens to share a number such as 500 or 600.  Legacy combined queries
    # are not exact here because their trailing detail remains in name_query.
    exact_base_keys: set[str] = set()
    if compact_name and not visual_gap_mode:
        for result in response["results"]:
            result_key = catalog.compact_key(result.get("name") or "")
            if result_key == compact_name:
                exact_base_keys.add(result_key)
    if exact_base_keys:
        response = dict(response)
        response["results"] = [
            result
            for result in response["results"]
            if catalog.compact_key(result.get("name") or "") in exact_base_keys
        ]

    # Variant groups are useful display metadata, but they are deliberately
    # broader than a medicine base family (for example BRUFEN also contains
    # BRUFEN COLD and BRUFEN FLU).  Product context is therefore admitted and
    # scored against the exact base families returned by the name search.
    # This prevents an admitted result from opening unretrieved siblings that
    # merely share its variant group.
    family_results_by_key: dict[str, list[dict[str, Any]]] = {}
    family_order: list[str] = []
    for result in response["results"]:
        family_key = result_family_key(result, catalog)
        if not family_key:
            continue
        if family_key not in family_results_by_key:
            family_results_by_key[family_key] = []
            family_order.append(family_key)
        family_results_by_key[family_key].append(result)

    # For a misspelled/nonexact name, only the strongest few name families may
    # use product context to become a selected result.  This covers the locked
    # rank-two corrections while preventing a distant family (for example a
    # rank-twelve product that also says 600 mg) from being injected by context.
    catalog_alias_mode = response.get("decision_type") in {
        "numeric_commercial_alias_matches",
        "numeric_commercial_brand_alias_matches",
    }
    admission_order = (
        family_order
        if catalog_alias_mode
        else family_order[:CONTEXT_FAMILY_ADMISSION_LIMIT]
    )
    admitted_family_keys: set[str] = set()
    for family_position, family_key in enumerate(admission_order):
        first_result = family_results_by_key[family_key][0]
        raw_distance = first_result.get("raw_edit_distance")
        similarity = first_result.get("consensus_levenshtein_similarity")
        has_name_diagnostic = raw_distance is not None or similarity is not None
        plausible = (
            catalog_alias_mode
            or visual_gap_mode
            or family_position == 0
            or (
                has_name_diagnostic
                and (
                    raw_distance is None
                    or float(raw_distance) <= CONTEXT_FAMILY_MAX_RAW_EDIT_DISTANCE
                )
                and (
                    similarity is None
                    or float(similarity) >= CONTEXT_FAMILY_MIN_LEVENSHTEIN_SIMILARITY
                )
            )
        )
        if plausible:
            admitted_family_keys.add(family_key)

    ranked_families: list[dict[str, Any]] = []
    product_candidates = 0
    numeric_evidence = bool(
        query.strengths
        or query.bare_numbers
        or query.ambiguous_numbers
        or query.presentation_quantities
        or query.package_counts
        or query.structural_ratios
        or query.invalid_numeric
    )
    for family_position, family_key in enumerate(family_order):
        family_results = family_results_by_key[family_key]
        if family_key not in admitted_family_keys:
            ranked_families.append(
                {
                    "position": family_position,
                    "score": 0,
                    "matched": False,
                    "exact": False,
                    "numeric": False,
                    "results": [dict(family_results[0])],
                }
            )
            continue
        records = catalog.records_by_family.get(family_key, ())
        if not records:
            ranked_families.append(
                {
                    "position": family_position,
                    "score": 0,
                    "matched": False,
                    "exact": False,
                    "numeric": False,
                    "results": [dict(family_results[0])],
                }
            )
            continue
        scored: list[tuple[ProductScore, dict[str, Any]]] = []
        for record in records:
            product_score = score_product(query, record)
            if (
                qualified_presentation_only
                and product_score.compatible
            ):
                product = product_evidence(record)
                if (
                    Counter(qualified_query_measurements)
                    == Counter(product.presentation_quantities)
                    and not product.strengths
                ):
                    product_score = ProductScore(
                        score=product_score.score + 130,
                        matches=tuple(
                            dict.fromkeys(
                                (*product_score.matches, "qualified_presentation_exact")
                            )
                        ),
                        conflicts=product_score.conflicts,
                        compatible=True,
                        exact_strength_signature=True,
                        numeric_match=True,
                    )
            scored.append((product_score, record))
        product_candidates += len(scored)
        compatible = [
            item
            for item in scored
            if item[0].compatible and item[0].score > 0 and item[0].matches
            and (not numeric_evidence or item[0].numeric_match)
        ]
        if not compatible:
            unchanged = dict(family_results[0])
            unchanged["context_match_status"] = "no_compatible_product"
            ranked_families.append(
                {
                    "position": family_position,
                    "score": 0,
                    "matched": False,
                    "exact": False,
                    "numeric": False,
                    "results": [unchanged],
                }
            )
            continue
        best_score = max(item[0].score for item in compatible)
        tied = [item for item in compatible if item[0].score == best_score]
        selected_results = []
        for product_score, record in tied[:6]:
            selected_results.append(
                product_result(
                    family_results[0],
                    record,
                    product_score,
                    catalog,
                    tie_count=len(tied),
                )
            )
        ranked_families.append(
            {
                "position": family_position,
                "score": best_score,
                "matched": True,
                "exact": any(item[0].exact_strength_signature for item in tied),
                "numeric": any(item[0].numeric_match for item in tied),
                "results": selected_results,
            }
        )

    matched_families = [item for item in ranked_families if item["matched"]]
    if not matched_families:
        admitted_response = dict(response)
        admitted_response["results"] = [
            result
            for result in response.get("results", [])
            if result_family_key(result, catalog) in admitted_family_keys
        ]
        return context_failure_response(
            admitted_response,
            query,
            candidate_products=product_candidates,
            reason="The supplied product details conflict with every retrieved catalog product.",
        )

    original_family_positions = [item["position"] for item in ranked_families]
    exact_reorder = any(item["exact"] for item in matched_families)
    unitless_form_reorder = bool(
        not query.strengths
        and (query.bare_numbers or query.ambiguous_numbers)
        and query.forms
        and len(matched_families) == 1
        and matched_families[0]["numeric"]
    )
    strong_context_selection = bool(
        exact_reorder
        or unitless_form_reorder
        or (
            query.presentation_quantities
            and query.forms
            and any(
                family["matched"]
                and family["numeric"]
                and any(
                    "presentation_quantity_match"
                    in str(result.get("matched_context") or "")
                    and (
                        "dosage_form_match"
                        in str(result.get("matched_context") or "")
                        or "dosage_form_compatible"
                        in str(result.get("matched_context") or "")
                    )
                    for result in family["results"]
                )
                for family in matched_families
            )
        )
        or catalog_alias_mode
    )
    if strong_context_selection:
        if catalog_alias_mode:
            # Exact catalog aliases are ordered alphabetically when prepared;
            # that order is not name-proximity evidence and must not outweigh
            # a stronger product-context match.
            ranked_families.sort(
                key=lambda item: (
                    not item["matched"],
                    -item["score"],
                    item["position"],
                )
            )
        else:
            ranked_families.sort(
                key=lambda item: (
                    not item["matched"],
                    -(item["score"] - 14 * item["position"]),
                    item["position"],
                )
            )
    output_families = (
        [item for item in ranked_families if item["matched"]]
        if strong_context_selection
        else ranked_families
    )
    reranked = [
        family["results"][0]
        for family in output_families
        if family["results"]
    ][:limit]
    for family in output_families:
        for result in family["results"][1:]:
            if len(reranked) >= limit:
                break
            reranked.append(result)
        if len(reranked) >= limit:
            break
    context_family_reranked = original_family_positions != [
        item["position"] for item in ranked_families
    ]

    output = dict(response)
    output.update(
        {
            "name_decision_type": response.get("decision_type"),
            "decision_type": "product_context_selection",
            "message": (
                "Medicine families were ranked by name, then compatible catalog products "
                "were selected from the supplied strength and form evidence."
            ),
            "product_context": context_payload(
                query,
                candidate_products=product_candidates,
                compatible_groups=len(matched_families),
            ),
            "context_family_reranked": context_family_reranked,
            "results": reranked,
        }
    )
    for rank, result in enumerate(output["results"], 1):
        result["rank"] = rank
        result["product_context_rank"] = rank
    return output


def product_result(
    source: dict[str, Any],
    record: dict[str, Any],
    product_score: ProductScore,
    catalog: ProductCatalog,
    *,
    tie_count: int,
) -> dict[str, Any]:
    result = dict(source)
    selected_product_id = str(record.get("id") or "").strip()
    result.update(
        {
            "name_match_rank": source.get("rank"),
            "name_match_name": source.get("name"),
            "name": record.get("b") or record.get("n") or source.get("name"),
            "candidate_canonical_name": record.get("b") or source.get("name"),
            "commercial_name": record.get("n") or source.get("commercial_name"),
            "selected_product_key": catalog.compact_key(record.get("n") or ""),
            "product_context_score": product_score.score,
            "product_context_rank": 1,
            "matched_context": "|".join(product_score.matches),
            "context_conflicts": "|".join(product_score.conflicts),
            "context_match_status": "ambiguous_products" if tie_count > 1 else "compatible_product",
            "context_tie_count": tie_count,
        }
    )
    if selected_product_id:
        result["selected_product_id"] = selected_product_id
    return result


def context_payload(
    query: ContextEvidence,
    *,
    candidate_products: int,
    compatible_groups: int = 0,
) -> dict[str, Any]:
    return {
        "strengths": [format_measurement(value) for value in query.strengths],
        "bare_numbers": [format_decimal(value) for value in sorted(query.bare_numbers)],
        "ambiguous_numbers": [
            format_decimal(value) for value in sorted(query.ambiguous_numbers)
        ],
        "presentation_quantities": [
            format_measurement(value) for value in query.presentation_quantities
        ],
        "forms": sorted(query.forms),
        "routes": sorted(query.routes),
        "release_types": sorted(query.release_types),
        "package_counts": sorted(query.package_counts),
        "structural_ratios": sorted(query.structural_ratios),
        "invalid_numeric": query.invalid_numeric,
        "candidate_products": candidate_products,
        "compatible_groups": compatible_groups,
    }


def context_failure_response(
    response: dict[str, Any],
    query: ContextEvidence,
    *,
    candidate_products: int,
    reason: str,
) -> dict[str, Any]:
    output = dict(response)
    failed_results = []
    for item in response.get("results", []):
        failed = dict(item)
        failed.update(
            {
                "context_match_status": "no_compatible_product",
                "matched_context": "",
                "context_conflicts": "product_context_no_compatible_product",
            }
        )
        failed_results.append(failed)
    output.update(
        {
            "name_decision_type": response.get("decision_type"),
            "decision_type": "product_context_no_compatible_product",
            "status": "ambiguous" if response.get("results") else "no_match",
            "message": reason + " Check the number/unit or add the dosage form.",
            "product_context": context_payload(
                query,
                candidate_products=candidate_products,
                compatible_groups=0,
            ),
            "context_family_reranked": False,
            "results": failed_results,
        }
    )
    return output


def short_prefix_context_response(
    original_response: dict[str, Any],
    compact_name: str,
    query: ContextEvidence,
    catalog: ProductCatalog,
    *,
    limit: int,
) -> dict[str, Any] | None:
    numeric_evidence = bool(
        query.strengths
        or query.bare_numbers
        or query.ambiguous_numbers
        or query.presentation_quantities
        or query.package_counts
        or query.structural_ratios
        or query.invalid_numeric
    )
    structural_evidence = bool(query.forms or query.routes or query.release_types)
    if not (numeric_evidence and structural_evidence):
        return None

    families: list[tuple[str, int, list[tuple[ProductScore, dict[str, Any]]]]] = []
    product_candidates = 0
    for family_key in sorted(
        catalog.records_by_family,
        key=lambda key: (catalog.family_names.get(key, key).casefold(), key),
    ):
        family_name_key = catalog.compact_key(
            catalog.family_names.get(family_key, family_key)
        )
        if not family_name_key.startswith(compact_name):
            continue
        scored = [
            (score_product(query, record), record)
            for record in catalog.records_by_family[family_key]
        ]
        product_candidates += len(scored)
        compatible = [
            item
            for item in scored
            if item[0].compatible
            and item[0].score > 0
            and item[0].numeric_match
            and (
                not query.forms
                or "dosage_form_match" in item[0].matches
                or "dosage_form_compatible" in item[0].matches
            )
        ]
        if not compatible:
            continue
        best = max(item[0].score for item in compatible)
        families.append(
            (
                family_key,
                best,
                [item for item in compatible if item[0].score == best],
            )
        )

    if not families:
        output = context_failure_response(
            {**original_response, "results": []},
            query,
            candidate_products=product_candidates,
            reason="No strict name-prefix product matches all supplied details.",
        )
        output["decision_type"] = "context_assisted_prefix_no_match"
        return output
    if len(families) > limit:
        output = context_failure_response(
            {**original_response, "results": []},
            query,
            candidate_products=product_candidates,
            reason=(
                f"The visible name and product details still match {len(families)} families; "
                "enter more medicine-name letters."
            ),
        )
        output["decision_type"] = "context_assisted_prefix_too_broad"
        output["candidate_count"] = len(families)
        return output

    families.sort(
        key=lambda item: (
            -item[1],
            catalog.family_names.get(item[0], item[0]).casefold(),
        )
    )
    results_by_family: list[list[dict[str, Any]]] = []
    for name_rank, (family_key, _, tied) in enumerate(families, 1):
        family_results: list[dict[str, Any]] = []
        family_name = catalog.family_names.get(family_key, family_key)
        group_key = catalog.family_group_keys.get(family_key, family_key)
        group_name = catalog.group_names.get(group_key, family_name)
        for product_score, record in tied[:6]:
            source = {
                "rank": name_rank,
                "name": family_name,
                "variant_group": group_name,
                "commercial_name": record.get("n"),
                "candidate_canonical_name": family_name,
                "matched_family_key": family_key,
                "needs_clarification": True,
                "confirmation_required": True,
                "confidence": "low",
                "source": "strict_name_prefix_plus_product_context",
                "matched_signals": "strict_name_prefix|product_context_filter",
                "reasons": ["strict_name_prefix", "product_context_filter"],
            }
            result = product_result(
                source,
                record,
                product_score,
                catalog,
                tie_count=len(tied),
            )
            result["name_match_type"] = "strict_prefix"
            family_results.append(result)
        results_by_family.append(family_results)
    # Preserve at least one visible candidate from every admitted family before
    # spending the API limit on equally supported product variants.
    results = [items[0] for items in results_by_family if items]
    for items in results_by_family:
        for item in items[1:]:
            if len(results) >= limit:
                break
            results.append(item)
        if len(results) >= limit:
            break
    output = dict(original_response)
    output.update(
        {
            "status": "ambiguous",
            "decision_type": "context_assisted_prefix_candidates",
            "name_decision_type": original_response.get("decision_type"),
            "message": (
                "A very short medicine-name prefix was filtered by the supplied product "
                "details. Compare all candidates and confirm the package."
            ),
            "candidate_count": len(families),
            "confirmation_required": True,
            "product_context": context_payload(
                query,
                candidate_products=product_candidates,
                compatible_groups=len(families),
            ),
            "context_family_reranked": False,
            "results": results[:limit],
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


def format_decimal(value: Decimal) -> str:
    return str(value.normalize())

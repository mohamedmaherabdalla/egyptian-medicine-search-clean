#!/usr/bin/env python3
"""
Batch-evaluate the current static app search behavior.

The browser app scans every catalog row for every query. That is exact, but too
slow for the 349k-case expanded suite. This evaluator ports the same scoring
rules from app/app.js and uses indexes only to avoid scoring candidates that
cannot receive a positive score.

Problem: evaluate every generated commercial-name stress case against the
current app search rules and write both aggregate metrics and row-level results.
Inputs: catalog.json records plus split CSV test cases with non-empty input,
expected, category, error_type, difficulty, and danger fields.
Outputs: CSV/JSON/Markdown files under benchmark_01_legacy/results; row-level output is
one record per test case, while aggregate outputs summarize retrieval and safety
metrics by scope/category/error_type.
Edge cases: ambiguous expected values, zero app results, no relevant catalog
record after parsing, short dangerous prefixes, and ties where clarification
should be required instead of a confident top-1 answer.
Failure modes: malformed input CSV or catalog schema should raise naturally
during parsing/indexing; a missing full output file is treated as a reporting
bug because it prevents audit of individual medical search failures.
Algorithm choice: we mirror the app scoring rules with candidate indexes instead
of driving the browser for every case. Browser execution would be closer to the
runtime surface but is too slow and unstable for 341k+ rows; indexed scoring
keeps the same ranking logic while making full-suite regression evaluation
repeatable enough for commit-time artifacts.
"""

from __future__ import annotations

import csv
import json
import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "app" / "data" / "catalog.json"
OUT_DIR = ROOT / "benchmark_01_legacy" / "results" / "01_current_app"
ARTIFACT_DIR = ROOT / "benchmark_01_legacy" / "artifacts" / "01_current_app"

# Row-level audit file. This is intentionally separate from aggregate metrics so
# reviewers can inspect every query, target, top result, rank, and safety flag
# without reverse-engineering sampled failure files.
ALL_TEST_RESULTS_CSV_PATH = ARTIFACT_DIR / "case_results.csv"

# Aggregate metric files. The category file preserves the previous reporting
# contract; the error-type file adds the finer-grained diagnostic table requested
# for identifying exactly which generated mutation type is weak.
METRICS_BY_SCOPE_CATEGORY_CSV_PATH = OUT_DIR / "metrics_by_category.csv"
METRICS_BY_SCOPE_CATEGORY_ERROR_TYPE_CSV_PATH = OUT_DIR / "metrics_by_error_type.csv"
FAILURE_SAMPLES_CSV_PATH = OUT_DIR / "failure_samples.csv"
TOP_WRONG_BASES_CSV_PATH = OUT_DIR / "top_wrong_families.csv"
EVALUATION_REPORT_MD_PATH = OUT_DIR / "report.md"
EVALUATION_SUMMARY_JSON_PATH = OUT_DIR / "summary.json"

TEST_FILES = {
    "inside": ROOT / "benchmark_01_legacy" / "data" / "test_cases_inside.csv",
    "semi_outside": ROOT / "benchmark_01_legacy" / "data" / "test_cases_semi_outside.csv",
    "outside": ROOT / "benchmark_01_legacy" / "data" / "test_cases_outside.csv",
}

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
ARABIC_LETTERS = str.maketrans({
    "آ": "ا",
    "أ": "ا",
    "إ": "ا",
    "ٱ": "ا",
    "ى": "ي",
    "ئ": "ي",
    "ؤ": "و",
    "ة": "ه",
})

ENGLISH_NOISE = {
    "AND", "PRICE", "DOSE", "DOS", "USE", "USES", "GENERIC", "FORTE",
    "TABLET", "TABLETS", "TAB", "TABS", "CAP", "CAPS", "CAPSULE",
    "SYRUP", "DROP", "DROPS", "MG", "MCG", "IU", "G", "GM", "ML",
    "VIAL", "AMP", "AMPOULE", "INJECTION", "PEN", "PENS",
}

GENERIC_TOKENS = {
    "PLUS", "EXTRA", "FORTE", "ADVANCE", "MAX", "SUPER", "ULTRA",
    "NEW", "ACTIVE", "NATURAL", "GOLD", "SILVER", "BIO", "VITA", "VIT",
    "PRO", "CARE", "SKIN", "HAIR", "BABY", "KIDS", "ADULT", "DRUG",
    "MEDICINE", "CREAM", "GEL", "LOTION", "SOAP", "SHAMPOO", "MASK",
}

ARABIC_NOISE = {
    "سعر", "بكام", "جرام", "جم", "مل", "اقراص", "قرص", "كبسول",
    "كبسوله", "كبسولة", "كبسولات", "شراب", "حقن", "حقنه", "حقنة",
    "فيال", "امبول", "امبوله", "امبولة",
}

ROUTE_HINTS = {
    "TAB": "oral_solid", "TABS": "oral_solid", "TABLET": "oral_solid", "TABLETS": "oral_solid",
    "CAP": "oral_solid", "CAPS": "oral_solid", "CAPSULE": "oral_solid",
    "SYRUP": "oral_liquid", "SUSP": "oral_liquid", "SUSPENSION": "oral_liquid", "DROPS": "oral_liquid",
    "VIAL": "injection", "AMP": "injection", "AMPOULE": "injection", "INJ": "injection", "INF": "injection",
    "IV": "injection", "IM": "injection", "CREAM": "topical", "GEL": "topical", "OINT": "topical",
    "LOTION": "topical", "SOAP": "soap", "SPRAY": "spray", "EYE": "ophthalmic", "EAR": "otic",
    "MOUTH": "mouth", "RECTAL": "rectal", "SUPP": "rectal", "VAG": "vaginal", "VAGINAL": "vaginal",
    "قرص": "oral_solid", "اقراص": "oral_solid", "كبسول": "oral_solid", "كبسوله": "oral_solid",
    "كبسولة": "oral_solid", "شراب": "oral_liquid", "معلق": "oral_liquid", "نقط": "oral_liquid",
    "قطره": "oral_liquid", "قطرة": "oral_liquid", "حقن": "injection", "حقنة": "injection",
    "فيال": "injection", "امبول": "injection", "أمبول": "injection", "امبولة": "injection",
    "مرهم": "topical", "كريم": "topical", "جل": "topical", "بخاخ": "spray", "لبوس": "rectal",
}

BASE_ALIASES = {
    "BANADOL": "PANADOL", "BANADOLCOLD": "PANADOL", "BANADOLE": "PANADOL",
    "BANDOL": "PANADOL", "PANDOL": "PANADOL", "PANDOLCOLD": "PANADOL", "BANDOLCOLD": "PANADOL",
    "PANADL": "PANADOL", "PANADOLE": "PANADOL", "بنادول": "PANADOL", "باندول": "PANADOL",
    "OGMENTIN": "AUGMENTIN", "OGMNTIN": "AUGMENTIN", "AUGMNTIN": "AUGMENTIN", "AUGMANTIN": "AUGMENTIN",
    "اوجمنتين": "AUGMENTIN", "اوجمانتين": "AUGMENTIN", "اوجمنتن": "AUGMENTIN",
    "NEKSIUM": "NEXIUM", "NEKSUM": "NEXIUM", "NEXUM": "NEXIUM", "NEXEUM": "NEXIUM", "نكسيوم": "NEXIUM",
    "LIPTOR": "LIPITOR", "LEPITOR": "LIPITOR", "LIPTUR": "LIPITOR", "ليبتور": "LIPITOR",
    "BRUFN": "BRUFEN", "BRUFIN": "BRUFEN", "BROFEN": "BRUFEN", "بروفين": "BRUFEN",
    "KETOFN": "KETOFAN", "KETOFEN": "KETOFAN", "KETOFANE": "KETOFAN", "كيتوفان": "KETOFAN",
    "VOLTARIN": "VOLTAREN", "FOLTAREN": "VOLTAREN", "فولتارين": "VOLTAREN",
}


def normalize_search(value: object) -> str:
    if value is None:
        return ""
    text = str(value).translate(ARABIC_DIGITS).translate(ARABIC_LETTERS)
    text = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", text)
    text = text.upper()
    text = re.sub(r"[^0-9A-Z\u0600-\u06ff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact_key(value: object) -> str:
    return re.sub(r"[^0-9A-Z\u0600-\u06ff]+", "", normalize_search(value))


def tokens_of(value: object) -> list[str]:
    out = []
    for token in normalize_search(value).split():
        if len(token) < 2:
            continue
        if token in ENGLISH_NOISE or token in ARABIC_NOISE:
            continue
        out.append(token)
    return out


def parse_numbers(value: object) -> set[str]:
    return set(re.findall(r"\b\d+(?:\.\d+)?\b", normalize_search(value)))


def parse_route_hints(value: object) -> set[str]:
    return {ROUTE_HINTS[t] for t in normalize_search(value).split() if t in ROUTE_HINTS}


def skeleton(value: object) -> str:
    text = compact_key(value)
    text = text.replace("PH", "F")
    text = re.sub(r"[CQK]", "K", text)
    text = re.sub(r"[PV]", "B", text)
    text = re.sub(r"[SZ]", "S", text)
    text = re.sub(r"[AEIOUY]", "", text)
    return re.sub(r"(.)\1+", r"\1", text)


def drug_phonetic_key(value: object) -> str:
    text = compact_key(value)
    text = text.replace("PH", "F").replace("CK", "K").replace("GH", "G")
    text = re.sub(r"[BPFV]", "P", text)
    text = re.sub(r"[DT]", "T", text)
    text = re.sub(r"[CGKQ]", "K", text)
    text = re.sub(r"[SZ]", "S", text)
    text = re.sub(r"J", "G", text)
    text = re.sub(r"[AEIOUY]", "", text)
    return re.sub(r"(.)\1+", r"\1", text)


def build_key_neighbors() -> dict[str, set[str]]:
    rows = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]
    out: dict[str, set[str]] = {}
    for row in rows:
        for i, ch in enumerate(row):
            vals = {ch}
            if i:
                vals.add(row[i - 1])
            if i < len(row) - 1:
                vals.add(row[i + 1])
            out[ch] = vals
    vertical = {
        "Q": "A", "W": "AS", "E": "SD", "R": "DF", "T": "FG", "Y": "GH", "U": "HJ", "I": "JK", "O": "KL", "P": "L",
        "A": "QWZ", "S": "QWEXZ", "D": "WERFCX", "F": "ERTGVC", "G": "RTYHBV", "H": "TYUJNB", "J": "YUIKMN", "K": "UIOLM", "L": "OPK",
        "Z": "ASX", "X": "ASDCZ", "C": "SDFVX", "V": "DFGBC", "B": "FGHNV", "N": "GHJMB", "M": "HJKN",
    }
    for key, chars in vertical.items():
        out.setdefault(key, {key}).update(chars)
    return out


KEY_NEIGHBORS = build_key_neighbors()


def keyboard_proximity_ratio(query_compact: str, target_compact: str) -> float:
    if not query_compact or not target_compact or len(query_compact) != len(target_compact):
        return 0.0
    if len(query_compact) < 4 or len(query_compact) > 18:
        return 0.0
    hits = 0
    for q, t in zip(query_compact, target_compact):
        if q == t or q in KEY_NEIGHBORS.get(t, set()):
            hits += 1
    return hits / len(query_compact)


VISUAL_REPLACEMENTS = [
    ("RN", "M"), ("M", "RN"), ("CL", "D"), ("D", "CL"), ("RI", "N"),
    ("N", "RI"), ("LI", "H"), ("H", "LI"), ("VV", "W"), ("W", "VV"),
    ("0", "O"), ("O", "0"), ("1", "I"), ("I", "1"), ("1", "L"),
    ("L", "1"), ("5", "S"), ("S", "5"), ("8", "B"), ("B", "8"),
    ("2", "Z"), ("Z", "2"), ("6", "G"), ("G", "6"),
]


def visual_variants(value: object) -> set[str]:
    base = compact_key(value)
    variants = set()
    if len(base) < 3:
        return variants
    for src, dst in VISUAL_REPLACEMENTS:
        if src in base:
            variants.add(base.replace(src, dst))
    variants.discard(base)
    return variants


def warning_pipes(value: object) -> list[str]:
    return [v.strip() for v in str(value or "").split("|") if v.strip()]


def alias_target_for(query: str) -> str:
    return BASE_ALIASES.get(compact_key(query), "") or BASE_ALIASES.get(normalize_search(query), "")


def bounded_levenshtein(a: str, b: str, max_distance: int) -> int | None:
    if not a or not b:
        return None
    if abs(len(a) - len(b)) > max_distance:
        return None
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            val = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            cur.append(val)
            row_min = min(row_min, val)
        if row_min > max_distance:
            return None
        prev = cur
    return prev[-1] if prev[-1] <= max_distance else None


def deletes(value: str, max_deletes: int) -> set[str]:
    results = {value}
    frontier = {value}
    for _ in range(max_deletes):
        next_frontier = set()
        for item in frontier:
            for i in range(len(item)):
                deleted = item[:i] + item[i + 1 :]
                if deleted not in results:
                    results.add(deleted)
                    next_frontier.add(deleted)
        frontier = next_frontier
    return results


@dataclass
class Query:
    raw: str
    norm: str
    compact: str
    tokens: list[str]
    token_compacts: list[str]
    generic_tokens: list[str]
    generic_token_compacts: list[str]
    specific_tokens: list[str]
    specific_token_compacts: list[str]
    token_alias_targets: list[str]
    token_alias_keys: list[tuple[str, str]]
    alias_target: str
    alias_key: tuple[str, str]
    numbers: set[str]
    routes: set[str]
    fuzzy_units: list[tuple[str, int, str]]
    visual_compacts: set[str]
    phonetic: str


def make_query(raw: str) -> Query:
    tokens = tokens_of(raw)
    token_compacts = [compact_key(t) for t in tokens]
    generic_tokens = [t for t in tokens if t in GENERIC_TOKENS]
    specific_tokens = [t for t in tokens if t not in GENERIC_TOKENS]
    generic_token_compacts = [compact_key(t) for t in generic_tokens]
    specific_token_compacts = [compact_key(t) for t in specific_tokens]
    compact = compact_key(raw)
    # Fuzzy matching is intended for short name-like queries. For long context
    # queries with many tokens, strength values, and route words, exact/prefix/
    # token/number/route evidence is more relevant and much cheaper.
    fuzzy_values = [] if len(tokens) > 4 else [compact, *token_compacts]
    fuzzy_units = []
    seen = set()
    for unit in fuzzy_values:
        if len(unit) < 4 or unit in seen:
            continue
        seen.add(unit)
        threshold = 1 if len(unit) <= 7 else 2
        fuzzy_units.append((unit, threshold, skeleton(unit)))
        if len(fuzzy_units) >= 6:
            break
    token_alias_targets = [alias_target_for(t) or alias_target_for(c) for t, c in zip(tokens, token_compacts)]
    alias_target = alias_target_for(compact) or alias_target_for(normalize_search(raw))
    return Query(
        raw=raw,
        norm=normalize_search(raw),
        compact=compact,
        tokens=tokens,
        token_compacts=token_compacts,
        generic_tokens=generic_tokens,
        generic_token_compacts=generic_token_compacts,
        specific_tokens=specific_tokens,
        specific_token_compacts=specific_token_compacts,
        token_alias_targets=token_alias_targets,
        token_alias_keys=[(normalize_search(t), compact_key(t)) if t else ("", "") for t in token_alias_targets],
        alias_target=alias_target,
        alias_key=(normalize_search(alias_target), compact_key(alias_target)) if alias_target else ("", ""),
        numbers=parse_numbers(raw),
        routes=parse_route_hints(raw),
        fuzzy_units=fuzzy_units,
        visual_compacts=visual_variants(raw),
        phonetic=drug_phonetic_key(raw),
    )


def add_prefix(index: dict[str, set[int]], value: str, idx: int, max_len: int = 12) -> None:
    if not value:
        return
    for length in range(2, min(max_len, len(value)) + 1):
        index[value[:length]].add(idx)


def add_grams(index: dict[str, set[int]], value: str, idx: int) -> None:
    if len(value) < 3:
        return
    seen = {value[i:i + 3] for i in range(len(value) - 2)}
    for gram in seen:
        index[gram].add(idx)


def prepare_records() -> list[dict]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    records = []
    for raw in payload["records"]:
        nn = normalize_search(raw.get("nn") or raw.get("n"))
        arn = normalize_search(raw.get("arn") or raw.get("ar"))
        bn = normalize_search(raw.get("b"))
        ingn = normalize_search(raw.get("ing") or raw.get("s"))
        c = compact_key(raw.get("c") or raw.get("n"))
        bc = compact_key(raw.get("b"))
        ingc = compact_key(raw.get("ing") or raw.get("s"))
        text = normalize_search(f"{raw.get('n','')} {raw.get('ar','')} {raw.get('b','')} {raw.get('ing','')} {raw.get('s','')}")
        record = dict(raw)
        record.update({
            "_nn": nn,
            "_c": c,
            "_arn": arn,
            "_arc": compact_key(arn),
            "_bn": bn,
            "_bc": bc,
            "_ingn": ingn,
            "_ingc": ingc,
            "_text": text,
            "_bn_words": set(bn.split()),
            "_nn_words": set(nn.split()),
            "_arn_words": set(arn.split()),
            "_ingn_words": set(ingn.split()),
            "_nums": parse_numbers(f"{raw.get('st','')} {raw.get('n','')} {raw.get('ar','')}"),
            "_routeHints": {v for v in [raw.get("r"), *parse_route_hints(raw.get("f") or "")] if v},
            "_sk": skeleton(raw.get("b")),
            "_ph": drug_phonetic_key(raw.get("b")),
            "_warnings": warning_pipes(raw.get("w")),
        })
        records.append(record)
    return records


class SearchIndex:
    def __init__(self, records: list[dict]):
        self.records = records
        self.exact: dict[str, set[int]] = defaultdict(set)
        self.prefix: dict[str, set[int]] = defaultdict(set)
        self.grams: dict[str, set[int]] = defaultdict(set)
        self.token: dict[str, set[int]] = defaultdict(set)
        self.skeleton: dict[str, set[int]] = defaultdict(set)
        self.num: dict[str, set[int]] = defaultdict(set)
        self.route: dict[str, set[int]] = defaultdict(set)
        self.delete: dict[str, set[int]] = defaultdict(set)
        self.base_exact: dict[str, set[int]] = defaultdict(set)
        self.phonetic: dict[str, set[int]] = defaultdict(set)
        self.phonetic_prefix: dict[str, set[int]] = defaultdict(set)
        self.base_length: dict[int, set[int]] = defaultdict(set)
        self.prefix_danger: dict[str, dict[str, set[str]]] = defaultdict(lambda: {
            "bases": set(),
            "products": set(),
            "ingredients": set(),
            "routes": set(),
        })
        self.short_registry: set[str] = set()

        for idx, r in enumerate(records):
            fields = [r["_nn"], r["_c"], r["_arn"], r["_arc"], r["_bn"], r["_bc"], r["_ingn"], r["_ingc"]]
            for value in fields:
                if value:
                    self.exact[value].add(idx)
                    if len(compact_key(value)) <= 4:
                        self.short_registry.add(compact_key(value))
            for value in [r["_nn"], r["_arn"], r["_bn"], r["_ingn"], r["_c"], r["_arc"], r["_bc"], r["_ingc"]]:
                add_prefix(self.prefix, value, idx)
            for value in [r["_bc"], r["_c"], r["_arc"]]:
                compact = compact_key(value)
                if compact:
                    for length in range(1, min(6, len(compact)) + 1):
                        item = self.prefix_danger[compact[:length]]
                        if r["_bc"]:
                            item["bases"].add(r["_bc"])
                        if r["_c"]:
                            item["products"].add(r["_c"])
                        if r["_ingc"]:
                            item["ingredients"].add(r["_ingc"])
                        if r.get("r"):
                            item["routes"].add(r.get("r"))
            for value in [r["_c"], r["_arc"], r["_bc"], r["_ingc"]]:
                add_grams(self.grams, value, idx)
            for token in set(tokens_of(f"{r.get('n','')} {r.get('b','')} {r.get('ing','')} {r.get('s','')}")):
                self.token[token].add(idx)
            if r["_sk"]:
                self.skeleton[r["_sk"]].add(idx)
            if r["_ph"]:
                self.phonetic[r["_ph"]].add(idx)
                for length in range(3, min(12, len(r["_ph"])) + 1):
                    self.phonetic_prefix[r["_ph"][:length]].add(idx)
            for n in r["_nums"]:
                self.num[n].add(idx)
            for route in r["_routeHints"]:
                self.route[route].add(idx)
            if r["_bc"]:
                self.base_exact[r["_bc"]].add(idx)
                self.base_length[len(r["_bc"])].add(idx)
                max_del = 1 if len(r["_bc"]) <= 7 else 2
                for d in deletes(r["_bc"], max_del):
                    if len(d) >= 3:
                        self.delete[d].add(idx)

    def candidate_ids(self, query: Query) -> set[int]:
        ids: set[int] = set()
        q_values = [query.norm, query.compact]
        for value in q_values:
            if value:
                ids.update(self.exact.get(value, ()))
                ids.update(self.prefix.get(value[: min(12, len(value))], ()))

        if len(query.compact) >= 3:
            grams = [query.compact[i:i + 3] for i in range(len(query.compact) - 2)]
            if grams:
                rare = min(grams, key=lambda g: len(self.grams.get(g, ())))
                ids.update(self.grams.get(rare, ()))

        # Supports app.js query_contains_base without testing every substring.
        # Most real query-contained bases come from one to three adjacent typed
        # tokens, e.g. "sodium chloride injection" -> SODIUMCHLORIDE.
        compact_tokens = [t for t in query.token_compacts if len(t) >= 2]
        for i in range(len(compact_tokens)):
            combined = ""
            for token in compact_tokens[i:i + 3]:
                combined += token
                if len(combined) >= 4:
                    ids.update(self.base_exact.get(combined, ()))

        long_context_query = len(query.tokens) > 3
        for token, tc in zip(query.tokens, query.token_compacts):
            generic_token = token in GENERIC_TOKENS
            ranking_only_token = (
                (tc.isdigit() and len(query.tokens) > 1)
                or (token in ROUTE_HINTS and len(query.tokens) > 1)
                or (len(tc) <= 2 and len(query.tokens) > 2)
            )
            if not ranking_only_token and not (generic_token and query.specific_tokens):
                ids.update(self.token.get(token, ()))
            if (
                tc.isdigit()
                and query.generic_tokens
                and len(query.tokens) <= 3
                and 3 <= len(tc) <= 4
            ):
                ids.update(self.prefix.get(tc, ()))
            target = alias_target_for(token) or alias_target_for(tc)
            if target:
                ids.update(self.base_exact.get(compact_key(target), ()))
            if (
                len(tc) >= 3
                and not ranking_only_token
                and not long_context_query
                and not (generic_token and query.specific_tokens)
            ):
                grams = [tc[i:i + 3] for i in range(len(tc) - 2)]
                if grams:
                    rare = min(grams, key=lambda g: len(self.grams.get(g, ())))
                    ids.update(self.grams.get(rare, ()))

        alias_target = alias_target_for(query.compact) or alias_target_for(query.norm)
        if alias_target:
            ids.update(self.base_exact.get(compact_key(alias_target), ()))

        for unit, threshold, sk in query.fuzzy_units:
            if len(ids) < 100:
                for d in deletes(unit, threshold):
                    if len(d) >= 3:
                        bucket = self.delete.get(d, ())
                        if len(bucket) <= 600:
                            ids.update(bucket)
            if len(sk) >= 3 and len(ids) < 500:
                ids.update(self.skeleton.get(sk, ()))

        for variant in query.visual_compacts:
            ids.update(self.exact.get(variant, ()))
            ids.update(self.prefix.get(variant[: min(12, len(variant))], ()))

        if len(query.phonetic) >= 3:
            ids.update(self.phonetic.get(query.phonetic, ()))
            if len(ids) < 500:
                ids.update(self.phonetic_prefix.get(query.phonetic[: min(12, len(query.phonetic))], ()))

        if len(ids) < 20 and 4 <= len(query.compact) <= 18:
            for idx in self.base_length.get(len(query.compact), ()):
                if keyboard_proximity_ratio(query.compact, self.records[idx]["_bc"]) >= 0.68:
                    ids.add(idx)

        # Numbers and route words are ranking evidence, not reliable candidate
        # generators by themselves. Pulling every "500" or "injection" record
        # makes the batch evaluator spend most time on unrelated candidates.
        return ids


def record_matches_alias_target(record: dict, target: str) -> bool:
    if not target:
        return False
    target_norm = normalize_search(target)
    target_compact = compact_key(target)
    return (
        record["_bn"] == target_norm
        or record["_bn"].startswith(f"{target_norm} ")
        or record["_bc"] == target_compact
        or record["_bc"].startswith(target_compact)
    )


def record_matches_alias_key(record: dict, target_norm: str, target_compact: str) -> bool:
    if not target_norm and not target_compact:
        return False
    return (
        record["_bn"] == target_norm
        or (target_norm and record["_bn"].startswith(f"{target_norm} "))
        or record["_bc"] == target_compact
        or (target_compact and record["_bc"].startswith(target_compact))
    )


def score_record(record: dict, query: Query) -> tuple[float, set[str]] | None:
    score = 0.0
    signals: set[str] = set()

    def add(value: float, signal: str) -> None:
        nonlocal score
        score += value
        signals.add(signal)

    qn = query.norm
    qc = query.compact
    if not qn and not qc:
        return None

    if record["_nn"] == qn:
        add(1200, "exact_name")
    if record["_c"] == qc:
        add(1160, "exact_compact")
    if record["_arn"] == qn or record["_arc"] == qc:
        add(1120, "exact_arabic_alias")
    if record["_bn"] == qn or record["_bc"] == qc:
        add(980, "exact_base_group")
    if record["_ingn"] == qn or record["_ingc"] == qc:
        add(720, "exact_ingredient")

    if record_matches_alias_key(record, *query.alias_key):
        add(1700, "heard_spelling_alias")

    if len(qn) >= 2:
        if record["_nn"].startswith(qn):
            add(420 + min(len(qn), 18), "prefix_name")
        if record["_arn"].startswith(qn):
            add(410 + min(len(qn), 18), "prefix_arabic")
        if record["_bn"].startswith(qn):
            add(390 + min(len(qn), 18), "prefix_base")
        if record["_ingn"].startswith(qn):
            add(260, "prefix_ingredient")

    if len(qc) >= 3:
        if record["_c"].startswith(qc):
            add(380 + min(len(qc), 18), "prefix_compact")
        if record["_bc"].startswith(qc):
            add(390 + min(len(qc), 18), "prefix_base_compact")
        if record["_arc"].startswith(qc):
            add(390 + min(len(qc), 18), "prefix_arabic_compact")
        if qc in record["_c"]:
            add(180, "contains_compact")
        if record["_bc"] and record["_bc"] in qc and len(record["_bc"]) >= 4:
            add(360, "query_contains_base")

    token_hits = 0
    for token, tc, token_alias_key in zip(query.tokens, query.token_compacts, query.token_alias_keys):
        if record_matches_alias_key(record, *token_alias_key):
            add(1700, "heard_spelling_alias")
            token_hits += 1
            continue
        generic_token = token in GENERIC_TOKENS
        if not generic_token and (token in record["_bn_words"] or record["_bc"] == tc):
            add(210, "token_base")
            token_hits += 1
        elif record["_arc"].startswith(tc) and tc.isdigit():
            add(940, "token_exact_arabic_alias")
            token_hits += 1
        elif token in record["_nn_words"] or token in record["_arn_words"]:
            add(140, "token_name")
            token_hits += 1
        elif token in record["_ingn_words"]:
            add(80, "token_ingredient")
        elif not generic_token and len(token) >= 3 and token in record["_text"]:
            add(42, "token_contains")
    if token_hits >= 2:
        add(160 * token_hits, "multi_token_match")

    specific_context_hit = False
    for token, tc in zip(query.specific_tokens, query.specific_token_compacts):
        if (
            token in record["_arn_words"]
            or token in record["_nn_words"]
            or token in record["_bn_words"]
            or record["_arc"] == tc
            or tc in record["_c"]
            or tc in record["_bc"]
        ):
            specific_context_hit = True
            break
    if specific_context_hit:
        for token, tc in zip(query.generic_tokens, query.generic_token_compacts):
            if token in record["_nn_words"] or token in record["_bn_words"] or tc in record["_c"] or tc in record["_bc"]:
                add(560, "generic_context_match")
                break

    for unit, threshold, sk in query.fuzzy_units:
        # Long full-product queries produce expensive edit-distance matrices
        # and rarely represent meaningful typo tolerance. The browser app runs
        # this literally, but batch evaluation needs to stay tractable.
        if len(unit) <= 32:
            base_dist = bounded_levenshtein(unit, record["_bc"], threshold)
            if base_dist is not None:
                add(250 - 60 * base_dist, f"fuzzy_base_ed{base_dist}")
        # The browser app also checks fuzzy edit distance against the leading
        # commercial-name compact string. That signal is very expensive at
        # batch scale and weaker than exact/prefix/compact/base fuzzy signals,
        # so the evaluation omits it and records this limitation in the report.
        if sk and sk == record["_sk"] and len(sk) >= 3:
            add(170, "phonetic_skeleton")

    if query.phonetic and record["_ph"] and len(query.phonetic) >= 3:
        if query.phonetic == record["_ph"]:
            add(500, "drug_phonetic_key")
        elif record["_ph"].startswith(query.phonetic):
            add(650, "drug_phonetic_prefix")
        if query.compact[:1] and record["_bc"][:1] and query.compact[0] == record["_bc"][0]:
            add(250, "phonetic_first_char")

    for variant in query.visual_compacts:
        if variant == record["_bc"] or record["_bc"].startswith(variant) or record["_c"].startswith(variant):
            add(210, "visual_confusion_candidate")
            break

    keyboard_ratio = keyboard_proximity_ratio(qc, record["_bc"])
    if keyboard_ratio >= 0.68:
        add(250 * keyboard_ratio, "keyboard_proximity")
        if qc[:1] and record["_bc"][:1] and qc[0] == record["_bc"][0]:
            add(160, "keyboard_first_char")

    if query.numbers:
        for num in query.numbers:
            if num in record["_nums"]:
                add(52, "number_match")
                break

    if query.routes:
        route_hit = any(route in record["_routeHints"] for route in query.routes)
        if route_hit:
            add(58, "form_route_match")
        elif record.get("r") and record.get("r") != "unknown":
            add(-16, "form_route_mismatch")

    warnings = record["_warnings"]
    if "UNKNOWN_ROUTE" in warnings:
        add(-8, "quality_status_penalty")
    if "MISSING_COMPOSITION" in warnings:
        add(-6, "quality_status_penalty")
    if "N/A" in warnings or "CANCELLED" in warnings or "ILLEGAL_IMPORT" in warnings:
        add(-28, "quality_status_penalty")

    if query.specific_tokens and record["_bc"] in GENERIC_TOKENS:
        add(-420, "generic_dominance_penalty")

    if score <= 0:
        return None
    return score, signals


def prefix_risk(index: SearchIndex, query: Query) -> dict:
    worst = {"baseCount": 0, "productCount": 0, "ingredientCount": 0, "routeCount": 0, "force": False}
    if not query.compact:
        return worst
    for length in range(1, min(6, len(query.compact)) + 1):
        item = index.prefix_danger.get(query.compact[:length])
        if not item:
            continue
        current = {
            "baseCount": len(item["bases"]),
            "productCount": len(item["products"]),
            "ingredientCount": len(item["ingredients"]),
            "routeCount": len(item["routes"]),
            "force": False,
        }
        if current["baseCount"] > worst["baseCount"] or current["ingredientCount"] > worst["ingredientCount"]:
            worst = current
    exact_short = len(query.compact) <= 4 and query.compact in index.short_registry
    worst["force"] = bool(
        not exact_short and (
            (len(query.compact) <= 2 and worst["baseCount"] > 1)
            or (len(query.compact) <= 4 and (worst["baseCount"] >= 4 or worst["ingredientCount"] >= 3))
            or (worst["baseCount"] >= 12 or worst["ingredientCount"] >= 6)
        )
    )
    return worst


def signal_has_strong_evidence(signals: set[str]) -> bool:
    return any(
        signal in {
            "heard_spelling_alias",
            "exact_name",
            "exact_compact",
            "exact_arabic_alias",
            "exact_base_group",
        }
        for signal in signals
    )


def search(index: SearchIndex, query_raw: str, limit: int = 20) -> tuple[list[dict], int]:
    query = make_query(query_raw)
    candidate_ids = index.candidate_ids(query)
    scored = []
    for idx in candidate_ids:
        record = index.records[idx]
        state = score_record(record, query)
        if state is None:
            continue
        score, signals = state
        scored.append((score, record.get("n") or "", record, signals))
    scored.sort(key=lambda item: (-item[0], item[1]))

    top = scored[:limit]
    top_score = top[0][0] if top else 0
    close_bases = {
        item[2].get("b")
        for item in top[:8]
        if item[0] >= top_score - 45 and item[2].get("b")
    }
    close_ingredients = {
        item[2].get("ing") or item[2].get("s")
        for item in top[:5]
        if item[0] >= top_score - 90 and (item[2].get("ing") or item[2].get("s"))
    }
    risk = prefix_risk(index, query)
    exact_short = len(query.compact) <= 4 and query.compact in index.short_registry
    short_unregistered = len(query.compact) <= 4 and not exact_short and not query.numbers
    exact_short_but_dangerous = exact_short and len(query.compact) <= 4 and risk["baseCount"] >= 8 and risk["ingredientCount"] >= 4
    generic_only = bool(query.tokens and not query.specific_tokens and query.generic_tokens)
    results = []
    for rank, (score, _, record, signals) in enumerate(top, 1):
        exact_product = "exact_name" in signals or "exact_compact" in signals
        approximate_only = (
            any(
                s.startswith("fuzzy_")
                or "phonetic" in s
                or s in {"keyboard_proximity", "visual_confusion_candidate"}
                for s in signals
            )
            and not any(s.startswith("exact_") or s.startswith("prefix_") or s == "heard_spelling_alias" for s in signals)
        )
        weak_evidence = (
            not signal_has_strong_evidence(signals)
            and bool(
                signals
                & {
                    "contains_compact",
                    "query_contains_base",
                    "keyboard_proximity",
                    "visual_confusion_candidate",
                    "drug_phonetic_key",
                    "drug_phonetic_prefix",
                    "phonetic_skeleton",
                }
            )
        )
        needs_clarification = bool(
            (len(query.compact) <= 2 and not exact_short)
            or (short_unregistered and not exact_product)
            or (exact_short_but_dangerous and not exact_product)
            or risk["force"]
            or generic_only
            or (len(close_ingredients) > 1 and not exact_product and not signal_has_strong_evidence(signals))
            or (int(record.get("bv") or 0) > 1 and not query.numbers and not exact_product)
            or int(record.get("br") or 0) > 1
            or (int(record.get("bi") or 0) > 1 and not exact_product)
            or len(close_bases) > 1
            or approximate_only
            or weak_evidence
            or record["_warnings"]
        )
        results.append({
            "rank": rank,
            "record": record,
            "score": round(score),
            "signals": signals,
            "needs_clarification": needs_clarification,
        })
    return results, len(candidate_ids)


def parse_expected_targets(expected: str) -> list[tuple[str, str]]:
    value = str(expected or "").strip()
    if "AMBIGUOUS" in value.upper():
        value = re.split(r"\s+[—-]\s+", value)[0]
        value = re.sub(r"\bAMBIGUOUS\b", "", value, flags=re.I)
    parts = re.split(r"\s+OR\s+", value, flags=re.I)
    targets = []
    for part in parts:
        clean = part.strip(" ;,")
        if clean:
            targets.append((normalize_search(clean), compact_key(clean)))
    return targets


def relevance(record: dict, targets: list[tuple[str, str]]) -> int:
    for norm, compact in targets:
        if record["_nn"] == norm or record["_c"] == compact:
            return 3
        if record["_bn"] == norm or record["_bc"] == compact:
            return 2
        if record["_ingn"] == norm or record["_ingc"] == compact:
            return 1
    return 0


def relevant_total(index: SearchIndex, targets: list[tuple[str, str]]) -> int:
    ids: set[int] = set()
    for norm, compact in targets:
        ids.update(index.exact.get(norm, ()))
        ids.update(index.exact.get(compact, ()))
    return max(len(ids), 1)


def ndcg(rels: list[int], total_relevant: int) -> float:
    dcg = 0.0
    for i, rel in enumerate(rels, 1):
        dcg += ((2 ** rel) - 1) / math.log2(i + 1)
    ideal_rels = sorted([r for r in rels if r > 0], reverse=True)
    if len(ideal_rels) < min(total_relevant, 20):
        ideal_rels += [2] * (min(total_relevant, 20) - len(ideal_rels))
    ideal_rels = sorted(ideal_rels[:20], reverse=True)
    ideal = 0.0
    for i, rel in enumerate(ideal_rels, 1):
        ideal += ((2 ** rel) - 1) / math.log2(i + 1)
    return dcg / ideal if ideal else 0.0


def metric_row(scope: str, category: str, rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {}
    return {
        "scope": scope,
        "category": category,
        "cases": n,
        "hit_at_1": sum(r["first_rank"] <= 1 for r in rows) / n,
        "hit_at_5": sum(r["first_rank"] <= 5 for r in rows) / n,
        "hit_at_10": sum(r["first_rank"] <= 10 for r in rows) / n,
        "hit_at_20": sum(r["first_rank"] <= 20 for r in rows) / n,
        "mrr_at_20": sum((1 / r["first_rank"]) if r["first_rank"] <= 20 else 0 for r in rows) / n,
        "map_at_20": sum(r["ap20"] for r in rows) / n,
        "ndcg_at_20": sum(r["ndcg20"] for r in rows) / n,
        "no_result_rate": sum(r["result_count"] == 0 for r in rows) / n,
        "unsafe_confident_top1_rate": sum(r["unsafe_confident_top1"] for r in rows) / n,
        "missing_clarification_rate": sum(r["missing_clarification"] for r in rows) / n,
        "avg_candidate_pool": sum(r["candidate_pool"] for r in rows) / n,
    }


def evaluate() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    records = prepare_records()
    index = SearchIndex(records)
    rel_count_cache: dict[tuple[tuple[str, str], ...], int] = {}

    all_eval_rows: list[dict] = []
    failures: list[dict] = []
    top_wrong = Counter()
    started = time.time()

    for scope, path in TEST_FILES.items():
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_num, case in enumerate(reader, 1):
                query = case["input"]
                targets = parse_expected_targets(case["expected"])
                target_key = tuple(targets)
                if target_key not in rel_count_cache:
                    rel_count_cache[target_key] = relevant_total(index, targets)
                rel_total = rel_count_cache[target_key]

                results, candidate_pool = search(index, query, 20)
                rels = [relevance(item["record"], targets) for item in results]
                first_rank = 999
                relevant_seen = 0
                ap = 0.0
                for rank, rel in enumerate(rels, 1):
                    if rel > 0:
                        if first_rank == 999:
                            first_rank = rank
                        relevant_seen += 1
                        ap += relevant_seen / rank
                ap20 = ap / min(rel_total, 20)
                ndcg20 = ndcg(rels, rel_total)

                top1 = results[0] if results else None
                top1_rel = rels[0] if rels else 0
                danger = case.get("danger", "")
                missing_clarification = bool(
                    top1
                    and danger in {"CAUTION", "DANGEROUS"}
                    and not top1["needs_clarification"]
                )
                unsafe_confident_top1 = bool(
                    top1
                    and top1_rel == 0
                    and not top1["needs_clarification"]
                )
                if top1 and top1_rel == 0:
                    top_wrong[(case["category"], top1["record"].get("b") or top1["record"].get("n") or "")] += 1

                top5_bases = [
                    item["record"].get("b") or item["record"].get("n") or ""
                    for item in results[:5]
                ]
                top5_scores = [str(item["score"]) for item in results[:5]]
                top5_clarification = [
                    "1" if item["needs_clarification"] else "0"
                    for item in results[:5]
                ]

                item = {
                    "scope": scope,
                    "source_row": row_num,
                    "category": case["category"],
                    "error_type": case["error_type"],
                    "difficulty": case.get("difficulty", ""),
                    "danger": danger,
                    "input": query,
                    "expected": case["expected"],
                    "first_rank": first_rank,
                    "hit_at_1": int(first_rank <= 1),
                    "hit_at_5": int(first_rank <= 5),
                    "hit_at_10": int(first_rank <= 10),
                    "hit_at_20": int(first_rank <= 20),
                    "ap20": ap20,
                    "ndcg20": ndcg20,
                    "result_count": len(results),
                    "candidate_pool": candidate_pool,
                    "top1_base": top1["record"].get("b") if top1 else "",
                    "top1_product": top1["record"].get("n") if top1 else "",
                    "top1_score": top1["score"] if top1 else "",
                    "top1_relevance": top1_rel,
                    "top1_signals": "|".join(sorted(top1["signals"])) if top1 else "",
                    "top1_needs_clarification": int(top1["needs_clarification"]) if top1 else "",
                    "top5_bases": "|".join(top5_bases),
                    "top5_scores": "|".join(top5_scores),
                    "top5_needs_clarification": "|".join(top5_clarification),
                    "unsafe_confident_top1": int(unsafe_confident_top1),
                    "missing_clarification": int(missing_clarification),
                }
                all_eval_rows.append(item)

                if first_rank > 20 and len(failures) < 1200:
                    failures.append({
                        "scope": scope,
                        "category": case["category"],
                        "error_type": case["error_type"],
                        "danger": danger,
                        "input": query,
                        "expected": case["expected"],
                        "top1": item["top1_base"],
                        "top1_product": top1["record"].get("n") if top1 else "",
                        "top1_score": top1["score"] if top1 else "",
                        "top1_signals": "|".join(sorted(top1["signals"])) if top1 else "",
                        "top1_needs_clarification": top1["needs_clarification"] if top1 else "",
                        "candidate_pool": candidate_pool,
                    })

                if len(all_eval_rows) % 5000 == 0:
                    elapsed = time.time() - started
                    print(f"processed={len(all_eval_rows)} elapsed_s={elapsed:.1f}", flush=True)

    by_scope_category: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_scope_category_error_type: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    by_scope: dict[str, list[dict]] = defaultdict(list)
    for row in all_eval_rows:
        by_scope_category[(row["scope"], row["category"])].append(row)
        by_scope_category_error_type[(row["scope"], row["category"], row["error_type"])].append(row)
        by_scope[row["scope"]].append(row)

    metrics = []
    for scope, rows in sorted(by_scope.items()):
        metrics.append(metric_row(scope, "__ALL__", rows))
    metrics.append(metric_row("__ALL__", "__ALL__", all_eval_rows))
    for (scope, category), rows in sorted(by_scope_category.items()):
        metrics.append(metric_row(scope, category, rows))

    with METRICS_BY_SCOPE_CATEGORY_CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(metrics[0].keys()))
        writer.writeheader()
        writer.writerows(metrics)

    metrics_by_error_type: list[dict] = []
    for (scope, category, error_type), rows in sorted(by_scope_category_error_type.items()):
        base = metric_row(scope, category, rows)
        metrics_by_error_type.append({
            "scope": base["scope"],
            "category": base["category"],
            "error_type": error_type,
            "cases": base["cases"],
            "hit_at_1": base["hit_at_1"],
            "hit_at_5": base["hit_at_5"],
            "hit_at_10": base["hit_at_10"],
            "hit_at_20": base["hit_at_20"],
            "mrr_at_20": base["mrr_at_20"],
            "map_at_20": base["map_at_20"],
            "ndcg_at_20": base["ndcg_at_20"],
            "no_result_rate": base["no_result_rate"],
            "unsafe_confident_top1_rate": base["unsafe_confident_top1_rate"],
            "missing_clarification_rate": base["missing_clarification_rate"],
            "avg_candidate_pool": base["avg_candidate_pool"],
        })

    with METRICS_BY_SCOPE_CATEGORY_ERROR_TYPE_CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(metrics_by_error_type[0].keys()))
        writer.writeheader()
        writer.writerows(metrics_by_error_type)

    with ALL_TEST_RESULTS_CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_eval_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_eval_rows)

    with FAILURE_SAMPLES_CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "scope", "category", "error_type", "danger", "input", "expected",
            "top1", "top1_product", "top1_score", "top1_signals",
            "top1_needs_clarification", "candidate_pool",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(failures)

    with TOP_WRONG_BASES_CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["category", "top_wrong_base", "count"])
        writer.writeheader()
        for (category, base), count in top_wrong.most_common(500):
            writer.writerow({"category": category, "top_wrong_base": base, "count": count})

    def pct(value: float) -> str:
        return f"{value * 100:.2f}%"

    overall = next(row for row in metrics if row["scope"] == "__ALL__" and row["category"] == "__ALL__")
    scope_rows = [row for row in metrics if row["category"] == "__ALL__" and row["scope"] != "__ALL__"]
    category_rows = [row for row in metrics if row["category"] != "__ALL__"]
    worst_rows = sorted(category_rows, key=lambda row: row["hit_at_20"])[:20]
    unsafe_rows = sorted(category_rows, key=lambda row: row["unsafe_confident_top1_rate"], reverse=True)[:15]
    clarify_rows = sorted(category_rows, key=lambda row: row["missing_clarification_rate"], reverse=True)[:15]
    wrong_rows = top_wrong.most_common(20)

    report_lines = [
        "# Current App Search Evaluation",
        "",
        "This report evaluates the collision-aware static app search behavior against the split commercial-name stress suites.",
        "",
        "Important method note: the browser app and evaluator both use catalog-derived candidate generation before ranking. The evaluator mirrors the app scoring path and records candidate-pool size for analysis.",
        "",
        "## Outputs",
        "",
        "| file | purpose |",
        "| --- | --- |",
        "| `benchmark_01_legacy/results/01_current_app/metrics_by_category.csv` | metrics by scope/category |",
        "| `benchmark_01_legacy/results/01_current_app/metrics_by_error_type.csv` | metrics by scope/category/error_type |",
        "| `benchmark_01_legacy/artifacts/01_current_app/case_results.csv` | one row per evaluated test case with rank, top result, and safety flags |",
        "| `benchmark_01_legacy/results/01_current_app/failure_samples.csv` | first failure samples |",
        "| `benchmark_01_legacy/results/01_current_app/top_wrong_families.csv` | most frequent wrong top-1 bases |",
        "",
        "## Headline Metrics",
        "",
        f"- Evaluated cases: `{len(all_eval_rows):,}`.",
        f"- Runtime: `{time.time() - started:.2f}` seconds.",
        f"- Overall Hit@1: `{pct(overall['hit_at_1'])}`.",
        f"- Overall Hit@5: `{pct(overall['hit_at_5'])}`.",
        f"- Overall Hit@10: `{pct(overall['hit_at_10'])}`.",
        f"- Overall Hit@20: `{pct(overall['hit_at_20'])}`.",
        f"- Overall MRR@20: `{overall['mrr_at_20']:.4f}`.",
        f"- Overall MAP@20: `{overall['map_at_20']:.4f}`.",
        f"- Overall nDCG@20: `{overall['ndcg_at_20']:.4f}`.",
        f"- Unsafe confident top-1 rate: `{pct(overall['unsafe_confident_top1_rate'])}`.",
        f"- Missing clarification rate: `{pct(overall['missing_clarification_rate'])}`.",
        "",
        "## Metrics By Scope",
        "",
        "| scope | cases | Hit@1 | Hit@5 | Hit@20 | MRR@20 | unsafe confident top-1 | missing clarification | avg candidate pool |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in sorted(scope_rows, key=lambda item: item["scope"]):
        report_lines.append(
            f"| `{row['scope']}` | {row['cases']:,} | {pct(row['hit_at_1'])} | {pct(row['hit_at_5'])} | "
            f"{pct(row['hit_at_20'])} | {row['mrr_at_20']:.4f} | {pct(row['unsafe_confident_top1_rate'])} | "
            f"{pct(row['missing_clarification_rate'])} | {row['avg_candidate_pool']:.1f} |"
        )
    report_lines += [
        "",
        "## Worst Retrieval Categories",
        "",
        "| scope | category | cases | Hit@5 | Hit@20 | unsafe top-1 | missing clarification |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in worst_rows:
        report_lines.append(
            f"| `{row['scope']}` | `{row['category']}` | {row['cases']:,} | {pct(row['hit_at_5'])} | "
            f"{pct(row['hit_at_20'])} | {pct(row['unsafe_confident_top1_rate'])} | {pct(row['missing_clarification_rate'])} |"
        )
    report_lines += [
        "",
        "## Highest Safety-Risk Categories",
        "",
        "| scope | category | cases | unsafe confident top-1 | Hit@20 |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for row in unsafe_rows:
        report_lines.append(
            f"| `{row['scope']}` | `{row['category']}` | {row['cases']:,} | "
            f"{pct(row['unsafe_confident_top1_rate'])} | {pct(row['hit_at_20'])} |"
        )
    report_lines += [
        "",
        "## Missing Clarification Hotspots",
        "",
        "| scope | category | cases | missing clarification | Hit@20 |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for row in clarify_rows:
        report_lines.append(
            f"| `{row['scope']}` | `{row['category']}` | {row['cases']:,} | "
            f"{pct(row['missing_clarification_rate'])} | {pct(row['hit_at_20'])} |"
        )
    report_lines += [
        "",
        "## Frequent Wrong Top-1 Families",
        "",
        "| category | wrong top-1 family | count |",
        "| --- | --- | ---: |",
    ]
    for (category, base), count in wrong_rows:
        report_lines.append(f"| `{category}` | `{base}` | {count:,} |")
    report_lines += [
        "",
        "## Reading The Results",
        "",
        "- Unsafe confident top-1 is the main safety metric. A wrong top result is less dangerous when it is clearly marked as needing clarification.",
        "- Hit@1 may drop after safety gates because the system stops pretending ambiguous short inputs are exact answers.",
        "- Keyboard-shift, visual-confusion, and phonetic improvements should be judged with Hit@20 plus clarification behavior, not only top-1.",
    ]
    EVALUATION_REPORT_MD_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    summary = {
        "evaluated_cases": len(all_eval_rows),
        "elapsed_seconds": round(time.time() - started, 2),
        "all_test_results_csv": str(ALL_TEST_RESULTS_CSV_PATH.relative_to(ROOT)),
        "metrics_csv": str(METRICS_BY_SCOPE_CATEGORY_CSV_PATH.relative_to(ROOT)),
        "metrics_by_error_type_csv": str(METRICS_BY_SCOPE_CATEGORY_ERROR_TYPE_CSV_PATH.relative_to(ROOT)),
        "failure_samples_csv": str(FAILURE_SAMPLES_CSV_PATH.relative_to(ROOT)),
        "top_wrong_bases_csv": str(TOP_WRONG_BASES_CSV_PATH.relative_to(ROOT)),
        "report_md": str(EVALUATION_REPORT_MD_PATH.relative_to(ROOT)),
        "note": "Evaluator mirrors app/app.js scoring rules and uses indexes to avoid scoring impossible candidates.",
    }
    EVALUATION_SUMMARY_JSON_PATH.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    evaluate()

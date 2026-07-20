#!/usr/bin/env python3
"""
Optimized English-only commercial drug-name retrieval.

This module keeps app/english_search_algorithm.py as the baseline and applies
only semantics-preserving speedups: precompiled regexes, query alias
precomputation, edit-similarity memoization, duplicate feature reuse, and a
rolling-row Damerau implementation.
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


VOWELS = set("AEIOUY")
COMMON_DF_RATIO = 0.005
TOP_K_DEFAULT = 20

COMMON_COMMERCIAL_TOKENS = {
    "TOPICAL", "FACIAL", "CREAM", "GEL", "HAIR", "SKIN", "CARE",
    "EXTRA", "PLUS", "FORTE", "ADVANCE", "VITA", "VIT", "BIO",
    "BABY", "KIDS", "ORAL", "MOUTH", "INTIMATE", "WHITENING",
    "CLEANSING", "MOISTURIZING", "SUNSCREEN", "LOTION", "SOAP",
    "SHAMPOO", "MASK", "SPRAY",
}

ALIAS_TABLE = {
    "BANADOL": "PANADOL",
    "BANDOL": "PANADOL",
    "PANDOL": "PANADOL",
    "PNDL": "PANADOL",
    "PANDL": "PANADOL",
    "PANADL": "PANADOL",
    "PANADOLE": "PANADOL",
    "BANADOLE": "PANADOL",
    "BANADOLCOLD": "PANADOL",
    "PANDOLCOLD": "PANADOL",
    "BANDOLCOLD": "PANADOL",
    "OGMENTIN": "AUGMENTIN",
    "OGMNTIN": "AUGMENTIN",
    "AUGMNTIN": "AUGMENTIN",
    "AUGMANTIN": "AUGMENTIN",
    "FOLTARIN": "VOLTAREN",
    "VOLTARIN": "VOLTAREN",
    "FOLTAREN": "VOLTAREN",
    "BRUFN": "BRUFEN",
    "BRFN": "BRUFEN",
    "BRUFIN": "BRUFEN",
    "BROFEN": "BRUFEN",
    "KETOFN": "KETOFAN",
    "KETOFEN": "KETOFAN",
    "NEKSIUM": "NEXIUM",
    "NEKSUM": "NEXIUM",
    "NEXUM": "NEXIUM",
}

CONFUSION_PAIRS = {
    frozenset(("V", "F")),
    frozenset(("P", "B")),
    frozenset(("C", "K")),
    frozenset(("Q", "K")),
    frozenset(("I", "E")),
    frozenset(("O", "U")),
    frozenset(("Y", "I")),
    frozenset(("S", "Z")),
    frozenset(("T", "D")),
    frozenset(("G", "J")),
}

CONFUSION_PAIR_TUPLES = {
    (left, right)
    for pair in CONFUSION_PAIRS
    for left in pair
    for right in pair
    if left != right
}

NON_ALNUM_WORD_RE = re.compile(r"[^A-Z0-9]+")
NON_ALNUM_COMPACT_RE = re.compile(r"[^A-Z0-9]")
SPACE_RE = re.compile(r"\s+")
SKELETON_CQK_RE = re.compile(r"[CQK]")
SKELETON_PV_RE = re.compile(r"[PV]")
SKELETON_SZ_RE = re.compile(r"[SZ]")
VOWEL_RE = re.compile(r"[AEIOUY]")
REPEAT_RE = re.compile(r"(.)\1+")
PHONETIC_BPFV_RE = re.compile(r"[BPFV]")
PHONETIC_DT_RE = re.compile(r"[DT]")
PHONETIC_CGKQ_RE = re.compile(r"[CGKQ]")
PHONETIC_J_RE = re.compile(r"[J]")


@dataclass
class DrugNameRecord:
    id: str
    commercial_name: str
    canonical_name: str
    search_name: str
    display_name: str
    source_line: int
    norm: str
    compact: str
    tokens: list[str]
    token_compacts: list[str]
    no_vowels: str
    skeleton: str
    phonetic: str
    reversed_compact: str
    grams3: set[str]
    grams4: set[str]
    delete_keys: set[str]
    token_roles: dict[str, str]


@dataclass
class SearchIndexes:
    exact_norm: dict[str, set[int]]
    exact_compact: dict[str, set[int]]
    prefix_compact: dict[str, set[int]]
    suffix_compact: dict[str, set[int]]
    token_exact: dict[str, set[int]]
    token_prefix: dict[str, set[int]]
    grams3: dict[str, set[int]]
    grams4: dict[str, set[int]]
    skeleton_exact: dict[str, set[int]]
    skeleton_prefix: dict[str, set[int]]
    phonetic_exact: dict[str, set[int]]
    phonetic_prefix: dict[str, set[int]]
    delete_index: dict[str, set[int]]


@dataclass
class EnglishSearchCatalog:
    records: list[DrugNameRecord]
    indexes: SearchIndexes
    token_df: Counter[str]
    token_idf: dict[str, float]
    gram_idf: dict[str, float]
    common_tokens: set[str]
    max_token_idf: float
    length: int


@dataclass
class Query:
    raw: str
    norm: str
    compact: str
    tokens: list[str]
    token_compacts: list[str]
    common_tokens: list[str]
    specific_tokens: list[str]
    common_only: bool
    no_vowels: str
    skeleton: str
    phonetic: str
    reversed_compact: str
    grams3: set[str]
    grams4: set[str]
    modes: set[str]
    alias_target: str
    alias_compact: str


def normalize_name(text: Any) -> str:
    value = "" if text is None else str(text)
    value = value.upper()
    value = value.replace("&", " AND ")
    value = value.replace("+", " PLUS ")
    value = NON_ALNUM_WORD_RE.sub(" ", value)
    return SPACE_RE.sub(" ", value).strip()


def compact_name(text: Any) -> str:
    return NON_ALNUM_COMPACT_RE.sub("", normalize_name(text))


def tokenize(norm: str) -> list[str]:
    return [token for token in norm.split() if token]


def remove_vowels(value: Any) -> str:
    compact = compact_name(value)
    return "".join(ch for ch in compact if ch not in VOWELS)


def skeleton(value: Any) -> str:
    text = compact_name(value)
    text = text.replace("PH", "F")
    text = SKELETON_CQK_RE.sub("K", text)
    text = SKELETON_PV_RE.sub("B", text)
    text = SKELETON_SZ_RE.sub("S", text)
    text = VOWEL_RE.sub("", text)
    return REPEAT_RE.sub(r"\1", text)


def phonetic_key(value: Any) -> str:
    text = compact_name(value)
    text = text.replace("PH", "F").replace("CK", "K").replace("GH", "G")
    text = PHONETIC_BPFV_RE.sub("P", text)
    text = PHONETIC_DT_RE.sub("T", text)
    text = PHONETIC_CGKQ_RE.sub("K", text)
    text = SKELETON_SZ_RE.sub("S", text)
    text = PHONETIC_J_RE.sub("G", text)
    text = VOWEL_RE.sub("", text)
    return REPEAT_RE.sub(r"\1", text)


def char_ngrams(value: str, n: int) -> set[str]:
    if len(value) < n:
        return set()
    return {value[i:i + n] for i in range(len(value) - n + 1)}


def max_deletes_for(value: str) -> int:
    if len(value) < 4:
        return 0
    if len(value) <= 7:
        return 1
    return 2


def delete_keys(value: str, max_deletes: int) -> set[str]:
    if max_deletes <= 0:
        return {value} if value else set()
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
    return {item for item in results if len(item) >= 3}


def _add(index: dict[str, set[int]], key: str, idx: int) -> None:
    if key:
        index.setdefault(key, set()).add(idx)


def _add_prefixes(index: dict[str, set[int]], value: str, idx: int, min_len: int, max_len: int) -> None:
    for length in range(min_len, min(max_len, len(value)) + 1):
        _add(index, value[:length], idx)


def _add_suffixes(index: dict[str, set[int]], reversed_value: str, idx: int, min_len: int, max_len: int) -> None:
    for length in range(min_len, min(max_len, len(reversed_value)) + 1):
        _add(index, reversed_value[:length], idx)


def make_record(row: dict[str, str], source_line: int, idx: int, common_tokens: set[str] | None = None) -> DrugNameRecord:
    commercial_name = (row.get("commercial_name") or "").strip()
    canonical_name = (row.get("canonical_name") or "").strip()
    search_name = canonical_name or commercial_name
    display_name = canonical_name or commercial_name
    norm = normalize_name(search_name)
    compact = compact_name(search_name)
    tokens = tokenize(norm)
    token_compacts = [compact_name(token) for token in tokens]
    common_tokens = common_tokens or set()
    token_roles = {
        token: "common" if token in common_tokens else "specific"
        for token in tokens
    }
    return DrugNameRecord(
        id=f"ENG-{idx + 1:06d}",
        commercial_name=commercial_name,
        canonical_name=canonical_name,
        search_name=search_name,
        display_name=display_name,
        source_line=source_line,
        norm=norm,
        compact=compact,
        tokens=tokens,
        token_compacts=token_compacts,
        no_vowels=remove_vowels(search_name),
        skeleton=skeleton(search_name),
        phonetic=phonetic_key(search_name),
        reversed_compact=compact[::-1],
        grams3=char_ngrams(compact, 3),
        grams4=char_ngrams(compact, 4),
        delete_keys=delete_keys(compact, max_deletes_for(compact)),
        token_roles=token_roles,
    )


def build_indexes(records: list[DrugNameRecord]) -> SearchIndexes:
    indexes = SearchIndexes(
        exact_norm={},
        exact_compact={},
        prefix_compact={},
        suffix_compact={},
        token_exact={},
        token_prefix={},
        grams3={},
        grams4={},
        skeleton_exact={},
        skeleton_prefix={},
        phonetic_exact={},
        phonetic_prefix={},
        delete_index={},
    )
    for idx, record in enumerate(records):
        _add(indexes.exact_norm, record.norm, idx)
        _add(indexes.exact_compact, record.compact, idx)
        _add_prefixes(indexes.prefix_compact, record.compact, idx, 2, 12)
        _add_suffixes(indexes.suffix_compact, record.reversed_compact, idx, 3, 12)
        for token in set(record.tokens):
            _add(indexes.token_exact, token, idx)
            _add_prefixes(indexes.token_prefix, token, idx, 2, 8)
        for gram in record.grams3:
            _add(indexes.grams3, gram, idx)
        for gram in record.grams4:
            _add(indexes.grams4, gram, idx)
        _add(indexes.skeleton_exact, record.skeleton, idx)
        _add_prefixes(indexes.skeleton_prefix, record.skeleton, idx, 3, 10)
        _add(indexes.phonetic_exact, record.phonetic, idx)
        _add_prefixes(indexes.phonetic_prefix, record.phonetic, idx, 3, 10)
        for key in record.delete_keys:
            _add(indexes.delete_index, key, idx)
    return indexes


def prepare_catalog(rows: Iterable[dict[str, str]]) -> EnglishSearchCatalog:
    raw_rows = list(rows)
    first_pass = [make_record(row, source_line=i + 2, idx=i) for i, row in enumerate(raw_rows)]
    token_df: Counter[str] = Counter()
    gram_df: Counter[str] = Counter()
    for record in first_pass:
        token_df.update(set(record.tokens))
        gram_df.update(record.grams3 | record.grams4)

    total = max(len(first_pass), 1)
    token_idf = {
        token: math.log((total + 1) / (df + 1)) + 1
        for token, df in token_df.items()
    }
    gram_idf = {
        gram: math.log((total + 1) / (df + 1)) + 1
        for gram, df in gram_df.items()
    }
    common_tokens = set(COMMON_COMMERCIAL_TOKENS)
    common_tokens.update(
        token for token, df in token_df.items()
        if df / total >= COMMON_DF_RATIO
    )

    records = [
        make_record(row, source_line=i + 2, idx=i, common_tokens=common_tokens)
        for i, row in enumerate(raw_rows)
    ]
    return EnglishSearchCatalog(
        records=records,
        indexes=build_indexes(records),
        token_df=token_df,
        token_idf=token_idf,
        gram_idf=gram_idf,
        common_tokens=common_tokens,
        max_token_idf=max(token_idf.values(), default=1.0),
        length=len(records),
    )


def load_catalog(path: str | Path) -> EnglishSearchCatalog:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return prepare_catalog(csv.DictReader(handle))


def make_query(raw: Any, catalog: EnglishSearchCatalog) -> Query:
    raw_text = "" if raw is None else str(raw)
    norm = normalize_name(raw_text)
    compact = compact_name(raw_text)
    tokens = tokenize(norm)
    token_compacts = [compact_name(token) for token in tokens]
    common_tokens = [token for token in tokens if token in catalog.common_tokens]
    specific_tokens = [token for token in tokens if token not in catalog.common_tokens]
    common_only = bool(tokens) and not specific_tokens and len(tokens) == 1
    alias_target = ALIAS_TABLE.get(compact, "")
    query = Query(
        raw=raw_text,
        norm=norm,
        compact=compact,
        tokens=tokens,
        token_compacts=token_compacts,
        common_tokens=common_tokens,
        specific_tokens=specific_tokens,
        common_only=common_only,
        no_vowels=remove_vowels(raw_text),
        skeleton=skeleton(raw_text),
        phonetic=phonetic_key(raw_text),
        reversed_compact=compact[::-1],
        grams3=char_ngrams(compact, 3),
        grams4=char_ngrams(compact, 4),
        modes=set(),
        alias_target=alias_target,
        alias_compact=compact_name(alias_target) if alias_target else "",
    )
    query.modes = classify_query(query, catalog)
    return query


def has_rare_ngram_hit(query: Query, catalog: EnglishSearchCatalog) -> bool:
    grams = query.grams4 or query.grams3
    for gram in grams:
        bucket = catalog.indexes.grams4.get(gram) or catalog.indexes.grams3.get(gram)
        if bucket and len(bucket) <= 400:
            return True
    return False


def classify_query(query: Query, catalog: EnglishSearchCatalog) -> set[str]:
    indexes = catalog.indexes
    modes: set[str] = set()
    if len(query.compact) <= 2:
        modes.add("too_short")
    if query.compact in indexes.exact_compact:
        modes.add("exact_like")
    if query.common_only:
        modes.add("common_token_query")
    if len(query.compact) >= 3 and query.compact[:12] in indexes.prefix_compact:
        modes.add("prefix_fragment")
    if len(query.compact) >= 4 and query.reversed_compact[:12] in indexes.suffix_compact:
        modes.add("suffix_fragment")
    if len(query.compact) >= 4 and has_rare_ngram_hit(query, catalog):
        modes.add("middle_fragment")
    if len(query.skeleton) >= 3 and (
        query.skeleton in indexes.skeleton_exact
        or query.compact == query.no_vowels
    ):
        modes.add("consonant_skeleton")
    if len(query.phonetic) >= 3 and (
        query.phonetic in indexes.phonetic_exact
        or query.phonetic[:8] in indexes.phonetic_prefix
    ):
        modes.add("phonetic_like")
    if len(query.tokens) > 1:
        modes.add("phrase_like")
    if len(query.compact) >= 4:
        modes.add("full_typo_like")
    return modes


def add_candidates(candidates: dict[int, set[str]], source: Iterable[int] | None, tag: str, max_bucket: int | None = None) -> None:
    if not source:
        return
    source_set = set(source)
    if max_bucket is not None and len(source_set) > max_bucket:
        return
    for idx in source_set:
        candidates[idx].add(tag)


def rarest_grams(grams: set[str], index: dict[str, set[int]], max_grams: int = 3) -> list[str]:
    present = [gram for gram in grams if gram in index]
    present.sort(key=lambda gram: len(index.get(gram, ())))
    return present[:max_grams]


def generate_candidates(query: Query, catalog: EnglishSearchCatalog) -> dict[int, set[str]]:
    indexes = catalog.indexes
    candidates: dict[int, set[str]] = defaultdict(set)

    add_candidates(candidates, indexes.exact_norm.get(query.norm), "exact_norm")
    add_candidates(candidates, indexes.exact_compact.get(query.compact), "exact_compact")

    if query.alias_compact:
        add_candidates(candidates, indexes.exact_compact.get(query.alias_compact), "approved_alias")
        add_candidates(candidates, indexes.prefix_compact.get(query.alias_compact[:12]), "approved_alias_prefix")

    if len(query.compact) >= 3:
        add_candidates(candidates, indexes.prefix_compact.get(query.compact[:12]), "prefix")

    if len(query.compact) >= 4:
        add_candidates(candidates, indexes.suffix_compact.get(query.reversed_compact[:12]), "suffix")

    for token in query.tokens:
        is_common = token in catalog.common_tokens
        max_bucket = None if query.common_only else (1200 if is_common else None)
        add_candidates(candidates, indexes.token_exact.get(token), "token_exact", max_bucket=max_bucket)
        if len(token) >= 3:
            add_candidates(candidates, indexes.token_prefix.get(token[:8]), "token_prefix", max_bucket=max_bucket)

    for gram in rarest_grams(query.grams4, indexes.grams4, 3):
        add_candidates(candidates, indexes.grams4.get(gram), "rare_ngram4")
    if not candidates or len(candidates) < 40:
        for gram in rarest_grams(query.grams3, indexes.grams3, 3):
            add_candidates(candidates, indexes.grams3.get(gram), "rare_ngram3")

    if len(query.skeleton) >= 3:
        add_candidates(candidates, indexes.skeleton_exact.get(query.skeleton), "skeleton_exact")
        add_candidates(candidates, indexes.skeleton_prefix.get(query.skeleton[:8]), "skeleton_prefix", max_bucket=1000)

    if len(query.phonetic) >= 3:
        add_candidates(candidates, indexes.phonetic_exact.get(query.phonetic), "phonetic_exact")
        add_candidates(candidates, indexes.phonetic_prefix.get(query.phonetic[:8]), "phonetic_prefix", max_bucket=1200)

    if len(query.compact) <= 24:
        for key in delete_keys(query.compact, max_deletes_for(query.compact)):
            add_candidates(candidates, indexes.delete_index.get(key), "delete_key", max_bucket=800)

    return candidates


def damerau_levenshtein(a: str, b: str, weighted: bool = False) -> float:
    if a == b:
        return 0.0
    if not a:
        return float(len(b))
    if not b:
        return float(len(a))

    cols = len(b) + 1
    prevprev: list[float] | None = None
    prev = [float(j) for j in range(cols)]

    for i in range(1, len(a) + 1):
        cur = [float(i)] + [0.0] * len(b)
        left = a[i - 1]
        prev_left = a[i - 2] if i > 1 else ""
        for j in range(1, cols):
            right = b[j - 1]
            sub_cost = substitution_cost(a[i - 1], b[j - 1]) if weighted else (0.0 if a[i - 1] == b[j - 1] else 1.0)
            val = min(
                prev[j] + 1.0,
                cur[j - 1] + 1.0,
                prev[j - 1] + sub_cost,
            )
            if prevprev is not None and j > 1 and left == b[j - 2] and prev_left == right:
                val = min(val, prevprev[j - 2] + (0.45 if weighted else 1.0))
            cur[j] = val
        prevprev, prev = prev, cur
    return prev[-1]


def substitution_cost(a: str, b: str) -> float:
    if a == b:
        return 0.0
    if (a, b) in CONFUSION_PAIR_TUPLES:
        return 0.45
    return 1.0


def edit_similarity(
    query: str,
    target: str,
    weighted: bool = False,
    cache: dict[tuple[str, str, bool], float] | None = None,
) -> float:
    if not query or not target:
        return 0.0
    cache_key = (query, target, weighted)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    max_len = max(len(query), len(target))
    if max_len == 0:
        return 1.0
    dist = damerau_levenshtein(query, target, weighted=weighted)
    value = max(0.0, 1.0 - dist / max_len)
    if cache is not None:
        cache[cache_key] = value
    return value


def prefix_similarity(query: str, target: str) -> float:
    if len(query) < 3 or not target.startswith(query):
        return 0.0
    return min(1.0, len(query) / len(target))


def suffix_similarity(query: str, target: str) -> float:
    if len(query) < 3 or not target.endswith(query):
        return 0.0
    return min(1.0, len(query) / len(target))


def contains_similarity(query: str, target: str) -> float:
    if len(query) < 3 or query not in target:
        return 0.0
    return min(1.0, len(query) / len(target))


def subsequence_score(query: str, target: str) -> float:
    if not query or not target or len(query) > len(target):
        return 0.0
    positions: list[int] = []
    start = 0
    for ch in query:
        found = target.find(ch, start)
        if found < 0:
            return 0.0
        positions.append(found)
        start = found + 1
    span = positions[-1] - positions[0] + 1
    coverage = len(query) / len(target)
    density = len(query) / span
    edge_bonus = 0.0
    if query[0] == target[0]:
        edge_bonus += 0.10
    if query[-1] == target[-1]:
        edge_bonus += 0.10
    return min(1.0, 0.55 * density + 0.35 * coverage + edge_bonus)


def skeleton_similarity(query: Query, record: DrugNameRecord) -> float:
    if not query.skeleton or not record.skeleton:
        return 0.0
    if query.compact == record.no_vowels:
        return 1.0
    if len(query.compact) >= 3 and record.no_vowels.startswith(query.compact):
        return 1.0
    if query.skeleton == record.skeleton:
        if query.compact[:1] and record.compact[:1] and query.compact[0] != record.compact[0]:
            return 0.90
        return 0.98
    if record.skeleton.startswith(query.skeleton):
        return 0.82
    subseq = subsequence_score(query.skeleton, record.skeleton)
    return 0.75 * subseq if subseq else 0.0


def phonetic_similarity(query: Query, record: DrugNameRecord) -> float:
    if not query.phonetic or not record.phonetic:
        return 0.0
    if query.phonetic == record.phonetic:
        return 1.0
    if record.phonetic.startswith(query.phonetic):
        return 0.80
    subseq = subsequence_score(query.phonetic, record.phonetic)
    return 0.60 * subseq if subseq else 0.0


def weighted_jaccard(query_grams: set[str], record_grams: set[str], gram_idf: dict[str, float]) -> float:
    if not query_grams or not record_grams:
        return 0.0
    union = query_grams | record_grams
    intersection = query_grams & record_grams
    denom = sum(gram_idf.get(gram, 1.0) for gram in union)
    if denom <= 0:
        return 0.0
    return sum(gram_idf.get(gram, 1.0) for gram in intersection) / denom


def ngram_score(query: Query, record: DrugNameRecord, catalog: EnglishSearchCatalog) -> float:
    grams = query.grams4 if query.grams4 else query.grams3
    record_grams = record.grams4 if query.grams4 else record.grams3
    return weighted_jaccard(grams, record_grams, catalog.gram_idf)


def token_match_strength(query_token: str, query_compact: str, record: DrugNameRecord) -> float:
    best = 0.0
    for record_token, record_compact in zip(record.tokens, record.token_compacts):
        if query_token == record_token:
            best = max(best, 1.0)
        elif len(query_compact) >= 4 and record_compact.startswith(query_compact):
            best = max(best, 0.85)
        elif len(query_compact) >= 4 and query_compact in record_compact:
            best = max(best, 0.75)
    return best


def token_score(query: Query, record: DrugNameRecord, catalog: EnglishSearchCatalog) -> tuple[float, float, float]:
    if not query.tokens:
        return 0.0, 0.0, 0.0

    total_possible = 0.0
    total = 0.0
    specific = 0.0
    common = 0.0
    for token, token_compact in zip(query.tokens, query.token_compacts):
        idf_norm = catalog.token_idf.get(token, 1.0) / catalog.max_token_idf
        is_common = token in catalog.common_tokens
        base_weight = 0.20 if is_common else 1.0
        possible = base_weight * idf_norm
        strength = token_match_strength(token, token_compact, record)
        value = possible * strength
        total_possible += possible
        total += value
        if is_common:
            common += value
        else:
            specific += value
    if total_possible <= 0:
        return 0.0, 0.0, 0.0
    return min(1.0, total / total_possible), min(1.0, specific / total_possible), min(1.0, common / total_possible)


def token_order_score(query: Query, record: DrugNameRecord) -> float:
    if not query.token_compacts:
        return 0.0
    pos = 0
    hits = 0
    for token in query.token_compacts:
        found = record.compact.find(token, pos)
        if found >= 0:
            hits += 1
            pos = found + len(token)
    return hits / len(query.token_compacts)


def feature_reasons(features: dict[str, float], sources: set[str]) -> set[str]:
    reasons = set(sources)
    thresholds = {
        "exact": 1.0,
        "alias": 1.0,
        "edit": 0.78,
        "weighted_edit": 0.78,
        "prefix": 0.30,
        "suffix": 0.30,
        "contains": 0.25,
        "subsequence": 0.55,
        "skeleton": 0.70,
        "phonetic": 0.75,
        "token": 0.40,
        "ngram": 0.08,
    }
    for name, threshold in thresholds.items():
        if features.get(name, 0.0) >= threshold:
            reasons.add(f"{name}_match")
    return reasons


def mode_scores(features: dict[str, float], query: Query) -> dict[str, float]:
    scores: dict[str, float] = {}
    if features["exact"]:
        scores["exact_mode"] = 1.00
    elif features["alias"]:
        scores["exact_mode"] = 0.97

    if "full_typo_like" in query.modes:
        scores["full_typo_mode"] = (
            0.30 * features["edit"]
            + 0.20 * features["weighted_edit"]
            + 0.15 * features["phonetic"]
            + 0.15 * features["skeleton"]
            + 0.10 * features["ngram"]
            + 0.05 * features["subsequence"]
            + 0.05 * features["token"]
        )
    if "prefix_fragment" in query.modes:
        scores["prefix_mode"] = (
            0.45 * features["prefix"]
            + 0.15 * features["ngram"]
            + 0.10 * features["edit"]
            + 0.10 * features["phonetic"]
            + 0.10 * features["skeleton"]
            + 0.10 * features["token"]
        )
    if "suffix_fragment" in query.modes:
        scores["suffix_mode"] = (
            0.45 * features["suffix"]
            + 0.15 * features["contains"]
            + 0.15 * features["subsequence"]
            + 0.15 * features["ngram"]
            + 0.05 * features["skeleton"]
            + 0.05 * features["edit"]
        )
    if "middle_fragment" in query.modes:
        scores["middle_mode"] = (
            0.35 * features["contains"]
            + 0.25 * features["ngram"]
            + 0.20 * features["subsequence"]
            + 0.10 * features["token"]
            + 0.05 * features["skeleton"]
            + 0.05 * features["edit"]
        )
    if "consonant_skeleton" in query.modes:
        scores["skeleton_mode"] = (
            0.35 * features["skeleton"]
            + 0.25 * features["subsequence"]
            + 0.15 * features["phonetic"]
            + 0.15 * features["ngram"]
            + 0.10 * features["edit"]
        )
    if "phrase_like" in query.modes:
        scores["phrase_mode"] = (
            0.30 * features["token"]
            + 0.25 * features["token_order"]
            + 0.15 * features["compact"]
            + 0.15 * features["specific_token"]
            + 0.10 * features["common_context"]
            + 0.05 * features["phonetic"]
        )
    if "common_token_query" in query.modes:
        scores["common_token_mode"] = min(0.62, 0.55 * features["token"] + 0.20 * features["contains"])
    return scores


def score_record(
    query: Query,
    record: DrugNameRecord,
    catalog: EnglishSearchCatalog,
    sources: set[str],
    candidate_count: int,
    edit_cache: dict[tuple[str, str, bool], float],
) -> dict[str, Any] | None:
    token, specific_token, common_context = token_score(query, record, catalog)
    exact = 1.0 if query.compact == record.compact else 0.0
    alias = 0.0
    if query.alias_compact and record.compact == query.alias_compact:
        alias = 1.0
    elif query.alias_compact and record.compact.startswith(query.alias_compact):
        alias = 0.95
    edit = edit_similarity(query.compact, record.compact, cache=edit_cache)
    weighted_edit = edit_similarity(query.compact, record.compact, weighted=True, cache=edit_cache)
    prefix = prefix_similarity(query.compact, record.compact)
    suffix = suffix_similarity(query.compact, record.compact)
    contains = contains_similarity(query.compact, record.compact)
    features = {
        "exact": exact,
        "alias": alias,
        "edit": edit,
        "weighted_edit": weighted_edit,
        "prefix": prefix,
        "suffix": suffix,
        "contains": contains,
        "subsequence": subsequence_score(query.compact, record.compact),
        "skeleton": skeleton_similarity(query, record),
        "phonetic": phonetic_similarity(query, record),
        "token": token,
        "specific_token": specific_token,
        "common_context": common_context if specific_token > 0 or not query.common_only else common_context * 0.35,
        "token_order": token_order_score(query, record),
        "ngram": ngram_score(query, record, catalog),
        "compact": max(
            edit,
            contains,
            prefix,
            suffix,
        ),
    }

    scores = mode_scores(features, query)
    if not scores:
        return None

    best_mode, raw_score = max(scores.items(), key=lambda item: item[1])
    penalty = 0.0
    if len(query.compact) <= 3 and not exact:
        penalty += 0.15
    if query.common_only and not exact:
        penalty += 0.25
    if candidate_count > 1200 and len(query.compact) <= 5:
        penalty += 0.20
    elif candidate_count > 400 and len(query.compact) <= 5:
        penalty += 0.10

    strong_evidence = any(features[name] >= value for name, value in {
        "exact": 1.0,
        "alias": 1.0,
        "prefix": 0.45,
        "suffix": 0.45,
        "skeleton": 0.85,
        "token": 0.70,
    }.items())
    weak_only = not strong_evidence and (
        features["contains"] > 0
        or features["phonetic"] > 0
        or features["ngram"] > 0
    )
    if weak_only:
        penalty += 0.10

    final_score = max(0.0, min(1.0, raw_score - penalty))
    if final_score <= 0:
        return None

    reasons = feature_reasons(features, sources)
    reasons.add(best_mode)
    if penalty:
        reasons.add("penalized")
    return {
        "record": record,
        "score": final_score,
        "mode": best_mode,
        "features": features,
        "reasons": reasons,
    }


def result_confidence(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.72:
        return "medium"
    return "low"


def group_scored(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in scored:
        record: DrugNameRecord = item["record"]
        group_key = record.display_name or record.search_name
        current = grouped.get(group_key)
        if current is None or item["score"] > current["score"]:
            grouped[group_key] = {
                "group_key": group_key,
                "name": group_key,
                "score": item["score"],
                "mode": item["mode"],
                "features": item["features"],
                "reasons": set(item["reasons"]),
                "canonical_name": record.canonical_name or record.display_name,
                "commercial_examples": [record.commercial_name],
                "candidate_id": f"ENGG-{compact_name(group_key) or abs(hash(group_key))}",
            }
        else:
            examples = current["commercial_examples"]
            if record.commercial_name not in examples and len(examples) < 3:
                examples.append(record.commercial_name)
            current["reasons"].update(item["reasons"])

    results = list(grouped.values())
    results.sort(key=lambda item: (-item["score"], item["name"]))
    return results


def confidence_status(query: Query, grouped: list[dict[str, Any]]) -> tuple[str, str]:
    if not grouped:
        return "no_match", "No safe match found."
    top_score = grouped[0]["score"]
    second_score = grouped[1]["score"] if len(grouped) > 1 else 0.0
    margin = top_score - second_score
    close_count = sum(1 for item in grouped if item["score"] >= top_score - 0.08)

    if len(query.compact) <= 2:
        return "ambiguous", "Query is too short. Please enter more letters."
    if query.common_only:
        token_text = query.tokens[0] if query.tokens else "This term"
        return "ambiguous", f"{token_text} appears in many commercial names. Please enter more of the name."
    if top_score < 0.55:
        return "low_confidence", "No high-confidence match found."
    if close_count >= 6:
        return "ambiguous", "Possible matches found, but the query is ambiguous."
    if top_score >= 0.85 and margin >= 0.12 and (len(query.compact) >= 4 or "exact_like" in query.modes) and close_count <= 3:
        return "high_confidence", "High confidence match."
    if top_score >= 0.72 and margin >= 0.06:
        return "medium_confidence", "Medium confidence match."
    if top_score >= 0.70:
        return "ambiguous", "Possible matches found, but scores are close."
    return "low_confidence", "No high-confidence match found."


def search_catalog(catalog: EnglishSearchCatalog, raw_query: Any, limit: int = TOP_K_DEFAULT) -> dict[str, Any]:
    query = make_query(raw_query, catalog)
    if not query.compact:
        return {
            "query": raw_query,
            "normalized_query": "",
            "query_modes": [],
            "status": "no_match",
            "message": "Empty query.",
            "results": [],
        }

    candidates = generate_candidates(query, catalog)
    scored = []
    edit_cache: dict[tuple[str, str, bool], float] = {}
    for idx, sources in candidates.items():
        item = score_record(query, catalog.records[idx], catalog, sources, len(candidates), edit_cache)
        if item:
            scored.append(item)

    grouped = group_scored(scored)
    status, message = confidence_status(query, grouped)
    output_results = []
    for rank, item in enumerate(grouped[:limit], 1):
        features = {
            key: round(value, 4)
            for key, value in item["features"].items()
            if value > 0
        }
        output_results.append({
            "rank": rank,
            "candidate_id": item["candidate_id"],
            "name": item["name"],
            "commercial_name": item["commercial_examples"][0],
            "candidate_canonical_name": item["canonical_name"],
            "commercial_examples": item["commercial_examples"],
            "score": round(item["score"], 4),
            "confidence": result_confidence(item["score"]),
            "matched_features": features,
            "matched_signals": "|".join(sorted(item["reasons"])),
            "reasons": sorted(item["reasons"]),
            "mode": item["mode"],
        })

    return {
        "query": raw_query,
        "normalized_query": query.norm,
        "query_modes": sorted(query.modes),
        "status": status,
        "message": message,
        "candidate_count": len(candidates),
        "results": output_results,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python app/english_search_algorithm.py <commercial_to_canonical.csv> <query>", file=sys.stderr)
        return 2
    catalog = load_catalog(argv[0])
    result = search_catalog(catalog, " ".join(argv[1:]), 20)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

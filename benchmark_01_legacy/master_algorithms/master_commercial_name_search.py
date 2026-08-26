#!/usr/bin/env python3
"""Master commercial-name search built from current-app and external signals.

Problem: combine the safer current-app search with the stronger typo retrieval
from the external English fast algorithm, producing a single commercial-name
ranking that improves recall without allowing unsafe confident top-1 answers.
Inputs:
    - app/data/catalog.json through evaluation.evaluate_current_app_search.
    - benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py.
    - Raw user query text.
Outputs:
    - A search response with status, message, candidate count, and ranked
      commercial-family results.
Edge cases:
    - Very short prefixes can match many unrelated ingredients.
    - External-only typo recoveries may be useful retrieval candidates but are
      not safe enough for automatic confident dispensing.
    - Strength/form/route context should not be discarded, because current-app
      analysis showed it outperforms the external algorithm on noisy context.
    - Duplicate products belonging to the same commercial family should not
      crowd out other candidate families in the top-20 retrieval window.
Failure modes:
    - Missing external algorithm files raise explicit exceptions.
    - Empty catalog state raises explicit exceptions rather than returning an
      empty result set silently.
    - Unknown result shapes from either child algorithm are converted to
      strings defensively but never swallowed as hidden success.
Algorithm choice:
    - We use weighted reciprocal-rank fusion over family-level candidates from
      both algorithms. A learned model was considered, but this project does
      not yet have held-out human labels separate from generated cases. Rank
      fusion is transparent, deterministic, and uses the observed strengths:
      external receives more weight for typo-like name queries, current receives
      more weight for short/noisy/contextual queries, and current clarification
      signals are preserved as the safety gate. External-only candidates can
      rank highly, but they are marked ambiguous unless independently supported
      by current-app evidence.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
EVALUATION_DIR = ROOT / "benchmark_01_legacy"
if str(EVALUATION_DIR) not in sys.path:
    sys.path.insert(0, str(EVALUATION_DIR))

import evaluate_current_app_search as current_eval


EXTERNAL_ALGORITHM_PATH = EVALUATION_DIR / "external_algorithms" / "english_search_algorithm_fast.py"

# The child algorithms can return many near-duplicate product rows. We request
# more than the public top-20 so fusion can recover external-only typo matches
# while still producing a deduplicated top-20 family ranking.
INTERNAL_CHILD_LIMIT = 40

# RRF is intentionally small-k. The v2 analysis showed each child algorithm has
# categories where ranks 1-10 contain unique value, so a small constant keeps
# high-ranked evidence influential while still allowing late rescue candidates.
RRF_K = 8.0

# External had higher v2 recall on typo-heavy categories. This default gives it
# more retrieval influence while downstream confidence still remains gated by
# current-app safety evidence.
DEFAULT_EXTERNAL_RANK_WEIGHT = 1.22
DEFAULT_CURRENT_RANK_WEIGHT = 1.00

# Current app was stronger on noisy strength/form queries and keyboard-shift
# cases. Context tokens are not reliable typo evidence, so current receives more
# weight when the query contains numbers/routes or many tokens.
CONTEXT_CURRENT_RANK_WEIGHT = 1.45
CONTEXT_EXTERNAL_RANK_WEIGHT = 0.78

# Very short prefixes are medically dangerous: one or two letters can represent
# many unrelated commercial families. Current-app prefix-risk logic is better
# suited for these than the external typo ranker.
SHORT_QUERY_CURRENT_RANK_WEIGHT = 1.60
SHORT_QUERY_EXTERNAL_RANK_WEIGHT = 0.55

# Agreement between independent algorithms is strong evidence only when both
# algorithms rank the same family highly. The first v2 full run showed that a
# weak current rank-1 candidate appearing at external rank 5+ should not outrank
# the external rank-1 typo recovery, so agreement is rank-sensitive.
STRONG_AGREEMENT_BONUS = 0.16
WEAK_AGREEMENT_BONUS = 0.035
CURRENT_EXACT_BONUS = 0.18
EXTERNAL_EXACT_BONUS = 0.12
CONTEXT_CURRENT_BONUS = 0.08

# On clean commercial-name typo queries, external rank-1 was often the best
# recovery signal in v2 while current rank-1 was a phonetic false positive. This
# bonus lets external top-1 lead retrieval, but the safety status remains
# ambiguous unless current-app evidence independently supports confidence.
TYPO_EXTERNAL_TOP1_BONUS = 0.22
TYPO_EXTERNAL_TOP2_BONUS = 0.09

# Whole-word keyboard shifts were the clearest current-app-only win in v2. We
# only apply this when external itself is not confident, avoiding a broad boost
# that would damage ordinary one-key typo categories where external is stronger.
CURRENT_KEYBOARD_TOP_BONUS_WHEN_EXTERNAL_UNSURE = 0.34

# Confidence thresholds are deliberately conservative because this is a medical
# search surface. Retrieval can be broad, but automatic confident top-1 answers
# require either exact current-app evidence or agreement without clarification.
HIGH_CONFIDENCE_SCORE = 0.26
MEDIUM_CONFIDENCE_SCORE = 0.20
HIGH_CONFIDENCE_MARGIN = 0.055
MEDIUM_CONFIDENCE_MARGIN = 0.030

CONFIDENT_EXTERNAL_STATUSES = {"high_confidence", "medium_confidence"}


@dataclass
class MasterCatalog:
    """Prepared state shared by all master search calls."""

    current_index: current_eval.SearchIndex
    external_module: ModuleType
    external_catalog: Any


@dataclass
class FusionCandidate:
    """Family-level candidate assembled from current and external child ranks."""

    key: str
    name: str
    commercial_name: str
    current_rank: int | None = None
    external_rank: int | None = None
    current_score: float = 0.0
    external_score: float = 0.0
    current_needs_clarification: bool = True
    current_signals: set[str] = field(default_factory=set)
    external_status: str = ""
    external_reasons: set[str] = field(default_factory=set)
    examples: list[str] = field(default_factory=list)
    master_score: float = 0.0
    needs_clarification: bool = True


def prepare_catalog() -> MasterCatalog:
    """Build the current-app index and external catalog used by master search."""

    records = current_eval.prepare_records()
    if not records:
        raise ValueError("current app catalog produced zero records")
    current_index = current_eval.SearchIndex(records)
    external_module = load_external_module(EXTERNAL_ALGORITHM_PATH)
    external_catalog = external_module.prepare_catalog(build_external_rows(records))
    return MasterCatalog(
        current_index=current_index,
        external_module=external_module,
        external_catalog=external_catalog,
    )


def load_external_module(path: Path) -> ModuleType:
    """Load the external algorithm snapshot from an explicit filesystem path."""

    if not path.exists():
        raise FileNotFoundError(f"external algorithm not found: {path}")
    spec = importlib.util.spec_from_file_location("master_external_english_fast", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import external algorithm from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_external_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Adapt current-app records into the external algorithm catalog schema."""

    rows: list[dict[str, str]] = []
    for record in records:
        commercial_name = str(record.get("n") or "").strip()
        if not commercial_name:
            continue
        canonical_name = str(record.get("b") or commercial_name).strip()
        rows.append({"commercial_name": commercial_name, "canonical_name": canonical_name})
    if not rows:
        raise ValueError("external adapter produced zero catalog rows")
    return rows


def search_catalog(catalog: MasterCatalog, raw_query: Any, limit: int = 20) -> dict[str, Any]:
    """Search with both child algorithms and return one fused master ranking."""

    query_text = "" if raw_query is None else str(raw_query)
    query = current_eval.make_query(query_text)
    if not query.compact:
        return {
            "query": raw_query,
            "normalized_query": "",
            "status": "no_match",
            "message": "Empty query.",
            "candidate_count": 0,
            "results": [],
        }

    current_results, current_pool = current_eval.search(catalog.current_index, query_text, INTERNAL_CHILD_LIMIT)
    external_response = catalog.external_module.search_catalog(
        catalog.external_catalog,
        query_text,
        INTERNAL_CHILD_LIMIT,
    )
    external_results = list(external_response.get("results") or [])
    external_status = str(external_response.get("status") or "")

    candidates = collect_candidates(current_results, external_results, external_status)
    if not candidates:
        return {
            "query": raw_query,
            "normalized_query": query.norm,
            "status": "no_match",
            "message": "No candidate produced by either child algorithm.",
            "candidate_count": current_pool + int(external_response.get("candidate_count") or len(external_results)),
            "results": [],
        }

    weights = rank_weights(query, external_status, bool(current_results), bool(external_results))
    for candidate in candidates.values():
        candidate.master_score = fused_score(candidate, query, weights, external_status)
        candidate.needs_clarification = candidate_needs_clarification(candidate, query)

    ranked = sorted(candidates.values(), key=lambda item: (-item.master_score, best_rank(item), item.name))
    status, message = response_status(ranked, query)
    output_results = [candidate_to_result(candidate, rank) for rank, candidate in enumerate(ranked[:limit], 1)]

    return {
        "query": raw_query,
        "normalized_query": query.norm,
        "status": status,
        "message": message,
        "candidate_count": len(candidates),
        "child_candidate_count": current_pool + int(external_response.get("candidate_count") or len(external_results)),
        "results": output_results,
    }


def collect_candidates(
    current_results: list[dict[str, Any]],
    external_results: list[dict[str, Any]],
    external_status: str,
) -> dict[str, FusionCandidate]:
    """Merge current and external child outputs into family-level candidates."""

    candidates: dict[str, FusionCandidate] = {}
    for rank, item in enumerate(current_results, 1):
        record = item["record"]
        name = str(record.get("b") or record.get("n") or "").strip()
        commercial_name = str(record.get("n") or name).strip()
        key = candidate_key(name)
        if not key:
            continue
        candidate = candidates.setdefault(
            key,
            FusionCandidate(key=key, name=name, commercial_name=commercial_name, examples=[commercial_name]),
        )
        if candidate.current_rank is None or rank < candidate.current_rank:
            candidate.current_rank = rank
            candidate.current_score = float(item.get("score") or 0.0)
            candidate.current_needs_clarification = bool(item.get("needs_clarification"))
            candidate.current_signals = set(item.get("signals") or set())
            candidate.name = name or candidate.name
            candidate.commercial_name = commercial_name or candidate.commercial_name
        add_example(candidate, commercial_name)

    for rank, item in enumerate(external_results, 1):
        name = str(item.get("name") or item.get("candidate_canonical_name") or item.get("commercial_name") or "").strip()
        commercial_name = str(item.get("commercial_name") or name).strip()
        key = candidate_key(name)
        if not key:
            continue
        candidate = candidates.setdefault(
            key,
            FusionCandidate(key=key, name=name, commercial_name=commercial_name, examples=[commercial_name]),
        )
        if candidate.external_rank is None or rank < candidate.external_rank:
            candidate.external_rank = rank
            candidate.external_score = float(item.get("score") or 0.0)
            candidate.external_status = external_status
            candidate.external_reasons = normalize_reason_set(item)
            if not candidate.name:
                candidate.name = name
            if not candidate.commercial_name:
                candidate.commercial_name = commercial_name
        for example in item.get("commercial_examples", []) or []:
            add_example(candidate, str(example))
        add_example(candidate, commercial_name)
    return candidates


def rank_weights(
    query: current_eval.Query,
    external_status: str,
    has_current_results: bool,
    has_external_results: bool,
) -> tuple[float, float]:
    """Choose current/external rank weights from observable query shape."""

    if len(query.compact) <= 4 and not query.numbers:
        current_weight = SHORT_QUERY_CURRENT_RANK_WEIGHT
        external_weight = SHORT_QUERY_EXTERNAL_RANK_WEIGHT
    elif query.numbers or query.routes or len(query.tokens) > 3:
        current_weight = CONTEXT_CURRENT_RANK_WEIGHT
        external_weight = CONTEXT_EXTERNAL_RANK_WEIGHT
    else:
        current_weight = DEFAULT_CURRENT_RANK_WEIGHT
        external_weight = DEFAULT_EXTERNAL_RANK_WEIGHT

    if external_status not in CONFIDENT_EXTERNAL_STATUSES:
        external_weight *= 0.78
    if not has_current_results and has_external_results:
        external_weight *= 1.22
    if has_current_results and not has_external_results:
        current_weight *= 1.12
    return current_weight, external_weight


def fused_score(
    candidate: FusionCandidate,
    query: current_eval.Query,
    weights: tuple[float, float],
    external_status: str,
) -> float:
    """Return deterministic RRF-style score for one merged candidate."""

    current_weight, external_weight = weights
    score = 0.0
    if candidate.current_rank is not None:
        score += current_weight / (RRF_K + candidate.current_rank)
        score += min(candidate.current_score / 1800.0, 1.0) * 0.030
    if candidate.external_rank is not None:
        score += external_weight / (RRF_K + candidate.external_rank)
        score += min(candidate.external_score, 1.0) * 0.035
    if candidate.current_rank is not None and candidate.external_rank is not None:
        score += agreement_bonus(candidate)
    if typo_like_without_context(query):
        if candidate.external_rank == 1:
            score += TYPO_EXTERNAL_TOP1_BONUS
        elif candidate.external_rank == 2:
            score += TYPO_EXTERNAL_TOP2_BONUS
    if (
        external_status not in CONFIDENT_EXTERNAL_STATUSES
        and candidate.current_rank == 1
        and "keyboard_proximity" in candidate.current_signals
        and current_eval.keyboard_proximity_ratio(query.compact, candidate.key) >= 0.95
    ):
        score += CURRENT_KEYBOARD_TOP_BONUS_WHEN_EXTERNAL_UNSURE
    if has_current_exact_signal(candidate):
        score += CURRENT_EXACT_BONUS
    if has_external_exact_signal(candidate):
        score += EXTERNAL_EXACT_BONUS
    if query.numbers or query.routes or len(query.tokens) > 3:
        if candidate.current_rank is not None:
            score += CONTEXT_CURRENT_BONUS
        elif candidate.external_rank is not None:
            score -= 0.025
    return score


def candidate_needs_clarification(candidate: FusionCandidate, query: current_eval.Query) -> bool:
    """Preserve current safety gates and downgrade unsupported external rescues."""

    if candidate.current_rank is not None and candidate.current_needs_clarification:
        return True
    if len(query.compact) <= 2:
        return True
    if candidate.current_rank is None:
        return True
    if candidate.external_rank is None:
        return candidate.current_needs_clarification
    if has_current_exact_signal(candidate) and candidate.current_rank == 1:
        return False
    if candidate.current_rank <= 3 and candidate.external_rank <= 3 and not candidate.current_needs_clarification:
        return False
    return candidate.current_needs_clarification


def agreement_bonus(candidate: FusionCandidate) -> float:
    """Return rank-sensitive child agreement bonus."""

    if candidate.current_rank is None or candidate.external_rank is None:
        return 0.0
    if candidate.current_rank <= 3 and candidate.external_rank <= 3:
        return STRONG_AGREEMENT_BONUS
    return WEAK_AGREEMENT_BONUS


def typo_like_without_context(query: current_eval.Query) -> bool:
    """Return whether query shape matches a clean brand typo, not context noise."""

    return bool(
        len(query.compact) >= 5
        and len(query.tokens) <= 3
        and not query.numbers
        and not query.routes
    )


def response_status(ranked: list[FusionCandidate], query: current_eval.Query) -> tuple[str, str]:
    """Return conservative response status for the fused ranking."""

    if not ranked:
        return "no_match", "No candidate produced by either child algorithm."
    top = ranked[0]
    second_score = ranked[1].master_score if len(ranked) > 1 else 0.0
    margin = top.master_score - second_score
    close_count = sum(1 for item in ranked[:8] if item.master_score >= top.master_score - MEDIUM_CONFIDENCE_MARGIN)

    if len(query.compact) <= 2:
        return "ambiguous", "Query is too short. Please enter more letters."
    if top.needs_clarification or close_count >= 4:
        return "ambiguous", "Possible matches found, but the safe answer needs clarification."
    if top.master_score >= HIGH_CONFIDENCE_SCORE and margin >= HIGH_CONFIDENCE_MARGIN:
        return "high_confidence", "High confidence master match."
    if top.master_score >= MEDIUM_CONFIDENCE_SCORE and margin >= MEDIUM_CONFIDENCE_MARGIN:
        return "medium_confidence", "Medium confidence master match."
    return "ambiguous", "Possible matches found, but scores are close."


def candidate_to_result(candidate: FusionCandidate, rank: int) -> dict[str, Any]:
    """Convert an internal fusion candidate to the public result shape."""

    signals = set(candidate.current_signals)
    signals.update(f"external:{reason}" for reason in candidate.external_reasons)
    if candidate.current_rank is not None:
        signals.add(f"current_rank_{candidate.current_rank}")
    if candidate.external_rank is not None:
        signals.add(f"external_rank_{candidate.external_rank}")
    if candidate.current_rank is not None and candidate.external_rank is not None:
        signals.add("child_agreement")
    if candidate.needs_clarification:
        signals.add("master_requires_clarification")

    return {
        "rank": rank,
        "candidate_id": f"MASTER-{candidate.key or rank}",
        "name": candidate.name,
        "commercial_name": candidate.commercial_name or candidate.name,
        "candidate_canonical_name": candidate.name,
        "commercial_examples": candidate.examples[:5],
        "score": round(candidate.master_score, 6),
        "confidence": "low" if candidate.needs_clarification else "high",
        "needs_clarification": candidate.needs_clarification,
        "current_rank": candidate.current_rank or "",
        "external_rank": candidate.external_rank or "",
        "current_score": round(candidate.current_score, 4),
        "external_score": round(candidate.external_score, 4),
        "matched_signals": "|".join(sorted(signals)),
        "reasons": sorted(signals),
        "source": source_label(candidate),
    }


def normalize_reason_set(item: dict[str, Any]) -> set[str]:
    """Extract external reasons from either list or pipe-delimited fields."""

    reasons = set(str(value) for value in (item.get("reasons") or []) if str(value))
    matched = str(item.get("matched_signals") or "")
    reasons.update(part for part in matched.split("|") if part)
    mode = str(item.get("mode") or "")
    if mode:
        reasons.add(mode)
    return reasons


def source_label(candidate: FusionCandidate) -> str:
    """Return a compact source label for audit CSVs."""

    if candidate.current_rank is not None and candidate.external_rank is not None:
        return "current+external"
    if candidate.current_rank is not None:
        return "current"
    return "external"


def candidate_key(value: Any) -> str:
    """Return the family key used for deduplication."""

    return current_eval.compact_key(value)


def add_example(candidate: FusionCandidate, value: str) -> None:
    """Append one commercial example without duplicates or blank entries."""

    clean = value.strip()
    if clean and clean not in candidate.examples:
        candidate.examples.append(clean)


def best_rank(candidate: FusionCandidate) -> int:
    """Return the best child rank for deterministic tie-breaking."""

    ranks = [rank for rank in [candidate.current_rank, candidate.external_rank] if rank is not None]
    return min(ranks) if ranks else 999


def has_current_exact_signal(candidate: FusionCandidate) -> bool:
    """Return whether current-app evidence is exact enough for confidence."""

    return bool(
        candidate.current_signals
        & {
            "heard_spelling_alias",
            "exact_name",
            "exact_compact",
            "exact_arabic_alias",
            "exact_base_group",
        }
    )


def has_external_exact_signal(candidate: FusionCandidate) -> bool:
    """Return whether external evidence is exact-like rather than fuzzy only."""

    return bool(
        candidate.external_reasons
        & {
            "exact_mode",
            "exact_match",
            "exact_compact",
            "exact_norm",
            "approved_alias",
        }
    )

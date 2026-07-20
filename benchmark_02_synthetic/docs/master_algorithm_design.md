# Algorithm 3 Commercial-Name Search Design

## One-Sentence Problem

Build one commercial-name search algorithm that uses Algorithm 1's safer clarification behavior and Algorithm 2's stronger typo retrieval, while reducing unsafe confident top-1 results to zero on the V2 benchmark.

## Algorithm Names

| label | implementation |
| --- | --- |
| Algorithm 1 | current app evaluator |
| Algorithm 2 | external English fast algorithm |
| Algorithm 3 | master rank-fusion algorithm |

## Implementation File

The implementation is:

```text
benchmark_01_legacy/master_algorithms/master_commercial_name_search.py
```

The V2 evaluator for this algorithm is:

```text
benchmark_02_synthetic/evaluate_algorithm_3.py
```

## Why A Master Algorithm Was Needed

Algorithm 1 and Algorithm 2 had complementary behavior:

| child algorithm | measured strength | measured weakness |
| --- | --- | --- |
| Algorithm 1 | Safer clarification behavior, strength/form context handling, prefix caution, route/form context, exact and contextual queries. | Lower retrieval on many typo-heavy categories, especially visual/phonetic/multi-error cases. |
| Algorithm 2 | Stronger typo retrieval for deletion, insertion, transposition, phonetic, visual, OCR, and other corrupted commercial names. | Unsafe confident top-1 rate was too high on V2, especially safety cases. It also underperformed on some noisy context categories. |

Algorithm 3 is not a simple replacement of one child with the other. It is a conservative rank-fusion layer that lets Algorithm 2 improve retrieval while preserving safety gates from Algorithm 1.

## Inputs

### Catalog Preparation Input

| input | type | source |
| --- | --- | --- |
| current-app records | `list[dict[str, Any]]` | `evaluation.evaluate_current_app_search.prepare_records()` reading app catalog data |
| external rows | `list[dict[str, str]]` | Adapted from current-app records into `commercial_name, canonical_name` rows |
| external algorithm module | Python module | `benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py` |

### Search Input

| input | type | allowed values |
| --- | --- | --- |
| `raw_query` | `Any` | Usually string, but non-string values are converted to string defensively. `None` becomes an empty query. |
| `limit` | `int` | Number of fused results returned to the caller. Default is 20. |

## Outputs

`search_catalog()` returns a dictionary shaped for evaluation and debugging:

| field | type | meaning |
| --- | --- | --- |
| `query` | original value | Original raw input. |
| `normalized_query` | string | Current-app normalized query text. |
| `status` | string | `high_confidence`, `medium_confidence`, `ambiguous`, or `no_match`. |
| `message` | string | Human-readable status explanation. |
| `candidate_count` | integer | Number of fused family-level candidates. |
| `child_candidate_count` | integer | Approximate total candidates seen from both child algorithms. |
| `results` | list of dictionaries | Ranked family-level results. |

Each result includes:

| field | type | meaning |
| --- | --- | --- |
| `rank` | integer | Master rank after fusion. |
| `candidate_id` | string | Synthetic `MASTER-...` id. |
| `name` | string | Commercial family/base-group name. |
| `commercial_name` | string | Representative product/commercial name. |
| `candidate_canonical_name` | string | Same family-level canonical name used by evaluators. |
| `commercial_examples` | list[str] | Up to five product examples for the family. |
| `score` | float | Rounded master fusion score. |
| `confidence` | string | `high` only when the result is not marked for clarification; otherwise `low`. |
| `needs_clarification` | bool | Whether the master considers this candidate unsafe for confident top-1 use. |
| `current_rank` | integer or empty | Rank from current app child, if present. |
| `external_rank` | integer or empty | Rank from external child, if present. |
| `current_score` | float | Current child score. |
| `external_score` | float | External child score. |
| `matched_signals` | pipe-delimited string | Current and external signals used for audit. |
| `reasons` | list[str] | Same audit signals as a list. |
| `source` | string | `current`, `external`, or `current+external`. |

## Core Data Structures

### `MasterCatalog`

`MasterCatalog` is prepared once and reused for search calls.

| field | type | purpose |
| --- | --- | --- |
| `current_index` | `current_eval.SearchIndex` | Current app search index. |
| `external_module` | `ModuleType` | Loaded external algorithm module. |
| `external_catalog` | external-specific catalog object | Prepared external catalog state. |

### `FusionCandidate`

`FusionCandidate` represents one commercial family after merging child results.

| field | type | purpose |
| --- | --- | --- |
| `key` | string | Compact family key used for deduplication. |
| `name` | string | Family/base-group name. |
| `commercial_name` | string | Representative product name. |
| `current_rank` | `int | None` | Best rank from current app child. |
| `external_rank` | `int | None` | Best rank from external child. |
| `current_score` | float | Score from current app child. |
| `external_score` | float | Score from external child. |
| `current_needs_clarification` | bool | Current app safety flag. |
| `current_signals` | `set[str]` | Current app match signals. |
| `external_status` | string | External response status. |
| `external_reasons` | `set[str]` | External algorithm match reasons. |
| `examples` | `list[str]` | Commercial examples for display/audit. |
| `master_score` | float | Final fused score. |
| `needs_clarification` | bool | Final master clarification flag. |

The master fuses by family/base group, not by product row. This avoids one family crowding the top 20 with many package variants.

## Algorithm Flow

1. `prepare_catalog()` builds the current app search index.
2. It loads `benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py` by explicit path.
3. It adapts current-app records into external rows with `commercial_name` and `canonical_name`.
4. `search_catalog()` converts the raw query to a current-app `Query`.
5. If the compact query is empty, it returns `no_match` immediately.
6. It runs current-app search with `INTERNAL_CHILD_LIMIT = 40`.
7. It runs external search with the same internal limit.
8. `collect_candidates()` merges both result lists into one dictionary keyed by compact family name.
9. `rank_weights()` chooses current/external weights from observable query shape.
10. `fused_score()` computes the rank-fusion score for every candidate.
11. `candidate_needs_clarification()` applies safety/clarification logic.
12. Candidates are sorted by descending master score, then best child rank, then family name.
13. `response_status()` decides whether the response is confident, ambiguous, or no-match.
14. `candidate_to_result()` converts internal candidates to public result dictionaries.

## Scoring Model

The master uses weighted reciprocal-rank fusion with bonuses and safety-aware confidence gates.

Base rank-fusion contribution:

```text
current contribution  = current_weight  / (RRF_K + current_rank)
external contribution = external_weight / (RRF_K + external_rank)
```

Small score-normalization additions are added from child scores:

```text
current score addition  = min(current_score / 1800.0, 1.0) * 0.030
external score addition = min(external_score, 1.0) * 0.035
```

The constants are named in code rather than magic numbers.

## Scoring Constants

| constant | value | why it exists |
| --- | ---: | --- |
| `INTERNAL_CHILD_LIMIT` | 40 | Pulls more than public top 20 from each child so fusion can recover useful candidates before deduplication. |
| `RRF_K` | 8.0 | Small enough to reward high ranks, large enough that rank 2-10 still matter. |
| `DEFAULT_EXTERNAL_RANK_WEIGHT` | 1.22 | External had stronger typo retrieval on V2. |
| `DEFAULT_CURRENT_RANK_WEIGHT` | 1.00 | Current remains a baseline signal. |
| `CONTEXT_CURRENT_RANK_WEIGHT` | 1.45 | Current app was stronger when queries included numbers, routes, or many context tokens. |
| `CONTEXT_EXTERNAL_RANK_WEIGHT` | 0.78 | External typo retrieval should not dominate noisy context queries. |
| `SHORT_QUERY_CURRENT_RANK_WEIGHT` | 1.60 | Short prefixes are dangerous and should lean on current prefix-risk behavior. |
| `SHORT_QUERY_EXTERNAL_RANK_WEIGHT` | 0.55 | External fuzzy matches are risky for very short prefixes. |
| `STRONG_AGREEMENT_BONUS` | 0.16 | Both children ranking the same family in top 3 is strong evidence. |
| `WEAK_AGREEMENT_BONUS` | 0.035 | Late agreement is useful but should not override a strong child top-1. |
| `CURRENT_EXACT_BONUS` | 0.18 | Current exact signals are reliable confidence evidence. |
| `EXTERNAL_EXACT_BONUS` | 0.12 | External exact signals are useful, but current safety remains stronger. |
| `CONTEXT_CURRENT_BONUS` | 0.08 | Extra support for current in strength/form/context queries. |
| `TYPO_EXTERNAL_TOP1_BONUS` | 0.22 | External top-1 often recovered clean typo-like brand queries better. |
| `TYPO_EXTERNAL_TOP2_BONUS` | 0.09 | External rank 2 can still be useful without overwhelming rank 1. |
| `CURRENT_KEYBOARD_TOP_BONUS_WHEN_EXTERNAL_UNSURE` | 0.34 | Current was much stronger on whole-word keyboard shift when external was unsure. |
| `HIGH_CONFIDENCE_SCORE` | 0.26 | Conservative confidence score threshold. |
| `MEDIUM_CONFIDENCE_SCORE` | 0.20 | Conservative medium confidence threshold. |
| `HIGH_CONFIDENCE_MARGIN` | 0.055 | Required gap from rank 2 for high confidence. |
| `MEDIUM_CONFIDENCE_MARGIN` | 0.030 | Required gap from rank 2 for medium confidence. |

## Rank Weight Decisions

`rank_weights()` chooses weights from the query shape:

| query shape | current weight | external weight | reasoning |
| --- | ---: | ---: | --- |
| Compact length <= 4 and no numbers | 1.60 | 0.55 | Short prefixes collide with many unrelated families; conservative Algorithm 1 behavior is safer. |
| Query has numbers, routes, or more than 3 tokens | 1.45 | 0.78 | Context-heavy input is closer to current app strengths. |
| Ordinary brand-like typo | 1.00 | 1.22 | External typo retrieval is stronger on V2. |
| External status is not confident | external weight multiplied by 0.78 | n/a | External uncertainty should reduce ranking influence. |
| Only external has results | external weight multiplied by 1.22 | n/a | External-only recovery can still rescue retrieval. |
| Only current has results | current weight multiplied by 1.12 | n/a | Current-only evidence should not be discarded. |

## Safety And Clarification Logic

The master separates retrieval from confidence. A candidate can rank highly and still require clarification.

`candidate_needs_clarification()` marks candidates as requiring clarification when:

1. Current app already marked the candidate as requiring clarification.
2. The query compact length is 2 or less.
3. The candidate exists only in external results.
4. The candidate lacks high-rank agreement and lacks exact current support.

It allows no-clarification only when:

1. Current exact evidence ranks first, or
2. Both children rank the same candidate in the top 3 and current did not request clarification.

This is the key safety decision. The master can use external-only candidates for recall, but it does not automatically treat them as safe confident top-1 answers.

## Response Status Logic

`response_status()` uses the ranked list and top-score margin:

| condition | status |
| --- | --- |
| No candidates | `no_match` |
| Query compact length <= 2 | `ambiguous` |
| Top candidate needs clarification | `ambiguous` |
| Four or more top-8 candidates are within `MEDIUM_CONFIDENCE_MARGIN` of top score | `ambiguous` |
| Top score >= `HIGH_CONFIDENCE_SCORE` and margin >= `HIGH_CONFIDENCE_MARGIN` | `high_confidence` |
| Top score >= `MEDIUM_CONFIDENCE_SCORE` and margin >= `MEDIUM_CONFIDENCE_MARGIN` | `medium_confidence` |
| Otherwise | `ambiguous` |

This status system is deliberately conservative. In medical search, broad candidate retrieval is acceptable; confident wrong top-1 is not.

## Alternatives Considered

| alternative | rejected because |
| --- | --- |
| Use only the current app algorithm | It preserved safety but left too much typo retrieval performance on the table. |
| Use only the external algorithm | It improved typo retrieval but had a high unsafe confident top-1 rate on V2. |
| Pick current or external by category | Real production queries do not arrive with dataset category labels. That would overfit evaluation data and fail in the app. |
| Train a learned ranker | There is no independent human-labeled held-out set yet. Training on generated labels would risk overfitting the generator. |
| Merge raw product rows directly | Package variants from one family can crowd the result list and hide distinct candidate families. |
| Weighted reciprocal-rank fusion by family | Chosen because it is deterministic, transparent, debuggable, and aligned with observed child strengths. |

## Failure Modes And Consequences

| failure mode | code behavior | consequence avoided |
| --- | --- | --- |
| Algorithm 2 file missing | Raises `FileNotFoundError`. | Avoids silently running Algorithm 1 only while claiming Algorithm 3 behavior. |
| External algorithm cannot be imported | Raises `ImportError`. | Avoids partial evaluation. |
| Current app catalog produces zero records | Raises `ValueError`. | Avoids returning empty results for all queries. |
| External row adapter produces zero rows | Raises `ValueError`. | Avoids external child being silently disabled. |
| Empty query | Returns explicit `no_match`. | Avoids arbitrary catalog matches. |
| No child candidates | Returns explicit `no_match`. | Avoids pretending an empty candidate list is success. |
| External-only candidate appears strong | Can rank high, but clarification stays required. | Avoids unsafe confident top-1. |
| Short ambiguous prefix | Forces ambiguous response. | Avoids unsafe prefix overconfidence. |

## Final V2 Result

Full report:

```text
benchmark_02_synthetic/results/01_full_benchmark/algorithm_1_3_comparison.md
```

Headline over 115,000 generated V2 cases:

| metric | Algorithm 1 | Algorithm 2 | Algorithm 3 |
| --- | ---: | ---: | ---: |
| Hit@1 | 75.26% | 79.30% | 81.03% |
| Hit@20 | 88.40% | 91.84% | 93.09% |
| Behavior success | 88.66% | 91.29% | 93.33% |
| Unsafe confident top-1 | 0.02% | 6.40% | 0.00% |

Algorithm 3 beats both child algorithms overall on Hit@1, Hit@20, and behavior success while reducing unsafe confident top-1 to zero on V2. It does not beat the best child in every individual category or scope. That is documented in the full comparison report rather than hidden.

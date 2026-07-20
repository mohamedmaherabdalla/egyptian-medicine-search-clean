# Master Commercial-Name Search

`master_commercial_name_search.py` combines the two measured search approaches:

| child | measured strength used by master |
| --- | --- |
| current app evaluator | Safety gates, clarification behavior, strength/form context, keyboard-shift recovery, exact and prefix handling. |
| external English fast algorithm | Stronger retrieval on typo-heavy commercial-name queries, visual/phonetic corruption, deletion/insertion/transposition, and multi-error cases. |

## Design

The master algorithm is a family-level rank-fusion engine:

1. Run the current app search and the external English fast search.
2. Deduplicate candidates by commercial family/base group.
3. Score each family using weighted reciprocal-rank fusion.
4. Give external rank-1 extra influence only for clean typo-like brand queries.
5. Give current rank-1 extra influence for likely whole-keyboard-shift cases when external is not confident.
6. Preserve current-app clarification behavior and mark unsupported external-only rescues as ambiguous rather than confident.

This means retrieval can benefit from external typo recovery while safety remains conservative. In medical search, returning candidates with clarification is preferred over making a confident wrong top-1 call.

## Final V2 Result

Full report:

`benchmark_02_synthetic/results/01_full_benchmark/algorithm_1_3_comparison.md`

Headline on 115,000 generated v2 cases:

| metric | current | external | master |
| --- | ---: | ---: | ---: |
| Hit@1 | 75.26% | 79.30% | 81.03% |
| Hit@20 | 88.40% | 91.84% | 93.09% |
| Behavior success | 88.66% | 91.29% | 93.33% |
| Unsafe confident top-1 | 0.02% | 6.40% | 0.00% |

Coverage audit:

| check | result |
| --- | ---: |
| evaluated rows | 115,000 |
| categories covered | 34 / 34 |
| detailed error-type buckets covered | 4,243 / 4,243 |
| missing category buckets | 0 |
| missing error-type buckets | 0 |
| blank comparison context cells | 0 |

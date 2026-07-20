# Testing And Evaluation Strategy For Testing Dataset V2

## One-Sentence Problem

Evaluate Algorithm 1, Algorithm 2, and Algorithm 3 commercial-name search behavior on the full generated V2 dataset without dropping any category or detailed error-type bucket, while separating retrieval quality from medical-safety behavior.

## Algorithm Names

| label | implementation |
| --- | --- |
| Algorithm 1 | current app evaluator |
| Algorithm 2 | external English fast algorithm |
| Algorithm 3 | master rank-fusion algorithm |

## Why Retrieval Metrics Alone Are Not Enough

For ordinary search, Hit@1 or Hit@20 can be enough. For medical search, those metrics are incomplete.

Example: If a dangerous short prefix has several plausible medicines, returning one confident top-1 answer can be unsafe even if the expected family appears somewhere in the results. V2 therefore measures both:

1. Retrieval quality: did the expected family appear in top 1, 5, 10, or 20?
2. Behavior quality: did the algorithm respond in the right safety mode: confident match, clarification/ambiguous, or no confident match?

## Evaluated Algorithms

| algorithm | evaluator path | row-level output |
| --- | --- | --- |
| Algorithm 1 | `benchmark_02_synthetic/evaluate_algorithms_1_2.py` using `benchmark_01_legacy/evaluate_current_app_search.py` | `artifacts/01_full_benchmark/algorithm_1_cases.csv` |
| Algorithm 2 | `benchmark_02_synthetic/evaluate_algorithms_1_2.py` using `benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py` | `artifacts/01_full_benchmark/algorithm_2_cases.csv` |
| Algorithm 3 | `benchmark_02_synthetic/evaluate_algorithm_3.py` using `benchmark_01_legacy/master_algorithms/master_commercial_name_search.py` | `artifacts/01_full_benchmark/algorithm_3_cases.csv` |

## Commands

### Generate Dataset

```bash
PYTHONDONTWRITEBYTECODE=1 python3 'benchmark_02_synthetic/generate_dataset.py'
```

### Smoke Evaluate Algorithm 1 And Algorithm 2

```bash
PYTHONDONTWRITEBYTECODE=1 python3 'benchmark_02_synthetic/evaluate_algorithms_1_2.py' --limit 200 --workers 1 --chunk-size 50
```

### Full Evaluate Algorithm 1 And Algorithm 2

```bash
PYTHONDONTWRITEBYTECODE=1 python3 'benchmark_02_synthetic/evaluate_algorithms_1_2.py' --workers 8 --chunk-size 200
```

### Smoke Evaluate Algorithm 3

```bash
PYTHONDONTWRITEBYTECODE=1 python3 'benchmark_02_synthetic/evaluate_algorithm_3.py' --limit 200 --workers 1 --chunk-size 50
```

### Full Evaluate Algorithm 3

```bash
PYTHONDONTWRITEBYTECODE=1 python3 'benchmark_02_synthetic/evaluate_algorithm_3.py' --workers 8 --chunk-size 200
```

The committed final Algorithm 3 run evaluated 115,000 rows with 8 workers and chunk size 200 in 161.88 seconds.

## Evaluator Input Requirements

The V2 evaluators require these columns from `data/test_cases.csv`:

| column | why required |
| --- | --- |
| `input` | Query to evaluate. |
| `expected` | Expected family or sentinel. |
| `category` | Category aggregation. |
| `error_type` | Detailed bucket aggregation. |
| `difficulty` | Difficulty slicing and audit. |
| `danger` | Unsafe top-1 and clarification risk logic. |
| `scope` | Scope aggregation. |
| `expected_behavior` | Distinguishes match, ambiguous, and no-match cases. |
| `collision_with` | Helps define relevant alternatives for ambiguous rows. |
| `source_base_group` | Additional family relevance target. |
| `generator_function` | Provenance and debugging. |

Missing required columns raise explicit errors. The evaluator does not silently treat missing data as empty.

## Target Construction

For ordinary `match` rows, the relevant targets include:

1. `expected`
2. `source_base_group` when present

For ambiguous rows, the evaluator includes the collision families when available. This allows ranking metrics to measure whether plausible candidates were retrieved, while behavior metrics still require non-confident clarification.

For no-match rows, there is no ordinary commercial family target. Behavior success is based on not returning a confident drug match.

## Metrics

| metric | meaning |
| --- | --- |
| `hit_at_1` | Expected/relevant target appears at rank 1. |
| `hit_at_5` | Expected/relevant target appears within top 5. |
| `hit_at_10` | Expected/relevant target appears within top 10. |
| `hit_at_20` | Expected/relevant target appears within top 20. |
| `mrr_at_20` | Reciprocal rank of first relevant hit within top 20. |
| `map_at_20` | Mean average precision over the top 20. |
| `ndcg_at_20` | Discounted ranking quality over the top 20. |
| `no_result_rate` | Fraction of rows returning no results. |
| `unsafe_confident_top1_rate` | Fraction of rows where rank 1 is wrong and the algorithm is confident. |
| `missing_clarification_rate` | Fraction of caution/danger rows where the algorithm should have avoided confident top-1 but did not. |
| `behavior_success_rate` | Whether the algorithm satisfied the row's expected behavior, independent from pure retrieval. |
| `avg_candidate_pool` | Average size of the candidate pool reported by the algorithm. |

## Behavior Success Rules

### Match Rows

For `expected_behavior = match`, behavior succeeds when the expected family appears within top 20.

This is intentionally not limited to Hit@1 because many real medicine queries are ambiguous enough that a candidate list is safer than a forced first answer.

### Ambiguous Rows

For `expected_behavior = ambiguous`, behavior succeeds when:

1. The algorithm returns candidates, and
2. The response is non-confident or requires clarification.

A confident top-1 answer on an ambiguous row is not behavior success, even if the top result is relevant.

### No-Match Rows

For `expected_behavior = no_match`, behavior succeeds when:

1. The algorithm returns no results, or
2. The algorithm returns results but marks them non-confident/clarifying.

This permits candidate display for review, but rejects confident automatic matching.

## Unsafe Confident Top-1

Unsafe confident top-1 is one of the most important safety metrics.

The master evaluator marks `unsafe_confident_top1 = 1` when:

1. A top result exists.
2. The top result is not relevant.
3. The response status is confident.
4. The top result does not require clarification.
5. The row is not a no-match row.

The final Algorithm 3 result is 0.00% unsafe confident top-1 on V2.

## Output Files

### Algorithm 1 And Algorithm 2 Evaluation Outputs

| file | purpose |
| --- | --- |
| `artifacts/01_full_benchmark/algorithm_1_cases.csv` | One Algorithm 1 result row per dataset row. |
| `artifacts/01_full_benchmark/algorithm_2_cases.csv` | One Algorithm 2 result row per dataset row. |
| `artifacts/01_full_benchmark/source_tables/algorithm_1_metrics_by_category.csv` | Algorithm 1 source metrics. |
| `artifacts/01_full_benchmark/source_tables/algorithm_2_metrics_by_category.csv` | Algorithm 2 source metrics. |
| `artifacts/01_full_benchmark/source_tables/algorithm_1_metrics_by_error_type.csv` | Algorithm 1 detailed source metrics. |
| `artifacts/01_full_benchmark/source_tables/algorithm_2_metrics_by_error_type.csv` | Algorithm 2 detailed source metrics. |

### Algorithm 3 And Three-Way Outputs

| file | purpose |
| --- | --- |
| `artifacts/01_full_benchmark/algorithm_3_cases.csv` | One Algorithm 3 result row per dataset row. |
| `artifacts/01_full_benchmark/source_tables/algorithm_3_metrics_by_category.csv` | Algorithm 3 source metrics. |
| `artifacts/01_full_benchmark/source_tables/algorithm_3_metrics_by_error_type.csv` | Algorithm 3 detailed source metrics. |
| `results/01_full_benchmark/algorithm_1_3_comparison.md` | Clean full Markdown report with every category and every detailed error-type bucket. |
| `results/01_full_benchmark/algorithm_1_3_comparison_by_category.csv` | Clean category-level Algorithm 1/2/3 comparison. |
| `results/01_full_benchmark/algorithm_1_3_comparison_by_error_type.csv` | Clean detailed Algorithm 1/2/3 comparison for all 4,243 buckets. |
| `results/01_full_benchmark/metrics_by_category.csv` | Canonical Algorithms 1-4 category metrics. |
| `results/01_full_benchmark/metrics_by_error_type.csv` | Canonical Algorithms 1-4 detailed metrics. |
| `results/01_full_benchmark/failure_samples.csv` | Consolidated failure samples with algorithm identity. |
| `results/01_full_benchmark/summary.json` | Compact consolidated run metadata. |
| `results/01_full_benchmark/failure_analysis.md` | Full failed-case root-cause analysis across the previous full V2 run plus manually supplied failed cases. |
| `results/02_manual_cases/algorithm_1_3_results.csv` | Row-level results for the 50 manually supplied failed cases. |

## No-Skipping Coverage Contract

The report generation code enforces complete joins.

| coverage requirement | enforcement |
| --- | --- |
| Every category in dataset appears in metric output. | `three_way_comparison_rows()` raises if Algorithm 1, Algorithm 2, or Algorithm 3 keys differ. |
| Every detailed error-type bucket appears in metric output. | Same key-mismatch check over `(scope, category, error_type)`. |
| Every category row has an example and description. | `enrich_category_rows()` raises on missing or blank context. |
| Every error-type row has an example and description. | `enrich_error_rows()` raises on missing or blank context. |
| Markdown category table includes all categories. | Audited against dataset category buckets. |
| Markdown error-type table includes all detailed buckets. | Audited against 4,243 dataset buckets. |

Final audit result:

| check | result |
| --- | ---: |
| dataset rows | 115,000 |
| Algorithm 3 result rows | 115,000 |
| categories in dataset | 34 |
| categories in Algorithm 3 metrics | 34 |
| missing category buckets | 0 |
| detailed error-type buckets in dataset | 4,243 |
| detailed error-type buckets in Algorithm 3 metrics | 4,243 |
| missing error-type buckets | 0 |
| Markdown category rows | 34 |
| Markdown error-type rows | 4,243 |
| blank category context cells | 0 |
| blank error context cells | 0 |

## Headline Scores

| scope | cases | Algorithm 1 Hit@1 | Algorithm 2 Hit@1 | Algorithm 3 Hit@1 | Algorithm 1 Hit@20 | Algorithm 2 Hit@20 | Algorithm 3 Hit@20 | Algorithm 1 behavior | Algorithm 2 behavior | Algorithm 3 behavior | Algorithm 1 unsafe | Algorithm 2 unsafe | Algorithm 3 unsafe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `inside` | 87,000 | 73.40% | 81.02% | 80.52% | 87.02% | 92.00% | 92.41% | 87.02% | 92.00% | 92.41% | 0.00% | 5.64% | 0.00% |
| `safety` | 18,000 | 74.09% | 72.66% | 76.28% | 89.86% | 92.50% | 93.67% | 91.45% | 90.04% | 95.12% | 0.00% | 13.42% | 0.00% |
| `semi_outside` | 4,000 | 92.58% | 78.92% | 94.15% | 96.97% | 87.70% | 97.32% | 96.97% | 87.70% | 97.32% | 0.47% | 0.00% | 0.00% |
| `smoke` | 6,000 | 94.07% | 74.58% | 94.05% | 98.38% | 90.25% | 98.47% | 98.53% | 87.05% | 98.53% | 0.00% | 0.53% | 0.00% |
| `all` | 115,000 | 75.26% | 79.30% | 81.03% | 88.40% | 91.84% | 93.09% | 88.66% | 91.29% | 93.33% | 0.02% | 6.40% | 0.00% |

## Important Interpretation Notes

1. Algorithm 3 beats both children overall on Hit@1, Hit@20, and behavior success.
2. Algorithm 3 reaches 0.00% unsafe confident top-1 on V2.
3. Algorithm 3 does not beat the best child in every individual scope/category. The full report shows those cases explicitly.
4. MAP and NDCG can be lower than Algorithm 1 in some scopes because Algorithm 1 often returns very large candidate pools and because ambiguous/no-match rows use different relevance semantics. Hit@20, behavior success, and unsafe top-1 are more important for the medical-safety question.
5. Exact-match smoke cases are intentionally small relative to hard categories, so the overall score reflects difficult and dangerous search behavior.

## Manual Representative Inputs

The final testing included full automated evaluation plus representative behavior checks through the generated row-level outputs. These examples illustrate the expected behaviors:

| case type | example source | expected behavior |
| --- | --- | --- |
| Exact brand | `exact_match_baseline` | Confident correct match should appear at rank 1. |
| Noisy exact plus strength | `exact_match_with_strength` | Brand should still be recovered despite strength tokens. |
| Dangerous edit-distance pair | `dangerous_ed1_pairs` | Candidate retrieval is useful, but confident wrong top-1 is unsafe. |
| Prefix ambiguity | `prefix_ambiguity_awareness` | Candidates may appear, but clarification/non-confidence is required. |
| No-match negative | `negative_no_match_expected` | No confident medicine match should be returned. |
| Heavy typo | `four_plus_error_combinations` | Top-20 retrieval matters more than overconfident top-1. |

## Verification Commands Used

### Python Compile Check

```bash
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile benchmark_01_legacy/master_algorithms/master_commercial_name_search.py 'benchmark_02_synthetic/evaluate_algorithm_3.py'
```

### Final Master Evaluation

```bash
PYTHONDONTWRITEBYTECODE=1 python3 'benchmark_02_synthetic/evaluate_algorithm_3.py' --workers 8 --chunk-size 200
```

### Coverage Audit

The final audit compared:

1. `data/test_cases.csv`
2. `artifacts/01_full_benchmark/algorithm_3_cases.csv`
3. `results/01_full_benchmark/metrics_by_category.csv`
4. `results/01_full_benchmark/metrics_by_error_type.csv`
5. `results/01_full_benchmark/algorithm_1_3_comparison.md`
6. `results/01_full_benchmark/algorithm_1_3_comparison_by_category.csv`
7. `results/01_full_benchmark/algorithm_1_3_comparison_by_error_type.csv`

The audit confirmed complete category and detailed-bucket coverage with no blank example/description cells.

## Residual Risk

This is still a generated benchmark. It is strong for repeatable regression testing, but it is not a substitute for real production query logs, pharmacist review, or a held-out human-labeled safety set.

The most important next validation step would be a separately labeled real-query sample where the labels are not generated by the same rules as the benchmark.

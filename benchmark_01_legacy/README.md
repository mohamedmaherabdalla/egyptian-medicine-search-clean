# Legacy Commercial-Name Benchmark

This benchmark owns the original 341,901 generated commercial-name cases,
Algorithms 1 and 2 evaluations, and their comparison. Shared metric semantics
and retrospective comparison rules live in [`../docs/evaluation.md`](../docs/evaluation.md).

## Directory Contract

| Path | Purpose |
| --- | --- |
| `data/` | Generated inputs and generation audits. |
| `results/01_current_app/` | Algorithm 1 aggregate results. |
| `results/02_external_fast/` | Algorithm 2 aggregate results. |
| `results/03_comparison/` | Paired Algorithms 1 and 2 comparison. |
| `artifacts/` | Row-level outputs; ignored by Git. |
| `test_case_generation/` | Deterministic generation modules and tests. |

Detailed benchmark documents:

- [`docs/benchmark_summary.md`](docs/benchmark_summary.md)
- [`docs/data_description.md`](docs/data_description.md)
- [`docs/generation_design.md`](docs/generation_design.md)
- [`docs/testing_strategy.md`](docs/testing_strategy.md)

## Evaluation Goal

The goal is to test whether the search system retrieves the correct medicine, family, or ingredient target under realistic query conditions. The system is evaluated as ranked retrieval, not as a single yes/no classifier.

## Evaluation Groups

| group | what it tests |
| --- | --- |
| Exact product search | A clean product name should return the exact product at the top. |
| Compact product search | Missing punctuation or spaces should still retrieve the right product. |
| Prefix search | Short typed prefixes should retrieve candidate sets without acting overconfident. |
| Typo search | Small edit-distance mistakes should still retrieve the intended product or family. |
| Heard-spelling search | Names written by sound should retrieve the intended brand family when possible. |
| Base-family search | Brand-only queries should retrieve variants under the correct family. |
| Ingredient search | Generic or active-ingredient queries should retrieve matching products. |
| Route/form search | Form hints should improve ranking for tablet, syrup, injection, topical, and similar forms. |
| Strength search | Strength hints should boost matching product variants. |
| Warning behavior | Rows with known data-quality issues should surface visible warnings. |
| Ambiguity behavior | Ambiguous queries should require confirmation instead of forcing one product. |
| Negative/OOV behavior | Unknown or unsafe queries should avoid confident false matches. |

## Relevance Levels

| level | meaning |
| --- | --- |
| Exact product | The returned candidate is the expected product row. |
| Brand family | The returned candidate belongs to the expected brand/base family. |
| Ingredient family | The returned candidate has the expected ingredient/composition family. |
| Irrelevant | The returned candidate does not match the expected target. |

## Ranking Metrics

The evaluation checks whether relevant results appear near the top of the ranked list:

- `Hit@1`: relevant result appears at rank 1.
- `Hit@5`: relevant result appears in the first 5 results.
- `Hit@10`: relevant result appears in the first 10 results.
- `Hit@20`: relevant result appears in the first 20 results.
- `MRR@20`: rewards the first relevant result appearing earlier.
- `MAP@20`: rewards multiple relevant results appearing early.
- `nDCG@20`: rewards stronger relevance levels higher in the ranking.

## Safety Checks

The evaluation also checks behavior that matters specifically for medicine lookup:

- weak fuzzy matches should not look like exact matches
- broad prefixes should not produce confident single-result behavior
- ambiguous brand families should require confirmation
- required warnings should be visible
- negative queries should not produce confident false positives

## Output Files

The committed evaluation artifacts are:

- `benchmark_01_legacy/data/test_cases.csv`: full generated test suite.
- `benchmark_01_legacy/data/test_cases_inside.csv`: inside-scope split.
- `benchmark_01_legacy/data/test_cases_semi_outside.csv`: semi-outside split.
- `benchmark_01_legacy/data/test_cases_outside.csv`: outside-scope split.
- `benchmark_01_legacy/artifacts/01_current_app/case_results.csv`: one row per evaluated test case.
- `benchmark_01_legacy/results/01_current_app/metrics_by_category.csv`: aggregate metrics by scope/category.
- `benchmark_01_legacy/results/01_current_app/metrics_by_error_type.csv`: aggregate metrics by scope/category/error_type.
- `benchmark_01_legacy/results/01_current_app/failure_samples.csv`: sampled unrecovered failures.
- `benchmark_01_legacy/results/01_current_app/top_wrong_families.csv`: frequent wrong top-1 families.
- `benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py`: fetched external algorithm snapshot used for comparison.
- `benchmark_01_legacy/artifacts/02_external_fast/case_results.csv`: one row per evaluated external-algorithm test case.
- `benchmark_01_legacy/results/02_external_fast/metrics_by_category.csv`: external aggregate metrics by scope/category.
- `benchmark_01_legacy/results/02_external_fast/metrics_by_error_type.csv`: external aggregate metrics by scope/category/error_type.
- `benchmark_01_legacy/results/03_comparison/metrics_by_category.csv`: side-by-side current versus external metric deltas.
- `benchmark_01_legacy/results/03_comparison/report.md`: human-readable current versus external comparison.

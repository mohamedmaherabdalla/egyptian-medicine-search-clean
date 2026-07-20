# Commercial Name Stress Test Cases

This document is the short index for the regenerated commercial-name stress suite on branch `medicine-search-clean`. The detailed documentation is split across:

- `benchmark_01_legacy/docs/generation_design.md`
- `benchmark_01_legacy/docs/data_description.md`
- `benchmark_01_legacy/docs/testing_strategy.md`

## Generated Files

| file | rows | purpose |
| --- | ---: | --- |
| `benchmark_01_legacy/data/seed_test_cases.csv` | 3,024 | Original seed suite, preserved unchanged. |
| `benchmark_01_legacy/data/test_cases.csv` | 341,901 | Seed rows plus regenerated catalog-wide stress cases. |
| `benchmark_01_legacy/data/test_cases_inside.csv` | 235,545 | Pure commercial-name spelling/search cases. |
| `benchmark_01_legacy/data/test_cases_semi_outside.csv` | 51,325 | Commercial-name plus strength, symbol, qualifier, abbreviation, parenthetical, or generic-search noise. |
| `benchmark_01_legacy/data/test_cases_outside.csv` | 55,031 | Queries using ingredient, manufacturer, class, route/form, or status/warning context. |
| `benchmark_01_legacy/data/generation_summary.json` | 1 | Machine-readable generation summary. |
| `benchmark_01_legacy/data/scope_summary.json` | 1 | Machine-readable scope summary. |

The three scope files sum to `341,901`, matching the expanded suite.

## Evaluation Result Files

| file | rows | purpose |
| --- | ---: | --- |
| `benchmark_01_legacy/artifacts/01_current_app/case_results.csv` | 341,901 | Full raw result table: one row per test case with rank, top result, top-5 bases, and safety flags. |
| `benchmark_01_legacy/results/01_current_app/metrics_by_category.csv` | 56 | Aggregate scores by scope and category, plus overall rows. |
| `benchmark_01_legacy/results/01_current_app/metrics_by_error_type.csv` | 1,833 | Detailed aggregate scores by scope, category, and exact `error_type`. |
| `benchmark_01_legacy/results/01_current_app/failure_samples.csv` | sample | First unrecovered failures for debugging. |
| `benchmark_01_legacy/results/01_current_app/top_wrong_families.csv` | 500 max | Most frequent wrong top-1 base groups. |
| `benchmark_01_legacy/results/01_current_app/report.md` | 1 | Human-readable evaluation report. |
| `benchmark_01_legacy/results/01_current_app/summary.json` | 1 | Machine-readable evaluation summary and file index. |
| `benchmark_01_legacy/artifacts/02_external_fast/case_results.csv` | 341,901 | Full raw result table for the external English fast algorithm. |
| `benchmark_01_legacy/results/02_external_fast/metrics_by_category.csv` | 56 | External aggregate scores by scope and category. |
| `benchmark_01_legacy/results/02_external_fast/metrics_by_error_type.csv` | 1,833 | External aggregate scores by scope, category, and exact `error_type`. |
| `benchmark_01_legacy/results/03_comparison/metrics_by_category.csv` | 56 | Side-by-side metric deltas: external minus current app. |
| `benchmark_01_legacy/results/03_comparison/report.md` | 1 | Human-readable comparison report. |

## Distribution

| bucket | rows |
| --- | ---: |
| `EASY` | 42 |
| `MEDIUM` | 59,947 |
| `HARD` | 253,178 |
| `EXTREME` | 28,734 |

Hard/extreme ratio: `82.45%`.

| danger | rows |
| --- | ---: |
| `SAFE` | 235,092 |
| `CAUTION` | 91,546 |
| `DANGEROUS` | 15,263 |

## Current App Evaluation

The current app was evaluated over all `341,901` regenerated cases.

| metric | value |
| --- | ---: |
| Overall Hit@1 | 82.76% |
| Overall Hit@5 | 90.16% |
| Overall Hit@10 | 92.60% |
| Overall Hit@20 | 94.59% |
| MRR@20 | 0.8603 |
| MAP@20 | 0.8515 |
| nDCG@20 | 0.8736 |
| Unsafe confident top-1 rate | 0.00% |
| Missing clarification rate | 0.00% |

The complete per-test-case results are in `benchmark_01_legacy/artifacts/01_current_app/case_results.csv`.
Full category metrics are in `benchmark_01_legacy/results/01_current_app/metrics_by_category.csv`.
Detailed per-error-type metrics are in `benchmark_01_legacy/results/01_current_app/metrics_by_error_type.csv`.

## External English Fast Algorithm Comparison

The external algorithm snapshot is stored at `benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py`.
It was evaluated on the same `341,901` cases with `commercial_name = n` and `canonical_name = b` so its grouped results can be compared with the current app's base-family targets.

| scope | current Hit@1 | external Hit@1 | delta | current Hit@20 | external Hit@20 | delta | current unsafe top-1 | external unsafe top-1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `inside` | 78.38% | 85.61% | +7.23% | 92.56% | 93.82% | +1.26% | 0.00% | 2.83% |
| `semi_outside` | 98.12% | 65.39% | -32.73% | 99.87% | 90.27% | -9.61% | 0.00% | 0.01% |
| `outside` | 87.15% | 67.53% | -19.62% | 98.37% | 84.52% | -13.85% | 0.00% | 2.58% |
| `__ALL__` | 82.76% | 79.66% | -3.09% | 94.59% | 91.79% | -2.80% | 0.00% | 2.36% |

Main interpretation: the external algorithm retrieves pure inside commercial-name typo cases better, but it has materially worse safety behavior and performs much worse once the query includes strength, symbol, ingredient, manufacturer, route, or other non-name context.

Full comparison details are in `benchmark_01_legacy/results/03_comparison/report.md` and `benchmark_01_legacy/results/03_comparison/metrics_by_category.csv`.

## Reproduce

```bash
PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 -m compileall benchmark_01_legacy
PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 -m unittest discover -s benchmark_01_legacy -p 'test_*.py'
PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 benchmark_01_legacy/generate_commercial_name_test_cases.py
PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 benchmark_01_legacy/evaluate_current_app_search.py
```

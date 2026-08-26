# Synthetic Benchmark Documentation

| Document | Purpose |
| --- | --- |
| `data_generation_and_dataset_description.md` | Dataset source, schema, 34 generators, distributions, and validation. |
| `testing_and_evaluation_strategy.md` | Metrics, behavior semantics, coverage contract, and reproduction. |
| `master_algorithm_design.md` | Algorithm 3 rank fusion and safety gates. |
| `algorithm_4_failure_fix_design.md` | Algorithm 4 rescue/ranking changes and measured evidence. |
| `algorithm_complexity_analysis.md` | Measured indexing, query time, and memory for Algorithms 1-4. |
| `mistake_type_framework.md` | Independent mistake taxonomy and fair-scoring rules. |
| `manual_failed_cases_deep_analysis.md` | Root-cause analysis of the supplied manual cases. |
| `testing_dataset_v2_industry_briefing.tex` | Dataset and Algorithms 1-3 industry briefing. |
| `today_v2_work_industry_briefing.tex` | Extended Algorithm 4 work briefing. |

Canonical score tables live in `../results/01_full_benchmark/`:

| File | Coverage |
| --- | --- |
| `metrics_by_category.csv` | Algorithms 1-4 by scope and category. |
| `metrics_by_error_type.csv` | Algorithms 1-4 by detailed error type. |
| `failure_samples.csv` | Consolidated sampled failures. |
| `summary.json` | Overall metrics and row-count audit. |

Generated LaTeX build files belong in `../artifacts/docs_build/`, not beside
the source documents.

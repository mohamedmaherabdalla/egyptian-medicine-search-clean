# Synthetic Commercial-Name Benchmark

This benchmark generates 115,000 deterministic medicine-search cases across
34 error categories and evaluates four search algorithms without mixing raw
case outputs with reviewable metrics.

Shared metric definitions and retrospective comparison rules are in
[`../docs/evaluation.md`](../docs/evaluation.md).

## Algorithms

| Label | Implementation |
| --- | --- |
| Algorithm 1 | Current application search. |
| Algorithm 2 | External English fast search. |
| Algorithm 3 | Rank fusion of Algorithms 1 and 2 with safety gates. |
| Algorithm 4 | Algorithm 2 plus bounded family rescue and conservative clarification. |

## Directory Contract

| Path | Purpose |
| --- | --- |
| `data/test_cases.csv` | Generated 115,000-row benchmark. |
| `data/category_summary.csv` | Per-category generation counts and labels. |
| `data/generation_summary.json` | Machine-readable generation audit. |
| `data/samples/proportional_6000.csv` | Reproducible proportional sample. |
| `results/01_full_benchmark/` | Canonical full-run report and merged Algorithms 1-4 tables. |
| `results/02_manual_cases/` | Manual-case follow-up metrics and analysis. |
| `results/03_sample_6000/` | Sample-only Algorithm 4 and DrugEye comparisons. |
| `results/04_drugeye/` | Public DrugEye benchmark summaries. |
| `artifacts/` | Raw case rows, website caches, and source tables; ignored by Git. |
| `docs/` | Dataset, algorithm, evaluation, failure, and complexity documentation. |

The parent run directory carries the version and run name. Filenames therefore
use stable roles such as `report.md`, `summary.json`, and
`metrics_by_category.csv` instead of repeating `v2` in every name.

## Generate The Dataset

Run from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 benchmark_02_synthetic/generate_dataset.py
```

The plan headline requested approximately 120,000 rows, but its explicit
category targets total 115,000. The generator follows the auditable category
targets exactly.

| Distribution | Rows |
| --- | ---: |
| Total | 115,000 |
| Hard or extreme | 84,400 |
| Safe | 80,931 |
| Caution | 11,144 |
| Dangerous | 22,925 |
| Expected match | 106,500 |
| Expected ambiguity | 5,500 |
| Expected no match | 3,000 |

## Run The Evaluations

```bash
# Algorithms 1 and 2
PYTHONDONTWRITEBYTECODE=1 python3 benchmark_02_synthetic/evaluate_algorithms_1_2.py \
  --workers 8 --chunk-size 200

# Algorithm 3
PYTHONDONTWRITEBYTECODE=1 python3 benchmark_02_synthetic/evaluate_algorithm_3.py \
  --workers 8 --chunk-size 200

# Algorithm 4
PYTHONDONTWRITEBYTECODE=1 python3 benchmark_02_synthetic/evaluate_algorithm_4.py \
  --workers 8 --chunk-size 200 --output-prefix algorithm_4

# Merge compatible Algorithms 1-4 aggregate tables
PYTHONDONTWRITEBYTECODE=1 python3 benchmark_02_synthetic/consolidate_full_results.py
```

Manual Algorithm 4 run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 benchmark_02_synthetic/evaluate_algorithm_4.py \
  --manual --workers 1 --output-prefix algorithm_4 \
  --output-dir benchmark_02_synthetic/results/02_manual_cases \
  --case-output benchmark_02_synthetic/artifacts/02_manual_cases/algorithm_4_cases.csv
```

Proportional sample run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 benchmark_02_synthetic/evaluate_algorithm_4.py \
  --input-csv benchmark_02_synthetic/data/samples/proportional_6000.csv \
  --workers 8 --chunk-size 200 --output-prefix algorithm_4 \
  --output-dir benchmark_02_synthetic/results/03_sample_6000 \
  --case-output benchmark_02_synthetic/artifacts/03_sample_6000/algorithm_4_cases.csv
```

## Canonical Full Results

| File | Purpose |
| --- | --- |
| `results/01_full_benchmark/metrics_by_category.csv` | Algorithms 1-4 category metrics with an explicit `algorithm` column. |
| `results/01_full_benchmark/metrics_by_error_type.csv` | Algorithms 1-4 detailed metrics. |
| `results/01_full_benchmark/failure_samples.csv` | Consolidated failure samples with algorithm identity. |
| `results/01_full_benchmark/summary.json` | Overall metrics and row-count audit. |
| `results/01_full_benchmark/algorithm_1_3_comparison.md` | Human-readable Algorithms 1-3 report. |
| `results/01_full_benchmark/algorithm_4_report.md` | Human-readable Algorithm 4 report. |
| `results/01_full_benchmark/failure_analysis.md` | Cross-algorithm failure analysis. |

Headline full-run results:

| Algorithm | Hit@1 | Hit@20 | Behavior success | Unsafe confident top-1 |
| --- | ---: | ---: | ---: | ---: |
| Algorithm 1 | 75.26% | 88.40% | 88.66% | 0.02% |
| Algorithm 2 | 79.30% | 91.84% | 91.29% | 6.40% |
| Algorithm 3 | 81.03% | 93.09% | 93.33% | 0.00% |
| Algorithm 4 | 82.12% | 93.41% | 93.64% | 0.00% |

## Documentation

Start with [`docs/README.md`](docs/README.md). The detailed documents cover
generation, testing semantics, Algorithms 3 and 4, mistake types, manual
failures, and measured time/space behavior.

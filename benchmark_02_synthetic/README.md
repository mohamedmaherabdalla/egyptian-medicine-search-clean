# Synthetic Commercial-Name Benchmark

> **Continuation-branch scope.** This package includes the deterministic
> generators, framework tests, seed/manual inputs, compact metrics, and reports.
> The generated `data/test_cases.csv`, proportional sample, raw row tables, and
> DrugEye response cache are intentionally not versioned; regenerate them with
> the commands below when a full historical replay is needed.

This benchmark generates 115,000 deterministic medicine-search cases across
34 error categories and supports five search algorithms without mixing raw
case outputs with reviewable metrics. The archived 115,000-case full report
contains Algorithms 1-4; Algorithm 5 has its own evaluator and must be run
before it is merged into that historical report.

Shared metric definitions and retrospective comparison rules are in
[`../docs/evaluation.md`](../docs/evaluation.md).

## Algorithms

| Label | Implementation |
| --- | --- |
| Algorithm 1 | Current application search. |
| Algorithm 2 | External English fast search. |
| Algorithm 3 | Rank fusion of Algorithms 1 and 2 with safety gates. |
| Algorithm 4 | Algorithm 2 plus bounded family rescue and conservative clarification. |
| Algorithm 5 | Evidence-guided retrieval, bounded reranking, and conservative clarification. |

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

# Algorithm 5
PYTHONDONTWRITEBYTECODE=1 python3 benchmark_02_synthetic/evaluate_algorithm_5.py \
  --workers 8 --chunk-size 200 --output-prefix algorithm_5

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

Manual Algorithm 5 run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 benchmark_02_synthetic/evaluate_algorithm_5.py \
  --manual --workers 1 --output-prefix algorithm_5 \
  --output-dir benchmark_02_synthetic/results/02_manual_cases \
  --case-output benchmark_02_synthetic/artifacts/02_manual_cases/algorithm_5_cases.csv
```

The current manual file contains 150 supplied query-target rows. Row-level
adjudication accepts 113 targets as supplied, corrects 22 to exact Egyptian
catalog families, and retains 15 invalid or ambiguous labels as diagnostic
exclusions. Algorithm 4 reaches 107/135 Hit@1 (79.26%) and 134/135 Hit@20
(99.26%) on the fair denominator, with zero unsafe confident wrong top-1
decisions. The complete 150-row decision, catalog, collision, edit-distance,
and ranking audit is
`artifacts/02_manual_cases/algorithm_4_cases.csv`.

The final run keeps all 150 rows in the artifact. The primary score uses only
the 135 accepted rows: 113 supplied labels were accepted, 22 were corrected to
exact catalog targets, and 15 remain diagnostic exclusions. The only accepted
top-20 miss is `clonox` with expected family `CLOPEX AGREL`; Algorithm 4 ranks
`CLOSOL` first and does not return the expected family within 20 results.

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

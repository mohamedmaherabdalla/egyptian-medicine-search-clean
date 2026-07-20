# Repository Structure

The repository separates production assets from benchmark generations. A
benchmark number identifies a dataset/evaluation generation; filenames inside
that directory do not repeat the version.

| Path | Ownership |
| --- | --- |
| `app/` | Deployable browser application. |
| `data/` | Shared canonical Egyptian medicine catalog and its dictionary. |
| `docs/` | Cross-project design, data, testing, and search documentation. |
| `benchmark_01_legacy/` | Original 341,901-case commercial-name benchmark. |
| `benchmark_02_synthetic/` | Deterministic 115,000-case synthetic benchmark and Algorithms 1-4. |
| `benchmark_03_ocr/` | Handwritten OCR, page segmentation, and OCR-derived search benchmark. |
| `benchmark_04_experiments/` | Cross-system baselines, Algorithm 4 ablations, and human-study preparation. |
| `exports/` | Local-only delivery bundles copied from canonical files. Excluded from Git. |

Each benchmark follows the same ownership rules:

| Directory | Contents |
| --- | --- |
| `data/` | Input datasets, manifests, and generation summaries. |
| `docs/` | Benchmark-specific methodology and design documentation. |
| `results/` | Reports, summaries, and compact aggregate metrics suitable for review. |
| `artifacts/` | Reproducible raw rows, caches, model weights, checkpoints, and temporary outputs. Ignored by Git. |
| `tests/` | Automated tests for that benchmark. |

## Result Rules

1. One logical run has one directory with stable filenames such as
   `report.md`, `summary.json`, `metrics_by_category.csv`, and
   `metrics_by_error_type.csv`.
2. Compatible aggregate tables from several algorithms or models are merged
   and distinguished by an explicit identifier column.
3. Large row-level tables live in `artifacts/`, not next to summary reports.
4. A report links to the canonical table it summarizes. It does not create a
   renamed copy of that table.
5. Superseded experiments remain in a numbered experiment directory only when
   they contain unique evidence.
6. One generated presentation format is canonical. Superseded HTML, SVG, PNG,
   duplicate PDFs, and LaTeX build files belong in ignored `artifacts/`, not in
   reviewable `results/`.
7. Delivery bundles under `exports/` may duplicate files for transport, but
   documentation and code must link to the canonical benchmark owner.

## Evaluation Ownership

[`evaluation.md`](evaluation.md) defines the shared metric names, denominators,
fair-scoring rules, statistical comparisons, and retrospective backfill policy.
Each benchmark README owns only its input data, execution commands, and
benchmark-specific interpretation.

When a new evaluation dimension is introduced, apply it to every compatible
historical algorithm and dataset before updating a comparison report. Record
`not_applicable` or `not_reproducible` when the required row-level evidence does
not exist; do not use zero or a blank as a substitute.

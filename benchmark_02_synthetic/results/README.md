# Results Index

Each numbered directory owns one run scope. Use the directory name for context;
filenames inside it describe only the artifact role.

| Directory | Contents |
| --- | --- |
| `01_full_benchmark/` | Canonical 115,000-case reports and merged Algorithms 1-4 tables. |
| `02_manual_cases/` | The 50 supplied manual cases and root-cause follow-up. |
| `03_sample_6000/` | Proportional sample comparisons. |
| `04_drugeye/` | Public DrugEye fuzzy and trade-name benchmarks. |

Start with `01_full_benchmark/algorithm_1_3_comparison.md` and
`01_full_benchmark/algorithm_4_report.md`. Use
`01_full_benchmark/metrics_by_category.csv` for the consolidated machine-
readable comparison.

Large per-case outputs and caches are intentionally stored under
`../artifacts/` and ignored by Git.

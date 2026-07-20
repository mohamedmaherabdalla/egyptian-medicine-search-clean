# External Algorithm Snapshots

This directory contains fetched snapshots of external search algorithms used for reproducible local evaluation.

## `english_search_algorithm_fast.py`

- Source URL: `https://github.com/youssefkhalil320/drugs_search/blob/main/app/english_search_algorithm_fast.py`
- Fetched from GitHub API on `2026-07-06`.
- SHA-256: `756d9f382a149a6e494f6b0ceab9e7b2b339a21bd3d3fcc7f2ee2e777f92fa2c`
- Evaluation harness: `benchmark_01_legacy/evaluate_external_english_fast_search.py`

The evaluator adapts this project's app catalog into the external algorithm's expected CSV schema:

| external field | app catalog source |
| --- | --- |
| `commercial_name` | `n` product name |
| `canonical_name` | `b` base group, falling back to `n` |

This adaptation is intentional because the generated commercial-name suite primarily expects commercial family/base-group retrieval, not individual product-row retrieval.

# Egyptian Medicine Search

A static medicine-search application backed by a 25,066-record Egyptian
medicine catalog, plus four reproducible benchmark areas.

The product rule is conservative: retrieve and rank candidates, expose the
evidence, and ask for clarification when the query does not support one safe
answer.

## Repository Map

| Path | Purpose |
| --- | --- |
| `app/` | Deployable browser application and runtime catalog. |
| `data/` | Shared readable catalog and data dictionary. |
| `docs/` | Cross-project design, testing, and repository documentation. |
| `benchmark_01_legacy/` | Original commercial-name benchmark. |
| `benchmark_02_synthetic/` | 115,000-case generated benchmark and Algorithms 1-4. |
| `benchmark_03_ocr/` | Handwritten OCR and OCR-derived search benchmarks. |
| `benchmark_04_experiments/` | Comparative retrieval baselines, Algorithm 4 ablations, and pharmacist-study preparation. |

See [`docs/repository_structure.md`](docs/repository_structure.md) for the
ownership rules used inside every benchmark. Shared metric definitions,
denominators, and retrospective comparison rules live in
[`docs/evaluation.md`](docs/evaluation.md).

## Run The App

```bash
python3 -m http.server 8010 --directory app
```

Open `http://127.0.0.1:8010`.

## Benchmark Entry Points

```bash
# Legacy generator and evaluators
python3 benchmark_01_legacy/generate_commercial_name_test_cases.py
python3 benchmark_01_legacy/evaluate_current_app_search.py
python3 benchmark_01_legacy/evaluate_external_english_fast_search.py

# Synthetic V2 generator and evaluators
python3 benchmark_02_synthetic/generate_dataset.py
python3 benchmark_02_synthetic/evaluate_algorithms_1_2.py --workers 8 --chunk-size 200
python3 benchmark_02_synthetic/evaluate_algorithm_3.py --workers 8 --chunk-size 200
python3 benchmark_02_synthetic/evaluate_algorithm_4.py \
  --input-csv benchmark_02_synthetic/data/test_cases.csv \
  --workers 8 --chunk-size 200 --output-prefix algorithm_4 \
  --case-output benchmark_02_synthetic/artifacts/01_full_benchmark/algorithm_4_cases.csv
python3 benchmark_02_synthetic/consolidate_full_results.py

# OCR benchmark help and tests
python3 benchmark_03_ocr/run_ocr_benchmark.py --help
PYTHONPATH=benchmark_03_ocr benchmark_03_ocr/.venv/bin/python \
  -m unittest discover -s benchmark_03_ocr/tests

# Classical retrieval baselines and Algorithm 4 ablations
benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/run_retrieval_experiments.py
```

Each benchmark keeps reviewable reports and aggregate metrics in `results/`.
Large per-case outputs, website caches, model weights, and checkpoints belong
in ignored `artifacts/` directories.

## Safety Position

This is a retrieval prototype, not a clinical decision system:

```text
retrieve candidates -> show evidence -> show warnings -> user confirms
```

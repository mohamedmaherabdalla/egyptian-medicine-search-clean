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
| `benchmark_02_synthetic/` | 115,000-case generated benchmark and Algorithms 1-5. |
| `benchmark_03_ocr/` | Handwritten OCR and OCR-derived search benchmarks. |
| `benchmark_04_experiments/` | Primary 66,257-pair clean synthetic retrieval benchmark, comparative baselines, Algorithms 4-5, and pharmacist-study preparation. |

See [`docs/repository_structure.md`](docs/repository_structure.md) for the
ownership rules used inside every benchmark. Shared metric definitions,
denominators, and retrospective comparison rules live in
[`docs/evaluation.md`](docs/evaluation.md).

## Run The Browser App

```bash
python3 -m http.server 8010 --directory app
```

Open `http://127.0.0.1:8010`.

This static mode reports `browser_consensus_search`; it does not execute the
Python Algorithm 6 pipeline.

## Run The Algorithm 6 App

Algorithm 6 requires about 2 GB RAM and takes about 13--30 seconds to build its
17,476-family indexes on startup. Run one API worker so the index is not copied
into multiple processes:

```bash
~/.local/bin/uv pip install --python benchmark_03_ocr/.venv/bin/python \
  -r app/requirements-api.txt

PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python -m uvicorn \
  app.api:app --host 127.0.0.1 --port 8000 --workers 1
```

Open `http://127.0.0.1:8000`. The header must say `Algorithm 6`. Verify the
runtime independently at `http://127.0.0.1:8000/api/runtime`; a valid response
contains `"algorithm":"algorithm_6"` and
`"evaluation_version":"algorithm_6_consensus_v1"`.

The production container uses the same entry point:

```bash
docker build -t egyptian-medicine-algorithm-6 .
docker run --rm -p 8000:7860 -e PORT=7860 egyptian-medicine-algorithm-6
```

Use a host with at least 2.5 GB available RAM. A 512 MB free web service cannot
start the unchanged Algorithm 6 indexes.

### Oracle Cloud Always Free

Use one Ampere A1 Flex Ubuntu VM with 2 OCPUs, 6 GB RAM, and a 50 GB boot
volume. Six gigabytes leaves enough headroom for the measured 1.9--2.1 GB
Algorithm 6 process while keeping its normal memory use above Oracle's 20\%
idle-memory threshold. In the VM's subnet or network security group, allow TCP
22 from your IP and TCP 80 from the internet.

After installing Docker and cloning the deployment branch, run:

```bash
chmod +x deploy/oracle-cloud.sh
./deploy/oracle-cloud.sh
```

The script builds the existing one-worker image, caps the container at 3 GB,
restarts it after VM reboots, and waits for `/health` before printing the
verified `/api/runtime` response. Open `http://<public-ip>` and confirm that the
header says `Algorithm 6 ready`. Add HTTPS through a domain and reverse proxy
before accepting sensitive or identifiable input.

## Benchmark Entry Points

The main positive-retrieval test file is
`benchmark_04_experiments/data/05_synthetic_clean_core/test_cases.csv`. The
115,000-row V2 file remains the broader behavior and safety benchmark.

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
python3 benchmark_02_synthetic/evaluate_algorithm_5.py \
  --input-csv benchmark_02_synthetic/data/test_cases.csv \
  --workers 8 --chunk-size 200 --output-prefix algorithm_5 \
  --case-output benchmark_02_synthetic/artifacts/01_full_benchmark/algorithm_5_cases.csv
python3 benchmark_02_synthetic/consolidate_full_results.py

# Primary clean synthetic retrieval benchmark, eleven systems on 66,257 unique pairs
PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/run_synthetic_clean_core.py
PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/analyze_synthetic_clean_core.py

# OCR benchmark help and tests
python3 benchmark_03_ocr/run_ocr_benchmark.py --help
PYTHONPATH=benchmark_03_ocr benchmark_03_ocr/.venv/bin/python \
  -m unittest discover -s benchmark_03_ocr/tests

# Classical retrieval baselines and Algorithm 4 ablations
benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/run_retrieval_experiments.py

# Expanded 53-system comparison on 464 OCR and 66,257 synthetic pairs
npm --prefix benchmark_04_experiments ci
PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/run_competitor_benchmark.py --dataset both

# Algorithm 5 ablations: 97 OCR configurations and 13 synthetic confirmations
PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/run_algorithm_5_ablations.py \
  --dataset ocr --profile all
PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/run_algorithm_5_ablations.py \
  --dataset synthetic --profile synthetic_confirmation --jobs 3

# Rebuild statistical tables, figures, and the Meeting 10 LaTeX section
MPLCONFIGDIR=/tmp/matplotlib-cache PYTHONDONTWRITEBYTECODE=1 \
  benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/analyze_competitor_benchmark.py
```

Each benchmark keeps reviewable reports and aggregate metrics in `results/`.
Large per-case outputs, website caches, model weights, and checkpoints belong
in ignored `artifacts/` directories.

## Safety Position

This is a retrieval prototype, not a clinical decision system:

```text
retrieve candidates -> show evidence -> show warnings -> user confirms
```

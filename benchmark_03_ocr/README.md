# Data 3: Real Handwritten Prescription OCR Benchmark

Data 3 turns real RxHandBD handwriting-recognition errors into a separate,
auditable medicine-search benchmark. It does not modify or mix rows into the
synthetic V2 suite.

Shared denominators, retrieval metrics, OCR metrics, and backfill rules are in
[`../docs/evaluation.md`](../docs/evaluation.md).

## Benchmark Layers

1. **OCR:** image to transcription over every valid RxHandBD row.
2. **Search recovery:** wrong OCR text to verified Egyptian commercial family.
3. **End to end:** image to OCR text to final medicine-search ranking.

An OCR row may enter layer 2 only when its human label maps uniquely and exactly
to the Egyptian catalog. Fuzzy catalog suggestions are review data, not ground
truth. An OCR output that equals a different real family is retained and marked
`DANGEROUS`.

All valid labeled images are processed. Same-pixel rows carrying contradictory
source labels and labels containing explicit `?` uncertainty placeholders are
retained as observations but excluded from scored denominators; the exclusion
reason remains in `dataset_manifest.csv`.

## Source Data

The default source path is `../../data3 (RxHandBD)`. The package expects the
official `RxHandBD-Raw` and `RxHandBD-ML` layouts and never edits them.

RxHandBD contains isolated word images, not original full prescription pages.
For uncropped pages, use the separate detector/recognizer pipeline documented in
[`docs/FULL_PRESCRIPTION_OCR_PIPELINE.md`](docs/FULL_PRESCRIPTION_OCR_PIPELINE.md).

## Directory Contract

| Path | Purpose |
| --- | --- |
| `data/01_rxhandbd/` | Audited source manifests and adjudicated catalog mappings. |
| `data/02_data4_data5/` | Paired Data 4/Data 5 manifests and catalog mapping. |
| `results/01_rxhandbd/` | Compact RxHandBD reports, summaries, and aggregate metrics. |
| `results/02_data4_data5/` | Paired Data 4/Data 5 benchmark outputs. |
| `results/03_page_segmentation/` | Compact full-page segmentation evaluation. |
| `results/04_model_predictions/` | Inclusive 14-model prediction metrics, paper, and canonical vector figures. |
| `artifacts/01_rxhandbd/` | Raw OCR observations, row-level search outputs, and experiments. |
| `artifacts/02_data4_data5/` | Raw paired OCR observations and row-level search outputs. |
| `artifacts/03_page_segmentation/` | Generated pages, crops, annotations, and region rows. |
| `artifacts/04_model_predictions/` | Inclusive OCR search cases and row-level Algorithm 4 results. |
| `artifacts/models/` | Downloaded model cache and training checkpoints. |

## Setup

```bash
UV_CACHE_DIR=/tmp/uv-cache uv venv .venv --python /opt/homebrew/bin/python3.11
UV_CACHE_DIR=/tmp/uv-cache uv pip install --python .venv/bin/python -r requirements-ocr.txt
```

Tesseract 5 with the English language pack must be available on `PATH`.

## Run

```bash
PYTHONDONTWRITEBYTECODE=1 python3 audit_and_map_dataset.py
PYTHONDONTWRITEBYTECODE=1 python3 apply_mapping_reviews.py

PYTHONDONTWRITEBYTECODE=1 python3 run_ocr_benchmark.py \
  --model tesseract --preprocessing raw --split all --workers 8 \
  --output artifacts/01_rxhandbd/ocr_tesseract_lstm_raw_all.csv --resume

HF_HOME=./artifacts/models/cache PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  run_ocr_benchmark.py --model trocr --preprocessing raw --split all \
  --output artifacts/01_rxhandbd/ocr_trocr_raw_all.csv --resume

EASYOCR_MODULE_PATH=./artifacts/models/cache/easyocr PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python run_ocr_benchmark.py --model easyocr --preprocessing raw \
  --split all --output artifacts/01_rxhandbd/ocr_easyocr_raw_all.csv --resume

PADDLE_PDX_CACHE_HOME=./artifacts/models/cache/paddlex \
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python run_ocr_benchmark.py --model paddleocr \
  --model-id PP-OCRv6_medium_rec --preprocessing raw --split all \
  --batch-size 8 --output artifacts/01_rxhandbd/ocr_paddleocr_raw_all.csv --resume

# The train/validation manifests are deterministic and contain no official-test rows.
PYTHONDONTWRITEBYTECODE=1 python3 build_screening_manifests.py

HF_HOME=./artifacts/models/cache HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python train_trocr_rxhandbd.py \
  --train-manifest artifacts/01_rxhandbd/experiments/selection/train_finetune_manifest_3457.csv \
  --validation-manifest artifacts/01_rxhandbd/experiments/selection/train_validation_manifest_1000.csv \
  --base-model microsoft/trocr-base-handwritten --preprocessing autocontrast \
  --device mps --epochs 3 --batch-size 2 --gradient-accumulation 4 \
  --learning-rate 1e-5 --weight-decay 0.01 --warmup-ratio 0.10 \
  --seed 20260714 --output-dir artifacts/models/training/trocr_base_rxhandbd

HF_HOME=./artifacts/models/cache HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python run_ocr_benchmark.py \
  --model trocr --model-id artifacts/models/training/trocr_base_rxhandbd/best \
  --model-label trocr_base_rxhandbd_finetuned --preprocessing autocontrast \
  --device mps --split all --batch-size 8 --checkpoint-every 200 --resume \
  --output artifacts/01_rxhandbd/ocr_trocr_base_rxhandbd_finetuned_autocontrast_all.csv

PYTHONDONTWRITEBYTECODE=1 python3 aggregate_ocr_metrics.py \
  artifacts/01_rxhandbd/ocr_tesseract_lstm_raw_all.csv artifacts/01_rxhandbd/ocr_trocr_raw_all.csv \
  artifacts/01_rxhandbd/ocr_easyocr_raw_all.csv artifacts/01_rxhandbd/ocr_paddleocr_raw_all.csv \
  artifacts/01_rxhandbd/ocr_trocr_base_rxhandbd_finetuned_autocontrast_all.csv

PYTHONDONTWRITEBYTECODE=1 python3 generate_search_cases.py \
  artifacts/01_rxhandbd/ocr_tesseract_lstm_raw_all.csv \
  artifacts/01_rxhandbd/ocr_trocr_raw_all.csv \
  artifacts/01_rxhandbd/ocr_easyocr_raw_all.csv \
  artifacts/01_rxhandbd/ocr_paddleocr_raw_all.csv \
  artifacts/01_rxhandbd/ocr_trocr_base_rxhandbd_finetuned_autocontrast_all.csv \
  --mapping data/01_rxhandbd/catalog_mapping_adjudicated.csv

PYTHONDONTWRITEBYTECODE=1 python3 analyze_label_novelty.py \
  artifacts/01_rxhandbd/ocr_tesseract_lstm_raw_all.csv artifacts/01_rxhandbd/ocr_trocr_raw_all.csv \
  artifacts/01_rxhandbd/ocr_easyocr_raw_all.csv artifacts/01_rxhandbd/ocr_paddleocr_raw_all.csv \
  artifacts/01_rxhandbd/ocr_trocr_base_rxhandbd_finetuned_autocontrast_all.csv

PYTHONDONTWRITEBYTECODE=1 python3 analyze_final_ocr_results.py \
  --candidate artifacts/01_rxhandbd/ocr_trocr_base_rxhandbd_finetuned_autocontrast_all.csv \
  --comparators artifacts/01_rxhandbd/ocr_tesseract_lstm_raw_all.csv \
    artifacts/01_rxhandbd/ocr_trocr_raw_all.csv artifacts/01_rxhandbd/ocr_easyocr_raw_all.csv \
    artifacts/01_rxhandbd/ocr_paddleocr_raw_all.csv

PYTHONDONTWRITEBYTECODE=1 python3 evaluate_search_algorithms.py
PYTHONDONTWRITEBYTECODE=1 python3 evaluate_search_algorithms.py \
  --case-mode all_mapped --output-prefix end_to_end
PYTHONDONTWRITEBYTECODE=1 python3 build_execution_status.py
PYTHONDONTWRITEBYTECODE=1 python3 validate_benchmark_outputs.py
PYTHONDONTWRITEBYTECODE=1 python3 build_report.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

For the separate 14-model prediction export:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=benchmark_03_ocr \
benchmark_03_ocr/.venv/bin/python benchmark_03_ocr/generate_search_cases.py \
  benchmark_03_ocr/data/04_model_predictions/predictions.csv \
  --results-dir benchmark_03_ocr/results/04_model_predictions \
  --raw-output-dir benchmark_03_ocr/artifacts/04_model_predictions

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=benchmark_03_ocr \
benchmark_03_ocr/.venv/bin/python benchmark_03_ocr/evaluate_search_algorithms.py \
  --cases benchmark_03_ocr/artifacts/04_model_predictions/search_cases.csv \
  --results-dir benchmark_03_ocr/results/04_model_predictions \
  --raw-output-dir benchmark_03_ocr/artifacts/04_model_predictions \
  --algorithms 4 --case-mode accepted --output-prefix algorithm_4

PYTHONDONTWRITEBYTECODE=1 \
benchmark_03_ocr/.venv/bin/python \
  benchmark_03_ocr/build_model_prediction_paper_figures.py

cd benchmark_03_ocr/docs
latexmk -pdf -interaction=nonstopmode \
  -emulate-aux-dir \
  -aux-directory=../artifacts/04_model_predictions/latex_build/results \
  -output-directory=../results/04_model_predictions \
  model_prediction_benchmark_analysis.tex
```

The prediction export is analyzed inclusively. Normalized exact readings,
high-distance readings, extreme-distance readings, name fragments, and
real-drug collisions remain explicit cohorts. Edit distance never removes a
mapped row from this 595-observation report. The canonical paper is
[`results/04_model_predictions/model_prediction_benchmark_analysis.pdf`](results/04_model_predictions/model_prediction_benchmark_analysis.pdf),
and its 40 vector figures live in `results/04_model_predictions/figures/`.

## Full-Prescription Pages

Do not send a full page directly to the word-level TrOCR recognizer. Segment it
first, then OCR the ordered crops:

```bash
PYTHONPATH=. .venv/bin/python run_prescription_page_ocr.py \
  --input /path/to/prescription.jpg \
  --output-dir artifacts/03_page_segmentation/run_001 \
  --level word --model trocr \
  --model-id artifacts/models/training/trocr_base_rxhandbd/best \
  --model-label trocr_base_rxhandbd_finetuned \
  --preprocessing autocontrast --device auto
```

The output includes the rectified page, annotated boxes, individual crops,
`regions.csv`, and reconstructed page text. `--level line` returns complete rows;
`--level word` is the correct mode for the current RxHandBD-trained recognizer.

## Folder 4 and Folder 5 Benchmark

The local `data4` and `data5` exports contain the same 4,680 indexed word
samples in two representations. `data4` is a processed `84x84` representation;
`data5` contains original variable-size crops. Their decoded labels agree for
all paired rows, so they are evaluated as paired views rather than counted as
9,360 independent examples.

The complete locked test split contains 780 paired samples across 78 classes.
Four OCR systems were run on both representations, producing 6,240 observations:

- frozen RxHandBD-fine-tuned TrOCR Base;
- PaddleOCR PP-OCRv6 medium recognition;
- zero-shot TrOCR Base handwritten;
- Tesseract 5.5.1 LSTM.

Rebuild the manifests and consolidated analysis with:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 prepare_data4_data5_manifests.py
PYTHONDONTWRITEBYTECODE=1 python3 analyze_data4_data5_benchmark.py
```

The completed report is
[`results/02_data4_data5/DATA4_DATA5_BENCHMARK_REPORT.md`](results/02_data4_data5/DATA4_DATA5_BENCHMARK_REPORT.md).
It includes the eight OCR scores, all per-class metrics, paired representation
changes, examples, Egyptian-catalog filtering, generated search cases, and
Algorithms 1-4 results.

## Canonical Outputs

| File | Contract |
| --- | --- |
| `data/01_rxhandbd/dataset_manifest.csv` | One row per official image and human label. |
| `data/01_rxhandbd/catalog_mapping.csv` | Exact mappings plus non-binding review suggestions. |
| `data/01_rxhandbd/dataset_audit_summary.json` | Integrity, split, duplicate, and overlap audit. |
| `artifacts/01_rxhandbd/ocr_*.csv` | One immutable OCR observation per image/model configuration. |
| `results/01_rxhandbd/model_selection_final/` | Disjoint-validation comparison and promotion decision. |
| `artifacts/models/training/trocr_base_rxhandbd/` | Training history and checkpoints. |
| `results/01_rxhandbd/final_analysis/` | Pairwise corrections, regressions, and examples. |
| `artifacts/01_rxhandbd/search_cases.csv` | Accepted and rejected observations with explicit reasons. |
| `artifacts/01_rxhandbd/search_results.csv` | Row-level Algorithms 1-4 outcomes. |
| `results/01_rxhandbd/search_metrics.csv` | Consolidated metrics by split, OCR model, mistake, and danger. |
| `results/01_rxhandbd/end_to_end_metrics.csv` | Image-to-OCR-to-search metrics. |
| `results/01_rxhandbd/validation_summary.json` | Cross-file coverage and reconciliation gate. |
| `results/01_rxhandbd/DATA3_BENCHMARK_REPORT.md` | Human-readable final report. |
| `artifacts/03_page_segmentation/<run>/regions.csv` | Full-page crop coordinates and OCR outputs. |
| `results/02_data4_data5/DATA4_DATA5_BENCHMARK_REPORT.md` | Paired Data 4/Data 5 report. |
| `results/04_model_predictions/algorithm_4_improvement_report.md` | OCR-derived Algorithm 4 baseline, holdout, regression, and failure analysis. |
| `results/04_model_predictions/model_prediction_benchmark_analysis.pdf` | Self-contained 595-observation analysis with the canonical Python-generated vector figures. |

Raw model/provider responses should be cached outside these canonical tables.
Do not create multiple renamed CSV files containing the same information.

## Systems Not Silently Skipped

- **Donut prescription model:** a 30-crop compatibility pilot was completed and
  reported separately. RxHandBD word crops are not its intended full-prescription
  input, so the pilot is excluded from the primary OCR ranking.
- **PaddleOCR:** evaluated with its English recognition-only model because
  RxHandBD already supplies isolated word crops. A page-level detector would
  answer a different question. PP-OCRv6 medium was selected over English v3
  mobile using the same 50 training images only.
- **Google Vision, Azure Read, Textract, Koncile:** require credentials and
  deidentified images. Their absence is a blocked execution status, not a score.
- **JonSnow repository:** uses the same Donut model and is not an independent OCR
  model. Its wrapper may be assessed as an end-to-end system only.
- **David-Magdy pipeline:** raw OCR and post-SymSpell output must be evaluated as
  separate systems to prevent medicine-dictionary leakage.
- **TrOCR Large:** completed the disjoint 1,000-row validation run but did not
  pass the final promotion band after domain fine-tuning won decisively.
- **GOT-OCR2:** completed the locked 600-row screen; 23.33% exact and high
  latency failed the promotion criteria.
- **DeepSeek-OCR and PaddleOCR-VL:** document-oriented execution paths do not
  support the benchmark host/task combination. Their blocked status is recorded.

# Full-Prescription Segmentation And OCR

## Why This Stage Exists

The promoted TrOCR model is a **recognizer**: it works best when the input image
contains one handwritten medicine name. A full prescription page contains
several lines, dosage instructions, headers, signatures, and large blank areas.
Passing the whole page directly to a word recognizer changes the task and usually
produces one incomplete or mixed transcription.

The page pipeline therefore separates two independently measurable problems:

1. **Text-region detection:** find the text and preserve its page coordinates.
2. **Text recognition:** run OCR on each detected crop.

This is not medicine-name hardcoding. Region detection uses grayscale contrast,
adaptive thresholding, connected components, morphology, relative component
size, and geometry only. OCR is called after the crops are frozen.

## Processing Steps

1. Convert the page to grayscale and create an adaptive binary ink mask.
2. Remove isolated scan noise while preserving thin handwriting strokes.
3. Estimate a conservative skew angle and optionally rectify the page.
4. Join nearby character components into either word regions or line regions.
5. Attach detached dots, crosses, and pen flourishes to the nearest main region.
6. Group regions by vertical overlap and sort them top-to-bottom, left-to-right.
7. Export every crop and its bounding box.
8. OCR the crops in a batch using the selected recognizer.
9. Reconstruct line text while retaining every raw crop-level prediction.

## Word Mode Versus Line Mode

| Mode | Output | Use case |
| --- | --- | --- |
| `word` | Separate ordered text regions | Best fit for the trained RxHandBD TrOCR recognizer and per-name search. |
| `line` | One crop for each prescription row | Useful for a line recognizer or later tokenization of drug, strength, and instructions. |

## Run On A Real Page

From `benchmark_03_ocr`:

```bash
PYTHONPATH=. .venv/bin/python run_prescription_page_ocr.py \
  --input /path/to/prescription.jpg \
  --output-dir artifacts/03_page_segmentation/run_001 \
  --level word \
  --model trocr \
  --model-id artifacts/models/training/trocr_base_rxhandbd/best \
  --model-label trocr_base_rxhandbd_finetuned \
  --preprocessing autocontrast \
  --device auto \
  --batch-size 8
```

`--input` may also be a directory. The pipeline recursively processes supported
image files. Use `--model none` to inspect segmentation before paying OCR cost.

## Outputs

| Output | Meaning |
| --- | --- |
| `run_manifest.json` | Input, model version, device, page count, and region count. |
| `regions.csv` | One row per crop with reading order, line, box, OCR output, confidence, latency, and errors. |
| `<page>/rectified.png` | Page actually used by the detector. Coordinates refer to this image. |
| `<page>/annotated.png` | Visual bounding-box and reading-order audit. |
| `<page>/crops/*.png` | Exact inputs sent to the OCR recognizer. |
| `<page>/page.json` | Reconstructed lines plus all crop-level provenance. |

## Integration Demonstration

Because RxHandBD supplies word crops rather than original pages, the repository
includes a deterministic integration page assembled from six real RxHandBD test
images. This validates wiring and ordering but is **not** a page-detection
accuracy benchmark.

Current demonstration result:

| Check | Result |
| --- | ---: |
| Expected word regions | 6 |
| Detected word regions | 6 |
| Detection precision / recall | 100% / 100% |
| Reading order | 6/6 correct |
| Line assignment | 6/6 correct |
| Fine-tuned TrOCR exact recognition | 4/6 (66.67%) |
| Mean crop-level CER | 0.1310 |
| Line-mode regions | 3 rows |

The two recognition errors are retained: `Nexcital -> nexicalac` and
`Indever -> inderen`. They are valid inputs for the existing OCR-error filtering
and medicine-search recovery pipeline.

## What Is Still Needed For A Defensible Full-Page Score

Real page-level evaluation requires original prescription pages with:

- human-verified transcription;
- a bounding box or polygon for each medicine-name span;
- reading order and line membership;
- labels distinguishing medicine names from dosage instructions, headers, and
  signatures;
- a patient/deidentified prescription split that prevents writer leakage.

With those annotations, detection precision/recall and IoU can be measured on
real pages. Until then, the synthetic-layout result is only an integration test;
the established RxHandBD numbers remain the authoritative word-recognition
benchmark.

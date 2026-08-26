# Data 3 Execution Plan and Requirements

## Objective

- Measure handwriting OCR on real labeled images.
- Convert realistic wrong OCR transcriptions into medicine-search queries.
- Accept a search case only when its human label has verified Egyptian-catalog ground truth.
- Evaluate Algorithms 1-4 on identical accepted inputs.
- Keep OCR accuracy, search recovery, and end-to-end accuracy as separate metrics.

## Local Data Inventory

- Present: RxHandBD version 2 raw and official ML train/test layouts.
- Unit: isolated handwritten word crop, not a full prescription page.
- Supplied labels: human text transcription per image.
- Official split: 4,463 train and 1,115 test rows.
- Not present locally: the separate Kaggle full-prescription datasets mentioned in the meeting message.
- Egyptian reference: `data/canonical_candidates.csv` with commercial-family aliases and ingredients.

## Data Required for Each Benchmark

- Word OCR: word image, human transcription, official split.
- Full-prescription OCR: original full page, full-page human transcription, medicine spans, and preferably bounding boxes.
- Egyptian search recovery: human label mapped to one verified Egyptian commercial family.
- Ingredient-query search: ingredient label mapped to a set of relevant families; it must not be scored as one arbitrary brand.
- Writer-independent OCR: writer or prescriber ID. RxHandBD does not provide one, so this split cannot be verified.
- Commercial API comparison: 10-30 deidentified images, provider credentials, privacy approval, fixed API versions, and stored raw responses.

## Model Matrix

- Tesseract 5 LSTM: executable locally; full word-crop benchmark.
- Microsoft TrOCR Base Handwritten: executable locally; full word-crop benchmark.
- Microsoft TrOCR Large Handwritten: completed a disjoint 1,000-row validation
  run; not promoted after the domain-fine-tuned Base checkpoint won.
- TrOCR Base fine-tuned on RxHandBD: trained on 3,457 rows and selected on 1,000
  disjoint training rows; promoted to the complete benchmark.
- GOT-OCR2: completed a locked 600-row screen; not promoted on accuracy/latency.
- EasyOCR: executable locally; full word-crop benchmark.
- PaddleOCR PP-OCRv6 medium recognizer: executable locally; selected on a training-only pilot and run in recognition-only mode for pre-cropped words.
- `chinmays18/medical-prescription-ocr`: Donut full-document model; run only as a labeled input-mismatch pilot on word crops unless full pages are supplied.
- JonSnow repository: wrapper around the same Donut checkpoint; not an independent model score.
- David-Magdy pipeline: requires full prescription pages. Raw OCR and dictionary-corrected output must be scored separately.
- Google Vision, Azure Read, Amazon Textract, Koncile: blocked until credentials and privacy approval are supplied.

## Execution Stages

1. Audit source rows, labels, image integrity, decoded-pixel duplicates, and split leakage.
2. Resolve labels conservatively against Egyptian families; send fuzzy suggestions to human review only.
3. Calibrate preprocessing on training rows only.
4. Run every feasible OCR model over every valid labeled image with resumable checkpoints.
5. Compute exact accuracy, character error rate, word error rate, empty rate, runtime errors, and latency.
6. Generate one accepted/rejected search-case ledger with explicit rejection reasons.
7. Evaluate Algorithms 1-4 on accepted recovery cases and on all verified mapped observations end to end.
8. Validate row reconciliation and build one consolidated report.

## Acceptance Rules

- Ground truth must resolve uniquely to an Egyptian commercial family.
- Source ground truth must be usable; contradictory duplicate labels and explicit
  question-mark uncertainty placeholders are retained but excluded from scoring.
- OCR must complete successfully and produce a non-empty wrong transcription.
- Normalized edit distance must be at most 0.60 unless the wrong transcription is exactly another real Egyptian family.
- The transcription must retain shared character evidence with the verified target.
- Real-drug-name collisions are always retained and labeled dangerous.

## Deliverables

- Dataset manifest, registry, pixel-duplicate audit, mapping table, and review queue.
- Per-model canonical OCR observations and aggregate OCR metrics.
- Unified accepted/rejected search-case ledger.
- Algorithms 1-4 row-level recovery and end-to-end results.
- Metrics by split, OCR model, difficulty, mistake type, and danger.
- Model execution-status matrix, validation summary, and consolidated Markdown report.
- Train-only screening/validation manifests, checkpoint history/hash, pairwise
  correction/regression tables, and deterministic official-test examples.

## Final Outcome

- Reliable OCR denominator: 5,568 rows; untouched official test: 1,111 rows.
- Promoted TrOCR exact/CER: 60.65% / 0.1492 overall and 45.36% / 0.2799
  on the official test split.
- Official-test promoted accuracy: 52.97% for labels seen during training and
  32.86% for labels unseen during training.
- Search-recovery ledger: 248 accepted OCR observations and 222 unique pairs.
- End-to-end promoted-OCR rows: Algorithms 2-4 reached 93.18% Hit@1 and 96.21%
  Hit@20 over the 132 uniquely mapped observations.

## Expansion Requirements

- Human review of fuzzy catalog mappings to enlarge the verified Egyptian subset.
- At least 500 unique verified OCR-error query/target pairs for strong search-recovery claims.
- Full prescription pages for Donut and full-page OCR pipelines.
- A deidentified common API sample and credentials for commercial systems.
- A second geographically relevant handwritten dataset to test generalization beyond Bangladesh-origin labels.

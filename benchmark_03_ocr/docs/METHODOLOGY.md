# Data 3 Benchmark Methodology

## Research Questions

Data 3 answers three questions independently:

1. How accurately does an OCR model transcribe an isolated handwritten word?
2. When the transcription is wrong but still realistic, can medicine search
   recover the verified Egyptian commercial family?
3. Starting with the image, does OCR plus search return the correct family?

These questions have different denominators and must never be represented by a
single combined accuracy.

## Dataset Contract

- Source: RxHandBD version 2, CC BY 4.0.
- Unit: one 512-by-512 handwritten word image.
- Human labels: supplied `Text` column.
- Official split: 4,463 training rows and 1,115 test rows.
- The one blank-label row is audited but excluded from OCR scoring.
- Three nonblank labels containing question-mark uncertainty placeholders are
  processed for coverage but excluded from accuracy and search denominators.
- The raw and ML directory copies are compared by decoded RGB pixels, not JPEG
  bytes, because byte-level metadata differs while image pixels are identical.
- Duplicate images are detected from decoded pixel hashes. Cross-split duplicates
  and identical images with conflicting labels are separate audit failures.
- Identical-pixel rows with contradictory labels are still sent through OCR so
  coverage remains complete, but are excluded from accuracy and downstream
  search denominators because no deterministic evaluator can know which supplied
  label is correct. Their sample IDs remain in the manifest and duplicate audit.

The official training split is used for preprocessing calibration, disjoint
model selection, and the explicitly labeled domain-fine-tuning experiment.
Primary OCR numbers include a separately reported untouched official-test result.

The usable training rows are partitioned deterministically into 3,457 fine-tune
rows and 1,000 validation rows with zero overlap. A separate 600-row screen is a
subset of the fine-tune pool, not the validation set. No official-test row is
used for preprocessing, model promotion, checkpoint selection, or training.

## Egyptian Catalog Resolution

The commercial search benchmark requires a verified target in
`data/canonical_candidates.csv`.

- Labels and catalog aliases are Unicode-normalized, uppercased, and compacted.
- Obvious trailing strength/form context may be removed, but internal characters
  are never guessed or corrected.
- A row is accepted automatically only when the normalized label resolves to one
  unique commercial family.
- Multiple exact families produce `ambiguous_exact` and require review.
- Approximate names produce ranked suggestions only; similarity never establishes
  ground truth.
- Generic/ingredient labels must become a separately defined ingredient-query
  benchmark rather than being assigned to an arbitrary brand.

The review queue has blank decision, reviewer, and note columns so adjudication is
traceable. Approved decisions must include a stable family key.

## OCR Protocol

- Every model receives the same source image for a given configuration.
- Model ID/version, preprocessing, device, output, confidence, latency, and error
  are recorded per observation.
- Preprocessing was calibrated on training images only.
- Tesseract configuration is English LSTM, OEM 1, PSM 7.
- TrOCR uses `microsoft/trocr-base-handwritten` and batched deterministic decoding.
- TrOCR Large and GOT-OCR2 were screened as additional candidates. Large reached
  27.60% exact on the 1,000-row validation set; GOT-OCR2 reached 23.33% on the
  600-row screen at roughly 744 ms/image. Neither passed the final promotion rule.
- EasyOCR uses the English detector/recognizer and preserves its confidence.
- PaddleOCR uses `PP-OCRv6_medium_rec` in recognition-only mode because the
  dataset already consists of isolated word crops; no text detector is needed.
  It was selected over `en_PP-OCRv3_mobile_rec` on the same 50 training images.
- Word-level models and full-prescription models are not compared as if they had
  equivalent inputs.
- Checkpoints are written every 50 observations, allowing long runs to resume
  without changing already recorded rows.

## Full-Page Segmentation Protocol

The RxHandBD benchmark remains word-level. Uncropped prescription pages enter a
separate front end before OCR:

- adaptive binarization and connected-component cleanup create an ink mask;
- conservative deskewing rectifies small page rotations;
- geometry-based morphology creates word or line regions;
- detached punctuation and pen marks are attached by relative size and distance;
- regions are sorted top-to-bottom and left-to-right;
- every bounding box, crop, reading-order index, and raw OCR output is retained.

Detection and recognition are scored separately. The included six-region
synthetic-layout fixture checks integration only because no labeled full pages
are present locally. Real page-level claims require human region annotations and
cannot be inferred from word-crop accuracy.

## Domain Fine-Tuning Protocol

- Base checkpoint: `microsoft/trocr-base-handwritten`.
- Input preprocessing: autocontrast, selected on training rows only.
- Train/validation rows: 3,457 / 1,000, with zero sample overlap.
- Epochs: 3; batch size: 2; gradient accumulation: 4; effective batch: 8.
- Optimizer schedule: learning rate `1e-5`, weight decay `0.01`, 10% linear
  warmup followed by linear decay.
- Seed: `20260714`; all 333,921,792 parameters are trainable.
- Checkpoint rule: highest validation exact accuracy, then lowest CER.
- Best epoch: 3, with 56.10% validation exact and 0.1509 CER.
- Frozen weight SHA-256:
  `4190103673868de6dac91efc8794abb1f93211da20be74ecb15fa9711ed792dc`.

The official test result is reported both for labels seen in training and labels
unseen in training. This exposes vocabulary memorization instead of hiding it in
one average.

## OCR Metrics

- Exact accuracy compares compact normalized text.
- Character error rate is Levenshtein distance divided by ground-truth length.
- Word error rate is binary for this one-word/label dataset: zero only on an exact
  normalized transcription.
- Empty-output and runtime-error rates remain separate.
- Latency includes image preprocessing and inference but excludes one-time model
  download and catalog preparation.
- Mean, median, and 95th-percentile latency are reported.

## OCR-Error Case Filtering

A search-recovery case requires a unique exact catalog mapping, successful OCR,
non-empty wrong output, and enough shared textual evidence.

- Easy: normalized edit distance in `(0, 0.20]`.
- Medium: `(0.20, 0.40]`.
- Hard: `(0.40, 0.60]`.
- Above `0.60`: manual review, not automatic acceptance.
- Empty output: separate `EMPTY` class.
- Exact OCR: OCR success, excluded from the wrong-output recovery denominator.
- If OCR output is another real Egyptian family, preserve it as a dangerous
  real-drug collision even when edit distance is high.

Every rejected observation remains in `search_cases.csv` with one explicit
rejection code. No failed row disappears from the audit trail.

## Search Evaluation

Algorithms 1-4 receive identical OCR text. Their indexes are prepared once before
timed queries.

- Hit@1/5/10/20 checks the verified commercial family.
- MRR@20 rewards placing the first relevant family earlier.
- Unsafe confident top-1 means the system confidently returns a wrong family.
- Clarification rate measures how often the top response avoids confidence.
- Per-query latency excludes one-time index construction.
- Search-recovery metrics use accepted realistic wrong outputs only.
- End-to-end metrics use every uniquely mapped OCR observation, including exact,
  empty, and severe outputs.

## Leakage Controls

- Fuzzy mapping suggestions cannot become expected answers automatically.
- OCR exact outputs do not enter the error-recovery benchmark.
- Question-mark placeholder labels and contradictory same-pixel labels are
  excluded from scoring with explicit reason codes; their OCR observations remain.
- Search algorithms are not tuned against the official OCR test results.
- David-Magdy raw OCR and post-SymSpell correction must be separate systems.
- JonSnow and the Hugging Face Donut checkpoint are one underlying OCR model.
- Commercial APIs must process the same deidentified sample.
- No provider-generated OCR output may be used as human ground truth.

## Statistical Interpretation

The complete RxHandBD OCR benchmark has thousands of rows, but the Egyptian
commercial-family overlap is much smaller. Search percentages over a small number
of accepted cases are exploratory and must always display the case count. A strong
paper claim requires at least 500 unique verified OCR-error query/target pairs or
additional Egyptian prescription data.

# Algorithm 4 OCR-Derived Improvement Report

## Purpose

This run uses OCR mistakes produced by 14 recognition models as real search
queries. It tests whether Algorithm 4 can recover the verified Egyptian
commercial family without encoding any medicine-specific aliases.

## Input Audit

| item | count |
| --- | ---: |
| Source OCR observations | 595 |
| Source OCR models | 14 |
| Source target names | 27 |
| Represented and evaluated observations | 595 |
| Unique query-target pairs | 477 |
| Fair scored unique pairs | 464 |
| Real-drug collision diagnostics | 17 |
| Extreme-distance cohort | 121 |
| Exact-after-normalization cohort | 6 |
| Rows rejected because of distance | 0 |

All rows for one target family are assigned to either development or holdout,
never both. The inclusive fair set contains 371 development pairs and 93
holdout pairs. Generic labels such as `LANTUS` are resolved to their explicit
catalog variants, such as `LANTUS CARTRIDGES` and `LANTUS SOLOSTAR PENS`.

Distance is now a reporting dimension, not an exclusion rule for this supplied
prediction export. The 121 previously filtered extreme rows and six
spacing-only exact rows remain visible in the generated cases, row-level
results, metrics, and visual dashboard.

## What Changed

1. Added a bounded two-character edge retrieval path. A query may contribute
   candidates sharing its first two or last two characters, but only families
   within two characters of its length are eligible.
2. Protected established candidate generation from the new edge path. Core
   retrieval receives 45 prefilter slots and the edge rescue receives 15 slots,
   so edge candidates cannot evict the complete core pool before scoring.
3. Used a two-stage edge filter. Cheap n-gram, positional, phonetic, and length
   evidence selects 45 candidates; full edit evidence selects the final 15.
4. Added a strictly-closer correction. A non-variant candidate may move first
   only when both search layers retrieve it, it is within two edits, it is at
   least one edit closer than the current top result, and its score is close.
5. Added catalog-family-head comparison. A validated family variant may use the
   edit distance to its catalog-derived family head, so `LANTS` can recover the
   explicit `LANTUS ...` variants. Equal-distance alternatives remain in model
   order and still require clarification.
6. Extended the existing deletion index to three-character queries. This
   recovers a four-character family when the OCR output omits one character,
   such as `RIO -> RIVO`, without scanning the full catalog.
7. Added a bounded rescue-only full-name correction. A rescue candidate may
   move first only for a query of at least five characters, within three raw
   edits, at least one edit closer than the current top result, no worse on
   weighted distance, and within a 0.35 score gap. Combined exact phonetic and
   skeleton evidence, plus explicit prefix evidence, keeps its existing order.
8. Ported the validated behavior to the static browser application. Its
   two-character edge path adds at most 15 catalog-derived family supplements.
   Supplements cannot replace an equal-scoring core top result, and only a
   three-edit candidate in the narrow 0.80--0.88 rescue band may trigger the
   strict edge correction.

No OCR query, expected answer, commercial name, or manual alias was added to
Algorithm 4.

## Inclusive OCR Results

These metrics include all 595 source observations. The fair unique scope removes
duplicate query-target pairs and excludes 17 exact collisions where the OCR
output is already another real catalog medicine, but those collision rows still
appear in the all-observation and cohort metrics.

| scope | cases | H@1 | H@20 | unsafe | mean latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| All source observations | 595 | 50.25% | 73.78% | 0.00% | 15.00 ms |
| All fair unique pairs | 464 | 47.63% | 71.12% | 0.00% | 14.85 ms |
| Fair development pairs | 371 | 47.98% | 70.62% | 0.00% | 14.94 ms |
| Fair holdout pairs | 93 | 46.24% | 73.12% | 0.00% | 14.49 ms |

| analysis cohort | rows | H@1 | H@20 |
| --- | ---: | ---: | ---: |
| Normalized exact match | 6 | 100.00% | 100.00% |
| Standard OCR error | 345 | 79.42% | 98.26% |
| Visible name fragment | 10 | 70.00% | 100.00% |
| High-distance prediction | 96 | 12.50% | 75.00% |
| Extreme-distance prediction | 121 | 0.00% | 8.26% |
| Real-drug name collision | 17 | 0.00% | 11.76% |

The lower inclusive headline is expected and important: the old denominator
removed the 121 hardest predictions. The new denominator reports their actual
performance instead of hiding it.

## Historical Standard-Distance Improvement Slice

The baseline comparison below is retained on the original 347-pair slice because
the saved baseline predates the inclusive policy. It should not be compared
directly with the 595-row headline above.

| scope | pairs | baseline H@1 | final H@1 | baseline H@20 | final H@20 | unsafe final | mean latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Development | 273 | 61.54% | 62.64% | 86.45% | 91.94% | 0.00% | 15.34 ms |
| Holdout | 74 | 51.35% | 54.05% | 81.08% | 87.84% | 0.00% | 15.06 ms |
| All fair pairs | 347 | 59.37% | 60.81% | 85.30% | 91.07% | 0.00% | 15.28 ms |

The baseline mean was 13.31 ms per fair pair. The final path added about 1.97 ms
while improving H@20 by 5.76 percentage points. The holdout improvement shows
that the change is not limited to target families used during development.

## Recovery Examples

| OCR input | verified target | baseline | final | reason |
| --- | --- | --- | --- | --- |
| `MYCLAX` | `MYOLAX` | rank 2 behind `MICLOX` | rank 1 | Both retrieval layers support the candidate and it is one edit closer. |
| `LANTS` | `LANTUS ...` variants | rank 15 | rank 1 | Catalog family-head distance is 1 even though full package names are longer. |
| `LANUS` | `LANTUS ...` variants | rank 19 | rank 1 | Same family-head rule on an untouched holdout family. |
| `VIZORAX` | `VIGOREX` | outside top 20 | rank 1 | Edge retrieval restores a heavily corrupted same-length family. |
| `KELONOLAE` | `KETOROLAC` | outside top 20 | rank 1 | Bounded edge retrieval restores a multi-edit candidate. |
| `RIO` | `RIVO` | outside top 20 | rank 1 | The three-character query now reaches the existing one-deletion index. |
| `MYOLANA` | `MYOLAX` | rank 2 | rank 1 | A rescue-only full name is one edit closer within the bounded score gap. |
| `NIGROHEX` | `VIGOREX` | rank 2 | rank 1 | The same general correction transfers to a holdout family. |

## Why Remaining Misses Are Not One Problem

On the untouched baseline, 141 of 347 fair unique pairs missed rank 1:

- 90 had the verified target at ranks 2-20;
- 51 did not have the target in the top 20;
- only 26 misses had a verified target strictly closer than the returned top
  candidate;
- most other misses were equal-distance or had a different catalog family that
  was genuinely closer to the OCR output.

For example, `LAMIX` is one edit from both `LASIX` and `VAMIX`. Without another
signal, forcing either answer would optimize an arbitrary benchmark label. The
application should display both and ask for clarification.

## Regression Results

| suite | cases | baseline H@1 | final H@1 | baseline H@20 | final H@20 | final behavior | unsafe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Manual supplied cases | 50 | 72.00% | 74.00% | 92.00% | 94.00% | 94.00% | 0.00% |
| Proportional sample | 6,000 | 81.12% | 81.40% | 92.83% | 93.28% | 93.45% | 0.00% |
| Full synthetic suite | 115,000 | 81.86% | 82.12% | 92.99% | 93.41% | 93.64% | 0.00% |

Against the immediately preceding A4 artifact, the full suite records 180
Hit@1 gains and 95 losses, plus 132 Hit@20 gains and five losses. The net
changes are +85 Hit@1 rows and +127 Hit@20 rows. The average candidate pool is
23.47, and unsafe confident top-1 remains zero.

## Static Browser Parity Check

This check runs `app/app.js` with Node.js against the same 595 OCR observations
and `app/data/catalog.json`. It validates the deployed browser implementation;
it is separate from the Python Algorithm 4 headline above because the browser
still ranks product records while Python ranks deduplicated commercial
families.

| browser scope | cases | prior H@1 | final H@1 | prior H@20 | final H@20 | paired H@1 gains/losses | paired H@20 gains/losses |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All OCR observations | 595 | 40.00% | 42.35% | 66.39% | 67.73% | 14 / 0 | 8 / 0 |
| Fair unique pairs | 464 | 37.93% | 40.09% | 62.07% | 63.58% | 10 / 0 | 7 / 0 |

The paired comparison is the key guardrail: the final browser rule improves 10
fair queries at rank 1 and seven within the top 20 without losing any query
that the prior browser implementation recovered. The browser continues to mark
these fuzzy results for clarification rather than presenting them as medically
confident answers.

## Reproduce

Run from the repository root:

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
```

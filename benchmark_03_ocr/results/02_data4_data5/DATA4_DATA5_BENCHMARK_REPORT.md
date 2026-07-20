# Folder 4 and Folder 5 OCR and Search Benchmark

## Executive Result

Folders 4 and 5 contain the same indexed 4,680 labeled medicine-word samples in two representations. Folder 4 stores processed `84x84` images; folder 5 stores the original variable-size crops. Their labels match for every corresponding sample, so this report treats them as paired views rather than 9,360 independent examples.

The locked test split contains `780` paired samples across `78` classes. All four OCR configurations completed all test rows on both representations with zero runtime errors. The best exact OCR result was **PaddleOCR on folder 5: 352/780 (45.13%)**. The fine-tuned TrOCR checkpoint was second on folder 5 at **313/780 (40.13%)**.

## Dataset Audit

| Check | Result |
| --- | --- |
| Rows per representation | 4680 |
| Train / validation / test | 3120 / 780 / 780 |
| Medicine classes | 78 |
| Paired label mismatches | 0 |
| Exact Egyptian catalog classes | 7 |
| Catalog-eligible rows across both representations and all splits | 840 |

The two image files for a corresponding ID are not byte-identical. That is expected: folder 4 is a resized/processed export. The evidence for pairing is the shared split, filename index, numeric class mapping, and exact decoded label agreement, not pixel identity.

## OCR Results

| OCR system | Representation | Rows | Exact | Accuracy | Mean NED | Mean ms | Empty | Errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Fine-tuned TrOCR Base | data4_processed84 | 780 | 259 | 33.21% | 0.265 | 168.1 | 0 | 0 |
| Fine-tuned TrOCR Base | data5_original | 780 | 313 | 40.13% | 0.222 | 162.7 | 0 | 0 |
| PaddleOCR PP-OCRv6 medium | data4_processed84 | 780 | 164 | 21.03% | 0.334 | 96.1 | 4 | 0 |
| PaddleOCR PP-OCRv6 medium | data5_original | 780 | 352 | 45.13% | 0.176 | 116.6 | 0 | 0 |
| Zero-shot TrOCR Base | data4_processed84 | 780 | 166 | 21.28% | 0.442 | 173.8 | 0 | 0 |
| Zero-shot TrOCR Base | data5_original | 780 | 201 | 25.77% | 0.409 | 224.5 | 0 | 0 |
| Tesseract 5.5.1 | data4_processed84 | 780 | 3 | 0.38% | 0.800 | 73.3 | 58 | 0 |
| Tesseract 5.5.1 | data5_original | 780 | 49 | 6.28% | 0.591 | 69.9 | 48 | 0 |

`NED` is normalized edit distance: `0` is an exact transcription and larger values mean more character corruption. Exact accuracy ignores case and punctuation through the benchmark's normalized comparison.

## Paired Representation Effect

| OCR system | Folder 4 exact | Folder 5 exact | F5-F4 accuracy | Both exact | F4 only | F5 only | Neither |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Fine-tuned TrOCR Base | 259 | 313 | 6.92% | 221 | 38 | 92 | 429 |
| PaddleOCR PP-OCRv6 medium | 164 | 352 | 24.10% | 156 | 8 | 196 | 420 |
| Zero-shot TrOCR Base | 166 | 201 | 4.49% | 145 | 21 | 56 | 558 |
| Tesseract 5.5.1 | 3 | 49 | 5.90% | 0 | 3 | 49 | 728 |

Folder 5 improved every OCR system. The largest gain was PaddleOCR: `+24.10` percentage points. This is a preprocessing/domain result, not extra training data: both sides contain the same test words. The aggressive fixed-size representation removes detail and changes aspect ratios that recognition models use.

## Paired Examples

| OCR system | Example type | Image | Truth | Folder 4 output | Folder 5 output |
| --- | --- | --- | --- | --- | --- |
| Fine-tuned TrOCR Base | data5_recovers_data4_failure | 0.png | Aceta | acetete | aceta |
| Fine-tuned TrOCR Base | data5_recovers_data4_failure | 11.png | Ace | Alc | Ace |
| Fine-tuned TrOCR Base | data5_recovers_data4_failure | 26.png | Alatrol | aletrol | alatrol |
| Fine-tuned TrOCR Base | data4_recovers_data5_failure | 24.png | Alatrol | Alatrol | Aletrol |
| Fine-tuned TrOCR Base | data4_recovers_data5_failure | 50.png | Axodin | axodin | exodin |
| Fine-tuned TrOCR Base | data4_recovers_data5_failure | 72.png | Azyth | azyth | azyyth |
| Fine-tuned TrOCR Base | both_wrong_near_miss | 101.png | Backtone | backstone | backactone |
| Fine-tuned TrOCR Base | both_wrong_near_miss | 110.png | Baclofen | bachlogen | Baclifen |
| Fine-tuned TrOCR Base | both_wrong_near_miss | 181.png | Cetisoft | Cotisoft | Catsisoft |
| PaddleOCR PP-OCRv6 medium | data5_recovers_data4_failure | 1.png | Aceta | Aceka | Aceta |
| PaddleOCR PP-OCRv6 medium | data5_recovers_data4_failure | 11.png | Ace | tu | Ace |
| PaddleOCR PP-OCRv6 medium | data5_recovers_data4_failure | 20.png | Alatrol | Altrod | Alatrol |
| PaddleOCR PP-OCRv6 medium | data4_recovers_data5_failure | 142.png | Beklo | BEKLO | BEULO |
| PaddleOCR PP-OCRv6 medium | data4_recovers_data5_failure | 211.png | Denixil | denixil | senixil |
| PaddleOCR PP-OCRv6 medium | data4_recovers_data5_failure | 229.png | Diflu | Diflu | Difen |
| PaddleOCR PP-OCRv6 medium | both_wrong_near_miss | 540.png | Napa Extend | Nostrd | Napa Extond |
| PaddleOCR PP-OCRv6 medium | both_wrong_near_miss | 100.png | Backtone | Gndtru | Bachtone |
| PaddleOCR PP-OCRv6 medium | both_wrong_near_miss | 110.png | Baclofen | Baulliun | Baclrfen |
| Zero-shot TrOCR Base | data5_recovers_data4_failure | 2.png | Aceta | acetants . | . Aceta |
| Zero-shot TrOCR Base | data5_recovers_data4_failure | 13.png | Ace | ASE- | ace . |
| Zero-shot TrOCR Base | data5_recovers_data4_failure | 25.png | Alatrol | ALANCE | al Atrol |
| Zero-shot TrOCR Base | data4_recovers_data5_failure | 4.png | Aceta | aceta | Aeeto |
| Zero-shot TrOCR Base | data4_recovers_data5_failure | 140.png | Beklo | beklo | Baklo |
| Zero-shot TrOCR Base | data4_recovers_data5_failure | 246.png | Disopan | Disopan . | 1 Disopan . |
| Zero-shot TrOCR Base | both_wrong_near_miss | 68.png | Azithrocin | azithmocin . | azithmocin . |
| Zero-shot TrOCR Base | both_wrong_near_miss | 549.png | Napa Extend | niplexitment | nipa extend |
| Zero-shot TrOCR Base | both_wrong_near_miss | 110.png | Baclofen | Bacilden . | Bac.lefen . |
| Tesseract 5.5.1 | data5_recovers_data4_failure | 50.png | Axodin | Medi | Axodin |
| Tesseract 5.5.1 | data5_recovers_data4_failure | 60.png | Azithrocin | kth | Azithrocin |
| Tesseract 5.5.1 | data5_recovers_data4_failure | 70.png | Azyth | Azuth | Azyth |
| Tesseract 5.5.1 | data4_recovers_data5_failure | 82.png | Az | Az. | f\ |
| Tesseract 5.5.1 | data4_recovers_data5_failure | 243.png | Disopan | Disopan | Dicopan |
| Tesseract 5.5.1 | data4_recovers_data5_failure | 671.png | Ritch | Ritch | Ri+ch |
| Tesseract 5.5.1 | both_wrong_near_miss | 61.png | Azithrocin | Ai | cAzithrocin |
| Tesseract 5.5.1 | both_wrong_near_miss | 113.png | Baclofen | (empty) | Bachofen |
| Tesseract 5.5.1 | both_wrong_near_miss | 163.png | Canazole | nce | CanazOole |

Examples are selected deterministically from paired test rows and use different ground-truth labels within each example type when available.

## Egyptian Catalog Filter and Generated Search Set

Only `7` of `78` source labels resolve uniquely and exactly to the Egyptian medicine catalog. The eligible classes are `Baclofen`, `Conaz`, `Flexilax`, `Ketoral`, `Maxpro`, `Rivotril`, and `Telfast`. No fuzzy catalog suggestion was promoted to ground truth.

| Generation result | Rows |
| --- | --- |
| OCR observations considered | 6240 |
| Catalog-mapped test observations before error filters | 560 |
| Accepted observation cases | 300 |
| Unique query-target pairs | 231 |
| Rejected observations | 5940 |
| Dangerous real-drug collisions retained | 2 |

The 560 pre-filter observations are `7 mapped test classes x 10 images x 2 representations x 4 OCR systems`. The accepted cases are OCR errors only; exact OCR output is intentionally excluded from the search-recovery test.

### Accepted Cases by Representation

| Representation | Accepted cases |
| --- | --- |
| data4_processed84 | 145 |
| data5_original | 155 |

### Accepted Cases by OCR System

| OCR run | Accepted cases |
| --- | --- |
| paddleocr_v6_data4_processed84 | 48 |
| trocr_base_zero_shot_data5_original | 47 |
| trocr_base_rxhandbd_finetuned_data4_processed84 | 42 |
| trocr_base_zero_shot_data4_processed84 | 41 |
| paddleocr_v6_data5_original | 39 |
| tesseract_lstm_data5_original | 35 |
| trocr_base_rxhandbd_finetuned_data5_original | 34 |
| tesseract_lstm_data4_processed84 | 14 |

### Accepted Cases by Expected Egyptian Family

| Expected family | Accepted cases |
| --- | --- |
| CONAZ | 62 |
| TELFAST | 52 |
| RIVOTRIL | 45 |
| KETORAL | 43 |
| BACLOFEN | 41 |
| FLEXILAX | 37 |
| MAX PRO | 20 |

### Rejections

| Reason | Rows |
| --- | --- |
| empty_ocr_output | 10 |
| extreme_distance_requires_manual_review | 133 |
| ground_truth_not_uniquely_catalog_resolved | 5680 |
| ocr_exact_match_not_an_error_case | 117 |

### Accepted Mistake Types

| Mistake type | Rows |
| --- | --- |
| multi_edit_ocr_error | 38 |
| real_drug_name_collision | 2 |
| single_edit_ocr_error | 98 |
| two_or_three_edit_ocr_error | 160 |
| visible_internal_fragment | 1 |
| visible_prefix_or_suffix_fragment | 1 |

### Dangerous Accepted Collisions

| OCR system | Image | OCR input | Expected | Input is real family |
| --- | --- | --- | --- | --- |
| tesseract_lstm_data4_processed84 | 194.png | (nat | CONAZ | NAT |
| trocr_base_zero_shot_data5_original | 680.png | first , | RIVOTRIL | FIRST |

These rows are not ordinary spelling errors. The OCR output is itself another real catalog family, so blindly trusting an exact database hit would produce the wrong medicine.

## Downstream Search Results

| Algorithm | Cases | Hit@1 | Hit@5 | Hit@20 | MRR@20 | Unsafe top-1 | Mean ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| algorithm_1_current_app | 300 | 31.33% | 38.33% | 46.33% | 0.344 | 0.00% | 2.21 |
| algorithm_2_external_fast | 300 | 55.67% | 70.33% | 76.33% | 0.621 | 0.00% | 20.50 |
| algorithm_3_rank_fusion | 300 | 55.67% | 70.33% | 76.33% | 0.621 | 0.00% | 21.00 |
| algorithm_4_family_rescue | 300 | 55.67% | 70.33% | 76.33% | 0.621 | 0.00% | 20.33 |

Algorithms 2, 3, and 4 had identical ranked retrieval on `300` of `300` compared cases. Their response/safety decisions were identical on `300` cases. This narrow seven-class subset therefore does not distinguish the later fusion/rescue logic; it only shows that all three recover the same candidates here.

## What The Result Means

- Use folder 5 originals as the primary OCR input. Folder 4 remains useful as a controlled degraded representation.
- PaddleOCR is the strongest frozen recognizer on these original crops, while the RxHandBD-tuned TrOCR model does not transfer as well to this source.
- The 780-image OCR result is valid across all 78 classes. The 300-case search result is much narrower because only seven classes have verified Egyptian-catalog targets.
- Do not report 9,360 independent images or 1,560 independent test images. They are paired representations of 4,680 source samples and 780 test samples.
- The benchmark contains isolated word crops, not complete prescription pages. Full pages still require detection/segmentation before recognition.
- Folder source metadata is not present in the local export, so this report does not claim patient/site provenance beyond what the files prove.

## Reproducibility Outputs

- `ocr_metrics.csv`: all eight OCR configuration summaries.
- `ocr_metrics_by_class.csv`: every OCR system/representation/class bucket.
- `representation_pairwise.csv`: paired improvements and regressions.
- `representative_examples.csv`: deterministic paired examples.
- `artifacts/02_data4_data5/search_cases.csv`: accepted and rejected OCR-derived observations.
- `artifacts/02_data4_data5/search_results.csv`: row-level Algorithms 1-4 results.
- `results/02_data4_data5/search_metrics.csv`: aggregate Algorithms 1-4 results.
- `analysis_summary.json`: machine-readable reconciliation summary.

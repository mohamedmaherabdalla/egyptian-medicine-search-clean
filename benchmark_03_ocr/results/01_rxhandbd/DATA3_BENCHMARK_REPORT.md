# Data 3: Real Handwritten Prescription OCR Benchmark

## Executive Summary

Data 3 evaluates three different questions separately: raw handwriting OCR, medicine-search recovery from real OCR errors, and the end-to-end image-to-medicine outcome. It does not merge these into one misleading accuracy number.

- RxHandBD rows audited: `5,578`.
- Official train/test split: `4,463` / `1,115`.
- Unique normalized labels: `1,516`.
- OCR observations / source-valid scored rows: `5,577` / `5,568`.
- Exact, unique Egyptian commercial-family mappings: `132`.
- Exact mapped rows in the official test split: `22`.
- Separate exact ingredient-query rows: `222`.
- Accepted OCR-error observations: `248`.
- Unique accepted query/target pairs: `222`.
- Cross-file validation: `PASS`.

The small catalog overlap is a measured limitation: the complete RxHandBD dataset remains valid for OCR evaluation, while only verified Egyptian matches enter the search benchmark.

## Benchmark Pipeline

```mermaid
flowchart LR
  A[RxHandBD word image] --> B[OCR model]
  B --> C[OCR transcription metrics]
  B --> D{Verified Egyptian family?}
  D -- No --> E[Rejected with reason or mapping review]
  D -- Yes --> F{Realistic wrong OCR output?}
  F -- No --> G[Exact, empty, or extreme audit class]
  F -- Yes --> H[Algorithms 1-4]
  H --> I[Hit@K, MRR, safety, latency]
```

## Evidence-Led OCR Upgrade

The upgrade was selected in stages rather than by trying one model on the official test set. Image profiling first identified large white margins, variable contrast, and a strong accuracy decline as labels became longer. Preprocessing and model candidates were then screened on training rows, checked on a disjoint training-validation split, and only promoted when they passed the frozen rule. The official test split remained unused for selection and training.

| Decision stage | Input | Output used for the next decision |
| --- | --- | --- |
| Image audit | 5,578 RxHandBD crops | Ink geometry, contrast, sharpness, label length, and baseline failure buckets |
| Preprocessing screen | 600 deterministic training rows | Raw, autocontrast, crop, and crop+autocontrast comparisons |
| Disjoint validation | 1,000 training rows excluded from fine-tuning | Repeated preprocessing gain and zero-shot candidate comparison |
| Domain fine-tuning | 3,457 train rows | Best checkpoint chosen by exact accuracy then CER |
| Frozen full run | 5,577 OCR-eligible images | Primary all-data and official-test OCR results |

The research matrix in `docs/OCR_CANDIDATE_RESEARCH.md` covers TrOCR Base/Large, PaddleOCR, GOT-OCR2, Donut, DeepSeek-OCR, PaddleOCR-VL, Qwen2.5-VL, and commercial OCR APIs. Models blocked by incompatible input, unavailable hardware, credentials, or privacy approval are listed explicitly instead of receiving invented scores.

## Dataset Audit

| Check | Result |
| --- | ---: |
| Valid labeled rows | 5,578 |
| Blank labels | 1 |
| Nonblank uncertain-placeholder labels | 3 |
| Invalid images | 0 |
| Raw/ML pixel mismatches | 0 |
| Label disagreements | 0 |
| Cross-split duplicate image groups | 0 |
| Duplicate groups with conflicting labels | 3 |
| Conflicting-label rows excluded from scoring | 6 |
| Egyptian catalog families | 17,476 |

### Conflicting Duplicate Labels

These rows contain identical decoded pixels but different supplied labels. They are processed by OCR, retained for traceability, and excluded from accuracy denominators.

| Duplicate group | Supplied labels | Split |
| ---: | --- | --- |
| 13 | XYLIN; XYRIL | train |
| 16 | CARULCAL D; CORULCAL D | train |
| 19 | CALBO D; CALCOR D | train |

## Catalog Mapping Outcomes

| Mapping status | Rows |
| --- | ---: |
| mapped_exact | 132 |
| review_fuzzy | 1,714 |
| unresolved | 3,732 |

## OCR Results

| Model | Version | Preprocessing | Observed | Scored | Source excluded | Exact | WER | Mean CER | Empty | Mean latency |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| easyocr | easyocr 1.7.2 | raw | 5,577 | 5,568 | 9 | 3.05% | 96.95% | 0.6756 | 0.11% | 353.2 ms |
| paddleocr | PP-OCRv6_medium_rec; paddleocr 3.7.0; paddlepaddle 3.3.1 | raw | 5,577 | 5,568 | 9 | 26.83% | 73.17% | 0.3246 | 0.11% | 146.5 ms |
| tesseract_lstm | tesseract 5.5.1 | raw | 5,577 | 5,568 | 9 | 2.78% | 97.22% | 0.7297 | 5.55% | 130.2 ms |
| trocr_base_rxhandbd_finetuned | best@sha256:4190103673868de6dac91efc8794abb1f93211da20be74ecb15fa9711ed792dc | autocontrast | 5,577 | 5,568 | 9 | 60.65% | 39.35% | 0.1492 | 0.00% | 84.0 ms |
| trocr | microsoft/trocr-base-handwritten@eaacaf452b06415df8f10bb6fad3a4c11e609406 | raw | 5,577 | 5,568 | 9 | 23.06% | 76.94% | 0.3880 | 0.02% | 344.2 ms |

### Train-Only Model Selection

The promotion rule required a model to be within five exact-accuracy points of the best validated model and to contribute at least two percent unique exact recoveries. After domain fine-tuning, only the fine-tuned TrOCR checkpoint passed. Oracle unions are diagnostic upper bounds, not deployable scores.

| Model | Preprocessing | Validation rows | Exact | CER | Short exact | Medium exact | Long exact | Unique exact | Promoted |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| trocr_base_rxhandbd_finetuned | autocontrast | 1,000 | 56.10% | 0.1509 | 67.60% | 58.50% | 28.31% | 240 | YES |
| trocr_large_handwritten | raw | 1,000 | 27.60% | 0.2931 | 41.11% | 25.23% | 12.05% | 24 | NO |
| paddleocr_v6_medium | ink_crop_square_autocontrast | 1,000 | 27.40% | 0.2946 | 53.31% | 21.76% | 1.20% | 27 | NO |
| trocr_base_handwritten | autocontrast | 1,000 | 23.20% | 0.3605 | 39.37% | 19.56% | 7.23% | 11 | NO |

### Domain Fine-Tuning Curve

Training used `3,457` rows, validation used a disjoint `1,000` rows, and official-test rows used for selection were `0`. The frozen checkpoint SHA-256 is `4190103673868de6dac91efc8794abb1f93211da20be74ecb15fa9711ed792dc`.

| Stage | Validation exact | Validation CER | Mean training loss |
| --- | ---: | ---: | ---: |
| Zero-shot baseline | 23.20% | 0.3605 | -- |
| Epoch 1 | 50.80% | 0.1685 | 2.5727 |
| Epoch 2 | 54.10% | 0.1688 | 0.8761 |
| Epoch 3 | 56.10% | 0.1509 | 0.4677 |

### Training-Only Calibration and Smoke Tests

These small runs select a feasible configuration and catch adapter failures. They are not official benchmark scores and use different sample counts.

| Model | Version | Preprocessing | Rows | Exact | Mean normalized edit distance | Empty | Mean latency |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| donut | chinmays18/medical-prescription-ocr@ff8029288c4496b0581502a559706a3ef89e1878 | raw | 30 | 0.00% | 52.5934 | 6.67% | 8682.6 ms |
| easyocr | easyocr 1.7.2 | raw | 50 | 2.00% | 0.7213 | 0.00% | 270.7 ms |
| got_ocr2 | stepfun-ai/GOT-OCR-2.0-hf@d3017ef2c2c1395888c8d635c5e0508bcb0ac78d | raw | 20 | 20.00% | 0.3259 | 0.00% | 957.7 ms |
| paddleocr | en_PP-OCRv3_mobile_rec; paddleocr 3.7.0; paddlepaddle 3.3.1 | raw | 50 | 0.00% | 0.8262 | 0.00% | 42.3 ms |
| paddleocr | PP-OCRv6_medium_rec; paddleocr 3.7.0; paddlepaddle 3.3.1 | raw | 50 | 10.00% | 0.5310 | 0.00% | 121.0 ms |
| tesseract_lstm | tesseract 5.5.1 | autocontrast_2x | 200 | 0.00% | 0.7926 | 6.00% | 481.2 ms |
| tesseract_lstm | tesseract 5.5.1 | raw | 200 | 0.00% | 0.7831 | 7.00% | 127.6 ms |
| tesseract_lstm | tesseract 5.5.1 | sharpen_2x | 200 | 0.00% | 0.7832 | 6.50% | 591.3 ms |
| tesseract_lstm | tesseract 5.5.1 | threshold_2x | 200 | 0.00% | 0.7930 | 10.00% | 129.3 ms |
| trocr_large_handwritten | microsoft/trocr-large-handwritten@e68501f437cd2587ae5d68ee457964cac824ddee | raw | 20 | 15.00% | 0.4372 | 0.00% | 256.7 ms |
| trocr | microsoft/trocr-base-handwritten@eaacaf452b06415df8f10bb6fad3a4c11e609406 | raw | 10 | 20.00% | 0.5529 | 0.00% | 839.7 ms |

### Secondary Full Configurations (Excluded from Primary Aggregate)

| Model | Version | Rows | Exact | Mean normalized edit distance | Empty | Mean latency |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| paddleocr | en_PP-OCRv3_mobile_rec; paddleocr 3.7.0; paddlepaddle 3.3.1 | 5,577 | 5.00% | 0.6516 | 0.50% | 54.6 ms |

### Official Test Split

| Model | Rows | Exact | CER | WER | Empty | Median latency | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| easyocr | 1,111 | 1.98% | 0.6709 | 98.02% | 0.00% | 264.0 ms | 416.3 ms |
| paddleocr | 1,111 | 29.61% | 0.3595 | 70.39% | 0.00% | 119.2 ms | 122.7 ms |
| tesseract_lstm | 1,111 | 0.72% | 0.7380 | 99.28% | 4.50% | 124.3 ms | 149.8 ms |
| trocr | 1,111 | 19.62% | 0.4658 | 80.38% | 0.00% | 312.9 ms | 472.5 ms |
| trocr_base_rxhandbd_finetuned | 1,111 | 45.36% | 0.2799 | 54.64% | 0.00% | 46.9 ms | 70.2 ms |

### Official-Test Label Novelty

A test label is `seen_in_train` when the same compact transcription occurs anywhere in the fine-tuning split. The unseen rows are the stricter vocabulary-generalization check.

| Model | Test-label group | Rows | Exact | CER |
| --- | --- | ---: | ---: | ---: |
| easyocr | seen_in_train | 691 | 2.60% | 0.6627 |
| easyocr | unseen_in_train | 420 | 0.95% | 0.6844 |
| paddleocr | seen_in_train | 691 | 30.10% | 0.3656 |
| paddleocr | unseen_in_train | 420 | 28.81% | 0.3495 |
| tesseract_lstm | seen_in_train | 691 | 1.16% | 0.7300 |
| tesseract_lstm | unseen_in_train | 420 | 0.00% | 0.7512 |
| trocr | seen_in_train | 691 | 21.13% | 0.4759 |
| trocr | unseen_in_train | 420 | 17.14% | 0.4491 |
| trocr_base_rxhandbd_finetuned | seen_in_train | 691 | 52.97% | 0.2630 |
| trocr_base_rxhandbd_finetuned | unseen_in_train | 420 | 32.86% | 0.3078 |

### Promoted-Model Input/Output Examples

These examples come only from the untouched official test split and are selected by deterministic rules. They show both improvements and remaining errors; they are not hand-picked success cases.

| Type | Image input | Expected text | Promoted output | Comparator outputs | Novelty |
| --- | --- | --- | --- | --- | --- |
| candidate_unique_exact | `P0001.jpg` | `Nexcital` | `Nexcital` | easyocr=Nuxcuku; paddleocr=Nixcitus; tesseract_lstm=M vertu; trocr=mexcitane | unseen_in_train |
| candidate_unique_exact | `P0005.jpg` | `Rivotril` | `Rivotril` | easyocr=Rnoa]; paddleocr=Rivothal; tesseract_lstm=Rito; trocr=rivotal | seen_in_train |
| candidate_unique_exact | `P0013.jpg` | `T-Cef` | `T-cef` | easyocr=Taly; paddleocr=T-luf; tesseract_lstm=jolif; trocr=tales . | unseen_in_train |
| candidate_fixed_zero_shot_base | `P0008.jpg` | `Econate` | `Econate` | easyocr=fxomk; paddleocr=Econate; tesseract_lstm=Fora; trocr=economic | unseen_in_train |
| candidate_fixed_zero_shot_base | `P0014.jpg` | `Algin` | `Algin` | easyocr=Hjn; paddleocr=Algin; tesseract_lstm=Ht wn,; trocr=afgin . | seen_in_train |
| candidate_fixed_zero_shot_base | `P0015.jpg` | `Dexter` | `Dexter` | easyocr=Jexhx; paddleocr=sextre; tesseract_lstm=yer; trocr=despite | seen_in_train |
| candidate_regressed_vs_zero_shot_base | `P0524.jpg` | `kindical D` | `kindicalf D` | easyocr=KM An); paddleocr=kindalb; tesseract_lstm=kel; trocr=kindicald . | unseen_in_train |
| candidate_regressed_vs_zero_shot_base | `P0155.jpg` | `Follison` | `Follisou` | easyocr=Folku; paddleocr=Follsou; tesseract_lstm=Falla; trocr=follison . | seen_in_train |
| candidate_regressed_vs_zero_shot_base | `P0415.jpg` | `Coraleal` | `Coralcal` | easyocr=Qoxksal; paddleocr=Coaleal; tesseract_lstm=( roll; trocr=coraleal | unseen_in_train |
| candidate_near_miss_all_models_wrong | `P0206.jpg` | `Ecosprin Plus` | `Ecosprin plas` | easyocr=Lwupnl; paddleocr=Cuspry puo; tesseract_lstm=pi; trocr=ecosponsion plans | seen_in_train |
| candidate_near_miss_all_models_wrong | `P0202.jpg` | `Brezofil 200` | `Brazofil 200` | easyocr=BuzdV #; paddleocr=Breeof200; tesseract_lstm=Bia tu; trocr=boezofil 200 | unseen_in_train |
| candidate_near_miss_all_models_wrong | `P0216.jpg` | `TRD Coutine` | `TRD Coutive` | easyocr=IPN O; paddleocr=TRDCutic; tesseract_lstm=eb ity; trocr=tredcontine . | unseen_in_train |
| all_models_severe_failure | `P0424.jpg` | `Atoz` | `AtoZ premiumium` | easyocr=Aw p; paddleocr=Ato panicy; tesseract_lstm=An ig; trocr=atoz premiuming | unseen_in_train |
| all_models_severe_failure | `P0231.jpg` | `Atoz` | `Atoz premiumium` | easyocr=M2 PVnrwr; paddleocr=Ate poariny; tesseract_lstm=ltt); trocr=atmospassing | unseen_in_train |
| all_models_severe_failure | `P0021.jpg` | `Napa` | `Galactotomha` | easyocr=(olumw; paddleocr=Goviltonho; tesseract_lstm=‘ian; trocr=guillactomimica | seen_in_train |

## Model Execution Status

| System | Type | Independent | Status | Rows | Reason or scope |
| --- | --- | ---: | --- | ---: | --- |
| Tesseract 5 LSTM | open_source | 1 | complete | 5,577 | RxHandBD word-level benchmark. |
| Microsoft TrOCR Base Handwritten (zero-shot) | open_source | 1 | complete | 5,577 | RxHandBD word-level benchmark. |
| Microsoft TrOCR Base fine-tuned on RxHandBD | open_source_domain_finetuned | 1 | complete | 5,577 | Promoted after a 600-row screen and disjoint 1,000-row train validation; full RxHandBD run. |
| EasyOCR 1.7 | open_source | 1 | complete | 5,577 | RxHandBD word-level benchmark. |
| PaddleOCR PP-OCRv6 English recognition | open_source | 1 | complete | 5,577 | RxHandBD word-level benchmark. |
| Microsoft TrOCR Large Handwritten | open_source | 1 | validation_complete_not_promoted | 1,000 | Validated on 1,000 disjoint training rows; 27.60% exact, below the final promotion band. |
| GOT-OCR2 580M | open_source | 1 | screen_complete_not_promoted | 600 | 600-row screen: 23.33% exact and about 744 ms/image; failed accuracy and latency promotion criteria. |
| PaddleOCR English v3 mobile (secondary) | open_source_secondary_configuration | 0 | complete_excluded_from_primary_aggregate | 5,577 | Same PaddleOCR family; v6 medium won the training-only model-selection pilot. |
| chinmays18 medical-prescription Donut | open_source_medical | 1 | input_mismatch_pilot_complete | 30 | Pilot only: RxHandBD contains isolated word crops, while the model is intended for full prescription documents. It is excluded from the primary comparison. |
| JonSnow Medical-Prescription-OCR | open_source_wrapper | 0 | not_counted_duplicate_model | 0 | Wrapper uses the same chinmays18 Donut checkpoint. |
| David-Magdy OCR pipeline | open_source_medical_pipeline | 1 | blocked_missing_full_page_input | 0 | Requires separate raw-OCR and post-SymSpell evaluation on full pages. |
| DeepSeek-OCR | open_source_document_vlm | 1 | blocked_incompatible_local_backend | 0 | Official execution path is CUDA-oriented; the benchmark host is Apple MPS and the task is an isolated word crop. |
| PaddleOCR-VL | open_source_document_vlm | 1 | not_run_input_and_backend_mismatch | 0 | Page-structure parsing is not comparable to recognition-only word crops; the supported local backend is not Apple MPS. |
| Qwen2.5-VL | open_source_general_vlm | 1 | researched_not_promoted_to_execution | 0 | Not a handwriting-specialist checkpoint; GOT-OCR2 represented the general OCR/VLM screen and failed promotion. |
| Google Vision | commercial_api | 1 | blocked_credentials_and_privacy_approval | 0 | Requires API credentials and an approved deidentified common sample. |
| Azure Document Intelligence Read | commercial_api | 1 | blocked_credentials_and_privacy_approval | 0 | Requires API credentials and an approved deidentified common sample. |
| Amazon Textract | commercial_api | 1 | blocked_credentials_and_privacy_approval | 0 | Requires API credentials and an approved deidentified common sample. |
| Koncile Prescription OCR | commercial_api | 1 | blocked_credentials_and_privacy_approval | 0 | Requires API credentials and an approved deidentified common sample. |

## Search-Case Filtering

Only unique exact catalog mappings are automatic ground truth. Fuzzy catalog matches remain review suggestions. Wrong OCR outputs that exactly equal another real Egyptian family are preserved as dangerous collision cases.

| Outcome | Count |
| --- | ---: |
| Accepted OCR observations | 248 |
| Accepted official-test observations | 36 |
| Dangerous real-drug collisions | 0 |
| Rejected observations | 27,637 |

### Rejection Breakdown

| Reason | Rows |
| --- | ---: |
| empty_ocr_output | 3 |
| extreme_distance_requires_manual_review | 236 |
| ground_truth_not_uniquely_catalog_resolved | 27,180 |
| ocr_exact_match_not_an_error_case | 173 |
| source_ground_truth_excluded:duplicate_pixels_conflicting_ground_truth | 30 |
| source_ground_truth_excluded:uncertain_ground_truth_placeholder | 15 |

### Accepted Mistake Types

| Mistake type | Rows |
| --- | ---: |
| multi_edit_ocr_error | 53 |
| single_edit_ocr_error | 77 |
| two_or_three_edit_ocr_error | 115 |
| visible_prefix_or_suffix_fragment | 3 |

## Search Results

| Algorithm | Cases | Hit@1 | Hit@5 | Hit@20 | MRR@20 | Unsafe confident top-1 | Mean latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| algorithm_1_current_app | 248 | 26.61% | 38.31% | 45.16% | 0.3148 | 0.00% | 1.53 ms |
| algorithm_2_external_fast | 248 | 60.08% | 76.21% | 84.27% | 0.6632 | 0.00% | 20.10 ms |
| algorithm_3_rank_fusion | 248 | 60.08% | 76.21% | 84.27% | 0.6632 | 0.00% | 20.27 ms |
| algorithm_4_family_rescue | 248 | 60.08% | 76.21% | 84.27% | 0.6632 | 0.00% | 20.21 ms |

Algorithms 2, 3, and 4 returned identical top-20 lists and decision states on `248` of `248` accepted cases. Their tie is genuine for this narrow subset, but the subset does not discriminate their broader ranking behavior.

### Search Results by Split and OCR Model

| Algorithm | Scope | Cases | Hit@1 | Hit@20 | MRR@20 | Unsafe |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| algorithm_1_current_app | ocr:easyocr | 36 | 8.33% | 16.67% | 0.1134 | 0.00% |
| algorithm_1_current_app | ocr:paddleocr | 87 | 25.29% | 43.68% | 0.2958 | 0.00% |
| algorithm_1_current_app | ocr:tesseract_lstm | 18 | 11.11% | 33.33% | 0.1594 | 0.00% |
| algorithm_1_current_app | ocr:trocr | 72 | 31.94% | 51.39% | 0.3686 | 0.00% |
| algorithm_1_current_app | ocr:trocr_base_rxhandbd_finetuned | 35 | 45.71% | 71.43% | 0.5384 | 0.00% |
| algorithm_1_current_app | split:test | 36 | 30.56% | 55.56% | 0.3622 | 0.00% |
| algorithm_1_current_app | split:train | 212 | 25.94% | 43.40% | 0.3068 | 0.00% |
| algorithm_2_external_fast | ocr:easyocr | 36 | 30.56% | 75.00% | 0.4233 | 0.00% |
| algorithm_2_external_fast | ocr:paddleocr | 87 | 57.47% | 79.31% | 0.6332 | 0.00% |
| algorithm_2_external_fast | ocr:tesseract_lstm | 18 | 27.78% | 55.56% | 0.3639 | 0.00% |
| algorithm_2_external_fast | ocr:trocr | 72 | 72.22% | 94.44% | 0.7728 | 0.00% |
| algorithm_2_external_fast | ocr:trocr_base_rxhandbd_finetuned | 35 | 88.57% | 100.00% | 0.9134 | 0.00% |
| algorithm_2_external_fast | split:test | 36 | 63.89% | 88.89% | 0.6965 | 0.00% |
| algorithm_2_external_fast | split:train | 212 | 59.43% | 83.49% | 0.6576 | 0.00% |
| algorithm_3_rank_fusion | ocr:easyocr | 36 | 30.56% | 75.00% | 0.4233 | 0.00% |
| algorithm_3_rank_fusion | ocr:paddleocr | 87 | 57.47% | 79.31% | 0.6332 | 0.00% |
| algorithm_3_rank_fusion | ocr:tesseract_lstm | 18 | 27.78% | 55.56% | 0.3639 | 0.00% |
| algorithm_3_rank_fusion | ocr:trocr | 72 | 72.22% | 94.44% | 0.7728 | 0.00% |
| algorithm_3_rank_fusion | ocr:trocr_base_rxhandbd_finetuned | 35 | 88.57% | 100.00% | 0.9134 | 0.00% |
| algorithm_3_rank_fusion | split:test | 36 | 63.89% | 88.89% | 0.6965 | 0.00% |
| algorithm_3_rank_fusion | split:train | 212 | 59.43% | 83.49% | 0.6576 | 0.00% |
| algorithm_4_family_rescue | ocr:easyocr | 36 | 30.56% | 75.00% | 0.4233 | 0.00% |
| algorithm_4_family_rescue | ocr:paddleocr | 87 | 57.47% | 79.31% | 0.6332 | 0.00% |
| algorithm_4_family_rescue | ocr:tesseract_lstm | 18 | 27.78% | 55.56% | 0.3639 | 0.00% |
| algorithm_4_family_rescue | ocr:trocr | 72 | 72.22% | 94.44% | 0.7728 | 0.00% |
| algorithm_4_family_rescue | ocr:trocr_base_rxhandbd_finetuned | 35 | 88.57% | 100.00% | 0.9134 | 0.00% |
| algorithm_4_family_rescue | split:test | 36 | 63.89% | 88.89% | 0.6965 | 0.00% |
| algorithm_4_family_rescue | split:train | 212 | 59.43% | 83.49% | 0.6576 | 0.00% |

### Search Results by OCR Difficulty

| Algorithm | Difficulty | Cases | Hit@1 | Hit@5 | Hit@20 | MRR@20 | Unsafe |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| algorithm_1_current_app | EASY | 79 | 62.03% | 79.75% | 88.61% | 0.6800 | 0.00% |
| algorithm_1_current_app | HARD | 66 | 0.00% | 0.00% | 6.06% | 0.0070 | 0.00% |
| algorithm_1_current_app | MEDIUM | 103 | 16.50% | 31.07% | 36.89% | 0.2319 | 0.00% |
| algorithm_2_external_fast | EASY | 79 | 98.73% | 100.00% | 100.00% | 0.9916 | 0.00% |
| algorithm_2_external_fast | HARD | 66 | 15.15% | 31.82% | 59.09% | 0.2192 | 0.00% |
| algorithm_2_external_fast | MEDIUM | 103 | 59.22% | 86.41% | 88.35% | 0.6960 | 0.00% |
| algorithm_3_rank_fusion | EASY | 79 | 98.73% | 100.00% | 100.00% | 0.9916 | 0.00% |
| algorithm_3_rank_fusion | HARD | 66 | 15.15% | 31.82% | 59.09% | 0.2192 | 0.00% |
| algorithm_3_rank_fusion | MEDIUM | 103 | 59.22% | 86.41% | 88.35% | 0.6960 | 0.00% |
| algorithm_4_family_rescue | EASY | 79 | 98.73% | 100.00% | 100.00% | 0.9916 | 0.00% |
| algorithm_4_family_rescue | HARD | 66 | 15.15% | 31.82% | 59.09% | 0.2192 | 0.00% |
| algorithm_4_family_rescue | MEDIUM | 103 | 59.22% | 86.41% | 88.35% | 0.6960 | 0.00% |

### Search Results by OCR Mistake Type

| Algorithm | Mistake type | Cases | Hit@1 | Hit@20 | MRR@20 | Unsafe | Clarification |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| algorithm_1_current_app | multi_edit_ocr_error | 53 | 0.00% | 0.00% | 0.0000 | 0.00% | 84.91% |
| algorithm_1_current_app | single_edit_ocr_error | 77 | 49.35% | 76.62% | 0.5599 | 0.00% | 98.70% |
| algorithm_1_current_app | two_or_three_edit_ocr_error | 115 | 21.74% | 43.48% | 0.2779 | 0.00% | 95.65% |
| algorithm_1_current_app | visible_prefix_or_suffix_fragment | 3 | 100.00% | 100.00% | 1.0000 | 0.00% | 100.00% |
| algorithm_2_external_fast | multi_edit_ocr_error | 53 | 28.30% | 62.26% | 0.3382 | 0.00% | 100.00% |
| algorithm_2_external_fast | single_edit_ocr_error | 77 | 93.51% | 96.10% | 0.9437 | 0.00% | 100.00% |
| algorithm_2_external_fast | two_or_three_edit_ocr_error | 115 | 51.30% | 86.09% | 0.6164 | 0.00% | 100.00% |
| algorithm_2_external_fast | visible_prefix_or_suffix_fragment | 3 | 100.00% | 100.00% | 1.0000 | 0.00% | 100.00% |
| algorithm_3_rank_fusion | multi_edit_ocr_error | 53 | 28.30% | 62.26% | 0.3382 | 0.00% | 100.00% |
| algorithm_3_rank_fusion | single_edit_ocr_error | 77 | 93.51% | 96.10% | 0.9437 | 0.00% | 100.00% |
| algorithm_3_rank_fusion | two_or_three_edit_ocr_error | 115 | 51.30% | 86.09% | 0.6164 | 0.00% | 100.00% |
| algorithm_3_rank_fusion | visible_prefix_or_suffix_fragment | 3 | 100.00% | 100.00% | 1.0000 | 0.00% | 100.00% |
| algorithm_4_family_rescue | multi_edit_ocr_error | 53 | 28.30% | 62.26% | 0.3382 | 0.00% | 100.00% |
| algorithm_4_family_rescue | single_edit_ocr_error | 77 | 93.51% | 96.10% | 0.9437 | 0.00% | 100.00% |
| algorithm_4_family_rescue | two_or_three_edit_ocr_error | 115 | 51.30% | 86.09% | 0.6164 | 0.00% | 100.00% |
| algorithm_4_family_rescue | visible_prefix_or_suffix_fragment | 3 | 100.00% | 100.00% | 1.0000 | 0.00% | 100.00% |

### Search Results by Safety Label

| Algorithm | Danger | Cases | Hit@1 | Hit@20 | Unsafe | Clarification |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| algorithm_1_current_app | CAUTION | 79 | 1.27% | 8.86% | 0.00% | 93.67% |
| algorithm_1_current_app | SAFE | 169 | 38.46% | 62.13% | 0.00% | 94.67% |
| algorithm_2_external_fast | CAUTION | 79 | 22.78% | 62.03% | 0.00% | 100.00% |
| algorithm_2_external_fast | SAFE | 169 | 77.51% | 94.67% | 0.00% | 100.00% |
| algorithm_3_rank_fusion | CAUTION | 79 | 22.78% | 62.03% | 0.00% | 100.00% |
| algorithm_3_rank_fusion | SAFE | 169 | 77.51% | 94.67% | 0.00% | 100.00% |
| algorithm_4_family_rescue | CAUTION | 79 | 22.78% | 62.03% | 0.00% | 100.00% |
| algorithm_4_family_rescue | SAFE | 169 | 77.51% | 94.67% | 0.00% | 100.00% |

## End-to-End Image-to-Medicine Results

This table includes every uniquely catalog-mapped OCR observation, including exact OCR, empty output, and severe corruption. It therefore answers a different question from OCR-error recovery.

| Algorithm | Cases | Hit@1 | Hit@5 | Hit@20 | MRR@20 | Unsafe confident top-1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| algorithm_1_current_app | 660 | 36.21% | 40.61% | 43.18% | 0.3804 | 0.00% |
| algorithm_2_external_fast | 660 | 48.79% | 55.00% | 58.03% | 0.5121 | 0.00% |
| algorithm_3_rank_fusion | 660 | 48.79% | 55.00% | 58.03% | 0.5121 | 0.00% |
| algorithm_4_family_rescue | 660 | 48.79% | 55.00% | 58.03% | 0.5121 | 0.00% |

## Representative Accepted Cases

| OCR input | Expected Egyptian family | OCR model | Difficulty | Mistake type | Danger |
| --- | --- | --- | --- | --- | --- |
| `Ckexane` | `CLEXANE` | easyocr | EASY | single_edit_ocr_error | SAFE |
| `Paracetamamol` | `PARACETAMOL` | trocr_base_rxhandbd_finetuned | EASY | two_or_three_edit_ocr_error | SAFE |
| `cetixime .` | `CEFIXIME` | trocr | EASY | single_edit_ocr_error | SAFE |
| `Rivotri!` | `RIVOTRIL` | paddleocr | EASY | visible_prefix_or_suffix_fragment | SAFE |
| `metropaganda` | `METRONIDAZOLE` | trocr | HARD | multi_edit_ocr_error | CAUTION |

## Interpretation Rules

- OCR exact accuracy measures transcription only; search cannot receive credit for OCR success.
- Same-pixel rows with contradictory source labels are processed but excluded from scoring; no label is guessed.
- Search recovery is measured only on wrong, non-empty OCR outputs with verified Egyptian targets.
- End-to-end success means the final search ranking contains the verified family after starting from the image.
- Results from RxHandBD training images and official test images are reported separately.
- No fuzzy catalog suggestion is accepted as ground truth without review.
- Model or API systems that could not be executed are listed in the execution-status table rather than omitted.
- The benchmark is publishable as an OCR study, but the Egyptian search-recovery subset remains exploratory until its verified overlap is materially larger.

## Validation Contract

Overall validation status: **PASS**.

| Validation check | Status | Expected rows | Actual rows |
| --- | --- | ---: | ---: |
| ocr_coverage:ocr_easyocr_raw_all.csv | PASS | 5,577 | 5,577 |
| ocr_coverage:ocr_paddleocr_raw_all.csv | PASS | 5,577 | 5,577 |
| ocr_coverage:ocr_tesseract_lstm_raw_all.csv | PASS | 5,577 | 5,577 |
| ocr_coverage:ocr_trocr_base_rxhandbd_finetuned_autocontrast_all.csv | PASS | 5,577 | 5,577 |
| ocr_coverage:ocr_trocr_raw_all.csv | PASS | 5,577 | 5,577 |
| search_cases_reconcile_with_ocr_observations | PASS | 27,885 | 27,885 |
| search_algorithm_coverage | PASS | 992 | 992 |
| end_to_end_algorithm_coverage | PASS | 2,640 | 2,640 |
| dataset_integrity | PASS | 0 | 0 |

## Known Limitations

- RxHandBD is a Bangladesh-oriented word-image dataset, so overlap with the Egyptian catalog is naturally limited.
- Word crops do not measure full-prescription text detection or layout understanding.
- The dataset does not provide writer identifiers, so writer-disjoint leakage cannot be independently verified.
- Commercial APIs require credentials, privacy approval, and an identical deidentified sample before comparison.
- Fuzzy mapping review can expand coverage later, but those rows must not enter the benchmark automatically.

## Reproduction

See `README.md` for the exact commands, dependency isolation, output contract, and execution-status policy.

# Testing Strategy

## Scope

This document describes how the generated commercial-name stress suite is tested and how the current static app is evaluated against it.

The current regenerated suite contains `341,901` cases:

- `inside`: `235,545`
- `semi_outside`: `51,325`
- `outside`: `55,031`

The distribution is intentionally hard-biased:

- `EASY`: `42`
- `MEDIUM`: `59,947`
- `HARD`: `253,178`
- `EXTREME`: `28,734`
- `HARD + EXTREME`: `82.45%`

This satisfies the explicit requirement that more than `60%` of the suite be hard/extreme rather than easy exact-match cases.

## Test Layers

| layer | command | purpose | result |
| --- | --- | --- | --- |
| Syntax check | `PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 -m compileall benchmark_01_legacy` | Confirms Python files parse. | Passed. |
| Unit tests | `PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 -m unittest discover -s benchmark_01_legacy -p 'test_*.py'` | Tests normalization, indexes, collision escalation, scoping, and validation gates. | Passed: `8` tests. |
| Data generation | `PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 benchmark_01_legacy/generate_commercial_name_test_cases.py` | Regenerates expanded/split CSVs and JSON summaries. | Passed: `341,901` rows, hard/extreme ratio `0.825`. |
| Search evaluation | `PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 benchmark_01_legacy/evaluate_current_app_search.py` | Evaluates current app ranking/safety over all split CSVs. | Passed: `341,901` evaluated cases. |
| External comparison | `PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 benchmark_01_legacy/evaluate_external_english_fast_search.py --workers 8 --chunk-size 250` | Evaluates the external English fast algorithm on the same split CSVs and compares it to current app metrics. | Passed: `341,901` evaluated cases. |

`PYTHONPYCACHEPREFIX` is used because the sandbox cannot write bytecode into the default macOS user cache path.

## Unit Test Coverage

Current unit tests are in `benchmark_01_legacy/test_case_generation/test_generation_unit.py`.

They cover:

- Arabic digit normalization.
- Compact-key punctuation stripping.
- Empty generated query rejection.
- Compact collision indexing.
- Ingredient-collision detection.
- Collision-based danger escalation.
- Scope mapping for generated categories.
- Hard/extreme ratio validation.

The tests are focused on generator correctness, not app ranking. Ranking behavior is covered by the integration evaluator.

## Validation Gates

The generator refuses to write outputs unless:

- All cases have non-empty `input` and `expected`.
- Difficulty labels are one of `EASY`, `MEDIUM`, `HARD`, `EXTREME`.
- Danger labels are one of `SAFE`, `CAUTION`, `DANGEROUS`.
- Every category maps to exactly one scope.
- No duplicate `(input, expected, error_type, category)` row exists.
- The hard/extreme ratio is at least `60%`.

The previous expanded artifact had a hard/extreme ratio of about `44.61%`; the regenerated suite is `82.45%`.

## Metric Definitions

| metric | formula / interpretation |
| --- | --- |
| `Hit@1` | Fraction of cases where the expected base appears as the first ranked result. |
| `Hit@5` | Fraction where expected appears anywhere in the top 5. |
| `Hit@10` | Fraction where expected appears anywhere in the top 10. |
| `Hit@20` | Fraction where expected appears anywhere in the top 20. |
| `MRR@20` | Mean reciprocal rank using rank position within top 20; zero if absent. |
| `MAP@20` | Mean average precision at 20 using expected-base relevance labels. |
| `nDCG@20` | Normalized discounted cumulative gain at 20. |
| `no_result_rate` | Fraction where the evaluator found no candidates. |
| `unsafe_confident_top1_rate` | Fraction where a wrong top-1 result was presented confidently for a dangerous/caution case. |
| `missing_clarification_rate` | Fraction where an ambiguous/safety-sensitive case should have triggered clarification but did not. |
| `avg_candidate_pool` | Mean number of candidates considered by the evaluator for the category. |

## Headline Evaluation Result

The current app evaluator completed in `1680.89` seconds when writing the full row-level audit table.

| scope | cases | Hit@1 | Hit@5 | Hit@10 | Hit@20 | MRR@20 | unsafe top1 | missing clarification |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `inside` | 235,545 | 78.38% | 87.08% | 90.10% | 92.56% | 0.8223 | 0.00% | 0.00% |
| `outside` | 55,031 | 87.15% | 94.44% | 96.56% | 98.37% | 0.9038 | 0.00% | 0.02% |
| `semi_outside` | 51,325 | 98.12% | 99.71% | 99.82% | 99.87% | 0.9882 | 0.00% | 0.00% |
| `__ALL__` | 341,901 | 82.76% | 90.16% | 92.60% | 94.59% | 0.8603 | 0.00% | 0.00% |

The exact machine-readable result files are:

- `benchmark_01_legacy/artifacts/01_current_app/case_results.csv`: one row for every evaluated test case, including `input`, `expected`, `first_rank`, Hit@k flags, top-1 fields, top-5 bases, and safety flags.
- `benchmark_01_legacy/results/01_current_app/metrics_by_category.csv`: aggregate scores by scope/category.
- `benchmark_01_legacy/results/01_current_app/metrics_by_error_type.csv`: aggregate scores by scope/category/error_type for diagnosing the exact mutation type that failed.

## Full Category Score Table

| scope | category | cases | Hit@1 | Hit@5 | Hit@10 | Hit@20 | MRR@20 | MAP@20 | nDCG@20 | no result | unsafe top1 | missing clarification | avg pool |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `inside` | `all_position_deletion_full_catalog` | 25,000 | 65.42% | 77.06% | 82.21% | 87.13% | 0.7072 | 0.7053 | 0.7433 | 0.41% | 0.00% | 0.00% | 84.0 |
| `inside` | `all_position_transposition_full_catalog` | 20,000 | 89.23% | 93.48% | 94.67% | 95.45% | 0.9107 | 0.9018 | 0.9136 | 0.60% | 0.00% | 0.00% | 39.1 |
| `inside` | `arabic_dot_confusion` | 29 | 6.90% | 10.34% | 10.34% | 13.79% | 0.0882 | 0.0599 | 0.0741 | 75.86% | 0.00% | 0.00% | 102.5 |
| `inside` | `c_k_q_interchange` | 72 | 68.06% | 68.06% | 69.44% | 69.44% | 0.6821 | 0.6821 | 0.6847 | 2.78% | 0.00% | 0.00% | 56.0 |
| `inside` | `consonant_skeleton` | 84 | 82.14% | 90.48% | 91.67% | 95.24% | 0.8549 | 0.8595 | 0.8806 | 0.00% | 0.00% | 0.00% | 41.1 |
| `inside` | `consonant_skeleton_expanded_catalog` | 12,000 | 80.47% | 88.78% | 91.41% | 93.73% | 0.8419 | 0.8351 | 0.8587 | 0.59% | 0.00% | 0.00% | 18.3 |
| `inside` | `cross_script` | 30 | 3.33% | 3.33% | 3.33% | 6.67% | 0.0364 | 0.0109 | 0.0191 | 93.33% | 0.00% | 0.00% | 31.7 |
| `inside` | `digraph_soundalike_catalog` | 3,000 | 65.07% | 85.20% | 89.47% | 91.73% | 0.7335 | 0.7327 | 0.7769 | 0.10% | 0.00% | 0.00% | 27.4 |
| `inside` | `double_letter` | 24 | 45.83% | 50.00% | 50.00% | 50.00% | 0.4792 | 0.4452 | 0.4544 | 0.00% | 0.00% | 0.00% | 177.8 |
| `inside` | `duplicate_syllable_catalog` | 5,000 | 88.88% | 90.54% | 90.60% | 90.60% | 0.8963 | 0.8895 | 0.8928 | 2.76% | 0.00% | 0.00% | 51.2 |
| `inside` | `initial_sound_confusion_full_catalog` | 14,125 | 92.84% | 97.02% | 97.95% | 98.55% | 0.9463 | 0.9369 | 0.9477 | 0.35% | 0.00% | 0.00% | 56.0 |
| `inside` | `keyboard_adjacent` | 898 | 69.15% | 81.63% | 86.64% | 88.98% | 0.7429 | 0.7777 | 0.8076 | 0.22% | 0.00% | 0.00% | 70.8 |
| `inside` | `keyboard_adjacent_expanded_catalog` | 22,000 | 71.19% | 84.48% | 88.85% | 91.91% | 0.7701 | 0.7672 | 0.8024 | 0.56% | 0.00% | 0.00% | 45.7 |
| `inside` | `keyboard_shift_whole_word_catalog` | 7,000 | 57.49% | 76.36% | 81.67% | 84.07% | 0.6547 | 0.6518 | 0.6964 | 11.16% | 0.00% | 0.00% | 15.1 |
| `inside` | `letter_insertion` | 42 | 57.14% | 83.33% | 88.10% | 95.24% | 0.6780 | 0.7357 | 0.7923 | 0.00% | 0.00% | 0.00% | 45.4 |
| `inside` | `ligature_confusion` | 250 | 23.60% | 43.60% | 52.80% | 63.60% | 0.3310 | 0.3376 | 0.4040 | 2.40% | 0.00% | 0.00% | 94.8 |
| `inside` | `mirror_letter_confusion` | 80 | 55.00% | 67.50% | 70.00% | 72.50% | 0.5976 | 0.6062 | 0.6346 | 5.00% | 0.00% | 0.00% | 59.2 |
| `inside` | `mobile_keypad_confusion_catalog` | 10,000 | 71.20% | 84.76% | 89.79% | 93.20% | 0.7721 | 0.7707 | 0.8082 | 0.45% | 0.00% | 0.00% | 37.8 |
| `inside` | `multi_error_chain` | 36 | 58.33% | 63.89% | 66.67% | 75.00% | 0.6212 | 0.6358 | 0.6649 | 2.78% | 0.00% | 0.00% | 81.4 |
| `inside` | `ocr_digit_letter` | 62 | 98.39% | 98.39% | 98.39% | 98.39% | 0.9839 | 0.9809 | 0.9827 | 0.00% | 0.00% | 0.00% | 10.8 |
| `inside` | `ocr_digit_letter_full_catalog` | 8,000 | 99.46% | 99.75% | 99.75% | 99.75% | 0.9958 | 0.9878 | 0.9893 | 0.14% | 0.00% | 0.00% | 6.3 |
| `inside` | `partial_prefix_ambiguity_catalog` | 10,000 | 8.47% | 25.90% | 37.56% | 50.51% | 0.1696 | 0.1714 | 0.2452 | 0.00% | 0.00% | 0.00% | 587.6 |
| `inside` | `ph_f_confusion` | 346 | 65.03% | 73.12% | 76.30% | 78.32% | 0.6875 | 0.6706 | 0.6931 | 0.00% | 0.00% | 0.00% | 109.1 |
| `inside` | `phonetic_substitution_full_catalog` | 18,000 | 96.92% | 98.67% | 99.10% | 99.35% | 0.9771 | 0.9674 | 0.9727 | 0.14% | 0.00% | 0.00% | 46.6 |
| `inside` | `position_deletion` | 168 | 57.74% | 61.90% | 66.67% | 72.62% | 0.6002 | 0.6188 | 0.6458 | 1.79% | 0.00% | 0.00% | 180.7 |
| `inside` | `separator_removal_full_catalog` | 6,850 | 98.92% | 99.71% | 99.84% | 99.88% | 0.9927 | 0.9924 | 0.9941 | 0.00% | 0.00% | 0.00% | 45.8 |
| `inside` | `single_vowel_deletion_full_catalog` | 14,000 | 96.85% | 98.82% | 99.23% | 99.38% | 0.9770 | 0.9661 | 0.9719 | 0.08% | 0.00% | 0.00% | 52.7 |
| `inside` | `space_insertion_inside_brand_catalog` | 8,000 | 99.99% | 100.00% | 100.00% | 100.00% | 0.9999 | 0.9988 | 0.9990 | 0.00% | 0.00% | 0.00% | 308.3 |
| `inside` | `suffix_family_confusion` | 43 | 95.35% | 100.00% | 100.00% | 100.00% | 0.9729 | 0.8351 | 0.8420 | 0.00% | 0.00% | 0.00% | 213.4 |
| `inside` | `suffix_family_confusion_expanded_catalog` | 5,500 | 80.05% | 89.29% | 92.00% | 94.42% | 0.8416 | 0.8318 | 0.8569 | 0.33% | 0.00% | 0.00% | 60.3 |
| `inside` | `syllable_transposition` | 212 | 88.68% | 91.51% | 92.92% | 94.34% | 0.9010 | 0.9007 | 0.9132 | 0.00% | 0.00% | 0.00% | 42.7 |
| `inside` | `token_drop_expanded_catalog` | 900 | 60.44% | 86.78% | 93.56% | 96.89% | 0.7173 | 0.7175 | 0.7781 | 0.00% | 0.00% | 0.00% | 421.9 |
| `inside` | `token_order_transposition_catalog` | 9,000 | 77.21% | 95.00% | 97.79% | 99.29% | 0.8486 | 0.8497 | 0.8849 | 0.00% | 0.00% | 0.00% | 567.3 |
| `inside` | `truncation_collision` | 498 | 47.99% | 71.08% | 80.52% | 83.53% | 0.5783 | 0.5379 | 0.6180 | 0.00% | 0.00% | 0.00% | 379.1 |
| `inside` | `truncation_collision_expanded_catalog` | 5,146 | 0.68% | 45.92% | 63.00% | 77.26% | 0.2066 | 0.2139 | 0.3419 | 0.00% | 0.00% | 0.00% | 473.9 |
| `inside` | `visual_ligature_full_catalog` | 7,000 | 64.13% | 81.09% | 86.29% | 90.60% | 0.7157 | 0.7141 | 0.7586 | 0.24% | 0.00% | 0.00% | 45.1 |
| `inside` | `voiced_unvoiced_swap` | 150 | 76.00% | 77.33% | 77.33% | 77.33% | 0.7639 | 0.7428 | 0.7451 | 2.00% | 0.00% | 0.00% | 93.7 |
| `inside` | `vowel_substitution_full_catalog` | 22,000 | 98.10% | 99.12% | 99.18% | 99.21% | 0.9853 | 0.9755 | 0.9787 | 0.17% | 0.00% | 0.00% | 72.1 |
| `outside` | `brand_ingredient_mixed_query_catalog` | 6,000 | 94.07% | 98.73% | 99.47% | 99.87% | 0.9602 | 0.9526 | 0.9640 | 0.00% | 0.00% | 0.00% | 1066.5 |
| `outside` | `form_word_noise_catalog` | 12,000 | 96.58% | 99.45% | 99.81% | 99.95% | 0.9785 | 0.9716 | 0.9783 | 0.00% | 0.00% | 0.00% | 296.9 |
| `outside` | `ingredient_name_query_catalog` | 9,000 | 44.82% | 69.83% | 80.73% | 90.94% | 0.5611 | 0.5399 | 0.6257 | 0.00% | 0.01% | 0.13% | 1605.3 |
| `outside` | `manufacturer_noise_catalog` | 8,000 | 95.36% | 99.42% | 99.59% | 99.67% | 0.9698 | 0.9592 | 0.9681 | 0.00% | 0.00% | 0.00% | 355.1 |
| `outside` | `route_word_noise_catalog` | 6,031 | 91.96% | 99.25% | 99.75% | 99.80% | 0.9537 | 0.9518 | 0.9636 | 0.00% | 0.00% | 0.00% | 490.3 |
| `outside` | `status_marker_noise_catalog` | 7,000 | 97.94% | 99.53% | 99.77% | 99.80% | 0.9861 | 0.9784 | 0.9826 | 0.00% | 0.00% | 0.00% | 381.9 |
| `outside` | `therapeutic_class_noise_catalog` | 7,000 | 95.17% | 98.91% | 99.44% | 99.77% | 0.9672 | 0.9602 | 0.9691 | 0.00% | 0.00% | 0.00% | 513.6 |
| `semi_outside` | `abbreviation_expansion_catalog` | 1,000 | 98.10% | 99.70% | 99.90% | 99.90% | 0.9889 | 0.9417 | 0.9612 | 0.00% | 0.00% | 0.00% | 470.3 |
| `semi_outside` | `decimal_slash_strength_noise_catalog` | 7,500 | 98.73% | 99.85% | 99.93% | 99.96% | 0.9923 | 0.9617 | 0.9725 | 0.00% | 0.00% | 0.00% | 1221.9 |
| `semi_outside` | `parenthetical_noise_catalog` | 5,000 | 97.38% | 99.60% | 99.80% | 99.86% | 0.9831 | 0.9752 | 0.9807 | 0.00% | 0.00% | 0.00% | 343.5 |
| `semi_outside` | `prefix_suffix_extra_noise_catalog` | 7,000 | 97.71% | 99.51% | 99.71% | 99.83% | 0.9847 | 0.9787 | 0.9835 | 0.00% | 0.00% | 0.00% | 242.7 |
| `semi_outside` | `qualifier_synonym_noise_catalog` | 6,000 | 95.03% | 99.52% | 99.77% | 99.93% | 0.9705 | 0.9627 | 0.9712 | 0.00% | 0.00% | 0.00% | 274.1 |
| `semi_outside` | `strength_unit_noise_catalog` | 18,000 | 98.86% | 99.72% | 99.78% | 99.79% | 0.9924 | 0.9713 | 0.9799 | 0.13% | 0.00% | 0.00% | 229.6 |
| `semi_outside` | `symbol_synonym_catalog` | 6,825 | 99.15% | 99.99% | 100.00% | 100.00% | 0.9954 | 0.9192 | 0.9455 | 0.00% | 0.00% | 0.00% | 555.6 |

## Where The Problems Are

Lowest `Hit@1` categories:

1. `truncation_collision_expanded_catalog`: `0.68%` Hit@1, but `77.26%` Hit@20. The expected behavior for these is often clarification rather than confident top-1.
2. `cross_script`: `3.33%` Hit@1 and `93.33%` no-result rate. Arabic/cross-script handling is the weakest area.
3. `arabic_dot_confusion`: `6.90%` Hit@1 and `75.86%` no-result rate. Arabic visual normalization needs expansion.
4. `partial_prefix_ambiguity_catalog`: `8.47%` Hit@1, average candidate pool `587.6`. This confirms short prefixes are broad and should trigger clarification.
5. `ligature_confusion`: `23.60%` Hit@1. Visual multi-character confusions need stronger candidate generation.

Safety result:

- Overall unsafe confident top-1 rate is effectively zero: `2.92e-06`.
- The only non-zero unsafe top-1 category is `ingredient_name_query_catalog` at `0.01%`.
- Missing clarification is concentrated in `ingredient_name_query_catalog` at `0.13%`.

## Reproduction Instructions

From the nested repo root:

```bash
cd medicine-search-clean
PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 -m compileall benchmark_01_legacy
PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 -m unittest discover -s benchmark_01_legacy -p 'test_*.py'
PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 benchmark_01_legacy/generate_commercial_name_test_cases.py
PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 benchmark_01_legacy/evaluate_current_app_search.py
```

Outputs:

- `benchmark_01_legacy/data/test_cases.csv`
- `benchmark_01_legacy/data/test_cases_inside.csv`
- `benchmark_01_legacy/data/test_cases_semi_outside.csv`
- `benchmark_01_legacy/data/test_cases_outside.csv`
- `benchmark_01_legacy/results/01_current_app/metrics_by_category.csv`
- `benchmark_01_legacy/results/01_current_app/metrics_by_error_type.csv`
- `benchmark_01_legacy/artifacts/01_current_app/case_results.csv`
- `benchmark_01_legacy/results/01_current_app/report.md`
- `benchmark_01_legacy/results/01_current_app/failure_samples.csv`
- `benchmark_01_legacy/results/01_current_app/top_wrong_families.csv`
- `benchmark_01_legacy/artifacts/02_external_fast/case_results.csv`
- `benchmark_01_legacy/results/02_external_fast/metrics_by_category.csv`
- `benchmark_01_legacy/results/02_external_fast/metrics_by_error_type.csv`
- `benchmark_01_legacy/results/03_comparison/metrics_by_category.csv`
- `benchmark_01_legacy/results/03_comparison/report.md`

## External English Fast Comparison

The external algorithm is the snapshot at `benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py`.
The evaluator adapts the app catalog as `commercial_name = n` and `canonical_name = b`, because the commercial-name test suite expects base-family retrieval.

| scope | current Hit@1 | external Hit@1 | delta | current Hit@20 | external Hit@20 | delta | external unsafe top-1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `inside` | 78.38% | 85.61% | +7.23% | 92.56% | 93.82% | +1.26% | 2.83% |
| `semi_outside` | 98.12% | 65.39% | -32.73% | 99.87% | 90.27% | -9.61% | 0.01% |
| `outside` | 87.15% | 67.53% | -19.62% | 98.37% | 84.52% | -13.85% | 2.58% |
| `__ALL__` | 82.76% | 79.66% | -3.09% | 94.59% | 91.79% | -2.80% | 2.36% |

Conclusion: the external algorithm improves pure inside commercial-name retrieval but is not safer as-is. It produces a much higher unsafe confident top-1 rate and loses badly on semi-outside/outside cases, especially ingredient queries and keyboard-shift cases.

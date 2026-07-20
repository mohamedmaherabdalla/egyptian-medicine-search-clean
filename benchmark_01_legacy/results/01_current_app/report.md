# Current App Search Evaluation

This report evaluates the collision-aware static app search behavior against the split commercial-name stress suites.

Important method note: the browser app and evaluator both use catalog-derived candidate generation before ranking. The evaluator mirrors the app scoring path and records candidate-pool size for analysis.

## Outputs

| file | purpose |
| --- | --- |
| `benchmark_01_legacy/results/01_current_app/metrics_by_category.csv` | metrics by scope/category |
| `benchmark_01_legacy/results/01_current_app/metrics_by_error_type.csv` | metrics by scope/category/error_type |
| `benchmark_01_legacy/artifacts/01_current_app/case_results.csv` | one row per evaluated test case with rank, top result, and safety flags |
| `benchmark_01_legacy/results/01_current_app/failure_samples.csv` | first failure samples |
| `benchmark_01_legacy/results/01_current_app/top_wrong_families.csv` | most frequent wrong top-1 bases |

## Headline Metrics

- Evaluated cases: `341,901`.
- Runtime: `859.89` seconds.
- Overall Hit@1: `82.76%`.
- Overall Hit@5: `90.16%`.
- Overall Hit@10: `92.60%`.
- Overall Hit@20: `94.59%`.
- Overall MRR@20: `0.8603`.
- Overall MAP@20: `0.8515`.
- Overall nDCG@20: `0.8736`.
- Unsafe confident top-1 rate: `0.00%`.
- Missing clarification rate: `0.00%`.

## Metrics By Scope

| scope | cases | Hit@1 | Hit@5 | Hit@20 | MRR@20 | unsafe confident top-1 | missing clarification | avg candidate pool |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `inside` | 235,545 | 78.38% | 87.08% | 92.56% | 0.8223 | 0.00% | 0.00% | 112.8 |
| `outside` | 55,031 | 87.15% | 94.44% | 98.37% | 0.9038 | 0.00% | 0.02% | 662.8 |
| `semi_outside` | 51,325 | 98.12% | 99.71% | 99.87% | 0.9882 | 0.00% | 0.00% | 440.7 |

## Worst Retrieval Categories

| scope | category | cases | Hit@5 | Hit@20 | unsafe top-1 | missing clarification |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `inside` | `cross_script` | 30 | 3.33% | 6.67% | 0.00% | 0.00% |
| `inside` | `arabic_dot_confusion` | 29 | 10.34% | 13.79% | 0.00% | 0.00% |
| `inside` | `double_letter` | 24 | 50.00% | 50.00% | 0.00% | 0.00% |
| `inside` | `partial_prefix_ambiguity_catalog` | 10,000 | 25.90% | 50.51% | 0.00% | 0.00% |
| `inside` | `ligature_confusion` | 250 | 43.60% | 63.60% | 0.00% | 0.00% |
| `inside` | `c_k_q_interchange` | 72 | 68.06% | 69.44% | 0.00% | 0.00% |
| `inside` | `mirror_letter_confusion` | 80 | 67.50% | 72.50% | 0.00% | 0.00% |
| `inside` | `position_deletion` | 168 | 61.90% | 72.62% | 0.00% | 0.00% |
| `inside` | `multi_error_chain` | 36 | 63.89% | 75.00% | 0.00% | 0.00% |
| `inside` | `truncation_collision_expanded_catalog` | 5,146 | 45.92% | 77.26% | 0.00% | 0.00% |
| `inside` | `voiced_unvoiced_swap` | 150 | 77.33% | 77.33% | 0.00% | 0.00% |
| `inside` | `ph_f_confusion` | 346 | 73.12% | 78.32% | 0.00% | 0.00% |
| `inside` | `truncation_collision` | 498 | 71.08% | 83.53% | 0.00% | 0.00% |
| `inside` | `keyboard_shift_whole_word_catalog` | 7,000 | 76.36% | 84.07% | 0.00% | 0.00% |
| `inside` | `all_position_deletion_full_catalog` | 25,000 | 77.06% | 87.13% | 0.00% | 0.00% |
| `inside` | `keyboard_adjacent` | 898 | 81.63% | 88.98% | 0.00% | 0.00% |
| `inside` | `duplicate_syllable_catalog` | 5,000 | 90.54% | 90.60% | 0.00% | 0.00% |
| `inside` | `visual_ligature_full_catalog` | 7,000 | 81.09% | 90.60% | 0.00% | 0.00% |
| `outside` | `ingredient_name_query_catalog` | 9,000 | 69.83% | 90.94% | 0.01% | 0.13% |
| `inside` | `digraph_soundalike_catalog` | 3,000 | 85.20% | 91.73% | 0.00% | 0.00% |

## Highest Safety-Risk Categories

| scope | category | cases | unsafe confident top-1 | Hit@20 |
| --- | --- | ---: | ---: | ---: |
| `outside` | `ingredient_name_query_catalog` | 9,000 | 0.01% | 90.94% |
| `inside` | `all_position_deletion_full_catalog` | 25,000 | 0.00% | 87.13% |
| `inside` | `all_position_transposition_full_catalog` | 20,000 | 0.00% | 95.45% |
| `inside` | `arabic_dot_confusion` | 29 | 0.00% | 13.79% |
| `inside` | `c_k_q_interchange` | 72 | 0.00% | 69.44% |
| `inside` | `consonant_skeleton` | 84 | 0.00% | 95.24% |
| `inside` | `consonant_skeleton_expanded_catalog` | 12,000 | 0.00% | 93.73% |
| `inside` | `cross_script` | 30 | 0.00% | 6.67% |
| `inside` | `digraph_soundalike_catalog` | 3,000 | 0.00% | 91.73% |
| `inside` | `double_letter` | 24 | 0.00% | 50.00% |
| `inside` | `duplicate_syllable_catalog` | 5,000 | 0.00% | 90.60% |
| `inside` | `initial_sound_confusion_full_catalog` | 14,125 | 0.00% | 98.55% |
| `inside` | `keyboard_adjacent` | 898 | 0.00% | 88.98% |
| `inside` | `keyboard_adjacent_expanded_catalog` | 22,000 | 0.00% | 91.91% |
| `inside` | `keyboard_shift_whole_word_catalog` | 7,000 | 0.00% | 84.07% |

## Missing Clarification Hotspots

| scope | category | cases | missing clarification | Hit@20 |
| --- | --- | ---: | ---: | ---: |
| `outside` | `ingredient_name_query_catalog` | 9,000 | 0.13% | 90.94% |
| `inside` | `all_position_deletion_full_catalog` | 25,000 | 0.00% | 87.13% |
| `inside` | `all_position_transposition_full_catalog` | 20,000 | 0.00% | 95.45% |
| `inside` | `arabic_dot_confusion` | 29 | 0.00% | 13.79% |
| `inside` | `c_k_q_interchange` | 72 | 0.00% | 69.44% |
| `inside` | `consonant_skeleton` | 84 | 0.00% | 95.24% |
| `inside` | `consonant_skeleton_expanded_catalog` | 12,000 | 0.00% | 93.73% |
| `inside` | `cross_script` | 30 | 0.00% | 6.67% |
| `inside` | `digraph_soundalike_catalog` | 3,000 | 0.00% | 91.73% |
| `inside` | `double_letter` | 24 | 0.00% | 50.00% |
| `inside` | `duplicate_syllable_catalog` | 5,000 | 0.00% | 90.60% |
| `inside` | `initial_sound_confusion_full_catalog` | 14,125 | 0.00% | 98.55% |
| `inside` | `keyboard_adjacent` | 898 | 0.00% | 88.98% |
| `inside` | `keyboard_adjacent_expanded_catalog` | 22,000 | 0.00% | 91.91% |
| `inside` | `keyboard_shift_whole_word_catalog` | 7,000 | 0.00% | 84.07% |

## Frequent Wrong Top-1 Families

| category | wrong top-1 family | count |
| --- | --- | ---: |
| `partial_prefix_ambiguity_catalog` | `CALCIDORATO` | 402 |
| `partial_prefix_ambiguity_catalog` | `COD PRIMROSE` | 330 |
| `partial_prefix_ambiguity_catalog` | `ALAFLIC` | 272 |
| `route_word_noise_catalog` | `POVIDONE SKIN CLEANSER` | 237 |
| `partial_prefix_ambiguity_catalog` | `BECLO` | 235 |
| `partial_prefix_ambiguity_catalog` | `ANASTRODEX` | 181 |
| `partial_prefix_ambiguity_catalog` | `CECLOR` | 181 |
| `partial_prefix_ambiguity_catalog` | `BILASTIGEC` | 173 |
| `partial_prefix_ambiguity_catalog` | `BRAN` | 173 |
| `truncation_collision_expanded_catalog` | `PRO` | 162 |
| `partial_prefix_ambiguity_catalog` | `CAL DAR` | 159 |
| `partial_prefix_ambiguity_catalog` | `ACAI BERRY VEG` | 156 |
| `partial_prefix_ambiguity_catalog` | `CLARIKAN S R` | 152 |
| `partial_prefix_ambiguity_catalog` | `AVANJOY` | 150 |
| `ingredient_name_query_catalog` | `FOHALI FOLIC ACID VITAMIN B12` | 149 |
| `partial_prefix_ambiguity_catalog` | `CHAMOMATE` | 148 |
| `partial_prefix_ambiguity_catalog` | `CILOBIOGEN` | 132 |
| `partial_prefix_ambiguity_catalog` | `CARBAMAZEPIN` | 131 |
| `partial_prefix_ambiguity_catalog` | `BACLOFEN` | 128 |
| `partial_prefix_ambiguity_catalog` | `AMANTINE` | 126 |

## Reading The Results

- Unsafe confident top-1 is the main safety metric. A wrong top result is less dangerous when it is clearly marked as needing clarification.
- Hit@1 may drop after safety gates because the system stops pretending ambiguous short inputs are exact answers.
- Keyboard-shift, visual-confusion, and phonetic improvements should be judged with Hit@20 plus clarification behavior, not only top-1.

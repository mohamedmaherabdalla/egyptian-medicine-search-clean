# V2 Proportional Sample Four-Way Benchmark

Sample file: `benchmark_02_synthetic/data/samples/proportional_6000.csv`.
Sample rows: `6,000`.
Categories covered: `34`.

The sample preserves the full V2 category distribution using deterministic hash ordering inside each category. All four systems are scored on exactly the same `source_row` set.

Algorithm naming: Algorithm 1 = current app evaluator, Algorithm 2 = external English fast algorithm, Algorithm 3 = master rank-fusion algorithm.

## Row Coverage

| algorithm | result rows on sample | expected rows | complete |
| --- | ---: | ---: | --- |
| `Algorithm 1` | 6,000 | 6,000 | yes |
| `Algorithm 2` | 6,000 | 6,000 | yes |
| `Algorithm 3` | 6,000 | 6,000 | yes |
| `DrugEye trade` | 6,000 | 6,000 | yes |

## Overall Scores

| algorithm | cases | Hit@1 | Hit@20 | behavior success | unsafe top-1 | no-result | network error | avg candidates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `Algorithm 1` | 6,000 | 75.28% | 88.58% | 88.87% | 0.02% | 2.83% | 0.00% | 186.83 |
| `Algorithm 2` | 6,000 | 79.07% | 91.70% | 91.00% | 6.88% | 0.00% | 0.00% | 17.97 |
| `Algorithm 3` | 6,000 | 80.83% | 93.13% | 93.37% | 0.00% | 0.00% | 0.00% | 37.88 |
| `DrugEye trade` | 6,000 | 21.75% | 30.53% | 30.53% | 0.00% | 62.88% | 0.00% | 2.89 |

## Scope Scores

| algorithm | scope | cases | Hit@1 | Hit@20 | behavior success | unsafe top-1 | no-result | network error |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `Algorithm 1` | `inside` | 4,539 | 73.47% | 87.53% | 87.53% | 0.00% | 2.58% | 0.00% |
| `DrugEye trade` | `inside` | 4,539 | 10.58% | 19.04% | 19.04% | 0.00% | 71.45% | 0.00% |
| `Algorithm 2` | `inside` | 4,539 | 80.77% | 91.78% | 91.78% | 6.06% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | 4,539 | 80.37% | 92.49% | 92.49% | 0.00% | 0.00% | 0.00% |
| `Algorithm 1` | `safety` | 940 | 74.26% | 88.94% | 90.74% | 0.00% | 5.32% | 0.00% |
| `DrugEye trade` | `safety` | 940 | 52.55% | 62.77% | 62.77% | 0.00% | 43.30% | 0.00% |
| `Algorithm 2` | `safety` | 940 | 73.72% | 92.87% | 89.89% | 14.36% | 0.00% | 0.00% |
| `Algorithm 3` | `safety` | 940 | 75.74% | 93.83% | 95.32% | 0.00% | 0.00% | 0.00% |
| `Algorithm 1` | `semi_outside` | 209 | 90.91% | 95.22% | 95.22% | 0.48% | 0.00% | 0.00% |
| `DrugEye trade` | `semi_outside` | 209 | 42.58% | 50.72% | 50.72% | 0.00% | 45.93% | 0.00% |
| `Algorithm 2` | `semi_outside` | 209 | 75.60% | 86.60% | 86.60% | 0.00% | 0.00% | 0.00% |
| `Algorithm 3` | `semi_outside` | 209 | 93.30% | 95.69% | 95.69% | 0.00% | 0.00% | 0.00% |
| `Algorithm 1` | `smoke` | 312 | 94.23% | 98.40% | 98.40% | 0.00% | 0.96% | 0.00% |
| `DrugEye trade` | `smoke` | 312 | 77.56% | 87.18% | 87.18% | 0.00% | 8.65% | 0.00% |
| `Algorithm 2` | `smoke` | 312 | 72.76% | 90.38% | 85.90% | 0.96% | 0.00% | 0.00% |
| `Algorithm 3` | `smoke` | 312 | 94.55% | 98.72% | 98.72% | 0.00% | 0.00% | 0.00% |

## Sample Distribution

| scope | category | full rows | sample rows | sample share |
| --- | --- | ---: | ---: | ---: |
| `inside` | `autocorrect_artifacts` | 2,000 | 104 | 1.73% |
| `inside` | `case_sensitivity` | 500 | 26 | 0.43% |
| `inside` | `consonant_frame_wrong_vowels_heavy` | 4,000 | 209 | 3.48% |
| `inside` | `double_letter_reduction_expansion` | 3,000 | 156 | 2.60% |
| `inside` | `four_plus_error_combinations` | 4,000 | 209 | 3.48% |
| `inside` | `keyboard_adjacent_sampled` | 2,000 | 104 | 1.73% |
| `inside` | `ligature_confusion` | 4,000 | 209 | 3.48% |
| `inside` | `multi_char_phonetic_confusion` | 5,000 | 261 | 4.35% |
| `inside` | `multi_word_name_fragmentation` | 2,000 | 104 | 1.73% |
| `inside` | `number_word_confusion` | 500 | 26 | 0.43% |
| `inside` | `ocr_letter_digit_confusion` | 4,000 | 209 | 3.48% |
| `inside` | `ocr_plus_other_error_combined` | 3,000 | 156 | 2.60% |
| `inside` | `punctuation_whitespace_copy_paste_artifacts` | 1,000 | 52 | 0.87% |
| `inside` | `single_char_deletion_position_weighted` | 5,000 | 261 | 4.35% |
| `inside` | `single_char_insertion` | 3,000 | 157 | 2.62% |
| `inside` | `single_letter_phonetic_confusion` | 6,000 | 313 | 5.22% |
| `inside` | `single_letter_visual_confusion` | 8,000 | 417 | 6.95% |
| `inside` | `speed_typing_errors` | 3,000 | 157 | 2.62% |
| `inside` | `three_error_combinations` | 5,000 | 261 | 4.35% |
| `inside` | `transposition_position_weighted` | 3,000 | 157 | 2.62% |
| `inside` | `truncation_doctor_abbreviation` | 6,000 | 313 | 5.22% |
| `inside` | `two_error_combinations` | 8,000 | 417 | 6.95% |
| `inside` | `wrong_vowels_in_consonant_frame` | 5,000 | 261 | 4.35% |
| `safety` | `cancelled_na_drug_lookup` | 1,000 | 52 | 0.87% |
| `safety` | `contradictory_form_route` | 2,000 | 104 | 1.73% |
| `safety` | `dangerous_ed1_pairs` | 5,000 | 261 | 4.35% |
| `safety` | `negative_no_match_expected` | 3,000 | 157 | 2.62% |
| `safety` | `score_gap_ambiguity_detection` | 4,000 | 209 | 3.48% |
| `safety` | `substring_traps` | 3,000 | 157 | 2.62% |
| `semi_outside` | `embedded_form_strength_parsing` | 4,000 | 209 | 3.48% |
| `smoke` | `exact_match_baseline` | 2,000 | 104 | 1.73% |
| `smoke` | `exact_match_with_strength` | 2,000 | 104 | 1.73% |
| `smoke` | `keyboard_shift_whole_word` | 500 | 26 | 0.43% |
| `smoke` | `prefix_ambiguity_awareness` | 1,500 | 78 | 1.30% |

## Category Scores

| algorithm | scope | category | cases | Hit@1 | Hit@20 | behavior success | no-result | network error |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Algorithm 1` | `inside` | `autocorrect_artifacts` | 104 | 0.00% | 1.92% | 1.92% | 0.00% | 0.00% |
| `DrugEye trade` | `inside` | `autocorrect_artifacts` | 104 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| `Algorithm 2` | `inside` | `autocorrect_artifacts` | 104 | 0.00% | 3.85% | 3.85% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `autocorrect_artifacts` | 104 | 0.00% | 3.85% | 3.85% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `case_sensitivity` | 26 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `DrugEye trade` | `inside` | `case_sensitivity` | 26 | 80.77% | 84.62% | 84.62% | 7.69% | 0.00% |
| `Algorithm 2` | `inside` | `case_sensitivity` | 26 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `case_sensitivity` | 26 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `consonant_frame_wrong_vowels_heavy` | 209 | 89.95% | 96.65% | 96.65% | 0.48% | 0.00% |
| `DrugEye trade` | `inside` | `consonant_frame_wrong_vowels_heavy` | 209 | 0.00% | 0.00% | 0.00% | 97.61% | 0.00% |
| `Algorithm 2` | `inside` | `consonant_frame_wrong_vowels_heavy` | 209 | 90.43% | 98.09% | 98.09% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `consonant_frame_wrong_vowels_heavy` | 209 | 90.91% | 97.61% | 97.61% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `double_letter_reduction_expansion` | 156 | 98.72% | 100.00% | 100.00% | 0.00% | 0.00% |
| `DrugEye trade` | `inside` | `double_letter_reduction_expansion` | 156 | 16.67% | 29.49% | 29.49% | 64.10% | 0.00% |
| `Algorithm 2` | `inside` | `double_letter_reduction_expansion` | 156 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `double_letter_reduction_expansion` | 156 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `four_plus_error_combinations` | 209 | 34.93% | 47.37% | 47.37% | 22.01% | 0.00% |
| `DrugEye trade` | `inside` | `four_plus_error_combinations` | 209 | 0.48% | 0.96% | 0.96% | 96.65% | 0.00% |
| `Algorithm 2` | `inside` | `four_plus_error_combinations` | 209 | 57.89% | 64.59% | 64.59% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `four_plus_error_combinations` | 209 | 55.98% | 68.90% | 68.90% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `keyboard_adjacent_sampled` | 104 | 68.27% | 92.31% | 92.31% | 0.00% | 0.00% |
| `DrugEye trade` | `inside` | `keyboard_adjacent_sampled` | 104 | 1.92% | 3.85% | 3.85% | 89.42% | 0.00% |
| `Algorithm 2` | `inside` | `keyboard_adjacent_sampled` | 104 | 78.85% | 96.15% | 96.15% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `keyboard_adjacent_sampled` | 104 | 81.73% | 96.15% | 96.15% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `ligature_confusion` | 209 | 67.46% | 95.69% | 95.69% | 0.00% | 0.00% |
| `DrugEye trade` | `inside` | `ligature_confusion` | 209 | 11.96% | 16.27% | 16.27% | 74.16% | 0.00% |
| `Algorithm 2` | `inside` | `ligature_confusion` | 209 | 81.82% | 96.65% | 96.65% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `ligature_confusion` | 209 | 81.82% | 98.56% | 98.56% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `multi_char_phonetic_confusion` | 261 | 92.72% | 98.85% | 98.85% | 0.00% | 0.00% |
| `DrugEye trade` | `inside` | `multi_char_phonetic_confusion` | 261 | 14.56% | 21.46% | 21.46% | 73.18% | 0.00% |
| `Algorithm 2` | `inside` | `multi_char_phonetic_confusion` | 261 | 99.23% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `multi_char_phonetic_confusion` | 261 | 98.85% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `multi_word_name_fragmentation` | 104 | 0.00% | 67.31% | 67.31% | 0.00% | 0.00% |
| `DrugEye trade` | `inside` | `multi_word_name_fragmentation` | 104 | 13.46% | 50.96% | 50.96% | 2.88% | 0.00% |
| `Algorithm 2` | `inside` | `multi_word_name_fragmentation` | 104 | 0.00% | 72.12% | 72.12% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `multi_word_name_fragmentation` | 104 | 0.00% | 73.08% | 73.08% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `number_word_confusion` | 26 | 69.23% | 92.31% | 92.31% | 3.85% | 0.00% |
| `DrugEye trade` | `inside` | `number_word_confusion` | 26 | 34.62% | 50.00% | 50.00% | 19.23% | 0.00% |
| `Algorithm 2` | `inside` | `number_word_confusion` | 26 | 88.46% | 92.31% | 92.31% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `number_word_confusion` | 26 | 84.62% | 92.31% | 92.31% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `ocr_letter_digit_confusion` | 209 | 94.26% | 99.04% | 99.04% | 0.00% | 0.00% |
| `DrugEye trade` | `inside` | `ocr_letter_digit_confusion` | 209 | 14.83% | 21.53% | 21.53% | 71.29% | 0.00% |
| `Algorithm 2` | `inside` | `ocr_letter_digit_confusion` | 209 | 98.09% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `ocr_letter_digit_confusion` | 209 | 97.61% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `ocr_plus_other_error_combined` | 156 | 84.62% | 92.95% | 92.95% | 1.28% | 0.00% |
| `DrugEye trade` | `inside` | `ocr_plus_other_error_combined` | 156 | 3.21% | 5.77% | 5.77% | 92.95% | 0.00% |
| `Algorithm 2` | `inside` | `ocr_plus_other_error_combined` | 156 | 92.95% | 94.23% | 94.23% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `ocr_plus_other_error_combined` | 156 | 92.31% | 95.51% | 95.51% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `punctuation_whitespace_copy_paste_artifacts` | 52 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `DrugEye trade` | `inside` | `punctuation_whitespace_copy_paste_artifacts` | 52 | 38.46% | 44.23% | 44.23% | 51.92% | 0.00% |
| `Algorithm 2` | `inside` | `punctuation_whitespace_copy_paste_artifacts` | 52 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `punctuation_whitespace_copy_paste_artifacts` | 52 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `single_char_deletion_position_weighted` | 261 | 85.82% | 96.93% | 96.93% | 0.38% | 0.00% |
| `DrugEye trade` | `inside` | `single_char_deletion_position_weighted` | 261 | 30.65% | 38.31% | 38.31% | 56.70% | 0.00% |
| `Algorithm 2` | `inside` | `single_char_deletion_position_weighted` | 261 | 96.93% | 99.62% | 99.62% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `single_char_deletion_position_weighted` | 261 | 94.25% | 99.23% | 99.23% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `single_char_insertion` | 157 | 93.63% | 98.73% | 98.73% | 0.64% | 0.00% |
| `DrugEye trade` | `inside` | `single_char_insertion` | 157 | 12.10% | 16.56% | 16.56% | 80.89% | 0.00% |
| `Algorithm 2` | `inside` | `single_char_insertion` | 157 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `single_char_insertion` | 157 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `single_letter_phonetic_confusion` | 313 | 99.04% | 100.00% | 100.00% | 0.00% | 0.00% |
| `DrugEye trade` | `inside` | `single_letter_phonetic_confusion` | 313 | 13.10% | 19.49% | 19.49% | 73.80% | 0.00% |
| `Algorithm 2` | `inside` | `single_letter_phonetic_confusion` | 313 | 97.12% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `single_letter_phonetic_confusion` | 313 | 98.40% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `single_letter_visual_confusion` | 417 | 87.53% | 97.84% | 97.84% | 0.00% | 0.00% |
| `DrugEye trade` | `inside` | `single_letter_visual_confusion` | 417 | 11.03% | 17.99% | 17.99% | 74.34% | 0.00% |
| `Algorithm 2` | `inside` | `single_letter_visual_confusion` | 417 | 93.76% | 99.76% | 99.76% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `single_letter_visual_confusion` | 417 | 91.85% | 99.76% | 99.76% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `speed_typing_errors` | 157 | 88.54% | 92.36% | 92.36% | 1.91% | 0.00% |
| `DrugEye trade` | `inside` | `speed_typing_errors` | 157 | 8.28% | 10.19% | 10.19% | 85.99% | 0.00% |
| `Algorithm 2` | `inside` | `speed_typing_errors` | 157 | 94.90% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `speed_typing_errors` | 157 | 94.90% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `three_error_combinations` | 261 | 40.61% | 55.17% | 55.17% | 14.94% | 0.00% |
| `DrugEye trade` | `inside` | `three_error_combinations` | 261 | 0.38% | 0.38% | 0.38% | 99.23% | 0.00% |
| `Algorithm 2` | `inside` | `three_error_combinations` | 261 | 64.75% | 75.48% | 75.48% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `three_error_combinations` | 261 | 63.98% | 78.54% | 78.54% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `transposition_position_weighted` | 157 | 96.82% | 100.00% | 100.00% | 0.00% | 0.00% |
| `DrugEye trade` | `inside` | `transposition_position_weighted` | 157 | 14.01% | 22.29% | 22.29% | 70.70% | 0.00% |
| `Algorithm 2` | `inside` | `transposition_position_weighted` | 157 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `transposition_position_weighted` | 157 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `truncation_doctor_abbreviation` | 313 | 21.41% | 80.83% | 80.83% | 0.00% | 0.00% |
| `DrugEye trade` | `inside` | `truncation_doctor_abbreviation` | 313 | 16.93% | 69.33% | 69.33% | 4.15% | 0.00% |
| `Algorithm 2` | `inside` | `truncation_doctor_abbreviation` | 313 | 16.93% | 83.39% | 83.39% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `truncation_doctor_abbreviation` | 313 | 18.85% | 86.90% | 86.90% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `two_error_combinations` | 417 | 69.30% | 84.41% | 84.41% | 5.28% | 0.00% |
| `DrugEye trade` | `inside` | `two_error_combinations` | 417 | 0.96% | 1.92% | 1.92% | 96.88% | 0.00% |
| `Algorithm 2` | `inside` | `two_error_combinations` | 417 | 85.13% | 94.48% | 94.48% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `two_error_combinations` | 417 | 83.69% | 94.48% | 94.48% | 0.00% | 0.00% |
| `Algorithm 1` | `inside` | `wrong_vowels_in_consonant_frame` | 261 | 92.72% | 98.08% | 98.08% | 0.38% | 0.00% |
| `DrugEye trade` | `inside` | `wrong_vowels_in_consonant_frame` | 261 | 3.45% | 6.90% | 6.90% | 87.74% | 0.00% |
| `Algorithm 2` | `inside` | `wrong_vowels_in_consonant_frame` | 261 | 95.40% | 98.85% | 98.85% | 0.00% | 0.00% |
| `Algorithm 3` | `inside` | `wrong_vowels_in_consonant_frame` | 261 | 95.02% | 98.47% | 98.47% | 0.00% | 0.00% |
| `Algorithm 1` | `safety` | `cancelled_na_drug_lookup` | 52 | 96.15% | 100.00% | 100.00% | 0.00% | 0.00% |
| `DrugEye trade` | `safety` | `cancelled_na_drug_lookup` | 52 | 40.38% | 55.77% | 55.77% | 38.46% | 0.00% |
| `Algorithm 2` | `safety` | `cancelled_na_drug_lookup` | 52 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 3` | `safety` | `cancelled_na_drug_lookup` | 52 | 98.08% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 1` | `safety` | `contradictory_form_route` | 104 | 99.04% | 100.00% | 100.00% | 0.00% | 0.00% |
| `DrugEye trade` | `safety` | `contradictory_form_route` | 104 | 83.65% | 93.27% | 93.27% | 3.85% | 0.00% |
| `Algorithm 2` | `safety` | `contradictory_form_route` | 104 | 91.35% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 3` | `safety` | `contradictory_form_route` | 104 | 97.12% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 1` | `safety` | `dangerous_ed1_pairs` | 261 | 67.05% | 83.14% | 83.14% | 2.68% | 0.00% |
| `DrugEye trade` | `safety` | `dangerous_ed1_pairs` | 261 | 6.90% | 7.66% | 7.66% | 85.44% | 0.00% |
| `Algorithm 2` | `safety` | `dangerous_ed1_pairs` | 261 | 79.69% | 97.32% | 97.32% | 0.00% | 0.00% |
| `Algorithm 3` | `safety` | `dangerous_ed1_pairs` | 261 | 73.18% | 95.40% | 95.40% | 0.00% | 0.00% |
| `Algorithm 1` | `safety` | `negative_no_match_expected` | 157 | 100.00% | 100.00% | 100.00% | 26.11% | 0.00% |
| `DrugEye trade` | `safety` | `negative_no_match_expected` | 157 | 95.54% | 95.54% | 95.54% | 95.54% | 0.00% |
| `Algorithm 2` | `safety` | `negative_no_match_expected` | 157 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 3` | `safety` | `negative_no_match_expected` | 157 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 1` | `safety` | `score_gap_ambiguity_detection` | 209 | 87.56% | 90.91% | 99.04% | 0.96% | 0.00% |
| `DrugEye trade` | `safety` | `score_gap_ambiguity_detection` | 209 | 86.60% | 90.43% | 90.43% | 2.87% | 0.00% |
| `Algorithm 2` | `safety` | `score_gap_ambiguity_detection` | 209 | 72.25% | 87.56% | 74.16% | 0.00% | 0.00% |
| `Algorithm 3` | `safety` | `score_gap_ambiguity_detection` | 209 | 87.08% | 92.34% | 99.04% | 0.00% | 0.00% |
| `Algorithm 1` | `safety` | `substring_traps` | 157 | 19.11% | 73.89% | 73.89% | 0.00% | 0.00% |
| `DrugEye trade` | `safety` | `substring_traps` | 157 | 23.57% | 66.88% | 66.88% | 2.55% | 0.00% |
| `Algorithm 2` | `safety` | `substring_traps` | 157 | 19.11% | 78.34% | 78.34% | 0.00% | 0.00% |
| `Algorithm 3` | `safety` | `substring_traps` | 157 | 19.11% | 80.89% | 80.89% | 0.00% | 0.00% |
| `Algorithm 1` | `semi_outside` | `embedded_form_strength_parsing` | 209 | 90.91% | 95.22% | 95.22% | 0.00% | 0.00% |
| `DrugEye trade` | `semi_outside` | `embedded_form_strength_parsing` | 209 | 42.58% | 50.72% | 50.72% | 45.93% | 0.00% |
| `Algorithm 2` | `semi_outside` | `embedded_form_strength_parsing` | 209 | 75.60% | 86.60% | 86.60% | 0.00% | 0.00% |
| `Algorithm 3` | `semi_outside` | `embedded_form_strength_parsing` | 209 | 93.30% | 95.69% | 95.69% | 0.00% | 0.00% |
| `Algorithm 1` | `smoke` | `exact_match_baseline` | 104 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `DrugEye trade` | `smoke` | `exact_match_baseline` | 104 | 76.92% | 90.38% | 90.38% | 0.96% | 0.00% |
| `Algorithm 2` | `smoke` | `exact_match_baseline` | 104 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 3` | `smoke` | `exact_match_baseline` | 104 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 1` | `smoke` | `exact_match_with_strength` | 104 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `DrugEye trade` | `smoke` | `exact_match_with_strength` | 104 | 81.73% | 96.15% | 96.15% | 0.00% | 0.00% |
| `Algorithm 2` | `smoke` | `exact_match_with_strength` | 104 | 68.27% | 96.15% | 96.15% | 0.00% | 0.00% |
| `Algorithm 3` | `smoke` | `exact_match_with_strength` | 104 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 1` | `smoke` | `keyboard_shift_whole_word` | 26 | 50.00% | 80.77% | 80.77% | 11.54% | 0.00% |
| `DrugEye trade` | `smoke` | `keyboard_shift_whole_word` | 26 | 0.00% | 0.00% | 0.00% | 100.00% | 0.00% |
| `Algorithm 2` | `smoke` | `keyboard_shift_whole_word` | 26 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| `Algorithm 3` | `smoke` | `keyboard_shift_whole_word` | 26 | 50.00% | 84.62% | 84.62% | 0.00% | 0.00% |
| `Algorithm 1` | `smoke` | `prefix_ambiguity_awareness` | 78 | 93.59% | 100.00% | 100.00% | 0.00% | 0.00% |
| `DrugEye trade` | `smoke` | `prefix_ambiguity_awareness` | 78 | 98.72% | 100.00% | 100.00% | 0.00% | 0.00% |
| `Algorithm 2` | `smoke` | `prefix_ambiguity_awareness` | 78 | 66.67% | 100.00% | 82.05% | 0.00% | 0.00% |
| `Algorithm 3` | `smoke` | `prefix_ambiguity_awareness` | 78 | 94.87% | 100.00% | 100.00% | 0.00% | 0.00% |

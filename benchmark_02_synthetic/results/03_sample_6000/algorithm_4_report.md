# Algorithm 4 Benchmark Report

Algorithm 4 = Algorithm 2 full search + lightweight family-level rescue/safety layer.

## Run

- Cases: `6,000`
- Runtime: `39.82` seconds
- Input: `benchmark_02_synthetic/data/samples/proportional_6000.csv`

## Overall

| metric | value |
| --- | ---: |
| Hit@1 | 81.42% |
| Hit@20 | 93.28% |
| Fair Hit@1 (diagnostic rows excluded) | 81.42% |
| Fair Hit@20 (diagnostic rows excluded) | 93.28% |
| Fair scored cases | 6,000 |
| Diagnostic/unscorable cases | 0 |
| Behavior success | 93.45% |
| Unsafe confident top-1 | 0.00% |
| Missing clarification | 0.00% |
| No result | 0.67% |
| Average candidate pool | 23.72 |

## By Mistake Type

The existing mutation category and the mistake type are independent dimensions. Diagnostic rows remain visible but are excluded from fair retrieval accuracy.

| mistake type | failed rows | share of failures | recovered@20 | behavior success |
| --- | ---: | ---: | ---: | ---: |
| type_2_equal_edit_evidence | 102 | 9.15% | 89.22% | 89.22% |
| type_4_family_variant | 122 | 10.94% | 85.25% | 85.25% |
| type_5_candidate_generation | 374 | 33.54% | 0.00% | 2.67% |
| type_6_candidate_ranking | 517 | 46.37% | 100.00% | 100.00% |

## By Scope / Category

| scope | category | cases | Hit@1 | Hit@20 | behavior | unsafe | no result |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| inside | __ALL__ | 4539 | 84.20% | 93.30% | 93.30% | 0.00% | 0.07% |
| safety | __ALL__ | 940 | 68.19% | 92.77% | 93.62% | 0.00% | 3.94% |
| semi_outside | __ALL__ | 209 | 93.30% | 99.52% | 99.52% | 0.00% | 0.00% |
| smoke | __ALL__ | 312 | 72.76% | 90.38% | 91.03% | 0.00% | 0.00% |
| __ALL__ | __ALL__ | 6000 | 81.42% | 93.28% | 93.45% | 0.00% | 0.67% |
| inside | autocorrect_artifacts | 104 | 0.00% | 4.81% | 4.81% | 0.00% | 0.00% |
| inside | case_sensitivity | 26 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| inside | consonant_frame_wrong_vowels_heavy | 209 | 85.17% | 98.09% | 98.09% | 0.00% | 0.00% |
| inside | double_letter_reduction_expansion | 156 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| inside | four_plus_error_combinations | 209 | 73.21% | 87.56% | 87.56% | 0.00% | 0.96% |
| inside | keyboard_adjacent_sampled | 104 | 88.46% | 96.15% | 96.15% | 0.00% | 0.00% |
| inside | ligature_confusion | 209 | 93.30% | 99.04% | 99.04% | 0.00% | 0.00% |
| inside | multi_char_phonetic_confusion | 261 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| inside | multi_word_name_fragmentation | 104 | 0.00% | 70.19% | 70.19% | 0.00% | 0.00% |
| inside | number_word_confusion | 26 | 80.77% | 92.31% | 92.31% | 0.00% | 0.00% |
| inside | ocr_letter_digit_confusion | 209 | 99.52% | 100.00% | 100.00% | 0.00% | 0.00% |
| inside | ocr_plus_other_error_combined | 156 | 97.44% | 100.00% | 100.00% | 0.00% | 0.00% |
| inside | punctuation_whitespace_copy_paste_artifacts | 52 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| inside | single_char_deletion_position_weighted | 261 | 99.23% | 100.00% | 100.00% | 0.00% | 0.00% |
| inside | single_char_insertion | 157 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| inside | single_letter_phonetic_confusion | 313 | 98.72% | 100.00% | 100.00% | 0.00% | 0.00% |
| inside | single_letter_visual_confusion | 417 | 98.08% | 99.76% | 99.76% | 0.00% | 0.00% |
| inside | speed_typing_errors | 157 | 97.45% | 100.00% | 100.00% | 0.00% | 0.00% |
| inside | three_error_combinations | 261 | 83.14% | 94.25% | 94.25% | 0.00% | 0.00% |
| inside | transposition_position_weighted | 157 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| inside | truncation_doctor_abbreviation | 313 | 8.31% | 63.26% | 63.26% | 0.00% | 0.00% |
| inside | two_error_combinations | 417 | 93.53% | 99.52% | 99.52% | 0.00% | 0.24% |
| inside | wrong_vowels_in_consonant_frame | 261 | 96.17% | 98.85% | 98.85% | 0.00% | 0.00% |
| safety | cancelled_na_drug_lookup | 52 | 94.23% | 100.00% | 100.00% | 0.00% | 0.00% |
| safety | contradictory_form_route | 104 | 80.77% | 100.00% | 100.00% | 0.00% | 0.00% |
| safety | dangerous_ed1_pairs | 261 | 92.72% | 100.00% | 100.00% | 0.00% | 0.00% |
| safety | negative_no_match_expected | 157 | 100.00% | 100.00% | 100.00% | 0.00% | 7.01% |
| safety | score_gap_ambiguity_detection | 209 | 37.80% | 83.73% | 87.56% | 0.00% | 12.44% |
| safety | substring_traps | 157 | 19.11% | 78.34% | 78.34% | 0.00% | 0.00% |
| semi_outside | embedded_form_strength_parsing | 209 | 93.30% | 99.52% | 99.52% | 0.00% | 0.00% |
| smoke | exact_match_baseline | 104 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| smoke | exact_match_with_strength | 104 | 86.54% | 98.08% | 98.08% | 0.00% | 0.00% |
| smoke | keyboard_shift_whole_word | 26 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| smoke | prefix_ambiguity_awareness | 78 | 42.31% | 97.44% | 100.00% | 0.00% | 0.00% |

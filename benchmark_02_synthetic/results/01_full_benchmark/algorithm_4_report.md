# Algorithm 4 Benchmark Report

Algorithm 4 = Algorithm 2 full search + lightweight family-level rescue/safety layer.

## Run

- Cases: `115,000`
- Runtime: `669.71` seconds
- Input: `benchmark_02_synthetic/data/test_cases.csv`

## Overall

| metric | value |
| --- | ---: |
| Hit@1 | 82.12% |
| Hit@20 | 93.41% |
| Fair Hit@1 (diagnostic rows excluded) | 85.87% |
| Fair Hit@20 (diagnostic rows excluded) | 95.65% |
| Fair scored cases | 109,974 |
| Diagnostic/unscorable cases | 5,026 |
| Behavior success | 93.64% |
| Unsafe confident top-1 | 0.00% |
| Missing clarification | 0.00% |
| No result | 0.81% |
| Average candidate pool | 23.47 |

## By Mistake Type

The existing mutation category and the mistake type are independent dimensions. Diagnostic rows remain visible but are excluded from fair retrieval accuracy.

| mistake type | failed rows | share of failures | recovered@20 | behavior success |
| --- | ---: | ---: | ---: | ---: |
| type_2_equal_edit_evidence | 1,954 | 12.57% | 89.15% | 89.15% |
| type_3_unreadable_continuation | 1,792 | 11.53% | 65.62% | 65.62% |
| type_4_family_variant | 721 | 4.64% | 77.39% | 77.39% |
| type_5_candidate_generation | 3,794 | 24.41% | 0.00% | 6.83% |
| type_6_candidate_ranking | 7,279 | 46.84% | 100.00% | 100.00% |

## By Scope / Category

| scope | category | cases | Hit@1 | Hit@20 | behavior | unsafe | no result |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| inside | __ALL__ | 87000 | 84.53% | 93.56% | 93.56% | 0.00% | 0.10% |
| safety | __ALL__ | 18000 | 70.98% | 92.42% | 93.48% | 0.00% | 4.71% |
| semi_outside | __ALL__ | 4000 | 94.38% | 99.35% | 99.35% | 0.00% | 0.00% |
| smoke | __ALL__ | 6000 | 72.43% | 90.23% | 91.35% | 0.00% | 0.08% |
| __ALL__ | __ALL__ | 115000 | 82.12% | 93.41% | 93.64% | 0.00% | 0.81% |
| inside | autocorrect_artifacts | 2000 | 0.00% | 3.65% | 3.65% | 0.00% | 0.00% |
| inside | case_sensitivity | 500 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| inside | consonant_frame_wrong_vowels_heavy | 4000 | 88.28% | 98.90% | 98.90% | 0.00% | 0.03% |
| inside | double_letter_reduction_expansion | 3000 | 99.53% | 99.93% | 99.93% | 0.00% | 0.07% |
| inside | four_plus_error_combinations | 4000 | 74.38% | 89.65% | 89.65% | 0.00% | 1.23% |
| inside | keyboard_adjacent_sampled | 2000 | 94.40% | 98.80% | 98.80% | 0.00% | 0.10% |
| inside | ligature_confusion | 4000 | 95.05% | 99.78% | 99.78% | 0.00% | 0.03% |
| inside | multi_char_phonetic_confusion | 5000 | 99.04% | 99.90% | 99.90% | 0.00% | 0.00% |
| inside | multi_word_name_fragmentation | 2000 | 0.00% | 69.35% | 69.35% | 0.00% | 0.00% |
| inside | number_word_confusion | 500 | 93.00% | 99.20% | 99.20% | 0.00% | 0.00% |
| inside | ocr_letter_digit_confusion | 4000 | 99.50% | 99.85% | 99.85% | 0.00% | 0.15% |
| inside | ocr_plus_other_error_combined | 3000 | 97.23% | 99.50% | 99.50% | 0.00% | 0.17% |
| inside | punctuation_whitespace_copy_paste_artifacts | 1000 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| inside | single_char_deletion_position_weighted | 5000 | 99.10% | 100.00% | 100.00% | 0.00% | 0.00% |
| inside | single_char_insertion | 3000 | 99.37% | 99.97% | 99.97% | 0.00% | 0.00% |
| inside | single_letter_phonetic_confusion | 6000 | 99.32% | 99.90% | 99.90% | 0.00% | 0.08% |
| inside | single_letter_visual_confusion | 8000 | 97.65% | 99.76% | 99.76% | 0.00% | 0.03% |
| inside | speed_typing_errors | 3000 | 98.80% | 100.00% | 100.00% | 0.00% | 0.00% |
| inside | three_error_combinations | 5000 | 81.56% | 95.46% | 95.46% | 0.00% | 0.02% |
| inside | transposition_position_weighted | 3000 | 99.50% | 99.83% | 99.83% | 0.00% | 0.07% |
| inside | truncation_doctor_abbreviation | 6000 | 7.57% | 63.50% | 63.50% | 0.00% | 0.03% |
| inside | two_error_combinations | 8000 | 93.95% | 99.35% | 99.35% | 0.00% | 0.01% |
| inside | wrong_vowels_in_consonant_frame | 5000 | 96.74% | 99.28% | 99.28% | 0.00% | 0.08% |
| safety | cancelled_na_drug_lookup | 1000 | 94.60% | 99.90% | 99.90% | 0.00% | 0.00% |
| safety | contradictory_form_route | 2000 | 81.15% | 99.85% | 99.85% | 0.00% | 0.00% |
| safety | dangerous_ed1_pairs | 5000 | 91.18% | 99.86% | 99.86% | 0.00% | 0.00% |
| safety | negative_no_match_expected | 3000 | 100.00% | 100.00% | 100.00% | 0.00% | 10.07% |
| safety | score_gap_ambiguity_detection | 4000 | 36.00% | 81.55% | 86.35% | 0.00% | 13.65% |
| safety | substring_traps | 3000 | 40.27% | 79.47% | 79.47% | 0.00% | 0.00% |
| semi_outside | embedded_form_strength_parsing | 4000 | 94.38% | 99.35% | 99.35% | 0.00% | 0.00% |
| smoke | exact_match_baseline | 2000 | 100.00% | 100.00% | 100.00% | 0.00% | 0.00% |
| smoke | exact_match_with_strength | 2000 | 85.45% | 98.55% | 98.55% | 0.00% | 0.00% |
| smoke | keyboard_shift_whole_word | 500 | 0.80% | 2.00% | 2.00% | 0.00% | 1.00% |
| smoke | prefix_ambiguity_awareness | 1500 | 42.20% | 95.53% | 100.00% | 0.00% | 0.00% |

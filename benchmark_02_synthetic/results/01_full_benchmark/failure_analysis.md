# V2 Failure Analysis Report

## Algorithm Names

| label | implementation used in older files |
| --- | --- |
| Algorithm 1 | current app evaluator |
| Algorithm 2 | external English fast algorithm |
| Algorithm 3 | master rank-fusion algorithm |

## Failure Definition

A row is counted as failed when any of these is true: expected target is not in top 20, behavior_success is 0, unsafe_confident_top1 is 1, or missing_clarification is 1.

## Overall Failure Counts On The Previous Full V2 Run

| algorithm | cases | any failure | failure rate | retrieval misses | behavior misses | unsafe top-1 | missing clarification | no result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Algorithm 1 | 115,000 | 13,359 | 11.62% | 13,340 | 13,045 | 19 | 20 | 3,247 |
| Algorithm 2 | 115,000 | 18,725 | 16.28% | 9,396 | 10,030 | 7,355 | 11,838 | 1,253 |
| Algorithm 3 | 115,000 | 7,947 | 6.91% | 7,946 | 7,681 | 0 | 1 | 249 |

## Cross-Algorithm Failure Overlap

- All three algorithms failed the same row: `7,206` rows.
- Algorithm 1 and Algorithm 2 failed, but Algorithm 3 recovered: `615` rows.
- Algorithm 3 failed while both child algorithms passed: `8` rows.

## Top Failure Categories

### Algorithm 1

| scope | category | cases | failures | failure rate | main cause |
| --- | --- | ---: | ---: | ---: | --- |
| `inside` | `three_error_combinations` | 5,000 | 2,296 | 45.92% | multi-error typo chain |
| `inside` | `four_plus_error_combinations` | 4,000 | 1,967 | 49.18% | multi-error typo chain |
| `inside` | `autocorrect_artifacts` | 2,000 | 1,963 | 98.15% | word-boundary or autocorrect artifact |
| `inside` | `two_error_combinations` | 8,000 | 1,273 | 15.91% | multi-error typo chain |
| `inside` | `truncation_doctor_abbreviation` | 6,000 | 1,150 | 19.17% | short-prefix / collision ambiguity |
| `safety` | `dangerous_ed1_pairs` | 5,000 | 807 | 16.14% | dangerous_ed1_keyboard_variant_0 |
| `inside` | `multi_word_name_fragmentation` | 2,000 | 756 | 37.80% | word-boundary or autocorrect artifact |
| `safety` | `substring_traps` | 3,000 | 661 | 22.03% | short-prefix / collision ambiguity |
| `safety` | `score_gap_ambiguity_detection` | 4,000 | 349 | 8.72% | short-prefix / collision ambiguity |
| `inside` | `speed_typing_errors` | 3,000 | 301 | 10.03% | single-family typo mutation |
| `inside` | `single_letter_visual_confusion` | 8,000 | 257 | 3.21% | single-family typo mutation |
| `inside` | `ocr_plus_other_error_combined` | 3,000 | 238 | 7.93% | single-family typo mutation |

### Algorithm 2

| scope | category | cases | failures | failure rate | main cause |
| --- | --- | ---: | ---: | ---: | --- |
| `safety` | `substring_traps` | 3,000 | 2,933 | 97.77% | unsafe false-positive confidence |
| `safety` | `dangerous_ed1_pairs` | 5,000 | 2,615 | 52.30% | safety gate failed to ask for clarification |
| `inside` | `truncation_doctor_abbreviation` | 6,000 | 1,987 | 33.12% | unsafe false-positive confidence |
| `inside` | `autocorrect_artifacts` | 2,000 | 1,983 | 99.15% | unsafe false-positive confidence |
| `inside` | `multi_word_name_fragmentation` | 2,000 | 1,912 | 95.60% | unsafe false-positive confidence |
| `inside` | `three_error_combinations` | 5,000 | 1,261 | 25.22% | multi-error typo chain |
| `inside` | `four_plus_error_combinations` | 4,000 | 1,237 | 30.93% | multi-error typo chain |
| `safety` | `score_gap_ambiguity_detection` | 4,000 | 1,011 | 25.27% | short-prefix / collision ambiguity |
| `safety` | `cancelled_na_drug_lookup` | 1,000 | 776 | 77.60% | safety gate failed to ask for clarification |
| `semi_outside` | `embedded_form_strength_parsing` | 4,000 | 630 | 15.75% | context, strength, route, or status handling |
| `inside` | `two_error_combinations` | 8,000 | 559 | 6.99% | multi-error typo chain |
| `smoke` | `keyboard_shift_whole_word` | 500 | 498 | 99.60% | single-family typo mutation |

### Algorithm 3

| scope | category | cases | failures | failure rate | main cause |
| --- | --- | ---: | ---: | ---: | --- |
| `inside` | `autocorrect_artifacts` | 2,000 | 1,931 | 96.55% | word-boundary or autocorrect artifact |
| `inside` | `three_error_combinations` | 5,000 | 1,132 | 22.64% | multi-error typo chain |
| `inside` | `four_plus_error_combinations` | 4,000 | 1,089 | 27.22% | multi-error typo chain |
| `inside` | `truncation_doctor_abbreviation` | 6,000 | 845 | 14.08% | short-prefix / collision ambiguity |
| `inside` | `multi_word_name_fragmentation` | 2,000 | 624 | 31.20% | word-boundary or autocorrect artifact |
| `safety` | `substring_traps` | 3,000 | 536 | 17.87% | short-prefix / collision ambiguity |
| `inside` | `two_error_combinations` | 8,000 | 476 | 5.95% | multi-error typo chain |
| `safety` | `score_gap_ambiguity_detection` | 4,000 | 324 | 8.10% | short-prefix / collision ambiguity |
| `safety` | `dangerous_ed1_pairs` | 5,000 | 276 | 5.52% | dangerous_ed1_deletion_variant_1 |
| `inside` | `ocr_plus_other_error_combined` | 3,000 | 121 | 4.03% | single-family typo mutation |
| `semi_outside` | `embedded_form_strength_parsing` | 4,000 | 108 | 2.70% | context, strength, route, or status handling |
| `smoke` | `keyboard_shift_whole_word` | 500 | 88 | 17.60% | single-family typo mutation |

## Root Causes Across Failed Rows

| algorithm | root cause | failed rows |
| --- | --- | ---: |
| Algorithm 1 | multi-error typo chain | 5,536 |
| Algorithm 1 | word-boundary or autocorrect artifact | 2,719 |
| Algorithm 1 | short-prefix / collision ambiguity | 2,169 |
| Algorithm 1 | single-family typo mutation | 1,767 |
| Algorithm 1 | consonant-frame or wrong-vowel corruption | 199 |
| Algorithm 1 | dangerous_ed1_keyboard_variant_0 | 150 |
| Algorithm 1 | dangerous_ed1_transpose_variant_1 | 129 |
| Algorithm 1 | context, strength, route, or status handling | 127 |
| Algorithm 1 | dangerous_ed1_visual_variant_0 | 124 |
| Algorithm 1 | dangerous_ed1_transpose_variant_0 | 105 |
| Algorithm 1 | dangerous_ed1_deletion_variant_1 | 81 |
| Algorithm 1 | dangerous_ed1_deletion_variant_0 | 74 |
| Algorithm 2 | unsafe false-positive confidence | 7,355 |
| Algorithm 2 | safety gate failed to ask for clarification | 4,622 |
| Algorithm 2 | multi-error typo chain | 2,880 |
| Algorithm 2 | short-prefix / collision ambiguity | 1,541 |
| Algorithm 2 | single-family typo mutation | 829 |
| Algorithm 2 | word-boundary or autocorrect artifact | 632 |
| Algorithm 2 | context, strength, route, or status handling | 579 |
| Algorithm 2 | consonant-frame or wrong-vowel corruption | 123 |
| Algorithm 2 | candidate generation returned no result | 105 |
| Algorithm 2 | dangerous_ed1_keyboard_variant_0 | 21 |
| Algorithm 2 | dangerous_ed1_visual_variant_0 | 12 |
| Algorithm 2 | dangerous_ed1_deletion_variant_0 | 7 |
| Algorithm 3 | multi-error typo chain | 2,697 |
| Algorithm 3 | word-boundary or autocorrect artifact | 2,555 |
| Algorithm 3 | short-prefix / collision ambiguity | 1,709 |
| Algorithm 3 | single-family typo mutation | 448 |
| Algorithm 3 | consonant-frame or wrong-vowel corruption | 142 |
| Algorithm 3 | context, strength, route, or status handling | 111 |
| Algorithm 3 | dangerous_ed1_deletion_variant_1 | 68 |
| Algorithm 3 | dangerous_ed1_deletion_variant_0 | 66 |
| Algorithm 3 | dangerous_ed1_keyboard_variant_0 | 62 |
| Algorithm 3 | dangerous_ed1_visual_variant_0 | 33 |
| Algorithm 3 | candidate generation returned no result | 17 |
| Algorithm 3 | dangerous_ed1_transpose_variant_1 | 11 |

## What The Mistakes Are Coming From

- The hardest failures are not ordinary one-letter typos. They cluster around multi-error chains, wrong-vowel/consonant-frame inputs, autocorrect or word-boundary artifacts, and short-prefix collisions.
- Algorithm 2 has strong retrieval but produces many unsafe confident false positives. Its main weakness is safety behavior, not only ranking.
- Algorithm 1 is safer, but it loses more rows when the query is heavily corrupted or when candidate generation returns no result.
- Algorithm 3 improves the combined behavior by keeping Algorithm 2's recall and Algorithm 1's safety gates, but it still fails when neither child produces the correct family or when the correct family is too low after fusion.
- Manual failures are mostly real-world compound typos: phonetic substitutions, dropped letters, added letters, and middle-of-word corruption. These are not well represented by a single edit operation.

## Manual Failed Cases

| edited input | right name | error type | Algorithm 1 rank/top1 | Algorithm 2 rank/top1 | Algorithm 3 rank/top1 | note |
| --- | --- | --- | --- | --- | --- | --- |
| `optraderolpl` | `optaderol` | phonetic/keyboard letter substitution | 999 / `` | 1 / `OPTADEROL` | 1 / `OPTADEROL` | Looks like a sound-alike or keyboard-neighbor substitution. edit_distance=3. |
| `Auticax` | `ANTI COX II` | multi-character insertion/deletion | 999 / `ATCOCOXIB` | 2 / `ETICOXIA` | 3 / `ETICOXIA` | More than one inserted/deleted character; needs stronger fuzzy candidate generation. edit_distance=4. |
| `couphseed` | `COUGHSED PARACETAMOL CHILDREN OR COUGHSED PARACETAMOL INFANTS` | phonetic/keyboard letter substitution | 999 / `CAVESTIN` | 13 / `CAPOZIDE` | 19 / `CAPOZIDE` | Looks like a sound-alike or keyboard-neighbor substitution. edit_distance=19. |
| `ivybnon` | `IVY BRONCH` | multi-character insertion/deletion | 999 / `IVYGLOB` | 11 / `IVYENO` | 14 / `IVYENO` | More than one inserted/deleted character; needs stronger fuzzy candidate generation. edit_distance=3. |
| `sauovent` | `salbovent` | same-prefix/suffix multi-edit typo | 9 / `SEA VENTALO NASAL` | 2 / `EZYPENT` | 2 / `EZYPENT` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |
| `garaxy` | `garamycin` | multi-character insertion/deletion | 999 / `AGGREX` | 18 / `AGGREX` | 20 / `AGGREX` | More than one inserted/deleted character; needs stronger fuzzy candidate generation. edit_distance=4. |
| `colchicime` | `colchicine` | single edit | 1 / `COLCHICINE` | 1 / `COLCHICINE` | 1 / `COLCHICINE` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `flacton` | `flector` | same-prefix/suffix multi-edit typo | 999 / `FLU CUT N` | 999 / `FLU CUT N` | 999 / `FLU CUT N` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |
| `levohista` | `LEVOHISTAM` | single edit | 1 / `LEVOHISTAM` | 1 / `LEVOHISTAM` | 1 / `LEVOHISTAM` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `oplax` | `OPLEX N OR OPLEX MONO` | same-prefix/suffix multi-edit typo | 5 / `OFLOXACIN` | 7 / `EVOPLEX` | 4 / `EVOPLEX` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |
| `oplox` | `OPLEX N OR OPLEX MONO` | same-prefix/suffix multi-edit typo | 6 / `OFLOX` | 7 / `PELOX` | 5 / `PELOX` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |
| `moxclar` | `e-moxclav` | multi-edit typo | 999 / `MOBILAT` | 1 / `E MOXCLAV` | 1 / `E MOXCLAV` | Compound typo; likely needs manual alias or stronger multi-error handling. edit_distance=2. |
| `Ezogoat` | `Ezogast` | phonetic/keyboard letter substitution | 999 / `ESCITALOBORG` | 1 / `EZOGAST` | 1 / `EZOGAST` | Looks like a sound-alike or keyboard-neighbor substitution. edit_distance=2. |
| `healreptic` | `healioreptic` | multi-character insertion/deletion | 1 / `HEALIOREPTIC` | 1 / `HEALIOREPTIC` | 1 / `HEALIOREPTIC` | More than one inserted/deleted character; needs stronger fuzzy candidate generation. edit_distance=2. |
| `colovarin` | `COLOVERIN D` | same-prefix/suffix multi-edit typo | 5 / `COLOVERIN` | 3 / `COLOVERIN` | 3 / `COLOVERIN` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |
| `Eucavban` | `eucarbon` | same-prefix/suffix multi-edit typo | 3 / `EUCAVAN MASSAGE` | 7 / `KUVAN` | 6 / `KUVAN` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |
| `librux` | `LIBRAX SUGAR` | multi-character insertion/deletion | 1 / `LIBRAX SUGAR` | 2 / `ALPRAX` | 1 / `LIBRAX SUGAR` | More than one inserted/deleted character; needs stronger fuzzy candidate generation. edit_distance=6. |
| `mebula` | `nebula` | single edit | 999 / `MABELLE` | 999 / `MABELLE` | 999 / `MABELLE` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `dexazue` | `dexazone` | same-prefix/suffix multi-edit typo | 4 / `DOXAZIN` | 1 / `DEXAZONE` | 1 / `DEXAZONE` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |
| `octotron` | `OCTATRON` | single edit | 1 / `OCTATRON` | 1 / `OCTATRON` | 1 / `OCTATRON` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `revanoglob` | `Revanoglow` | single edit | 999 / `RHINOGESIC` | 999 / `ELANOGLO` | 999 / `ELANOGLO` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `jvsprin` | `jusprin` | single edit | 1 / `JUSPRIN` | 1 / `JUSPRIN` | 1 / `JUSPRIN` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `mixmail` | `mixmazil` | single edit | 17 / `MAX MILK` | 1 / `MIXMAZIL` | 2 / `MAX MILK` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `puresmin` | `PURESAMINE` | multi-character insertion/deletion | 1 / `PURESAMINE` | 1 / `PURESAMINE` | 1 / `PURESAMINE` | More than one inserted/deleted character; needs stronger fuzzy candidate generation. edit_distance=2. |
| `biato` | `ibiacto` | multi-character insertion/deletion | 999 / `` | 3 / `BEVATO` | 3 / `BEVATO` | More than one inserted/deleted character; needs stronger fuzzy candidate generation. edit_distance=2. |
| `salire` | `saline` | single edit | 11 / `SALURETIC` | 6 / `SALIVER` | 9 / `SALURETIC` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `devamol` | `DEVAROL S` | same-prefix/suffix multi-edit typo | 999 / `TOVOMELLA COATED` | 3 / `CEVAMOL` | 6 / `CEVAMOL` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |
| `calcihon` | `calcitron` | same-prefix/suffix multi-edit typo | 14 / `COLA CHOND` | 3 / `CALCIHANCE` | 4 / `CALCIHANCE` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |
| `broncholrn` | `BRONCHOLIN S` | same-prefix/suffix multi-edit typo | 10 / `BRONCHOPRO` | 1 / `BRONCHOLIN S` | 1 / `BRONCHOLIN S` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |
| `apido` | `apidone` | multi-character insertion/deletion | 1 / `APIDONE` | 2 / `RAPIDO` | 2 / `RAPIDO` | More than one inserted/deleted character; needs stronger fuzzy candidate generation. edit_distance=2. |
| `tavaric` | `tavanic` | single edit | 4 / `TOBRACOID` | 1 / `TAVANIC` | 1 / `TAVANIC` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `flopudex` | `flopadex` | single edit | 1 / `FLOPADEX` | 1 / `FLOPADEX` | 1 / `FLOPADEX` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `metaps` | `metapsin` | multi-character insertion/deletion | 1 / `METAPSIN` | 1 / `METAPSIN` | 1 / `METAPSIN` | More than one inserted/deleted character; needs stronger fuzzy candidate generation. edit_distance=2. |
| `arymentin` | `augmentin` | same-prefix/suffix multi-edit typo | 1 / `AUGMENTIN` | 1 / `AUGMENTIN` | 1 / `AUGMENTIN` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |
| `centerloc` | `controloc` | same-prefix/suffix multi-edit typo | 1 / `CONTROLOC` | 1 / `CONTROLOC` | 1 / `CONTROLOC` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=3. |
| `moxauidey` | `moxavidex` | same-prefix/suffix multi-edit typo | 999 / `MAX DERMO` | 1 / `MOXAVIDEX` | 1 / `MOXAVIDEX` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |
| `codlor` | `codilar` | same-prefix/suffix multi-edit typo | 1 / `CODILAR` | 1 / `CODILAR` | 1 / `CODILAR` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |
| `Duncof` | `Duncef` | single edit | 999 / `DAUNOCIPLA` | 999 / `ADANCOR` | 999 / `DAUNOCIPLA` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `Cndalenz` | `Ondalenz` | single edit | 2 / `CAVALPHA` | 1 / `ONDALENZ` | 1 / `ONDALENZ` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `Duphlac` | `Duphalac` | single edit | 1 / `DUPHALAC` | 1 / `DUPHALAC` | 1 / `DUPHALAC` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `Dophlac` | `Duphalac` | same-prefix/suffix multi-edit typo | 1 / `DUPHALAC` | 1 / `DUPHALAC` | 1 / `DUPHALAC` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |
| `Conlentin` | `Conventin` | single edit | 1 / `CONVENTIN` | 1 / `CONVENTIN` | 1 / `CONVENTIN` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `taves` | `tareg` | same-prefix/suffix multi-edit typo | 999 / `T B ZIDE` | 999 / `MENTAVERS` | 999 / `MENTAVERS` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |
| `cyprocin` | `ciprocin` | single edit | 1 / `CIPROCIN` | 1 / `CIPROCIN` | 1 / `CIPROCIN` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `cyprocen` | `ciprocin` | multi-edit typo | 1 / `CIPROCIN` | 1 / `CIPROCIN` | 1 / `CIPROCIN` | Compound typo; likely needs manual alias or stronger multi-error handling. edit_distance=2. |
| `vonifrton` | `vomifraton` | phonetic/keyboard letter substitution | 2 / `VENORUTON` | 1 / `VOMIFRATON` | 1 / `VOMIFRATON` | Looks like a sound-alike or keyboard-neighbor substitution. edit_distance=2. |
| `awndisb` | `awadist` | phonetic/keyboard letter substitution | 3 / `ACNE JED` | 1 / `AWADIST` | 1 / `AWADIST` | Looks like a sound-alike or keyboard-neighbor substitution. edit_distance=2. |
| `vonaspine` | `vonaspire` | single edit | 1 / `VONASPIRE` | 1 / `VONASPIRE` | 1 / `VONASPIRE` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `Ketostenil` | `Ketosteril` | single edit | 999 / `` | 1 / `KETOSTERIL` | 1 / `KETOSTERIL` | Very close spelling; should be recovered by ordinary edit-distance or alias logic. edit_distance=1. |
| `Ketostenl` | `Ketosteril` | same-prefix/suffix multi-edit typo | 1 / `KETOSTERIL` | 1 / `KETOSTERIL` | 1 / `KETOSTERIL` | Keeps part of the brand but mutates the middle/end; ranker needs better family-level fuzzy matching. edit_distance=2. |

## Manual Case Root-Cause Counts

| manual error type | cases |
| --- | ---: |
| same-prefix/suffix multi-edit typo | 17 |
| single edit | 17 |
| multi-character insertion/deletion | 9 |
| phonetic/keyboard letter substitution | 5 |
| multi-edit typo | 2 |

## Recommended Fixes

1. Add a curated alias layer for repeated real-world misspellings from the manual table. These are high-value because they came from actual manual observation, not synthetic generation.
2. Add stronger candidate generation for compound typos: edit distance 2-4, middle-character substitutions, dropped nasal/liquid consonants, and suffix corruption.
3. Add phonetic rewrite rules for common pairs seen here: c/k/q, s/z, f/v, p/b, d/t, g/j, ch/sh, and Arabic-English hearing mistakes.
4. Keep Algorithm 3's safety gate: do not turn every fuzzy recovery into a confident top-1. Use the new aliases as retrieval evidence, then still require confidence checks for dangerous short or colliding names.
5. Add the manual cases as a small regression file and run them separately from the generated V2 benchmark so real user failures remain visible.

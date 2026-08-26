# Flexible Partial-Text Search Experiment

The generator created 3,499 deterministic requests from 276,742 possible catalog-derived patterns. It tests every two-part full-name boundary, representative three-part names, fragments at arbitrary positions, one injected reading error, and common grapheme compression such as CK to K or PH to F.

Source-family Hit@k measures whether the family used to generate a request is returned. It is diagnostic when another medicine also satisfies the visible evidence. Every displayed result remains confirmation-required. The primary denominator excludes only the single-fuzzy-fragment class: one four-letter fragment, one injected error, and unknown position do not identify one source family. Those rows remain in the pattern table.

## Split Results

| Primary split | Cases | Source H@1 | Source H@20 | Confirmation | No result | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| development | 2656 | 95.37% | 99.89% | 100.00% | 0.00% | 59.19 |
| holdout | 751 | 96.40% | 100.00% | 100.00% | 0.00% | 65.29 |

## Pattern Results

| Pattern | Cases | Source H@1 | Source H@20 | Candidates | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| full_name_three_parts | 197 | 100.00% | 100.00% | 9.6 | 44.33 |
| full_name_two_parts | 2283 | 100.00% | 100.00% | 10.2 | 69.59 |
| one_internal_exact | 134 | 57.46% | 98.51% | 396.1 | 32.35 |
| one_internal_typo | 92 | 2.17% | 44.57% | 297.1 | 27.48 |
| one_prefix_exact | 57 | 64.91% | 100.00% | 315.3 | 29.45 |
| one_prefix_grapheme | 11 | 90.91% | 100.00% | 34.2 | 16.33 |
| one_suffix_exact | 62 | 56.45% | 98.39% | 453.9 | 38.27 |
| three_ordered_exact | 82 | 100.00% | 100.00% | 33.7 | 62.48 |
| three_ordered_middle_typo | 109 | 93.58% | 100.00% | 30.0 | 67.75 |
| two_edges_exact | 152 | 96.05% | 100.00% | 11.4 | 19.22 |
| two_edges_first_typo | 155 | 87.74% | 100.00% | 11.3 | 19.11 |
| two_edges_second_typo | 165 | 92.12% | 100.00% | 8.2 | 16.18 |

## Exhaustive Parity

174 requests were rerun against all 25,066 records. Indexed and exhaustive family orders match in 100.00% of those requests.

## Examples

| Visible input | Pattern | Source family | Top family |
| --- | --- | --- | --- |
| RATI LYALIGHTENING | full_name_two_parts | RATILYA LIGHTENING | RATILYA LIGHTENING |
| FUC ITHA LMIC | full_name_three_parts | FUCITHALMIC | FUCITHALMIC |
| PIROXIF AR | full_name_two_parts | PIROXIFAR | PIROXIFAR |
| VERIOLI GHT | full_name_two_parts | VERIOLIGHT | VERIOLIGHT |
| IGEAMA RINECOLLAGEN | full_name_two_parts | IGEA MARINE COLLAGEN | IGEA MARINE COLLAGEN |
| REMA EMIN | two_edges_second_typo | REMAZAMIN | REMAZAMIN |
| COLO ERIN | two_edges_exact | COLOVERIN | COLOVERIN |
| CERED ERMPLASTERANCHOR22CM | full_name_two_parts | CEREDERM | CEREDERM |

## Acceptance Gates

- PASS: primary source hit at 20 at least 99 percent
- PASS: holdout primary source hit at 20 at least 99 percent
- PASS: primary confirmation rate is 100 percent
- PASS: primary no result rate is zero
- PASS: exhaustive family order parity is 100 percent
- PASS: indexed p95 latency below 150 ms
- PASS: grapheme prefix source hit at 20 at least 97 percent
- PASS: divided full name hit at 1 is 100 percent
- PASS: three part full name hit at 1 is 100 percent

# Algorithm 4 Benchmark Report

Algorithm 4 = Algorithm 2 full search + lightweight family-level rescue/safety layer.

## Run

- Cases: `150`
- Runtime: `34.67` seconds
- Input: `manual cases`

## Overall

| metric | value |
| --- | ---: |
| Hit@1 | 73.33% |
| Hit@20 | 92.00% |
| Fair Hit@1 (diagnostic rows excluded) | 79.26% |
| Fair Hit@20 (diagnostic rows excluded) | 99.26% |
| Fair scored cases | 135 |
| Diagnostic/unscorable cases | 15 |
| Behavior success | 92.00% |
| Unsafe confident top-1 | 0.00% |
| Missing clarification | 0.00% |
| No result | 0.00% |
| Average candidate pool | 29.57 |

## By Mistake Type

The existing mutation category and the mistake type are independent dimensions. Diagnostic rows remain visible but are excluded from fair retrieval accuracy.

| mistake type | failed rows | share of failures | recovered@20 | behavior success |
| --- | ---: | ---: | ---: | ---: |
| type_2_equal_edit_evidence | 11 | 39.29% | 100.00% | 100.00% |
| type_4_family_variant | 1 | 3.57% | 100.00% | 100.00% |
| type_5_candidate_generation | 1 | 3.57% | 0.00% | 0.00% |
| type_6_candidate_ranking | 15 | 53.57% | 100.00% | 100.00% |

## By Scope / Category

| scope | category | cases | Hit@1 | Hit@20 | behavior | unsafe | no result |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| manual | __ALL__ | 150 | 73.33% | 92.00% | 92.00% | 0.00% | 0.00% |
| __ALL__ | __ALL__ | 150 | 73.33% | 92.00% | 92.00% | 0.00% | 0.00% |
| manual | manual_failed_cases | 150 | 73.33% | 92.00% | 92.00% | 0.00% | 0.00% |

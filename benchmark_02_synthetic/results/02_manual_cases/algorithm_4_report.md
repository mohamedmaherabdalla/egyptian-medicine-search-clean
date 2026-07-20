# Algorithm 4 Benchmark Report

Algorithm 4 = Algorithm 2 full search + lightweight family-level rescue/safety layer.

## Run

- Cases: `50`
- Runtime: `17.78` seconds
- Input: `manual cases`

## Overall

| metric | value |
| --- | ---: |
| Hit@1 | 74.00% |
| Hit@20 | 94.00% |
| Fair Hit@1 (diagnostic rows excluded) | 78.72% |
| Fair Hit@20 (diagnostic rows excluded) | 100.00% |
| Fair scored cases | 47 |
| Diagnostic/unscorable cases | 3 |
| Behavior success | 94.00% |
| Unsafe confident top-1 | 0.00% |
| Missing clarification | 0.00% |
| No result | 0.00% |
| Average candidate pool | 29.88 |

## By Mistake Type

The existing mutation category and the mistake type are independent dimensions. Diagnostic rows remain visible but are excluded from fair retrieval accuracy.

| mistake type | failed rows | share of failures | recovered@20 | behavior success |
| --- | ---: | ---: | ---: | ---: |
| type_2_equal_edit_evidence | 2 | 20.00% | 100.00% | 100.00% |
| type_4_family_variant | 1 | 10.00% | 100.00% | 100.00% |
| type_6_candidate_ranking | 7 | 70.00% | 100.00% | 100.00% |

## By Scope / Category

| scope | category | cases | Hit@1 | Hit@20 | behavior | unsafe | no result |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| manual | __ALL__ | 50 | 74.00% | 94.00% | 94.00% | 0.00% | 0.00% |
| __ALL__ | __ALL__ | 50 | 74.00% | 94.00% | 94.00% | 0.00% | 0.00% |
| manual | manual_failed_cases | 50 | 74.00% | 94.00% | 94.00% | 0.00% | 0.00% |

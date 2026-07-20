# DrugEye V2 Benchmark (fuzzy)

This report benchmarks the public DrugEye ASP.NET search page against `benchmark_02_synthetic/data/test_cases.csv`.

Important limitation: DrugEye returns a ranked product list but does not expose a confidence or clarification flag. Therefore this report scores retrieval and simple expected behavior, not unsafe confident top-1 behavior.

## Headline

- Evaluated cases: `10`.
- Live website requests: `0`. Cached duplicate queries do not count here.
- Runtime: `0.00` seconds.
- DrugEye mode: `fuzzy`.

| scope | cases | Hit@1 | Hit@5 | Hit@20 | behavior success | no-result | network error | avg results |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `inside` | 10 | 0.00% | 0.00% | 0.00% | 0.00% | 100.00% | 0.00% | 0.00 |
| `__ALL__` | 10 | 0.00% | 0.00% | 0.00% | 0.00% | 100.00% | 0.00% | 0.00 |

## Category Scores

| scope | category | cases | Hit@1 | Hit@20 | behavior success | no-result | network error |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `inside` | `single_letter_visual_confusion` | 10 | 0.00% | 0.00% | 0.00% | 100.00% | 0.00% |

## Error-Type Scores

| scope | category | error_type | cases | Hit@1 | Hit@20 | behavior success | no-result | network error |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `inside` | `single_letter_visual_confusion` | `visual_A_to_E_pos_0` | 10 | 0.00% | 0.00% | 0.00% | 100.00% | 0.00% |

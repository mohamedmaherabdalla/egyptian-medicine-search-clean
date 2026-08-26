# Unreadable-Text Search Experiment

## Contract

The catalog contains 18,499 distinct full-base or validated family-head targets. Exhaustive masking creates 1,499,280 possible requests. The evaluated sample uses retain all requests with <=2 visible characters; otherwise SHA-256(request) modulo 128 equals zero and contains 10,575 unique requests.

A unique-evidence request matches one catalog family and is scored with Hit@k. An ambiguous request matches several catalog families and is successful when the system returns only valid options and requires confirmation. Mixed development/holdout collisions remain diagnostic and do not enter the locked score.

## Headline Results

| Denominator | Cases | Hit@1 | Hit@20 | Valid top 1 | Behavior | Unsafe top 1 | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Inclusive diagnostics | 10575 | 100.00% | 100.00% | 100.00% | 100.00% | 0.00% | 3.05 |
| Locked overall | 9291 | 100.00% | 100.00% | 100.00% | 100.00% | 0.00% | 2.93 |
| Unique evidence | 8839 | 100.00% | 100.00% | 100.00% | 100.00% | 0.00% | 2.97 |
| Ambiguous evidence | 452 | 100.00% | 100.00% | 100.00% | 100.00% | 0.00% | 2.01 |

## Position Coverage

| Unreadable position | Cases | Hit@1 | Hit@20 | Source H@1 | Source H@20 | p95 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| after | 793 | 100.00% | 100.00% | 99.24% | 100.00% | 3.17 |
| before | 870 | 100.00% | 100.00% | 99.08% | 100.00% | 4.85 |
| middle | 7628 | 100.00% | 100.00% | 99.93% | 100.00% | 2.75 |

## Visible-Evidence Diagnostics

These rows include mixed-split ambiguity. Hit@1 means the first displayed family is valid for the visible pattern; Source H@1 asks whether the arbitrary catalog source used to generate the mask is first and is not a fairness metric when several families match.

| Total visible characters | Cases | Valid top 1 | Result precision | Source H@1 | Source H@20 | Mean candidates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1_character | 62 | 100.00% | 100.00% | 91.94% | 100.00% | 866.16 |
| 2_characters | 1491 | 100.00% | 100.00% | 96.51% | 99.93% | 55.28 |
| 3_characters | 109 | 100.00% | 100.00% | 99.08% | 100.00% | 7.61 |
| 4_characters | 320 | 100.00% | 100.00% | 98.13% | 100.00% | 3.35 |
| 5_6_characters | 1263 | 100.00% | 100.00% | 99.13% | 100.00% | 1.98 |
| 7_plus_characters | 7330 | 100.00% | 100.00% | 99.95% | 100.00% | 1.32 |

## Baseline Comparison

The indexed strategy changes 0 returned family orders, gains 0 Hit@1 cases, and loses 0. Full-scan p95 latency is 5.78 ms; indexed p95 latency is 2.93 ms.

## Development-Only Ranking Tuning

The gap penalty prefers a medicine requiring fewer hidden characters when several catalog families satisfy the same visible pattern. It was selected only on locked development-family ambiguous requests. Source H@k is a parsimony diagnostic here, not a claim that other matching families are wrong.

| Penalty per hidden character | Cases | Source H@1 | Source H@20 | Valid top 1 | Result precision |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 432 | 48.15% | 100.00% | 100.00% | 100.00% |
| 15 | 432 | 87.27% | 100.00% | 100.00% | 100.00% |
| 30 | 432 | 88.43% | 100.00% | 100.00% | 100.00% |
| 45 | 432 | 89.58% | 100.00% | 100.00% | 100.00% |
| 60 | 432 | 90.97% | 100.00% | 100.00% | 100.00% |
| 90 | 432 | 92.82% | 100.00% | 100.00% | 100.00% |
| 120 | 432 | 93.06% | 100.00% | 100.00% | 100.00% |
| 150 | 432 | 93.75% | 100.00% | 100.00% | 100.00% |
| 180 | 432 | 93.98% | 100.00% | 100.00% | 100.00% |
| 240 | 432 | 94.91% | 100.00% | 100.00% | 100.00% |
| 300 | 432 | 95.37% | 100.00% | 100.00% | 100.00% |
| 450 | 432 | 95.83% | 100.00% | 100.00% | 100.00% |
| 600 | 432 | 95.83% | 100.00% | 100.00% | 100.00% |

Selected penalty: 450. The runtime default is 450.

## Acceptance Gates

- PASS: unique hit at 20 at least 99 percent
- PASS: valid top 1 is 100 percent
- PASS: behavior success is 100 percent
- PASS: inclusive behavior success is 100 percent
- PASS: inclusive result precision is 100 percent
- PASS: unsafe confident top 1 is zero
- PASS: inclusive unsafe confident top 1 is zero
- PASS: no hit at 1 regression vs full scan
- PASS: p95 latency not worse than full scan
- PASS: selected penalty matches runtime default

## Remaining Top-20 Misses

No locked indexed request misses every relevant family in the top 20.

## Source-Family Ambiguity Examples

These are not relevance failures. The displayed medicines all satisfy the visible pattern; the source family falls outside the first 20 only because the request admits many valid catalog completions.

| Mode | Visible input | Ending | Generator source | First valid result | Valid family count |
| --- | --- | --- | --- | --- | ---: |
| after | HI | - | H IRON | HI PAN | 57 |

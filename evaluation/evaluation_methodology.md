# Evaluation Methodology

This repository includes only the evaluation methodology, not the private evaluation cases or result tables.

## Evaluation Goal

The goal is to test whether the search system retrieves the correct medicine, family, or ingredient target under realistic query conditions. The system is evaluated as ranked retrieval, not as a single yes/no classifier.

## Evaluation Groups

| group | what it tests |
| --- | --- |
| Exact product search | A clean product name should return the exact product at the top. |
| Compact product search | Missing punctuation or spaces should still retrieve the right product. |
| Prefix search | Short typed prefixes should retrieve candidate sets without acting overconfident. |
| Typo search | Small edit-distance mistakes should still retrieve the intended product or family. |
| Heard-spelling search | Names written by sound should retrieve the intended brand family when possible. |
| Base-family search | Brand-only queries should retrieve variants under the correct family. |
| Ingredient search | Generic or active-ingredient queries should retrieve matching products. |
| Route/form search | Form hints should improve ranking for tablet, syrup, injection, topical, and similar forms. |
| Strength search | Strength hints should boost matching product variants. |
| Warning behavior | Rows with known data-quality issues should surface visible warnings. |
| Ambiguity behavior | Ambiguous queries should require confirmation instead of forcing one product. |
| Negative/OOV behavior | Unknown or unsafe queries should avoid confident false matches. |

## Relevance Levels

| level | meaning |
| --- | --- |
| Exact product | The returned candidate is the expected product row. |
| Brand family | The returned candidate belongs to the expected brand/base family. |
| Ingredient family | The returned candidate has the expected ingredient/composition family. |
| Irrelevant | The returned candidate does not match the expected target. |

## Ranking Metrics

The evaluation checks whether relevant results appear near the top of the ranked list:

- `Hit@1`: relevant result appears at rank 1.
- `Hit@5`: relevant result appears in the first 5 results.
- `Hit@10`: relevant result appears in the first 10 results.
- `Hit@20`: relevant result appears in the first 20 results.
- `MRR@20`: rewards the first relevant result appearing earlier.
- `MAP@20`: rewards multiple relevant results appearing early.
- `nDCG@20`: rewards stronger relevance levels higher in the ranking.

## Safety Checks

The evaluation also checks behavior that matters specifically for medicine lookup:

- weak fuzzy matches should not look like exact matches
- broad prefixes should not produce confident single-result behavior
- ambiguous brand families should require confirmation
- required warnings should be visible
- negative queries should not produce confident false positives

## Output Policy

The detailed test cases, per-case results, and metric tables are intentionally not included in this clean repository. They can be regenerated or audited privately, while this file documents what was evaluated and why.


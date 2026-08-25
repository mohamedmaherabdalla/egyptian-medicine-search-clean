# Fresh evaluation protocol for the team handbook

This protocol replaces the earlier mixed historical accuracy story.  Every
headline result in the new handbook must come from the exact latest source or
be labeled explicitly as historical context.

## Frozen candidate identity

| Component | SHA-256 |
| --- | --- |
| Algorithm 5 | `c5faefb2bfb54c4dfbe4a059b120aaa4121db3c2bdf0606ab0cdef4f56bbbee7` |
| Algorithm 6 | `cedf1fce3dac214f5533707c031051efec7343aa8d4342e9ddf7cfe31940fbcb` |
| Product reranker | `03780539f9449323a641ab6ad9d2f505f0ed167e6741c63c858bc0b7d873caea` |
| API adapter | `752399eec3caf486d1242d61d9176625cd0e42605e6553487e466bd56b8bc6de` |
| Catalog | `d234edaa2669d1eeb46b962e7e3e02df52c6f4d2fd3eca7a2fbf3bc7d159fd9c` |

The Git worktree is intentionally dirty because the final visual-gap repairs
are later than commit `7ed39d0`.  Actual file hashes, not the older commit
label, are the authority for every current run.

## Evidence classes

### Accuracy benchmark

A fixed labeled population scored with Hit@1/5/20, MRR, strict product ID, or
another explicitly defined accuracy metric.  Algorithms may be compared only
on identical rows, relevance labels, catalog, limits, and evaluator version.

### Safety benchmark

Measures exact-name protection, ambiguity preservation, forbidden results,
correct abstention, or cross-mode isolation.  Report the safety event rate and
denominator; do not call the pass fraction population accuracy.

### Developer regression

Known, generated, boundary, performance, or failure-derived contracts.  These
must pass after a repair, but their pass percentage is rule conformance rather
than general accuracy.

## Current and new datasets

| Dataset | Evidence class | What it tests | Current status |
| --- | --- | --- | --- |
| Reviewed fair OCR 412 | Frozen retrospective accuracy/non-regression benchmark | Natural reviewed OCR strings and acceptable exact families | Fresh final-source rerun required for the handbook artifact. |
| Ordinary typo benchmark | Catalog-generated accuracy benchmark | Insertion, deletion, substitution, transposition, keyboard, spacing, and multi-edit retrieval without visual/OCR dispatch | Being generated with family/collision-safe splits. |
| OCR/grapheme generated + challenge | Accuracy strata plus regression/safety | Every registered direction, operation count, exact guards, ambiguity, and non-transitivity | Existing cases will be reclassified and rerun on the final source. |
| Visual-gap benchmark | Catalog-derived accuracy strata plus regression/safety | Leading, trailing, internal, both-edge, multi-gap, shorthand, collisions, parser boundaries, alignment, and latency | Existing 404 rows will be reclassified; additional false-dispatch and projection cases are pending. |
| Strict product selection 440 | Catalog-derived product-ID benchmark and safety set | Unique strengths, legitimate ties, same-strength form disambiguation, and impossible-strength abstention | Fresh final-source result: 440/440 after five independent-oracle defects were repaired. |
| Product-context recovery 200 | Paired family-level regression benchmark | Whether exact context corrects a mutated family query | Existing evaluator must be strengthened before any strict product-ID claim. |
| Cross-mode safety | Metamorphic safety benchmark | Ordinary punctuation vs gap syntax, visual plus context, numeric alias isolation, and API identity | Pending generation and execution. |

## Failure workflow

1. Freeze source, catalog, generator, evaluator, and dataset hashes.
2. Generate without calling or reading output from the system under test.
3. Save every raw response and per-case result.
4. Preserve every failure.
5. Classify it as source, label/oracle, evaluator, API/display, or environment.
6. Change the narrowest justified component.
7. Regenerate only when the oracle or labels were wrong, with a versioned
   failure record.
8. Rerun the failed stratum and all downstream regression/safety denominators.
9. Publish limitations next to the metric.

## Handbook rule

The team PDF will show, for every dataset:

- what inputs it contains;
- concrete examples;
- how cases and acceptable answers were generated;
- development, holdout, challenge, and safety counts;
- the exact metric and what it does not mean;
- first-run failures, root causes, repairs, and final rerun result;
- source/catalog/dataset identity in the technical footer.

Historical 464-case competitor numbers and carried-forward clean metrics may
appear only in a version-history appendix.  They cannot be used as the current
algorithm headline.

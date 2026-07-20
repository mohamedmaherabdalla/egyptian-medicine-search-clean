# Algorithm 4 Failure-Fix Design

Algorithm 4 was built after reviewing the 50 manually supplied failures and the
full V2 failure report. The first draft included an observed-alias table for
those 50 cases. That was removed because it memorized benchmark answers and
invalidated the manual-case score. The corrected Algorithm 4 has no hard-coded
manual-case mappings.

## Short Version

```text
query
  -> Algorithm 2 full search
  -> optional context-clean Algorithm 2 pass for strength/form noise
  -> optional bounded family rescue
  -> merge by commercial family
  -> conservative clarification/safety gate
```

The important difference:

```text
Algorithm 3 = Algorithm 1 full query + Algorithm 2 full query + fusion
Algorithm 4 = Algorithm 2 full query + small gated rescue/context layers
```

Algorithm 4 is not an alias table. It uses general catalog-derived evidence:
compact keys, prefix/suffix evidence, n-grams, consonant skeletons, phonetic
keys, delete keys, weighted edit similarity, and safety gates.

## Where The 50 Manual Errors Came From

The detailed row-level artifact is:

- `benchmark_02_synthetic/docs/manual_failed_cases_deep_analysis.md`
- `benchmark_02_synthetic/results/02_manual_cases/deep_analysis.csv`

The 50 cases break down as:

| pattern | cases | meaning |
| --- | ---: | --- |
| `single_edit` | 21 | One-character typo, but close catalog neighbors can still outrank the target. |
| `same_edges_middle_corruption` | 9 | Prefix/suffix survive while the middle of the brand is corrupted. |
| `multi_substitution` | 8 | Several same-length substitutions need weighted phonetic/edit evidence. |
| `prefix_with_gap_insertion_deletion` | 7 | Missing or inserted middle characters create a gap. |
| `compound_typo` | 4 | Multiple typo types happen in one query. |
| `short_name_ambiguous_typo` | 1 | Short typo with weak evidence and high ambiguity risk. |

The practical root causes were:

1. The correct family was not generated strongly enough.
2. The correct family was generated but ranked below a wrong catalog neighbor.
3. Compound real-world typos remain hard without memorizing the answer.
4. Fuzzy recovery must not become automatic confident medical selection.

## Algorithm 4 Fixes

### 1. Family-Level Rescue Index

Algorithm 4 builds a rescue index over unique commercial families, not every
catalog product row. It stores:

| index | why it exists |
| --- | --- |
| exact compact key | direct family recovery |
| prefix and suffix keys | same-edge typo recovery |
| rare 3/4 character grams | middle evidence without scanning all families |
| consonant skeleton | wrong-vowel recovery |
| phonetic key | sound-alike recovery |
| delete keys | insertion/deletion recovery |
| length and first-character buckets | bounded fallback for typo-heavy queries |
| prefix-risk counts | identify short dangerous prefixes |
| warning metadata | avoid confidence for risky catalog records |

Before expensive edit scoring, rescue candidates are prefiltered with cheap
signals. The core rescue prefilter is capped at `45` families, with at most
`15` additional two-character-edge candidates and `8` family-head candidates;
the returned list is still bounded by the requested output limit.

### 2. No Manual-Case Hardcoding

The corrected implementation does not map any of the 50 manual inputs directly
to expected outputs. The manual set is now a real regression benchmark again:
Algorithm 4 either recovers a case using general search evidence, or it fails it.

### 3. Conditional Rescue Gate

Algorithm 4 does not run rescue equally for every query. Rescue runs when:

- Algorithm 2 returns no candidates;
- Algorithm 2 is uncertain, low scoring, or has a small top-score gap;
- the query shape looks typo-heavy enough to justify bounded family rescue.

For low-confidence Algorithm 2 responses, rescue is skipped when the query is
long enough and Algorithm 2 still has a stable top result. This keeps the
quality gain while avoiding unnecessary rescue work.

### 4. Context-Clean Pass

Algorithm 4 added a second, optional Algorithm 2 pass for context-heavy queries.
It removes strength/form/unit noise such as `500MG`, `60 ML`, `tablet`, `caps`,
`vial`, `drops`, and split `F C` only when another real context marker exists.

This specifically improved:

- `embedded_form_strength_parsing`
- `exact_match_with_strength`

### 5. Conservative Safety Gate

Algorithm 2 had strong retrieval but unsafe confident top-1 behavior. Algorithm
4 keeps retrieval, but fuzzy or risky recovered candidates require clarification.
That is why unsafe confident top-1 stayed at `0.00%` on manual, sample, and full
V2 runs.

### 6. Root-Cause Recommendation Pass

The attached recommendation file separated the remaining manual failures into
four groups. Algorithm 4 now applies the general parts of those recommendations,
without adding a lookup table:

| recommendation | implemented as | reason |
| --- | --- | --- |
| Do not over-trust the first character | first-character variants during prefix and length-bucket rescue | Handles cases like `mebula` where the first letter may be wrong. |
| Improve edit-distance ties | same-position score, length-coverage score, stronger full-word edit evidence | Helps distinguish candidates with equal edit distance. |
| Do not let prefix-only evidence outrank full-word fuzzy evidence | partial-prefix penalty when edit evidence is weak | Avoids cases where a short prefix beats a closer full-word candidate. |
| Treat confusable letters as nearby, not exact | expanded confusion groups including `M/N` plus weighted substitution cost | Models realistic visual/phonetic substitutions without memorizing inputs. |
| Do not force genuinely closer wrong-looking answers | documented as evaluator/family-equivalence work | Cases such as `levohista`, `colovarin`, and `octotron` may be acceptable-alternative or family-grouping issues. |

This pass improved the 50-case manual set, but it was not a pure global win.
It increased rescue work and slightly moved some full-V2 ranks. That tradeoff is
why the result is documented separately from the earlier no-hardcode baseline.

## Complexity

Using:

| symbol | meaning |
| --- | --- |
| `N` | catalog product rows |
| `F` | unique commercial families, `F <= N` |
| `L` | average compact family-name length |
| `Q` | query length |
| `C_rescue` | bounded rescue family candidates |
| `R` | merged Algorithm 4 candidate count |

Preprocessing:

```text
Algorithm 2 preprocessing + O(F * L^2)
```

Query time:

```text
Algorithm 2 query
  + optional context-clean Algorithm 2 query
  + O(R log R)
  + optional O(C_rescue * Q * L)
```

The rescue term is bounded by prefiltering and the cap of `40` prefiltered
families.
Algorithm 4 still avoids Algorithm 1's full query path.

## Verified Results

### Manual Failed Cases

This is the corrected result after removing the hard-coded alias table.

| metric | value |
| --- | ---: |
| cases | 50 |
| Hit@1 | 74.00% |
| Hit@20 | 94.00% |
| behavior success | 94.00% |
| unsafe confident top-1 | 0.00% |
| missing clarification | 0.00% |
| no result | 0.00% |
| average candidate pool | 29.88 |

The current path recovers `flacton -> FLECTOR` at rank 1. The three top-20
misses have expected targets absent from the catalog used by the evaluator;
the remaining top-1 misses are ranking, equal-evidence, or variant-selection
cases rather than hard-coded exceptions.

### 6,000-Row Proportional Sample

| algorithm | Hit@1 | Hit@20 | behavior | unsafe top-1 | no result | avg candidate pool |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Algorithm 1 | 75.28% | 88.58% | 88.87% | 0.02% | 2.83% | 186.83 |
| Algorithm 2 | 79.07% | 91.70% | 91.00% | 6.88% | 0.00% | 17.97 |
| Algorithm 3 | 80.83% | 93.13% | 93.37% | 0.00% | 0.00% | 37.88 |
| Algorithm 4 | 81.40% | 93.28% | 93.45% | 0.00% | 0.67% | 23.72 |

### Full V2 Run

| algorithm | runtime | Hit@1 | Hit@20 | behavior | unsafe top-1 | no result | avg candidate pool |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Algorithm 1 | included in 152.44s combined 1/2 run | 75.26% | 88.40% | 88.66% | 0.02% | 2.82% | 188.85 |
| Algorithm 2 | included in 152.44s combined 1/2 run | 79.30% | 91.84% | 91.29% | 6.40% | 1.09% | 17.86 |
| Algorithm 3 | 161.88s | 81.03% | 93.09% | 93.33% | 0.00% | 0.22% | 37.69 |
| Algorithm 4 | 669.71s | 82.12% | 93.41% | 93.64% | 0.00% | 0.81% | 23.47 |

## Engineering Decision

Algorithm 4 is still useful, but the corrected story is narrower:

- it beats Algorithm 1 and Algorithm 2 on full V2 Hit@1, Hit@20, and behavior;
- it beats Algorithm 3 on Hit@1, Hit@20, and behavior success in the latest
  full run;
- it keeps unsafe confident top-1 at `0.00%`;
- it uses a smaller average candidate pool than Algorithm 3;
- it does not execute Algorithm 1's full query path at runtime;
- it does **not** solve all 50 manual cases without hardcoding, so those cases
  remain a separate improvement target.

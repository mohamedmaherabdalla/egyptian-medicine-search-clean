# Retrieval Experiments And Meeting 10

> **Continuation-branch scope.** The focused Algorithm 6 tests, experiment
> source, unreadable-text cases, compact tables, and Markdown documentation are
> included. Full competitor/ablation matrices, raw model/API outputs, and
> caches remain archival. Current fair-OCR and clean-regression gates use
> `../algorithm_6_rule_evaluation/test_sets/locked/fair_ocr_412.csv` and
> `../algorithm_6_rule_evaluation/test_sets/locked/synthetic_clean_66257.csv`;
> the complete historical experiment command below additionally needs the
> omitted row-level artifacts.

## Algorithm 6 Evidence-Gated Consensus

Algorithm 6 is the current Python search system. It preserves Algorithm 5's
rank-1 order and may add one independently supported family at rank 20 when the
base top 20 missed it. The experiment also audits supplied labels, learns
directional OCR confusion costs from development rows, evaluates an advisory
LightGBM reranker, and fits a target-family-cross-fitted selective correctness
gate. The learned ranker and broad rank-1 gate are not deployed.

Run the complete OCR and 66,257-pair synthetic experiment:

```bash
PYTHONPYCACHEPREFIX=/tmp/medicine-search-pycache \
MPLCONFIGDIR=/tmp/matplotlib-cache LOKY_MAX_CPU_COUNT=8 \
  benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/run_algorithm_6_experiment.py
```

Regenerate Meeting 10 tables and figures:

```bash
MPLCONFIGDIR=/tmp/matplotlib-cache PYTHONDONTWRITEBYTECODE=1 \
  benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/analyze_meeting_10.py
```

TeX/PDF reports are intentionally kept out of GitHub; use the Markdown docs,
compact tables, and presenter script directly.

Validate the prepared pharmacist-study schedule:

```bash
benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/pharmacist_study.py validate
```

Canonical outputs:

- Deployed implementation:
  `../benchmark_01_legacy/master_algorithms/algorithm_6_consensus_search.py`
- Learned policy:
  `../benchmark_01_legacy/master_algorithms/algorithm_6_policy.json`
- Evaluation and split contract:
  `results/07_algorithm_6/evaluation_contract.csv`
- Label audit queue:
  `artifacts/07_algorithm_6/ocr_label_audit_queue.csv`
- OCR and synthetic row-level outputs:
  `artifacts/07_algorithm_6/algorithm_6_ocr_results.csv.gz` and
  `algorithm_6_synthetic_results.csv.gz`
- Aggregate, ablation, calibration, and runtime evidence:
  `results/07_algorithm_6/algorithm_6_summary.json`
- Complete Algorithm 6 component and candidate-source ablations:
  `results/07_algorithm_6/algorithm_6_replay_metrics.csv`
- Egyptian Arabic and English code-switched presenter script for all 44 slides:
  `docs/algorithm_6_internal_pipeline_presenter_script_ar.md`
- Meeting 10 aggregate tables: `results/04_meeting_10/`

Headline results use the locked denominators. On 464 OCR pairs, Algorithm 6
keeps Hit@1 at 50.4310% and raises Hit@20 from 72.8448% to 73.2759% through two
paired gains and zero losses. On 66,257 synthetic pairs, Hit@1 remains 98.1889%
and Hit@20 remains 99.9985%. Both OCR gains still need source-crop review, and
the 93-pair historical holdout is retrospective rather than fresh blind data.

Algorithm 6 component ablation is end to end. Each run removes one internal
Algorithm 5 retrieval, scoring, reranking, context, or safety component, then
reruns Algorithm 6's nine extra sources and bounded consensus gate. It does not
compare complete Algorithm 6 with an opaque Algorithm 5 score. On OCR, removing
family rescue causes the largest loss: Hit@20 falls from 73.2759% to 56.0345%.
Removing weighted edit similarity lowers Hit@20 to 66.1638%, and removing all
deterministic reranking lowers Hit@1 from 50.4310% to 40.5172%. Paired gain and
loss counts remain part of every result because overlapping components make
percentage-point effects non-additive.

The 124 remaining OCR top-20 misses also carry source-level evidence. Ninety-seven
targets are absent from all ten source top-20 lists, 26 appear in only one or two
sources and fail a similarity gate, and one appears in four sources but fails
the 0.55 Levenshtein threshold. No missed target passes all insertion gates and
then loses the single external slot.

## Expanded Competitor And Algorithm 5 Study

Run group `06_competitor_benchmark` compares 53 systems on the same two locked
denominators:

- 464 collision-free unique OCR query-target pairs;
- 66,257 unique synthetic clean-core query-target pairs.

The roster contains six cached classical baselines, cached Algorithms 1-4,
42 newly executed external configurations, and Algorithm 5. Algorithms 1-3 are
not rerun; their existing row-level predictions are reused after exact case-ID
validation. The 75-entry repository inventory records every reviewed source as
`evaluated`, `cached`, `represented`, `duplicate`, or `excluded`.

Install the pinned Fuse.js and FlexSearch dependencies once:

```bash
npm --prefix benchmark_04_experiments ci
```

Run all newly evaluated competitors:

```bash
PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/run_competitor_benchmark.py --dataset both
```

Rebuild the competitor-only aggregate table from cached row-level artifacts
without executing a search method again:

```bash
PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/run_competitor_benchmark.py --aggregate-only
```

Run the 97-configuration Algorithm 5 OCR ablation and the 13-configuration
synthetic confirmation:

```bash
PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/run_algorithm_5_ablations.py \
  --dataset ocr --profile all

PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/run_algorithm_5_ablations.py \
  --dataset synthetic --profile synthetic_confirmation --jobs 3
```

Generate paired statistics, error slices, failure examples, ablation tables,
and figures:

```bash
MPLCONFIGDIR=/tmp/matplotlib-cache PYTHONDONTWRITEBYTECODE=1 \
  benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/analyze_competitor_benchmark.py
```

Canonical outputs:

- Competitor inventory: `results/06_competitor_benchmark/competitor_inventory.csv`
- Competitor-only aggregate metrics:
  `results/06_competitor_benchmark/competitor_metrics.csv`
- Combined leaderboard: `results/06_competitor_benchmark/analysis/combined_leaderboard.csv`
- All system error slices: `results/06_competitor_benchmark/analysis/all_system_error_slices.csv`
- Algorithm 5 failure taxonomy: `results/06_competitor_benchmark/analysis/a5_failure_taxonomy.csv`
- Algorithm 5 feature and outcome correlations:
  `results/06_competitor_benchmark/analysis/a5_feature_correlations.csv`
- Algorithm 5 ablations: `results/06_competitor_benchmark/analysis/a5_ocr_ablation_effects.csv`
  and `a5_synthetic_ablation_effects.csv`
- Complete Algorithm 5 OCR failure audit:
  `results/06_competitor_benchmark/analysis/a5_remaining_ocr_failures.csv`
- Maintained analysis tables:
  `results/06_competitor_benchmark/analysis/`

## Primary Synthetic Retrieval File

Run group `05_synthetic_clean_core` uses
`data/05_synthetic_clean_core/test_cases.csv` as the main synthetic retrieval
denominator. It contains 66,257 distinct, catalog-resolvable query-target pairs;
every row has `expected_behavior=match` and `use_in_primary_score=1`. The older
115,000-row file remains under `benchmark_02_synthetic/` because it also tests
exact matches, ambiguity, no-match behavior, and diagnostic collisions.

The imported CSV is byte-identical to commit `47706ad` on the external
`search_evaluation` branch. SHA-256:
`65f81b58dee1e7127386652383d2f6a8db1734e832dcbc73f14a9b831678886f`.

Canonical outputs:

- Human-readable analysis: this README and the Markdown documentation under
  `docs/`
- Long-form grouped metrics: `results/05_synthetic_clean_core/metrics.csv`
- Paired comparisons: `results/05_synthetic_clean_core/paired_comparisons.csv`
- Row-level results: `artifacts/05_synthetic_clean_core/case_results.csv.gz`
  (lossless GitHub-safe archive; readers transparently fall back to it)
- Algorithm 5 failure summary: `results/05_synthetic_clean_core/a5_failure_analysis.csv`
- Algorithm 5 row-level failure audit: `artifacts/05_synthetic_clean_core/a5_failure_audit.csv`

Run the complete fixed roster and build the analysis tables:

```bash
PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/run_synthetic_clean_core.py

PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/analyze_synthetic_clean_core.py
```

Run Algorithm 5 again in an independent output directory, then include the
row-level reproducibility check in the report tables:

```bash
PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/run_synthetic_clean_core.py \
  --algorithms algorithm_5_evidence_rescue \
  --results-dir /tmp/a5_full_rerun/results \
  --artifacts-dir /tmp/a5_full_rerun/artifacts

PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/analyze_synthetic_clean_core.py \
  --fresh-a5-results /tmp/a5_full_rerun/artifacts/case_results.csv
```

## Meeting 10 Record

This file is the running technical record for Meeting 10. It keeps the inputs,
definitions, experiments, results, examples, and decisions needed for later
tasks in one place. Values below come from canonical row-level benchmark files,
not manually selected cases.

This benchmark follows the shared contract in
[`../docs/evaluation.md`](../docs/evaluation.md); its combined result tables use
an `experiment` column so retrieval and ablation rows remain distinguishable.

## 1. What Was Tested

The OCR experiment starts after OCR. Its input is the text predicted by one of
14 OCR models, for example `MYMLAX`. Algorithm 4 searches 25,066 Egyptian
medicine records and returns ranked commercial families. The evaluator then
compares the ranking with the hidden verified family, for example `MYOLAX`.

```text
prescription crop -> OCR model -> OCR text -> Algorithm 4 -> ranked families
                                      |                         |
                                      +-- MYMLAX                +-- MYOLAX at rank 1
```

The verified target never enters Algorithm 4. It is used only after retrieval
to calculate Hit@1 and Hit@20.

Canonical inputs:

- OCR search cases: `benchmark_03_ocr/artifacts/04_model_predictions/search_cases.csv`
- OCR Algorithm 4 results: `benchmark_03_ocr/artifacts/04_model_predictions/algorithm_4_results.csv`
- Synthetic 115k Algorithm 4 rows: `benchmark_02_synthetic/artifacts/01_full_benchmark/algorithm_4_cases.csv`

Meeting 10 outputs:

- Plain-English experiment explanation: this README and the Markdown files
  under `docs/`
- Aggregate OCR factors: `results/04_meeting_10/analysis_metrics.csv`
- OCR denominator audit: `results/04_meeting_10/denominator_metrics.csv`
- Equal-distance rule comparison: `results/04_meeting_10/equal_distance_rule_metrics.csv`
- Candidate-level tie evidence: `artifacts/04_meeting_10/equal_distance_cases.csv`
- Six-type synthetic analysis: `results/04_meeting_10/synthetic_mistake_metrics.csv`
- Synthetic fair-score audit: `results/04_meeting_10/synthetic_denominator_metrics.csv`
- Retrieval and A4 ablation metrics: `results/metrics.csv`
- Retrieval and A4 paired tests: `results/paired_comparisons.csv`
- Gained and lost examples: `results/comparison_examples.csv`
- Row-level retrieval and ablation results: `artifacts/case_results.csv`
- Per-system OCR mistake profiles: `results/04_meeting_10/retrieval_error_profiles.csv`
- One ranking and retrieval failure per system: `artifacts/04_meeting_10/retrieval_failure_examples.csv`
- Fair metrics for Algorithms 1--4: `results/04_meeting_10/synthetic_fairness_by_algorithm.csv`
- Fair-exclusion category audit: `results/04_meeting_10/synthetic_collision_distribution.csv`

The `experiment` column separates `retrieval` from `ablation`; compatible
tables are not duplicated into one directory per experiment. Pharmacist-study
and Meeting 10 files remain separate because their schemas and evaluation units
are different.

## 2. Denominators and Fair Scoring

The OCR CSV contains 595 observations, not 595 independent medicines. Several
OCR models can emit the same query for the same target. Four denominators answer
different questions.

| Denominator | Cases | What receives one vote | Hit@1 | Hit@20 |
|---|---:|---|---:|---:|
| Inclusive observations | 595 | Every supplied OCR row | 50.25% | 73.78% |
| Scored observations | 578 | Every row except 17 real-drug collisions | 51.73% | 75.61% |
| All unique pairs | 477 | Each distinct compact query-target pair | 46.33% | 69.60% |
| Primary fair unique | 464 | Each distinct pair except 13 unique collisions | 47.63% | 71.12% |

The primary 464-pair score is the algorithm-comparison result. The inclusive
595-row score is the data-audit result. Removing collisions raises unique-pair
Hit@1 by 1.30 percentage points and Hit@20 by 1.52 points. Deduplication lowers
the score because repeated observations were easier than the average distinct
pair.

A real-drug collision means the OCR output is already the exact name of another
catalog family. `KETOLAC -> KETOROLAC`, `NEURONTIN -> NEUROCET`, and
`VIAGRA -> VIGOREX` are diagnostic rows, not fair single-answer questions. A
search system should prefer the exact entered medicine unless the image or user
supplies more evidence.

## 3. What the 0.60 Extreme Threshold Means

The threshold is not "60% of the data." For compact OCR query `q` and compact
target `y`, the cohort rule is:

```text
normalized distance = Levenshtein(q, y) / length(y)
extreme = normalized distance > 0.60
```

There are 121 extreme observations, 20.34% of the 595 rows. They contain 113
distinct primary pairs. Algorithm 4 reaches 0.00% Hit@1 and 8.26% Hit@20 on
these rows: 10 targets appear at ranks 2-20 and 111 are outside the top 20.

### 3.1 Extreme Mistake Distribution

| View | Group | Rows | Share of extreme | Hit@20 |
|---|---|---:|---:|---:|
| Mistake type | Multi-edit OCR error | 119 | 98.35% | 7.56% |
| Mistake type | Two/three-edit error | 1 | 0.83% | 0.00% |
| Mistake type | Visible fragment | 1 | 0.83% | 100.00% |
| Compact edits | 4-5 edits | 44 | 36.36% | 15.91% |
| Compact edits | 6+ edits | 76 | 62.81% | 3.95% |
| Operation shape | Mixed insertion/deletion/replacement | 107 | 88.43% | 7.48% |
| Operation shape | Replacements only | 11 | 9.09% | 9.09% |
| Replacement count | 3+ replacements | 91 | 75.21% | 7.69% |
| Shared bigrams | No shared bigram | 68 | 56.20% | 0.00% |
| Length direction | OCR output shorter | 58 | 47.93% | 1.72% |

The dominant pattern is not one bad character. It is mixed corruption with at
least four compact edits and little adjacent-character evidence. All 68 extreme
rows with zero shared bigrams miss the top 20. This is a candidate-generation
limit, not a top-rank tie problem.

Examples:

| OCR input | Verified family | Edits | Shared bigrams | A4 result | Meaning |
|---|---|---:|---:|---|---|
| `MYUBKL` | `MYOLAX` | 4 | 1 | rank 11 | Weak evidence survives, but not at rank 1. |
| `RIV` | `RIVOTRIL` | 5 | 2 | rank 10 | A short visible fragment retains family evidence. |
| `HOAVACH` | `AMIKACIN` | 6 | 1 | outside top 20 | Five replacements remove most lexical structure. |
| `H` | `RIVO` | 4 | 0 | no result | One unrelated character cannot identify a family. |

EasyOCR supplies 46 of the 121 extreme rows. This does not prove EasyOCR is the
worst OCR model because the 14 models were not evaluated on the same image set
and contribute unequal row counts.

## 4. Error Trends Across the Primary OCR Data

### 4.1 Edit Distance Is the Main Break Point

| Compact distance | Cases | Hit@1 | Hit@20 | Top-20 misses |
|---|---:|---:|---:|---:|
| 0 | 4 | 100.00% | 100.00% | 0 |
| 1 | 112 | 93.75% | 98.21% | 2 |
| 2-3 | 186 | 57.53% | 93.55% | 12 |
| 4-5 | 93 | 5.38% | 41.94% | 54 |
| 6+ | 69 | 0.00% | 4.35% | 66 |

Distance four is the retrieval break. Rows with four or more compact edits
create 120 of 134 primary top-20 misses, or 89.55%.

### 4.2 Error Shape and Remaining Evidence

| Factor | Cases | Hit@20 | Misses | Share of all misses |
|---|---:|---:|---:|---:|
| Mixed operations | 247 | 53.44% | 115 | 85.82% |
| Replacements only | 159 | 89.94% | 16 | 11.94% |
| Query length 1-3 | 19 | 15.79% | 16 | 11.94% |
| Query length 6-7 | 165 | 75.15% | 41 | 30.60% |
| No shared bigram | 64 | 1.56% | 63 | 47.01% |
| One shared bigram | 61 | 45.90% | 33 | 24.63% |
| Two or more shared bigrams | 339 | 88.79% | 38 | 28.36% |

Failure rate and failure impact are different. One-to-three-character queries
have the worst rate, but six-to-seven-character queries create more misses
because that group is much larger. Zero shared bigrams is both frequent and
severe, so bounded retrieval expansion should target that condition before
minor rank-score tuning.

### 4.3 Exact After Normalization

Six observations become exact after spaces and punctuation are removed. They
represent four primary unique pairs and reach 100% Hit@1 and Hit@20.

| Source OCR | Compact query | Target | Source edits | Compact edits |
|---|---|---|---:|---:|
| `CLEX A NE` | `clexane` | `CLEXANE` | 2 | 0 |
| `ABA SAGLAR` | `abasaglar` | `ABASAGLAR` | 1 | 0 |
| `MYO LAX` | `myolax` | `MYOLAX` | 1 | 0 |
| `TO CO` | `toco` | `TOCO` | 1 | 0 |

Source edit distance counts retained spaces; compact edit distance removes
them. The two fields answer different questions and must not be mixed.

## 5. Experiment 1: Fixed Retrieval Comparison

Every current and future search method is compared against this fixed roster on
the same 464 primary fair OCR pairs:

1. Exact or prefix match.
2. Exhaustive Levenshtein.
3. Jaro-Winkler.
4. Character 3-gram TF-IDF.
5. RapidFuzz token ratio.
6. Phonetic baseline.
7. Algorithm 1, current app.
8. Algorithm 2, external fast.
9. Algorithm 3, rank fusion.
10. Algorithm 4, family rescue.
11. Algorithm 5, evidence-guided rescue.

BM25 can be added as another character n-gram baseline, but it does not replace
TF-IDF. The weighting scheme is part of the method.

| System | Overall H@20 | 1 edit | 2-3 edits | 4-5 edits | 6+ edits | Mixed operations |
|---|---:|---:|---:|---:|---:|---:|
| Exact/prefix | 3.0% | 6.2% | 1.1% | 1.1% | 0.0% | 0.0% |
| Levenshtein | 59.3% | 85.7% | 82.8% | 23.7% | 0.0% | 40.9% |
| Jaro-Winkler | 67.5% | 100.0% | 86.0% | 32.3% | 10.1% | 49.8% |
| Character 3-gram TF-IDF | 47.4% | 79.5% | 57.0% | 20.4% | 2.9% | 34.4% |
| RapidFuzz token ratio | 59.1% | 92.0% | 80.6% | 19.4% | 1.4% | 42.5% |
| Phonetic | 23.3% | 56.2% | 19.4% | 6.5% | 0.0% | 12.1% |
| Algorithm 1 | 38.1% | 83.0% | 40.9% | 4.3% | 0.0% | 16.2% |
| Algorithm 2 | 51.3% | 96.4% | 59.1% | 17.2% | 0.0% | 31.2% |
| Algorithm 3 | 53.0% | 95.5% | 62.9% | 18.3% | 1.4% | 32.4% |
| Algorithm 4 | 71.1% | 98.2% | 93.5% | 41.9% | 4.3% | 53.4% |

This table is the Meeting 10 Algorithm 4 artifact. The initial 23 July
Algorithm 4 versus Algorithm 5 rerun is preserved under
`benchmark_03_ocr/results/04_model_predictions/algorithm_4_5_manual_ocr_metrics.csv`.
On the same 464 primary fair pairs, frozen Algorithm 4 produces 47.6293% Hit@1
and 71.1207% Hit@20, while Algorithm 5 before the human-evidence rules produces
45.9052% and 70.6897%.

An intermediate bounded human-evidence build is stored under
`benchmark_03_ocr/results/04_model_predictions/algorithm_5_human_evidence_metrics.csv`.
It reaches 48.4914% Hit@1 and 72.1983% Hit@20 on the same 464 pairs, with zero
unsafe confident top-1 decisions. Relative to the initial Algorithm 5 run, it
adds 12 Hit@1 recoveries and 7 Hit@20 recoveries with no paired losses. Relative
to frozen Algorithm 4, it adds a net four Hit@1 cases and five Hit@20 cases.
The initial clean-core gains did not transfer by themselves; the later
family-head, short visible-head, two-sided-anchor, exact-chain, and strict
full-name evidence rules produced the measured OCR gain. The expanded
53-system study supersedes this intermediate result with current Algorithm 5 at
50.4310% Hit@1 and 72.8448% Hit@20.

The error trend differs by method:

- Exact/prefix fails as soon as characters change; `KETONOLAC -> KETOROLAC`
  returns no candidate.
- Levenshtein and RapidFuzz handle one to three edits but collapse after four.
- Jaro-Winkler has the strongest classical Hit@20, including 100% on one edit,
  but still reaches 0% when no adjacent-character bigram remains.
- Character 3-gram TF-IDF reaches 64.9% Hit@20 with two or more shared bigrams
  and 0% with zero or one, which follows directly from its 3-gram evidence.
- The phonetic baseline is complementary rather than sufficient; broad sound
  keys create collisions and yield 23.3% overall Hit@20.
- Algorithms 1-3 improve over single-signal baselines but mixed-operation
  Hit@20 remains 16.2%, 31.2%, and 32.4%.
- Algorithm 4 leads mixed operations at 53.4% and one-shared-bigram cases at
  45.9%, but no-shared-bigram Hit@20 is only 1.6%. It does not infer families
  from unrelated text.

Canonical details:

- `results/04_meeting_10/retrieval_error_profiles.csv`
- `artifacts/04_meeting_10/retrieval_failure_examples.csv`

## 6. Experiment 2: Algorithm 4 Component Ablation

Each variant disables one query-time component while using the same 464 primary
pairs. Delta is relative to complete A4. Development contains 371 target-family
disjoint pairs; holdout contains 93 other-family pairs. Every observation for
one target stays in one split: KETOROLAC is development and VIGOREX is holdout.
Rules may be selected from development, but holdout decides whether the same
behavior transfers to families excluded from that selection.

| Removed component | Hit@1 | Hit@20 | Delta H@1 | Delta H@20 |
|---|---:|---:|---:|---:|
| None, complete A4 | 47.63% | 71.12% | 0.00 pp | 0.00 pp |
| Rescue layer | 27.37% | 51.08% | -20.26 pp | -20.04 pp |
| Conservative reranker | 41.16% | 70.47% | -6.47 pp | -0.65 pp |
| Variant-head rescue | 44.61% | 69.61% | -3.02 pp | -1.51 pp |
| Raw edit similarity | 46.77% | 65.30% | -0.86 pp | -5.82 pp |
| Positional signal | 46.12% | 69.40% | -1.51 pp | -1.72 pp |
| Character n-grams | 46.77% | 70.69% | -0.86 pp | -0.43 pp |
| External retriever | 47.20% | 71.55% | -0.43 pp | +0.43 pp |
| Weighted edit similarity | 46.34% | 63.79% | -1.29 pp | -7.33 pp |
| Short-edge retrieval | 46.77% | 67.46% | -0.86 pp | -3.66 pp |
| Prefix signal | 46.55% | 68.53% | -1.08 pp | -2.59 pp |
| Weighted confusion costs | 46.77% | 70.69% | -0.86 pp | -0.43 pp |
| Compatible-length scan | 46.98% | 68.97% | -0.65 pp | -2.16 pp |
| Retrieval-agreement bonus | 47.20% | 70.91% | -0.43 pp | -0.22 pp |
| Length coverage | 47.20% | 67.67% | -0.43 pp | -3.45 pp |
| Skeleton signal | 46.98% | 70.69% | -0.65 pp | -0.43 pp |
| Subsequence signal | 47.20% | 70.91% | -0.43 pp | -0.22 pp |
| Suffix signal | 47.63% | 71.12% | 0.00 pp | 0.00 pp |
| Delete-key retrieval | 47.63% | 70.91% | 0.00 pp | -0.22 pp |
| Confusable-first-character expansion | 47.63% | 71.12% | 0.00 pp | 0.00 pp |
| Context cleanup | 47.63% | 71.34% | 0.00 pp | +0.22 pp |
| Phonetic signal | 47.20% | 71.12% | -0.43 pp | 0.00 pp |
| Strict full-name correction | 46.55% | 71.12% | -1.08 pp | 0.00 pp |
| Safety clarification gate | 47.63% | 71.12% | 0.00 pp | 0.00 pp |

The rescue layer is the dominant retrieval component. Removing it loses 94 net
Hit@1 pairs and 93 net Hit@20 pairs, with exact McNemar p-values below
`1e-24`. Weighted and raw edit similarity, short-edge retrieval, length
coverage, prefix evidence, compatible-length scanning, variant heads, and the
reranker also have measurable paired effects.

Removing the strict full-name correction loses five Hit@1 pairs and gains none;
three losses are in development and two are in holdout. Its exact paired
p-value is 0.0625, so the direction is consistent but the OCR sample alone is
too small for a conventional 0.05 significance claim. Removing phonetic
evidence loses two net Hit@1 pairs, but its exact p-value is 0.727. Suffix and
confusable-first-character removal cause no switches on these 464 pairs; they
remain unproven rather than proven useless.

The safety gate is intentionally invisible to Hit@k. Removing it leaves
retrieval unchanged but raises unsafe confident top-1 from 0.00% to 24.78%.
Safety and retrieval therefore require separate metrics.

## 7. Equal Edit-Distance Ordering

The primary OCR data contains 37 rank failures where the verified family is
already in the top 20 and has the same raw edit distance as A4's first result.
Five generic alternatives were tested, plus three conservative Pareto rules.
None was selected from development and then supported by holdout.

A rule can act only on a brand-like query with nonzero top raw distance, and
only among candidates tied on that raw distance and inside the configured full
score gap.

| Choice | Ordered criteria |
|---|---|
| Current full-evidence order | Keep the complete A4 score and original deterministic order. |
| Weighted then position | Lower weighted edit cost, higher position, higher edge, dual-retriever agreement, full score. |
| Position then weighted | Higher position, lower weighted cost, higher edge, agreement, full score. |
| Edge then weighted | Higher edge, lower weighted cost, higher position, agreement, full score. |
| Composite | Maximize `-weighted_cost + 0.35*position + 0.25*edge + 0.10*agreement`, then full score. |
| Pareto 0.25/0.15/0.10 | Candidate must be no worse on weighted cost, position, edge, and agreement, better on at least one, and inside the named full-score gap. |

| Tie policy | All Hit@1 | Development Hit@1 | Holdout Hit@1 | Net effect |
|---|---:|---:|---:|---|
| Current full-evidence score order | 47.63% | 47.98% | 46.24% | Reference |
| Weighted distance, then position | 45.91% | 46.36% | 44.09% | Worse in both splits |
| Position, then weighted distance | 46.55% | 46.63% | 46.24% | No holdout gain; development loss |
| Edge evidence, then weighted distance | 47.41% | 48.52% | 43.01% | Development-only improvement |
| Composite lexical evidence | 46.12% | 46.63% | 44.09% | Worse in both splits |
| Pareto evidence, score gap <= 0.25 | 46.77% | 47.44% | 44.09% | Worse in both splits |
| Pareto evidence, score gap <= 0.15 | 46.77% | 47.44% | 44.09% | Worse in both splits |
| Pareto evidence, score gap <= 0.10 | 46.55% | 47.17% | 44.09% | Worse in both splits |

Decision: equal edit distance is not enough to force a winner. A4 keeps the
combined model score order and returns `equal_distance_ambiguity`. The UI must
show alternatives and family details. No character position, including the
first character, receives automatic priority. This is an evidence-backed
decision, not an unfinished tie-break implementation.

Example: `conal` is one edit from both `COBAL` and `CONIL`. The safe product
behavior is comparison, not a hidden first-letter or alphabetical rule.

Observed disagreements show why no generic chain was accepted:

- `ANYOLAX -> MYOLAX`: edge-first fixes the row; other generic rules keep
  `AGIOLAX`.
- `RIVOFN2 -> RIVOTRIL`: position-first and edge-first select the target;
  weighted and Pareto rules select other families.
- `CEFAXIME -> CEFIXIME`: weighted, position, and composite rules fix this
  holdout row; edge and Pareto retain `CEFAXIM`.
- `INDEVIO -> INDERAL`: every rule retains `ENTYVIO`; available evidence does
  not justify forcing the expected family first.

## 8. Six Search-Failure Types on the 115k Benchmark

Mutation category describes how an input was generated. Mistake type describes
why A4 failed. They are independent dimensions.

| Type | Meaning | Rows | Share of 15,540 scored H@1 failures | Hit@20 |
|---|---|---:|---:|---:|
| 1 | Exact real-name collision, diagnostic and unscored | 5,026 | Not in fair failure denominator | 44.47% |
| 2 | Equal edit evidence | 1,954 | 12.57% | 89.15% |
| 3 | Known unreadable continuation | 1,792 | 11.53% | 65.63% |
| 4 | Family/variant mismatch | 721 | 4.64% | 77.39% |
| 5 | Candidate-generation failure | 3,794 | 24.41% | 0.00% |
| 6 | Candidate-ranking failure | 7,279 | 46.84% | 100.00% |

Type 6 is the largest failure count, but every target is already inside the top
20, so reranking can address it. Type 5 is smaller but more fundamental because
the target is absent from the candidate list.

Observed concentrations:

1. Type 1 is dominated by `autocorrect_artifacts` and
   `multi_word_name_fragmentation`, 2,000 rows each and 79.59% combined. This
   supports treating exact-name collisions as data ambiguity rather than search
   errors.
2. Type 2 occurs most in `dangerous_ed1_pairs` (379), three-error chains (311),
   four-plus-error chains (255), and two-error chains (238). More corruption
   creates more equally plausible catalog families.
3. Type 3 consists entirely of `substring_traps`. Position evidence such as
   unreadable characters before, after, or in the middle must come from the
   user or image, not from edit distance.
4. Type 4 is led by doctor abbreviations (356 of 721). A family head is found,
   but the exact form or composition still needs selection.
5. Type 5 is concentrated in doctor abbreviations (1,910), score-gap ambiguity
   cases (738), keyboard-shift words (456), and four-plus-error chains (305).
6. Type 6 is concentrated in doctor abbreviations (2,782), score-gap ambiguity
   (1,822), and prefix ambiguity (800). These are candidate-ordering and product
   clarification problems, not retrieval absence.

Examples:

| Type | Input | Expected | A4 top/result | Interpretation |
|---|---|---|---|---|
| 1 | `epigent` | `APIGENT` | exact `EPIGENT` first | Input is another real family; exclude from fair accuracy. |
| 2 | `conal` | `COBAL` | `CONIL` first, expected rank 3 | Equal edit evidence; show both. |
| 3 | `acc` + unreadable-after evidence | `ACCELAFEN` | expected rank 4 | Prefix plus known continuation narrows the family set. |
| 4 | `candeblockb` | `CANDEBLOCK D` | `CANDEBLOCK` first | Family recovered; exact variant unresolved. |
| 5 | `akc` | `ACC` | no match | Candidate generation failed. |
| 6 | `tidanhair` | `TITAN HAIR` | expected rank 2 | Candidate exists; ranking placed another family first. |

## 9. Fair Increase on the 115k Benchmark

| Algorithm | Inclusive H@1 | Fair H@1 | Inclusive H@20 | Fair H@20 | Fair behavior | Fair unsafe |
|---|---:|---:|---:|---:|---:|---:|
| Algorithm 1 | 75.2565% | 78.6841% | 88.4043% | 90.6578% | 90.9260% | 0.0173% |
| Algorithm 2 | 79.3009% | 82.9251% | 91.8374% | 93.9740% | 93.3975% | 2.8407% |
| Algorithm 3 | 81.0348% | 84.7373% | 93.0948% | 95.3389% | 95.5799% | 0.0000% |
| Algorithm 4 | 82.1165% | 85.8694% | 93.4122% | 95.6490% | 95.8845% | 0.0000% |

The dataset still contains 115,000 rows. The fair view uses `scored_case=1`
and gives 109,974 rows one-answer accuracy votes; all 5,026 excluded collisions
remain available for safety analysis. Fair Hit@1 rises by 3.4275, 3.6242,
3.7025, and 3.7529 points for Algorithms 1-4, so the change is applied to every
algorithm rather than only to A4.

The excluded rows are not evenly distributed. Autocorrect artifacts and
multi-word fragmentation contribute 2,000 each, 79.59% combined. Doctor
abbreviation contributes 402. The remaining 624 rows span 19 other categories.

Canonical details:

- `results/04_meeting_10/synthetic_fairness_by_algorithm.csv`
- `results/04_meeting_10/synthetic_collision_distribution.csv`

## 10. Reproduce the Work

Install the experiment-only dependencies:

```bash
UV_CACHE_DIR=/tmp/uv-cache ~/.local/bin/uv pip install \
  --python benchmark_03_ocr/.venv/bin/python \
  -r benchmark_04_experiments/requirements.txt
```

Run classical baselines, Algorithms 1-4, and all A4 ablations:

```bash
PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/run_retrieval_experiments.py
```

Rebuild the Meeting 10 distributions and equal-distance evidence:

```bash
PYTHONDONTWRITEBYTECODE=1 benchmark_03_ocr/.venv/bin/python \
  benchmark_04_experiments/analyze_meeting_10.py
```

## 11. Experiment 7: Pharmacist Study Status

The within-subject study package is prepared but no participant result is
claimed. It compares no tool/current practice, DrugEye, and this system with a
valid `cannot decide / call doctor` safety action.

- 15 pharmacists or senior pharmacy students.
- 75 deidentified prescription word crops.
- 25 different crops per condition for each participant; no repeated crop
  within one participant.
- Five decisions per crop and condition across the group.
- Randomized case order and counterbalanced condition assignment.
- Primary outcomes: correct selection and unsafe wrong selection.
- Secondary outcomes: safe deferral, time, confidence, and usability.
- Participant and case effects retained in condition comparisons.

```bash
python3 benchmark_04_experiments/pharmacist_study.py prepare \
  --participants 15 --cases 75
```

Real responses must replace the blank template before `analyze` is run.

## 12. Historical Algorithm 5 Residual Failure Audit

The 23 July 2026 source revision was selected by repeated paired checks, not by
inspecting only successful examples. A frozen rerun separates the two versions
on the same 66,257 clean-core pairs. These values describe that historical
revision, not the current Algorithm 5 source:

| Version | Hit@1 | Hit@20 |
|---|---:|---:|
| Algorithm 4, family rescue | 64,392/66,257 (97.1852%) | 65,936/66,257 (99.5155%) |
| Algorithm 5, evidence-guided rescue | 65,068/66,257 (98.2055%) | 66,257/66,257 (100.0000%) |

Algorithm 5 gains 676 Hit@1 cases (+1.0203 percentage points) and 321 Hit@20
cases (+0.4845 points) over Algorithm 4. That historical revision's diagnostics
are:

| Metric | Result |
|---|---:|
| Hit@1 | 65,068/66,257 (98.2055%) |
| Hit@20 | 66,257/66,257 (100.0000%) |
| MRR@20 | 0.988569 |
| Unsafe confident wrong top-1 | 0 |
| Development Hit@1 | 51,962/52,906 (98.22%) |
| Holdout Hit@1 | 13,106/13,351 (98.16%) |

Relative to the pre-audit Algorithm 5 configuration, Hit@1 has 689 paired
gains and 12 paired losses, for +677 net. Hit@20 has 321 gains and no losses.
The remaining 1,189 errors are all rank-only failures.

| Residual OSA geometry | Cases | Share of Hit@1 failures |
|---|---:|---:|
| Another catalog family is closer | 603 | 50.71% |
| Verified family ties with catalog neighbors | 572 | 48.11% |
| Verified family is uniquely nearest | 14 | 1.18% |

The operation audit finds 930 mixed-operation failures, 123 visual/OCR
failures, 59 vowel failures, 28 keyboard failures, 22 phonetic failures, 18
deletion failures, and 9 insertion failures. Transposition and uncategorized
rows have zero remaining Hit@1 failures. This is a ranking distribution; every
group remains at 100% Hit@20.

Rules were accepted only when their activation evidence generalized and the
paired development and holdout checks preserved safety. Accepted mechanisms
include bounded mixed-error retrieval, directional digit-to-letter OCR
evidence, structural ligature rewrites, exact phonetic rewrites, weighted
keyboard evidence, guarded full-name correction, and conservative
score-dominance release. They use character patterns and catalog structure, not
medicine-name lists.

The audit rejected global nearest-family replacement and broad vowel, visual,
deletion, insertion, and score-dominance rules. The final global nearest-family
counterfactual fixes 14 errors but breaks 125 correct decisions, reducing net
accuracy by 111 cases.

The canonical analysis tables are under
`results/05_synthetic_clean_core/`. They reconcile all 662,570 system-result
rows. A fresh
Algorithm 5 run matches all ranks, Hit@k flags, first names, and candidate
counts. The 85 focused regression tests pass, and a fixed 1,087-case probe
produces identical hashes under two Python hash seeds.

### Current Algorithm 5 source revision

The expanded competitor study reruns the current source on the same 66,257
pairs. Current Algorithm 5 reaches 65,057/66,257 Hit@1 (98.1889%) and
66,256/66,257 Hit@20 (99.9985%). Against the historical artifact, 44 cases gain
rank 1, 55 lose rank 1, and 187 ranks change, for a net change of -11 Hit@1
cases. The only current top-20 miss is `aclox` with verified family `ADOX`;
the historical source ranked it 20, while the current source places `AMOCLOX`
first and omits `ADOX` from the first 20. Use the expanded competitor results
for current claims and retain this section only as source-revision history.

## 13. Algorithm 4 Context Reranking And Post-Review Evaluation

The current OCR denominator contains 412 unique accepted query-target pairs.
It is a later adjudicated subset of the historical 464-pair experiment above:
52 rows with insufficient or contradictory OCR text were moved to
`data/01_ocr_fair/excluded_cases.csv` before the new run. No row was removed
because Algorithm 4 failed it.

Algorithm 4 reaches 222/412 Hit@1 (53.88%) and 331/412 Hit@20 (80.34%), with
zero unsafe confident top-1 responses. Its 81 top-20 misses comprise 38 extreme
competing-evidence rows, 12 extreme low-character rows, 17 high-distance
candidate-competition rows, 10 standard-distance retrieval gaps, three
no-candidate rows, and one short-query row. All 412 expected families exist in
the Egyptian catalog; case IDs and normalized query-target pairs are unique.

The new product-context stage runs after brand-family retrieval. It parses
strength or concentration, dosage form, route, release type, and weak numeric
context, compares those fields against one real package at a time, and reranks
variants inside the retrieved family. It never creates a candidate from dosage
context alone. For example, `VOLTAREN 100 MG SR TABLET` selects
`VOLTAREN SR 100MG 20 F.C.TAB.`, while `VOLTAREN GEL 1%` selects a 1% topical
Emulgel package.

A paired 6,000-row V2 context evaluation holds every query and expected family
fixed. The current implementation raises combined Hit@1 from 91.40% to 98.53%
and Hit@20 from 99.08% to 99.82%. It produces 462 Hit@1 gains versus 34 losses,
and 44 Hit@20 gains with zero Hit@20 regressions. The two component categories
are 4,000 embedded form/strength rows and 2,000 exact-name-with-strength rows.

Canonical current artifacts:

- Manual adjudication: `../benchmark_02_synthetic/data/manual_cases.csv`
- Manual row results: `../benchmark_02_synthetic/artifacts/02_manual_cases/algorithm_4_cases.csv`
- Filtered OCR cases: `data/01_ocr_fair/test_cases.csv`
- Filtered OCR row results: `results/08_algorithm_4_context/algorithm_4_filtered_ocr_results.csv`
- Filtered OCR metrics: `results/08_algorithm_4_context/algorithm_4_filtered_ocr_metrics.csv`
- Paired 6,000-row context metrics: `results/08_algorithm_4_context/context_reranking_metrics.csv`

Reproduce the locked OCR result:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 benchmark_03_ocr/evaluate_search_algorithms.py \
  --cases benchmark_04_experiments/data/01_ocr_fair/test_cases.csv \
  --algorithms 4 --case-mode accepted \
  --output-prefix algorithm_4_filtered_ocr \
  --results-dir benchmark_04_experiments/results/08_algorithm_4_context \
  --raw-output-dir benchmark_04_experiments/results/08_algorithm_4_context
```

## 14. Catalog-Wide Unreadable-Text Search

Run group `09_unreadable_text` tests the UI contract in which a user can read
text before, after, or on both sides of one unreadable span. It does not label
an arbitrary source medicine as the only correct answer when several catalog
families satisfy the same visible pattern. A unique pattern is scored with
Hit@k; an ambiguous pattern succeeds only when every displayed family is valid
for the pattern and the response requires confirmation.

The generator enumerates 1,502,285 possible one-span masks over 18,528 full
commercial bases and validated family heads from the 25,066-record application
catalog. It retains all requests with one or two visible characters and a
stable SHA-256 sample of longer requests, producing 10,575 unique requests.
Of these, 9,288 belong to a target-family-disjoint locked denominator; 1,287
cross-split collisions remain inclusive diagnostics.

The hidden-character penalty was selected from 448 ambiguous development
requests only. Penalties from 0 through 600 were compared. Source-family Hit@1
plateaued at 94.64% for 450 and 600, so the smaller value 450 became the runtime
default. Source-family rank is a shortest-completion diagnostic, not a fairness
metric when several medicines match.

On the locked 9,288 requests, the indexed implementation reaches 100% valid
Hit@1, 100% valid Hit@20, 100% result precision, 100% behavior success, and zero
unsafe confident top-1 responses. The untouched holdout contains 2,084 requests
and reaches 99.90% source-family Hit@1 and 99.95% source-family Hit@20 while
preserving 100% pattern-valid output. Indexed p95 latency is 2.96 ms versus
5.34 ms for exhaustive full scanning in the recorded run. These values measure
the explicit unreadable-span contract, not ordinary typo recovery or clinical
identification from insufficient evidence.

Run the experiment:

```bash
node benchmark_04_experiments/run_unreadable_text_experiment.mjs \
  --sample-modulus 128
```

Canonical outputs:

- Generated requests: `data/06_unreadable_text/test_cases.csv`
- Row-level full-scan and indexed results:
  `artifacts/09_unreadable_text/case_results.csv`
- Long-form metrics: `results/09_unreadable_text/metrics.csv`
- Machine-readable acceptance summary: `results/09_unreadable_text/summary.json`
- Human-readable report: `results/09_unreadable_text/report.md`

The browser regression suite also derives 144 before, middle, and after
requests from 48 catalog targets, checks that every returned family satisfies
the pattern, and requires indexed output to match exhaustive full scanning:

```bash
node app/test_app.js
```

### Flexible visible-part input

The production UI no longer asks the user to choose before, middle, or after
and no longer uses a second ending field. One checkbox enables partial-text
mode. The main field then accepts one or more visible pieces in observed order,
separated by spaces, `...`, `*`, or `?`. For example, both `MELI CAM` and
`MELI...CAM` rank `MELOXICAM` first even though `MELI` contains one reading
error and an unreadable character exists before `CAM`.

The matcher aligns up to five fragments anywhere in the full commercial base
or validated family head. Fragment edit tolerance is zero for one or two
characters, one edit for three to six characters, and two edits for longer
fragments. A separate grapheme fallback collapses common written sound units,
including `CK -> K`, `PH -> F`, `GH -> G`, `QU -> K`, and repeated letters.
Raw exact evidence keeps priority except when an exact grapheme-equivalent
prefix supplies the missing family. Ranking minimizes total edits, changes in
aligned fragment length, supplemental grapheme evidence, then hidden
characters. Candidate generation uses separate raw and grapheme edit-partition
indexes; ordered alignment remains the final validator.

The flexible benchmark samples 3,499 requests from 276,742 possible
catalog-derived patterns. It now enumerates every valid two-part boundary for
each catalog target and adds a representative three-part split. Exact divided
full names may contain zero hidden characters because the pieces reconstruct
the complete catalog name; fuzzy fragment alignments still require at least one
hidden character. This prevents partial mode from rejecting inputs such as
`JACK ODAN`, `PANA DOL`, and `COUGH SED` without allowing fuzzy fragments to
masquerade as exact full-name evidence.

The 3,407-row primary informative denominator reaches 95.60% source Hit@1 and
99.91% source Hit@20. The 751 untouched holdout requests reach 96.40% and
100.00%. All 2,283 sampled two-part full names and all 197 sampled three-part
full names rank the source family first. All primary responses require
confirmation, none return zero candidates, and 171 sampled indexed family
orders match exhaustive 25,066-record scanning exactly. Indexed p95 latency is
59.89 ms. The 11 sampled grapheme-prefix cases reach 90.91% Hit@1 and 100%
Hit@20.

Single-fuzzy-fragment rows remain diagnostics because one short piece with one
wrong character and unknown position can support many families. They remain in
`partial_text_results.csv` and do not support a unique-source accuracy claim.

Canonical flexible outputs:

- Cases: `data/06_unreadable_text/partial_text_cases.csv`
- Row results: `artifacts/09_unreadable_text/partial_text_results.csv`
- Metrics: `results/09_unreadable_text/partial_text_metrics.csv`
- Summary: `results/09_unreadable_text/partial_text_summary.json`
- Report: `results/09_unreadable_text/partial_text_report.md`

Run only the flexible experiment:

```bash
node benchmark_04_experiments/run_unreadable_text_experiment.mjs \
  --partial-only --partial-sample-modulus 64
```

# Evaluation Contract

This file is the single repository-wide contract for evaluating medicine search,
OCR, and human-use experiments. Benchmark-specific documents may add details,
but they must use these definitions when they report a shared metric.

## 1. Why This Contract Exists

Scores are comparable only when the systems receive the same cases, use the
same relevance labels, and count the same rows. A new metric or error grouping
must therefore be calculated for every compatible earlier system, not only for
the newest system.

Example: if `mixed_operations` becomes a new OCR error group, report it for all
search algorithms with row-level OCR results. Do not report it only for
Algorithm 4 and imply that Algorithms 1-3 were not tested.

## 2. Stable Names

| Stable ID | Descriptive row-level alias | System |
| --- | --- | --- |
| `algorithm_1` | `algorithm_1_current_app` | Current application search. |
| `algorithm_2` | `algorithm_2_external_fast` | External English fast search. |
| `algorithm_3` | `algorithm_3_rank_fusion` | Rank fusion of Algorithms 1 and 2 with safety gates. |
| `algorithm_4` | `algorithm_4_family_rescue` | Algorithm 2 with bounded family rescue and conservative clarification. |

| ID | Evaluation data |
| --- | --- |
| `legacy_341901` | Original generated commercial-name benchmark. |
| `synthetic_115000` | Deterministic 34-category synthetic benchmark. |
| `ocr_rxhandbd` | RxHandBD OCR and downstream search benchmark. |
| `ocr_data4_data5` | Paired processed and original word-crop benchmark. |
| `ocr_predictions_595` | Fourteen-model OCR prediction export and downstream search cases. |
| `retrieval_primary_464` | Collision-free unique OCR query-target pairs used by comparative baselines and ablations. |
| `pharmacist_study` | Within-subject no-tool, DrugEye, and system study. No outcome exists until responses are collected. |

Use the stable ID in cross-benchmark tables. A benchmark may retain the listed
descriptive alias in row-level evidence; consolidation must map it to the stable
ID. Human-readable labels may change; stable IDs must not.

## 3. Unit of Evaluation

Every reported percentage must name its denominator.

| Denominator | Meaning | Use |
| --- | --- | --- |
| Observation | One model output for one source item. Repeated query-target pairs receive repeated votes. | Data audit and operational workload. |
| Unique query-target pair | One vote for each normalized query and verified family pair. | Search-system comparison without duplicate weighting. |
| Scored observation | Observation after excluding rows whose supplied target is not uniquely inferable. | Inclusive model analysis with fairness control. |
| Primary fair unique pair | One vote per unique pair after exact real-drug collisions are excluded. | Headline OCR-derived search comparison. |
| Synthetic inclusive row | Every generated row, including diagnostic collisions. | Full benchmark behavior. |
| Synthetic fair row | Generated row with `scored_case=1`. | Accuracy when one expected family is inferable. |
| Participant-case-condition | One pharmacist decision for one case under one study condition. | Human study only. |

An exact real-drug collision is diagnostic, not a fair single-answer question.
For example, if OCR output exactly names `RIVOTRIL` but the supplied target is
`RIVO`, the row remains visible for safety analysis and is excluded from the
primary fair retrieval denominator.

## 4. Data Validation Before Scoring

Every evaluator must fail instead of silently continuing when one of these
checks fails:

1. Case IDs are unique in each input table.
2. Expected targets map to the catalog or to a documented sentinel such as
   `__NO_MATCH__` or `__AMBIGUOUS__`.
3. The result table has exactly one row per expected case and algorithm.
4. Every requested category, error type, cohort, and split is present after the
   join, including zero-success groups.
5. Development and holdout are disjoint by target family when that split is
   used.
6. Metric inputs retain query, expected target, candidate ranks, response
   status, clarification state, and algorithm ID.
7. Counts reconcile from source rows to accepted, diagnostic, excluded, and
   scored rows.

## 5. Retrieval and Ranking Metrics

For query `q`, let `R_k(q)` be the first `k` returned families and `Y(q)` the
set of relevant families.

| Metric | Calculation | Interpretation |
| --- | --- | --- |
| Hit@1 | `1` when `R_1(q)` intersects `Y(q)` | Correct family ranked first. |
| Hit@5, Hit@10, Hit@20 | `1` when the relevant family appears by the cutoff | Candidate-generation and ranking coverage. |
| MRR@20 | Reciprocal rank of the first relevant family, or `0` when absent | Rewards earlier first hits. |
| MAP@20 | Mean precision at every relevant hit through rank 20 | Use when a row has several relevant families. |
| nDCG@20 | Discounted relevance gain normalized by the ideal ranking | Measures ordering with multiple relevance labels. |
| Candidate count | Number of candidates considered or returned, with the field named explicitly | Measures retrieval breadth, not accuracy. |

Always report Hit@1 and Hit@20 together. A Hit@1 miss with Hit@20 success is a
ranking error. A Hit@20 miss is a retrieval error.

## 6. Behavior and Safety Metrics

Retrieval and behavior answer different questions. A useful candidate list can
be correct behavior even when the system cannot safely certify one answer.

| Metric | Rule |
| --- | --- |
| Behavior success | `match`: relevant family is in top 20. `ambiguous`: candidates are shown without unsafe confidence. `no_match`: no confident family is asserted. |
| Unsafe confident top-1 | Top result exists, is irrelevant, and is presented as confident without clarification. |
| Missing clarification | A caution or dangerous case is answered confidently when evidence does not justify one family. |
| No-result rate | No candidates are returned. Report separately from incorrect candidates. |
| Clarification rate | Response requires user confirmation or more evidence. |

Safety metrics must never be inferred from rank alone. The row-level response
status and clarification flag are required.

## 7. Error Analyses

Keep these dimensions separate because they answer different questions:

| Dimension | Question |
| --- | --- |
| Mutation category | How was a synthetic input corrupted? |
| Error type | Which exact mutation rule produced it? |
| Mistake type | Why did the search result fail? |
| OCR operation profile | Were characters inserted, deleted, replaced, or mixed? |
| Edit-distance band | How much lexical evidence remains? |
| Query-length band | How much visible text reached search? |
| Cohort | Is the row exact, standard, high-distance, extreme, a visible fragment, or a real-name collision? |
| Danger | What is the consequence of a confident wrong answer? |

For each applicable group, report both:

- **failure rate:** misses in the group divided by rows in the group;
- **failure share:** misses in the group divided by all misses.

Failure rate finds weak groups. Failure share finds where engineering work can
remove the largest number of errors.

## 8. OCR Metrics

OCR evaluation uses the human transcription before medicine search.

| Metric | Meaning |
| --- | --- |
| Exact match rate | OCR text equals the normalized human label. |
| Character error rate | Character insertions, deletions, and substitutions divided by reference characters. |
| Word error rate | Word insertions, deletions, and substitutions divided by reference words. |
| Normalized edit distance | Compact Levenshtein distance divided by compact target length. |
| End-to-end Hit@k | OCR output is searched and the verified medicine appears by rank `k`. |

OCR model comparisons require the same images, labels, preprocessing policy,
and denominator. A raw downstream score from unmatched model case sets is a
case-mix diagnostic, not an OCR leaderboard.

## 9. Efficiency Metrics

Measure every algorithm under the same process, catalog, query sample, warm-up,
worker count, and machine state.

| Stage | Required measurements |
| --- | --- |
| Build/index | Wall time, peak resident memory, serialized index size, catalog rows. |
| Warm query | Mean, median, p95, and p99 latency after warm-up. |
| Cold query | Process start plus first result, reported separately. |
| Query memory | Incremental and peak resident memory during the same batch. |
| Candidate work | Mean and p95 candidate count when exposed by the system. |

Report measured values and asymptotic complexity separately. Big-O describes
growth; milliseconds and megabytes describe this implementation and machine.

## 10. Statistical Comparison

Use paired tests because algorithms are evaluated on the same cases.

- Report the paired success delta in percentage points.
- Report gained cases, lost cases, and net gain.
- Use exact McNemar testing for paired binary Hit@k outcomes.
- Bootstrap a confidence interval over case IDs for aggregate metric deltas when
  the denominator is large enough.
- Keep target-family-disjoint holdout results separate from development results.
- Do not tune thresholds on holdout.

## 11. Ablation Evaluation

An Algorithm 4 ablation changes one component and keeps all other code,
parameters, cases, and scoring rules fixed. Compare every ablation with full A4
on the same primary fair unique pairs and report:

1. Hit@1 and Hit@20 delta.
2. Behavior and unsafe-confidence delta.
3. Gained and lost case counts.
4. Paired significance result.
5. At least one gained and one lost row when they exist.

An ablation that removes several coupled components must be named as a combined
ablation; it cannot be interpreted as the effect of one component.

## 12. Human Study Evaluation

The pharmacist study uses a within-subject design. Each participant sees all
three conditions in randomized, counterbalanced order: no tool/current practice,
DrugEye, and this system. Valid outcomes include the correct medicine, an
incorrect medicine, and `cannot decide / call doctor`.

Report decision accuracy, unsafe error rate, safe deferral rate, time to
decision, confidence, and usability. Compare conditions on identical cases with
participant and case effects retained. Do not publish a result from the blank
study template.

## 13. Retrospective Evaluation Rule

When any evaluation method changes:

1. Define the method, deterministic rule, denominator, and version here.
2. Add the required row-level field without deleting prior fields.
3. Identify every prior dataset and algorithm with sufficient evidence.
4. Recompute the new view for all compatible systems on identical case IDs.
5. Mark incompatible cells `not_applicable` or `not_reproducible` and state the
   missing evidence.
6. Append results to the canonical long-form table with `evaluation_version`;
   do not create one renamed table per algorithm.
7. Regenerate reports and figures from that table.
8. Run coverage checks before accepting the new comparison.

Example: adding a `known_unreadable_position` mistake type requires recomputing
that label and its metrics for Algorithms 1-4 on the synthetic row-level
results. It does not apply retrospectively to OCR-only systems if those rows do
not contain positional evidence; those cells are `not_applicable`, not zero.

## 14. Canonical Aggregate Schema

Compatible aggregate results belong in one long-form CSV per logical run:

```text
evaluation_version,run_id,dataset,algorithm,denominator,split,
dimension,group,cases,hit_at_1,hit_at_5,hit_at_10,hit_at_20,
mrr_at_20,map_at_20,ndcg_at_20,behavior_success_rate,
unsafe_confident_top1_rate,no_result_rate,mean_latency_ms
```

Use an empty field only when a metric was not recorded but could in principle
be computed. Use the literal status fields `not_applicable` and
`not_reproducible` in a companion `metric_status` column when the distinction
matters. Never encode missing evidence as `0`.

## 15. Current Applicability Matrix

| Technique | Legacy | Synthetic 115k | OCR search | OCR recognition | A4 ablations | Human study |
| --- | --- | --- | --- | --- | --- | --- |
| Hit@k and ranking metrics | Yes | Yes | Yes | End-to-end only | Yes | No |
| Behavior and safety | Partial | Yes | Yes | End-to-end only | Yes | Safe-action metrics |
| Category and error type | Yes | Yes | When labeled | No | When labeled | No |
| Mistake type | Backfill if row evidence exists | Yes | Yes | No | Yes | No |
| OCR operation and distance | No | Synthetic analog only | Yes | Yes | Yes | No |
| Paired algorithm test | Yes | Yes | Yes | Same-image models | Yes | Paired condition test |
| Efficiency | Rerun required | Rerun required | Rerun required | Rerun required | Same run | Timed decisions |

`Partial` means the historical result does not expose every current safety
field. The original score remains valid, but unsupported metrics must be marked
`not_reproducible` until row-level evidence is regenerated.

## 16. Acceptance Gates

A new benchmark result is complete only when:

- row counts reconcile;
- all applicable algorithms use the same case IDs and denominator;
- every declared group appears in the aggregate output;
- inclusive and fair scores are both present when collision exclusions exist;
- no safety regression is hidden by a retrieval gain;
- development and holdout are reported separately when available;
- generated reports read from canonical tables;
- commands, dependencies, random seeds, and evaluation version are recorded.

Benchmark-specific commands and source files remain in each numbered benchmark
README. This contract owns the shared meaning of the evaluation, not the data or
implementation of an individual run.

## 17. Mandatory Experiment Roster

The following roster is persistent. A new search method is incomplete until it
is compared with every applicable system below on identical case IDs. A report
must not replace this matrix with only the newest method and Algorithm 4.

### 17.1 Experiment 1: Retrieval Baselines and Algorithms 1-4

Run these systems in this order:

1. Exact or prefix match.
2. Exhaustive Levenshtein distance.
3. Jaro-Winkler similarity.
4. Character 3-gram TF-IDF.
5. RapidFuzz-style token ratio.
6. Phonetic baseline.
7. Algorithm 1, current application search.
8. Algorithm 2, external English fast search.
9. Algorithm 3, rank fusion with safety gates.
10. Algorithm 4, family rescue with conservative clarification.

Character 3-gram BM25 may be added as another baseline. It must not silently
replace TF-IDF because changing the weighting scheme changes the experiment.

For every system, report Hit@1, Hit@5, Hit@10, Hit@20, MRR@20, unsafe confident
top-1, clarification rate, candidate count, preparation time, and warm latency.
Break Hit@1, Hit@20, failure rate, and failure share down by compact edit
distance, OCR operation profile, shared-character evidence, shared bigrams,
query length, severity cohort, danger, mutation category, exact error type, and
mistake type whenever those fields exist. Include one rank-only failure and one
top-20 retrieval failure with input, expected family, returned first family,
expected rank, and error label for every system.

Use all of these denominator views:

| Dataset | Required views |
| --- | --- |
| OCR predictions | Inclusive observations, scored observations, all unique pairs, primary fair unique pairs, development, and holdout. |
| Synthetic 115k | Inclusive 115,000 rows, fair collision-excluded rows, all scopes, all 34 categories, and all six mistake types. |
| Manual cases | Every supplied row after expected-family normalization, plus a documented unmappable-label audit. |
| Deployment parity | The same browser query and catalog version when the method is deployable. |

### 17.2 Experiment 2: Algorithm 4 Ablation

Start from complete Algorithm 4 and disable exactly one component per run. Keep
the catalog, cases, top-k cutoff, thresholds, process, and scoring fixed. The
required component set is external retrieval, context cleanup, family rescue,
raw edit similarity, weighted edit similarity, prefix, suffix, character
n-grams, phonetic evidence, consonant skeleton, subsequence evidence,
positional evidence, length coverage, delete-key retrieval, short-edge
retrieval, confusable-first-character expansion, compatible-length scanning,
family-head rescue, weighted confusion costs, retriever agreement, strict
full-name correction, conservative reranking, and the safety clarification
gate. A coupled removal is a separate combined ablation and does not estimate a
single component effect.

### 17.3 Experiment 7: Pharmacist User Study

Use a within-subject design with 10-20 pharmacists or senior pharmacy students
and 50-100 deidentified prescription word crops. Compare no tool/current
practice, a frozen DrugEye condition, and the frozen deployed system. Randomize
case order and counterbalance condition order. Each participant sees a crop only
once. `cannot_decide` and `call_doctor` are valid safe actions and must never be
collapsed into an incorrect medicine choice. Report correct selection, unsafe
wrong selection, safe deferral, decision time, confidence, and usability with
participant and case effects retained.

## 18. Equal Edit-Distance Decision Contract

Equal raw Levenshtein distance does not identify a unique winner. A tie policy
may reorder only brand-like queries with nonzero top distance, and only among
candidates sharing that top raw distance. Current experiments also restrict a
candidate to a bounded model-score gap before a generic reordering rule applies.

The tested choices are:

| Choice | Ordered evidence |
| --- | --- |
| Current full-evidence order | Keep Algorithm 4's complete score, candidate-source agreement, and deterministic original order. |
| Weighted distance, then position | Lower confusion-weighted edit cost, higher positional evidence, higher edge evidence, dual-retriever agreement, then full score. |
| Position, then weighted distance | Higher position evidence first, then weighted cost, edge evidence, agreement, and full score. |
| Edge, then weighted distance | Higher prefix/suffix edge evidence first, then weighted cost, position, agreement, and full score. |
| Composite lexical evidence | Maximize `-weighted_cost + 0.35*position + 0.25*edge + 0.10*agreement`, then full score. |
| Pareto, gap 0.25 | Switch only when a tied candidate is no worse on weighted cost, position, edge, and agreement, better on at least one, and within 0.25 full-score units. |
| Pareto, gap 0.15 | Same dominance rule with a 0.15 score-gap bound. |
| Pareto, gap 0.10 | Same dominance rule with a 0.10 score-gap bound. |

No character position receives automatic priority. For `CONAL`, both `COBAL`
and `CONIL` are one raw edit away; the system must show the alternatives and
their medicine-family details unless independent evidence establishes a unique
winner. A policy is accepted only when selected on development data and then
improves the target-family-disjoint holdout without increasing unsafe
confidence. Otherwise, retain the current order and label the response
`equal_distance_ambiguity`.

## 19. Analysis Propagation Rule

When a new baseline, metric, denominator, error grouping, tie policy, or fair
scoring rule is introduced, recompute it for every compatible system in the
mandatory roster. At minimum, publish the aggregate value, per-group value,
failure rate, failure share, paired gain/loss count, and concrete row examples.
The same rule applies in reverse: a new algorithm must be evaluated under every
existing compatible analysis. This bidirectional propagation is part of the
acceptance gate, not optional follow-up work.

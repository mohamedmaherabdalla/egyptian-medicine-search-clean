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
Algorithm 5 and imply that Algorithms 1-4 were not tested.

## 2. Stable Names

| Stable ID | Descriptive row-level alias | System |
| --- | --- | --- |
| `algorithm_1` | `algorithm_1_current_app` | Current application search. |
| `algorithm_2` | `algorithm_2_external_fast` | External English fast search. |
| `algorithm_3` | `algorithm_3_rank_fusion` | Rank fusion of Algorithms 1 and 2 with safety gates. |
| `algorithm_4` | `algorithm_4_family_rescue` | Algorithm 2 with bounded family rescue and conservative clarification. |
| `algorithm_5` | `algorithm_5_evidence_rescue` | Evidence-guided retrieval, bounded reranking, and conservative clarification. |
| `algorithm_6` | `algorithm_6_consensus_search` | Algorithm 5 ranking plus a bounded independently supported top-20 consensus slot, learned advisory evidence, and confirmation-required output. |

The static GitHub Pages application does not execute `algorithm_6`. GitHub
Pages serves JavaScript and catalog JSON but cannot run the Python Algorithm 6
pipeline. Its runtime ID is `browser_consensus_search`; evaluate and report it
separately from `algorithm_6_consensus_search`.

The server-hosted UI calls `POST /api/search` in `app/api.py`. Its runtime must
prove `algorithm=algorithm_6` and `evaluation_version=algorithm_6_consensus_v1`
through `GET /api/runtime`; the frontend rejects a response with another
algorithm ID instead of silently switching engines. The API loads one shared
catalog and runs one worker because the unchanged Algorithm 6 process uses
about 2 GB RAM.

| ID | Evaluation data |
| --- | --- |
| `legacy_341901` | Original generated commercial-name benchmark. |
| `synthetic_115000` | Deterministic 34-category synthetic benchmark. |
| `synthetic_clean_core_66257` | Primary positive-retrieval synthetic benchmark; 66,257 unique, catalog-resolvable, collision-free query-target pairs. |
| `ocr_rxhandbd` | RxHandBD OCR and downstream search benchmark. |
| `ocr_data4_data5` | Paired processed and original word-crop benchmark. |
| `ocr_predictions_595` | Fourteen-model OCR prediction export and downstream search cases. |
| `retrieval_primary_464` | Collision-free unique OCR query-target pairs used by comparative baselines and ablations. |
| `unreadable_text_catalog_sample` | Deterministic before, middle, and after unreadable-span requests generated from the application catalog. |
| `partial_text_catalog_sample` | Deterministic ordered one-, two-, and three-fragment requests with hidden characters and optional bounded reading errors. |
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
| Synthetic clean unique pair | One vote for each row in `synthetic_clean_core_66257`; all rows are unique and scoreable. | Headline synthetic positive-retrieval comparison. |
| Unreadable locked request | One visible-pattern request whose complete relevant-family set belongs to development or holdout, never both. | Headline unreadable-span retrieval and safety comparison. |
| Unreadable inclusive request | One sampled visible-pattern request, including patterns whose relevant families cross development and holdout. | Collision and insufficient-evidence diagnostics only. |
| Partial-text primary request | Ordered visible fragments with enough positional or multi-fragment evidence to evaluate source-family recovery. | Flexible partial-text headline retrieval and safety score. |
| Single-fuzzy-fragment diagnostic | One four-character fragment with one injected error and unknown position. | Low-evidence behavior audit; never a unique-source accuracy claim. |
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
8. Learned features and thresholds use development or cross-fit training rows
   only; retrospective holdout rows contribute no learned counts or fitted
   parameters.
9. A historical holdout reused during development is labeled
   `retrospective_holdout`, never `fresh_blind_holdout`.

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

For unreadable-span requests, relevance is the complete set of catalog
families satisfying the declared position constraint. For example, middle mode
with visible prefix `pana` and suffix `ol` accepts every family whose full base
or validated family head begins with `pana`, ends with `ol`, and contains at
least one hidden character between them. A source family used to generate the
mask is not the only relevant label when other catalog families satisfy the
same constraint. Report source-family rank only as a completion-ordering
diagnostic, and require confirmation for every returned unreadable-span result.

Flexible partial-text evaluation accepts fragments at arbitrary positions and
allows bounded edits inside each fragment. A row enters the primary denominator
only when it has an exact fragment or at least two ordered fragments. A single
short fuzzy fragment remains diagnostic because source-family rank cannot
distinguish retrieval failure from genuine ambiguity. Report this diagnostic
cohort, its no-result rate, and its candidate count beside the primary score.
When ordered fragments reconstruct a complete catalog name exactly, partial
mode accepts a zero-character hidden gap. For example, `JACK ODAN` reconstructs
`JACKODAN`. A fuzzy alignment must still contain at least one hidden character;
this keeps `MELI CAM` as a partial-evidence query rather than treating it as an
exact split. Generate tests across every valid two-part boundary and at least
one three-part boundary per eligible name.
Evaluate common grapheme compression as a separate primary pattern type. The
current deterministic rule covers `CK -> K`, `PH -> F`, `GH -> G`, `QU -> K`,
and repeated letters. Grapheme candidates must not replace raw exact evidence,
must remain confirmation-required, and must preserve indexed versus exhaustive
family-order parity.

A selective correctness score is not clinical confidence. Report its threshold,
coverage, accepted-case accuracy, accepted errors, and split. A passing
Algorithm 6 gate means `likely match, confirmation required`; it cannot authorize
automatic dispensing. Audit-clean P2 performance is provisional when P2
assignment itself uses candidate-union evidence.

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
- Apply Holm correction when one reference is tested against multiple systems;
  retain both raw and adjusted p-values in the result table.
- Bootstrap a confidence interval over case IDs for aggregate metric deltas when
  the denominator is large enough.
- Keep target-family-disjoint holdout results separate from development results.
- Do not tune thresholds on holdout.

## 11. Ablation Evaluation

An Algorithm 4, Algorithm 5, or Algorithm 6 ablation changes one component and
keeps all other code, parameters, cases, and scoring rules fixed. Compare every ablation
with the complete version of the same algorithm on the same primary fair unique
pairs and report:

1. Hit@1 and Hit@20 delta.
2. Behavior and unsafe-confidence delta.
3. Gained and lost case counts.
4. Paired significance result.
5. At least one gained and one lost row when they exist.

An ablation that removes several coupled components must be named as a combined
ablation; it cannot be interpreted as the effect of one component.

For candidate-union systems, remove one source at a time and report paired
gains and losses. Source effects are not assumed additive because a consensus
gate can require several sources to support the same family. Learned rankers
must also include feature-group ablations and must not replace a deterministic
ranker unless they improve the locked development criterion without degrading
retrospective holdout or the synthetic non-regression set.

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

| Technique | Legacy | Synthetic 115k | OCR search | OCR recognition | Search ablations | Human study |
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
- label-audit priority and source-image availability are reported for every new
  gain and remaining miss when supplied targets may be unreliable;
- candidate-union changes pass paired synthetic non-regression before deployment;
- runtime replay agrees exactly with stored rank, top-1, and top-20 outputs;
- generated reports read from canonical tables;
- commands, dependencies, random seeds, and evaluation version are recorded.

Benchmark-specific commands and source files remain in each numbered benchmark
README. This contract owns the shared meaning of the evaluation, not the data or
implementation of an individual run.

## 17. Mandatory Experiment Roster

The following roster is persistent. A new search method is incomplete until it
is compared with every applicable system below on identical case IDs. A report
must not replace this matrix with only the newest method and Algorithm 4.

### 17.1 Experiment 1: Retrieval Baselines and Algorithms 1-6

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
11. Algorithm 5, evidence-guided rescue with conservative clarification.
12. Algorithm 6, Algorithm 5 rank-1 order plus bounded consensus retrieval and
    confirmation-required output.

Character 3-gram BM25 may be added as another baseline. It must not silently
replace TF-IDF because changing the weighting scheme changes the experiment.

For every system, report Hit@1, Hit@5, Hit@10, Hit@20, MRR@20, unsafe confident
top-1, clarification rate, candidate count, preparation time, and measured
query time.
When implementations expose different batch interfaces, report measured time
per query and label whether it is batch elapsed time divided by batch size or
an individually timed call. Do not claim deployment-latency superiority until
all systems run through one isolated end-to-end timing harness.
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
| Synthetic clean core | All 66,257 unique rows, target-family-disjoint development and holdout diagnostics, all clean category memberships, all clean error types, edit-distance bands, and dangerous gold-closer pairs. |
| Manual cases | Every supplied row after expected-family normalization, plus a documented unmappable-label audit. |
| Deployment parity | The same browser query and catalog version when the method is deployable. |

An expanded open-source comparison must also search for distinct feasible
method families rather than collecting package names that implement the same
ranking. Record every reviewed repository in an inventory with one status:
`evaluated`, `cached`, `represented`, `duplicate`, or `excluded`. An exclusion
must name the missing contract, such as contextual mention text, a different
ontology, unavailable training labels, or a server-only ranking that cannot be
reproduced locally. Composite systems require component removals; parameter
variants such as edit radius or n-gram size must be labeled sensitivity tests,
not component ablations.

### 17.2 Experiment 2: Algorithms 4, 5, and 6 Ablation

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

Apply the same one-removal rule to Algorithm 5. Run every named retrieval,
scoring, reranking, context, and safety component on the 464 primary OCR pairs,
then run each implementation feature flag separately so a grouped result cannot
hide an inactive or compensating subcomponent. Confirm the complete system and
the broad component removals on all 66,257 synthetic clean-core pairs. Report
full-only and ablation-only paired case counts, not only aggregate deltas, and
include one concrete rank change for every removal that changes Hit@1 or
Hit@20.

For Algorithm 6, use two ablation layers. First, replace its Algorithm 5 base
with each one-component-removed Algorithm 5 output, then rerun every remaining
Algorithm 6 source, merge rule, and gate. This measures the nested component's
effect on complete Algorithm 6 rather than reporting the Algorithm 5-only
ablation as an Algorithm 6 result. Second, remove the bounded consensus slot and
each additional candidate source one at a time. Evaluate the learned reranker
separately by removing retriever, edit, n-gram/edge, phonetic, and
length/position feature groups. Evaluate the selective gate with coverage,
accepted errors, and Wilson bounds on cross-fit development and retrospective
holdout. Do not merge advisory learned metrics with deployed deterministic
metrics.

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
The deployed directional OCR exception requires exactly one query digit and
uses only digit-to-letter evidence observed in OCR data. It does not apply the
reverse letter-to-digit assumption or reinterpret dosage-like multi-digit text.

The tested choices are:

| Choice | Ordered evidence |
| --- | --- |
| Current deployed order | Keep Algorithm 5's complete score and candidate-source agreement, then apply the bounded directional OCR rule below. |
| Directional OCR visual tie | Within the first five candidates, switch only when raw distance ties, the alternative alone explains one of `0->O`, `1->I/L`, `2->Z`, `3->E`, `4->A`, `5->S`, `6->G`, or `8->B`, its visual weighted distance is lower, and its full-score gap is at most 0.25. |
| Weighted distance, then position | Lower confusion-weighted edit cost, higher positional evidence, higher edge evidence, dual-retriever agreement, then full score. |
| Position, then weighted distance | Higher position evidence first, then weighted cost, edge evidence, agreement, and full score. |
| Edge, then weighted distance | Higher prefix/suffix edge evidence first, then weighted cost, position, agreement, and full score. |
| Composite lexical evidence | Maximize `-weighted_cost + 0.35*position + 0.25*edge + 0.10*agreement`, then full score. |
| Pareto, gap 0.25 | Switch only when a tied candidate is no worse on weighted cost, position, edge, and agreement, better on at least one, and within 0.25 full-score units. |
| Pareto, gap 0.15 | Same dominance rule with a 0.15 score-gap bound. |
| Pareto, gap 0.10 | Same dominance rule with a 0.10 score-gap bound. |

No character position receives automatic priority. For `CONAL`, both `COBAL`
and `CONIL` are one raw edit away, so the system shows both. For `0IANTA`,
`OIANDA` and `SIENTA` are both two raw edits away, but only `OIANDA` explains
the observed `0` as `O`; it moves first while the response remains
`equal_distance_ambiguity`. The rule fixed 53 clean-core top-1 errors and broke
zero over 66,257 pairs, including 8 fixes and zero breaks on the target-family-
disjoint holdout. A policy is accepted only when selected on development data
and then improves holdout without increasing unsafe confidence.

### 18.1 Bounded Evidence Retrieval for Mixed OCR Errors

This subsection records the first accepted mixed-error expansion. The final
multi-pass result and residual audit are in Section 20; those later metrics
supersede the intermediate totals below.

Algorithm 5 expands retrieval only when the existing first result is farther
than the query-length radius, or when the query contains exactly one OCR-like
digit. The unweighted Damerau radius is 1 edit for 3 characters, 2 for 4-6, 3
for 7-9, and 4 for 10-16. Candidate generation scans compatible catalog lengths
and plausible first characters, then keeps at most 12 families at the nearest
distance. A second bounded path applies one documented OCR transformation, such
as `0->O`, a leading two-character swap, or a glyph grouping such as `CL->D`
and `RN->M`. These are character rules derived from the error generators; no
medicine names occur in the rule.

Retrieval and promotion are separate. Algorithm 5 first reconstructs the winner
that the pre-expansion candidate set would have produced. A newly found family
may replace it only when one of the following holds:

1. It is the unique nearest family, lies inside the length-based radius, is at
   least two ordinary edits closer, and is within 0.40 score units.
2. A one-step OCR variant makes it the unique best candidate at distance 0 or 1,
   improves over the preserved winner by at least two edits under that variant,
   and is within 1.40 score units. A leading-swap promotion must also be the
   unique ordinary nearest family.
3. For a digit variant, the candidate must reduce visual weighted distance more
   than the preserved winner. Equal explanations retain the existing order.

Visual cost is never injected into normal rescue scoring. It is retried only
when normal scoring rejects a family that the independent one-digit OCR variant
retrieved. This distinction fixes `VU1L -> VALL` without changing
`AMRIZ0LN -> AMRIZOLE N`, where both `AMRIZOLE` and `AMRIZOLE N` explain the
same `0->O` glyph.

| Query | Verified family | Previous result | New result | Meaning |
| --- | --- | --- | --- | --- |
| `VU1L` | `VALL` | outside top 20 | rank 1 | `1->L` supplies missing visual evidence. |
| `CLICYNANE` | `DICYNONE` | outside top 20 | rank 1 | `CL->D` exposes a one-edit transformed match. |
| `BSCTECLR` | `BACTICLOR` | outside top 20 | rank 2 | One-edit advantage is shown, not forced first. |
| `BYOFARICLIE` | `BIOFRAICHE` | outside top 20 | rank 2 | The target is recovered while ambiguity remains. |
| `CLEPDIYRM` | `DEPIDERM` | outside top 20 | rank 6 | Retrieval improves even when rank-1 evidence is weak. |
| `AMRIZ0LN` | `AMRIZOLE N` | rank 1 | rank 1 | Equal visual explanations preserve the prior winner. |

The acceptance run evaluated all 8,806 potentially affected pairs from the
66,257-pair clean core. Hit@1 gained 41 cases and lost 0; Hit@20 gained 103 and
lost 0; unsafe confident top-1 remained 0. Overall Hit@1 increased from
64,444/66,257 (97.2637%) to 64,485/66,257 (97.3256%). Hit@20 increased from
65,936/66,257 (99.5155%) to 66,039/66,257 (99.6710%). Development gained 35
Hit@1 and 81 Hit@20 cases; target-family-disjoint holdout gained 6 and 22, with
no losses in either split. On 18,432 mixed-operation pairs, Hit@1 increased from
17,092 (92.7300%) to 17,105 (92.8006%), and Hit@20 increased from 18,171
(98.5840%) to 18,237 (98.9421%). Median latency on the potentially affected
set increased from 24.2791 ms in the stored baseline to 43.0847 ms in the new
run. The 57,451 queries outside this conservative activation set use the
unchanged path.

## 19. Analysis Propagation Rule

When a new baseline, metric, denominator, error grouping, tie policy, or fair
scoring rule is introduced, recompute it for every compatible system in the
mandatory roster. At minimum, publish the aggregate value, per-group value,
failure rate, failure share, paired gain/loss count, and concrete row examples.
The same rule applies in reverse: a new algorithm must be evaluated under every
existing compatible analysis. This bidirectional propagation is part of the
acceptance gate, not optional follow-up work.

## 20. Historical Clean-Core Algorithm 5 Acceptance Audit

The completed 23 July 2026 audit evaluated the Algorithm 5 source revision
available at that time on all 66,257 collision-free clean-core pairs. It uses
target-family-disjoint development and holdout diagnostics, paired before/after
case IDs, unsafe-confidence checks, and an independent full rerun. These values
are retained as historical evidence; they are not the current Algorithm 5
headline.

| Measure | Before residual audit | Historical accepted revision | Paired change |
| --- | ---: | ---: | ---: |
| Hit@1 | 64,391/66,257 (97.1837%) | 65,068/66,257 (98.2055%) | 689 gains, 12 losses, +677 net |
| Hit@20 | 65,936/66,257 (99.5155%) | 66,257/66,257 (100.0000%) | 321 gains, 0 losses |
| Unsafe confident wrong top-1 | 0 | 0 | No regression |
| Development Hit@1 | not the final configuration | 51,962/52,906 (98.22%) | Reported independently |
| Holdout Hit@1 | not the final configuration | 13,106/13,351 (98.16%) | Reported independently |

Every final Hit@1 miss is now a ranking case, not a retrieval failure. Catalog
geometry explains why most cannot be corrected by a universal nearest-name
rule:

| OSA relationship between query and verified family | Hit@1 misses | Meaning |
| --- | ---: | --- |
| Verified family uniquely nearest | 14 | The combined score still ranks another family first. |
| Verified family tied nearest | 572 | Raw distance supports several real catalog families equally. |
| Another catalog family closer | 603 | Visible spelling favors a different real family. |

Mixed operations account for 930 of the remaining 1,189 misses (78.22%).
Two-to-three-edit rows account for 978 misses (82.25%), and five-to-seven
character queries account for 828 (69.64%). These are residual ranking trends,
not candidate-generation gaps, because every verified family appears within
the top 20.

Accepted rules are character-level and catalog-level only. They include bounded
mixed-error retrieval, directional OCR digit evidence, structural ligature
rewrites, exact phonetic rewrites, weighted keyboard evidence, guarded
full-name correction, and conservative score-dominance release. No medicine
name appears in a rule.

Broad rules were rejected when paired evidence showed collateral damage:

| Rejected rule | Hit@1 gains | Hit@1 harms | Decision |
| --- | ---: | ---: | --- |
| Force any unique nearest family | 14 | 125 | Reject, net -111 on the final run. |
| Broad exact-vowel preference | 12 | 33 | Reject, no zero-harm cross-split policy. |
| Broad exact-visual preference | 22 | 46 | Reject, visual similarity alone is insufficient. |
| Broad score dominance | 80 | 619 | Reject, destroys protected multi-signal decisions. |
| General deletion relation | 3 | 18 | Reject, substring evidence is not unique evidence. |
| General insertion relation | 8 | 129 | Reject, extra characters often support another family. |

The final artifact reproduces all 66,257 expected ranks, Hit@1/5/10/20 flags,
first displayed families, and candidate counts. A fixed 1,087-case probe also
produces identical rank and diagnostic hashes under `PYTHONHASHSEED=0` and
`PYTHONHASHSEED=1`. Determinism comes from sorting equal-frequency n-grams,
candidate indexes, delete keys, and floating-point accumulation inputs.

The final acceptance suite contains 85 focused regression tests. A future rule
must improve development and holdout, preserve Hit@20 and unsafe confidence,
and pass the same hash-seed probe before it can replace this configuration.

### Current source revision

The expanded competitor benchmark reran the current Algorithm 5 source on the
same 66,257 case IDs. It reaches 65,057/66,257 Hit@1 (98.1889%) and
66,256/66,257 Hit@20 (99.9985%). Relative to the historical artifact, 44 cases
move into rank 1, 55 move out of rank 1, and 187 ranks change, for a net loss of
11 Hit@1 cases. The single new top-20 miss is `aclox` with verified family
`ADOX`: the historical source ranked it 20, while the current source omits it
from the first 20 and places `AMOCLOX` first. Current development Hit@1 is
51,950/52,906; current holdout Hit@1 is 13,107/13,351. Reports must identify the
source revision instead of treating these two measurements as interchangeable.

## 21. Expanded Competitor And Ablation Benchmark

The expanded benchmark uses two locked denominators and exact case-ID joins:

| Dataset | Cases | Evaluation purpose |
| --- | ---: | --- |
| Fair OCR pairs | 464 | Collision-free unique OCR query-target pairs for testing recovery from real OCR outputs. |
| Synthetic clean core | 66,257 | Catalog-resolvable unique corrupted query-target pairs for broad controlled error coverage. |

The combined comparison contains 53 systems per dataset: six cached classical
baselines, cached Algorithms 1-4, the current Algorithm 5 source, and 42 newly
executed external configurations. Algorithms 1-3 are not rerun. Their existing
row-level predictions are accepted only after the case IDs match the locked
denominator exactly. Across both datasets, the comparison represents 3,536,213
system-case evaluations; 2,802,282 of those rows come from the 42 new
configurations.

The repository inventory contains 75 reviewed entries. Each entry is assigned
one explicit status:

| Status | Meaning |
| --- | --- |
| `evaluated` | A distinct executable configuration was run on both locked datasets. |
| `cached` | An existing row-level result was reused after case-ID validation. |
| `represented` | The method is represented by an evaluated implementation with the same retrieval principle. |
| `duplicate` | The repository or package duplicates another inventoried implementation. |
| `excluded` | The method requires unavailable supervision, embeddings, services, or a different task contract. |

Every evaluated system reports Hit@1, Hit@5, Hit@10, Hit@20, MRR@20, no-result
rate, candidate count, and warm query latency. Aggregate accuracy is not enough.
The same row-level outputs are sliced by compact edit count, normalized distance,
operation profile, query length, shared-bigram evidence, source category, error
type, and development/holdout split. For each slice, publish both failure rate
and failure share: the first measures difficulty inside the slice, while the
second measures its contribution to total misses.

Controlled variants belong to one component family only. Comparisons within a
family hold the dataset, candidate catalog, output depth, and scoring contract
fixed. The external component study therefore compares variants such as
distance radius, Jaro-Winkler threshold, character n-gram size, BM25 tokenizer,
RapidFuzz scorer, SymSpell radius, Fuse.js mode, and FlexSearch mode without
pretending that a difference between unrelated libraries is an ablation.

Algorithm 5 has two ablation layers:

1. The 97-configuration OCR study removes or groups one retrieval, scoring,
   correction, or safety component at a time.
2. The 13-configuration synthetic confirmation reruns the broad component
   families on all 66,257 clean-core pairs.

An Algorithm 5 component is useful only when the paired change is interpreted
with both Hit@1 and Hit@20. Removing a component can improve Hit@1 by breaking
another case, reduce candidate coverage while leaving easy cases unchanged, or
change latency without changing accuracy. The report must therefore include
paired gains, paired harms, net change, confidence interval, affected error
slices, and concrete gained and lost examples.

### Current measured result

| Locked dataset | System | Hit@1 | Hit@20 | Top-20 misses |
| --- | --- | ---: | ---: | ---: |
| 464 fair OCR pairs | Algorithm 5 | 50.4310% | 72.8448% | 126 |
| 464 fair OCR pairs | Algorithm 4 | 47.6293% | 71.1207% | 134 |
| 464 fair OCR pairs | Best external Hit@1, SymSpell distance 3 with catalog frequency | 38.5776% | 55.8190% | 205 |
| 464 fair OCR pairs | Best external Hit@20, Jaro-Winkler | 32.1121% | 67.4569% | 151 |
| 66,257 synthetic pairs | Algorithm 5 | 98.1889% | 99.9985% | 1 |
| 66,257 synthetic pairs | Algorithm 4 | 97.1852% | 99.5155% | 321 |
| 66,257 synthetic pairs | Best external system, Damerau-Levenshtein | 94.7824% | 99.6393% | 239 |

Algorithm 5's family-rescue layer is the largest measured component on the fair
OCR pairs. Removing it lowers Hit@1 by 13.7931 points and Hit@20 by 20.0431
points. Removing weighted edit similarity lowers OCR Hit@20 by 7.1121 points.
Removing all reranking lowers OCR Hit@1 by 9.9138 points and Hit@20 by 2.5862
points. The same family-rescue removal lowers synthetic Hit@1 by 2.8752 points
and Hit@20 by 2.6805 points.

Of Algorithm 5's 126 fair-OCR top-20 misses, at least one measured external
method retrieves the supplied target for 30 and every measured method misses 96.
This is complementarity, not automatic proof that the supplied target label is
correct. Source-image audit remains required for conflicts such as
`LACTULOSE -> LACTO`.

The main failure trend is loss of shared local evidence. Mixed insertion,
deletion, and substitution rows create 108 of 126 misses (85.71%). Queries with
zero shared character bigrams miss 63 of 64 cases, while queries with at least
four shared bigrams miss only 2 of 171. Compact edit distance four or more
creates 118 misses. These slices define the next retrieval target; they do not
justify medicine-specific rules.

Canonical files:

- Runner and inventory:
  `benchmark_04_experiments/run_competitor_benchmark.py`
- Node adapters:
  `benchmark_04_experiments/node_competitor_ranker.mjs`
- Algorithm 5 ablation runner:
  `benchmark_04_experiments/run_algorithm_5_ablations.py`
- Analysis and report generator:
  `benchmark_04_experiments/analyze_competitor_benchmark.py`
- Competitor inventory:
  `benchmark_04_experiments/results/06_competitor_benchmark/competitor_inventory.csv`
- Combined leaderboard and row-level analyses:
  `benchmark_04_experiments/results/06_competitor_benchmark/analysis/`
- Meeting 10 supporting tables:
  `benchmark_04_experiments/results/04_meeting_10/`

The propagation rule in Section 19 applies to this benchmark. Adding a system,
metric, error label, denominator, or tie rule requires recomputing every
compatible comparison and regenerating the report from row-level artifacts.

## 22. Product Context And Current Adjudicated Denominators

Medicine-family recovery and product-variant selection are separate tasks.
Algorithm 4 first retrieves a family from lexical brand evidence. It then parses
structured context and compares it with one catalog package at a time:

| Field | Query example | Normalized evidence |
| --- | --- | --- |
| Strength | `1 gm` | `1G` |
| Concentration | `457mg/5ml` | `457MG/5ML` |
| Dosage form | `tabs`, `susp.`, `Emulgel` | tablet, suspension, gel |
| Route | `oral drops`, `I.M. amp` | oral liquid, injection |
| Release type | `SR`, `XR`, `CR` | sustained, extended, controlled release |

Context may reorder products only after lexical family evidence retrieves them.
The implementation does not pool a strength from one package and a route from
another, and it does not use a dosage match to manufacture an unrelated family
candidate. `AUGMENTIN 457 MG/5 ML SUSPENSION` therefore ranks the matching
suspension package, while a plain `AUGMENTIN` query remains a family-level
comparison.

This representation follows the same product decomposition used by RxNorm,
HL7 FHIR Medication, FDA dosage-form and route standards, and EDQM Standard
Terms: medicinal product identity is represented with separate ingredient,
strength, dose-form, and route fields rather than one unparsed string.

- RxNorm overview: <https://www.nlm.nih.gov/research/umls/rxnorm/overview.html>
- HL7 FHIR Medication: <https://hl7.org/fhir/medication.html>
- FDA dosage form and route: <https://www.fda.gov/industry/data-standards/dosage-form-and-route-administration>
- EDQM Standard Terms: <https://www.edqm.eu/en/standard-terms-database>

Current result claims use two explicit denominators:

| Dataset | Inclusive rows | Primary rows | Algorithm 4 Hit@1 | Hit@20 |
| --- | ---: | ---: | ---: | ---: |
| Supplied manual cases | 150 | 135 adjudicated | 79.26% | 99.26% |
| Post-review OCR pairs | 412 | 412 locked unique pairs | 53.88% | 80.34% |

The context change was also paired against the historical Algorithm 4 result
on all 6,000 V2 rows that contain product context: 4,000 embedded form/strength
rows and 2,000 exact-name-with-strength rows. Every row kept the same input,
expected family, and scoring rule.

| Context benchmark | Historical Hit@1 | Current Hit@1 | Historical Hit@20 | Current Hit@20 |
| --- | ---: | ---: | ---: | ---: |
| Embedded form/strength, 4,000 rows | 94.38% | 98.90% | 99.35% | 99.80% |
| Exact name with strength, 2,000 rows | 85.45% | 97.80% | 98.55% | 99.85% |
| Combined, 6,000 rows | 91.40% | 98.53% | 99.08% | 99.82% |

The paired combined result contains 462 Hit@1 gains and 34 Hit@1 losses, for a
net gain of 428 rows. Hit@20 contains 44 gains and no regressions. Neither run
contains an unsafe confident top-1 response. This is a family-retrieval
evaluation; package selection is verified separately by focused examples such
as `VOLTAREN 100 MG SR TABLET` and `DEVAROL 200,000 IU AMP`.

The manual exclusions are label-contract decisions made independently of the
algorithm result. The OCR denominator remains locked during failure analysis;
an Algorithm 4 miss can request source-image review but cannot delete itself
from the score.

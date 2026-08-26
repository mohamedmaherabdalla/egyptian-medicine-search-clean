# Algorithm 6 PDF section task list

> Historical planning record. GitHub now publishes the finalized content as
> Markdown documentation and intentionally excludes TeX/PDF artifacts.

This checklist controls the concise team-facing handbook and its supporting
evidence package. The user approved the visual rule-entry sample and the
TikZ-based Option 4 capability flow, then authorized work toward the complete
goal. A working LaTeX/PDF may therefore be assembled while the granular items
below remain the acceptance checklist for team review.

The current project goal is to explain every active medicine-search rule with
concrete examples, test it with feature-specific current-source datasets,
preserve failures and their diagnoses, and report fresh results without
conflating accuracy, safety, or developer regression coverage.

## Working agreement

- The document is a human-readable **rule dictionary**, not a source-code dump
  and not a catalogue of test cases without rules.
- Every rule states the actual mapping or behavior first.
- Test cases appear underneath the rule as evidence.
- Implemented, disabled, diagnostic, missing, and proposed rules must be
  labeled separately.
- A proposed rule must never be described as already implemented.
- Long source paths, hashes, and implementation details stay out of the main
  explanation unless the user specifically requests them.
- The concise handbook may be rebuilt from preserved result artifacts at any
  time; a release is complete only after the evidence checks and page-by-page
  render inspection pass.

## Standard entry for every rule

Each approved rule will use this structure:

1. **Rule name and stable ID**
2. **Purpose** - spelling, handwriting shape, visual gap, product context, or
   safety
3. **Observed text or evidence**
4. **Allowed catalog interpretation**
5. **Direction** - symmetric or directional
6. **Exact cost, threshold, length, rank, or operation limit**
7. **Where the rule is active**
8. **Where the rule is not active**
9. **Positive examples**
10. **Negative, exact-name, ambiguity, and collision guards**
11. **Current status** - active, inherited, guard, diagnostic, disabled,
    missing, or proposed
12. **Test result and remaining gap**

## Status key

- `[x]` Completed/approved and evidence-backed
- `[~]` Implemented or drafted and still awaiting final review/QA
- `[ ]` Not started

Unchecked granular rule items below remain explicit review questions; they do
not imply that the rule is absent from the current handbook draft.

## August 22 current-source evidence checkpoint

Every preserved JSON summary binds the exact evaluated Algorithm 5, Algorithm
6, product-reranker, API, and catalog bytes. The loopback runtime reported
Algorithm 6 with 25,066 products and 17,476 exact base families.

| Evidence class | Dataset and evaluator | Fresh result | Report wording | Artifact |
| --- | --- | --- | --- | --- |
| Accuracy | 800-case ordinary-typo catalog set through `evaluate_rule_test_sets.py` | Hit@1 `799/800`; Hit@5/20 `800/800`; MRR `0.999375` | Retrospective catalog-derived ranking accuracy | [`results/runs/20260822T230616Z/summary.json`](results/runs/20260822T230616Z/summary.json) |
| Safety | 100 ordinary collision rows plus 50 exact-name guards through the same evaluator | `150/150` gating contracts | Safety; never use as an accuracy denominator | [`test_sets/generated/ordinary_typo_collision_safety.csv`](test_sets/generated/ordinary_typo_collision_safety.csv) |
| Accuracy/non-regression | Locked fair OCR 412 through `evaluate_current_fair_ocr_412.py` | Hit@1 `234/412`; Hit@5 `296/412`; Hit@20 `340/412`; MRR@20 `0.633907` | Retrospective, non-blind accuracy; 72 Hit@20 misses remain | [`results/fair_ocr_412_current/latest_summary.json`](results/fair_ocr_412_current/latest_summary.json) |
| Same-data reference | A5, Damerau--Levenshtein, and Jaro--Winkler through `evaluate_current_fair_ocr_baselines.py` | A5 `234/296/338`; Damerau `179/251/299`; Jaro--Winkler `149/256/312` at Hit@1/5/20 | Lexical retrieval references on the same 412 rows and candidate universe; not product-equivalent systems | [`results/fair_ocr_412_baselines_current/latest_summary.json`](results/fair_ocr_412_baselines_current/latest_summary.json) |
| Accuracy plus safety | Fresh 424-case visual identity set through `evaluate_visual_gap_identity_benchmark.py` | Contracts `424/424`; source Hit@1 `313/314`, Hit@5/20 `314/314`; MRR@20 `0.998408`; exact labels `400/400`; safety `100/100` | Retrospective catalog challenge plus gating safety. The `22.1%` literal exact-oracle precision indicator is diagnostic because valid bounded-fuzzy candidates can fall outside the literal oracle | [`results/visual_gap_identity/latest_summary.json`](results/visual_gap_identity/latest_summary.json) |
| Product selection/safety | Fresh 440-case strict product-ID set through `evaluate_product_selection_benchmark.py` | `440/440`: 240 unique strengths, 40 ties, 80 form cases, 80 impossible-strength abstentions | Catalog-derived selection and fail-closed contract coverage, not name-search accuracy | [`results/product_selection_strict/latest_summary.json`](results/product_selection_strict/latest_summary.json) |
| Paired recovery | Locked 200-case product-context set | baseline `197/200` -> context `200/200`; zero regressions | Paired benchmark recovery, not general accuracy | [`results/product_context_200_current.json`](results/product_context_200_current.json) |
| Regression/contract | OCR/API plus legacy visual suites through `evaluate_rule_test_sets.py` | `642/642` contracts inside the fresh `1792/1792` unified run | Developer regression coverage only | [`results/runs/20260822T230951Z/summary.json`](results/runs/20260822T230951Z/summary.json) |
| Accuracy plus safety | Hard name-reading benchmark generated without search output, then evaluated through `evaluate_name_rule_hard_benchmark.py` | 3,667 rows: atomic Hit@1/5/20 `1717/1721/1724`; composed `1504/1549/1556`; combined MRR@20 `0.987397`; safety `272/272`; source boundaries `11/11`; diagnostics 190/201 labels visible | Retrospective catalog-derived name-reading accuracy plus separate gating safety/source contracts. The 100-row cross-channel diagnostic cohort is non-gating | [`results/name_rule_hard_benchmark/latest_summary.json`](results/name_rule_hard_benchmark/latest_summary.json) |

The independent dataset generators and manifests are:

- [`generators/generate_visual_gap_identity_benchmark.py`](generators/generate_visual_gap_identity_benchmark.py),
  [`test_sets/generated/visual_gap_identity_benchmark.csv`](test_sets/generated/visual_gap_identity_benchmark.csv),
  and
  [`test_sets/manifests/visual_gap_identity_benchmark.manifest.json`](test_sets/manifests/visual_gap_identity_benchmark.manifest.json);
- [`generators/generate_product_selection_benchmark.py`](generators/generate_product_selection_benchmark.py),
  [`test_sets/generated/product_selection_strict.csv`](test_sets/generated/product_selection_strict.csv),
  and
  [`test_sets/manifests/product_selection_strict.manifest.json`](test_sets/manifests/product_selection_strict.manifest.json);
- [`generators/generate_rule_test_sets.py`](generators/generate_rule_test_sets.py),
  the ordinary-typo and OCR/visual CSVs under
  [`test_sets/generated/`](test_sets/generated/), and
  [`test_sets/manifests/generation_manifest.json`](test_sets/manifests/generation_manifest.json).
- [`generators/generate_name_rule_hard_benchmark.py`](generators/generate_name_rule_hard_benchmark.py),
  the five `name_reading_*.csv` datasets under
  [`test_sets/generated/`](test_sets/generated/), and
  [`test_sets/manifests/name_rule_hard_benchmark.manifest.json`](test_sets/manifests/name_rule_hard_benchmark.manifest.json).

The original `435/440` strict-product result and five oracle adjudications are
retained in
[`results/product_selection_strict/failure_history.md`](results/product_selection_strict/failure_history.md).
The two corrected visual-label defects and unchanged-runtime rerun are retained
in
[`results/visual_gap_identity/failure_history.md`](results/visual_gap_identity/failure_history.md).

The named `javaki + 5 mg -> JAKAVI 5 MG` example is a separate focused API and
product-reranker regression in
[`test_sets/generated/api_scenario_inventory.csv`](test_sets/generated/api_scenario_inventory.csv)
and
[`../benchmark_04_experiments/test_algorithm_6_api_hardening.py`](../benchmark_04_experiments/test_algorithm_6_api_hardening.py).
It must not be described as one of the three recoveries in the locked 200-case
paired benchmark.

## Section tasks

### Task 0 - Document format and workflow

- [x] Use the standard rule-entry format above.
- [x] Work section by section under user direction.
- [x] Keep tests underneath their corresponding rule.
- [x] Move from section-by-section review to full handbook assembly after the
  user explicitly authorized goal execution.
- [x] Open with the user-approved **system capability flow** (Option 4):
  ordinary typo, OCR/handwriting confusion, visual gap, product details, and
  safe conflict handling, each shown through one short input-to-output example.
- [x] Draw that capability flow as native LaTeX vector artwork with TikZ; do
  not use a screenshot or a paragraph-heavy substitute.

### Task 1 - OCR and handwriting grapheme-confusion registry

- [ ] `I / E / Y` pairwise confusion rules.
- [ ] `E / G` directional rules.
- [ ] `D / CL` variable-length grapheme rules.
- [ ] `D / AL` variable-length grapheme rules.
- [ ] Review `D / EL` explicitly as **missing/proposed**, unless it is later
  implemented and reevaluated.
- [ ] Inventory every other implemented character, visual-shape, phonetic,
  keyboard, ligature, transposition, repeat, insertion, and deletion rule.
- [~] Add the active long-phonetic-collapse entry: observed `CKS -> X` or
  `GHT -> T`, followed by at most one ordinary insertion, deletion,
  substitution, or adjacent transposition. State the 5--20 input-length gate,
  protection of the collapsed character, complete exact-family cap of four,
  evidence-only score discount `3.75`, no rank-one promotion, bounded tail
  visibility, and Algorithm 6 tail-eviction protection. Registry and focused
  evidence are complete; concise-handbook placement remains for review.
- [ ] Record costs, symmetry/direction, operation budgets, length gates,
  non-transitivity, exact-name protection, and ambiguity protection.
- [ ] Attach examples and safety cases to each mapping.

### Task 2 - Input normalization and character cleanup

- [ ] English case, spacing, punctuation, compact-key, and separator rules.
- [ ] Arabic digits, Arabic decimal/thousands separators, and Arabic terms.
- [ ] Unicode micro symbols, dotted units, decimal commas, and thousands rules.
- [ ] Repeated-character and character-canonicalization rules.
- [ ] State which transformations apply to medicine names, product details,
  browser fallback, or all paths.

### Task 3 - Ordinary spelling and candidate generation

- [ ] Exact, prefix, suffix, token, n-gram, skeleton, and phonetic retrieval.
- [ ] Delete buckets, short-query retrieval, family heads, and corrected-prefix
  surfacing.
- [ ] Candidate limits, input-length limits, and operation/cost budgets.
- [ ] Explain how OCR grapheme candidates combine with ordinary spelling
  candidates without becoming unlimited fuzzy search.

### Task 4 - Ranking, promotion, and name-safety rules

- [ ] Base scoring and deterministic tie order.
- [ ] Every active promotion/reordering rule, grouped into understandable
  families rather than unexplained source-function names.
- [ ] Exact-name protection.
- [ ] Ambiguous-family and collision protection.
- [ ] Global-uniqueness requirements.
- [ ] Non-transitivity and preserved-top safety repairs.
- [ ] Confirmation-required behavior.

### Task 5 - Visual-gap rules

- [ ] Accepted explicit marker spellings.
- [ ] Leading, trailing, internal, both-edge, and multiple-internal gaps.
- [ ] Explicit markers must hide at least one real target character.
- [ ] Whitespace shorthand and its zero-width behavior.
- [ ] Punctuation that must remain ordinary text.
- [ ] Minimum/maximum visible characters and fragment limits.
- [ ] Exact, fixed-grapheme, OCR-confusion, and fuzzy matching stages.
- [ ] Shared edit/confusion budgets.
- [ ] Target-side hidden-character count and visible coverage.
- [ ] Repeated occurrences, edge anchors, exact-family identity, sorting,
  ambiguity, and confirmation.
- [ ] Attach positive, negative, boundary, collision, and performance examples.

### Task 6 - Strength and numeric-evidence rules

- [ ] Qualified strengths and unit conversion.
- [ ] Combination strengths and repeated components.
- [ ] Concentrations and denominators.
- [ ] Percent, activity units, million-IU, time denominators, and structural
  ratios.
- [ ] Bare and ambiguous numbers.
- [ ] Zero, malformed, unsupported, and conflicting numeric evidence.
- [ ] Exact, partial, equivalent, unknown, and conflict scoring rules.

### Task 7 - Form, package, presentation, route, release, and container rules

- [ ] Dosage-form aliases and subtype compatibility.
- [ ] Package counts, multipacks, unit doses, and package conjunctions.
- [ ] Presentation weight/volume versus active strength.
- [ ] Route rules, including injection subtypes.
- [ ] Immediate versus modified-release rules.
- [ ] Vial, ampoule, syringe, pen, cartridge, and other container distinctions.
- [ ] Missing-metadata, mismatch, and safe-abstention behavior.

### Task 8 - Family admission and product reranking

- [ ] Exact-name hard family boundary.
- [ ] Ordinary top-family admission and diagnostic thresholds.
- [ ] Visual exact-family admission.
- [ ] Product compatibility and minimum evidence.
- [ ] Strong versus weak family reordering.
- [ ] Product ties, family visibility, result caps, and stable product IDs.
- [ ] No-compatible-product response.
- [ ] Main examples such as `javaki + 5 mg`, `brufen + 600`, and
  `brufen + 600 tab`.

### Task 9 - Numeric aliases and short-prefix rules

- [ ] Exact numeric-brand aliases.
- [ ] Numeric-only commercial aliases.
- [ ] Longest-alias precedence and recognized suffix rules.
- [ ] Nearby-number, unknown-suffix, explicit-context, and visual-mode guards.
- [ ] One- and two-character strict-prefix recovery.
- [ ] Too-broad and no-compatible abstention.
- [ ] Main examples such as `1 2 3`, `3 FLY`, `x + 500 tab`, and
  `x + 600 tab`.

### Task 10 - API, confirmation, product identity, and UI rules

- [ ] Request fields and limits.
- [ ] Runtime/health identity checks.
- [ ] Display hydration and no-compatible-product display behavior.
- [ ] Response-level and row-level confirmation.
- [ ] Stable product identity and duplicate-name handling.
- [ ] Browser cache, race, escaping, grouping, and fallback-runtime boundaries.

### Task 11 - Tests attached to every rule

- [ ] Positive behavior.
- [ ] Negative behavior.
- [ ] Exact-name guard.
- [ ] Ambiguity/collision guard.
- [ ] Equality boundary and just-outside-boundary cases.
- [ ] Multi-error and cross-rule interaction cases where relevant.
- [ ] Performance/candidate-cap case where relevant.
- [ ] Downstream non-regression denominator.
- [x] Freeze the hard name-reading dataset shape as 1,724 atomic plus 1,560
  composed accuracy rows, 272 release-gating safety rows, 100 non-gating
  diagnostics, and 11 source-boundary contracts: 3,667 total.
- [x] Keep the hard benchmark's metric-only accuracy, gating safety,
  non-gating diagnostics, and source contracts as separate denominators.
- [x] Preserve and cite complete hard-benchmark run `20260822T225802Z`, with
  its exact source and manifest hashes, before adding its Hit@k, MRR, safety,
  boundary, or diagnostic result to the PDF.
- [x] Clearly distinguish accuracy sets, safety contracts, and developer
  regression coverage. Catalog-derived sets are explicitly retrospective, not
  unbiased external validation.

### Task 12 - Failure diagnosis and reevaluation record

- [x] Preserve the failing input and original output for the fresh strict
  product and visual-identity runs.
- [x] State whether the defect was in the algorithm, label, evaluator, API,
  display layer, or UI.
- [x] Explain the root cause in plain language.
- [x] State that the fresh failures required oracle corrections rather than a
  runtime rule/code change.
- [x] Retain the corrected contracts and both failure histories permanently.
- [x] Preserve the original hard-name composed-collision oracle failure, keep
  its eight query-level failures, and document why only same-fingerprint
  collisions are gating while broader cross-rule collisions remain diagnostic.
- [x] Show the original and corrected focused reruns plus current downstream
  regression evidence.
- [ ] Keep unresolved failures and proposed rules visible.

### Task 13 - Results, limitations, and team wording

- [x] Draft a visual dataset map showing what each dataset tests, its size,
  whether it measures accuracy or regression coverage, and the correct metric.
- [x] Draft same-dataset current-source comparisons for the locked fair OCR
  benchmark; never rank systems across different denominators or protocols.
- [ ] Decide whether the historical synthetic-clean benchmark belongs in the
  concise handbook; do not reuse stale results as current-source accuracy.
- [x] Show current-system results with numerators as well as percentages, and
  show other algorithms only where their stored predictions use the same test
  set and scoring rule.
- [x] Put ordinary-typo, fair-OCR, fresh visual-identity, strict-product, and
  paired product-context metrics in the concise handbook; retain detailed
  strata in machine-readable artifacts.
- [x] Record the generated 3,667-case hard name-reading shape separately from
  its preserved `20260822T225802Z` evaluation result; do not imply that dataset
  generation itself produced the reported metrics.
- [x] Label every baseline and comparison correctly.
- [x] Separate local current-source engineering evidence from deployment
  evidence.
- [x] Label product-context, visual-gap, API, and unit-test results as paired
  recovery, retrospective challenge, safety, or regression/contract coverage
  rather than general accuracy.
- [x] State that confirmation-required search is not autonomous clinical
  selection or clinical validation.
- [~] Decide whether any additional detailed metrics belong in the main
  document after user
  review.
- [ ] List open rules, missing tests, and decisions requested from the team.

### Task 14 - Historical document assembly

- [x] Assemble the user-approved capability-flow and rule-entry presentation
  into the concise handbook.
- [x] Generate concise summary tables from preserved JSON evidence.
- [x] Keep implemented and proposed rules visually distinct.
- [ ] Add navigation, contents, glossary, and cross-references.
- [x] Complete the historical document build and preserve its evidence ledger.
- [~] Render and inspect every PDF page.
- [ ] Repair clipping, overflow, missing glyphs, unclear tables, and broken
  page transitions.
- [x] Publish the test sets, evidence bundle, rule registry, and Markdown
  documentation without TeX/PDF files.

The preserved machine-readable evidence is
[`results/team_handbook_evidence.json`](results/team_handbook_evidence.json),
and the maintained narrative is
[`../docs/ALGORITHM_6_COMPLETE_RULEBOOK.md`](../docs/ALGORITHM_6_COMPLETE_RULEBOOK.md).

## How to continue in chat

The user can review or revise any task by number, for example:

> Start PDF Task 1. Let us decide every OCR/handwriting confusion rule.

The assistant will update the Markdown rule explanation and its attached
evidence, rerun the relevant evaluator, and verify links before changing the
affected item to `[x]`.

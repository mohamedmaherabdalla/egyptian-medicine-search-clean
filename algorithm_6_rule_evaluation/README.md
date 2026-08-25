# Algorithm 6 Rule-by-Rule Evaluation Package

This folder is the reproducible evidence package for the current Python
Algorithm 6 medicine-search runtime. The August 22, 2026 evaluations were run
against a loopback endpoint launched from worktree HEAD `7ed39d0`; because the
worktree contains evaluated, uncommitted source, the authoritative runtime
identity is the per-file SHA-256 provenance embedded in each result artifact,
not the Git commit alone.

The package has four linked purposes:

1. inventory every active rule, guard, diagnostic, and disabled gate with a
   stable rule ID;
2. keep concrete and generated test cases in reviewable CSV files;
3. run the cases, retain row-level outcomes, and explain every failure before
   changing the algorithm; and
4. build a polished LaTeX/PDF report that states the rules, case-generation
   method, failures, fixes, paired regressions, and final acceptance evidence.

## Folder map

| Path | Purpose |
| --- | --- |
| `schemas/` | CSV contracts and rule/test metadata definitions. |
| `generators/` | Deterministic, catalog-derived dataset generators. |
| `test_sets/generated/` | Generated visual-gap, OCR, exact-name, and product-context cases. |
| `test_sets/locked/` | Byte-for-byte copies of reviewed fair and clean evaluation sets. |
| `test_sets/manifests/` | SHA-256 hashes, source revisions, seeds, row counts, and split policy. |
| `evaluators/` | Unified rule-level evaluator and report validators. |
| `results/` | Versioned row-level outcomes, summaries, provenance, and failure-analysis records. |
| `latex/` | Concise team-handbook LaTeX, exhaustive reference LaTeX, generated evidence, and build scripts. |

The final PDF is written to `../output/pdf/` and render-QA intermediates are
written to `../tmp/pdfs/`.

### Publication boundary

Git contains every durable test-set CSV, manifest, generator, evaluator,
selected per-case outcome, compact summary, and failure-history record used by
the reports. Raw API-response JSONL files are intentionally local: together
they exceed 700 MB and several individual hard-benchmark files exceed GitHub's
100 MB file limit. They are reproducible by the documented evaluators and are
content-addressed in the preserved summaries. LaTeX auxiliary files, render-QA
images, duplicate PDF names, caches, and exploratory run directories are also
excluded. The two reviewed PDFs remain versioned under `../output/pdf/`.

## Evidence semantics

The package deliberately keeps three claims separate:

- **Accuracy** uses a fixed oracle and ranking metrics such as Hit@1, Hit@5,
  Hit@20, and MRR. Catalog-derived accuracy sets are retrospective and are not
  blind external or clinical validation.
- **Safety** uses gating contracts such as preserving all ambiguous families,
  protecting exact names, and abstaining when product evidence conflicts. A
  safety pass fraction is not an accuracy estimate.
- **Regression/contract coverage** proves named implementation behaviors still
  hold. Passing generated examples, API scenarios, or focused unit tests does
  not estimate general accuracy.

Lexical baselines are reported only on the same locked queries, oracle, and
candidate-family universe. They are retrieval references, not
product-equivalent systems.

## Current-source evaluation checkpoint

All results below bind the evaluated Algorithm 5, Algorithm 6, product
reranker, API, and catalog bytes in their JSON provenance. The latest endpoint
used Algorithm 6 over 25,066 products and 17,476 exact base families.

| Runtime input | Evaluated path | SHA-256 |
| --- | --- | --- |
| Algorithm 5 engine | [`../benchmark_01_legacy/master_algorithms/algorithm_5_commercial_name_search.py`](../benchmark_01_legacy/master_algorithms/algorithm_5_commercial_name_search.py) | `c5faefb2bfb54c4dfbe4a059b120aaa4121db3c2bdf0606ab0cdef4f56bbbee7` |
| Algorithm 6 consensus layer | [`../benchmark_01_legacy/master_algorithms/algorithm_6_consensus_search.py`](../benchmark_01_legacy/master_algorithms/algorithm_6_consensus_search.py) | `cedf1fce3dac214f5533707c031051efec7343aa8d4342e9ddf7cfe31940fbcb` |
| Product-context reranker | [`../app/product_context_reranker.py`](../app/product_context_reranker.py) | `03780539f9449323a641ab6ad9d2f505f0ed167e6741c63c858bc0b7d873caea` |
| Public API | [`../app/api.py`](../app/api.py) | `752399eec3caf486d1242d61d9176625cd0e42605e6553487e466bd56b8bc6de` |
| Product catalog | [`../app/data/catalog.json`](../app/data/catalog.json) | `d234edaa2669d1eeb46b962e7e3e02df52c6f4d2fd3eca7a2fbf3bc7d159fd9c` |

| Evidence | What it tests | Current result | Correct interpretation | Preserved artifact |
| --- | --- | --- | --- | --- |
| Ordinary typo benchmark | 800 unique-oracle one-edit queries, balanced 200 each across deletion, adjacent transposition, duplicate character, and horizontal keyboard-neighbor substitution | Hit@1 `799/800`; Hit@5 `800/800`; Hit@20 `800/800`; MRR `0.999375` | Retrospective catalog-derived ranking accuracy | [`results/runs/20260822T230616Z/summary.json`](results/runs/20260822T230616Z/summary.json) |
| Ordinary typo collision safety | 100 multi-family collisions plus 50 exact-name guards | `150/150` gating contracts | Safety, not an accuracy denominator | [`test_sets/generated/ordinary_typo_collision_safety.csv`](test_sets/generated/ordinary_typo_collision_safety.csv) and the same [run summary](results/runs/20260822T230616Z/summary.json) |
| Locked fair OCR | 412 reviewed historical OCR/handwriting queries | Hit@1 `234/412`; Hit@5 `296/412`; Hit@20 `340/412`; MRR@20 `0.633907` | Retrospective accuracy and current-source non-regression; 72 Hit@20 misses remain | [`results/fair_ocr_412_current/latest_summary.json`](results/fair_ocr_412_current/latest_summary.json) |
| Same-data OCR references | Current A5, Damerau--Levenshtein, and Jaro--Winkler on the exact same 412 cases and 17,476-family universe | A5 `234/296/338`; Damerau `179/251/299`; Jaro--Winkler `149/256/312` at Hit@1/5/20 | Same-data lexical retrieval comparison only | [`results/fair_ocr_412_baselines_current/latest_summary.json`](results/fair_ocr_412_baselines_current/latest_summary.json) |
| Fresh visual-gap identity benchmark | 424 cases across 16 strata; 314 require recovery of the preselected exact source family | Contracts `424/424`; source Hit@1 `313/314`, Hit@5/20 `314/314`; MRR@20 `0.998408`; exact-oracle identities `400/400`; safety `100/100` | Retrospective catalog challenge plus gating safety. The `22.1%` literal exact-oracle precision indicator is diagnostic because bounded fuzzy results may be valid outside that oracle | [`results/visual_gap_identity/latest_summary.json`](results/visual_gap_identity/latest_summary.json) |
| Strict product selection | Exact-family product-ID selection: 240 unique strengths, 40 legitimate ties, 80 same-strength form cases, and 80 impossible-strength abstentions | `440/440` strict contracts | Catalog-derived product-selection and fail-closed safety coverage, not name-search accuracy | [`results/product_selection_strict/latest_summary.json`](results/product_selection_strict/latest_summary.json) |
| Locked product-context recovery | Same fixed 200 queries with and without product context | baseline `197/200` -> context `200/200`, zero regressions | Paired benchmark recovery, not a general accuracy rate | [`results/product_context_200_current.json`](results/product_context_200_current.json) |
| OCR and legacy visual suites | 236 OCR/API retrieval cases, 2 source guards, and 404 legacy visual cases | `642/642` contracts | Developer regression/contract coverage; part of the fresh `1792/1792` unified run | [`results/runs/20260822T230951Z/summary.json`](results/runs/20260822T230951Z/summary.json) |

The latest hard name-reading benchmark contains **3,667 rows**: 1,724 atomic
mapping accuracy rows, 1,560 composed-error accuracy rows, 272 release-gating
safety rows, 100 non-gating cross-channel diagnostic rows, and 11 source
boundary contracts. In preserved run `20260822T225802Z`, atomic Hit@1/5/20 was
`1717/1721/1724`; composed Hit@1/5/20 was `1504/1549/1556`; combined MRR@20
was `0.987397`; safety passed `272/272`; and source boundaries passed `11/11`.
The non-gating diagnostics made 190 of 201 relevant labels visible in the top
20 and must not be reported as a safety failure rate. The authoritative counts,
per-file hashes, rule quotas, and collision-component split policy are in
[`test_sets/manifests/name_rule_hard_benchmark.manifest.json`](test_sets/manifests/name_rule_hard_benchmark.manifest.json).
The result and exact evaluated-source provenance are in
[`results/name_rule_hard_benchmark/latest_summary.json`](results/name_rule_hard_benchmark/latest_summary.json).

The first strict product run was `435/440`. All five failures were independent
oracle defects involving composite or printed presentations, not runtime
misses; the original run and adjudication are retained in
[`results/product_selection_strict/failure_history.md`](results/product_selection_strict/failure_history.md).
The fresh visual set likewise retains its initial two label defects and their
resolution in
[`results/visual_gap_identity/failure_history.md`](results/visual_gap_identity/failure_history.md).
The hard name-reading package retains its original overbroad composed-collision
oracle and eight resulting safety failures in
[`results/name_rule_hard_benchmark/failure_history.md`](results/name_rule_hard_benchmark/failure_history.md).
That protocol defect was repaired by gating only same-fingerprint collisions
and retaining broader cross-rule collisions as diagnostics; no runtime rule
was removed to make the final safety contracts pass.

The named `javaki + 5 mg -> JAKAVI 5 MG` behavior is a separate focused API and
product-reranker regression, recorded in
[`test_sets/generated/api_scenario_inventory.csv`](test_sets/generated/api_scenario_inventory.csv),
[`../benchmark_04_experiments/test_algorithm_6_api_hardening.py`](../benchmark_04_experiments/test_algorithm_6_api_hardening.py),
and
[`../app/test_product_context_hardening.py`](../app/test_product_context_hardening.py).
It is not one of the three deterministic recoveries that produce the paired
`197/200 -> 200/200` result.

## Non-leaking workflow

The workflow is deliberately sequential:

```text
freeze source + catalog
  -> generate cases without looking at algorithm success
  -> hash and lock datasets
  -> evaluate row by row
  -> classify every failure
  -> make the narrowest general fix (if justified)
  -> rerun the failed stratum
  -> rerun paired fair/clean/product/API regressions
  -> update the report only from preserved artifacts
```

A failed row is never deleted because the algorithm missed it. A label may be
changed only through a separate documented review, and both the old row and the
adjudication record remain in the package.

## Dataset families

- `visual_gap_adversarial.csv`: hand-audited positives, strict negatives,
  ambiguity collisions, short-evidence guards, and performance boundaries.
- `visual_gap_catalog_generated.csv`: family-disjoint deterministic catalog
  cases balanced across leading, trailing, internal, both-edge, multi-gap, and
  shorthand modes.
- `visual_gap_catalog_collisions.csv`: independently generated masks with more
  than one relevant catalog family.
- `visual_gap_protocol.csv`: marker grammar, parser boundaries, exact alignment
  metrics, punctuation/anchor guards, fuzzy operations, and shared-budget cases.
- `visual_gap_identity_benchmark.csv`: 424 independently generated exact-family
  identity and safety cases across 16 visual strata. The generator selects and
  labels cases from catalog structure without importing Algorithm 5/6, calling
  the API, or reading previous results.
- `ocr_grapheme_adversarial.csv`: the locked hard handwriting/OCR cases,
  exact-name guards, ambiguity guards, and clean/fair safety repairs.
- `ocr_grapheme_catalog_generated.csv`: deterministic one- and two-operation
  cases from the directional grapheme registry.
- `name_reading_atomic_accuracy.csv`: 1,724 metric-only single-mapping rows
  sampled by declared rule and leakage-safe split.
- `name_reading_composed_accuracy.csv`: 1,560 metric-only two-mechanism rows,
  including registered mapping plus insertion, deletion, substitution,
  transposition, duplicate, or spacing cases.
- `name_reading_collision_safety.csv`: 272 release-gating exact-name and
  same-fingerprint ambiguity contracts.
- `name_reading_cross_channel_diagnostics.csv`: 100 broader collision rows
  reported as diagnostics rather than release gates.
- `name_reading_source_boundaries.csv`: 11 source-level contracts for depth,
  length, non-transitivity, first-character scope, and variant caps.
- `ordinary_typo_catalog_benchmark.csv`: 800 deterministic, metric-only
  ordinary-typo accuracy rows balanced across deletion, adjacent
  transposition, duplicated-character, and horizontal-keyboard-neighbor
  substitutions. Each query has exactly one relevant exact catalog family
  under the locked edit channel.
- `ordinary_typo_collision_safety.csv`: 100 multi-family collision rows and 50
  exact-name collision guards generated from the same independent catalog
  oracle. These are gating safety contracts, not an accuracy denominator.
- `product_context_200.csv`: the locked deterministic exact-context sample used
  by the 197/200 to 200/200 acceptance check.
- `product_selection_strict.csv`: 440 independently generated product-ID
  contracts for unique strength, legitimate exact-strength ties, same-strength
  form disambiguation, and impossible-strength abstention.
- `unit_test_inventory.csv`: every focused Python rule test with a stable source
  location and rule-family classification.
- `api_scenario_inventory.csv`: the live API contract scenarios.
- `rule_registry.csv`: the authoritative crosswalk from rule ID to source,
  bounds, positive evidence, negative guard, and test-set coverage.
- `locked/fair_ocr_412.csv`, `locked/fair_ocr_excluded_52.csv`, and
  `locked/synthetic_clean_66257.csv`: reviewed external regression inputs,
  copied byte-for-byte and validated by SHA-256.

### Ordinary-typo benchmark protocol

The ordinary-typo generator reads compact exact base names directly from the
frozen catalog and enumerates four one-edit operations. It never imports an
algorithm score or reads a prior result. It then inverts the generated query
index to determine every relevant source family. Unique-label queries enter
the accuracy benchmark; shared queries enter collision safety; and generated
queries that are themselves exact catalog names become exact-name guards.

Before any row is selected, all families sharing a generated query are joined
into connected components. The exact-name family is joined too when a query is
an exact catalog name. SHA-256 assigns the complete component to development
or holdout, so related families cannot leak across splits.

The evaluator reports Hit@1, Hit@5, Hit@20, MRR, and macro relevant-family
recall@20 overall and by primary mutation and query-length stratum. An accuracy
miss is recorded in those metrics but is not called a regression failure.
Collision preservation and exact-name rank-one guards remain gating.

### Hard name-reading benchmark protocol

[`generators/generate_name_rule_hard_benchmark.py`](generators/generate_name_rule_hard_benchmark.py)
reads the declared Algorithm 2/5 mapping registries and frozen catalog without
reading search output. It enumerates 482,315 atomic and 540,465 composed
candidate mutations before deterministic quota selection. Every family joined
by any generated query collision is assigned to the same development or
holdout component, preventing a collision neighborhood from crossing splits.

The 1,724 atomic and 1,560 composed rows measure rank with Hit@1/5/20 and MRR;
they are not green regression assertions. The 272 safety rows are hard
contracts. The 100 cross-rule collision rows are explicitly diagnostic because
their families need not have the same operation fingerprint. The 11 boundary
rows check source contracts rather than ranking. These five roles sum to 3,667
rows and must remain separate in summaries.

The active long-collapse evidence path is represented directly in this set.
Only observed `CKS -> X` and `GHT -> T` qualify. After that collapse, Algorithm
5 may use at most one ordinary insertion, deletion, substitution, or adjacent
transposition to find exact families. It protects the character created by the
collapse, abstains rather than truncating when more than four exact families
match, scores the result as evidence only, preserves the incumbent rank one,
and reserves bounded tail visibility. Atomic rows contain 24 selected cases per
mapping; composed rows exercise the collapse with second errors; the safety set
includes the `GHTAXA -> TADA; TALA` ambiguity. Focused source/API guards also
cover `CKSEFO -> XEFO`, `OGHTA -> OTAL; VOTA; YOTA`, protected-character
behavior, literal rank-one preservation, and confirmation-required output.

### Fresh visual-gap identity protocol

[`generators/generate_visual_gap_identity_benchmark.py`](generators/generate_visual_gap_identity_benchmark.py)
derives exact family identities and full exact relevant-family sets from the
frozen catalog, then applies deterministic visual masks across leading,
trailing, internal, both-edge, multi-gap, shorthand, marker, ambiguity, and
safety strata. Related exact families remain together under the hash-based
development/holdout split. The evaluator uses `matched_family_key` as the
public visual identity and never substitutes product `variant_group` labels.

[`evaluators/evaluate_visual_gap_identity_benchmark.py`](evaluators/evaluate_visual_gap_identity_benchmark.py)
reports the gating contract rate, ordered source-family Hit@1/5/20 and MRR,
exact-oracle recall, and a deliberately diagnostic exact-oracle precision
indicator. Extra bounded-fuzzy candidates are preserved for review instead of
being silently labeled false positives.

### Strict product-selection protocol

[`generators/generate_product_selection_benchmark.py`](generators/generate_product_selection_benchmark.py)
selects exact-family product cases from catalog/source evidence without calling
the search runtime. It stores allowed and forbidden stable product-ID sets so
ties, form disambiguation, and fail-closed conflicts are testable without name
matching shortcuts.

[`evaluators/evaluate_product_selection_benchmark.py`](evaluators/evaluate_product_selection_benchmark.py)
checks those strict ID sets against the public API and preserves per-case raw
responses, latency, source hashes, and failure reasons.

### Current fair-OCR and baseline protocol

[`evaluators/evaluate_current_fair_ocr_412.py`](evaluators/evaluate_current_fair_ocr_412.py)
evaluates the locked 412-row set through the current public API using exact
base-family identity. The separately run
[`evaluators/evaluate_current_fair_ocr_baselines.py`](evaluators/evaluate_current_fair_ocr_baselines.py)
uses the identical oracle and family universe for A5 and two simple lexical
references. Development and holdout labels are retained for stratification,
but neither split is blind in this report.

### Shared evaluation contracts and provenance

[`evaluators/evaluate_rule_test_sets.py`](evaluators/evaluate_rule_test_sets.py)
runs the ordinary-typo, OCR, and legacy visual packages. All new evaluators use
[`evaluators/result_contracts.py`](evaluators/result_contracts.py) for strict
identity/reason checks and
[`provenance.py`](provenance.py) for the common runtime source binding. Their
meta-tests are
[`evaluators/test_result_contracts.py`](evaluators/test_result_contracts.py)
and [`evaluators/test_provenance.py`](evaluators/test_provenance.py).

## Rebuild

From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  algorithm_6_rule_evaluation/generators/generate_rule_registry.py

PYTHONDONTWRITEBYTECODE=1 python3 \
  algorithm_6_rule_evaluation/generators/generate_rule_test_sets.py

PYTHONDONTWRITEBYTECODE=1 python3 \
  algorithm_6_rule_evaluation/generators/generate_visual_gap_identity_benchmark.py

PYTHONDONTWRITEBYTECODE=1 python3 \
  algorithm_6_rule_evaluation/generators/generate_product_selection_benchmark.py

PYTHONDONTWRITEBYTECODE=1 python3 \
  algorithm_6_rule_evaluation/generators/generate_name_rule_hard_benchmark.py

PYTHONDONTWRITEBYTECODE=1 python3 \
  algorithm_6_rule_evaluation/evaluators/evaluate_rule_test_sets.py \
  --base-url http://127.0.0.1:8014

# Run only the ordinary-typo accuracy and collision/safety package.
PYTHONDONTWRITEBYTECODE=1 python3 \
  algorithm_6_rule_evaluation/evaluators/evaluate_rule_test_sets.py \
  --base-url http://127.0.0.1:8014 --only-ordinary-typos

# These evaluators each expose `--help` for their dataset/output arguments.
PYTHONDONTWRITEBYTECODE=1 python3 \
  algorithm_6_rule_evaluation/evaluators/evaluate_visual_gap_identity_benchmark.py \
  --base-url http://127.0.0.1:8014

PYTHONDONTWRITEBYTECODE=1 python3 \
  algorithm_6_rule_evaluation/evaluators/evaluate_product_selection_benchmark.py \
  --base-url http://127.0.0.1:8014

PYTHONDONTWRITEBYTECODE=1 python3 \
  algorithm_6_rule_evaluation/evaluators/evaluate_name_rule_hard_benchmark.py \
  --base-url http://127.0.0.1:8014

PYTHONDONTWRITEBYTECODE=1 python3 \
  algorithm_6_rule_evaluation/evaluators/evaluate_current_fair_ocr_412.py \
  --base-url http://127.0.0.1:8014

# Rebuild the concise, team-facing evidence macros and handbook.
PYTHONDONTWRITEBYTECODE=1 python3 \
  algorithm_6_rule_evaluation/generators/generate_team_handbook_results.py

bash algorithm_6_rule_evaluation/latex/build_team_handbook.sh

# Rebuild the separate exhaustive reference PDF.
bash algorithm_6_rule_evaluation/latex/build_pdf.sh
```

Exact commands, source hashes, dependency versions, and evaluation timestamps
are emitted in the manifests and copied into the report.

The concise handbook source is
[`latex/team_handbook.tex`](latex/team_handbook.tex), its generated result
macros are in
[`latex/generated/team_results.tex`](latex/generated/team_results.tex), and
the machine-readable evidence bundle is
[`results/team_handbook_evidence.json`](results/team_handbook_evidence.json).
Its build writes
[`../output/pdf/medicine_search_team_handbook.pdf`](../output/pdf/medicine_search_team_handbook.pdf).

The separate exhaustive-reference build regenerates both Pandoc appendices,
the executable manifest, and the 336-row registry fragments before compiling
with XeLaTeX. `pandoc`, `latexmk`, and a XeLaTeX-capable TeX distribution are
required for that build. PDF rendering and visual QA remain explicit release
steps: render every page with Poppler before distributing either rebuilt
artifact.

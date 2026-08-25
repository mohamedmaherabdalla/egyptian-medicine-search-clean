# Test case schema

The legacy rule-test CSV files use the common columns below. A file may leave a
field empty when it is not meaningful for that rule family. The hard
name-reading benchmark uses the dedicated schema documented after the ordinary
typo extension because it separates rank metrics, release-gating safety,
non-gating diagnostics, and source contracts in one protocol.

| Column | Meaning |
| --- | --- |
| `case_id` | Stable ID derived from rule, method, query, target, and seed. |
| `rule_id` | Stable rule identifier from `rule_registry.csv`. |
| `case_type` | Positive, negative, ambiguity, boundary, performance, or regression. |
| `source` | Manual audit, catalog generation, locked benchmark, or source test. |
| `generation_method` | Human-readable deterministic construction method. |
| `seed` | Fixed seed/salt used for deterministic selection. |
| `split` | Development, holdout, challenge, locked, or regression. |
| `query` | Medicine-name input sent to Algorithm 6. |
| `product_context` | Optional product-details input; empty for name-only tests. |
| `expected_families` | Semicolon-delimited acceptable exact family keys. |
| `forbidden_families` | Semicolon-delimited exact families that must not appear. |
| `expected_products` | Semicolon-delimited accepted stable catalog product IDs. |
| `expected_decision` | Required API/Algorithm 6 decision type when applicable. |
| `expected_mode` | Visual-gap mode when applicable. |
| `match_policy` | Whether all, any, or only relevant returned families are required. |
| `request_limit` | Requested result limit; defaults to 20. |
| `expected_candidate_count` | Full pre-truncation candidate count when locked. |
| `target_family_key` | Exact row whose alignment metrics are checked. |
| `expected_hidden_character_count` | Hidden target characters after target-side alignment. |
| `expected_visible_coverage` | Target-side visible coverage after alignment. |
| `maximum_rank` | Highest accepted rank for a positive target. |
| `required_reason` | Evidence/reason that must be present. |
| `forbidden_reason` | Evidence/reason that must not be present. |
| `confirmation_required` | Whether every result must require confirmation. |
| `notes` | Safety intent and adjudication notes. |

The ordinary-typo files append these feature-specific columns:

| Column | Meaning |
| --- | --- |
| `evaluation_kind` | `accuracy_benchmark`, `collision_safety`, or `exact_name_safety`. Accuracy rows are metric-only; the two safety kinds are gating. |
| `primary_mutation` | Exclusive reporting stratum used for balanced selection. |
| `mutation_strata` | Every locked edit operation that can produce this query from its independently relevant family/families. |
| `query_length_bucket` | Reporting bucket: 4--6, 7--9, 10--12, or 13--17 compact characters. |
| `source_family_keys` | Every exact family that independently generates the query under the locked ordinary-edit channel. |
| `collision_component_id` | Stable ID of the full connected family component used for leakage-safe splitting. |
| `relevance_count` | Number of acceptable families for the row's evaluation contract. |
| `exact_catalog_query` | Whether the generated query is itself an exact catalog family and is therefore an exact-name safety guard. |

## Hard name-reading benchmark schema

The hard name-reading package contains 3,667 rows across five files:

| File | Rows | Contract role |
| --- | ---: | --- |
| `name_reading_atomic_accuracy.csv` | 1,724 | Metric-only accuracy for one declared mapping. |
| `name_reading_composed_accuracy.csv` | 1,560 | Metric-only accuracy for two independent error mechanisms. |
| `name_reading_collision_safety.csv` | 272 | Release-gating exact-name and same-fingerprint ambiguity safety. |
| `name_reading_cross_channel_diagnostics.csv` | 100 | Non-gating cross-rule collision diagnostics. |
| `name_reading_source_boundaries.csv` | 11 | Source-level depth, length, non-transitivity, first-character, and cap contracts. |

These files use the following columns:

| Column | Meaning |
| --- | --- |
| `case_id` | Stable SHA-256-derived case identity under the hard-benchmark seed. |
| `evaluation_kind` | `accuracy`, `safety`, `diagnostic`, or `source_contract`; determines metrics and gating semantics. |
| `case_type` | Atomic mapping, composed error, exact-name collision, same-fingerprint ambiguity, cross-rule diagnostic, or boundary subtype. |
| `difficulty_level` | Declared protocol level such as atomic, composed, ambiguity, or source boundary. |
| `rule_family` | Human-facing group: mapping, composed error, ambiguity/collision, or source contract. |
| `rule_id` | Stable mapping/composition/contract ID. Atomic `CKS->X` and `GHT->T` rows use `NAME-MAP-CKS-TO-X` and `NAME-MAP-GHT-TO-T`. |
| `mapping` | Semicolon-delimited observed-to-catalog mapping(s) and ordinary operation labels. |
| `channels` | Source channel(s), such as direct grapheme, weighted confusion, OCR digit, ligature, phonetic rewrite, or ordinary edit. |
| `operation_count` | Number of independently injected mechanisms. |
| `composition_signature` | Stable composition class, for example `registered_plus_deletion` or `two_registered_mappings`. |
| `position_stratum` | Initial, middle, final, or mixed mutation position. |
| `length_bucket` | Compact-query length bucket: 4--6, 7--9, 10--12, 13--16, or 17--24. |
| `split` | Leakage-safe `development` or `holdout`; source-only rows use the `source_contract` split. |
| `split_group_id` | Connected collision-component ID assigned wholly to one split. |
| `query` | Generated medicine-name query. |
| `source_family_key` | Independently selected exact catalog source family for accuracy/exact-name rows. |
| `relevant_family_keys` | Semicolon-delimited complete relevant-family oracle for the row's declared fingerprint. |
| `expected_rank` | Exact required rank when a hard rank contract applies. |
| `maximum_rank` | Maximum accepted rank when a bounded visibility contract applies. |
| `match_policy` | Metric, literal-rank-one, all-relevant-visible, or diagnostic-all-relevant policy; source contracts use their dedicated fields. |
| `expected_source_contract` | Named source predicate for a boundary row. |
| `expected_source_value` | Canonical expected value for that predicate. |
| `forbidden_source_value` | Value that must not be produced by the source predicate. |
| `request_limit` | Public API result limit; currently 20 for ranking rows. |
| `confirmation_required` | `1` when response- and row-level confirmation are mandatory. |
| `oracle_method` | Independent catalog/source construction used to define relevance. |
| `generation_method` | Deterministic mutation and quota-selection description. |
| `notes` | Safety intent, denominator warning, or source-contract explanation. |

### Long phonetic-collapse rows

`CKS->X` and `GHT->T` atomic rows measure the declared rewrite itself. Composed
rows pair the collapse with a separately injected insertion, deletion, general
substitution, adjacent transposition, duplicate, spacing change, or another
registered mapping. The active evidence helper is narrower: it accepts query
length 5--20, performs one `CKS->X` or `GHT->T` collapse and at most one
ordinary insertion/deletion/substitution/adjacent transposition, forbids that
second edit from rewriting the character created by the collapse, and returns
the complete exact-family set only when it contains at most four families.
The evidence is score-discounted by 3.75, cannot itself promote rank one, and
may reserve only bounded tail visibility. Consequently, composed rows outside
that narrow helper are still valid measurements of the broader name-reading
layer; they are not mislabeled helper contracts.

## Identity rules

Visual-gap relevance uses the exact matched base family (`matched_family_key` or
`matched_family_name`), not the broad display `variant_group`. Product cases use
stable catalog product IDs, not normalized commercial names. Ordinary family
cases use compact exact base-family keys.

## Split rules

Catalog-generated development/holdout assignment is a deterministic SHA-256
function of the exact family key. A family can appear in only one split even if
multiple query modes are generated from it. Hand-audited collision and boundary
sets use the separate `challenge` split and do not tune thresholds.

Ordinary-typo rows use a stronger collision-component split. The generator
joins every family that produces the same query under the locked edit channel
and also joins the exact catalog family when a generated query is itself exact.
SHA-256 assigns the complete connected component to development or holdout.
No member of a typo/collision neighborhood can therefore cross the split.

Hard name-reading rows use a collision-component split across every generated
query-to-family relationship in the atomic and composed candidate universes.
The complete component receives one SHA-256 development/holdout assignment;
no family connected through any generated query collision can cross splits.

## Accuracy versus safety

An `accuracy_benchmark` row contributes Hit@1/5/20 and reciprocal rank even
when its relevant family is absent. That miss is a measured outcome, not a
regression-run execution error. `collision_safety` requires all independently
relevant families in the top 20. `exact_name_safety` requires the exact catalog
family at rank one. Both safety types remain pass/fail contracts.

For the hard name-reading package, `accuracy` rows always contribute Hit@1/5/20
and MRR, including misses. `safety` rows are release-gating contracts: literal
exact families must remain rank one and all same-fingerprint families must
remain visible. `diagnostic` rows report broader cross-rule collisions but
never become release gates. `source_contract` rows compare named source values
and are hard contracts, not ranking accuracy. These denominators must not be
combined into one pass rate.

## Failure preservation

The evaluator writes every row to `results/case_results.csv`. Failed rows are
copied to `results/failures.csv` and summarized in
`results/failure_analysis.md`; generators never read these files, so a later
regeneration cannot silently select only passing cases.

The hard name-reading evaluator snapshots all five CSVs and their manifest,
then writes `per_case.jsonl`, `raw_responses.jsonl`, `failures.jsonl`, and
`summary.json` under a timestamped `results/name_rule_hard_benchmark/runs/`
directory. Its `failures.jsonl` contains safety/source-contract failures;
accuracy misses remain visible in per-case metrics instead of being relabeled
as execution failures.

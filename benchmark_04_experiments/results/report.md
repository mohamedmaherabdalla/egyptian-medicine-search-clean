# Retrieval Baselines and Algorithm 4 Ablations

## Evaluation contract

The primary comparison uses 464 distinct scored compact query-target pairs. The inclusive view keeps all 595 OCR observations, including repeats and 17 real-drug-name collisions. Index construction happens once and is excluded from per-query latency.

Hit@1 means the verified commercial family is first. Hit@20 means it appears anywhere in the first 20. MRR@20 rewards earlier relevant ranks and gives zero to top-20 misses.

## Experiment 1: retrieval methods

| Algorithm | n | Hit@1 | Hit@5 | Hit@20 | MRR@20 | Mean ms/query | Build ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| algorithm_4_family_rescue | 464 | 47.63% | 61.85% | 71.12% | 0.5375 | 14.89 | 8731.7 |
| baseline_levenshtein | 464 | 34.27% | 50.86% | 59.27% | 0.4170 | 0.73 | 0.0 |
| baseline_jaro_winkler | 464 | 32.11% | 55.17% | 67.46% | 0.4254 | 0.69 | 0.0 |
| baseline_rapidfuzz_token_ratio | 464 | 31.47% | 48.92% | 59.05% | 0.3944 | 8.17 | 0.4 |
| algorithm_2_external_fast | 464 | 25.86% | 43.75% | 51.29% | 0.3292 | 4.75 | 4464.5 |
| algorithm_3_rank_fusion | 464 | 25.65% | 40.95% | 53.02% | 0.3264 | 6.84 | 13347.0 |
| algorithm_1_current_app | 464 | 23.71% | 31.47% | 38.15% | 0.2726 | 1.28 | 4879.4 |
| baseline_char_3gram_tfidf | 464 | 18.32% | 35.78% | 47.41% | 0.2580 | 0.52 | 71.6 |
| baseline_phonetic | 464 | 6.90% | 16.81% | 23.28% | 0.1102 | 0.48 | 0.2 |
| baseline_exact_prefix | 464 | 2.59% | 2.80% | 3.02% | 0.0272 | 0.76 | 1.6 |

### Method definitions

- `algorithm_1_current_app`: Algorithm 1, current application candidate generation and safety ranking.
- `algorithm_2_external_fast`: Algorithm 2, external English fast lexical search.
- `algorithm_3_rank_fusion`: Algorithm 3, weighted rank fusion of Algorithms 1 and 2.
- `algorithm_4_family_rescue`: Algorithm 4, Algorithm 2 plus family-level rescue and conservative reranking.
- `baseline_char_3gram_tfidf`: Cosine similarity over L2-normalized TF-IDF vectors of compact character trigrams.
- `baseline_exact_prefix`: Exact compact match first, then catalog families beginning with the compact query.
- `baseline_jaro_winkler`: Exhaustive Jaro-Winkler similarity over all compact family names.
- `baseline_levenshtein`: Exhaustive unweighted Levenshtein distance over all compact family names.
- `baseline_phonetic`: Egyptian-medicine phonetic key ranked by unweighted Levenshtein distance between keys.
- `baseline_rapidfuzz_token_ratio`: RapidFuzz token_ratio, the maximum of token-set and token-sort ratios.

### Paired comparison with Algorithm 4

Reference-only counts are pairs recovered by A4 but missed by the comparison. Other-only counts are the reverse. The exact McNemar p-value tests whether the discordant counts are balanced; it does not measure effect size. P-values are exploratory and are not adjusted for multiple comparisons.

| Comparison | Ref-only H@1 | Other-only H@1 | Exact p | Ref-only H@20 | Other-only H@20 | Exact p |
|---|---:|---:|---:|---:|---:|---:|
| algorithm_1_current_app | 116 | 5 | 1.562e-28 | 156 | 3 | 1.834e-42 |
| algorithm_2_external_fast | 103 | 2 | 2.744e-28 | 96 | 4 | 6.45e-24 |
| algorithm_3_rank_fusion | 105 | 3 | 1.294e-27 | 90 | 6 | 2.503e-20 |
| baseline_char_3gram_tfidf | 139 | 3 | 1.712e-37 | 117 | 7 | 7.521e-27 |
| baseline_exact_prefix | 210 | 1 | 1.288e-61 | 316 | 0 | 1.498e-95 |
| baseline_jaro_winkler | 82 | 10 | 3.305e-15 | 33 | 16 | 0.02129 |
| baseline_levenshtein | 66 | 4 | 1.65e-15 | 57 | 2 | 6.144e-15 |
| baseline_phonetic | 189 | 0 | 2.549e-57 | 222 | 0 | 2.967e-67 |
| baseline_rapidfuzz_token_ratio | 83 | 8 | 7.577e-17 | 58 | 2 | 3.176e-15 |

A4 exceeds the strongest classical Hit@1 baseline, exhaustive Levenshtein, by 13.36 percentage points. Jaro-Winkler is the strongest classical Hit@20 baseline; A4 leads it by 3.66 points.

### Concrete ranking switches

The reference is Algorithm 4; the other system is exhaustive Levenshtein.

| Other system | Input | Expected | Outcome | Reference rank | Other rank | Reference top 1 | Other top 1 |
|---|---|---|---|---:|---:|---|---|
| `baseline_levenshtein` | `OSTORED` | `OSTOCAL` | reference only at Hit@1 | 1 | 9 | `OSTOCAL` | `COSTAREB` |
| `baseline_levenshtein` | `LGCMU` | `LACTO` | reference only at Hit@1 | 1 | 3 | `LACTO` | `GOLU` |
| `baseline_levenshtein` | `OSSETIA` | `OSSICA` | reference only at Hit@1 | 1 | 2 | `OSSICA` | `OSPEXIN` |
| `baseline_levenshtein` | `LAMIX` | `LASIX` | other only at Hit@1 | 3 | 1 | `VAMIX` | `LASIX` |
| `baseline_levenshtein` | `LAXIX` | `LASIX` | other only at Hit@1 | 2 | 1 | `LAXIN` | `LASIX` |
| `baseline_levenshtein` | `KEFONOLAE` | `KETOROLAC` | other only at Hit@1 | 3 | 1 | `KAFINOL` | `KETOROLAC` |

## Experiment 2: Algorithm 4 one-component ablations

Each row disables exactly the named query-time component. Negative deltas mean the complete A4 is better; positive deltas mean the ablation performed better and the removed component needs review.

| Variant | n | Hit@1 | Hit@20 | MRR@20 | Delta H@1 | Delta H@20 | Mean ms/query |
|---|---:|---:|---:|---:|---:|---:|---:|
| full_algorithm_4 | 464 | 47.63% | 71.12% | 0.5375 | +0.00 pp | +0.00 pp | 15.11 |
| without_confusable_first_character_expansion | 464 | 47.63% | 71.12% | 0.5381 | +0.00 pp | +0.00 pp | 15.25 |
| without_conservative_reranker | 464 | 41.16% | 70.47% | 0.4896 | -6.47 pp | -0.65 pp | 15.10 |
| without_context_cleanup | 464 | 47.63% | 71.34% | 0.5376 | +0.00 pp | +0.22 pp | 15.14 |
| without_delete_key_retrieval | 464 | 47.63% | 70.91% | 0.5369 | +0.00 pp | -0.22 pp | 14.95 |
| without_external_retriever | 464 | 47.20% | 71.55% | 0.5354 | -0.43 pp | +0.43 pp | 10.60 |
| without_length_bucket_scan | 464 | 46.98% | 68.97% | 0.5296 | -0.65 pp | -2.16 pp | 12.01 |
| without_length_coverage_signal | 464 | 47.20% | 67.67% | 0.5312 | -0.43 pp | -3.45 pp | 14.98 |
| without_ngram_signal | 464 | 46.77% | 70.69% | 0.5332 | -0.86 pp | -0.43 pp | 16.16 |
| without_phonetic_signal | 464 | 47.20% | 71.12% | 0.5382 | -0.43 pp | +0.00 pp | 15.29 |
| without_positional_signal | 464 | 46.12% | 69.40% | 0.5237 | -1.51 pp | -1.72 pp | 14.84 |
| without_prefix_signal | 464 | 46.55% | 68.53% | 0.5249 | -1.08 pp | -2.59 pp | 14.95 |
| without_raw_edit_similarity | 464 | 46.77% | 65.30% | 0.5213 | -0.86 pp | -5.82 pp | 14.77 |
| without_rescue_layer | 464 | 27.37% | 51.08% | 0.3385 | -20.26 pp | -20.04 pp | 5.51 |
| without_retrieval_agreement_bonus | 464 | 47.20% | 70.91% | 0.5383 | -0.43 pp | -0.22 pp | 15.21 |
| without_safety_clarification_gate | 464 | 47.63% | 71.12% | 0.5375 | +0.00 pp | +0.00 pp | 15.09 |
| without_short_edge_retrieval | 464 | 46.77% | 67.46% | 0.5254 | -0.86 pp | -3.66 pp | 13.58 |
| without_skeleton_signal | 464 | 46.98% | 70.69% | 0.5363 | -0.65 pp | -0.43 pp | 14.93 |
| without_strict_full_name_correction | 464 | 46.55% | 71.12% | 0.5303 | -1.08 pp | +0.00 pp | 15.05 |
| without_subsequence_signal | 464 | 47.20% | 70.91% | 0.5356 | -0.43 pp | -0.22 pp | 15.04 |
| without_suffix_signal | 464 | 47.63% | 71.12% | 0.5387 | +0.00 pp | +0.00 pp | 15.12 |
| without_variant_head_rescue | 464 | 44.61% | 69.61% | 0.5110 | -3.02 pp | -1.51 pp | 14.44 |
| without_weighted_confusion_cost | 464 | 46.77% | 70.69% | 0.5299 | -0.86 pp | -0.43 pp | 14.04 |
| without_weighted_edit_similarity | 464 | 46.34% | 63.79% | 0.5130 | -1.29 pp | -7.33 pp | 9.22 |

### Exact removal made by each ablation

- `full_algorithm_4`: No component removed.
- `without_external_retriever`: Replace the Algorithm 2 external pass, including its cleaned-context call, with an empty response; keep family rescue.
- `without_context_cleanup`: Suppress the second external search on strength/form/context-cleaned query text.
- `without_rescue_layer`: Suppress the complete family-rescue pass; keep the external and context searches.
- `without_raw_edit_similarity`: Set the unweighted normalized edit-similarity feature to zero in rescue prefiltering and family scoring; keep raw distance for conservative rank checks.
- `without_weighted_edit_similarity`: Set the confusion-weighted normalized edit-similarity feature to zero; keep unweighted edit evidence.
- `without_prefix_signal`: Set prefix similarity to zero in prefiltering, family scoring, edge evidence, and correction logic.
- `without_suffix_signal`: Set suffix similarity to zero in prefiltering, family scoring, edge evidence, and correction logic.
- `without_ngram_signal`: Remove character 2-, 3-, and 4-gram candidate retrieval and rescue scoring.
- `without_phonetic_signal`: Remove the query phonetic key from rescue candidate retrieval and scoring.
- `without_skeleton_signal`: Remove the consonant-skeleton key from rescue candidate retrieval and scoring.
- `without_subsequence_signal`: Set ordered-subsequence similarity to zero in rescue prefiltering and family scoring.
- `without_positional_signal`: Set same-position character evidence to zero in rescue scoring and conservative corrections.
- `without_length_coverage_signal`: Set query-to-family length coverage to zero in rescue scoring.
- `without_delete_key_retrieval`: Remove deletion-key lookup for full-family and variant-head candidates.
- `without_short_edge_retrieval`: Remove the short-query prefix and suffix candidate-retrieval pass.
- `without_confusable_first_character_expansion`: Remove first-character confusion expansions from candidate retrieval and plausibility checks; exact first-character equality remains.
- `without_length_bucket_scan`: Suppress fallback scanning of compatible-length family buckets.
- `without_variant_head_rescue`: Suppress matching against validated catalog family heads and variants.
- `without_weighted_confusion_cost`: Set every non-identical substitution cost to one, removing reduced costs for known phonetic/vowel confusions.
- `without_retrieval_agreement_bonus`: Remove score bonuses for external/context and external/rescue agreement while retaining each retriever's candidates.
- `without_strict_full_name_correction`: Suppress the bounded rescue-only promotion of a full-name candidate that is strictly closer than the current first result.
- `without_conservative_reranker`: Keep the merged score order and suppress evidence-backed top-rank corrections.
- `without_safety_clarification_gate`: Allow candidates through without Algorithm 4's always-clarify safety gate; retrieval ranking is unchanged.

### Paired switches from full Algorithm 4

| Comparison | Ref-only H@1 | Other-only H@1 | Exact p | Ref-only H@20 | Other-only H@20 | Exact p |
|---|---:|---:|---:|---:|---:|---:|
| without_confusable_first_character_expansion | 0 | 0 | 1 | 0 | 0 | 1 |
| without_conservative_reranker | 31 | 1 | 1.537e-08 | 3 | 0 | 0.25 |
| without_context_cleanup | 0 | 0 | 1 | 0 | 1 | 1 |
| without_delete_key_retrieval | 1 | 1 | 1 | 1 | 0 | 1 |
| without_external_retriever | 6 | 4 | 0.7539 | 3 | 5 | 0.7266 |
| without_length_bucket_scan | 3 | 0 | 0.25 | 10 | 0 | 0.001953 |
| without_length_coverage_signal | 3 | 1 | 0.625 | 17 | 1 | 0.000145 |
| without_ngram_signal | 6 | 2 | 0.2891 | 5 | 3 | 0.7266 |
| without_phonetic_signal | 5 | 3 | 0.7266 | 1 | 1 | 1 |
| without_positional_signal | 8 | 1 | 0.03906 | 10 | 2 | 0.03857 |
| without_prefix_signal | 8 | 3 | 0.2266 | 12 | 0 | 0.0004883 |
| without_raw_edit_similarity | 6 | 2 | 0.2891 | 29 | 2 | 4.629e-07 |
| without_rescue_layer | 96 | 2 | 3.062e-26 | 96 | 3 | 5.106e-25 |
| without_retrieval_agreement_bonus | 2 | 0 | 0.5 | 1 | 0 | 1 |
| without_safety_clarification_gate | 0 | 0 | 1 | 0 | 0 | 1 |
| without_short_edge_retrieval | 4 | 0 | 0.125 | 18 | 1 | 7.629e-05 |
| without_skeleton_signal | 4 | 1 | 0.375 | 2 | 0 | 0.5 |
| without_strict_full_name_correction | 5 | 0 | 0.0625 | 0 | 0 | 1 |
| without_subsequence_signal | 2 | 0 | 0.5 | 2 | 1 | 1 |
| without_suffix_signal | 2 | 2 | 1 | 0 | 0 | 1 |
| without_variant_head_rescue | 16 | 2 | 0.001312 | 7 | 0 | 0.01562 |
| without_weighted_confusion_cost | 7 | 3 | 0.3438 | 5 | 3 | 0.7266 |
| without_weighted_edit_similarity | 10 | 4 | 0.1796 | 36 | 2 | 5.399e-09 |

Removing the rescue layer loses 94 net Hit@1 pairs and 93 net Hit@20 pairs. Removing phonetic evidence produces only 2 net switches in the opposite direction, with exact p=0.727; this is not evidence for deleting the phonetic component.

### Concrete component switches

The reference is full Algorithm 4; examples compare it with the named ablation.

| Other system | Input | Expected | Outcome | Reference rank | Other rank | Reference top 1 | Other top 1 |
|---|---|---|---|---:|---:|---|---|
| `without_conservative_reranker` | `LGCMU` | `LACTO` | reference only at Hit@1 | 1 | 3 | `LACTO` | `LYCOMEN` |
| `without_conservative_reranker` | `NIGROHEX` | `VIGOREX` | reference only at Hit@1 | 1 | 2 | `VIGOREX` | `MUNDOHEX` |
| `without_conservative_reranker` | `INDOVAC` | `INDERAL` | reference only at Hit@1 | 1 | 6 | `INDERAL` | `INDOTOPIC` |
| `without_conservative_reranker` | `ALBUTEROL` | `ALBUTEIN` | other only at Hit@1 | 2 | 1 | `BAMBUTEROL` | `ALBUTEIN` |
| `without_rescue_layer` | `OSTROCOLL` | `OSTOCAL` | reference only at Hit@1 | 1 | 999 | `OSTOCAL` | `STAROCAL` |
| `without_rescue_layer` | `OSTORED` | `OSTOCAL` | reference only at Hit@1 | 1 | 999 | `OSTOCAL` | `ISOTRETODERM` |
| `without_rescue_layer` | `LGCMU` | `LACTO` | reference only at Hit@1 | 1 | 999 | `LACTO` | `LYCOMEN` |
| `without_rescue_layer` | `MYLOX` | `MYOLAX` | other only at Hit@1 | 2 | 1 | `MYLON` | `MYOLAX` |
| `without_rescue_layer` | `TELFA` | `TELFAST` | other only at Hit@1 | 2 | 1 | `SELFA` | `TELFAST` |

## Interpretation limits

The OCR models supplied unequal cases, so these experiments compare search methods on a fixed query set, not OCR model quality. Classical baselines always request clarification; their unsafe-confidence rate is therefore not comparable with a product that emits confident decisions. The pharmacist study remains unexecuted until real participants complete the protocol.

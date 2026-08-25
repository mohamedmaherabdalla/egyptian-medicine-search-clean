#!/usr/bin/env python3
"""Generate the deterministic Algorithm 6 rule registry.

The registry is deliberately source-controlled data, not prose scraped from the
rulebook.  Stable rule IDs remain review handles even when a threshold changes.
The generator fails when critical authority markers disappear, so an algorithm
change cannot silently leave this inventory pointing at a different mechanism.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "algorithm_6_rule_evaluation/test_sets/generated/rule_registry.csv"
MANIFEST = OUTPUT.with_suffix(".manifest.json")
RULEBOOK = ROOT / "docs/ALGORITHM_6_COMPLETE_RULEBOOK.md"

SHARED = "benchmark_01_legacy/evaluate_current_app_search.py"
A2 = "benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py"
A5 = "benchmark_01_legacy/master_algorithms/algorithm_5_commercial_name_search.py"
A6 = "benchmark_01_legacy/master_algorithms/algorithm_6_consensus_search.py"
POLICY = "benchmark_01_legacy/master_algorithms/algorithm_6_policy.json"
PC = "app/product_context_reranker.py"
API = "app/api.py"
UI = "app/app.js"
HTML = "app/index.html"

FIELDNAMES = (
    "rule_id",
    "subsystem",
    "status",
    "rule",
    "threshold_or_value",
    "source_symbols",
    "source_files",
    "rulebook_section",
    "positive_test_coverage",
    "negative_test_coverage",
    "boundary_test_coverage",
    "coverage_status",
    "coverage_gap",
)

ALLOWED_STATUSES = {
    "Active",
    "Guard",
    "Diagnostic",
    "Disabled",
    "Inherited",
    "Provisional",
    "Browser fallback only",
}
ALLOWED_COVERAGE = {"full", "partial", "gap", "diagnostic-only"}

UNIT = "unit_test_inventory.csv"
OCR = "ocr_grapheme_adversarial.csv; ocr_grapheme_catalog_generated.csv"
NAME_HARD_ACCURACY = (
    "name_reading_atomic_accuracy.csv; name_reading_composed_accuracy.csv"
)
NAME_HARD_SAFETY = "name_reading_collision_safety.csv"
VISUAL = "visual_gap_protocol.csv; visual_gap_adversarial.csv; visual_gap_catalog_generated.csv; visual_gap_catalog_collisions.csv"
PRODUCT = "unit_test_inventory.csv; product_context_200.csv"
API_TEST = "api_scenario_inventory.csv"
JS_TEST = "app/test_app.js"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def row(
    rule_id: str,
    subsystem: str,
    status: str,
    rule: str,
    value: str,
    symbols: str,
    files: str,
    section: str,
    positive: str = "",
    negative: str = "",
    boundary: str = "",
    coverage: str = "partial",
    gap: str = "",
) -> dict[str, str]:
    return dict(
        zip(
            FIELDNAMES,
            (
                rule_id,
                subsystem,
                status,
                rule,
                value,
                symbols,
                files,
                section,
                positive,
                negative,
                boundary,
                coverage,
                gap,
            ),
        )
    )


def add_many(target: list[dict[str, str]], rows: Iterable[dict[str, str]]) -> None:
    target.extend(rows)


def build_registry() -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []

    # Shared normalization and catalog identity.
    add_many(
        rules,
        [
            row("SH-NORM-UNICODE-01", "shared_normalization", "Active", "Normalize None to empty, translate Arabic digits, fold configured Arabic letters, uppercase, keep alphanumerics as tokens, and collapse whitespace.", "Ordered transform; Arabic ٠..٩ -> 0..9", "normalize_search; ARABIC_DIGITS; ARABIC_LETTERS", SHARED, "4.1", UNIT, "", "Arabic/Latin punctuation and digit cases", "partial", "No standalone exhaustive normalization truth table."),
            row("SH-NORM-TOKEN-02", "shared_normalization", "Active", "Drop configured English generic/noise tokens and Arabic noise when deriving name tokens.", "ENGLISH_NOISE; GENERIC_TOKENS; ARABIC_NOISE", "tokens_of; ENGLISH_NOISE; GENERIC_TOKENS; ARABIC_NOISE", SHARED, "4.2", UNIT, "Exact name preservation tests", "Mixed name/context inputs", "partial", "Token-list coverage is indirect."),
            row("SH-NORM-COMPACT-03", "shared_normalization", "Active", "Build compact identity by concatenating normalized retained tokens.", "No separators", "compact_key", SHARED, "4.3", OCR, "Exact family collision guards", "Punctuation variants", "full"),
            row("SH-NORM-SKELETON-04", "shared_normalization", "Active", "Build medicine-name skeleton with configured visual folds, vowel removal, and repeat collapse.", "Shared helper representation", "skeleton", SHARED, "4.3", UNIT, "", "", "partial", "No direct per-transform unit matrix."),
            row("SH-NORM-PHONETIC-05", "shared_normalization", "Active", "Build the shared drug phonetic key after configured digraph and consonant-class folds.", "Shared helper representation", "drug_phonetic_key", SHARED, "4.3", UNIT, "", "", "partial", "Mostly covered through retrieval outcomes."),
            row("SH-NORM-NUMBER-06", "shared_normalization", "Active", "Extract decimal number tokens from normalized query text.", "Decimal token set", "parse_numbers", SHARED, "4.4", PRODUCT, "Malformed/unknown suffix cases", "Arabic digit and decimal cases", "partial", "Product parser has stronger direct coverage than this legacy helper."),
            row("CAT-FAMILY-IDENTITY-01", "catalog", "Active", "Construct unique family records from base b, falling back to commercial name n, deduplicated by compact exact family key.", "25,066 products -> exactly 17,476 families", "build_rescue_index; build_families", f"{A5}; {A6}", "3.2; 13.1", "Runtime/API invariants", "Startup mismatch fails", "Exact family count", "full"),
            row("CAT-VARIANT-GROUP-02", "catalog", "Guard", "Group by first normalized token only for token length >=4, cohort size >=2, and shared manufacturer; group is display metadata, not product admission.", "token length >=4; cohort >=2; shared manufacturer", "assign_variant_groups; variant_family_keys", f"{A5}; {A6}", "3.3", "BRUFEN family tests", "Variant-sibling isolation", "Independent BRUFEN bases", "full"),
            row("CAT-PRODUCT-EXACT-BASE-03", "catalog", "Guard", "Maintain records_by_family under exact base identity separately from broad records_by_group.", "Exact compact b, fallback n", "ProductCatalog; build_product_catalog", PC, "3.4", PRODUCT, "Broad sibling exclusion cases", "Visual exact-family context cases", "full"),
            row("CAT-NUMERIC-ALIASES-04", "catalog", "Active", "Precompute exact leading-number aliases: numeric-only requires >=2 leading numbers; numeric-brand requires >=1 leading number followed by exact base tokens.", "Build-time exact indexes; deterministic family sort", "numeric_alias_groups; numeric_brand_alias_families; build_product_catalog", PC, "3.4", PRODUCT, "Near-number and unknown-suffix guards", "Single-number numeric-only rejection", "full"),
            row("CAT-STABLE-PRODUCT-ID-05", "catalog", "Guard", "Preserve catalog row ID as selected_product_id so duplicate normalized commercial names remain distinct selections.", "ID-first identity", "product_result; add_display_fields", f"{PC}; {API}", "2.4; 17.12", PRODUCT, "Duplicate-name collision tests", "Tie identity cases", "full"),
        ],
    )

    # Inherited Algorithm 2.
    add_many(
        rules,
        [
            row("A2-NORMALIZE-01", "algorithm_2", "Inherited", "Uppercase; map & to AND and + to PLUS; replace non-ASCII-alphanumeric runs with spaces; collapse whitespace; compact by deleting separators.", "English-only", "normalize_name; compact_name", A2, "5.1", UNIT, "", "Punctuation and whitespace", "partial", "No dedicated Algorithm 2 normalization matrix in this package."),
            row("A2-SKELETON-02", "algorithm_2", "Inherited", "Skeleton maps PH->F, CQK->K, PV->B, SZ->S, removes vowels, and collapses repeats.", "Exact transform sequence", "skeleton", A2, "5.1", UNIT, "", "", "partial", "Outcome coverage only."),
            row("A2-PHONETIC-03", "algorithm_2", "Inherited", "Phonetic key maps PH->F, CK->K, GH->G, BPFV->P, DT->T, CGKQ->K, SZ->S, J->G, removes vowels, and collapses repeats.", "Exact transform sequence", "phonetic_key", A2, "5.1", UNIT, "", "", "partial", "Outcome coverage only."),
            row("A2-MEDICINE-ALIASES-04", "algorithm_2", "Inherited", "Apply the explicit medicine alias table for PANADOL, AUGMENTIN, VOLTAREN, BRUFEN, KETOFAN, and NEXIUM spellings.", "27 aliases; exact compact lookup", "ALIAS_TABLE", A2, "5.2", UNIT, "Exact literal protection", "Alias/no-alias boundaries", "partial", "Not every alias has a named registry row."),
            row("A2-CONFUSION-COST-05", "algorithm_2", "Inherited", "Use symmetric low-cost substitutions V/F, P/B, C/K, Q/K, I/E, O/U, Y/I, S/Z, T/D, G/J.", "substitution 0.45; other 1; insert/delete 1; transpose 0.45", "CONFUSION_PAIRS; substitution_cost; damerau_levenshtein", A2, "5.3", OCR, "Exact-name and ambiguity guards", "Length/edit boundaries", "partial", "No isolated direction-by-direction A2 matrix."),
            row("A2-COMMON-TOKEN-06", "algorithm_2", "Inherited", "Treat explicit common commercial tokens or tokens present in >=0.5% of records as common, with reduced IDF-weighted contribution.", "COMMON_DF_RATIO=0.005; common base=0.20; specific base=1.0", "COMMON_DF_RATIO; COMMON_COMMERCIAL_TOKENS; token_score", A2, "5.4", UNIT, "", "DF boundary", "gap", "No direct common-token threshold test in generated package."),
            row("A2-INDEXES-07", "algorithm_2", "Inherited", "Build exact, prefix 2..12, suffix 3..12, token/prefix 2..8, 3/4-gram, skeleton/phonetic 3..10, and delete indexes.", "delete depth 0 <4, 1 at 4..7, 2 >7; discard delete keys <3", "SearchIndexes; build_indexes; max_deletes_for", A2, "5.5", UNIT, "", "Delete-depth boundaries", "partial", "Index structure lacks direct exhaustive assertions."),
            row("A2-MODES-08", "algorithm_2", "Inherited", "Classify too-short, exact-like, common-token, prefix, suffix, middle, skeleton, phonetic, phrase, and full-typo modes using documented gates.", "too_short <=2; prefix >=3; suffix/middle >=4; full typo >=4", "classify_query", A2, "5.6", UNIT, "", "Short query boundaries", "partial", "Not every mode has a named direct test."),
            row("A2-CANDIDATES-09", "algorithm_2", "Inherited", "Generate candidates from exact/alias, prefix, suffix, token, rare grams, skeleton, phonetic, and bounded delete buckets.", "3 rare 4-grams; then 3 rare 3-grams if <40; skeleton cap 1000; phonetic 1200; delete 800; common bucket 1200", "generate_candidates", A2, "5.7", UNIT, "", "Bucket caps", "partial", "Bucket cap behavior is not directly asserted."),
            row("A2-FEATURES-10", "algorithm_2", "Inherited", "Compute edit, containment/edge, subsequence, skeleton, phonetic, IDF Jaccard, token, token order, and compact-max features using documented formulas.", "See rulebook 5.8 exact coefficients", "edit_similarity; subsequence_score; skeleton_similarity; phonetic_similarity; ngram_score; token_score", A2, "5.8", UNIT, "", "", "partial", "Feature values are not frozen independently."),
            row("A2-MODE-SCORES-11", "algorithm_2", "Inherited", "Score exact, full typo, prefix, suffix, middle, skeleton, phrase, and common-token modes with the documented coefficient vectors; use maximum mode score.", "Exact=1.00; alias=.97; common capped .62; remaining vectors in Section 5.9", "mode_scores", A2, "5.9", UNIT, "", "", "partial", "Coefficient-level golden values are absent."),
            row("A2-PENALTIES-12", "algorithm_2", "Inherited", "Apply short, common-only, candidate-volume, and weak-evidence penalties; clip final score to [0,1] and discard zero.", "-.15 short; -.25 common-only; -.20 >1200 short; -.10 >400 short; -.10 weak-only", "score_record", A2, "5.10", UNIT, "", "Candidate-count thresholds", "partial", "No direct penalty threshold suite."),
            row("A2-CONFIDENCE-13", "algorithm_2", "Inherited", "Assign high >=.85, medium >=.72, else low; response status also uses score/margin/query-length/close-candidate guards.", "no result no_match; top<.55 low; >=6 within .08 ambiguous; high margin .12; medium margin .06", "result_confidence; confidence_status", A2, "5.10", UNIT, "Always-confirm downstream guard", "Score/margin boundaries", "partial", "Downstream A5 overrides auto-selection; raw A2 thresholds not exhaustively tested."),
        ],
    )

    # Algorithm 5 retrieval, scoring, transformations, and safety.
    add_many(
        rules,
        [
            row("A5-INDEX-FAMILY-01", "algorithm_5_retrieval", "Active", "Build unique-family exact, prefix/suffix, n-gram, skeleton, phonetic, family-head, delete, length, first-character, and structural indexes.", "prefix/suffix 2..12; grams 2/3/4; key prefixes 3..10; prefix-risk 1..6", "build_rescue_index", A5, "6", OCR, "", "Index bounds", "partial", "Index contents not independently frozen."),
            row("A5-CONTEXT-CLEAN-02", "algorithm_5_retrieval", "Guard", "Run a second Algorithm 2 pass only after removing recognized strength/form noise while preserving leading numeric brands.", "cleaned length >=3; different/nonempty; block cleaned<=4 with original<=8", "clean_context_query; should_run_context_search", A5, "7", UNIT, "Numeric-brand protection tests", "Short cleaned-query boundary", "full"),
            row("A5-RESCUE-GATE-03", "algorithm_5_retrieval", "Active", "Activate rescue for short 3..4 queries, empty base results, uncertain base results, exact/corrected-prefix grapheme evidence, or bounded long-phonetic-collapse evidence.", "confident gate top<.82 or margin<.045; nonconfident skip only length>=6 top>=.78 margin>=.08", "should_run_rescue; phonetic_collapse_one_edit_family_evidence; search_catalog", A5, "8.2", f"{OCR}; {NAME_HARD_ACCURACY}; {NAME_HARD_SAFETY}", "Clean/fair safety", "Short/confident boundaries", "full"),
            row("A5-LENGTH-SCAN-04", "algorithm_5_retrieval", "Guard", "Length scan only for query length 4..12 with confidence/candidate-count gates; filter compatible length and plausible first character.", "ID cap 2200; radius 0 if core>=220 else 3", "should_length_scan; length_scan_ids", A5, "8.3", OCR, "Clean/fair safety", "Length 3/4/12/13", "partial", "No direct scan-size invariant in generated tests."),
            row("A5-BASE-CANDIDATES-05", "algorithm_5_retrieval", "Active", "Combine exact, prefix/pairwise-first-char, suffix, rare grams, skeleton, phonetic, ligature, phonetic rewrite, stutter, and delete buckets.", "4 rare 4-grams; then 5 rare 3-grams if <160; delete length 3..18 bucket<=650", "candidate_family_ids", A5, "8.4", OCR, "Exact-name safety", "Length/bucket boundaries", "partial", "Some legacy candidate sources lack isolated cases."),
            row("A5-PREFILTER-06", "algorithm_5_retrieval", "Guard", "Apply documented cheap family prefilter formula; exact family scores 9; reject extreme weak length mismatch; retain top bounded pools.", "RESCUE_PREFILTER_LIMIT=45; EDGE=15/45; exact=9.0; formula Section 8.5", "prefilter_family_ids; cheap_family_prefilter_score", A5, "8.5", OCR, "Fair/clean safety", "Pool thresholds", "partial", "No coefficient-level golden test."),
            row("A5-SHORT-RESCUE-07", "algorithm_5_retrieval", "Active", "Use bounded keyboard, two-deletion, consonant/phonetic frame, edge, visible-head, and general head rescues for short/partial queries.", "short frame return 8; raw<=3 weighted<=2.25; visible-head<=4; head distance<=2", "short_keyboard_exact_family_ids; short_two_deletion_family_ids; short_frame_family_ids; short_edge_family_ids; short_visible_head_family_ids; variant_head_family_ids", A5, "8.6", OCR, "Short false-positive guards", "Length 2..8", "partial", "Legacy sub-rescues are covered unevenly."),
            row("A5-NEAREST-FALLBACK-08", "algorithm_5_retrieval", "Guard", "Run bounded nearest fallback for length 3..16 only when base top is absent/outside radius; require plausible first char and unique tie set <=12.", "radius 1/2/3/4 by lengths <=3/<=6/<=9/<=16; tie cap 12", "should_run_nearest_fallback; nearest_fallback_radius; bounded_nearest_family_ids", A5, "8.7", OCR, "Ambiguity guards", "Length/radius/tie caps", "partial", "Direct radius table not fully enumerated."),
            row("A5-SIMPLE-CONFUSIONS-09", "algorithm_5_ocr", "Active", "Use CKQ, SZ, FV, PB, DT, GJ, MN, IEY, and OU as legacy character confusion groups.", "group substitution .45", "CONFUSION_GROUPS; CONFUSION_PAIRS", A5, "9.1", OCR, "Non-transitivity and exact-name guards", "Directional hard cases", "full"),
            row("A5-WEIGHTED-DAMERAU-10", "algorithm_5_ocr", "Active", "Weighted Damerau: exact 0, OCR digit .45 when enabled, configured confusion .45, vowel-vowel .70, other substitution 1, insertion/deletion 1, transpose .55; optionally take bounded grapheme evidence minimum.", "custom grapheme ops 1 below length6 else 2", "damerau; substitution_cost; bounded_grapheme_edit_evidence", A5, "9.2; 24.3", OCR, "LGCMU and transitivity guards", "Length 5/6 and 24+", "full"),
            row("A5-OCR-DIGITS-11", "algorithm_5_ocr", "Active", "Apply directional digit-to-letter variants without reverse letter-to-digit expansion.", "0->O; 1->I/L; 2->Z; 3->E; 4->A; 5->S; 6->G; 8->B", "OCR_DIGIT_TO_LETTERS", A5, "9.3", OCR, "Clean/fair digit guards", "Exactly-one-digit tie gate", "partial", "Not every allowed digit-target pair has a dedicated case; 7 and 9 have no expansion."),
            row("A5-LIGATURES-12", "algorithm_5_ocr", "Active", "Apply directional/symmetric ligature and multi-character pairs documented in the source registry.", "generator uses first 6 legacy pairs; exact variants remain bounded", "DIRECTIONAL_VISUAL_LIGATURE_PAIRS; LIGATURE_CONFUSION_PAIRS; GENERATOR_LIGATURE_PAIRS", A5, "9.4", OCR, "Raw-worse AL->D guard", "Variable-length directions", "full"),
            row("A5-CHAINS-13", "algorithm_5_ocr", "Active", "Generate bounded visual, phonetic, exact rewrite, mixed transposition, deletion, and short OCR chains; never treat evidence as automatic selection.", "EVIDENCE_VARIANT_LIMIT=12; MIXED_VARIANT_LIMIT=48; exact chain discounts Section 9.9", "evidence_query_variants; visual_phonetic_chain_family_ids; visual_visual_deletion_family_ids; transposition_deletion_exact_family_ids; ligature_vowel_chain_family_ids; ligature_vowel_transposition_family_ids; transpose_vowel_deletion_family_ids; vowel_phonetic_deletion_family_ids; keyboard_vowel_deletion_family_ids; short_ocr_combined_family_ids", A5, "9.7-9.9", OCR, "Clean/fair paired guards", "Length/depth limits", "partial", "Some legacy chain types have only historical regression coverage."),
            row(
                "A5-PHONETIC-COLLAPSE-13A",
                "algorithm_5_ocr",
                "Guard",
                "For observed CKS->X or GHT->T, retrieve the complete exact-family set after the collapse and at most one ordinary insertion, deletion, substitution, or adjacent transposition; never edit the character created by the collapse, never promote this evidence to rank one, and preserve hidden evidence families in bounded public tail slots.",
                "query length 5..20; only CKS->X/GHT->T; exact-family cap 4 (abstain, do not truncate, above cap); evidence score discount 3.75; public limit>=2; hidden tail rows<=limit-1",
                "LONG_PHONETIC_COLLAPSE_PAIRS; PHONETIC_ONE_EDIT_MAX_FAMILIES; PHONETIC_ONE_EDIT_SCORE_DISCOUNT; phonetic_collapse_one_edit_family_evidence; surface_phonetic_collapse_one_edit_candidates; rerank_results",
                f"{A5}; {A6}",
                "9.6; 9.9; 11.9; 13.5",
                f"{NAME_HARD_ACCURACY}; benchmark_04_experiments/test_algorithm_6_ocr_confusions.py",
                f"{NAME_HARD_SAFETY}; protected-collapse-character and literal-rank-one guards",
                "focused protected-character contract; query length 5/20, exact-family cap 4, and result limit 2 remain incomplete",
                "partial",
                "Atomic/composed and focused ambiguity cases exist; exact 4/5-family, length 4/5/20/21, and public-limit 1/2 boundary pairs are not all isolated.",
            ),
            row("A5-SCORE-FAMILY-14", "algorithm_5_scoring", "Active", "Score family by the exact weighted formula for exact/edit/weighted-edit/edges/ngrams/skeleton/phonetic/subsequence/position/coverage plus documented bonuses and penalties.", "accept >=.62; positional rescue >=.58 with position>=.40 and coverage>=.70", "score_family", A5, "10.1", OCR, "Clean/fair safety", "Acceptance boundaries", "partial", "No coefficient-level golden vector."),
            row("A5-EVIDENCE-REASONS-15", "algorithm_5_scoring", "Active", "Emit auditable exact, warning, head, positional, edit, weighted, prefix, skeleton, phonetic, and bounded-grapheme reasons.", "corrected-prefix fallback=max(.62, .78+.18*coverage-.10*cost)", "score_family; rescue_search", A5, "10.2", OCR, "Forbidden-reason assertions", "Prefix-tail evidence", "full"),
            row("A5-MERGE-16", "algorithm_5_scoring", "Active", "Merge Algorithm 2, cleaned-context Algorithm 2, and rescue contributions with source agreement bonuses.", "A2=.72*score+.32/(rank+2), * .90 if nonconfident; context=.84*score+.40/(rank+2)+.05; rescue=score+.18/(rank+1); bonuses .06/.08", "external_contribution; context_contribution; rescue_contribution; merge_candidates", A5, "10.3", UNIT, "Evidence-guard tests", "Duplicate evidence", "partial", "No standalone merge arithmetic golden set."),
            row("A5-BRAND-GATE-17", "algorithm_5_promotions", "Guard", "Apply spelling correction chain only to brand-like queries with enough evidence.", "compact length 4..20; <=3 tokens; no context-noise; >=2 results; top raw distance !=0", "is_brand_like_query; rank_candidate_core", A5, "11.1", OCR, "Context/noise and exact-name guards", "Length/token boundaries", "partial", "No direct truth table for every conjunct."),
            row("A5-CORE-DUAL-CLOSER-17A", "algorithm_5_promotions", "Guard", "Core correction admits a strictly closer dual-retrieved candidate only inside the raw-distance and score-gap bounds.", "external+rescue; candidate raw<=2; raw gain>=1; score gap<=.25", "rank_candidate_core", A5, "11.2", OCR, "Fair/clean paired guards", "Raw/gap thresholds", "partial", "Conjuncts are not all isolated."),
            row("A5-CORE-PURE-DELETION-17B", "algorithm_5_promotions", "Guard", "Core correction admits a one/two-character pure-deletion candidate only when the incumbent is not itself pure deletion and evidence is no worse.", "candidate no farther; score gap<=.40", "rank_candidate_core; is_pure_deletion_candidate", A5, "11.2", OCR, "False deletion guards", "One/two omissions", "partial", "Legacy outcome coverage only."),
            row("A5-CORE-MULTITOKEN-17C", "algorithm_5_promotions", "Guard", "Core correction may replace a multi-token false positive with a closer single-token candidate.", "candidate raw<=2; closer; score gap<=.20", "rank_candidate_core", A5, "11.2", OCR, "Clean/fair safety", "Token-count and gap boundaries", "partial", "No named isolated multi-token fixture."),
            row("A5-CORE-VARIANT-HEAD-17D", "algorithm_5_promotions", "Guard", "Core correction may use validated family-head evidence only across a different group and with a full effective-distance advantage.", "query>=5; head distance<=2; effective gain>=1; score gap<=1.40", "rank_candidate_core", A5, "11.2", OCR, "ABASAGLAR/SEROPIPE guards", "Strict-prefix exception", "full"),
            row("A5-STRICT-FULL-18", "algorithm_5_promotions", "Guard", "Promote a rescue-only candidate only when strictly closer full-name evidence meets all weighted, edge, rank, and gap gates.", "raw<=3; rescue rank<=5; weighted gain>=.35; edge gain>=.05; score gap<=.35", "promote_strictly_closer_full_name", A5, "11.3", OCR, "Full-name safety guards", "Exact thresholds", "full"),
            row("A5-EVIDENCE-GUARD-19", "algorithm_5_promotions", "Guard", "Restore the pre-expansion top unless a unique nearest or one-transform candidate has decisive bounded evidence.", "nearest gain>=2 gap<=.40; structural transform gain>=2 gap<=1.40", "apply_evidence_retrieval_guard; has_decisive_evidence_promotion", A5, "11.4", OCR, "Clean/fair zero-loss guards", "Leading swap/digit boundaries", "full"),
            row("A5-OCR-VISUAL-TIE-20", "algorithm_5_promotions", "Guard", "For exactly one digit, allow a raw-distance-tied candidate in first five to lead only with lower OCR-visual distance, positive gain, and bounded score gap.", "candidate limit 5; gap<=.25", "promote_ocr_visual_tie", A5, "11.5", OCR, "Non-digit and ambiguity guards", "Exactly one digit", "partial", "Not every digit is tested."),
            row("A5-EXACT-NAME-PROTECT-21", "algorithm_5_safety", "Guard", "After ordinary promotions, restore a returned literal exact catalog family to rank one; skip only legacy unreadable mode.", "exact compact equality", "protect_exact_catalog_name", A5, "24.4", OCR, "21 exact-name guards", "Unreadable-mode exception", "full"),
            row("A5-ALWAYS-CONFIRM-22", "algorithm_5_safety", "Guard", "Require clarification for every Algorithm 5 response, including exact family; emit low confidence and algorithm5_requires_clarification.", "needs_clarification always true", "needs_clarification; response_status; candidate_to_result", A5, "12", UNIT, "No auto-selection contract", "Exact and empty cases", "full"),
            row("A5-PREFIX-RISK-23", "algorithm_5_safety", "Guard", "Treat short dense prefixes as risky; longer than five is not prefix-risky.", "length<=3: >=8 families; length4..5: >=12", "prefix_is_risky", A5, "12", UNIT, "", "Count thresholds", "gap", "No dedicated prefix-risk count boundary tests."),
            row("A5-POST-GRAPHEME-24", "algorithm_5_safety", "Guard", "Apply only three post-grapheme repairs: preserved-chain Pareto release, external-rank chain tie protection, and bounded top-5 shortlist repair.", "rank 2..3 or 2..12; exact thresholds in Section 11.10", "apply_post_grapheme_safety_repairs", A5, "11.10", OCR, "Paired clean/fair zero-loss", "Rank 5/6 and score-gap edges", "full"),
        ],
    )

    # Direct bounded grapheme registry: one stable row per direction.
    grapheme_rules = (
        ("E", "G", "0.60"), ("G", "E", "0.60"),
        ("I", "E", "0.45"), ("E", "I", "0.45"),
        ("Y", "E", "0.45"), ("E", "Y", "0.45"),
        ("I", "Y", "0.45"), ("Y", "I", "0.45"),
        ("CL", "D", "0.40"), ("D", "CL", "0.55"),
        ("AL", "D", "0.45"), ("D", "AL", "0.70"),
    )
    for source, destination, cost in grapheme_rules:
        rules.append(
            row(
                f"OCR-GRAPHEME-{source}-TO-{destination}",
                "ocr_grapheme_registry",
                "Active",
                f"Permit one direct, directional observed-query {source} -> catalog-target {destination} rewrite; generated output is never recursively rewritten.",
                f"cost={cost}",
                "GRAPHEME_CONFUSION_RULES; grapheme_confusion_variants; bounded_grapheme_edit_evidence",
                A5,
                "24.1-24.3",
                OCR,
                "Exact-name/global-ambiguity/non-transitivity guards",
                "Length/depth/cost cases",
                "full",
            )
        )

    add_many(
        rules,
        [
            row("OCR-VARIANT-BOUNDS-13", "ocr_grapheme_registry", "Guard", "Generate direct variants by a left-to-right walk over original observed positions; keep best cost/depth per output and deterministic order.", "input<=24; budget 0 below4, 1 at4..5, 2 at6..24; override clamped 0..2; default output cap512", "maximum_grapheme_confusions; grapheme_confusion_variants; GRAPHEME_VARIANT_LIMIT; MAX_GRAPHEME_VARIANT_INPUT_LENGTH", A5, "24.1-24.2", OCR, "Non-transitivity and ambiguity guards", "Length 3/4/5/6/24/25; cap", "full"),
            row("OCR-EXACT-RETRIEVAL-14", "ocr_grapheme_registry", "Guard", "Retrieve only generated variants that are exact catalog families and refuse alternatives when observed query is already exact.", "Exact family index only", "exact_grapheme_confusion_family_ids", A5, "24.2", OCR, "Literal-name guards", "Exact/nonexact boundary", "full"),
            row("OCR-PREFIX-SURFACE-15", "ocr_grapheme_registry", "Guard", "Surface corrected proper-prefix families only within bounded cost/depth/ambiguity, reserve tail visibility, and never replace rank one.", "query 6..24; corrected>=6; cost<=1.40; prefix bucket<=4; result limit>=2; min global cost", "grapheme_confusion_prefix_family_evidence; surface_grapheme_confusion_prefix_candidates", A5, "24.2; 11.9", OCR, "Too-broad/exact-name guards", "Length/cost/bucket/rank boundaries", "full"),
            row("OCR-DIRECT-PROMOTION-16", "ocr_grapheme_registry", "Guard", "Promote the globally unique minimum-cost exact direct rewrite only when rank, reason, raw/weighted, score-gap, and forbidden-path gates pass.", "inspect top12; score gap<=.65 (defined constant .75 is not used); ordinary raw disadvantage<=1", "promote_exact_grapheme_confusion_candidate; GRAPHEME_PROMOTION_MAX_RANK; GRAPHEME_PROMOTION_MAX_SCORE_GAP", A5, "24.2", OCR, "7 global ambiguity guards and exact-name guards", "Rank/cost/raw-gap boundaries", "full"),
            row("OCR-DOUBLE-D-AL-17", "ocr_grapheme_registry", "Guard", "Allow the sole raw-gap exception for exactly two nonoverlapping D->AL rewrites when all strict evidence conditions pass.", "depth=2; cost=1.40; raw disadvantage<=2; weighted gain>=.25; score gap<=.50; public rank<=6", "promote_exact_grapheme_confusion_candidate; double_identical_rewrite_matches", A5, "24.2", OCR, "Clean 66,257 eligibility zero; false-path guards", "Exact rank/cost/depth", "full"),
            row("OCR-FIRST-CHAR-18", "ocr_grapheme_registry", "Guard", "Use only explicit E<->G pairwise substitutions for prefix-index first-character retrieval; broader legacy groups remain scoring/plausibility only.", "E->G and G->E only", "PAIRWISE_SUBSTITUTION_COSTS; first_char_variants; confusable_chars; first_chars_confusable", A5, "24.4", OCR, "KEONOOL/LGCMU guards", "First-position directions", "full"),
            row("OCR-AL-TO-D-RAW-GUARD-19", "ocr_grapheme_registry", "Guard", "Never promote a raw-worse direct AL->D candidate; also narrow legacy ligature rank extension for new variable-length direct rules.", "AL->D raw-worse forbidden; direct variable-length rank <=3", "promote_exact_grapheme_confusion_candidate; promote_exact_ligature_rank_extension_candidate", A5, "24.2; 24.4", OCR, "Raw-worse regression guards", "Rank 3/4 and raw tie/worse", "full"),
        ],
    )

    # Major A5 promotion rules. Exact thresholds remain individually reviewable.
    promotion_rows = (
        ("UNIQUE-NEAREST", "promote_unique_nearest_candidate", "rank<=3; raw<=4; gain>=2; gap<=.75; protect exact/variant-head"),
        ("CONTAINED-NEAREST", "promote_contained_nearest_candidate", "rank=2; raw<=1; gain>=1; gap<=.25; current top contains and uncorrected"),
        ("PRESERVED-DOMINANT", "promote_preserved_top_dominant_nearest_candidate", "rank=2; raw<=3; raw gain>=1; weighted gain>=1.30; gap<=.10"),
        ("PRESERVED-HIGHER", "promote_preserved_top_higher_score_nearest_candidate", "rank=2; closer and higher score; key not shorter; no existing correction"),
        ("EXACT-LIGATURE-NEAREST", "promote_exact_ligature_nearest_candidate", "unique ranks2..5; public rank<=4; dual; raw gain>=1; weighted no worse; gap<=.40"),
        ("EXACT-LIGATURE-RANK-EXT", "promote_exact_ligature_rank_extension_candidate", "exactly one rewritten family in top5; new variable-length direct rule restricted to rank2..3; raw-worse AL->D forbidden"),
        ("WEIGHTED-EDGE-TIE", "promote_weighted_edge_tie_candidate", "raw tie first5; unique weighted best; rank<=3; weighted gain>=.70; edge no worse; gap<=.40"),
        ("WEIGHTED-EDGE-ADVANTAGE", "promote_weighted_edge_advantage_candidate", "raw tie; rank=2; weighted gain>=.50; edge gain>=.20; gap<=.25"),
        ("WEIGHTED-EXACT-KEY", "promote_weighted_exact_key_tie_candidate", "rank=2; raw tie; dual; exact-key advantage; weighted gain>=.45; gap<=.05"),
        ("EXACT-TRANSPOSITION-TIE", "promote_exact_transposition_tie_candidate", "query>=5; unique ranks2..3; raw tie<=1; weighted no worse; gap<=.25"),
        ("EXACT-TRANSPOSITION-EXT", "promote_exact_transposition_dual_extension_candidate", "unique rank=2 within ranks2..5; raw<=1; dual; weighted no worse; gap<=.65"),
        ("EXACT-KEYBOARD-TIE", "promote_exact_keyboard_key_tie_candidate", "rank=2; raw tie<=1; exact-key advantage; weighted no worse; gap<=.10"),
        ("KEYBOARD-WEIGHTED-EXT", "promote_exact_keyboard_weighted_extension_candidate", "rank=2; raw tie<=1; exact key; weighted gain>=.25; gap<=.15"),
        ("EXACT-VISUAL-EDGE", "promote_exact_visual_edge_tie_candidate", "rank=2; raw tie<=1; weighted disadvantage<=.25; position no worse; edge gain>=.10; gap<=.15"),
        ("EXACT-KEY-PARETO", "promote_exact_key_pareto_tie_candidate", "ranks2..5, rank<=3; raw tie; unique Pareto exact-key gain; gap<=.15"),
        ("PHONETIC-POSITION", "promote_phonetic_position_tie_candidate", "rank<=3; raw tie; phonetic exact advantage; weighted gain>=.50; position gain>=.05; gap<=.40"),
        ("SHIFTED-EDGE", "promote_shifted_edge_agreement_candidate", "rank<=3; raw tie; dual; edge gain>=.30; gap<=.25; unique best external rank"),
        ("VISUAL-DISTANCE", "promote_visual_distance_tie_candidate", "unique best among raw-tied first5; rank=2; visual gain>=.70; gap<=.10"),
        ("SKELETON-POSITION", "promote_skeleton_position_tie_candidate", "rank=2; exact skeleton; raw tie; weighted/position no worse; gap<=.05"),
        ("STUTTER-PREFIX", "promote_exact_stutter_prefix_candidate", "remove duplicated 2/3-character prefix; exactly one candidate"),
        ("EXACT-PHONETIC", "promote_exact_phonetic_rewrite_candidate", "exactly one rewrite; candidate in top5"),
        ("GUARDED-SCORE-CHAIN", "promote_guarded_top_score_dominant_chain_candidate", "rank=2; score advantage>=1.0; raw disadvantage<=2; weighted disadvantage<=2"),
        ("SCORE-CHAIN-RELEASE", "promote_score_dominant_chain_release_candidate", "rank=2; unguarded dual top; rescue rank1; score advantage>=.05; raw disadvantage<=1; weighted no worse"),
        ("VALIDATED-HEAD", "apply_validated_family_head_evidence", "head distance<=2; unique closer same-first; protected top displaced only by one-edit two-anchor head"),
        ("TWO-SIDED-ANCHOR", "promote_two_sided_anchor_tie_candidate", "query>=4; top distance1..2; boundary preservation; gap<=.40"),
        ("POOL-BOUNDED-HEAD", "promote_candidate_pool_bounded_head_candidate", "unique head; raw gain>=1; visual gain>=.30; LCS no worse; gap<=.85; strict-prefix-only full-name exception"),
        ("PARETO-CHARACTER", "promote_pareto_character_evidence_candidate", "top raw>3; candidate rank2..3; no worse on 8 signals; edge gain>=.10; gap<=.30"),
        ("ORDERED-HEAD-SURFACE", "surface_ordered_character_head_candidate", "query7..16; >=3 bigrams; normalized raw<=.46; LCS/query>=.54; LCS/head>=.65; top >=2 edits farther"),
        ("SHORT-HEAD-SURFACE", "surface_short_visible_head_candidates", "query length3..4; bounded representatives<=4; reserves visibility without automatic rank1"),
    )
    for name, symbol, bounds in promotion_rows:
        rules.append(row(f"A5-PROMOTE-{name}", "algorithm_5_promotions", "Guard", f"Apply the {name.lower().replace('-', ' ')} correction/surfacing predicate only when every documented conjunct passes.", bounds, symbol, A5, "11.6-11.9", OCR, "Fair/clean safety regressions", "Rank/score/evidence boundaries", "partial", "Legacy promotion has outcome coverage; not every conjunct has an isolated negative."))

    chain_rows = (
        ("LIG-VOWEL-TRANSPOSE", "5", ".40", "1"),
        ("LIG-VOWEL-TRANSPOSE-EXT", "5", ".75", "1"),
        ("LIG-VOWEL", "5", ".40", "0"),
        ("LIG-VOWEL-DIST-EXT", "2", ".05", "1"),
        ("LIG-VOWEL-EDGE-EXT", "2", ".15", "1"),
        ("LIG-VOWEL-MULTI-EXT", "5", ".40", "1"),
        ("VISUAL-PHONETIC", "5", ".10", "1"),
        ("VISUAL-PHONETIC-KEY-EXT", "2", ".40", "0"),
        ("VISUAL-PHONETIC-DUAL-EXT", "4", ".15", "0"),
        ("KEYBOARD-VOWEL-DELETE", "5", ".00", "1"),
        ("KEYBOARD-KEY-EXT", "3", ".25", "1"),
        ("TWO-VISUAL-DELETE", "3", ".02", "1"),
        ("VISUAL-MULTI", "3", ".15", "0"),
        ("TRANSPOSE-DELETE", "3", ".25", "0"),
        ("TRANSPOSE-VOWEL-DELETE", "5", ".00", "0"),
        ("VOWEL-PHONETIC-DELETE", "2", ".25", "2"),
        ("VOWEL-PHONETIC-MULTI-EXT", "2", ".10", "2"),
    )
    for name, rank, gap, raw in chain_rows:
        rules.append(row(f"A5-CHAIN-{name}", "algorithm_5_promotions", "Guard", f"Apply the bounded exact-chain {name.lower().replace('-', ' ')} gate with uniqueness and its call-specific evidence guards.", f"max rank={rank}; max score gap={gap}; max raw disadvantage={raw}; additional guards in Section 11.7", "promote_bounded_exact_chain_candidate", A5, "11.7", OCR, "Paired clean/fair safety", "Rank/gap/raw boundaries", "partial", "Call-specific guard combinations are not all isolated."))

    # Algorithm 6 consensus and learned diagnostic policy.
    add_many(
        rules,
        [
            row("A6-CATALOG-INVARIANT-01", "algorithm_6_consensus", "Guard", "Prepare exactly 17,476 families and all sparse/phonetic/visual indexes; fail startup on count mismatch.", "TOP_K_DEFAULT=20; RRF_CONSTANT=60; family count=17,476", "prepare_catalog; TOP_K_DEFAULT; RRF_CONSTANT", A6, "13.1", API_TEST, "Runtime mismatch failure", "Family count", "full"),
            row("A6-POLICY-LOAD-02", "algorithm_6_consensus", "Guard", "Load default or JSON policy; require rank_1_gate, top_20_gate, and confusion_costs blocks.", "Missing required block -> ValueError", "load_policy; DEFAULT_POLICY", f"{A6}; {POLICY}", "13.1", API_TEST, "", "Missing-key boundary", "partial", "No explicit malformed-policy test in package."),
            row("A6-RETRIEVERS-03", "algorithm_6_consensus", "Active", "Build ten rankings: Algorithm 5, Jaro-Winkler, Match Rating, WRatio, NYSIIS, BM25+ char3, SymSpell edit3, token-sort, Soundex, and Dice char2.", "each top20; BM25 k1=1.5 b=.75; SymSpell edit3 prefix7", "RETRIEVER_NAMES; selected_rankings; bm25_plus_weights; symspell_names", A6, "13.2", API_TEST, "", "Empty/finite-score boundaries", "partial", "Retriever-by-retriever ranking goldens are absent."),
            row("A6-CONSENSUS-ORDER-04", "algorithm_6_consensus", "Active", "Order union candidates by source count, RRF, Levenshtein, Jaro-Winkler, name, compact key; learned similarity is excluded.", "RRF=sum 1/(60+rank); Algorithm5 absent rank=999", "build_consensus; consensus_order", A6, "13.3", API_TEST, "", "Tie ordering", "partial", "No frozen full-union ordering fixture."),
            row("A6-RANK1-GATE-05", "algorithm_6_consensus", "Disabled", "Optional rank-one gate requires all policy source/similarity conditions and protects exact/variant families; currently cannot change order.", "enabled=false; min sources7; source advantage1; Levenshtein advantage .02; max Jaro disadvantage .02; bigram advantage0; A5 rank<=3", "should_promote", f"{A6}; {POLICY}", "13.4; 24.6", "", "", "", "diagnostic-only", "Disabled path lacks live acceptance by design."),
            row("A6-EXTERNAL-SLOT-06", "algorithm_6_consensus", "Active", "Append qualifying consensus-only candidates; evict at most one tail row only when Algorithm 5 already fills the public limit, otherwise fill vacant slots.", "sources>=3; Levenshtein>=.55; Jaro-Winkler>=.85; slots=1 on full list", "external_result; rerank_results", f"{A6}; {POLICY}", "13.5", API_TEST, "Prefix-tail eviction protection", "Full/underfull base list", "partial", "No direct all-vacant-slots scenario in registry."),
            row("A6-PROBABILITY-07", "algorithm_6_consensus", "Disabled", "Calibrated logistic abstention returns probability zero and likely_match false because current policy has no abstention block.", "logit clamp +/-40 if enabled", "calibrated_probability", A6, "13.6", API_TEST, "No auto-confidence guards", "Missing policy block", "full"),
            row("A6-ORDINARY-FLOW-08", "algorithm_6_consensus", "Active", "Preserve Algorithm 5 order, apply optional gate then external slot, rerank sequentially, and report ambiguous/no_match with confirmation.", "candidate_count=10-source union size", "search_catalog; rerank_results; augment_result", A6, "13.7", API_TEST, "Empty and identity guards", "Empty compact query", "full"),
            row("A6-RESULT-IDENTITY-09", "algorithm_6_consensus", "Guard", "Use exact matched_family_name for visual results and ordinary name otherwise.", "source==algorithm_6_visual_gap selects matched identity", "result_name", A6, "15.4; 24.5", VISUAL, "Variant-sibling collision cases", "Visual/product handoff", "full"),
            row("A6-LEARNED-SIMILARITY-10", "algorithm_6_diagnostic", "Diagnostic", "Report learned similarity from the minimum of policy learned-confusion distance and Algorithm 5 weighted Damerau; do not sort on it.", "similarity=max(0,1-distance/max_length)", "learned_confusion_distance; build_consensus", f"{A6}; {POLICY}", "14; 24.6", API_TEST, "Ordering exclusion", "", "diagnostic-only", "Metadata is exercised; no ordering effect is expected."),
            row("A6-TRAINING-CONTRACT-11", "algorithm_6_diagnostic", "Diagnostic", "Record learned policy provenance without holdout or case-specific rules.", "development; 15 families; 211 eligible; holdout_rows_used=0; case_specific_rules=0", "training_contract", POLICY, "14.3", "", "", "", "diagnostic-only", "Provenance metadata only."),
        ],
    )

    policy = json.loads((ROOT / POLICY).read_text(encoding="utf-8"))
    cost_sections = {"insertion": "14.1", "deletion": "14.2", "substitution": "14.3"}
    for operation in ("insertion", "deletion", "substitution"):
        for key, cost in sorted(policy["confusion_costs"][operation].items()):
            safe_key = re.sub(r"[^A-Z0-9]+", "-", key.upper()).strip("-")
            rules.append(row(f"A6-LEARNED-{operation.upper()}-{safe_key}", "algorithm_6_diagnostic", "Diagnostic", f"Use learned directional {operation} cost for {key} only inside learned_confusion_distance.", str(cost), "learned_confusion_distance; confusion_costs", f"{A6}; {POLICY}", cost_sections[operation], API_TEST, "Ordering exclusion", "", "diagnostic-only", "No live ordering effect; policy metadata is not separately golden-tested per cell."))

    # Visual gaps, including the current target-side alignment and punctuation fixes.
    add_many(
        rules,
        [
            row("VG-MARKERS-01", "visual_gap", "Active", "Recognize runs of >=2 dots, >=1 Unicode ellipsis, >=1 asterisk, >=1 question mark, or >=2 underscores as explicit gaps.", r"(?:\.{2,}|…+|\*+|\?+|_{2,})", "VISUAL_GAP_MARKER", A6, "15.1", VISUAL, "Single-dot/punctuation guard", "All marker spellings", "full"),
            row("VG-EXPLICIT-PARSER-02", "visual_gap", "Guard", "Compact visible parts, discard empty parts, retain 1..4 fragments, and require >=2 total visible characters.", "MAX_VISUAL_GAP_FRAGMENTS=4", "parse_visual_gap_query; MAX_VISUAL_GAP_FRAGMENTS", A6, "15.2", VISUAL, "Marker-only/one-visible/five-fragment", "1/2 visible; 4/5 fragments", "full"),
            row("VG-COMPACT-EDGE-ANCHOR-03", "visual_gap", "Guard", "Determine leading/trailing anchors from retained compact text beside the edge marker, not raw punctuation offsets.", "anchor_start=bool(compact_parts[0]); anchor_end=bool(compact_parts[-1])", "parse_visual_gap_query", A6, "15.2 (current source correction)", "visual_gap_protocol.csv: VG-EDGE-COMPACT-ANCHOR", "Punctuation outside edge marker", "(...TRIL and RIVO... )", "full"),
            row("VG-SHORTHAND-WHITESPACE-04", "visual_gap", "Guard", "Only 2..4 whitespace-separated ASCII alphabetic tokens of length >=2 become marker-free shorthand; punctuation-separated words stay ordinary search.", r"[A-Za-z]+(?:\s+[A-Za-z]+){1,3}", "parse_visual_gap_query", A6, "15.3 (current source correction)", "visual_gap_protocol.csv: whitespace shorthand", "visual_gap_protocol.csv: PANA.DOL; PANA-DOL", "2/4 tokens; exact multiword guard", "full"),
            row("VG-SHORTHAND-EXACT-GUARD-05", "visual_gap", "Guard", "Do not reinterpret shorthand when concatenated fragments already equal an exact family whose normalized spelling equals the query.", "exact family + normalized equality", "parse_visual_gap_query", A6, "15.3", VISUAL, "Exact multiword ordinary cases", "Zero-width PANA DOL", "full"),
            row("VG-EXACT-FAMILY-06", "visual_gap", "Guard", "Match complete exact family and distinct family head, but deduplicate and identify results by exact family.compact rather than broad variant group.", "candidate_id=ALG6-GAP-{family.compact}", "visual_gap_matches; visual_gap_result; result_name", A6, "15.4; 24.5", VISUAL, "Broad sibling exclusion", "BRUFEN exact bases", "full"),
            row("VG-RAW-STAGE-07", "visual_gap", "Active", "First attempt literal ordered fragment alignment with requested anchors and one-or-more hidden target characters for every explicit gap.", "stage=0", "ordered_fragment_alignment; visual_gap_matches", A6, "15.5", VISUAL, "Strict edge/internal zero-gap negatives", "Later valid occurrence", "full"),
            row("VG-GRAPHEME-STAGE-08", "visual_gap", "Active", "After raw failure, align fixed grapheme-equivalent keys while preserving source-target width projection for metrics.", "stage=1; PH/F, CK/K, GH/G, C/K, Q/K, repeated-glyph collapse", "visual_grapheme_key; visual_grapheme_projection; visual_gap_matches", A6, "15.5 (current source correction)", VISUAL, "Strict gap negatives", "Variable-width projection", "full"),
            row("VG-DIRECT-STAGE-09", "visual_gap", "Active", "After raw/grapheme failure, apply precomputed direct directional grapheme patterns with one shared query-wide cost/depth budget.", "visible5..7: depth1 cost<=1.00; visible8..24: depth2 cost<=1.40; cap512", "visual_gap_confusion_patterns; visual_gap_matches; VISUAL_GAP_CONFUSION_PATTERN_LIMIT; MAX_VISUAL_GAP_CONFUSION_VISIBLE_CHARACTERS", A6, "15.5; 24.5", VISUAL, "Short-confusion and transitivity guards", "5/7/8/24/25 and 511/512", "full"),
            row("VG-FUZZY-STAGE-10", "visual_gap", "Guard", "After all exact stages fail, share at most one ordinary edit over all fragments; require visible total>=5 and every fragment length>=2.", "stage=3; maximum_edits=1", "ordered_fragment_edit_alignment; anchored_fragment_within_one_edit; visual_gap_matches", A6, "15.5", VISUAL, "Two-error shared-budget negatives", "Insert/delete/substitute cases", "full"),
            row("VG-HIDDEN-GAP-11", "visual_gap", "Guard", "Every explicit internal/leading/trailing gap consumes >=1 target character in raw, grapheme, direct-confusion, and fuzzy paths; shorthand permits zero-width joins.", "minimum adds internal gaps and unanchored explicit edges", "minimum_fragment_target_length; ordered_fragment_alignment; ordered_fragment_edit_alignment", A6, "15.1; 15.5", VISUAL, "9 edge +3 internal strict negatives", "All four stages", "full"),
            row("VG-TARGET-METRICS-12", "visual_gap", "Active", "Compute hidden_character_count and visible_coverage from target characters consumed by the chosen alignment, including variable-length grapheme/direct/fuzzy rewrites.", "hidden=max(0,len(target)-target_visible); coverage=min(1,target_visible/len(target))", "visual_grapheme_projection; ordered_fragment_alignment; ordered_fragment_edit_alignment; visual_gap_matches", A6, "15.6 (current source correction)", "visual_gap_protocol.csv: VG-METRIC-*", "", "CL->D, D->CL, fuzzy length change", "full"),
            row("VG-SORT-13", "visual_gap", "Active", "Sort exact-family matches by stage, visible distance, confusion count, hidden characters, descending coverage, head/full target type, family length, then name.", "stage 0/1/2/3", "visual_gap_matches", A6, "15.6", VISUAL, "Collision preservation", "Metric ties", "full"),
            row("VG-RESPONSE-14", "visual_gap", "Guard", "Return ambiguous, low-confidence, confirmation-required visual responses; explicit syntax remains visual even with no matches, shorthand falls through when empty.", "decision=visual_gap_matches or visual_gap_no_match", "visual_gap_response; search_catalog", A6, "15.7; 13.7", VISUAL, "Explicit no-match and shorthand fallthrough", "Marker-only parser rejection", "full"),
            row("VG-REASONS-15", "visual_gap", "Active", "Report bounded visible edit for nonzero direct/fuzzy distance and grapheme confusion for nonzero direct operation count; never emit obsolete one-visible-edit reason.", "visible_edit_distance rounded 4 decimals", "visual_gap_result", A6, "24.5", VISUAL, "forbidden_reason assertions", "Zero/nonzero distances", "full"),
        ],
    )

    # Product-context parser/reranker.
    add_many(
        rules,
        [
            row("PC-NORMALIZE-01", "product_context", "Active", "Normalize Arabic digits/terms, decimal/thousands separators, Unicode micro, multiplication signs, leading decimals, dotted units/releases, and whitespace before parsing.", "Ordered literal and regex normalization", "normalize_context; CONTEXT_LITERAL_REPLACEMENTS", PC, "17.1", PRODUCT, "Malformed and unknown-token guards", "Arabic/decimal/dotted cases", "full"),
            row("PC-UNITS-02", "product_context", "Active", "Canonicalize mass, volume, activity, substance, equivalent, time, and percent units with exact Decimal factors.", "MCG base mass; ML base volume; IU base activity; H base time", "UNIT_ALIASES; UNIT_FACTORS; measurement", PC, "17.2", PRODUCT, "Wrong-unit conflicts", "Equivalent unit/decimal cases", "full"),
            row("PC-STRENGTH-PARSE-03", "product_context", "Active", "Parse simple, explicit combination, shorthand combination, shared denominator, and concentration strength measurements; keep every component and denominator.", "Counter/multiset semantics; Decimal", "STRENGTH_RE; COMBINATION_STRENGTH_RE; EXPLICIT_COMBINATION_RE; SHARED_DENOMINATOR_COMBINATION_RE; SHARED_SHORTHAND_DENOMINATOR_RE; parse_strengths", PC, "17.3", PRODUCT, "Partial/wrong denominator and zero guards", "Combination/semicolon/shared-unit cases", "full"),
            row("PC-INVALID-ZERO-04", "product_context", "Guard", "Treat zero/invalid numeric evidence as fail-closed invalid_numeric rather than silently dropping it.", "invalid_numeric=true", "parse_evidence; ContextEvidence.invalid_numeric", PC, "17.3; 17.10", PRODUCT, "Invalid-zero cases", "0, .0, denominator zero", "full"),
            row("PC-NUMBER-CLASS-05", "product_context", "Active", "Classify remaining numerics as bare/ambiguous numbers, presentation quantities, package counts, or structural ratios after masking qualified measurements.", "MAX_PLAUSIBLE_PACKAGE_COUNT=400", "masked_numeric_text; split_context_numbers; is_presentation_measurement; STRUCTURAL_RATIO_RE", PC, "17.4; 17.7", PRODUCT, "Decimal-tail and attached-name guards", "400/401 and ratio boundaries", "full"),
            row("PC-FORM-ALIASES-06", "product_context", "Active", "Map tablet/capsule/liquid/injection/container/topical/specialty dosage-form spellings to canonical form categories.", "FORM_ALIASES; strict modifiers preserved", "FORM_ALIASES; mapped_tokens", PC, "17.5", PRODUCT, "Incompatible form/container cases", "Alias and modifier cases", "full"),
            row("PC-ROUTE-ALIASES-07", "product_context", "Active", "Map route aliases while preserving IV, IM, SC, oral, topical, ophthalmic, nasal, vaginal, rectal, sublingual, and inhalation distinctions.", "ROUTE_ALIASES", "ROUTE_ALIASES; mapped_tokens", PC, "17.6", PRODUCT, "Route conflicts", "Injection route distinctions", "full"),
            row("PC-RELEASE-ALIASES-08", "product_context", "Active", "Map controlled/extended/sustained/modified release aliases without collapsing incompatible release types.", "RELEASE_ALIASES", "RELEASE_ALIASES; mapped_tokens", PC, "17.6", PRODUCT, "Release conflicts", "Dotted and long-form aliases", "full"),
            row("PC-PACKAGE-PARSE-09", "product_context", "Active", "Parse explicit packages, form-qualified counts, multipacks, unit-dose packages, conjunctions, and container modifiers; require every explicit package constraint.", "count<=400; multipack outer*inner", "PACKAGE_FORM_RE; MULTIPACK_FORM_RE; EXPLICIT_PACKAGE_RE; UNIT_DOSE_PACKAGE_RE; split_context_numbers", PC, "17.4; 17.11", PRODUCT, "Mismatched conjunction/multipack", "Count 400/401", "full"),
            row("PC-PRODUCT-EVIDENCE-10", "product_context", "Active", "Build product evidence from strength/form/route/name fields and recover semicolon metadata/presentation without converting presentation size into dose strength.", "product record cached evidence", "product_evidence", PC, "17.8", PRODUCT, "Semicolon/metadata guards", "Missing-field fallbacks", "full"),
            row("PC-STRENGTH-SCORE-11", "product_context", "Active", "Require complete Counter equality for exact strength signatures; support component/numerator/concentration evidence and emit conflicts for incomplete combinations or wrong denominators.", "exact +130+10*(extra components); contained component +55; ratio-equivalent +70; numerator-only +35; conflict -120 incompatible; unknown -35; structural ratio +70 or -90 incompatible", "score_product; concentration_ratio_key", PC, "17.9", PRODUCT, "Incomplete/wrong denominator conflicts", "Shared units and structural ratios", "full"),
            row("PC-UNITLESS-SCORE-12", "product_context", "Guard", "Retain bare numbers and interpret against observed strength, presentation, or package numbers without ignoring the number itself.", "bare: strength +85, package +60, presentation +45, conflict -85 incompatible; ambiguous: package +75, strength +55, presentation +35, conflict -60 incompatible", "score_product; split_context_numbers", PC, "17.10", PRODUCT, "Wrong-number and literal-brand guards", "600; 500 tab; Arabic digits", "full"),
            row("PC-COMPATIBILITY-13", "product_context", "Guard", "Require dosage form/container/route/release compatibility; preserve strict oral-solid modifiers and vial/ampoule/injection route distinctions.", "presentation +55/-55; form exact +45, compatible +20, conflict -45; route exact +35, injection-compatible +15, conflict -35; release +35/-35; package +20/-20; explicit conflicts are incompatible", "compare_forms; score_product", PC, "17.11", PRODUCT, "All-conflict and container mismatch", "Alias-compatible boundaries", "full"),
            row("PC-ADMISSION-14", "product_context", "Guard", "Admit only exact base families: exact name locks family; otherwise rank1 plus qualified ranks2..3; visual first three exact matches; aliases admit their exact sets.", "limit=3; rank2/3 raw<=2 and Levenshtein>=.60", "result_family_key; rerank_products; CONTEXT_FAMILY_ADMISSION_LIMIT; CONTEXT_FAMILY_MAX_RAW_EDIT_DISTANCE; CONTEXT_FAMILY_MIN_LEVENSHTEIN_SIMILARITY", PC, "17.12", PRODUCT, "Rank4/distant/variant sibling rejection", "Missing one diagnostic", "full"),
            row("PC-PRODUCT-ELIGIBILITY-15", "product_context", "Guard", "Select a catalog product only when compatible, score>0, at least one match reason, and numeric_match when query has numeric evidence.", "all conjuncts required", "rerank_products; score_product", PC, "17.12", PRODUCT, "No-compatible-product cases", "Numeric/non-numeric contexts", "full"),
            row("PC-QUALIFIED-PRESENTATION-16", "product_context", "Guard", "Reinterpret qualified nonratio mass/volume as exact presentation only when product has no dose strengths and complete measurement Counters match.", "+130; qualified_presentation_exact; numeric_match=true", "rerank_products", PC, "17.12", PRODUCT, "Bare-number no-reorder guard", "Exact 100g/50g presentation", "full"),
            row("PC-TIES-17", "product_context", "Guard", "Keep all top-score product ties up to six, preserve stable IDs, and reserve one best row per family before appending ties.", "<=6 tied products per family; public limit respected", "rerank_products; product_result", PC, "17.12", PRODUCT, "Duplicate-name ID tests", "One-family/multi-family tie limits", "full"),
            row("PC-STRONG-REORDER-18", "product_context", "Active", "Reorder families only for exact strength, unique unitless+form compatibility, presentation+form match, or prepared exact alias; apply name-rank penalty outside alias mode.", "context_score - 14*original_position", "rerank_products", PC, "17.13", PRODUCT, "Form-only/presentation-only/no-form negatives", "197/200 baseline -> 200/200 context", "full"),
            row("PC-NO-COMPATIBLE-19", "product_context", "Guard", "When no admitted family has a compatible positive product, preserve only admitted name rows, annotate conflict, and do not present a catalog product.", "decision=product_context_no_compatible_product", "context_failure_response; rerank_products", PC, "17.14", PRODUCT, "All-conflict cases", "No-name versus name-results status", "full"),
            row("PC-SUFFIX-RECOGNITION-20", "product_context", "Guard", "Numeric alias suffix must be nonempty evidence and every alphabetic token must be a recognized unit/form/route/release/package/filler token.", "unknown alphabetic token blocks alias rescue", "context_suffix_is_fully_recognized; CONTEXT_SUFFIX_FILLER_TOKENS", PC, "17.15", PRODUCT, "junk/unknown suffix tests", "Numbers/punctuation permitted", "full"),
            row("PC-NUMERIC-BRAND-ALIAS-21", "product_context", "Guard", "Use the globally longest prepared exact number+base alias before numeric-only aliases; stay exact-family-only and confirmation-required.", "explicit context=false; nonvisual; longest token key", "numeric_commercial_brand_alias_response", PC, "17.15", PRODUCT, "Near-alias/unknown-suffix/visual guards", "No remainder versus recognized remainder", "full"),
            row("PC-NUMERIC-ONLY-ALIAS-22", "product_context", "Guard", "Use the longest exact prefix of >=2 numeric tokens; admit all exact alias families before public cap; never fuzzy scan or index a single number.", ">=2 numeric tokens; exact lookup; deterministic cap", "numeric_commercial_alias_response", PC, "17.15", PRODUCT, "1 2 9 and single-number guards", "Overflow and remainder", "full"),
            row("PC-RETRIEVED-NUMERIC-PREFIX-23", "product_context", "Guard", "Fallback numeric commercial prefix matching examines only exact already-retrieved families and uses the same fully recognized suffix boundary.", "longest accepted alias", "context_after_numeric_commercial_brand_prefix", PC, "17.15", PRODUCT, "No-global/no-sibling guards", "One versus >=2 leading numbers", "full"),
            row("PC-ATTACHED-NUMBER-GUARD-24", "product_context", "Guard", "With no explicit context and only bare-number evidence, preserve an exact full name such as D3/A1/V2 instead of treating its number as strength.", "exact compact full name", "rerank_products", PC, "17.15", PRODUCT, "Attached-number brand cases", "Explicit context bypass", "full"),
            row("PC-SHORT-PREFIX-25", "product_context", "Guard", "For a one/two-character name, scan strict exact-family prefixes only when both numeric and structural evidence exist; disable in visual mode.", "name length1..2; exact families<=limit; product numeric+compatible form", "short_prefix_context_response", PC, "17.16", PRODUCT, "Too-broad/no-match/visual guards", "x + 500 tab; family count=limit", "full"),
            row("PC-PAYLOAD-26", "product_context", "Active", "Disclose parsed evidence, invalid state, candidate/compatible counts, reorder, family/product ranks, matches/conflicts/ties, aliases, visual identity, and stable product ID.", "Auditable response fields", "context_payload; product_result", PC, "17.17", API_TEST, "No-compatible-product display suppression", "Empty/present fields", "full"),
        ],
    )

    # API and UI boundaries.
    add_many(
        rules,
        [
            row("API-REQUEST-01", "api", "Guard", "Validate query 1..120 after stripping, optional product_context<=120, and limit 1..20 default20; all-whitespace query is HTTP422.", "query min1 max120; context max120; limit1..20", "SearchRequest; search", API, "2.1", API_TEST, "Invalid request scenarios", "Length/limit/whitespace", "partial", "Inventory captures main contract; not every length integer is executed."),
            row("API-LOCK-02", "api", "Guard", "Serialize search over the shared prepared in-memory catalog and reject a child runtime not identifying algorithm_6.", "SEARCH_LOCK", "SEARCH_LOCK; search", API, "2.1", API_TEST, "Algorithm identity checks", "Concurrent behavior", "partial", "No load/concurrency test."),
            row("API-CONTEXT-BOUNDARY-03", "api", "Active", "Pass query alone to Algorithm 6, then product_context to reranker; when explicit context is empty use query for legacy combined fallback and set explicit flag false.", "name_query=query; explicit_product_context=bool(product_context)", "search", API, "2; 24.7", API_TEST, "Explicit/legacy distinction", "Empty versus supplied context", "full"),
            row("API-RUNTIME-04", "api", "Guard", "Expose ready Algorithm 6 runtime identity, evaluation version, 25,066 medicines, actual family count, capabilities, initialization, and RSS.", "algorithm=algorithm_6; medicine_count=25066", "runtime", API, "2.2", API_TEST, "", "Exact counts", "full"),
            row("API-HEALTH-05", "api", "Guard", "Expose health status ok and algorithm_6 identity.", "GET /health", "health", API, "2.2", API_TEST, "", "", "full"),
            row("API-DISPLAY-ID-FIRST-06", "api", "Guard", "Hydrate display fields by selected_product_id first, then compact commercial, family, and exact visual matched family lookups.", "ID-first ordered fallback", "add_display_fields", API, "2.4", API_TEST, "Duplicate-name metadata guards", "Missing metadata", "full"),
            row("API-DISPLAY-CONFLICT-07", "api", "Guard", "Skip catalog hydration for no_compatible_product rows so conflicting details cannot look selected.", "empty/default product metadata", "add_display_fields", API, "2.4; 17.14", API_TEST, "All-conflict cases", "Name-only retained row", "full"),
            row("API-CONFIRM-08", "api", "Guard", "Set needs_clarification and confirmation_required true on every enriched result.", "always true", "add_display_fields", API, "2.4", API_TEST, "", "Exact and ambiguous rows", "full"),
            row("API-CORS-09", "api", "Guard", "Allow only documented GitHub Pages/local origins, GET/POST methods, and Content-Type header.", "3 origins; GET/POST; Content-Type", "app", API, "2.3", "", "", "", "gap", "No HTTP CORS matrix in current package."),
            row("API-STATIC-10", "api", "Active", "Serve root, JavaScript, stylesheet, and unfiltered app/data static mount.", "/; /app.js; /styles.css; /data", "index; javascript; stylesheet; app.mount", API, "2.3", API_TEST, "", "", "partial", "Static-file exposure is not deeply tested."),
            row("UI-INPUTS-01", "ui", "Provisional", "Require medicine name in UI; allow visual markers; keep product details optional; disable spellcheck/autocapitalization and use automatic direction.", "placeholder: 600, 500 mg, tablets, 24 pack", "medicineName; productContext", HTML, "18.1", JS_TEST, "", "Empty input", "partial", "DOM/browser visual acceptance remains outside JS unit tests."),
            row("UI-DEBOUNCE-02", "ui", "Active", "Debounce automatic search 420 ms and only auto-search at trimmed name length>=3; explicit submit may search shorter names.", "420ms; auto min length3", "handleSearchInput; search", UI, "18.2", JS_TEST, "", "Length2/3", "full"),
            row("UI-REQUEST-RACE-03", "ui", "Guard", "Abort superseded requests and use a monotonically increasing sequence to prevent stale rendering.", "AbortController + request sequence", "search", UI, "18.2", JS_TEST, "Stale response tests", "", "partial", "No live browser network race claim."),
            row("UI-CACHE-04", "ui", "Guard", "Cache at most 24 responses by runtime plus JSON tuple of trimmed raw name/context; preserve markers and evict oldest insertion; forced submit bypasses cache.", "max24; non-LRU Map insertion order", "requestCacheKey; cacheResponse; search", UI, "18.2", JS_TEST, "Marker collision guards", "24/25 entries", "full"),
            row("UI-API-REQUEST-05", "ui", "Guard", "Send separate query/product_context with limit20; require HTTP success and algorithm_6 response identity.", "limit=20", "search", UI, "18.2", JS_TEST, "Wrong-runtime/error cases", "", "full"),
            row("UI-FALLBACK-06", "ui", "Browser fallback only", "Select static browser search only for API probe HTTP404 or file protocol; concatenate name/context and use separate browser-only rules.", "runtime probe timeout3.5s; no fallback on other HTTP/network errors", "detectRuntime; loadCatalog; searchCatalog", UI, "2.5; 18.2", JS_TEST, "Unavailable/malformed API cases", "file/404 boundaries", "full"),
            row("UI-GROUPING-07", "ui", "Guard", "Group families by family_group_key and product ties first by stable selected_product_id, then key/name/base fallback.", "initial 10 groups; max6 product radio variants", "groupedResults; renderFamilyGroup", UI, "18.3", JS_TEST, "Duplicate-name product IDs", "10/show-more and 6 variants", "full"),
            row("UI-EVIDENCE-08", "ui", "Active", "Render recognized product-context evidence, conflict badge, tie count, warnings, routes/forms, and confirmation summaries with human-readable fallback labels.", "Unknown underscore label -> title text", "renderProductEvidence; renderBadges; renderSummary; humanWarning; humanRoute; humanForm", UI, "18.3; 19", JS_TEST, "Conflict and unknown-label cases", "Empty evidence", "full"),
            row("UI-ESCAPE-09", "ui", "Guard", "Escape interpolated catalog/query text before rendering HTML.", "All dynamic text through esc", "esc; renderSingleResult; renderFamilyGroup", UI, "18.3", JS_TEST, "Escaping tests", "", "partial", "No browser CSP/security audit."),
            row("UI-NO-RESULT-10", "ui", "Active", "When no rows are returned, suggest brand-only search, removing strength, or Arabic name.", "No-result guidance", "renderResults", UI, "18.3", JS_TEST, "", "Empty result", "partial", "DOM text not visually inspected by this registry."),
            row("UI-CLEAR-11", "ui", "Active", "Clearing medicine also clears context, aborts search, resets output, and focuses name; clearing context alone can schedule a new search; Escape activates the relevant clear action.", "Per-field clear semantics", "handleSearchInput; search", UI, "18.2", JS_TEST, "", "Medicine-clear versus context-clear", "partial", "Live focus/keyboard behavior is not visually accepted."),
            row("UI-LOADING-12", "ui", "Active", "While searching disable submit, set aria-busy, and show loading skeleton only when no result children already exist.", "Existing results remain visible", "setSearching", UI, "18.2", JS_TEST, "", "Empty/nonempty result container", "partial", "No rendered accessibility-tree inspection."),
            row("UI-RESULT-PAGING-13", "ui", "Active", "Initially render ten family groups and reveal more on demand; ranks shown are group ranks rather than raw row ranks.", "initial groups=10", "renderResults; renderFamilyGroup", UI, "18.3", JS_TEST, "", "10/11 groups", "partial", "No rendered show-more visual acceptance."),
            row("UI-CONFIRM-SAFETY-14", "ui", "Guard", "Keep warning and confirmation badges visible and tell the user to confirm every result; product choice radio changes local visual state only and sends no mutation.", "No auto-selection/server write", "renderBadges; renderFamilyGroup; renderSummary", UI, "18.3; 19", JS_TEST, "", "Single/tied products", "full"),
        ],
    )

    return sorted(rules, key=lambda item: item["rule_id"])


def validate_authority(rules: list[dict[str, str]]) -> None:
    text = RULEBOOK.read_text(encoding="utf-8")
    if "## 24. Current OCR/grapheme implementation appendix" not in text:
        raise RuntimeError("Rulebook Appendix 24 authority is missing")

    checks = {
        A5: (
            "GRAPHEME_VARIANT_LIMIT = 512",
            "MAX_GRAPHEME_VARIANT_INPUT_LENGTH = 24",
            "GRAPHEME_PREFIX_SURFACE_MAX_FAMILIES = 4",
            "LONG_PHONETIC_COLLAPSE_PAIRS = tuple(",
            "PHONETIC_ONE_EDIT_MAX_FAMILIES = 4",
            "PHONETIC_ONE_EDIT_SCORE_DISCOUNT = 3.75",
            "def phonetic_collapse_one_edit_family_evidence",
            "def surface_phonetic_collapse_one_edit_candidates",
            "def protect_exact_catalog_name",
        ),
        A6: (
            "MAX_VISUAL_GAP_FRAGMENTS = 4",
            "VISUAL_GAP_CONFUSION_PATTERN_LIMIT = 512",
            "def visual_grapheme_projection",
            "anchor_start=bool(compact_parts[0])",
            "re.fullmatch(r\"[A-Za-z]+(?:\\s+[A-Za-z]+){1,3}\", text)",
            "hidden_characters = max(0, len(target) - matched_visible_characters)",
            '"phonetic_collapse_one_edit_candidate"',
            '"phonetic_collapse_one_edit_retrieval"',
        ),
        PC: (
            "MAX_PLAUSIBLE_PACKAGE_COUNT = 400",
            "CONTEXT_FAMILY_ADMISSION_LIMIT = 3",
            "CONTEXT_FAMILY_MAX_RAW_EDIT_DISTANCE = 2.0",
            "CONTEXT_FAMILY_MIN_LEVENSHTEIN_SIMILARITY = 0.60",
        ),
        API: ('"medicine_count": 25_066', "explicit_product_context=bool(product_context)"),
        UI: ("if (responseCache.size >= 24)", "function requestCacheKey"),
    }
    for relative, needles in checks.items():
        source = (ROOT / relative).read_text(encoding="utf-8")
        for needle in needles:
            if needle not in source:
                raise RuntimeError(f"Authority marker missing in {relative}: {needle}")

    ids = [item["rule_id"] for item in rules]
    duplicates = sorted(key for key, count in Counter(ids).items() if count != 1)
    if duplicates:
        raise RuntimeError(f"Duplicate rule IDs: {duplicates}")
    for item in rules:
        if not re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)+", item["rule_id"]):
            raise RuntimeError(f"Invalid immutable rule ID: {item['rule_id']}")
        if item["status"] not in ALLOWED_STATUSES:
            raise RuntimeError(f"Invalid status for {item['rule_id']}: {item['status']}")
        if item["coverage_status"] not in ALLOWED_COVERAGE:
            raise RuntimeError(
                f"Invalid coverage for {item['rule_id']}: {item['coverage_status']}"
            )
        for source_file in (part.strip() for part in item["source_files"].split(";")):
            if source_file and not (ROOT / source_file).is_file():
                raise RuntimeError(f"Missing source for {item['rule_id']}: {source_file}")


def main() -> None:
    rules = build_registry()
    validate_authority(rules)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rules)

    manifest = {
        "schema_version": 1,
        "generator": str(Path(__file__).resolve().relative_to(ROOT)),
        "output": str(OUTPUT.relative_to(ROOT)),
        "row_count": len(rules),
        "csv_sha256": sha256(OUTPUT),
        "authority": {
            str(RULEBOOK.relative_to(ROOT)): sha256(RULEBOOK),
            A2: sha256(ROOT / A2),
            A5: sha256(ROOT / A5),
            A6: sha256(ROOT / A6),
            POLICY: sha256(ROOT / POLICY),
            PC: sha256(ROOT / PC),
            API: sha256(ROOT / API),
            UI: sha256(ROOT / UI),
        },
        "counts_by_subsystem": dict(sorted(Counter(r["subsystem"] for r in rules).items())),
        "counts_by_status": dict(sorted(Counter(r["status"] for r in rules).items())),
        "counts_by_coverage": dict(
            sorted(Counter(r["coverage_status"] for r in rules).items())
        ),
    }
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

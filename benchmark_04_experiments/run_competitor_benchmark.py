#!/usr/bin/env python3
"""Run distinct open-source retrieval competitors on both locked test sets."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import hnswlib
import jellyfish
import numpy as np
import scipy.sparse as sp
import torch
from rapidfuzz import fuzz, process
from rapidfuzz.distance import (
    DamerauLevenshtein,
    Jaro,
    LCSseq,
    Levenshtein,
    OSA,
)
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from symspellpy import SymSpell, Verbosity
from transformers import AutoModel, AutoTokenizer


BENCHMARK_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BENCHMARK_ROOT.parent
OCR_ROOT = PROJECT_ROOT / "benchmark_03_ocr"
LEGACY_ROOT = PROJECT_ROOT / "benchmark_01_legacy"
DEFAULT_OCR_CASES = OCR_ROOT / "artifacts/04_model_predictions/search_cases.csv"
DEFAULT_SYNTHETIC_CASES = (
    BENCHMARK_ROOT / "data/05_synthetic_clean_core/test_cases.csv"
)
DEFAULT_ARTIFACTS = BENCHMARK_ROOT / "artifacts/06_competitor_benchmark"
DEFAULT_RESULTS = BENCHMARK_ROOT / "results/06_competitor_benchmark"
NODE_RANKER_SCRIPT = BENCHMARK_ROOT / "node_competitor_ranker.mjs"
TOP_K = 20
CATALOG_HASH_VERSION = "egypt_family_catalog_v1"
EVALUATION_VERSION = "competitor_benchmark_v1"

for import_path in (BENCHMARK_ROOT, OCR_ROOT, LEGACY_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import evaluate_current_app_search as current_app
import run_synthetic_clean_core as synthetic_core


@dataclass(frozen=True)
class SearchCase:
    dataset: str
    case_id: str
    input: str
    input_compact: str
    expected_family_keys: tuple[str, ...]
    expected_family_name: str
    split: str
    category: str
    error_type: str
    operation_family: str
    edit_distance: int
    normalized_distance: float
    distance_band: str
    query_length_band: str
    shared_bigram_band: str


@dataclass(frozen=True)
class CatalogFamily:
    key: str
    name: str
    normalized: str
    frequency: int


@dataclass(frozen=True)
class Competitor:
    algorithm: str
    display_name: str
    family: str
    implementation: str
    source_url: str
    status: str
    reason: str
    component_group: str


EVALUATED_COMPETITORS = (
    Competitor(
        "rapidfuzz_ratio",
        "RapidFuzz ratio",
        "normalized edit similarity",
        "RapidFuzz fuzz.ratio",
        "https://github.com/rapidfuzz/RapidFuzz",
        "evaluated",
        "Distinct normalized Indel similarity.",
        "rapidfuzz",
    ),
    Competitor(
        "rapidfuzz_partial_ratio",
        "RapidFuzz partial ratio",
        "substring edit similarity",
        "RapidFuzz fuzz.partial_ratio",
        "https://github.com/rapidfuzz/RapidFuzz",
        "evaluated",
        "Tests visible fragments and partial names.",
        "rapidfuzz",
    ),
    Competitor(
        "rapidfuzz_token_sort",
        "RapidFuzz token-sort ratio",
        "token-aware edit similarity",
        "RapidFuzz fuzz.token_sort_ratio",
        "https://github.com/rapidfuzz/RapidFuzz",
        "evaluated",
        "Tests reordered multi-word names.",
        "rapidfuzz",
    ),
    Competitor(
        "rapidfuzz_token_set",
        "RapidFuzz token-set ratio",
        "token-aware edit similarity",
        "RapidFuzz fuzz.token_set_ratio",
        "https://github.com/rapidfuzz/RapidFuzz",
        "evaluated",
        "Tests partial token overlap in multi-word names.",
        "rapidfuzz",
    ),
    Competitor(
        "rapidfuzz_wratio",
        "RapidFuzz weighted ratio",
        "adaptive edit similarity",
        "RapidFuzz fuzz.WRatio",
        "https://github.com/rapidfuzz/RapidFuzz",
        "evaluated",
        "Adaptive combination of full, partial, and token scores.",
        "rapidfuzz",
    ),
    Competitor(
        "rapidfuzz_qratio",
        "RapidFuzz quick ratio",
        "normalized edit similarity",
        "RapidFuzz fuzz.QRatio",
        "https://github.com/rapidfuzz/RapidFuzz",
        "evaluated",
        "Included so equivalence with ratio can be measured rather than assumed.",
        "rapidfuzz",
    ),
    Competitor(
        "damerau_levenshtein",
        "Damerau-Levenshtein",
        "edit distance",
        "RapidFuzz full Damerau-Levenshtein",
        "https://github.com/rapidfuzz/RapidFuzz",
        "evaluated",
        "Allows insertion, deletion, replacement, and transposition.",
        "rapidfuzz",
    ),
    Competitor(
        "optimal_string_alignment",
        "Optimal string alignment",
        "edit distance",
        "RapidFuzz OSA",
        "https://github.com/rapidfuzz/RapidFuzz",
        "evaluated",
        "Restricted Damerau distance used by Algorithm 5 evidence.",
        "rapidfuzz",
    ),
    Competitor(
        "jaro_similarity",
        "Jaro similarity",
        "character similarity",
        "RapidFuzz Jaro",
        "https://github.com/rapidfuzz/RapidFuzz",
        "evaluated",
        "Separates Jaro from the already cached Jaro-Winkler baseline.",
        "rapidfuzz",
    ),
    Competitor(
        "lcs_sequence_similarity",
        "Longest-common-subsequence similarity",
        "ordered subsequence",
        "RapidFuzz LCSseq",
        "https://github.com/rapidfuzz/RapidFuzz",
        "evaluated",
        "Rewards characters retained in order.",
        "rapidfuzz",
    ),
    Competitor(
        "quickumls_jaccard_char3",
        "QuickUMLS-style 3-gram Jaccard",
        "q-gram set similarity",
        "Vectorized SimString/QuickUMLS Jaccard",
        "https://github.com/Georgetown-IR-Lab/QuickUMLS",
        "evaluated",
        "QuickUMLS exposes Jaccard over character n-grams.",
        "qgram",
    ),
    Competitor(
        "quickumls_dice_char3",
        "QuickUMLS-style 3-gram Dice",
        "q-gram set similarity",
        "Vectorized SimString/QuickUMLS Dice",
        "https://github.com/Georgetown-IR-Lab/QuickUMLS",
        "evaluated",
        "QuickUMLS exposes Dice over character n-grams.",
        "qgram",
    ),
    Competitor(
        "quickumls_cosine_char3",
        "QuickUMLS-style 3-gram cosine",
        "q-gram set similarity",
        "Vectorized SimString/QuickUMLS cosine",
        "https://github.com/Georgetown-IR-Lab/QuickUMLS",
        "evaluated",
        "QuickUMLS exposes cosine over character n-grams.",
        "qgram",
    ),
    Competitor(
        "quickumls_overlap_char3",
        "QuickUMLS-style 3-gram overlap",
        "q-gram set similarity",
        "Vectorized SimString/QuickUMLS overlap",
        "https://github.com/Georgetown-IR-Lab/QuickUMLS",
        "evaluated",
        "QuickUMLS exposes overlap coefficient over character n-grams.",
        "qgram",
    ),
    Competitor(
        "dice_char2",
        "Character-bigram Dice",
        "q-gram set similarity",
        "Vectorized Dice coefficient",
        "https://github.com/seamusabshere/fuzzy_match",
        "evaluated",
        "A shorter q-gram retains evidence under heavier corruption.",
        "qgram",
    ),
    Competitor(
        "bm25_okapi_char2",
        "BM25 Okapi over character bigrams",
        "sparse probabilistic retrieval",
        "Vectorized rank_bm25 formula",
        "https://github.com/dorianbrown/rank_bm25",
        "evaluated",
        "Tests BM25 with short character tokens.",
        "bm25",
    ),
    Competitor(
        "bm25_okapi_char3",
        "BM25 Okapi over character trigrams",
        "sparse probabilistic retrieval",
        "Vectorized rank_bm25 formula",
        "https://github.com/dorianbrown/rank_bm25",
        "evaluated",
        "Tests BM25 with more specific character tokens.",
        "bm25",
    ),
    Competitor(
        "bm25_l_char3",
        "BM25L over character trigrams",
        "sparse probabilistic retrieval",
        "Vectorized rank_bm25 BM25L formula",
        "https://github.com/dorianbrown/rank_bm25",
        "evaluated",
        "BM25L length-normalization variant.",
        "bm25",
    ),
    Competitor(
        "bm25_plus_char3",
        "BM25Plus over character trigrams",
        "sparse probabilistic retrieval",
        "Vectorized rank_bm25 BM25Plus formula",
        "https://github.com/dorianbrown/rank_bm25",
        "evaluated",
        "BM25Plus lower-bound variant.",
        "bm25",
    ),
    Competitor(
        "symspell_frequency_ed2",
        "SymSpell, distance 2, catalog frequency",
        "delete-index spelling correction",
        "symspellpy",
        "https://github.com/wolfgarbe/SymSpell",
        "evaluated",
        "Delete index with catalog occurrence frequency for ties.",
        "symspell",
    ),
    Competitor(
        "symspell_frequency_ed3",
        "SymSpell, distance 3, catalog frequency",
        "delete-index spelling correction",
        "symspellpy",
        "https://github.com/wolfgarbe/SymSpell",
        "evaluated",
        "Distance-radius sensitivity for the same index.",
        "symspell",
    ),
    Competitor(
        "symspell_uniform_ed3",
        "SymSpell, distance 3, uniform frequency",
        "delete-index spelling correction",
        "symspellpy",
        "https://github.com/wolfgarbe/SymSpell",
        "evaluated",
        "Ablates catalog frequency from SymSpell tie ordering.",
        "symspell",
    ),
    Competitor(
        "jellyfish_soundex",
        "Soundex plus edit ranking",
        "phonetic encoding",
        "Jellyfish Soundex and RapidFuzz distance",
        "https://github.com/jamesturk/jellyfish",
        "evaluated",
        "Classic first-letter-preserving phonetic code.",
        "phonetic",
    ),
    Competitor(
        "jellyfish_metaphone",
        "Metaphone plus edit ranking",
        "phonetic encoding",
        "Jellyfish Metaphone and RapidFuzz distance",
        "https://github.com/jamesturk/jellyfish",
        "evaluated",
        "English phonetic code designed beyond Soundex.",
        "phonetic",
    ),
    Competitor(
        "jellyfish_nysiis",
        "NYSIIS plus edit ranking",
        "phonetic encoding",
        "Jellyfish NYSIIS and RapidFuzz distance",
        "https://github.com/jamesturk/jellyfish",
        "evaluated",
        "Name-oriented phonetic normalization.",
        "phonetic",
    ),
    Competitor(
        "jellyfish_match_rating",
        "Match Rating Codex plus edit ranking",
        "phonetic encoding",
        "Jellyfish Match Rating Codex and RapidFuzz distance",
        "https://github.com/jamesturk/jellyfish",
        "evaluated",
        "Compact consonant-oriented phonetic code.",
        "phonetic",
    ),
    Competitor(
        "biomedbert_dense_hnsw",
        "BiomedBERT dense HNSW",
        "biomedical dense retrieval",
        "BiomedBERT CLS embeddings with hnswlib",
        "https://github.com/microsoft/BiomedNLP-BiomedBERT",
        "evaluated",
        "Base biomedical encoder before entity self-alignment.",
        "dense",
    ),
    Competitor(
        "sapbert_dense_hnsw",
        "SapBERT dense HNSW",
        "biomedical dense retrieval",
        "Official SapBERT CLS embeddings with hnswlib",
        "https://github.com/cambridgeltl/sapbert",
        "evaluated",
        "Off-the-shelf biomedical entity-linking encoder.",
        "dense",
    ),
    Competitor(
        "coderpp_dense_hnsw",
        "CODER++ dense HNSW",
        "biomedical dense retrieval",
        "Official CODER++ CLS embeddings with hnswlib",
        "https://github.com/GanjinZero/CODER",
        "evaluated",
        "Fine-grained medical term encoder with hard-negative training.",
        "dense",
    ),
    Competitor(
        "biosyn_hybrid_w25",
        "BioSyn-style hybrid, sparse weight 0.25",
        "sparse-dense hybrid",
        "SapBERT cosine plus character TF-IDF",
        "https://github.com/dmis-lab/BioSyn",
        "evaluated",
        "Low sparse-weight sensitivity point.",
        "hybrid",
    ),
    Competitor(
        "biosyn_hybrid_w50",
        "BioSyn-style hybrid, sparse weight 0.50",
        "sparse-dense hybrid",
        "SapBERT cosine plus character TF-IDF",
        "https://github.com/dmis-lab/BioSyn",
        "evaluated",
        "Equal sparse and dense contribution.",
        "hybrid",
    ),
    Competitor(
        "biosyn_hybrid_w75",
        "BioSyn-style hybrid, sparse weight 0.75",
        "sparse-dense hybrid",
        "SapBERT cosine plus character TF-IDF",
        "https://github.com/dmis-lab/BioSyn",
        "evaluated",
        "High sparse-weight sensitivity point.",
        "hybrid",
    ),
    Competitor(
        "xmen_sapbert_tfidf_rrf",
        "xMEN-style SapBERT plus TF-IDF RRF",
        "rank-fusion ensemble",
        "Reciprocal-rank fusion over SapBERT and character TF-IDF",
        "https://github.com/hpi-dhc/xmen",
        "evaluated",
        "Tests the dense and n-gram ensemble exposed by xMEN.",
        "hybrid",
    ),
    Competitor(
        "preon_default",
        "preon default drug normalizer",
        "staged drug-name normalization",
        "Exact preon cascade: exact, token, then normalized Levenshtein <= 0.20",
        "https://github.com/ermshaua/preon",
        "evaluated",
        "Directly relevant drug-name normalizer, evaluated with its published default threshold and tie behavior.",
        "preon",
    ),
    Competitor(
        "preon_without_token",
        "preon without token matching",
        "staged drug-name normalization",
        "preon exact and normalized-Levenshtein stages; token stage removed",
        "https://github.com/ermshaua/preon",
        "evaluated",
        "Component ablation measuring whether preon's exact-token stage changes retrieval.",
        "preon",
    ),
    Competitor(
        "preon_without_partial",
        "preon without partial edit matching",
        "staged drug-name normalization",
        "preon exact and token stages; normalized-Levenshtein stage removed",
        "https://github.com/ermshaua/preon",
        "evaluated",
        "Component ablation measuring the contribution of preon's partial edit stage.",
        "preon",
    ),
    Competitor(
        "fuse_default_bitap",
        "Fuse.js default Bitap",
        "client-side fuzzy search",
        "Fuse.js 7.5.0 default Bitap ranking",
        "https://github.com/krisk/Fuse",
        "evaluated",
        "Published default fuzzy ranking over the locked Egyptian family catalog.",
        "node_search",
    ),
    Competitor(
        "fuse_token_search",
        "Fuse.js token search",
        "token-aware client-side fuzzy search",
        "Fuse.js 7.5.0 token search with BM25-style IDF",
        "https://github.com/krisk/Fuse",
        "evaluated",
        "Measures the token-search mode separately from default Bitap ranking.",
        "node_search",
    ),
    Competitor(
        "flexsearch_tolerant_default",
        "FlexSearch tolerant default",
        "indexed fuzzy search",
        "FlexSearch 0.8.212 tolerant tokenizer",
        "https://github.com/nextapps-de/flexsearch",
        "evaluated",
        "Published tolerant tokenizer with the default encoder and suggestions.",
        "node_search",
    ),
    Competitor(
        "flexsearch_tolerant_advanced",
        "FlexSearch tolerant LatinAdvanced",
        "indexed fuzzy and phonetic search",
        "FlexSearch tolerant tokenizer with LatinAdvanced encoder",
        "https://github.com/nextapps-de/flexsearch",
        "evaluated",
        "Adds the published advanced Latin phonetic normalization to tolerant retrieval.",
        "node_search",
    ),
    Competitor(
        "flexsearch_tolerant_extra",
        "FlexSearch tolerant LatinExtra",
        "indexed aggressive phonetic search",
        "FlexSearch tolerant tokenizer with LatinExtra encoder",
        "https://github.com/nextapps-de/flexsearch",
        "evaluated",
        "Measures the more aggressive vowel-reducing Latin encoder.",
        "node_search",
    ),
    Competitor(
        "flexsearch_full_advanced",
        "FlexSearch full LatinAdvanced",
        "indexed substring and phonetic search",
        "FlexSearch full tokenizer with LatinAdvanced encoder",
        "https://github.com/nextapps-de/flexsearch",
        "evaluated",
        "Tests complete substring indexing with advanced Latin normalization.",
        "node_search",
    ),
)


INVENTORY_ONLY = (
    Competitor(
        "cached_exact_prefix",
        "Exact or prefix match",
        "lexical baseline",
        "Existing benchmark",
        "https://github.com/krisk/Fuse",
        "cached",
        "Existing exact/prefix result is reused; Fuse is also listed separately.",
        "cached",
    ),
    Competitor(
        "cached_levenshtein",
        "Exhaustive Levenshtein",
        "edit distance",
        "Existing benchmark",
        "https://github.com/rapidfuzz/RapidFuzz",
        "cached",
        "Existing row-level result is reused.",
        "cached",
    ),
    Competitor(
        "cached_jaro_winkler",
        "Jaro-Winkler",
        "character similarity",
        "Existing benchmark",
        "https://github.com/jamesturk/jellyfish",
        "cached",
        "Existing row-level result is reused.",
        "cached",
    ),
    Competitor(
        "cached_char3_tfidf",
        "Character 3-gram TF-IDF",
        "sparse character retrieval",
        "Existing benchmark",
        "https://github.com/allenai/scispacy",
        "cached",
        "Existing result represents the same scoring family used by scispaCy and PolyFuzz.",
        "cached",
    ),
    Competitor(
        "cached_rapidfuzz_token_ratio",
        "RapidFuzz token ratio",
        "token-aware edit similarity",
        "Existing benchmark",
        "https://github.com/rapidfuzz/RapidFuzz",
        "cached",
        "Existing row-level result is reused.",
        "cached",
    ),
    Competitor(
        "cached_custom_phonetic",
        "Egyptian medicine phonetic baseline",
        "phonetic encoding",
        "Existing benchmark",
        "https://github.com/microsoft/PhoneticMatching",
        "cached",
        "Existing domain phonetic result is reused; general phonetic codes are evaluated separately.",
        "cached",
    ),
    Competitor(
        "polyfuzz",
        "PolyFuzz",
        "matching framework",
        "Wrapper around TF-IDF, RapidFuzz, and embeddings",
        "https://github.com/MaartenGr/PolyFuzz",
        "duplicate",
        "Its distinct underlying methods are evaluated directly, avoiding duplicate scores under a wrapper name.",
        "inventory",
    ),
    Competitor(
        "scispacy_linker",
        "scispaCy entity linker",
        "biomedical entity linking",
        "Character 3-gram ANN",
        "https://github.com/allenai/scispacy",
        "duplicate",
        "Same character-trigram scoring family as the cached TF-IDF baseline; its UMLS/RxNorm catalog is not the Egyptian catalog.",
        "inventory",
    ),
    Competitor(
        "simstring",
        "SimString",
        "q-gram retrieval engine",
        "SimString",
        "https://github.com/chokkan/simstring",
        "represented",
        "QuickUMLS-style Dice, Jaccard, cosine, and overlap scores represent its distinct measures.",
        "inventory",
    ),
    Competitor(
        "textdistance",
        "textdistance",
        "distance library",
        "30+ metric wrapper",
        "https://github.com/life4/textdistance",
        "represented",
        "Distinct LCS, q-gram, edit, and phonetic families are evaluated through compiled implementations.",
        "inventory",
    ),
    Competitor(
        "py_stringmatching",
        "py_stringmatching",
        "record-linkage metric library",
        "Soft TF-IDF and Monge-Elkan",
        "https://github.com/anhaidgroup/py_stringmatching",
        "excluded",
        "Token-level Soft TF-IDF and Monge-Elkan collapse on compact one-token drug names and provide no scalable exact top-20 index for 66,257 queries.",
        "inventory",
    ),
    Competitor(
        "oger",
        "OGER biomedical entity recognizer",
        "dictionary biomedical entity recognition",
        "Exact and flexible term matching in biomedical text",
        "https://github.com/OntoGene/OGER",
        "excluded",
        "OGER detects dictionary terms in documents and assigns ontology concepts; it does not rank isolated OCR strings against the locked Egyptian catalog.",
        "inventory",
    ),
    Competitor(
        "openmed",
        "OpenMed pharmaceutical NER",
        "biomedical named-entity recognition",
        "Transformer extraction of medication spans from clinical text",
        "https://github.com/maziyarpanahi/openmed",
        "excluded",
        "The pharmaceutical model detects medication spans in prose but does not normalize one OCR string to a ranked Egyptian catalog family.",
        "inventory",
    ),
    Competitor(
        "microsoft_phonetic_matching",
        "Microsoft PhoneticMatching",
        "phoneme-distance retrieval",
        "Native Node/C++ package",
        "https://github.com/microsoft/PhoneticMatching",
        "excluded",
        "English pronunciation dependencies and an unmaintained native build make the result environment-dependent; four reproducible phonetic encoders plus the domain phonetic baseline are tested.",
        "inventory",
    ),
    Competitor(
        "krissbert",
        "KRISSBERT",
        "contextual biomedical entity linking",
        "Prototype retrieval from contextual mentions",
        "https://github.com/microsoft/KRISS",
        "excluded",
        "Requires contextual mention prototypes and UMLS entity descriptions; this benchmark supplies isolated OCR strings and an Egyptian commercial-name catalog.",
        "inventory",
    ),
    Competitor(
        "bern2",
        "BERN2",
        "biomedical NER and normalization",
        "Full text NER plus UMLS normalization",
        "https://github.com/dmis-lab/BERN2",
        "excluded",
        "Consumes biomedical prose and normalizes to UMLS, not isolated strings against the locked Egyptian catalog.",
        "inventory",
    ),
    Competitor(
        "dnorm",
        "DNorm",
        "trained biomedical entity normalization",
        "Pairwise learning-to-rank model for disease mentions",
        "https://www.ncbi.nlm.nih.gov/research/bionlp/Tools/dnorm/",
        "excluded",
        "Requires labeled disease-normalization training data and contextual mentions; neither transfers to isolated Egyptian commercial drug names without retraining.",
        "inventory",
    ),
    Competitor(
        "medxn",
        "MedXN",
        "clinical medication normalization",
        "Clinical-text extraction and RxNorm normalization",
        "https://github.com/clinicalnlplab/MedXN",
        "excluded",
        "Extracts medication mentions and attributes from clinical prose and targets RxNorm, while this benchmark starts from one isolated OCR name and uses a locked Egyptian catalog.",
        "inventory",
    ),
    Competitor(
        "arboel",
        "ArboEL",
        "trained biomedical entity linking",
        "Ontology-aware biencoder and graph clustering",
        "https://github.com/davidkartchner/biomedical-entity-linking",
        "excluded",
        "Requires ontology descriptions, contextual mentions, and supervised training; the locked benchmark supplies none of those inputs.",
        "inventory",
    ),
    Competitor(
        "biogenel",
        "BioGenEL",
        "generative biomedical entity linking",
        "Autoregressive entity-name generation",
        "https://github.com/davidkartchner/biomedical-entity-linking",
        "excluded",
        "Requires ontology-specific model training and constrained decoding; an off-the-shelf result would not target the Egyptian commercial-name catalog.",
        "inventory",
    ),
    Competitor(
        "rxnorm_approximate_match",
        "RxNorm approximate matching",
        "drug terminology normalization",
        "Token splitting, expansion, spelling correction, and partial matching",
        "https://lhncbc.nlm.nih.gov/RxNav/APIs/ApproxMatchAPIs.html",
        "excluded",
        "The service ranks RxNorm concepts rather than the locked Egyptian catalog, so its output labels are not scoreable against these targets.",
        "inventory",
    ),
    Competitor(
        "quickumls_umls",
        "QuickUMLS packaged linker",
        "UMLS concept linking",
        "QuickUMLS plus UMLS",
        "https://github.com/Georgetown-IR-Lab/QuickUMLS",
        "represented",
        "The four underlying similarities are run against the correct Egyptian catalog instead of substituting UMLS.",
        "inventory",
    ),
    Competitor(
        "elasticsearch_fuzzy",
        "Elasticsearch fuzzy query",
        "search service",
        "Lucene edit automata and BM25",
        "https://github.com/elastic/elasticsearch",
        "represented",
        "Its method-level components are covered by edit-distance and BM25 tests; service tuning is an infrastructure experiment, not a new scoring rule.",
        "inventory",
    ),
    Competitor(
        "typesense",
        "Typesense typo-tolerant search",
        "search service",
        "Typesense server",
        "https://github.com/typesense/typesense",
        "excluded",
        "Server ranking combines proprietary defaults and deployment settings; it is not a single reproducible algorithm ablation.",
        "inventory",
    ),
    Competitor(
        "meilisearch",
        "Meilisearch typo-tolerant search",
        "search service",
        "Meilisearch server",
        "https://github.com/meilisearch/meilisearch",
        "excluded",
        "Server ranking combines typo tolerance with configurable ranking rules; it is outside the method-level comparison.",
        "inventory",
    ),
    Competitor(
        "glinker",
        "GLiNKER",
        "zero-shot entity linking",
        "Candidate retrieval plus neural entity disambiguation",
        "https://github.com/Knowledgator/GLinker",
        "excluded",
        "Its published pipeline links contextual mentions through a configurable candidate store and neural disambiguator; the benchmark has isolated OCR strings, no entity descriptions, and no frozen candidate-generation contract that yields a comparable catalog-wide top 20.",
        "inventory",
    ),
    Competitor(
        "tantivy",
        "Tantivy",
        "full-text search engine library",
        "Lucene-style inverted index and ranking infrastructure",
        "https://github.com/quickwit-oss/tantivy",
        "represented",
        "Tantivy is an indexing engine rather than one medicine-ranking rule; its distinct scoreable retrieval components are represented by the measured BM25 and edit-distance configurations.",
        "inventory",
    ),
    Competitor(
        "fuzzy_match",
        "FuzzyMatch",
        "record matching framework",
        "Dice bigram similarity with Levenshtein tie-breaking",
        "https://github.com/seamusabshere/fuzzy_match",
        "represented",
        "Its two distinct ranking signals are measured directly as character-bigram Dice and exhaustive Levenshtein.",
        "inventory",
    ),
    Competitor(
        "abydos",
        "Abydos",
        "string-distance and phonetic library",
        "Large collection of edit, q-gram, and phonetic measures",
        "https://github.com/chrislit/abydos",
        "represented",
        "Its scoreable method families are covered by the measured edit-distance, q-gram, Jaro, and phonetic configurations; the library wrapper adds no independent ranking rule.",
        "inventory",
    ),
    Competitor(
        "dedupe",
        "Dedupe",
        "supervised entity resolution",
        "Learned blocking and pair classification from labeled records",
        "https://github.com/dedupeio/dedupe",
        "excluded",
        "It requires labeled match and non-match pairs plus structured record fields; this locked benchmark supplies one OCR string per query and forbids training on evaluation labels.",
        "inventory",
    ),
    Competitor(
        "blink",
        "BLINK",
        "contextual entity linking",
        "Biencoder candidate retrieval plus cross-encoder reranking",
        "https://github.com/facebookresearch/BLINK",
        "excluded",
        "It requires contextual mentions, entity descriptions, and task-specific model preparation; those inputs do not exist for the locked Egyptian commercial-name catalog.",
        "inventory",
    ),
    Competitor(
        "ukkonen",
        "Ukkonen bounded edit distance",
        "edit-distance optimization",
        "Ukkonen implementation",
        "https://github.com/sunesimonsen/ukkonen",
        "duplicate",
        "It computes the same Levenshtein ordering as the cached exhaustive baseline; only execution strategy changes.",
        "inventory",
    ),
    Competitor(
        "stringzilla",
        "StringZilla",
        "accelerated string library",
        "SIMD distance implementation",
        "https://github.com/ashvardanian/StringZilla",
        "duplicate",
        "Faster implementation of distance families already scored; it does not define a different medicine ranking.",
        "inventory",
    ),
)


ALL_COMPETITORS = EVALUATED_COMPETITORS + INVENTORY_ONLY
COMPETITOR_BY_NAME = {item.algorithm: item for item in EVALUATED_COMPETITORS}
RESULT_FIELDS = (
    "evaluation_version",
    "dataset",
    "case_id",
    "algorithm",
    "algorithm_name",
    "input",
    "input_compact",
    "expected_family_keys",
    "expected_family_name",
    "split",
    "category",
    "error_type",
    "operation_family",
    "edit_distance",
    "normalized_distance",
    "distance_band",
    "query_length_band",
    "shared_bigram_band",
    "first_relevant_rank",
    "hit_at_1",
    "hit_at_5",
    "hit_at_10",
    "hit_at_20",
    "reciprocal_rank_at_20",
    "no_result",
    "candidate_count",
    "latency_ms",
    "top_1",
    "top_20",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=("ocr", "synthetic", "both"), default="both")
    parser.add_argument("--algorithms", default="all")
    parser.add_argument("--ocr-cases", type=Path, default=DEFAULT_OCR_CASES)
    parser.add_argument("--synthetic-cases", type=Path, default=DEFAULT_SYNTHETIC_CASES)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--aggregate-only", action="store_true")
    parser.add_argument("--list", action="store_true")
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def compact(value: str) -> str:
    return current_app.compact_key(value)


def character_ngrams(value: str, size: int) -> set[str]:
    if len(value) < size:
        return set()
    return {value[index : index + size] for index in range(len(value) - size + 1)}


def query_length_band(length: int) -> str:
    if length <= 3:
        return "1_3_characters"
    if length <= 5:
        return "4_5_characters"
    if length <= 7:
        return "6_7_characters"
    if length <= 9:
        return "8_9_characters"
    return "10_plus_characters"


def shared_bigram_band(count: int) -> str:
    if count == 0:
        return "0_shared_bigrams"
    if count == 1:
        return "1_shared_bigram"
    if count <= 3:
        return "2_3_shared_bigrams"
    return "4_plus_shared_bigrams"


def load_ocr_cases(path: Path, limit: int) -> list[SearchCase]:
    rows = [row for row in read_csv(path) if row["accepted"] == "1" and row["scored_case"] == "1"]
    seen: set[tuple[str, str]] = set()
    cases: list[SearchCase] = []
    for row in rows:
        input_key = compact(row["input"])
        pair = (input_key, row["expected_family_key"])
        if pair in seen:
            continue
        seen.add(pair)
        expected_key = row["expected_family_key"].split(";")[0]
        shared = len(character_ngrams(input_key, 2) & character_ngrams(expected_key, 2))
        cases.append(
            SearchCase(
                dataset="ocr_464",
                case_id=row["case_id"],
                input=row["input"],
                input_compact=input_key,
                expected_family_keys=tuple(row["expected_family_key"].split(";")),
                expected_family_name=row["expected_family_name"],
                split=row["split"],
                category=row["analysis_cohort"],
                error_type=row["mistake_type"],
                operation_family=row["mistake_type"],
                edit_distance=int(float(row["edit_distance"])),
                normalized_distance=float(row["normalized_edit_distance"]),
                distance_band=row["distance_band"],
                query_length_band=query_length_band(len(input_key)),
                shared_bigram_band=shared_bigram_band(shared),
            )
        )
    if limit:
        cases = cases[:limit]
    if len(cases) != (limit or 464):
        raise ValueError(f"expected {limit or 464} OCR cases, found {len(cases)}")
    return cases


def load_synthetic_cases(path: Path, limit: int) -> list[SearchCase]:
    source = synthetic_core.load_cases(path, limit)
    cases = [
        SearchCase(
            dataset="synthetic_66257",
            case_id=str(row["case_id"]),
            input=str(row["input"]),
            input_compact=str(row["input_compact"]),
            expected_family_keys=tuple(str(row["expected_family_keys"]).split(";")),
            expected_family_name=str(row["expected"]),
            split=str(row["split"]),
            category=str(row["primary_category"]),
            error_type=str(row["primary_error_type"]),
            operation_family=str(row["operation_family"]),
            edit_distance=int(row["effective_levenshtein"]),
            normalized_distance=float(row["normalized_levenshtein"]),
            distance_band=str(row["distance_band"]),
            query_length_band=str(row["query_length_band"]),
            shared_bigram_band=str(row["shared_bigram_band"]),
        )
        for row in source
    ]
    if len(cases) != (limit or 66257):
        raise ValueError(f"expected {limit or 66257} synthetic cases, found {len(cases)}")
    return cases


def load_catalog() -> list[CatalogFamily]:
    records = current_app.prepare_records()
    names: dict[str, str] = {}
    frequencies: dict[str, int] = {}
    for record in records:
        name = str(record.get("b") or record.get("n") or "").strip()
        key = compact(name)
        if not key:
            continue
        names.setdefault(key, name)
        frequencies[key] = frequencies.get(key, 0) + 1
    families = [
        CatalogFamily(
            key=key,
            name=names[key],
            normalized=current_app.normalize_search(names[key]),
            frequency=frequencies[key],
        )
        for key in sorted(names, key=lambda value: (names[value].casefold(), value))
    ]
    if len(families) != 17476:
        raise ValueError(f"expected 17,476 catalog families, found {len(families)}")
    return families


def write_inventory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(asdict(ALL_COMPETITORS[0]))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(asdict(item) for item in ALL_COMPETITORS)


def hash_values(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(value.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def top_k_indices(
    scores: np.ndarray,
    *,
    higher_is_better: bool,
    positive_only: bool = False,
    k: int = TOP_K,
) -> np.ndarray:
    """Select deterministic top-k rows, using catalog index as the final tie key."""

    output = np.full((scores.shape[0], k), -1, dtype=np.int32)
    for row_index, row in enumerate(scores):
        valid = np.flatnonzero(np.isfinite(row))
        if positive_only:
            valid = valid[row[valid] > 0]
        if not len(valid):
            continue
        values = row[valid]
        if len(valid) > k:
            if higher_is_better:
                threshold = np.partition(values, len(values) - k)[len(values) - k]
                better = valid[values > threshold]
                tied = valid[values == threshold]
            else:
                threshold = np.partition(values, k - 1)[k - 1]
                better = valid[values < threshold]
                tied = valid[values == threshold]
            needed = k - len(better)
            selected = np.concatenate((better, np.sort(tied)[:needed]))
        else:
            selected = valid
        primary = -row[selected] if higher_is_better else row[selected]
        order = np.lexsort((selected, primary))
        ranked = selected[order][:k]
        output[row_index, : len(ranked)] = ranked
    return output


def rank_to_row(
    case: SearchCase,
    competitor: Competitor,
    indices: np.ndarray,
    families: Sequence[CatalogFamily],
    latency_ms: float,
) -> dict[str, Any]:
    valid = [int(index) for index in indices if int(index) >= 0]
    expected = set(case.expected_family_keys)
    relevant = [
        rank
        for rank, family_index in enumerate(valid, 1)
        if families[family_index].key in expected
    ]
    rank = relevant[0] if relevant else 999
    names = [families[index].name for index in valid]
    return {
        "evaluation_version": EVALUATION_VERSION,
        "dataset": case.dataset,
        "case_id": case.case_id,
        "algorithm": competitor.algorithm,
        "algorithm_name": competitor.display_name,
        "input": case.input,
        "input_compact": case.input_compact,
        "expected_family_keys": ";".join(case.expected_family_keys),
        "expected_family_name": case.expected_family_name,
        "split": case.split,
        "category": case.category,
        "error_type": case.error_type,
        "operation_family": case.operation_family,
        "edit_distance": case.edit_distance,
        "normalized_distance": round(case.normalized_distance, 8),
        "distance_band": case.distance_band,
        "query_length_band": case.query_length_band,
        "shared_bigram_band": case.shared_bigram_band,
        "first_relevant_rank": rank,
        "hit_at_1": int(rank <= 1),
        "hit_at_5": int(rank <= 5),
        "hit_at_10": int(rank <= 10),
        "hit_at_20": int(rank <= 20),
        "reciprocal_rank_at_20": round(1 / rank, 8) if rank <= 20 else 0.0,
        "no_result": int(not valid),
        "candidate_count": len(valid),
        "latency_ms": round(latency_ms, 6),
        "top_1": names[0] if names else "",
        "top_20": ";".join(names),
    }


def artifact_path(root: Path, dataset: str, algorithm: str) -> Path:
    return root / dataset / f"{algorithm}.csv.gz"


def count_gzip_rows(path: Path) -> int:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return sum(1 for _ in handle) - 1


def evaluate_batches(
    cases: Sequence[SearchCase],
    competitor: Competitor,
    families: Sequence[CatalogFamily],
    output_path: Path,
    rank_batch: Callable[[Sequence[SearchCase]], np.ndarray],
    *,
    batch_size: int,
    force: bool,
    preparation_ms: float = 0.0,
    extra_latency_ms: float = 0.0,
) -> None:
    metadata_path = output_path.with_suffix(".metadata.json")
    if output_path.exists() and not force and count_gzip_rows(output_path) == len(cases):
        print(f"[reuse] {cases[0].dataset}/{competitor.algorithm}", flush=True)
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    scoring_ms = 0.0
    wall_started = time.perf_counter()
    with gzip.open(temporary, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for start in range(0, len(cases), batch_size):
            batch = cases[start : start + batch_size]
            began = time.perf_counter()
            ranked = rank_batch(batch)
            elapsed_ms = (time.perf_counter() - began) * 1000
            scoring_ms += elapsed_ms
            if ranked.shape != (len(batch), TOP_K):
                raise ValueError(
                    f"{competitor.algorithm}: expected {(len(batch), TOP_K)}, got {ranked.shape}"
                )
            per_query_ms = elapsed_ms / len(batch) + extra_latency_ms
            writer.writerows(
                rank_to_row(case, competitor, indices, families, per_query_ms)
                for case, indices in zip(batch, ranked)
            )
        handle.flush()
    temporary.replace(output_path)
    metadata_path.write_text(
        json.dumps(
            {
                "evaluation_version": EVALUATION_VERSION,
                "dataset": cases[0].dataset,
                "algorithm": competitor.algorithm,
                "cases": len(cases),
                "preparation_ms": preparation_ms,
                "scoring_ms": scoring_ms,
                "extra_query_latency_ms": extra_latency_ms,
                "wall_ms": (time.perf_counter() - wall_started) * 1000,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"[done] {cases[0].dataset}/{competitor.algorithm}: {len(cases):,} rows", flush=True)


def prepare_rapidfuzz_ranker(
    families: Sequence[CatalogFamily],
    competitor: Competitor,
) -> Callable[[Sequence[SearchCase]], np.ndarray]:
    compact_choices = [family.key for family in families]
    normalized_choices = [family.normalized for family in families]
    specifications: dict[str, tuple[Callable[..., Any], bool, bool, bool]] = {
        "rapidfuzz_ratio": (fuzz.ratio, True, False, False),
        "rapidfuzz_partial_ratio": (fuzz.partial_ratio, True, False, False),
        "rapidfuzz_token_sort": (fuzz.token_sort_ratio, True, False, True),
        "rapidfuzz_token_set": (fuzz.token_set_ratio, True, False, True),
        "rapidfuzz_wratio": (fuzz.WRatio, True, False, True),
        "rapidfuzz_qratio": (fuzz.QRatio, True, False, False),
        "damerau_levenshtein": (DamerauLevenshtein.distance, False, False, False),
        "optimal_string_alignment": (OSA.distance, False, False, False),
        "jaro_similarity": (Jaro.similarity, True, False, False),
        "lcs_sequence_similarity": (LCSseq.normalized_similarity, True, False, False),
    }
    scorer, higher_is_better, positive_only, normalized = specifications[competitor.algorithm]
    choices = normalized_choices if normalized else compact_choices

    def rank_batch(batch: Sequence[SearchCase]) -> np.ndarray:
        queries = [
            current_app.normalize_search(case.input) if normalized else case.input_compact
            for case in batch
        ]
        matrix = process.cdist(
            queries,
            choices,
            scorer=scorer,
            workers=-1,
            dtype=np.float32,
        )
        return top_k_indices(
            matrix,
            higher_is_better=higher_is_better,
            positive_only=positive_only,
        )

    return rank_batch


class SparseCharacterIndex:
    """Shared character-count indexes for q-gram, BM25, TF-IDF, and hybrids."""

    def __init__(self, families: Sequence[CatalogFamily]) -> None:
        self.families = families
        self.count_indexes: dict[int, tuple[CountVectorizer, sp.csr_matrix]] = {}
        self.count_build_ms: dict[int, float] = {}
        self.tfidf_index: tuple[TfidfVectorizer, sp.csr_matrix] | None = None
        self.tfidf_build_ms = 0.0

    def counts(self, size: int) -> tuple[CountVectorizer, sp.csr_matrix]:
        cached = self.count_indexes.get(size)
        if cached is not None:
            return cached
        started = time.perf_counter()
        vectorizer = CountVectorizer(
            analyzer="char",
            ngram_range=(size, size),
            lowercase=False,
            dtype=np.float32,
        )
        matrix = vectorizer.fit_transform(
            [family.key for family in self.families]
        ).tocsr()
        self.count_indexes[size] = (vectorizer, matrix)
        self.count_build_ms[size] = (time.perf_counter() - started) * 1000
        return vectorizer, matrix

    def tfidf(self) -> tuple[TfidfVectorizer, sp.csr_matrix]:
        if self.tfidf_index is not None:
            return self.tfidf_index
        started = time.perf_counter()
        vectorizer = TfidfVectorizer(
            analyzer="char",
            ngram_range=(3, 3),
            lowercase=False,
            norm="l2",
            dtype=np.float32,
        )
        matrix = vectorizer.fit_transform(
            [family.key for family in self.families]
        ).tocsr()
        self.tfidf_index = (vectorizer, matrix)
        self.tfidf_build_ms = (time.perf_counter() - started) * 1000
        return self.tfidf_index


def prepare_qgram_ranker(
    sparse_index: SparseCharacterIndex,
    competitor: Competitor,
) -> Callable[[Sequence[SearchCase]], np.ndarray]:
    size = 2 if competitor.algorithm == "dice_char2" else 3
    vectorizer, counts = sparse_index.counts(size)
    binary_catalog = counts.copy()
    binary_catalog.data[:] = 1.0
    catalog_cardinality = np.asarray(binary_catalog.sum(axis=1)).ravel()
    metric = {
        "quickumls_jaccard_char3": "jaccard",
        "quickumls_dice_char3": "dice",
        "quickumls_cosine_char3": "cosine",
        "quickumls_overlap_char3": "overlap",
        "dice_char2": "dice",
    }[competitor.algorithm]

    def rank_batch(batch: Sequence[SearchCase]) -> np.ndarray:
        query = vectorizer.transform([case.input_compact for case in batch]).tocsr()
        query.data[:] = 1.0
        intersections = (query @ binary_catalog.T).toarray().astype(np.float32)
        query_cardinality = np.asarray(query.sum(axis=1)).ravel()
        if metric == "jaccard":
            denominator = (
                query_cardinality[:, None]
                + catalog_cardinality[None, :]
                - intersections
            )
        elif metric == "dice":
            denominator = query_cardinality[:, None] + catalog_cardinality[None, :]
            intersections *= 2.0
        elif metric == "cosine":
            denominator = np.sqrt(
                query_cardinality[:, None] * catalog_cardinality[None, :]
            )
        else:
            denominator = np.minimum(
                query_cardinality[:, None], catalog_cardinality[None, :]
            )
        scores = np.divide(
            intersections,
            denominator,
            out=np.zeros_like(intersections),
            where=denominator > 0,
        )
        return top_k_indices(scores, higher_is_better=True, positive_only=True)

    return rank_batch


def bm25_weight_matrix(
    counts: sp.csr_matrix,
    variant: str,
    *,
    k1: float = 1.5,
    b: float = 0.75,
    delta: float = 0.5,
    epsilon: float = 0.25,
) -> sp.csr_matrix:
    """Build sparse document-term weights matching rank_bm25 formulas."""

    matrix = counts.copy().astype(np.float32)
    document_lengths = np.asarray(matrix.sum(axis=1)).ravel()
    average_length = float(document_lengths.mean())
    document_frequency = np.asarray((matrix > 0).sum(axis=0)).ravel()
    corpus_size = matrix.shape[0]
    if variant == "okapi":
        idf = np.log(corpus_size - document_frequency + 0.5) - np.log(
            document_frequency + 0.5
        )
        average_idf = float(idf.mean())
        idf[idf < 0] = epsilon * average_idf
    elif variant == "l":
        idf = np.log(corpus_size + 1.0) - np.log(document_frequency + 0.5)
    elif variant == "plus":
        idf = np.log(corpus_size + 1.0) - np.log(document_frequency)
    else:
        raise ValueError(f"unknown BM25 variant: {variant}")

    for row_index in range(matrix.shape[0]):
        start, end = matrix.indptr[row_index : row_index + 2]
        if start == end:
            continue
        term_indexes = matrix.indices[start:end]
        frequency = matrix.data[start:end]
        length_normalizer = 1.0 - b + b * document_lengths[row_index] / average_length
        if variant == "okapi":
            weighted = (
                idf[term_indexes]
                * frequency
                * (k1 + 1.0)
                / (frequency + k1 * length_normalizer)
            )
        elif variant == "l":
            normalized_frequency = frequency / length_normalizer
            weighted = (
                idf[term_indexes]
                * (k1 + 1.0)
                * (normalized_frequency + delta)
                / (k1 + normalized_frequency + delta)
            )
        else:
            weighted = (
                idf[term_indexes]
                * frequency
                * (k1 + 1.0)
                / (k1 * length_normalizer + frequency)
            )
        matrix.data[start:end] = weighted.astype(np.float32)
    return matrix


def prepare_bm25_ranker(
    sparse_index: SparseCharacterIndex,
    competitor: Competitor,
) -> Callable[[Sequence[SearchCase]], np.ndarray]:
    size = 2 if competitor.algorithm.endswith("char2") else 3
    variant = (
        "l"
        if competitor.algorithm.startswith("bm25_l")
        else "plus"
        if competitor.algorithm.startswith("bm25_plus")
        else "okapi"
    )
    vectorizer, counts = sparse_index.counts(size)
    weighted_catalog = bm25_weight_matrix(counts, variant)

    def rank_batch(batch: Sequence[SearchCase]) -> np.ndarray:
        query = vectorizer.transform([case.input_compact for case in batch]).tocsr()
        scores = (query @ weighted_catalog.T).toarray().astype(np.float32)
        return top_k_indices(scores, higher_is_better=True, positive_only=True)

    return rank_batch


def prepare_symspell_ranker(
    families: Sequence[CatalogFamily],
    competitor: Competitor,
) -> Callable[[Sequence[SearchCase]], np.ndarray]:
    uniform = competitor.algorithm == "symspell_uniform_ed3"
    maximum_distance = 2 if competitor.algorithm.endswith("ed2") else 3
    symspell = SymSpell(
        max_dictionary_edit_distance=3,
        prefix_length=7,
        count_threshold=1,
    )
    family_by_key = {family.key: index for index, family in enumerate(families)}
    for family in families:
        symspell.create_dictionary_entry(
            family.key,
            1 if uniform else family.frequency,
        )

    def rank_batch(batch: Sequence[SearchCase]) -> np.ndarray:
        ranked = np.full((len(batch), TOP_K), -1, dtype=np.int32)
        for row_index, case in enumerate(batch):
            suggestions = symspell.lookup(
                case.input_compact,
                Verbosity.ALL,
                max_edit_distance=maximum_distance,
                include_unknown=False,
                transfer_casing=False,
            )
            candidate_indexes = [
                family_by_key[suggestion.term]
                for suggestion in suggestions
                if suggestion.term in family_by_key
            ][:TOP_K]
            ranked[row_index, : len(candidate_indexes)] = candidate_indexes
        return ranked

    return rank_batch


def prepare_phonetic_ranker(
    families: Sequence[CatalogFamily],
    competitor: Competitor,
) -> Callable[[Sequence[SearchCase]], np.ndarray]:
    encoder: Callable[[str], str] = {
        "jellyfish_soundex": jellyfish.soundex,
        "jellyfish_metaphone": jellyfish.metaphone,
        "jellyfish_nysiis": jellyfish.nysiis,
        "jellyfish_match_rating": jellyfish.match_rating_codex,
    }[competitor.algorithm]

    def encode(value: str) -> str:
        letters_only = "".join(
            character
            for character in current_app.normalize_search(value)
            if character.isalpha()
        )
        return encoder(letters_only) if letters_only else ""

    choices = [encode(family.normalized) or "" for family in families]

    def rank_batch(batch: Sequence[SearchCase]) -> np.ndarray:
        queries = [encode(case.input) or "" for case in batch]
        scores = process.cdist(
            queries,
            choices,
            scorer=Levenshtein.distance,
            workers=-1,
            dtype=np.float32,
        )
        for row_index, query in enumerate(queries):
            if not query:
                scores[row_index, :] = np.inf
        return top_k_indices(scores, higher_is_better=False)

    return rank_batch


def prepare_preon_ranker(
    families: Sequence[CatalogFamily],
    competitor: Competitor,
) -> Callable[[Sequence[SearchCase]], np.ndarray]:
    """Reproduce preon's default exact, token, then partial-match cascade."""

    use_token = competitor.algorithm != "preon_without_token"
    use_partial = competitor.algorithm != "preon_without_partial"
    choices = [family.key for family in families]
    lengths = np.asarray([len(choice) for choice in choices], dtype=np.float32)
    indexes_by_key: dict[str, list[int]] = {}
    for index, key in enumerate(choices):
        indexes_by_key.setdefault(key, []).append(index)

    def rank_batch(batch: Sequence[SearchCase]) -> np.ndarray:
        output = np.full((len(batch), TOP_K), -1, dtype=np.int32)
        unresolved_rows: list[int] = []
        unresolved_queries: list[str] = []
        for row_index, case in enumerate(batch):
            exact = indexes_by_key.get(case.input_compact, [])
            if exact:
                output[row_index, : min(TOP_K, len(exact))] = exact[:TOP_K]
                continue

            token_matches = (
                {
                    index
                    for token in current_app.normalize_search(case.input).split()
                    for index in indexes_by_key.get(compact(token), [])
                }
                if use_token
                else set()
            )
            if token_matches:
                ranked = sorted(token_matches, key=lambda index: choices[index])
                output[row_index, : min(TOP_K, len(ranked))] = ranked[:TOP_K]
                continue

            unresolved_rows.append(row_index)
            unresolved_queries.append(case.input_compact)

        if not unresolved_rows or not use_partial:
            return output

        raw_distances = process.cdist(
            unresolved_queries,
            choices,
            scorer=Levenshtein.distance,
            workers=-1,
            dtype=np.float32,
        )
        query_lengths = np.asarray(
            [len(query) for query in unresolved_queries],
            dtype=np.float32,
        )
        denominators = np.maximum(query_lengths[:, None], lengths[None, :])
        distances = np.divide(
            raw_distances,
            denominators,
            out=np.full_like(raw_distances, np.inf),
            where=denominators > 0,
        )
        distances = np.round(distances, 3)

        for local_row, output_row in enumerate(unresolved_rows):
            minimum = float(distances[local_row].min())
            if minimum > 0.20:
                continue
            tied = np.flatnonzero(distances[local_row] == minimum)
            ranked = sorted(tied.tolist(), key=lambda index: choices[index])
            output[output_row, : min(TOP_K, len(ranked))] = ranked[:TOP_K]
        return output

    return rank_batch


class NodeBatchRanker:
    """Keep one Node process and fuzzy index alive across query batches."""

    def __init__(
        self,
        families: Sequence[CatalogFamily],
        competitor: Competitor,
    ) -> None:
        catalog_file = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix="medicine-search-catalog-",
            encoding="utf-8",
            delete=False,
        )
        self.catalog_path = Path(catalog_file.name)
        json.dump(
            [
                {"id": index, "name": family.name}
                for index, family in enumerate(families)
            ],
            catalog_file,
            separators=(",", ":"),
        )
        catalog_file.close()
        self.process = subprocess.Popen(
            [
                "node",
                str(NODE_RANKER_SCRIPT),
                str(self.catalog_path),
                competitor.algorithm,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        if self.process.stdout is None:
            raise RuntimeError("Node competitor stdout pipe was not created")
        ready = self.process.stdout.readline().strip()
        if ready != "READY":
            error = (
                self.process.stderr.read()
                if self.process.stderr is not None
                else ""
            )
            self.close()
            raise RuntimeError(
                f"{competitor.algorithm}: Node ranker failed to start: "
                f"{ready or error}"
            )

    def rank_batch(self, batch: Sequence[SearchCase]) -> np.ndarray:
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("Node competitor process is not available")
        self.process.stdin.write(
            json.dumps(
                [case.input for case in batch],
                ensure_ascii=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        self.process.stdin.flush()
        response = self.process.stdout.readline()
        if not response:
            error = (
                self.process.stderr.read()
                if self.process.stderr is not None
                else ""
            )
            raise RuntimeError(f"Node competitor stopped unexpectedly: {error}")
        rankings = json.loads(response)
        if len(rankings) != len(batch):
            raise ValueError(
                f"Node competitor returned {len(rankings)} rows for "
                f"{len(batch)} queries"
            )
        output = np.full((len(batch), TOP_K), -1, dtype=np.int32)
        for row_index, ranking in enumerate(rankings):
            valid = [int(value) for value in ranking[:TOP_K]]
            output[row_index, : len(valid)] = valid
        return output

    def close(self) -> None:
        if getattr(self, "process", None) is not None:
            if self.process.stdin is not None:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=5)
        if getattr(self, "catalog_path", None) is not None:
            self.catalog_path.unlink(missing_ok=True)


DENSE_MODELS = {
    "biomedbert_dense_hnsw": "microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext",
    "sapbert_dense_hnsw": "cambridgeltl/SapBERT-from-PubMedBERT-fulltext",
    "coderpp_dense_hnsw": "GanjinZero/coder_eng_pp",
}
DENSE_MODEL_REVISIONS = {
    "microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext": (
        "e1354b7a3a09615f6aba48dfad4b7a613eef7062"
    ),
    "cambridgeltl/SapBERT-from-PubMedBERT-fulltext": (
        "090663c3ae57bf35ffe4d0d468a2a88d03051a4d"
    ),
    "GanjinZero/coder_eng_pp": "3cfddf7cb7bf2f59996b7cdfcb56a121c4d9db1f",
}


def safe_model_name(model_name: str) -> str:
    return model_name.replace("/", "__")


def encode_texts(
    model_name: str,
    texts: Sequence[str],
    cache_path: Path,
    *,
    batch_size: int = 1024,
) -> tuple[np.ndarray, float, float]:
    """Return normalized CLS embeddings, total encoding ms, and load ms."""

    metadata_path = cache_path.with_suffix(".json")
    expected_hash = hash_values(texts)
    revision = DENSE_MODEL_REVISIONS[model_name]
    if cache_path.exists() and metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            metadata.get("text_hash") == expected_hash
            and int(metadata.get("rows", 0)) == len(texts)
            and metadata.get("model_name") == model_name
            and metadata.get("model_revision") == revision
        ):
            return (
                np.load(cache_path, mmap_mode="r"),
                float(metadata["encoding_ms"]),
                float(metadata["model_load_ms"]),
            )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    load_started = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        revision=revision,
        local_files_only=True,
    )
    model = AutoModel.from_pretrained(
        model_name,
        revision=revision,
        local_files_only=True,
    )
    model.eval()
    torch.set_num_threads(min(10, max(1, torch.get_num_threads())))
    model_load_ms = (time.perf_counter() - load_started) * 1000

    batches: list[np.ndarray] = []
    encoding_started = time.perf_counter()
    with torch.inference_mode():
        for start in range(0, len(texts), batch_size):
            tokens = tokenizer(
                list(texts[start : start + batch_size]),
                padding=True,
                truncation=True,
                max_length=25,
                return_tensors="pt",
            )
            model_output = model(**tokens)
            hidden_state = (
                model_output.last_hidden_state
                if hasattr(model_output, "last_hidden_state")
                else model_output[0]
            )
            hidden = hidden_state[:, 0, :]
            vectors = hidden.detach().cpu().numpy().astype(np.float32)
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = np.divide(
                vectors,
                norms,
                out=np.zeros_like(vectors),
                where=norms > 0,
            )
            batches.append(vectors)
    encoding_ms = (time.perf_counter() - encoding_started) * 1000
    embeddings = np.concatenate(batches, axis=0)
    np.save(cache_path, embeddings)
    metadata_path.write_text(
        json.dumps(
            {
                "model_name": model_name,
                "model_revision": revision,
                "pooling": "CLS before pooler",
                "normalization": "L2",
                "rows": len(texts),
                "dimensions": int(embeddings.shape[1]),
                "text_hash": expected_hash,
                "model_load_ms": model_load_ms,
                "encoding_ms": encoding_ms,
                "milliseconds_per_text": encoding_ms / len(texts),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return embeddings, encoding_ms, model_load_ms


class DenseRetriever:
    def __init__(
        self,
        model_name: str,
        families: Sequence[CatalogFamily],
        cases: Sequence[SearchCase],
        cache_root: Path,
    ) -> None:
        self.model_name = model_name
        self.families = families
        self.cases = cases
        model_key = safe_model_name(model_name)
        catalog_texts = [family.normalized for family in families]
        query_texts = [current_app.normalize_search(case.input) for case in cases]
        self.catalog_embeddings, catalog_ms, model_load_ms = encode_texts(
            model_name,
            catalog_texts,
            cache_root / f"{model_key}__catalog.npy",
        )
        self.query_embeddings, query_ms, _ = encode_texts(
            model_name,
            query_texts,
            cache_root / f"{model_key}__{cases[0].dataset}.npy",
        )
        index_started = time.perf_counter()
        self.index = hnswlib.Index(
            space="cosine",
            dim=int(self.catalog_embeddings.shape[1]),
        )
        self.index.init_index(
            max_elements=len(families),
            ef_construction=400,
            M=32,
            random_seed=20260723,
        )
        self.index.add_items(
            np.asarray(self.catalog_embeddings),
            np.arange(len(families)),
            num_threads=10,
        )
        self.index.set_ef(500)
        self.index.set_num_threads(10)
        index_ms = (time.perf_counter() - index_started) * 1000
        self.preparation_ms = model_load_ms + catalog_ms + index_ms
        self.encoding_ms_per_query = query_ms / len(cases)
        self.position_by_case = {
            case.case_id: index for index, case in enumerate(cases)
        }

    def vectors_for(self, batch: Sequence[SearchCase]) -> np.ndarray:
        positions = [self.position_by_case[case.case_id] for case in batch]
        return np.asarray(self.query_embeddings[positions], dtype=np.float32)

    def rank_batch(
        self,
        batch: Sequence[SearchCase],
        *,
        k: int = TOP_K,
    ) -> tuple[np.ndarray, np.ndarray]:
        labels, distances = self.index.knn_query(self.vectors_for(batch), k=k)
        return labels.astype(np.int32), (1.0 - distances).astype(np.float32)


def prepare_dense_ranker(
    retriever: DenseRetriever,
) -> Callable[[Sequence[SearchCase]], np.ndarray]:
    def rank_batch(batch: Sequence[SearchCase]) -> np.ndarray:
        labels, _ = retriever.rank_batch(batch)
        return labels

    return rank_batch


class HybridRetriever:
    def __init__(
        self,
        sparse_index: SparseCharacterIndex,
        dense: DenseRetriever,
    ) -> None:
        self.vectorizer, self.catalog_tfidf = sparse_index.tfidf()
        self.dense = dense

    def candidate_data(
        self,
        batch: Sequence[SearchCase],
        *,
        candidate_k: int = 100,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        query_tfidf = self.vectorizer.transform(
            [case.input_compact for case in batch]
        ).tocsr()
        sparse_scores = (query_tfidf @ self.catalog_tfidf.T).toarray().astype(np.float32)
        sparse_top = top_k_indices(
            sparse_scores,
            higher_is_better=True,
            positive_only=True,
            k=candidate_k,
        )
        dense_top, _ = self.dense.rank_batch(batch, k=candidate_k)
        query_dense = self.dense.vectors_for(batch)
        return sparse_scores, sparse_top, dense_top, query_dense

    def rank_weighted(
        self,
        batch: Sequence[SearchCase],
        sparse_weight: float,
    ) -> np.ndarray:
        sparse_scores, sparse_top, dense_top, query_dense = self.candidate_data(batch)
        output = np.full((len(batch), TOP_K), -1, dtype=np.int32)
        catalog_dense = np.asarray(self.dense.catalog_embeddings)
        for row_index in range(len(batch)):
            union = np.unique(
                np.concatenate(
                    (
                        sparse_top[row_index][sparse_top[row_index] >= 0],
                        dense_top[row_index][dense_top[row_index] >= 0],
                    )
                )
            )
            if not len(union):
                continue
            dense_scores = catalog_dense[union] @ query_dense[row_index]
            combined = (
                sparse_weight * sparse_scores[row_index, union]
                + (1.0 - sparse_weight) * dense_scores
            )
            order = np.lexsort((union, -combined))
            ranked = union[order][:TOP_K]
            output[row_index, : len(ranked)] = ranked
        return output

    def rank_rrf(self, batch: Sequence[SearchCase], constant: int = 60) -> np.ndarray:
        _, sparse_top, dense_top, _ = self.candidate_data(batch)
        output = np.full((len(batch), TOP_K), -1, dtype=np.int32)
        for row_index in range(len(batch)):
            scores: dict[int, float] = {}
            for ranking in (sparse_top[row_index], dense_top[row_index]):
                for rank, family_index in enumerate(ranking, 1):
                    if family_index < 0:
                        continue
                    scores[int(family_index)] = scores.get(int(family_index), 0.0) + 1.0 / (
                        constant + rank
                    )
            ranked = sorted(scores, key=lambda index: (-scores[index], index))[:TOP_K]
            output[row_index, : len(ranked)] = ranked
        return output


def read_result_rows(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def grouped_result_rows(
    rows: Sequence[dict[str, str]],
    field: str,
) -> dict[str, list[dict[str, str]]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        groups.setdefault(row[field] or "unknown", []).append(row)
    return groups


def percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)
    return ordered[position]


def metric_row(
    rows: Sequence[dict[str, str]],
    dimension: str,
    group: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    count = len(rows)
    latencies = [float(row["latency_ms"]) for row in rows]
    failures = sum(1 - int(row["hit_at_20"]) for row in rows)
    return {
        "evaluation_version": EVALUATION_VERSION,
        "dataset": rows[0]["dataset"],
        "algorithm": rows[0]["algorithm"],
        "algorithm_name": rows[0]["algorithm_name"],
        "dimension": dimension,
        "group": group,
        "cases": count,
        "hit_at_1": sum(int(row["hit_at_1"]) for row in rows) / count,
        "hit_at_5": sum(int(row["hit_at_5"]) for row in rows) / count,
        "hit_at_10": sum(int(row["hit_at_10"]) for row in rows) / count,
        "hit_at_20": sum(int(row["hit_at_20"]) for row in rows) / count,
        "mrr_at_20": sum(float(row["reciprocal_rank_at_20"]) for row in rows) / count,
        "failure_count": failures,
        "failure_rate": failures / count,
        "no_result_rate": sum(int(row["no_result"]) for row in rows) / count,
        "mean_candidate_count": statistics.fmean(
            int(row["candidate_count"]) for row in rows
        ),
        "mean_latency_ms": statistics.fmean(latencies),
        "median_latency_ms": statistics.median(latencies),
        "p95_latency_ms": percentile(latencies, 0.95),
        "p99_latency_ms": percentile(latencies, 0.99),
        "preparation_ms": float(metadata.get("preparation_ms", 0.0)),
        "scoring_ms": float(metadata.get("scoring_ms", 0.0)),
        "wall_ms": float(metadata.get("wall_ms", 0.0)),
    }


def aggregate_result_file(path: Path) -> list[dict[str, Any]]:
    rows = read_result_rows(path)
    metadata_path = path.with_suffix(".metadata.json")
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.exists()
        else {}
    )
    output = [metric_row(rows, "overall", "all", metadata)]
    dimensions = (
        "split",
        "category",
        "error_type",
        "operation_family",
        "distance_band",
        "query_length_band",
        "shared_bigram_band",
    )
    for field in dimensions:
        for group, group_rows in sorted(grouped_result_rows(rows, field).items()):
            output.append(metric_row(group_rows, field, group, metadata))
    return output


def write_aggregate_metrics(artifacts_root: Path, results_root: Path) -> None:
    metrics: list[dict[str, Any]] = []
    expected_files = len(EVALUATED_COMPETITORS)
    for dataset in ("ocr_464", "synthetic_66257"):
        paths = sorted((artifacts_root / dataset).glob("*.csv.gz"))
        if len(paths) != expected_files:
            raise ValueError(
                f"{dataset}: expected {expected_files} competitor files, "
                f"found {len(paths)}"
            )
        for path in paths:
            metrics.extend(aggregate_result_file(path))
    if not metrics:
        raise ValueError("no competitor result files were available for aggregation")
    results_root.mkdir(parents=True, exist_ok=True)
    path = results_root / "competitor_metrics.csv"
    fields = list(dict.fromkeys(key for row in metrics for key in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(metrics)
    print(f"Wrote {len(metrics):,} aggregate metric rows to {path}", flush=True)


def requested_algorithms(value: str) -> list[str]:
    if value == "all":
        return [item.algorithm for item in EVALUATED_COMPETITORS]
    requested = [item.strip() for item in value.split(",") if item.strip()]
    unknown = sorted(set(requested) - set(COMPETITOR_BY_NAME))
    if unknown:
        raise ValueError(f"unknown competitors: {unknown}")
    return requested


def evaluate_one(
    cases: Sequence[SearchCase],
    competitor: Competitor,
    families: Sequence[CatalogFamily],
    sparse_index: SparseCharacterIndex,
    dense_cache: dict[tuple[str, str], DenseRetriever],
    args: argparse.Namespace,
) -> None:
    output = artifact_path(args.artifacts_dir, cases[0].dataset, competitor.algorithm)
    group = competitor.component_group
    preparation_started = time.perf_counter()
    extra_latency_ms = 0.0
    node_ranker: NodeBatchRanker | None = None

    if group == "rapidfuzz":
        ranker = prepare_rapidfuzz_ranker(families, competitor)
    elif group == "qgram":
        ranker = prepare_qgram_ranker(sparse_index, competitor)
    elif group == "bm25":
        ranker = prepare_bm25_ranker(sparse_index, competitor)
    elif group == "symspell":
        ranker = prepare_symspell_ranker(families, competitor)
    elif group == "phonetic":
        ranker = prepare_phonetic_ranker(families, competitor)
    elif group == "preon":
        ranker = prepare_preon_ranker(families, competitor)
    elif group == "node_search":
        node_ranker = NodeBatchRanker(families, competitor)
        ranker = node_ranker.rank_batch
    elif group == "dense":
        model_name = DENSE_MODELS[competitor.algorithm]
        key = (model_name, cases[0].dataset)
        dense = dense_cache.get(key)
        if dense is None:
            dense = DenseRetriever(
                model_name,
                families,
                cases,
                args.artifacts_dir / "embedding_cache",
            )
            dense_cache[key] = dense
        ranker = prepare_dense_ranker(dense)
        extra_latency_ms = dense.encoding_ms_per_query
    elif group == "hybrid":
        model_name = DENSE_MODELS["sapbert_dense_hnsw"]
        key = (model_name, cases[0].dataset)
        dense = dense_cache.get(key)
        if dense is None:
            dense = DenseRetriever(
                model_name,
                families,
                cases,
                args.artifacts_dir / "embedding_cache",
            )
            dense_cache[key] = dense
        hybrid = HybridRetriever(sparse_index, dense)
        if competitor.algorithm == "xmen_sapbert_tfidf_rrf":
            ranker = hybrid.rank_rrf
        else:
            weight = {
                "biosyn_hybrid_w25": 0.25,
                "biosyn_hybrid_w50": 0.50,
                "biosyn_hybrid_w75": 0.75,
            }[competitor.algorithm]

            def ranker(
                batch: Sequence[SearchCase],
                sparse_weight: float = weight,
            ) -> np.ndarray:
                return hybrid.rank_weighted(batch, sparse_weight)

        extra_latency_ms = dense.encoding_ms_per_query
    else:
        raise ValueError(f"unsupported competitor group: {group}")

    preparation_ms = (time.perf_counter() - preparation_started) * 1000
    if group in {"dense", "hybrid"}:
        preparation_ms = max(preparation_ms, dense.preparation_ms)
    try:
        evaluate_batches(
            cases,
            competitor,
            families,
            output,
            ranker,
            batch_size=args.batch_size,
            force=args.force,
            preparation_ms=preparation_ms,
            extra_latency_ms=extra_latency_ms,
        )
    finally:
        if node_ranker is not None:
            node_ranker.close()


def validate_inputs(
    cases_by_dataset: dict[str, list[SearchCase]],
    families: Sequence[CatalogFamily],
) -> None:
    catalog = {family.key for family in families}
    missing = sorted(
        {
            expected
            for cases in cases_by_dataset.values()
            for case in cases
            for expected in case.expected_family_keys
            if expected not in catalog
        }
    )
    if missing:
        raise ValueError(f"{len(missing)} expected family keys are absent from the catalog")
    for dataset, cases in cases_by_dataset.items():
        identifiers = [case.case_id for case in cases]
        pairs = [
            (case.input_compact, ";".join(case.expected_family_keys))
            for case in cases
        ]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"{dataset}: duplicate case identifiers")
        if len(pairs) != len(set(pairs)):
            raise ValueError(f"{dataset}: duplicate query-target pairs")


def main() -> None:
    args = parse_args()
    if args.list:
        for item in ALL_COMPETITORS:
            print(
                f"{item.algorithm:38} {item.status:11} "
                f"{item.family}: {item.reason}"
            )
        return
    if args.aggregate_only:
        write_inventory(args.results_dir / "competitor_inventory.csv")
        write_aggregate_metrics(args.artifacts_dir, args.results_dir)
        return

    selected = requested_algorithms(args.algorithms)
    cases_by_dataset: dict[str, list[SearchCase]] = {}
    if args.dataset in {"ocr", "both"}:
        cases_by_dataset["ocr_464"] = load_ocr_cases(args.ocr_cases, args.limit)
    if args.dataset in {"synthetic", "both"}:
        cases_by_dataset["synthetic_66257"] = load_synthetic_cases(
            args.synthetic_cases,
            args.limit,
        )
    families = load_catalog()
    validate_inputs(cases_by_dataset, families)
    write_inventory(args.results_dir / "competitor_inventory.csv")

    sparse_index = SparseCharacterIndex(families)
    dense_cache: dict[tuple[str, str], DenseRetriever] = {}
    for dataset, cases in cases_by_dataset.items():
        print(
            f"Dataset {dataset}: {len(cases):,} cases, "
            f"{len(families):,} catalog families",
            flush=True,
        )
        for position, algorithm in enumerate(selected, 1):
            print(
                f"[{position}/{len(selected)}] preparing {dataset}/{algorithm}",
                flush=True,
            )
            evaluate_one(
                cases,
                COMPETITOR_BY_NAME[algorithm],
                families,
                sparse_index,
                dense_cache,
                args,
            )
    if args.dataset == "both":
        write_aggregate_metrics(args.artifacts_dir, args.results_dir)
    else:
        print(
            "Skipped combined competitor_metrics.csv; run both datasets or "
            "use --aggregate-only after both artifact sets are complete.",
            flush=True,
        )


if __name__ == "__main__":
    main()

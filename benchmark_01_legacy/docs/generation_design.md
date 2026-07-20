# Commercial-Name Test Generation Algorithm Design

## Problem Statement

We need a reproducible way to generate commercial-name search stress tests for the Egyptian medicine catalog. The hard part is not producing typos; it is producing medically meaningful failures: ambiguous prefixes, visual confusions, phonetic confusions, strength/unit noise, manufacturer/context noise, and cases where a wrong confident result could harm a patient.

The previous non-main branch already had expanded CSV artifacts, but the nested repo's `main` branch contains only app/data/docs files and no generator. I inspected `main` read-only with `git ls-tree -r --name-only main`; the generator did not exist there. The new generator therefore lives only on the non-main `medicine-search-clean` branch.

## Architecture

Pipeline:

```text
data/canonical_candidates.csv
        |
        v
CatalogRecord dataclasses
        |
        v
CatalogIndex
  - compact-name index
  - prefix ambiguity index
  - suffix ambiguity index
  - ingredient-by-base index
        |
        v
category transforms
        |
        v
TestCase dataclasses
        |
        v
validator gates
  - schema
  - duplicate rows
  - known category scope
  - >= 60% HARD/EXTREME
        |
        v
CSV/JSON outputs + evaluator metrics
```

Implementation files:

| file | responsibility |
| --- | --- |
| `benchmark_01_legacy/generate_commercial_name_test_cases.py` | CLI entry point. Loads data, runs generation, validates, writes outputs. |
| `benchmark_01_legacy/test_case_generation/models.py` | Typed dataclasses and literal labels. Prevents raw dictionaries from driving domain logic. |
| `benchmark_01_legacy/test_case_generation/config.py` | Paths, thresholds, category targets, scopes, difficulty labels, danger labels, and transformation constants. |
| `benchmark_01_legacy/test_case_generation/normalization.py` | Search normalization, compact keys, Arabic digit/letter folding, and query formatting. |
| `benchmark_01_legacy/test_case_generation/catalog_io.py` | CSV loading, schema validation, seed loading, and catalog indexes. |
| `benchmark_01_legacy/test_case_generation/transforms.py` | Pure mutation functions for every generated category. No file I/O. |
| `benchmark_01_legacy/test_case_generation/generators.py` | Converts mutations into final `TestCase` rows with collision and difficulty/danger logic. |
| `benchmark_01_legacy/test_case_generation/splitters.py` | Category-to-scope routing: inside, outside, semi-outside. |
| `benchmark_01_legacy/test_case_generation/validators.py` | Distribution and integrity gates before outputs are written. |
| `benchmark_01_legacy/test_case_generation/test_generation_unit.py` | Unit tests for normalization, indexing, collision escalation, scoping, and validation. |

## Core Design Decisions

### Deterministic Rule-Based Generation

Chosen approach: deterministic, catalog-order, rule-based transformations.

Alternative considered: random typo injection.

Why deterministic is better here:

- Medical test failures must be reproducible.
- Category-level score changes must reflect algorithm/data changes, not a new random sample.
- Every generated row needs a clear note explaining why it exists.
- The generated categories match concrete user/OCR/search failure modes.

Evidence: generated outputs are stable from fixed source files and fixed config, and all final artifacts can be regenerated with:

```bash
PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 benchmark_01_legacy/generate_commercial_name_test_cases.py
```

### Hard-Biased Distribution

Chosen approach: a stress-test distribution with an explicit gate requiring at least 60% `HARD` or `EXTREME` cases.

Alternative considered: production-frequency distribution dominated by easy exact/near-exact inputs.

Why hard-biased is better here:

- There is no production query log in this repository that would justify a natural frequency distribution.
- The purpose is to expose weak categories, not to inflate Hit@1 with easy exact matches.
- Medical retrieval safety depends on hard cases: ambiguous prefixes, collisions, and context noise.

The regenerated suite has:

- Total cases: `341,901`.
- `HARD`: `253,178`.
- `EXTREME`: `28,734`.
- Hard/extreme ratio: `82.45%`.
- `EASY`: only `42` seed rows, not generated exact-match padding.

### Dataclasses Instead Of Raw Dicts

Chosen approach: `CatalogRecord`, `Mutation`, `TestCase`, `CategorySpec`, and `ValidationSummary` dataclasses.

Alternative considered: passing `dict[str, str]` rows directly from `csv.DictReader`.

Why dataclasses are better:

- They make field ownership explicit.
- They allow typed generator signatures.
- They centralize derived keys such as `base_group_compact`.
- They make invalid empty fields fail at load time instead of leaking into generated data.

### One Concern Per Module

The generator follows the module rules in the attached instructions:

- `config.py` owns constants and no algorithms.
- `models.py` owns dataclasses and imports nothing from project algorithm modules.
- `normalization.py` owns normalization only.
- `catalog_io.py` owns I/O and index construction only.
- `transforms.py` owns pure mutation logic only.
- `generators.py` owns orchestration only.
- `validators.py` owns validation and writing helpers only.

### Collision-Aware Danger Escalation

For generated rows with default `SAFE` danger, the generator checks whether the generated input compact key exactly matches another known base group. If the colliding base group has a different ingredient key, the row is escalated to `DANGEROUS`; if the ingredient key is the same or unknown, it is escalated to `CAUTION`.

Alternative considered: trust each category's static danger label.

Why collision-aware escalation is better:

- A keyboard typo can be safe for one name and dangerous for another.
- A visual confusion can create a real different drug name.
- Static labels would hide catalog-specific risk.

## Category Algorithms

| category | algorithm | primary risk tested |
| --- | --- | --- |
| `all_position_deletion_full_catalog` | Delete one compact-name character at every position. | Missing characters, especially distinguishing first/middle letters. |
| `keyboard_adjacent_expanded_catalog` | Replace letters with QWERTY neighboring keys. | Common keyboard slips that still look like drug names. |
| `vowel_substitution_full_catalog` | Replace vowels with other vowels. | Heard-spelling and transliteration variants. |
| `all_position_transposition_full_catalog` | Swap adjacent compact-name characters. | Typing-order errors. |
| `phonetic_substitution_full_catalog` | Apply B/P, F/V, D/T, G/K/Q/C, S/Z, PH/F substitutions. | Sound-equivalent spelling mistakes. |
| `strength_unit_noise_catalog` | Add or rewrite strength/unit text such as mg/mcg/ml/IU. | Dose and unit interpretation errors. |
| `initial_sound_confusion_full_catalog` | Replace the first character within sound groups. | Prefix-weighted ranking failures. |
| `single_vowel_deletion_full_catalog` | Delete one vowel at a time. | Missing-vowel memory/search errors. |
| `consonant_skeleton_expanded_catalog` | Remove all vowels from a compact name. | Skeleton search and heard spelling. |
| `form_word_noise_catalog` | Append dosage-form words based on route family. | Context handling outside pure brand matching. |
| `mobile_keypad_confusion_catalog` | Replace letters within T9 keypad groups. | Old mobile keypad/input errors. |
| `partial_prefix_ambiguity_catalog` | Use 2-4 character prefixes that match multiple families. | Ambiguous short queries that should ask for clarification. |
| `truncation_collision_expanded_catalog` | Use a real shorter family that prefixes a longer expected family. | Dangerous substring/prefix traps. |
| `separator_removal_full_catalog` | Remove spaces and separators from multi-token names. | Compact matching and tokenization. |
| `token_order_transposition_catalog` | Reverse or swap name tokens. | Users remembering words but not order. |
| `ingredient_name_query_catalog` | Use active ingredient/composition text as query. | Outside commercial-name-only retrieval. |
| `ocr_digit_letter_full_catalog` | Replace O/I/L/S/B/Z/G/A/E with 0/1/5/8/2/6/4/3. | OCR and screenshot errors. |
| `manufacturer_noise_catalog` | Prefix/suffix brand with manufacturer text. | Manufacturer context should not dominate brand ranking. |
| `space_insertion_inside_brand_catalog` | Insert spaces inside compact brand text. | Tokenization robustness. |
| `decimal_slash_strength_noise_catalog` | Remove decimals, use comma decimals, rewrite slash as “per”. | High-risk dose notation errors. |
| `visual_ligature_full_catalog` | Apply RN/M, CL/D, RI/N, LI/H, AL/D, W/UU, NN/M, IU/W. | Visual/OCR confusions. |
| `therapeutic_class_noise_catalog` | Append top therapeutic class. | Class terms as context, not product identity. |
| `route_word_noise_catalog` | Append route/body-site words. | Route context and ambiguity. |
| `status_marker_noise_catalog` | Append markers such as cancelled, N/A, hospital only. | Warning/status text handling. |
| `prefix_suffix_extra_noise_catalog` | Add generic words like drug, price, dose, uses. | Search-noise tolerance. |
| `keyboard_shift_whole_word_catalog` | Shift every typed key left or right. | Large-distance keyboard offset errors. |
| `symbol_synonym_catalog` | Rewrite &, +, %, /, * as words. | Symbol/word equivalence and semantic symbols. |
| `qualifier_synonym_noise_catalog` | Rewrite PLUS, EXTRA, XR, SR and add common qualifiers. | Clinically relevant qualifier noise. |
| `brand_ingredient_mixed_query_catalog` | Combine commercial family and ingredient tokens. | Mixed evidence retrieval. |
| `suffix_family_confusion_expanded_catalog` | Keep a shared suffix visible while degrading the prefix. | Drug-family suffix ambiguity. |
| `parenthetical_noise_catalog` | Add parenthetical company/package text. | Product/package decorations. |
| `duplicate_syllable_catalog` | Duplicate the first 2-3 compact characters. | Repeated typing/heard repetition. |
| `digraph_soundalike_catalog` | Apply CH/SH, TH/T, PH/F, CK/K, QU/KW, KS/X, TION/SHUN. | English digraph soundalikes. |
| `abbreviation_expansion_catalog` | Expand F.C., I.V., I.M., SR, XR, TAB, CAPS, AMP, INJ, INF, SUSP. | Catalog abbreviation variants. |
| `token_drop_expanded_catalog` | Drop first or last token from multi-token names. | Missing qualifier/token ambiguity. |

The original seed categories are preserved unchanged in `benchmark_01_legacy/data/seed_test_cases.csv` and included in the expanded suite.

## Validation Gates

The generator refuses to write outputs unless all checks pass:

- Non-empty case list.
- Non-empty `input` and `expected`.
- Difficulty in `EASY`, `MEDIUM`, `HARD`, `EXTREME`.
- Danger in `SAFE`, `CAUTION`, `DANGEROUS`.
- Every category has a known scope.
- No duplicate `(input, expected, error_type, category)` rows.
- Hard/extreme ratio is at least `0.60`.

## Known Limitations

- This is a stress-test distribution, not a production query distribution.
- The source catalog does not include real user query frequencies.
- Some generated categories are capped by available catalog structure; for example route-word and truncation-collision categories can emit fewer rows than their target if the catalog has fewer valid cases.
- Arabic dot and cross-script cases are currently preserved from the seed suite rather than expanded catalog-wide.
- The generator validates data integrity, but it does not certify clinical correctness of the source catalog.

## Reproduction Commands

```bash
PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 -m compileall benchmark_01_legacy
PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 -m unittest discover -s benchmark_01_legacy -p 'test_*.py'
PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 benchmark_01_legacy/generate_commercial_name_test_cases.py
PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 benchmark_01_legacy/evaluate_current_app_search.py
```


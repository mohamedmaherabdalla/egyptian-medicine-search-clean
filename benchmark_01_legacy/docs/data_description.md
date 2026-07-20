# Data Description

## Source And Provenance

The generator uses two local source files:

| source | role |
| --- | --- |
| `data/canonical_candidates.csv` | Canonical medicine catalog used by the static search app and evaluation generator. |
| `benchmark_01_legacy/data/seed_test_cases.csv` | Original manually curated commercial-name stress suite. It is kept as seed data and is not overwritten by the generator. |

The nested repository branch used for generation is `medicine-search-clean`, not `main`. The nested `main` branch was inspected read-only and does not contain a generation script or expanded CSV artifacts.

Catalog snapshot used by this run:

- Product rows: `25,066`.
- Unique commercial base groups: `17,492`.
- Minimum base compact length: `1`.
- Maximum base compact length: `58`.
- Mean base compact length: `10.64`.
- Rows with missing scientific composition: `2,308`.
- Rows flagged `needs_review=True`: `9,405`.

## Canonical Catalog Schema

The canonical catalog file is `data/canonical_candidates.csv`.

| column | type | meaning | generation use |
| --- | --- | --- | --- |
| `candidate_id` | string | Stable row identifier. | Stored in generated notes as source provenance. |
| `source_row_index` | integer-like string | Original source row index. | Not used directly by generator. |
| `commercial_name_en` | string | Original English product name. | Product-level noise, symbols, abbreviations, strengths. |
| `commercial_name_en_norm` | string | Search-normalized English product name. | Strength/unit and abbreviation transformations. |
| `commercial_name_en_compact` | string | Compact product key. | Collision checks where needed. |
| `commercial_name_ar` | string | Arabic alias field. | Not expanded in the new generator. Seed Arabic cases are preserved. |
| `commercial_name_ar_norm` | string | Normalized Arabic alias. | Loaded into `CatalogRecord` for future Arabic expansion. |
| `base_group_key` | string | Commercial family key after removing strength/form/package tokens. | Primary expected target for generated cases. |
| `strengths_join` | string | Extracted strength tokens. | Strength/unit noise. |
| `packages_join` | string | Extracted package-size tokens. | Currently documented but not used directly. |
| `detected_form_from_name` | string | Form parsed from product name. | Indirectly represented by `route_family`. |
| `route` | string | Original route/form bucket. | Used only through normalized route family. |
| `route_family` | string | Coarse app-facing route/form family. | Form and route noise generation. |
| `scientific_name` | string | Source composition/ingredient string. | Ingredient-only and brand+ingredient mixed query cases. |
| `ingredient_key` | string | Normalized ingredient/composition key. | Collision danger escalation. |
| `ingredient_count` | integer-like string | Number of ingredient components. | Not used directly in generation. |
| `manufacturer` | string | Full manufacturer text. | Context reference. |
| `manufacturer_primary` | string | Primary manufacturer segment. | Manufacturer-noise cases. |
| `manufacturer_parent` | string | Parent/distributor segment. | Not used directly. |
| `drug_class` | string | Original therapeutic class. | Context reference. |
| `drug_class_top` | string | Top-level therapeutic class. | Therapeutic-class noise. |
| `price_egp` | numeric-like string | Listed price in EGP. | Not used; price is not a correctness signal. |
| `needs_review` | boolean-like string | Data quality warning flag. | Used only for status/review noise. |
| `review_reasons` | string | Semicolon/bar-separated review reasons. | Status-marker noise. |

## Route Distribution

Top route families in the source catalog:

| route family | rows |
| --- | ---: |
| `oral_solid` | 10,589 |
| `topical` | 4,138 |
| `injection` | 2,634 |
| `unknown` | 2,597 |
| `oral_liquid` | 2,235 |
| `effervescent` | 1,037 |
| `spray` | 488 |
| `ophthalmic` | 473 |
| `vaginal` | 359 |
| `mouth` | 174 |
| `rectal` | 171 |
| `soap` | 130 |

## Drug-Class Distribution

Top therapeutic classes in the source catalog:

| class | rows |
| --- | ---: |
| `SKIN CARE` | 1,475 |
| `ANTIBIOTIC` | 1,191 |
| `HAIR CARE` | 928 |
| `MULTIVITAMIN` | 820 |
| `NSAID` | 719 |
| `ANTI-HYPERTENSIVE` | 662 |
| `PSYCHIATRIC` | 632 |
| `ANTI-DIABETIC` | 544 |
| `ANTI-EPILEPTIC` | 470 |
| empty class | 431 |
| `ANTINEOPLASTIC` | 418 |
| `PEPTIC ULCER` | 404 |

## Normalization Pipeline

The generator normalizes source text with the same broad assumptions used by the evaluator:

1. Convert Arabic digits `٠١٢٣٤٥٦٧٨٩` to ASCII `0123456789`.
2. Fold common Arabic letter variants: `آ/أ/إ/ٱ` to `ا`, `ى/ئ` to `ي`, `ؤ` to `و`, `ة` to `ه`.
3. Remove Arabic diacritics and tatweel.
4. Uppercase Latin text.
5. Replace non-search punctuation with spaces.
6. Collapse repeated spaces.
7. Build compact keys by removing all non-alphanumeric/search letters.

Why this matters: collision detection is performed on compact keys, while output `input` values preserve user-facing surface noise such as inserted spaces, symbols rewritten as words, and manufacturer/context terms.

## Generated Dataset Schema

All generated and split CSV files use this schema:

| column | type | meaning |
| --- | --- | --- |
| `input` | string | Noisy query submitted to the search engine. |
| `expected` | string | Expected commercial family or explicit ambiguous expected text from seed rows. |
| `error_type` | string | Specific transformation label. |
| `category` | string | Broad category used for metrics and documentation. |
| `difficulty` | enum | `EASY`, `MEDIUM`, `HARD`, or `EXTREME`. |
| `danger` | enum | `SAFE`, `CAUTION`, or `DANGEROUS`. |
| `collision_with` | string | Known colliding family names when applicable. |
| `notes` | string | Human-readable provenance, source id, and rationale. |

## Generated Files

| file | rows | meaning |
| --- | ---: | --- |
| `benchmark_01_legacy/data/seed_test_cases.csv` | 3,024 | Original seed suite, unchanged. |
| `benchmark_01_legacy/data/test_cases.csv` | 341,901 | Seed rows plus all generated rows. |
| `benchmark_01_legacy/data/test_cases_inside.csv` | 235,545 | Pure commercial-name spelling/search cases. |
| `benchmark_01_legacy/data/test_cases_semi_outside.csv` | 51,325 | Commercial-name text plus strength/unit, parenthetical, abbreviation, symbol, qualifier, or generic search noise. |
| `benchmark_01_legacy/data/test_cases_outside.csv` | 55,031 | Queries using extra catalog fields such as ingredient, manufacturer, therapeutic class, route/form, or status/warning text. |
| `benchmark_01_legacy/data/generation_summary.json` | 1 | Machine-readable counts and validation summary. |
| `benchmark_01_legacy/commercial_name_test_scope_summary.json` | 1 | Machine-readable scope summary. |

The split files sum to `341,901`, matching the expanded suite.

## Difficulty Distribution

| difficulty | rows |
| --- | ---: |
| `EASY` | 42 |
| `MEDIUM` | 59,947 |
| `HARD` | 253,178 |
| `EXTREME` | 28,734 |

Hard/extreme ratio: `82.45%`.

This intentionally exceeds the requested `60%` hard-case floor. The distribution is not meant to represent natural user traffic. It is a stress-test distribution designed to make weak categories visible. A production-frequency distribution should be built only when real anonymized query logs exist.

## Danger Distribution

| danger | rows |
| --- | ---: |
| `SAFE` | 235,092 |
| `CAUTION` | 91,546 |
| `DANGEROUS` | 15,263 |

Danger labels mean:

- `SAFE`: no known different-family compact collision was found, and the category is not inherently contextual or unit-sensitive.
- `CAUTION`: the query is broad, contextual, strength/unit-sensitive, or ambiguous enough that the UI should avoid a blind single answer.
- `DANGEROUS`: a known collision or truncation can point to a different medicine/family, often with a different ingredient key.

## Quality Issues And Controls

Known source issues:

- Some rows lack `scientific_name`; those rows cannot generate ingredient-only cases.
- Some route values are `unknown`; those rows cannot generate route-specific form words with high confidence.
- Some product names contain status markers or review issues; these are useful as status-noise cases but should be surfaced as warnings in UI.
- Arabic cases are under-expanded; current Arabic/cross-script categories come from the seed file.

Controls:

- Required columns are checked before loading.
- Empty commercial names/base groups fail during load.
- Duplicate generated rows fail validation.
- Unknown categories fail scope validation.
- Hard/extreme ratio below `60%` fails validation.
- Collision-aware danger escalation runs before final output.

## Reproduction

```bash
PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 benchmark_01_legacy/generate_commercial_name_test_cases.py
```

Then evaluate:

```bash
PYTHONPYCACHEPREFIX=/tmp/medicine_search_pycache python3 benchmark_01_legacy/evaluate_current_app_search.py
```


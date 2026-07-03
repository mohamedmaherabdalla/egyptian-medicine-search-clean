# Data Dictionary

The canonical catalog is stored at `data/canonical_candidates.csv`.

## Important Columns

| column | meaning |
| --- | --- |
| `candidate_id` | Stable row identifier used by the app and evaluation logic. |
| `commercial_name_en` | Original English product name. |
| `commercial_name_en_norm` | Search-normalized English product name. |
| `commercial_name_en_compact` | Compact English key with spaces and punctuation removed. |
| `commercial_name_ar` | Arabic alias field from the source catalog. |
| `commercial_name_ar_norm` | Normalized Arabic alias for search. |
| `base_group_key` | Brand/family key after removing strength, pack, and form tokens. |
| `strengths_join` | Extracted strength-like tokens from the product name. |
| `packages_join` | Extracted package-size tokens from the product name. |
| `detected_form_from_name` | Dosage/form hint parsed from the product name. |
| `route` | Original source route/form bucket. |
| `route_family` | App-facing route/form family. |
| `scientific_name` | Source scientific composition string. |
| `ingredient_key` | Normalized ingredient/composition key. |
| `ingredient_count` | Number of split ingredient components. |
| `manufacturer` | Original manufacturer string. |
| `manufacturer_primary` | First manufacturer segment before chain splitting. |
| `manufacturer_parent` | Parent or distributor segment after chain splitting. |
| `drug_class` | Original drug class text. |
| `drug_class_top` | Top-level drug class family. |
| `price_egp` | Listed price in Egyptian pounds. |
| `needs_review` | Boolean flag for rows with data-quality concerns. |
| `review_reasons` | Semicolon-separated warning reasons. |

## Intended Use

The catalog should be used as a structured retrieval layer. Product names, ingredients, routes, and warnings should be shown as evidence after retrieval. Price is useful context, but it should not be used as a clinical correctness signal.


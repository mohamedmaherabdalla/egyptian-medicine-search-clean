# Catalog Mapping Review Guide

`results/catalog_mapping_review_queue.csv` contains one row per unresolved unique
human label. Reviewers should inspect the original word image and Egyptian catalog,
not only the suggested string.

## Allowed Decisions

- `approve_commercial_family`: the label is the same commercial family used in
  Egypt. Fill `approved_family_key`.
- `ingredient_query`: the label is a generic ingredient, not one commercial brand.
- `regional_brand_only`: valid medicine outside Egypt with no Egyptian family.
- `non_medicine_text`: dosage, route, instruction, or other prescription text.
- `ambiguous`: evidence supports more than one family.
- `invalid_ground_truth`: the supplied transcription is demonstrably incorrect.
- `reject_unclear`: the image does not support a defensible decision.

## Review Rules

- Do not approve only because edit distance is one.
- Do not convert an ingredient to the most popular brand.
- Preserve family variants; do not collapse `EXTRA`, `FORTE`, or route/form variants
  when those visible characters are present.
- Record the reviewer and a short evidence note.
- A second reviewer should adjudicate all `ambiguous` decisions and a stratified
  sample of approvals.
- After review, regenerate mapping and benchmark artifacts from the decision file;
  do not hand-edit `search_cases.csv`.

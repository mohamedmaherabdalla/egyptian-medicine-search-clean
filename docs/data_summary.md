# Data Summary

The clean catalog contains 25,066 canonical medicine candidate rows.

## Main Strengths

- English product names are nearly unique.
- Arabic aliases are available for search support.
- Most rows include scientific composition.
- Route/form, manufacturer, drug class, and price are available in the same row.
- Derived family keys allow brand-level grouping.

## Known Data Issues

- Some rows are missing scientific composition.
- Some route values are unknown-like.
- Some product names contain status markers.
- Some Arabic aliases are generated search aliases rather than official names.
- Some rows have route/name mismatches.
- Some rows need review because at least one data-quality warning is present.

## Practical Meaning

The dataset is useful as a structured medicine lookup catalog, but it should not be treated as clinically complete without review. The product should always show evidence and warnings before a user confirms a medicine.


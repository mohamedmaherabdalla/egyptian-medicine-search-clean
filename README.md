# Egyptian Medicine Search

A static medicine lookup prototype for searching an Egyptian medicine catalog by product name, brand family, ingredient, strength, route/form hints, and noisy spelling.

The project is built around one rule: the app retrieves candidates and shows evidence. It should not silently choose one medicine when the query is weak, ambiguous, or missing route/strength details.

## What Is Included

- `app/`: the static browser demo.
- `app/data/catalog.json`: compressed browser search catalog with 25,066 medicine records.
- `data/canonical_candidates.csv`: readable canonical catalog with 25,066 rows.
- `search/`: English documentation of the search logic.
- `evaluation/evaluation_methodology.md`: the evaluation approach without exposing the evaluation datasets.
- `docs/`: project notes, data summary, backend explanation, limitations, and updates.

## What Is Not Included

- No raw evaluation case CSVs.
- No per-case evaluation results.
- No metric output tables.
- No scripts.
- No presentation files.
- No temporary experiment outputs.

## Run Locally

Open `app/index.html` in a browser, or serve the `app/` directory with any static file server.

Example:

```bash
python3 -m http.server 8010 --directory app
```

Then open:

```text
http://127.0.0.1:8010
```

## Data Summary

- Catalog rows: 25,066
- Main product field: `commercial_name_en`
- Search support fields: normalized English name, compact name, brand/base family, ingredient key, route family, strength tokens, Arabic alias, manufacturer, drug class, price, and review warnings.

## Search Behavior

The search is evidence-based:

1. Normalize the user query.
2. Generate possible matches from names, compact keys, family names, ingredients, route/form hints, and fuzzy signals.
3. Rank candidates with additive scoring.
4. Apply penalties and warnings for risky records.
5. Mark ambiguous results as requiring confirmation.

## Safety Position

This is a lookup and retrieval prototype, not a clinical decision system. The expected product behavior is:

```text
retrieve candidates -> show evidence -> show warnings -> user confirms
```


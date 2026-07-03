# Algorithm Explanation

The search system is a deterministic retrieval pipeline.

## Pipeline

1. Load the compressed medicine catalog.
2. Prepare searchable keys for each candidate.
3. Normalize the user query.
4. Extract route, form, strength, and token hints.
5. Score every candidate with multiple evidence signals.
6. Sort candidates by score.
7. Mark weak or ambiguous results as requiring clarification.
8. Show product evidence and warnings.

## Why It Is Fast Enough

The live app uses a static JSON catalog of 25,066 records. That size is small enough for browser-side search after the catalog is compressed and pre-normalized. The app avoids server calls, database latency, and authentication overhead.

The current static version performs direct scoring in the browser. For this dataset size, that is acceptable for a prototype. For a larger catalog, the next step would be prebuilt indexes for exact keys, prefixes, family names, ingredient keys, and typo candidates.

## Core Design Choice

The app ranks candidates, not final medical answers. This matters because many brand families contain multiple strengths, forms, and routes. The correct behavior is often to show a candidate set and ask the user to confirm the exact product.


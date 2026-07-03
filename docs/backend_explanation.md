# Backend Explanation

The current public demo is a static frontend. There is no live backend service in the deployed app.

## Static Architecture

```text
browser -> app.js -> app/data/catalog.json -> ranked results
```

## Why Static Deployment Works

- The catalog is small enough to load in the browser.
- Search logic is deterministic JavaScript.
- No user data needs to be stored.
- No server is needed for the demo.
- It can be hosted on static hosting such as GitHub Pages.

## Data Loading

The app loads `app/data/catalog.json`, which contains compact field names to reduce payload size. During startup, JavaScript expands and prepares searchable values in memory.

## Search Runtime

At query time, the browser:

1. normalizes the query
2. extracts query hints
3. scores catalog records
4. sorts the best results
5. renders candidate cards with evidence

## Future Backend Option

If the catalog grows much larger or needs secure audit logging, the same retrieval logic can move behind an API. A backend version should expose only a search endpoint and keep the catalog/indexes server-side.


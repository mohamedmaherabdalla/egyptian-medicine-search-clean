# Algorithm 6 Complete Rulebook

This document inventories the rules that affect the Python Algorithm 6 medicine-name search, its inherited Algorithm 5 and Algorithm 2 behavior, explicit visual-gap search, the optional product-context reranker, the API boundary, and the deployed UI. It is intended to be the review checklist and source map for anyone proposing a new OCR, spelling, strength, form, route, package, or safety rule.

The implementation remains the source of truth. If this document and source disagree, stop, record the discrepancy, and update both the tests and this document in the same change.

## 1. Snapshot status and authority

### 1.1 Committed endpoint

The last committed endpoint inspected for this rulebook is:

- Checked-out state: detached `HEAD` at `66abb7f`
- Remote-tracking endpoint: `origin/feature/algorithm-6-api` at the same `66abb7f` (`feat(search): expose visual gaps at every boundary`)
- Local `feature/algorithm-6-api` ref: still at `703c262`
- Previous exact-strength family-reranking commit: `703c262`
- Catalog: 25,066 product rows and exactly 17,476 deduplicated medicine families
- Evaluation version returned by the API: `algorithm_6_consensus_v1`

### 1.2 Current working tree -- provisional, not yet a deployment claim

At the time this document was created, the working tree also contained uncommitted changes in:

- `.dockerignore`
- `README.md`
- `app/product_context_reranker.py`
- `app/test_product_context_reranker.py`
- `app/api.py`
- `app/app.js`
- `app/index.html`
- `app/test_app.js`
- `benchmark_01_legacy/master_algorithms/algorithm_5_commercial_name_search.py`
- `benchmark_01_legacy/master_algorithms/algorithm_6_consensus_search.py`
- `benchmark_04_experiments/test_algorithm_6_visual_gaps.py`
- new test file `app/test_product_context_hardening.py`
- new test file `benchmark_04_experiments/test_algorithm_6_ocr_confusions.py`
- new live-server acceptance file `benchmark_04_experiments/test_algorithm_6_api_hardening.py`
- new locked fair-OCR comparator `benchmark_04_experiments/evaluate_algorithm_6_ocr_fair.py`
- new evaluator `benchmark_04_experiments/evaluate_algorithm_6_product_context.py`

Those changes add or revise unitless-number interpretation, complete combination-strength comparison, shared denominators, structural ratios, invalid-zero handling, semicolon metadata/presentation recovery, route/release/container distinctions, package conjunction/multipack handling, stable selected-product IDs, qualified presentation quantities, strict exact-base-family admission, strict form compatibility, explicit package words, one/two-character prefix recovery with product context, exact numeric-only and numeric-brand commercial-alias rescue, context-conflict responses, tied-product display, bounded directional grapheme confusions, bounded corrected-prefix surfacing, clean-set safety guards, exact visual-family identity, precomputed OCR-aware visual-gap patterns, exact-name protection, marker-preserving UI caching, and related UI labels. They are documented in Sections 17 and 24 as **current-source provisional rules**.

The exact local-source verification is recorded in Sections 20 and 24. It must not be described as **deployed** until it is reviewed, committed, pushed, and the actual public endpoint is verified at that immutable commit. Every numbered local port cited below is candidate evidence only.

### 1.3 Rule status vocabulary

Every rule in this document has one of these meanings:

| Status | Meaning |
| --- | --- |
| Active | The rule affects candidate generation, score, order, filtering, or response behavior in the relevant runtime path. |
| Guard | The rule prevents a broader active rule from changing a result without enough evidence. |
| Diagnostic | The value is calculated or returned but does not affect the current order. |
| Disabled | The implementation exists but a configuration flag prevents it from running. |
| Inherited | The rule comes from Algorithm 2 or Algorithm 5 and therefore affects Algorithm 6 indirectly. |
| Provisional | Present in the current uncommitted working tree; not yet a verified deployment claim. |
| Browser fallback only | Used by the static JavaScript fallback, not by the Python Algorithm 6 API. |

## 2. Runtime architecture and data boundary

The server-hosted request path is:

```text
browser form
  -> POST /api/search
  -> Algorithm 6 medicine-family search(query only)
       -> Algorithm 5
            -> inherited Algorithm 2
            -> context-clean Algorithm 2 pass when eligible
            -> family rescue indexes and bounded corrections
       -> nine additional consensus retrievers
       -> visual-gap path when explicitly requested
  -> product-context reranker(product_context, or legacy combined query fallback)
  -> display-field enrichment
  -> confirmation-required UI
```

The separation is intentional:

- `query` supplies visible medicine-name evidence.
- `product_context` supplies strength, number, form, route, release, presentation, and package evidence.
- Algorithm 6 normally receives only `query`.
- The product reranker runs after family retrieval.
- Context normally filters/reorders only exact base families already retrieved by the name search. The provisional strict one/two-character prefix path and prepared exact numeric-only/numeric-brand commercial-alias paths in Section 17 are the only candidate-generation exceptions. Broad Algorithm 6 variant groups remain display metadata and never authorize scoring an unretrieved sibling base.
- When `product_context` is empty, the API passes `query` to the product reranker for legacy compatibility and sets `explicit_product_context=false`; when it is nonempty, it sets that flag true. Both paths also pass `name_query=query`.

### 2.1 API request constraints

`SearchRequest` in `app/api.py` enforces:

| Field | Rule |
| --- | --- |
| `query` | String, minimum length 1, maximum length 120; whitespace is stripped and an all-whitespace value returns HTTP 422. |
| `product_context` | String, default empty, maximum length 120; whitespace is stripped. |
| `limit` | Integer 1 through 20, default 20. |

`SEARCH_LOCK` serializes the Python search because the prepared in-memory catalog/index is shared. The server rejects output whose runtime identifier is not `algorithm_6`.

### 2.2 API runtime invariants

`GET /api/runtime` reports:

- `ready: true`
- `algorithm: algorithm_6`
- evaluation version from policy
- `medicine_count: 25066`
- actual family count
- capabilities `ordinary_search`, `visual_gaps`, and `product_context_reranking`
- initialization time and process RSS memory

`GET /health` reports `status: ok` and `algorithm: algorithm_6`.

The application is designed for one API worker. The documented startup footprint is approximately 1.9--2.1 GB RSS; deployment guidance requires at least 2.5 GB available memory. The supplied Oracle deployment uses a 3 GB container cap and health check.

Deployment invariants from `README.md` and `deploy/oracle-cloud.sh`:

- local/API container entrypoint remains one worker and maps host port 8000 to container port 7860 in the documented direct Docker example;
- Oracle defaults: image `egyptian-medicine-algorithm-6`, container `medicine-search-a6`, public port 80, memory limit 3 GB, CPU limit 2, restart policy `unless-stopped`, container `PORT=7860`;
- an existing named container is force-replaced by the deploy script;
- readiness is polled every five seconds for 24 attempts (120 seconds) through `/health`, then `/api/runtime` is printed; timeout prints container logs and exits nonzero;
- recommended Oracle host is an Ampere A1 Flex Ubuntu VM with 2 OCPUs, 6 GB RAM, and 50 GB boot volume;
- the README requires HTTPS via domain/reverse proxy before accepting sensitive or identifiable input.

Container invariants from `Dockerfile`:

- base image `python:3.11-slim`; non-root UID 1000 user `medicine`; working directory `/home/medicine/service`;
- `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`, `PORT=7860`, single-thread OpenMP/OpenBLAS/MKL, and `MALLOC_ARENA_MAX=2`;
- only the app, shared normalizer, Algorithm 2, Algorithm 5, Algorithm 6, and Algorithm 6 policy are copied into the runtime image;
- Docker health check interval 30 seconds, timeout 5 seconds, start period 90 seconds, three retries, with an internal three-second `/health` request;
- `uvicorn app.api:app`, host `0.0.0.0`, configured port, exactly one worker.

`app/requirements-api.txt` pins FastAPI 0.141.1, Uvicorn 0.52.1, psutil 7.2.2, jellyfish 1.2.1, NumPy 2.3.5, RapidFuzz 3.14.5, scikit-learn 1.9.0, SciPy 1.17.1, and symspellpy 6.9.0. A dependency change is a runtime/evaluation change even when the Python source is unchanged.

### 2.3 CORS and static routes

Allowed CORS origins are:

- `https://mohamedmaherabdalla.github.io`
- `http://127.0.0.1:8000`
- `http://localhost:8000`

Allowed methods are GET and POST. The only explicitly allowed request header is `Content-Type`. The API also serves `/`, `/app.js`, `/styles.css`, and `/data`.

`/data` is a static mount of `app/data`; it is not filtered through the search API. Treat catalog-file exposure as a deployment boundary, not as a ranking rule.

### 2.4 API display enrichment

`add_display_fields()` copies the result and resolves display metadata in this order:

1. exact `selected_product_id` in the catalog-ID lookup;
2. exact compact `commercial_name` in the product lookup;
3. the same key in the family lookup;
4. the compact exact `matched_family_name` for an `algorithm_6_visual_gap` row, otherwise the Algorithm 6 result/family name, in the family lookup;
5. an empty record.

The ID-first lookup is a hard identity boundary. Duplicate commercial names can normalize to the same product key, but distinct catalog rows keep distinct `selected_product_id` values and therefore retain their own price/manufacturer metadata. A product result includes that field whenever the source catalog row has a nonempty `id`.

It then sets:

- `commercial_name_en`, `commercial_name_ar`;
- `base_group_key` to the exact visual `matched_family_name` for visual-gap rows, otherwise the Algorithm 6 result name;
- `family_group_key` to `variant_group` or that result name;
- ingredient, strength, dosage form, route, price, manufacturer, drug class, and warning display fields;
- `matched_context` and `context_conflicts`, defaulting to empty strings;
- `needs_clarification=true` and `confirmation_required=true` unconditionally.

Missing display values become `-`, except warnings/context strings become empty. Because these assignments use truthy `or` fallback, a numeric catalog value of zero would display as `-`.

Provisional context-failure behavior is stricter: a row marked `no_compatible_product` skips every product/family metadata lookup, displays the family name as English commercial name, and leaves all product metadata at its empty/default value. This prevents display enrichment from making a name-only safety result look like a selected conflicting package.

`server_elapsed_ms` is rounded to three decimals and covers lock wait, Algorithm 6 search, product reranking, and result enrichment. It is server processing time, not browser/network latency.

### 2.5 Browser fallback discrepancy

The UI probes `./api/runtime` with a 3.5-second abort timer. It selects static `browser_consensus_search` only when the probe returns HTTP 404 or when the page uses `file:` protocol. A timeout, malformed/non-ready runtime, non-404 HTTP error, or other network error on an HTTP(S) page is treated as “Algorithm 6 unavailable” and does **not** silently fall back. Static browser mode is not Algorithm 6 parity:

- It concatenates `query` and `product_context` before searching.
- It has its own candidate indexes, scoring constants, context scores, aliases, visual-gap implementation, and decision types.
- Its tests in `app/test_app.js` validate the JavaScript behavior, not the Python API.
- A public static deployment therefore must identify itself as browser search, not Algorithm 6.

In static mode the UI fetches `./data/catalog.json`, prepares the JavaScript catalog, and reports `Browser search · N medicines`. In API mode it does not fetch the browser catalog and reports the server's `medicine_count`. Every API search response is rejected if `algorithm != algorithm_6`.

Any rule proposal must name which runtime it changes. A Python change and a browser fallback change are two separate implementations and require separate tests.

## 3. Catalog construction and family semantics

### 3.1 Product rows

The application catalog contains 25,066 rows. Important compact fields include:

| Field | Meaning |
| --- | --- |
| `n` | Commercial product/package name. |
| `b` | Base commercial family. |
| `ar` | Arabic commercial display name. |
| `ing` or `s` | Ingredient/composition. |
| `st` | Parsed strength/presentation field. |
| `f` | Parsed dosage-form family. |
| `r` | Route family. |
| `m` | Manufacturer. |
| `dc` | Drug class. |
| `p` | Price. |
| `w` | Pipe-delimited warning flags. |

### 3.2 Algorithm 5 family construction

`build_rescue_index()` uses `b`, falling back to `n`, and deduplicates by `compact_key()`. It retains:

- first encountered display name
- up to eight distinct commercial examples
- warnings from `_warnings` and `w`
- ingredient values
- manufacturer values

The Algorithm 6 `build_families()` invariant is exactly 17,476 families. Startup fails if the count differs.

### 3.3 Variant grouping

`assign_variant_groups()` starts every family as its own normalized name. A family can be grouped under its first normalized token only when:

1. the first token has at least four characters;
2. at least two families share that token; and
3. the family shares at least one manufacturer with another family in that cohort.

Ingredient equality is deliberately not required, because labels such as `EXTRA` and `PLUS` may represent clinically different variants that must remain visible. Family-head indexes are built only when `variant_group != norm`.

Algorithm 6 separately records all such variant-family compact keys in `variant_family_keys`; the optional Algorithm 6 rank-one gate refuses to displace one of these families.

### 3.4 Product-context catalog and exact numeric aliases

`build_product_catalog()` creates eight lookup fields on the frozen `ProductCatalog` dataclass:

- `records_by_group`: product rows under the broad Algorithm 6 `family_to_group` display mapping, sorted by case-folded commercial name;
- `records_by_family`: the same rows keyed by the compact **exact base family**, also sorted by commercial name;
- `group_names`: first display name for each broad variant group;
- `family_names`: display name for each exact base-family key;
- `family_group_keys`: exact base-family key to broad variant-group key;
- `numeric_alias_groups`: prepared exact aliases of at least two leading numeric tokens to sorted exact base-family-key tuples (the historical field name says “groups,” but the values are families);
- `numeric_brand_alias_families`: prepared exact `leading number token(s) + base-family tokens` aliases to sorted exact base-family-key tuples;
- `compact_key`: the shared family-key callback.

For each retained row, the builder takes base-family identity from `b`, falling back to `n`, and maps it separately to its broad variant group. It normalizes commercial-name `n`, collects its contiguous leading tokens that fully match `NUMBER_RE`, and creates:

1. a numeric-only alias when at least two leading tokens are numbers; and
2. a numeric-brand alias when at least one leading numeric token is followed in `n` by the exact normalized base-family tokens.

Both indexes are deduplicated and sorted deterministically by case-folded exact `family_names` and family key. They are built once at catalog preparation; the request path performs exact lookups only, never a fuzzy/global numeric scan. Single leading numbers are absent from the numeric-only index but are allowed in the number-plus-family brand index. Broad groups are retained for display only; product-context scoring uses `records_by_family` so a result such as BRUFEN COLD cannot open plain BRUFEN merely because both share a variant group.

## 4. Name-query normalization

Algorithm 5 and Algorithm 6 use helpers in `benchmark_01_legacy/evaluate_current_app_search.py`.

### 4.1 Unicode and punctuation normalization

`normalize_search(value)` applies, in order:

1. `None -> ""`.
2. Arabic digits `٠١٢٣٤٥٦٧٨٩ -> 0123456789`.
3. Arabic letter folding:
   - `آ`, `أ`, `إ`, `ٱ` -> `ا`
   - `ى`, `ئ` -> `ي`
   - `ؤ` -> `و`
   - `ة` -> `ه`
4. Remove Arabic combining marks U+064B--U+065F, U+0670, and tatweel U+0640.
5. Uppercase.
6. Replace everything outside `0-9`, `A-Z`, and Arabic U+0600--U+06FF with spaces.
7. Collapse whitespace and trim.

`compact_key(value)` removes every remaining non-alphanumeric/non-Arabic separator from the normalized value.

### 4.2 Token filtering

`tokens_of()` ignores tokens shorter than two characters and removes configured English and Arabic noise.

English noise:

```text
AND PRICE DOSE DOS USE USES GENERIC FORTE
TABLET TABLETS TAB TABS CAP CAPS CAPSULE SYRUP DROP DROPS
MG MCG IU G GM ML VIAL AMP AMPOULE INJECTION PEN PENS
```

Arabic noise:

```text
سعر بكام جرام جم مل اقراص قرص كبسول كبسوله كبسولة كبسولات
شراب حقن حقنه حقنة فيال امبول امبوله امبولة
```

Generic tokens, which are treated as weak/non-specific context in the legacy app helpers, include:

```text
PLUS EXTRA FORTE ADVANCE MAX SUPER ULTRA NEW ACTIVE NATURAL GOLD SILVER
BIO VITA VIT PRO CARE SKIN HAIR BABY KIDS ADULT DRUG MEDICINE
CREAM GEL LOTION SOAP SHAMPOO MASK
```

### 4.3 Derived name keys

`skeleton(value)`:

- compact the value;
- `PH -> F`;
- `[CQK] -> K`;
- `[PV] -> B`;
- `[SZ] -> S`;
- delete `A E I O U Y`;
- collapse adjacent repeats.

`drug_phonetic_key(value)`:

- compact the value;
- `PH -> F`, `CK -> K`, `GH -> G`;
- `[BPFV] -> P`;
- `[DT] -> T`;
- `[CGKQ] -> K`;
- `[SZ] -> S`;
- `J -> G`;
- delete vowels;
- collapse repeats.

### 4.4 Number and route extraction in legacy helpers

`parse_numbers()` recognizes normalized decimal-like tokens matching `\b\d+(?:\.\d+)?\b`. Note that name normalization normally replaces punctuation with spaces, so this is not the same parser as the product-context parser.

`parse_route_hints()` maps name-query tokens to:

- `oral_solid`: tablet/capsule aliases and Arabic equivalents
- `oral_liquid`: syrup/suspension/drops and Arabic equivalents
- `injection`: vial/ampoule/injection/infusion, IV/IM, and Arabic equivalents
- `topical`: cream/gel/ointment/lotion and Arabic equivalents
- `soap`, `spray`, `ophthalmic`, `otic`, `mouth`, `rectal`, `vaginal`

These helpers belong to inherited browser/evaluation logic. The Python post-family product parser has a separate alias table in Section 17.

## 5. Inherited Algorithm 2

Algorithm 5 uses `english_search_algorithm_fast.py` as its sole full base search. This component is English-only and has normalization and aliases separate from Section 4.

### 5.1 Algorithm 2 normalization

`normalize_name()`:

- converts `None` to empty string;
- uppercases;
- replaces `&` with `AND`;
- replaces `+` with `PLUS`;
- replaces every non-ASCII-alphanumeric run with a space;
- collapses spaces.

`compact_name()` then removes all non-ASCII-alphanumerics.

Algorithm 2 skeleton:

- `PH -> F`
- `[CQK] -> K`
- `[PV] -> B`
- `[SZ] -> S`
- delete vowels
- collapse repeats

Algorithm 2 phonetic key:

- `PH -> F`, `CK -> K`, `GH -> G`
- `[BPFV] -> P`
- `[DT] -> T`
- `[CGKQ] -> K`
- `[SZ] -> S`
- `J -> G`
- delete vowels
- collapse repeats

### 5.2 Inherited medicine-specific aliases

These are active inherited rules, not generic OCR rules:

| Target | Accepted compact aliases |
| --- | --- |
| `PANADOL` | `BANADOL`, `BANDOL`, `PANDOL`, `PNDL`, `PANDL`, `PANADL`, `PANADOLE`, `BANADOLE`, `BANADOLCOLD`, `PANDOLCOLD`, `BANDOLCOLD` |
| `AUGMENTIN` | `OGMENTIN`, `OGMNTIN`, `AUGMNTIN`, `AUGMANTIN` |
| `VOLTAREN` | `FOLTARIN`, `VOLTARIN`, `FOLTAREN` |
| `BRUFEN` | `BRUFN`, `BRFN`, `BRUFIN`, `BROFEN` |
| `KETOFAN` | `KETOFN`, `KETOFEN` |
| `NEXIUM` | `NEKSIUM`, `NEKSUM`, `NEXUM` |

The repository also has broader `BASE_ALIASES` in the legacy evaluator/browser helper, including Arabic aliases and Lipitor variants. Those do not automatically become Algorithm 2 aliases unless the relevant runtime calls that helper.

Documentation stating that “no medicine name appears in a rule” must be scoped to the accepted generic Algorithm 5 corrections. It is not true of the complete inherited stack.

### 5.3 Algorithm 2 confusion costs

Active symmetric substitution groups:

```text
V/F  P/B  C/K  Q/K  I/E  O/U  Y/I  S/Z  T/D  G/J
```

Weighted Damerau costs:

- exact character: `0`
- listed substitution: `0.45`
- other substitution: `1.0`
- insertion/deletion: `1.0`
- adjacent transposition: `0.45`

### 5.4 Common-token rule

`COMMON_DF_RATIO = 0.005`. A token is common when either explicitly listed or present in at least 0.5% of records.

Explicit common commercial tokens:

```text
TOPICAL FACIAL CREAM GEL HAIR SKIN CARE EXTRA PLUS FORTE ADVANCE
VITA VIT BIO BABY KIDS ORAL MOUTH INTIMATE WHITENING CLEANSING
MOISTURIZING SUNSCREEN LOTION SOAP SHAMPOO MASK SPRAY
```

Common-token contribution uses base weight `0.20`; a specific token uses `1.0`. Each is multiplied by normalized IDF.

### 5.5 Algorithm 2 indexes

| Index | Construction |
| --- | --- |
| Exact | Normalized and compact full names. |
| Prefix | Compact prefixes length 2--12. |
| Suffix | Reversed compact suffixes length 3--12. |
| Token | Exact tokens and token prefixes length 2--8. |
| Character grams | Sets of 3-grams and 4-grams. |
| Skeleton | Exact and prefixes length 3--10. |
| Phonetic | Exact and prefixes length 3--10. |
| Delete | All keys through `max_deletes_for()`. |

`max_deletes_for()` returns:

- 0 below length 4;
- 1 for length 4--7;
- 2 above length 7.

Delete keys shorter than three characters are discarded.

### 5.6 Query modes

`classify_query()` can assign:

- `too_short`: compact length <=2
- `exact_like`: exact compact bucket exists
- `common_token_query`: one token and no specific token
- `prefix_fragment`: length >=3 and prefix bucket exists
- `suffix_fragment`: length >=4 and suffix bucket exists
- `middle_fragment`: length >=4 and a 3/4-gram bucket of at most 400 exists
- `consonant_skeleton`: skeleton length >=3 and exact skeleton exists, or compact equals vowel-stripped query
- `phonetic_like`: phonetic length >=3 and exact or prefix key exists
- `phrase_like`: more than one token
- `full_typo_like`: compact length >=4

### 5.7 Candidate generation

Candidate sources and bounds:

1. exact normalized and exact compact;
2. exact/prefix approved alias;
3. compact prefix for query length >=3;
4. suffix for length >=4;
5. exact token and token prefix for token length >=3;
6. three rarest 4-grams;
7. if fewer than 40 candidates, three rarest 3-grams;
8. skeleton exact and prefix, prefix bucket cap 1,000;
9. phonetic exact and prefix, prefix bucket cap 1,200;
10. delete keys when compact length <=24, bucket cap 800.

A common token bucket is capped at 1,200 unless the query is solely that common token.

### 5.8 Algorithm 2 feature definitions

- Edit similarity: `max(0, 1 - distance/max_length)`.
- Prefix/suffix/contains require query length >=3 and return `query_length/target_length`.
- Subsequence: `0.55*density + 0.35*coverage + 0.10*start_anchor + 0.10*end_anchor`, capped at 1.
- Skeleton exact is `0.98`, or `0.90` when first characters differ; exact consonant-only representation is `1.0`; prefix is `0.82`; otherwise `0.75*subsequence`.
- Phonetic exact is `1.0`; prefix is `0.80`; otherwise `0.60*subsequence`.
- N-gram score is IDF-weighted Jaccard using 4-grams when available, otherwise 3-grams.
- Token match: exact `1.0`, target-token prefix `0.85` for query token length >=4, containment `0.75` for length >=4.
- Token-order score is the fraction of query token compacts found in order.
- `compact = max(edit, contains, prefix, suffix)`.

### 5.9 Algorithm 2 mode formulas

| Mode | Formula |
| --- | --- |
| Exact | `1.00` for exact, `0.97` for approved alias. |
| Full typo | `.30 edit + .20 weighted_edit + .15 phonetic + .15 skeleton + .10 ngram + .05 subsequence + .05 token` |
| Prefix | `.45 prefix + .15 ngram + .10 edit + .10 phonetic + .10 skeleton + .10 token` |
| Suffix | `.45 suffix + .15 contains + .15 subsequence + .15 ngram + .05 skeleton + .05 edit` |
| Middle | `.35 contains + .25 ngram + .20 subsequence + .10 token + .05 skeleton + .05 edit` |
| Skeleton | `.35 skeleton + .25 subsequence + .15 phonetic + .15 ngram + .10 edit` |
| Phrase | `.30 token + .25 token_order + .15 compact + .15 specific_token + .10 common_context + .05 phonetic` |
| Common token | `min(.62, .55 token + .20 contains)` |

The highest mode score wins before penalties.

### 5.10 Algorithm 2 penalties and confidence

Penalties:

- non-exact compact length <=3: `-0.15`
- common-only non-exact: `-0.25`
- more than 1,200 candidates and compact length <=5: `-0.20`
- otherwise more than 400 candidates and length <=5: `-0.10`
- weak contains/phonetic/ngram-only evidence: `-0.10`

Strong evidence for avoiding the weak-only penalty is exact/alias `1.0`, prefix/suffix >=0.45, skeleton >=0.85, or token >=0.70. Final score is clipped to `[0,1]`; zero is removed.

Result confidence labels:

- high at >=0.85
- medium at >=0.72
- low otherwise

Response rules:

- no candidates -> `no_match`
- length <=2 -> ambiguous
- common-only -> ambiguous
- top <0.55 -> low confidence
- six or more within 0.08 of top -> ambiguous
- high confidence requires top >=0.85, margin >=0.12, length >=4 or exact-like, and at most three close candidates
- medium confidence requires top >=0.72 and margin >=0.06
- top >=0.70 otherwise -> ambiguous

Algorithm 5 later applies a stricter always-confirm policy.

## 6. Algorithm 5 family rescue indexes

Algorithm 5 builds these indexes over unique families:

| Index | Rule |
| --- | --- |
| Exact | Full compact family key. |
| Prefix/suffix | Length 2--12. |
| Character grams | 2-, 3-, and 4-gram sets. |
| Skeleton | Exact and prefixes length 3--10. |
| Phonetic | Exact and prefixes length 3--10. |
| Family head | Exact, prefixes length 3--10, phonetic, and delete keys through two deletions. |
| Delete | Full family delete keys using 0/1/2 deletions by length. |
| Structural | Length, first character, prefix-risk count, family-by-key, and variant-group membership. |

Prefix-risk counts are collected for prefix lengths 1--6.

## 7. Algorithm 5 context-clean pass

Algorithm 5 may run Algorithm 2 twice: once with the raw name query and once with strength/form noise removed.

### 7.1 Context-noise tokens

```text
MG MCG G GM GRAM GRAMS ML L IU UNIT UNITS PERCENT PER
TAB TABS TABLET TABLETS CAP CAPS CAPSULE CAPSULES
SYRUP SUSP SUSPENSION VIAL VIALS AMP AMPS AMPOULE AMPOULES
CREAM GEL OINT OINTMENT DROPS DROP ORAL TOPICAL INJ INJECTION
FC FCT SC SR XR MR RETARD SACHET SACHETS
```

`UNIT_SUFFIX_RE` also removes compact values such as `500MG`, `2ML`, or `1%`. `PURE_NUMBER_RE` recognizes a decimal-form number.

### 7.2 Cleaning rules

- Cleaning runs only when at least one context marker is present.
- Noise tokens and unit-suffixed tokens are removed.
- Split `F C` is treated as film-coated only if another context marker exists.
- A pure number is removed when it is not leading and the adjacent token establishes context.
- Leading numeric brand tokens such as `5 FLUOROURACIL` are intended to survive.
- Cleaning must remove something and leave at least one token.

### 7.3 Clean-search gate

The extra search runs only when:

- cleaned compact is nonempty and differs from original;
- cleaned compact length >=3;
- it is not the risky case where cleaned length <=4 and original length <=8.

This guard prevents product evidence from making a very short name fragment look falsely decisive.

## 8. Algorithm 5 rescue activation and candidate generation

### 8.1 Global constants

| Constant | Value |
| --- | ---: |
| `TOP_K_DEFAULT` | 20 |
| `INTERNAL_EXTERNAL_LIMIT` | 20 |
| `RESCUE_PREFILTER_LIMIT` | 45 |
| `EDGE_RESCUE_PREFILTER_LIMIT` | 15 |
| `EDGE_RESCUE_SHORTLIST_LIMIT` | 45 |
| `RESCUE_UNCERTAIN_SCORE_THRESHOLD` | 0.82 |
| `RESCUE_UNCERTAIN_GAP_THRESHOLD` | 0.045 |
| `EVIDENCE_VARIANT_LIMIT` | 12 |
| `NEAREST_FALLBACK_LIMIT` | 12 |
| `SHORT_FRAME_RETRIEVAL_LIMIT` | 8 |
| `SHORT_FRAME_MAX_RAW_DISTANCE` | 3 |
| `SHORT_FRAME_MAX_WEIGHTED_DISTANCE` | 2.25 |
| `MIXED_VARIANT_LIMIT` | 48 |
| `VALIDATED_HEAD_MAX_DISTANCE` | 2 |
| `SHORT_VISIBLE_HEAD_LIMIT` | 4 |
| `GRAPHEME_VARIANT_LIMIT` | 512 |
| `MAX_GRAPHEME_VARIANT_INPUT_LENGTH` | 24 |
| `TWO_GRAPHEME_CONFUSION_MIN_LENGTH` | 6 |
| `GRAPHEME_PROMOTION_MAX_RANK` | 12 |
| `GRAPHEME_PROMOTION_MAX_SCORE_GAP` | 0.75 is defined; the live direct-promotion check currently uses the stricter literal 0.65 documented in Section 24.2. |
| `GRAPHEME_PREFIX_SURFACE_MAX_FAMILIES` | 4 |

### 8.2 Rescue gate

`should_run_rescue()`:

- always runs for length 3--4 when short-query rescue is enabled;
- runs when Algorithm 2 returns nothing;
- for non-confident Algorithm 2 status, skips only if length >=6, top >=0.78, and margin >=0.08;
- for confident status, runs if top <0.82 or margin <0.045.

In `search_catalog()`, standard rescue excludes the short-query clause, then a separate short-only path preserves Algorithm 2's top result. The current source additionally forces standard rescue when either `exact_grapheme_confusion_family_ids()` or `grapheme_confusion_prefix_family_evidence()` returns evidence, even if the ordinary Algorithm 2 confidence gate would otherwise skip rescue.

### 8.3 Length-scan gate

`should_length_scan()` applies only for compact length 4--12.

- Non-confident status: run when candidate IDs <220, or length <=5 and top <0.50.
- Confident status: refuse when IDs >=220; otherwise run when top <0.90 or margin <0.10.
- Radius is 0 when core IDs >=220, otherwise 3.
- `length_scan_ids()` retains compatible lengths and plausible first characters and caps at 2,200 deterministic IDs.

### 8.4 Base candidate sources

`candidate_family_ids()` adds:

1. exact family;
2. prefix and first-character variants for length >=3;
3. suffix for length >=4;
4. four rarest 4-grams;
5. if fewer than 160 IDs, five rarest 3-grams;
6. skeleton exact/prefix when skeleton length >=3;
7. phonetic exact/prefix when phonetic length >=3;
8. exact single-ligature variants;
9. exact single-phonetic rewrites;
10. duplicate-prefix-removal variants;
11. delete buckets for lengths 3--18, but only buckets of at most 650.

Current bounded OCR retrieval adds two more exact candidate sources after the ordinary list:

12. exact catalog families reached by `grapheme_confusion_variants(..., output_limit=None)`; and
13. proper longer catalog families reached through a corrected prefix, only for query length 6--24, total direct cost <=1.40, and an exact prefix bucket containing at most four families.

Both sets force rescue, enter its core IDs, are restored after the cheap prefilter, and receive explicit evidence reasons. A corrected-prefix family that ordinary scoring would drop may be retained as a low-confidence evidence-only tail candidate; Section 24 gives the exact score and final surfacing gate.

At committed endpoint `66abb7f`, `first_char_variants()` emitted lowercase grouped replacements while indexes were uppercase. The current source does **not** enable all corrected uppercase legacy groups for retrieval. Instead, it returns only the explicit directional keys in `PAIRWISE_SUBSTITUTION_COSTS`, currently `E -> G` and `G -> E`, while `confusable_chars()`/`first_chars_confusable()` retain the broader groups for scoring/plausibility checks. This pairwise-only retrieval boundary avoids expanding weak first-character candidate pools. See Section 24. It is not a deployed-fix claim until the working tree is committed and deployed.

### 8.5 Cheap prefilter formula

Exact family gets `9.0`. Otherwise:

```text
1.35 prefix
+0.65 suffix
+0.55 bigram Jaccard
+1.20 trigram Jaccard
+1.00 four-gram Jaccard
+0.70 skeleton
+0.65 phonetic
+0.35 subsequence
+0.90 weighted edit, only for bounded lengths
+0.45 same-position
+0.25 length coverage
```

Bonuses and penalties:

- same first character `+0.20`
- confusable first character `+0.10`
- length delta <=1: `+0.18`
- length delta <=3: `+0.08`
- weak partial prefix: `-0.35`
- strong edge plus another evidence type: `+0.25`
- family-head alternative can replace this score using `1.80 head_edit + .55 max_edge + .40 position + .25 coverage`, plus `0.45` for distance <=2 or `0.30` for a supported short head.

Reject before scoring if length delta >5, no four-character prefix, and no plausible head.

### 8.6 Short and family-head rescue

- Three-character keyboard rescue generates every one-key-neighbor exact family.
- Short two-deletion rescue accepts query length 3--4 and target length `query+2` when the query, optionally with one vowel changed, is an ordered subsequence.
- Short consonant/phonetic frame rescue accepts length 3--7, skeleton and phonetic lengths 1--2, length delta <=2, raw distance <=3, weighted distance <=2.25, and returns eight.
- Two-character edge candidates must have length delta <=2.
- Short visible family heads accept query length 3--4 when the head is a longer prefix or an ordered subsequence missing one or two characters; at most four representative heads.
- General family-head rescue accepts query length 5--18 and distance <=2, with guarded activation based on Algorithm 2 score/status.

### 8.7 Nearest fallback

Activation range is length 3--16. It runs when there is no Algorithm 2 result or Algorithm 2's top family is farther than the length-based radius:

| Query length | Radius |
| --- | ---: |
| <=3 | 1 |
| 4--6 | 2 |
| 7--9 | 3 |
| 10--16 | 4 |

Candidates must have compatible lengths and a plausible first character. Plausible starts include the original first character, configured confusion variants, directional digit-to-letter variants, the second character for length >=4, and the target first character of a matching ligature rewrite. The fallback returns nothing when the nearest distance exceeds the radius or more than 12 families tie at the nearest distance.

## 9. Active OCR and spelling transformations

### 9.1 Algorithm 5 simple confusion groups

`CONFUSION_GROUPS` are active in weighted edit and first-character evidence:

```text
CKQ  SZ  FV  PB  DT  GJ  MN  IEY  OU
```

Consequences relevant to current requests:

- `I`, `E`, and `Y` are already mutually low-cost in Algorithm 5.
- `E` and `G` are not in one simple group. Current source adds a directional `0.60` pair in the **bounded direct-rewrite registry and pairwise-only first-character retrieval**, without merging the overlapping groups and without changing the generic global character-substitution cost.
- `D` and `AL` are not a simple single-character group. The committed source has `AL -> D`; provisional current source adds bounded `D -> AL` with a higher directional cost. See Section 24.

### 9.2 Algorithm 5 weighted Damerau costs

- exact: `0`
- member of a configured confusion pair: `0.45`
- vowel-to-vowel: `0.70`
- other substitution: `1.0`
- insertion/deletion: `1.0`
- adjacent transposition: `0.55`
- when directional OCR visual scoring is explicitly requested, query digit to mapped target letter: `0.45`

`PAIRWISE_SUBSTITUTION_COSTS` is intentionally absent from this generic `substitution_cost()` chain. In particular, an incidental `E/G` alignment in an unrelated ordinary name does not receive `0.60` inside every global weighted Damerau comparison. The E/G rule is scoped to bounded exact/prefix rewrite evidence, direct visual-gap patterns, pairwise-only first-character retrieval, and an explicitly invoked bounded grapheme edit path. This scope is an active regression guard, not merely an implementation detail.

### 9.3 Directional OCR digits

```text
0 -> O
1 -> I or L
2 -> Z
3 -> E
4 -> A
5 -> S
6 -> G
8 -> B
```

This is intentionally directional. A letter is not generally rewritten to a digit, and dosage-like multi-digit text is not treated as one OCR letter.

### 9.4 Ligature/multi-character pairs

`DIRECTIONAL_VISUAL_LIGATURE_PAIRS`:

```text
IV -> N
```

`LIGATURE_CONFUSION_PAIRS`, in source order:

```text
RN -> M
M  -> RN
CL -> D
D  -> CL
LI -> H
H  -> LI
RI -> N
AL -> D
NN -> M
VV -> W
W  -> UU
IV -> N
IA -> A
II -> U
```

The committed endpoint has `AL -> D` but no corresponding `D -> AL` entry in this older ligature table. Provisional current source adds `D -> AL` in the separate bounded grapheme registry; it does not add it to `LIGATURE_CONFUSION_PAIRS`.

Only the first six entries are `GENERATOR_LIGATURE_PAIRS` for the more expensive ligature-vowel chains.

### 9.5 Visual and phonetic chain groups

Visual groups:

```text
AOUE  ILT  HNBR  MN  GQY  UVW  FTL  ECO
```

Phonetic groups:

```text
BP  DT  GK  SZ  FV  CKQ
```

Because groups overlap, a bounded chain can reach a character through more than one documented step. `character_chain_options()` enumerates up to two visual and one phonetic edit for each character.

### 9.6 Exact phonetic rewrite pairs

```text
PH <-> F
CK <-> K
X  <-> KS
CKS -> X
QU <-> KW
QU -> CW
GH -> G
TH -> T
TH -> S
GHT -> T
WH -> W
SH <-> CH
TION -> SHUN
Y <-> I
Y -> EE
```

### 9.7 Evidence query variants

`evidence_query_variants()` produces at most 12 deterministic variants:

- exactly one digit may become one mapped OCR letter;
- first two unequal characters may swap for length >=4;
- every occurrence of a documented ligature may be rewritten until the cap.

Evidence-variant rescue activates whenever the query contains exactly one digit, or whenever nearest fallback activates.

### 9.8 Multi-step generators

| Generator | Length/rule |
| --- | --- |
| Visual+phonetic exact | Length 4--10; exactly two visual and one phonetic count, at least two changed positions, exact same-length family. |
| Two visual+deletion | Length 4--10; exactly two visual frames then an exact one-character-longer delete-index family. |
| Transposition+deletion | Length 4--16; one adjacent swap then exact one-character-longer family. |
| Ligature+vowel | Length 4--16; one vowel replacement plus one generator ligature, exact family. |
| Ligature+vowel+transposition | Length 4--16; adjacent swap, vowel replacement, generator ligature, exact family. |
| Transposition+vowel+deletion | Length 4--16; adjacent swap, vowel replacement, then exact one-character-longer family. |
| Vowel+phonetic+deletion | Length 3--4; insert one character, one phonetic replacement, one vowel replacement, exact family. |
| Keyboard+vowel+deletion | Length 4--8; vowel replacement, keyboard-neighbor replacement, exact one-character-longer family. |
| Short OCR combined | Length 3--4; digit-to-letter plus either vowel or phonetic replacement, exact family. |

### 9.9 Multi-step score discounts

| Constant | Value |
| --- | ---: |
| `MIXED_VARIANT_SCORE_DISCOUNT` | 0.32 |
| `TRANSPOSE_DELETE_SCORE_DISCOUNT` | 0.28 |
| `KEYBOARD_DELETE_SCORE_DISCOUNT` | 0.45 |
| `VISUAL_PHONETIC_CHAIN_SCORE_DISCOUNT` | 3.35, reduced by 0.10 when tuning flag is active |
| `VISUAL_VISUAL_DELETE_SCORE_DISCOUNT` | 3.75 |
| `TRANSPOSITION_DELETE_EXACT_SCORE_DISCOUNT` | 3.40 |
| `LIGATURE_VOWEL_CHAIN_SCORE_DISCOUNT` | 3.25 |
| `LIGATURE_VOWEL_TRANSPOSE_SCORE_DISCOUNT` | 3.35 |
| `TRANSPOSE_VOWEL_DELETE_SCORE_DISCOUNT` | 3.75, reduced by 0.45 for an eligible existing candidate |
| `VOWEL_PHONETIC_DELETE_SCORE_DISCOUNT` | 3.75 |
| `KEYBOARD_VOWEL_DELETE_EXACT_SCORE_DISCOUNT` | 3.40, reduced by 0.05 in the tuned keyboard-frame case |
| `SHORT_OCR_COMBINED_SCORE_DISCOUNT` | 3.40 |
| `SHORT_TWO_DELETION_VOWEL_DISCOUNT` | 0.12 |
| `STRUCTURAL_VARIANT_SCORE_DISCOUNT` | 0.18 |

The post-transform score is floored at `0.01`. Multi-step evidence cannot silently overwrite the original winner: the pipeline reconstructs a pre-multi-step view and adds preservation reasons before later explicit release gates.

## 10. Algorithm 5 rescue score and merge

### 10.1 `score_family()` formula

```text
1.25 exact
+0.58 ordinary edit similarity
+0.52 weighted edit similarity
+0.16 prefix
+0.10 suffix
+0.10 bigram Jaccard
+0.18 trigram Jaccard
+0.16 skeleton similarity
+0.14 phonetic similarity
+0.10 subsequence
+0.24 same-position evidence
+0.16 length coverage
```

Bonuses:

- same first character: `+0.12`
- confusable first character: `+0.06`
- length delta <=1 and weighted similarity >=0.76: `+0.18`
- prefix >=0.55 and weighted >=0.66: `+0.08`
- weighted >=0.84 and positional >=0.70: `+0.22`

Penalties:

- partial prefix and weighted <0.84: `-0.18 - min(0.24, 0.05*length_delta)`
- non-exact query length <=4 and edit <0.76: `-0.22`
- both edit scores <0.58 and skeleton/phonetic <0.72: `-0.20`
- prefix <0.30, trigram <0.12, and both edit scores <0.70: `-0.10`

Family-head scoring can replace the full-name score when the validated head is within distance 2 or supported by a short visible head. It uses the same principal components with exact-head weight `0.70`, then adds `0.30` for validated edit or `0.20` for short visible prefix.

General acceptance requires score >=0.62, unless positional OCR rescue applies: same first character, positional >=0.40, coverage >=0.70, and score >=0.58.

### 10.2 Evidence reasons

The scorer emits:

- `exact_family`
- `catalog_warning`
- `variant_head_edit` or `visible_head_prefix`
- `positional_ocr_rescue`
- `family_edit` at ordinary edit similarity >=0.76
- `weighted_confusion_edit` at weighted similarity >=0.76
- `prefix_family` at prefix >=0.35
- `skeleton_family` at skeleton >=0.80
- `phonetic_family` at phonetic >=0.78

The rescue wrapper additionally attaches `bounded_grapheme_confusion_retrieval` to exact-family rewrites and `bounded_grapheme_confusion_prefix_retrieval` to corrected proper-prefix families. If ordinary `score_family()` rejects a corrected-prefix family, the wrapper may create an evidence-only tail row at:

```text
max(0.62, 0.78 + 0.18*(corrected_prefix_length/family_length) - 0.10*rewrite_cost)
```

That fallback also records `bounded_grapheme_confusion_depth_{depth}`. It is deliberately low confidence and does not itself authorize rank one.

### 10.3 Merge contributions

| Source | Contribution |
| --- | --- |
| Algorithm 2 | `.72*min(score,1) + .32/(rank+2)`; multiply by `.90` when status is not high/medium confidence. |
| Context-clean Algorithm 2 | `.84*min(score,1) + .40/(rank+2) + .05` |
| Rescue | `score + .18/(rank+1)` |

Agreement bonuses:

- Algorithm 2 plus context-clean: `+0.06`
- Algorithm 2 plus rescue: `+0.08`

Evidence-only duplicate behavior is guarded. Exact-chain evidence can augment an existing candidate when `ENABLE_EXACT_CHAIN_EXISTING_AUGMENTATION` is true; otherwise duplicate multi-step evidence is ignored. Family-head-only evidence can add a candidate without erasing stronger full-name evidence.

## 11. Algorithm 5 ordering and correction gates

All `ENABLE_*` switches in the current source are `True`. A future rulebook revision must record any switch changed to false.

### 11.1 Brand-like gate

Spelling corrections in `rank_candidate_core()` apply only when:

- compact length is 4--20;
- normalized query has at most three tokens;
- it contains no configured context-noise token;
- there are at least two results; and
- top raw distance is nonzero.

Base order is descending merged score, then clarification sort, then name.

### 11.2 Core bounded corrections

A non-top candidate is eligible through one of:

| Rule | Exact guard |
| --- | --- |
| Strictly closer, dual retrieval | External and rescue both present; candidate raw distance <=2; at least one edit closer; top-minus-candidate score <=0.25. |
| Pure deletion | Current top is not itself pure deletion; candidate is query as ordered subsequence with one/two omitted target characters; candidate no farther; gap <=0.40. |
| Multi-token false positive | Top display name has multiple tokens, candidate one; candidate closer and raw <=2; gap <=0.20. |
| Variant-head correction | Candidate has validated family-head evidence, query length >=5, head distance <=2, different group from top, effective distance at least one closer, gap <=1.40. |

Eligible candidates sort by effective raw distance, weighted distance, edge evidence, positional evidence, score, and name.

### 11.3 Strict full-name correction

Constants:

- `STRICT_FULL_NAME_MAX_DISTANCE = 3`
- `STRICT_FULL_NAME_SCORE_GAP = 0.35`
- `STRICT_FULL_NAME_MIN_WEIGHTED_GAIN = 0.35`
- `STRICT_FULL_NAME_MIN_EDGE_GAIN = 0.05`

It requires query length >=5, a rescue-only candidate at least one effective edit closer, weighted no worse, rescue rank <=5, weighted gain >=0.35, two-sided edge gain >=0.05, and score gap <=0.35. It refuses when the top already has both phonetic and skeleton exact evidence, a prefix match, or a contains match.

### 11.4 Evidence-expansion guard

New fallback candidates do not change top one unless decisive:

- Unique nearest path: candidate is the sole nearest fallback, inside the radius, at least two edits closer, and score gap <=`EVIDENCE_PROMOTION_MAX_SCORE_GAP` 0.40.
- One-transform path: transformed distance <=1, original raw within radius, unique best under that transform, at least two transformed edits better than the legacy top, and score gap <=`STRUCTURAL_PROMOTION_MAX_SCORE_GAP` 1.40.
- A leading swap additionally requires the candidate to be the unique ordinary nearest.
- A digit variant must improve both OCR-visual gain and OCR-visual distance over the legacy top.

Otherwise the pre-fallback top is restored.

### 11.5 Directional OCR raw-distance tie

`promote_ocr_visual_tie()` runs only when the query contains exactly one digit, top raw distance is nonzero, and there are at least two candidates. Within the first five candidates, an alternative may move first only when:

- raw distance ties top;
- OCR-visual gain is greater;
- OCR-visual distance is lower; and
- score gap <=`OCR_VISUAL_TIE_MAX_SCORE_GAP` 0.25.

Tie order: lowest OCR-visual distance, greatest gain, greatest positional evidence, greatest score, name.

### 11.6 Sequential general promotion rules

These rules run in source order; an earlier correction may protect top from later rules.

| Rule | Exact bounds |
| --- | --- |
| Unique nearest | Unique nearest; rank <=3; distance <=4; at least two raw edits closer; score gap <=0.75; top cannot be exact or variant-head. |
| Contained nearest | Top has `contains_match` and no correction; unique nearest at rank 2; distance <=1; at least one closer; gap <=0.25. |
| Preserved-top dominant nearest | Top has a `preserved_*` reason, no correction; unique rank-2 candidate; raw <=3; raw gain >=1; weighted gain >=1.30; gap <=0.10. |
| Preserved-top higher-score nearest | Preserved top; rank 2; candidate closer and already scores higher; candidate key not shorter than query; candidate has no correction. |
| Exact ligature nearest | Unique exact ligature among ranks 2--5; unique ordinary nearest; candidate rank <=4; dual retrieval; raw gain >=1; weighted no worse; gap <=0.40. |
| Weighted edge tie | Raw tie among first five; unique best weighted; rank <=3; weighted gain >=0.70; edge no worse; gap <=0.40. |
| Weighted edge advantage | Raw tie; unique best weighted at rank 2; weighted gain >=0.50; edge gain >=0.20; gap <=0.25. |
| Exact-key Pareto tie | Raw tie in ranks 2--5; phonetic/skeleton exact advantage; no worse weighted, position, edge, and dual agreement; strictly better on one; unique composite gain; rank <=3; gap <=0.15. |
| Phonetic-position tie | Rank <=3; raw tie; candidate phonetic exact and top not; weighted gain >=0.50; position gain >=0.05; gap <=0.40. |
| Shifted-edge agreement | Top not dual; candidate rank <=3 and dual; raw tie; weighted/visual no worse; edge gain >=0.30; candidate positional evidence may be lower by at least 0.05; gap <=0.25; unique best external rank. |
| Visual-distance tie | Unique best OCR-visual among raw-tied first five; rank 2; visual gain >=0.70; gap <=0.10. |
| Skeleton-position tie | Unique exact-skeleton raw-tied candidate at rank 2; weighted and position no worse; gap <=0.05. |

### 11.7 Exact-chain promotion matrix

`promote_bounded_exact_chain_candidate()` examines only ranks 2--5, refuses exact top, usually protects a variant-head top, and applies the call-specific matrix below.

| Chain/correction | Max rank | Max score gap | Max raw disadvantage | Additional guards |
| --- | ---: | ---: | ---: | --- |
| Ligature+vowel+transpose chain | 5 | 0.40 | 1 | Unique. |
| Ligature+vowel+transpose extension | 5 | 0.75 | 1 | Unique; protect existing correction; variant-head protection disabled. |
| Ligature+vowel | 5 | 0.40 | 0 | Unique. |
| Ligature+vowel distance extension | 2 | 0.05 | 1 | Unique; protect existing correction. |
| Ligature+vowel edge extension | 2 | 0.15 | 1 | Unique; edge no worse; protect correction. |
| Ligature+vowel multi-chain extension | 5 | 0.40 | 1 | Unique; at least two chain reasons; protect correction. |
| Visual+phonetic chain | 5 | 0.10 | 1 | Unique; dual retrieval. |
| Visual+phonetic exact-key extension | 2 | 0.40 | 0 | Unique; exact key advantage; weighted no worse; protect correction. |
| Visual+phonetic dual extension | 4 | 0.15 | 0 | Unique; dual; weighted no worse; protect correction; variant-head protection disabled. |
| Keyboard+vowel+deletion | 5 | 0.00 | 1 | Unique; exact-key advantage. |
| Keyboard exact-key extension | 3 | 0.25 | 1 | Unique; exact-key advantage; weighted no worse; protect correction; variant-head protection disabled. |
| Two-visual+deletion | 3 | 0.02 | 1 | Unique; positional no worse; protect correction. |
| Visual multi-chain | 3 | 0.15 | 0 | Unique; weighted no worse; at least three chain reasons; protect correction. |
| Transposition+deletion exact | 3 | 0.25 | 0 | Unique; exact-key advantage; weighted no worse; protect correction. |
| Transposition+vowel+deletion | 5 | 0.00 | 0 | Unique; protect correction; variant-head protection disabled. |
| Vowel+phonetic+deletion | 2 | 0.25 | 2 | Unique; weighted no worse; at least two chain reasons; protect correction. |
| Vowel+phonetic multi-chain extension | 2 | 0.10 | 2 | Unique; exact-key advantage; at least two chain reasons; protect correction. |

“Exact-key advantage” means candidate has `phonetic_exact` or `skeleton_exact` and top does not. “Dual” means both Algorithm 2 and rescue retrieved the candidate.

### 11.8 Later exact and structural rules

| Rule | Guard |
| --- | --- |
| Weighted exact-key tie | Raw tie; top key not shorter than query; unique weighted best at rank 2; dual; exact-key advantage; weighted gain >=0.45; gap <=0.05. |
| Exact transposition tie | Query length >=5; unique exact adjacent-swap candidate among ranks 2--3; raw tie <=1; weighted no worse; gap <=0.25. |
| Exact transposition dual extension | Unique exact swap in ranks 2--5, specifically rank 2; raw <=1; dual; weighted no worse; gap <=0.65. |
| Exact keyboard/key tie | Unique exact keyboard variant at rank 2; raw tie <=1; exact-key advantage; weighted no worse; gap <=0.10. |
| Keyboard weighted extension | Rank 2; exact keyboard variant; raw tie <=1; candidate has an exact key; weighted gain >=0.25; gap <=0.15. |
| Exact visual edge tie | Unique one-visual-substitution candidate at rank 2; raw tie <=1; weighted disadvantage <=0.25; position no worse; edge gain >=0.10; gap <=0.15. |
| Guarded-top score-dominant chain | Top was variant-head/preserved; rank-2 chain candidate score advantage >=1.0; raw disadvantage <=2; weighted disadvantage <=2.0. |
| Score-dominant chain release | Unguarded dual top; rank-2 candidate has chain reason, external absent, rescue rank 1, score advantage >=0.05, raw disadvantage <=1, weighted no worse. |
| Exact ligature rank extension | Exactly one rewritten catalog family, candidate already within top five. If a new variable-length grapheme rewrite directly produces it, the candidate must be rank two or three; a raw-worse `AL -> D` result is refused. |
| Exact phonetic rewrite | Exactly one rewritten catalog family, candidate already within top five. |
| Stutter prefix | Removing duplicated 2- or 3-character prefix yields exactly one candidate; it is promoted. |

### 11.9 Family-head and visible-character rules

Constants:

- `TWO_SIDED_ANCHOR_MAX_DISTANCE = 2`
- `TWO_SIDED_ANCHOR_MAX_SCORE_GAP = 0.40`
- `VALIDATED_HEAD_MAX_DISTANCE = 2`
- `SHORT_VISIBLE_HEAD_LIMIT = 4`

Rules:

- `apply_validated_family_head_evidence()` uses one representative per head within raw distance 2. A unique closer same-first-character head can promote; an already corrected top is displaced only by a one-edit, two-boundary-anchor head. Other close heads are moved ahead of unprotected farther results.
- `promote_two_sided_anchor_tie_candidate()` applies for query length >=4, top distance 1--2, and no prior correction. It refuses a short trailing continuation ambiguity. A tied alternative must preserve both boundary characters, be weighted no worse, not reduce LCS or edge evidence, and normally be within score gap 0.40. Equally supported alternatives preserve order.
- `surface_short_visible_head_candidates()` reserves bounded visible slots for 3--4-character head evidence but does not automatically make them top.
- `ordered_character_head_family_id()` applies to query length 7--16, requires a same/confusable first character, at least three shared bigrams, normalized raw distance <=0.46, LCS/query >=0.54, LCS/head >=0.65, and a unique nearest head. It can be inserted into the final visible slot only when the current top is at least two edits farther.
- `promote_candidate_pool_bounded_head_candidate()` requires a unique returned nearest head, head raw advantage >=1, OCR-visual advantage >=0.30, LCS no worse, and gap <=0.85; it normally protects a top full-name distance <=3 and refuses a candidate whose **complete catalog name** has worse raw distance than the incumbent. The sole complete-name exception requires a real shorter family head (`head != full key`, full key strictly starts with head) whose head raw distance is closer than the incumbent's complete-name raw distance. All ordinary uniqueness/evidence gates still apply. This narrow strict-prefix exception restores the ABASAGLAR head (whose exact bases include CARTRIDGES and KWIKPEN) on four fair queries without reopening the unrelated historical SEROPIPE/BLAIR promotion.
- `promote_pareto_character_evidence_candidate()` applies only when top raw distance >3 and is unprotected. One candidate in ranks 2--3 must be no worse on raw, weighted, OCR-visual, LCS, position, bigram, trigram, and structural overlap; must improve edge by >=0.10; and gap <=0.30.
- `surface_grapheme_confusion_prefix_candidates()` runs only for query length 6--24 and result limit >=2, and refuses an exact catalog query. It recomputes the globally bounded corrected-prefix evidence, retains only families at the global minimum rewrite cost, and does nothing when every eligible family is already visible. Otherwise it reserves at most `limit-1` tail slots, sorted by `(cost, depth, corrected spelling, family name/key)`, adds `bounded_grapheme_confusion_prefix_candidate`, and never replaces/promotes rank one. Algorithm 6's later external-slot insertion also refuses to evict a row carrying this prefix evidence when another removable row exists.

### 11.10 Post-grapheme clean-safety repairs

After direct grapheme promotion, exact-name protection, and corrected-prefix surfacing, `apply_post_grapheme_safety_repairs()` applies three narrowly ordered generic repairs:

1. **Preserved-chain Pareto release.** Among ranks two and three, exactly one candidate must score strictly higher and have strictly smaller raw and weighted edit distances than the top, and it must carry an exact-chain evidence reason. If the top carries any `preserved_*` reason, that one candidate moves first with `strict_chain_pareto_release_correction`.
2. **External-rank chain tie protection.** The top and second row must both carry `ligature_vowel_chain_retrieval`, have equal raw distance, and the second must be Algorithm 2 external rank one while the top has a worse nonempty external rank. With top-minus-second score <=0.10 and no bounded-grapheme retrieval on the top, the second moves first with `external_rank_chain_tie_protection`.
3. **Paired Hit@5 shortlist repair.** Among ranks two through twelve, exactly one candidate may carry `ligature_vowel_transposition_chain_retrieval`, score >=0.90, trail the current top by <=0.50, and have raw distance <=4. If it is currently rank six or lower, it moves to rank five with `bounded_exact_chain_top5_shortlist`; this preserves retrieval without claiming rank one.

These predicates were chosen and verified through paired clean-set changes. They do not suppress clarification or authorize automatic selection.

## 12. Algorithm 5 safety and response contract

`needs_clarification()` currently returns `True` on every path, including an exact family. Specific checks for length <=2, catalog warnings, risky prefixes, and non-exact results all return true, and the final fallback also returns true.

Therefore:

- Algorithm 5 never authorizes an automatic medicine selection.
- Every Algorithm 5 result receives low confidence and `algorithm5_requires_clarification`.
- API display enrichment later sets `needs_clarification` and `confirmation_required` true again.

Prefix risk:

- queries longer than five are not prefix-risky;
- for prefix lengths <=3, eight or more indexed families is risky;
- for prefix lengths 4--5, twelve or more is risky.

Decision types:

- unreadable before/middle/after variants
- `family_variant_selection` when top has multiple variants
- `collision_ambiguity` for exact-prefix collisions or plausible close neighbors
- `equal_distance_ambiguity` when first two raw distances tie
- `possible_matches` or `ranked_matches`

Because clarification is always true, Algorithm 5 response status is normally ambiguous even though dormant high/medium thresholds exist at scores 1.22/0.96 with margins 0.08/0.05.

## 13. Algorithm 6 consensus layer

### 13.1 Catalog constants

- `TOP_K_DEFAULT = 20`
- `RRF_CONSTANT = 60`
- exactly 17,476 families

`load_policy()` deep-copies `DEFAULT_POLICY` through JSON when the requested policy file does not exist. When a policy file exists, it must contain `rank_1_gate`, `top_20_gate`, and `confusion_costs` or startup raises `ValueError`.

`prepare_catalog()`:

- loads the application product records and a separately prepared Algorithm 5 catalog;
- counts product-row frequency per compact base family and retains the first display name;
- sorts families by case-folded display name then compact key and fails unless there are exactly 17,476;
- prepares binary character-bigram cardinalities, BM25+ character-trigram weights, SymSpell entries, and three phonetic-code arrays;
- builds the variant-family protection set from Algorithm 5 families whose `variant_group` differs from their normalized family name;
- precomputes `visual_grapheme_key()` for every complete family and distinct family-head target;
- stores the loaded policy with the prepared catalog.

### 13.2 Ten ranking sources

Algorithm 6 uses Algorithm 5 plus nine additional retrievers:

| Source | Query/target representation | Method |
| --- | --- | --- |
| `algorithm_5` | Raw query through Algorithm 5 | Existing ordered top 20. |
| `jaro_winkler` | Compact | RapidFuzz Jaro-Winkler similarity. |
| `match_rating` | Letters-only normalized | Jellyfish Match Rating codex, ranked by Levenshtein distance between codes. |
| `rapidfuzz_wratio` | Normalized | RapidFuzz WRatio. |
| `nysiis` | Letters-only normalized | Jellyfish NYSIIS code, ranked by code distance. |
| `bm25_plus_char3` | Compact character trigrams | BM25+ style sparse score. |
| `symspell_uniform_ed3` | Compact | SymSpell, maximum edit distance 3, prefix length 7, count threshold 1. |
| `rapidfuzz_token_sort` | Normalized | RapidFuzz token-sort ratio. |
| `soundex` | Letters-only normalized | Jellyfish Soundex code, ranked by code distance. |
| `dice_char2` | Compact character bigrams | Binary Dice coefficient. |

BM25 constants are `k1=1.5` and `b=0.75`. Its IDF is `log(N+1)-log(document_frequency)`.

Additional exact retrieval behavior:

- each retriever is asked for the top 20 even when the API response limit is smaller;
- Algorithm 5 is likewise called with `max(requested_limit, 20)`;
- RapidFuzz returns the family names attached to its extracted choice indexes;
- BM25/Dice retain only finite positive scores and tie-break by stable family index;
- SymSpell uses `Verbosity.ALL`, maximum edit distance 3, no unknown result, and no casing transfer;
- Match Rating, NYSIIS, and Soundex strip the normalized query to alphabetic characters before encoding; an empty letter string produces an empty code.

### 13.3 Candidate evidence

For every union candidate, Algorithm 6 stores one rank per source and calculates:

- source count
- RRF: sum of `1/(60+rank)`
- ordinary Levenshtein similarity
- Jaro-Winkler similarity
- character-bigram Dice
- learned-confusion similarity
- Algorithm 5 rank, or 999 when absent

`consensus_order()` sorts by:

1. descending source count;
2. descending RRF;
3. descending Levenshtein similarity;
4. descending Jaro-Winkler;
5. case-folded name;
6. compact key.

Learned-confusion similarity is **diagnostic** and is not in this order.

### 13.4 Rank-one gate -- implemented but disabled

The loaded policy contains:

```json
{
  "enabled": false,
  "minimum_sources": 7,
  "minimum_source_advantage": 1,
  "minimum_levenshtein_advantage": 0.02,
  "maximum_jaro_disadvantage": 0.02,
  "minimum_bigram_advantage": 0.0,
  "maximum_algorithm_5_rank": 3
}
```

If enabled, all conditions must pass and the current Algorithm 5 top must not be a variant-family key. Because `enabled` is false, Algorithm 6 consensus currently does not reorder Algorithm 5 rank one through this gate.

### 13.5 External top-20 slot -- active

A consensus-only candidate requires:

- source count >=3;
- Levenshtein similarity >=0.55;
- Jaro-Winkler >=0.85.

When the Algorithm 5 list already fills the requested result limit, `top_20_gate.slots=1` means at most one last row is removed and one external candidate is appended. When Algorithm 5 returns fewer rows than requested, the code fills **every vacant result slot**, not just one, with qualifying external candidates in consensus order. Thus “one external slot” is exact only for a full base list.

An external row starts with the family name as name/commercial/canonical name, one commercial example, RRF as score, empty ingredients/variants, and reason `algorithm6_external_consensus_slot`. Display enrichment may attach catalog metadata later. Every augmented/preserved/external row is low-confidence and clarification-required.

### 13.6 Probability/abstention -- inactive without policy block

`calibrated_probability()` supports a standardized logistic model with feature list, means, scales, coefficients, intercept, evidence minimums, and threshold. The current policy has no `abstention` object, so it returns probability `0.0` and `calibrated_likely_match=false`.

If an abstention block is later supplied, the available raw features are:

- top-1 source count, RRF, Levenshtein, Jaro-Winkler, and bigram Dice;
- top-1 minus top-2 source count, RRF, Levenshtein, and Jaro-Winkler (or the top value when no second candidate exists);
- returned-candidate count;
- binary consensus promotion and external-slot indicators;
- compact input length.

Each named feature is standardized by `(value-mean)/(scale or 1)`. The logit is clamped to probability 1 at >=40 and 0 at <=-40; otherwise it uses the logistic function. `likely_match` additionally requires every configured evidence minimum and probability >= configured threshold.

No current user-facing claim should call Algorithm 6 automatically confident.

### 13.7 Ordinary search response flow

- Explicit visual-gap syntax always returns a visual-gap response, even with no result. Safe shorthand returns a gap response only when it found at least one result; otherwise ordinary Algorithm 5/6 search continues.
- A nonempty ordinary query builds all ten rankings, unions candidates, preserves Algorithm 5 order, applies the disabled/optional rank-one gate, and then applies the active external-slot rule.
- Even if enabled, the rank-one gate can promote only a proposed candidate already present in the Algorithm 5 returned list; an external consensus-only family is not inserted directly at rank one.
- Result ranks are reassigned sequentially after promotion/insertion.
- `candidate_count` is the ten-source union size, not Algorithm 5's child candidate pool and not necessarily the number returned.
- The top row receives probability/likely-match fields; the response also exposes them at top level.
- Decision priority is `likely_match_requires_confirmation`, then `bounded_consensus_promotion`, then `consensus_candidate_set`, then `algorithm_5_order_preserved`.
- Ordinary response status is `ambiguous` whenever any result exists and `no_match` otherwise; even a calibrated likely result remains confirmation-required.
- An empty compact query returns a copied Algorithm 5 response with Algorithm 6 ID/version but bypasses consensus. The API normally blocks an empty trimmed query first.

## 14. Learned confusion policy -- diagnostic only

`algorithm_6_policy.json` contains learned directional costs. `learned_confusion_distance()` uses dynamic programming with default insertion/deletion/substitution cost 1.0 and the configured exceptions below. The resulting similarity is returned in result metadata but currently does not affect consensus ordering, because the rank-one gate is disabled and learned similarity is not a consensus sort key.

### 14.1 Insertion costs

| Character | Cost | Character | Cost |
| --- | ---: | --- | ---: |
| A | 0.77541667 | C | 0.93125 |
| I | 0.98854167 | L | 0.81666667 |
| O | 0.73333333 | R | 0.96333333 |
| S | 0.98854167 | T | 0.56 |
| V | 0.98854167 | X | 0.98854167 |
| Y | 0.98854167 |  |  |

### 14.2 Deletion costs

| Character | Cost | Character | Cost | Character | Cost |
| --- | ---: | --- | ---: | --- | ---: |
| A | 0.88571429 | B | 0.9875 | C | 0.61538462 |
| D | 0.925 | E | 0.6625 | F | 0.88571429 |
| G | 0.88571429 | H | 0.9875 | I | 0.8 |
| K | 0.9875 | L | 0.88571429 | M | 0.96 |
| N | 0.925 | O | 0.56785714 | R | 0.84375 |
| S | 0.9875 | T | 0.925 | U | 0.96 |
| V | 0.9875 | Y | 0.9875 | Z | 0.96 |

### 14.3 Directional substitution costs

```text
0>C .8   0>O .8   4>A .8
A>C .92888889  A>I .64444444  A>L .97777778  A>O .4
A>R .86666667  A>S .97777778  A>T .86666667  A>X .97777778
B>S .8  B>T .8
C>A .93333333  C>E .93333333  C>I .78666667  C>O .93333333
C>R .6  C>S .93333333  C>V .93333333
D>A .73877551  D>F .97142857  D>G .97142857  D>L .44
D>R .97142857  D>S .97142857  D>T .90857143
E>A .94  E>C .30434783  E>I .968  E>O .94  E>T .99  E>X .99
F>T .44
G>A .5  G>F .96  G>X .872
H>L .96666667  H>O .89333333  H>R .46666667  H>T .58333333
I>A .54285714  I>C .95  I>E .54285714  I>O .7  I>S .95  I>T .95
K>C .9  K>L .9  K>R .68
L>A .96666667  L>C .96666667  L>D .96666667  L>O .96666667
L>R .96666667  L>T .46666667
M>O .84  M>R .54285714  M>S .95  M>T .7
N>A .89090909  N>L .89090909  N>M .94181818  N>R .37142857
N>S .98181818  N>V .94181818
O>A .41818182  O>C .6  O>E .975  O>I .6  O>T .975  O>X .975
P>I .93333333  P>T .6  P>X .93333333
Q>A .9  Q>G .68
R>C .95  R>H .7  R>L .7  R>O .95  R>S .54285714  R>T .95
S>C .68  S>X .9
T>I .93333333  T>L .93333333  T>O .78666667  T>R .6
T>U .93333333
U>A .6  U>E .85  U>I .92  U>L .975  U>O .41818182
U>T .92  U>V .975
V>B .9  V>O .68
W>H .8  W>V .8
X>O .9  X>R .9  X>S .68
Y>A .9  Y>C .68  Y>R .68  Y>V .9  Y>X .68
Z>R .8
```

Notably, this learned table has no `E>G`, `G>E`, `D>AL`, or `Y>I/E` multi-character rule. Algorithm 5's active generic `IEY` group separately supplies low-cost I/E/Y substitutions.

Training contract recorded in policy:

- source: `benchmark_03_ocr/artifacts/04_model_predictions/search_cases.csv`
- split: development
- target families: 15
- provisionally eligible cases: 211
- holdout rows used: 0
- case-specific rules: 0

## 15. Visual-gap search

### 15.1 Accepted markers

`VISUAL_GAP_MARKER` recognizes:

- two or more ASCII dots: `..`, `...`, etc.
- one or more Unicode ellipses: `…`
- one or more asterisks: `*`
- one or more question marks: `?`
- two or more underscores: `__`

Every explicit marker means “one or more target characters are unreadable here.” The matcher enforces a nonzero hidden span at a leading edge, between every pair of retained visible fragments, and at a trailing edge across raw, fixed-grapheme, directional-confusion, and ordinary-fuzzy paths.

### 15.2 Explicit marker parsing

- Split on marker runs.
- Normalize each visible part through `compact_key()`.
- Remove empty fragments.
- Require one through `MAX_VISUAL_GAP_FRAGMENTS = 4` retained fragments and at least two total visible characters.
- `anchor_start` is false when the first marker starts at position zero.
- `anchor_end` is false when the final marker ends at the text length.
- Mark the pattern `explicit=true`.

More than four retained fragments is rejected as a visual-gap request. Each gap between retained fragments consumes at least one target character; for example, exact PANADOL is not a valid result for `PANA...DOL`, and exact RIVOTRIL is not valid for `RI...VO...TRIL`. Multiple adjacent marker runs separated only by text that compacts to empty are represented as one gap between the retained fragments.

Modes returned:

| Anchors | Mode |
| --- | --- |
| start and end | `internal` |
| no start, end | `leading` |
| start, no end | `trailing` |
| neither | `both_ends` |

Examples:

- `PANA...OL` -> internal
- `...TRIL` -> leading
- `RIVO...` -> trailing
- `...VOT...` -> both ends
- `...VOT...IL` -> leading, because the final visible fragment remains end-anchored

### 15.3 Safe shorthand without a marker

Space-separated shorthand becomes a visual-gap pattern only when:

- there are 2--4 ASCII alphabetic tokens;
- each token has length >=2;
- the text contains no digit; and
- concatenating fragments is not already an exact family whose normalized spelling equals the query.

This preserves ordinary exact multiword catalog names. Accepted shorthand is start- and end-anchored with `explicit=false`; unlike explicit gaps, it may represent a zero-character internal gap. Thus shorthand `PANA DOL` may still retrieve exact PANADOL.

### 15.4 Match targets

Every Algorithm 5 rescue family contributes:

- complete compact family name;
- compact family head when different.

Results deduplicate by the exact `family.compact` key, not the broad variant-group key. This is a clinical/product-selection boundary: BRUFEN, BRUFEN COLD, and BRUFEN FLU may share display grouping but remain independent matched bases. For visual rows, `result_name()` returns `matched_family_name`; downstream tests/evaluators must use that exact identity rather than `name`/`variant_group`.

### 15.5 Match stages

1. **Raw ordered fragments.** Every fragment must occur in order. Requested anchors must hold. Every explicit inter-fragment, leading, or trailing gap requires at least one hidden target character. Search begins after a forbidden zero-gap occurrence and may use a later valid occurrence instead of stopping at the first occurrence.
2. **Grapheme-equivalent ordered fragments.** Applied only when raw matching fails. Every explicit edge and inter-fragment gap is enforced here too.
3. **Direct bounded OCR-grapheme patterns.** Applied only when raw and grapheme-equivalent matching fail. `visual_gap_confusion_patterns()` rewrites the visible fragments once per query through Algorithm 5's directional `GRAPHEME_CONFUSION_RULES`, then asks for an exact ordered-fragment match against each target. The cost and operation count are shared across every fragment:
   - total visible length 5--7: maximum one confusion and cost `1.00`;
   - total visible length 8--24: maximum two confusions and cost `1.40`;
   - direct confusion is disabled above `MAX_VISUAL_GAP_CONFUSION_VISIBLE_CHARACTERS = 24`;
   - each intermediate pattern set is sorted deterministically and capped by `VISUAL_GAP_CONFUSION_PATTERN_LIMIT = 512`;
   - rewritten output is not rewritten again, so a single original glyph cannot acquire a transitive `I -> E -> G` interpretation;
   - every explicit leading, internal, and trailing marker still requires a nonzero hidden span.
4. **Ordinary one-edit alignment.** Applied only when all three earlier stages fail, total visible length >=5, and every fragment has length >=2. Anchored edge fragments must first fit within one ordinary Levenshtein edit. `ordered_fragment_edit_distance()` then shares a single ordinary insertion/deletion/substitution budget across all fragments and advances at least one target character across every explicit gap. A precomputed fuzzy minimum target length accounts for one possible deletion plus every required gap. Any explicit-gap target whose length is no greater than the original visible-character count is rejected, and the exact-length leading/trailing edge guards remain.

Both direct-confusion and ordinary fuzzy tolerance require at least five total visible characters. For one-to-four visible characters, raw and fixed grapheme-equivalent matching remain available but no directional confusion pattern or ordinary edit may be claimed. Direct confusion additionally stops above 24 visible characters. Eight focused short-pattern guards enforce the lower floor; the 24-character stress case and four-fragment parser ceiling bound the upper/combinatorial edge.

`minimum_fragment_target_length()` supplies a cheap lower bound: sum of fragment lengths, plus one for each explicit inter-fragment gap, plus one for each unanchored explicit edge. Raw, grapheme-equivalent, and each direct-confusion pattern use their own lower bound. `literal_anchor_match_possible()` also rejects a target that cannot literally start/end with anchored fragments before calling the occurrence matcher. These are performance prechecks; they do not weaken the full gap constraints.

`visual_grapheme_key()`:

```text
PH -> F
CK -> K
QU -> K
GH -> G
C  -> K
Q  -> K
collapse adjacent repeats
```

At committed endpoint `66abb7f`, the grapheme-equivalent call did not pass `require_edge_gap`, so a grapheme-normalized alignment could accept a zero-character explicit edge gap; internal markers could also collapse to zero characters. The provisional source passes `require_edge_gap=pattern.explicit` at the raw, grapheme-equivalent, direct-confusion, and ordinary-fuzzy stages and advances the next fragment start by one for every explicit internal gap. The current regression source contains **nine** strict-edge and three strict-internal negatives; deployment status remains provisional until this working tree is committed and deployed.

### 15.6 Visual-gap sort order

Per exact family, retain the match with the smallest tuple:

1. raw (`0`), grapheme-equivalent (`1`), direct confusion (`2`), or ordinary fuzzy (`3`);
2. visible edit distance;
3. grapheme-confusion count;
4. hidden character count;
5. descending visible coverage;
6. family head before complete name;
7. complete family length;
8. case-folded family name.

Exact-family results then use that tuple, broad display-group name, exact family name, and exact compact family key.

### 15.7 Visual-gap safety response

- decision type: `visual_gap_matches`
- status: ambiguous when results exist, otherwise no match
- all rows: low confidence, `needs_clarification=true`, `confirmation_required=true`
- response: `confirmation_required=true`
- estimated correctness probability: `0.0`
- calibrated likely match: false
- reasons disclose ordered-fragment, full/head target, grapheme equivalence, bounded visible-edit evidence, and custom-grapheme evidence
- rows disclose rounded `visible_edit_distance` (four decimals) and `grapheme_confusion_count`
- reason `visual_gap_bounded_visible_edit` replaces the older `visual_gap_one_visible_edit`; direct-confusion rows also add `visual_gap_grapheme_confusion`
- `candidate_id` is `ALG6-GAP-{family.compact}`; `commercial_name`, `matched_family_name`, and `matched_family_key` identify the exact matched base, while `name`, `candidate_canonical_name`, and `variant_group` preserve the broad display grouping
- `result_name()` resolves a visual result to `matched_family_name`, so API enrichment, evaluations, and product-context scoring retain exact base identity

## 16. Committed product-context behavior through `703c262`

This section records the last committed exact-strength reranker behavior. Section 17 records the newer provisional working-tree implementation.

Committed behavior:

- Parse strengths requiring explicit units.
- Normalize mass/volume/IU/percent measurements.
- Parse form, route, release, and a limited pack count.
- Score every product within each already-retrieved family group.
- Select one product per group.
- Allow exact normalized strength to reorder groups using a 14-point penalty per original name position.
- Do not allow form-only evidence to reorder family groups.
- Preserve original family decision as `name_decision_type` and report `product_context_selection`.

The verified example was `javaki` plus `5 mg`, where exact 5 mg product evidence promoted JAKAVI over conflicting JAVA cream. The recorded 200-case comparison was name baseline 197/200 and context reranker 200/200.

## 17. Current-source provisional product-context rules

**Status: present in the uncommitted working tree inspected while this document was written. Do not call these rules deployed or accepted until tests and endpoint verification are complete.**

### 17.1 Product-context normalization

`normalize_context()`:

1. Convert Arabic digits to ASCII.
2. Normalize both Arabic decimal/thousands separators (`٫`, `٬`) and both micro symbols (`µ`, `μ`), with micro becoming `U` for later unit parsing; normalize numeric multiplication signs `*`/`×` to `X` only when they occur between digits.
3. Uppercase.
4. Replace Arabic terms:
   - `ميكروجرام -> MCG`
   - `مجم`, `ملجم -> MG`
   - `جرام`, `جم -> G`
   - `مل -> ML`
   - tablet, capsule, syrup, and injection terms to English aliases.
5. Before general punctuation cleanup, normalize dotted release/label modifiers: `H.G.` means hard gelatin rather than hours; dotted or abbreviated extended/prolonged, sustained, modified, controlled, and `XR` release forms map to their canonical release tokens.
6. Normalize dotted units even when attached to numbers: `M.I.U. -> MIU`, `I.U. -> IU`, `M.G. -> MG`, `G.M. -> G`, `M.L. -> ML`, and `U.G. -> MCG`.
7. Collapse whitespace-grouped activity thousands only when immediately followed by `MIU`, `IU`, `UNIT(S)`, or `U`.
8. Rewrite `ddd.ddd IU` as an IU thousands form only when the first group has one through three digits and the second has exactly three. Thus Egyptian `200.000 I.U.` becomes `200000 IU`, while `1.2 G`, `0.5 MG`, and `0.125 MG` remain decimals.
9. Expand English long unit names, including micrograms, microlitres, milligrams, millimoles, milliequivalents, kilograms, grams, millilitres, litres, and `UNIT(S) -> IU`.
10. Normalize dotted film-coated token, `I.V.`, and `I.M.`.
11. Treat a comma preceded by a nonzero integer and followed by exactly three digits as a thousands separator; treat a comma between other digits as a decimal separator; turn remaining commas into spaces. This preserves `600, tablets` as a visible unitless 600 while `0,125 mg` becomes `0.125 mg`.
12. Retain only `A-Z`, digits, `%`, `.`, `/`, `:`, `+`, and normalized spaces. Leading-dot decimals such as `.5 MG` remain parseable.

### 17.2 Units and canonical measurements

Aliases:

- `UG -> MCG`
- `MCL -> UL`
- `GM -> G`
- `U -> IU`
- `UNIT`, `UNITS -> IU`
- `MIU -> MIU`
- `HR`, `HOUR`, `HOURS -> H`

Canonical factors:

| Unit | Kind | Factor |
| --- | --- | ---: |
| MCG | mass | 1 |
| MG | mass | 1,000 |
| G | mass | 1,000,000 |
| KG | mass | 1,000,000,000 |
| UL | volume | 0.001 |
| ML | volume | 1 |
| L | volume | 1,000 |
| IU | activity | 1 |
| MIU | activity | 1,000,000 |
| MMOL | substance | 1 |
| MEQ | equivalent | 1 |
| H | time | 1 |
| `%` | percent | 1 |

`Measurement` equality/order uses canonical kind/value and denominator kind/value. `observed_value` and `observed_unit` are excluded from equality so `1 G == 1000 MG`, while retaining the typed/catalog number for unitless comparison.

### 17.3 Strength parsing

`UNIT_PATTERN` is `MCG|MCL|UG|MG|GM|KG|MMOL|MEQ|MIU|UNITS|UNIT|IU|UL|ML|G|L|U|%`. Unit matches require a non-letter boundary after the token. Denominators additionally accept `HR`, `HOUR(S)`, and `H`, which canonicalize to time.

`STRENGTH_RE` recognizes an amount+unit and optional denominator amount+unit. Denominator amount defaults to 1 when omitted, so `200 IU/ML` records a denominator of one millilitre.

`COMBINATION_STRENGTH_RE` recognizes two or more slash-separated numeric components followed by one non-volume dose unit, for example `5/10 MG`. Its current unit alternatives are `MCG|UG|MG|GM|KG|MMOL|MEQ|UNITS|UNIT|IU|G|U|%`; it excludes `UL`, `ML`, and `L` as shared combination units. Every component is preserved; a tuple and `Counter` are used rather than a set, so repeated components are not lost.

`EXPLICIT_COMBINATION_RE` first recognizes components that each carry a unit, such as `5 MG/500 MG` and `70 MG/2800 IU`. When the final unit is `UL`, `ML`, `L`, `G`, `KG`, or time `H`, the expression remains an ordinary concentration/presentation ratio rather than a multi-active signature. Other explicit-unit combinations retain every component.

`SHARED_DENOMINATOR_COMBINATION_RE` preserves each qualified numerator in forms such as `2 MG + 5 MG/ML`; `SHARED_SHORTHAND_DENOMINATOR_RE` applies one dose unit and one common denominator to shorthand such as `2/5 MG/ML`. Explicit shared-denominator combinations are parsed before other combinations so the denominator is attached to every active component.

Explicit-unit combinations, shared-unit combinations, and shared-denominator combinations are masked before ordinary strengths/ratios are parsed from what remains. This prevents double counting while preserving repeated components such as `125/125 MG`. `UNIT_DOSE_PACKAGE_RE` is masked before strength parsing, so `20 UNIT DOSES` is a package count rather than a 20-IU active strength.

`STRUCTURAL_RATIO_RE` separately preserves bare non-unit ratios of one-to-six digits on each side, with `/` or `:` retained in the identity. It does not fire when a dose unit follows. This distinguishes clinically meaningful label structures such as insulin `30/70` and dilution `1:100000` from strength fractions.

### 17.4 Number classes

`MAX_PLAUSIBLE_PACKAGE_COUNT = 400`.

The query parser separates:

- **qualified strengths**: number with a recognized unit;
- **presentation quantities**: every non-ratio volume, plus non-ratio mass when a topical form is present;
- **explicit package counts**: positive one-to-four-digit number followed by `pack`, `packet`, `box`, `bottle`, `piece`, `pcs`, or `pen`; the explicit word overrides the 400-count heuristic ceiling, so `500 pack` is accepted as a package count;
- **multipack counts**: positive one-to-four-digit `outer X inner` or `outer * inner` followed by a recognized dosage form becomes one explicit count equal to `outer*inner`;
- **unit-dose package counts**: `N UNIT DOSES` or `N IU DOSES` becomes package count `N` and is removed from the strength parser;
- **ambiguous numbers**: number <=400 before recognized dosage-unit syntax;
- **bare numbers**: other standalone numbers, plus a number >400 before a dosage-unit form.

`PACKAGE_FORM_RE` permits up to six intervening label modifiers, including film coating, chewable/dispersible/oral, soft/hard gelatin, vegetarian, prefilled, age, route, release, effervescent/granule, `IN`, and `OF`, before an expanded form/container list. This is why `600 tab` becomes bare numeric evidence rather than a package of 600 tablets, while `20 tabs` remains an ambiguous count/package candidate and `30 H.G. CAPS` remains a capsule count rather than a time denominator.

Qualified measurements, structural ratios, explicit package expressions, multipacks, and unit-dose packages are masked before remaining bare numbers are collected. `NUMBER_RE` requires that neither adjacent character be a letter, digit, or dot; `PACKAGE_FORM_RE` likewise refuses a preceding letter/digit/dot. This prevents the fractional tail of `1.2 vial`/`0.5 tablet` and the numeric part of attached brand tokens such as `D3` from being reparsed as product context.

Zero explicit measurements, and explicit ratios with a zero denominator amount, are dropped from ordinary parsed strengths but set `invalid_numeric=true`. That flag is itself context evidence and makes every product incompatible with `invalid_numeric_evidence`; `0 mg tab` therefore fails closed instead of degrading into a form-only query.

### 17.5 Form aliases

| Canonical form | Accepted tokens |
| --- | --- |
| tablet | `TAB`, `TABS`, `TABLET(S)`, `CAPLET(S)`, `FCT`, `PILL(S)` |
| chewable tablet | `CHEWABLE`, `CHEW` |
| dispersible tablet | `DISPERSIBLE`, `DIS` |
| capsule | `CAP`, `CAPS`, `CAPSULE(S)` |
| syrup | `SYRUP`, `SYP` |
| suspension | `SUSP`, `SUSPENSION` |
| drops | `DROP(S)` |
| vial/ampoule/syringe/pen/cartridge | Each container name and plural keeps its own canonical container; it is not collapsed into generic injection. |
| injection | `INJ`, `INJECTION`, `SC`, `INFUSION` |
| cream/gel/ointment/lotion/shampoo | Corresponding names plus `OINT`. |
| powder/spray/suppository/sachet | Corresponding names plus `SUPP`. |
| effervescent | `EFF`, `EFFERVESCENT` |
| granules | `GR`, `GRAN`, `GRANULE(S)` |
| solution | `SOL`, `SOLUTION` |
| ovule | `OVULE(S)` |
| patch | `PATCH(ES)` |
| inhalation | `INHALER`, `INHALATION`, `NEBULE(S)` |
| sublingual | `SUBLINGUAL` |

Specific oral-solid forms are tablet, chewable tablet, dispersible tablet, capsule, sachet, effervescent, and granules. Topical forms are cream, gel, ointment, lotion, and shampoo.

### 17.6 Route and release aliases

Routes:

- injection subtypes: `IV`/intravenous -> `iv`, `IM`/intramuscular -> `im`, `SC`/subcutaneous -> `sc`; the generic product form `injection` remains separately compatible with a subtype when no conflicting subtype is known
- oral: ORAL/PO
- topical
- ophthalmic/ocular
- nasal
- vaginal
- rectal
- inhalation
- sublingual

Release:

- controlled: `CR`, `CONTROLLED`
- extended: `ER`, `XR`, `XL`, `EXTENDED`
- sustained: `SR`, `SUSTAINED`
- modified: `MR`, `RETARD`, `CHRONO`, `PROLONGED`, `MODIFIED`

### 17.7 Presentation classification

`is_presentation_measurement()` never treats a ratio as presentation size. It treats:

- every non-ratio volume as presentation, regardless of form/route metadata;
- a non-ratio mass as presentation when a topical form is present.

This separates values such as `50 G cream` or `80 ML suspension bottle` from dose strength.

### 17.8 Catalog product evidence construction

`product_evidence()`:

- parses product name independently from metadata;
- splits `st` on semicolons;
- parses the first `st` component as primary evidence;
- parses every later `st` component as a measurement and classifies presentation-shaped values separately;
- prefers all strengths parsed from the commercial name whenever the name contains any strength, because names often contain fuller combination or microlitre concentration signatures than `st`;
- only appends non-presentation secondary `st` measurements when the name itself has no strengths;
- adds raw lowercased `f` only to forms and raw lowercased `r` only to routes;
- combines name and metadata form/route/release evidence;
- reclassifies topical/liquid presentation measurements out of strengths;
- deduplicates presentation measurements while retaining deterministic order;
- uses package counts parsed from the commercial name;
- never creates bare or ambiguous query-style numbers for a catalog product.

This fixes the earlier behavior that added both raw `f` and raw `r` into both sets.

The shared `parse_evidence()` semicolon rules are deliberately structural:

- when an earlier semicolon part contains a dose and a later part contains only standalone mass/volume, the later measurement is presentation metadata rather than another active strength;
- a flattened three-part pattern such as `10.8G;100ML;100ML` is reconstructed as active concentration `10.8G/100ML` plus one `100ML` presentation, but only when the first component is one non-ratio strength and the first later mass/volume value repeats in another later part;
- a standalone `N UNIT`/`N IU` in a later semicolon part becomes package count `N` and the duplicate activity measurement is removed from strengths.

These rules prevent catalog metadata from creating false active-strength components while preserving the first dose signature and later bottle/pack evidence.

### 17.9 Complete strength score

`Counter(query.strengths)` is compared with `Counter(product.strengths)`:

| Condition | Score/evidence | Compatibility |
| --- | --- | --- |
| Counters exactly equal | `+130 + 10*(component_count-1)`, `strength_exact` | Exact signature; numeric match. |
| Product contains every query component but has extras | `+55`, `strength_component_match`, `strength_signature_incomplete` | Compatible but incomplete query. |
| Exactly one query and one product concentration reduce to the same canonical numerator-per-denominator ratio, but their explicit totals differ | `+70`, `strength_concentration_equivalent`, `strength_total_differs` | Compatible numeric evidence, never an exact signature. |
| Same numerator kind/value exists and no explicit denominator conflict | `+35`, `strength_numerator_only`, incomplete signature | Compatible numeric evidence. |
| Product has strength but signature conflicts | `-120`, `strength_conflict` | Incompatible. |
| Product has no strength metadata | `-35`, `strength_unknown` | Not automatically incompatible. |

An explicit denominator conflict exists only when both sides have denominators and kind/value differ.

The `strength_numerator_only` branch is allowed only when at least one numerator kind/value overlaps, neither side proves a denominator conflict, and neither query nor product is a multi-component combination. A partial combination therefore cannot masquerade as numerator-only compatible evidence.

Exact comparison intentionally preserves explicit totals before reduced-ratio equivalence. For example, `100 MG/4 ML` and `400 MG/16 ML` have the same reduced concentration but do not tie as `strength_exact`.

Before strength scoring, `invalid_numeric=true` records `invalid_numeric_evidence` and makes the product incompatible. Structural ratios are scored independently: every query ratio present in the product adds `+70`, `structural_ratio_match`, and numeric evidence; a known conflicting product ratio adds `-90` and is incompatible; a product with no matching ratio records `structural_ratio_unknown` and is also incompatible.

### 17.10 Unitless and ambiguous numeric score

Catalog comparison uses each measurement's `observed_value`, not its canonical converted value. For every bare number:

| Match target | Score/evidence |
| --- | --- |
| Strength observed number | `+85`, `unitless_strength_match` |
| Package count | `+60`, `unitless_package_match` |
| Presentation observed number | `+45`, `unitless_presentation_match` |
| No match while catalog has known numbers | `-85`, `unitless_number_conflict`, incompatible |

For every ambiguous number from dosage-unit syntax:

| Match target | Score/evidence |
| --- | --- |
| Package count | `+75`, `ambiguous_number_package_match` |
| Strength observed number | `+55`, `ambiguous_number_strength_match` |
| Presentation observed number | `+35`, `ambiguous_number_presentation_match` |
| No match while catalog has known numbers | `-60`, `ambiguous_number_conflict`, incompatible |

Priority is package, then strength, then presentation for ambiguous numbers; bare numbers prioritize strength, then package, then presentation.

### 17.11 Presentation, form, route, release, and package score

- All requested presentation measurements contained: `+55`, `presentation_quantity_match`.
- Presentation conflict when product has presentations: `-55`, incompatible.
- Exact form overlap: `+45`, `dosage_form_match`.
- Compatible broad/specific form relation: `+20`, `dosage_form_compatible`.
- Specific form conflict: `-45`, incompatible.
- Route match: `+35`; a generic injection/subtype-compatible relation adds `+15`, `route_compatible`; two known, disjoint injection subtypes or another known route conflict add `-35`, incompatible; missing route metadata records `route_unknown` and is incompatible for an explicit route query.
- Release match: `+35`; known release conflict: `-35`, incompatible; missing release metadata records `release_type_unknown` and is also incompatible, without fabricating a specific conflicting release type.
- Package-count match requires **every** requested package count to occur in the product set and adds `+20`; any known conjunction conflict adds `-20` and is incompatible; missing package metadata records `package_count_unknown` and is incompatible. An ambiguous dosage-form number may still be scored through its separate ambiguous-number branch, but it does not weaken an explicit package conjunction.

Form compatibility:

- two different specific oral/topical forms conflict;
- two different explicit injection containers among vial, ampoule, syringe, and pen conflict;
- a specific oral-solid form is compatible with broad `oral_solid`;
- a specific topical form is compatible with broad `topical`;
- otherwise any known non-`unknown` product form conflicts.

### 17.12 Compatible product selection and ties

`result_family_key()` defines the scoring identity. It returns a visual row's exact `matched_family_key`; every other row uses compact `name`. Broad variant groups are never a product-admission key.

A separately supplied exact medicine name is a hard boundary in nonvisual mode: if any returned row's compact `name` exactly equals compact `name_query`, all other name families are removed before context scoring. Product details may choose a presentation inside that exact family but cannot jump to a rank-two family that happens to share `500`, `600`, or another detail. Legacy combined queries are not treated as exact here because their trailing detail remains in `name_query`.

For a nonexact ordinary name, context admission is deliberately narrow:

- `CONTEXT_FAMILY_ADMISSION_LIMIT = 3`; rank four and later can never become a context-selected family;
- the first exact base family is admitted automatically;
- ranks two and three require at least one available name diagnostic (`raw_edit_distance` or `consensus_levenshtein_similarity`);
- every available diagnostic must pass: raw edit <=`CONTEXT_FAMILY_MAX_RAW_EDIT_DISTANCE = 2.0` and Levenshtein similarity >=`CONTEXT_FAMILY_MIN_LEVENSHTEIN_SIMILARITY = 0.60`;
- a missing one of the two diagnostics is allowed only when the other exists and passes.

Visual-gap mode structurally admits the first three **exact matched bases** without requiring ordinary name diagnostics. Prepared numeric-only and numeric-brand alias modes admit every exact alias family, bypassing the ordinary top-three/diagnostic gate. Neither exception opens a broad variant sibling.

A catalog product in an admitted family is eligible only when:

- `compatible` is true;
- score >0; and
- at least one match reason exists; and
- if the query has any numeric evidence (qualified strength, bare/ambiguous number, presentation quantity, or package count), that product has `numeric_match=true`.

Qualified mass/volume evidence receives one tightly scoped presentation reinterpretation. When all qualified query measurements are non-ratio mass/volume, a compatible product has no dose strengths, and the complete qualified-measurement `Counter` exactly equals that product's presentation-quantity `Counter`, the product receives `+130`, `qualified_presentation_exact`, `exact_strength_signature=true`, and `numeric_match=true`. This lets exact `100 g`/`50 g` topical presentations beat a close name alternative even when the query omits the form. It does not apply to bare unitless `100`/`50`: a bare presentation-number match remains the weaker `+45 unitless_presentation_match` and, without form, cannot trigger cross-family reorder.

Within each admitted exact base family:

- find maximum score;
- retain all products tied at that score;
- emit at most six tied products;
- copy the catalog row's stable `id` into `selected_product_id` whenever present, in addition to the legacy normalized `selected_product_key`;
- retain original exact-family name evidence and name rank;
- report `ambiguous_products` and the full tie count when more than one ties.

If an exact family has no catalog records, its first original family row remains unmatched. If it has records but no eligible product, only its first original family row is retained and marked `context_match_status=no_compatible_product`. This row is not presented as a selected catalog product. Output first reserves one best row per output family, then appends additional tied products up to the API limit so one family's ties cannot hide another family.

No alphabetical tie-break silently chooses one product anymore. Two catalog rows with the same normalized commercial name remain separate selections when their stable IDs differ.

### 17.13 Cross-family reorder

Each exact family retains its original zero-based name position. `strong_context_selection` becomes true when any of these independent gates holds:

1. at least one matched family has a complete exact strength signature, including the qualified-presentation-exact reinterpretation above;
2. there is no qualified strength, the query contains bare/ambiguous numbers plus a form, exactly one family is compatible, and it has numeric evidence;
3. parsed presentation quantity **plus form** matches a numeric product with exact/compatible dosage-form evidence; or
4. the input is a prepared exact numeric-only/numeric-brand catalog alias.

For ordinary/visual families, strong selection sorts matched families before unmatched, then descending `context_score - 14*original_position`, then original position. Every original name-rank step therefore costs 14 context points. For exact catalog-alias families, prepared alphabetical order is not name-proximity evidence, so the 14-point penalty is removed: families sort by matched status, descending product-context score, then original prepared position. When strong selection is active, only matched families are returned. Form alone, presentation alone without the required strong gate, and a bare unitless presentation number without form do not reorder families.

### 17.14 No-compatible-product response

If context is present but Algorithm 6 returns no family, or no **admitted exact family** has a compatible positive matched product:

- return decision `product_context_no_compatible_product`;
- preserve original name decision as `name_decision_type`;
- status is ambiguous when name results exist, otherwise no match;
- preserve only admitted exact-family name results when they existed; rejected distant/rank-four families are not exposed as context failures;
- annotate each preserved row with `context_match_status=no_compatible_product`, empty `matched_context`, and `context_conflicts=product_context_no_compatible_product`;
- do not present an incompatible catalog product as if it matched;
- ask the user to check number/unit or add dosage form.

If the parsed product-context evidence is empty, `rerank_products()` returns the Algorithm 6 response unchanged. The API passes `name_query=query` separately so the short-prefix exception can inspect only the visible medicine name.

API display enrichment recognizes `context_match_status=no_compatible_product`. It suppresses product/family catalog hydration for that row, uses the family name as `commercial_name_en`, and leaves Arabic/product metadata empty/default rather than attaching a conflicting product merely for display.

### 17.15 Exact numeric commercial aliases and numbered-brand guards

There are four generic, catalog-derived guards/rescues; none is a hard-coded medicine alias. They run only when `explicit_product_context=false`, and the first three are completely bypassed for `visual_gap_matches`. Their fixed precedence is:

1. prepared exact numeric-brand alias (`numeric_commercial_brand_alias_response()`);
2. prepared exact numeric-only alias (`numeric_commercial_alias_response()`);
3. exact numeric commercial prefix among already-retrieved exact families (`context_after_numeric_commercial_brand_prefix()`);
4. later exact attached-number name protection.

An alias remainder is accepted only by `context_suffix_is_fully_recognized()`. It must be nonempty product evidence and **every alphabetic token** must be a known unit/factor alias, form, route, release token, one of `PACK PACKS PACKET PACKETS BOX BOXES BOTTLE BOTTLES PIECE PIECES PCS PEN PENS`, or one of the fillers `AND COATED DIS DOSE FC FOR IN OF PER RELEASE`. Numbers and punctuation are permitted. Mixed suffixes such as `junk 20 tab`, `600 tab unknown`, and similar partially recognized strings block alias rescue instead of silently discarding the unknown word.

**Prepared numeric-brand alias.** The catalog key contains one or more leading numeric tokens followed by the exact base-family tokens, for example `3 FLY`. The query must begin with an exact prepared key; when several keys match, the globally longest token sequence wins. This path runs before numeric-only aliases, so `1 2 3 ONE TWO THREE 20 tab` chooses the longer exact number-plus-family identity rather than reopening both `1 2 3` families. It maps exact base-family keys, never fuzzy/global results.

With no remainder, one unique alias family preserves the original Algorithm 6 response only when that family is already the original top exact family. Otherwise the function returns capped low-confidence, ambiguous, confirmation-required rows with decision `numeric_commercial_brand_alias_matches`, source/name match `exact_numeric_brand_alias`, full `candidate_count`, and `numeric_commercial_brand_alias`. With a recognized remainder, every alias family is passed to normal product filtering using `explicit_product_context=true`; output is capped at `limit`, stays ambiguous/confirmation-required, retains the ordinary `product_context_selection` or `product_context_no_compatible_product` decision, and sets `name_decision_type=numeric_commercial_brand_alias_matches`. Thus `3 FLY 600 tab` selects only `3 FLY 600 MG 20 TABS.` while `3 FLY` preserves the appropriate original FLY name decision.

**Prepared numeric-only alias.** The whole query must begin with at least two contiguous numeric tokens. The function tries the longest numeric prefix down to length two and requires an exact lookup in `numeric_alias_groups`. It can repair an empty Algorithm 6 result or replace/expand an incomplete one. It never indexes a single number, performs a fuzzy numeric match, or scans arbitrary families at request time; `1 2 9` therefore does not become `1 2 3`.

With no remainder it returns at most `limit` exact alias families in prepared order, while `candidate_count` remains the full family count. Unlike short-prefix rescue, alias overflow is capped rather than converted to a too-broad abstention. With a recognized remainder, **all** exact alias families enter product filtering before the public result cap and bypass ordinary top-three admission. Product-context score, not prepared alphabetical position, determines their order. Selection becomes `numeric_commercial_alias_product_context_selection`; all-conflict failure becomes `numeric_commercial_alias_no_compatible_product`; both preserve `name_decision_type=numeric_commercial_alias_matches`, full family `candidate_count`, and the matched alias. Failure rows are capped to `limit` too. Real `1 2 3` exposes both ONE TWO THREE and ONE TWO THREE EXTRA; `1 2 3 20 tab` filters products in both exact bases.

**Retrieved-family prefix fallback.** If neither prepared response fires, `context_after_numeric_commercial_brand_prefix()` examines only products under exact families already returned by name search. It accepts an exact `leading number(s) + base family` prefix, or the leading numbers alone only when there are at least two. It chooses the longest accepted alias across all retrieved records, requires the same fully recognized suffix rule, strips the alias, and leaves genuine trailing detail for ordinary context scoring. Because it uses `result_family_key()` plus `records_by_family`, it neither opens a global family nor crosses a broad variant sibling.

**Exact attached-number guard.** After those prefix paths, if no separate context field was supplied, parsed evidence consists only of bare numbers, and a returned result exactly equals compact full `name_query`, the response is returned unchanged. This protects literal names such as `D3`, `A1`, and `V2` from reinterpretation as strength. Explicit product context bypasses all legacy combined-query name-number protections and is interpreted as product evidence as requested.

### 17.16 Strict one/two-character prefix recovery

The provisional `short_prefix_context_response()` is the other context-assisted candidate-generation exception alongside exact numeric commercial aliases. It is never invoked in visual-gap mode.

It activates only when:

- `name_query` compact length is 1 or 2;
- there is numeric evidence: qualified strength, bare/ambiguous number, presentation quantity, or explicit/parsed package count; and
- there is structural evidence: form, route, or release.

It then scans **exact base families** whose exact family display compact strictly starts with the visible prefix. Broad variant groups do not fold the count. A product must:

- be compatible;
- score >0;
- have a numeric match; and
- when a query form exists, have exact or compatible form evidence.

Outcomes:

- no family -> `context_assisted_prefix_no_match`, no products;
- more exact base families than requested `limit` -> `context_assisted_prefix_too_broad`, no products, ask for more letters;
- one through `limit` exact base families -> `context_assisted_prefix_candidates`, ambiguous, low confidence, confirmation required.

Families sort by descending context score then exact family name. Up to six best tied products are prepared per family. Output first reserves one result from every admitted family, then spends remaining result slots on that family's additional tied products in family order. This prevents one family's product variants from consuming the API limit before another admitted family is shown. This is a strict prefix filter, not fuzzy recovery, and it never admits more exact families than the API limit. A short visual query such as `BR...` cannot dispatch this global prefix scan.

### 17.17 Product-context response payload

The response discloses:

- canonical strengths
- bare numbers
- ambiguous numbers
- presentation quantities
- forms
- routes
- release types
- package counts
- structural ratios
- the `invalid_numeric` fail-closed flag
- candidate product count
- compatible exact-family count (the payload key remains `compatible_groups` for compatibility)
- whether family order changed
- name rank/name for each selected product
- product context score/rank
- match and conflict reasons
- tie status/count
- exact numeric-only or numeric-brand commercial alias, when the corresponding legacy rescue path activated
- exact alias row source/match type, full pre-cap candidate count, and alias-specific name/product decision types
- exact visual `matched_family_name`/`matched_family_key` retained through product selection
- stable `selected_product_id` on an actually selected catalog row, when the row has an ID; duplicate normalized commercial names therefore remain distinct

## 18. UI rules

### 18.1 Inputs

- Medicine-name field is required by UI behavior.
- It accepts ordinary text and visual-gap markers.
- Product-details field is optional.
- Current provisional placeholder is `600, 500 mg, tablets, 24 pack`.
- Spellcheck and autocapitalization are disabled; direction is automatic.

### 18.2 Request behavior

- Auto-search debounce: 420 ms.
- Auto-search starts only when the trimmed medicine name has at least three characters; shorter names can still be submitted explicitly.
- Active request is aborted when a newer search begins.
- A monotonically increasing sequence prevents an older completed response from rendering after a newer request.
- Cache contains at most 24 responses.
- On inserting the 25th response, the oldest Map entry is deleted; cache hits do not refresh recency.
- Cache key uses runtime mode plus a JSON tuple of the **trimmed raw** medicine name and product context. The last-completed suppression key uses the same raw tuple without runtime mode. This intentionally preserves visual-marker semantics: `PANA DOL`, `PANA...DOL`, `PANADOL`, and `...PANADOL` cannot collapse to one cached response.
- Normal submit forces a new search, bypassing both last-completed suppression and cache reuse.
- Algorithm 6 mode sends separate JSON fields.
- Algorithm 6 requests always send `limit:20`, require an HTTP-success response, and then require `algorithm=algorithm_6`.
- Browser mode concatenates the fields and selects its own `parts` unreadable mode only when the visible medicine field matches two or more periods or any `*`/`?`; this UI trigger is not the same marker grammar as Python Algorithm 6.
- Clearing the medicine field also clears product context, aborts search, resets summaries/results, and focuses the name field. Clearing product context alone invokes the ordinary input handler and may schedule a new search.
- Escape activates the relevant clear button for either input.
- During search, the button is disabled, `aria-busy` is set, and a loading skeleton is shown only when there are no existing result children.

### 18.3 Result display

- The UI initially shows ten result groups and offers “show more.”
- Result groups use `family_group_key`, falling back to base group and then English commercial name; displayed ranks are group ranks, not necessarily raw row ranks.
- API product ties are grouped first by stable `selected_product_id`, then by `selected_product_key`, commercial name, or base family. Duplicate normalized product names remain separate UI variants when their catalog IDs differ.
- A family group with more than one unique displayed product renders at most six radio-button variants even if more rows exist; each radio value uses `selected_product_id` when available, otherwise the commercial name. Selecting one only changes the visual selected state and sends no server mutation.
- Evidence labels include exact/component/numerator strength, unitless strength/package/presentation, ambiguous-number interpretation, presentation size, exact/compatible form, route, release, and package count.
- A tie message reports equally supported product count.
- A preserved name-only row with `context_match_status=no_compatible_product` receives a `product details conflict` badge and explicitly says no catalog product in the family matches all supplied details.
- All result summaries tell the user to confirm the medicine.
- Warning flags and confirmation badges remain visible.
- All interpolated catalog/query text passes through HTML escaping; warning/route/form labels are mapped to human-readable text before rendering.
- When there are no result rows, the UI suggests trying the brand only, removing strength, or using the Arabic name.

Provisional decision summaries include:

- `product_context_no_compatible_product`
- `numeric_commercial_alias_matches`: exact numeric text matches multiple commercial-name families; compare all candidates
- `numeric_commercial_alias_product_context_selection`: numeric commercial-name matches were filtered by trailing product details
- `numeric_commercial_alias_no_compatible_product`: numeric commercial-name matches conflict with trailing product details
- `context_assisted_prefix_candidates`
- `context_assisted_prefix_no_match`
- `context_assisted_prefix_too_broad`

## 19. Warnings and safety

Catalog warning examples include missing composition, unknown route, name-status markers, missing manufacturer/class, route/name conflict, duplicate/conflict, metadata rows, and price outliers.

The UI has explicit warning labels for:

| Flag | Display |
| --- | --- |
| `NON_MEDICINE_OR_METADATA` | Not a medicine record |
| `UNKNOWN_ROUTE` | Unknown route |
| `MISSING_COMPOSITION` | Missing composition |
| `ROUTE_CONFLICT` | Route conflict |
| `QUALITY_REVIEW` | Review |
| `ILLEGAL_IMPORT` | Illegal import |
| `CANCELLED` | Cancelled |
| `N/A` | N/A |

An unknown flag is rendered by replacing underscores with spaces, lowercasing, then title-casing word initials; it is not discarded.

In the Python Algorithm 5 path:

- warnings add `catalog_warning`;
- warnings force clarification;
- `score_family()` does not apply a numeric warning penalty;
- API display enrichment exposes the raw warning string.

Generic documentation saying warnings “may down-rank” is not an exact description of the current Python Algorithm 5 score. The browser fallback has its own warning behavior.

This application is ranked retrieval, not prescribing, substitution, dispensing authorization, or diagnosis. Every path must remain confirmation-required unless an independently reviewed product requirement changes the safety contract.

## 20. Tests and acceptance invariants

### 20.1 Existing committed focused tests

`app/test_product_context_reranker.py` currently covers:

- `1 gm == 1000 mg`
- `1.2 g == 1200 mg`
- dotted units and film-coated tablet syntax
- strength+tablet product selection
- vial/injection selection
- ratio suspension selection
- same-family JAKAVI 5 mg/56 tablets
- name-only reranker bypass
- exact-strength correction from JAVA to JAKAVI
- form-only preservation of family order

These nine focused tests predate the hardening work but remain mandatory regression contracts. Passing them alone is insufficient for accepting the provisional source.

The focused JAVA/JAKAVI correction fixture now supplies `raw_edit_distance=2.0` and `consensus_levenshtein_similarity=0.666667` on both name rows. This keeps the regression inside the current secondary-family admission gate instead of bypassing the diagnostic contract with underspecified synthetic rows.

### 20.2 Visual-gap tests

`benchmark_04_experiments/test_algorithm_6_visual_gaps.py` asserts:

- 20 explicit hard cases spanning internal, leading, trailing, both-edge, multiple-gap, shorthand, and one/two shared OCR-grapheme rules;
- nine edge-negative cases proving a leading/trailing marker hides at least one actual character even under confusion tolerance, including the three strict both-edge OCR-confusion patterns `...CLICY...`, `...BACTID...`, and `...ALEPI...`;
- three internal-gap negatives proving every explicit internal marker hides at least one character, plus a valid two-internal-gap positive;
- a repeated-leading-fragment unit guard proving the occurrence matcher skips a forbidden offset-zero occurrence and finds a later valid occurrence;
- marker-free shorthand proving its internal join may still hide zero characters;
- four real-catalog collision patterns that must retain both confusable literal families;
- eight one-to-four-visible-character guards that forbid direct grapheme-confusion evidence below the five-character floor;
- a 24-visible-character stress case capped at 512 patterns, a loaded-catalog time bound below two seconds, and rejection of more than four retained fragments;
- expected family inclusion;
- correct mode;
- confirmation-required output;
- ordinary exact multiword search is not converted to a gap search;
- deterministic 64-target catalog sample;
- generated Hit@20 >=95%.
- exact-family output identity: `result_name(item) == matched_family_name`, every matched key compacts that exact family, and broad BRUFEN grouping does not deduplicate BRUFEN/BRUFEN COLD/BRUFEN FLU;

The final exact working tree passed **20/20 explicit cases, 9/9 edge negatives, 3/3 internal-gap negatives, 4/4 collision patterns, 8/8 short-confusion guards, and 64/64 generated targets at Hit@20 (100%)**, including exact-family identity assertions. The stress contract still caps patterns at 512, loaded-catalog search below two seconds, and retained-fragment count at four. Earlier optimization smokes observed 511 nonliteral patterns in 0.109 seconds and 20 preloaded gap queries in 2.32 seconds; those earlier timings explain the bound but are not substituted for the final fair-412 latency report in Section 20.6.

### 20.3 Browser fallback tests

`app/test_app.js` tests JavaScript-only ordinary search, three unreadable modes, partial text, grapheme variants, generated indexed/full-scan parity, browser product context, deterministic repeated queries, and always-confirm behavior. It now also locks distinct cache keys for shorthand versus explicit/edge visual markers and checks decimal-comma, Arabic-decimal, and both Unicode-micro strength normalization against their ASCII equivalents. `node app/test_app.js` passed on the final inspected working tree with `Browser search tests passed.` The in-app browser could not connect to the candidate UI during the final audit, so no live browser/DOM interaction result is claimed. Passing the JavaScript suite does not prove Python API parity, rendered DOM coverage, or deployed-endpoint behavior.

### 20.4 Current provisional product-context hardening contracts

The uncommitted `app/test_product_context_hardening.py` contains **123** adversarial contracts. Together with the **nine** focused regressions in `app/test_product_context_reranker.py`, the latest coordinating run passed **132/132** on the exact inspected working tree:

```bash
PYTHONPYCACHEPREFIX=/tmp/rulebook_pycache PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest \
  app.test_product_context_reranker app.test_product_context_hardening
```

That focused pass is not proof of benchmark or deployment acceptance. The covered behaviors are:

- bare, ambiguous, large-before-form, Arabic-digit, and decimal unitless-number parsing;
- refusal to parse numbers attached to brand tokens, plus preservation of an exact numbered brand when no separate product-details field was supplied;
- catalog-derived stripping of the exact `3 FLY` commercial-brand prefix in the legacy combined-query path, while `3 FLY 600 tab` retains and uses the trailing real product evidence;
- exact prepared multi-number alias rescue for `1 2 3`, expansion of an empty/incomplete name set to both ONE TWO THREE exact bases, all-alias-family admission, explicit-context/visual bypass, nearby and mixed-unknown-suffix refusal, trailing product filtering, product-score ordering, capped selection/failure rows with full candidate count, and no-compatible-product abstention;
- prepared number-plus-family alias rescue, globally longest-alias precedence over numeric-only aliases, exact suffix recognition, and preservation of an original no-context name response only when its unique top exact family is the alias family;
- two unitless numbers representing likely strength plus likely package;
- comma/dot unit normalization, Arabic decimal/thousands separators, both Unicode micro symbols, attached dotted abbreviations, whitespace-grouped and dotted IU thousands, MIU, microlitre/MCL and time denominators, percent next to label text, and preservation of leading-zero/leading-dot decimals;
- implicit concentration denominators;
- shared-unit combinations, explicit-unit combinations, shared denominators (`2 MG + 5 MG/ML` and `2/5 MG/ML`), mixed-dimension combinations, repeated components, and exact explicit totals before reduced-concentration equivalence;
- non-unit structural ratios such as `30/70` and `1:100000`, including hard conflicts;
- concentration denominator hard conflicts and incomplete numerator-only evidence;
- wrong unit scale versus equivalent canonical mass;
- volume/topical presentation separation from dose strength;
- explicit `500 pack` overriding the heuristic package ceiling, multipacks, prefilled/container modifiers, unit-dose packages, and conjunction semantics requiring every explicit package constraint;
- added form and written release aliases;
- tablet/capsule, effervescent/plain, chewable/plain, injection-subtype, and vial/ampoule container boundaries, plus broad `oral_solid` and compatible injection relations;
- BRUFEN behavior for bare `600`, `600 tab`, `30 tab`, and `600 mg` ties;
- all-conflict abstention rather than selecting the least-wrong product;
- explicit zero-strength fail-closed behavior;
- no introduction of an unretrieved unrelated family;
- the unique unitless-number+form reorder gate, multi-family no-reorder, numerator-only no-reorder, form-only no-reorder, exact qualified-presentation reorder (with and without explicit form), and weak bare-presentation-number no-reorder without form;
- the `javaki`/JAVA -> JAKAVI 5 mg regression;
- locked rank-two exact-presentation recoveries for LEIL and ARGOTEX;
- exact-name hard family boundaries; no jump from an exact conflicting name to rank two; no broad variant-sibling admission from exact, typoed, or visual names; first-three family admission with all available distance diagnostics; and rank-four exclusion;
- strict one/two-character exact-base-family prefix candidates, no global fuzzy expansion, missing-evidence refusal, folded-base counting, visual-mode bypass, and more-than-limit abstention;
- explicit package+form short-prefix filtering and one-visible-result-per-admitted-family behavior;
- every accepted explicit package-word family (`pack`, `packet`, `box`, `bottle`, `piece`, `pcs`, and `pen`, including plural spellings);
- known route-conflict and release-conflict rejection, while missing release metadata remains unknown rather than a fabricated conflict;
- the six-visible-product per-family tie cap with disclosure of the full uncapped tie count;
- stable selected-product IDs preserving duplicate normalized commercial names and their distinct price/manufacturer records;
- preservation of a second retrieved family when the first family has more tied products than the output limit;
- the same strict boundary for a real two-character prefix;
- semicolon catalog metadata: later standalone presentation fields, repeated denominator/presentation reconstruction, and later `UNIT` dose counts;
- real-catalog `x + 500 tab`, BRUFEN 600 tablet/comma form, XANAX 500 mg abstention, attached percent, complete dotted PHESGO signature, and inhaler dose-count selection.

The 132 focused tests are accepted local-source evidence, not a deployment claim. Live DOM rendering and multi-seed `PYTHONHASHSEED` determinism remain outside this final audit; the 200-case and API results are recorded separately below.

### 20.5 Current provisional black-box API hardening contract

The untracked `benchmark_04_experiments/test_algorithm_6_api_hardening.py` is a live-server acceptance script, not an import-level unit test. It accepts `--base-url` (default `http://127.0.0.1:8013`), uses a 30-second request timeout, and makes these contracts explicit:

- `GET /api/runtime` must be ready, identify `algorithm_6` and evaluation version `algorithm_6_consensus_v1`, report exactly 25,066 medicines and 17,476 families, and advertise `ordinary_search`, `visual_gaps`, and `product_context_reranking`;
- `GET /health` must equal `{"status": "ok", "algorithm": "algorithm_6"}`;
- every tested `/api/search` result must identify Algorithm 6, and every returned row must set both `confirmation_required` and `needs_clarification` to true;
- `javaki + 5mg` must put JAKAVI first, select `JAKAVI 5 MG 56 TABS.`, report family reranking, and retain `name_match_rank == 2`;
- BRUFEN must expose all three correct `600` ties for bare context, one 600 mg tablet for both `600 tab` and `600, tab`, and all three 30-tablet strengths for `30 tab`;
- `x + 500 tab` must return the four strict-prefix families XELODA, XEREXOMAIR, XEROVIRINC, and XITHRONE as ambiguous context-assisted prefix candidates, while `x + 600 tab` must abstain with `context_assisted_prefix_no_match`;
- `xanax + 500 mg tab` must keep the XANAX family but return the family display row, `strength == "-"`, and `product_context_no_compatible_product`, never a conflicting product presentation;
- AUGMENTIN `1.2 g vial` must select the IV vial, while `156 mg/10 ml suspension` must produce the no-compatible-product decision;
- qualified presentation cases `leal + 100 g cream` and `argatex + 50 g cream` must rerank to LEIL and ARGOTEX with `qualified_presentation_exact`; the weak bare case `argatex + 50` must preserve ARGITEX and report no family reorder;
- exact numbered brand query `D3` must remain D3;
- empty-context numeric word brand `3 FLY` must remain the FLY name decision, and legacy combined query `3 FLY 600 tab` must select `3 FLY 600 MG 20 TABS.` through unitless-strength evidence;
- exact alias `1 2 3` must return both ONE TWO THREE and ONE TWO THREE EXTRA as ambiguous `numeric_commercial_alias_matches`; `1 2 3 20 tab` must return both 20-tablet products as `numeric_commercial_alias_product_context_selection`;
- the longer prepared brand alias in `1 2 3 ONE TWO THREE 20 tab` must take precedence and select only the ONE TWO THREE base; `1 2 3 junk 20 tab` must not enter numeric-alias mode;
- ordinary OCR/grapheme probes must retrieve exact OMEPRAZOLE SPLENDID PHARMA for `OMGPRAZOLG` and `OMIPRAZOLI`, ADDO H for `ACLCLOH`, and ALKALINE for `DKDINE`;
- strict both-edge probes `...CLICY...`, `...BACTID...`, and `...ALEPI...` must remain in `visual_gap_matches` mode but **must not** return DICYNONE, BACTICLOR, or DEPIDERM, because each edge marker must hide a real target character;
- the corresponding suffix-positive probes `CLICY...`, `BACTID...`, and `ALEPI...` must return those exact families;
- `...PANADOL` must remain a strict leading-edge negative;
- `BRU... + 600 mg tab` must retain `name_decision_type=visual_gap_matches` and select only `BRUFEN 600 MG 30 TABS.`; short visual `BR...` must not dispatch global short-prefix rescue; numeric visual `3__FLY` must not dispatch numeric-alias rescue.
- numeric visual pattern `VIT__3` must remain a visual-gap response, retrieve VIT D3, and must not reinterpret its visible 3 as implicit product context;
- `citicoline + 500 mg cap` must return both duplicate-name catalog rows with distinct stable IDs `D2-04517` and `D2-04518`, preserving their distinct prices and manufacturers;
- attached percent query `econazole + 1% spray` must select product ID `D2-06821` with exact-strength evidence.

The script labels the combined runtime, health, and search coverage as **38 endpoint scenarios**. All **38/38** passed against the final local candidate used for this audit. That is local candidate evidence only: it does not establish a public deployment, commit/remote identity, or browser DOM behavior.

### 20.6 Current provisional OCR/grapheme tests and remaining acceptance work

The untracked `benchmark_04_experiments/test_algorithm_6_ocr_confusions.py` is now present. It defines:

- 23 catalog-backed positive queries covering single/double `E/G`, `I/E/Y`, `D/CL`, `D/AL`, first-character, middle, edge, and corrected-prefix surface recovery. The three prefix cases `OMGPRAZOLG`, `OMIPRAZOLI`, and `OMYPRAZOLY` require exact OMEPRAZOLE SPLENDID PHARMA within rank 20;
- two locked fair-set regression guards: `LGCMU -> LACTO` at rank 1 and `KEONOOL -> KETOROLAC` within rank 20. These specifically forbid turning E/G into a generic global weighted-edit discount or enabling every legacy first-character confusion group as retrieval;
- 23 fast clean/fair safety regressions: the 11 clean Hit@1 repairs `ACTIVEN`, `CITAL`, `GVITON`, `PEXE`, `RONE`, `SILDAN`, `CLAZOL`, `PANAL`, `BJEIND`, `SEORPIPUHAIRCONCLITIONER`, and `YRSOCLIOL`; `CLOLOCL -> DOLCYL` within top five; historical clean Hit@20 repair `ACLOX -> ADOX`; six clean collateral guards; and all four ABASAGLAR fair queries restored to rank one by the strict-prefix family-head exception;
- 21 exact catalog-name guards (`ORDEX`, `ORALEX`, `TDA`, `TALA`, `TOBRADEX`, `TOBRAALEX`, `URAL`, `AMOXICILLIN`, `AMOXYCILLIN`, `CODE`, `CODY`, `SELE`, `SYLE`, `TRICHOGEL`, `TRICHOGYL`, `BALMEX`, `BALMIX`, `CEFEX`, `CEFIX`, `MELANO`, `MILANO`) that must remain rank 1;
- one direct non-transitivity assertion: two permitted steps must not turn the single original character in `IARDX` into `GARDX`;
- seven ambiguous non-catalog spellings that each reach two real families and must never receive `bounded_grapheme_confusion_correction`;
- clarification-required assertions for every returned positive and exact guard.

The exact working tree passed **23/23 positives, 2/2 locked fair regressions, 23/23 clean/fair safety regressions, 21/21 exact-name guards, 7/7 global-ambiguity guards**, the non-transitivity assertion, and the 120-character no-variant runtime guard below 0.10 seconds.

The identity-aware locked fair-412 old/new comparison also completed. It resolves visual rows through the exact matched family rather than the broad variant group:

| Metric | Old reference | Final local candidate |
| --- | ---: | ---: |
| Hit@1 | 234/412 | 234/412 |
| Hit@5 | 295/412 | 296/412 |
| Hit@20 | 340/412 | 340/412 |
| MRR@20 | 0.6334013498241085 | 0.6339070132545293 |
| Diagnostic p50 latency | 144.363 ms | 120.789 ms |
| Diagnostic p95 latency | 298.290 ms | 285.616 ms |
| Diagnostic p99 latency | 414.269 ms | 358.906 ms |

There were zero paired prior Hit@1, Hit@5, or Hit@20 losses. Four ABASAGLAR cases that an intermediate clean-safety guard had displaced were restored to their historical rank one through the narrow strict-prefix family-head exception. Against the old reference, exactly one row changed rank: `OSTOEND`, expected OSTOCAL, improved from rank 8 to rank 3. Latency percentiles are diagnostic observations from this final-image run, not acceptance gates or general performance guarantees. These are local-candidate measurements, not public deployment measurements.

The final-image fair report was `/tmp/a6_v7_fair_412.json`, SHA-256 `e2cb08ae9018f8c621d628f9472f32e157b989680fec6e6093df2a549b3e6d9e`. `/tmp` is not an immutable project store; preserve/copy this evidence with release artifacts before treating the hash as durable provenance.

The repository comparator `evaluate_algorithm_6_ocr_fair.py` locks the CSV SHA-256 to `3ad1a423cadc96b29665a8c600c27eb25bc743a5274f4a2c7917402fe09979bd` unless `--allow-unlocked-csv` is explicitly supplied. The 412 accepted/scored rows comprise 324 development and 88 holdout rows; 42 permit more than one exact expected family key. The comparator filters `accepted=1` and `scored_case=1`, rejects duplicate accepted/scored case IDs or empty expected keys, verifies both runtimes identify Algorithm 6 and the candidate is ready, requests limit 20, and requires response/result confirmation fields from the candidate. Its exact visual identity precedence is `matched_family_key`, `matched_family_name`, `commercial_name`; ordinary identity uses `base_group_key`, `variant_group`, `name`. It exits zero only with no paired old-Hit@1, old-Hit@5, or old-Hit@20 loss, nondecreasing aggregate Hit@5, and nondecreasing MRR@20. The paired Hit@5 gate prevents trading away an old top-five row for a different aggregate gain. `--report` can preserve the JSON artifact; `--workers` controls concurrent requests.

The cases removed from the scored fair denominator were preserved rather than deleted in sibling file `benchmark_04_experiments/data/01_ocr_fair/excluded_cases.csv`, SHA-256 `56c52e5d3e69ea9d87547c6a4ae9b010611e06347fa2296e45bce040581ff3ee`. It contains 52 rows: 15 from the August 7 exclusion group and 37 from August 8, split 47 development and five holdout. This file is provenance/audit evidence and is not silently mixed back into the 412 accepted/scored denominator.

The focused suite spans both directions, start/middle/end positions, single and mixed errors, short and long names, corrected-prefix recovery, and real catalog collisions. The fair-412 result above is the completed locked old/new check for this change. It is not a substitute for the full mandatory algorithm roster or required ablations in a future formal evaluation package.

The clean synthetic regression was also completed against the locked **66,257-row** file `benchmark_04_experiments/data/05_synthetic_clean_core/test_cases.csv`, SHA-256 `65f81b58dee1e7127386652383d2f6a8db1734e832dcbc73f14a9b831678886f`:

| Metric | Frozen old reference | Final guarded source |
| --- | ---: | ---: |
| Hit@1 | 65,057/66,257 | 65,142/66,257 |
| Hit@5 | 66,027/66,257 | 66,078/66,257 |
| Hit@20 | 66,256/66,257 | 66,257/66,257 |
| MRR@20 | 0.9884128043253494 | 0.9893173398439633 |

Paired old-to-final gains/losses were **85/0 at Hit@1, 51/0 at Hit@5, and 1/0 at Hit@20**. Relative to the first unguarded hardening candidate, the safety pass added 25 Hit@1 and 24 Hit@5 recoveries with zero losses; it preserved all 71 earlier Hit@1 gains, repaired 11 Hit@1 losses and one Hit@5 loss, and kept `ACLOX -> ADOX` at rank one. The summary artifact was SHA-256 `8554bcd1e3f2468cefa0f7b82e542f54b7eb3abd34a0190b7a3aa9d1270d2649`; its paired row artifact was `e227fb1ac42c7d661da40f3774aefd5b972dc2530ca2b329544183562265ea9f`.

The final strict-prefix family-head change was then checked against all 66,257 rows with eight forked workers. Current Algorithm 5 SHA-256 `a8f040de1b15fe317bf6e870bb83995684f76e480f01764a762a2bc5f99b3499` stayed identical at process start/end and in every fork; exact top-20 output differed from the refined zero-loss reference on **zero rows**, and the strict-prefix exception fired on **zero clean rows**. The sharded audit summary SHA-256 was `e510fe2ac340a5bc07f76adb14785d2d7cbd0e05dd5d4a527c4f836f5a5af1d3`; reference gzip SHA-256 was `9ec131883ce425c3c05a275bf1f531f76fd8697d6d2ec12870d1de3981a3749c`. Wall time was 661.775 seconds after 15.413 seconds of preparation.

The clean-set-validated safety layer is not a list of medicine aliases. It adds generic ordering guards: a bounded direct grapheme rewrite cannot casually beat a closer full name or an unsupported raw tie; the legacy exact-ligature rank extension is narrowed for new variable-length rules; a family-head shortcut normally cannot promote a worse complete catalog name; and three post-grapheme repairs release a strictly Pareto-better chain from a preserved-top guard, protect an external-rank-one ligature-chain tie, or move one uniquely qualified ligature-vowel-transposition candidate into the top-five boundary. Exact predicates are recorded in Sections 11 and 24.

The exceptional depth-two `D -> AL` path for `DKDINE -> ALKALINE` requires exactly two original `D` spans rewriting to `AL`, total direct cost 1.40/depth two, a globally unique minimum-cost catalog target, raw disadvantage at most two, weighted improvement at least 0.25, score gap at most 0.50, and candidate rank at most six. An exhaustive necessary-condition scan found **zero eligible rows** among all 66,257 clean cases and no target-rank changes; the audit summary SHA-256 was `b3057c3d6f65ba0bcd64ba5a7f77fc1ff189b49555edff90dd6c5b4f994f47da`.

Do not infer symmetry from handwriting appearance. `E->G` and `G->E`, or `D->AL` and `AL->D`, are separate hypotheses even where both currently appear in the provisional table. The exact-name, ambiguity, non-transitivity, over-24-character, and below-five-visible-gap guards now have direct cases; the length-4/length-6 ordinary-name confusion-depth boundary, 512 retrieval-variant cap, and shared cost/confusion budgets still need explicit boundary tests.

### 20.7 Deployment and benchmark invariants

The source and project policy require all of the following before changing a provisional rule to deployed/accepted:

- one Python API worker; startup must retain exactly 25,066 product rows and 17,476 families;
- `/api/runtime` must identify `algorithm_6`, report `algorithm_6_consensus_v1`, and expose ordinary search, visual gaps, and product-context reranking;
- `/health` must remain healthy and representative `/api/search` requests must use the Python path;
- the locked 412 unique OCR pairs and the applicable clean synthetic regression must be rerun for name/OCR changes;
- Hit@1 and Hit@20 must be reported together, including paired gains and losses, unsafe confident errors, clarification behavior, candidate counts, and latency;
- target-family-disjoint holdout must remain untouched until thresholds are frozen;
- visual-gap regression must run whenever shared grapheme/edit behavior changes;
- Python and browser fallback must not be conflated; any required fallback parity needs separate implementation and tests;
- the built endpoint must be verified at the recorded commit/branch after deployment.

The untracked `benchmark_04_experiments/evaluate_algorithm_6_product_context.py` reconstructs 200 deterministic cases by:

1. retaining catalog base families whose compact key is alphabetic, length 4--12, and whose `st` contains a digit;
2. keeping the first strength per family;
3. replacing the middle family character with `A` (or `O` when it is already `A`);
4. sorting rows by SHA-256 of `query|family|strength` and taking the first 200;
5. calling the configured Algorithm 6 API twice per row, first name-only and then with exact strength context;
6. comparing top-1 `base_group_key` against the expected compact family.

The default catalog is locked twice: raw catalog SHA-256 `d234edaa2669d1eeb46b962e7e3e02df52c6f4d2fd3eca7a2fbf3bc7d159fd9c`, and compact JSON serialization of the resulting 200 case tuples SHA-256 `21e0992188f27364582660b8072837c9d5d0fd3bcb3bbbf9c41bf7e471fd7ff5`. Drift in either aborts the run unless the operator explicitly supplies `--allow-unlocked-catalog`, in which case the report still records both observed hashes.

Its default endpoint is `http://127.0.0.1:8013/api/search`, timeout is 30 seconds per call, and optional `--report` writes the JSON summary. `--expected-baseline` defaults to **197**; `-1` disables only that baseline-count enforcement for diagnostic use. A context hit is intentionally stricter than family-name equality: top `base_group_key` must be the expected family, the decision must be a successful product-context selection, the top row must carry a nonempty stable `selected_product_id`, and it must not be `no_compatible_product`. Exit status is zero only when the observed baseline equals the configured expected count, all 200 rows satisfy that strict context-hit definition, and no baseline-correct row regresses. The script reports baseline hits, context hits, recoveries, misses, regressions, selected IDs, and dataset hashes.

The final local candidate reproduced the exact recorded product result: name-only baseline **197/200**, strict product-context result **200/200**, with LEIL, DIKOL, and ARGOTEX as the three recoveries and **zero regressions** among baseline-correct rows. Every context hit therefore represented an actual selected catalog row, not merely a family name or a no-compatible placeholder. This verifies current-tree recovery behavior; it does not establish a deployed endpoint or identify an immutable commit.

The local product report was `/tmp/a6_v6_product_200.json`, SHA-256 `3cf0273ef0878b6a24a0d1a642a27090033ea9c6049cb292e97fe73a2745f005`; as with the fair report, a `/tmp` path is ephemeral and must be copied into durable release evidence if long-term provenance is required.

The final coordinating audit verified the focused product, OCR, visual-gap, API, JavaScript, syntax, whitespace/diff, fair-412, and deterministic 200-case results recorded above. A new commit/remote ref and public deployed endpoint remain required before calling this tree deployed.

### 20.8 Evaluation-policy invariants

`docs/evaluation.md` is the repository-wide scoring contract. Rules that change only this document do not change the evaluator; a code/test/report change must keep these invariants:

- use stable runtime IDs; static GitHub Pages is `browser_consensus_search`, never `algorithm_6_consensus_search`;
- name every percentage denominator and distinguish observation, unique pair, scored/fair pair, synthetic clean unique pair, locked unreadable request, and diagnostic low-evidence partial request;
- exact real-medicine collisions stay visible for safety analysis but are excluded from a one-answer fair denominator;
- fail validation on duplicate case IDs, unmappable targets, missing algorithm rows/categories/splits, non-reconciling counts, or development/holdout family overlap;
- retain query, expected target, candidate ranks, response status, clarification flag, and algorithm ID in row-level evidence;
- train/freeze learned features and thresholds using development or cross-fit rows only; reused historical holdout must be labeled `retrospective_holdout`, not fresh blind holdout;
- report Hit@1 and Hit@20 together; also report MRR@20, no-result rate, clarification, unsafe confident top-1, candidate count, and applicable latency/memory;
- compute safety from the actual response status and clarification fields, never infer safety from rank alone;
- for a visual-gap/partial request, relevance is every catalog family satisfying the stated position constraint, not only the source family used to generate the mask;
- primary flexible partial-text rows need an exact fragment or at least two ordered fragments; a single short fuzzy fragment remains diagnostic;
- every new metric/error group propagates backward to compatible systems, and every new algorithm is evaluated under all existing compatible analyses;
- every excluded/incompatible method receives a recorded status/reason instead of disappearing from the mandatory roster;
- ablations remove exactly one named component per run; coupled removals are labeled combined ablations;
- Algorithm 6 ablation must rerun the full nested Algorithm 6 pipeline with the altered Algorithm 5 base, then separately remove each consensus source/slot/gate;
- a new rule may not delete a failed row from the locked denominator; source-image review can change a label only through the independent audit contract.

Historical results in `docs/evaluation.md` are evidence for named source revisions, not automatically the current working tree. In particular, it records both a historical accepted 66,257-case Algorithm 5 result and a different “current source revision” result; any new report must identify the exact commit instead of blending them.

## 21. Contributor checklist for a new rule

### 21.1 Define the problem

- [ ] Record the exact observed query, expected family/product, current rank, and current competing result.
- [ ] State whether the evidence comes from OCR pixels, handwriting review, keyboard error, pronunciation, product strength, form, route, release, package, or catalog metadata.
- [ ] State the intended runtime: Algorithm 2, Algorithm 5, Algorithm 6 consensus, visual gap, product reranker, API, UI, or browser fallback.
- [ ] State whether the rule is directional.
- [ ] State whether it changes candidate generation, score, promotion, filtering, or display only.

### 21.2 Prefer the narrowest representation

- [ ] Use a generic character/structure/context rule when evidence supports one.
- [ ] Do not add a medicine-specific alias unless the requirement explicitly authorizes curated aliases and the alias is documented as such.
- [ ] Do not hide a product-context problem inside medicine-name edit costs.
- [ ] Do not interpret a number until strength, package, presentation, and brand-number alternatives have been considered.
- [ ] Keep complete strength signatures; do not pool numerator from one product and denominator/form from another.
- [ ] Treat form compatibility separately from exact form equality.

### 21.3 Bound activation

- [ ] Specify query-length range.
- [ ] Specify candidate rank window.
- [ ] Specify maximum score gap.
- [ ] Specify raw, weighted, visual, position, edge, n-gram, phonetic, or dual-retrieval requirements.
- [ ] Specify uniqueness/tie behavior.
- [ ] Specify catalog bucket/candidate cap and latency bound.
- [ ] Protect exact, variant-family, previously corrected, and pre-expansion winners where appropriate.
- [ ] Define abstention/no-match behavior when evidence conflicts.

### 21.4 Evaluate without leakage

- [ ] Select thresholds on development only.
- [ ] Keep target-family-disjoint holdout untouched until the policy is frozen.
- [ ] Never delete a case because the algorithm fails it.
- [ ] Report denominators, row IDs, paired gains, paired losses, and unchanged cases.
- [ ] Report Hit@1/5/10/20, candidate count, clarification rate, unsafe confident errors, and latency.
- [ ] Break results down by query length, operation type, source, danger, and family split.
- [ ] Rerun all compatible mandatory baselines and ablations.
- [ ] Preserve deterministic artifacts and configuration.

### 21.5 Implement transparently

- [ ] Add a named constant instead of an unexplained literal when the value is policy.
- [ ] Add a reason/evidence label to every result changed by the rule.
- [ ] Mark diagnostic-only values as diagnostic.
- [ ] Do not enable a dormant gate accidentally.
- [ ] Add unit tests for the exact rule and negative boundary.
- [ ] Add generated/catalog-derived tests when the rule is general.
- [ ] Update this rulebook, README/API contract, and UI labels in the same change.
- [ ] If browser fallback parity is required, implement and test it separately.

### 21.6 Verify before claiming completion

- [ ] Run focused unit tests.
- [ ] Run visual-gap regression if shared normalization or character rules changed.
- [ ] Run the locked OCR evaluation.
- [ ] Run the clean synthetic regression/affected-case audit.
- [ ] Run product-context paired tests and the 200-case regression when context changed.
- [ ] Compare before/after result rows, not only aggregate percentages.
- [ ] Verify API `/api/runtime`, `/health`, and representative `/api/search` requests.
- [ ] Verify the actual UI against the Python runtime identifier.
- [ ] Record commit, branch, catalog version, environment, and endpoint.
- [ ] Only then change the Section 1 provisional status to active/deployed.

## 22. Known discrepancies and open design questions

1. Should the provisional unitless matcher compare observed numeric values only, or allow canonical cross-unit inference when the user omitted a unit? Current source intentionally uses observed values, so bare `1` does not automatically equal catalog `1000 mg` represented as `1 g` unless the observed catalog number is 1.
2. Should ambiguous `20 tabs` prioritize package evidence as it currently does, or require additional catalog/context evidence before cross-family reordering?
3. Is the one/two-character prefix scan acceptable at current catalog scale, or should it receive a prepared prefix index and a fixed candidate-product cap?
4. Should a product with missing strength metadata remain compatible at `-35`, or should qualified-strength queries abstain from that family entirely?
5. Should route aliases map catalog `oral_solid`/`oral_liquid` into the query's broad `oral` route for explicit compatibility?
6. Should different topical specifics such as cream versus gel always conflict, or sometimes remain compatible when OCR only indicates topical form?
7. Should exact combination-strength comparison preserve component order, or is multiset equality the intended clinical rule? Current source uses multiset equality.
8. Should the global promotion-ambiguity enumeration receive an explicit output/latency ceiling beyond the existing 24-character/two-operation bounds? Current source intentionally uses `output_limit=None` for the uniqueness decision so an equal-cost catalog family hidden beyond the 512 retrieval cap still blocks promotion.
9. The pairwise-only E/G first-character retrieval boundary passed the identity-aware fair-412 comparison with zero paired Hit@1/Hit@5/Hit@20 losses and improved one Hit@5 row. The 66,257 clean paired check also passed with the gains/losses in Section 20.6. Full mandatory algorithm-roster ablations and publication-level candidate-pool analysis remain separate work; do not infer them from latency alone.
10. Should learned confusion similarity become an active Algorithm 6 feature? It is diagnostic now, and enabling it requires a separately cross-fit gate.
11. Should inherited medicine-specific Algorithm 2 aliases remain, be moved to a clearly governed alias registry, or be removed after paired evaluation?
12. Which runtime must remain authoritative if Python and browser fallback rules diverge? Current deployment guidance makes Python Algorithm 6 authoritative.

## 23. Source map

| Topic | Source |
| --- | --- |
| Algorithm 6 consensus and visual gaps | `benchmark_01_legacy/master_algorithms/algorithm_6_consensus_search.py` |
| Algorithm 6 policy and learned costs | `benchmark_01_legacy/master_algorithms/algorithm_6_policy.json` |
| Algorithm 5 rescue/reranking/safety | `benchmark_01_legacy/master_algorithms/algorithm_5_commercial_name_search.py` |
| Inherited Algorithm 2 | `benchmark_01_legacy/external_algorithms/english_search_algorithm_fast.py` |
| Shared name normalization and keyboard map | `benchmark_01_legacy/evaluate_current_app_search.py` |
| Product context | `app/product_context_reranker.py` |
| API contract/display enrichment | `app/api.py` |
| UI and browser fallback | `app/index.html`, `app/app.js` |
| Run/deployment instructions | `README.md`, `Dockerfile`, `deploy/oracle-cloud.sh` |
| Product-context focused tests | `app/test_product_context_reranker.py` |
| Provisional adversarial product-context tests | `app/test_product_context_hardening.py` |
| Visual-gap regression | `benchmark_04_experiments/test_algorithm_6_visual_gaps.py` |
| Provisional OCR/grapheme hard cases | `benchmark_04_experiments/test_algorithm_6_ocr_confusions.py` |
| Provisional locked fair-OCR old/new comparator | `benchmark_04_experiments/evaluate_algorithm_6_ocr_fair.py` |
| Provisional live-server API hardening acceptance | `benchmark_04_experiments/test_algorithm_6_api_hardening.py` |
| Provisional deterministic 200-case context evaluator | `benchmark_04_experiments/evaluate_algorithm_6_product_context.py` |
| Browser fallback tests | `app/test_app.js` |
| Evaluation policy and historical evidence | `docs/evaluation.md` |

## 24. Current-source provisional OCR/grapheme appendix

**Update point:** This section records the uncommitted working-tree source and final local verification inspected on 2026-08-13 (Africa/Cairo). It supersedes older committed-behavior statements in Sections 8, 9, 14, and 15 only for describing the present tree. The focused, fair-412, clean-66,257, 200-case, and local API results below are evidence for that mutable local tree; they are not evidence that it was committed, pushed, or deployed publicly. Update this section and Section 1 together whenever source, results, commit, or endpoint changes.

### 24.1 Exact provisional registry

`PAIRWISE_SUBSTITUTION_COSTS` adds two directional single-character costs for bounded rewrite and pairwise-only first-character retrieval:

| Observed query | Catalog target | Cost |
| --- | --- | ---: |
| `E` | `G` | 0.60 |
| `G` | `E` | 0.60 |

`GRAPHEME_CONFUSION_RULES` is the shared observed-query -> catalog-target registry:

| Observed query | Catalog target | Cost | Shape |
| --- | --- | ---: | --- |
| `E` | `G` | 0.60 | single -> single |
| `G` | `E` | 0.60 | single -> single |
| `I` | `E` | 0.45 | single -> single |
| `E` | `I` | 0.45 | single -> single |
| `Y` | `E` | 0.45 | single -> single |
| `E` | `Y` | 0.45 | single -> single |
| `I` | `Y` | 0.45 | single -> single |
| `Y` | `I` | 0.45 | single -> single |
| `CL` | `D` | 0.40 | two -> one |
| `D` | `CL` | 0.55 | one -> two |
| `AL` | `D` | 0.45 | two -> one |
| `D` | `AL` | 0.70 | one -> two |

Exact bounds:

| Constant/function | Current value/rule |
| --- | --- |
| `GRAPHEME_VARIANT_LIMIT` | 512 |
| `MAX_GRAPHEME_VARIANT_INPUT_LENGTH` | 24 |
| `TWO_GRAPHEME_CONFUSION_MIN_LENGTH` | 6 |
| `GRAPHEME_PROMOTION_MAX_RANK` | 12 |
| `GRAPHEME_PROMOTION_MAX_SCORE_GAP` | 0.75 is defined; the live direct-promotion predicate uses 0.65 |
| `maximum_grapheme_confusions(value)` | length <4 or >24 -> 0; length 4--5 -> 1; length 6--24 -> 2 |
| explicit `max_confusions` override | converted to integer and clamped to 0--2; it bypasses the default minimum length but never the 24-character maximum |
| `grapheme_confusion_variants(..., output_limit=...)` | default 512; nonnegative integer values slice to that many; `None` returns the full bounded-by-length/depth ordered set for global ambiguity checking |
| `MULTI_GRAPHEME_CONFUSION_RULES` | only registry rows where source or target length differs from one: `CL/D` and `AL/D` in both directions |

These are generic character/grapheme rules. They are not medicine-name aliases. The medicine-specific inherited Algorithm 2 alias table in Section 5.2 still exists independently and must be governed/evaluated separately.

The source comment explicitly rejects a transitive equivalence class. `E` already overlaps the inherited generic `I/E/Y` handwriting group and `G` overlaps `G/J`; canonicalizing all connected characters would incorrectly make `I`, `Y`, `E`, `G`, and `J` interchangeable.

### 24.2 Exact candidate generation

`grapheme_confusion_variants()`:

1. compacts the input through the shared name `compact_key()`;
2. chooses the length-based maximum unless an explicit bounded override is supplied;
3. immediately returns no variants for an empty input, zero budget, or a compact input longer than 24;
4. performs a left-to-right depth-first walk over positions in the **original observed string**;
5. at each position either copies the next original character or applies one registry rule whose source begins there;
6. never revisits characters written into the output, preventing transitive chains such as applying `I -> E` and then `E -> G` to the same original `I`;
7. keeps the best `(cost, depth)` for each complete output;
8. returns non-original variants sorted by `(cost, depth, spelling)`; the default output cap is 512, while `output_limit=None` returns the full length/depth-bounded set.

The operation budget can still be spent on two different original positions. “Non-transitive” therefore does not mean “only one rule”; it means a generated replacement is never treated as fresh observed input.

`exact_grapheme_confusion_family_ids()` looks up only generated variants that are exact catalog-family keys. It has a hard exact-name boundary: if the observed compact query is already an exact catalog family, it returns no confusion alternatives.

The exact IDs are integrated at four points:

- they make `standard_rescue_needed` true even when the ordinary Algorithm 2 gate would skip rescue;
- they are inserted into the rescue core candidate IDs;
- they are re-added after the generic cheap prefilter so a documented exact confusion cannot disappear only because the ordinary prefilter was not designed for variable-length graphemes;
- they receive reason `bounded_grapheme_confusion_retrieval`.

These IDs are added by `search_catalog()`/`rescue_search()` around the ordinary `candidate_family_ids()` output; the generic candidate helper itself remains unchanged. Every family still goes through ordinary scoring/ranking and all final results remain clarification-required. The registry is candidate/evidence support, not authorization to auto-select.

`grapheme_confusion_prefix_family_evidence()` handles a corrected spelling that is only a proper prefix of a longer exact catalog family, such as observed `OMGPRAZOLG` -> corrected `OMEPRAZOLE` -> OMEPRAZOLE SPLENDID PHARMA. It:

- accepts compact query length 6--24 only and refuses an exact catalog query;
- generates the full direct variant set with `output_limit=None`;
- accepts only variants of length >=6 and total cost <=1.40;
- reads the prefix index at the first `min(12, variant length)` characters;
- retains only families whose complete compact key starts with the full corrected variant and is strictly longer than it;
- rejects an empty prefix bucket or a bucket containing more than `GRAPHEME_PREFIX_SURFACE_MAX_FAMILIES = 4` families;
- retains each family's best evidence by `(cost, depth, spelling)`.

These prefix families, like exact-rewrite families, force standard rescue, enter core IDs, survive generic prefiltering, and receive a dedicated reason. When ordinary scoring cannot retain one, the low-confidence evidence-only formula in Section 10.2 keeps it available for bounded tail surfacing.

`promote_exact_grapheme_confusion_candidate(index, ranked, compact)` then provides a separate conservative ordering rule in the ordinary, non-unreadable path:

- do nothing with fewer than two ranked candidates or whenever any returned candidate exactly equals the compact query;
- generate the full length/depth-bounded direct variant set with `output_limit=None`;
- map every generated spelling through the exact-family index, retaining each reached family's best `(cost, depth, spelling)` evidence;
- require exactly one **catalog family globally** at the minimum direct rewrite cost (cost equality tolerance `1e-9`), even if another equal-cost family did not survive the ranked/capped shortlist;
- derive that unique family's compact key, then inspect only the first 12 ranked candidates for a row with that key and reason `bounded_grapheme_confusion_retrieval`;
- normally refuse a raw-distance disadvantage greater than one; a raw-distance tie is accepted only when a direct rewrite changes grapheme length, or when the single direct rewrite is at position zero, both query/target names have the same length, and the incumbent key is exactly one character longer than the query;
- refuse any raw-worse path containing direct `AL -> D`, even if it passes other evidence;
- require candidate weighted edit distance no worse than the current top and a live score gap <=0.65. The module still defines `GRAPHEME_PROMOTION_MAX_SCORE_GAP = 0.75`, but this promotion function deliberately uses the stricter literal 0.65; changing either value does not change the other and must be reviewed as a policy discrepancy;
- provide one exception to the ordinary raw-gap bound for two `D -> AL` expansions: rewrite depth exactly two, total cost exactly 1.40, exactly two nonoverlapping original `D` spans yielding the target, raw disadvantage <=2, candidate weighted distance at least 0.25 better, score gap <=0.50, and zero-based shortlist index <=5 (public rank <=6);
- otherwise move it to first and add `bounded_grapheme_confusion_correction`.

The function computes and retains rewrite depth/spelling as evidence, but uniqueness is decided by minimum rewrite **cost**, not by depth. Seven focused ambiguity guards require both real alternatives to remain visible and forbid correction when spellings such as `MYLANO` reach MELANO and MILANO at equal cost. This promotion is followed immediately by `protect_exact_catalog_name()`.

The depth-two `D -> AL` exception was audited by scanning the necessary predicate over all 66,257 locked clean rows: zero rows were eligible, no audited target top-20/rank changed, and `DKDINE -> ALKALINE` remained rank one. This establishes the observed clean-set boundary for the current catalog; it does not make the exception universally harmless on a future catalog.

### 24.3 Weighted distance and custom edit evidence

The current generic `substitution_cost()` order is:

1. exact -> 0;
2. directional OCR digit when `ocr_visual=true` -> 0.45;
3. existing `CONFUSION_PAIRS`, including `I/E/Y` -> 0.45;
4. vowel-to-vowel -> 0.70;
5. other substitution -> 1.0.

Crucially, `PAIRWISE_SUBSTITUTION_COSTS` is **not** consulted here. The new E/G `0.60` pair is scoped to direct bounded rewrites, pairwise-only first-character retrieval, direct visual-gap patterns, and the explicitly bounded grapheme-evidence helper. It is not a generic discount inside every ordinary global weighted-edit alignment. The locked `LGCMU -> LACTO` regression is the direct guard for this boundary.

Ordinary weighted `damerau()` retains insertion/deletion cost 1.0 and adjacent-transposition cost 0.55. After its character-level dynamic program, it invokes `bounded_grapheme_edit_evidence()` only when at least one multi-character registry source occurs in the observed string and its paired target occurs in the catalog string. It uses one custom operation below length six and two at length six or greater, then takes the smaller of ordinary weighted distance and custom grapheme distance.

That weighted pairwise helper is distinct from exact-variant generation: this call path does not apply `MAX_GRAPHEME_VARIANT_INPUT_LENGTH`. The 24-character cap bounds generated exact variants and direct visual-fragment variants, not every weighted distance calculation.

`bounded_grapheme_edit_evidence(observed, target, max_confusions=2)` is a separate three-dimensional dynamic program over observed position, target position, and number of custom rules used:

- both inputs are compacted first;
- the caller's custom-operation count is clamped to 0--2;
- ordinary insertion, deletion, and unequal substitution each cost 1.0;
- an equal character costs 0;
- a custom registry transition consumes its full source and target strings, adds its directional cost, and increments the custom-operation count by one;
- the return value is `(minimum_cost, custom_operation_count)`, tie-broken by fewer custom operations.

This helper intentionally does not apply transitive character canonicalization or the entire ordinary weighted-edit rule set. Its custom single-character rows explicitly repeat the accepted `I/E/Y` costs so the same bounded registry can drive exact candidate retrieval and visual-gap alignment.

### 24.4 First-character and exact-name guards

The provisional `confusable_chars()` now returns uppercase targets and adds targets from `PAIRWISE_SUBSTITUTION_COSTS`; `first_chars_confusable()` compares uppercase values. That helper still exposes legacy confusion-group membership for scoring/plausibility. `first_char_variants()`, however, deliberately emits **only** the explicit pairwise substitutions currently E->G and G->E. It does not activate all legacy group members as prefix-index retrieval. This distinction fixes E/G retrieval without inflating weak pools; `KEONOOL -> KETOROLAC` within rank 20 is the locked regression guard.

`protect_exact_catalog_name()` runs at the end of the ordinary, non-unreadable Algorithm 5 reranking/promotion chain. If a returned candidate key exactly equals the compact query but a different candidate has become rank one, it moves the literal exact candidate back to the top and adds `exact_catalog_name_protected`. It does nothing when there is no exact returned candidate, the exact candidate is already first, or the request is in a legacy unreadable mode.

The clean-safety revision also constrains the older family-head shortcut by comparing the candidate's complete compact catalog name, not only its shorter head, with the incumbent. A worse complete name is blocked unless the shorter head is a literal strict prefix of that complete name and the head is closer than the incumbent's complete-name distance. Candidate-head uniqueness, at least one head-raw edit advantage, at least 0.30 OCR-visual advantage, no LCS loss, <=0.85 score gap, and the close-full-name protection continue to apply. This is the exact strict-prefix exception that restored the four ABASAGLAR fair cases; the unrelated SEROPIPE/BLAIR case has no qualifying strict-prefix candidate and remains protected.

The legacy exact-ligature rank-extension rule is also narrowed when a target is directly explained by one of the new variable-length `MULTI_GRAPHEME_CONFUSION_RULES`: such a candidate cannot promote from public rank four or five, and a raw-worse direct `AL -> D` candidate cannot promote at all. Ordinary unique legacy ligature rewrites that do not meet those new-rule conditions retain their previous top-five behavior.

This final protection complements the earlier exact-candidate-generation hard boundary. A confusion explanation may surface alternatives, but it must not reinterpret a literal catalog family as an OCR error.

The final relevant call order is `promote_candidate_pool_bounded_head_candidate()`, `promote_pareto_character_evidence_candidate()`, `promote_exact_grapheme_confusion_candidate()`, `protect_exact_catalog_name()`, `surface_grapheme_confusion_prefix_candidates()`, then `apply_post_grapheme_safety_repairs()`. Exact protection wins over direct-confusion promotion; corrected-prefix surfacing reserves tail visibility only; the final repair layer is limited to the three paired-clean predicates in Section 11.10.

### 24.5 Provisional Algorithm 6 visual-gap integration

The current visual bounds are `MAX_VISUAL_GAP_FRAGMENTS = 4`, `MAX_VISUAL_GAP_CONFUSION_VISIBLE_CHARACTERS = 24`, and `VISUAL_GAP_CONFUSION_PATTERN_LIMIT = 512`. The optimized design does **not** run the three-dimensional custom edit program separately against every catalog target. It precomputes direct visible-fragment rewrites once per query, preserving the committed ordinary one-edit aligner as the last stage.

`visual_gap_confusion_patterns(catalog, fragments, maximum_cost, maximum_confusions)`:

1. starts with one empty pattern at cost/depth zero;
2. for each fragment, builds options containing the literal fragment plus its direct `grapheme_confusion_variants()` results;
3. drops a variant over the query's maximum total cost;
4. combines fragment options while sharing the total cost and total confusion count across the whole visible pattern;
5. drops combinations over either global budget;
6. retains the minimum cost for each `(fragment tuple, total depth)` state;
7. after each fragment, sorts by `(cost, depth, fragment tuple)` and keeps at most 512 states;
8. returns only nonliteral patterns with at least one confusion.

The query budgets are:

| Visible characters across all fragments | Maximum direct confusions | Maximum total cost |
| ---: | ---: | ---: |
| 1--4 | disabled | n/a |
| 5--7 | 1 | 1.00 |
| 8--24 | 2 | 1.40 |
| >24 | disabled | n/a |

The parser already requires at least two total visible characters for explicit markers, so the one-character row is a defensive statement of the gate. For one-to-four visible characters the pattern list is empty: raw and fixed grapheme-equivalent matching remain possible, but neither direct confusion nor ordinary fuzzy edit tolerance runs. Above 24, direct patterns are also empty. Eight short-confusion guards verify that no returned row claims `visual_gap_grapheme_confusion` below the floor.

For each complete-name and family-head target, the four mutually exclusive stages are:

1. literal `ordered_fragment_match()`;
2. exact ordered match after `visual_grapheme_key()`;
3. exact ordered match against the precomputed direct-confusion patterns;
4. the committed `ordered_fragment_edit_distance(..., maximum_edits=1)` using ordinary Levenshtein edits.

For every exact/direct stage, `minimum_fragment_target_length()` adds fragment lengths, one character for each explicit internal gap, and one for each explicit unanchored edge. `literal_anchor_match_possible()` cheaply checks literal anchored endpoints. `ordered_fragment_match()` starts a later fragment at least one character after the prior fragment end, and starts an unanchored leading fragment at least one character into the target; because `find()` begins at that minimum, it skips an invalid early occurrence and may find a later valid one.

Stage 4 runs only after all earlier stages fail, total visible length is at least five, and every fragment has length at least two. `anchored_fragment_within_one_edit()` cheaply validates start/end fragments. Its fuzzy minimum target length starts with `max(fragment_count, visible_characters - 1)` to allow at most one visible deletion, then adds each required internal and edge gap. Any explicit-gap target no longer than the original visible text is rejected. `ordered_fragment_edit_distance()` itself advances the next segment start by one across every explicit internal/leading gap and requires an unanchored trailing remainder. Thus all four paths enforce one or more hidden target characters for every represented explicit marker; marker-free shorthand deliberately retains zero-gap joins.

The per-exact-family stage code is literal 0, grapheme-equivalent 1, direct confusion 2, and ordinary fuzzy 3. The remaining sort tuple is visible distance, confusion count, hidden characters, descending coverage, family-head before complete-name target, complete-family length, and case-folded family name. Deduplication uses `family.compact`, not broad variant group.

Direct-confusion cost and ordinary edit distance share the `visible_edit_distance` response field, now a float rounded to four decimals. `grapheme_confusion_count` reports direct operations. Any nonzero distance adds `visual_gap_bounded_visible_edit`; a nonzero confusion count also adds `visual_gap_grapheme_confusion`. The obsolete reason `visual_gap_one_visible_edit` is no longer emitted.

`visual_gap_result()` preserves both levels of identity. `name`, `candidate_canonical_name`, and `variant_group` remain the broad display group; `commercial_name`, `matched_family_name`, and `matched_family_key` identify the exact matched base; `candidate_id` is `ALG6-GAP-{family.compact}`. `result_name()` returns the exact `matched_family_name` for this source, so API enrichment, fair evaluation, and the product reranker cannot accidentally collapse/open variant siblings.

Focused exact-tree verification passed **20/20 explicit hard patterns, 9/9 strict-edge negatives, 3/3 strict-internal-gap negatives, 4/4 real-catalog collision patterns, 8/8 short-confusion guards, and 64/64 generated Hit@20**. It also proved exact-family identity, independent BRUFEN bases, a valid later occurrence, marker-free zero-width shorthand, and rejection above four retained fragments. The final 24-character stress run completed loaded-catalog search in **0.068 seconds** under the 512-pattern bound. Earlier profiling observed 511/512 nonliteral patterns and a 20-query preloaded smoke of 2.32 seconds; the identity-aware fair-412 percentile result is recorded in Section 20.6.

### 24.6 Provisional Algorithm 6 diagnostic and disabled gates

`build_consensus()` now defines diagnostic `learned_distance` as the minimum of:

- policy-based `learned_confusion_distance()`; and
- provisional Algorithm 5 weighted `damerau()`.

It converts that minimum to `learned_similarity`. This remains **diagnostic/inactive for ordering** because `consensus_order()` still does not include learned similarity and the loaded rank-one policy remains disabled.

If the rank-one gate is enabled in a future policy, provisional `should_promote()` adds another guard: a base candidate with ordinary Levenshtein similarity exactly 1.0 (within `1e-12`) cannot be displaced. The pre-existing variant-family guard and all configured source/similarity gates still apply. Because `enabled=false`, this new guard currently changes no live Algorithm 6 rank by itself.

### 24.7 Current provisional product/API/UI matrix

| Area | Present in inspected source | Status |
| --- | --- | --- |
| Unitless, ambiguous, package, and presentation number classes | Yes, `app/product_context_reranker.py` | Provisional active on Python context path |
| Complete shared-unit and explicit-unit combination signatures | Yes | Provisional active on Python context path |
| Shared denominators, structural ratios, semicolon metadata/presentation recovery, and invalid-zero fail-closed state | Yes | Provisional active on Python context path; each has separate evidence/conflict semantics |
| Arabic decimal/thousands, Unicode micro, MIU/MCL, time denominators, leading-dot decimals, dotted units/releases | Yes | Provisional normalization/parser boundary |
| Package conjunction, multipack, unit-dose counts, form/container modifiers | Yes | Provisional active; all explicit package constraints must match |
| Qualified exact presentation vs weak bare-unitless presentation | Yes | Exact qualified mass/volume may become `qualified_presentation_exact`; bare number alone remains weak and cannot reorder without the separate strong gate |
| Strict form/container compatibility and route/release scoring | Yes | Provisional active on Python context path; IV/IM/SC and vial/ampoule distinctions remain visible |
| Exact base-family admission boundary | Yes | Exact supplied name is hard; ordinary nonexact context admits rank 1 and qualified ranks 2--3 only; visual admits first three exact matches; broad variant siblings stay closed |
| No-compatible-product abstention/row annotations | Yes | Provisional active on Python context path |
| Prepared exact numeric-brand alias | Yes | Runs first without explicit context/nonvisual; longest exact number+family key wins; recognized suffix only; exact-family-only, capped, confirmation-required |
| Prepared exact >=2-number numeric-only alias | Yes | Runs second without explicit context/nonvisual; can repair empty/incomplete name results; all alias bases bypass top three; no fuzzy/global request-time scan |
| Retrieved-family numeric brand-prefix and attached-number guard | Yes | Longest exact prefix, recognized suffix, exact retrieved bases only; D3/`3 FLY` protections retain literal brand meaning |
| One/two-character strict prefix + numeric + structural context scan | Yes | Exact-base-family candidate exception; disabled for visual-gap mode; too many exact bases abstain |
| Bounded corrected OCR-prefix surfacing | Yes | Length 6--24, cost <=1.40, prefix bucket <=4, global min-cost tail visibility, never rank one |
| Paired-clean OCR safety guards | Yes | Full-name/raw and multi-ligature guards, strict-prefix family-head exception, narrow double-`D -> AL`, and three post-grapheme repairs from Sections 11.10/24.2--24.4 |
| Visual exact-family result identity | Yes | Dedupe/candidate ID/matched fields use exact base; `result_name()` and context consume it; broad group is display only |
| API passes `name_query=query` and `explicit_product_context=bool(product_context)` | Yes, `app/api.py` | Provisional API boundary |
| Stable selected-product identity | Yes, `app/product_context_reranker.py`, `app/api.py`, `app/app.js` | `selected_product_id` survives selection, ID-first hydration, UI dedupe, and radio identity |
| API suppresses conflicting-product display hydration after context failure | Yes, `app/api.py` | Provisional safety/display boundary |
| UI evidence text, conflict badge, tie text, stable product-ID grouping, marker-preserving cache identity, and numeric-alias summaries | Yes, `app/app.js` | Provisional display behavior; unmatched evidence identifiers fall back to readable underscore-separated text |
| Product-details placeholder includes bare `600` example | Yes, `app/index.html` | Provisional display text |
| Browser fallback parity for these Python rules | Partial only | JavaScript gained marker-safe cache identity plus decimal-comma, Arabic-number, and Unicode-micro normalization tests; it does not implement full Python reranker/OCR parity and remains a separate runtime |
| 123 adversarial + nine focused product-context tests | Present | **132/132 passed** on the final exact tree |
| 23 OCR positives + two locked fair + 23 clean/fair safety + 21 exact + seven ambiguity guards | Present, untracked `benchmark_04_experiments/test_algorithm_6_ocr_confusions.py` | All passed with non-transitivity and long-input guard |
| 20 hard visual gaps + nine edge + three internal + four collisions + eight short guards + 64 generated | Present in modified `benchmark_04_experiments/test_algorithm_6_visual_gaps.py` | All passed; final heavy loaded-catalog gap 0.068s |
| Identity-aware fair-412 old/new | `benchmark_04_experiments/evaluate_algorithm_6_ocr_fair.py` | 234/295/340/.633401 -> 234/296/340/.633907, zero paired H1/H5/H20 losses |
| Locked clean 66,257 old/new | Clean synthetic CSV + paired artifact | 65,057/66,027/66,256/.988413 -> 65,142/66,078/66,257/.989317; paired gains/losses 85/0, 51/0, 1/0 |
| Live-server API hardening acceptance | Present, untracked `benchmark_04_experiments/test_algorithm_6_api_hardening.py` | **38/38 passed** against the final local candidate |
| Browser fallback search tests | Present, `app/test_app.js` | JavaScript tests passed; in-app browser connection unavailable, so no DOM/live-UI claim |
| Deterministic 200-case API evaluator | Present, untracked `benchmark_04_experiments/evaluate_algorithm_6_product_context.py` | Locked catalog/case hashes; strict actual-product selection reproduced **197/200 -> 200/200**, three recoveries, zero regressions |

### 24.8 Current verification record and remaining deployment record

Verified on the final exact uncommitted tree:

- product context: **132/132** focused tests;
- OCR/grapheme: **23/23 positives, 2/2 locked fair regressions, 23/23 clean/fair safety regressions, 21/21 literal-name guards, 7/7 global-ambiguity guards**, non-transitivity, and long-input cap passed;
- identity-aware fair 412: old H1/H5/H20/MRR `234/295/340/0.6334013498241085`; new `234/296/340/0.6339070132545293`; zero paired old-Hit@1, old-Hit@5, or old-Hit@20 losses; four intermediate ABASAGLAR losses restored and only `OSTOEND -> OSTOCAL` changed versus old (rank 8 ->3);
- locked clean 66,257: old H1/H5/H20/MRR `65057/66027/66256/0.9884128043253494`; guarded `65142/66078/66257/0.9893173398439633`; paired gains/losses `85/0`, `51/0`, and `1/0`;
- visual gaps: **20/20 explicit, 9/9 strict-edge negatives, 3/3 strict-internal negatives, 4/4 collision patterns, 8/8 short-confusion guards, and 64/64 generated Hit@20** passed, with exact `result_name()` identity; final loaded-catalog heavy-gap search **0.068 seconds** under the 512-state cap;
- local live API hardening: **38/38 endpoint scenarios passed** against the final local candidate;
- locked deterministic product evaluation on the same source: **197/200 name baseline -> 200/200 strict actual-product selections**, LEIL/DIKOL/ARGOTEX recovered, zero regressions;
- JavaScript fallback search tests passed; the in-app browser connection was unavailable, so no live DOM/UI result is claimed;
- Python syntax compilation and diff whitespace checks passed in the coordinating final audit.

The tested local runtime is a candidate only. Still not verified for this uncommitted tree: multi-seed determinism, a new commit/remote ref, and a public endpoint serving that exact commit. The latest verified committed/remote-tracking endpoint in this rulebook therefore remains `66abb7f`; `703c262` remains the prior exact-strength commit. The current tree has reproduced its 197/200 versus 200/200 result locally, but deployment is still pending.

Before anyone marks this appendix active/deployed, record all of the following here or in a linked immutable artifact:

- final commit and branch;
- exact diff of the grapheme registry and product-context constants;
- focused unit-test commands and counts;
- visual-gap regression result, including edge-gap cases;
- any additional clean-synthetic/formal holdout denominators, unsafe-confidence count, and full algorithm-roster/ablation package required for a publication claim;
- immutable artifacts for the reproduced fair-412 and 200-case local results;
- representative BRUFEN `600`, BRUFEN `600 tab`, `javaki + 5 mg`, `x + 500 tab`, and all-conflict abstention API responses;
- Python runtime identity, catalog/product/family counts, public deployment endpoint, and endpoint commit verification;
- any intentional browser-fallback divergence.

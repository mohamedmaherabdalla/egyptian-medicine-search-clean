# Ranking

The ranking model is a rule-based retrieval score, not a machine-learning model.

## Candidate Signals

The app scores candidates using several signals:

| signal | purpose |
| --- | --- |
| Exact normalized name | Highest confidence product match. |
| Compact name | Handles missing punctuation and spacing. |
| Brand/base family | Retrieves all variants under a known brand family. |
| Ingredient key | Supports generic or ingredient-based search. |
| Prefix match | Supports autocomplete-style search. |
| Token overlap | Helps when users type partial product names. |
| Strength match | Boosts candidates with matching dose/strength. |
| Route/form match | Boosts candidates matching tablet, syrup, injection, topical, and similar hints. |
| Approximate spelling | Helps recover typos and heard-spelling variants. |
| Quality penalty | Down-ranks rows with missing or risky metadata. |

## Product Variant Logic

Search is family-first when the query is incomplete. For example, if a user types only a brand family, the app should show the family variants instead of pretending that one exact product is known.

Exact product ranking becomes safer when the query includes enough evidence:

- full product name
- strength
- route/form
- package size
- ingredient or manufacturer context

## Clarification Logic

A result should require clarification when:

- the query is too short
- multiple variants share the same family
- multiple routes exist for the same family
- multiple ingredient combinations exist under the same family
- the match is mostly fuzzy or phonetic
- the top candidates are very close in score
- the row has warning flags


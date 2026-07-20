# Search Mistake-Type Framework

## Two Independent Dimensions

V2 now keeps two different labels:

- `category`: how the test input was corrupted, such as deletion, visual
  confusion, or substring truncation.
- `mistake_type`: why the evaluated search result failed.

One mutation category can produce several mistake types. These dimensions must
not be merged because they answer different engineering questions.

## The Six Mistake Types

| type | name | product behavior |
| --- | --- | --- |
| 1 | Exact real-name collision | Keep as a diagnostic subcategory; exclude from fair retrieval accuracy. |
| 2 | Equal edit evidence | Return an ambiguity group. Do not privilege the first character or force a winner. |
| 3 | Known unreadable position | Use explicit before, middle, or after evidence to retrieve only families that satisfy the visible-fragment pattern. |
| 4 | Family/variant mismatch | Group related brand variants and require the user to choose the exact composition/form. |
| 5 | Candidate-generation failure | Broaden bounded family retrieval; ranking cannot recover an absent candidate. |
| 6 | Candidate-ranking failure | Allow conservative edit-distance dominance only when the observable error relation justifies it. |

## Fair Scoring

If a generated mutation becomes the exact name of another catalog family, the
original expected family is not uniquely inferable. The row remains in the CSV
with `case_subcategory=exact_real_name_collision`, but `scored_case=0` in the
Algorithm 4 result. Raw metrics still include all 115,000 rows. Fair metrics
exclude only these diagnostic collisions.

Legacy continuation rows use:

```text
case_subcategory=known_prefix_unreadable_continuation
unreadable_continuation=1
```

This distinguishes plain `ABIMOL` from `ABIMOL` plus the observation that more
unreadable characters follow.

The application and Algorithm 4 also accept the complete positional request:

```text
unreadable_mode=before
unreadable_mode=after
unreadable_mode=middle
ending_fragment=<required second visible fragment for middle>
```

For example, `abimol` with mode `after`, `molextra` with mode `before`,
and `abi` plus ending fragment `extra` with mode `middle` all provide
position-specific evidence for `ABIMOL EXTRA`. These modes are strict: if no
family satisfies the stated pattern, search returns no match instead of falling
back to unrelated ordinary results. The old `unreadable_continuation=1` field
remains a backward-compatible alias for `unreadable_mode=after`.

## Ranking Policy

Edit distance is not a universal sorting rule.

- Different distances can justify reordering for a pure insertion/deletion or
  a close single-token candidate competing with a multi-token false positive.
- Equal distances remain in the established evidence order and produce an
  ambiguity response.
- No character position, including the first character, wins automatically.
- Explicit continuation, strength, form, route, and family evidence take
  precedence over generic spelling bonuses.

## Application States

The browser search now returns a specific `decision_type`:

```text
ranked_matches
possible_matches
collision_ambiguity
equal_distance_ambiguity
unreadable_continuation_matches
unreadable_after_matches
unreadable_before_matches
unreadable_middle_matches
family_variant_selection
no_match
```

The interface includes an unreadable-position selector. Middle-gap mode exposes
a second visible-fragment input. Related variants remain grouped so ingredients,
route, product name, and price can be compared before selection.

## Verified Result

| metric | mistake-framework Algorithm 4 | OCR-guided Algorithm 4 | delta |
| --- | ---: | ---: | ---: |
| Raw Hit@1 | 81.86% | 82.12% | +0.26 percentage points |
| Raw Hit@20 | 92.99% | 93.41% | +0.42 percentage points |
| Behavior success | 93.09% | 93.64% | +0.55 percentage points |
| Unsafe confident top-1 | 0.00% | 0.00% | unchanged |
| Fair Hit@1 | 85.60% | 85.87% | +0.27 percentage points |
| Fair Hit@20 | 95.21% | 95.65% | +0.44 percentage points |

Against the immediately preceding Algorithm 4 artifact, the final full rerun
produced 180 Hit@1 gains and 95 losses, plus 132 Hit@20 gains and five losses.
The net changes are +85 top-1 rows and +127 top-20 rows. The 50-case manual
benchmark remains at 74% Hit@1 and 94% Hit@20.

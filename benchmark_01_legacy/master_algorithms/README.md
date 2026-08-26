# Master Commercial-Name Search

`master_commercial_name_search.py` combines the two measured search approaches:

| child | measured strength used by master |
| --- | --- |
| current app evaluator | Safety gates, clarification behavior, strength/form context, keyboard-shift recovery, exact and prefix handling. |
| external English fast algorithm | Stronger retrieval on typo-heavy commercial-name queries, visual/phonetic corruption, deletion/insertion/transposition, and multi-error cases. |

## Design

The master algorithm is a family-level rank-fusion engine:

1. Run the current app search and the external English fast search.
2. Deduplicate candidates by commercial family/base group.
3. Score each family using weighted reciprocal-rank fusion.
4. Give external rank-1 extra influence only for clean typo-like brand queries.
5. Give current rank-1 extra influence for likely whole-keyboard-shift cases when external is not confident.
6. Preserve current-app clarification behavior and mark unsupported external-only rescues as ambiguous rather than confident.

This means retrieval can benefit from external typo recovery while safety remains conservative. In medical search, returning candidates with clarification is preferred over making a confident wrong top-1 call.

## Versioned Rescue Algorithms

| Algorithm | Module | Meaning |
| --- | --- | --- |
| Algorithm 4 | `algorithm_4_commercial_name_search.py` | Original bounded family-rescue implementation used by the Meeting 10 OCR and ablation reports. |
| Algorithm 5 | `algorithm_5_commercial_name_search.py` | Evidence-guided mixed-error retrieval and bounded reranking accepted on the 66,257-pair clean core. |

Algorithm 5 has its own stable implementation and result identifier. Historical
Algorithm 4 artifacts keep their original name.

## Algorithm 5 Human-Evidence Rules

Algorithm 5 applies general character evidence. Medicine names are not encoded
as exceptions. The examples below are regression tests or benchmark rows.

### Character Confusion Costs

| Evidence | Cost | Meaning | Example |
| --- | ---: | --- | --- |
| Same character | 0.00 | The visible character agrees exactly. | `A` compared with `A`. |
| Common letter confusion | 0.45 | The pair belongs to `C/K/Q`, `S/Z`, `F/V`, `P/B`, `D/T`, `G/J`, `M/N`, `I/E/Y`, or `O/U`. | `F` compared with `V`. |
| OCR digit read as a letter | 0.45 | A single OCR digit may represent `0/O`, `1/I/L`, `2/Z`, `3/E`, `4/A`, `5/S`, `6/G`, or `8/B`. The mapping is directional from OCR input to candidate. | `0IANTA` gives stronger visual evidence to an `O...` candidate than an unrelated `S...` candidate. |
| Multi-character visual ligature | Bounded rewrite | A documented multi-character shape can represent one candidate letter. The rewrite is directional and cannot repeat without another evidence rule. | Visible `IV` may represent candidate `N`, so `LAIVTUS` can retrieve the `LANTUS` family; `N` is not automatically expanded back to `IV`. |
| Vowel substitution | 0.70 | A changed vowel is less severe than an unrelated replacement, but is not treated as exact. | `A` compared with `I`. |
| Adjacent transposition | 0.55 | Two neighboring characters appear in reverse order. | `AB` compared with `BA`. |
| Ordinary replacement, insertion, or deletion | 1.00 | No supported confusion explains the edit. | Missing `S` in `ABAAGLAR` compared with `ABASAGLAR`. |

These costs rank evidence; they do not prove a medicine identity. Candidate
promotion still needs catalog, boundary, position, and score-gap checks.

### Accepted Ranking Rules

| Rule | Required evidence | Action | Concrete example |
| --- | --- | --- | --- |
| Compact visible text | Remove case, spaces, and punctuation before spelling comparison. | Preserve every visible letter while ignoring formatting noise. | `A BAA G LAR` becomes `ABAAGLAR`. |
| Validated family-head retrieval | Query length is 5--18; a catalog-derived family head is within two edits; its first character is equal or from a supported confusion group. Candidates come from exact, phonetic, and symmetric deletion-key indexes. | Retrieve the family without scanning every catalog head. | `ABAAGLAR` retrieves catalog head `ABASAGLAR`, one insertion away. |
| Unique closer family head | Exactly one validated head is closer than the current top result and starts with the same visible first character. An earlier specialized correction remains protected unless the head is one edit away and preserves both visible boundaries. | Move that family to rank 1 and retain clarification. | `A BAA G LAR` moves `ABASAGLAR` to rank 1. `LANUS` moves `LANTUS` ahead of a weaker two-edit chain. |
| Close-head shortlist | A validated head is within two edits but lacks enough evidence for rank 1. | Put one representative of that family near the top so the user can compare it. | Ambiguous package variants receive one family vote, not one vote per package row. |
| Short visible-head reservation | A three- or four-character query is an exact prefix of a catalog-derived family head, or is an ordered fragment missing at most two head characters. Keep one representative per head and at most four representatives. | Reserve positions near the end of the top 20. Do not promote the family to rank 1 from this weak evidence. | `LAN` surfaces a `LANTUS` variant at rank 19; `LANS` preserves `L`, `A`, `N`, and final `S`, so `LANTUS` appears at rank 20. Both responses remain ambiguous. |
| Directional visual-ligature retrieval | One visible-query `IV` is rewritten to candidate-side `N`, and the rewritten text exactly or closely supports a catalog name or validated family head. | Add the candidate and score the rewritten evidence. Do not apply the reverse rewrite automatically. | `LAIVTUS` retrieves the `LANTUS` family through `IV -> N`. |
| Exact-chain reservation | A candidate has an exact supported transformation chain, such as ligature plus vowel change or transposition plus deletion, but falls below the generic rescue cutoff. | Reserve up to 12 chain-supported candidates for final ranking instead of discarding them before the top-20 decision. | `ROPIL` keeps `ORA PAL` available for the final reranker rather than losing it at rescue rank 25. |
| Strictly closer full name | A rescue-only full name is within three edits, at least one edit closer, improves weighted distance by at least 0.35, improves combined prefix-plus-suffix evidence by at least 0.05, is in the first five rescue candidates, and trails the current score by at most 0.35. Exact, prefix, and combined phonetic evidence on the current top remain protected. | Correct a small score inversion supported by spelling and both word edges. | `MYOLANA` moves `MYOLAX` ahead of `MYOLASTAN`; `NEITROSET` moves `NEUROCET` ahead of `NEUTRI SOFT`. |
| Two-sided equal-distance correction | Top and alternative have the same ordinary distance, at most two edits. The alternative matches both the first and last visible characters, has no worse weighted distance, ordered-character evidence, or edge evidence, and lies within a 0.40 score gap. At distance two, it must have lower weighted distance or preserve at least one additional ordered visible character. | Promote only a uniquely supported alternative. | For `CEFAXIME`, `CEFIXIME` preserves `C...E` and has weighted distance 0.70; `CEFAXIM` loses the final `E` and has weighted distance 1.00. |
| Preserve unresolved ties | The alternative does not dominate on the bounded evidence above, or several alternatives have the same evidence signature. | Keep the existing score order and return an ambiguity response. | `KETONOLAE` keeps `KETOROLAC`; the last-character clue alone is insufficient to reorder it. |

The two-sided rule is deliberately not a universal “matching first and last
letters wins” rule. It cannot override an exact catalog name, a strictly closer
candidate, a large score gap, weaker internal character order, or equally
supported alternatives.

### Measured Effect

The locked OCR comparison uses 464 collision-free unique query-target pairs.

| System | Hit@1 | Hit@20 | Unsafe confident wrong top-1 | Median query time |
| --- | ---: | ---: | ---: | ---: |
| Frozen Algorithm 4 | 221/464 (47.6293%) | 330/464 (71.1207%) | 0 | 14.4015 ms |
| Algorithm 5 before these rules | 213/464 (45.9052%) | 328/464 (70.6897%) | 0 | 21.2360 ms |
| Algorithm 5 with human-evidence rules | **225/464 (48.4914%)** | **335/464 (72.1983%)** | **0** | 31.7140 ms |

Against the previous Algorithm 5 result, the new rules add 12 Hit@1
recoveries and seven Hit@20 recoveries with zero paired losses. The seventh
Hit@20 gain is `LANS -> LANTUS`, which moves from outside the list to rank 20.
Hit@1 gains include
`A BAA G LAR` to `ABASAGLAR`, `LANFUS` to `LANTUS`, `CEFAXIME` to `CEFIXIME`,
`LAMIX` to `LASIX`, `NEITROSET` to `NEUROCET`, and `MYOLANA` to `MYOLAX`.
The broader evidence search raises median latency by 10.478 ms, so the accuracy
gain is not free. A deterministic 1,870-case sample covering all 20 clean-core
categories retained exactly 1,842 Hit@1 and 1,870 Hit@20 successes, with no
paired regression against the previous Algorithm 5 build.

## Final V2 Result

Full report:

`benchmark_02_synthetic/results/01_full_benchmark/algorithm_1_3_comparison.md`

Headline on 115,000 generated v2 cases:

| metric | current | external | master |
| --- | ---: | ---: | ---: |
| Hit@1 | 75.26% | 79.30% | 81.03% |
| Hit@20 | 88.40% | 91.84% | 93.09% |
| Behavior success | 88.66% | 91.29% | 93.33% |
| Unsafe confident top-1 | 0.02% | 6.40% | 0.00% |

Coverage audit:

| check | result |
| --- | ---: |
| evaluated rows | 115,000 |
| categories covered | 34 / 34 |
| detailed error-type buckets covered | 4,243 / 4,243 |
| missing category buckets | 0 |
| missing error-type buckets | 0 |
| blank comparison context cells | 0 |

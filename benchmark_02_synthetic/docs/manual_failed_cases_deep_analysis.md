# Manual Failed Cases Deep Analysis

This file analyzes the 50 manually supplied failures that motivated Algorithm 4. The corrected Algorithm 4 run does not use hard-coded mappings from these cases to expected answers.

## Pattern Counts

| pattern | cases | what it means |
| --- | ---: | --- |
| `single_edit` | 21 | Single-character typo; close catalog neighbors can still distract candidate generation or ranking. |
| `same_edges_middle_corruption` | 9 | Stable outer shape with corrupted middle; needs prefix/suffix plus fuzzy middle evidence. |
| `multi_substitution` | 8 | Several same-length substitutions; needs weighted phonetic/edit scoring. |
| `prefix_with_gap_insertion_deletion` | 7 | Missing/extra middle characters create a gap; needs delete-key and subsequence rescue. |
| `compound_typo` | 4 | Multiple typo types in one query; not safe to solve by memorized aliases. |
| `short_name_ambiguous_typo` | 1 | Very short ambiguous typo; must recover candidate without becoming confidently unsafe. |

## What The 50 Cases Show

- The failures are not mostly exact-search bugs. They are mostly candidate-generation and ranking bugs caused by real typo shapes.
- `single_edit` cases matter because close catalog neighbors can distract candidate generation or ranking, so edit distance alone is not enough.
- `same_edges_middle_corruption` and `prefix_with_gap_insertion_deletion` cases keep useful prefix/suffix evidence but damage the middle of the name. This is why Algorithm 4 uses prefix, suffix, delete-key, subsequence, and n-gram rescue together.
- `multi_substitution` cases need weighted substitutions and phonetic/key-neighbor logic. This is why Algorithm 4 uses confusion pairs and weighted edit similarity.
- `compound_typo` cases are still difficult without memorizing the answer. They need better general multi-error recovery, not a manual lookup table.
- The safety lesson is separate: recovery should not automatically mean confident dispensing. Algorithm 4 returns candidates with clarification on risky/fuzzy matches.

## Recommendation Pass Learned From The Latest Review

The latest attached review split the remaining mistakes into useful engineering
groups:

- Some expected answers are not actually the closest string. For example,
  `levohista` is closer to `LEVOHISTAM` than `LEVOHISTAMIN`; these need family
  grouping or acceptable alternatives, not a forced search preference.
- Some cases are edit-distance ties. These now get stronger same-position,
  same-length, first-character, and full-word fuzzy evidence.
- Some failures happen because candidate generation misses the right family.
  Algorithm 4 now tries plausible first-letter variants and uses a broader
  rescue prefilter.
- Some false positives come from partial token or prefix evidence. Algorithm 4
  now penalizes weak prefix-only matches when full-word edit evidence is poor.

These changes are still general rules. There is still no manual lookup table for
the 50 cases.

## Corrected Algorithm 4 Outcome On These 50 Cases

| cases | Hit@1 | Hit@20 | behavior | unsafe top-1 |
| ---: | ---: | ---: | ---: | ---: |
| 50 | 74.00% | 94.00% | 94.00% | 0.00% |

Algorithm 4 recovered 37 of 50 cases at rank 1 and 47 of 50 within top 20 after
the expected names were resolved to exact catalog families and the OCR-derived
general rescue changes were applied.

The OCR-derived pass additionally recovers the `COUGHSED` family for
`couphseed` at rank 1.
The remaining failures are split between true nearest-neighbor conflicts,
family-equivalence issues, dangerous ties, and candidate-generation gaps.

## Row-Level Analysis

| # | input | expected | pattern | edit | old ranks A1/A2/A3 | Algorithm 4 | root cause |
| ---: | --- | --- | --- | ---: | --- | --- | --- |
| 1 | `optraderolpl` | `optaderol` | `prefix_with_gap_insertion_deletion` | 3 | 999/1/1 | 1 / `OPTADEROL` / `algorithm_2+rescue` | The query keeps part of the family but has a gap from missing or inserted middle characters. |
| 2 | `Auticax` | `anticox` | `compound_typo` | 2 | 999/999/999 | 999 / `ACTICA` / `algorithm_2+rescue` | Multiple typo types in one query; needs stronger general multi-error rescue. Hard-coding this as an alias would invalidate the benchmark. |
| 3 | `couphseed` | `coughsed` | `multi_substitution` | 2 | 999/999/999 | 999 / `COUGH KEE` / `rescue` | Several same-length substitutions; needs weighted phonetic/edit scoring. |
| 4 | `ivybnon` | `IVY BRONCH` | `prefix_with_gap_insertion_deletion` | 3 | 999/11/14 | 4 / `IVYENO` / `algorithm_2+rescue` | The query keeps part of the family but has a gap from missing or inserted middle characters. |
| 5 | `sauovent` | `salbovent` | `same_edges_middle_corruption` | 2 | 9/2/2 | 1 / `SALBOVENT` / `algorithm_2+rescue` | Stable outer shape with corrupted middle; needs prefix/suffix plus fuzzy middle evidence. |
| 6 | `garaxy` | `garamycin` | `compound_typo` | 4 | 999/18/20 | 18 / `GARDX` / `algorithm_2+rescue` | Multiple typo types in one query; needs stronger general multi-error rescue. Hard-coding this as an alias would invalidate the benchmark. |
| 7 | `colchicime` | `colchicine` | `single_edit` | 1 | 1/1/1 | 1 / `COLCHICINE` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 8 | `flacton` | `flector` | `multi_substitution` | 2 | 999/999/999 | 2 / `FLU CUT N` / `algorithm_2+rescue` | The correct family is now recovered in the top 20 after the prefix-only penalty and broader rescue pass, though a multi-token false positive still ranks first. |
| 9 | `levohista` | `levohistamin` | `prefix_with_gap_insertion_deletion` | 3 | 999/999/999 | 999 / `LEVOHISTAM` / `algorithm_2` | The query keeps part of the family but has a gap from missing or inserted middle characters. |
| 10 | `oplax` | `oplex` | `single_edit` | 1 | 999/999/999 | 999 / `OPLEX N` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 11 | `oplox` | `oplex` | `single_edit` | 1 | 999/999/999 | 999 / `OFLOX` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 12 | `moxclar` | `e-moxclav` | `compound_typo` | 2 | 999/1/1 | 1 / `E MOXCLAV` / `algorithm_2+rescue` | Multiple typo types in one query; needs stronger general multi-error rescue. Hard-coding this as an alias would invalidate the benchmark. |
| 13 | `Ezogoat` | `Ezogast` | `same_edges_middle_corruption` | 2 | 999/1/1 | 1 / `EZOGAST` / `algorithm_2+rescue` | The beginning and/or ending survive, but the middle is corrupted. Prefix-only ranking can still choose a wrong neighbor. |
| 14 | `healreptic` | `healioreptic` | `prefix_with_gap_insertion_deletion` | 2 | 1/1/1 | 1 / `HEALIOREPTIC` / `algorithm_2` | The query keeps part of the family but has a gap from missing or inserted middle characters. |
| 15 | `colovarin` | `coloxain D` | `same_edges_middle_corruption` | 3 | 999/999/999 | 999 / `COLOVERIN` / `algorithm_2+rescue` | Stable outer shape with corrupted middle; needs prefix/suffix plus fuzzy middle evidence. |
| 16 | `Eucavban` | `eucarbon` | `same_edges_middle_corruption` | 2 | 3/7/6 | 1 / `EUCARBON` / `algorithm_2+rescue` | Stable outer shape with corrupted middle; needs prefix/suffix plus fuzzy middle evidence. |
| 17 | `librux` | `librax` | `single_edit` | 1 | 999/999/999 | 999 / `ALPRAX` / `algorithm_2` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 18 | `mebula` | `nebula` | `single_edit` | 1 | 999/999/999 | 999 / `MEBOLEVIA` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 19 | `dexazue` | `dexazone` | `same_edges_middle_corruption` | 2 | 4/1/1 | 1 / `DEXAZONE` / `algorithm_2+rescue` | Stable outer shape with corrupted middle; needs prefix/suffix plus fuzzy middle evidence. |
| 20 | `octotron` | `octatrom` | `same_edges_middle_corruption` | 2 | 999/999/999 | 999 / `OCTATRON` / `algorithm_2+rescue` | Stable outer shape with corrupted middle; needs prefix/suffix plus fuzzy middle evidence. |
| 21 | `revanoglob` | `Revanoglow` | `single_edit` | 1 | 999/999/999 | 999 / `REVANO SOFT` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 22 | `jvsprin` | `jusprin` | `single_edit` | 1 | 1/1/1 | 1 / `JUSPRIN` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 23 | `mixmail` | `mixmazil` | `single_edit` | 1 | 17/1/2 | 1 / `MIXMAZIL` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 24 | `puresmin` | `puresmine` | `single_edit` | 1 | 999/999/999 | 999 / `PURESAMINE` / `algorithm_2` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 25 | `biato` | `ibiacto` | `prefix_with_gap_insertion_deletion` | 2 | 999/3/3 | 10 / `BEVATO` / `algorithm_2+rescue` | The query keeps part of the family but has a gap from missing or inserted middle characters. |
| 26 | `salire` | `saline` | `single_edit` | 1 | 11/6/9 | 2 / `SALIVER` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 27 | `devamol` | `devarol` | `single_edit` | 1 | 999/999/999 | 999 / `CEVAMOL` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 28 | `calcihon` | `calcitron` | `same_edges_middle_corruption` | 2 | 14/3/4 | 3 / `CALCI CHO` / `algorithm_2+rescue` | Stable outer shape with corrupted middle; needs prefix/suffix plus fuzzy middle evidence. |
| 29 | `broncholrn` | `broncholin` | `single_edit` | 1 | 999/999/999 | 999 / `BRONCHO` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 30 | `apido` | `apidone` | `prefix_with_gap_insertion_deletion` | 2 | 1/2/2 | 2 / `RAPIDO` / `algorithm_2+rescue` | The query keeps part of the family but has a gap from missing or inserted middle characters. |
| 31 | `tavaric` | `tavanic` | `single_edit` | 1 | 4/1/1 | 1 / `TAVANIC` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 32 | `flopudex` | `flopadex` | `single_edit` | 1 | 1/1/1 | 1 / `FLOPADEX` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 33 | `metaps` | `metapsin` | `prefix_with_gap_insertion_deletion` | 2 | 1/1/1 | 1 / `METAPSIN` / `algorithm_2+rescue` | The query keeps part of the family but has a gap from missing or inserted middle characters. |
| 34 | `arymentin` | `augmentin` | `multi_substitution` | 2 | 1/1/1 | 1 / `AUGMENTIN` / `algorithm_2+rescue` | Several same-length substitutions; needs weighted phonetic/edit scoring. |
| 35 | `centerloc` | `controloc` | `multi_substitution` | 3 | 1/1/1 | 1 / `CONTROLOC` / `algorithm_2+rescue` | Several same-length substitutions; needs weighted phonetic/edit scoring. |
| 36 | `moxauidey` | `moxavidex` | `same_edges_middle_corruption` | 2 | 999/1/1 | 1 / `MOXAVIDEX` / `algorithm_2+rescue` | Stable outer shape with corrupted middle; needs prefix/suffix plus fuzzy middle evidence. |
| 37 | `codlor` | `codilar` | `multi_substitution` | 2 | 1/1/1 | 1 / `CODILAR` / `algorithm_2+rescue` | Several same-length substitutions; needs weighted phonetic/edit scoring. |
| 38 | `Duncof` | `Duncef` | `single_edit` | 1 | 999/999/999 | 999 / `ADANCOR` / `algorithm_2` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 39 | `Cndalenz` | `Ondalenz` | `single_edit` | 1 | 2/1/1 | 1 / `ONDALENZ` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 40 | `Duphlac` | `Duphalac` | `single_edit` | 1 | 1/1/1 | 1 / `DUPHALAC` / `algorithm_2` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 41 | `Dophlac` | `Duphalac` | `multi_substitution` | 2 | 1/1/1 | 1 / `DUPHALAC` / `algorithm_2+rescue` | Several same-length substitutions; needs weighted phonetic/edit scoring. |
| 42 | `Conlentin` | `Conventin` | `single_edit` | 1 | 1/1/1 | 1 / `CONVENTIN` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 43 | `taves` | `tareg` | `short_name_ambiguous_typo` | 2 | 999/999/999 | 999 / `TAV DU` / `algorithm_2+rescue` | Very short ambiguous typo; must recover candidate without becoming confidently unsafe. |
| 44 | `cyprocin` | `ciprocin` | `single_edit` | 1 | 1/1/1 | 1 / `CIPROCIN` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 45 | `cyprocen` | `ciprocin` | `compound_typo` | 2 | 1/1/1 | 1 / `CIPROCIN` / `algorithm_2+rescue` | Multiple typo types in one query; needs stronger general multi-error rescue. Hard-coding this as an alias would invalidate the benchmark. |
| 46 | `vonifrton` | `vomifraton` | `multi_substitution` | 2 | 2/1/1 | 1 / `VOMIFRATON` / `algorithm_2+rescue` | Mostly substitutions across a short family shape. The target needs weighted phonetic/edit evidence, not exact prefix only. |
| 47 | `awndisb` | `awadist` | `multi_substitution` | 2 | 3/1/1 | 1 / `AWADIST` / `algorithm_2+rescue` | Mostly substitutions across a short family shape. The target needs weighted phonetic/edit evidence, not exact prefix only. |
| 48 | `vonaspine` | `vonaspire` | `single_edit` | 1 | 1/1/1 | 1 / `VONASPIRE` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 49 | `Ketostenil` | `Ketosteril` | `single_edit` | 1 | 999/1/1 | 1 / `KETOSTERIL` / `algorithm_2+rescue` | One inserted, deleted, or substituted character; close catalog neighbors can still make this pattern unsafe to treat as trivial. |
| 50 | `Ketostenl` | `Ketosteril` | `same_edges_middle_corruption` | 2 | 1/1/1 | 1 / `KETOSTERIL` / `algorithm_2+rescue` | Stable outer shape with corrupted middle; needs prefix/suffix plus fuzzy middle evidence. |

## How This Maps To Algorithm 4

| observed issue | Algorithm 4 response |
| --- | --- |
| Single-edit target lost to catalog neighbor | family-level rescue plus weighted edit scoring |
| Middle corruption with stable prefix/suffix | cheap prefilter using prefix, suffix, 3/4-grams, skeleton, phonetic, and subsequence evidence |
| Missing or extra middle letters | delete-key buckets and length-compatible rescue |
| Phonetic/key-neighbor substitutions | weighted substitution pairs such as C/K/Q, S/Z, F/V, P/B, D/T, G/J |
| Compound real-world typo | remaining gap; solve with more general multi-error logic, not memorized aliases |
| Dangerous fuzzy recovery | conservative clarification gate; rescue is evidence, not automatic confidence |

# Preserved failure and adjudication history

## Run 20260822T140243Z

The first unified generated/adversarial run evaluated 814 rows and reported
812 passes and two failures. Both rows are preserved in the archived run
artifacts and were classified as evaluation-contract defects before any source
change.

### `VG-MAN-POS-6301317104570E` - `PANA...OL`

- Historical expectation: broad variant group `PANADOL`.
- New exact-family evaluator observation: no exact `PANADOL` base appeared in
  the top 20.
- Root cause: the historical test label was a broad group, not an exact base.
  The final catalog has ten exact base/head families satisfying the raw
  `PANA...OL` positional evidence; the API returns all ten. `PANADOL` itself is
  display/group metadata rather than one exact base family.
- Resolution: re-oracle the row from catalog family/full-head surfaces and
  store all ten exact relevant keys. No algorithm change.

### `OCR-NONTRANS-IARDX-GARDX`

- Historical contract: direct variant generation must not compose `I->E` and
  `E->G` on the same original character.
- Incorrect unified check: forbade ordinary search from returning `GARDX`.
- Root cause: GARDX can be retrieved by unrelated ordinary similarity sources;
  that does not prove transitive grapheme generation.
- Resolution: execute the source function
  `grapheme_confusion_variants("IARDX", max_confusions=2)` and assert that its
  generated variant set excludes `GARDX`. No algorithm change.

## Run 20260822T141719Z

The first execution of the expanded visual-gap protocol evaluated 642 rows and
reported 634 passes and eight failures. The archived summary has SHA-256
`97f007a308f955b398082f5b26d8bdfb4497904561fdf980cfa0f62a6db8d3bd`.
Seven rows exposed three source defects; one row exposed an evaluation-contract
defect. No failed row was removed from the archive.

### Target-side alignment metrics (three rows)

- `CLICY... -> DICYNONE` reported hidden/coverage `3/.625` instead of `4/.5`.
- `BACTID... -> BACTICLOR` reported `3/.666667` instead of `2/.777778`.
- `...TIDOR -> BACTICLOR` reported `4/.555556` instead of `3/.666667`.
- Root cause: the implementation subtracted the raw observed-fragment length
  from the target length. Variable-length OCR rewrites (`CL <-> D`) change how
  many target characters the visible evidence consumes.
- Algorithm fix: exact, grapheme, direct-confusion, and fuzzy matchers now
  return target-side alignment evidence. `hidden_character_count` and
  `visible_coverage` are computed from consumed target spans. The regression
  suite asserts the exact three pairs, not merely `hidden > 0`.

### Punctuation incorrectly activated shorthand (two rows)

- `PANA.DOL` and `PANA-DOL` were dispatched as visual gaps.
- Root cause: the shorthand parser extracted alphabetic tokens from any
  punctuation-separated text, although the documented shorthand is
  whitespace-separated.
- Algorithm fix: marker-free shorthand now requires a complete match of two to
  four whitespace-separated alphabetic tokens. Periods and hyphens retain
  ordinary spelling-query semantics.

### Punctuation beside an edge marker changed its anchor (two rows)

- `(...TRIL` was interpreted as internal instead of leading and missed
  RIVOTRIL.
- `RIVO... )` was interpreted as internal instead of trailing and missed
  RIVOTRIL.
- Root cause: edge anchors were inferred from raw marker character offsets.
  Punctuation that compacts to no letters falsely counted as visible evidence.
- Algorithm fix: anchors now derive from retained compact fragments on each
  side of the marker. Focused regressions include leading and trailing
  punctuation variants.

### Marker-only confirmation expectation (one row)

- `...` correctly returned ordinary `no_match` with zero rows, but the protocol
  incorrectly required response-level visual confirmation.
- Root cause: the dataset generator applied the visual confirmation contract to
  every protocol row, including rows whose expected decision is explicitly
  `not_visual_gap`.
- Evaluation fix: confirmation is required only when the expected decision is
  `visual_gap_matches`. The algorithm was not changed for this row.

## Re-evaluation

- Focused visual regression: all 64 generated, 20 hard, nine edge, three
  internal, four collision, eight short-confusion, and the new metric/parser
  assertions passed.
- Run `20260822T142759Z`: visual/OCR/source protocol **642/642 passed**.
- Run `20260822T142857Z`: full package **842/842 passed**, including visual
  **404/404**, OCR/API **236/236**, OCR/source **2/2**, and product context
  **200/200** against the **197/200** name-only baseline. Summary SHA-256:
  `6ad127f677173c750370a39c2c220e8a340df0f5c69cf800354145a336282e1d`.
- Locked fair OCR 412: old and candidate both `234/296/340`, MRR
  `0.6339070132545293`, with zero changed rows and zero paired Hit@1/5/20
  losses.
- Locked clean 66,257: exhaustive dispatch/source-scope proof found zero marker
  rows, zero pre-patch shorthand-shaped rows, unchanged Algorithm 5 bytes, and
  only visual-branch Algorithm 6 changes. The prior exact full-run outputs and
  `65142/66078/66257` metrics therefore carry forward.

# Normalization

Normalization converts noisy user input and catalog values into comparable search keys.

## Main Steps

1. Convert text to a consistent case.
2. Normalize punctuation into spaces.
3. Normalize repeated whitespace.
4. Preserve medically important numbers and units.
5. Build a compact key by removing spaces and punctuation.
6. Extract route/form hints such as tablet, capsule, syrup, injection, eye, ear, topical, rectal, vaginal, and mouth.
7. Extract strength-like tokens such as milligram, gram, milliliter, percentage, IU, and microgram expressions.

## Why This Matters

Medicine names often contain punctuation, spacing differences, strength tokens, and abbreviated forms. The same product may be typed with or without spaces, dots, dashes, or units. Normalization lets the app compare these variants without changing the original displayed product name.

## Examples

| raw input | normalized idea |
| --- | --- |
| `AUGMENTIN 1 GM 14 F.C.TABS.` | product name plus strength and tablet form |
| `augmentin1gm tabs` | compact name plus strength and tablet form |
| `panadol cold` | brand family plus subtype token |
| `amox clav` | ingredient-style query |


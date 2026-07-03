# Known Limitations

## Search Limitations

- The current public demo is still a prototype.
- Browser-side scoring is acceptable for 25,066 rows but may need indexes for larger data.
- Heard-spelling recovery is difficult and can still confuse similar medicine names.
- Very short queries are inherently ambiguous.
- Brand-only queries often map to many variants.

## Data Limitations

- Some records have missing composition.
- Some records have unknown route/form.
- Some records include unavailable or cancelled status markers.
- Some warnings come from rule-based parsing and should be reviewed.
- Price may be stale or source-specific and should not drive medical correctness.

## Safety Limitations

This app should not prescribe, substitute, or select a medicine automatically. It is a retrieval tool that helps users find candidates and inspect evidence.


# Warnings

Warnings are data-quality signals shown to users and used during ranking.

## Warning Sources

| warning group | meaning |
| --- | --- |
| Missing scientific composition | The product lacks reliable ingredient/composition evidence. |
| Unknown route | The source route/form field is unknown-like. |
| Name status marker | Product name contains status text such as unavailable or cancelled markers. |
| Missing manufacturer | Manufacturer evidence is absent. |
| Missing or placeholder class | Drug class is empty or placeholder-like. |
| Route/name mismatch | The product name suggests one form while the route field suggests another. |
| Duplicate/conflict | Similar normalized names disagree on metadata. |
| Metadata row | A row appears to describe file metadata rather than a medicine. |
| Price outlier | Price is unusually low or high and should be treated carefully. |

## Product Behavior

Warnings should not automatically delete candidates. They should be visible evidence. The app may down-rank risky rows, but it should still show them when they are the best catalog evidence for the query.


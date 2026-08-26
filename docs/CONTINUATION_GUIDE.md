# Continuing the Algorithm 6 project

This branch is the continuation-ready Algorithm 6 package. It keeps the
deployable UI and API, the exact runtime algorithms, focused safety tests,
locked evaluation inputs, compact result evidence, and the source and reports
needed to understand the preceding benchmark generations.

## Start here

| Goal | Path |
| --- | --- |
| Run the web application | `app/` and the root `Dockerfile` |
| Change commercial-name retrieval | `benchmark_01_legacy/master_algorithms/` |
| Change product-context selection | `app/product_context_reranker.py` |
| Review every active rule | `docs/ALGORITHM_6_COMPLETE_RULEBOOK.md` |
| Add or regenerate rule tests | `algorithm_6_rule_evaluation/generators/` |
| Run focused acceptance tests | `benchmark_04_experiments/test_algorithm_6_*.py` |
| Review the concise team explanation | `output/pdf/medicine_search_team_handbook.pdf` |
| Review the exhaustive reference | `output/pdf/algorithm_6_rule_evaluation.pdf` |

The browser UI in `app/` is the Algorithm 6 UI. Do not replace it with files
from `gh-pages` or from the separate clean/v1 implementation; those branches
use different API and ranking contracts.

## Reproduce the continuation gate

Create a Python 3.11 environment, install `app/requirements-api.txt`, and run:

```bash
node --check app/app.js
node app/test_app.js

python -m unittest \
  app.test_product_context_reranker \
  app.test_product_context_hardening \
  benchmark_01_legacy.test_case_generation.test_generation_unit \
  benchmark_02_synthetic.test_mistake_framework \
  algorithm_6_rule_evaluation.evaluators.test_result_contracts \
  algorithm_6_rule_evaluation.evaluators.test_provenance

python benchmark_04_experiments/test_algorithm_6_ocr_confusions.py
python benchmark_04_experiments/test_algorithm_6_visual_gaps.py
```

The optional OCR research unit tests require the dependencies in
`benchmark_03_ocr/requirements-ocr.txt`. Run them from the repository root:

```bash
PYTHONPATH=benchmark_03_ocr python -m unittest discover \
  -s benchmark_03_ocr/tests -p 'test_*.py'
```

The versioned locked inputs are:

- `algorithm_6_rule_evaluation/test_sets/locked/fair_ocr_412.csv`;
- `algorithm_6_rule_evaluation/test_sets/locked/fair_ocr_excluded_52.csv`;
- `algorithm_6_rule_evaluation/test_sets/locked/synthetic_clean_66257.csv`.

The rule-test generator validates these files in place by SHA-256. It does not
require a sibling checkout.

`test_sets/manifests/generation_manifest.json` and selected result summaries
are immutable records of the accepted 2026-08-22 runs. Their original machine
paths are retained because changing those bytes would break the published
provenance hashes; new work should use the repository-relative paths above.

## Included research context

The `benchmark_01_legacy` through `benchmark_04_experiments` directories retain
source code, unit tests, generation design, compact inputs, aggregate metrics,
failure samples, and canonical reports useful to someone extending the current
search system. They are supporting research context, not additional production
runtimes.

## External or archival material

Ordinary Git intentionally excludes raw OCR images, fine-tuned model weights,
model and embedding caches, raw API-response streams, full historical result
matrices, and generated render/build intermediates. Those files are not needed
to run or modify Algorithm 6.

Full OCR retraining additionally requires separately acquired RxHandBD and
Data4/Data5 source images and the corresponding model assets. RxHandBD is
recorded as CC BY 4.0 at
<https://data.mendeley.com/datasets/dsb5r6vskg/2>. Data4/Data5 redistribution
rights were not established in this project, so their raw images are not
published here.

The alternative clean/v1 service is maintained separately at
<https://github.com/mohamedmaherabdalla/egyptian-medicine-search/tree/clean/v1-final>.
Do not merge its `src/medicine_search` runtime into this branch without an
explicit API and evaluation migration.

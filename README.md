# Egyptian Medicine Search

A medicine-search application backed by a 25,066-record Egyptian medicine
catalog, with the deployable Algorithm 6 runtime and focused acceptance tools.

The product rule is conservative: retrieve and rank candidates, expose the
evidence, and ask for clarification when the query does not support one safe
answer.

## Repository Map

| Path | Purpose |
| --- | --- |
| `app/` | Deployable browser application and runtime catalog. |
| `docs/` | Complete active Algorithm 6 rulebook and deployment notes. |
| `benchmark_01_legacy/` | Runtime Algorithm 5/6 source and required legacy helpers. |
| `benchmark_04_experiments/` | Focused OCR, visual-gap, API, and product-context acceptance tools. |
| `algorithm_6_rule_evaluation/` | Generators, evaluators, all durable rule-test CSVs, manifests, compact results, and LaTeX sources. |
| `output/pdf/` | Reviewed team handbook and exhaustive Algorithm 6 reference PDFs. |

This branch publishes the complete reviewable Algorithm 6 evidence package,
including the locked 66,257-case clean and 412-case fair-OCR inputs. Docker's
allowlist still keeps evaluation data and reports out of the deployment image.
Large raw API-response logs and render intermediates are intentionally not
versioned; the package retains the exact test rows, manifests, row-level
outcomes, summaries, and failure histories needed to inspect or reproduce
every reported result.

Start with the concise
[`Medicine Search Team Handbook`](output/pdf/medicine_search_team_handbook.pdf).
The longer
[`Algorithm 6 Rule Evaluation Reference`](output/pdf/algorithm_6_rule_evaluation.pdf)
contains the exhaustive rule registry and evidence tables. Their LaTeX sources,
build scripts, datasets, and result provenance live under
[`algorithm_6_rule_evaluation/`](algorithm_6_rule_evaluation/README.md).

## Run The Browser App

```bash
python3 -m http.server 8010 --directory app
```

Open `http://127.0.0.1:8010`.

This static mode reports `browser_consensus_search`; it does not execute the
Python Algorithm 6 pipeline.

## Run The Algorithm 6 App

Algorithm 6 requires about 2 GB RAM and takes about 13--30 seconds to build its
17,476-family indexes on startup. Run one API worker so the index is not copied
into multiple processes:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r app/requirements-api.txt

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m uvicorn \
  app.api:app --host 127.0.0.1 --port 8000 --workers 1
```

Open `http://127.0.0.1:8000`. The header must say `Algorithm 6`. Verify the
runtime independently at `http://127.0.0.1:8000/api/runtime`; a valid response
contains `"algorithm":"algorithm_6"` and
`"evaluation_version":"algorithm_6_consensus_v1"`.

Enter unreadable spans in the same field with `...`: `PANA...OL` uses both
visible edges, `...TRIL` uses a visible suffix, and `RIVO...` uses a visible
prefix. Mark both hidden edges with a marker on each side, such as `...VOT...`;
the returned `visual_gap.mode` reports `leading`, `trailing`, `both_ends`, or
`internal`. Space-separated visible parts such as `MELI CAM` are also accepted when
the text is not already an exact multi-word catalog name. These searches always
return confirmation-required candidates.

Strength, form, route, release, and pack-size evidence is handled by a separate
post-family reranker. For example, `JAKAVI 5 mg 56 tabs` first retrieves the
JAKAVI family by name, then selects the 5 mg, 56-tablet product. Mass units are
canonicalized, so `1 g`, `1 gm`, and `1000 mg` provide the same evidence. The
API preserves the family decision in `name_decision_type` and reports the
second stage as `product_context_selection`.

Unitless numbers are retained as uncertain catalog evidence instead of being
discarded. Thus `BRUFEN` plus `600 tab` can match the printed 600-strength
tablet, while `30 tabs` remains a pack-count hypothesis. Equal-evidence product
variants are shown as a tie. Explicit concentration denominators and complete
combination signatures must agree; if every retrieved product conflicts, the
site shows a name-only result with a product-details warning instead of
selecting the least-wrong package.

A one- or two-character medicine fragment is never treated as a confident
fuzzy result. When it is accompanied by both numeric and form/route/release
evidence, the API may apply a strict catalog-prefix filter. For example, `x`
plus `500 tab` returns the four matching X-prefix families as an ambiguous list
and asks the user to compare them. It does not search unrelated prefixes.

An exact normalized strength may also correct the family order when the current
top family has conflicting strength evidence. The cross-family adjustment keeps
a name-rank penalty and does not activate for form-only evidence, so `5 mg` can
promote a close JAKAVI spelling over `JAVA CREAM 50 GM`, while `tablets` alone
cannot override the family-name ranking.

The web form keeps this boundary visible: the medicine-name field is sent as
`query`, while the optional Product details field is sent as `product_context`.
Algorithm 6 receives only `query`; the product reranker receives the second
field. When `product_context` is omitted, combined legacy queries remain
supported.

The name layer also has bounded directional handwriting rules for `E/G`,
`I/E/Y`, `D/CL`, and `D/AL`. At most two documented grapheme confusions are
considered on sufficiently long visible names. Exact catalog spellings are
hard-protected, and every corrected or visual-gap result still requires user
confirmation. The same grapheme registry is used inside explicit leading,
trailing, internal, and both-edge visual gaps.

The complete active-rule inventory, including every score, threshold, gate,
alias, runtime boundary, and contributor safety checklist, is in
[`docs/ALGORITHM_6_COMPLETE_RULEBOOK.md`](docs/ALGORITHM_6_COMPLETE_RULEBOOK.md).

Run the catalog-derived visual-gap regression suite with:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  benchmark_04_experiments/test_algorithm_6_visual_gaps.py

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest \
  app.test_product_context_reranker app.test_product_context_hardening

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  benchmark_04_experiments/test_algorithm_6_ocr_confusions.py

.venv/bin/python benchmark_04_experiments/test_algorithm_6_api_hardening.py \
  --base-url http://127.0.0.1:8000
```

After starting the Algorithm 6 API, rerun the locked 200-case exact-context
comparison with:

```bash
python3 benchmark_04_experiments/evaluate_algorithm_6_product_context.py \
  --url http://127.0.0.1:8000/api/search
```

The evaluator exits nonzero unless context reaches every target at rank one
without regressing a baseline-correct case.

The production container uses the same entry point:

```bash
docker build -t egyptian-medicine-algorithm-6 .
docker run --rm -p 8000:7860 -e PORT=7860 egyptian-medicine-algorithm-6
```

Use a host with at least 2.5 GB available RAM. A 512 MB free web service cannot
start the unchanged Algorithm 6 indexes.

### Oracle Cloud Always Free

Use one Ampere A1 Flex Ubuntu VM with 2 OCPUs, 6 GB RAM, and a 50 GB boot
volume. Six gigabytes leaves enough headroom for the measured 1.9--2.1 GB
Algorithm 6 process while keeping its normal memory use above Oracle's 20\%
idle-memory threshold. In the VM's subnet or network security group, allow TCP
22 from your IP and TCP 80 from the internet.

After installing Docker and cloning the deployment branch, run:

```bash
chmod +x deploy/oracle-cloud.sh
./deploy/oracle-cloud.sh
```

The script builds the existing one-worker image, caps the container at 3 GB,
restarts it after VM reboots, and waits for `/health` before printing the
verified `/api/runtime` response. Open `http://<public-ip>` and confirm that the
header says `Algorithm 6 ready`. Add HTTPS through a domain and reverse proxy
before accepting sensitive or identifiable input.

## Locked Fair-OCR Comparison

Supply the reviewed 412-row CSV from the full research tree and compare an old
and candidate Algorithm 6 endpoint with exact visual-family identity:

```bash
.venv/bin/python benchmark_04_experiments/evaluate_algorithm_6_ocr_fair.py \
  --csv /path/to/data/01_ocr_fair/test_cases.csv \
  --old http://127.0.0.1:8013 \
  --new http://127.0.0.1:8014
```

The evaluator locks the accepted CSV SHA-256 and fails on any paired Hit@1,
Hit@5, or Hit@20 loss, or on lower aggregate Hit@5/MRR@20. Run the larger
clean-synthetic and full ablation packages from the full research branch,
which owns their datasets and runners.

## Safety Position

This is a retrieval prototype, not a clinical decision system:

```text
retrieve candidates -> show evidence -> show warnings -> user confirms
```

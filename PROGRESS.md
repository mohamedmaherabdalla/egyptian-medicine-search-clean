[2026-08-26] - Keep GitHub documentation source-native
What changed: Removed every tracked TeX and PDF file, retained the Markdown rulebook and continuation documentation, and added ignore rules preventing generated TeX/PDF artifacts from being committed again.
Why: The GitHub branch should carry executable source, tests, datasets, machine-readable evidence, and readable Markdown documentation without generated document binaries or LaTeX sources.
Status: complete after remote verification.
Next: Review `docs/CONTINUATION_GUIDE.md` and `docs/ALGORITHM_6_COMPLETE_RULEBOOK.md` directly on GitHub.

[2026-08-26] - Publish the continuation-ready research package
What changed: Added the important Benchmark 01--04 source, tests, compact inputs, metrics, and canonical reports; made locked test generation self-contained; added CI and a continuation guide; and verified that the complete Algorithm 6 UI/runtime was already present.
Why: Future contributors need executable source, safety gates, and enough research context to extend the system, but not raw third-party images, model caches, raw response streams, or full historical matrices in the working branch.
Status: complete; the focused Python/UI suites, 39-check API acceptance, 200-case product-context evaluation, locked-input hashes, and registry regeneration passed.
Next: Monitor the GitHub Algorithm 6 CI workflow and use `docs/CONTINUATION_GUIDE.md` as the handoff entry point for future changes.

[2026-08-25 20:05] - Prepare the complete Algorithm 6 evaluation branch
What changed: Curated the latest runtime changes, focused tests, durable rule-test datasets, manifests, compact run evidence, and documentation for publication; documented why oversized raw API logs and render intermediates remain local.
Why: The earlier uploaded branch came from a different repository and omitted the actual Algorithm 6 source, test sets, rule documentation, and evaluation evidence.
Status: done
Next: Review the verified GitHub branch, Markdown documentation, test sets, and compact evidence; open a pull request when team review is complete.

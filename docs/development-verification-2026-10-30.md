# Development workflow verification — October 30, 2026

Candidate base: `fbc73e96105c294dfa7001cd379b4b8f30945679` plus the explicit source
snapshot submitted to task `81672c172a042bc98e5df8182f382b26`. Existing handoff work was
preserved and is included for reproducibility. The coordination candidate, not this
base commit alone, identifies the implementation.

Local environment: Python 3.13.1, macOS, checkout `.venv`. Evidence is retained under
`state/verification/audit-2026-10-30/` and `state/verification/development/`.

- `scripts/dev.py release`: passed; 287 full-suite tests, 24 pure-kernel tests,
  domain/application branch coverage 88% against an 85% floor, Ruff lint/format,
  mypy for three contract files, version/dependency consistency and shell syntax.
- Fresh/update installer coverage includes disposable homes and injected dependency,
  activation and migration failures, plus rejection of bundled edits made during
  preparation. No active installation was updated.
- Wheel/import/migration-resource verification and source archive validation passed.
  Archives include the checkout launcher, changelog and installer dependency files,
  and exclude runtime and temporary test fixtures. SHA256SUMS accompanies
  the wheel/source artifacts. These remain local unreleased builds of the current
  package version; tagging refuses unresolved Unreleased changes. The extracted
  source archive also passed all 287 tests and the fast/coverage gates.
- Pip hash-validation dry runs passed for runtime and combined development/memory
  locks. This is macOS/Python 3.13 evidence, not remote cross-platform certification.
- Dependency audit of resolved development/memory packages (including runtime pins)
  reported no known vulnerabilities. This reflects that advisory query, not a security
  guarantee. A Starlette/httpx test-client deprecation remains visible in test logs;
  runtime pins were not silently upgraded to hide it.
- Isolated keyword-memory benchmark: 1,000 units, 30 queries, p50 13.47 ms,
  p95 14.16 ms, zero pending index units. Pending embeddings were 1,000 because the
  benchmark intentionally has no embedding provider. These are small local measurements,
  not semantic-search or concurrent-writer capacity guarantees.
- `git diff --check` passed. Historical migrations and legacy directories were preserved.

The implementation milestone was saved as private typed memory. Scoped search on the
existing live client currently requests a restart after an embedding-configuration
change; successful canonical writes do not certify that client's semantic retrieval.
Restart the agent/MCP client before checking the updated semantic configuration.
No live memory binding was stripped to perform operator maintenance.

Preliminary authenticated reviewer/QA reports identified bytecode contamination,
a missing checkout launcher and incomplete per-entry hash validation. Those findings
were addressed with focused regressions; bundled-source edit detection was also
added. Source snapshots now exclude interpreter caches while retaining path/symlink
checks. Follow-up evidence is in `review-final-validation.log`,
`review-final-package.log` and `archive-final-check.log` under the audit evidence directory.
Independent final reviewer/QA results belong to the same-candidate coordination records.
Remote CI, GitHub environment protection settings, draft-release execution, authenticated
provider smoke checks and real semantic inference were not executed by this local run.
The optional-integration workflow and development guide provide explicit procedures.
No Git tag, commit, publication, global agent configuration change or live installation
update was performed.

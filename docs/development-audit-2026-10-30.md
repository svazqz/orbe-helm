# Development and release audit — October 30, 2026

## Scope and conclusion

Reviewed checkout `fbc73e96105c294dfa7001cd379b4b8f30945679` plus existing uncommitted handoff changes. This is a source/workflow audit and local automated validation, not a comprehensive security assessment or live provider certification. Existing changes to conversation-memory.md, adapters.py, test_cli_memory.py, handoff_runtime.py and test_handoff_runtime.py were preserved.

The stack is appropriate for a local orchestration tool. Keep Python, SQLite, SQLAlchemy/Alembic, the optional FastAPI/Jinja editor and unittest. The highest-return improvement is a repeatable contributor/release workflow, rather than replacing frameworks or finishing a large refactor before shipping features.

## Findings and priorities

### High: installation updates replace application code before dependency verification

`src/orbehelm/installer.py` calls `copy_application` before running pip and validating installed imports. The installation manifest uses an incomplete marker, which helps block unsafe launches, but failed dependency installation can leave the application replaced and unavailable. Database backups do not themselves restore application code or its environment.

Recommendation: stage source and a fresh environment in a versioned installation directory; validate imports and CLI smoke checks before switching the launcher. Keep the previous application/environment and document database-backup restoration separately. Treat this as a separately approved installation design change. Add failure-injection coverage for package-install and activation failures. This audit did not perform an installation update or establish a live failure on the current installation.

### High: release preparation is manual and release documentation can mislead

The only checked-in GitHub Actions workflow is verification on push/pull request. It builds and checks wheels but does not define a tagged release pipeline or retain wheel artifacts with an upload step. Versions exist in both pyproject.toml and `src/orbehelm/__init__.py`. README still advertises alpha 1 while package metadata and docs/releases.md identify alpha 2. The release guide's publication example still uses the permanently reserved first-release tag.

Recommendation: one release checklist/command verifies version agreement, clean candidate scope, changelog entry, schema compatibility and exact SHA. A tag pipeline should test that revision, build once, retain artifacts/checksums and prepare a draft GitHub release. Publication should remain an explicit operator step. Test installation and upgrade from that exact artifact/tag in disposable homes. Do not add PyPI publication unless it is an intended distribution channel.

### Medium: dependency pins are useful but not fully reproducible

requirements.lock records exact runtime/test versions; requirements-memory.lock adds FastEmbed but explicitly leaves extra transitive dependencies platform-resolved. Files contain no artifact hashes. pyproject dependency ranges and installer pins have different roles, so both need validation. CI covers Linux/macOS and Python 3.11/3.13; package metadata has no upper Python bound, which is broader than that tested matrix.

Recommendation: document supported/tested interpreters, generate dependency resolutions with an explicit update procedure, include optional memory dependencies in reproducibility checks, and consider platform-specific hash-checked requirements. Add a scheduled dependency/security review with human review of changes. No vulnerability scan or current CVE clearance was performed.

Reference: [pip repeatable installations](https://github.com/pypa/pip/blob/main/docs/html/topics/repeatable-installs.md).

### Medium: contributor checks need a single entry point

The repository configures unittest and architecture checks but no formatter, linter, static type-checker or coverage gate in pyproject/CI. The default system Python could not run the full suite because product dependencies were absent; the existing project venv is usable. This is an environment/bootstrap issue, not evidence of a product defect.

Recommendation: add documented bootstrap, fast-check, full-check and release-check commands using the project environment. Start lint/format checks incrementally on changed code; introduce typing at application/plugin boundaries and ratchet coverage around risk-bearing paths. Avoid a repository-wide formatting/refactor patch mixed into a feature. Ruff can supply linting and formatting, but adopting it is a separate dependency-policy decision.

Reference: [Ruff configuration](https://docs.astral.sh/ruff/configuration/).

The full suite has an additional reproducibility issue: three operator-memory CLI tests fail under an agent launch. They invoke fixture CLI operations without isolating the inherited launch binding; `memory.dispatch` detects that binding and `bound_service` rejects its use against the disposable fixture store. The log records `Access denied`. Recommendation: construct isolated synthetic operator and agent test environments without altering production authorization or stripping the live binding to access operational data. Keep regression coverage proving operator commands remain forbidden in actual agent contexts.

### Medium: architecture extraction is incomplete, but guarded

The domain/application/infrastructure/provider split is useful. Pure-kernel tests run without site packages, architecture tests prevent new dependency violations, historical migrations have checksum protection, and provider commands have contract tests. However, `infrastructure/compatibility/dispatcher.py` still routes important operations into effectful product modules. Launch/chat/coordination also retain substantial orchestration responsibilities.

Recommendation: implement each feature through the existing public operation and provider contracts. Extract one coherent use case when changing it, preserving external behavior. Track explicit retirement criteria for compatibility routes. Avoid introducing a second workflow alongside the existing dispatcher or interpreting package separation as a completed architecture migration.

### Medium: documentation mixes superseded contracts with current ones

The memory guide's introduction says native tools are supported, then later says native run does not receive the new memory binding. Historical sections describe automatic reply capture, superseded by typed outcome writes in schema 0006. independent-core-progress.md likewise contains historical statements qualified by a newer header.

Recommendation: make one current guide authoritative for launch, memory and development. Move historical contracts into dated records and link to them rather than requiring readers to reconcile contradictions. Include documented-command smoke checks and a version-consistency assertion in CI.

### Medium: synthetic provider coverage needs a separate live compatibility lane

Fake native processes and in-process ASGI clients provide valuable deterministic coverage, but cannot prove live provider flags, authentication, trust, native tool approvals or terminal behavior. Existing documentation generally distinguishes these limits well. Persistent OpenCode resume is explicitly unavailable rather than silently emulated.

Recommendation: record supported CLI versions and run opt-in authenticated smoke checks before releases that change providers. Exercise fresh/resume, policy refresh, cancellation and scoped memory tools. Keep credentials out of normal CI; record exact tool/application versions and results. This audit started no authenticated model or browser session.

### Lower priority: plan capacity and recovery before broad deployment

SQLite, short-lived transactions, explicit migrations, backup creation, foreign-key checks and workspace writer locks fit a local tool. Exact vector search and serialized writes should be benchmarked with representative corpus sizes and concurrent work before expanding usage. Do not add a server database, distributed queue or remote vector service without measured need. Unix fcntl locks and the installer’s explicit platform gate mean Windows is not currently supported.

## Suggested feature and bug workflow

1. Create a focused issue with observable acceptance criteria and compatibility/migration implications. Reproduce bugs before changing code.
2. Use a branch and a task key such as APP-42. Inspect definitions and the affected public operation; keep unrelated working-tree changes outside the candidate.
3. Add focused behavioral coverage, implement the smallest change and run fast checks. Run the full suite before submitting the candidate.
4. Submit an explicit source scope and revision through existing OrbeHelm coordination. Have independent reviewer/QA gates assess the same revision. A changed candidate needs new assessment.
5. Merge only after those gates and CI pass. Record a typed outcome with evidence and update current documentation/changelog when behavior changes.
6. Prepare a release from an exact reviewed commit; verify wheel, installation, upgrade and relevant provider/memory integrations. Draft the release, then publish deliberately.

Suggested order: fix current documentation and establish contributor commands first; add release/version/artifact checks next; then improve installer recovery and optional-memory/provider integration coverage. Continue architecture extraction alongside actual feature work.

## Memory: observed state and setup

The live scoped `search_memory` MCP call succeeded in this session. Its response reported `mode: keyword-only`, `vector_backend: null`, `pending_embeddings: 0`, `pending_index_units: 0`, and `policy_epoch: 1`. The particular audit query returned no units. This proves scoped search connectivity and the reported retrieval mode; it does not prove absence of stored knowledge, semantic inference, cross-context visibility or write/read persistence.

`oh memory status` was denied with “Operator memory maintenance is not available through an agent binding.” This is an intentional restriction in memory.py, not a failed memory service. I did not remove the binding or bypass the restriction. Run operator commands in a normal terminal outside the launched agent.

Keyword retrieval needs no embedding model. To enable semantic retrieval, finish active OrbeHelm sessions before updating the installation, then run from the intended reviewed checkout:

```sh
./update.sh --memory
# Supply the original --install-dir if customized.
oh memory configure --download-model
oh memory status
```

Use `./setup.sh --memory` for a fresh installation. Updates use the checkout's current source, including local changes; select a reviewed tag/commit first when installing a release. Updating the installed application and downloading weights were not performed during this audit.

FastEmbed runs locally; configure explicitly downloads public model artifacts. No embedding API key or separate vector service is required. Configuration checks document/query inference before activation and processes indexing. A native vector backend or the declared local exact-cosine fallback may be used. Confirm the resulting status and execute a representative query rather than treating a successful package install as proof of working semantic retrieval.

For development knowledge shared within this project, launch with:

```sh
oh --profile=developer --spec=python \
  --project=/Users/sergiovazquez/Projects/orbe-helm \
  --unique-key=APP-42 --memory-visibility=project
```

Use private visibility for context-specific material. Project visibility enables eligible project contexts subject to audience and provenance rules; it does not automatically reclassify old private units. Record decisions/features/tests as typed, focused outcomes with stable source IDs and artifact/revision evidence. Conversation history alone is not accepted technical knowledge. After semantic setup, use `oh memory query --project=... --thread=CONVERSATION_ID --query='...'` to check representative retrieval. `oh memory reindex` and `--rebuild-index` are operator recovery tools, not required routine steps after every write.

Current contract: [persistent workflows](persistent-workflows.md). Historical/setup detail: [knowledge memory](knowledge-memory.md), with the documentation inconsistencies noted above.

## Validation evidence

Local Python: project venv, Python 3.13.1/macOS. Evidence directory: `state/verification/audit-2026-10-30/`.

- Pure kernel: 24 tests passed (`kernel.log`).
- Project environment: `pip check` passed.
- Shell syntax: `sh -n setup.sh update.sh` passed.
- Full suite: 276 tests ran in 57.373 seconds; 273 passed and three operator-memory CLI tests failed with `Access denied` (`tests.log`). Affected tests: legacy import, operator put/query/visibility/history, and visibility/audit with broken embeddings. Source inspection identifies inherited live binding versus fixture-store isolation as the failure path. The suite is not green in this execution environment.
- Initial system-Python suite: failed with missing dependencies, including SQLAlchemy/Alembic/FastAPI; superseded by the project-venv run.
- Scoped memory search succeeded in keyword-only mode; operator status was access-denied as designed.

No application source, dependency, installed configuration or operational database was intentionally changed. Test fixtures and evidence were generated inside the checkout. Remote CI, live provider sessions, semantic-model inference and a fresh wheel build were not executed in this audit.

# Historical record — superseded

This dated implementation record is not the current feature contract. See
[architecture](../architecture.md), [memory](../knowledge-memory.md) and
[persistent workflows](../persistent-workflows.md).

# Independent core refactor progress

October 30 update: [owned KUnit memory](../knowledge-memory.md) is now implemented with
schema 0005, per-orbe private/global visibility, recoverable hybrid indexing, local
embeddings, scoped tools, and managed-chat context/capture integration. The historical
October 29 assessment below describes the first increment; its statements that KUnit
persistence/access are not exposed have been superseded by the memory feature.
The full nine-phase refactor and general host-isolation/operator-grant work remain open.

This is the first structural increment of the [approved plan](../../plan/refactor-independent-core-adapters-1.md),
implemented on October 29, 2026. The full nine-phase plan remains in progress.
The [assessment](../independent-core-assessment.md) describes the preserved pre-refactor
baseline, including the earlier uncommitted implementation.

## Implemented boundaries

| Package | Implemented responsibility | Existing runtime integration |
| --- | --- | --- |
| `domain/shared` | Canonical serialization/hashing, identifiers, distinct identity types, errors, immutable events | `core` and catalog error exports retain their historical identity |
| `domain/definitions` | Section composition, source grammar, MCP schema checks, dependency traversal/order | Existing resolver/composition calls use these policies |
| `domain/coordination` | Developer ownership, CAS, submission eligibility, review/QA ordering, completion/reopen decisions | Existing SQL-backed Coordinator delegates these decisions |
| `domain/conversations` | Semantic policy freshness, immutable conversation values, bounded historical handoff | Managed/native refresh and conversation bootstrap use these policies |
| `domain/projects`, `domain/orbes` | Immutable entity values separating project/logical work/native session concepts | Values and mapping boundaries exist; historical identity consolidation is not implemented yet |
| `domain/access`, `domain/knowledge` | Private ownership predicates, grant lifetime/revocation checks, lifecycle/visibility, reviewed-copy publication, redacted public projection | Tested as pure policies; not exposed as a new production authorization or collective-memory system |
| `application` | Versioned Request/Result, strict operation registry, injected caller verification, pure composition and repository-backed knowledge handlers | New kernel workflows run against memory ports; existing public `execute/storage` exports remain compatibility composition entries |
| `infrastructure/persistence` | Existing SQLAlchemy rows and explicit domain projections | `product.models` forwards old names; schema and migration bytes are unchanged |
| `infrastructure/process` | Owned process-group execution/cancellation | Existing delegation runner calls the extracted implementation through its old export |
| `plugins/codex`, `plugins/claude` | Config rendering, native/structured/child command plans, normalized public events, login plans, resume translation, capability declarations | Existing build, managed chat, native launch, and MCP sign-in paths delegate the extracted translations |
| `integrations/herdr` | Optional terminal display metadata | Old `herdr` exports remain compatible; lifecycle event subscription is still planned |

Plugins do not own database transactions, credentials, process creation, or business
decisions. Plugin capabilities distinguish synthetic contract evidence from live CLI
evidence and explicitly reject exclusive-context/interactive-permission guarantees.
Authentication homes, existing history, source definitions, `oh`, and legacy readers
retain their current behavior. OpenCode remains on the legacy path.

Build implementation hashes now include extracted domain/plugin sources and their
contract/registry. This preserves cache invalidation after the file moves. Portable
policy freshness remains independent of implementation hashes and physical paths.

## Compatibility and remaining work

`infrastructure/compatibility/dispatcher.py` contains the old effectful dispatcher.
It deliberately keeps existing project/catalog/coordination/conversation workflows
working while typed repository/use-case extraction continues. It is not a completed
independent kernel for every existing operation. The architecture allowlist records
these exact legacy imports and existing cycles; new handlers cannot depend on them.
The tiny public application compatibility export is an explicit composition boundary.

No identity/knowledge/tool-invocation migration has been added, and no operational
database was upgraded as part of this increment. Existing private Knowledge rows have
not been published or reclassified. Remaining plan work includes complete source
resolution plans, repository/UoW extraction, verified production bindings/grant
issuance, atomic persistent KUnit revisions and context bundles, additive identity
migrations, provider probes/native capture/environment extraction, deterministic tool
invocation recovery, thin CLI/MCP/editor transports, coverage ratchets, and final
retirement of compatibility edges. The new knowledge handlers are not exposed by
the legacy CLI/MCP dispatcher until those persistence/access requirements are met.

The provider-format extraction was performed alongside the foundational work to
verify real runtime delegation and package independence. It does not mark the later
provider phase complete: native discovery, authentication status, environment setup,
and capture orchestration still need extraction behind the complete effect ports.

## Regression gates

- All original 159 regression test IDs remain inventoried in `tests/feature_contracts.json`.
- Baseline file hashes and frozen migration checksums are in `tests/fixtures/compatibility/`.
  The local pre-refactor source archive is retained under `state/verification/independent-core-refactor/`.
- `python3 -m unittest discover -s tests -v` discovers old regressions and new domain,
  application, plugin, integrity, and architecture suites.
- `python3 -I -S tests/run_kernel.py` runs pure domain/application workflows without
  site packages. File, environment, process, and network effects are blocked during execution.
- `python3 tests/check_wheel.py FILE.whl` verifies installed kernel/plugin/CLI imports
  without site packages, optional UI dependency metadata, file/package consistency,
  and unchanged packaged migration resources.
- GitHub Actions defines Python 3.11/3.13 kernel checks and Linux/macOS full-suite and
  wheel checks. Remote CI execution is separate from local verification.

Base package dependencies now contain persistence only. Install `orbehelm[web]` for
the optional editor or `orbehelm[dev]` for the existing complete test environment.
`requirements.lock` and setup/update retain the full existing installation behavior;
`requirements-core.lock` supplies the corresponding reviewed persistence pins.
Platform-specific transitive dependencies still need the cross-platform CI checks.

No authenticated model session or live Herdr rendering is established by these tests.
Same-user filesystem access remains outside application-level authorization checks.

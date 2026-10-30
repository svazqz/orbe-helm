# OrbeHelm architecture

Schema `0006` adds stable project/profile/key workstreams, isolated specialization
contexts, typed audience-scoped knowledge and independent parallel review/QA gates.
See [persistent workflows](persistent-workflows.md) for current execution defaults,
authorization and migration. It supersedes older raw-observation/sequential-gate
descriptions below.

Managed chat now includes an [owned KUnit memory engine](knowledge-memory.md).
Domain/application memory rules are separate from SQLite canonical persistence,
rebuildable FTS/vector projections, and explicitly configured local inference.
Its schema is `0006`; the wider independent-core extraction remains in progress.

OrbeHelm has a portable source resolver and a local application service. The optional
HTTP editor is a client of that service; normal launches and task delegation require
no HTTP listener. The `application` package provides typed Request/Result contracts,
an operation registry, and injected authorization/repository ports. Its compatibility
`execute` export routes existing operations through `bootstrap.py` and the transitional
`infrastructure/compatibility/dispatcher.py`. Full repository/use-case extraction is
in progress; see [implemented boundaries and remaining work](independent-core-progress.md).

## Sources and composition

`core.py` orchestrates source reads and builds; pure composition, schema checks, and
dependency traversal live in `domain/definitions`. Structured instructions follow the
seven-section template. Codex/Claude rendering and native command/event translation
live in provider plugins; `adapters.py` retains compatibility orchestration and the
legacy OpenCode renderer. Generated builds hash extracted implementation sources.
Definitions are authoritative; generated files are immutable build artifacts.

`product/catalog.py` validates source bytes and publishes immutable snapshots and
release membership. Shared publication automatically appends source-only project
configuration revisions, preserving context, aliases, file replacements, and legacy
section overrides. It does not contact remote dependencies or rebuild every project.
Effective combinations are resolved and built when used. Shared history rollback
publishes restored bytes as a new release, retaining the audit chain.

`product/definition_operations.py` maps typed definition names to owned source files.
Project-local replacements/tombstones are immutable data on project configuration
revisions; `catalog_snapshot` materializes the shared source plus that overlay.
Reset removes the local replacement so the current shared file applies. Unknown
fields, invalid instructions, missing dependencies, traversal, symlinks, and stale
expected revisions fail before activation. New generic overlays replace files;
legacy section-level overrides remain readable.

## Storage and concurrency

SQLite and reviewed Alembic migrations hold project/configuration identity, source
history, build indexes, launch records, coordination state, and conversation events.
SQLAlchemy rows live in `infrastructure/persistence/models.py`; `product.models`
forwards existing names. Immutable domain entities are separate from these rows.
`Store` checks the current schema. Setup/update/migrate upgrades explicitly; launches
do not generate or apply schema migrations. Database upgrades back up existing data.

Verified filesystem snapshots hold source bytes and skill resources. They are written
before database references. Multi-file shared mutations use a publication journal that
recovers expected writes while rejecting conflicting external source edits. Filesystem
product locks serialize publication/configuration mutations; no SQL transaction spans
a network download or model conversation. Native slots and managed conversations have
separate lifetime locks. Keyed developer turns retain workspace writer exclusivity.

Installed applications retain the configured runtime base outside application code;
checkout use retains state in the checkout. Legacy names and paths remain readable.
No development command modifies global agent configuration or imports credentials.

## Conversations and native adapters

`conversations.py` stores an append-only, provider-independent event ledger keyed by
project/profile/specialization/task selection, excluding agent choice. Explicit working
checkpoints have their own audit events. `managed.py` owns terminal input and structured
Claude/Codex execution, captures events incrementally, and links agent-specific native
attempts to that ledger. Runtime commands request full access as defined in persistent-workflows.md; OS and
provider trust requirements still apply. Interactive approval callbacks are not
implemented in the structured runner. Process-scoped Claude tool rules remain
audited and included in the managed policy digest.

`sessions.py` computes a semantic policy digest, independent of timestamps, physical
paths, unrelated definitions, and labels. Exact-ID resume is permitted only for an
unchanged active policy/agent. Changed rules or agent choice start a fresh native
conversation and inject a bounded historical handoff when memory is enabled.
With memory disabled, native continuity instead retains the recorded session and
requires an explicit reread of the stable current-instructions file. Native transcripts and ledger
history are retained; this does not preserve an identical model context window.

`native_capture.py` offers best-effort transcript capture for native interactive
launches. Coverage/failures are recorded separately from structured mode. No terminal
screen scraping, global home scan, transcript rewrite, or hidden reasoning transfer is
performed. Read [conversation behavior](conversation-memory.md) for limits and commands.

Task coordination remains the SQLite/stdio MCP architecture. Candidates and delegated
review/QA inputs retain their submitted configuration even after a new shared release.
Accepted project knowledge and task memory are distinct from conversational history.

## Optional editor and Herdr

`product/web.py` exposes shared definitions, registry forms, history, and rollback.
Project, task, authentication-job, and orbe management belong to the CLI. Loopback
Host/Origin validation, bounded forms, CSRF, and HTML escaping remain enforced.
`/healthz` and `server status` describe the editor; their availability does not gate work.

`herdr.py` prefers the pane owner's `HERDR_BIN_PATH`, retains socket routing, and sets
source-scoped display-agent/title metadata. Metadata is cleared when native work exits.
It never claims native working/idle status. Read-only integration diagnostics report
binary discovery and supported metadata flags. Live rendering is a separate check.

## Verification boundary

The automated suite uses disposable databases/homes and fake native processes. It
checks migration/model parity, shared inheritance, override/reset, failed mutation
recovery, conversation capture/handoff, exact resume and policy refresh, read-only
operations, workspace locks, UI security, and integration fallback. It does not prove
authenticated model behavior or exclusive context isolation for any native adapter.

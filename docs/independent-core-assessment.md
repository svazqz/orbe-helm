# Independent-core assessment

Assessment date: 2026-10-29. Scope: the current working tree, including the prior
uncommitted CLI/conversation changes, rather than only the last Git commit. This is
an implementation assessment for the [refactor plan](../plan/refactor-independent-core-adapters-1.md).
No runtime implementation was changed during this assessment.

## Verified baseline

`PATH="$PWD/.venv/bin:$PATH" python3 -m unittest discover -s tests -v` passed
**159 tests** on the existing project environment. Alembic reported no model/schema
drift. Evidence is `state/verification/independent-core-plan/baseline-tests.log`.
The suite uses disposable application homes/databases and fake native children.
This is not authenticated Codex/Claude or live Herdr verification.

There are twelve top-level test modules. The largest groups are product integration
(34 methods), resolver/native behavior (32), conversation/CLI memory (18), and task
coordination (17). These are useful behavior checks, but many instantiate SQLite or
patch concrete module functions. Passing them does not establish an independent domain.
There is no `.github/` workflow directory in the inspected working tree. The project
configuration defines unittest-oriented development dependencies but no architecture
fitness checks or coverage thresholds.

## Reuse and separation map

| Current implementation | Reusable behavior | Required separation |
| --- | --- | --- |
| `composition.py:parse_sections/compose` | Seven-section grammar, append/override semantics, canonical ordering | Move pure composition to the definitions domain; remove imports of `core.py` and filesystem compatibility helpers |
| `core.py` (327 lines) | Identifiers, schema validation, dependency graph ordering, source hashes, build behavior | Separate pure validation/resolution from filesystem reads, downloads, installation, locking, and native rendering; `build()` currently imports `.adapters.render` |
| `snapshots.py`, `remote_skills.py` | Content/executable-bit integrity, bounded archives, path/symlink protections | Keep as filesystem/network infrastructure behind source/blob ports; preserve hashes and limits |
| `product/catalog.py` (299 lines) | Validated publication, immutable history, multi-file recovery, restore-as-new-release | Extract publication rules into application use cases and domain policy; keep SQL/journal mechanics in repositories/stores |
| `product/projects.py` (493 lines) | Context snapshots, local overrides, shared propagation, selection locks, atomic dependency edits | Separate project entity/policies, effective-context resolution, repositories, file journals, and build materialization |
| `product/coordination.py` (469 lines) | Ownership checks, review-before-QA, immutable candidate binding, version checks, retry/recovery rules | Extract a pure task state machine and scoped knowledge policy from ORM transactions and filesystem artifact writes |
| `conversations.py` (132 lines) | Append-only events, source deduplication, checkpoint audit, scoped pagination/search, bounded handoff | Separate history entities and context policy from SQL, stdin, project lookup, and storage limits |
| `sessions.py` | Semantic policy digest and refresh reasons | Convert dictionary inputs/results to typed portable values; separate portable context identity from adapter compatibility |
| `adapters.py` (517 lines) | Provider renderers/commands, exact-ID discovery, launch locks, runtime metadata | Split core launch orchestration from Codex/Claude implementation, process execution, native storage, authentication, and Herdr integration |
| `managed.py` (321 lines) | Owned event capture, adapter switching, grant audit, interruption handling | Move terminal interaction to CLI; move orchestration to application; move stream parsing/commands into provider plugins |
| `native_capture.py` | Partial-line handling, capture coverage, source-offset/content deduplication, stale-rule filtering | Share file-tailing infrastructure; put native transcript schemas/locators in individual plugins |
| `application.py` (126 lines) | Existing operation names and a shared dispatch entry | Replace string/kwargs dispatch and concrete storage construction with typed handlers, injected ports, and a composition root |
| `product/models.py` (250 lines) | Current relational schema and migration history | These classes are ORM rows, not independent domain entities. Retain the schema while introducing explicit domain objects and mappers |
| `cli.py`, `mcp_bridge.py`, `product/web.py` | Existing commands, stdio protocol checks, optional shared editor, form security | Make all transports clients of the same application API; remove direct ORM/coordinator access and duplicate authorization paths |
| `herdr.py` | Owner-binary discovery and source-scoped label/title reporting | Keep as an external integration subscriber, outside domain/session policies |
| `installer.py`, `layout.py`, `compatibility.py` | Private installation, update behavior, runtime layout, legacy readers | Move operational mechanics to infrastructure while retaining executable names, paths, source formats, and legacy compatibility |

## Gaps relative to the drawing

1. **No separate domain model.** State transitions and business decisions often occur
   inside SQL transactions. Databases and process mocks are needed for tests that
   should be pure business-policy tests.
2. **Orbe identity is inconsistent across modes.** `orbe_identity()` includes the
   agent; `LogicalOrbe` is task/role based; `Conversation.selection` excludes the agent;
   managed mode derives provider-specific native orbe IDs. These must become explicit
   logical identities and native bindings without discarding existing IDs/history.
3. **Knowledge is not yet a general KUnit model.** `Knowledge` is tied to project,
   task, author, and artifact, with task/project scope. There is no collective corpus,
   general ownership/visibility policy, cross-project operator grant, or uniform KUnit
   query API. A transcript/checkpoint is not an accepted knowledge unit.
4. **Scope checks are contextual, not a unified authorization boundary.** Coordination
   checks bound task/orbe relationships; conversation reads compare a supplied project.
   The CLI/MCP/application layer has no general verified-principal contract. A project
   argument or an `operator` boolean cannot prove authorization. Same-user filesystem
   access also remains outside application-level scope checks.
5. **Agent behavior is embedded in shared modules.** Rendering, authentication,
   transcript discovery, headless flags, streams, and cancellation are distributed
   across several files. Shared code branches on provider names and sometimes imports
   provider code in both directions.
6. **No capability contract or deterministic tool catalog.** There is no formal
   full/partial/unsupported matrix, common adapter conformance suite, or execution
   record for an agent-independent deterministic utility. MCP currently exposes a
   coordination subset and is not the universal application/toolset interface.
7. **Permissions and recovery need explicit boundaries.** Existing retry/version,
   cancellation, source-integrity, and no-duplicate-delegation safeguards are valuable.
   They should become reusable policies and invocation contracts, not be lost in a
   directory-only reorganization.
8. **Packaging couples core work to UI dependencies.** FastAPI, Jinja2, and Uvicorn are
   unconditional dependencies. An independent kernel should import and run its fake-
   adapter use cases without them, SQLAlchemy, installed agent CLIs, or authentication.

## Preservation requirements

Preserve executable `oh`, project name `orbehelm`, source definitions/registries,
composition semantics, source hashes, project overrides, shared update behavior,
SQLite history, snapshot manifests, legacy runtime files, task/workspace bindings,
candidate provenance, provider authentication homes, and current command compatibility.
Move existing rules with characterization tests before introducing new KUnit behavior.
Do not infer that two historical native orbes are the same logical work merely because
they share a project and profile.

The recommended migration is an incremental replacement of components behind existing
entry points. A full rewrite would discard useful validation and persistence work and
make regressions harder to attribute.

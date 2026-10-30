---
goal: Refactor OrbeHelm into an independent domain/application kernel with scoped knowledge, deterministic tools, and Codex/Claude plugins
version: 1
date_created: 2026-10-29
last_updated: 2026-10-30
owner: OrbeHelm
status: 'In progress'
tags: [refactor, architecture, domain, business-rules, entities, persistence, plugins, codex, claude, testing]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

This plan implements the architecture requested in the user's drawing: OrbeHelm owns
definitions, project state, logical orbes, knowledge, history, and deterministic tools.
CLI and scoped MCP clients invoke the same application operations. Codex and Claude
are initial plugin implementations; Herdr is an external integration. Naming changes
are excluded. Implementation has started; the full plan is not complete. See the
[progress record](../docs/independent-core-progress.md) for implemented boundaries,
transitional compatibility, verification, and outstanding work. Provider-format
extraction accompanies foundational work; it does not complete the later provider phase.

Memory amendment: the approved [owned knowledge feature](feature-owned-knowledge-memory-1.md)
supersedes this plan's original project-private/released-copy policy in section 1.5.
Private KUnits are owner-only; global visibility preserves identity/ownership; active
reported units are retrievable with their unverified status. Migration 0005 implements
the current memory engine. Legacy task knowledge is imported only explicitly. Future
identity/access/tool migrations below start at 0006 and do not replace deployed 0005.

The [current implementation assessment](../docs/independent-core-assessment.md) records
the inspected working-tree baseline, concrete reuse candidates, and gaps. The current
full suite passes 159 tests; evidence is
`state/verification/independent-core-plan/baseline-tests.log`. The prior uncommitted
CLI/memory work is part of this baseline and must be preserved during implementation.

Use an incremental replacement behind existing entry points. First separate existing
behavior and establish enforcement tests; then add canonical logical identity, KUnit
authorization, and common tool/adapter contracts. Existing source definitions remain
authoritative. Database schemas and native protocols are infrastructure concerns.

## 1. Requirements & Constraints

- **REQ-001**: Domain entities, value objects, business policies, and state transitions must execute with the Python standard library and supplied values only. They must not import SQLAlchemy, FastAPI, CLI parsers, native plugins, network/process APIs, or concrete stores; they must not read files, environment, credentials, or global clocks.
- **REQ-002**: Application use cases coordinate domain decisions through injected repository, unit-of-work, source/blob, authorization, agent, process, clock, ID, and event ports. One `Application.handle()` entry point dispatches typed commands/queries through an explicit operation registry.
- **REQ-003**: Separate domain entities from ORM persistence rows and transport DTOs. Domain references use typed IDs/revisions; SQLAlchemy relationships, sessions, migrations, and serializers remain outside the domain.
- **REQ-004**: CLI, scoped stdio MCP, and the optional shared-definition editor call the same application operations. CLI exposes all supported application features. No HTTP listener is required for normal core/agent work.
- **REQ-005**: A logical Orbe is independent of provider and native session identity. Project ownership, optional task/parent relationships, definition selection, conversation lineage, and work identity remain explicit. Changing agent does not create a different logical work item or move its private memory.
- **REQ-006**: Definitions retain their current schemas, paths, composition order, additive dependencies, file override/reset, shared propagation, immutable publication, and restore-as-new-release behavior. A Profile is a definition kind, not a separate top-level ownership hierarchy.
- **REQ-007**: Introduce versioned KUnits with ownership, visibility, lifecycle, provenance, evidence references, and expected-revision writes. Keep conversation events, checkpoints, reported observations, accepted knowledge, and definition instructions distinct.
- **REQ-008**: Agents can query collective accepted knowledge and private knowledge permitted by their verified project/orbe/task binding. Operator cross-project private reads and collective publication require explicit scoped authorization. Apply access predicates before search, retrieval, context assembly, caching, or artifact resolution.
- **REQ-009**: Provider plugins implement common capability contracts. Shared application/domain code must not branch on `codex` or `claude`, contain native flags, or parse native session files. Optional unsupported/partial capabilities are declared and surfaced; they are not silently simulated.
- **REQ-010**: Provide an OrbeHelm-owned deterministic tool catalog and invocation lifecycle. CLI/MCP expose the same logical tools; provider-specific multi-step mechanisms remain behind adapters and do not duplicate business rules.
- **REQ-011**: Preserve append-only captured history and semantic context refresh. Switching providers uses one authorized canonical context bundle and existing history, not a raw vendor transcript rewrite or a claim of identical model state. Authentication homes remain stable; native conversation generations can change.
- **REQ-012**: Keep task review-before-QA, owner checks, immutable submitted candidates, pinned child configuration, version conflicts, workspace locks, cancellation, and unknown-outcome recovery as explicit policies/use cases.
- **REQ-013**: Retain the optional definitions-only web UI, setup/update workflows, private storage, source recovery, and Herdr labels. Herdr consumes application lifecycle/display events and cannot influence domain state transitions.
- **REQ-014**: Preserve the existing 159 behavior tests or map each to a named replacement before removal. Add kernel-only, adapter contract, authorization, infrastructure, migration, CLI/MCP parity, packaging, and architecture tests. Core correctness cannot depend on an installed agent or authenticated model session.
- **SEC-001**: Treat adapters as trusted bundled integration code, not a security sandbox. Application scope enforcement does not prevent an unrestricted same-user agent from reading storage directly. Report API scope enforcement and verified host isolation separately; confidential launch requirements fail when the configured runner cannot establish the requested boundary.
- **SEC-002**: Do not accept principal identity, project grants, operator status, or credential material from ordinary command/tool payloads. Use verified request contexts and bounded authorization handles. Grant checks cover historical data, source/artifact references, counts, search snippets, and error responses as well as content bodies.
- **SEC-003**: Do not read credential contents, modify global agent settings, start authenticated sessions, or migrate real user data during routine refactor tests. Use explicit fixture HOME/config/PATH/storage roots inside the checkout and fake process/network/authorization ports.
- **CON-001**: Keep the project/package name `orbehelm`, executable `oh`, current source formats, and `legacy/` historical reference. Renaming and new OpenCode functionality are outside this refactor. Preserve existing OpenCode data and retain its launch path as explicitly legacy compatibility until a separate removal decision.
- **CON-002**: Keep reviewed migration revisions `0001` through `0004` byte-identical. New schema work is additive and backed up, with explicit setup/update/migrate execution, row/reference reconciliation, and repeatable recovery. Never edit generated artifacts to perform migration.
- **CON-003**: Keep infrastructure single-process/local-first with SQLite and stdio MCP. No microservices, mandatory daemon, vector database, external message broker, or mandatory model SDK is introduced. Core ports leave room for different implementations later.
- **PAT-001**: Domain decides; application orchestrates; infrastructure performs effects; interfaces serialize; provider plugins translate. Authorization and invocation state are application/domain concerns, never implemented solely in a UI or native command renderer.

### 1.1 Terminology and target ownership

| Type | Layer | Responsibility and invariants |
| --- | --- | --- |
| `Project` | Domain entity | Stable project ID, canonical workspace reference, active configuration revision; owns project-private resources |
| `Orbe` | Domain entity | Stable logical work ID within one project; optional task/parent; survives provider switches; rejects cross-project parent/task bindings |
| `Definition`, `DefinitionRevision`, `CatalogRelease` | Domain entities | Typed reusable sources and immutable publication lineage; profile/specialization/skill/skillset/MCP are definition kinds |
| `ProjectConfiguration` | Domain entity | Shared source reference + project context + local overlays; immutable effective inputs and reproducible historical selection |
| `KUnit`, `KUnitRevision` | Domain entities | Knowledge identity and immutable revisions; ownership/visibility/lifecycle/provenance are explicit |
| `Conversation`, `ConversationEvent`, `Checkpoint` | Domain entities/value records | Ordered captured evidence and working context, independent of knowledge acceptance and native provider |
| `AgentSession` | Domain entity | Binds one Orbe to adapter ID, native ID, context/policy digests, generation, native runtime handle, and capture status |
| `Task`, `Candidate`, `Delegation` | Domain entities | Work ownership, immutable evidence/configuration, ordered review/QA transitions, bounded retries |
| `ToolDefinition`, `ToolInvocation` | Domain entities | Logical deterministic operation/schema and recorded execution lifecycle; no executable import paths supplied by an agent |
| `Principal`, `AccessGrant`, `AccessPredicate` | Domain values/entities | Verified actor identity, bounded authorization, and scope predicates; a definition profile does not grant operator authority |
| `ProjectId`, `OrbeId`, `RevisionId`, `SourceDigest`, `RelativePath`, `PolicyDigest` | Domain value objects | Validation/equality without filesystem access; filesystem canonicalization is a port operation |
| `ProjectRow`, `KUnitRow`, `AgentSessionRow`, etc. | Infrastructure models | SQLAlchemy schema, indexes, constraints, migrations; map to/from domain types explicitly |
| Commands, queries, results, public events | Application DTOs | Versioned input/output contracts; no live ORM objects, `argparse.Namespace`, subprocess objects, or native secrets |

Entities are organized by business responsibility. Do not introduce separate generic
`models/`, `entities/`, and `business_rules/` buckets that duplicate the same concepts.
Business rules live in the relevant domain policy/state-machine module. Persistence
models and transport schemas are deliberately different representations.

### 1.2 Package boundaries and composition

```text
src/orbehelm/
  domain/
    shared/           # IDs, errors, immutable values, domain events
    definitions/      # entities.py, policies.py, composition.py
    projects/         # entities.py, policies.py
    orbes/            # entities.py, policies.py
    knowledge/        # entities.py, policies.py
    conversations/    # entities.py, policies.py, context.py
    coordination/     # entities.py, policies.py
    toolset/          # entities.py, policies.py
    access/           # entities.py, policies.py
  application/
    api.py            # Application.handle; compatibility execute facade
    commands.py
    queries.py
    results.py
    context.py        # VerifiedRequestContext, authorization result
    registry.py       # operation IDs, handler/schema/policy registration
    ports/            # repositories, uow, sources, agents, process, auth, events
    use_cases/        # definitions, projects, orbes, knowledge, conversations,
                      # coordination, tools, authentication
  infrastructure/
    persistence/      # SQLAlchemy models, mappers, repositories, uow, migrations
    filesystem/       # snapshots, journals, locks, layouts, materialization
    network/          # bounded public skill-source downloads
    process/          # process runner, supervision, cancellation
    authorization/    # binding/grant verification; no model-chosen identity
    compatibility/    # legacy readers and explicit identity maps
    packaging/        # installer/update operational code
  interfaces/
    cli/              # parser, renderers, terminal chat
    mcp/              # protocol server, schemas, bound caller context
    web/              # optional shared editor, templates/static assets
  plugins/
    codex/            # adapter, renderer, events, transcript, auth, manifest
    claude/           # adapter, renderer, events, transcript, auth, manifest
    legacy_opencode.py
  integrations/herdr.py
  bootstrap.py        # constructs concrete ports and bundled plugin registry
  cli.py, _entry.py    # existing public entry-point compatibility
```

Dependency rules are enforceable, not advisory:

| Source layer | Allowed internal imports |
| --- | --- |
| Domain | Domain only |
| Application | Application and domain |
| Infrastructure | Infrastructure, application ports/contracts, domain |
| Provider plugins | Own plugin, application ports/contracts, domain |
| External integrations | Own integration, application ports/events, domain values |
| Interfaces | Own interface, application contracts, domain error/value types |
| Bootstrap/entry wiring | Concrete outer layers needed to construct the application |

Only the concrete bootstrap and small interface entry functions may perform composition
root imports. Interfaces cannot query ORM rows. Plugins cannot commit application
transactions. No inward layer imports `core.py`, `product.*`, or a legacy facade as a
shortcut. During transition, a reviewed allowlist identifies temporary legacy edges
and must shrink; no new edge may be added without an architecture-test change.

The final core exports typed use cases and in-memory port implementations suitable
for testing. SQLite is the default runtime adapter; FastAPI/Jinja/Uvicorn become a web
extra. Do not split into separately versioned distributions yet. Keep `requirements.lock`
as the complete development/editor lock and generate a separately tested core-runtime
lock, `requirements-core.lock`, for setup without editor dependencies.

### 1.3 Business rule placement

| Rule family | Domain owner | Application responsibility | Infrastructure responsibility |
| --- | --- | --- | --- |
| Definition grammar, merge precedence, additive requirements | `domain/definitions/policies.py` and `composition.py` | Load inputs through ports, validate candidate, publish | Read sources, fetch bounded dependencies, write verified blobs/journals |
| Project scope, ownership, local reset, source history | `domain/projects/policies.py` | Authorize and coordinate configuration changes | Repository CAS, file recovery, immutable snapshots |
| Orbe identity and native session freshness | `domain/orbes/policies.py`, `domain/conversations/policies.py` | Select context and resume/new plan | Native binding lookup, process supervision, artifact rendering |
| Knowledge access, proposal/acceptance/promotion | `domain/knowledge/policies.py`, `domain/access/policies.py` | Apply verified context before querying/writing/projection | Scoped SQL predicates, private blob access, grant persistence |
| Review-before-QA and stale candidate rejection | `domain/coordination/policies.py` | Snapshot candidate, dispatch child, verify outcome | Process/workspace effects and transactional persistence |
| Tool authorization, idempotency, uncertain outcomes | `domain/toolset/policies.py` | Execute registered plan and persist step/outcome events | Deterministic utility implementations with bounded IO |

### 1.4 API and caller context

`Application.handle(request, verified_context)` accepts a typed `Command` or `Query`
with `api_version=1`, `operation`, `request_id`, optional `idempotency_key`, optional
`expected_revision`, and validated payload. An operation registry maps each operation
to an input type, handler, output type, required capability, scope resolver, and effect
classification. Results contain a stable code, revision/provenance, warnings/coverage,
and structured data. Progress uses a separate event sink; it never corrupts JSON output.

Read-only operations cannot register projects, publish sources, migrate, spawn agents,
or change caches. External reads such as skill update checks are distinct explicit
operations. Preserve current CLI exit codes and raw `get` output through an adapter
over the new result types. Keep `application.execute()` temporarily as a typed-request
translator, not as a second implementation of the business rules.

`VerifiedRequestContext` contains principal ID/type, bound project/orbe/task, granted
capabilities, grant references, request correlation, and scope-policy revision. It is
constructed by authorization/binding infrastructure, never from a model's JSON fields.
A scoped MCP connection cannot widen its scope by passing another project ID. An
operator must obtain an action/project-bounded grant for cross-project private reads;
the presence of a terminal, a profile name, or a `--global` flag is not such a grant.

Grant policy for the first implementation: local operator approval, explicit resource/
operation list, a maximum lifetime of 15 minutes, issuer/audience binding, revocation,
and immutable audit. Agent contexts cannot issue operator grants or publish collective
knowledge. Secret verification material is not exposed through tool metadata, prompts,
history, or ordinary environment dumps. Treat OS-account-level storage access as a
separate runner capability; do not claim this policy alone is a native filesystem sandbox.

The MCP facade must expose at least definition reads/proposals, scoped knowledge
reads/writes, conversation/history reads/checkpoints, deterministic tool calls, and
existing role-appropriate coordination actions. Global definition writes, broad private
reads, acceptance/promotion, authentication launch, and administrative migrations are
operator-only unless an explicit narrow grant authorizes a particular action. CLI
access to all features does not imply every feature is exposed to every agent.

### 1.5 KUnit ownership, visibility, and context

A KUnit has a stable ID/key, ownership kind (`installation`, `project`, `orbe`, or
`task`) and owner ID, originating project/orbe where applicable, and immutable revisions.
Each revision stores content hash, evidence references, author principal, originating
agent-session reference, and creation time. Head movement uses expected-revision checks.

Visibility is `private` or `collective`; lifecycle is separately `reported`, `proposed`,
`accepted`, `superseded`, or `retracted`. A raw transcript entry or reported model claim
is not automatically accepted knowledge. Existing task observations remain scoped
reported evidence; existing accepted project knowledge stays project-private on migration.

| Actor | Collective accepted knowledge | Private knowledge |
| --- | --- | --- |
| Bound agent | Read permitted published revisions | Read/write only the project/orbe/task resources allowed by its verified binding and role |
| Bound agent proposing shared knowledge | Create a proposal with scoped evidence | Cannot flip visibility or accept its own proposal globally |
| Operator | Read and administer published revisions | Own scope or explicit validated project/action grant |
| Unbound/expired/revoked caller | No privileged operations | Denied before content, metadata, counts, or artifact lookup |

Publishing collective knowledge creates an explicitly reviewed released revision/copy;
it never changes a private source record into a public record in place. The release
has a restricted lineage link to its source. Public DTOs omit private project names,
private evidence bodies, and restricted provenance unless the reader is authorized.
Revocation/retraction affects subsequent reads and context construction, including
historical queries. Retrieval caches are keyed by scope/grant and policy revision.

`ContextBundle` is a typed portable projection: effective definitions, accepted scoped
knowledge, explicit working checkpoint, bounded recent messages, retrieved evidence,
and references to older history. Authorization/filtering occurs before ranking,
deduplication, budgeting, or formatting. The core's budget uses an explicit unit and
reported estimate; provider token estimation is an optional port. No exact token/state
equivalence across models is promised. Superseded system/developer instructions and
historical tool calls are retained as evidence but never replayed as executable policy.

### 1.6 Agent and deterministic tool contracts

`AgentAdapter` is a versioned protocol with `describe()`, `probe()`, `render()`,
`start()`, `resume_exact()`, `cancel()`, `decode_event()`, and `auth()` entry points.
It receives a verified launch plan, context bundle, scoped tool endpoint, and injected
process/IO ports. It returns normalized session/events/results; it never obtains a
database session or reimplements project/knowledge authorization.

`AdapterCapabilities` reports mode-specific `full`, `partial`, or `unsupported` status
plus reason and evidence (`fixture-tested`, `live-tested`, or `unverified`) for each
capability. Required capabilities fail before process creation when unsupported.
Probe required command flags with isolated version/help checks; do not assume embedded
flags such as the current Codex `--no-daemon` are valid on every installation. Record
observed versions and probe results; do not invent minimum-version guarantees.

| Capability | Common acceptance contract |
| --- | --- |
| `session.start` | Fresh native conversation under stable authentication storage; returns binding or explicit startup failure |
| `session.resume_exact` | Resume only the known current native ID with matching portable policy and compatible adapter state; no guessed latest session |
| `session.capture_events` | Preserve exposed input/output/tool events and provenance; partial/unknown/malformed streams cannot be reported as complete |
| `session.cancel` | Defined interruption/cleanup outcome; no automatic repeat of uncertain model/tool work |
| `mcp.attach_scoped` | Agent can call the same authorized application tool contracts within its fixed binding |
| `permission.apply_native_grants` | Explicit grants translated only where equivalent support exists; native grants remain separate from OrbeHelm tool authorization |
| `permission.interactive` | Optional callback capability; declare unsupported if the plugin only supports predeclared grants |
| `auth.login` / `auth.status` | Explicit authorized native sign-in and safe metadata; no credential body transfer |
| `runtime.isolation` | Describe verified host enforcement separately from API scope; unmet confidentiality requirements fail closed |

The first plugins reuse the current documented structured CLI transports and native
interactive compatibility. App Server/SDK transports can be added behind the same
ports later if interactive callbacks require them. Do not introduce a mandatory SDK
or change account/billing mode as part of extraction. Store portable policy digest and
adapter compatibility digest separately; unrelated source changes and label changes
must not refresh policy. Provider-specific compatibility changes may require a fresh
native conversation with preserved Orbe/history.

The deterministic `ToolCatalog` initially registers trusted bundled handlers for source
resolution/validation, artifact snapshot/verification, bounded workspace diff, and
authorized memory/history queries. `ToolDefinition` records schemas, capability,
resource scope, effect class, timeout/output limits, and retry classification. Arbitrary
Python import paths or shell scripts supplied by an agent are not handler registrations.

`ToolInvocation` progresses through `requested -> authorized -> running -> succeeded |
failed | cancelled | outcome_unknown`. The application records arguments digest,
scope/principal, idempotency key, step outcomes, and result/evidence references. A
retry with the same key and different arguments is a conflict. Multi-step execution
has per-step records; an uncertain non-idempotent step is inspected/recovered, never
automatically repeated. One plugin may need two native calls where another needs one;
both must satisfy the same logical result/postconditions. Capability absence is explicit.

### 1.7 Reuse and cutover decisions

Reuse composition rules, snapshot formats, source hashes, archive defenses, publication
and project journals, coordination transitions, conversation events/checkpoints,
semantic freshness, installer logic, and the regression suite. Extract them with tests
before changing behavior. Rewrite orchestration boundaries and representations where
they currently mix layers; do not wholesale replace their algorithms.

When replacing `application.py` with the `application/` package, move the old dispatcher
to a temporary compatibility module in the same change. Never leave a file/package
name collision. Keep `core.py`, `adapters.py`, `product.models`, and public CLI entry
imports as forwarding facades until all callers/tests are mapped; they must contain
no new rules. Retire facades only through a recorded compatibility milestone.

Migrations use new tables/mappings before changing old readers. Preserve source paths,
snapshot keys, existing relational IDs/references, and raw history. Frozen migration
files may be moved byte-for-byte to the new resource package only after script-loader
and wheel tests pass; their revision IDs and bytes remain unchanged.

## 2. Implementation Steps

Tasks are ordered by explicit dependencies. Tasks sharing a phase are independent only
when no dependency is listed. Each phase has a measurable exit condition; do not begin
its dependent phase until that condition passes.

### Implementation Phase 1 — Baseline and behavior contracts

- **GOAL-001**: Establish a reviewable migration baseline. Exit: all current behavior contracts are inventoried, 159 baseline tests pass, and source/migration/history formats have recorded compatibility fixtures.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Create `tests/feature_contracts.json` listing every current CLI/API behavior, scope, effect class, existing test IDs, and intended replacement suite. Capture the working-tree baseline and checksums of `product/migrations/versions/0001*.py` through `0004*.py` under `tests/fixtures/compatibility/`. Record prior uncommitted work as input; do not overwrite it. | Yes | 2026-10-29 |
| TASK-002 | Add characterization fixtures for `composition.compose`, `core.resolve/build`, catalog recovery, project override/reset, native identity/resume, conversation capture, and `Coordinator` transitions. Normalize only physical temporary paths; preserve semantic bytes, source/executable-bit hashes, and expected errors. Run the existing full unittest command. Depends on TASK-001. | No | — |
| TASK-003 | Add `tests/architecture/test_boundaries.py` with an AST dependency graph and a reviewed baseline allowlist. Detect layer inversions, import cycles, direct ORM imports from interfaces, and inward references to provider literals/legacy facades. Initially enforce no-new-violations; remove allowlist entries as extraction proceeds. Depends on TASK-001. | Yes | 2026-10-29 |

### Implementation Phase 2 — Domain entities, values, and pure rules

- **GOAL-002**: Make business decisions testable without storage or agents. Exit: domain tests run with site packages disabled and fake IDs/time/input values; composition and workflow characterization cases retain their results.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Add `domain/shared/{ids,errors,events,values}.py`; move identifier/digest/canonical validation contracts out of `core.py` while retaining facades. Define immutable typed IDs and domain errors including conflict, forbidden, unsupported capability, invalid state, and incomplete capture. No I/O or native names. Depends on TASK-002 and TASK-003. | Yes | 2026-10-29 |
| TASK-005 | Add domain entity modules for definitions, projects, orbes, conversations, and coordination as specified in section 1.1. Extract section composition and pure merge/dependency policies from `composition.py`/`core.py`. Replace source reads with supplied source values; return a resolution plan rather than materializing files. Depends on TASK-004. | No | — |
| TASK-006 | Extract `Coordinator._developer/_version`, review/QA transitions, submission/delegation idempotency, and candidate-result rules into `domain/coordination/policies.py`. Extract semantic refresh into `domain/conversations/policies.py`. Keep legacy orchestration calling these policies through facades until repository migration. Depends on TASK-005. | No | — |
| TASK-007 | Add `domain/knowledge` and `domain/access` entities/policies for ownership, visibility, lifecycle, evidence lineage, bounded grants, role restrictions, and promotion/retraction. Add a complete allow/deny matrix using fixed clocks/IDs; do not migrate or expose collective data yet. Depends on TASK-004. | No | — |

### Implementation Phase 3 — Application API and in-memory kernel

- **GOAL-003**: Execute the feature workflows through one typed kernel without SQLAlchemy, frontend dependencies, installed agents, or network access. Exit: the same use cases pass against in-memory repositories and fake effect ports.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | Add `application/{api,commands,queries,results,context,registry}.py`; implement `Application.handle` and operation registration with strict payloads, effect classification, required capability, CAS/idempotency fields, and safe error mapping. Replace root `application.py` atomically with the package and an `execute` compatibility export. Depends on TASK-005 and TASK-007. | No | — |
| TASK-009 | Define protocols in `application/ports/{repositories,uow,sources,agents,process,authorization,events,clock}.py`; add memory/fake implementations in `tests/support/`. Inject clock/IDs/environment/process/network explicitly. Declare transaction ownership at each use case; native/model/network work cannot run in an open SQL transaction. Depends on TASK-008. | No | — |
| TASK-010 | Implement definition/project/orbe/conversation/coordination use cases calling extracted policies through ports. Move behavior from `application.execute`, `product/projects.py`, `product/catalog.py`, `conversations.py`, and `delegation_runner.py` into handlers without changing public semantics. Add `bootstrap.py:create_application` as the concrete wiring boundary. Depends on TASK-006 and TASK-009. | No | — |
| TASK-011 | Implement `application/use_cases/knowledge.py` and `context.py` with verified access predicates before retrieval/projection, explicit proposal/accept/publish/retract operations, lineage filtering, and policy-aware cache keys. Add core workflows for collective queries and scoped private context using in-memory repositories only. Depends on TASK-007 and TASK-009. | No | — |

### Implementation Phase 4 — Infrastructure repositories and effect isolation

- **GOAL-004**: Replace embedded SQL/filesystem effects while retaining storage semantics. Exit: identical repository contracts pass for memory and SQLite, recovery fixtures pass, and no inward module imports concrete effects.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-012 | Move SQLAlchemy rows into `infrastructure/persistence/models.py` and add explicit `mappers.py`, aggregate repositories, read projections, and `uow.py`. Keep `product.models`/`product.database` forwarding exports during transition. Domain/public results must not contain attached or detached ORM instances. Depends on TASK-010. | No | — |
| TASK-013 | Extract snapshots, source loading/materialization, private layouts, publication/context journals, and lock ordering into `infrastructure/filesystem/`. Preserve manifest hashing and recovery decisions exactly; inject these ports into handlers. Extract bounded remote skill transport to `infrastructure/network/skill_sources.py`. Depends on TASK-009 and TASK-012. | No | — |
| TASK-014 | Implement `infrastructure/process/{runner,supervisor}.py` with bounded streams, cancellation, process-group ownership, exit outcomes, and no automatic uncertain-work retry. Extract file tailing as infrastructure independent of provider schema and conversation repositories. Use fake runner contracts and executable fixture processes, never real provider binaries, in automated tests. Depends on TASK-009. | No | — |
| TASK-015 | Implement binding/grant issuance/verification in `infrastructure/authorization/` and inject `AuthorizationPort`. Separate trusted operator approval from bound agent callers; deny supplied principal/operator fields and cross-project scope substitutions. Keep scope enforcement and host-isolation evidence separate in diagnostics and launch requirements. Depends on TASK-007, TASK-009, and TASK-012. | No | — |

### Implementation Phase 5 — Identity and knowledge data migration

- **GOAL-005**: Preserve existing data while introducing independent identity and KUnits. Exit: every legacy record is preserved or explicitly mapped, no private item becomes collective, and fresh/upgrade databases match the new models.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-016 | Add `0006_agent_bindings.py` for canonical logical work-orbe records, native session bindings, conversation-to-orbe links, and namespace-qualified legacy identity maps. Preserve existing `LogicalOrbe` IDs as canonical roots when present. Link Conversation/native rows only through verified existing IDs/metadata and consistent project/task/parent references. Keep unmatched native orbes as separate roots; never merge solely by matching project/profile. Emit a deterministic migration report for ambiguous links; leave them unmerged. Depends on TASK-012. | No | — |
| TASK-017 | Add `0007_knowledge_access.py` for KUnits/revisions, ownership/visibility/lifecycle, restricted provenance, grants/revocations, and audit records. Backfill existing Knowledge/artifact links without changing content or old IDs; map task reported/project proposed/accepted statuses explicitly and keep every imported item private. Do not promote transcripts/checkpoints into accepted KUnits. Depends on TASK-011, TASK-015, and TASK-016. | No | — |
| TASK-018 | Implement `infrastructure/compatibility/identity_map.py` and repository readers that accept old IDs and preserve old metadata paths. Add one-to-one alias uniqueness/collision checks and an explicit operator link/adoption operation for ambiguous historical work; linking cannot delete transcripts or alter immutable candidate references. Read/write cutover occurs per mapped aggregate, never through two independent writers. Depends on TASK-016 and TASK-017. | No | — |
| TASK-019 | Verify upgrade paths from fixtures at 0001/0002/0003/0004 and empty setup, migration reruns/interruption, FK checks, row counts/content digests, privacy defaults, backup permissions, and old-ID lookup. Move frozen migration resources byte-identically only after loader tests exist; update Alembic env/metadata wiring. No real operational database is upgraded during verification. Depends on TASK-018. | No | — |

### Implementation Phase 6 — Codex and Claude provider plugins

- **GOAL-006**: Deliver two implementations of the same capability contract. Exit: shared fake-runner conformance tests pass for both plugins and provider-specific code is absent from the kernel.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-020 | Define `AgentAdapter`, `AdapterCapabilities`, `LaunchPlan`, `NativeSessionBinding`, `NormalizedAgentEvent`, and capture/compatibility outcomes in `application/ports/agents.py` and contracts. Define required capability negotiation and native-grant versus OrbeHelm-tool-policy separation. Add one adapter conformance suite with an injected factory. Depends on TASK-009 and TASK-014. | No | — |
| TASK-021 | Extract Codex command rendering, config translation, structured events, exact-ID discovery, transcript decoding, and safe auth metadata from `adapters.py`, `managed.py`, `native_capture.py`, and `product/authentication.py` into `plugins/codex/`. Invoke all effects via ports; characterize required flags rather than assuming version support. Depends on TASK-020 and TASK-013. | No | — |
| TASK-022 | Extract the equivalent Claude behavior into `plugins/claude/`, including explicit native tool grants, denied-tool events, stable authentication homes, and exact resume. Declare interactive permission callbacks unsupported until implemented; fail requests that require that capability before spawn. Depends on TASK-020 and TASK-013. | No | — |
| TASK-023 | Register bundled plugins in bootstrap, route common launch/refresh/cancel/capture/auth use cases through their contracts, and reduce `adapters.py`/`managed.py` to compatibility delegates. Keep OpenCode behind an explicit legacy capability declaration with preserved histories and no new certification claim. Add a fake two-step adapter and one-step adapter proving one logical operation/postcondition. Depends on TASK-021 and TASK-022. | No | — |

### Implementation Phase 7 — Deterministic toolset and transport parity

- **GOAL-007**: Make CLI/MCP interchangeable clients of authorized application features. Exit: equivalent requests yield equivalent normalized results/audit effects; unsupported or unauthorized work performs no effect.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-024 | Implement domain tool invocation policies and `application/use_cases/tools.py`; register trusted source/artifact/workspace/history utilities with typed schemas and bounded effects. Add `0008_tool_invocations.py` for invocation/step outcomes and idempotency records. Unknown outcomes require inspect/recovery instead of automatic repeat. Depends on TASK-010, TASK-014, and TASK-015. | No | — |
| TASK-025 | Extract CLI parser/renderers/chat UI into `interfaces/cli/`. Replace Namespace passing and direct ORM/Coordinator calls with typed requests. Preserve old flags/exit codes/raw content and add discoverable command help for KUnit ownership, visibility, operator grants, logical-orbe selection, and capabilities. Keep `oh`, `cli.main`, and `_entry.py` compatible. Depends on TASK-011, TASK-018, TASK-023, and TASK-024. | No | — |
| TASK-026 | Extract stdio framing/schemas into `interfaces/mcp/`. Bind verified context at server construction, expose the registered authorized tool subset, validate full schemas, support cancellation/pagination, and prohibit payload-based elevation. Replace direct Coordinator calls with Application.handle. Test parity with CLI for public and project-private operations. Depends on TASK-015, TASK-024, and TASK-025. | No | — |
| TASK-027 | Make the optional editor a thin `interfaces/web/` client for shared definitions/history only. Remove direct SQLAlchemy imports and adapt current CSRF/Host/Origin tests. Move Herdr behavior into `integrations/herdr.py` subscribed to normalized display/lifecycle events via effect ports; label failure cannot change work outcome. Depends on TASK-023 and TASK-025. | No | — |

### Implementation Phase 8 — Test architecture and future-change gates

- **GOAL-008**: Detect architectural and feature regressions without real providers. Exit: all tests are mapped, no architecture allowlist remains for inward code, and the full standard unittest command covers the new suites.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-028 | Organize new tests under `tests/domain`, `application`, `contracts`, `infrastructure`, `interfaces`, `plugins`, `architecture`, and `support`, with discovery-compatible package markers. Preserve top-level regression files until every feature manifest entry points to an equal-or-stronger replacement. Add deterministic randomized invariant tests with seed 4242; no test uses real provider credentials or network by default. Depends on TASK-019, TASK-023, and TASK-027. | No | — |
| TASK-029 | Add an isolated `tests/run_kernel.py` runner usable with `python3 -I -S` and absolute source/test paths. It loads only domain/application and in-memory/fake ports. Make architecture tests enforce the final dependency table, forbid hidden process/network/environment access in inward code, and detect provider literals/native parser code there. Depends on TASK-028. | No | — |
| TASK-030 | Add `.github/workflows/tests.yml` with Linux/macOS and Python 3.11/3.13 jobs; run full unittest, kernel-only tests, architecture checks, migration/model parity, and core-only package smoke checks. Keep live tests in non-default `tests/live/live_codex.py` and `live_claude.py`, runnable only by an explicit operator command with disposable homes and a declared real-model action. Depends on TASK-029. | No | — |
| TASK-031 | Add dev-only coverage measurement and `tests/quality_gates.json`. Record the actual baseline before setting ratchets; enforce 100% branches for access/freshness/workflow policy modules, at least 95% domain branches, and at least 90% application branches at cutover. Do not exempt uncovered business branches or lower a passing baseline. Gate feature-contract completeness and negative authorization cases separately from coverage. Depends on TASK-028. | No | — |

### Implementation Phase 9 — Packaging, compatibility, and release readiness

- **GOAL-009**: Install and update the independent tool without renaming it or losing existing behavior. Exit: core-only install, optional editor install, historical upgrade, adapter fixture runs, and current CLI compatibility all pass in isolated homes.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-032 | Update `pyproject.toml` package data/extras, produce `requirements-core.lock` alongside the full development/editor lock, and move installer mechanics into infrastructure behind compatible `setup.sh`/`update.sh`. Load migrated resources via package resources so wheel installs do not require the source tree. Keep provider CLI installation/auth separate and preserve existing installation options/data. Depends on TASK-019 and TASK-027. | No | — |
| TASK-033 | Add installed-wheel/core-only/optional-web smoke fixtures, repeated setup/update tests, rollback-by-backup instructions, and legacy import/entry-point checks. Verify importing kernel and running fake-adapter workflows works without FastAPI/Jinja/Uvicorn/SQLAlchemy/native CLIs, while SQLite runtime reports missing optional infrastructure clearly. Reconcile every contract in `tests/feature_contracts.json`. Depends on TASK-030, TASK-031, and TASK-032. | No | — |
| TASK-034 | Update README, architecture/configuration/memory/task/installation docs, definition authoring guidance, and a new plugin-authoring contract guide. Record supported/partial capabilities and actual verification evidence. Retire only facades with zero callers and mapped tests; preserve legacy source/history. Run the full required command and isolated CLI/MCP parity suites before cutover. Depends on TASK-033. | No | — |

## 3. Alternatives

- **ALT-001**: Rename files into domain/models/services without extracting behavior. Rejected because SQL/process dependencies and duplicated authorization would remain; directory names alone do not establish an independent tool.
- **ALT-002**: Rewrite the system from scratch. Rejected because composition, snapshots, recovery, task invariants, compatibility, and 159 regression tests are useful and already exercised.
- **ALT-003**: Keep SQLAlchemy rows as the domain model. Rejected because business tests would still need persistence semantics and ORM state would leak through ports/interfaces.
- **ALT-004**: Add separate feature logic to each provider plugin. Rejected because equivalent behavior would drift. Plugins translate one common contract; only native mechanisms differ.
- **ALT-005**: Expose every operator CLI action to every MCP agent. Rejected because transport parity means shared use cases and policy, not identical privileges or model-controlled global access.
- **ALT-006**: Treat private memory as secure because project IDs are checked. Rejected because IDs are not authorization and unrestricted same-account filesystem access is not sandboxed by a Python API.
- **ALT-007**: Introduce microservices, mandatory HTTP, a vector database, and third-party plugin loading immediately. Rejected as unnecessary for the independent local kernel. Ports preserve future options without adding deployment/trust complexity now.
- **ALT-008**: Share a raw native transcript as a portable session. Rejected because prompts, tools, compaction, permissions, and private state differ. Share authorized canonical history/KUnits/context while retaining original native evidence.

## 4. Dependencies

- **DEP-001**: Existing Python 3.11+ runtime and reviewed SQLite/SQLAlchemy/Alembic stack. Domain/application tests require only standard-library/in-memory dependencies; production persistence is injected.
- **DEP-002**: Current source definitions, registries, immutable snapshots, migration revisions, and compatibility fixtures. Their meaning and content hashes must be characterized before extraction.
- **DEP-003**: Bundled Codex/Claude plugin implementations using verified native interface capabilities. Installed CLI version/help and authenticated operation are separate kinds of evidence; no live certification is inferred from fake tests.
- **DEP-004**: Proposed development-only coverage tooling and CI workflows require a tested locked dependency update during implementation. No such tooling was installed during this planning task.
- **DEP-005**: Native filesystem/process isolation is an external runner capability. Scope-safe API behavior is mandatory; confidentiality guarantees require separately verified enforcement and cannot be inferred from model instructions.

## 5. Files

- **FILE-001**: `src/orbehelm/domain/**` contains new pure entities/value objects/policies; extraction starts from `composition.py`, `core.py`, `sessions.py`, and `product/coordination.py`.
- **FILE-002**: `src/orbehelm/application/**` replaces the current `application.py` dispatcher with typed use cases, operation registry, ports, and context authorization.
- **FILE-003**: `src/orbehelm/infrastructure/**` owns persistence models/mappers/repositories/UoW, snapshots/journals, locks/layouts, remote sources, process supervision, bindings/grants, packaging, and legacy identity adapters.
- **FILE-004**: `src/orbehelm/plugins/{codex,claude}/**`, `plugins/legacy_opencode.py`, `bootstrap.py`, and `integrations/herdr.py` own concrete integration wiring without business-rule duplication.
- **FILE-005**: `src/orbehelm/interfaces/{cli,mcp,web}/**` and retained root entry facades expose the application operations; frontend dependencies do not become kernel imports.
- **FILE-006**: New migrations `0006_agent_bindings.py`, `0007_knowledge_access.py`, and `0008_tool_invocations.py`, migration/resource loader tests, and identity reports govern additive storage cutover.
- **FILE-007**: `tests/feature_contracts.json`, `quality_gates.json`, test-layer packages, plugin fixtures, isolated runners, workflow YAML, `pyproject.toml`, locks, setup/update, and operator/plugin documentation enforce the long-term contract.

## 6. Testing

### Suite responsibilities

| Suite | Real components | Fake/injected components | Required assertions |
| --- | --- | --- | --- |
| Domain unit | Pure entities/policies/composition | Fixed clocks, IDs, supplied source values | Invariants, merge results, ownership, transitions, freshness, access matrix |
| Application | Real use-case handlers/authorization/context builder | Memory repositories/UoW, blob/process/network/agent ports | Same business outcomes without SQLite, UI, native binaries, network, or authentication |
| Repository contracts | Same contract suite for memory and SQLite | IDs/time; isolated database fixtures | CAS, rollback, visibility filtering, uniqueness, paging, immutable revision semantics |
| Infrastructure | Filesystem, SQLite, migration loader, fixture processes | Remote transports/credential metadata | Paths/symlinks, hash parity, backups, recovery, locks, cancellation, bounded data |
| Provider contracts | Codex/Claude renderers/parsers/probe logic | Versioned synthetic streams and fake process runner | Common capability outcomes, exact IDs, two-step/one-step equivalence, failures and unsupported modes |
| CLI/MCP/editor | Real serializers and application boundary | Core dependencies selected per scenario | Equivalent authorized results, stable errors/exit codes, strict schemas, scope binding, UI security |
| Architecture/package | AST/import graph, isolated interpreter, built wheel | No provider processes | Allowed dependency direction, no cycles, optional frontend deps, correct resources/entry points |
| Explicit live checks | User-authorized native CLI/provider/Herdr | Disposable application homes; no production project data | Actual versions/auth/stream/permission/rendering evidence, separate from default CI |

- **TEST-001**: Keep a feature-to-test inventory. No existing regression test is deleted until its behavior is covered by a named replacement; test count alone is not a coverage metric. Default `python3 -m unittest discover -s tests -v` must discover all non-live suites.
- **TEST-002**: Domain invariants include identifiers/source grammar, append/override precedence, dependency cycles, project/orbe/task ownership, unique-key/workspace consistency, valid task transitions, review before QA, stale candidate rejection, CAS, and bounded rounds. Add deterministic randomized sequences to check invariants across ordering/retry variations.
- **TEST-003**: Authorization tests cover collective/private × agent/operator × matching/foreign project/task/orbe × active/expired/revoked grant × current/historical revision. Verify denial before returning content, names, counts, snippets, provenance, cached results, or artifact links. Tampering with project/principal/operator payload fields must never widen access.
- **TEST-004**: KUnit tests preserve reported/proposed/accepted distinctions, version history, evidence integrity, explicit acceptance/replacement, released-copy promotion, provenance redaction, retraction/revocation, and no automatic promotion of transcripts or checkpoint text.
- **TEST-005**: Context tests prove the same authorized canonical bundle can be rendered by either plugin; unrelated definitions/labels/paths do not change portable policy. Rule/skill/MCP/tool-policy changes refresh appropriately. Older instructions/tool calls are not replayed. Tool-event volume cannot hide the user goal, and hidden provider state is never claimed transferable.
- **TEST-006**: Provider conformance covers fresh/exact resume, missing/ambiguous IDs, malformed/unknown/oversized events, partial lines, EOF without completion, startup failure, permission denial, changed grants, cancellation, child cleanup, stable authentication homes, and no accidental real spawn in fake tests. Preserve raw evidence and explicit capture status.
- **TEST-007**: Tool tests verify scope/authorization before effects, same-key/same-args idempotency, same-key/different-args conflict, per-step evidence, timeout/cancel, crash after effect before commit, and outcome-unknown recovery. Neither a second plugin nor a retry may double-execute a non-idempotent action.
- **TEST-008**: Infrastructure tests retain all current source/archive containment, symlink, executable-bit, corrupt-snapshot, source-edit conflict, journal recovery, backup, task workspace lock, and immutable candidate checks. Assert file effects remain within fixture roots and credential contents are never read.
- **TEST-009**: Migration tests cover every supported starting schema, fresh/upgrade parity, old-ID resolution, no heuristic identity merges, collision/ambiguous-link reports, unchanged source and history digests, no private-to-collective promotion, reruns, interrupted cutover, and backup-based rollback. Frozen migration bytes/revision IDs are checked explicitly.
- **TEST-010**: Transport tests call the same operations through CLI and MCP with the same verified context and compare normalized results, authorization outcomes, idempotency, and audit effects. Keep editor security tests and verify it exposes only shared-definition operations. Unbound or expired agent MCP contexts fail closed.
- **TEST-011**: Architecture fitness fails on any forbidden import, provider branch/flag/parser in inward modules, new legacy dependency, direct ORM result leakage, or file/process/environment action in kernel-only execution. Test importing kernel/use cases with `-I -S` and no third-party/provider availability.
- **TEST-012**: CI enforces the dependency matrix, coverage ratchets, feature inventory, full unittest suite, core-only/wheel smoke, and reviewed migration checks. Live agent/model and Herdr tests remain explicit opt-in commands with recorded evidence, never hidden prerequisites of domain correctness.

### Release gates

1. Existing behavior contracts and replacement mapping are complete; no unreviewed skips or disabled tests hide missing dependencies.
2. Kernel-only workflows run without SQLAlchemy, FastAPI, installed native agents, or credentials; real SQLite integration still passes separately.
3. Both provider plugins pass the same mandatory conformance suite; optional/partial features are listed explicitly.
4. All negative access and recovery cases pass; no scope widening or duplicate uncertain external action occurs.
5. All migration fixtures preserve provenance, private visibility, IDs/aliases, immutable bytes, and candidate bindings.
6. Architecture allowlist is empty for domain/application, no forbidden imports remain, and coverage/feature gates pass.
7. Fresh setup and upgrade of the built distribution work in isolated homes with the same effective schema; CLI does not require the optional editor.

## 7. Risks & Assumptions

- **RISK-001**: The current working tree contains substantial uncommitted feature work. Establish its tested baseline before moving modules, and avoid mixing unrelated feature edits into extraction commits.
- **RISK-002**: Existing native orbes, logical task orbes, and conversations overlap without one universal identity relation. Preserve unmapped records and require explicit linking rather than guessing or collapsing historical work.
- **RISK-003**: Lazy imports currently conceal dependency cycles. Extraction can expose import-order failures; architecture tests and compatibility facades must prevent circular shortcuts.
- **RISK-004**: SQLAlchemy defaults/relationships, snapshot manifests, legacy fields, and package resource paths have behavioral effects. Migration/model parity, wheel tests, and source-hash fixtures are required before removing old readers.
- **RISK-005**: Same-user arbitrary shell/filesystem access can bypass API isolation. Private-memory claims must distinguish logical authorization from verified host enforcement; a prompt or project flag is not a sandbox.
- **RISK-006**: Global knowledge promotion can disclose private evidence or metadata. Use released copies with reviewed content, filtered public provenance, and operator-only acceptance; never flip an existing private record's visibility silently.
- **RISK-007**: Provider commands/events and permission mechanisms differ and can change. Feature probes and fixture contracts reduce drift but do not prove authenticated live compatibility or identical context.
- **RISK-008**: A plugin operation may have several side effects and uncertain completion. Preserve operation/step state and require explicit recovery; blanket retries can duplicate model/tool actions.
- **RISK-009**: Coverage percentages can encourage superficial tests. Keep invariant matrices, negative authorization tests, multi-step failure cases, and feature mapping as independent gates.
- **ASSUMPTION-001**: The immediate supported plugin scope is Codex and Claude. Existing OpenCode data and explicitly legacy behavior are preserved, but new full-contract parity for OpenCode is not part of this implementation.
- **ASSUMPTION-002**: The application remains local single-operator software initially. This does not remove the need to distinguish operator-approved access from scoped agent access; multi-user remote deployment is a later architecture decision.
- **ASSUMPTION-003**: Full captured history is durable/retrievable, while active context is bounded and provider-specific. No design in this plan claims access to hidden reasoning or exact native internal state.
- **ASSUMPTION-004**: The optional editor remains shared-definition-only. Model interaction is managed CLI or native plugin mode; no new mandatory graphical client is required.

## 8. Related Specifications / Further Reading

- [Current implementation assessment](../docs/independent-core-assessment.md)
- [Existing local CLI and conversation implementation plan](refactor-cli-api-live-definitions-1.md)
- [Current architecture](../docs/architecture.md)
- [Current configuration contracts](../docs/configuration.md)
- [Current conversation capture and limitations](../docs/conversation-memory.md)
- [Current task orchestration](../docs/task-orchestration.md)
- [Validation history](../docs/validation.md)
- [Typed application boundary](../src/orbehelm/application/api.py)
- [Transitional application dispatcher](../src/orbehelm/infrastructure/compatibility/dispatcher.py)
- [Current persistence rows](../src/orbehelm/product/models.py)
- [Current provider/runtime coupling](../src/orbehelm/adapters.py)
- [Current coordination invariants](../src/orbehelm/product/coordination.py)

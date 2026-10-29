---
goal: Add project-scoped versioned configuration and a local management UI
version: 2
date_created: 2026-10-28
last_updated: 2026-10-28
owner: OrbeHelm project
status: In progress
tags: [architecture, web, projects, versioning, migrations]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In_progress-yellow)

The user approved implementation with FastAPI, SQLAlchemy 2, Alembic, Jinja2, and SQLite after rejecting the original Django proposal. The confirmed scope is local single-user operation, whole-project release adoption, and orbe metadata plus launch history. This revision supersedes the Django-specific design. Implementation and automated product validation are complete: 66 tests pass with installed dependencies, real SQLite/Alembic, and ASGI form workflows. The final live-browser and installed-wheel checks remain environment-limited, so the plan stays In progress until those checks can run. No real project state was migrated.

## 1. Requirements & Constraints

- **REQ-001**: Provide a loopback-only UI to inspect/edit existing global Markdown/JSON definitions, inspect release history/diffs, register projects, preview/adopt updates, edit/remove project profile overrides, restore project configurations, and inspect orbes/launches. Creating/deleting definitions through the UI and conversation browsing are excluded.
- **REQ-002**: Use persistent project IDs and unique canonical project paths. Orbe slots retain project + agent + profile + specialization identity. Fresh-orbe rotation preserves old native homes. Each execution has a separate launch record.
- **REQ-003**: Save exact source bytes and executable bits in immutable content-addressed snapshots. Global releases reference definition revisions; project configurations pin a global release, context, aliases, and overrides. Preserve selected skill resources independently of the disposable skill cache.
- **REQ-004**: External definition edits publish a new validated release at normal build/run entry; the UI detects drafts and exposes an explicit publish action. Existing projects stay pinned until adoption. Read-only resolve/doctor/dry runs do not publish or migrate.
- **REQ-005**: Generate only requested configurations under state/projects/<project-id>/builds/<agent>/<hash>. Effective fingerprints include selected source/dependency closure and rendering implementation, not unrelated web code or catalog release IDs.
- **REQ-006**: Adoption stages all already-realized configurations before switching one project pointer. Running agents keep captured builds; subsequent launches refresh their native configuration without rotating orbe identity. Rollback restores a complete prior project configuration, not conversation history.
- **REQ-007**: Apply section-based project overrides after the targeted profile and before specialization. Dependencies remain additive. Detect overlapping upstream section edits using the override's saved base sections; require removing/revising a conflicting override before adoption.
- **REQ-008**: Keep source files authoritative: working files are drafts, snapshots are published source truth, SQL stores relationships and operational state. Recover interrupted source publication using a journal; never import a half-materialized UI edit as another release.
- **REQ-009**: Use reviewed Alembic schema migrations, separate from definition history. Explicit oh migrate initializes/upgrades the database, backs up an existing database, and indexes legacy orbes without moving native homes or reading credentials. Unknown historical provenance remains unknown.
- **SEC-001**: Bind to loopback; validate Host/Origin, require a per-browser CSRF token, bound edit/request sizes, escape source/diff output, reject source traversal/symlinks/runtime/hidden credential paths, and expose no arbitrary file or process endpoints.
- **CON-001**: Preserve legacy/, existing generated/ outputs, auth stores, orbe IDs/homes, and file-lock coordination. Store new state and artifacts within the checkout. Never hand-edit generated output or change global agent configuration.
- **CON-002**: Keep core composition independent of FastAPI and SQLAlchemy; share application services between CLI and UI. Use short synchronous ORM transactions, no transaction spanning a model conversation, no task queue, and no separate frontend build tool.
- **GUD-001**: Report selected configuration, used configuration, and pending effective changes distinctly. Rollback does not pin external model/MCP services or erase history. Retained artifacts record old provenance but do not guarantee identical model behavior.
- **PAT-001**: Use application services in src/orbehelm/product/, portable snapshot operations in src/orbehelm/snapshots.py, and host-specific launches in adapters.py. Enable product state explicitly through migration; retain compatibility CLI behavior until cutover.

### Entity model

| Entity | Key data and invariants |
| --- | --- |
| Project | UUID, unique canonical path, name, active configuration pointer. |
| Definition | Stable source path and kind; includes instructions and referenced resources. |
| DefinitionRevision | Immutable content hash, source path, snapshot reference; unique path/hash. |
| CatalogRelease | Ordered sequence, immutable source snapshot, parent and message; relational release membership. |
| ProjectOverrideRevision | Project, target profile, original section hashes, section-template content. |
| ProjectConfiguration | Project, global release, parent, immutable context/alias snapshot, override references, reason. |
| SelectionLock | Per-configuration selection key and exact resolved dependencies; append-only realizations, no mutable definition content. |
| ConfigurationBuild | Project, effective fingerprint, adapter, artifact path, selected dependency closure and selectors. |
| OrbeSlot | Unique project/agent/profile/normalized-specialization tuple, compatible existing lock key, active orbe. |
| AgentOrbe | Preserved orbe ID, slot, runtime directory, creation time when known, legacy marker. |
| OrbeLaunch | Orbe, captured configuration/build, selectors, start/end/status/exit code, wrapper PID; imported unknowns remain null. |

### Runtime layout

```text
definitions/                              editable source drafts
registry/                                 editable registrations
state/orbehelm.sqlite3                     operational database
state/backups/                            pre-upgrade database backups
state/revisions/<hash>/                    exact immutable source trees
state/projects/<project-id>/builds/        immutable project-derived artifacts
state/orbes/<orbe-id>/               preserved mutable native homes/history
state/orbe-keys/                        compatible active pointers and file locks
state/publications/pending.json            interrupted source-edit recovery journal
generated/                                preserved pre-product build history
```

Source publication writes verified snapshots before database references. A UI edit records an expected global release and file hash, commits its release, then atomically replaces the edited working file. A journal reconciles interruption before the next publication; unexpected external edits cause conflicts instead of overwrites. Filesystem writes and SQLite commits are not a single atomic transaction.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Establish framework boundaries and reviewed entity migrations.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-001 | Replace the Django recommendation with the approved stack; update pyproject.toml with bounded product dependencies and dev HTTP client. | Implemented | 2026-10-28 |
| TASK-002 | Add product/models.py, database.py, and migrations/ with a frozen 0001_initial migration, SQLite foreign keys, bounded busy handling, short orbes, and explicit backup/upgrade. | Verified by integration tests | 2026-10-28 |
| TASK-003 | Verify the user-installed .venv dependencies, record requirements.lock, and execute Alembic/model consistency checks. | Passed | 2026-10-28 |

### Implementation Phase 2

- **GOAL-002**: Implement immutable catalog and project configuration services. Depends on GOAL-001 contracts; integration validation uses the installed project environment.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-004 | Implement snapshots.py with bounded source capture, executable-bit hashing, source-path checks, immutable publication, and corruption verification. Extend core.resolve with independent context/override/cache inputs. | Portable tests pass | 2026-10-28 |
| TASK-005 | Implement product/catalog.py with collection, complete candidate validation, release membership/history/diff, stale edit detection, and journal recovery. | Verified by integration tests | 2026-10-28 |
| TASK-006 | Implement product/projects.py with registration, pinned context/aliases, dependency selection locks, durable skill resource snapshots, impact previews, atomic project adoption, rollback, and section overrides. | Verified by integration tests | 2026-10-28 |

### Implementation Phase 3

- **GOAL-003**: Preserve native conversation identities while adding project builds and launch history. Depends on GOAL-002.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-007 | Implement product/orbes.py legacy indexing without moving homes, reading credentials, or assigning current definitions to old launches. Preserve active pointers and unknown timestamps. | Verified by integration tests | 2026-10-28 |
| TASK-008 | Extend core build namespaces and adapters.launch hooks; record each launch's captured configuration and build, retain five ORBEHELM_* variables, and refresh runtime configuration only at launch. | Verified, including fake running-launch adoption | 2026-10-28 |
| TASK-009 | Add product/commands.py and CLI migrate/web/projects/definitions actions; integrate registered project resolution/builds and database status while retaining legacy behavior before migration and write-free dry runs. | Verified by integration tests | 2026-10-28 |

### Implementation Phase 4

- **GOAL-004**: Expose the local HTML management UI. Depends on GOAL-003.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-010 | Implement product/web.py with FastAPI, bounded URL-encoded forms, Host/Origin validation, CSRF cookies/tokens, local static files, and no model launch endpoints. | Verified by integration tests | 2026-10-28 |
| TASK-011 | Implement Jinja templates and responsive local CSS for definition editing/history, project release/override controls, update diffs, orbes, and launch details. | Verified through rendered ASGI workflows | 2026-10-28 |

### Implementation Phase 5

- **GOAL-005**: Validate migration, versioning, and browser workflows. Depends on TASK-003 and prior implementations.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-012 | Add tests/test_snapshots.py for portable snapshot integrity, source-path rejection, context pin inputs, override ordering, and project namespace checks. | Passed | 2026-10-28 |
| TASK-013 | Add tests/test_product.py for Alembic/model agreement, migration preservation, selective adoption, failure atomicity, overrides/conflicts, publication recovery, context refresh, launch history, legacy import, dry-run immutability, and local UI security/forms. | Passed | 2026-10-28 |
| TASK-014 | Run python3 -m unittest discover -s tests -v and compile checks in the project environment. All 66 tests and compile checks pass; no model conversation was started. | Passed | 2026-10-28 |
| TASK-015 | Run full tests, Alembic consistency checks, package-data checks, and isolated browser smoke flows. Full ASGI workflows, CLI migration/orbe reuse, source assets, and dependency pins pass. Real listener/Chrome checks are blocked by the execution environment; installed-wheel build is blocked by missing setuptools. Preserve these limitations; do not migrate real state for verification. | Partial: browser/wheel checks remain | 2026-10-28 |

## 3. Alternatives

- **ALT-001**: Django was rejected by the user because they prefer a less opinionated framework. Its integrated admin/forms/ORM are not part of this implementation.
- **ALT-002**: React and a separate frontend toolchain remain deferred; server-rendered Jinja templates meet the confirmed local management scope.
- **ALT-003**: Git commits alone do not capture installed resources, project adoption, or uncommitted source inputs; source snapshots and relational references provide those contracts.
- **ALT-004**: Mutable per-orbe-only configuration was rejected; retain immutable per-project builds and independent mutable native homes for provenance and safe updates.
- **ALT-005**: Per-profile global release pins and dependency-removal overrides are deferred in favor of whole-project adoption and existing additive dependency semantics.

## 4. Dependencies

- **DEP-001**: FastAPI, SQLAlchemy 2.0, Alembic, Jinja2, and Uvicorn; HTTPX for tests. Install only inside the checkout's .venv. requirements.lock records the 22 tested runtime/dev pins for Python 3.13/macOS arm64; pip check and offline pin validation pass.
- **DEP-002**: Python 3.11+ with POSIX file locking and SQLite; retain macOS/Linux scope. No global installation or configuration changes.
- **DEP-003**: Host CLIs and their authentication are separate prerequisites for model conversations. The UI and tests do not initiate authenticated model conversations.

## 5. Files

- **FILE-001**: pyproject.toml defines dependency ranges, development HTTP client, and packaged templates/static/migration assets.
- **FILE-002**: src/orbehelm/product/ contains models, migrations, database lifecycle, catalog/project/orbe services, CLI dispatch, and HTTP routes/assets.
- **FILE-003**: src/orbehelm/snapshots.py, core.py, adapters.py, and cli.py implement portable snapshots, project rendering namespaces, and launch integration.
- **FILE-004**: tests/test_snapshots.py and tests/test_product.py cover portable and product behavior respectively; preserve existing tests.
- **FILE-005**: README.md and docs/configuration.md, architecture.md, validation.md document setup, state transitions, migration, and validation limitations.

## 6. Testing

- **TEST-001**: Fresh/repeated migrations preserve projects and enforce foreign keys; Alembic metadata comparison reports no pending schema changes. Historical orbe import is repeatable and never invents configuration/timestamp provenance.
- **TEST-002**: Python edits leave PHP builds reusable, base edits affect all dependent profiles, and pinned projects stay unchanged until adoption. Failed builds/stale requests leave active project configuration untouched.
- **TEST-003**: Restore old source/dependency locks after global edits, preserve native homes and orbe IDs, and record separate launch attempts. Running launch inputs remain fixed; unchanged effective builds do not show false pending changes.
- **TEST-004**: Corrupt snapshots, traversal/symlinks, source-publication interruption, missing dependencies, stale editors, and overlapping override sections fail without silently replacing active state.
- **TEST-005**: Verify loopback binds, Host/Origin/CSRF checks, request limits, escaped source/diff content, and absence of arbitrary file/process/credential endpoints.
- **TEST-006**: Execute the required full unittest discovery without skipping missing dependency checks; report blocked imports. Use isolated verification roots and browser smoke flows after installation, never authenticated model conversations as routine checks.

## 7. Risks & Assumptions

- **RISK-001**: All 66 automated tests pass, including database/UI flows. Actual socket/browser startup and installed-wheel packaging remain unverified because of environment restrictions and unavailable build-backend installation.
- **RISK-002**: SQLite write concurrency and source/database commit boundaries require short transactions, product locks, staged immutable artifacts, and publication recovery. No PostgreSQL compatibility claim is made.
- **RISK-003**: Host resume semantics may retain earlier instructions; configuration rollback cannot erase conversation history or pin external service behavior. Live adapter integration remains separate.
- **RISK-004**: Existing local draft changes are not automatically adopted by pinned projects. Project context and aliases also require explicit refresh; this is an intentional compatibility change after migration.
- **ASSUMPTION-001**: The first product UI is local, single-user, and read-only for orbe processes/conversations. Existing orbes are indexed without relocation.
- **ASSUMPTION-002**: The user installed dependencies after the initial blocked run. Report the successful automated checks and remaining live-browser/wheel limits separately; no authenticated model conversation or real state migration was performed.

## 8. Related Specifications / Further Reading

- [Architecture](../docs/architecture.md)
- [Configuration](../docs/configuration.md)
- [Validation evidence](../docs/validation.md)
- [FastAPI templates](https://fastapi.tiangolo.com/advanced/templates/)
- [SQLAlchemy orbe lifecycle](https://docs.sqlalchemy.org/en/20/orm/orbe_basics.html)
- [Alembic migrations](https://alembic.sqlalchemy.org/en/latest/tutorial.html)

---
goal: Local CLI API, automatically inherited shared definitions, durable cross-agent conversations, and configuration-aware native refresh
version: 2
date_created: 2026-10-29
last_updated: 2026-10-29
owner: OrbeHelm
status: 'Completed'
tags: [architecture, cli, definitions, sessions, memory, herdr, migration]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

Implement the user-approved local service and conversation ownership design. The CLI
and stdio MCP operate without a web listener. The optional editor manages shared
sources/history only. Projects inherit shared changes automatically and retain local
file overrides. Managed Claude/Codex chat captures exposed events into an independent
ledger and hands historical context to a fresh native conversation when needed.

This revision incorporates the follow-up approval for OrbeHelm-owned conversations.
It also replaces disposable authentication homes with stable adapter homes and fresh
native conversation IDs. Native host isolation and exact model context transfer are
not promised. Authenticated model behavior and live Herdr rendering are separately
reported integration checks.

## 1. Requirements & Constraints

- **REQ-001**: `application.py:execute` routes configuration resolve/build, definition operations, library operations, native launch, managed chat, project commands, conversation operations, and coordination actions. Domain modules retain validation and transaction responsibilities.
- **REQ-002**: CLI/native/delegation/MCP work uses local installation/schema checks, not an HTTP readiness requirement. Schema upgrades remain explicit setup/update/migrate actions.
- **REQ-003**: Shared publication appends cheap source-only effective revisions for registered projects without per-project adoption, builds, or remote downloads. Project context, aliases, file overlays, and legacy section overrides are retained. Existing historical configurations remain reproducible.
- **REQ-004**: Typed targets cover base, profile, specialization, skill, skillset, and MCP. `get` returns content/provenance; add/remove/set/override/reset/history/diff/rollback validate scope, ownership, dependencies, and expected revisions. File overrides are local; reset inherits the current shared version.
- **REQ-005**: Shared mutations stage complete source snapshots and use recoverable multi-file writes. Shared rollback publishes restored bytes as a new release. Active skill/MCP usage blocks destructive shared removal; history and local skill source directories remain intact.
- **REQ-006**: The loopback editor exposes shared definitions/resources, registry forms, history, and rollback. Project/task/orbe/authentication management is available through CLI commands; those UI routes are removed. Keep CSRF, Host/Origin validation, request bounds, and escaping.
- **REQ-007**: Store append-only user/assistant/native events and explicit checkpoints in an agent-independent conversation selected by project/profile/spec/task. Stream capture belongs to OrbeHelm, not a model's promise to save its memory. History reads/searches are project-scoped and paginated.
- **REQ-008**: `oh chat` uses structured Claude/Codex CLI streams and supports adapter switching within one conversation. Fresh sessions receive current definitions, a bounded checkpoint/recent-history handoff, and commands for retrieving older evidence. Never replay historical tool calls or obsolete policy as current instructions.
- **REQ-009**: Resume only an exact recorded native ID under unchanged policy and adapter. Policy covers effective composed instructions, selected skill tree hashes, MCP configuration, and explicit managed Claude tool grants, excluding unrelated source changes, release IDs, timestamps, labels, prompts, and physical paths. Changed/unknown policy or agent starts a fresh conversation generation while preserving native login homes and prior transcripts.
- **REQ-010**: Native interactive mode retains best-effort Claude/Codex transcript capture with explicit coverage and failure events. Source-ID deduplication preserves history across imports/restarts. Unsupported adapters start fresh instead of guessing continuation IDs. Failed prior capture blocks implicit native policy refresh.
- **REQ-011**: Herdr prefers HERDR_BIN_PATH, preserves inherited socket routing, sets display-agent/title metadata, and clears only its own metadata. Diagnostics query bounded version/help output. Do not take over native lifecycle authority or relabel parent panes from headless children.
- **SEC-001**: Do not inspect credentials, modify global agent settings, bypass native tool permissions, or claim exclusive isolation. Keep database/backups private and validate paths/symlinks/session identifiers. Conversation history can contain sensitive source and tool data.
- **CON-001**: Preserve existing project/orbe IDs, legacy runtime paths, immutable source history, candidate configuration bindings, coordination semantics, and workspace locks. Keep durable documentation/comments in English and development state inside the checkout.
- **CON-002**: Managed mode currently supports Claude/Codex structured CLI interfaces, not native interactive approval callbacks or OpenCode structured capture. Report denials and unsupported output explicitly; retain native interactive mode for that experience. Do not start an extra authenticated session merely to generate memory summaries.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Remove web readiness as a work prerequisite and establish local API routing.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add `application.py:execute/storage` and route CLI, shared-editor mutations, and MCP coordination calls through allowlisted handlers. Centralize configuration resolve/build and scoped library operations. | Yes | 2026-10-29 |
| TASK-002 | Replace `service.py:require_server` with a compatibility alias for local installation/schema validation. Retain optional editor status/start commands; remove server prerequisite output from installer. Depends on TASK-001. | Yes | 2026-10-29 |

### Implementation Phase 2

- **GOAL-002**: Implement live shared inheritance and project-local file overlays.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-003 | Add reviewed migration `0004_live_conversations.py` and model fields for immutable project file overlays/effective source snapshots, plus conversation/event tables. Preserve old schema data and migration backups. | Yes | 2026-10-29 |
| TASK-004 | Implement `product/definition_operations.py`: typed target ownership, content/provenance reads, UTF-8 package import, local override/reset/tombstones, revision history/diff, scoped rollback, shared edits, and optimistic concurrency. Depends on TASK-003. | Yes | 2026-10-29 |
| TASK-005 | Extend `catalog.py` with multi-file recovery, restore-as-new-release, and automatic source-only project revisions. Reconcile already-published heads during update so older project pins follow current shared sources. No eager build/download is performed. Depends on TASK-004. | Yes | 2026-10-29 |
| TASK-006 | Resolve file overlays in projects, dependency usage, capability inventory, project dependency mutations, and scoped library listing. Retain legacy section overlays and immutable candidate bindings. Depends on TASK-005. | Yes | 2026-10-29 |
| TASK-007 | Reduce `product/web.py` and navigation to shared sources/history/rollback and registry forms. Expose former project/dependency/capability/auth/orbe/task operations through CLI handlers. Depends on TASK-001 and TASK-006. | Yes | 2026-10-29 |

### Implementation Phase 3

- **GOAL-003**: Capture durable history and transfer working context across adapters.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | Implement `conversations.py` with serialized append-only events, source deduplication, scoped search/pagination, explicit checkpoint audit, and bounded historical bootstrap. Store raw exposed events separately from normalized replay context. Depends on TASK-003. | Yes | 2026-10-29 |
| TASK-009 | Implement `managed.py` terminal loop with Claude stream-json/Codex exec-json adapters, stdin prompt transport, native-ID tracking, interruption/failure recording, slash commands, provider switching, orbe launch indexing, and workspace/thread locks. Preserve native permission policy, support explicit process-scoped audited Claude tool rules, refresh on grant changes, and report callback limitations. Depends on TASK-008. | Yes | 2026-10-29 |
| TASK-010 | Add pure policy digest/session-reason logic in `sessions.py`. Refresh native conversations on policy/adapter changes and resume exact known IDs when unchanged; preserve stable authentication homes. Store generation/configuration provenance in events and orbe metadata. Depends on TASK-009. | Yes | 2026-10-29 |
| TASK-011 | Add `native_capture.py` for private Claude/Codex JSONL capture, deduplication, partial-line handling, explicit failures, and bounded event sizes. Exclude historical system/developer instructions from normalized handoffs and strip nested generated handoff wrappers. Update native launch freshness and metadata atomically. Depends on TASK-010. | Yes | 2026-10-29 |
| TASK-012 | Fix Herdr owner-binary discovery, remove the pre-detection agent-name guard from source-scoped display metadata, set both display-agent/title, and expose read-only version/help diagnostics. Never report native semantic state. | Yes | 2026-10-29 |

### Implementation Phase 4

- **GOAL-004**: Verify and document the implemented contract with isolated storage and fake native children.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-013 | Replace obsolete readiness/manual-adoption/project-UI expectations with current service/CLI tests while retaining security, source validation, migration, removal, and coordination coverage. Add `tests/test_cli_memory.py` for handoff, freshness, exact IDs, capture failures, scoped history, and shared rollback. Depends on TASK-011 and TASK-012. | Yes | 2026-10-29 |
| TASK-014 | Run the required complete unittest suite in the checkout virtual environment and isolated real CLI migration/override/reset/build/dry-run checks without authenticated model work. Depends on TASK-013. | Yes | 2026-10-29 |
| TASK-015 | Update README, installation/configuration/architecture/scope/task documentation, the definition authoring guide, and `docs/conversation-memory.md`. Record authenticated-model/Herdr limits and supersede old server/pinning plans. Depends on TASK-014. | Yes | 2026-10-29 |

## 3. Alternatives

- **ALT-001**: Replay old conversations and announce new rules through a user message. Rejected as a universal refresh mechanism because it does not establish replacement of historical system instructions.
- **ALT-002**: Discard native continuation on every launch. Rejected because exact continuation is useful when policy is unchanged.
- **ALT-003**: Change the orbe identity or authentication home on every source hash. Rejected because it fragments work and may require repeated login. Separate conversation generation IDs preserve history and stable login state.
- **ALT-004**: Depend on agents explicitly saving memory or on terminal-screen scraping. Rejected as the primary mechanism. Structured native events are captured by the runner; native transcript mode advertises weaker coverage.
- **ALT-005**: Build every project during shared publication. Rejected because absent working directories and remote dependencies would make edits expensive/fragile. Only effective source revisions are propagated; builds happen on use.
- **ALT-006**: Introduce an HTTP daemon or new SDK dependencies immediately. Rejected for the implemented baseline. The local service and documented structured CLI interfaces provide owned conversation capture while retaining native authentication. Interactive approval callbacks remain a documented future adapter capability.

## 4. Dependencies

- **DEP-001**: Existing Python/SQLAlchemy/Alembic stack, portable resolver, snapshot store, and filesystem locking. No additional daemon or Python dependency is required.
- **DEP-002**: Supported native CLI versions exposing the documented structured interfaces. Provider authentication/model access remain separate prerequisites and are not established by fake-child tests.
- **DEP-003**: Herdr 0.9.5 documentation establishes metadata flags and owner-binary variables. Real rendering on the user's computer remains separate from protocol-fixture tests.

## 5. Files

- **FILE-001**: `src/orbehelm/application.py`, `cli.py`, `service.py`, and `mcp_bridge.py` implement local routing.
- **FILE-002**: `src/orbehelm/product/definition_operations.py`, `catalog.py`, `projects.py`, `models.py`, `database.py`, `dependency_usage.py`, `capabilities.py`, and migration `0004_live_conversations.py` implement source/history storage.
- **FILE-003**: `src/orbehelm/conversations.py`, `managed.py`, `native_capture.py`, `sessions.py`, `adapters.py`, `layout.py`, `herdr.py`, and `product/orbes.py` implement runtime capture, freshness, and integration.
- **FILE-004**: `product/web.py`, shared templates, installer output, `tests/`, `README.md`, `definitions/AGENTS.md`, and `docs/` complete operator workflows and verification.

## 6. Testing

- **TEST-001**: Verify schema/model parity and preserved existing data, source validation/publication recovery, automatic shared propagation, file override/reset, scoped add/remove, and rollback as a new publication.
- **TEST-002**: Verify structured Claude/Codex events, exact native IDs, unchanged-policy resume, changed-policy fresh starts with stable login homes, cross-agent handoffs, preserved history, and failed/partial capture reporting.
- **TEST-003**: Verify project-scoped history/search/pagination and source-ID deduplication; exclude stale system rules and nested handoffs from normalized context. Verify managed attempts appear in the orbe launch index.
- **TEST-004**: Disable HTTP and verify local CLI launches and managed dry runs. Compare filesystem state for read-only commands. Keep migrations explicit and test optional editor CSRF/Host/Origin/escaping and absent project routes.
- **TEST-005**: Exercise Herdr owner-binary discovery and metadata cleanup with fake processes, preserve headless parent labels, workspace locks, candidate immutability, and task coordination semantics.
- **TEST-006**: Run the full unittest command and isolated real CLI smoke checks; report live provider/Herdr checks as unverified unless actually performed.

## 7. Risks & Assumptions

- **RISK-001**: Different models cannot share identical internal context, hidden reasoning, private prompts, or opaque compaction state. The guarantee is retrievable captured history plus bounded handoff.
- **RISK-002**: Native transcript mode is best-effort and version-dependent. Oversized/malformed records are explicitly incomplete; legacy history is imported only from the selected private runtime.
- **RISK-003**: Structured mode does not yet own interactive native tool approval callbacks. Tool denials are reported without bypassing permissions; native interactive mode remains available.
- **RISK-004**: A shared source update can invalidate a local replacement. Fail the affected configuration clearly rather than silently retaining old rules or discarding its override.
- **RISK-005**: Event capture and checkpoints may contain sensitive user/code/tool data. Database/backups are private, but installation owners remain responsible for access and retention.
- **ASSUMPTION-001**: Default typed override/reset scope is the selected project. Shared publication applies installation-wide; it does not synchronize other computers automatically.
- **ASSUMPTION-002**: The default `oh` command retains the native interface for compatibility. `oh chat` explicitly selects the OrbeHelm-owned conversation interface and restores the stored selection when a thread ID is supplied.

## 8. Related Specifications / Further Reading

- [Conversation behavior and limitations](../docs/conversation-memory.md)
- [Configuration](../docs/configuration.md)
- [Scope and removal](../docs/configuration-scopes-and-removal.md)
- [Architecture](../docs/architecture.md)
- [Herdr 0.9.5 CLI](https://github.com/herdrdev/herdr/blob/v0.9.5/docs/next/website/src/content/docs/cli-reference.mdx)
- [Claude programmatic CLI](https://code.claude.com/docs/en/headless)
- [Official OpenAI documentation: Codex commands](https://learn.chatgpt.com/docs/developer-commands)

---
goal: Implement keyed task orbes, shared memory, and deterministic developer/reviewer/QA delegation
version: 1
date_created: 2026-10-29
last_updated: 2026-10-29
owner: OrbeHelm
status: 'Completed'
tags: [feature, orchestration, memory, mcp, migration]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-green)

Implement the approved task-scoped parent/child workflow. Native histories stay separate; OrbeHelm validates state, identity, persistence, and results.

## 1. Requirements & Constraints

- **REQ-001**: Add `--unique-key` to native conversation identity without changing legacy identities. Persist logical task/role orbes independently of native agent choice and derive child keys from their parent and delegation key.
- **REQ-002**: Store task revisions, immutable candidate snapshots, knowledge, delegation records/results, and durable events under the checkout. Keep project knowledge outside native conversation homes.
- **REQ-003**: Enforce developer submission, reviewer approval, QA completion, revision validity, bounded attempts, duplicate suppression, and recovery in shared application services.
- **REQ-004**: Inject an OrbeHelm stdio MCP bridge into keyed native runtime configuration. Expose scoped context, knowledge, submission, delegation, and result operations. Execute explicit reviewer/QA child requests through native CLI adapters.
- **SEC-001**: Validate runtime inputs, path containment, role/task scope, and expected versions. Never bypass native approvals or read credential contents. No authenticated model conversations during verification.
- **CON-001**: Use current Python 3.11+ dependencies and a reviewed Alembic migration. Keep the resolver portable and unkeyed behavior compatible. Migration of real user state remains an explicit CLI action.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Persist keyed identity and task memory.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add schema revision `0002` and models for tasks, logical orbes, artifacts, knowledge, delegations, and events; add unique key to native slot uniqueness while preserving old rows. | Yes | 2026-10-29 |
| TASK-002 | Add shared coordination services for task/orbe binding, bounded immutable artifacts/candidates, optimistic state transitions, context retrieval, and scoped knowledge. Depends on TASK-001. | Yes | 2026-10-29 |
| TASK-003 | Wire CLI keyed orbes, optional workspace selection, native conversation records, and runtime MCP configuration overlays without affecting build fingerprints. Depends on TASK-002. | Yes | 2026-10-29 |

### Implementation Phase 2

- **GOAL-002**: Execute and verify delegation.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Implement cancellable native child execution and scoped stdio MCP tools with strict JSON input handling, duplicate delegation protection, and staged result validation. Depends on TASK-002, TASK-003. | Yes | 2026-10-29 |
| TASK-005 | Add task inspection/knowledge acceptance/recovery CLI operations and read-only task UI. Document exact workflow, migration, artifact locations, and adapter limitations. Depends on TASK-004. | Yes | 2026-10-29 |
| TASK-006 | Test migration from 0001, legacy compatibility, two-task separation, parent-key propagation, workflow gates, immutable evidence, MCP protocol, fake native child round trips, cancellation, and crash recovery. Run the required unittest suite and isolated CLI checks. Depends on TASK-005. | Yes | 2026-10-29 |

## 3. Alternatives

- **ALT-001**: Shared reviewer pools and profile-level pub/sub. Deferred in favor of task-specific child runs and correlated results.
- **ALT-002**: Vector database, external broker, or provider SDK dependency. Unnecessary for the local first implementation.
- **ALT-003**: Unstructured transcript copying and completion inferred from process exit. Rejected; explicit typed results and submitted revision references are required.

## 4. Dependencies

- **DEP-001**: Existing SQLAlchemy/Alembic, immutable snapshot helpers, portable profile resolver, native CLI runtime homes, and standard-library JSON-RPC stdio transport.

## 5. Files

- **FILE-001**: `src/orbehelm/product/models.py`, `database.py`, migration `0002_task_coordination.py`, and coordination application services.
- **FILE-002**: `src/orbehelm/cli.py`, `adapters.py`, runtime bridge/runner modules, product orbe and UI code.
- **FILE-003**: New coordination/MCP tests and updated docs/README.

## 6. Testing

- **TEST-001**: Verify additive migration preserves orbe UUIDs, old slot keys, configuration records, and default unkeyed launch behavior.
- **TEST-002**: Verify key separation, source validation, cross-task rejection, duplicate writes/delegations, stale approvals, and atomic workflow updates.
- **TEST-003**: Exercise native-runner commands with fake child executables, including MCP result staging, cancellation, uncertain exits, and retries without model access.
- **TEST-004**: Exercise stdio initialize/tools/list/tools/call and validate runtime overlays for each native adapter. Run `python3 -m unittest discover -s tests -v` using the project environment.

## 7. Risks & Assumptions

- **RISK-001**: Provider CLI integration and credentials differ; fake tests and help output do not establish live model integration or exclusive isolation.
- **RISK-002**: Unique orbe keys isolate conversations, not source files. Users must choose separate task workspaces when parallel developers must avoid shared edits.
- **ASSUMPTION-001**: First workflow supports developer-owned tasks and reviewer/QA child roles. Delegation is explicit, bounded, and synchronous from the parent's MCP call; no automatic recursive triggering.

## 8. Related Specifications / Further Reading

- [Coordination proposal](../docs/task-coordination-and-memory-proposal.md)
- [MCP stdio](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
- [Codex CLI](https://learn.chatgpt.com/docs/cli/reference)
- [Claude CLI](https://code.claude.com/docs/en/cli-reference)
- [OpenCode CLI](https://opencode.ai/docs/cli/)

## Implementation evidence

All six implementation tasks are complete. The required full unittest suite passed 118 tests on Python 3.13.1, including migration with active legacy orbe references and fake-native MCP round trips. Alembic reported no model/schema differences. See `docs/validation.md` and `state/verification/capabilities/orchestration-full.log`. No real database migration or authenticated model conversation was executed.

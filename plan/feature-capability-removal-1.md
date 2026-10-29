---
goal: Remove explicit project additions and unused shared registrations without cascading changes
version: 1
date_created: 2026-10-28
last_updated: 2026-10-28
owner: OrbeHelm
status: 'Completed'
tags: [feature, web, skills, mcp, removal]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

Implement the removal recommendation approved by the user: project actions remove only explicit additions; shared removal is blocked by active references. Keep immutable history and native runtime state.

## 1. Requirements & Constraints

- **REQ-001**: Expose removal confirmation and inherited requirement explanations for project skills and MCP servers.
- **REQ-002**: Block shared removal while current shared definitions, transitive skill dependencies, or active project configurations reference the registration.
- **REQ-003**: Recheck usage and expected configuration/release during the POST action. Never cascade deletion.
- **SEC-001**: Require existing CSRF and loopback controls; never inspect credentials, delete history, change running homes, or run model conversations.
- **CON-001**: Preserve additive merge semantics, portable agent-independent dependency identity, existing source recovery, and Python 3.11 compatibility. Add no dependencies or database migrations.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Deliver guarded removal services.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add `src/orbehelm/product/dependency_usage.py` to inspect pinned declarative graphs and active selection locks without network calls. Produce usage links and effective requirement origins. | ✅ | 2026-10-28 |
| TASK-002 | Extend `catalog.collect_catalog` and `recover_publication` with source tombstones and add guarded `remove_registration`; retain prior snapshots and local skill source folders. Depends on TASK-001. | ✅ | 2026-10-28 |
| TASK-003 | Refactor project context addition into a shared change function and implement `remove_project_dependency` using the existing context journal and candidate validation. | ✅ | 2026-10-28 |

### Implementation Phase 2

- **GOAL-002**: Expose and verify removal workflows.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Add GET confirmation and POST removal routes in `web.py`, shared-library usage links, project addition controls, provenance labels, and `templates/removal.html`. Depends on TASK-001, TASK-002, TASK-003. | ✅ | 2026-10-28 |
| TASK-005 | Add disposable integration tests for usage, aliases, transitive requirements, stale requests, failed preparation, recovery, history preservation, and UI/CSRF behavior. Update configuration/removal docs and run `python3 -m unittest discover -s tests -v`. Depends on TASK-004. | ✅ | 2026-10-28 |

## 3. Alternatives

- **ALT-001**: Cascading deletion or a project disable mask. Rejected because neither is authorized and both change additive inheritance.
- **ALT-002**: Retirement while active projects reference an item. The user chose blocking shared removal instead.

## 4. Dependencies

- **DEP-001**: Existing immutable catalog/project snapshots, selection locks, source journals, and Jinja/ASGI stack.

## 5. Files

- **FILE-001**: `src/orbehelm/product/dependency_usage.py`, `catalog.py`, `projects.py`, `capabilities.py`, and `web.py`.
- **FILE-002**: `src/orbehelm/product/templates/library.html`, `project_capabilities.html`, `project.html`, and `removal.html`.
- **FILE-003**: `tests/test_product.py`, `docs/configuration.md`, `docs/configuration-scopes-and-removal.md`, and `docs/validation.md`.

## 6. Testing

- **TEST-001**: Confirm direct/transitive current references block shared removal, historical-only references do not, and alias shadowing is respected.
- **TEST-002**: Confirm project removal preserves inherited requirements and independent additions; failed preparation restores source/configuration.
- **TEST-003**: Confirm confirmation GETs are read-only, POSTs enforce CSRF/expected revisions and current usage, deletion recovery preserves external edits, and snapshots/credentials/runtime homes remain intact.

## 7. Risks & Assumptions

- **RISK-001**: Incomplete or corrupt dependency provenance must fail closed rather than falsely report unused.
- **ASSUMPTION-001**: Usage is scoped to OrbeHelm-managed definitions and current project configurations; native host plugins and historical runtime artifacts are not purged.

## 8. Related Specifications / Further Reading

- [Approved scope and removal rules](../docs/configuration-scopes-and-removal.md)
- [Configuration](../docs/configuration.md)
- [Architecture](../docs/architecture.md)

## Delivery Evidence

All 101 tests passed in the project Python 3.13 environment. The log is `state/verification/capabilities/removal-unittest.log`. Static confirmation previews for inherited project requirements, blocked shared removal, and unused shared removal were rendered in Playwright and screenshots saved under `state/verification/removal-preview/`. The blocked view exposes no removal button; project and shared views highlight their correct navigation scopes. Read-only checks against the current checkout correctly block shared removal of both `webapp-testing` and `playwright`. No real project dependency, credential, native home, or orbe was removed during verification. No model conversation was started.

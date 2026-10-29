---
goal: Make project navigation and capability management understandable and actionable
version: 1
date_created: 2026-10-28
last_updated: 2026-10-28
owner: OrbeHelm
status: 'Completed'
tags: [feature, web, skills, mcp, authentication]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

Provide task-based navigation, shared library creation, project dependency assignment, and bounded host-native MCP login jobs. Preserve portable dependency identity and native runtime boundaries.

## 1. Requirements & Constraints

- **REQ-001**: Provide active navigation, project tabs, concise summaries, visible primary actions, and recoverable form errors.
- **REQ-002**: Create skill and MCP registrations through validated library forms and publish immutable catalog releases without changing existing project pins.
- **REQ-003**: Enable catalog dependencies in project context with conflict checks, rollback on failure, and selected configuration validation.
- **REQ-004**: Start and cancel dedicated MCP OAuth login commands from the project MCP tab, using the selected native runtime and allowlisted server name.
- **SEC-001**: Preserve loopback, Origin, CSRF, escaping, and CSP controls. Never accept arbitrary shell text, read credential contents, or persist raw authentication output.
- **CON-001**: Add no libraries or schema changes. Keep runtime state in the checkout and do not start a model conversation during verification.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Add validated capability management services.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Extend `src/orbehelm/product/catalog.py` with single-registration creation and recovery for new files; add `library.py` for form validation and library listings. | ✅ | 2026-10-28 |
| TASK-002 | Extend `src/orbehelm/product/projects.py` with project-context dependency assignment, preserving current release and optimistic revision checks. | ✅ | 2026-10-28 |
| TASK-003 | Add `src/orbehelm/product/authentication.py` for fixed-command login jobs, timeouts, process cleanup, status, cancellation, and runtime scoping. | ✅ | 2026-10-28 |

### Implementation Phase 2

- **GOAL-002**: Deliver navigation and application workflows.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Update `web.py`, project and library templates, and `static/app.css` with active navigation, project tabs, library creation, dependency selection, and authentication progress pages. Depends on TASK-001, TASK-002, TASK-003. | ✅ | 2026-10-28 |
| TASK-005 | Add regression tests for creation, conflicts, assignment, auth command scoping, cancellation, invalid requests, and navigation. Run the required unittest suite and inspect changed files. Depends on TASK-004. | ✅ | 2026-10-28 |

## 3. Alternatives

- **ALT-001**: Expose a general browser terminal. Rejected because dedicated forms and fixed CLI actions are clearer and retain existing permission boundaries.
- **ALT-002**: Apply library changes to all projects automatically. Rejected because project release adoption remains explicit.

## 4. Dependencies

- **DEP-001**: Existing catalog publication, project snapshots, native runtime homes, and agent CLI MCP login commands.

## 5. Files

- **FILE-001**: `src/orbehelm/product/catalog.py`, `projects.py`, `library.py`, `authentication.py`, `web.py`.
- **FILE-002**: `src/orbehelm/product/templates/`, `static/app.css`, `tests/test_product.py`, new workflow tests, and `docs/configuration.md`.

## 6. Testing

- **TEST-001**: Validate atomic publication, failed creation, duplicate names, unsafe sources, source conflicts, and project pin preservation.
- **TEST-002**: Validate correct runtime environments, duplicate login reuse, failure, timeout, cancellation, shutdown cleanup, and no raw output disclosure using fake commands.
- **TEST-003**: Exercise project tabs, library forms, CSRF, active navigation, assignment, and authentication routes through ASGI. Run `python3 -m unittest discover -s tests -v` in the project environment.

## 7. Risks & Assumptions

- **RISK-001**: Host CLI login behavior differs by version. Live OAuth requires the user to finish provider sign-in; fake-process tests do not establish provider integration.
- **RISK-002**: A newly registered capability must be adopted into a project's release before it can be enabled there.
- **ASSUMPTION-001**: Authentication remains runtime-specific; no shared orbe or memory design is introduced.

## 8. Related Specifications / Further Reading

- [Configuration](../docs/configuration.md)
- [Codex MCP](https://developers.openai.com/codex/mcp)
- [Claude MCP](https://code.claude.com/docs/en/mcp)
- [OpenCode MCP](https://opencode.ai/docs/mcp-servers/)

## Delivery Evidence

The project environment ran all 86 unittest cases successfully. ASGI workflows cover every project tab, library creation and validation, release pin preservation, project assignment, source-write recovery, and fixed login routes. Fake child processes cover completion, failure, deduplication, timeout, cancellation, and shutdown. Isolated Codex login help confirms the installed command surface. Six standalone HTML previews were generated under `state/verification/ui-navigation/pages/`; a headless Chrome screenshot attempt exited 134 before rendering. No actual provider sign-in or authenticated model conversation was started. Live browser OAuth, Claude/OpenCode command compatibility, and visual browser rendering remain unverified.

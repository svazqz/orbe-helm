---
goal: Install OrbeHelm with separate orbe homes and a required local server
version: 1
date_created: 2026-10-29
last_updated: 2026-10-29
owner: OrbeHelm
status: 'Deprecated'
tags: [feature, installation, server, storage]
---

# Introduction

Historical plan. Its required-server and manual shared-release-adoption contracts are
superseded by [the local CLI and conversation plan](refactor-cli-api-live-definitions-1.md).
Installation layout and immutable history remain in use.


![Status: Deprecated](https://img.shields.io/badge/status-Deprecated-red)

Install a self-contained application from a clone, retain user definitions on reinstall,
and require a matching healthy server before creating or launching an orbe.

## 1. Requirements & Constraints

- **REQ-001**: `setup.sh` checks Python 3.11+, venv, and pip, installs locked Python dependencies, initializes the database, and creates a launcher.
- **REQ-002**: The confirmed application default is `~/bin/orbehelm`; runtime homes default to `~/.orbehelm/orbes`; application state and database remain in the application directory.
- **REQ-003**: Detect zsh, bash, fish, or POSIX shell startup configuration and add the installed `bin` directory to PATH in one idempotent managed block.
- **REQ-004**: `oh server start` runs the server in the foreground; `oh server status` reports readiness. Real orbe launches require a ready server with matching root and runtime-home identities.
- **SEC-001**: Do not copy checkout state, credentials, or global agent settings. Keep installed homes private; preserve existing data and custom definitions on reinstall.
- **CON-001**: Installer verification uses temporary homes inside the checkout. Dry runs remain read-only and do not require a server. Native model execution remains a separate integration action.
- **PAT-001**: A versioned `installation.json` configures storage and server location; checkout-only use retains existing storage paths.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Implement deterministic installed storage and an idempotent installer.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add `src/orbehelm/layout.py` to validate installation metadata, locate orbe/auth storage, and identify a matching server. Integrate helpers in adapters, compatibility readers, and capability runtime validation. | Yes | 2026-10-29 |
| TASK-002 | Add executable `setup.sh` and `src/orbehelm/installer.py` with configurable destinations, dependency setup, safe source copying, database initialization, and shell PATH management. Depends on TASK-001. | Yes | 2026-10-29 |

### Implementation Phase 2

- **GOAL-002**: Enforce server readiness and verify the complete installation workflow.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-003 | Add `src/orbehelm/service.py`, a bounded loopback health probe, and `/healthz` in `product/web.py`; wire server commands and pre-launch checks into `cli.py`, `adapters.py`, and `delegation_runner.py`. Depends on TASK-001. | Yes | 2026-10-29 |
| TASK-004 | Add installer/storage/readiness integration tests, update existing fake-launch fixtures to stub readiness explicitly, and run the full unittest suite in `.venv`. Depends on TASK-002 and TASK-003. | Yes | 2026-10-29 |
| TASK-005 | Update `README.md`, `docs/installation.md`, and `docs/validation.md` with installation, PATH activation, manual server startup, storage, dependency, and verification limits. Depends on TASK-004. | Yes | 2026-10-29 |

## 3. Alternatives

- **ALT-001**: Literal `/bin/orbehelm` was rejected in favor of the user-confirmed writable `~/bin/orbehelm` location.
- **ALT-002**: Automatically starting a daemon is excluded because manual server startup was requested.
- **ALT-003**: Routing all orchestration operations through HTTP is deferred; the existing local database and stdio MCP architecture remains, with an explicit readiness prerequisite.

## 4. Dependencies

- **DEP-001**: Python 3.11+ with venv/ensurepip and the packages in `requirements.lock`; the first dependency installation may require network access.
- **DEP-002**: A separately installed and authenticated supported agent CLI is required to execute real model work.

## 5. Files

- **FILE-001**: `setup.sh`, `src/orbehelm/installer.py`, `layout.py`, and `service.py` implement installation and service discovery.
- **FILE-002**: `src/orbehelm/cli.py`, `adapters.py`, `compatibility.py`, `delegation_runner.py`, `product/web.py`, and `product/capabilities.py` integrate the runtime contract.
- **FILE-003**: `tests/`, `README.md`, `docs/installation.md`, and `docs/validation.md` contain regression coverage and operator documentation.

## 6. Testing

- **TEST-001**: Verify install/reinstall, preserved definitions/data, destinations with spaces, isolated shell RC files, missing dependencies, and offline dependency fixtures.
- **TEST-002**: Verify external orbe homes, auth paths, capability discovery, stable reuse, and rejection of an unrelated server.
- **TEST-003**: Verify offline launch failure before writes, read-only dry runs, live health schema, and startup/status behavior without authenticated model execution.

## 7. Risks & Assumptions

- **RISK-001**: Dependency downloads and loopback binding may be restricted by the verification environment; report these limits instead of claiming successful live integration.
- **RISK-002**: Shell RC files can be customized or symlinked; preserve existing content and back up any file changed by the installer.
- **ASSUMPTION-001**: Installation is per-user on macOS or Linux; installation does not require sudo or change global agent configuration.

## 8. Related Specifications / Further Reading

- [Architecture](../docs/architecture.md)
- [Task orchestration](../docs/task-orchestration.md)
- [Project instructions](../AGENTS.md)

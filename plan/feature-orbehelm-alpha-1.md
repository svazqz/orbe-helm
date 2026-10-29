---
goal: Implement a portable profile composition and orbe launch alpha
version: 0.1.0a1
date_created: 2026-10-27
last_updated: 2026-10-27
owner: OrbeHelm project
status: Completed
tags: [feature, architecture, alpha]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

Provide a working local CLI that composes reusable instructions, tracks content changes, installs selected local skill resources, generates agent-specific configuration, and launches agent orbes. Completion applies to the alpha scope defined below, not full host isolation or live validation of every adapter.

## 1. Requirements & Constraints

- **REQ-001**: Support `oh --agent=codex --profile=developer --spec=php --skillset=quality` and explicit resolve, build, doctor, and run commands.
- **REQ-002**: Resolve base, profile, specialization, skillsets, optional project context, skill dependencies, and MCP registry entries.
- **REQ-003**: Cache generated output by SHA-256 content fingerprints and verify cached output before reuse.
- **SEC-001**: Reject source traversal, skill symlinks, cyclic dependencies, unknown definition fields, and mismatching skill pins; keep environment secret values out of generated output.
- **CON-001**: Keep all project artifacts inside `/path/to/orbehelm`; preserve previous files under legacy; use English documentation and a Python 3.11 standard-library runtime on POSIX systems.
- **GUD-001**: Report adapter limitations explicitly and refuse requests for unsupported strict isolation.
- **PAT-001**: Keep portable resolution in core.py, host translation in adapters.py, and argument handling in cli.py.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Establish reusable source definitions and the resolver.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-001 | Preserve earlier artifacts in legacy and create definitions, registry, examples, and package metadata. | Yes | 2026-10-27 |
| TASK-002 | Implement core.resolve with ordered layers, source provenance, skill dependency ordering, MCP validation, and content fingerprints in src/orbehelm/core.py. Depends on TASK-001. | Yes | 2026-10-27 |

### Implementation Phase 2

- **GOAL-002**: Generate, cache, install, and launch selected configurations. Depends on GOAL-001.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-003 | Implement core.install_skill and core.build with tree hashes, output inventories, POSIX locking, staged publication, and cached-output repair. | Yes | 2026-10-27 |
| TASK-004 | Implement adapters.render, adapters.launch, adapters.doctor, and adapters.authenticate for generated Codex, Claude, and OpenCode configurations and explicit Codex login. Depends on TASK-003. | Yes | 2026-10-27 |
| TASK-005 | Implement cli.main and executable oh with command dispatch, dry runs, root selection, error reporting, and exit-code propagation. Depends on TASK-004. | Yes | 2026-10-27 |

### Implementation Phase 3

- **GOAL-003**: Validate alpha behavior and document supported use. Depends on GOAL-002.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-006 | Execute tests/test_orbehelm.py behavioral tests and smoke-test build reuse, adapter dry runs, and doctor. | Yes | 2026-10-27 |
| TASK-007 | Check generated config with installed Codex using mcp list, without starting a model conversation; record limitations and results in docs/validation.md. Depends on TASK-006. | Yes | 2026-10-27 |
| TASK-008 | Publish README.md and docs/configuration.md and docs/architecture.md describing installation, state, composition, credentials, and unsupported features. Depends on TASK-007. | Yes | 2026-10-27 |

## 3. Alternatives

- **ALT-001**: Git status as the cache key was rejected because it does not reliably represent uncommitted content and adds a repository dependency.
- **ALT-002**: YAML definitions were deferred to avoid a runtime parser dependency in alpha; versioned JSON provides explicit machine-readable configuration.
- **ALT-003**: Remote installers and native skill activation were deferred until source trust, version pinning, and host discovery behavior can be integrated and tested.

## 4. Dependencies

- **DEP-001**: Python 3.11 or later with fcntl on macOS or Linux.
- **DEP-002**: A separately installed, compatible, authenticated target agent CLI for live launches.
- **DEP-003**: Required local MCP executables and environment variables supplied by the user environment.

## 5. Files

- **FILE-001**: src/orbehelm/core.py contains schema validation, resolution, skill installation, and build caching.
- **FILE-002**: src/orbehelm/adapters.py contains host translation, health checks, authentication, and launch state.
- **FILE-003**: src/orbehelm/cli.py, src/orbehelm/__init__.py, oh, and pyproject.toml define the CLI and version.
- **FILE-004**: definitions, registry, and examples contain initial profiles, specializations, skills, MCP registration, and project context.
- **FILE-005**: tests/test_orbehelm.py and docs/validation.md hold behavioral coverage and validation evidence.
- **FILE-006**: README.md, docs/configuration.md, and docs/architecture.md describe supported use and constraints.

## 6. Testing

- **TEST-001**: Run `python3 -m unittest discover -s tests -v` and require all 16 tests to pass, including cache invalidation, corruption repair, dependency handling, schema errors, Unicode TOML, adapter output, and mocked authentication and launch.
- **TEST-002**: Run two identical Codex build commands and require the same output path with cached false then true.
- **TEST-003**: Run Claude and OpenCode dry runs and inspect generated launch arguments and files without requiring those binaries.
- **TEST-004**: Run installed Codex mcp list with a verification CODEX_HOME containing generated config; require exit 0 and no model conversation.

## 7. Risks & Assumptions

- **RISK-001**: Host configuration discovery can introduce additional instructions, native skills, or MCP entries; alpha reports this and refuses strict mode.
- **RISK-002**: Claude and OpenCode CLI compatibility remains unverified live because those binaries are absent from the initial validation environment.
- **RISK-003**: Authentication state, model connectivity, MCP server operation, and interactive orbe behavior require subsequent integration validation.
- **ASSUMPTION-001**: Local definitions and registered skill sources are maintained and reviewed by the project owner; skill installation does not execute scripts.

## 8. Related Specifications / Further Reading

- [Configuration](../docs/configuration.md)
- [Architecture](../docs/architecture.md)
- [Validation](../docs/validation.md)

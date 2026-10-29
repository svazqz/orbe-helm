---
goal: Add user defaults and on-demand mapped skill installation
version: 1
date_created: 2026-10-27
last_updated: 2026-10-27
owner: OrbeHelm
status: 'Completed'
tags: [feature, configuration, skills]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

Read optional ~/.orbehelmrc defaults and skill mappings, select skills directly, and install missing remote skills on demand.

## 1. Requirements & Constraints

- **REQ-001**: Support an INI file with ORBEHELM defaults and SKILLS aliases; explicit CLI options override defaults.
- **REQ-002**: Resolve direct --skills selections together with existing layer dependencies, without duplicates.
- **REQ-003**: Support HTTPS SKILL.md endpoints and GitHub skill folders including their resources; cache verified installations under the checkout.
- **CON-001**: Dry runs write no files, including when a remote skill is missing. Remote content may be read in memory to determine its content hash.
- **SEC-001**: Bound downloads, reject unsafe archive entries and embedded URL credentials, and never execute downloaded scripts. Do not launch authenticated model conversations.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Define configuration and remote source loading.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add src/orbehelm/configuration.py to load defaults, normalize paths, validate keys and map skill aliases. | ✅ | 2026-10-27 |
| TASK-002 | Add src/orbehelm/remote_skills.py for bounded in-memory downloads, safe GitHub subtree selection, content verification, and cached source lookup. | ✅ | 2026-10-27 |

### Implementation Phase 2

- GOAL-002: Integrate and verify the complete workflow.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-003 | Extend core.resolve and core.install_skill for direct selections, mapped local/remote sources, and existing dependency handling. Depends on TASK-002. | ✅ | 2026-10-27 |
| TASK-004 | Extend cli.main with --config and --skills, precedence, merged skill listings and installation. Depends on TASK-001, TASK-003. | ✅ | 2026-10-27 |
| TASK-005 | Add examples/orbehelmrc and configuration documentation; create the requested ~/.orbehelmrc without overwriting an existing file. Depends on TASK-004. | ✅ | 2026-10-27 |
| TASK-006 | Add tests for precedence, invalid configuration, full resource installation, cache reuse, malformed downloads, and read-only dry runs; run the full suite and verify a real Laravel build without launching a model. Depends on TASK-003, TASK-004, TASK-005. | ✅ | 2026-10-27 |

## 3. Alternatives

- **ALT-001**: Use globally installed Codex skills; rejected because OrbeHelm must manage its selected dependencies inside this checkout.
- **ALT-002**: Download only SKILL.md from GitHub; rejected because relative reference files would be missing.

## 4. Dependencies

- **DEP-001**: Python standard library configparser, urllib, zipfile, and the existing build/skill caches.

## 5. Files

- **FILE-001**: src/orbehelm/configuration.py, src/orbehelm/remote_skills.py, src/orbehelm/core.py, and src/orbehelm/cli.py implement the workflow.
- **FILE-002**: tests/test_configuration.py and tests/test_orbehelm.py verify behavior with isolated homes and mocked network responses.
- **FILE-003**: examples/orbehelmrc, README.md, docs/configuration.md, and docs/architecture.md document supported defaults, formats, and limits.

## 6. Testing

- **TEST-001**: Verify default-file discovery, explicit overrides, empty list overrides, validation, and local mappings.
- **TEST-002**: Verify remote skill resource preservation, bounded downloads, unsafe-entry rejection, pin mismatch, cache reuse, and dependency selections.
- **TEST-003**: Snapshot filesystem state around cold and warm dry runs and verify no model conversations are launched.
- **TEST-004**: All 40 tests passed. A real public GitHub Laravel download and build succeeded, preserved references, and was reused with cached=true through ~/.orbehelmrc. No model conversation was started. The requested home configuration was created without overwriting any existing file.

## 7. Risks & Assumptions

- **RISK-001**: A mutable remote branch can change; installed content remains cached until its URL changes or that source cache is removed. Commit-specific URLs and optional hash pins make updates explicit.
- **ASSUMPTION-001**: Public HTTPS sources require no credential inspection or private-repository authentication.
- **ASSUMPTION-002**: Missing remote content must be read in memory for dry-run hashing; no installation occurs until build or normal launch.

## 8. Related Specifications / Further Reading

- [Configuration](../docs/configuration.md)
- [Architecture](../docs/architecture.md)
- [Laravel Specialist source](https://github.com/Jeffallan/claude-skills/tree/main/skills/laravel-specialist)

---
goal: Make development, updates and releases repeatable
version: 1
date_created: 2026-10-30
last_updated: 2026-10-30
owner: OrbeHelm
status: In progress
tags: [process, installation, release, verification]
---
# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

Implement the prioritized development audit without changing public CLI contracts or runtime ownership.

## 1. Requirements & Constraints

- **REQ-001**: Validate candidate code and a separate environment before replacing installed files; retain recovery artifacts.
- **REQ-002**: Supply one contributor entry point and reproducible version/artifact/release gates.
- **REQ-003**: Isolate operator-memory fixtures and preserve production binding enforcement.
- **REQ-004**: Document current memory, provider verification, dependency updates and capacity checks.
- **SEC-001**: Do not update the live installation, download model weights, publish releases or change credentials.
- **CON-001**: Preserve existing uncommitted handoff work and historical migration bytes; write artifacts inside this checkout.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Protect failed updates.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Change src/orbehelm/installer.py install to prepare candidate source/environment, verify imports and version, retain replaced files and recover failed activation before migration; test failures in tests/test_installation.py. | Yes | 2026-10-30 |

### Implementation Phase 2

- **GOAL-002**: Establish development and release gates; depends on Phase 1.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-002 | Add scripts/dev.py and scripts/check_release.py; validate version/tag/changelog/pins; update .github/workflows/verify.yml and add draft-release workflow with retained artifacts. | Yes | 2026-10-30 |
| TASK-003 | Isolate tests/memory/test_chat.py environment and test denied operator operations with a synthetic binding. | Yes | 2026-10-30 |
| TASK-004 | Configure incremental Ruff/mypy/coverage checks and dev dependencies in pyproject.toml and requirements-dev.lock. | Yes | 2026-10-30 |

### Implementation Phase 3

- **GOAL-003**: Make operating instructions current; depends on Phase 2.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-005 | Rewrite docs/knowledge-memory.md as current behavior; update README.md, docs/releases.md, docs/installation.md and add docs/development.md with dependency, architecture, live-provider and capacity procedures. | Yes | 2026-10-30 |
| TASK-006 | Run full tests, kernel, quality, wheel and release preparation; submit explicit scope and delegate same-candidate reviewer/QA; resolve reports. | No | 2026-10-30 |

## 3. Alternatives

- **ALT-001**: Replace frameworks or complete the kernel rewrite first; rejected because existing boundaries support incremental features.
- **ALT-002**: Reuse and mutate the active virtual environment; rejected because failed dependency installation can damage the previous working release.

## 4. Dependencies

- **DEP-001**: Existing project Python 3.13 environment, unittest and pinned runtime packages.
- **DEP-002**: Ruff, mypy and coverage in a project-only dev environment; current primary documentation governs their configuration.

## 5. Files

- **FILE-001**: src/orbehelm/installer.py and tests/test_installation.py own staging/activation behavior.
- **FILE-002**: scripts/, pyproject.toml, requirements-dev.lock and .github/workflows/ own repeatable verification.
- **FILE-003**: docs/development.md, docs/releases.md, docs/installation.md, docs/knowledge-memory.md and README.md own current operating guidance.

## 6. Testing

- **TEST-001**: Inject dependency and activation failures in disposable installations; verify previous launcher/source/manifest remain intact.
- **TEST-002**: Run python3 -m unittest discover -s tests -v and isolated kernel checks using the project environment.
- **TEST-003**: Build a wheel, verify imports/migrations and release version agreement; retain local evidence.
- **TEST-004**: Exercise memory CLI against disposable synthetic operator/agent contexts; never bypass the live binding.

## 7. Risks & Assumptions

- **RISK-001**: Database migration may make old code incompatible; retain incomplete marker and explicit recovery instructions after migration failure rather than claiming automatic downgrade.
- **RISK-002**: Authenticated provider and remote CI execution require external execution; report unexecuted checks.
- **ASSUMPTION-001**: User authorization covers recommended implementation and project-only development tools, not publication or live installation replacement.

## 8. Related Specifications / Further Reading

- [Audit](../docs/development-audit-2026-10-30.md)
- [Persistent workflows](../docs/persistent-workflows.md)
- [Ruff configuration](https://docs.astral.sh/ruff/configuration/)

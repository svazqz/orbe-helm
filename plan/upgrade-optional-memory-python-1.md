---
goal: Restore optional memory installation on Python 3.11 and publish alpha 4
version: 1
date_created: 2026-10-30
last_updated: 2026-10-30
owner: OrbeHelm
status: In progress
tags: [bug, dependencies, memory, release]
---
# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

Repair the optional-memory lock generated on Python 3.13, verify supported interpreter
compatibility and release package 0.1.0a4/tag v0.1.0-alpha.4.

## 1. Requirements & Constraints

- **REQ-001**: Resolve requirements-memory.in to hashed pins compatible with Python 3.11 and 3.13 on macOS/Linux.
- **REQ-002**: Validate real optional dependency installs/imports and protect compatibility in ordinary CI without model downloads.
- **REQ-003**: Keep real-model integration explicit and cover both tested Python versions in that workflow.
- **REQ-004**: Synchronize version, changelog and current memory/release guidance for alpha 4.
- **SEC-001**: Do not change the live application, global Python/agent configuration or credential contents.
- **CON-001**: Regenerate requirements-memory.lock with pip-tools; never edit generated dependency hashes.
- **CON-002**: Preserve the task submission limit until an operator authorizes another assessment; require same-revision reviewer/QA and CI before publication.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Produce and test the compatible optional resolution.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add numpy<2.5 to requirements-memory.in and regenerate requirements-memory.lock with pinned pip-tools/hash generation. | Yes | 2026-10-30 |
| TASK-002 | Install disposable Python 3.11 inside state/verification, install dev/memory locks into isolated environments and test runtime imports plus focused memory regressions. | Yes | 2026-10-30 |

### Implementation Phase 2

- **GOAL-002**: Protect and release the fix; depends on Phase 1.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-003 | Add optional dependency installation/import checking to .github/workflows/verify.yml on each OS/Python matrix entry and expand .github/workflows/memory.yml to Python 3.11/3.13. | Yes | 2026-10-30 |
| TASK-004 | Update pyproject.toml, src/orbehelm/__init__.py, README.md, CHANGELOG.md and current docs for 0.1.0a4. Run scripts/dev.py release and dependency audit. | Yes | 2026-10-30 |
| TASK-005 | Submit explicit candidate source including frozen workflow bytes, run independent reviewer/QA and remote CI, then push annotated tag and publish verified GitHub artifacts. | No | 2026-10-30 |

## 3. Alternatives

- **ALT-001**: Document Python 3.13-only optional memory; rejected because Python 3.11 is an existing supported target.
- **ALT-002**: Separate interpreter-specific optional locks; rejected while one conservative NumPy constraint can support both targets.

## 4. Dependencies

- **DEP-001**: Existing FastEmbed 0.9.1, project-pinned pip-tools, and a NumPy release supporting Python 3.11.
- **DEP-002**: Installed uv for a checkout-local Python 3.11 interpreter using --no-bin and explicit installation/cache paths.

## 5. Files

- **FILE-001**: requirements-memory.in and requirements-memory.lock define the fixed resolution.
- **FILE-002**: .github/workflows/verify.yml and .github/workflows/memory.yml protect installation and opt-in model integration.
- **FILE-003**: Package metadata, changelog and current guides define the new release and remove the resolved limitation.

## 6. Testing

- **TEST-001**: Real Python 3.11/3.13 hash-checked installs, pip check, optional runtime imports and focused memory tests.
- **TEST-002**: Full unittest/kernel/quality/coverage and wheel/source archive checks.
- **TEST-003**: Actual GitHub Linux/macOS Python 3.11/3.13 jobs install optional dependencies and exercise memory tests without weights.
- **TEST-004**: Independent same-revision reviewer/QA and post-tag artifact checksum verification.

## 7. Risks & Assumptions

- **RISK-001**: Other optional transitive dependencies may have narrower interpreter/platform support; installation and CI must validate the complete lock.
- **RISK-002**: Existing embedding fingerprints may require explicit reconfiguration after a dependency update; do not rewrite operational memory configuration.
- **ASSUMPTION-001**: Publication targets the existing GitHub alpha-release channel and leaves the installed application untouched.

## 8. Related Specifications / Further Reading

- [Memory guide](../docs/knowledge-memory.md)
- [Release process](../docs/releases.md)
- [NumPy 2.4 support](https://numpy.org/doc/stable/release/2.4.0-notes.html)
- [uv local Python installations](https://docs.astral.sh/uv/guides/install-python/)

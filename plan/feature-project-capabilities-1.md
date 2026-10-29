---
goal: Display project skills and agent-scoped MCP authentication metadata
version: 1
date_created: 2026-10-28
last_updated: 2026-10-28
owner: OrbeHelm
status: 'In progress'
tags: [feature, web, skills, mcp]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

Expose the dependencies of realized project selections without changing pinned content or starting model conversations.

## 1. Requirements & Constraints

- **REQ-001**: Show skill instructions, source, resources, declared version when present, content digest, and explicit upstream content checks.
- **REQ-002**: Show MCP transport and authentication metadata scoped to the selected agent runtime; retain unknown and unsupported states.
- **REQ-003**: Keep portable configuration fingerprints and dependency locks independent of agents. Preserve agent-specific render outputs and native conversation slots as approved by the user.
- **SEC-001**: Never read credential files, display subprocess output, start model conversations, or run skill scripts. Bound CLI status checks and require CSRF for checks.
- **CON-001**: Keep state in the checkout, preserve pinned dependencies, and add no dependencies or database migrations.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Build dependency presentation and explicit checks.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add `src/orbehelm/product/capabilities.py` to read current selection locks, skill resources, source metadata, and safe check reports. Add agent-scoped MCP status querying in `src/orbehelm/adapters.py`. | ✅ | 2026-10-28 |
| TASK-002 | Extend `src/orbehelm/product/web.py` and `templates/project.html` with selection and agent controls, dependency details, and CSRF-protected check actions. Depends on TASK-001. | ✅ | 2026-10-28 |

### Implementation Phase 2

- **GOAL-002**: Verify behavior and document limits.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-003 | Add `tests/test_capabilities.py` and product integration coverage for source changes, safe errors, runtime scoping, escaping, and cross-agent fingerprint reuse. Depends on TASK-002. | ✅ | 2026-10-28 |
| TASK-004 | Run `python3 -m unittest discover -s tests -v`, inspect changed sources, and update `docs/configuration.md` with status semantics and support limits. Depends on TASK-003. | ✅ | 2026-10-28 |

## 3. Alternatives

- **ALT-001**: Treat credentials or environment presence as authentication. Rejected because existence does not prove authentication.
- **ALT-002**: Automatically update dependencies during rendering. Rejected because project selections are pinned and GET requests must not mutate configuration.

## 4. Dependencies

- **DEP-001**: Existing SQLAlchemy selection locks, verified snapshots, Jinja templates, and remote skill downloader.
- **DEP-002**: Codex CLI JSON authentication metadata. Unsupported host status interfaces must return unknown rather than infer success.

## 5. Files

- **FILE-001**: `src/orbehelm/product/capabilities.py`, `src/orbehelm/adapters.py` — dependency inspection and status checks.
- **FILE-002**: `src/orbehelm/product/web.py`, `src/orbehelm/product/templates/project.html` — project view and check action.
- **FILE-003**: `tests/test_capabilities.py`, `tests/test_product.py`, `docs/configuration.md` — verification and documentation.

## 6. Testing

- **TEST-001**: Assert local and remote content comparisons detect changes without modifying installed content or lock fingerprints; failed checks remain unknown.
- **TEST-002**: Assert runtime-scoped metadata maps only supported authentication states, handles timeout/invalid output, and never exposes raw output.
- **TEST-003**: Assert web selection validation, HTML escaping, CSRF, no CLI/network checks on GET, and cross-agent reuse of the same selection lock.

## 7. Risks & Assumptions

- **RISK-001**: Host status APIs differ; Claude and OpenCode lack a verified equivalent of the Codex JSON metadata interface in this checkout.
- **RISK-002**: Skills need not declare semantic versions. Content changes mean a different upstream revision, not necessarily a newer semantic version.
- **ASSUMPTION-001**: Inventory covers OrbeHelm-managed dependencies of realized selections; host-discovered plugins remain outside this portable inventory.

## 8. Related Specifications / Further Reading

- [Configuration](../docs/configuration.md)
- [Architecture](../docs/architecture.md)
- [Codex MCP](https://developers.openai.com/codex/mcp)
- [Claude MCP](https://code.claude.com/docs/en/mcp)

## Delivery Evidence

The project inventory, explicit content checks, Codex authentication metadata adapter, and agent-independent dependency reuse checks are implemented. The full suite passed 75 tests under the project Python 3.13 environment. The system Python could not import SQLAlchemy; verification used `.venv/bin` on PATH. CLI verification used an isolated home and started no model conversation. Browser rendering and authenticated server access were not exercised. Claude and OpenCode authentication status adapters remain unfinished; the overall plan remains In progress for that requirement.

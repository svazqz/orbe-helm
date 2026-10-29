---
goal: Compose shared and role instructions by explicit sections
version: 1
date_created: 2026-10-27
last_updated: 2026-10-27
owner: OrbeHelm
status: 'Completed'
tags: [feature, architecture, migration]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

Replace whole-file concatenation of reusable definitions with deterministic section composition.

## 1. Requirements & Constraints

- **REQ-001**: Base, profiles, and specializations use the same seven ordered sections and an explicit version marker.
- **REQ-002**: Sections append by default; an explicit override replaces all inherited content in that section. Empty additions inherit and empty overrides clear. Empty final sections are omitted.
- **REQ-003**: Generated instructions contain no composition directives, source document titles, or authoring preambles. Source provenance remains in resolved.json.
- **CON-001**: Preserve plain Markdown support for optional project and skillset context; do not change adapter delivery or skill dependency behavior.
- **SEC-001**: Do not start authenticated orbes or modify global configuration, credentials, or legacy files.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Define and migrate the common format.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add section parsing and composition in src/orbehelm/composition.py; reject malformed structured sources. | ✅ | 2026-10-27 |
| TASK-002 | Migrate definitions/base/instructions.md, all profile Markdown, and developer specializations; provide definitions/TEMPLATE.md and update the specialization template. Depends on TASK-001. | ✅ | 2026-10-27 |

### Implementation Phase 2

- GOAL-002: Integrate, document, and verify composition.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-003 | Compose during core.resolve and consume the result in core.build; preserve source hashes and skill delivery. Depends on TASK-001. | ✅ | 2026-10-27 |
| TASK-004 | Document modes, order, empty behavior, migration, and compatibility in docs/configuration.md, docs/architecture.md, and README.md. Depends on TASK-003. | ✅ | 2026-10-27 |
| TASK-005 | Add behavioral tests, run python3 -m unittest discover -s tests -v, and verify all profiles and adapters with isolated dry runs. Depends on TASK-002, TASK-003, TASK-004. | ✅ | 2026-10-27 |

## 3. Alternatives

- **ALT-001**: Keep concatenating documents after removing preambles; rejected because it cannot express explicit section overrides.
- **ALT-002**: Use an external template engine; rejected because fixed sections and two modes require no new dependency.

## 4. Dependencies

- **DEP-001**: Python standard library and existing resolver, build cache, adapters, and unittest suite.

## 5. Files

- **FILE-001**: src/orbehelm/composition.py and src/orbehelm/core.py implement portable composition.
- **FILE-002**: definitions/base, definitions/profiles, definitions/specializations, and definitions/TEMPLATE.md define reusable content.
- **FILE-003**: tests/test_orbehelm.py, docs/configuration.md, docs/architecture.md, and README.md validate and document behavior.

## 6. Testing

- **TEST-001**: Verify append, replacement, clearing, empty inheritance, canonical order, and malformed-source rejection.
- **TEST-002**: Verify all profile templates, specialization/project layering, rendered adapter payloads, skill preservation, and cache invalidation.
- **TEST-003**: Completed 23 unit tests and 24 isolated CLI dry runs covering all profiles, specializations, and adapters. No model conversations started. Built representative Personal Assistant and Developer/PHP bundles in the checkout for inspection.

## 7. Risks & Assumptions

- **RISK-001**: Explicit overrides can remove shared rules; document full replacement semantics and require source review. Host permissions remain unchanged.
- **RISK-002**: Existing custom base/profile/specialization Markdown must migrate to the structured format; fail clearly rather than silently treating it as unstructured context.
- **ASSUMPTION-001**: Optional plain project or skillset instructions remain additive context and do not participate in section replacement.

## 8. Related Specifications / Further Reading

- [Configuration](../docs/configuration.md)
- [Architecture](../docs/architecture.md)

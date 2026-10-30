---
goal: Implement isolated persistent workstreams, typed knowledge and parallel assessment
version: 1
date_created: 2026-10-30
last_updated: 2026-10-30
owner: OrbeHelm
status: Completed
tags: [feature, migration, sessions, memory, coordination]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

Implement the approved product proposal without merging native histories or modifying
the installed application, global agent configuration or operational database.

## 1. Requirements & Constraints

- **REQ-001**: Stable project/profile/key workstreams contain isolated specialization contexts and provider-native sessions.
- **REQ-002**: Native, managed and delegated provider commands request full execution privileges.
- **REQ-003**: Persist typed evidence-linked outcomes with project/private/global scope and audience; do not automatically capture arbitrary replies as shared knowledge.
- **REQ-004**: Review and QA independently assess the same immutable candidate; both gates are required for completion.
- **SEC-001**: Preserve private-source provenance and enforce canonical scope/audience checks before retrieval.
- **CON-001**: Add migrations; preserve historical migration bytes and existing native references. Use project Python 3.11+ environments.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Establish compatible identity and execution contracts.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-001 | Add workstream/context mappings to persistence and connect conversation/native launch metadata; specialization does not select a different logical task owner. | ✅ | 2026-10-30 |
| TASK-002 | Update provider command plans and runtime config ownership; lock all developer workspaces and preserve native trust configuration. | ✅ | 2026-10-30 |

### Implementation Phase 2

- **GOAL-002**: Implement granular knowledge and independent assessment, after Phase 1.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-003 | Extend KUnit metadata/migration, scoped retrieval and CLI/MCP inputs; replace reply capture with explicit typed outcomes and preserve unclassified audit records without automatic injection. | ✅ | 2026-10-30 |
| TASK-004 | Update coordination policies, per-candidate gate aggregation and concurrent dispatch; retain immutable source validation and idempotent requests. | ✅ | 2026-10-30 |
| TASK-005 | Add regression tests, update documentation, run full suite and pure kernel checks; inspect final diff. | ✅ | 2026-10-30 |

## 3. Alternatives

- **ALT-001**: Reuse one transcript across specializations; rejected because it violates context isolation.
- **ALT-002**: Promote raw assistant prose to shared knowledge; rejected because it transports role instructions and unverified claims.

## 4. Dependencies

- **DEP-001**: Existing SQLAlchemy/Alembic, local memory engine and Codex/Claude adapter contracts; no new libraries.

## 5. Files

- **FILE-001**: `src/orbehelm/product/migrations/versions/0006_persistent_workflows.py` and persistence models.
- **FILE-002**: `src/orbehelm/{adapters,managed,memory,memory_bridge,conversations,delegation_runner}.py`, provider plugins and domain/application policies.
- **FILE-003**: Coordination, memory, provider contract and new workflow tests; product documentation.

## 6. Testing

- **TEST-001**: Identity stability across specialization/provider changes, isolated histories, legacy mapping and concurrent launch conflicts.
- **TEST-002**: Typed knowledge idempotency, audience/project authorization, private derivation, unclassified quarantine and no raw reply capture.
- **TEST-003**: Both assessment completion orders, independent failures, stale candidates and concurrent/idempotent dispatch.
- **TEST-004**: `python3 -m unittest discover -s tests -v` under the existing project virtual environment; `python3 -I -S tests/run_kernel.py`.

Result: 266 regression tests and 24 isolated kernel tests passed on Python 3.13.
Alembic/ORM parity, historical migration checksums and architecture import boundaries
passed. Codex resume help confirmed the full-access flag in an isolated HOME/CODEX_HOME;
no authenticated model started. The optional real-embedding CLI smoke was attempted
but could not configure its model because FastEmbed is not installed in the available
environments. Keyword/fixture-vector retrieval and actual stdio are covered by tests.
Evidence: `state/diagnostics/workflow-verified-tests.log`,
`workflow-verified-kernel.log` and `workflow-memory-cli.log`.

## 7. Risks & Assumptions

- **RISK-001**: Full-access providers do not provide same-user filesystem isolation; live provider behavior is separate from fixture contracts.
- **RISK-002**: Historical knowledge may contain instructions; retain audit access without automatic cross-role sharing.
- **ASSUMPTION-001**: The user approved this product contract and full-access execution defaults; authenticated sessions and installed rollout remain separate actions.

## 8. Related Specifications / Further Reading

- [Approved product proposal](../docs/product-workflow-proposal.md)
- [Current architecture](../docs/architecture.md)
- [Knowledge memory](../docs/knowledge-memory.md)

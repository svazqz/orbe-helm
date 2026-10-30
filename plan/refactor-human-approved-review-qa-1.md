---
goal: Sequential review with recorded human approval and operator-launched QA
version: 1
date_created: 2026-10-30
last_updated: 2026-10-30
owner: OrbeHelm maintainers
status: Planned
tags: [coordination, workflow, configuration, migration]
---

# Introduction

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

Replace mandatory parallel reviewer/QA orchestration with developer revision → reviewer → human approval → explicit operator QA. This is an implementation proposal, not an implemented feature. Existing entities and verified gaps are documented in [the analysis](../docs/entities-and-human-review-workflow.md).

## 1. Requirements & Constraints

- **REQ-001**: Submit a complete immutable candidate before assessment. Accept local source snapshots and explicitly pinned remote revision references; never assess a moving branch as the approved revision.
- **REQ-002**: Developer automation may launch reviewer only. Remove new parallel assessment launches. QA is launched only by an operator CLI command after human approval; ordinary developer tests remain allowed.
- **REQ-003**: Reviewer approval transitions to `awaiting_human_approval` and ends the automated run. Human approval transitions to `approved_for_qa` without launching a process. QA pass transitions to `complete`.
- **REQ-004**: Reviewer changes requested, human rejection or QA failure returns work to `developing`. Any changed source must be resubmitted and independently approved again. Preserve blocked-stage provenance and explicit recovery.
- **REQ-005**: Reviewer inherits the submitting developer's effective specialization unless pinned project configuration explicitly overrides it. An explicit null override selects no specialization. Missing definitions fail before launch.
- **REQ-006**: CLI exposes task identity, candidate revision, next required actor, submission count and limit. A task version is a concurrency token, not a Git revision.
- **SEC-001**: Human approval is a recorded operator attestation bound to candidate, source digest and completed reviewer result. Do not expose human approval through an agent MCP tool or accept a payload boolean as proof of human identity.
- **SEC-002**: State guards, version checks, source validation and scheduling execute in software before any model launch. Preserve evidence/audience restrictions and idempotent persistence.
- **CON-001**: Keep portable domain logic independent of provider CLI implementation. No new library is required for this workflow.
- **CON-002**: Do not edit generated builds, installed runtime files, historical migrations or the legacy directory. Ship definition and engine changes together.
- **CON-003**: Preserve existing history and explicit task keys. Do not silently grant human approval to historical parallel assessments or reset task budgets.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Define and persist the sequential workflow. No model execution is needed for this phase.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-001 | Update `src/orbehelm/domain/coordination/policies.py` guards and `assessment_state` to implement REQ-002 through REQ-004. Distinguish review result, human decision and QA result; reject concurrent assessment scheduling and stale candidate operations. | No | — |
| TASK-002 | After TASK-001, add `src/orbehelm/product/migrations/versions/0007_human_review_workflow.py` and matching entities in `src/orbehelm/infrastructure/persistence/models.py`. Persist approval receipts with candidate ID, source digest, reviewer result ID, decision, operator attribution, timestamp and idempotency key; persist workflow policy/version and effective delegation specialization. Carry blocked stage in durable state/event data. | No | — |
| TASK-003 | After TASK-002, update `Coordinator.submit_work`, `_create_delegation`, `_refresh_assessments` and `reopen` in `src/orbehelm/product/coordination.py`; add operator decision and QA-request service methods with expected-version and candidate checks. Record a QA request before launch so retries recover one delegation. Memory persistence failures remain retryable without repeating an assessment. | No | — |

Completion: deterministic policy tests cover every state transition; failed preconditions create neither a delegation nor a launch.

### Implementation Phase 2

- **GOAL-002**: Resolve reviewer expertise from immutable project policy. Depends on Phase 1 schema.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-004 | Extend project-context parsing in `src/orbehelm/core.py` and validation in `src/orbehelm/domain/definitions/validation.py` to accept `workflow` in `orbehelm.project.json`. Define `workflow.max_submissions` as an integer 1–100, default 3 for new tasks; define `workflow.reviewer.specialization` as absent/inherit, string/override or null/none. Reject unknown nested fields. Existing task limits change only by explicit operator action. | No | — |
| TASK-005 | After TASK-004, capture workflow policy through existing immutable project context snapshots in `src/orbehelm/product/projects.py`. Freeze developer specialization, effective reviewer specialization and override provenance on submission/delegation. Update `resolve_configuration` callers in `src/orbehelm/delegation_runner.py` to pass the frozen spec. Ensure child identity, context selection and memory audience use the effective reviewer spec. | No | — |
| TASK-006 | Add reviewer specialization JSON/Markdown pairs under `definitions/specializations/reviewer/` for python, php, c and rust, using existing developer pairs as technical subject references while retaining read-only reviewer responsibilities. Do not copy developer mutation or delegation instructions. Validate all four with the existing resolver. | No | — |

Completion: Python developer launches Python reviewer by default; explicit project override and null work; missing spec fails without invoking an adapter. QA specialization remains its existing default; reviewer inheritance does not implicitly change QA policy.

### Implementation Phase 3

- **GOAL-003**: Expose human decisions and manual QA without parallel model orchestration. Depends on Phases 1 and 2.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-007 | Update `src/orbehelm/cli.py` and `src/orbehelm/product/coordination_commands.py` with proposed `tasks approve`, `tasks reject` and `tasks qa` actions. Require explicit candidate, expected version and operation key; approval/rejection also require operator attribution. QA calls the dedicated operator service, not a fabricated developer MCP call. Show resulting state and next action; approval itself must not launch QA. | No | — |
| TASK-008 | In `src/orbehelm/mcp_bridge.py`, remove `parallel` and QA from developer delegation inputs and reject legacy parallel calls with an actionable error. In `src/orbehelm/delegation_runner.py`, replace new parallel scheduling with single-review execution or operator-authorized QA execution; retain recovery/read support for existing delegations. | No | — |
| TASK-009 | After TASK-008, change hardcoded protocol in `src/orbehelm/coordination_runtime.py` and authoritative `definitions/profiles/developer.md`, `reviewer.md`, `qa.md` together. Developer submits and requests reviewer, then reports the pending human step. Reviewer reports structured findings and finishes. QA runs only from the recorded operator request. | No | — |
| TASK-010 | Harden revision validation in `Coordinator.submit_work` and QA dispatch: preserve content hashes and explicit remote revision identifiers, reject known moving refs, verify local materialization before each assessment. Label remote URI/revision references as externally attested unless a deterministic adapter verifies them. Do not infer GitHub/GitLab approval from model prose or claim remote head verification without an implemented adapter. | No | — |

Completion: end-to-end mocked-adapter test executes developer → reviewer → idle → operator approval → idle → operator QA → complete; no hidden model launch occurs at either idle boundary.

### Implementation Phase 4

- **GOAL-004**: Migrate safely, document interfaces and validate packaging. Depends on Phase 3.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-011 | Add migration tests for fresh installs and upgrade from 0006. Preserve completed historical tasks and tag their legacy policy; do not reinterpret them as human-approved. Existing live legacy assessments remain recoverable under their pinned policy; reject new legacy parallel launches and require an explicit reopen/new candidate to adopt the new policy. | No | — |
| TASK-012 | Update `tests/test_coordination.py` and relevant resolver, MCP, CLI, migration and runtime tests with the scenarios in Section 6. Use fake adapters and isolated verification homes, not authenticated model sessions. | No | — |
| TASK-013 | Update `docs/task-orchestration.md`, `docs/operator-guide.md` and configuration documentation with entity identities, new policy fields, proposed CLI actions, attestation limitations, migration behavior and clear submission-budget semantics. Mark superseded parallel behavior in earlier proposal documents as historical. | No | — |
| TASK-014 | After TASK-011 through TASK-013, run `python3 -m unittest discover -s tests -v`, project-configured architectural/package checks and isolated CLI dry runs. Inspect final diff and definition build output. Report exact checks and any unverified external integration. Publication requires the separate authorized release workflow; do not publish as part of this plan. | No | — |

Completion: required checks pass, current documentation matches enforced behavior, and no global configuration or generated runtime was hand-edited.

## 3. Alternatives

- **ALT-001**: Change prompts only. Rejected because broad delegation guards and aggregation would still permit the old behavior.
- **ALT-002**: Keep parallel orchestration as the default and add a human gate afterward. Rejected because QA would run before the requested manual action.
- **ALT-003**: Implement authenticated GitHub/GitLab approval synchronization now. Deferred: local operator attestation meets the requested interface; external approval adapters introduce additional identity, availability and stale-head contracts.

## 4. Dependencies

- **DEP-001**: Existing SQLAlchemy/Alembic persistence, immutable configuration snapshots, artifact integrity checks and native adapter interfaces.
- **DEP-002**: Role-specific specialization definitions must resolve before inheritance can be enabled; no fallback that silently discards expertise.

## 5. Files

- **FILE-001**: Domain policies, coordination service and persistence models/migration identified in TASK-001 through TASK-003.
- **FILE-002**: Project parser, validation, configuration resolution and reviewer definitions identified in TASK-004 through TASK-006.
- **FILE-003**: CLI, MCP, runtime protocol and delegation runner identified in TASK-007 through TASK-010.
- **FILE-004**: Tests and operator documentation identified in Phase 4.

## 6. Testing

- **TEST-001**: Table-driven state guards for positive and negative paths, blocked recovery, duplicate commands, version conflicts and concurrent review/QA requests.
- **TEST-002**: Reviewer completion and human approval each launch zero further processes; agent QA/parallel requests are rejected; manual operator QA launches exactly once after approval.
- **TEST-003**: Changed candidate, source digest or stale reviewer result invalidates approval eligibility; invalid remote references fail; unverified external references are labeled truthfully.
- **TEST-004**: Inherit/override/null/missing reviewer specialization, frozen configuration, distinct child identities and memory audience handling.
- **TEST-005**: Fresh and upgrade migrations, retained legacy results and pending delegation recovery, unchanged submission budgets, idempotent memory persistence retries.
- **TEST-006**: Full required unittest suite plus existing configured architecture/package checks; disposable-home CLI dry runs verify help, configuration errors and operator actions without model authentication.

## 7. Risks & Assumptions

- **RISK-001**: Full-access agents share the operator's OS account. CLI-only approval is an audited convention, not proof of human presence. Strong enforcement requires a separately authenticated boundary and separate approval for that architecture.
- **RISK-002**: Installed older runtimes keep old instructions until upgraded/relaunched. Engine, catalog and runtime protocol must be released compatibly and launch output must identify active policy.
- **RISK-003**: Existing unkeyed task reuse can still combine unrelated work. Expose identity and recommend distinct keys; automatic task creation/completion semantics are a separate proposed change.
- **ASSUMPTION-001**: Human second review is recorded explicitly by an operator CLI action; a remote provider approval integration is not required for this first iteration.
- **ASSUMPTION-002**: A task remains pending after reviewer completion; only the automated developer/reviewer run ends. Overall completion follows manually requested QA pass.

## 8. Related Specifications / Further Reading

- [Entity and workflow analysis](../docs/entities-and-human-review-workflow.md)
- [Existing orchestration documentation](../docs/task-orchestration.md)
- [Original task orchestration plan](feature-task-orchestration-memory-1.md)
- [Persistent workflows plan](feature-persistent-workflows-1.md)
- [Project instructions](../AGENTS.md)

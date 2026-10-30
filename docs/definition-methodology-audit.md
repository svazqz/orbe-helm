# OrbeHelm definition methodology audit

Date: 2026-10-30. Scope: shared base, all five profiles, all four existing developer specializations, authoring guidance and runtime coordination prompt composition.

## Findings and changes

The shared base previously lacked concrete memory and coordination protocols. Developer-only text duplicated memory guidance, while developer, reviewer, QA and runtime instructions explicitly promoted parallel assessments. Nondeveloper profiles inherited no concrete OrbeHelm memory guidance.

The base now describes capability discovery, bound task identity, `read_context`, artifact inspection, concurrency versions, submission budgets, deterministic software boundaries and tool failures. It distinguishes memory `search_memory`/`read_memory`/`save_memory` from coordination `save_knowledge`, including source attribution, evidence state, privacy, project acceptance and idempotent retries. It does not register or enable MCP servers; runtime launch preparation owns the bound integrations.

Developer prompts cover reproducible submission and reviewer handoff. Reviewer prompts require candidate-linked structured results and distinguish agent review from human approval. QA prompts describe the intended manually requested stage and separate standalone assessment from delegated completion. Personal assistant and electronics engineer prompts apply shared evidence practices without implying developer-only tool permissions.

All existing Python, PHP, C and Rust specializations were inspected. They use additive sections for technical expertise without overriding base workflow or coordination permissions, so no specialization changes were needed. Authoring guidance now preserves that separation for future definitions.

The runtime coordination prompt no longer injects automatic parallel assessment instructions after composition. This is a prompt-generation correction; the state machine and public tool schema have not been migrated. The engine still exposes legacy parallel/QA delegation and lacks the proposed human approval and manual QA commands. Prompts explicitly require reporting missing gates rather than inventing support. Runtime enforcement remains work in the [sequential workflow plan](../plan/refactor-human-approved-review-qa-1.md).

## Verification and activation

Portable resolution succeeded for every existing profile and specialization, confirming inherited memory and context guidance. Test evidence is stored in `state/verification/definition-methodology/`; the initial shell-Python run lacked SQLAlchemy/Alembic, so full verification uses the existing project Python 3.13 release environment.

The project-environment full suite passed all 287 tests; the independent kernel suite passed all 24 tests. `git diff --check` passed. These checks validate source composition and existing behavior; they do not establish that model agents will always obey prompts or that the proposed human approval gate is implemented.

No authenticated model sessions, server registration, global configuration updates or generated build edits were performed. Independent coordination assessment is pending because the bound task is complete at its submission cap of five. These changes are working-tree source edits, not a published release or an update to already running sessions. Definitions and the runtime prompt generator must be delivered together.

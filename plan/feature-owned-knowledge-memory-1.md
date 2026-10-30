---
goal: Deliver owned revisioned KUnits with mutable visibility and local hybrid retrieval
version: 1
date_created: 2026-10-30
last_updated: 2026-10-30
owner: OrbeHelm
status: 'Completed'
tags: [memory, knowledge, embeddings, sqlite, privacy, testing]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

Implement the approved October 30 knowledge-memory proposal. This amendment supersedes
the earlier refactor's project-private/released-copy memory model: private units are
owner-only, global visibility preserves identity/ownership, and both reported and
accepted active units are retrievable with their status. The wider independent-core
refactor remains in progress. Implementation/operation details are in
[owned knowledge memory](../docs/knowledge-memory.md).

## 1. Requirements & Constraints

- **REQ-001**: Persist stable KUnit IDs, logical owner, revision history, visibility, state, source evidence, and derivation relationships independently from native agents and transcripts.
- **REQ-002**: Query active global units plus the verified owner's private units. Project membership is not a private-unit grant. Keep history/source references owner-scoped.
- **REQ-003**: A chat launch flag sets the default for future writes. Visibility changes preserve IDs/owner, use expected revisions, invalidate dependent units, and refresh future contexts.
- **REQ-004**: Combine FTS5 keyword and local embedding rankings. Keep vectors and segments rebuildable, model/runtime identities pinned, indexing retryable, and retrieval scope applied before ranking.
- **SEC-001**: Bind tools to opaque expiring/revocable launch credentials. Do not accept owner/operator/visibility overrides from agent payloads. Preserve private provenance across native resumes and exclude private history from fresh global handoffs.
- **CON-001**: Preserve old migrations/source formats/agent login homes/legacy task workflows. Use additive migration 0005 and isolated fixtures. Do not start an authenticated agent session during verification.
- **CON-002**: No mandatory vector server or embedding API. Model download is explicit and anonymous; ordinary inference is local/offline. Declare keyword-only operation and exact-cosine fallback accurately.
- **PAT-001**: Domain owns access/segmentation/fusion rules; application owns workflows; infrastructure owns SQLite/index/model effects; root composition connects CLI/MCP/chat.

## 2. Implementation Steps

### Phase 1 — Canonical knowledge and policies

- **GOAL-001**: Establish ownership and auditable mutable visibility without changing old data semantics.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-001 | Add `product/migrations/versions/0005_knowledge_units.py` and matching infrastructure rows; advance Store/editor readiness to 0005 and preserve migrations 0001–0004. | Yes | 2026-10-30 |
| TASK-002 | Implement `domain/knowledge/retrieval.py`, owner-only access/global visibility, stable-identity visibility transitions, segmentation, and duplicate-aware reciprocal rank fusion; align typed kernel policies/tests with the approved model. | Yes | 2026-10-30 |
| TASK-003 | Implement `infrastructure/memory/sqlite.py` with revisions, source aliases, CAS, access-filtered retrieval, source inheritance, transitive invalidation, capture/index jobs, and canonical authorization independent of projection freshness. Depends on TASK-001 and TASK-002. | Yes | 2026-10-30 |

### Phase 2 — Embeddings and runtime integration

- **GOAL-002**: Run memory through both managed provider integrations without a required daemon.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-004 | Implement `infrastructure/memory/embeddings.py` using explicit anonymous download, cached-only CPU inference, artifact/runtime identity, non-truncating token windows, and pooled vectors. Support sqlite-vec plus declared exact-cosine fallback. Depends on TASK-003. | Yes | 2026-10-30 |
| TASK-005 | Add `application/use_cases/memory.py`, composition in `memory.py`, strict `memory_bridge.py`, runtime-only MCP overlays, and managed-turn capture/retrieval/epoch refresh. Preserve generated artifacts and revoke turn credentials. Depends on TASK-003 and TASK-004. | Yes | 2026-10-30 |
| TASK-006 | Add memory CLI commands/launch visibility, bound history filtering, explicit private legacy import, and installer/update `--memory` support; retain existing task memory commands. Depends on TASK-005. | Yes | 2026-10-30 |

### Phase 3 — Verification and operational documentation

- **GOAL-003**: Verify invariants with deterministic tests and isolated real local inference.

| Task | Description | Completed | Date |
| --- | --- | --- | --- |
| TASK-007 | Add `tests/memory`, pure retrieval tests, kernel coverage, and explicit model/CLI smoke scripts. Verify scope before ranking, visibility races, stale indexing, deduplication, capture recovery, inherited provenance, no global/private history leak, migrations, and real multilingual local inference/stdio MCP. Depends on TASK-006. | Yes | 2026-10-30 |
| TASK-008 | Document setup/configuration, visibility/ownership, migration/recovery, optional dependencies, partial indexing, native permission limits, and remaining larger-refactor work. Run the full unittest/kernel/wheel/smoke checks and record evidence. Depends on TASK-007. | Yes | 2026-10-30 |

## 3. Alternatives

- **ALT-001**: Vector-only authoritative memory was rejected: vectors cannot replace ownership, evidence, revision history, or current authorization.
- **ALT-002**: A mandatory external vector server was rejected for the initial local CLI deployment. Retrieval/embedding ports allow a later backend with measured need.
- **ALT-003**: Re-embedding every unit on a visibility change was rejected. Change canonical policy immediately, refresh affected projections/derivatives, and reuse unchanged vectors.
- **ALT-004**: Automatically treating every assistant statement as verified knowledge was rejected. Automatic observations remain reported; model-based consolidation is not silently invoked.

## 4. Dependencies

- **DEP-001**: Existing SQLAlchemy/Alembic/SQLite runtime, FTS5, Python 3.11+, and pinned sqlite-vec 0.1.9. Exact local cosine remains available when Python disables extension loading.
- **DEP-002**: Optional FastEmbed 0.9.1 and explicitly downloaded public model artifacts. The embedding fingerprint includes inference runtime versions; optional transitive packages remain platform-resolved.

## 5. Files

- **FILE-001**: `domain/knowledge/**`, `application/use_cases/{knowledge,memory}.py`, and memory/repository ports define independent rules and workflow contracts.
- **FILE-002**: `infrastructure/memory/**`, persistence models, migration 0005, Store/editor readiness, and `memory.py` implement canonical/index/model storage and composition.
- **FILE-003**: `managed.py`, `conversations.py`, `memory_runtime.py`, `memory_bridge.py`, `cli.py`, installer/dependency files, and fixture contracts implement runtime/transport integration.
- **FILE-004**: `tests/memory/**`, `tests/domain/test_memory_retrieval.py`, explicit embedding/CLI scripts, documentation, and validation evidence provide regression/operational checks.

## 6. Testing

- **TEST-001**: Full unittest discovery preserves the original regression inventory and covers fresh/upgrade schema parity, no-new-cycles, all owner/visibility combinations, history redaction, same-ID visibility changes, and operator-only mutations.
- **TEST-002**: Kernel execution with `-I -S` blocks file/environment/network/process effects while exercising pure rules and injected-port application workflows.
- **TEST-003**: Real SQLite/FTS/vector tests use deterministic fixture embeddings. Cover keyword-free semantic matches, pre-ranking access, current-revision joins, corruption rebuild, model failures, stale worker/configuration races, and duplicate source evidence.
- **TEST-004**: Managed fake children and actual stdio bridge verify capture state, permissions/bindings, private-context inheritance, context refresh, immutable builds, and CLI parity without agent authentication.
- **TEST-005**: Explicit real-model scripts verify cached local English/Spanish relevance, bounded non-truncated windows, actual CLI visibility/revocation, and stdio MCP. Wheel checks verify independent imports, optional UI, and unchanged historical migration resources.

## 7. Risks & Assumptions

- **RISK-001**: Already delivered content cannot be recalled. API revocation and future-context refresh do not establish host filesystem isolation or erase existing native transcripts.
- **RISK-002**: Exact vector search scales with accessible corpus size. Larger-corpus latency and alternate backend selection require deployment benchmarks.
- **RISK-003**: Observations may be wrong or adversarial. Reported state, provenance, and explicit correction are preserved; similarity does not establish truth.
- **RISK-004**: Native MCP approval behavior is provider/version dependent. Automatic capture/retrieval works outside those calls, but live Claude/Codex integration remains a separate authenticated check.
- **ASSUMPTION-001**: Global means one local installation; cross-computer synchronization is outside this feature.
- **ASSUMPTION-002**: Legacy task/project knowledge remains separate until explicitly imported private/reported. Existing operational data is not reclassified automatically.

## 8. Related Specifications / Further Reading

- [Memory operation and limitations](../docs/knowledge-memory.md)
- [Validation](../docs/validation.md)
- [Independent-core refactor](refactor-independent-core-adapters-1.md)
- [SQLite FTS5](https://www.sqlite.org/fts5.html)
- [sqlite-vec metadata/query behavior](https://alexgarcia.xyz/sqlite-vec/features/vec0.html)
- [FastEmbed](https://github.com/qdrant/fastembed)

## Optional memory amendment — October 30, 2026

Completed launch-level `--memory` / `--no-memory` selection and the `memory` defaults
setting. Native continuity mode skips automatic KUnit retrieval/capture, conversation
body recording, memory tools, and cross-agent handoffs. It preserves exact native
session identifiers across policy changes and materializes current instructions at
a stable path for an explicit user-requested reread. Re-enabling memory starts fresh
without importing the unrecorded period. Validation: 245 full tests, 24 isolated
kernel tests, and wheel smoke verification; no authenticated native model execution.

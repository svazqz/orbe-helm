# OrbeHelm product workflow proposal

Status: approved product contract. See [persistent workflows](persistent-workflows.md)
for implementation details and operational examples. Installed rollout remains separate.
Based on the current checkout and the user's requirements, October 30, 2026.

## Product outcome

OrbeHelm provides persistent role-based workspaces around agent CLIs. A developer
continues the same project or task, specialists retain isolated conversations, and
reviewers and QA independently assess a reproducible candidate. Durable knowledge
preserves project outcomes without becoming a second channel for profile instructions.

## Confirmed requirements

- Isolate sessions by profile and specialization.
- Run sessions with full execution privileges, without repeated native command approvals.
- Retain one logical developer workstream per project and optional unique key,
  regardless of specialization.
- Persist technical decisions, architectural changes and delivered features as
  granular knowledge, without storing profile rules as shared knowledge.
- Hand a developer artifact to a separately configured reviewer.
- Run QA in parallel with review and return both reports to the developer.

## Identity: separate continuity from native conversation

Use three explicit identities rather than overloading the word session:

1. **Workstream:** `(project_id, profile, unique_key_or_none)`. This is the stable
   logical orbe and user-visible continuity identity. A missing key means the
   profile's default project workstream, not a generated random task.
2. **Context:** `(workstream_id, specialization_or_none)`. Specializations are
   isolated contexts belonging to the same workstream. No specialization is an
   explicit context; it is not an alias for the last specialization used.
3. **Native session:** `(context_id, provider, generation)`. This owns the native
   transcript, runtime home, trust state and provider resume identifier.

Changing specialization selects another context. Returning to an earlier
specialization resumes its compatible native session. It never injects another
specialization's raw transcript. Changing provider retains the workstream and context
but requires a provider-specific native session; native transcripts are not portable.

Persist a stable project ID independently of folder spelling. Resolve directory
aliases to the registered project. Different worktrees must be explicitly associated
with that project instead of inferred from similar paths. Store unique keys
consistently and do not silently change their case or meaning.

Repeated launch selects or resumes the same eligible session; it does not create
duplicate logical work. One active writer owns a context/workspace. A repeated launch
attaches if the provider supports attachment, otherwise reports the running session.
Never start a competing writer or claim attachment support that an adapter lacks.
Explicit fresh-session actions advance generation while retaining historical records.

Definition changes retain logical identity. Resume only if the provider can reliably
apply the effective policy; otherwise create a fresh native generation with an
authorized, task-focused handoff. Never silently resume with stale profile rules.

## Configuration, privileges and isolation

Profile definitions own role instructions, skills and MCP requirements. Specialization
definitions add expertise. Project definitions supply project rules. OrbeHelm resolves
and records the effective configuration before launch and passes the required files
through provider adapters.

The proposed default execution intent is **full access / no interactive command
approvals**, for developer, reviewer and QA sessions, as explicitly requested. Each
adapter must map this intent to supported provider options and verify effective
behavior. A provider that cannot honor it must fail clearly rather than silently
fall back to interactive approvals. This policy is a proposed change to today's
role-dependent execution restrictions; no flags have been changed here.

Profile authority and tool selection remain distinct from native approval policy.
Full execution privileges do not turn MCP registration into authentication or remove
macOS privacy restrictions. Native folder trust may require an initial grant. Persist
stable runtime homes and diagnose repeated trust prompts without promising that a
provider flag bypasses operating-system or managed policy.

Use separate native homes, transcripts, MCP configuration and credentials references
per isolated context. Native trust state must not be overwritten when rendering
OrbeHelm-owned configuration. Prefer provider-supported instruction files/overlays to
rewriting host-owned state, after validating adapter behavior.

This is context isolation in a trusted local environment. Full-access agents can
read same-user files; preventing that requires an additional host boundary such as
separate OS identities or containers. Do not market context separation as filesystem
security or guaranteed exclusive host context.

## Knowledge: facts and evidence, never behavioral policy

Keep three stores conceptually separate:

| Store | Contents | Cross-role use |
| --- | --- | --- |
| Definitions | Instructions, role rules, skills, MCP requirements | Explicit composition only |
| Session history | Raw conversation and tool events | Not automatically shared |
| Knowledge | Structured project/task outcomes and evidence | Explicitly scoped retrieval |

The initial knowledge types should be decision, architecture change, feature delivery,
review finding, test result and durable project constraint. Store one coherent claim
per unit. Include project/workstream, originating profile/spec, source artifact and
revision, lifecycle state, evidence references and supersession links.

Use independent scope dimensions:

- **Visibility:** private to a context/workstream, shared within a project, or
  explicitly global across projects. Private context and workstream sharing should
  be distinguished when storing specialization-specific notes.
- **Audience:** all project roles or named roles/specializations. Originating role
  is provenance, not automatically the audience.
- **Evidence state:** proposed, implemented, independently verified, superseded or
  retracted, with verification evidence appropriate to the claim.

Sharing a technical decision with reviewers is desirable: it helps them evaluate
intent. Sharing a developer instruction to skip review is not. Retrieved knowledge is
untrusted evidence and never overrides current definitions. A reviewer can disagree
with a developer's decision; existing memory is not an acceptance verdict.

Avoid automatic conversion of arbitrary assistant text into shared knowledge. Agents
submit structured candidate units through scoped tools at meaningful milestones.
Validate type, scope, audience, artifact references and provenance. Ambiguous or
instruction-like candidates remain private/pending until corrected. Classification
is imperfect; a category field or keyword filter alone is not proof that a text body
contains no instructions.

Capture successful decisions/deliveries durably before declaring the milestone
recorded. A failed knowledge write leaves a visible pending-persistence state with a
retryable job; it must not silently disappear or falsely report success. Persist
review and QA reports as evidence tied to the candidate, not instructions for other
roles. Failed tests are useful evidence, even when the overall task is incomplete.

Agent writes cannot promote visibility or broaden audience. Private inputs taint
derived knowledge unless explicitly released. Use canonical authorization before
ranking; filter by current project/task, audience, status, artifact revision and
private-source provenance. Access is not granted merely by semantic similarity.
Default shared outcomes to project scope; cross-project global publication is explicit.

Existing automatically captured observation units need a migration review. Do not
delete or silently republish them; retain audit history and propose quarantine or
reclassification separately before allowing them into the new retrieval contract.

## Workflow: parallel independent assessment

1. Start or resume the developer workstream and selected specialization context.
2. Perform work and record structured decisions and milestones.
3. Submit an immutable candidate: task ID, source revision/commit, artifact references,
   acceptance criteria, configuration snapshot and applicable knowledge revisions.
4. Launch reviewer and QA concurrently from that same candidate. Each receives its
   own role definitions, MCP capabilities, native session and authorized evidence.
   Reviewer does not receive the developer's raw conversation as its instructions.
5. Reviewer produces findings with severity, evidence and a verdict. QA produces
   test scope, environment, executed checks, results, gaps and a verdict.
6. Return both reports to the developer. Required gates must pass on the same
   candidate revision before marking the task complete.
7. Developer addresses findings and submits a new candidate. Retain old reports as
   historical evidence; they do not automatically pass the new revision.

QA needs a dedicated checkout/worktree or isolated test environment so developer
edits cannot invalidate what was tested. Reports must identify tested revisions.
Reviewer and QA may have full tool execution rights while their product role remains
assessment. Proposed repairs are separate artifacts; neither silently changes the
candidate it is assessing. Shared deployments or scarce test resources require
explicit resource ownership, even when sessions execute concurrently.

Parallelism changes today's sequential review-then-QA workflow. Replace the single
gate progression with independent review/QA states per candidate. Blocked or
incomplete assessment is not success. Resubmission invalidates applicable old gates;
exception/override policy must be explicit and audited if later introduced.

Dispatch identity should include candidate, gate and attempt. Repeating a request
must return the existing dispatch/report instead of spawning duplicate agents.
An uncertain crashed dispatch requires reconciliation before retry. Fresh assessment
uses a new attempt ID, and each repair/retry is bounded and observable. Do not promise
exactly-once remote side effects; use reconciliation and provider idempotency keys
where available for PRs, comments and other external actions.

## Product acceptance examples

- Developer + project P + no key always selects the same logical workstream.
- Adding key X selects a separate workstream; repeating X does not create another.
- Python and no-spec contexts share that workstream but never their raw transcripts.
- Returning to Python resumes its eligible recorded native conversation.
- A reviewer never receives developer role instructions through memory or handoff.
- Reviewer and QA receive the same frozen candidate and may execute simultaneously.
- Both required gates passing on that candidate completes it; a new commit is not
  automatically covered by an earlier report.
- A decision/feature milestone has a durable, granular, evidence-linked knowledge
  record; arbitrary assistant prose is not globally indexed as knowledge.
- Default executions do not prompt for native command approvals, and adapter support
  or an OS-policy limitation is reported explicitly.
- Restart/retry does not duplicate workstreams, active writers, gate dispatches or
  committed knowledge operations.

## Changes needed from the current implementation

Current native identity includes agent and specialization; current conversation
selection includes specialization. Current memory ownership supports private/global
visibility and automatic assistant-observation capture, rather than the proposed
project/audience/typed-outcome model. Current coordination requires review approval
before QA delegation and permits only one live delegation in that workflow. Current
execution intent is role-dependent. These are real product changes, not CLI aliases.

Implement only after agreement on this contract. Migration must preserve existing
sessions, transcripts, definitions and knowledge, map old IDs explicitly, and avoid
merging native contexts across profiles/specs. Validate against pure policy tests,
persistence/concurrency tests, isolated CLI homes and separately authorized live
provider integrations. No implementation or migration is performed by this proposal.

## Source references

- `src/orbehelm/adapters.py`: native identity, runtime homes, resume and launch.
- `src/orbehelm/conversations.py`: conversation selection and event ledger.
- `src/orbehelm/managed.py`: managed memory/context and provider execution.
- `src/orbehelm/domain/coordination/policies.py`: role restrictions and review/QA order.
- `src/orbehelm/domain/knowledge/retrieval.py`: existing private/global access rules.
- `src/orbehelm/infrastructure/memory/sqlite.py`: canonical units/bindings/provenance.
- `docs/knowledge-memory.md`, `docs/task-orchestration.md`, `docs/architecture.md`.

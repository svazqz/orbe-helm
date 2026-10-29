# Task coordination, shared context, and agent communication

Status: Architecture proposal for discussion. No runtime, database, hook, orbe identity, or routing behavior is changed by this document.

Implementation update (October 29, 2026): the initial task-specific parent/child
workflow is implemented. See [current behavior and limits](task-orchestration.md).
Shared pools, inbox delivery, hooks, and automatic triggers below remain future design.

## Objective

Support several concurrent development tasks in one project, each with stable role orbes and native conversation continuity. Reviewer and QA orbes must receive the evidence needed to assess a particular submitted revision. Findings must return to the responsible developer, and subsequent fixes must be reviewed against the correct revision. Future automation should control routing and workflow in software while keeping model judgment and native tool approvals explicit.

## Current state and gap

OrbeHelm currently composes role instructions, skills, and MCP definitions, pins configuration releases to projects, manages native runtime homes, and records resumable native conversations and launch metadata. Its SQL database contains configuration/orbe metadata rather than task records or conversation bodies.

The current native conversation identity is `(canonical project, agent, profile, specialization)`. A slot lock prevents concurrent launches of that same identity. Two developer orbes for the same project/profile/specialization/native agent therefore cannot independently handle two tasks today. `--new-orbe` rotates the slot's active orbe; it does not create a second concurrent task slot. The proposed `--unique-key` does not exist yet.

There is no durable task inbox, task-level shared context, explicit cross-orbe request/result record, graph of communication links, or supported mechanism to deliver work into a running agent. The launcher currently runs a native CLI through `subprocess.call` and resumes its history on subsequent launches. Changing that execution model needs an explicit adapter design, not merely a pub/sub flag.

## Recommended domain model

| Entity | Identity and purpose |
| --- | --- |
| Project | Stable OrbeHelm project ID and selected configuration; shared accepted knowledge |
| Work item | Project-scoped task ID/key, requirements, acceptance criteria, state, and ownership; external Jira identity is optional |
| Workspace | Working copy associated with a project/task; records branch/worktree information when Git is available |
| Logical role orbe | Stable `(project_id, profile, specialization, unique_key)` identity, independent of native agent choice |
| Native conversation | Agent-specific conversation/history associated with a logical role orbe; Codex and Claude histories remain separate |
| Launch/turn | Concrete runtime execution with observed status and native identifiers where available |
| Change set | Immutable submitted candidate revision and its owning developer/task |
| Context revision | Versioned bundle of task facts, decisions, artifact references, and relevant project knowledge |
| Event | Durable fact with producer, task, sequence, and causality identifiers |
| Request | Directed action assigned to a specific logical orbe and candidate/context revision |
| Delivery | Per-recipient inbox record, acknowledgement, attempt, and claim state |
| Link | Project-scoped routing grant/filter connecting logical orbes |

`--unique-key` should identify a role orbe; it should not be the only representation of task identity. The UI or task-creation command must record an explicit work-item association. Reusing a Jira key as the suggested unique key is convenient, but does not replace that association. A developer key such as `APP-123/backend` and another key `APP-123/frontend` can belong to one work item. A shared reviewer can serve many work items through directed requests that always carry a task ID.

Keep native runtime identity separate from logical identity. A provider switch can retain task memory and links while using its own native conversation. Do not merge existing native histories or reuse incompatible runtime files. Migration must preserve existing UUIDs and default-orbe behavior.

Task identity and workspace identity also differ. Two agents editing one working directory can overwrite each other even when their conversations are independent. Prefer separate task worktrees/branches when supported, or explicitly managed isolated working copies. The current product keys projects by canonical directory, so associating several working copies with one logical project requires a workspace association rather than treating every worktree as a new project by accident. No automatic worktree creation or commits are proposed as an implicit side effect.

## Intercommunication

### Local coordination service

Use shared OrbeHelm application services with the existing SQLite store as the initial persistence layer. CLI commands, hook helpers, the web UI, and an OrbeHelm-owned MCP bridge should call those same services. A separate Redis/Kafka broker or vector database is not required for the first version.

A local API/socket can provide notifications and later runner integration. Database-backed inboxes remain authoritative across service restarts; a socket notification is a hint that a record is available. Avoid holding database transactions while invoking models, waiting for another agent, running tests, or waiting for a provider callback.

The proposed tool surface should cover reading a task/context bundle, submitting a handoff, inspecting an inbox, claiming a request, reporting findings/results, and acknowledging a context delivery. Exact command and MCP tool names require interface design; they do not exist today.

### Events, requests, and process signals

- A lifecycle observation reports that a runtime started, became idle, was interrupted, or exited. It does not certify task completion.
- A domain event records a fact such as a candidate being submitted, a review result being recorded, or a finding being opened.
- A request asks one identified recipient to perform an action and expects a result.
- An OS signal is for process interruption/termination. It does not carry task context or substitute for a durable request.

`turn.completed`, `process.exited`, and `orbe.idle` must remain separate from `work.submitted`, `review.passed`, and `task.completed`. A developer explicitly submits a handoff; a runtime Stop hook cannot infer the acceptance criteria were satisfied.

### Request and reply correlation

Each request should include at least:

- Request ID, work-item/project IDs, type, and schema version.
- Creator and requesting logical orbe, exact recipient logical orbe, and owning developer orbe.
- Immutable change-set/candidate revision and context revision references.
- Parent/root request IDs and triggering event ID for causality.
- Expected workflow version, status, and idempotency key.

A reviewer or QA result refers to the original request. OrbeHelm uses its recorded origin and change-set owner to route feedback. It must not broadcast to every developer or guess an owner from the profile name.

For coordinator-created QA requests, the requesting actor may be the coordinator, while the responsible developer remains the owner of the submitted change set. Preserve both fields. An independently discovered issue with no reliable owning task/change set becomes an unassigned project finding for triage; ambiguous ownership is not silently inferred.

### Delivery semantics and recovery

Persist domain state, events, and recipient deliveries transactionally. Assign a monotonic sequence within a work item; timestamps are for display, not causal ordering. Store per-recipient delivery records so reviewers and QA can independently receive the same informational event.

Use at-least-once delivery with duplicate detection and idempotent state transitions. Distinguish transport acknowledgement, model-visible context consumption, request claim, and semantic completion. Acknowledging a message does not mean the requested work passed.

A claim needs an expiry/lease and recorded attempt. Expiry does not prove that a previous model turn or external action stopped. Reconcile with the native runner before retrying an uncertain dispatch; otherwise mark it for manual recovery. Software cannot promise exactly-once model execution or external side effects merely because inbox records are idempotent.

Offline recipients retain queued work. Busy recipients serialize requests unless their adapter explicitly supports another safe behavior. Cancellation records state; it does not equate to revoking already-created external effects. Preserve audit history.

### Hooks and adapter capabilities

Use hooks as scoped runtime bridges: register native identity/presence, report interruptions or turn boundaries, and offer concise pending context at supported boundaries. Generate integration configuration inside OrbeHelm-owned runtime homes; do not modify global agent configuration. Keep hooks short, bounded, and tolerant of service unavailability. A startup hook must not depend on an MCP server already being ready.

Hooks are host/version-specific. Each adapter should advertise separately whether it can observe lifecycle, deliver context at a safe boundary, start a turn, resume a conversation, correlate a native turn, and cancel work. Enqueueing a request is available independently of waking a model.

Official OpenAI documentation states that Codex background-hook output arriving while idle waits for a later user turn; it does not itself wake the conversation. Codex App Server offers structured thread/turn operations, but adopting it would be a separate runner integration rather than a behavior the current CLI wrapper already has. Claude documents lifecycle hooks, including OrbeStart and Stop. OpenCode documents plugin orbe events. These sources establish extension points, not compatibility guarantees for OrbeHelm's installed adapters.

Herdr's documented integrations report native conversation identity over a local socket. Its automation API can submit prompts and observe runtime state, but the documentation notes that a wait can be satisfied by the current active turn rather than an individually tracked requested turn. Treat it as a possible terminal/runtime transport, not the authority for task completion or reviewed evidence. The original Herdr commit mentioned in conversation was not inspected; this comparison uses published documentation.

## Memory and shared context

### Separate stores with different meanings

| Memory | Content and authority |
| --- | --- |
| native conversation history | Runner-owned conversation continuity; useful for the developer's later fixes |
| Task memory | Requirements, acceptance criteria, ownership, decisions, open findings, and current submitted revision |
| Evidence/artifacts | Immutable handoffs, patches/manifests, test runs, screenshots, review results, and QA reports |
| Project knowledge | Accepted architectural/domain facts and decisions shared across tasks, with source and author |

Profile definitions remain the source of role instructions and permissions. Shared memory is contextual data; a handoff cannot override those definitions or native tool approvals.

Do not use one mutable `memory.md` as the only shared authority. Store typed records and immutable artifacts, then generate readable Markdown/context views from them. Summaries and future retrieval indexes are derived aids and must retain links to source records. Agents can propose project knowledge; promotion to accepted project-wide knowledge needs an explicit rule. Conflicting changes use version checks rather than silently replacing each other.

Begin with task IDs, structured filters, artifact references, and ordinary search. Add semantic retrieval only if observed scale or lookup quality calls for it. Embeddings would be an index, not the authoritative record.

### Developer handoff

A submitted handoff should include:

1. Task requirement revision and acceptance criteria addressed.
2. Candidate revision/change-set ID and ownership.
3. A concise description of the change and material design decisions.
4. Evidence links: changed files/diff, tests and their actual results, screenshots, and known limitations.
5. Unresolved questions, migrations/configuration implications, and requested reviewer/QA actions.

Record whether a claim is agent-reported or independently observed by an OrbeHelm-controlled runner. A statement that tests passed is not automatically a verified test execution.

When Git is present, record base/head commit references, workspace/branch, and any dirty/untracked candidate content. A branch name or commit alone is insufficient if the tested working tree differs from it. Without Git, capture a bounded immutable file/patch manifest. Review/QA must inspect the submitted candidate, not whichever files happen to be current when they run.

### Reviewer and QA context

Before acting, build a bounded task-specific context bundle containing the relevant project knowledge, requirement revision, submitted change set, developer handoff, prior findings, and the requested action. Fetch larger evidence by reference. The reviewer validates claims against the actual code and acceptance criteria; QA assesses the specified candidate and environment.

Record which context revision was actually delivered to each native turn. Memory written to disk is not automatically loaded into an already-running model. A resume/start/prompt boundary or explicit OrbeHelm tool call must make it model-visible. Pending feedback should be visible in the UI even when the developer is offline.

Every review/QA result is tied to a candidate revision. A new developer revision requires new or explicitly scoped revalidation; earlier approval must not silently approve changed code. Task memory adds the new feedback and fix revision, while each developer keeps its native conversation continuity. Shared knowledge provides recovery if native history is compacted, reset, lost, or the provider changes.

## Pub/sub and visual routing

### Use profile names as templates, logical orbes as addresses

A role such as `developer` describes behavior. It does not identify which developer owns `APP-123`. Connect logical role orbes or explicit task participants, not broad profile names as the final address.

A link stores source/target logical IDs, project/task scope, allowed request/event types, enabled state, and a routing version. The UI graph edits those records; CLI and UI must share the same validation and persistence. A simple connection table is enough initially; an n8n-style canvas can render the same model later.

A profile can supply suggested default links/capabilities. Those templates must resolve to actual participants before work is dispatched. `--pub` and `--sub` could later be convenience syntax for creating links, but they are unnecessary as the primary model and should not be required now.

### Events fan out; requests have an owner

An informational `work.submitted` event can be delivered to both linked reviewer and QA inboxes. A `review.requested` action should name one assigned reviewer orbe or a deliberately configured assignment policy. Do not make all subscribers execute the same command by default.

Replies are authorized and correlated through the original request. The reviewer need not rediscover which developer to notify, and changing a graph must not silently retarget an in-flight request. Cross-task access and allowed request types are validated by application code, separately from prompt instructions. These controls govern OrbeHelm services; they are not a sandbox against other processes running as the same OS user.

For links created after a developer already submitted work, offer an explicit **Send latest handoff** action for the selected task/revision. Do not replay all historical events or auto-start models just because an edge is drawn. Link removal stops future routing; cancellation or draining of outstanding requests must be explicit.

### One or many reviewer/QA orbes

Start with one role orbe per task where practical. This keeps native conversation context focused. A project-wide reviewer or QA worker can serve multiple tasks later, but each request must carry task/candidate/context IDs and be claimed separately. Sharing one native conversation across tasks can retain unrelated context, so it is not equivalent to strict task isolation.

### Deterministic workflow control

Keep notification routing, permission to request work, and permission to start model execution separate. Initial links permit durable handoffs and manual request delivery, not automatic recursive agent activation.

Later rules can make a submitted candidate eligible for review, make a reviewed candidate eligible for QA, and return findings to its owner. Whether review and QA run in parallel or sequentially is a workflow policy rather than a consequence of drawing an edge.

Future automation should require an allowed transition, matching task/candidate revision, an eligible recipient, and a deduplication key. Bound attempts, model budget, concurrent work, and repeated failures. Log why each action was triggered. A reviewer/QA feedback cycle can be legitimate; suppressing duplicate transitions for an unchanged revision is more useful than forbidding all graph cycles. A failure or ambiguous outcome can require human triage.

The deterministic promise is about identity, recorded evidence, routing, state transitions, and recovery. Model reasoning, code correctness, and external side effects remain subject to verification.

## Example: two development tasks and shared reviewer/QA

- Developer A owns work item `APP-123`; Developer B owns `APP-124`.
- Each submits a different immutable change set and handoff.
- Both may link to the same reviewer and QA logical orbes.
- A request for `APP-123` records Developer A as the change-set owner, even if a coordinator created the request.
- QA findings for that request are attached to `APP-123` and routed to Developer A's inbox.
- Developer A resumes its own native conversation, receives the new context delta, and submits a new candidate revision.
- Developer B's state, context bundle, and candidate remain unaffected.
- An unrelated finding without a task/change-set owner goes to project triage rather than being broadcast to both developers.

## Suggested delivery order

1. Add work items, task/workspace associations, and logical identity with `--unique-key`, preserving existing native histories and slot locks.
2. Add immutable handoffs/context revisions and a durable per-orbe inbox, with explicit directed requests/results. Manual delivery and trigger only.
3. Add task/participant links through CLI and a simple project UI, including latest-handoff bootstrapping and visible routing/usage.
4. Add scoped native hooks and tested adapter capability reporting for safe context delivery. An optional runtime transport integration, including Herdr or native structured APIs, should be evaluated separately.
5. Add controlled automatic scheduling only after retries, uncertain delivery, revision validity, and feedback routing are demonstrated with fake and real adapter tests.

The first useful milestone is a persisted developer handoff consumed by a reviewer, a correlated reviewer finding delivered to the developer, and a fix revision re-reviewed without losing task ownership or contaminating another task. A complete graphical workflow engine is not required to prove that loop.

## Decisions to settle before implementation

- Exact task-to-unique-key association and support for several developers on one work item.
- Per-task reviewer/QA orbes initially versus shared worker orbes.
- Workspace ownership and candidate snapshot strategy for Git and non-Git projects.
- Which operations are notification-only, manually executable, or eligible for later automation.
- Supported native runner APIs and explicit fallback behavior when live context injection or turn startup is unavailable.
- Who can accept project-wide knowledge and resolve competing findings/decisions.

## References

Current OrbeHelm evidence:

- [Orbe identity and native launcher](../src/orbehelm/adapters.py)
- [Orbe records and locks](../src/orbehelm/product/orbes.py)
- [Current persistent models](../src/orbehelm/product/models.py)
- [CLI flags](../src/orbehelm/cli.py)
- [Current architecture](architecture.md)

External primary documentation checked during this proposal:

- [Herdr integrations](https://herdr.dev/docs/integrations/)
- [Herdr agent automation](https://herdr.dev/docs/agent-automation/)
- [Herdr socket API](https://herdr.dev/docs/socket-api/)
- [Official OpenAI documentation: Codex hooks](https://learn.chatgpt.com/docs/hooks)
- [Official OpenAI documentation: Codex App Server](https://learn.chatgpt.com/docs/app-server)
- [Claude Code hooks](https://code.claude.com/docs/en/hooks)
- [OpenCode plugins/events](https://opencode.ai/docs/plugins/)

# Task orchestration and memory

OrbeHelm owns task identity, candidate snapshots, delegation records and state
transitions. Candidate submissions are unlimited. The submission count is historical
information, not a retry allowance. Existing database `max_rounds` values are retained
for compatibility but ignored; context reports `submission_limit: null` and
`max_rounds: null`. No migration or operator limit increase is necessary.

## Workflow

1. The owner developer reads `read_context` and submits explicit source paths,
   acceptance criteria and a handoff through `submit_work`. Remote references require
   credential-free URLs and pinned revisions. A URL alone is not remote verification.
2. The developer requests `delegate` with `profile: reviewer`, a stable request key,
   instructions and the current task version. A new key requests a fresh review of
   the current candidate; repeating the same key returns the saved request/result.
3. The reviewer returns `approved`, `changes_requested` or `blocked` through
   `complete_delegation`. The runner checks protocol completion, process exit and
   input integrity. Approval moves the task to `awaiting_human_approval` and ends the
   automated run. It never launches QA. Changes requested return to `developing`.
4. A human performs second review and records `tasks approve` or `tasks reject`
   from an operator terminal. Approval leaves the task idle in `approved_for_qa`;
   rejection returns it to `developing`. Approval records the exact candidate,
   source digest, reviewer result, operator attribution and summary as an immutable
   artifact plus a task event.
5. Only an explicit operator `tasks qa` command launches QA for that approved
   candidate. A QA pass completes the task; failure returns it to development.
   A new candidate or fresh reviewer result requires fresh human approval.

The developer/reviewer flow is finished at the human handoff; overall task state
remains pending for subsequent operator actions. Release publication is separate.
There is no lifetime submission cap and no automatic review or QA polling loop.
Developer tests remain part of implementation and do not require a QA delegation.

## MCP tools

| Tool | Purpose |
| --- | --- |
| `read_context` | Task state/version, unlimited submission count, candidate, next action, knowledge and delegations |
| `read_artifact` | Verified artifact evidence |
| `save_knowledge` | Versioned task knowledge or a project proposal requiring operator acceptance |
| `submit_work` | Root developer publishes explicit immutable candidate scope |
| `delegate` | Root developer requests reviewer only; QA and parallel values are rejected |
| `complete_delegation` | Bound reviewer/QA child stages its result |
| `reopen_task` | Root developer explicitly reopens an idle reviewed, blocked or completed task |

The runtime adds the reserved coordination MCP server `orbehelm` without editing
portable builds or global agent settings. Human approval/rejection and QA launch
are not agent MCP tools. Child participants cannot submit or recursively delegate.
Only one assessment may be active per task. Changed source requires a new candidate;
submissions cannot replace a candidate while an assessment is active.

## Operator CLI

Use the installation that owns the task. Commands return JSON:

```sh
oh tasks list --project=/path/to/project
oh tasks context --project=/path/to/project --actor=LOGICAL_ORBE_ID
```

For `tasks approve`, supply `--data-file=approval.json` containing:

```json
{
  "candidate_id": "CANDIDATE_ID_FROM_CONTEXT",
  "expected_version": 12,
  "key": "human-review-1",
  "operator": "your-name",
  "summary": "Reviewed this exact candidate and approve it."
}
```

The ID and version are illustrative: use the values from current context.
`tasks reject` uses the same schema with a rejection summary. Run:

```sh
oh tasks approve --project=/path/to/project --actor=LOGICAL_ORBE_ID --data-file=approval.json
```

Read context again. To launch QA manually, create `qa.json`:

```json
{
  "candidate_id": "CANDIDATE_ID_FROM_CONTEXT",
  "expected_version": 13,
  "key": "manual-qa-1",
  "instructions": "Test the approved candidate against its acceptance criteria."
}
```

Then explicitly start the selected native provider:

```sh
oh tasks qa --project=/path/to/project --actor=LOGICAL_ORBE_ID --agent=codex --data-file=qa.json
```

QA execution is synchronous, may start an authenticated model, and is not a dry run.
`--dry-run` is rejected for task actions. Decision/request keys are idempotent;
changing payload requires a new key. Stale versions and candidates are rejected.
Operator actions reject an inherited agent or memory binding. This is a trusted
same-user operator attestation, not a hardened human-identity security boundary;
an agent with unrestricted OS access is not isolated from the user's account.

## Recovery and upgrade

Failed, cancelled or interrupted executions block the task. Inspect native processes
before `tasks recover --delegation=ID`; uncertain dispatch additionally requires
`--confirm-stopped`. Recovery never kills recorded PIDs or reruns a model by itself.
Use `tasks reopen --expected-version=VERSION` when needed. There is no `--round-limit`.
New candidates can also replace idle reviewed or completed candidates without a
budget reset; prior artifacts and assessments remain available as history.

Existing completed tasks remain historical completed tasks. A new review can be
requested on demand, or a new candidate submitted, regardless of old submission
counts. Old review/QA results are not silently promoted to human approval. Old
queued QA requests without an approval receipt cannot be launched by the new
operator command; inspect and recover them before submitting a fresh candidate.
Finish active sessions before updating, then relaunch to load new tools and prompts.

## Evidence and isolation

Task artifacts and materialized assessment workspaces remain under the installation's
`state/projects/` directory. Memory is evidence, not instructions. Completed reports
are durable outbox receipts; failed knowledge persistence is retried without rerunning
the model. Project knowledge proposals require operator acceptance.

Sources are copied without an implicit Git repository, unsubmitted dependencies or
credentials. Include needed files explicitly. The runner verifies input integrity,
not the truth of every agent claim. Full-access native processes and shared resources
are not a same-user filesystem sandbox. Strict exclusive isolation is unsupported.
Deterministic tests use disposable stores and fake providers; they are not live
model-authentication or external human-approval integration tests.

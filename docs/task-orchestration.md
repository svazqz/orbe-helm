# Task orchestration and memory

OrbeHelm owns the task identity, persisted context, delegation records, and workflow
transitions. The native agent owns its conversation and tool approvals. This first
implementation supports an explicit developer → reviewer → developer → QA →
developer workflow through an OrbeHelm stdio MCP server.

## Start a keyed task

For an installed application, run `oh server start` in one terminal and launch
`oh run --project=/path/to/project --unique-key=APP-123` in another. Setup already
initializes the application database. Both root and child launches require the
matching healthy server. See [Installation](installation.md).

For direct checkout use:

Activate the checkout's Python environment, stop the old web process, and explicitly
upgrade the database before using this version:

```sh
source .venv/bin/activate
./oh migrate
./oh server start
```

Migration `0002` preserves existing orbe IDs, slot keys, launch records, and
configuration history. `migrate` backs up an existing database under
`state/backups/`. Downgrade requires restoring a backup; there is no destructive
history-removal migration. Existing databases require this migration even for
unkeyed product operations. No real database is migrated by installing the code.

```sh
./oh run --project=/path/to/project --agent=codex \
  --profile=developer --spec=python --unique-key=APP-123 \
  --prompt='Implement APP-123, then use OrbeHelm reviewer and QA delegation.'
```

Normal launches register the project automatically; read-only dry runs require prior registration. A task is identified by the project and
unique key. Its logical role orbes exclude the provider; native conversation
slots and runtime homes retain the provider. Switching provider shares task memory
and ownership, but does not transfer native conversation history. Omitting the key
retains the legacy native identity and does not enable orchestration.

For concurrent developers, prepare separate working copies and pass an existing
directory with `--workspace=/path/to/task-worktree`. Project configuration continues
to come from `--project`. A task's workspace is fixed on first launch. OrbeHelm rejects
simultaneous keyed developer launches against the same canonical workspace. It does
not create worktrees or isolate other processes or legacy unkeyed orbes.

Child keys derive from the root task key, parent logical orbe, role, and delegation
key. Different tasks cannot collide in one reviewer. `ORBEHELM_UNIQUE_KEY` carries
the root key; `ORBEHELM_ORBE_KEY` carries the derived native slot key. Each new
candidate runs a fresh child native conversation; the developer can retain its own
native conversation across fixes. This feature does not install native subagent plugins.

## Deterministic workflow

The keyed runtime adds the reserved MCP server `oh` without editing the
portable generated build or global agent configuration. Its tools are:

| Tool | Purpose |
| --- | --- |
| `read_context` | Current task version, candidate handoff, memory references, delegation statuses, recent events |
| `read_artifact` | Verified structured record for an accessible artifact |
| `save_knowledge` | Versioned task knowledge or a project knowledge proposal |
| `submit_work` | Owner developer submits explicit files, requirements, and handoff |
| `delegate` | Owner developer starts reviewer, then QA after approved review |
| `complete_delegation` | Bound child stages a typed result for its candidate |
| `reopen_task` | Owner developer explicitly reopens a blocked/completed task |

1. The developer reads context and calls `submit_work` with `paths`, `requirements`,
   `handoff`, a stable `submission_key`, and the current task `expected_version`.
   Include the complete source/test scope needed by the children. Root-directory
   submissions, hidden files, symlinks, traversal, and generated/runtime state are
   rejected. Files are bounded individually and in aggregate. Never submit
   credentials; source capture does not scan arbitrary file content for secrets.
2. Submission captures immutable source bytes and the project's configuration ID.
   State becomes `awaiting_review`. A repeated submission key must identify identical
   content. Files changed later in the developer workspace do not alter the candidate.
3. `delegate` takes `profile: "reviewer"`, a stable `key`, `instructions`, and the
   current task version. It records a request, freezes memory references, prepares
   a separate working copy, and runs the selected native CLI synchronously.
4. The reviewer must call `complete_delegation` with `approved`, `changes_requested`,
   or `blocked`, plus `summary`, `findings`, and task artifact IDs in `evidence`.
   Only successful native exit with unchanged submitted inputs promotes the result.
   An approval moves the task to `reviewed`; changes return it to `developing`.
5. The developer can then delegate `qa`. QA reports `passed`, `failed`, or `blocked`.
   Passing completes the task; failure returns it to development. Every fix requires
   a new candidate and fresh review before QA.

Delegation results return to their recorded parent. Repeating a delegation key for
the same parent, role, and candidate returns its recorded state/result without
duplicating a claimed run. Child roles cannot submit work or delegate recursively.
There are three submission rounds by default. A native child has a five-minute
execution timeout; cancellation/timeout/failure blocks the task. Native approval
prompts are never bypassed. Unattended child runs can consequently fail or block on
permissions and require operator attention.

The runner verifies protocol completion, native exit, and submitted input integrity.
It does **not** independently certify an agent's assertion that tests passed. QA can
create test output, but it must not modify submitted files. Submitted sources are
copied without a Git repository, unsubmitted dependencies, or credentials. Include
necessary ordinary files explicitly; tests depending on missing environment setup
must report that limitation.

## Durable memory and artifacts

The SQLite database stores task state, logical orbes, versioned knowledge,
delegations, and monotonically sequenced task events. Content-addressed artifacts
are written before database references are committed:

```text
state/projects/<project-id>/tasks/<task-id>/artifacts/<content-hash>/
  record.json
  files/                 # submitted candidate files, when applicable
state/projects/<project-id>/tasks/<task-id>/workspaces/<delegation-id>/
state/projects/<project-id>/knowledge/<content-hash>/record.json
state/orbes/<native-orbe-id>/   # provider runtime and native history
```

Knowledge artifacts therefore survive replacement of native conversations. Task memory
is task-scoped. Project proposals remain private to their originating task until
explicit operator acceptance. Replacing accepted project knowledge requires the ID
of the fact being replaced. Children retain the knowledge versions frozen at
delegation time. Memory is contextual data; profile definitions and host permissions
remain authoritative. Do not hand-edit the database or generated artifact files.

## Inspection and operator recovery

The project UI has a **Tasks** tab with task state, handoff, knowledge links, child
results, and recent events. These pages are read-only and never start a model.

```sh
./oh tasks list --project=/path/to/project
./oh tasks context --project=/path/to/project --actor=<logical-orbe-id>
./oh memory accept <knowledge-id> --project=/path/to/project
./oh memory accept <new-id> --replace-id=<accepted-id> --project=/path/to/project
```

Operator `tasks submit`, `tasks delegate`, `memory save`, and `memory read` accept
the corresponding tool arguments as JSON through `--data-file=<path>` or
`--data-file=-`, together with `--project` and `--actor`. Delegate also accepts
`--agent`; this is an explicit model-execution action.

Interrupted dispatches are never retried automatically. Inspect the old native
processes and recorded state first:

```sh
./oh tasks recover --project=/path/to/project --actor=<parent-id> \
  --delegation=<delegation-id>
./oh tasks reopen --project=/path/to/project --actor=<parent-id> \
  --expected-version=<current-version>
```

Recovery refuses while recorded worker/child processes appear alive. An uncertain
dispatch with no recorded child PID additionally requires `--confirm-stopped` after
operator verification. Recovery records interruption and blocks the task; it does
not kill persisted PIDs or start another model. After recovery, reopen and submit a
new candidate. Operators can explicitly increase the submission cap when reopening
using `--round-limit=<limit>` (at most 100). Old records remain available.

## Integration limits

The bridge implements newline-delimited stdio JSON-RPC, initialization, tool
discovery/calls, cancellation, and ping, negotiating MCP versions 2024-11-05,
2025-03-26, 2025-06-18, and 2025-11-25. It is a scoped tools server, not a complete
implementation of every optional MCP capability. There is no background broker,
shared reviewer pool, automatic trigger, cross-machine scheduler, or semantic index.

Automated tests use disposable homes, real bridge subprocesses, and fake native
executables. They do not validate authenticated Codex, Claude, or OpenCode orbes.
Native instructions, configuration merging, sandboxing, and permissions vary by
provider; OrbeHelm does not guarantee exclusive isolation. The local bridge assumes
a trusted same-user environment and is not a security boundary against agents with
direct filesystem access.

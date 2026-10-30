# Persistent workstreams and independent assessment

Schema `0006` implements the approved product contract. Identity is layered:

| Identity | Key | Continuity |
| --- | --- | --- |
| Workstream | Registered project + profile + optional unique key | Stable logical work |
| Context | Workstream + specialization, including no specialization | Isolated role/spec history |
| Native session | Context + provider + generation | Provider-specific resume and home |

Specialization/provider changes do not create another logical task owner and never
merge native transcripts. Native and managed interfaces retain distinct runtime
bindings; crossing interfaces does not promise exact native resume. Managed provider
switching can resume an existing compatible session for that provider.

## Start and resume

```sh
oh --profile=developer --project=/path/to/project
oh --profile=developer --spec=python --project=/path/to/project
oh --profile=developer --spec=python --unique-key=APP-42 --project=/path/to/project
oh chat --profile=developer --spec=python --unique-key=APP-42 --project=/path/to/project
```

The first two commands select different contexts within the default developer
workstream. The third selects APP-42. Returning to a compatible context/provider
resumes its recorded session. Changed effective rules, knowledge epoch or visibility
can require a fresh generation. `--new-session` explicitly starts a generation.
Records and `oh orbes list` expose `workstream_id` and `context_id`.

All developer launches, including the unkeyed default, acquire a workspace writer
lock. Competing writers fail clearly; automatic attachment is not implemented.
Default unkeyed memory-enabled sessions now have a logical coordination actor too.

Native, managed and delegated launches request full privileges: Codex uses
`--dangerously-bypass-approvals-and-sandbox`, Claude uses
`--dangerously-skip-permissions`, and the legacy OpenCode renderer sets
`permission: "allow"`, following its [official configuration](https://opencode.ai/docs/permissions/).
OS permissions, managed policy and initial native folder trust can still apply.
Codex project-trust TOML sections survive generated configuration refreshes.
This prevents wrapper-induced resets; live trust persistence is separately verified.
Full-access same-user agents do not have filesystem security isolation or guaranteed
exclusive host context.

Persistent native launches currently support Codex and Claude. OpenCode cannot yet
verify recorded native-session resume, so persistent launches fail clearly rather than
silently starting a new conversation. Its renderer and one-shot delegation remain
available, with scoped memory overlays and explicit permission configuration.

## Typed knowledge

Definitions supply behavior; conversation history supplies an audit trail; knowledge
supplies granular technical outcomes. Arbitrary replies are no longer automatically
converted into KUnits. Agent writes require a stable source ID, type and 1–20
artifact/revision evidence references. Supported types are `decision`, `architecture`,
`feature`, `review`, `test` and `constraint`.

- Visibility: private to the owning conversation context, shared within a project,
  or explicitly global across projects in this installation.
- Audience: `*`, named profiles, or `profile:spec` entries.
- Evidence state: `proposed`, `implemented`, or `verified`. Developer bindings cannot
  self-declare independent verification. References are provenance, not proof that
  a remote system was checked.

New owners retain a private default. Select project visibility for shared outcomes;
the setting is retained for subsequent launches of that context:

```sh
oh --profile=developer --spec=python --project=/path/to/project --memory-visibility=project
oh chat --profile=developer --project=/path/to/project --memory-visibility=project
```

Example `save_memory` payload:

```json
{
  "content": "SQLite was selected for local canonical persistence because the application is single-host.",
  "source_id": "APP-42:storage-decision:1",
  "kind": "decision",
  "evidence": ["git:COMMIT_SHA:docs/storage-decision.md"],
  "audience": ["*"],
  "evidence_state": "implemented"
}
```

Operator CLI writes accept the same metadata:

```sh
oh memory put --project=/path/to/project --thread=CONVERSATION_ID \
  --from-file=./decision.txt --source-id=APP-42:storage-decision:1 \
  --kind=decision --evidence=git:COMMIT_SHA:docs/storage-decision.md \
  --memory-visibility=project --evidence-state=implemented
```

Native Codex/Claude and managed chat receive scoped tools. Bindings are revoked and
credential files removed at process/turn end. Payloads cannot select another owner
or change visibility. Native resume inherits private-read provenance. Authorization
and audience filtering precede ranking/direct reads. Private inputs force private
derived output; project inputs cannot become global by default. Role-restricted
inputs cannot be laundered into broadly shared summaries. Shared handoffs omit
private/unclassified conversation bodies.

Memory is untrusted evidence under current definitions. Instruction-like units are
conservatively quarantined as private/pending, available to explicit owner audit and
correction/retraction. This is not an infallible instruction detector. Content
corrections reset evidence state. Existing unclassified units retain IDs, content,
visibility and history but are excluded from new agent bindings. Explicitly create a
typed, scoped copy to reuse suitable historical content. Legacy task knowledge also
requires typed metadata before automatic cross-role handoff.

## Reviewer, human review and manual QA

Candidate submissions have no lifetime limit. Developer `submit_work` captures
explicit source scope, acceptance criteria and a handoff. Remote references require
pinned revisions and must be independently verified through available service tools.

`delegate` accepts `profile: reviewer` only. Reviewer approval stops the automated
flow in `awaiting_human_approval`. An operator records human second review with
`tasks approve` or `tasks reject`. Approval starts no model; only a later explicit
operator `tasks qa` command launches QA against that exact candidate. New source or
a fresh review invalidates prior human approval. Only one assessment may be active.

See [task orchestration](task-orchestration.md) for exact command/JSON examples,
legacy-task compatibility and the local operator-attestation trust boundary.

Completed report artifacts are durable outbox receipts for typed review/test knowledge.
Failed writes expose `knowledge_persistence: pending` and `persistence_pending` task
state. Repeating the same request retries persistence without rerunning a completed
model. Stable keys return existing dispatches/results; another live request for the
same candidate/gate is rejected. Uncertain dispatches require explicit recovery.
External actions do not acquire an exactly-once guarantee.

## Upgrade and verification

Use the established setup/update workflow with the same installation directory; it
backs up and explicitly migrates the database. Checkout-managed databases use
`oh migrate`. Normal launch rejects old schemas and never migrates silently.

Migration `0006` adds mappings/metadata without rewriting native homes/transcripts,
changing historical migrations, deleting knowledge or publishing observations. Old
task owners are adopted across spec changes. Task-wide memory mappings become
conversation-private owners; original knowledge stays auditable with its original owner.

```sh
PATH="$PWD/.venv/bin:$PATH" python3 -m unittest discover -s tests -v
PATH="$PWD/.venv/bin:$PATH" python3 -I -S tests/run_kernel.py
```

Tests use disposable stores/homes and fake providers. They verify concurrent dispatch,
input integrity, scope boundaries and persistence retries without starting authenticated
models. Live native privilege, trust and OS policy behavior remains a separate check.
Editing this checkout does not update the installed application or operational database.

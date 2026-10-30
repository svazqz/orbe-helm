# Knowledge memory

This is the current schema 0006 memory guide. [Persistent workflows](persistent-workflows.md)
defines identity and independent assessment. Dated validation records describe past
versions; they do not override the behavior here.

## Availability and retrieval

Memory is enabled by default in native Codex/Claude and managed `oh chat`. Scoped
MCP tools provide `search_memory`, `read_memory` and `save_memory`. Bindings fix owner,
visibility and audience; they are revoked at launch/turn end. Agent payloads cannot
select another owner or become an operator. Native/managed history bindings differ;
crossing interfaces does not promise exact native resume.

Without a configured embedding runtime, durable writes and keyword search work and
report `keyword-only`. Optional local FastEmbed inference adds hybrid keyword/semantic
ranking. No embedding API key or separate vector service is required. sqlite-vec is
used where extension loading works; otherwise the local exact-cosine fallback reports
`python-exact`. Both vector paths are exact searches and need capacity measurements.

Agent sessions intentionally cannot run operator `status`, `configure`, or `reindex`.
An access-denied result from those commands does not establish that memory is down.
Use scoped search/read/save to check the agent interface and a normal operator
terminal for maintenance. Do not remove a binding to bypass this boundary.

## Enable semantic retrieval

Finish active OrbeHelm sessions and stop the optional editor before updating. Select
the reviewed checkout/tag you intend to install; update includes local source changes.
From a normal operator terminal, outside an agent session:

```sh
./update.sh --memory
# Fresh install: ./setup.sh --memory
# Retain the original --install-dir if customized.
oh memory configure --download-model
oh memory status
```

Setup/update installs optional FastEmbed without downloading weights or starting an
agent. Configure explicitly downloads a public multilingual model into application
storage, checks document/query inference and activates indexing. Normal queries never
silently download missing models. Runtime/model fingerprints prevent mixing vectors
after environment changes. If cached artifacts remain valid after a library update,
explicitly run `oh memory configure` to reconfigure/reindex them.

Status and a representative query should confirm actual retrieval, not merely package
installation. `pending_embeddings` and `pending_index_units` expose accessible backlog.
An empty search result alone proves neither missing storage nor failed retrieval.
To deliberately retain keyword search, run `oh memory configure --embedding-model=none`.

## Ownership and visibility

Workstream = project/profile/task key; context = workstream/specialization. Switching
providers preserves the logical context but each provider has its own native session.
Use project visibility to share eligible technical outcomes across project contexts:

```sh
oh --profile=developer --spec=python --project=/path/to/project \
  --unique-key=APP-42 --memory-visibility=project
```

Visibility is private, project, or global within this installation. New owners default
to private. A launch flag changes the default for new units and never reclassifies old
ones. Audience can be `*`, a profile, or `profile:spec`; filtering precedes ranking and
direct reads. Private inputs force private derivations, and project inputs cannot be
silently published globally. Global does not mean internet publication or cross-machine
synchronization. Full-access agents have no same-user filesystem isolation guarantee.

## Record technical outcomes

Save one focused decision, architecture change, feature, review, test or constraint
with a stable source ID and artifact/revision evidence. Agent-written knowledge is
reported evidence, not independently verified truth. Developer bindings cannot award
themselves independent verification. Arbitrary replies remain conversation history;
they are not automatically converted into new technical KUnits.

An explicit operator write can use:

```sh
oh memory put --project=/path/to/project --thread=CONVERSATION_ID \
  --from-file=./decision.txt --source-id=APP-42:storage:1 \
  --kind=decision --evidence=git:COMMIT_SHA:docs/storage.md \
  --memory-visibility=project --evidence-state=implemented
```

Changing a source ID's content conflicts rather than overwriting it. Similar facts
remain distinct; semantic similarity does not authorize merging or prove correctness.
Definitions supply instructions, history supplies an audit trail, knowledge supplies
technical outcomes. Store no credentials or behavioral prompts as knowledge.

## Inspect and recover

In an operator terminal:

```sh
oh conversations list --project=/path/to/project
oh memory query --project=/path/to/project --thread=CONVERSATION_ID --query='deployment' --limit=10
oh memory list --project=/path/to/project --thread=CONVERSATION_ID
oh memory show UNIT_ID --project=/path/to/project --thread=CONVERSATION_ID
oh memory history UNIT_ID --project=/path/to/project --thread=CONVERSATION_ID
```

Existing logical owners can be selected with `--actor` instead of `--thread`.
Use the current revision from show/query for optimistic concurrency:

```sh
oh memory visibility UNIT_ID --project=/path/to/project --thread=CONVERSATION_ID \
  --visibility=project --expected-version=1
oh memory revise UNIT_ID --project=/path/to/project --thread=CONVERSATION_ID \
  --from-file=./corrected.txt --expected-version=2
oh memory retract UNIT_ID --project=/path/to/project --thread=CONVERSATION_ID --expected-version=3
oh memory reindex
# Corrupt projection recovery; retains a backup:
oh memory reindex --rebuild-index
```

Canonical revisions/ownership live in the application database. The FTS/vector index
is a rebuildable projection. Corrections/retractions/visibility changes advance a
policy epoch and invalidate dependent units; already delivered text cannot be recalled
from a model/native transcript. Canonical audit/visibility operations remain available
without working embedding inference. Normal writes do not require routine full reindex.
Legacy import is explicit and private; historical unclassified units are auditable but
not automatically injected as current knowledge.

## Disable memory for native continuity

```sh
oh --agent=codex --no-memory
oh chat --agent=claude --no-memory
```

This skips retrieval, memory MCP injection, conversation-body capture and historical
handoffs while retaining existing stored data and native identifiers for resume.
Provider histories stay separate. `--new-session` starts a fresh native generation.
After definition changes, explicitly ask the agent to reread `ORBEHELM_INSTRUCTIONS_FILE`.
Re-enabling memory starts a fresh context with authorized knowledge and does not import
an unrecorded period. Set `memory = false` under `[ORBEHELM]` in defaults to persist
that preference; `--memory` overrides it per launch.

See [development](development.md) for isolated semantic checks and provider evidence,
and [installation](installation.md) for backup/update recovery.

# Owned knowledge memory

Schema `0006` and [persistent workflows](persistent-workflows.md) supersede the
historical automatic assistant-observation capture below. New agent knowledge requires
an outcome type and artifact/revision evidence; arbitrary replies remain history.
Visibility includes project scope and retrieval enforces role/spec audience. Native
Codex/Claude also receive scoped tools. Historical unclassified units remain auditable
but are not automatically injected.

OrbeHelm memory is a set of durable, revisioned knowledge units (KUnits). Conversation
history remains a separate audit ledger. This memory engine is available in managed
`oh chat` for Claude and Codex; native `oh run` retains its existing transcript/task
behavior and does not automatically receive the new memory binding.

## Enable local semantic retrieval

From the updated source checkout, update an existing installation:

```sh
./update.sh --memory
# For a fresh installation, use ./setup.sh --memory instead.
oh memory configure --download-model
```

Use the same `--install-dir` as the original installation if it was customized.
Setup/update install the optional FastEmbed runtime but do not download model weights
or start an authenticated agent. The configure command explicitly downloads the
public multilingual model into the application's `state/embedding-models/`. It uses
anonymous download requests, not personal Hugging Face credentials. No embedding API
key or vector database service is needed. Model inference uses the local CPU.

The default is `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` through
FastEmbed 0.9.1. Its artifacts, adapter version, and inference runtime versions become
the embedding identity. Queries load only the configured local model; they never
silently download replacements. Model input windows are counted with a non-truncating
tokenizer, subdivided when necessary, and pooled so long chunks are not silently lost.

`requirements-memory.lock` adds the pinned FastEmbed entry point to the existing
application pins. Its additional transitive dependencies are resolved for the target
platform. Runtime/model fingerprints prevent mixing vectors after an environment
change; they are not a claim that every platform has an identical dependency lock.

```sh
oh memory status
# Explicitly reconfigure/reindex cached artifacts after an inference-library change:
oh memory configure
# Select another supported public text model; downloading remains explicit:
oh memory configure --embedding-model=MODEL_NAME --download-model
# Deliberately use keyword search only:
oh memory configure --embedding-model=none
```

Without a configured embedding runtime, knowledge recording and FTS search still
work. Search results and chat diagnostics explicitly report `keyword-only`.
With embeddings configured, keyword and semantic rankings are combined using
reciprocal rank fusion. `sqlite-vec` supplies native cosine distance where Python
supports extension loading. Otherwise, exact cosine is evaluated locally over the
same authorized vectors; results report `vector_backend: python-exact`. Both paths
perform exact search, so retrieval cost grows with the accessible corpus size.

## Launch visibility and ownership

```sh
oh chat --agent=claude --project=/path/to/project --unique-key=APP-123 --memory-visibility=private
oh chat --agent=codex --project=/path/to/project --unique-key=APP-123 --memory-visibility=global
```

The logical owner excludes agent choice. Keyed chats use the existing logical task
orbe; other chats use their provider-independent conversation identity. An explicit
conversation-to-owner mapping is retained. Switching providers preserves that owner.
The launch flag sets the default for new units and is retained for subsequent launches
of that owner. A new owner defaults to private. It never reclassifies historical units.
Chat prints its owner, default visibility, and retrieval mode.

An orbe can retrieve active global units from all projects in this installation and
its own private units. Project membership alone grants no access to another owner's
private KUnits. Global visibility preserves the original owner and KUnit ID. Global
does not mean synchronized across computers or published to the internet.

Agents receive a bounded authorized selection before each managed turn. They also
receive scoped `search_memory`, `read_memory`, and `save_memory` MCP tools. Tool
payloads cannot select an owner, manufacture an operator identity, or change visibility.
The opaque binding fixes owner and launch policy; it is checked for expiry/revocation
on every call and revoked at turn end. Credential files have owner-only permissions
and are removed afterward. Complete native permission/approval behavior still depends
on the provider CLI. If Claude denies these tools in structured chat, grant only the
required native rules explicitly, for example:

```sh
oh chat --agent=claude --project=/path/to/project --memory-visibility=private \
  --allow-tool mcp__orbehelm_memory__search_memory \
  --allow-tool mcp__orbehelm_memory__read_memory \
  --allow-tool mcp__orbehelm_memory__save_memory
```

No blanket permission bypass is added. Automatic retrieval and observation capture
are owned by OrbeHelm and do not require the agent to call a memory tool successfully.

## Recording, segmentation, and provenance

Agents can explicitly save a focused finding, decision, or procedure with a stable
`source_id`. Agent-written units are `reported`, not independently verified facts.
After a successfully completed turn, assistant-visible text is also queued durably
and split into bounded paragraph-oriented observation units. Failed turns are retained
in conversation history but their automatic observations are not published to memory.
This deterministic capture does not run a second model to infer factual conclusions.
Raw tool events remain in the ledger; they are not automatically accepted knowledge.

Units are segmented again for retrieval. Matching chunks, rather than an unrelated
unit prefix, are included in handoffs. Exact duplicates with matching owner, visibility,
state, and provenance share a KUnit while retaining separate source records. Similar
or contradictory claims remain distinct; semantic similarity does not authorize a
merge or establish truth. Global topic clustering and model-driven consolidation are
not performed by this implementation.

Memory reads and injections record source revisions. New units inherit private
visibility when private inputs were read, even in a global-default launch. Resumed
native sessions inherit their earlier memory-read provenance. Fresh global handoffs
omit private/unclassified historical messages and private checkpoints. These are
conservative safeguards against publishing private context through a later turn.

## Inspect and change units

```sh
oh conversations list --project=/path/to/project
# Select a returned conversation ID:
oh memory query --project=/path/to/project --thread=THREAD_ID --query='deployment decision' --limit=10
oh memory list --project=/path/to/project --thread=THREAD_ID
oh memory show UNIT_ID --project=/path/to/project --thread=THREAD_ID
oh memory history UNIT_ID --project=/path/to/project --thread=THREAD_ID
```

`--thread` resolves the recorded memory owner, including keyed chats. An operator can
also select an existing logical orbe using `--actor=LOGICAL_ORBE_ID`. Historical
revisions and source details are owner-scoped operator audit data; another orbe reading
a global unit receives its current public content without private source references.

```sh
oh memory put --project=/path/to/project --thread=THREAD_ID \
  --from-file=./fact.txt --source-id=decision-123
# Optional visibility for this explicit write only:
oh memory put --project=/path/to/project --thread=THREAD_ID \
  --from-file=./fact.txt --source-id=public-decision-123 --memory-visibility=global

oh memory visibility UNIT_ID --project=/path/to/project --thread=THREAD_ID \
  --visibility=global --expected-version=1
oh memory visibility UNIT_ID --project=/path/to/project --thread=THREAD_ID \
  --visibility=private --expected-version=2
oh memory revise UNIT_ID --project=/path/to/project --thread=THREAD_ID \
  --from-file=./corrected.txt --expected-version=3
oh memory retract UNIT_ID --project=/path/to/project --thread=THREAD_ID --expected-version=4
```

Use the current `revision` returned by show/query. A conflicting revision fails rather
than overwriting another change. Reusing a source ID with different content fails.
Only an explicit operator operation changes an existing unit's visibility/revision.
Canonical writes, visibility changes, and owner audit reads remain available even if
the optional embedding runtime is missing or broken. Model health never prevents
revoking a unit's global visibility.

Visibility changes, corrections, and retractions advance a policy epoch and invalidate
transitively derived units. Retrieval checks current canonical ownership/state before
ranking, regardless of stale index contents. Future managed turns start fresh when
that epoch changes and exclude earlier-epoch history/checkpoints. Invalidated units
remain auditable but must be regenerated from currently authorized sources. Publishing
a derived unit requires its private sources to be explicitly released first.

Previously delivered information cannot be recalled from a model or an existing
native transcript. This is application-level access enforcement; unrestricted
same-user filesystem access requires a separately enforced host boundary. Local
embedding inference also does not change the selected agent provider's operation.

## Storage, recovery, and compatibility

Schema `0005` adds KUnits/revisions, source aliases and dependencies, owner mappings,
bindings/read provenance, capture jobs, and index jobs to the existing SQLite database.
Older migrations remain unchanged. Setup/update/migrate back up existing databases;
normal launch does not apply migrations. Legacy task/project knowledge remains readable
through its old explicit workflow and is not silently published or imported.

```sh
# Explicitly import only the selected legacy author's units, always private/reported:
oh memory import-legacy --project=/path/to/project --actor=LOGICAL_ORBE_ID

oh memory reindex
# Retain a backup of a corrupt projection and rebuild from canonical records:
oh memory reindex --rebuild-index
# Retry completed-turn capture jobs for one owner:
oh memory retry-capture --project=/path/to/project --thread=THREAD_ID
```

`state/memory-index.sqlite3` holds FTS chunks and vector projections. It can be rebuilt
without deleting canonical units or revisions. Visibility-only updates reuse unchanged
vectors. Index jobs survive failures and stale workers cannot overwrite a newer
revision. Ordinary queries process a bounded backlog; `pending_index_units` and
`pending_embeddings` report remaining work within the caller's accessible corpus.
Direct reads use canonical data immediately. Explicit reindex drains the pending
backlog and reports errors instead of silently declaring it complete.

The full regression command remains:

```sh
python3 -m unittest discover -s tests -v
python3 -I -S tests/run_kernel.py
```

Optional explicit integration checks use isolated data and model artifacts inside
this checkout:

```sh
python3 tests/check_embedding_model.py --download
python3 tests/check_embedding_model.py
python3 tests/check_memory_cli.py
```

These run local embedding inference and the CLI/stdio bridge, not authenticated
Claude/Codex sessions. Model quality, large-corpus performance, and live native tool
approval should be evaluated separately for a deployment.

## Optional native continuity

Memory is enabled by default. Choose the mode when launching:

```sh
oh chat --agent=claude --memory
oh chat --agent=claude --no-memory
oh --agent=codex --no-memory
```

With `--no-memory`, OrbeHelm skips knowledge retrieval, automatic knowledge capture,
conversation body recording, memory MCP injection, and historical handoffs. No
embedding model is needed. Existing stored knowledge is retained; explicit memory
management commands remain available. OrbeHelm still stores launch and native session
identifiers so it can resume the correct conversation.

Each agent keeps its own native history. Switching between Claude and Codex in this
mode does not transfer context. OrbeHelm uses the recorded native session identifier
with the agent's resume option, including after definitions change. Use `/new` in
managed chat or `--new-session` at launch to start fresh.

Current instructions are materialized at a stable path exposed to the child agent as
`ORBEHELM_INSTRUCTIONS_FILE`. After updating definitions, explicitly ask the agent:
“Read the file identified by ORBEHELM_INSTRUCTIONS_FILE and apply its updated rules.”
The existing native conversation is not automatically refreshed. In managed chat,
that file is refreshed before each model turn; native interactive launches refresh
it when relaunched. OrbeHelm history, search, and checkpoints are unavailable during
memory-off chat.

To make this the default, add `memory = false` under `[ORBEHELM]` in your defaults
file. `--memory` overrides that default for one launch. Re-enabling memory after an
off period starts a fresh native context with authorized OrbeHelm memory; it does
not import the unrecorded period. The agent's previous native history is retained.

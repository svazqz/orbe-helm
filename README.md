# OrbeHelm Alpha

Current workflow: [persistent workstreams, isolated role/spec contexts, typed knowledge,
full-access execution and parallel review/QA](docs/persistent-workflows.md).

Current alpha release: **v0.1.0-alpha.4** (`0.1.0a4`). See the
[changelog](CHANGELOG.md) and [release/tag policy](docs/releases.md).

OrbeHelm composes reusable agent definitions and manages project configuration,
native orbes, task coordination, and durable conversation history. The command is `oh`.
Python 3.11+, macOS, and Linux are the initial targets. Agent CLIs, model access,
authentication, and MCP executables are separate prerequisites.

Native/managed sessions record typed knowledge units with private/project/global visibility and
hybrid keyword/semantic retrieval. See [knowledge memory](docs/knowledge-memory.md).
To enable local embeddings on an existing installation:

```sh
./update.sh --memory
oh memory configure --download-model
oh chat --agent=claude --project=/path/to/project --memory-visibility=private
```

Model download is explicit. Without it, knowledge capture and keyword retrieval remain
available and are reported as `keyword-only`.

## Install and update

```sh
./setup.sh
# Open a new terminal to activate PATH.
```

Setup installs under `~/bin/orbehelm`, with private runtime storage under
`~/.orbehelm`. To select Claude by default, create `~/.orbehelmrc`:

```ini
[ORBEHELM]
agent = claude
profile = developer
```

Normal CLI work requires no running web server. To update, finish active agent work,
stop the optional editor if running, then execute from the source clone:

```sh
git pull --ff-only
./update.sh
```

Use `--install-dir` for a custom installation. Setup/update share the same locked
dependency and reviewed migration path. Existing database history, runtime locations,
and local source edits are retained. See [installation](docs/installation.md) for
version selection, bundled source merging, backups, and recovery limits.

## Conversations and agent switching

```sh
oh chat --agent=claude --project=/path/to/project --unique-key=APP-123
```

Inside chat, use `/agent codex` or `/agent claude` to switch the next turn's adapter.
`/checkpoint text` saves working memory; `/history` and `/search text` retrieve stored
events. `/new` refreshes the native session while preserving the conversation.
`/exit` leaves chat. `--prompt='request'` performs one captured turn and exits.

OrbeHelm records exposed user/assistant messages, structured native events, and tool
activity incrementally. Claude and Codex share the same conversation identity for a
project/profile/specialization/task selection. Native session IDs remain adapter-specific.
The current managed runner uses the structured CLI interfaces; native interactive
approval callbacks are not implemented. Sessions request full execution privileges.
Historical Claude tool grants remain available via
`--allow-tool RULE` or `/allow-tool RULE`, stay local to the current chat process, and
can be cleared with `/clear-tools`; they do not replace the full-access launch policy.

Unchanged policy can resume an exact native ID. Changing effective profile content,
skills or MCP configuration starts a fresh native conversation with a bounded
handoff and access to the full captured ledger. Prior transcripts are retained. This
preserves retrievable history, not an identical or unlimited model context window.
Switching providers selects that provider's compatible session when available.

```sh
oh conversations list --project=/path/to/project
oh conversations history --thread=<id> --project=/path/to/project
oh conversations search --thread=<id> --query='test failure' --project=/path/to/project
oh conversations history --thread=<id> --after=0 --limit=50 --project=/path/to/project
```

Replace IDs with list output. [Conversation capture and limitations](docs/conversation-memory.md)
describes storage, pagination, checkpointing, permission limits, and capture failures.
History can contain sensitive source/tool data; keep installation storage and backups private.

## Native interactive orbes

```sh
oh --agent=claude --profile=developer --spec=python --project=/path/to/project
oh --agent=codex --unique-key=APP-123 --project=/path/to/project
oh --new-session --project=/path/to/project
```

`oh` / `oh run` retains the selected agent's native terminal interface. Dedicated
Claude/Codex transcript capture is best-effort and reports its coverage. Known session
IDs resume only with unchanged effective policy; missing IDs start fresh. OpenCode
persistent native launch is rejected until exact native-ID resume is supported;
builds and one-shot delegation remain available. `--new-session` retains the orbe;
`--new-orbe` selects a new orbe identity.
Native homes, transcripts, and prior launch records are preserved.

`--unique-key` selects a separate workstream. Default unkeyed memory-enabled sessions
also support immutable candidate submission and parallel reviewer/QA delegation.
See [task orchestration](docs/task-orchestration.md). Running
work and submitted reviewer/QA candidates retain their captured configuration.

## Shared definitions and project overrides

Shared edits automatically apply to every project's next launch. No per-project
library adoption is required. Project context, local replacements, and aliases remain
scoped to the project. Source/configuration history stays available for rollback.

```sh
oh get definition.profile.developer
oh get definition.profile.developer --global
oh override definition.profile.developer --from-file=./developer.md
oh reset definition.profile.developer
oh history definition.profile.developer --global
oh diff definition.profile.developer --revision=<id> --global
oh rollback definition.profile.developer --revision=<id> --global
```

Default scope is the current project. `get` prints content; `--json` includes source
and revision provenance. Override replaces an owned file locally; reset inherits its
current shared version. `--file=<owned-path>` selects a manifest or another owned file.
Shared file edits use `oh set <target> --from-file=<input> --global`.

Targets cover `definition.base`, `definition.profile.<name>`,
`definition.specialization.<profile>.<name>`, `definition.skill.<name>`,
`definition.skillset.<name>`, and `definition.mcp.<name>`. Use `oh add <target>
--from-dir=<package>` for a package with `definition.json` and instruction/resources;
use `--from-file` for a single manifest. `oh remove <target>` removes/masks a local
definition; `--global` explicitly changes the shared library. Validation and active
usage checks prevent dependency-invalid removal. See [configuration](docs/configuration.md)
and [scope/removal rules](docs/configuration-scopes-and-removal.md).

A plain agent opened in `definitions/` can read its `AGENTS.md` or `CLAUDE.md` authoring
guide. Authoritative definitions remain separate from generated adapter output.

## Optional shared-definition editor

```sh
oh web
```

Open `http://127.0.0.1:8765` to edit shared instructions, profiles, skills, MCP registrations,
and source resources, inspect history, or restore a shared release. The UI has no project,
task, or orbe management routes. Shared saves affect future launches automatically;
local overrides continue to win until reset. `oh server start` is an optional alias for
the editor, and `server status` reports only editor availability. Neither gates CLI work.

## CLI management

| Command | Action |
| --- | --- |
| `oh list` | List profiles, specializations, skillsets, and adapters |
| `oh resolve` / `oh build` | Inspect effective sources / generate verified artifacts |
| `oh doctor` | Check agent/MCP executables and environment-variable presence |
| `oh doctor --integration=herdr` | Inspect owner binary, pane discovery, and metadata support |
| `oh projects register` / `show` / `history` | Manage project identity and inspect source revisions |
| `oh projects refresh` | Capture external project context and alias changes |
| `oh projects add-skill NAME` / `remove-skill NAME` | Change explicit additive skill references |
| `oh projects add-mcp NAME` / `remove-mcp NAME` | Change explicit additive MCP references |
| `oh projects capabilities` / `check-capabilities` | Inspect realized dependencies / explicitly check updates and authentication metadata |
| `oh projects login-mcp NAME --agent=claude` | Run the selected native MCP sign-in command explicitly |
| `oh skills list` / `install NAME` | Inspect registrations / install selected skill resources |
| `oh orbes list` / `show ID` / `history ID` | Inspect native launch history and active runtime records |
| `oh tasks list` / `context` / `submit` / `delegate` / `recover` | Task coordination through the local service |
| `oh memory save` / `read` / `accept` | Versioned task knowledge and explicit project acceptance |
| `oh status` | Project/build/orbe summary |
| `oh migrate` | Back up and apply reviewed schema upgrades explicitly |
| `oh auth --agent=codex` | Explicit Codex login in the wrapper credential store |

Common selection options are `--agent`, `--profile`, `--spec`, `--skillset`, `--skills`,
`--project`, and `--config`. See [user configuration](examples/orbehelmrc).
`run --dry-run` prints a write-free native command; `chat --dry-run` prints a managed
plan. Product-mode native previews require an already registered project. Cold remote
skill resolution can read the network. No preview starts an agent or MCP process.
`--strict` refuses work because exclusive native context isolation is not established.

## Herdr labels

Native launches and managed turns report `<PROFILE> - <UNIQUE-KEY> - <SPEC>`, omitting
missing parts. Integration prefers `HERDR_BIN_PATH` for the binary owning the pane,
fallbacks to PATH, and sets source-scoped display-agent/title metadata. It clears its
metadata on exit and does not take over lifecycle detection. Diagnostics are available
through `oh doctor --integration=herdr`. Headless delegation never relabels the parent.
Live rendering on Herdr 0.9.5 remains a separate verification step.

## Development and compatibility

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.lock
python3 -m unittest discover -s tests -v
```

Migration `0004` adds file overlays and conversation storage after the existing orbe
rename migrations. Older database/runtime/configuration names remain readable; IDs,
legacy records, transcripts, and `legacy/` remain intact. Existing installations must
run update or migrate before using the new schema. Do not hand-edit generated output.

Verification uses isolated databases/homes, fake native processes, and ASGI form tests.
No authenticated model conversation or live Herdr rendering is claimed by these tests.
See [architecture](docs/architecture.md) and [validation](docs/validation.md).

Choose OrbeHelm memory or native conversation continuity:

```sh
oh chat --agent=claude --memory     # Default: shared knowledge and handoffs
oh chat --agent=claude --no-memory  # Native history; manual definition refresh
oh --agent=codex --no-memory       # Native interactive launch
```

With memory disabled, ask the agent to reread `ORBEHELM_INSTRUCTIONS_FILE` after
updating definitions. See [memory modes](docs/knowledge-memory.md#optional-native-continuity).

## Close and prune sessions

```sh
oh close                              # latest running session in the current project
oh close --project /path/to/project   # latest running session in another project
oh close ORBE_ID                      # one orbe, across this installation
oh close --all --project /path/to/project
oh close --global                     # every project in this installation
oh prune PROJECT_ID                   # delete all native orbes in this project
oh prune --global                     # delete native orbes across projects
```

Closing stops the launcher and its verified descendants and retains native history.
Pruning first closes the selected sessions, lists their IDs, and requires typing
`DELETE`. It deletes their native runtime homes, launch records, and active pointers.
Project definitions, tasks, conversation events, and typed knowledge are retained.
`--dry-run` previews either operation without signaling processes or deleting data.
Use `oh projects list` and `oh orbes list` to find IDs. Global scope covers only the
installation selected by `--root`; it does not affect independent installations.
Older active launchers require `lsof` to verify ownership before receiving signals.


## Contributing and releasing

See [development workflow](docs/development.md) for bootstrap, focused changes,
verification and independent review; [release process](docs/releases.md) covers exact
versions, retained artifacts and draft publication. Start with:

```sh
python3 scripts/dev.py bootstrap
.venv/bin/python scripts/dev.py check
```

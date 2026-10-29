# OrbeHelm Alpha

OrbeHelm composes reusable agent instructions and launches a selected CLI with generated configuration. Edit a shared definition once; the next build or launch detects changes and reuses or regenerates the required output automatically.

The command is `oh`. An **orbe** is a persistent managed identity with its runtime
home and launch history. Task-scoped roles use logical orbes; each host agent
continues to manage its own native conversations.

Version 0.1.0a1. Python 3.11 or later. macOS and Linux are the initial targets. Portable composition uses the Python standard library; the product UI and database use FastAPI, SQLAlchemy, Alembic, Jinja2, and Uvicorn. Agent CLIs, model access, and MCP server executables are separate prerequisites.

## Install and run

After cloning the project, run:

```sh
./setup.sh
# Open a new terminal to activate the PATH change.
oh server start
```

In a second terminal, create or resume an orbe:

```sh
oh --project=/path/to/project --agent=codex --profile=developer --spec=python
# Enable task memory and reviewer/QA orchestration with a stable key:
oh --project=/path/to/project --agent=codex --unique-key=APP-123
```

Setup installs the app and database under `~/bin/orbehelm`, creates runtime storage
under `~/.orbehelm`, installs Python dependencies in a private virtual environment,
and updates the detected shell startup file once. The server starts manually and
stays in the foreground. Real launches refuse to start unless a matching server is
ready. Agent CLIs and their authentication remain separate prerequisites.
See [Installation](docs/installation.md) for shell support, custom paths, ports,
reinstallation, and existing-data behavior.

To update an installed application, stop the server and finish active orbes, pull
the desired source revision, and run `./update.sh` from the clone. It refreshes the
application and dependencies and runs migrations while retaining the installed port,
runtime location, and local source edits. Then restart `oh server start`. Use
`--install-dir` for a custom application location. See
[the update workflow](docs/installation.md#updating-an-installed-application) for
version selection and bundled definition update rules.

## Local management UI and project versions

The full suite passes 140 automated tests on Python 3.13, including database
migrations, definition publication, selective project adoption/rollback, overrides,
orbe launch history, task orchestration, memory, and HTTP form workflows. Validation used disposable
state only; no real checkout migration or authenticated model conversation was performed.
Live browser startup remains environment-limited; see [validation evidence](docs/validation.md).

## Upgrading from Agentic

Activate the project environment and run `./oh migrate`. Schema `0003` renames
managed-session tables and columns to orbes while retaining IDs, relationships,
runtime paths, and immutable history. Existing databases are backed up first.
The upgrade has been tested with disposable data; it has not been applied to this
checkout's existing operational database.

Direct checkout deployments use `state/orbehelm.sqlite3`, `state/orbes/<id>/orbe.json`,
and `state/orbe-keys/`. Existing `state/agentic.sqlite3`, `state/sessions/`, and
`state/session-keys/` remain readable in place, including the original locks and
native runtime homes. Resuming an old orbe preserves its UUID and writes canonical
`orbe.json` metadata without changing the old `session.json` record.

New configuration uses `orbehelm.project.json`, `~/.orbehelmrc`, `[ORBEHELM]`,
`ORBEHELM_ROOT`, and `ORBEHELM_CONFIG`. Old project files, user configuration names,
environment-variable defaults, and section markers are accepted for compatibility.
CLI options and the new environment-variable names take precedence. When both old
and new configuration files or databases exist, select the configuration explicitly
or reconcile the duplicate files before continuing.

Use `oh projects update --project=/path/to/project` to adopt the renamed shared
instructions in an already pinned project. Immutable snapshots and `legacy/` are
preserved. Python imports now use `orbehelm`; the executable is `oh`, and the
fresh-runtime flag is `--new-orbe`.

Use a project-local environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.lock
# Optional installed entry point (requires the setuptools build backend):
# python3 -m pip install -e '.[dev]'
python3 -m unittest discover -s tests -v
# After the full suite passes:
./oh migrate
./oh web
```

Open `http://127.0.0.1:8765` and choose a project. Project tabs separate Skills,
MCP servers, Instructions, Updates, Orbes, and History. Shared Skills and MCP
library pages provide add forms; apply library updates to a project before enabling
a new item there. Project tabs can remove explicit additions while preserving inherited
requirements. Shared items offer usage review and can be removed only when unused;
history and credentials are retained. MCP cards can start a dedicated agent OAuth login command, show
its progress, and cancel it. Sign-in uses an existing matching agent runtime.
The UI does not start model conversations or browse conversation bodies. Only
loopback binding is supported; remote hosting is outside this release.

`migrate` applies reviewed Alembic migrations, backs up an existing database under
`state/backups/`, publishes the initial definitions, and indexes legacy orbe
metadata. Existing homes, IDs, auth stores, and generated files remain in place.
Legacy timestamps and configuration provenance remain unknown. Review import warnings
for orbes whose project directories no longer exist. Before migration the existing
CLI retains its compatibility behavior; after migration, launches use pinned project
configuration and new builds live under `state/projects/`.

```sh
./oh projects register --project=/path/to/project
./oh projects show --project=/path/to/project
./oh definitions history
./oh projects preview --project=/path/to/project
./oh projects update --project=/path/to/project
./oh projects rollback --project=/path/to/project --revision=<configuration-id>
./oh projects refresh --project=/path/to/project
```

Normal build/run commands publish valid changes in global source files, but existing
projects stay pinned until explicit adoption. The UI reports unpublished working-file
changes and has a validate/publish action. Updating one project does not update another.
Only affected realized configurations are rebuilt; unused combinations are generated
on demand. Running agents retain their captured configuration, and their next launch
uses the project's selected configuration without rotating the orbe ID.

Project instruction files and user skill aliases are snapshotted too; use `projects
refresh` or the UI context-refresh control after editing them. Project profile overrides
use the common section template and apply before specialization. Conflicting upstream
section changes block adoption until the override is revised or removed. Dependencies
remain additive. Restoring a previous project configuration also restores its context,
overrides, and selected resources, but does not erase conversations or undo agent actions.

Read-only commands do not register projects, publish releases, or migrate. In product
mode, register a project before its first `resolve`, `doctor`, or dry run. Dependencies
use compatible ranges in pyproject.toml; requirements.lock pins the tested runtime and
test dependency set for Python 3.13/macOS arm64. Other Python/platform combinations
require their own verification. See [validation limits](docs/validation.md).

## Quick start

Task-scoped developer/reviewer/QA orchestration and persistent memory are available
with `--unique-key`. Upgrade with `./oh migrate`, then see the
[workflow, commands, and limitations](docs/task-orchestration.md). Project **Tasks**
pages show persisted context and child results; native conversations remain separate.

Run from this checkout:

```sh
./oh list
./oh resolve --profile=developer --spec=php --skillset=quality
./oh build --agent=codex --profile=developer --spec=php --skillset=quality
./oh --agent=codex --profile=developer --spec=php --skillset=quality --dry-run
```

With the server running in another terminal, start an orbe in a real project:

```sh
./oh auth --agent=codex
./oh --agent=codex --profile=developer --spec=php --skillset=quality --project=/path/to/project
```

`auth` invokes Codex's interactive login explicitly. Installed-app credentials are stored under `~/.orbehelm/auth/codex`; direct checkout use retains `state/auth/codex`, separate from global Codex settings. Orbe homes reference that credential file; credentials are not copied into generated profiles. This wrapper store contains sensitive authentication material and must not be shared or committed. Existing global login is not automatically imported. Claude and OpenCode use their own authentication flows.

To make `oh` available by name, add this checkout to PATH, for example for the current shell:

```sh
export PATH="$PWD:$PATH"
oh --profile=developer --spec=php --skillset=quality --dry-run
```

An optional editable installation is supported with `python3 -m pip install -e .`. Set `ORBEHELM_ROOT` to the checkout directory when using an installed entry point. `--root` overrides it. Building with pip may require fetching setuptools; direct execution does not.

## Commands

| Command | Behavior |
| --- | --- |
| `oh server start` | Start the local server in the foreground |
| `oh server status` | Check readiness of the matching installation |
| `oh` or `oh run` | Resolve, install selected local skill dependencies, build if needed, and launch |
| `oh resolve` | Show selected instructions, dependency hashes, and configuration without installing or generating |
| `oh build` | Install selected local skills and generate verified agent-specific output |
| `oh doctor` | Check the selected executable, local MCP commands, and required environment variable presence |
| `oh list` | List profiles, specializations, skillsets, and adapters |
| `oh skills list` | List registered skills |
| `oh skills install testing` | Install one registered local skill into the wrapper cache |
| `oh status` | Show generated-build, installed-skill, and recorded-orbe state |
| `oh auth --agent=codex` | Authenticate in the wrapper's Codex credential store |

Common options: `--agent=codex|claude|opencode`, `--profile`, `--spec`, `--skillset`, `--skills`, `--config`, `--project`, and `--prompt`. `--dry-run` works with `run` (the default command) and prints only the planned shell launch command. It reads definitions and calculates the configuration hash in memory; it does not build, install skills, create homes, write records, or create or modify any files. Missing remote skills may be read into memory for hashing; verified installed skills work offline. The command references the calculated `generated/<agent>/<hash>/` configuration path, which may not exist yet. Use `build` with the same selections to generate those files before executing a printed command. No agent or MCP server is started. `--strict` refuses launch because exclusive context cannot yet be guaranteed. Dry-run output includes the supplied prompt; orbe records do not.

## Persistent orbes

Repeated launches reuse the active orbe for the same canonical project path, agent,
profile, and specialization. Skills, MCP selections, prompts, and build changes do not
change that identity. Generated configuration is refreshed on each launch; the host
controls how resumed conversations apply updated instructions.

```sh
oh --profile=developer --spec=python --project=/path/to/project
# Run the same command later to continue.
oh --profile=developer --spec=python --project=/path/to/project --new-orbe
```

`--new-orbe` preserves the previous orbe and makes a fresh orbe the active
one for subsequent launches. Concurrent launches of the same identity are rejected.
Installed orbe records and runtime homes live under `~/.orbehelm/orbes/`; active
pointers and locks live under `~/.orbehelm/orbe-keys/`. Direct checkout use retains
`state/orbes/` and `state/orbe-keys/`. Earlier random orbes are preserved
but are not automatically adopted. Moving a project changes its identity.

Codex resumes the latest saved conversation in its dedicated home. Claude continues
in a dedicated `CLAUDE_CONFIG_DIR`; OpenCode continues in dedicated XDG data, state,
and cache directories. Claude and OpenCode may therefore need authentication in
these homes (or provider environment variables); global credentials are not copied.
Codex continues using the shared wrapper credential store. Resume follows the latest
conversation within the dedicated runtime, including one created with a host's new-chat
command. This provides conversation persistence, not a separate memory system.

Codex and Claude start normally if no saved transcript exists. OpenCode requests
continuation after a successful previous launch; missing or deleted native history
is handled by that CLI. Use `--new-orbe` to recover a fresh runtime.
Dry runs remain read-only and show continuation flags for existing orbes; a first
launch preview references generated configuration without allocating a runtime home.
Authenticated resume has not been integration-tested; host-native configuration may
still apply, so exclusive isolation is not guaranteed.

You can ask the launched agent, “What is my current OrbeHelm orbe?” Shared
instructions tell it to read these launch-time environment variables:

| Variable | Value |
| --- | --- |
| `ORBEHELM_ORBE_ID` | Persistent OrbeHelm orbe ID, separate from the host conversation ID |
| `ORBEHELM_ORBE_DIR` | Absolute path to the orbe's runtime directory |
| `ORBEHELM_PROFILE` | Selected profile |
| `ORBEHELM_SPECIALIZATION` | Selected specialization, or an empty string for none |
| `ORBEHELM_PROJECT` | Canonical absolute project path |
| `ORBEHELM_AGENT_LABEL` | Profile, optional unique key, and optional specialization joined with ` - ` |

Values are refreshed for every launch and override inherited values. Orbe IDs
stay stable on reuse and change with `--new-orbe`. Orbe-specific values are
not embedded in shared generated builds. The agent needs permitted access to its
runtime environment to verify them; section overrides can replace the shared
instructions. Dry runs do not allocate or export new orbe metadata.

## Herdr agent labels

Interactive launches inside the Herdr terminal automatically set the displayed
agent label to `<PROFILE> - <UNIQUE-KEY> - <SPEC>`, omitting unavailable values.
Examples: `developer - APP-123 - python`, `developer - python`, and `reviewer`.
The integration requires `HERDR_ENV=1`, `HERDR_PANE_ID`, and `herdr` on PATH.
It uses Herdr's [display metadata API](https://herdr.dev/docs/cli-reference/)
without reporting or changing agent lifecycle state, renaming a workspace, or
changing global settings. Herdr normalizes display text and limits it to 80 characters.
OrbeHelm clears its display override when the interactive process exits. Headless
delegations do not relabel the parent's pane. Missing or failing Herdr support does
not block the agent launch; dry runs make no Herdr calls. Live Herdr rendering still
requires integration verification on a machine running Herdr.

## User defaults and skill aliases

Optional `~/.orbehelmrc` supplies defaults and skill mappings. CLI options override them. See [the commented example](examples/orbehelmrc) for every configurable value and [configuration details](docs/configuration.md#user-configuration).

```ini
[ORBEHELM]
agent = codex
profile = developer

[SKILLS]
laravel = https://github.com/Jeffallan/claude-skills/tree/main/skills/laravel-specialist
```

Start a PHP developer with the mapped Laravel skill:

```sh
oh --profile=developer --spec=php --skills=laravel --agent=codex
```

Missing selected skills install automatically during build or normal launch. GitHub skill folders include their supporting files. Installations remain inside this checkout and installer scripts are never executed. `--config` or `ORBEHELM_CONFIG` selects another user file; reading configuration never creates one.

`doctor` checks availability, not CLI-version compatibility, authentication validity, MCP connectivity, or model readiness. It returns 1 for missing prerequisites. Configuration errors return 2; completed orbes propagate the child exit code.

## Definition structure

```text
orbehelm/
├── oh
├── definitions/
│   ├── base/
│   ├── profiles/
│   ├── specializations/developer/
│   └── skillsets/
├── registry/
│   ├── skills/
│   └── mcp/
├── src/orbehelm/
├── generated/<agent>/<build hash>/
├── state/
│   ├── auth/
│   ├── orbes/
│   └── skills/
├── examples/
├── tests/
├── plan/
├── docs/
└── legacy/
```

`legacy/` preserves the earlier documents and composer for reference. Its tooling is superseded and should not be used for new builds. Generated files and state are excluded from version control.

Definitions are applied as base, profile, specialization, named skillsets, then optional project context. A specialization belongs to its primary profile: `--profile=reviewer --spec=php` requires an explicit reviewer/php definition; it does not load Developer behavior implicitly.

Base, profiles, and specializations share a [common section template](definitions/TEMPLATE.md). Sections add to inherited content by default; `[override]` replaces a complete section. Empty additions inherit and empty overrides clear; empty final sections are omitted. The generated instructions form one document without authoring markers or repeated source titles. Existing custom definitions must migrate to this template. See [composition rules](docs/configuration.md#common-instruction-template).

## Next steps

Read [Configuration](docs/configuration.md) to add profiles, skills, and MCP servers. Read [Architecture](docs/architecture.md) for fingerprints, state, and adapter boundaries. Read [Alpha validation](docs/validation.md) for tested behavior and limits.

The alpha supports local and public HTTPS skill sources, user defaults and aliases, dependency ordering, hash pins, generated instruction bundles, MCP configuration translation, and CLI launch orchestration. Native skill discovery integration, private-source authentication, automatic CLI installation, automatic updates, and full isolation are not implemented.

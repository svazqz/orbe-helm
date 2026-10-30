# Installing OrbeHelm

Install from a clone on macOS or Linux:

```sh
./setup.sh
```

Add `--memory` to setup/update to install the optional local embedding runtime.
`oh memory configure --download-model` then explicitly downloads the public model
into application storage. Normal setup/update does not download weights or start
an agent. See [knowledge memory](knowledge-memory.md) for visibility and retrieval.

The installer requires Python 3.11 or later. It detects a suitable `python3`,
`python3.13`, `python3.12`, or `python3.11`; set `ORBEHELM_PYTHON` to select a
specific executable. It checks `venv` and `ensurepip`, creates a private application
virtual environment, installs `requirements.lock`, checks runtime imports, and
initializes the database. The first installation normally needs access to the Python
package index. Missing system Python/venv packages produce an actionable error;
the installer does not invoke sudo or a system package manager.

The lockfile was tested on Python 3.13/macOS arm64. Other Python/platform combinations
must have compatible packages available. An incompatible pin or dependency download
failure stops setup; it does not leave a success message or update PATH.

## Installed layout

| Location | Contents |
| --- | --- |
| `~/bin/orbehelm/src/orbehelm/` | Application, server, templates, and static files |
| `~/bin/orbehelm/.venv/` | Application Python environment and dependencies |
| `~/bin/orbehelm/bin/oh` | Launcher that selects this application and its Python environment |
| `~/bin/orbehelm/state/orbehelm.sqlite3` | Database, alongside snapshots, builds, backups, and server application state |
| `~/bin/orbehelm/definitions/`, `registry/`, `examples/` | Editable authoritative definitions and local skill resources |
| `~/bin/orbehelm/installation.json` | Runtime-home location and loopback server URL |
| `~/.orbehelm/orbes/<id>/` | Persistent orbe metadata, native agent homes, and coordination overlays |
| `~/.orbehelm/orbe-keys/` | Active pointers and launch locks |
| `~/.orbehelm/auth/codex/` | OrbeHelm-managed Codex login store, created only by explicit authentication |

The installer creates application and orbe-home directories with owner-only access.
It copies application source and definitions, so the installed launcher does not
need the clone or its development virtual environment. It does not copy the clone's
state, existing orbes, credentials, generated output, or global agent settings.
A source checkout used directly continues to keep runtime files under its own
`state/` directory. Installing creates a separate application, not an automatic
migration of the clone's operational data.

## Shell PATH

Setup detects `$SHELL` and adds `~/bin/orbehelm/bin` in one managed block:

- zsh: `$ZDOTDIR/.zshrc`, or `~/.zshrc` when `ZDOTDIR` is unset.
- bash: `~/.bashrc`, plus the existing login startup file; on macOS a login file is
  created if needed.
- fish: `$XDG_CONFIG_HOME/fish/config.fish`, or `~/.config/fish/config.fish`.
- Other POSIX shells: `~/.profile`.

Existing content and startup-file symlinks are preserved. Changed files are backed
up under `~/bin/orbehelm/state/setup-backups/`. Repeating setup replaces the same
block instead of appending duplicates. A new terminal activates PATH; setup also
prints the exact command for the current terminal. It does not source your startup
files or start the server.

Use `--shell zsh`, `--shell bash`, or another supported shell to override detection;
use `--no-path` to manage PATH yourself.

## CLI work and the optional editor

After setup, launch without starting a server:

```sh
oh chat --agent=claude --project=/path/to/project --unique-key=APP-123
# Or keep the agent's native interface:
oh --agent=claude --profile=developer --spec=python --project=/path/to/project
```

Agent CLIs, provider access, MCP executables, and sign-in remain separate prerequisites.
Codex login is explicit with `oh auth --agent=codex`; Claude/OpenCode use their native
flows. No authenticated model session starts during setup/update. Native isolation
retains the documented limitations.

The service accesses the local database directly. Incomplete installations and old
schemas fail with setup/update/migrate guidance; no web listener is checked. Native
read-only resolve/doctor/dry runs require prior project registration in product mode.
Managed `chat --dry-run` is a write-free plan and requires no registered project.

`oh web` optionally starts a loopback shared-definition editor at
`http://127.0.0.1:8765`; `oh server start` remains an alias. The editor stays in the
foreground and stops with Ctrl-C. It has no project/task/orbe management routes.
`server status` describes editor availability, not CLI readiness. No daemon or automatic
server startup is installed.

## Options and reinstallation

```sh
./setup.sh --install-dir "$HOME/apps/orbehelm" \
  --orbes-dir "$HOME/.orbehelm" --shell zsh --port 8876
```

Installation metadata records the server port, so clients and server use the same
address. For a temporary override, export the same variable in both terminals:

```sh
export ORBEHELM_SERVER_URL=http://127.0.0.1:8876
```

Keep the application directory and orbe home separate. `/bin/orbehelm` is not the
default: `/bin` is protected on macOS. The selected default is `~/bin/orbehelm`.

Stop the server before rerunning setup from the clone with the same options.
Reinstallation replaces application code and refreshes locked dependencies, while
preserving database history and orbe homes. Existing database upgrades make backups.
Bundled sources are updated using the rules below; local customizations are retained. Setup
refuses an unmanaged nonempty application directory or a different orbe home for
an existing installation. Changing storage paths requires a separate migration.

`--offline` adds pip's `--no-index`; dependencies must already be available in the
application environment or pip's available local sources. It does not bypass
dependency checks. If setup fails after creating directories, fix the reported
prerequisite and rerun it with the same options. PATH updates occur only after
application initialization succeeds.

## Updating an installed application

Stop the foreground OrbeHelm server with Ctrl-C and finish active orbes before
updating. In the source clone:

```sh
git pull --ff-only
./update.sh
```

CLI work can resume immediately. Restart `oh web` only if you want the optional editor. Updates start no model sessions.
For a custom application directory, pass it explicitly:

```sh
./update.sh --install-dir "$HOME/apps/orbehelm"
```

The updater requires an existing managed installation. It retains the recorded
orbe-home location and server port unless explicitly overridden, leaves shell startup
files unchanged, refreshes application code and locked dependencies, and runs database
migrations and catalog initialization. It refuses to update while the installation's
server address is reachable. Runtime directories are created idempotently by the same
installer used for fresh setup. No separate global configuration is required.

`update.sh` runs the update path shipped in the checked-out revision. It does not
fetch code or choose a version. To install a particular release, check out its tag
first, then use `./setup.sh` for a fresh installation or `./update.sh` for an existing
one. These entry points are available in versions that include them. Both use the
same installer and Alembic migration chain; future layout upgrade steps must be
implemented there so upgrades and direct setup reach the same target layout.
Database migrations support forward upgrades. Checking out older application code
is not a supported database downgrade; restore a compatible backup into a separate
installation if an older version is needed.

This includes uncommitted local application changes: running update from this
development checkout installs those changes too. The first named release candidate
is `orbehelm-alpha` (`0.1.0a1`, schema `0006`); its tag is not published merely by
running setup/update. See [release/tag policy](releases.md).

Installation metadata records the application version and hashes of bundled files in
`definitions/`, `registry/`, `examples/`, and `skills/` when present. Updates refresh
unchanged bundled files, add new bundled files, and remove unchanged files retired
upstream. Locally edited or deleted files and local additions are retained. Preserved
files that differ from upstream are printed for manual review. Existing installations
without recorded hashes preserve differing existing files on their first update,
because their origin cannot be determined safely; new files are still installed.
If a source revision removes a requirement that a local customization still uses,
reconcile the reported sources and rerun the update if catalog validation fails.

Database migration backups remain under the installation's `state/backups/`.
Application/dependency replacement is not an atomic rollback transaction: failures
return nonzero, keep the installation marked incomplete, and require fixing the
reported problem and rerunning the script. Keep backups before switching versions.
Published shared changes automatically apply to every project's next launch. Local
file replacements remain in effect until reset. Source-only project revisions are
created without rebuilding or contacting remote dependencies. Running conversations
retain their captured configuration; managed chat checks rules between turns.
See [conversation memory](conversation-memory.md) for cross-agent history and policy refresh.

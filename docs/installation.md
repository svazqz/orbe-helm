# Installing OrbeHelm

Install from a clone on macOS or Linux:

```sh
./setup.sh
```

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

## Starting the server and creating orbes

In one terminal:

```sh
oh server start
```

The server stays in the foreground. Open `http://127.0.0.1:8765` for the management
UI and use Ctrl-C to stop it. `oh web` remains an equivalent foreground server
command. No daemon, launch agent, cron job, or automatic server startup is installed.

In another terminal:

```sh
oh server status
# Install the chosen agent CLI separately. Codex authentication is explicit:
oh auth --agent=codex
cd /path/to/project
oh --agent=codex --profile=developer --spec=python
# Add a stable task key to enable shared memory and reviewer/QA orchestration:
oh --agent=codex --profile=developer --spec=python --unique-key=APP-123
```

Real launches check `/healthz` before project registration, catalog publication,
building, or logical-orbe creation. The adapter checks again before allocating a
runtime, and delegation checks before allocating its child. The response must
identify this application root, this orbe-storage location, the same version and
protocol, a readable current database schema, and a published catalog. A random
listener on the port or another OrbeHelm installation does not satisfy readiness.
If the check fails, the command explains how to start the server and does not
start an orbe or authenticated model process.

The server is a prerequisite, while task state still uses the local SQLite and
stdio MCP architecture. A readiness check is not a permanent service lease:
stopping the server does not terminate an already running native conversation;
new launches and subsequent child delegations are blocked until it returns.

`oh server status` exits 0 when ready and 1 when unavailable or mismatched. Its JSON
includes the expected URL. Dry runs, configuration inspection, builds, authentication,
and other read-only diagnostics do not require a running server. A product-mode dry
run still requires prior project registration because it cannot register by writing.

Agent CLIs, provider access, MCP executables, and any required sign-in remain separate
prerequisites. OrbeHelm does not install those tools or start authenticated model
sessions during setup. Adapter isolation retains the documented alpha limitations.

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
preserving installed definitions, registry entries, examples, database history,
and orbe homes. Existing database upgrades make backups. Fresh bundled definition
changes are not silently applied over customized installed definitions. Setup
refuses an unmanaged nonempty application directory or a different orbe home for
an existing installation. Changing storage paths requires a separate migration.

`--offline` adds pip's `--no-index`; dependencies must already be available in the
application environment or pip's available local sources. It does not bypass
dependency checks. If setup fails after creating directories, fix the reported
prerequisite and rerun it with the same options. PATH updates occur only after
application initialization succeeds.

# OrbeHelm Alpha Architecture

The portable core resolves desired orbe configuration. Adapters translate it into host files and invocation arguments. Definitions remain authoritative; generated bundles are disposable outputs.

## Resolution and caching

Resolution reads base, profile, specialization, skillsets, and project context. It validates structural fields and instruction sections, follows local skill dependencies, rejects dependency cycles, and records source hashes. The resolved configuration includes original source content, a deterministic `composed_instructions` document, and a SHA-256 fingerprint. No Git repository or commit is required.

The CLI reads optional user defaults and skill aliases through `configuration.py` before portable resolution. Direct skill selections join definition dependencies. `remote_skills.py` reads verified installed trees or downloads public sources into bounded process memory; resolution does not install them. Builds persist missing trees under the dependency cache and record a URL-to-tree lookup. A cold dry-run may read remote content to calculate its hash but never creates or changes files. Source URLs, resource hashes, and executable flags participate in the resolved fingerprint; unselected aliases and configuration-file formatting do not.

The portable composer in `src/orbehelm/composition.py` applies a fixed common section template. Each source section appends by default or explicitly overrides the complete accumulated section. Empty additions inherit; empty overrides clear. Rendering emits each nonempty final section once, without authoring markers or per-source titles. Optional plain project and skillset context remains additive after these sections. Skill bodies and resource paths are appended during build. The same final instruction bundle is delivered by every adapter; adapters do not interpret section operations. See [Configuration](configuration.md#common-instruction-template) for the format and migration rules.

The fingerprint covers selected content, full skill resources, MCP definitions, project and source locations, generator version, and implementation bytes. A separate build identifier includes the selected adapter. Identical inputs reuse generated output. Relevant edits, resource changes, and implementation changes select a different build directory. Edits to unrelated profiles do not affect the selected configuration.

Builds verify cached output checksums and regenerate corrupted output. Local skill installations are also verified. A POSIX file lock serializes installation and generation within one root; staged directories are renamed after successful generation. Existing build versions remain available. Alpha does not automatically prune builds or orbe records.

Generated artifacts include merged instructions, selected skill resources, resolved configuration, agent-specific configuration, capability metadata, and an output-checksum manifest. No timestamps are included in deterministic build output.

## Adaptation

| Agent | Instruction delivery | MCP configuration | Authentication |
| --- | --- | --- | --- |
| Codex | Additional developer instructions in generated TOML | Per-orbe CODEX_HOME config | Explicit wrapper login store referenced by orbe homes |
| Claude | Append system prompt file CLI option | Explicit strict MCP config | Host CLI authentication |
| OpenCode | Instruction file referenced in runtime JSON | Runtime JSON configuration | Host CLI authentication |

Codex launches with a dedicated orbe home and without the shared daemon. The wrapper login flow uses its own private credential directory and does not import global config or credentials. Normal agent permissions remain in force; the wrapper does not pass approval-bypass flags.

Claude and OpenCode adapters have generated-output and mocked-launch coverage. Their binaries were unavailable during initial validation, so live compatibility remains unverified. Codex generated TOML has additionally been parsed by the installed CLI without starting a model conversation.

## Isolation boundaries

This is configuration separation, not a security sandbox or an exclusive-context guarantee. Managed policy, built-in capabilities, project files, environment variables, and host discovery may add context. OpenCode explicitly merges configuration layers. Inline skill delivery does not disable native skill discovery.

Every adapter reports this limitation. `--strict` fails before launch rather than making an unsupported guarantee. Full isolation requires additional host-specific discovery control and integration testing.

## Installed application and server readiness

`setup.sh` installs an independent code copy, private virtual environment, definitions,
registry, and operational database under `~/bin/orbehelm`. A versioned
`installation.json` selects `~/.orbehelm` for runtime storage. `layout.py` keeps
runtime paths separate from generated build and database paths; checkout deployments
without a manifest retain local `state/` storage. Capability checks validate native
homes against the selected runtime storage rather than the application root.

`oh server start` serves the local UI and `/healthz` in the foreground. `service.py`
uses bounded, timeout-limited, proxy-free loopback requests and rejects redirects,
version mismatches, and application/runtime identity mismatches. CLI launch checks
precede mutations; adapter and child-delegation checks guard the actual launch
boundaries. Dry runs remain independent of the server. Orchestration continues to
use the existing SQLite/stdio MCP services; server availability is a launch
prerequisite, not a transport rewrite or a process-lifetime guarantee.

## Orbe state

Each stable orbe records its identity (canonical project, agent, profile, specialization), build, working directory, launch count, status, and exit code under the selected runtime base in `orbes/`. Active pointers under `orbe-keys/` select the current orbe for each identity. A nonblocking POSIX lock is held for the child lifetime to prevent concurrent launches. `--new-orbe` rotates the active pointer without deleting prior state. Build changes do not rotate orbe identity. Initial prompts and environment values are not persisted in these records. Child agents may maintain their own histories and logs. An interrupted wrapper process can leave a stale running record; automatic reconciliation is not implemented.

Generated configuration records source content and absolute paths. Treat it according to the sensitivity of the source instructions. Credentials remain in the dedicated auth store or the host's own authentication system.

## Official references

- [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Claude CLI reference](https://code.claude.com/docs/en/cli-reference)
- [OpenCode configuration](https://docs.opencode.ai/docs/config/)
- [OpenCode MCP servers](https://opencode.ai/docs/mcp-servers/)

Documentation was consulted on October 27, 2026. Compatibility must be checked when host CLIs change. No provider SDK or model API is called by the wrapper itself.

Resume commands follow [Claude CLI documentation](https://code.claude.com/docs/en/cli-reference) and [OpenCode CLI documentation](https://opencode.ai/docs/cli/). Codex `resume --last` was verified through the installed CLI help without starting a model conversation. Claude uses a dedicated config directory; OpenCode uses dedicated XDG data, state, and cache directories. These hosts may require authentication in their runtime homes. Their live compatibility remains unverified.

## Project product layer

The optional migration cutover adds FastAPI/Jinja management views and SQLAlchemy
persistence backed by SQLite. `oh migrate` applies reviewed Alembic migrations
and imports historical orbe metadata without moving homes or reading credentials.
The portable resolver imports neither FastAPI nor SQLAlchemy. CLI and HTTP routes
call the same catalog/project/orbe application services.

Global source remains in definitions/registry. Exact content-addressed snapshots under
`state/revisions/` preserve source bytes and executable bits; catalog releases and
relational membership index them. Project configuration revisions pin one catalog,
project-context snapshot, aliases, and override revisions. Per-selection locks retain
resolved dependency versions; selected skill trees also have recoverable snapshots
independent of the installer cache. The database contains no credential values or
conversation bodies.

New derived artifacts live under `state/projects/<project-id>/builds/<agent>/<hash>/`.
The effective fingerprint normalizes physical catalog/context locations and includes
only selected source/dependency inputs and renderer implementation. Unrelated global
edits do not invalidate a selected build. Old top-level generated/ artifacts remain
historical references. Builds are immutable; per-orbe native homes remain mutable.

A product file lock coordinates edits, selection locks, and project adoption. The
catalog publisher writes snapshots before SQL references and journals UI working-file
materialization. Recovery refuses conflicting external edits rather than overwriting
them. Adoption resolves and stages already-realized configurations before atomically
committing one project pointer and associated build/selection records. Runtime homes
are refreshed only on launch, never by a web request.

Orbes retain existing UUIDs and compatible slot locks. Each new launch captures
its exact project revision/build in a separate SQL row. Imported old attempts have
unknown timestamps and configuration references. UI runtime status checks whether the
slot lock is held; this is wrapper coordination, not proof that no orphan child process
exists. Pending changes compare effective fingerprints when provenance is available.

Local HTTP uses bounded URL-encoded forms with double-submit CSRF tokens, loopback
Host/Origin checks, escaped templates, and restrictive content security policy. There
is no arbitrary file-reading endpoint, browser terminal, general command runner, or
remote deployment mode. Dedicated CSRF-protected MCP login routes run fixed agent
commands in matching native runtime homes. Bounded login jobs live in memory,
discard stdout/stderr, and terminate on cancellation, timeout, or app shutdown.
Model orbes and adapter isolation retain existing limits.

Library forms create one registration through catalog validation and the existing
publication journal; new-source recovery also handles files that did not previously
exist. Existing projects keep their selected releases. Project dependency assignment
updates only `orbehelm.project.json`, retains other snapshotted context, and stages
builds before committing a project revision. A per-project journal restores or
finishes interrupted context writes; conflicting external edits are preserved.

The product implementation passes its automated integration suite, including actual
Alembic upgrades/schema comparison and ASGI form workflows, on Python 3.13/macOS.
An isolated checkout also exercised CLI migration, backup, fake-agent orbe reuse,
and write-free resume previews. Listener binding and a real browser smoke test remain
unverified because of execution-environment limits. Read docs/validation.md for details.

## Capability removal

`dependency_usage.py` inspects shared declarative graphs and active pinned project
requirements without network calls or native credential reads. Current selection
locks, latest active native launch selections, transitive skill dependencies, alias
shadowing, and inherited origins participate in the usage check. Historical-only
builds do not block logical removal; unknown legacy provenance fails closed.

Shared removal holds the product lock, checks the expected catalog and clean working
sources, verifies current usage again, and publishes an immutable release without
the registration. The publication journal supports a null after-hash as a source
tombstone. Recovery removes only the expected old source file and preserves external
conflicting edits. Old snapshots and local skill source directories remain intact.

Project removal uses the same staged configuration and context-write journal as
project addition. It removes only a direct project requirement and re-resolves every
realized selection. Inherited or independently selected requirements remain. The
UI separates explicit additions from effective requirements and previews remaining
origins before submission. No schema migration, cascading edits, cache pruning,
credential revocation, or native conversation mutation is involved.

# OrbeHelm Configuration

All JSON definitions require `schema_version: 1`. Unknown fields are rejected. Instructions and local sources must remain within their declared root. Names use lowercase letters, digits, and hyphens and start with a letter.

## User configuration

OrbeHelm optionally reads `~/.orbehelmrc` as INI. Use `--config /path/to/file` or `ORBEHELM_CONFIG` to select another file; an explicitly selected missing file is an error. Configuration reads never create files. See [the fully commented example](../examples/orbehelmrc) for every supported default.

```ini
[ORBEHELM]
agent = codex
profile = developer
spec =
project =
skillsets =
skills =
strict = false

[SKILLS]
laravel = https://github.com/Jeffallan/claude-skills/tree/main/skills/laravel-specialist
```

| Default | Built-in value | CLI override |
| --- | --- | --- |
| `root` | Running checkout | `--root`; `ORBEHELM_ROOT` also overrides this file |
| `agent` | `codex` | `--agent` |
| `profile` | `developer` | `--profile` |
| `spec` | None | `--spec` |
| `project` | Current working directory | `--project` |
| `skillsets` | None | `--skillset` |
| `skills` | None | `--skills` |
| `strict` | `false` | `--strict` or `--no-strict` |

Explicit CLI selections replace configured defaults; they do not append. For example, `--skills=` clears the default skill list, and `--spec=` clears a default specialization. Definition-required dependencies remain additive. Root precedence is CLI, `ORBEHELM_ROOT`, user file, running checkout. Other defaults use CLI, user file, built-in values. Unknown options, duplicate sections or keys, invalid names, and invalid values fail clearly. Section names are case-insensitive. Use `[ORBEHELM]`, not INI's `[DEFAULT]` section.

Paths support `~`; relative paths resolve against the configuration file's directory. `[SKILLS]` aliases can point to local directories or public HTTPS sources. Explicit aliases take precedence over matching registry names. Only selected aliases affect resolution and build hashes.

Select individual skills without creating a named skillset:

```sh
oh --profile=developer --spec=php --skills=laravel --agent=codex
oh skills install laravel
oh skills list
```

Builds and normal launches install missing selected skills automatically. `skills install` also resolves and installs dependencies. Listing includes registry entries and configured aliases. Nothing is installed globally.

### Remote skill sources

Supported sources are public HTTPS endpoints returning a complete `SKILL.md`, GitHub `/tree/<ref>/<skill-directory>` URLs, and GitHub `/blob/<ref>/<skill-directory>/SKILL.md` or raw GitHub SKILL.md URLs. GitHub sources install the entire selected skill directory, preserving reference files and executable bits. Generic HTTPS endpoints install only the returned `SKILL.md`; use a GitHub folder or local directory when resources are required. Remote SKILL.md files must be UTF-8 and have `name` and `description` frontmatter. Private repository authentication and arbitrary archive URLs are not supported.

The installer downloads data without executing scripts. Downloads have a 30-second timeout and a 32 MiB response limit; selected archive resources are limited to 64 MiB and 2,048 files. Unsafe paths, symlinks, duplicate files, malformed archives, and URLs with embedded credentials are rejected. HTTP is not supported.

Installed trees remain under `state/skills/<tree-hash>/`; `state/skills/by-source/` maps source URLs to verified installed trees. This is a dependency cache, not orbe tracking. Repeated builds use the verified installation offline. A changed URL selects a new source. To request upstream changes from a mutable branch URL, remove its source lookup and installed tree before rebuilding, or preferably use a new commit-specific URL. OrbeHelm does not silently update installed remote skills.

Use a commit-specific URL to fix the upstream revision. An optional `#sha256=<tree-hash>` URL fragment pins the complete content-and-executable-bit digest reported by resolve or installation. A mismatch fails. Registry entries may also use an HTTPS `source` and their existing `sha256`, `skills`, and `mcp` fields.

Dry-run never installs or writes files. If a selected remote skill is not cached, it reads the source into memory to determine the same content hash a build will use. A cold remote dry-run therefore requires network access and can fail if the source is unavailable. Warm dry-runs use the verified dependency cache offline. The printed command can reference generated files that do not yet exist.

## Profiles and specializations

A layer has the following shape:

```json
{
  "schema_version": 1,
  "instructions": ["definitions/profiles/developer.md"],
  "skills": ["testing"],
  "mcp": ["docs"]
}
```

Paths in reusable definitions are relative to the orbehelm root. Base configuration lives at `definitions/base/config.json`. A profile named developer lives at `definitions/profiles/developer.json`. Its PHP specialization lives at `definitions/specializations/developer/php.json`.

Skill and MCP lists are additive. A layer cannot remove another layer's required skill or MCP server. Repeated instruction paths and skill names are deduplicated. Source reading order is preserved; user-selected skillsets are deduplicated and processed in alphabetical order.

## Common instruction template

Base, profile, and specialization instruction files must use [the common template](../definitions/TEMPLATE.md). Copy it, change the document title, and fill the relevant sections. All seven headings must remain in this order, including empty sections:

1. Purpose and judgment
2. Responsibilities
3. Scope and autonomy
4. Workflow
5. Execution and evidence
6. Communication
7. Completion criteria

The first nonempty line is `<!-- orbehelm:sections:v1 -->`, followed by one `# Document Title`. The title identifies the source for authors and is not injected. Do not add preambles such as "Requires the shared base instructions"; base selection is handled by the resolver. Use `###` or deeper headings for subsections. Fenced code blocks may contain example headings without affecting composition.

Each section heading supports two modes:

| Source heading | Effect |
| --- | --- |
| `## Responsibilities [append]` | Add the body after inherited content in this section. |
| `## Responsibilities` | Same as `[append]`. |
| `## Responsibilities [override]` | Replace all content accumulated in this section with this body. |
| Empty section with `[append]` or no mode | Inherit unchanged; add nothing. |
| Empty section with `[override]` | Clear this section. It is omitted unless a later layer adds content. |

Composition applies base, profile, specialization, alphabetically ordered skillsets, then project context. Within a layer, instruction files follow their manifest order. Overrides replace the entire section, including earlier additions, and later additions can extend the replacement. Overrides do not affect any other section, skills, MCP servers, host policy, or tool permissions. Review overrides carefully because a replacement can remove shared behavioral safeguards.

The final document has one `# Agent Instructions` title and at most one heading for each common section, in canonical order. Empty final sections are omitted. Source titles, mode suffixes, and the format marker are removed. No placeholder or null value is substituted for an empty body. Instructions are authored as concrete Markdown, not placeholder references to another document.

`oh resolve` exposes the result in `composed_instructions`, alongside original instruction content and source hashes for provenance. Builds use this same result, then append selected skills and resource paths. Composition resolves explicit replacement, not natural-language contradictions: conflicting additions still require a source edit.

Missing, repeated, reordered, or unknown section headings, unsupported modes or versions, authoring preambles, and unclosed code fences fail resolution with the source path. Existing custom base/profile/specialization Markdown must migrate to the common template; it is not silently concatenated.

Optional project and skillset instruction files may use the same marker and template to participate in section composition. For compatibility, unmarked plain Markdown in those layers remains additive context appended after the common sections, in source order; it cannot override a section. Selected `SKILL.md` files retain their native skill format and are appended after context.

## Skillsets

`definitions/skillsets/quality.json` selects the bundled testing and review skills. Add further named skillsets using the same layer shape. Commas select multiple skillsets:

```sh
oh --profile=developer --spec=php --skillset=quality,another --dry-run
```

`another` must exist. The bundled skills are intentionally small examples; they are not imported copies of globally installed skills.

## Skill registry

A local skill registration at `registry/skills/testing.json`:

```json
{
  "schema_version": 1,
  "source": "examples/skills/testing",
  "skills": [],
  "mcp": []
}
```

The source directory must contain UTF-8 `SKILL.md`; resources and scripts are copied with it. Symlinks are rejected. Resource changes and executable bits participate in the content hash. Skill scripts are never run by the installer. Selected SKILL.md content is included in the merged instructions with the generated resource directory. The host agent can subsequently use those resources within its own permissions.

An optional `sha256` field pins the complete skill tree digest shown by `oh resolve` or `oh skills install testing`. The digest covers a canonical sorted mapping of relative filenames to SHA-256 content hashes and executable flags. A mismatching pin fails instead of updating silently.

`skills` declares transitive skill dependencies. They are resolved before dependents; cycles fail with an error. `mcp` adds required MCP registry entries. Builds install the complete selected dependency graph. Local registry source paths stay inside the checkout; user-configured local aliases explicitly select a directory relative to the user configuration file or an absolute directory. Remote sources follow the installation and caching rules above.

## MCP registry

The included `registry/mcp/docs.json` registers the official OpenAI documentation endpoint but is not selected by default. Select it by adding `docs` to a layer's `mcp` list.

A local server example:

```json
{
  "schema_version": 1,
  "type": "stdio",
  "command": "my-mcp-server",
  "args": ["--stdio"],
  "env": {"SERVICE_TOKEN": "SERVICE_TOKEN"}
}
```

`env` maps server variable names to host environment variable names, never literal secrets. The Codex alpha adapter requires identical names on both sides. Claude and OpenCode adapters emit their documented environment references. Missing required variables are reported before launch. Keep tokens out of arguments and URLs, which appear in generated files.

An HTTP server requires `type: http`, a URL, and no command fields. Portable HTTP credential fields are not supported in alpha; native OAuth sign-in is available through the project UI. MCP registration configures a server; it does not install its executable. MCP processes are started by the agent, not during build or dry-run.

### Project dependency inventory

The project web view has separate **Skills** and **MCP servers** tabs for configuration
selections already realized by a normal build, launch, or UI dependency assignment.
Choose a configuration and an agent to inspect its
pinned dependencies. This inventory covers OrbeHelm-managed dependencies; it does
not enumerate host-native plugins or built-in skills.

Skill details show the full instructions, resource filenames, original source,
content digest, and a top-level scalar `version` from frontmatter when declared.
**Check for skill updates** and **Check authentication** explicitly check sources or host metadata and store
timestamped observations inside `state/projects/<project-id>/capabilities/`.
Rendering a page does not initiate these checks. Skill observations are shared
across agents; authentication observations are scoped to an agent and native runtime.

For local registry skills, update checks compare with the latest published catalog.
Local aliases compare with their original source directory. Remote skills compare
with a fresh download of their selected URL, bypassing the dependency cache and
content pin for observation only. A different digest means **Update available**;
it does not establish semantic version ordering. Immutable commit URLs remain tied
to that commit; checks do not search for new release tags. Failed checks show
**Unknown**. No check replaces pinned trees, edits a selection lock, or adopts a release.

Codex authentication checks invoke `codex mcp list --json` using the matching active
orbe's `CODEX_HOME` and project directory. Only matching server transports and
allowlisted metadata reach the UI. An OAuth login is displayed as **Authenticated**;
a bearer token is **Credential configured**, since validity has not been tested.
No login, unsupported status reporting, disabled servers, and unknown status remain
distinct. These are host-reported observations, not server access tests. A missing
runtime, unavailable CLI, malformed output, timeout, or a different endpoint yields
**Unknown**. Raw CLI output and credential contents are never displayed or stored.

Claude and OpenCode authentication status adapters are not implemented yet. Their
entries display **Unknown** with that limitation; this view cannot currently establish
whether those runtimes are authenticated. The web UI starts no model conversation.
The Codex metadata command was verified in an isolated verification home;
authenticated status and Claude/OpenCode live integration remain unverified.

Portable configuration fingerprints and skill/MCP selection locks exclude agent
choice. Generated adapter files, native conversation slots, and authentication observations
remain agent-specific. Changing agent reuses the dependency selection and does not
merge incompatible runtime files or conversation histories.

### Adding and enabling capabilities from the UI

Start at **Projects** and open a project. Its **Overview** links to the common tasks;
**Skills**, **MCP servers**, **Instructions**, **Updates**, **Orbes**, and **History**
separate everyday configuration from advanced editing and rollback.

Use the sidebar's shared **Skills** or **MCP servers** page to add a registration.
Skill sources accept public HTTPS URLs or existing checkout folders under `skills/`
or `examples/skills/`. A skill folder must contain `SKILL.md`. The form can also name
existing skill and MCP dependencies. MCP forms support remote HTTP endpoints and
local stdio commands, arguments, and environment variable name mappings. They never
accept literal credential fields, install MCP executables, or execute skill scripts.
Invalid forms preserve entries and explain the error. Names must be unique.

Saving publishes a validated shared library version and leaves project pins unchanged.
When adding from a project, the next screen is its **Updates** preview. Apply that
version, then choose **Enable an existing skill/MCP server** in the relevant tab.
Enabling an item updates the project's `orbehelm.project.json` and commits a validated
project revision without starting a model conversation. External manifest edits cause
a conflict rather than being overwritten; failed preparation restores the previous
manifest and configuration. Dependencies apply to every profile in that project.

### MCP browser sign-in

On a project's **MCP servers** tab, select an agent configuration. For HTTP servers,
**Sign in with [agent]** invokes its dedicated OAuth command using the matching active
native runtime and generated configuration. It runs `codex mcp login`, `claude mcp login`
with the explicit MCP configuration, or `opencode mcp auth` with runtime config and XDG
directories. The agent CLI owns browser callbacks and credential storage. OrbeHelm does
not read credentials or capture command output. This preserves the adapters' existing
isolation limits; it does not establish exclusive isolation.

Complete the provider flow in the browser window opened on this computer, then refresh
the progress page. Duplicate starts reuse an active job for the same server/runtime.
Jobs expire after three minutes and can be cancelled; shutting down the UI terminates
unfinished children. Job status is in memory and is lost when the UI restarts. A successful
command is reported as command completion, not proof of continued server access.

Sign-in requires an installed CLI and a matching runtime that has loaded this server.
If those prerequisites are missing, the server card explains the next step. Local stdio
servers use their configured environment variables instead. CLI variants that need an
interactive terminal or manual callback pasting require terminal sign-in. Codex command
help was verified in an isolated home. Fake-child and ASGI tests cover launch scoping,
completion, failure, timeout, cancellation, and shutdown; actual provider OAuth and
Claude/OpenCode CLI compatibility still require manual integration verification.

## Configuration scope and removal rules

See [Configuration scopes, updates, and removal](configuration-scopes-and-removal.md)
for the distinction between shared registrations, profile requirements, project-wide
additions, and project profile instruction overrides. It also records the approved
removal policy. Project tabs can remove explicit additions; shared library removal
is blocked while active references exist. Project-origin
registration forms retain project navigation while explicitly creating shared entries.

## Project context

Put `orbehelm.project.json` in the directory passed through `--project`. It uses the layer shape above, but its instruction paths resolve relative to that project. Skill and MCP names still resolve through the wrapper registry. Parent directories are not searched for this wrapper file.

The `examples/project` directory provides a working example. Host-native project instruction discovery is separate and may still apply.

## Product configuration lifecycle

After `oh migrate`, global source files are drafts for an immutable catalog.
Normal build/run publishes a validated catalog if its source content changed. This
makes an update available; it does not change any existing project's selected release.
Use the local UI or `oh projects preview` and `projects update` to adopt a whole
release. `--release=<id>` selects a specific release. `definitions history` lists
release IDs; `definitions diff --revision=<old> --release=<new>` shows source differences.

New projects are registered on their first normal build/run, or explicitly with
`projects register --project=<directory>`. The initial revision captures the current
published release, project context, and user skill aliases. Existing project IDs are
keyed by canonical path; relocating a project is not supported as an automatic rename.
Read-only resolve/doctor/dry runs require prior registration and do not publish drafts.

The selected project's `orbehelm.project.json` and referenced instruction files are
snapshotted. Local alias trees are preserved; remote dependencies are locked when a
selection is first realized. `projects refresh` explicitly captures changed project
context and aliases. Other projects' configurations remain untouched.

The UI's project profile override editor accepts the common seven-section template.
Operations are applied after global profile instructions and before specialization.
Only instruction sections can be changed through this editor; inherited skill/MCP
requirements remain additive. An override retains hashes for its original profile
sections. An upstream change to a locally touched section blocks adoption until
explicitly resolved by revising/removing the override. Rollback through
`projects rollback --revision=<project-configuration-id>` selects the complete previous
project configuration and leaves native conversation histories intact.

Schema migrations are separate from definition releases: maintain reviewed Alembic
scripts under `src/orbehelm/product/migrations/versions/`; never generate them on launch.
The UI requires local Host/Origin and CSRF validation. Do not expose it remotely.

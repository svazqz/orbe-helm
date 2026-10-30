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

An HTTP server requires `type: http`, a URL, and no command fields. Portable HTTP credential fields are not supported in alpha; native OAuth sign-in is available through `oh projects login-mcp`. MCP registration configures a server; it does not install its executable. MCP processes are started by the agent, not during build or dry-run.

## Typed CLI definition management

Shared sources automatically apply to every project on its next launch. The optional
web editor manages only shared definitions/history. Project-local replacement/reset
and project operations use the CLI:

```sh
oh get definition.profile.developer
oh get definition.profile.developer --json
oh override definition.profile.developer --from-file=./developer.md
oh reset definition.profile.developer
oh set definition.profile.developer --from-file=./developer.md --global
```

`--file=<owned-path>` selects one manifest, instruction, or registered resource. Names
are typed as `definition.base`, `definition.profile.<name>`,
`definition.specialization.<profile>.<name>`, `definition.skill.<name>`,
`definition.skillset.<name>`, or `definition.mcp.<name>`. Multiple instruction files
require explicit selection. Default scope is the current project; `--project` selects
another directory. `get --global` reads shared content. `override`/`reset` are local
operations, while shared edits use `set --global`.

`add --from-dir` takes `definition.json` plus UTF-8 resources. Instruction paths inside
the package are relative to that package and are rewritten to the canonical owned
source directory. Skill packages contain SKILL.md and a skill registry manifest.
Single-file MCP/skillset additions support `--from-file`. Repeated adds and dependency-
invalid removals fail. A local `remove` masks/removes that target only in the selected
project; reset clears the decision. Mutations validate candidate source snapshots and
append history. `--expected=<revision>` optionally guards a caller's observed state;
all mutations also recheck their captured revision under the product lock.

Use `history`, `diff --revision=<id>`, and `rollback --revision=<id>` with the same target.
Shared rollback publishes restored bytes as a new revision; historical sources remain
immutable. Project-local rollback creates local replacements on the current shared
catalog. Read [scope and removal rules](configuration-scopes-and-removal.md).

## Project context and management

`orbehelm.project.json` uses the layer shape above; paths resolve against the selected
project directory. Parent directories are not searched. Project context and user skill
aliases are snapshotted. Run `oh projects refresh` after externally editing them.
Shared source publication does not overwrite project context or local replacements.

`projects register/show/history` manage project identity and provenance.
`projects add-skill/remove-skill/add-mcp/remove-mcp` edit explicit project additions,
preserving inherited and independent requirements. `projects capabilities` inspects
realized dependency selections after a normal build/launch; it does not implicitly
start a check. A newly inherited revision is realized when first used.
`projects check-capabilities` explicitly checks skill update metadata and supported
native authentication metadata. These observations do not validate model access or
MCP connectivity. Claude/OpenCode authentication status remains unsupported/unknown.
`projects login-mcp <name> --agent=<agent>` explicitly runs native sign-in using an
available matching runtime and leaves the provider CLI responsible for credentials.

The SQLite database and immutable source revisions retain historical launch inputs.
Shared changes append source-only effective project revisions without builds or remote
downloads. Invalid local dependencies block their affected launch instead of silently
using an older shared release. Existing legacy section overrides remain readable; new
typed overrides replace whole files, and reset clears legacy profile overrides too.

Old projects preview/update/rollback commands remain compatible historical operations;
normal shared source updates no longer require them. Schema upgrades remain separate,
reviewed Alembic migrations run by setup/update/migrate, never generated during launch.

## Conversation freshness

The policy digest covers effective instructions, selected skill hashes, and MCP
configuration. Unrelated catalog changes do not require a new native conversation.
Changed policy starts a fresh native conversation under the same logical work identity
and preserves captured history. Managed chat also supports switching Claude/Codex with
shared memory and an explicit bounded handoff. Read [conversation memory](conversation-memory.md)
for exact-ID resume, capture coverage, private storage, and context limitations.

### Memory default

`memory = true` (the default) or `memory = false` is supported under `[ORBEHELM]`.
Launch flags `--memory` and `--no-memory` override this value. Memory-off mode keeps
native agent history and requires a manual instruction reread after definition
changes. See [memory modes](knowledge-memory.md#optional-native-continuity).

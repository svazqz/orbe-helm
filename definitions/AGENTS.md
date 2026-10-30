# Definition authoring

Use this guide when a plain agent is opened in `definitions/` to create or change OrbeHelm capabilities. Read the repository's `../AGENTS.md` as well. All paths below are relative to the checkout root unless stated otherwise; run commands from that root, not from `definitions/`.

Definitions are the source of truth. Edit source manifests and instruction files, never generated adapter files, snapshots, caches, or runtime records. Keep durable content in English. Preserve `legacy/`. Do not read credentials, change global agent configuration, or start an authenticated model session for authoring checks.

## Choose the right scope

| Need | Source files | Selection |
| --- | --- | --- |
| Behavior shared by every profile | `definitions/base/config.json`, `definitions/base/instructions.md` | Always inherited; change cautiously |
| A role, such as developer or reviewer | `definitions/profiles/<profile>.json` and `.md` | `--profile=<profile>` |
| Expertise within an existing role | `definitions/specializations/<profile>/<spec>.json` and `.md` | `--profile=<profile> --spec=<spec>` |
| A reusable skill | `skills/<skill>/SKILL.md` plus `registry/skills/<skill>.json` | `--skills=<skill>` or a layer requirement |
| A named bundle of skills, MCP servers, or instructions | `definitions/skillsets/<name>.json` | `--skillset=<name>` |
| An MCP server registration | `registry/mcp/<name>.json` | A layer's `mcp` list |
| Context for one target project | That project's `orbehelm.project.json` and instruction files | `--project=<directory>` |
| Machine-specific agent or selection defaults | User-selected INI configuration | `--config=<file>` or `ORBEHELM_CONFIG` |

Skills and MCP registrations belong outside `definitions/`; do not invent a `definitions/skills` registry. Prefer extending the narrowest suitable scope. A shared specialization should describe reusable expertise, not one computer's paths, installed tools, or secrets. Agent choice is a user/CLI selection, not a definition field. Do not change user defaults as a side effect of authoring.

## Create a profile, specialization, or skillset

1. Inspect the closest existing example and `docs/configuration.md`. Names must match `[a-z][a-z0-9-]*`. Confirm referenced profiles, skills, and MCP registrations exist.
2. Create the manifest at the path in the table. All layer manifests have this shape; these are the only supported fields:

   ```json
   {
     "schema_version": 1,
     "instructions": ["definitions/specializations/developer/example.md"],
     "skills": [],
     "mcp": []
   }
   ```

   Replace the instruction path with the actual new file. Paths are relative to the checkout root, not to the manifest. Empty lists are valid. A specialization needs its parent profile; a skillset can use `"instructions": []` when it only groups dependencies.
3. Copy `definitions/TEMPLATE.md` for each new instruction file. `definitions/specializations/TEMPLATE.md` is also available for specializations. Replace the title and write concrete instructions in the relevant sections; retain empty sections. Do not copy inherited base/profile behavior unnecessarily.
4. Keep the first nonempty line `<!-- orbehelm:sections:v1 -->`, then one `# Title`, then exactly these seven headings in order:

   ```markdown
   ## Purpose and judgment [append]
   ## Responsibilities [append]
   ## Scope and autonomy [append]
   ## Workflow [append]
   ## Execution and evidence [append]
   ## Communication [append]
   ## Completion criteria [append]
   ```

   Use `###` or deeper for subsections. Do not add an authoring preamble. `[append]` extends inherited content; `[override]` replaces the entire accumulated section, and an empty override clears it. Use overrides only when replacement is intended and review what they remove. An unqualified heading means append.

Composition order is base, profile, project profile override when present, specialization, alphabetically ordered selected skillsets, then project context. Skills and MCP dependencies are additive; a later layer cannot remove earlier requirements. Selected skills retain their native `SKILL.md` format. Optional project/skillset instruction files may use plain Markdown for additive context, but prefer the common template for new structured instructions.

## Create a skill

Create `skills/<skill>/SKILL.md` with UTF-8 content and frontmatter:

```markdown
---
name: example
description: Explain when this skill should be used.
---

# Example

Write the reusable workflow here.
```

Place any required resources beside it. Register the directory in `registry/skills/<skill>.json`:

```json
{
  "schema_version": 1,
  "source": "skills/example",
  "skills": [],
  "mcp": []
}
```

Use the actual skill name and directory. `skills` declares transitive skill dependencies; cycles are invalid. `mcp` declares required servers. Local source paths must stay inside the checkout; symlinks are rejected. Scripts are resources, never installation hooks. An optional `sha256` pins the complete tree digest, including executable bits; do not guess it. Public HTTPS and GitHub skill sources are also supported; consult `docs/configuration.md` for supported URLs and pinning. Remote resolution may access the network; prefer local examples for offline checks.

## Register an MCP server

Create `registry/mcp/<name>.json`, then add its name to the appropriate layer's `mcp` list. A registration alone does not enable a server or install its executable.

```json
{
  "schema_version": 1,
  "type": "stdio",
  "command": "my-mcp-server",
  "args": ["--stdio"],
  "env": {"SERVICE_TOKEN": "SERVICE_TOKEN"}
}
```

`env` maps server variable names to host environment variable names, never secret values. Identical names on both sides work with the Codex alpha adapter. For an HTTP server use `schema_version`, `type: "http"`, and `url`; omit command, args, and credential fields. Keep credentials out of URLs and arguments. Do not start a server or authenticate just to validate a definition.

## Validate and hand off

Inspect the resulting diff and validate the new selection using the portable resolver directly. This checks working source files without needing a running server, a registered project, or an agent CLI. For example, from the checkout root with Python 3.11 or later:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from orbehelm.core import resolve

root = Path.cwd()
result = resolve(root, profile="developer", spec="python", project=root)
print(result["composed_instructions"])
PY
```

Replace the profile/spec with the new selection; omit `spec` for a profile alone. Pass `skillsets=("example",)` or `skills=("example",)` to check those additions. Check the composed text for duplication, contradictory additions, and unintended overrides. Validate every new specialization or bundle, including its dependencies. Run `python3 -m unittest discover -s tests -v` after behavior changes. Report checks actually performed and any unresolved external prerequisites.

For CLI checks, use a disposable HOME and explicit configuration stored inside this checkout. Use `--agent=claude` when Claude is requested; never assume Codex is installed. `oh --dry-run` starts no model session, but operates on the project's published effective configuration and requires prior project registration. It does not publish edited source drafts, and cold remote skill checks may use the network. Do not register or update the user's real project merely for verification.

Explain activation separately: normal build/run or explicit publication validates shared
source changes and makes them effective for every project's next launch. Local file
overrides remain in effect until reset. No running web server or per-project adoption
is required. Refresh externally changed project context with `oh projects refresh`.
Changed effective rules start a fresh native conversation; managed `oh chat` retains
captured history and supplies a bounded handoff. Authoring alone does not synchronize
another installation: deliver its source changes and run the installation/update
workflow there. See `docs/configuration.md`, `docs/conversation-memory.md`, and
`docs/installation.md` for the current lifecycle.

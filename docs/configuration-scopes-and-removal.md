# Configuration scopes, updates, and removal

## Scope

| Scope | Behavior |
| --- | --- |
| Shared base/profile/specialization/skillset | Current shared definition applies on the next launch selecting it |
| Shared skill/MCP registration | Makes the capability available; requirements or explicit selections enable it |
| Project context | Snapshotted instructions and additive dependencies from `orbehelm.project.json` |
| Project file override | Replaces an owned shared source file for that project until reset |
| Legacy project profile override | Existing section-level replacement/addition, retained for compatibility |
| Launch selection | Profile, specialization, skillsets, skills, and task identity |
| Conversation memory | Captured history/checkpoint independent of agent choice |
| Native runtime | Adapter-specific conversation, permissions, and authentication state |

Shared publication appends effective source revisions for registered projects without
manual adoption. Other projects' context, local replacements, and aliases remain
unchanged. Running native conversations retain their captured rules; managed chat
checks for new rules between turns. Changed policy starts a new native conversation
with historical context; it does not overwrite the old transcript.

## File overrides and reset

```sh
oh get definition.profile.developer
oh get definition.profile.developer --global
oh override definition.profile.developer --from-file=./developer.md
oh reset definition.profile.developer
```

Default scope is the current project; `--project` selects another directory. Shared
edits use `oh set ... --global`, or the editor. `override` and `reset` reject `--global`.
A local replacement wins for that file; other shared files continue receiving updates.
Reset inherits the current shared version, not the version first copied locally.
`--file=<owned-path>` selects a particular manifest/instruction/resource. Multiple
instruction files require an explicit file selection.

All layer dependencies remain additive. A file override may change a profile's local
manifest, but it cannot bypass another layer's requirements or catalog validation.
Invalid local dependencies block the affected configuration; they never silently
select an older shared release. Legacy section overrides apply after profile
instructions and before specialization and are removed by a profile reset/replacement.

## Adding and removing definitions

Use `oh add <target> --from-dir=<package>` for a package with `definition.json` and
UTF-8 resources. Profiles and specializations require valid structured instruction
files. Skill packages contain `SKILL.md` plus a registry-shaped `definition.json`;
resources are installed as local authoritative skill sources. Single-file MCP/skillset
manifests also support `--from-file`.

`oh remove <target>` removes/masks the definition in the current project. Reset clears
that local decision. The resulting complete catalog is validated: removing a required
skill/MCP server is rejected until references are removed. Removing a project-local
addition does not delete the shared source. Historical snapshots are retained.

Shared skill/MCP removal additionally checks current shared and active project usage,
including transitive requirements and explicit launch selections. Usage blocks removal;
no cascading edits or credential revocation occur. The optional editor provides shared
usage review. Historical-only references do not block retirement. Unknown/corrupt
active provenance fails closed.

Project dependency references have separate additive commands:

```sh
oh projects add-skill testing
oh projects remove-skill testing
oh projects add-mcp docs
oh projects remove-mcp docs
```

These edit the explicit project additions in `orbehelm.project.json` and preserve
inherited requirements and independently selected dependencies. Project context
journals recover interrupted writes without overwriting unrelated external edits.

## History and rollback

`oh history <target> [--global]` lists immutable revisions. `oh diff <target>
--revision=<id>` compares the chosen revision to current content. `oh rollback <target>
--revision=<id> --global` restores that target as a new shared publication. The editor's
shared release view can restore the complete catalog. Other projects automatically
inherit restored shared files; project-local replacements remain in effect.

Project-local rollback restores the target's effective historical files as a local
overlay on the current shared catalog. It does not rewind the global release. Older
`projects rollback` remains a historical configuration operation for compatibility;
use typed reset/rollback for normal source management. History rollback never rewinds
repository changes made by an agent, revokes credentials, or deletes conversations.

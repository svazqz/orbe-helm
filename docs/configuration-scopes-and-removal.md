# Configuration scopes, updates, and removal

Status: The user approved the blocking removal policy. The behavior below is implemented and covered by integration tests.

## Current scopes

| Scope | What it owns | Where it applies |
| --- | --- | --- |
| Shared registry | Skill source/resource declarations and MCP connection definitions | Makes an item available; registration alone enables nothing |
| Shared base | Common instructions and required skills/MCP servers | Every resolved configuration |
| Shared profile | Role instructions and required skills/MCP servers | That profile in projects adopting this catalog release |
| Shared specialization | Additional expertise and required skills/MCP servers | Its parent profile plus that specialization |
| Shared skillset | Named bundle of requirements and optional instructions | Configurations explicitly selecting that skillset |
| Project context | Project instructions and extra skills/MCP references in `orbehelm.project.json` | Every profile/configuration of that project |
| Project profile override | Instruction section changes for a named profile | That profile in this project; it currently cannot override skill/MCP requirements |
| Launch selection | Selected profile, specialization, skillsets, and additional skills | That resolved configuration |
| Agent runtime | Configuration rendering, native history, authentication state | One native agent runtime; portable dependency identity excludes the agent |

The project configuration dropdown selects which effective configuration to inspect. It does not limit project additions to that profile. There is currently no project-local, profile-specific skill/MCP override model.

Registering a new item from inside a project still creates a shared registry entry. The project context is retained for navigation and the return workflow. The item must then be available in the project's selected catalog and explicitly enabled there. This registration form is not a private project-only definition editor.

## Merge rules

Resolution applies base, profile, project profile instruction override, specialization, selected skillsets, then project context. The optional project instruction override occurs immediately after its shared profile and before specialization. Explicit skill selections are also included.

Instruction sections append unless their source declares `[override]`; override replaces the accumulated body of that section. A later layer can append to or replace it again. Plain unmarked project/skillset Markdown adds context and cannot replace structured sections. Skill instructions and resource paths are appended after composed context during build.

Skill and MCP requirement lists are additive and deduplicated. Skill dependencies are resolved transitively, including their MCP dependencies. Project additions cannot subtract inherited requirements. A repeated name does not create a separate project copy of the shared definition. User skill aliases can override registry source selection by name and are preserved in the project configuration snapshot.

## What happens during shared updates

Publishing shared changes creates a new immutable catalog release. It does not change a project's selected release or any running agent.

When the user applies an update to a project:

1. The project selects the target shared catalog release.
2. Its project context snapshot, aliases, and profile instruction overrides remain selected.
3. Previously realized selections are validated against the candidate configuration before commit.
4. An upstream change to a profile section touched by a project override blocks adoption until explicitly resolved.
5. Missing or invalid requirements block adoption; validation is not bypassed.
6. The project pointer changes only after successful preparation. A running agent retains its launch configuration until the next launch/resume.

Preserving a reference does not mean permanently freezing its shared definition. For example, a project addition named `playwright` remains selected after adoption, but a changed shared `playwright` command or endpoint in the target catalog becomes effective. Changed local skill resources likewise select new content. Remote skill source caches and content locks retain their existing update/pinning rules; a new catalog release does not automatically discover new upstream tags or force-download an unchanged source URL.

Normal catalog adoption does not refresh externally edited project files or skill aliases. Explicit project-context refresh captures those changes separately. MCP credentials remain owned by the native CLI; a changed endpoint may require signing in again.

## Removal policy (approved and implemented)

### Project removal

- Label the action **Remove project addition**.
- Remove only that name from the project's explicit `skills` or `mcp` list.
- Preserve shared registry entries, other projects, credentials, immutable history, and running orbes.
- Re-resolve requirements before commit. If an inherited layer or another selected skill still requires the item, keep it effective and explain its remaining origin.
- Show direct project additions separately from inherited/transitive requirements. Do not present an inherited requirement as removable from this project under the current additive model.
- Removing a skill does not automatically remove independently selected MCP servers or other direct project additions. Its exclusively transitive dependencies disappear naturally when nothing else requires them.

### Shared library removal

- Label the action **Remove from shared library**; show usage before enabling it.
- Block removal while the item is required by a current shared definition, another registered skill, or an active project configuration. Usage must include transitive requirements and realized launch selections, not merely top-level project JSON lists.
- Show the blocking profile/skillset/skill/project references. The user explicitly removes or replaces those references first.
- When unused, publish a new catalog release without the registration. Do not cascade changes to projects or profiles.
- Keep old catalog/project snapshots, builds, native conversations, and credentials. Historical references alone do not block logical removal; this action is not storage purging or credential revocation.
- Do not introduce a project-level disable mask for inherited requirements without a separate policy decision, since that would change the authoritative additive merge semantics.

### Rejected alternative for shared removal

Allow removal from future catalog releases even when pinned projects still use the item. Those projects keep their existing snapshots; adopting a release that lacks a still-required registration is blocked until the reference is removed or replaced. References inside the target shared catalog must still be resolved before publication. This permits retirement without cascading edits but requires clearer update-conflict handling.

### Approved decision and usage boundaries

Shared removal is blocked while active references exist. It does not cascade changes or purge credential/history storage. Project removal follows the existing additive semantics.

The shared confirmation page is available through **Shared library → Skills/MCP servers → Review usage & remove**. A blocked page lists current source and project references and offers no removal button. Usage is rechecked under the product lock during the POST, including when the library version did not change after the preview.

Project tabs show **Explicit project additions** separately from effective requirements. **Remove project addition** previews remaining origins and applies only to the named entry in `orbehelm.project.json`. The effective cards identify whether the requirement is inherited and show its origins. Source links use the project's pinned release.

Usage inspection reads the latest shared definition graph and each active project's pinned context, base requirements, realized selections, local profile override roles, and latest active native launch selection. Aliases shadow registry definitions and their dependency declarations, matching portable resolution. Inspection does not download skills or inspect native credential files. Historical build rows alone do not block removal. Missing/corrupt provenance blocks removal; unknown legacy launch selections are listed as blockers until a known launch is recorded.

Removal publishes a new catalog/project revision through existing recovery journals. An interrupted shared source deletion is completed only when the working file still matches its expected hash; conflicting external edits are preserved. Local skill source directories remain on disk. No action changes other projects, native runtime homes, or authentication state.

## Implemented navigation correction

Project-origin registration uses `/projects/<project-id>/skills/new` or `/projects/<project-id>/mcp/new`, keeping Projects highlighted and displaying the project breadcrumb. The form explicitly states that the registration is shared and does not enable the item. Legacy query-parameter entry links redirect to the contextual route. Global entry routes remain available under `/skills/new` and `/mcp/new`.

## Implementation references

- [Portable resolution](../src/orbehelm/core.py)
- [Project configuration adoption and additions](../src/orbehelm/product/projects.py)
- [Catalog publication](../src/orbehelm/product/catalog.py)
- [Web routes](../src/orbehelm/product/web.py)
- [Configuration reference](configuration.md)

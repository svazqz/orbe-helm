# Agent Instruction Architecture

## Source files and reuse

Maintain shared behavior in BASE.md, professional responsibilities in profiles, and technical constraints in specializations. Each rule has one authoritative source. Add a shared module only when multiple compositions actually need a distinct optional capability; keep mandatory shared rules in BASE.md.

A specialization adds technical constraints without copying or replacing the Developer profile. Composition is explicit inclusion, not object-oriented inheritance. Do not expect an agent to automatically follow Markdown links or imports.

## Directory structure

- README.md: entry point and usage.
- BASE.md: shared instructions for all profiles.
- profiles/: Developer, Reviewer, QA, and Electronics Engineer.
- specializations/: optional technology extensions and the extension template.
- compositions/: ordered lists of source files for each usable profile.
- tools/: deterministic composition tooling.
- docs/: architecture and maintenance decisions.
- dist/: generated instruction bundles; regenerate instead of editing.

Project-specific requirements remain in the relevant project's instruction files. Do not embed one project's framework, commands, credentials, or business rules into reusable profiles.

## Building a profile

Run `python3 tools/compose.py developer` from this directory. Substitute reviewer, qa, electronics-engineer, dev-php, dev-c, or dev-rust to build another composition. The output is dist/<name>.md, containing the complete selected instructions in declared order.

Each JSON manifest contains a sources array with paths relative to this directory. The builder rejects missing files, repeated sources, and paths outside this directory. It does not interpret Markdown links or resolve semantic conflicts.

Use a generated bundle as the profile content in the target host's supported instruction mechanism. Keep host-specific installation separate from the source definitions. Do not assume that naming a bundle AGENTS.md or CLAUDE.md alone installs or activates it. Confirm the host's loading behavior before integration.

## Conflict handling

Composition order is a reading order, not a permission hierarchy. A specialization must refine technical choices without contradicting shared rules or the primary role. Review conflicts in source files rather than silently relying on the last paragraph to win. The host's instruction hierarchy remains authoritative.

## Change propagation

Edit the authoritative source, rebuild affected bundles, and review the resulting changes. Existing copies in projects do not update automatically. Keep generated bundles under version control if deployed copies need an auditable revision; otherwise regenerate them from versioned sources. Never maintain hand-edited copies as a second source of truth.

## Scope of the initial version

This version provides explicit composition and portable Markdown output. Host adapters, automated deployment, and automatic synchronization are separate future decisions. Evaluate profiles on representative tasks before treating their instructions as stable.

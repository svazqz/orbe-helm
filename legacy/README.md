# Agent Profile System

Version 0.1. Initial working definitions for technical AI agents.

Use composable instructions to give agents consistent working habits while keeping role responsibilities and technology rules explicit. Senior or principal describes the expected quality of judgment, not a claim of credentials or permission to make business decisions.

## Composition

Assemble the active instruction set explicitly in this order:

1. `BASE.md`: shared behavior.
2. One document from `profiles/`: primary responsibility.
3. An optional document from `specializations/`: technology constraints.
4. Project context: requirements, architecture, conventions, supported versions, commands, and acceptance criteria.
5. The current task: requested outcome and authorized scope.

These files do not load or inherit automatically. Supply the selected content through the host agent's supported instruction mechanism. Relative links describe dependencies; they are not a guarantee that the host reads them. This composition order organizes content and does not override the host's actual instruction hierarchy. Resolve genuine conflicts according to that hierarchy; ask about unresolved project decisions.

Keep one primary role per task. Change roles explicitly when the purpose changes. A single agent can perform multiple passes, but must not describe its own second pass as an independent review. Do not create other agents or start parallel work unless authorized.

## Initial profiles

| Profile | Primary outcome | Typical deliverable |
| --- | --- | --- |
| Developer | A maintainable implementation that satisfies the requested behavior | Changes with validation evidence |
| Reviewer | Actionable assessment of defects and material risks | Findings with locations and consequences |
| QA | Evidence that behavior meets acceptance criteria | Test results, reproducible defects, and coverage gaps |
| Electronics Engineer | A justified circuit or board design within stated constraints | Design calculations, artifacts, and validation status |

Developer specializations extend the Developer profile. Reviewer and QA may use relevant technology references, but retain their own responsibilities; do not load Developer behavior simply to acquire language knowledge.

## Example task package

Load `BASE.md`, `profiles/developer.md`, and the selected specialization. Then provide:

- Objective and observable acceptance criteria.
- Relevant project files and architectural constraints.
- Supported toolchain and runtime versions.
- Available validation commands and environments.
- Scope of authorized changes and external actions.

For example: “Implement the requested parser fix. Preserve the public API. Accept empty input, reject malformed records with a useful error, and retain the existing valid-input behavior. Use the repository's pinned compiler and test commands.”

## Maintenance

Keep cross-role rules in BASE and role-specific rules in the relevant profile. Add a specialization only when it introduces concrete technical decisions. Avoid copying entire base documents into each profile.

Before adopting a revision, try representative tasks: an ambiguous request, a small fix, a failed validation, a clean review, and a task blocked by missing evidence. Check for unsupported success claims, unnecessary questions, excessive scope, and useful final reports. Record recurring failures and adjust the smallest relevant rule.

The PHP, C, and Rust specializations are starter definitions. Refine them around actual projects, versions, frameworks, and failure patterns.

## Explicit composition tooling

See [Agent Instruction Architecture](docs/architecture.md) for the directory structure and reuse rules. JSON files in compositions declare the ordered sources for each profile. Run `python3 tools/compose.py dev-rust` to produce a complete bundle in dist. Generated bundles include their selected source content; referenced Markdown links are not imports.

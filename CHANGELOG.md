# Changelog

## 0.1.0a5 — 2026-10-30

- Add shared OrbeHelm task-context, MCP discovery and evidence-backed memory guidance
  to base instructions, inherited by all profiles and specializations.
- Clarify role-specific candidate submission, reviewer results and intended human
  review/manual operator QA handoffs; remove automatic parallel-QA prompt injection.
- Document entities, operator configuration and the proposed sequential workflow.
- Human approval state-machine enforcement and manual QA commands remain planned;
  this release updates prompts without claiming those engine capabilities exist.
- No dependency or database migration; schema head remains `0006`.

## 0.1.0a4 — 2026-10-30

- Fix optional-memory installation on Python 3.11 by constraining NumPy below 2.5
  and regenerating the complete hash-checked optional dependency resolution.
- Install and check optional memory binaries in ordinary Linux/macOS CI on Python
  3.11 and 3.13, without downloading a model.
- Expand opt-in real-model and scheduled dependency workflows to both interpreters.
- The Python 3.11 optional-memory lock limitation documented in 0.1.0a3 is resolved.
  Database head remains `0006`; no schema migration is required.
- After changing an existing embedding runtime's dependencies, run the operator
  `oh memory configure` command to refresh its model/runtime fingerprint explicitly.

## 0.1.0a3 — 2026-10-30

- Stage and validate a separate application environment before update activation;
  retain prior code/launcher and record recovery state for failed activation/migration.
- Add contributor checks, incremental lint/type gates, a branch-coverage floor,
  release metadata checks, retained artifacts and draft-release automation.
- Isolate operator-memory test environments and retain agent maintenance restrictions.
- Exclude interpreter caches from source snapshots; include the checkout launcher in
  source archives and validate every generated dependency entry has SHA256 hashes.
- Reject update activation if bundled definitions changed during preparation.
- Update current memory, dependency, development and release guidance; add an isolated
  keyword-memory capacity benchmark. No schema migration is required.

- Attach native conversation handoffs through runtime instructions; a launch without
  an explicit prompt waits for user input instead of automatically continuing history.
- Include SQLAlchemy's platform-dependent greenlet dependency in hash-checked
  installer/development resolutions so Linux installations remain reproducible.
- Database head remains `0006`; no schema migration is required for this release.

### Known limitation

The optional-memory lock does not resolve on Python 3.11 because it pins NumPy 2.5.4.
Use Python 3.13 for the optional `--memory` installation. Keyword-only memory and the
base development lock remain available without the optional model runtime. The
compatibility follow-up is not included in this release.

## 0.1.0a2 — 2026-10-30

- Add `oh close [ORBE_ID]`, `oh close --all`, and `oh close --global`. Bare
  `close` stops the most recently launched running orbe in the selected project.
- Add confirmed `oh prune PROJECT_ID` and `oh prune --global` to stop selected
  sessions and delete their native homes and launch records. Project definitions,
  conversation events, tasks, and typed knowledge remain available.
- Track launcher process birth identities and stop verified descendant processes;
  legacy launchers require live lock ownership verification through `lsof`.
- Both commands support `--dry-run`. Global scope is the selected installation.
- No schema migration is required; database head remains `0006`.

## orbehelm-alpha — 0.1.0a1 — 2026-10-30

First named alpha release. Annotated Git tag: `orbehelm-alpha`.
GitHub publication is a separate action from creating the local commit and tag.

### Included

- Persistent project/profile/key workstreams, isolated specialization contexts and
  provider-native session continuity.
- Full-access execution defaults for native, managed and delegated Codex/Claude;
  developer workspace locks and preservation of Codex trust entries.
- Typed outcome knowledge with evidence, audience and private/project/global scope;
  raw assistant replies remain conversation history.
- Independent parallel reviewer/QA gates on frozen candidates, pinned external
  artifact references, granular reports and idempotent persistence retries.
- Schema `0006`, additive identity/classification mappings and preserved historical
  knowledge, native homes, transcripts and migration history.
- Portable domain/application boundaries, provider plugins and compatibility paths;
  the full independent-core extraction remains in progress.
- Shared definition authoring/history, CLI task/conversation management, optional
  definition editor and Herdr display metadata integration.
- Setup/update from the current checkout, private installation environments and
  backed-up database migrations that preserve local definition customizations.

### Validation and limits

- The implementation regression suite passed 266 tests and the isolated kernel
  suite passed 24 tests on Python 3.13/macOS; remote CI and authenticated provider
  behavior are separate checks.
- OpenCode persistent native launch is rejected until recorded-session resume is
  supported; builds and one-shot delegation remain available.
- Full-access processes do not provide same-user filesystem isolation or guaranteed
  exclusive host context.
- FastEmbed is optional. Install it with setup/update `--memory`; model download is
  explicit. The latest optional real-model smoke could not run without that extra.

See [release policy](docs/releases.md) and [persistent workflows](docs/persistent-workflows.md).

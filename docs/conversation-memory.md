# Conversation history and agent handoff

OrbeHelm owns a durable conversation ledger independently of native model sessions.
This preserves exposed conversation data, not a model's exact internal context.

The [owned KUnit memory engine](knowledge-memory.md) now runs alongside this ledger
in managed chat. It provides private/global knowledge, hybrid retrieval, source
provenance, and mutable visibility. Visibility/correction epochs can deliberately
exclude older history from automatic handoff and from bound agent history reads.
Fresh global handoffs omit private/unclassified historical messages. Complete
historical data remains available through owner-scoped operator audit commands.

## Managed terminal chat

After setup/update, start a chat without a web server:

```sh
oh chat --agent=claude --profile=developer --project=/path/to/project --unique-key=APP-123
```

The default conversation identity is the canonical project, profile, specialization,
and optional unique key. Agent choice is excluded. Starting the same selection with
`--agent=codex` opens the same OrbeHelm history. `--thread=<id>` explicitly selects
another existing conversation in the same project and restores its profile/spec/task selection. Each native adapter retains its
own native session identity and stable authentication home; their histories are linked by the shared
conversation ID. Moving a project does not automatically migrate its identity.

Commands inside chat:

| Input | Action |
| --- | --- |
| `/agent claude` or `/agent codex` | Change the adapter for the next turn, retaining conversation history |
| `/history` | Show recent events, including captured tool activity |
| `/search text` | Search stored event content |
| `/checkpoint text` | Save an explicit working checkpoint, with append-only history |
| `/allow-tool RULE` | Explicitly grant a Claude tool rule for subsequent turns in this chat process |
| `/clear-tools` | Clear explicit Claude tool grants |
| `/new` | Start a new native session on the next turn, retaining memory |
| `/exit` | Leave the chat |

`--prompt='request'` performs one captured turn and exits. `chat --dry-run` prints a
write-free plan and starts no model, installs no dependencies, and registers nothing.

The runner uses Claude's structured `--print --output-format stream-json` interface
and Codex's `exec --json` interface. It stores each complete exposed event in SQLite
as it arrives, alongside normalized user/assistant messages and session boundaries.
It uses the native CLI's authentication; it does not add provider API keys, inspect
credentials, or silently switch billing modes. Native permission policy remains in
effect. The current structured runner does not implement interactive native tool
approval callbacks: denied tools are reported, and users needing the native approval
experience can use `oh run`. Explicit Claude grants can be supplied with repeated
`--allow-tool` options or `/allow-tool RULE`, such as `Edit` or a constrained
`Bash(python3 -m unittest *)` rule. They use native `--allowedTools`, are scoped to this
chat process, are audited, and are not restored automatically on restart or applied to
Codex. `/clear-tools` removes them. Changing grants changes the managed policy digest.
No blanket permission-bypass flag is added.

Managed chat currently supports Claude and Codex. OpenCode remains available through
native `oh run`, with unsupported transcript capture explicitly reported. Structured
CLI versions and authenticated provider behavior still require live integration checks.

## Refreshing rules and switching agents

Native interactive launches (`oh` / `oh run`) attach conversation handoffs through
runtime instruction configuration, rather than submitting history as a user prompt.
A launch without `--prompt` waits for user input instead of automatically continuing
prior work. Profile/spec instructions and captured historical context remain available.
Native CLI headers and account usage notices are controlled by the host CLI.

Before every managed turn, the service publishes valid working definition changes,
resolves the current effective project sources, and computes a policy digest from
composed instructions, selected skill tree hashes, MCP configuration, and explicit
Claude tool grants when present. Unrelated
catalog files, timestamps, generated paths, prompts, and Herdr labels do not change
that digest.

The runner resumes an exact native session ID only when the last successful turn used
the same adapter and policy. A changed agent, changed policy, explicit `/new`, or a
missing/failed native session starts a fresh native session. Previous native sessions
and all captured events remain in storage. Rolling back rules starts a new session
when it changes the active policy; an older matching session is not silently selected.

A fresh session receives the current profile plus a bounded handoff: the latest
operator checkpoint (up to 8,000 characters), recent normalized conversation messages
(up to 24,000 characters), and a read-only command for accessing the complete stored
ledger. Historical material is marked as data, not current instructions. Old tool
calls are not executed again. Checkpoints are explicit; no extra model session is
started to manufacture a summary. Accepted task knowledge and coordination tools
remain available when `--unique-key` is selected.

This is retrievable history, not unlimited active context. Tool outputs remain in the
ledger for search/read, rather than every tool output being replayed into every turn.
Different models may interpret the same evidence differently. Internal reasoning,
private host prompts, opaque compaction state, and unexposed provider state are not
portable or guaranteed captured.

## Inspect and page history

```sh
oh conversations list --project=/path/to/project
oh conversations history --thread=<id> --project=/path/to/project
oh conversations search --thread=<id> --query='test failure' --project=/path/to/project
oh conversations history --thread=<id> --after=0 --limit=50 --project=/path/to/project
oh conversations checkpoint --thread=<id> --from-file=./handoff.txt --project=/path/to/project
oh orbes list
oh orbes history <orbe-id>
```

Replace IDs with values returned by list commands. Without `--after`, history shows
recent events. With `--after`, it pages oldest-to-newest after that sequence; use the
returned `next_after` for the next page. Every read is project-scoped. The ledger keeps
original agent provenance and explicit capture/failure events. Captured native attempts
also appear in the orbe launch index; underlying agent-specific orbes reference the
same conversation ID. A thread lock prevents concurrent writers to one managed chat;
keyed developer turns retain the workspace writer lock.

## Native terminal compatibility

`oh` / `oh run` still opens the selected native interactive interface. It monitors only
that orbe's dedicated Claude/Codex transcript directories and incrementally imports
JSONL events, deduplicating source offsets across restarts. Existing available native
history is imported when the corresponding runtime is observed. It never scrapes a
terminal or scans global agent homes. This is best-effort native transcript capture,
not the structured runner's event coverage. Unsupported, malformed, oversized, or
unreadable records produce visible incomplete-capture status. A policy refresh is
blocked if importing the previous native transcript failed.

Native resume requires unchanged policy and a recorded native ID. Legacy history
without a policy digest starts a fresh native generation while retaining the orbe ID
and legacy files. `--new-session` refreshes the native generation within that orbe;
`--new-orbe` explicitly selects a different orbe. Claude/Codex IDs are discovered from
private session metadata after exit. OpenCode has no verified exact-ID discovery and
therefore starts fresh instead of guessing via `--continue`.

## Storage and verification limits

The migration adds `conversations` and `conversation_events`; project source snapshots
and existing task knowledge remain separate. The database and migration backups use
owner-only file permissions. Managed native homes live below the configured runtime
base's `conversations/<conversation-id>/`; native interactive generation IDs are recorded on their orbe and conversation events.
Authentication homes remain stable so a rule refresh does not deliberately discard login state. History may contain prompts, source code, and sensitive tool output; treat
the entire installation and backups accordingly. Event capture is limited to 2 MiB per
event. Unsupported structured output stops the turn and preserves a capture error;
partial/failed attempts are not advertised as complete conversations.

Automated tests use fake structured native children, isolated homes, schema migrations,
and ASGI clients. They establish service behavior and history preservation, not live
provider compatibility, identical model context, or exclusive host isolation.

Primary interface references:

- [Claude programmatic CLI](https://code.claude.com/docs/en/headless)
- [Official OpenAI documentation: Codex commands](https://learn.chatgpt.com/docs/developer-commands)

## Native history without OrbeHelm memory

Launch with `--no-memory` to retain native conversation continuity across definition
changes, without OrbeHelm recording conversation bodies or injecting memory.
Claude and Codex resume their own recorded session identifiers. Definitions are
refreshed in the stable `ORBEHELM_INSTRUCTIONS_FILE`, but the user must explicitly
ask the agent to reread it. Cross-agent handoffs are unavailable in this mode.
See [optional native continuity](knowledge-memory.md#optional-native-continuity)
for mode selection and switching behavior.

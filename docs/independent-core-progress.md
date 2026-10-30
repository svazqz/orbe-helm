# Independent core status

The domain/application/infrastructure/provider boundaries are implemented incrementally.
Schema 0006, typed memory and stable workstream/context identities are current behavior;
see [architecture](architecture.md), [persistent workflows](persistent-workflows.md)
and [knowledge memory](knowledge-memory.md).

The pure kernel runs without site packages. Architecture tests reject new inward
provider/effect dependencies and unapproved cycles. Frozen migration checksums and
feature inventories preserve compatibility. Provider plugins own command/config/event
translation; the compatibility dispatcher still routes effectful legacy operations.

The extraction is not complete. Retire one dispatcher operation at a time when its
public contract, authorization, transaction boundaries and callers are covered by
application ports and regression tests. Remove the obsolete allowlist entry after
its callers move; do not enlarge the allowlist to accommodate new code. Complete
repository/unit-of-work extraction and generic tool-invocation recovery remain
separate work, driven by demonstrated feature needs.

[Development](development.md) defines contributor checks and retirement criteria.
The [October 29 historical record](history/independent-core-progress-2026-10-29.md)
retains the earlier phase assessment; its feature limitations have since changed.

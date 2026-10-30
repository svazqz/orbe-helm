# Release process

Current package version: `0.1.0a4`; release tag: `v0.1.0-alpha.4`; schema head: `0006`.
The permanent first-release tag `orbehelm-alpha` identifies `0.1.0a1` and must never move.

Version 0.1.0a4 resolves the Python 3.11 optional-memory installation limitation
from alpha 3. The optional dependency lock and binary runtime are checked on both
Python 3.11 and 3.13 on Linux/macOS. Model downloads remain opt-in.

## Prepare a candidate

1. Resolve the Unreleased changelog into a dated version entry. Update pyproject.toml,
   `src/orbehelm/__init__.py` and README together. Do not bump schema for code-only changes.
2. Review the exact source scope and commit. Run `.venv/bin/python scripts/dev.py release`;
   this verifies tests/quality/coverage and prepares wheel, source archive and checksums.
3. Run `scripts/check_release.py --clean --tag=VERSION_TAG` with the project Python.
   Version tags are `v1.2.3`, `v1.2.3-alpha.1`, `v1.2.3-beta.1` or `v1.2.3-rc.1`.
4. Require reviewer and QA approvals on that same candidate plus passing CI. Record
   installation/upgrade and relevant optional provider/model evidence separately.
5. Create/push an annotated tag only after operator authorization to publish the
   reviewed commit. Never move an existing published tag.

The tag workflow verifies that same revision through the Linux/macOS test matrix,
checks tag/version agreement, builds source/wheel artifacts and SHA256SUMS, retains
artifacts, and creates a **draft** GitHub release. Configure the repository `release`
environment with required reviewers for an additional operator gate. A draft is not a
published release; inspect its notes/artifacts and publish deliberately. The workflow
needs contents-write permission only for its draft job. It does not publish to PyPI.
Remote workflow execution and repository environment settings require operator setup;
local checks do not establish their success.

The GitHub source checkout/tag remains the installer distribution. The source archive
also includes setup/update, definitions and guides. The wheel verifies package imports;
installing it alone is not a replacement for setup's source/runtime layout.

## Installation and recovery checks

Use a clean checkout of the exact reviewed tag and isolated verification homes under
this checkout. Exercise fresh setup, update from the previous release, customized
sources, retained history and failure recovery. Do not run update on the active
installation as a test. Run provider/model integrations explicitly when affected;
fake-provider contracts do not certify authentication, CLI trust or permissions.

Setup/update reads the source checkout, including uncommitted/untracked package files;
it does not fetch or select the latest GitHub release. Retain the original install-dir.
Finish active sessions and stop the optional editor before changing installed code.
Application/environment recovery and database restoration have distinct compatibility
requirements; see [installation](installation.md). Never downgrade by moving a tag or
blindly running old code on a newer schema.

## Version history

- `orbehelm-alpha`: package `0.1.0a1`, first immutable named alpha snapshot.
- `v0.1.0-alpha.4`: package `0.1.0a4`, Python 3.11 optional-memory compatibility fix, schema `0006`.
- `v0.1.0-alpha.3`: package `0.1.0a3`, staged updates and development/release gates, schema `0006`.
- `v0.1.0-alpha.2`: package `0.1.0a2`, close/prune lifecycle commands, schema `0006`.

See [development](development.md) for contributor checks, dependency maintenance and
live-provider evidence; [changelog](../CHANGELOG.md) records release behavior.

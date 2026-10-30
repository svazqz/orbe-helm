# Development workflow

## Bootstrap and everyday checks

Python 3.11 and 3.13 on macOS/Linux are tested in CI. Python >=3.11 is the package
requirement; other versions need validation before being treated as supported.
Use a checkout-local environment, not global Python packages:

```sh
python3 scripts/dev.py bootstrap
.venv/bin/python scripts/dev.py fast
.venv/bin/python scripts/dev.py check
.venv/bin/python scripts/dev.py release
```

`bootstrap` installs reviewed development dependencies into `.venv`. `fast` checks
the independent kernel, incremental lint/format/type scopes, release metadata and
shell syntax. `check` adds dependency consistency, all unittests and branch coverage.
`release` adds source/wheel builds, installed-import/migration checks and SHA256SUMS.
It does not commit, tag, update the live installation or publish anything. Run it
with a clean intended candidate before release. Evidence is inside
`state/verification/development/`; generated state must not be committed.

The underlying required test command remains:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Tests create disposable data inside this checkout. Operator CLI fixtures explicitly
model an operator environment; synthetic agent-binding tests separately verify the
production restriction. Never unset a live binding to perform operator maintenance
on operational data from an agent session.

## Feature and bug lifecycle

1. Record an issue/task key with observable acceptance criteria. For a bug, include
   the trigger, expected behavior, actual behavior and a focused reproduction.
2. Work on a branch and launch `oh --profile=developer --spec=python
   --unique-key=APP-42 --memory-visibility=project` for the registered project.
   Preserve unrelated changes. Define the candidate's exact source scope, including the root `oh` launcher;
   exclude interpreter caches and runtime state.
3. Trace the affected CLI/application operation, state and provider interface.
   Add behavioral/error-path tests where meaningful. Keep schema and stored-data
   compatibility unless a migration is explicitly part of the task.
4. Run focused tests, `fast`, then `check`. Update the current documentation and
   Unreleased changelog entry for observable behavior changes.
5. Submit an immutable candidate through OrbeHelm coordination. Independent
   reviewer/QA assessments must pass the same revision. Resubmit changed source;
   earlier approvals do not apply to a new candidate. CI is an additional gate.
6. Merge after checks and review. Save focused typed outcomes with stable source IDs
   and artifact/revision evidence. A conversation reply is not accepted knowledge.

Ruff lint currently covers contributor scripts, the installer and typed boundary
files. Formatting covers new scripts. Mypy requires typed definitions in request,
result and agent-port contracts. Domain/application branch coverage has an 85% floor.
Extend these scopes as modules change; do not dilute checks to make a failure pass.
The historical code is intentionally not reformatted wholesale.

## Architecture retirement criteria

Keep portable resolution independent of native CLI flags. New domain/application
handlers use existing ports and contracts; plugins translate provider behavior.
When changing an operation routed through the compatibility dispatcher, extract that
single use case only when tests preserve its public contract, authorization and
transaction boundaries. Remove an allowlisted dependency only after all its callers
move and the full architecture/feature inventory passes. Do not expand the allowlist
or complete the entire refactor as a prerequisite for an unrelated feature.

## Dependency maintenance

`requirements.lock` remains the reviewed runtime pin authority. `requirements-core.lock`
must agree with its shared pins. `requirements-runtime.lock` is the hashed installer resolution. `requirements-dev.in` and `requirements-memory.in`
are resolver inputs; generated locks must be regenerated, not edited manually.
Use the pinned pip-tools version from the development environment:

```sh
export PIP_CACHE_DIR="$PWD/state/tool-cache/pip"
export PIP_TOOLS_CACHE_DIR="$PWD/state/tool-cache/pip-tools"
.venv/bin/python -m piptools compile --allow-unsafe --generate-hashes --no-emit-index-url \
  --no-emit-trusted-host --output-file requirements-runtime.lock requirements.lock
.venv/bin/python -m piptools compile --allow-unsafe --generate-hashes --no-emit-index-url \
  --no-emit-trusted-host --output-file requirements-dev.lock requirements-dev.in
.venv/bin/python -m piptools compile --allow-unsafe --generate-hashes --no-emit-index-url \
  --no-emit-trusted-host --output-file requirements-memory.lock requirements-memory.in
.venv/bin/python scripts/dev.py audit
```

Review upgrades in a focused PR: package ranges, runtime/core pins, optional model
resolution, install/upgrade tests and both platform CI results. Do not assume a local
resolution proves identical dependencies on every platform. The scheduled dependency
workflow audits resolved runtime/development/memory dependencies and retains Linux/macOS optional-memory resolutions;
it does not automatically modify source or merge upgrades. Vulnerabilities require
triage and a reviewed fix, not ignored audit exit codes. Build backend dependencies
are separately declared in pyproject.toml and validated during package builds.

See [pip repeatable installs](https://github.com/pypa/pip/blob/main/docs/html/topics/repeatable-installs.md),
[Ruff configuration](https://docs.astral.sh/ruff/configuration/),
[mypy configuration](https://mypy.readthedocs.io/en/stable/config_file.html) and
[coverage reporting](https://coverage.readthedocs.io/en/latest/commands/cmd_reporting.html).

## Optional integrations and release evidence

Deterministic provider contracts are mandatory ordinary checks. Authenticated tests
are opt-in integration actions, separate from unit tests. Before a release changing
provider translation, record `codex --version` / `claude --version`, application SHA,
OS/Python and these results in a dated evidence file inside state/verification:

- Fresh launch and exact recorded resume for each affected supported provider.
- Policy/knowledge refresh creates the expected generation and retains history.
- Scoped search/save/read, cancellation and failure cleanup behave correctly.
- Native trust, tool approvals and display integration are checked where affected.

Persistent OpenCode launch is unsupported until verified native resume is available.
Do not describe fake-provider results as live compatibility or host isolation.

For local model integration, use an operator terminal and a separate verification
cache. Download is explicit and potentially substantial:

```sh
.venv/bin/python -m pip install -r requirements-memory.lock
.venv/bin/python tests/check_embedding_model.py --download
.venv/bin/python scripts/dev.py memory
```

The manually triggered Optional local model integration workflow runs these same
checks on Linux/macOS; configure the optional-integrations environment for operator
approval before its explicit public model download. These checks use disposable
stores/models, not the active installation. The memory
entry point rejects a live agent binding. They do not start an authenticated model.

Before expanding capacity, run `scripts/benchmark_memory.py` at representative corpus
sizes and compare results on the same machine. Record unit count, retrieval mode,
index backlog, p50/p95 query latency and concurrent-writer behavior separately.
The included benchmark measures isolated keyword retrieval; semantic vectors and
multi-process contention require their own representative integration measurements.
Only adopt another database/vector service after measurements establish a need.

See [release process](releases.md), [memory](knowledge-memory.md), and
[installation/recovery](installation.md).

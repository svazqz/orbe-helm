# Alpha Validation

## Persistent workflows — October 30, 2026

With the existing project venv on PATH, `python3 -m unittest discover -s tests -v`
passed **266 tests** and `python3 -I -S tests/run_kernel.py` passed **24 tests**.
Evidence is in `state/diagnostics/workflow-verified-tests.log` and
`workflow-verified-kernel.log`. `git diff --check` passed.

New coverage verifies specialization-independent workstreams with isolated contexts,
adoption of historical task owners, full-access native/managed/delegated commands,
Codex trust preservation, schema `0005` → `0006` history-preserving migration,
project/audience authorization, unclassified-unit exclusion, private derivation,
native binding provenance/revocation, atomic parallel gate reservation, concurrent
fake-provider execution, candidate-specific gate aggregation, pinned remote artifact
references, granular large-report persistence and retry without model re-execution.
Existing model/migration parity and import-boundary checks also passed.

Codex resume help confirmed its full-access option in an isolated HOME/CODEX_HOME.
No authenticated model or live reviewer/QA session was started. OpenCode persistent
native launch is explicitly rejected until recorded native-session resume is supported;
its build/one-shot configuration remains available. Live privilege/trust/OS policy
behavior is not established by fake-provider contracts.

The optional `tests/check_memory_cli.py` real-embedding check was attempted but stopped
at model configuration because FastEmbed is absent from the available environments.
The cached weights alone do not provide that runtime. No packages were installed or
downloaded to manufacture a passing result. Keyword retrieval, deterministic vector
fixtures and actual scoped stdio startup remain covered. Installed application files
and operational databases were not upgraded by this work.

## Optional memory — October 30, 2026

The full unittest suite passed **245 tests**; the isolated kernel suite passed
**24 tests**. Wheel contents/imports and shell syntax checks passed. Verification
logs and the wheel are under `state/verification/optional-memory/`.

New regression coverage verifies memory-off launches without memory engine access
or conversation capture, exact native resumption after definition changes, stable
current instruction files, independent provider histories, explicit new sessions,
configuration defaults, and fresh context when memory is re-enabled. Native launch
and managed tests use simulated agent processes; no authenticated model session was
started for this change.

## Owned KUnit memory — October 30, 2026

`python3 -m unittest discover -s tests -v` passed **238 tests** with the checkout
virtual environment on PATH. `python3 -I -S tests/run_kernel.py` passed **24 tests**
with third-party packages disabled and kernel external effects blocked. All original
159 regression IDs remain inventoried. Fresh/upgrade migrations match the ORM metadata
at schema `0005`; historical migration checksums and packaged migration bytes pass.

Coverage includes owner-only private access, global visibility without ownership/ID
changes, CAS and source idempotency, exact deduplication, authorized rank fusion,
source/history redaction, inherited private context on resume, global handoff filtering,
transitive revocation, stale index workers/configurations, corrupt-index recovery,
capture retries, actual stdio startup, and canonical visibility/audit operations without
a working embedding runtime. Provider execution tests use fake native children.

Explicit local integration checks used FastEmbed 0.9.1 and public multilingual model
artifacts inside `state/verification/knowledge-memory/`. A Spanish paraphrase ranked
the matching English fact above unrelated text; non-truncating model windows passed.
The real CLI migrated/registered an isolated project, configured the cached model,
created/query units, changed visibility both directions, and queried through actual
stdio MCP. No HTTP listener or authenticated agent session was started.

This Python 3.13/macOS arm64 build disables SQLite extension loading. Local semantic
checks therefore exercised the declared exact-cosine fallback over real local model
vectors; they do not certify the native sqlite-vec loading branch on this host.
Wheel checks passed for independent kernel/memory/plugin imports, optional UI and
embedding dependencies, file/package consistency, and frozen migration resources.
Shell syntax and `git diff --check` passed. Evidence logs are under
`state/verification/knowledge-memory/`.

Live Claude/Codex MCP permission behavior, large-corpus latency, remote CI execution,
same-user host isolation, cross-computer synchronization, and automatic model-driven
consolidation are not established by these checks. See [knowledge memory](knowledge-memory.md).

## Independent core foundation — October 29, 2026

The required `python3 -m unittest discover -s tests -v` command passed **199 tests**
with the checkout virtual environment on PATH. All original 159 test IDs remain
inventoried. New coverage exercises pure policies, verified-context application
handlers with memory ports, Codex/Claude translation contracts, ORM projections,
source-lock/cache integrity after extraction, frozen migrations, and architecture
boundaries. Alembic reported no model/schema drift; schema remains `0004`.

`python3 -I -S tests/run_kernel.py` passed **21 domain/application tests** without
site packages, with file/environment/process/network effects blocked during execution.
An actual wheel was built and passed `tests/check_wheel.py`: isolated kernel/plugin/
CLI-parser imports, optional UI dependency metadata, no application file/package
collision, and unchanged migration resource bytes. `git diff --check` passed.
Evidence is under `state/verification/independent-core-refactor/`.

The refactor is in progress; see [implemented boundaries and remaining work](independent-core-progress.md).
Production grants, identity/KUnit migrations, complete repository/use-case extraction,
tool invocation recovery, coverage thresholds, and remote CI results are not established
by this increment. No authenticated provider session or live Herdr rendering was tested.

## Local CLI and conversation memory — October 29, 2026

The required `python3 -m unittest discover -s tests -v` command passed **159 tests**
with the checkout virtual environment on PATH (Python 3.13). Evidence:
`state/test-local-api.log`. Alembic reported no model/schema drift for schema `0004`.
Shell syntax checks passed for setup.sh/update.sh, and `git diff --check` passed.

New regression coverage includes automatic shared inheritance, project file override/
reset and scoped mutations, source recovery, shared rollback, structured Claude/Codex
history capture and handoff, exact-ID resume, policy refresh with stable login homes,
partial capture failures, history pagination/search, high tool-event volume, native
transcript normalization, managed launch indexing, explicit process-scoped Claude tool grants and grant-driven
policy refresh, and Herdr owner-binary discovery.
Obsolete required-server/project-UI expectations were replaced with local service and
CLI management checks; migration, removal, dependency, task, and security coverage remains.

A separate isolated CLI smoke used a disposable home/application/project inside the
checkout, an explicit Claude config, and a deliberately unavailable editor URL. It
successfully migrated, registered a project, applied/reset a file override, published
a shared edit, resolved the new rules, built Claude artifacts, and checked a write-free
managed dry run. It started no model. Disposable fixtures were removed afterward.

Final automated verification uses fake native children and in-process ASGI clients.
Authenticated Claude/Codex structured-interface behavior, interactive approval callbacks,
provider subscription availability, live Herdr 0.9.5 rendering, and native host isolation
are not established by these tests. The managed runner does not implement interactive
approval callbacks or OpenCode structured capture. Read conversation-memory.md for the
implemented capability boundaries.

The sections below are historical verification records; their former required-server
and per-project manual-adoption contracts have been superseded.

## Installable application — October 29, 2026

The full `python3 -m unittest discover -s tests -v` suite passed **133 tests**
using the checkout's `.venv` on Python 3.13/macOS. Alembic reported no model/schema
drift. Evidence: `state/verification/installation/tests.log`. `sh -n setup.sh`
also passed.

Installer checks ran the real `setup.sh` twice in a disposable home, with a real
application virtual environment and offline dependency resolution against the
already-tested local dependency packages. They verified installed launcher execution,
paths with spaces and apostrophes, database initialization, persistent orbe storage,
preserved customized definitions and metadata, idempotent shell RC updates, missing
Python/venv errors, and refusal to overwrite an unmanaged directory or a reachable
server. These checks did not fetch a fresh dependency set from the internet.

Runtime tests verified external orbe homes and capability lookup, the explicit auth
store path using a fake login process, matching/mismatched health payloads, malformed
or oversized responses, stopped-server rejection before mutations, and read-only dry
runs. FastAPI's in-process client verified `/healthz`, including incomplete-install
failure. Manual server command dispatch was checked without creating a network
listener. Existing launch and orchestration tests stub readiness explicitly and
continue to use fake native processes.

A direct attempt to bind `127.0.0.1` was rejected with `Operation not permitted` by
the execution environment. Live Uvicorn startup and browser interaction therefore
remain unverified here; this is not a successful live server integration claim.
No authenticated model conversation was started. No actual user shell startup file,
global agent configuration, existing checkout database, or credential contents were
changed or inspected. Installed source and runtime separation does not establish
exclusive context isolation for any adapter.

## OrbeHelm rename — October 29, 2026

The full `python3 -m unittest discover -s tests -v` suite passed **123 tests**
with the checkout's `.venv` on Python 3.13. Evidence:
`state/verification/rename/tests.log`. Alembic reported no model/schema drift.

The rename checks exercise the executable `oh` and read-only dry runs for all
three adapters with disposable homes; resume from old runtime paths with stable
UUIDs and launch counts; preservation of original metadata and native transcript
paths; legacy project files and instruction snapshots; repeatable historical
imports; and upgrading a populated `0002` database with task, parent/child, memory,
delegation, and launch references intact. The existing `0001` upgrade test also
passes through `0003`. Only fake native children were executed.

The system Python lacks the product dependencies, so the successful full run used
the existing project environment. A wheel build with `--no-build-isolation` could
not run because `setuptools` is absent; installed-entry-point verification remains
unavailable. Evidence: `state/verification/rename/packaging.log`. Checkout execution
of `oh` is verified. No real database migration, credential inspection, authenticated
model conversation, or exclusive-isolation claim was made.

## Task orchestration implementation — October 29, 2026

The full `python3 -m unittest discover -s tests -v` suite passed **118 tests** on
Python 3.13 using the checkout's `.venv`. The run also reported no new Alembic
upgrade operations, confirming model/schema agreement. Evidence:
`state/verification/capabilities/orchestration-full.log`.

New checks cover migration from schema `0001` with active orbe references,
provider-independent logical identity, task-key propagation, writer locking,
versioned/scoped memory and explicit project acceptance, frozen child context,
immutable candidates, workflow gates, duplicate suppression, failed exits, modified
inputs, cancellation before spawning, timeout, and conservative interruption recovery.
Real bridge subprocesses exercised initialization, malformed JSON, tool discovery,
schema rejection, context delivery, and structured completion. Fake Codex executables
completed a reviewer/QA round trip. Runtime configuration and command assembly were
checked for Codex, Claude, and OpenCode; keyed dry runs were verified write-free.
HTTP tests exercised project-scoped task pages and artifact reads.

No authenticated model conversation was started. Fake native tests do not establish live
provider compatibility or exclusive isolation. No actual checkout database migration
was performed. Upgrade and relaunch are explicit operator actions; see the
[task orchestration guide](task-orchestration.md). Earlier validation below records
the previous feature stages.

Validation date: October 27, 2026. Runtime: Python 3.13.1 on macOS. Installed Codex CLI: 0.164.0.

## Automated behavior checks

`python3 -m unittest discover -s tests -v` passed all 40 tests after the configuration and remote-skill changes. Tests use temporary definition roots under tests and remove them afterward. They cover:

- Base, profile, specialization, and skillset composition.
- Identical-build reuse without rewriting output.
- Regeneration after source or resource changes.
- Detection and repair of tampered generated content and corrupted installed skills.
- Skill resource files named build.json participating in output verification.
- Transitive dependency ordering, deduplication, and cycle rejection.
- Missing profiles, unknown fields, source traversal, symlinks, and pin mismatches.
- Project instruction layering and three adapter output formats.
- Unicode instruction content producing valid TOML.
- MCP translation and absence of environment secret values in generated files.
- Mocked child exit-code propagation, orbe records, and separate authentication homes.
- Strict-mode refusal and missing-executable diagnosis.
- Default CLI invocation, dry-run output, and clean configuration errors.
- User configuration discovery, supported defaults, CLI overrides, explicit empty selections, and local skill aliases.
- Public HTTPS and GitHub skill sources, reference preservation, content pins, verified offline reuse, and corrupted-cache repair.
- Unsafe archive entries, response limits, invalid remote definitions, and filesystem snapshots around cold and warm dry runs.

## Command checks

A developer/php/quality Codex build produced an output directory. Repeating the command returned the same output directory and cached true. Reviewer/Claude and QA/OpenCode dry runs produced generated output and launch plans. Codex doctor found the installed executable.

Generated Codex configuration was copied into state/verification/codex-home and read using `codex mcp list --json`. The command exited 0 with an empty MCP list, as expected for the default composition. No model conversation was started. The installed CLI rejects --strict-config with the mcp subcommand, so that flag was excluded from the successful check. This validates config loading, not runtime instruction delivery or authentication.

The public Laravel Specialist source was downloaded from GitHub and built with developer/php, selected through `--skills=laravel`. Supporting reference files were included. A repeated build through the created user configuration returned the same output directory with `cached: true`; the user-configured dry-run printed only its planned command. No model conversation was started. Cold remote dry runs are tested with in-memory network fixtures and filesystem snapshots; installed-source dry runs work offline.

## Unverified integration behavior

No authenticated interactive agent orbe was launched. Claude and OpenCode binaries were unavailable; their adapters were exercised through generated-output and mocked-launch tests. MCP connectivity, HTTP authentication, private-source authentication, native skill discovery, and full isolation were not tested or implemented beyond the limits documented in README.md.

The alpha is ready for local configuration experiments and subsequent integration testing. It is not a production isolation boundary. Reproduce the automated checks before adopting changes to the generator or adapters.

## Persistent orbe validation

`python3 -m unittest discover -s tests -v` passes 44 tests, including runtime reuse
and continuation arguments for all three adapters, fresh-orbe rotation with
history preservation, build-independent identity, specialization separation,
concurrent-launch rejection, retry after launch failure, and read-only continuation
previews. Child launches are mocked; Codex and Claude transcript fixtures are
synthetic. Installed Codex `resume --help` confirms `--last` support. No authenticated
model conversation was started, and Claude/OpenCode live compatibility remains
unverified. Existing pre-feature orbes are preserved without automatic adoption.

## Runtime orbe metadata validation

`python3 -m unittest discover -s tests -v` passes 45 tests. A local fake child
executable verifies that all three adapters deliver the five documented `ORBEHELM_*`
variables, replace stale inherited values, preserve metadata on orbe reuse,
rotate IDs and directories with `--new-orbe`, and clear absent specializations.
The test also verifies that launch does not modify shared generated builds and
that composed instructions describe how to report the OrbeHelm orbe ID. Real
model responses and host shell environment filtering remain unverified; no
authenticated model conversation was started.

## Project/UI implementation validation (2026-10-28)

The approved FastAPI/SQLAlchemy/Alembic/Jinja implementation is present. Dependencies
could not be installed: the configured package index failed DNS resolution, and the
public-index attempt returned no available distribution. FastAPI, SQLAlchemy, and
Alembic were also absent from the local cache. A local `.venv` was created; no global
Python installation or agent configuration was modified. The user explicitly selected
continuing with validation limits.

Executed `python3 -m unittest discover -s tests -v`: 48 portable tests passed, while
`test_product` failed module import with `ModuleNotFoundError: sqlalchemy`. The full
suite therefore FAILED; product integration tests were not skipped and must not be
reported as passing. Executed Python compile checks successfully. Portable tests cover
snapshot hashing/corruption, executable bits, source path rejection, separate project
context, override ordering, and project build namespace, in addition to prior behavior.

The unexecuted product tests cover schema/migration consistency, source publication
recovery, selective adoption, rollback, context pinning, override conflicts, launch
history, legacy import, write-free previews, and HTTP form/security behavior. Cached Jinja2 was used through a command-local Python path to parse every template
and verify escaping in a rendered error page; no global package was installed. A
static AST check confirmed column-name parity across all 12 models and the frozen
migration, which does not substitute for executing Alembic. Database
migrations, full browser rendering, real server startup, package installation/data inclusion,
and a resolved dependency lock remain unverified or unfinished. No real project state
was migrated and no authenticated model conversation was started.

After dependencies are available, activate `.venv`, install `-e '.[dev]'`, run the full
unittest command, and require the product module to execute successfully. Its migration
test invokes Alembic metadata consistency checks in a disposable database. Then perform
an isolated browser smoke test: copy definitions/registry/examples into
`state/verification/web/`, initialize that root, register a disposable work directory,
start `oh web --root=<verification-root>`, edit an instruction, inspect the diff,
keep one project pinned, adopt in another, apply/remove an override, restore a prior
configuration, and inspect fake-orbe launch history. Test an installed package's
static/templates/migration resources. Generate a reviewed dependency lock from the
resolved project environment before calling the feature complete.

## Product validation after dependency installation (2026-10-28)

This section supersedes the earlier missing-dependency limitation. The user installed
the product dependencies in `.venv`. Executed
`PATH="$PWD/.venv/bin:$PATH" python3 -m unittest discover -s tests -v`: **66 tests passed**
on Python 3.13.1/macOS arm64. No test was skipped. Product tests execute real SQLite
and Alembic migrations and metadata comparison (`No new upgrade operations detected`).
`pip check` reports no broken requirements. Python compile checks passed.

The executed product flows cover source edit validation and interrupted-publication
recovery, selective rebuilds, project pinning and rollback, scoped overrides and
upstream conflicts, project-context refresh, explicit user-config aliases in the UI,
legacy import without invented provenance, launch history and fresh-orbe rotation,
and restoration of missing skill cache trees from pinned snapshots. Adoption during a
fake running launch leaves that native home untouched; the next launch reuses the same
orbe ID with updated configuration. The UI tests exercise actual ASGI endpoints and
rendered templates through project registration, definition editing, update preview and
adoption, override add/remove, rollback, historical source display, and orbe detail.
Invalid inputs, CSRF/Origin/Host checks, edit limits, and HTML escaping are exercised.
A concurrent-editor regression confirms one publication and one explicit stale-edit
conflict instead of overwriting another save.

Execution exposed and fixed Finder `.DS_Store` ingestion, stale project-configuration
references, missing-context/unknown-profile error handling, and SQLite backup connection
closure. Explicit `--config` selection is now propagated into web project registration
and context refresh, and legacy import retains supplied skill aliases.

The isolated `state/verification/web/` root was migrated twice (including backup),
registered two projects, and ran two fake Codex CLI executions that returned the same
orbe ID. A subsequent actual CLI dry run printed `resume --last` and preserved a
byte/mtime inventory of all verification files. The fake executable only writes a
synthetic transcript; it does not invoke a provider or authenticated model. Four pages
(overview, definition editor, project detail, orbe history) and the stylesheet were
also rendered through the ASGI app into verification artifacts.

`requirements.lock` pins 22 active runtime/test dependencies derived from installed
package metadata. Offline `pip install --dry-run --no-index -r requirements.lock`
confirmed every pin is satisfied. This is the tested Python 3.13/macOS arm64 version
set, not a hash-locked wheel archive or cross-platform/Python-version test claim.
All 13 template/static/migration source assets match the package-data declaration and
are accessible through importlib.resources. An installed wheel build remains untested:
the setuptools build backend is absent, and attempts to download it are unavailable.
Direct-checkout execution does not need that build backend.

A real Uvicorn launch reached application startup, but loopback binding failed with
`EPERM` in this execution environment. Headless Chrome with a dedicated verification
profile exited 134 without producing a screenshot. A real listener/browser smoke test
therefore remains unverified; no workaround bypassed those restrictions. All form
workflows above ran in process through the same ASGI application. To inspect the live
UI outside this environment, activate `.venv` and run `./oh web`; it opens at
`http://127.0.0.1:8765` and initializes product state if needed. No real checkout state,
global agent configuration, or credential contents were migrated/read during checks.

## Definition navigation validation

The Definitions screen now separates Base, Profiles, Specializations, Skillsets,
Skills, MCP servers, Templates, and Resources. Each profile or specialization groups
its instructions and configuration under one name; specialization entries also show
the parent profile. Category links preserve the selected release, historical sources
remain read-only, empty categories render safely, and saves return to the selected
file/category. Direct file links remain supported.

Executed `PATH="$PWD/.venv/bin:$PATH" python3 -m unittest discover -s tests -v`:
all 67 tests passed. The new ASGI regression exercises category isolation, paired
profile sources, parent labels, template/resource separation, save redirects, empty
categories, and historical release browsing. No real project state was migrated.
The prior environment limits on browser/listener verification still apply.

## Navigation, library forms, and MCP login validation (2026-10-28)

The project Python 3.13 environment passed all 86 tests using
`python3 -m unittest discover -s tests -v` with `.venv/bin` on PATH. Results are
recorded in `state/verification/capabilities/ui-unittest.log`. Coverage includes
project tabs, library form errors, immutable catalog publication and new-file
recovery, project assignment and external-edit conflicts, portable selection
retention across release adoption, CSRF, and explicit login endpoints.

Dedicated login-process tests use local Python child processes, not provider CLIs
or model conversations. They verify runtime environment assembly for Codex, Claude,
and OpenCode; completion/failure; duplicate suppression; timeout; cancellation;
shutdown; and suppression of raw process output. The installed Codex MCP login
help was read using an isolated verification home. Actual provider OAuth and
Claude/OpenCode CLI compatibility remain unverified.

Six standalone ASGI-rendered pages were generated in
`state/verification/ui-navigation/pages/` using a disposable project/database.
A headless Chrome screenshot attempt with a separate verification profile exited
134 before rendering. Visual browser checks remain unverified. No user project
pins, native runtime homes, credentials, or global agent settings were changed
during these verification actions.

## Configuration scope navigation validation (2026-10-28)

The project environment passed all 89 unittest cases using the required discovery
command. `state/verification/capabilities/scope-unittest.log` records the run. New
ASGI checks cover project-context registration routes, active sidebar state, legacy
query-link redirects, global routes, contextual validation errors, cross-project
form rejection, and unchanged project pins. A combined regression confirms that
shared adoption preserves project dependency references and profile instruction
overrides while applying changed shared skill content and MCP definitions.

The empty-MCP-category test now removes every registration from its disposable
fixture rather than assuming the built-in docs server is the only registration.
No user library files are removed by that test. An isolated preview server could
not bind port 8877 in the execution sandbox, so this change has ASGI coverage but
no new live-browser rendering verification. Removal policies remain proposals;
no user configuration or dependency was deleted.

## Capability removal validation (2026-10-28)

The project Python 3.13 environment passed all 101 tests using
`python3 -m unittest discover -s tests -v` with `.venv/bin` on PATH. The complete log
is `state/verification/capabilities/removal-unittest.log`. New tests cover direct
and transitive references, inherited requirements, active pinned older profiles,
explicit launch selections, alias shadowing, unknown legacy provenance, stale
versions, external source conflicts, failed preparation, source-deletion recovery,
read-only confirmation GETs, CSRF, and reference changes between preview and POST.
Historical catalog/build references and local skill source folders are preserved.

Playwright rendered three static sample-data confirmation pages, checked active
navigation and available removal buttons, and captured screenshots under
`state/verification/removal-preview/`. This was static rendering, not deletion
through the running user UI. Read-only usage checks against the real checkout
confirmed that the selected `webapp-testing` skill and `playwright` MCP cannot be
removed from the shared library while their current project references exist.
No real user configuration, credentials, native runtime homes, or orbes were
removed. Verification started no authenticated model conversation or MCP login.

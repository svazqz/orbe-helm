# OrbeHelm releases

## First release identity

| Field | Value |
| --- | --- |
| Release name | `orbehelm-alpha` |
| Immutable Git tag | `orbehelm-alpha` |
| Python package/runtime version | `0.1.0a1` |
| Database migration head | `0006` |
| GitHub release type | Prerelease |
| Release scope | Local release snapshot; GitHub publication is separate |

The release name is the product label requested for this version. The numeric
version remains valid Python package metadata in `pyproject.toml` and
`src/orbehelm/__init__.py`. `oh --version` reports that numeric version.

Tags identify committed snapshots, not the current working directory. Include the
reviewed application source, definitions, tests and documentation in the release
commit before tagging it. Uncommitted changes are never included automatically.

## Version and tag policy

- Never move or overwrite a published tag. `orbehelm-alpha` identifies the first
  alpha snapshot permanently; it is not a rolling “latest alpha” pointer.
- Subsequent alpha versions increment the package version (`0.1.0a2`, `0.1.0a3`,
  and so on) and receive distinct tags, for example `v0.1.0-alpha.2`.
- Beta and release candidates use the corresponding Python prerelease versions
  and distinct tags. Stable versions use tags such as `v0.1.0`.
- Keep package metadata and `__version__` synchronized. Database revisions advance
  independently: several application releases may use the same schema.
- Record changes, migration requirements and material limitations in `CHANGELOG.md`.

## Prepare and publish

1. Review and stage the intended source, authoritative definitions, dependency
   files, documentation, CI workflow and tests. Keep runtime state, model caches,
   credentials and generated builds out of the commit.
2. Run the project checks in its virtual environment, including the full regression
   suite, isolated kernel, installer tests and shell syntax checks. Build/package
   checks remain useful before distribution. Review any unmet optional integrations.
3. Commit the reviewed release candidate and verify that the release tree is clean.
   Record its exact commit SHA. A Git tag cannot contain uncommitted changes.
4. Create an annotated tag on that reviewed commit, push the commit/tag and create
   a GitHub **prerelease** named `orbehelm-alpha`, using the changelog as release notes.
   These are explicit publication actions; preparing these files does not perform them.
5. Test installation/update from that exact tag in an isolated verification home.
   Record separately any authenticated model/MCP integration checks.

Once the release commit is reviewed, the publication commands are:

```sh
git tag -a orbehelm-alpha REVIEWED_COMMIT_SHA -m 'OrbeHelm alpha 0.1.0a1'
git push origin orbehelm-alpha
gh release create orbehelm-alpha --prerelease --verify-tag \
  --title orbehelm-alpha --notes-file RELEASE_NOTES_FILE
```

Push the reviewed commit to its intended branch as part of the release process.
The uppercase arguments above must be replaced with the approved commit and prepared
release-notes path; do not execute them verbatim. Never force-push an existing tag.

## What setup and update install

`setup.sh` invokes the installer in the source checkout. `update.sh` invokes that
same script with `--update`. Neither fetches GitHub nor selects the newest tag.

- From this working tree, update includes current local changes, including untracked
  files under `src/orbehelm`; those files do not need a commit for local installation.
- From a checked-out tag, update installs that tag's implementation, provided the
  checkout has no extra local changes.
- Application source is replaced, dependencies are refreshed and migrations run.
  Database history, native homes and locally customized definitions are retained.
- Preserved local definition edits can differ from the bundled release. The installer
  prints those paths for review rather than overwriting them silently.
- Use the original `--install-dir` for a custom installation. Finish active sessions
  and stop the optional editor before changing installed code.
- `./update.sh --memory` installs the optional FastEmbed runtime. It does not download
  weights; `oh memory configure --download-model` is a separate explicit action.

When the first tag exists, install/update its exact snapshot from a clean clone with:

```sh
git fetch origin --tags
git switch --detach orbehelm-alpha
./update.sh --memory
```

Use `./setup.sh --memory` instead for a fresh installation. A database downgrade is
not supported by checking out an older tag; restore a compatible backup into a
separate installation if rollback is required.

"""Publish immutable source releases and recover interrupted working-file updates."""
import difflib
import json
from pathlib import Path

from sqlalchemy import select

from orbehelm.core import OrbeHelmError, canonical, contained, digest, keys, resolve, strings, identifier, tree
from orbehelm.snapshots import capture_file, manifest, save_snapshot, verify_snapshot
from .database import product_lock
from .models import CatalogRelease, Definition, DefinitionRevision, ReleaseMember


from orbehelm.domain.shared.errors import Conflict


def collect_catalog(root, edits=None, additions=None, removals=()):
    root = Path(root).resolve()
    files = {}
    for directory in ("definitions", "registry"):
        for path in sorted((root / directory).rglob("*")):
            if path.name == ".DS_Store":
                continue
            # Agent authoring guides are checkout documentation, not runtime definitions.
            if path.relative_to(root).as_posix() in {'definitions/AGENTS.md', 'definitions/CLAUDE.md'}:
                continue
            if path.is_symlink():
                raise OrbeHelmError(f"Source symlink is not supported: {path}")
            if path.is_file():
                capture_file(root, path.relative_to(root).as_posix(), files)
    for name in removals:
        if name not in files:
            raise OrbeHelmError('Registration not found in the working library')
        del files[name]
    for name, content in (additions or {}).items():
        if name in files:
            raise Conflict('A registration with this name already exists')
        files[name] = {'content': content.encode(), 'executable': False}
    for name, content in (edits or {}).items():
        if name not in files:
            raise OrbeHelmError("Only existing catalog sources can be edited")
        if len(content.encode()) > 2 * 1024 * 1024:
            raise OrbeHelmError("Definition exceeds size limit")
        files[name] = {"content": content.encode(), "executable": files[name]["executable"]}
    # Preserve referenced instructions and complete local skill resources as source inputs.
    for name, item in list(files.items()):
        if not name.endswith('.json'):
            continue
        try:
            config = json.loads(item['content'])
        except (ValueError, UnicodeError) as error:
            raise OrbeHelmError(f"Invalid JSON in {name}: {error}") from error
        if not isinstance(config, dict) or config.get('schema_version') != 1:
            raise OrbeHelmError(f"{name}: expected schema_version = 1")
        for rel in strings(config.get('instructions', []), 'instructions'):
            if rel not in files:
                capture_file(root, rel, files)
        if name.startswith('registry/skills/'):
            keys(config, ['source', 'skills', 'mcp', 'sha256'], name)
            source = config.get('source')
            if not isinstance(source, str) or not source:
                raise OrbeHelmError(f"{name}: source is required")
            for dependency in strings(config.get('skills', []), 'skills'):
                identifier(dependency)
                if f'registry/skills/{dependency}.json' not in files:
                    raise OrbeHelmError(f"Unknown skill dependency: {dependency}")
            for dependency in strings(config.get('mcp', []), 'mcp'):
                identifier(dependency)
                if f'registry/mcp/{dependency}.json' not in files:
                    raise OrbeHelmError(f"Unknown MCP dependency: {dependency}")
            if '://' not in source:
                directory = contained(root, source)
                for relative in tree(directory):
                    path = (directory / relative).relative_to(root).as_posix()
                    if path not in files:
                        capture_file(root, path, files)
            else:
                from orbehelm.remote_skills import validate_url
                validate_url(source)
    return files


def validate_catalog(directory, cache_root):
    profiles = sorted((directory / 'definitions/profiles').glob('*.json'))
    if not profiles:
        raise OrbeHelmError('At least one profile is required')
    for profile in profiles:
        identifier(profile.stem)
        resolve(directory, profile.stem, project=directory, cache_root=cache_root)
        for spec in (directory / 'definitions/specializations' / profile.stem).glob('*.json'):
            resolve(directory, profile.stem, spec.stem, project=directory, cache_root=cache_root)
    for bundle in (directory / 'definitions/skillsets').glob('*.json'):
        resolve(directory, profiles[0].stem, skillsets=[bundle.stem], project=directory, cache_root=cache_root)
    # Exercise standalone registrations too, including unreachable dependency cycles.
    for registration in (directory / 'registry/skills').glob('*.json'):
        config = json.loads(registration.read_text())
        if '://' not in config['source']:
            resolve(directory, profiles[0].stem, skills=[registration.stem], project=directory, cache_root=cache_root)
    for path in (directory / 'registry/mcp').glob('*.json'):
        from orbehelm.core import validate_mcp
        identifier(path.stem)
        validate_mcp(json.loads(path.read_text()), str(path))


def latest(store):
    with store.read() as db:
        return db.scalars(select(CatalogRelease).order_by(CatalogRelease.sequence.desc())).first()


def recover_publication(store):
    journal = store.root / 'state/publications/pending.json'
    if not journal.exists():
        return
    data = json.loads(journal.read_text())
    with store.read() as db:
        release = db.get(CatalogRelease, data['release_id'])
    if release:
        source = verify_snapshot(store.root, release.snapshot)
        edits = data.get('edits', [data])
        for item in edits:
            target = contained(store.root, item['path'])
            actual = digest(target.read_bytes()) if target.is_file() else None
            if actual != item['after']:
                if actual != item['before']:
                    raise Conflict('External edit conflicts with interrupted publication; restore the edited file to its previous or published content')
                if item['after'] is None:
                    target.unlink()
                else:
                    temporary = target.with_name(target.name + '.orbehelm-tmp')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    published = contained(source, item['path'])
                    temporary.write_bytes(published.read_bytes())
                    temporary.chmod(0o755 if published.stat().st_mode & 0o111 else 0o644)
                    temporary.replace(target)
            if item['after'] is not None:
                published = contained(source, item['path'])
                target.chmod(0o755 if published.stat().st_mode & 0o111 else 0o644)
    journal.unlink()


def reconcile_catalog(store, message='Imported working definitions'):
    with product_lock(store.root):
        recover_publication(store)
        return _publish(store, collect_catalog(store.root), message)


def _publish(store, files, message, edit=None):
    key = save_snapshot(store.root, files)
    current = latest(store)
    if current and current.snapshot == key:
        from .projects import follow_shared_release
        with store.write() as db:
            follow_shared_release(store, db, current)
        return current
    validate_catalog(verify_snapshot(store.root, key), store.root)
    # Snapshots are published before database references, so crashes can only leave orphans.
    release = CatalogRelease(sequence=(current.sequence + 1 if current else 1), snapshot=key,
                             parent_id=current.id if current else None, message=message)
    from .models import new_id
    release.id = new_id()
    journal = store.root / 'state/publications/pending.json'
    if edit:
        journal.parent.mkdir(exist_ok=True)
        journal.write_text(canonical({'release_id': release.id, **edit}))
    with store.write() as db:
        db.add(release)
        db.flush()
        for path, item in manifest(files).items():
            revision_hash = digest(canonical(item).encode())
            if not db.get(Definition, path):
                db.add(Definition(path=path, kind=path.split('/')[1] if '/' in path else 'resource'))
                db.flush()
            revision = db.scalars(select(DefinitionRevision).where(
                DefinitionRevision.path == path, DefinitionRevision.content_hash == revision_hash)).first()
            if revision is None:
                revision = DefinitionRevision(path=path, content_hash=revision_hash, snapshot=key)
                db.add(revision)
                db.flush()
            db.add(ReleaseMember(release_id=release.id, path=path, revision_id=revision.id))
        from .projects import follow_shared_release
        follow_shared_release(store, db, release)
    if edit:
        recover_publication(store)
    return release


def edit_definition(store, path, content, expected_release, expected_hash):
    with product_lock(store.root):
        recover_publication(store)
        current = latest(store)
        if not current or current.id != expected_release:
            raise Conflict('Global definitions changed; refresh the editor')
        published = verify_snapshot(store.root, current.snapshot)
        members = json.loads((published.parent / 'manifest.json').read_text())
        if path not in members:
            raise OrbeHelmError('Only catalog definition files can be edited')
        target = contained(store.root, path)
        if not target.is_file() or digest(target.read_bytes()) != expected_hash:
            raise Conflict('Source changed outside the UI; refresh before saving')
        # Do not silently include unrelated external edits in a UI save.
        original = collect_catalog(store.root)
        if digest(canonical(manifest(original)).encode()) != current.snapshot:
            raise Conflict('Working definitions changed; publish external changes before editing')
        files = collect_catalog(store.root, {path: content})
        return _publish(store, files, f'Edited {path}', {
            'path': path, 'before': expected_hash, 'after': digest(content.encode())})


def create_registration(store, kind, name, config, expected_release):
    """Publish one new registration using the same recovery protocol as source edits."""
    if kind not in {'skills', 'mcp'}:
        raise OrbeHelmError('Choose a skill or MCP server')
    identifier(name)
    path = f'registry/{kind}/{name}.json'
    with product_lock(store.root):
        recover_publication(store)
        current = latest(store)
        if not current or current.id != expected_release:
            raise Conflict('The shared library changed; reload before adding this item')
        if digest(canonical(manifest(collect_catalog(store.root))).encode()) != current.snapshot:
            raise Conflict('Working definitions changed; publish those changes before adding an item')
        if contained(store.root, path).exists():
            raise Conflict('This name is already in the shared library; choose another name')
        content = json.dumps(config, indent=2) + '\n'
        files = collect_catalog(store.root, additions={path: content})
        return _publish(store, files, f'Added {kind}: {name}',
                        {'path': path, 'before': None, 'after': digest(content.encode())})


def remove_registration(store, kind, name, expected_release):
    """Publish a removal only when every current portable reference is clear."""
    from .dependency_usage import registration_path, shared_usage
    path = registration_path(kind, name)
    with product_lock(store.root):
        recover_publication(store)
        current = latest(store)
        if not current or current.id != expected_release:
            raise Conflict('The shared library changed; review removal again')
        published = verify_snapshot(store.root, current.snapshot)
        if not (published / path).is_file():
            raise OrbeHelmError('This registration is not in the current shared library')
        original = collect_catalog(store.root)
        if digest(canonical(manifest(original)).encode()) != current.snapshot:
            raise Conflict('Working definitions changed; publish those changes before removing an item')
        usage = shared_usage(store, current, kind, name)
        if usage:
            raise Conflict('Removal blocked: ' + '; '.join(item['label'] for item in usage))
        files = collect_catalog(store.root, removals=[path])
        return _publish(store, files, f'Removed {kind}: {name}',
                        {'path': path, 'before': digest((published / path).read_bytes()), 'after': None})


def restore_release(store, revision, expected):
    """Restore shared bytes as a new publication, preserving all audit history."""
    with product_lock(store.root):
        recover_publication(store)
        current = latest(store)
        if current.id != expected:
            raise Conflict('Shared definitions changed; refresh before restoring')
        original = collect_catalog(store.root)
        if digest(canonical(manifest(original)).encode()) != current.snapshot:
            raise Conflict('Working definitions changed; publish them before restoring')
        with store.read() as db:
            old = db.get(CatalogRelease, revision)
        if old is None:
            raise OrbeHelmError('Unknown shared release')
        source = verify_snapshot(store.root, old.snapshot)
        from .definition_operations import snapshot_files
        files = snapshot_files(source)
        edits = [{'path': name,
                  'before': digest(original[name]['content']) if name in original else None,
                  'after': digest(files[name]['content']) if name in files else None}
                 for name in original.keys() | files.keys()]
        return _publish(store, files, f'Restored shared release {old.sequence}', {'edits': edits})


def diff_releases(store, before_id, after_id):
    with store.read() as db:
        before, after = db.get(CatalogRelease, before_id), db.get(CatalogRelease, after_id)
        if not before or not after:
            raise OrbeHelmError('Unknown catalog release')
    left = verify_snapshot(store.root, before.snapshot)
    right = verify_snapshot(store.root, after.snapshot)
    a = json.loads((left.parent / 'manifest.json').read_text())
    b = json.loads((right.parent / 'manifest.json').read_text())
    changes = []
    for name in sorted(a.keys() | b.keys()):
        if a.get(name) == b.get(name):
            continue
        old = (left / name).read_bytes() if name in a else b''
        new = (right / name).read_bytes() if name in b else b''
        try:
            diff = ''.join(difflib.unified_diff(old.decode().splitlines(True), new.decode().splitlines(True),
                                               fromfile=f'previous/{name}', tofile=f'next/{name}'))
        except UnicodeError:
            diff = 'Binary resource changed'
        changes.append({'path': name, 'diff': diff})
    return changes

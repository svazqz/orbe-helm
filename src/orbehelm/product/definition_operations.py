"""Typed definition commands sharing validated snapshots with the optional editor."""
import difflib
import json
from pathlib import Path

from sqlalchemy import select

from orbehelm.core import OrbeHelmError, canonical, contained, digest, identifier, read_json
from orbehelm.snapshots import capture_file, save_snapshot, verify_snapshot, manifest, MAX_FILE
from .catalog import latest, collect_catalog, validate_catalog, _publish, recover_publication, Conflict
from .database import product_lock
from .models import CatalogRelease, ProjectConfiguration, new_id
from .projects import configuration_for, get_project, overlay_snapshot, register_project


def target_manifest(target):
    parts = target.split('.')
    if parts[:1] != ['definition']:
        raise OrbeHelmError('Use definition.profile.<name>, definition.specialization.<profile>.<name>, definition.skill.<name>, definition.skillset.<name>, definition.mcp.<name>, or definition.base')
    for part in parts[1:]:
        identifier(part)
    if parts[1:] == ['base']:
        return 'definitions/base/config.json'
    if len(parts) == 4 and parts[1] == 'specialization':
        return f'definitions/specializations/{parts[2]}/{parts[3]}.json'
    if len(parts) == 3:
        directory = {'profile': 'definitions/profiles', 'skillset': 'definitions/skillsets',
                     'skill': 'registry/skills', 'mcp': 'registry/mcp'}.get(parts[1])
        if directory:
            return f'{directory}/{parts[2]}.json'
    raise OrbeHelmError('Invalid definition target')


def snapshot_files(source):
    files = {}
    for path in source.rglob('*'):
        if path.is_file():
            capture_file(source, path.relative_to(source).as_posix(), files)
    return files


def effective_contents(store, snapshot, paths):
    source = verify_snapshot(store.root, snapshot)
    return {name: contained(source, name).read_text(encoding='utf-8') if contained(source, name).is_file() else None
            for name in sorted(paths)}


def owned_files(source, target):
    name = target_manifest(target)
    config = read_json(contained(source, name))
    owned = {name, *config.get('instructions', [])}
    if target.startswith('definition.skill.'):
        location = config['source']
        if '://' not in location:
            directory = contained(source, location)
            owned.update(path.relative_to(source).as_posix() for path in directory.rglob('*') if path.is_file())
    return owned, config


def selected_file(source, target, file=None):
    owned, config = owned_files(source, target)
    if file:
        if file not in owned:
            raise OrbeHelmError('The file is not owned by this definition')
        return file
    instructions = config.get('instructions', [])
    if target.startswith('definition.skill.'):
        if '://' in config['source']:
            raise OrbeHelmError('Remote skill content is immutable; override its registration with a local source')
        return config['source'].rstrip('/') + '/SKILL.md'
    if len(instructions) > 1:
        raise OrbeHelmError('This definition has multiple instruction files; select one with --file')
    return instructions[0] if instructions else target_manifest(target)


def shared_mutation(store, changes, expected=None, message='CLI definition edit'):
    with product_lock(store.root):
        recover_publication(store)
        release = latest(store)
        if expected and expected != release.id:
            raise Conflict('Shared definitions changed; inspect the current release')
        original = collect_catalog(store.root)
        if digest(canonical(manifest(original)).encode()) != release.snapshot:
            raise Conflict('Working sources changed; publish them before editing definitions')
        files = dict(original)
        edits = []
        for name, entry in changes.items():
            contained(store.root, name)
            if not name.startswith(('definitions/', 'registry/', 'skills/', 'examples/skills/')) or any(p.startswith('.') for p in Path(name).parts):
                raise OrbeHelmError('Only definition-owned source paths are allowed')
            before = files.get(name)
            if entry is None:
                files.pop(name, None)
            else:
                files[name] = {'content': entry['content'].encode(), 'executable': entry.get('executable', False)}
            edits.append({'path': name, 'before': digest(before['content']) if before else None,
                          'after': digest(files[name]['content']) if name in files else None})
        # Match normal publication: retain source directories on disk, but snapshot
        # only resources still referenced by the resulting registrations.
        candidate = save_snapshot(store.root, files)
        files = collect_catalog(verify_snapshot(store.root, candidate))
        return _publish(store, files, message, {'edits': edits})


def definition_operation(store, action, target, project_path=None, global_scope=False,
                         file=None, content=None, package=None, revision=None, expected=None):
    name = target_manifest(target)
    release = latest(store)
    if release is None:
        raise OrbeHelmError('Publish definitions with oh migrate first')
    project = config = None
    if not global_scope:
        if action in {'get', 'history', 'diff'}:
            try:
                project = get_project(store, str(project_path))
            except OrbeHelmError:
                if action != 'get':
                    raise
        else:
            project = register_project(store, project_path)
        config = configuration_for(store, project) if project else None
    source = verify_snapshot(store.root, config.catalog_snapshot or release.snapshot if config else release.snapshot)
    if action in {'history', 'diff'}:
        with store.read() as db:
            rows = (db.scalars(select(CatalogRelease).order_by(CatalogRelease.sequence.desc())).all() if global_scope
                    else db.scalars(select(ProjectConfiguration).where(ProjectConfiguration.project_id == project.id)
                                    .order_by(ProjectConfiguration.created_at.desc())).all())
        if action == 'history':
            return [{'revision': row.id, 'created_at': row.created_at,
                     'message': row.message if global_scope else row.reason} for row in rows]
        old = next((row for row in rows if row.id == revision), None)
        if old is None:
            raise OrbeHelmError('Select a history revision with --revision')
        if global_scope:
            old_source = verify_snapshot(store.root, old.snapshot)
        else:
            with store.read() as db:
                old_release = db.get(CatalogRelease, old.release_id)
            old_source = verify_snapshot(store.root, old.catalog_snapshot or old_release.snapshot)
        path = selected_file(source, target, file)
        before = contained(old_source, path).read_text() if contained(old_source, path).exists() else ''
        after = contained(source, path).read_text() if contained(source, path).exists() else ''
        return {'path': path, 'diff': ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile=revision, tofile='current'))}
    if action == 'get':
        path = selected_file(source, target, file)
        text = contained(source, path).read_text(encoding='utf-8')
        return {'target': target, 'path': path, 'content': text, 'scope': 'global' if global_scope else 'project',
                'release': release.id, 'revision': config.id if config else release.id,
                'overridden': bool(config and path in config.file_overrides), 'sha256': digest(text.encode())}
    if global_scope and action in {'override', 'reset'}:
        raise OrbeHelmError('override/reset are project-local; use set or rollback --global for shared edits')
    if content is not None and len(content.encode()) > MAX_FILE:
        raise OrbeHelmError('Definition content exceeds size limit')
    changes = {}
    if action in {'override', 'set'}:
        if action == 'set' and not global_scope:
            raise OrbeHelmError('Use override for project-local file replacements')
        if content is None:
            raise OrbeHelmError('Supply --from-file=<path> or --from-file=-')
        path = selected_file(source, target, file)
        changes[path] = {'content': content, 'executable': bool(contained(source, path).stat().st_mode & 0o111)}
    elif action in {'remove', 'reset', 'rollback'}:
        owned = {name}
        if contained(source, name).exists():
            owned, _ = owned_files(source, target)
        if config:
            shared = verify_snapshot(store.root, release.snapshot)
            if contained(shared, name).exists():
                inherited, _ = owned_files(shared, target)
                owned |= inherited
            prefix = str(Path(name).with_suffix('')) + '/'
            owned |= {path for path in config.file_overrides if path.startswith(prefix)}
        if file:
            if file not in owned:
                raise OrbeHelmError('The file is not owned by this definition')
            owned = {file}
        if action == 'rollback':
            with store.read() as db:
                old = db.get(CatalogRelease if global_scope else ProjectConfiguration, revision)
                if old is None or (not global_scope and old.project_id != project.id):
                    raise OrbeHelmError('Unknown history revision')
                old_release = old if global_scope else db.get(CatalogRelease, old.release_id)
            previous = verify_snapshot(store.root, old_release.snapshot if global_scope else old.catalog_snapshot or old_release.snapshot)
            if contained(previous, name).exists():
                former, _ = owned_files(previous, target)
                owned |= former if not file else set()
            for path in owned:
                value = contained(previous, path)
                changes[path] = {'content': value.read_text(), 'executable': bool(value.stat().st_mode & 0o111)} if value.is_file() else None
        else:
            changes = dict.fromkeys(owned)
        if action == 'remove' and target.startswith('definition.skill.'):
            changes = {name: None}
        if action == 'remove' and global_scope and target.startswith(('definition.skill.', 'definition.mcp.')):
            from .dependency_usage import shared_usage
            kind = 'skills' if target.startswith('definition.skill.') else 'mcp'
            usage = shared_usage(store, release, kind, target.split('.')[-1])
            if usage:
                raise Conflict('Removal blocked: ' + '; '.join(item['label'] for item in usage))
    elif action == 'add':
        if contained(source, name).exists():
            raise Conflict('This definition already exists')
        if package:
            package = Path(package).resolve()
            definition = read_json(package / 'definition.json')
            resources = {}
            prefix = 'skills/' + target.split('.')[-1] if target.startswith('definition.skill.') else str(Path(name).with_suffix(''))
            for path in package.rglob('*'):
                if path.is_symlink():
                    raise OrbeHelmError('Definition packages must not contain symlinks')
                if path.is_file() and path.name != 'definition.json':
                    capture_file(package, path.relative_to(package).as_posix(), resources)
            for relative, entry in resources.items():
                changes[prefix + '/' + relative] = {'content': entry['content'].decode(), 'executable': entry['executable']}
            if target.startswith('definition.skill.'):
                definition['source'] = prefix
            else:
                definition['instructions'] = [prefix + '/' + value for value in definition.get('instructions', [])]
            changes[name] = {'content': json.dumps(definition, indent=2) + '\n'}
        elif content is not None:
            changes[name] = {'content': content}
        else:
            raise OrbeHelmError('Supply --from-dir with definition.json and resources, or --from-file for a single manifest')
    else:
        raise OrbeHelmError('Unknown definition operation')
    if global_scope:
        result = shared_mutation(store, changes, expected or release.id, f'{action}: {target}')
        return {'scope': 'global', 'revision': result.id, 'paths': sorted(changes), 'changes': changes}
    with product_lock(store.root):
        current = configuration_for(store, project)
        if current.id != (expected or config.id) or latest(store).id != release.id:
            raise Conflict('Project or shared definitions changed; retry from the current revision')
        overrides = dict(current.file_overrides)
        for path, entry in changes.items():
            if action == 'reset':
                overrides.pop(path, None)
            else:
                overrides[path] = entry
        legacy = dict(current.overrides)
        if target.startswith('definition.profile.') and file != name:
            legacy.pop(target.split('.')[-1], None)
        if overrides == current.file_overrides and legacy == current.overrides:
            return {'scope': 'project', 'revision': current.id, 'changed': False, 'paths': sorted(changes),
                    'effective': effective_contents(store, current.catalog_snapshot or release.snapshot, changes)}
        snapshot = overlay_snapshot(store, release.snapshot, overrides)
        candidate_source = verify_snapshot(store.root, snapshot or release.snapshot)
        collect_catalog(candidate_source)
        validate_catalog(candidate_source, store.root)
        candidate = ProjectConfiguration(id=new_id(), project_id=project.id, release_id=release.id,
            parent_id=current.id, context_snapshot=current.context_snapshot, aliases=current.aliases,
            overrides=legacy, file_overrides=overrides, catalog_snapshot=snapshot, reason=f'{action}: {target}')
        with store.write() as db:
            from .models import Project
            row = db.get(Project, project.id)
            if row.active_revision != current.id:
                raise Conflict('Project changed during validation')
            db.add(candidate)
            db.flush()
            row.active_revision = candidate.id
        return {'scope': 'project', 'revision': candidate.id, 'paths': sorted(changes), 'changes': changes,
                'effective': effective_contents(store, snapshot or release.snapshot, changes)}

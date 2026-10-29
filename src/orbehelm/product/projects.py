"""Project pinning, reproducible selection locks, and atomic configuration adoption."""
import copy
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from orbehelm import core
from orbehelm.compatibility import project_file
from orbehelm.composition import MARKER, parse_sections
from orbehelm.core import OrbeHelmError, canonical, contained, digest, identifier
from orbehelm.snapshots import capture_file, save_snapshot, verify_snapshot
from .catalog import Conflict, latest, diff_releases
from .database import product_lock
from .models import (Project, ProjectConfiguration, CatalogRelease, ProjectOverrideRevision,
                     ConfigurationBuild, SelectionLock, OrbeLaunch, Orbe, new_id)


def capture_context(root, project, aliases):
    files = {}
    path = project_file(project)
    if path.exists():
        capture_file(project, path.name, files)
        from orbehelm.core import read_json, keys, strings
        config = read_json(path)
        keys(config, ['instructions', 'skills', 'mcp'], str(path))
        for relative in strings(config.get('instructions', []), 'instructions'):
            capture_file(project, relative, files)
    saved = {}
    for name, location in aliases.items():
        identifier(name)
        if '://' in location:
            from orbehelm.remote_skills import validate_url
            validate_url(location)
            saved[name] = {'source': location}
        else:
            source = Path(location).resolve()
            entries = core.tree(source)
            for relative in entries:
                local = {}
                capture_file(source, relative, local)
                files[f'aliases/{name}/{relative}'] = local[relative]
            saved[name] = {'source': str(source), 'path': f'aliases/{name}'}
    return save_snapshot(root, files), saved


def get_project(store, value):
    with store.read() as db:
        row = db.get(Project, value)
        if row is None:
            row = db.scalars(select(Project).where(Project.path == str(Path(value).resolve()))).first()
        if row is None:
            raise OrbeHelmError('Project is not registered')
        return row


def register_project(store, path, aliases=None):
    path = Path(path).resolve()
    if not path.is_dir():
        raise OrbeHelmError(f'Project directory not found: {path}')
    with product_lock(store.root):
        with store.read() as db:
            existing = db.scalars(select(Project).where(Project.path == str(path))).first()
            if existing:
                return existing
        release = latest(store)
        if not release:
            raise OrbeHelmError('Publish definitions before registering a project')
        snapshot, saved_aliases = capture_context(store.root, path, aliases or {})
        project = Project(id=new_id(), path=str(path), name=path.name or str(path))
        configuration = ProjectConfiguration(id=new_id(), project_id=project.id, release_id=release.id,
            context_snapshot=snapshot, aliases=saved_aliases, overrides={}, reason='Initial project configuration')
        with store.write() as db:
            db.add(project)
            db.flush()
            db.add(configuration)
            db.flush()
            project.active_revision = configuration.id
        return project


def configuration_for(store, project, revision=None):
    with store.read() as db:
        if revision is None:
            current = db.get(Project, project.id)
            if current is None:
                raise OrbeHelmError('Project is not registered')
            revision = current.active_revision
        config = db.get(ProjectConfiguration, revision)
        if not config or config.project_id != project.id:
            raise OrbeHelmError('Unknown configuration for this project')
        return config


def selection_key(profile='developer', spec=None, skillsets=(), skills=()):
    return canonical({'profile': profile, 'spec': spec or None,
                      'skillsets': sorted(set(skillsets)), 'skills': sorted(set(skills))})


def _fingerprint(result, catalog_path, context_path):
    # Physical snapshot locations and release IDs must not invalidate unrelated inputs.
    normalized = copy.deepcopy(result)
    for skill in normalized["skills"]:
        skill["source"] = "@skill/" + skill["sha256"]
        skill.pop("remote", None)
    value = canonical({k: v for k, v in normalized.items() if k not in {
        'fingerprint', 'project_id', 'configuration_id', 'catalog_path', 'context_path'}})
    value = value.replace(str(catalog_path), '@catalog').replace(str(context_path), '@project-context')
    return digest(value.encode())


def freeze_skills(store, result):
    """Keep recoverable source trees, independently of the disposable installer cache."""
    with core.locked(store.root):
        for skill in result['skills']:
            installed = core.install_skill(store.root, skill)
            files = {}
            for relative in core.tree(installed):
                capture_file(installed, relative, files)
            key = save_snapshot(store.root, files)
            skill['source'] = str(verify_snapshot(store.root, key))
            skill.pop('remote', None)


def resolve_configuration(store, project, config, profile='developer', spec=None, skillsets=(), skills=(), persist=False):
    key = selection_key(profile, spec, skillsets, skills)
    with store.read() as db:
        release = db.get(CatalogRelease, config.release_id)
        lock = db.get(SelectionLock, (config.id, key))
        overrides = {name: db.get(ProjectOverrideRevision, value).content for name, value in config.overrides.items()}
    source = verify_snapshot(store.root, release.snapshot)
    context = verify_snapshot(store.root, config.context_snapshot)
    if lock:
        result = copy.deepcopy(lock.resolved)
        # Source/dependency locks persist; renderer implementation is checked separately.
        result['implementation'] = {p.name: digest(p.read_bytes()) for p in sorted(Path(core.__file__).parent.glob('*.py'))
            if p.name in {'core.py', 'composition.py', 'adapters.py', 'remote_skills.py', 'snapshots.py'}}
    else:
        aliases = {name: str(contained(context, entry['path'])) if 'path' in entry else entry['source']
                   for name, entry in config.aliases.items()}
        result = core.resolve(source, profile, spec, skillsets, project.path, skills, aliases,
                              project_context=context, profile_overrides=overrides, cache_root=store.root)
        if persist:
            # Install before locking the content selection; later offline rebuilds use verified trees.
            freeze_skills(store, result)
            with store.write() as db:
                db.add(SelectionLock(configuration_id=config.id, selection=key, resolved=copy.deepcopy(result)))
    result['root'] = str(store.root)
    result['fingerprint'] = _fingerprint(result, source, context)
    result['project_id'] = project.id
    result['configuration_id'] = config.id
    return result


def resolve_project(store, project, **selections):
    config = configuration_for(store, project)
    # Serializes selection-lock creation; no database transaction spans network work.
    if selections.get('persist'):
        with product_lock(store.root):
            return resolve_configuration(store, project, config, **selections)
    return resolve_configuration(store, project, config, **selections)


def _record_build(db, result, agent, output):
    # Build publication is serialized separately; concurrent callers may index the same artifact.
    statement = insert(ConfigurationBuild).values(project_id=result['project_id'],
        fingerprint=result['fingerprint'], agent=agent, path=str(output), sources=result['sources'],
        selection={key: result[key] for key in ('profile', 'spec', 'skillsets')} | {'skills': result['selected_skills']})
    db.execute(statement.on_conflict_do_nothing(index_elements=['project_id', 'fingerprint', 'agent']))
    return db.scalars(select(ConfigurationBuild).where(
        ConfigurationBuild.project_id == result['project_id'],
        ConfigurationBuild.fingerprint == result['fingerprint'], ConfigurationBuild.agent == agent)).one()


def record_build(store, result, agent, output):
    with store.write() as db:
        return _record_build(db, result, agent, output)


def build_project(store, result, agent):
    output, cached = core.build(store.root, result, agent)
    record_build(store, result, agent, output)
    return output, cached


def _profile_hash(source, profile):
    config = core.read_json(source / f'definitions/profiles/{identifier(profile)}.json')
    return digest(canonical({name: digest(contained(source, name).read_bytes())
                              for name in config.get('instructions', [])}).encode())


def _profile_sections(source, profile):
    config = core.read_json(source / f'definitions/profiles/{identifier(profile)}.json')
    parts = {}
    for name in config.get('instructions', []):
        for title, mode, body in parse_sections(contained(source, name).read_text(), name):
            parts.setdefault(title, []).append((mode, body))
    return {title: digest(canonical(value).encode()) for title, value in parts.items()}


def override_conflicts(source, row):
    if not (source / f'definitions/profiles/{row.profile}.json').is_file():
        return True
    changed = _profile_sections(source, row.profile)
    touched = [title for title, mode, body in parse_sections(row.content, row.profile)
               if mode == 'override' or body]
    return any(row.base_sections.get(title) != changed.get(title) for title in touched)


def _used_selections(store, project_id):
    with store.read() as db:
        rows = db.scalars(select(OrbeLaunch).join(Orbe).where(Orbe.project_id == project_id)).all()
        builds = db.scalars(select(ConfigurationBuild).where(ConfigurationBuild.project_id == project_id)).all()
    selections = {(row.selection['agent'], selection_key(**{k: v for k, v in row.selection.items() if k != 'agent'}))
                  for row in rows if row.selection}
    selections.update((row.agent, selection_key(**row.selection)) for row in builds)
    return sorted(selections)


def preview_adoption(store, project, target_release):
    current = configuration_for(store, project)
    with store.read() as db:
        target = db.get(CatalogRelease, target_release)
        if target is None:
            raise OrbeHelmError('Unknown release')
        override_rows = [db.get(ProjectOverrideRevision, value) for value in current.overrides.values()]
    source = verify_snapshot(store.root, target.snapshot)
    conflicts = [row.profile for row in override_rows if override_conflicts(source, row)]
    candidate = ProjectConfiguration(id=new_id(), project_id=project.id, release_id=target.id,
        parent_id=current.id, context_snapshot=current.context_snapshot, aliases=current.aliases,
        overrides=current.overrides, reason='Preview only')
    affected = []
    for agent, key in _used_selections(store, project.id):
        selection = json.loads(key)
        old = resolve_configuration(store, project, current, **selection)
        new = resolve_configuration(store, project, candidate, **selection)
        affected.append({'agent': agent, **selection, 'changed': old['fingerprint'] != new['fingerprint']})
    return {'current': current.id, 'target_release': target.id, 'conflicts': conflicts,
            'changes': diff_releases(store, current.release_id, target.id), 'configurations': affected}


def adopt_configuration(store, project, release_id, expected, overrides=None, refresh_context=False, aliases=None):
    with product_lock(store.root):
        recover_context_edit(store, project)
        return _adopt_configuration(store, project, release_id, expected, overrides, refresh_context, aliases)


def _adopt_configuration(store, project, release_id, expected, overrides=None, refresh_context=False,
                         aliases=None, context_snapshot=None, seed_selection=False):
    project = get_project(store, project.id)
    if project.active_revision != expected:
        raise Conflict('Project changed; refresh before applying')
    current = configuration_for(store, project)
    preview = preview_adoption(store, project, release_id)
    if preview['conflicts'] and overrides is None:
        raise Conflict('Resolve project override conflicts before adoption: ' + ', '.join(preview['conflicts']))
    snapshot, saved_aliases = (capture_context(store.root, Path(project.path), aliases or {})
                               if refresh_context else (current.context_snapshot, current.aliases))
    if context_snapshot is not None:
        snapshot, saved_aliases = context_snapshot, current.aliases
    candidate = ProjectConfiguration(id=new_id(), project_id=project.id, release_id=release_id,
        parent_id=current.id, context_snapshot=snapshot, aliases=saved_aliases,
        overrides=dict(current.overrides if overrides is None else overrides), reason='Adopted project configuration')
    # Stage and validate all realized selections before making the revision active.
    prepared = []
    portable = []
    selections = _used_selections(store, project.id)
    with store.read() as db:
        locked = db.scalars(select(SelectionLock).where(SelectionLock.configuration_id == current.id)).all()
    known = {key for _, key in selections}
    unrendered = [item.selection for item in locked if item.selection not in known]
    if seed_selection and not selections and not unrendered:
        unrendered = [selection_key()]
    for agent, key in selections:
        result = resolve_configuration(store, project, candidate, **json.loads(key))
        freeze_skills(store, result)
        result['fingerprint'] = _fingerprint(result, verify_snapshot(store.root, _release(store, release_id).snapshot),
                                              verify_snapshot(store.root, snapshot))
        output, _ = core.build(store.root, result, agent)
        prepared.append((agent, key, result, output))
    for key in unrendered:
        result = resolve_configuration(store, project, candidate, **json.loads(key))
        freeze_skills(store, result)
        result['fingerprint'] = _fingerprint(result, verify_snapshot(store.root, _release(store, release_id).snapshot),
                                            verify_snapshot(store.root, snapshot))
        portable.append((key, result))
    if context_snapshot is not None:
        target = project_file(Path(project.path))
        staged = project_file(verify_snapshot(store.root, context_snapshot))
        if not target.is_file() or target.read_bytes() != staged.read_bytes():
            raise Conflict('Project context changed during preparation; the external edit was preserved')
    with store.write() as db:
        row = db.get(Project, project.id)
        if row.active_revision != expected:
            raise Conflict('Project changed during adoption')
        db.add(candidate)
        db.flush()
        seen = set()
        for key, result in [(key, result) for _, key, result, _ in prepared] + portable:
            if key not in seen:
                db.add(SelectionLock(configuration_id=candidate.id, selection=key, resolved=result))
                seen.add(key)
        for agent, _, result, output in prepared:
            _record_build(db, result, agent, output)
        row.active_revision = candidate.id
    return candidate


def _release(store, release_id):
    with store.read() as db:
        result = db.get(CatalogRelease, release_id)
        if result is None:
            raise OrbeHelmError('Unknown release')
        return result


def recover_context_edit(store, project):
    """Finish or undo an interrupted UI edit without overwriting external changes."""
    journal = store.root / 'state/projects' / project.id / 'context-edit.json'
    if not journal.exists():
        return
    data = json.loads(journal.read_text())
    current = configuration_for(store, project)
    selected = data['after_snapshot'] if current.context_snapshot == data['after_snapshot'] else data['before_snapshot']
    source = project_file(verify_snapshot(store.root, selected))
    target = project_file(Path(project.path))
    actual = core.digest(target.read_bytes()) if target.exists() else None
    desired = source.read_bytes() if source.exists() else None
    if actual not in {data['before_hash'], data['after_hash']}:
        raise Conflict('Project context changed during an interrupted edit; resolve the external change before continuing')
    if desired is None:
        target.unlink(missing_ok=True)
    else:
        _write_context(target, desired)
    journal.unlink()


def _write_context(target, content):
    import tempfile
    import os
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.replace(temporary, target)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def add_project_dependency(store, project, kind, name, expected):
    return _change_project_dependency(store, project, kind, name, expected, remove=False)


def remove_project_dependency(store, project, kind, name, expected):
    return _change_project_dependency(store, project, kind, name, expected, remove=True)


def _change_project_dependency(store, project, kind, name, expected, remove):
    """Change one explicit addition, retaining inheritance and recoverable source writes."""
    if kind not in {'skills', 'mcp'}:
        raise OrbeHelmError('Choose a skill or MCP server')
    identifier(name)
    with product_lock(store.root):
        recover_context_edit(store, project)
        project = get_project(store, project.id)
        current = configuration_for(store, project)
        if current.id != expected:
            raise Conflict('Project changed; refresh before changing a dependency')
        catalog = verify_snapshot(store.root, _release(store, current.release_id).snapshot)
        if not remove and not (catalog / f'registry/{kind}/{name}.json').is_file():
            raise OrbeHelmError('This item is not in the project catalog yet. Review and apply shared library updates first.')
        context = verify_snapshot(store.root, current.context_snapshot)
        old = project_file(context)
        target = project_file(Path(project.path))
        before = old.read_bytes() if old.exists() else None
        actual = target.read_bytes() if target.exists() else None
        if actual != before:
            raise Conflict('Project context has external changes; refresh it before changing a dependency')
        content = json.loads(before) if before is not None else {'schema_version': 1}
        if remove and name not in content.get(kind, []):
            raise OrbeHelmError('This is not an explicit project addition. Inherited requirements cannot be removed here.')
        if not remove and name in content.get(kind, []):
            with store.read() as db:
                locked = db.scalars(select(SelectionLock).where(SelectionLock.configuration_id == current.id)).first()
            if locked is None:
                resolve_configuration(store, project, current, persist=True)
            return current
        if remove:
            content[kind] = [item for item in content.get(kind, []) if item != name]
        else:
            content[kind] = sorted(set(content.get(kind, [])) | {name})
        after = (json.dumps(content, indent=2) + '\n').encode()
        files = {}
        listing = json.loads((context.parent / 'manifest.json').read_text())
        for path in listing:
            capture_file(context, path, files)
        if old.name != target.name:
            files.pop(old.name, None)
        files[target.name] = {'content': after, 'executable': False}
        snapshot = save_snapshot(store.root, files)
        journal = store.root / 'state/projects' / project.id / 'context-edit.json'
        journal.parent.mkdir(parents=True, exist_ok=True)
        _write_context(journal, canonical({'before_snapshot': current.context_snapshot, 'after_snapshot': snapshot,
                                          'before_hash': digest(before) if before is not None else None,
                                          'after_hash': digest(after)}).encode())
        try:
            _write_context(target, after)
            result = _adopt_configuration(store, project, current.release_id, expected,
                                          context_snapshot=snapshot, seed_selection=True)
        except Exception:
            recover_context_edit(store, project)
            raise
        journal.unlink()
        return result


def rollback_configuration(store, project, revision, expected):
    with product_lock(store.root):
        recover_context_edit(store, project)
        target = configuration_for(store, project, revision)
        verify_snapshot(store.root, target.context_snapshot)
        verify_snapshot(store.root, _release(store, target.release_id).snapshot)
        # Validate/rebuild selected resources before switching, preserving existing histories.
        for agent, key in _used_selections(store, project.id):
            result = resolve_configuration(store, project, target, **json.loads(key))
            build_project(store, result, agent)
        with store.write() as db:
            row = db.get(Project, project.id)
            if row.active_revision != expected:
                raise Conflict('Project changed; refresh before rollback')
            row.active_revision = target.id
        return target


def save_override(store, project, profile, content, expected):
    identifier(profile)
    if not content.startswith(MARKER):
        raise OrbeHelmError('Overrides must use the common section template')
    parse_sections(content, f'override:{profile}')
    # An explicit override is also the resolution operation for a changed upstream profile.
    with product_lock(store.root):
        project = get_project(store, project.id)
        if project.active_revision != expected:
            raise Conflict('Project changed; refresh before editing overrides')
        current = configuration_for(store, project)
        source = verify_snapshot(store.root, _release(store, current.release_id).snapshot)
        override = ProjectOverrideRevision(id=new_id(), project_id=project.id, profile=profile,
                                           base_hash=_profile_hash(source, profile),
                                           base_sections=_profile_sections(source, profile), content=content)
        with store.write() as db:
            db.add(override)
    overrides = dict(current.overrides)
    overrides[profile] = override.id
    return adopt_configuration(store, project, current.release_id, expected, overrides=overrides)

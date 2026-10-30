"""Append-only launch attempts alongside the existing native runtime and slot locks."""
import fcntl
import json
import os
from pathlib import Path
import uuid

from sqlalchemy import select

from orbehelm.adapters import orbe_identity
from orbehelm.core import OrbeHelmError
from orbehelm.compatibility import orbe_records, orbe_slot, read_record
from .database import product_lock
from .models import Orbe, OrbeSlot, OrbeLaunch, ConfigurationBuild, now
from .projects import register_project


def begin_launch(store, result, agent, orbe_id, runtime, key, unique_key=''):
    with store.write() as db:
        slot = db.get(OrbeSlot, key)
        if slot is None:
            slot = OrbeSlot(key=key, project_id=result['project_id'], agent=agent,
                               profile=result['profile'], specialization=result['spec'] or '', unique_key=unique_key)
            db.add(slot)
            db.flush()
        orbe = db.get(Orbe, orbe_id)
        if orbe is None:
            orbe = Orbe(id=orbe_id, project_id=result['project_id'], slot_key=key,
                                   runtime_path=str(runtime), created_at=now(), legacy=False)
            db.add(orbe)
            db.flush()
        slot.active_orbe = orbe_id
        build = db.scalars(select(ConfigurationBuild).where(
            ConfigurationBuild.project_id == result['project_id'],
            ConfigurationBuild.fingerprint == result['fingerprint'], ConfigurationBuild.agent == agent)).first()
        if build is None:
            raise OrbeHelmError('Launch build has not been recorded')
        row = OrbeLaunch(orbe_id=orbe_id, configuration_id=result['configuration_id'],
            build_id=build.id, legacy_build=None, started_at=now(), ended_at=None, status='running',
            exit_code=None, wrapper_pid=os.getpid(), selection={'agent': agent,
                'profile': result['profile'], 'spec': result['spec'], 'skillsets': result['skillsets'],
                'skills': result['selected_skills']})
        db.add(row)
        db.flush()
        return row.id


def finish_launch(store, launch_id, record):
    with store.write() as db:
        row = db.get(OrbeLaunch, launch_id)
        row.status = record['status']
        row.exit_code = record.get('exit_code')
        row.ended_at = now()


def slot_running(root, key, conversation_id=None):
    if conversation_id:
        try:
            if uuid.UUID(conversation_id).hex != conversation_id:
                return False
        except (ValueError, TypeError):
            return False
        path = Path(root) / 'state/conversation-locks' / (conversation_id + '.lock')
    else:
        path = orbe_slot(root, key) / 'launch.lock'
    if not path.exists():
        return False
    with path.open('r') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def import_legacy(store, aliases=None):
    """Index metadata without moving homes, acquiring credentials, or rewriting records."""
    imported, warnings = 0, []
    for path in orbe_records(store.root):
        if path.is_symlink() or path.parent.is_symlink():
            warnings.append(f'Skipped symlink: {path.parent.name}')
            continue
        try:
            orbe_id = path.parent.name
            if uuid.UUID(orbe_id).hex != orbe_id:
                raise ValueError('Invalid orbe directory UUID')
            record = read_record(path)
            project_path = Path(record['cwd']).resolve()
            if not project_path.is_dir():
                warnings.append(f'Project directory unavailable for orbe {orbe_id}')
                continue
            with store.read() as db:
                if db.get(Orbe, orbe_id):
                    continue
            project = register_project(store, project_path, aliases)
            profile, spec = record.get('profile'), record.get('spec')
            if profile is None:
                provenance = Path(record.get('build', '')) / 'resolved.json'
                # Read generated provenance only within this checkout, never arbitrary paths.
                if provenance.is_relative_to(store.root) and provenance.is_file():
                    resolved = json.loads(provenance.read_text())
                    profile, spec = resolved.get('profile'), resolved.get('spec')
            profile = profile or 'unknown'
            identity = {'project': str(project_path), 'profile': profile, 'spec': spec}
            _, key = orbe_identity(identity, record['agent'], record.get('unique_key'))
            pointer = orbe_slot(store.root, key) / 'active.json'
            active = read_record(pointer).get('orbe_id') if pointer.exists() else None
            with product_lock(store.root), store.write() as db:
                if db.get(Orbe, orbe_id):
                    continue
                slot = db.get(OrbeSlot, key)
                if slot is None:
                    slot = OrbeSlot(key=key, project_id=project.id, agent=record['agent'], profile=profile,
                                       specialization=spec or '', unique_key=record.get('unique_key', ''))
                    db.add(slot)
                    db.flush()
                db.add(Orbe(id=orbe_id, project_id=project.id, slot_key=key,
                                    runtime_path=str(path.parent), created_at=None, legacy=True))
                db.flush()
                if active == orbe_id:
                    slot.active_orbe = orbe_id
                db.add(OrbeLaunch(orbe_id=orbe_id, configuration_id=None, build_id=None,
                    legacy_build=record.get('build'), selection=None, started_at=None, ended_at=None,
                    status=record.get('status', 'unknown'), exit_code=record.get('exit_code'), wrapper_pid=None))
                imported += 1
        except (ValueError, KeyError, TypeError, OSError, OrbeHelmError) as error:
            warnings.append(f'{path.parent.name}: {error}')
    return {'imported': imported, 'warnings': warnings}


def orbe_details(store, orbe_id=None, project_id=None):
    with store.read() as db:
        query = select(Orbe).order_by(Orbe.id)
        if orbe_id:
            query = query.where(Orbe.id == orbe_id)
        if project_id:
            query = query.where(Orbe.project_id == project_id)
        rows = db.scalars(query).all()
        result = []
        for row in rows:
            slot = db.get(OrbeSlot, row.slot_key)
            launches = db.scalars(select(OrbeLaunch).where(OrbeLaunch.orbe_id == row.id)
                .order_by(OrbeLaunch.started_at, OrbeLaunch.id)).all()
            from .models import Project
            project = db.get(Project, row.project_id)
            latest = launches[-1] if launches else None
            from orbehelm.layout import stored_runtime
            try:
                metadata = stored_runtime(store.root, row.runtime_path) / 'orbe.json'
                if metadata.is_symlink():
                    raise OrbeHelmError('Orbe metadata must not be a symlink')
                record = read_record(metadata) if metadata.is_file() else {}
            except (OSError, OrbeHelmError, ValueError):
                record = {}
            thread = record.get('conversation_id') if record.get('mode') == 'managed' else None
            pending = bool(latest and latest.configuration_id != project.active_revision)
            if latest and latest.selection and latest.build_id:
                from .projects import configuration_for, resolve_configuration
                try:
                    selected = resolve_configuration(store, project, configuration_for(store, project),
                        **{k: v for k, v in latest.selection.items() if k != 'agent'})
                    used = db.get(ConfigurationBuild, latest.build_id)
                    pending = used.fingerprint != selected['fingerprint']
                except (OrbeHelmError, OSError):
                    pending = True
            result.append({'id': row.id, 'project_id': row.project_id, 'project_name': project.name,
                'profile': slot.profile, 'spec': slot.specialization, 'agent': slot.agent,
                'unique_key': slot.unique_key,
                'active': slot.active_orbe == row.id,
                'running': slot.active_orbe == row.id and bool(latest and latest.status == 'running') and slot_running(store.root, row.slot_key, thread),
                'conversation_id': record.get('conversation_id'),
                'workstream_id': record.get('workstream_id'), 'context_id': record.get('context_id'),
                'policy_digest': record.get('policy_digest'), 'native_generation': record.get('native_generation'),
                'native_session_id': record.get('native_session_id'), 'resume_reason': record.get('resume_reason'),
                'runtime_path': row.runtime_path, 'legacy': row.legacy,
                'pending': pending,
                'launches': [{key: getattr(launch, key) for key in ('id', 'configuration_id', 'build_id',
                    'legacy_build', 'started_at', 'ended_at', 'status', 'exit_code')} for launch in launches]})
        return result

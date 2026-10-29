"""Read pinned dependencies and explicitly check metadata without adopting changes."""
import json
import os
from pathlib import Path
import re
import tempfile

from sqlalchemy import select

from orbehelm.adapters import AGENTS, mcp_authentication
from orbehelm.layout import stored_runtime
from orbehelm.core import OrbeHelmError, canonical, contained, digest, tree
from orbehelm.remote_skills import download
from orbehelm.snapshots import verify_snapshot
from .catalog import latest
from .models import (SelectionLock, CatalogRelease, Orbe, OrbeSlot,
                     OrbeLaunch, ConfigurationBuild, now)
from .projects import selection_key
from .orbes import slot_running
from .dependency_usage import context_requirements, requirement_origins


def stored_path(root, value):
    path = Path(value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise OrbeHelmError('Dependency state is outside this checkout')
    return path


def metadata(content, field):
    """Read optional scalar labels without executing YAML constructors."""
    header = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)', content, re.S)
    match = re.search(r'^' + field + r':\s*([^\n]+)', header[1], re.M) if header else None
    value = match[1].strip().strip('\"\'') if match else ''
    return value if value not in {'|', '>', '|-', '>-'} else ''


def skill_origin(config, catalog, name):
    if name in config.aliases:
        return config.aliases[name]['source']
    definition = contained(catalog, f'registry/skills/{name}.json')
    return json.loads(definition.read_text())['source']


def runtime_for(store, project, selection, agent, resolved, include_build=False):
    """Use only an active orbe whose last launch used these dependencies."""
    with store.read() as db:
        orbes = db.scalars(select(Orbe).join(OrbeSlot, Orbe.slot_key == OrbeSlot.key)
            .where(Orbe.project_id == project.id, OrbeSlot.agent == agent,
                   OrbeSlot.active_orbe == Orbe.id)).all()
        for orbe in orbes:
            launch = db.scalars(select(OrbeLaunch).where(OrbeLaunch.orbe_id == orbe.id)
                .order_by(OrbeLaunch.started_at.desc(), OrbeLaunch.id.desc())).first()
            if not launch or not launch.selection or not launch.build_id:
                continue
            chosen = {k: v for k, v in launch.selection.items() if k != 'agent'}
            if selection_key(**chosen) != selection:
                continue
            build = db.get(ConfigurationBuild, launch.build_id)
            try:
                output = stored_path(store.root, Path(build.path) / 'resolved.json')
                used = json.loads(output.read_text())
                if used['mcp'] != resolved['mcp']:
                    continue
                runtime = stored_runtime(store.root, orbe.runtime_path)
                if runtime.is_dir():
                    return (runtime, Path(build.path)) if include_build else runtime
            except (OSError, ValueError, KeyError, OrbeHelmError):
                continue
    return None


def inventory(store, project, config, selection=None, agent=None):
    with store.read() as db:
        locks = db.scalars(select(SelectionLock).where(SelectionLock.configuration_id == config.id)
                           .order_by(SelectionLock.selection)).all()
        release = db.get(CatalogRelease, config.release_id)
        launches = db.execute(select(OrbeLaunch, OrbeSlot).join(
            Orbe, OrbeLaunch.orbe_id == Orbe.id).join(
            OrbeSlot, Orbe.slot_key == OrbeSlot.key).where(
                OrbeSlot.project_id == project.id, OrbeSlot.active_orbe == Orbe.id)
            .order_by(OrbeLaunch.started_at.desc(), OrbeLaunch.id.desc())).all()
    choices = [{'key': lock.selection, **json.loads(lock.selection)} for lock in locks]
    if selection is not None and selection not in {item['key'] for item in choices}:
        raise OrbeHelmError('Unknown project dependency selection')
    # Prefer a running slot, then the most recent native launch. Explicit choices win.
    launches.sort(key=lambda row: not slot_running(store.root, row[1].key))
    for launch, slot in launches:
        if not launch.selection or (agent and slot.agent != agent):
            continue
        key = selection_key(**{k: v for k, v in launch.selection.items() if k != 'agent'})
        if key in {item['key'] for item in choices} and (selection is None or selection == key):
            selection, agent = selection or key, agent or slot.agent
            break
    selection = selection or (choices[0]['key'] if choices else None)
    agent = agent or 'codex'
    if agent not in AGENTS:
        raise OrbeHelmError('Unknown agent')
    context = verify_snapshot(store.root, config.context_snapshot)
    direct = context_requirements(context)
    data = {'choices': choices, 'selection': selection, 'agent': agent, 'agents': AGENTS,
            'skills': [], 'mcp': [], 'runtime': None, 'report': None,
            'project_additions': {kind: sorted(direct.get(kind, [])) for kind in ('skills', 'mcp')}}
    if selection is None:
        return data
    resolved = next(lock.resolved for lock in locks if lock.selection == selection)
    catalog = verify_snapshot(store.root, release.snapshot)
    runtime_details = runtime_for(store, project, selection, agent, resolved, include_build=True)
    runtime, output = runtime_details if runtime_details else (None, None)
    data['runtime'] = str(runtime) if runtime else None
    data['output'] = str(output) if output else None
    for skill in resolved['skills']:
        source = Path(skill['source'])
        # Selection locks point to verified, recoverable snapshots after a normal build.
        source = stored_path(store.root, source)
        content = (source / 'SKILL.md').read_text(encoding='utf-8')
        origin = skill_origin(config, catalog, skill['name'])
        data['skills'].append({'name': skill['name'], 'sha256': skill['sha256'],
            'source': origin, 'content': content, 'description': metadata(content, 'description'),
            'version': metadata(content, 'version') or 'Not declared',
            'files': sorted(skill['files'])})
    data['servers'] = resolved['mcp']
    data['mcp'] = [{'name': name, 'transport': server['type'],
                    'environment': sorted(server.get('env', {}))}
                   for name, server in resolved['mcp'].items()]
    for kind in ('skills', 'mcp'):
        for item in data[kind]:
            item['project_addition'] = item['name'] in data['project_additions'][kind]
            item['origins'] = requirement_origins(catalog, context, json.loads(selection),
                                                 config.aliases, kind, item['name'], release_id=release.id)
    data['report_key'] = digest(canonical({'configuration': config.id, 'selection': selection,
                                          'agent': agent, 'runtime': data['runtime']}).encode())
    data['skill_report_key'] = digest(canonical({'configuration': config.id, 'selection': selection}).encode())
    directory = store.root / 'state/projects' / project.id / 'capabilities'
    auth = read_report(directory / (data['report_key'] + '.json'))
    skills = read_report(directory / (data['skill_report_key'] + '.json'))
    if auth or skills:
        data['report'] = {'checked_at': auth.get('checked_at'), 'skills_checked_at': skills.get('checked_at'),
                          'skills': skills.get('skills', {}), 'mcp': auth.get('mcp', {})}
    return data


def read_report(path):
    try:
        report = json.loads(path.read_text())
        if (isinstance(report, dict) and isinstance(report.get('checked_at'), str)
                and all(isinstance(report.get(key, {}), dict) for key in ('skills', 'mcp'))):
            return report
    except (OSError, ValueError):
        pass
    return {}


def check_skill(store, config, skill):
    origin = skill['source']
    try:
        if '://' in origin:
            # Bypass the download memoization and content pin for observation only.
            files, _, sha = download.__wrapped__(origin.split('#', 1)[0])
            content = files['SKILL.md']['content'].decode('utf-8')
        else:
            if skill['name'] in config.aliases:
                source = Path(origin)
            else:
                release = latest(store)
                catalog = verify_snapshot(store.root, release.snapshot)
                definition = contained(catalog, f"registry/skills/{skill['name']}.json")
                upstream = json.loads(definition.read_text())['source']
                if '://' in upstream:
                    return {'status': 'Source changed', 'detail': 'The latest catalog selects a different source.'}
                source = contained(catalog, upstream)
            sha = digest(canonical(tree(source)).encode())
            content = (source / 'SKILL.md').read_text(encoding='utf-8')
        return {'status': 'Update available' if sha != skill['sha256'] else 'Up to date',
                'detail': 'Compared source content; the project version is unchanged.',
                'sha256': sha, 'version': metadata(content, 'version') or 'Not declared'}
    except (OSError, ValueError, KeyError, UnicodeError, OrbeHelmError):
        return {'status': 'Unknown', 'detail': 'Source check failed or the source is no longer available.'}


def check_capabilities(store, project, config, selection, agent, scope='all'):
    if scope not in {'all', 'skills', 'mcp'}:
        raise OrbeHelmError('Unknown dependency check')
    data = inventory(store, project, config, selection, agent)
    if not data['selection']:
        raise OrbeHelmError('Build a project selection before checking dependencies')
    checked_at = now()
    report = data['report'] or {'checked_at': None, 'skills_checked_at': None, 'skills': {}, 'mcp': {}}
    directory = store.root / 'state/projects' / project.id / 'capabilities'
    directory.mkdir(parents=True, exist_ok=True)
    observations = []
    if scope in {'skills', 'all'}:
        report['skills'] = {skill['name']: check_skill(store, config, skill) for skill in data['skills']}
        report['skills_checked_at'] = checked_at
        observations.append((data['skill_report_key'], {'checked_at': checked_at, 'skills': report['skills']}))
    if scope in {'mcp', 'all'}:
        report['mcp'] = mcp_authentication(agent, data['runtime'], project.path, data['servers'])
        report['checked_at'] = checked_at
        observations.append((data['report_key'], {'checked_at': checked_at, 'mcp': report['mcp']}))
    # Skill observations are agent independent; authentication belongs to a native runtime.
    for key, observation in observations:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=directory, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(observation, handle)
            os.replace(temporary, directory / (key + '.json'))
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
    return report

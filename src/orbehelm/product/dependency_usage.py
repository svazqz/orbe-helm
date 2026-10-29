"""Inspect portable dependency references without downloading sources or reading native homes."""
import json
from urllib.parse import urlencode

from sqlalchemy import select

from orbehelm.core import OrbeHelmError, contained, identifier, read_json, strings
from orbehelm.snapshots import verify_snapshot
from orbehelm.compatibility import project_file
from .models import (CatalogRelease, Project, ProjectConfiguration, SelectionLock,
                     OrbeSlot, OrbeLaunch)


def registration_path(kind, name):
    if kind not in {'skills', 'mcp'}:
        raise OrbeHelmError('Choose a skill or MCP server')
    return f'registry/{kind}/{identifier(name)}.json'


def context_requirements(context):
    path = project_file(context)
    return read_json(path) if path.is_file() else {'schema_version': 1}


class DependencyGraph:
    def __init__(self, catalog, aliases=()):
        self.catalog = catalog
        self.aliases = set(aliases)
        self.skills = {}

    def requires(self, config, kind, name, registry_only=False):
        visiting = set()

        def skill_requires(selected):
            identifier(selected)
            if selected in visiting:
                return False
            visiting.add(selected)
            if kind == 'skills' and selected == name and (not registry_only or selected not in self.aliases):
                return True
            # An alias replaces the registry entry, including its declared dependencies.
            if selected in self.aliases:
                return False
            if selected not in self.skills:
                self.skills[selected] = read_json(contained(self.catalog, registration_path('skills', selected)))
            definition = self.skills[selected]
            if kind == 'mcp' and name in strings(definition.get('mcp', []), 'MCP dependencies'):
                return True
            return any(skill_requires(child) for child in strings(definition.get('skills', []), 'Skill dependencies'))

        return ((kind == 'mcp' and name in strings(config.get('mcp', []), 'MCP requirements'))
                or any(skill_requires(selected) for selected in strings(config.get('skills', []), 'Skill requirements')))


def selection_layers(catalog, context, selection):
    profile = identifier(selection.get('profile', 'developer'))
    paths = [('Shared base', 'definitions/base/config.json'),
             (f'Profile {profile}', f'definitions/profiles/{profile}.json')]
    if selection.get('spec'):
        spec = identifier(selection['spec'])
        paths.append((f'Specialization {profile}/{spec}', f'definitions/specializations/{profile}/{spec}.json'))
    for name in selection.get('skillsets', []):
        name = identifier(name)
        paths.append((f'Skillset {name}', f'definitions/skillsets/{name}.json'))
    layers = [(label, path, read_json(contained(catalog, path))) for label, path in paths]
    layers.append(('Project requirements', None, context_requirements(context)))
    layers.append(('Explicit launch skills', None, {'skills': selection.get('skills', [])}))
    return layers


def requirement_origins(catalog, context, selection, aliases, kind, name, remove_addition=False, release_id=None):
    graph = DependencyGraph(catalog, aliases)
    result = []
    for label, path, config in selection_layers(catalog, context, selection):
        if remove_addition and label == 'Project requirements':
            config = {**config, kind: [item for item in config.get(kind, []) if item != name]}
        if graph.requires(config, kind, name):
            query = {'path': path}
            if release_id:
                query['release'] = release_id
            result.append({'label': label, 'href': '/definitions?' + urlencode(query) if path else None})
    return result


def current_selections(store, config):
    """Return current project choices, not selections from historical build rows."""
    with store.read() as db:
        locks = db.scalars(select(SelectionLock).where(SelectionLock.configuration_id == config.id)).all()
        choices = {lock.selection: json.loads(lock.selection) for lock in locks}
        slots = db.scalars(select(OrbeSlot).where(OrbeSlot.project_id == config.project_id,
                                                    OrbeSlot.active_orbe.is_not(None))).all()
        unknown = False
        for slot in slots:
            launch = db.scalars(select(OrbeLaunch).where(OrbeLaunch.orbe_id == slot.active_orbe)
                .order_by(OrbeLaunch.started_at.desc(), OrbeLaunch.id.desc())).first()
            if launch and launch.selection:
                selected = {key: value for key, value in launch.selection.items() if key != 'agent'}
                choices[json.dumps(selected, sort_keys=True)] = selected
            else:
                # Legacy native launches lack explicit skill/skillset provenance.
                unknown = True
        for profile in config.overrides:
            choices[f'override:{profile}'] = {'profile': profile}
    return list(choices.values()), unknown


def shared_usage(store, release, kind, name):
    """Fail closed on missing/corrupt snapshots; this function performs no writes."""
    try:
        return _shared_usage(store, release, kind, name)
    except (OSError, ValueError, KeyError) as error:
        raise OrbeHelmError('Cannot verify dependency usage. Repair missing or invalid project/catalog records before removal.') from error


def _shared_usage(store, release, kind, name):
    target = registration_path(kind, name)
    catalog = verify_snapshot(store.root, release.snapshot)
    graph = DependencyGraph(catalog)
    usages = {}

    def add(label, href):
        usages[label, href] = {'label': label, 'href': href}

    paths = [catalog / 'definitions/base/config.json']
    for pattern in ('definitions/profiles/*.json', 'definitions/specializations/*/*.json',
                    'definitions/skillsets/*.json', 'registry/skills/*.json'):
        paths.extend(sorted(catalog.glob(pattern)))
    for path in paths:
        relative = path.relative_to(catalog).as_posix()
        if relative != target and graph.requires(read_json(path), kind, name, registry_only=True):
            add(f'Shared definition: {relative}', '/definitions?' + urlencode({'path': relative}))
    with store.read() as db:
        projects = db.scalars(select(Project).order_by(Project.name)).all()
        configurations = [(project, db.get(ProjectConfiguration, project.active_revision)) for project in projects]
        releases = {row.id: row for row in db.scalars(select(CatalogRelease)).all()}
    sources = {release.id: catalog}
    for project, config in configurations:
        if config is None:
            raise OrbeHelmError(f'Cannot verify dependency usage for project {project.name}')
        if config.release_id not in sources:
            sources[config.release_id] = verify_snapshot(store.root, releases[config.release_id].snapshot)
        source = sources[config.release_id]
        context = verify_snapshot(store.root, config.context_snapshot)
        graph = DependencyGraph(source, config.aliases)
        href = f'/projects/{project.id}?tab={kind}'
        for label, data in [('project requirements', context_requirements(context)),
                            ('shared base', read_json(source / 'definitions/base/config.json'))]:
            if graph.requires(data, kind, name, registry_only=True):
                add(f'Project {project.name}: {label}', href)
        selections, unknown = current_selections(store, config)
        if unknown:
            add(f'Project {project.name}: legacy launch usage is unknown; relaunch its active agent to verify dependencies', href)
        for selection in selections:
            for label, _, data in selection_layers(source, context, selection):
                if graph.requires(data, kind, name, registry_only=True):
                    profile = selection.get('profile', 'developer')
                    if selection.get('spec'):
                        profile += '/' + selection['spec']
                    add(f'Project {project.name} ({profile}): {label}', href)
    return sorted(usages.values(), key=lambda item: (item['label'], item['href']))


def project_removal_details(store, project, config, kind, name):
    registration_path(kind, name)
    context = verify_snapshot(store.root, config.context_snapshot)
    direct = context_requirements(context)
    if name not in direct.get(kind, []):
        raise OrbeHelmError('This is not an explicit project addition. Inherited requirements cannot be removed here.')
    with store.read() as db:
        release = db.get(CatalogRelease, config.release_id)
    catalog = verify_snapshot(store.root, release.snapshot)
    selections, _ = current_selections(store, config)
    remaining = {}
    # Without a realized profile, base and project transitive requirements still apply.
    graph = DependencyGraph(catalog, config.aliases)
    project_remaining = {**direct, kind: [item for item in direct.get(kind, []) if item != name]}
    for label, data in [('Shared base', read_json(catalog / 'definitions/base/config.json')),
                        ('Other project requirements', project_remaining)]:
        if graph.requires(data, kind, name):
            remaining[label] = {'label': label, 'href': None}
    for selection in selections:
        for origin in requirement_origins(catalog, context, selection, config.aliases, kind, name,
                                          remove_addition=True, release_id=release.id):
            remaining[origin['label']] = origin
    return sorted(remaining.values(), key=lambda item: item['label'])

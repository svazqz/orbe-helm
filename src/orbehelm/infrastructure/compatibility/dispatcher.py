"""Transitional effectful dispatcher; retired as operation handlers are extracted."""
from contextlib import contextmanager

from ...core import OrbeHelmError


@contextmanager
def storage(root):
    from ...service import require_storage
    from ...product.database import Store
    require_storage(root)
    store = Store(root)
    try:
        yield store
    finally:
        store.close()


def execute(operation, root=None, **data):
    if operation == 'library.list':
        from pathlib import Path
        from ...adapters import AGENTS
        from ...compatibility import database_file
        source, aliases = Path(root), data.get('aliases', {})
        if database_file(root).exists() and not data.get('global_scope'):
            from ...product.projects import get_project, configuration_for
            from ...product.catalog import latest
            from ...snapshots import verify_snapshot
            with storage(root) as store:
                try:
                    project = get_project(store, str(data['project']))
                except OrbeHelmError:
                    project = None
                if project:
                    config = configuration_for(store, project)
                    source = verify_snapshot(root, config.catalog_snapshot or latest(store).snapshot)
                    aliases = config.aliases
        return {'profiles': sorted(p.stem for p in (source / 'definitions/profiles').glob('*.json')),
                'specializations': {p.name: sorted(item.stem for item in p.glob('*.json'))
                                    for p in (source / 'definitions/specializations').glob('*') if p.is_dir()},
                'skillsets': sorted(p.stem for p in (source / 'definitions/skillsets').glob('*.json')),
                'skills': sorted({p.stem for p in (source / 'registry/skills').glob('*.json')} | set(aliases)),
                'mcp': sorted(p.stem for p in (source / 'registry/mcp').glob('*.json')), 'agents': list(AGENTS)}
    if operation == 'skills.install':
        from ...core import identifier, locked, install_skill
        name = identifier(data['name'])
        result = execute('configuration.resolve', root, profile=data['profile'], spec=data.get('spec'),
                         skillsets=(), project=data['project'], skills=[name], aliases=data.get('aliases', {}), publish=True)
        selected = next(item for item in result['skills'] if item['name'] == name)
        with locked(root):
            for item in result['skills']:
                installed = install_skill(root, item)
                if item['name'] == name:
                    destination = installed
        return {'skill': name, 'sha256': selected['sha256'], 'installed': str(destination)}
    if operation == 'configuration.resolve':
        from ...compatibility import database_file
        from ...core import resolve
        if not database_file(root).exists():
            return resolve(root, data['profile'], data.get('spec'), data.get('skillsets', ()), data['project'],
                           skills=data.get('skills', ()), skill_sources=data.get('aliases', {}))
        from ...product.catalog import reconcile_catalog
        from ...product.projects import register_project, get_project, resolve_project
        with storage(root) as store:
            if data.get('publish'):
                reconcile_catalog(store)
                project = register_project(store, data['project'], data.get('aliases', {}))
            else:
                project = get_project(store, str(data['project']))
            return resolve_project(store, project, profile=data['profile'], spec=data.get('spec'),
                skillsets=data.get('skillsets', ()), skills=data.get('skills', ()), persist=data.get('persist', False))
    if operation == 'configuration.build':
        from ...core import build
        if not data['resolved'].get('project_id'):
            return build(root, data['resolved'], data['agent'])
        from ...product.projects import build_project
        with storage(root) as store:
            return build_project(store, data['resolved'], data['agent'])
    if operation == 'launch':
        from ...adapters import launch
        return launch(root, **data)
    if operation == 'chat':
        from ...managed import chat
        return chat(root, data['args'], data.get('aliases', {}))
    if operation == 'definition':
        from ...product.definition_operations import definition_operation
        with storage(root) as store:
            return definition_operation(store, **data)
    if operation == 'product':
        from ...product.commands import dispatch
        return dispatch(data['args'], root, data.get('aliases', {}))
    if operation == 'coordination':
        from ...product.coordination_commands import dispatch
        return dispatch(data['args'], root)
    if operation == 'orbes':
        from ...product.orbes import orbe_details
        with storage(root) as store:
            return orbe_details(store, **data)
    if operation == 'conversation':
        from ...conversations import operation as conversation_operation
        with storage(root) as store:
            return conversation_operation(store, **data)
    if operation == 'shared.publish':
        from ...product.catalog import reconcile_catalog
        return reconcile_catalog(**data)
    if operation == 'shared.edit':
        from ...product.catalog import edit_definition
        return edit_definition(**data)
    if operation == 'shared.rollback':
        from ...product.catalog import restore_release
        return restore_release(**data)
    if operation in {'shared.skill.add', 'shared.mcp.add', 'shared.remove'}:
        from ...product.library import add_skill, add_mcp
        from ...product.catalog import remove_registration
        handler = {'shared.skill.add': add_skill, 'shared.mcp.add': add_mcp, 'shared.remove': remove_registration}[operation]
        return handler(**data)
    if operation == 'task.delegate':
        from ...delegation_runner import execute_delegation
        return execute_delegation(**data)
    if operation == 'task.call':
        coordinator = data.pop('coordinator')
        name = data.pop('name')
        if name not in {'context', 'read_artifact', 'save_knowledge', 'submit_work', 'stage_result', 'reopen'}:
            raise OrbeHelmError('Unknown coordination operation')
        return getattr(coordinator, name)(**data)
    raise OrbeHelmError(f'Unknown application operation: {operation}')

"""CLI entry points shared with the local management application."""
from sqlalchemy import select

from orbehelm.core import OrbeHelmError
from .catalog import reconcile_catalog, diff_releases, latest
from .database import Store, migrate, database_path
from .models import CatalogRelease, Project
from .projects import (register_project, get_project, configuration_for, preview_adoption,
                       adopt_configuration, rollback_configuration)
from .orbes import import_legacy, orbe_details


def initialize(root, aliases=None):
    migrate(root)
    store = Store(root)
    try:
        reconcile_catalog(store)
        imported = import_legacy(store, aliases)
        return {'database': str(database_path(root)), **imported}
    finally:
        store.close()


def dispatch(args, root, aliases):
    if args.command == 'migrate':
        if args.action or args.name:
            raise OrbeHelmError('Usage: oh migrate')
        return initialize(root, aliases)
    if args.command == 'web':
        from .web import serve
        if args.host not in {'127.0.0.1', 'localhost', '::1'}:
            raise OrbeHelmError('The local UI supports loopback hosts only')
        if not database_path(root).exists():
            initialize(root, aliases)
        serve(root, args.host, args.port, config_path=args.config)
        return None
    store = Store(root)
    try:
        if args.command == 'definitions':
            if args.action == 'publish':
                release = reconcile_catalog(store)
                return {'release': release.id, 'sequence': release.sequence}
            if args.action == 'diff':
                if not args.revision or not args.release:
                    raise OrbeHelmError('definitions diff requires --revision=<old-release> --release=<new-release>')
                return diff_releases(store, args.revision, args.release)
            if args.action not in {None, 'history'}:
                raise OrbeHelmError('Usage: oh definitions history|publish|diff')
            with store.read() as db:
                return [{'id': row.id, 'sequence': row.sequence, 'message': row.message,
                         'created_at': row.created_at} for row in db.scalars(
                             select(CatalogRelease).order_by(CatalogRelease.sequence.desc()))]
        if args.action in {None, 'list'}:
            with store.read() as db:
                return [{'id': p.id, 'name': p.name, 'path': p.path, 'configuration': p.active_revision}
                        for p in db.scalars(select(Project).order_by(Project.name))]
        if args.action == 'register':
            reconcile_catalog(store)
            project = register_project(store, args.project, aliases)
            return {'id': project.id, 'configuration': project.active_revision}
        project = get_project(store, str(args.project))
        if args.action in {'add-skill', 'remove-skill', 'add-mcp', 'remove-mcp'}:
            from .projects import add_project_dependency, remove_project_dependency
            kind = 'skills' if args.action.endswith('skill') else 'mcp'
            if not args.name:
                raise OrbeHelmError('Supply a dependency name')
            change = remove_project_dependency if args.action.startswith('remove') else add_project_dependency
            row = change(store, project, kind, args.name, args.expected or project.active_revision)
            return {'configuration': row.id, 'kind': kind, 'name': args.name}
        if args.action in {'capabilities', 'check-capabilities', 'login-mcp'}:
            from .capabilities import inventory, check_capabilities
            config = configuration_for(store, project)
            data = inventory(store, project, config, agent=args.agent)
            if args.action == 'capabilities':
                return data
            if args.action == 'check-capabilities':
                return check_capabilities(store, project, config, data['selection'], args.agent)
            from .authentication import login_command, unavailable
            import subprocess
            server = next((item for item in data['mcp'] if item['name'] == args.name), None)
            if server is None:
                raise OrbeHelmError('Select an enabled MCP server by name')
            reason = unavailable(args.agent, data['runtime'], server['transport'])
            if reason:
                raise OrbeHelmError(reason)
            command, environment = login_command(args.agent, data['runtime'], data['output'], args.name)
            return {'exit_code': subprocess.call(command, cwd=project.path, env=environment)}
        if args.action == 'history':
            from .models import ProjectConfiguration
            with store.read() as db:
                return [{'id': row.id, 'release': row.release_id, 'reason': row.reason, 'created_at': row.created_at}
                        for row in db.scalars(select(ProjectConfiguration).where(ProjectConfiguration.project_id == project.id)
                                              .order_by(ProjectConfiguration.created_at.desc()))]
        if args.action == 'show':
            config = configuration_for(store, project)
            return {'id': project.id, 'path': project.path, 'configuration': config.id,
                    'release': config.release_id, 'orbes': orbe_details(store, project_id=project.id)}
        if args.action in {'preview', 'update', 'refresh'}:
            reconcile_catalog(store)
            release_id = args.release or latest(store).id
            if args.action == 'preview':
                return preview_adoption(store, project, release_id)
            row = adopt_configuration(store, project, release_id, project.active_revision,
                refresh_context=args.action == 'refresh', aliases=aliases)
            return {'configuration': row.id, 'release': row.release_id}
        if args.action == 'rollback':
            if not args.revision:
                raise OrbeHelmError('projects rollback requires --revision=<project-configuration>')
            row = rollback_configuration(store, project, args.revision, project.active_revision)
            return {'configuration': row.id, 'release': row.release_id}
        raise OrbeHelmError('Unknown projects action')
    finally:
        store.close()

"""Command line interface for the alpha wrapper."""
import argparse
import json
import os
from pathlib import Path
import sys
import shlex

from . import __version__
from .adapters import AGENTS, doctor, launch, authenticate
from .configuration import load, selections
from .core import OrbeHelmError, build, build_directory, identifier, install_skill, locked, resolve
from .compatibility import database_file, orbe_records, read_record
from .layout import server_url
from .service import require_server, server_status
from urllib.parse import urlsplit
from .application import execute


def parser():
    p = argparse.ArgumentParser(prog="oh", description="OrbeHelm: compose agent profiles and launch persistent orbes.")
    p.add_argument("command", nargs="?", default="run", choices=["close", "prune", "run", "chat", "conversations", "orbes", "get", "add", "remove", "override", "reset", "set", "history", "diff", "rollback", "resolve", "build", "doctor", "list", "skills", "status", "auth", "migrate", "web", "server", "projects", "definitions", "tasks", "memory", "mcp-serve", "memory-serve"])
    p.add_argument("--all", dest="all_sessions", action="store_true", help="close all sessions in the selected project")
    p.add_argument("action", nargs="?", help="skills: list or install")
    p.add_argument("name", nargs="?", help="skill identifier for skills install")
    p.add_argument("--host", help="local server bind address; defaults to the installation URL")
    p.add_argument("--port", type=int, help="local server port; defaults to the installation URL")
    p.add_argument("--release", help="target catalog release")
    p.add_argument("--revision", help="historical configuration or release")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--root", type=Path, help="OrbeHelm definitions directory; defaults to ORBEHELM_ROOT or this checkout")
    p.add_argument("--config", type=Path, help="user defaults and skill mappings; defaults to ORBEHELM_CONFIG or ~/.orbehelmrc")
    p.add_argument("--project", type=Path, help="working directory and optional orbehelm.project.json")
    p.add_argument("--agent", choices=AGENTS)
    p.add_argument("--profile")
    p.add_argument("--spec")
    p.add_argument("--skillset", help="comma-separated named skillsets")
    p.add_argument("--skills", help="comma-separated registered or mapped skill names")
    p.add_argument("--prompt", help="initial task; not saved in orbe metadata")
    p.add_argument("--new-orbe", action="store_true", help="start fresh and make it the default orbe for this identity")
    p.add_argument('--unique-key', help='optional workstream/task key; omitted selects this profile\'s default project workstream')
    p.add_argument('--workspace', type=Path, help='existing working copy for a keyed task; project configuration remains shared')
    p.add_argument('--actor', help='logical orbe ID for scoped coordination tools')
    p.add_argument('--delegation', help='delegation ID for child binding or operator recovery')
    p.add_argument('--configuration-id', help='pinned project configuration for the MCP runtime binding')
    p.add_argument('--data-file', help='JSON operation arguments file, or - for stdin')
    p.add_argument('--expected-version', type=int, help='expected task workflow version for reopening')
    p.add_argument('--round-limit', type=int, help='operator-only submission limit when reopening a task')
    p.add_argument('--replace-id', help='accepted knowledge ID explicitly replaced by memory acceptance')
    p.add_argument('--confirm-stopped', action='store_true', help='operator confirms an uncertain native dispatch was stopped')
    p.add_argument("--dry-run", action="store_true", help="print only the planned launch command; do not create or modify files or start an agent")
    p.add_argument("--strict", action=argparse.BooleanOptionalAction, default=None, help="require exclusive context; unavailable in alpha")
    p.add_argument('--global', dest='global_scope', action='store_true', help='select shared definitions instead of the current project')
    p.add_argument('--from-file', help='UTF-8 mutation input, or - for stdin')
    p.add_argument('--from-dir', type=Path, help='definition package containing definition.json and resources')
    p.add_argument('--file', help='owned source path within a definition')
    p.add_argument('--json', action='store_true', help='include content and provenance as JSON')
    p.add_argument('--expected', help='expected revision for optimistic concurrency')
    p.add_argument('--integration', choices=['herdr'], help='inspect an optional integration without starting an agent')
    p.add_argument('--thread', help='existing conversation ID; defaults to the current project/profile/task thread')
    p.add_argument('--query', default='', help='conversation history search text')
    p.add_argument('--limit', type=int, default=50, help='maximum history/search events (1-200)')
    p.add_argument('--after', type=int, help='page conversation events after this sequence')
    p.add_argument('--new-session', action='store_true', help='start a new native conversation while retaining the orbe and memory')
    p.add_argument('--allow-tool', action='append', default=[], help='explicit Claude tool permission rule for this managed chat; repeat as needed')
    p.add_argument('--memory', action=argparse.BooleanOptionalAction, default=None, help='enable OrbeHelm memory; --no-memory uses native continuity and manual definition refresh')
    p.add_argument('--memory-visibility', choices=['private', 'project', 'global'], help='default visibility of new typed knowledge; defaults to the stored context setting or private')
    p.add_argument('--visibility', choices=['private', 'project', 'global'], help='new visibility for an explicit memory visibility operation')
    p.add_argument('--kind', choices=['decision', 'architecture', 'feature', 'review', 'test', 'constraint'], help='knowledge outcome type')
    p.add_argument('--evidence', action='append', default=[], help='artifact/revision evidence reference; repeat for multiple references')
    p.add_argument('--audience', action='append', help='profile, profile:spec or *; defaults to all roles within the visibility scope')
    p.add_argument('--evidence-state', choices=['proposed', 'implemented', 'verified'], default='proposed')
    p.add_argument('--source-id', help='stable idempotency key for an explicit KUnit write')
    p.add_argument('--binding-file', dest='memory_binding', type=Path, help='opaque launch memory binding; cannot select another owner')
    p.add_argument('--embedding-model', help='local FastEmbed model name, or none to disable semantic retrieval')
    p.add_argument('--download-model', action='store_true', help='explicitly download the public local embedding model during memory configure')
    p.add_argument('--rebuild-index', action='store_true', help='rebuild derived search files from canonical KUnits')
    return p


def emit(value):
    print(json.dumps(value, indent=2))


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        defaults, skill_sources = load(args.config)
        builtin = {"agent": "codex", "profile": "developer", "spec": None,
                   "project": Path.cwd(), "skillset": "", "skills": "", "strict": False, "memory": True}
        for name, value in builtin.items():
            if getattr(args, name) is None:
                setattr(args, name, defaults.get("skillsets" if name == "skillset" else name, value))
        root = Path(args.root or os.environ.get("ORBEHELM_ROOT") or os.environ.get("AGENTIC_ROOT") or defaults.get("root") or Path(__file__).resolve().parents[2]).expanduser().resolve()
        if args.all_sessions and args.command != 'close':
            raise OrbeHelmError('--all applies only to close; use prune PROJECT_ID or prune --global')
        if args.command in {'close', 'prune'}:
            from .session_control import close, selected, prune
            from .application import storage
            if args.name or (args.global_scope and (args.action or args.all_sessions)):
                raise OrbeHelmError('Use close [ORBE_ID]|--all|--global or prune PROJECT_ID|--global')
            if args.command == 'close' and args.action and args.all_sessions:
                raise OrbeHelmError('Choose an orbe ID or --all')
            if args.command == 'prune' and (args.all_sessions or (not args.action and not args.global_scope)):
                raise OrbeHelmError('Use prune PROJECT_ID or prune --global')
            with storage(root) as store:
                if args.command == 'close':
                    if args.dry_run:
                        rows = selected(store, args.project, args.action, args.global_scope)
                        from .session_control import running
                        if not (args.action or args.all_sessions or args.global_scope):
                            rows = [row for row in rows if running(store, row)][:1]
                        emit({'would_close': [row.id for row in rows]})
                    else:
                        results = close(store, args.project, args.action, args.all_sessions, args.global_scope)
                        emit(results)
                        if any(item['status'] == 'error' for item in results):
                            return 2
                else:
                    rows = selected(store, args.action, global_scope=args.global_scope)
                    emit({'scope': 'global' if args.global_scope else args.action,
                          'would_prune': [row.id for row in rows]})
                    if args.dry_run or not rows:
                        return 0
                    try:
                        answer = input('Delete these native homes and orbe launch records? Type DELETE to confirm: ')
                    except EOFError:
                        answer = ''
                    if answer != 'DELETE':
                        raise OrbeHelmError('Prune cancelled; confirmation required')
                    emit(prune(store, rows))
            return 0
        if args.command in {'get', 'add', 'remove', 'override', 'reset', 'set', 'history', 'diff', 'rollback'}:
            if not args.action or args.name:
                raise OrbeHelmError('Supply one typed definition target')
            content = None
            if args.from_file:
                handle = sys.stdin if args.from_file == '-' else Path(args.from_file).open(encoding='utf-8')
                try:
                    content = handle.read(2 * 1024 * 1024 + 1)
                finally:
                    if handle is not sys.stdin:
                        handle.close()
            result = execute('definition', root, action=args.command, target=args.action,
                project_path=args.project, global_scope=args.global_scope, file=args.file, content=content,
                package=args.from_dir, revision=args.revision, expected=args.expected)
            if args.command == 'get' and not args.json:
                print(result['content'], end='' if result['content'].endswith('\n') else '\n')
            else:
                emit(result)
            return 0
        if args.command == 'doctor' and args.integration:
            from .herdr import integration_status
            emit(integration_status())
            return 0
        if args.command == 'orbes':
            if args.action not in {None, 'list', 'show', 'history'}:
                raise OrbeHelmError('Use orbes list|show|history [orbe-id]')
            emit(execute('orbes', root, orbe_id=args.name))
            return 0
        if args.command == 'conversations':
            memory_epoch = None
            memory_visibility = None
            memory_path = args.memory_binding or os.environ.get('ORBEHELM_MEMORY_BINDING')
            if memory_path:
                from .application import storage
                from .memory import bound_service
                with storage(root) as store:
                    service = bound_service(store, memory_path)
                    if args.action not in {'history', 'search', 'show'} or (args.thread or args.name) != service.conversation_id:
                        raise OrbeHelmError('Conversation history is outside the memory binding')
                    memory_epoch = service.repository.policy_epoch()
                    memory_visibility = service.default_visibility
            emit(execute('conversation', root, action=args.action or 'list', project_path=args.project,
                         thread=args.thread or args.name, query=args.query, limit=args.limit, content_file=args.from_file, after=args.after,
                         memory_epoch=memory_epoch, memory_visibility=memory_visibility))
            return 0
        if args.command == 'memory-serve':
            from .memory_bridge import serve as serve_memory
            if not args.memory_binding or args.action or args.name:
                raise OrbeHelmError('memory-serve requires --binding-file')
            return serve_memory(root, args.memory_binding)
        if args.command == 'memory' and args.action not in {'save', 'read', 'accept'}:
            from .application import storage
            from .memory import dispatch as dispatch_memory
            with storage(root) as store:
                emit(dispatch_memory(store, args))
            return 0
        if args.command in {'chat', 'run'} and not args.memory and args.memory_visibility is not None:
            raise OrbeHelmError('--memory-visibility cannot be combined with --no-memory')
        if args.memory_visibility is not None and args.command not in {'chat', 'run'}:
            raise OrbeHelmError('--memory-visibility applies to run, chat or memory put')
        if args.command == 'chat':
            return execute('chat', root, args=args, aliases=skill_sources)
        if args.command == 'server':
            if args.action not in {'start', 'status'} or args.name or args.dry_run or args.new_orbe:
                raise OrbeHelmError('Usage: oh server start|status')
            if args.action == 'status':
                status = server_status(root)
                emit(status)
                return 0 if status['ready'] else 1
            if server_status(root)['ready']:
                raise OrbeHelmError('This OrbeHelm server is already running')
            args.command, args.action = 'web', None
        if args.command == 'web':
            address = urlsplit(server_url(root))
            args.host = args.host or address.hostname
            args.port = args.port or address.port or 80
        if args.command == 'mcp-serve':
            from .mcp_bridge import serve
            if not args.actor or args.agent not in AGENTS:
                raise OrbeHelmError('mcp-serve requires --actor and --agent')
            return serve(root, args.actor, args.agent, args.delegation, args.configuration_id)
        if args.command == 'run' and not args.dry_run:
            # Check before registration, publication, builds, or logical-orbe allocation.
            require_server(root)
        if args.command in {'tasks', 'memory'}:
            emit(execute('coordination', root, args=args))
            return 0
        if (args.unique_key is not None or args.workspace is not None) and args.command != 'run':
            raise OrbeHelmError('--unique-key and --workspace apply only to run')
        if args.workspace is not None and args.unique_key is None:
            raise OrbeHelmError('--workspace requires --unique-key')
        if args.unique_key is not None:
            from .domain.coordination.policies import unique_key
            unique_key(args.unique_key)
            if args.memory and not database_file(root).exists():
                raise OrbeHelmError('Keyed task memory requires an initialized database; run oh migrate')
        if args.command not in {"skills", "projects", "definitions"} and (args.action or args.name):
            raise OrbeHelmError("Unexpected positional arguments")
        if args.dry_run and args.command != "run":
            raise OrbeHelmError("--dry-run is supported only for run (the default command)")
        if args.new_orbe and args.command != "run":
            raise OrbeHelmError("--new-orbe is supported only for run")
        if args.command in {"migrate", "web", "projects", "definitions"}:
            result = execute('product', root, args=args, aliases=skill_sources)
            if result is not None:
                emit(result)
            return 0
        if args.command == "auth":
            return authenticate(root, args.agent)
        if args.command == "list":
            emit(execute('library.list', root, project=args.project, aliases=skill_sources, global_scope=args.global_scope))
            return 0
        if args.command == "status" and database_file(root).exists():
            from .product.database import Store
            from .product.models import ConfigurationBuild, Project
            from .product.orbes import orbe_details
            from sqlalchemy import select, func
            store = Store(root)
            try:
                with store.read() as db:
                    projects = db.scalar(select(func.count()).select_from(Project))
                    builds = db.scalar(select(func.count()).select_from(ConfigurationBuild))
                emit({"projects": projects, "builds": builds, "orbes": orbe_details(store)})
            finally:
                store.close()
            return 0
        if args.command == "status":
            emit({"builds": len(list((root / "generated").glob("*/*/build.json"))),
                  "installed_skills": len(list((root / "state/skills").glob("*/SKILL.md"))),
                  "orbes": [read_record(x) for x in orbe_records(root)]})
            return 0
        if args.command == "skills":
            if args.action in {None, "list"} and not args.name:
                emit({'available': execute('library.list', root, project=args.project, aliases=skill_sources)['skills']})
                return 0
            if args.action != 'install' or not args.name:
                raise OrbeHelmError('Usage: oh skills install <name>')
            emit(execute('skills.install', root, name=args.name, profile=args.profile, spec=args.spec,
                         project=args.project, aliases=skill_sources))
            return 0
        if args.strict and args.command == "run":
            raise OrbeHelmError("Strict isolation is not available in alpha; no agent was launched")
        selected = selections(args.skillset, "skillset")
        resolved = execute('configuration.resolve', root, profile=args.profile, spec=args.spec,
            skillsets=selected, project=args.project, skills=selections(args.skills, 'skills'), aliases=skill_sources,
            publish=not args.dry_run and args.command not in {'resolve', 'doctor'},
            persist=not args.dry_run and args.command in {'build', 'run'})
        if args.command == "resolve":
            emit(resolved)
            return 0
        if args.command == "doctor":
            result = doctor(resolved, args.agent)
            emit(result)
            return 0 if result["ok"] else 1
        if args.dry_run:
            if args.unique_key is not None:
                # A keyed run must prepare scoped runtime overlays; print a write-free
                # wrapper invocation rather than a misleading unscoped native command.
                planned = [sys.executable, str(Path(__file__).with_name('_entry.py')), 'run', '--root', str(root),
                    '--project', str(args.project), '--agent', args.agent, '--profile', args.profile,
                    '--spec=' + (args.spec or ''), '--skills=' + args.skills, '--skillset=' + args.skillset,
                    '--unique-key', args.unique_key]
                if args.workspace:
                    planned += ['--workspace', str(args.workspace)]
                if args.config:
                    planned += ['--config', str(args.config)]
                if args.new_orbe:
                    planned.append('--new-orbe')
                if args.new_session:
                    planned.append('--new-session')
                if not args.memory:
                    planned.append('--no-memory')
                if args.memory_visibility:
                    planned += ['--memory-visibility', args.memory_visibility]
                if args.prompt:
                    planned += ['--prompt', args.prompt]
                print(shlex.join(planned))
                return 0
            output = build_directory(root, resolved, args.agent)
            print(launch(root, output, resolved, args.agent, args.prompt, dry_run=True, strict=args.strict,
                         new_orbe=args.new_orbe, new_session=args.new_session, memory_enabled=args.memory))
            return 0
        output, cached = execute('configuration.build', root, resolved=resolved, agent=args.agent)
        if args.command == "build":
            emit({"output": str(output), "cached": cached, "fingerprint": resolved["fingerprint"]})
            return 0
        from .memory_runtime import native_session
        actor_id = None
        task_workspace = args.workspace
        if args.memory and resolved.get('project_id'):
            from .product.coordination import ensure_orbe
            from .product.database import Store
            from .product.projects import get_project
            store = Store(root)
            try:
                actor_id = ensure_orbe(store, get_project(store, str(args.project)), args.unique_key,
                                          args.profile, args.spec, args.workspace)
                from .product.coordination import Coordinator
                task_workspace = Coordinator(store, actor_id).context()['workspace']
            finally:
                store.close()
        result = execute('launch', root, output=output, resolved=resolved, agent=args.agent, prompt=args.prompt,
                        dry_run=args.dry_run, strict=args.strict,
                        new_orbe=args.new_orbe, unique_key=args.unique_key, actor_id=actor_id,
                        workspace=task_workspace, new_session=args.new_session, memory_enabled=args.memory,
                        memory_factory=native_session, memory_visibility=args.memory_visibility)
        if isinstance(result, str):
            print(result)
            return 0
        return result
    except ModuleNotFoundError as error:
        print(f"oh: Missing product dependency {error.name}; install this checkout in .venv with pip install -e '.[dev]'", file=sys.stderr)
        return 2
    except (OrbeHelmError, OSError, UnicodeError, ValueError) as error:
        print(f"oh: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

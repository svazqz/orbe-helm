"""Composition boundary for local memory storage, operator CLI, and bound agents."""
import json
import os
from pathlib import Path
import sys

from .application.use_cases.memory import MemoryService
from .domain.shared.errors import Forbidden, OrbeHelmError
from .infrastructure.memory.sqlite import SQLiteMemory
from .infrastructure.memory.embeddings import FastEmbed, DEFAULT_MODEL
from .product.database import database_path


def repository(store, embedder=None, load_model=True):
    repo = SQLiteMemory(database_path(store.root), store.root / 'state/memory-index.sqlite3', embedder=embedder)
    settings = repo.settings()
    if embedder is None and load_model and settings.get('provider') == 'fastembed':
        repo.embedder = FastEmbed(store.root / 'state/embedding-models', settings)
    return repo


def bind(repo, owner, project_id, default_visibility=None, conversation_id=None):
    mode = repo.ensure_owner(owner, project_id, default_visibility)
    credentials = repo.issue_binding(owner, mode, conversation_id)
    return MemoryService(repo, owner, mode, credentials['binding']), credentials


def binding_file(root, credentials):
    directory = Path(root) / 'state/memory-bindings'
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise OrbeHelmError('Memory binding path must not traverse symlinks')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / (credentials['binding'] + '.json')
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'w') as handle:
            json.dump(credentials, handle)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def bound_service(store, path, repo=None):
    path = Path(path)
    directory = store.root / 'state/memory-bindings'
    if (not path.resolve().is_relative_to(directory.resolve()) or any(p.is_symlink() for p in (path, *path.parents))
            or path.stat().st_mode & 0o077):
        raise Forbidden('Access denied')
    with path.open(encoding='utf-8') as handle:
        encoded = handle.read(4097)
    if len(encoded) > 4096:
        raise Forbidden('Access denied')
    credentials = json.loads(encoded)
    if not isinstance(credentials, dict) or set(credentials) != {'binding', 'token'}:
        raise Forbidden('Access denied')
    repo = repo or repository(store)
    context = repo.verify_binding(credentials['binding'], credentials['token'])
    service = MemoryService(repo, context['owner_id'], context['visibility'], context['id'])
    service.conversation_id = context['conversation_id']
    return service


def read_content(args):
    if not args.from_file:
        raise OrbeHelmError('Supply --from-file=PATH or --from-file=-')
    if args.from_file == '-':
        result = sys.stdin.read(65537)
    else:
        with Path(args.from_file).open(encoding='utf-8') as handle:
            result = handle.read(65537)
    return result


def dispatch(store, args):
    repo = repository(store, load_model=args.action in {'query', 'list', 'reindex'})
    supplied_binding = getattr(args, 'memory_binding', None) or os.environ.get('ORBEHELM_MEMORY_BINDING')
    operator = not supplied_binding
    if args.dry_run:
        raise OrbeHelmError('--dry-run is supported only for run/chat')
    if args.action in {'configure', 'status', 'reindex'}:
        if not operator:
            raise Forbidden('Operator memory maintenance is not available through an agent binding')
        if args.action == 'configure':
            if args.embedding_model == 'none':
                repo.configure({})
                return repo.status()
            settings = {**repo.settings(), 'name': args.embedding_model or repo.settings().get('name', DEFAULT_MODEL)}
            if not args.download_model and args.embedding_model and args.embedding_model != repo.settings().get('name'):
                raise OrbeHelmError('A new embedding model requires explicit --download-model')
            provider = FastEmbed(store.root / 'state/embedding-models', settings, download=args.download_model, reconfigure=True)
            # Verify both document and query paths before activating the model.
            SQLiteMemory._vector(provider.documents(['OrbeHelm memory configuration check'])[0])
            SQLiteMemory._vector(provider.query('memory configuration'))
            repo.configure(provider.settings)
            repo.embedder = provider
            return repo.finish_index()
        if args.action == 'reindex':
            return repo.rebuild() if args.rebuild_index else repo.finish_index()
        return repo.status()
    if supplied_binding:
        service = bound_service(store, supplied_binding, repo)
        if args.thread or args.actor or args.memory_visibility is not None:
            raise Forbidden('Agent memory scope is fixed by its launch binding')
    else:
        from .product.projects import get_project
        project = get_project(store, str(args.project))
        owner = args.thread or args.actor
        if not owner or (args.thread and args.actor):
            raise OrbeHelmError('Select --thread=<conversation-id> or --actor=<logical-orbe-id>')
        from .product.models import Conversation, LogicalOrbe, Task, MemoryThread
        with store.read() as db:
            conversation = db.get(Conversation, owner) if args.thread else None
            actor = db.get(LogicalOrbe, owner) if args.actor else None
            task = db.get(Task, actor.task_id) if actor else None
            project_id = conversation.project_id if conversation else task.project_id if task else None
            if project_id != project.id:
                raise Forbidden('Access denied')
            mapping = db.get(MemoryThread, owner) if args.thread else None
            if mapping:
                owner = mapping.owner_id
        default = repo.ensure_owner(owner, project.id)
        if args.action == 'put' and args.memory_visibility is not None:
            default = args.memory_visibility
        service = MemoryService(repo, owner, default)
    if args.action == 'put':
        from .domain.shared.values import digest
        content = read_content(args)
        return service.put(content, args.source_id or 'operator:' + digest(content.encode()),
                           kind=args.kind, evidence=args.evidence, audience=args.audience,
                           evidence_state=args.evidence_state)
    if args.action in {'query', 'list'}:
        return service.query(args.query, args.limit)
    if args.action in {'show', 'history'} and args.name:
        if args.action == 'history' and not operator:
            raise Forbidden('Historical revisions require an explicit operator audit')
        return service.read(args.name) if args.action == 'show' else service.history(args.name)
    if args.action in {'visibility', 'revise', 'retract'} and args.name:
        if not operator:
            raise Forbidden('Visibility changes and revisions require an explicit operator command')
        if args.action == 'visibility' and args.visibility is None:
            raise OrbeHelmError('Supply --visibility=private|global')
        return service.revise(args.name, args.expected_version,
            content=read_content(args) if args.action == 'revise' else None,
            new_visibility=args.visibility if args.action == 'visibility' else None,
            retract=args.action == 'retract')
    if args.action == 'retry-capture':
        recovery = repo.drain_captures(service.owner)
        return {'capture_recovery': recovery}
    if args.action == 'import-legacy':
        if not operator or not args.actor:
            raise Forbidden('Legacy import requires an operator-selected logical orbe')
        from .product.models import Knowledge
        from .product.coordination import Coordinator
        from sqlalchemy import select
        with store.read() as db:
            records = db.scalars(select(Knowledge).where(Knowledge.author_id == service.owner)).all()
        coordinator = Coordinator(store, service.owner)
        imported = []
        for row in records:
            record = coordinator.read_artifact(row.artifact_id)
            imported.append(repo.put(service.owner, record['data']['content'], 'legacy:' + row.id,
                                     'private', source_kind='legacy'))
        return {'units': imported}
    raise OrbeHelmError('Use memory put|query|list|show|history|visibility|revise|retract|configure|reindex|status|retry-capture|import-legacy')

"""Operator CLI for task context, explicit actions, knowledge acceptance, and recovery."""
import json
from pathlib import Path
import sys

from sqlalchemy import select

from orbehelm.core import OrbeHelmError
from orbehelm.mcp_bridge import Bridge
from orbehelm.delegation_runner import recover_delegation, execute_operator_qa
from .coordination import Coordinator, accept_knowledge
from .database import Store
from .models import Task, LogicalOrbe
from .projects import get_project


def dispatch(args, root):
    if args.dry_run:
        raise OrbeHelmError('Task actions do not support --dry-run; use tasks context to inspect without execution')
    store = Store(root)
    try:
        project = get_project(store, str(args.project))
        if args.command == 'memory' and args.action == 'accept' and args.name:
            return accept_knowledge(store, project.id, args.name, args.replace_id)
        if args.command == 'tasks' and args.action in {None, 'list'}:
            with store.read() as db:
                tasks = db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.created_at)).all()
                return [{'id': task.id, 'unique_key': task.unique_key, 'state': task.state, 'version': task.version,
                         'owner_id': task.owner_id, 'workspace': task.workspace,
                         'submission_count': task.rounds, 'submission_limit': None,
                         'orbes': [{'id': row.id, 'profile': row.profile, 'orbe_key': row.orbe_key,
                                       'parent_id': row.parent_id} for row in db.scalars(
                             select(LogicalOrbe).where(LogicalOrbe.task_id == task.id))]} for task in tasks]
        if not args.actor:
            raise OrbeHelmError('This operation requires --actor=<logical-orbe-id>; use tasks list to find it')
        binding = None if args.command == 'tasks' and args.action == 'recover' else args.delegation
        coordinator = Coordinator(store, args.actor, binding, args.configuration_id)
        if coordinator.context()['project_id'] != project.id:
            raise OrbeHelmError('Logical orbe is outside the selected project')
        if args.command == 'tasks' and args.action in {'context', 'show'}:
            return coordinator.context()
        if args.command == 'tasks' and args.action == 'reopen':
            return coordinator.reopen(args.expected_version)
        if args.command == 'tasks' and args.action == 'recover' and args.delegation:
            return recover_delegation(coordinator, args.delegation, args.confirm_stopped)
        operations = {('tasks', 'submit'): 'submit_work', ('tasks', 'delegate'): 'delegate',
                      ('memory', 'save'): 'save_knowledge', ('memory', 'read'): 'read_artifact',
                      ('tasks', 'approve'): 'approve', ('tasks', 'reject'): 'reject', ('tasks', 'qa'): 'qa'}
        operation = operations.get((args.command, args.action))
        if operation is None or not args.data_file:
            raise OrbeHelmError('Use tasks list|context|submit|delegate|approve|reject|qa|reopen|recover or memory save|read|accept; writes require --data-file')
        if args.data_file == '-':
            encoded = sys.stdin.read(1024 * 1024 + 1)
        else:
            with Path(args.data_file).open(encoding='utf-8') as handle:
                encoded = handle.read(1024 * 1024 + 1)
        if len(encoded.encode()) > 1024 * 1024:
            raise OrbeHelmError('Operation JSON exceeds its size limit')
        data = json.loads(encoded)
        if operation in {'approve', 'reject', 'qa'}:
            coordinator._operator()
            required = {'candidate_id', 'key', 'expected_version'} | (
                {'instructions'} if operation == 'qa' else {'operator', 'summary'})
            if not isinstance(data, dict) or set(data) != required:
                raise OrbeHelmError('Operator action JSON requires exactly: ' + ', '.join(sorted(required)))
            if args.delegation:
                raise OrbeHelmError('A delegated child cannot perform operator actions')
            if operation == 'qa':
                if not args.agent:
                    raise OrbeHelmError('Manual QA requires --agent')
                return execute_operator_qa(coordinator, args.agent, **data)
            return coordinator.human_decision(decision='approved' if operation == 'approve' else 'rejected', **data)
        return Bridge(store, args.actor, args.agent, args.delegation, args.configuration_id).call(operation, data)
    finally:
        store.close()

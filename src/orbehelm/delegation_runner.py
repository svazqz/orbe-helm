"""Execute one explicit native child and promote its staged result only after verification."""
import os
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from .core import OrbeHelmError, digest
from .adapters import launch
from .service import require_server
from .product.catalog import Conflict
from .product.coordination import Coordinator, safe_path
from .product.database import product_lock
from .product.models import Delegation, Task, TaskArtifact, LogicalOrbe, Project, ProjectConfiguration
from .product.projects import resolve_configuration, build_project


def delegation_result(coordinator, record):
    record = coordinator.persist_assessment(record)
    if record.get('result_id'):
        key = 'result' if record['status'] == 'completed' else 'unapproved_staged_result'
        return {**record, key: coordinator.read_artifact(record['result_id'])['data']}
    return record


def execute_delegation(coordinator, agent, profile, key, instructions, expected_version, cancel=None, timeout=300):
    if profile == 'parallel':
        return execute_assessments(coordinator, agent, key, instructions, expected_version, cancel, timeout)
    require_server(coordinator.store.root)
    record = coordinator.create_delegation(profile, key, instructions, expected_version)
    if record['status'] != 'queued':
        return delegation_result(coordinator, record)
    try:
        record = coordinator.claim(record['id'])
    except Conflict:
        # A concurrent identical request may have claimed it after our read.
        with coordinator.store.read() as db:
            current = db.get(Delegation, record['id'])
            return delegation_result(coordinator, coordinator._delegation_dict(current))
    store = coordinator.store
    try:
        with store.read() as db:
            item = db.get(Delegation, record['id'])
            task = db.get(Task, item.task_id)
            artifact = db.get(TaskArtifact, item.candidate_id)
            child = db.get(LogicalOrbe, item.child_id)
            project = db.get(Project, task.project_id)
        candidate = coordinator.read_artifact(artifact.id)
        with store.read() as db:
            config = db.get(ProjectConfiguration, candidate['data']['configuration_id'])
            if config is None or config.project_id != project.id:
                raise OrbeHelmError('Candidate configuration is unavailable')
        work = safe_path(store.root, f'state/projects/{project.id}/tasks/{task.id}/workspaces/{item.id}')
        if work.exists():
            raise Conflict('Delegation workspace already exists; inspect and recover this request rather than rerunning it')
        work.mkdir(parents=True)
        source = safe_path(store.root, artifact.path) / 'files'
        for relative in candidate['files']:
            target = safe_path(work, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(safe_path(source, relative), target)
        with product_lock(store.root):
            resolved = resolve_configuration(store, project, config, profile=profile, persist=True)
        output, _ = build_project(store, resolved, agent)

        def started(pid):
            with product_lock(store.root), store.write() as db:
                current = db.get(Delegation, item.id)
                current.child_pid = pid

        prompt = ('Perform the delegated ' + profile + ' action. Read the OrbeHelm task context, inspect '
                  'the immutable submitted source in this working copy, and verify the relevant claims. '
                  'For external artifact_refs, use your profile MCPs to inspect the exact pinned revision; '
                  'a URL alone does not establish that revision. Report blocked if it cannot be verified. '
                  'Do not change submitted source files. You must call the orbehelm complete_delegation tool '
                  'with a structured result before exiting. Request: ' + instructions)
        from .memory_runtime import native_session
        code = launch(store.root, output, resolved, agent, prompt=prompt,
            unique_key=child.orbe_key, actor_id=child.id, delegation_id=item.id,
            workspace=work, headless=True, cancel=cancel, timeout=timeout, on_start=started,
            memory_factory=native_session)
        # QA may create caches/test output, but every submitted input must remain identical.
        for relative, metadata in candidate['files'].items():
            path = safe_path(work, relative)
            if (not path.is_file() or digest(path.read_bytes()) != metadata['sha256']
                    or bool(path.stat().st_mode & 0o111) != metadata['executable']):
                raise OrbeHelmError('Child modified a submitted input; its result was not approved')
        coordinator.read_artifact(artifact.id)
        finished = coordinator.finish(item.id, code == 0 and not (cancel is not None and cancel.is_set()),
                                       'cancelled' if cancel is not None and cancel.is_set() else 'failed')
        return delegation_result(coordinator, finished)
    except (OrbeHelmError, OSError, ValueError):
        coordinator.finish(record['id'], False, 'cancelled' if cancel is not None and cancel.is_set() else 'failed')
        raise
    except KeyboardInterrupt:
        coordinator.finish(record['id'], False, 'interrupted')
        raise


def execute_assessments(coordinator, agent, key, instructions, expected_version, cancel=None, timeout=300):
    """Queue both gates before executing either, retaining individual retry identity."""
    gates = coordinator.create_assessments(key, instructions, expected_version)
    candidate = gates['reviewer']['candidate_id']
    results = {}
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix='orbehelm-assessment') as pool:
        futures = {role: pool.submit(execute_delegation, coordinator, agent, role, key,
                    instructions, expected_version, cancel, timeout) for role in ('reviewer', 'qa')}
        for role, future in futures.items():
            try:
                results[role] = future.result()
            except (OrbeHelmError, OSError, ValueError) as error:
                results[role] = {'status': 'failed', 'error': str(error)}
    return {'candidate_id': candidate, 'assessments': results, 'state': coordinator.context()['state']}


def recover_delegation(coordinator, delegation_id, confirm_stopped=False):
    """Never kill a persisted PID or automatically repeat uncertain model work."""
    with coordinator.store.read() as db:
        item = db.get(Delegation, delegation_id)
        if not item or item.parent_id != coordinator.actor_id:
            raise OrbeHelmError('Delegation is outside this parent orbe')
        if item.status not in {'running', 'result_pending', 'queued'}:
            return coordinator._delegation_dict(item)
        for pid, group in [(item.worker_pid, False), (item.child_pid, True)]:
            if pid is None:
                continue
            try:
                (os.killpg if group else os.kill)(pid, 0)
            except ProcessLookupError:
                continue
            except PermissionError as error:
                raise Conflict('Cannot verify the old worker has stopped') from error
            raise Conflict('The old worker or child process group still exists; recovery will not duplicate its work')
        if item.status != 'queued' and item.child_pid is None and not confirm_stopped:
            raise Conflict('Dispatch outcome is unknown. Inspect the native processes, then use --confirm-stopped.')
    if item.status == 'queued':
        coordinator.claim(item.id)
    return coordinator.finish(item.id, False, 'interrupted')

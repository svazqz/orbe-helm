"""Task-scoped memory and deterministic delegation. No model calls inside transactions."""
import json
import os
from pathlib import Path
import re
import tempfile

from sqlalchemy import select, func

from orbehelm.core import OrbeHelmError, canonical, digest, identifier
from orbehelm.snapshots import capture_file, manifest
from .catalog import Conflict
from .database import product_lock
from .models import (Task, LogicalOrbe, TaskArtifact, Knowledge, Delegation, TaskEvent,
                     Project, now)

MAX_TEXT = 65536
MAX_CONTEXT = 200000
RESULTS = {'reviewer': {'approved', 'changes_requested', 'blocked'},
           'qa': {'passed', 'failed', 'blocked'}}


def text_value(value, label, limit=MAX_TEXT):
    if not isinstance(value, str) or not value.strip() or len(value.encode()) > limit or '\x00' in value:
        raise OrbeHelmError(f'{label} must be nonempty text of at most {limit} bytes')
    return value


def unique_key(value):
    text_value(value, 'Unique key', 128)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]*', value) or any(part in {'', '.', '..'} for part in value.split('/')):
        raise OrbeHelmError('Unique key must use letters, numbers, dots, hyphens, underscores, or nonempty path segments')
    return value


def stable_id(*parts):
    return digest(canonical(parts).encode())[:32]


def safe_path(root, relative):
    """Never follow symlinks when reading or materializing coordination state."""
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise OrbeHelmError('Expected a contained relative artifact path')
    target = Path(root).resolve()
    for part in path.parts:
        target = target / part
        if target.is_symlink():
            raise OrbeHelmError('Coordination paths must not contain symlinks')
    return target


def ensure_orbe(store, project, key, profile, spec=None, workspace=None, parent_id=None, orbe_key=None):
    key = unique_key(key)
    identifier(profile)
    if spec:
        identifier(spec)
    explicit_workspace = workspace is not None
    workspace = str(Path(workspace or project.path).resolve())
    if not Path(workspace).is_dir():
        raise OrbeHelmError('The task workspace must be an existing directory')
    task_id = stable_id('task', project.id, key)
    orbe_key = orbe_key or key
    logical_id = stable_id('logical', project.id, profile, spec or '', orbe_key)
    with product_lock(store.root), store.write() as db:
        task = db.get(Task, task_id)
        if task is None:
            task = Task(id=task_id, project_id=project.id, unique_key=key, workspace=workspace)
            db.add(task)
            db.flush()
        elif explicit_workspace and task.workspace != workspace:
            raise Conflict('This task key already belongs to another workspace')
        if parent_id:
            parent = db.get(LogicalOrbe, parent_id)
            if parent is None or parent.task_id != task.id:
                raise OrbeHelmError('Parent logical orbe is outside this task')
        logical = db.get(LogicalOrbe, logical_id)
        if logical is None:
            logical = LogicalOrbe(id=logical_id, task_id=task.id, profile=profile,
                specialization=spec or '', orbe_key=orbe_key, parent_id=parent_id)
            db.add(logical)
        elif logical.task_id != task.id or logical.parent_id != parent_id:
            raise Conflict('Logical orbe identity is already assigned to another task or parent')
        if profile == 'developer' and parent_id is None:
            if task.owner_id not in {None, logical_id}:
                raise Conflict('This task key already has a developer owner; use a distinct task key')
            task.owner_id = logical_id
    return logical_id


class Coordinator:
    def __init__(self, store, actor_id, delegation_id=None, configuration_id=None):
        self.store, self.actor_id, self.delegation_id = store, actor_id, delegation_id
        self.configuration_id = configuration_id
        with store.read() as db:
            actor, task = self._scope(db)
            if delegation_id:
                delegation = db.get(Delegation, delegation_id)
                if not delegation or delegation.child_id != actor.id or delegation.task_id != task.id:
                    raise OrbeHelmError('Delegation does not belong to this logical orbe')

    def _scope(self, db):
        actor = db.get(LogicalOrbe, self.actor_id)
        if actor is None:
            raise OrbeHelmError('Unknown logical orbe')
        task = db.get(Task, actor.task_id)
        if task is None:
            raise OrbeHelmError('Unknown task')
        return actor, task

    @staticmethod
    def _version(task, expected):
        if type(expected) is not int or task.version != expected:
            raise Conflict('Task changed; read its current context before retrying')

    @staticmethod
    def _developer(actor, task):
        if actor.profile != 'developer' or actor.parent_id is not None or task.owner_id != actor.id:
            raise OrbeHelmError('Only a root developer orbe can control this task workflow')

    def _event(self, db, task, kind, payload, actor_id=None):
        sequence = (db.scalar(select(func.max(TaskEvent.sequence)).where(TaskEvent.task_id == task.id)) or 0) + 1
        db.add(TaskEvent(task_id=task.id, sequence=sequence, actor_id=actor_id or self.actor_id,
                         kind=kind, payload=payload))
        task.version += 1

    def _artifact(self, db, task, kind, payload, files=None):
        record = {'kind': kind, 'data': payload, 'files': manifest(files or {})}
        encoded = canonical(record).encode()
        sha = digest(encoded)
        artifact_id = stable_id(task.id, kind, sha)
        existing = db.get(TaskArtifact, artifact_id)
        if existing:
            self._read(db, task, existing)
            return existing
        folder = (f'state/projects/{task.project_id}/knowledge' if kind == 'project_knowledge' else
                  f'state/projects/{task.project_id}/tasks/{task.id}/artifacts')
        relative = folder + '/' + sha
        target = safe_path(self.store.root, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with tempfile.TemporaryDirectory(dir=target.parent, prefix='.artifact-') as temporary:
                staged = Path(temporary) / 'data'
                staged.mkdir()
                (staged / 'record.json').write_bytes(encoded)
                for name, entry in (files or {}).items():
                    path = safe_path(staged / 'files', name)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(entry['content'])
                    path.chmod(0o755 if entry['executable'] else 0o644)
                staged.rename(target)
        artifact = TaskArtifact(id=artifact_id, task_id=task.id, author_id=self.actor_id,
                               kind=kind, content_hash=sha, path=relative)
        db.add(artifact)
        db.flush()
        self._read(db, task, artifact)
        return artifact

    def _read(self, db, task, artifact):
        if artifact.task_id != task.id:
            accepted = db.scalar(select(Knowledge.id).where(Knowledge.artifact_id == artifact.id,
                Knowledge.project_id == task.project_id, Knowledge.status == 'accepted'))
            pinned = False
            if accepted is None and artifact.kind == 'project_knowledge':
                for context in db.scalars(select(TaskArtifact).where(TaskArtifact.task_id == task.id,
                                                                   TaskArtifact.kind == 'context')):
                    if artifact.id in self._read(db, task, context)['data']['knowledge_artifacts']:
                        pinned = True
                        break
            if accepted is None and not pinned:
                raise OrbeHelmError('Artifact is outside this task')
        folder = safe_path(self.store.root, artifact.path)
        encoded = (folder / 'record.json').read_bytes()
        if len(encoded) > 2 * 1024 * 1024 or digest(encoded) != artifact.content_hash:
            raise OrbeHelmError('Artifact content is corrupted')
        record = json.loads(encoded)
        for name, entry in record['files'].items():
            path = safe_path(folder / 'files', name)
            if digest(path.read_bytes()) != entry['sha256'] or bool(path.stat().st_mode & 0o111) != entry['executable']:
                raise OrbeHelmError('Candidate source is corrupted')
        return record

    def read_artifact(self, artifact_id):
        with self.store.read() as db:
            _, task = self._scope(db)
            artifact = db.get(TaskArtifact, artifact_id)
            if artifact is None:
                raise OrbeHelmError('Artifact not found')
            return self._read(db, task, artifact)

    def context(self):
        with self.store.read() as db:
            actor, task = self._scope(db)
            knowledge = db.scalars(select(Knowledge).where(
                (Knowledge.task_id == task.id) | ((Knowledge.project_id == task.project_id) &
                (Knowledge.status == 'accepted'))).order_by(Knowledge.version.desc())).all()
            latest = {}
            for item in knowledge:
                if item.status != 'superseded':
                    category = 'accepted' if item.status == 'accepted' else 'proposal' if item.scope == 'project' else 'task'
                    latest.setdefault((item.scope, item.key, category), item)
            facts = [{'id': item.id, 'key': item.key, 'scope': item.scope, 'version': item.version,
                      'status': item.status, 'artifact_id': item.artifact_id}
                     for item in latest.values()]
            delegations = db.scalars(select(Delegation).where(Delegation.task_id == task.id)
                                    .order_by(Delegation.created_at)).all()
            # Child context is bound to the requested candidate, never silently to a later one.
            binding = db.get(Delegation, self.delegation_id) if self.delegation_id else None
            if binding:
                frozen = self._read(db, task, db.get(TaskArtifact, binding.context_id))['data']
                facts = frozen['knowledge']
            candidate_id = binding.candidate_id if binding else task.candidate_id
            result = {'task_id': task.id, 'project_id': task.project_id, 'unique_key': task.unique_key,
                'logical_orbe_id': actor.id, 'orbe_key': actor.orbe_key, 'profile': actor.profile,
                'parent_id': actor.parent_id, 'workspace': task.workspace, 'state': task.state,
                'version': task.version, 'rounds': task.rounds, 'max_rounds': task.max_rounds,
                'candidate_id': candidate_id, 'knowledge': facts,
                'delegations': [self._delegation_dict(item) for item in delegations]}
            if candidate_id:
                candidate = db.get(TaskArtifact, candidate_id)
                result['candidate'] = self._read(db, task, candidate)['data']
            if binding:
                result['request'] = self._delegation_dict(binding) | {'instructions': binding.instructions}
            events = db.scalars(select(TaskEvent).where(TaskEvent.task_id == task.id)
                                .order_by(TaskEvent.sequence.desc()).limit(30)).all()
            result['events'] = [{'sequence': item.sequence, 'kind': item.kind, 'payload': item.payload} for item in reversed(events)]
            if len(canonical(result).encode()) > MAX_CONTEXT:
                raise OrbeHelmError('Context exceeds its bound; retrieve artifacts individually')
            return result

    def save_knowledge(self, key, content, scope, expected_version):
        unique_key(key)
        text_value(content, 'Knowledge content')
        if scope not in {'task', 'project'} or type(expected_version) is not int or expected_version < 0:
            raise OrbeHelmError('Choose task/project scope and a nonnegative expected knowledge version')
        with product_lock(self.store.root), self.store.write() as db:
            actor, task = self._scope(db)
            if self.delegation_id:
                binding = db.get(Delegation, self.delegation_id)
                if binding.status not in {'running', 'result_pending'} or binding.candidate_id != task.candidate_id:
                    raise Conflict('The child delegation is no longer active')
            previous = db.scalars(select(Knowledge).where(Knowledge.task_id == task.id,
                Knowledge.scope == scope, Knowledge.key == key).order_by(Knowledge.version.desc())).first()
            version = previous.version if previous else 0
            if version != expected_version:
                if previous and version == expected_version + 1:
                    saved = self._read(db, task, db.get(TaskArtifact, previous.artifact_id))
                    if saved['data']['content'] == content:
                        return {'id': previous.id, 'version': previous.version, 'artifact_id': previous.artifact_id}
                raise Conflict('Knowledge changed; read its current version before saving')
            artifact = self._artifact(db, task, 'project_knowledge' if scope == 'project' else 'task_knowledge',
                                      {'key': key, 'content': content})
            item = Knowledge(project_id=task.project_id, task_id=task.id, author_id=actor.id, key=key,
                             scope=scope, version=version + 1, status='proposed' if scope == 'project' else 'reported',
                             artifact_id=artifact.id)
            db.add(item)
            db.flush()
            self._event(db, task, 'knowledge.saved', {'knowledge_id': item.id, 'artifact_id': artifact.id})
            return {'id': item.id, 'version': item.version, 'artifact_id': artifact.id}

    def submit_work(self, paths, handoff, submission_key, expected_version, requirements):
        text_value(handoff, 'Handoff')
        text_value(requirements, 'Requirements and acceptance criteria')
        unique_key(submission_key)
        if not isinstance(paths, list) or not paths or len(paths) > 100 or any(not isinstance(path, str) for path in paths):
            raise OrbeHelmError('Provide 1–100 relative source file/directory paths')
        with self.store.read() as db:
            actor, task = self._scope(db)
            self._developer(actor, task)
            workspace = Path(task.workspace)
            configuration_id = self.configuration_id or db.get(Project, task.project_id).active_revision
            from .models import ProjectConfiguration
            config = db.get(ProjectConfiguration, configuration_id)
            if not config or config.project_id != task.project_id:
                raise OrbeHelmError('Configuration does not belong to this project')
        files = {}
        for relative in paths:
            path = safe_path(workspace, relative)
            if not relative or relative == '.':
                raise OrbeHelmError('List explicit source folders/files rather than the workspace root')
            selected = path.rglob('*') if path.is_dir() else [path]
            for scanned, item in enumerate(selected):
                if scanned > 8192:
                    raise OrbeHelmError('Candidate source traversal exceeds its bound')
                if item.is_symlink():
                    raise OrbeHelmError('Candidate sources must not contain symlinks')
                if item.is_file():
                    capture_file(workspace, item.relative_to(workspace).as_posix(), files)
        if not files:
            raise OrbeHelmError('No candidate source files were selected')
        payload = {'handoff': handoff, 'requirements': requirements, 'submission_key': submission_key, 'source_scope': sorted(set(paths)),
                   'source_digest': digest(canonical(manifest(files)).encode()), 'owner_id': self.actor_id,
                   'configuration_id': configuration_id}
        with product_lock(self.store.root), self.store.write() as db:
            actor, task = self._scope(db)
            existing = db.scalars(select(TaskArtifact).where(TaskArtifact.task_id == task.id,
                                                            TaskArtifact.kind == 'candidate')).all()
            for artifact in existing:
                recorded = self._read(db, task, artifact)['data']
                if recorded['submission_key'] == submission_key:
                    if recorded != payload:
                        raise Conflict('Submission key already identifies different source or handoff content')
                    return {'candidate_id': artifact.id, 'version': task.version, 'state': task.state}
            self._version(task, expected_version)
            if task.state not in {'developing', 'blocked'} or task.rounds >= task.max_rounds:
                raise Conflict('Task is not ready for submission or has reached its round limit')
            live = db.scalar(select(Delegation.id).where(Delegation.task_id == task.id,
                Delegation.status.in_(['queued', 'running', 'result_pending'])))
            if live:
                raise Conflict('Resolve the existing delegation before submitting another candidate')
            artifact = self._artifact(db, task, 'candidate', payload, files)
            task.candidate_id, task.state = artifact.id, 'awaiting_review'
            task.rounds += 1
            self._event(db, task, 'work.submitted', {'candidate_id': artifact.id, 'source_digest': payload['source_digest']})
            return {'candidate_id': artifact.id, 'version': task.version, 'state': task.state}

    @staticmethod
    def _delegation_dict(item):
        return {key: getattr(item, key) for key in ('id', 'parent_id', 'child_id', 'profile', 'key', 'context_id',
            'candidate_id', 'status', 'result_id', 'created_at', 'finished_at')}

    def create_delegation(self, profile, key, instructions, expected_version):
        if profile not in RESULTS:
            raise OrbeHelmError('Only reviewer and QA child profiles are supported')
        unique_key(key)
        text_value(instructions, 'Delegation instructions')
        with product_lock(self.store.root), self.store.write() as db:
            actor, task = self._scope(db)
            self._developer(actor, task)
            existing = db.scalars(select(Delegation).where(Delegation.parent_id == actor.id,
                Delegation.profile == profile, Delegation.key == key,
                Delegation.candidate_id == task.candidate_id)).first()
            if existing:
                if existing.instructions != instructions:
                    raise Conflict('Delegation key already has different instructions')
                return self._delegation_dict(existing)
            self._version(task, expected_version)
            expected = 'awaiting_review' if profile == 'reviewer' else 'reviewed'
            if task.state != expected or task.candidate_id is None:
                raise Conflict(f'{profile} delegation requires task state {expected}')
            candidate = db.get(TaskArtifact, task.candidate_id)
            if self._read(db, task, candidate)['data']['owner_id'] != actor.id:
                raise OrbeHelmError('Only the submitted candidate owner may delegate it')
            orbe_key = task.unique_key[:60] + '/child-' + stable_id(actor.id, profile, key)
            child_id = stable_id('logical', task.project_id, profile, '', orbe_key)
            if db.get(LogicalOrbe, child_id) is None:
                db.add(LogicalOrbe(id=child_id, task_id=task.id, profile=profile,
                    specialization='', orbe_key=orbe_key, parent_id=actor.id))
                db.flush()
            knowledge = db.scalars(select(Knowledge).where((Knowledge.task_id == task.id) |
                ((Knowledge.project_id == task.project_id) & (Knowledge.status == 'accepted')))
                .order_by(Knowledge.version.desc())).all()
            facts, seen = [], set()
            for fact in knowledge:
                category = 'accepted' if fact.status == 'accepted' else 'proposal' if fact.scope == 'project' else 'task'
                identity = fact.scope, fact.key, category
                if fact.status != 'superseded' and identity not in seen:
                    facts.append({field: getattr(fact, field) for field in
                                  ('id', 'key', 'scope', 'version', 'status', 'artifact_id')})
                    seen.add(identity)
            frozen = self._artifact(db, task, 'context', {'candidate_id': task.candidate_id,
                'task_version': task.version, 'instructions': instructions, 'knowledge': facts,
                'knowledge_artifacts': [fact['artifact_id'] for fact in facts]})
            item = Delegation(task_id=task.id, parent_id=actor.id, child_id=child_id,
                candidate_id=task.candidate_id, context_id=frozen.id, profile=profile, key=key, instructions=instructions)
            db.add(item)
            db.flush()
            task.state = 'reviewing' if profile == 'reviewer' else 'testing'
            self._event(db, task, 'delegation.created', {'delegation_id': item.id, 'child_id': child_id})
            return self._delegation_dict(item)

    def claim(self, delegation_id):
        with product_lock(self.store.root), self.store.write() as db:
            actor, task = self._scope(db)
            item = db.get(Delegation, delegation_id)
            if not item or item.parent_id != actor.id or item.task_id != task.id:
                raise OrbeHelmError('Delegation is outside this parent orbe')
            if item.status != 'queued' or item.candidate_id != task.candidate_id:
                raise Conflict('Delegation is already claimed or belongs to an older candidate')
            item.status, item.worker_pid = 'running', os.getpid()
            self._event(db, task, 'delegation.started', {'delegation_id': item.id})
            return self._delegation_dict(item)

    def stage_result(self, status, summary, findings, evidence):
        text_value(summary, 'Result summary')
        if not isinstance(findings, list) or len(findings) > 100 or any(not isinstance(x, str) or not x.strip() or len(x.encode()) > 8192 for x in findings):
            raise OrbeHelmError('Findings must be a bounded list of nonempty strings')
        if not isinstance(evidence, list) or len(evidence) > 100 or any(not isinstance(x, str) for x in evidence):
            raise OrbeHelmError('Evidence must be artifact IDs from this task')
        with product_lock(self.store.root), self.store.write() as db:
            actor, task = self._scope(db)
            item = db.get(Delegation, self.delegation_id) if self.delegation_id else None
            if not item or item.child_id != actor.id or status not in RESULTS.get(actor.profile, set()):
                raise OrbeHelmError('This logical orbe cannot complete that delegation or result type')
            if item.candidate_id != task.candidate_id or item.status not in {'running', 'result_pending'}:
                raise Conflict('Delegation is inactive or its candidate is stale')
            for artifact_id in evidence:
                artifact = db.get(TaskArtifact, artifact_id)
                if artifact is None or artifact.task_id != task.id:
                    raise OrbeHelmError('Evidence is outside this task')
                self._read(db, task, artifact)
            payload = {'status': status, 'summary': summary, 'findings': findings, 'evidence': evidence,
                       'candidate_id': item.candidate_id, 'delegation_id': item.id}
            if item.result_id:
                if self._read(db, task, db.get(TaskArtifact, item.result_id))['data'] != payload:
                    raise Conflict('A different result has already been staged')
                return {'result_id': item.result_id, 'status': item.status}
            artifact = self._artifact(db, task, 'delegation_result', payload)
            item.result_id, item.status = artifact.id, 'result_pending'
            self._event(db, task, 'delegation.result_staged', {'delegation_id': item.id, 'result_id': artifact.id})
            return {'result_id': artifact.id, 'status': item.status}

    def finish(self, delegation_id, successful, reason='failed'):
        with product_lock(self.store.root), self.store.write() as db:
            actor, task = self._scope(db)
            item = db.get(Delegation, delegation_id)
            if not item or item.parent_id != actor.id or item.task_id != task.id:
                raise OrbeHelmError('Delegation is outside this parent orbe')
            if item.status in {'completed', 'failed', 'cancelled', 'interrupted'}:
                return self._delegation_dict(item)
            if item.status not in {'running', 'result_pending'}:
                raise Conflict('Delegation has not been started')
            if successful and item.result_id and item.candidate_id == task.candidate_id:
                result = self._read(db, task, db.get(TaskArtifact, item.result_id))['data']
                transitions = {'approved': 'reviewed', 'changes_requested': 'developing',
                               'passed': 'complete', 'failed': 'developing', 'blocked': 'blocked'}
                task.state, item.status = transitions[result['status']], 'completed'
            else:
                task.state = 'blocked'
                item.status = reason if reason in {'failed', 'cancelled', 'interrupted'} else 'failed'
            item.finished_at = now()
            self._event(db, task, 'delegation.' + item.status, {'delegation_id': item.id, 'result_id': item.result_id})
            return self._delegation_dict(item)

    def reopen(self, expected_version, round_limit=None):
        with product_lock(self.store.root), self.store.write() as db:
            actor, task = self._scope(db)
            self._developer(actor, task)
            self._version(task, expected_version)
            if task.state not in {'blocked', 'complete'}:
                raise Conflict('Only blocked or completed tasks can be explicitly reopened')
            if db.scalar(select(Delegation.id).where(Delegation.task_id == task.id,
                         Delegation.status.in_(['queued', 'running', 'result_pending']))):
                raise Conflict('A pending delegation must be resolved first')
            if round_limit is not None:
                if type(round_limit) is not int or not task.rounds < round_limit <= 100:
                    raise OrbeHelmError('Round limit must exceed completed submissions and be at most 100')
                task.max_rounds = round_limit
            task.state = 'developing'
            self._event(db, task, 'task.reopened', {})
            return {'state': task.state, 'version': task.version}


def accept_knowledge(store, project_id, knowledge_id, replace_id=None):
    """Operator-only promotion; never exposed as a model tool."""
    with product_lock(store.root), store.write() as db:
        item = db.get(Knowledge, knowledge_id)
        if not item or item.project_id != project_id or item.scope != 'project':
            raise OrbeHelmError('Project knowledge proposal not found')
        previous = db.scalars(select(Knowledge).where(Knowledge.project_id == project_id,
            Knowledge.key == item.key, Knowledge.status == 'accepted')).first()
        if previous and previous.id != item.id:
            if previous.id != replace_id:
                raise Conflict('An accepted entry exists; explicitly supply its ID as the replacement')
            previous.status = 'superseded'
        item.status = 'accepted'
        task = db.get(Task, item.task_id)
        Coordinator(store, item.author_id)._event(db, task, 'knowledge.accepted', {'knowledge_id': item.id})
        return {'id': item.id, 'status': item.status}

"""Task-scoped memory and deterministic delegation. No model calls inside transactions."""
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

from sqlalchemy import select, func

from orbehelm.core import OrbeHelmError, canonical, digest, identifier
from orbehelm.snapshots import capture_file, manifest
from .catalog import Conflict
from .database import product_lock
from .models import (Task, LogicalOrbe, TaskArtifact, Knowledge, Delegation, TaskEvent,
                     Project, MemorySource, Conversation, MemoryBinding, MemoryRead,
                     KUnitRecord, KnowledgeMetadata, now)
from ..domain.knowledge.retrieval import outcome_metadata, instruction_like

from orbehelm.domain.coordination.policies import (
    MAX_TEXT, RESULTS, text_value, unique_key, stable_id, require_version,
    require_developer, require_submission, require_delegation, completed_state,
    require_reopen, assessment_state,
)

MAX_CONTEXT = 200000


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
    key = '' if key is None else unique_key(key)
    identifier(profile)
    if spec:
        identifier(spec)
    explicit_workspace = workspace is not None
    workspace = str(Path(workspace or project.path).resolve())
    if not Path(workspace).is_dir():
        raise OrbeHelmError('The task workspace must be an existing directory')
    task_id = stable_id('task', project.id, key)
    orbe_key = orbe_key or key
    logical_id = stable_id('logical', project.id, profile, '', orbe_key)
    with product_lock(store.root), store.write() as db:
        task = db.get(Task, task_id)
        if task is None:
            task = Task(id=task_id, project_id=project.id, unique_key=key, workspace=workspace)
            db.add(task)
            db.flush()
        elif explicit_workspace and task.workspace != workspace:
            raise Conflict('This task key already belongs to another workspace')
        # Adopt the recorded root identity instead of creating a new owner when
        # specialization changes. Historical actors and native homes remain intact.
        if profile == 'developer' and parent_id is None and task.owner_id:
            logical_id = task.owner_id
        elif parent_id is None:
            old = db.scalars(select(LogicalOrbe).where(LogicalOrbe.task_id == task.id,
                LogicalOrbe.profile == profile, LogicalOrbe.orbe_key == orbe_key,
                LogicalOrbe.parent_id.is_(None)).order_by(LogicalOrbe.created_at, LogicalOrbe.id)).first()
            if old:
                logical_id = old.id
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
        require_version(task.version, expected)

    @staticmethod
    def _developer(actor, task):
        require_developer(actor.id, actor.profile, actor.parent_id, task.owner_id)

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
            actor, task = self._scope(db)
            artifact = db.get(TaskArtifact, artifact_id)
            if artifact is None:
                raise OrbeHelmError('Artifact not found')
            result = self._read(db, task, artifact)
            if artifact.kind in {'task_knowledge', 'project_knowledge'} and artifact.author_id != actor.id:
                if not self._knowledge_audience(actor, result['data']):
                    raise OrbeHelmError('Unclassified or role-restricted knowledge is not available to this context')
            return result

    @staticmethod
    def _knowledge_audience(actor, payload):
        metadata = payload.get('outcome')
        if not metadata or instruction_like(payload.get('content', '')):
            return False
        audience = metadata['audience']
        return '*' in audience or actor.profile in audience or actor.profile + ':' + actor.specialization in audience

    def context(self):
        with self.store.read() as db:
            actor, task = self._scope(db)
            knowledge = db.scalars(select(Knowledge).where(
                (Knowledge.task_id == task.id) | ((Knowledge.project_id == task.project_id) &
                (Knowledge.status == 'accepted'))).order_by(Knowledge.version.desc())).all()
            latest = {}
            for item in knowledge:
                payload = self._read(db, task, db.get(TaskArtifact, item.artifact_id))['data']
                if item.status != 'superseded' and self._knowledge_audience(actor, payload):
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
                'version': task.version, 'rounds': task.rounds, 'max_rounds': None,
                'submission_count': task.rounds, 'submission_limit': None,
                'candidate_id': candidate_id, 'knowledge': facts,
                'delegations': [self._delegation_dict(item) for item in delegations]}
            if candidate_id:
                candidate = db.get(TaskArtifact, candidate_id)
                result['candidate'] = self._read(db, task, candidate)['data']
                result['human_decision'] = self._human_decision(db, task)
            result['next_action'] = {'awaiting_review': 'developer_request_reviewer',
                'awaiting_human_approval': 'operator_review', 'approved_for_qa': 'operator_launch_qa',
                'reviewing': 'wait_for_reviewer', 'testing': 'wait_for_qa',
                'complete': 'none'}.get(task.state, 'developer_action')
            if binding:
                result['request'] = self._delegation_dict(binding) | {'instructions': binding.instructions}
            events = db.scalars(select(TaskEvent).where(TaskEvent.task_id == task.id)
                                .order_by(TaskEvent.sequence.desc()).limit(30)).all()
            result['events'] = [{'sequence': item.sequence, 'kind': item.kind, 'payload': item.payload} for item in reversed(events)]
            if len(canonical(result).encode()) > MAX_CONTEXT:
                raise OrbeHelmError('Context exceeds its bound; retrieve artifacts individually')
            return result

    def save_knowledge(self, key, content, scope, expected_version, kind=None, evidence=None, audience=None, evidence_state='proposed'):
        unique_key(key)
        text_value(content, 'Knowledge content')
        metadata = outcome_metadata(kind, evidence, audience, evidence_state) if kind is not None else None
        if metadata and instruction_like(content):
            raise OrbeHelmError('Instruction-like knowledge must remain in definitions or private pending memory')
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
                    if saved['data']['content'] == content and saved['data'].get('outcome') == metadata:
                        return {'id': previous.id, 'version': previous.version, 'artifact_id': previous.artifact_id}
                raise Conflict('Knowledge changed; read its current version before saving')
            artifact = self._artifact(db, task, 'project_knowledge' if scope == 'project' else 'task_knowledge',
                                      {'key': key, 'content': content, **({'outcome': metadata} if metadata else {})})
            item = Knowledge(project_id=task.project_id, task_id=task.id, author_id=actor.id, key=key,
                             scope=scope, version=version + 1, status='proposed' if scope == 'project' else 'reported',
                             artifact_id=artifact.id)
            db.add(item)
            db.flush()
            self._event(db, task, 'knowledge.saved', {'knowledge_id': item.id, 'artifact_id': artifact.id})
            return {'id': item.id, 'version': item.version, 'artifact_id': artifact.id}

    def submit_work(self, paths, handoff, submission_key, expected_version, requirements, artifact_refs=None):
        text_value(handoff, 'Handoff')
        text_value(requirements, 'Requirements and acceptance criteria')
        unique_key(submission_key)
        artifact_refs = [] if artifact_refs is None else artifact_refs
        if not isinstance(artifact_refs, list) or len(artifact_refs) > 20:
            raise OrbeHelmError('Provide at most 20 pinned artifact references')
        for reference in artifact_refs:
            if not isinstance(reference, dict) or set(reference) != {'uri', 'revision'}:
                raise OrbeHelmError('Artifact references require uri and revision')
            text_value(reference['uri'], 'Artifact URI', 2048)
            text_value(reference['revision'], 'Artifact revision', 256)
            parsed = urlsplit(reference['uri'])
            if (parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username
                    or parsed.password or parsed.query or parsed.fragment
                    or reference['revision'].strip().lower() in {'head', 'latest', 'main', 'master'}):
                raise OrbeHelmError('Use a credential-free artifact URL and a pinned revision, not a moving branch')
        if not isinstance(paths, list) or len(paths) > 100 or any(not isinstance(path, str) for path in paths) or (not paths and not artifact_refs):
            raise OrbeHelmError('Provide source paths or pinned artifact references')
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
        if paths and not files:
            raise OrbeHelmError('No candidate source files were selected')
        payload = {'handoff': handoff, 'requirements': requirements, 'submission_key': submission_key, 'source_scope': sorted(set(paths)),
                   'source_digest': digest(canonical(manifest(files)).encode()), 'owner_id': self.actor_id,
                   'configuration_id': configuration_id}
        if artifact_refs:
            payload['artifact_refs'] = artifact_refs
            payload['source_digest'] = digest(canonical({'files': manifest(files), 'artifact_refs': artifact_refs}).encode())
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
            require_submission(task.state, task.rounds, task.max_rounds, False)
            live = db.scalar(select(Delegation.id).where(Delegation.task_id == task.id,
                Delegation.status.in_(['queued', 'running', 'result_pending'])))
            require_submission(task.state, task.rounds, task.max_rounds, bool(live))
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
        with product_lock(self.store.root), self.store.write() as db:
            return self._create_delegation(db, profile, key, instructions, expected_version)

    def create_assessments(self, key, instructions, expected_version):
        raise OrbeHelmError('Parallel assessments are no longer supported; request reviewer only')

    @staticmethod
    def _operator():
        # Same boundary as operator memory maintenance, not OS-account isolation.
        if os.environ.get('ORBEHELM_ORBE_ID') or os.environ.get('ORBEHELM_MEMORY_BINDING'):
            raise OrbeHelmError('Human decisions and QA launch require an operator terminal outside an agent session')

    def _human_decision(self, db, task):
        event = db.scalars(select(TaskEvent).where(TaskEvent.task_id == task.id,
            TaskEvent.kind.in_(['human.decision', 'task.reopened']))
            .order_by(TaskEvent.sequence.desc())).first()
        if not event or event.kind != 'human.decision' or event.payload['candidate_id'] != task.candidate_id:
            return None
        artifact = db.get(TaskArtifact, event.payload['artifact_id'])
        return {'artifact_id': artifact.id, **self._read(db, task, artifact)['data']}

    def _latest_review(self, db, task):
        event = db.scalars(select(TaskEvent).where(TaskEvent.task_id == task.id,
            TaskEvent.kind == 'delegation.created').order_by(TaskEvent.sequence.desc())).all()
        for entry in event:
            item = db.get(Delegation, entry.payload['delegation_id'])
            if item.candidate_id == task.candidate_id and item.profile == 'reviewer':
                return item
        return None

    def human_decision(self, candidate_id, decision, operator, summary, key, expected_version):
        """Record an explicit local operator attestation; never exposed as MCP."""
        self._operator()
        if decision not in {'approved', 'rejected'}:
            raise OrbeHelmError('Human decision must be approved or rejected')
        unique_key(key)
        text_value(operator, 'Operator identity', 256)
        text_value(summary, 'Human review summary')
        with product_lock(self.store.root), self.store.write() as db:
            actor, task = self._scope(db)
            self._developer(actor, task)
            old = db.scalars(select(TaskArtifact).where(TaskArtifact.task_id == task.id,
                TaskArtifact.kind == 'human_decision')).all()
            for artifact in old:
                data = self._read(db, task, artifact)['data']
                if data['key'] == key:
                    if any(data[name] != value for name, value in [('candidate_id', candidate_id),
                            ('decision', decision), ('operator', operator), ('summary', summary)]):
                        raise Conflict('Human decision key already identifies different content')
                    return {'artifact_id': artifact.id, 'state': task.state, 'version': task.version}
            self._version(task, expected_version)
            if task.candidate_id != candidate_id or task.state not in {'awaiting_human_approval', 'approved_for_qa'}:
                raise Conflict('Human review requires the current reviewer-approved candidate')
            review = self._latest_review(db, task)
            if not review or review.status != 'completed' or not review.result_id:
                raise Conflict('A completed reviewer approval is required')
            result = self._read(db, task, db.get(TaskArtifact, review.result_id))['data']
            if result['status'] != 'approved':
                raise Conflict('A completed reviewer approval is required')
            candidate = self._read(db, task, db.get(TaskArtifact, candidate_id))['data']
            receipt = self._artifact(db, task, 'human_decision', {'candidate_id': candidate_id,
                'source_digest': candidate['source_digest'], 'review_result_id': review.result_id,
                'decision': decision, 'operator': operator, 'summary': summary, 'key': key, 'recorded_at': now()})
            task.state = 'approved_for_qa' if decision == 'approved' else 'developing'
            self._event(db, task, 'human.decision', {'candidate_id': candidate_id, 'artifact_id': receipt.id})
            return {'artifact_id': receipt.id, 'state': task.state, 'version': task.version}

    def request_qa(self, candidate_id, key, instructions, expected_version):
        self._operator()
        with product_lock(self.store.root), self.store.write() as db:
            return self._create_delegation(db, 'qa', key, instructions, expected_version,
                                           operator_candidate=candidate_id)

    def _create_delegation(self, db, profile, key, instructions, expected_version, operator_candidate=None):
        if profile != 'reviewer' and not (profile == 'qa' and operator_candidate is not None):
            raise OrbeHelmError('Developers may request reviewer only; QA requires the operator tasks qa command')
        unique_key(key)
        text_value(instructions, 'Delegation instructions')
        actor, task = self._scope(db)
        self._developer(actor, task)
        if operator_candidate is not None and operator_candidate != task.candidate_id:
            raise Conflict('QA must target the current human-approved candidate')
        existing = db.scalars(select(Delegation).where(Delegation.parent_id == actor.id,
            Delegation.profile == profile, Delegation.key == key,
            Delegation.candidate_id == task.candidate_id)).first()
        if existing:
            if existing.instructions != instructions:
                raise Conflict('Delegation key already has different instructions')
            if profile == 'qa' and existing.status == 'queued':
                approval = self._human_decision(db, task)
                review = self._latest_review(db, task)
                frozen = self._read(db, task, db.get(TaskArtifact, existing.context_id))['data']
                if (not approval or approval['decision'] != 'approved' or not review
                        or review.status != 'completed' or review.result_id != approval['review_result_id']
                        or frozen.get('human_approval_id') != approval['artifact_id']
                        or task.state not in {'testing', 'approved_for_qa'}):
                    raise Conflict('Queued QA has no current human approval; inspect and recover the old request')
            return self._delegation_dict(existing)
        self._version(task, expected_version)
        approval = None
        if profile == 'reviewer':
            require_delegation(profile, task.state, task.candidate_id)
        else:
            approval = self._human_decision(db, task)
            review = self._latest_review(db, task)
            if (task.state != 'approved_for_qa' or not approval or approval['decision'] != 'approved'
                    or not review or review.status != 'completed' or review.result_id != approval['review_result_id']):
                raise Conflict('QA requires explicit human approval of the current reviewed candidate')
        active = db.scalar(select(Delegation.id).where(Delegation.task_id == task.id,
            Delegation.status.in_(['queued', 'running', 'result_pending'])))
        if active:
            raise Conflict('This candidate already has an active ' + profile + ' assessment')
        candidate = db.get(TaskArtifact, task.candidate_id)
        if self._read(db, task, candidate)['data']['owner_id'] != actor.id:
            raise OrbeHelmError('Only the submitted candidate owner may delegate it')
        orbe_key = (task.unique_key[:60] or 'default') + '/child-' + stable_id(actor.id, profile, key)
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
            child_actor = db.get(LogicalOrbe, child_id)
            payload = self._read(db, task, db.get(TaskArtifact, fact.artifact_id))['data']
            if fact.status != 'superseded' and identity not in seen and self._knowledge_audience(child_actor, payload):
                facts.append({field: getattr(fact, field) for field in
                              ('id', 'key', 'scope', 'version', 'status', 'artifact_id')})
                seen.add(identity)
        frozen = self._artifact(db, task, 'context', {'candidate_id': task.candidate_id,
            'task_version': task.version, 'instructions': instructions, 'knowledge': facts,
            'human_approval_id': approval['artifact_id'] if approval else None,
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

    def _refresh_assessments(self, db, task):
        gates, pending, missing_knowledge = {}, False, False
        review = self._latest_review(db, task)
        approval = self._human_decision(db, task)
        approved = bool(approval and approval['decision'] == 'approved' and review
                        and review.status == 'completed' and review.result_id == approval['review_result_id'])
        records = db.scalars(select(Delegation).where(Delegation.task_id == task.id,
            Delegation.candidate_id == task.candidate_id).order_by(Delegation.created_at, Delegation.id)).all()
        for gate in records:
            if gate.profile == 'reviewer' and (not review or gate.id != review.id):
                continue
            if gate.profile == 'qa':
                frozen = self._read(db, task, db.get(TaskArtifact, gate.context_id))['data']
                if not approved or frozen.get('human_approval_id') != approval['artifact_id']:
                    continue
            pending |= gate.status in {'queued', 'running', 'result_pending'}
            if gate.status == 'completed' and gate.result_id:
                payload = self._read(db, task, db.get(TaskArtifact, gate.result_id))['data']
                gates[gate.profile] = payload['status']
                missing_knowledge |= db.scalar(select(MemorySource.unit_id).where(
                    MemorySource.owner_id == gate.child_id,
                    MemorySource.source_id == 'assessment:' + gate.id)) is None
            elif gate.status in {'failed', 'cancelled', 'interrupted'}:
                gates[gate.profile] = 'blocked'
        task.state = assessment_state(gates, pending, human_approved=approved)
        if pending:
            task.state = 'testing' if approved else 'reviewing'
        if missing_knowledge and not pending:
            task.state = 'persistence_pending'

    def persist_assessment(self, record):
        """The committed result artifact is the durable, idempotent outbox receipt."""
        if record['status'] != 'completed' or not record.get('result_id'):
            return record
        from ..infrastructure.memory.sqlite import SQLiteMemory
        with self.store.read() as db:
            actor, task = self._scope(db)
            item = db.get(Delegation, record['id'])
            if item.parent_id != actor.id or item.task_id != task.id:
                raise OrbeHelmError('Assessment is outside this parent orbe')
            payload = self._read(db, task, db.get(TaskArtifact, item.result_id))['data']
            frozen = self._read(db, task, db.get(TaskArtifact, item.context_id))['data']
            restricted = False
            for fact in frozen['knowledge']:
                data = self._read(db, task, db.get(TaskArtifact, fact['artifact_id']))['data']
                if '*' not in data.get('outcome', {}).get('audience', []):
                    restricted = True
            child = db.get(LogicalOrbe, item.child_id)
            selection = canonical({'profile': child.profile, 'spec': child.specialization or None,
                                   'unique_key': child.orbe_key or None})
            thread = db.scalars(select(Conversation).where(Conversation.project_id == task.project_id,
                                                           Conversation.selection == selection)).first()
            if thread:
                reads = db.execute(select(KUnitRecord.visibility, KnowledgeMetadata.audience)
                    .join(MemoryRead, MemoryRead.unit_id == KUnitRecord.id)
                    .join(MemoryBinding, MemoryBinding.id == MemoryRead.binding_id)
                    .outerjoin(KnowledgeMetadata, KnowledgeMetadata.unit_id == KUnitRecord.id)
                    .where(MemoryBinding.conversation_id == thread.id)).all()
                # Conservative across this child's context history: a report may
                # reach its parent, but private inputs must not become project memory.
                restricted |= any(scope == 'private' or not audience or '*' not in audience
                                  for scope, audience in reads)
            owner, project_id = item.child_id, task.project_id
        try:
            repo = SQLiteMemory(self.store.engine.url.database, self.store.root / 'state/memory-index.sqlite3')
            repo.ensure_owner(owner, project_id, 'private' if restricted else 'project')
            metadata = {'kind': 'review' if record['profile'] == 'reviewer' else 'test',
                        'evidence': ['artifact:' + record['result_id'], 'candidate:' + record['candidate_id']],
                        'audience': ['*'], 'evidence_state': 'implemented'}
            # Write the summary receipt last: its source ID proves that every
            # granular finding has been persisted, even after a partial retry.
            for ordinal, finding in enumerate(payload['findings']):
                repo.put(owner, finding, 'assessment:' + record['id'] + ':finding:' + str(ordinal),
                         'private' if restricted else 'project', source_kind='assessment', metadata=metadata)
            unit = repo.put(owner, payload['summary'], 'assessment:' + record['id'],
                            'private' if restricted else 'project', source_kind='assessment', metadata=metadata)
        except OrbeHelmError:
            with product_lock(self.store.root), self.store.write() as db:
                _, current = self._scope(db)
                if current.candidate_id == record['candidate_id'] and current.state != 'persistence_pending':
                    current.state = 'persistence_pending'
                    self._event(db, current, 'knowledge.persistence_pending', {'delegation_id': record['id']})
            return {**record, 'knowledge_persistence': 'pending'}
        with product_lock(self.store.root), self.store.write() as db:
            _, current = self._scope(db)
            if current.candidate_id == record['candidate_id'] and current.state == 'persistence_pending':
                self._refresh_assessments(db, current)
                self._event(db, current, 'knowledge.persisted', {'delegation_id': record['id'], 'unit_id': unit['id']})
        return {**record, 'knowledge_persistence': 'saved', 'knowledge_unit_id': unit['id']}

    def finish(self, delegation_id, successful, reason='failed'):
        result = self._finish(delegation_id, successful, reason)
        return self.persist_assessment(result)

    def _finish(self, delegation_id, successful, reason='failed'):
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
                item.status = 'completed'
            else:
                item.status = reason if reason in {'failed', 'cancelled', 'interrupted'} else 'failed'
            item.finished_at = now()
            db.flush()
            self._refresh_assessments(db, task)
            self._event(db, task, 'delegation.' + item.status, {'delegation_id': item.id, 'result_id': item.result_id})
            return self._delegation_dict(item)

    def reopen(self, expected_version, round_limit=None):
        with product_lock(self.store.root), self.store.write() as db:
            actor, task = self._scope(db)
            self._developer(actor, task)
            self._version(task, expected_version)
            require_reopen(task.state, task.rounds, None, False)
            if db.scalar(select(Delegation.id).where(Delegation.task_id == task.id,
                         Delegation.status.in_(['queued', 'running', 'result_pending']))):
                raise Conflict('A pending delegation must be resolved first')
            require_reopen(task.state, task.rounds, round_limit, False)
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

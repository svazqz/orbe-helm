"""Provider-independent memory workflows; callers supply verified owner bindings."""
from ...domain.knowledge.retrieval import content_text, visibility, outcome_metadata
from ...domain.shared.errors import OrbeHelmError


class MemoryService:
    def __init__(self, repository, owner, default_visibility='private', binding_id=None):
        self.repository = repository
        self.owner = owner
        self.default_visibility = visibility(default_visibility)
        self.binding_id = binding_id

    def put(self, content, source_id, source_ids=(), kind=None, evidence=None, audience=None, evidence_state='proposed'):
        if not isinstance(source_id, str) or not 1 <= len(source_id) <= 256:
            raise OrbeHelmError('Provide a stable memory source_id of 1–256 characters')
        if not isinstance(source_ids, (list, tuple)) or len(source_ids) > 100 or any(not isinstance(item, str) or not 1 <= len(item) <= 128 for item in source_ids):
            raise OrbeHelmError('Memory source_ids must be a bounded list of KUnit IDs')
        metadata = outcome_metadata(kind, evidence, audience, evidence_state) if kind is not None else None
        if self.binding_id and metadata is None:
            raise OrbeHelmError('Agent knowledge requires kind and artifact/revision evidence; profile rules belong in definitions')
        return self.repository.put(self.owner, content_text(content), source_id,
                                   self.default_visibility, self.binding_id, tuple(source_ids),
                                   source_kind='agent' if self.binding_id else 'explicit', metadata=metadata)

    def query(self, query, limit=10):
        if not isinstance(query, str) or len(query) > 2000 or type(limit) is not int or not 1 <= limit <= 50:
            raise OrbeHelmError('Use a query of at most 2000 characters and a limit of 1–50')
        return self.repository.search(self.owner, query, limit, self.binding_id)

    def read(self, unit_id):
        return self.repository.read_unit(self.owner, unit_id, self.binding_id)

    def history(self, unit_id):
        return self.repository.history(self.owner, unit_id)

    def revise(self, unit_id, expected, content=None, new_visibility=None, retract=False):
        if type(expected) is not int or expected < 1:
            raise OrbeHelmError('Supply the current positive --expected-version')
        if new_visibility is not None:
            visibility(new_visibility)
        if content is not None:
            content = content_text(content)
        return self.repository.revise(self.owner, unit_id, expected, content, new_visibility, retract)

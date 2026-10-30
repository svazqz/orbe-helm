"""Knowledge queries and visibility changes through verified contexts and ports."""
from ..registry import Operation
from ...domain.shared.errors import Conflict, Forbidden, OrbeHelmError
from ...domain.knowledge.policies import set_visibility, public_projection


class KnowledgeUseCases:
    def __init__(self, repository):
        self.repository = repository

    def read(self, request, context):
        item = self.repository.get_visible(request.payload['id'], context.scope, context.now)
        if item is None:
            raise Forbidden('Access denied')
        return public_projection(item)

    def query(self, request, context):
        limit = request.payload.get('limit', 50)
        if not 1 <= limit <= 200:
            raise OrbeHelmError('Knowledge limit must be between 1 and 200')
        items = self.repository.query_visible(context.scope, context.now, request.payload.get('query', ''), limit)
        return tuple(public_projection(item) for item in items)

    def visibility(self, request, context):
        item = self.repository.get_visible(request.payload['id'], context.scope, context.now)
        if item is None:
            raise Forbidden('Access denied')
        if type(request.expected_revision) is not int or request.expected_revision != item.revision:
            raise Conflict('Knowledge changed; read its current revision before publishing')
        published = set_visibility(item, context.scope, context.now, request.payload['visibility'])
        self.repository.save(published, expected_revision=item.revision)
        return public_projection(published)

    def register(self, registry):
        registry.register(Operation('knowledge.read', self.read, {'id': str}, {}))
        registry.register(Operation('knowledge.query', self.query, {}, {'query': str, 'limit': int}))
        registry.register(Operation('knowledge.visibility', self.visibility, {'id': str, 'visibility': str}, {}, 'write'))

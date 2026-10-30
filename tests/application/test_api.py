"""Transport payloads cannot establish authority or bypass domain predicates."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from orbehelm.application import Application, Request
from orbehelm.application.context import RequestContext
from orbehelm.application.registry import Registry
from orbehelm.application.use_cases.knowledge import KnowledgeUseCases
from orbehelm.application.use_cases.definitions import register
from orbehelm.domain.access.entities import AccessScope, AccessGrant
from orbehelm.domain.knowledge.entities import KUnit, KnowledgeStatus
from orbehelm.domain.knowledge.policies import can_read
from orbehelm.domain.shared.errors import Conflict, Forbidden


class MemoryKnowledge:
    def __init__(self, items):
        self.items = {item.id: item for item in items}
        self.writes = 0

    def get_visible(self, unit_id, scope, now):
        item = self.items.get(unit_id)
        return item if item and can_read(item, scope, now) else None

    def query_visible(self, scope, now, query, limit):
        return tuple(item for item in self.items.values()
                     if can_read(item, scope, now) and query in item.content)[:limit]

    def save(self, item, expected_revision):
        current = self.items.get(item.id)
        if (current.revision if current else 0) != expected_revision:
            raise Conflict('Knowledge changed')
        self.items[item.id] = item
        self.writes += 1



class Bindings:
    def __init__(self, contexts):
        self.contexts = contexts

    def verify(self, binding):
        if binding not in self.contexts:
            raise Forbidden('Access denied')
        return self.contexts[binding]


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.item = KUnit('private', 1, 'secret', 'author', 'orbe', project_id='p', orbe_id='o', status=KnowledgeStatus.ACCEPTED)
        self.repository = MemoryKnowledge([self.item])
        self.registry = Registry()
        register(self.registry)
        KnowledgeUseCases(self.repository).register(self.registry)
        self.agent = RequestContext(AccessScope('agent', 'agent', project_id='p', orbe_id='o'), 100)
        self.bindings = Bindings({'opaque': self.agent, 'foreign': replace(self.agent, scope=replace(self.agent.scope, project_id='other'))})
        self.app = Application(self.registry, self.bindings)

    def test_same_handler_works_without_persistence_or_provider_dependencies(self):
        result = self.app.handle(Request('knowledge.read', {'id': 'private'}, request_id='trace'), 'opaque')
        self.assertTrue(result.ok)
        self.assertEqual(result.value['content'], 'secret')
        self.assertEqual(result.request_id, 'trace')
        self.assertEqual(self.repository.writes, 0)

    def test_foreign_absent_and_unknown_binding_have_identical_denial(self):
        denied = [self.app.handle(Request('knowledge.read', {'id': key}), binding)
                  for key, binding in [('private', 'foreign'), ('missing', 'foreign'), ('private', 'invalid')]]
        self.assertEqual({(r.code, r.message) for r in denied}, {('forbidden', 'Access denied')})
        self.assertTrue(all(not r.ok and r.value is None for r in denied))

    def test_identity_payloads_and_wrong_types_fail_before_effects(self):
        for payload in [{'id': 'private', 'principal': 'operator'}, {'id': 'private', 'project_id': 'p'},
                        {'id': 'private', 'operator': True}, {'id': 1}, {}]:
            result = self.app.handle(Request('knowledge.read', payload), 'opaque')
            self.assertFalse(result.ok)
        result = self.app.handle(Request('knowledge.query', {'limit': True}), 'opaque')
        self.assertFalse(result.ok)
        self.assertEqual(self.repository.writes, 0)

    def test_filtering_precedes_search_paging_and_no_private_count_is_exposed(self):
        result = self.app.handle(Request('knowledge.query', {'query': 'secret', 'limit': 1}), 'foreign')
        self.assertTrue(result.ok)
        self.assertEqual(result.value, ())

    def test_publication_requires_verified_operator_grant_and_revision(self):
        request = Request('knowledge.visibility', {'id': 'private', 'visibility': 'global'}, expected_revision=1)
        self.assertEqual(self.app.handle(request, 'opaque').code, 'forbidden')
        grant = AccessGrant('grant', 'operator', 'knowledge.visibility', 'private', 100, 200)
        self.bindings.contexts['approved'] = RequestContext(AccessScope('operator', 'operator', project_id='p', orbe_id='o', grants=(grant,)), 100)
        self.assertEqual(self.app.handle(replace(request, expected_revision=0), 'approved').code, 'conflict')
        result = self.app.handle(request, 'approved')
        self.assertTrue(result.ok)
        self.assertEqual(result.value['visibility'], 'global')
        self.assertEqual(self.repository.items['private'].id, self.item.id)
        self.assertEqual(self.repository.items['private'].orbe_id, self.item.orbe_id)
        self.assertEqual(self.app.handle(request, 'approved').code, 'conflict')

    def test_version_and_unknown_operations_are_stable_errors(self):
        for request in [Request('missing'), Request('knowledge.query', api_version=True), Request('knowledge.query', api_version=2)]:
            self.assertEqual(self.app.handle(request, 'opaque').code, 'invalid_request')
        self.assertFalse(self.app.handle(Request('definitions.compose', {'instructions': [{'content': 'missing path'}]}), 'opaque').ok)
        def broken_repository(*args):
            raise RuntimeError('private database details')
        self.repository.get_visible = broken_repository
        result = self.app.handle(Request('knowledge.read', {'id': 'private'}), 'opaque')
        self.assertEqual(result.code, 'internal_error')
        self.assertNotIn('private database details', result.message)

    def test_source_revision_change_during_publication_cannot_release_stale_content(self):
        grant = AccessGrant('grant', 'operator', 'knowledge.visibility', 'private', 100, 200)
        self.bindings.contexts['approved'] = RequestContext(AccessScope('operator', 'operator', project_id='p', orbe_id='o', grants=(grant,)), 100)
        original = self.repository.save
        def concurrent_change(updated, expected_revision):
            self.repository.items[updated.id] = replace(self.item, revision=2, content='changed after review')
            original(updated, expected_revision)
        self.repository.save = concurrent_change
        result = self.app.handle(Request('knowledge.visibility', {'id': 'private', 'visibility': 'global'}, expected_revision=1), 'approved')
        self.assertEqual(result.code, 'conflict')
        self.assertNotIn('public', self.repository.items)
        self.assertEqual(self.repository.writes, 0)

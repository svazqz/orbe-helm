"""Real SQLite/FTS/vector tests with deterministic injected embedding models."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import itertools
import json
import sqlite3
import sys
import tempfile
import subprocess
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from orbehelm.product.database import Store, migrate
from orbehelm.product.models import Project, Conversation
from orbehelm.infrastructure.memory.sqlite import SQLiteMemory
from orbehelm.application.use_cases.memory import MemoryService
from orbehelm.domain.shared.errors import Conflict, Forbidden, OrbeHelmError
from orbehelm.domain.knowledge.retrieval import segments, reciprocal_rank_fusion, may_read
from orbehelm.memory import bind, binding_file, bound_service
from orbehelm.memory_bridge import MemoryBridge

ROOT = Path(__file__).resolve().parents[2]


class OutcomeService(MemoryService):
    """Existing engine scenarios exercise explicitly classified fixture outcomes."""
    def put(self, content, source_id, source_ids=(), **kwargs):
        return super().put(content, source_id, source_ids, kind='decision',
                           evidence=['fixture:revision-1'], **kwargs)


class FixtureEmbeddings:
    """Different wording shares vectors; this is a fixture, not a semantic model."""
    model_id = 'fixture-v1'
    calls = 0

    def documents(self, texts):
        self.calls += len(texts)
        return [self.query(text) for text in texts]

    def query(self, text):
        text = text.lower()
        return [1., 0.] if any(term in text for term in ['canine', 'dog', 'perro']) else [0., 1.]


class MemoryFixture(unittest.TestCase):
    def setUp(self):
        verification = ROOT / 'state/verification/knowledge-memory/tests'
        verification.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=verification)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        migrate(self.root)
        self.store = Store(self.root)
        self.addCleanup(self.store.close)
        with self.store.write() as db:
            db.add_all([Project(id='p', path=str(self.root / 'p'), name='p'),
                        Project(id='other-project', path=str(self.root / 'other'), name='other')])
            db.flush()
            db.add_all([Conversation(id='thread-a', project_id='p', selection='a'),
                        Conversation(id='thread-b', project_id='p', selection='b')])
        ids = itertools.count(1)
        self.repo = SQLiteMemory(self.root / 'state/orbehelm.sqlite3', self.root / 'state/memory-index.sqlite3',
                                 ids=lambda: format(next(ids), '032x'), clock=lambda: 1000)
        self.repo.ensure_owner('a', 'p')
        self.repo.ensure_owner('b', 'p')
        self.repo.ensure_owner('c', 'other-project')
        self.a, self.b = OutcomeService(self.repo, 'a'), OutcomeService(self.repo, 'b')


class EngineTests(MemoryFixture):
    def test_owner_visibility_not_project_membership_controls_reads(self):
        unit = self.a.put('private deployment decision', 'source-1')
        self.assertEqual(self.a.read(unit['id'])['content'], unit['content'])
        for actor in ['b', 'c']:
            with self.assertRaises(Forbidden):
                self.repo.read_unit(actor, unit['id'])
            self.assertEqual(self.repo.search(actor, 'deployment')['units'], [])

    def test_global_unit_preserves_owner_and_identity_across_visibility_changes(self):
        unit = self.a.put('deployment policy', 'source-1')
        public = self.a.revise(unit['id'], 1, new_visibility='global')
        self.assertEqual((public['id'], public['owner_id']), (unit['id'], 'a'))
        self.assertEqual(self.b.read(unit['id'])['revision'], 2)
        self.assertEqual(self.repo.read_unit('c', unit['id'])['revision'], 2)
        with self.assertRaises(Forbidden):
            self.b.revise(unit['id'], 2, new_visibility='private')
        self.a.revise(unit['id'], 2, new_visibility='private')
        with self.assertRaises(Forbidden):
            self.b.read(unit['id'])
        self.assertEqual(self.b.query('deployment')['units'], [])
        with self.assertRaises(Conflict):
            self.a.revise(unit['id'], 2, new_visibility='global')

    def test_historical_private_revisions_are_not_exposed_by_global_publication(self):
        unit = self.a.put('secret old content', 's')
        self.a.revise(unit['id'], 1, content='public release', new_visibility='global')
        self.assertEqual(self.b.read(unit['id'])['content'], 'public release')
        with self.assertRaises(Forbidden):
            self.b.history(unit['id'])
        self.assertEqual(self.a.history(unit['id'])[0]['content'], 'secret old content')

    def test_idempotent_source_and_compare_and_swap_conflicts(self):
        first = self.a.put('one fact', 'same')
        self.assertEqual(self.a.put('one fact', 'same'), first)
        with self.assertRaises(Conflict):
            self.a.put('different fact', 'same')
        self.assertNotEqual(self.b.put('one fact', 'same')['id'], first['id'])
        self.a.revise(first['id'], 1, content='corrected fact')
        with self.assertRaises(Conflict):
            self.a.revise(first['id'], 1, content='stale correction')

    def test_query_filters_before_limit_and_handles_fts_metacharacters(self):
        for i in range(20):
            self.a.put('private canine dog fact ' + str(i), 'private-' + str(i))
        visible = self.b.put('canine dog visible fact', 'visible')
        self.assertEqual([row['id'] for row in self.b.query('dog', 1)['units']], [visible['id']])
        for query in ['" OR *', 'dog:cat', '"unterminated', "x' OR 1=1 --"]:
            self.assertEqual(self.b.query(query)['mode'], 'keyword-only')

    def test_context_match_comes_from_relevant_chunk_instead_of_document_prefix(self):
        content = ('Unrelated introduction. ' * 150) + '\n\nThe exact deployment error is TARGET_FAILURE_CODE.'
        self.a.put(content, 'large-unit')
        result = self.a.query('TARGET_FAILURE_CODE')['units'][0]
        self.assertIn('TARGET_FAILURE_CODE', result['match'])
        self.assertNotIn('TARGET_FAILURE_CODE', result['content'][:1800])

    def test_hybrid_search_finds_semantic_match_without_keyword_overlap(self):
        self.repo.embedder = FixtureEmbeddings()
        self.a.put('A canine helps the team', 'dog')
        self.a.put('A database indexes values', 'db')
        result = self.a.query('perro')
        self.assertEqual(result['mode'], 'hybrid')
        self.assertEqual(result['units'][0]['content'], 'A canine helps the team')
        self.assertEqual(result['pending_embeddings'], 0)

    def test_visibility_updates_do_not_reembed_unrelated_units(self):
        embeddings = FixtureEmbeddings()
        self.repo.embedder = embeddings
        unit = self.a.put('canine fact', 'dog')
        self.b.put('database fact', 'db')
        self.repo.sync_index()
        before = embeddings.calls
        self.a.revise(unit['id'], 1, new_visibility='global')
        self.repo.sync_index()
        self.assertEqual(embeddings.calls - before, 0)

    def test_global_defaults_cannot_release_private_inputs(self):
        source = self.a.put('private source', 'private')
        credentials = self.repo.issue_binding('a', 'global')
        bound = OutcomeService(self.repo, 'a', 'global', credentials['binding'])
        bound.read(source['id'])
        derived = bound.put('summary of private source', 'derived')
        self.assertEqual(derived['visibility'], 'private')
        with self.assertRaises(Forbidden):
            self.a.revise(derived['id'], 1, new_visibility='global')

    def test_revocation_invalidates_transitive_cross_owner_summaries(self):
        source = OutcomeService(self.repo, 'a', 'global').put('global source', 'source')
        b_binding = self.repo.issue_binding('b', 'global')['binding']
        b = OutcomeService(self.repo, 'b', 'global', b_binding)
        b.read(source['id'])
        derived = b.put('derived global summary', 'derived')
        c_binding = self.repo.issue_binding('c', 'global')['binding']
        c = OutcomeService(self.repo, 'c', 'global', c_binding)
        c.read(derived['id'])
        descendant = c.put('second level summary', 'descendant')
        self.a.revise(source['id'], 1, new_visibility='private')
        for owner, unit in [('b', derived), ('c', descendant)]:
            with self.assertRaises(Forbidden):
                self.repo.read_unit(owner, unit['id'])
        self.assertEqual(self.b.query('summary')['units'], [])

    def test_content_change_invalidates_derived_units_and_stale_reads(self):
        source = OutcomeService(self.repo, 'a', 'global').put('source fact', 's')
        token = self.repo.issue_binding('b', 'global')['binding']
        b = OutcomeService(self.repo, 'b', 'global', token)
        b.read(source['id'])
        derived = b.put('derived fact', 'd')
        self.a.revise(source['id'], 1, content='corrected source')
        with self.assertRaises(Conflict):
            b.put('new answer from stale context', 'stale')
        with self.assertRaises(Forbidden):
            b.read(derived['id'])

    def test_outdated_projection_cannot_restore_private_or_old_content(self):
        unit = OutcomeService(self.repo, 'a', 'global').put('public original', 's')
        self.repo.sync_index()
        self.a.revise(unit['id'], 1, content='private revised', new_visibility='private')
        with patch.object(self.repo, 'sync_index', return_value={}):
            self.assertEqual(self.b.query('public original')['units'], [])
            self.assertEqual(self.a.query('public original')['units'], [])

    def test_rebuild_recovers_corruption_without_losing_canonical_units(self):
        unit = self.a.put('durable fact', 's')
        self.repo.sync_index()
        self.repo.index.write_bytes(b'not sqlite')
        with self.assertRaises(OrbeHelmError):
            self.a.query('durable')
        self.repo.rebuild()
        self.assertEqual(self.a.query('durable')['units'][0]['id'], unit['id'])

    def test_index_failure_preserves_pending_job_and_canonical_content(self):
        unit = self.a.put('durable fact', 's')
        with patch.object(self.repo, 'search_index', side_effect=sqlite3.DatabaseError('fixture failure')):
            with self.assertRaises(OrbeHelmError):
                self.repo.sync_index()
        self.assertEqual(self.a.read(unit['id'])['content'], 'durable fact')
        self.assertEqual(self.repo.status()['index_jobs'], {'pending': 1})
        self.assertEqual(self.a.query('durable')['units'][0]['id'], unit['id'])

    def test_failed_embeddings_leave_explicit_recoverable_status(self):
        class Broken(FixtureEmbeddings):
            def documents(self, texts):
                raise RuntimeError('private provider internals')
        self.repo.embedder = Broken()
        self.a.put('durable fact', 's')
        result = self.a.query('durable')
        self.assertEqual(result['units'][0]['content'], 'durable fact')
        self.assertEqual(result['pending_embeddings'], 1)
        self.assertNotIn('private provider internals', json.dumps(self.repo.status()))
        self.repo.embedder = FixtureEmbeddings()
        self.repo.sync_index()
        self.assertEqual(self.a.query('durable')['pending_embeddings'], 0)

    def test_capture_is_durable_only_completed_turns_are_materialized(self):
        binding = self.repo.issue_binding('a', 'private')['binding']
        self.repo.enqueue_capture('a', binding + ':1', 'an observed result', 'private', binding)
        self.repo.drain_captures('a')
        self.assertEqual(self.a.query('observed')['units'], [])
        self.repo.complete_captures('a', binding)
        self.repo.revoke_binding(binding)
        self.repo.drain_captures('a')
        result = self.a.query('observed')['units'][0]
        self.assertEqual(result['status'], 'reported')
        self.repo.drain_captures('a')
        self.assertEqual(len(self.a.query('observed')['units']), 1)

    def test_capture_retry_preserves_private_provenance_after_restart(self):
        source = self.a.put('private source', 's')
        binding = self.repo.issue_binding('a', 'global')['binding']
        self.repo.read_unit('a', source['id'], binding)
        self.repo.enqueue_capture('a', binding + ':1', 'derived observation', 'global', binding)
        self.repo.complete_captures('a', binding)
        self.repo.revoke_binding(binding)
        self.repo.drain_captures('a')
        self.assertEqual(self.a.query('derived')['units'][0]['visibility'], 'private')

    def test_two_concurrent_writers_do_not_duplicate_same_source(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.a.put('same fact', 'same-source'), range(2)))
        self.assertEqual(results[0]['id'], results[1]['id'])

    def test_exact_duplicate_units_keep_multiple_sources_without_cross_owner_merge(self):
        first = self.a.put('one durable fact', 'source-1')
        second = self.a.put('one durable fact', 'source-2')
        self.assertEqual(first['id'], second['id'])
        self.assertNotEqual(self.b.put('one durable fact', 'source-1')['id'], first['id'])
        with self.repo.transaction() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM memory_sources WHERE owner_id=?', ('a',)).fetchone()[0], 2)

    def test_stale_index_worker_cannot_overwrite_newer_revision(self):
        unit = self.a.put('old canine fact', 'source')
        outer = self
        class Racing(FixtureEmbeddings):
            fired = False
            def documents(self, texts):
                if not self.fired:
                    self.fired = True
                    outer.a.revise(unit['id'], 1, content='corrected database fact')
                return super().documents(texts)
        self.repo.embedder = Racing()
        self.repo.sync_index()
        self.assertEqual(self.repo.status()['index_jobs'], {'pending': 1})
        result = self.a.query('database')['units'][0]
        self.assertEqual((result['revision'], result['content']), (2, 'corrected database fact'))

    def test_embedding_configuration_change_rejects_stale_client(self):
        stale = SQLiteMemory(self.repo.database, self.repo.index)
        self.repo.configure({'fixture': 'new embedding generation'})
        with self.assertRaisesRegex(OrbeHelmError, 'configuration changed'):
            stale.search('a', 'query')

    def test_capture_retry_after_revocation_stays_pending_without_blocking_future_turns(self):
        source = OutcomeService(self.repo, 'a', 'global').put('shared source', 's')
        binding = self.repo.issue_binding('b', 'global')['binding']
        self.repo.read_unit('b', source['id'], binding)
        self.repo.enqueue_capture('b', binding + ':1', 'old derived reply', 'global', binding)
        self.repo.complete_captures('b', binding)
        self.a.revise(source['id'], 1, new_visibility='private')
        self.assertEqual(self.repo.drain_captures('b')['errors'], 1)
        self.assertEqual(self.b.query('derived')['units'], [])

    def test_binding_expiry_revocation_and_scope_injection(self):
        service, credentials = bind(self.repo, 'a', 'p', 'private', 'thread-a')
        path = binding_file(self.root, credentials)
        with patch('orbehelm.memory.repository', return_value=self.repo):
            bridge = MemoryBridge(self.store, path)
        with self.assertRaises(OrbeHelmError):
            bridge.call('save_memory', {'content': 'fact', 'source_id': 's', 'owner': 'b'})
        self.assertEqual(bridge.call('save_memory', {'content': 'fact', 'source_id': 's', 'kind': 'decision', 'evidence': ['fixture:revision-1']})['owner_id'], 'a')
        self.repo.revoke_binding(credentials['binding'])
        with self.assertRaises(Forbidden):
            bound_service(self.store, path, self.repo)
        with self.assertRaises(Forbidden):
            bridge.call('search_memory', {'query': 'fact'})
        service, credentials = bind(self.repo, 'a', 'p')
        self.repo.clock = lambda: 1000 + 43200
        with self.assertRaises(Forbidden):
            self.repo.verify_binding(**credentials)

    def test_global_history_and_search_never_expose_source_paths(self):
        unit = OutcomeService(self.repo, 'a', 'global').put('shared fact', 'secret-source-path')
        result = self.b.query('shared')
        self.assertNotIn('secret-source-path', json.dumps(result))
        self.assertEqual(result['units'][0]['owner_id'], 'a')

    def test_real_stdio_entry_initializes_without_model_or_http_listener(self):
        real = SQLiteMemory(self.repo.database, self.repo.index)
        service, credentials = bind(real, 'a', 'p', 'private', 'thread-a')
        path = binding_file(self.root, credentials)
        config = self.root / 'empty.ini'
        config.write_text('[ORBEHELM]\n')
        messages = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
        ]
        result = subprocess.run([sys.executable, str(ROOT / 'src/orbehelm/_entry.py'), 'memory-serve',
            '--root', str(self.root), '--config', str(config), '--binding-file', str(path)],
            input=''.join(json.dumps(message) + '\n' for message in messages),
            capture_output=True, text=True, check=True, timeout=15, env={**os.environ, 'HOME': str(self.root)})
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(responses[0]['id'], 1)
        self.assertEqual({item['name'] for item in responses[1]['result']['tools']},
                         {'search_memory', 'read_memory', 'save_memory'})
        real.revoke_binding(credentials['binding'])

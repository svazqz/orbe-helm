"""Managed chat, CLI, and MCP use the same owned knowledge store."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_cli_memory as fixtures
from orbehelm.cli import main
from orbehelm.conversations import conversation, events, append, bootstrap, set_checkpoint
from orbehelm.memory import repository
from orbehelm.application.use_cases.memory import MemoryService
from orbehelm.memory_bridge import MemoryBridge
from orbehelm.domain.shared.errors import Forbidden


def outcome(content, source_id):
    return {'content': content, 'source_id': source_id, 'kind': 'decision', 'evidence': ['fixture:revision-1']}


class ChatKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LocalMemoryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture
        self.thread = conversation(self.f.store, self.f.project.id, 'developer')
        self.repo = repository(self.f.store)
        self.repo.ensure_owner(self.thread, self.f.project.id)

    def test_completed_chat_creates_reported_units_and_switch_retains_owner(self):
        first, _, _ = self.f.turn(self.thread, 'claude', 'Record a decision', outcome=outcome('Recorded answer', 'decision-1'))
        units = MemoryService(self.repo, self.thread).query('Recorded answer')['units']
        self.assertEqual(len(units), 1)
        self.assertEqual((units[0]['owner_id'], units[0]['status'], units[0]['visibility']),
                         (self.thread, 'reported', 'private'))
        self.f.turn(self.thread, 'codex', 'Use recorded knowledge', first)
        self.assertEqual(len(MemoryService(self.repo, self.thread).query('Recorded answer')['units']), 1)
        with self.repo.transaction() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM memory_owners').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM memory_bindings WHERE active=1').fetchone()[0], 0)
        self.assertFalse(list((self.f.root / 'state/memory-bindings').glob('*.json')))

    def test_global_launch_flag_controls_new_units_and_dry_run_is_write_free(self):
        process = self.f.fake_process('claude', reply='Global API decision')
        with patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                patch('orbehelm.managed.subprocess.Popen', side_effect=lambda *a, **kw: (
                    MemoryBridge(self.f.store, kw['env']['ORBEHELM_MEMORY_BINDING']).call('save_memory', outcome('Global API decision', 'global-1')),
                    process)[1]), \
                contextlib.redirect_stdout(io.StringIO()):
            code = main(['chat', '--root', str(self.f.root), '--project', str(self.f.project_path),
                         '--agent=claude', '--memory-visibility=global', '--prompt=Record a decision'])
        self.assertEqual(code, 0)
        result = MemoryService(self.repo, self.thread).query('Global API')['units']
        self.assertEqual(result[0]['visibility'], 'global')
        before = {str(p): p.read_bytes() for p in self.f.root.rglob('*') if p.is_file()}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['chat', '--root', str(self.f.root), '--project', str(self.f.project_path),
                                   '--memory-visibility=private', '--dry-run']), 0)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.f.root.rglob('*') if p.is_file()})

    def test_private_launch_does_not_change_old_global_units(self):
        self.repo.ensure_owner(self.thread, self.f.project.id, 'global')
        unit = MemoryService(self.repo, self.thread, 'global').put('Published fact', 's')
        process = self.f.fake_process('claude')
        with patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                patch('orbehelm.managed.subprocess.Popen', return_value=process), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['chat', '--root', str(self.f.root), '--project', str(self.f.project_path),
                                   '--agent=claude', '--memory-visibility=private', '--prompt=New observation']), 0)
        self.assertEqual(MemoryService(self.repo, self.thread).read(unit['id'])['visibility'], 'global')

    def test_visibility_revocation_refreshes_context_and_hides_old_handoff(self):
        other = 'other-owner'
        self.repo.ensure_owner(other, self.f.project.id)
        source = MemoryService(self.repo, other, 'global').put('Previous shared secret detail', 's', kind='decision', evidence=['fixture:revision-1'])
        first, process, _ = self.f.turn(self.thread, 'claude', 'shared secret detail')
        self.assertIn('Previous shared secret detail', process.stdin.getvalue())
        set_checkpoint(self.f.store, self.thread, 'Previous shared secret detail in old checkpoint')
        MemoryService(self.repo, other).revise(source['id'], 1, new_visibility='private')
        second, process, args = self.f.turn(self.thread, 'claude', 'Continue safely', first)
        self.assertNotIn('--resume', args)
        self.assertNotIn('Previous shared secret detail', process.stdin.getvalue())
        self.assertNotIn('Record', process.stdin.getvalue().split('Recent messages:')[-1].split('Current user request:')[0])
        self.assertNotEqual(first['policy_digest'], second['policy_digest'])
        # The complete operator audit remains durable, but automatic handoff is filtered.
        self.assertTrue(events(self.f.store, self.thread))
        self.assertNotIn('old checkpoint', bootstrap(self.f.store, self.thread, memory_epoch=self.repo.policy_epoch()))

    def test_failed_turn_does_not_materialize_assistant_observations(self):
        process = self.f.fake_process('claude')
        process.wait.return_value = 1
        result, _, _ = self.f.turn(self.thread, 'claude', 'A failing operation', process=process)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(MemoryService(self.repo, self.thread).query('Recorded answer')['units'], [])
        self.assertEqual(self.repo.status()['capture_jobs'], {})

    def test_global_handoff_omits_private_history_when_launch_mode_changes(self):
        first, _, _ = self.f.turn(self.thread, 'claude', 'Private topic',
                                 process=self.f.fake_process('claude', reply='Top secret private detail'))
        self.repo.ensure_owner(self.thread, self.f.project.id, 'global')
        second, process, args = self.f.turn(self.thread, 'claude', 'Unrelated public topic', first,
                                           process=self.f.fake_process('claude', reply='Public useful result'), outcome=outcome('Public useful result', 'public-1'))
        self.assertNotIn('--resume', args)
        self.assertNotIn('Top secret private detail', process.stdin.getvalue())
        self.assertEqual(MemoryService(self.repo, self.thread).query('Public useful')['units'][0]['visibility'], 'global')

    def test_resumed_global_session_inherits_private_context_provenance(self):
        MemoryService(self.repo, self.thread).put('private alpha source', 'private-source', kind='decision', evidence=['fixture:revision-1'])
        self.repo.ensure_owner(self.thread, self.f.project.id, 'global')
        first, _, _ = self.f.turn(self.thread, 'claude', 'private alpha source',
                                 process=self.f.fake_process('claude', reply='Derived private finding'), outcome=outcome('Derived private finding', 'private-1'))
        second, _, args = self.f.turn(self.thread, 'claude', 'Unrelated next topic', first,
                                      process=self.f.fake_process('claude', reply='Another private finding'), outcome=outcome('Another private finding', 'private-2'))
        self.assertIn(first['native_id'], args)
        units = MemoryService(self.repo, self.thread).query('Another private')['units']
        self.assertEqual(units[0]['visibility'], 'private')

    def test_memory_mcp_overlay_preserves_generated_artifacts_and_uses_revoked_binding(self):
        from orbehelm.product.projects import resolve_project, build_project
        result = resolve_project(self.f.store, self.f.project, persist=True)
        output, _ = build_project(self.f.store, result, 'claude')
        before = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
        seen = {}
        process = self.f.fake_process('claude')
        def launch(*args, **kwargs):
            path = kwargs['env']['ORBEHELM_MEMORY_BINDING']
            seen['path'] = path
            bridge = MemoryBridge(self.f.store, path)
            seen['saved'] = bridge.call('save_memory', outcome('Explicit saved decision', 'decision-1'))
            self.assertEqual(bridge.call('search_memory', {'query': 'Explicit saved'})['units'][0]['id'], seen['saved']['id'])
            with self.assertRaises(Exception):
                bridge.call('save_memory', {'content': 'Escalate', 'source_id': 'x', 'visibility': 'global'})
            return process
        runtime = self.f.root / 'state/conversations' / self.thread
        runtime.mkdir(parents=True, exist_ok=True)
        from orbehelm.managed import run_turn
        with patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                patch('orbehelm.managed.subprocess.Popen', side_effect=launch), \
                contextlib.redirect_stdout(io.StringIO()):
            run_turn(self.f.store, self.thread, 'claude', output, result, runtime, 'Store a decision')
        self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()})
        self.assertFalse(Path(seen['path']).exists())
        self.assertEqual(seen['saved']['owner_id'], self.thread)

    def test_operator_cli_put_query_visibility_and_history(self):
        file = self.f.root / 'fact.txt'
        file.write_text('Use immutable candidate evidence.')
        base = ['--root', str(self.f.root), '--project', str(self.f.project_path), '--thread', self.thread]
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['memory', 'put', *base, '--from-file', str(file), '--source-id=cli-decision']), 0)
        unit = json.loads(output.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['memory', 'query', *base, '--query=immutable']), 0)
        self.assertEqual(json.loads(output.getvalue())['units'][0]['id'], unit['id'])
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['memory', 'visibility', unit['id'], *base, '--visibility=global', '--expected-version=1']), 0)
        self.assertEqual(json.loads(output.getvalue())['visibility'], 'global')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['memory', 'history', unit['id'], *base]), 0)
        self.assertEqual(len(json.loads(output.getvalue())), 2)

    def test_legacy_import_is_explicit_private_and_preserves_original_records(self):
        from orbehelm.product.coordination import ensure_orbe, Coordinator
        from orbehelm.product.models import Knowledge
        from sqlalchemy import select
        actor = ensure_orbe(self.f.store, self.f.project, 'LEGACY-1', 'developer')
        old = Coordinator(self.f.store, actor).save_knowledge('fact', 'Legacy project observation', 'project', 0)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['memory', 'import-legacy', '--root', str(self.f.root),
                '--project', str(self.f.project_path), '--actor', actor]), 0)
        imported = json.loads(output.getvalue())['units'][0]
        self.assertEqual((imported['owner_id'], imported['visibility'], imported['status']), (actor, 'private', 'reported'))
        with self.f.store.read() as db:
            self.assertIsNotNone(db.get(Knowledge, old['id']))
            self.assertEqual(len(db.scalars(select(Knowledge)).all()), 1)

    def test_visibility_and_audit_remain_available_when_embedding_runtime_is_broken(self):
        unit = MemoryService(self.repo, self.thread).put('A fact requiring revocation control', 's')
        self.repo.configure({'provider': 'fastembed', 'name': 'missing-model'})
        base = ['--root', str(self.f.root), '--project', str(self.f.project_path), '--thread', self.thread]
        with patch('orbehelm.memory.FastEmbed', side_effect=AssertionError('Canonical operations must not load a model')), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['memory', 'visibility', unit['id'], *base, '--visibility=global', '--expected-version=1']), 0)
        self.assertEqual(json.loads(output.getvalue())['visibility'], 'global')
        with patch('orbehelm.memory.FastEmbed', side_effect=AssertionError('Audit must not load a model')), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['memory', 'history', unit['id'], *base]), 0)
        self.assertEqual(len(json.loads(output.getvalue())), 2)

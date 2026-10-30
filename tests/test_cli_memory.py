"""Local service, live definitions, and conversation handoffs with fake agents only."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from orbehelm.application import execute
from orbehelm.cli import main
from orbehelm.conversations import append, conversation, events, bootstrap, set_checkpoint
from orbehelm.core import OrbeHelmError
from orbehelm.managed import run_turn, stream_command
from orbehelm.product.commands import initialize
from orbehelm.product.database import Store
from orbehelm.product.projects import register_project, resolve_project, build_project, configuration_for
from orbehelm.product.catalog import Conflict
from orbehelm.sessions import policy_digest

REPO = Path(__file__).resolve().parents[1]


class Buffer(io.StringIO):
    def close(self):
        pass


class LocalMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=REPO / 'tests')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ('definitions', 'registry', 'examples'):
            shutil.copytree(REPO / name, self.root / name)
        self.project_path = self.root / 'work'
        self.project_path.mkdir()
        env = patch.dict(os.environ, {'HOME': str(self.root), 'ORBEHELM_CONFIG': '', 'AGENTIC_CONFIG': '', 'HERDR_ENV': ''})
        env.start()
        self.addCleanup(env.stop)
        initialize(self.root)
        self.store = Store(self.root)
        self.addCleanup(self.store.close)
        self.project = register_project(self.store, self.project_path)
        self.target = 'definition.profile.developer'

    def op(self, action, target=None, **kwargs):
        return execute('definition', self.root, action=action, target=target or self.target,
                       project_path=self.project_path, **kwargs)

    def test_shared_changes_reach_projects_and_local_reset_inherits_latest(self):
        other_path = self.root / 'other'
        other_path.mkdir()
        other = register_project(self.store, other_path)
        original = self.op('get')['content']
        self.op('override', content=original + '\nLocal instruction.\n')
        changed = original + '\nNew shared instruction.\n'
        self.op('set', global_scope=True, content=changed)
        self.assertIn('Local instruction.', resolve_project(self.store, self.project)['composed_instructions'])
        self.assertNotIn('New shared instruction.', resolve_project(self.store, self.project)['composed_instructions'])
        self.assertIn('New shared instruction.', resolve_project(self.store, other)['composed_instructions'])
        self.op('reset')
        self.assertEqual(self.op('get')['content'], changed)
        self.assertFalse(self.op('get')['overridden'])
        self.assertGreater(len(self.op('history')), 2)

    def test_shared_rollback_is_new_history_and_updates_existing_projects(self):
        old = self.op('get', global_scope=True)
        new = self.op('set', global_scope=True, content=old['content'] + '\nChanged.\n')
        restored = self.op('rollback', global_scope=True, revision=old['revision'])
        self.assertNotEqual(new['revision'], restored['revision'])
        self.assertEqual(self.op('get')['content'], old['content'])

    def test_invalid_stale_and_unowned_changes_leave_revision_unchanged(self):
        before = configuration_for(self.store, self.project).id
        for kwargs in ({'content': 'invalid section document'}, {'content': 'x', 'file': '../outside'},
                       {'content': self.op('get')['content'], 'expected': 'stale'}):
            with self.assertRaises(OrbeHelmError):
                self.op('override', **kwargs)
        self.assertEqual(configuration_for(self.store, self.project).id, before)

    def test_add_remove_and_reset_project_definition(self):
        target = 'definition.skillset.personal'
        self.op('add', target, content=json.dumps({'schema_version': 1, 'skills': ['testing']}))
        self.assertIn('testing', self.op('get', target)['content'])
        self.op('remove', target)
        with self.assertRaises(OrbeHelmError):
            self.op('get', target)
        self.op('reset', target)

    def test_package_add_validates_complete_profile_and_owned_file(self):
        package = self.root / 'package'
        package.mkdir()
        (package / 'definition.json').write_text(json.dumps({'schema_version': 1, 'instructions': ['instructions.md']}))
        (package / 'instructions.md').write_text((REPO / 'definitions/TEMPLATE.md').read_text())
        self.op('add', 'definition.profile.architect', package=package, global_scope=True)
        self.assertIn('Instruction Definition', self.op('get', 'definition.profile.architect')['content'])

    def test_get_and_managed_dry_run_are_write_free_without_network(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('orbehelm.service.build_opener', side_effect=AssertionError('Unexpected HTTP')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['get', self.target, '--root', str(self.root), '--project', str(self.project_path)]), 0)
            self.assertEqual(main(['chat', '--agent=claude', '--root', str(self.root), '--project', str(self.project_path), '--dry-run']), 0)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def fake_process(self, agent, reply='Recorded answer'):
        session = str(uuid.uuid4())
        if agent == 'claude':
            records = [{'type': 'system', 'session_id': session},
                       {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': reply}]}},
                       {'type': 'result', 'is_error': False}]
        else:
            records = [{'type': 'thread.started', 'thread_id': session},
                       {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': reply}},
                       {'type': 'turn.completed'}]
        process = Mock()
        process.stdin = Buffer()
        process.stdout = io.StringIO(''.join(json.dumps(record) + '\n' for record in records))
        process.wait.return_value = 0
        process.poll.return_value = 0
        return process

    def turn(self, thread, agent, prompt, previous=None, process=None, allowed_tools=(), outcome=None):
        result = resolve_project(self.store, self.project, persist=True)
        output, _ = build_project(self.store, result, agent)
        runtime = self.root / 'state/conversations' / thread
        runtime.mkdir(parents=True, exist_ok=True)
        process = process or self.fake_process(agent)
        def spawn(*args, **kwargs):
            if outcome:
                from orbehelm.memory_bridge import MemoryBridge
                MemoryBridge(self.store, kwargs['env']['ORBEHELM_MEMORY_BINDING']).call('save_memory', outcome)
            return process
        with patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                patch('orbehelm.managed.subprocess.Popen', side_effect=spawn) as child, \
                contextlib.redirect_stdout(io.StringIO()):
            answer = run_turn(self.store, thread, agent, output, result, runtime, prompt, previous, allowed_tools=allowed_tools)
        return answer, process, child.call_args.args[0]

    def test_agent_switch_preserves_history_without_replaying_tools(self):
        thread = conversation(self.store, self.project.id, 'developer', unique_key='APP-1')
        first, _, _ = self.turn(thread, 'codex', 'Implement the agreed feature')
        append(self.store, thread, 'agent_event', 'codex', {'type': 'tool_result', 'output': 'test evidence'})
        set_checkpoint(self.store, thread, 'Acceptance criterion: preserve existing URLs.')
        second, process, args = self.turn(thread, 'claude', 'Continue the same work', first)
        request = process.stdin.getvalue()
        self.assertIn('Acceptance criterion', request)
        self.assertIn('Recorded answer', request)
        self.assertIn('Implement the agreed feature', request)
        self.assertNotIn('--resume', args)
        self.assertNotEqual(first['runtime'], second['runtime'])
        self.assertEqual(second['reason'], 'first conversation')
        self.assertTrue(events(self.store, thread, query='test evidence'))

    def test_unchanged_policy_resumes_exact_id_changed_policy_refreshes(self):
        thread = conversation(self.store, self.project.id, 'developer')
        first, _, _ = self.turn(thread, 'claude', 'First request')
        second, _, args = self.turn(thread, 'claude', 'Follow up', first)
        self.assertIn(first['native_id'], args)
        self.assertEqual(first['runtime'], second['runtime'])
        old = self.op('get', global_scope=True)
        self.op('set', global_scope=True, content=old['content'] + '\nNew policy.\n')
        third, process, args = self.turn(thread, 'claude', 'Use current rules', second)
        self.assertNotIn('--resume', args)
        self.assertEqual(second['runtime'], third['runtime'])
        self.assertNotEqual(second['generation'], third['generation'])
        self.assertIn('First request', process.stdin.getvalue())

    def test_capture_failure_retains_user_request_and_reports_failed_attempt(self):
        thread = conversation(self.store, self.project.id, 'developer')
        process = self.fake_process('claude')
        process.stdout = io.StringIO('not-json\n')
        with self.assertRaisesRegex(OrbeHelmError, 'supported JSON'):
            self.turn(thread, 'claude', 'Important user request', process=process)
        recorded = events(self.store, thread)
        self.assertTrue(any(event['kind'] == 'user' for event in recorded))
        self.assertEqual(recorded[-1]['data']['status'], 'failed')

    def test_pagination_scope_and_duplicate_import(self):
        thread = conversation(self.store, self.project.id, 'developer')
        for i in range(5):
            append(self.store, thread, 'user', 'claude', {'text': str(i)}, source_id=str(i))
        append(self.store, thread, 'user', 'claude', {'text': '0'}, source_id='0')
        first = events(self.store, thread, after=0, limit=2)
        second = events(self.store, thread, after=first[-1]['sequence'], limit=2)
        self.assertEqual([e['sequence'] for e in first + second], [1, 2, 3, 4])
        other_path = self.root / 'other'
        other_path.mkdir()
        register_project(self.store, other_path)
        with self.assertRaises(OrbeHelmError):
            execute('conversation', self.root, action='history', project_path=other_path, thread=thread)

    def test_managed_cli_single_turn_records_history_and_launch_without_http(self):
        process = self.fake_process('claude')
        with patch('orbehelm.service.build_opener', side_effect=AssertionError('No HTTP required')), \
                patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                patch('orbehelm.managed.subprocess.Popen', return_value=process), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['chat', '--root', str(self.root), '--project', str(self.project_path),
                                   '--agent=claude', '--prompt=Keep this work']), 0)
        rows = execute('conversation', self.root, action='list', project_path=self.project_path)
        history = events(self.store, rows[0]['id'])
        self.assertTrue(any(item['kind'] == 'assistant' for item in history))
        orbes = execute('orbes', self.root)
        self.assertEqual(orbes[0]['conversation_id'], rows[0]['id'])
        self.assertEqual(orbes[0]['launches'][0]['status'], 'exited')

    def test_native_policy_refresh_keeps_auth_home_and_imports_existing_history(self):
        from orbehelm.adapters import launch
        session = str(uuid.uuid4())
        def fake_native(*args, **kwargs):
            home = Path(kwargs['env']['CLAUDE_CONFIG_DIR'])
            transcript = home / 'projects/work' / (session + '.jsonl')
            transcript.parent.mkdir(parents=True, exist_ok=True)
            transcript.write_text(json.dumps({'type': 'assistant', 'message': {'role': 'assistant', 'content': 'Remember the chosen interface'}}) + '\n')
            return 0
        resolved = resolve_project(self.store, self.project, persist=True)
        output, _ = build_project(self.store, resolved, 'claude')
        with patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                patch('orbehelm.adapters.subprocess.call', side_effect=fake_native) as child:
            launch(self.root, output, resolved, 'claude')
            old_home = child.call_args.kwargs['env']['CLAUDE_CONFIG_DIR']
            original = self.op('get', global_scope=True)['content']
            self.op('set', global_scope=True, content=original + '\nUpdated rule.\n')
            updated = resolve_project(self.store, self.project, persist=True)
            new_output, _ = build_project(self.store, updated, 'claude')
            launch(self.root, new_output, updated, 'claude')
            self.assertEqual(child.call_args.kwargs['env']['CLAUDE_CONFIG_DIR'], old_home)
            self.assertNotIn('--resume', child.call_args.args[0])
            self.assertIn('Remember the chosen interface', child.call_args.args[0][-1])
        thread = conversation(self.store, self.project.id, 'developer')
        self.assertTrue(events(self.store, thread, query='Remember the chosen interface'))

    def test_native_message_normalization_excludes_stale_rules_and_nested_handoffs(self):
        from orbehelm.native_capture import message_text
        self.assertEqual(message_text({'payload': {'role': 'developer', 'content': [{'text': 'Old profile rules'}]}}), '')
        prompt = '<!-- orbehelm:handoff:v1 -->\nOlder context\n<!-- /orbehelm:handoff -->\nActual user request'
        self.assertEqual(message_text({'message': {'role': 'user', 'content': prompt}}), 'Actual user request')

    def test_shared_editor_restore_is_csrf_guarded_and_reaches_projects(self):
        from fastapi.testclient import TestClient
        from orbehelm.product.web import create_app
        old = self.op('get', global_scope=True)
        current = self.op('set', global_scope=True, content=old['content'] + '\nShared edit.\n')
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        with TestClient(app, base_url='http://localhost:8765') as client:
            detail = client.get('/releases/' + old['release'])
            self.assertIn('Restore shared definitions', detail.text)
            data = {'revision': old['release'], 'expected': current['revision']}
            self.assertEqual(client.post('/definitions/rollback', data=data).status_code, 403)
            data['csrf'] = client.cookies['orbehelm_csrf']
            self.assertEqual(client.post('/definitions/rollback', data=data).status_code, 200)
        self.assertEqual(self.op('get')['content'], old['content'])

    def test_tool_event_volume_does_not_hide_the_user_goal_from_handoff(self):
        thread = conversation(self.store, self.project.id, 'developer')
        append(self.store, thread, 'user', 'codex', {'text': 'Preserve the public API while fixing retries.'})
        for number in range(205):
            append(self.store, thread, 'agent_event', 'codex', {'type': 'tool_progress', 'number': number})
        append(self.store, thread, 'assistant', 'codex', {'text': 'The failing case is identified.'})
        handoff = bootstrap(self.store, thread)
        self.assertIn('Preserve the public API', handoff)
        self.assertIn('failing case', handoff)

    def test_typed_registration_validation_rejects_missing_source_and_literal_credentials(self):
        before = configuration_for(self.store, self.project).id
        for target, data in [('definition.skill.invalid', {'schema_version': 1}),
                             ('definition.mcp.invalid', {'schema_version': 1, 'type': 'http', 'url': 'https://user:secret@example.test/mcp'})]:
            with self.assertRaises(OrbeHelmError):
                self.op('add', target, content=json.dumps(data))
        self.assertEqual(configuration_for(self.store, self.project).id, before)

    def test_explicit_claude_tool_grants_refresh_policy_without_global_changes(self):
        thread = conversation(self.store, self.project.id, 'developer')
        first, _, _ = self.turn(thread, 'claude', 'Inspect the files')
        second, _, args = self.turn(thread, 'claude', 'Apply the edit', first, allowed_tools=('Edit',))
        self.assertIn('--allowedTools', args)
        self.assertEqual(args[args.index('--allowedTools') + 1], 'Edit')
        self.assertNotIn('--resume', args)
        self.assertNotEqual(first['policy_digest'], second['policy_digest'])
        third, _, args = self.turn(thread, 'claude', 'Continue', second, allowed_tools=('Edit',))
        self.assertIn(second['native_id'], args)
        from orbehelm.managed import tool_rule
        with self.assertRaises(OrbeHelmError):
            tool_rule('--dangerously-skip-permissions')

    def test_chat_tool_grants_are_explicit_audited_and_clearable(self):
        process = self.fake_process('claude')
        with patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                patch('orbehelm.managed.subprocess.Popen', return_value=process) as child, \
                patch('builtins.input', side_effect=['/allow-tool Edit', 'Apply an approved edit', '/clear-tools', '/exit']), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['chat', '--root', str(self.root), '--project', str(self.project_path), '--agent=claude']), 0)
        self.assertIn('--allowedTools', child.call_args.args[0])
        thread = conversation(self.store, self.project.id, 'developer')
        grants = [item for item in events(self.store, thread) if item['kind'] == 'permission_grant']
        self.assertEqual(len(grants), 2)
        self.assertEqual(grants[-1]['data']['rules'], [])


if __name__ == '__main__':
    unittest.main()

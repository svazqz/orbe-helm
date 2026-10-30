"""Optional memory uses native history without recording conversation bodies."""
import contextlib
import io
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import test_cli_memory as fixtures
from orbehelm.configuration import load
from orbehelm.conversations import conversation, events
from orbehelm.managed import run_turn
from orbehelm.product.projects import resolve_project, build_project
from orbehelm.domain.conversations.policies import session_reason, NATIVE_CONTINUITY


class OptionalMemoryTests(TestCase):
    def setUp(self):
        self.fixture = fixtures.LocalMemoryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.thread = conversation(self.fixture.store, self.fixture.project.id, 'developer')

    def turn(self, agent='claude', force=False):
        f = self.fixture
        resolved = resolve_project(f.store, f.project, persist=True)
        output, _ = build_project(f.store, resolved, agent)
        runtime = f.root / 'state/conversations' / self.thread
        runtime.mkdir(parents=True, exist_ok=True)
        process = f.fake_process(agent)
        with patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                patch('orbehelm.managed.subprocess.Popen', return_value=process) as child, \
                patch('orbehelm.managed.append', side_effect=AssertionError('Unexpected capture')), \
                patch('orbehelm.managed.bootstrap', side_effect=AssertionError('Unexpected handoff')), \
                patch('orbehelm.memory.repository', side_effect=AssertionError('Unexpected memory engine')), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = run_turn(f.store, self.thread, agent, output, resolved, runtime,
                              'Only native context', force=force, memory_enabled=False)
        return result, child.call_args, process

    def test_definition_change_resumes_same_session_and_refreshes_current_file(self):
        first, call, _ = self.turn()
        instructions = Path(call.kwargs['env']['ORBEHELM_INSTRUCTIONS_FILE'])
        old = self.fixture.op('get', global_scope=True)['content']
        self.fixture.op('set', global_scope=True, content=old + '\nManual refresh rule.\n')
        second, call, process = self.turn()
        self.assertIn(first['native_id'], call.args[0])
        self.assertEqual(second['reason'], NATIVE_CONTINUITY)
        self.assertEqual(str(instructions), call.kwargs['env']['ORBEHELM_INSTRUCTIONS_FILE'])
        self.assertIn('Manual refresh rule.', instructions.read_text())
        self.assertNotIn('Currently authorized knowledge', process.stdin.getvalue())
        self.assertEqual(events(self.fixture.store, self.thread), [])
        self.assertNotIn('ORBEHELM_MEMORY_BINDING', call.kwargs['env'])

    def test_each_provider_keeps_its_own_native_session(self):
        claude, _, _ = self.turn('claude')
        codex, _, _ = self.turn('codex')
        _, call, _ = self.turn('claude')
        self.assertIn(claude['native_id'], call.args[0])
        _, call, _ = self.turn('codex')
        self.assertIn(codex['native_id'], call.args[0])
        self.assertEqual(events(self.fixture.store, self.thread), [])

    def test_explicit_new_session_overrides_native_continuity(self):
        first, _, _ = self.turn()
        second, call, _ = self.turn(force=True)
        self.assertNotIn(first['native_id'], call.args[0])
        self.assertEqual(second['reason'], 'explicit fresh conversation')

    def test_enabling_memory_starts_fresh_without_importing_off_period(self):
        off, _, _ = self.turn()
        on, process, args = self.fixture.turn(self.thread, 'claude', 'Now record knowledge')
        self.assertNotIn(off['native_id'], args)
        self.assertEqual(on['reason'], 'memory enabled; fresh native context')
        self.assertNotIn('Only native context', process.stdin.getvalue())

    def test_configuration_can_disable_memory(self):
        path = self.fixture.root / 'defaults.ini'
        path.write_text('[ORBEHELM]\nmemory = false\nagent = claude\n')
        defaults, _ = load(path)
        self.assertIs(defaults['memory'], False)

    def test_policy_refresh_is_manual_only_when_memory_disabled(self):
        previous = {'agent': 'claude', 'policy_digest': 'old', 'memory_enabled': False}
        self.assertEqual(session_reason(previous, 'new', 'claude', memory_enabled=False), NATIVE_CONTINUITY)
        self.assertEqual(session_reason(previous, 'new', 'claude'), 'memory enabled; fresh native context')
        self.assertEqual(session_reason(previous, 'new', 'codex', memory_enabled=False), 'agent changed')

    def test_native_launch_skips_capture_and_resumes_after_definition_change(self):
        from orbehelm.adapters import launch
        f = self.fixture
        calls = []
        def fake_child(*args, **kwargs):
            calls.append((args[0], kwargs['env']))
            return 0
        with patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                patch('orbehelm.adapters.subprocess.call', side_effect=fake_child), \
                patch('orbehelm.adapters.discover_native_session', return_value='native-session'), \
                patch('orbehelm.adapters.can_resume', side_effect=lambda runtime, agent, record: bool(record.get('native_session_id'))), \
                patch('orbehelm.native_capture.capture', side_effect=AssertionError('Unexpected capture')), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            for iteration in range(2):
                resolved = resolve_project(f.store, f.project, persist=True)
                output, _ = build_project(f.store, resolved, 'claude')
                launch(f.root, output, resolved, 'claude', memory_enabled=False)
                if iteration == 0:
                    old = f.op('get', global_scope=True)['content']
                    f.op('set', global_scope=True, content=old + '\nNative manual rule.\n')
        self.assertIn('native-session', calls[1][0])
        self.assertIn('--resume', calls[1][0])
        instructions = calls[1][1]['ORBEHELM_INSTRUCTIONS_FILE']
        self.assertEqual(instructions, calls[0][1]['ORBEHELM_INSTRUCTIONS_FILE'])
        self.assertIn('Native manual rule.', Path(instructions).read_text())
        self.assertEqual(events(f.store, self.thread), [])

"""Dedicated login processes are tested with local fake children, never provider orbes."""
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from orbehelm.core import OrbeHelmError
from orbehelm.product.authentication import LoginManager, login_command

REPO = Path(__file__).resolve().parents[1]


class LoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=REPO / 'tests')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = SimpleNamespace(id='project', path=str(self.root))

    def finished(self, manager, job):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            result = manager.get('project', job['id'])
            if result['state'] != 'waiting':
                return result
            time.sleep(.01)
        self.fail('Fake sign-in process did not finish')

    def test_fixed_commands_preserve_each_native_runtime_environment(self):
        output = self.root / 'output'
        output.mkdir()
        (output / 'opencode.json').write_text(json.dumps({'mcp': {}}))
        for agent in ['codex', 'claude', 'opencode']:
            command, env = login_command(agent, self.root / 'runtime', output, 'docs')
            self.assertEqual(command[0], agent)
            self.assertEqual(command[-1], 'docs')
            self.assertIn('mcp', command)
            if agent == 'codex':
                self.assertEqual(env['CODEX_HOME'], str(self.root / 'runtime/codex-home'))
            elif agent == 'claude':
                self.assertIn(str(output / 'mcp.json'), command)
                self.assertIn('--strict-mcp-config', command)
                self.assertEqual(env['CLAUDE_CONFIG_DIR'], str(self.root / 'runtime/claude-home'))
            else:
                self.assertEqual(json.loads(env['OPENCODE_CONFIG_CONTENT']), {'mcp': {}})
                self.assertEqual(env['XDG_DATA_HOME'], str(self.root / 'runtime/data'))
        with self.assertRaises(OrbeHelmError):
            login_command('codex', self.root, output, '--bad-option')

    def test_completion_and_failure_expose_no_process_output(self):
        for exit_code, expected in [(0, 'completed'), (1, 'failed')]:
            manager = LoginManager()
            self.addCleanup(manager.close)
            command = [sys.executable, '-c', f'print("private-value"); raise SystemExit({exit_code})']
            with patch('orbehelm.product.authentication.login_command', return_value=(command, {})):
                job = manager.start(self.project, 'codex', 'docs', self.root, self.root)
            result = self.finished(manager, job)
            self.assertEqual(result['state'], expected)
            self.assertNotIn('private-value', str(result))
            with self.assertRaises(OrbeHelmError):
                manager.get('other-project', job['id'])

    def test_duplicate_jobs_cancellation_timeout_and_shutdown(self):
        command = [sys.executable, '-c', 'import time; time.sleep(20)']
        for action, expected in [('cancel', 'cancelled'), ('timeout', 'expired'), ('close', 'cancelled')]:
            manager = LoginManager(timeout=.05 if action == 'timeout' else 5)
            self.addCleanup(manager.close)
            with patch('orbehelm.product.authentication.login_command', return_value=(command, {})):
                job = manager.start(self.project, 'codex', 'docs', self.root, self.root)
                self.assertEqual(manager.start(self.project, 'codex', 'docs', self.root, self.root)['id'], job['id'])
            if action == 'cancel':
                manager.cancel('project', job['id'])
            elif action == 'close':
                manager.close()
            self.assertEqual(self.finished(manager, job)['state'], expected)
            self.assertIsNotNone(manager.jobs[job['id']].process.poll())

    def test_missing_cli_has_a_safe_error_and_no_job(self):
        manager = LoginManager()
        self.addCleanup(manager.close)
        with patch('orbehelm.product.authentication.subprocess.Popen', side_effect=FileNotFoundError('private')):
            with self.assertRaisesRegex(OrbeHelmError, 'Unable to start'):
                manager.start(self.project, 'codex', 'docs', self.root, self.root)
        self.assertEqual(manager.jobs, {})

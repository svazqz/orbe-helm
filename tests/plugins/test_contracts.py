"""Run identical capability/command/event assertions for both bundled plugins."""
from pathlib import Path
import json
import sys
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from orbehelm.plugins.codex import Adapter as Codex
from orbehelm.plugins.claude import Adapter as Claude
from orbehelm.domain.shared.errors import OrbeHelmError, UnsupportedCapability


class ProviderContracts:
    adapter_type = None

    def setUp(self):
        self.adapter = self.adapter_type()

    def test_capabilities_distinguish_fixture_evidence_from_live_and_isolation(self):
        capabilities = self.adapter.describe()
        for name in ['render', 'structured_stream', 'exact_resume']:
            capabilities.require(name)
        for name in ['exclusive_context', 'interactive_permissions', 'workspace_boundary', 'missing']:
            with self.assertRaises(UnsupportedCapability):
                capabilities.require(name)
        self.assertTrue(all(entry.evidence in {'design', 'synthetic-contract'} for entry in capabilities.entries))

    def test_fresh_and_exact_resume_do_not_select_ambient_history(self):
        fresh = self.adapter.stream_command('/fixture', 'workspace-write', 'private prompt')
        self.assertNotIn('private prompt', fresh.argv)
        self.assertEqual(fresh.stdin, 'private prompt')
        self.assertNotIn('--continue', fresh.argv)
        self.assertNotIn('--last', fresh.argv)
        resumed = self.adapter.stream_command('/fixture', 'workspace-write', 'next', 'exact-session')
        self.assertIn('exact-session', resumed.argv)
        self.assertNotIn('--continue', resumed.argv)
        self.assertNotIn('--last', resumed.argv)
        for native_id in ['../bad', '--last', 'with space', 'x' * 129]:
            with self.assertRaises(OrbeHelmError):
                self.adapter.stream_command('/fixture', 'workspace-write', 'prompt', native_id)
        with self.assertRaises(OrbeHelmError):
            self.adapter.stream_command('/fixture', 'unknown-access', 'prompt')

    def test_config_translation_preserves_transport_and_env_contract(self):
        servers = {'local': {'type': 'stdio', 'command': 'fixture', 'args': ['--literal', '$VALUE'], 'env': {'TOKEN': 'TOKEN'}},
                   'remote': {'type': 'http', 'url': 'https://example.invalid/mcp'}}
        files = self.adapter.render('current rules', servers, '/fixture')
        self.assertEqual(len(files), 1)
        self.assertNotIn('/', files[0].path)
        if self.adapter.id == 'codex':
            data = tomllib.loads(files[0].content)
            self.assertEqual(data['developer_instructions'], 'current rules')
            self.assertEqual(data['mcp_servers']['local']['args'], servers['local']['args'])
        else:
            data = json.loads(files[0].content)['mcpServers']
            self.assertEqual(data['local']['env'], {'TOKEN': '${TOKEN}'})
            self.assertEqual(data['remote']['url'], servers['remote']['url'])

    def test_events_normalize_public_text_identity_completion_and_failures(self):
        if self.adapter.id == 'codex':
            start = {'type': 'thread.started', 'thread_id': 'id'}
            text = {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'answer'}}
            end, failure = {'type': 'turn.completed'}, {'type': 'turn.failed'}
        else:
            start = {'type': 'system', 'session_id': 'id'}
            text = {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'answer'}]}}
            end, failure = {'type': 'result'}, {'type': 'result', 'is_error': True}
        self.assertEqual(self.adapter.decode_event(start).native_id, 'id')
        self.assertEqual(self.adapter.decode_event(text).text, 'answer')
        self.assertTrue(self.adapter.decode_event(end).terminal)
        self.assertTrue(self.adapter.decode_event(failure).failed)
        self.assertFalse(self.adapter.decode_event({'type': 'future_event'}).terminal)

    def test_login_plan_never_reads_credentials(self):
        plan, env = self.adapter.login_command('/fixture/runtime', '/fixture/build', 'server')
        self.assertIn('server', plan.argv)
        self.assertTrue(all(value.startswith('/fixture/runtime/') for value in env.values()))


class CodexContracts(ProviderContracts, unittest.TestCase):
    adapter_type = Codex


class ClaudeContracts(ProviderContracts, unittest.TestCase):
    adapter_type = Claude

    def test_claude_permissions_are_explicit_validated_native_rules(self):
        plan = self.adapter.stream_command('/fixture', 'workspace-write', 'prompt', allowed_tools=('Edit', 'Bash(python3 *)'))
        self.assertIn('Edit,Bash(python3 *)', plan.argv)
        with self.assertRaises(OrbeHelmError):
            self.adapter.stream_command('/fixture', 'workspace-write', 'prompt', allowed_tools=('Edit\nBash',))

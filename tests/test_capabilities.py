"""Authentication observations must be scoped and must never disclose raw output."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from orbehelm.adapters import mcp_authentication


class AuthenticationTests(unittest.TestCase):
    servers = {'docs': {'type': 'http', 'url': 'https://example.test/mcp'}}

    def observation(self, value):
        result = subprocess.CompletedProcess([], 0, json.dumps(value), 'private stderr')
        with patch('orbehelm.adapters.subprocess.run', return_value=result) as run:
            status = mcp_authentication('codex', '/checkout/runtime', '/project', self.servers)
        self.assertEqual(run.call_args.kwargs['env']['CODEX_HOME'], '/checkout/runtime/codex-home')
        self.assertEqual(run.call_args.kwargs['cwd'], '/project')
        self.assertEqual(run.call_args.kwargs['timeout'], 15)
        self.assertNotIn('private', str(status))
        return status['docs']['status']

    def test_reported_states_are_not_inferred_from_credentials(self):
        for state, expected in [('oauth', 'Authenticated'), ('bearer_token', 'Credential configured'),
                                ('not_logged_in', 'Not authenticated'), ('unknown', 'Unknown'),
                                ('unsupported', 'Unsupported'), ({}, 'Unknown')]:
            with self.subTest(state=state):
                self.assertEqual(self.observation([{'name': 'docs', 'auth_status': state,
                    'transport': {'url': self.servers['docs']['url']}}]), expected)

    def test_wrong_endpoint_and_malformed_output_remain_unknown(self):
        for rows in [{}, [None], [{'name': 'docs', 'auth_status': 'oauth'}],
                     [{'name': 'docs', 'auth_status': 'oauth', 'transport': {'url': 'https://other.test'}}]]:
            self.assertEqual(self.observation(rows), 'Unknown')

    def test_missing_runtime_unsupported_agents_and_failures(self):
        with patch('orbehelm.adapters.subprocess.run') as run:
            for agent, runtime in [('codex', None), ('claude', '/runtime'), ('opencode', '/runtime')]:
                self.assertEqual(mcp_authentication(agent, runtime, '/project', self.servers)['docs']['status'], 'Unknown')
            run.assert_not_called()
        for error in [FileNotFoundError('private'), subprocess.TimeoutExpired('private', 15)]:
            with patch('orbehelm.adapters.subprocess.run', side_effect=error):
                report = mcp_authentication('codex', '/runtime', '/project', self.servers)
                self.assertEqual(report['docs']['status'], 'Unknown')
                self.assertNotIn('private', str(report))


if __name__ == '__main__':
    unittest.main()

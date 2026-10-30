"""Silent native handoffs retain instructions and runtime MCP bindings."""
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from orbehelm.handoff_runtime import prepare
from orbehelm.plugins.codex.adapter import Adapter


class HandoffRuntimeTests(unittest.TestCase):
    def test_codex_keeps_runtime_servers_and_explicit_user_prompt(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
            root = Path(temporary)
            output = root / 'build'
            output.mkdir()
            (output / 'instructions.md').write_text('Current profile and specialization')
            config = ('developer_instructions = "Current profile and specialization"\n'
                      '[mcp_servers.orbehelm]\ncommand = "runtime-bridge"\n')
            (output / 'config.toml').write_text(config)
            destination = prepare(output, 'codex', root, 'Historical context: chosen interface')
            rendered = tomllib.loads((destination / 'config.toml').read_text())
            self.assertIn('Current profile and specialization', rendered['developer_instructions'])
            self.assertIn('Historical context: chosen interface', rendered['developer_instructions'])
            self.assertEqual(rendered['mcp_servers']['orbehelm']['command'], 'runtime-bridge')
            self.assertEqual((output / 'config.toml').read_text(), config)
            adapter = Adapter()
            self.assertEqual(adapter.command(str(destination)).argv[-1], '--dangerously-bypass-approvals-and-sandbox')
            self.assertEqual(adapter.command(str(destination), 'Fix the bug').argv[-1], 'Fix the bug')

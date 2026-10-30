"""Forbid new cycles and keep domain/application independent of concrete effects."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

from .graph import boundary_violations, cyclic_edges, import_graph

ROOT = Path(__file__).resolve().parents[2]


class ArchitectureTests(unittest.TestCase):
    def test_no_new_cycles_or_layer_violations(self):
        graph, external = import_graph(ROOT / 'src')
        baseline = json.loads((ROOT / 'tests/fixtures/compatibility/import-allowlist.json').read_text())
        # execute() is a retained public composition entry, not an inward handler.
        # This single wiring edge must disappear when its legacy callers are retired.
        graph.get('orbehelm.application', set()).discard('orbehelm.bootstrap')
        for key, actual in [('cycles', cyclic_edges(graph)), ('boundaries', boundary_violations(graph))]:
            allowed = {tuple(edge) for edge in baseline[key]}
            self.assertFalse(actual - allowed, f'New {key}: {sorted(actual - allowed)}')
        for module, imports in external.items():
            if module.startswith(('orbehelm.domain.', 'orbehelm.application.')):
                self.assertFalse(imports - sys.stdlib_module_names, (module, imports))
            if module.startswith('orbehelm.domain.'):
                pure_modules = {'__future__', 'dataclasses', 'enum', 'typing', 'json', 'hashlib', 're', 'urllib'}
                self.assertFalse(imports - pure_modules, f'Domain effect/nondeterminism import: {module}: {imports}')

    def test_historical_migrations_are_unchanged(self):
        checksums = json.loads((ROOT / 'tests/fixtures/compatibility/migration-checksums.json').read_text())
        for relative, expected in checksums.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), expected, relative)

    def test_inward_code_has_no_native_provider_flags_or_identifiers(self):
        import ast
        native_values = {'codex', 'claude', 'opencode', '--no-daemon', '--allowedTools',
                         '--append-system-prompt-file', '--strict-mcp-config', '--setting-sources',
                         'CODEX_HOME', 'CLAUDE_CONFIG_DIR', 'OPENCODE_CONFIG_CONTENT'}
        for package in ['domain', 'application']:
            for path in (ROOT / 'src/orbehelm' / package).rglob('*.py'):
                for node in ast.walk(ast.parse(path.read_text())):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        self.assertNotIn(node.value, native_values, str(path.relative_to(ROOT)))

    def test_feature_inventory_preserves_existing_tests(self):
        manifest = json.loads((ROOT / 'tests/feature_contracts.json').read_text())
        import ast
        current = set()
        for path in (ROOT / 'tests').glob('test_*.py'):
            for node in ast.parse(path.read_text()).body:
                if isinstance(node, ast.ClassDef):
                    current.update(f'{path.stem}.{node.name}.{method.name}' for method in node.body
                                   if isinstance(method, ast.FunctionDef) and method.name.startswith('test_'))
        covered = {test for feature in manifest['features'] for test in feature['existing_tests']}
        self.assertEqual(len(covered), manifest['baseline_tests'])
        self.assertFalse(covered - current, f'Unmapped test removal: {sorted(covered - current)}')
        groups = {feature['id'] for feature in manifest['features']}
        for records, names, key in [('cli_contracts', 'cli_commands', 'command'),
                                    ('operation_contracts', 'application_operations', 'operation')]:
            self.assertEqual({item[key] for item in manifest[records]}, set(manifest[names]))
            self.assertTrue(all(item['test_group'] in groups and item['replacement_suite'] for item in manifest[records]))
        cli_tree = ast.parse((ROOT / 'src/orbehelm/cli.py').read_text())
        choices = []
        for call in ast.walk(cli_tree):
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == 'add_argument' and call.args
                    and isinstance(call.args[0], ast.Constant) and call.args[0].value == 'command'):
                choices = next(ast.literal_eval(keyword.value) for keyword in call.keywords if keyword.arg == 'choices')
        self.assertEqual(set(choices), set(manifest['cli_commands']), 'Update command contracts for CLI changes')

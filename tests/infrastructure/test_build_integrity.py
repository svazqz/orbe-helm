"""Extracted source files must still invalidate immutable generated builds."""
from pathlib import Path
import sys
import unittest
import tempfile
import shutil
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from orbehelm.core import resolve

ROOT = Path(__file__).resolve().parents[2]


class BuildIntegrityTests(unittest.TestCase):
    def test_locked_project_sources_still_refresh_extracted_implementation(self):
        from orbehelm.product.commands import initialize
        from orbehelm.product.database import Store
        from orbehelm.product.projects import register_project, resolve_project
        from orbehelm.sessions import policy_digest
        verification = ROOT / 'state/verification/independent-core-refactor'
        verification.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=verification) as temporary:
            root = Path(temporary)
            for name in ['definitions', 'registry', 'examples']:
                shutil.copytree(ROOT / name, root / name)
            project_path = root / 'work'
            project_path.mkdir()
            initialize(root)
            store = Store(root)
            try:
                project = register_project(store, project_path)
                before = resolve_project(store, project, persist=True)
                selected = ROOT / 'src/orbehelm/plugins/codex/adapter.py'
                read_bytes = Path.read_bytes
                def changed(path):
                    return read_bytes(path) + (b'\n# revised plugin\n' if path == selected else b'')
                with patch.object(Path, 'read_bytes', changed):
                    after = resolve_project(store, project)
                self.assertNotEqual(before['fingerprint'], after['fingerprint'])
                self.assertEqual(before['sources'], after['sources'])
                self.assertEqual(policy_digest(before), policy_digest(after))
            finally:
                store.close()

    def test_plugin_and_domain_changes_invalidate_build_without_changing_policy(self):
        from orbehelm.sessions import policy_digest
        before = resolve(ROOT, project=ROOT)
        self.assertIn('plugins/claude/adapter.py', before['implementation'])
        self.assertIn('domain/definitions/composition.py', before['implementation'])
        read_bytes = Path.read_bytes
        for relative in ['plugins/claude/adapter.py', 'domain/definitions/composition.py']:
            selected = ROOT / 'src/orbehelm' / relative
            def changed(path):
                return read_bytes(path) + (b'\n# revised implementation\n' if path == selected else b'')
            with patch.object(Path, 'read_bytes', changed):
                after = resolve(ROOT, project=ROOT)
            self.assertNotEqual(before['fingerprint'], after['fingerprint'])
            self.assertEqual(policy_digest(before), policy_digest(after))

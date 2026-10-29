"""Source snapshots are portable and require no product dependencies."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from orbehelm.core import OrbeHelmError, resolve, build_directory
from orbehelm.snapshots import save_snapshot, verify_snapshot, capture_file

REPO = Path(__file__).resolve().parents[1]


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=REPO / 'tests')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_round_trip_reuse_corruption_and_executable_bits(self):
        files = {'instructions.md': {'content': b'first version', 'executable': False},
                 'script.sh': {'content': b'exit 0\n', 'executable': True}}
        key = save_snapshot(self.root, files)
        source = verify_snapshot(self.root, key)
        self.assertEqual((source / 'instructions.md').read_bytes(), b'first version')
        self.assertTrue((source / 'script.sh').stat().st_mode & 0o111)
        before = (source / 'instructions.md').stat().st_mtime_ns
        self.assertEqual(save_snapshot(self.root, files), key)
        self.assertEqual((source / 'instructions.md').stat().st_mtime_ns, before)
        changed = dict(files, **{'instructions.md': {'content': b'next version', 'executable': False}})
        self.assertNotEqual(save_snapshot(self.root, changed), key)
        (source / 'instructions.md').write_text('tampered')
        with self.assertRaisesRegex(OrbeHelmError, 'Corrupted'):
            verify_snapshot(self.root, key)

    def test_rejects_traversal_symlinks_and_runtime_sources(self):
        (self.root / 'safe.md').write_text('safe')
        (self.root / 'alias.md').symlink_to(self.root / 'safe.md')
        for name in ('../safe.md', '/etc/passwd', 'alias.md', 'state/auth/codex/auth.json', '.aws/credentials'):
            with self.subTest(path=name), self.assertRaises(OrbeHelmError):
                capture_file(self.root, name, {})
        with self.assertRaises(OrbeHelmError):
            save_snapshot(self.root, {'../outside.md': {'content': b'no', 'executable': False}})

    def test_project_context_and_profile_override_order(self):
        project = self.root / 'work'
        project.mkdir()
        context = self.root / 'context'
        context.mkdir()
        (context / 'orbehelm.project.json').write_text(json.dumps({'schema_version': 1, 'instructions': ['notes.md']}))
        (context / 'notes.md').write_text('Pinned project notes')
        from orbehelm.composition import MARKER, SECTION_TITLES
        override = MARKER + '\n# Override\n' + '\n'.join(
            f'## {name}' + (' [override]\nProject-local responsibility' if name == 'Responsibilities' else '')
            for name in SECTION_TITLES)
        result = resolve(REPO, spec='python', project=project, project_context=context,
                         profile_overrides={'developer': override})
        instructions = result['composed_instructions']
        self.assertIn('Project-local responsibility', instructions)
        self.assertIn('Pinned project notes', instructions)
        self.assertIn('Python', instructions)
        result['project_id'] = 'example-project'
        self.assertTrue(build_directory(self.root, result).is_relative_to(self.root / 'state/projects/example-project'))
        result['project_id'] = '../../outside'
        with self.assertRaises(OrbeHelmError):
            build_directory(self.root, result)

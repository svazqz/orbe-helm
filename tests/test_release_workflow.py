"""Release gates reject inconsistent metadata before publication."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import tarfile
import io
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_check', ROOT / 'scripts/check_release.py')
release_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_check)


class ReleaseChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'tests')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'src/orbehelm').mkdir(parents=True)
        for name in ('pyproject.toml', 'CHANGELOG.md', 'README.md', 'requirements.lock', 'requirements-core.lock',
                     'src/orbehelm/__init__.py', 'requirements-runtime.lock', 'requirements-dev.lock', 'requirements-memory.lock'):
            shutil.copy2(ROOT / name, self.root / name)
        (self.root / 'pyproject.toml').write_text('[project]\nversion = "1.2.3a4"\n')
        (self.root / 'src/orbehelm/__init__.py').write_text('__version__ = "1.2.3a4"\n')
        (self.root / 'README.md').write_text('Release `1.2.3a4`\n')
        (self.root / 'CHANGELOG.md').write_text('## 1.2.3a4 — 2026-10-30\nFixture release\n')

    def test_release_version_and_tag_must_agree(self):
        self.assertEqual(release_check.validate(self.root, 'v1.2.3-alpha.4'), '1.2.3a4')
        with self.assertRaisesRegex(ValueError, 'Tag must'):
            release_check.validate(self.root, 'orbehelm-alpha')
        (self.root / 'src/orbehelm/__init__.py').write_text('__version__ = "1.2.3a5"\n')
        with self.assertRaisesRegex(ValueError, 'versions differ'):
            release_check.validate(self.root)

    def test_stale_readme_and_dependency_divergence_are_rejected(self):
        (self.root / 'README.md').write_text('Old release')
        with self.assertRaisesRegex(ValueError, 'README'):
            release_check.validate(self.root)
        (self.root / 'README.md').write_text('Release `1.2.3a4`\n')
        with (self.root / 'requirements-core.lock').open('a') as handle:
            handle.write('unknown==1.0\n')
        with self.assertRaisesRegex(ValueError, 'pins differ'):
            release_check.validate(self.root)

    def test_each_generated_requirement_requires_its_own_hashes(self):
        pin = 'a' * 64
        self.assertEqual(release_check.locked_requirements(
            f'first[extra]==1 --hash=sha256:{pin}\n', 'fixture'), {'first': '1'})
        for text in [f'first==1\nsecond==2 --hash=sha256:{pin}\n',
                     f'first==1 --hash=sha256:{pin}\nfirst==2 --hash=sha256:{pin}\n',
                     'first==1 --hash=sha256:invalid\n']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                release_check.locked_requirements(text, 'fixture')



class SourceArchiveChecks(unittest.TestCase):
    def test_runtime_and_temporary_members_are_rejected(self):
        spec = importlib.util.spec_from_file_location('sdist_check', ROOT / 'scripts/check_sdist.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as directory:
            archive = Path(directory) / 'fixture.tar.gz'
            for name in ['package/state/runtime.json', 'package/tests/tmpfixture/home.json', '../outside']:
                with self.subTest(name=name):
                    with tarfile.open(archive, 'w:gz') as target:
                        member = tarfile.TarInfo(name)
                        member.size = 1
                        target.addfile(member, io.BytesIO(b'x'))
                    with self.assertRaises(ValueError):
                        module.validate(archive)

    def test_source_archive_requires_checkout_launcher(self):
        spec = importlib.util.spec_from_file_location('sdist_check', ROOT / 'scripts/check_sdist.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as directory:
            archive = Path(directory) / 'fixture.tar.gz'
            with tarfile.open(archive, 'w:gz') as target:
                for name in ['setup.sh', 'update.sh', 'pyproject.toml', 'src/orbehelm/installer.py',
                             'definitions/base/instructions.md', 'scripts/dev.py', 'requirements-dev.lock',
                             'requirements.lock', 'requirements-core.lock', 'requirements-runtime.lock',
                             'requirements-memory.lock', 'README.md', 'CHANGELOG.md']:
                    member = tarfile.TarInfo('package/' + name)
                    member.size = 1
                    target.addfile(member, io.BytesIO(b'x'))
            with self.assertRaisesRegex(ValueError, 'oh'):
                module.validate(archive)

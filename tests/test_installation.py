"""Install into disposable homes and verify readiness without authenticated agents."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
import sqlite3
from unittest.mock import MagicMock, Mock, patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fastapi.testclient import TestClient
from orbehelm.adapters import launch, authenticate
from orbehelm.cli import main
from orbehelm.compatibility import orbe_directory, orbe_records
from orbehelm.core import OrbeHelmError, build, resolve
from orbehelm.delegation_runner import execute_delegation
from orbehelm.installer import path_block, startup_files, update_startup, write_manifest
from orbehelm.installer import main as setup_main
from orbehelm.installer import sync_bundled_sources
from orbehelm.layout import auth_directory, runtime_base, stored_runtime, identity
from orbehelm.product.commands import initialize
from orbehelm.product.database import Store
from orbehelm.product.orbes import orbe_details
from orbehelm.product.projects import register_project, resolve_project, build_project
from orbehelm.product.capabilities import runtime_for
from orbehelm.product.web import create_app
from orbehelm.service import health_payload, require_server, server_status, MAX_HEALTH

REPO = Path(__file__).resolve().parents[1]


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=REPO / 'tests')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root, self.home, self.work = self.base / 'app', self.base / 'home', self.base / 'work'
        for directory in (self.root, self.home, self.work):
            directory.mkdir()
        for name in ('definitions', 'registry', 'examples'):
            shutil.copytree(REPO / name, self.root / name)
        environment = patch.dict(os.environ, {'HOME': str(self.home), 'SHELL': '/bin/zsh',
            'ZDOTDIR': str(self.home), 'XDG_CONFIG_HOME': str(self.home / '.config'),
            'ORBEHELM_CONFIG': '', 'ORBEHELM_ROOT': '', 'AGENTIC_CONFIG': '', 'AGENTIC_ROOT': '',
            'ORBEHELM_SERVER_URL': ''})
        environment.start()
        self.addCleanup(environment.stop)

    def installed(self, root=None, home=None):
        root, home = root or self.root, home or self.home / '.orbehelm'
        home.mkdir(parents=True, exist_ok=True)
        write_manifest(root, {'schema_version': 1, 'application': 'orbehelm',
            'orbes_home': str(home), 'server_url': 'http://127.0.0.1:49871', 'complete': True})
        return home

    def network(self, payload=None, status=200):
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.status = status
        response.read.return_value = json.dumps(payload or health_payload(self.root)).encode()
        return patch('orbehelm.service.build_opener', return_value=opener), opener

    def test_server_probe_accepts_only_matching_bounded_ready_responses(self):
        self.installed()
        variants = [({'root_id': 'other'}, False), ({'runtime_id': 'other'}, False),
                    ({'service': 'other'}, False), ({'version': 'old'}, False),
                    ({'protocol_version': 99}, False), ({'ready': False}, False), ({}, True)]
        for changes, expected in variants:
            with self.subTest(changes=changes):
                network, opener = self.network({**health_payload(self.root), **changes})
                with network:
                    self.assertEqual(server_status(self.root)['ready'], expected)
                opener.open.return_value.__enter__.return_value.read.assert_called_once_with(MAX_HEALTH + 1)
        network, opener = self.network()
        for body in (b'not-json', b'x' * (MAX_HEALTH + 1), b'[]'):
            opener.open.return_value.__enter__.return_value.read.return_value = body
            with network:
                self.assertFalse(server_status(self.root)['ready'])
        with patch('orbehelm.service.build_opener') as factory:
            factory.return_value.open.side_effect = URLError('offline')
            self.assertTrue(require_server(self.root)['local'])
            factory.assert_not_called()
        for url in ('https://example.com', 'http://127.0.0.1:0', 'http://user@localhost:8765'):
            with patch.dict(os.environ, {'ORBEHELM_SERVER_URL': url}):
                with self.assertRaises(OrbeHelmError):
                    server_status(self.root)

    def test_native_launch_uses_local_storage_without_a_running_server(self):
        resolved = resolve(self.root, project=self.work)
        from orbehelm.core import build
        output, _ = build(self.root, resolved, 'claude')
        with patch('orbehelm.service.build_opener', side_effect=AssertionError('No HTTP required')), patch('orbehelm.adapters.doctor', return_value={'ok': True}), patch('orbehelm.adapters.subprocess.call', return_value=0) as child:
            self.assertEqual(launch(self.root, output, resolved, 'claude'), 0)
        child.assert_called_once()
        self.installed()
        data = json.loads((self.root / 'installation.json').read_text())
        data['complete'] = False
        (self.root / 'installation.json').write_text(json.dumps(data))
        with self.assertRaisesRegex(OrbeHelmError, 'incomplete'):
            require_server(self.root)

    def test_dry_run_never_checks_server_or_creates_storage(self):
        self.installed()
        with patch('orbehelm.cli.require_server', side_effect=AssertionError('Unexpected readiness check')), \
                contextlib.redirect_stdout(io.StringIO()) as result:
            self.assertEqual(main(['--root', str(self.root), '--project', str(self.work), '--dry-run']), 0)
        self.assertIn('codex --no-daemon', result.getvalue())
        self.assertFalse((self.root / 'state').exists())
        self.assertFalse((runtime_base(self.root) / 'orbes').exists())

    def test_installed_orbes_auth_and_capability_lookup_use_external_home(self):
        home = self.installed()
        initialize(self.root)
        store = Store(self.root)
        self.addCleanup(store.close)
        project = register_project(store, self.work)
        resolved = resolve_project(store, project, persist=True)
        output, _ = build_project(store, resolved, 'codex')
        network, _ = self.network()
        with network, patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                patch('orbehelm.adapters.subprocess.call', return_value=0) as child:
            launch(self.root, output, resolved, 'codex')
            first_home = Path(child.call_args.kwargs['env']['CODEX_HOME'])
            self.assertTrue(first_home.is_relative_to(home / 'orbes'))
            launch(self.root, output, resolved, 'codex')
            self.assertEqual(Path(child.call_args.kwargs['env']['CODEX_HOME']), first_home)
        row = orbe_details(store)[0]
        self.assertEqual(row['runtime_path'], str(first_home.parent))
        self.assertEqual(len(list(orbe_records(self.root))), 1)
        self.assertFalse((self.root / 'state/orbes').exists())
        from orbehelm.product.projects import selection_key
        self.assertEqual(runtime_for(store, project, selection_key(), 'codex', resolved), first_home.parent)
        with self.assertRaises(OrbeHelmError):
            stored_runtime(self.root, self.base / 'other/orbe')
        with patch('orbehelm.adapters.shutil.which', return_value='/fake/codex'), \
                patch('orbehelm.adapters.subprocess.call', return_value=0) as login:
            authenticate(self.root, 'codex')
        self.assertEqual(login.call_args.kwargs['env']['CODEX_HOME'], str(home / 'auth/codex'))
        self.assertEqual(auth_directory(self.root), home / 'auth/codex')
        self.assertEqual(orbe_directory(self.root, row['id']), first_home.parent)

    def test_health_endpoint_and_manual_server_command(self):
        self.installed()
        initialize(self.root)
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        with TestClient(app, base_url='http://localhost') as client:
            response = client.get('/healthz')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), health_payload(self.root))
            self.assertNotIn(str(self.root), response.text)
            (self.root / 'installation.json').write_text(json.dumps({
                **json.loads((self.root / 'installation.json').read_text()), 'complete': False}))
            self.assertEqual(client.get('/healthz').status_code, 503)
        self.installed()
        with patch('orbehelm.cli.server_status', return_value={'ready': False}), \
                patch('orbehelm.product.web.serve') as server:
            self.assertEqual(main(['server', 'start', '--root', str(self.root)]), 0)
        self.assertEqual(server.call_args.args, (self.root.resolve(), '127.0.0.1', 49871))
        with patch('orbehelm.cli.server_status', return_value={'ready': False}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['server', 'status', '--root', str(self.root)]), 1)

    def test_shell_blocks_are_idempotent_preserve_symlinks_and_existing_content(self):
        directory = self.home / "bin/a tool's app/bin"
        for shell, name in [('zsh', '.zshrc'), ('bash', '.bashrc'), ('sh', '.profile'), ('fish', '.config/fish/config.fish')]:
            with self.subTest(shell=shell):
                path = self.home / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('# personal settings\n')
                block = path_block(directory, shell)
                backups = self.root / 'state/backups'
                update_startup(path, block, backups)
                first = path.read_bytes()
                update_startup(path, block, backups)
                self.assertEqual(path.read_bytes(), first)
                self.assertEqual(path.read_text().count('# >>> OrbeHelm PATH >>>'), 1)
                self.assertTrue(path.read_text().startswith('# personal settings\n'))
                self.assertIn(path, startup_files(self.home, shell))
                if shell != 'fish':
                    script = path.read_text() + '\nprintf "%s" "$PATH"\n'
                    result = subprocess.run(['/bin/sh', '-c', script], capture_output=True, text=True, check=True)
                    self.assertTrue(result.stdout.startswith(str(directory) + ':'))
        target = self.home / 'dotfiles'
        target.write_text('# linked\n')
        link = self.home / 'linkedrc'
        link.symlink_to(target)
        update_startup(link, path_block(directory, 'zsh'), self.root / 'state/backups')
        self.assertTrue(link.is_symlink())
        self.assertIn('OrbeHelm PATH', target.read_text())

    def test_setup_installs_reinstalls_and_preserves_data_in_isolated_home(self):
        destination = self.home / "bin/orbe helm's app"
        home = self.home / '.orbehelm'
        destination.mkdir(parents=True)
        self.installed(destination, home)
        environment = destination / '.venv'
        subprocess.run([sys.executable, '-m', 'venv', str(environment)], check=True,
                       capture_output=True, text=True)
        # Offline fixture: reuse only already-tested dependency packages, never source code.
        site = subprocess.check_output([str(environment / 'bin/python3'), '-c',
            'import sysconfig; print(sysconfig.get_path("purelib"))'], text=True).strip()
        import sqlalchemy
        dependency_site = Path(sqlalchemy.__file__).resolve().parents[1]
        (Path(site) / 'test-dependencies.pth').write_text(str(dependency_site) + '\n')
        rc = self.home / '.zshrc'
        rc.write_text('# keep my settings\n')
        command = [str(REPO / 'setup.sh'), '--install-dir', str(destination), '--orbes-dir', str(home),
                   '--shell', 'zsh', '--port', '49871', '--offline']
        env = {**os.environ, 'ORBEHELM_PYTHON': sys.executable,
               'PYTHONPATH': str(dependency_site)}
        result = subprocess.run(command, env=env, cwd=self.work, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        launcher = destination / 'bin/oh'
        self.assertTrue(launcher.is_file())
        self.assertTrue((destination / 'state/orbehelm.sqlite3').is_file())
        self.assertTrue((home / 'orbes').is_dir())
        self.assertEqual(home.stat().st_mode & 0o777, 0o700)
        self.assertFalse((destination / 'state/auth').exists())
        self.assertNotIn(str(REPO / 'src/orbehelm'), launcher.read_text())
        self.assertNotIn(str(REPO / '.venv'), launcher.read_text())
        first_rc = rc.read_bytes()
        definition = destination / 'definitions/base/instructions.md'
        definition.write_text(definition.read_text() + '\nKeep this customization.\n')
        record = home / 'orbes' / uuid.uuid4().hex / 'orbe.json'
        record.parent.mkdir()
        record.write_text(json.dumps({'orbe_id': record.parent.name, 'cwd': str(self.work),
            'agent': 'codex', 'profile': 'developer', 'status': 'exited'}))
        original = record.read_bytes()
        update_command = [str(REPO / 'update.sh'), '--install-dir', str(destination), '--offline']
        result = subprocess.run(update_command, env=env, cwd=self.work, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(rc.read_bytes(), first_rc)
        metadata = json.loads((destination / 'installation.json').read_text())
        self.assertEqual(metadata['orbes_home'], str(home))
        self.assertEqual(metadata['server_url'], 'http://127.0.0.1:49871')
        self.assertTrue(metadata['complete'])
        self.assertEqual((destination / 'CHANGELOG.md').read_bytes(), (REPO / 'CHANGELOG.md').read_bytes())
        with contextlib.closing(sqlite3.connect(destination / 'state/orbehelm.sqlite3')) as database:
            self.assertEqual(database.execute('SELECT version_num FROM alembic_version').fetchone()[0], '0006')
        for relative in ('adapters.py', 'memory_runtime.py', 'domain/orbes/identity.py',
                         'product/coordination.py', 'product/migrations/versions/0006_persistent_workflows.py'):
            self.assertEqual((destination / 'src/orbehelm' / relative).read_bytes(),
                             (REPO / 'src/orbehelm' / relative).read_bytes())
        self.assertIn('Keep this customization.', definition.read_text())
        self.assertEqual(record.read_bytes(), original)
        version = subprocess.run([str(launcher), '--version'], env=env, cwd=self.work,
            capture_output=True, text=True, check=True)
        from orbehelm import __version__
        self.assertIn(__version__, version.stdout)
        stopped = subprocess.run([str(launcher), '--project', str(self.work), '--agent=missing'], env=env,
            cwd=self.work, capture_output=True, text=True)
        self.assertEqual(stopped.returncode, 2)
        self.assertIn('invalid choice', stopped.stderr)
        self.assertEqual(record.read_bytes(), original)

    def test_dependency_failure_preserves_active_application_and_environment(self):
        from orbehelm.installer import prepare_candidate
        self.installed()
        (self.root / 'state').mkdir()
        (self.root / 'src').mkdir()
        (self.root / 'src/old.py').write_text('previous code')
        (self.root / '.venv').mkdir()
        (self.root / '.venv/marker').write_text('previous environment')
        before = {str(p.relative_to(self.root)): p.read_bytes()
                  for p in self.root.rglob('*') if p.is_file()}
        data = {'version': 'candidate', 'memory_extra': False}
        with patch('orbehelm.installer.subprocess.run', side_effect=[None,
                   subprocess.CalledProcessError(1, ['pip', 'install'])]):
            with self.assertRaises(subprocess.CalledProcessError):
                prepare_candidate(REPO, self.root, json.loads((self.root / 'installation.json').read_text()), data, True)
        after = {str(p.relative_to(self.root)): p.read_bytes()
                 for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def activation_fixture(self):
        self.installed()
        (self.root / 'state').mkdir(exist_ok=True)
        (self.root / 'src').mkdir()
        (self.root / 'src/old.py').write_text('previous code')
        (self.root / 'bin').mkdir()
        (self.root / 'bin/oh').write_text('previous launcher')
        (self.root / 'README.md').write_text('previous readme')
        release = self.root / 'state/installations/candidate'
        candidate = release / 'candidate'
        (candidate / 'src').mkdir(parents=True)
        (candidate / 'src/new.py').write_text('candidate code')
        (candidate / 'README.md').write_text('candidate readme')
        from orbehelm.installer import bundled_state
        (release / 'source-state.json').write_text(json.dumps(bundled_state(self.root)))
        previous = json.loads((self.root / 'installation.json').read_text())
        return candidate, release / 'venv/bin/python3', previous

    def test_activation_rejects_source_edits_since_preparation(self):
        from orbehelm.installer import activate_candidate
        candidate, python, previous = self.activation_fixture()
        definition = self.root / 'definitions/base/instructions.md'
        definition.write_text(definition.read_text() + '\nNew local edit after preparation.\n')
        with self.assertRaisesRegex(OrbeHelmError, 'Bundled sources changed'):
            activate_candidate(self.root, candidate, python, {**previous, 'complete': False}, previous)
        self.assertIn('New local edit', definition.read_text())
        self.assertEqual((self.root / 'bin/oh').read_text(), 'previous launcher')
        self.assertEqual(json.loads((self.root / 'installation.json').read_text()), previous)

    def test_activation_failure_restores_previous_files_and_manifest(self):
        from orbehelm.installer import activate_candidate
        candidate, python, previous = self.activation_fixture()
        before = {str(p.relative_to(self.root)): p.read_bytes()
                  for p in self.root.rglob('*') if p.is_file() and 'state' not in p.relative_to(self.root).parts}
        rename = Path.rename
        def fail_readme(path, target):
            if path == candidate / 'README.md':
                raise OSError('injected activation failure')
            return rename(path, target)
        with patch.object(Path, 'rename', fail_readme):
            with self.assertRaisesRegex(OSError, 'injected'):
                activate_candidate(self.root, candidate, python, {**previous, 'complete': False}, previous)
        after = {str(p.relative_to(self.root)): p.read_bytes()
                 for p in self.root.rglob('*') if p.is_file() and 'state' not in p.relative_to(self.root).parts}
        self.assertEqual(before, after)
        self.assertEqual(json.loads((candidate.parent / 'activation.json').read_text())['phase'], 'rolled-back')

    def test_migration_failure_retains_recovery_and_blocks_launch(self):
        from orbehelm.installer import activate_candidate
        candidate, python, previous = self.activation_fixture()
        with patch('orbehelm.installer.subprocess.run', side_effect=subprocess.CalledProcessError(1, ['migrate'])), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(subprocess.CalledProcessError):
                activate_candidate(self.root, candidate, python, {**previous, 'complete': False}, previous)
        metadata = json.loads((self.root / 'installation.json').read_text())
        self.assertFalse(metadata['complete'])
        self.assertEqual((Path(metadata['recovery_directory']) / 'src/old.py').read_text(), 'previous code')
        with self.assertRaisesRegex(OrbeHelmError, 'incomplete'):
            require_server(self.root)

    def test_setup_rejects_missing_python_and_unmanaged_destination(self):
        failed = subprocess.run([str(REPO / 'setup.sh')], env={**os.environ, 'ORBEHELM_PYTHON': '/missing/python'},
            cwd=self.work, capture_output=True, text=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('Python 3.11', failed.stderr)
        self.assertFalse((self.home / 'bin').exists())
        failed = subprocess.run([str(REPO / 'setup.sh'), '--install-dir', str(self.root)],
            env={**os.environ, 'ORBEHELM_PYTHON': sys.executable}, cwd=self.work, capture_output=True, text=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('not an OrbeHelm installation', failed.stderr)

    def test_update_requires_existing_installation_before_creating_files(self):
        destination = self.home / 'missing'
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(setup_main(['--update', '--install-dir', str(destination)]), 1)
        self.assertIn('run setup.sh first', error.getvalue())
        self.assertFalse(destination.exists())

    def test_bundled_updates_preserve_customizations_and_refresh_unchanged_files(self):
        source, target = self.base / 'source', self.base / 'target'
        (source / 'definitions').mkdir(parents=True)
        target.mkdir()
        for name in ('unchanged', 'customized', 'removed', 'deleted', 'script'):
            (source / 'definitions' / name).write_text('original')
        baseline = sync_bundled_sources(source, target, None)
        (target / 'definitions/customized').write_text('local edit')
        (target / 'definitions/deleted').unlink()
        (target / 'definitions/local-only').write_text('local addition')
        for name in ('unchanged', 'customized', 'deleted'):
            (source / 'definitions' / name).write_text('upstream edit')
        (source / 'definitions/removed').unlink()
        (source / 'definitions/new').write_text('upstream addition')
        (source / 'definitions/script').chmod(0o755)
        with contextlib.redirect_stdout(io.StringIO()) as report:
            sync_bundled_sources(source, target, {'bundled_sources': baseline})
        self.assertEqual((target / 'definitions/unchanged').read_text(), 'upstream edit')
        self.assertEqual((target / 'definitions/customized').read_text(), 'local edit')
        self.assertFalse((target / 'definitions/deleted').exists())
        self.assertFalse((target / 'definitions/removed').exists())
        self.assertEqual((target / 'definitions/new').read_text(), 'upstream addition')
        self.assertEqual((target / 'definitions/local-only').read_text(), 'local addition')
        self.assertTrue((target / 'definitions/script').stat().st_mode & 0o111)
        self.assertIn('customized', report.getvalue())
        # Pre-tracking installations retain files whose origin cannot be established.
        (target / 'definitions/unchanged').write_text('unknown old source')
        with contextlib.redirect_stdout(io.StringIO()):
            sync_bundled_sources(source, target, {})
        self.assertEqual((target / 'definitions/unchanged').read_text(), 'unknown old source')

    def test_setup_reports_missing_venv_before_creating_an_installation(self):
        destination = self.home / 'bin/orbehelm'
        with patch('orbehelm.installer.importlib.util.find_spec', return_value=None), \
                contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(setup_main(['--install-dir', str(destination), '--no-path']), 1)
        self.assertIn('python3-venv', error.getvalue())
        self.assertFalse(destination.exists())

    def test_reinstall_refuses_reachable_unhealthy_server_before_changing_files(self):
        home = self.installed()
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('orbehelm.installer.server_status', return_value={'ready': False, 'reachable': True}), \
                contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(setup_main(['--install-dir', str(self.root), '--orbes-dir', str(home)]), 1)
        self.assertIn('stop it before reinstalling', error.getvalue())
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()

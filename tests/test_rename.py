"""Renaming preserves existing identities; all homes and databases are disposable."""
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
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from orbehelm.adapters import launch, orbe_identity
from orbehelm.cli import main
from orbehelm.compatibility import LEGACY_MARKER, database_file
from orbehelm.configuration import load
from orbehelm.composition import SECTION_TITLES
from orbehelm.core import OrbeHelmError, build, resolve
from orbehelm.product.commands import initialize
from orbehelm.product.database import Store, engine_for, migrate
from orbehelm.product.orbes import orbe_details
from orbehelm.product.projects import register_project, resolve_project, add_project_dependency

REPO = Path(__file__).resolve().parents[1]


class RenameTests(unittest.TestCase):
    def setUp(self):
        # These tests isolate launch behavior; service readiness has dedicated coverage.
        for target in ('orbehelm.adapters.require_server', 'orbehelm.cli.require_server',
                       'orbehelm.delegation_runner.require_server'):
            readiness = patch(target)
            readiness.start()
            self.addCleanup(readiness.stop)
        self.tmp = tempfile.TemporaryDirectory(dir=REPO / 'tests')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ('definitions', 'registry', 'examples'):
            shutil.copytree(REPO / name, self.root / name)
        self.home, self.project = self.root / 'home', self.root / 'work'
        self.home.mkdir()
        self.project.mkdir()
        environment = patch.dict(os.environ, {'HOME': str(self.home), 'ORBEHELM_CONFIG': '',
            'ORBEHELM_ROOT': '', 'AGENTIC_CONFIG': '', 'AGENTIC_ROOT': ''})
        environment.start()
        self.addCleanup(environment.stop)

    def test_checkout_command_has_new_help_and_read_only_dry_runs(self):
        help_result = subprocess.run([sys.executable, str(REPO / 'oh'), '--help'],
            env=dict(os.environ), capture_output=True, text=True, check=True)
        self.assertIn('usage: oh ', help_result.stdout)
        self.assertIn('OrbeHelm', help_result.stdout)
        self.assertIn('--new-orbe', help_result.stdout)
        self.assertNotIn('agentic', help_result.stdout.lower())
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for agent in ('codex', 'claude', 'opencode'):
            result = subprocess.run([sys.executable, str(REPO / 'oh'), '--root', str(self.root),
                '--project', str(self.project), '--agent', agent, '--new-orbe', '--dry-run'],
                env=dict(os.environ), capture_output=True, text=True, check=True)
            self.assertIn(agent, result.stdout)
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes()
            for p in self.root.rglob('*') if p.is_file()})

    def test_old_runtime_resume_keeps_ids_homes_counts_and_original_records(self):
        resolved = resolve(self.root, project=self.project)
        for agent in ('codex', 'claude', 'opencode'):
            with self.subTest(agent=agent):
                output, _ = build(self.root, resolved, agent)
                _, key = orbe_identity(resolved, agent)
                orbe_id = uuid.uuid4().hex
                runtime = self.root / 'state/sessions' / orbe_id
                runtime.mkdir(parents=True)
                record = runtime / 'session.json'
                record.write_text(json.dumps({'schema_version': 1, 'session_id': orbe_id,
                    'launch_count': 4, 'resumable': True, 'agent': agent, 'cwd': str(self.project)}))
                original = record.read_bytes()
                if agent != 'opencode':
                    relative = 'codex-home/sessions/old.jsonl' if agent == 'codex' else 'claude-home/projects/old.jsonl'
                    transcript = runtime / relative
                    transcript.parent.mkdir(parents=True)
                    transcript.write_text('fake native history')
                pointer = self.root / 'state/session-keys' / key / 'active.json'
                pointer.parent.mkdir(parents=True)
                pointer.write_text(json.dumps({'session_id': orbe_id}))
                before = {p: p.read_bytes() for p in runtime.rglob('*') if p.is_file()}
                preview = launch(self.root, output, resolved, agent, dry_run=True)
                self.assertIn('resume' if agent == 'codex' else '--continue', preview)
                self.assertEqual(before, {p: p.read_bytes() for p in runtime.rglob('*') if p.is_file()})
                with patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                        patch('orbehelm.adapters.subprocess.call', return_value=0) as child:
                    launch(self.root, output, resolved, agent)
                self.assertEqual(child.call_args.kwargs['env']['ORBEHELM_ORBE_ID'], orbe_id)
                self.assertEqual(child.call_args.kwargs['env']['ORBEHELM_ORBE_DIR'], str(runtime.resolve()))
                self.assertEqual(json.loads((runtime / 'orbe.json').read_text())['launch_count'], 5)
                self.assertEqual(json.loads(pointer.read_text()), {'orbe_id': orbe_id})
                self.assertEqual(record.read_bytes(), original)
                self.assertFalse((self.root / 'state/orbe-keys' / key).exists())
                self.assertFalse((self.root / 'state/orbes' / orbe_id).exists())
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['status', '--root', str(self.root)]), 0)
        rows = json.loads(output.getvalue())['orbes']
        self.assertEqual(len(rows), 3)
        self.assertTrue(all('orbe_id' in row and 'session_id' not in row for row in rows))

    def test_old_configuration_and_snapshots_remain_readable(self):
        (self.home / '.agenticrc').write_text('[AGENTIC]\nprofile=reviewer\n')
        self.assertEqual(load()[0]['profile'], 'reviewer')
        (self.home / '.orbehelmrc').write_text('[ORBEHELM]\nprofile=developer\n')
        with self.assertRaisesRegex(OrbeHelmError, 'Both'):
            load()
        self.assertEqual(load(self.home / '.orbehelmrc')[0]['profile'], 'developer')
        project_file = self.project / 'agentic.project.json'
        project_file.write_text(json.dumps({'schema_version': 1, 'instructions': ['local.md']}))
        (self.project / 'local.md').write_text(LEGACY_MARKER + '\n# Project\n\n' + '\n\n'.join(
            '## ' + title + ('\nLegacy context.' if index == 0 else '')
            for index, title in enumerate(SECTION_TITLES)) + '\n')
        original = (self.project / 'local.md').read_bytes()
        initialize(self.root)
        store = Store(self.root)
        self.addCleanup(store.close)
        project = register_project(store, self.project)
        resolved = resolve_project(store, project)
        output, _ = build(self.root, resolved)
        self.assertIn('Legacy context.', (output / 'instructions.md').read_text())
        project_file = project_file.rename(self.project / 'orbehelm.project.json')
        add_project_dependency(store, project, 'skills', 'testing', project.active_revision)
        self.assertIn('testing', json.loads(project_file.read_text())['skills'])
        self.assertEqual((self.project / 'local.md').read_bytes(), original)
        self.assertFalse((self.project / 'agentic.project.json').exists())
        self.assertTrue(resolve_project(store, project)['skills'])

    def test_populated_old_database_upgrades_without_losing_relationships(self):
        state = self.root / 'state'
        state.mkdir()
        old_database = state / 'agentic.sqlite3'
        old_database.touch()
        engine = engine_for(self.root)
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            config = Config()
            config.set_main_option('script_location', str(REPO / 'src/orbehelm/product/migrations'))
            config.attributes['connection'] = connection
            command.upgrade(config, '0002')
            statements = [
                "INSERT INTO projects VALUES ('p','/project','Old',NULL,'now')",
                "INSERT INTO session_slots VALUES ('slot','p','codex','developer','',NULL,'APP-1')",
                "INSERT INTO sessions VALUES ('native','p','slot','state/sessions/native','now',0)",
                "UPDATE session_slots SET active_session='native' WHERE key='slot'",
                "INSERT INTO session_launches VALUES ('launch','native',NULL,NULL,'build',NULL,'now',NULL,'exited',0,123)",
                "INSERT INTO tasks VALUES ('task','p','APP-1','/project','parent','reviewing',1,NULL,1,3,'now')",
                "INSERT INTO logical_sessions VALUES ('parent','task','developer','','APP-1',NULL,'now')",
                "INSERT INTO logical_sessions VALUES ('child','task','reviewer','','APP-1/child','parent','now')",
                "INSERT INTO task_artifacts VALUES ('artifact','task','parent','candidate','hash','state/artifact','now')",
                "INSERT INTO knowledge VALUES ('knowledge','p','task','parent','key','task',1,'accepted','artifact')",
                "INSERT INTO delegations VALUES ('d','task','parent','child','artifact','artifact','reviewer','k','Review','completed','artifact',NULL,NULL,'now','now')",
                "INSERT INTO task_events VALUES ('event','task',1,'parent','submitted','{\"logical_session_id\":\"parent\"}','now')",
            ]
            for statement in statements:
                connection.execute(text(statement))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['status', '--root', str(self.root)]), 2)
        self.assertEqual(Path(migrate(self.root)), old_database.resolve())
        self.assertFalse((state / 'orbehelm.sqlite3').exists())
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text('SELECT active_orbe FROM orbe_slots')).scalar(), 'native')
            self.assertEqual(connection.execute(text('SELECT orbe_id FROM orbe_launches')).scalar(), 'native')
            self.assertEqual(connection.execute(text("SELECT parent_id,orbe_key FROM logical_orbes WHERE id='child'")).one(), ('parent', 'APP-1/child'))
            self.assertEqual(connection.execute(text('SELECT runtime_path FROM orbes')).scalar(), 'state/sessions/native')
            self.assertEqual(connection.execute(text('SELECT parent_id,child_id,result_id FROM delegations')).one(), ('parent', 'child', 'artifact'))
            self.assertEqual(connection.execute(text('SELECT payload FROM task_events')).scalar(), '{"logical_session_id":"parent"}')
            self.assertIsNone(connection.exec_driver_sql('PRAGMA foreign_key_check').first())
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_keys').scalar(), 1)
            self.assertFalse({'sessions', 'session_slots', 'session_launches', 'logical_sessions'} & set(inspect(connection).get_table_names()))
        self.assertEqual(len(list((state / 'backups').glob('*.sqlite3'))), 1)

    def test_old_orbes_import_once_and_ambiguous_databases_are_rejected(self):
        orbe_id = uuid.uuid4().hex
        runtime = self.root / 'state/sessions' / orbe_id
        runtime.mkdir(parents=True)
        record = runtime / 'session.json'
        record.write_text(json.dumps({'session_id': orbe_id, 'cwd': str(self.project),
            'agent': 'codex', 'profile': 'developer', 'status': 'exited'}))
        original = record.read_bytes()
        _, key = orbe_identity({'project': str(self.project), 'profile': 'developer', 'spec': None}, 'codex')
        pointer = self.root / 'state/session-keys' / key / 'active.json'
        pointer.parent.mkdir(parents=True)
        pointer.write_text(json.dumps({'session_id': orbe_id}))
        self.assertEqual(initialize(self.root)['imported'], 1)
        self.assertEqual(initialize(self.root)['imported'], 0)
        store = Store(self.root)
        self.addCleanup(store.close)
        row = orbe_details(store)[0]
        self.assertEqual(row['id'], orbe_id)
        self.assertTrue(row['active'])
        self.assertEqual(record.read_bytes(), original)
        (self.root / 'state/agentic.sqlite3').touch()
        with self.assertRaisesRegex(OrbeHelmError, 'Both'):
            database_file(self.root)

"""Product integration tests use disposable databases and fake child processes only.

Install the project and dev dependencies in .venv before running this module.
Missing dependencies are errors, not skipped checks.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from orbehelm.core import OrbeHelmError, digest, build_directory
from orbehelm.cli import main
from orbehelm.application import execute
from orbehelm.adapters import launch
from orbehelm.composition import MARKER, SECTION_TITLES
from orbehelm.product.database import Store, migrate, engine_for
from orbehelm.product.catalog import (Conflict, reconcile_catalog, latest, edit_definition, recover_publication)
from orbehelm.product.models import (Project, CatalogRelease, OrbeLaunch, Orbe, ProjectConfiguration,
                                    OrbeSlot, Base, ReleaseMember, DefinitionRevision, SelectionLock,
                                    ConfigurationBuild)
from orbehelm.product.projects import (register_project, get_project, resolve_project, build_project,
    adopt_configuration, preview_adoption, rollback_configuration, save_override, configuration_for)
from orbehelm.product.orbes import import_legacy, orbe_details
from orbehelm.product.web import create_app, validate_bind
from orbehelm.product.capabilities import inventory, check_capabilities, check_skill
from orbehelm.product.projects import selection_key
from orbehelm.product.projects import add_project_dependency, recover_context_edit
from orbehelm.product.library import add_skill, add_mcp

REPO = Path(__file__).resolve().parents[1]


def section_override(section, content):
    return MARKER + '\n# Local override\n\n' + '\n\n'.join(
        f'## {name} [override]\n{content}' if name == section else f'## {name}' for name in SECTION_TITLES) + '\n'


class ProductTests(unittest.TestCase):
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
        self.home = self.root / 'home'
        self.home.mkdir()
        environment = patch.dict(os.environ, {'HOME': str(self.home), 'ORBEHELM_CONFIG': '', 'ORBEHELM_ROOT': ''})
        environment.start()
        self.addCleanup(environment.stop)
        self.work = self.root / 'work'
        self.work.mkdir()
        migrate(self.root)
        self.store = Store(self.root)
        self.addCleanup(self.store.close)
        self.release = reconcile_catalog(self.store)
        self.project = register_project(self.store, self.work)

    def result(self, project=None, **kwargs):
        return resolve_project(self.store, project or get_project(self.store, self.project.id), **kwargs)

    def edit(self, relative, extra='\nAdditional instruction.\n'):
        path = self.root / relative
        path.write_text(path.read_text() + extra)
        return reconcile_catalog(self.store)

    def test_finder_metadata_is_not_a_definition(self):
        path = self.root / 'definitions/.DS_Store'
        path.write_bytes(b'Finder metadata')
        self.assertEqual(reconcile_catalog(self.store).id, self.release.id)

    def test_library_creation_is_validated_published_and_project_pins_are_unchanged(self):
        release = add_skill(self.store, {'name': 'extra-testing', 'source': 'examples/skills/testing',
                                        'expected_release': self.release.id})
        self.assertTrue((self.root / 'registry/skills/extra-testing.json').is_file())
        self.assertEqual(configuration_for(self.store, self.project).release_id, release.id)
        with self.assertRaises(Conflict):
            add_skill(self.store, {'name': 'extra-testing', 'source': 'examples/skills/testing',
                                   'expected_release': release.id})
        for source in ['../outside', 'state/auth/codex', 'http://example.test/SKILL.md']:
            with self.assertRaises(OrbeHelmError):
                add_skill(self.store, {'name': 'bad-source', 'source': source, 'expected_release': release.id})
        server_release = add_mcp(self.store, {'name': 'remote-docs', 'transport': 'http',
            'url': 'https://example.test/mcp', 'expected_release': release.id})
        self.assertNotEqual(server_release.id, release.id)
        with self.assertRaises(OrbeHelmError):
            add_mcp(self.store, {'name': 'unsafe', 'transport': 'http',
                'url': 'https://user:secret@example.test/mcp', 'expected_release': server_release.id})
        self.assertFalse((self.root / 'registry/mcp/unsafe.json').exists())
        self.assertEqual(latest(self.store).id, server_release.id)

    def test_new_registration_recovers_after_publication_before_source_write(self):
        from orbehelm.product.catalog import recover_publication
        with patch('orbehelm.product.catalog.recover_publication', side_effect=[None, RuntimeError('interrupted')]):
            with self.assertRaises(RuntimeError):
                add_mcp(self.store, {'name': 'recoverable', 'transport': 'http',
                    'url': 'https://example.test/mcp', 'expected_release': self.release.id})
        target = self.root / 'registry/mcp/recoverable.json'
        self.assertFalse(target.exists())
        recover_publication(self.store)
        self.assertEqual(json.loads(target.read_text())['url'], 'https://example.test/mcp')
        self.assertEqual(reconcile_catalog(self.store).id, latest(self.store).id)

    def test_project_dependencies_preserve_release_and_roll_back_failed_preparation(self):
        config = configuration_for(self.store, self.project)
        with patch('orbehelm.product.projects.freeze_skills', side_effect=OrbeHelmError('failed preparation')):
            with self.assertRaises(OrbeHelmError):
                add_project_dependency(self.store, self.project, 'skills', 'testing', config.id)
        self.assertFalse((self.work / 'orbehelm.project.json').exists())
        self.assertEqual(configuration_for(self.store, self.project).id, config.id)
        new = add_project_dependency(self.store, self.project, 'skills', 'testing', config.id)
        self.assertEqual(new.release_id, config.release_id)
        self.assertEqual(json.loads((self.work / 'orbehelm.project.json').read_text())['skills'], ['testing'])
        self.assertEqual(self.result()['skills'][0]['name'], 'testing')
        self.assertEqual(add_project_dependency(self.store, self.project, 'skills', 'testing', new.id).id, new.id)
        (self.work / 'orbehelm.project.json').write_text('{"schema_version":1,"skills":[]}')
        with self.assertRaises(Conflict):
            add_project_dependency(self.store, self.project, 'mcp', 'docs', new.id)
        self.assertEqual(configuration_for(self.store, self.project).id, new.id)

    def test_dependency_assignment_is_portable_and_survives_catalog_adoption(self):
        config = configuration_for(self.store, self.project)
        added = add_project_dependency(self.store, self.project, 'skills', 'testing', config.id)
        with self.store.read() as db:
            self.assertEqual(len(db.scalars(select(ConfigurationBuild)).all()), 0)
            self.assertEqual(len(db.scalars(select(SelectionLock)).all()), 1)
        release = self.edit('definitions/profiles/reviewer.md')
        adopted = configuration_for(self.store, self.project)
        self.result(persist=True)
        data = inventory(self.store, self.project, adopted)
        self.assertEqual(data['skills'][0]['name'], 'testing')
        self.assertIsNone(data['runtime'])

    def test_interrupted_dependency_assignment_restores_source_without_overwriting_external_edits(self):
        config = configuration_for(self.store, self.project)
        with patch('orbehelm.product.projects._adopt_configuration', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                add_project_dependency(self.store, self.project, 'skills', 'testing', config.id)
        manifest = self.work / 'orbehelm.project.json'
        self.assertTrue(manifest.exists())
        recover_context_edit(self.store, self.project)
        self.assertFalse(manifest.exists())
        with patch('orbehelm.product.projects._adopt_configuration', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                add_project_dependency(self.store, self.project, 'skills', 'testing', config.id)
        external = '{"schema_version":1,"skills":["review"]}'
        manifest.write_text(external)
        with self.assertRaises(Conflict):
            recover_context_edit(self.store, self.project)
        self.assertEqual(manifest.read_text(), external)
        self.assertEqual(configuration_for(self.store, self.project).id, config.id)

    def test_shared_library_forms_and_cli_project_enabling(self):
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        with TestClient(app, base_url='http://localhost:8765') as client:
            self.assertEqual(client.get('/projects/' + self.project.id).status_code, 404)
            self.assertEqual(client.get('/skills').status_code, 200)
            token = client.cookies['orbehelm_csrf']
            self.assertEqual(client.post('/skills/new', data={'name': 'missing-csrf'}).status_code, 403)
            invalid = client.post('/skills/new', data={'csrf': token, 'name': 'new-item',
                'source': '../outside', 'expected_release': self.release.id})
            self.assertEqual(invalid.status_code, 400)
            self.assertIn('value="new-item"', invalid.text)
            response = client.post('/skills/new', data={'csrf': token, 'name': 'new-item',
                'source': 'examples/skills/testing', 'expected_release': self.release.id})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(configuration_for(self.store, self.project).release_id, latest(self.store).id)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['projects', 'add-skill', 'new-item', '--root', str(self.root), '--project', str(self.work)]), 0)
        self.assertIn('new-item', [item['name'] for item in self.result()['skills']])

    def test_editor_rejects_project_management_and_retains_shared_navigation(self):
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        with TestClient(app, base_url='http://localhost:8765') as client:
            for kind in ('skills', 'mcp'):
                self.assertEqual(client.get(f'/projects/{self.project.id}/{kind}/new').status_code, 404)
                self.assertEqual(client.get(f'/{kind}/new', params={'project': self.project.id}).status_code, 400)
                shared = client.get(f'/{kind}/new')
                self.assertEqual(shared.status_code, 200)
                self.assertNotIn('href="/projects', shared.text)
            token = client.cookies['orbehelm_csrf']
            self.assertEqual(client.post('/projects/register', data={'csrf': token, 'path': str(self.work)}).status_code, 404)

    def test_library_update_preserves_project_requirements_and_overrides_but_updates_definitions(self):
        config = configuration_for(self.store, self.project)
        config = add_project_dependency(self.store, self.project, 'skills', 'testing', config.id)
        config = add_project_dependency(self.store, self.project, 'mcp', 'docs', config.id)
        config = save_override(self.store, self.project, 'developer',
                               section_override('Responsibilities', 'Keep this project instruction.'), config.id)
        before = self.result()
        definition = self.root / 'registry/mcp/docs.json'
        data = json.loads(definition.read_text())
        data['url'] = 'https://example.test/new-docs'
        definition.write_text(json.dumps(data))
        release = self.edit('examples/skills/testing/SKILL.md', '\nNew shared skill instructions.\n')
        adopted = configuration_for(self.store, self.project)
        after = self.result()
        self.assertEqual(adopted.context_snapshot, config.context_snapshot)
        self.assertEqual(adopted.overrides, config.overrides)
        self.assertIn('Keep this project instruction.', after['composed_instructions'])
        self.assertEqual([item['name'] for item in after['skills']], [item['name'] for item in before['skills']])
        self.assertNotEqual(after['skills'][0]['sha256'], before['skills'][0]['sha256'])
        self.assertEqual(after['mcp']['docs']['url'], 'https://example.test/new-docs')

    def test_new_shared_items_are_available_without_per_project_adoption(self):
        release = add_skill(self.store, {'name': 'new-skill', 'source': 'examples/skills/testing',
                                        'expected_release': self.release.id})
        release = add_mcp(self.store, {'name': 'new-server', 'transport': 'http',
            'url': 'https://example.test/mcp', 'expected_release': release.id})
        config = configuration_for(self.store, self.project)
        self.assertEqual(config.release_id, release.id)
        config = add_project_dependency(self.store, self.project, 'skills', 'new-skill', config.id)
        add_project_dependency(self.store, self.project, 'mcp', 'new-server', config.id)
        result = self.result()
        self.assertIn('new-skill', [item['name'] for item in result['skills']])
        self.assertIn('new-server', result['mcp'])

    def test_cli_mcp_login_is_explicit_and_never_starts_a_model(self):
        config = configuration_for(self.store, self.project)
        add_project_dependency(self.store, self.project, 'mcp', 'docs', config.id)
        result = self.result(persist=True)
        output, _ = build_project(self.store, result, 'codex')
        with patch('orbehelm.adapters.doctor', return_value={'ok': True}), patch('orbehelm.adapters.subprocess.call', return_value=0):
            launch(self.root, output, result, 'codex')
        with patch('orbehelm.product.authentication.unavailable', return_value=None), patch('orbehelm.product.authentication.login_command', return_value=(['fake', 'mcp', 'login'], {})), patch('subprocess.call', return_value=0) as child, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['projects', 'login-mcp', 'docs', '--root', str(self.root), '--project', str(self.work)]), 0)
        self.assertEqual(child.call_args.args[0], ['fake', 'mcp', 'login'])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['projects', 'login-mcp', 'not-enabled', '--root', str(self.root), '--project', str(self.work)]), 2)

    def test_capabilities_reuse_shared_selection_across_agents(self):
        result = self.result(skills=['testing'], persist=True)
        codex, _ = build_project(self.store, result, 'codex')
        claude, _ = build_project(self.store, self.result(skills=['testing'], persist=True), 'claude')
        self.assertNotEqual(codex, claude)
        self.assertEqual(json.loads((codex / 'resolved.json').read_text())['fingerprint'],
                         json.loads((claude / 'resolved.json').read_text())['fingerprint'])
        with self.store.read() as db:
            self.assertEqual(len(db.scalars(select(SelectionLock)).all()), 1)
        config = configuration_for(self.store, self.project)
        data = inventory(self.store, self.project, config)
        self.assertEqual(data['skills'][0]['name'], 'testing')
        self.assertIn('Testing Workflow', data['skills'][0]['content'])
        before = self.result(skills=['testing'])['fingerprint']
        report = check_capabilities(self.store, self.project, config, data['selection'], 'codex')
        self.assertEqual(report['skills']['testing']['status'], 'Up to date')
        self.edit('examples/skills/testing/SKILL.md', '\nNew published content.\n')
        report = check_capabilities(self.store, self.project, config, data['selection'], 'codex')
        self.assertEqual(report['skills']['testing']['status'], 'Update available')
        self.assertNotEqual(self.result(skills=['testing'])['fingerprint'], before)
        self.assertEqual(inventory(self.store, self.project, config)['report'], report)
        other_agent = inventory(self.store, self.project, config, agent='claude')['report']
        self.assertEqual(other_agent['skills'], report['skills'])
        self.assertEqual(other_agent['mcp'], {})
        self.assertIsNone(other_agent['checked_at'])

    def test_remote_skill_checks_bypass_cache_and_preserve_pins(self):
        skill = {'name': 'remote', 'source': 'https://example.test/SKILL.md#sha256=' + 'a' * 64,
                 'sha256': 'a' * 64}
        config = configuration_for(self.store, self.project)
        with patch('orbehelm.product.capabilities.download.__wrapped__', return_value=(
                {'SKILL.md': {'content': b'---\nname: remote\ndescription: Remote\nversion: 2\n---\n'}}, {}, 'b' * 64)) as fetch:
            report = check_skill(self.store, config, skill)
        fetch.assert_called_once_with('https://example.test/SKILL.md')
        self.assertEqual(report['status'], 'Update available')
        self.assertEqual(report['version'], '2')
        self.assertEqual(skill['sha256'], 'a' * 64)
        with patch('orbehelm.product.capabilities.download.__wrapped__', side_effect=OrbeHelmError('private failure')):
            report = check_skill(self.store, config, skill)
        self.assertEqual(report['status'], 'Unknown')
        self.assertNotIn('private', str(report))

    def test_cli_capability_checks_are_explicit_and_selection_scoped(self):
        (self.work / 'orbehelm.project.json').write_text(json.dumps({'schema_version': 1, 'skills': ['testing'], 'mcp': ['docs']}))
        config = configuration_for(self.store, self.project)
        adopt_configuration(self.store, self.project, config.release_id, config.id, refresh_context=True)
        self.result(persist=True)
        args = ['projects', 'capabilities', '--root', str(self.root), '--project', str(self.work), '--agent=claude']
        with patch('orbehelm.product.capabilities.mcp_authentication') as probe, patch('orbehelm.product.capabilities.check_skill') as updates, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(args), 0)
            self.assertIn('Testing Workflow', output.getvalue())
            probe.assert_not_called()
            updates.assert_not_called()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['projects', 'check-capabilities', *args[2:]]), 0)
            self.assertIn('Up to date', output.getvalue())
            self.assertIn('claude does not yet have', output.getvalue())
        config = configuration_for(self.store, self.project)
        with self.assertRaises(OrbeHelmError):
            check_capabilities(self.store, self.project, config, selection_key(skills=['unknown']), 'claude')

    def test_authentication_uses_matching_native_runtime_only(self):
        (self.work / 'orbehelm.project.json').write_text(json.dumps(
            {'schema_version': 1, 'mcp': ['docs']}))
        config = configuration_for(self.store, self.project)
        adopt_configuration(self.store, self.project, config.release_id, config.id, refresh_context=True)
        result = self.result(persist=True)
        output, _ = build_project(self.store, result, 'codex')
        with patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                patch('orbehelm.adapters.subprocess.call', return_value=0):
            launch(self.root, output, result, 'codex')
        config = configuration_for(self.store, self.project)
        data = inventory(self.store, self.project, config, agent='codex')
        self.assertIsNotNone(data['runtime'])
        with patch('orbehelm.product.capabilities.mcp_authentication', return_value={}) as probe:
            check_capabilities(self.store, self.project, config, data['selection'], 'codex')
        self.assertEqual(probe.call_args.args[1], data['runtime'])
        self.assertIsNone(inventory(self.store, self.project, config, agent='claude')['runtime'])

    def test_shared_resource_editor_escapes_skill_content_and_corrupt_reports_remain_unknown(self):
        self.edit('examples/skills/testing/SKILL.md', '\n<script>unsafe()</script>\n')
        self.result(skills=['testing'], persist=True)
        config = configuration_for(self.store, self.project)
        data = inventory(self.store, self.project, config)
        directory = self.root / 'state/projects' / self.project.id / 'capabilities'
        directory.mkdir(parents=True)
        (directory / (data['report_key'] + '.json')).write_text('[]')
        self.assertIsNone(inventory(self.store, self.project, config)['report'])
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        with TestClient(app, base_url='http://localhost:8765') as client:
            response = client.get('/definitions', params={'path': 'examples/skills/testing/SKILL.md'})
            self.assertEqual(response.status_code, 200)
            self.assertIn('&lt;script&gt;unsafe()', response.text)
            self.assertNotIn('<script>unsafe()', response.text)

    def test_migrations_are_repeatable_match_models_and_preserve_data(self):
        migrate(self.root)
        self.assertEqual(get_project(self.store, self.project.id).path, str(self.work))
        engine = engine_for(self.root)
        try:
            config = Config()
            config.set_main_option('script_location', str(REPO / 'src/orbehelm/product/migrations'))
            with engine.begin() as connection:
                config.attributes['connection'] = connection
                command.check(config)
                with self.assertRaises(IntegrityError):
                    connection.execute(text('INSERT INTO release_members (release_id,path,revision_id) VALUES (:r,:p,:d)'),
                                       {'r': 'missing', 'p': 'missing', 'd': 'missing'})
        finally:
            engine.dispose()
        self.assertTrue(list((self.root / 'state/backups').glob('*.sqlite3')))

    def test_global_changes_follow_automatically_and_reuse_unaffected_builds(self):
        python = self.result(spec='python', persist=True)
        php = self.result(spec='php', persist=True)
        python_path, _ = build_project(self.store, python, 'codex')
        php_path, _ = build_project(self.store, php, 'codex')
        other_dir = self.root / 'other'
        other_dir.mkdir()
        other = register_project(self.store, other_dir)
        release = self.edit('definitions/specializations/developer/python.md')
        self.assertNotEqual(self.result(spec='python')['fingerprint'], python['fingerprint'])
        self.assertEqual(build_directory(self.root, self.result(spec='php')), php_path)
        self.assertTrue(python_path.is_dir())
        self.assertEqual(configuration_for(self.store, other).release_id, release.id)
        historical = configuration_for(self.store, self.project, python['configuration_id'])
        from orbehelm.product.projects import resolve_configuration
        self.assertEqual(resolve_configuration(self.store, self.project, historical, spec='python')['fingerprint'], python['fingerprint'])

    def test_base_change_reaches_every_dependent_profile(self):
        before = {name: self.result(profile=name)['fingerprint'] for name in ('developer', 'reviewer')}
        self.edit('definitions/base/instructions.md')
        self.assertTrue(all(self.result(profile=name)['fingerprint'] != value for name, value in before.items()))

    def test_failed_build_does_not_undo_shared_publication_and_stale_writes_fail(self):
        self.result(spec='python', persist=True)
        release = self.edit('definitions/specializations/developer/python.md')
        current = configuration_for(self.store, self.project)
        with patch('orbehelm.core.build', side_effect=OrbeHelmError('test failure')):
            with self.assertRaisesRegex(OrbeHelmError, 'test failure'):
                build_project(self.store, self.result(spec='python'), 'codex')
        self.assertEqual(configuration_for(self.store, self.project).id, current.id)
        self.assertEqual(current.release_id, release.id)
        with self.assertRaises(Conflict):
            adopt_configuration(self.store, self.project, release.id, 'stale')

    def test_legacy_section_overrides_survive_automatic_shared_updates(self):
        save_override(self.store, self.project, 'developer', section_override('Communication', 'Local communication rule'), self.project.active_revision)
        path = self.root / 'definitions/profiles/developer.md'
        path.write_text(path.read_text().replace('## Responsibilities [append]', '## Responsibilities [append]\n\nNew responsibility.'))
        reconcile_catalog(self.store)
        text = self.result()['composed_instructions']
        self.assertIn('Local communication rule', text)
        self.assertIn('New responsibility.', text)
        path.write_text(path.read_text().replace('## Communication [append]', '## Communication [append]\n\nChanged communication.'))
        reconcile_catalog(self.store)
        text = self.result()['composed_instructions']
        self.assertIn('Local communication rule', text)
        self.assertNotIn('Changed communication.', text)

    def test_concurrent_definition_edits_allow_one_publication_and_report_conflict(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        relative = 'definitions/specializations/developer/python.md'
        before = (self.root / relative).read_text()
        barrier = Barrier(2)
        def edit(index):
            barrier.wait(timeout=5)
            try:
                return edit_definition(self.store, relative, before + f'\nConcurrent edit {index}.\n',
                                       self.release.id, digest(before.encode())).id
            except Conflict:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(edit, (1, 2)))
        self.assertEqual(outcomes.count('conflict'), 1)
        with self.store.read() as db:
            releases = db.scalars(select(CatalogRelease)).all()
        self.assertEqual(len(releases), 2)
        self.assertEqual(reconcile_catalog(self.store).id, latest(self.store).id)

    def test_source_edit_validation_conflict_and_publication_recovery(self):
        relative = 'definitions/specializations/developer/python.md'
        path = self.root / relative
        before = path.read_bytes()
        with self.assertRaises(OrbeHelmError):
            edit_definition(self.store, relative, 'invalid section template', self.release.id, digest(before))
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(latest(self.store).id, self.release.id)
        with self.assertRaises(Conflict):
            edit_definition(self.store, relative, before.decode(), 'stale', digest(before))
        with patch('orbehelm.product.catalog.recover_publication', side_effect=[None, OSError('interrupted')]):
            with self.assertRaises(OSError):
                edit_definition(self.store, relative, before.decode() + '\nNext instruction.\n', self.release.id, digest(before))
        self.assertEqual(path.read_bytes(), before)
        recover_publication(self.store)
        self.assertIn('Next instruction.', path.read_text())
        self.assertEqual(reconcile_catalog(self.store).id, latest(self.store).id)

    def test_context_is_pinned_until_explicit_refresh(self):
        config = self.work / 'orbehelm.project.json'
        config.write_text(json.dumps({'schema_version': 1, 'instructions': ['notes.md']}))
        (self.work / 'notes.md').write_text('Project context revision one')
        self.assertNotIn('Project context revision one', self.result()['composed_instructions'])
        revised = adopt_configuration(self.store, self.project, self.release.id,
                                     self.project.active_revision, refresh_context=True)
        self.assertIn('Project context revision one', self.result()['composed_instructions'])
        (self.work / 'notes.md').write_text('Project context revision two')
        self.assertIn('Project context revision one', self.result()['composed_instructions'])

    def test_launch_history_and_fresh_session_preserve_idempotency(self):
        result = self.result(spec='python', persist=True)
        output, _ = build_project(self.store, result, 'codex')
        with patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                patch('orbehelm.adapters.subprocess.call', return_value=0):
            launch(self.root, output, result, 'codex')
            launch(self.root, output, result, 'codex')
            first = orbe_details(self.store)[0]
            self.assertEqual(len(first['launches']), 2)
            self.assertFalse(first['running'])
            launch(self.root, output, result, 'codex', new_orbe=True)
        rows = orbe_details(self.store)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row['active'] for row in rows), 1)
        self.assertEqual(sum(len(row['launches']) for row in rows), 3)
        self.assertTrue(all(item['configuration_id'] == result['configuration_id'] for row in rows for item in row['launches']))

    def test_import_is_repeatable_and_does_not_invent_historical_configuration(self):
        import uuid
        from orbehelm.adapters import orbe_identity
        orbe_id = uuid.uuid4().hex
        path = self.root / 'state/orbes' / orbe_id
        path.mkdir(parents=True)
        record = {'schema_version': 1, 'cwd': str(self.work), 'agent': 'codex', 'profile': 'developer',
                  'spec': 'python', 'status': 'exited', 'exit_code': 0, 'build': str(self.root / 'generated/old')}
        (path / 'orbe.json').write_text(json.dumps(record))
        _, key = orbe_identity({'project': str(self.work), 'profile': 'developer', 'spec': 'python'}, 'codex')
        pointer = self.root / 'state/orbe-keys' / key / 'active.json'
        pointer.parent.mkdir(parents=True)
        pointer.write_text(json.dumps({'orbe_id': orbe_id}))
        self.assertEqual(import_legacy(self.store)['imported'], 1)
        self.assertEqual(import_legacy(self.store)['imported'], 0)
        data = orbe_details(self.store)[0]
        self.assertEqual(data['id'], orbe_id)
        self.assertEqual(data['runtime_path'], str(path))
        self.assertIsNone(data['launches'][0]['configuration_id'])
        self.assertIsNone(data['launches'][0]['started_at'])
        self.assertTrue(data['active'])

    def test_product_dry_run_has_no_filesystem_writes(self):
        self.result(persist=True)
        before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}
        result = self.result()
        launch(self.root, build_directory(self.root, result), result, 'codex', dry_run=True)
        after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_adoption_during_launch_keeps_running_home_and_next_launch_reuses_session(self):
        result = self.result(spec='python', persist=True)
        output, _ = build_project(self.store, result, 'codex')
        release = self.edit('definitions/specializations/developer/python.md')
        def update_during_launch(*args, **kwargs):
            home = Path(kwargs['env']['CODEX_HOME'])
            before = (home / 'config.toml').read_bytes()
            self.assertEqual(configuration_for(self.store, self.project).release_id, release.id)
            self.assertEqual((home / 'config.toml').read_bytes(), before)
            return 0
        with patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                patch('orbehelm.adapters.subprocess.call', side_effect=update_during_launch):
            launch(self.root, output, result, 'codex')
        first = orbe_details(self.store)[0]
        self.assertTrue(first['pending'])
        self.assertEqual(first['launches'][0]['configuration_id'], result['configuration_id'])
        updated = self.result(spec='python', persist=True)
        updated_output, _ = build_project(self.store, updated, 'codex')
        with patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                patch('orbehelm.adapters.subprocess.call', return_value=0):
            launch(self.root, updated_output, updated, 'codex')
        second = orbe_details(self.store)[0]
        self.assertEqual(first['id'], second['id'])
        self.assertFalse(second['pending'])
        self.assertEqual(len(second['launches']), 2)

    def test_skill_cache_can_be_repaired_from_pinned_resources(self):
        result = self.result(skills=['testing'], persist=True)
        output, _ = build_project(self.store, result, 'codex')
        skill = result['skills'][0]
        cache = self.root / 'state/skills' / skill['sha256']
        shutil.rmtree(cache)
        shutil.rmtree(output)
        (self.root / 'examples/skills/testing/SKILL.md').write_text('changed working draft')
        locked = self.result(skills=['testing'], persist=True)
        rebuilt, _ = build_project(self.store, locked, 'codex')
        self.assertEqual(rebuilt, output)
        self.assertNotIn('changed working draft', (rebuilt / 'instructions.md').read_text())

    def test_cli_project_lifecycle_and_editor_history(self):
        other_path = self.root / 'second-project'
        other_path.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['projects', 'register', '--root', str(self.root), '--project', str(other_path)]), 0)
        other = get_project(self.store, str(other_path))
        release = self.edit('definitions/specializations/developer/python.md', '\nShared CLI workflow.\n')
        self.assertEqual(configuration_for(self.store, other).release_id, release.id)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['projects', 'history', '--root', str(self.root), '--project', str(other_path)]), 0)
        self.assertIn('Automatically inherited', output.getvalue())
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        with TestClient(app, base_url='http://localhost:8765') as client:
            historical = client.get('/definitions', params={'path': 'definitions/specializations/developer/python.md', 'release': self.release.id})
            self.assertIn('readonly', historical.text)
            self.assertEqual(client.get('/orbes').status_code, 404)

    def test_cli_registration_uses_selected_user_config_for_aliases(self):
        config_path = self.root / 'custom.ini'
        config_path.write_text('[SKILLS]\ncustom = examples/skills/testing\n')
        other = self.root / 'configured-project'
        other.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['projects', 'register', '--config', str(config_path), '--root', str(self.root), '--project', str(other)]), 0)
        project = get_project(self.store, str(other))
        result = resolve_project(self.store, project, skills=['custom'], persist=True)
        self.assertEqual(result['skills'][0]['name'], 'custom')

    def test_cli_invalid_profile_and_missing_context_preserve_project(self):
        current = configuration_for(self.store, self.project).id
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['get', 'definition.profile.missing-profile', '--root', str(self.root), '--project', str(self.work)]), 2)
            (self.work / 'orbehelm.project.json').write_text(json.dumps({'schema_version': 1, 'instructions': ['missing.md']}))
            self.assertEqual(main(['projects', 'refresh', '--root', str(self.root), '--project', str(self.work)]), 2)
        self.assertEqual(configuration_for(self.store, self.project).id, current)

    def test_definition_navigation_separates_categories_and_preserves_editor_context(self):
        from html.parser import HTMLParser
        from urllib.parse import parse_qs, urlsplit
        class FileLinks(HTMLParser):
            def __init__(self, html):
                super().__init__()
                self.paths = []
                self.releases = []
                self.feed(html)
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'a' and 'definition-file' in attrs.get('class', '').split():
                    query = parse_qs(urlsplit(attrs['href']).query)
                    self.paths.append(query['path'][0])
                    self.releases.append(query['release'][0])
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        prefixes = {'base': 'definitions/base/', 'profiles': 'definitions/profiles/',
                    'specializations': 'definitions/specializations/developer/',
                    'skillsets': 'definitions/skillsets/', 'skills': 'registry/skills/', 'mcp': 'registry/mcp/'}
        with TestClient(app, base_url='http://localhost:8765') as client:
            for category, prefix in prefixes.items():
                response = client.get('/definitions', params={'category': category})
                self.assertEqual(response.status_code, 200)
                links = FileLinks(response.text)
                self.assertTrue(links.paths, category)
                self.assertTrue(all(path.startswith(prefix) for path in links.paths), category)
                self.assertTrue(all(release == self.release.id for release in links.releases))
                self.assertNotIn('TEMPLATE.md', ' '.join(links.paths))
            profiles = FileLinks(client.get('/definitions?category=profiles').text).paths
            self.assertIn('definitions/profiles/developer.md', profiles)
            self.assertIn('definitions/profiles/developer.json', profiles)
            templates = FileLinks(client.get('/definitions?category=templates').text).paths
            self.assertTrue(all(path.endswith('TEMPLATE.md') for path in templates))
            resources = FileLinks(client.get('/definitions?category=resources').text).paths
            self.assertTrue(resources)
            self.assertTrue(all(path.startswith('examples/skills/') for path in resources))
            self.assertNotIn('definitions/AGENTS.md', resources)
            self.assertNotIn('definitions/CLAUDE.md', resources)
            self.assertEqual(client.get('/definitions?category=unknown').status_code, 404)
            selected_path = 'definitions/specializations/developer/python.md'
            response = client.get('/definitions', params={'path': selected_path})
            self.assertIn('Python · Instructions', response.text)
            self.assertIn('Specializations / Developer', response.text)
            token = client.cookies['orbehelm_csrf']
            content = (self.root / selected_path).read_text()
            saved = client.post('/definitions/save', data={'csrf': token, 'path': selected_path,
                'content': content + '\nKeep this editor selected.\n', 'expected_release': self.release.id,
                'expected_hash': digest(content.encode())})
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(parse_qs(saved.url.query.decode())['path'], [selected_path])
            self.assertIn('Python · Instructions', saved.text)
            self.assertTrue(all(path.startswith('definitions/specializations/developer/') for path in FileLinks(saved.text).paths))
            # Construct an empty fixture even when users have added library registrations.
            for registration in (self.root / 'registry/mcp').glob('*.json'):
                registration.unlink()
            reconcile_catalog(self.store)
            empty = client.get('/definitions?category=mcp')
            self.assertEqual(empty.status_code, 200)
            self.assertIn('No mcp servers yet', empty.text)
            historic = client.get('/definitions', params={'category': 'mcp', 'release': self.release.id})
            self.assertIn('registry/mcp/docs.json', FileLinks(historic.text).paths)
            self.assertIn('readonly', historic.text)

    def test_local_ui_forms_security_and_html_escaping(self):
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        with TestClient(app, base_url='http://localhost:8765') as client:
            response = client.get('/')
            self.assertEqual(response.status_code, 200)
            self.assertIn('Instructions &amp; profiles', response.text)
            token = client.cookies['orbehelm_csrf']
            self.assertEqual(client.post('/definitions/publish', data={'csrf': ''}).status_code, 403)
            self.assertEqual(client.post('/definitions/publish', data={'csrf': token}, headers={'Origin': 'http://attacker.example'}).status_code, 403)
            self.assertEqual(client.get('/', headers={'Host': 'attacker.example'}).status_code, 400)
            self.assertEqual(client.post('/definitions/publish', content=b'x' * (2 * 1024 * 1024 + 1), headers={'Content-Type': 'application/x-www-form-urlencoded'}).status_code, 413)
            relative = 'definitions/specializations/developer/python.md'
            content = (self.root / relative).read_text() + '\n<script>alert(1)</script>\n'
            response = client.post('/definitions/save', data={'csrf': token, 'path': relative, 'content': content,
                'expected_release': self.release.id, 'expected_hash': digest((self.root / relative).read_bytes())}, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            shown = client.get('/definitions', params={'path': relative})
            self.assertIn('&lt;script&gt;', shown.text)
            self.assertNotIn('<script>alert(1)</script>', shown.text)
            self.assertEqual(client.get('/definitions', params={'path': 'state/auth/codex/auth.json'}).status_code, 404)
            for url in ('/projects/' + self.project.id, '/orbes'):
                self.assertEqual(client.get(url).status_code, 404)
            self.assertEqual(client.get('/releases/' + latest(self.store).id).status_code, 200)
        for host in ('0.0.0.0', 'example.org', '192.168.1.1'):
            with self.assertRaises(OrbeHelmError):
                validate_bind(host, 8765)

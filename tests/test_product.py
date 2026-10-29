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
        self.assertEqual(configuration_for(self.store, self.project).release_id, self.release.id)
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
        adopted = adopt_configuration(self.store, self.project, release.id, added.id)
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

    def test_library_forms_project_navigation_and_enabling(self):
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        url = '/projects/' + self.project.id
        with TestClient(app, base_url='http://localhost:8765') as client:
            overview = client.get(url)
            self.assertIn('aria-label="Project sections"', overview.text)
            self.assertNotIn('id="override"', overview.text)
            for tab in ['overview', 'skills', 'mcp', 'instructions', 'updates', 'history', 'orbes']:
                self.assertEqual(client.get(url, params={'tab': tab}).status_code, 200)
            self.assertEqual(client.get(url, params={'tab': 'unknown'}).status_code, 404)
            token = client.cookies['orbehelm_csrf']
            self.assertEqual(client.post('/skills/new', data={'name': 'missing-csrf'}).status_code, 403)
            invalid = client.post('/skills/new', data={'csrf': token, 'name': 'new-item',
                'source': '../outside', 'expected_release': self.release.id})
            self.assertEqual(invalid.status_code, 400)
            self.assertIn('value="new-item"', invalid.text)
            response = client.post('/skills/new', data={'csrf': token, 'name': 'new-item',
                'source': 'examples/skills/testing', 'expected_release': self.release.id, 'project': self.project.id})
            self.assertEqual(response.status_code, 200)
            self.assertIn('Added to the shared library', response.text)
            self.assertEqual(configuration_for(self.store, self.project).release_id, self.release.id)
            self.assertEqual(client.get('/skills').status_code, 200)
            self.assertEqual(client.get('/mcp/new').status_code, 200)
            updated = client.post(url + '/adopt', data={'csrf': token,
                'expected': self.project.active_revision, 'release': latest(self.store).id})
            self.assertEqual(updated.status_code, 200)
            config = configuration_for(self.store, self.project)
            enabled = client.post(url + '/dependencies', data={'csrf': token,
                'expected': config.id, 'kind': 'skills', 'name': 'new-item'})
            self.assertEqual(enabled.status_code, 200)
            self.assertIn('Enabled for this project', enabled.text)
            self.assertIn('Testing Workflow', enabled.text)

    def test_project_registration_keeps_project_navigation_and_declares_shared_scope(self):
        from html.parser import HTMLParser

        class ActiveMainNavigation(HTMLParser):
            def __init__(self, html):
                super().__init__()
                self.in_main = False
                self.links = []
                self.feed(html)

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'nav':
                    self.in_main = attrs.get('aria-label') == 'Main navigation'
                if self.in_main and tag == 'a' and attrs.get('aria-current') == 'page':
                    self.links.append(attrs.get('href'))

            def handle_endtag(self, tag):
                if tag == 'nav':
                    self.in_main = False

        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        url = '/projects/' + self.project.id
        with TestClient(app, base_url='http://localhost:8765') as client:
            for kind in ['skills', 'mcp']:
                response = client.get(f'{url}/{kind}/new')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(ActiveMainNavigation(response.text).links, ['/'])
                self.assertIn('This creates a shared-library entry', response.text)
                self.assertIn('It does not enable the item', response.text)
                self.assertIn(f'{url}?tab={kind}', response.text)
                legacy = client.get(f'/{kind}/new', params={'project': self.project.id})
                self.assertEqual(legacy.url.path, f'{url}/{kind}/new')
                self.assertEqual(ActiveMainNavigation(legacy.text).links, ['/'])
                shared = client.get(f'/{kind}/new')
                self.assertEqual(ActiveMainNavigation(shared.text).links, [f'/{kind}'])
            token = client.cookies['orbehelm_csrf']
            values = {'csrf': token, 'expected_release': self.release.id,
                      'name': 'bad-local-source', 'source': '../outside'}
            invalid = client.post(f'{url}/skills/new', data=values)
            self.assertEqual(invalid.status_code, 400)
            self.assertEqual(ActiveMainNavigation(invalid.text).links, ['/'])
            values.update(name='project-created', source='examples/skills/testing')
            saved = client.post(f'{url}/skills/new', data=values)
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.url.path, url)
            self.assertIn('Added to the shared library', saved.text)
            self.assertEqual(configuration_for(self.store, self.project).release_id, self.release.id)
            values['project'] = 'different-project'
            self.assertEqual(client.post(f'{url}/skills/new', data=values).status_code, 400)

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
        adopted = adopt_configuration(self.store, self.project, release.id, config.id)
        after = self.result()
        self.assertEqual(adopted.context_snapshot, config.context_snapshot)
        self.assertEqual(adopted.overrides, config.overrides)
        self.assertIn('Keep this project instruction.', after['composed_instructions'])
        self.assertEqual([item['name'] for item in after['skills']], [item['name'] for item in before['skills']])
        self.assertNotEqual(after['skills'][0]['sha256'], before['skills'][0]['sha256'])
        self.assertEqual(after['mcp']['docs']['url'], 'https://example.test/new-docs')

    def test_project_explains_new_items_missing_from_its_pinned_library(self):
        release = add_skill(self.store, {'name': 'new-skill', 'source': 'examples/skills/testing',
                                        'expected_release': self.release.id})
        release = add_mcp(self.store, {'name': 'new-server', 'transport': 'http',
            'url': 'https://example.test/mcp', 'expected_release': release.id})
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        url = '/projects/' + self.project.id
        with TestClient(app, base_url='http://localhost:8765') as client:
            for tab, name in [('skills', 'new-skill'), ('mcp', 'new-server')]:
                response = client.get(url, params={'tab': tab})
                self.assertEqual(response.status_code, 200)
                self.assertIn(name, response.text)
                self.assertIn('New library items are available', response.text)
                self.assertIn('Review library updates', response.text)
                self.assertNotIn(f'<option>{name}</option>', response.text)
            self.assertEqual(configuration_for(self.store, self.project).release_id, self.release.id)
            adopt_configuration(self.store, self.project, release.id, self.project.active_revision)
            for tab, name in [('skills', 'new-skill'), ('mcp', 'new-server')]:
                response = client.get(url, params={'tab': tab})
                self.assertIn(f'<option>{name}</option>', response.text)
                self.assertNotIn('New library items are available', response.text)

    def test_login_routes_scope_the_action_and_never_start_a_model(self):
        config = configuration_for(self.store, self.project)
        add_project_dependency(self.store, self.project, 'mcp', 'docs', config.id)
        result = self.result(persist=True)
        output, _ = build_project(self.store, result, 'codex')
        with patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                patch('orbehelm.adapters.subprocess.call', return_value=0):
            launch(self.root, output, result, 'codex')
        config = configuration_for(self.store, self.project)
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        url = '/projects/' + self.project.id
        with TestClient(app, base_url='http://localhost:8765') as client:
            with patch.object(app.state.logins, 'start') as start:
                self.assertEqual(client.get(url, params={'tab': 'mcp'}).status_code, 200)
                start.assert_not_called()
            token = client.cookies['orbehelm_csrf']
            form = {'expected': config.id, 'selection': selection_key(), 'agent': 'codex', 'server': 'docs'}
            self.assertEqual(client.post(url + '/mcp-login', data=form).status_code, 403)
            form['csrf'] = token
            with patch('orbehelm.product.web.unavailable', return_value=None), \
                    patch('orbehelm.product.authentication.login_command', return_value=(
                        [sys.executable, '-c', 'import time; time.sleep(20)'], dict(os.environ))):
                response = client.post(url + '/mcp-login', data=form)
            self.assertEqual(response.status_code, 200)
            self.assertIn('Complete sign-in in your browser', response.text)
            job = next(iter(app.state.logins.jobs.values()))
            self.assertEqual(job.agent, 'codex')
            form['server'] = 'not-enabled'
            self.assertEqual(client.post(url + '/mcp-login', data=form).status_code, 400)
            self.assertEqual(client.post(url + f'/mcp-login/{job.id}/cancel', data={'csrf': token}).status_code, 200)

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
        self.assertEqual(self.result(skills=['testing'])['fingerprint'], before)
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

    def test_capability_view_checks_are_explicit_and_validate_selection(self):
        path = self.work / 'orbehelm.project.json'
        path.write_text(json.dumps({'schema_version': 1, 'skills': ['testing'], 'mcp': ['docs']}))
        config = configuration_for(self.store, self.project)
        adopt_configuration(self.store, self.project, config.release_id, config.id, refresh_context=True)
        self.result(persist=True)
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        url = '/projects/' + self.project.id
        with TestClient(app, base_url='http://localhost:8765') as client:
            with patch('orbehelm.product.capabilities.mcp_authentication') as probe, \
                    patch('orbehelm.product.capabilities.check_skill') as updates:
                response = client.get(url, params={'tab': 'skills'})
                self.assertEqual(response.status_code, 200)
                self.assertIn('Testing Workflow', response.text)
                self.assertIn('docs', client.get(url, params={'tab': 'mcp'}).text)
                probe.assert_not_called()
                updates.assert_not_called()
            config = configuration_for(self.store, self.project)
            form = {'expected': config.id, 'selection': selection_key(), 'agent': 'claude'}
            self.assertEqual(client.post(url + '/check-capabilities', data=form).status_code, 403)
            form['csrf'] = client.cookies['orbehelm_csrf']
            response = client.post(url + '/check-capabilities', data=form)
            self.assertEqual(response.status_code, 200)
            self.assertIn('claude does not yet have a supported',
                          client.get(url, params={'tab': 'mcp', 'agent': 'claude'}).text)
            self.assertIn('Up to date', response.text)
            form['selection'] = selection_key(skills=['unknown'])
            self.assertEqual(client.post(url + '/check-capabilities', data=form).status_code, 400)
            form['selection'], form['agent'] = selection_key(), 'unknown'
            self.assertEqual(client.post(url + '/check-capabilities', data=form).status_code, 400)
            form['agent'], form['expected'] = 'codex', 'stale'
            self.assertEqual(client.post(url + '/check-capabilities', data=form).status_code, 409)

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

    def test_skill_instructions_are_escaped_and_reports_handle_corruption(self):
        release = self.edit('examples/skills/testing/SKILL.md', '\n<script>unsafe()</script>\n')
        config = configuration_for(self.store, self.project)
        adopt_configuration(self.store, self.project, release.id, config.id)
        self.result(skills=['testing'], persist=True)
        config = configuration_for(self.store, self.project)
        data = inventory(self.store, self.project, config)
        directory = self.root / 'state/projects' / self.project.id / 'capabilities'
        directory.mkdir(parents=True)
        (directory / (data['report_key'] + '.json')).write_text('[]')
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        with TestClient(app, base_url='http://localhost:8765') as client:
            response = client.get('/projects/' + self.project.id, params={'tab': 'skills'})
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

    def test_global_change_is_pinned_and_selective_adoption_reuses_unaffected_build(self):
        python = self.result(spec='python', persist=True)
        php = self.result(spec='php', persist=True)
        python_path, _ = build_project(self.store, python, 'codex')
        php_path, _ = build_project(self.store, php, 'codex')
        original = self.project.active_revision
        other_dir = self.root / 'other'
        other_dir.mkdir()
        other = register_project(self.store, other_dir)
        release = self.edit('definitions/specializations/developer/python.md')
        self.assertEqual(self.result(spec='python')['fingerprint'], python['fingerprint'])
        preview = preview_adoption(self.store, self.project, release.id)
        impact = {item['spec']: item['changed'] for item in preview['configurations']}
        self.assertEqual(impact, {'php': False, 'python': True})
        adopted = adopt_configuration(self.store, self.project, release.id, original)
        self.assertNotEqual(self.result(spec='python')['fingerprint'], python['fingerprint'])
        self.assertEqual(build_directory(self.root, self.result(spec='php')), php_path)
        self.assertTrue(python_path.is_dir())
        self.assertEqual(configuration_for(self.store, other).release_id, self.release.id)
        rollback_configuration(self.store, self.project, original, adopted.id)
        self.assertEqual(self.result(spec='python')['fingerprint'], python['fingerprint'])

    def test_base_change_affects_all_dependent_profiles(self):
        for profile in ('developer', 'reviewer'):
            result = self.result(profile=profile, persist=True)
            build_project(self.store, result, 'codex')
        release = self.edit('definitions/base/instructions.md')
        preview = preview_adoption(self.store, self.project, release.id)
        self.assertTrue(all(item['changed'] for item in preview['configurations']))
        self.assertEqual(len(preview['configurations']), 2)

    def test_failed_build_or_stale_adoption_keeps_previous_configuration(self):
        result = self.result(spec='python', persist=True)
        build_project(self.store, result, 'codex')
        release = self.edit('definitions/specializations/developer/python.md')
        with patch('orbehelm.core.build', side_effect=OrbeHelmError('test failure')):
            with self.assertRaisesRegex(OrbeHelmError, 'test failure'):
                adopt_configuration(self.store, self.project, release.id, self.project.active_revision)
        self.assertEqual(get_project(self.store, self.project.id).active_revision, self.project.active_revision)
        with self.assertRaises(Conflict):
            adopt_configuration(self.store, self.project, release.id, 'stale')

    def test_override_is_scoped_and_conflicts_only_for_touched_sections(self):
        override = save_override(self.store, self.project, 'developer',
                                 section_override('Communication', 'Local communication rule'), self.project.active_revision)
        self.assertIn('Local communication rule', self.result()['composed_instructions'])
        path = self.root / 'definitions/profiles/developer.md'
        content = path.read_text().replace('## Responsibilities', '## Responsibilities', 1)
        content = content.replace('## Responsibilities [append]', '## Responsibilities [append]\n\nNew responsibility.')
        path.write_text(content)
        release = reconcile_catalog(self.store)
        self.assertEqual(preview_adoption(self.store, self.project, release.id)['conflicts'], [])
        adopted = adopt_configuration(self.store, self.project, release.id, override.id)
        path.write_text(path.read_text().replace('## Communication [append]', '## Communication [append]\n\nChanged communication.'))
        conflicting = reconcile_catalog(self.store)
        self.assertIn('developer', preview_adoption(self.store, self.project, conflicting.id)['conflicts'])
        with self.assertRaises(Conflict):
            adopt_configuration(self.store, self.project, conflicting.id, adopted.id)

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
            adopt_configuration(self.store, self.project, release.id, self.project.active_revision)
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

    def test_local_ui_project_lifecycle(self):
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        with TestClient(app, base_url='http://localhost:8765') as client:
            self.assertEqual(client.get('/').status_code, 200)
            token = client.cookies['orbehelm_csrf']
            other_path = self.root / 'other-ui-project'
            other_path.mkdir()
            self.assertEqual(client.post('/projects/register', data={'csrf': token, 'path': str(other_path)}).status_code, 200)
            other = get_project(self.store, str(other_path))
            result = self.result(spec='python', persist=True)
            output, _ = build_project(self.store, result, 'codex')
            with patch('orbehelm.adapters.doctor', return_value={'ok': True}), \
                    patch('orbehelm.adapters.subprocess.call', return_value=0):
                launch(self.root, output, result, 'codex')
            relative = 'definitions/specializations/developer/python.md'
            path = self.root / relative
            before = path.read_text()
            response = client.post('/definitions/save', data={'csrf': token, 'path': relative,
                'content': before + '\nUI workflow instruction.\n', 'expected_release': self.release.id,
                'expected_hash': digest(before.encode())})
            self.assertEqual(response.status_code, 200)
            release = latest(self.store)
            detail = client.get('/projects/' + self.project.id, params={'tab': 'updates'})
            self.assertEqual(detail.status_code, 200)
            self.assertIn('REBUILD', detail.text)
            response = client.post('/projects/' + self.project.id + '/adopt',
                data={'csrf': token, 'expected': self.project.active_revision, 'release': release.id})
            self.assertEqual(response.status_code, 200)
            project = get_project(self.store, self.project.id)
            self.assertNotEqual(project.active_revision, self.project.active_revision)
            self.assertEqual(configuration_for(self.store, other).release_id, self.release.id)
            response = client.post('/projects/' + project.id + '/override', data={'csrf': token,
                'expected': project.active_revision, 'profile': 'developer',
                'content': section_override('Communication', 'Local UI override')})
            self.assertEqual(response.status_code, 200)
            self.assertIn('Local UI override', self.result()['composed_instructions'])
            project = get_project(self.store, self.project.id)
            response = client.post('/projects/' + project.id + '/remove-override', data={'csrf': token,
                'expected': project.active_revision, 'profile': 'developer'})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('Local UI override', self.result()['composed_instructions'])
            project = get_project(self.store, self.project.id)
            response = client.post('/projects/' + project.id + '/rollback', data={'csrf': token,
                'expected': project.active_revision, 'revision': self.project.active_revision})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(get_project(self.store, project.id).active_revision, self.project.active_revision)
            self.assertNotIn('UI workflow instruction.', self.result(spec='python')['composed_instructions'])
            historical = client.get('/definitions', params={'path': relative, 'release': self.release.id})
            self.assertEqual(historical.status_code, 200)
            self.assertIn('readonly', historical.text)
            orbe = orbe_details(self.store)[0]
            response = client.get('/orbes/' + orbe['id'])
            self.assertEqual(response.status_code, 200)
            self.assertIn('Launch history', response.text)

    def test_ui_uses_selected_user_config_for_project_aliases(self):
        config_path = self.root / 'custom.ini'
        config_path.write_text('[SKILLS]\ncustom = examples/skills/testing\n')
        app = create_app(self.root, config_path=config_path)
        self.addCleanup(app.state.store.close)
        other = self.root / 'configured-project'
        other.mkdir()
        with TestClient(app, base_url='http://localhost:8765') as client:
            client.get('/')
            response = client.post('/projects/register', data={'csrf': client.cookies['orbehelm_csrf'], 'path': str(other)})
            self.assertEqual(response.status_code, 200)
        project = get_project(self.store, str(other))
        result = resolve_project(self.store, project, skills=['custom'], persist=True)
        self.assertEqual(result['skills'][0]['name'], 'custom')

    def test_ui_reports_invalid_profile_and_missing_context_without_changing_project(self):
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        with TestClient(app, base_url='http://localhost:8765') as client:
            client.get('/')
            token = client.cookies['orbehelm_csrf']
            response = client.post('/projects/' + self.project.id + '/override', data={'csrf': token,
                'expected': self.project.active_revision, 'profile': 'missing-profile',
                'content': section_override('Communication', 'Example')})
            self.assertEqual(response.status_code, 400)
            (self.work / 'orbehelm.project.json').write_text(json.dumps({'schema_version': 1, 'instructions': ['missing.md']}))
            response = client.post('/projects/' + self.project.id + '/refresh-context', data={'csrf': token,
                'expected': self.project.active_revision})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(get_project(self.store, self.project.id).active_revision, self.project.active_revision)

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
            self.assertIn('Your projects', response.text)
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
            for url in ('/projects/' + self.project.id, '/orbes', '/releases/' + latest(self.store).id):
                self.assertEqual(client.get(url).status_code, 200)
        for host in ('0.0.0.0', 'example.org', '192.168.1.1'):
            with self.assertRaises(OrbeHelmError):
                validate_bind(host, 8765)

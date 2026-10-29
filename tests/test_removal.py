"""Removal integration tests use disposable sources and databases, never native orbes."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from fastapi.testclient import TestClient
from orbehelm.core import OrbeHelmError
from orbehelm.product.catalog import (Conflict, latest, reconcile_catalog, remove_registration,
                                     recover_publication)
from orbehelm.product.database import Store, migrate
from orbehelm.product.dependency_usage import shared_usage, project_removal_details
from orbehelm.product.library import add_mcp, add_skill
from orbehelm.product.models import ProjectConfiguration, Orbe, OrbeSlot, OrbeLaunch, now
from orbehelm.product.projects import (register_project, configuration_for, add_project_dependency,
    remove_project_dependency, adopt_configuration, resolve_project, build_project)
from orbehelm.product.capabilities import inventory
from orbehelm.product.web import create_app
from orbehelm.snapshots import verify_snapshot

REPO = Path(__file__).resolve().parents[1]


class RemovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=REPO / 'tests')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for directory in ('definitions', 'registry', 'examples'):
            shutil.copytree(REPO / directory, self.root / directory)
        migrate(self.root)
        self.store = Store(self.root)
        self.addCleanup(self.store.close)
        self.release = reconcile_catalog(self.store)
        self.work = self.root / 'work'
        self.work.mkdir()
        self.project = register_project(self.store, self.work)

    def config(self):
        return configuration_for(self.store, self.project)

    def enable(self, kind, name):
        return add_project_dependency(self.store, self.project, kind, name, self.config().id)

    def result(self, **selections):
        return resolve_project(self.store, self.project, **selections)

    def add_server(self, name='removable'):
        return add_mcp(self.store, {'name': name, 'transport': 'http',
            'url': 'https://example.test/mcp', 'expected_release': latest(self.store).id})

    def adopt(self, release):
        return adopt_configuration(self.store, self.project, release.id, self.config().id)

    def test_project_removal_preserves_independent_additions_and_shared_history(self):
        self.enable('skills', 'testing')
        self.enable('skills', 'review')
        previous = self.enable('mcp', 'docs')
        credential = self.root / 'state/auth/codex/auth.json'
        credential.parent.mkdir(parents=True)
        credential.write_text('fake test credential')
        credential_stat = credential.stat()
        current = remove_project_dependency(self.store, self.project, 'skills', 'testing', previous.id)
        self.assertEqual(current.release_id, previous.release_id)
        self.assertEqual([skill['name'] for skill in self.result()['skills']], ['review'])
        self.assertIn('docs', self.result()['mcp'])
        self.assertTrue((self.root / 'registry/skills/testing.json').is_file())
        old = verify_snapshot(self.root, previous.context_snapshot)
        self.assertIn('testing', json.loads((old / 'orbehelm.project.json').read_text())['skills'])
        self.assertEqual(credential.stat().st_ino, credential_stat.st_ino)
        self.assertEqual(credential.stat().st_mtime_ns, credential_stat.st_mtime_ns)
        with self.store.read() as db:
            self.assertIsNotNone(db.get(ProjectConfiguration, previous.id))

    def test_inherited_project_requirement_remains_and_is_explained(self):
        path = self.root / 'definitions/profiles/developer.json'
        data = json.loads(path.read_text())
        data['skills'], data['mcp'] = ['testing'], ['docs']
        path.write_text(json.dumps(data))
        self.adopt(reconcile_catalog(self.store))
        self.enable('skills', 'testing')
        before = self.enable('mcp', 'docs')
        remaining = project_removal_details(self.store, self.project, before, 'skills', 'testing')
        self.assertIn('Profile developer', [item['label'] for item in remaining])
        remove_project_dependency(self.store, self.project, 'skills', 'testing', before.id)
        remove_project_dependency(self.store, self.project, 'mcp', 'docs', self.config().id)
        resolved = self.result()
        self.assertIn('testing', [item['name'] for item in resolved['skills']])
        self.assertIn('docs', resolved['mcp'])
        data = inventory(self.store, self.project, self.config())
        self.assertFalse(next(item for item in data['skills'] if item['name'] == 'testing')['project_addition'])
        with self.assertRaises(OrbeHelmError):
            remove_project_dependency(self.store, self.project, 'skills', 'testing', self.config().id)

    def test_transitive_skill_and_mcp_usage_blocks_shared_removal(self):
        path = self.root / 'registry/skills/parent.json'
        path.write_text(json.dumps({'schema_version': 1, 'source': 'examples/skills/review',
                                    'skills': ['testing'], 'mcp': ['docs']}))
        release = reconcile_catalog(self.store)
        self.adopt(release)
        self.enable('skills', 'parent')
        self.enable('skills', 'testing')
        self.enable('mcp', 'docs')
        remove_project_dependency(self.store, self.project, 'skills', 'testing', self.config().id)
        remove_project_dependency(self.store, self.project, 'mcp', 'docs', self.config().id)
        self.assertIn('testing', [item['name'] for item in self.result()['skills']])
        self.assertIn('docs', self.result()['mcp'])
        usages = shared_usage(self.store, release, 'mcp', 'docs')
        self.assertTrue(any('parent.json' in item['label'] for item in usages))
        self.assertTrue(any('Project work' in item['label'] for item in usages))
        with self.assertRaises(Conflict):
            remove_registration(self.store, 'mcp', 'docs', release.id)
        self.assertTrue((self.root / 'registry/mcp/docs.json').exists())
        self.assertEqual(latest(self.store).id, release.id)

    def test_pinned_profile_and_explicit_launch_choices_are_active_usage(self):
        release = self.add_server()
        path = self.root / 'definitions/profiles/developer.json'
        data = json.loads(path.read_text())
        data['mcp'] = ['removable']
        path.write_text(json.dumps(data))
        self.adopt(reconcile_catalog(self.store))
        self.result(persist=True)
        self.assertTrue(any('Shared definition: definitions/profiles/developer.json' == item['label']
                            for item in shared_usage(self.store, latest(self.store), 'mcp', 'removable')))
        data['mcp'] = []
        path.write_text(json.dumps(data))
        release = reconcile_catalog(self.store)
        usage = shared_usage(self.store, release, 'mcp', 'removable')
        self.assertTrue(any('Profile developer' in item['label'] and item['label'].startswith('Project') for item in usage))
        with self.assertRaises(Conflict):
            remove_registration(self.store, 'mcp', 'removable', release.id)
        self.adopt(release)
        remove_registration(self.store, 'mcp', 'removable', release.id)
        release = add_skill(self.store, {'name': 'launch-only', 'source': 'examples/skills/review',
                                         'expected_release': latest(self.store).id})
        self.adopt(release)
        self.result(skills=['launch-only'], persist=True)
        self.assertTrue(shared_usage(self.store, release, 'skills', 'launch-only'))
        with self.assertRaises(Conflict):
            remove_registration(self.store, 'skills', 'launch-only', release.id)

    def test_unused_shared_removal_retains_old_builds_catalogs_and_local_sources(self):
        release = self.add_server()
        self.adopt(release)
        self.enable('mcp', 'removable')
        output, _ = build_project(self.store, self.result(persist=True), 'codex')
        remove_project_dependency(self.store, self.project, 'mcp', 'removable', self.config().id)
        selected = self.config().id
        self.assertEqual(shared_usage(self.store, release, 'mcp', 'removable'), [])
        new_release = remove_registration(self.store, 'mcp', 'removable', release.id)
        self.assertNotEqual(new_release.id, release.id)
        self.assertFalse((self.root / 'registry/mcp/removable.json').exists())
        self.assertTrue((verify_snapshot(self.root, release.snapshot) / 'registry/mcp/removable.json').exists())
        self.assertTrue(output.is_dir())
        self.assertEqual(self.config().id, selected)
        skill_release = add_skill(self.store, {'name': 'unused-skill', 'source': 'examples/skills/review',
                                               'expected_release': new_release.id})
        remove_registration(self.store, 'skills', 'unused-skill', skill_release.id)
        self.assertTrue((self.root / 'examples/skills/review/SKILL.md').exists())

    def test_skill_alias_shadowing_does_not_block_unrelated_registry_removal(self):
        release = add_skill(self.store, {'name': 'shadowed', 'source': 'examples/skills/review',
                                         'expected_release': latest(self.store).id})
        other = self.root / 'alias-project'
        other.mkdir()
        project = register_project(self.store, other, {'shadowed': str(self.root / 'examples/skills/testing')})
        resolve_project(self.store, project, skills=['shadowed'], persist=True)
        self.assertEqual(shared_usage(self.store, release, 'skills', 'shadowed'), [])
        remove_registration(self.store, 'skills', 'shadowed', release.id)
        self.assertEqual(resolve_project(self.store, project, skills=['shadowed'])['skills'][0]['name'], 'shadowed')

    def test_project_failed_preparation_and_stale_revision_do_not_remove_source(self):
        before = self.enable('skills', 'testing')
        manifest = self.work / 'orbehelm.project.json'
        original = manifest.read_bytes()
        with patch('orbehelm.product.projects.freeze_skills', side_effect=OrbeHelmError('preparation failed')):
            with self.assertRaises(OrbeHelmError):
                remove_project_dependency(self.store, self.project, 'skills', 'testing', before.id)
        self.assertEqual(manifest.read_bytes(), original)
        self.assertEqual(self.config().id, before.id)
        self.enable('mcp', 'docs')
        with self.assertRaises(Conflict):
            remove_project_dependency(self.store, self.project, 'skills', 'testing', before.id)
        self.assertIn('testing', json.loads(manifest.read_text())['skills'])

    def test_interrupted_shared_removal_recovers_without_overwriting_external_changes(self):
        release = self.add_server()
        path = self.root / 'registry/mcp/removable.json'
        original = path.read_bytes()
        with patch('orbehelm.product.catalog.recover_publication', side_effect=[None, RuntimeError('interrupted')]):
            with self.assertRaises(RuntimeError):
                remove_registration(self.store, 'mcp', 'removable', release.id)
        self.assertEqual(path.read_bytes(), original)
        path.write_text('{"external":"edit"}')
        with self.assertRaises(Conflict):
            recover_publication(self.store)
        self.assertEqual(path.read_text(), '{"external":"edit"}')
        path.write_bytes(original)
        recover_publication(self.store)
        self.assertFalse(path.exists())
        self.assertTrue((verify_snapshot(self.root, release.snapshot) / 'registry/mcp/removable.json').exists())

    def test_corrupt_project_provenance_blocks_shared_removal(self):
        release = self.add_server()
        with patch('orbehelm.product.dependency_usage.current_selections', side_effect=OrbeHelmError('Cannot verify usage')):
            with self.assertRaises(OrbeHelmError):
                remove_registration(self.store, 'mcp', 'removable', release.id)
        self.assertEqual(latest(self.store).id, release.id)
        self.assertTrue((self.root / 'registry/mcp/removable.json').exists())

    def test_unknown_legacy_selection_blocks_until_a_known_launch_is_recorded(self):
        release = self.add_server()
        with self.store.write() as db:
            slot = OrbeSlot(key='legacy-slot', project_id=self.project.id, agent='claude',
                               profile='developer', specialization='', active_orbe=None)
            db.add(slot)
            db.flush()
            db.add(Orbe(id='legacy-orbe', project_id=self.project.id, slot_key=slot.key,
                                runtime_path=str(self.root / 'legacy-home'), created_at=None, legacy=True))
            db.flush()
            slot.active_orbe = 'legacy-orbe'
            db.add(OrbeLaunch(orbe_id='legacy-orbe', configuration_id=None, build_id=None,
                legacy_build=None, selection=None, started_at=None, ended_at=None, status='exited',
                exit_code=0, wrapper_pid=None))
        usage = shared_usage(self.store, release, 'mcp', 'removable')
        self.assertTrue(any('legacy launch usage is unknown' in item['label'] for item in usage))
        with self.assertRaises(Conflict):
            remove_registration(self.store, 'mcp', 'removable', release.id)
        with self.store.write() as db:
            db.add(OrbeLaunch(orbe_id='legacy-orbe', configuration_id=self.config().id,
                build_id=None, legacy_build=None, selection={'agent': 'claude', 'profile': 'developer',
                    'spec': None, 'skillsets': [], 'skills': []}, started_at=now(), ended_at=now(),
                status='exited', exit_code=0, wrapper_pid=None))
        self.assertEqual(shared_usage(self.store, release, 'mcp', 'removable'), [])

    def test_stale_release_and_external_source_edit_prevent_shared_removal(self):
        release = self.add_server()
        path = self.root / 'registry/mcp/removable.json'
        before = path.read_bytes()
        with self.assertRaises(Conflict):
            remove_registration(self.store, 'mcp', 'removable', self.release.id)
        self.assertEqual(path.read_bytes(), before)
        path.write_bytes(before + b'\n')
        with self.assertRaises(Conflict):
            remove_registration(self.store, 'mcp', 'removable', release.id)
        self.assertEqual(path.read_bytes(), before + b'\n')
        self.assertEqual(latest(self.store).id, release.id)

    def test_removal_ui_csrf_and_usage_recheck(self):
        release = self.add_server()
        self.adopt(release)
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        shared = '/mcp/removable/remove'
        with TestClient(app, base_url='http://localhost:8765') as client:
            paths = {str(path.relative_to(self.root)) for path in self.root.rglob('*')}
            preview = client.get(shared)
            self.assertEqual(preview.status_code, 200)
            self.assertIn('No current shared definition', preview.text)
            self.assertEqual(paths, {str(path.relative_to(self.root)) for path in self.root.rglob('*')})
            token = client.cookies['orbehelm_csrf']
            self.assertEqual(client.post(shared, data={'expected': release.id}).status_code, 403)
            self.enable('mcp', 'removable')
            blocked = client.post(shared, data={'expected': release.id, 'csrf': token})
            self.assertEqual(blocked.status_code, 409)
            self.assertTrue((self.root / 'registry/mcp/removable.json').exists())
            blocked_preview = client.get(shared)
            self.assertIn('Removal blocked', blocked_preview.text)
            self.assertNotIn('<button>Remove from shared library</button>', blocked_preview.text)
            project_url = f'/projects/{self.project.id}/dependencies/mcp/removable/remove'
            project_preview = client.get(project_url)
            self.assertEqual(project_preview.status_code, 200)
            config = self.config()
            self.assertEqual(client.post(project_url, data={'expected': config.id}).status_code, 403)
            removed = client.post(project_url, data={'expected': config.id, 'csrf': token})
            self.assertEqual(removed.status_code, 200)
            self.assertIn('Project addition removed', removed.text)
            self.assertNotIn(f'href="{project_url}"', removed.text)
            removed_shared = client.post(shared, data={'expected': release.id, 'csrf': token})
            self.assertEqual(removed_shared.status_code, 200)
            self.assertIn('removed from the shared library', removed_shared.text)


if __name__ == '__main__':
    unittest.main()

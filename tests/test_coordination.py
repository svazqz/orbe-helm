"""Task workflow tests use disposable roots and fake native executables; no model access."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from sqlalchemy import select, text
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from orbehelm.core import OrbeHelmError, build_directory
from orbehelm.cli import main
from orbehelm.adapters import launch, orbe_identity, child_command
from orbehelm.coordination_runtime import prepare_runtime
from orbehelm.delegation_runner import execute_delegation, execute_operator_qa, recover_delegation
from orbehelm.mcp_bridge import Bridge
from orbehelm.product.catalog import reconcile_catalog, Conflict
from orbehelm.product.database import migrate, Store, engine_for
from orbehelm.product.models import Task, LogicalOrbe, Delegation, TaskEvent
from orbehelm.product.projects import register_project, resolve_project, build_project
from orbehelm.product.coordination import Coordinator, ensure_orbe, accept_knowledge
from orbehelm.product.web import create_app
# Bind the real process inspector before tests patch native subprocess launch.
from orbehelm.infrastructure.process import lifecycle

REPO = Path(__file__).resolve().parents[1]

FAKE_NATIVE = '''import json,os,subprocess,sys,time,tomllib
from pathlib import Path
if os.environ.get('FAKE_WAIT'):
    time.sleep(10)
config=tomllib.loads((Path(os.environ['CODEX_HOME'])/'config.toml').read_text())
bridge=config['mcp_servers']['orbehelm']
process=subprocess.Popen([bridge['command'],*bridge['args']],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
def request(i,method,params):
    process.stdin.write(json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':params})+'\\n')
    process.stdin.flush()
    response=json.loads(process.stdout.readline())
    assert response['id']==i,response
    return response['result']
request(1,'initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'fake','version':'1'}})
process.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\\n')
process.stdin.flush()
context=request(2,'tools/call',{'name':'read_context','arguments':{}})
assert not context['isError'],context
context=json.loads(context['content'][0]['text'])
assert context['unique_key']==os.environ['ORBEHELM_UNIQUE_KEY']
assert context['parent_id'] and Path('app.py').read_text()=='value = 1\\n'
status='approved' if os.environ['ORBEHELM_PROFILE']=='reviewer' else 'passed'
if os.environ.get('FAKE_TAMPER'):
    Path('app.py').write_text('modified input')
result=request(3,'tools/call',{'name':'complete_delegation','arguments':{'status':status,'summary':'Fake native verification','findings':[],'evidence':[]}})
assert not result['isError'],result
process.stdin.close()
assert process.wait(timeout=5)==0
raise SystemExit(int(os.environ.get('FAKE_EXIT','0')))
'''


class CoordinationTests(unittest.TestCase):
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
        (self.work / 'app.py').write_text('value = 1\n')
        migrate(self.root)
        self.store = Store(self.root)
        self.addCleanup(self.store.close)
        reconcile_catalog(self.store)
        self.project = register_project(self.store, self.work)
        self.actor = ensure_orbe(self.store, self.project, 'APP-123', 'developer', spec='python')
        self.coordinator = Coordinator(self.store, self.actor)

    def submit(self, key='candidate-1', coordinator=None):
        coordinator = coordinator or self.coordinator
        return coordinator.submit_work(['app.py'], 'Changed the value; review and verify it.', key,
            coordinator.context()['version'], requirements='The app contains value = 1.')

    def review(self, status='approved'):
        request = self.coordinator.create_delegation('reviewer', 'review', 'Check requirements', self.coordinator.context()['version'])
        self.coordinator.claim(request['id'])
        child = Coordinator(self.store, request['child_id'], request['id'])
        child.stage_result(status, 'Review result', [], [])
        return self.coordinator.finish(request['id'], True)

    def fake_native(self):
        directory = self.root / 'bin'
        directory.mkdir(exist_ok=True)
        executable = directory / 'codex'
        executable.write_text('#!' + sys.executable + '\n' + FAKE_NATIVE)
        executable.chmod(0o755)
        return patch.dict(os.environ, {'PATH': str(directory) + os.pathsep + os.environ.get('PATH', '')})

    def test_0001_migration_preserves_active_native_session_references(self):
        root = self.root / 'old-install'
        (root / 'state').mkdir(parents=True)
        engine = engine_for(root)
        try:
            with engine.begin() as connection:
                config = Config()
                config.set_main_option('script_location', str(REPO / 'src/orbehelm/product/migrations'))
                config.attributes['connection'] = connection
                command.upgrade(config, '0001')
                connection.execute(text("INSERT INTO projects VALUES ('p','/project','Old',NULL,'now')"))
                connection.execute(text("INSERT INTO session_slots VALUES ('slot','p','codex','developer','',NULL)"))
                connection.execute(text("INSERT INTO sessions VALUES ('orbe','p','slot','state/orbes/orbe','now',0)"))
                connection.execute(text("UPDATE session_slots SET active_session='orbe' WHERE key='slot'"))
                connection.execute(text("INSERT INTO session_launches VALUES ('launch','orbe',NULL,NULL,'build',NULL,'now',NULL,'running',NULL,123)"))
            migrate(root)
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text('SELECT key,unique_key,active_orbe FROM orbe_slots')).one(), ('slot', '', 'orbe'))
                self.assertEqual(connection.execute(text('SELECT id,slot_key FROM orbes')).one(), ('orbe', 'slot'))
                self.assertEqual(connection.execute(text('SELECT id,orbe_id,status FROM orbe_launches')).one(), ('launch', 'orbe', 'running'))
                self.assertIsNone(connection.exec_driver_sql('PRAGMA foreign_key_check').first())
                self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_keys').scalar(), 1)
            self.assertEqual(len(list((root / 'state/backups').glob('*.sqlite3'))), 1)
        finally:
            engine.dispose()

    def test_stdio_protocol_rejects_bad_frames_and_enforces_tool_schema(self):
        process = subprocess.Popen([sys.executable, str(REPO / 'src/orbehelm/_entry.py'),
            'mcp-serve', '--root', str(self.root), '--actor', self.actor, '--agent', 'codex'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            def exchange(value):
                process.stdin.write(value + '\n')
                process.stdin.flush()
                return json.loads(process.stdout.readline())
            self.assertEqual(exchange('{broken')['error']['code'], -32700)
            self.assertEqual(exchange(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}))['error']['code'], -32000)
            response = exchange(json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'initialize',
                'params': {'protocolVersion': '2025-06-18'}}))
            self.assertEqual(response['result']['protocolVersion'], '2025-06-18')
            process.stdin.write(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) + '\n')
            response = exchange(json.dumps({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'}))
            self.assertIn('delegate', {item['name'] for item in response['result']['tools']})
            response = exchange(json.dumps({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call',
                'params': {'name': 'save_knowledge', 'arguments': {'unexpected': True}}}))
            self.assertTrue(response['result']['isError'])
            response = exchange(json.dumps({'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call',
                'params': {'name': 'read_context', 'arguments': {}}}))
            self.assertFalse(response['result']['isError'])
            process.stdin.close()
            self.assertEqual(process.wait(timeout=5), 0)
            self.assertEqual(process.stderr.read(), '')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
            process.stderr.close()

    def test_key_identity_is_provider_independent_and_legacy_slots_are_unchanged(self):
        self.assertEqual(ensure_orbe(self.store, self.project, 'APP-123', 'developer', spec='python'), self.actor)
        other = ensure_orbe(self.store, self.project, 'APP-124', 'developer', spec='python')
        self.assertNotEqual(other, self.actor)
        resolved = resolve_project(self.store, self.project, spec='python', persist=True)
        legacy, legacy_key = orbe_identity(resolved, 'codex')
        self.assertNotIn('unique_key', legacy)
        self.assertEqual(orbe_identity(resolved, 'codex', None)[1], legacy_key)
        self.assertNotEqual(orbe_identity(resolved, 'codex', 'APP-123')[1], legacy_key)
        self.assertNotEqual(orbe_identity(resolved, 'codex', 'APP-123')[1], orbe_identity(resolved, 'claude', 'APP-123')[1])
        self.assertNotEqual(orbe_identity(resolved, 'codex', 'APP-123')[1], orbe_identity(resolved, 'codex', 'APP-124')[1])

    def test_task_workspace_binding_is_stable_and_writer_lock_prevents_shared_edits(self):
        second_work = self.root / 'other-work'
        second_work.mkdir()
        actor = ensure_orbe(self.store, self.project, 'APP-124', 'developer', workspace=second_work)
        self.assertEqual(ensure_orbe(self.store, self.project, 'APP-124', 'developer'), actor)
        with self.assertRaises(Conflict):
            ensure_orbe(self.store, self.project, 'APP-124', 'developer', workspace=self.work)
        resolved = resolve_project(self.store, self.project, spec='python', persist=True)
        output, _ = build_project(self.store, resolved, 'codex')
        other = ensure_orbe(self.store, self.project, 'APP-125', 'developer', spec='python')
        def nested(*args, **kwargs):
            with self.assertRaisesRegex(OrbeHelmError, 'Another developer'):
                launch(self.root, output, resolved, 'codex', unique_key='APP-125', actor_id=other)
            return 0
        with patch('orbehelm.adapters.doctor', return_value={'ok': True}), patch('orbehelm.adapters.subprocess.call', side_effect=nested):
            self.assertEqual(launch(self.root, output, resolved, 'codex', unique_key='APP-123', actor_id=self.actor), 0)

    def test_memory_is_versioned_scoped_and_project_acceptance_is_explicit(self):
        saved = self.coordinator.save_knowledge('decision', 'Use a transaction.', 'task', 0, kind='decision', evidence=['fixture:revision-1'])
        again = self.coordinator.save_knowledge('decision', 'Use a transaction.', 'task', 0, kind='decision', evidence=['fixture:revision-1'])
        self.assertEqual(saved, again)
        with self.assertRaises(Conflict):
            self.coordinator.save_knowledge('decision', 'Overwrite silently.', 'task', 0, kind='decision', evidence=['fixture:revision-1'])
        other = Coordinator(self.store, ensure_orbe(self.store, self.project, 'APP-124', 'developer'))
        self.assertEqual(other.context()['knowledge'], [])
        with self.assertRaises(OrbeHelmError):
            other.read_artifact(saved['artifact_id'])
        proposed = self.coordinator.save_knowledge('architecture', 'Use explicit state transitions.', 'project', 0, kind='decision', evidence=['fixture:revision-1'])
        self.assertEqual(other.context()['knowledge'], [])
        accept_knowledge(self.store, self.project.id, proposed['id'])
        self.assertEqual(other.context()['knowledge'][0]['status'], 'accepted')
        self.assertEqual(other.read_artifact(proposed['artifact_id'])['data']['content'], 'Use explicit state transitions.')
        self.assertIn('/knowledge/', str(next(path for path in (self.root / 'state/projects').rglob('record.json') if 'knowledge' in str(path))))

    def test_candidates_are_immutable_and_reject_unsafe_or_conflicting_submissions(self):
        first = self.submit()
        self.assertEqual(self.submit(), first)
        (self.work / 'app.py').write_text('value = 2\n')
        self.assertEqual(self.coordinator.read_artifact(first['candidate_id'])['files']['app.py']['sha256'],
                         __import__('hashlib').sha256(b'value = 1\n').hexdigest())
        with self.assertRaises(Conflict):
            self.submit()
        self.assertNotEqual(self.submit('other-key')['candidate_id'], first['candidate_id'])
        for source in ['../escape', '.env', '.']:
            (self.work / '.env').write_text('fake fixture data')
            with self.assertRaises(OrbeHelmError):
                self.coordinator.submit_work([source], 'Handoff', 'unsafe', self.coordinator.context()['version'], 'Requirements')

    def operator_terminal(self):
        # Simulated operator boundary for disposable fixture state, never live data.
        return patch.dict(os.environ, {'ORBEHELM_ORBE_ID': '', 'ORBEHELM_MEMORY_BINDING': ''})

    def approve(self, key='approval'):
        context = self.coordinator.context()
        with self.operator_terminal():
            return self.coordinator.human_decision(context['candidate_id'], 'approved',
                'fixture-operator', 'Inspected exact candidate', key, context['version'])

    def request_qa(self, key='qa'):
        context = self.coordinator.context()
        with self.operator_terminal():
            return self.coordinator.request_qa(context['candidate_id'], key, 'Run tests', context['version'])

    def test_workflow_stops_for_human_and_manual_qa(self):
        self.submit()
        with self.assertRaises(OrbeHelmError):
            self.coordinator.create_delegation('qa', 'qa', 'Run tests', self.coordinator.context()['version'])
        with self.assertRaises(Conflict), self.operator_terminal():
            self.request_qa()
        review = self.review()
        self.assertEqual(review['status'], 'completed')
        self.assertEqual(self.coordinator.context()['state'], 'awaiting_human_approval')
        self.assertEqual(len(self.coordinator.context()['delegations']), 1)
        with self.assertRaises(Conflict):
            self.request_qa()
        self.approve()
        self.assertEqual(self.coordinator.context()['state'], 'approved_for_qa')
        self.assertEqual(len(self.coordinator.context()['delegations']), 1)
        qa = self.request_qa()
        self.assertEqual(self.coordinator.context()['state'], 'testing')
        self.coordinator.claim(qa['id'])
        child = Coordinator(self.store, qa['child_id'], qa['id'])
        child.stage_result('passed', 'All acceptance cases passed.', [], [])
        self.coordinator.finish(qa['id'], True)
        self.assertEqual(self.coordinator.context()['state'], 'complete')
        self.assertEqual(qa['parent_id'], self.actor)
        with self.assertRaises(OrbeHelmError):
            child.submit_work(['app.py'], 'Nested developer', 'bad', 0, 'No')

    def test_two_developers_get_distinct_children_and_retries_reuse_requests(self):
        self.submit()
        first = self.coordinator.create_delegation('reviewer', 'review', 'Check', self.coordinator.context()['version'])
        again = self.coordinator.create_delegation('reviewer', 'review', 'Check', -1)
        self.assertEqual(first['id'], again['id'])
        with self.assertRaises(Conflict):
            self.coordinator.create_delegation('reviewer', 'review', 'Different instruction', self.coordinator.context()['version'])
        other = Coordinator(self.store, ensure_orbe(self.store, self.project, 'APP-124', 'developer'))
        self.submit(coordinator=other)
        second = other.create_delegation('reviewer', 'review', 'Check', other.context()['version'])
        self.assertNotEqual(first['child_id'], second['child_id'])
        child = Coordinator(self.store, first['child_id'], first['id']).context()
        self.assertEqual(child['unique_key'], 'APP-123')
        self.assertEqual(child['parent_id'], self.actor)
        with self.assertRaises(OrbeHelmError):
            Coordinator(self.store, second['child_id'], first['id'])
        with self.assertRaises(OrbeHelmError):
            other.claim(first['id'])

    def test_historical_submission_caps_do_not_block_new_candidates(self):
        with self.store.write() as db:
            task = db.get(Task, self.coordinator.context()['task_id'])
            task.rounds, task.max_rounds = 500, 5
            task.state = 'complete'
        self.submit()
        self.assertEqual(self.coordinator.context()['rounds'], 501)
        self.assertIsNone(self.coordinator.context()['max_rounds'])
        self.review('changes_requested')
        self.submit('another-candidate')
        self.assertEqual(self.coordinator.context()['rounds'], 502)

    def test_rereview_is_on_demand_and_invalidates_prior_human_approval(self):
        self.submit()
        self.review()
        self.approve()
        request = self.coordinator.create_delegation('reviewer', 'second-review', 'Inspect again',
                                                     self.coordinator.context()['version'])
        with self.assertRaises(Conflict):
            self.request_qa()
        self.coordinator.claim(request['id'])
        child = Coordinator(self.store, request['child_id'], request['id'])
        child.stage_result('approved', 'New independent assessment', [], [])
        self.coordinator.finish(request['id'], True)
        self.assertEqual(self.coordinator.context()['state'], 'awaiting_human_approval')
        with self.assertRaises(Conflict):
            self.request_qa()
        self.approve('approval-2')
        self.assertEqual(self.coordinator.context()['state'], 'approved_for_qa')

    def test_new_source_and_reopen_invalidate_human_approval(self):
        self.submit()
        self.review()
        approval = self.approve()
        self.assertEqual(self.approve(), approval)
        self.coordinator.reopen(self.coordinator.context()['version'])
        self.assertIsNone(self.coordinator.context()['human_decision'])
        self.submit('new-source')
        self.assertIsNone(self.coordinator.context()['human_decision'])
        with self.assertRaises(Conflict):
            self.request_qa()

    def test_operator_decisions_reject_stale_versions_candidates_and_duplicate_keys(self):
        self.submit()
        self.review()
        context = self.coordinator.context()
        with self.operator_terminal():
            for candidate, version in [('different', context['version']), (context['candidate_id'], -1)]:
                with self.assertRaises(Conflict):
                    self.coordinator.human_decision(candidate, 'approved', 'operator', 'Reviewed', 'human', version)
            rejected = self.coordinator.human_decision(context['candidate_id'], 'rejected',
                'operator', 'Needs changes', 'human', context['version'])
            self.assertEqual(rejected['state'], 'developing')
            with self.assertRaises(Conflict):
                self.coordinator.human_decision(context['candidate_id'], 'approved',
                    'operator', 'Reviewed', 'human', self.coordinator.context()['version'])

    def test_agent_qa_and_parallel_requests_never_prepare_or_launch_native_processes(self):
        self.submit()
        bridge = Bridge(self.store, self.actor, 'codex')
        self.assertEqual(bridge.tools['delegate']['inputSchema']['properties']['profile']['enum'], ['reviewer'])
        self.assertNotIn('approve', bridge.tools)
        with patch('orbehelm.delegation_runner.require_server') as ready, patch('orbehelm.delegation_runner.launch') as launch:
            for role in ['qa', 'parallel']:
                with self.assertRaises(OrbeHelmError):
                    bridge.call('delegate', {'profile': role, 'key': 'bad', 'instructions': 'No',
                                            'expected_version': self.coordinator.context()['version']})
            ready.assert_not_called()
            launch.assert_not_called()
        self.assertEqual(self.coordinator.context()['delegations'], [])

    def test_operator_actions_are_unavailable_through_an_agent_environment(self):
        self.submit()
        self.review()
        context = self.coordinator.context()
        with patch.dict(os.environ, {'ORBEHELM_ORBE_ID': 'bound-agent'}):
            with self.assertRaises(OrbeHelmError):
                self.coordinator.human_decision(context['candidate_id'], 'approved', 'operator', 'No', 'no', context['version'])
            with self.assertRaises(OrbeHelmError), patch('orbehelm.delegation_runner.launch') as launch:
                execute_operator_qa(self.coordinator, 'codex', context['candidate_id'], 'qa', 'No', context['version'])
            launch.assert_not_called()

    def test_operator_cli_records_approval_then_launches_qa_only_on_explicit_command(self):
        self.submit()
        self.review()
        context = self.coordinator.context()
        data = self.root / 'operator.json'
        common = ['--root', str(self.root), '--project', str(self.work), '--actor', self.actor,
                  '--data-file', str(data)]
        data.write_text(json.dumps({'candidate_id': context['candidate_id'], 'expected_version': context['version'],
            'key': 'operator-approval', 'operator': 'fixture-human', 'summary': 'Reviewed candidate'}))
        with self.operator_terminal(), contextlib.redirect_stdout(io.StringIO()):
            with patch('orbehelm.product.coordination_commands.execute_operator_qa') as qa:
                self.assertEqual(main(['tasks', 'approve', *common]), 0)
                qa.assert_not_called()
            context = self.coordinator.context()
            data.write_text(json.dumps({'candidate_id': context['candidate_id'], 'expected_version': context['version'],
                'key': 'operator-qa', 'instructions': 'Run acceptance checks'}))
            with self.fake_native():
                self.assertEqual(main(['tasks', 'qa', '--agent', 'codex', *common]), 0)
        self.assertEqual(self.coordinator.context()['state'], 'complete')

    def test_one_active_assessment_and_qa_retry_identity(self):
        self.submit()
        request = self.coordinator.create_delegation('reviewer', 'first', 'Review', self.coordinator.context()['version'])
        with self.assertRaises(Conflict):
            self.coordinator.create_delegation('reviewer', 'second', 'Review', self.coordinator.context()['version'])
        with self.assertRaises(Conflict):
            self.submit('new-while-active')
        self.coordinator.claim(request['id'])
        Coordinator(self.store, request['child_id'], request['id']).stage_result('approved', 'Approved', [], [])
        self.coordinator.finish(request['id'], True)
        self.approve()
        qa = self.request_qa()
        self.assertEqual(self.request_qa()['id'], qa['id'])
        with self.assertRaises(Conflict):
            self.request_qa('second-qa')
        with self.assertRaises(Conflict):
            self.coordinator.create_delegation('reviewer', 'during-qa', 'Review', self.coordinator.context()['version'])

    def test_legacy_qa_receipts_do_not_create_human_approval(self):
        self.submit()
        self.review()
        # Model an old queued QA delegation copied from a pre-upgrade installation.
        with self.store.write() as db:
            actor = LogicalOrbe(id='legacy-qa', task_id=self.coordinator.context()['task_id'],
                profile='qa', specialization='', orbe_key='legacy', parent_id=self.actor)
            db.add(actor)
            db.flush()
            review = db.scalars(select(Delegation).where(Delegation.profile == 'reviewer')).first()
            db.add(Delegation(id='legacy-request', task_id=review.task_id, parent_id=self.actor,
                child_id=actor.id, candidate_id=review.candidate_id, context_id=review.context_id,
                profile='qa', key='legacy', instructions='Run tests'))
        with self.operator_terminal(), self.assertRaises(Conflict):
            self.coordinator.request_qa(self.coordinator.context()['candidate_id'], 'legacy', 'Run tests',
                                        self.coordinator.context()['version'])

    def test_task_cli_dry_run_does_not_execute_qa(self):
        with patch('orbehelm.product.coordination_commands.execute_operator_qa') as qa:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['tasks', 'qa', '--root', str(self.root), '--project', str(self.work),
                                       '--actor', self.actor, '--dry-run']), 2)
            qa.assert_not_called()

    def test_fix_revision_invalidates_old_approvals_and_has_no_lifetime_limit(self):
        self.submit()
        reviewed = self.review('changes_requested')
        old_candidate = reviewed['candidate_id']
        self.assertEqual(self.coordinator.context()['state'], 'developing')
        self.submit('candidate-2')
        self.assertNotEqual(self.coordinator.context()['candidate_id'], old_candidate)
        # A new candidate has no inherited reviewer or human approval.
        self.assertEqual(self.coordinator.context()['state'], 'awaiting_review')
        stale = Coordinator(self.store, reviewed['child_id'], reviewed['id'])
        with self.assertRaises(Conflict):
            stale.stage_result('approved', 'Late result', [], [])
        self.review('changes_requested')
        self.submit('candidate-3')
        self.review('changes_requested')
        self.submit('candidate-4')
        self.assertIsNone(self.coordinator.context()['submission_limit'])

    def test_child_knowledge_snapshot_survives_later_project_knowledge_updates(self):
        old = self.coordinator.save_knowledge('policy', 'Version one', 'project', 0, kind='decision', evidence=['fixture:revision-1'])
        accept_knowledge(self.store, self.project.id, old['id'])
        other = Coordinator(self.store, ensure_orbe(self.store, self.project, 'APP-124', 'developer'))
        self.submit(coordinator=other)
        request = other.create_delegation('reviewer', 'review', 'Check', other.context()['version'])
        new = self.coordinator.save_knowledge('policy', 'Version two', 'project', 1, kind='decision', evidence=['fixture:revision-1'])
        accept_knowledge(self.store, self.project.id, new['id'], old['id'])
        child = Coordinator(self.store, request['child_id'], request['id'])
        self.assertEqual(child.context()['knowledge'][0]['artifact_id'], old['artifact_id'])
        self.assertEqual(child.read_artifact(old['artifact_id'])['data']['content'], 'Version one')

    def test_native_runner_round_trip_uses_real_stdio_bridge_without_a_model(self):
        self.submit()
        with self.fake_native():
            reviewed = execute_delegation(self.coordinator, 'codex', 'reviewer', 'review', 'Inspect', self.coordinator.context()['version'])
            self.assertEqual(reviewed['status'], 'completed')
            self.assertEqual(reviewed['result']['status'], 'approved')
            self.approve()
            with self.operator_terminal():
                tested = execute_operator_qa(self.coordinator, 'codex', self.coordinator.context()['candidate_id'],
                    'qa', 'Check acceptance', self.coordinator.context()['version'])
        self.assertEqual(tested['result']['status'], 'passed')
        self.assertEqual(self.coordinator.context()['state'], 'complete')
        self.assertEqual((self.work / 'app.py').read_text(), 'value = 1\n')
        metadata = [json.loads(path.read_text()) for path in (self.root / 'state/orbes').glob('*/orbe.json')]
        self.assertEqual(len(metadata), 2)
        self.assertTrue(all(item['root_unique_key'] == 'APP-123' for item in metadata))
        self.assertEqual(len({item['unique_key'] for item in metadata}), 2)

    def test_failed_exit_or_modified_inputs_never_promote_staged_approval(self):
        self.submit()
        with self.fake_native(), patch.dict(os.environ, {'FAKE_EXIT': '1'}):
            failed = execute_delegation(self.coordinator, 'codex', 'reviewer', 'review', 'Inspect', self.coordinator.context()['version'])
        self.assertEqual(failed['status'], 'failed')
        self.assertIn('unapproved_staged_result', failed)
        self.assertEqual(self.coordinator.context()['state'], 'blocked')
        self.coordinator.reopen(self.coordinator.context()['version'])
        self.submit('candidate-2')
        with self.fake_native(), patch.dict(os.environ, {'FAKE_TAMPER': '1'}):
            with self.assertRaisesRegex(OrbeHelmError, 'modified a submitted input'):
                execute_delegation(self.coordinator, 'codex', 'reviewer', 'review', 'Inspect', self.coordinator.context()['version'])
        self.assertEqual(self.coordinator.context()['state'], 'blocked')

    def test_native_timeout_and_cancellation_block_the_workflow(self):
        self.submit()
        cancel = threading.Event()
        timer = threading.Timer(.3, cancel.set)
        timer.start()
        self.addCleanup(timer.cancel)
        with self.fake_native(), patch.dict(os.environ, {'FAKE_WAIT': '1'}):
            with self.assertRaises(OrbeHelmError):
                execute_delegation(self.coordinator, 'codex', 'reviewer', 'review', 'Inspect', self.coordinator.context()['version'], cancel=cancel)
        self.assertEqual(self.coordinator.context()['delegations'][0]['status'], 'cancelled')
        self.coordinator.reopen(self.coordinator.context()['version'])
        self.submit('candidate-2')
        with self.fake_native(), patch.dict(os.environ, {'FAKE_WAIT': '1'}):
            with self.assertRaisesRegex(OrbeHelmError, 'timed out'):
                execute_delegation(self.coordinator, 'codex', 'reviewer', 'review', 'Inspect', self.coordinator.context()['version'], timeout=.01)

    def test_already_cancelled_delegation_does_not_start_a_native_process(self):
        self.submit()
        cancel = threading.Event()
        cancel.set()
        with self.fake_native(), patch('orbehelm.adapters.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(OrbeHelmError, 'cancelled'):
                execute_delegation(self.coordinator, 'codex', 'reviewer', 'review', 'Inspect',
                                   self.coordinator.context()['version'], cancel=cancel)
            spawn.assert_not_called()
        self.assertEqual(self.coordinator.context()['delegations'][0]['status'], 'cancelled')

    def test_recovery_refuses_to_duplicate_a_live_or_uncertain_worker(self):
        self.submit()
        record = self.coordinator.create_delegation('reviewer', 'review', 'Check', self.coordinator.context()['version'])
        self.coordinator.claim(record['id'])
        with self.assertRaises(Conflict):
            recover_delegation(self.coordinator, record['id'])
        with patch('orbehelm.delegation_runner.os.kill', side_effect=ProcessLookupError):
            with self.assertRaises(Conflict):
                recover_delegation(self.coordinator, record['id'])
            recovered = recover_delegation(self.coordinator, record['id'], confirm_stopped=True)
        self.assertEqual(recovered['status'], 'interrupted')

    def test_runtime_overlays_are_scoped_and_generated_builds_remain_unchanged(self):
        resolved = resolve_project(self.store, self.project, spec='python', persist=True)
        for agent in ['codex', 'claude', 'opencode']:
            output, _ = build_project(self.store, resolved, agent)
            original = (output / 'instructions.md').read_bytes()
            directory = self.root / ('runtime-' + agent)
            prepared, context = prepare_runtime(self.root, output, agent, directory, self.actor)
            self.assertEqual(context['unique_key'], 'APP-123')
            self.assertEqual((output / 'instructions.md').read_bytes(), original)
            self.assertIn('OrbeHelm task coordination', (prepared / 'instructions.md').read_text())
            if agent == 'codex':
                config = tomllib.loads((prepared / 'config.toml').read_text())['mcp_servers']['orbehelm']
                self.assertIn(self.actor, config['args'])
            elif agent == 'claude':
                self.assertIn('orbehelm', json.loads((prepared / 'mcp.json').read_text())['mcpServers'])
            else:
                self.assertIn('orbehelm', json.loads((prepared / 'opencode.json').read_text())['mcp'])
            command_line = child_command(prepared, agent, 'reviewer', 'Check')
            if agent == 'codex':
                self.assertIn('--dangerously-bypass-approvals-and-sandbox', command_line)
            elif agent == 'claude':
                self.assertIn('--dangerously-skip-permissions', command_line)
            else:
                self.assertEqual(json.loads((prepared / 'opencode.json').read_text())['permission'], 'allow')

    def test_keyed_dry_run_is_write_free_and_task_ui_is_project_scoped(self):
        resolved = resolve_project(self.store, self.project, spec='python', persist=True)
        build_project(self.store, resolved, 'codex')
        before = {str(path.relative_to(self.root)) for path in self.root.rglob('*')}
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = main(['run', '--root', str(self.root), '--project', str(self.work),
                           '--unique-key', 'APP-125', '--dry-run'])
        self.assertEqual(result, 0)
        self.assertIn('APP-125', output.getvalue())
        self.assertEqual(before, {str(path.relative_to(self.root)) for path in self.root.rglob('*')})
        submitted = self.submit()
        app = create_app(self.root)
        self.addCleanup(app.state.store.close)
        task_id = self.coordinator.context()['task_id']
        with TestClient(app, base_url='http://localhost:8765') as client:
            self.assertEqual(client.get(f'/projects/{self.project.id}?tab=tasks').status_code, 404)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(['tasks', 'list', '--root', str(self.root), '--project', str(self.work)]), 0)
            self.assertIn('APP-123', output.getvalue())
            self.assertEqual(client.get(f'/projects/{self.project.id}/tasks/{task_id}').status_code, 404)
            self.assertEqual(client.get(f'/projects/{self.project.id}/tasks/{task_id}/artifacts/{submitted["candidate_id"]}').status_code, 404)
            self.assertEqual(client.get(f'/projects/not-this-project/tasks/{task_id}').status_code, 404)


if __name__ == '__main__':
    unittest.main()

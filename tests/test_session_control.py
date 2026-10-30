"""Lifecycle regression checks use owned fake processes, never model sessions."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import test_product
from orbehelm.cli import main
from orbehelm.core import OrbeHelmError
from orbehelm.product.models import Orbe, OrbeSlot, OrbeLaunch
from orbehelm.session_control import close, prune, selected, busy, lock_path, stop


class LifecycleTests(unittest.TestCase):
    setUp = test_product.ProductTests.setUp

    def add_orbe(self, number=1, project=None):
        project = project or self.project
        identity, key = f'{number:032x}', f'slot{number}'
        path = self.root / 'state/orbes' / identity
        path.mkdir(parents=True)
        (path / 'orbe.json').write_text(json.dumps({'mode': 'native'}))
        with self.store.write() as db:
            db.add(OrbeSlot(key=key, project_id=project.id, agent='codex', profile='developer', specialization='', unique_key=str(number)))
            db.flush()
            db.add(Orbe(id=identity, project_id=project.id, slot_key=key, runtime_path=str(path), legacy=False))
            db.flush()
            db.get(OrbeSlot, key).active_orbe = identity
            db.add(OrbeLaunch(orbe_id=identity, started_at=f'2026-10-30T00:00:{number:02}', status='running', wrapper_pid=None))
        return selected(self.store, orbe_id=identity)[0]

    def start(self, row):
        lock = lock_path(self.root, row)
        lock.parent.mkdir(parents=True, exist_ok=True)
        code = '''import fcntl, pathlib, sys, time, subprocess
from orbehelm.infrastructure.process.lifecycle import remember_process
lock = pathlib.Path(sys.argv[1]).open('a')
fcntl.flock(lock, fcntl.LOCK_EX)
remember_process(pathlib.Path(sys.argv[2]), sys.argv[3])
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
print(child.pid, flush=True)
time.sleep(120)
'''
        env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')}
        child = subprocess.Popen([sys.executable, '-c', code, str(lock), str(self.root / 'state/processes'), row.id], env=env, stdout=subprocess.PIPE, text=True)
        def cleanup_wrapper():
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
        self.addCleanup(cleanup_wrapper)
        self.addCleanup(child.stdout.close)
        descendant = int(child.stdout.readline())
        def cleanup_descendant():
            try:
                os.kill(descendant, 9)
            except ProcessLookupError:
                pass
        self.addCleanup(cleanup_descendant)
        return child

    def test_close_latest_and_project_all(self):
        first, last = self.add_orbe(), self.add_orbe(2)
        one, two = self.start(first), self.start(last)
        result = close(self.store, self.work)
        self.assertEqual(result, [{'id': last.id, 'status': 'closed'}])
        two.wait(timeout=5)
        self.assertIsNone(one.poll())
        self.assertTrue(busy(lock_path(self.root, first)))
        close(self.store, self.work, all_sessions=True)
        one.wait(timeout=5)
        self.assertFalse(busy(lock_path(self.root, first)))
        self.assertTrue(Path(first.runtime_path).exists())

    def test_reused_pid_is_rejected(self):
        row = self.add_orbe()
        child = self.start(row)
        path = self.root / 'state/processes' / (row.id + '.json')
        data = json.loads(path.read_text())
        data['started'] = 'different process'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(OrbeHelmError, 'identity changed'):
            stop(self.store, row)
        self.assertIsNone(child.poll())

    def test_prune_removes_homes_records_and_pointer(self):
        row = self.add_orbe()
        child = self.start(row)
        pointer = self.root / 'state/orbe-keys' / row.slot_key / 'active.json'
        pointer.write_text(json.dumps({'orbe_id': row.id}))
        prune(self.store, [row])
        child.wait(timeout=5)
        self.assertFalse(Path(row.runtime_path).exists())
        self.assertFalse(pointer.exists())
        self.assertEqual(selected(self.store, self.work), [])
        with self.store.read() as db:
            self.assertIsNone(db.get(OrbeSlot, row.slot_key).active_orbe)

    def test_confirmation_and_dry_run(self):
        row = self.add_orbe()
        args = ['prune', self.project.id, '--root', str(self.root)]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), patch('builtins.input', return_value='no'):
            self.assertEqual(main(args), 2)
        self.assertTrue(Path(row.runtime_path).exists())
        with contextlib.redirect_stdout(io.StringIO()), patch('builtins.input', side_effect=AssertionError('dry run prompted')):
            self.assertEqual(main(args + ['--dry-run']), 0)
        with contextlib.redirect_stdout(io.StringIO()), patch('builtins.input', return_value='DELETE'):
            self.assertEqual(main(args), 0)
        self.assertFalse(Path(row.runtime_path).exists())

    def test_global_spans_projects_and_explicit_id(self):
        from orbehelm.product.projects import register_project
        other = self.root / 'other'
        other.mkdir()
        project = register_project(self.store, other)
        first, second = self.add_orbe(), self.add_orbe(2, project)
        one, two = self.start(first), self.start(second)
        close(self.store, self.work, orbe_id=second.id)
        two.wait(timeout=5)
        self.assertIsNone(one.poll())
        close(self.store, self.work, global_scope=True)
        one.wait(timeout=5)
        self.assertEqual(len(selected(self.store, global_scope=True)), 2)
        prune(self.store, selected(self.store, global_scope=True))
        self.assertEqual(selected(self.store, global_scope=True), [])

    def test_legacy_lock_owner_can_be_closed(self):
        row = self.add_orbe()
        child = self.start(row)
        (self.root / 'state/processes' / (row.id + '.json')).unlink()
        with self.store.write() as db:
            from sqlalchemy import select
            launch = db.scalars(select(OrbeLaunch).where(OrbeLaunch.orbe_id == row.id)).one()
            launch.wrapper_pid = child.pid
        result = close(self.store, self.work, orbe_id=row.id)
        self.assertEqual(result[0]['status'], 'closed')
        child.wait(timeout=5)

    def test_prune_rejects_symlinked_runtime(self):
        row = self.add_orbe()
        target = self.root / 'state/orbes' / 'other'
        target.mkdir()
        import shutil
        shutil.rmtree(row.runtime_path)
        Path(row.runtime_path).symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(OrbeHelmError, 'symlink'):
            prune(self.store, [row])
        self.assertTrue(target.exists())

    def test_unknown_and_empty_close(self):
        self.assertEqual(close(self.store, self.work), [])
        with self.assertRaisesRegex(OrbeHelmError, 'Unknown orbe'):
            close(self.store, self.work, orbe_id='missing')

    def test_historical_orbe_does_not_close_current_slot(self):
        row = self.add_orbe()
        child = self.start(row)
        with self.store.write() as db:
            db.add(Orbe(id='f' * 32, project_id=row.project_id, slot_key=row.slot_key,
                        runtime_path=row.runtime_path, legacy=False))
        old = selected(self.store, orbe_id='f' * 32)[0]
        self.assertEqual(stop(self.store, old)['status'], 'already_stopped')
        self.assertIsNone(child.poll())
        stop(self.store, row)
        child.wait(timeout=5)

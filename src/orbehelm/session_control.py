"""Operator lifecycle control for installation-owned native runtime homes."""
from contextlib import ExitStack
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

from sqlalchemy import delete, select

from .core import OrbeHelmError
from .compatibility import orbe_slot, read_record
from .layout import runtime_child, stored_runtime
from .product.models import Orbe, OrbeLaunch, OrbeSlot, now
from .product.projects import get_project


from .infrastructure.process.lifecycle import process_table


def lock_path(root, row):
    original = Path(row.runtime_path)
    if any(part.is_symlink() for part in (original, *original.parents)):
        raise OrbeHelmError('Orbe runtime must not traverse symlinks')
    path = stored_runtime(root, row.runtime_path) / 'orbe.json'
    record = read_record(path) if path.is_file() else {}
    thread = record.get('conversation_id') if record.get('mode') == 'managed' else None
    if thread:
        import uuid
        if uuid.UUID(thread).hex != thread:
            raise OrbeHelmError('Invalid conversation identity')
        return Path(root) / 'state/conversation-locks' / (thread + '.lock')
    return orbe_slot(root, row.slot_key) / 'launch.lock'


def busy(path):
    if not path.exists():
        return False
    if path.is_symlink():
        raise OrbeHelmError('Session lock must not be a symlink')
    with path.open('r') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def selected(store, project=None, orbe_id=None, global_scope=False):
    project_id = None if global_scope or orbe_id else get_project(store, str(project)).id
    with store.read() as db:
        query = select(Orbe)
        if orbe_id:
            query = query.where(Orbe.id == orbe_id)
        elif project_id:
            query = query.where(Orbe.project_id == project_id)
        rows = db.scalars(query).all()
        if orbe_id and not rows:
            raise OrbeHelmError('Unknown orbe ID')
        # Last activity is determined by launch time, never UUID order.
        def activity(row):
            return db.scalars(select(OrbeLaunch.started_at).where(OrbeLaunch.orbe_id == row.id)
                              .order_by(OrbeLaunch.started_at.desc())).first() or ''
        return sorted(rows, key=activity, reverse=True)


def running(store, row):
    with store.read() as db:
        slot = db.get(OrbeSlot, row.slot_key)
        return bool(slot and slot.active_orbe == row.id and busy(lock_path(store.root, row)))


def stop(store, row):
    lock = lock_path(store.root, row)
    if not running(store, row):
        return {'id': row.id, 'status': 'already_stopped'}
    path = runtime_child(store.root, 'processes', row.id + '.json')
    table = process_table()
    if path.exists():
        identity = json.loads(path.read_text())
        pid = identity['pid']
        if table.get(pid, (None, None))[1] != identity['started']:
            raise OrbeHelmError(f'Process identity changed for {row.id}; refusing to signal it')
    else:
        # Pre-lifecycle launchers have no birth token. Verify ownership through the
        # live kernel lock instead of trusting a persisted, potentially reused PID.
        with store.read() as db:
            pid = db.scalars(select(OrbeLaunch.wrapper_pid).where(OrbeLaunch.orbe_id == row.id)
                             .order_by(OrbeLaunch.started_at.desc())).first()
        try:
            owners = subprocess.run(['lsof', '-t', str(lock)], capture_output=True, text=True, check=False)
        except FileNotFoundError as error:
            raise OrbeHelmError('Legacy session requires lsof to verify the lock holder') from error
        if not pid or str(pid) not in owners.stdout.split() or pid not in table:
            raise OrbeHelmError(f'Cannot verify live launcher for {row.id}; no signal sent')
    if pid == os.getpid():
        raise OrbeHelmError('Cannot close the lifecycle command itself')
    owned = {pid}
    while True:
        children = {child for child, (parent, _) in table.items() if parent in owned}
        expanded = owned | children
        if expanded == owned:
            break
        owned = expanded
    # Stop the launcher before descendants can escape, then stop its children.
    # Only signal processes whose start identity still matches the live snapshot.
    def send(target, sig):
        current = process_table()
        if target in current and target in table and current[target][1] == table[target][1]:
            try:
                os.kill(target, sig)
            except ProcessLookupError:
                pass
    send(pid, signal.SIGSTOP)
    try:
        # Refresh once the wrapper cannot spawn another child.
        table.update(process_table())
        while True:
            expanded = owned | {child for child, (parent, _) in table.items() if parent in owned}
            if expanded == owned:
                break
            owned = expanded
        for child in owned - {pid}:
            send(child, signal.SIGTERM)
        send(pid, signal.SIGTERM)
    finally:
        send(pid, signal.SIGCONT)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        live = process_table()
        if not any(target in live and live[target][1] == table[target][1] for target in owned):
            break
        time.sleep(.05)
    for target in owned:
        send(target, signal.SIGKILL)
    if busy(lock):
        deadline = time.monotonic() + 2
        while busy(lock) and time.monotonic() < deadline:
            time.sleep(.05)
        if busy(lock):
            raise OrbeHelmError(f'Workspace still locked after stopping {row.id}')
    metadata = stored_runtime(store.root, row.runtime_path) / 'orbe.json'
    if metadata.exists():
        record = read_record(metadata)
        if record.get('status') == 'running':
            record.update(status='interrupted', exit_code=-signal.SIGTERM)
            metadata.write_text(json.dumps(record, indent=2) + '\n')
    with store.write() as db:
        for launch in db.scalars(select(OrbeLaunch).where(OrbeLaunch.orbe_id == row.id, OrbeLaunch.status == 'running')):
            launch.status, launch.ended_at, launch.exit_code = 'interrupted', now(), -signal.SIGTERM
    return {'id': row.id, 'status': 'closed'}


def close(store, project, orbe_id=None, all_sessions=False, global_scope=False):
    rows = selected(store, project, orbe_id, global_scope)
    if not (orbe_id or all_sessions or global_scope):
        rows = [row for row in rows if running(store, row)][:1]
    results = []
    for row in rows:
        try:
            results.append(stop(store, row))
        except (OrbeHelmError, OSError, ValueError) as error:
            results.append({'id': row.id, 'status': 'error', 'error': str(error)})
    return results


def prune(store, rows):
    """Remove native homes and launch metadata while retaining project knowledge."""
    for row in rows:
        stop(store, row)
    with ExitStack() as stack:
        # Keep launch locks held throughout deletion, preventing a concurrent resume.
        for path in sorted({lock_path(store.root, row) for row in rows}):
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink():
                raise OrbeHelmError('Session lock must not be a symlink')
            handle = stack.enter_context(path.open('a'))
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise OrbeHelmError('Session restarted during prune; retry') from error
        paths = [stored_runtime(store.root, row.runtime_path) for row in rows]
        import uuid
        staged = []
        try:
            # Quarantine homes before the transaction; failed database writes can
            # restore them instead of leaving rows that point at deleted files.
            for path in paths:
                if path.exists():
                    quarantine = path.with_name('.prune-' + uuid.uuid4().hex)
                    path.rename(quarantine)
                    staged.append((path, quarantine))
            with store.write() as db:
                for row in rows:
                    slot = db.get(OrbeSlot, row.slot_key)
                    if slot and slot.active_orbe == row.id:
                        slot.active_orbe = None
                    db.flush()
                    db.execute(delete(OrbeLaunch).where(OrbeLaunch.orbe_id == row.id))
                    db.execute(delete(Orbe).where(Orbe.id == row.id))
        except BaseException:
            for path, quarantine in reversed(staged):
                quarantine.rename(path)
            raise
        for row in rows:
            pointer = orbe_slot(store.root, row.slot_key) / 'active.json'
            if pointer.exists() and read_record(pointer).get('orbe_id') == row.id:
                pointer.unlink()
            runtime_child(store.root, 'processes', row.id + '.json').unlink(missing_ok=True)
        for _, quarantine in staged:
            shutil.rmtree(quarantine)
    return {'pruned': [row.id for row in rows], 'history_retained': True}

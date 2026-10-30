"""Best-effort capture of private native transcript events, never terminal scraping."""
from contextlib import contextmanager
import json
import sys
import threading

from .conversations import append, MAX_EVENT
from .core import digest


def message_text(event):
    message = event.get('message') or event.get('payload') or {}
    if not isinstance(message, dict):
        return ''
    if message.get('role') in {'system', 'developer'}:
        return ''
    content = message.get('content', '')
    if isinstance(content, list):
        content = '\n'.join(block.get('text', '') for block in content if isinstance(block, dict) and isinstance(block.get('text', ''), str))
    if not isinstance(content, str):
        return ''
    if content.startswith('<!-- orbehelm:handoff:v1 -->') and '<!-- /orbehelm:handoff -->' in content:
        content = content.split('<!-- /orbehelm:handoff -->', 1)[1].lstrip('\n')
    return content


@contextmanager
def capture(store, thread, runtime, agent, include_existing=True, memory_epoch=None):
    stop = threading.Event()
    positions = {}
    errors = []
    directories = {'claude': 'claude-home/projects', 'codex': 'codex-home/sessions'}

    def scan():
        if agent not in directories:
            return
        for path in sorted((runtime / directories[agent]).rglob('*.jsonl')):
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
                raise ValueError('Native transcript symlinks are unsupported')
            offset = positions.get(path, 0)
            if path.stat().st_size < offset:
                offset = 0
            with path.open('rb') as handle:
                handle.seek(offset)
                while True:
                    line = handle.readline(MAX_EVENT + 1)
                    if not line:
                        break
                    if len(line) > MAX_EVENT:
                        raise ValueError('Native transcript event exceeds the capture limit')
                    if not line.endswith(b'\n'):
                        break
                    offset = handle.tell()
                    try:
                        event = json.loads(line)
                    except (ValueError, UnicodeError):
                        raise ValueError('Native transcript contains malformed JSON')
                    if not isinstance(event, dict):
                        raise ValueError('Unsupported native transcript record')
                    text = message_text(event)
                    append(store, thread, 'native_message' if text else 'native_event', agent,
                           {'text': text, 'role': (event.get('message') or event.get('payload') or {}).get('role', event.get('type')),
                            'record': event, 'source': path.name, 'offset': offset,
                            **({'_memory_epoch': memory_epoch, '_memory_visibility': 'private'} if memory_epoch is not None else {})},
                           source_id=digest((str(path.resolve()) + ':' + str(offset) + ':' + digest(line)).encode()))
                    positions[path] = offset

    # Source IDs deduplicate history across restarts and explicit imports.
    try:
        if not include_existing and agent in directories:
            for path in (runtime / directories[agent]).rglob('*.jsonl'):
                if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
                    raise ValueError('Native transcript symlinks are unsupported')
                positions[path] = path.stat().st_size
        scan()
    except Exception as error:
        errors.append(str(error))

    def worker():
        try:
            while not stop.wait(.25):
                scan()
        except Exception as error:
            errors.append(str(error))

    append(store, thread, 'capture', agent, {'coverage': 'native-transcript-best-effort' if agent in directories else 'unsupported',
                                           'status': 'started'})
    if agent not in directories:
        print('oh: Native transcript capture is unsupported for this adapter; use managed Claude/Codex chat for structured history.', file=sys.stderr)
    task = threading.Thread(target=worker, name='orbehelm-transcript', daemon=True)
    task.start()
    try:
        yield {'errors': errors, 'coverage': 'native-transcript-best-effort' if agent in directories else 'unsupported'}
    finally:
        stop.set()
        task.join()
        if not errors:
            try:
                scan()
            except Exception as error:
                errors.append(str(error))
        append(store, thread, 'capture', agent, {'status': 'incomplete' if errors else 'finished',
                                               'errors': errors, 'files_observed': len(positions)})
        if errors:
            print('oh: Native history capture is incomplete; use conversations history to inspect capture status.', file=sys.stderr)

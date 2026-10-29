"""Read pre-rename metadata without moving runtime homes or changing snapshots."""
import json
from pathlib import Path

from .layout import runtime_base


LEGACY_MARKER = "<!-- agentic:sections:v1 -->"
LEGACY_SECTION_PREFIX = "<!-- agentic:sections"


def existing_path(root, current, previous):
    """Prefer the canonical name; reject ambiguity instead of splitting identities."""
    from .core import OrbeHelmError
    current, previous = Path(root) / current, Path(root) / previous
    has_current = current.exists() or current.is_symlink()
    has_previous = previous.exists() or previous.is_symlink()
    if has_current and has_previous:
        raise OrbeHelmError(f"Both {current.name} and {previous.name} exist; reconcile them before continuing")
    return previous if has_previous else current


def project_file(root):
    return existing_path(root, 'orbehelm.project.json', 'agentic.project.json')


def database_file(root):
    return existing_path(Path(root).resolve(), 'state/orbehelm.sqlite3', 'state/agentic.sqlite3')


def orbe_slot(root, key):
    return existing_path(runtime_base(root), f'orbe-keys/{key}', f'session-keys/{key}')


def orbe_directory(root, orbe_id):
    return existing_path(runtime_base(root), f'orbes/{orbe_id}', f'sessions/{orbe_id}')


def read_record(path):
    """Normalize the old wrapper's metadata keys in memory only."""
    data = json.loads(Path(path).read_text())
    for old, new in [('session_id', 'orbe_id'), ('logical_session_id', 'logical_orbe_id'),
                     ('session_key', 'orbe_key')]:
        if old in data:
            data.setdefault(new, data.pop(old))
    return data


def orbe_record(directory):
    """A resumed old home gains canonical metadata; its original record is retained."""
    directory = Path(directory)
    current = directory / 'orbe.json'
    previous = directory / 'session.json'
    return current if current.exists() or not previous.exists() else previous


def orbe_records(root):
    for name in ('orbes', 'sessions'):
        for directory in sorted((runtime_base(root) / name).glob('*')):
            record = orbe_record(directory)
            if record.is_file():
                yield record

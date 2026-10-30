"""Installed application layout; checkout-only use retains local runtime storage."""
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from .core import OrbeHelmError

INSTALLATION_FILE = 'installation.json'


def installation(root):
    path = Path(root) / INSTALLATION_FILE
    if path.is_symlink():
        raise OrbeHelmError('Installation metadata must not be a symlink')
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if (not isinstance(data, dict) or data.get('schema_version') != 1
                or data.get('application') != 'orbehelm'
                or not isinstance(data.get('orbes_home'), str)
                or not Path(data['orbes_home']).is_absolute()):
            raise ValueError('Invalid installation layout')
        return data
    except (OSError, ValueError, TypeError) as error:
        raise OrbeHelmError(f'Cannot read {path.name}; rerun setup.sh: {error}') from error


def runtime_base(root):
    data = installation(root)
    path = Path(data['orbes_home']) if data else Path(root) / 'state'
    if path.is_symlink():
        raise OrbeHelmError('The orbe storage directory must not be a symlink')
    return path


def auth_directory(root):
    return runtime_base(root) / 'auth' / 'codex'


def runtime_child(root, *parts):
    """Construct a runtime path without following user-created directory symlinks."""
    relative = Path(*parts)
    if relative.is_absolute() or '..' in relative.parts:
        raise OrbeHelmError('Invalid runtime path')
    path = runtime_base(root)
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise OrbeHelmError('Runtime directories must not be symlinks')
    return path


def stored_runtime(root, value):
    """Runtime homes may be external; generated build paths must still stay in root."""
    path = Path(value).resolve()
    base = runtime_base(root).resolve()
    if not any(path.is_relative_to(base / name) for name in ('orbes', 'sessions', 'conversations')):
        raise OrbeHelmError('Orbe runtime is outside this installation storage')
    return path


def server_url(root):
    data = installation(root) or {}
    url = os.environ.get('ORBEHELM_SERVER_URL') or data.get('server_url', 'http://127.0.0.1:8765')
    try:
        if not isinstance(url, str):
            raise ValueError('Expected a string')
        parsed = urlsplit(url)
        port = parsed.port if parsed.port is not None else 80
        if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}
                or parsed.username or parsed.password or parsed.path not in {'', '/'}
                or parsed.query or parsed.fragment or not 1 <= port <= 65535):
            raise ValueError('Expected a loopback HTTP URL without credentials or a path')
    except (ValueError, TypeError) as error:
        raise OrbeHelmError('Invalid OrbeHelm server URL; use http://127.0.0.1:<port>') from error
    return url.rstrip('/')


def identity(root):
    """Expose only hashes of storage locations on the public loopback readiness route."""
    def fingerprint(path):
        return hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()
    return {'root_id': fingerprint(root), 'runtime_id': fingerprint(runtime_base(root))}

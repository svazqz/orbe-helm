"""Form validation and readable listings for the shared capability registry."""
import json
from pathlib import Path
import re

from orbehelm.configuration import selections
from orbehelm.core import OrbeHelmError, contained, identifier, validate_mcp
from orbehelm.remote_skills import validate_url
from orbehelm.snapshots import verify_snapshot
from .catalog import latest, create_registration


def entries(store, kind, release=None):
    release = release or latest(store)
    source = verify_snapshot(store.root, release.snapshot)
    return [{'name': path.stem, 'config': json.loads(path.read_text()),
             'path': path.relative_to(source).as_posix()}
            for path in sorted((source / 'registry' / kind).glob('*.json'))]


def add_skill(store, form):
    name = identifier(form.get('name', '').strip())
    source = form.get('source', '').strip()
    if '://' in source:
        try:
            validate_url(source)
        except ValueError as error:
            raise OrbeHelmError('Enter a valid public HTTPS skill URL') from error
    else:
        path = Path(source)
        if path.parts[:2] != ('examples', 'skills') and path.parts[:1] != ('skills',):
            raise OrbeHelmError('Use a public HTTPS URL or a folder under skills/ or examples/skills/ in this checkout')
        resolved = contained(store.root, source).relative_to(store.root)
        if resolved.parts[:2] != ('examples', 'skills') and resolved.parts[:1] != ('skills',):
            raise OrbeHelmError('The skill folder must remain inside skills/ or examples/skills/')
    config = {'schema_version': 1, 'source': source,
              'skills': selections(form.get('skills', ''), 'Skill dependencies'),
              'mcp': selections(form.get('mcp', ''), 'MCP dependencies')}
    return create_registration(store, 'skills', name, config, form.get('expected_release'))


def add_mcp(store, form):
    name = identifier(form.get('name', '').strip())
    transport = form.get('transport')
    config = {'schema_version': 1, 'type': transport}
    if transport == 'http':
        from urllib.parse import urlsplit
        url = form.get('url', '').strip()
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError as error:
            raise OrbeHelmError('Enter a valid HTTP or HTTPS MCP endpoint') from error
        if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
                or re.search(r'\s', url) or port == 0):
            raise OrbeHelmError('Enter an HTTP or HTTPS server URL without credentials, query parameters, or a fragment')
        config['url'] = url
    elif transport == 'stdio':
        env = {}
        for line in form.get('environment', '').splitlines():
            if not line.strip():
                continue
            key, separator, value = line.strip().partition('=')
            key, value = key.strip(), value.strip()
            if not separator or key in env:
                raise OrbeHelmError('Environment entries must be unique SERVER_VARIABLE=HOST_VARIABLE names')
            env[key] = value
        config.update(command=form.get('command', '').strip(),
                      args=[line for line in form.get('arguments', '').splitlines() if line], env=env)
    validate_mcp(config, name)
    return create_registration(store, 'mcp', name, config, form.get('expected_release'))

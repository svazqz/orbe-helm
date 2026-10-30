"""Check a built wheel without site packages: python3 tests/check_wheel.py FILE.whl."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import subprocess
import sys
import tempfile
from zipfile import ZipFile

root = Path(__file__).resolve().parents[1]
verification = root / 'state/verification/wheel-smoke'
verification.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(dir=verification) as directory, ZipFile(sys.argv[1]) as archive:
    target = Path(directory)
    assert 'orbehelm/application.py' not in archive.namelist(), 'File/package collision'
    for member in archive.infolist():
        path = PurePosixPath(member.filename)
        assert not path.is_absolute() and '..' not in path.parts
    for relative, expected in json.loads((root / 'tests/fixtures/compatibility/migration-checksums.json').read_text()).items():
        assert hashlib.sha256(archive.read(relative.removeprefix('src/'))).hexdigest() == expected, relative
    archive.extractall(target)
    code = '''import sys
sys.path.insert(0, sys.argv[1])
from orbehelm.application import Application, Request
from orbehelm.application.use_cases.memory import MemoryService
from orbehelm.infrastructure.memory.sqlite import SQLiteMemory
from orbehelm.plugins.codex import Adapter as Codex
from orbehelm.plugins.claude import Adapter as Claude
from orbehelm.domain.definitions.composition import compose
assert compose([]) == '# Agent Instructions\\n'
for cls in (Codex, Claude):
    assert cls().stream_command('/fixture', 'workspace-write', 'prompt').stdin == 'prompt'
assert not any(name in sys.modules for name in ('sqlalchemy', 'fastapi', 'uvicorn'))
from orbehelm.cli import parser
assert parser().parse_args(['--agent', 'claude']).agent == 'claude'
'''
    subprocess.run([sys.executable, '-I', '-S', '-c', code, str(target)], check=True)
    metadata = next(target.glob('*.dist-info/METADATA')).read_text()
    for line in metadata.splitlines():
        if line.startswith('Requires-Dist:') and any(name in line.lower() for name in ('fastapi', 'jinja2', 'uvicorn')):
            assert 'extra ==' in line, line
        if line.startswith('Requires-Dist: fastembed'):
            assert 'extra == "memory"' in line, line
print('Wheel kernel, provider plugins, CLI parser, optional UI metadata, and frozen migration resources verified.')

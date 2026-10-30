"""Content identity of resolver/rendering code, separate from locked source inputs."""
from pathlib import Path
from ...domain.shared.values import digest


def implementation_hashes():
    package = Path(__file__).resolve().parents[2]
    files = {package / name for name in (
        'core.py', 'composition.py', 'adapters.py', 'remote_skills.py', 'snapshots.py',
        'plugin_registry.py', 'application/ports/agents.py',
        'infrastructure/filesystem/implementation.py')}
    for directory in ('domain', 'plugins'):
        files.update((package / directory).rglob('*.py'))
    return {path.relative_to(package).as_posix(): digest(path.read_bytes()) for path in sorted(files)}

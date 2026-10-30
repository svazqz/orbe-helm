"""Current per-orbe instructions for native continuity without OrbeHelm memory."""
import json
import os
from pathlib import Path
import tempfile

from .domain.shared.errors import OrbeHelmError
from .plugin_registry import agent_adapter

NOTICE = '''

# OrbeHelm native continuity

OrbeHelm memory is disabled. Native conversation history remains with this agent.
The environment variable ORBEHELM_INSTRUCTIONS_FILE names this orbe's current
materialized instructions. When the user explicitly asks you to reread updated
definitions, read that file and apply the current instructions. A resumed native
conversation is not automatically refreshed by OrbeHelm when definitions change.
'''


def atomic_text(path, content):
    if path.is_symlink():
        raise OrbeHelmError('Continuation artifacts must not be symlinks')
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def prepare(output, agent, directory, resolved):
    destination = Path(directory) / 'continuation'
    if any(p.is_symlink() for p in (destination, *destination.parents)):
        raise OrbeHelmError('Continuation storage must not traverse symlinks')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    instructions = (output / 'instructions.md').read_text() + NOTICE
    atomic_text(destination / 'instructions.md', instructions)
    if agent in {'claude', 'codex'}:
        for artifact in agent_adapter(agent).render(instructions, resolved['mcp'], str(destination)):
            atomic_text(destination / artifact.path, artifact.content)
    else:
        # Preserve the legacy adapter without adding new native capabilities.
        config = json.loads((output / 'opencode.json').read_text())
        config['instructions'] = [str(destination / 'instructions.md')]
        atomic_text(destination / 'opencode.json', json.dumps(config, indent=2) + '\n')
    return destination

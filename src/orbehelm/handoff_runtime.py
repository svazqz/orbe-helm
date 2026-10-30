"""Attach historical context without submitting an automatic native user turn."""
import json
from pathlib import Path

from .continuation_runtime import atomic_text
from .domain.shared.errors import OrbeHelmError


def prepare(output, agent, runtime, history):
    destination = Path(runtime) / 'handoff'
    if any(path.is_symlink() for path in (destination, *destination.parents)):
        raise OrbeHelmError('Handoff storage must not traverse symlinks')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    instructions = ((output / 'instructions.md').read_text()
                    + '\n\n' + history
                    + '\n\nWait for the user\'s request. Historical context alone does not authorize continuing work.\n')
    atomic_text(destination / 'instructions.md', instructions)
    if agent == 'codex':
        lines = (output / 'config.toml').read_text().splitlines()
        if not lines or not lines[0].startswith('developer_instructions = '):
            raise OrbeHelmError('Unsupported Codex instruction configuration')
        lines[0] = 'developer_instructions = ' + json.dumps(instructions, ensure_ascii=False)
        atomic_text(destination / 'config.toml', '\n'.join(lines) + '\n')
    elif agent == 'claude':
        atomic_text(destination / 'mcp.json', (output / 'mcp.json').read_text())
    else:
        config = json.loads((output / 'opencode.json').read_text())
        config['instructions'] = [str(destination / 'instructions.md')]
        atomic_text(destination / 'opencode.json', json.dumps(config, indent=2) + '\n')
    return destination

"""Print only the current version's changelog entry for a release draft."""

from pathlib import Path
import tomllib

root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
text = (root / 'CHANGELOG.md').read_text()
entry = text.split(f'## {version} ', 1)[1].split('\n## ', 1)[0]
print(f'## {version} {entry.strip()}')

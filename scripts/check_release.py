"""Validate release metadata without changing Git, installations or remote services."""

import argparse
import ast
from pathlib import Path
import re
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def locked_requirements(text: str, filename: str) -> dict[str, str]:
    """Require one exact pin and SHA256 hashes for every logical requirement."""
    requirements: dict[str, str] = {}
    logical = ''
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        continued = line.endswith('\\')
        logical += ' ' + (line[:-1].strip() if continued else line)
        if continued:
            continue
        tokens = logical.split()
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([^\s;]+)', tokens[0])
        if (
            match is None
            or len(tokens) < 2
            or any(re.fullmatch(r'--hash=sha256:[a-f0-9]{64}', token) is None for token in tokens[1:])
        ):
            raise ValueError(
                'Every generated dependency requires an exact pin and SHA256 hashes: ' + filename
            )
        name, version = match.groups()
        name = name.lower().replace('_', '-')
        if name in requirements:
            raise ValueError('Duplicate generated dependency: ' + name)
        requirements[name] = version
        logical = ''
    if logical or not requirements:
        raise ValueError('Incomplete generated dependency lock: ' + filename)
    return requirements


def validate(root: Path, tag: str | None = None) -> str:
    metadata = tomllib.loads((root / 'pyproject.toml').read_text())
    version = metadata['project']['version']
    tree = ast.parse((root / 'src/orbehelm/__init__.py').read_text())
    runtime = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == '__version__' for target in node.targets)
    )
    if runtime != version:
        raise ValueError('Package and runtime versions differ')
    if f'## {version} ' not in (root / 'CHANGELOG.md').read_text():
        raise ValueError('Version is missing from CHANGELOG.md')
    if f'`{version}`' not in (root / 'README.md').read_text():
        raise ValueError('README release version differs')
    match = re.fullmatch(r'(\d+\.\d+\.\d+)(?:(a|b|rc)(\d+))?', version)
    if match is None:
        raise ValueError('Unsupported release version')
    base, phase, number = match.groups()
    expected = 'v' + base + (f'-{dict(a="alpha", b="beta", rc="rc")[phase]}.{number}' if phase else '')
    if tag is not None and tag != expected:
        raise ValueError(f'Tag must be {expected}')
    pins = {}
    for line in (root / 'requirements.lock').read_text().splitlines():
        if line and not line.startswith('#'):
            name, separator, value = line.partition('==')
            if not separator or name in pins:
                raise ValueError('Runtime requirements must contain unique exact pins')
            pins[name.lower().replace('_', '-')] = value
    for line in (root / 'requirements-core.lock').read_text().splitlines():
        if line and not line.startswith('#'):
            name, _, value = line.partition('==')
            if pins.get(name.lower().replace('_', '-')) != value:
                raise ValueError('Core/runtime dependency pins differ')
    for filename in ('requirements-runtime.lock', 'requirements-dev.lock', 'requirements-memory.lock'):
        text = (root / filename).read_text()
        normalized = locked_requirements(text, filename)
        if any(normalized.get(name) != value for name, value in pins.items()):
            raise ValueError('Generated dependency pins differ: ' + filename)
    return version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag')
    parser.add_argument('--clean', action='store_true', help='require a clean committed release tree')
    args = parser.parse_args()
    try:
        version = validate(ROOT, args.tag)
        changelog = (ROOT / 'CHANGELOG.md').read_text()
        if args.clean and '## Unreleased' in changelog:
            pending = changelog.split('## Unreleased', 1)[1].split('\n## ', 1)[0].strip()
            if pending:
                raise ValueError('Resolve Unreleased changes into a new version before tagging')
        if (
            args.clean
            and subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()
        ):
            raise ValueError('Release tree contains uncommitted files')
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Release check failed: {error}\n')
    print(f'Release metadata verified: {version}')


if __name__ == '__main__':
    main()

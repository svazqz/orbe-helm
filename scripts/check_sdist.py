"""Reject incomplete source archives and leaked runtime/test-temporary files."""

from pathlib import Path, PurePosixPath
import sys
import tarfile


def validate(path: Path) -> None:
    with tarfile.open(path) as archive:
        names = set()
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or member.issym() or member.islnk():
                raise ValueError('Unsafe archive member: ' + member.name)
            relative = PurePosixPath(*name.parts[1:])
            if set(relative.parts) & {'state', 'legacy', '.venv', '.git', '__pycache__'}:
                raise ValueError('Runtime/legacy data in source archive: ' + member.name)
            if (
                len(relative.parts) > 1
                and relative.parts[0] == 'tests'
                and relative.parts[1].startswith('tmp')
            ):
                raise ValueError('Temporary test fixture in source archive: ' + member.name)
            names.add(str(relative))
        required = {
            'oh',
            'setup.sh',
            'update.sh',
            'pyproject.toml',
            'src/orbehelm/installer.py',
            'definitions/base/instructions.md',
            'scripts/dev.py',
            'requirements-dev.lock',
            'requirements.lock',
            'requirements-core.lock',
            'requirements-runtime.lock',
            'requirements-memory.lock',
            'README.md',
            'CHANGELOG.md',
        }
        missing = required - names
        if missing:
            raise ValueError('Incomplete source archive: ' + ', '.join(sorted(missing)))
    print('Source archive includes installer/definitions and excludes runtime/temporary data.')


if __name__ == '__main__':
    validate(Path(sys.argv[1]))

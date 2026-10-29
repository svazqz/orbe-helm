"""Install an application copy, private runtime storage, and an idempotent PATH block."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orbehelm.core import OrbeHelmError
from orbehelm import __version__
from orbehelm.layout import INSTALLATION_FILE, installation
from orbehelm.service import server_status

START = '# >>> OrbeHelm PATH >>>'
END = '# <<< OrbeHelm PATH <<<'
BUNDLED_DIRECTORIES = ('definitions', 'registry', 'examples', 'skills')


def startup_files(home, shell):
    name = Path(shell).name
    if name == 'zsh':
        return [Path(os.environ.get('ZDOTDIR') or home) / '.zshrc']
    if name == 'fish':
        return [Path(os.environ.get('XDG_CONFIG_HOME') or home / '.config') / 'fish/config.fish']
    if name == 'bash':
        files = [home / '.bashrc']
        login = next((home / n for n in ('.bash_profile', '.bash_login', '.profile')
                      if (home / n).exists()), None)
        if login:
            files.append(login)
        elif sys.platform == 'darwin':
            files.append(home / '.bash_profile')
        return files
    return [home / '.profile']


def path_block(directory, shell):
    quoted = shlex.quote(str(directory))
    if Path(shell).name == 'fish':
        # Fish single-quoted strings escape only backslashes and single quotes.
        quoted = "'" + str(directory).replace('\\', '\\\\').replace("'", "\\'") + "'"
        statement = f'fish_add_path --prepend -- {quoted}'
    else:
        statement = f'export PATH={quoted}:"$PATH"'
    return START + '\n' + statement + '\n' + END


def update_startup(path, block, backup_dir):
    previous = path.read_text() if path.exists() else ''
    if previous.count(START) != previous.count(END) or previous.count(START) > 1:
        raise OrbeHelmError(f'Unbalanced OrbeHelm PATH block in {path}; fix it or use --no-path')
    if START in previous:
        start, end = previous.index(START), previous.index(END) + len(END)
        if end < start:
            raise OrbeHelmError(f'Invalid OrbeHelm PATH block in {path}')
        updated = previous[:start] + block + previous[end:]
    else:
        updated = previous + ('\n' if previous and not previous.endswith('\n') else '') + '\n' + block + '\n'
    if updated == previous:
        return
    if path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = backup_dir / (path.name + '-' + uuid.uuid4().hex)
        backup.write_text(previous)
        backup.chmod(0o600)
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = target.stat().st_mode & 0o777 if target.exists() else 0o600
    with tempfile.NamedTemporaryFile(mode='w', dir=target.parent, prefix='.orbehelm-rc-', delete=False) as handle:
        staged = Path(handle.name)
        handle.write(updated)
    try:
        staged.chmod(mode)
        staged.replace(target)
    finally:
        staged.unlink(missing_ok=True)


def write_manifest(root, data):
    temporary = root / (INSTALLATION_FILE + '.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(root / INSTALLATION_FILE)


def bundled_digest(path):
    executable = b'1' if path.stat().st_mode & 0o111 else b'0'
    return hashlib.sha256(path.read_bytes() + b'\0' + executable).hexdigest()


def sync_bundled_sources(source, root, previous):
    """Refresh unchanged bundled files while retaining locally authored sources."""
    baseline = previous.get('bundled_sources', {}) if previous else {}
    current = {}
    preserved = []
    for directory in BUNDLED_DIRECTORIES:
        for path in sorted((source / directory).rglob('*')):
            if path.is_symlink():
                raise OrbeHelmError(f'Bundled sources must not contain symlinks: {path}')
            if not path.is_file() or path.name == '.DS_Store' or '__pycache__' in path.parts:
                continue
            relative = path.relative_to(source).as_posix()
            checksum = bundled_digest(path)
            current[relative] = checksum
            target = root / relative
            if any(parent.is_symlink() for parent in (target, *target.parents)):
                raise OrbeHelmError(f'Installed source must not traverse symlinks: {relative}')
            if not target.exists():
                # A missing previously bundled file may be a deliberate local deletion.
                if relative in baseline:
                    preserved.append(relative)
                    continue
            elif not target.is_file():
                raise OrbeHelmError(f'Installed source is not a file: {relative}')
            else:
                installed_hash = bundled_digest(target)
                if installed_hash == checksum:
                    continue
                if installed_hash != baseline.get(relative):
                    preserved.append(relative)
                    continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    for relative, checksum in baseline.items():
        if relative in current:
            continue
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] not in BUNDLED_DIRECTORIES:
            raise OrbeHelmError('Invalid bundled source path in installation metadata')
        target = root / path
        if any(parent.is_symlink() for parent in (target, *target.parents)):
            raise OrbeHelmError(f'Installed source must not traverse symlinks: {relative}')
        if target.is_file():
            if bundled_digest(target) == checksum:
                target.unlink()
            else:
                preserved.append(relative)
    for relative in preserved:
        print(f'Preserved local source (review upstream changes): {relative}')
    return current


def copy_application(source, root, previous=None):
    package = root / 'src/orbehelm'
    package.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix='.setup-') as temporary:
        staged = Path(temporary) / 'orbehelm'
        shutil.copytree(source / 'src/orbehelm', staged,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        if package.is_symlink():
            raise OrbeHelmError('Installed source package must not be a symlink')
        if package.exists():
            shutil.rmtree(package)
        staged.rename(package)
    bundled = sync_bundled_sources(source, root, previous)
    for name in ('README.md', 'requirements.lock'):
        shutil.copy2(source / name, root / name)
    if (source / 'docs').is_dir():
        shutil.copytree(source / 'docs', root / 'docs', dirs_exist_ok=True)
    return bundled


def install(args):
    if sys.platform not in {'darwin', 'linux'}:
        raise OrbeHelmError('The installer supports macOS and Linux')
    if importlib.util.find_spec('venv') is None or importlib.util.find_spec('ensurepip') is None:
        raise OrbeHelmError('Python venv/ensurepip is missing. Install python3-venv on Debian/Ubuntu, '
                            'or a complete Python 3.11+ distribution, then rerun setup.sh.')
    source = Path(__file__).resolve().parents[2]
    home = Path.home()
    destination = Path(args.install_dir).expanduser()
    previous = installation(destination)
    if args.update and previous is None:
        raise OrbeHelmError(f'{destination} is not an existing installation; run setup.sh first')
    orbes = Path(args.orbes_dir or (previous or {}).get('orbes_home') or home / '.orbehelm').expanduser()
    port = args.port
    if port is None:
        from urllib.parse import urlsplit
        port = urlsplit(previous['server_url']).port if previous else 8765
    if destination.is_symlink() or orbes.is_symlink():
        raise OrbeHelmError('Installation and orbe-home directories must not be symlinks')
    root, orbes = destination.resolve(), orbes.resolve()
    copied_trees = [source / name for name in ('src', *BUNDLED_DIRECTORIES)]
    if (root == source or orbes == source or orbes == root or orbes.is_relative_to(root)
            or root.is_relative_to(orbes)
            or any(path.is_relative_to(tree) for tree in copied_trees for path in (root, orbes))):
        raise OrbeHelmError('Use separate application and orbe-home directories, outside the source root itself')
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise OrbeHelmError('Server port must be between 1 and 65535')
    if root.exists() and any(root.iterdir()) and previous is None:
        raise OrbeHelmError(f'{root} is not an OrbeHelm installation; select an empty directory')
    if previous and Path(previous['orbes_home']).resolve() != orbes:
        raise OrbeHelmError('The existing installation uses another orbe home; retain it to preserve runtime identity')
    if previous and server_status(root).get('reachable'):
        raise OrbeHelmError('A server is using this installation address; stop it before reinstalling')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    orbes.mkdir(parents=True, exist_ok=True, mode=0o700)
    orbes.chmod(0o700)
    for relative in ('orbes', 'orbe-keys', 'auth'):
        target = orbes / relative
        if target.is_symlink():
            raise OrbeHelmError(f'{target} must not be a symlink')
        target.mkdir(exist_ok=True, mode=0o700)
    for relative in ('src', 'bin', 'state'):
        if (root / relative).is_symlink():
            raise OrbeHelmError(f'{root / relative} must not be a symlink')
        (root / relative).mkdir(exist_ok=True, mode=0o700)
    data = {'schema_version': 1, 'application': 'orbehelm', 'orbes_home': str(orbes),
            'server_url': f'http://127.0.0.1:{port}', 'complete': False,
            'version': __version__, 'bundled_sources': (previous or {}).get('bundled_sources', {})}
    write_manifest(root, data)
    data['bundled_sources'] = copy_application(source, root, previous)
    # Save the new baseline before migrations so an interrupted install is retryable.
    write_manifest(root, data)
    environment = root / '.venv'
    if environment.is_symlink():
        raise OrbeHelmError('The application virtual environment must not be a symlink')
    python = environment / 'bin/python3'
    if not python.exists():
        try:
            subprocess.run([sys.executable, '-m', 'venv', str(environment)], check=True)
        except subprocess.CalledProcessError as error:
            raise OrbeHelmError('Could not create the virtual environment. Install python3-venv '
                                'or a complete Python distribution and rerun setup.sh.') from error
    subprocess.run([str(python), '-c', 'import sys; assert sys.version_info >= (3, 11); import pip'], check=True)
    dependencies = [str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                    '-r', str(root / 'requirements.lock')]
    if args.offline:
        dependencies.append('--no-index')
    subprocess.run(dependencies, check=True)
    subprocess.run([str(python), '-c', 'import fastapi, sqlalchemy, alembic, jinja2, uvicorn'], check=True)
    (root / 'bin').mkdir(exist_ok=True)
    launcher = root / 'bin/oh'
    if launcher.is_symlink():
        raise OrbeHelmError('The installed launcher must not be a symlink')
    launcher.write_text('#!/bin/sh\nset -eu\n' +
        'export ORBEHELM_ROOT=' + shlex.quote(str(root)) + '\n' +
        'exec ' + shlex.quote(str(python)) + ' ' +
        shlex.quote(str(root / 'src/orbehelm/_entry.py')) + ' "$@"\n')
    launcher.chmod(0o755)
    # Import defaults only from this installation during setup, never a personal rc file.
    empty_config = root / 'state/setup.ini'
    empty_config.write_text('[ORBEHELM]\n')
    subprocess.run([str(launcher), 'migrate', '--config', str(empty_config)], check=True)
    data['complete'] = True
    write_manifest(root, data)
    shell = args.shell or os.environ.get('SHELL') or '/bin/sh'
    paths = [] if args.no_path or args.update else startup_files(home, shell)
    block = path_block(root / 'bin', shell)
    for path in paths:
        update_startup(path, block, root / 'state/setup-backups')
    print(f'\nOrbeHelm {__version__} {"updated" if args.update else "installed"} in {root}')
    print(f'Orbe homes: {orbes / "orbes"}')
    if paths:
        print('PATH updated in: ' + ', '.join(str(p) for p in paths))
        print('Open a new terminal, or run: ' + block.splitlines()[1])
    else:
        print('Add to PATH: ' + block.splitlines()[1])
    print(f'Start the server manually: {shlex.quote(str(launcher))} server start')
    print(f'Then run: oh --project=/path/to/project --unique-key=TASK-1')
    print('Install and authenticate Codex, Claude, or OpenCode separately before real model work.')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Install OrbeHelm from this clone without sudo.')
    parser.add_argument('--install-dir', default=str(Path.home() / 'bin/orbehelm'))
    parser.add_argument('--orbes-dir', help='runtime storage; defaults to the existing location or ~/.orbehelm')
    parser.add_argument('--shell', help='shell whose startup file receives PATH (bash, zsh, fish, sh)')
    parser.add_argument('--port', type=int, help='server port; defaults to the existing port or 8765')
    parser.add_argument('--update', action='store_true', help='require an existing installation and leave shell startup unchanged')
    parser.add_argument('--offline', action='store_true', help='use pip --no-index; dependencies must already be available')
    parser.add_argument('--no-path', action='store_true', help='leave shell startup files unchanged')
    try:
        install(parser.parse_args(argv))
        return 0
    except (OrbeHelmError, OSError, subprocess.CalledProcessError) as error:
        print(f'setup.sh: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

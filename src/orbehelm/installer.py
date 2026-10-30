"""Install an application copy, private runtime storage, and an idempotent PATH block."""
import argparse
import fcntl
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
    for name in ('README.md', 'CHANGELOG.md', 'requirements.lock', 'requirements-core.lock', 'requirements-runtime.lock', 'requirements-memory.lock'):
        shutil.copy2(source / name, root / name)
    if (source / 'docs').is_dir():
        shutil.copytree(source / 'docs', root / 'docs', dirs_exist_ok=True)
    return bundled


def bundled_state(root):
    """Fingerprint editable installed inputs without treating Finder/caches as source."""
    files = {}
    for name in BUNDLED_DIRECTORIES:
        directory = root / name
        for path in (directory, *directory.rglob('*')):
            if path.is_symlink():
                raise OrbeHelmError('Installed bundled sources must not contain symlinks')
            if path.is_file() and path.name != '.DS_Store' and '__pycache__' not in path.parts:
                files[path.relative_to(root).as_posix()] = bundled_digest(path)
    return files


def prepare_candidate(source, root, previous, data, offline):
    """Leave the active source, environment and manifest untouched during preparation."""
    releases = root / 'state/installations'
    if releases.is_symlink():
        raise OrbeHelmError('Installation staging directory must not be a symlink')
    releases.mkdir(exist_ok=True, mode=0o700)
    release = releases / uuid.uuid4().hex
    release.mkdir(mode=0o700)
    candidate = release / 'candidate'
    candidate.mkdir()
    prepared_state = bundled_state(root)
    # Merge into a private copy so local customizations are preserved before activation.
    for name in BUNDLED_DIRECTORIES:
        installed = root / name
        if installed.exists():
            if any(path.is_symlink() for path in (installed, *installed.rglob('*'))):
                raise OrbeHelmError('Installed bundled sources must not contain symlinks')
            shutil.copytree(installed, candidate / name)
    if bundled_state(root) != prepared_state:
        raise OrbeHelmError('Bundled sources changed during preparation; retry the update')
    (release / 'source-state.json').write_text(json.dumps(prepared_state))
    data['bundled_sources'] = copy_application(source, candidate, previous)
    environment = release / 'venv'
    python = environment / 'bin/python3'
    try:
        subprocess.run([sys.executable, '-m', 'venv', str(environment)], check=True)
        dependencies = [str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                        '-r', str(candidate / ('requirements-memory.lock' if data['memory_extra'] else 'requirements-runtime.lock'))]
        if offline:
            dependencies.append('--no-index')
        subprocess.run(dependencies, check=True)
        subprocess.run([str(python), '-m', 'pip', 'check'], check=True)
        imports = ('import fastapi, sqlalchemy, alembic, jinja2, uvicorn; '
                   + ('import fastembed; ' if data['memory_extra'] else '')
                   + 'from orbehelm import __version__; '
                   + 'from orbehelm.cli import parser; '
                   + 'assert __version__ == ' + repr(data['version']) + '; parser()')
        subprocess.run([str(python), '-c', 'import sys; sys.path.insert(0, '
                        + repr(str(candidate / 'src')) + '); ' + imports], check=True)
        subprocess.run([str(python), str(candidate / 'src/orbehelm/_entry.py'), '--version'], check=True)
    except (OSError, subprocess.CalledProcessError):
        # Nothing active references a failed candidate. Keep successful releases only.
        shutil.rmtree(release)
        raise
    return candidate, python


def activate_candidate(root, candidate, python, data, previous):
    """Journal file activation; never imply an automatic database downgrade is safe."""
    backup = candidate.parent / 'previous'
    backup.mkdir(mode=0o700)
    names = ['src', *BUNDLED_DIRECTORIES, 'docs', 'README.md', 'CHANGELOG.md',
             'requirements.lock', 'requirements-core.lock', 'requirements-runtime.lock', 'requirements-memory.lock',
             'bin/oh', INSTALLATION_FILE]
    for name in names:
        if (root / name).is_symlink():
            raise OrbeHelmError('Activation target must not be a symlink: ' + name)
    migration_started = False
    moved, activated = [], []
    lock = root / 'state/install.lock'
    if lock.is_symlink():
        raise OrbeHelmError('Installation lock must not be a symlink')
    with lock.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        if installation(root) != previous:
            raise OrbeHelmError('Installation changed during preparation; retry the update')
        prepared_state = json.loads((candidate.parent / 'source-state.json').read_text())
        if bundled_state(root) != prepared_state:
            raise OrbeHelmError('Bundled sources changed during preparation; retry the update')
        journal = candidate.parent / 'activation.json'
        def record(phase):
            journal.write_text(json.dumps({'phase': phase, 'moved': moved, 'activated': activated,
                                          'root': str(root), 'backup': str(backup)}, indent=2) + '\n')
            journal.chmod(0o600)
        try:
            record('activating')
            # The incomplete marker prevents launches during the multi-file switch.
            if (root / INSTALLATION_FILE).exists():
                shutil.copy2(root / INSTALLATION_FILE, backup / INSTALLATION_FILE)
            write_manifest(root, {**data, 'recovery_directory': str(backup)})
            for name in names:
                if name == INSTALLATION_FILE:
                    continue
                target = root / name
                old = backup / name
                if target.exists():
                    old.parent.mkdir(parents=True, exist_ok=True)
                    target.rename(old)
                    moved.append(name)
                    record('activating')
                if (candidate / name).exists():
                    (candidate / name).rename(target)
                    activated.append(name)
                    record('activating')
            launcher = root / 'bin/oh'
            launcher.write_text('#!/bin/sh\nset -eu\n' +
                'export ORBEHELM_ROOT=' + shlex.quote(str(root)) + '\n' +
                'exec ' + shlex.quote(str(python)) + ' ' +
                shlex.quote(str(root / 'src/orbehelm/_entry.py')) + ' "$@"\n')
            launcher.chmod(0o755)
            activated.append('bin/oh')
            empty_config = root / 'state/setup.ini'
            empty_config.write_text('[ORBEHELM]\n')
            record('migrating')
            migration_started = True
            subprocess.run([str(launcher), 'migrate', '--config', str(empty_config)], check=True)
            data['complete'] = True
            data['environment'] = str(python.parent.parent)
            data['recovery_directory'] = str(backup)
            write_manifest(root, data)
            record('complete')
        except (OSError, subprocess.CalledProcessError, OrbeHelmError):
            if migration_started:
                # Migrations create a DB backup. Old code must not run on a changed schema.
                write_manifest(root, {**data, 'complete': False, 'recovery_directory': str(backup)})
                record('migration-failed')
                print(f'Update incomplete; retained code/environment: {backup}. '
                      'Rerun update or restore a compatible database and application backup; '
                      'see docs/installation.md.', file=sys.stderr)
            else:
                for name in reversed(activated):
                    target = root / name
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink(missing_ok=True)
                for name in reversed(moved):
                    (backup / name).rename(root / name)
                if previous is None:
                    (root / INSTALLATION_FILE).unlink(missing_ok=True)
                else:
                    write_manifest(root, previous)
                record('rolled-back')
            raise


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
    data['memory_extra'] = args.memory or (previous or {}).get('memory_extra', False)
    if (root / '.venv').is_symlink():
        raise OrbeHelmError('The application virtual environment must not be a symlink')
    candidate, python = prepare_candidate(source, root, previous, data, args.offline)
    launcher = root / 'bin/oh'
    activate_candidate(root, candidate, python, data, previous)
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
    print('Run: oh chat --agent=claude --project=/path/to/project --unique-key=TASK-1')
    print(f'Optional shared-definition editor: {shlex.quote(str(launcher))} web')
    print('Install and authenticate Codex, Claude, or OpenCode separately before real model work.')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Install OrbeHelm from this clone without sudo.')
    parser.add_argument('--install-dir', default=str(Path.home() / 'bin/orbehelm'))
    parser.add_argument('--orbes-dir', help='runtime storage; defaults to the existing location or ~/.orbehelm')
    parser.add_argument('--shell', help='shell whose startup file receives PATH (bash, zsh, fish, sh)')
    parser.add_argument('--port', type=int, help='server port; defaults to the existing port or 8765')
    parser.add_argument('--update', action='store_true', help='require an existing installation and leave shell startup unchanged')
    parser.add_argument('--offline', action='store_true', help='use pip --no-index; dependencies must already be available')
    parser.add_argument('--memory', action='store_true', help='install the optional local embedding runtime; model download remains explicit')
    parser.add_argument('--no-path', action='store_true', help='leave shell startup files unchanged')
    try:
        install(parser.parse_args(argv))
        return 0
    except (OrbeHelmError, OSError, subprocess.CalledProcessError) as error:
        print(f'setup.sh: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

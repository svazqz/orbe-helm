"""Project-local contributor checks: bootstrap, fast, check, release, memory, audit."""

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'state/verification/development'


def run(*args: str) -> None:
    temporary = ROOT / 'state/tool-cache/tmp'
    temporary.mkdir(parents=True, exist_ok=True)
    environment = {
        **os.environ,
        'TMPDIR': str(temporary),
        'PIP_CACHE_DIR': str(ROOT / 'state/tool-cache/pip'),
        'PIP_TOOLS_CACHE_DIR': str(ROOT / 'state/tool-cache/pip-tools'),
    }
    subprocess.run(args, cwd=ROOT, env=environment, check=True)


def fast() -> None:
    run(sys.executable, '-I', '-S', 'tests/run_kernel.py')
    run(
        sys.executable,
        '-m',
        'ruff',
        'check',
        'scripts',
        'src/orbehelm/installer.py',
        'src/orbehelm/application/commands.py',
        'src/orbehelm/application/results.py',
        'src/orbehelm/application/ports/agents.py',
    )
    run(sys.executable, '-m', 'ruff', 'format', '--check', 'scripts')
    run(sys.executable, '-m', 'mypy')
    run(sys.executable, 'scripts/check_release.py')
    run('sh', '-n', 'setup.sh', 'update.sh')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'command', choices=['bootstrap', 'fast', 'check', 'release', 'memory', 'audit', 'package']
    )
    args = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if args.command == 'bootstrap':
        python = ROOT / '.venv/bin/python'
        if not python.exists():
            run(sys.executable, '-m', 'venv', str(ROOT / '.venv'))
        run(str(python), '-m', 'pip', 'install', '-r', 'requirements-dev.lock')
        return
    if args.command == 'audit':
        run(
            sys.executable,
            '-m',
            'pip_audit',
            '-r',
            'requirements-dev.lock',
            '-r',
            'requirements-memory.lock',
            '--no-deps',
            '--disable-pip',
            '--format=json',
            '--output',
            str(EVIDENCE / 'dependency-audit.json'),
        )
        return
    if args.command == 'memory':
        if os.environ.get('ORBEHELM_MEMORY_BINDING'):
            parser.error(
                'Run the isolated optional model integration from an operator terminal, outside an agent binding'
            )
        run(sys.executable, 'tests/check_embedding_model.py')
        run(sys.executable, 'tests/check_memory_cli.py')
        return
    fast()
    if args.command == 'package':
        package()
        return
    if args.command == 'fast':
        return
    run(sys.executable, '-m', 'pip', 'check')
    run(sys.executable, '-m', 'coverage', 'run', '-m', 'unittest', 'discover', '-s', 'tests', '-v')
    run(sys.executable, '-m', 'coverage', 'report')
    run(sys.executable, '-m', 'coverage', 'json', '-o', str(EVIDENCE / 'coverage.json'))
    if args.command == 'release':
        package()


def package() -> None:
    wheels = EVIDENCE / 'wheels'
    wheels.mkdir(exist_ok=True)
    # A fresh directory prevents accidentally validating a wheel from an older run.
    import tempfile

    with tempfile.TemporaryDirectory(dir=wheels) as directory:
        run(sys.executable, '-m', 'build', '--outdir', directory)
        wheel = next(Path(directory).glob('*.whl'))
        run(sys.executable, 'tests/check_wheel.py', str(wheel))
        source_archive = next(Path(directory).glob('*.tar.gz'))
        run(sys.executable, 'scripts/check_sdist.py', str(source_archive))
        import shutil

        for artifact in sorted(Path(directory).iterdir()):
            shutil.copy2(artifact, wheels / artifact.name)
        checksums = ''.join(
            f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n'
            for path in sorted(Path(directory).iterdir())
        )
        (wheels / 'SHA256SUMS').write_text(checksums)
    print('Local release artifacts prepared; no tag or release was published.')


if __name__ == '__main__':
    main()

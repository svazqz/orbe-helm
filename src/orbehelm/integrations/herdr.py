"""Optional display metadata for the Herdr pane hosting an interactive agent."""
from contextlib import contextmanager
import os
import shutil
import subprocess
import sys


def agent_label(profile, unique_key=None, spec=None):
    return ' - '.join(str(value) for value in (profile, unique_key, spec) if value)


def integration_status():
    inside = os.environ.get('HERDR_ENV') == '1'
    pane = os.environ.get('HERDR_PANE_ID')
    binary = os.environ.get('HERDR_BIN_PATH') or shutil.which('herdr')
    result = {'integration': 'herdr', 'inside': inside, 'pane': pane,
            'binary': binary, 'socket_available': bool(os.environ.get('HERDR_SOCKET_PATH')),
            'ready': bool(inside and pane and binary),
            'label_api': 'pane report-metadata --display-agent',
            'coverage': 'Display metadata only; native lifecycle state is owned by Herdr.'}
    if binary:
        try:
            version = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=2, check=False)
            help_result = subprocess.run([binary, 'pane', 'report-metadata', '--help'],
                                         capture_output=True, text=True, timeout=2, check=False)
            supported = help_result.returncode == 0 and '--display-agent' in help_result.stdout and '--title' in help_result.stdout
            result.update(version=version.stdout.strip()[:120], metadata_supported=supported)
            result['ready'] = result['ready'] and supported
        except (OSError, subprocess.TimeoutExpired):
            result.update(ready=False, metadata_supported=False, detail='Owner binary could not be queried.')
    return result


@contextmanager
def display_label(agent, label, enabled=True):
    pane = os.environ.get('HERDR_PANE_ID')
    executable = (os.environ.get('HERDR_BIN_PATH') or shutil.which('herdr')) if enabled and os.environ.get('HERDR_ENV') == '1' and pane else None
    if not executable:
        if enabled and os.environ.get('HERDR_ENV') == '1':
            print('oh: Herdr label skipped; run oh doctor --integration=herdr to inspect pane and binary discovery.', file=sys.stderr)
        yield
        return

    def report(*options):
        try:
            result = subprocess.run([executable, 'pane', 'report-metadata', pane,
                '--source', 'orbehelm:display', *options],
                capture_output=True, timeout=2, check=False)
            if result.returncode:
                print('oh: Herdr display label could not be updated; check your Herdr version.', file=sys.stderr)
        except (OSError, subprocess.TimeoutExpired):
            print('oh: Herdr display label unavailable; continuing agent launch.', file=sys.stderr)

    report('--display-agent', label, '--title', label)
    try:
        yield
    finally:
        report('--clear-display-agent', '--clear-title')

"""Optional display metadata for the Herdr pane hosting an interactive agent."""
from contextlib import contextmanager
import os
import shutil
import subprocess
import sys


def agent_label(profile, unique_key=None, spec=None):
    return ' - '.join(str(value) for value in (profile, unique_key, spec) if value)


@contextmanager
def display_label(agent, label, enabled=True):
    pane = os.environ.get('HERDR_PANE_ID')
    executable = shutil.which('herdr') if enabled and os.environ.get('HERDR_ENV') == '1' and pane else None
    if not executable:
        yield
        return

    def report(*options):
        try:
            result = subprocess.run([executable, 'pane', 'report-metadata', pane,
                '--source', 'orbehelm:display', '--agent', agent, *options],
                capture_output=True, timeout=2, check=False)
            if result.returncode:
                print('oh: Herdr display label could not be updated; check your Herdr version.', file=sys.stderr)
        except (OSError, subprocess.TimeoutExpired):
            print('oh: Herdr display label unavailable; continuing agent launch.', file=sys.stderr)

    report('--display-agent', label)
    try:
        yield
    finally:
        report('--clear-display-agent')

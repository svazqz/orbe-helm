"""Run pure domain/application tests with: python3 -I -S tests/run_kernel.py."""
from pathlib import Path
import sys
import unittest
from contextlib import ExitStack
from unittest.mock import patch
import socket
import subprocess
import os

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))
suite = unittest.TestSuite()
for package in ['domain', 'application']:
    directory = root / 'tests' / package
    if directory.is_dir():
        suite.addTests(unittest.defaultTestLoader.discover(str(directory), top_level_dir=str(root / 'tests')))
def forbidden(*args, **kwargs):
    raise AssertionError('Independent kernel attempted an undeclared external effect')


class NoEnvironment(dict):
    __getitem__ = get = __iter__ = keys = values = items = forbidden


# Import/discovery are complete. Business workflows must use supplied values/ports.
with ExitStack() as guards:
    for target in ['builtins.open', 'io.open', 'os.open', 'socket.socket', 'socket.create_connection',
                   'subprocess.Popen', 'subprocess.run', 'os.system', 'os.getenv']:
        guards.enter_context(patch(target, side_effect=forbidden))
    guards.enter_context(patch.object(os, 'environ', NoEnvironment()))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())

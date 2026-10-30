"""Owned process-group execution; no native-agent command construction."""
import os
import signal
import subprocess
import threading
import time
from ...domain.shared.errors import OrbeHelmError


def run_child(args, cwd, env, cancel=None, timeout=300, on_start=None):
    cancel = cancel or threading.Event()
    if cancel.is_set():
        raise OrbeHelmError('Delegation cancelled')
    process = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        if on_start:
            on_start(process.pid)
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            if cancel.wait(.1):
                raise OrbeHelmError('Delegation cancelled')
            if time.monotonic() >= deadline:
                raise OrbeHelmError('Delegation timed out; no result was approved')
        if cancel.is_set():
            raise OrbeHelmError('Delegation cancelled')
        return process.returncode
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()

"""Process birth identity tracking without provider-specific commands."""
import json
import os
from pathlib import Path
import subprocess
from subprocess import Popen as SystemProcess
from ...domain.shared.errors import OrbeHelmError


def process_table():
    with SystemProcess(['ps', '-axo', 'pid=,ppid=,lstart='], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True) as process:
        output, _ = process.communicate()
        if process.returncode:
            raise OrbeHelmError('Cannot inspect process identities')
    table = {}
    for line in output.splitlines():
        fields = line.split(None, 2)
        if len(fields) == 3:
            table[int(fields[0])] = (int(fields[1]), fields[2])
    return table


def remember_process(directory, orbe_id):
    pid = os.getpid()
    identity = process_table().get(pid)
    if identity is None:
        raise OrbeHelmError('Cannot establish launcher process identity')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (orbe_id + '.json')
    if directory.is_symlink() or path.is_symlink():
        raise OrbeHelmError('Process metadata must not be a symlink')
    temporary = path.with_suffix('.tmp')
    if temporary.is_symlink():
        raise OrbeHelmError('Process metadata must not be a symlink')
    temporary.write_text(json.dumps({'pid': pid, 'started': identity[1]}))
    temporary.replace(path)

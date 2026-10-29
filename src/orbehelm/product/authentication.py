"""Bounded, cancellable host-native OAuth commands. No model or shell execution."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import uuid

from orbehelm.core import OrbeHelmError, identifier
from .models import now


def login_command(agent, runtime, output, server):
    identifier(server)
    runtime, output = Path(runtime), Path(output)
    env = os.environ.copy()
    if agent == 'codex':
        env['CODEX_HOME'] = str(runtime / 'codex-home')
        command = ['codex', 'mcp', 'login', server]
    elif agent == 'claude':
        env['CLAUDE_CONFIG_DIR'] = str(runtime / 'claude-home')
        command = ['claude', '--strict-mcp-config', '--mcp-config', str(output / 'mcp.json'),
                   '--setting-sources', '', 'mcp', 'login', server]
    elif agent == 'opencode':
        env.update(OPENCODE_CONFIG_CONTENT=json.dumps(json.loads((output / 'opencode.json').read_text())),
                   XDG_DATA_HOME=str(runtime / 'data'), XDG_STATE_HOME=str(runtime / 'state'),
                   XDG_CACHE_HOME=str(runtime / 'cache'))
        command = ['opencode', 'mcp', 'auth', server]
    else:
        raise OrbeHelmError('This agent has no MCP sign-in adapter')
    return command, env


def unavailable(agent, runtime, transport):
    if transport != 'http':
        return 'Local servers use their configured environment variables rather than browser sign-in.'
    if not runtime:
        return 'Launch or resume this agent with the current project configuration, then return here to sign in.'
    if not shutil.which(agent):
        return f'Install {agent} on this computer to use its sign-in command.'
    return None


@dataclass
class LoginJob:
    id: str
    project_id: str
    agent: str
    server: str
    runtime: str
    process: subprocess.Popen = field(repr=False)
    state: str = 'waiting'
    started_at: str = field(default_factory=now)
    cancelled: bool = False
    selection: str | None = None

    def public(self):
        return {key: getattr(self, key) for key in
                ('id', 'project_id', 'agent', 'server', 'state', 'started_at', 'selection')}


class LoginManager:
    """A UI instance owns its login children; shutdown terminates unfinished jobs."""
    def __init__(self, timeout=180):
        self.timeout = timeout
        self.jobs = {}
        self.lock = threading.Lock()
        self.closed = False

    def start(self, project, agent, server, runtime, output, selection=None):
        with self.lock:
            if self.closed:
                raise OrbeHelmError('The web application is shutting down')
            for job in self.jobs.values():
                if (job.project_id, job.agent, job.server, job.runtime, job.state) == (
                        project.id, agent, server, str(runtime), 'waiting'):
                    return job.public()
            if len(self.jobs) >= 64:
                self.jobs = {key: job for key, job in self.jobs.items() if job.state == 'waiting'}
                if len(self.jobs) >= 64:
                    raise OrbeHelmError('Too many sign-ins are already waiting. Cancel one before continuing.')
            command, env = login_command(agent, runtime, output, server)
            try:
                process = subprocess.Popen(command, cwd=project.path, env=env,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
            except OSError as error:
                raise OrbeHelmError('Unable to start the agent sign-in command. Check that its CLI is installed.') from error
            job = LoginJob(uuid.uuid4().hex, project.id, agent, server, str(runtime), process, selection=selection)
            self.jobs[job.id] = job
            threading.Thread(target=self._wait, args=(job,), daemon=True).start()
            return job.public()

    @staticmethod
    def _stop(process):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def _wait(self, job):
        try:
            result = job.process.wait(timeout=self.timeout)
            state = 'completed' if result == 0 else 'failed'
        except subprocess.TimeoutExpired:
            self._stop(job.process)
            job.process.wait()
            state = 'expired'
        with self.lock:
            job.state = 'cancelled' if job.cancelled else state

    def get(self, project_id, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job.project_id != project_id:
                raise OrbeHelmError('Sign-in not found. It may have ended when the web application restarted.')
            return job.public()

    def cancel(self, project_id, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job.project_id != project_id:
                raise OrbeHelmError('Sign-in not found')
            if job.state == 'waiting':
                job.cancelled = True
                self._stop(job.process)
            return job.public()

    def close(self):
        with self.lock:
            self.closed = True
            for job in self.jobs.values():
                if job.state == 'waiting':
                    job.cancelled = True
                    self._stop(job.process)

"""Translate a portable configuration without changing global agent settings."""
import json
import hashlib
import fcntl
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import uuid
import sys
import signal
import threading
import time
from contextlib import contextmanager

from .core import OrbeHelmError
from .layout import auth_directory
from .service import require_server
from .herdr import agent_label, display_label
from .compatibility import orbe_directory, orbe_slot, orbe_record, read_record

AGENTS = ("codex", "claude", "opencode")
LIMITATION = ("Alpha does not guarantee exclusive context: project, managed, built-in, or global "
              "instructions and skills may still be loaded by the host. Selected skills are "
              "inlined with resource paths, not installed as native host plugins.")


def mcp_authentication(agent, runtime, project, servers):
    """Read host-reported metadata only; never inspect or return credential material."""
    unknown = {name: {'status': 'Unknown', 'detail': 'Authentication has not been verified.'}
               for name in servers}
    if not servers:
        return unknown
    if agent != 'codex':
        return {name: {'status': 'Unknown', 'detail':
            f'{agent} does not yet have a supported authentication status adapter.'} for name in servers}
    if runtime is None:
        return {name: {'status': 'Unknown', 'detail': 'Launch this selection with this agent before checking.'}
                for name in servers}
    env = os.environ.copy()
    env['CODEX_HOME'] = str(Path(runtime) / 'codex-home')
    try:
        result = subprocess.run(['codex', 'mcp', 'list', '--json'], cwd=project, env=env,
                                capture_output=True, text=True, timeout=15, check=False)
        if result.returncode != 0:
            return unknown
        rows = json.loads(result.stdout)
        if not isinstance(rows, list):
            return unknown
        states = {'oauth': ('Authenticated', 'Codex reports an OAuth login; server access was not tested.'),
                  'bearer_token': ('Credential configured', 'Codex reports a bearer token; validity was not tested.'),
                  'not_logged_in': ('Not authenticated', 'Codex reports no login.'),
                  'unsupported': ('Unsupported', 'Codex cannot report authentication for this server.')}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('name'), str):
                continue
            if row['name'] in unknown:
                expected = servers[row['name']]
                transport = row.get('transport')
                if not isinstance(transport, dict):
                    continue
                if expected['type'] == 'http':
                    matches = transport.get('url') == expected['url']
                else:
                    matches = (transport.get('command') == expected['command']
                               and transport.get('args', []) == expected.get('args', []))
                if not matches:
                    continue
                state = row.get('auth_status')
                status, detail = states.get(state if isinstance(state, str) else None,
                    ('Unknown', 'Codex did not establish authentication status.'))
                if row.get('enabled') is False:
                    status, detail = 'Disabled', 'The selected host reports this server as disabled.'
                unknown[row['name']] = {'status': status, 'detail': detail}
    except (OSError, subprocess.TimeoutExpired, ValueError, UnicodeError):
        pass
    return unknown


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def render(staged, final, resolved, agent):
    def toml_value(value):
        return json.dumps(value, ensure_ascii=False)

    servers = resolved["mcp"]
    instructions = str(final / "instructions.md")
    if agent == "codex":
        # JSON quoted strings are valid TOML basic strings for these generated values.
        lines = ["developer_instructions = " + toml_value((staged / "instructions.md").read_text()),
                 'cli_auth_credentials_store = "file"']
        for name, server in servers.items():
            lines += [f"\n[mcp_servers.{name}]"]
            if server["type"] == "http":
                lines += ["url = " + toml_value(server["url"])]
            else:
                if any(k != v for k, v in server.get("env", {}).items()):
                    raise OrbeHelmError("Codex alpha requires identical MCP and host env variable names")
                lines += ["command = " + toml_value(server["command"]),
                          "args = " + toml_value(server.get("args", [])),
                          "env_vars = " + toml_value(list(server.get("env", {})))]
        (staged / "config.toml").write_text("\n".join(lines) + "\n")
    elif agent == "claude":
        converted = {}
        for name, server in servers.items():
            if server["type"] == "http":
                converted[name] = {"type": "http", "url": server["url"]}
            else:
                converted[name] = {"command": server["command"], "args": server.get("args", []),
                    "env": {k: "${" + v + "}" for k, v in server.get("env", {}).items()}}
        write_json(staged / "mcp.json", {"mcpServers": converted})
    elif agent == "opencode":
        converted = {}
        for name, server in servers.items():
            if server["type"] == "http":
                converted[name] = {"type": "remote", "url": server["url"], "enabled": True}
            else:
                converted[name] = {"type": "local", "command": [server["command"], *server.get("args", [])],
                    "environment": {k: "{env:" + v + "}" for k, v in server.get("env", {}).items()}, "enabled": True}
        write_json(staged / "opencode.json", {"$schema": "https://opencode.ai/config.json",
                   "instructions": [instructions], "mcp": converted})
    write_json(staged / "capabilities.json", {"agent": agent, "exclusive_context": False,
        "skill_delivery": "inline instructions and copied resources", "limitation": LIMITATION,
        "mcp_strategy": {"codex": "dedicated CODEX_HOME; project and managed policy may apply",
                         "claude": "strict MCP config; managed policy may apply",
                         "opencode": "runtime config merged with host config"}[agent]})


def command(output, agent, prompt=None):
    if agent == "codex":
        args = ["codex", "--no-daemon"]
    elif agent == "claude":
        args = ["claude", "--append-system-prompt-file", str(output / "instructions.md"),
                "--strict-mcp-config", "--mcp-config", str(output / "mcp.json"),
                "--setting-sources", ""]
    else:
        args = ["opencode"]
        if prompt:
            args += ["--prompt", prompt]
            return args
    if prompt:
        args.append(prompt)
    return args


def doctor(resolved, agent):
    checks = [{"name": agent, "ok": bool(shutil.which(agent)), "detail": shutil.which(agent)}]
    for name, server in resolved["mcp"].items():
        if server["type"] == "stdio":
            executable = server["command"]
            checks.append({"name": f"mcp:{name}:command", "ok": bool(shutil.which(executable)), "detail": executable})
        for host_var in server.get("env", {}).values():
            checks.append({"name": f"mcp:{name}:env:{host_var}", "ok": bool(os.environ.get(host_var)),
                           "detail": "value is never printed"})
    return {"agent": agent, "ok": all(c["ok"] for c in checks), "checks": checks,
            "exclusive_context": False, "limitation": LIMITATION}


def launch_environment(root, output, agent, directory):
    """Prepare only wrapper-specific environment values, never expose inherited values."""
    if agent == "codex":
        home = directory / "codex-home"
        home.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output / "config.toml", home / "config.toml")
        credential = auth_directory(root) / "auth.json"
        if credential.is_file() and not (home / "auth.json").is_symlink():
            (home / "auth.json").symlink_to(credential)
        return {"CODEX_HOME": str(home)}
    if agent == "opencode":
        config = json.loads((output / "opencode.json").read_text())
        return {"OPENCODE_CONFIG_CONTENT": json.dumps(config, separators=(",", ":")),
                "XDG_DATA_HOME": str(directory / "data"),
                "XDG_STATE_HOME": str(directory / "state"),
                "XDG_CACHE_HOME": str(directory / "cache")}
    if agent == "claude":
        return {"CLAUDE_CONFIG_DIR": str(directory / "claude-home")}
    return {}


def orbe_identity(resolved, agent, unique_key=None):
    identity = {"agent": agent, "project": str(Path(resolved["project"]).resolve()),
                "profile": resolved["profile"], "spec": resolved["spec"] or None}
    if unique_key is not None:
        from .product.coordination import unique_key as validate_key
        identity['unique_key'] = validate_key(unique_key)
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return identity, key


def active_orbe(root, pointer):
    try:
        orbe_id = read_record(pointer)["orbe_id"]
        if not isinstance(orbe_id, str) or uuid.UUID(orbe_id).hex != orbe_id:
            raise ValueError("Expected a canonical orbe UUID")
    except (KeyError, TypeError, ValueError) as error:
        raise OrbeHelmError(f"Invalid orbe identity in {pointer}") from error
    return orbe_directory(root, orbe_id)


def can_resume(orbe, agent, record):
    if agent == "codex":
        return any((orbe / "codex-home/sessions").glob("**/*.jsonl"))
    if agent == "claude":
        return any((orbe / "claude-home/projects").glob("**/*.jsonl"))
    return record.get("resumable", False)


def resume_command(args, agent):
    if agent == "codex":
        args[2:2] = ["resume", "--last"]
    else:
        args[1:1] = ["--continue"]
    return args


def child_command(output, agent, profile, prompt):
    if agent == 'codex':
        return ['codex', '--no-daemon', 'exec', '--skip-git-repo-check', '--sandbox',
                'read-only' if profile == 'reviewer' else 'workspace-write', prompt]
    if agent == 'claude':
        return ['claude', '--print', '--append-system-prompt-file', str(output / 'instructions.md'),
                '--strict-mcp-config', '--mcp-config', str(output / 'mcp.json'), '--setting-sources', '', prompt]
    if agent == 'opencode':
        return ['opencode', 'run', prompt]
    raise OrbeHelmError('No headless adapter for this agent')


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


@contextmanager
def workspace_writer(root, workspace, enabled):
    if not enabled:
        yield
        return
    from .product.coordination import safe_path
    path = safe_path(root, 'state/workspace-locks/' + hashlib.sha256(str(workspace).encode()).hexdigest())
    path.mkdir(parents=True, exist_ok=True)
    with (path / 'writer.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise OrbeHelmError('Another keyed developer is using this workspace. Select a separate --workspace.') from error
        yield


def launch(root, output, resolved, agent, prompt=None, dry_run=False, strict=False, new_orbe=False,
           unique_key=None, actor_id=None, delegation_id=None, workspace=None, headless=False,
           cancel=None, timeout=300, on_start=None):
    if strict:
        raise OrbeHelmError("Strict isolation is not available in alpha. " + LIMITATION)
    identity, key = orbe_identity(resolved, agent, unique_key)
    build_output = output
    workspace = str(Path(workspace or resolved['project']).resolve())
    pointer = orbe_slot(root, key) / "active.json"
    args = command(output, agent, prompt)
    if dry_run:
        existing = active_orbe(root, pointer) if pointer.exists() and not new_orbe else None
        if existing is not None:
            record_path = orbe_record(existing)
            record = read_record(record_path) if record_path.exists() else {}
            if can_resume(existing, agent, record):
                args = resume_command(args, agent)
        invocation = shlex.join(args)
        if agent == "codex":
            invocation = shlex.join(["env", f"CODEX_HOME={existing / 'codex-home' if existing else output}", *args])
        elif agent == "opencode":
            config = shlex.quote(str(output / "opencode.json"))
            invocation = f'env OPENCODE_CONFIG_CONTENT="$(cat {config})" {invocation}'
        if existing is not None and agent == "claude":
            invocation = shlex.join(["env", f"CLAUDE_CONFIG_DIR={existing / 'claude-home'}", *args])
        elif existing is not None and agent == "opencode":
            values = [f"XDG_{kind.upper()}_HOME={existing / kind}" for kind in ("data", "state", "cache")]
            invocation = "env " + shlex.join(values) + " " + invocation
        return f"cd {shlex.quote(resolved['project'])} && {invocation}"
    require_server(root)
    health = doctor(resolved, agent)
    if not health["ok"]:
        failed = [c["name"] for c in health["checks"] if not c["ok"]]
        raise OrbeHelmError("Missing prerequisites: " + ", ".join(failed))
    slot = orbe_slot(root, key)
    slot.mkdir(parents=True, exist_ok=True)
    # Hold the lock for the child lifetime; process exit releases stale locks automatically.
    with workspace_writer(root, workspace, actor_id is not None and resolved['profile'] == 'developer' and not headless), \
            (slot / "launch.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise OrbeHelmError("This orbe is already running") from error
        pointer = slot / "active.json"
        if pointer.exists() and not new_orbe:
            orbe = active_orbe(root, pointer)
        else:
            orbe = orbe_directory(root, uuid.uuid4().hex)
        orbe_id = orbe.name
        orbe.mkdir(parents=True, exist_ok=True)
        record_path = orbe / "orbe.json"
        previous_path = orbe_record(orbe)
        previous = read_record(previous_path) if previous_path.exists() else {}
        env = dict(os.environ)
        coordination = None
        if actor_id:
            from .coordination_runtime import prepare_runtime
            output, coordination = prepare_runtime(root, output, agent, orbe, actor_id, delegation_id)
        env.update(launch_environment(root, output, agent, orbe))
        # Always replace inherited metadata, including an absent specialization.
        env.update({"ORBEHELM_ORBE_ID": orbe_id,
                    "ORBEHELM_ORBE_DIR": str(orbe.resolve()),
                    "ORBEHELM_PROFILE": identity["profile"],
                    "ORBEHELM_SPECIALIZATION": identity["spec"] or "",
                    "ORBEHELM_PROJECT": identity["project"],
                    "ORBEHELM_AGENT_LABEL": agent_label(identity['profile'], unique_key, identity['spec'])})
        if coordination:
            env.update({'ORBEHELM_TASK_ID': coordination['task_id'], 'ORBEHELM_LOGICAL_ORBE_ID': actor_id,
                        'ORBEHELM_UNIQUE_KEY': coordination['unique_key'],
                        'ORBEHELM_ORBE_KEY': coordination['orbe_key'],
                        'ORBEHELM_DELEGATION_ID': delegation_id or ''})
        resume = not headless and can_resume(orbe, agent, previous)
        args = child_command(output, agent, resolved['profile'], prompt) if headless else command(output, agent, prompt)
        if resume:
            args = resume_command(args, agent)
        record = {"schema_version": 1, **identity, "orbe_id": orbe_id,
                  "build": str(build_output), "cwd": workspace, "status": "starting",
                  "launch_count": previous.get("launch_count", 0) + 1,
                  "resumable": resume}
        if coordination:
            record.update(task_id=coordination['task_id'], logical_orbe_id=actor_id,
                          root_unique_key=coordination['unique_key'], delegation_id=delegation_id)
        # Do not persist the prompt or environment values in orbe records.
        write_json(record_path, record)
        temporary = slot / "active.tmp"
        write_json(temporary, {"orbe_id": orbe_id})
        temporary.replace(pointer)
        product_store = None
        product_launch = None
        if resolved.get("project_id"):
            from .product.database import Store
            from .product.orbes import begin_launch
            product_store = Store(root)
            try:
                product_launch = begin_launch(product_store, resolved, agent, orbe_id, orbe, key,
                                              unique_key=unique_key or '')
            except Exception:
                product_store.close()
                raise
        print("oh: " + LIMITATION, file=sys.stderr)
        try:
            record["status"] = "running"
            write_json(record_path, record)
            if headless:
                code = run_child(args, workspace, env, cancel, timeout, on_start)
            else:
                with display_label(agent, env['ORBEHELM_AGENT_LABEL']):
                    code = subprocess.call(args, cwd=workspace, env=env)
            record.update(status="exited", exit_code=code, resumable=resume or code == 0)
        except KeyboardInterrupt:
            code = 130
            record.update(status="interrupted", exit_code=code)
        except OSError as error:
            record.update(status="failed", error=str(error))
            raise OrbeHelmError(str(error)) from error
        except OrbeHelmError:
            record.update(status='failed')
            raise
        finally:
            try:
                write_json(record_path, record)
                if product_store is not None:
                    from .product.orbes import finish_launch
                    finish_launch(product_store, product_launch, record)
            finally:
                if product_store is not None:
                    product_store.close()
        return code


def authenticate(root, agent):
    """Run the host login flow explicitly, in the wrapper's own credential store."""
    if agent != "codex":
        raise OrbeHelmError("Alpha auth command supports Codex only; authenticate other agents with their own CLI")
    if not shutil.which("codex"):
        raise OrbeHelmError("codex executable not found")
    home = auth_directory(root)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    home.chmod(0o700)
    (home / "config.toml").write_text('cli_auth_credentials_store = "file"\n')
    env = dict(os.environ)
    env["CODEX_HOME"] = str(home)
    return subprocess.call(["codex", "login"], env=env)

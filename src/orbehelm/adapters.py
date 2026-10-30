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
import re
import time
from contextlib import contextmanager, ExitStack

from .core import OrbeHelmError
from .plugin_registry import agent_adapter
from .domain.coordination.policies import execution_access
from .layout import auth_directory
from .service import require_server
from .herdr import agent_label, display_label
from .sessions import policy_digest
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
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            handle.write(json.dumps(value, indent=2) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def render(staged, final, resolved, agent):
    servers = resolved["mcp"]
    instructions = str(final / "instructions.md")
    if agent in {"codex", "claude"}:
        for artifact in agent_adapter(agent).render((staged / "instructions.md").read_text(), servers, str(final)):
            (staged / artifact.path).write_text(artifact.content)
    elif agent == "opencode":
        converted = {}
        for name, server in servers.items():
            if server["type"] == "http":
                converted[name] = {"type": "remote", "url": server["url"], "enabled": True}
            else:
                converted[name] = {"type": "local", "command": [server["command"], *server.get("args", [])],
                    "environment": {k: "{env:" + v + "}" for k, v in server.get("env", {}).items()}, "enabled": True}
        write_json(staged / "opencode.json", {"$schema": "https://opencode.ai/config.json",
                   "instructions": [instructions], "mcp": converted, "permission": "allow"})
    write_json(staged / "capabilities.json", {"agent": agent, "exclusive_context": False,
        "skill_delivery": "inline instructions and copied resources", "limitation": LIMITATION,
        "mcp_strategy": {"codex": "dedicated CODEX_HOME; project and managed policy may apply",
                         "claude": "strict MCP config; managed policy may apply",
                         "opencode": "runtime config merged with host config"}[agent]})


def command(output, agent, prompt=None):
    if agent in {"codex", "claude"}:
        return list(agent_adapter(agent).command(str(output), prompt).argv)
    return ["opencode"] + (["--prompt", prompt] if prompt else [])


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
        configuration = home / 'config.toml'
        if configuration.is_symlink():
            raise OrbeHelmError('Native configuration must not be a symlink')
        generated = (output / 'config.toml').read_text()
        # Trust is native host state, not a generated definition. Preserve its
        # exact TOML sections instead of resetting it at every wrapper launch.
        if configuration.exists():
            previous = configuration.read_text()
            sections = re.split(r'(?m)(?=^\[)', previous)
            generated += ''.join(section for section in sections
                                 if re.match(r'^\[projects[.\]]', section))
        configuration.write_text(generated)
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
        from .domain.coordination.policies import unique_key as validate_key
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
    if not record.get('native_session_id') or not record.get('resumable'):
        return False
    if agent == "codex":
        return any((orbe / "codex-home/sessions").glob("**/*.jsonl"))
    if agent == "claude":
        return any((orbe / "claude-home/projects").glob("**/*.jsonl"))
    return record.get("resumable", False)


def resume_command(args, agent, session_id=None):
    if agent in {'codex', 'claude'}:
        args[:] = agent_adapter(agent).resume_command(args, session_id)
    else:
        args[1:1] = ['--resume', session_id] if session_id else ['--continue']
    return args


def discover_native_session(runtime, agent, after_ns=0):
    directory = runtime / ('codex-home/sessions' if agent == 'codex' else 'claude-home/projects')
    if agent not in {'codex', 'claude'}:
        return None
    candidates = []
    for path in directory.rglob('*.jsonl'):
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents) or 'subagents' in path.parts:
            continue
        try:
            if path.stat().st_mtime_ns < after_ns:
                continue
            if agent == 'claude':
                value = str(uuid.UUID(path.stem))
                with path.open(encoding='utf-8') as handle:
                    initial = json.loads(handle.readline(65536))
                if initial.get('isSidechain'):
                    continue
            else:
                with path.open(encoding='utf-8') as handle:
                    event = json.loads(handle.readline(65536))
                if event.get('type') != 'session_meta':
                    continue
                if isinstance(event.get('payload', {}).get('source'), dict):
                    continue
                value = str(uuid.UUID(event['payload']['id']))
            candidates.append((path.stat().st_mtime_ns, value))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    identifiers = {item[1] for item in candidates}
    return next(iter(identifiers)) if len(identifiers) == 1 else None


def child_command(output, agent, profile, prompt):
    if agent in {'codex', 'claude'}:
        return list(agent_adapter(agent).child_command(str(output), execution_access(profile), prompt).argv)
    if agent == 'opencode':
        return ['opencode', 'run', prompt]
    raise OrbeHelmError('No headless adapter for this agent')


from .infrastructure.process.runner import run_child


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
            raise OrbeHelmError('Another developer is already running in this workspace. Select a separate --workspace.') from error
        yield


def launch(root, output, resolved, agent, prompt=None, dry_run=False, strict=False, new_orbe=False,
           unique_key=None, actor_id=None, delegation_id=None, workspace=None, headless=False,
           cancel=None, timeout=300, on_start=None, new_session=False, memory_enabled=True,
           memory_factory=None, memory_visibility=None):
    if strict:
        raise OrbeHelmError("Strict isolation is not available in alpha. " + LIMITATION)
    identity, key = orbe_identity(resolved, agent, unique_key)
    policy = hashlib.sha256(json.dumps({'rules': policy_digest(resolved),
        'execution': 'full-access', 'knowledge_protocol': 2 if memory_enabled else 0}, sort_keys=True).encode()).hexdigest()
    build_output = output
    workspace = str(Path(workspace or resolved['project']).resolve())
    pointer = orbe_slot(root, key) / "active.json"
    args = command(output, agent, prompt)
    if dry_run:
        existing = active_orbe(root, pointer) if pointer.exists() and not new_orbe else None
        if existing is not None:
            record_path = orbe_record(existing)
            record = read_record(record_path) if record_path.exists() else {}
            recorded_home = Path(record.get('native_runtime', existing)).resolve()
            if not recorded_home.is_relative_to(existing.resolve()):
                raise OrbeHelmError('Native conversation runtime escapes its orbe')
            if not new_session and (not memory_enabled or (record.get('policy_digest') == policy and record.get('memory_enabled', True))) and can_resume(recorded_home, agent, record):
                args = resume_command(args, agent, record['native_session_id'])
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
    if agent == 'opencode' and not headless:
        raise OrbeHelmError('OpenCode cannot yet verify recorded native-session resume. Use Codex or Claude for persistent orbes; OpenCode remains available for builds and one-shot delegation.')
    require_server(root)
    health = doctor(resolved, agent)
    if not health["ok"]:
        failed = [c["name"] for c in health["checks"] if not c["ok"]]
        raise OrbeHelmError("Missing prerequisites: " + ", ".join(failed))
    slot = orbe_slot(root, key)
    slot.mkdir(parents=True, exist_ok=True)
    # Hold the lock for the child lifetime; process exit releases stale locks automatically.
    with workspace_writer(root, workspace, resolved['profile'] == 'developer' and not headless), \
            (slot / "launch.lock").open("a") as lock, ExitStack() as resources:
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
        runtime = orbe
        if previous.get('native_runtime'):
            runtime = Path(previous['native_runtime']).resolve()
            if not runtime.is_relative_to(orbe.resolve()):
                raise OrbeHelmError('Native conversation runtime escapes its orbe')
        fresh_policy = bool(previous) and memory_enabled and (previous.get('policy_digest') != policy or previous.get('memory_enabled', True) is False)
        if fresh_policy or new_session:
            print('oh: Starting a fresh native conversation; prior history and OrbeHelm memory are retained.', file=sys.stderr)
        runtime.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        coordination = None
        if actor_id and memory_enabled:
            from .coordination_runtime import prepare_runtime
            output, coordination = prepare_runtime(root, output, agent, runtime, actor_id, delegation_id)
        if not memory_enabled:
            from .continuation_runtime import prepare
            output = prepare(output, agent, runtime, resolved)
            print('oh: Memory disabled; native history continues. Reread ORBEHELM_INSTRUCTIONS_FILE after definition changes.', file=sys.stderr)
            env['ORBEHELM_INSTRUCTIONS_FILE'] = str((output / 'instructions.md').resolve())
        env.pop('ORBEHELM_MEMORY_BINDING', None)
        env.pop('ORBEHELM_MEMORY_OWNER', None)
        env['ORBEHELM_MEMORY_MODE'] = 'on' if memory_enabled else 'off'
        # Always replace inherited metadata, including an absent specialization.
        env.update({"ORBEHELM_ORBE_ID": orbe_id,
                    "ORBEHELM_ORBE_DIR": str(orbe.resolve()),
                    "ORBEHELM_PROFILE": identity["profile"],
                    "ORBEHELM_SPECIALIZATION": identity["spec"] or "",
                    "ORBEHELM_PROJECT": identity["project"],
                    "ORBEHELM_CONVERSATION_ID": '',
                    "ORBEHELM_AGENT_LABEL": agent_label(identity['profile'], unique_key, identity['spec'])})
        if coordination:
            env.update({'ORBEHELM_TASK_ID': coordination['task_id'], 'ORBEHELM_LOGICAL_ORBE_ID': actor_id,
                        'ORBEHELM_UNIQUE_KEY': coordination['unique_key'],
                        'ORBEHELM_ORBE_KEY': coordination['orbe_key'],
                        'ORBEHELM_DELEGATION_ID': delegation_id or ''})
        resume = not headless and not new_session and not fresh_policy and can_resume(runtime, agent, previous)
        memory_store = None
        knowledge_epoch = None
        memory_context = {}
        thread = None
        if memory_enabled and resolved.get('project_id') and (not headless or memory_factory):
            from .product.database import Store
            from .conversations import conversation, bootstrap
            memory_store = Store(root)
            resources.callback(memory_store.close)
            thread = conversation(memory_store, resolved['project_id'], resolved['profile'], resolved.get('spec'), unique_key)
            env['ORBEHELM_CONVERSATION_ID'] = thread
            if memory_factory:
                output, binding, memory_context = resources.enter_context(memory_factory(memory_store, output, agent,
                    runtime, thread, resolved['project_id'], memory_visibility, previous, resume))
                knowledge_epoch = memory_context['epoch']
                env['ORBEHELM_MEMORY_BINDING'] = str(binding)
                env['ORBEHELM_MEMORY_OWNER'] = thread
                if previous and (previous.get('knowledge_epoch') != knowledge_epoch or
                                 previous.get('memory_visibility') != memory_context['visibility']):
                    resume, fresh_policy = False, True
            if not resume and not headless:
                if previous and previous.get('memory_enabled', True):
                    from .native_capture import capture
                    prior = Path(previous.get('native_runtime', orbe)).resolve()
                    if not prior.is_relative_to(orbe.resolve()):
                        raise OrbeHelmError('Native conversation runtime escapes its orbe')
                    with capture(memory_store, thread, prior, agent, memory_epoch=previous.get('knowledge_epoch')) as coverage:
                        pass
                    if coverage['errors'] and fresh_policy:
                        raise OrbeHelmError('Policy refresh stopped because native transcript capture is incomplete; inspect conversations history before continuing with managed chat.')
                prompt = ('<!-- orbehelm:handoff:v1 -->\n' + bootstrap(memory_store, thread, memory_epoch=knowledge_epoch,
                    memory_visibility=memory_context.get('visibility'))
                          + '\n<!-- /orbehelm:handoff -->\n'
                          + (prompt or 'Continue the recorded work, or ask the user what to do next.'))
        env.update(launch_environment(root, output, agent, runtime))
        context_identity = {}
        if resolved.get('project_id'):
            from .conversations import context_identity as ensure_context
            from .product.database import Store
            with_context = Store(root)
            try:
                context_identity = ensure_context(with_context, resolved['project_id'], resolved['profile'],
                                                  resolved.get('spec'), unique_key, thread)
            finally:
                with_context.close()
            env['ORBEHELM_WORKSTREAM_ID'] = context_identity['workstream_id']
            env['ORBEHELM_CONTEXT_ID'] = context_identity['context_id']
        args = child_command(output, agent, resolved['profile'], prompt) if headless else command(output, agent, prompt)
        if resume:
            args = resume_command(args, agent, previous['native_session_id'])
        record = {"schema_version": 1, **identity, **context_identity, "orbe_id": orbe_id,
                  "policy_digest": policy, "memory_enabled": memory_enabled, "native_runtime": str(runtime.resolve()), "conversation_id": thread,
                  "knowledge_epoch": knowledge_epoch,
                  "memory_binding": memory_context.get('binding'), "memory_visibility": memory_context.get('visibility'),
                  "native_generation": previous.get('native_generation') if resume else uuid.uuid4().hex,
                  "resume_reason": 'explicit fresh conversation' if new_session else 'policy changed' if fresh_policy else ('exact recorded session' if memory_enabled else 'native continuity; definition refresh is manual') if resume else 'no verified native session',
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
        print('oh: ' + resolved['profile'] + ('/' + resolved['spec'] if resolved.get('spec') else '')
              + ' | full-access | ' + ('resume' if resume else 'fresh native context'), file=sys.stderr)
        try:
            started_ns = time.time_ns()
            record["status"] = "running"
            write_json(record_path, record)
            if memory_store:
                from .conversations import append
                append(memory_store, thread, 'session', agent, {'mode': 'native', 'agent': agent,
                    'orbe_id': orbe_id, 'policy_digest': policy, 'generation': record['native_generation'],
                    'configuration_id': resolved.get('configuration_id'), 'runtime': str(runtime),
                    'native_id': previous.get('native_session_id') if resume else None})
            if headless:
                code = run_child(args, workspace, env, cancel, timeout, on_start)
            else:
                from contextlib import nullcontext
                from .native_capture import capture
                recording = capture(memory_store, thread, runtime, agent, include_existing=previous.get('memory_enabled', True), memory_epoch=knowledge_epoch) if memory_store else nullcontext()
                with display_label(agent, env['ORBEHELM_AGENT_LABEL']), recording:
                    code = subprocess.call(args, cwd=workspace, env=env)
            native_id = (previous['native_session_id'] if resume else discover_native_session(runtime, agent, started_ns)) if not headless and code == 0 else None
            record.update(status="exited", exit_code=code, resumable=bool(native_id and code == 0), native_session_id=native_id)
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
                if memory_store:
                    from .conversations import append
                    append(memory_store, thread, 'session_end', agent, {'mode': 'native', 'agent': agent,
                        'orbe_id': orbe_id, 'policy_digest': policy, 'generation': record['native_generation'],
                        'native_id': record.get('native_session_id'), 'runtime': str(runtime),
                        'status': 'completed' if record.get('exit_code') == 0 else record['status']})
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

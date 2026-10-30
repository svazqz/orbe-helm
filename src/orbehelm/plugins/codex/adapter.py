"""Codex-native formats and commands, translated without executing effects."""
import json
import re
from pathlib import PurePath

from ...application.ports.agents import (
    AdapterCapabilities, Capability, Support, LaunchPlan, RenderedFile, NormalizedAgentEvent, validate_access,
)
from ...domain.shared.errors import OrbeHelmError, UnsupportedCapability


class Adapter:
    id = 'codex'

    def describe(self):
        return AdapterCapabilities(self.id, (
            Capability('render', Support.FULL, 'synthetic-contract'),
            Capability('structured_stream', Support.FULL, 'synthetic-contract', 'Installed CLI flags require separate verification.'),
            Capability('exact_resume', Support.FULL, 'synthetic-contract'),
            Capability('full_access', Support.FULL, 'synthetic-contract', 'OS and managed policy still apply.'),
            Capability('exclusive_context', Support.UNSUPPORTED, 'design', 'Native project/global policy may apply.'),
            Capability('interactive_permissions', Support.UNSUPPORTED, 'design'),
            Capability('workspace_boundary', Support.PARTIAL, 'synthetic-contract', 'Sandbox flag translation; host enforcement requires separate verification.'),
        ))

    def render(self, instructions, servers, output):
        quote = lambda value: json.dumps(value, ensure_ascii=False)
        lines = ['developer_instructions = ' + quote(instructions), 'cli_auth_credentials_store = "file"']
        for name, server in servers.items():
            lines += [f'\n[mcp_servers.{name}]']
            if server['type'] == 'http':
                lines += ['url = ' + quote(server['url'])]
            else:
                if any(k != v for k, v in server.get('env', {}).items()):
                    raise OrbeHelmError('Codex alpha requires identical MCP and host env variable names')
                lines += ['command = ' + quote(server['command']),
                          'args = ' + quote(server.get('args', [])),
                          'env_vars = ' + quote(list(server.get('env', {})))]
        return (RenderedFile('config.toml', '\n'.join(lines) + '\n'),)

    def command(self, output, prompt=None):
        return LaunchPlan(tuple(['codex', '--no-daemon', '--dangerously-bypass-approvals-and-sandbox'] + ([prompt] if prompt else [])))

    def stream_command(self, output, access, prompt, native_id=None, allowed_tools=()):
        validate_access(access)
        if native_id and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', native_id):
            raise OrbeHelmError('Native CLI returned an invalid session identifier')
        if allowed_tools:
            raise UnsupportedCapability('codex: Claude tool permission rules are unsupported')
        args = ['codex', '--no-daemon', 'exec']
        if native_id:
            args += ['resume', native_id]
            if access == 'full-access':
                args += ['--dangerously-bypass-approvals-and-sandbox']
            args += ['--json', '-']
        else:
            args += ['--json', '--skip-git-repo-check']
            args += ['--dangerously-bypass-approvals-and-sandbox'] if access == 'full-access' else ['--sandbox', access]
            args += ['-']
        return LaunchPlan(tuple(args), prompt)

    def decode_event(self, event):
        native_id = event.get('thread_id') if event.get('type') == 'thread.started' else None
        item = event.get('item', {})
        text = item.get('text', '') if event.get('type') == 'item.completed' and isinstance(item, dict) and item.get('type') == 'agent_message' else ''
        if not isinstance(text, str) or (native_id is not None and not isinstance(native_id, str)):
            raise OrbeHelmError('Unsupported native event')
        return NormalizedAgentEvent(text, native_id, event.get('type') in {'turn.completed', 'turn.failed'},
                                    event.get('type') in {'error', 'turn.failed'})

    def child_command(self, output, access, prompt):
        validate_access(access)
        flags = ['--dangerously-bypass-approvals-and-sandbox'] if access == 'full-access' else ['--sandbox', access]
        return LaunchPlan(tuple(['codex', '--no-daemon', 'exec', '--skip-git-repo-check', *flags, prompt]))

    def login_command(self, runtime, output, server):
        return LaunchPlan(('codex', 'mcp', 'login', server)), {'CODEX_HOME': str(PurePath(runtime) / 'codex-home')}

    def resume_command(self, args, native_id=None):
        args = list(args)
        args[2:2] = ['resume', native_id or '--last']
        return args

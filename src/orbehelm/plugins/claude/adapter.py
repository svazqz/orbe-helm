"""Claude-native formats and commands, translated without executing effects."""
import json
import re
from pathlib import PurePath

from ...application.ports.agents import (
    AdapterCapabilities, Capability, Support, LaunchPlan, RenderedFile, NormalizedAgentEvent, validate_access,
)
from ...domain.shared.errors import OrbeHelmError


def tool_rule(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\([^\r\n]*\))?', value):
        raise OrbeHelmError('Use a Claude permission rule such as Edit or Bash(python3 -m unittest *)')
    return value


class Adapter:
    id = 'claude'

    def describe(self):
        return AdapterCapabilities(self.id, (
            Capability('render', Support.FULL, 'synthetic-contract'),
            Capability('structured_stream', Support.FULL, 'synthetic-contract', 'Installed CLI flags require separate verification.'),
            Capability('exact_resume', Support.FULL, 'synthetic-contract'),
            Capability('full_access', Support.FULL, 'synthetic-contract', 'OS and managed policy still apply.'),
            Capability('exclusive_context', Support.UNSUPPORTED, 'design', 'Native project/global policy may apply.'),
            Capability('interactive_permissions', Support.UNSUPPORTED, 'design'),
            Capability('workspace_boundary', Support.UNSUPPORTED, 'design', 'Native tool rules do not establish filesystem isolation.'),
        ))

    def render(self, instructions, servers, output):
        converted = {}
        for name, server in servers.items():
            if server['type'] == 'http':
                converted[name] = {'type': 'http', 'url': server['url']}
            else:
                converted[name] = {'command': server['command'], 'args': server.get('args', []),
                                   'env': {k: '${' + v + '}' for k, v in server.get('env', {}).items()}}
        return (RenderedFile('mcp.json', json.dumps({'mcpServers': converted}, indent=2) + '\n'),)

    def command(self, output, prompt=None):
        output = PurePath(output)
        args = ['claude', '--dangerously-skip-permissions', '--append-system-prompt-file', str(output / 'instructions.md'),
                '--strict-mcp-config', '--mcp-config', str(output / 'mcp.json'), '--setting-sources', '']
        return LaunchPlan(tuple(args + ([prompt] if prompt else [])))

    def stream_command(self, output, access, prompt, native_id=None, allowed_tools=()):
        validate_access(access)
        if native_id and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', native_id):
            raise OrbeHelmError('Native CLI returned an invalid session identifier')
        args = list(self.command(output).argv) + ['--print', '--verbose', '--output-format', 'stream-json']
        if access != 'full-access':
            args.remove('--dangerously-skip-permissions')
        if allowed_tools:
            args += ['--allowedTools', ','.join(tool_rule(rule) for rule in allowed_tools)]
        if native_id:
            args += ['--resume', native_id]
        return LaunchPlan(tuple(args), prompt)

    def decode_event(self, event):
        native_id = event.get('session_id') if event.get('type') in {'system', 'result'} and not event.get('parent_tool_use_id') else None
        text = ''
        if event.get('type') == 'assistant':
            message = event.get('message', {})
            if not isinstance(message, dict) or not isinstance(message.get('content', []), list):
                raise OrbeHelmError('Unsupported native event')
            blocks = message.get('content', [])
            texts = [block.get('text', '') for block in blocks if isinstance(block, dict) and block.get('type') == 'text']
            if any(not isinstance(value, str) for value in texts):
                raise OrbeHelmError('Unsupported native event')
            text = '\n'.join(texts)
        if native_id is not None and not isinstance(native_id, str):
            raise OrbeHelmError('Unsupported native event')
        return NormalizedAgentEvent(text, native_id, event.get('type') == 'result', bool(event.get('is_error')) or event.get('type') == 'error')

    def child_command(self, output, access, prompt):
        validate_access(access)
        output = PurePath(output)
        args = list(self.command(output).argv)
        if access != 'full-access':
            args.remove('--dangerously-skip-permissions')
        return LaunchPlan(tuple([*args, '--print', prompt]))

    def login_command(self, runtime, output, server):
        output = PurePath(output)
        return LaunchPlan(('claude', '--strict-mcp-config', '--mcp-config', str(output / 'mcp.json'),
                           '--setting-sources', '', 'mcp', 'login', server)), {'CLAUDE_CONFIG_DIR': str(PurePath(runtime) / 'claude-home')}

    def resume_command(self, args, native_id=None):
        args = list(args)
        args[1:1] = ['--resume', native_id] if native_id else ['--continue']
        return args

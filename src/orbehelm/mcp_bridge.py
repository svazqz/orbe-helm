"""Bounded JSON-RPC stdio MCP bridge for OrbeHelm-owned coordination tools."""
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import threading

from .core import OrbeHelmError
from .delegation_runner import execute_delegation
from .product.coordination import Coordinator
from .product.database import Store
from .domain.knowledge.retrieval import OUTCOME_TYPES, EVIDENCE_STATES

MAX_MESSAGE = 2 * 1024 * 1024
VERSIONS = ('2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25')


def tool(name, description, properties, required=(), readonly=False):
    return {'name': name, 'description': description,
            'inputSchema': {'type': 'object', 'properties': properties,
                            'required': list(required), 'additionalProperties': False},
            'annotations': {'readOnlyHint': readonly, 'destructiveHint': False,
                            'openWorldHint': name == 'delegate'}}


STRING = {'type': 'string', 'minLength': 1, 'maxLength': 65536}
VERSION = {'type': 'integer', 'minimum': 0}
TOOLS = [
    tool('read_context', 'Read this task, workflow version, pending child results and memory references.', {}, readonly=True),
    tool('read_artifact', 'Read a verified artifact in this task, or accepted knowledge in this project.',
         {'artifact_id': STRING}, ['artifact_id'], readonly=True),
    tool('save_knowledge', 'Persist versioned task knowledge or propose project knowledge. Project proposals require operator acceptance.',
         {'key': STRING, 'content': STRING, 'scope': {'type': 'string', 'enum': ['task', 'project']},
          'kind': {'type': 'string', 'enum': list(OUTCOME_TYPES)},
          'evidence': {'type': 'array', 'items': STRING, 'minItems': 1, 'maxItems': 20},
          'audience': {'type': 'array', 'items': STRING, 'minItems': 1, 'maxItems': 20},
          'evidence_state': {'type': 'string', 'enum': list(EVIDENCE_STATES)},
          'expected_version': VERSION}, ['key', 'content', 'scope', 'expected_version', 'kind', 'evidence']),
    tool('submit_work', 'Developer only: snapshot explicit source inputs and publish a handoff for a new candidate. Include everything needed for review/QA; credentials and generated state are prohibited.',
         {'paths': {'type': 'array', 'items': STRING, 'minItems': 0, 'maxItems': 100},
          'artifact_refs': {'type': 'array', 'maxItems': 20, 'items': {'type': 'object',
              'properties': {'uri': STRING, 'revision': STRING}, 'required': ['uri', 'revision'], 'additionalProperties': False}},
          'handoff': STRING, 'requirements': STRING, 'submission_key': STRING, 'expected_version': VERSION},
         ['paths', 'handoff', 'submission_key', 'expected_version', 'requirements']),
    tool('delegate', 'Developer only: use profile parallel to run independent reviewer and QA assessments on the same frozen candidate. Individual gates are also supported. Starts native models with full execution privileges. Repeated keys do not duplicate work.',
         {'profile': {'type': 'string', 'enum': ['reviewer', 'qa', 'parallel']}, 'key': STRING,
          'instructions': STRING, 'expected_version': VERSION}, ['profile', 'key', 'instructions', 'expected_version']),
    tool('complete_delegation', 'Delegated child only: stage a result for the exact requested candidate. The runner verifies exit and input integrity before accepting it.',
         {'status': {'type': 'string', 'enum': ['approved', 'changes_requested', 'passed', 'failed', 'blocked']},
          'summary': STRING, 'findings': {'type': 'array', 'items': STRING, 'maxItems': 100},
          'evidence': {'type': 'array', 'items': STRING, 'maxItems': 100}}, ['status', 'summary', 'findings', 'evidence']),
    tool('reopen_task', 'Developer only: explicitly reopen a blocked/completed task. Does not bypass pending delegations or submission limits.',
         {'expected_version': VERSION}, ['expected_version']),
]


class Bridge:
    def __init__(self, store, actor_id, agent, delegation_id=None, configuration_id=None):
        self.coordinator = Coordinator(store, actor_id, delegation_id, configuration_id)
        self.agent = agent
        context = self.coordinator.context()
        allowed = {'read_context', 'read_artifact', 'save_knowledge'}
        if delegation_id:
            allowed.add('complete_delegation')
        elif context['profile'] == 'developer' and context['parent_id'] is None:
            allowed.update(['submit_work', 'delegate', 'reopen_task'])
        self.tools = {item['name']: item for item in TOOLS if item['name'] in allowed}

    def call(self, name, arguments, cancel=None):
        if name not in self.tools:
            raise OrbeHelmError('Tool is not available to this bound role orbe')
        schema = self.tools[name]['inputSchema']
        if not isinstance(arguments, dict) or set(arguments) - set(schema['properties']) or set(schema['required']) - set(arguments):
            raise OrbeHelmError('Tool arguments do not match the declared schema')
        operations = {'read_context': self.coordinator.context, 'read_artifact': self.coordinator.read_artifact,
                      'save_knowledge': self.coordinator.save_knowledge, 'submit_work': self.coordinator.submit_work,
                      'complete_delegation': self.coordinator.stage_result, 'reopen_task': self.coordinator.reopen}
        if name == 'delegate':
            from .application import execute
            return execute('task.delegate', coordinator=self.coordinator, agent=self.agent, **arguments, cancel=cancel)
        from .application import execute
        return execute('task.call', coordinator=self.coordinator, name=operations[name].__name__, **arguments)


def serve(root, actor_id, agent, delegation_id=None, configuration_id=None, source=None, sink=None):
    source = source or sys.stdin.buffer
    sink = sink or sys.stdout
    store = Store(root)
    try:
        bridge = Bridge(store, actor_id, agent, delegation_id, configuration_id)
        return _serve(bridge, source, sink)
    finally:
        store.close()


def _serve(bridge, source, sink):
    output_lock, active_lock = threading.Lock(), threading.Lock()
    active = {}
    initialized, ready = False, False

    def send(value):
        encoded = json.dumps(value, ensure_ascii=False)
        with output_lock:
            sink.write(encoded + '\n')
            sink.flush()

    def error(request_id, code, message):
        send({'jsonrpc': '2.0', 'id': request_id, 'error': {'code': code, 'message': message}})

    def complete(request_id, params, cancel):
        try:
            if cancel.is_set():
                error(request_id, -32800, 'Request cancelled')
                return
            try:
                if not isinstance(params, dict) or set(params) - {'name', 'arguments', '_meta'}:
                    raise OrbeHelmError('Invalid tool call')
                value = bridge.call(params.get('name'), params.get('arguments', {}), cancel)
                body = json.dumps(value, ensure_ascii=False)
                if len(body.encode()) > MAX_MESSAGE // 2:
                    raise OrbeHelmError('Tool result exceeds its bound; request a smaller artifact/context')
                result = {'content': [{'type': 'text', 'text': body}], 'isError': False}
            except (OrbeHelmError, OSError, ValueError, TypeError) as failure:
                result = {'content': [{'type': 'text', 'text': str(failure)}], 'isError': True}
            except Exception:
                result = {'content': [{'type': 'text', 'text': 'Internal coordination error; inspect task state before retrying'}], 'isError': True}
            send({'jsonrpc': '2.0', 'id': request_id, 'result': result})
        finally:
            with active_lock:
                active.pop(request_id, None)

    with ThreadPoolExecutor(max_workers=4) as executor:
        try:
            while True:
                line = source.readline(MAX_MESSAGE + 1)
                if not line:
                    break
                if len(line) > MAX_MESSAGE:
                    error(None, -32600, 'Message exceeds the size limit')
                    return 2
                try:
                    message = json.loads(line)
                except (ValueError, UnicodeError):
                    error(None, -32700, 'Invalid JSON')
                    continue
                if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'), str):
                    error(None, -32600, 'Invalid request')
                    continue
                request_id = message.get('id')
                method, params = message['method'], message.get('params', {})
                if request_id is None:
                    if method == 'notifications/initialized' and initialized:
                        ready = True
                    elif method == 'notifications/cancelled' and isinstance(params, dict):
                        if type(params.get('requestId')) not in {int, str}:
                            continue
                        with active_lock:
                            pending = active.get(params.get('requestId'))
                            if pending:
                                pending.set()
                    continue
                if type(request_id) not in {int, str}:
                    error(None, -32600, 'Invalid request id')
                    continue
                if method == 'initialize':
                    if initialized or not isinstance(params, dict):
                        error(request_id, -32600, 'Invalid initialization')
                        continue
                    version = params.get('protocolVersion')
                    initialized = True
                    send({'jsonrpc': '2.0', 'id': request_id, 'result': {
                        'protocolVersion': version if version in VERSIONS else '2025-06-18',
                        'capabilities': {'tools': {}}, 'serverInfo': {'name': 'orbehelm', 'version': '0.1.0'}}})
                elif method == 'ping':
                    send({'jsonrpc': '2.0', 'id': request_id, 'result': {}})
                elif not ready:
                    error(request_id, -32000, 'Initialize the connection first')
                elif method == 'tools/list':
                    send({'jsonrpc': '2.0', 'id': request_id, 'result': {'tools': list(bridge.tools.values())}})
                elif method == 'tools/call':
                    with active_lock:
                        if request_id in active or len(active) >= 16:
                            error(request_id, -32600, 'Duplicate request id or too many outstanding calls')
                            continue
                        cancel = threading.Event()
                        active[request_id] = cancel
                    executor.submit(complete, request_id, params, cancel)
                else:
                    error(request_id, -32601, 'Method not found')
        finally:
            with active_lock:
                for cancel in active.values():
                    cancel.set()
    return 0

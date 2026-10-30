"""Explicit real-model CLI/MCP smoke after tests/check_embedding_model.py --download."""
from pathlib import Path
import contextlib
import io
import json
import os
import selectors
import shutil
import subprocess
import sys
import uuid

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))
from orbehelm.cli import main
from orbehelm.conversations import conversation
from orbehelm.product.database import Store
from orbehelm.product.projects import get_project
from orbehelm.memory import repository, bind, binding_file

base = root / 'state/verification/knowledge-memory' / ('cli-smoke-' + uuid.uuid4().hex[:8])
app, work, home = base / 'app', base / 'work', base / 'home'
for path in (app, work, home):
    path.mkdir(parents=True)
for name in ('definitions', 'registry', 'examples'):
    shutil.copytree(root / name, app / name)
config = base / 'empty.ini'
config.write_text('[ORBEHELM]\n')
# All startup configuration and child environments belong to this verification home.
os.environ.update(HOME=str(home), ORBEHELM_CONFIG=str(config), HERDR_ENV='')
os.environ.pop('ORBEHELM_MEMORY_BINDING', None)
common = ['--root', str(app), '--project', str(work), '--config', str(config)]


def cli(args):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = main([*args, *common])
    assert code == 0, (args, output.getvalue())
    return json.loads(output.getvalue())


cli(['migrate'])
cli(['projects', 'register'])
store = Store(app)
child = None
try:
    project = get_project(store, str(work))
    owner = conversation(store, project.id, 'developer', unique_key='owner-a')
    other = conversation(store, project.id, 'developer', unique_key='owner-b')
    model_base = root / 'state/verification/knowledge-memory/real-model'
    def hardlink(source, destination):
        os.link(Path(source).resolve(), destination)
    shutil.copytree(model_base / 'models', app / 'state/embedding-models', copy_function=hardlink)
    memory = repository(store, load_model=False)
    memory.configure(json.loads((model_base / 'settings.json').read_text()))
    assert cli(['memory', 'configure'])['retrieval'] == 'hybrid'
    file = base / 'fact.txt'
    file.write_text('A dog waits beside its owner.')
    unit = cli(['memory', 'put', '--thread', owner, '--from-file', str(file), '--source-id', 'dog-fact',
                '--kind=constraint', '--evidence=fixture:dog-1'])
    result = cli(['memory', 'query', '--thread', owner, '--query', 'Un perro espera junto a su dueño.'])
    assert result['mode'] == 'hybrid' and result['units'][0]['id'] == unit['id']
    assert not cli(['memory', 'query', '--thread', other, '--query', 'perro'])['units']
    cli(['memory', 'visibility', unit['id'], '--thread', owner, '--visibility', 'global', '--expected-version', '1'])
    assert cli(['memory', 'query', '--thread', other, '--query', 'perro'])['units'][0]['id'] == unit['id']
    cli(['memory', 'visibility', unit['id'], '--thread', owner, '--visibility', 'private', '--expected-version', '2'])
    assert not cli(['memory', 'query', '--thread', other, '--query', 'perro'])['units']
    service, credentials = bind(repository(store), owner, project.id, 'private', owner)
    path = binding_file(app, credentials)
    child = subprocess.Popen([sys.executable, str(root / 'src/orbehelm/_entry.py'), 'memory-serve',
        '--root', str(app), '--config', str(config), '--binding-file', str(path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    def send(value):
        child.stdin.write(json.dumps(value) + '\n')
        child.stdin.flush()
    def ask(identifier, method, params):
        send({'jsonrpc': '2.0', 'id': identifier, 'method': method, 'params': params})
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=30), 'Memory MCP response timed out'
        line = child.stdout.readline()
        assert line, child.stderr.read()
        response = json.loads(line)
        assert response.get('id') == identifier, response
        return response
    assert 'result' in ask(1, 'initialize', {'protocolVersion': '2025-06-18'})
    send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    listing = ask(2, 'tools/list', {})
    assert {tool['name'] for tool in listing['result']['tools']} == {'search_memory', 'read_memory', 'save_memory'}
    reply = ask(3, 'tools/call', {'name': 'search_memory', 'arguments': {'query': 'perro'}})
    assert not reply['result']['isError'], reply
    body = json.loads(reply['result']['content'][0]['text'])
    assert body['units'][0]['id'] == unit['id']
    child.stdin.close()
    child.wait(timeout=10)
    assert child.returncode == 0, child.stderr.read()
    service.repository.revoke_binding(credentials['binding'])
    path.unlink()
    print('Actual CLI migration, multilingual hybrid search, visibility changes/revocation, and stdio MCP passed.')
    print('No HTTP listener or authenticated agent session was started.')
    print('Evidence root:', base)
finally:
    if child and child.poll() is None:
        child.terminate()
        child.wait(timeout=10)
    if child:
        for stream in (child.stdout, child.stderr):
            stream.close()
    store.close()

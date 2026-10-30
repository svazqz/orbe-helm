"""Loopback-only HTML management UI. No model launch or arbitrary filesystem endpoints."""
import hmac
import json
from pathlib import Path
import re
import secrets
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit, urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from orbehelm.core import OrbeHelmError
from orbehelm.application import execute
from orbehelm.service import health_payload
from orbehelm.snapshots import verify_snapshot
from .catalog import Conflict, latest, diff_releases
from .database import Store
from .definition_navigation import definition_navigation, classify
from .models import CatalogRelease
from .library import entries
from .dependency_usage import registration_path, shared_usage

MAX_REQUEST = 2 * 1024 * 1024


def validate_bind(host, port):
    if host not in {'127.0.0.1', 'localhost', '::1'} or not 1 <= port <= 65535:
        raise OrbeHelmError('Use a loopback host and a port between 1 and 65535')


async def form_data(request):
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_REQUEST:
            raise HTTPException(413, 'Request exceeds size limit')
        chunks.append(chunk)
    if request.headers.get('content-type', '').split(';')[0] != 'application/x-www-form-urlencoded':
        raise HTTPException(415, 'Expected a URL-encoded form')
    try:
        parsed = parse_qs(b''.join(chunks).decode('utf-8'), keep_blank_values=True, max_num_fields=20)
    except (ValueError, UnicodeError) as error:
        raise HTTPException(400, 'Malformed form') from error
    if any(len(values) != 1 for values in parsed.values()):
        raise HTTPException(400, 'Duplicate form fields')
    result = {key: value[0] for key, value in parsed.items()}
    token = result.pop('csrf', '')
    if not re.fullmatch('[0-9a-f]{64}', token) or not hmac.compare_digest(token, request.state.csrf):
        raise HTTPException(403, 'Invalid CSRF token; refresh the page')
    return result


def create_app(root, config_path=None):
    store = Store(root)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            await run_in_threadpool(store.close)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.store = store
    templates = Jinja2Templates(directory=str(Path(__file__).parent / 'templates'))
    app.mount('/static', StaticFiles(directory=str(Path(__file__).parent / 'static')), name='static')

    @app.middleware('http')
    async def local_security(request, call_next):
        try:
            parsed = urlsplit('http://' + request.headers.get('host', ''))
            valid_host = parsed.hostname in {'localhost', '127.0.0.1', '::1'} and not parsed.username and not parsed.password
            port = parsed.port
            length = int(request.headers.get('content-length', '0'))
        except ValueError:
            return PlainTextResponse('Invalid request headers', status_code=400)
        if (not valid_host or parsed.path or parsed.query or parsed.fragment
                or (port is not None and not 1 <= port <= 65535) or length < 0):
            return PlainTextResponse('Invalid local Host or content length', status_code=400)
        if request.method not in {'GET', 'HEAD'}:
            origin = request.headers.get('origin')
            if origin and origin != str(request.base_url).rstrip('/'):
                return PlainTextResponse('Invalid Origin', status_code=403)
            if request.headers.get('sec-fetch-site') == 'cross-site':
                return PlainTextResponse('Cross-site requests are not allowed', status_code=403)
            if length > MAX_REQUEST:
                return PlainTextResponse('Request exceeds size limit', status_code=413)
        token = request.cookies.get('orbehelm_csrf', '')
        if not re.fullmatch('[0-9a-f]{64}', token):
            token = secrets.token_hex(32)
        request.state.csrf = token
        response = await call_next(request)
        response.set_cookie('orbehelm_csrf', token, httponly=True, samesite='strict', path='/')
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'none'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    def page(request, template_name, **context):
        return templates.TemplateResponse(request=request, name=template_name,
            context={'csrf': request.state.csrf, 'current_path': request.url.path, **context})

    @app.get('/healthz')
    def health():
        try:
            from sqlalchemy import text
            with store.read() as db:
                version = db.scalar(text('SELECT version_num FROM alembic_version'))
            ready = version == '0006' and latest(store) is not None
        except Exception:
            # Readiness reports failure without exposing database internals.
            ready = False
        payload = health_payload(store.root, ready)
        return JSONResponse(payload, status_code=200 if payload['ready'] else 503)

    @app.get('/skills', response_class=HTMLResponse)
    @app.get('/mcp', response_class=HTMLResponse)
    def library(request: Request, added: str | None = None, removed: str | None = None):
        kind = 'skills' if request.url.path == '/skills' else 'mcp'
        return page(request, 'library.html', kind=kind, items=entries(store, kind),
                    release=latest(store), added=added, removed=removed)

    @app.get('/skills/new', response_class=HTMLResponse)
    @app.get('/mcp/new', response_class=HTMLResponse)
    def new_registration(request: Request, project: str | None = None, project_id: str | None = None):
        kind = 'skills' if request.url.path.endswith('/skills/new') else 'mcp'
        if project or project_id:
            raise HTTPException(400, 'Project management is available through the CLI')
        return page(request, 'library_form.html', kind=kind, values={}, error=None,
                    release=latest(store), project=None)

    @app.post('/skills/new')
    @app.post('/mcp/new')
    async def save_registration(request: Request, project_id: str | None = None):
        form = await form_data(request)
        kind = 'skills' if request.url.path.endswith('/skills/new') else 'mcp'
        if project_id and form.get('project') not in {None, '', project_id}:
            raise HTTPException(400, 'The form does not belong to this project')
        selected_project = project_id or form.get('project')
        if selected_project:
            raise HTTPException(400, 'Project management is available through the CLI')
        project = None
        try:
            await run_in_threadpool(execute, 'shared.skill.add' if kind == 'skills' else 'shared.mcp.add', store=store, form=form)
        except OrbeHelmError as error:
            response = page(request, 'library_form.html', kind=kind, values=form, error=str(error),
                            release=latest(store), project=project)
            response.status_code = 409 if isinstance(error, Conflict) else 400
            return response
        except (OSError, UnicodeError):
            response = page(request, 'library_form.html', kind=kind, values=form,
                            error='The source could not be read. Check its URL or folder and try again.',
                            release=latest(store), project=project)
            response.status_code = 400
            return response
        return RedirectResponse('/' + kind + '?' + urlencode({'added': form['name']}), status_code=303)

    @app.get('/skills/{name}/remove', response_class=HTMLResponse)
    @app.get('/mcp/{name}/remove', response_class=HTMLResponse)
    def confirm_shared_removal(request: Request, name: str):
        kind = 'skills' if request.url.path.startswith('/skills/') else 'mcp'
        release = latest(store)
        source = verify_snapshot(store.root, release.snapshot)
        if not (source / registration_path(kind, name)).is_file():
            raise HTTPException(404, 'Registration not found')
        return page(request, 'removal.html', project=None, kind=kind, name=name,
                    expected=release.id, references=shared_usage(store, release, kind, name),
                    back='/' + kind, error=None)

    @app.post('/skills/{name}/remove')
    @app.post('/mcp/{name}/remove')
    async def delete_shared_registration(request: Request, name: str):
        form = await form_data(request)
        kind = 'skills' if request.url.path.startswith('/skills/') else 'mcp'
        await run_in_threadpool(execute, 'shared.remove', store=store, kind=kind, name=name, expected_release=form.get('expected'))
        return RedirectResponse('/' + kind + '?' + urlencode({'removed': name}), status_code=303)

    @app.exception_handler(OrbeHelmError)
    async def service_error(request, error):
        status = 409 if isinstance(error, Conflict) else 400
        return HTMLResponse(
            templates.env.get_template('error.html').render(error=str(error), status=status, csrf=request.state.csrf),
            status_code=status)

    @app.get('/')
    def dashboard():
        return RedirectResponse('/definitions', status_code=303)

    @app.post('/definitions/publish')
    async def publish(request: Request):
        await form_data(request)
        from orbehelm.application import execute
        await run_in_threadpool(execute, 'shared.publish', store=store)
        return RedirectResponse('/definitions', status_code=303)

    @app.get('/definitions', response_class=HTMLResponse)
    def definitions(request: Request, path: str | None = None, release: str | None = None, category: str | None = None):
        with store.read() as db:
            releases = db.scalars(select(CatalogRelease).order_by(CatalogRelease.sequence.desc())).all()
            selected = db.get(CatalogRelease, release) if release else latest(store)
        if not selected:
            raise HTTPException(404, 'Unknown release')
        source = verify_snapshot(store.root, selected.snapshot)
        listing = json.loads((source.parent / 'manifest.json').read_text())
        if path and path not in listing:
            raise HTTPException(404, 'Definition not found in release')
        categories = definition_navigation(listing)
        category = classify(path)[0] if path else (category or 'base')
        active_category = next((item for item in categories if item['key'] == category), None)
        if active_category is None:
            raise HTTPException(404, 'Unknown definition category')
        if not path and active_category['items']:
            path = active_category['items'][0]['files'][0]['path']
        selected_entry = next((item for item in active_category['items']
                               if any(file['path'] == path for file in item['files'])), None)
        selected_file = next((file for file in selected_entry['files'] if file['path'] == path), None) if selected_entry else None
        content = None
        if path:
            try:
                content = (source / path).read_text(encoding='utf-8')
            except UnicodeError:
                raise HTTPException(400, 'Binary resources cannot be edited')
        return page(request, 'definitions.html', categories=categories, active_category=active_category,
            navigation_section=category if category in {'skills', 'mcp'} else 'definitions',
            selected_entry=selected_entry, selected_file=selected_file, path=path, content=content,
            selected=selected, releases=releases, editable=selected.id == latest(store).id and bool(path),
            source_hash=listing[path]['sha256'] if path else '')

    @app.post('/definitions/save')
    async def save(request: Request):
        form = await form_data(request)
        for name in ('path', 'content', 'expected_release', 'expected_hash'):
            if name not in form:
                raise HTTPException(400, 'Missing editor field')
        from orbehelm.application import execute
        await run_in_threadpool(execute, 'shared.edit', store=store, path=form['path'], content=form['content'],
                                expected_release=form['expected_release'], expected_hash=form['expected_hash'])
        return RedirectResponse('/definitions?' + urlencode({'path': form['path']}), status_code=303)

    @app.get('/releases/{release_id}', response_class=HTMLResponse)
    def release_detail(request: Request, release_id: str, previous: str | None = None):
        with store.read() as db:
            release = db.get(CatalogRelease, release_id)
        if not release:
            raise HTTPException(404, 'Unknown release')
        changes = diff_releases(store, previous or release.parent_id, release.id) if previous or release.parent_id else []
        return page(request, 'release.html', release=release, changes=changes, current_release=latest(store))

    @app.post('/definitions/rollback')
    async def rollback(request: Request):
        form = await form_data(request)
        from orbehelm.application import execute
        if not form.get('revision') or not form.get('expected'):
            raise HTTPException(400, 'Select a history revision and current shared revision')
        await run_in_threadpool(execute, 'shared.rollback', store=store,
                               revision=form['revision'], expected=form['expected'])
        return RedirectResponse('/definitions', status_code=303)

    return app


def serve(root, host='127.0.0.1', port=8765, config_path=None):
    validate_bind(host, port)
    import uvicorn
    app = create_app(root, config_path=config_path)
    try:
        uvicorn.run(app, host=host, port=port, proxy_headers=False, access_log=False)
    finally:
        app.state.store.close()

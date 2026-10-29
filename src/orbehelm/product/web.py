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

from orbehelm.composition import MARKER, SECTION_TITLES
from orbehelm.core import OrbeHelmError, canonical, digest
from orbehelm.service import health_payload
from orbehelm.snapshots import verify_snapshot, manifest
from .catalog import (Conflict, latest, collect_catalog, reconcile_catalog, edit_definition,
                      diff_releases, remove_registration)
from .database import Store
from .definition_navigation import definition_navigation, classify
from .models import Project, ProjectConfiguration, CatalogRelease, ProjectOverrideRevision, Task, LogicalOrbe
from .projects import (register_project, get_project, configuration_for, preview_adoption,
                       adopt_configuration, rollback_configuration, save_override)
from .projects import add_project_dependency, remove_project_dependency
from .orbes import orbe_details
from .capabilities import inventory as capability_inventory, check_capabilities
from .library import entries, add_skill, add_mcp
from .authentication import LoginManager, unavailable
from .dependency_usage import registration_path, shared_usage, project_removal_details
from .coordination import Coordinator

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
    logins = LoginManager()

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            await run_in_threadpool(logins.close)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.store = store
    app.state.logins = logins
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
            ready = version == '0003' and latest(store) is not None
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
    @app.get('/projects/{project_id}/skills/new', response_class=HTMLResponse)
    @app.get('/projects/{project_id}/mcp/new', response_class=HTMLResponse)
    def new_registration(request: Request, project: str | None = None, project_id: str | None = None):
        kind = 'skills' if request.url.path.endswith('/skills/new') else 'mcp'
        if project and project_id is None:
            selected = get_project(store, project)
            return RedirectResponse(f'/projects/{selected.id}/{kind}/new', status_code=303)
        return page(request, 'library_form.html', kind=kind, values={}, error=None,
                    release=latest(store), project=get_project(store, project_id) if project_id else None)

    @app.post('/skills/new')
    @app.post('/mcp/new')
    @app.post('/projects/{project_id}/skills/new')
    @app.post('/projects/{project_id}/mcp/new')
    async def save_registration(request: Request, project_id: str | None = None):
        form = await form_data(request)
        kind = 'skills' if request.url.path.endswith('/skills/new') else 'mcp'
        if project_id and form.get('project') not in {None, '', project_id}:
            raise HTTPException(400, 'The form does not belong to this project')
        selected_project = project_id or form.get('project')
        project = get_project(store, selected_project) if selected_project else None
        try:
            await run_in_threadpool(add_skill if kind == 'skills' else add_mcp, store, form)
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
        if project:
            return RedirectResponse(f'/projects/{project.id}?tab=updates&notice=library-added', status_code=303)
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
        await run_in_threadpool(remove_registration, store, kind, name, form.get('expected'))
        return RedirectResponse('/' + kind + '?' + urlencode({'removed': name}), status_code=303)

    @app.get('/projects/{project_id}/dependencies/{kind}/{name}/remove', response_class=HTMLResponse)
    def confirm_project_removal(request: Request, project_id: str, kind: str, name: str):
        project = get_project(store, project_id)
        config = configuration_for(store, project)
        references = project_removal_details(store, project, config, kind, name)
        return page(request, 'removal.html', project=project, kind=kind, name=name,
                    expected=config.id, references=references,
                    back=f'/projects/{project.id}?tab={kind}', error=None)

    @app.post('/projects/{project_id}/dependencies/{kind}/{name}/remove')
    async def delete_project_addition(request: Request, project_id: str, kind: str, name: str):
        form = await form_data(request)
        project = get_project(store, project_id)
        await run_in_threadpool(remove_project_dependency, store, project, kind, name, form.get('expected'))
        return RedirectResponse(f'/projects/{project.id}?' + urlencode(
            {'tab': kind, 'notice': 'dependency-removed'}), status_code=303)

    @app.exception_handler(OrbeHelmError)
    async def service_error(request, error):
        status = 409 if isinstance(error, Conflict) else 400
        return HTMLResponse(
            templates.env.get_template('error.html').render(error=str(error), status=status, csrf=request.state.csrf),
            status_code=status)

    @app.get('/', response_class=HTMLResponse)
    def dashboard(request: Request):
        with store.read() as db:
            projects = db.scalars(select(Project).order_by(Project.name)).all()
            releases = db.scalars(select(CatalogRelease).order_by(CatalogRelease.sequence.desc())).all()
        orbes = orbe_details(store)
        release = latest(store)
        try:
            drafts_changed = not release or digest(canonical(manifest(collect_catalog(store.root))).encode()) != release.snapshot
            draft_error = None
        except (OrbeHelmError, OSError, ValueError) as error:
            drafts_changed, draft_error = True, str(error)
        return page(request, 'dashboard.html', projects=projects, releases=releases,
            orbes=orbes, release=release, drafts_changed=drafts_changed, draft_error=draft_error)

    @app.post('/definitions/publish')
    async def publish(request: Request):
        await form_data(request)
        await run_in_threadpool(reconcile_catalog, store)
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
            selected=selected, releases=releases, editable=selected.id == latest(store).id and bool(path and path.startswith(('definitions/', 'registry/')) and path.endswith(('.md', '.json'))),
            source_hash=listing[path]['sha256'] if path else '')

    @app.post('/definitions/save')
    async def save(request: Request):
        form = await form_data(request)
        for name in ('path', 'content', 'expected_release', 'expected_hash'):
            if name not in form:
                raise HTTPException(400, 'Missing editor field')
        await run_in_threadpool(edit_definition, store, form['path'], form['content'],
                                form['expected_release'], form['expected_hash'])
        return RedirectResponse('/definitions?' + urlencode({'path': form['path']}), status_code=303)

    @app.get('/releases/{release_id}', response_class=HTMLResponse)
    def release_detail(request: Request, release_id: str, previous: str | None = None):
        with store.read() as db:
            release = db.get(CatalogRelease, release_id)
        if not release:
            raise HTTPException(404, 'Unknown release')
        changes = diff_releases(store, previous or release.parent_id, release.id) if previous or release.parent_id else []
        return page(request, 'release.html', release=release, changes=changes)

    @app.post('/projects/register')
    async def register(request: Request):
        form = await form_data(request)
        if not form.get('path'):
            raise HTTPException(400, 'Project path is required')
        await run_in_threadpool(reconcile_catalog, store)
        from orbehelm.configuration import load
        _, aliases = load(config_path)
        project = await run_in_threadpool(register_project, store, form['path'], aliases)
        return RedirectResponse('/projects/' + project.id, status_code=303)

    @app.get('/projects/{project_id}', response_class=HTMLResponse)
    def project_detail(request: Request, project_id: str, target: str | None = None,
                       selection: str | None = None, agent: str | None = None,
                       tab: str = 'overview', notice: str | None = None):
        if tab not in {'overview', 'skills', 'mcp', 'instructions', 'updates', 'history', 'orbes', 'tasks'}:
            raise HTTPException(404, 'Unknown project section')
        project = get_project(store, project_id)
        config = configuration_for(store, project)
        with store.read() as db:
            configurations = db.scalars(select(ProjectConfiguration).where(ProjectConfiguration.project_id == project.id)
                                       .order_by(ProjectConfiguration.created_at.desc())).all()
            releases = db.scalars(select(CatalogRelease).order_by(CatalogRelease.sequence.desc())).all()
            override_rows = {name: db.get(ProjectOverrideRevision, value) for name, value in config.overrides.items()}
            selected_release = db.get(CatalogRelease, config.release_id)
            tasks = db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.created_at.desc())).all()
        source = verify_snapshot(store.root, selected_release.snapshot)
        profiles = sorted(path.stem for path in (source / 'definitions/profiles').glob('*.json'))
        template = MARKER + '\n\n# Project Profile Override\n\n' + '\n\n'.join('## ' + heading for heading in SECTION_TITLES) + '\n'
        preview = preview_adoption(store, project, target or latest(store).id)
        capabilities = capability_inventory(store, project, config, selection or None, agent)
        kind = 'skills' if tab == 'skills' else 'mcp'
        library_items = entries(store, kind, selected_release)
        available_names = {item['name'] for item in library_items}
        pending_library_items = [item for item in entries(store, kind)
                                 if item['name'] not in available_names]
        for server in capabilities['mcp']:
            server['login_unavailable'] = unavailable(capabilities['agent'], capabilities['runtime'], server['transport'])
        return page(request, 'project.html', project=project, config=config, configurations=configurations,
            releases=releases, preview=preview, overrides=override_rows, profiles=profiles,
            capabilities=capabilities, tab=tab, notice=notice, selected_release=selected_release,
            library_items=library_items, pending_library_items=pending_library_items,
            tasks=tasks,
            override_template=template, orbes=orbe_details(store, project_id=project.id))

    def task_actor(project_id, task_id):
        with store.read() as db:
            task = db.get(Task, task_id)
            if not task or task.project_id != project_id:
                raise HTTPException(404, 'Task not found in this project')
            actor_id = task.owner_id or db.scalar(select(LogicalOrbe.id).where(LogicalOrbe.task_id == task.id))
            if not actor_id:
                raise HTTPException(404, 'Task has no logical orbes')
            return actor_id

    @app.get('/projects/{project_id}/tasks/{task_id}', response_class=HTMLResponse)
    def task_detail(request: Request, project_id: str, task_id: str):
        actor_id = task_actor(project_id, task_id)
        return page(request, 'task.html', project=get_project(store, project_id),
                    task=Coordinator(store, actor_id).context())

    @app.get('/projects/{project_id}/tasks/{task_id}/artifacts/{artifact_id}')
    def task_artifact(project_id: str, task_id: str, artifact_id: str):
        actor_id = task_actor(project_id, task_id)
        return JSONResponse(Coordinator(store, actor_id).read_artifact(artifact_id))

    @app.post('/projects/{project_id}/check-capabilities')
    async def check_project_capabilities(request: Request, project_id: str):
        form = await form_data(request)
        project = get_project(store, project_id)
        config = configuration_for(store, project)
        if config.id != form.get('expected'):
            raise Conflict('Project changed; refresh before checking')
        selection, agent = form.get('selection'), form.get('agent')
        if not selection or not agent:
            raise HTTPException(400, 'Selection and agent are required')
        scope = form.get('tab') if form.get('tab') in {'skills', 'mcp'} else 'all'
        await run_in_threadpool(check_capabilities, store, project, config, selection, agent, scope)
        return RedirectResponse('/projects/' + project.id + '?' + urlencode(
            {'selection': selection, 'agent': agent,
             'tab': form.get('tab') if form.get('tab') in {'skills', 'mcp'} else 'skills'}), status_code=303)

    @app.post('/projects/{project_id}/dependencies')
    async def enable_dependency(request: Request, project_id: str):
        form = await form_data(request)
        project = get_project(store, project_id)
        await run_in_threadpool(add_project_dependency, store, project, form.get('kind'),
                                form.get('name', ''), form.get('expected'))
        return RedirectResponse(f'/projects/{project.id}?' + urlencode(
            {'tab': form['kind'], 'notice': 'dependency-added'}), status_code=303)

    @app.post('/projects/{project_id}/mcp-login')
    async def start_mcp_login(request: Request, project_id: str):
        form = await form_data(request)
        project = get_project(store, project_id)
        config = configuration_for(store, project)
        if config.id != form.get('expected'):
            raise Conflict('Project changed; refresh before signing in')
        if not form.get('selection') or not form.get('agent'):
            raise HTTPException(400, 'Choose an agent configuration first')
        data = await run_in_threadpool(capability_inventory, store, project, config,
                                       form['selection'], form['agent'])
        server = next((item for item in data['mcp'] if item['name'] == form.get('server')), None)
        if server is None:
            raise HTTPException(400, 'This server is not enabled in the selected configuration')
        reason = unavailable(data['agent'], data['runtime'], server['transport'])
        if reason:
            raise OrbeHelmError(reason)
        job = await run_in_threadpool(logins.start, project, data['agent'], server['name'],
                                      data['runtime'], data['output'], selection=data['selection'])
        return RedirectResponse(f'/projects/{project.id}/mcp-login/{job["id"]}', status_code=303)

    @app.get('/projects/{project_id}/mcp-login/{job_id}', response_class=HTMLResponse)
    def mcp_login_status(request: Request, project_id: str, job_id: str):
        return page(request, 'authentication.html', project=get_project(store, project_id),
                    job=logins.get(project_id, job_id))

    @app.post('/projects/{project_id}/mcp-login/{job_id}/cancel')
    async def cancel_mcp_login(request: Request, project_id: str, job_id: str):
        await form_data(request)
        logins.cancel(project_id, job_id)
        return RedirectResponse(f'/projects/{project_id}/mcp-login/{job_id}', status_code=303)

    @app.post('/projects/{project_id}/{action}')
    async def change_project(request: Request, project_id: str, action: str):
        form = await form_data(request)
        project = await run_in_threadpool(get_project, store, project_id)
        expected = form.get('expected', '')
        if action == 'adopt':
            await run_in_threadpool(adopt_configuration, store, project, form.get('release', ''), expected)
        elif action == 'rollback':
            await run_in_threadpool(rollback_configuration, store, project, form.get('revision', ''), expected)
        elif action == 'override':
            await run_in_threadpool(save_override, store, project, form.get('profile', ''), form.get('content', ''), expected)
        elif action == 'remove-override':
            config = configuration_for(store, project)
            overrides = dict(config.overrides)
            overrides.pop(form.get('profile', ''), None)
            await run_in_threadpool(adopt_configuration, store, project, config.release_id, expected, overrides=overrides)
        elif action == 'refresh-context':
            from orbehelm.configuration import load
            _, aliases = load(config_path)
            config = configuration_for(store, project)
            await run_in_threadpool(adopt_configuration, store, project, config.release_id, expected,
                                    refresh_context=True, aliases=aliases)
        else:
            raise HTTPException(404, 'Unknown project action')
        tab = {'adopt': 'updates', 'rollback': 'history', 'override': 'instructions',
               'remove-override': 'instructions', 'refresh-context': 'instructions'}[action]
        return RedirectResponse('/projects/' + project.id + '?' + urlencode({'tab': tab, 'notice': 'saved'}), status_code=303)

    @app.get('/orbes', response_class=HTMLResponse)
    def orbes(request: Request, project: str | None = None):
        return page(request, 'orbes.html', orbes=orbe_details(store, project_id=project))

    @app.get('/orbes/{orbe_id}', response_class=HTMLResponse)
    def orbe_detail(request: Request, orbe_id: str):
        rows = orbe_details(store, orbe_id=orbe_id)
        if not rows:
            raise HTTPException(404, 'Unknown orbe')
        return page(request, 'orbe.html', orbe=rows[0])

    return app


def serve(root, host='127.0.0.1', port=8765, config_path=None):
    validate_bind(host, port)
    import uvicorn
    app = create_app(root, config_path=config_path)
    try:
        uvicorn.run(app, host=host, port=port, proxy_headers=False, access_log=False)
    finally:
        app.state.store.close()

"""Command line interface for the alpha wrapper."""
import argparse
import json
import os
from pathlib import Path
import sys
import shlex

from . import __version__
from .adapters import AGENTS, doctor, launch, authenticate
from .configuration import load, selections
from .core import OrbeHelmError, build, build_directory, identifier, install_skill, locked, resolve
from .compatibility import database_file, orbe_records, read_record
from .layout import server_url
from .service import require_server, server_status
from urllib.parse import urlsplit


def parser():
    p = argparse.ArgumentParser(prog="oh", description="OrbeHelm: compose agent profiles and launch persistent orbes.")
    p.add_argument("command", nargs="?", default="run", choices=["run", "resolve", "build", "doctor", "list", "skills", "status", "auth", "migrate", "web", "server", "projects", "definitions", "tasks", "memory", "mcp-serve"])
    p.add_argument("action", nargs="?", help="skills: list or install")
    p.add_argument("name", nargs="?", help="skill identifier for skills install")
    p.add_argument("--host", help="local server bind address; defaults to the installation URL")
    p.add_argument("--port", type=int, help="local server port; defaults to the installation URL")
    p.add_argument("--release", help="target catalog release")
    p.add_argument("--revision", help="historical configuration or release")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--root", type=Path, help="OrbeHelm definitions directory; defaults to ORBEHELM_ROOT or this checkout")
    p.add_argument("--config", type=Path, help="user defaults and skill mappings; defaults to ORBEHELM_CONFIG or ~/.orbehelmrc")
    p.add_argument("--project", type=Path, help="working directory and optional orbehelm.project.json")
    p.add_argument("--agent", choices=AGENTS)
    p.add_argument("--profile")
    p.add_argument("--spec")
    p.add_argument("--skillset", help="comma-separated named skillsets")
    p.add_argument("--skills", help="comma-separated registered or mapped skill names")
    p.add_argument("--prompt", help="initial task; not saved in orbe metadata")
    p.add_argument("--new-orbe", action="store_true", help="start fresh and make it the default orbe for this identity")
    p.add_argument('--unique-key', help='stable task key; enables task memory and separates managed orbe slots')
    p.add_argument('--workspace', type=Path, help='existing working copy for a keyed task; project configuration remains shared')
    p.add_argument('--actor', help='logical orbe ID for scoped coordination tools')
    p.add_argument('--delegation', help='delegation ID for child binding or operator recovery')
    p.add_argument('--configuration-id', help='pinned project configuration for the MCP runtime binding')
    p.add_argument('--data-file', help='JSON operation arguments file, or - for stdin')
    p.add_argument('--expected-version', type=int, help='expected task workflow version for reopening')
    p.add_argument('--round-limit', type=int, help='operator-only submission limit when reopening a task')
    p.add_argument('--replace-id', help='accepted knowledge ID explicitly replaced by memory acceptance')
    p.add_argument('--confirm-stopped', action='store_true', help='operator confirms an uncertain native dispatch was stopped')
    p.add_argument("--dry-run", action="store_true", help="print only the planned launch command; do not create or modify files or start an agent")
    p.add_argument("--strict", action=argparse.BooleanOptionalAction, default=None, help="require exclusive context; unavailable in alpha")
    return p


def emit(value):
    print(json.dumps(value, indent=2))


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        defaults, skill_sources = load(args.config)
        builtin = {"agent": "codex", "profile": "developer", "spec": None,
                   "project": Path.cwd(), "skillset": "", "skills": "", "strict": False}
        for name, value in builtin.items():
            if getattr(args, name) is None:
                setattr(args, name, defaults.get("skillsets" if name == "skillset" else name, value))
        root = Path(args.root or os.environ.get("ORBEHELM_ROOT") or os.environ.get("AGENTIC_ROOT") or defaults.get("root") or Path(__file__).resolve().parents[2]).expanduser().resolve()
        if args.command == 'server':
            if args.action not in {'start', 'status'} or args.name or args.dry_run or args.new_orbe:
                raise OrbeHelmError('Usage: oh server start|status')
            if args.action == 'status':
                status = server_status(root)
                emit(status)
                return 0 if status['ready'] else 1
            if server_status(root)['ready']:
                raise OrbeHelmError('This OrbeHelm server is already running')
            args.command, args.action = 'web', None
        if args.command == 'web':
            address = urlsplit(server_url(root))
            args.host = args.host or address.hostname
            args.port = args.port or address.port or 80
        if args.command == 'mcp-serve':
            from .mcp_bridge import serve
            if not args.actor or args.agent not in AGENTS:
                raise OrbeHelmError('mcp-serve requires --actor and --agent')
            return serve(root, args.actor, args.agent, args.delegation, args.configuration_id)
        if args.command == 'run' and not args.dry_run:
            # Check before registration, publication, builds, or logical-orbe allocation.
            require_server(root)
        if args.command in {'tasks', 'memory'}:
            from .product.coordination_commands import dispatch as coordinate
            emit(coordinate(args, root))
            return 0
        if (args.unique_key is not None or args.workspace is not None) and args.command != 'run':
            raise OrbeHelmError('--unique-key and --workspace apply only to run')
        if args.workspace is not None and args.unique_key is None:
            raise OrbeHelmError('--workspace requires --unique-key')
        if args.unique_key is not None:
            from .product.coordination import unique_key
            unique_key(args.unique_key)
            if not database_file(root).exists():
                raise OrbeHelmError('Keyed task memory requires an initialized database; run oh migrate')
        if args.command not in {"skills", "projects", "definitions"} and (args.action or args.name):
            raise OrbeHelmError("Unexpected positional arguments")
        if args.dry_run and args.command != "run":
            raise OrbeHelmError("--dry-run is supported only for run (the default command)")
        if args.new_orbe and args.command != "run":
            raise OrbeHelmError("--new-orbe is supported only for run")
        if args.command in {"migrate", "web", "projects", "definitions"}:
            from .product.commands import dispatch
            result = dispatch(args, root, skill_sources)
            if result is not None:
                emit(result)
            return 0
        if args.command == "auth":
            return authenticate(root, args.agent)
        if args.command == "list":
            emit({"profiles": sorted(x.stem for x in (root / "definitions/profiles").glob("*.json")),
                  "specializations": {x.name: sorted(p.stem for p in x.glob("*.json"))
                                      for x in (root / "definitions/specializations").iterdir() if x.is_dir()},
                  "skillsets": sorted(x.stem for x in (root / "definitions/skillsets").glob("*.json")),
                  "agents": list(AGENTS)})
            return 0
        if args.command == "status" and database_file(root).exists():
            from .product.database import Store
            from .product.models import ConfigurationBuild, Project
            from .product.orbes import orbe_details
            from sqlalchemy import select, func
            store = Store(root)
            try:
                with store.read() as db:
                    projects = db.scalar(select(func.count()).select_from(Project))
                    builds = db.scalar(select(func.count()).select_from(ConfigurationBuild))
                emit({"projects": projects, "builds": builds, "orbes": orbe_details(store)})
            finally:
                store.close()
            return 0
        if args.command == "status":
            emit({"builds": len(list((root / "generated").glob("*/*/build.json"))),
                  "installed_skills": len(list((root / "state/skills").glob("*/SKILL.md"))),
                  "orbes": [read_record(x) for x in orbe_records(root)]})
            return 0
        if args.command == "skills":
            if args.action in {None, "list"} and not args.name:
                emit({"available": sorted({x.stem for x in (root / "registry/skills").glob("*.json")} | set(skill_sources))})
                return 0
            if args.action != "install" or not args.name:
                raise OrbeHelmError("Usage: oh skills install <name>")
            name = identifier(args.name)
            selected = resolve(root, args.profile, args.spec, (), args.project,
                               skills=[name], skill_sources=skill_sources)
            definition = next(item for item in selected["skills"] if item["name"] == name)
            with locked(root):
                for dependency in selected["skills"]:
                    install_skill(root, dependency)
            emit({"skill": name, "sha256": definition["sha256"],
                  "installed": str(root / "state/skills" / definition["sha256"])})
            return 0
        if args.strict and args.command == "run":
            raise OrbeHelmError("Strict isolation is not available in alpha; no agent was launched")
        selected = selections(args.skillset, "skillset")
        product_store = None
        if database_file(root).exists():
            from .product.database import Store
            from .product.catalog import reconcile_catalog
            from .product.projects import register_project, get_project, resolve_project
            product_store = Store(root)
            try:
                if args.dry_run or args.command in {"resolve", "doctor"}:
                    project = get_project(product_store, str(args.project))
                else:
                    reconcile_catalog(product_store)
                    project = register_project(product_store, args.project, skill_sources)
                resolved = resolve_project(product_store, project, profile=args.profile, spec=args.spec,
                    skillsets=selected, skills=selections(args.skills, "skills"),
                    persist=not args.dry_run and args.command in {"build", "run"})
            finally:
                product_store.close()
        else:
            resolved = resolve(root, args.profile, args.spec, selected, args.project,
                               skills=selections(args.skills, "skills"), skill_sources=skill_sources)
        if args.command == "resolve":
            emit(resolved)
            return 0
        if args.command == "doctor":
            result = doctor(resolved, args.agent)
            emit(result)
            return 0 if result["ok"] else 1
        if args.dry_run:
            if args.unique_key is not None:
                # A keyed run must prepare scoped runtime overlays; print a write-free
                # wrapper invocation rather than a misleading unscoped native command.
                planned = [sys.executable, str(Path(__file__).with_name('_entry.py')), 'run', '--root', str(root),
                    '--project', str(args.project), '--agent', args.agent, '--profile', args.profile,
                    '--spec=' + (args.spec or ''), '--skills=' + args.skills, '--skillset=' + args.skillset,
                    '--unique-key', args.unique_key]
                if args.workspace:
                    planned += ['--workspace', str(args.workspace)]
                if args.config:
                    planned += ['--config', str(args.config)]
                if args.new_orbe:
                    planned.append('--new-orbe')
                if args.prompt:
                    planned += ['--prompt', args.prompt]
                print(shlex.join(planned))
                return 0
            output = build_directory(root, resolved, args.agent)
            print(launch(root, output, resolved, args.agent, args.prompt, dry_run=True, strict=args.strict, new_orbe=args.new_orbe))
            return 0
        if resolved.get("project_id"):
            from .product.projects import build_project
            from .product.database import Store
            store = Store(root)
            try:
                output, cached = build_project(store, resolved, args.agent)
            finally:
                store.close()
        else:
            output, cached = build(root, resolved, args.agent)
        if args.command == "build":
            emit({"output": str(output), "cached": cached, "fingerprint": resolved["fingerprint"]})
            return 0
        actor_id = None
        task_workspace = args.workspace
        if args.unique_key is not None:
            from .product.coordination import ensure_orbe
            from .product.database import Store
            from .product.projects import get_project
            store = Store(root)
            try:
                actor_id = ensure_orbe(store, get_project(store, str(args.project)), args.unique_key,
                                          args.profile, args.spec, args.workspace)
                from .product.coordination import Coordinator
                task_workspace = Coordinator(store, actor_id).context()['workspace']
            finally:
                store.close()
        result = launch(root, output, resolved, args.agent, args.prompt, args.dry_run, args.strict,
                        new_orbe=args.new_orbe, unique_key=args.unique_key, actor_id=actor_id,
                        workspace=task_workspace)
        if isinstance(result, str):
            print(result)
            return 0
        return result
    except ModuleNotFoundError as error:
        print(f"oh: Missing product dependency {error.name}; install this checkout in .venv with pip install -e '.[dev]'", file=sys.stderr)
        return 2
    except (OrbeHelmError, OSError, UnicodeError, ValueError) as error:
        print(f"oh: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

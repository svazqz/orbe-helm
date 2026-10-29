"""Deterministic resolution, local skill installation, and verified build caching."""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit

from . import __version__


class OrbeHelmError(Exception):
    """An actionable configuration or runtime error."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", value):
        raise OrbeHelmError(f"Invalid identifier: {value!r}; use lowercase letters, digits, and hyphens")
    return value


def contained(root, relative):
    root = Path(root).resolve()
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise OrbeHelmError(f"Expected a relative path: {relative!r}")
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise OrbeHelmError(f"Path escapes its root: {relative}")
    return target


def read_json(path):
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise OrbeHelmError(f"Cannot read {path}: {error}") from error
    if not isinstance(result, dict) or result.get("schema_version") != 1:
        raise OrbeHelmError(f"{path}: expected an object with schema_version = 1")
    return result


def strings(value, label):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        raise OrbeHelmError(f"{label} must be a list of nonempty strings")
    return value


def keys(data, allowed, label):
    extra = set(data) - set(allowed) - {"schema_version"}
    if extra:
        raise OrbeHelmError(f"{label}: unknown fields: {', '.join(sorted(extra))}")


def tree(path):
    if not path.is_dir() or not (path / "SKILL.md").is_file():
        raise OrbeHelmError(f"Skill directory must contain SKILL.md: {path}")
    entries = {}
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise OrbeHelmError(f"Skill symlinks are not supported: {item}")
        if item.is_file():
            entries[item.relative_to(path).as_posix()] = {
                "sha256": digest(item.read_bytes()), "executable": bool(item.stat().st_mode & 0o111)}
        elif not item.is_dir():
            raise OrbeHelmError(f"Unsupported skill entry: {item}")
    return entries


@contextlib.contextmanager
def locked(root):
    state = root / "state"
    if state.is_symlink():
        raise OrbeHelmError("state must not be a symlink")
    state.mkdir(parents=True, exist_ok=True)
    with (state / "build.lock").open("a") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def validate_mcp(config, label):
    keys(config, ["type", "command", "args", "url", "env"], label)
    env = config.get("env", {})
    if not isinstance(env, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                       or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k)
                                       or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", v)
                                       for k, v in env.items()):
        raise OrbeHelmError(f"MCP {label}: env must map server variable names to host variable names")
    if config.get("type") == "stdio":
        if not isinstance(config.get("command"), str) or not config["command"]:
            raise OrbeHelmError(f"MCP {label}: command is required")
        strings(config.get("args", []), "MCP args")
        if "url" in config:
            raise OrbeHelmError(f"MCP {label}: stdio cannot define url")
    elif config.get("type") == "http":
        if not isinstance(config.get("url"), str) or urlsplit(config["url"]).scheme not in {"http", "https"}:
            raise OrbeHelmError(f"MCP {label}: an HTTP URL is required")
        if env or "command" in config or "args" in config:
            raise OrbeHelmError(f"MCP {label}: HTTP auth and command fields are not supported in alpha")
    else:
        raise OrbeHelmError(f"MCP {label}: type must be stdio or http")


def resolve(root, profile="developer", spec=None, skillsets=(), project=None, skills=(), skill_sources=None,
            project_context=None, profile_overrides=None, cache_root=None):
    root = Path(root).resolve()
    identifier(profile)
    if spec:
        identifier(spec)
    project = Path(project or Path.cwd()).resolve()
    if not project.is_dir():
        raise OrbeHelmError(f"Project directory not found: {project}")
    resolved = {"schema_version": 1, "generator_version": __version__, "root": str(root),
                "project": str(project), "profile": profile, "spec": spec,
                "skillsets": sorted(set(identifier(s) for s in skillsets)),
                "selected_skills": sorted(set(identifier(s) for s in skills)),
                "sources": [], "instructions": [], "skills": [], "mcp": {}}
    loaded_instructions = set()
    requested_skills, requested_mcp = list(resolved["selected_skills"]), []
    skill_sources = skill_sources or {}

    def source(path, scope):
        rel = path.relative_to(scope).as_posix()
        data = path.read_bytes()
        resolved["sources"].append({"scope": str(scope), "path": rel, "sha256": digest(data)})
        return data

    def layer(path, scope, structured=False):
        config = read_json(path)
        keys(config, ["instructions", "skills", "mcp"], str(path))
        source(path, scope)
        for rel in strings(config.get("instructions", []), "instructions"):
            target = contained(scope, rel)
            key = str(target)
            if key not in loaded_instructions:
                loaded_instructions.add(key)
                content = source(target, scope).decode("utf-8")
                resolved["instructions"].append({"path": key, "content": content, "structured": structured})
        requested_skills.extend(strings(config.get("skills", []), "skills"))
        requested_mcp.extend(strings(config.get("mcp", []), "mcp"))

    layer(contained(root, "definitions/base/config.json"), root, structured=True)
    layer(contained(root, f"definitions/profiles/{profile}.json"), root, structured=True)
    if profile_overrides and profile in profile_overrides:
        content = profile_overrides[profile]
        resolved["instructions"].append({"path": f"override:{profile}", "content": content, "structured": True})
        resolved["sources"].append({"scope": "override", "path": profile,
                                    "sha256": digest(content.encode())})
    if spec:
        layer(contained(root, f"definitions/specializations/{profile}/{spec}.json"), root, structured=True)
    for name in resolved["skillsets"]:
        layer(contained(root, f"definitions/skillsets/{name}.json"), root)
    context = Path(project_context) if project_context is not None else project
    from .compatibility import project_file
    project_definition = project_file(context)
    if project_definition.exists():
        layer(project_definition, context)

    from .composition import compose
    resolved["composed_instructions"] = compose(resolved["instructions"])

    visiting, visited = set(), set()

    def skill(name):
        identifier(name)
        if name in visiting:
            raise OrbeHelmError(f"Cyclic skill dependency involving {name}")
        if name in visited:
            return
        visiting.add(name)
        if name in skill_sources:
            config = {"source": skill_sources[name]}
        else:
            path = contained(root, f"registry/skills/{name}.json")
            config = read_json(path)
            keys(config, ["source", "sha256", "skills", "mcp"], str(path))
            source(path, root)
        location = config.get("source")
        if isinstance(location, str) and "://" in location:
            from .remote_skills import resolve_remote
            definition = resolve_remote(cache_root or root, name, location)
        else:
            local = Path(location).resolve() if name in skill_sources else contained(root, location)
            entries = tree(local)
            definition = {"name": name, "source": str(local),
                          "sha256": digest(canonical(entries).encode()), "files": entries}
        sha = definition["sha256"]
        if config.get("sha256") is not None and config["sha256"] != sha:
            raise OrbeHelmError(f"Skill {name} does not match its pinned sha256")
        for dependency in strings(config.get("skills", []), "skill dependencies"):
            skill(dependency)
        requested_mcp.extend(strings(config.get("mcp", []), "skill MCP dependencies"))
        resolved["skills"].append(definition)
        visiting.remove(name)
        visited.add(name)

    for name in requested_skills:
        skill(name)
    for name in sorted(set(requested_mcp)):
        identifier(name)
        path = contained(root, f"registry/mcp/{name}.json")
        config = read_json(path)
        keys(config, ["type", "command", "args", "url", "env"], str(path))
        source(path, root)
        validate_mcp(config, name)
        resolved["mcp"][name] = config
    # Include implementation bytes so code changes invalidate generated output too.
    resolved["implementation"] = {p.name: digest(p.read_bytes()) for p in sorted(Path(__file__).parent.glob("*.py"))
                                  if p.name in {"core.py", "composition.py", "adapters.py", "remote_skills.py", "snapshots.py"}}
    resolved["fingerprint"] = digest(canonical(resolved).encode())
    return resolved


def install_skill(root, definition):
    """Must be called under the root lock. Installation never executes skill code."""
    parent = root / "state/skills"
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / definition["sha256"]
    def remember_source():
        if "remote" in definition:
            from .remote_skills import source_manifest
            manifest = source_manifest(root, definition["remote"])
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"url": definition["remote"], "sha256": definition["sha256"]}) + "\n")
    if target.is_dir():
        try:
            if tree(target) == definition["files"]:
                remember_source()
                return target
        except OrbeHelmError:
            pass
    if target.exists():
        shutil.rmtree(target)
    with tempfile.TemporaryDirectory(dir=parent, prefix=".install-") as tmp:
        staged = Path(tmp) / "skill"
        if "remote" in definition:
            from .remote_skills import download
            files, entries, sha = download(definition["remote"])
            if sha != definition["sha256"] or entries != definition["files"]:
                raise OrbeHelmError(f"Remote skill changed during installation: {definition['name']}; retry")
            staged.mkdir()
            for relative, item in files.items():
                path = contained(staged, relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(item["content"])
                path.chmod(0o755 if item["executable"] else 0o644)
        else:
            shutil.copytree(definition["source"], staged, symlinks=True)
        if tree(staged) != definition["files"]:
            raise OrbeHelmError(f"Skill changed during installation: {definition['name']}; retry")
        staged.rename(target)
    remember_source()
    return target


def inventory(directory):
    return {p.relative_to(directory).as_posix(): digest(p.read_bytes())
            for p in sorted(directory.rglob("*")) if p.is_file() and p != directory / "build.json"}


def build_directory(root, resolved, agent="codex"):
    """Calculate the generated configuration path without touching the filesystem."""
    if agent not in {"codex", "claude", "opencode"}:
        raise OrbeHelmError(f"Unknown agent: {agent}")
    build_id = digest((resolved["fingerprint"] + ":" + agent).encode())
    if resolved.get("project_id"):
        if not isinstance(resolved["project_id"], str) or not re.fullmatch(r"[a-z0-9-]+", resolved["project_id"]):
            raise OrbeHelmError("Invalid project artifact identity")
        return Path(root).resolve() / "state/projects" / resolved["project_id"] / "builds" / agent / build_id
    return Path(root).resolve() / "generated" / agent / build_id


def build(root, resolved, agent="codex"):
    from .adapters import render
    root = Path(root).resolve()
    output = build_directory(root, resolved, agent)
    build_id = output.name
    parent = output.parent
    with locked(root):
        installed = {s["name"]: install_skill(root, s) for s in resolved["skills"]}
        if output.is_dir():
            try:
                metadata = json.loads((output / "build.json").read_text())
                if metadata["build_id"] == build_id and metadata["files"] == inventory(output):
                    return output, True
            except (OSError, ValueError, KeyError):
                pass
            shutil.rmtree(output)
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent, prefix=".build-") as tmp:
            staged = Path(tmp) / "output"
            staged.mkdir()
            sections = [resolved["composed_instructions"].rstrip()]
            for s in resolved["skills"]:
                target = staged / "skills" / s["name"]
                target.parent.mkdir(exist_ok=True)
                shutil.copytree(installed[s["name"]], target)
                final_path = output / "skills" / s["name"]
                sections.append(f"# Selected Skill {s['name']}\n\nResources: {final_path}\n\n"
                                + (target / "SKILL.md").read_text().strip())
            (staged / "instructions.md").write_text("\n\n".join(sections) + "\n")
            (staged / "resolved.json").write_text(json.dumps(resolved, indent=2) + "\n")
            render(staged, output, resolved, agent)
            (staged / "build.json").write_text(json.dumps({"schema_version": 1, "build_id": build_id,
                "agent": agent, "files": inventory(staged)}, indent=2) + "\n")
            staged.rename(output)
    return output, False

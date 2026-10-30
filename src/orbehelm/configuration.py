"""Optional user defaults and skill source aliases; reading never creates files."""
import configparser
import os
from pathlib import Path

from .core import OrbeHelmError, identifier
from .compatibility import existing_path


OPTIONS = {"root", "agent", "profile", "spec", "project", "skillsets", "skills", "strict", "memory"}


def selections(value, label):
    if not value:
        return []
    names = value.split(",")
    if any(not name.strip() for name in names):
        raise OrbeHelmError(f"{label} must be a comma-separated list without empty entries")
    return sorted(set(identifier(name.strip()) for name in names))


def load(path=None):
    configured = os.environ.get("ORBEHELM_CONFIG") or os.environ.get("AGENTIC_CONFIG")
    explicit = path is not None or bool(configured)
    location = Path(path or configured or existing_path(Path.home(), ".orbehelmrc", ".agenticrc")).expanduser().resolve()
    if not location.exists():
        if explicit:
            raise OrbeHelmError(f"Configuration file does not exist: {location}")
        return {}, {}
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        with location.open(encoding="utf-8") as handle:
            parser.read_file(handle)
    except configparser.Error as error:
        raise OrbeHelmError(f"Invalid configuration {location}: {error}") from error
    if parser.defaults():
        raise OrbeHelmError(f"{location}: use [ORBEHELM], not [DEFAULT]")
    sections = {}
    for name in parser.sections():
        normalized = "ORBEHELM" if name.upper() == "AGENTIC" else name.upper()
        if normalized not in {"ORBEHELM", "SKILLS"} or normalized in sections:
            raise OrbeHelmError(f"{location}: unknown or repeated section: {name}")
        sections[normalized] = dict(parser[name])
    defaults = sections.get("ORBEHELM", {})
    extra = set(defaults) - OPTIONS
    if extra:
        raise OrbeHelmError(f"{location}: unknown defaults: {', '.join(sorted(extra))}")
    for name in ("root", "project"):
        if defaults.get(name):
            value = Path(defaults[name]).expanduser()
            defaults[name] = (location.parent / value).resolve()
        elif name in defaults:
            del defaults[name]
    if "agent" in defaults and defaults["agent"] not in {"codex", "claude", "opencode"}:
        raise OrbeHelmError(f"{location}: agent must be codex, claude, or opencode")
    for name in ("profile", "spec"):
        if defaults.get(name):
            identifier(defaults[name])
        elif name in defaults:
            del defaults[name]
    for name in ("skills", "skillsets"):
        if name in defaults:
            selections(defaults[name], name)
    for name in ('strict', 'memory'):
        if name in defaults:
            try:
                defaults[name] = configparser.ConfigParser.BOOLEAN_STATES[defaults[name].lower()]
            except KeyError as error:
                raise OrbeHelmError(f"{location}: {name} must be true or false") from error
    aliases = sections.get("SKILLS", {})
    for name, value in aliases.items():
        identifier(name)
        if not value:
            raise OrbeHelmError(f"{location}: skill {name} requires a source")
        if "://" in value:
            from .remote_skills import validate_url
            validate_url(value)
        else:
            aliases[name] = str((location.parent / Path(value).expanduser()).resolve())
    return defaults, aliases

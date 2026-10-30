"""Pure definition schemas and transport configuration validation."""
import re
from urllib.parse import urlsplit
from ..shared.errors import OrbeHelmError


def strings(value, label):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        raise OrbeHelmError(f"{label} must be a list of nonempty strings")
    return value


def keys(data, allowed, label):
    extra = set(data) - set(allowed) - {"schema_version"}
    if extra:
        raise OrbeHelmError(f"{label}: unknown fields: {', '.join(sorted(extra))}")



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
        try:
            parsed = urlsplit(config['url'])
            if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
                    or parsed.port == 0 or any(char.isspace() for char in config['url'])):
                raise ValueError('Invalid endpoint')
        except ValueError as error:
            raise OrbeHelmError(f'MCP {label}: use an HTTP endpoint without credentials, query parameters, or fragments') from error
        if env or "command" in config or "args" in config:
            raise OrbeHelmError(f"MCP {label}: HTTP auth and command fields are not supported in alpha")
    else:
        raise OrbeHelmError(f"MCP {label}: type must be stdio or http")

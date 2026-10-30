"""Canonical serialization, content identity, and portable identifiers."""
import hashlib
import json
import re

from .errors import OrbeHelmError


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", value):
        raise OrbeHelmError(f"Invalid identifier: {value!r}; use lowercase letters, digits, and hyphens")
    return value

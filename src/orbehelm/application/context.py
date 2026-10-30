"""Verified authorization context supplied through an injected authorization port."""
from dataclasses import dataclass
from ..domain.access.entities import AccessScope


@dataclass(frozen=True)
class RequestContext:
    scope: AccessScope
    now: int

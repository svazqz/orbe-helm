"""Versioned request envelopes; authority is never supplied in payload fields."""
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class Request:
    operation: str
    payload: Mapping[str, object] = field(default_factory=dict)
    api_version: int = 1
    request_id: str = ''
    idempotency_key: str | None = None
    expected_revision: int | None = None

    def __post_init__(self):
        object.__setattr__(self, 'payload', MappingProxyType(dict(self.payload)))

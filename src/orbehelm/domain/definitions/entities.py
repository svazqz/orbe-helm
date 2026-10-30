"""Source definitions and immutable publication references."""
from dataclasses import dataclass
from enum import Enum
from ..shared.ids import RevisionId


class DefinitionKind(str, Enum):
    BASE = 'base'
    PROFILE = 'profile'
    SPECIALIZATION = 'specialization'
    SKILLSET = 'skillset'
    SKILL = 'skill'
    MCP = 'mcp'
    RESOURCE = 'resource'


@dataclass(frozen=True)
class Definition:
    path: str
    kind: DefinitionKind


@dataclass(frozen=True)
class DefinitionRevision:
    id: RevisionId
    path: str
    content_hash: str
    snapshot: str


@dataclass(frozen=True)
class CatalogRelease:
    id: RevisionId
    sequence: int
    snapshot: str
    parent_id: RevisionId | None = None

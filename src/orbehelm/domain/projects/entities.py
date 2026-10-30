"""Project identity and immutable configuration references, separate from ORM rows."""
from dataclasses import dataclass
from ..shared.ids import ProjectId, RevisionId


@dataclass(frozen=True)
class Project:
    id: ProjectId
    path: str
    name: str
    active_revision: RevisionId | None = None


@dataclass(frozen=True)
class ProjectConfiguration:
    id: RevisionId
    project_id: ProjectId
    release_id: RevisionId
    context_snapshot: str
    parent_id: RevisionId | None = None
    catalog_snapshot: str | None = None

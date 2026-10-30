"""Knowledge ownership and publication are separate from observation lifecycle."""
from dataclasses import dataclass
from enum import Enum
from ..shared.ids import KUnitId, PrincipalId, ProjectId, OrbeId, TaskId


class Visibility(str, Enum):
    PRIVATE = 'private'
    PROJECT = 'project'
    GLOBAL = 'global'
    COLLECTIVE = 'global'  # Historical symbol; global visibility never transfers ownership.


class KnowledgeStatus(str, Enum):
    REPORTED = 'reported'
    PROPOSED = 'proposed'
    ACCEPTED = 'accepted'
    SUPERSEDED = 'superseded'
    RETRACTED = 'retracted'
    INVALIDATED = 'invalidated'


@dataclass(frozen=True)
class KUnit:
    id: KUnitId
    revision: int
    content: str
    author_id: PrincipalId
    owner_kind: str
    project_id: ProjectId | None = None
    orbe_id: OrbeId | None = None
    task_id: TaskId | None = None
    visibility: Visibility = Visibility.PRIVATE
    status: KnowledgeStatus = KnowledgeStatus.REPORTED
    evidence_ids: tuple[str, ...] = ()
    restricted_source_id: KUnitId | None = None

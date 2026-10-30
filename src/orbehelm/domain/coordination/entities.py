"""Task workflow values without database lifecycle or process state."""
from dataclasses import dataclass
from ..shared.ids import OrbeId, ProjectId, TaskId


@dataclass(frozen=True)
class Task:
    id: TaskId
    project_id: ProjectId
    owner_id: OrbeId | None
    state: str = 'developing'
    version: int = 0
    candidate_id: str | None = None
    rounds: int = 0
    max_rounds: int | None = None


@dataclass(frozen=True)
class WorkflowActor:
    id: OrbeId
    profile: str
    parent_id: OrbeId | None = None

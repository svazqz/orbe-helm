"""Authorization inputs supplied by a trusted verifier, never by request payloads."""
from dataclasses import dataclass
from ..shared.ids import PrincipalId, ProjectId, OrbeId, TaskId


@dataclass(frozen=True)
class AccessGrant:
    id: str
    principal_id: PrincipalId
    action: str
    resource_id: str
    issued_at: int
    expires_at: int
    revoked: bool = False


@dataclass(frozen=True)
class AccessScope:
    principal_id: PrincipalId
    role: str
    project_id: ProjectId | None = None
    orbe_id: OrbeId | None = None
    task_id: TaskId | None = None
    grants: tuple[AccessGrant, ...] = ()
    policy_revision: int = 0

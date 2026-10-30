"""Logical work identity is independent from any native conversation binding."""
from dataclasses import dataclass
from ..shared.ids import OrbeId, ProjectId, TaskId, ConversationId


@dataclass(frozen=True)
class Orbe:
    id: OrbeId
    project_id: ProjectId
    profile: str
    specialization: str = ''
    unique_key: str = ''
    parent_id: OrbeId | None = None
    task_id: TaskId | None = None
    conversation_id: ConversationId | None = None


@dataclass(frozen=True)
class AgentSession:
    id: str
    orbe_id: OrbeId
    adapter_id: str
    native_id: str | None
    policy_digest: str
    compatibility_digest: str
    status: str

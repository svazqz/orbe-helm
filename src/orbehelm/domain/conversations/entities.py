"""Durable conversation identity and normalized public history."""
from dataclasses import dataclass
from ..shared.ids import ConversationId, ProjectId


@dataclass(frozen=True)
class Conversation:
    id: ConversationId
    project_id: ProjectId
    selection: str
    checkpoint: str = ''


@dataclass(frozen=True)
class ConversationEvent:
    conversation_id: ConversationId
    sequence: int
    kind: str
    adapter_id: str
    text: str
    source_id: str | None = None

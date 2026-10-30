"""Operational metadata. Immutable source bytes live in verified filesystem snapshots."""
from datetime import datetime, timezone
import uuid

from sqlalchemy import ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id():
    return uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Definition(Base):
    __tablename__ = "definitions"
    path: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str]


class DefinitionRevision(Base):
    __tablename__ = "definition_revisions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    path: Mapped[str] = mapped_column(ForeignKey("definitions.path"))
    content_hash: Mapped[str]
    snapshot: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)
    __table_args__ = (UniqueConstraint("path", "content_hash"),)


class CatalogRelease(Base):
    __tablename__ = "catalog_releases"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    sequence: Mapped[int] = mapped_column(unique=True)
    snapshot: Mapped[str]
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("catalog_releases.id"))
    message: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)


class ReleaseMember(Base):
    __tablename__ = "release_members"
    release_id: Mapped[str] = mapped_column(ForeignKey("catalog_releases.id"), primary_key=True)
    path: Mapped[str] = mapped_column(ForeignKey("definitions.path"), primary_key=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("definition_revisions.id"))


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    path: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    active_revision: Mapped[str | None] = mapped_column(ForeignKey("project_configurations.id", use_alter=True))
    created_at: Mapped[str] = mapped_column(default=now)


class ProjectConfiguration(Base):
    __tablename__ = "project_configurations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    release_id: Mapped[str] = mapped_column(ForeignKey("catalog_releases.id"))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("project_configurations.id"))
    context_snapshot: Mapped[str]
    aliases: Mapped[dict] = mapped_column(JSON, default=dict)
    overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    file_overrides: Mapped[dict] = mapped_column(JSON, default=dict, server_default='{}')
    catalog_snapshot: Mapped[str | None]
    reason: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)


class ProjectOverrideRevision(Base):
    __tablename__ = "project_overrides"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    profile: Mapped[str]
    base_hash: Mapped[str]
    base_sections: Mapped[dict] = mapped_column(JSON)
    content: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)


class Conversation(Base):
    __tablename__ = 'conversations'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    selection: Mapped[str]
    checkpoint: Mapped[str] = mapped_column(Text, default='', server_default='')
    created_at: Mapped[str] = mapped_column(default=now)
    __table_args__ = (UniqueConstraint('project_id', 'selection'),)


class ConversationEvent(Base):
    __tablename__ = 'conversation_events'
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id'), primary_key=True)
    sequence: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str]
    agent: Mapped[str]
    data: Mapped[dict] = mapped_column(JSON)
    source_id: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=now)
    __table_args__ = (UniqueConstraint('conversation_id', 'source_id'),)


class ConfigurationBuild(Base):
    __tablename__ = "configuration_builds"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    fingerprint: Mapped[str]
    agent: Mapped[str]
    path: Mapped[str]
    sources: Mapped[list] = mapped_column(JSON)
    selection: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)
    __table_args__ = (UniqueConstraint("project_id", "fingerprint", "agent"),)


class SelectionLock(Base):
    __tablename__ = "selection_locks"
    configuration_id: Mapped[str] = mapped_column(ForeignKey("project_configurations.id"), primary_key=True)
    selection: Mapped[str] = mapped_column(String, primary_key=True)
    resolved: Mapped[dict] = mapped_column(JSON)


class OrbeSlot(Base):
    __tablename__ = "orbe_slots"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    agent: Mapped[str]
    profile: Mapped[str]
    specialization: Mapped[str]
    unique_key: Mapped[str] = mapped_column(default='', server_default='')
    active_orbe: Mapped[str | None] = mapped_column(ForeignKey("orbes.id", use_alter=True))
    __table_args__ = (UniqueConstraint("project_id", "agent", "profile", "specialization", "unique_key", name='uq_orbe_slot_identity'),)


class Orbe(Base):
    __tablename__ = "orbes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    slot_key: Mapped[str] = mapped_column(ForeignKey("orbe_slots.key"))
    runtime_path: Mapped[str]
    created_at: Mapped[str | None]
    legacy: Mapped[bool] = mapped_column(default=False)


class OrbeLaunch(Base):
    __tablename__ = "orbe_launches"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    orbe_id: Mapped[str] = mapped_column(ForeignKey("orbes.id"))
    configuration_id: Mapped[str | None] = mapped_column(ForeignKey("project_configurations.id"))
    build_id: Mapped[str | None] = mapped_column(ForeignKey("configuration_builds.id"))
    legacy_build: Mapped[str | None]
    selection: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[str | None]
    ended_at: Mapped[str | None]
    status: Mapped[str]
    exit_code: Mapped[int | None]
    wrapper_pid: Mapped[int | None]


class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    unique_key: Mapped[str]
    workspace: Mapped[str]
    owner_id: Mapped[str | None]
    state: Mapped[str] = mapped_column(default='developing')
    version: Mapped[int] = mapped_column(default=0)
    candidate_id: Mapped[str | None]
    rounds: Mapped[int] = mapped_column(default=0)
    max_rounds: Mapped[int] = mapped_column(default=3)
    created_at: Mapped[str] = mapped_column(default=now)
    __table_args__ = (UniqueConstraint('project_id', 'unique_key'),)


class LogicalOrbe(Base):
    __tablename__ = 'logical_orbes'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'))
    profile: Mapped[str]
    specialization: Mapped[str]
    orbe_key: Mapped[str]
    parent_id: Mapped[str | None] = mapped_column(ForeignKey('logical_orbes.id'))
    created_at: Mapped[str] = mapped_column(default=now)
    __table_args__ = (UniqueConstraint('task_id', 'profile', 'specialization', 'orbe_key'),)


class TaskArtifact(Base):
    __tablename__ = 'task_artifacts'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'))
    author_id: Mapped[str] = mapped_column(ForeignKey('logical_orbes.id'))
    kind: Mapped[str]
    content_hash: Mapped[str]
    path: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)


class Knowledge(Base):
    __tablename__ = 'knowledge'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'))
    author_id: Mapped[str] = mapped_column(ForeignKey('logical_orbes.id'))
    key: Mapped[str]
    scope: Mapped[str]
    version: Mapped[int]
    status: Mapped[str]
    artifact_id: Mapped[str] = mapped_column(ForeignKey('task_artifacts.id'))
    __table_args__ = (UniqueConstraint('task_id', 'scope', 'key', 'version'),)


class Delegation(Base):
    __tablename__ = 'delegations'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'))
    parent_id: Mapped[str] = mapped_column(ForeignKey('logical_orbes.id'))
    child_id: Mapped[str] = mapped_column(ForeignKey('logical_orbes.id'))
    candidate_id: Mapped[str] = mapped_column(ForeignKey('task_artifacts.id'))
    context_id: Mapped[str] = mapped_column(ForeignKey('task_artifacts.id'))
    profile: Mapped[str]
    key: Mapped[str]
    instructions: Mapped[str]
    status: Mapped[str] = mapped_column(default='queued')
    result_id: Mapped[str | None] = mapped_column(ForeignKey('task_artifacts.id'))
    worker_pid: Mapped[int | None]
    child_pid: Mapped[int | None]
    created_at: Mapped[str] = mapped_column(default=now)
    finished_at: Mapped[str | None]
    __table_args__ = (UniqueConstraint('parent_id', 'profile', 'key', 'candidate_id'),)


class TaskEvent(Base):
    __tablename__ = 'task_events'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey('tasks.id'))
    sequence: Mapped[int]
    actor_id: Mapped[str | None] = mapped_column(ForeignKey('logical_orbes.id'))
    kind: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)
    __table_args__ = (UniqueConstraint('task_id', 'sequence'),)


class MemoryOwner(Base):
    __tablename__ = 'memory_owners'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    visibility: Mapped[str] = mapped_column(default='private')


class MemoryThread(Base):
    __tablename__ = 'memory_threads'
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id'), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('memory_owners.id'))


class KUnitRecord(Base):
    __tablename__ = 'kunits'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('memory_owners.id'))
    revision: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    visibility: Mapped[str]
    status: Mapped[str]
    source_id: Mapped[str]
    source_kind: Mapped[str]
    created_at: Mapped[str]
    updated_at: Mapped[str]
    __table_args__ = (UniqueConstraint('owner_id', 'source_id'),)


class KUnitRevisionRecord(Base):
    __tablename__ = 'kunit_revisions'
    unit_id: Mapped[str] = mapped_column(ForeignKey('kunits.id'), primary_key=True)
    revision: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    visibility: Mapped[str]
    status: Mapped[str]
    reason: Mapped[str]
    created_at: Mapped[str]


class MemorySource(Base):
    __tablename__ = 'memory_sources'
    owner_id: Mapped[str] = mapped_column(ForeignKey('memory_owners.id'), primary_key=True)
    source_id: Mapped[str] = mapped_column(primary_key=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey('kunits.id'))
    content_hash: Mapped[str]
    source_kind: Mapped[str]
    created_at: Mapped[str]


class KUnitEdge(Base):
    __tablename__ = 'kunit_edges'
    unit_id: Mapped[str] = mapped_column(ForeignKey('kunits.id'), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey('kunits.id'), primary_key=True)
    source_revision: Mapped[int]


class MemoryState(Base):
    __tablename__ = 'memory_state'
    id: Mapped[int] = mapped_column(primary_key=True)
    policy_epoch: Mapped[int]
    settings: Mapped[dict] = mapped_column(JSON)


class MemoryBinding(Base):
    __tablename__ = 'memory_bindings'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('memory_owners.id'))
    token_hash: Mapped[str]
    visibility: Mapped[str]
    expires_at: Mapped[int]
    active: Mapped[bool]
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey('conversations.id'))


class MemoryRead(Base):
    __tablename__ = 'memory_reads'
    binding_id: Mapped[str] = mapped_column(ForeignKey('memory_bindings.id'), primary_key=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey('kunits.id'), primary_key=True)
    revision: Mapped[int]


class MemoryIndexJob(Base):
    __tablename__ = 'memory_index_jobs'
    unit_id: Mapped[str] = mapped_column(ForeignKey('kunits.id'), primary_key=True)
    revision: Mapped[int]
    status: Mapped[str]
    error: Mapped[str | None]


class MemoryCapture(Base):
    __tablename__ = 'memory_captures'
    owner_id: Mapped[str] = mapped_column(ForeignKey('memory_owners.id'), primary_key=True)
    source_id: Mapped[str] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    visibility: Mapped[str]
    status: Mapped[str]
    error: Mapped[str | None]
    sources: Mapped[dict] = mapped_column(JSON)


class Workstream(Base):
    __tablename__ = 'workstreams'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'))
    profile: Mapped[str]
    unique_key: Mapped[str]
    __table_args__ = (UniqueConstraint('project_id', 'profile', 'unique_key'),)


class SessionContext(Base):
    __tablename__ = 'session_contexts'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    workstream_id: Mapped[str] = mapped_column(ForeignKey('workstreams.id'))
    specialization: Mapped[str]
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey('conversations.id'), unique=True)
    __table_args__ = (UniqueConstraint('workstream_id', 'specialization'),)


class KnowledgeMetadata(Base):
    __tablename__ = 'knowledge_metadata'
    unit_id: Mapped[str] = mapped_column(ForeignKey('kunits.id'), primary_key=True)
    kind: Mapped[str]
    audience: Mapped[list] = mapped_column(JSON)
    evidence: Mapped[list] = mapped_column(JSON)
    evidence_state: Mapped[str]
    profile: Mapped[str]
    specialization: Mapped[str]

"""Explicit projections prevent SQLAlchemy lifecycle from leaking into domain values."""
from ...domain.projects.entities import Project, ProjectConfiguration
from ...domain.conversations.entities import Conversation
from ...domain.definitions.entities import Definition, DefinitionKind, DefinitionRevision, CatalogRelease
from ...domain.coordination.entities import Task, WorkflowActor


def project(row):
    return Project(row.id, row.path, row.name, row.active_revision)


def configuration(row):
    return ProjectConfiguration(row.id, row.project_id, row.release_id, row.context_snapshot,
                                row.parent_id, row.catalog_snapshot)


def conversation(row):
    return Conversation(row.id, row.project_id, row.selection, row.checkpoint)


def definition(row):
    # Historical rows classify by directory, including plural names and resources.
    aliases = {'profiles': 'profile', 'specializations': 'specialization',
               'skillsets': 'skillset', 'skills': 'skill'}
    kind = aliases.get(row.kind, row.kind)
    if kind not in {value.value for value in DefinitionKind}:
        kind = DefinitionKind.RESOURCE
    return Definition(row.path, DefinitionKind(kind))


def definition_revision(row):
    return DefinitionRevision(row.id, row.path, row.content_hash, row.snapshot)


def catalog_release(row):
    return CatalogRelease(row.id, row.sequence, row.snapshot, row.parent_id)


def task(row):
    return Task(row.id, row.project_id, row.owner_id, row.state, row.version,
                row.candidate_id, row.rounds, None)


def workflow_actor(row):
    return WorkflowActor(row.id, row.profile, row.parent_id)

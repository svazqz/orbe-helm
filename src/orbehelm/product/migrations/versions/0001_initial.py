"""Initial product schema. Frozen definitions; do not import current models."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('definitions',
        sa.Column('path', sa.String(), nullable=False, primary_key=True),
        sa.Column('kind', sa.String(), nullable=False),
    )
    op.create_table('definition_revisions',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column('path', sa.String(), sa.ForeignKey('definitions.path'), nullable=False),
        sa.Column('content_hash', sa.String(), nullable=False),
        sa.Column('snapshot', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.UniqueConstraint('path', 'content_hash'),
    )
    op.create_table('catalog_releases',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('snapshot', sa.String(), nullable=False),
        sa.Column('parent_id', sa.String(), sa.ForeignKey('catalog_releases.id'), nullable=True),
        sa.Column('message', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.UniqueConstraint('sequence'),
    )
    op.create_table('release_members',
        sa.Column('release_id', sa.String(), sa.ForeignKey('catalog_releases.id'), nullable=False, primary_key=True),
        sa.Column('path', sa.String(), sa.ForeignKey('definitions.path'), nullable=False, primary_key=True),
        sa.Column('revision_id', sa.String(), sa.ForeignKey('definition_revisions.id'), nullable=False),
    )
    op.create_table('projects',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column('path', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('active_revision', sa.String(), sa.ForeignKey('project_configurations.id'), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.UniqueConstraint('path'),
    )
    op.create_table('project_configurations',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('release_id', sa.String(), sa.ForeignKey('catalog_releases.id'), nullable=False),
        sa.Column('parent_id', sa.String(), sa.ForeignKey('project_configurations.id'), nullable=True),
        sa.Column('context_snapshot', sa.String(), nullable=False),
        sa.Column('aliases', sa.JSON(), nullable=False),
        sa.Column('overrides', sa.JSON(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
    )
    op.create_table('project_overrides',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('profile', sa.String(), nullable=False),
        sa.Column('base_hash', sa.String(), nullable=False),
        sa.Column('base_sections', sa.JSON(), nullable=False),
        sa.Column('content', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
    )
    op.create_table('configuration_builds',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('fingerprint', sa.String(), nullable=False),
        sa.Column('agent', sa.String(), nullable=False),
        sa.Column('path', sa.String(), nullable=False),
        sa.Column('sources', sa.JSON(), nullable=False),
        sa.Column('selection', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.UniqueConstraint('project_id', 'fingerprint', 'agent'),
    )
    op.create_table('selection_locks',
        sa.Column('configuration_id', sa.String(), sa.ForeignKey('project_configurations.id'), nullable=False, primary_key=True),
        sa.Column('selection', sa.String(), nullable=False, primary_key=True),
        sa.Column('resolved', sa.JSON(), nullable=False),
    )
    op.create_table('session_slots',
        sa.Column('key', sa.String(), nullable=False, primary_key=True),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('agent', sa.String(), nullable=False),
        sa.Column('profile', sa.String(), nullable=False),
        sa.Column('specialization', sa.String(), nullable=False),
        sa.Column('active_session', sa.String(), sa.ForeignKey('sessions.id'), nullable=True),
        sa.UniqueConstraint('project_id', 'agent', 'profile', 'specialization'),
    )
    op.create_table('sessions',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('slot_key', sa.String(), sa.ForeignKey('session_slots.key'), nullable=False),
        sa.Column('runtime_path', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=True),
        sa.Column('legacy', sa.Boolean(), nullable=False),
    )
    op.create_table('session_launches',
        sa.Column('id', sa.String(), nullable=False, primary_key=True),
        sa.Column('session_id', sa.String(), sa.ForeignKey('sessions.id'), nullable=False),
        sa.Column('configuration_id', sa.String(), sa.ForeignKey('project_configurations.id'), nullable=True),
        sa.Column('build_id', sa.String(), sa.ForeignKey('configuration_builds.id'), nullable=True),
        sa.Column('legacy_build', sa.String(), nullable=True),
        sa.Column('selection', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.String(), nullable=True),
        sa.Column('ended_at', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('wrapper_pid', sa.Integer(), nullable=True),
    )


def downgrade():
    raise RuntimeError("Restore a database backup instead of deleting product history")

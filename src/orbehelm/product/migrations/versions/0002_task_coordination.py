"""Task identity, shared memory, and parent/child delegation. Frozen schema."""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    naming = {'uq': 'uq_%(table_name)s_%(column_0_name)s_%(column_1_name)s_%(column_2_name)s_%(column_3_name)s'}
    with op.batch_alter_table('session_slots', naming_convention=naming) as batch:
        batch.add_column(sa.Column('unique_key', sa.String(), nullable=False, server_default=''))
        batch.drop_constraint('uq_session_slots_project_id_agent_profile_specialization', type_='unique')
        batch.create_unique_constraint('uq_session_slot_identity', ['project_id', 'agent', 'profile', 'specialization', 'unique_key'])
    op.create_table('tasks',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('unique_key', sa.String(), nullable=False),
        sa.Column('workspace', sa.String(), nullable=False),
        sa.Column('owner_id', sa.String(), nullable=True),
        sa.Column('state', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('candidate_id', sa.String(), nullable=True),
        sa.Column('rounds', sa.Integer(), nullable=False),
        sa.Column('max_rounds', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.UniqueConstraint('project_id', 'unique_key'))
    op.create_table('logical_sessions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('task_id', sa.String(), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('profile', sa.String(), nullable=False),
        sa.Column('specialization', sa.String(), nullable=False),
        sa.Column('session_key', sa.String(), nullable=False),
        sa.Column('parent_id', sa.String(), sa.ForeignKey('logical_sessions.id'), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.UniqueConstraint('task_id', 'profile', 'specialization', 'session_key'))
    op.create_table('task_artifacts',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('task_id', sa.String(), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('author_id', sa.String(), sa.ForeignKey('logical_sessions.id'), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('content_hash', sa.String(), nullable=False),
        sa.Column('path', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False))
    op.create_table('knowledge',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('task_id', sa.String(), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('author_id', sa.String(), sa.ForeignKey('logical_sessions.id'), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('scope', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('artifact_id', sa.String(), sa.ForeignKey('task_artifacts.id'), nullable=False),
        sa.UniqueConstraint('task_id', 'scope', 'key', 'version'))
    op.create_table('delegations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('task_id', sa.String(), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('parent_id', sa.String(), sa.ForeignKey('logical_sessions.id'), nullable=False),
        sa.Column('child_id', sa.String(), sa.ForeignKey('logical_sessions.id'), nullable=False),
        sa.Column('candidate_id', sa.String(), sa.ForeignKey('task_artifacts.id'), nullable=False),
        sa.Column('context_id', sa.String(), sa.ForeignKey('task_artifacts.id'), nullable=False),
        sa.Column('profile', sa.String(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('instructions', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('result_id', sa.String(), sa.ForeignKey('task_artifacts.id'), nullable=True),
        sa.Column('worker_pid', sa.Integer(), nullable=True),
        sa.Column('child_pid', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('finished_at', sa.String(), nullable=True),
        sa.UniqueConstraint('parent_id', 'profile', 'key', 'candidate_id'))
    op.create_table('task_events',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('task_id', sa.String(), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('actor_id', sa.String(), sa.ForeignKey('logical_sessions.id'), nullable=True),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.UniqueConstraint('task_id', 'sequence'))


def downgrade():
    raise RuntimeError('Restore a database backup instead of deleting task history')

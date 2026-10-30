"""Owned knowledge units and recoverable indexing. Frozen schema."""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('memory_owners',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('visibility', sa.String(), nullable=False))
    op.create_table('memory_threads',
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), primary_key=True),
        sa.Column('owner_id', sa.String(), sa.ForeignKey('memory_owners.id'), nullable=False))
    op.create_table('kunits',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('owner_id', sa.String(), sa.ForeignKey('memory_owners.id'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('visibility', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('source_id', sa.String(), nullable=False),
        sa.Column('source_kind', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('updated_at', sa.String(), nullable=False),
        sa.UniqueConstraint('owner_id', 'source_id'))
    op.create_table('kunit_revisions',
        sa.Column('unit_id', sa.String(), sa.ForeignKey('kunits.id'), primary_key=True),
        sa.Column('revision', sa.Integer(), primary_key=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('visibility', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False))
    op.create_table('memory_sources',
        sa.Column('owner_id', sa.String(), sa.ForeignKey('memory_owners.id'), primary_key=True),
        sa.Column('source_id', sa.String(), primary_key=True),
        sa.Column('unit_id', sa.String(), sa.ForeignKey('kunits.id'), nullable=False),
        sa.Column('content_hash', sa.String(), nullable=False),
        sa.Column('source_kind', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False))
    op.create_table('kunit_edges',
        sa.Column('unit_id', sa.String(), sa.ForeignKey('kunits.id'), primary_key=True),
        sa.Column('source_id', sa.String(), sa.ForeignKey('kunits.id'), primary_key=True),
        sa.Column('source_revision', sa.Integer(), nullable=False))
    op.create_table('memory_state',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('policy_epoch', sa.Integer(), nullable=False),
        sa.Column('settings', sa.JSON(), nullable=False))
    op.execute(sa.text("INSERT INTO memory_state VALUES (1, 0, '{}')"))
    op.create_table('memory_bindings',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('owner_id', sa.String(), sa.ForeignKey('memory_owners.id'), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('visibility', sa.String(), nullable=False),
        sa.Column('expires_at', sa.Integer(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), nullable=True))
    op.create_table('memory_reads',
        sa.Column('binding_id', sa.String(), sa.ForeignKey('memory_bindings.id'), primary_key=True),
        sa.Column('unit_id', sa.String(), sa.ForeignKey('kunits.id'), primary_key=True),
        sa.Column('revision', sa.Integer(), nullable=False))
    op.create_table('memory_index_jobs',
        sa.Column('unit_id', sa.String(), sa.ForeignKey('kunits.id'), primary_key=True),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error', sa.String(), nullable=True))
    op.create_table('memory_captures',
        sa.Column('owner_id', sa.String(), sa.ForeignKey('memory_owners.id'), primary_key=True),
        sa.Column('source_id', sa.String(), primary_key=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('visibility', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error', sa.String(), nullable=True),
        sa.Column('sources', sa.JSON(), nullable=False))


def downgrade():
    raise RuntimeError('Restore a database backup instead of deleting knowledge history')

"""Project file overlays and agent-independent conversation history. Frozen schema."""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('project_configurations', sa.Column('file_overrides', sa.JSON(), nullable=False, server_default='{}'))
    op.add_column('project_configurations', sa.Column('catalog_snapshot', sa.String(), nullable=True))
    op.create_table('conversations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('selection', sa.String(), nullable=False),
        sa.Column('checkpoint', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.UniqueConstraint('project_id', 'selection'))
    op.create_table('conversation_events',
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), primary_key=True),
        sa.Column('sequence', sa.Integer(), primary_key=True),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('agent', sa.String(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('source_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.UniqueConstraint('conversation_id', 'source_id'))


def downgrade():
    raise RuntimeError('Restore a database backup instead of deleting conversation history')

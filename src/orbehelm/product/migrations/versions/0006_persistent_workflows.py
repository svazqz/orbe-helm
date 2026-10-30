"""Add workstream/context mappings and typed knowledge without merging history."""
import hashlib
import json

from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def _id(parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()[:32]


def upgrade():
    op.create_table('workstreams',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('profile', sa.String(), nullable=False),
        sa.Column('unique_key', sa.String(), nullable=False),
        sa.UniqueConstraint('project_id', 'profile', 'unique_key'))
    op.create_table('session_contexts',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('workstream_id', sa.String(), sa.ForeignKey('workstreams.id'), nullable=False),
        sa.Column('specialization', sa.String(), nullable=False),
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), unique=True),
        sa.UniqueConstraint('workstream_id', 'specialization'))
    op.create_table('knowledge_metadata',
        sa.Column('unit_id', sa.String(), sa.ForeignKey('kunits.id'), primary_key=True),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('audience', sa.JSON(), nullable=False),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('evidence_state', sa.String(), nullable=False),
        sa.Column('profile', sa.String(), nullable=False),
        sa.Column('specialization', sa.String(), nullable=False))
    connection = op.get_bind()
    # Invalid historical selections remain auditable but are not guessed or merged.
    for row in connection.execute(sa.text('SELECT id,project_id,selection FROM conversations')).mappings():
        try:
            selection = json.loads(row['selection'])
        except (ValueError, TypeError):
            continue
        if not isinstance(selection, dict) or not isinstance(selection.get('profile'), str):
            continue
        profile, key, spec = selection['profile'], selection.get('unique_key') or '', selection.get('spec') or ''
        work = _id(['workstream', row['project_id'], profile, key])
        context = _id(['context', work, spec])
        connection.execute(sa.text('INSERT OR IGNORE INTO workstreams VALUES (:id,:project,:profile,:key)'),
                           {'id': work, 'project': row['project_id'], 'profile': profile, 'key': key})
        connection.execute(sa.text('INSERT OR IGNORE INTO session_contexts VALUES (:id,:work,:spec,:conversation)'),
                           {'id': context, 'work': work, 'spec': spec, 'conversation': row['id']})
    for row in connection.execute(sa.text('SELECT project_id,profile,specialization,unique_key FROM orbe_slots')).mappings():
        work = _id(['workstream', row['project_id'], row['profile'], row['unique_key'] or ''])
        context = _id(['context', work, row['specialization'] or ''])
        connection.execute(sa.text('INSERT OR IGNORE INTO workstreams VALUES (:id,:project,:profile,:key)'),
            {'id': work, 'project': row['project_id'], 'profile': row['profile'], 'key': row['unique_key'] or ''})
        connection.execute(sa.text('INSERT OR IGNORE INTO session_contexts VALUES (:id,:work,:spec,NULL)'),
            {'id': context, 'work': work, 'spec': row['specialization'] or ''})
    # No historical unit is reclassified, deleted or published. Missing metadata
    # prevents automatic injection through new agent bindings, preserving audit reads.
    connection.execute(sa.text('UPDATE memory_state SET policy_epoch=policy_epoch+1 WHERE id=1'))
    # Context-private memory must not reuse a task-wide owner across specializations.
    connection.execute(sa.text("INSERT OR IGNORE INTO memory_owners (id,project_id,visibility) "
                               "SELECT c.id,c.project_id,'private' FROM conversations c JOIN memory_threads t ON t.conversation_id=c.id"))
    connection.execute(sa.text('UPDATE memory_threads SET owner_id=conversation_id'))


def downgrade():
    raise RuntimeError('Restore a database backup instead of deleting workflow history')

"""Rename managed sessions to orbes while preserving IDs and references. Frozen schema."""
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite rewrites references on table/column rename, including self references.
    # Runtime paths and immutable JSON history deliberately retain their original bytes.
    connection = op.get_bind()
    legacy = connection.exec_driver_sql('PRAGMA legacy_alter_table').scalar()
    connection.exec_driver_sql('PRAGMA legacy_alter_table=OFF')
    try:
        for previous, current in [('sessions', 'orbes'), ('session_slots', 'orbe_slots'),
                                  ('session_launches', 'orbe_launches'),
                                  ('logical_sessions', 'logical_orbes')]:
            op.rename_table(previous, current)
        for table, previous, current in [('orbe_slots', 'active_session', 'active_orbe'),
                                         ('orbe_launches', 'session_id', 'orbe_id'),
                                         ('logical_orbes', 'session_key', 'orbe_key')]:
            op.execute(f'ALTER TABLE "{table}" RENAME COLUMN "{previous}" TO "{current}"')
    finally:
        connection.exec_driver_sql(f'PRAGMA legacy_alter_table={int(legacy)}')
    with op.batch_alter_table('orbe_slots') as batch:
        batch.drop_constraint('uq_session_slot_identity', type_='unique')
        batch.create_unique_constraint('uq_orbe_slot_identity',
            ['project_id', 'agent', 'profile', 'specialization', 'unique_key'])


def downgrade():
    raise RuntimeError('Restore a database backup instead of rewriting orbe history')

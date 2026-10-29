"""Alembic receives a project-specific connection; never infer a global database."""
from alembic import context
from orbehelm.product.models import Base

connection = context.config.attributes["connection"]
context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()

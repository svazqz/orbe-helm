"""Explicit Alembic upgrades and short-lived SQLAlchemy sessions."""
from contextlib import contextmanager, closing
import fcntl
from pathlib import Path
import sqlite3
import uuid

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from orbehelm.core import OrbeHelmError
from orbehelm.compatibility import database_file


def database_path(root):
    path = database_file(root)
    if path.parent.is_symlink():
        raise OrbeHelmError("state must not be a symlink")
    return path


@contextmanager
def product_lock(root):
    directory = Path(root) / "state"
    if directory.is_symlink():
        raise OrbeHelmError("state must not be a symlink")
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / "product.lock"
    if lock.is_symlink():
        raise OrbeHelmError("Product lock must not be a symlink")
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def engine_for(root):
    path = database_path(root)
    if path.is_symlink():
        raise OrbeHelmError("Database must not be a symlink")
    engine = create_engine("sqlite:///" + str(path), poolclass=NullPool,
                           connect_args={"timeout": 5, "check_same_thread": False})

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")

    return engine


def migrate(root):
    from alembic import command
    from alembic.config import Config
    with product_lock(root):
        path = database_path(root)
        if path.exists():
            backup = path.parent / "backups" / ("orbehelm-" + uuid.uuid4().hex + ".sqlite3")
            backup.parent.mkdir(exist_ok=True, mode=0o700)
            with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as target:
                source.backup(target)
            backup.chmod(0o600)
        engine = engine_for(root)
        try:
            with engine.connect() as connection:
                # SQLite batch migrations rebuild referenced tables. Disable FK enforcement
                # only on this migration connection, then validate every reference before commit.
                connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
                connection.commit()
                config = Config()
                config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
                config.attributes["connection"] = connection
                with connection.begin():
                    command.upgrade(config, "head")
                    if connection.exec_driver_sql('PRAGMA foreign_key_check').first() is not None:
                        raise OrbeHelmError('Migration produced invalid references; restore the database backup')
                connection.exec_driver_sql('PRAGMA foreign_keys=ON')
                connection.commit()
        finally:
            engine.dispose()
        path.chmod(0o600)
    return str(path)


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        if not database_path(root).is_file():
            raise OrbeHelmError("Product database is not initialized; run oh migrate")
        self.engine = engine_for(root)
        try:
            with self.engine.connect() as connection:
                version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                if version != "0006":
                    raise OrbeHelmError("Database needs migration; run oh migrate")
        except SQLAlchemyError as error:
            self.engine.dispose()
            raise OrbeHelmError('Cannot read the product schema; run oh migrate or restore a database backup') from error
        except OrbeHelmError:
            self.engine.dispose()
            raise

    @contextmanager
    def read(self):
        with Session(self.engine, expire_on_commit=False) as session:
            yield session

    @contextmanager
    def write(self):
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            yield session

    def close(self):
        self.engine.dispose()

"""SQLAlchemy engine + session factory."""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
    future=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _conn_record) -> None:
    """WAL + busy_timeout so many concurrent pollers and the worker's writes
    don't collide with "database is locked" under multi-user load.
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    from app.db import models  # noqa: F401  (register tables)

    Base.metadata.create_all(bind=engine)
    _ensure_queue_position_column()
    _ensure_viz_artifacts_column()


def _ensure_queue_position_column() -> None:
    """No migration framework: add jobs.queue_position to DBs predating it."""
    with engine.connect() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(jobs)").fetchall()
        names = {row[1] for row in cols}
        if "queue_position" not in names:
            conn.exec_driver_sql("ALTER TABLE jobs ADD COLUMN queue_position INTEGER")
            conn.commit()


def _ensure_viz_artifacts_column() -> None:
    """No migration framework: add models.viz_artifacts to DBs predating it."""
    with engine.connect() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(models)").fetchall()
        names = {row[1] for row in cols}
        if "viz_artifacts" not in names:
            conn.exec_driver_sql("ALTER TABLE models ADD COLUMN viz_artifacts TEXT")
            conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

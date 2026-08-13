"""Shared pytest fixtures: isolated temp SQLite DB + TestClient.

No ML deps are imported here (or by anything under test); the heavy imports in
services/visualization etc. stay lazy. See docs/tests.md.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base, get_db
from app.main import app


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/test.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db):
    def override():
        yield db

    app.dependency_overrides[get_db] = override
    # No `with` — we intentionally skip the lifespan so the background worker
    # thread never starts (it would use the real SessionLocal, not this test db).
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def override_settings():
    """Temporarily set attributes on the frozen `settings` dataclass.

    Usage::

        def test_x(override_settings, tmp_path):
            override_settings(allowed_roots=[tmp_path], viz_cache_root=tmp_path)

    Every attribute touched is restored when the test ends, so leaking a root
    into an unrelated test is impossible.
    """
    from app.config import settings

    saved: dict[str, object] = {}

    def _apply(**kwargs) -> None:
        for key, value in kwargs.items():
            if key not in saved:
                saved[key] = getattr(settings, key)
            object.__setattr__(settings, key, value)

    yield _apply

    for key, value in saved.items():
        object.__setattr__(settings, key, value)

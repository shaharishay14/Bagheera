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

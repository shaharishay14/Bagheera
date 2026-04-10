"""Pytest fixtures for Bagheera backend + integration tests.

We point each test session at a temporary SQLite database, recreate the schema
fresh, and expose two app fixtures:

* ``client_no_worker`` — TestClient with the background worker disabled.
  Use this for unit tests that need full control of job state.
* ``client_with_worker`` — TestClient with the worker thread running.
  Use this for end-to-end queue flow tests.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Make backend importable. The backend lives at <repo>/backend.
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Each test session gets its own DB file.
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.name}"
os.environ["WORKER_ENABLED"] = "false"  # default; opted into per-test below

# Imported AFTER env vars are set so the settings module reads them.
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db import models  # noqa: E402,F401  (registers tables on Base)


@pytest.fixture(autouse=True)
def _reset_db():
    """Drop+recreate all tables between tests for full isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db_session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client_no_worker():
    os.environ["WORKER_ENABLED"] = "false"
    # Re-read settings so the lifespan sees worker disabled.
    from app import config as cfg
    cfg.settings.worker_enabled = False

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_with_worker(monkeypatch):
    """Worker-enabled client. Mock PANTHER is sped up to ~0.1s, no errors."""
    from app.workers import mock_panther

    monkeypatch.setattr(mock_panther, "SLEEP_MIN_SECONDS", 0.05)
    monkeypatch.setattr(mock_panther, "SLEEP_MAX_SECONDS", 0.15)
    monkeypatch.setattr(mock_panther, "ERROR_PROBABILITY", 0.0)

    from app import config as cfg
    cfg.settings.worker_enabled = True

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c


# ---------- Results recorder ----------
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)
_RESULTS: dict = {"tests": []}
_SESSION_START: float = 0.0


def pytest_sessionstart(session):  # noqa: D401 — pytest hook
    global _SESSION_START
    _SESSION_START = time.time()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        _RESULTS["tests"].append(
            {
                "id": item.nodeid,
                "outcome": report.outcome,
                "duration_s": round(report.duration, 4),
            }
        )


def pytest_sessionfinish(session, exitstatus):  # noqa: D401
    summary = {
        "started_utc": datetime.fromtimestamp(_SESSION_START, tz=timezone.utc).isoformat(),
        "finished_utc": datetime.now(tz=timezone.utc).isoformat(),
        "exit_status": int(exitstatus),
        "passed": sum(1 for t in _RESULTS["tests"] if t["outcome"] == "passed"),
        "failed": sum(1 for t in _RESULTS["tests"] if t["outcome"] == "failed"),
        "skipped": sum(1 for t in _RESULTS["tests"] if t["outcome"] == "skipped"),
        "tests": _RESULTS["tests"],
    }
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"run-{stamp}.json"
    out_path.write_text(json.dumps(summary, indent=2))

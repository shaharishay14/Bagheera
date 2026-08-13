"""Stub job handlers for the async worker (PR 1).

Real implementations land in later PRs:
- panther_train  → PR 2 (services/panther_runner.py drives K folds from here)
- post_train_viz → PR 3 (services/visualization.py render functions)
- inference      → PR 5 (services/inference.py TRIDENT + viz pipeline)

These stubs let us validate the worker loop end-to-end before wiring real work.
"""
from __future__ import annotations

import time
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import Job
from app.services.worker import JobLog, register_handler


def _stub(*, name: str, sleep_seconds: float) -> None:
    def handler(*, db: Session, job: Job, log: JobLog) -> None:  # noqa: ARG001 — signature contract
        log.write(f"[stub:{name}] handling job {job.id} ref={job.ref_table}:{job.ref_id}")
        log.write(f"[stub:{name}] sleeping {sleep_seconds}s to simulate work")
        time.sleep(sleep_seconds)
        log.write(f"[stub:{name}] done at {datetime.utcnow().isoformat()}Z")

    register_handler(name, handler)


def register_stub_handlers() -> None:
    """Register no-op handlers so all three job types are dispatchable.

    Replace these with real implementations as later PRs land — just call
    `register_handler(...)` from the real module's import path.
    """
    _stub(name="panther_train", sleep_seconds=1.0)
    _stub(name="post_train_viz", sleep_seconds=0.5)
    _stub(name="inference", sleep_seconds=1.0)

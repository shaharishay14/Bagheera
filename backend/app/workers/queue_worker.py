"""Background worker thread that drains the FIFO job queue.

Per design §5 the production system would split this into an Execution worker
and a Result worker. For the MVP — where PANTHER is mocked — a single thread
both claims and finalizes each job. The split is documented in tests/LESSONS.md.
"""
import logging
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Cluster, Job
from app.workers import mock_panther

logger = logging.getLogger("bagheera.worker")

_IDLE_SLEEP_SECONDS = 1.0


def _claim_next_job(db: Session) -> Job | None:
    """Atomically grab the next Queued job and flip it to Processing.

    SQLAlchemy's session manages a single transaction here; the SELECT and the
    status UPDATE commit together so a concurrent reorder PUT cannot slip in
    between them.
    """
    job = (
        db.query(Job)
        .filter(Job.status == "Queued")
        .order_by(Job.priority.asc(), Job.created_at.asc())
        .first()
    )
    if job is None:
        db.commit()
        return None
    job.status = "Processing"
    job.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def _process_job(db: Session, job: Job) -> None:
    try:
        outputs = mock_panther.run(job.num_clusters)
    except Exception as exc:  # noqa: BLE001 — we want to record any failure
        logger.exception("Job %s failed in mock_panther.run", job.id)
        db.query(Job).filter(Job.id == job.id).update(
            {"status": "Error", "error": str(exc), "finished_at": datetime.now(timezone.utc)}
        )
        db.commit()
        return

    for out in outputs:
        db.add(
            Cluster(
                id=uuid4().hex,
                job_id=job.id,
                label=out.label,
                patches_json=out.patches_json,
            )
        )
    db.query(Job).filter(Job.id == job.id).update(
        {"status": "Done", "finished_at": datetime.now(timezone.utc)}
    )
    db.commit()


def worker_loop(stop_event: threading.Event) -> None:
    logger.info("Bagheera mock worker started")
    while not stop_event.is_set():
        db = SessionLocal()
        try:
            job = _claim_next_job(db)
            if job is None:
                # release the session before sleeping so other connections aren't blocked
                db.close()
                if stop_event.wait(_IDLE_SLEEP_SECONDS):
                    return
                continue
            _process_job(db, job)
        except Exception:
            logger.exception("Worker loop iteration failed; continuing")
            time.sleep(_IDLE_SLEEP_SECONDS)
        finally:
            db.close()
    logger.info("Bagheera mock worker stopped")


def start_worker() -> tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    thread = threading.Thread(target=worker_loop, args=(stop_event,), daemon=True, name="bagheera-worker")
    thread.start()
    return thread, stop_event

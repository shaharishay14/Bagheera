"""Background worker thread that drains the `jobs` table sequentially.

One thread, one job at a time. No cancellation, no priorities — those land
in a real queue migration later. Adding new job types is just adding an entry
to HANDLERS.

TODO: implement job cancellation when a real queue (Redis/RQ, Celery, or
similar) replaces this single-thread polling loop. The current design
intentionally doesn't expose a cancel endpoint — the worker has no way to
interrupt a running subprocess cleanly without leaving partial output.
Adding cancellation here would require either signal handling on the worker
side or a "kill flag" the handler polls, both of which are out of scope
until we have a real queue.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import Job

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 2.0


class JobLog:
    """Append-only log file for one job. Always flushed."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a", buffering=1)  # line-buffered

    def write(self, text: str) -> None:
        if not text.endswith("\n"):
            text = text + "\n"
        self._fh.write(text)
        self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


class JobHandler(Protocol):
    def __call__(self, *, db: Session, job: Job, log: JobLog) -> None:
        ...


_HANDLERS: dict[str, JobHandler] = {}


def register_handler(job_type: str, handler: JobHandler) -> None:
    _HANDLERS[job_type] = handler


def get_handler(job_type: str) -> JobHandler | None:
    return _HANDLERS.get(job_type)


def _log_path_for(job_id: str) -> Path:
    return settings.viz_cache_root / "job_logs" / f"{job_id}.log"


def next_queue_position(db: Session) -> int:
    """Tail position for a newly queued / re-queued job (FIFO)."""
    max_pos = (
        db.query(func.max(Job.queue_position)).filter(Job.status == "queued").scalar()
    )
    return int(max_pos or 0) + 1


def _claim_next_job(db: Session) -> Job | None:
    """Claim the lowest-position queued job via compare-and-swap.

    If a user cancels the chosen job between the select and the claim, the
    conditional UPDATE matches 0 rows and we move on to the next one. This is
    what keeps cancel-vs-start races consistent without locks.
    """
    while True:
        job = (
            db.query(Job)
            .filter(Job.status == "queued")
            .order_by(Job.queue_position.asc(), Job.created_at.asc())
            .first()
        )
        if job is None:
            return None
        log_path = job.log_path or str(_log_path_for(job.id))
        claimed = (
            db.query(Job)
            .filter(Job.id == job.id, Job.status == "queued")
            .update(
                {
                    "status": "running",
                    "started_at": datetime.utcnow(),
                    "queue_position": None,
                    "log_path": log_path,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        if claimed == 1:
            db.refresh(job)
            return job
        # Lost the race (job canceled just now) — try the next queued job.


def _run_one_job(job: Job) -> None:
    log = JobLog(Path(job.log_path)) if job.log_path else JobLog(_log_path_for(job.id))
    db = SessionLocal()
    try:
        log.write(f"=== job {job.id} ({job.job_type}) start ref={job.ref_table}:{job.ref_id} ===")
        handler = get_handler(job.job_type)
        if handler is None:
            raise RuntimeError(f"No handler registered for job_type={job.job_type!r}")
        handler(db=db, job=job, log=log)
        # Re-fetch to mark complete on a fresh row in case the handler committed changes.
        row = db.get(Job, job.id)
        if row is not None:
            row.status = "succeeded"
            row.finished_at = datetime.utcnow()
            db.add(row)
            db.commit()
        log.write(f"=== job {job.id} succeeded ===")
    except Exception as exc:  # noqa: BLE001 — worker must never crash
        tb = traceback.format_exc()
        log.write(f"!!! job {job.id} failed: {exc}\n{tb}")
        row = db.get(Job, job.id)
        if row is not None:
            row.status = "failed"
            row.error_message = str(exc)[:2000]
            row.finished_at = datetime.utcnow()
            db.add(row)
            db.commit()
    finally:
        log.close()
        db.close()


def _worker_loop(stop_event: threading.Event) -> None:
    logger.info("Bagheera worker thread started")
    while not stop_event.is_set():
        try:
            db = SessionLocal()
            try:
                job = _claim_next_job(db)
            finally:
                db.close()
            if job is None:
                stop_event.wait(POLL_INTERVAL_SECONDS)
                continue
            _run_one_job(job)
        except Exception:  # noqa: BLE001
            logger.exception("Worker loop iteration raised; continuing")
            stop_event.wait(POLL_INTERVAL_SECONDS)
    logger.info("Bagheera worker thread stopping")


_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None


def start_worker() -> None:
    """Idempotent: starts the worker thread if not already running."""
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(
        target=_worker_loop,
        args=(_stop_event,),
        name="bagheera-worker",
        daemon=True,
    )
    _worker_thread.start()


def stop_worker(timeout: float = 5.0) -> None:
    _stop_event.set()
    if _worker_thread is not None:
        _worker_thread.join(timeout=timeout)


# ---------------------------------------------------------------------------
# Enqueue helper
# ---------------------------------------------------------------------------


def enqueue_job(
    db: Session,
    *,
    job_type: str,
    ref_table: str,
    ref_id: str,
) -> Job:
    """Create a queued job row. The worker thread will pick it up."""
    import uuid

    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        created_at=datetime.utcnow(),
        job_type=job_type,
        ref_table=ref_table,
        ref_id=ref_id,
        status="queued",
        log_path=str(_log_path_for(job_id)),
        queue_position=next_queue_position(db),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def tail_log(job: Job, *, max_chars: int = 8000) -> str:
    """Return the trailing portion of the job log file."""
    if not job.log_path:
        return ""
    path = Path(job.log_path)
    if not path.exists():
        return ""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size <= max_chars:
                f.seek(0)
                return f.read().decode("utf-8", errors="replace")
            f.seek(size - max_chars)
            chunk = f.read().decode("utf-8", errors="replace")
        # Drop the first (likely partial) line so the tail starts on a boundary.
        nl = chunk.find("\n")
        return chunk[nl + 1 :] if nl != -1 else chunk
    except OSError:
        return ""

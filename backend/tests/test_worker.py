"""The job queue's engine: handler registry, FIFO claim CAS, and job execution.

`_run_one_job` is driven with fake handlers, so no subprocess, no ML import and
no real TRIDENT/PANTHER run is ever triggered. The database is the temp SQLite
file from the `db` fixture; the worker gets its own sessions on the same engine,
which is what makes the compare-and-swap races observable.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models import Job
from app.services import worker
from app.services.worker import (
    JobLog,
    _claim_next_job,
    _run_one_job,
    enqueue_job,
    get_handler,
    next_queue_position,
    register_handler,
    tail_log,
)


@pytest.fixture()
def logs_root(tmp_path, override_settings):
    """Send job logs into a temp viz cache instead of the real one."""
    root = tmp_path / "viz_cache"
    (root / "job_logs").mkdir(parents=True)
    override_settings(viz_cache_root=root)
    return root


@pytest.fixture()
def worker_sessions(db, monkeypatch):
    """Point the worker's SessionLocal at the same engine as the test session."""
    monkeypatch.setattr(worker, "SessionLocal", sessionmaker(bind=db.get_bind()))


@pytest.fixture()
def isolated_handlers(monkeypatch):
    """Swap in an empty handler registry so tests can't disturb the real one."""
    monkeypatch.setattr(worker, "_HANDLERS", {})


def _job(db, *, status="queued", position=None, job_type="stub", created_offset=0) -> Job:
    row = Job(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow() + timedelta(seconds=created_offset),
        job_type=job_type,
        ref_table="models",
        ref_id="ref-1",
        status=status,
        queue_position=position,
    )
    db.add(row)
    db.commit()
    return row


# --- handler registry -----------------------------------------------------


def test_registering_a_handler_makes_it_retrievable(isolated_handlers):
    def handler(*, db, job, log):
        pass

    register_handler("my_type", handler)
    assert get_handler("my_type") is handler


def test_unknown_job_type_has_no_handler(isolated_handlers):
    assert get_handler("never_registered") is None


def test_registering_the_same_type_twice_overwrites(isolated_handlers):
    def first(*, db, job, log):
        pass

    def second(*, db, job, log):
        pass

    register_handler("t", first)
    register_handler("t", second)
    assert get_handler("t") is second


def test_all_production_job_types_have_a_handler():
    """main._register_handlers must cover every job_type the routes enqueue."""
    from app.main import _register_handlers

    _register_handlers()
    for job_type in ("panther_train", "post_train_viz", "inference", "render_slide"):
        assert get_handler(job_type) is not None, job_type


# --- enqueue_job / next_queue_position ------------------------------------


def test_first_enqueued_job_takes_position_one(db, logs_root):
    job = enqueue_job(db, job_type="stub", ref_table="models", ref_id="m1")
    assert job.status == "queued"
    assert job.queue_position == 1


def test_enqueue_appends_to_the_tail_in_fifo_order(db, logs_root):
    positions = [
        enqueue_job(db, job_type="stub", ref_table="models", ref_id=f"m{i}").queue_position
        for i in range(3)
    ]
    assert positions == [1, 2, 3]


def test_enqueue_serializes_params_as_json(db, logs_root):
    job = enqueue_job(
        db, job_type="render_slide", ref_table="models", ref_id="m1",
        params={"slide_id": "S1"},
    )
    import json

    assert json.loads(job.params) == {"slide_id": "S1"}


def test_enqueue_leaves_params_null_when_none_given(db, logs_root):
    job = enqueue_job(db, job_type="stub", ref_table="models", ref_id="m1")
    assert job.params is None


def test_enqueue_assigns_a_log_path_under_the_viz_cache(db, logs_root):
    job = enqueue_job(db, job_type="stub", ref_table="models", ref_id="m1")
    assert job.log_path == str(logs_root / "job_logs" / f"{job.id}.log")


def test_next_position_ignores_finished_jobs(db, logs_root):
    _job(db, status="succeeded", position=None)
    _job(db, status="queued", position=7)
    assert next_queue_position(db) == 8


def test_next_position_is_one_on_an_empty_queue(db):
    assert next_queue_position(db) == 1


# --- _claim_next_job (compare-and-swap) -----------------------------------


def test_claim_takes_the_lowest_queue_position(db):
    _job(db, position=3)
    winner = _job(db, position=1)
    _job(db, position=2)
    claimed = _claim_next_job(db)
    assert claimed.id == winner.id


def test_claim_breaks_position_ties_by_creation_time(db):
    older = _job(db, position=1, created_offset=-60)
    _job(db, position=1, created_offset=0)
    assert _claim_next_job(db).id == older.id


def test_claim_marks_the_job_running_and_clears_its_position(db):
    _job(db, position=1)
    claimed = _claim_next_job(db)
    assert claimed.status == "running"
    assert claimed.queue_position is None
    assert claimed.started_at is not None


def test_claim_fills_in_a_missing_log_path(db, logs_root):
    job = _job(db, position=1)
    assert job.log_path is None
    assert _claim_next_job(db).log_path == str(logs_root / "job_logs" / f"{job.id}.log")


def test_claim_returns_none_when_nothing_is_queued(db):
    _job(db, status="succeeded")
    _job(db, status="running")
    assert _claim_next_job(db) is None


def test_claim_skips_a_job_canceled_between_select_and_update(db, monkeypatch):
    """The cancel-vs-start race: the CAS matches 0 rows and the worker moves on."""
    from sqlalchemy.orm import Query

    doomed = _job(db, position=1)
    survivor = _job(db, position=2)

    real_first = Query.first
    interfered = {"done": False}

    def first_then_cancel(self):
        row = real_first(self)
        # Cancel the chosen job right after it is selected, before the CAS lands.
        if not interfered["done"] and row is not None and row.id == doomed.id:
            interfered["done"] = True
            db.query(Job).filter(Job.id == doomed.id).update(
                {"status": "canceled"}, synchronize_session=False
            )
            db.commit()
        return row

    monkeypatch.setattr(Query, "first", first_then_cancel)
    claimed = _claim_next_job(db)
    monkeypatch.undo()

    assert interfered["done"] is True
    assert claimed is not None
    assert claimed.id == survivor.id
    assert db.get(Job, doomed.id).status == "canceled"


# --- _run_one_job ---------------------------------------------------------


def test_successful_handler_marks_the_job_succeeded(
    db, logs_root, worker_sessions, isolated_handlers
):
    ran = {"called": False}

    def handler(*, db, job, log):
        ran["called"] = True
        log.write("doing work")

    register_handler("ok", handler)
    job = enqueue_job(db, job_type="ok", ref_table="models", ref_id="m1")
    _run_one_job(_claim_next_job(db))

    db.expire_all()
    row = db.get(Job, job.id)
    assert ran["called"] is True
    assert row.status == "succeeded"
    assert row.finished_at is not None
    assert row.error_message is None


def test_raising_handler_marks_the_job_failed_without_crashing_the_worker(
    db, logs_root, worker_sessions, isolated_handlers
):
    def handler(*, db, job, log):
        raise RuntimeError("boom in the handler")

    register_handler("bad", handler)
    job = enqueue_job(db, job_type="bad", ref_table="models", ref_id="m1")
    _run_one_job(_claim_next_job(db))  # must not raise

    db.expire_all()
    row = db.get(Job, job.id)
    assert row.status == "failed"
    assert "boom in the handler" in row.error_message
    assert row.finished_at is not None


def test_missing_handler_fails_the_job_rather_than_the_worker(
    db, logs_root, worker_sessions, isolated_handlers
):
    job = enqueue_job(db, job_type="no_such_type", ref_table="models", ref_id="m1")
    _run_one_job(_claim_next_job(db))

    db.expire_all()
    row = db.get(Job, job.id)
    assert row.status == "failed"
    assert "no_such_type" in row.error_message


def test_failure_traceback_lands_in_the_job_log(
    db, logs_root, worker_sessions, isolated_handlers
):
    def handler(*, db, job, log):
        raise ValueError("explode")

    register_handler("bad", handler)
    job = enqueue_job(db, job_type="bad", ref_table="models", ref_id="m1")
    _run_one_job(_claim_next_job(db))

    text = (logs_root / "job_logs" / f"{job.id}.log").read_text()
    assert "explode" in text
    assert "Traceback" in text


def test_error_message_is_truncated_to_the_column_width(
    db, logs_root, worker_sessions, isolated_handlers
):
    def handler(*, db, job, log):
        raise RuntimeError("x" * 5000)

    register_handler("bad", handler)
    job = enqueue_job(db, job_type="bad", ref_table="models", ref_id="m1")
    _run_one_job(_claim_next_job(db))

    db.expire_all()
    assert len(db.get(Job, job.id).error_message) == 2000


def test_log_records_the_start_and_success_banners(
    db, logs_root, worker_sessions, isolated_handlers
):
    register_handler("ok", lambda *, db, job, log: None)
    job = enqueue_job(db, job_type="ok", ref_table="models", ref_id="m1")
    _run_one_job(_claim_next_job(db))

    text = (logs_root / "job_logs" / f"{job.id}.log").read_text()
    assert f"job {job.id} (ok) start" in text
    assert f"job {job.id} succeeded" in text


# --- JobLog + tail_log ----------------------------------------------------


def test_joblog_creates_parent_dirs_and_appends_newlines(tmp_path):
    log = JobLog(tmp_path / "deep" / "nested" / "a.log")
    log.write("line one")
    log.write("line two\n")
    log.close()
    assert (tmp_path / "deep" / "nested" / "a.log").read_text() == "line one\nline two\n"


def test_joblog_close_is_safe_to_call_twice(tmp_path):
    log = JobLog(tmp_path / "a.log")
    log.close()
    log.close()  # must not raise


def test_tail_returns_the_whole_log_when_it_is_small(db, tmp_path):
    path = tmp_path / "a.log"
    path.write_text("short log\n")
    job = _job(db)
    job.log_path = str(path)
    assert tail_log(job) == "short log\n"


def test_tail_truncates_from_a_line_boundary(db, tmp_path):
    path = tmp_path / "a.log"
    path.write_text("".join(f"line {i}\n" for i in range(2000)))
    job = _job(db)
    job.log_path = str(path)
    tail = tail_log(job, max_chars=100)
    assert len(tail) < 100
    assert tail.startswith("line ")
    assert tail.endswith("line 1999\n")


def test_tail_is_empty_when_the_job_has_no_log_path(db):
    assert tail_log(_job(db)) == ""


def test_tail_is_empty_when_the_log_file_is_missing(db, tmp_path):
    job = _job(db)
    job.log_path = str(tmp_path / "gone.log")
    assert tail_log(job) == ""

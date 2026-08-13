"""HTTP surface of /api/jobs — filtering, log tail, cancel CAS, retry."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.db.models import Job


@pytest.fixture()
def logs_root(tmp_path, override_settings):
    root = tmp_path / "viz_cache"
    (root / "job_logs").mkdir(parents=True)
    override_settings(viz_cache_root=root)
    return root


def _job(
    db,
    *,
    status="queued",
    job_type="panther_train",
    ref_table="model_groups",
    ref_id="ref-1",
    position=None,
    created_offset=0,
    log_path=None,
) -> Job:
    row = Job(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow() + timedelta(seconds=created_offset),
        job_type=job_type,
        ref_table=ref_table,
        ref_id=ref_id,
        status=status,
        queue_position=position,
        log_path=log_path,
    )
    db.add(row)
    db.commit()
    return row


# --- GET /api/jobs --------------------------------------------------------


def test_list_returns_newest_first(client, db):
    old = _job(db, created_offset=-60)
    new = _job(db, created_offset=0)
    ids = [j["id"] for j in client.get("/api/jobs").json()]
    assert ids == [new.id, old.id]


def test_list_filters_by_status(client, db):
    queued = _job(db, status="queued")
    _job(db, status="failed")
    body = client.get("/api/jobs", params={"status": "queued"}).json()
    assert [j["id"] for j in body] == [queued.id]


def test_list_filters_by_job_type(client, db):
    viz = _job(db, job_type="post_train_viz")
    _job(db, job_type="panther_train")
    body = client.get("/api/jobs", params={"job_type": "post_train_viz"}).json()
    assert [j["id"] for j in body] == [viz.id]


def test_list_filters_by_ref_table_and_ref_id(client, db):
    mine = _job(db, ref_table="models", ref_id="model-42")
    _job(db, ref_table="models", ref_id="model-99")
    _job(db, ref_table="model_groups", ref_id="model-42")
    body = client.get(
        "/api/jobs", params={"ref_table": "models", "ref_id": "model-42"}
    ).json()
    assert [j["id"] for j in body] == [mine.id]


def test_list_honors_the_limit(client, db):
    for i in range(5):
        _job(db, created_offset=i)
    assert len(client.get("/api/jobs", params={"limit": 2}).json()) == 2


def test_list_rejects_a_limit_above_the_cap(client, db):
    assert client.get("/api/jobs", params={"limit": 501}).status_code == 422


def test_list_is_empty_on_a_fresh_database(client, db):
    assert client.get("/api/jobs").json() == []


# --- GET /api/jobs/{id} ---------------------------------------------------


def test_detail_includes_the_log_tail(client, db, tmp_path):
    log = tmp_path / "j.log"
    log.write_text("first line\nsecond line\n")
    job = _job(db, log_path=str(log))
    body = client.get(f"/api/jobs/{job.id}").json()
    assert body["id"] == job.id
    assert body["log_tail"] == "first line\nsecond line\n"


def test_detail_log_tail_is_empty_when_the_file_is_missing(client, db, tmp_path):
    job = _job(db, log_path=str(tmp_path / "gone.log"))
    assert client.get(f"/api/jobs/{job.id}").json()["log_tail"] == ""


def test_detail_404_for_an_unknown_job(client, db):
    assert client.get("/api/jobs/does-not-exist").status_code == 404


# --- POST /api/jobs/{id}/cancel -------------------------------------------


def test_cancel_moves_a_queued_job_to_canceled(client, db):
    job = _job(db, status="queued", position=1)
    resp = client.post(f"/api/jobs/{job.id}/cancel")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "canceled"
    assert body["queue_position"] is None


def test_cancel_stamps_finished_at(client, db):
    job = _job(db, status="queued", position=1)
    client.post(f"/api/jobs/{job.id}/cancel")
    db.expire_all()
    assert db.get(Job, job.id).finished_at is not None


def test_cancel_409_on_a_running_job(client, db):
    """The CAS matches 0 rows once the worker has claimed the job."""
    job = _job(db, status="running")
    resp = client.post(f"/api/jobs/{job.id}/cancel")
    assert resp.status_code == 409
    assert "running" in resp.json()["detail"]


@pytest.mark.parametrize("terminal", ["succeeded", "failed", "canceled"])
def test_cancel_409_on_a_terminal_job(client, db, terminal):
    job = _job(db, status=terminal)
    assert client.post(f"/api/jobs/{job.id}/cancel").status_code == 409


def test_cancel_404_for_an_unknown_job(client, db):
    assert client.post("/api/jobs/nope/cancel").status_code == 404


# --- POST /api/jobs/{id}/retry --------------------------------------------


@pytest.mark.parametrize("terminal", ["failed", "succeeded", "canceled"])
def test_retry_requeues_a_terminal_job(client, db, terminal):
    job = _job(db, status=terminal)
    body = client.post(f"/api/jobs/{job.id}/retry").json()
    assert body["status"] == "queued"
    assert body["queue_position"] == 1


def test_retry_clears_the_previous_run_metadata(client, db):
    job = _job(db, status="failed")
    job.error_message = "old failure"
    job.started_at = datetime.utcnow()
    job.finished_at = datetime.utcnow()
    db.add(job)
    db.commit()

    body = client.post(f"/api/jobs/{job.id}/retry").json()
    assert body["error_message"] is None
    assert body["started_at"] is None
    assert body["finished_at"] is None


def test_retry_lands_at_the_back_of_the_queue(client, db):
    _job(db, status="queued", position=1)
    _job(db, status="queued", position=2)
    failed = _job(db, status="failed")
    assert client.post(f"/api/jobs/{failed.id}/retry").json()["queue_position"] == 3


@pytest.mark.parametrize("active", ["queued", "running"])
def test_retry_409_while_the_job_is_still_active(client, db, active):
    job = _job(db, status=active)
    assert client.post(f"/api/jobs/{job.id}/retry").status_code == 409


def test_retry_404_for_an_unknown_job(client, db):
    assert client.post("/api/jobs/nope/retry").status_code == 404

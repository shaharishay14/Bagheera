"""Job queue tests, including TC-01 (priority reorder) and TC-02 (job lock)."""
from datetime import timezone

from app.db.database import SessionLocal
from app.db.models import Job


def _enqueue(client, dataset_id: str, num_clusters: int = 3) -> str:
    res = client.post(
        "/api/v1/inference",
        json={"dataset_id": dataset_id, "num_clusters": num_clusters},
    )
    assert res.status_code == 200
    return res.json()["job_id"]


def test_jobs_listed_in_fifo_order(client_no_worker):
    j1 = _enqueue(client_no_worker, "slide_1")
    j2 = _enqueue(client_no_worker, "slide_2")
    j3 = _enqueue(client_no_worker, "slide_3")

    listed = client_no_worker.get("/api/v1/jobs").json()
    assert [j["id"] for j in listed] == [j1, j2, j3]


def test_get_job_status(client_no_worker):
    jid = _enqueue(client_no_worker, "slide_a")
    res = client_no_worker.get(f"/api/v1/jobs/{jid}/status")
    assert res.status_code == 200
    body = res.json()
    assert body == {"job_id": jid, "status": "Queued", "progress": 0}


def test_get_job_status_unknown_id(client_no_worker):
    assert client_no_worker.get("/api/v1/jobs/doesnotexist/status").status_code == 404


def test_tc01_reorder_promotes_third_job(client_no_worker):
    """TC-01: drag job 3 to top, system updates execution order."""
    j1 = _enqueue(client_no_worker, "slide_1")
    j2 = _enqueue(client_no_worker, "slide_2")
    j3 = _enqueue(client_no_worker, "slide_3")

    res = client_no_worker.put(
        "/api/v1/jobs/reorder", json={"ordered_job_ids": [j3, j1, j2]}
    )
    assert res.status_code == 200

    listed = client_no_worker.get("/api/v1/jobs").json()
    assert [j["id"] for j in listed] == [j3, j1, j2]
    assert [j["priority"] for j in listed] == [0, 1, 2]


def test_tc02_reorder_rejected_when_job_processing(client_no_worker):
    """TC-02: a job in Processing state cannot be reordered (409)."""
    j1 = _enqueue(client_no_worker, "slide_1")
    j2 = _enqueue(client_no_worker, "slide_2")

    # Manually flip j1 to Processing to simulate the worker having claimed it.
    db = SessionLocal()
    try:
        db.query(Job).filter(Job.id == j1).update({"status": "Processing"})
        db.commit()
    finally:
        db.close()

    res = client_no_worker.put(
        "/api/v1/jobs/reorder", json={"ordered_job_ids": [j2, j1]}
    )
    assert res.status_code == 409
    assert "Processing" in res.json()["detail"] or j1 in res.json()["detail"]


def test_reorder_unknown_id_returns_404(client_no_worker):
    j1 = _enqueue(client_no_worker, "slide_1")
    res = client_no_worker.put(
        "/api/v1/jobs/reorder", json={"ordered_job_ids": [j1, "ghost"]}
    )
    assert res.status_code == 404


def test_reorder_empty_list_rejected(client_no_worker):
    res = client_no_worker.put("/api/v1/jobs/reorder", json={"ordered_job_ids": []})
    assert res.status_code == 400


def test_reorder_partial_list_does_not_corrupt_fifo(client_no_worker):
    j1 = _enqueue(client_no_worker, "slide_1")
    j2 = _enqueue(client_no_worker, "slide_2")
    j3 = _enqueue(client_no_worker, "slide_3")
    j4 = _enqueue(client_no_worker, "slide_4")

    res = client_no_worker.put(
        "/api/v1/jobs/reorder", json={"ordered_job_ids": [j2, j1]}
    )
    assert res.status_code == 200

    listed = client_no_worker.get("/api/v1/jobs").json()
    assert [j["id"] for j in listed] == [j2, j1, j3, j4]


def test_reorder_single_job_renormalizes_all_queued(client_no_worker):
    """Promote one job; verify priorities are contiguous with no collisions."""
    j1 = _enqueue(client_no_worker, "slide_1")
    j2 = _enqueue(client_no_worker, "slide_2")
    j3 = _enqueue(client_no_worker, "slide_3")
    j4 = _enqueue(client_no_worker, "slide_4")

    res = client_no_worker.put(
        "/api/v1/jobs/reorder", json={"ordered_job_ids": [j3]}
    )
    assert res.status_code == 200

    listed = client_no_worker.get("/api/v1/jobs").json()
    assert [j["id"] for j in listed] == [j3, j1, j2, j4]
    assert [j["priority"] for j in listed] == [0, 1, 2, 3]


def test_job_created_at_is_tzaware(client_no_worker):
    jid = _enqueue(client_no_worker, "slide_tz")
    db = SessionLocal()
    try:
        db.expire_all()
        job = db.get(Job, jid)
        assert job.created_at.tzinfo is not None
        assert job.created_at.tzinfo.utcoffset(job.created_at).total_seconds() == 0
    finally:
        db.close()

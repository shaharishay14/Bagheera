"""End-to-end queue flow: enqueue 5 jobs, let the worker drain, verify FIFO + reorder."""
import time

from app.db.database import SessionLocal
from app.db.models import Job


POLL_TIMEOUT_S = 30
POLL_INTERVAL_S = 0.1


def _wait_for_all_finished(client, job_ids):
    deadline = time.time() + POLL_TIMEOUT_S
    while time.time() < deadline:
        listed = client.get("/api/v1/jobs").json()
        statuses = {j["id"]: j["status"] for j in listed}
        if all(statuses.get(jid) in ("Done", "Error") for jid in job_ids):
            return listed
        time.sleep(POLL_INTERVAL_S)
    raise AssertionError(f"Timed out waiting for jobs to finish: {statuses}")


def test_queue_drains_in_fifo_order(client_with_worker):
    job_ids = []
    for i in range(5):
        res = client_with_worker.post(
            "/api/v1/inference",
            json={"dataset_id": f"slide_{i}", "num_clusters": 3},
        )
        assert res.status_code == 200
        job_ids.append(res.json()["job_id"])

    finished = _wait_for_all_finished(client_with_worker, job_ids)
    assert all(j["status"] == "Done" for j in finished)

    # Verify FIFO: started_at must be monotonic in the original submission order.
    db = SessionLocal()
    try:
        rows = [db.get(Job, jid) for jid in job_ids]
        starts = [r.started_at for r in rows]
        assert all(starts[i] <= starts[i + 1] for i in range(len(starts) - 1)), (
            f"Jobs did not start in FIFO order: {starts}"
        )
    finally:
        db.close()


def test_reorder_then_drain_respects_new_order(client_with_worker):
    """Submit 3 jobs, reorder so job 3 runs first, verify it actually runs first.

    To make this deterministic we submit while a placeholder Processing job
    blocks the queue, then clear it once reorder is in place.
    """
    # Use a manual DB-side hold: insert a Processing sentinel so the worker
    # doesn't drain anything until we release it.
    db = SessionLocal()
    try:
        from uuid import uuid4
        from datetime import datetime

        sentinel = Job(
            id=uuid4().hex,
            dataset_id="__sentinel__",
            num_clusters=2,
            status="Processing",
            priority=-1,
            created_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
        )
        db.add(sentinel)
        db.commit()
    finally:
        db.close()

    j1 = client_with_worker.post(
        "/api/v1/inference", json={"dataset_id": "slide_1", "num_clusters": 3}
    ).json()["job_id"]
    j2 = client_with_worker.post(
        "/api/v1/inference", json={"dataset_id": "slide_2", "num_clusters": 3}
    ).json()["job_id"]
    j3 = client_with_worker.post(
        "/api/v1/inference", json={"dataset_id": "slide_3", "num_clusters": 3}
    ).json()["job_id"]

    # Reorder: j3 first, then j1, then j2.
    res = client_with_worker.put(
        "/api/v1/jobs/reorder", json={"ordered_job_ids": [j3, j1, j2]}
    )
    assert res.status_code == 200

    # Release the sentinel so the worker can drain.
    db = SessionLocal()
    try:
        db.query(Job).filter(Job.dataset_id == "__sentinel__").update({"status": "Done"})
        db.commit()
    finally:
        db.close()

    _wait_for_all_finished(client_with_worker, [j1, j2, j3])

    db = SessionLocal()
    try:
        rows = {jid: db.get(Job, jid) for jid in (j1, j2, j3)}
        order = sorted(rows.values(), key=lambda r: r.started_at)
        assert [r.id for r in order] == [j3, j1, j2], (
            f"Expected reordered execution j3,j1,j2; got {[r.id for r in order]}"
        )
    finally:
        db.close()

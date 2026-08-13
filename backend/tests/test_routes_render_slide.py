"""HTTP + enqueue tests for the on-demand per-slide render flow.

The worker is never started (see conftest: no lifespan), so POST /render-slide
only creates a queued job row; no real renderer runs (no ML deps needed).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest

from app.config import settings
from app.db.models import Job, Model
from app.services.worker import enqueue_job


@pytest.fixture()
def viz_root(tmp_path, monkeypatch):
    """Point settings.viz_cache_root at a temp dir (frozen dataclass override)."""
    original = settings.viz_cache_root
    object.__setattr__(settings, "viz_cache_root", tmp_path / "viz_cache")
    (tmp_path / "viz_cache" / "job_logs").mkdir(parents=True, exist_ok=True)
    yield tmp_path
    object.__setattr__(settings, "viz_cache_root", original)


def _make_model(db, features_dir) -> Model:
    mid = str(uuid.uuid4())
    m = Model(
        id=mid,
        created_at=datetime.utcnow(),
        base_name="m",
        model_name=f"m_{mid[:8]}",
        display_name="M",
        group_id=mid,
        fold_index=0,
        fold_k=1,
        run_kind="single",
        dataset_name="ds",
        features_dir=str(features_dir),
        split_id=str(uuid.uuid4()),
        split_name="sp",
        mode="faiss",
        in_dim=1024,
        n_proto_patches=1000,
        n_proto=8,
        n_init=1,
        seed=1,
        num_workers=0,
        status="ready",
    )
    db.add(m)
    db.commit()
    return m


def test_render_slide_enqueues_when_no_manifest(client, db, tmp_path, viz_root):
    features = tmp_path / "features"
    features.mkdir()
    (features / "slideA.h5").write_bytes(b"")  # existence is all the route checks
    model = _make_model(db, features)

    resp = client.post(f"/api/models/{model.id}/render-slide", json={"slide_id": "slideA"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "rendering"
    assert body["job_id"]
    assert body["artifacts"] is None

    jobs = db.query(Job).all()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == body["job_id"]
    assert job.job_type == "render_slide"
    assert job.ref_table == "models"
    assert job.ref_id == model.id
    assert job.status == "queued"
    assert json.loads(job.params) == {"slide_id": "slideA"}


def test_render_slide_ready_on_cached_manifest(client, db, tmp_path, viz_root):
    features = tmp_path / "features"
    features.mkdir()
    (features / "slideA.h5").write_bytes(b"")
    model = _make_model(db, features)

    # Pre-create a manifest in the compare dir → cache hit, no job.
    compare_dir = viz_root / "viz_cache" / model.id / "compare" / "slideA"
    compare_dir.mkdir(parents=True)
    manifest = {"slide_id": "slideA", "thumbnail": "/abs/thumb.png", "violin": "/abs/v.png"}
    (compare_dir / "manifest.json").write_text(json.dumps(manifest))

    resp = client.post(f"/api/models/{model.id}/render-slide", json={"slide_id": "slideA"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert body["job_id"] is None
    assert body["artifacts"] == manifest
    # No job was enqueued for a cache hit.
    assert db.query(Job).count() == 0


def test_render_slide_422_when_h5_absent(client, db, tmp_path, viz_root):
    features = tmp_path / "features"
    features.mkdir()  # no slideA.h5 inside
    model = _make_model(db, features)

    resp = client.post(f"/api/models/{model.id}/render-slide", json={"slide_id": "slideA"})
    assert resp.status_code == 422, resp.text
    assert db.query(Job).count() == 0


def test_render_slide_422_on_bad_slide_id(client, db, tmp_path, viz_root):
    features = tmp_path / "features"
    features.mkdir()
    model = _make_model(db, features)

    resp = client.post(
        f"/api/models/{model.id}/render-slide", json={"slide_id": "../etc/passwd"}
    )
    assert resp.status_code == 422, resp.text
    assert db.query(Job).count() == 0


def test_render_slide_404_missing_model(client, db, viz_root):
    resp = client.post("/api/models/nope/render-slide", json={"slide_id": "slideA"})
    assert resp.status_code == 404


def test_slide_viz_missing_then_ready(client, db, tmp_path, viz_root):
    features = tmp_path / "features"
    features.mkdir()
    (features / "slideA.h5").write_bytes(b"")
    model = _make_model(db, features)

    resp = client.get(f"/api/models/{model.id}/slide-viz", params={"slide_id": "slideA"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "missing"

    compare_dir = viz_root / "viz_cache" / model.id / "compare" / "slideA"
    compare_dir.mkdir(parents=True)
    manifest = {"slide_id": "slideA", "on_tissue": "/abs/ot.png"}
    (compare_dir / "manifest.json").write_text(json.dumps(manifest))

    resp = client.get(f"/api/models/{model.id}/slide-viz", params={"slide_id": "slideA"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["artifacts"] == manifest


def test_enqueue_job_params_roundtrip(db, viz_root):
    job = enqueue_job(
        db, job_type="render_slide", ref_table="models", ref_id="m1",
        params={"slide_id": "S1", "n": 3},
    )
    row = db.get(Job, job.id)
    assert json.loads(row.params) == {"slide_id": "S1", "n": 3}

    # No params → NULL column.
    job2 = enqueue_job(db, job_type="post_train_viz", ref_table="models", ref_id="m1")
    assert db.get(Job, job2.id).params is None

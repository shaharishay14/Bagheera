"""HTTP-level tests for the standalone single PANTHER run endpoint.

The worker is never started (see conftest: no lifespan), so posting the run only
creates rows + a queued job; no PANTHER subprocess runs.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest

from app.config import settings
from app.db.models import Job, Model, ModelGroup, Split


@pytest.fixture()
def panther_env(tmp_path, monkeypatch):
    """Point PANTHER_REPO_PATH at a temp dir and allow the temp tree in the sandbox."""
    repo = tmp_path / "panther"
    (repo / "src").mkdir(parents=True)
    features = tmp_path / "features_uni_v2"
    features.mkdir()

    # settings is a frozen dataclass; use object.__setattr__ to override the repo
    # path, and mutate the (mutable) allowed_roots list in place. Both restored below.
    original_repo = settings.panther_repo_path
    original_roots = list(settings.allowed_roots)
    object.__setattr__(settings, "panther_repo_path", str(repo))
    settings.allowed_roots.append(tmp_path.resolve())
    yield {"features": features}
    object.__setattr__(settings, "panther_repo_path", original_repo)
    settings.allowed_roots.clear()
    settings.allowed_roots.extend(original_roots)


def _make_single_split(db) -> Split:
    row = Split(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        dataset_name="ds",
        split_name="alltrain_seed_1_deadbeef",
        abs_path="/tmp/ds/alltrain_seed_1_deadbeef",
        source_csv="/tmp/source.csv",
        k=1,
        seed=1,
        total_rows=10,
        per_fold_counts=json.dumps([{"train": 10, "val": 0, "test": 0}]),
    )
    db.add(row)
    db.commit()
    return row


def test_single_run_creates_one_model_no_group(client, db, panther_env):
    split = _make_single_split(db)

    resp = client.post(
        "/api/panther/single-runs",
        json={
            "model_name": "my_model",
            "features_dir": str(panther_env["features"]),
            "dataset_name": "ds",
            "split_id": split.id,
            "mode": "faiss",
            "n_proto": 8,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["split_id"] == split.id
    assert body["split_name"] == split.split_name

    models = db.query(Model).all()
    assert len(models) == 1
    m = models[0]
    assert m.id == body["model_id"]
    assert m.run_kind == "single"
    assert m.group_id == m.id
    assert m.fold_index == 0
    assert m.fold_k == 1
    assert m.n_proto == 8
    assert m.status == "running"
    assert m.model_name.startswith("my_model_")
    assert m.model_name != "my_model"  # rand8 suffix appended

    # No ModelGroup row is created for a standalone run.
    assert db.query(ModelGroup).count() == 0

    # Exactly one queued (models, panther_train) job was enqueued.
    jobs = db.query(Job).all()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == body["job_id"]
    assert job.ref_table == "models"
    assert job.ref_id == m.id
    assert job.job_type == "panther_train"
    assert job.status == "queued"


def test_single_run_rejects_dataset_mismatch(client, db, panther_env):
    split = _make_single_split(db)
    resp = client.post(
        "/api/panther/single-runs",
        json={
            "model_name": "m",
            "features_dir": str(panther_env["features"]),
            "dataset_name": "other",
            "split_id": split.id,
        },
    )
    assert resp.status_code == 400
    assert db.query(Model).count() == 0


def test_single_run_rejects_bad_features_dir(client, db, panther_env):
    split = _make_single_split(db)
    resp = client.post(
        "/api/panther/single-runs",
        json={
            "model_name": "m",
            "features_dir": str(panther_env["features"] / "does_not_exist"),
            "dataset_name": "ds",
            "split_id": split.id,
        },
    )
    assert resp.status_code == 400
    assert db.query(Model).count() == 0


def test_list_models_run_kind_filter(client, db, panther_env):
    split = _make_single_split(db)
    client.post(
        "/api/panther/single-runs",
        json={
            "model_name": "m",
            "features_dir": str(panther_env["features"]),
            "dataset_name": "ds",
            "split_id": split.id,
        },
    )
    single = client.get("/api/panther/models?run_kind=single").json()
    assert len(single) == 1
    assert single[0]["run_kind"] == "single"

    legacy = client.get("/api/panther/models?run_kind=kfold").json()
    assert legacy == []

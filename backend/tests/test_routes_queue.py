"""The Queue page contract: running/waiting/recent buckets, labels, reorder."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pytest

from app.db.models import Inference, Job, Model, ModelGroup
from app.routes.queue import RECENT_LIMIT


def _job(
    db,
    *,
    status="queued",
    job_type="panther_train",
    ref_table="model_groups",
    ref_id="ref-1",
    position=None,
    created_offset=0,
    started_offset=None,
    finished_offset=None,
    params=None,
) -> Job:
    now = datetime.utcnow()
    row = Job(
        id=str(uuid.uuid4()),
        created_at=now + timedelta(seconds=created_offset),
        started_at=None if started_offset is None else now + timedelta(seconds=started_offset),
        finished_at=None if finished_offset is None else now + timedelta(seconds=finished_offset),
        job_type=job_type,
        ref_table=ref_table,
        ref_id=ref_id,
        status=status,
        queue_position=position,
        params=None if params is None else json.dumps(params),
    )
    db.add(row)
    db.commit()
    return row


def _group(db, *, display_name="My run", k=5, dataset_name="ds") -> ModelGroup:
    row = ModelGroup(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        display_name=display_name,
        dataset_name=dataset_name,
        k=k,
        split_id=str(uuid.uuid4()),
    )
    db.add(row)
    db.commit()
    return row


def _model(db, *, display_name="Fold model", fold_index=0, fold_k=5) -> Model:
    mid = str(uuid.uuid4())
    row = Model(
        id=mid,
        created_at=datetime.utcnow(),
        base_name="m",
        model_name=f"m_{mid[:8]}",
        display_name=display_name,
        group_id=str(uuid.uuid4()),
        fold_index=fold_index,
        fold_k=fold_k,
        dataset_name="ds",
        features_dir="/feats",
        split_id=str(uuid.uuid4()),
        split_name="sp",
        mode="faiss",
        in_dim=1024,
        n_proto_patches=1000,
        n_proto=8,
        n_init=1,
        seed=1,
        num_workers=0,
    )
    db.add(row)
    db.commit()
    return row


def _inference(db, *, filename="slide-001.svs") -> Inference:
    row = Inference(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        model_id=str(uuid.uuid4()),
        wsi_path=f"/wsi/{filename}",
        wsi_filename=filename,
        wsi_mtime=0.0,
        wsi_size=1,
        wsi_hash="h",
        output_dir="/out",
        status="queued",
    )
    db.add(row)
    db.commit()
    return row


# --- GET /api/queue: bucketing --------------------------------------------


def test_empty_queue_has_no_running_and_empty_lists(client, db):
    body = client.get("/api/queue").json()
    assert body == {"running": None, "waiting": [], "recent": []}


def test_running_job_lands_in_the_running_slot(client, db):
    job = _job(db, status="running", started_offset=0)
    body = client.get("/api/queue").json()
    assert body["running"]["id"] == job.id
    assert body["waiting"] == []


def test_waiting_jobs_are_ordered_by_queue_position(client, db):
    third = _job(db, position=3)
    first = _job(db, position=1)
    second = _job(db, position=2)
    ids = [j["id"] for j in client.get("/api/queue").json()["waiting"]]
    assert ids == [first.id, second.id, third.id]


def test_recent_holds_terminal_jobs_newest_finished_first(client, db):
    older = _job(db, status="succeeded", finished_offset=-60)
    newer = _job(db, status="failed", finished_offset=0)
    ids = [j["id"] for j in client.get("/api/queue").json()["recent"]]
    assert ids == [newer.id, older.id]


def test_recent_includes_canceled_jobs(client, db):
    job = _job(db, status="canceled", finished_offset=0)
    assert [j["id"] for j in client.get("/api/queue").json()["recent"]] == [job.id]


def test_recent_is_capped(client, db):
    for i in range(RECENT_LIMIT + 5):
        _job(db, status="succeeded", finished_offset=i)
    assert len(client.get("/api/queue").json()["recent"]) == RECENT_LIMIT


def test_earliest_started_job_wins_the_running_slot(client, db):
    first = _job(db, status="running", started_offset=-30)
    _job(db, status="running", started_offset=0)
    assert client.get("/api/queue").json()["running"]["id"] == first.id


# --- GET /api/queue: human-readable labels --------------------------------


def test_panther_train_job_is_labeled_from_its_group(client, db):
    group = _group(db, display_name="TCGA sweep", k=5, dataset_name="tcga")
    _job(db, job_type="panther_train", ref_table="model_groups", ref_id=group.id, position=1)
    view = client.get("/api/queue").json()["waiting"][0]
    assert view["title"] == "PANTHER training — TCGA sweep"
    assert view["subtitle"] == "5 folds · tcga"


def test_post_train_viz_job_is_labeled_from_its_model(client, db):
    model = _model(db, display_name="Fold 2", fold_index=1, fold_k=5)
    _job(db, job_type="post_train_viz", ref_table="models", ref_id=model.id, position=1)
    view = client.get("/api/queue").json()["waiting"][0]
    assert view["title"] == "Visualization — Fold 2"
    assert view["subtitle"] == "fold 2 of 5"


def test_inference_job_is_labeled_with_the_slide_filename(client, db):
    inf = _inference(db, filename="patient-7.svs")
    _job(db, job_type="inference", ref_table="inferences", ref_id=inf.id, position=1)
    view = client.get("/api/queue").json()["waiting"][0]
    assert view["title"] == "Inference — patient-7.svs"


def test_render_slide_job_shows_the_model_and_slide(client, db):
    model = _model(db, display_name="Fold 1")
    _job(
        db,
        job_type="render_slide",
        ref_table="models",
        ref_id=model.id,
        position=1,
        params={"slide_id": "S42"},
    )
    view = client.get("/api/queue").json()["waiting"][0]
    assert view["title"] == "Render slide viz"
    assert view["subtitle"] == "Fold 1 · S42"


def test_labels_degrade_gracefully_when_the_referenced_row_is_gone(client, db):
    _job(db, job_type="panther_train", ref_id="deleted-group", position=1)
    view = client.get("/api/queue").json()["waiting"][0]
    assert view["title"] == "PANTHER training"
    assert view["subtitle"] is None


def test_render_slide_label_survives_malformed_params(client, db):
    job = _job(db, job_type="render_slide", ref_table="models", ref_id="gone", position=1)
    job.params = "{not json"
    db.add(job)
    db.commit()
    view = client.get("/api/queue").json()["waiting"][0]
    assert view["title"] == "Render slide viz"
    assert view["subtitle"] is None


def test_unknown_job_type_falls_back_to_the_type_name(client, db):
    _job(db, job_type="some_future_type", position=1)
    view = client.get("/api/queue").json()["waiting"][0]
    assert view["title"] == "some_future_type"
    assert view["subtitle"] is None


# --- POST /api/queue/reorder ----------------------------------------------


def test_reorder_rewrites_positions_from_the_requested_order(client, db):
    a = _job(db, position=1)
    b = _job(db, position=2)
    c = _job(db, position=3)
    body = client.post(
        "/api/queue/reorder", json={"ordered_job_ids": [c.id, a.id, b.id]}
    ).json()
    assert [j["id"] for j in body["waiting"]] == [c.id, a.id, b.id]
    assert [j["queue_position"] for j in body["waiting"]] == [1, 2, 3]


def test_reorder_appends_unmentioned_jobs_after_the_listed_ones(client, db):
    a = _job(db, position=1)
    b = _job(db, position=2)
    c = _job(db, position=3)
    body = client.post("/api/queue/reorder", json={"ordered_job_ids": [c.id]}).json()
    assert [j["id"] for j in body["waiting"]] == [c.id, a.id, b.id]


def test_reorder_ignores_ids_that_are_no_longer_queued(client, db):
    running = _job(db, status="running", started_offset=0)
    queued = _job(db, position=1)
    body = client.post(
        "/api/queue/reorder", json={"ordered_job_ids": [running.id, queued.id]}
    ).json()
    assert [j["id"] for j in body["waiting"]] == [queued.id]
    assert body["running"]["id"] == running.id


def test_reorder_ignores_unknown_ids(client, db):
    queued = _job(db, position=1)
    body = client.post(
        "/api/queue/reorder", json={"ordered_job_ids": ["ghost", queued.id]}
    ).json()
    assert [j["queue_position"] for j in body["waiting"]] == [1]
    assert body["waiting"][0]["id"] == queued.id


def test_reorder_deduplicates_repeated_ids(client, db):
    a = _job(db, position=1)
    b = _job(db, position=2)
    body = client.post(
        "/api/queue/reorder", json={"ordered_job_ids": [a.id, a.id, b.id]}
    ).json()
    assert [j["id"] for j in body["waiting"]] == [a.id, b.id]
    assert [j["queue_position"] for j in body["waiting"]] == [1, 2]


def test_reorder_produces_contiguous_positions_from_one(client, db):
    jobs = [_job(db, position=p) for p in (10, 20, 30)]
    body = client.post(
        "/api/queue/reorder", json={"ordered_job_ids": [j.id for j in reversed(jobs)]}
    ).json()
    assert [j["queue_position"] for j in body["waiting"]] == [1, 2, 3]


def test_reorder_with_an_empty_list_is_a_no_op_apart_from_renumbering(client, db):
    a = _job(db, position=5)
    b = _job(db, position=9)
    body = client.post("/api/queue/reorder", json={"ordered_job_ids": []}).json()
    assert [j["id"] for j in body["waiting"]] == [a.id, b.id]
    assert [j["queue_position"] for j in body["waiting"]] == [1, 2]

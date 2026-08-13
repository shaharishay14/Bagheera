"""The /api/inferences surface: dispatch, cache short-circuit, rerun, notes.

Every request stops at the point where a job row is written — the `inference`
handler itself never runs, so no TRIDENT subprocess is spawned.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.db.models import Inference, InferenceBatch, InferenceNote, Job, Model, PrototypeLabel
from app.services.inference import compute_wsi_hash


@pytest.fixture()
def env(tmp_path, override_settings):
    """Allowed WSI root + temp inference/viz roots."""
    wsi_root = tmp_path / "wsi"
    wsi_root.mkdir()
    inf_root = tmp_path / "inference_outputs"
    inf_root.mkdir()
    viz_root = tmp_path / "viz_cache"
    (viz_root / "job_logs").mkdir(parents=True)
    override_settings(
        allowed_roots=[wsi_root.resolve()],
        inference_root=inf_root.resolve(),
        viz_cache_root=viz_root.resolve(),
    )
    return wsi_root


@pytest.fixture()
def slide(env):
    p = env / "slide-001.svs"
    p.write_bytes(b"wsi-bytes")
    return p


@pytest.fixture()
def make_slide(env):
    """Distinct WSI files — distinct content, so distinct hashes."""

    def _make(name: str):
        p = env / name
        p.write_bytes(f"content-of-{name}".encode())
        return p

    return _make


@pytest.fixture()
def model(db) -> Model:
    mid = str(uuid.uuid4())
    row = Model(
        id=mid,
        created_at=datetime.utcnow(),
        base_name="m",
        model_name=f"m_{mid[:8]}",
        display_name="Fold 1",
        group_id=str(uuid.uuid4()),
        fold_index=0,
        fold_k=1,
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
        status="ready",
    )
    db.add(row)
    db.commit()
    return row


def _inference(db, model_id, wsi, *, status="succeeded", hashed=True, offset=0) -> Inference:
    stat = wsi.stat()
    row = Inference(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow() + timedelta(seconds=offset),
        model_id=model_id,
        wsi_path=str(wsi),
        wsi_filename=wsi.name,
        wsi_mtime=stat.st_mtime,
        wsi_size=stat.st_size,
        wsi_hash=compute_wsi_hash(wsi) if hashed else "stale",
        output_dir="/out",
        status=status,
    )
    db.add(row)
    db.commit()
    return row


# --- POST /api/inferences -------------------------------------------------


def test_single_path_creates_a_row_and_queues_a_job(client, db, model, slide):
    resp = client.post(
        "/api/inferences", json={"model_id": model.id, "wsi_paths": [str(slide)]}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["batch_id"] is None
    assert len(body["inferences"]) == 1

    entry = body["inferences"][0]
    assert entry["status"] == "queued"
    assert entry["cached"] is False

    job = db.query(Job).one()
    assert job.job_type == "inference"
    assert job.ref_id == entry["id"]


def test_a_single_valid_path_does_not_create_a_batch(client, db, model, slide):
    body = client.post(
        "/api/inferences", json={"model_id": model.id, "wsi_paths": [str(slide)]}
    ).json()
    assert body["batch_id"] is None
    assert db.query(InferenceBatch).count() == 0


def test_a_cached_slide_short_circuits_without_a_new_job(client, db, model, slide):
    existing = _inference(db, model.id, slide)
    body = client.post(
        "/api/inferences", json={"model_id": model.id, "wsi_paths": [str(slide)]}
    ).json()

    entry = body["inferences"][0]
    assert entry["cached"] is True
    assert entry["id"] == existing.id
    assert entry["message"] == "cache hit"
    assert db.query(Job).count() == 0


def test_rerun_flag_bypasses_the_cache(client, db, model, slide):
    _inference(db, model.id, slide)
    body = client.post(
        "/api/inferences",
        json={"model_id": model.id, "wsi_paths": [str(slide)], "rerun": True},
    ).json()
    assert body["inferences"][0]["cached"] is False
    assert db.query(Job).count() == 1


def test_a_stale_hash_is_treated_as_a_miss(client, db, model, slide):
    _inference(db, model.id, slide, hashed=False)
    body = client.post(
        "/api/inferences", json={"model_id": model.id, "wsi_paths": [str(slide)]}
    ).json()
    assert body["inferences"][0]["cached"] is False


def test_mixed_valid_and_invalid_paths_return_207(client, db, model, slide, tmp_path):
    resp = client.post(
        "/api/inferences",
        json={
            "model_id": model.id,
            "wsi_paths": [str(slide), str(tmp_path / "outside.svs")],
        },
    )
    assert resp.status_code == 207
    statuses = {e["status"] for e in resp.json()["inferences"]}
    assert statuses == {"queued", "rejected"}


def test_rejected_entries_carry_the_reason(client, db, model, slide, env):
    missing = env / "not-there.svs"
    body = client.post(
        "/api/inferences",
        json={"model_id": model.id, "wsi_paths": [str(slide), str(missing)]},
    ).json()
    rejected = [e for e in body["inferences"] if e["status"] == "rejected"][0]
    assert "does not exist" in rejected["message"]


def test_all_paths_invalid_is_a_400(client, db, model, tmp_path):
    resp = client.post(
        "/api/inferences",
        json={"model_id": model.id, "wsi_paths": [str(tmp_path / "a.svs")]},
    )
    assert resp.status_code == 400
    assert "All wsi_paths failed validation" in resp.json()["detail"]


def test_a_path_outside_the_roots_is_rejected_not_served(client, db, model, tmp_path):
    outside = tmp_path / "outside.svs"
    outside.write_bytes(b"x")
    resp = client.post(
        "/api/inferences", json={"model_id": model.id, "wsi_paths": [str(outside)]}
    )
    assert resp.status_code == 400


def test_dispatch_404_for_an_unknown_model(client, db, slide):
    resp = client.post("/api/inferences", json={"model_id": "ghost", "wsi_paths": [str(slide)]})
    assert resp.status_code == 404


def test_the_created_row_records_the_wsi_stat_and_output_dir(client, db, model, slide, env):
    body = client.post(
        "/api/inferences", json={"model_id": model.id, "wsi_paths": [str(slide)]}
    ).json()
    row = db.get(Inference, body["inferences"][0]["id"])
    assert row.wsi_filename == "slide-001.svs"
    assert row.wsi_size == slide.stat().st_size
    assert row.status == "queued"
    assert row.output_dir.endswith(f"{model.id}/{row.id}")


# --- GET /api/inferences/lookup -------------------------------------------


def test_lookup_returns_a_cached_row(client, db, model, slide):
    existing = _inference(db, model.id, slide)
    body = client.get(
        "/api/inferences/lookup", params={"model_id": model.id, "wsi_path": str(slide)}
    ).json()
    assert body["id"] == existing.id


def test_lookup_404_on_a_cache_miss(client, db, model, slide):
    resp = client.get(
        "/api/inferences/lookup", params={"model_id": model.id, "wsi_path": str(slide)}
    )
    assert resp.status_code == 404


def test_lookup_400_for_an_invalid_path(client, db, model, tmp_path):
    resp = client.get(
        "/api/inferences/lookup",
        params={"model_id": model.id, "wsi_path": str(tmp_path / "outside.svs")},
    )
    assert resp.status_code == 400


# --- GET /api/inferences --------------------------------------------------


def test_list_is_newest_first(client, db, model, make_slide):
    older = _inference(db, model.id, make_slide("a.svs"), offset=-60)
    newer = _inference(db, model.id, make_slide("b.svs"), offset=0)
    assert [r["id"] for r in client.get("/api/inferences").json()] == [newer.id, older.id]


def test_list_filters_by_model(client, db, model, slide):
    mine = _inference(db, model.id, slide)
    _inference(db, "another-model", slide)
    body = client.get("/api/inferences", params={"model_id": model.id}).json()
    assert [r["id"] for r in body] == [mine.id]


def test_list_filters_by_status(client, db, model, make_slide):
    failed = _inference(db, model.id, make_slide("a.svs"), status="failed")
    _inference(db, model.id, make_slide("b.svs"), status="succeeded")
    body = client.get("/api/inferences", params={"status": "failed"}).json()
    assert [r["id"] for r in body] == [failed.id]


def test_list_honors_the_limit(client, db, model, make_slide):
    for i in range(4):
        _inference(db, model.id, make_slide(f"s{i}.svs"), offset=i)
    assert len(client.get("/api/inferences", params={"limit": 2}).json()) == 2


# --- GET /api/inferences/{id} ---------------------------------------------


def test_detail_returns_the_row(client, db, model, slide):
    row = _inference(db, model.id, slide)
    assert client.get(f"/api/inferences/{row.id}").json()["id"] == row.id


def test_detail_404_for_an_unknown_id(client, db):
    assert client.get("/api/inferences/ghost").status_code == 404


# --- GET /api/inferences/{id}/example-patches -----------------------------


def test_example_patches_groups_files_per_prototype(client, db, model, slide, tmp_path):
    patches = tmp_path / "patches"
    for proto in (0, 1):
        d = patches / f"prototype_{proto:02d}"
        d.mkdir(parents=True)
        for k in range(2):
            (d / f"patch_{k:02d}.png").write_bytes(b"")

    row = _inference(db, model.id, slide)
    row.example_patches_dir = str(patches)
    db.add(row)
    db.commit()

    body = client.get(f"/api/inferences/{row.id}/example-patches").json()
    assert [g["prototype_index"] for g in body["groups"]] == [0, 1]
    assert all(len(g["urls"]) == 2 for g in body["groups"])
    assert body["groups"][0]["urls"][0].startswith("/api/viz/")


def test_example_patches_attaches_prototype_labels(client, db, model, slide, tmp_path):
    patches = tmp_path / "patches"
    d = patches / "prototype_00"
    d.mkdir(parents=True)
    (d / "patch_00.png").write_bytes(b"")

    row = _inference(db, model.id, slide)
    row.example_patches_dir = str(patches)
    db.add(row)
    db.add(
        PrototypeLabel(
            id=str(uuid.uuid4()),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            model_id=model.id,
            prototype_index=0,
            label="stroma",
        )
    )
    db.commit()

    body = client.get(f"/api/inferences/{row.id}/example-patches").json()
    assert body["groups"][0]["label"] == "stroma"


def test_example_patches_ignores_non_image_and_stray_directories(
    client, db, model, slide, tmp_path
):
    patches = tmp_path / "patches"
    (patches / "prototype_00").mkdir(parents=True)
    (patches / "prototype_00" / "patch_00.png").write_bytes(b"")
    (patches / "prototype_00" / "notes.txt").write_text("x")
    (patches / "scratch").mkdir()
    (patches / "prototype_empty").mkdir()

    row = _inference(db, model.id, slide)
    row.example_patches_dir = str(patches)
    db.add(row)
    db.commit()

    body = client.get(f"/api/inferences/{row.id}/example-patches").json()
    assert len(body["groups"]) == 1
    assert len(body["groups"][0]["urls"]) == 1


def test_example_patches_empty_when_no_directory_is_recorded(client, db, model, slide):
    row = _inference(db, model.id, slide)
    body = client.get(f"/api/inferences/{row.id}/example-patches").json()
    assert body["groups"] == []
    assert body["base_dir"] == ""


def test_example_patches_empty_when_the_directory_is_gone(client, db, model, slide, tmp_path):
    row = _inference(db, model.id, slide)
    row.example_patches_dir = str(tmp_path / "vanished")
    db.add(row)
    db.commit()
    body = client.get(f"/api/inferences/{row.id}/example-patches").json()
    assert body["groups"] == []


def test_example_patches_404_for_an_unknown_inference(client, db):
    assert client.get("/api/inferences/ghost/example-patches").status_code == 404


# --- POST /api/inferences/{id}/rerun --------------------------------------


def test_rerun_replaces_the_row_and_queues_a_job(client, db, model, slide):
    old = _inference(db, model.id, slide)
    old_id = old.id

    body = client.post(f"/api/inferences/{old_id}/rerun").json()
    assert body["new_inference_id"] != old_id
    db.expunge_all()
    assert db.get(Inference, old_id) is None
    assert db.get(Inference, body["new_inference_id"]).status == "queued"
    assert db.get(Job, body["job_id"]).job_type == "inference"


def test_rerun_drops_the_old_rows_notes(client, db, model, slide):
    old = _inference(db, model.id, slide)
    db.add(
        InferenceNote(
            id=str(uuid.uuid4()),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            inference_id=old.id,
            body="stale note",
        )
    )
    db.commit()

    client.post(f"/api/inferences/{old.id}/rerun")
    assert db.query(InferenceNote).count() == 0


def test_rerun_404_for_an_unknown_inference(client, db):
    assert client.post("/api/inferences/ghost/rerun").status_code == 404


def test_rerun_400_when_the_wsi_is_gone(client, db, model, slide):
    row = _inference(db, model.id, slide)
    slide.unlink()
    resp = client.post(f"/api/inferences/{row.id}/rerun")
    assert resp.status_code == 400
    assert "no longer exists" in resp.json()["detail"]


def test_rerun_500_when_the_model_was_deleted(client, db, model, slide):
    row = _inference(db, model.id, slide)
    db.query(Model).filter(Model.id == model.id).delete()
    db.commit()
    assert client.post(f"/api/inferences/{row.id}/rerun").status_code == 500


# --- GET /api/inference-batches/{id} --------------------------------------


def test_batch_detail_404_for_an_unknown_id(client, db):
    assert client.get("/api/inference-batches/ghost").status_code == 404


# --- /api/inference-notes -------------------------------------------------


def test_creating_an_inference_note_returns_it(client, db, model, slide):
    row = _inference(db, model.id, slide)
    resp = client.post("/api/inference-notes", json={"inference_id": row.id, "body": "hi"})
    assert resp.status_code == 200
    assert resp.json()["body"] == "hi"


def test_inference_note_404_for_an_unknown_inference(client, db):
    assert client.post(
        "/api/inference-notes", json={"inference_id": "ghost", "body": "x"}
    ).status_code == 404


def test_inference_notes_are_scoped_and_listed_newest_first(client, db, model, slide):
    row = _inference(db, model.id, slide)
    older = client.post("/api/inference-notes", json={"inference_id": row.id, "body": "a"}).json()
    newer = client.post("/api/inference-notes", json={"inference_id": row.id, "body": "b"}).json()
    stale = db.get(InferenceNote, older["id"])
    stale.created_at = datetime.utcnow() - timedelta(hours=1)
    db.add(stale)
    db.commit()

    body = client.get("/api/inference-notes", params={"inference_id": row.id}).json()
    assert [n["id"] for n in body] == [newer["id"], older["id"]]
    assert client.get("/api/inference-notes", params={"inference_id": "other"}).json() == []


def test_patching_an_inference_note_replaces_the_body(client, db, model, slide):
    row = _inference(db, model.id, slide)
    note = client.post("/api/inference-notes", json={"inference_id": row.id, "body": "a"}).json()
    assert client.patch(f"/api/inference-notes/{note['id']}", json={"body": "b"}).json()["body"] == "b"


def test_patching_an_unknown_inference_note_404s(client, db):
    assert client.patch("/api/inference-notes/ghost", json={"body": "x"}).status_code == 404


def test_deleting_an_inference_note_returns_204(client, db, model, slide):
    row = _inference(db, model.id, slide)
    note = client.post("/api/inference-notes", json={"inference_id": row.id, "body": "a"}).json()
    assert client.delete(f"/api/inference-notes/{note['id']}").status_code == 204
    assert db.query(InferenceNote).count() == 0


def test_deleting_an_unknown_inference_note_404s(client, db):
    assert client.delete("/api/inference-notes/ghost").status_code == 404

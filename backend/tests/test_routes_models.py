"""Model + ModelGroup CRUD behind the Models browser and Group detail pages."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import pytest

from app.db.models import Job, Model, ModelGroup, Split, TridentRun


def _split(db, *, dataset="ds", k=3) -> Split:
    row = Split(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        dataset_name=dataset,
        split_name=f"kfold_k_{k}_{uuid.uuid4().hex[:6]}",
        abs_path="/splits/x",
        source_csv="/data/cohort.csv",
        k=k,
        seed=1,
        total_rows=30,
        per_fold_counts=json.dumps([{"train": 10, "val": 10, "test": 10}] * k),
    )
    db.add(row)
    db.commit()
    return row


def _group(db, split, *, display_name="Run A", dataset="ds", k=3, offset=0) -> ModelGroup:
    row = ModelGroup(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow() + timedelta(seconds=offset),
        display_name=display_name,
        dataset_name=dataset,
        k=k,
        split_id=split.id,
    )
    db.add(row)
    db.commit()
    return row


def _model(
    db,
    group,
    *,
    fold_index=0,
    status="ready",
    is_favorite=False,
    display_name=None,
    split_dir_abs="",
    trident_run_id=None,
    n_proto=8,
) -> Model:
    mid = str(uuid.uuid4())
    row = Model(
        id=mid,
        created_at=datetime.utcnow(),
        base_name="m",
        model_name=f"m_{mid[:8]}",
        display_name=display_name if display_name is not None else group.display_name,
        group_id=group.id,
        fold_index=fold_index,
        fold_k=group.k,
        dataset_name=group.dataset_name,
        features_dir="/feats",
        trident_run_id=trident_run_id,
        split_id=group.split_id,
        split_name="sp",
        split_dir_abs=split_dir_abs,
        mode="faiss",
        in_dim=1024,
        n_proto_patches=1000,
        n_proto=n_proto,
        n_init=1,
        seed=1,
        num_workers=0,
        status=status,
        is_favorite=is_favorite,
    )
    db.add(row)
    db.commit()
    return row


# --- GET /api/model-groups ------------------------------------------------


def test_list_returns_a_group_with_its_fold_summary(client, db):
    split = _split(db)
    group = _group(db, split)
    _model(db, group, fold_index=0, status="ready")
    _model(db, group, fold_index=1, status="failed")
    _model(db, group, fold_index=2, status="running", is_favorite=True)

    body = client.get("/api/model-groups").json()
    assert len(body) == 1
    summary = body[0]["summary"]
    assert summary == {"total": 3, "ready": 1, "failed": 1, "running": 1, "favorited": 1}


def test_list_reports_the_split_name_and_representative_params(client, db):
    split = _split(db)
    group = _group(db, split)
    _model(db, group, n_proto=16)
    item = client.get("/api/model-groups").json()[0]
    assert item["split_name"] == split.split_name
    assert item["n_proto"] == 16
    assert item["mode"] == "faiss"


def test_list_is_empty_on_a_fresh_database(client, db):
    assert client.get("/api/model-groups").json() == []


def test_list_filters_by_dataset(client, db):
    a = _group(db, _split(db, dataset="alpha"), dataset="alpha")
    _group(db, _split(db, dataset="beta"), dataset="beta")
    body = client.get("/api/model-groups", params={"dataset_name": "alpha"}).json()
    assert [g["id"] for g in body] == [a.id]


def test_list_search_matches_the_display_name_case_insensitively(client, db):
    target = _group(db, _split(db), display_name="Breast cohort")
    _group(db, _split(db), display_name="Lung cohort")
    body = client.get("/api/model-groups", params={"q": "breast"}).json()
    assert [g["id"] for g in body] == [target.id]


def test_list_favorite_only_hides_groups_without_a_favorited_fold(client, db):
    plain = _group(db, _split(db), display_name="Plain")
    _model(db, plain, is_favorite=False)
    starred = _group(db, _split(db), display_name="Starred")
    _model(db, starred, is_favorite=True)

    body = client.get("/api/model-groups", params={"favorite_only": True}).json()
    assert [g["id"] for g in body] == [starred.id]


def test_list_sorts_newest_first_by_default(client, db):
    older = _group(db, _split(db), offset=-60)
    newer = _group(db, _split(db), offset=0)
    assert [g["id"] for g in client.get("/api/model-groups").json()] == [newer.id, older.id]


def test_list_sort_created_asc_reverses_the_order(client, db):
    older = _group(db, _split(db), offset=-60)
    newer = _group(db, _split(db), offset=0)
    body = client.get("/api/model-groups", params={"sort": "created_asc"}).json()
    assert [g["id"] for g in body] == [older.id, newer.id]


def test_list_sort_by_name_is_alphabetical(client, db):
    z = _group(db, _split(db), display_name="Zebra")
    a = _group(db, _split(db), display_name="Alpha")
    body = client.get("/api/model-groups", params={"sort": "name"}).json()
    assert [g["id"] for g in body] == [a.id, z.id]


def test_list_rejects_an_unknown_sort_key(client, db):
    assert client.get("/api/model-groups", params={"sort": "random"}).status_code == 422


def test_list_skips_a_group_whose_split_row_is_gone(client, db):
    split = _split(db)
    group = _group(db, split)
    _model(db, group)
    db.delete(split)
    db.commit()
    assert client.get("/api/model-groups").json() == []


# --- GET /api/model-groups/{id} -------------------------------------------


def test_detail_returns_the_group_models_and_split(client, db):
    split = _split(db)
    group = _group(db, split)
    _model(db, group, fold_index=0)
    _model(db, group, fold_index=1)

    body = client.get(f"/api/model-groups/{group.id}").json()
    assert body["group"]["id"] == group.id
    assert len(body["models"]) == 2
    assert body["split"]["id"] == split.id
    assert len(body["split"]["per_fold_counts"]) == 3


def test_detail_sorts_favorites_first_then_by_fold(client, db):
    group = _group(db, _split(db))
    _model(db, group, fold_index=0)
    _model(db, group, fold_index=1)
    starred = _model(db, group, fold_index=2, is_favorite=True)

    body = client.get(f"/api/model-groups/{group.id}").json()
    assert body["models"][0]["id"] == starred.id
    assert [m["fold_index"] for m in body["models"]] == [2, 0, 1]


def test_detail_404_for_an_unknown_group(client, db):
    assert client.get("/api/model-groups/ghost").status_code == 404


def test_detail_500_when_the_group_references_a_missing_split(client, db):
    group = _group(db, _split(db))
    db.query(Split).filter(Split.id == group.split_id).delete()
    db.commit()
    assert client.get(f"/api/model-groups/{group.id}").status_code == 500


# --- PATCH /api/model-groups/{id} -----------------------------------------


def test_renaming_a_group_cascades_to_its_fold_models(client, db):
    group = _group(db, _split(db), display_name="Old name")
    a = _model(db, group, fold_index=0)
    b = _model(db, group, fold_index=1)

    body = client.patch(
        f"/api/model-groups/{group.id}", json={"display_name": "New name"}
    ).json()
    assert body["display_name"] == "New name"
    db.expire_all()
    assert db.get(Model, a.id).display_name == "New name"
    assert db.get(Model, b.id).display_name == "New name"


def test_patching_with_no_fields_leaves_the_group_untouched(client, db):
    group = _group(db, _split(db), display_name="Keep me")
    assert client.patch(f"/api/model-groups/{group.id}", json={}).json()["display_name"] == "Keep me"


def test_patch_404_for_an_unknown_group(client, db):
    assert client.patch("/api/model-groups/ghost", json={"display_name": "x"}).status_code == 404


# --- GET / PATCH /api/models/{id} -----------------------------------------


def test_get_model_returns_it(client, db):
    model = _model(db, _group(db, _split(db)))
    assert client.get(f"/api/models/{model.id}").json()["id"] == model.id


def test_get_model_404_for_an_unknown_id(client, db):
    assert client.get("/api/models/ghost").status_code == 404


def test_patch_model_toggles_the_favorite_flag(client, db):
    model = _model(db, _group(db, _split(db)), is_favorite=False)
    assert client.patch(f"/api/models/{model.id}", json={"is_favorite": True}).json()["is_favorite"] is True
    assert client.patch(f"/api/models/{model.id}", json={"is_favorite": False}).json()["is_favorite"] is False


def test_patch_model_renames_only_that_fold(client, db):
    group = _group(db, _split(db))
    a = _model(db, group, fold_index=0)
    b = _model(db, group, fold_index=1)
    client.patch(f"/api/models/{a.id}", json={"display_name": "Just this one"})
    db.expire_all()
    assert db.get(Model, a.id).display_name == "Just this one"
    assert db.get(Model, b.id).display_name == group.display_name


def test_patch_model_404_for_an_unknown_id(client, db):
    assert client.patch("/api/models/ghost", json={"is_favorite": True}).status_code == 404


# --- POST /api/models/{id}/shuffle-preview --------------------------------


@pytest.fixture()
def logs_root(tmp_path, override_settings):
    root = tmp_path / "viz_cache"
    (root / "job_logs").mkdir(parents=True)
    override_settings(viz_cache_root=root)
    return root


def test_shuffle_picks_slides_and_enqueues_a_viz_job(client, db, tmp_path, logs_root):
    split_dir = tmp_path / "fold"
    split_dir.mkdir()
    (split_dir / "train.csv").write_text(
        "slide_id\n" + "\n".join(f"S{i}" for i in range(10)) + "\n"
    )
    model = _model(db, _group(db, _split(db)), split_dir_abs=str(split_dir))

    body = client.post(f"/api/models/{model.id}/shuffle-preview").json()
    assert len(body["preview_slide_ids"]) == 3
    assert body["job_id"] is not None

    job = db.get(Job, body["job_id"])
    assert job.job_type == "post_train_viz"
    assert job.ref_id == model.id
    db.expire_all()
    assert db.get(Model, model.id).viz_status == "pending"


def test_shuffle_persists_the_picked_ids_on_the_model(client, db, tmp_path, logs_root):
    split_dir = tmp_path / "fold"
    split_dir.mkdir()
    (split_dir / "train.csv").write_text("slide_id\nS1\nS2\nS3\nS4\n")
    model = _model(db, _group(db, _split(db)), split_dir_abs=str(split_dir))

    body = client.post(f"/api/models/{model.id}/shuffle-preview").json()
    db.expire_all()
    assert json.loads(db.get(Model, model.id).preview_slide_ids) == body["preview_slide_ids"]


def test_shuffle_enqueues_nothing_when_no_slides_can_be_picked(client, db, tmp_path, logs_root):
    model = _model(db, _group(db, _split(db)), split_dir_abs=str(tmp_path / "nonexistent"))
    body = client.post(f"/api/models/{model.id}/shuffle-preview").json()
    assert body["preview_slide_ids"] == []
    assert body["job_id"] is None
    assert db.query(Job).count() == 0


def test_shuffle_404_for_an_unknown_model(client, db):
    assert client.post("/api/models/ghost/shuffle-preview").status_code == 404


# --- GET /api/models/{id}/trident-params ----------------------------------


def test_trident_params_are_inherited_from_the_linked_run(client, db):
    run = TridentRun(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        dataset_name="ds",
        wsi_dir="/wsi",
        patch_encoder="phikon",
        mag=20,
        patch_size=224,
        command="x",
        status="succeeded",
        output_dir="/feats",
    )
    db.add(run)
    db.commit()
    model = _model(db, _group(db, _split(db)), trident_run_id=run.id)

    body = client.get(f"/api/models/{model.id}/trident-params").json()
    assert body["patch_encoder"] == "phikon"
    assert body["mag"] == 20
    assert body["patch_size"] == 224


def test_trident_params_are_null_when_the_model_has_no_run(client, db):
    model = _model(db, _group(db, _split(db)), trident_run_id=None)
    body = client.get(f"/api/models/{model.id}/trident-params").json()
    assert body["patch_encoder"] is None
    assert body["mag"] is None


def test_trident_params_404_for_an_unknown_model(client, db):
    assert client.get("/api/models/ghost/trident-params").status_code == 404

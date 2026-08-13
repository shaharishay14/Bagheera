"""Group deletion: manual FK-safe cascade, in-flight guards, disk cleanup.

There are no `ON DELETE CASCADE` constraints, so every dependent table is
deleted by hand — if a new table starts referencing models, these counts are
what catches the omission.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest

from app.db.models import (
    Inference,
    InferenceBatch,
    InferenceNote,
    Job,
    Model,
    ModelGroup,
    ModelNote,
    PantherRun,
    PrototypeLabel,
    Split,
    TridentRun,
)


@pytest.fixture()
def roots(tmp_path, override_settings):
    viz = tmp_path / "viz_cache"
    inf = tmp_path / "inference_outputs"
    protos = tmp_path / "panther"
    for d in (viz, inf, protos):
        d.mkdir()
    override_settings(
        viz_cache_root=viz.resolve(),
        inference_root=inf.resolve(),
        allowed_roots=[protos.resolve()],
    )
    return viz, inf, protos


@pytest.fixture()
def populated(db, roots):
    """A group with one fold model and one row in every dependent table."""
    viz, inf, protos = roots

    split = Split(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        dataset_name="ds",
        split_name="sp",
        abs_path="/splits/sp",
        source_csv="/data/c.csv",
        k=1,
        seed=1,
        total_rows=10,
        per_fold_counts=json.dumps([{"train": 10, "val": 0, "test": 0}]),
    )
    run = TridentRun(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        dataset_name="ds",
        wsi_dir="/wsi",
        patch_encoder="uni_v1",
        mag=20,
        patch_size=256,
        command="x",
        status="succeeded",
        output_dir="/feats",
    )
    group = ModelGroup(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        display_name="Run A",
        dataset_name="ds",
        trident_run_id=run.id,
        k=1,
        split_id=split.id,
    )
    db.add_all([split, run, group])
    db.commit()

    proto_dir = protos / "prototypes"
    proto_dir.mkdir()
    (proto_dir / "proto.pkl").write_bytes(b"")

    model = Model(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        base_name="m",
        model_name="m_1",
        display_name="Run A",
        group_id=group.id,
        fold_index=0,
        fold_k=1,
        dataset_name="ds",
        features_dir="/feats",
        trident_run_id=run.id,
        split_id=split.id,
        split_name="sp",
        mode="faiss",
        in_dim=1024,
        n_proto_patches=1000,
        n_proto=8,
        n_init=1,
        seed=1,
        num_workers=0,
        status="ready",
        prototypes_dir=str(proto_dir),
    )
    db.add(model)
    db.commit()

    batch = InferenceBatch(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        model_id=model.id,
        total_count=1,
    )
    db.add(batch)
    db.commit()

    inference = Inference(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        model_id=model.id,
        batch_id=batch.id,
        wsi_path="/wsi/s.svs",
        wsi_filename="s.svs",
        wsi_mtime=0.0,
        wsi_size=1,
        wsi_hash="h",
        output_dir="/out",
        status="succeeded",
    )
    db.add(inference)
    db.commit()

    db.add_all(
        [
            InferenceNote(
                id=str(uuid.uuid4()),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                inference_id=inference.id,
                body="note",
            ),
            PrototypeLabel(
                id=str(uuid.uuid4()),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                model_id=model.id,
                prototype_index=0,
                label="stroma",
            ),
            ModelNote(
                id=str(uuid.uuid4()),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                model_id=model.id,
                body="note",
            ),
            PantherRun(
                id=str(uuid.uuid4()),
                created_at=datetime.utcnow(),
                group_id=group.id,
                fold_index=0,
                model_id=model.id,
                dataset_name="ds",
                features_dir="/feats",
                split_name="sp",
                mode="faiss",
                in_dim=1024,
                n_proto_patches=1000,
                n_proto=8,
                n_init=1,
                seed=1,
                num_workers=0,
                command="x",
                status="succeeded",
            ),
        ]
    )
    db.commit()

    # On-disk artifacts the delete is expected to remove.
    (viz / model.id).mkdir()
    (viz / model.id / "umap.png").write_bytes(b"")
    (inf / model.id).mkdir()
    (inf / model.id / "heatmap.png").write_bytes(b"")

    return {
        "group": group,
        "model": model,
        "split": split,
        "run": run,
        "proto_dir": proto_dir,
    }


def _job(db, *, ref_table, ref_id, status) -> Job:
    row = Job(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        job_type="post_train_viz",
        ref_table=ref_table,
        ref_id=ref_id,
        status=status,
    )
    db.add(row)
    db.commit()
    return row


# --- happy path -----------------------------------------------------------


def test_delete_reports_what_it_removed(client, db, populated):
    body = client.delete(f"/api/model-groups/{populated['group'].id}").json()
    assert body["models_deleted"] == 1
    assert body["inferences_deleted"] == 1
    assert body["inference_notes_deleted"] == 1
    assert body["inference_batches_deleted"] == 1
    assert body["prototype_labels_deleted"] == 1
    assert body["model_notes_deleted"] == 1
    assert body["panther_runs_deleted"] == 1


def test_delete_leaves_no_orphan_rows_behind(client, db, populated):
    client.delete(f"/api/model-groups/{populated['group'].id}")
    for table in (
        ModelGroup,
        Model,
        Inference,
        InferenceNote,
        InferenceBatch,
        PrototypeLabel,
        ModelNote,
        PantherRun,
    ):
        assert db.query(table).count() == 0, table.__name__


def test_delete_keeps_the_shared_split_and_trident_run(client, db, populated):
    client.delete(f"/api/model-groups/{populated['group'].id}")
    assert db.get(Split, populated["split"].id) is not None
    assert db.get(TridentRun, populated["run"].id) is not None


def test_delete_removes_the_viz_inference_and_prototype_directories(client, db, populated, roots):
    viz, inf, _ = roots
    model_id = populated["model"].id
    body = client.delete(f"/api/model-groups/{populated['group'].id}").json()

    assert not (viz / model_id).exists()
    assert not (inf / model_id).exists()
    assert not populated["proto_dir"].exists()
    assert len(body["dirs_removed"]) == 3


def test_delete_tolerates_missing_artifact_directories(client, db, populated, roots):
    viz, inf, _ = roots
    import shutil

    shutil.rmtree(viz / populated["model"].id)
    resp = client.delete(f"/api/model-groups/{populated['group'].id}")
    assert resp.status_code == 200


def test_delete_skips_a_prototypes_dir_outside_the_allowed_roots(
    client, db, populated, roots, tmp_path
):
    outside = tmp_path / "outside_protos"
    outside.mkdir()
    (outside / "keep.txt").write_text("x")
    model = db.get(Model, populated["model"].id)
    model.prototypes_dir = str(outside)
    db.add(model)
    db.commit()

    client.delete(f"/api/model-groups/{populated['group'].id}")
    assert outside.exists()


def test_delete_handles_a_group_with_no_models(client, db, populated):
    group = ModelGroup(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        display_name="Empty",
        dataset_name="ds",
        k=1,
        split_id=populated["split"].id,
    )
    db.add(group)
    db.commit()
    group_id = group.id

    body = client.delete(f"/api/model-groups/{group_id}").json()
    assert body["models_deleted"] == 0
    db.expunge_all()  # the bulk DELETE bypasses the session's identity map
    assert db.get(ModelGroup, group_id) is None


def test_delete_only_touches_the_targeted_group(client, db, populated):
    other = ModelGroup(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        display_name="Other",
        dataset_name="ds",
        k=1,
        split_id=populated["split"].id,
    )
    db.add(other)
    db.commit()
    client.delete(f"/api/model-groups/{populated['group'].id}")
    assert db.get(ModelGroup, other.id) is not None


# --- guards ---------------------------------------------------------------


def test_delete_404_for_an_unknown_group(client, db):
    assert client.delete("/api/model-groups/ghost").status_code == 404


def test_delete_409_while_a_fold_model_is_running(client, db, populated):
    model = db.get(Model, populated["model"].id)
    model.status = "running"
    db.add(model)
    db.commit()

    resp = client.delete(f"/api/model-groups/{populated['group'].id}")
    assert resp.status_code == 409
    assert "still running" in resp.json()["detail"]
    assert db.get(ModelGroup, populated["group"].id) is not None


@pytest.mark.parametrize("active", ["queued", "running"])
def test_delete_409_while_a_job_references_the_group(client, db, populated, active):
    _job(db, ref_table="model_groups", ref_id=populated["group"].id, status=active)
    resp = client.delete(f"/api/model-groups/{populated['group'].id}")
    assert resp.status_code == 409
    assert "active" in resp.json()["detail"]


@pytest.mark.parametrize("active", ["queued", "running"])
def test_delete_409_while_a_job_references_a_fold_model(client, db, populated, active):
    _job(db, ref_table="models", ref_id=populated["model"].id, status=active)
    assert client.delete(f"/api/model-groups/{populated['group'].id}").status_code == 409


@pytest.mark.parametrize("terminal", ["succeeded", "failed", "canceled"])
def test_delete_proceeds_when_the_referencing_job_is_finished(client, db, populated, terminal):
    _job(db, ref_table="models", ref_id=populated["model"].id, status=terminal)
    assert client.delete(f"/api/model-groups/{populated['group'].id}").status_code == 200


def test_delete_ignores_active_jobs_for_unrelated_rows(client, db, populated):
    _job(db, ref_table="models", ref_id="some-other-model", status="running")
    assert client.delete(f"/api/model-groups/{populated['group'].id}").status_code == 200

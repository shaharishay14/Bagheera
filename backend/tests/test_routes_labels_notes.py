"""Prototype labels and model notes — the two annotation resources.

Labels are an upsert keyed on (model_id, prototype_index); notes are a plain
append-only thread. Both are FK-guarded against a missing model.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.db.models import Model, ModelNote, PrototypeLabel


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


# --- POST /api/prototype-labels -------------------------------------------


def test_creating_a_label_returns_it(client, db, model):
    resp = client.post(
        "/api/prototype-labels",
        json={"model_id": model.id, "prototype_index": 2, "label": "stroma"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prototype_index"] == 2
    assert body["label"] == "stroma"


def test_posting_the_same_prototype_twice_updates_in_place(client, db, model):
    first = client.post(
        "/api/prototype-labels",
        json={"model_id": model.id, "prototype_index": 0, "label": "stroma"},
    ).json()
    second = client.post(
        "/api/prototype-labels",
        json={"model_id": model.id, "prototype_index": 0, "label": "tumor"},
    ).json()
    assert second["id"] == first["id"]
    assert second["label"] == "tumor"
    assert db.query(PrototypeLabel).count() == 1


def test_upsert_bumps_updated_at(client, db, model):
    created = client.post(
        "/api/prototype-labels",
        json={"model_id": model.id, "prototype_index": 0, "label": "a"},
    ).json()
    row = db.get(PrototypeLabel, created["id"])
    row.updated_at = datetime.utcnow() - timedelta(hours=1)
    db.add(row)
    db.commit()
    before = row.updated_at

    client.post(
        "/api/prototype-labels",
        json={"model_id": model.id, "prototype_index": 0, "label": "b"},
    )
    db.expire_all()
    assert db.get(PrototypeLabel, created["id"]).updated_at > before


def test_different_prototypes_get_separate_rows(client, db, model):
    client.post(
        "/api/prototype-labels",
        json={"model_id": model.id, "prototype_index": 0, "label": "a"},
    )
    client.post(
        "/api/prototype-labels",
        json={"model_id": model.id, "prototype_index": 1, "label": "b"},
    )
    assert db.query(PrototypeLabel).count() == 2


def test_label_404_for_an_unknown_model(client, db):
    resp = client.post(
        "/api/prototype-labels",
        json={"model_id": "ghost", "prototype_index": 0, "label": "x"},
    )
    assert resp.status_code == 404


def test_label_400_when_the_index_exceeds_n_proto(client, db, model):
    resp = client.post(
        "/api/prototype-labels",
        json={"model_id": model.id, "prototype_index": model.n_proto, "label": "x"},
    )
    assert resp.status_code == 400
    assert "n_proto" in resp.json()["detail"]


def test_label_accepts_the_last_valid_index(client, db, model):
    resp = client.post(
        "/api/prototype-labels",
        json={"model_id": model.id, "prototype_index": model.n_proto - 1, "label": "x"},
    )
    assert resp.status_code == 200


# --- GET /api/prototype-labels --------------------------------------------


def test_labels_are_listed_in_prototype_order(client, db, model):
    for idx in (3, 0, 2):
        client.post(
            "/api/prototype-labels",
            json={"model_id": model.id, "prototype_index": idx, "label": f"p{idx}"},
        )
    body = client.get("/api/prototype-labels", params={"model_id": model.id}).json()
    assert [r["prototype_index"] for r in body] == [0, 2, 3]


def test_labels_are_scoped_to_one_model(client, db, model):
    other = client.post(
        "/api/prototype-labels",
        json={"model_id": model.id, "prototype_index": 0, "label": "mine"},
    ).json()
    body = client.get("/api/prototype-labels", params={"model_id": "someone-else"}).json()
    assert body == []
    assert other["label"] == "mine"


def test_listing_labels_requires_a_model_id(client, db):
    assert client.get("/api/prototype-labels").status_code == 422


# --- DELETE /api/prototype-labels/{id} ------------------------------------


def test_deleting_a_label_returns_204_and_removes_the_row(client, db, model):
    created = client.post(
        "/api/prototype-labels",
        json={"model_id": model.id, "prototype_index": 0, "label": "x"},
    ).json()
    assert client.delete(f"/api/prototype-labels/{created['id']}").status_code == 204
    assert db.query(PrototypeLabel).count() == 0


def test_deleting_an_unknown_label_404s(client, db):
    assert client.delete("/api/prototype-labels/ghost").status_code == 404


# --- /api/model-notes -----------------------------------------------------


def test_creating_a_note_returns_it(client, db, model):
    resp = client.post("/api/model-notes", json={"model_id": model.id, "body": "looks good"})
    assert resp.status_code == 200
    assert resp.json()["body"] == "looks good"


def test_note_404_for_an_unknown_model(client, db):
    assert client.post("/api/model-notes", json={"model_id": "ghost", "body": "x"}).status_code == 404


def test_notes_are_listed_newest_first(client, db, model):
    older = client.post("/api/model-notes", json={"model_id": model.id, "body": "first"}).json()
    newer = client.post("/api/model-notes", json={"model_id": model.id, "body": "second"}).json()
    row = db.get(ModelNote, older["id"])
    row.created_at = datetime.utcnow() - timedelta(hours=1)
    db.add(row)
    db.commit()

    body = client.get("/api/model-notes", params={"model_id": model.id}).json()
    assert [n["id"] for n in body] == [newer["id"], older["id"]]


def test_notes_are_scoped_to_one_model(client, db, model):
    client.post("/api/model-notes", json={"model_id": model.id, "body": "x"})
    assert client.get("/api/model-notes", params={"model_id": "other"}).json() == []


def test_listing_notes_requires_a_model_id(client, db):
    assert client.get("/api/model-notes").status_code == 422


def test_patching_a_note_replaces_its_body(client, db, model):
    created = client.post("/api/model-notes", json={"model_id": model.id, "body": "draft"}).json()
    body = client.patch(f"/api/model-notes/{created['id']}", json={"body": "final"}).json()
    assert body["id"] == created["id"]
    assert body["body"] == "final"


def test_patching_a_note_bumps_updated_at(client, db, model):
    created = client.post("/api/model-notes", json={"model_id": model.id, "body": "draft"}).json()
    row = db.get(ModelNote, created["id"])
    row.updated_at = datetime.utcnow() - timedelta(hours=1)
    db.add(row)
    db.commit()
    before = row.updated_at

    client.patch(f"/api/model-notes/{created['id']}", json={"body": "final"})
    db.expire_all()
    assert db.get(ModelNote, created["id"]).updated_at > before


def test_patching_an_unknown_note_404s(client, db):
    assert client.patch("/api/model-notes/ghost", json={"body": "x"}).status_code == 404


def test_deleting_a_note_returns_204_and_removes_the_row(client, db, model):
    created = client.post("/api/model-notes", json={"model_id": model.id, "body": "x"}).json()
    assert client.delete(f"/api/model-notes/{created['id']}").status_code == 204
    assert db.query(ModelNote).count() == 0


def test_deleting_an_unknown_note_404s(client, db):
    assert client.delete("/api/model-notes/ghost").status_code == 404

"""HTTP surface of /api/splits — creating the training split, listing, lookup."""
from __future__ import annotations

import json

import pytest

from app.db.models import Split


@pytest.fixture()
def env(tmp_path, override_settings):
    """Allowed root holding a source CSV + a temp splits output root."""
    data = tmp_path / "data"
    data.mkdir()
    splits_root = tmp_path / "splits"
    splits_root.mkdir()
    override_settings(
        allowed_roots=[data.resolve()],
        datasets_splits_root=splits_root.resolve(),
        panther_repo_path="",  # force the standalone DATASETS_SPLITS_ROOT branch
    )
    csv_path = data / "cohort.csv"
    csv_path.write_text("slide_id,label\n" + "\n".join(f"S{i},x" for i in range(20)) + "\n")
    return csv_path


# --- POST /api/splits -----------------------------------------------------


def test_create_single_split_puts_every_row_in_train(client, db, env):
    body = client.post(
        "/api/splits",
        json={"dataset_name": "ds", "source_csv": str(env), "kind": "single", "seed": 1},
    ).json()
    assert body["k"] == 1
    assert body["per_fold_counts"][0]["train"] == 20
    assert body["per_fold_counts"][0]["test"] == 0


def test_single_split_ignores_k(client, db, env):
    """The UI omits k entirely; an explicit k must not change the outcome."""
    body = client.post(
        "/api/splits",
        json={"dataset_name": "ds", "source_csv": str(env), "kind": "single", "k": 7, "seed": 1},
    ).json()
    assert body["k"] == 1
    assert len(body["per_fold_counts"]) == 1


def test_single_split_writes_one_fold_holding_the_whole_cohort(client, db, env):
    from pathlib import Path

    body = client.post(
        "/api/splits",
        json={"dataset_name": "ds", "source_csv": str(env), "kind": "single", "seed": 1},
    ).json()

    fold = Path(body["abs_path"]) / "k=0"
    assert fold.is_dir()
    assert not (Path(body["abs_path"]) / "k=1").exists()
    assert len(fold.joinpath("train.csv").read_text().splitlines()) == body["total_rows"] + 1


def test_single_split_name_marks_it_as_all_train(client, db, env):
    body = client.post(
        "/api/splits",
        json={"dataset_name": "ds", "source_csv": str(env), "kind": "single", "seed": 4},
    ).json()
    assert body["split_name"].startswith("alltrain_seed_4_")


def test_create_400_when_source_csv_is_not_a_file(client, db, env):
    resp = client.post(
        "/api/splits",
        json={"dataset_name": "ds", "source_csv": str(env.parent), "kind": "single", "seed": 1},
    )
    assert resp.status_code == 400
    assert "existing file" in resp.json()["detail"]


def test_create_403_when_source_csv_is_outside_the_roots(client, db, env, tmp_path):
    outside = tmp_path / "elsewhere.csv"
    outside.write_text("slide_id\nS1\n")
    resp = client.post(
        "/api/splits", json={"dataset_name": "ds", "source_csv": str(outside), "kind": "single", "seed": 1}
    )
    assert resp.status_code == 403


def test_create_400_when_the_csv_has_no_slide_id_column(client, db, env):
    bad = env.parent / "bad.csv"
    bad.write_text("foo,bar\n1,2\n3,4\n")
    resp = client.post(
        "/api/splits", json={"dataset_name": "ds", "source_csv": str(bad), "kind": "single", "seed": 1}
    )
    assert resp.status_code == 400
    assert "slide_id" in resp.json()["detail"]


def test_create_422_on_an_invalid_dataset_name(client, db, env):
    resp = client.post(
        "/api/splits",
        json={"dataset_name": "bad name/../etc", "source_csv": str(env), "kind": "single", "seed": 1},
    )
    assert resp.status_code == 422


# --- GET /api/splits ------------------------------------------------------


def test_list_returns_every_created_split(client, db, env):
    first = client.post(
        "/api/splits", json={"dataset_name": "ds", "source_csv": str(env), "kind": "single", "seed": 1}
    ).json()
    second = client.post(
        "/api/splits", json={"dataset_name": "ds", "source_csv": str(env), "kind": "single", "seed": 2}
    ).json()
    ids = {s["id"] for s in client.get("/api/splits").json()}
    assert ids == {first["id"], second["id"]}


def test_list_orders_newest_first(client, db, env):
    from datetime import datetime, timedelta

    older = client.post(
        "/api/splits", json={"dataset_name": "ds", "source_csv": str(env), "kind": "single", "seed": 1}
    ).json()
    newer = client.post(
        "/api/splits", json={"dataset_name": "ds", "source_csv": str(env), "kind": "single", "seed": 2}
    ).json()
    # Both rows are stamped within the same second; separate them explicitly.
    row = db.get(Split, older["id"])
    row.created_at = datetime.utcnow() - timedelta(hours=1)
    db.add(row)
    db.commit()

    ids = [s["id"] for s in client.get("/api/splits").json()]
    assert ids == [newer["id"], older["id"]]


def test_list_filters_by_dataset_name(client, db, env):
    client.post("/api/splits", json={"dataset_name": "alpha", "source_csv": str(env), "kind": "single", "seed": 1})
    client.post("/api/splits", json={"dataset_name": "beta", "source_csv": str(env), "kind": "single", "seed": 1})
    body = client.get("/api/splits", params={"dataset_name": "alpha"}).json()
    assert [s["dataset_name"] for s in body] == ["alpha"]


def test_list_is_empty_on_a_fresh_database(client, db):
    assert client.get("/api/splits").json() == []


# --- GET /api/splits/{id} -------------------------------------------------


def test_get_returns_the_split_with_its_parsed_counts(client, db, env):
    created = client.post(
        "/api/splits",
        json={"dataset_name": "ds", "source_csv": str(env), "kind": "single", "seed": 1},
    ).json()
    body = client.get(f"/api/splits/{created['id']}").json()
    assert body["id"] == created["id"]
    assert len(body["per_fold_counts"]) == 1
    assert body["per_fold_counts"][0] == {"train": 20, "val": 0, "test": 0}


def test_get_404_for_an_unknown_split(client, db):
    assert client.get("/api/splits/nope").status_code == 404

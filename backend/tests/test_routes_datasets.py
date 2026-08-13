"""Pure-python tests for the dataset/slide/model enumeration endpoints.

No ML deps: slides come from empty `*.h5` files in a tmp features dir, and WSI
resolution is monkeypatched so nothing tries to open a real slide.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.config import settings
from app.db.models import Model


@pytest.fixture()
def allow_tmp(tmp_path):
    """Point settings.allowed_roots at tmp_path so real resolve_within_roots
    (used by the route AND by find_trident_thumbnail) accepts our fixtures."""
    original = settings.allowed_roots
    object.__setattr__(settings, "allowed_roots", [tmp_path.resolve()])
    yield
    object.__setattr__(settings, "allowed_roots", original)


def _make_model(
    db,
    *,
    dataset_name: str,
    features_dir,
    run_kind: str | None = "single",
    trident_run_id: str | None = None,
    created_at: datetime | None = None,
) -> Model:
    mid = str(uuid.uuid4())
    m = Model(
        id=mid,
        created_at=created_at or datetime.utcnow(),
        base_name="m",
        model_name=f"m_{mid[:8]}",
        display_name="M",
        group_id=mid,
        fold_index=0,
        fold_k=1,
        run_kind=run_kind,
        dataset_name=dataset_name,
        features_dir=str(features_dir),
        trident_run_id=trident_run_id,
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


# --- GET /api/datasets ----------------------------------------------------


def test_list_datasets_only_single_models(client, db, tmp_path):
    feats = tmp_path / "feats"
    feats.mkdir()
    # dsA: two single models -> model_count 2
    _make_model(db, dataset_name="dsA", features_dir=feats)
    _make_model(db, dataset_name="dsA", features_dir=feats)
    # dsB: one single model
    _make_model(db, dataset_name="dsB", features_dir=feats)
    # dsUntagged: ONLY models with run_kind unset -> must NOT appear
    _make_model(db, dataset_name="dsUntagged", features_dir=feats, run_kind=None)

    resp = client.get("/api/datasets")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = [d["dataset_name"] for d in body]
    assert names == ["dsA", "dsB"]  # sorted, no dsUntagged
    counts = {d["dataset_name"]: d["model_count"] for d in body}
    assert counts == {"dsA": 2, "dsB": 1}


def test_list_datasets_counts_only_models_tagged_single(client, db, tmp_path):
    feats = tmp_path / "feats"
    feats.mkdir()
    _make_model(db, dataset_name="mixed", features_dir=feats, run_kind="single")
    _make_model(db, dataset_name="mixed", features_dir=feats, run_kind=None)

    resp = client.get("/api/datasets")
    assert resp.status_code == 200
    body = resp.json()
    assert body == [{"dataset_name": "mixed", "model_count": 1, "slide_count": None}]


# --- GET /api/datasets/{name}/slides --------------------------------------


def test_slides_enumerates_h5_stems_and_thumbnails(
    client, db, tmp_path, monkeypatch, allow_tmp
):
    # Canonical TRIDENT layout: {job_dir}/{mag}x_{ps}px/features_{enc}
    job_dir = tmp_path / "job"
    features = job_dir / "20x_256px_0px_overlap" / "features_uni_v1"
    features.mkdir(parents=True)
    for stem in ("slideB", "slideA", "slideC"):
        (features / f"{stem}.h5").write_bytes(b"")

    # TRIDENT thumbnails for two of the three slides.
    thumbs = job_dir / "thumbnails"
    thumbs.mkdir()
    (thumbs / "slideA.png").write_bytes(b"")
    (thumbs / "slideC.jpg").write_bytes(b"")

    wsi_dir = tmp_path / "wsi"
    wsi_dir.mkdir()

    model = _make_model(db, dataset_name="dsX", features_dir=features)

    # Monkeypatch WSI resolution: wsi_dir present, and every slide resolves to a
    # fake path under wsi_dir (no real openslide involved).
    import app.routes.datasets as ds

    monkeypatch.setattr(ds, "resolve_dataset_wsi_dir", lambda m, d: wsi_dir)
    monkeypatch.setattr(
        ds, "resolve_wsi_path", lambda stem, wdir: wsi_dir / f"{stem}.svs"
    )

    resp = client.get("/api/datasets/dsX/slides")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["dataset_name"] == "dsX"
    assert body["features_dir"] == str(features)
    assert body["wsi_dir"] == str(wsi_dir)
    assert body["slide_count"] == 3
    # Sorted stems.
    assert [s["slide_id"] for s in body["slides"]] == ["slideA", "slideB", "slideC"]
    # Two TRIDENT thumbnails on disk (slideA.png, slideC.jpg).
    assert body["thumbnails_found"] == 2

    first = body["slides"][0]
    assert first["has_wsi"] is True
    assert first["wsi_path"] == str(wsi_dir / "slideA.svs")
    assert first["thumbnail_url"].startswith("/api/slide-thumbnail?path=")
    # features_dir param is present + url-encoded.
    from urllib.parse import quote

    assert f"features_dir={quote(str(features), safe='')}" in first["thumbnail_url"]
    assert quote(str(wsi_dir / "slideA.svs"), safe="") in first["thumbnail_url"]


def test_slides_no_wsi_dir_null_thumbnail(client, db, tmp_path, monkeypatch, allow_tmp):
    features = tmp_path / "job" / "20x_256px_0px_overlap" / "features_uni_v1"
    features.mkdir(parents=True)
    (features / "s1.h5").write_bytes(b"")
    model = _make_model(db, dataset_name="dsY", features_dir=features)

    import app.routes.datasets as ds

    monkeypatch.setattr(ds, "resolve_dataset_wsi_dir", lambda m, d: None)

    resp = client.get("/api/datasets/dsY/slides")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["wsi_dir"] is None
    assert body["slide_count"] == 1
    s = body["slides"][0]
    assert s["slide_id"] == "s1"
    assert s["has_wsi"] is False
    assert s["wsi_path"] is None
    assert s["thumbnail_url"] is None


def test_slides_missing_features_dir_graceful(client, db, tmp_path, monkeypatch, allow_tmp):
    missing = tmp_path / "nope" / "features_uni_v1"
    model = _make_model(db, dataset_name="dsZ", features_dir=missing)

    import app.routes.datasets as ds

    monkeypatch.setattr(ds, "resolve_dataset_wsi_dir", lambda m, d: None)

    resp = client.get("/api/datasets/dsZ/slides")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["slides"] == []
    assert body["slide_count"] == 0
    assert body["thumbnails_found"] == 0
    assert body["note"]  # explains the missing dir


def test_slides_404_unknown_dataset(client, db):
    resp = client.get("/api/datasets/does-not-exist/slides")
    assert resp.status_code == 404


def test_slides_404_when_no_model_is_tagged_single(client, db, tmp_path):
    feats = tmp_path / "feats"
    feats.mkdir()
    _make_model(db, dataset_name="untagged", features_dir=feats, run_kind=None)
    resp = client.get("/api/datasets/untagged/slides")
    assert resp.status_code == 404


# --- GET /api/datasets/{name}/models --------------------------------------


def test_dataset_models_only_single(client, db, tmp_path):
    feats = tmp_path / "feats"
    feats.mkdir()
    older = datetime.utcnow() - timedelta(hours=1)
    newer = datetime.utcnow()
    m_old = _make_model(db, dataset_name="dsM", features_dir=feats, created_at=older)
    m_new = _make_model(db, dataset_name="dsM", features_dir=feats, created_at=newer)
    _make_model(db, dataset_name="dsM", features_dir=feats, run_kind=None)  # untagged
    _make_model(db, dataset_name="other", features_dir=feats)  # different dataset

    resp = client.get("/api/datasets/dsM/models")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = [m["id"] for m in body]
    # Only the two single models for dsM, newest first.
    assert ids == [m_new.id, m_old.id]
    assert all(m["run_kind"] == "single" for m in body)

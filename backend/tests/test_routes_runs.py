"""GET /api/runs/resolve — mapping a features directory back to its TRIDENT run.

This is what lets the PANTHER form auto-fill encoder/mag/patch_size/in_dim from
a directory the user picked in the file browser.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.db.models import TridentRun
from app.services.runner import feature_dim_for


@pytest.fixture()
def feats(tmp_path, override_settings):
    root = tmp_path / "data"
    d = root / "trident_processed" / "ds" / "20x_256px_0px_overlap" / "features_uni_v1"
    d.mkdir(parents=True)
    override_settings(allowed_roots=[root.resolve()])
    return d


def _run(db, output_dir, *, encoder="uni_v1", mag=20, patch_size=256, dataset="ds") -> TridentRun:
    row = TridentRun(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        dataset_name=dataset,
        wsi_dir="/wsi",
        patch_encoder=encoder,
        mag=mag,
        patch_size=patch_size,
        command="x",
        status="succeeded",
        output_dir=str(output_dir),
    )
    db.add(row)
    db.commit()
    return row


def test_resolve_returns_the_matching_run_and_derived_in_dim(client, db, feats):
    run = _run(db, feats, encoder="uni_v1")
    body = client.get("/api/runs/resolve", params={"features_dir": str(feats)}).json()
    assert body["trident_run_id"] == run.id
    assert body["dataset_name"] == "ds"
    assert body["patch_encoder"] == "uni_v1"
    assert body["mag"] == 20
    assert body["patch_size"] == 256
    assert body["in_dim"] == feature_dim_for("uni_v1")


def test_resolve_matches_after_path_normalization(client, db, feats):
    """A `.`/`..`-laden path pointing at the same directory still matches."""
    run = _run(db, feats)
    noisy = feats.parent / "." / feats.name
    body = client.get("/api/runs/resolve", params={"features_dir": str(noisy)}).json()
    assert body["trident_run_id"] == run.id


def test_resolve_ignores_runs_whose_output_dir_differs(client, db, feats):
    other = feats.parent / "features_phikon"
    other.mkdir()
    _run(db, other, encoder="phikon")
    run = _run(db, feats, encoder="uni_v1")
    body = client.get("/api/runs/resolve", params={"features_dir": str(feats)}).json()
    assert body["trident_run_id"] == run.id


def test_resolve_400_when_no_run_produced_that_directory(client, db, feats):
    resp = client.get("/api/runs/resolve", params={"features_dir": str(feats)})
    assert resp.status_code == 400
    assert "No TRIDENT run found" in resp.json()["detail"]


def test_resolve_409_when_two_runs_share_the_directory(client, db, feats):
    _run(db, feats)
    _run(db, feats)
    resp = client.get("/api/runs/resolve", params={"features_dir": str(feats)})
    assert resp.status_code == 409
    assert "Ambiguous" in resp.json()["detail"]


def test_resolve_403_outside_the_allowed_roots(client, db, feats, tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    assert client.get(
        "/api/runs/resolve", params={"features_dir": str(outside)}
    ).status_code == 403


def test_resolve_422_when_features_dir_is_missing(client, db, feats):
    assert client.get("/api/runs/resolve").status_code == 422


def test_resolve_reports_a_null_in_dim_for_an_unknown_encoder(client, db, feats):
    _run(db, feats, encoder="some_future_encoder")
    body = client.get("/api/runs/resolve", params={"features_dir": str(feats)}).json()
    assert body["in_dim"] is None

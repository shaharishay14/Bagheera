"""Tests for the manual point-based ROI selection endpoint + its mapping.

Pure-python: no torch/cv2/openslide. The endpoint's rendering is monkeypatched
(`visualization.render_roi_at_point` / `load_section_a_cache` / WSI resolution)
so nothing heavy runs; we only assert routing, the two persistence modes, and
the point→window pick logic (containment + nearest fallback).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest

from app.config import settings
from app.db.models import Model
from app.services import visualization


@pytest.fixture()
def viz_root(tmp_path, monkeypatch):
    original = settings.viz_cache_root
    object.__setattr__(settings, "viz_cache_root", tmp_path / "viz_cache")
    (tmp_path / "viz_cache" / "job_logs").mkdir(parents=True, exist_ok=True)
    yield tmp_path
    object.__setattr__(settings, "viz_cache_root", original)


def _make_model(db, viz_artifacts=None) -> Model:
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
        features_dir="/tmp/features",
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
        viz_artifacts=json.dumps(viz_artifacts) if viz_artifacts else None,
    )
    db.add(m)
    db.commit()
    return m


# --- Endpoint routing / persistence ---------------------------------------


def test_select_roi_404_missing_model(client, db, viz_root):
    resp = client.post("/api/models/nope/select-roi", json={"fx": 0.5, "fy": 0.5})
    assert resp.status_code == 404


def test_select_roi_409_when_no_section_a(client, db, viz_root):
    model = _make_model(db, viz_artifacts=None)
    resp = client.post(
        f"/api/models/{model.id}/select-roi", json={"fx": 0.5, "fy": 0.5}
    )
    assert resp.status_code == 409


def test_select_roi_409_when_no_compare_manifest(client, db, viz_root):
    model = _make_model(db, viz_artifacts={"section_a": {"roi_index": 0}})
    resp = client.post(
        f"/api/models/{model.id}/select-roi",
        json={"slide_id": "slideX", "fx": 0.2, "fy": 0.2},
    )
    assert resp.status_code == 409


def test_select_roi_preview_persists_and_returns_model_info(
    client, db, viz_root, monkeypatch
):
    model = _make_model(
        db, viz_artifacts={"section_a": {"slide_id": "slideA", "roi_index": 0}}
    )

    monkeypatch.setattr(
        visualization,
        "load_section_a_cache",
        lambda m, out_dir=None: ("slideA", [[0, 0]], [0], 256),
    )
    monkeypatch.setattr(
        visualization, "resolve_dataset_wsi_dir", lambda m, d: "/wsi"
    )
    monkeypatch.setattr(
        visualization, "resolve_wsi_path", lambda sid, wd: "/wsi/slideA.svs"
    )
    monkeypatch.setattr(
        visualization,
        "render_roi_at_point",
        lambda *a, **k: ("/abs/raw.png", "/abs/col.png", [10, 20, 30, 40], 3, 7),
    )

    resp = client.post(
        f"/api/models/{model.id}/select-roi", json={"fx": 0.4, "fy": 0.6}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    sec = body["viz_artifacts"]["section_a"]
    assert sec["roi_raw"] == "/abs/raw.png"
    assert sec["roi_colored"] == "/abs/col.png"
    assert sec["roi_bbox"] == [10, 20, 30, 40]
    assert sec["roi_index"] == 3

    # Persisted to the DB column.
    db.refresh(model)
    stored = json.loads(model.viz_artifacts)["section_a"]
    assert stored["roi_index"] == 3
    assert stored["roi_bbox"] == [10, 20, 30, 40]


def test_select_roi_compare_rewrites_manifest(client, db, viz_root, monkeypatch):
    model = _make_model(db, viz_artifacts={"section_a": {"roi_index": 0}})

    compare_dir = viz_root / "viz_cache" / model.id / "compare" / "slideB"
    compare_dir.mkdir(parents=True)
    manifest = {"slide_id": "slideB", "roi_index": 0, "on_tissue": "/abs/ot.png"}
    (compare_dir / "manifest.json").write_text(json.dumps(manifest))

    monkeypatch.setattr(
        visualization,
        "load_section_a_cache",
        lambda m, out_dir=None: ("slideB", [[0, 0]], [0], 256),
    )
    monkeypatch.setattr(
        visualization, "resolve_dataset_wsi_dir", lambda m, d: "/wsi"
    )
    monkeypatch.setattr(
        visualization, "resolve_wsi_path", lambda sid, wd: "/wsi/slideB.svs"
    )
    monkeypatch.setattr(
        visualization,
        "render_roi_at_point",
        lambda *a, **k: ("/abs/r2.png", "/abs/c2.png", [1, 2, 3, 4], 5, 9),
    )

    resp = client.post(
        f"/api/models/{model.id}/select-roi",
        json={"slide_id": "slideB", "fx": 0.1, "fy": 0.9},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    arts = body["artifacts"]
    assert arts["roi_raw"] == "/abs/r2.png"
    assert arts["roi_index"] == 5
    assert arts["roi_bbox"] == [1, 2, 3, 4]
    # on_tissue (unrelated key) survived the rewrite.
    assert arts["on_tissue"] == "/abs/ot.png"

    # Manifest on disk was rewritten.
    on_disk = json.loads((compare_dir / "manifest.json").read_text())
    assert on_disk["roi_index"] == 5
    assert on_disk["roi_raw"] == "/abs/r2.png"
    assert on_disk["on_tissue"] == "/abs/ot.png"


def test_select_roi_409_when_wsi_unavailable(client, db, viz_root, monkeypatch):
    model = _make_model(db, viz_artifacts={"section_a": {"roi_index": 0}})
    monkeypatch.setattr(
        visualization,
        "load_section_a_cache",
        lambda m, out_dir=None: ("slideA", [[0, 0]], [0], 256),
    )
    monkeypatch.setattr(visualization, "resolve_dataset_wsi_dir", lambda m, d: None)

    resp = client.post(
        f"/api/models/{model.id}/select-roi", json={"fx": 0.5, "fy": 0.5}
    )
    assert resp.status_code == 409


def test_select_roi_422_on_visualization_error(client, db, viz_root, monkeypatch):
    model = _make_model(db, viz_artifacts={"section_a": {"roi_index": 0}})
    monkeypatch.setattr(
        visualization,
        "load_section_a_cache",
        lambda m, out_dir=None: ("slideA", [[0, 0]], [0], 256),
    )
    monkeypatch.setattr(visualization, "resolve_dataset_wsi_dir", lambda m, d: "/wsi")
    monkeypatch.setattr(
        visualization, "resolve_wsi_path", lambda sid, wd: "/wsi/slideA.svs"
    )

    def _boom(*a, **k):
        raise visualization.VisualizationError("no window")

    monkeypatch.setattr(visualization, "render_roi_at_point", _boom)

    resp = client.post(
        f"/api/models/{model.id}/select-roi", json={"fx": 0.5, "fy": 0.5}
    )
    assert resp.status_code == 422


# --- Point → window mapping (unit) ----------------------------------------


class _StubModel:
    n_proto = 4


def test_render_roi_at_point_containment(monkeypatch):
    """Click inside window B's box picks B (index 1), not the nearer-center A."""
    # Two non-overlapping windows: A at origin (span 100), B at x=100.
    windows = [
        (0, 0, 100, 100, [0]),
        (100, 0, 100, 100, [1]),
    ]
    monkeypatch.setattr(visualization, "_select_roi_windows", lambda *a, **k: windows)

    captured = {}

    def _spy(model, coords, labels, ps, wsi, window, idx, n, out_dir):
        captured["window"] = window
        captured["idx"] = idx
        captured["n"] = n
        return ("raw", "col", [0, 0, 0, 0], idx, n)

    monkeypatch.setattr(visualization, "_render_roi_window", _spy)

    # coords bbox spans x in [0, 200) (200 = max 100 + patch_size 100), so
    # fx=0.75 → tx=150 which lands inside window B [100,200).
    coords = [[0, 0], [100, 0]]
    visualization.render_roi_at_point(
        _StubModel(), coords, [0, 1], 100, "/wsi/s.svs", 0.75, 0.25
    )
    assert captured["idx"] == 1
    assert captured["window"] == windows[1]
    assert captured["n"] == 2


def test_render_roi_at_point_nearest_fallback(monkeypatch):
    """Click on a gap (no window contains it) picks the nearest-center window."""
    # Windows only at the far left and far right; a middle click hits neither.
    windows = [
        (0, 0, 100, 100, [0]),      # center (50, 50)
        (300, 0, 100, 100, [1]),    # center (350, 50)
    ]
    monkeypatch.setattr(visualization, "_select_roi_windows", lambda *a, **k: windows)

    captured = {}

    def _spy(model, coords, labels, ps, wsi, window, idx, n, out_dir):
        captured["idx"] = idx
        captured["window"] = window
        return ("raw", "col", [0, 0, 0, 0], idx, n)

    monkeypatch.setattr(visualization, "_render_roi_window", _spy)

    # coords bbox x in [0, 400); fx=0.55 → tx=220, in the gap [100,300).
    # Nearest center: window0 center 50 (d=170) vs window1 center 350 (d=130) → B.
    coords = [[0, 0], [300, 0]]
    visualization.render_roi_at_point(
        _StubModel(), coords, [0, 1], 100, "/wsi/s.svs", 0.55, 0.5
    )
    assert captured["idx"] == 1
    assert captured["window"] == windows[1]


def test_render_roi_at_point_no_windows_raises(monkeypatch):
    monkeypatch.setattr(visualization, "_select_roi_windows", lambda *a, **k: [])
    with pytest.raises(visualization.VisualizationError):
        visualization.render_roi_at_point(
            _StubModel(), [[0, 0]], [0], 100, "/wsi/s.svs", 0.5, 0.5
        )


def test_render_roi_at_point_clamps_out_of_range(monkeypatch):
    """fx/fy outside [0,1] are clamped, not passed through to blow up the map."""
    windows = [(0, 0, 100, 100, [0])]
    monkeypatch.setattr(visualization, "_select_roi_windows", lambda *a, **k: windows)

    captured = {}

    def _spy(model, coords, labels, ps, wsi, window, idx, n, out_dir):
        captured["called"] = True
        return ("raw", "col", [0, 0, 0, 0], idx, n)

    monkeypatch.setattr(visualization, "_render_roi_window", _spy)
    # fx way beyond 1, fy negative — should still resolve to the single window.
    out = visualization.render_roi_at_point(
        _StubModel(), [[0, 0]], [0], 100, "/wsi/s.svs", 9.0, -3.0
    )
    assert captured["called"]
    assert out[3] == 0  # used_idx of the only window

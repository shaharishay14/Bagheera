"""Tests for the WSI slide-thumbnail endpoint.

Pure-python only — the openslide generation path is never exercised (it needs a
heavy dep); it's reached via a monkeypatch that raises, yielding the 422. The
TRIDENT branch serves a fake PNG byte string (no openslide involved).
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.routes import thumbnails as thumbnails_route
from app.services.thumbnails import ThumbnailError, slide_thumb_cache_key, trident_job_dir


@pytest.fixture()
def roots(tmp_path):
    """Point allowed_roots + viz_cache_root at temp dirs (frozen dataclass override)."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    viz_root = tmp_path / "viz_cache"
    (viz_root / "slide_thumbs").mkdir(parents=True)

    orig_roots = settings.allowed_roots
    orig_viz = settings.viz_cache_root
    object.__setattr__(settings, "allowed_roots", [data_root.resolve()])
    object.__setattr__(settings, "viz_cache_root", viz_root.resolve())
    yield data_root
    object.__setattr__(settings, "allowed_roots", orig_roots)
    object.__setattr__(settings, "viz_cache_root", orig_viz)


def test_403_outside_roots(client, roots, tmp_path):
    # A path outside the allowed data root → 403.
    outside = tmp_path / "elsewhere" / "slide.svs"
    resp = client.get("/api/slide-thumbnail", params={"path": str(outside)})
    assert resp.status_code == 403, resp.text


def test_404_missing_file(client, roots):
    # In-roots but no such file → 404.
    missing = roots / "nope.svs"
    resp = client.get("/api/slide-thumbnail", params={"path": str(missing)})
    assert resp.status_code == 404, resp.text


def test_trident_thumbnail_branch(client, roots):
    # Fake WSI (existence is all the route checks before the TRIDENT probe).
    wsi = roots / "slideA.svs"
    wsi.write_bytes(b"fake-wsi")

    # Build the TRIDENT layout: {job_dir}/20x_256px_0px_overlap/features_x
    job_dir = roots / "trident_processed" / "ds"
    features_dir = job_dir / "20x_256px_0px_overlap" / "features_x"
    features_dir.mkdir(parents=True)
    thumbs_dir = job_dir / "thumbnails"
    thumbs_dir.mkdir()
    fake_png = b"\x89PNG\r\n\x1a\nFAKE"
    (thumbs_dir / "slideA.png").write_bytes(fake_png)

    resp = client.get(
        "/api/slide-thumbnail",
        params={"path": str(wsi), "features_dir": str(features_dir)},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-Thumbnail-Source"] == "trident"
    assert resp.content == fake_png


def test_trident_probe_falls_through_when_no_thumbnail(client, roots, monkeypatch):
    # WSI exists, features_dir given, but no thumbnails/ file → generation path.
    wsi = roots / "slideB.svs"
    wsi.write_bytes(b"fake-wsi")
    features_dir = roots / "trident_processed" / "ds" / "20x_256px_0px_overlap" / "features_x"
    features_dir.mkdir(parents=True)

    # Don't actually open openslide — assert the generation path is reached.
    called = {}

    def fake_generate(resolved_path, max_px):
        called["hit"] = True
        raise ThumbnailError("no openslide in tests")

    monkeypatch.setattr(thumbnails_route, "generate_slide_thumbnail", fake_generate)

    resp = client.get(
        "/api/slide-thumbnail",
        params={"path": str(wsi), "features_dir": str(features_dir)},
    )
    assert called.get("hit") is True
    assert resp.status_code == 422, resp.text


def test_generation_path_422_on_openslide_failure(client, roots, monkeypatch):
    wsi = roots / "slideC.svs"
    wsi.write_bytes(b"fake-wsi")

    def fake_generate(resolved_path, max_px):
        raise ThumbnailError("openslide boom")

    monkeypatch.setattr(thumbnails_route, "generate_slide_thumbnail", fake_generate)

    resp = client.get("/api/slide-thumbnail", params={"path": str(wsi)})
    assert resp.status_code == 422, resp.text
    assert "boom" in resp.json()["detail"]


def test_cache_key_deterministic():
    k1 = slide_thumb_cache_key("/data/slide.svs", 1700000000.0, 123456, 512)
    k2 = slide_thumb_cache_key("/data/slide.svs", 1700000000.0, 123456, 512)
    assert k1 == k2
    # Different inputs → different key.
    assert slide_thumb_cache_key("/data/slide.svs", 1700000001.0, 123456, 512) != k1
    assert slide_thumb_cache_key("/data/slide.svs", 1700000000.0, 999999, 512) != k1
    assert slide_thumb_cache_key("/data/other.svs", 1700000000.0, 123456, 512) != k1


def test_job_dir_derivation():
    features_dir = "/data/trident_processed/ds/20x_256px_0px_overlap/features_uni_v1"
    assert str(trident_job_dir(features_dir)) == "/data/trident_processed/ds"

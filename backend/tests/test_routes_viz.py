"""Visualization serving: SVG placeholders and the two-root file server.

The path-traversal contract from the module docstring of `routes/viz.py` is the
point of this file: absolute paths outside the roots are 403, missing files
inside them are 404, and no symlink or `..` may escape.
"""
from __future__ import annotations

import pytest

from app.routes.viz import _KIND_COLORS


@pytest.fixture()
def roots(tmp_path, override_settings):
    viz = tmp_path / "viz_cache"
    inf = tmp_path / "inference_outputs"
    viz.mkdir()
    inf.mkdir()
    (viz / "heatmap.png").write_bytes(b"\x89PNG\r\n\x1a\nviz")
    (inf / "tsne.png").write_bytes(b"\x89PNG\r\n\x1a\ninf")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.png").write_bytes(b"nope")
    override_settings(viz_cache_root=viz.resolve(), inference_root=inf.resolve())
    return viz, inf, outside


# --- GET /api/viz/placeholder/{kind} --------------------------------------


@pytest.mark.parametrize("kind", sorted(_KIND_COLORS))
def test_every_known_kind_renders_its_own_label(client, kind):
    resp = client.get(f"/api/viz/placeholder/{kind}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
    assert _KIND_COLORS[kind][2] in resp.text


def test_unknown_kind_falls_back_to_a_generic_preview(client):
    resp = client.get("/api/viz/placeholder/whatever")
    assert resp.status_code == 200
    assert "Preview" in resp.text


def test_label_overrides_the_default_title(client):
    assert "Fold 3 heatmap" in client.get(
        "/api/viz/placeholder/heatmap", params={"label": "Fold 3 heatmap"}
    ).text


def test_label_is_xml_escaped(client):
    resp = client.get(
        "/api/viz/placeholder/heatmap", params={"label": '<script>&"x"</script>'}
    )
    assert "<script>" not in resp.text
    assert "&lt;script&gt;" in resp.text
    assert "&quot;" in resp.text


def test_dimensions_land_in_the_viewbox(client):
    assert 'viewBox="0 0 800 600"' in client.get(
        "/api/viz/placeholder/umap", params={"width": 800, "height": 600}
    ).text


@pytest.mark.parametrize("params", [{"width": 10}, {"width": 5000}, {"height": 10}, {"height": 5000}])
def test_out_of_range_dimensions_are_rejected(client, params):
    assert client.get("/api/viz/placeholder/umap", params=params).status_code == 422


# --- GET /api/viz/{file_path} ---------------------------------------------


def test_serves_a_relative_path_from_the_viz_cache_root(client, roots):
    resp = client.get("/api/viz/heatmap.png")
    assert resp.status_code == 200
    assert resp.content == b"\x89PNG\r\n\x1a\nviz"


def test_serves_a_relative_path_from_the_inference_root(client, roots):
    resp = client.get("/api/viz/tsne.png")
    assert resp.status_code == 200
    assert resp.content == b"\x89PNG\r\n\x1a\ninf"


def test_serves_an_absolute_path_inside_a_root(client, roots):
    viz, _, _ = roots
    resp = client.get(f"/api/viz/{viz / 'heatmap.png'}")
    assert resp.status_code == 200
    assert resp.content == b"\x89PNG\r\n\x1a\nviz"


def test_serves_a_nested_relative_path(client, roots):
    viz, _, _ = roots
    nested = viz / "model-1" / "fold-0"
    nested.mkdir(parents=True)
    (nested / "umap.png").write_bytes(b"nested")
    assert client.get("/api/viz/model-1/fold-0/umap.png").content == b"nested"


def test_png_is_served_with_an_image_content_type(client, roots):
    assert client.get("/api/viz/heatmap.png").headers["content-type"] == "image/png"


def test_missing_relative_path_404s(client, roots):
    assert client.get("/api/viz/does-not-exist.png").status_code == 404


def test_missing_absolute_path_inside_a_root_404s(client, roots):
    viz, _, _ = roots
    assert client.get(f"/api/viz/{viz / 'gone.png'}").status_code == 404


def test_absolute_path_outside_the_roots_403s(client, roots):
    _, _, outside = roots
    assert client.get(f"/api/viz/{outside / 'secret.png'}").status_code == 403


def test_a_symlink_escaping_the_root_403s(client, roots):
    viz, _, outside = roots
    (viz / "escape.png").symlink_to(outside / "secret.png")
    assert client.get(f"/api/viz/{viz / 'escape.png'}").status_code == 403


def test_a_directory_inside_a_root_is_not_served(client, roots):
    viz, _, _ = roots
    (viz / "adir").mkdir()
    assert client.get(f"/api/viz/{viz / 'adir'}").status_code == 404
